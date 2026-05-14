"""LBW pipeline: impact detection, extrapolation, covariance, verdict."""

import numpy as np

from infinity_stumps import (
    assess_lbw,
    detect_impact,
    extrapolate_to_stumps,
    find_bounce,
    fit_covariance,
    lbw_verdict,
    stump_line_covariance,
)
from infinity_stumps.lbw import STUMP_HALF_W, STUMP_TOP_H

# ---------- impact detection ----------


def test_detect_impact_finds_first_spike():
    times = np.linspace(0.0, 1.0, 101)
    accel = np.full(101, 1.0)
    accel[40] = 80.0  # pad strike
    accel[60] = 250.0  # later bat strike
    assert detect_impact(times, accel) == times[40]


def test_detect_impact_returns_none_without_spike():
    times = np.linspace(0.0, 1.0, 101)
    accel = np.full(101, 2.0)
    assert detect_impact(times, accel) is None


# ---------- forward extrapolation ----------


def test_extrapolate_reaches_stump_line(standard_delivery):
    release_pos, v0, spin = standard_delivery
    result = extrapolate_to_stumps(release_pos, v0, spin)
    assert result is not None
    t_cross, yz = result
    assert t_cross > 0.0
    assert yz.shape == (2,)
    assert np.all(np.isfinite(yz))


def test_extrapolate_returns_none_when_never_crossing():
    # Ball travelling away from the stump line never crosses it.
    result = extrapolate_to_stumps(
        np.array([0.0, 0.0, 1.0]),
        np.array([-5.0, 0.0, 2.0]),
        np.zeros(3),
        t_max=0.5,
    )
    assert result is None


# ---------- bounce ----------


def test_find_bounce_locates_pitch_contact(standard_delivery):
    release_pos, v0, spin = standard_delivery
    bounce_xy = find_bounce(release_pos, v0, spin)
    assert bounce_xy is not None
    assert bounce_xy.shape == (2,)
    assert -2.0 < bounce_xy[0] < 9.0  # lands on the pitch strip


def test_find_bounce_returns_none_before_first_contact(standard_delivery):
    release_pos, v0, spin = standard_delivery
    # Too short a window to reach the ground.
    assert find_bounce(release_pos, v0, spin, t_max=0.1) is None


# ---------- covariance ----------


def test_fit_covariance_well_conditioned(rng):
    jac = rng.normal(size=(40, 9))
    residuals = rng.normal(size=40)
    cov = fit_covariance(jac, residuals)
    assert cov is not None
    assert cov.shape == (9, 9)
    assert np.allclose(cov, cov.T)


def test_fit_covariance_none_when_underdetermined(rng):
    jac = rng.normal(size=(5, 9))  # fewer observations than parameters
    residuals = rng.normal(size=5)
    assert fit_covariance(jac, residuals) is None


def test_stump_line_covariance_is_2x2(standard_delivery):
    release_pos, v0, spin = standard_delivery
    params = np.concatenate([release_pos, v0, spin])
    param_cov = np.diag(np.full(9, 0.01))
    cov = stump_line_covariance(params, param_cov)
    assert cov is not None
    assert cov.shape == (2, 2)
    assert np.all(np.isfinite(cov))


# ---------- verdict ----------


def test_verdict_hitting_when_centre_inside_with_tiny_uncertainty():
    yz = np.array([0.0, 0.3])  # dead centre of the stumps
    cov = np.diag([1e-8, 1e-8])
    assert lbw_verdict(yz, cov).decision == "HITTING"


def test_verdict_missing_when_centre_far_outside():
    yz = np.array([1.0, 0.3])  # well wide of the stumps
    cov = np.diag([1e-8, 1e-8])
    assert lbw_verdict(yz, cov).decision == "MISSING"


def test_verdict_umpires_call_when_ellipse_straddles_edge():
    yz = np.array([STUMP_HALF_W, 0.35])  # centred on the stump edge
    cov = np.diag([0.04**2, 0.04**2])
    verdict = lbw_verdict(yz, cov)
    assert verdict.decision == "UMPIRE'S CALL"
    assert verdict.ellipse_semi_axes[0] > 0.0


def test_verdict_binary_without_covariance():
    inside = lbw_verdict(np.array([0.0, 0.3]), None)
    outside = lbw_verdict(np.array([1.0, 0.3]), None)
    assert inside.decision == "HITTING"
    assert outside.decision == "MISSING"
    assert inside.yz_cov is None


# ---------- full assessment ----------


def test_assess_lbw_returns_structured_verdict(standard_delivery):
    release_pos, v0, spin = standard_delivery
    impact_pos = np.array([0.0, 0.0, 0.3])
    assessment = assess_lbw(release_pos, v0, spin, impact_pos)
    assert isinstance(assessment.out, bool)
    assert isinstance(assessment.impact_in_line, bool)
    assert assessment.stump_line.decision in {
        "HITTING",
        "MISSING",
        "UMPIRE'S CALL",
    }


def test_assess_lbw_not_out_when_impact_outside_line(standard_delivery):
    release_pos, v0, spin = standard_delivery
    impact_pos = np.array([0.0, 0.5, 0.3])  # struck well outside the line
    assessment = assess_lbw(release_pos, v0, spin, impact_pos)
    assert assessment.impact_in_line is False
    assert assessment.out is False


def test_stump_geometry_constants_sane():
    assert 0.0 < STUMP_HALF_W < 0.2
    assert 0.6 < STUMP_TOP_H < 0.8
