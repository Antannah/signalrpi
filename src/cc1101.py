# cc1101.py -- SPI-Treiber für CC1101-Module

import time
from machine import SPI, Pin

# CC1101 Strobe Commands
CC1101_SRES    = 0x30  # Reset chip
CC1101_SFSTXON = 0x31  # Enable calibration and write status
CC1101_SXOFF   = 0x32  # Turn off crystal oscillator
CC1101_SCAL    = 0x33  # Calibrate frequency synthesizer and turn it off
CC1101_SRX     = 0x34  # Enable RX
CC1101_STX     = 0x35  # Enable TX
CC1101_SIDLE   = 0x36  # Exit RX / TX, turn off frequency synthesizer
CC1101_SFRX    = 0x3A  # Flush RX FIFO
CC1101_SFTX    = 0x3B  # Flush TX FIFO

# CC1101 Register Addresses
CC1101_IOCFG2   = 0x00  # GDO2 Output Pin Configuration
CC1101_IOCFG0   = 0x02  # GDO0 Output Pin Configuration
CC1101_FIFOTHR  = 0x03  # RX FIFO and TX FIFO Thresholds
CC1101_PKTCTRL1 = 0x07  # Packet Automation Control
CC1101_PKTCTRL0 = 0x08  # Packet Automation Control
CC1101_ADDR     = 0x09  # Device Address
CC1101_FSCTRL1  = 0x0B  # Frequency Synthesizer Control
CC1101_FREQ2    = 0x0D  # Frequency Control Word, High Byte
CC1101_FREQ1    = 0x0E  # Frequency Control Word, Middle Byte
CC1101_FREQ0    = 0x0F  # Frequency Control Word, Low Byte
CC1101_MDMCFG4  = 0x10  # Modem Configuration
CC1101_MDMCFG3  = 0x11  # Modem Configuration
CC1101_MDMCFG2  = 0x12  # Modem Configuration
CC1101_MCSM0    = 0x18  # Main Radio Control State Machine Configuration
CC1101_FOCCFG   = 0x19  # Frequency Offset Compensation Configuration
CC1101_BSCFG    = 0x1A  # Bit Synchronization Configuration
CC1101_AGCCTRL2 = 0x1B  # AGC Control
CC1101_AGCCTRL1 = 0x1C  # AGC Control
CC1101_AGCCTRL0 = 0x1D  # AGC Control
CC1101_FREND0   = 0x22  # Front End TX Configuration
CC1101_FSCAL3   = 0x23  # Frequency Synthesizer Calibration
CC1101_FSCAL2   = 0x24  # Frequency Synthesizer Calibration
CC1101_FSCAL1   = 0x25  # Frequency Synthesizer Calibration
CC1101_FSCAL0   = 0x26  # Frequency Synthesizer Calibration
CC1101_PATABLE  = 0x3E  # PA Table Control (8 Bytes)

# CC1101 Status Registers (Read-only, require ORing with 0xC0)
CC1101_PARTNUM  = 0x30  # Chip part number (expected 0x00)
CC1101_VERSION  = 0x31  # Chip version (expected 0x04 or 0x14)
CC1101_FREQEST  = 0x32  # Frequency Offset Estimate
CC1101_LQI      = 0x33  # Demodulator estimate for Link Quality
CC1101_RSSI     = 0x34  # Received Signal Strength Indicator
CC1101_MARSTATE = 0x35  # Main Radio Control State Machine State
CC1101_PKTSTATUS= 0x38  # Current GDOx status and packet status
CC1101_RXBYTES  = 0x3B  # Underflow and number of bytes in RX FIFO
CC1101_TXBYTES  = 0x3C  # Overflow and number of bytes in TX FIFO

STATE_NAMES = {
    0: "IDLE",
    1: "RX",
    2: "TX",
    3: "FSTXON",
    4: "CALIBRATE",
    5: "SETTLING",
    6: "RX_FIFO_ERROR",
    7: "TX_FIFO_ERROR",
    13: "RX (Active)",
    14: "RX (Active)",
    15: "RX (Active)",
    19: "TX (Active)",
    20: "TX_END"
}

