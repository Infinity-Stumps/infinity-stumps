# Infinity Stumps

**DRS for the rest of us.** Hawk-Eye-class ball tracking and LBW prediction
for cricket, at roughly 1/30th the cost — running on a consumer phone.

[![CI](https://github.com/Infinity-Stumps/infinity-stumps/actions/workflows/ci.yml/badge.svg)](https://github.com/Infinity-Stumps/infinity-stumps/actions/workflows/ci.yml)
&nbsp;Python 3.10–3.12 &nbsp;|&nbsp; Apache-2.0 / CERN-OHL-S / CC-BY-4.0

---

Eight ultra-wideband (UWB) anchors around a cricket pitch, a tag inside the
ball, and a phone that does all the maths. It tracks the ball in 3D, predicts
trajectories, and renders DRS-style LBW verdicts — for the 99% of cricket
played in clubs, schools, academies, and back gardens that has never had
access to ball-tracking analytics.

This repository is the **Phase 0 simulation** work: the estimation and
prediction pipeline, validated end-to-end in simulation before any hardware
is built. It is public from day one as dated, open prior art (see
[`docs/about.md`](docs/about.md)).

## Headline results

Simulated, n=30 deliveries at 100 Hz with a realistic occlusion model
(skeleton batter + Law-41 bowler), EKF + RTS smoother pipeline:

| Metric | Result | iBall (NSDI '17) | |
|---|--:|--:|--|
| Lateral median error at the stump line | **9.1 mm** | 99 mm | 11× better |
| 3D median error at the stump line | **28.0 mm** | 220 mm | 7.9× better |
| Trajectory RMS (replay) | **47.3 mm** | — | |
| LBW verdict accuracy (exact match) | **96.7%** | — | 29/30 |
| False positives (wrong OUT) | **0** | — | across all 30 |

Full breakdown in [`docs/status-2026-05-13.md`](docs/status-2026-05-13.md).

## How it works

```
  ball tag ──UWB DS-TWR @ 100 Hz──▶ 8 anchors ──▶ hub stump ──BLE──▶ phone
                                                                      │
                          per-anchor ranges ──▶ physics EKF ──────────┤
                                               + RTS smoother         │
                                               + LBW verdict          ▼
                                                          trajectory + verdict
```

- **Physics EKF** — a 9-state Extended Kalman Filter over (position, velocity,
  spin), propagated with a drag + Magnus + gravity ODE and updated per UWB
  range measurement. Runs forward in real time for a live overlay.
- **RTS smoother** — a Rauch–Tung–Striebel backward pass that retrofits past
  estimates with later measurements for replay-quality precision.
- **LBW pipeline** — forward-extrapolates the ball past the pad to the stump
  line, propagates the EKF covariance into a 95% confidence ellipse, and
  classifies it against the stump rectangle as HITTING / MISSING / UMPIRE'S CALL.

## Repository layout

| Path | What's in it |
|---|---|
| `src/infinity_stumps/` | The library — geometry, physics, solvers, EKF, LBW. |
| `src/infinity_stumps/geometry.py` | Pitch geometry, anchor layouts, GDOP. |
| `src/infinity_stumps/physics.py` | Ball flight dynamics (drag + Magnus + gravity, bounce). |
| `src/infinity_stumps/solver.py` | Multilateration and physics-constrained trajectory fit. |
| `src/infinity_stumps/ekf.py` | The production estimator: trajectory EKF + RTS smoother. |
| `src/infinity_stumps/lbw.py` | LBW extrapolation, uncertainty ellipse, verdict logic. |
| `src/infinity_stumps/noise.py` | UWB ranging noise models (Gaussian + occlusion/NLOS). |
| `src/infinity_stumps/skeleton.py` | Anthropometric skeleton batter for the occlusion model. |
| `sims/` | Standalone simulation scripts — each writes a PNG to `outputs/`. |
| `tests/` | Per-module test suite (`pytest`). |
| `docs/` | Architecture, BOM, prior-art strategy, test plans. |
| `outputs/` | Committed simulation result figures. |

## Quickstart

Requires Python 3.10+.

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
| `06_imu_fusion.py` | Complementary-filter IMU fusion (rejected — see `docs/findings.md`). |
| `07_sync_budget.py` | TDoA noise floor (why the system uses TWR, not TDoA). |
| `11_ground_multipath.py` | Outdoor ground-reflection multipath. |

## Documentation

- [`docs/about.md`](docs/about.md) — what this is, the open-source posture, and the prior-art strategy.
- [`docs/architecture.md`](docs/architecture.md) — full system architecture.
- [`docs/bom.md`](docs/bom.md) — active bill of materials (Qorvo DWM3001C platform).
- [`docs/prior-art.md`](docs/prior-art.md) — iBall (NSDI '17) analysis and borrowed techniques.
- [`docs/status-2026-05-13.md`](docs/status-2026-05-13.md) — current results in detail.
- [`docs/phase1-2-test-plan.md`](docs/phase1-2-test-plan.md) — hardware bring-up plan.
- `CLAUDE.md` — the running decision log.

## Project status

Phase 0 (simulation) is complete. Hardware bring-up (Phase 1+2) is next, on
Qorvo DWM3001C modules. The iOS app and full-pitch outdoor validation follow.
This repo currently contains the simulation pipeline only — no hardware or
app code yet.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). In short: `make check` must pass,
and the project values dated decisions and explicit reasoning — match that
style and contributions land easily.

## Licence

This project uses three licences by file type:

- **Software** (`src/`, `sims/`, `tests/`) — Apache License 2.0 ([`LICENSE`](LICENSE))
- **Hardware designs** — CERN-OHL-S v2 ([`LICENSE-hardware`](LICENSE-hardware))
- **Documentation** (`docs/`, `README.md`) — CC-BY-4.0 ([`LICENSE-docs`](LICENSE-docs))

## Acknowledgements

Built on **iBall** (Gowda et al., *Bringing IoT to Sports Analytics*, NSDI '17),
which established UWB ranging + physics-fit + LBW extrapolation for a cricket
ball as public prior art. This project productises that idea with modern
silicon, an 8-anchor topology, and outdoor validation.
