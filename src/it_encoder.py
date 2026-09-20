# it_encoder.py -- Puls-Encoder für Intertechno V1 (Tri-State) und V3 (Manchester)

class ITEncoder:
    @staticmethod
    def encode_it_v1(family: str, group: int, device: int, state: bool) -> list:
        """
        Erzeugt die High/Low-Mikrosekunden-Pulsfolge für ein Intertechno V1 Telegramm (Tri-State).
        
        Telegramm-Aufbau: 12 Tri-State Bits (24 Flanken):
        - Bits 0..3:  Hauscode / Family (A..P -> Tri-State)
        - Bits 4..7:  Geräteadresse (1..4 / 1..16 -> Tri-State)
        - Bits 8..9:  Gruppe / Flags
        - Bits 10..11: Zustand (EIN: 'FF' oder '0F', AUS: 'F0' oder '00')
        
        Tri-State Definitionen (Basiszeit Te ca. 360 µs):
        - '0': High 1 Te, Low 3 Te, High 1 Te, Low 3 Te
        - 'F': High 1 Te, Low 3 Te, High 3 Te, Low 1 Te
        - Sync-Pause: ca. 10.500 µs Low
        """
        te = 360  # Basiszeit in µs
        
        # Mappe Family A..P auf 4 Tri-State Bits (FHEM-Standard)
        # A='0000', B='F000', C='0F00', D='FF00', E='00F0', F='F0F0', G='0FF0', H='FFF0', ...
        fam_idx = max(0, min(15, ord(family.upper()) - ord('A')))
        # Binär zu Tri-State ('0' wenn Bit 0, 'F' wenn Bit 1)
        fam_ts = [('F' if (fam_idx & (1 << i)) else '0') for i in range(4)]
        
        # Device (1..4 bzw. 1..16): 4 Tri-State Bits
        dev_idx = max(0, min(15, device - 1))
        dev_ts = [('F' if (dev_idx & (1 << i)) else '0') for i in range(4)]
        
        # Gruppe / Dummy: 2 Bits
        grp_ts = ['0', 'F']
        
        # Zustand: EIN = ['F', 'F'], AUS = ['F', '0']
        state_ts = ['F', 'F'] if state else ['F', '0']
        
        # Gesamter 12-Bit Tri-State Code
        all_bits = fam_ts + dev_ts + grp_ts + state_ts
        
        pulses = []
        for bit in all_bits:
            if bit == '0':
                pulses.extend([te, te * 3, te, te * 3])
            elif bit == 'F':
                pulses.extend([te, te * 3, te * 3, te])
            elif bit == '1':
                pulses.extend([te * 3, te, te * 3, te])
                
        # Sync-Puls am Ende des Bursts (High 1 Te, Low ~32 Te bzw. 10.500 µs)
        pulses.extend([te, 10500])
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
