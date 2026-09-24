# main.py -- Hauptprogramm
# Empfängt Pulsfolgen und verteilt diese über MQTT.

import machine
import time
import json
import gc
from machine import Pin, SPI

# RT6150-Schaltregler des Pico in den PWM-Modus (CCM) zwingen.
# Im Standard-PSM (PFM) schwingt die Schaltfrequenz lastabhängig und erzeugt
# auf der 3V3-Schiene einen Ripple von 50–150 mV, der den CC1101 LNA/VCO stört.
# Mit GPIO23 = HIGH: feste Taktung → Ripple < 10 mV.
_smps_mode = machine.Pin(23, machine.Pin.OUT)
_smps_mode.value(1)
from cc1101 import CC1101
from pio_receiver import PIOReceiver
from umqtt.simple import MQTTClient
import en_decoders as decoders

# Onboard-LED für Aktivitätsanzeige (Pico W nutzt Pin 'LED' über den CYW43)
try:
    led = Pin("LED", Pin.OUT)
    led.value(0)
except Exception:
    led = None

# Versuche, die Konfiguration aus config_loader (config.json) oder config_local zu laden
try:
    from config_loader import config
    has_config = True
except Exception:
    try:
        import config_local as config
        has_config = True
    except ImportError:
        print("Fehler: Weder config.json noch config_local.py gefunden.")
        has_config = False

