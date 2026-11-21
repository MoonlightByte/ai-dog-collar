"""Minimal CC1101 driver for 433.92 MHz OOK async capture/replay on a Raspberry Pi.

Wiring (SPI0/CE0): GDO0 -> GPIO25 (pin 22), GDO2 -> GPIO24 (pin 18).
"""
import time
import spidev

GDO0_GPIO = 25
GDO2_GPIO = 24

# Strobes
SRES, SCAL, SRX, STX, SIDLE, SFRX, SFTX = 0x30, 0x33, 0x34, 0x35, 0x36, 0x3A, 0x3B
PATABLE_ADDR = 0x3E

# 26 MHz crystal: FREQ = f * 2^16 / 26e6
def freq_regs(mhz):
    word = round(mhz * 1e6 * 65536 / 26e6)
    return (word >> 16) & 0xFF, (word >> 8) & 0xFF, word & 0xFF

def base_config(mhz=433.92, mod='ook', dev=0x47):
    f2, f1, f0 = freq_regs(mhz)
    return {
        0x00: 0x0E,  # IOCFG2: GDO2 = carrier sense
        0x02: 0x0D,  # IOCFG0: GDO0 = async serial data
        0x03: 0x47,  # FIFOTHR
        0x08: 0x32,  # PKTCTRL0: async serial mode, infinite length
        0x0B: 0x06,  # FSCTRL1: IF
        0x0D: f2, 0x0E: f1, 0x0F: f0,
        0x10: 0x57,  # MDMCFG4: RX BW ~325 kHz (tolerant of cheap remote drift)
        0x11: 0x93,  # MDMCFG3
        0x12: {'ook': 0x30, 'fsk': 0x00, 'gfsk': 0x10}[mod],  # MDMCFG2: modulation, no sync word
        0x15: dev,   # DEVIATN (FSK deviation; 0x47 = 47.6 kHz)
        0x13: 0x02,  # MDMCFG1
        0x18: 0x18,  # MCSM0: autocal IDLE->RX/TX
        0x19: 0x16,  # FOCCFG
        0x1B: 0x03,  # AGCCTRL2 (OOK recommended)
        0x1C: 0x00,  # AGCCTRL1
        0x1D: 0x91,  # AGCCTRL0
        0x21: 0x56,  # FREND1
        0x22: 0x11 if mod == 'ook' else 0x10,  # FREND0: OOK uses PATABLE[0]/[1]; FSK uses [0]
        0x23: 0xE9, 0x24: 0x2A, 0x25: 0x00, 0x26: 0x1F,  # FSCAL3..0
        0x2C: 0x81, 0x2D: 0x35, 0x2E: 0x09,  # TEST2..0
    }

class CC1101:
    def __init__(self, bus=0, dev=0):
        self.spi = spidev.SpiDev()
        self.spi.open(bus, dev)
        self.spi.max_speed_hz = 1_000_000
        self.spi.mode = 0

    def strobe(self, cmd):
        self.spi.xfer2([cmd])

    def write(self, addr, val):
        self.spi.xfer2([addr, val])

    def read(self, addr):
        return self.spi.xfer2([0x80 | addr, 0])[1]

    def status(self, addr):
        return self.spi.xfer2([0xC0 | addr, 0])[1]

    def rssi_dbm(self):
        raw = self.status(0x34)
        if raw >= 128:
            raw -= 256
        return raw / 2 - 74

    def marcstate(self):
        return self.status(0x35) & 0x1F

    def setup(self, mhz=433.92, power=0xC0, mod='ook', dev=0x47):
        self.strobe(SRES)
        time.sleep(0.01)
        for addr, val in base_config(mhz, mod, dev).items():
            self.write(addr, val)
        # PATABLE burst: OOK [off, on]; FSK [on]
        table = [0x00, power] if mod == 'ook' else [power]
        self.spi.xfer2([0x40 | PATABLE_ADDR] + table)
        self.strobe(SIDLE)
        self.strobe(SCAL)
        time.sleep(0.005)

    def rx(self):
        self.strobe(SIDLE)
        self.strobe(SFRX)
        self.strobe(SRX)

    def tx(self):
        self.strobe(SIDLE)
        self.strobe(STX)

    def idle(self):
        self.strobe(SIDLE)

    def close(self):
        self.idle()
        self.spi.close()
