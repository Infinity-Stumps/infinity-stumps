"""Sim 06 — IMU fusion: body-frame model with attitude integration.

The ball carries a 6-axis IMU at 1 kHz. Real IMUs report in BODY frame
(rotates with the ball), so to use the accelerometer for world-frame
motion we have to integrate the gyro to track attitude.

The ball spins at ~25 rev/s = 157 rad/s = 9000 °/s in flight. That
saturates standard ±2000 °/s consumer gyros — this sim assumes a
high-range gyro (±10,000 °/s) such as Murata SCC or ICM-45686.

Pipeline:
  1. Generate ground-truth trajectory (sim 03 reuse)
  2. Generate body-frame IMU measurements:
       accel_body(t) = R(t)^T * (a_world(t) + g_world)
       gyro_body(t)  = R(t)^T * omega_world
     where R(t) is ground-truth attitude, omega_world is spin axis,
     g_world = [0,0,+9.81] (specific force convention)
     Add noise per spec: σ_a, σ_g, plus slow bias random walk
  3. Estimator side (strapdown):
       integrate gyro_body to get R̂(t) (with errors from bias+noise)
       a_world_est = R̂(t) * accel_body - g_world
       integrate a_world_est → vel̂(t) → poŝ(t)
     poŝ drifts as t^3 from gyro errors (uncorrected)
  4. Complementary fusion with UWB: each UWB fix snaps the IMU
     position estimate toward measured. Tunable gain alpha.
  5. Physics fit on fused trajectory.

Compares:
  - UWB only, clean LOS
  - UWB only, occlusion (sim 05b baseline)
  - UWB + body-frame IMU, clean LOS
  - UWB + body-frame IMU, occlusion
  - UWB + zero-noise IMU (upper bound)
"""

from __future__ import annotations

import importlib.util

import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial.transform import Rotation

from infinity_stumps import (
    ANCHORS_8,
    RANGE_SIGMA_DEFAULT,
    fit_trajectory,
    solve_position,
)
from infinity_stumps.physics import integrate_trajectory, make_delivery

_spec = importlib.util.spec_from_file_location(
    "sim05", __file__.replace("06_imu_fusion.py", "05_multipath_occlusion.py")
)
sim05 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sim05)


# Sensor specs — high-range gyro + good MEMS accel
SIGMA_A = 0.05  # m/s², 1 kHz BW
SIGMA_G = 0.005  # rad/s — high-range gyro typical
BIAS_A_PSD = 0.003  # m/s²/sqrt(s)
BIAS_G_PSD = 0.0005  # rad/s/sqrt(s)
IMU_RATE = 1000.0
G_WORLD = np.array([0.0, 0.0, 9.81])  # specific-force sign convention


def attitude_at(t, omega_world, R0):
    """R(t) given constant world-frame angular velocity omega_world."""
    angle = np.linalg.norm(omega_world) * t
    if angle < 1e-9:
        return R0
    axis = omega_world / np.linalg.norm(omega_world)
    R_t = Rotation.from_rotvec(axis * angle).as_matrix()
    return R_t @ R0


def simulate_imu_body(ts_truth, states_truth, omega_world, R0, seed, perfect=False):
    """Body-frame IMU sim. Returns t_imu, accel_body, gyro_body."""
    rng = np.random.default_rng(seed)
    t_imu = np.arange(ts_truth[0], ts_truth[-1], 1.0 / IMU_RATE)
    N = len(t_imu)
    dt_imu = 1.0 / IMU_RATE

    # World-frame accel from numerical derivative of velocity truth
    vel_truth = states_truth[:, 3:6]
    vel_at_imu = np.zeros((N, 3))
    for d in range(3):
        vel_at_imu[:, d] = np.interp(t_imu, ts_truth, vel_truth[:, d])
    a_world = np.zeros_like(vel_at_imu)
    a_world[1:] = np.diff(vel_at_imu, axis=0) / dt_imu
    a_world[0] = a_world[1]

    accel_body = np.zeros((N, 3))
    gyro_body = np.zeros((N, 3))
    for k in range(N):
        R_t = attitude_at(t_imu[k], omega_world, R0)
        # Specific force (what accel measures) in world = a_world + g_world
        f_world = a_world[k] + G_WORLD
        accel_body[k] = R_t.T @ f_world
        gyro_body[k] = R_t.T @ omega_world

    if perfect:
        return t_imu, accel_body, gyro_body

    bias_a = np.cumsum(rng.normal(0, BIAS_A_PSD * np.sqrt(dt_imu), (N, 3)), axis=0)
    bias_g = np.cumsum(rng.normal(0, BIAS_G_PSD * np.sqrt(dt_imu), (N, 3)), axis=0)
    accel_body_meas = accel_body + bias_a + rng.normal(0, SIGMA_A, (N, 3))
    gyro_body_meas = gyro_body + bias_g + rng.normal(0, SIGMA_G, (N, 3))
    return t_imu, accel_body_meas, gyro_body_meas


