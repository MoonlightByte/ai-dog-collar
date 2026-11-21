#!/usr/bin/env python3
"""Live loop: watch the camera, fire a TONE when the black dog is up on a surface.

Always processes the NEWEST frame (drops backlog). Requires N consecutive
"up on a surface" frames before firing, then a cooldown. Default is DRY-RUN:
it only logs "WOULD TONE" and never touches the collar. Pass --arm to actually
send TONE to the Pi tone_service.

    python3 live_detect.py                 # dry-run, prints verdicts
    python3 live_detect.py --arm --pi dogpi # live: sends TONE to the Pi

Safety: this can only ever send TONE/VIBE (see pi/collar_tx.py). Never shock.
"""
import argparse, json, os, time, threading, socket, csv
from collections import deque
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
import detect  # ZONES, poly_mask, thresholds, IMGSZ, CONF

HERE = os.path.dirname(os.path.abspath(__file__))
CAM = json.load(open(os.path.join(HERE, "camera.local.json")))["cameras"]["downstairs"]

def rtsp_url(stream):
    import urllib.parse
    pw = urllib.parse.quote(CAM["pass"], safe="")
    return f"rtsp://{CAM['user']}:{pw}@{CAM['ip']}:554/{stream}"

class Newest:
    """Background reader that always keeps only the latest frame."""
    def __init__(self, url):
        self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        try: self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception: pass
        self.frame = None; self.lock = threading.Lock(); self.run = True
        threading.Thread(target=self._loop, daemon=True).start()
    def _loop(self):
        while self.run:
            ok, f = self.cap.read()
            if not ok:
                time.sleep(0.05); continue
            with self.lock: self.frame = f
    def get(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()
    def stop(self):
        self.run = False; self.cap.release()

def send_tone(host, port, token):
    with socket.create_connection((host, port), timeout=2) as s:
        s.sendall(f"TONE {token}\n".encode())
        return s.recv(100).decode().strip()

def evaluate(pil, model, zmask, zarea):
    """Return (fired_zones, dogs) where dogs = [(mask, is_black), ...]."""
    arr = np.asarray(pil)
    res = model(pil, conf=detect.CONF, imgsz=detect.IMGSZ, verbose=False)[0]
    fired, dogs = [], []
    if res.masks is not None:
        for b, xy in zip(res.boxes, res.masks.xy):
            if res.names[int(b.cls)] != "dog" or len(xy) < 3: continue
            dm = detect.poly_mask(xy, pil.width, pil.height, normalized=False)
            dm_n = max(int(dm.sum()), 1)
            is_black = float(arr[dm].mean()) < detect.BLACK_V_MAX
            dogs.append((dm, is_black))
            if not is_black: continue  # only the black dog can trigger
            for n, zm in zmask.items():
                inter = int((dm & zm).sum())
                if inter and (inter/zarea[n] >= detect.ZONE_COVER or inter/dm_n >= detect.DOG_IN_ZONE):
                    fired.append(n)
    return sorted(set(fired)), dogs

def annotate(pil, dogs, fired, mode):
    """Draw zones + dog boxes + verdict onto a copy, for the audit trail."""
    im = pil.copy(); d = ImageDraw.Draw(im, "RGBA"); W, H = im.size
    try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
    except Exception: font = ImageFont.load_default()
    for n, z in detect.ZONES.items():
        c = (255,40,40) if z["type"] == "gate_top" else (0,220,80)
        d.polygon([(x*W, y*H) for x, y in z["poly"]], fill=c+(55,), outline=c+(255,))
    for dm, is_black in dogs:
        ys, xs = np.where(dm)
        if len(xs):
            col = (255,235,0) if is_black else (120,160,255)
            d.rectangle((int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())), outline=col+(255,), width=4)
    label = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {mode}  TONE: {', '.join(fired)}"
    d.text((16, 14), label, fill=(255,255,255,255), font=font, stroke_width=3, stroke_fill=(0,0,0,255))
    return im

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="store_true", help="actually send TONE (default: dry-run)")
    ap.add_argument("--stream", default=CAM.get("main", "stream1"))  # high-res; dark dog needs detail
    ap.add_argument("--consec", type=int, default=3, help="consecutive up-frames before firing")
    ap.add_argument("--cooldown", type=float, default=10.0)
    ap.add_argument("--pi", default=os.environ.get("DOGPI_HOST", "dogpi"))
    ap.add_argument("--port", type=int, default=8737)
    ap.add_argument("--token", default=os.environ.get("DOGPI_TOKEN", ""),
                help="shared secret (or env DOGPI_TOKEN); must match the Pi")
    ap.add_argument("--model", default="yolo11x-seg.pt")
    ap.add_argument("--save-dir", default=os.path.join(HERE, "..", "data", "events"))
    a = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(a.model)
    # warm up zone masks at the stream resolution (lazy: built on first frame)
    os.makedirs(a.save_dir, exist_ok=True)
    cam = Newest(rtsp_url(a.stream))
    mode = "ARMED (will TONE)" if a.arm else "DRY-RUN (no tone)"
    print(f"live_detect {mode} stream={a.stream} consec={a.consec} cooldown={a.cooldown}s")
    print("waiting for first frame...")

    audit_csv = os.path.join(a.save_dir, "audit.csv")
    if not os.path.exists(audit_csv):
        with open(audit_csv, "w", newline="") as fh:
            csv.writer(fh).writerow(["timestamp", "mode", "zones", "event_dir", "context_frames"])

    zmask = zarea = None
    window = deque(maxlen=a.consec)
    recent = deque(maxlen=max(a.consec + 3, 6))  # raw frames for pre-trigger context
    last_fire = 0.0
    try:
        while True:
            f = cam.get()
            if f is None:
                time.sleep(0.05); continue
            pil = Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
            if zmask is None:
                zmask = {n: detect.poly_mask(z["poly"], pil.width, pil.height) for n, z in detect.ZONES.items()}
                zarea = {n: max(int(m.sum()), 1) for n, m in zmask.items()}
                print(f"frame {pil.width}x{pil.height}; running.")
            recent.append((time.time(), pil))
            fired, dogs = evaluate(pil, model, zmask, zarea)
            window.append(bool(fired))
            up = len(window) == a.consec and all(window)
            now = time.time()
            if fired:
                print(f"  up-on: {', '.join(fired)}  (streak {sum(window)}/{a.consec})")
            if up and now - last_fire >= a.cooldown:
                last_fire = now
                ts = time.strftime("%Y%m%d_%H%M%S")
                mode = "ARMED" if a.arm else "DRYRUN"
                # one folder per event: annotated trigger frame + raw context frames
                ev = os.path.join(a.save_dir, f"{ts}_{'_'.join(fired)}")
                os.makedirs(ev, exist_ok=True)
                annotate(pil, dogs, fired, mode).save(os.path.join(ev, "trigger.jpg"), quality=90)
                n_ctx = 0
                for i, (t0, p0) in enumerate(list(recent)):
                    p0.save(os.path.join(ev, f"ctx_{i:02d}_{t0 - recent[0][0]:+.1f}s.jpg"), quality=85)
                    n_ctx += 1
                with open(audit_csv, "a", newline="") as fh:
                    csv.writer(fh).writerow([time.strftime("%Y-%m-%d %H:%M:%S"), mode,
                                             " ".join(fired), ev, n_ctx])
                if a.arm:
                    try: print(f"  *** TONE sent -> {send_tone(a.pi, a.port, a.token)}  [{', '.join(fired)}]  audit:{ev}")
                    except Exception as e: print(f"  !! TONE send failed: {e}")
                else:
                    print(f"  *** WOULD TONE [{', '.join(fired)}] (dry-run)  audit:{ev} ***")
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        cam.stop()

if __name__ == "__main__":
    main()
