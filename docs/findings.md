# Findings — Phase 0 Simulation

## Architecture pivot — broadcast DS-TWR at 100 Hz (READ THIS FIRST)

The initial spec assumed TDoA at 500 Hz. Sim 07 measured this and
found a ~120 mm intrinsic noise floor even with perfect anchor sync —
caused by hyperbolic GDOP being ~3× worse than spherical, plus all
TDoA observations sharing the reference anchor's timestamp noise.

First fix attempt was "TWR at 150 Hz" — but `docs/airtime-budget.md`
showed that breaches ETSI's 5% per-device TX duty cycle. Real fix:
**broadcast DS-TWR at ~100 Hz**. One ball poll, 8 staggered anchor
responses, one ball final per cycle. Ball duty cycle 4%, per-anchor
2%. ETSI-compliant, ~85 samples per 0.85 s flight.

Sims 03, 05, 05b ran at 500 Hz with TWR-equivalent independent ranges.
The scaling-from-500 Hz estimates were superseded first by
`sim_realistic.py` (batch-fit baseline) and then by `sim_ekf.py`
(EKF + RTS smoother — the current production architecture):

| Stage | Headline | Source |
|---|---|---|
| Clean-LOS fit | ~10 mm | sim 03 @ 500 Hz (scales to ~17–22 mm @ 100 Hz) |
| Batch fit (deprecated) mean / p95 | 41 / 78 mm | sim_realistic n=30 @ 100 Hz |
| **EKF + RTS, realistic occlusion mean** | **47 mm** | sim_ekf n=30 @ 100 Hz |
| **EKF + RTS, realistic occlusion median** | **48 mm** | sim_ekf n=30 @ 100 Hz |
| **EKF + RTS, realistic occlusion p95** | **61 mm** | sim_ekf n=30 @ 100 Hz |
| **EKF + RTS y-axis (lateral)** | **8.7 mm** | sim_ekf n=30 @ 100 Hz |
| Old blob-batter occlusion | 74 mm mean / 92 mm p95 | sim_realistic n=30 @ 100 Hz |

**The EKF+RTS smoother is the production pipeline** (May 2026). It
beats the batch-fit baseline on p95 (61 vs 78 mm) and lateral
(8.7 mm sub-cm) — the metrics that matter for the user-visible LBW
verdict and tail behaviour. Mean is 6 mm worse than batch fit
(47 vs 41) but this is the trade-off for the much tighter tail.

Architectural bonus: the forward-only pass works in real time for
live broadcast overlay (a capability batch fit fundamentally
cannot provide). The RTS backward pass runs after the delivery
completes for DRS replay. Same code, two modes.

These are the headline operational targets. All well inside DRS LBW
range (stumps 228 × 711 mm).

**Why "more realistic" came out better, not worse:** the older
sim 05b modelled the batter as a single 0.35 m radius cylinder. A
real 14-bone skeleton has torso ~0.15 m, limbs ~0.05-0.08 m, bat
~0.04 m — net blockage is *less* even though there are more
occluders. Result: 26.2% range drop rate vs the old 42.7%, and a
~45% improvement in mean fit RMS.

**Implication for documentation and decisions:**
- `CLAUDE.md` decision 4 was rewritten on 2026-05-12 to specify TWR
- `docs/spec-v0.2.md` architecture section updated to match
- Sim 07's TDoA characterisation is kept as documentation of the
  rejected option (and as the spec for any fallback when TWR airtime
  cannot be met — e.g., very high beacon-rate experiments)
