# Anchor Board

The stump-anchor PCB for Infinity Stumps. **One board design serves all
eight anchor positions** — the four stump-top anchors (A1, A2, A7, A8)
and, with only an enclosure + charge-connector change, the four in-ground
PAI anchors (A3–A6). The hub role (A7) is **firmware-only**: the same
fully-populated board, reflashed.

This document is the design specification — form factor, functional
blocks, the complete passive component list, pin allocation, layout
rules, and the dev-board → production-board conversion plan. It should be
read alongside `docs/bom.md` (costed BOM) and `docs/architecture.md`
(system design). KiCad project lives in this directory once started.

**Status:** specification. No schematic/layout yet.

---

## 1. Design philosophy: one board, dev first, production by subtraction

The board is designed as a **development board that converts into the
production board by subtraction only** — no re-layout, no re-spin.

This is cheap to do here because the **DWM3001C is a pre-certified
module**, not a bare chip: the nRF52833 MCU, the DW3110 UWB radio, the
UWB + BLE antennas, the 32.768 kHz LFXO crystal and a low-g accelerometer
are all *inside* the module. The board we are designing is therefore a
**carrier** — power, charging, storage, status I/O, and breakouts. There
is almost no RF layout risk (just a keepout under the module antenna), so
"dev = production + extra parts" is genuinely achievable.

**Mechanism:**

- **Single 4-layer PCB, single set of Gerbers, two assembly BOMs.**
- The production circuit lives in the board core.
- All dev-only conveniences (full SWD header, UART header, GPIO breakout,
  current-measurement shunt, LED-disable jumper) sit on a **V-scored
  break-off rail** along one long edge.
- For production: snap off the rail and mark the dev-only parts DNP. Same
  fab output, different pick-and-place file.

See §8 for the full conversion checklist.

### Hub vs dumb: populate flash on every board

**This design populates the 16 MB flash + load switch on every board.**
The cost is ~£1.20/board (~£8/pitch — noise against the ~£601 pitch
cost), and in return there is a **single assembly BOM** and **any board
is promotable to hub by reflashing**. No second variant to stock, build,
or track. The hub/dumb distinction is entirely firmware. `docs/bom.md`
is written to match — there is no separate hub SKU.

---

## 2. Form factor — tall and thin, fits inside the stump

The board drops vertically down inside a hollow cricket stump (≈38 mm
outer diameter, ≈30–34 mm internal bore). It occupies only the **upper
~145 mm** of the stump.

**Nominal envelope: 25 mm wide × ≈145 mm long, 4-layer, 1.6 mm.**

Width is set by the DWM3001C (19.13 mm wide) plus a ~3 mm routing rail
each side. Length is a vertical stack of functional zones:

```
   ┌─────────────┐  ← TOP of stump (z = 680 mm anchor reference point)
   │  ANTENNA    │  ~6 mm   Module sits fully on-board; this zone is an
   │  (keepout)  │          all-layer copper keepout under the DWM3001C
   │             │          antenna, per the Qorvo integration guide.
   ├─────────────┤
   │  DWM3001C   │  ~21 mm  Module body. Castellation pads both long
   │   MODULE    │          edges. Decoupling on the back side.
   ├─────────────┤
   │  POWER &    │  ~30 mm  LDO, charger, battery protection, SPI flash,
   │  SUPPORT    │          load switch, ESD array, RGB LED, button.
   ├─────────────┤
   │             │
   │   18650     │  ~77 mm  Keystone 1042 single-cell holder, PC-pin
   │   HOLDER    │          mount. Battery sits on top of the PCB; this
   │             │          zone carries no other components.
   │             │
   ├─────────────┤
   │  USB-C +    │  ~12 mm  USB-C receptacle on the long edge, port
   │  CHG INPUT  │          facing OUT the side of the stump.
   └─────────────┘  ← ≈145 mm below stump top — still ≈350 mm+ above
                      ground, so the side charge slot stays clear of
                      the buried portion of the stump.
═══ V-score ═══════  Break-off dev rail runs the full length on one
   [ dev rail   ]    long edge (see §7).
```

