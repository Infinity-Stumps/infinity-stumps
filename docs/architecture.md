# Infinity Stumps — Technical Architecture

> System architecture for the Infinity Stumps ball tracking + LBW prediction
> system. Reference document for v1.

**Version:** v1 (May 2026)
**Status:** Simulation-validated. Hardware bring-up in progress.
**Last updated:** 2026-05-13

---

## 1. System Overview

### 1.1 Goal

Track a regulation cricket ball in 3D through delivery, flight, bounce,
and post-bounce with Hawk-Eye-class precision, and provide a DRS-style
LBW prediction with an uncertainty ellipse. All processing runs on a
consumer smartphone connected to a small fixed-position UWB sensor
network at the pitch.

### 1.2 Scope

**In scope (v1):**
- Single-pitch installation (8 anchors + ball tag)
- Ball trajectory tracking + 3D physics fit
- LBW prediction with HIT / MISS / UMPIRE'S CALL verdict
- DRS replay overlay on iPhone / iPad
- Live broadcast overlay (best-effort)

**Out of scope (v1):**
- Spin analytics (v2 — magnetometer-based)
- No-ball detection, run-out review, multi-camera reconstruction
- Edge / sound detection
- Multi-pitch / venue-wide tracking
- Player tracking (UWB sensors on players)
- Cloud sync, multi-device session sharing

### 1.3 Key performance claims (sim, n=30)

| Metric | Value | Source |
|---|---:|---|
| Trajectory 3D RMS mean | 47 mm | sim_ekf |
| Trajectory 3D RMS p95 | 61 mm | sim_ekf |
| LBW lateral error median | 9 mm | sim_lbw |
| LBW 3D error median | 28 mm | sim_lbw |
| LBW verdict accuracy | 96.7% | sim_lbw, n=30 |
| LBW false-positive rate | 0% | sim_lbw, n=30 |
| Cost target | ~£1,500 per pitch | BOM in §3 |

### 1.4 Comparison to existing systems

