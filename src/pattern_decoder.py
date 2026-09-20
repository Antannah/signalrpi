# pattern_decoder.py -- Mustererkennung & Takt-Extraktion nach SignalDUINO-Prinzip

class SignalPattern:
    def __init__(self, clock: int, multiples: list[int], sync_ratio: float, raw_pulses: list[int]):
        self.clock = clock                  # Basis-Takt in µs (z. B. 380)
        self.multiples = multiples          # Diskrete Vielfache [1, 3, 1, 3, ...]
        self.sync_ratio = sync_ratio        # Verhältnis des längsten Pulses zum Clock (z. B. 31.0)
        self.raw_pulses = raw_pulses        # Originale Mikrosekunden-Werte

    def __len__(self):
        return len(self.raw_pulses)

    def __getitem__(self, idx):
        return self.raw_pulses[idx]

    def __iter__(self):
        return iter(self.raw_pulses)

    def __repr__(self):
        return f"<SignalPattern clock={self.clock}µs len={len(self.multiples)} sync={self.sync_ratio:.1f}T>"


class PatternDecoder:
    """
    Analysiert rohe Pulsfolgen (µs-Dauern) und extrahiert den Basis-Takt (Clock)
    sowie die ganzzahligen Vielfachen der Pulse (z. B. 1T, 3T, 31T).
    Basiert auf den Prinzipien des SignalDUINO signalDecoder.cpp.
    """

    @staticmethod
    def decode_pattern(pulses: list[int], tol_fact: float = 0.25) -> SignalPattern | None:
        """
        Nimmt eine Liste von Pulsen (µs) entgegen und gibt ein SignalPattern zurück,
        oder None wenn kein stabiles Muster/Takt ermittelt werden konnte.
        """
        if not pulses or len(pulses) < 8:
            return None

        # 1. Glitches filtern: Ignoriere Werte < 40 µs
        valid_pulses = [p for p in pulses if p >= 40]
        if len(valid_pulses) < 8:
            return None

        # 2. Clusterung (findpatt / compress_pattern)
        # Wir bilden Cluster aus ähnlichen Pulslängen (Toleranz ca. 20-25%)
        clusters = []  # Liste aus [avg_pulse, count]
        for p in valid_pulses:
            matched = False
            for c in clusters:
                avg = c[0]
                tol = avg * tol_fact
                if abs(p - avg) <= tol:
                    # Gleitender / gewichteter Mittelwert
                    c[0] = (c[0] * c[1] + p) / (c[1] + 1)
                    c[1] += 1
                    matched = True
                    break
            if not matched:
                clusters.append([float(p), 1])

        # Sortiere Cluster nach Pulslänge
        clusters.sort(key=lambda c: c[0])

        # 3. Basis-Takt (Clock / T0) identifizieren (nach getClock())
        # Der Basis-Takt ist der kürzeste Puls, der mit ausreichender Signifikanz vorkommt.
        # Bei Tri-State / Manchester typischerweise mind. 10-15% aller Pulse.
        min_count = max(2, int(len(valid_pulses) * 0.10))
        
        clock = None
        for c in clusters:
            if c[1] >= min_count and 120 <= c[0] <= 1200:
                clock = int(round(c[0]))
                break

        if not clock:
            # Fallback: Kürzester Cluster mit mind. 2 Vorkommen
            for c in clusters:
                if c[1] >= 2 and 120 <= c[0] <= 1500:
                    clock = int(round(c[0]))
                    break

        if not clock or clock < 80:
            return None

        # 4. Quantisiere alle Pulse in ganzzahlige Vielfache von clock
        multiples = []
        max_ratio = 1.0
        for p in valid_pulses:
            ratio = p / clock
            mult = max(1, int(round(ratio)))
            multiples.append(mult)
            if ratio > max_ratio:
                max_ratio = ratio

        return SignalPattern(
            clock=clock,
            multiples=multiples,
            sync_ratio=round(max_ratio, 1),
            raw_pulses=valid_pulses
        )
