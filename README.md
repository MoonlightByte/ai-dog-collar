# ai-dog-collar

A local, low-latency system that watches gates/doors with cameras and gives a
dog an **audible tone** (and optionally a vibration) correction the instant it
jumps up — so the correction lines up with the behavior. Vision runs on a PC;
a Raspberry Pi drives a 433 MHz radio that talks to an off-the-shelf training
collar.

> **Status:** Working end to end. The Pi triggers the collar's **tone** over RF
> (reverse-engineered, software only, no hardware mod), and a GPU vision app
> watches the camera and fires a tone the moment the target dog is up on a gate
> or counter — validated on real footage, running live on a laptop GPU. See
> [docs/](docs/).

## Please read first

This project automates a **tone/vibration** deterrent only. **Automated shock is
intentionally out of scope** — a camera detector will occasionally false-trigger,
and an automatic shock on a false positive is both unfair to the dog and
counter-productive for training. See **[docs/SAFETY.md](docs/SAFETY.md)**. Do this
only with **your own collar and your own dog**, on your own property.

## How it works

```
 Camera(s)  --Wi-Fi/RTSP-->  PC (vision: is it the dog? is it jumping?)
                                     |  "TONE" over LAN (TCP)
                                     v
                              Raspberry Pi  -->  CC1101 433.92 MHz  -->  collar
```

- The **PC** does all the heavy lifting (video + a small detection model).
- The **Pi** does one job: receive a `TONE` command and key the radio. It keeps
  a climbing counter, enforces a cooldown, and logs every fire.

## Parts

| Qty | Part | Notes |
|----:|------|-------|
| 1 | Raspberry Pi 4 (a Pi 3 also works) | Runs the radio service |
| 1 | microSD card, 8 GB+ | Raspberry Pi OS Lite (64-bit) |
| 1 | CC1101 433 MHz module + SMA antenna | e.g. Ebyte E07-M1101D; **3.3 V only** |
| 8 | Female–female jumper wires | CC1101 ↔ Pi GPIO |
| 1 | 433 MHz training collar + remote | This build targets an **AIKEEP** collar (FCC ID `2AYAF-OTB3`, 433.92 MHz). Others use the same approach with different frame bits. |
| 1–2 | Wi-Fi cameras with local **RTSP** | For the vision phase (e.g. TP-Link Tapo). One high, wide camera can cover a whole room. |
| 1 | PC with an **NVIDIA GPU** | Runs the detector (developed on an RTX 4080 laptop; Windows+WSL2 or Linux) |

Total radio/Pi side: roughly **$15–20** plus the Pi and collar you likely own.

## Quick start (collar control)

1. Flash Raspberry Pi OS Lite, enable SSH + Wi-Fi, hostname `dogpi`.
2. Enable SPI: `sudo raspi-config nonint do_spi 0 && sudo reboot`.
3. Install deps: `sudo apt install -y python3-spidev python3-lgpio`.
4. Wire the CC1101 — see **[docs/01-hardware.md](docs/01-hardware.md)**.
5. Copy `pi/` to `~/dogcollar` on the Pi and verify the chip:
   `python3 cc1101_check.py` → should detect the CC1101.
6. Fire a tone: `python3 collar_tx.py` (collar nearby, off the dog). It should beep.
7. Run as a service and trigger from the PC — see
   **[docs/03-collar-control.md](docs/03-collar-control.md)**.

## Quick start (vision + app)

On the PC with the GPU, once the collar side above works:

1. Install PyTorch with CUDA for your GPU, then `pip install -r requirements.txt`.
2. Set up a camera and its RTSP credentials — **[docs/05-cameras.md](docs/05-cameras.md)**
   (`cp pc/camera.sample.json pc/camera.local.json` and edit).
3. Mark your no-go surfaces and build the zones —
   **[docs/06-zones.md](docs/06-zones.md)** (paint a snapshot, run `pc/make_zones.py`).
4. Point the app at your Pi (`pc/collar.local.json` or `DOGPI_HOST`).
5. `./start.sh` → open **http://localhost:8800**. It starts in **dry-run**
   (detects + logs, sends nothing). Review the audit log, then **Arm** it to send
   tones. Full walkthrough: **[docs/07-app.md](docs/07-app.md)**.

No model is trained: stock YOLO segmentation finds dogs, color tells the target
dog apart, and a per-zone overlap check decides "up on a surface." See
**[docs/04-vision.md](docs/04-vision.md)**.

## Docs

- [01-hardware.md](docs/01-hardware.md) — parts, wiring, first-boot
- [02-rf-capture.md](docs/02-rf-capture.md) — how the remote's signal was
  captured and decoded (the reproducible methodology)
- [03-collar-control.md](docs/03-collar-control.md) — transmit recipe + Pi service
- [04-vision.md](docs/04-vision.md) — how the detector decides "up on a surface"
- [05-cameras.md](docs/05-cameras.md) — cameras, placement, and RTSP setup
- [06-zones.md](docs/06-zones.md) — programming the scene (marking no-go surfaces)
- [07-app.md](docs/07-app.md) — running the detector + dashboard, and going live
- [SAFETY.md](docs/SAFETY.md) — scope, ethics, and electrical safety

## License

MIT — see [LICENSE](LICENSE).
