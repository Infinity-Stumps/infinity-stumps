"""Position solvers — multilateration and physics-fit."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import least_squares

from .physics import BallParams, integrate_trajectory


def solve_position(
    measured_ranges: NDArray[np.float64],
    anchors: NDArray[np.float64],
    x0: NDArray[np.float64] | None = None,
) -> NDArray[np.float64]:
    """LM multilateration. Handles NaN ranges as dropped anchors."""
    valid = ~np.isnan(measured_ranges)
    if valid.sum() < 4:
        raise ValueError(f"Need ≥4 valid ranges; got {valid.sum()}")
    if x0 is None:
        x0 = np.mean(anchors, axis=0).copy()
        x0[2] = 1.0
    anchors_v = anchors[valid]
    ranges_v = measured_ranges[valid]

    def residuals(p):
        return np.linalg.norm(anchors_v - p, axis=1) - ranges_v

    return least_squares(residuals, x0, method="lm").x


def solve_position_at_ground(
    measured_ranges: NDArray[np.float64],
    anchors: NDArray[np.float64],
    x0_xy: NDArray[np.float64] | None = None,
    z_fixed: float = 0.0,
) -> NDArray[np.float64]:
    """2D multilateration with z fixed. Returns 3-vector [x, y, z_fixed].

    At the bounce moment we know z = 0 exactly. Solving 8 ranges for
    only (x, y) instead of (x, y, z) is dramatically more overdetermined
    (8 equations, 2 unknowns) and bypasses GDOP_z bleeding noise into
    the answer. Result: sharpest position estimate of the whole flight.
    """
    valid = ~np.isnan(measured_ranges)
    if valid.sum() < 3:
        raise ValueError(f"Need ≥3 valid ranges; got {valid.sum()}")
    if x0_xy is None:
        # Anchors are symmetric around (0, 0), so mean would be 0. LM with
        # numerical Jacobian uses step = sqrt(eps)*|x|, which is 0 at x=0
        # and the solver dies on the start point. Pick a slightly offset
        # seed instead.
        x0_xy = np.array([0.1, 0.1])
    anchors_v = anchors[valid]
    ranges_v = measured_ranges[valid]

    def residuals(p_xy):
        p = np.array([p_xy[0], p_xy[1], z_fixed])
        return np.linalg.norm(anchors_v - p, axis=1) - ranges_v

    xy = least_squares(residuals, x0_xy, method="lm").x
    return np.array([xy[0], xy[1], z_fixed])


def fit_trajectory(
    times_obs: NDArray[np.float64],
    pos_obs: NDArray[np.float64],
    sigma_pos: float = 0.05,
    params: BallParams | None = None,
    x0: NDArray[np.float64] | None = None,
    max_nfev: int = 200,
    loss: str = "linear",
    f_scale: float = 1.0,
    bounce_time: float | None = None,
    bounce_sigma_z: float = 0.020,
    bounce_vz_obs: float | None = None,
    bounce_vz_sigma: float = 1.0,
    bounce_xy_obs: NDArray[np.float64] | None = None,
    bounce_xy_sigma: float | NDArray[np.float64] = 0.020,
) -> tuple[NDArray, NDArray]:
    """Physics-constrained trajectory fit.

    Fits [release_pos(3), v0(3), spin(3)] to observed positions by
    integrating the ball ODE. Returns (pos_fitted, fitted_params).

    loss="linear" (default) uses pure least-squares via LM — fast and
    optimal under Gaussian noise. loss="huber" / "soft_l1" / "cauchy"
    enable robust fitting via TRF, suppressing the influence of outliers
    such as NLOS-biased ranges. f_scale is the residual scale at which
    the loss transitions from quadratic to robust (in units of sigma_pos).

    bounce_time (iBall-borrow #1, NSDI '17 §4.2): if provided, adds a
    soft constraint that z(bounce_time) == 0 with weight 1/bounce_sigma_z.
    This anchors the Z-axis to ground-truth-zero at the bounce instant,
    which the ball-side accelerometer can detect from the impact spike.

    bounce_vz_obs (beyond iBall, found to be net-neutral in sim with
    realistic CoR/spin noise — keep API but typically don't use):
    observed incoming vertical velocity at bounce. If provided, adds a
    soft constraint that vz(bounce_time) == bounce_vz_obs with weight
    1/bounce_vz_sigma. Residual is Huber-clipped at ±2σ.

    bounce_xy_obs (the strong-impact one): observed (x, y) at the bounce
    moment from a constrained-z=0 multilateration of the UWB ranges
    sampled at t_bounce. Because z is known to be 0 at that instant,
    the multilat is 8 equations in 2 unknowns (vs 3) — sharpest
    position estimate of the whole flight. Combined with the z=0
    constraint this pins the trajectory through a precise 3D point.
    """
    if params is None:
        params = BallParams()
    if x0 is None:
        n_init = min(20, len(times_obs))
        p0_pos = pos_obs[0]
        dt_init = max(times_obs[n_init - 1] - times_obs[0], 1e-3)
        p0_vel = (pos_obs[n_init - 1] - pos_obs[0]) / dt_init
        p0_spin = np.array([0.0, 50.0, 0.0])
        x0 = np.concatenate([p0_pos, p0_vel, p0_spin])
    # Need to integrate past both observations and the bounce constraint
    t_max = (
        max(times_obs[-1], bounce_time if bounce_time is not None else times_obs[-1])
        + 1e-3
    )

    def residuals(pv):
        ts, states = integrate_trajectory(
            pv[:3], pv[3:6], pv[6:9], t_max=t_max, params=params
        )
        # Linear interpolation onto observation times — avoids the
        # ~9.5 mm/axis bias that arises from picking nearest-after
        # samples when fitting against real (irregularly-timed)
        # measurements.
        interp_pos = np.column_stack(
            [np.interp(times_obs, ts, states[:, d]) for d in range(3)]
        )
        obs_residuals = (interp_pos - pos_obs).flatten() / sigma_pos
        if bounce_time is None:
            return obs_residuals
        # Bouncing constraint: z(bounce_time) == 0
        z_at_bounce = float(np.interp(bounce_time, ts, states[:, 2]))
        extra = [z_at_bounce / bounce_sigma_z]
        if bounce_vz_obs is not None:
            # v_in vertical recovered from piezo impulse + CoR physics.
            # Evaluate slightly BEFORE bounce_time — integrate_trajectory
            # applies the CoR flip at the bounce instant, so at exactly
            # bounce_time the velocity has already inverted. Pre-bounce
            # offset gives consistent v_in everywhere.
            t_pre = bounce_time - 0.002
            vz_pre = float(np.interp(t_pre, ts, states[:, 5]))
            # Hard Huber-style clip at ±2σ: when the piezo observation
            # is a noise outlier (e.g., bad CoR estimate that session,
            # large spin-mismatch) the residual maxes out and stops
            # dragging the rest of the fit into a wrong basin.
            r = (vz_pre - bounce_vz_obs) / bounce_vz_sigma
            extra.append(float(np.clip(r, -2.0, 2.0)))
        if bounce_xy_obs is not None:
            # Sharp (x, y) pin at the bounce moment from z=0-constrained
            # multilat. σ can be scalar (same on both axes) or 2-vector
            # (per-axis). With 8-anchor symmetric geometry the y-axis is
            # much weaker than x at z=0 (short cross-pitch baseline) so
            # per-axis weighting is recommended.
            x_at_bounce = float(np.interp(bounce_time, ts, states[:, 0]))
            y_at_bounce = float(np.interp(bounce_time, ts, states[:, 1]))
            if np.ndim(bounce_xy_sigma) == 0:
                sx = sy = float(bounce_xy_sigma)
            else:
                sx, sy = float(bounce_xy_sigma[0]), float(bounce_xy_sigma[1])
            extra.append((x_at_bounce - bounce_xy_obs[0]) / sx)
            extra.append((y_at_bounce - bounce_xy_obs[1]) / sy)
        return np.concatenate([obs_residuals, np.asarray(extra)])

    if loss == "linear":
        result = least_squares(residuals, x0, method="lm", max_nfev=max_nfev)
    else:
        result = least_squares(
            residuals, x0, method="trf", loss=loss, f_scale=f_scale, max_nfev=max_nfev
        )
    fp = result.x
    ts_fit, st_fit = integrate_trajectory(
        fp[:3], fp[3:6], fp[6:9], t_max=t_max, params=params
    )
    interp_fit = np.column_stack(
        [np.interp(times_obs, ts_fit, st_fit[:, d]) for d in range(3)]
    )
    return interp_fit, fp
