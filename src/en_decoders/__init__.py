# en_decoders/__init__.py -- Parser- & Encoder-Registry für OOK- und FSK-Protokolle

from .tcm97001 import DecoderTCM97001
from .sd_ws07 import DecoderWS07
from .sd_ws_ook import DecoderWSOOK
from .sd_ws_fsk import DecoderWSFSK
from .intertechno import DecoderIntertechno
from .pattern_decoder import PatternDecoder, SignalPattern
from .it_encoder import ITEncoder

# OOK-Decoder (Puls-Pausen-Folgen & SignalPatterns)
DECODERS_OOK = [
    DecoderIntertechno(),
    DecoderTCM97001(),
    DecoderWS07(),
    DecoderWSOOK(),
]

# FSK-Decoder (Byte-Pakete)
DECODERS_FSK = [
    DecoderWSFSK(),
]

def decode_ook_signal(pulse_width_sequence: list) -> dict | None:
    """
    Versucht, eine Puls-Pausen-Folge mit allen registrierten OOK-Decodern zu interpretieren.
    Extrahiert vorab das SignalPattern (Basis-Takt und Vielfache) nach SignalDUINO-Art.
    """
    # 1. Voranalyse: Muster und Takt bestimmen
    pattern = None
    try:
        pattern = PatternDecoder.decode_pattern(pulse_width_sequence)
    except Exception as e:
        print("Musterdecoder Fehler:", e)

    if not pattern:
        return None

    # 2. Pipeline der Protokoll-Decoder durchlaufen
    for decoder in DECODERS_OOK:
        try:
            result = decoder.decode(pattern)
            if result:
                if "ms_string" not in result:
                    result["ms_string"] = pattern.to_ms_string()
                return result
        except Exception as e:
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
