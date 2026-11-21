#!/usr/bin/env python3
"""Sweep RSSI across a frequency range to locate the remote's carrier(s).

Usage: python3 sweep.py <seconds> <start_mhz> <stop_mhz> <step_khz> <outfile.json>
Keeps the per-frequency max RSSI over every sweep that saw a signal.
"""
import json
import sys
import time

from cc1101 import CC1101, SIDLE, SRX, freq_regs

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 30
start = float(sys.argv[2]) if len(sys.argv) > 2 else 433.4
stop = float(sys.argv[3]) if len(sys.argv) > 3 else 434.4
step = float(sys.argv[4]) if len(sys.argv) > 4 else 10
out = sys.argv[5] if len(sys.argv) > 5 else "sweep.json"

freqs = []
f = start
while f <= stop + 1e-9:
    freqs.append(round(f, 4))
    f += step / 1000

r = CC1101()
r.setup(433.92, mod="ook")
bw = int(sys.argv[6], 16) if len(sys.argv) > 6 else 0xC7
r.write(0x10, bw)  # MDMCFG4: RX BW (0xC7 ~102 kHz, 0xF7 ~58 kHz)
best = {f: -200.0 for f in freqs}
noise = {f: [] for f in freqs}
sweeps = hits = 0
timeline = []
t0 = time.monotonic()
while time.monotonic() - t0 < secs:
    row = []
    for f in freqs:
        r.strobe(SIDLE)
        f2, f1, f0 = freq_regs(f)
        r.write(0x0D, f2); r.write(0x0E, f1); r.write(0x0F, f0)
        r.strobe(SRX)
        time.sleep(0.003)  # autocal (~0.8 ms) + RSSI settle
        row.append(r.rssi_dbm())
    sweeps += 1
    timeline.append((round(time.monotonic() - t0, 2), max(row), freqs[row.index(max(row))]))
    if max(row) > -75:
        hits += 1
        for f, v in zip(freqs, row):
            best[f] = max(best[f], v)
    else:
        for f, v in zip(freqs, row):
            noise[f].append(v)
r.close()

print(f"{sweeps} sweeps, {hits} with signal")
for t, m, f in timeline:
    if m > -85:
        print(f"  t={t:5.2f}s max {m:6.1f} dBm at {f:.3f} MHz")
for f in freqs:
    nf = sum(noise[f]) / len(noise[f]) if noise[f] else -200
    bar = "#" * max(0, int((best[f] + 100) / 2))
    print(f"{f:9.3f} MHz  peak {best[f]:6.1f}  noise {nf:6.1f}  {bar}")
json.dump({"freqs": freqs, "best": best, "timeline": timeline, "sweeps": sweeps, "hits": hits}, open(out, "w"))
