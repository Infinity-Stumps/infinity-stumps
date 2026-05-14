"""Pitch geometry and GDOP."""

import numpy as np

from infinity_stumps import ANCHORS_8, ANCHORS_12, gdop, gdop_map
from infinity_stumps.geometry import PAI_X, PITCH_HL, STUMP_TOP


def test_anchor_array_shapes():
    assert ANCHORS_8.shape == (8, 3)
    assert ANCHORS_12.shape == (12, 3)


def test_anchors_12_extends_anchors_8():
    # The 12-anchor layout is the 8-anchor one plus 4 mid-stump anchors.
    assert np.array_equal(ANCHORS_12[:8], ANCHORS_8)


def test_stump_anchors_at_stump_top_height():
    stump_anchors = ANCHORS_8[np.abs(np.abs(ANCHORS_8[:, 0]) - PITCH_HL) < 1e-6]
    assert len(stump_anchors) == 4
    assert np.allclose(stump_anchors[:, 2], STUMP_TOP)


def test_pai_anchors_at_ground_level():
    pai_anchors = ANCHORS_8[ANCHORS_8[:, 2] == 0.0]
    assert len(pai_anchors) == 4
    assert set(np.abs(pai_anchors[:, 0])) == {PAI_X}


def test_gdop_modest_above_pitch_centre():
    # Mid-pitch, 1.5 m up: usable geometry, not singular.
    g = gdop(np.array([0.0, 0.0, 1.5]))
    assert 1.0 < g < 10.0


def test_gdop_singular_at_anchor():
    # Sitting on an anchor makes the geometry matrix rank-deficient.
    g = gdop(ANCHORS_8[0])
    assert np.isnan(g) or g > 100


def test_gdop_worse_far_outside_anchor_footprint():
    # Inside the anchor footprint the angular spread is wide; far past the
    # batter end every anchor sits behind you and GDOP collapses.
    inside = gdop(np.array([0.0, 0.0, 1.5]))
    far_outside = gdop(np.array([30.0, 0.0, 1.5]))
    assert far_outside > inside


def test_gdop_map_shapes():
    xs, ys, grid = gdop_map(z=1.0, resolution=20)
    assert grid.shape == (len(ys), len(xs))
    assert np.all(np.isfinite(grid))
