"""Position solvers: multilateration and physics-constrained fit."""

import numpy as np
import pytest

from infinity_stumps import (
    fit_trajectory,
    integrate_trajectory,
    solve_position,
    solve_position_at_ground,
)


def test_perfect_ranges_give_exact_position(anchors):
    target = np.array([1.0, 0.5, 1.5])
    ranges = np.linalg.norm(anchors - target, axis=1)
    est = solve_position(ranges, anchors, x0=target + 0.1)
    assert np.allclose(est, target, atol=1e-5)


def test_solve_position_recovers_from_noise(anchors, rng):
    target = np.array([2.0, -0.3, 1.2])
    ranges = np.linalg.norm(anchors - target, axis=1)
    noisy = ranges + rng.normal(0, 0.03, ranges.shape)
    est = solve_position(noisy, anchors)
    assert np.linalg.norm(est - target) < 0.15


def test_solve_position_drops_nan_ranges(anchors):
    target = np.array([1.0, 0.5, 1.5])
    ranges = np.linalg.norm(anchors - target, axis=1)
    ranges[2] = np.nan  # one dropped anchor
    ranges[5] = np.nan
    est = solve_position(ranges, anchors, x0=target + 0.1)
    assert np.allclose(est, target, atol=1e-5)


def test_solve_position_needs_four_ranges(anchors):
    ranges = np.full(8, np.nan)
    ranges[:3] = 5.0
    with pytest.raises(ValueError, match="4 valid ranges"):
        solve_position(ranges, anchors)


def test_solve_position_at_ground_exact(anchors):
    target = np.array([2.0, 0.5, 0.0])
    ranges = np.linalg.norm(anchors - target, axis=1)
    est = solve_position_at_ground(ranges, anchors)
    assert np.allclose(est, target, atol=1e-5)
    assert est[2] == 0.0


def test_solve_position_at_ground_needs_three_ranges(anchors):
    ranges = np.full(8, np.nan)
    ranges[:2] = 5.0
    with pytest.raises(ValueError, match="3 valid ranges"):
        solve_position_at_ground(ranges, anchors)


def test_fit_trajectory_beats_raw_noise(standard_delivery, rng):
    release_pos, v0, spin = standard_delivery
    ts, states = integrate_trajectory(release_pos, v0, spin)
    sample_t = np.arange(0.01, ts[-1] - 0.01, 0.002)
    idx = np.clip(np.searchsorted(ts, sample_t), 0, len(ts) - 1)
    clean = states[idx, :3]
    noisy = clean + rng.normal(0, 0.1, clean.shape)

    fitted, params = fit_trajectory(sample_t, noisy)

    raw_rms = np.sqrt(((noisy - clean) ** 2).sum(axis=1)).mean()
    fit_rms = np.sqrt(((fitted - clean) ** 2).sum(axis=1)).mean()
    assert fit_rms < raw_rms / 2
    assert params.shape == (9,)


def test_fit_trajectory_recovers_clean_trajectory(standard_delivery):
    release_pos, v0, spin = standard_delivery
    ts, states = integrate_trajectory(release_pos, v0, spin)
    sample_t = np.arange(0.01, ts[-1] - 0.01, 0.002)
    idx = np.clip(np.searchsorted(ts, sample_t), 0, len(ts) - 1)
    clean = states[idx, :3]

    fitted, _ = fit_trajectory(sample_t, clean)

    # On noise-free input the physics fit should be near-exact.
    assert np.sqrt(((fitted - clean) ** 2).sum(axis=1)).mean() < 0.01


def test_fit_trajectory_accepts_bounce_constraint(standard_delivery, rng):
    release_pos, v0, spin = standard_delivery
    ts, states = integrate_trajectory(release_pos, v0, spin)
    sample_t = np.arange(0.01, ts[-1] - 0.01, 0.002)
    idx = np.clip(np.searchsorted(ts, sample_t), 0, len(ts) - 1)
    noisy = states[idx, :3] + rng.normal(0, 0.05, (len(sample_t), 3))

    # Bounce time: first z==0 sample.
    bounce_t = float(ts[np.argmax(states[:, 2] == 0.0)])
    fitted, params = fit_trajectory(sample_t, noisy, bounce_time=bounce_t)
    assert fitted.shape == (len(sample_t), 3)
    assert params.shape == (9,)
