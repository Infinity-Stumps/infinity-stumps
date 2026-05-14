"""Ball flight dynamics: gravity, drag, Magnus, bounce."""

import numpy as np
import pytest

from infinity_stumps import BallParams, integrate_trajectory, make_delivery


def test_cross_section_is_pi_r_squared():
    params = BallParams()
    assert params.cross_section == np.pi * params.radius**2


def test_pure_gravity_fall_matches_analytic():
    # With drag and Magnus disabled, z(t) = z0 - 0.5 g t^2.
    params = BallParams(Cd=0.0, CL_coef=0.0)
    ts, states = integrate_trajectory(
        np.array([0.0, 0.0, 2.0]),
        np.zeros(3),
        np.zeros(3),
        t_max=0.5,
        dt=1e-4,
        params=params,
    )
    idx = np.searchsorted(ts, 0.2)
    expected_z = 2.0 - 0.5 * 9.81 * 0.2**2
    assert abs(states[idx, 2] - expected_z) < 0.02


def test_energy_conserved_without_drag_or_magnus():
    # Gravity-only flight (no bounce) must conserve KE + PE.
    params = BallParams(Cd=0.0, CL_coef=0.0)
    release = np.array([0.0, 0.0, 3.0])
    v0 = np.array([5.0, 0.0, 2.0])
    ts, states = integrate_trajectory(
        release, v0, np.zeros(3), t_max=0.4, dt=1e-3, params=params
    )

    def energy(state: np.ndarray) -> float:
        speed_sq = float(state[3:6] @ state[3:6])
        return 0.5 * params.mass * speed_sq + params.mass * 9.81 * state[2]

    e0, e1 = energy(states[0]), energy(states[-1])
    assert abs(e1 - e0) / e0 < 1e-3


def test_drag_decelerates_horizontal_motion():
    release = np.array([0.0, 0.0, 2.0])
    v0 = np.array([30.0, 0.0, 0.0])
    no_drag = integrate_trajectory(
        release, v0, np.zeros(3), t_max=0.3, params=BallParams(Cd=0.0, CL_coef=0.0)
    )[1]
    with_drag = integrate_trajectory(
        release, v0, np.zeros(3), t_max=0.3, params=BallParams(Cd=0.4, CL_coef=0.0)
    )[1]
    # Drag can only remove horizontal momentum.
    assert with_drag[-1, 3] < no_drag[-1, 3]
    assert with_drag[-1, 0] < no_drag[-1, 0]


def test_magnus_deflects_trajectory_sideways():
    release = np.array([0.0, 0.0, 2.0])
    v0 = np.array([30.0, 0.0, 0.0])
    spin = np.array([0.0, 0.0, 200.0])  # spin about vertical -> sideways force
    no_spin = integrate_trajectory(release, v0, np.zeros(3), t_max=0.3)[1]
    with_spin = integrate_trajectory(release, v0, spin, t_max=0.3)[1]
    # Without spin, y stays ~0; with spin it deviates measurably.
    assert abs(no_spin[-1, 1]) < 1e-6
    assert abs(with_spin[-1, 1]) > 0.01


def test_bounce_clamps_z_and_reverses_vertical_velocity():
    release_pos, v0, spin = make_delivery(speed_mps=38.0)
    ts, states = integrate_trajectory(release_pos, v0, spin)
    # z never goes below the ground.
    assert states[:, 2].min() >= -1e-9
    # There is a sample where z == 0 and the ball is then moving upward.
    bounce_idx = next(
        (
            i
            for i in range(1, len(states))
            if states[i, 2] == 0.0 and states[i - 1, 2] > 0.0
        ),
        None,
    )
    assert bounce_idx is not None
    assert states[bounce_idx, 5] > 0.0  # vz flipped upward


def test_bounce_loses_energy_via_restitution():
    # Vertical speed just after bounce ~= cor_vertical * speed just before.
    params = BallParams()
    release_pos, v0, spin = make_delivery(speed_mps=38.0)
    ts, states = integrate_trajectory(release_pos, v0, spin, params=params)
    bounce_idx = next(
        i
        for i in range(1, len(states))
        if states[i, 2] == 0.0 and states[i - 1, 2] > 0.0
    )
    vz_before = abs(states[bounce_idx - 1, 5])
    vz_after = abs(states[bounce_idx, 5])
    assert vz_after < vz_before
    assert vz_after == pytest.approx(params.cor_vertical * vz_before, rel=0.15)


def test_make_delivery_respects_inputs():
    release_pos, v0, spin = make_delivery(
        speed_mps=40.0, release_height=2.3, release_x=-8.5
    )
    assert release_pos[2] == 2.3
    assert release_pos[0] == -8.5
    # Direction vector isn't perfectly normalised (sub-ppm), so allow slack.
    assert np.linalg.norm(v0) == pytest.approx(40.0, rel=1e-3)


def test_make_delivery_bounces_on_the_pitch():
    release_pos, v0, spin = make_delivery(speed_mps=38.0)
    ts, states = integrate_trajectory(release_pos, v0, spin)
    bounce_idx = next(
        i
        for i in range(1, len(states))
        if states[i, 2] == 0.0 and states[i - 1, 2] > 0.0
    )
    # Bounce lands on the pitch strip, not behind the bowler or past the stumps.
    assert -2.0 < states[bounce_idx, 0] < 9.0
