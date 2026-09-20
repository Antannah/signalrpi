# decoders/sd_ws07.py -- Decoder für Nexus / Eurochron / FreeTec (SD_WS07)
# Protokoll 7 (FHEM SD_WS07)

from .base import BaseDecoder
from pattern_decoder import PatternDecoder, SignalPattern

class DecoderWS07(BaseDecoder):
    """
    Decodiert Wettersensoren nach dem Nexus/Eurochron/FreeTec-Protokoll (FHEM SD_WS07).
    Modulation: PPM (Puls-Pausen-Modulation), Takt ~500 µs
    - Bit 0: ~500 µs High (1T) + ~1000 µs Low (2T)
    - Bit 1: ~500 µs High (1T) + ~2000 µs Low (4T)
    - Sync / Interpacket-Pause: ~4000 µs (8T)

    Paket-Aufbau (36 Bits = 9 Nibbles):
    [0..7]:   Sensor-ID (8 Bit)
    [8]:      Batterie (1 = OK, 0 = Low)
    [9]:      Sendemodus (1 = manuell, 0 = auto) / oder Channel-Bit
    [10..11]: Kanal (2 Bit, 0..2 -> Ch 1..3)
    [12..23]: Temperatur (12 Bit signed, zweierkomplement oder >= 3840 -> temp - 4096, Skalierung / 10)
    [24..27]: Konstante / Marker: typischerweise 0xF (1111) oder 0xA (1010)
    [28..35]: Luftfeuchtigkeit (8 Bit, 0..100 %, 0 = nur Temperatur)
    """

    def __init__(self) -> None:
        super().__init__("SD_WS07")

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
        if pattern and 300 <= pattern.clock <= 700 and len(pattern.multiples) >= 20:
            res = self._decode_pattern(pattern)
            if res:
                return res

        # 2. Fallback auf rohe Mikrosekunden-Folge
        if raw_pulses and len(raw_pulses) >= 20:
            return self._decode_raw(raw_pulses)

        return None

    def _decode_pattern(self, pattern: SignalPattern) -> dict | None:
        """
        Decodiert SD_WS07 mittels diskreter Vielfacher:
        - Bit 0: 1T High, 2T Low (erlaubt 1..3T)
        - Bit 1: 1T High, 4T Low (erlaubt 3..5T)
        - Sync / Pause: >= 6T Low (überspringen/beenden)
        """
        m = pattern.multiples
        bits = []
        i = 0
        while i < len(m) - 1:
            high = m[i]
            low = m[i+1]

            if high == 1:
                if 1 <= low <= 3:       # ~2T Low -> Bit 0
                    bits.append(0)
                    i += 2
                    continue
                elif 4 <= low <= 6:     # ~4T Low -> Bit 1
                    bits.append(1)
                    i += 2
                    continue
                elif low >= 7:          # Sync / Endpause (~8T)
                    if len(bits) >= 32:
                        break
                    bits = []
                    i += 2
                    continue

            # Bei Fehlschlag Puffer zurücksetzen, falls noch keine vollen Bits
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
        High: 300..700 µs
        Low 0: 700..1500 µs
        Low 1: 1600..2600 µs
        """
        bits = []
        i = 0
        while i < len(pulses) - 1:
            high = pulses[i]
            low = pulses[i+1]

            if 250 <= high <= 750:
                if 650 <= low <= 1500:
                    bits.append(0)
                    i += 2
                    continue
                elif 1550 <= low <= 2800:
                    bits.append(1)
                    i += 2
                    continue
                elif low > 3000:
                    if len(bits) >= 32:
                        break
                    bits = []
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
        Extrahiert Temperatur, Feuchte, ID, Batterie und Kanal aus mindestens 32 bzw. 36 Bits.
        """
        # Auffüllen auf 36 Bits falls z.B. 32-35 empfangen wurden (letzte Bits manchmal abgeschnitten)
        b = bits[:]
        while len(b) < 36:
            b.append(0)

        # In Hex-String umwandeln (9 Hex-Zeichen)
        hex_str = ""
        for i in range(0, 36, 4):
            nibble = b[i:i+4]
            val = 0
            for bit in nibble:
                val = (val << 1) | bit
            hex_str += "{:X}".format(val)

        # ID: Erstes Byte (2 Hex-Zeichen)
        dev_id_hex = hex_str[0:2]

        # Flags: Nibble 2 (Bits 8..11)
        b8 = b[8]   # 1 = Batterie OK, 0 = Batterie schwach
        battery_low = (b8 == 0)

        # Prüfe Konstante / Marker in Nibble 6 (Bits 24..27: 0xF oder 0xA)
        marker = int(hex_str[6], 16)
        if marker not in (0xF, 0xA, 0x0):
            # Nicht konform zu SD_WS07
            return None

        if marker == 0xA:
            # Auriol AFW 2 A1 Variante
            forced_send = bool(b[9])
            channel = ((b[10] << 1) | b[11]) + 1
        else:
            forced_send = False
            channel = ((b[9] << 2) | (b[10] << 1) | b[11]) + 1
            if channel > 4:
                channel = ((b[10] << 1) | b[11]) + 1

        # Temperatur (Bits 12..23 = Nibble 3, 4, 5)
        temp_val = (b[12] << 11) | (b[13] << 10) | (b[14] << 9) | (b[15] << 8) | \
                   (b[16] << 7)  | (b[17] << 6)  | (b[18] << 5) | (b[19] << 4) | \
                   (b[20] << 3)  | (b[21] << 2)  | (b[22] << 1) | b[23]

        # Negative Temperatur nach FHEM SD_WS07-Standard:
        if temp_val >= 3840:
            temp_val -= 4096
        elif b[12] == 1 and temp_val > 2048:
            temp_val = -((~temp_val & 0xFFF) + 1)

        temperature = temp_val / 10.0
        if temperature < -40.0 or temperature > 70.0:
            return None

        # Luftfeuchtigkeit (Bits 28..35 = Nibble 7, 8)
        hum_val = int(hex_str[7:9], 16)
        if hum_val > 100:
            hum_val = None

        device_id = f"{dev_id_hex}_{channel}"

        data = {
            "temperature": temperature,
            "channel": channel,
            "battery_low": battery_low,
            "forced_send": forced_send
        }
        if hum_val is not None:
            data["humidity"] = hum_val

        res = {
            "protocol": "SD_WS07",
            "device_id": device_id,
            "data": data
        }
        if clock:
            res["data"]["clock"] = clock
        return res
