# Safety & scope

## Use only on your own dog and collar

This project is for correcting one behavior (jumping on gates/doors) on **your
own dog**, with **your own collar**, on **your own property**. Triggering a
training collar you don't own — or one on an animal that isn't yours — is abuse
and likely illegal. Don't.

## Tone/vibration only — shock stays manual

The automated, camera-triggered path only ever sends a **tone** (and optionally a
**vibration**). This is a deliberate design rule, for two practical reasons:

1. **False positives are inevitable.** A vision model will sometimes misfire
   (shadows, the other pets, odd poses). A mistaken *beep* is harmless; a
   mistaken *shock* is not.
2. **Welfare and effectiveness.** An unpredictable shock the dog can't associate
   with its own action creates fear and can make the gate behavior worse.

If you use shock at all, it should be a **deliberate, human-in-the-loop** decision
in the moment — never fired automatically by the detector. This repository does
**not** ship a turnkey shock transmitter. The capture/decode method is documented
for completeness, but automating shock is out of scope here.

Start every deployment in **dry-run** mode (log "would have fired", collar off),
review the events, and only enable the tone once false triggers are near zero.

## Electrical safety (CC1101)

- The CC1101 module is **3.3 V only**. Power it from the Pi's **3.3 V** pin
  (physical pin 1), never 5 V, or you will destroy it.
- Wire it with the Pi **powered off**. Double-check VCC and GND before power-on.
- Always screw the antenna on before transmitting.

## Testing the collar

- Keep the collar **on a table, off the dog, and not against your skin** while
  capturing or transmitting.
- Set the remote to the **lowest level** and disable bark mode during tests.

## Radio / legal

433.92 MHz is a license-free band in many regions (ISM / SRD), but the exact
rules (duty cycle, power) vary by country. You are responsible for complying with
your local regulations. Keep transmissions short and low-power (this project does).
