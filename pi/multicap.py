#!/usr/bin/env python3
"""Cycle through FSK receiver settings (centre freq x deviation) and record the
demodulated edges for each, so we can find the setting that decodes the remote.

Usage: python3 multicap.py <seconds> <outfile.json>
"""
import json
import sys
import time

import lgpio

from cc1101 import CC1101, GDO0_GPIO, SIDLE, SRX, freq_regs

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 45
out = sys.argv[2] if len(sys.argv) > 2 else "multicap.json"

CENTRES = [433.920, 433.930, 433.940]
DEVS = [0x15, 0x24, 0x34, 0x47]  # ~5, 9.5, 19, 47.6 kHz
configs = [(c, d) for c in CENTRES for d in DEVS]
DWELL = 0.1

r = CC1101()
r.setup(433.92, mod="fsk")
r.write(0x10, 0xC8)  # RX BW ~102 kHz, data rate ~10 kBaud (12.5 us sampling)

h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_alert(h, GDO0_GPIO, lgpio.BOTH_EDGES)
edges = []
cb = lgpio.callback(h, GDO0_GPIO, lgpio.BOTH_EDGES,
                    lambda chip, gpio, level, tick: edges.append((tick, level)))

dwells = []
t0 = time.monotonic()
i = 0
while time.monotonic() - t0 < secs:
    c, d = configs[i % len(configs)]
    i += 1
    r.strobe(SIDLE)
    f2, f1, f0 = freq_regs(c)
    r.write(0x0D, f2); r.write(0x0E, f1); r.write(0x0F, f0)
    r.write(0x15, d)
    r.strobe(SRX)
    time.sleep(0.005)
    a = len(edges)
    rs = []
    t1 = time.monotonic()
    while time.monotonic() - t1 < DWELL:
        rs.append(r.rssi_dbm())
        time.sleep(0.01)
    b = len(edges)
    dwells.append({"t": round(t1 - t0, 3), "mhz": c, "dev": d,
                   "rssi_min": min(rs), "rssi_max": max(rs), "a": a, "b": b})
cb.cancel()
lgpio.gpiochip_close(h)
r.close()

good = [x for x in dwells if x["rssi_min"] > -60]
print(f"{len(dwells)} dwells, {len(good)} fully inside a transmission")
json.dump({"dwells": dwells, "edges": edges}, open(out, "w"))
