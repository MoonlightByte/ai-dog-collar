# Collar control (transmit + service)

## Transmit recipe

The CC1101 reproduces the frame using **asynchronous FSK** plus DMA-timed GPIO
("wave") output on GDO0. Working configuration for the AIKEEP collar:

| Setting | Value |
|---------|-------|
| Frequency | 433.92 MHz |
| Modulation | FSK |
| Deviation (`DEVIATN`) | `0x40` (~25 kHz) |
| Output power (`PATABLE[0]`) | `0xC0` |
| Packet mode (`PKTCTRL0`) | `0x32` (async, infinite) |
| **`IOCFG0` during TX** | **`0x2E` (hi-Z)** |

> **The hi-Z step is essential.** If GDO0 stays configured as a chip output
> (`0x0D`) while the Pi also drives it, the two fight and the collar hears
> nothing. Setting `IOCFG0 = 0x2E` lets the Pi's wave drive the modulator
> cleanly. Finding the right **deviation** (`0x40`) was the other key — nearby
> values like `0x24` do not trigger this collar.

Each "press" is the frame repeated ~6 times. Space presses **≥ 3 s apart**:
back-to-back frames arrive while the collar is still beeping and get dropped
(measured reliability: 8/8 presses at 3 s spacing, after the counter syncs).

Fire one tone (collar nearby, off the dog):

```bash
python3 collar_tx.py        # prints the counter used; collar beeps
```

`collar_tx.py` holds the locked-in config and the persistent counter
(`~/dogcollar/counter.txt`). It can send **TONE** or **VIBE**
(`python3 collar_tx.py vibe`). The two frames are identical except for a few
button-code bits. **The shock frame is deliberately not implemented** — see
[SAFETY.md](SAFETY.md).

## Pi service

`tone_service.py` is a small LAN TCP server (default port 8737). It enforces a
cooldown, keeps the counter, and logs every fire to `~/dogcollar/tone.log`.

Protocol (newline-terminated):

```
PING <token>   -> PONG
TONE <token>   -> OK TONE <counter> | COOLDOWN <secs> | BADAUTH
VIBE <token>   -> OK VIBE <counter> | COOLDOWN <secs> | BADAUTH
```

Install as a systemd service so it starts on boot:

```bash
# secret stays out of git; the service refuses to start without it
echo "DOGPI_TOKEN=$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')" > ~/dogcollar/dogpi.env
chmod 600 ~/dogcollar/dogpi.env
sudo cp ~/dogcollar/dogpi-tone.service /etc/systemd/system/
sudo systemctl enable --now dogpi-tone
systemctl status dogpi-tone
```

Trigger from the PC:

```bash
python3 pc/send_tone.py ping          # -> PONG
python3 pc/send_tone.py tone          # -> OK TONE 7  (collar beeps)
```

Put the same token in `pc/collar.local.json` (or `DOGPI_TOKEN`) on the PC. There
is no built-in default token. The cooldown in the service is a
second safety layer independent of the PC.
