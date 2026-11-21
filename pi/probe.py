#!/usr/bin/env python3
"""FSK receive at a fixed frequency; log RSSI + FREQEST (frequency offset) ~1 kHz.

Usage: python3 probe.py <seconds> <outfile.json> [freq_mhz]
FREQEST is the demodulator's estimate of how far the signal is from our tuned
frequency (signed, 26e6/2^14 = ~1.587 kHz per LSB).
"""
import json
import sys
import time

from cc1101 import CC1101

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 30
out = sys.argv[2] if len(sys.argv) > 2 else "probe.json"
mhz = float(sys.argv[3]) if len(sys.argv) > 3 else 433.92

r = CC1101()
r.setup(mhz, mod="fsk", dev=0x47)
r.write(0x10, 0x27)  # MDMCFG4: RX BW ~541 kHz
r.write(0x19, 0x1F)  # FOCCFG: FOC on, limit +/- BW/2 (~270 kHz) so FREQEST can see big offsets
r.rx()
time.sleep(0.01)

KHZ_PER_LSB = 26e6 / 2**14 / 1e3
log = []
t0 = time.monotonic()
while time.monotonic() - t0 < secs:
    rssi = r.rssi_dbm()
    fe = r.status(0x32)
    if fe >= 128:
        fe -= 256
    log.append((round(time.monotonic() - t0, 4), rssi, round(fe * KHZ_PER_LSB, 1)))
    time.sleep(0.001)
r.close()

sig = [x for x in log if x[1] > -60]
print(f"{len(log)} samples, {len(sig)} with signal (> -60 dBm)")
if sig:
    offs = sorted(x[2] for x in sig)
    n = len(offs)
    print(f"freq offset kHz: min {offs[0]}  p10 {offs[n//10]}  median {offs[n//2]}  p90 {offs[9*n//10]}  max {offs[-1]}")
    from collections import Counter
    hist = Counter(round(o / 5) * 5 for o in offs)
    for k in sorted(hist):
        print(f"  {k:+6.0f} kHz  {hist[k]:5d}  {'#' * min(60, hist[k] // 10)}")
    # transmission windows
    wins, start, last = [], None, None
    for t, rs, fe in log:
        if rs > -60:
            if start is None:
                start = t
            last = t
        elif start is not None and t - last > 0.05:
            wins.append((start, last)); start = None
    if start is not None:
        wins.append((start, last))
    print("transmissions:", ", ".join(f"{a:.2f}-{b:.2f}s" for a, b in wins))
json.dump({"mhz": mhz, "log": log}, open(out, "w"))
