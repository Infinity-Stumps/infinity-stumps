# Infinity Stumps — Simulation

The Python estimation and LBW-prediction pipeline, plus the simulation
harnesses that validate it. This is the **Phase 0** work: the algorithm
architecture proven end-to-end in simulation before any hardware is built.

It is also the reference spec the firmware and the mobile app are ported
from — see the other top-level directories and the repo-root
[`README.md`](../README.md) for the whole-system picture.

## Headline results

n=30 deliveries at 100 Hz with a realistic occlusion model (skeleton
batter + Law-41 bowler), EKF + RTS smoother pipeline:

| Metric | Result | iBall (NSDI '17) | |
|---|--:|--:|--|
| Lateral median error at the stump line | **9.1 mm** | 99 mm | 11× better |
| 3D median error at the stump line | **28.0 mm** | 220 mm | 7.9× better |
| Trajectory RMS (replay) | **47.3 mm** | — | |
| LBW verdict accuracy (exact match) | **96.7%** | — | 29/30 |
| False positives (wrong OUT) | **0** | — | across all 30 |

Full breakdown in [`../docs/status-2026-05-13.md`](../docs/status-2026-05-13.md).

## The pipeline

- **Physics EKF** — a 9-state Extended Kalman Filter over (position, velocity,
  spin), propagated with a drag + Magnus + gravity ODE and updated per UWB
  range measurement. Runs forward in real time for a live overlay.
- **RTS smoother** — a Rauch–Tung–Striebel backward pass that retrofits past
  estimates with later measurements for replay-quality precision.
- **LBW pipeline** — forward-extrapolates the ball past the pad to the stump
  line, propagates the EKF covariance into a 95% confidence ellipse, and
  classifies it against the stump rectangle as HITTING / MISSING / UMPIRE'S CALL.

## Layout

| Path | What's in it |
|---|---|
| `src/infinity_stumps/geometry.py` | Pitch geometry, anchor layouts, GDOP. |
| `src/infinity_stumps/physics.py` | Ball flight dynamics (drag + Magnus + gravity, bounce). |
| `src/infinity_stumps/solver.py` | Multilateration and physics-constrained trajectory fit. |
| `src/infinity_stumps/ekf.py` | The production estimator: trajectory EKF + RTS smoother. |
| `src/infinity_stumps/lbw.py` | LBW extrapolation, uncertainty ellipse, verdict logic. |
| `src/infinity_stumps/noise.py` | UWB ranging noise models (Gaussian + occlusion/NLOS). |
| `src/infinity_stumps/skeleton.py` | Anthropometric skeleton batter for the occlusion model. |
| `sims/` | Standalone simulation scripts — each writes a PNG to `outputs/`. |
| `tests/` | Per-module test suite (`pytest`). |
| `outputs/` | Committed simulation result figures. |

## Quickstart

Requires Python 3.10+. Run everything from this directory.

```bash
make install      # editable install with dev extras + pre-commit hooks
make test         # run the test suite
make check        # the full gate: lint + typecheck + test
make sims         # regenerate every figure in outputs/
```

`make help` lists every target. Without `make`:

```bash
pip install -e ".[dev]"
pytest
python sims/sim_lbw.py
```

## Simulations

Each script in `sims/` is self-contained and writes a figure to `outputs/`.

| Script | What it shows |
|---|---|
| `sim_ekf.py` | **EKF + RTS smoother** — the production estimator (current primary). |
| `sim_lbw.py` | **LBW prediction + verdict** — 96.7% exact-match accuracy. |
| `sim_realistic.py` | Batch-fit baseline under realistic occlusion (deprecated primary). |
| `sim_ml.py` | ML correction-layer exploration (concluded net-neutral). |
| `01_precision_map.py` | GDOP map across the pitch. |
| `02_anchor_comparison.py` | 8 vs 12 anchors (12 rejected — <2% gain). |
| `03_trajectory_recovery.py` | Clean-LOS physics fit. |
| `05_multipath_occlusion.py` | NLOS impact, no mitigations (the problem). |
| `05b_occlusion_mitigations.py` | Huber loss + NLOS detection (the fix). |
| `06_imu_fusion.py` | Complementary-filter IMU fusion (rejected — see `../docs/findings.md`). |
| `07_sync_budget.py` | TDoA noise floor (why the system uses TWR, not TDoA). |
| `11_ground_multipath.py` | Outdoor ground-reflection multipath. |

## Contributing

See [`../CONTRIBUTING.md`](../CONTRIBUTING.md). In short: `make check` must
pass, and the project values dated decisions and explicit reasoning.

## Licence

Apache-2.0 (see [`../LICENSE`](../LICENSE)).
