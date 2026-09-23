# it_encoder.py -- Puls-Encoder für Intertechno V1 (Tri-State) und V3 (Manchester)

class ITEncoder:
    # Offizielle FHEM 10_IT.pm Tri-State Tabelle für Drehschalter (A..P und 1..16)
    _FAM_MAP = {
        'A': '0000', 'B': 'F000', 'C': '0F00', 'D': 'FF00',
        'E': '00F0', 'F': 'F0F0', 'G': '0FF0', 'H': 'FFF0',
        'I': '000F', 'J': 'F00F', 'K': '0F0F', 'L': 'FF0F',
        'M': '00FF', 'N': 'F0FF', 'O': '0FFF', 'P': 'FFFF'
    }
    _DEV_MAP = {
        1: '0000', 2: 'F000', 3: '0F00', 4: 'FF00',
        5: '00F0', 6: 'F0F0', 7: '0FF0', 8: 'FFF0',
        9: '000F', 10: 'F00F', 11: '0F0F', 12: 'FF0F',
        13: '00FF', 14: 'F0FF', 15: '0FFF', 16: 'FFFF'
    }

    @staticmethod
    def encode_it_v1(family: str, group: int, device: int, state: bool) -> list:
        """
        Erzeugt die High/Low-Mikrosekunden-Pulsfolge für ein Intertechno V1 Telegramm (Tri-State).
        Exakt nach FHEM 10_IT.pm Standard für Drehschalter / DIP-Schalter.
        
        Telegramm-Aufbau: 12 Tri-State Bits (24 Flanken):
        - Bits 0..3:  Hauscode / Family (A..P -> Tri-State)
        - Bits 4..7:  Geräteadresse (1..16 -> Tri-State)
        - Bits 8..9:  Gruppe / Flags ('0F')
        - Bits 10..11: Zustand (EIN: 'FF', AUS: 'F0')
        
        Tri-State Definitionen (Basiszeit Te ca. 380 µs laut Messung):
        - '0': High 1 Te, Low 3 Te, High 1 Te, Low 3 Te
        - 'F': High 1 Te, Low 3 Te, High 3 Te, Low 1 Te
        - '1': High 3 Te, Low 1 Te, High 3 Te, Low 1 Te
        - Sync-Pause: High 1 Te, Low 31 Te (ca. 11.500 µs)
        """
        te = 380  # Basiszeit in µs (SignalDUINO / FHEM Standard ~380-420 µs)
        
        fam_str = ITEncoder._FAM_MAP.get(str(family).upper(), '0000')
        dev_str = ITEncoder._DEV_MAP.get(int(device), '0000')
        grp_str = '0F'
        state_str = 'FF' if state else 'F0'
        
        # Gesamter 12-Bit Tri-State Code
        all_bits = fam_str + dev_str + grp_str + state_str
        
        pulses = []
        for bit in all_bits:
            if bit == '0':
                pulses.extend([te, te * 3, te, te * 3])
            elif bit == 'F':
                pulses.extend([te, te * 3, te * 3, te])
            elif bit == '1':
                pulses.extend([te * 3, te, te * 3, te])
                
        # Sync-Puls am Ende des Bursts (High 1 Te, Low ~31 Te bzw. 11.500 µs)
        pulses.extend([te, te * 31])
        return pulses

    @staticmethod
    def encode_it_v3(binary_code: str, channel: int, state: bool, group: bool = False) -> list:
        """
        Erzeugt die High/Low-Mikrosekunden-Pulsfolge für ein Intertechno V3 Telegramm (32-Bit Manchester).
        
        Aufbau:
        - 26 Bit: Sender-Adresse (Binärstring)
        - 1 Bit: Group (0 = Einzelgerät, 1 = Gruppe)
        - 1 Bit: State (1 = EIN / Anlernen, 0 = AUS)
        - 4 Bit: Unit / Kanal (0000 = Kanal 1 bis 1111 = Kanal 16)
        
        Manchester Codierung (Basiszeit T ca. 275 µs):
        - Start-Puls: High 1 T (275 µs), Low 10 T (2750 µs)
        - Bit 0: High 1 T, Low 1 T, High 1 T, Low 5 T (Manchester 01)
        - Bit 1: High 1 T, Low 5 T, High 1 T, Low 1 T (Manchester 10)
        - Stop/Sync-Puls: High 1 T, Low 36 T (ca. 10.000 µs)
        """
        t = 275  # Basiszeit in µs
        
        # Bereinige 26-Bit Code
        clean_code = "".join([c for c in binary_code if c in "01"])[:26]
        if len(clean_code) < 26:
            clean_code = clean_code.ljust(26, "0")
            
        grp_bit = "1" if group else "0"
        state_bit = "1" if state else "0"
        
        # Unit 1..16 -> 0..15 als 4 Bit Binärstring
        ch_idx = max(0, min(15, channel - 1))
        unit_bits = "{:04b}".format(ch_idx)
        
        # Vollständiges 32-Bit Telegramm
        full_bits = clean_code + grp_bit + state_bit + unit_bits
        
        pulses = []
        # 1. Start-Puls
        pulses.extend([t, t * 10])
        
        # 2. 32 Datenbits
        for b in full_bits:
            if b == "0":
                pulses.extend([t, t, t, t * 5])
            else:
                pulses.extend([t, t * 5, t, t])
                
        # 3. Stop / Sync-Pause
        pulses.extend([t, t * 36])
        return pulses
