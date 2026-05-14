"""Realistic-occlusion sim — skeleton batter + corrected bowler at 100 Hz.

Compares two occlusion models on the same trajectory + anchor setup,
both at the deployable 100 Hz UWB rate:

  A) "old"        — sim 05b's blob batter, x=-9 → -4 bowler, no high-arm
  B) "realistic"  — sampled batter skeleton (14 bones), bowler with
                    Law-41-compliant follow-through (-8.84 → -5.0,
                    +0.20 → +1.50) plus high-arm cylinder during the
                    release window (first 0.15 s)

Both use TWR + Huber loss + 85% NLOS detection from sim 05b. All
geometry uses oriented bones via `line_bone_chord_length`.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from infinity_stumps import (
    ANCHORS_8,
    RANGE_SIGMA_DEFAULT,
    fit_trajectory,
    solve_position,
)
from infinity_stumps.physics import integrate_trajectory, make_delivery
from infinity_stumps.skeleton import (
    CHORD_BLOCK_THRESHOLD_M,
    Bone,
    line_bone_chord_length,
    sample_batter,
)

P_DETECT = 0.85
P_FP = 0.02
HUBER_FSCALE = 3.0
SIGMA_NLOS = 0.10
NLOS_BIAS = (0.05, 0.20)
DROP_PROB = 0.5
N_MC = 30
UWB_RATE_HZ = 100.0


# ---------- occluder generators ----------


def static_bones_old():
    """sim 05b-equivalent: blob batter + fat-cylinder static people."""
    HUMAN_R = 0.35
    return [
        Bone(
            np.array([-10.5, -0.40, 0.0]),
            np.array([-10.5, -0.40, 1.85]),
            HUMAN_R,
            "umpire",
        ),
        Bone(
            np.array([+10.0, -0.05, 0.0]),
            np.array([+10.0, -0.05, 1.85]),
            HUMAN_R,
            "batter_blob",
        ),
        Bone(
            np.array([+11.0, 0.0, 0.0]), np.array([+11.0, 0.0, 1.10]), HUMAN_R, "keeper"
        ),
        Bone(
            np.array([+11.2, -1.20, 0.0]),
            np.array([+11.2, -1.20, 1.10]),
            HUMAN_R,
            "slip1",
        ),
        Bone(
            np.array([+11.5, -1.80, 0.0]),
            np.array([+11.5, -1.80, 1.10]),
            HUMAN_R,
            "slip2",
        ),
    ]


def static_bones_realistic(rng):
    """Skeleton batter sampled per delivery + realistic-radius static people."""
    bones = [
        # Umpire — torso width 0.20m (more realistic than the 0.35 blob)
        Bone(
            np.array([-10.5, -0.40, 0.0]),
            np.array([-10.5, -0.40, 1.85]),
            0.20,
            "umpire",
        ),
        # Keeper (crouched, slightly stockier in crouch)
        Bone(np.array([+11.0, 0.0, 0.0]), np.array([+11.0, 0.0, 1.10]), 0.25, "keeper"),
        # 1st slip
        Bone(
            np.array([+11.2, -1.20, 0.0]), np.array([+11.2, -1.20, 1.10]), 0.22, "slip1"
        ),
        # 2nd slip
        Bone(
            np.array([+11.5, -1.80, 0.0]), np.array([+11.5, -1.80, 1.10]), 0.22, "slip2"
        ),
    ]
    batter = sample_batter(rng, stance_x_centre=10.0)
    bones.extend(batter.bones)
    return bones


def bowler_bones_old(t):
    """sim 05b's old bowler: linear (-9, 0.2) → (-4, 0.6), static cylinder."""
    if t <= 0.5:
        s = t / 0.5
        x = -9.0 + 5.0 * s
        y = 0.20 + 0.40 * s
    else:
        x, y = -4.0, 0.60
    return [Bone(np.array([x, y, 0.0]), np.array([x, y, 1.85]), 0.35, "bowler_old")]


def bowler_bones_realistic(t):
    """Law-41-compliant follow-through + high-arm release window.

    t=0       : (-8.84, +0.20)  — heel on popping crease
    t=0.5     : (-5.0,  +1.50)  — clear of pitch and protected area
    First 0.15s : bonus high-arm bone z up to 2.5m (release arm extension)
    """
    if t <= 0.5:
        s = t / 0.5
        x = -8.84 + (-5.0 - -8.84) * s
        y = 0.20 + (1.50 - 0.20) * s
    else:
        x, y = -5.0, 1.50
    bones = [Bone(np.array([x, y, 0.0]), np.array([x, y, 1.85]), 0.20, "bowler_torso")]
    if t <= 0.15:
        # Arm extended overhead — modelled as a thinner cylinder from
        # torso top to release height
        bones.append(
            Bone(np.array([x, y, 1.85]), np.array([x, y, 2.50]), 0.05, "bowler_arm")
        )
    return bones


# ---------- measurement + run ----------


def is_blocked(p_source, p_target, bones, threshold=CHORD_BLOCK_THRESHOLD_M):
    for b in bones:
        if line_bone_chord_length(p_source, p_target, b) > threshold:
            return True
    return False


