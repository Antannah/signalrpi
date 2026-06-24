# cc1101.py -- SPI-Treiber für CC1101-Module

class CC1101:
    def __init__(self, spi, cs_pin, gdo0_pin):
        self.spi = spi
        self.cs_pin = cs_pin
        self.gdo0_pin = gdo0_pin

    def init_rf(self, frequency):
        # Initialisierung der Register
        pass
