# Cricket UWB — Bill of Materials (active)

> Living document. Update freely as components / suppliers / volumes change.

**Last reviewed:** 2026-05-13
**Volume assumption:** 100 pitches (prototype / low-volume pricing)
**Currency:** GBP

---

## Per-pitch BOM summary

| Item | Qty | Unit £ | Subtotal £ | Notes |
|---|---:|---:|---:|---|
| Hub stump anchor | 1 | 30 | 30 | A7 — sync master + BLE gateway + disconnect cache |
| Dumb stump anchor | 3 | 28 | 84 | A1, A2, A8 |
| PAI ground anchor | 4 | 37 | 148 | A3-A6 — sealed IP67 housing |
| Ball tag | (per ball) | 53 | — | Add N × £53 for N balls |
| **Per-pitch electronics** | | | **£262** | Before balls and enclosures |
| Enclosures + assembly | × 8 | ~£40 | 320 | Stump caps + PAI housings + labour |
| **Per-pitch total (8 anchors + housings)** | | | **~£582** | Plus N balls @ £53 each (+ shell) |

For a club pitch with 6 game balls: **~£900**. For a single-ball training setup: **~£635**.

---

## Dumb stump anchor BOM (A1, A2, A8 — 3× per pitch)

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
| Tactile power button | Alps SKHHALA010 | 0.10 | Side-mounted, IP67-rated |
| RGB status LED | Würth 150141RV73100 | 0.10 | 0805 SMD, common-anode |
| SWD tag-connect footprint | Tag-Connect TC2030-NL | 0.10 | No connector on board, just pads |
| Bulk decoupling caps (×4) | 10 µF / 0.1 µF | 0.20 | Standard practice |
| Misc passives | resistors, inductors | 0.50 | Per schematic |
| PCB (4-layer, 30×40 mm) | PCBWay / JLCPCB | 2.00 | At 100-piece volume |
| **Subtotal silicon + PCB** | | **28.40** | Excludes enclosure + assembly. DWM3001C integrating the accel + crystal drops ~£1.25 of discretes and ~£8 of module cost vs QPK3000. |

---

## Hub stump anchor BOM (A7 — 1× per pitch)

All of the dumb anchor BOM, plus:

| Extra component | Part number | £ each | Notes |
|---|---|---:|---|
| 16 MB SPI flash | Winbond W25Q128JVSIQ | 1.00 | Disconnect cache (not archive). See architecture.md §5.4. |
| Flash power load switch | TI TPS22916C | 0.20 | Gates flash VCC in deep sleep. One GPIO controls it. Saves ~1 µA in deep-power-down mode. Worth the £0.20 for a battery-life product. |
| **Hub anchor subtotal** | | **29.60** | |

Designated hub-stump role is **firmware-only** — same PCB with the flash chip populated. In small volumes you can leave the flash footprint unpopulated on dumb anchors.

---

## PAI ground anchor BOM (A3-A6 — 4× per pitch)

Same electronics as dumb stump anchor (£28.40) plus:

| Extra component | Part number | £ each | Notes |
|---|---|---:|---|
| IP67 sealed cylinder enclosure | Custom CNC ali, ~50 mm diameter | 5.00 | Or potted ABS at higher volume |
| Magnetic charging connector | Rosenberger MagSafe-style 2-pin | 3.00 | Replaces USB-C to maintain IP67 |
| Anti-corrosion gasket | Generic EPDM O-ring | 0.20 | Threaded enclosure seal |
| **PAI anchor subtotal** | | **36.60** | Includes the IP67 housing |

Sits flush with the ground, threaded into a buried mounting cup. Magnetic charging via a separate dock for off-season.

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

Replace W25Q128 with W25Q01JV (128 MB / 1 Gb): **+£8** on hub stump only.

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
