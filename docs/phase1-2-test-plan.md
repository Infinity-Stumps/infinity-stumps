# Phase 1 + 2 Test Plan — Per-link σ + NLOS Characterisation

This is the first empirical validation block. It answers the two
foundation questions every other sim conclusion depends on:

1. **Phase 1:** Is the per-anchor ranging σ really ~30 mm outdoors?
2. **Phase 2:** Is the chip-level NLOS detection really ~85% TPR, and
   what does the real NLOS bias distribution look like?

All tests use the **Qorvo DWM3001CDK** (Digikey part `2312-DWM3001CDK-ND`,
~£26 inc-VAT each, currently 668 in stock UK).

---

## Equipment

| Item | Qty | Cost | Notes |
|---|---|---|---|
| DWM3001CDK | 3 | £78.69 | 2 active + 1 spare |
| USB-C cable | 3 | — | For power + data |
| Mini tripod or camera mount | 2 | ~£20 | Hold anchor + tag steady |
| Laser distance meter (e.g., Bosch GLM 50-23 G) | 1 | ~£60 | Ground truth to ±2 mm |
| Outdoor space, ~30 m clear sight line | — | — | Park or cricket club outfield |
| Laptop with USB | 1 | — | Data logging |
| **Initial spend** | | **~£160** | (£100 if rangefinder borrowed) |

Optional but useful:
- Volunteer for Phase 2 occlusion tests
- Bench scale to weigh things (if doing tag-in-shell early)
- Logitech webcam or phone on tripod for visual sync of occlusion events

---

## Phase 1.0 — Firmware Bring-Up (PREREQUISITE)

Before any data collection, the boards need firmware that:
- Performs DS-TWR between two boards
- Reads diagnostic registers after each exchange: `IP_DIAG_*`, `STS_DIAG_*`,
  `RX_POWER`, `FP_POWER`, the `RX_TIME` quality bits
- Logs everything over UART/USB serial as CSV
- Records each range with its diagnostic context

**Starting point:** Qorvo's `ex_06a_ss_twr_initiator` and `ex_06b_ss_twr_responder`
example pairs in the DW3000 SDK. Modify to:
1. Switch to DS-TWR (`ex_05a` / `ex_05b`) for clock-cancellation
2. Add diagnostic register reads after each exchange (see User Manual sec 4.7)
3. Print CSV to USB CDC

**Output format per ranging exchange:**

```
timestamp_ms, range_mm, rx_power_dbm, fp_power_dbm,
  fp_to_total_ratio, ip_diag_status, sts_quality_flag, anchor_id, tag_id
```

**Effort:** 1 weekend if comfortable with nRF Connect SDK; 2-3 weekends if
learning it from scratch. The Qorvo examples compile out-of-the-box,
the work is just adding the diagnostic readouts.

**Acceptance:** two boards in line-of-sight at 5 m report ranges ~5000 mm
with σ < 50 mm in a 1000-sample log, with all diagnostic fields populated.

---

## Phase 1.1 — Per-link σ vs Distance

**Question:** Does the chip deliver datasheet-rated 30 mm σ at the
distances we'll use in cricket geometry?

**Setup:**
- Anchor on tripod at 1 m height
- Tag on tripod at 1 m height
- Measure horizontal distance with laser rangefinder to ±5 mm
- Clean line of sight, no people walking by

**Procedure:**
1. Set distance to 1 m, log 1000 ranges (~30 sec at 30 Hz update)
2. Repeat at 5 m, 10 m, 15 m, 20 m, 25 m
3. Repeat the whole sweep 3× over a day (morning / midday / evening) to
   catch temperature effects
4. At each distance, log the diagnostic registers too (we'll use these
   in Phase 2)

**Analysis:**
- σ vs distance: should be roughly flat ~30 mm, perhaps creeping up at 20+ m
- Mean bias vs distance: should be roughly constant (antenna delay
  calibrated out)
- Outlier rate: % of ranges > 3σ from mean

**Pass criteria:**
- σ ≤ 35 mm across all distances tested
- Mean bias < ±20 mm at any distance
- < 1% outliers (anything more suggests preamble detection issues)

**Failure modes:**
- σ > 50 mm everywhere → calibration problem in firmware, dig in
- σ ramps up sharply at 15-20 m → link budget marginal, check antenna or power settings
- Mean bias drifts > 100 mm between distances → antenna delay needs proper calibration
- Different from morning to evening → temperature effect, expected but
  document magnitude

