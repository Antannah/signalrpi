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
CC1101_FSCAL3   = 0x23  # Frequency Synthesizer Calibration
CC1101_FSCAL2   = 0x24  # Frequency Synthesizer Calibration
CC1101_FSCAL1   = 0x25  # Frequency Synthesizer Calibration
CC1101_FSCAL0   = 0x26  # Frequency Synthesizer Calibration

# CC1101 Status Registers (Read-only, require ORing with 0xC0)
CC1101_RSSI     = 0x34  # Received Signal Strength Indicator
CC1101_MARSTATE = 0x35  # Main Radio Control State Machine State

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
        
        # CSn ist active low -> mit High initialisieren
        self.cs_pin.init(mode=Pin.OUT, value=1)
        self.gdo0_pin.init(mode=Pin.IN)

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
        
        # 7. Aktiviere den Empfänger
        self.enable_rx()

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
