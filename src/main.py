# main.py -- Hauptprogramm
# Empfängt Pulsfolgen und verteilt diese über MQTT.

import machine
import time
import json
from machine import Pin, SPI
from cc1101 import CC1101
from pio_receiver import PIOReceiver
from umqtt.simple import MQTTClient
import decoders

# Versuche, die lokale Konfiguration zu laden
try:
    import config_local as config
    has_config = True
except ImportError:
    print("Fehler: config_local.py nicht gefunden. Beende.")
    has_config = False

if has_config:
    # 1. SPI-Bus für CC1101-Module initialisieren
    # GP18 = SCK, GP19 = MOSI, GP16 = MISO
    spi = SPI(0, baudrate=5_000_000, polarity=0, phase=0, sck=Pin(18), mosi=Pin(19), miso=Pin(16))
    
    # 2. CC1101-Module instanziieren
    # CC1101 #1 für 433 MHz: CS = GP17, GDO0 = GP20
    cc_433 = CC1101(spi, cs_pin=Pin(17), gdo0_pin=Pin(20))
    # CC1101 #2 für 868 MHz: CS = GP22, GDO0 = GP21
    cc_868 = CC1101(spi, cs_pin=Pin(22), gdo0_pin=Pin(21))
    
    print("Initialisiere HF-Empfänger...")
    cc_433.init_ask_ook(433.92)
    cc_868.init_ask_ook(868.30)
    
    # 3. PIO-Receiver für die Flankenerkennung instanziieren
    # State Machine 0 für 433 MHz (GDO0 an GP20)
    rx_433 = PIOReceiver(sm_id=0, pin_num=20)
    # State Machine 1 für 868 MHz (GDO0 an GP21)
    rx_868 = PIOReceiver(sm_id=1, pin_num=21)
    
    # 4. MQTT-Verbindung aufbauen
    print("Verbinde mit MQTT-Broker: {}...".format(config.MQTT_BROKER))
    client = None
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
        print("MQTT erfolgreich verbunden!")
    except Exception as e:
        print("MQTT-Verbindungsfehler:", e)
        # Das Programm läuft trotzdem weiter und gibt Rohwerte im Serial Terminal aus
        
    print("\nsignalrpi ist betriebsbereit und scannt den Äther...")
    
    # Hauptschleife
    while True:
        # 433 MHz Paketprüfung
        packet_433 = rx_433.get_packet()
        if packet_433:
            rssi = cc_433.get_rssi()
            print("[433 MHz] Signal empfangen (RSSI: {:.1f} dBm, Pulses: {}): {}".format(
                rssi, len(packet_433), packet_433
            ))
            
            # Dekodierungsversuch
            decoded = decoders.decode_signal(packet_433)
            
            # Publizieren
            if client:
                try:
                    if decoded:
                        topic = "signalrpi/messages/{}/{}".format(decoded["protocol"], decoded["device_id"])
                        payload = {
                            "protocol": decoded["protocol"],
                            "device_id": decoded["device_id"],
                            "data": decoded["data"],
                            "signal": {"rssi": rssi, "pulses": len(packet_433)}
                        }
                        client.publish(topic, json.dumps(payload))
                    else:
                        # Raw-Ausgabe für unbekannte Signale
                        client.publish("signalrpi/raw/433", json.dumps({
                            "rssi": rssi,
                            "pulses": packet_433
                        }))
                except Exception as ex:
                    print("Fehler beim MQTT-Senden (433 MHz):", ex)
                    
        # 868 MHz Paketprüfung
        packet_868 = rx_868.get_packet()
        if packet_868:
            rssi = cc_868.get_rssi()
            print("[868 MHz] Signal empfangen (RSSI: {:.1f} dBm, Pulses: {}): {}".format(
                rssi, len(packet_868), packet_868
            ))
            
            # Dekodierungsversuch
            decoded = decoders.decode_signal(packet_868)
            
            # Publizieren
            if client:
                try:
                    if decoded:
                        topic = "signalrpi/messages/{}/{}".format(decoded["protocol"], decoded["device_id"])
                        payload = {
                            "protocol": decoded["protocol"],
                            "device_id": decoded["device_id"],
                            "data": decoded["data"],
                            "signal": {"rssi": rssi, "pulses": len(packet_868)}
                        }
                        client.publish(topic, json.dumps(payload))
                    else:
                        # Raw-Ausgabe für unbekannte Signale
                        client.publish("signalrpi/raw/868", json.dumps({
                            "rssi": rssi,
                            "pulses": packet_868
                        }))
                except Exception as ex:
                    print("Fehler beim MQTT-Senden (868 MHz):", ex)
                    
        # Kurze Pause zur Vermeidung von CPU-Volllast und zum Einlassen von Interrupts
        time.sleep_us(200)
