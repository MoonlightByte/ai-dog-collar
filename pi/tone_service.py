#!/usr/bin/env python3
"""Pi-side collar service. Listens on the LAN for stimulus commands from the
vision PC, enforces a cooldown, keeps the climbing counter, and logs everything.

Protocol (newline-terminated, plain TCP):
    PING <token>            -> PONG
    TONE <token>            -> OK TONE <counter>   | COOLDOWN <secs> | BADAUTH
    VIBE <token>            -> OK VIBE <counter>   | COOLDOWN <secs> | BADAUTH

SAFETY: only stimuli implemented in collar_tx can be sent. Shock is NOT sent by
this service and the vision trigger must never request it. Cooldown is a second
safety layer independent of the PC.
"""
import json
import os
import socket
import sys
import threading
import time
from datetime import datetime

import collar_tx

HOST, PORT = "0.0.0.0", 8737
TOKEN = os.environ.get("DOGPI_TOKEN", "")   # shared LAN secret; set in ~/dogcollar/dogpi.env
if len(TOKEN) < 16:
    sys.exit("DOGPI_TOKEN missing/too short: put DOGPI_TOKEN=<random secret> in ~/dogcollar/dogpi.env")
COOLDOWN_S = float(os.environ.get("DOGPI_COOLDOWN", "5"))
LOG = os.path.expanduser("~/dogcollar/tone.log")

_lock = threading.Lock()
_last_fire = 0.0

def log(event, **kw):
    rec = {"t": datetime.now().isoformat(timespec="seconds"), "event": event, **kw}
    line = json.dumps(rec)
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def handle(cmd):
    global _last_fire
    parts = cmd.strip().split()
    if not parts:
        return "ERR empty"
    verb = parts[0].upper()
    token = parts[1] if len(parts) > 1 else ""
    if token != TOKEN:
        log("badauth", verb=verb)
        return "BADAUTH"
    if verb == "PING":
        return "PONG"
    if verb in ("TONE", "VIBE"):
        with _lock:
            now = time.monotonic()
            remaining = COOLDOWN_S - (now - _last_fire)
            if remaining > 0:
                log("cooldown", verb=verb, remaining=round(remaining, 2))
                return f"COOLDOWN {remaining:.1f}"
            counter = collar_tx.send(verb)
            _last_fire = now
            log(verb.lower(), counter=counter)
            return f"OK {verb} {counter}"
    return f"ERR unknown {verb}"

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(5)
    log("start", host=HOST, port=PORT, cooldown=COOLDOWN_S)
    while True:
        conn, addr = s.accept()
        try:
            conn.settimeout(5)
            data = conn.recv(256).decode(errors="replace")
            reply = handle(data)
            conn.sendall((reply + "\n").encode())
        except Exception as e:
            log("error", err=str(e))
        finally:
            conn.close()

if __name__ == "__main__":
    main()
