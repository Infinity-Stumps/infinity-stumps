"""Sim 05b — Mitigations for occlusion / NLOS bias.

Sim 05 showed that biased NLOS ranges destroy the trajectory fit
(225 mm RMS vs 10 mm clean-LOS). Two standard fixes:

  1. Robust loss in least-squares (Huber). Outliers get diminishing
     influence — needs no extra hardware signal, just a solver flag.
  2. NLOS detection at the UWB chip. Real chips (DW3110 incl.) expose
     channel-quality metrics; we model a detector with
     p_detect=0.85 (true positive on NLOS) and p_fp=0.02 (false positive
     on clean LOS). Detected NLOS ranges are dropped before they reach
     the solver.

Three scenarios compared:
  - Baseline       : no detection, lm loss              (= sim 05)
  - Robust only    : no detection, huber loss
  - NLOS + robust  : detection + huber loss
"""

from __future__ import annotations
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from cricket_uwb import (ANCHORS_8, RANGE_SIGMA_DEFAULT,
                          solve_position, fit_trajectory)
from cricket_uwb.physics import integrate_trajectory, make_delivery

# Reuse the cylinder geometry from sim 05
import sys, importlib.util
_spec = importlib.util.spec_from_file_location(
    "sim05", __file__.replace("05b_occlusion_mitigations.py",
                               "05_multipath_occlusion.py"))
sim05 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sim05)


P_DETECT = 0.85
P_FP = 0.02
HUBER_FSCALE = 3.0   # in units of sigma_pos (residuals are /sigma_pos)


def occluded_ranges_with_detection(true_pos, anchors, occluders, rng,
                                    p_detect: float, p_fp: float):
    """Like sim05.occluded_ranges, but with NLOS detector."""
    n = len(anchors)
    true_r = np.linalg.norm(anchors - true_pos, axis=1)
    noisy = np.zeros(n)
    for i, anchor in enumerate(anchors):
        is_blocked = any(sim05.cylinder_blocks(anchor, true_pos, occ)
                         for occ in occluders)
        if not is_blocked:
            if rng.random() < p_fp:
                noisy[i] = np.nan
            else:
                noisy[i] = true_r[i] + rng.normal(0.0, RANGE_SIGMA_DEFAULT)
        else:
            # 50/50 between hard-drop and biased survival
            if rng.random() < sim05.DROP_PROB:
                noisy[i] = np.nan
            else:
                if rng.random() < p_detect:
                    noisy[i] = np.nan
                else:
                    noisy[i] = (true_r[i] + rng.uniform(*sim05.NLOS_BIAS)
                                + rng.normal(0.0, sim05.SIGMA_NLOS))
    return noisy


def measure_trajectory(times, positions, anchors, seed, p_detect, p_fp):
    rng = np.random.default_rng(seed)
    meas_t, meas_p = [], []
    last = None
    static = sim05.static_occluders()
    for t, true_pos in zip(times, positions):
        occluders = static + [sim05.bowler_at(t)]
        ranges = occluded_ranges_with_detection(
            true_pos, anchors, occluders, rng, p_detect, p_fp)
        if (~np.isnan(ranges)).sum() < 4:
            continue
        x0 = (true_pos + rng.normal(0, 0.05, 3)) if last is None else last
        try:
            est = solve_position(ranges, anchors, x0)
        except Exception:
            continue
        meas_t.append(t); meas_p.append(est); last = est
    return np.array(meas_t), np.array(meas_p)


def run_scenario(scenario_name, seed, p_detect, p_fp, loss, f_scale):
    rp, v0, spin = make_delivery(speed_mps=38.0)
    ts, st = integrate_trajectory(rp, v0, spin)
    sample_t = np.arange(0.01, ts[-1]-0.01, 0.002)
    idx = np.clip(np.searchsorted(ts, sample_t), 0, len(ts)-1)
    sample_p = st[idx, :3]
    meas_t, meas_p = measure_trajectory(sample_t, sample_p, ANCHORS_8,
                                         seed, p_detect, p_fp)
    if len(meas_t) < 20:
        return float("nan"), 0
    idx_m = np.clip(np.searchsorted(ts, meas_t), 0, len(ts)-1)
    truth = st[idx_m, :3]
    fitted, _ = fit_trajectory(meas_t, meas_p, loss=loss, f_scale=f_scale)
    err = fitted - truth
    rms = float(np.sqrt((err**2).sum(axis=1)).mean() * 1000)
    return rms, len(meas_t)


def main():
    print("\nSim 05b — occlusion mitigations\n", flush=True)
    scenarios = [
        ("baseline (no det, lm)",         0.0,       0.0,  "linear", 1.0),
        ("robust only (huber, no det)",   0.0,       0.0,  "huber",  HUBER_FSCALE),
        ("NLOS det + huber",              P_DETECT,  P_FP, "huber",  HUBER_FSCALE),
        ("perfect det + huber",           1.0,       0.0,  "huber",  HUBER_FSCALE),
    ]
    n_mc = 8
    results = {}
    for name, pd, pfp, loss, fs in scenarios:
        print(f"  Scenario: {name}", flush=True)
        rmss = []
        for s in range(n_mc):
            rms, n_fixes = run_scenario(name, 100+s, pd, pfp, loss, fs)
            if not np.isnan(rms):
                rmss.append(rms)
            print(f"    [{s+1}/{n_mc}] fixes={n_fixes:3d}  RMS = "
                  f"{'fail' if np.isnan(rms) else f'{rms:7.1f} mm'}",
                  flush=True)
        rmss = np.array(rmss)
        results[name] = rmss
        print(f"    -> mean={rmss.mean():.1f}  median={np.median(rmss):.1f} "
              f"  p95={np.percentile(rmss,95):.1f} mm  (n={len(rmss)})\n",
              flush=True)

    print("\nSUMMARY")
    print("-" * 60)
    print(f"  {'scenario':35s} {'mean':>8s} {'median':>8s} {'p95':>8s}")
    for name, rmss in results.items():
        print(f"  {name:35s} {rmss.mean():>7.1f}  "
              f"{np.median(rmss):>7.1f}  {np.percentile(rmss,95):>7.1f}")
    print(f"\n  Clean-LOS baseline: ~10 mm")
    print(f"  DRS target:         <40 mm")

    fig, ax = plt.subplots(figsize=(11, 6))
    pos = np.arange(len(results))
    labels = list(results.keys())
    data = [results[k] for k in labels]
    bp = ax.boxplot(data, positions=pos, widths=0.6, patch_artist=True,
                    labels=[l.replace(" (", "\n(") for l in labels])
    for patch, c in zip(bp["boxes"], ["#c44", "#e88", "#48a", "#4a4"]):
        patch.set_facecolor(c); patch.set_alpha(0.7)
    ax.axhline(10, color="green", ls="--", label="clean-LOS baseline")
    ax.axhline(40, color="orange", ls="--", label="DRS target ceiling")
    ax.set_ylabel("Fit 3D RMS (mm)")
    ax.set_yscale("log")
    ax.set_title(f"Sim 05b — occlusion mitigations (n={n_mc} deliveries each)")
    ax.legend(); ax.grid(alpha=0.3, axis="y", which="both")
    out = "outputs/sim05b_mitigations.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    main()
