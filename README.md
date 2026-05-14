# Cricket UWB Tracking — Simulation Project

Phase 0 simulation work for a UWB-based cricket ball tracking system.
Target: 10–20 mm 3D positional precision through full delivery and bounce,
using 8 Qorvo DWM3001C modules as anchors (4 stump-top + 4 in-ground PAI).

This repo is the working simulation environment. The goal is to validate
(or falsify) the precision claims before any hardware is purchased.

## What's been established so far

- **10–20 mm precision is achievable**, but the anchor geometry alone gives
  ~125 mm RMS — the precision comes from physics-constrained trajectory
  fitting (7–8x noise rejection on top of raw multilateration).
- **8 anchors is enough.** The 12-anchor upgrade (mid-stump anchors)
  gives <2% improvement and is not worth the cost.
- **The trajectory fit IS the product.** Raw point-by-point queries look
  bad; analytics on the fitted curve look excellent.

## Quick start

```bash
pip install -e .
python sims/03_trajectory_recovery.py   # the headline sim
pytest -q                               # run tests
```

Outputs land in `outputs/` as PNGs.

## Status

Phase 0 — desk study and simulation only. No hardware yet.

See `ROADMAP.md` for what to do next.
