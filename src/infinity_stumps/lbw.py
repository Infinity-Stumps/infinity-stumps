"""LBW prediction — forward extrapolation + uncertainty ellipse + verdict.

After a pad strike, predict where the ball would have travelled had the
pad not intercepted, and compare to the stump rectangle. Outputs one of:

  HITTING        — ball would have hit, 95% confidence ellipse fully
                   inside the stump rectangle
  MISSING        — ball would have missed, ellipse fully outside
  UMPIRE'S CALL  — ellipse overlaps the stump edge

Mirrors DRS / Hawk-Eye logic on Infinity Stumps hardware + iPhone compute.

Benchmark to beat: iBall (Gowda et al., NSDI '17) reports 22 cm 3D /
9.9 cm X-axis trajectory extrapolation error at the stump line.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .geometry import PITCH_HL, STUMP_W
from .physics import BallParams, integrate_trajectory

# Stump rectangle: y in [-half_w, +half_w], z in [0, top]
STUMP_HALF_W: float = STUMP_W / 2  # 0.1143 m
STUMP_TOP_H: float = 0.711  # full stump height (m)
STUMP_LINE_X: float = PITCH_HL  # batter-end stump line (+10.06 m)

# χ² critical value for 2D 95% confidence ellipse
CHI2_95_2D: float = 5.991


# ---------- impact detection ----------


def detect_impact(
    times: NDArray[np.float64],
    accel_mag_g: NDArray[np.float64],
    threshold_g: float = 30.0,
) -> float | None:
    """First sample whose |a| exceeds the threshold (in g units).

    Pad strikes are ~30-100g, bat strikes ~100-1000g — so 30g picks up
    both. Returns None if no spike. Times and accel_mag_g must align.
    """
    mask = accel_mag_g > threshold_g
    if not mask.any():
        return None
    return float(times[mask.argmax()])


# ---------- forward extrapolation ----------


def extrapolate_to_stumps(
    release_pos: NDArray[np.float64],
    v0: NDArray[np.float64],
    spin: NDArray[np.float64],
    stump_x: float = STUMP_LINE_X,
    t_max: float = 2.0,
    params: BallParams | None = None,
) -> tuple[float, NDArray] | None:
    """Integrate trajectory forward; return (t_cross, [y, z]) at stump_x.

    Returns None if the integrated trajectory never crosses stump_x
    (e.g., diverged or already past).
    """
    ts, st = integrate_trajectory(release_pos, v0, spin, t_max=t_max, params=params)
    xs = st[:, 0]
    crosses = (xs[:-1] < stump_x) & (xs[1:] >= stump_x)
    idx = np.where(crosses)[0]
    if len(idx) == 0:
        return None
    i = int(idx[0])
    alpha = (stump_x - xs[i]) / (xs[i + 1] - xs[i])
    t_cross = ts[i] + alpha * (ts[i + 1] - ts[i])
    yz = st[i, 1:3] + alpha * (st[i + 1, 1:3] - st[i, 1:3])
    return float(t_cross), np.asarray(yz, dtype=np.float64)


# ---------- covariance from least-squares fit ----------


def fit_covariance(
    jac: NDArray[np.float64],
    residuals: NDArray[np.float64],
) -> NDArray[np.float64] | None:
    """Parameter covariance estimate from scipy.least_squares output.

    Σ_p ≈ s² · (Jᵀ J)⁻¹ where s² = ||r||² / (n - p) is the reduced
    chi-square (Birge ratio). Returns None if Jᵀ J is singular.
    """
    n, p = jac.shape
    if n <= p:
        return None
    s2 = float(residuals @ residuals) / (n - p)
    JTJ = jac.T @ jac
    try:
        cov = s2 * np.linalg.inv(JTJ)
    except np.linalg.LinAlgError:
        return None
    return cov


def stump_line_covariance(
    params: NDArray[np.float64],
    param_cov: NDArray[np.float64],
    stump_x: float = STUMP_LINE_X,
    eps: float = 1e-3,
    ball_params: BallParams | None = None,
) -> NDArray[np.float64] | None:
    """Propagate param covariance to (y, z) covariance at stump line.

    Σ_yz = J Σ_p Jᵀ, with J = ∂(y,z)/∂params estimated by central
    differences on `extrapolate_to_stumps`.
    """
    n = len(params)
    J = np.zeros((2, n))
    for i in range(n):
        dp = np.zeros(n)
        dp[i] = eps
        plus = extrapolate_to_stumps(
            params[:3] + dp[:3],
            params[3:6] + dp[3:6],
            params[6:9] + dp[6:9],
            stump_x,
            params=ball_params,
        )
        minus = extrapolate_to_stumps(
            params[:3] - dp[:3],
            params[3:6] - dp[3:6],
            params[6:9] - dp[6:9],
            stump_x,
            params=ball_params,
        )
        if plus is None or minus is None:
            return None
        J[:, i] = (plus[1] - minus[1]) / (2 * eps)
    return J @ param_cov @ J.T


# ---------- verdict ----------


@dataclass
class LBWVerdict:
    decision: str  # "HITTING" / "MISSING" / "UMPIRE'S CALL"
    yz_predicted: NDArray  # 2-vector (y, z) at stump line
    yz_cov: NDArray | None  # 2×2 covariance, or None
    ellipse_semi_axes: tuple[float, float]  # 95% semi-axes (m), or (0,0)
    ellipse_angle: float  # rotation (rad)


def lbw_verdict(
    yz_predicted: NDArray[np.float64],
    yz_cov: NDArray[np.float64] | None,
    stump_half_w: float = STUMP_HALF_W,
    stump_top: float = STUMP_TOP_H,
) -> LBWVerdict:
    """Three-way verdict comparing the 95% ellipse to the stump rectangle."""
    y, z = float(yz_predicted[0]), float(yz_predicted[1])
    centre_in = (abs(y) <= stump_half_w) and (0.0 <= z <= stump_top)

    if yz_cov is None:
        return LBWVerdict(
            "HITTING" if centre_in else "MISSING",
            yz_predicted,
            None,
            (0.0, 0.0),
            0.0,
        )

    # 95% ellipse semi-axes
    eigvals, eigvecs = np.linalg.eigh(yz_cov)
    eigvals = np.maximum(eigvals, 0.0)
    a = float(np.sqrt(CHI2_95_2D * eigvals[1]))  # major
    b = float(np.sqrt(CHI2_95_2D * eigvals[0]))  # minor
    angle = float(np.arctan2(eigvecs[1, 1], eigvecs[0, 1]))

    # Sample ellipse boundary, classify each point as inside-stumps or not
    theta = np.linspace(0.0, 2 * np.pi, 128, endpoint=False)
    ex = a * np.cos(theta)
    ey = b * np.sin(theta)
    c_, s_ = np.cos(angle), np.sin(angle)
    pts_y = y + c_ * ex - s_ * ey
    pts_z = z + s_ * ex + c_ * ey
    inside = (np.abs(pts_y) <= stump_half_w) & (pts_z >= 0.0) & (pts_z <= stump_top)

    if inside.all() and centre_in:
        decision = "HITTING"
    elif (not inside.any()) and (not centre_in):
        decision = "MISSING"
    else:
        decision = "UMPIRE'S CALL"
    return LBWVerdict(decision, yz_predicted, yz_cov, (a, b), angle)


# ---------- full LBW assessment ----------


@dataclass
class LBWAssessment:
    """Full LBW assessment with cricket-rule preconditions."""

    pitched_in_line: bool  # |y_bounce| ≤ stump_half_w
    pitched_outside_off: bool  # y_bounce < -stump_half_w (right-hand bat)
    impact_in_line: bool  # |y_impact| ≤ stump_half_w
    stump_line: LBWVerdict  # HIT/MISS/UMPIRE
    out: bool  # composite: pitched & impact in line & HITTING


def find_bounce(
    release_pos, v0, spin, params: BallParams | None = None, t_max: float = 2.0
) -> NDArray[np.float64] | None:
    """Return (x_bounce, y_bounce) where the fitted trajectory hits z=0."""
    ts, st = integrate_trajectory(release_pos, v0, spin, t_max=t_max, params=params)
    zs = st[:, 2]
    # First downward crossing of z=0
    hits = (zs[:-1] > 0.0) & (zs[1:] <= 0.0)
    idx = np.where(hits)[0]
    if len(idx) == 0:
        return None
    i = int(idx[0])
    alpha = zs[i] / (zs[i] - zs[i + 1])
    xy = st[i, 0:2] + alpha * (st[i + 1, 0:2] - st[i, 0:2])
    return np.asarray(xy, dtype=np.float64)


def assess_lbw(
    release_pos: NDArray[np.float64],
    v0: NDArray[np.float64],
    spin: NDArray[np.float64],
    impact_pos: NDArray[np.float64],
    param_cov: NDArray[np.float64] | None = None,
    ball_params: BallParams | None = None,
) -> LBWAssessment:
    """Full LBW assessment given fitted params + observed impact position.

    Right-hand bat convention assumed (off side = -y). For left-hand bat,
    flip sign on `pitched_outside_off` interpretation outside this fn.
    """
    bounce_xy = find_bounce(release_pos, v0, spin, params=ball_params)
    if bounce_xy is None:
        pitched_in_line = False
        pitched_outside_off = False
    else:
        y_bounce = float(bounce_xy[1])
        pitched_in_line = abs(y_bounce) <= STUMP_HALF_W
        pitched_outside_off = y_bounce < -STUMP_HALF_W

    impact_in_line = abs(float(impact_pos[1])) <= STUMP_HALF_W

    extr = extrapolate_to_stumps(release_pos, v0, spin, params=ball_params)
    if extr is None:
        verdict = LBWVerdict(
            "MISSING", np.array([np.nan, np.nan]), None, (0.0, 0.0), 0.0
        )
    else:
        _, yz = extr
        if param_cov is not None:
            params9 = np.concatenate([release_pos, v0, spin])
            yz_cov = stump_line_covariance(params9, param_cov, ball_params=ball_params)
        else:
            yz_cov = None
        verdict = lbw_verdict(yz, yz_cov)

    out = (
        (pitched_in_line or pitched_outside_off)
        and impact_in_line
        and verdict.decision == "HITTING"
    )
    return LBWAssessment(
        pitched_in_line,
        pitched_outside_off,
        impact_in_line,
        verdict,
        out,
    )
