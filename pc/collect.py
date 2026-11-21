#!/usr/bin/env python3
"""Collect training frames from a Tapo camera over RTSP.

Saves one timestamped JPEG every N seconds into data/<camera>/. Credentials come
from camera.local.json (gitignored) so they never hit the repo or the process
list of other tools.

Usage:
    python3 collect.py [camera] [--interval 2] [--sub|--main] [--seconds N]
"""
import argparse
import json
import os
import subprocess
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument("camera", nargs="?", default="downstairs")
ap.add_argument("--interval", type=float, default=2.0, help="seconds between frames")
ap.add_argument("--sub", action="store_true", help="use the low-res sub stream (default)")
ap.add_argument("--main", action="store_true", help="use the full-res main stream")
ap.add_argument("--seconds", type=int, default=0, help="stop after N seconds (0 = run until Ctrl-C)")
ap.add_argument("--config", default=os.path.join(HERE, "camera.local.json"))
a = ap.parse_args()

cfg = json.load(open(a.config))["cameras"][a.camera]
stream = cfg["main"] if a.main else cfg["sub"]
pw = urllib.parse.quote(cfg["pass"], safe="")
url = f"rtsp://{cfg['user']}:{pw}@{cfg['ip']}:554/{stream}"

outdir = os.path.join(HERE, "..", "data", a.camera)
os.makedirs(outdir, exist_ok=True)

cmd = ["ffmpeg", "-loglevel", "warning", "-rtsp_transport", "tcp", "-i", url,
       "-vf", f"fps=1/{a.interval}", "-strftime", "1",
       "-q:v", "3", os.path.join(outdir, "%Y%m%d_%H%M%S.jpg")]
if a.seconds:
    cmd[1:1] = ["-t", str(a.seconds)]

print(f"Collecting from '{a.camera}' ({stream}) every {a.interval}s -> {outdir}")
print("Ctrl-C to stop.")
try:
    subprocess.run(cmd)
except KeyboardInterrupt:
    print("\nstopped")
