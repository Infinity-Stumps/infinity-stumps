# System Spec v0.2

## Mission

**DRS for the rest of us.** Hawk-Eye is £100K+ and locked to
professional cricket. We deliver Hawk-Eye-class trajectory tracking and
LBW prediction at consumer prices, via a portable kit and a phone app.

## Prior art

Gowda et al. (NSDI '17, "Bringing IoT to Sports Analytics" — iBall)
established UWB + physics-fit + LBW extrapolation as published public
knowledge. They demonstrated 8 cm median (indoor, 2 anchors) and LBW
extrapolation at 22 cm 3D / 9.9 cm X (within ICC 10 cm tolerance) but
never productised. **Our contribution is execution**: 8 anchors (no
DoP collapse), modern Qorvo FiRa 2.0 silicon (~5× better raw σ),
outdoor validation, hub-stump topology, iPhone-native compute,
consumer pricing. See `docs/prior-art.md` for the full breakdown of
what we borrow vs add.

## Goal
17–22 mm 3D positional precision in clean LOS / **35 mm median, 78 mm
p95** under realistic occlusion, of a regulation cricket ball through
delivery, flight, bounce, and post-bounce, sampled at 100 Hz
(ETSI-compliant), in a portable system deployable at any ground.
LBW prediction target: **substantially under iBall's 22 cm 3D /
9.9 cm X-axis** at the stump line.

## Platform: Qorvo DWM3001C

Single 27×19.13×3.2 mm module integrating:
- DW3110 UWB transceiver (channels 5/9, FiRa PHY/MAC, 802.15.4z BPRF)
- Nordic nRF52833 SoC (Cortex-M4F @ 64 MHz, BLE 5)
- Planar UWB antenna + Bluetooth chip antenna
- 3-axis accelerometer (IMU) on-module
- 32.768 kHz crystal + power management on-module
- VCC 2.5–3.6 V, 48-pin castellation
- FCC/SRRC/ETSI certification (planned), nRF Connect SDK
- The DWM3001CDK dev kit *is* this module — dev kit = production part

## Anchor configuration: 8 anchors

| ID | Position | Z (mm) | Mount |
|---|---|---|---|
| A1 | Bowler off stump | 680 | Top of stump |
| A2 | Bowler leg stump | 680 | Top of stump |
| A3 | Bowler PAI off | 0 | Flush in-ground |
| A4 | Bowler PAI leg | 0 | Flush in-ground |
| A5 | Batter PAI off | 0 | Flush in-ground |
| A6 | Batter PAI leg | 0 | Flush in-ground |
| A7 | Batter off stump | 680 | **Hub stump** (sync master + BLE gateway + flash buffer) |
| A8 | Batter leg stump | 680 | Top of stump |

PAI positions: ±7.62 m longitudinal, ±1.53 m lateral (per Law 7).

## Architecture

- **Positioning: broadcast DS-TWR at 100 Hz.** One ball poll, 8
  staggered anchor responses, one ball final per cycle. Ball duty
  cycle 4%, per-anchor 2% — ETSI-compliant. TDoA was considered for
  500 Hz beacons but sim 07 showed it carries a ~120 mm intrinsic
  noise floor from hyperbolic GDOP + correlated reference noise; TWR
  wins. 150 Hz TWR was considered but breaches ETSI duty cycle (see
  `airtime-budget.md`).
- Sync: wireless via inter-anchor UWB ranging at 10 Hz, with FTS-style
  disciplined-timer correction at each anchor (no cabling). The
  **hub stump** (A7) is the sync master. See sim 07.
- **Topology: hub stump + iPhone.** One stump-top anchor acts as the
  system hub: UWB sync master, range aggregator (collects ranges from
  the other 7 over UWB-data-mode packets), and BLE gateway to the
  user's phone. The other 7 anchors are "dumb peers" running the same
  hardware with a simpler firmware image. The iPhone (or iPad) runs
  multilat + Huber physics fit + optional ML layers using Swift +
  Accelerate + CoreML. **No edge PC in the BOM.**
- Pipeline: ball ↔ 7 anchors (UWB ranging) + ball ↔ hub stump (UWB
  ranging) → 7 anchors → hub (UWB-data) → hub → iPhone (BLE) →
  physics fit on phone → DRS replay overlay on phone
- Update rate: 100 Hz UWB cycles. IMU dropped from v1 BOM (sim 06
  showed complementary-filter fusion hurts more than helps).
- Live broadcast overlay (if implemented) uses sliding-window fit on
  the same data stream — deprioritised; DRS replay is the primary
  product.
- Hub buffers ranges to internal flash when the phone is absent or
  backgrounded, so the system is a self-contained recorder by
  default — the phone catches up on reconnect.

## Precision budget (validated by sims 03, 05b, 07, sim_realistic, sim_ekf)

| Stage | 3D RMS | Source |
|---|---|---|
| Raw UWB ranging (TWR) | 30 mm σ | datasheet |
| TWR multilat, clean LOS | ~125 mm | sim 03 |
| TWR physics-fit, clean LOS @ 100 Hz | ~17–22 mm | scaled from sim 03 |
| TWR fit + occlusion (no mitigations) | ~225 mm | sim 05 |
| Batch fit (deprecated), realistic occlusion @ 100 Hz | 41 mean / 35 med / 78 p95 mm | sim_realistic n=30 |
| **EKF forward (live overlay)** @ 100 Hz | **47 mean / 47 med / 82 p95 mm** | sim_ekf n=30 |
| **EKF + RTS smoother (DRS replay)** @ 100 Hz | **47 mean / 48 med / 61 p95 mm** | sim_ekf n=30 |
| **EKF + RTS lateral (y-axis)** @ 100 Hz | **8.7 mm** mean \|err\| | sim_ekf n=30 |
| TDoA fit, perfect sync (rejected) | ~120 mm | sim 07 |

**Operational target: EKF + RTS smoother at 47 mm mean / 61 mm p95 /
8.7 mm y-axis** under realistic occlusion at 100 Hz. Forward-only EKF
runs in real time for live broadcast overlay; the RTS pass refines for
DRS replay. **The smoother beats the older batch fit on p95 (61 vs
78 mm) and lateral, at the cost of +6 mm on the mean.**

Headline 10–20 mm is the clean-LOS marketing number; the operational
number is what ships. Both are competitive with Hawk-Eye in match
conditions (independent audits put Hawk-Eye at 30–50 mm field accuracy,
despite a marketed 3.6 mm spec).

**The trajectory engine is the system's core technical IP.**

## BOM (rough, low volume)

| Item | Cost | Notes |
|---|---|---|
| Stump anchor (×4) | ~$120 ea | DWM3001C + 1× 18650 + flash + USB-C + enclosure. Identical hardware A1/A2/A7/A8; A7 runs hub firmware |
| PAI anchor (×4) | ~$135 ea | Same board, magnetic charging connector + sealed cylinder |
| Ball tag (×N) | ~$190 ea | DWM3001C + ADXL372 (±200g, bounce/pad/bat timing) + piezo high-g impact sensor (±10-50 kg, impulse for v_in recovery → physics-determines Z trajectory) |
| **Per-pitch** | **~$1,500** | Plus N balls. **No edge PC** — user supplies phone. |

## Open Phase 0 items
1. Sliding-window real-time filter (sim 04)
2. Multipath + occlusion model (sim 05)
3. IMU fusion (sim 06)
4. Sync engine modelling (sim 07)
5. Self-localisation (sim 08)
6. Patent landscape search
7. Qorvo applications engineering engagement
