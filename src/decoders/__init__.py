# decoders/__init__.py -- Parser-Registry für OOK- und FSK-Protokolle

from .cul_tcm97001 import DecoderTCM97001
from .sd_ws_ook import DecoderWSOOK
from .sd_ws_fsk import DecoderWSFSK

# OOK-Decoder (Puls-Pausen-Folgen)
DECODERS_OOK = [
    DecoderTCM97001(),
    DecoderWSOOK(),
]

# FSK-Decoder (Byte-Pakete)
DECODERS_FSK = [
    DecoderWSFSK(),
]

def decode_ook_signal(pulse_width_sequence: list) -> dict | None:
    """
    Versucht, eine Puls-Pausen-Folge mit allen registrierten OOK-Decodern zu interpretieren.
    """
    for decoder in DECODERS_OOK:
        try:
            result = decoder.decode(pulse_width_sequence)
            if result:
                return result
        except Exception as e:
            # Tolerantes Fehlverhalten bei Parser-Fehlern
            print("Fehler im OOK-Decoder {}: {}".format(decoder.name, e))
    return None

def decode_fsk_packet(packet_bytes: bytes) -> dict | None:
    """
    Versucht, ein rohes FSK-Byte-Paket mit allen registrierten FSK-Decodern zu interpretieren.
    """
    for decoder in DECODERS_FSK:
        try:
            result = decoder.decode(packet_bytes)
            if result:
                return result
        except Exception as e:
            print("Fehler im FSK-Decoder {}: {}".format(decoder.name, e))
    return None

# Abwärtskompatibilität für das Hauptprogramm
def decode_signal(pulse_width_sequence: list) -> dict | None:
    return decode_ook_signal(pulse_width_sequence)