**Cross-section inside the stump:** PCB (25 mm × 1.6 mm) with the 18650
(≈18 mm dia) lying on top → ≈25 mm wide × ≈20 mm tall. Comfortably
inside a ≈30–34 mm bore. The 18650 holder must be retained against the
PCB with the BOM's cell clip — the board will see knocks and the ball's
impact shock through the stump.

**Orientation is fixed:** antenna end UP (it is the anchor's z = 680 mm
reference point), USB-C end DOWN. The PAI variant has no "up" constraint
and swaps the USB-C zone for a 2-pin magnetic charge connector.

---

## 3. Functional block diagram

```
                 USB-C VBUS ─► [TPD4S014] ─► [BQ24074] ─► VSYS ──┬──► [TLV75530] ──► 3V0 rail
                 (5 V in)       ESD/TVS       Li-ion charger      │     LDO            │
                                                  │              │                   ├─► DWM3001C  (2.5–3.6 V)
                 USB-C CC1/CC2 ─► 5k1 Rd ─► GND   │              │                   ├─► W25Q128 flash
                                                  ▼              │                   │   (via TPS22916 switch)
                                       [18650 cell] ◄─► [DW01A    │                   ├─► RGB LED
                                        3400 mAh        + 8205A]  │                   └─► (button pull-up)
                                                        protection│
                                                                  │
                          VBAT sense divider ──────────────────────┘──► nRF52833 ADC

   DWM3001C (module): nRF52833 MCU + DW3110 UWB + on-module antennas,
                      32.768 kHz LFXO, low-g accel — all internal.
        GPIO ─► SPI to W25Q128   │   GPIO ─► TPS22916 ON   │   GPIO ─► RGB LED ×3
        GPIO ◄─ power button     │   ADC  ◄─ VBAT sense    │   GPIO ◄─ BQ24074 /CHG, /PGOOD
        SWD / UART / spare GPIO ─► break-off dev rail
```

---

## 4. Functional blocks and their passives

This is the **complete passive list**, grouped by block. Values are the
design intent; finalise against each IC's datasheet app circuit during
schematic capture. Reference designators are indicative.

### 4.1 DWM3001C module

The module needs almost nothing external — its job is done internally.

| Ref | Part | Value | Purpose |
|---|---|---|---|
| C1, C2 | Capacitor 0402 | 100 nF | VDD pin decoupling, one per supply pin group, placed hard against the castellations |
| C3 | Capacitor 0805 | 10 µF | Bulk decoupling on the module 3V0 feed |
| R1 | Resistor 0402 | 10 kΩ | nRESET pull-up |
| C4 | Capacitor 0402 | 100 nF | nRESET RC debounce (to GND) |

Antenna region: **copper keepout on all layers** under and around the
module's antenna end, per the Qorvo DWM3001C integration guidelines. No
ground pour, no traces, no vias. The module sits **fully on the board**
(no overhang) — the keepout gives the RF clearance, and keeping the
module fully supported is the mechanically robust choice inside the cap,
where the board takes ball-impact shock through the stump.

### 4.2 USB-C input + ESD (production: stump anchors only)

Sink-only, no USB-PD, no data — power in at 5 V.

| Ref | Part | Value | Purpose |
|---|---|---|---|
| J1 | GCT USB4105-GF-A | — | USB-C receptacle, long-edge mount, port facing out |
| R2, R3 | Resistor 0402 | 5.1 kΩ | CC1 / CC2 pull-downs (Rd) — required for a source to detect the sink |
| C5 | Capacitor 0805 | 10 µF | VBUS bulk cap |
| C6 | Capacitor 0402 | 100 nF | VBUS HF decoupling |
| U2 | TI TPD4S014 | — | TVS/ESD array on VBUS + CC lines |
| R4 | Resistor 0402 | 1 MΩ | Shield-to-GND bleed (parallel with C7) |
| C7 | Capacitor 0402 | 4.7 nF | Shield-to-GND, chassis noise return |

> **PAI variant:** J1, R2, R3 are replaced by a 2-pin magnetic charge
> connector (Rosenberger). VBUS path otherwise identical. This is the
> *only* electrical difference between the stump and PAI boards.

### 4.3 Li-ion charger — TI BQ24074

