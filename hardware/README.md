# Hardware

PCB and mechanical design for the Infinity Stumps anchors and ball tag.
Electronics built around the **Qorvo DWM3001C** module — see
`docs/bom.md` for the full bill of materials and `docs/architecture.md`
for the system design.

## Layout

| Directory | Contents |
|---|---|
| `anchor-board/` | The stump-anchor PCB. One design serves both the **dumb** and **hub** roles — the hub variant just populates the SPI flash + load switch for the disconnect cache. KiCad project. |
| `pai-board/` | The PAI (ground-level) anchor — same electronics as the stump anchor, in an IP67 sealed cylinder with a magnetic charging connector instead of USB-C. |
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
