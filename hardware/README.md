# Hardware

PCB and mechanical design for the Infinity Stumps anchors and ball tag.
Electronics built around the **Qorvo DWM3001C** module — see
`docs/bom.md` for the full bill of materials and `docs/architecture.md`
for the system design.

## Layout

| Directory | Contents |
|---|---|
| `anchor-board/` | The anchor PCB — **one design serves all eight anchor positions**. Every board is built identically (flash + load switch populated); the hub role (A7) is firmware-only and any board is hub-promotable by reflashing. Tall-and-thin to fit inside the stump. KiCad project. See its `README.md` for the full design spec. |
| `pai-board/` | The PAI (ground-level) anchor — **not an independent design**, just a one-component fork of `anchor-board/`: USB-C receptacle swapped for a magnetic charging connector, in an IP67 sealed cylinder. Same board family, same Gerbers minus the USB-C cluster. |
| `ball-tag/` | The in-ball tag — a custom 4-layer flex PCB shaped to the ball interior, carrying the DWM3001C + ADXL372 impact accelerometer + small LiPo. |
| `mechanical/` | Enclosure design — stump-top caps, PAI housings, ball shell. STL + STEP. |

Each board is its own KiCad project (schematic + layout + Gerbers).
Manufacturing outputs are committed alongside the source.

## Status

Not started. PCB design follows firmware bring-up on the DWM3001CDK
dev kits.

## Licence

CERN-OHL-S v2 — strongly reciprocal (see `LICENSE-hardware` at the repo
root). Mechanical design files (STL/STEP) are CC-BY-4.0 per the project
licensing in `docs/about.md`.
