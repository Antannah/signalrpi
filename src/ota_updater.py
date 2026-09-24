# ota_updater.py -- GitHub OTA Update für signalrpi
import urequests
import os
import machine
import gc

GITHUB_RAW_TEMPLATE = "https://raw.githubusercontent.com/Antannah/signalrpi/{}"

# Liste der Kernkomponenten, die aktualisiert werden
FILES_TO_UPDATE = [
    "src/main.py",
    "src/web_server.py",
    "src/device_manager.py",
    "src/index.html.gz",
    "src/cc1101.py",
    "src/pio_receiver.py",
    "src/time_sync.py",
    "src/ota_updater.py",
    "src/en_decoders/__init__.py",
    "src/en_decoders/base.py",
    "src/en_decoders/pattern_decoder.py",
    "src/en_decoders/it_encoder.py",
    "src/en_decoders/intertechno.py",
    "src/en_decoders/tcm97001.py",
    "src/en_decoders/sd_ws07.py",
    "src/en_decoders/sd_ws_ook.py",
    "src/en_decoders/sd_ws_fsk.py"
]

VERSION = "1.1.0-alpha"

def get_version_info():
    """
    Liest den aktuellen Versions- und Branch-Stand aus version.json.
    """
    info = {
        "version": VERSION,
        "branch": "main",
        "updated_at": "-"
    }
    try:
        import json
        with open("version.json", "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                info.update(data)
    except Exception:
        pass
    return info

def save_version_info(branch):
    try:
        import json, time
        t = time.localtime()
        dt_str = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}".format(t[0], t[1], t[2], t[3], t[4])
        info = {
            "version": VERSION,
            "branch": str(branch),
            "updated_at": dt_str
        }
        with open("version.json", "w") as f:
            json.dump(info, f)
    except Exception as ex:
        print("Fehler beim Speichern von version.json:", ex)

FILES_TO_CLEANUP = [
    "index.html",
    "static_html.py"
]

def cleanup_obsolete_files():
    """Löscht veraltete/überflüssige Dateien aus dem Flash-Speicher."""
    for fn in FILES_TO_CLEANUP:
        try:
            os.remove(fn)
            print("OTA Cleanup: {} gelöscht".format(fn))
        except OSError:
            pass

# Status-Tracking für das Webinterface
is_updating = False

ota_state = {
    "status": "idle",       # idle, downloading, rebooting, error
    "branch": "main",
    "current_file": "",
    "step": 0,
    "total": len(FILES_TO_UPDATE),
    "message": ""
}

def get_ota_state():
    return ota_state

def update_from_github(branch="main", callback=None):
    """
    Lädt alle Kern-Dateien von GitHub herunter und speichert sie im Flash.
    Führt anschließend einen Warmstart des Pico W durch.
    """
    global ota_state, is_updating
    try:
        is_updating = True
        ota_state["status"] = "downloading"
        ota_state["branch"] = branch
        ota_state["step"] = 0
        ota_state["total"] = len(FILES_TO_UPDATE)
        ota_state["message"] = "Bereinige alte Dateien..."
        
        cleanup_obsolete_files()
        success_count = 0
        errors = []
        base_url = GITHUB_RAW_TEMPLATE.format(branch)

        for idx, file_path in enumerate(FILES_TO_UPDATE):
            # Lokaler Zielpfad: z. B. 'src/main.py' -> 'main.py'
            local_name = file_path.replace("src/", "")
            ota_state["step"] = idx + 1
            ota_state["current_file"] = local_name
            ota_state["message"] = "Lade {} ({}/{})...".format(local_name, idx + 1, len(FILES_TO_UPDATE))
            
            url = "{}/{}".format(base_url, file_path)
            if callback:
                callback("Downloading {}...".format(local_name))
            print("OTA: Lade", url)
            
            file_downloaded = False
            # Retry-Schleife (bis zu 2 Versuche je Datei)
            for attempt in range(2):
                gc.collect()
                res = None
                try:
                    res = urequests.get(url)
                    if res.status_code == 200:
                        is_bin = local_name.endswith(".gz")
                        
                        # Stelle sicher, dass Unterverzeichnisse existieren
                        if "/" in local_name:
                            parts = local_name.split("/")
                            cur_dir = ""
                            for part in parts[:-1]:
                                cur_dir = cur_dir + "/" + part if cur_dir else part
                                try:
                                    os.mkdir(cur_dir)
                                except OSError:
                                    pass
                                
                        # Streame in 1 KB Chunks direkt auf Flash als Binärdaten (vermeidet UTF-8 Split & ENOMEM)
                        with open(local_name, "wb") as f:
                            while True:
                                chunk = res.raw.read(1024)
                                if not chunk:
                                    break
                                f.write(chunk)
                                gc.collect()
                        
                        try:
                            if hasattr(res, "raw") and res.raw:
                                res.raw.close()
                        except Exception:
                            pass
                        res.close()
                        del res
                        res = None
                        gc.collect()
                        file_downloaded = True
                        success_count += 1
                        print("OTA: {} erfolgreich aktualisiert".format(local_name))
                        break
                    else:
                        err_msg = "HTTP {} für {}".format(res.status_code, local_name)
                        if res:
                            try:
                                if hasattr(res, "raw") and res.raw:
                                    res.raw.close()
                            except Exception:
                                pass
                            res.close()
                            del res
                            res = None
                        if attempt == 1:
                            errors.append(err_msg)
                            print("OTA Fehler:", err_msg)
                except Exception as ex:
                    if res:
                        try:
                            if hasattr(res, "raw") and res.raw:
                                res.raw.close()
                        except Exception:
                            pass
                        try:
                            res.close()
                        except Exception:
                            pass
                        del res
                        res = None
                    gc.collect()
                    err_msg = "{}: {}".format(local_name, ex)
                    if attempt == 1:
                        errors.append(err_msg)
                        print("OTA Exception:", err_msg)
                
                # Kurze Pause vor dem Retry
                import time
                time.sleep_ms(300)
                
            gc.collect()
            import time
            time.sleep_ms(50)

        if len(errors) == 0 and success_count == len(FILES_TO_UPDATE):
            save_version_info(branch)
            ota_state["status"] = "rebooting"
            ota_state["message"] = "Update erfolgreich ({}/{}). Starte neu...".format(success_count, len(FILES_TO_UPDATE))
            print("OTA Update abgeschlossen: {} Dateien aktualisiert. Starte neu...".format(success_count))
            if callback:
                callback("Update fertig ({} Dateien). Neustart in 2s...".format(success_count))
            import time
            time.sleep(2)
            machine.reset()
            return True, "Update erfolgreich"
        else:
            is_updating = False
            ota_state["status"] = "error"
            err_summary = ", ".join(errors)
            ota_state["message"] = "Fehler bei {} Datei(en): {}".format(len(errors), err_summary)
            return False, "Fehler beim OTA Update: " + err_summary
    except Exception as fatal_ex:
        is_updating = False
        ota_state["status"] = "error"
        ota_state["message"] = "Absturz während OTA: {}".format(fatal_ex)
        print("Fatal OTA Error:", fatal_ex)
        return False, str(fatal_ex)
