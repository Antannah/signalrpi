# web_server.py -- Asynchroner Mini-Webserver für Pico W
import uasyncio as asyncio
import json
import gc
from static_html import HTML_PAGE

class WebServer:
    def __init__(self, device_manager, sniffer_queue, wlan, port=80):
        self.device_manager = device_manager
        self.sniffer_queue = sniffer_queue
        self.wlan = wlan
        self.port = port

    async def start(self):
        server = await asyncio.start_server(self.handle_client, "0.0.0.0", self.port)
        print("Web-Interface läuft auf Port", self.port)
        return server

    async def handle_client(self, reader, writer):
        try:
            line = await reader.readline()
            if not line:
                await writer.aclose()
                return

            req_line = line.decode("utf-8").strip()
            parts = req_line.split()
            if len(parts) < 2:
                await writer.aclose()
                return

            method = parts[0]
            url = parts[1]

            # Header überlesen & Content-Length ermitteln
            content_len = 0
            while True:
                h = await reader.readline()
                if not h or h == b"\r\n":
                    break
                h_str = h.decode("utf-8").lower()
                if h_str.startswith("content-length:"):
                    content_len = int(h_str.split(":")[1].strip())

            # Routing
            if url == "/" or url.startswith("/index"):
                # HTML Dashboard streamen
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n")
                writer.write(HTML_PAGE.encode("utf-8"))

            elif url == "/api/status":
                gc.collect()
                ip = self.wlan.ifconfig()[0] if self.wlan.isconnected() else "Offline"
                status = {
                    "ip": ip,
                    "wifi_rssi": getattr(self.wlan, "status")('rssi') if hasattr(self.wlan, 'status') else -50,
                    "free_ram": gc.mem_free(),
                    "allocated_ram": gc.mem_alloc()
                }
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n")
                writer.write(json.dumps(status).encode("utf-8"))

            elif url.startswith("/api/devices/toggle") and method == "POST":
                body = await reader.read(content_len) if content_len > 0 else b"{}"
                try:
                    data = json.loads(body.decode("utf-8"))
                    ha_id = data.get("id")
                    ok, new_state = self.device_manager.toggle_enabled(ha_id)
                    if ok:
                        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n")
                        writer.write(json.dumps({"ok": True, "enabled": new_state}).encode("utf-8"))
                    else:
                        writer.write(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")
                except Exception:
                    writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")

            elif url.startswith("/api/devices/profile") and method == "POST":
                body = await reader.read(content_len) if content_len > 0 else b"{}"
                try:
                    data = json.loads(body.decode("utf-8"))
                    ha_id = data.get("id")
                    profile = data.get("profile")
                    if ha_id and profile and self.device_manager.set_device_profile(ha_id, profile):
                        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"ok\":true}")
                    else:
                        writer.write(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")
                except Exception:
                    writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")

            elif url.startswith("/api/devices"):
                if method == "GET":
                    devs = self.device_manager.get_all()
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n")
                    writer.write(json.dumps(devs).encode("utf-8"))

                elif method == "POST":
                    body = await reader.read(content_len) if content_len > 0 else b"{}"
                    try:
                        new_dev = json.loads(body.decode("utf-8"))
                        self.device_manager.add_or_update(new_dev)
                        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"ok\":true}")
                    except Exception as ex:
                        writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")

                elif method == "DELETE":
                    # URL query ?id=xyz
                    dev_id = None
                    if "?id=" in url:
                        dev_id = url.split("?id=")[1].split("&")[0]
                    if dev_id and self.device_manager.delete(dev_id):
                        writer.write(b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n{\"ok\":true}")
                    else:
                        writer.write(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")

            elif url == "/api/reassign" and method == "POST":
                body = await reader.read(content_len) if content_len > 0 else b"{}"
                try:
                    data = json.loads(body.decode("utf-8"))
                    ha_id = data.get("ha_id")
                    new_id = data.get("new_id")
                    new_ch = data.get("channel")
                    if ha_id and new_id is not None and self.device_manager.reassign_sensor(ha_id, new_id, new_ch):
                        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"ok\":true}")
                    else:
                        writer.write(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")
                except Exception:
                    writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")

            elif url == "/api/live":
                # Gibt die neuesten gepufferten Sniffer-Pakete als JSON-Array zurück
                pkts = []
                while len(self.sniffer_queue) > 0:
                    pkts.append(self.sniffer_queue.pop(0))
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n")
                writer.write(json.dumps(pkts).encode("utf-8"))

            elif url == "/api/ota" and method == "POST":
                # GitHub OTA Update anstoßen
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"status\":\"started\"}")
                await writer.drain()
                await writer.aclose()
                try:
                    import ota_updater
                    ota_updater.update_from_github()
                except Exception as ex:
                    print("OTA Trigger Fehler:", ex)
                return

            elif url.startswith("/api/upload") and method == "POST":
                # Datei-Upload: Ziel-Dateiname aus Query Parameter ?filename=...
                filename = "uploaded_file.py"
                if "?filename=" in url:
                    filename = url.split("?filename=")[1].split("&")[0]
                
                # Sanitize filename (keine unerlaubten Pfade)
                filename = filename.replace("..", "").lstrip("/")
                
                try:
                    # Lese Dateiinhalt blockweise
                    remaining = content_len
                    with open(filename, "wb") as f:
                        while remaining > 0:
                            chunk_size = min(remaining, 512)
                            chunk = await reader.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            remaining -= len(chunk)
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"ok\":true}")
                except Exception as ex:
                    print("Upload Fehler:", ex)
                    writer.write(b"HTTP/1.1 500 Server Error\r\nConnection: close\r\n\r\n")

            else:
                writer.write(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\nNot Found")

            await writer.drain()
            await writer.aclose()
        except Exception as e:
            try:
                await writer.aclose()
            except Exception:
                pass
