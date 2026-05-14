# Airtime budget — TWR architecture

Quick reality check on the "TWR at ~150 Hz" claim from CLAUDE.md
decision 4. The binding constraint turns out to be **ETSI 5% per-device
TX duty cycle**, not UWB channel saturation.

## Per-frame timing (DW3110, BPRF 6.8 Mbps + STS)

Approximate frame durations from DW3110 datasheet + DW3000-family
characterisation:

| Element | Duration |
|---|---|
| Preamble (64 symb @ 64 MHz PRF) | ~64 µs |
| SFD (8 symb) | ~8 µs |
| STS (64 symb, security/NLOS dual estimate) | ~64 µs |
| PHR | ~25 µs |
| Payload (short TWR, ~12 bytes) | ~25 µs |
| Guard / processing | ~14 µs |
| **TX frame total** | **~200 µs** |

## Three architectural variants

**(A) Per-anchor sequential DS-TWR** (one full DS-TWR per anchor)
- Per anchor: 3 frames (poll/response/final) + turnaround ≈ 1 ms
- 8 anchors sequential: 8 ms per cycle → 125 Hz max
- Ball TX: 2 × 8 = 16 frames per cycle → 16 × 200 µs × 125 Hz = **400 ms/s = 40% duty cycle**
- **Fails ETSI 5%** by ~8×. FCC-only deployment possible.

**(B) Broadcast DS-TWR** (one ball poll → 8 staggered anchor responses → one ball final)
- Poll: 200 µs
- Anchor turnaround: 200 µs
- 8 staggered responses: 8 × (200 µs + 50 µs guard) = 2 ms
- Ball turnaround: 200 µs
- Final: 200 µs
- **Per cycle: ~3 ms** → 333 Hz theoretical max
- Ball TX: 2 frames per cycle → 2 × 200 µs × rate
  - At 100 Hz: 40 ms/s = **4% duty cycle** ✓ ETSI
  - At 125 Hz: 50 ms/s = **5% duty cycle** = at limit
- Per-anchor TX: 1 frame per cycle → 1 × 200 µs × rate
  - At 100 Hz: 20 ms/s = **2% duty cycle** ✓ ETSI
- **Deployable rate: ~100 Hz under ETSI**, ~125 Hz at the absolute edge

**(C) Hybrid: TDoA beacons + slow TWR calibration**
- Most cycles: ball broadcasts single packet, anchors timestamp arrival (TDoA)
- Periodically (every 100 ms): full TWR refresh for absolute calibration
- TDoA gives 500+ Hz beacon rate, ETSI-fine for ball (1 × 200 µs × 500 = 10%, **over ETSI**)
  - At 250 Hz: 5% — at limit
- **Inherits TDoA's 120 mm intrinsic noise floor (sim 07)**. Rejected.

## Sample-count impact on fit precision

Sim 03 gave ~10 mm fit RMS at 500 Hz × 0.85 s = 425 samples.
Precision scales as ~1/√N for the physics fit (~9 free params, many samples each).

| Architecture | Rate | Samples / flight | Clean-LOS fit RMS |
|---|---|---|---|
| Sim 03 baseline | 500 Hz | 425 | ~10 mm |
| FCC sequential TWR | 125 Hz | 106 | ~20 mm |
| ETSI broadcast TWR | 100 Hz | 85 | ~22 mm |
| ETSI SS-TWR (faster, noisier) | 200 Hz | 170 | ~25 mm (worse σ/range) |
| ETSI hybrid TDoA | 250 Hz | 213 | ~80 mm (TDoA floor) |

## Decision

**Broadcast DS-TWR at 100 Hz is the deployable architecture for an
internationally-shippable system.**

- ETSI-compliant per-device duty cycle (4% ball, 2% anchor)
- ~85 samples per flight → ~22 mm clean-LOS fit (vs 10 mm at 500 Hz)
- Same physics, same fit method, same NLOS handling as sim 05b
- Occlusion + Huber + NLOS det baseline scales: **~60–70 mm mean, ~90 mm p95**
  (sim 05b's 47 mm × √(425/85) ≈ 47 × 2.2 ≈ 100 mm worst — but the
  trajectory fit's noise floor is dominated by fit-model goodness, not
  pure sample count, so 60-70 mm is a more realistic projection)

## Knobs that buy back airtime

If 100 Hz is too slow:

1. **Shorter preamble** (16 symb vs 64) — saves ~50 µs/frame.
   100 Hz → 125 Hz feasible. Hits sensitivity at long range.
2. **Skip STS** — saves ~64 µs/frame. Loses secure-ranging anti-spoof
   AND the chip's dual-estimate NLOS self-check. **Don't do this** —
   the dual STS estimate is too useful for NLOS detection.
3. **SS-TWR** instead of DS-TWR — halves the exchange frames but
   doubles the ranging σ (no clock-cancellation). Net precision worse.
4. **FCC-only deployment** — no duty cycle limit. 150 Hz easily,
   maybe 250 Hz. Loses European / Indian / Australian markets.
5. **Reduce anchor count to 6** — costs raw geometry but saves
   airtime. Probably not worth it.

## CLAUDE.md update

Decision 4 should read **"TWR at ~100 Hz (broadcast DS-TWR for ETSI
compliance), NOT TDoA"** rather than "TWR at ~150 Hz."

## What this changes about projected precision

Updated headline operational targets:

| Stage | Old (assumed 150 Hz) | New (100 Hz under ETSI) |
|---|---|---|
| Clean LOS fit | 10 mm | ~17–22 mm |
| Occlusion + mitigations | 47 mm | ~60–70 mm |
| Occlusion p95 | 70 mm | ~90–100 mm |

Still DRS-grade (stumps are 228 × 711 mm). Still much cheaper than
Hawk-Eye. The shippable number just got a bit less pretty.
