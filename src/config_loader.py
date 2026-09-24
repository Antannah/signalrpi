# config_loader.py -- Lädt und speichert die Konfiguration aus config.json
import json

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "wifi": {
        "ssid": "",
        "password": "",
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

class Config:
    def __init__(self):
        self.data = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        # 1. Versuche config.json zu laden
        loaded = False
        try:
            with open(CONFIG_FILE, "r") as f:
                c = json.load(f)
                if isinstance(c, dict):
                    if "wifi" in c:
                        self.data["wifi"].update(c.get("wifi", {}))
                    if "mqtt" in c:
                        self.data["mqtt"].update(c.get("mqtt", {}))
                    if "rf" in c:
                        self.data["rf"].update(c.get("rf", {}))
                    loaded = True
        except Exception:
            pass

        # 2. Fallback auf config_local.py falls config.json noch nicht existiert
        if not loaded:
            try:
                import config_local as cl
                if hasattr(cl, "WIFI_SSID"):
                    self.data["wifi"]["ssid"] = cl.WIFI_SSID
                if hasattr(cl, "WIFI_PASSWORD"):
                    self.data["wifi"]["password"] = cl.WIFI_PASSWORD
                if hasattr(cl, "MQTT_BROKER"):
                    self.data["mqtt"]["broker"] = cl.MQTT_BROKER
                if hasattr(cl, "MQTT_PORT"):
                    self.data["mqtt"]["port"] = cl.MQTT_PORT
                if hasattr(cl, "MQTT_USER"):
                    self.data["mqtt"]["user"] = cl.MQTT_USER
                if hasattr(cl, "MQTT_PASSWORD"):
                    self.data["mqtt"]["password"] = cl.MQTT_PASSWORD
                if hasattr(cl, "MQTT_CLIENT_ID"):
                    self.data["mqtt"]["client_id"] = cl.MQTT_CLIENT_ID
                if hasattr(cl, "MODE_868"):
                    self.data["rf"]["mode_868"] = cl.MODE_868
                self.save()
            except ImportError:
                pass

    def save(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.data, f)
            return True
        except Exception as e:
            print("Fehler beim Speichern der Konfiguration:", e)
            return False

    # Hilfs-Properties für nahtlose Abwärtskompatibilität
    @property
    def WIFI_SSID(self):
        return self.data["wifi"].get("ssid", "")

    @property
    def WIFI_PASSWORD(self):
        return self.data["wifi"].get("password", "")

    @property
    def MQTT_BROKER(self):
        return self.data["mqtt"].get("broker", "")

    @property
    def MQTT_PORT(self):
        return self.data["mqtt"].get("port", 1883)

    @property
    def MQTT_USER(self):
        return self.data["mqtt"].get("user")

    @property
    def MQTT_PASSWORD(self):
        return self.data["mqtt"].get("password")

    @property
    def MQTT_CLIENT_ID(self):
        return self.data["mqtt"].get("client_id", "signalrpi")

    @property
    def MODE_868(self):
        return self.data["rf"].get("mode_868", "FSK")

config = Config()
