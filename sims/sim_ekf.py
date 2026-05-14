"""Sim EKF — TrajectoryEKF vs batch fit on the same realistic occlusion.

Phase 1 of the UWB-IMU fusion plan: physics EKF without IMU.

Same realistic-skeleton occlusion model as sim_realistic, same n=30
seeds (1500..1529). The EKF runs cycle-by-cycle, ingesting per-anchor
ranges in TWR-staggered order. After ingesting all pre-impact samples,
it forward-propagates to give the final trajectory.

Compares to sim_realistic n=30 baseline (mean 41 / median 35 / p95 78 mm
RMS error per delivery).
"""

from __future__ import annotations
import numpy as np
import matplotlib.pyplot as plt

from cricket_uwb import (ANCHORS_8, BallParams, TrajectoryEKF, EKFConfig,
                           integrate_trajectory)
from cricket_uwb.physics import make_delivery
from cricket_uwb.skeleton import (sample_batter, line_bone_chord_length,
                                    CHORD_BLOCK_THRESHOLD_M, Bone)

P_DETECT = 0.85
P_FP = 0.02
SIGMA_NLOS = 0.10
NLOS_BIAS = (0.05, 0.20)
DROP_PROB = 0.5
RANGE_SIGMA = 0.030
UWB_RATE_HZ = 100.0
ANCHOR_STAGGER = 1.5e-3 / 8     # 150 µs per anchor within one cycle
N_MC = 30


def static_bones(rng):
    return [
        Bone(np.array([-10.5, -0.40, 0.0]),
             np.array([-10.5, -0.40, 1.85]), 0.20, "umpire"),
        Bone(np.array([+11.0, 0.0, 0.0]),
             np.array([+11.0, 0.0, 1.10]), 0.25, "keeper"),
        Bone(np.array([+11.2, -1.20, 0.0]),
             np.array([+11.2, -1.20, 1.10]), 0.22, "slip1"),
        Bone(np.array([+11.5, -1.80, 0.0]),
             np.array([+11.5, -1.80, 1.10]), 0.22, "slip2"),
    ] + sample_batter(rng, stance_x_centre=10.0).bones


def bowler_bones(t):
    if t <= 0.5:
        s = t / 0.5
        x = -8.84 + (-5.0 - -8.84) * s
        y = 0.20 + (1.50 - 0.20) * s
    else:
        x, y = -5.0, 1.50
    out = [Bone(np.array([x, y, 0.0]),
                np.array([x, y, 1.85]), 0.20, "bowler_torso")]
    if t <= 0.15:
        out.append(Bone(np.array([x, y, 1.85]),
                        np.array([x, y, 2.50]), 0.05, "bowler_arm"))
    return out


def is_blocked(p_src, p_tgt, bones):
    for b in bones:
        if line_bone_chord_length(p_src, p_tgt, b) > CHORD_BLOCK_THRESHOLD_M:
            return True
    return False


def measure_one_range(true_pos, anchor, bones, rng):
    """Generate one anchor's range with NLOS / dropout / FP. NaN = invalid."""
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
    return (true_d + rng.uniform(*NLOS_BIAS)
            + rng.normal(0.0, SIGMA_NLOS))


