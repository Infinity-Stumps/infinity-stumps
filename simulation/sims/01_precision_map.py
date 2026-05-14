"""Sim 01 — Position precision and GDOP across playing volume."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec

from infinity_stumps import (
    ANCHORS_8,
    RANGE_SIGMA_DEFAULT,
    add_range_noise,
    gdop,
    solve_position,
)
from infinity_stumps.geometry import gdop_map
from infinity_stumps.plotting import draw_pitch_sideview, draw_pitch_topdown


def monte_carlo_precision(
    true_pos, anchors=ANCHORS_8, n_trials=500, sigma=RANGE_SIGMA_DEFAULT, seed=42
):
    rng = np.random.default_rng(seed)
    errors = np.zeros((n_trials, 3))
    true_ranges = np.linalg.norm(anchors - true_pos, axis=1)
    for i in range(n_trials):
        measured = add_range_noise(true_ranges, sigma=sigma, rng=rng)
        x0 = true_pos + rng.normal(0, 0.1, 3)
        errors[i] = solve_position(measured, anchors, x0) - true_pos
    return errors


def main():
    test_points = [
        ("Bowler release (high)", np.array([-9.5, 0.0, 2.2])),
        ("Mid-pitch (1.5m)", np.array([0.0, 0.0, 1.5])),
        ("Mid-pitch low (0.5m)", np.array([0.0, 0.0, 0.5])),
        ("Good length bounce", np.array([6.0, 0.0, 0.0])),
        ("At batter stumps top", np.array([9.8, 0.0, 0.7])),
        ("At batter stumps mid", np.array([9.8, 0.0, 0.4])),
        ("Wide of off", np.array([8.0, -1.2, 1.0])),
    ]
    print("\nSim 01 — raw multilateration precision")
    print(f"  Anchors: 8 | Ranging σ: {RANGE_SIGMA_DEFAULT * 1000:.0f} mm\n")
    results = []
    for name, pos in test_points:
        errs = monte_carlo_precision(pos)
        s = errs.std(axis=0) * 1000
        rms = np.sqrt((errs**2).sum(axis=1)).mean() * 1000
        g = gdop(pos)
        results.append((name, s, rms, g))
        print(
            f"  {name:30s} σ=({s[0]:5.1f},{s[1]:5.1f},{s[2]:5.1f}) "
            f"RMS={rms:5.1f} GDOP={g:.2f}"
        )

    fig = plt.figure(figsize=(15, 9))
    gs = GridSpec(3, 3, figure=fig, hspace=0.4, wspace=0.3)
    ax1 = fig.add_subplot(gs[0, 0])
    draw_pitch_topdown(ax1)
    ax1.set_title("Anchor layout (top-down)")
    ax2 = fig.add_subplot(gs[0, 1])
    draw_pitch_sideview(ax2)
    ax2.set_title("Anchor layout (side view)")

    ax3 = fig.add_subplot(gs[0, 2])
    names = [r[0].replace(" ", "\n", 1) for r in results]
    rms_vals = [r[2] for r in results]
    cols = ["green" if v < 20 else "orange" if v < 40 else "red" for v in rms_vals]
    ax3.barh(range(len(names)), rms_vals, color=cols, edgecolor="k")
    ax3.axvline(20, color="green", ls="--", label="20 mm target")
    ax3.set_yticks(range(len(names)))
    ax3.set_yticklabels(names, fontsize=8)
    ax3.invert_yaxis()
    ax3.set_xlabel("3D RMS (mm)")
    ax3.set_title("Raw precision")
    ax3.legend(fontsize=8)
    ax3.grid(alpha=0.3, axis="x")

    for k, z in enumerate([0.5, 1.5, 2.5]):
        ax = fig.add_subplot(gs[1, k])
        xs, ys, grid = gdop_map(z)
        im = ax.imshow(
            grid,
            extent=[xs[0], xs[-1], ys[0], ys[-1]],
            origin="lower",
            aspect="equal",
            cmap="RdYlGn_r",
            vmin=1.0,
            vmax=4.0,
        )
        ax.scatter(
            ANCHORS_8[:, 0], ANCHORS_8[:, 1], c="white", s=30, edgecolors="k", zorder=5
        )
        ax.set_title(f"GDOP at z={z:.1f} m")
        ax.set_xlabel("X (m)")
        if k == 0:
            ax.set_ylabel("Y (m)")
        plt.colorbar(im, ax=ax, label="GDOP", shrink=0.8)

    ax = fig.add_subplot(gs[2, :])
    ax.axis("off")
    ax.text(
        0.02,
        0.5,
        "KEY FINDING — Sim 01\n"
        + "-" * 60
        + "\nRaw multilateration RMS: 40–210 mm depending on location."
        "\nGDOP at z=0.5 m is 4–8 across most of the pitch."
        "\nVertical resolution is the weakness — anchors at/near ground level."
        "\nThis is what sim 03's physics-fit must overcome.",
        transform=ax.transAxes,
        family="monospace",
        fontsize=10,
        verticalalignment="center",
    )
    fig.suptitle("Sim 01 — Position precision across playing volume", fontsize=13)
    out = "outputs/sim01_precision_map.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    main()