**Estimated time:** 1 full afternoon (4 hours) including setup.

---

## Phase 1.2 — Antenna Delay Calibration

**Question:** What's the systematic per-board antenna delay, and once
calibrated, what σ do we get?

This is genuinely production-relevant. The chip ships uncalibrated;
deployment needs each anchor calibrated individually.

**Setup:**
- Same as 1.1 but with 3 boards in a triangle, all known distances
- Each pair gets ranged

**Procedure:**
1. Place 3 boards at known positions forming a triangle (e.g., 5, 7, 9 m sides)
2. Log 500 ranges per pair (3 pairs)
3. Compute systematic per-pair bias: `bias_AB = mean(measured) - true`
4. Solve the 3-equation system to get per-board antenna delays
5. Apply calibration, re-measure, confirm bias < 10 mm

**Pass criteria:** Post-calibration mean bias on each pair < 10 mm.

**Estimated time:** 2 hours.

---

## Phase 2.1 — NLOS Bias Distribution (human in line)

**Question:** When a human stands in the anchor-tag line, what's the
distribution of (a) drop rate, (b) range bias, (c) chip diagnostic
signature?

**Setup:**
- Anchor at one end, tag at other end, 10 m apart, both at 1.5 m height
  (representative ball-flight zone)
- Volunteer positioned to stand in or near the line

**Procedure:**

For each of these positions, log 500 ranges + full diagnostic registers:

1. **Clean LOS** — volunteer standing 5 m to the side of the line
2. **Direct torso block** — volunteer standing in the line, 5 m from anchor,
   facing perpendicular (max torso block)
3. **Partial occlusion** — volunteer offset 0.5 m from the line
4. **Edge occlusion** — volunteer offset 1.0 m from the line
5. **No occlusion (cross-check)** — volunteer offset 2.0 m from the line
6. **Walking through** — volunteer walks across the line at ~1 m/s (5-10
   passes, total ~500 ranges)

Optional / nice-to-have:
- Hand-label each sample with a binary "blocked / clear" tag using
  the recording or timestamps
- Repeat with different body orientations (facing along the line, vs
  perpendicular) to test orientation sensitivity

**Analysis:**

For each position:
- Mean range bias (measured − true) — should be 0 for LOS, positive for NLOS
- σ of measurements
- Drop rate (fraction returning no range / invalid status)
- Histogram of `fp_power - rx_power` ratio (this is the NLOS metric)

Plot:
- `fp_power - rx_power` vs LOS/NLOS label → shows separability
- Compute classifier ROC curve, find threshold that gives ~85% TPR and
  measure actual FPR at that threshold

**Pass criteria:**
- Direct torso block produces detectable bias (mean shift > 20 mm vs LOS)
  OR clear drop in success rate
- The `fp/rx_power` ratio separates LOS from NLOS classes — i.e., the
  ROC curve sits above the diagonal
- At a threshold giving 80% TPR, FPR < 10%

**Failure modes:**
- No detectable bias under torso block → reflection/diffraction model
  was wrong; need to rethink the NLOS hypothesis
- `fp/rx_power` doesn't separate classes → can't build a usable NLOS
  classifier from datasheet metrics, need raw CIR ML approach
- Bias is in the wrong direction (negative) → unexpected, would suggest
  early-path detector is misbehaving

**Estimated time:** 1 full evening (~2-3 hours including setup and
volunteer coordination).

---

## Phase 2.2 — Statistical NLOS Characterisation

**Question:** What does the realistic distribution of NLOS biases look
like across many occluder configurations?

**Setup:**
- Same as 2.1
- Multiple volunteers, ~5-10 people of different builds if possible

**Procedure:**
1. Volunteer walks naturally across the line of sight repeatedly while
   ranges log continuously
2. Have 2-3 volunteers walking in random patterns simultaneously
3. Log 30 minutes of data with people moving around naturally
4. Hand-label periodically using camera footage or live notes

**Analysis:**
- Aggregate distribution of biases from all NLOS-labelled samples
- Compare to the assumption from sim 05: uniform(50 mm, 200 mm) + N(0, 100 mm)
- Tail behaviour — what's the p95, p99 bias?

**Pass criteria (purely informational, no fail):**
- Distribution roughly uniform in 50-200 mm range, OR
- Distribution distinctly different (heavy tail, bimodal, etc.) → update
  sim 05 assumptions

