# decoders/tcm97001.py -- Decoder für TCM97001 (NC_WS) Wettersensoren

from .base import BaseDecoder
from .pattern_decoder import PatternDecoder, SignalPattern

class DecoderTCM97001(BaseDecoder):
    """
    Decodiert TCM97001 (NC_WS) Wettersensoren.
    Nutzt vorrangig das SignalPattern (Mustererkennung: Takt ~500 µs, 1:4=0, 1:8=1)
    sowie die bewährte Zeitschwellen-Logik als Fallback.
    """

    def __init__(self) -> None:
        super().__init__("TCM97001")

    def decode(self, signal) -> dict | None:
        pattern = None

        if isinstance(signal, SignalPattern):
            pattern = signal
        elif isinstance(signal, list):
            pattern = PatternDecoder.decode_pattern(signal)

        if pattern and 350 <= pattern.clock <= 650:
            return self._decode_pattern(pattern)

        return None

    def _decode_pattern(self, pattern: SignalPattern) -> dict | None:
        """
        Musterübersetzung:
        High-Puls: 1T (~500 µs)
        Bit 0: Low 3..5T (~2000 µs / 4T)
        Bit 1: Low 6..10T (~4000 µs / 8T)
        Sync:  Low >= 14T (~9000 µs)
        """
        m = pattern.multiples
        bits = []
        i = 0
        while i < len(m) - 1:
            high = m[i]
            low = m[i+1]
            if high == 1:
                if 3 <= low <= 5:
                    bits.append(0)
                    i += 2
                    continue
                elif 6 <= low <= 10:
                    bits.append(1)
                    i += 2
                    continue
            
            # Bei Fehlpassung oder Sync: Puffer zurücksetzen wenn noch keine 36 Bits
            if len(bits) < 36:
                bits = []
            elif len(bits) >= 36:
                break
            i += 1

        if len(bits) < 36:
            return None

        return self._parse_bits(bits[:36], pattern.clock)

    def _parse_bits(self, bits: list[int], clock: int | None = None) -> dict | None:
        """
        Originale CUL_TCM97001 Bit-Extraktion:
        9 Hex-Zeichen, erstes Zeichen muss '5' sein.
        ID = dezimaler Wert des ersten Bytes (hex_str[0:2]), z.B. 80, 91, 87.
        """
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

        # 1. Temperatur (12 Bit signed aus Nibbles 4, 5, 6)
        temp_hex = hex_str[4:7]
        temp_val = int(temp_hex, 16)

        negative = int(hex_str[4], 16) & 0x8
        if negative:
            temp_val = -((~temp_val & 0x7FF) + 1)

        temperature = temp_val / 10.0
        if temperature < -30.0 or temperature > 60.0:
            return None

        # 2. Luftfeuchtigkeit (7 Bit aus Nibbles 7, 8)
        humidity = int(hex_str[7:9], 16) & 0x7F
        if humidity < 0 or humidity > 100:
            return None

        # 3. Kanal (Bits 14-15 von Nibble 3, Wertebereich 1-3)
        channel = (int(hex_str[3], 16) & 0x3) + 1

        # 4. Batterie-Status (Bit 12 von Nibble 3, 1 = Ok, 0 = Low)
        batbit = (int(hex_str[3], 16) & 0x8) >> 3
        battery_low = (batbit == 0)

        # 5. Sendemodus (Bit 13 von Nibble 3, 1 = manuell, 0 = auto)
        mode = (int(hex_str[3], 16) & 0x4) >> 2

        # Device ID in FHEM/CUL: dezimaler Wert des ersten Bytes (z.B. 0x50 -> 80, 0x5B -> 91)
        device_id = str(int(hex_str[0:2], 16))

        res = {
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
        if clock:
            res["data"]["clock"] = clock
        return res
