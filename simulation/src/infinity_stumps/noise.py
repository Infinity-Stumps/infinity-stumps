"""UWB ranging noise models."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

RANGE_SIGMA_DEFAULT: float = 0.030  # 30 mm 1σ — conservative DW3110 estimate


def add_range_noise(
    true_ranges: NDArray[np.float64],
    sigma: float = RANGE_SIGMA_DEFAULT,
    rng: np.random.Generator | None = None,
) -> NDArray[np.float64]:
    """Zero-mean Gaussian noise."""
    if rng is None:
        rng = np.random.default_rng()
    return true_ranges + rng.normal(0.0, sigma, size=true_ranges.shape)


def occluded_range_noise(
    true_ranges,
    anchor_positions,
    target_pos,
    occluders=None,
    sigma_los=RANGE_SIGMA_DEFAULT,
    sigma_nlos=0.10,
    nlos_bias_range=(0.05, 0.20),
    drop_prob_nlos=0.5,
    rng=None,
):
    """Occlusion-aware noise. Used by sim 05.

    occluders: list of (position, radius). Rays passing within `radius`
    of an occluder are flagged NLOS — either dropped (returning NaN)
    or biased.
    """
    if rng is None:
        rng = np.random.default_rng()
    if occluders is None:
        occluders = []
    n = len(true_ranges)
    noisy = np.zeros(n)
    is_los = np.ones(n, dtype=bool)
    for i in range(n):
        anchor = anchor_positions[i]
        ray = target_pos - anchor
        ray_len = float(np.linalg.norm(ray))
        ray_unit = ray / ray_len if ray_len > 0 else ray
        for occ_pos, occ_r in occluders:
            v = occ_pos - anchor
            t = float(np.dot(v, ray_unit))
            if t < 0 or t > ray_len:
                continue
            if float(np.linalg.norm(v - t * ray_unit)) < occ_r:
                is_los[i] = False
                break
        if is_los[i]:
            noisy[i] = true_ranges[i] + rng.normal(0, sigma_los)
        else:
            if rng.random() < drop_prob_nlos:
                noisy[i] = np.nan
            else:
                noisy[i] = (
                    true_ranges[i]
                    + rng.uniform(*nlos_bias_range)
                    + rng.normal(0, sigma_nlos)
                )
    return noisy, is_los
