# main.py -- Hauptprogramm
# Empfängt Pulsfolgen und verteilt diese über MQTT.

import machine
import time
import json
import gc
from machine import Pin, SPI
from cc1101 import CC1101
from pio_receiver import PIOReceiver
from umqtt.simple import MQTTClient
import decoders

# Onboard-LED für Aktivitätsanzeige (Pico W nutzt Pin 'LED' über den CYW43)
try:
    led = Pin("LED", Pin.OUT)
    led.value(0)
except Exception:
    led = None

# Versuche, die lokale Konfiguration zu laden
try:
    import config_local as config
    has_config = True
except ImportError:
    print("Fehler: config_local.py nicht gefunden. Beende.")
    has_config = False

if has_config:
    # 1. SPI-Busse für CC1101-Module initialisieren (2 getrennte Hardware-Controller)
    # SPI1 (Links): GP10 = SCK, GP11 = MOSI, GP12 = MISO
    spi1 = SPI(1, baudrate=5_000_000, polarity=0, phase=0, sck=Pin(10), mosi=Pin(11), miso=Pin(12))
    # SPI0 (Rechts): GP18 = SCK, GP19 = MOSI, GP16 = MISO
    spi0 = SPI(0, baudrate=5_000_000, polarity=0, phase=0, sck=Pin(18), mosi=Pin(19), miso=Pin(16))
    
    # 2. CC1101-Module instanziieren
    # CC1101 #1 für 433 MHz (Links): SPI1, CS = GP13, GDO0 = GP6
    cc_433 = CC1101(spi1, cs_pin=Pin(13), gdo0_pin=Pin(6))
    # CC1101 #2 für 868 MHz (Rechts): SPI0, CS = GP17, GDO0 = GP21
    cc_868 = CC1101(spi0, cs_pin=Pin(17), gdo0_pin=Pin(21))
    
    # Betriebsmodus für 868 MHz konfigurieren (Standard: FSK)
    mode_868 = getattr(config, "MODE_868", "FSK").upper()
    
    print("Initialisiere HF-Empfänger...")
    cc_433.init_ask_ook(433.92)
    
    # 3. PIO-Receiver für die Flankenerkennung instanziieren
    # State Machine 0 für 433 MHz (GDO0 an GP6)
    rx_433 = PIOReceiver(sm_id=0, pin_num=6)
    
    if mode_868 == "FSK":
        print("868 MHz Empfänger im FSK-Paketmodus initialisiert.")
        cc_868.init_fsk_packet(868.30)
        rx_868 = None
    else:
        print("868 MHz Empfänger im OOK-Modus (asynchron) initialisiert.")
        cc_868.init_ask_ook(868.30)
        # State Machine 1 für 868 MHz (GDO0 an GP21)
        rx_868 = PIOReceiver(sm_id=1, pin_num=21)
    
    # 4. WLAN-Verbindung herstellen
    import network
    # Hostname für DHCP / Fritzbox setzen (muss vor active/connect passieren)
    try:
        network.hostname("SignalRPI")
    except Exception:
        pass
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    try:
        wlan.config(hostname="SignalRPI")
    except Exception:
        pass
    if not wlan.isconnected():
        print("Verbinde mit WLAN '{}'...".format(config.WIFI_SSID))
        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        timeout = 25
        while not wlan.isconnected() and timeout > 0:
            time.sleep(0.5)
            timeout -= 1
            
    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print("WLAN erfolgreich verbunden! IP-Adresse:", ip)
        # NTP Zeitsynchronisation
        try:
            import time_sync
            time_sync.sync_time(wlan)
        except Exception as e:
            print("Zeitsynchronisations-Fehler:", e)
    else:
        print("Warnung: WLAN-Verbindung fehlgeschlagen!")

    # 5. MQTT-Verbindung aufbauen
    print("Verbinde mit MQTT-Broker: {}...".format(config.MQTT_BROKER))
    client = None
    if wlan.isconnected():
        try:
            client = MQTTClient(
                config.MQTT_CLIENT_ID,
                config.MQTT_BROKER,
                port=config.MQTT_PORT,
                user=config.MQTT_USER,
                password=config.MQTT_PASSWORD,
                keepalive=60
            )
            # Last Will and Testament für Statusüberwachung
            client.set_last_will("signalrpi/status", '{"state": "offline"}', retain=True, qos=1)
            client.connect()
            client.publish("signalrpi/status", '{"state": "online"}', retain=True, qos=1)
            
            # Callback für Fernsteuerungs-Kommandos (OTA Update)
            def mqtt_callback(topic, msg):
                t_str = topic.decode("utf-8") if isinstance(topic, bytes) else str(topic)
                if t_str == "signalrpi/system/ota_update":
                    print("MQTT OTA Update Befehl empfangen!")
                    import ota_updater
                    ota_updater.update_from_github()
            
            client.set_callback(mqtt_callback)
            client.subscribe("signalrpi/system/ota_update")
            print("MQTT erfolgreich verbunden!")
        except Exception as e:
            print("MQTT-Verbindungsfehler:", e)
    else:
        print("MQTT übersprungen (kein WLAN).")
        
    # 6. Device Manager & Home Assistant Auto-Discovery
    from device_manager import DeviceManager
    device_mgr = DeviceManager(mqtt_client=client)
    if client:
        print("Sende Home Assistant Auto-Discovery für bekannte Geräte...")
        device_mgr.publish_all_discovery()

    # Puffer für Live-Sniffer im Webinterface (max 30 Pakete)
    sniffer_queue = []

    def push_sniffer(band, proto, dev_id, rssi, data=None, channel=None, matched_name=None, raw_data=None):
        if len(sniffer_queue) > 30:
            sniffer_queue.pop(0)
        t = time.localtime()
        time_str = "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])
        sniffer_queue.append({
            "time": time_str,
            "band": band,
            "proto": proto,
            "id": dev_id,
            "channel": channel,
            "rssi": round(rssi, 1),
            "data": data or {},
            "device_name": matched_name,
            "raw": raw_data
        })

    # 7. Asynchroner Webserver starten
    import gc
    gc.collect()
    import uasyncio as asyncio
    from web_server import WebServer
    web_srv = WebServer(device_manager=device_mgr, sniffer_queue=sniffer_queue, wlan=wlan, port=80)

    print("\nsignalrpi ist betriebsbereit!")
    if wlan.isconnected():
        print("-> Web-Dashboard erreichbar unter: http://{}".format(wlan.ifconfig()[0]))
    print("-> Starte asynchrone Tasks (Funkempfang, MQTT, Web)...")

    async def radio_loop():
        gc_counter = 0
        while True:
            # Eventuelle MQTT-Nachrichten abfragen
            if client:
                try:
                    client.check_msg()
                except Exception:
                    pass

            # 433 MHz Paketprüfung
            packet_433 = rx_433.get_packet()
            if packet_433:
                if led:
                    led.value(1)
                rssi = cc_433.get_rssi()
                decoded = decoders.decode_signal(packet_433)
                
                matched_ha_id, matched_name, is_enabled = (None, None, False)
                if decoded:
                    matched_ha_id, matched_name, is_enabled = device_mgr.match_and_get_info(decoded)
                    
                proto_name = decoded["protocol"] if decoded else "RAW_433"
                dev_id_str = str(decoded["device_id"]) if decoded else "-"
                ch = decoded.get("data", {}).get("channel") if decoded else None
                # Bei unbekannten Signalen Rohpulse (max. 120 Flanken) für Web-UI mitsenden
                raw_to_send = packet_433[:120] if not decoded else None
                push_sniffer("433 MHz", proto_name, dev_id_str, rssi, data=decoded.get("data") if decoded else None, channel=ch, matched_name=matched_name, raw_data=raw_to_send)
                
                if client:
                    try:
                        if decoded:
                            # 1. Standard SignalDUINO Message Topic
                            topic = "signalrpi/messages/{}/{}".format(decoded["protocol"], decoded["device_id"])
                            payload = {
                                "protocol": decoded["protocol"],
                                "device_id": decoded["device_id"],
                                "data": decoded["data"],
                                "signal": {"rssi": rssi, "pulses": len(packet_433)}
                            }
                            client.publish(topic, json.dumps(payload))
                            
                            # 2. Falls einem konfigurierten HA-Device zugeordnet & freigegeben -> HA State Topic
                            if matched_ha_id and is_enabled:
                                ha_topic = "signalrpi/devices/{}/state".format(matched_ha_id)
                                client.publish(ha_topic, json.dumps(decoded["data"]))
                        else:
                            client.publish("signalrpi/raw/433", json.dumps({
                                "rssi": rssi,
                                "pulses": packet_433
                            }))
                    except Exception as ex:
                        # Bei Verbindungsabbruch (ECONNRESET) einmal versuchen neu zu verbinden
                        try:
                            client.connect()
                        except Exception:
                            pass
                        
            # 868 MHz Paketprüfung
            if mode_868 == "FSK":
                packet_868 = cc_868.read_fsk_packet()
                if packet_868:
                    if led:
                        led.value(1)
                    payload = packet_868[:14]
                    rssi_val = packet_868[14]
                    rssi = (rssi_val - 256) / 2.0 - 74.0 if rssi_val >= 128 else (rssi_val / 2.0) - 74.0
                    decoded = decoders.decode_fsk_packet(payload)
                    
                    proto_name = decoded["protocol"] if decoded else "RAW_868_FSK"
                    dev_id_str = str(decoded["device_id"]) if decoded else payload[:4].hex().upper()
                    raw_fsk = payload.hex().upper() if not decoded else None
                    push_sniffer("868 MHz", proto_name, dev_id_str, rssi, data=decoded.get("data") if decoded else None, raw_data=raw_fsk)
                    
                    if client:
                        try:
                            if decoded:
                                topic = "signalrpi/messages/{}/{}".format(decoded["protocol"], decoded["device_id"])
                                payload_data = {
                                    "protocol": decoded["protocol"],
                                    "device_id": decoded["device_id"],
                                    "data": decoded["data"],
                                    "signal": {"rssi": rssi, "raw_len": len(payload)}
                                }
                                client.publish(topic, json.dumps(payload_data))
                                
                                matched_ha_id = device_mgr.match_and_get_id(decoded)
                                if matched_ha_id:
                                    ha_topic = "signalrpi/devices/{}/state".format(matched_ha_id)
                                    client.publish(ha_topic, json.dumps(decoded["data"]))
                            else:
                                client.publish("signalrpi/raw/868", json.dumps({
                                    "rssi": rssi,
                                    "raw": payload.hex().upper()
                                }))
                        except Exception as ex:
                            print("MQTT-Sende-Fehler 868 FSK:", ex)
            else:
                packet_868 = rx_868.get_packet()
                if packet_868:
                    if led:
                        led.value(1)
                    rssi = cc_868.get_rssi()
                    decoded = decoders.decode_signal(packet_868)
                    proto_name = decoded["protocol"] if decoded else "RAW_868_OOK"
                    dev_id_str = str(decoded["device_id"]) if decoded else "-"
                    raw_ook = packet_868[:120] if not decoded else None
                    push_sniffer("868 MHz", proto_name, dev_id_str, rssi, data=decoded.get("data") if decoded else None, raw_data=raw_ook)
                    if client and decoded:
                        topic = "signalrpi/messages/{}/{}".format(decoded["protocol"], decoded["device_id"])
                        client.publish(topic, json.dumps(decoded))
                        
            # Kleiner Yield für Kooperatives Multitasking & periodische GC gegen Fragmentierung
            await asyncio.sleep_ms(1)
            if led and led.value():
                led.value(0)
            if gc_counter % 200 == 0:
                gc.collect()
            gc_counter += 1

    async def main_async():
        await web_srv.start()
        await radio_loop()

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nProgramm durch Benutzer beendet.")
        # Kurze Pause zur Vermeidung von CPU-Volllast und zum Einlassen von Interrupts
        time.sleep_us(200)
