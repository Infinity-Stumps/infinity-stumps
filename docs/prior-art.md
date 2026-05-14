# Prior Art — iBall (Gowda et al., NSDI '17)

**Paper:** "Bringing IoT to Sports Analytics"
**Authors:** Mahanth Gowda, Ashutosh Dhekne, Sheng Shen, Romit Roy
Choudhury (UIUC) + Xue Yang, Lei Yang, Suresh Golwalkar, Alexander
Essanian (Intel)
**Venue:** 14th USENIX Symposium on Networked Systems Design and
Implementation (NSDI '17), Boston, March 2017
**URL:** https://www.usenix.org/conference/nsdi17/technical-sessions/gowda

**This paper is the foundational prior art for our system.** It
establishes the core idea (UWB ranging + physics-constrained
trajectory fit + LBW extrapolation for a cricket ball) as published
public knowledge. We are *not* patenting that combination. We *are*
shipping a productised, outdoor-validated, consumer-priced version
of what they prototyped.

---

## What iBall built

**Hardware**
- Intel Curie board (IMU + UWB radio) embedded in a hollowed-out
  cricket ball, halves glued shut, USB pigtail for charging
- Decawave UWB radio (gen 1), 6.5 GHz, 802.15.4-compliant
- Only **2 anchors** placed at the wickets (they believed additional
  anchors on the field of play were infeasible due to player
  interference)
- Anchors used 4-antenna MIMO for Angle-of-Arrival (AoA)
- Magnetometer for spin tracking (BMM150)
- IMU at 70 Hz, UWB ranging + AoA at 150 Hz

**Algorithm**
1. UWB ToF → range from 2 anchors → "tube" of possible positions
   (1-D underdetermined with only 2 anchors)
2. Add physics: drag + Magnus + gravity ODE as 6-parameter motion
   model (x₀, y₀, z₀, vₓ, v_y, v_z)
3. Add **bouncing constraint**: z = 0 at bounce (detected from
   accelerometer)
4. Add **AoA constraint** from MIMO anchor
5. **DoP-weighted residuals** (1/√DoP) — downweight ranges when the
   geometry collapses (mid-flight when anchor lines become collinear)
6. Non-linear gradient descent over 6 params; resolve AoA integer
   ambiguity by checking against ToF
7. **Magnetometer-based spin**: gyros saturate beyond ~6 rps but
   cricket spin is up to 25 rps. Trick: in free-fall the magnetometer
   sees a cone-shaped trace around the rotation axis. Fit a cone to
   3 consecutive measurements to get axis + rate.

**Results (indoor, ViCon ground truth)**
- Median 3D location error: **8 cm**
- Per-axis: 4.5 cm X, 3.4 cm Y, 2.4 cm Z (Z is best because of
  bouncing constraint)
- LBW trajectory extrapolation: **22 cm 3D / 9.9 cm X-axis** (ICC
  tolerance is 10 cm, so feasible "barely")
- Speed estimation: 0.4 m/s median error
- Spin orientation: 11.2° median cumulative angle error
- Cumulative angle: 1% mean, 3.9% max
- Player tracking (clip-on UWB): 1.2 m median, up to 80 m from
  anchors

**Explicit limitations they acknowledge**
- **Indoor only** — outdoor multipath/aerodynamics never validated
- Max 45 mph / 20 m/s ball speed (pro is 90 mph / 40 m/s)
- Max 12 rps spin (pro is up to 25 rps)
- 75-90 min battery
- Custom hollowed cricket ball, not a professionally manufactured one
- DoP issues in middle of flight
- Indoor multipath may have helped AoA accuracy artificially

---

## What we do differently

| Dimension | iBall 2017 | Infinity Stumps 2026 | Reason |
|---|---|---|---|
| Anchors | 2 | **8** | DoP collapse with 2 anchors; sim 02 says 8 is the sweet spot |
| UWB silicon | Decawave gen-1 | Qorvo DW3110 (DWM3001C module) | ~5× better raw ranging σ (30 mm vs 150 mm), FiRa / 802.15.4z, CIR access for NLOS detection |
| Topology | Anchors → backend PC | Hub stump → iPhone | No edge compute; consumer product |
| Sync | n/a (TWR sync-free) | Wireless inter-anchor TWR sync | Multi-anchor sync was their open problem too |
| Sample rate | 150 Hz (incl. AoA) | 100 Hz | ETSI duty-cycle limit (see `airtime-budget.md`) |
| Occlusion handling | Acknowledged | Huber loss + chip NLOS detection + realistic skeleton sim | Their indoor setup masked the occlusion problem |
| Outdoor validation | Punted to future work | Operational target (Phase 1+2) | The point of the project |
| Spin tracking | Magnetometer + cone-fitting | **Not yet** — ADXL372 is impact-only | v2 candidate, see below |
| LBW prediction | Claimed feasible at 22 cm/9.9 cm | Target: substantially under | Their explicit benchmark |
| **Location error** | **8 cm median (indoor)** | **3.5 cm median (sim, outdoor occlusion)** | sim_realistic n=30 |

---

## What we should borrow (and one thing we should add)

Techniques iBall validated that we should fold into our pipeline, plus
one new piece of sensing they didn't have:

### 1. Bouncing constraint (HIGH priority)

When the ball bounces, z = 0 at that timestamp. This is a strong
constraint — one point on the trajectory is *pinned* to within ranging
noise. iBall's Z-axis error was the best of all axes (2.4 cm) largely
because of this.

**For us:**
- Detect bounce from ADXL372 impact spike (we already log this)
- Add a soft constraint to `fit_trajectory`: residual `(z(t_bounce) - 0)² / σ_z²`
- Should improve Z-axis error specifically and tighten LBW predictions
- Effort: ~1 day in `simulation/src/infinity_stumps/solver.py`

### 2. AoA / PDoA fusion (HIGH priority)

iBall's AoA from MIMO anchors gave them a second observable per
anchor, letting them recover from DoP collapse. The Qorvo DW3110
chip supports **PDoA (Phase-Difference of Arrival)** when configured
with paired antennas. Same mathematical primitive.

**For us:**
- Add a 2-antenna config to the hub stump (or all stump anchors)
- Each ranging exchange also returns PDoA → 1 angle measurement per
  anchor
- Add AoA residual to `fit_trajectory`:
  `(cos(θ_measured) - cos(θ_predicted))² / σ_aoa²`
- iBall used 18 cm antenna separation to get unambiguous AoA. Our
  stump cross-section is ~36 mm wide, so we'd need a separate antenna
  bar above the stump (a few cm of horizontal aluminium)
- Effort: hardware design + ~1-2 days code
- Expected improvement: substantial reduction in mid-flight DoP error,
  better LBW extrapolation

### 3. DoP-weighted residuals (MEDIUM priority)

iBall weighted each range residual by 1/√DoP. We use Huber loss,
which is a different mechanism (suppresses outliers). They're
complementary — Huber for NLOS rejection, DoP weighting for geometric
quality.

**For us:**
- Compute DoP per timestep (already have GDOP code in `geometry.py`)
- Weight `fit_trajectory` residuals by 1/√DoP
- Effort: ~half day
- Expected improvement: modest mid-flight tightening; worth doing

### 4. High-g piezoelectric impact sensor (BEYOND iBall — HIGH priority)

This isn't borrowed from iBall — it's a step beyond them. iBall used a
generic IMU which saturated on real cricket impacts, so they had no
information from the bounce force itself.

**The mechanism:** with a non-saturating impact sensor, integrating its
spike over the ~0.5 ms contact yields the velocity change Δv at the
bounce. Coefficient-of-restitution physics then gives `v_in_vertical =
-Δv_vertical / (1 + COR_vertical)` — the ball's incoming vertical
velocity at the bounce moment. Combined with the bounce timestamp + the
known gravity vector + the bounce (x, y) from multilat, the **entire
z-trajectory becomes physics-determined**, bypassing the UWB anchors'
weak vertical baseline (GDOP_z ≈ 8 at mid-pitch).

**Sensor candidates:**
- Piezoelectric: PCB Piezotronics 350M77 (±50,000g), Meggitt Endevco
  7270A series (±60,000g)
- MEMS high-g: Silicon Designs / Endevco 7298A (±60,000g)
- PVDF film: wrapped inside ball shell, near-zero added mass, charge-mode

**Implementation:** dual-accelerometer ball-side: ADXL372 (±200g) for
spike *timing* and impact classification (pad vs bat vs bounce);
piezoelectric (±10-50 kg) for the actual *impulse measurement* that
yields v_in.

**Physics caveats — what the simple model gets wrong:**

The textbook formula `v_in = -Δv / (1 + COR_v)` treats COR_v as a known
constant and assumes the impulse is purely vertical. In real cricket
neither is true:

1. **COR varies session-to-session and within a session.** Pitch
   moisture (damp pitch → ~0.4-0.5), ball wear (new → ~0.6, worn → ~0.5),
   impact velocity (Hertzian softening at high v), temperature.
   Mitigation: **per-session COR calibration.** First 5-10 deliveries
   collect (Δv_piezo, v_in_uwb-bracketing); solve for COR_v that
   minimises (predicted - observed). Use that for the rest of the
   session. One-parameter fit, easy.
2. **Impulse is a vector, not a scalar.** A spinning ball with pitch
   friction has tangential impulse component. Magnitude-only piezo
   over-reads |Δv_z| by ~5-15%. Solutions:
   - **3-axis impact sensor (recommended)** — three single-axis piezos
     at perpendicular orientations, or a tri-axial MEMS high-g sensor.
     Direct vector impulse, no decomposition assumed. ~£30 ball-side.
   - Alternative: IMU orientation + assumption of pure normal impulse —
     free but breaks down precisely when spin matters most.
3. **Spin/slip at contact** transfers horizontal impulse not captured
   by the simple formula. Model mismatch grows with spin rate;
   typically 0.02 × spin_rps m/s additional noise on v_in.

**Realistic noise model on the recovered v_in:**

```
σ_v_in² = σ_impulse_integration² + σ_COR² + σ_spin_mismatch²

σ_impulse_integration  ≈ 5% of |Δv|          (sensor accuracy)
σ_COR_propagated       ≈ |v_z| / (1+COR) × σ_COR  (≈5% for σ_COR=0.05)
σ_spin_mismatch        ≈ 0.02 × spin_rps     (model gap)

⇒ per-delivery σ_v ≈ 0.6 m/s (no spin) to 0.85 m/s (max cricket spin)
```

The sim now uses this per-delivery noise model.

**Expected impact:** Z fit error drops from current ~60 mm median to
single-digit mm on low-spin deliveries; modest improvement on high-spin
deliveries where the simple impulse-CoR model has the largest mismatch.
Lateral and 3D LBW errors tighten correspondingly. Cost: +~£30 ball-side
(3-axis piezo), modest PCB area, no power needed (piezo is
self-generating).

This is the **single biggest precision lever** we have on top of iBall.

---

### 5. Magnetometer-based spin tracking (v2)

If we ever want spin analytics (revolutions, axis, "wobble"), iBall's
magnetometer + cone-fitting trick is the right approach because gyros
saturate at cricket spin rates. They achieved 11° axis error and
1% cumulative angle error.

**For us:**
- Adds magnetometer to ball-side BOM (BMM150 or modern equivalent)
- Implements the cone-fitting algorithm
- v2 territory — don't do until v1 location tracking is in users' hands

---

## Patent implications

The novel-system patent angle is **dead**. The combination "UWB +
physics-constrained trajectory model + cricket ball + LBW
extrapolation" is published prior art as of March 2017.

**What might still be defensible** (much narrower):
- The **hub-stump system topology** (sync master + range aggregator +
  BLE gateway integrated in stump). iBall's architecture was generic
  anchor → backend.
- Specific implementation details of phone-side compute (e.g., a
  particular CoreML model architecture for NLOS detection from CIR).
- A specific calibration procedure for in-field anchor positions.

These are narrow continuation-style claims, not core IP. **Better to
ship and brand than to file.** The competitive moat is execution speed
+ product quality + outdoor validation + iPhone-native experience, not
a patent.

---

## What this means for our roadmap

**Phase 0 (sim) — mostly done:**
- ✅ Trajectory fit + Huber + NLOS detection
- ✅ Realistic occlusion model (better than iBall — they didn't model it)
- ⬜ **Bouncing constraint in fit_trajectory** (iBall-borrow #1)
- ⬜ **DoP-weighted residuals** (iBall-borrow #3)
- ⬜ **LBW module** with iBall benchmark to beat

**Phase 1+2 (hardware):** unchanged — characterise the DW3110's
real-world σ and NLOS bias distribution.

**Phase 3 (full geometry):** outdoor validation — this is where we
beat iBall's hard limitation (indoor-only).

**Phase 4a (printed ball shell):** establishes engineering feasibility.

**Phase 5 (PDoA hardware):** add AoA to anchors (iBall-borrow #2) once
v1 is in users' hands and we want to push precision further.

**v2 (spin tracking):** magnetometer + cone-fitting (iBall-borrow #4)
when product demand justifies it.
