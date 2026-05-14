"""Sim 05 — Multipath and occlusion. People on the pitch block UWB rays.

Real cricket has a bowler completing follow-through, an umpire behind
the stumps, the batter, the keeper, and slips. Each is a vertical
cylindrical obstacle that can block anchor-to-ball lines.

Model:
  - 6 cylindrical occluders (radius 0.35 m, height 1.10 m or 1.85 m)
  - Bowler is dynamic: at release at x=-9 y=+0.2, follows through to
    x=-4 y=+0.6 over 0.5 s
  - For each (anchor, ball, time): check if the 3D ray passes through
    any cylinder. If blocked: 50% dropped (NaN), 50% kept with bias
    of +50…+200 mm and inflated noise (σ=100 mm)

Compare 3D RMS against clean-LOS baseline from sim 03.
"""

from __future__ import annotations

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec

from infinity_stumps import (
    ANCHORS_8,
    RANGE_SIGMA_DEFAULT,
    add_range_noise,
    fit_trajectory,
    solve_position,
)
from infinity_stumps.geometry import PITCH_HL, STUMP_HEIGHT
from infinity_stumps.physics import integrate_trajectory, make_delivery

HUMAN_R = 0.35
TALL_H = 1.85
CROUCH_H = 1.10
SIGMA_NLOS = 0.10
NLOS_BIAS = (0.05, 0.20)
DROP_PROB = 0.5


def static_occluders():
    """Static people: umpire, batter, keeper, two slips."""
    return [
        ("umpire", -10.5, -0.40, HUMAN_R, 0.0, TALL_H),
        ("batter", +10.0, -0.05, HUMAN_R, 0.0, TALL_H),
        ("keeper", +11.0, 0.00, HUMAN_R, 0.0, CROUCH_H),
        ("slip1", +11.2, -1.20, HUMAN_R, 0.0, CROUCH_H),
        ("slip2", +11.5, -1.80, HUMAN_R, 0.0, CROUCH_H),
    ]


def bowler_at(t):
    """Bowler follow-through. Returns (name, cx, cy, r, z_min, z_max)."""
    if t <= 0.5:
        s = t / 0.5
        x = -9.0 + (-4.0 - -9.0) * s
        y = 0.2 + (0.6 - 0.2) * s
    else:
        x, y = -4.0, 0.6
    return ("bowler", x, y, HUMAN_R, 0.0, TALL_H)


def cylinder_blocks(anchor, target, cyl):
    """Vertical-cylinder ray test. cyl = (name, cx, cy, r, z_min, z_max)."""
    _, cx, cy, r, z_min, z_max = cyl
    a = np.asarray(anchor, dtype=float)
    t = np.asarray(target, dtype=float)
    v = t - a
    v_xy = v[:2]
    v_sq = float(v_xy @ v_xy)
    if v_sq < 1e-12:
        if np.hypot(a[0] - cx, a[1] - cy) > r:
            return False
        z_lo, z_hi = sorted([a[2], t[2]])
        return not (z_hi < z_min or z_lo > z_max)
    w_xy = np.array([cx - a[0], cy - a[1]])
    s_closest = float(w_xy @ v_xy) / v_sq
    perp = w_xy - s_closest * v_xy
    perp_dist = float(np.linalg.norm(perp))
    if perp_dist > r:
        return False
    half_chord = float(np.sqrt(r**2 - perp_dist**2) / np.sqrt(v_sq))
    s_lo = max(s_closest - half_chord, 0.0)
    s_hi = min(s_closest + half_chord, 1.0)
    if s_lo > s_hi:
        return False
    z_lo = a[2] + s_lo * v[2]
    z_hi = a[2] + s_hi * v[2]
    z_seg_min, z_seg_max = sorted([z_lo, z_hi])
    return not (z_seg_max < z_min or z_seg_min > z_max)


