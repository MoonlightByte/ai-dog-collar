#!/usr/bin/env python3
"""Run the segmentation detector over a folder of frames and log the verdict.

Saves an annotated .annot.jpg ONLY for frames that TRIGGER (so false positives
are easy to eyeball) and writes a CSV of every processed frame.
    python3 batch.py data/live --step 5 --model yolo11x-seg.pt
"""
import argparse, glob, os, csv
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import detect  # reuse poly_mask, ZONES, thresholds

ap = argparse.ArgumentParser()
ap.add_argument("folder")
ap.add_argument("--step", type=int, default=5)
ap.add_argument("--model", default="yolo11x-seg.pt")
a = ap.parse_args()

from ultralytics import YOLO
model = YOLO(a.model)
Z = detect.ZONES
frames = sorted(glob.glob(os.path.join(a.folder, "*.jpg")))[::a.step]
print(f"{len(frames)} frames (every {a.step})")

rows, fires = [], []
for idx, p in enumerate(frames):
    im = Image.open(p).convert("RGB"); W, H = im.size
    arr = np.asarray(im)
    zmask = {n: detect.poly_mask(z["poly"], W, H) for n, z in Z.items()}
    zarea = {n: max(int(m.sum()), 1) for n, m in zmask.items()}
    res = model(p, conf=detect.CONF, imgsz=detect.IMGSZ, verbose=False)[0]
    nblack = nother = 0; fired = []; dogs = []
    if res.masks is not None:
        for b, xy in zip(res.boxes, res.masks.xy):
            if res.names[int(b.cls)] != "dog" or len(xy) < 3: continue
            dm = detect.poly_mask(xy, W, H, normalized=False)
            dm_n = max(int(dm.sum()), 1)
            meanV = float(arr[dm].mean()) if dm.any() else 255.0
            black = meanV < detect.BLACK_V_MAX
            nblack += black; nother += (not black)
            dogs.append((dm, black))
            if black:
                for n, zm in zmask.items():
                    inter = int((dm & zm).sum())
                    if inter and (inter/zarea[n] >= detect.ZONE_COVER or inter/dm_n >= detect.DOG_IN_ZONE):
                        fired.append(n)
    fired = sorted(set(fired))
    rows.append((os.path.basename(p), nblack, nother, "|".join(fired)))
    if fired:
        fires.append((p, fired))
        over = im.copy(); d = ImageDraw.Draw(over, "RGBA")
        try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        except Exception: font = ImageFont.load_default()
        for n, z in Z.items():
            c = (255,40,40) if z["type"]=="gate_top" else (0,220,80)
            d.polygon([(x*W,y*H) for x,y in z["poly"]], fill=c+(55,), outline=c+(255,))
        for dm, black in dogs:
            col = (255,235,0) if black else (120,160,255)
            ys,xs = np.where(dm)
            if len(xs): d.rectangle((int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())), outline=col+(255,), width=4)
        d.text((20,20), "TRIGGER: "+", ".join(fired), fill=(255,255,255,255), font=font, stroke_width=3, stroke_fill=(0,0,0,255))
        over.save(os.path.splitext(p)[0]+".annot.jpg", quality=88)
    if idx % 20 == 0: print(f"  {idx}/{len(frames)} ...")

with open(os.path.join(a.folder, "verdicts.csv"), "w", newline="") as f:
    csv.writer(f).writerows([("frame","n_black","n_other","fired")] + rows)

bframes = sum(1 for r in rows if r[1] > 0)
print(f"\nDONE. frames with black dog: {bframes}/{len(frames)}")
print(f"frames that TRIGGERED: {len(fires)}")
for p, fz in fires: print(f"  {os.path.basename(p)} -> {', '.join(fz)}")
