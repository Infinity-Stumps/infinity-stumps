# MCU choice & developer-onboarding model

**Decision (2026-05-14): stay on the Qorvo DWM3001C. Solve developer
onboarding by distributing pre-bootloadered boards — not by changing
silicon.**

## The question

Developer-onboarding friction: the nRF52833 needs an SWD probe + nRF
Connect SDK (Zephyr) to flash. There is no USB ROM bootloader, so a
*blank* board cannot be flashed over USB. We considered dropping the
DWM3001C for a **DWM3000** (UWB-only module) + an **Espressif ESP32-C6**
(USB ROM bootloader, Arduino / ESP-IDF ecosystem) to make the project
easier for open-source contributors to build and hack on.

## Why we stay on the DWM3001C

- **Ball-tag consistency.** The in-ball tag has the hardest power/size
  constraints in the system; nRF52-class silicon is the right fit there.
  ESP32 anchors + nRF ball = two MCU families, two toolchains, two
  firmware codebases — *worse* for contributors, not better.
- **Carrier-board elegance.** DWM3001C = pre-certified module, MCU<->UWB
  SPI internal, dev = production. DWM3000 + ESP32 means owning that SPI
  bus, placing two modules, a fatter board — permanent complexity for
  every builder, forever.
- **Battery life.** ESP32-C6 anchor modelled at **~130-210 days vs ~290**
  (DWM3001C). The UWB radio (DW3110) energy is identical; the loss is all
  in active-session MCU current. Standby is a wash (~52 µA vs ~50 µA —
  board housekeeping dominates, not the MCU). It breaks the "charge once
  per season" goal.
- **The onboarding problem has a cheaper fix** (below) — re-architecting
  the whole system to solve a one-time dev-setup step is the wrong lever.

## The onboarding model

- **Distribute pre-bootloadered boards.** Sell assembled / tested /
  flashed units at a sustaining margin, or otherwise provide pre-flashed
  boards. The one-time SWD bootloader flash happens at assembly /
  provisioning; the board then behaves like an Adafruit Feather
  (USB-flashable, UF2-style). This is the standard OSHW model — Adafruit,
  Sparkfun, Prusa all do exactly this, and CERN-OHL-S permits it.
- **The PCB fab can do the bootloader flash.** JLCPCB offers a PCBA
  firmware-flashing service — they program each board after assembly from
  a HEX/BIN you supply (~$8 setup + ~$8/hr labour). Requirements:
  accessible on-board SWD pads (the Tag-Connect TC2030 block) and a
  support confirmation that they can target the nRF52833 over SWD,
  including the APPROTECT `--recover` step. So fab + assembly + flash can
  be a single order — no in-house provisioning line needed. A standalone
  J-Link + scripted `nrfjprog` stays as the fallback and for dev boards.
- **Keep BOM / Gerbers / firmware fully public.** Self-builders get a free
  DIY path; only someone hand-assembling *and* doing bare-metal bring-up
  needs a ~£15 probe — and that person already owns one.
- **BLE DFU** already covers field firmware updates for the consumer path.
- **Going-vendor caveat:** selling hardware brings real obligations —
  finished-product EMC / CE / FCC marking, warranty, returns, inventory,
  support load. De-risk by starting on Tindie / via an existing shop
  before becoming a hardware company.

## Antenna-delay calibration is not vendor lock-in

It was briefly considered a vendor-only value-add; it is not:

- The DWM3001C is **factory-calibrated** for antenna delay (stored in
  OTP). The antenna is on-module; the carrier board adds none.
- Any residual **self-calibrates in the field**: the 8 anchors sit at
  Laws-of-Cricket positions and already run inter-anchor TWR for time
  sync — per-anchor delay solves by least-squares against the known
  geometry. Zero user effort, no jig, no known-distance procedure.

The pre-flashed board's value is assembly + bootloader + test + QC +
support + "works out of the box" — not an artificial calibration moat.

## Open / not yet decided

- **Route USB D+/D-/VUSB** from the module to the USB-C connector?
  Enables USB-DFU *after* the one-time SWD bootstrap. The module exposes
  them (DWM3001C pins 18 VUSB / 19 USB_N / 20 USB_P). Currently §4.2's
  USB-C is power-only. Touches anchor-board §4.2 and the §4.7 reset/button
  scheme if double-tap-reset DFU is wanted.
