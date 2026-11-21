# RF capture & decode (methodology)

This is the reproducible process used to understand the collar remote. It works
for any button; the examples use the **tone** button.

## 1. Find the signal

The remote's FCC grant (FCC ID `2AYAF-OTB3`) lists **433.92 MHz, FSK**. Confirm
by receiving:

```bash
python3 capture.py 45 tone.json 433.92 fsk 47   # press the button during this
```

`capture.py` puts the CC1101 in async FSK receive, logs an RSSI timeline, and
records the demodulated edges from GDO0. A button press shows as a jump from the
~-90 dBm noise floor to ~-20 dBm. If you see nothing, the remote may be asleep
(press once to wake it) or out of range.

`sweep.py` (RSSI across a frequency range) and `probe.py` (frequency-offset
estimate) help locate the exact centre and modulation if the FCC data is unknown.

## 2. Decode the frame

The tone button decodes to a **97-symbol, pulse-distance-coded frame**:

- Each symbol = a **HIGH pulse of ~206 µs**, then a **LOW gap**: ~206 µs = bit
  `0`, ~407 µs = bit `1`.
- Frames repeat while the button is held, separated by a ~1207 µs gap.

`multicap.py` cycles through receiver settings (centre frequency × deviation)
while you hold the button, so you can find the setting that demodulates cleanly
and dump the repeated frames.

## 3. What changes between presses

Comparing many presses: **89 of 97 bits are constant**. The only variation is a
**4-bit counter** that appears twice in the frame:

- bits `[37:41]` = `(C + 3) & 0xF`
- bits `[85:89]` = `C & 0xF`

`C` increments by 1 each press and wraps at 16. The duplicated copy is almost
certainly the receiver's integrity check. This is **not** a cryptographic rolling
code — it is a short de-duplication counter, so the frame can be synthesized.

The collar only accepts a counter that is **ahead** of the last one it saw, so a
transmitter must keep a persistent, always-incrementing counter and never resend
a stale value.

## 4. Different buttons

Other buttons (vibration, etc.) use the **same structure and counter**; only
some of the "constant" button-code bits differ. Capture a button the same way
and diff its frame against the tone frame to find those bits.

> Decoding your collar is reverse-engineering of a device you own — fine. See
> [SAFETY.md](SAFETY.md) for why automating *shock* is deliberately out of scope.
