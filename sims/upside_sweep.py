"""Upside sweep — three potential gains over the sim 05b baseline.

Sim 05b (TWR + Huber + 85% NLOS detection under occlusion) gave us
47 mm at 500 Hz → ~65 mm at the operational 100 Hz rate. This script
tests three upside levers as quick variations on that baseline:

  A) Tighter per-range σ      — chip calibration tooling (20 mm vs 30 mm)
  B) Multi-channel diversity  — run Ch5 + Ch9, take best LOS
  C) Alternative geometry     — move stump-tops off-axis, or add 9th anchor

Each is run on the same occlusion model from sim 05, same Huber-loss
trajectory fit, same NLOS detection model. Only one variable changes
per sweep.

All sims at the operational 100 Hz rate. Numbers reported are
directly meaningful — no √5 scaling needed.
"""

from __future__ import annotations

import importlib.util

import matplotlib.pyplot as plt
import numpy as np

from infinity_stumps import (
    ANCHORS_8,
    RANGE_SIGMA_DEFAULT,
    fit_trajectory,
    solve_position,
)
from infinity_stumps.geometry import (
    PAI_X,
    PAI_Y,
    PITCH_HL,
    STUMP_MID,
    STUMP_TOP,
    STUMP_W,
)
from infinity_stumps.physics import integrate_trajectory, make_delivery

_spec = importlib.util.spec_from_file_location(
    "sim05", __file__.replace("upside_sweep.py", "05_multipath_occlusion.py")
)
sim05 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sim05)


P_DETECT = 0.85
P_FP = 0.02
HUBER_FSCALE = 3.0
N_MC = 6


def measure_with_detect(true_pos, anchors, occluders, rng, sigma_los, p_detect, p_fp):
    """Single-channel occluded measurement with NLOS detection."""
    n = len(anchors)
    true_r = np.linalg.norm(anchors - true_pos, axis=1)
    noisy = np.zeros(n)
    for i, anchor in enumerate(anchors):
        is_blocked = any(
            sim05.cylinder_blocks(anchor, true_pos, occ) for occ in occluders
        )
        if not is_blocked:
            if rng.random() < p_fp:
                noisy[i] = np.nan
            else:
                noisy[i] = true_r[i] + rng.normal(0.0, sigma_los)
        else:
            if rng.random() < sim05.DROP_PROB:
                noisy[i] = np.nan
            else:
                if rng.random() < p_detect:
                    noisy[i] = np.nan
                else:
                    noisy[i] = (
                        true_r[i]
                        + rng.uniform(*sim05.NLOS_BIAS)
                        + rng.normal(0.0, sim05.SIGMA_NLOS)
                    )
    return noisy


def measure_multichannel(
    true_pos, anchors, occluders, rng, sigma_los, p_detect, p_fp, nlos_correlation
):
    """Two-channel measurement with channel-correlated NLOS events.

    Each channel has independent NLOS detection (TPR=p_detect, FPR=p_fp).
    NLOS events between channels are partially correlated:
      - Geometric occlusion (cylinder blocks the line) is shared
        (correlation = 1.0 for that part)
      - Stochastic dropout vs bias choice and signal-strength variability
        is partially independent (correlation = nlos_correlation)
    Best of two channels: if either is LOS-detected and valid, use it.
    If both NLOS-detected, drop. If both biased-and-undetected, average.
    """
    n = len(anchors)
    true_r = np.linalg.norm(anchors - true_pos, axis=1)
    result = np.zeros(n)
    for i, anchor in enumerate(anchors):
        is_blocked = any(
            sim05.cylinder_blocks(anchor, true_pos, occ) for occ in occluders
        )
        ch_vals = []
        # Sample two per-channel "luck" values with correlation `nlos_correlation`
        u_ch0 = rng.random()
        u_ch1 = nlos_correlation * u_ch0 + (1 - nlos_correlation) * rng.random()
        u_per_ch = [u_ch0, u_ch1]
        for ch in range(2):
            if not is_blocked:
                if rng.random() < p_fp:
                    ch_vals.append(np.nan)
                else:
                    ch_vals.append(true_r[i] + rng.normal(0.0, sigma_los))
            else:
                u = u_per_ch[ch]
                if u < sim05.DROP_PROB:
                    ch_vals.append(np.nan)
                elif rng.random() < p_detect:
                    ch_vals.append(np.nan)
                else:
                    ch_vals.append(
                        true_r[i]
                        + rng.uniform(*sim05.NLOS_BIAS)
                        + rng.normal(0.0, sim05.SIGMA_NLOS)
                    )
        valid = [v for v in ch_vals if not np.isnan(v)]
        if not valid:
            result[i] = np.nan
        elif len(valid) == 1:
            result[i] = valid[0]
        else:
            result[i] = np.mean(valid)
    return result


