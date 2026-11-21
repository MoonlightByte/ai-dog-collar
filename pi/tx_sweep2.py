#!/usr/bin/env python3
"""Sweep FSK deviation (and optionally polarity) at a fixed frequency.
Fixes GDO0 to hi-Z (0x2E) during TX so only our wave drives the modulator.

Usage: python3 tx_sweep2.py [freq_mhz] [invert]
"""
import sys
import time

import lgpio

from cc1101 import CC1101, GDO0_GPIO, SIDLE, STX

TEMPLATE = "0010101010101010101110100101001010000XXXX11000100010000001000001010001101000000010011XXXX00000000"
HIGH_US, ZERO_US, ONE_US, GAP_US = 206, 206, 407, 1207
MASK = 1 << 0

mhz    = float(sys.argv[1]) if len(sys.argv) > 1 else 433.92
invert = int(sys.argv[2]) if len(sys.argv) > 2 else 0
SPACING = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
_devcsv = sys.argv[4] if len(sys.argv) > 4 else ""
_LBL = {0x03:"~1kHz",0x05:"~1.5kHz",0x08:"~2kHz",0x0A:"~2.5kHz",0x10:"~3kHz",
        0x13:"~4kHz",0x15:"~5kHz",0x1A:"~6.5kHz",0x24:"~9.5kHz",0x34:"~19kHz",
        0x40:"~25kHz",0x47:"~47kHz"}
if _devcsv:
    DEVS = [(int(x,16), _LBL.get(int(x,16), f"0x{int(x,16):02X}")) for x in _devcsv.split(",")]
else:
    DEVS = [(0x05,"~1.5kHz"),(0x10,"~3kHz"),(0x15,"~5kHz"),(0x24,"~9.5kHz"),
            (0x34,"~19kHz"),(0x40,"~25kHz"),(0x47,"~47kHz")]
REPEATS = 6

def frame_bits(c):
    b = list(TEMPLATE)
    b[37:41] = list(format((c + 3) & 0xF, "04b"))
    b[85:89] = list(format(c & 0xF, "04b"))
    return "".join(b)

hi, lo = (0, MASK) if invert else (MASK, 0)

def pulses_for(frame):
    p = []
    for bit in frame:
        p.append(lgpio.pulse(hi, MASK, HIGH_US))
        p.append(lgpio.pulse(lo, MASK, ONE_US if bit == "1" else ZERO_US))
    p.append(lgpio.pulse(lo, MASK, GAP_US))
    return p

print(f"freq={mhz}  polarity={'inverted' if invert else 'normal'}  {len(DEVS)} bursts, {SPACING}s apart")
for i, (d, lbl) in enumerate(DEVS, 1):
    print(f"  #{i}  dev=0x{d:02X} {lbl}")

h = lgpio.gpiochip_open(0)
counter = 0
for i, (d, lbl) in enumerate(DEVS, 1):
    pulses = pulses_for(frame_bits(counter))
    counter = (counter + 1) & 0xF
    r = CC1101()
    r.setup(mhz, power=0xC0, mod="fsk", dev=d)
    r.write(0x02, 0x2E)          # IOCFG0 = hi-Z so only our GPIO drives GDO0
    r.strobe(SIDLE); r.strobe(STX); time.sleep(0.002)
    lgpio.group_claim_output(h, [GDO0_GPIO], [lo])
    t0 = time.monotonic()
    for _ in range(REPEATS):
        lgpio.tx_wave(h, GDO0_GPIO, pulses)
        while lgpio.tx_busy(h, GDO0_GPIO, lgpio.TX_WAVE):
            time.sleep(0.001)
    lgpio.group_write(h, GDO0_GPIO, lo, MASK)
    lgpio.group_free(h, GDO0_GPIO)
    r.strobe(SIDLE); r.close()
    print(f"  sent #{i} ({lbl})", flush=True)
    time.sleep(max(0, SPACING - (time.monotonic() - t0)))
lgpio.gpiochip_close(h)
print("done")
