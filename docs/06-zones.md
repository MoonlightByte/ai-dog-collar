# Programming the scene (zones)

A **zone** is a polygon on the camera image marking a surface the dog must stay
off: a **gate top** or a **counter/island**. The detector fires only when the
target dog's pixels overlap one of these zones — so defining them well is how you
teach the system *your* kitchen. Zones live in `pc/zones.json`.

Polygons are stored **normalized** (each point is `0–1` of the frame width/height),
so the same file works on any stream resolution.

## The easy way: mark a photo, extract by color

1. Grab a still from the camera in its final mounted position:
   ```bash
   ffmpeg -rtsp_transport tcp -i "rtsp://USER:PASS@CAM_IP:554/stream1" -frames:v 1 scene.jpg
   ```
2. Open `scene.jpg` in any image editor (Paint, GIMP, Photoshop, Preview…). Then:
   - **Fill each off-limits surface top solid GREEN** (counters, island, stove top).
   - **Draw a RED line (or thin fill) along each gate's TOP RAIL** — the line the
     dog crosses when he rears up onto it.
   - Trace the surfaces as the camera sees them (they look like angled
     parallelograms, not rectangles — follow the real edges).
   - Save as a **PNG**, same size/framing as the still.
3. Extract the zones:
   ```bash
   python3 pc/make_zones.py scene_marked.png --out pc/zones.json --preview preview.jpg
   ```
   Green blobs become `counter` zones, red blobs become `gate_top` zones, named
   `counter_1..`, `gate_1..` left-to-right.
4. Open `preview.jpg` to check the outlines land on the real surfaces. Rename the
   zones in `pc/zones.json` to something meaningful (`island`, `gate_left`, …) if
   you like — names are just labels.

Tips: if a surface is missed, paint it more fully or lower `--min-area`. If a
stray green/red object in the scene gets picked up, edit it out of the marked PNG
(or delete that zone from the JSON).

## The manual way

Edit `pc/zones.json` directly (copy `pc/zones.sample.json`). Each zone is a name,
a `type` (`gate_top` or `counter`), and a `poly` list of `[x, y]` points in
`0–1` coordinates, clockwise. To read pixel coordinates, open the still in an
editor that shows a cursor position and divide by the image width/height.

```json
{
  "camera": "downstairs",
  "view_w": 2560, "view_h": 1440,
  "zones": {
    "gate_left": { "type": "gate_top", "poly": [[0.17,0.51],[0.29,0.52],[0.29,0.53],[0.17,0.52]] },
    "island":    { "type": "counter",  "poly": [[0.54,0.66],[0.75,0.63],[0.78,0.70],[0.57,0.74]] }
  }
}
```

## Check your zones against reality

Run the still-image detector on a photo of the dog actually up on a surface, and
on photos of him on the floor nearby, and confirm the verdicts:

```bash
python3 pc/detect.py on_the_island.jpg on_the_floor.jpg --save
```
It prints which zone (if any) the dog overlaps and writes an annotated
`*.annot.jpg`. You want **TRIGGER: yes** when he's up and **no** when he's on the
floor. Tune the thresholds at the top of `pc/detect.py` if needed:
- `BLACK_V_MAX` — brightness cutoff for "is this the dark/target dog" (raise for a
  lighter target, lower to be stricter). If your dogs aren't told apart by
  darkness, see the note in [04-vision.md](04-vision.md).
- `ZONE_COVER` / `DOG_IN_ZONE` — how much overlap counts as "on the surface."
- `IMGSZ` — detection input size; keep ≥1280 for a small/dark dog.

Once the zones look right, run the app — **[07-app.md](07-app.md)**.
