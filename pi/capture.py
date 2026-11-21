#!/usr/bin/env python3
"""Record OOK edges from the CC1101 for N seconds and save them.

Usage: python3 capture.py <seconds> <outfile.json> [freq_mhz] [ook|fsk|gfsk] [deviatn_hex]
Prints an RSSI timeline so we can see when the remote was pressed.
"""
import json
import sys
import time

import lgpio

from cc1101 import CC1101, GDO0_GPIO

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 15
out = sys.argv[2] if len(sys.argv) > 2 else "capture.json"
mhz = float(sys.argv[3]) if len(sys.argv) > 3 else 433.92
mod = sys.argv[4] if len(sys.argv) > 4 else "ook"
dev = int(sys.argv[5], 16) if len(sys.argv) > 5 else 0x47

radio = CC1101()
radio.setup(mhz, mod=mod, dev=dev)
radio.rx()
time.sleep(0.01)

h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_alert(h, GDO0_GPIO, lgpio.BOTH_EDGES)
edges = []
cb = lgpio.callback(h, GDO0_GPIO, lgpio.BOTH_EDGES,
                    lambda chip, gpio, level, tick: edges.append((tick, level)))

rssi = []
print(f"Listening on {mhz} MHz {mod.upper()} dev=0x{dev:02X} for {secs:.0f} s ... (marcstate=0x{radio.marcstate():02X}, 0x0D=RX)", flush=True)
t0 = time.monotonic()
while time.monotonic() - t0 < secs:
    rssi.append((round(time.monotonic() - t0, 3), radio.rssi_dbm()))
    time.sleep(0.02)

cb.cancel()
lgpio.gpiochip_close(h)
radio.close()

# Print RSSI peaks per 0.5 s window
print("time(s)  peak RSSI (dBm)")
win = {}
for t, r in rssi:
    k = int(t * 2) / 2
    win[k] = max(win.get(k, -200), r)
for k in sorted(win):
    bar = "#" * max(0, int((win[k] + 100) / 2))
    print(f"{k:6.1f}  {win[k]:7.1f}  {bar}")

with open(out, "w") as f:
    json.dump({"mhz": mhz, "mod": mod, "dev": dev, "edges": edges, "rssi": rssi}, f)
print(f"Saved {len(edges)} edges to {out}")
