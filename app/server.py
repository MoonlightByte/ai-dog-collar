"""Dog-collar monitoring app: live dashboard + control API.

Run:  python3 -m uvicorn app.server:app --host 0.0.0.0 --port 8800
or:   ./start.sh
"""
import os
from fastapi import FastAPI, Body
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.engine import Engine, EVENTS_DIR, HERE

app = FastAPI(title="Dog Collar Monitor")
engine = Engine()

STATIC = os.path.join(HERE, "static")


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/status")
def status():
    return engine.status()


@app.post("/api/arm")
def arm(body: dict = Body(...)):
    engine.set_armed(body.get("armed", False))
    return {"armed": engine.armed}


@app.post("/api/enable")
def enable(body: dict = Body(...)):
    engine.enabled = bool(body.get("enabled", True))
    return {"enabled": engine.enabled}


@app.post("/api/config")
def config(body: dict = Body(...)):
    engine.set_config(consec=body.get("consec"), cooldown=body.get("cooldown"))
    return engine.status()


@app.post("/api/test_tone")
def test_tone():
    return {"result": engine.test_tone()}


@app.get("/api/events")
def events():
    return {"events": engine.events[:100]}


@app.get("/api/event/{eid}/{fname}")
def event_file(eid: str, fname: str):
    # guard against traversal
    if "/" in eid or "/" in fname or ".." in eid or ".." in fname:
        return JSONResponse({"error": "bad path"}, status_code=400)
    p = os.path.join(EVENTS_DIR, eid, fname)
    if not os.path.exists(p):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(p)


@app.get("/stream.mjpg")
def stream():
    return StreamingResponse(engine.mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.on_event("shutdown")
def _shutdown():
    engine.stop()


if os.path.isdir(STATIC):
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
