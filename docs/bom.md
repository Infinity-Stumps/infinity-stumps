# Infinity Stumps — Bill of Materials (active)

> Living document. Update freely as components / suppliers / volumes change.

**Last reviewed:** 2026-05-13
**Volume assumption:** 100 pitches (prototype / low-volume pricing)
**Currency:** GBP

---

## Per-pitch BOM summary

| Item | Qty | Unit £ | Subtotal £ | Notes |
|---|---:|---:|---:|---|
| Stump anchor | 4 | 31.20 | 125 | A1, A2, A7, A8 — **identical hardware**; A7 runs hub firmware |
| PAI ground anchor | 4 | 39.00 | 156 | A3-A6 — same board, magnetic connector + sealed IP67 housing |
| Ball tag | (per ball) | 53 | — | Add N × £53 for N balls |
| **Per-pitch electronics** | | | **£281** | Before balls and enclosures |
| Enclosures + assembly | × 8 | ~£40 | 320 | Stump caps + PAI housings + labour |
| **Per-pitch total (8 anchors + housings)** | | | **~£601** | Plus N balls @ £53 each (+ shell) |

For a club pitch with 6 game balls: **~£920**. For a single-ball training setup: **~£655**.

> **One board, all eight anchors.** The stump anchor and the PAI anchor
> are the *same PCB* — the PAI variant just swaps the USB-C receptacle
> for a magnetic charging connector and uses a sealed housing. The hub
> (A7) is firmware-only: every board is built identically (flash
> populated) and any one is hub-promotable by reflashing. See
> `hardware/anchor-board/README.md` for the board design.

---

## Stump anchor BOM (A1, A2, A7, A8 — 4× per pitch, identical hardware)

This is the single board design used at every anchor position. Full
schematic-level part list (≈40 passives, pin allocation, layout rules)
is in `hardware/anchor-board/README.md`.

| Component | Part number | £ each | Notes / supplier |
|---|---|---:|---|
| UWB+BLE+MCU module | Qorvo DWM3001C | 18.00 | DW3110 UWB + nRF52833 BLE/MCU. **Integrates a 3-axis accelerometer and the 32.768 kHz LFXO crystal** — no separate parts needed. Available from stock. Same module as the DWM3001CDK dev kit. Digi-Key / Mouser. |
| 18650 Li-ion cell | Panasonic NCR18650B 3400 mAh | 4.00 | Or equivalent. Genuine cells only. |
| 18650 holder | Keystone 1042 | 0.50 | Single-cell, with leads |
| Battery protection IC | DW01A + 8205A pair | 0.30 | Over-charge / over-discharge / over-current |
| Charge controller | TI BQ24074 | 1.50 | USB-C input, Li-ion CC/CV. 1.5 A max charge. |
| 3.0 V LDO | TI TLV75530PDQNR | 0.40 | Low-IQ, 500 mA. Powers DWM3001C from battery. |
| USB-C receptacle | GCT USB4105-GF-A | 0.40 | Standard CC1/CC2, no DP/Alt-Mode |
| USB-C TVS / ESD array | TI TPD4S014 (or equivalent) | 0.30 | USB lines ESD + overvoltage. Critical for outdoor / human-handled product. |
| 16 MB SPI flash | Winbond W25Q128JVSIQ | 1.00 | Disconnect cache (not archive). See architecture.md §5.4. **Populated on every board** — used only by hub (A7) firmware, but fitting it everywhere makes any anchor hub-promotable and keeps a single assembly BOM. |
| Flash power load switch | TI TPS22916C | 0.20 | Gates flash VCC in deep sleep. One GPIO controls it. Saves ~1 µA in deep-power-down mode. |
| Tactile power button | Alps SKHHALA010 | 0.10 | Side-mounted, IP67-rated |
| RGB status LED | Würth 150141RV73100 | 0.10 | 0805 SMD, common-anode |
| SWD tag-connect footprint | Tag-Connect TC2030-NL | 0.10 | No connector on board, just pads |
| Passives (~40 parts) | caps / resistors / 1 ferrite | 0.80 | Full itemised list in `hardware/anchor-board/README.md` §4 — module decoupling, charger network, protection, ESD, VBAT sense divider, LED limits, etc. |
| PCB (4-layer, ~25×145 mm) | PCBWay / JLCPCB | 3.50 | Tall-and-thin to slide vertically inside the stump. At 100-piece volume. |
| **Subtotal silicon + PCB** | | **31.20** | Excludes enclosure + assembly. DWM3001C integrating the accel + crystal drops ~£1.25 of discretes and ~£8 of module cost vs QPK3000. |

