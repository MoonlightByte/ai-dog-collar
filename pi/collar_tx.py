"""Collar transmit — the one place frames are built and sent.

SAFETY: this module can ONLY send the non-painful stimuli TONE and VIBE.
The shock frame is deliberately NOT implemented. Do not add it, and never let
the automated vision trigger call anything but TONE/VIBE. See docs/SAFETY.md.
"""
import os
import time

import lgpio

from cc1101 import CC1101, GDO0_GPIO, SIDLE, STX

# Locked-in working RF config (see memory: project-dogcollar-rf)
FREQ_MHZ = 433.92
DEVIATN  = 0x40      # ~25 kHz — the value that the collar accepts
POWER    = 0xC0
INVERT   = 0
REPEATS  = 6         # frame repeats per "press" (~0.3s hold)

# 97-symbol pulse-distance frames. 4-bit counter at [37:41]=(C+offset)&0xF and
# [85:89]=C&0xF; buttons differ only in a few constant bits and the first-copy
# offset. Captured from the AIKEEP remote.
BUTTONS = {
    "TONE": {"offset": 3,
             "tpl": "0010101010101010101110100101001010000XXXX11000100010000001000001010001101000000010011XXXX00000000"},
    "VIBE": {"offset": 6,
             "tpl": "0010101010101010101110100101001010001XXXX11000001010000001000001010001101000000010100XXXX00000000"},
    # NOTE: SHOCK is intentionally not defined here. Do not add it.
}
HIGH_US, ZERO_US, ONE_US, GAP_US = 206, 206, 407, 1207
MASK = 1 << 0

CFILE = os.path.expanduser("~/dogcollar/counter.txt")

def _next_counter():
    try:
        v = int(open(CFILE).read().strip())
    except Exception:
        v = 0
    open(CFILE, "w").write(str((v + 1) & 0xFFFF))
    return v & 0xF

def _pulses(button, counter):
    spec = BUTTONS[button]
    hi, lo = (0, MASK) if INVERT else (MASK, 0)
    b = list(spec["tpl"])
    b[37:41] = list(format((counter + spec["offset"]) & 0xF, "04b"))
    b[85:89] = list(format(counter & 0xF, "04b"))
    p = []
    for bit in b:
        p.append(lgpio.pulse(hi, MASK, HIGH_US))
        p.append(lgpio.pulse(lo, MASK, ONE_US if bit == "1" else ZERO_US))
    p.append(lgpio.pulse(lo, MASK, GAP_US))
    return p, lo

def send(button="TONE"):
    """Transmit one press of TONE or VIBE. Returns the 4-bit counter used."""
    if button not in BUTTONS:
        raise ValueError(f"unsupported button {button!r} (allowed: {list(BUTTONS)})")
    counter = _next_counter()
    pulses, lo = _pulses(button, counter)
    r = CC1101()
    r.setup(FREQ_MHZ, power=POWER, mod="fsk", dev=DEVIATN)
    r.write(0x02, 0x2E)                 # IOCFG0 hi-Z: required, else collar hears nothing
    r.strobe(SIDLE); r.strobe(STX); time.sleep(0.002)
    h = lgpio.gpiochip_open(0)
    lgpio.group_claim_output(h, [GDO0_GPIO], [lo])
    try:
        for _ in range(REPEATS):
            lgpio.tx_wave(h, GDO0_GPIO, pulses)
            while lgpio.tx_busy(h, GDO0_GPIO, lgpio.TX_WAVE):
                time.sleep(0.001)
        lgpio.group_write(h, GDO0_GPIO, lo, MASK)
    finally:
        lgpio.group_free(h, GDO0_GPIO)
        lgpio.gpiochip_close(h)
        r.strobe(SIDLE); r.close()
    return counter

def send_tone():
    return send("TONE")

def send_vibe():
    return send("VIBE")

if __name__ == "__main__":
    import sys
    btn = (sys.argv[1].upper() if len(sys.argv) > 1 else "TONE")
    print(f"{btn} sent, counter =", send(btn))
