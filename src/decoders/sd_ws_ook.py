# decoders/sd_ws_ook.py -- Decoder für SD_WS_50 (XT300 Bodenfeuchtesensor)

from .base import BaseDecoder

class DecoderWSOOK(BaseDecoder):
    def __init__(self) -> None:
        super().__init__("SD_WS_50")

    def decode(self, pulses: list) -> dict | None:
        """
        Versucht, eine Pulsfolge als SD_WS_50 (Opus XT300) Signal zu dekodieren.
        
        Soll-Puls-Timing (Base-Clock ~500 us):
        - Bit 0: ca. 1500 us High + 1000 us Low (Verhältnis 3:-2)
        - Bit 1: ca. 500 us High + 1000 us Low (Verhältnis 1:-2)
        - Timeout am Ende des Pakets wird als lange Low-Phase (> 5000 us) erfasst.
        """
        bits = []
        for i in range(0, len(pulses) - 1, 2):
            high = pulses[i]
            low = pulses[i+1]
            
            # Die Low-Phase sollte um 1000 us liegen (erlaubt 600 bis 1500 us).
            # Für die allerletzte Low-Phase (Timeout) akzeptieren wir Werte >= 1500 us.
            is_last_pulse = (i == len(pulses) - 2)
            if 600 <= low <= 1500 or (is_last_pulse and low >= 1500):
                # High-Phase bestimmt den Bit-Wert
                if 1100 <= high <= 1900:
                    bits.append(0)
                elif 250 <= high <= 850:
                    bits.append(1)
                    
        # Ein vollständiges Paket besteht aus 48 Bits (6 Bytes)
        if len(bits) != 48:
            return None
            
        # Bits in Bytes umwandeln
        bytes_data = bytearray()
        for i in range(0, 48, 8):
            byte_bits = bits[i:i+8]
            val = 0
            for bit in byte_bits:
                val = (val << 1) | bit
            bytes_data.append(val)
            
        # Das erste Byte (Preamble) muss 0xFF sein
        if bytes_data[0] != 0xFF:
            return None
            
        # Checksumme validieren
        # (Byte 1 + Byte 2 + Byte 3 + Byte 4) & 0xFF == Byte 5
        checksum_calc = sum(bytes_data[1:5]) & 0xFF
        if checksum_calc != bytes_data[5]:
            return None
            
        # Sensor-ID (Untere 2 Bits von Byte 1, ergibt ID 1, 2 oder 3)
        sensor_id = bytes_data[1] & 0x03
        device_id = f"SM_{sensor_id}"
        
        # Bodenfeuchtigkeit in % (Byte 2)
        moisture = float(bytes_data[2])
        
        # Temperatur (Byte 3, Offset um 40 Grad subtrahieren)
        temperature = float(bytes_data[3] - 40)
        
        # Plausibilitätsprüfungen
        if moisture < 0.0 or moisture > 100.0:
            return None
        if temperature < -30.0 or temperature > 60.0:
            return None
            
        return {
            "protocol": "SD_WS_50",
            "device_id": device_id,
            "data": {
                "moisture": moisture,
                "temperature": temperature
            }
        }
