# decoders/tcm97001.py -- Decoder für TCM97001 (NC_WS) Wettersensoren

from .base import BaseDecoder
from pattern_decoder import PatternDecoder, SignalPattern

class DecoderTCM97001(BaseDecoder):
    """
    Decodiert TCM97001 / NC_WS Wettersensoren (z.B. TFA, PEARL NC7159).
    Arbeitet sowohl mit SignalPattern (diskrete Vielfache via PatternDecoder)
    als auch mit rohen Pulsfolgen (µs).
    """

    def __init__(self) -> None:
        super().__init__("TCM97001")

    def decode(self, signal) -> dict | None:
        """
        signal kann entweder eine rohe Pulsfolge (list[int]) sein,
        oder bereits ein voranalysiertes SignalPattern.
        """
        pattern: SignalPattern | None = None
        raw_pulses = None

        if isinstance(signal, SignalPattern):
            pattern = signal
            raw_pulses = signal.raw_pulses
        elif isinstance(signal, list):
            raw_pulses = signal
            pattern = PatternDecoder.decode_pattern(signal)

        # 1. Bevorzugt über diskret quantisierte Vielfache (Mustererkennung)
        if pattern and 300 <= pattern.clock <= 750 and len(pattern.multiples) >= 20:
            res = self._decode_pattern(pattern)
            if res:
                return res

        # 2. Fallback auf rohe Mikrosekunden-Folge
        if raw_pulses and len(raw_pulses) >= 20:
            return self._decode_raw(raw_pulses)

        return None

    def _decode_pattern(self, pattern: SignalPattern) -> dict | None:
        """
        Decodiert TCM97001 mittels diskreter Vielfacher:
        - Bit 0: 1T High, 3T..5T Low (~ 4T)
        - Bit 1: 1T High, 6T..10T Low (~ 8T)
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
            
            # Bei Fehlpassung Puffer zurücksetzen, wenn noch keine 32 Bits
            if len(bits) < 32:
                bits = []
            elif len(bits) >= 32:
                break
            i += 1

        if len(bits) < 32:
            return None

        return self._parse_bits(bits, pattern.clock)

    def _decode_raw(self, pulses: list[int]) -> dict | None:
        """
        Traditionelle Zeitschwellen-Dekodierung als Fallback.
        """
        bits = []
        i = 0
        while i < len(pulses) - 1:
            high = pulses[i]
            low = pulses[i+1]
            
            if 300 <= high <= 800:
                if 1400 <= low <= 2600:
                    bits.append(0)
                    i += 2
                    continue
                elif 3100 <= low <= 4800:
                    bits.append(1)
                    i += 2
                    continue
            
            if len(bits) < 32:
                bits = []
            elif len(bits) >= 32:
                break
            i += 1

        if len(bits) < 32:
            return None

        return self._parse_bits(bits)

    def _parse_bits(self, bits: list[int], clock: int | None = None) -> dict | None:
        """
        Extrahiert Temperatur, Luftfeuchtigkeit, Kanal und Status aus 32 oder 36 Bits.
        Unterstützt:
        - NC_WS (Start mit 0x5)
        - Prologue / FreeTec (Start mit 0x9)
        - Rubicson (Start mit 0x8)
        - Generische TCM97001 / ABS700 (32-36 Bit)
        """
        # In Hex-String umwandeln
        hex_len = (len(bits) // 4) * 4
        hex_str = ""
        for i in range(0, hex_len, 4):
            nibble = bits[i:i+4]
            val = 0
            for bit in nibble:
                val = (val << 1) | bit
            hex_str += "{:X}".format(val)

        if len(hex_str) < 8:
            return None

        # Fall A: 36-Bit Standard (NC_WS, Prologue, etc.)
        if len(hex_str) >= 9:
            # Erlaubte Start-Nibbles für TCM97001-Familie (0x5 = NC_WS, 0x9 = Prologue, 0x8 = Rubicson)
            first_nibble = hex_str[0]
            if first_nibble in ('5', '9', '8'):
                # 1. Temperatur dekodieren (12 Bit signed aus Nibbles 4, 5, 6)
                temp_hex = hex_str[4:7]
                temp_val = int(temp_hex, 16)
                
                negative = int(hex_str[4], 16) & 0x8
                if negative:
                    temp_val = -((~temp_val & 0x7FF) + 1)
                    
                temperature = temp_val / 10.0
                if -35.0 <= temperature <= 65.0:
                    # 2. Luftfeuchtigkeit (7 Bit aus Nibbles 7, 8)
                    humidity = int(hex_str[7:9], 16) & 0x7F
                    if 0 <= humidity <= 100:
                        channel = (int(hex_str[3], 16) & 0x3) + 1
                        batbit = (int(hex_str[3], 16) & 0x8) >> 3
                        mode = (int(hex_str[3], 16) & 0x4) >> 2
                        device_id = str(int(hex_str[0:2], 16))

                        res = {
                            "protocol": "TCM97001",
                            "device_id": device_id,
                            "data": {
                                "temperature": temperature,
                                "humidity": humidity,
                                "battery_low": (batbit == 0),
                                "channel": channel,
                                "forced_send": bool(mode)
                            }
                        }
                        if clock:
                            res["data"]["clock"] = clock
                        return res

        # Fall B: 32-Bit Format (8 Hex-Zeichen, z.B. ABS700, Mebus, TCM 32-bit)
        # ID: Byte 0, Nibble 2: Flags/Channel, Nibbles 3..5: Temp (oder 4..6), Nibbles 6..7: Hum
        # Nibbles: [0, 1] [2] [3, 4, 5] [6, 7]
        try:
            temp_raw = int(hex_str[3:6], 16)
            if temp_raw >= 2048:
                temp_raw -= 4096
            temp_val = temp_raw / 10.0
            hum_val = int(hex_str[6:8], 16)

            if -35.0 <= temp_val <= 65.0 and 0 <= hum_val <= 100:
                ch = (int(hex_str[2], 16) & 0x3) + 1
                bat_low = bool((int(hex_str[2], 16) & 0x8) == 0)
                dev_id = str(int(hex_str[0:2], 16))

                res = {
                    "protocol": "TCM97001",
                    "device_id": dev_id,
                    "data": {
                        "temperature": temp_val,
                        "humidity": hum_val,
                        "battery_low": bat_low,
                        "channel": ch
                    }
                }
                if clock:
                    res["data"]["clock"] = clock
                return res
        except Exception:
            pass

        return None