| Ref | Part | Value | Purpose |
|---|---|---|---|
| U3 | TI BQ24074 | — | USB-input Li-ion CC/CV charger |
| C8 | Capacitor 0603 | 1 µF | IN pin input cap |
| C9 | Capacitor 0603 | 1 µF | OUT pin cap |
| C10 | Capacitor 0603 | 1 µF | BAT pin cap |
| R5 | Resistor 0402 | 909 Ω | ISET — fast-charge current ≈ 1.0 A (≈0.3C on a 3400 mAh cell; conservative for outdoor temps) |
| R6 | Resistor 0402 | TBD | TMR — safety-timer program resistor, sized for a ~10 h timer (generous margin over a ~0.3C charge); value from the BQ24074 datasheet timer equation at schematic capture |
| R7, R8 | Resistor 0402 | 10 kΩ + 10 kΩ | TS pin — equal divider holds TS at mid-rail, disabling temperature sensing in v1 (no pack thermistor). v2 may swap R8 for an NTC. |
| R9, R10 | Resistor 0402 | 10 kΩ | /CHG and /PGOOD open-drain pull-ups to 3V0, also sensed by MCU GPIO |
| R11, R12 | Resistor 0402 | strap | EN1 / EN2 mode straps — set input current limit (USB500 / ISET) |

### 4.4 Battery + protection — 18650 + DW01A/8205A

| Ref | Part | Value | Purpose |
|---|---|---|---|
| BT1 | Panasonic NCR18650B | 3400 mAh | Single Li-ion cell, in Keystone 1042 holder |
| U4 | DW01A | — | Protection controller (over-charge / over-discharge / over-current) |
| U5 | 8205A | — | Dual N-FET, protection switch (no passives of its own) |
| R13 | Resistor 0402 | 330 Ω | DW01A VCC series resistor |
| C11 | Capacitor 0402 | 100 nF | DW01A VCC–VSS decoupling |
| R14 | Resistor 0402 | 2 kΩ | DW01A current-sense input resistor |

### 4.5 3.0 V regulation — TI TLV75530

| Ref | Part | Value | Purpose |
|---|---|---|---|
| U6 | TI TLV75530PDQNR | 3.0 V | Low-IQ 500 mA LDO, battery → 3V0 system rail |
| C12 | Capacitor 0603 | 1 µF | VIN cap |
| C13 | Capacitor 0603 | 1 µF | VOUT cap |
| C14 | Capacitor 0805 | 10 µF | 3V0 rail bulk cap |
| FB1 | Ferrite bead 0603 | — | Optional: charger-OUT → LDO-IN, isolates charge ripple from the rail |

### 4.6 SPI flash + load switch — W25Q128 + TPS22916C

Populated on **every** board (see §1).

| Ref | Part | Value | Purpose |
|---|---|---|---|
| U7 | Winbond W25Q128JVSIQ | 16 MB | Disconnect-cache flash (hub firmware uses it; dumb firmware leaves it idle) |
| U8 | TI TPS22916C | — | Load switch — gates flash VCC in deep sleep (~1 µA saving) |
| C15 | Capacitor 0402 | 100 nF | W25Q128 VCC decoupling |
| C16 | Capacitor 0402 | 1 µF | TPS22916 output cap |
| C17 | Capacitor 0402 | 1 nF | TPS22916 CT — turn-on slew-rate control |
| R15 | Resistor 0402 | 10 kΩ | /CS pull-up (idle-high during MCU boot) |
| R16, R17 | Resistor 0402 | 10 kΩ | /WP and /HOLD pull-ups (single-SPI mode, tied inactive) |

### 4.7 User I/O — RGB LED + power button

| Ref | Part | Value | Purpose |
|---|---|---|---|
| D1 | Würth 150141RV73100 | — | Common-anode RGB status LED, 0805 |
| R18 | Resistor 0402 | 1 kΩ | Red current limit (run dim — LED is a battery drain) |
| R19 | Resistor 0402 | 680 Ω | Green current limit |
| R20 | Resistor 0402 | 680 Ω | Blue current limit |
| SW1 | Alps SKHHALA010 | — | Side-mounted IP67 tactile power/mode button |
| R21 | Resistor 0402 | 10 kΩ | Button pull-up (or use nRF internal pull and DNP) |
| C18 | Capacitor 0402 | 100 nF | Button debounce |