def occluded_ranges(true_pos, anchors, occluders, rng):
    n = len(anchors)
    true_r = np.linalg.norm(anchors - true_pos, axis=1)
    noisy = np.zeros(n)
    blocked = np.zeros(n, dtype=bool)
    for i, anchor in enumerate(anchors):
        is_blocked = any(cylinder_blocks(anchor, true_pos, occ) for occ in occluders)
        blocked[i] = is_blocked
        if not is_blocked:
            noisy[i] = true_r[i] + rng.normal(0.0, RANGE_SIGMA_DEFAULT)
        else:
            if rng.random() < DROP_PROB:
                noisy[i] = np.nan
            else:
                noisy[i] = (
                    true_r[i] + rng.uniform(*NLOS_BIAS) + rng.normal(0.0, SIGMA_NLOS)
                )
    return noisy, blocked


def measure_trajectory_occluded(times, positions, anchors=ANCHORS_8, seed=42):
    rng = np.random.default_rng(seed)
    meas_t, meas_p = [], []
    n_total = n_drop = n_skip = 0
    per_anchor_drop = np.zeros(len(anchors), dtype=int)
    per_anchor_samp = np.zeros(len(anchors), dtype=int)
    last = None
    static = static_occluders()
    for t, true_pos in zip(times, positions):
        occluders = static + [bowler_at(t)]
        ranges, blocked = occluded_ranges(true_pos, anchors, occluders, rng)
        n_total += len(ranges)
        dropped = np.isnan(ranges)
        n_drop += int(dropped.sum())
        per_anchor_samp += 1
        per_anchor_drop += dropped.astype(int)
        valid = (~dropped).sum()
        if valid < 4:
            n_skip += 1
            continue
        x0 = (true_pos + rng.normal(0, 0.05, 3)) if last is None else last
        try:
            est = solve_position(ranges, anchors, x0)
        except Exception:
            n_skip += 1
            continue
        meas_t.append(t)
        meas_p.append(est)
        last = est
    return (
        np.array(meas_t),
        np.array(meas_p),
        n_drop,
        n_total,
        n_skip,
        per_anchor_drop,
        per_anchor_samp,
    )


def run_one_delivery(seed):
    """Single delivery returning (n_total, n_drop, n_skip, raw_rms, fit_rms)."""
    rp, v0, spin = make_delivery(speed_mps=38.0)
    ts_true, st_true = integrate_trajectory(rp, v0, spin)
    sample_t = np.arange(0.01, ts_true[-1] - 0.01, 0.002)
    idx = np.clip(np.searchsorted(ts_true, sample_t), 0, len(ts_true) - 1)
    sample_p = st_true[idx, :3]
    meas_t, meas_p, ndrop, ntot, nskip, *_ = measure_trajectory_occluded(
        sample_t, sample_p, seed=seed
    )
    if len(meas_t) < 20:
        return ntot, ndrop, nskip, float("nan"), float("nan")
    idx_m = np.clip(np.searchsorted(ts_true, meas_t), 0, len(ts_true) - 1)
    truth = st_true[idx_m, :3]
    raw_err = meas_p - truth
    raw_rms = float(np.sqrt((raw_err**2).sum(axis=1)).mean() * 1000)
    fitted, _ = fit_trajectory(meas_t, meas_p)
    fit_err = fitted - truth
    fit_rms = float(np.sqrt((fit_err**2).sum(axis=1)).mean() * 1000)
    return ntot, ndrop, nskip, raw_rms, fit_rms


