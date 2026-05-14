# App

The mobile app — the compute and UI half of Infinity Stumps. It connects
to the hub-stump anchor over a single BLE link, runs the full estimation
pipeline on-device, and renders the trajectory and LBW verdict.

There is **no edge PC** in the system: the phone does all the maths.

## Layout

| Directory | Contents |
|---|---|
| `ios/` | The iOS app (built first). Swift, with the EKF + RTS smoother and LBW pipeline ported to Accelerate / CoreML. Targets iPhone and iPad. |

Android follows iOS once the architecture is proven on one platform —
it will live in `app/android/` when it starts.

## What the app does

- Pairs with the hub-stump anchor over BLE; receives the consolidated
  per-cycle range stream (and gap-fills from the hub's disconnect cache
  after any dropout).
- Runs the physics EKF for a live trajectory overlay, and the RTS
  smoother for DRS-quality replay.
- Produces the LBW verdict — extrapolation, 95% confidence ellipse,
  HITTING / MISSING / UMPIRE'S CALL.
- Handles the 60-second walk-around anchor calibration.

The reference algorithms it implements live in `simulation/` — that is
the spec the app is ported from.

## Status

Not started. The architecture is validated in simulation; no app code yet.

## Licence

Apache-2.0 (see `LICENSE` at the repo root).