> **Power-button behaviour: soft-wake, no hard latch.** The button is an
> MCU GPIO wake/mode source; "off" is nRF52833 deep sleep (System OFF
> ≈ a few µA; the power budget's conservative ~50 µA sleep figure
> already covers this). No load-switch latch on the 3V0 rail. Rationale:
> the anchor must always be able to wake on UWB, BLE or motion — a hard
> "dead until button" state breaks the hub-as-recorder behaviour and the
> 290-day runtime is already computed against deep sleep, not a true
> zero-draw off. Fewer parts, more robust.

### 4.8 Battery voltage sense

Needed for the `battery_pct` field in the hub's BLE Status characteristic.

| Ref | Part | Value | Purpose |
|---|---|---|---|
| R22, R23 | Resistor 0402 | 1 MΩ + 1 MΩ | High-impedance divider, VBAT → nRF ADC pin (≈2 µA drain — acceptable vs 50 µA sleep) |
| C19 | Capacitor 0402 | 100 nF | ADC anti-alias / sample-and-hold filter |

### 4.9 Rail-level / misc

| Ref | Part | Value | Purpose |
|---|---|---|---|
| TP1–TP6 | Test points | — | VBUS, VSYS, VBAT, 3V0, GND ×2 — keep on the production board, they cost nothing |
| C20 | Capacitor 0805 | 10 µF | Extra 3V0 bulk near the module if layout needs it |

**Passive count, production board:** ≈40 parts — caps, resistors, one
ferrite. All 0402/0603/0805, single reel-friendly family. This maps to
the BOM's "Bulk decoupling caps ×4 / Misc passives" lines, which should
be expanded to match this list (see §10).

---

## 5. Pin allocation (proposed)

nRF52833 GPIO exposed on the DWM3001C castellations. **Finalise against
the DWM3001C datasheet castellation map** — the function-to-pin mapping
below is the design intent, not the pin numbers.

| Function | Dir | Notes |
|---|---|---|
| SWDIO / SWDCLK | — | Tag-Connect TC2030 pads (production) **and** dev-rail 2×5 header |
| UART TX / RX | — | nRF log console → dev-rail header only |
| SPI SCK / MOSI / MISO / CS | out/io | W25Q128 flash |
| FLASH_EN | out | TPS22916 ON pin |
| LED_R / LED_G / LED_B | out | RGB LED, common-anode (drive low = on) |
| BTN | in | Power/mode button, wake source |
| CHG_STAT | in | BQ24074 /CHG (open-drain) |
| PGOOD | in | BQ24074 /PGOOD (open-drain) |
| EN1 / EN2 | out | BQ24074 mode control — *or* hard-strap with R11/R12 and free the GPIO |
| VBAT_SENSE | ain | ADC, via R22/R23 divider |
| Spare GPIO ×4–6 | — | Broken out to the dev rail for bring-up |

The DW3110 UWB radio talks to the nRF52833 over an **on-module** SPI bus
— not exposed, not our concern.

---

## 6. Layer stack-up and layout rules

**4-layer, 1.6 mm:** `Signal / GND / PWR / Signal`.

1. **Antenna keepout** — the single hard RF rule. All-layer copper
   keepout under/around the DWM3001C antenna end, per Qorvo's
   integration guide. No pour, no trace, no via, no battery, no metal
   nearby. This protects the module's pre-certification.
2. **Module placement** — DWM3001C at the top edge, antenna outboard.
   Decoupling caps (C1–C3) on the *back* side directly behind the supply
   castellations.
3. **USB-C** — keep VBUS traces short and wide; TPD4S014 placed right at
   the connector, before anything else. CC pull-downs at the connector.
4. **Charge/power path** — BQ24074 → DW01A/8205A → TLV75530 in a compact
   cluster in the Power & Support zone. Keep the high-current battery
   loop (cell → 8205A → charger/load) tight; star-ground the analog
   return of the VBAT divider away from it.
5. **18650 zone** — no components, but route the cell + / − traces
   wide (charge current up to 1 A). The holder's PC pins anchor it
   mechanically; pair with the BOM cell clip.
6. **Thermal** — negligible. Worst case ≈8 mA average, ≈1 A only while
   charging; modest copper pour on the PWR layer around the charger is
   plenty. No concern in a sealed stump.