def run_one(anchors, sigma_los, multichannel, nlos_correlation, seed):
    rp, v0, spin = make_delivery(speed_mps=38.0)
    ts, st = integrate_trajectory(rp, v0, spin)
    sample_t = np.arange(0.01, ts[-1] - 0.01, 0.01)  # 100 Hz operational
    idx = np.clip(np.searchsorted(ts, sample_t), 0, len(ts) - 1)
    sample_p = st[idx, :3]

    rng = np.random.default_rng(seed)
    meas_t, meas_p = [], []
    last = None
    static = sim05.static_occluders()
    for t, true_pos in zip(sample_t, sample_p):
        occluders = static + [sim05.bowler_at(t)]
        if multichannel:
            ranges = measure_multichannel(
                true_pos,
                anchors,
                occluders,
                rng,
                sigma_los,
                P_DETECT,
                P_FP,
                nlos_correlation,
            )
        else:
            ranges = measure_with_detect(
                true_pos, anchors, occluders, rng, sigma_los, P_DETECT, P_FP
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
    meas_t = np.array(meas_t)
    meas_p = np.array(meas_p)
    if len(meas_t) < 50:
        return float("nan")
    idx_m = np.clip(np.searchsorted(ts, meas_t), 0, len(ts) - 1)
    truth_m = st[idx_m, :3]
    fitted, _ = fit_trajectory(meas_t, meas_p, loss="huber", f_scale=HUBER_FSCALE)
    err = fitted - truth_m
    return float(np.sqrt((err**2).sum(axis=1)).mean() * 1000)


# ---------- alternative geometries ----------

ANCHORS_BASELINE = ANCHORS_8

ANCHORS_OFFAXIS = np.array(
    [
        [-PITCH_HL, -STUMP_W / 2 - 0.20, STUMP_TOP],  # A1 bowler off, +20cm off-axis
        [-PITCH_HL, +STUMP_W / 2 + 0.20, STUMP_TOP],  # A2 bowler leg, +20cm off-axis
        [-PAI_X, -PAI_Y, 0.0],
        [-PAI_X, +PAI_Y, 0.0],
        [+PAI_X, -PAI_Y, 0.0],
        [+PAI_X, +PAI_Y, 0.0],
        [+PITCH_HL, -STUMP_W / 2 - 0.20, STUMP_TOP],  # A7 batter off, +20cm
        [+PITCH_HL, +STUMP_W / 2 + 0.20, STUMP_TOP],  # A8 batter leg, +20cm
    ]
)

ANCHORS_9 = np.vstack(
    [
        ANCHORS_8,
        np.array([[0.0, 0.0, 2.5]]),  # 9th anchor: mid-pitch elevated
    ]
)


# ---------- main sweep ----------


def sweep(name, anchors, sigma_los, multichannel=False, nlos_correlation=0.5):
    rmss = []
    for s in range(N_MC):
        r = run_one(anchors, sigma_los, multichannel, nlos_correlation, seed=900 + s)
        if not np.isnan(r):
            rmss.append(r)
        print(
            f"    [{s + 1}/{N_MC}] {r:6.1f} mm"
            if not np.isnan(r)
            else f"    [{s + 1}/{N_MC}] fail",
            flush=True,
        )
    return np.array(rmss)


def main():
    print("\nUpside Sweep — 3 levers on sim 05b baseline\n", flush=True)
    print(
        f"  Baseline: sim 05b config "
        f"(σ={RANGE_SIGMA_DEFAULT * 1000:.0f} mm, 8 anchors, single channel)",
        flush=True,
    )
    print("  Operating point: TWR + Huber + 85% NLOS detection under occlusion")
    print(
        "  All scenarios run at 500 Hz internal (gains scale identically to 100 Hz)\n",
        flush=True,
    )

    results = {}

    print("Baseline reproduction (sim 05b)")
    results["BASELINE"] = sweep("baseline", ANCHORS_BASELINE, RANGE_SIGMA_DEFAULT)
    print()

    print("Lever A: tighter per-range σ (the realistic points)")
    for sigma_mm in [20, 15]:
        key = f"A-σ={sigma_mm}mm"
        print(f"  σ = {sigma_mm} mm")
        results[key] = sweep(key, ANCHORS_BASELINE, sigma_mm / 1000.0)
    print()

    print("Lever B: multi-channel — realistic NLOS correlation")
    for rho in [0.3, 0.5]:
        key = f"B-rho={rho}"
        print(f"  NLOS correlation rho = {rho}")
        results[key] = sweep(
            key,
            ANCHORS_BASELINE,
            RANGE_SIGMA_DEFAULT,
            multichannel=True,
            nlos_correlation=rho,
        )
    print()

    # Lever C (anchor geometry) removed — stump positions are fixed by
    # Law 8 (Cricket) and a 9th anchor mid-pitch on a pole is physically
    # nonsensical. Geometry is not a free variable in this product.

    # ---------- summary ----------
    print("\nSUMMARY")
    print("-" * 70)
    print(f"  {'config':25s} {'mean':>7s} {'med':>7s} {'p95':>7s}  vs baseline")
    base = results["BASELINE"].mean()
    for key, arr in results.items():
        if len(arr) == 0:
            print(f"  {key:25s} all-fail")
            continue
        ratio = arr.mean() / base
        improvement = (1 - ratio) * 100
        sign = "improvement" if improvement > 0 else "REGRESSION"
        print(
            f"  {key:25s} {arr.mean():>6.1f}  "
            f"{np.median(arr):>6.1f}  {np.percentile(arr, 95):>6.1f}  "
            f"{improvement:+5.1f}%  ({sign})"
        )

    print(f"\n  Baseline (mean): {base:.1f} mm at 500 Hz")
    print(f"  Scaling to 100 Hz operational: × √5 = {base * np.sqrt(5):.0f} mm")

    # Plot box-plot of all conditions
    fig, ax = plt.subplots(figsize=(13, 6))
    labels = list(results.keys())
    data = [results[k] for k in labels]
    bp = ax.boxplot(data, widths=0.6, patch_artist=True, tick_labels=labels)
    for patch, k in zip(bp["boxes"], labels):
        if k == "BASELINE":
            patch.set_facecolor("#888")
        elif k.startswith("A"):
            patch.set_facecolor("#4a8")
        elif k.startswith("B"):
            patch.set_facecolor("#48a")
        elif k.startswith("C"):
            patch.set_facecolor("#a84")
        patch.set_alpha(0.7)
    ax.axhline(base, color="black", ls="--", lw=1, label=f"baseline {base:.0f}mm")
    ax.set_ylabel("Fit 3D RMS (mm) at 500 Hz")
    ax.set_title("Upside sweep — tighter σ vs multichannel vs geometry")
    ax.tick_params(axis="x", rotation=30, labelsize=8)
    ax.grid(alpha=0.3, axis="y")
    ax.legend()
    plt.tight_layout()
    out = "outputs/upside_sweep.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\n  Saved: {out}", flush=True)


if __name__ == "__main__":
    main()
