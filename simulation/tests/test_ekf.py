"""Trajectory EKF and the RTS backward smoother."""

import numpy as np

from infinity_stumps import EKFConfig, TrajectoryEKF, integrate_trajectory


def test_initialise_sets_state_and_default_covariance():
    ekf = TrajectoryEKF()
    x0 = np.arange(9, dtype=float)
    ekf.initialise(t=0.0, x0=x0)
    assert np.array_equal(ekf.state, x0)
    assert ekf.P.shape == (9, 9)
    # Default covariance is diagonal from the configured sigmas.
    cfg = EKFConfig()
    assert ekf.P[0, 0] == cfg.sigma0_pos**2
    assert ekf.P[3, 3] == cfg.sigma0_vel**2
    assert ekf.P[6, 6] == cfg.sigma0_spin**2
    # One history snapshot recorded at init.
    assert len(ekf.history_state) == 1


def test_predict_noop_when_time_does_not_advance():
    ekf = TrajectoryEKF()
    ekf.initialise(t=1.0, x0=np.zeros(9))
    ekf.predict(1.0)
    assert ekf.t == 1.0
    assert len(ekf.history_state) == 1


def test_predict_matches_direct_integration(standard_delivery):
    release_pos, v0, spin = standard_delivery
    ekf = TrajectoryEKF()
    ekf.initialise(t=0.0, x0=np.concatenate([release_pos, v0, spin]))
    ekf.predict(0.1)  # before bounce

    ts, states = integrate_trajectory(release_pos, v0, spin, t_max=0.1)
    # EKF state propagation should agree with the standalone integrator.
    assert np.allclose(ekf.state[:6], states[-1], atol=0.02)


def test_predict_grows_position_covariance(standard_delivery):
    release_pos, v0, spin = standard_delivery
    ekf = TrajectoryEKF()
    ekf.initialise(t=0.0, x0=np.concatenate([release_pos, v0, spin]))
    pos_var_before = np.trace(ekf.P[:3, :3])
    ekf.predict(0.05)
    # With no measurements, velocity uncertainty integrates into position.
    assert np.trace(ekf.P[:3, :3]) > pos_var_before


def test_range_update_shrinks_covariance(standard_delivery, anchors):
    release_pos, v0, spin = standard_delivery
    ts, states = integrate_trajectory(release_pos, v0, spin)
    true_pos = np.array([np.interp(0.05, ts, states[:, d]) for d in range(3)])

    ekf = TrajectoryEKF()
    ekf.initialise(t=0.0, x0=np.concatenate([release_pos, v0, spin]))
    ekf.predict(0.05)
    trace_predicted = np.trace(ekf.P)
    for anchor in anchors:
        ekf.update_range(anchor, float(np.linalg.norm(true_pos - anchor)))
    # A full ring of range measurements must tighten the estimate.
    assert np.trace(ekf.P) < trace_predicted


def test_ekf_tracks_a_noisy_delivery(standard_delivery, anchors, rng):
    release_pos, v0, spin = standard_delivery
    ts, states = integrate_trajectory(release_pos, v0, spin)
    sample_t = np.arange(0.03, ts[-1] - 0.03, 0.01)
    true_pos = np.column_stack(
        [np.interp(sample_t, ts, states[:, d]) for d in range(3)]
    )

    ekf = TrajectoryEKF()
    x0 = np.concatenate([release_pos, v0, spin])
    x0[:6] += rng.normal(0, 0.1, 6)  # deliberately imperfect initial guess
    ekf.initialise(t=0.0, x0=x0)

    estimates = []
    for i, t in enumerate(sample_t):
        ekf.predict(float(t))
        for anchor in anchors:
            true_range = float(np.linalg.norm(true_pos[i] - anchor))
            ekf.update_range(anchor, true_range + rng.normal(0, 0.03))
        estimates.append(ekf.state[:3].copy())

    errors = np.linalg.norm(np.array(estimates) - true_pos, axis=1)
    # Once converged, clean-LOS tracking error stays well under 15 cm.
    assert errors[len(errors) // 2 :].mean() < 0.15


def test_rts_smoother_trivial_with_short_history():
    ekf = TrajectoryEKF()
    ekf.initialise(t=0.0, x0=np.zeros(9))
    ekf.smooth_backward()
    assert len(ekf.smoothed_state) == 1


def test_rts_smoother_matches_filter_at_final_sample(standard_delivery, anchors, rng):
    release_pos, v0, spin = standard_delivery
    ts, states = integrate_trajectory(release_pos, v0, spin)
    sample_t = np.arange(0.03, ts[-1] - 0.03, 0.01)
    true_pos = np.column_stack(
        [np.interp(sample_t, ts, states[:, d]) for d in range(3)]
    )

    ekf = TrajectoryEKF()
    ekf.initialise(t=0.0, x0=np.concatenate([release_pos, v0, spin]))
    for i, t in enumerate(sample_t):
        ekf.predict(float(t))
        for anchor in anchors:
            true_range = float(np.linalg.norm(true_pos[i] - anchor))
            ekf.update_range(anchor, true_range + rng.normal(0, 0.03))

    ekf.smooth_backward()
    assert len(ekf.smoothed_state) == len(ekf.history_state)
    # RTS leaves the final sample unchanged; earlier ones are revised.
    np.testing.assert_allclose(ekf.smoothed_state[-1], ekf.history_state[-1])


def test_rts_smoother_does_not_inflate_covariance(standard_delivery, anchors, rng):
    release_pos, v0, spin = standard_delivery
    ts, states = integrate_trajectory(release_pos, v0, spin)
    sample_t = np.arange(0.03, ts[-1] - 0.03, 0.01)
    true_pos = np.column_stack(
        [np.interp(sample_t, ts, states[:, d]) for d in range(3)]
    )

    ekf = TrajectoryEKF()
    ekf.initialise(t=0.0, x0=np.concatenate([release_pos, v0, spin]))
    for i, t in enumerate(sample_t):
        ekf.predict(float(t))
        for anchor in anchors:
            true_range = float(np.linalg.norm(true_pos[i] - anchor))
            ekf.update_range(anchor, true_range + rng.normal(0, 0.03))

    ekf.smooth_backward()
    # Smoothing folds in future data, so covariance never grows.
    k = len(ekf.history_P) // 3
    assert np.trace(ekf.smoothed_P[k]) <= np.trace(ekf.history_P[k]) + 1e-9
