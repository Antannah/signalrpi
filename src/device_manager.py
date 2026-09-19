# device_manager.py -- Verwaltung von Geräten und HA MQTT Auto-Discovery
import json

DEVICES_FILE = "devices.json"

class DeviceManager:
    def __init__(self, mqtt_client=None):
        self.mqtt_client = mqtt_client
        self.devices = []
        self.load()

    def load(self):
        try:
            with open(DEVICES_FILE, "r") as f:
                self.devices = json.load(f)
        except Exception:
            self.devices = []
        return self.devices

    def save(self):
        try:
            with open(DEVICES_FILE, "w") as f:
                json.dump(self.devices, f)
            return True
        except Exception as e:
            print("Fehler beim Speichern von devices.json:", e)
            return False

    def get_all(self):
        return self.devices

    def add_or_update(self, dev):
        # Prüfung, ob ID bereits existiert
        dev_id = dev.get("id")
        if not dev_id:
            return False
        
        found = False
        for i, existing in enumerate(self.devices):
            if existing.get("id") == dev_id:
                self.devices[i] = dev
                found = True
                break
        if not found:
            self.devices.append(dev)
            
        self.save()
        if self.mqtt_client:
            self.publish_discovery(dev)
        return True

    def reassign_sensor(self, ha_id, new_dev_id, new_channel=None):
        """
        Ordnet eine neue Funk-ID (nach Batteriewechsel) einem bestehenden Sensor zu.
        Die Home Assistant Entity-ID bleibt unverändert!
        """
        for dev in self.devices:
            if dev.get("id") == ha_id:
                dev["device_id"] = new_dev_id
                if new_channel is not None:
                    dev["channel"] = new_channel
                self.save()
                return True
        return False

    def delete(self, dev_id):
        new_list = [d for d in self.devices if d.get("id") != dev_id]
        if len(new_list) != len(self.devices):
            self.devices = new_list
            self.save()
            if self.mqtt_client:
                self.remove_discovery(dev_id)
            return True
        return False

    def publish_all_discovery(self):
        if not self.mqtt_client:
            return
        for dev in self.devices:
            self.publish_discovery(dev)

    def publish_discovery(self, dev):
        if not self.mqtt_client:
            return
            
        dev_id = dev["id"]
        dev_name = dev.get("name", dev_id)
        dev_type = dev.get("type", "sensor")
        
        device_info = {
            "identifiers": ["signalrpi_" + dev_id],
            "name": dev_name,
            "model": dev.get("protocol", "RF Device"),
            "manufacturer": "signalrpi",
            "via_device": "signalrpi_gateway"
        }
        
        if dev_type == "sensor":
            entities = dev.get("entities", [])
            for ent in entities:
                key = ent["key"]
                lbl = ent.get("name") or key
                disc_topic = "homeassistant/sensor/signalrpi_{}_{}/config".format(dev_id, key)
                payload = {
                    "name": "{} {}".format(dev_name, lbl),
                    "state_topic": "signalrpi/devices/{}/state".format(dev_id),
                    "value_template": "{{{{ value_json.{} }}}}".format(key),
                    "unique_id": "signalrpi_{}_{}".format(dev_id, key),
                    "device": device_info
                }
                if "unit" in ent:
                    payload["unit_of_measurement"] = ent["unit"]
                if "device_class" in ent:
                    payload["device_class"] = ent["device_class"]
                if "icon" in ent:
                    payload["icon"] = ent["icon"]
                    
                try:
                    self.mqtt_client.publish(disc_topic, json.dumps(payload), retain=True)
                except Exception as e:
                    print("HA Discovery Fehler:", e)
                    
        elif dev_type == "switch":
            disc_topic = "homeassistant/switch/signalrpi_{}/config".format(dev_id)
            payload = {
                "name": dev_name,
                "command_topic": "signalrpi/devices/{}/set".format(dev_id),
                "state_topic": "signalrpi/devices/{}/state".format(dev_id),
                "unique_id": "signalrpi_{}".format(dev_id),
                "device": device_info
            }
            if "icon" in dev:
                payload["icon"] = dev["icon"]
            try:
                self.mqtt_client.publish(disc_topic, json.dumps(payload), retain=True)
            except Exception as e:
                print("HA Discovery Fehler:", e)

    def remove_discovery(self, dev_id):
        if not self.mqtt_client:
            return
        # Leere Payload löscht die Entität in Home Assistant
        disc_topic = "homeassistant/sensor/signalrpi_{}/config".format(dev_id)
        try:
            self.mqtt_client.publish(disc_topic, "", retain=True)
        except Exception:
            pass

    def get_all(self):
        # Gib Geräte angereichert mit den letzten Messwerten zurück
        res = []
        for dev in self.devices:
            d_copy = dict(dev)
            d_copy["latest"] = getattr(self, "latest_values", {}).get(dev["id"], {})
            res.append(d_copy)
        return res

    def set_latest(self, dev_id, data):
        if not hasattr(self, "latest_values"):
            self.latest_values = {}
        self.latest_values[dev_id] = data

    def match_and_get_info(self, decoded_data):
        # Prüft, ob ein empfangenes Funkpaket zu einem konfigurierten Gerät passt
        proto = decoded_data.get("protocol")
        dev_id_val = str(decoded_data.get("device_id"))
        data = decoded_data.get("data", {})
        channel = data.get("channel")
        
        for dev in self.devices:
            if dev.get("protocol") != proto:
                continue
            # Optionaler Filter auf channel
            if "channel" in dev and dev["channel"] is not None and channel is not None:
                if str(dev["channel"]) != str(channel):
                    continue
            # Filter auf device_id
            if "device_id" in dev and dev["device_id"] is not None:
                if str(dev["device_id"]) != dev_id_val:
                    continue
            
            # Treffer: Letzte Werte merken
            self.set_latest(dev["id"], data)
            return dev["id"], dev.get("name", dev["id"])
            
        return None, None

    def match_and_get_id(self, decoded_data):
        dev_id, _ = self.match_and_get_info(decoded_data)
        return dev_id
