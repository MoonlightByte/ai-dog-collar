#!/usr/bin/env python3
"""Sweep TX settings so the user can pinpoint which one makes the collar beep.
Each combo: a labeled burst, then a fixed 2.0s gap. Reports the index->setting map.

Usage: python3 tx_sweep.py [dev_hex] [freqs_csv]
"""
import sys
import time

import lgpio

from cc1101 import CC1101, GDO0_GPIO, SIDLE, STX

TEMPLATE = "0010101010101010101110100101001010000XXXX11000100010000001000001010001101000000010011XXXX00000000"
HIGH_US, ZERO_US, ONE_US, GAP_US = 206, 206, 407, 1207
MASK = 1 << 0

dev = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x24
freqs = [float(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else \
        [433.84, 433.88, 433.90, 433.92, 433.94, 433.96, 434.00]
REPEATS, SPACING = 6, 2.0

def frame_bits(c):
    b = list(TEMPLATE)
    b[37:41] = list(format((c + 3) & 0xF, "04b"))
    b[85:89] = list(format(c & 0xF, "04b"))
    return "".join(b)

def pulses_for(frame, invert):
    hi, lo = (0, MASK) if invert else (MASK, 0)
    p = []
    for bit in frame:
        p.append(lgpio.pulse(hi, MASK, HIGH_US))
        p.append(lgpio.pulse(lo, MASK, ONE_US if bit == "1" else ZERO_US))
    p.append(lgpio.pulse(lo, MASK, GAP_US))
    return p, lo

combos = []
for f in freqs:
    for inv in (0, 1):
        combos.append((f, inv))

print(f"dev=0x{dev:02X}  {len(combos)} combos, {SPACING}s apart")
for i, (f, inv) in enumerate(combos, 1):
    print(f"  #{i:2d}  {f:.2f} MHz  {'inverted' if inv else 'normal'}")

h = lgpio.gpiochip_open(0)
counter = 0
for i, (f, inv) in enumerate(combos, 1):
    frame = frame_bits(counter)
    counter = (counter + 1) & 0xF
    pulses, lo = pulses_for(frame, inv)
    r = CC1101()
    r.setup(f, power=0xC0, mod="fsk", dev=dev)
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
    print(f"  sent #{i}", flush=True)
    time.sleep(max(0, SPACING - (time.monotonic() - t0)))
lgpio.gpiochip_close(h)
print("done")