class CC1101:
    def __init__(self, spi: SPI, cs_pin: Pin, gdo0_pin: Pin):
        """
        Initialisiert den CC1101-Treiber.
        :param spi: Ein initialisiertes machine.SPI-Objekt.
        :param cs_pin: Ein machine.Pin-Objekt für Chip Select (Output).
        :param gdo0_pin: Ein machine.Pin-Objekt für den GDO0-Datenausgang (Input).
        """
        self.spi = spi
        self.cs_pin = cs_pin
        self.gdo0_pin = gdo0_pin
        self.carrier_freq = 0.0
        self.mode = "NONE"
        self.last_check = {"ok": False, "msg": "Nicht initialisiert"}
        
        # CSn ist active low -> mit High initialisieren
        self.cs_pin.init(mode=Pin.OUT, value=1)
        self.gdo0_pin.init(mode=Pin.IN)

    def check_hardware(self) -> dict:
        """
        Führt einen Hardware-Selbsttest über SPI durch.
        Liest PARTNUM, VERSION und aktuellen Zustand (MARSTATE) aus.
        """
        try:
            partnum = self._read_status(CC1101_PARTNUM)
            version = self._read_status(CC1101_VERSION)
            marstate = self._read_status(CC1101_MARSTATE) & 0x1F
            state_str = STATE_NAMES.get(marstate, f"STATE_{marstate}")
            
            # Ein echter CC1101 antwortet mit PARTNUM=0x00 und VERSION=0x04 oder 0x14
            is_valid = (partnum == 0x00 and version in [0x04, 0x14, 0x03, 0x05])
            if is_valid:
                msg = f"OK (v0x{version:02X}, State: {state_str})"
            else:
                msg = f"FEHLER: Ungültige Antwort (Part=0x{partnum:02X}, Ver=0x{version:02X})"
                
            self.last_check = {
                "ok": is_valid,
                "partnum": partnum,
                "version": version,
                "state_code": marstate,
                "state_name": state_str,
                "freq": self.carrier_freq,
                "mode": self.mode,
                "msg": msg
            }
            return self.last_check
        except Exception as ex:
            self.last_check = {"ok": False, "msg": f"SPI-Ausnahme: {ex}"}
            return self.last_check

    def _write_reg(self, reg: int, val: int) -> None:
        """Schreibt einen Wert in ein CC1101-Register."""
        self.cs_pin.value(0)
        # MSB=0 (Write), Burst=0 (Single Access)
        cmd = bytearray([reg & 0x3F, val & 0xFF])
        self.spi.write(cmd)
        self.cs_pin.value(1)

    def _read_reg(self, reg: int) -> int:
        """Liest den Wert eines CC1101-Registers."""
        self.cs_pin.value(0)
        # MSB=1 (Read), Burst=0 (Single Access)
        cmd = bytearray([reg | 0x80])
        self.spi.write(cmd)
        val = self.spi.read(1)[0]
        self.cs_pin.value(1)
        return val

    def _read_status(self, reg: int) -> int:
        """Liest den Wert eines CC1101-Statusregisters (erfordert Burst-Bit 0x40 und Read-Bit 0x80)."""
        self.cs_pin.value(0)
        cmd = bytearray([reg | 0xC0])
        self.spi.write(cmd)
        val = self.spi.read(1)[0]
        self.cs_pin.value(1)
        return val

    def _write_strobe(self, cmd: int) -> None:
        """Sendet ein Strobe-Kommando (Zustandsänderung) an den CC1101."""
        self.cs_pin.value(0)
        self.spi.write(bytearray([cmd & 0xFF]))
        self.cs_pin.value(1)

    def reset(self) -> None:
        """Führt einen Hardware-Reset des CC1101-Chips aus."""
        self.cs_pin.value(1)
        time.sleep_us(5)
        self.cs_pin.value(0)
        time.sleep_us(10)
        self.cs_pin.value(1)
        time.sleep_us(45)
        
        self._write_strobe(CC1101_SRES)
        time.sleep_ms(10)  # Warte auf Initialisierung des Oszillators
        self._write_strobe(CC1101_SIDLE)

    def set_carrier_frequency(self, freq_mhz: float) -> None:
        """
        Berechnet und setzt die Trägerfrequenz des Synthesizers.
        Formel: f_carrier = (f_osc / 2^16) * FREQ[21..0]
        Mit f_osc = 26 MHz Standardquarz.
        """
        f_osc = 26.0 * 1000000.0  # 26 MHz
        freq_hz = freq_mhz * 1000000.0
        
        freq_word = int((freq_hz * 65536.0) / f_osc)
        
        freq2 = (freq_word >> 16) & 0xFF
        freq1 = (freq_word >> 8) & 0xFF
        freq0 = freq_word & 0xFF
        
        self._write_reg(CC1101_FREQ2, freq2)
        self._write_reg(CC1101_FREQ1, freq1)
        self._write_reg(CC1101_FREQ0, freq0)

    def init_ask_ook(self, freq_mhz: float) -> None:
        """
        Konfiguriert den CC1101 in den Continuous RX Modus (ASK/OOK Modulation).
        Der demodulierte Bitstrom wird direkt auf dem GDO0-Pin ausgegeben.
        """
        self.carrier_freq = freq_mhz
        self.mode = "ASK/OOK"
        self.reset()
        
        # 1. Trägerfrequenz einstellen
        self.set_carrier_frequency(freq_mhz)
        
        # 2. Pin-Konfiguration: GDO0 auf Serial Data Out (continuous mode)
        # Wert 0x0D bedeutet: Serial Data Output
        self._write_reg(CC1101_IOCFG0, 0x0D)
        self._write_reg(CC1101_IOCFG2, 0x2E)  # GDO2 auf Tri-state (nicht genutzt)
        
        # 3. Paket-Konfiguration: Asynchroner serieller Modus, unendliche Paketlänge
        # Wert 0x32: Format = 3 (Serial Modus), Length Config = 2 (Infinite packet length)
        self._write_reg(CC1101_PKTCTRL0, 0x32)
        self._write_reg(CC1101_PKTCTRL1, 0x00)  # Keine Adressprüfung, kein Status-Append
        
        # 4. Modulationsart und AGC-Einstellungen für ASK/OOK (typisch für Heimautomation)
        # MDMCFG2: 0x30 -> ASK/OOK Modulation, keine Manchestercodierung
        self._write_reg(CC1101_MDMCFG2, 0x30)
        
        # FSCTRL1: Frequenzsynthesizer-Steuerung (ZF = 152 kHz)
        self._write_reg(CC1101_FSCTRL1, 0x06)
        
        # MDMCFG4: Filterbandbreite des Empfängers auf ca. 325 kHz einstellen (OOK-Toleranz)
        # Wert 0x87 ist ein bewährter Standard für SignalDUINO
        self._write_reg(CC1101_MDMCFG4, 0x87)
        self._write_reg(CC1101_MDMCFG3, 0xF8)  # Symbolrate (nicht genutzt im serial mode, aber initialisiert)
        
        # 5. Kalibrierungs- und AGC-Optimierungen für OOK
        self._write_reg(CC1101_MCSM0, 0x18)     # Automatische Kalibrierung beim Übergang von IDLE zu RX/TX
        self._write_reg(CC1101_FIFOTHR, 0x07)   # FIFO Schwellwert
        self._write_reg(CC1101_FOCCFG, 0x16)    # Frequenzoffset-Kompensation
        self._write_reg(CC1101_BSCFG, 0x6C)     # Bitsynchronisation
        
        # AGC-Steuerung optimieren für ASK/OOK (Rauschanpassung)
        self._write_reg(CC1101_AGCCTRL2, 0x03)  # Maximale Verstärkung
        self._write_reg(CC1101_AGCCTRL1, 0x40)
        self._write_reg(CC1101_AGCCTRL0, 0x91)  # AGC Hysterese und Filterung
        
        # 6. Kalibrierungsdaten schreiben (CC1101 spezifisch)
        self._write_reg(CC1101_FSCAL3, 0xE9)
        self._write_reg(CC1101_FSCAL2, 0x2A)
        self._write_reg(CC1101_FSCAL1, 0x00)
        self._write_reg(CC1101_FSCAL0, 0x1F)
        
        # 7. Sendeleistung für ASK/OOK konfigurieren:
        # Für ASK/OOK wählt FREND0 PA_POWER=1 (Index 1 der PATABLE für High, Index 0 für Low/0x00).
        # PATABLE Index 0 = 0x00 (Sender aus bei Low), Index 1 = 0xC0 (+10 dBm Sendeleistung bei High).
        self._write_reg(CC1101_FREND0, 0x11)
        self.set_pa_table(bytearray([0x00, 0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]))
        
        # 8. Aktiviere den Empfänger
        self.enable_rx()

    def set_pa_table(self, patable: bytearray) -> None:
        """Schreibt die 8-Byte Sendeleistungs-Tabelle (PATABLE)."""
        self.cs_pin.value(0)
        # MSB=0 (Write), Burst=1 (0x40) -> 0x7E
        self.spi.write(bytearray([CC1101_PATABLE | 0x40]))
        self.spi.write(patable)
        self.cs_pin.value(1)

    def enable_rx(self) -> None:
        """Versetzt den CC1101 in den Empfangsmodus (RX)."""
        self._write_strobe(CC1101_SIDLE)
        self._write_strobe(CC1101_SFRX)  # Flush RX FIFO
        self._write_strobe(CC1101_SRX)
        
        # Warte kurz, bis der Chip im RX-Zustand ist
        # State 13 = RX
        timeout = 100
        while timeout > 0:
            state = self._read_status(CC1101_MARSTATE) & 0x1F
            if state == 13:
                break
            time.sleep_us(10)
            timeout -= 1
        else:
            print("Warnung: CC1101 konnte nicht in den RX-Zustand versetzt werden. State:", state)

    def transmit_ook_pulses(self, gdo0_pin, pulse_seq: list, repetitions: int = 6) -> None:
        """
        Sendet eine Folge von High/Low-Mikrosekunden-Pulsen (OOK) über den CC1101.
        Schaltet kurzzeitig auf TX (GDO0 als Eingang des CC1101, Ausgang des Pico),
        taktet das Signal mit der angegebenen Anzahl an Wiederholungen (repetitions)
        in die Luft und schaltet danach nahtlos wieder auf Continuous-RX zurück.
        """
        import machine
        
        # 1. CC1101 in IDLE versetzen
        self._write_strobe(CC1101_SIDLE)
        self._write_strobe(CC1101_SFTX)
        
        # 2. GDO0 auf asynchronen Serial Data Input (TX) konfigurieren (0x2D = Invert off, Serial Data In)
        self._write_reg(CC1101_IOCFG0, 0x2D)
        
        # 3. Den Pico-GPIO temporär als Ausgang schalten (Start mit Low)
        gdo0_pin.init(mode=Pin.OUT, value=0)
        
        # 4. CC1101 in den TX-Modus schalten und auf Synthesizer-Lock warten
        self._write_strobe(CC1101_STX)
        timeout = 100
        while timeout > 0:
            state = self._read_status(CC1101_MARSTATE) & 0x1F
            if state in [19, 20]:  # 19=TX, 20=TX_END
                break
            time.sleep_us(10)
            timeout -= 1
        
        # 5. Pulssignal mit der gewünschten Anzahl an Wiederholungen aussenden
        for _ in range(repetitions):
            high = True
            for dur in pulse_seq:
                gdo0_pin.value(1 if high else 0)
                time.sleep_us(dur)
                high = not high
            gdo0_pin.value(0)
            
        # 6. TX beenden & zurück in IDLE
        self._write_strobe(CC1101_SIDLE)
        
        # 7. GDO0 wieder als Ausgang für demodulierte RX-Daten (0x0D = Serial Data Out)
        self._write_reg(CC1101_IOCFG0, 0x0D)
        
        # 8. Pico-GPIO wieder als Eingang schalten
        gdo0_pin.init(mode=Pin.IN)
        
        # 9. Zurück in den Empfangsmodus (RX)
        self.enable_rx()

    def get_rssi(self) -> float:
        """
        Liest den aktuellen RSSI-Wert (Signalstärke in dBm) aus.
        Formel laut Datenblatt: RSSI_dbm = RSSI_dec / 2 - 74 (für 26 MHz OSC)
        Wenn RSSI_dec >= 128: RSSI_dbm = (RSSI_dec - 256) / 2 - 74
        """
        rssi_dec = self._read_status(CC1101_RSSI)
        if rssi_dec >= 128:
            rssi_dbm = (rssi_dec - 256) / 2.0 - 74.0
        else:
            rssi_dbm = (rssi_dec / 2.0) - 74.0
        return rssi_dbm

    def init_fsk_packet(self, freq_mhz: float) -> None:
        """
        Konfiguriert den CC1101 in den 2-FSK Paket-Empfangsmodus.
        Die Demodulation und Rahmenerkennung (Sync-Word 2DD4) erfolgen in Hardware.
        Der fertige Paketstrom wird über die SPI-Schnittstelle ausgelesen.
        """
        self.carrier_freq = freq_mhz
        self.mode = "2-FSK (Sync 2DD4)"
        self.reset()
        
        # 1. Trägerfrequenz einstellen
        self.set_carrier_frequency(freq_mhz)
        
        # 2. Registerkonfiguration für FSK-Paketmodus
        # Parameter gemäß FHEM/SignalDUINO Referenz:
        # Freq: 868.350 MHz, BW: 135 kHz (MDMCFG4=0x5A), Drate: 17.26 kBaud (MDMCFG3=0x5C), Deviation: 34.91 kHz (DEVIATN=0x42)
        fsk_regs = {
            CC1101_IOCFG2:   0x2E,  # GDO2 auf Tri-state (nicht genutzt)
            CC1101_IOCFG0:   0x06,  # GDO0: Asserts on sync word, deasserts at end of packet (Active High)
            CC1101_FIFOTHR:  0x07,  # RX FIFO Threshold = 32 Bytes
            CC1101_PKTCTRL1: 0x04,  # Append status bytes RSSI/LQI at the end of packet (Bit 2 = 1)
            CC1101_PKTCTRL0: 0x00,  # Fixed packet length mode
            0x06:            0x0E,  # PKTLEN (Packet Length) = 14 Bytes
            CC1101_MDMCFG4:  0x89,  # Bandwidth = ca. 200 kHz (CHANBW_E=2, CHANBW_M=0) -> fängt Quarzdrift der Sender ab
            CC1101_MDMCFG3:  0x5C,  # Symbol rate = 17.26 kBaud
            CC1101_MDMCFG2:  0x12,  # 2-FSK, 16/16 sync word bits (2DD4) + CARRIER SENSE (nur Träger > -90 dBm)
            0x13:            0x22,  # MDMCFG1: 2 preamble bytes, no channel spacing
            0x14:            0xF8,  # MDMCFG0: Channel spacing
            0x15:            0x42,  # DEVIATN = 34.91 kHz
            CC1101_FSCTRL1:  0x06,  # IF = 6 * 26MHz / 1024 = 152 kHz (SIGNALduino-Standard fuer 868 MHz FSK)
            CC1101_MCSM0:    0x18,  # Autocalibrate on IDLE -> RX/TX
            CC1101_FOCCFG:   0x16,  # Frequency Offset Compensation
            CC1101_BSCFG:    0x6C,  # Bit Synchronization
            CC1101_AGCCTRL2: 0x43,  # AGC: rAmpl=33 dB, max LNA gain (sduinoESP Fine_Offset_WH51_868)
            CC1101_AGCCTRL1: 0x68,  # AGC: sens=8 dB, LNA-Prioritaet (sduinoESP Fine_Offset_WH51_868)
            CC1101_AGCCTRL0: 0x91,  # AGC: mittlere Hysterese, 16 Samples
            # Calibration
            CC1101_FSCAL3:   0xE9,
            CC1101_FSCAL2:   0x2A,
            CC1101_FSCAL1:   0x00,
            CC1101_FSCAL0:   0x1F,
        }
        
        # Write all registers
        for reg, val in fsk_regs.items():
            self._write_reg(reg, val)
            
        # Write Sync Word registers (address 0x04 = 0x2D, address 0x05 = 0xD4)
        self._write_reg(0x04, 0x2D)
        self._write_reg(0x05, 0xD4)
        
        self.enable_rx()

    def get_radio_state(self) -> int:
        """Gibt den internen Zustand der Radio State Machine zurück (13 = RX)."""
        try:
            return self._read_status(CC1101_MARSTATE) & 0x1F
        except Exception:
            return -1

    def read_fsk_packet(self) -> bytearray | None:
        """
        Liest ein FSK-Paket aus dem CC1101-FIFO, falls verfügbar.
        Gibt das Byte-Array zurück (16 Bytes: 14 Bytes Daten + 2 Bytes RSSI/LQI Status),
        oder None, wenn kein Paket bereitsteht.
        """
        # Statusregister RXBYTES (0x3B) auslesen
        rxbytes = self._read_status(0x3B)
        
        # Falls FIFO Overflow (Bit 7 gesetzt), löschen und neu starten
        if rxbytes & 0x80:
            self._write_strobe(CC1101_SIDLE)
            self._write_strobe(CC1101_SFRX)
            self._write_strobe(CC1101_SRX)
            return None
            
        num_bytes = rxbytes & 0x7F
        # Wir erwarten 16 Bytes (14 Bytes Payload + 2 Bytes RSSI/LQI)
        if num_bytes >= 16:
            self.cs_pin.value(0)
            self.spi.write(bytearray([0xFF]))  # Burst read ab FIFO (0x3F | 0xC0 = 0xFF)
            packet = self.spi.read(16)
            self.cs_pin.value(1)
            
            # Restart RX to clear any remaining bytes and prepare for next packet
            self._write_strobe(CC1101_SIDLE)
            self._write_strobe(CC1101_SFRX)
            self._write_strobe(CC1101_SRX)
            
            return packet
            
        return None