7. **Mechanical** — M2 mounting holes (BOM standoffs) at the corners of
   the rigid core; keep them out of the antenna keepout. The board takes
   ball-impact shock transmitted through the stump — no tall unsupported
   parts, secure the cell.

---

## 7. The break-off dev rail

A V-scored strip down one long edge, snapped off for production. Carries
**only** bring-up and validation aids:

| Dev-rail item | Why it is dev-only |
|---|---|
| 2×5 1.27 mm SWD/JTAG header | Production uses the Tag-Connect pads on the core board; the shrouded header is faster for daily flashing/debug |
| UART header (TX/RX/GND) | nRF RTT/console logging during bring-up |
| GPIO breakout (spare ×4–6 + I²C/SPI taps) | Probing, logic analyser, attaching test sensors |
| **3V0 current-shunt jumper** | A 2-pin header in series with the 3V0 rail. Pull the jumper, insert a µA meter — **this is how the 290-day / ~50 µA sleep budget gets validated.** Production: replace with a 0 Ω. |
| LED-disable jumper | LEDs wreck a sleep-current measurement; cut them cleanly during power profiling |
| Boot/mode strap pads | Recovery / forced-DFU during firmware bring-up |

The core board is **fully functional with the rail removed** — the
Tag-Connect pads, the 0 Ω in place of the shunt jumper, and the on-board
RGB LED cover everything production needs.

---

## 8. Dev → production conversion checklist

No re-layout. No re-spin. Same Gerbers. To go from dev to production:

1. **Snap off** the V-scored dev rail.
2. **Fit R_shunt = 0 Ω** in the current-shunt jumper position.
3. **Mark DNP:** dev-rail parts (already gone with the rail), the SWD
   shrouded header, UART header, GPIO breakout, mode-strap pads.
4. **Stuff the Tag-Connect TC2030 pads** (they are on the core board, not
   the rail).
5. Swap the **assembly/pick-and-place BOM** to the production variant.
   Fab output (Gerbers, drill, netlist) is **identical**.
6. PAI-board fork only: swap the USB-C cluster (J1/R2/R3) for the
   magnetic connector footprint — a one-component schematic change, same
   board family.

---

## 9. Decisions made and remaining open items

**Resolved in this design:**

- **Form factor** — ≈25×145 mm, tall-and-thin (§2). `docs/bom.md` updated
  to match (PCB line, cost).
- **Flash on every board** — single assembly BOM, any board
  hub-promotable (§1). `docs/bom.md` and `docs/architecture.md` updated.
- **Power button** — soft-wake, no hard latch (§4.7).
- **Antenna** — module fully on-board with an all-layer keepout, no
  overhang (§4.1).
- **BQ24074 TS** — temperature sensing disabled with a fixed 10k/10k
  divider in v1, no pack thermistor (§4.3).

**Still open (need the mechanical/enclosure design or a datasheet pass):**

- **18650 holder exact footprint.** The ~77 mm zone is sized for the
  Keystone 1042; confirm the real footprint (PC-pin pitch, retention)
  before fixing the final board length.
- **USB-C side-slot sealing.** Design assumes a side slot in the stump
  wall ≈145 mm below the top, IP54-gasketed. Mechanical design to
  confirm the slot seals acceptably vs. the alternative of routing the
  port through the stump-top cap (rejected here — it crowds the antenna
  and the cap is the removable part).
- **BQ24074 TMR resistor value** — set from the datasheet timer equation
  at schematic capture (target ~10 h safety timer).

## 10. BOM reconciliation — done

`docs/bom.md` and `docs/architecture.md` have been updated to match this
design (2026-05-14):

- **PCB size** 30×40 mm → ≈25×145 mm, £2.00 → £3.50.
- **Flash + load switch** moved from a hub-only extra into the base
  stump-anchor BOM (populated on every board); the separate hub SKU is
  gone — hub is firmware-only.
- **Passives** — the "bulk caps ×4" + "misc passives" lines collapsed
  into one "Passives (~40 parts)" line referencing §4 here, £0.70 →
  £0.80. This now covers the VBAT sense divider (§4.8) and USB shield RC
  (§4.2).
- Per-pitch electronics £262 → £281; per-pitch total £582 → £601.
