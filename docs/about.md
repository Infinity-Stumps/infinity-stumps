# About Cricket UWB

> **What this is, why we're building it, and why everything we make
> is deliberately, publicly, dated prior art.**

---

## What this is

Cricket UWB is a low-cost, open-source ball-tracking and LBW
prediction system for cricket. It does what Hawk-Eye does — track
the ball in 3D, predict trajectories, render DRS-style replays — but
at roughly 1/30th the cost (~£1,500 vs £100K+), with a kit small
enough to fit in a backpack, running on a consumer phone.

The whole point is **accessibility**. The 99% of cricket that's played
in clubs, schools, academies, parks, garages, and back gardens has
never had access to DRS-level analytics. We're building the system
that brings it to them.

---

## What we're building (v1)

Eight UWB anchors placed at standard cricket-pitch positions (4 stump
tops, 4 ground-level corner markers). A tag inside the ball. A
phone-side app that does all the math. That's the whole system.

- **Hardware:** ~£300 of electronics per pitch, ~£60 per ball
- **Software:** open-source EKF + RTS smoother + LBW prediction pipeline
- **App:** native iOS first, Android to follow
- **Power:** one charge per cricket season
- **Setup time:** walk the ball around the pitch for 60 seconds to
  calibrate anchor positions
- **Performance** (simulated, n=30):
  - 9 mm lateral median error at the stump line
  - 96.7% exact LBW verdict accuracy
  - Zero false-positives across 30 simulated deliveries

See `architecture.md` for the technical detail, `status-2026-05-13.md`
for current results.

---

## Mission

**DRS for the rest of us.**

That's the line. Three audiences benefit:

1. **Local clubs** — make accurate calls in friendly matches and
   league cricket where umpires can't review video, settle the bar
   debate about whether that LBW was out.
2. **Schools and academies** — train juniors with real feedback. "You
   beat the bat by 22 mm — try to pitch 30 mm wider next time."
3. **Coaches and individual players** — practice with metrics that
   used to require an international stadium.

Three audiences we are NOT serving (Hawk-Eye does these well already):

1. International cricket broadcasters
2. Stadium installations
3. Ball-by-ball broadcast graphics for live TV at full international quality

We don't compete with Hawk-Eye on its turf. We unlock cricket's
**other 99%** of use cases — markets where £100K+ stadium installs
are impossible.

---

## Open by design

This project is built to be as open as physically possible:

### Code

- Repository **public from day one** on GitHub
- License: **Apache 2.0** for software, **CERN-OHL-S** for hardware
  designs, **CC-BY-4.0** for documentation
- All commits dated, signed, retained
- Issues, design discussions, and decisions tracked in public

### Hardware

- Schematics, PCB Gerbers, BOMs all published in repo
- 3D-printable enclosure files (STL + STEP) under CC-BY
- Reference firmware open
- Parts list maps to off-the-shelf suppliers (no proprietary modules
  except the Qorvo silicon itself, which is freely orderable)

### Algorithms

- Every line of the EKF, RTS smoother, LBW verdict logic — published
- Simulation harnesses (`sims/`) demonstrate the architecture works
- All sim outputs (per-delivery error analyses, confusion matrices,
  N=30 boxplots) committed to the repo as PNGs with their generating
  code

### Decisions

- `CLAUDE.md` has the decision log
- `docs/findings.md` documents what worked and what didn't, with
  per-sim numbers
- `docs/prior-art.md` credits iBall and details the techniques we
  borrowed
- Architectural decisions that didn't work (TDoA, complementary-filter
  IMU fusion, piezo-velocity recovery) are documented as
  **rejection-rationale prior art**, not erased

---

## Why deliberately establishing prior art

