# Vision pipeline (in progress)

The PC watches the cameras and decides when to ask the Pi for a tone. Design:

```
RTSP camera(s) --> newest-frame reader --> detector --> target check --> posture
                                                                           |
                                            3 consecutive "jumping" frames  |
                                                                           v
                                                           TONE to Pi (+ cooldown)
```

## Cameras

- Two Wi-Fi cameras with a **local RTSP** stream (this build uses TP-Link Tapo).
  One covers the gates, one the sliding door; mount the door camera **outside**
  if the dog jumps the glass from outside, to avoid reflections.
- Angle each camera so it sees the **whole dog and the gate/door surface** — you
  need to tell "standing near it" from "paws up on it."
- Good lighting or IR at night; a black dog on a dark background is the hard case.
- Measure glass-to-tone latency: point a camera at a stopwatch on the PC screen.
  Target < ~500 ms end to end; budget < ~300 ms for the camera itself.

## Detection

1. Read each RTSP stream, always processing the **newest** frame (drop backlog).
2. Detect dogs with a small **YOLO** model (Ultralytics) on the GPU.
3. **Is it the target dog?** Fine-tune on footage of each pet so the other
   animals never trigger.
4. **Is it jumping?** Classify posture inside a cropped gate/door zone:
   normal vs. reared / paws-on-surface.
5. Require ~3 consecutive agreeing frames (~100–150 ms) before firing.
6. Send `TONE` to the Pi, save a clip, start a cooldown.

## Rollout

1. Record a week of normal activity and real jumps from the installed views.
2. Label clips (target-jumping / target-normal / other-animal / nobody) and train.
3. Test on held-out recordings.
4. Run in **dry-run** mode (log "would have fired", collar off) for several days;
   review every event.
5. Go live with **tone only** once false triggers are near zero. Tune cooldown,
   confidence, and zones from the logs.

See [SAFETY.md](SAFETY.md) — the automated loop never fires shock.

## Data collection (available now)

`pc/collect.py` pulls timestamped frames from a Tapo camera over RTSP into
`data/<camera>/` for building a training set. Camera credentials live in
`pc/camera.local.json` (gitignored); copy `pc/camera.sample.json` and fill it in.

```bash
cp pc/camera.sample.json pc/camera.local.json   # then edit with your camera account
python3 pc/collect.py downstairs --interval 2    # a frame every 2s until Ctrl-C
```

Run it while the dogs are active (especially around the gate/door) to gather
both "normal" and "jumping" examples, then label and fine-tune. Captured frames
and video are gitignored — they stay local and private.

## Validated approach (2026-11-20)

No custom training needed. Pipeline: **YOLO segmentation (yolo11x-seg @ 1280px)
detects dogs -> sample color from the dog's own mask pixels (black vs grey) ->
test whether that mask overlaps a surface zone**. Using the pixel mask (not the
bounding box) is what makes "reared up on a gate" work.

- `pc/detect.py IMAGE... --save` — single images, prints per-zone overlap + verdict.
- `pc/batch.py FOLDER --step N` — runs a folder on GPU, saves an annotated image
  only for frames that TRIGGER, writes verdicts.csv.

Validated on ~3.5 min of real footage (person + dog roaming): black dog seen in
111 frames, 6 triggered — all 6 were genuine "up on a surface" moments; zero
false triggers on ~105 floor frames; the person never triggered. The dark dog
needs the x-model at >=1280px (nano/default miss it). Runs real-time on a 4080.
