#!/usr/bin/env python3
"""Turn a hand-marked snapshot into zones.json.

Workflow:
  1. Grab a still from your camera (see docs/05-cameras.md), e.g.:
       ffmpeg -rtsp_transport tcp -i "rtsp://user:pass@CAM_IP:554/stream1" \
              -frames:v 1 scene.jpg
  2. Open scene.jpg in any image editor. Paint the OFF-LIMITS SURFACE TOPS
     solid GREEN, and draw a RED line/fill along each GATE's TOP RAIL. Save
     as a PNG (keep the same framing/size).
  3. Run:  python3 make_zones.py scene_marked.png --out zones.json --preview preview.jpg

Green blobs become 'counter' zones, red blobs become 'gate_top' zones. They are
named counter_1.., gate_1.. by position (left->right); rename them in the JSON
to taste. Polygons are stored normalized (0-1) so they work at any resolution.
"""
import argparse, json, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from scipy.spatial import ConvexHull

ap = argparse.ArgumentParser()
ap.add_argument("image", help="hand-marked PNG (green = counters, red = gate tops)")
ap.add_argument("--out", default="zones.json")
ap.add_argument("--preview", default=None, help="write an overlay JPG to check the result")
ap.add_argument("--min-area", type=int, default=1500, help="ignore blobs smaller than this (px)")
ap.add_argument("--camera", default="downstairs")
a = ap.parse_args()

im = np.asarray(Image.open(a.image).convert("RGB")).astype(int)
H, W = im.shape[:2]
R, G, B = im[..., 0], im[..., 1], im[..., 2]
green = (G > 90) & (G - R > 25) & (G - B > 25)
red   = (R > 150) & (R - G > 85) & (R - B > 85)

def blobs(mask, min_area):
    lab, n = ndimage.label(mask)
    out = []
    for i in range(1, n + 1):
        ys, xs = np.where(lab == i)
        if len(xs) < min_area:
            continue
        pts = np.column_stack([xs, ys])
        try:
            poly = pts[ConvexHull(pts).vertices]
        except Exception:
            poly = np.array([[xs.min(), ys.min()], [xs.max(), ys.min()],
                             [xs.max(), ys.max()], [xs.min(), ys.max()]])
        out.append({"cx": xs.mean(), "poly": [[round(x / W, 4), round(y / H, 4)] for x, y in poly]})
    out.sort(key=lambda r: r["cx"])          # left -> right
    return out

zones = {}
for i, z in enumerate(blobs(green, a.min_area), 1):
    zones[f"counter_{i}"] = {"type": "counter", "poly": z["poly"]}
for i, z in enumerate(blobs(red, max(120, a.min_area // 10)), 1):
    zones[f"gate_{i}"] = {"type": "gate_top", "poly": z["poly"]}

json.dump({"camera": a.camera, "view_w": W, "view_h": H,
           "note": "normalized polygons; type gate_top=gate rail, counter=surface top",
           "zones": zones}, open(a.out, "w"), indent=1)
print(f"wrote {a.out}: {list(zones)}")

if a.preview:
    img = Image.open(a.image).convert("RGB"); d = ImageDraw.Draw(img, "RGBA")
    try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    except Exception: font = ImageFont.load_default()
    for name, z in zones.items():
        c = (255, 40, 40) if z["type"] == "gate_top" else (0, 220, 80)
        pts = [(x * W, y * H) for x, y in z["poly"]]
        d.polygon(pts, fill=c + (70,), outline=c + (255,))
        d.text((min(p[0] for p in pts), min(p[1] for p in pts) - 30), name,
               fill=(255, 255, 255, 255), font=font, stroke_width=3, stroke_fill=(0, 0, 0, 255))
    img.save(a.preview, quality=90)
    print(f"wrote preview {a.preview}")
