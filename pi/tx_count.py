#!/usr/bin/env python3
"""Send frames with strictly increasing counter at fixed freq/deviation,
to test the collar's counter-tracking and confirm a working deviation.

Usage: python3 tx_count.py [freq] [dev_hex] [start] [n] [spacing] [invert]
"""
import sys
import time

import lgpio

from cc1101 import CC1101, GDO0_GPIO, SIDLE, STX

TEMPLATE = "0010101010101010101110100101001010000XXXX11000100010000001000001010001101000000010011XXXX00000000"
HIGH_US, ZERO_US, ONE_US, GAP_US = 206, 206, 407, 1207
MASK = 1 << 0

import os
CFILE = os.path.expanduser("~/dogcollar/counter.txt")

mhz    = float(sys.argv[1]) if len(sys.argv) > 1 else 433.92
dev    = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x24
n      = int(sys.argv[3]) if len(sys.argv) > 3 else 6
spacing= float(sys.argv[4]) if len(sys.argv) > 4 else 1.5
invert = int(sys.argv[5]) if len(sys.argv) > 5 else 0
REPEATS = 6
hi, lo = (0, MASK) if invert else (MASK, 0)

def next_counter():
    try:
        v = int(open(CFILE).read().strip())
    except Exception:
        v = 0
    open(CFILE, "w").write(str((v + 1) & 0xFFFF))
    return v & 0xF  # low 4 bits go in the frame; we keep climbing a 16-bit tally

def pulses_for(c):
    b = list(TEMPLATE)
    b[37:41] = list(format((c + 3) & 0xF, "04b"))
    b[85:89] = list(format(c & 0xF, "04b"))
    p = []
    for bit in b:
        p.append(lgpio.pulse(hi, MASK, HIGH_US))
        p.append(lgpio.pulse(lo, MASK, ONE_US if bit == "1" else ZERO_US))
    p.append(lgpio.pulse(lo, MASK, GAP_US))
    return p

print(f"freq={mhz} dev=0x{dev:02X} invert={invert}  {n} bursts (persistent climbing counter), {spacing}s apart")
h = lgpio.gpiochip_open(0)
for i in range(n):
    c = next_counter()
    pulses = pulses_for(c)
    r = CC1101()
    r.setup(mhz, power=0xC0, mod="fsk", dev=dev)
    r.write(0x02, 0x2E)
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
    print(f"  burst {i+1}/{n}  counter={c}", flush=True)
    time.sleep(max(0, spacing - (time.monotonic() - t0)))
lgpio.gpiochip_close(h)
print("done")