**Estimated time:** 1 evening + a couple of evenings of analysis.

---

## Phase 2.3 — Spinning Tag Antenna Pattern (Phase 4a precursor)

**Question:** Does the tag's antenna gain pattern, when the tag rotates,
produce systematic drops in ranging from any one anchor direction?

This is technically Phase 4a but is cheap enough to include here while the
kit is set up.

**Setup:**
- Tag mounted on a cheap brushless motor (RC car / drone motor + ESC), free-spinning
- Spin rate adjustable from 0 to 1500 RPM (= 25 rev/s, peak cricket spin)
- Anchor 10 m away

**Procedure:**
1. Static baseline: 500 ranges with tag stationary
2. Slow spin: 1 Hz, 500 ranges
3. Medium spin: 10 Hz, 500 ranges
4. Cricket-fast spin: 25 Hz, 500 ranges
5. Repeat with anchor at different angles relative to tag rotation axis
   (perpendicular, parallel, 45°)

**Analysis:**
- Look for periodic structure in range time series at the spin period
- Compute drop rate per spin condition
- Check σ vs spin rate

**Pass criteria:**
- No systematic dropouts > 50 ms at any spin rate
- σ at 25 rev/s ≤ 1.5× static σ

**Failure modes:**
- Periodic drops at the spin period → antenna has a deep null; needs
  diversity antennas or different antenna design before going to Phase 4
- σ inflates dramatically with spin → Doppler / phase effects we hadn't
  modelled

**Estimated time:** 1 evening + ~£20 for motor/ESC.

---

## Data Logging Format

All tests log to CSV. Columns:

```
test_id              # which test this row belongs to
timestamp_ms         # since recording started
distance_true_mm     # ground truth (from laser meter)
range_meas_mm        # what the chip reported
rx_power_dbm
fp_power_dbm
ratio                # fp_power - rx_power (the NLOS metric)
ip_diag_status       # bitfield from IP_DIAG status word
sts_quality_flag     # STS dual-estimate flag (high = error)
sts_diag_status      # bitfield from STS_DIAG status word
label                # MANUAL: "los", "nlos-torso", "nlos-walking", etc
anchor_id            # which board was anchor
tag_id               # which board was tag
notes                # free text
```

Plus a `metadata.json` per session with weather, temperature, location,
orientation, volunteer count etc.

---

## Acceptance Summary — Phase 1+2 Outcome

After all tests complete, you can answer:

| Question | Source test | If pass → | If fail → |
|---|---|---|---|
| σ matches sim assumption (30 mm)? | 1.1 | Continue to Phase 3 | Rescale sim numbers, reconsider |
| Antenna delay calibrable to < 10 mm? | 1.2 | Production tooling is feasible | Need per-anchor cal procedure design |
| NLOS bias detectable in chip diagnostics? | 2.1 | Build classifier on these features | Need CIR-based ML classifier (more work) |
| NLOS bias distribution matches sim 05 assumption? | 2.2 | sim 05b numbers are valid | Update sim and re-estimate operational target |
| Spinning antenna survives 25 rev/s without dropouts? | 2.3 | In-ball architecture is feasible | Antenna redesign before Phase 4 |

If all five questions pass → **Phase 3 (full cricket geometry) is the next step**, and the system has cleared the major risk gates the simulations couldn't.

If 2.3 fails specifically → reconsider in-ball architecture (might need diversity antennas, or accept that anchors at certain angles will always be flaky).

---

## Total Phase 1+2 Effort Estimate

| Element | Time | Cost |
|---|---|---|
| Firmware bring-up (Phase 1.0) | 1-3 weekends | — |
| Phase 1.1 — σ vs distance | 1 afternoon | £60 if buying rangefinder |
| Phase 1.2 — antenna calibration | 2 hours | — |
| Phase 2.1 — NLOS bias single subject | 1 evening | — |
| Phase 2.2 — NLOS bias statistical | 1 evening + analysis | — |
| Phase 2.3 — spinning tag | 1 evening | ~£20 motor |
| **Total** | **3-5 weekends spread over 4-8 weeks** | **~£260** (incl. 3 boards) |

Outcome: you know whether the operational headline (~65-90 mm fit RMS
under realistic conditions) is real or a sim artefact, and whether
the chip's diagnostic registers genuinely enable NLOS detection at
the rates we assumed. This is the data that backs the patent filing.
