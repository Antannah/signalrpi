# ota_updater.py -- GitHub OTA Update für signalrpi
import urequests
import os
import machine
import gc

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/Antannah/signalrpi/main"

# Liste der Kernkomponenten, die aktualisiert werden
FILES_TO_UPDATE = [
    "src/main.py",
    "src/web_server.py",
    "src/device_manager.py",
    "src/static_html.py",
    "src/cc1101.py",
    "src/pio_receiver.py",
    "src/ota_updater.py",
    "src/decoders/__init__.py",
    "src/decoders/cul_tcm97001.py",
    "src/decoders/lacrosse.py"
]

def update_from_github(callback=None):
    """
    Lädt alle Kern-Dateien von GitHub herunter und speichert sie im Flash.
    Führt anschließend einen Warmstart des Pico W durch.
    """
    success_count = 0
    errors = []

    for file_path in FILES_TO_UPDATE:
        # Lokaler Zielpfad: z. B. 'src/main.py' -> 'main.py'
        local_name = file_path.replace("src/", "")
        
        url = "{}/{}".format(GITHUB_RAW_BASE, file_path)
        if callback:
            callback("Downloading {}...".format(local_name))
        print("OTA: Lade", url)
        
        gc.collect()
        try:
            res = urequests.get(url)
            if res.status_code == 200:
                content = res.text
                res.close()
                
                # Prüfe, ob Unterverzeichnis existiert (z. B. decoders/)
                if "/" in local_name:
                    dir_name = local_name.split("/")[0]
                    try:
                        os.mkdir(dir_name)
                    except OSError:
                        pass
                        
                with open(local_name, "w") as f:
                    f.write(content)
                success_count += 1
                print("OTA: {} erfolgreich aktualisiert".format(local_name))
            else:
                err_msg = "HTTP {} für {}".format(res.status_code, local_name)
                errors.append(err_msg)
                print("OTA Fehler:", err_msg)
                res.close()
        except Exception as ex:
            err_msg = "{}: {}".format(local_name, ex)
            errors.append(err_msg)
            print("OTA Exception:", err_msg)

    if success_count > 0:
        print("OTA Update abgeschlossen: {} Dateien aktualisiert. Starte neu...".format(success_count))
        if callback:
            callback("Update fertig ({} Dateien). Neustart in 2s...".format(success_count))
        import time
        time.sleep(2)
        machine.reset()
        return True, "Update erfolgreich"
    else:
        return False, "Keine Dateien aktualisiert: " + ", ".join(errors)
