"""Tests for the core modules. Run with: pytest -q"""
import numpy as np
import pytest

from cricket_uwb import (
    ANCHORS_8, ANCHORS_12, RANGE_SIGMA_DEFAULT,
    solve_position, fit_trajectory, gdop,
    integrate_trajectory, add_range_noise, BallParams, make_delivery,
)
from cricket_uwb.geometry import PITCH_HL, PAI_X, STUMP_TOP


def test_anchor_count():
    assert ANCHORS_8.shape == (8, 3)
    assert ANCHORS_12.shape == (12, 3)


def test_anchor_geometry_known_values():
    stump_z = {a[2] for a in ANCHORS_8 if abs(abs(a[0]) - PITCH_HL) < 1e-6}
    assert STUMP_TOP in stump_z
    pai_x = {abs(a[0]) for a in ANCHORS_8 if a[2] == 0.0}
    assert pai_x == {PAI_X}


def test_gdop_modest_above_pitch():
    g = gdop(np.array([0.0, 0.0, 1.5]))
    assert 1.0 < g < 10.0


def test_gdop_singular_at_anchor():
    g = gdop(ANCHORS_8[0])
    assert np.isnan(g) or g > 100


def test_ball_falls_under_gravity():
    params = BallParams(Cd=0.0, CL_coef=0.0)
    ts, states = integrate_trajectory(np.array([0.0, 0.0, 2.0]),
                                       np.zeros(3), np.zeros(3),
                                       t_max=0.5, dt=0.0001, params=params)
    idx = np.searchsorted(ts, 0.2)
    expected_z = 2.0 - 0.5 * 9.81 * 0.2**2
    assert abs(states[idx, 2] - expected_z) < 0.02


def test_delivery_bounces_on_pitch():
    rp, v0, spin = make_delivery(speed_mps=38.0)
    ts, states = integrate_trajectory(rp, v0, spin, t_max=0.85)
    bounce_idx = next((i for i in range(1, len(states))
                       if states[i, 2] == 0 and states[i-1, 2] > 0), None)
    assert bounce_idx is not None
    assert -2 < states[bounce_idx, 0] < 9


def test_perfect_ranges_give_exact_position():
    target = np.array([1.0, 0.5, 1.5])
    ranges = np.linalg.norm(ANCHORS_8 - target, axis=1)
    est = solve_position(ranges, ANCHORS_8, x0=target + 0.1)
    assert np.allclose(est, target, atol=1e-5)


def test_fit_improves_on_noisy_raw():
    rp, v0, spin = make_delivery(speed_mps=38.0)
    ts, states = integrate_trajectory(rp, v0, spin)
    sample_t = np.arange(0.01, ts[-1]-0.01, 0.002)
    idx = np.clip(np.searchsorted(ts, sample_t), 0, len(ts)-1)
    clean = states[idx, :3]
    rng = np.random.default_rng(42)
    noisy = clean + rng.normal(0, 0.1, clean.shape)
    fitted, _ = fit_trajectory(sample_t, noisy)
    raw_rms = np.sqrt(((noisy - clean)**2).sum(axis=1)).mean()
    fit_rms = np.sqrt(((fitted - clean)**2).sum(axis=1)).mean()
    assert fit_rms < raw_rms / 2
