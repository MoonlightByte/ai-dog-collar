"""Detection engine for the dog-collar app.

Runs the RTSP -> YOLO-seg -> zone-check -> (TONE) loop in a background thread,
keeps the latest annotated frame for the dashboard, logs every fire to disk,
and exposes thread-safe status/control. Stimulus is TONE ONLY (beep) by design.
"""
import os, sys, time, json, socket, threading, subprocess, csv
from collections import deque
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PC = os.path.join(ROOT, "pc")
sys.path.insert(0, PC)
import detect  # ZONES, poly_mask, thresholds, IMGSZ, CONF  (from pc/)

_cam_cfg = os.path.join(PC, "camera.local.json")
if not os.path.exists(_cam_cfg):
    raise RuntimeError(f"Missing {_cam_cfg}. Copy pc/camera.sample.json to it and "
                       f"fill in your camera (see docs/05-cameras.md).")
CAM = json.load(open(_cam_cfg))["cameras"]["downstairs"]
EVENTS_DIR = os.path.join(ROOT, "data", "events")
os.makedirs(EVENTS_DIR, exist_ok=True)

def _pi_config():
    """Pi tone-service address. Order: pc/collar.local.json -> env -> defaults.
    Set DOGPI_HOST (or collar.local.json) to your Pi's IP/hostname."""
    host = os.environ.get("DOGPI_HOST", "dogpi")
    port = int(os.environ.get("DOGPI_PORT", "8737"))
    token = os.environ.get("DOGPI_TOKEN", "")   # no default: set in collar.local.json
    p = os.path.join(PC, "collar.local.json")
    if os.path.exists(p):
        c = json.load(open(p))
        host, port, token = c.get("host", host), int(c.get("port", port)), c.get("token", token)
    return host, port, token

def _rtsp(stream):
    import urllib.parse
    pw = urllib.parse.quote(CAM["pass"], safe="")
    return f"rtsp://{CAM['user']}:{pw}@{CAM['ip']}:554/{stream}"

try:
    FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
    FONT_S = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
except Exception:
    FONT = FONT_S = ImageFont.load_default()

# Motion gate (GPU saver). Tunable via env; DOGCOLLAR_MOTION_GATE=0 disables.
_e = os.environ.get
MG_ON        = _e("DOGCOLLAR_MOTION_GATE", "1") != "0"
MG_W, MG_H   = 320, 180                                   # diff resolution
MG_MARGIN    = float(_e("DOGCOLLAR_MG_MARGIN", "0.12"))   # zone dilation, fraction of width (approach area)
MG_PIX_DIFF  = int(_e("DOGCOLLAR_MG_PIX_DIFF", "18"))     # per-pixel gray delta counted as change
MG_FRAC      = float(_e("DOGCOLLAR_MG_FRAC", "0.002"))    # changed fraction of region => motion
MG_LAG       = float(_e("DOGCOLLAR_MG_LAG", "0.5"))       # compare vs frame this many s old
MG_HOLD      = float(_e("DOGCOLLAR_MG_HOLD", "4"))        # keep inferring this long after motion
MG_HEARTBEAT = float(_e("DOGCOLLAR_MG_HEARTBEAT", "2"))   # infer at least this often regardless


