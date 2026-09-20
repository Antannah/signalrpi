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

    def get_device(self, ha_id):
        for dev in self.devices:
            if dev.get("id") == ha_id:
                return dev
        return None

    def add_or_update(self, dev):
        # Prüfung, ob ID bereits existiert
        dev_id = dev.get("id")
        if not dev_id:
            return False
        
        # Standardmäßig aktiviert, falls nicht angegeben
        if "enabled" not in dev:
            dev["enabled"] = True
            
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
            if dev.get("enabled", True):
                self.publish_discovery(dev)
            else:
                self.remove_discovery(dev_id)
        return True

    def set_device_profile(self, ha_id, profile_name):
        """
        Ändert das Entitäten-Profil eines Geräts (z.B. thermo_hygro, thermo, contact)
        und aktualisiert ggf. das MQTT Auto-Discovery.
        """
        for dev in self.devices:
            if dev.get("id") == ha_id:
                # Vorherige Entitäten abmelden, falls MQTT aktiv
                if self.mqtt_client and dev.get("enabled", True):
                    self.remove_discovery(ha_id)
                
                dev["profile"] = profile_name
                if profile_name == "switch":
                    dev["type"] = "switch"
                    dev["entities"] = []
                    if "repetitions" not in dev:
                        dev["repetitions"] = 6
                    if dev.get("protocol") == "IT" and "it_code" not in dev:
                        dev_id_parts = str(dev.get("device_id", "A_1_1")).split("_")
                        fam = dev_id_parts[0] if len(dev_id_parts) > 0 else "A"
                        grp = int(dev_id_parts[1]) if len(dev_id_parts) > 1 and dev_id_parts[1].isdigit() else 1
                        device_num = int(dev_id_parts[2]) if len(dev_id_parts) > 2 and dev_id_parts[2].isdigit() else 1
                        dev["it_code"] = {"family": fam, "group": grp, "device": device_num}
                elif profile_name == "button":
                    dev["type"] = "sensor"
                    dev["entities"] = [
                        {"key": "state", "name": "Taste", "icon": "mdi:remote"},
                        {"key": "battery_low", "name": "Batterie", "device_class": "battery"}
                    ]
                elif profile_name == "thermo_hygro":
                    dev["type"] = "sensor"
                    dev["entities"] = [
                        {"key": "temperature", "name": "Temperatur", "unit": "°C", "device_class": "temperature"},
                        {"key": "humidity", "name": "Luftfeuchtigkeit", "unit": "%", "device_class": "humidity"},
                        {"key": "battery_low", "name": "Batterie", "device_class": "battery"}
                    ]
                elif profile_name == "thermo":
                    dev["type"] = "sensor"
                    dev["entities"] = [
                        {"key": "temperature", "name": "Temperatur", "unit": "°C", "device_class": "temperature"},
                        {"key": "battery_low", "name": "Batterie", "device_class": "battery"}
                    ]
                elif profile_name == "contact":
                    dev["type"] = "sensor"
                    dev["entities"] = [
                        {"key": "state", "name": "Zustand", "device_class": "door"},
                        {"key": "battery_low", "name": "Batterie", "device_class": "battery"}
                    ]
                
                self.save()
                if self.mqtt_client and dev.get("enabled", True):
                    self.publish_discovery(dev)
                return True
        return False

    def toggle_enabled(self, ha_id, state=None):
        for dev in self.devices:
            if dev.get("id") == ha_id:
                if state is None:
                    dev["enabled"] = not dev.get("enabled", True)
                else:
                    dev["enabled"] = bool(state)
                self.save()
                if self.mqtt_client:
                    if dev["enabled"]:
                        self.publish_discovery(dev)
                    else:
                        self.remove_discovery(ha_id)
                return True, dev["enabled"]
        return False, False

    def set_repetitions(self, ha_id, repetitions: int):
        for dev in self.devices:
            if dev.get("id") == ha_id:
                dev["repetitions"] = max(1, min(25, int(repetitions)))
                self.save()
                if self.mqtt_client:
                    try:
                        self.mqtt_client.publish(
                            "signalrpi/devices/{}/repetitions/state".format(ha_id),
                            str(dev["repetitions"]),
                            retain=True
                        )
                    except Exception:
                        pass
                return True
        return False

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
        import time
        for dev in self.devices:
            if dev.get("enabled", True):
                self.publish_discovery(dev)
                time.sleep_ms(40)

    def publish_discovery(self, dev):
        if not self.mqtt_client or not dev.get("enabled", True):
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
        
        import time
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
                    time.sleep_ms(25)
                except Exception as e:
                    print("HA Discovery Fehler:", e)
                    try:
                        self.mqtt_client.connect()
                        self.mqtt_client.publish(disc_topic, json.dumps(payload), retain=True)
                    except Exception:
                        pass
                    
        elif dev_type == "switch":
            # 1. Switch Entity
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
                time.sleep_ms(25)
            except Exception as e:
                print("HA Discovery Fehler (Switch):", e)

            # 2. Number Entity für Repetitions (Wiederholungen)
            rep_topic = "homeassistant/number/signalrpi_{}_rep/config".format(dev_id)
            rep_payload = {
                "name": "{} Wiederholungen".format(dev_name),
                "command_topic": "signalrpi/devices/{}/repetitions/set".format(dev_id),
                "state_topic": "signalrpi/devices/{}/repetitions/state".format(dev_id),
                "unique_id": "signalrpi_{}_repetitions".format(dev_id),
                "min": 1,
                "max": 25,
                "step": 1,
                "icon": "mdi:repeat",
                "device": device_info
            }
            try:
                self.mqtt_client.publish(rep_topic, json.dumps(rep_payload), retain=True)
                time.sleep_ms(25)
                # Aktuellen Repetitions-Wert publishen
                curr_rep = dev.get("repetitions", 6)
                self.mqtt_client.publish("signalrpi/devices/{}/repetitions/state".format(dev_id), str(curr_rep), retain=True)
            except Exception as e:
                print("HA Discovery Fehler (Repetitions):", e)

    def remove_discovery(self, dev_id):
        if not self.mqtt_client:
            return
        import time
        # Finde das Gerät um alle seine Entities sauber abzumelden
        target_dev = None
        for d in self.devices:
            if d.get("id") == dev_id:
                target_dev = d
                break
                
        if target_dev and target_dev.get("type") == "sensor":
            for ent in target_dev.get("entities", []):
                key = ent["key"]
                disc_topic = "homeassistant/sensor/signalrpi_{}_{}/config".format(dev_id, key)
                try:
                    self.mqtt_client.publish(disc_topic, "", retain=True)
                    time.sleep_ms(20)
                except Exception:
                    pass
        else:
            disc_topic = "homeassistant/switch/signalrpi_{}/config".format(dev_id)
            rep_topic = "homeassistant/number/signalrpi_{}_rep/config".format(dev_id)
            try:
                self.mqtt_client.publish(disc_topic, "", retain=True)
                time.sleep_ms(20)
                self.mqtt_client.publish(rep_topic, "", retain=True)
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
        d_val = dict(data)
        try:
            import time
            t = time.localtime()
            d_val["_time"] = "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])
        except Exception:
            pass
        self.latest_values[dev_id] = d_val

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
            is_enabled = dev.get("enabled", True)
            return dev["id"], dev.get("name", dev["id"]), is_enabled
            
        return None, None, False

    def match_and_get_id(self, decoded_data):
        dev_id, _, is_enabled = self.match_and_get_info(decoded_data)
        return dev_id if is_enabled else None