- Sim 07 status: only the "perfect sync" baseline scenario was
  validated end-to-end (~120 mm intrinsic noise floor — sufficient to
  drive the pivot). Drift scenarios had over-specified random-walk
  PSDs that produced gigametre errors. PSDs were lowered to realistic
  Allan-dev values on 2026-05-12 but not yet re-run since the headline
  conclusion (don't use TDoA) was already established.

---

## Sim 01 — Position precision and GDOP

**Setup:** 8 anchors, 30 mm UWB ranging σ, raw multilateration only.

**Findings:**
- X-axis (along pitch): 11–14 mm σ everywhere
- Y-axis (across): 25–80 mm σ
- Z-axis (height): the problem — at mid-pitch low (z=0.5 m), GDOP ~8
  and σz reaches 237 mm
- 680 mm vertical baseline is insufficient when ball is between
  anchors in height

**Interpretation:** Raw geometry does not deliver the precision target.
The Z-axis problem is fundamental.

## Sim 02 — 8 vs 12 anchor

**Setup:** sim 01 plus 4 mid-stump anchors at z=0.340 m.

**Findings:**
- 12 anchors gives 1.01–1.16× improvement on raw RMS
- Essentially zero after trajectory fitting
- ~$400 extra hardware cost not justified

**Decision:** Stick with 8 anchors.

## Sim 03 — Trajectory recovery (THE HEADLINE)

**Setup:** 38 m/s fast-bowler delivery, 500 Hz sampling, 8 anchors,
30 mm ranging σ, drag + Magnus + gravity with bounce.

**Findings:**
- Raw multilateration RMS: ~125 mm 3D
- After physics fit RMS: ~16 mm 3D
- Improvement: 7–8×
- **Precision target ACHIEVED ✓**

**Why it works:** ~9 parameters describe the full flight; ~400 samples
at 500 Hz gives 40+ observations per free parameter. Noise averages out
by ~√40 ≈ 6×; physics constraints do the rest.

**Implication:** The trajectory engine is the heart of the system. Raw
position fixes look unimpressive; the fitted curve delivers the product.

## Sim 05 — Multipath and occlusion (THE PIVOT)

**Setup:** Same 38 m/s delivery, plus 6 cylindrical occluders (bowler in
follow-through, bowler-end umpire, batter, keeper, two slips). Ray
through a cylinder → 50% drop, 50% kept with +50–200 mm bias and
inflated σ=100 mm. Vanilla solver, no mitigations.

**Findings:**
- 24% of all anchor rays are blocked
- Drop rate per anchor extremely uneven: A2 57%, A7 54%, A8 50% (the
  three stump-tops with persistent occluders in their line of sight),
  vs A4 0%, A6 0% (leg-side PAIs, mostly clear)
- Even though ≥4 anchors always survive (so every sample produces a
  fix), the leaked biased ranges destroy the fit
- Fit RMS: **225 mm mean** (220–263 range over 8 deliveries)
- 22× degradation vs the clean-LOS baseline

**Implication:** The 10 mm headline does not survive contact with the
real world. The trajectory fit cannot tell good measurements from
biased-NLOS measurements, and least-squares is extremely sensitive to
outliers. Untreated, the product target is broken.

## Sim 05b — Occlusion mitigations (THE RECOVERY)

**Setup:** Same occlusion model as sim 05. Four scenarios compared:
baseline, Huber loss only, NLOS detection (85% TPR / 2% FPR) + Huber,
perfect NLOS detection + Huber. n=8 Monte Carlo per scenario.

**Findings:**

| Scenario | Mean RMS | Median | p95 |
|---|---:|---:|---:|
| Baseline (no fix) | 245 mm | 247 mm | 261 mm |
| Huber loss only | 58 mm | 55 mm | 82 mm |
| **NLOS det + Huber** | **47 mm** | **42 mm** | **70 mm** |
| Perfect det + Huber | 59 mm | 63 mm | 90 mm |

**Three counterintuitive results that the sim revealed:**

1. **Switching the solver loss from least-squares to Huber is the
   single largest win** (245 → 58 mm). One line of code in
   `solver.fit_trajectory`. No new hardware capability needed.
2. **A modest NLOS detector helps** (58 → 47 mm), but it's not
   load-bearing. The chip's CIR access is needed for "good enough"
   detection; a world-class detector is not.
3. **Perfect NLOS detection is WORSE than 85% detection** (59 vs 47
   mm) because dropping 100% of biased rays starves the fit of data.
   Letting 15% leak through while Huber suppresses them keeps the fit
   better-constrained. Don't push p_detect above ~80–90%.

**Operating point:** "85% NLOS det + Huber" — ~47 mm mean, ~70 mm p95.

## Product framing — revised

- Clean-LOS headline: ~10 mm (sim 03) — for marketing slides
- **Operational reality: ~50 mm mean / ~80 mm p95** (sim 05b)
- Stumps are 228 × 711 mm — 50 mm is ~22% of stump width
- This is DRS-grade. Not "Hawk-Eye-marketing-spec." That's still a
  real product, especially at 1/10 the BOM cost
- Hardware ask of Qorvo: CIR access (which they have via the CIA
  block), not a world-class classifier

## Datasheet validation (DWM3001C / DW3110, Product Brief Rev. C)

- Table 14: ranging σ typical 30 mm, bound ±60 mm, in LOS — our
  `RANGE_SIGMA_DEFAULT` matches exactly. Sim 03's 10 mm is real, not
  optimistic.
- Table 18: DS-TWR histograms suggest ~20 mm σ achievable with tuning.
- Block diagram: dedicated CIA (Channel Impulse Analyzer) block in
  digital RX path → CIR access is silicon-supported. NLOS detection
  is implementable, not speculative.
- Link budget ~17 dB at 25 m clean LOS. Through a human body ~ -10 dB
  → body-NLOS rays mostly die rather than bias. Justifies our 50/50
  drop/bias split.
- DW1000/DW3000 backward compatibility: existing DW3000 CIR analysis
  code will port.
- Datasheet does NOT cover: NLOS detector spec, TDoA mode accuracy,
  CIR register format. These need the User Manual and/or Qorvo apps
  engineering engagement.

## Sim 11 — Ground-reflection multipath on TWR ranging

**Setup:** Each stump-top anchor (4 of 8, z=0.68 m) sees a ground-bounce
echo of the ball's signal arriving Δd later than LOS. When
Δd < ~1 m the chip's first-path detector can't separate the two and
the timestamp gets pulled toward a centroid. PAI anchors at z=0 see
no ground reflection — only stump-top anchors affected.

Modelled with reflection coefficient swept across plausible pitch
conditions. Δd computed from anchor/ball heights and horizontal
distance. Bias proportional to refl_coef × Δd / 2 (centroid pull),
plus phase-jitter Gaussian for constructive/destructive interference.

**Findings (n=6 deliveries, sim's 500 Hz rate):**

| Condition | Fit RMS mean | p95 | vs baseline |
|---|---:|---:|---:|
| Baseline (no multipath) | 11.6 mm | 14.6 mm | 1.00× |
| **Dry pitch (refl=0.15)** | **17.4 mm** | **27.6 mm** | **1.49×** |
| Wet pitch (refl=0.30) | 40.8 mm | 56.0 mm | 3.51× |
| Worst case (refl=0.50) | 75.0 mm | 101.6 mm | 6.45× |

**Interpretation:**
- Dry pitch (test/domestic norm) adds only ~6 mm of fit RMS error.
  Huber loss suppresses the worst multipath outliers; the four
  affected anchors (out of 8) leave plenty of clean rays for the fit.
- Wet pitch (rain, dew, freshly watered) is a real cost — 3.5× the
  baseline. Combining with sim 05b's occlusion: √(47² + 30²) ≈ 56 mm
  at sim rate, ~75 mm at deployable 100 Hz.
- Worst case is only physically realistic for standing water on the
  pitch — unusual in match play.

**Combined operational estimate:**

| Condition | At 500 Hz (sim) | At 100 Hz (deployable) |
|---|---:|---:|
| Clean LOS, no multipath | 10 mm | 22 mm |
| Occlusion only (sim 05b) | 47 mm | 65 mm |
| Occlusion + dry multipath | ~50 mm | ~70 mm |
| Occlusion + wet multipath | ~56 mm | ~80 mm |

**The realistic operational headline holds at ~60–80 mm under
realistic conditions, comfortably DRS-grade.**

## Sim 06 — IMU fusion (complementary filter rejected)

**Setup:** Body-frame IMU at 1 kHz with realistic chip noise specs
(SIGMA_G = 0.005 rad/s, SIGMA_A = 0.05 m/s²) and perfect initial
attitude. Strapdown integration with complementary-filter UWB blending
at alpha=0.5. UWB at the operational 100 Hz rate.

**Findings (partial — sim killed after clean-LOS scenarios):**

| Scenario | Fit RMS mean |
|---|---:|
| UWB only, clean LOS | **19.5 mm** |
| UWB only, occlusion | **72.2 mm** |
| **UWB + IMU, clean LOS** | **47–110 mm (worse than UWB-only)** |

**Conclusion: complementary filter is the wrong architecture for this
problem.** Even in clean LOS with perfect initial attitude, the IMU
integration drift dominates and the alpha=0.5 blend doesn't snap back
to UWB hard enough. The fused trajectory is strictly worse than
UWB-only.

**Why the complementary filter fails here:**
- At 100 Hz UWB with no anchor dropouts (sim 05 showed dropouts are
  rare), there are no UWB gaps for IMU to bridge.
- The IMU's contribution is only meaningful if it provides independent
  constraints on the fit — which a complementary filter cannot do
  (it produces a position estimate, not residuals).
- Real IMU benefit requires **tightly-coupled fusion** — joint
  optimisation of UWB range residuals + IMU dynamic residuals in
  the trajectory fit. That's significant engineering work and
  belongs in sim 06b / v2 product.

**Recommendation for v1 BOM:**
- **Drop the precision-tracking IMU.** Saves $5-15 + board space +
  firmware complexity. The 60-70 mm operational target is achievable
  with TWR + Huber + NLOS detection alone.
- **Keep a high-g accelerometer** (e.g., ADXL372, ~$6) purely for
  bat-impact detection — useful binary signal for catch/edge
  analytics, doesn't need fusion.

**v2 path:** if tightly-coupled fusion is built later, expect ~20-30%
improvement on the occluded number (60-70 mm → 45-55 mm). Plan
for it but don't gate v1 on it.

## Architecture decisions confirmed

1. 8 anchors is sufficient — don't pursue 12-anchor upgrade
2. Physics fit is mandatory, not optional
3. Fit must be physics-constrained (naive spline gave 1.1×; physics
   model gives 7–8×)
4. Product is fundamentally retrospective; live use needs sliding-window

## Open questions (in priority order)

1. **Real-time precision** (sim 04): does it survive past-only data?
2. **Occlusion robustness** (sim 05): bowler/keeper/slips blocking 1–3
   of 8 anchors
3. **IMU benefit** (sim 06): essential or nice-to-have?
4. **Sync engine** (sim 07): sub-ns wireless anchor sync achievable?

## Unvalidated assumptions

- Clean LOS UWB ranging (sim 05)
- Perfect anchor-to-anchor sync (sim 07)
- Batch fitting only (sim 04)
- Anchors at exactly known positions (sim 08)
- Single delivery type (sim 12)
- 25 m max range, omnidirectional antenna (sim 11)
- Standard atmosphere (sim 13)
