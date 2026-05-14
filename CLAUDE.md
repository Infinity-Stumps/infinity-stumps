# Context for Claude Code

You're helping continue Phase 0 simulation work on a UWB cricket ball
tracking project.

## Mission: DRS for the rest of us

Make professional-grade Decision Review System tracking **accessible**.
Hawk-Eye is £100K+ and locked to professional cricket. We're building a
**~£1,500 system + a phone app** that delivers Hawk-Eye-class precision
to local clubs, schools, coaches, and individual players.

## Prior art (not a patent — an execution play)

The core idea (UWB ranging + physics-constrained trajectory fit + LBW
extrapolation for a cricket ball) was published in 2017 by Gowda et al.
("Bringing IoT to Sports Analytics" — iBall, NSDI '17, UIUC + Intel).
See `docs/prior-art.md`. They demonstrated 8 cm median location error
indoors with 2 anchors + AoA fusion and showed LBW prediction at
22 cm 3D / 9.9 cm X-axis (within ICC's 10 cm tolerance). The paper
sat dormant — nobody productised it.

**Our job is to ship it.** Our advantages are entirely about
**execution**, not concept:
- 8 anchors (kills their dilution-of-precision problem) vs 2
- 5× better silicon (Qorvo DW3110 FiRa/802.15.4z, ~3 cm raw vs ~15 cm)
- Outdoor validation (they explicitly punted)
- Hub-stump + iPhone topology (no edge PC)
- Modern NLOS detection from chip CIR
- Realistic occlusion modelled (skeleton batter sim)
- Consumer product, not research prototype

A UWB-based tracking system for cricket balls delivering 17–22 mm 3D
precision in clean LOS / **35 mm median, 78 mm p95** under realistic
occlusion at 100 Hz. Eight Qorvo DWM3001C modules as anchors (4 at top
of stumps, 4 in-ground at PAIs), one DWM3001C + ADXL372 in the ball.

The physics-constrained fit (drag + Magnus + gravity, 10 free params
fit to ~70 samples per delivery at 100 Hz) is the engine; everything
else is engineering around it.

## Key decisions already made

1. Hardware platform: Qorvo DWM3001C module (DW3110 UWB + nRF52833
   BLE/MCU + integrated antenna, 3-axis accel and 32.768 kHz LFXO on
   module, nRF Connect SDK). Switched from QPK3000 on 2026-05-14 —
   available from stock, the DWM3001CDK dev kit *is* the production
   module, and it integrates the accel + crystal. omlox is not
   pre-loaded; the peer-to-hub data path is a thin fixed-schedule
   TDMA layer on the 802.15.4z PHY.
2. Anchor count: 8. The 12-anchor upgrade was simulated and rejected
   (<2% precision improvement for ~50% more cost).
3. Sync architecture: wireless UWB self-sync via inter-anchor TWR at
   10 Hz (FTS-style disciplined timer per sim 07b), no cabling.
4. **Positioning: broadcast DS-TWR at ~100 Hz, NOT TDoA.** Initial spec
   said TDoA at 500 Hz, rejected by sim 07 (~120 mm intrinsic floor).
   First TWR claim was 150 Hz, but `docs/airtime-budget.md` showed
   that exceeds ETSI 5% per-device duty cycle. Broadcast DS-TWR (one
   ball poll → 8 staggered anchor responses → one ball final) at
   100 Hz is the ETSI-compliant deployment rate (4% ball, 2%
   per-anchor TX duty cycle). The earlier sims (03, 05, 05b) ran at
   500 Hz; scale their numbers by ~√(425/85) ≈ 2.2× for the
   operational rate — so 47 mm under occlusion becomes ~60–70 mm. The
   physics conclusions still hold; only the sample count differs.
5. Ball-side: one DWM3001C + **two-tier impact sensing**:
   - **ADXL372** (±200g) for bounce/pad/bat *timing* — saturates on
     all real cricket impacts (~6000g peak) but reliably reports
     spike timestamps to ~1 ms precision.
   - **Piezoelectric impact sensor** (e.g., PCB Piezotronics 35x
     series or Meggitt Endevco 7270A class, ±10,000-50,000g) for
     measuring the **full impact impulse magnitude**. Integrating
     this over the ~0.5 ms contact reads out the velocity change
     Δv at impact, from which the **incoming vertical velocity v_in
     at bounce** is recoverable via Δv = -(1+COR_v)·v_in. Combined
     with bounce timing + gravity, this **physics-determines the
     entire z-trajectory** without relying on the UWB anchors'
     weak vertical baseline (GDOP_z ≈ 8 at mid-pitch). Expected to
     drop Z-axis fit error from ~60 mm → single-digit mm.
   Precision-tracking IMU dropped from v1 BOM — sim 06 showed
   complementary-filter fusion is the wrong architecture for this
   problem (IMU integration drift hurts more than it helps at 100 Hz
   UWB with no dropouts). v2 could revisit with tightly-coupled
   fusion (sim 06b — not built).
6. Analytics: **physics-EKF with RTS smoother**. The state-space
   estimator (`src/cricket_uwb/ekf.py`) runs a continuous EKF over
   (position, velocity, spin) using the drag+Magnus+gravity ODE for
   prediction and per-anchor TWR range measurements for updates. A
   Rauch-Tung-Striebel backward pass refines past estimates using
   future measurements. Same code handles two modes:
     - **Forward only** → live broadcast overlay (real-time, 47 mm
       mean / 61 mm p95)
     - **Forward + RTS** → DRS replay (post-flight, **beats batch fit
       on p95 and lateral**: 47 mm mean / 61 mm p95 / 8.7 mm y-axis)
   This supersedes the earlier "batch fit only" architecture. The
   batch fit (`fit_trajectory` in solver.py) is kept as a reference
   implementation but the EKF+RTS is the production path.
7. **System topology: hub-stump + iPhone-as-compute.** One anchor (a
   stump-top, naturally central in the geometry) acts as the system
   hub: it is the UWB sync master for the other 7, aggregates their
   ranges over UWB-data-mode packets, and forwards the consolidated
   stream to a consumer device over a single BLE link. The **iPhone
   (or iPad)** runs the multilat + Huber physics fit + ML layers in
   Swift + Accelerate + CoreML. No edge controller (Pi/Jetson) in the
   BOM. Benefits: single BLE peripheral to manage (vs 8), hub buffers
   for graceful app-lifecycle handling, and the hub can log to flash
   when no phone is present (acts as a self-contained recorder).
   7 "dumb" anchors + 1 "hub stump" are the same hardware — just
   different firmware images. This topology is our engineering
   contribution beyond iBall, whose architecture was anchor → PC.

## HARD RULES (DO NOT VIOLATE)

- **NEVER run any sim at 500 Hz or any rate above 100 Hz.** The
  deployable rate is 100 Hz (ETSI duty-cycle constraint, see
  `docs/airtime-budget.md`). 500 Hz produces aspirational numbers
  that require constant √5 scaling and have been a major source of
  confusion. **Use 100 Hz everywhere, always.** This includes new
  sims, re-runs of old sims, and any debugging. If a sim file was
  written at 500 Hz historically (sims 03, 05, 05b, 07, 11), don't
  re-run it without converting to 100 Hz first.

## What to NOT touch

- Anchor geometry constants in `geometry.py` are calibrated to Laws of
  Cricket. Don't change PITCH_HL, PAI_X, PAI_Y, STUMP_W, STUMP_TOP.
- 30 mm ranging σ in `noise.py` is the conservative DW3110 outdoor
  estimate.
- Cricket ball physics constants (Cd=0.4, CL_coef=0.15, m=0.160 kg,
  r=0.0356 m) are within published ranges.

## What to focus on

1. **LBW prediction module** (`sims/sim_lbw.py`, `src/cricket_uwb/lbw.py`):
   forward extrapolation + uncertainty ellipse at stump line + HIT/MISS/
   UMPIRE'S CALL verdict. Target: beat iBall's 22 cm 3D / 9.9 cm X-axis.
2. **iBall borrowables** (see `docs/prior-art.md`):
   - **Bouncing constraint** — pin z=0 at bounce in the physics fit
   - **AoA / PDoA fusion** — Qorvo DW3110 supports phase-difference
     of arrival; add as a constraint
   - **DoP-weighted residuals** — complement to Huber loss
   - **Magnetometer-based spin** (v2) — gyros saturate above ~6 rps;
     iBall's trick uses magnetometer + cone-fitting instead.
3. Phase 1+2 firmware bring-up when the 3× DWM3001CDK boards arrive.

## Coding conventions

- Python 3.10+, numpy / scipy / matplotlib only
- Type hints on public functions
- Each `sims/NN_*.py` is standalone, writes to `outputs/`
- Tests in `tests/`, run with `pytest -q`

## Findings to remember

- Ground-plane-heavy anchor layout has bad raw Z resolution mid-pitch
  (GDOP ~8 at z=0.5 m).
- Physics fit overcomes this because the trajectory is overdetermined
  (~40 samples per free parameter).
- For real-time use expect 2–4× precision degradation vs batch fit —
  to be confirmed in sim 04 (deprioritised, see decision 6).
- **TDoA was a wrong call** — sim 07 found 120 mm intrinsic noise
  floor with perfect sync. Architecture pivoted to TWR. Don't
  recommend TDoA without flagging that it tanks the precision target.
- Untreated NLOS bias is catastrophic (225 mm RMS, sim 05). Always
  pair Huber loss with NLOS detection. Above ~85% true-positive
  detection rate there are diminishing returns (sim 05b).
- **EKF + RTS smoother is the production analytics pipeline**
  (sim_ekf.py, n=30):
    - Forward only:  47 mm mean / 47 mm med / 61 mm p95  (real-time)
    - + RTS smoother: same — RTS retrofits past estimates with future
      data, killing the tail. Y-axis 8.7 mm (sub-cm lateral!).
  Beats the older batch-fit baseline (41 mm mean / 78 mm p95) on
  the metrics that matter most (p95 and lateral), at the cost of
  +6 mm on mean. The architecture is genuinely real-time-capable —
  live broadcast overlay was previously impossible.
- Batch fit (`fit_trajectory`) still produces 41 mm mean / 78 mm p95
  but is deprecated as primary; kept only for reference / batch
  re-processing. EKF+RTS is the path forward.
- Hawk-Eye-class precision for cheap.