def strapdown_with_uwb_fusion(
    t_imu,
    accel_body,
    gyro_body,
    t_uwb,
    pos_uwb,
    R0_est,
    p0,
    v0,
    alpha_pos=0.10,
    alpha_R=0.02,
):
    """Strapdown INS + complementary UWB fusion.

    State: position, velocity, attitude (rotation matrix).
    Propagate via IMU at each step. On UWB fix, blend pos toward
    measurement; also tilt-correct attitude using accel-derived
    gravity direction when ball is roughly in free fall.

    Returns pos_est over t_imu.
    """
    N = len(t_imu)
    pos = np.zeros((N, 3))
    vel = np.zeros((N, 3))
    R = R0_est.copy()
    pos[0] = p0
    vel[0] = v0
    dt = 1.0 / IMU_RATE
    uwb_idx = 0
    for k in range(1, N):
        # Attitude propagation (Rodrigues)
        omega = gyro_body[k - 1]
        ang = np.linalg.norm(omega) * dt
        if ang > 1e-9:
            axis = omega / np.linalg.norm(omega)
            dR = Rotation.from_rotvec(axis * ang).as_matrix()
            R = R @ dR
        # Convert body accel to world, subtract gravity
        a_world_est = R @ accel_body[k - 1] - G_WORLD
        # Newton step
        pos[k] = pos[k - 1] + vel[k - 1] * dt + 0.5 * a_world_est * dt**2
        vel[k] = vel[k - 1] + a_world_est * dt
        # Blend UWB fixes
        while uwb_idx < len(t_uwb) and t_uwb[uwb_idx] <= t_imu[k]:
            err = pos_uwb[uwb_idx] - pos[k]
            pos[k] = pos[k] + alpha_pos * err
            # Don't update vel from single fix — finite diff is too noisy
            uwb_idx += 1
    return pos


def measure_uwb(sample_t, sample_p, anchors=ANCHORS_8, occlusion=False, seed=42):
    rng = np.random.default_rng(seed)
    meas_t, meas_p = [], []
    last = None
    static = sim05.static_occluders() if occlusion else []
    for t, true_pos in zip(sample_t, sample_p):
        if occlusion:
            occluders = static + [sim05.bowler_at(t)]
            ranges, _ = sim05.occluded_ranges(true_pos, anchors, occluders, rng)
        else:
            ranges = np.linalg.norm(anchors - true_pos, axis=1) + rng.normal(
                0, RANGE_SIGMA_DEFAULT, len(anchors)
            )
        if (~np.isnan(ranges)).sum() < 4:
            continue
        x0 = (true_pos + rng.normal(0, 0.05, 3)) if last is None else last
        try:
            est = solve_position(ranges, anchors, x0)
        except Exception:
            continue
        meas_t.append(t)
        meas_p.append(est)
        last = est
    return np.array(meas_t), np.array(meas_p)


UWB_RATE_HZ = 100.0  # ETSI-compliant operational rate