The **hub role (A7) is firmware-only** — no hardware delta. Every board
is built identically with the flash + load switch populated, so any
anchor can take the hub role (or be swapped in as a hub replacement) by
reflashing. There is no separate hub SKU.

---

## PAI ground anchor BOM (A3-A6 — 4× per pitch)

The **same board** as the stump anchor, with the USB-C receptacle
swapped for a magnetic charging connector (to maintain IP67) and a
sealed housing instead of a stump cap:

| Component | Part number | £ each | Notes |
|---|---|---:|---|
| Stump anchor board, less USB-C receptacle | per above | 30.80 | £31.20 base − £0.40 USB-C receptacle |
| Magnetic charging connector | Rosenberger MagSafe-style 2-pin | 3.00 | Replaces USB-C to maintain IP67 |
| IP67 sealed cylinder enclosure | Custom CNC ali, ~50 mm diameter | 5.00 | Or potted ABS at higher volume |
| Anti-corrosion gasket | Generic EPDM O-ring | 0.20 | Threaded enclosure seal |
| **PAI anchor subtotal** | | **39.00** | Includes the IP67 housing |

Sits flush with the ground, threaded into a buried mounting cup. Magnetic
charging via a separate dock for off-season. The PCB is a one-component
fork of the stump anchor (connector footprint only) — same board family,
same Gerbers minus the USB-C cluster.

---

## Ball tag BOM (per ball)

