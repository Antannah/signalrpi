#!/usr/bin/env python3
"""
install.py -- Interaktiver Installer für signalrpi auf dem Raspberry Pi Pico W

Workflow:
1. Prüft / installiert Voraussetzungen (mpremote).
2. Findet den angeschlossenen Raspberry Pi Pico W am USB/COM-Port.
3. Fragt interaktiv nach den WLAN-Zugangsdaten (SSID & Passwort).
4. Erzeugt die initiale Konfigurationsdatei (config.json) auf dem Pico.
5. Überträgt alle Firmware- und Web-Dateien (mit gzip-optimiertem Frontend).
6. Startet den Pico neu und gibt die IP-Adresse des Web-Dashboards aus.
"""

import sys
import os
import time
import json
import subprocess
import glob

def print_banner():
    print("=" * 65)
    print("        📻 signalrpi -- Raspberry Pi Pico W Installer        ")
    print("       Zwei-Kanal 433 / 868 MHz Funk-Gateway fuer Smart Home   ")
    print("=" * 65)
    print()

def ensure_dependencies():
    try:
        import serial.tools.list_ports
    except ImportError:
        print("[INFO] Installiere pyserial...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyserial"])
    
    try:
        subprocess.run([sys.executable, "-m", "mpremote", "version"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except Exception:
        print("[INFO] Installiere mpremote...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "mpremote"])

def find_pico_port():
    import serial.tools.list_ports
    ports = list(serial.tools.list_ports.comports())
    pico_ports = []
    
    for p in ports:
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        # Raspberry Pi Pico Vendor-ID: 2E8A
        if "2e8a" in hwid or "pico" in desc or "micropython" in desc:
            pico_ports.append(p.device)
            
    if pico_ports:
        return pico_ports[0]
    elif len(ports) == 1:
        return ports[0].device
    elif len(ports) > 1:
        print("Mehrere serielle Schnittstellen gefunden:")
        for idx, p in enumerate(ports):
            print(f"  [{idx + 1}] {p.device} ({p.description})")
        sel = input("Waehle den Port des Pico W [1]: ").strip()
        idx = int(sel) - 1 if sel.isdigit() else 0
        return ports[idx].device
    return None

def run_mpremote(port, args):
    cmd = [sys.executable, "-m", "mpremote", "connect", port] + args
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode == 0, res.stdout, res.stderr

def main():
    print_banner()
    ensure_dependencies()
    
    # 1. Port suchen
    print("[1/5] Suche angeschlossenen Raspberry Pi Pico W...")
    port = find_pico_port()
    if not port:
        print("FEHLER: Kein Raspberry Pi Pico gefunden!")
        print("Bitte verbinde den Pico W per USB-Kabel und starte install.py erneut.")
        sys.exit(1)
    print(f"      Gefunden an Port: {port}\n")

    # 2. WLAN-Zugangsdaten abfragen
    print("[2/5] WLAN-Konfiguration")
    print("      Damit der Pico W sich mit Deinem Heimnetzwerk verbinden kann:")
    
    # Prüfe ob config_local oder lokale config existiert als Vorgabe
    default_ssid = ""
    if os.path.exists("src/config_local.py"):
        try:
            with open("src/config_local.py", "r") as f:
                for line in f:
                    if "WIFI_SSID" in line and "=" in line:
                        default_ssid = line.split("=")[1].strip().strip('"').strip("'")
        except Exception:
            pass

    if default_ssid:
        ssid = input(f"      WLAN SSID [{default_ssid}]: ").strip() or default_ssid
    else:
        ssid = input("      WLAN SSID: ").strip()
        while not ssid:
            ssid = input("      WLAN SSID (Pflichtfeld): ").strip()

    wifi_pass = input("      WLAN Passwort: ").strip()

    # Initiale config.json aufbauen
    initial_config = {
        "wifi": {
            "ssid": ssid,
            "password": wifi_pass,
            "hostname": "SignalRPI"
        },
        "mqtt": {
            "broker": "",
            "port": 1883,
            "user": None,
            "password": None,
            "client_id": "signalrpi"
        },
        "rf": {
            "mode_868": "FSK"
        }
    }
    
    # Temporäre config.json lokal schreiben
    os.makedirs("build", exist_ok=True)
    temp_config_path = os.path.join("build", "config.json")
    with open(temp_config_path, "w", encoding="utf-8") as f:
        json.dump(initial_config, f, indent=2)
    print("      Konfiguration vorbereitet.\n")

    # 3. Web-Assets aktualisieren (gzip)
    print("[3/5] Web-Dashboard komprimieren (gzip)...")
    if os.path.exists("src/index.html"):
        import gzip
        with open("src/index.html", "rb") as f_in, gzip.GzipFile("src/index.html.gz", "wb", mtime=0) as f_out:
            f_out.write(f_in.read())
        orig_sz = os.path.getsize("src/index.html")
        gz_sz = os.path.getsize("src/index.html.gz")
        print(f"      index.html: {orig_sz//1024} KB -> index.html.gz: {gz_sz//1024} KB (-{int((1 - gz_sz/orig_sz)*100)}%)\n")

    # 4. Dateien übertragen
    print("[4/5] Uebertrage Dateien auf den Raspberry Pi Pico W...")
    
    # Stoppe eventuell laufende Programme
    run_mpremote(port, ["exec", "import machine"])
    
    # Basisdateien
    files_to_copy = [
        ("src/boot.py", ":boot.py"),
        ("src/main.py", ":main.py"),
        ("src/config_loader.py", ":config_loader.py"),
        ("src/cc1101.py", ":cc1101.py"),
        ("src/pio_receiver.py", ":pio_receiver.py"),
        ("src/device_manager.py", ":device_manager.py"),
        ("src/web_server.py", ":web_server.py"),
        ("src/time_sync.py", ":time_sync.py"),
        ("src/ota_updater.py", ":ota_updater.py"),
        ("src/index.html.gz", ":index.html.gz"),
        (temp_config_path, ":config.json"),
    ]
    
    for src, dst in files_to_copy:
        if os.path.exists(src):
            print(f"      -> {os.path.basename(src)}")
            ok, out, err = run_mpremote(port, ["fs", "cp", src, dst])
            if not ok:
                print(f"         Warnung bei {src}: {err.strip()}")

    # Ordner en_decoders
    print("      -> Ordner en_decoders/")
    run_mpremote(port, ["fs", "mkdir", ":en_decoders"])
    for dec_file in glob.glob("src/en_decoders/*.py"):
        base = os.path.basename(dec_file)
        run_mpremote(port, ["fs", "cp", dec_file, f":en_decoders/{base}"])

    # Ordner lib
    print("      -> Ordner lib/")
    run_mpremote(port, ["fs", "mkdir", ":lib"])
    run_mpremote(port, ["fs", "mkdir", ":lib/umqtt"])
    if os.path.exists("src/lib/umqtt/simple.py"):
        run_mpremote(port, ["fs", "cp", "src/lib/umqtt/simple.py", ":lib/umqtt/simple.py"])
    if os.path.exists("src/lib/ssl.mpy"):
        run_mpremote(port, ["fs", "cp", "src/lib/ssl.mpy", ":lib/ssl.mpy"])

    # Veraltete static_html.py oder unkomprimierte index.html aufräumen
    run_mpremote(port, ["fs", "rm", ":static_html.py"])
    run_mpremote(port, ["fs", "rm", ":index.html"])

    print("      Uebertragung erfolgreich abgeschlossen.\n")

    # 5. Neustart & IP-Ermittlung
    print("[5/5] Starte Pico W neu und verbinde mit WLAN...")
    run_mpremote(port, ["reset"])
    
    # Warte bis WLAN verbunden ist (max 15s)
    ip_found = None
    for _ in range(15):
        time.sleep(1)
        ok, out, _ = run_mpremote(port, ["exec", "import network; w=network.WLAN(network.STA_IF); print(w.ifconfig()[0] if w.isconnected() else '')"])
        if ok and out.strip() and out.strip() != "0.0.0.0":
            ip_found = out.strip().splitlines()[-1]
            break

    print()
    print("=" * 65)
    if ip_found:
        print(f"🎉 INSTALLATION ERFOLGREICH!")
        print()
        print(f"👉 Web-Dashboard erreichbar unter:  http://{ip_found}")
        print()
        print("Du kannst jetzt im Web-Dashboard unter 'System' Deine")
        print("MQTT-Broker-Zugangsdaten eintragen und Geraete anlernen.")
    else:
        print("✅ Dateien erfolgreich auf den Pico W übertragen!")
        print("Der Pico W startet nun neu und verbindet sich mit Deinem WLAN.")
        print("Die IP-Adresse findest Du in Deinem Router (Name: 'SignalRPI').")
    print("=" * 65)

if __name__ == "__main__":
    main()
