# Hardware & wiring

## Bill of materials

See the table in the [README](../README.md#parts). The radio side is a CC1101
433 MHz module (this build used an **Ebyte E07-M1101D** with an SMA antenna) and
8 jumper wires to a Raspberry Pi.

## CC1101 → Raspberry Pi wiring (SPI0 / CE0)

Wire with the Pi **powered off**. Pin numbers are physical header pins.

| CC1101 pin | Signal | → Pi physical pin | Pi GPIO |
|-----------:|--------|------------------:|---------|
| VCC | 3.3 V | **1** | — |
| GND | ground | 25 | — |
| SCK | SPI clock | 23 | GPIO11 |
| MOSI | SPI MOSI | 19 | GPIO10 |
| MISO | SPI MISO | 21 | GPIO9 |
| CSN | SPI chip select | 24 | GPIO8 (CE0) |
| GDO0 | data (RX/TX) | 22 | GPIO25 |
| GDO2 | (unused) | 18 | GPIO24 |

> **VCC must go to physical pin 1 (3.3 V).** Pin 2 next to it is 5 V and will
> destroy the module. The E07-M1101D's own pin order is
> `1 GND, 2 VCC, 3 GDO0, 4 CSN, 5 SCK, 6 MOSI, 7 MISO, 8 GDO2` — check the
> silkscreen on your board, orders vary between vendors.

GND on pin 25 (rather than pin 6) keeps all eight wires grouped at the bottom of
the header and leaves pin 6 free for a case fan.

## First boot

1. Flash **Raspberry Pi OS Lite (64-bit)** with Raspberry Pi Imager. In the
   settings: hostname `dogpi`, enable SSH (key auth recommended), set Wi-Fi.
2. Boot with nothing wired; confirm `ssh <user>@dogpi.local`.
3. Enable SPI and reboot:
   ```bash
   sudo raspi-config nonint do_spi 0
   sudo reboot
   ```
4. Install dependencies:
   ```bash
   sudo apt update && sudo apt install -y python3-spidev python3-lgpio git
   ```
5. Power off, wire the CC1101, screw on the antenna, power back on.
6. Copy `pi/` to `~/dogcollar` and verify the chip:
   ```bash
   python3 ~/dogcollar/cc1101_check.py
   # PARTNUM=0x00, VERSION=0x14 → CC1101 detected, wiring good
   ```
