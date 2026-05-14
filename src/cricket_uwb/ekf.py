"""Extended Kalman Filter for cricket-ball trajectory tracking.

Phase 1 of the UWB-IMU fusion roadmap. This module implements the
physics-EKF: state = (position, velocity, spin), dynamics from the
drag + Magnus + gravity ODE, measurements from per-anchor UWB ranges.

Why this exists:
  - The current pipeline does batch trajectory fits AFTER all samples
    arrive. That collapses to a single 10-param fit over ~70 noisy 3D
    positions. Works well, but ignores within-TWR-cycle timing, can't
    handle live updates, and can't propagate state across discontinuities
    (bounce, pad strike) without separate logic.
  - An EKF gives a continuous best estimate that updates per range,
    handles asynchronous TWR ordering naturally, and exposes proper
    state covariance for downstream uncertainty (LBW ellipse).
  - Phase 2 will add IMU events (bounce/pad/bat) as triggers.
  - Phase 3 will fuse magnetometer for spin axis.

This phase does NOT use any IMU. State is propagated by integrating
the physics ODE between measurements.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from numpy.typing import NDArray
from scipy.integrate import odeint

from .physics import BallParams, ball_dynamics


# Index helpers
P_X, P_Y, P_Z = 0, 1, 2          # position
V_X, V_Y, V_Z = 3, 4, 5          # velocity
S_X, S_Y, S_Z = 6, 7, 8          # spin (rad/s)
STATE_DIM = 9


@dataclass
class EKFConfig:
    """Hyperparameters for the trajectory EKF."""
    # Initial covariance (uncertainty on initial state guess)
    sigma0_pos: float = 0.30         # m
    sigma0_vel: float = 5.0          # m/s
    sigma0_spin: float = 50.0        # rad/s — broad, we know little a priori

    # Process noise per second (continuous-time)
    q_pos: float = 0.001             # m/√s   — physics is nearly exact
    q_vel: float = 0.05              # m/s/√s — drag/Magnus model errors
    q_spin: float = 0.5              # rad/s/√s — slow spin axis variation

    # Measurement noise (range)
    sigma_range: float = 0.030       # m (matches DW3110 datasheet)

    # Bounce constraint (when triggered by impact sensor)
    sigma_bounce_z: float = 0.020    # m — softly pin z=0 at bounce instant

    # Numerical
    ode_dt: float = 0.001            # s — internal integration step
    jacobian_eps: float = 1e-4       # m or m/s for numerical Jacobian


class TrajectoryEKF:
    """Continuous EKF over (position, velocity, spin) for a cricket ball.

    Usage:
        ekf = TrajectoryEKF(BallParams(), EKFConfig())
        ekf.initialise(t=0.0, x0=initial_state, P0=initial_cov)
        for (t, anchor_idx, range_m) in measurements:
            ekf.predict(t)               # propagate to measurement time
            ekf.update_range(anchor_pos, range_m)
        # State at any time:
        ekf.predict(t_query)
        pos = ekf.state[:3]
        cov = ekf.P
    """

    def __init__(self, params: BallParams | None = None,
                 cfg: EKFConfig | None = None):
        self.params = params or BallParams()
        self.cfg = cfg or EKFConfig()
        self.state: NDArray[np.float64] = np.zeros(STATE_DIM)
        self.P: NDArray[np.float64] = np.eye(STATE_DIM)
        self.t: float = 0.0
        self._has_bounced: bool = False
        # History (optional; useful for plotting / debugging)
        self.history_t: list[float] = []
        self.history_state: list[NDArray] = []
        self.history_P: list[NDArray] = []
        # RTS smoother bookkeeping — per predict-update pair we record
        # (F, Q, x_predicted_before_update, P_predicted_before_update)
        # so the backward pass can compute G[k] and propagate smoothed
        # estimates.
        self._F_to_next: list[NDArray] = []          # F used to reach this snapshot
        self._x_pred_at: list[NDArray] = []          # predicted state at snapshot time
        self._P_pred_at: list[NDArray] = []          # predicted cov at snapshot time
        # Smoothed history (populated by smooth_backward)
        self.smoothed_state: list[NDArray] = []
        self.smoothed_P: list[NDArray] = []

    # ---------- initialisation ----------

    def initialise(self, t: float, x0: NDArray[np.float64],
                    P0: NDArray[np.float64] | None = None) -> None:
        self.t = float(t)
        self.state = np.asarray(x0, dtype=np.float64).copy()
        if P0 is None:
            diag = np.array([
                self.cfg.sigma0_pos**2, self.cfg.sigma0_pos**2,
                self.cfg.sigma0_pos**2,
                self.cfg.sigma0_vel**2, self.cfg.sigma0_vel**2,
                self.cfg.sigma0_vel**2,
                self.cfg.sigma0_spin**2, self.cfg.sigma0_spin**2,
                self.cfg.sigma0_spin**2,
            ])
            self.P = np.diag(diag)
        else:
            self.P = np.asarray(P0, dtype=np.float64).copy()
        self._has_bounced = False
        self.history_t.clear()
        self.history_state.clear()
        self.history_P.clear()
        self._F_to_next.clear()
        self._x_pred_at.clear()
        self._P_pred_at.clear()
        self.smoothed_state.clear()
        self.smoothed_P.clear()
        # Initial snapshot: F and predicted are unused at idx 0, store
        # identity + the initial state for shape consistency.
        self._F_to_next.append(np.eye(STATE_DIM))
        self._x_pred_at.append(self.state.copy())
        self._P_pred_at.append(self.P.copy())
        self._snapshot()

    # ---------- prediction ----------

    def predict(self, t_to: float) -> None:
        """Propagate state and covariance forward to time t_to.

        Uses the physics ODE for state propagation and a numerical
        Jacobian for the covariance update.

        Records F, predicted state, and predicted covariance into
        history so the RTS smoother can run later. If a subsequent
        update_range() is called before the next predict(), it will
        overwrite the (now filtered) state at the same index.
        """
        if t_to <= self.t + 1e-9:
            return
        dt = float(t_to - self.t)
        x_before = self.state.copy()
        self.state = self._propagate_state(x_before, dt)
        F = self._numerical_jacobian(x_before, dt)
        q_diag = np.array([
            self.cfg.q_pos**2, self.cfg.q_pos**2, self.cfg.q_pos**2,
            self.cfg.q_vel**2, self.cfg.q_vel**2, self.cfg.q_vel**2,
            self.cfg.q_spin**2, self.cfg.q_spin**2, self.cfg.q_spin**2,
        ]) * dt
        self.P = F @ self.P @ F.T + np.diag(q_diag)
        self.P = 0.5 * (self.P + self.P.T)
        self.t = float(t_to)
        # Snapshot: store predicted state/cov + the F that got us here.
        # If an update arrives next, _commit_filtered() overwrites the
        # filtered state/cov at this index (predicted stays for RTS).
        self.history_t.append(self.t)
        self.history_state.append(self.state.copy())   # filtered (no update yet → = pred)
        self.history_P.append(self.P.copy())
        self._F_to_next.append(F)
        self._x_pred_at.append(self.state.copy())
        self._P_pred_at.append(self.P.copy())

    def _propagate_state(self, x: NDArray[np.float64],
                          dt: float) -> NDArray[np.float64]:
        """One-shot ODE integration with bounce handling."""
        if dt <= 0:
            return x.copy()
        # State vector for ODE: [x, y, z, vx, vy, vz]
        ode_state = x[:6].copy()
        spin = x[6:9].copy()
        n_steps = max(1, int(np.ceil(dt / self.cfg.ode_dt)))
        ts_local = np.linspace(0.0, dt, n_steps + 1)
        sol = odeint(ball_dynamics, ode_state, ts_local,
                      args=(spin, self.params), rtol=1e-7, atol=1e-9)
        new_state6 = sol[-1].copy()
        # Bounce: if z <= 0 and falling, apply CoR (one-shot per call)
        if new_state6[2] <= 0.0 and new_state6[5] < 0:
            new_state6[5] *= -self.params.cor_vertical
            new_state6[3] *= self.params.cor_horizontal
            new_state6[4] *= self.params.cor_horizontal
            new_state6[2] = 0.0
            self._has_bounced = True
        return np.concatenate([new_state6, spin])

    def _numerical_jacobian(self, x: NDArray[np.float64],
                              dt: float) -> NDArray[np.float64]:
        """∂(propagate(x, dt))/∂x via central differences."""
        eps = self.cfg.jacobian_eps
        F = np.zeros((STATE_DIM, STATE_DIM))
        for i in range(STATE_DIM):
            xp = x.copy(); xp[i] += eps
            xm = x.copy(); xm[i] -= eps
            yp = self._propagate_state(xp, dt)
            ym = self._propagate_state(xm, dt)
            F[:, i] = (yp - ym) / (2.0 * eps)
        return F

    # ---------- measurement updates ----------

    def update_range(self, anchor_pos: NDArray[np.float64],
                      range_obs: float) -> None:
        """Standard range-measurement EKF update.

        Range residual: r_obs - || pos_estimate - anchor ||
        Overwrites the most recent (predict-only) snapshot with the
        filtered state/cov. The predicted state/cov are preserved in
        the RTS bookkeeping arrays.
        """
        pos = self.state[:3]
        diff = pos - anchor_pos
        d = float(np.linalg.norm(diff))
        if d < 1e-6:
            return
        H = np.zeros((1, STATE_DIM))
        H[0, P_X] = diff[0] / d
        H[0, P_Y] = diff[1] / d
        H[0, P_Z] = diff[2] / d
        R = np.array([[self.cfg.sigma_range ** 2]])
        innovation = np.array([range_obs - d])
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.state = self.state + (K @ innovation).flatten()
        I = np.eye(STATE_DIM)
        self.P = (I - K @ H) @ self.P @ (I - K @ H).T + K @ R @ K.T
        self.P = 0.5 * (self.P + self.P.T)
        # Overwrite the filtered slot at the most recent snapshot
        if self.history_state:
            self.history_state[-1] = self.state.copy()
            self.history_P[-1] = self.P.copy()

    def update_bounce_z(self, bounce_time: float) -> None:
        """Apply the z=0 bounce constraint as a soft measurement update."""
        self.predict(bounce_time)
        H = np.zeros((1, STATE_DIM)); H[0, P_Z] = 1.0
        R = np.array([[self.cfg.sigma_bounce_z ** 2]])
        innovation = np.array([0.0 - self.state[P_Z]])
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.state = self.state + (K @ innovation).flatten()
        I = np.eye(STATE_DIM)
        self.P = (I - K @ H) @ self.P @ (I - K @ H).T + K @ R @ K.T
        self.P = 0.5 * (self.P + self.P.T)
        if self.history_state:
            self.history_state[-1] = self.state.copy()
            self.history_P[-1] = self.P.copy()

    # ---------- RTS smoother (Rauch-Tung-Striebel) ----------

    def smooth_backward(self) -> None:
        """Run the RTS backward pass over the recorded history.

        Populates self.smoothed_state and self.smoothed_P. The last
        smoothed estimate equals the last filtered one; earlier ones
        are pulled toward consistency with all later measurements.

        Standard RTS recursion (k from N-2 down to 0):
          G[k] = P_f[k] @ F[k+1].T @ inv(P_pred[k+1])
          x_s[k] = x_f[k] + G[k] @ (x_s[k+1] - x_pred[k+1])
          P_s[k] = P_f[k] + G[k] @ (P_s[k+1] - P_pred[k+1]) @ G[k].T
        """
        N = len(self.history_state)
        if N < 2:
            self.smoothed_state = [s.copy() for s in self.history_state]
            self.smoothed_P = [P.copy() for P in self.history_P]
            return
        xs = [None] * N
        Ps = [None] * N
        xs[-1] = self.history_state[-1].copy()
        Ps[-1] = self.history_P[-1].copy()
        for k in range(N - 2, -1, -1):
            Pf = self.history_P[k]
            xf = self.history_state[k]
            F_kp1 = self._F_to_next[k + 1]
            x_pred_kp1 = self._x_pred_at[k + 1]
            P_pred_kp1 = self._P_pred_at[k + 1]
            try:
                Pp_inv = np.linalg.inv(P_pred_kp1)
            except np.linalg.LinAlgError:
                Pp_inv = np.linalg.pinv(P_pred_kp1)
            G = Pf @ F_kp1.T @ Pp_inv
            xs[k] = xf + G @ (xs[k + 1] - x_pred_kp1)
            Ps[k] = Pf + G @ (Ps[k + 1] - P_pred_kp1) @ G.T
            Ps[k] = 0.5 * (Ps[k] + Ps[k].T)
        self.smoothed_state = xs
        self.smoothed_P = Ps

    # ---------- diagnostics ----------

    def _snapshot(self) -> None:
        """Legacy snapshot — superseded by per-predict recording.

        Kept only because initialise() calls it once at startup.
        """
        self.history_t.append(self.t)
        self.history_state.append(self.state.copy())
        self.history_P.append(self.P.copy())

    def state_at(self, idx: int) -> tuple[float, NDArray, NDArray]:
        return self.history_t[idx], self.history_state[idx], self.history_P[idx]

    def trajectory_array(self) -> tuple[NDArray, NDArray]:
        """Return (times, states[N, 9]) from the history buffer."""
        return (np.asarray(self.history_t),
                np.asarray(self.history_state))
