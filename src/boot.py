# boot.py -- läuft beim Systemstart
# Initialisiert die WLAN-Verbindung auf dem Pico W.

import network
import time
import machine

print("Booting signalrpi...")

# Versuche, die lokale Konfiguration zu laden
try:
    import config_local as config
    has_config = True
except ImportError:
    print("Warnung: config_local.py nicht gefunden. WLAN-Verbindung übersprungen.")
    has_config = False

def do_connect():
    if not has_config:
        return False
        
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    if wlan.isconnected():
        print("WLAN bereits verbunden. IP-Adresse:", wlan.ifconfig()[0])
        return True
        
    print("Verbinde mit WLAN-Netzwerk: {}...".format(config.WIFI_SSID))
    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
    
    # Warte auf Verbindung (maximal 15 Sekunden)
    max_wait = 15
    while max_wait > 0:
        status = wlan.status()
        # 3 entspricht network.STAT_GOT_IP
        if status == 3 or wlan.isconnected():
            break
        max_wait -= 1
        print("Warte auf IP-Adresse... ({}s)".format(max_wait))
        time.sleep(1)
        
    if wlan.isconnected():
        ip_info = wlan.ifconfig()
        print("WLAN erfolgreich verbunden!")
        print("IP-Adresse: {}, Subnetzmaske: {}, Gateway: {}".format(ip_info[0], ip_info[1], ip_info[2]))
        return True
    else:
        print("Fehler: WLAN-Verbindung konnte nicht hergestellt werden. Status-Code:", wlan.status())
        return False

# Ausführen der Verbindung beim Booten
wlan_connected = do_connect()
