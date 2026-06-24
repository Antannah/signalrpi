# pio_receiver.py -- PIO-Zustandsmaschine & DMA-Setup

import rp2

@rp2.asm_pio(autopush=True, push_thresh=32)
def pulse_counter():
    # PIO Programm zur Zeitmessung der Pulsweiten
    pass
