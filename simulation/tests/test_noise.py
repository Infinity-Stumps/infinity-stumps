"""UWB ranging noise models."""

import numpy as np

from infinity_stumps import RANGE_SIGMA_DEFAULT, add_range_noise, occluded_range_noise


def test_add_range_noise_preserves_shape():
    ranges = np.array([1.0, 5.0, 10.0, 20.0])
    noisy = add_range_noise(ranges, rng=np.random.default_rng(0))
    assert noisy.shape == ranges.shape


def test_add_range_noise_is_deterministic_with_seed():
    ranges = np.full(100, 5.0)
    a = add_range_noise(ranges, rng=np.random.default_rng(123))
    b = add_range_noise(ranges, rng=np.random.default_rng(123))
    assert np.array_equal(a, b)


def test_add_range_noise_statistics():
    ranges = np.full(50_000, 5.0)
    noisy = add_range_noise(
        ranges, sigma=RANGE_SIGMA_DEFAULT, rng=np.random.default_rng(7)
    )
    residuals = noisy - ranges
    assert abs(residuals.mean()) < 0.002  # zero-mean
    assert abs(residuals.std() - RANGE_SIGMA_DEFAULT) < 0.002


def test_occluded_range_noise_all_los_without_occluders(anchors, rng):
    target = np.array([0.0, 0.0, 1.0])
    true_ranges = np.linalg.norm(anchors - target, axis=1)
    noisy, is_los = occluded_range_noise(true_ranges, anchors, target, rng=rng)
    assert is_los.all()
    assert np.all(np.isfinite(noisy))


def test_occluded_range_noise_flags_blocked_ray(anchors, rng):
    target = np.array([0.0, 0.0, 1.0])
    true_ranges = np.linalg.norm(anchors - target, axis=1)
    # Place a large occluder squarely between anchor 0 and the target.
    midpoint = 0.5 * (anchors[0] + target)
    occluders = [(midpoint, 0.5)]
    noisy, is_los = occluded_range_noise(
        true_ranges, anchors, target, occluders=occluders, rng=rng
    )
    assert not is_los[0]  # that anchor is NLOS
    # NLOS ranges are either dropped (NaN) or positively biased.
    assert np.isnan(noisy[0]) or noisy[0] > true_ranges[0]
