"""Infinity Stumps — low-cost ball tracking + LBW prediction.

Phase 0 simulation package: pitch geometry, ball flight physics,
position solvers, the trajectory EKF + RTS smoother, and the LBW
verdict pipeline.
"""

from .ekf import EKFConfig, TrajectoryEKF
from .geometry import (
    ANCHORS_8,
    ANCHORS_12,
    PAI_X,
    PAI_Y,
    PITCH_HL,
    STUMP_HEIGHT,
    STUMP_MID,
    STUMP_TOP,
    STUMP_W,
    gdop,
    gdop_map,
)
from .lbw import (
    LBWAssessment,
    LBWVerdict,
    assess_lbw,
    detect_impact,
    extrapolate_to_stumps,
    find_bounce,
    fit_covariance,
    lbw_verdict,
    stump_line_covariance,
)
from .noise import RANGE_SIGMA_DEFAULT, add_range_noise, occluded_range_noise
from .physics import BallParams, ball_dynamics, integrate_trajectory, make_delivery
from .solver import fit_trajectory, solve_position, solve_position_at_ground

__all__ = [
    # geometry
    "ANCHORS_8",
    "ANCHORS_12",
    "PITCH_HL",
    "PAI_X",
    "PAI_Y",
    "STUMP_W",
    "STUMP_HEIGHT",
    "STUMP_TOP",
    "STUMP_MID",
    "gdop",
    "gdop_map",
    # physics
    "BallParams",
    "ball_dynamics",
    "integrate_trajectory",
    "make_delivery",
    # solvers
    "solve_position",
    "solve_position_at_ground",
    "fit_trajectory",
    # noise
    "RANGE_SIGMA_DEFAULT",
    "add_range_noise",
    "occluded_range_noise",
    # EKF
    "TrajectoryEKF",
    "EKFConfig",
    # LBW
    "LBWVerdict",
    "LBWAssessment",
    "detect_impact",
    "extrapolate_to_stumps",
    "fit_covariance",
    "stump_line_covariance",
    "lbw_verdict",
    "find_bounce",
    "assess_lbw",
]