if has_config:
    # 1. SPI-Busse für CC1101-Module initialisieren (2 getrennte Hardware-Controller)
    # SPI1 (Links): GP10 = SCK, GP11 = MOSI, GP12 = MISO
    # SPI-Takt auf 1 MHz reduziert: reicht für CC1101-Register/FIFO vollständig aus.
    # 5 MHz erzeugte Oberwellen bei 10/15/20 MHz, die direkt in den 10,7-MHz-ZF-Pfad des CC1101 einstrahlten.
    spi1 = SPI(1, baudrate=1_000_000, polarity=0, phase=0, sck=Pin(10), mosi=Pin(11), miso=Pin(12))
    # SPI0 (Rechts): GP18 = SCK, GP19 = MOSI, GP16 = MISO
    spi0 = SPI(0, baudrate=1_000_000, polarity=0, phase=0, sck=Pin(18), mosi=Pin(19), miso=Pin(16))
    
    # 2. CC1101-Module instanziieren
    # CC1101 #1 für 433 MHz (Links): SPI1, CS = GP13, GDO0 = GP6
    cc_433 = CC1101(spi1, cs_pin=Pin(13), gdo0_pin=Pin(6))
    # CC1101 #2 für 868 MHz (Rechts): SPI0, CS = GP17, GDO0 = GP21
    cc_868 = CC1101(spi0, cs_pin=Pin(17), gdo0_pin=Pin(21))
    
    # Betriebsmodus für 868 MHz konfigurieren (Standard: FSK)
    mode_868 = getattr(config, "MODE_868", "FSK").upper()
    
    # Globaler Alert-Puffer für System-Ereignisse (max. 20)
    system_alerts = []

    def push_alert(level: str, msg: str):
        t = time.localtime()
        time_str = "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])
        if len(system_alerts) > 20:
            system_alerts.pop(0)
        entry = {"time": time_str, "level": level, "msg": msg}
        system_alerts.append(entry)
        print(f"[{level.upper()}] {msg}")

    print("Initialisiere HF-Empfänger...")
    cc_433.init_ask_ook(433.92)
    
    # 3. PIO-Receiver für die Flankenerkennung instanziieren
    # State Machine 0 für 433 MHz (GDO0 an GP6)
    rx_433 = PIOReceiver(sm_id=0, pin_num=6)
    
    if mode_868 == "FSK":
        print("868 MHz Empfänger im FSK-Paketmodus (868.30 MHz) initialisiert.")
        cc_868.init_fsk_packet(868.30)
        rx_868 = None
    else:
        print("868 MHz Empfänger im OOK-Modus (asynchron) initialisiert.")
        cc_868.init_ask_ook(868.30)
        # State Machine 1 für 868 MHz (GDO0 an GP21)
        rx_868 = PIOReceiver(sm_id=1, pin_num=21)

    # Hardware-Selbsttest beider CC1101-Module
    hw_433 = cc_433.check_hardware()
    hw_868 = cc_868.check_hardware()
    
    if hw_433["ok"]:
        push_alert("info", f"CC1101 433 MHz bereit: {hw_433['msg']}")
    else:
        push_alert("error", f"CC1101 433 MHz FEHLER: {hw_433['msg']}")
        
    if hw_868["ok"]:
        push_alert("info", f"CC1101 868 MHz bereit: {hw_868['msg']}")
    else:
        push_alert("error", f"CC1101 868 MHz FEHLER: {hw_868['msg']}")
    
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

    # 5. Device Manager vorbereiten
    from device_manager import DeviceManager
    device_mgr = DeviceManager()

    # 6. Sende-Handler für 433 MHz (Intertechno V1 & V3)
    from en_decoders.it_encoder import ITEncoder

    def handle_tx(cmd_data: dict) -> bool:
        """
        Führt einen Sende-Befehl über das 433 MHz CC1101-Modul aus.
        Unterstützt Intertechno V1 und V3 mit konfigurierbaren Wiederholungen (repetitions).
        """
        try:
            proto = cmd_data.get("protocol", "IT_V3").upper()
            action = cmd_data.get("action", "on").lower()
            state = (action in ["on", "learn", "true", "1"])
            reps = int(cmd_data.get("repetitions", 6))
            
            pulses = None
            if proto == "IT_V3":
                bin_code = cmd_data.get("binary_code", "00011100110111100110100111")
                channel = int(cmd_data.get("channel", 1))
                pulses = ITEncoder.encode_it_v3(bin_code, channel, state, group=False)
            elif proto in ["IT", "IT_V1"]:
                fam = cmd_data.get("family", "A")
                group = int(cmd_data.get("group", 1))
                dev = int(cmd_data.get("device", 1))
                pulses = ITEncoder.encode_it_v1(fam, group, dev, state)
                
            if pulses:
                # Vorübergehend State Machine von RX pausieren während TX
                rx_433.sm.active(0)
                try:
                    cc_433.transmit_ook_pulses(cc_433.gdo0_pin, pulses, repetitions=reps)
                finally:
                    # RX-FIFO leeren, um eigene TX-Signale zu verwerfen
                    while rx_433.sm.rx_fifo() > 0:
                        rx_433.sm.get()
                    rx_433.pulse_buffer.clear()
                    rx_433.expect_high = True
                    rx_433.sm.active(1)
                print("TX 433 MHz:", proto, action.upper(), "Reps:", reps)
                return True
        except Exception as ex:
            print("Fehler beim 433 MHz Senden:", ex)
        return False

    # 7. MQTT-Client Manager mit robuster Resubscription und Auto-Reconnect
    client = None
    last_mqtt_reconnect = 0
    last_mqtt_ping = time.time()

    def mqtt_callback(topic, msg):
        try:
            t_str = topic.decode("utf-8") if isinstance(topic, bytes) else str(topic)
            m_str = msg.decode("utf-8").strip() if isinstance(msg, bytes) else str(msg).strip()
            print("[MQTT IN] Topic:", t_str, "Payload:", m_str)
            
            if t_str == "signalrpi/system/ota_update":
                branch = m_str if m_str and not m_str.startswith("{") else "main"
                if m_str.startswith("{"):
                    try:
                        b_data = json.loads(m_str)
                        branch = b_data.get("branch", "main")
                    except Exception:
                        pass
                print("MQTT OTA Update Befehl empfangen für Branch:", branch)
                import ota_updater
                ota_updater.update_from_github(branch=branch)
                
            elif t_str.startswith("signalrpi/devices/") and t_str.endswith("/set"):
                # Format: signalrpi/devices/<ha_id>/set
                parts = t_str.split("/")
                ha_id = parts[2]
                dev = device_mgr.get_device(ha_id)
                d_type = dev.get("profile") or dev.get("type") if dev else None
                if dev and d_type in ["switch", "light"]:
                    reps = dev.get("repetitions", 6)
                    proto = dev.get("protocol", "IT_V3")
                    state_val = m_str.upper()
                    tx_cmd = {
                        "protocol": proto,
                        "action": "on" if state_val in ["ON", "TRUE", "1"] else "off",
                        "repetitions": reps
                    }
                    if proto == "IT_V3":
                        tx_cmd["binary_code"] = dev.get("binary_code")
                        tx_cmd["channel"] = dev.get("channel", 1)
                    elif proto in ["IT", "IT_V1"]:
                        it_c = dev.get("it_code", {})
                        tx_cmd["family"] = it_c.get("family", "A")
                        tx_cmd["group"] = it_c.get("group", 1)
                        tx_cmd["device"] = it_c.get("device", 1)
                        
                    print("MQTT Befehl für {}: {} ({})".format(ha_id, tx_cmd["action"], proto))
                    if handle_tx(tx_cmd):
                        # Schalter-/Licht-Status an Home Assistant zurückmelden
                        if client:
                            client.publish("signalrpi/devices/{}/state".format(ha_id), state_val, retain=True)
                        device_mgr.set_latest(ha_id, {"state": state_val})
                        
            elif t_str.startswith("signalrpi/devices/") and t_str.endswith("/repetitions/set"):
                # Format: signalrpi/devices/<ha_id>/repetitions/set
                parts = t_str.split("/")
                ha_id = parts[2]
                try:
                    new_rep = int(m_str)
                    device_mgr.set_repetitions(ha_id, new_rep)
                    print("MQTT Repetitions für", ha_id, "auf", new_rep, "gesetzt")
                except Exception as e:
                    print("Fehler beim Setzen der Repetitions:", e)
        except Exception as ex:
            print("MQTT Callback Fehler:", ex)

    def ensure_mqtt_subscribed():
        global client, last_mqtt_reconnect, last_mqtt_ping
        if not wlan.isconnected():
            return False
            
        now = time.time()
        # Mindestens 5 Sekunden zwischen Reconnect-Versuchen warten
        if client is not None and (now - last_mqtt_reconnect) < 5:
            return False

        last_mqtt_reconnect = now
        try:
            if client is None:
                client = MQTTClient(
                    config.MQTT_CLIENT_ID,
                    config.MQTT_BROKER,
                    port=config.MQTT_PORT,
                    user=config.MQTT_USER,
                    password=config.MQTT_PASSWORD,
                    keepalive=60
                )
                client.set_last_will("signalrpi/status", '{"state": "offline"}', retain=True, qos=1)
                client.set_callback(mqtt_callback)
            
            # Neu verbinden
            try:
                client.disconnect()
            except Exception:
                pass
            client.connect()
            
            # Subscriptions nach jedem Reconnect neu registrieren
            client.subscribe("signalrpi/system/ota_update")
            client.subscribe("signalrpi/devices/+/set")
            client.subscribe("signalrpi/devices/+/repetitions/set")
            
            # Status online melden
            client.publish("signalrpi/status", '{"state": "online"}', retain=True, qos=1)
            client.publish("signalrpi/status/hardware", json.dumps({"cc_433": hw_433, "cc_868": hw_868}), retain=True)
            
            # Device Manager mit Client verknüpfen
            device_mgr.mqtt_client = client
            print("MQTT erfolgreich verbunden und Subscriptions registriert!")
            last_mqtt_ping = time.time()
            return True
        except Exception as e:
            print("MQTT Verbindungs-/Subscription-Fehler:", e)
            client = None
            device_mgr.mqtt_client = None
            return False

    # Initiale MQTT-Verbindung
    print("Verbinde mit MQTT-Broker: {}...".format(config.MQTT_BROKER))
    ensure_mqtt_subscribed()

    # Puffer für Live-Sniffer im Webinterface (max 30 Pakete)
    sniffer_queue = []

    def push_sniffer(band, proto, dev_id, rssi, data=None, channel=None, matched_name=None, raw_data=None, ms_pattern=None):
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
            "raw": raw_data,
            "ms": ms_pattern
        })

    # 8. Asynchroner Webserver starten
    import gc
    gc.collect()
    import uasyncio as asyncio
    from web_server import WebServer
    web_srv = WebServer(device_manager=device_mgr, sniffer_queue=sniffer_queue, wlan=wlan, port=80, tx_handler=handle_tx)
    web_srv.cc_433 = cc_433
    web_srv.cc_868 = cc_868
    web_srv.alerts = system_alerts
    web_srv.push_alert = push_alert

    print("\nsignalrpi ist betriebsbereit!")
    if wlan.isconnected():
        print("-> Web-Dashboard erreichbar unter: http://{}".format(wlan.ifconfig()[0]))
    print("-> Starte asynchrone Tasks (Funkempfang, MQTT, Web)...")

    async def radio_loop():
        global client, last_mqtt_ping
        gc_counter = 0
        while True:
            # Während eines OTA-Updates Funk- und MQTT-Aktivität pausieren (schützt vor TLS ENOMEM)
            import ota_updater
            if ota_updater.is_updating:
                del sniffer_queue[:]
                gc.collect()
                await asyncio.sleep_ms(500)
                continue

            # 1. WLAN Überwachung & Auto-Reconnect
            if not wlan.isconnected():
                try:
                    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
                except Exception:
                    pass

            # 2. MQTT Verbindung sicherstellen
            if client is None and wlan.isconnected():
                ensure_mqtt_subscribed()

            # 3. Eventuelle MQTT-Nachrichten abfragen & Keepalive-Ping
            if client:
                try:
                    client.check_msg()
                    # Regelmäßiger MQTT-Ping alle 20 Sekunden
                    now = time.time()
                    if (now - last_mqtt_ping) > 20:
                        client.ping()
                        last_mqtt_ping = now
                except Exception as ex:
                    print("[MQTT] Verbindungsfehler bei check_msg / ping:", ex)
                    client = None
                    device_mgr.mqtt_client = None
                    # Sofortiger Reconnect-Versuch inklusive Subscriptions
                    ensure_mqtt_subscribed()

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
                ms_str = decoded.get("ms_string") if decoded else None
                if not ms_str:
                    try:
                        pat = decoders.PatternDecoder.decode_pattern(packet_433)
                        if pat:
                            ms_str = pat.to_ms_string()
                    except Exception:
                        pass

                # Debug: 433 MHz Pakete auf der seriellen Konsole ausgeben
                print("[433 OOK] proto={} id={} ch={} rssi={:.1f}dBm decoded={} ms={}".format(
                    proto_name, dev_id_str, ch, rssi, decoded is not None, ms_str or "-"))
                # Rohpulse (max. 120 Flanken) für Web-UI mitsenden (auch bei erkannten Paketen)
                raw_to_send = packet_433[:120]
                push_sniffer("433 MHz", proto_name, dev_id_str, rssi, data=decoded.get("data") if decoded else None, channel=ch, matched_name=matched_name, raw_data=raw_to_send, ms_pattern=ms_str)
                
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
                                dev_obj = device_mgr.get_device(matched_ha_id)
                                if dev_obj and dev_obj.get("type") in ["switch", "light"]:
                                    # HA Switch/Light erwartet "ON" oder "OFF" als Rohstring
                                    state_str = str(decoded["data"].get("state", "OFF")).upper()
                                    client.publish(ha_topic, state_str, retain=True)
                                else:
                                    # Sensoren erhalten vollständiges JSON mit allen Entitäten + CC1101-RSSI
                                    state_data = dict(decoded["data"])
                                    state_data["rssi"] = round(rssi, 1)
                                    client.publish(ha_topic, json.dumps(state_data))
                        else:
                            ms_str = None
                            try:
                                pat = decoders.PatternDecoder.decode_pattern(packet_433)
                                if pat:
                                    ms_str = pat.to_ms_string()
                            except Exception:
                                pass
                            raw_payload = {
                                "rssi": rssi,
                                "pulses": packet_433
                            }
                            if ms_str:
                                raw_payload["ms"] = ms_str
                            client.publish("signalrpi/raw/433", json.dumps(raw_payload))
                    except Exception as ex:
                        print("[MQTT] Sende-Fehler 433 MHz:", ex)
                        client = None
                        device_mgr.mqtt_client = None
                        ensure_mqtt_subscribed()
                        
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
                    
                    # Debug: Rohbytes immer ausgeben, damit Decoder-Probleme sichtbar werden
                    print("[868 FSK] raw={} rssi={:.1f}dBm decoded={}".format(
                        payload.hex().upper(), rssi, decoded["protocol"] if decoded else "NONE"))
                    
                    proto_name = decoded["protocol"] if decoded else "RAW_868_FSK"
                    dev_id_str = str(decoded["device_id"]) if decoded else payload[:4].hex().upper()
                    raw_fsk = payload.hex().upper()
                    # Rausch-Pakete (decoded == None und RSSI < -88 dBm) nicht in die Web-Sniffer-Queue schieben
                    if decoded or rssi > -88.0:
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
                                    state_data = dict(decoded["data"])
                                    state_data["rssi"] = round(rssi, 1)
                                    client.publish(ha_topic, json.dumps(state_data))
                                    device_mgr.set_latest(matched_ha_id, state_data)
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
                    raw_ook = packet_868[:120]
                    push_sniffer("868 MHz", proto_name, dev_id_str, rssi, data=decoded.get("data") if decoded else None, raw_data=raw_ook)
                    if client and decoded:
                        topic = "signalrpi/messages/{}/{}".format(decoded["protocol"], decoded["device_id"])
                        client.publish(topic, json.dumps(decoded))
                        matched_ha_id = device_mgr.match_and_get_id(decoded)
                        if matched_ha_id:
                            ha_topic = "signalrpi/devices/{}/state".format(matched_ha_id)
                            state_data = dict(decoded.get("data", {}))
                            state_data["rssi"] = round(rssi, 1)
                            client.publish(ha_topic, json.dumps(state_data))
                            device_mgr.set_latest(matched_ha_id, state_data)
                        
            # Kleiner Yield für Kooperatives Multitasking & periodische GC gegen Fragmentierung
            await asyncio.sleep_ms(1)
            if led and led.value():
                led.value(0)
            if gc_counter % 200 == 0:
                gc.collect()
            gc_counter += 1

    async def deferred_discovery():
        # Warte 5 Sekunden, bis Funkempfang und Webserver stabil laufen
        await asyncio.sleep(5)
        print("Sende Home Assistant MQTT Discovery im Hintergrund...")
        for dev in device_mgr.devices:
            if dev.get("enabled", True):
                try:
                    device_mgr.publish_discovery(dev)
                except Exception as ex:
                    print("Discovery Fehler bei {}: {}".format(dev.get("id"), ex))
                await asyncio.sleep_ms(150)
        print("Home Assistant MQTT Discovery abgeschlossen.")

    async def main_async():
        await web_srv.start()
        asyncio.create_task(deferred_discovery())
        await radio_loop()

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nProgramm durch Benutzer beendet.")
        # Kurze Pause zur Vermeidung von CPU-Volllast und zum Einlassen von Interrupts
        time.sleep_us(200)
