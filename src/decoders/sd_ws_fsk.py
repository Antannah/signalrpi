# decoders/sd_ws_fsk.py -- Decoder für FSK-Sensoren: SD_WS_107 (WH51) & SD_WS_126 (WH40)

from .base import BaseDecoder

def crc8_poly31(data: bytes) -> int:
    """Berechnet die CRC8 mit Polynom 0x31 (Init 0x00, nicht reflektiert)."""
    crc = 0x00
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x31) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc

class DecoderWSFSK(BaseDecoder):
    def __init__(self) -> None:
        # Dieser Decoder bedient beide Typen (WH51 und WH40)
        super().__init__("SD_WS_FSK")

    def decode(self, packet: bytes) -> dict | None:
        """
        Dekodiert ein FSK-Paket vom CC1101 (14 Bytes Payload).
        Gibt ein strukturiertes Dict zurück oder None bei Fehlern.
        """
        if len(packet) < 14:
            return None
            
        family_code = packet[0]
        
        if family_code == 0x51:
            # --- WH51 Bodenfeuchtesensor (Protokoll 107) ---
            # 1. Checksummenprüfung
            # CRC8 über die ersten 12 Bytes (0-11)
            crc_calc = crc8_poly31(packet[:12])
            if crc_calc != packet[12]:
                return None
                
            # Summen-Checksumme über die ersten 13 Bytes (0-12)
            sum_calc = sum(packet[:13]) & 0xFF
            if sum_calc != packet[13]:
                return None
                
            # 2. Datenextraktion
            # ID (3 Bytes ab Byte 1)
            device_id = packet[1:4].hex().upper()
            
            # Batteriestatus (Bits 35-39, d.h. untere 5 Bits von Byte 4)
            battery_volt = (packet[4] & 0x1F) / 10.0
            battery_low = (battery_volt < 1.2)
            
            # Bodenfeuchtigkeit in % (Byte 6)
            moisture = float(packet[6])
            
            # 10-Bit ADC-Wert (Bit 62-71: LSBs von Byte 7 + Byte 8)
            adc = ((packet[7] & 0x03) << 8) | packet[8]
            
            # Plausibilität prüfen
            if moisture < 0.0 or moisture > 100.0:
                return None
                
            return {
                "protocol": "SD_WS_107",
                "device_id": device_id,
                "data": {
                    "moisture": moisture,
                    "battery_voltage": battery_volt,
                    "battery_low": battery_low,
                    "adc": adc
                }
            }
            
        elif family_code == 0x40:
            # --- WH40 Regensensor (Protokoll 126) ---
            # 1. Checksummenprüfung
            # CRC8 über die ersten 7 Bytes (0-6)
            crc_calc = crc8_poly31(packet[:7])
            if crc_calc != packet[7]:
                return None
                
            # Summen-Checksumme über die ersten 8 Bytes (0-7)
            sum_calc = sum(packet[:8]) & 0xFF
            if sum_calc != packet[8]:
                return None
                
            # 2. Datenextraktion
            # ID (3 Bytes ab Byte 1)
            device_id = packet[1:4].hex().upper()
            
            # Batteriestatus (untere 5 Bits von Byte 4)
            battery_volt = (packet[4] & 0x1F) / 10.0
            battery_low = (battery_volt < 1.2) if battery_volt > 0 else False
            
            # Regenmenge (2 Bytes ab Byte 5: RR RR in 0.1 mm Schritten)
            rain_ticks = (packet[5] << 8) | packet[6]
            rain_total = float(rain_ticks) * 0.1
            
            return {
                "protocol": "SD_WS_126",
                "device_id": device_id,
                "data": {
                    "rain_total": rain_total,
                    "rain_ticks": rain_ticks,
                    "battery_voltage": battery_volt if battery_volt > 0 else None,
                    "battery_low": battery_low
                }
            }
            
        return None
