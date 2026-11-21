#!/usr/bin/env bash
# Dog Collar Monitor launcher. Starts the dashboard + detection app.
cd "$(dirname "$0")"
PORT="${PORT:-8800}"
echo "=================================================="
echo "  Dog Collar Monitor"
echo "  Dashboard:  http://localhost:${PORT}"
echo "  (loads YOLO + camera; give it ~10s on first start)"
echo "  Ctrl-C to stop."
echo "=================================================="
# open the Windows browser once the server is up
( for i in $(seq 1 30); do
    curl -sf "http://localhost:${PORT}/api/status" >/dev/null 2>&1 && break; sleep 1; done
  cmd.exe /c start "" "http://localhost:${PORT}" >/dev/null 2>&1 || true ) &
exec python3 -m uvicorn app.server:app --host 0.0.0.0 --port "${PORT}"
