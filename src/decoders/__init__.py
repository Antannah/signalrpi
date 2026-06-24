# decoders/__init__.py -- Parser-Registry

from .sd_ws07 import DecoderWS07

DECODERS = [
    DecoderWS07(),
]

def decode_signal(pulse_width_sequence):
    for decoder in DECODERS:
        result = decoder.decode(pulse_width_sequence)
        if result:
            return result
    return None
