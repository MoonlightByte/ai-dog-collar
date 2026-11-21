#!/usr/bin/env python3
"""Check that the CC1101 answers over SPI (bus 0, CE0)."""
import time
import spidev

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 500_000
spi.mode = 0

def strobe(cmd):
    return spi.xfer2([cmd])[0]

def read_status(addr):
    # status registers need the burst bit set: 0xC0 | addr
    return spi.xfer2([0xC0 | addr, 0x00])[1]

strobe(0x30)  # SRES: reset chip
time.sleep(0.01)

partnum = read_status(0x30)
version = read_status(0x31)
marcstate = read_status(0x35) & 0x1F
print(f"PARTNUM  = 0x{partnum:02X}  (expect 0x00)")
print(f"VERSION  = 0x{version:02X}  (expect 0x14, some clones 0x04)")
print(f"MARCSTATE= 0x{marcstate:02X}  (0x01 = IDLE)")

if partnum == 0x00 and version in (0x14, 0x04, 0x17):
    print("RESULT: CC1101 detected - wiring is good")
elif version in (0x00, 0xFF):
    print("RESULT: no response - check VCC/GND/MISO/CSN wiring")
else:
    print("RESULT: unexpected values - check wiring, send this output to Claude")
spi.close()