class Engine:
    STIM = "TONE"  # beep only. Never VIBE/SHOCK from automation.

    def __init__(self, pi_host=None, pi_port=None, pi_token=None,
                 stream="stream1", consec=3, cooldown=10.0, model="yolo11x-seg.pt"):
        h, p, t = _pi_config()
        self.pi_host, self.pi_port, self.pi_token = pi_host or h, pi_port or p, pi_token or t
        self.stream = stream
        self.consec = consec
        self.cooldown = cooldown
        self.model_name = model
        self.armed = False            # dry-run by default
        self.enabled = True           # detection on/off (camera always watched)
        self.lock = threading.Lock()
        self.run = True
        self.model = None
        self._raw = None              # latest BGR frame
        self._annot_jpeg = None       # latest annotated JPEG bytes
        self._zmask = self._zarea = None
        self.window = deque(maxlen=consec)
        self.recent = deque(maxlen=max(consec + 3, 6))
        self.last_fire = 0.0
        # stats
        self.frames = 0
        self.fps = 0.0
        self.dog_present = False
        self.last_dog_black = None
        self.started = time.time()
        self.events = []              # recent, newest first
        self.pi_ok = None
        # motion gate state
        self._mg_region = None; self._mg_region_n = 1
        self._mg_hist = deque()
        self._mg_last_motion = 0.0
        self.motion_frac = 0.0
        self.gate_active = True
        self.infer_fps = 0.0
        self._gpu = {"util": None, "mem": None, "t": 0}
        self._load_events()
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._infer, daemon=True).start()
        threading.Thread(target=self._pinger, daemon=True).start()

    # ---- infra ----
    def _reader(self):
        cap = None
        while self.run:
            if cap is None:
                cap = cv2.VideoCapture(_rtsp(self.stream), cv2.CAP_FFMPEG)
                try: cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception: pass
            ok, f = cap.read()
            if not ok:
                cap.release(); cap = None; time.sleep(0.3); continue
            with self.lock:
                self._raw = f

    def _pinger(self):
        while self.run:
            self.pi_ok = self._pi_cmd("PING")
            time.sleep(5)

    def _pi_cmd(self, verb):
        try:
            with socket.create_connection((self.pi_host, self.pi_port), timeout=2) as s:
                s.sendall(f"{verb} {self.pi_token}\n".encode())
                return s.recv(100).decode().strip()
        except Exception as e:
            return f"ERR:{e.__class__.__name__}"

    def _gpu_stat(self):
        if time.time() - self._gpu["t"] < 2:
            return self._gpu
        try:
            # multi-GPU hosts: report the GPU we run on (nvidia-smi index, PCI order)
            gid = os.environ.get("DOGCOLLAR_GPU_INDEX", "0")
            out = subprocess.run(["nvidia-smi", f"--id={gid}", "--query-gpu=utilization.gpu,memory.used",
                                  "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=2).stdout.strip()
            u, m = out.splitlines()[0].split(",")[0:2]
            self._gpu = {"util": int(u), "mem": int(m), "t": time.time()}
        except Exception:
            self._gpu = {"util": None, "mem": None, "t": time.time()}
        return self._gpu

    # ---- detection ----
    def _infer(self):
        from ultralytics import YOLO
        self.model = YOLO(self.model_name)
        t_last = time.time(); n = 0
        # fps cap to save GPU power (0 = uncapped). consec=3 @10fps still confirms in ~0.3s.
        max_fps = float(os.environ.get("DOGCOLLAR_MAX_FPS", "10"))
        period = 1.0 / max_fps if max_fps > 0 else 0.0
        t_next = time.time()
        t_inf = 0.0; n_inf = 0; t_inf_last = time.time()
        while self.run:
            if period:
                dt = t_next - time.time()
                if dt > 0: time.sleep(dt)
                t_next = max(t_next + period, time.time())
            with self.lock:
                f = None if self._raw is None else self._raw.copy()
            if f is None:
                time.sleep(0.03); continue
            pil = Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
            if self._zmask is None:
                self._zmask = {k: detect.poly_mask(z["poly"], pil.width, pil.height) for k, z in detect.ZONES.items()}
                self._zarea = {k: max(int(m.sum()), 1) for k, m in self._zmask.items()}
            # motion gate: skip the big model when the area around the zones is still.
            # Fail-safe: always infer while a dog was last seen, for HOLD s after motion,
            # and at least every HEARTBEAT s.
            now = time.time()
            moving = self._motion(f, now)
            run_model = self.enabled and (
                not MG_ON or moving or self.dog_present
                or now - self._mg_last_motion < MG_HOLD or now - t_inf >= MG_HEARTBEAT)
            if run_model:
                fired, dogs = self._evaluate(pil); t_inf = now; n_inf += 1
                self._annotate_latest(pil, dogs, fired)
            else:
                fired, dogs = [], []
                self._annotate_latest(pil, dogs, fired, idle=self.enabled)
            self.gate_active = bool(run_model)
            if now - t_inf_last >= 5.0:   # 5s window: heartbeat-only reads ~0.5, not 0/1 flicker
                self.infer_fps = round(n_inf / (now - t_inf_last), 1); n_inf = 0; t_inf_last = now
            self.recent.append((time.time(), pil))
            self.window.append(bool(fired))
            self.dog_present = len(dogs) > 0
            self.last_dog_black = any(b for _, b in dogs) if dogs else None
            up = len(self.window) == self.consec and all(self.window)
            now = time.time()
            if up and now - self.last_fire >= self.cooldown:
                self.last_fire = now
                self._fire(pil, dogs, fired)
            # fps
            self.frames += 1; n += 1
            if now - t_last >= 1.0:
                self.fps = round(n / (now - t_last), 1); n = 0; t_last = now

    def _motion(self, bgr, now):
        """Cheap CPU frame-diff inside the (dilated) zone region. Returns True on motion."""
        g = cv2.cvtColor(cv2.resize(bgr, (MG_W, MG_H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        g = cv2.GaussianBlur(g, (5, 5), 0)
        if self._mg_region is None:
            m = np.zeros((MG_H, MG_W), np.uint8)
            for z in detect.ZONES.values():
                pts = np.array([(x * MG_W, y * MG_H) for x, y in z["poly"]], np.int32)
                cv2.fillPoly(m, [pts], 1)
            r = max(1, int(MG_MARGIN * MG_W))
            m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
            self._mg_region = m.astype(bool)
            self._mg_region_n = max(int(self._mg_region.sum()), 1)
        # compare against a frame ~MG_LAG s old so slow movement still registers
        ref = self._mg_hist[0][1] if self._mg_hist else None
        self._mg_hist.append((now, g))
        while len(self._mg_hist) > 1 and now - self._mg_hist[0][0] > MG_LAG:
            self._mg_hist.popleft()
        if ref is None:
            return True
        changed = (cv2.absdiff(g, ref) > MG_PIX_DIFF) & self._mg_region
        self.motion_frac = round(float(changed.sum()) / self._mg_region_n, 4)
        if self.motion_frac >= MG_FRAC:
            self._mg_last_motion = now
            return True
        return False

    def _evaluate(self, pil):
        arr = np.asarray(pil)
        res = self.model(pil, conf=detect.CONF, imgsz=detect.IMGSZ, verbose=False)[0]
        fired, dogs = [], []
        if res.masks is not None:
            for b, xy in zip(res.boxes, res.masks.xy):
                if res.names[int(b.cls)] != "dog" or len(xy) < 3: continue
                dm = detect.poly_mask(xy, pil.width, pil.height, normalized=False)
                dm_n = max(int(dm.sum()), 1)
                is_black = float(arr[dm].mean()) < detect.BLACK_V_MAX
                dogs.append((dm, is_black))
                if not is_black: continue
                for k, zm in self._zmask.items():
                    inter = int((dm & zm).sum())
                    if inter and (inter / self._zarea[k] >= detect.ZONE_COVER or inter / dm_n >= detect.DOG_IN_ZONE):
                        fired.append(k)
        return sorted(set(fired)), dogs

    def _draw(self, pil, dogs, fired, caption):
        im = pil.copy(); d = ImageDraw.Draw(im, "RGBA"); W, H = im.size
        for k, z in detect.ZONES.items():
            c = (255, 40, 40) if z["type"] == "gate_top" else (0, 220, 80)
            hot = k in fired
            d.polygon([(x*W, y*H) for x, y in z["poly"]], fill=c+(110 if hot else 45,), outline=c+(255,))
        for dm, is_black in dogs:
            ys, xs = np.where(dm)
            if len(xs):
                col = (255, 235, 0) if is_black else (120, 160, 255)
                d.rectangle((int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())), outline=col+(255,), width=4)
        d.rectangle((0, 0, W, 34), fill=(0, 0, 0, 150))
        d.text((10, 6), caption, fill=(255, 255, 255, 255), font=FONT_S)
        return im

    def _annotate_latest(self, pil, dogs, fired, idle=False):
        mode = "ARMED·BEEP" if self.armed else "DRY-RUN"
        streak = f"{sum(self.window)}/{self.consec}" if self.window else "0"
        cap = f"{time.strftime('%H:%M:%S')}  {mode}  dogs:{len(dogs)}  streak:{streak}" + (f"  UP:{','.join(fired)}" if fired else "")
        if idle:
            cap = f"{time.strftime('%H:%M:%S')}  {mode}  idle (no motion near zones)"
        im = self._draw(pil, dogs, fired, cap)
        buf = cv2.imencode(".jpg", cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 70])[1]
        with self.lock:
            self._annot_jpeg = buf.tobytes()

    def _fire(self, pil, dogs, fired):
        ts = time.strftime("%Y%m%d_%H%M%S")
        mode = "ARMED" if self.armed else "DRYRUN"
        ev = os.path.join(EVENTS_DIR, f"{ts}_{'_'.join(fired)}")
        os.makedirs(ev, exist_ok=True)
        self._draw(pil, dogs, fired, f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {mode}  TONE: {', '.join(fired)}").save(
            os.path.join(ev, "trigger.jpg"), quality=90)
        for i, (t0, p0) in enumerate(list(self.recent)):
            p0.save(os.path.join(ev, f"ctx_{i:02d}.jpg"), quality=85)
        tone_result = None
        if self.armed:
            tone_result = self._pi_cmd("TONE")
        with open(os.path.join(EVENTS_DIR, "audit.csv"), "a", newline="") as fh:
            csv.writer(fh).writerow([time.strftime("%Y-%m-%d %H:%M:%S"), mode, " ".join(fired),
                                     os.path.basename(ev), tone_result or ""])
        rec = {"id": os.path.basename(ev), "time": time.strftime("%Y-%m-%d %H:%M:%S"),
               "mode": mode, "zones": fired, "tone": tone_result}
        self.events.insert(0, rec)
        self.events = self.events[:200]

    def _load_events(self):
        p = os.path.join(EVENTS_DIR, "audit.csv")
        if not os.path.exists(p): return
        try:
            for row in list(csv.reader(open(p)))[1:][-200:][::-1]:
                if len(row) >= 4:
                    self.events.append({"id": os.path.basename(row[3]), "time": row[0], "mode": row[1],
                                        "zones": row[2].split(), "tone": row[4] if len(row) > 4 else None})
        except Exception:
            pass

    # ---- public API ----
    def mjpeg(self):
        while self.run:
            with self.lock:
                j = self._annot_jpeg
            if j:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + j + b"\r\n"
            time.sleep(0.1)

    def set_armed(self, v): self.armed = bool(v)
    def set_config(self, consec=None, cooldown=None):
        if consec: self.consec = int(consec); self.window = deque(self.window, maxlen=self.consec); self.recent = deque(self.recent, maxlen=max(self.consec+3,6))
        if cooldown is not None: self.cooldown = float(cooldown)
    def test_tone(self): return self._pi_cmd("TONE")

    def status(self):
        g = self._gpu_stat()
        return {
            "armed": self.armed, "enabled": self.enabled, "stim": self.STIM,
            "stream": self.stream, "consec": self.consec, "cooldown": self.cooldown,
            "fps": self.fps, "frames": self.frames, "dog_present": self.dog_present,
            "dog_black": self.last_dog_black,
            "streak": sum(self.window), "uptime": int(time.time() - self.started),
            "last_fire": (time.strftime("%H:%M:%S", time.localtime(self.last_fire)) if self.last_fire else None),
            "fires_total": len(self.events),
            "pi_ok": self.pi_ok, "gpu_util": g["util"], "gpu_mem": g["mem"],
            "model": self.model_name, "ready": self.model is not None,
            "motion_gate": MG_ON, "gate_active": self.gate_active,
            "infer_fps": self.infer_fps, "motion_frac": self.motion_frac,
        }

    def stop(self):
        self.run = False
