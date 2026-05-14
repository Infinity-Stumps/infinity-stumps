# Infinity Stumps

**DRS for the rest of us.** Hawk-Eye-class ball tracking and LBW prediction
for cricket, at roughly 1/30th the cost — running on a consumer phone.

[![CI](https://github.com/Infinity-Stumps/infinity-stumps/actions/workflows/ci.yml/badge.svg)](https://github.com/Infinity-Stumps/infinity-stumps/actions/workflows/ci.yml)
&nbsp;Apache-2.0 / CERN-OHL-S / CC-BY-4.0

---

Eight ultra-wideband (UWB) anchors around a cricket pitch, a tag inside the
ball, and a phone that does all the maths. It tracks the ball in 3D, predicts
trajectories, and renders DRS-style LBW verdicts — for the 99% of cricket
played in clubs, schools, academies, and back gardens that has never had
access to ball-tracking analytics.

The whole system is **open by design** — public from day one as dated,
detailed prior art so the techniques can't be locked up by anyone else.
See [`docs/about.md`](docs/about.md) for the what, why, and the open-source
posture.

## Headline results

Phase 0 simulation, n=30 deliveries at 100 Hz with a realistic occlusion
model (skeleton batter + Law-41 bowler), EKF + RTS smoother pipeline:

| Metric | Result | iBall (NSDI '17) | |
|---|--:|--:|--|
| Lateral median error at the stump line | **9.1 mm** | 99 mm | 11× better |
| 3D median error at the stump line | **28.0 mm** | 220 mm | 7.9× better |
| LBW verdict accuracy (exact match) | **96.7%** | — | 29/30 |
| False positives (wrong OUT) | **0** | — | across all 30 |

Full breakdown in [`docs/status-2026-05-13.md`](docs/status-2026-05-13.md).

## Repository layout

This is a monorepo, one directory per discipline:

| Directory | What's in it | Status |
|---|---|---|
| [`simulation/`](simulation/) | The Python estimation + LBW pipeline — physics EKF, RTS smoother, verdict logic, and the simulation harnesses that validate them. | Phase 0 complete |
| [`firmware/`](firmware/) | Anchor and ball-tag firmware for the Qorvo DWM3001C (C / nRF Connect SDK). | Not started |
| [`hardware/`](hardware/) | KiCad PCB projects and enclosure design. | Not started |
| [`app/`](app/) | The mobile app — iOS first; runs the full pipeline on-device. | Not started |
| [`docs/`](docs/) | System-level architecture, BOM, prior-art strategy, test plans. | Living |

Each directory has its own README with the detail.

## How the system works

```
  ball tag ──UWB DS-TWR @ 100 Hz──▶ 8 anchors ──▶ hub stump ──BLE──▶ phone
                                                                      │
                          per-anchor ranges ──▶ physics EKF ──────────┤
                                               + RTS smoother         │
                                               + LBW verdict          ▼
                                                          trajectory + verdict
```

- **Hardware** — 8 Qorvo DWM3001C anchors (4 stump-top, 4 ground-level), one
  designated the hub stump; a DWM3001C + impact accelerometer in the ball.
- **Estimation** — a 9-state physics EKF over (position, velocity, spin) with
  a drag + Magnus + gravity ODE, plus an RTS backward smoother for
  replay-quality precision. Runs on the phone.
- **LBW** — forward-extrapolates past the pad to the stump line, propagates the
  EKF covariance into a 95% confidence ellipse, classifies it against the
  stump rectangle as HITTING / MISSING / UMPIRE'S CALL.

## Getting started

The Phase 0 work lives in [`simulation/`](simulation/) — see its README:

```bash
cd simulation
make install
make test
python sims/sim_lbw.py
```

## Documentation

- [`docs/about.md`](docs/about.md) — what this is, the open-source posture, the prior-art strategy.
- [`docs/architecture.md`](docs/architecture.md) — full system architecture.
- [`docs/bom.md`](docs/bom.md) — active bill of materials (Qorvo DWM3001C platform).
- [`docs/prior-art.md`](docs/prior-art.md) — iBall (NSDI '17) analysis and borrowed techniques.
- [`docs/status-2026-05-13.md`](docs/status-2026-05-13.md) — current results in detail.
- [`docs/phase1-2-test-plan.md`](docs/phase1-2-test-plan.md) — hardware bring-up plan.
- `CLAUDE.md` — the running decision log. `CONTRIBUTING.md` — how to work on the project.

## Licence

Three licences by file type:

- **Software** (`simulation/`, `firmware/`, `app/`) — Apache-2.0 ([`LICENSE`](LICENSE))
- **Hardware designs** (`hardware/`) — CERN-OHL-S v2 ([`LICENSE-hardware`](LICENSE-hardware))
- **Documentation** (`docs/`, READMEs) — CC-BY-4.0 ([`LICENSE-docs`](LICENSE-docs))

## Acknowledgements

Built on **iBall** (Gowda et al., *Bringing IoT to Sports Analytics*, NSDI '17),
which established UWB ranging + physics-fit + LBW extrapolation for a cricket
ball as public prior art. This project productises that idea with modern
silicon, an 8-anchor topology, and outdoor validation.
