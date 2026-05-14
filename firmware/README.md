# Firmware

Embedded firmware for the Infinity Stumps UWB nodes. All nodes are built
on the **Qorvo DWM3001C** module (DW3110 UWB transceiver + Nordic
nRF52833 BLE/MCU, with an on-module 3-axis accelerometer and 32.768 kHz
crystal).

Toolchain: **Nordic nRF Connect SDK** (Zephyr-based). The DWM3001CDK dev
kit *is* the production module, so bring-up firmware transfers directly
to production hardware.

## Layout

| Directory | Role |
|---|---|
| `anchor/` | Anchor firmware. One image with a build-time role flag — a **dumb anchor** ranges and relays; a **hub anchor** additionally acts as UWB sync master, range aggregator, BLE gateway to the phone, and disconnect-cache recorder. 7 dumb + 1 hub per pitch. |
| `ball-tag/` | Ball-tag firmware. Drives the UWB ranging exchange and reads the impact accelerometer (ADXL372) for bounce/pad/bat event timing. |
| `common/` | Shared code — UWB ranging (broadcast DS-TWR @ 100 Hz), the fixed-schedule TDMA data layer on the 802.15.4z PHY, power management, BLE service definitions. |

## Status

Not started. Phase 1+2 (hardware bring-up) begins when the DWM3001CDK
boards arrive — see `docs/phase1-2-test-plan.md` and `docs/architecture.md`.

## Licence

Apache-2.0 (see `LICENSE` at the repo root).
