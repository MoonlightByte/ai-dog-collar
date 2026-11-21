#!/usr/bin/env python3
"""Transmit a synthesized AIKEEP collar frame via CC1101 async FSK + lgpio DMA wave.

Frame model (from capture): 97 symbols, pulse-distance coded.
  symbol = HIGH 206us, then LOW 206us (bit 0) or LOW 407us (bit 1)
  89 bits constant; a 4-bit counter appears at [37:41] as (C+3)&0xF and at
  [85:89] as C&0xF. Frame repeated with a ~1207us gap between repeats.

Usage:
  python3 tx.py <counter> [freq_mhz] [deviatn_hex] [power_hex] [repeats] [invert]
"""
import sys
import time

import lgpio

from cc1101 import CC1101, GDO0_GPIO, SIDLE, STX

TEMPLATE = "0010101010101010101110100101001010000XXXX11000100010000001000001010001101000000010011XXXX00000000"
HIGH_US, ZERO_US, ONE_US, GAP_US = 206, 206, 407, 1207

counter = int(sys.argv[1]) if len(sys.argv) > 1 else 12
mhz     = float(sys.argv[2]) if len(sys.argv) > 2 else 433.92
dev     = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x24
power   = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0xC0
repeats = int(sys.argv[5]) if len(sys.argv) > 5 else 8
invert  = int(sys.argv[6]) if len(sys.argv) > 6 else 0

def nib(v):
    return format(v & 0xF, "04b")

def build_frame(c):
    a, b = nib(c + 3), nib(c)
    bits = list(TEMPLATE)
    bits[37:41] = list(a)
    bits[85:89] = list(b)
    return "".join(bits)

frame = build_frame(counter)
print(f"counter={counter}  freq={mhz}  dev=0x{dev:02X}  pwr=0x{power:02X}  rpt={repeats}  inv={invert}")
print(f"frame=({len(frame)}b) {frame}")

MASK = 1 << 0  # group bit 0 == GDO0_GPIO
hi, lo = (0, MASK) if invert else (MASK, 0)

pulses = []
for bit in frame:
    pulses.append(lgpio.pulse(hi, MASK, HIGH_US))
    pulses.append(lgpio.pulse(lo, MASK, ONE_US if bit == "1" else ZERO_US))
pulses.append(lgpio.pulse(lo, MASK, GAP_US))  # inter-frame gap, line idle low

# --- radio into async TX ---
r = CC1101()
r.setup(mhz, power=power, mod="fsk", dev=dev)
r.strobe(SIDLE)
r.strobe(STX)          # carrier on; async mode makes GDO0 an input
time.sleep(0.002)
print("marcstate after STX = 0x%02X (0x13=TX)" % r.marcstate())

h = lgpio.gpiochip_open(0)
lgpio.group_claim_output(h, [GDO0_GPIO], [lo])  # start idle
try:
    for _ in range(repeats):
        lgpio.tx_wave(h, GDO0_GPIO, pulses)
        while lgpio.tx_busy(h, GDO0_GPIO, lgpio.TX_WAVE):
            time.sleep(0.001)
    lgpio.group_write(h, GDO0_GPIO, lo, MASK)
finally:
    lgpio.group_free(h, GDO0_GPIO)
    lgpio.gpiochip_close(h)
    r.strobe(SIDLE)
    r.close()
print("sent")
