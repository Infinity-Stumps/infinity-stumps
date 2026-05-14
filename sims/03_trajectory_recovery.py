"""Sim 03 — Headline: full trajectory recovery with physics fit.

Noise model is TWR (each anchor produces an independent noisy range).
This matches the deployed architecture per CLAUDE.md decision 4 (TWR
at ~150 Hz, not TDoA at 500 Hz — see sim 07 for why).

This sim still runs at 500 Hz internally to show the physics-fit
headroom; at 150 Hz the same fit would land at ~17 mm RMS instead of
~10 mm (scales as 1/sqrt(N) in the sample count).
"""
from __future__ import annotations
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.gridspec import GridSpec

from cricket_uwb import (ANCHORS_8, RANGE_SIGMA_DEFAULT,
                          solve_position, fit_trajectory, add_range_noise)
from cricket_uwb.physics import integrate_trajectory, make_delivery
from cricket_uwb.geometry import PITCH_HL, STUMP_HEIGHT


def measure_trajectory(positions, anchors=ANCHORS_8,
                       sigma=RANGE_SIGMA_DEFAULT, seed=42):
    rng = np.random.default_rng(seed)
    noisy = np.zeros_like(positions)
    last = None
    for i, p in enumerate(positions):
        true_r = np.linalg.norm(anchors - p, axis=1)
        meas = add_range_noise(true_r, sigma=sigma, rng=rng)
        x0 = p + rng.normal(0, 0.05, 3) if last is None else last
        noisy[i] = solve_position(meas, anchors, x0)
        last = noisy[i]
    return noisy