def measure(true_pos, anchors, bones, rng):
    n = len(anchors)
    true_r = np.linalg.norm(anchors - true_pos, axis=1)
    noisy = np.zeros(n)
    for i, anchor in enumerate(anchors):
        blocked = is_blocked(anchor, true_pos, bones)
        if not blocked:
            if rng.random() < P_FP:
                noisy[i] = np.nan
            else:
                noisy[i] = true_r[i] + rng.normal(0.0, RANGE_SIGMA_DEFAULT)
        else:
            if rng.random() < DROP_PROB:
                noisy[i] = np.nan
            elif rng.random() < P_DETECT:
                noisy[i] = np.nan
            else:
                noisy[i] = (
                    true_r[i] + rng.uniform(*NLOS_BIAS) + rng.normal(0.0, SIGMA_NLOS)
                )
    return noisy


def run_one(scenario, seed):
    rp, v0, spin = make_delivery(speed_mps=38.0)
    ts, st = integrate_trajectory(rp, v0, spin)
    sample_t = np.arange(0.01, ts[-1] - 0.01, 1.0 / UWB_RATE_HZ)
    idx = np.clip(np.searchsorted(ts, sample_t), 0, len(ts) - 1)
    sample_p = st[idx, :3]

    rng = np.random.default_rng(seed)
    if scenario == "old":
        static = static_bones_old()
        bowler_fn = bowler_bones_old
    else:
        static = static_bones_realistic(rng)
        bowler_fn = bowler_bones_realistic

    meas_t, meas_p = [], []
    last = None
    n_blocked_total = 0
    n_total = 0
    for t, true_pos in zip(sample_t, sample_p):
        bones = static + bowler_fn(t)
        ranges = measure(true_pos, ANCHORS_8, bones, rng)
        n_total += len(ranges)
        n_blocked_total += int(np.isnan(ranges).sum())
        if (~np.isnan(ranges)).sum() < 4:
            continue
        x0 = (true_pos + rng.normal(0, 0.05, 3)) if last is None else last
        try:
            est = solve_position(ranges, ANCHORS_8, x0)
        except Exception:
            continue
        meas_t.append(t)
        meas_p.append(est)
        last = est

    meas_t = np.array(meas_t)
    meas_p = np.array(meas_p)
    if len(meas_t) < 20:
        return float("nan"), 0.0
    idx_m = np.clip(np.searchsorted(ts, meas_t), 0, len(ts) - 1)
    truth_m = st[idx_m, :3]
    fitted, _ = fit_trajectory(meas_t, meas_p, loss="huber", f_scale=HUBER_FSCALE)
    err = fitted - truth_m
    rms = float(np.sqrt((err**2).sum(axis=1)).mean() * 1000)
    drop_rate = n_blocked_total / max(n_total, 1)
    return rms, drop_rate


def main():
    print("\nSim Realistic — skeleton batter + corrected bowler @ 100 Hz\n", flush=True)
    print(f"  UWB rate         : {int(UWB_RATE_HZ)} Hz (ETSI-compliant)")
    print(f"  NLOS detection   : p_detect={P_DETECT}, p_fp={P_FP}")
    print(f"  Solver loss      : Huber (f_scale={HUBER_FSCALE})\n", flush=True)

    results = {}
    for scenario in ["old", "realistic"]:
        print(f"  Scenario: {scenario}", flush=True)
        rmss, drops = [], []
        for s in range(N_MC):
            r, d = run_one(scenario, seed=1500 + s)
            if not np.isnan(r):
                rmss.append(r)
                drops.append(d)
            print(
                f"    [{s + 1}/{N_MC}] fit RMS = "
                f"{'fail' if np.isnan(r) else f'{r:6.1f} mm'}, "
                f"drop_rate = {d * 100:.1f}%",
                flush=True,
            )
        rmss = np.array(rmss)
        drops = np.array(drops)
        results[scenario] = (rmss, drops)
        print(
            f"    -> mean={rmss.mean():.1f}  med={np.median(rmss):.1f}  "
            f"p95={np.percentile(rmss, 95):.1f} mm  "
            f"avg drop={drops.mean() * 100:.1f}%\n",
            flush=True,
        )

    print("\nSUMMARY")
    print("-" * 60)
    print(f"  {'scenario':15s} {'mean':>8s} {'med':>8s} {'p95':>8s} {'drop%':>8s}")
    for name, (rmss, drops) in results.items():
        print(
            f"  {name:15s} {rmss.mean():>7.1f}  {np.median(rmss):>7.1f}  "
            f"{np.percentile(rmss, 95):>7.1f}  {drops.mean() * 100:>7.1f}"
        )
    old_rms = results["old"][0].mean()
    new_rms = results["realistic"][0].mean()
    delta = (new_rms - old_rms) / old_rms * 100
    print(
        f"\n  Δ realistic vs old: {delta:+.1f}%  ({'better' if delta < 0 else 'worse'})"
    )

    fig, ax = plt.subplots(figsize=(9, 5))
    labels = list(results.keys())
    data = [results[k][0] for k in labels]
    bp = ax.boxplot(data, widths=0.6, patch_artist=True, tick_labels=labels)
    for patch, c in zip(bp["boxes"], ["#c44", "#48a"]):
        patch.set_alpha(0.7)
        patch.set_facecolor(c)
    ax.axhline(47, color="purple", ls="--", label="sim 05b at 500 Hz (~47 mm)")
    ax.set_ylabel("Fit 3D RMS (mm) at 100 Hz")
    ax.set_title("Sim Realistic — old vs skeleton+corrected-bowler occlusion")
    ax.grid(alpha=0.3, axis="y")
    ax.legend()
    plt.tight_layout()
    out = "outputs/sim_realistic.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\n  Saved: {out}", flush=True)


if __name__ == "__main__":
    main()
