# decoders/intertechno.py -- Decoder für Intertechno V1 (Tri-State) und V3 (Manchester)

from .base import BaseDecoder
from .pattern_decoder import PatternDecoder, SignalPattern

class DecoderIntertechno(BaseDecoder):
    """
    Decodiert Intertechno V1 (Tri-State Dreh-/DIP-Schalter) und Intertechno V3 (Manchester)
    mittels diskret quantisierter Vielfacher aus dem SignalPattern (PatternDecoder).
    """

    # FHEM 10_IT.pm Drehschalter Zuordnungstabelle
    _FAM_REV = {
        '0000': 'A', 'F000': 'B', '0F00': 'C', 'FF00': 'D',
        '00F0': 'E', 'F0F0': 'F', '0FF0': 'G', 'FFF0': 'H',
        '000F': 'I', 'F00F': 'J', '0F0F': 'K', 'FF0F': 'L',
        '00FF': 'M', 'F0FF': 'N', '0FFF': 'O', 'FFFF': 'P'
    }

    _DEV_REV = {
        '0000': 1, 'F000': 2, '0F00': 3, 'FF00': 4,
        '00F0': 5, 'F0F0': 6, '0FF0': 7, 'FFF0': 8,
        '000F': 9, 'F00F': 10, '0F0F': 11, 'FF0F': 12,
        '00FF': 13, 'F0FF': 14, '0FFF': 15, 'FFFF': 16
    }

    def __init__(self) -> None:
        super().__init__("IT")

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

        if not pattern:
            return None

        # 1. Prüfe auf Intertechno V1 (Tri-State)
        res_v1 = self._decode_v1(pattern)
        if res_v1:
            return res_v1

        # 2. Prüfe auf Intertechno V3 (Manchester)
        res_v3 = self._decode_v3(pattern)
        if res_v3:
            return res_v3

        return None

    def _decode_v1(self, pattern: SignalPattern) -> dict | None:
        # IT V1 Basiszeit liegt bei 260..420 µs (typ. 320-380 µs)
        if not (240 <= pattern.clock <= 440):
            return None

        # Ein echtes IT V1 Telegramm hat einen Sync-/Pausen-Puls (mind. 12T, typ. 31T)
        if pattern.sync_ratio < 12.0:
            return None

        m = pattern.multiples
        if len(m) < 24:
            return None

        # Suche nach einer Folge von 12 Tri-State Symbolen (mind. 24 Flanken/Paare)
        # Jedes Symbol besteht aus 4 Pulsen (2 Paare aus High/Low)
        # Wir durchsuchen m mit gleitendem Fenster
        for start_idx in range(len(m) - 23):
            # Prüfe ob wir ab start_idx Tri-State Bits bilden können
            bits = []
            idx = start_idx
            valid = True
            
            while idx + 3 < len(m) and len(bits) < 12:
                chunk = m[idx:idx+4]
                # '0': 1T 3T 1T 3T
                if chunk[0] == 1 and (2 <= chunk[1] <= 4) and chunk[2] == 1 and (2 <= chunk[3] <= 4):
                    bits.append('0')
                    idx += 4
                # 'F': 1T 3T 3T 1T
                elif chunk[0] == 1 and (2 <= chunk[1] <= 4) and (2 <= chunk[2] <= 4) and chunk[3] == 1:
                    bits.append('F')
                    idx += 4
                # '1': 3T 1T 3T 1T
                elif (2 <= chunk[0] <= 4) and chunk[1] == 1 and (2 <= chunk[2] <= 4) and chunk[3] == 1:
                    bits.append('1')
                    idx += 4
                # 'D': 3T 1T 1T 3T
                elif (2 <= chunk[0] <= 4) and chunk[1] == 1 and chunk[2] == 1 and (2 <= chunk[3] <= 4):
                    bits.append('D')
                    idx += 4
                else:
                    valid = False
                    break

            if len(bits) == 12:
                # Erfolgreich 12 Tri-State Zeichen extrahiert!
                fam_code = "".join(bits[0:4])
                dev_code = "".join(bits[4:8])
                grp_code = "".join(bits[8:10])
                state_code = "".join(bits[10:12])

                family = self._FAM_REV.get(fam_code, fam_code)
                device = self._DEV_REV.get(dev_code, dev_code)
                
                # FHEM / SignalDUINO Konvention: 'FF' = ON, 'F0' / '00' = OFF
                state_val = "ON" if (state_code == "FF" or bits[11] == "F") else "OFF"
                
                # Standard ID Format für V1: z. B. C_1_3 oder C3
                dev_id = f"{family}_1_{device}"

                return {
                    "protocol": "IT",
                    "device_id": dev_id,
                    "data": {
                        "family": family,
                        "group": 1,
                        "device": device,
                        "state": state_val,
                        "raw_tristate": "".join(bits),
                        "clock": pattern.clock
                    }
                }

        return None

    def _decode_v3(self, pattern: SignalPattern) -> dict | None:
        # IT V3 Manchester: Basiszeit liegt typischerweise bei 220..320 µs
        if not (180 <= pattern.clock <= 350):
            return None

        m = pattern.multiples
        # IT V3 hat: Start (1, 10), 32 Bits (je 4 Pulse), Stop (1, 36) -> ~130 Pulse
        if len(m) < 66:
            return None

        # Suche Startpuls: High 1T, Low >= 8T
        for start_idx in range(len(m) - 65):
            if m[start_idx] == 1 and m[start_idx + 1] >= 8:
                # Folge von Bits dekodieren
                bits = []
                idx = start_idx + 2
                while idx + 3 < len(m) and len(bits) < 32:
                    chunk = m[idx:idx+4]
                    # Bit 0: 1 1 1 5 (T T T 5T)
                    if chunk[0] == 1 and chunk[1] <= 2 and chunk[2] == 1 and chunk[3] >= 3:
                        bits.append("0")
                        idx += 4
                    # Bit 1: 1 5 1 1 (T 5T T T)
                    elif chunk[0] == 1 and chunk[1] >= 3 and chunk[2] == 1 and chunk[3] <= 2:
                        bits.append("1")
                        idx += 4
                    else:
                        break

                if len(bits) == 32:
                    bin_code = "".join(bits[0:26])
                    grp_bit = bits[26]
                    state_bit = bits[27]
                    unit_bits = "".join(bits[28:32])
                    
                    unit = int(unit_bits, 2) + 1
                    state = "ON" if state_bit == "1" else "OFF"
                    
                    return {
                        "protocol": "IT_V3",
                        "device_id": bin_code,
                        "data": {
                            "binary_code": bin_code,
                            "group": bool(int(grp_bit)),
                            "channel": unit,
                            "state": state,
                            "clock": pattern.clock
                        }
                    }

        return None