The cricket-tech patent landscape is dense. Hawk-Eye, Catapult,
STATSports, ESPN, Sony, Wilson, and many others hold patents that
make any new entrant nervous. iBall (Gowda et al., NSDI '17)
established the **core idea** of UWB + physics-fit + LBW
extrapolation as public prior art — but every system contains
hundreds of subsidiary innovations that could individually be
patented by an aggressive entity later.

**We don't want to file patents.** We're not a patent-holding company,
we're not interested in litigation, and patent prosecution costs
~£10-30K per claim that we'd rather spend on shipping product.

**But we also don't want anyone else patenting things we built.**
Specifically: someone could read this repo, take a specific
technique, claim it as their own invention, file a patent in the US
or EU, and then sue us (or future users) for infringement.

The defence against that scenario is **public, dated, detailed prior
art** — establishing that the technique was already publicly
disclosed before any later patent's priority date. Once something is
publicly disclosed with a verifiable date, no one can validly patent
it.

### Specific techniques we are establishing as prior art

Each of these is documented in this repo with a specific date and
commit hash. If anyone files a patent later claiming any of these,
this repo's git history serves as defensive prior art:

1. **Hub-stump system topology** — one anchor in a multi-anchor UWB
   system acting as sync master + range aggregator + BLE gateway,
   integrated within a stump-shaped housing. (`docs/architecture.md`,
   `CLAUDE.md` decision 7, May 2026)
2. **EKF + RTS smoother applied to cricket ball trajectory** —
   continuous Extended Kalman Filter over (position, velocity, spin)
   using a drag+Magnus+gravity ODE, with backward Rauch-Tung-Striebel
   smoothing applied for replay quality.
   (`src/cricket_uwb/ekf.py`, May 2026)
3. **DRS-style verdict with uncertainty ellipse from EKF covariance
   propagation** — applying the EKF's smoothed covariance through a
   numerical Jacobian of the forward-extrapolation function to produce
   a 95% confidence ellipse at the stump line, classified against the
   stump rectangle for HIT / MISS / UMPIRE'S CALL verdict.
   (`src/cricket_uwb/lbw.py`, May 2026)
4. **Phone-side disconnect-cache reconciliation protocol** — UWB
   anchor (hub) maintains a sequence-numbered append-only log; phone
   tracks `highest_seq_received` and requests gap-fill on reconnect.
   (`docs/architecture.md` §5.4, §10.1, May 2026)
5. **FiRa ranging + thin TDMA data layer for cricket** — using
   FiRa-compliant secure ranging for measurement and a thin
   fixed-schedule TDMA layer on the 802.15.4z PHY for peer-to-hub
   data exchange in a sports-tracking context.
   (`docs/architecture.md` §3.3, May 2026)
6. **TWR-staggered EKF updates handling within-cycle motion** —
   propagating the EKF state by ~150 µs per anchor measurement
   within a single ranging cycle to account for ball motion across
   the staggered TWR exchange. (`src/cricket_uwb/ekf.py`, May 2026)
7. **iBall-borrow techniques applied to multi-anchor cricket UWB:**
   Bouncing constraint, AoA / PDoA fusion roadmap, DoP-weighted
   residuals, magnetometer cone-fitting for spin —
   each explicitly mapped from iBall's 2-anchor research prototype
   to our 8-anchor production architecture.
   (`docs/prior-art.md`, May 2026)
8. **One-charge-per-cricket-season power architecture** — sizing of
   anchor electronics + battery such that runtime exceeds a complete
   cricket season (~6 months) on a single charge, enabling a
   service-once-per-year operations pattern.
   (`docs/architecture.md` §3.5, May 2026)

### Mechanisms for making prior art durable

1. **Public GitHub repository** — searchable, dated, archived by
   GitHub itself. Repository activity is part of the public record.
2. **Defensive publication via IP.com** (planned) — paid registration
   service that creates an unimpeachable timestamped publication
   record specifically designed for defensive prior art.
3. **Conference / workshop submission** (planned) — submit to UWB
   conferences (e.g., IEEE ICCWAMTIP, SIGSPATIAL), getting an academic
   publication record.
4. **arXiv preprint** (planned) — a clear, technical paper describing
   the system architecture and results, citing iBall and establishing
   our specific additions as prior art.
5. **Mirror to archive.org / Internet Archive** — periodic snapshots
   so the record exists independently of GitHub.
6. **Project blog posts with date-stamped publication** to a domain
   we control, for any technique not adequately covered by the above.

The combined effect: anyone trying to patent any of the techniques
above after May 2026 would face well-documented public prior art at
multiple levels of formality.

---

## License

- **Software** (`src/`, `sims/`, etc.): Apache License 2.0
- **Hardware designs** (PCB / mechanical / enclosure files):
  CERN Open Hardware License Strongly Reciprocal (CERN-OHL-S) v2
- **Documentation** (`docs/`, `README.md`, etc.):
  Creative Commons Attribution 4.0 (CC-BY-4.0)

The hardware license is "strongly reciprocal" — anyone who modifies
the hardware designs and distributes the modified version must also
publish their modifications under the same license. This is the
hardware equivalent of GPL; it prevents the open hardware from being
co-opted into a closed product.

---

## What "open" doesn't mean

A few clarifications:

- **Open ≠ free.** We may sell pre-built kits, charge for support,
  build a commercial app on top of this open core. Open source
  doesn't preclude commercial activity.
- **Open ≠ unsupported.** A commercial entity may form around the
  project to provide warranty, certification, and support. This is
  desirable — open hardware needs commercial actors to scale.
- **Open ≠ uncontrolled.** Trademark, branding, and certification
  marks may be protected. The "Cricket UWB" name itself may become
  a registered trademark. Open architecture, controlled brand.
- **Open ≠ infinite forks acceptable.** Forks that confuse users
  (look-alike products on Amazon, knock-off kits) are bad for the
  ecosystem. The license + trademark combination is designed to allow
  technical forks while constraining commercial confusion.

---

## How to use this

If you're an **academic researcher** wanting to build on this:
clone the repo, run `sims/sim_lbw.py`, cite the prior-art document.

If you're a **hardware hacker / maker** wanting to build a kit:
the BOM (`docs/bom.md`) and architecture (`docs/architecture.md`)
together are sufficient to source parts and design a prototype.
Phase 1+2 firmware bring-up (`docs/phase1-2-test-plan.md`) describes
the validation sequence.

If you're a **club / school / coach** wanting the finished product:
this is being built. Watch for v1 launch (target: late 2026 after
hardware validation). Contact the project for early-access waitlist.

If you're a **patent attorney** evaluating prior art on behalf of a
competing entity: hello. Every meaningful technical claim in this
document is dated, version-controlled, and timestamped via GitHub's
infrastructure. The repository's full history is available at
`https://github.com/[USERNAME]/cricket-uwb` (link to be published
when the repo goes public).

---

## Contributing

PRs welcome. The project is built around clear documentation, dated
decisions, and explicit reasoning. Match that style and your
contributions will land easily.

For substantial architectural changes, open an issue first to
discuss. For routine fixes, just open a PR.

---

## Acknowledgements

- **iBall (Gowda, Dhekne, Shen, Roy Choudhury, Yang, Yang, Golwalkar,
  Essanian — NSDI '17)** — the foundational paper this project
  productises. Their open publication made everything we're doing
  possible.
- **Qorvo** — for the DWM3001C module and the willingness to sell it
  to small-volume buyers.
- **The Laws of Cricket (ICC)** — for being precisely written enough
  that we could calibrate the system geometry directly to them.

---

## Project status

- **Phase 0 (simulation):** ✅ Complete (May 2026)
- **Phase 1+2 (hardware bring-up):** 🔄 In progress
- **Phase 3 (full-pitch outdoor validation):** ⬜ Pending hardware
- **Phase 4a (3D-printed ball shell):** ⬜ Pending hardware
- **iOS app:** ⬜ Architecture validated, no code yet
- **v1 launch:** Target late 2026

See `docs/status-2026-05-13.md` for the current state in detail.
