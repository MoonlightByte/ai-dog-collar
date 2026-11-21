# The app (detector + dashboard)

`app/` is a self-contained application: it watches the camera on the GPU, shows a
live dashboard in your browser, and — when you arm it — sends a **tone** to the
collar the instant the target dog is up on a zone.

```
camera (RTSP) → newest frame → YOLO-seg → is it the dark dog? →
   does its mask overlap a zone? → N frames in a row → TONE to the Pi (+ cooldown)
```

The detection method (segmentation mask for color + zone overlap, model/size
choices) is explained in **[04-vision.md](04-vision.md)**. Automation only ever
sends **tone** — see **[SAFETY.md](SAFETY.md)**.

## Requirements

A PC with an NVIDIA GPU (this was developed on an RTX 4080 laptop; anything of
that class runs the `yolo11x-seg` model comfortably in real time). Works on
Windows via WSL2, or native Linux.

1. Install **PyTorch with CUDA** for your GPU from
   <https://pytorch.org/get-started/locally/> and confirm:
   ```bash
   python3 -c "import torch; print(torch.cuda.is_available())"   # True
   ```
2. Install the rest:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up the camera (**[05-cameras.md](05-cameras.md)**) and zones
   (**[06-zones.md](06-zones.md)**) so `pc/camera.local.json` and `pc/zones.json`
   exist.
4. Make sure the **Pi tone service** is running and reachable
   (**[03-collar-control.md](03-collar-control.md)**).

## Point it at your Pi

The app finds the Pi from (in order) `pc/collar.local.json`, environment
variables, then defaults. Easiest is the local file (git-ignored):

```json
{ "host": "192.168.1.50", "port": 8737, "token": "your-token" }
```
Or export `DOGPI_HOST` / `DOGPI_PORT` / `DOGPI_TOKEN`. The `token` must match the
Pi service's `DOGPI_TOKEN`.

## Run it

```bash
./start.sh
```
This serves the dashboard at **http://localhost:8800** (and opens your browser).
First start takes ~10 s to load the model and connect to the camera.

## The dashboard

- **Live view** — the camera with zones drawn (green = counters, red = gate tops)
  and a box on any detected dog; the caption shows mode, dog count, and the
  up-streak.
- **Status pills** — model ready, GPU %, **Pi online/offline**, FPS, uptime.
- **Mode** — starts in **DRY-RUN** (detects and logs, but sends nothing). The
  **Arm** button (with a confirm) switches to **ARMED · BEEP LIVE**, where each
  trigger sends a tone.
- **Test beep** — sends one tone to the collar now (use it with the collar in
  your hand to verify the whole chain).
- **Pause detection**, and sliders for **consecutive frames** (how many in a row
  before firing) and **cooldown** (seconds between tones).
- **Event audit log** — every fire with a thumbnail; click it to see the full
  annotated trigger frame plus the context frames from the ~½ second before.

Every fire is also written to `data/events/<timestamp>_<zone>/`
(`trigger.jpg` + context frames) and appended to `data/events/audit.csv`, so you
can review whether each tone was fair.

## Recommended way to go live

1. `./start.sh`, confirm the dashboard shows **Pi online** and live video.
2. Leave it in **DRY-RUN** for a while during normal activity. Review the audit
   log — you want fires only when the dog is genuinely up, and none when he's on
   the floor or when a person is near a surface. Tune zones/thresholds until that
   holds.
3. Hold the collar **in your hand** and click **Test beep** — confirm you hear it.
4. Click **Arm**. Coax the dog up on a surface and confirm it beeps and logs.
5. When you're satisfied it's fair, put the collar on the dog. Keep reviewing the
   audit log for a while.

## Command-line alternative

`pc/live_detect.py` is the same loop without the dashboard (dry-run by default,
`--arm` to send tones, writes the same `data/events` audit trail). Handy for a
headless box:
```bash
python3 pc/live_detect.py            # dry-run
python3 pc/live_detect.py --arm      # live (tone only)
```
