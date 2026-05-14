"""Sim LBW — predict stump-line impact + verdict, vs ground truth.

For each simulated delivery:
  1. Generate full natural trajectory (no pad)
  2. Sample at 100 Hz with realistic skeleton occlusion + Huber/NLOS
  3. Multilat per timestep, keep only samples before t_impact (where
     t_impact is the time the ball would have reached the pad plane,
     ~1 m in front of the batter-end stumps)
  4. Physics-fit those samples with Huber loss
  5. Compute parameter covariance from the fit Jacobian
  6. Extrapolate fitted trajectory to stump line; propagate covariance
  7. Compare predicted (y, z) at stump line to ground truth

Reports:
  - y-axis stump-line error (mm) — iBall benchmark: 99 mm (NSDI '17)
  - z-axis stump-line error (mm)
  - 3D extrapolation error (mm)        — iBall: 220 mm
  - Verdict confusion matrix (HIT/MISS/UMPIRE)
  - 95% ellipse semi-axes — width of the UMPIRE'S CALL band

Compare-to-iBall summary printed at the end.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares

from infinity_stumps import (
    ANCHORS_8,
    BallParams,
    EKFConfig,
    TrajectoryEKF,
    integrate_trajectory,
    solve_position,
)
from infinity_stumps.lbw import (
    STUMP_HALF_W,
    STUMP_LINE_X,
    STUMP_TOP_H,
    extrapolate_to_stumps,
    find_bounce,
    fit_covariance,
    lbw_verdict,
    stump_line_covariance,
)
from infinity_stumps.physics import make_delivery
from infinity_stumps.skeleton import (
    CHORD_BLOCK_THRESHOLD_M,
    Bone,
    line_bone_chord_length,
    sample_batter,
)
from infinity_stumps.solver import solve_position_at_ground

# Same noise + occlusion model as sim_realistic
UWB_RATE_HZ = 100.0
RANGE_SIGMA = 0.030
HUBER_FSCALE = 3.0
SIGMA_NLOS = 0.10
NLOS_BIAS = (0.05, 0.20)
P_DETECT = 0.85
P_FP = 0.02
DROP_PROB = 0.5
PAD_DISTANCE_FROM_STUMPS = 1.0  # m — typical batter front foot position
N_MC = 30


def static_bones(rng):
    return [
        Bone(
            np.array([-10.5, -0.40, 0.0]),
            np.array([-10.5, -0.40, 1.85]),
            0.20,
            "umpire",
        ),
        Bone(np.array([+11.0, 0.0, 0.0]), np.array([+11.0, 0.0, 1.10]), 0.25, "keeper"),
        Bone(
            np.array([+11.2, -1.20, 0.0]), np.array([+11.2, -1.20, 1.10]), 0.22, "slip1"
        ),
        Bone(
            np.array([+11.5, -1.80, 0.0]), np.array([+11.5, -1.80, 1.10]), 0.22, "slip2"
        ),
    ] + sample_batter(rng, stance_x_centre=10.0).bones


def bowler_bones(t):
    if t <= 0.5:
        s = t / 0.5
        x = -8.84 + (-5.0 - -8.84) * s
        y = 0.20 + (1.50 - 0.20) * s
    else:
        x, y = -5.0, 1.50
    bones = [Bone(np.array([x, y, 0.0]), np.array([x, y, 1.85]), 0.20, "bowler_torso")]
    if t <= 0.15:
        bones.append(
            Bone(np.array([x, y, 1.85]), np.array([x, y, 2.50]), 0.05, "bowler_arm")
        )
    return bones


def is_blocked(p_src, p_tgt, bones):
    for b in bones:
        if line_bone_chord_length(p_src, p_tgt, b) > CHORD_BLOCK_THRESHOLD_M:
            return True
    return False


def measure(true_pos, anchors, bones, rng):
    n = len(anchors)
    true_r = np.linalg.norm(anchors - true_pos, axis=1)
    out = np.zeros(n)
    for i, a in enumerate(anchors):
        blocked = is_blocked(a, true_pos, bones)
        if not blocked:
            if rng.random() < P_FP:
                out[i] = np.nan
            else:
                out[i] = true_r[i] + rng.normal(0.0, RANGE_SIGMA)
        else:
            if rng.random() < DROP_PROB:
                out[i] = np.nan
            elif rng.random() < P_DETECT:
                out[i] = np.nan
            else:
                out[i] = (
                    true_r[i] + rng.uniform(*NLOS_BIAS) + rng.normal(0.0, SIGMA_NLOS)
                )
    return out


def measure_one_range(true_pos, anchor, bones, rng):
    """Per-anchor range with NLOS / dropout / FP. NaN = invalid."""
    blocked = is_blocked(anchor, true_pos, bones)
    true_d = float(np.linalg.norm(anchor - true_pos))
    if not blocked:
        if rng.random() < P_FP:
            return np.nan
        return true_d + rng.normal(0.0, RANGE_SIGMA)
    if rng.random() < DROP_PROB:
        return np.nan
    if rng.random() < P_DETECT:
        return np.nan
    return true_d + rng.uniform(*NLOS_BIAS) + rng.normal(0.0, SIGMA_NLOS)


def fit_with_jacobian(
    times_obs,
    pos_obs,
    sigma_pos=0.05,
    params: BallParams | None = None,
    loss="huber",
    f_scale=HUBER_FSCALE,
    bounce_time: float | None = None,
    bounce_sigma_z: float = 0.020,
    bounce_vz_obs: float | None = None,
    bounce_vz_sigma: float = 1.0,
    bounce_xy_obs: np.ndarray | None = None,
    bounce_xy_sigma=(0.015, 0.080),
):
    """Run the physics fit and return (fitted_params, residuals, jacobian)."""
    if params is None:
        params = BallParams()
    n_init = min(20, len(times_obs))
    p0_pos = pos_obs[0]
    dt_init = max(times_obs[n_init - 1] - times_obs[0], 1e-3)
    p0_vel = (pos_obs[n_init - 1] - pos_obs[0]) / dt_init
    p0_spin = np.array([0.0, 50.0, 0.0])
    x0 = np.concatenate([p0_pos, p0_vel, p0_spin])
    t_max = (
        max(times_obs[-1], bounce_time if bounce_time is not None else times_obs[-1])
        + 1e-3
    )

    def residuals(pv):
        ts, st = integrate_trajectory(
            pv[:3], pv[3:6], pv[6:9], t_max=t_max, params=params
        )
        interp = np.column_stack([np.interp(times_obs, ts, st[:, d]) for d in range(3)])
        obs_r = (interp - pos_obs).flatten() / sigma_pos
        if bounce_time is None:
            return obs_r
        z_b = float(np.interp(bounce_time, ts, st[:, 2]))
        extra = [z_b / bounce_sigma_z]
        if bounce_vz_obs is not None:
            t_pre = bounce_time - 0.002
            vz_pre = float(np.interp(t_pre, ts, st[:, 5]))
            r = (vz_pre - bounce_vz_obs) / bounce_vz_sigma
            extra.append(float(np.clip(r, -2.0, 2.0)))
        if bounce_xy_obs is not None:
            x_b = float(np.interp(bounce_time, ts, st[:, 0]))
            y_b = float(np.interp(bounce_time, ts, st[:, 1]))
            if np.ndim(bounce_xy_sigma) == 0:
                sx = sy = float(bounce_xy_sigma)
            else:
                sx, sy = float(bounce_xy_sigma[0]), float(bounce_xy_sigma[1])
            extra.append((x_b - bounce_xy_obs[0]) / sx)
            extra.append((y_b - bounce_xy_obs[1]) / sy)
        return np.concatenate([obs_r, np.asarray(extra)])

    result = least_squares(
        residuals, x0, method="trf", loss=loss, f_scale=f_scale, max_nfev=200
    )
    return result.x, result.fun, result.jac


def run_one(seed: int, verbose: bool = False) -> dict:
    rng = np.random.default_rng(seed)

    # Random delivery — vary release, spin, angles so trajectories
    # actually differ in where they pitch / would hit the stumps
    speed = float(rng.uniform(28.0, 42.0))
    release_h = float(rng.uniform(2.0, 2.5))
    release_x = float(rng.uniform(-9.5, -8.0))
    release_y = float(rng.uniform(-0.5, 0.5))
    ang_h = float(rng.uniform(-4.0, 4.0))  # horizontal launch (deg)
    ang_v = float(rng.uniform(3.0, 9.0))  # vertical launch (deg)
    spin_axis = rng.normal(size=3)
    spin_rps = float(rng.uniform(15.0, 35.0))
    rp, v0, spin = make_delivery(
        speed_mps=speed,
        release_height=release_h,
        release_x=release_x,
        release_y=release_y,
        angle_horizontal_deg=ang_h,
        angle_vertical_deg=ang_v,
        spin_axis=spin_axis,
        spin_rev_per_sec=spin_rps,
    )

    # Ground truth — full natural trajectory, no pad
    ts_truth, st_truth = integrate_trajectory(rp, v0, spin)
    xs_truth = st_truth[:, 0]

    # Determine pad-impact time: ball at x = stump_x - pad_distance
    target_x = STUMP_LINE_X - PAD_DISTANCE_FROM_STUMPS
    crosses = (xs_truth[:-1] < target_x) & (xs_truth[1:] >= target_x)
    idx_imp = np.where(crosses)[0]
    if len(idx_imp) == 0:
        return {"ok": False, "reason": "trajectory never reached pad plane"}
    i_imp = int(idx_imp[0])
    alpha = (target_x - xs_truth[i_imp]) / (xs_truth[i_imp + 1] - xs_truth[i_imp])
    t_impact = ts_truth[i_imp] + alpha * (ts_truth[i_imp + 1] - ts_truth[i_imp])
    impact_pos = st_truth[i_imp, :3] + alpha * (
        st_truth[i_imp + 1, :3] - st_truth[i_imp, :3]
    )

    # Ground truth stump-line crossing
    truth = extrapolate_to_stumps(rp, v0, spin)
    if truth is None:
        return {"ok": False, "reason": "truth never reaches stump line"}
    _, yz_truth = truth
    truth_verdict = lbw_verdict(yz_truth, None).decision
    truth_bounce = find_bounce(rp, v0, spin)

    # Sample UWB observations at 100 Hz, only BEFORE t_impact
    sample_t = np.arange(
        0.01, min(t_impact - 0.005, ts_truth[-1] - 0.01), 1.0 / UWB_RATE_HZ
    )
    idx = np.clip(np.searchsorted(ts_truth, sample_t), 0, len(ts_truth) - 1)
    sample_p = st_truth[idx, :3]
    if len(sample_t) < 20:
        return {"ok": False, "reason": f"too few samples ({len(sample_t)})"}

    statics = static_bones(rng)

    # Run EKF forward through all pre-impact UWB cycles (TWR-staggered),
    # then RTS-smooth backward. Smoothed state at t=0 is the equivalent
    # of the batch-fit's recovered (release_pos, v0, spin).
    ekf = TrajectoryEKF(BallParams(), EKFConfig())
    # Initial guess — same kind of noisy prior as batch fit used.
    # We use the truth release params + noise; in production we'd seed
    # from a first-few-samples linear extrapolation.
    x0_state = np.concatenate(
        [
            rp + rng.normal(0, 0.2, 3),
            v0 + rng.normal(0, 2.0, 3),
            spin + rng.normal(0, 20, 3),
        ]
    )
    ekf.initialise(t=0.0, x0=x0_state)

    ANCHOR_STAGGER = 1.5e-3 / 8
    for t, true_pos in zip(sample_t, sample_p):
        bones = statics + bowler_bones(t)
        for i, anchor in enumerate(ANCHORS_8):
            t_meas = float(t + i * ANCHOR_STAGGER)
            ekf.predict(t_meas)
            r = measure_one_range(true_pos, anchor, bones, rng)
            if not np.isnan(r):
                ekf.update_range(anchor, r)

    ekf.smooth_backward()

    # Smoothed state at LAST sample (just before pad impact) — best
    # estimate of where the ball is and how it's moving right before
    # the pad would have intercepted. Extrapolating from there to the
    # stumps is a short integration (~30 ms) — much less error
    # compounding than integrating from t=0 release.
    if not ekf.smoothed_state:
        return {"ok": False, "reason": "smoother produced no output"}
    fp = ekf.smoothed_state[-1].copy()
    cov_p = ekf.smoothed_P[-1].copy()

    # Extrapolate fit to stump line
    extr = extrapolate_to_stumps(fp[:3], fp[3:6], fp[6:9])
    if extr is None:
        return {"ok": False, "reason": "fit trajectory never reached stumps"}
    _, yz_pred = extr

    # Propagate covariance to stump line
    yz_cov = None
    if cov_p is not None:
        yz_cov = stump_line_covariance(fp, cov_p)

    pred_verdict = lbw_verdict(yz_pred, yz_cov)

    # Errors
    err_yz = yz_pred - yz_truth
    return {
        "ok": True,
        "y_err_mm": float(err_yz[0] * 1000),
        "z_err_mm": float(err_yz[1] * 1000),
        "yz_3d_err_mm": float(np.sqrt((err_yz**2).sum()) * 1000),
        "truth_verdict": truth_verdict,
        "pred_verdict": pred_verdict.decision,
        "ellipse_semi_axes_mm": tuple(s * 1000 for s in pred_verdict.ellipse_semi_axes),
        "yz_truth": yz_truth.tolist(),
        "yz_pred": yz_pred.tolist(),
    }


def main():
    print("Sim LBW — stump-line extrapolation + verdict @ 100 Hz")
    print(f"  N_MC = {N_MC}")
    print(
        f"  Pad-impact plane: x = {STUMP_LINE_X:.2f} - "
        f"{PAD_DISTANCE_FROM_STUMPS:.2f} = {STUMP_LINE_X - PAD_DISTANCE_FROM_STUMPS:.2f}\n",
        flush=True,
    )

    rows = []
    for i, s in enumerate(range(2000, 2000 + N_MC)):
        r = run_one(s)
        if r["ok"]:
            rows.append(r)
            print(
                f"  [{i + 1:2d}/{N_MC}] y_err={r['y_err_mm']:>+7.1f} mm  "
                f"z_err={r['z_err_mm']:>+7.1f} mm  3D={r['yz_3d_err_mm']:>6.1f}  "
                f"truth={r['truth_verdict']:<14s} pred={r['pred_verdict']}",
                flush=True,
            )
        else:
            print(f"  [{i + 1:2d}/{N_MC}] SKIP — {r['reason']}", flush=True)

    if not rows:
        print("\nNo successful deliveries.")
        return

    y_err = np.array([r["y_err_mm"] for r in rows])
    z_err = np.array([r["z_err_mm"] for r in rows])
    e3d = np.array([r["yz_3d_err_mm"] for r in rows])
    ellipse_a = np.array([r["ellipse_semi_axes_mm"][0] for r in rows])
    ellipse_b = np.array([r["ellipse_semi_axes_mm"][1] for r in rows])

    print("\nSTUMP-LINE EXTRAPOLATION ERROR")
    print(
        f"  y (lateral)  : mean |err| = {np.abs(y_err).mean():>6.1f}  "
        f"med |err| = {np.median(np.abs(y_err)):>6.1f}  "
        f"p95 = {np.percentile(np.abs(y_err), 95):>6.1f}  mm"
    )
    print(
        f"  z (vertical) : mean |err| = {np.abs(z_err).mean():>6.1f}  "
        f"med |err| = {np.median(np.abs(z_err)):>6.1f}  "
        f"p95 = {np.percentile(np.abs(z_err), 95):>6.1f}  mm"
    )
    print(
        f"  2D euclid    : mean       = {e3d.mean():>6.1f}  "
        f"med       = {np.median(e3d):>6.1f}  "
        f"p95 = {np.percentile(e3d, 95):>6.1f}  mm"
    )

    print("\nvs iBall (NSDI '17):")
    print(
        f"  iBall lateral (X-axis) median: 99 mm  | Ours: "
        f"{np.median(np.abs(y_err)):.1f} mm  "
        f"({'BETTER' if np.median(np.abs(y_err)) < 99 else 'WORSE'})"
    )
    print(
        f"  iBall 3D extrap     median:    220 mm | Ours: "
        f"{np.median(e3d):.1f} mm  "
        f"({'BETTER' if np.median(e3d) < 220 else 'WORSE'})"
    )
    print(
        f"  ICC LBW tolerance:             100 mm | Ours: "
        f"{np.median(np.abs(y_err)):.1f} mm  "
        f"({'WITHIN' if np.median(np.abs(y_err)) < 100 else 'OUT OF'})"
    )

    print("\n95% ELLIPSE (uncertainty band at stump line)")
    print(
        f"  Major semi-axis : mean = {ellipse_a.mean():>6.1f}  "
        f"med = {np.median(ellipse_a):>6.1f}  mm"
    )
    print(
        f"  Minor semi-axis : mean = {ellipse_b.mean():>6.1f}  "
        f"med = {np.median(ellipse_b):>6.1f}  mm"
    )

    print("\nVERDICT CONFUSION (rows=truth, cols=pred)")
    labels = ["HITTING", "MISSING", "UMPIRE'S CALL"]
    cm = np.zeros((3, 3), dtype=int)
    for r in rows:
        ti = labels.index(r["truth_verdict"])
        pi = labels.index(r["pred_verdict"])
        cm[ti, pi] += 1
    print(f"  {'':<16}{'HIT':>8}{'MISS':>8}{'UMP':>8}")
    for i, name in enumerate(labels):
        print(f"  {name:<16}{cm[i, 0]:>8}{cm[i, 1]:>8}{cm[i, 2]:>8}")
    # Strict-accuracy (predicted-vs-truth identical, treating UMP as correct)
    correct = sum(1 for r in rows if r["truth_verdict"] == r["pred_verdict"])
    print(
        f"\n  Exact-match verdict accuracy: {correct}/{len(rows)} "
        f"({100 * correct / len(rows):.1f}%)"
    )
    consistent = sum(
        1
        for r in rows
        if r["pred_verdict"] == "UMPIRE'S CALL"
        or r["truth_verdict"] == r["pred_verdict"]
    )
    print(
        f"  Verdict consistent (pred=UMP allowed): {consistent}/{len(rows)} "
        f"({100 * consistent / len(rows):.1f}%)"
    )

    # Scatter plot at stump line
    fig, ax = plt.subplots(figsize=(8, 6))
    yt = np.array([r["yz_truth"][0] for r in rows]) * 1000
    zt = np.array([r["yz_truth"][1] for r in rows]) * 1000
    yp = np.array([r["yz_pred"][0] for r in rows]) * 1000
    zp = np.array([r["yz_pred"][1] for r in rows]) * 1000
    # Stump rectangle
    from matplotlib.patches import Rectangle

    rect = Rectangle(
        (-STUMP_HALF_W * 1000, 0),
        STUMP_HALF_W * 2 * 1000,
        STUMP_TOP_H * 1000,
        fill=False,
        edgecolor="black",
        linewidth=2,
        label="stumps",
    )
    ax.add_patch(rect)
    ax.scatter(
        yt,
        zt,
        c="green",
        s=60,
        alpha=0.7,
        label="ground truth",
        marker="o",
        edgecolor="black",
    )
    ax.scatter(yp, zp, c="red", s=60, alpha=0.7, label="predicted", marker="x")
    for r in rows:
        ax.plot(
            [r["yz_truth"][0] * 1000, r["yz_pred"][0] * 1000],
            [r["yz_truth"][1] * 1000, r["yz_pred"][1] * 1000],
            "k-",
            alpha=0.2,
            lw=0.5,
        )
    ax.set_xlabel("y (lateral, mm)")
    ax.set_ylabel("z (vertical, mm)")
    ax.set_title(f"Sim LBW — predicted vs truth at stump line, n={len(rows)}")
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    ax.legend()
    ax.set_xlim(-600, 600)
    ax.set_ylim(-200, 1200)
    plt.tight_layout()
    out = "outputs/sim_lbw.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\n  Saved: {out}", flush=True)


if __name__ == "__main__":
    main()
