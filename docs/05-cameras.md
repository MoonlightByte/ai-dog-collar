# Cameras & RTSP

The vision side needs one or more Wi-Fi cameras that expose a **local RTSP**
stream (no cloud dependency, low latency). This build uses a **TP-Link Tapo**
camera, but any camera with an RTSP URL works.

## Placement — this matters more than the camera

Mount the camera **high and angled down** so it sees the **tops of the gates and
counters** with open space above them. The detector decides "up on a surface"
vs. "on the floor" from where the dog's body sits in the frame, and a high,
downward view separates those two cleanly. A low, across-the-room view (e.g. on a
counter) fails: foreground furniture hides the gates and "on the floor in front
of a counter" looks the same as "on the counter."

One camera mounted high can cover a whole open-plan kitchen (both gates + all
counters). Use a second camera for areas the first can't see (e.g. a sliding
door in another room).

Other placement notes:
- Good light, or IR at night — a black dog on a dark background is the hard case.
- If the dog jumps a glass door **from outside**, mount that camera outside to
  avoid reflections.
- Put the PC on Ethernet and give the cameras strong Wi-Fi.

## Enable RTSP (TP-Link Tapo)

1. Set the camera up in the **Tapo** app and update its firmware.
2. In the app: **camera → Settings → Advanced Settings → Camera Account** — create
   a **username and password**. This "Camera Account" is separate from your Tapo
   login and is what RTSP uses.
3. Find the camera's LAN IP (your router's client list, or the app).
4. The stream URLs are:
   - `rtsp://USER:PASS@CAM_IP:554/stream1` — main, full resolution
   - `rtsp://USER:PASS@CAM_IP:554/stream2` — sub, lower resolution

Use **stream1 (full res)** for detection — a dark dog needs the detail; the sub
stream is too small and misses him. Test the stream first:

```bash
ffplay "rtsp://USER:PASS@CAM_IP:554/stream1"        # or open it in VLC
# grab a single still (used for zone-marking, see 06-zones.md):
ffmpeg -rtsp_transport tcp -i "rtsp://USER:PASS@CAM_IP:554/stream1" -frames:v 1 scene.jpg
```

## Configure credentials (kept out of git)

Copy the sample and fill in your camera. This file is **git-ignored** so your
credentials never get committed:

```bash
cp pc/camera.sample.json pc/camera.local.json
# edit pc/camera.local.json:
```
```json
{
  "cameras": {
    "downstairs": {
      "ip": "192.168.1.50",
      "user": "YOUR_CAMERA_ACCOUNT_USER",
      "pass": "YOUR_CAMERA_ACCOUNT_PASS",
      "main": "stream1",
      "sub": "stream2"
    }
  }
}
```

`pc/collect.py` (frame grabber for building a test set) and the app both read
this file. Next: **[06-zones.md](06-zones.md)** to mark the no-go surfaces.