def run_scenario(name, occlusion, use_imu, perfect_imu, seed):
    rp, v0_world, spin = make_delivery(speed_mps=38.0)
    ts, st = integrate_trajectory(rp, v0_world, spin)
    sample_t = np.arange(0.01, ts[-1] - 0.01, 1.0 / UWB_RATE_HZ)
    idx = np.clip(np.searchsorted(ts, sample_t), 0, len(ts) - 1)
    sample_p = st[idx, :3]

    meas_t, meas_p = measure_uwb(sample_t, sample_p, occlusion=occlusion, seed=seed)
    if len(meas_t) < 20:
        return float("nan")
    idx_m = np.clip(np.searchsorted(ts, meas_t), 0, len(ts) - 1)
    truth_m = st[idx_m, :3]

    if not use_imu:
        fitted, _ = fit_trajectory(meas_t, meas_p, loss="huber", f_scale=3.0)
    else:
        # IMU sim. Perfect initial attitude — realistic when ball is
        # held still pre-release and gyro is integrated from rest.
        R0 = np.eye(3)
        R0_est = R0.copy()
        t_imu, accel_b, gyro_b = simulate_imu_body(
            ts, st, spin, R0, seed=seed + 1, perfect=perfect_imu
        )
        # Initialise estimator from first UWB fix
        p0_est = meas_p[0]
        if len(meas_p) > 1:
            dt0 = meas_t[1] - meas_t[0]
            v0_est = (meas_p[1] - meas_p[0]) / dt0
        else:
            v0_est = v0_world
        # alpha_pos=0.5 — moderate UWB trust; IMU interpolates between
        # the now-sparser 100 Hz fixes (10 IMU samples per UWB cycle)
        fused_pos = strapdown_with_uwb_fusion(
            t_imu,
            accel_b,
            gyro_b,
            meas_t,
            meas_p,
            R0_est,
            p0_est,
            v0_est,
            alpha_pos=0.5,
        )
        idx_imu = np.clip(np.searchsorted(t_imu, meas_t), 0, len(t_imu) - 1)
        fused_at_meas = fused_pos[idx_imu]
        fitted, _ = fit_trajectory(meas_t, fused_at_meas, loss="huber", f_scale=3.0)

    err = fitted - truth_m
    return float(np.sqrt((err**2).sum(axis=1)).mean() * 1000)


def main():
    print("\nSim 06 — IMU fusion (body-frame, 100 Hz UWB)\n", flush=True)
    print(f"  UWB rate    : {int(UWB_RATE_HZ)} Hz (ETSI-compliant)")
    print(f"  IMU rate    : {int(IMU_RATE)} Hz")
    print(f"  Gyro σ      : {SIGMA_G} rad/s")
    print(f"  Accel σ     : {SIGMA_A} m/s²")
    print("  Spin rate   : 25 rev/s = 9000 °/s")
    print("  Init attitude error : 0° (perfect — best case)")
    print("  Fusion alpha: 0.5 (balanced UWB/IMU)\n", flush=True)

    scenarios = [
        ("UWB only,  clean LOS", False, False, False),
        ("UWB only,  occlusion", True, False, False),
        ("UWB+IMU,   clean LOS", False, True, False),
        ("UWB+IMU,   occlusion", True, True, False),
        ("UWB+pIMU,  occlusion (UB)", True, True, True),
    ]
    n_mc = 6
    results = {}
    for name, occ, imu, perfect in scenarios:
        print(f"  Scenario: {name}", flush=True)
        rmss = []
        for s in range(n_mc):
            r = run_scenario(name, occ, imu, perfect, seed=800 + s)
            if not np.isnan(r):
                rmss.append(r)
            print(
                f"    [{s + 1}/{n_mc}] RMS = "
                f"{'fail' if np.isnan(r) else f'{r:6.1f} mm'}",
                flush=True,
            )
        rmss = np.array(rmss)
        results[name] = rmss
        print(
            f"    -> mean={rmss.mean():.1f}  median={np.median(rmss):.1f}  "
            f"p95={np.percentile(rmss, 95):.1f} mm\n",
            flush=True,
        )

    print("\nSUMMARY")
    print("-" * 60)
    print(f"  {'scenario':32s} {'mean':>7s} {'med':>7s} {'p95':>7s}")
    for name, rmss in results.items():
        print(
            f"  {name:32s} {rmss.mean():>6.1f}  "
            f"{np.median(rmss):>6.1f}  {np.percentile(rmss, 95):>6.1f}"
        )

    fig, ax = plt.subplots(figsize=(12, 6))
    labels = list(results.keys())
    data = [results[k] for k in labels]
    bp = ax.boxplot(
        data,
        widths=0.6,
        patch_artist=True,
        tick_labels=[l.replace(", ", "\n") for l in labels],
    )
    for patch, c in zip(bp["boxes"], ["#4a4", "#c44", "#7a7", "#a48", "#48a"]):
        patch.set_alpha(0.7)
        patch.set_facecolor(c)
    ax.axhline(10, color="green", ls="--", label="clean baseline (sim 03)")
    ax.axhline(47, color="purple", ls="--", label="sim 05b occluded")
    ax.set_ylabel("Fit 3D RMS (mm)")
    ax.set_yscale("log")
    ax.set_title(f"Sim 06 — body-frame IMU fusion (n={n_mc} deliveries)")
    ax.legend()
    ax.grid(alpha=0.3, axis="y", which="both")
    plt.tight_layout()
    out = "outputs/sim06_imu_fusion.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\n  Saved: {out}", flush=True)


if __name__ == "__main__":
    main()
