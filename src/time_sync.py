# time_sync.py -- Universelle NTP-Zeitsynchronisation fuer signalrpi
import ntptime
import time
import machine
import json

TIME_CONFIG_FILE = "time_config.json"

DEFAULT_CONFIG = {
    "tz_offset": 1,        # UTC+1 (MEZ / Berlin)
    "auto_dst": True,      # Automatische EU-Sommerzeit
    "custom_ntp": ""       # Eigener NTP-Server (leer = Auto: Gateway -> pool.ntp.org)
}

def load_time_config():
    try:
        with open(TIME_CONFIG_FILE, "r") as f:
            cfg = json.load(f)
            # Default-Merge
            res = dict(DEFAULT_CONFIG)
            res.update(cfg)
            return res
    except Exception:
        return dict(DEFAULT_CONFIG)

def save_time_config(cfg):
    try:
        with open(TIME_CONFIG_FILE, "w") as f:
            json.dump(cfg, f)
        return True
    except Exception as e:
        print("Fehler beim Speichern von time_config.json:", e)
        return False

def is_eu_dst(year, month, day, hour):
    """
    Ermittelt, ob für Mitteleuropa (MESZ) Sommerzeit gilt.
    Regel: Beginn letzter Sonntag im März 02:00 UTC, Ende letzter Sonntag im Oktober 03:00 UTC.
    """
    if month < 3 or month > 10:
        return False
    if month > 3 and month < 10:
        return True
    
    # Letzter Sonntag im Monat: 31 minus Wochentag von Tag 31 (0=Mo, 6=So)
    try:
        wday_31 = time.localtime(time.mktime((year, month, 31, 0, 0, 0, 0, 0)))[6]
        last_sunday = 31 - ((wday_31 + 1) % 7)
    except Exception:
        last_sunday = 25 # Fallback

    if month == 3:
        return day > last_sunday or (day == last_sunday and hour >= 2)
    else: # Oktober
        return day < last_sunday or (day == last_sunday and hour < 3)

def sync_time(wlan=None):
    """
    Synchronisiert die RTC per NTP unter Berücksichtigung von Gateway/Fallback,
    Zeitzone und automatischer Sommerzeit.
    """
    cfg = load_time_config()
    custom_ntp = cfg.get("custom_ntp", "").strip()
    tz_base = cfg.get("tz_offset", 1)
    auto_dst = cfg.get("auto_dst", True)

    servers = []
    if custom_ntp:
        servers.append(custom_ntp)
    
    # 1. Standard-Gateway des Routers (z. B. FRITZ!Box 192.168.125.1)
    if wlan and wlan.isconnected():
        try:
            gw = wlan.ifconfig()[2]
            if gw and gw != "0.0.0.0" and gw not in servers:
                servers.append(gw)
        except Exception:
            pass

    # 2. Weltweite Fallbacks
    servers.extend(["pool.ntp.org", "time.google.com"])

    for srv in servers:
        try:
            ntptime.host = srv
            ntptime.settime() # Setzt interne RTC auf UTC
            
            # UTC auslesen
            utc = time.localtime()
            offset_hours = tz_base
            if auto_dst and is_eu_dst(utc[0], utc[1], utc[2], utc[3]):
                offset_hours += 1
            
            # Lokale Zeit berechnen
            local_secs = time.time() + (offset_hours * 3600)
            loc = time.localtime(local_secs)
            
            # RTC auf lokale Zeit umstellen: (year, month, mday, weekday, hour, min, sec, subsec)
            machine.RTC().datetime((loc[0], loc[1], loc[2], loc[6], loc[3], loc[4], loc[5], 0))
            print("Uhrzeit synchronisiert via {}: {:02d}:{:02d}:{:02d} (UTC+{})".format(srv, loc[3], loc[4], loc[5], offset_hours))
            return True, "{:02d}:{:02d}:{:02d}".format(loc[3], loc[4], loc[5]), srv
        except Exception as ex:
            # Server antwortet nicht, nächsten probieren
            continue
            
    print("NTP-Zeitsynchronisation fehlgeschlagen (alle Server unerreichbar).")
    return False, None, None
