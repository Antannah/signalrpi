# decoders/cul_tcm97001.py -- Decoder für CUL_TCM97001 (NC_WS)

from .base import BaseDecoder

class DecoderTCM97001(BaseDecoder):
    def __init__(self) -> None:
        super().__init__("CUL_TCM97001")

    def decode(self, pulses: list) -> dict | None:
        """
        Versucht, eine Pulsfolge als CUL_TCM97001 (NC_WS) Signal zu dekodieren.
        
        Soll-Puls-Timing (Base-Clock ~500 us):
        - Sync: ca. 500 us High + 9000 us Low
        - Bit 0: ca. 500 us High + 2000 us Low
        - Bit 1: ca. 500 us High + 4000 us Low
        """
        # Suche nach einer zusammenhängenden Folge von 36 Datenbits
        bits = []
        i = 0
        while i < len(pulses) - 1:
            high = pulses[i]
            low = pulses[i+1]
            
            # High-Puls: ca. 350 .. 750 µs
            if 300 <= high <= 800:
                if 1400 <= low <= 2600:
                    bits.append(0)
                    i += 2
                    continue
                elif 3100 <= low <= 4800:
                    bits.append(1)
                    i += 2
                    continue
            
            # Kein Treffer: wenn wir noch keine 36 Bits haben, Puffer zurücksetzen und weitersuchen
            if len(bits) < 36:
                bits = []
            elif len(bits) >= 36:
                break
            i += 1
        
        if len(bits) < 36:
            return None
            
        # Bits in Hex-String umwandeln (9 Hex-Zeichen)
        hex_str = ""
        for i in range(0, 36, 4):
            nibble = bits[i:i+4]
            val = 0
            for bit in nibble:
                val = (val << 1) | bit
            hex_str += "{:X}".format(val)
            
        # NC_WS Signale starten immer mit einer '5' im ersten Nibble
        if hex_str[0] != '5':
            return None
            
        # 1. Temperatur dekodieren (12 Bit signed aus Nibbles 4, 5, 6)
        temp_hex = hex_str[4:7]
        temp_val = int(temp_hex, 16)
        
        # Das höchste Bit von Nibble 4 ist das Vorzeichen-Bit (Bit 11)
        negative = int(hex_str[4], 16) & 0x8
        if negative:
            # 11-Bit Zweierkomplement
            temp_val = -((~temp_val & 0x7FF) + 1)
            
        temperature = temp_val / 10.0
        
        # Plausibilitätsprüfung für Temperatur
        if temperature < -30.0 or temperature > 60.0:
            return None
            
        # 2. Luftfeuchtigkeit dekodieren (7 Bit aus Nibbles 7, 8)
        humidity = int(hex_str[7:9], 16) & 0x7F
        
        # Plausibilitätsprüfung für Luftfeuchtigkeit
        if humidity < 0 or humidity > 100:
            return None
            
        # 3. Kanal dekodieren (Bits 14-15 von Nibble 3, Wertebereich 1-3)
        channel = (int(hex_str[3], 16) & 0x3) + 1
        
        # 4. Batterie-Status (Bit 12 von Nibble 3, 1 = Ok, 0 = Low)
        batbit = (int(hex_str[3], 16) & 0x8) >> 3
        battery_low = (batbit == 0)
        
        # 5. Sendemodus (Bit 13 von Nibble 3, 1 = manueller Test-Send, 0 = auto)
        mode = (int(hex_str[3], 16) & 0x4) >> 2
        
        # Device ID in FHEM entspricht dem dezimalen Wert des ersten Bytes (hex_str[0:2])
        # z.B. "50" in hex -> 80 in dec (se_eingang)
        device_id = str(int(hex_str[0:2], 16))
        
        return {
            "protocol": "CUL_TCM97001",
            "device_id": device_id,
            "data": {
                "temperature": temperature,
                "humidity": humidity,
                "battery_low": battery_low,
                "channel": channel,
                "forced_send": bool(mode)
            }
        }
