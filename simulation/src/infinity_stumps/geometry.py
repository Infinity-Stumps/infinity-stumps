"""
Cricket pitch geometry and anchor placements.

Coordinate system:
  X = along pitch (bowler end negative, batter end positive)
  Y = across pitch (off side negative for right-handed batter)
  Z = vertically up from pitch surface
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

# Pitch dimensions (metres)
STUMP_W: float = 0.2286  # 9 inches
STUMP_HEIGHT: float = 0.711
STUMP_TOP: float = 0.680  # anchor sits just below the bail
STUMP_MID: float = 0.340
PITCH_HL: float = 10.06  # half pitch length
PAI_X: float = 7.62  # PAI longitudinal (2.44 m in from stumps)
PAI_Y: float = 1.53  # PAI lateral offset


ANCHORS_8: NDArray[np.float64] = np.array(
    [
        [-PITCH_HL, -STUMP_W / 2, STUMP_TOP],  # A1 bowler off stump top
        [-PITCH_HL, +STUMP_W / 2, STUMP_TOP],  # A2 bowler leg stump top
        [-PAI_X, -PAI_Y, 0.0],  # A3 bowler PAI off
        [-PAI_X, +PAI_Y, 0.0],  # A4 bowler PAI leg
        [+PAI_X, -PAI_Y, 0.0],  # A5 batter PAI off
        [+PAI_X, +PAI_Y, 0.0],  # A6 batter PAI leg
        [+PITCH_HL, -STUMP_W / 2, STUMP_TOP],  # A7 batter off stump top
        [+PITCH_HL, +STUMP_W / 2, STUMP_TOP],  # A8 batter leg stump top
    ]
)

# 12-anchor upgrade — kept for completeness, sim 02 showed <2% benefit
ANCHORS_12: NDArray[np.float64] = np.vstack(
    [
        ANCHORS_8,
        np.array(
            [
                [-PITCH_HL, -STUMP_W / 2, STUMP_MID],
                [-PITCH_HL, +STUMP_W / 2, STUMP_MID],
                [+PITCH_HL, -STUMP_W / 2, STUMP_MID],
                [+PITCH_HL, +STUMP_W / 2, STUMP_MID],
            ]
        ),
    ]
)


def gdop(
    true_pos: NDArray[np.float64], anchors: NDArray[np.float64] = ANCHORS_8
) -> float:
    """Geometric Dilution of Precision at a position.

    Multiplier from per-anchor ranging σ to 3D position σ.
    GDOP=1 excellent, GDOP=2 doubles error, GDOP=10+ unusable.
    """
    diffs = anchors - true_pos
    dists = np.linalg.norm(diffs, axis=1, keepdims=True)
    if np.any(dists < 1e-9):
        return float("nan")
    H = diffs / dists
    try:
        Q = np.linalg.inv(H.T @ H)
        return float(np.sqrt(np.trace(Q)))
    except np.linalg.LinAlgError:
        return float("nan")


def gdop_map(
    z: float,
    anchors: NDArray[np.float64] = ANCHORS_8,
    x_range: tuple[float, float] = (-12, 12),
    y_range: tuple[float, float] = (-3, 3),
    resolution: int = 50,
) -> tuple[NDArray, NDArray, NDArray]:
    """GDOP across a horizontal slice at height z."""
    xs = np.linspace(*x_range, resolution)
    ys = np.linspace(*y_range, max(resolution // 2, 10))
    grid = np.zeros((len(ys), len(xs)))
    for i, y in enumerate(ys):
        for j, x in enumerate(xs):
            grid[i, j] = gdop(np.array([x, y, z]), anchors)
    return xs, ys, grid