def main():
    print("\nSim 03 — trajectory recovery with physics fit\n")
    release_pos, v0, spin = make_delivery(speed_mps=38.0)
    ts_true, st_true = integrate_trajectory(release_pos, v0, spin)
    true_pos = st_true[:, :3]

    sample_times = np.arange(0.01, ts_true[-1]-0.01, 0.002)
    idx = np.clip(np.searchsorted(ts_true, sample_times), 0, len(ts_true)-1)
    sample_pos = true_pos[idx]

    noisy_pos = measure_trajectory(sample_pos)
    raw_err = noisy_pos - sample_pos
    raw_rms = np.sqrt((raw_err**2).sum(axis=1)).mean() * 1000
    print(f"  Raw multilateration RMS: {raw_rms:.1f} mm")
    print(f"  Raw σ: X={raw_err[:,0].std()*1000:.1f} "
          f"Y={raw_err[:,1].std()*1000:.1f} Z={raw_err[:,2].std()*1000:.1f}")

    fitted, params_fit = fit_trajectory(sample_times, noisy_pos)
    fit_err = fitted - sample_pos
    fit_rms = np.sqrt((fit_err**2).sum(axis=1)).mean() * 1000
    print(f"  Physics-fit RMS: {fit_rms:.1f} mm")
    print(f"  Fit σ: X={fit_err[:,0].std()*1000:.1f} "
          f"Y={fit_err[:,1].std()*1000:.1f} Z={fit_err[:,2].std()*1000:.1f}")
    print(f"  Improvement: {raw_rms/fit_rms:.2f}×")
    print(f"  Target 10–20 mm: {'ACHIEVED ✓' if fit_rms < 20 else 'NOT MET ✗'}")

    fig = plt.figure(figsize=(16, 8))
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.3)

    ax = fig.add_subplot(gs[0, 0]); ax.set_aspect("equal")
    ax.add_patch(patches.Rectangle((-PITCH_HL, -1.525), 2*PITCH_HL, 3.05,
                                    facecolor="#d4a574", alpha=0.3))
    ax.plot(true_pos[:, 0], true_pos[:, 1], "g-", lw=2, label="True")
    ax.scatter(noisy_pos[:, 0], noisy_pos[:, 1], c="red", s=3, alpha=0.4, label="Raw")
    ax.plot(fitted[:, 0], fitted[:, 1], "b-", lw=1.5, label="Fit")
    ax.scatter(ANCHORS_8[:, 0], ANCHORS_8[:, 1], c="k", s=20, marker="s")
    ax.set_xlim(-11, 11); ax.set_ylim(-2, 2)
    ax.set_xlabel("X (m)"); ax.set_ylabel("Y (m)")
    ax.set_title("Top down"); ax.legend(fontsize=8); ax.grid(alpha=0.3)

    ax = fig.add_subplot(gs[0, 1])
    ax.plot(true_pos[:, 0], true_pos[:, 2], "g-", lw=2, label="True")
    ax.scatter(noisy_pos[:, 0], noisy_pos[:, 2], c="red", s=3, alpha=0.4, label="Raw")
    ax.plot(fitted[:, 0], fitted[:, 2], "b-", lw=1.5, label="Fit")
    ax.axhline(0, color="#8b6f47", lw=2)
    for x_end in [-PITCH_HL, PITCH_HL]:
        ax.plot([x_end, x_end], [0, STUMP_HEIGHT], color="saddlebrown", lw=2)
    ax.set_xlim(-11, 11); ax.set_ylim(-0.2, 3)
    ax.set_xlabel("X (m)"); ax.set_ylabel("Z (m)")
    ax.set_title("Side view"); ax.legend(fontsize=8); ax.grid(alpha=0.3)

    ax = fig.add_subplot(gs[0, 2])
    for col, c, name in [(0, "r", "X"), (1, "g", "Y"), (2, "b", "Z")]:
        ax.plot(sample_times*1000, fit_err[:, col]*1000, color=c, lw=1,
                label=f"{name} σ={fit_err[:,col].std()*1000:.1f}mm")
    ax.axhspan(-20, 20, color="green", alpha=0.15)
    ax.set_xlabel("Time (ms)"); ax.set_ylabel("Error (mm)")
    ax.set_title("Post-fit error"); ax.legend(fontsize=8); ax.grid(alpha=0.3)

    ax = fig.add_subplot(gs[1, 0])
    bins = np.linspace(0, 300, 40)
    raw_3d = np.sqrt((raw_err**2).sum(axis=1)) * 1000
    fit_3d = np.sqrt((fit_err**2).sum(axis=1)) * 1000
    ax.hist(raw_3d, bins=bins, alpha=0.5, color="red", label="Raw", edgecolor="k")
    ax.hist(fit_3d, bins=bins, alpha=0.8, color="blue", label="Fit", edgecolor="k")
    ax.axvline(20, color="green", ls="--", label="20mm")
    ax.set_xlabel("3D error (mm)"); ax.set_ylabel("Count")
    ax.set_title("Error distribution"); ax.legend(); ax.grid(alpha=0.3, axis="y")

    ax = fig.add_subplot(gs[1, 1:]); ax.axis("off")
    ax.text(0.0, 0.5,
            f"SIM 03 RESULTS\n{'-'*60}\n"
            f"Config: 8 anchors, {RANGE_SIGMA_DEFAULT*1000:.0f}mm σ, 500 Hz\n"
            f"Delivery: {np.linalg.norm(v0):.1f} m/s, "
            f"{np.linalg.norm(spin)/(2*np.pi):.1f} rev/s\n"
            f"Samples: {len(sample_times)}  Duration: {sample_times[-1]:.2f}s\n\n"
            f"Raw multilateration   RMS = {raw_rms:6.1f} mm\n"
            f"Physics-fit recovery  RMS = {fit_rms:6.1f} mm\n"
            f"Improvement           {raw_rms/fit_rms:.2f}×\n\n"
            f"Target 10-20mm: {'ACHIEVED ✓' if fit_rms < 20 else 'NOT MET ✗'}\n"
            "The precision comes from the physics fit, not the anchor\n"
            "geometry. This is the patentable core IP of the system.",
            transform=ax.transAxes, family="monospace", fontsize=10,
            verticalalignment="center")
    fig.suptitle("Sim 03 — Trajectory recovery with physics-constrained fit",
                 fontsize=13)
    out = "outputs/sim03_trajectory_recovery.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    main()