| Component | Part number | £ each | Notes |
|---|---|---:|---|
| UWB+BLE+MCU module | Qorvo DWM3001C | 18.00 | Same as anchors. Integrated accel is low-g (±16g) — fine for ball motion/release detection but NOT impact magnitude, hence the separate ADXL372 below. |
| Impact accelerometer | Analog Devices ADXL372 | 4.00 | ±200g, for impact event timing (the DWM3001C's integrated accel saturates too low for cricket impacts) |
| LiPo cell | 200 mAh prismatic, 25×15×4 mm | 3.50 | Custom-spec, impact-survival rated |
| LiPo protection IC | DW01A + 8205A | 0.30 | Same as anchors |
| Charge IC | TI BQ24074 lite | 1.20 | Smaller version, lower max charge |
| LDO 3.0V | TLV75530 | 0.40 | (32 kHz crystal is on the DWM3001C module) |
| Custom flex-PCB | Custom 4-layer flex, ~30×40 mm | 5.00 | To fit curved ball interior |
| Magnetic charging contacts | Custom 2-pin springloaded | 2.00 | Embedded in ball seam line |
| Misc passives | | 1.00 | |
| Cricket ball outer shell | Phase 4a 3D-print or moulded | 15.00 | + impact-survival validation |
| Adhesive + assembly | | 2.40 | |
| **Subtotal per ball** | | **53.20** | Includes shell + assembly |

---

## Enclosure / mechanical (per stump anchor)

| Item | £ | Notes |
|---|---:|---|
| Stump-top cap (ABS injection moulded, custom) | 8.00 | At 1,000-piece volume; £20 at 100 |
| PCB mounting brackets / standoffs | 1.50 | M2 brass standoffs |
| Cell mounting clip | 0.50 | Holds 18650 securely |
| Gasket (IP54) | 0.30 | EPDM |
| Assembly + functional test labour | 8.00 | UK rates, ~10 min per unit |
| **Subtotal per stump anchor** | **18.30** | Excludes electronics |

PAI ground anchor enclosure is included in its line above (£8.20 for housing parts above).

---

## Tooling / setup (one-time)

| Item | £ | Notes |
|---|---:|---|
| Injection mould tooling (stump cap) | 5,000 | Amortise across volume |
| PCB stencil + paste mask | 200 | One-time |
| Test jigs / fixtures | 1,000 | Functional test stand |
| Certification (FCC / CE / UKCA) | 8,000 | Per product variant |
| **Total tooling** | **~£14,200** | Amortise: £142/pitch at 100 pitches |

---

## Optional / future additions

### v2: Spin tracking (per ball)

| Component | Part number | £ each |
|---|---|---:|
| 3-axis magnetometer | Bosch BMM350 | 4.50 |
| Additional ball-side flash | Adds spin data | 1.00 |
| **v2 ball delta** | | **+5.50** |

### v2: PDoA / AoA capability (per anchor)

| Component | Part number | £ each |
|---|---|---:|
| Second UWB antenna | Yageo CHIP UWB ant | 1.50 |
| Antenna bar (custom CNC ali, ~180 mm) | | 4.00 |
| Additional RF switching | | 1.00 |
| **v2 anchor delta** | | **+6.50** |

### v3+: Full-match offline buffer

Replace W25Q128 with W25Q01JV (128 MB / 1 Gb): **+£8**. Since the flash
is populated on every board, this would apply per-board unless the
larger part is fitted only on the board assigned the hub role.

---

## Suppliers

| Component family | Primary supplier | Backup | Lead time |
|---|---|---|---|
| Qorvo DWM3001C | Digi-Key | Mouser, Farnell | In stock (same module as DWM3001CDK dev kit) |
| Passives (caps, resistors) | LCSC | Mouser | 1-2 weeks |
| 18650 cells | Battery Supplies UK | Vapcell | 1-2 weeks |
| PCB fab | PCBWay (proto), JLCPCB (volume) | OSH Park | 1-3 weeks |
| Enclosures (low vol) | Sculpteo, Protolabs | local 3D print | 3-5 days |
| Enclosures (high vol) | Chinese injection moulders | UK options | 8-12 weeks tooling |
| Magnetic chargers | Rosenberger UK | RS Components | 2-4 weeks |

---

## Cost trajectory (target)

| Volume | Per-pitch electronics | Notes |
|---|---:|---|
| Prototype (1-10) | ~£500 | Dev kits + breadboarded parts |
| Low volume (100) | **~£300** | Current state — this BOM |
| Mid volume (1,000) | ~£180 | Custom modules, bulk parts |
| High volume (10,000+) | ~£100 | Direct chip purchase, large reels |

The DWM3001C module is the dominant cost driver (~65%). At high volume, custom integration of the DW3110 + nRF52833 bare die (no module overhead) could roughly halve unit cost.

---

## Change log

| Date | Change | Rationale |
|---|---|---|
| 2026-05-14 | Merged dumb + hub anchor into one "Stump anchor" line; flash + load switch now populated on every board | Single assembly BOM, any anchor hub-promotable by reflashing. Hub is firmware-only. +£1.20/board on the 7 non-hub boards is noise. See `hardware/anchor-board/README.md`. |
| 2026-05-14 | PCB 30×40 mm → ~25×145 mm, £2.00 → £3.50 | Tall-and-thin form factor to slide vertically inside the stump tube. From the anchor-board design. |
| 2026-05-14 | "Bulk caps ×4" + "Misc passives" → single "Passives (~40 parts)" line, £0.70 → £0.80 | Expanded to the itemised schematic-level list (incl. VBAT sense divider, USB shield RC) in the anchor-board doc. |
| 2026-05-14 | PAI anchor is now explicitly the same board as the stump anchor (connector swap), not "same electronics" | One unified board design across all 8 anchors. |
| 2026-05-13 | Initial BOM | First active version, captures architecture decisions through May 13, 2026 |
| 2026-05-13 | 32 kHz crystal added to all anchors | RTC accuracy for BLE timing + log timestamps |
| 2026-05-13 | Flash: W25Q256 → W25Q128 | Disconnect-cache model (phone is source of truth), 16 MB plenty |
| 2026-05-13 | Battery: 2× 18650 → 1× 18650 | Power budget showed 290 days runtime on 1×, full cricket season |
| 2026-05-13 | QPK3000 → QPK3000ATR13 | omlox variant for peer-to-hub data path |
| 2026-05-13 | Added LIS2DH12 accelerometer to all anchors | Stump-side ball-strike detection, motion-wake for deep sleep, knockover detection. The QPK3000 doesn't integrate one (unlike DWM3001C). |
| 2026-05-13 | Added TPS22916 flash load switch on hub | Gates W25Q128 power in deep sleep, saves ~1 µA. Worth £0.20 in a battery-life product. |
| 2026-05-13 | USB ESD: clarified TPD4S014 as TVS+ESD array | Critical for outdoor / human-handled product. |
| 2026-05-14 | QPK3000ATR13 → DWM3001C | Available now, dev kit = production module, integrates a 3-axis accel + the 32 kHz LFXO crystal, nRF52833 / nRF Connect SDK. ~£8/anchor cheaper. Removed standalone LIS2DH12 + 32 kHz crystal + load caps lines. omlox no longer pre-loaded — peer-to-hub data path is now a thin fixed-schedule TDMA layer on the 802.15.4z PHY. |

---

## Reference links

- [Qorvo DWM3001C product page](https://www.qorvo.com) (datasheet, ordering codes — same module as the DWM3001CDK dev kit)
- [Digi-Key Qorvo UWB modules](https://www.digikey.com/en/products/filter/rf-transceiver-modules)
- [Winbond W25Q128JV datasheet](https://www.winbond.com)
- [Abracon 32 kHz crystals](https://abracon.com)
- [Architecture document](architecture.md) — full system spec
- [Phase 1+2 test plan](phase1-2-test-plan.md) — hardware bring-up
