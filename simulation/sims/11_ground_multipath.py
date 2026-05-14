"""Sim 11 — Outdoor multipath: ground reflections on the ranging itself.

The 30 mm σ assumption (sims 03 onwards) is from indoor characterisation
of the DW3110. Outdoors on a cricket pitch, the dominant unaccounted
effect is ground-reflection multipath:

  Ball at height h_b → anchor at height h_a, horizontal distance d_h
    LOS  path:  sqrt(d_h² + (h_b - h_a)²)
    Refl path:  sqrt(d_h² + (h_b + h_a)²)
    Δd = path_refl - path_LOS ≈ 2*h_b*h_a / d_h  (for d_h >> h's)

When Δd > UWB pulse width (~30 cm), the chip's first-path detector
resolves LOS cleanly. When Δd < ~30 cm, the reflection overlaps with
LOS and biases the timestamp toward the centroid.

Affects only the four stump-top anchors (z=0.68 m). The PAI anchors
are at z=0 — their ground reflection is into the ground, no effect.

Reflection coefficient: cricket pitch + outfield grass at 6.5 GHz ≈
0.15-0.30 depending on moisture, grass length, ground compaction.
Bias magnitude scales with this coefficient and inversely with Δd.

Compares fit RMS vs sim 03 baseline at 500 Hz.
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

PULSE_WIDTH_M = 0.30  # UWB pulse rough resolution
REFL_COEF_DRY = 0.15
REFL_COEF_WET = 0.30
SOFT_OVERLAP_M = 1.0  # within this Δd we model some interaction


def ground_multipath_bias(anchor_pos, ball_pos, refl_coef, rng):
    """Return additive range bias (m) from ground bounce.

    Δd small → unresolved overlap → bias ~ refl_coef × 0.5 × Δd
    Δd large → resolved cleanly → bias = 0
    In between → smoothly transitions.
    Sign of bias is approximately +ve (chip locks onto a centroid that
    is delayed vs the true LOS arrival). Add Gaussian on top reflecting
    constructive/destructive interference phase randomness.
    """
    h_a = anchor_pos[2]
    h_b = ball_pos[2]
    if h_a <= 0.01 or h_b <= 0.01:
        return 0.0
    dx, dy = anchor_pos[0] - ball_pos[0], anchor_pos[1] - ball_pos[1]
    d_h = float(np.hypot(dx, dy))
    if d_h < 0.5:
        return 0.0
    delta_d = np.sqrt(d_h**2 + (h_b + h_a) ** 2) - np.sqrt(d_h**2 + (h_b - h_a) ** 2)
    if delta_d > SOFT_OVERLAP_M:
        return 0.0
    overlap = max(0.0, (SOFT_OVERLAP_M - delta_d) / SOFT_OVERLAP_M)
    centroid_bias = refl_coef * 0.5 * delta_d * overlap
    phase_jitter = refl_coef * delta_d * overlap * rng.normal(0.0, 0.3)
    return centroid_bias + phase_jitter


def measure_trajectory_multipath(
    sample_t, sample_p, anchors=ANCHORS_8, refl_coef=REFL_COEF_DRY, seed=42
):
    rng = np.random.default_rng(seed)
    noisy = np.zeros_like(sample_p)
    last = None
    per_anchor_bias = [[] for _ in anchors]
    for k, true_pos in enumerate(sample_p):
        true_r = np.linalg.norm(anchors - true_pos, axis=1)
        biased = true_r.copy()
        for i, anchor in enumerate(anchors):
            b = ground_multipath_bias(anchor, true_pos, refl_coef, rng)
            biased[i] += b
            per_anchor_bias[i].append(b)
        meas = biased + rng.normal(0.0, RANGE_SIGMA_DEFAULT, len(anchors))
        x0 = (true_pos + rng.normal(0, 0.05, 3)) if last is None else last
        try:
            est = solve_position(meas, anchors, x0)
        except Exception:
            continue
        noisy[k] = est
        last = est
    return noisy, np.array(per_anchor_bias)


def run_scenario(refl_coef, seed):
    rp, v0, spin = make_delivery(speed_mps=38.0)
    ts, st = integrate_trajectory(rp, v0, spin)
    sample_t = np.arange(0.01, ts[-1] - 0.01, 0.002)
    idx = np.clip(np.searchsorted(ts, sample_t), 0, len(ts) - 1)
    sample_p = st[idx, :3]
    noisy, biases = measure_trajectory_multipath(
        sample_t, sample_p, refl_coef=refl_coef, seed=seed
    )
    raw_err = noisy - sample_p
    raw_rms = float(np.sqrt((raw_err**2).sum(axis=1)).mean() * 1000)
    fitted, _ = fit_trajectory(sample_t, noisy, loss="huber", f_scale=3.0)
    fit_err = fitted - sample_p
    fit_rms = float(np.sqrt((fit_err**2).sum(axis=1)).mean() * 1000)
    return raw_rms, fit_rms, sample_t, sample_p, noisy, fitted, biases


def main():
    print("\nSim 11 — Ground-reflection multipath on TWR ranging\n", flush=True)
    print(f"  UWB pulse width assumed:    {PULSE_WIDTH_M * 1000:.0f} mm")
    print(f"  Soft overlap distance:      {SOFT_OVERLAP_M * 1000:.0f} mm")
    print(f"  Reflection coef (dry):      {REFL_COEF_DRY}")
    print(f"  Reflection coef (wet):      {REFL_COEF_WET}\n", flush=True)

    scenarios = [
        ("baseline (no multipath)", 0.0),
        ("dry pitch (refl=0.15)", REFL_COEF_DRY),
        ("wet pitch (refl=0.30)", REFL_COEF_WET),
        ("worst case (refl=0.50)", 0.50),
    ]
    n_mc = 6
    results = {}
    for name, rc in scenarios:
        print(f"  Scenario: {name}", flush=True)
        raws, fits = [], []
        for s in range(n_mc):
            r, f, *_ = run_scenario(rc, seed=700 + s)
            raws.append(r)
            fits.append(f)
            print(f"    [{s + 1}/{n_mc}] raw={r:6.1f}  fit={f:6.1f} mm", flush=True)
        results[name] = (np.array(raws), np.array(fits))
        f_arr = results[name][1]
        print(
            f"    -> fit mean={f_arr.mean():.1f}  "
            f"median={np.median(f_arr):.1f}  "
            f"p95={np.percentile(f_arr, 95):.1f}\n",
            flush=True,
        )

    print("\nSUMMARY")
    print("-" * 70)
    print(
        f"  {'scenario':30s} {'raw mean':>10s} {'fit mean':>10s} "
        f"{'fit p95':>10s}  vs baseline"
    )
    base_fit = results["baseline (no multipath)"][1].mean()
    for name, (raw, fit) in results.items():
        ratio = fit.mean() / base_fit if base_fit > 0 else 0
        print(
            f"  {name:30s} {raw.mean():>9.1f}  {fit.mean():>9.1f}  "
            f"{np.percentile(fit, 95):>9.1f}  {ratio:.2f}×"
        )

    # Single-delivery deep dive (dry pitch)
    _, _, st_t, st_p, st_noisy, st_fit, st_biases = run_scenario(
        REFL_COEF_DRY, seed=700
    )

    fig = plt.figure(figsize=(15, 9))
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.3)

    # (1) Side view of trajectory
    ax = fig.add_subplot(gs[0, 0])
    ax.plot(st_p[:, 0], st_p[:, 2], "g-", lw=2, label="True")
    ax.scatter(
        st_noisy[:, 0],
        st_noisy[:, 2],
        c="red",
        s=3,
        alpha=0.4,
        label="Raw (with multipath bias)",
    )
    ax.plot(st_fit[:, 0], st_fit[:, 2], "b-", lw=1.5, label="Huber fit")
    ax.axhline(0, color="#8b6f47", lw=2)
    for xe in [-PITCH_HL, PITCH_HL]:
        ax.plot([xe, xe], [0, STUMP_HEIGHT], color="saddlebrown", lw=2)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Z (m)")
    ax.set_title("Side view — dry pitch")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    ax.set_xlim(-11, 11)
    ax.set_ylim(-0.2, 3)

    # (2) Per-anchor bias magnitude over time
    ax = fig.add_subplot(gs[0, 1:])
    for i in range(8):
        bz = st_biases[i, :] * 1000  # st_biases is (n_anchors, n_samples)
        if np.abs(bz).max() > 1:
            ax.plot(
                st_t * 1000, bz, lw=0.8, label=f"A{i + 1} (z={ANCHORS_8[i, 2]:.2f}m)"
            )
        else:
            ax.plot(st_t * 1000, bz, lw=0.5, alpha=0.3, color="grey")
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Ground-bounce bias (mm)")
    ax.set_title("Per-anchor multipath bias through flight (dry)")
    ax.legend(fontsize=7, ncol=2)
    ax.grid(alpha=0.3)

    # (3) Box plot of fit RMS by scenario
    ax = fig.add_subplot(gs[1, 0:2])
    labels = list(results.keys())
    fits = [results[k][1] for k in labels]
    bp = ax.boxplot(
        fits,
        widths=0.6,
        patch_artist=True,
        tick_labels=[l.replace(" (", "\n(") for l in labels],
    )
    for patch, c in zip(bp["boxes"], ["#4a4", "#7a4", "#c84", "#c44"]):
        patch.set_alpha(0.7)
        patch.set_facecolor(c)
    ax.axhline(10, color="green", ls="--", label="sim 03 baseline")
    ax.axhline(47, color="purple", ls="--", label="sim 05b (occlusion)")
    ax.set_ylabel("Fit 3D RMS (mm)")
    ax.set_yscale("log")
    ax.set_title("Sim 11 — ground multipath impact on fit precision")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y", which="both")

    # (4) Summary text
    ax = fig.add_subplot(gs[1, 2])
    ax.axis("off")
    dry_fit = results["dry pitch (refl=0.15)"][1].mean()
    wet_fit = results["wet pitch (refl=0.30)"][1].mean()
    worst_fit = results["worst case (refl=0.50)"][1].mean()
    ax.text(
        0.0,
        0.5,
        f"SIM 11 — GROUND MULTIPATH\n{'-' * 40}\n"
        f"Affects only stump-top anchors\n(A1, A2, A7, A8 at z=0.68m).\n"
        f"PAI anchors at z=0 see no\nground reflection.\n\n"
        f"Baseline fit:     {base_fit:6.1f} mm\n"
        f"Dry pitch:        {dry_fit:6.1f} mm "
        f"({dry_fit / base_fit:.2f}×)\n"
        f"Wet pitch:        {wet_fit:6.1f} mm "
        f"({wet_fit / base_fit:.2f}×)\n"
        f"Worst case:       {worst_fit:6.1f} mm "
        f"({worst_fit / base_fit:.2f}×)\n\n"
        f"Combined with sim 05b\n(occlusion + Huber + NLOS det):\n"
        f"  47 mm × {dry_fit / base_fit:.2f} ≈ "
        f"{47 * dry_fit / base_fit:.0f} mm dry\n"
        f"  47 mm × {wet_fit / base_fit:.2f} ≈ "
        f"{47 * wet_fit / base_fit:.0f} mm wet",
        transform=ax.transAxes,
        family="monospace",
        fontsize=9,
        verticalalignment="center",
    )

    fig.suptitle("Sim 11 — Outdoor multipath: ground reflections on TWR")
    out = "outputs/sim11_ground_multipath.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\n  Saved: {out}", flush=True)


if __name__ == "__main__":
    main()