def run_one(seed: int) -> dict:
    rng = np.random.default_rng(seed)
    rp, v0, spin = make_delivery(speed_mps=38.0)
    ts_truth, st_truth = integrate_trajectory(rp, v0, spin)
    sample_t = np.arange(0.01, ts_truth[-1] - 0.01, 1.0 / UWB_RATE_HZ)
    idx = np.clip(np.searchsorted(ts_truth, sample_t), 0, len(ts_truth) - 1)
    sample_p_truth = st_truth[idx, :3]

    statics = static_bones(rng)

    ekf = TrajectoryEKF(BallParams(), EKFConfig())
    x0_state = np.concatenate([
        rp + rng.normal(0, 0.2, 3),
        v0 + rng.normal(0, 2.0, 3),
        spin + rng.normal(0, 20, 3),
    ])
    ekf.initialise(t=0.0, x0=x0_state)

    # Record truth-at-cycle for comparison; also remember the cycle-end
    # snapshot index in EKF history so we can extract forward + smoothed
    # estimates at the same times.
    cycle_end_idx: list[int] = []
    truth_at_cycle: list[np.ndarray] = []

    for t, true_pos in zip(sample_t, sample_p_truth):
        bones_now = statics + bowler_bones(t)
        for i, anchor in enumerate(ANCHORS_8):
            t_meas = float(t + i * ANCHOR_STAGGER)
            ekf.predict(t_meas)
            r = measure_one_range(true_pos, anchor, bones_now, rng)
            if not np.isnan(r):
                ekf.update_range(anchor, r)
        cycle_end_idx.append(len(ekf.history_state) - 1)
        truth_at_cycle.append(true_pos.copy())

    # Run RTS smoother backward
    ekf.smooth_backward()

    truth_arr = np.asarray(truth_at_cycle)
    fwd_arr = np.asarray([ekf.history_state[i][:3] for i in cycle_end_idx])
    smo_arr = np.asarray([ekf.smoothed_state[i][:3] for i in cycle_end_idx])

    def stats(est_arr):
        err = est_arr - truth_arr
        rms_3d = float(np.sqrt((err ** 2).sum(axis=1)).mean() * 1000)
        med_3d = float(np.median(np.linalg.norm(err, axis=1)) * 1000)
        per_axis = np.abs(err)
        return {
            "rms_3d_mm": rms_3d,
            "med_3d_mm": med_3d,
            "mean_x_mm": float(per_axis[:, 0].mean() * 1000),
            "mean_y_mm": float(per_axis[:, 1].mean() * 1000),
            "mean_z_mm": float(per_axis[:, 2].mean() * 1000),
        }
    return {"forward": stats(fwd_arr), "smoothed": stats(smo_arr)}


def main():
    print("Sim EKF — physics-EKF (forward + RTS smoother) vs batch fit")
    print(f"  N_MC = {N_MC}, realistic occlusion @ 100 Hz\n", flush=True)
    rows = []
    for i, s in enumerate(range(1500, 1500 + N_MC)):
        r = run_one(s)
        rows.append(r)
        fwd = r["forward"]; smo = r["smoothed"]
        print(f"  [{i+1:2d}/{N_MC}]  fwd RMS={fwd['rms_3d_mm']:6.1f}  "
              f"smoothed RMS={smo['rms_3d_mm']:6.1f}  "
              f"Δ={fwd['rms_3d_mm']-smo['rms_3d_mm']:+5.1f} mm", flush=True)

    fwd_rms = np.array([r["forward"]["rms_3d_mm"] for r in rows])
    smo_rms = np.array([r["smoothed"]["rms_3d_mm"] for r in rows])
    fwd_x = np.array([r["forward"]["mean_x_mm"] for r in rows])
    fwd_y = np.array([r["forward"]["mean_y_mm"] for r in rows])
    fwd_z = np.array([r["forward"]["mean_z_mm"] for r in rows])
    smo_x = np.array([r["smoothed"]["mean_x_mm"] for r in rows])
    smo_y = np.array([r["smoothed"]["mean_y_mm"] for r in rows])
    smo_z = np.array([r["smoothed"]["mean_z_mm"] for r in rows])

    print("\nPer-delivery RMS 3D (mm):")
    print(f"  forward  : mean={fwd_rms.mean():5.1f}  med={np.median(fwd_rms):5.1f}  p95={np.percentile(fwd_rms,95):5.1f}")
    print(f"  smoothed : mean={smo_rms.mean():5.1f}  med={np.median(smo_rms):5.1f}  p95={np.percentile(smo_rms,95):5.1f}")
    print(f"  batch fit (reference): mean=41.0  med=35.0  p95=78.0")
    print("\nPer-axis |err| (mm):")
    print(f"  forward  : x={fwd_x.mean():5.1f}  y={fwd_y.mean():5.1f}  z={fwd_z.mean():5.1f}")
    print(f"  smoothed : x={smo_x.mean():5.1f}  y={smo_y.mean():5.1f}  z={smo_z.mean():5.1f}")

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.boxplot([fwd_rms, smo_rms], widths=0.6, patch_artist=True,
                tick_labels=["EKF forward", "EKF + RTS smoother"])
    ax.axhline(41, color="purple", ls="--", label="batch fit baseline (~41 mm)")
    ax.set_ylabel("Per-delivery RMS 3D (mm)")
    ax.set_title("Sim EKF — forward vs RTS-smoothed, realistic occlusion @ 100 Hz")
    ax.grid(alpha=0.3, axis="y"); ax.legend()
    plt.tight_layout()
    out = "outputs/sim_ekf.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\n  Saved: {out}", flush=True)


if __name__ == "__main__":
    main()
