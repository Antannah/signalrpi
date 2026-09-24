# pattern_decoder.py -- Mustererkennung & Takt-Extraktion nach SignalDUINO-Prinzip

class SignalPattern:
    """
    Repräsentiert ein nach SignalDUINO-Art geclustertes Signal (MS-Format):
    - patterns: Liste der geclusterten Pulslängen in µs (High positiv, Low negativ), z.B. [495, -1980, -4239, -9298]
    - data: Liste von Bin-Indizes entsprechend der zeitlichen Pulsfolge (z.B. [0, 3, 0, 1, ...])
    - clock: Basis-Takt in µs
    - clock_idx: Index des Takt-Bins (CP in SignalDUINO)
    - sync_idx: Index des Sync-/Pausen-Bins (SP in SignalDUINO)
    - multiples: Diskrete Vielfache von clock (für bestehende Decoder-Kompatibilität)
    - sync_ratio: Verhältnis des längsten Pulses/Pause zum Basis-Takt
    - raw_pulses: Ungefilterte/bereinigte Original-Pulsfolge in µs
    """
    def __init__(
        self,
        clock: int,
        multiples: list[int],
        sync_ratio: float,
        raw_pulses: list[int],
        patterns: list[int] | None = None,
        data: list[int] | None = None,
        clock_idx: int = 0,
        sync_idx: int = 0
    ):
        self.clock = clock
        self.multiples = multiples
        self.sync_ratio = sync_ratio
        self.raw_pulses = raw_pulses
        self.patterns = patterns or []
        self.data = data or []
        self.clock_idx = clock_idx
        self.sync_idx = sync_idx

    def to_ms_string(self) -> str:
        """
        Erzeugt den exakten SignalDUINO MS-String, z.B.:
        MS;P0=495;P1=-1980;P2=-4239;P3=-9298;D=030102...;CP=0;SP=3;R=37;
        """
        if not self.patterns or not self.data:
            return ""
        
        parts = ["MS"]
        for idx, val in enumerate(self.patterns):
            parts.append("P{}={}".format(idx, val))
            
        d_str = "".join(str(idx) for idx in self.data)
        parts.append("D={}".format(d_str))
        parts.append("CP={}".format(self.clock_idx))
        parts.append("SP={}".format(self.sync_idx))
        parts.append("R={}".format(len(self.data)))
        return ";".join(parts) + ";"

    def __len__(self):
        return len(self.raw_pulses)

    def __getitem__(self, idx):
        return self.raw_pulses[idx]

    def __iter__(self):
        return iter(self.raw_pulses)

    def __repr__(self):
        return f"<SignalPattern clock={self.clock}µs len={len(self.data)} patterns={len(self.patterns)} sync={self.sync_ratio:.1f}T>"


class PatternDecoder:
    """
    Analysiert rohe Pulsfolgen (µs-Dauern) und extrahiert den Basis-Takt (Clock)
    sowie die SignalDUINO-Cluster (P0..Pn) und die Symbolsequenz D.
    Basiert auf den Prinzipien des SignalDUINO signalDecoder.cpp / 00_SIGNALduino.pm.
    """

    @staticmethod
    def decode_pattern(pulses: list[int], tol_fact: float = 0.25) -> SignalPattern | None:
        """
        Nimmt eine Liste von Pulsen (µs) entgegen.
        Gerade Indizes (0, 2, 4...) sind High-Phasen (+),
        ungerade Indizes (1, 3, 5...) sind Low-Phasen (-).
        Gibt ein SignalPattern zurück oder None.
        """
        if not pulses or len(pulses) < 8:
            return None

        # 1. Vorzeichenbehaftete Phasenfolge bilden:
        # High = positiv, Low = negativ
        signed_pulses = []
        raw_clean = []
        for i, p in enumerate(pulses):
            try:
                val = int(p)
            except Exception:
                continue
            if val < 40 or val > 65000:
                continue  # Glitch-Filterung & Ausreißer
            raw_clean.append(val)
            signed_val = val if (len(raw_clean) % 2 == 1) else -val
            signed_pulses.append(signed_val)

        if len(signed_pulses) < 8:
            return None

        # 2. Clusterung (getrennte Cluster für High und Low)
        # Bins: Liste aus [avg_val, count]
        high_clusters = []
        low_clusters = []

        for sp in signed_pulses:
            val_abs = abs(sp)
            target_list = high_clusters if sp > 0 else low_clusters
            
            matched = False
            for c in target_list:
                avg = c[0]
                tol = avg * tol_fact
                if abs(val_abs - avg) <= tol:
                    c[0] = (c[0] * c[1] + val_abs) / (c[1] + 1)
                    c[1] += 1
                    matched = True
                    break
            if not matched:
                target_list.append([float(val_abs), 1])

        # Begrenzung auf signifikante Bins
        high_clusters.sort(key=lambda c: c[0])
        low_clusters.sort(key=lambda c: c[0])

        patterns = []  # Vorzeichenbehaftete Integer-Mittelwerte
        cluster_map = [] # (avg, tol, sign, bin_index)

        # High-Bins einfügen
        for c in high_clusters:
            bin_idx = len(patterns)
            avg_int = int(round(c[0]))
            patterns.append(avg_int)
            cluster_map.append((c[0], c[0] * tol_fact, 1, bin_idx))

        # Low-Bins einfügen (negativ)
        for c in low_clusters:
            bin_idx = len(patterns)
            avg_int = -int(round(c[0]))
            patterns.append(avg_int)
            cluster_map.append((c[0], c[0] * tol_fact, -1, bin_idx))

        if not patterns:
            return None

        # 3. Sequenz D bilden (Zuordnung jedes Pulses zum besten Bin)
        data_indices = []
        for sp in signed_pulses:
            sign = 1 if sp > 0 else -1
            val_abs = abs(sp)
            best_idx = None
            min_diff = 999999
            for avg, tol, c_sign, b_idx in cluster_map:
                if c_sign == sign:
                    diff = abs(val_abs - avg)
                    if diff < min_diff:
                        min_diff = diff
                        best_idx = b_idx
            if best_idx is not None:
                data_indices.append(best_idx)
            else:
                data_indices.append(0)

        # 4. Basis-Takt (Clock) und Clock-Index (CP) ermitteln
        min_high_count = max(2, int(len(signed_pulses) * 0.08))
        clock = None
        clock_idx = 0

        for i, p_val in enumerate(patterns):
            if p_val > 0:  # High
                cnt = data_indices.count(i)
                if cnt >= min_high_count and 120 <= p_val <= 1200:
                    clock = p_val
                    clock_idx = i
                    break

        if not clock:
            for i, p_val in enumerate(patterns):
                if p_val > 0 and p_val >= 80:
                    clock = p_val
                    clock_idx = i
                    break

        if not clock or clock < 60:
            clock = 350
            clock_idx = 0

        # 5. Sync-Index (SP) ermitteln
        sync_idx = 0
        max_pause = 0
        for i, p_val in enumerate(patterns):
            if p_val < 0 and abs(p_val) > max_pause:
                max_pause = abs(p_val)
                sync_idx = i

        sync_ratio = round(max_pause / clock, 1) if clock else 1.0

        # 6. Multiples für Kompatibilität mit bestehenden Decodern
        multiples = []
        for p in raw_clean:
            ratio = p / clock
            multiples.append(max(1, int(round(ratio))))

        return SignalPattern(
            clock=clock,
            multiples=multiples,
            sync_ratio=sync_ratio,
            raw_pulses=raw_clean,
            patterns=patterns,
            data=data_indices,
            clock_idx=clock_idx,
            sync_idx=sync_idx
        )
