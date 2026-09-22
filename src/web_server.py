# web_server.py -- Asynchroner Mini-Webserver für Pico W
import uasyncio as asyncio
import json
import gc

class WebServer:
    def __init__(self, device_manager, sniffer_queue, wlan, port=80, tx_handler=None):
        self.device_manager = device_manager
        self.sniffer_queue = sniffer_queue
        self.wlan = wlan
        self.port = port
        self.tx_handler = tx_handler

    async def start(self):
        server = await asyncio.start_server(self.handle_client, "0.0.0.0", self.port)
        print("Web-Interface läuft auf Port", self.port)
        return server

    async def handle_client(self, reader, writer):
        try:
            # 5 Sekunden Timeout für langsame oder abbrechende TCP-Verbindungen
            line = await asyncio.wait_for(reader.readline(), 5.0)
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

            # Header überlesen & Content-Length ermitteln (mit Timeout)
            content_len = 0
            while True:
                h = await asyncio.wait_for(reader.readline(), 3.0)
                if not h or h == b"\r\n":
                    break
                h_str = h.decode("utf-8").lower()
                if h_str.startswith("content-length:"):
                    content_len = int(h_str.split(":")[1].strip())

            # Routing
            if url == "/" or url.startswith("/index"):
                # HTML Dashboard chunked streamen aus Datei (extrem RAM-schonend)
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n")
                await writer.drain()
                try:
                    with open("index.html", "r") as f:
                        while True:
                            chunk = f.read(1024)
                            if not chunk:
                                break
                            writer.write(chunk.encode("utf-8"))
                            await writer.drain()
                except Exception:
                    # Fallback falls index.html noch nicht existiert
                    from static_html import HTML_PAGE
                    writer.write(HTML_PAGE.encode("utf-8"))
                    await writer.drain()

            elif url == "/api/status":
                gc.collect()
                ip = self.wlan.ifconfig()[0] if self.wlan.isconnected() else "Offline"
                status = {
                    "ip": ip,
                    "wifi_rssi": getattr(self.wlan, "status")('rssi') if hasattr(self.wlan, 'status') else -50,
                    "free_ram": gc.mem_free(),
                    "allocated_ram": gc.mem_alloc(),
                    "alerts": getattr(self, "alerts", [])
                }
                if hasattr(self, "cc_433") and self.cc_433:
                    status["cc_433"] = self.cc_433.check_hardware()
                if hasattr(self, "cc_868") and self.cc_868:
                    status["cc_868"] = self.cc_868.check_hardware()
                try:
                    import time
                    t = time.localtime()
                    status["time"] = "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])
                except Exception:
                    pass
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n")
                writer.write(json.dumps(status).encode("utf-8"))

            elif url == "/api/time" and method == "GET":
                import time_sync
                cfg = time_sync.load_time_config()
                import time
                t = time.localtime()
                cfg["current_time"] = "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n")
                writer.write(json.dumps(cfg).encode("utf-8"))

            elif url == "/api/time" and method == "POST":
                body = await reader.read(content_len) if content_len > 0 else b"{}"
                try:
                    import time_sync
                    new_cfg = json.loads(body.decode("utf-8"))
                    time_sync.save_time_config(new_cfg)
                    ok, timestr, srv = time_sync.sync_time(self.wlan)
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n")
                    writer.write(json.dumps({"ok": True, "time": timestr, "server": srv}).encode("utf-8"))
                except Exception as ex:
                    writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")

            elif url == "/api/devices/download":
                try:
                    with open("devices.json", "r") as f:
                        dev_data = f.read()
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Disposition: attachment; filename=\"devices.json\"\r\nConnection: close\r\n\r\n")
                    writer.write(dev_data.encode("utf-8"))
                except Exception:
                    writer.write(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n{}")

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
                    gc.collect()
                    body = b""
                    remaining = content_len
                    while remaining > 0:
                        chunk = await reader.read(min(remaining, 512))
                        if not chunk:
                            break
                        body += chunk
                        remaining -= len(chunk)
                    try:
                        new_dev = json.loads(body.decode("utf-8"))
                        # Gerät speichern (ohne MQTT-Discovery, um HTTP-Timeout zu vermeiden)
                        dev_id = new_dev.get("id")
                        if dev_id:
                            if "enabled" not in new_dev:
                                new_dev["enabled"] = True
                            found = False
                            for i, ex_dev in enumerate(self.device_manager.devices):
                                if ex_dev.get("id") == dev_id:
                                    self.device_manager.devices[i] = new_dev
                                    found = True
                                    break
                            if not found:
                                self.device_manager.devices.append(new_dev)
                            self.device_manager.save()
                            # Response sofort senden
                            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"ok\":true}")
                            await writer.drain()
                            await writer.aclose()
                            # MQTT-Discovery NACH dem Response (entkoppelt)
                            if self.device_manager.mqtt_client:
                                try:
                                    if new_dev.get("enabled", True):
                                        self.device_manager.publish_discovery(new_dev)
                                    else:
                                        self.device_manager.remove_discovery(dev_id)
                                except Exception as me:
                                    print("MQTT Discovery Fehler (async):", me)
                            return
                        else:
                            writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n{\"error\":\"missing id\"}")
                    except Exception as ex:
                        print("Device POST Fehler:", ex)
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

            elif url == "/api/it/send" and method == "POST":
                body = await reader.read(content_len) if content_len > 0 else b"{}"
                try:
                    data = json.loads(body.decode("utf-8"))
                    if self.tx_handler:
                        res = self.tx_handler(data)
                        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n")
                        writer.write(json.dumps({"ok": True, "result": res}).encode("utf-8"))
                    else:
                        writer.write(b"HTTP/1.1 501 Not Implemented\r\nConnection: close\r\n\r\n{\"error\":\"No TX handler\"}")
                except Exception as ex:
                    print("TX Web-API Fehler:", ex)
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
                    # Falls devices.json hochgeladen wurde, DeviceManager sofort neu einlesen & MQTT Discovery synchronisieren
                    if filename == "devices.json":
                        try:
                            self.device_manager.load()
                            if self.device_manager.mqtt_client:
                                self.device_manager.publish_all_discovery()
                        except Exception as e:
                            print("Fehler beim Neuladen der Geräte nach Upload:", e)
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
