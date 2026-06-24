# pio_receiver.py -- PIO-Zustandsmaschine & DMA-Setup

import rp2
from machine import Pin

@rp2.asm_pio(
    autopush=False,
    in_shiftdir=rp2.PIO.SHIFT_LEFT,
)
def pulse_timer():
    # 1. Einmalige Initialisierung: Lese Timeout-Wert von der CPU (z. B. 5000 µs)
    pull()
    mov(y, osr)              # Y speichert das Limit (z. B. 5000)
    
    wrap_target()
    
    # ---- 1. HIGH-PHASE MESSEN (wartet auf Übergang zu Low) ----
    # Wir zählen rückwärts von 0xFFFFFFFF (kein Timeout für High nötig)
    mov(x, invert(null))
    
    label("high_loop")
    jmp(pin, "high_count")   # Pin ist High -> weiterzählen
    jmp("high_done")         # Pin ist Low -> Phase beendet
    label("high_count")
    jmp(x_dec, "high_loop")  # Dekrementiere X und loope (2 Zyklen pro Schleife)
    
    label("high_done")
    mov(isr, invert(x))      # Dauer = 0xFFFFFFFF - X
    push()                   # Schicke Dauer der High-Phase an die CPU
    
    # ---- 2. LOW-PHASE MESSEN (mit Timeout) ----
    mov(x, y)                # Lade Timeout (z. B. 5000) in den Zähler X
    
    label("low_loop")
    jmp(pin, "low_done")     # Pin ist High -> Phase beendet, neuer Puls startet
    jmp(x_dec, "low_loop")   # Pin ist Low -> Dekrementiere X (2 Zyklen pro Schleife)
    
    # Wenn wir hier ankommen, ist X = 0 (Timeout erreicht -> Paketende)
    mov(isr, null)           # Sende 0 als Timeout-Marker an die CPU
    push()
    
    # Warte, bis der Pin wieder High wird, um sauber mit der nächsten High-Phase zu synchronisieren
    label("wait_high")
    jmp(pin, "sync_done")
    jmp("wait_high")
    label("sync_done")
    jmp("wrap_start")        # Gehe direkt zum Start der nächsten High-Phase (da Pin jetzt High ist)
    
    label("low_done")
    # Da wir in PIO nicht direkt subtrahieren können, schicken wir den aktuellen Wert von X.
    # Die CPU berechnet dann: Dauer = Timeout - X
    mov(isr, x)
    push()
    
    label("wrap_start")
    wrap_end()


class PIOReceiver:
    def __init__(self, sm_id: int, pin_num: int, pause_threshold_us: int = 5000, min_pulses: int = 8):
        """
        Initialisiert den PIO-Empfänger für Pulse-Pause-Modulationen.
        
        :param sm_id: ID der State Machine (0-7).
        :param pin_num: GPIO-Pin-Nummer (GDO0 des CC1101).
        :param pause_threshold_us: Schwellwert in µs für die Paketabgrenzung (Timeout).
        :param min_pulses: Mindestanzahl an Pulsen, damit ein Paket als valide gilt (Rauschfilter).
        """
        self.pin = Pin(pin_num, Pin.IN)
        self.pause_threshold = pause_threshold_us
        self.min_pulses = min_pulses
        
        # Initialisierung der State Machine mit 2 MHz Takt
        # Jede Schleife im PIO-Code dauert exakt 2 Taktzyklen -> 1 Zähler = 1 µs Auflösung
        self.sm = rp2.StateMachine(
            sm_id,
            pulse_timer,
            freq=2_000_000,
            jmp_pin=self.pin
        )
        
        # Starte die State Machine und sende das Timeout-Limit über die TX-FIFO
        self.sm.active(1)
        self.sm.put(self.pause_threshold)
        
        self.pulse_buffer = []
        self.expect_high = True  # Der erste empfangene Wert ist immer eine High-Phase

    def get_packet(self) -> list:
        """
        Liest Daten aus der RX-FIFO und rekonstruiert die Puls-Pausen-Zeiten.
        Gibt eine Liste von Zeiten in µs zurück, sobald ein Paket abgeschlossen ist,
        ansonsten None.
        """
        while self.sm.rx_fifo() > 0:
            val = self.sm.get()
            
            if self.expect_high:
                # High-Phase: Direktwert
                # Glitch-Filter: Ignoriere extrem kurze Störimpulse (z.B. < 30 µs) zu Beginn eines Pakets
                if val < 30 and len(self.pulse_buffer) == 0:
                    self.expect_high = True  # Erwarte weiterhin den ersten echten High-Puls
                    continue
                
                self.pulse_buffer.append(val)
                self.expect_high = False
            else:
                # Low-Phase: Wert ist der Restzähler X
                self.expect_high = True
                
                if val == 0:
                    # Timeout erreicht -> Paketende signalisiert!
                    # Hänge die Timeout-Pause an das Paket an
                    self.pulse_buffer.append(self.pause_threshold)
                    
                    packet = None
                    if len(self.pulse_buffer) >= self.min_pulses:
                        packet = self.pulse_buffer[:]
                    
                    self.pulse_buffer.clear()
                    return packet
                else:
                    # Normaler Übergang: Berechne Dauer = Timeout - X
                    duration = self.pause_threshold - val
                    self.pulse_buffer.append(duration)
                    
        return None