| System | Precision | Cost | Form factor | Target |
|---|---|---|---|---|
| Hawk-Eye | ~30 mm (field) | £100K–£250K + £20-50K/yr | Trucks, masts, multiple HD cameras | International cricket |
| iBall (NSDI '17) | 80 mm median (indoor) | research prototype, never productised | 2 anchors + ball-embedded UWB | Research |
| **Infinity Stumps v1** | **47 mm mean** | **~£1,500** | **8 small anchors + ball + phone** | **Clubs, schools, coaches** |

---

## 2. Conceptual Architecture

### 2.1 System block diagram

```
                                  ┌─────────────────────────┐
                                  │   iPhone / iPad         │
                                  │   ───────────────────   │
                                  │   • EKF + RTS smoother  │
                                  │   • LBW verdict + UI    │
                                  │   • Swift + Accelerate  │
                                  │   • CoreML (v2+)        │
                                  └────────────▲────────────┘
                                               │ BLE
                                               │ (single peripheral link)
                                  ┌────────────┴────────────┐
                                  │   HUB STUMP (Anchor A7) │
                                  │   ───────────────────   │
                                  │   • UWB sync master     │
                                  │   • Range aggregator    │
                                  │   • Flash ring buffer   │
                                  │   • BLE gateway         │
                                  └────────────▲────────────┘
                                               │
                          ┌────────────────────┴────────────────────┐
                          │   UWB data-mode packets (6.5 GHz)       │
                          │   Sync + ranging + telemetry            │
                          ├────────┬────────┬────────┬──────┬───────┤
                          ▼        ▼        ▼        ▼      ▼       ▼
                       ┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐
                       │ A1 │  │ A2 │  │ A3 │  │ A4 │  │ A5 │  │ A6 │  ... A8
                       └────┘  └────┘  └────┘  └────┘  └────┘  └────┘
                       Dumb peer anchors (same chip, simpler firmware)
                                               │
                                               │ UWB DS-TWR @ 100 Hz
                                               ▼
                                  ┌─────────────────────────┐
                                  │   BALL TAG              │
                                  │   ───────────────────   │
                                  │   • DWM3001C (UWB+BLE)  │
                                  │   • ADXL372 (impact)    │
                                  │   • Battery + antenna   │
                                  └─────────────────────────┘
```

### 2.2 Three computational layers

The system has three concurrent compute layers, each owning a
different time-scale:

| Layer | Hardware | Rate | Owns |
|---|---|---:|---|
| **Ranging** | Anchors + ball | 100 Hz | TWR exchanges, NLOS chip-level detection |
| **Aggregation** | Hub stump | 100 Hz | Sync, range collation, BLE forwarding |
| **Inference** | iPhone | per-cycle + RTS pass | EKF state, LBW verdict, UI |

Each layer is isolated from the others' timing constraints — the
anchors don't care about the iPhone's compute load, and the iPhone
doesn't need to keep up with anchor scheduling.

---

## 3. Hardware Architecture

### 3.1 Bill of materials (per pitch)

| Item | Qty | Unit cost | Notes |
|---|---:|---:|---|
| Stump anchor | 4 | ~£31 | DWM3001C + 1× 18650 + 16 MB flash + USB-C. **Identical hardware** A1/A2/A7/A8; A7 runs hub firmware |
| PAI ground anchor | 4 | ~£39 | Same board, magnetic connector instead of USB-C + IP67 sealed cylinder |
| Ball tag | N | ~£53 | DWM3001C + ADXL372 + small LiPo + impact-survival shell |
| **Per-pitch subtotal** | | **~£281** | Plus N balls. No edge PC. See `bom.md` for the line-item breakdown. |

One board design serves all eight anchor positions — the hub (A7) is
firmware-only, and the PAI variant is a one-component connector fork.
See `hardware/anchor-board/README.md`.

Enclosure / assembly costs roughly double the silicon, so realistic
fully-assembled per-pitch cost ≈ **£700-£1,200** depending on volume.

**Battery lifecycle:** 1× 18650 at ~3500 mAh gives ~290 days of active
use per the power budget in §3.5 — a full cricket season. Recharge in
the off-season. ~10-year service life with annual deep cycles.

### 3.2 Anchor placement (Laws of Cricket compliant)

| ID | Position | Z (mm) | Mount | Role |
|---|---|---:|---|---|
| A1 | Bowler off stump | 680 | Top of stump | Dumb peer |
| A2 | Bowler leg stump | 680 | Top of stump | Dumb peer |
| A3 | Bowler off-side PAI | 0 | Flush in-ground | Dumb peer |
| A4 | Bowler leg-side PAI | 0 | Flush in-ground | Dumb peer |
| A5 | Batter off-side PAI | 0 | Flush in-ground | Dumb peer |
| A6 | Batter leg-side PAI | 0 | Flush in-ground | Dumb peer |
| **A7** | **Batter off stump** | **680** | **Top of stump** | **Hub stump** |
| A8 | Batter leg stump | 680 | Top of stump | Dumb peer |

Constants in `simulation/src/infinity_stumps/geometry.py`:
- `PITCH_HL = 10.06 m` (half pitch length, ICC standard 22 yards)
- `PAI_X = 7.62 m` (Protected Area Indicator longitudinal offset)
- `PAI_Y = 1.53 m` (PAI lateral offset)
- `STUMP_W = 0.2286 m` (9 inches, ICC standard)
- `STUMP_TOP = 0.680 m` (top of stump, just below bail)
- `STUMP_HEIGHT = 0.711 m` (full ICC stump height)

### 3.3 Anchor electronics

All 8 anchors use the same hardware platform — only firmware differs:

**Qorvo DWM3001C module** (27 × 19.13 × 3.2 mm):
- DW3110 UWB transceiver (channels 5/9, FiRa-compliant DS-TWR)
- Nordic nRF52833 SoC (Cortex-M4F @ 64 MHz, BLE 5, 802.15.4)
- Integrated 3-axis accelerometer (motion-wake, ball-strike,
  knockover detection — no separate accel IC needed)
- Integrated UWB antenna + 2.4 GHz antenna
- On-module 32.768 kHz LFXO crystal (RTC / BLE timing reference)
- Pre-certified (FCC / ISED / CE / UKCA), Nordic nRF Connect SDK
  (Zephyr-based)

**Why DWM3001C** (chosen over Qorvo QPK3000, May 2026):
- The DWM3001CDK dev kit *is* the production module — bring-up
  firmware transfers directly to production hardware.
- Available from stock (QPK3000 had 12-16 week constrained lead times).
- Integrated accelerometer + on-module 32 kHz crystal → fewer BOM
  line items.
- nRF52833 → Nordic nRF Connect SDK, the best-supported UWB+BLE
  toolchain.
- Mature, widely-deployed DW3110 + nRF52833 combination.

**Standards posture:**
- For ranging: **FiRa-compliant** secure DS-TWR.
- For data exchange (peer → hub): a **thin, fixed-schedule TDMA data
  layer** on the 802.15.4z PHY, synchronised by the hub's cycle-start
  beacon. Not a general-purpose MAC — a static per-anchor slot
  schedule, which is all the disconnect-cache data model (§5.4)
  requires. ~1-2 weeks firmware.
- Marketing wording: "FiRa-compliant ranging plus proprietary
  fixed-schedule data frames on the 802.15.4z PHY." Accurate, honest.
  Do not claim "FiRa-compliant data exchange" — not a thing in the
  standard.

**Per-anchor additions:**
- 1× 18650 Li-ion (~3500 mAh, ~290 days runtime at 12 mAh/day average)
- (The 32.768 kHz LFXO crystal is on the DWM3001C module — no
  separate part. It provides the stable BLE timing / RTC reference
  during sleep that the internal RC oscillator can't.)
- USB-C for charging + firmware updates (PAI anchors: magnetic
  connector instead, to maintain IP67)
- Custom enclosure (stump-top or sealed in-ground)
- 16 MB SPI flash (Winbond W25Q128) + load switch — **populated on
  every board** but used only by the hub firmware as a **disconnect
  cache** (not a queryable archive). Phone is the source of truth; the
  hub forwards cycles via BLE notifications and writes a backup copy to
  flash with a monotonic sequence counter. On reconnect after a BLE
  drop, the phone requests gap-fill by sequence range. 16 MB at our
  throughput is comfortably more than a whole-session-disconnect's
  worth of cache. Fitting the flash on every board (vs hub-only) costs
  ~£1.20/board, keeps a single assembly BOM, and makes any anchor
  hub-promotable by reflashing. See §5 for the protocol.

### 3.4 Ball tag electronics

| Component | Function | Notes |
|---|---|---|
| DWM3001C | UWB ranging + BLE telemetry | Same module as anchors |
| ADXL372 (±200g) | Impact event timing | Saturates on amplitude but timestamp is fine |
| LiPo battery | ~75 min runtime | Power-optimised, sleep between sessions |
| Custom shell | Cricket-ball form factor | Phase 4a — 3D printed initially |

**Not in v1 ball:**
- Precision IMU (gyro saturates at cricket spin; sim 06 failure)
- Magnetometer (v2 — spin analytics)
- Piezo high-g sensor (sim showed net-neutral for our pipeline)

---

## 4. Coordinate System

```
                                  ^ +Z (up)
                                  |
                                  |
        bowler end                |              batter end
                                  |
   A1, A2   A3, A4                |               A5, A6   A7, A8
    │         │                   |                │         │
    │         │       o←──── ball ───→ o           │         │
    │         │                   |                │         │
    └─── x = -10.06 m ────────────┼────────────── x = +10.06 m ──┘
                                  |
                                  └─→ +X (along pitch, batter end positive)
```

**Origin:** centre of pitch (centre of both popping crease lines'
midpoint), at ground level.

**Axes:**
- X — along pitch, positive toward batter end
- Y — across pitch, positive toward leg side (right-hand batter)
- Z — vertical, positive up

**Right-handed coordinate system.**

**Convention notes:**
- Bowler stumps at x = -10.06 m
- Batter stumps at x = +10.06 m
- Stump centres at y = ±0.114 m (off and leg)
- PAIs at (x = ±7.62, y = ±1.53)
- Ball spin axis components: same coord system

---

### 3.5 Power budget (per anchor)

Annualised use pattern: matches and training are **delivery-driven**,
not continuous. Realistic estimate is ~10-20 min/day active ranging.

**Active state (during a delivery):**

| State | Current @ VDD=3.0V | Duty | Avg current |
|---|---:|---:|---:|
| UWB TX (1× per cycle, 150 µs) | ~200 mA | 1.5% | 3.0 mA |
| UWB RX (2× per cycle, 150 µs) | ~130 mA | 3.0% | 3.9 mA |
| MCU active | ~8 mA | 10% | 0.8 mA |
| Sleep | ~5 µA | 85% | ~0 |
| **Avg at module (peer anchor)** | | | **~7.7 mA** |
| Hub stump adds BLE forwarding | | | **+0.5-1 mA** |

**Battery side (3.7V Li-ion via LDO to 3.0V):**
- Same current as module (LDO drops 0.7V as heat)
- Peer anchor: 7.7 mA active
- Hub stump: 8-8.7 mA active (the BLE peripheral is steady-state
  forwarding, low load — see §5.4 disconnect-cache model)
- Sleep (between deliveries): ~50 µA

**Daily energy (delivery-driven use, ~10 min active):**
- ~12 mAh/day per anchor

**Annualised runtime:**

| Battery | Capacity | Runtime |
|---|---:|---:|
| 1× 18650 (default) | 3500 mAh | **~290 days = full cricket season** |
| 2× 18650 | 6500 mAh | ~540 days |
| 1× LiPo 1000 mAh | 1000 mAh | ~83 days (~3 months) |

**Lifecycle pattern:** charge each anchor at the start of the cricket
season (Apr-May). The 1× 18650 sees the whole season without
recharge. Off-season storage at ~50% charge for ~6 months. Estimated
~10-year service life with annual deep-cycle pattern.

---

## 5. Signal Chain

### 5.1 Per-cycle timing (100 Hz, ETSI-compliant)

One UWB cycle:

```
t=0      Ball transmits POLL frame (broadcast)
t=200µs  Anchor 1 transmits RESPONSE_1
t=350µs  Anchor 2 transmits RESPONSE_2
t=500µs  ...
t=1.4ms  Anchor 8 transmits RESPONSE_8
t=1.6ms  Ball transmits FINAL frame
         Each anchor now has the timing data to compute its own range
         (DS-TWR, clock drift cancelled by 2× round-trip)
t=1.8ms  Anchors send ranges → hub stump (UWB-data-mode burst)
t=2-3ms  Hub stump packs into one BLE notification → iPhone
t=10ms   Next cycle begins
```

**Duty cycle:** ball 4% TX (within ETSI 5% limit), per-anchor 2%.
See `docs/airtime-budget.md` for the derivation.

### 5.2 Inter-anchor sync

Wireless self-sync at 10 Hz via inter-anchor TWR:
- Hub stump initiates a sync burst every 100 ms
- Each peer anchor measures its range to hub via DS-TWR
- Combined with known anchor positions, hub computes per-anchor clock
  offset + drift
- FTS (Frequency-Tracking System) disciplined timer per anchor
- Result: anchor-to-anchor sync to ~100 ps (3 cm equivalent), no
  cabling, no GPS, no PTP

See `sim 07b` for the validation.

### 5.3 Hub-to-phone link

**Transport:** Bluetooth LE 5.0, single peripheral connection.

**Payload per cycle:** ~80 bytes
- 8 anchor ranges (16 bits each, fixed-point mm) = 16 bytes
- 8 NLOS-detection flags (1 bit each) = 1 byte
- 8 per-anchor timing offsets within cycle (16 bits each) = 16 bytes
- 1 cycle timestamp (microseconds, 32 bits) = 4 bytes
- 1 ball-side accelerometer event flag = 1 byte
- Padding / framing = ~42 bytes
- Total ~80 bytes × 100 Hz = ~64 kbps (well within BLE limits)

**Reliability:** BLE re-transmits + hub stump flash buffer if phone
disconnects. Phone catches up on reconnect by streaming missed cycles.

### 5.4 Phone is source of truth; flash is a disconnect cache

The data model is:

- **Primary path:** UWB peer → hub → BLE live notification → **phone-side
  persistent store** (SQLite / Core Data). Every cycle gets a monotonic
  `seq` number assigned by the hub; phone persists `{seq, timestamp,
  payload}` as it arrives. The user-facing record lives on the phone.
- **Backup path:** hub also writes each cycle to W25Q128 flash, append-only,
  using Zephyr FCB. Sector-aligned. The flash is *not* a queryable archive
  — it has no time index, no bookmarks. It just stores a contiguous
  sequence-ordered log.
- **Reconciliation path:** phone tracks `highest_seq_received`. On BLE
  reconnect after a drop, it reads the hub's `Status` characteristic
  (`{oldest_seq_in_flash, newest_seq, free_sectors}`), and if there's a
  gap, sends a `Control` request: "replay seq N+1 to current." The hub
  streams those records out of flash as a burst, phone slots them into
  its local store. UI scrubbing resumes seamlessly because the UI reads
  from local DB, not the hub.

**Why this model:**
- Phone has plenty of storage and compute — owns the record properly.
- Scrubbing the timeline is a local DB query → instant. No radio
  round-trip per scrub.
- Hub firmware shrinks: sequence counter (RRAM-persisted), append-only
  writes, replay-by-range. No queries, no indexing, no bookmarks.
  ~1 week of firmware work vs ~3-4 weeks for queryable-buffer design.
- Coexistence is easy: steady state is just forwarding (low BLE +
  low UWB load). Disconnect: BLE off, no concurrent radios. Reconnect:
  brief catchup burst (seconds at BLE 2M PHY), then back to steady
  state. The pathological "both radios saturated" case doesn't occur.

**Disconnect cache sizing:**
- 16 MB W25Q128 at our cycle throughput → survives any realistic BLE
  outage including whole-session disconnect (phone died, app force-
  quit, user forgot to start it). Phone gets everything on reconnect.

---

## 6. Algorithm Pipeline

### 6.1 Overview

```
   UWB ranges (per-anchor) ──┐
                             │
   Ball ADXL372 events ──────┼────► [EKF predict-update loop]
                             │           │
   Anchor positions ─────────┘           │
                                         ▼
                              [Smoothed trajectory state]
                                         │
                                         ▼
                              [Forward extrapolation past pad]
                                         │
                                         ▼
                              [LBW verdict + ellipse]
```

### 6.2 State estimation: EKF + RTS smoother

**Module:** `simulation/src/infinity_stumps/ekf.py` → `TrajectoryEKF`

**State vector:** 9-dimensional
```
x = [px, py, pz, vx, vy, vz, ωx, ωy, ωz]
    ─────────  ─────────  ──────────
     position    velocity    spin
       (m)       (m/s)       (rad/s)
```

**Dynamics model:** drag + Magnus + gravity ODE (`simulation/src/infinity_stumps/physics.py`)
```
dp/dt = v
dv/dt = -g·ẑ
        + (-½ρ·Cd·A·|v|·v) / m              ← drag
        + (½ρ·CL·A·|v|·(ω̂ × v)) / m         ← Magnus
dω/dt = 0                                    ← spin treated as constant
                                                (slow decay → process noise)
```

with `ρ = 1.20 kg/m³` (air density), `Cd = 0.40`, `CL_coef = 0.15`,
`m = 0.160 kg`, `A = π·r²` (cross-section of cricket ball).

Bounce: when `z ≤ 0` and `vz < 0`, apply coefficient of restitution:
- `vz' = -COR_vertical · vz` (COR_v = 0.55)
- `vx' = COR_horizontal · vx` (COR_h = 0.75)
- `vy' = COR_horizontal · vy`
- `z' = 0`

**EKF predict step:**
For each time advance `dt`:
1. Numerically integrate the ODE forward → new state `x_pred`
2. Compute Jacobian F = ∂x_pred/∂x via central differences
3. P_pred = F · P · F^T + Q · dt
4. Record (F, x_pred, P_pred) for the RTS smoother

**EKF measurement update (UWB range):**
For each per-anchor range arrival:
1. Predicted range: `r_pred = ||pos - anchor||`
2. Innovation: `y = r_obs - r_pred`
3. Measurement Jacobian: `H = (pos - anchor) / r_pred`, padded with zeros
4. Innovation covariance: `S = H·P·H^T + σ_range²`
5. Kalman gain: `K = P·H^T·S^-1`
6. State update: `x ← x + K·y`
7. Covariance update: `P ← (I - K·H)·P·(I - K·H)^T + K·R·K^T` (Joseph form)
8. Overwrite the filtered slot in history (the predicted is preserved
   in the RTS arrays)

**RTS smoother backward pass:**
After all measurements:
```
For k = N-1 down to 0:
    G[k]    = P_f[k] @ F[k+1]^T @ inv(P_pred[k+1])
    x_s[k]  = x_f[k] + G[k] @ (x_s[k+1] - x_pred[k+1])
    P_s[k]  = P_f[k] + G[k] @ (P_s[k+1] - P_pred[k+1]) @ G[k]^T
```

The smoothed series is the best estimate of the state at each time
using **all** measurements, not just past ones.

### 6.3 Handling TWR within-cycle stagger

Each cycle's 8 ranges aren't simultaneous — they're staggered ~150 µs
apart. The EKF handles this naturally: each per-anchor range arrival
triggers a `predict()` to the anchor's response time, then
`update_range()`. No batched approximation needed.

Within a 1.5 ms cycle, the ball moves ~45 mm at 30 m/s. Treating
ranges as simultaneous (the batch fit assumption) embeds ~22 mm RMS
systematic error per cycle. The EKF avoids this.

### 6.4 LBW prediction (post-impact)

**Module:** `simulation/src/infinity_stumps/lbw.py`

Triggered when the ball's ADXL372 detects pad impact (or by user
selecting a moment in replay):

1. **Get smoothed state at last pre-impact sample:** `x_pre = ekf.smoothed_state[-1]`
2. **Forward-integrate** the ODE from `x_pre` with no pad force,
   continuing until `x` crosses `STUMP_LINE_X = +10.06 m`
3. **Find crossing point:** linear interp gives `(t_stump, y_stump, z_stump)`
4. **Propagate covariance:** numerical Jacobian `J = ∂(y_stump, z_stump)/∂x_pre`,
   then `Σ_yz = J · P_pre · J^T`
5. **Compute 95% confidence ellipse** from eigendecomposition of `Σ_yz`
6. **Verdict:** sample the ellipse perimeter (128 points), classify each as
   inside / outside the stump rectangle (228 × 711 mm):
   - All inside → **HITTING**
   - All outside → **MISSING**
   - Mixed → **UMPIRE'S CALL**
7. **Cricket-rule preconditions:**
   - `pitched_in_line`: ball's bounce y within stump half-width
   - `impact_in_line`: ball position at pad impact within stump half-width
   - Final OUT = (pitched in line OR pitched outside off) AND impact in line AND HITTING

### 6.5 Noise model parameters

| Parameter | Value | Source |
|---|---:|---|
| σ_range (UWB) | 30 mm | DW3110 / DWM3001C datasheet |
| σ0_pos (initial) | 300 mm | Wide-open prior |
| σ0_vel (initial) | 5 m/s | Wide-open prior |
| σ0_spin (initial) | 50 rad/s | Wide-open prior |
| q_pos (process) | 1 mm/√s | ODE is nearly exact |
| q_vel (process) | 0.05 m/s/√s | Drag/Magnus model errors |
| q_spin (process) | 0.5 rad/s/√s | Slow spin axis variation |
| NLOS detection p_detect | 0.85 | Conservative chip claim |
| NLOS p_fp (LOS misclassified) | 0.02 | Conservative |
| NLOS drop probability | 0.5 | Chip can't decode |
| NLOS leakage bias | uniform(50, 200) mm | Untreated NLOS samples |

All values in `sim_realistic.py` / `sim_ekf.py` constants section.

---

## 7. Software Modules

### 7.1 `simulation/src/infinity_stumps/` — Python reference / sim implementation

| Module | Purpose |
|---|---|
| `geometry.py` | Anchor positions, pitch constants, GDOP helpers |
| `physics.py` | `BallParams`, `ball_dynamics` ODE, `integrate_trajectory`, `make_delivery` |
| `solver.py` | Reference batch multilat + batch trajectory fit (deprecated as primary) |
| `noise.py` | UWB ranging noise model + utility functions |
| `skeleton.py` | 14-bone batter model for realistic occlusion sims |
| **`ekf.py`** | **`TrajectoryEKF` (predict / update_range / update_bounce_z / smooth_backward) — production estimator** |
| `lbw.py` | LBW verdict logic, ellipse computation, cricket-rule preconditions |
| `plotting.py` | Matplotlib visualisation helpers |

### 7.2 `simulation/sims/` — Validation simulations

Each sim is standalone, writes outputs to `simulation/outputs/*.png`. See
`docs/status-2026-05-13.md` for the full inventory and results table.

The **production pipeline** is `sim_ekf` + `sim_lbw`. Other sims are
either:
- Reference / baseline (sim 03, sim_realistic)
- Architecture-rejection documentation (sim 06, sim 07)
- Exploration that didn't pan out (sim_ml)

### 7.3 Future: iPhone-side production code

Planned port (not yet built):
- **Language:** Swift 5+
- **Numerics:** Accelerate framework (LAPACK / vDSP) for ODE
  integration + matrix ops
- **ML (v2+):** CoreML for any learned components
- **Architecture:**
  - Background thread runs the EKF, processes incoming BLE notifications
  - UI thread renders SceneKit / RealityKit 3D overlay
  - Main app stores delivery records in Core Data / SQLite for replay
  - Delivery completion triggers `smooth_backward` → LBW verdict popup

---

## 8. Failure Modes & Mitigations

| Failure | Symptom | Mitigation |
|---|---|---|
| Anchor occlusion (player blocks LOS) | Few valid ranges per cycle | Huber loss + chip NLOS detection; EKF handles gracefully |
| BLE link drop | iPhone loses telemetry | Hub stump buffers to flash; phone re-syncs on reconnect |
| Ball antenna null at spin orientation | Periodic dropouts | Anchor diversity (8 anchors); rare for full delivery to be lost |
| Bowler hand on ball at release | UWB severely attenuated | Ignore first ~50 ms post-release; EKF init by next clean samples |
| Anchor moves mid-session | Position calibration stale | Detect via inter-anchor TWR drift; trigger recalibration UI prompt |
| Battery dies mid-session | Anchor falls silent | Other 7 still functional; EKF degrades gracefully to 7 ranges |
| iPhone app crash | Loss of UI / verdicts | Hub stump keeps logging; replay from flash on relaunch |
| User installs anchors at wrong height | Geometry assumption broken | Calibration step measures actual anchor positions; software adjusts |

### 8.1 Graceful degradation by valid range count

| Valid ranges per cycle | EKF behaviour |
|---:|---|
| 8 | Full update, optimal |
| 4-7 | Update with fewer measurements; slightly higher per-cycle σ |
| 1-3 | Skip update for this cycle; predict-only |
| 0 | Predict-only; uncertainty grows but trajectory continues |

The EKF naturally handles missing measurements — no special logic
required. The RTS smoother retroactively fills in dropouts.

---

## 9. Calibration

### 9.1 Anchor position calibration (one-time per setup)

User procedure:
1. Place anchors at intended positions (stump tops, PAI corners)
2. Open iPhone app → "Calibrate Pitch"
3. Walk the ball tag around the pitch perimeter for ~60 seconds
4. App runs a least-squares solver:
   - Unknowns: 8 anchor positions (24 dims, minus 6 fixed for ref
     anchor + axes)
   - Measurements: ~6000 ranges from various ball positions
   - Result: anchor positions to ~5 mm
5. App stores calibration; valid until anchors physically moved

### 9.2 Per-session sanity check

On session start, do a 30-second baseline:
- Ball tag placed at known position (e.g., on a popping crease)
- Compute expected ranges from calibrated anchor positions
- Compare to measured ranges
- Flag if σ > 60 mm (signals NLOS environment or anchor moved)

### 9.3 Coefficient of restitution (per-session, v2)

The pitch's bounciness varies (damp → 0.45, hard → 0.65). The iPhone
app can fit COR over the first 5-10 deliveries by comparing observed
post-bounce velocity (from UWB ranges bracketing the bounce) to
pre-bounce velocity. Subsequent deliveries use the calibrated COR.

Not in v1 (the EKF works with fixed COR_v = 0.55).

---

## 10. Interfaces

### 10.1 BLE service definition (hub stump → phone)

Custom service UUID: `TBD-0000-cric-uwb-hub-XXXXXXXXXXXX`

Four characteristics, mapping to the disconnect-cache data model (§5.4):

- **`Live`** (notify, ~90 bytes) — `{seq, timestamp_us, payload}` for
  each UWB cycle as it lands. Steady-state path.
- **`Control`** (write) — commands:
  - `replay {seq_start, seq_end}` — fill a gap from flash cache
  - `start_session`, `stop_session`, `start_calibration`, `reset_seq`
- **`Status`** (read) — `{oldest_seq_in_flash, newest_seq,
  free_sectors, battery_pct, fw_version, calibrated, anchor_count}`
- **`Session Metadata`** (read/write) — calibration values, anchor
  positions, pitch identifier, session ID

**Notification rate:** 100 Hz (one per UWB cycle). BLE connection
interval 7.5-15 ms accommodates. Payload ~90 bytes including framing
fits in one ATT MTU at standard 247-byte negotiation.

**Sequence counter:** monotonic, persisted to RRAM every ~10 s of
activity so it survives reboots without going backwards. Phone treats
seq as the authoritative ordering primitive; timestamps are
informational.

**Replay protocol:** phone writes `replay {N+1, current}` to `Control`,
hub streams matching records as `Live` notifications with their
original `seq` numbers (the phone tells them apart from live records
by checking seq < `current_at_request_time`). Streaming throttled to
not interfere with live cycle handling — typically completes in
seconds even for large gaps.

### 10.2 UWB-data-mode protocol (peers → hub)

Within the inter-cycle quiet period, each peer anchor sends:
- Its computed range to ball (16 bits, fp mm)
- Its NLOS-detection flag
- Its battery / temperature telemetry
- CRC

Hub aggregates 8 of these into one BLE notification.

### 10.3 iPhone app surface (placeholder; v1 UI not designed)

- Live 3D pitch view with ball trail
- Delivery list (date, type, verdict)
- Tap delivery → DRS-style replay with HIT/MISS/UMP overlay
- Export as MP4 (sharing)
- Calibration / setup wizard

---

## 11. Performance Envelope

### 11.1 Latency

| Path | Target | Notes |
|---|---:|---|
| Ball position estimate (live) | < 50 ms | EKF forward pass + BLE round-trip |
| LBW verdict after pad impact | < 1 s | Trigger → smoother → extrapolation → render |
| Calibration | < 90 s | One-time per pitch setup |
| Replay rendering | 60 fps | iPhone GPU has zero issue here |

### 11.2 Precision

See §1.3 and `docs/status-2026-05-13.md`.

### 11.3 Resource usage (iPhone)

Estimated, not yet measured:
- CPU: ~5-10% sustained (EKF per cycle is microseconds)
- Memory: < 50 MB per session
- Battery: ~5% per hour of active session (BLE is the dominant drain)
- Storage: ~5 MB per session (compressed)

---

## 12. Architectural Decision Log

Each decision links to its validation source. See full reasoning in
`CLAUDE.md` decisions list.

| # | Decision | Validation |
|---|---|---|
| 1 | Qorvo DWM3001C (vs QPK3000, Decawave, Apple U2, Murata) | Datasheet review + FiRa + ETSI + stock availability + dev kit = production part |
| 2 | 8 anchors (vs 12) | sim 02 — <2% gain not worth 50% cost |
| 3 | Wireless self-sync (vs cabled) | sim 07b — FTS at 10 Hz works |
| 4 | DS-TWR @ 100 Hz (vs TDoA, vs 150 Hz) | sim 07, `airtime-budget.md` |
| 5 | No precision IMU in ball | sim 06 |
| 6 | EKF + RTS smoother (vs batch fit) | sim_ekf, sim_lbw |
| 7 | Hub stump + iPhone (vs edge PC) | Cost + UX |
| 8 | Magnetometer-only spin path (v2) | iBall §3 + patent landscape |

---

## 13. Future Extensions (Roadmap)

### v2 (post-launch)

- **Magnetometer for spin analytics** — `BMM350` ball-side, iBall-style
  cone-fitting → spin axis + RPM. Adds coach-facing "your googly was
  X rps with Y° tilt" feature. ~£5 BOM addition.
- **Per-session COR calibration** — learn pitch bounciness in first 5-10
  deliveries.
- **Live broadcast graphics SDK** — let broadcasters embed our trajectory
  feed into their production. Forward-only EKF runs in real time.
- **Android app** — Kotlin / JNI port. Same algorithm.

### v3+ (speculative)

- **Player UWB tags** — track fielders and batter for run-out review
- **No-ball detection** — bowler foot crossing crease line
- **Edge detection** — sound sensor near stumps + UWB ball event
  cross-correlation for caught-behind
- **Multi-pitch venue mode** — manage 4-8 pitches from one phone
- **Cloud sync** — share session data across devices, team-level dashboards
- **Tightly-coupled UWB+IMU EKF** — if magnetometer-only proves
  insufficient (patent landscape permitting)

---

## 14. Glossary

| Term | Definition |
|---|---|
| **DS-TWR** | Double-Sided Two-Way Ranging — UWB ranging method that cancels clock drift via two round-trips |
| **EKF** | Extended Kalman Filter — nonlinear state estimator |
| **RTS** | Rauch-Tung-Striebel — backward smoothing pass over an EKF history |
| **NLOS** | Non-Line-of-Sight — UWB signal obstructed by a body, distorts range |
| **GDOP** | Geometric Dilution of Precision — how anchor geometry amplifies ranging noise into position noise |
| **PAI** | Protected Area Indicator — the four corner markers defined by Laws of Cricket |
| **DRS** | Decision Review System — the technology stack used in international cricket for umpire review |
| **CoR** | Coefficient of Restitution — fraction of vertical velocity retained after a bounce |
| **ETSI** | European Telecommunications Standards Institute — sets UWB duty-cycle limits |
| **FiRa** | Fine Ranging consortium — the FiRa 2.0 standard for interoperable UWB ranging |
| **TWR** | Two-Way Ranging — measures distance via timed round-trip |
| **TDoA** | Time Difference of Arrival — measures position via timing differences (rejected — sim 07) |

---

## 15. References

- iBall paper: Gowda et al., "Bringing IoT to Sports Analytics,"
  NSDI '17. https://www.usenix.org/conference/nsdi17/technical-sessions/gowda
- Qorvo DWM3001C datasheet + product brief: `docs/datasheets/`
- Cricket ball aerodynamics: Mehta, "Cricket ball aerodynamics: myth
  vs science," International Sports Engineering Conference, 2005.
- Laws of Cricket (ICC): https://www.icc-cricket.com/about/cricket/rules-and-regulations/playing-conditions
- ETSI EN 302 065-2 (UWB regulatory limits)
- See also: `docs/prior-art.md`, `docs/findings.md`, `docs/spec-v0.2.md`,
  `docs/airtime-budget.md`, `docs/phase1-2-test-plan.md`.
