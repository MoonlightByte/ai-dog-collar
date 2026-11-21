#!/usr/bin/env python3
"""Detect the target (black) dog and decide if it is UP ON a forbidden surface.

Approach (no custom training): stock YOLO *segmentation* finds dogs -> sample
color from only the dog's pixels (black vs grey) -> check whether the dog's
pixel mask overlaps a surface zone (gate top / counter / island). Using the
pixel mask (not the bounding box) is what makes "reared up on the gate" work:
the box bottom is his hind feet on the floor, but his mask reaches the surface.

Usage:
    python3 detect.py IMAGE [IMAGE ...] [--model yolo11x-seg.pt] [--save]
"""
import argparse, json, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ZONES = json.load(open(os.path.join(HERE, "zones.json")))["zones"]

# --- tunables ---
BLACK_V_MAX = 85     # mean brightness (0-255) of the DOG'S OWN pixels below this => black
IMGSZ       = 1280   # input size; dark dog needs >=1280
CONF        = 0.25
ZONE_COVER  = 0.08   # dog mask covers >=8% of a zone's area => touching that surface
DOG_IN_ZONE = 0.10   # OR >=10% of the dog's pixels fall inside the zone

def poly_mask(pts_norm, w, h, normalized=True):
    m = Image.new("L", (w, h), 0)
    pts = [(x*w, y*h) if normalized else (x, y) for x, y in pts_norm]
    ImageDraw.Draw(m).polygon(pts, fill=1)
    return np.asarray(m, dtype=bool)

def analyze(img_path, model, save=False):
    im = Image.open(img_path).convert("RGB"); W, H = im.size
    arr = np.asarray(im)
    zmask = {n: poly_mask(z["poly"], W, H) for n, z in ZONES.items()}
    zarea = {n: max(int(m.sum()), 1) for n, m in zmask.items()}

    res = model(img_path, conf=CONF, imgsz=IMGSZ, verbose=False)[0]
    names = res.names
    dogs = []
    if res.masks is not None:
        for b, xy in zip(res.boxes, res.masks.xy):
            if names[int(b.cls)] != "dog" or len(xy) < 3:
                continue
            dm = poly_mask(xy, W, H, normalized=False)
            dm_n = max(int(dm.sum()), 1)
            meanV = float(arr[dm].mean()) if dm.any() else 255.0
            is_black = meanV < BLACK_V_MAX
            hits = {}
            for n, zm in zmask.items():
                inter = int((dm & zm).sum())
                if inter:
                    hits[n] = (inter / zarea[n], inter / dm_n)  # zone_cover, dog_in_zone
            dogs.append(dict(box=tuple(int(v) for v in b.xyxy[0].tolist()),
                             conf=float(b.conf), meanV=meanV, is_black=is_black,
                             mask=dm, hits=hits))

    fired = []
    for d in dogs:
        if not d["is_black"]:
            continue
        for n, (zc, di) in d["hits"].items():
            if zc >= ZONE_COVER or di >= DOG_IN_ZONE:
                fired.append((n, zc, di))

    print(f"\n=== {os.path.basename(img_path)} ({W}x{H}) ===")
    if not dogs:
        print("  no dog detected")
    for i, d in enumerate(dogs):
        tag = "BLACK(target)" if d["is_black"] else "grey/other"
        print(f"  dog{i}: conf={d['conf']:.2f} dogV={d['meanV']:.0f} {tag}")
        for n,(zc,di) in sorted(d["hits"].items(), key=lambda kv:-max(kv[1])):
            m = "  <-- ON SURFACE" if (zc>=ZONE_COVER or di>=DOG_IN_ZONE) and d["is_black"] else ""
            print(f"       {n:20s} zone_cover={zc:.2f} dog_in_zone={di:.2f}{m}")
    print(f"  >>> TRIGGER: {'YES -> '+', '.join(n for n,_,_ in fired) if fired else 'no'}")

    if save:
        over = im.copy(); d = ImageDraw.Draw(over, "RGBA")
        try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        except Exception: font = ImageFont.load_default()
        for n, z in ZONES.items():
            c = (255,40,40) if z["type"]=="gate_top" else (0,220,80)
            d.polygon([(x*W,y*H) for x,y in z["poly"]], fill=c+(55,), outline=c+(255,))
        for dog in dogs:
            col = (255,235,0) if dog["is_black"] else (120,160,255)
            ys,xs = np.where(dog["mask"])
            if len(xs): d.rectangle((xs.min(),ys.min(),xs.max(),ys.max()), outline=col+(255,), width=4)
        verdict = "TRIGGER: "+", ".join(n for n,_,_ in fired) if fired else "no trigger"
        d.text((20,20), verdict, fill=(255,255,255,255), font=font, stroke_width=3, stroke_fill=(0,0,0,255))
        out = os.path.splitext(img_path)[0] + ".annot.jpg"
        over.save(out, quality=90); print(f"  saved {out}")
    return fired

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("--model", default="yolo11x-seg.pt")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    from ultralytics import YOLO
    model = YOLO(a.model)
    for p in a.images:
        analyze(p, model, save=a.save)