def main():
    print("\nSim 05 — multipath and occlusion\n", flush=True)
    rp, v0, spin = make_delivery(speed_mps=38.0)
    ts_true, st_true = integrate_trajectory(rp, v0, spin)
    true_pos = st_true[:, :3]
    sample_t = np.arange(0.01, ts_true[-1] - 0.01, 0.002)
    idx = np.clip(np.searchsorted(ts_true, sample_t), 0, len(ts_true) - 1)
    sample_p = true_pos[idx]

    meas_t, meas_p, ndrop, ntot, nskip, pa_drop, pa_samp = measure_trajectory_occluded(
        sample_t, sample_p, seed=42
    )
    idx_m = np.clip(np.searchsorted(ts_true, meas_t), 0, len(ts_true) - 1)
    truth = true_pos[idx_m]
    raw_err = meas_p - truth
    raw_rms = np.sqrt((raw_err**2).sum(axis=1)).mean() * 1000
    fitted, _ = fit_trajectory(meas_t, meas_p)
    fit_err = fitted - truth
    fit_rms = np.sqrt((fit_err**2).sum(axis=1)).mean() * 1000

    print(f"  Anchor-rays total      : {ntot}")
    print(f"  Anchor-rays blocked    : {ndrop} ({100 * ndrop / ntot:.1f}%)")
    print(f"  Samples lost (<4 valid): {nskip}/{len(sample_t)}")
    print(f"  Surviving fixes        : {len(meas_t)}")
    print(
        "  Per-anchor drop rate   : "
        + ", ".join(
            f"A{i + 1}={100 * pa_drop[i] / pa_samp[i]:.0f}%"
            for i in range(len(pa_drop))
        )
    )
    print(f"\n  Raw multilateration RMS: {raw_rms:.1f} mm (clean-LOS baseline ≈135)")
    print(f"  Physics-fit RMS        : {fit_rms:.1f} mm (clean-LOS baseline ≈10)")
    print(f"  Degradation vs clean   : {fit_rms / 10:.2f}× ")
    print(
        f"  Target ≤40 mm (DRS)    : {'ACHIEVED ✓' if fit_rms < 40 else 'DEGRADED ✗'}"
    )

    n_mc = 8
    print(f"\n  Monte Carlo ({n_mc} deliveries)...", flush=True)
    rmss = []
    for s in range(n_mc):
        _, _, _, _, fr = run_one_delivery(seed=100 + s)
        if not np.isnan(fr):
            rmss.append(fr)
        print(
            f"    [{s + 1}/{n_mc}] fit RMS = "
            f"{'fail' if np.isnan(fr) else f'{fr:.1f} mm'}",
            flush=True,
        )
    rmss = np.array(rmss)
    print(
        f"  MC fit RMS: mean={rmss.mean():.1f}  median={np.median(rmss):.1f} "
        f"  p95={np.percentile(rmss, 95):.1f}  min={rmss.min():.1f}  "
        f"max={rmss.max():.1f} mm  (n={len(rmss)})"
    )

    fig = plt.figure(figsize=(16, 9))
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.3)

    ax = fig.add_subplot(gs[0, 0])
    ax.set_aspect("equal")
    ax.add_patch(
        patches.Rectangle(
            (-PITCH_HL, -1.525), 2 * PITCH_HL, 3.05, facecolor="#d4a574", alpha=0.3
        )
    )
    ax.plot(true_pos[:, 0], true_pos[:, 1], "g-", lw=2, label="True")
    ax.scatter(meas_p[:, 0], meas_p[:, 1], c="red", s=3, alpha=0.4, label="Raw (occl.)")
    ax.plot(fitted[:, 0], fitted[:, 1], "b-", lw=1.5, label="Fit")
    ax.scatter(ANCHORS_8[:, 0], ANCHORS_8[:, 1], c="k", s=20, marker="s")
    for name, cx, cy, r, *_ in static_occluders():
        ax.add_patch(patches.Circle((cx, cy), r, color="purple", alpha=0.4))
        ax.annotate(name, (cx, cy), fontsize=7, ha="center", va="center")
    for t_snap in [0.0, 0.25, 0.5]:
        _, bx, by, br, *_ = bowler_at(t_snap)
        ax.add_patch(patches.Circle((bx, by), br, color="orange", alpha=0.25))
    ax.set_xlim(-12, 13)
    ax.set_ylim(-3, 2)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_title("Top down — occluders shown")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)

    ax = fig.add_subplot(gs[0, 1])
    ax.plot(true_pos[:, 0], true_pos[:, 2], "g-", lw=2, label="True")
    ax.scatter(meas_p[:, 0], meas_p[:, 2], c="red", s=3, alpha=0.4, label="Raw")
    ax.plot(fitted[:, 0], fitted[:, 2], "b-", lw=1.5, label="Fit")
    ax.axhline(0, color="#8b6f47", lw=2)
    for x_end in [-PITCH_HL, PITCH_HL]:
        ax.plot([x_end, x_end], [0, STUMP_HEIGHT], color="saddlebrown", lw=2)
    ax.set_xlim(-12, 13)
    ax.set_ylim(-0.2, 3)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Z (m)")
    ax.set_title("Side view")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)

    ax = fig.add_subplot(gs[0, 2])
    drop_pct = 100 * pa_drop / np.maximum(pa_samp, 1)
    ax.bar(range(1, 9), drop_pct, color="purple", edgecolor="k", alpha=0.7)
    ax.set_xticks(range(1, 9))
    ax.set_xlabel("Anchor ID")
    ax.set_ylabel("Drop rate (%)")
    ax.set_title("Per-anchor occlusion")
    ax.grid(alpha=0.3, axis="y")

    ax = fig.add_subplot(gs[1, 0])
    bins = np.linspace(0, 400, 40)
    raw_3d = np.sqrt((raw_err**2).sum(axis=1)) * 1000
    fit_3d = np.sqrt((fit_err**2).sum(axis=1)) * 1000
    ax.hist(raw_3d, bins=bins, alpha=0.5, color="red", label="Raw", edgecolor="k")
    ax.hist(fit_3d, bins=bins, alpha=0.8, color="blue", label="Fit", edgecolor="k")
    ax.axvline(20, color="green", ls="--", label="20mm")
    ax.set_xlabel("3D error (mm)")
    ax.set_ylabel("Count")
    ax.set_title("Single delivery error dist")
    ax.legend()
    ax.grid(alpha=0.3, axis="y")

    ax = fig.add_subplot(gs[1, 1])
    ax.hist(rmss, bins=15, color="steelblue", edgecolor="k", alpha=0.8)
    ax.axvline(10, color="green", ls="--", label="clean-LOS (≈10)")
    ax.axvline(rmss.mean(), color="red", lw=2, label=f"mean={rmss.mean():.1f}")
    ax.set_xlabel("Fit 3D RMS (mm)")
    ax.set_ylabel("Deliveries")
    ax.set_title("MC over 20 deliveries")
    ax.legend()
    ax.grid(alpha=0.3, axis="y")

    ax = fig.add_subplot(gs[1, 2])
    ax.axis("off")
    ax.text(
        0.0,
        0.5,
        f"SIM 05 — OCCLUSION RESULTS\n{'-' * 50}\n"
        f"6 cylindrical occluders (5 static + bowler)\n"
        f"Bowler follow-through: x=-9 → -4 over 0.5 s\n\n"
        f"Single-delivery:\n"
        f"  Rays blocked:      {100 * ndrop / ntot:5.1f}%\n"
        f"  Samples skipped:   {nskip}/{len(sample_t)}\n"
        f"  Raw RMS:           {raw_rms:6.1f} mm\n"
        f"  Fit RMS:           {fit_rms:6.1f} mm\n\n"
        f"Monte Carlo (n={len(rmss)}):\n"
        f"  mean fit RMS:      {rmss.mean():6.1f} mm\n"
        f"  median:            {np.median(rmss):6.1f} mm\n"
        f"  p95:               {np.percentile(rmss, 95):6.1f} mm\n\n"
        f"Clean-LOS baseline:  ≈ 10 mm\n"
        f"Degradation factor:  {rmss.mean() / 10:.2f}×\n\n"
        f"DRS target (≤40 mm): "
        f"{'PASS ✓' if np.percentile(rmss, 95) < 40 else 'CHECK ✗'}",
        transform=ax.transAxes,
        family="monospace",
        fontsize=9,
        verticalalignment="center",
    )

    fig.suptitle("Sim 05 — Trajectory recovery with cylindrical occlusion", fontsize=13)
    out = "outputs/sim05_multipath_occlusion.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    main()
