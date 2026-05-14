"""Parametric batter skeleton for UWB occlusion modelling.

Replaces the single-cylinder batter with a sampled-pose articulated model:
torso + head + arms + thighs + lower-legs + pads + bat as 14 separate
cylinders. Each delivery in a Monte Carlo gets a different batter
(height, build, handedness, stance variation, bat position).

Adapted from `plumb/src/batsman_skeleton.py` (same project owner, Matthew
Hardern; both projects local-only, pre-patent). The acoustic-specific
delay model is dropped; for UWB we only need binary blocked/not-blocked
per ray, since 6.5 GHz UWB is heavily absorbed by tissue (>30 dB/cm) so
any meaningful chord length effectively kills the ray.

Anthropometric ratios are Drillis-Contini (1966) — public-domain data.

The skeleton's 14 cylinders are:
  - 2 humerus (shoulder→elbow)
  - 2 forearm (elbow→wrist)
  - 2 femur (hip→knee)
  - 2 tibia (knee→ankle)
  - 1 torso (hip-mid→shoulder-mid)
  - 1 head (vertical cylinder at neck height)
  - 2 pads (over the shins, larger radius than tibia)
  - 1 bat (held forward+down from grip-centre)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

# Drillis-Contini anthropometric ratios (fraction of standing height)
FEMUR_RATIO = 0.245
TIBIA_RATIO = 0.246
HUMERUS_RATIO = 0.186
FOREARM_RATIO = 0.146
SPINE_RATIO = 0.288  # hip-midpoint to shoulder-midpoint
SHOULDER_BREADTH_RATIO = 0.259
HIP_BREADTH_RATIO = 0.191
HEAD_HEIGHT_RATIO = 0.130

# Bone radii (fraction of height × build factor) — anatomically plausible
HUMERUS_RADIUS_RATIO = 0.022
FOREARM_RADIUS_RATIO = 0.018
FEMUR_RADIUS_RATIO = 0.038
TIBIA_RADIUS_RATIO = 0.028
TORSO_RADIUS_RATIO = 0.090
HEAD_RADIUS_RATIO = 0.060
PAD_RADIUS_RATIO = 0.055  # cricket pads over the shins
BAT_RADIUS = 0.040

CHORD_BLOCK_THRESHOLD_M = 0.01  # rays with any cylinder chord > 1 cm count as blocked


@dataclass
class Bone:
    p0: np.ndarray  # (3,) start
    p1: np.ndarray  # (3,) end
    radius: float
    label: str = ""


@dataclass
class BatterSkeleton:
    bones: list[Bone]
    height_m: float
    build: float
    handedness: Literal["right", "left"]
    metadata: dict = field(default_factory=dict)


def _yaw_R(angle: float) -> np.ndarray:
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def sample_batter(
    rng: np.random.Generator, stance_x_centre: float = 10.0
) -> BatterSkeleton:
    """Sample a batter pose at the batter's-end crease.

    stance_x_centre: world X position of the batter's stance centre.
    For infinity-stumps's coordinate system (origin at pitch centre, +X
    toward batter end at +10.06 m), 10.0 m is typical (just inside
    the popping crease).
    """
    # Anthropometry
    height = float(np.clip(rng.normal(1.78, 0.07), 1.65, 1.95))
    build = float(np.clip(rng.normal(1.0, 0.10), 0.85, 1.20))
    handedness: Literal["right", "left"] = "right" if rng.uniform() < 0.5 else "left"

    femur_len = FEMUR_RATIO * height
    tibia_len = TIBIA_RATIO * height
    spine_len = SPINE_RATIO * height
    humerus_len = HUMERUS_RATIO * height
    forearm_len = FOREARM_RATIO * height
    shoulder_breadth = SHOULDER_BREADTH_RATIO * height
    hip_breadth = HIP_BREADTH_RATIO * height
    head_height = HEAD_HEIGHT_RATIO * height
    head_radius = HEAD_RADIUS_RATIO * height * build

    # Stance-pose params sampled per delivery
    cx = float(rng.uniform(stance_x_centre - 0.10, stance_x_centre + 0.10))
    cy = float(rng.uniform(-0.10, 0.10))
    body_yaw = float(rng.uniform(-np.pi / 8, np.pi / 8))  # small side-on variation
    foot_sep = float(rng.uniform(0.25, 0.40))
    knee_flex_l = float(rng.uniform(0.4, 0.8))
    knee_flex_r = float(rng.uniform(0.4, 0.8))
    spine_lean = float(rng.uniform(0.10, 0.30))
    shoulder_rot = float(rng.uniform(0.05, 0.25))
    elbow_flex_l = float(rng.uniform(1.4, 2.1))
    elbow_flex_r = float(rng.uniform(1.4, 2.1))

    sign = 1.0 if handedness == "right" else -1.0
    # For infinity-stumps, +X is toward batter end, so the bowler is at -X
    # relative to the batter. The batter faces toward -X (toward bowler).
    R_yaw = _yaw_R(body_yaw)
    fwd = R_yaw @ np.array([-1.0, 0.0, 0.0])  # toward bowler (was +X in plumb)
    side = R_yaw @ np.array([0.0, 1.0, 0.0])

    # Feet/ankles
    front_foot = np.array([cx, cy, 0.0]) + (foot_sep / 2) * fwd
    back_foot = np.array([cx, cy, 0.0]) - (foot_sep / 2) * fwd
    if handedness == "right":
        l_ankle = front_foot.copy()
        r_ankle = back_foot.copy()
    else:
        l_ankle = back_foot.copy()
        r_ankle = front_foot.copy()

    # Knees
    def knee_from_ankle(ankle, flex):
        z_offset = tibia_len * np.cos(flex / 2)
        x_offset = tibia_len * np.sin(flex / 2) * 0.5
        return ankle + np.array([0.0, 0.0, z_offset]) + x_offset * fwd

    l_knee = knee_from_ankle(l_ankle, knee_flex_l)
    r_knee = knee_from_ankle(r_ankle, knee_flex_r)

    # Hips
    knee_mid = (l_knee + r_knee) / 2
    avg_kf = (knee_flex_l + knee_flex_r) / 2
    hip_z = knee_mid[2] + femur_len * np.cos(avg_kf / 2)
    hip_x = knee_mid[0] + femur_len * np.sin(avg_kf / 2) * 0.5 * fwd[0]
    hip_y = knee_mid[1] + femur_len * np.sin(avg_kf / 2) * 0.5 * fwd[1]
    hip_mid = np.array([hip_x, hip_y, hip_z])
    l_hip = hip_mid - sign * (hip_breadth / 2) * side
    r_hip = hip_mid + sign * (hip_breadth / 2) * side

    # Spine + shoulders
    spine_dir = np.array(
        [
            np.sin(spine_lean) * fwd[0],
            np.sin(spine_lean) * fwd[1],
            np.cos(spine_lean),
        ]
    )
    shoulder_mid = hip_mid + spine_len * spine_dir
    R_sh = _yaw_R(sign * shoulder_rot)
    sh_axis = R_sh @ side
    l_shoulder = shoulder_mid - sign * (shoulder_breadth / 2) * sh_axis
    r_shoulder = shoulder_mid + sign * (shoulder_breadth / 2) * sh_axis

    # Elbows + wrists (bat-grip)
    def arm(shoulder, elbow_flex):
        elbow_dir = np.array([0.20 * fwd[0], 0.20 * fwd[1], -0.98])
        elbow_dir = elbow_dir / np.linalg.norm(elbow_dir)
        elbow = shoulder + humerus_len * elbow_dir
        bend = np.pi - elbow_flex
        forearm_dir = np.array(
            [
                np.sin(bend) * fwd[0],
                np.sin(bend) * fwd[1],
                -np.cos(bend),
            ]
        )
        forearm_dir = forearm_dir / np.linalg.norm(forearm_dir)
        wrist = elbow + forearm_len * forearm_dir
        return elbow, wrist

    l_elbow, l_wrist = arm(l_shoulder, elbow_flex_l)
    r_elbow, r_wrist = arm(r_shoulder, elbow_flex_r)

    # Head centre
    head_centre = shoulder_mid + np.array([0.0, 0.0, head_height / 2])

    # Build the bone cylinders
    bones: list[Bone] = []
    bones.append(
        Bone(l_shoulder, l_elbow, HUMERUS_RADIUS_RATIO * height * build, "humerus_L")
    )
    bones.append(
        Bone(l_elbow, l_wrist, FOREARM_RADIUS_RATIO * height * build, "forearm_L")
    )
    bones.append(
        Bone(r_shoulder, r_elbow, HUMERUS_RADIUS_RATIO * height * build, "humerus_R")
    )
    bones.append(
        Bone(r_elbow, r_wrist, FOREARM_RADIUS_RATIO * height * build, "forearm_R")
    )
    bones.append(Bone(l_hip, l_knee, FEMUR_RADIUS_RATIO * height * build, "femur_L"))
    bones.append(Bone(l_knee, l_ankle, TIBIA_RADIUS_RATIO * height * build, "tibia_L"))
    bones.append(Bone(r_hip, r_knee, FEMUR_RADIUS_RATIO * height * build, "femur_R"))
    bones.append(Bone(r_knee, r_ankle, TIBIA_RADIUS_RATIO * height * build, "tibia_R"))
    bones.append(
        Bone(hip_mid, shoulder_mid, TORSO_RADIUS_RATIO * height * build, "torso")
    )
    head_bottom = head_centre - np.array([0.0, 0.0, head_height / 2])
    head_top = head_centre + np.array([0.0, 0.0, head_height / 2])
    bones.append(Bone(head_bottom, head_top, head_radius, "head"))
    bones.append(Bone(l_ankle, l_knee, PAD_RADIUS_RATIO * height * build, "pad_L"))
    bones.append(Bone(r_ankle, r_knee, PAD_RADIUS_RATIO * height * build, "pad_R"))

    # Bat — held forward from grip-centre, down toward pitch
    grip_centre = (l_wrist + r_wrist) / 2
    bat_dir = np.array([0.6 * fwd[0], 0.6 * fwd[1], -0.8])
    bat_dir = bat_dir / np.linalg.norm(bat_dir)
    bat_tip = grip_centre + 0.85 * bat_dir
    bones.append(Bone(grip_centre, bat_tip, BAT_RADIUS, "bat"))

    metadata = {
        "stance_xy": (cx, cy),
        "body_yaw": body_yaw,
        "knee_flex": (knee_flex_l, knee_flex_r),
        "spine_lean": spine_lean,
        "shoulder_rot": shoulder_rot,
        "elbow_flex": (elbow_flex_l, elbow_flex_r),
    }
    return BatterSkeleton(
        bones=bones,
        height_m=height,
        build=build,
        handedness=handedness,
        metadata=metadata,
    )


def line_bone_chord_length(
    p_source: np.ndarray, p_mic: np.ndarray, bone: Bone
) -> float:
    """Length of segment [p_source, p_mic] inside a finite oriented cylinder.

    Parameterise line over t in [0,1]. Decompose into the cylinder-axial
    and perpendicular components, find the radial-intersection chord, and
    clip to (a) the line segment and (b) the cylinder's axial extent.
    Standard finite-oriented-cylinder vs. line-segment intersection.
    """
    d = p_mic - p_source
    a = bone.p1 - bone.p0
    a_norm_sq = float(a @ a)
    if a_norm_sq < 1e-12:
        return 0.0
    a_unit = a / np.sqrt(a_norm_sq)
    w = p_source - bone.p0
    d_par = float(d @ a_unit)
    w_par = float(w @ a_unit)
    d_perp = d - d_par * a_unit
    w_perp = w - w_par * a_unit
    A = float(d_perp @ d_perp)
    B = 2.0 * float(w_perp @ d_perp)
    C = float(w_perp @ w_perp) - bone.radius**2

    if A < 1e-12:
        # Line parallel to cylinder axis
        if C > 0:
            return 0.0
        if d_par == 0:
            return 0.0
        t_a = (0.0 - w_par) / d_par
        t_b = (np.sqrt(a_norm_sq) - w_par) / d_par
        t_lo, t_hi = sorted([t_a, t_b])
        t_lo = max(0.0, t_lo)
        t_hi = min(1.0, t_hi)
        if t_hi <= t_lo:
            return 0.0
        return (t_hi - t_lo) * float(np.linalg.norm(d))

    disc = B * B - 4 * A * C
    if disc <= 0:
        return 0.0
    sq = np.sqrt(disc)
    t1 = (-B - sq) / (2 * A)
    t2 = (-B + sq) / (2 * A)

    # Axial-extent clip
    if abs(d_par) < 1e-12:
        if 0 <= w_par <= np.sqrt(a_norm_sq):
            t_ax_lo, t_ax_hi = 0.0, 1.0
        else:
            return 0.0
    else:
        ta = (0.0 - w_par) / d_par
        tb = (np.sqrt(a_norm_sq) - w_par) / d_par
        t_ax_lo, t_ax_hi = sorted([ta, tb])

    t_lo = max(t1, t_ax_lo, 0.0)
    t_hi = min(t2, t_ax_hi, 1.0)
    if t_hi <= t_lo:
        return 0.0
    return (t_hi - t_lo) * float(np.linalg.norm(d))


def total_body_chord_length(
    p_source: np.ndarray, p_target: np.ndarray, skeleton: BatterSkeleton
) -> float:
    """Sum chord lengths through all bones. Overlaps are summed."""
    return sum(line_bone_chord_length(p_source, p_target, b) for b in skeleton.bones)


def is_blocked(
    p_source: np.ndarray,
    p_target: np.ndarray,
    skeleton: BatterSkeleton,
    threshold: float = CHORD_BLOCK_THRESHOLD_M,
) -> bool:
    """Binary block test: True if any bone gives a chord > threshold.

    UWB at 6.5 GHz attenuates ~30 dB/cm through tissue, so any chord
    over ~1 cm effectively kills the signal — well below typical
    link-budget margin at our anchor-tag distances.
    """
    for bone in skeleton.bones:
        if line_bone_chord_length(p_source, p_target, bone) > threshold:
            return True
    return False
