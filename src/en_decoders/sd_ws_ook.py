# decoders/sd_ws_ook.py -- Decoder für SD_WS_50 (XT300 Bodenfeuchtesensor)

from .base import BaseDecoder
from .pattern_decoder import PatternDecoder, SignalPattern

class DecoderWSOOK(BaseDecoder):
    """
    Decodiert SD_WS_50 (Opus XT300 Bodenfeuchtesensoren).
    Nutzt vorrangig das SignalPattern (diskrete Vielfache via PatternDecoder)
    sowie rohe Pulsfolgen als Fallback.
    """

    def __init__(self) -> None:
        super().__init__("SD_WS_50")

    def decode(self, signal) -> dict | None:
        """
        signal kann entweder eine rohe Pulsfolge (list[int]) sein,
        oder bereits ein voranalysiertes SignalPattern.
        """
        pattern: SignalPattern | None = None

        if isinstance(signal, SignalPattern):
            pattern = signal
        elif isinstance(signal, list):
            pattern = PatternDecoder.decode_pattern(signal)

        if pattern and 300 <= pattern.clock <= 750 and len(pattern.multiples) >= 40:
            return self._decode_pattern(pattern)

        return None

    def _decode_pattern(self, pattern: SignalPattern) -> dict | None:
        """
        Decodiert SD_WS_50 mittels diskreter Vielfacher:
        - Takt ~500 µs
        - Bit 0: 3T High (~1500 µs), 2T Low (~1000 µs)
        - Bit 1: 1T High (~500 µs), 2T Low (~1000 µs)
        """
        m = pattern.multiples
        bits = []
        i = 0
        while i < len(m) - 1:
            high = m[i]
            low = m[i+1]
            
            # Low-Phase ist typischerweise 2T (erlaubt 1..3T oder langer Timeout >= 3T am Ende)
            is_last = (i >= len(m) - 2)
            if (1 <= low <= 3) or (is_last and low >= 3):
                if 2 <= high <= 4:      # ~3T High -> Bit 0
                    bits.append(0)
                    i += 2
                    continue
                elif high == 1:         # ~1T High -> Bit 1
                    bits.append(1)
                    i += 2
                    continue
            
            # Bei Fehlpassung Puffer zurücksetzen, falls noch keine 48 Bits
            if len(bits) < 48:
                bits = []
            elif len(bits) >= 48:
                break
            i += 1

        if len(bits) < 48:
            return None

        return self._parse_bits(bits[:48], pattern.clock)

    def _parse_bits(self, bits: list[int], clock: int | None = None) -> dict | None:
        """
        Extrahiert Feuchte, Temperatur, ID und Checksumme aus 48 Bits.
        """
        bytes_data = bytearray()
        for i in range(0, 48, 8):
            byte_bits = bits[i:i+8]
            val = 0
            for bit in byte_bits:
                val = (val << 1) | bit
            bytes_data.append(val)
            
        # Preamble muss 0xFF sein
        if bytes_data[0] != 0xFF:
            return None
            
        # Checksumme validieren
        # (Byte 1 + Byte 2 + Byte 3 + Byte 4) & 0xFF == Byte 5
        checksum_calc = sum(bytes_data[1:5]) & 0xFF
        if checksum_calc != bytes_data[5]:
            return None
            
        sensor_id = bytes_data[1] & 0x03
        device_id = f"SM_{sensor_id}"
        moisture = float(bytes_data[2])
        temperature = float(bytes_data[3] - 40)
        
        if moisture < 0.0 or moisture > 100.0:
            return None
        if temperature < -30.0 or temperature > 60.0:
            return None
            
        res = {
            "protocol": "SD_WS_50",
            "device_id": device_id,
            "data": {
                "moisture": moisture,
                "temperature": temperature
            }
        }
        if clock:
            res["data"]["clock"] = clock
        return res
