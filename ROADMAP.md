# Roadmap — Next Simulations

Prioritised list. Each entry has a Claude-Code-ready prompt and an exit
criterion. Tier 1 items are project-critical.

---

## TIER 1 — Project-critical unknowns

### Sim 04 — Sliding-window real-time filter

**Why:** Sim 03 used a batch fit on the complete trajectory. Live use
needs a recursive estimator that only sees past samples. If precision
loss is 2× we're fine, if 10× the real-time product is broken.

**Prompt:**
Read CLAUDE.md and simulation/src/infinity_stumps/. Create simulation/sims/04_sliding_window.py:

Reuse the trajectory generator and noise model from sim 03.
Implement a sliding-window physics-fit estimator that, at each time t,
fits the physics model to samples up to t only (try windows of 100,
200, full history).
Compare estimates against ground truth at each instant.
Also implement a 6-state Kalman filter (position + velocity) with
physics-driven process model.
Plot precision vs time for batch / sliding-200 / Kalman on a single
delivery and as Monte Carlo over 50 deliveries.

Exit: precision-penalty ratio (RMS real-time / RMS batch), and whether
the Kalman is competitive with the sliding-window fit.

### Sim 05 — Multipath and occlusion

**Why:** Previous sims assumed clean LOS. Real cricket has bowler-
in-stride, umpire, keeper, slips intermittently blocking paths.

**Prompt:**
Build simulation/sims/05_multipath_occlusion.py:

Add 6 cylindrical occluders (bowler, umpire, keeper, 2 slips, gully)
at realistic positions. Anchor-ball rays within 0.4 m of an occluder
are either dropped (50% chance) or get a +50 to +200 mm bias added.
Bowler occluder moves: behind stumps at delivery, advances 5 m down
pitch in 0.5 s.
Verify the range-based multilateration solver (TWR architecture, see
CLAUDE.md decision 4) is robust to fewer than 8 anchors.
Run trajectory recovery with this realistic model. Compare batch and
sliding-window precision against clean-LOS baseline.

Exit: numbers on (a) fraction of samples losing anchors, (b) precision
degradation factor, (c) whether 8 anchors is still enough.

### Sim 06 — IMU fusion

**Why:** The in-ball tag has a 6-axis IMU. Adding it should reduce the
parameter space and bridge UWB dropouts.

**Prompt:**
Build simulation/sims/06_imu_fusion.py:

Model a 6-axis IMU. Accelerometer reads body-frame accel + gravity
with σ_a = 0.05 m/s². Gyro reads body-frame angular rate with
σ_g = 0.01 rad/s plus bias random walk. 1 kHz sample rate.
Coordinate frames: ball rotates at ~25 rev/s. Integrate gyro for
attitude, transform accel to world, integrate for vel+pos.
Tightly-coupled EKF combining UWB ranges and IMU.
Test against sim 05's occlusion model.

Exit: precision comparison (UWB only) vs (UWB + IMU) under clean LOS
and occluded conditions. Clear answer on whether the IMU is required
or just nice-to-have.

---

## TIER 2 — Sync engine and system-level

### Sim 07 — Anchor sync error budget

**Prompt:**
Build simulation/sims/07_sync_budget.py. Each anchor has its own clock with crystal
drift (20 ppm, random-walk-plus-bias). Inter-anchor TWR at 10 Hz produces
noisy clock-offset observations (σ = 30 ps). Linear regression per anchor
predicts the relationship to master. When a ball beacon arrives, each
anchor timestamps it on its own clock; the predicted relationship
translates to a common frame.
Vary inter-anchor sync rate (1/10/100 Hz) and crystal stability
(TCXO vs XO). Recommend spec.
Exit: clear answer on sync rate / oscillator class for production spec.

### Sim 08 — Anchor self-localisation

**Prompt:**
Build simulation/sims/08_self_localization.py. Place anchors at nominal positions
+ random perturbations (~50 mm 1σ). Use known constraint distances
(stump width, PAI lateral spread, pitch length) plus measured pairwise
UWB ranges to estimate positions in a self-consistent frame. Run with
30 mm range noise. Use the estimated geometry for ball tracking — how
does error propagate?

Exit: residual self-loc error <30 mm per anchor; ball-tracking precision
degrades by <10% vs perfect-knowledge geometry.

### Sim 09 — Scheduling and airtime

**Prompt:**
Build simulation/sims/09_scheduling.py. Time-slotted airtime with 50 µs slots.
Inter-anchor sync: 28 exchanges every 100 ms. Ball beacons: every 2 ms.
Account for FCC/ETSI UWB duty-cycle limits (~5%). Stats on packet loss,
collision rate, latency.
Exit: prove schedule fits within regulatory limits with margin; quantify
expected packet success rate.

---

## TIER 3 — Refinement
- Sim 10 — Bounce model (variable pitch state)
- Sim 11 — Spinning antenna pattern
- Sim 12 — Different bowling styles (spin, swing)
- Sim 13 — Weather effects

## TIER 4 — Engineering scoping
- Doc 01 — Power budget from DWM3001C datasheet
- Doc 02 — Mechanical design (stump + PAI enclosures)
- Doc 03 — Formal patent landscape search

---

## How to use

1. `cd infinity-stumps`
2. Open Claude Code in the directory
3. Pick a sim, paste its prompt
4. Review generated code and outputs
5. Commit and move on. Don't run all of Tier 1 at once — review each.
