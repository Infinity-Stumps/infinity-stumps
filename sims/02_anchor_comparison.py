"""Sim 02 — 8 vs 12 anchor comparison. Decision: stick with 8."""
from __future__ import annotations
import numpy as np
import matplotlib.pyplot as plt

from cricket_uwb import (ANCHORS_8, ANCHORS_12, RANGE_SIGMA_DEFAULT,
                          solve_position, add_range_noise)


def monte_carlo(true_pos, anchors, n_trials=500, seed=None):
    rng = np.random.default_rng(seed)
    errors = np.zeros((n_trials, 3))
    true_r = np.linalg.norm(anchors - true_pos, axis=1)
    for i in range(n_trials):
        measured = add_range_noise(true_r, rng=rng)
        x0 = true_pos + rng.normal(0, 0.1, 3)
        errors[i] = solve_position(measured, anchors, x0) - true_pos
    return errors


def main():
    test_points = [
        ("Bowler release (high)",   np.array([-9.5,  0.0, 2.2])),
        ("Mid-pitch (1.5 m)",       np.array([ 0.0,  0.0, 1.5])),
        ("Mid-pitch low (0.5 m)",   np.array([ 0.0,  0.0, 0.5])),
        ("Good length bounce",      np.array([ 6.0,  0.0, 0.0])),
        ("At batter stumps mid",    np.array([ 9.8,  0.0, 0.4])),
        ("Wide of off",             np.array([ 8.0, -1.2, 1.0])),
    ]
    print(f"\nSim 02 — 8 vs 12 anchor\n")
    rms8, rms12, names = [], [], []
    for i, (name, pos) in enumerate(test_points):
        e8 = monte_carlo(pos, ANCHORS_8, seed=42+i)
        e12 = monte_carlo(pos, ANCHORS_12, seed=42+i)
        r8 = np.sqrt((e8**2).sum(axis=1)).mean()*1000
        r12 = np.sqrt((e12**2).sum(axis=1)).mean()*1000
        rms8.append(r8); rms12.append(r12); names.append(name)
        print(f"  {name:25s} 8a={r8:6.1f}  12a={r12:6.1f}  "
              f"impr={r8/r12:.2f}×")

    fig, ax = plt.subplots(figsize=(11, 6))
    y = np.arange(len(names)); w = 0.35
    ax.barh(y-w/2, rms8, w, label="8 anchors", color="#c44", edgecolor="k")
    ax.barh(y+w/2, rms12, w, label="12 anchors", color="#48a", edgecolor="k")
    ax.axvline(20, color="green", ls="--", label="20 mm target")
    ax.set_yticks(y); ax.set_yticklabels(names); ax.invert_yaxis()
    ax.set_xlabel("3D RMS (mm)"); ax.set_title("Sim 02 — 8 vs 12 anchor")
    ax.legend(); ax.grid(alpha=0.3, axis="x")
    out = "outputs/sim02_anchor_comparison.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\n  Saved: {out}")
    print("  CONCLUSION: 12-anchor gives marginal raw improvement. Stick with 8.")


if __name__ == "__main__":
    main()
