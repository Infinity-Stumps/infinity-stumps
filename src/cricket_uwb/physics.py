"""
Cricket ball flight dynamics: gravity + drag + Magnus, with bounce.

References:
  - Mehta, R. D. (2005). "Cricket ball aerodynamics: myth versus
    science." International Sports Engineering Conference.
  - Sayers, A. T. (2001). "On the reverse swing of a cricket ball —
    modelling and measurement."

Bounce is a coefficient-of-restitution one-shot. Sim 10 will refine.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from numpy.typing import NDArray
from scipy.integrate import odeint


@dataclass
class BallParams:
    mass: float = 0.160            # kg (legal 0.156–0.163)
    radius: float = 0.0356         # m
    Cd: float = 0.40
    CL_coef: float = 0.15
    air_density: float = 1.20      # kg/m^3
    cor_vertical: float = 0.55
    cor_horizontal: float = 0.75

    @property
    def cross_section(self) -> float:
        return float(np.pi * self.radius ** 2)


def ball_dynamics(state: NDArray[np.float64], t: float,
                  spin: NDArray[np.float64],
                  params: BallParams) -> NDArray[np.float64]:
    """ODE RHS. state = [x,y,z,vx,vy,vz]. Bounce handled outside."""
    vel = state[3:]
    v_mag = float(np.linalg.norm(vel))
    if v_mag < 1e-3:
        v_mag = 1e-3
    a = np.array([0.0, 0.0, -9.81])
    F_drag = -0.5 * params.air_density * params.Cd * params.cross_section * v_mag * vel
    a += F_drag / params.mass
    spin_mag = float(np.linalg.norm(spin))
    if spin_mag > 1e-6:
        spin_hat = spin / spin_mag
        F_magnus = (0.5 * params.air_density * params.CL_coef *
                    params.cross_section * v_mag * np.cross(spin_hat, vel))
        a += F_magnus / params.mass
    return np.concatenate([vel, a])


def integrate_trajectory(release_pos: NDArray[np.float64],
                         v0: NDArray[np.float64],
                         spin: NDArray[np.float64],
                         t_max: float = 0.85,
                         dt: float = 0.0005,
                         params: BallParams | None = None
                         ) -> tuple[NDArray, NDArray]:
    """Integrate flight with bounce. Returns (times, states[N,6])."""
    if params is None:
        params = BallParams()
    times = [0.0]
    states = [np.concatenate([release_pos, v0])]
    state = states[0].copy()
    t = 0.0
    while t < t_max:
        sol = odeint(ball_dynamics, state, [t, t+dt],
                     args=(spin, params), rtol=1e-8, atol=1e-10)
        state = sol[-1].copy()
        t += dt
        if state[2] <= 0.0 and state[5] < 0:
            state[5] *= -params.cor_vertical
            state[3] *= params.cor_horizontal
            state[4] *= params.cor_horizontal
            state[2] = 0.0
        times.append(t)
        states.append(state.copy())
    return np.array(times), np.array(states)


def make_delivery(speed_mps: float,
                  release_height: float = 2.30,
                  release_x: float = -8.5,
                  release_y: float = 0.10,
                  angle_horizontal_deg: float = 1.5,
                  angle_vertical_deg: float = 6.0,
                  spin_axis: NDArray[np.float64] | None = None,
                  spin_rev_per_sec: float = 25.0,
                  ) -> tuple[NDArray, NDArray, NDArray]:
    """Convenience: realistic fast-bowler delivery."""
    if spin_axis is None:
        spin_axis = np.array([0.3, 1.0, 0.1])
    spin_axis = np.asarray(spin_axis, dtype=float)
    spin_axis_unit = spin_axis / np.linalg.norm(spin_axis)
    spin = spin_axis_unit * (2 * np.pi * spin_rev_per_sec)
    release_pos = np.array([release_x, release_y, release_height])
    ah = np.deg2rad(angle_horizontal_deg)
    av = np.deg2rad(angle_vertical_deg)
    v0 = speed_mps * np.array([np.cos(ah)*np.cos(av),
                                np.sin(ah),
                                -np.sin(av)])
    return release_pos, v0, spin
