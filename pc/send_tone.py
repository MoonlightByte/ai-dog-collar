#!/usr/bin/env python3
"""PC-side client: ask the Pi to fire one TONE (or PING it).

Usage:
    python3 send_tone.py [tone|ping] [--host dogpi] [--port 8737] [--token ...]
"""
import argparse
import os
import socket

ap = argparse.ArgumentParser()
ap.add_argument("cmd", nargs="?", default="tone", choices=["tone", "vibe", "ping"])
ap.add_argument("--host", default=os.environ.get("DOGPI_HOST", "dogpi"))
ap.add_argument("--port", type=int, default=8737)
ap.add_argument("--token", default=os.environ.get("DOGPI_TOKEN", ""),
                help="shared secret (or env DOGPI_TOKEN); must match the Pi")
a = ap.parse_args()

msg = f"{a.cmd.upper()} {a.token}\n".encode()
with socket.create_connection((a.host, a.port), timeout=5) as s:
    s.sendall(msg)
    print(s.recv(256).decode().strip())
