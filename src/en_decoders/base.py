# decoders/base.py -- Basisklasse für alle Protokoll-Decoder

class BaseDecoder:
    def __init__(self, name):
        self.name = name

    def decode(self, pulses):
        # Abstrakt: Muss von konkreten Decodern überschrieben werden.
        # Gibt ein Dictionary mit Sensordaten zurück oder None, wenn kein Match.
        raise NotImplementedError
