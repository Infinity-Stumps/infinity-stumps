"""Shared fixtures for the test suite."""

import numpy as np
import pytest

from infinity_stumps import (
    ANCHORS_8,
    BallParams,
    integrate_trajectory,
    make_delivery,
)


@pytest.fixture
def rng() -> np.random.Generator:
    """Seeded RNG so noise-driven tests are deterministic."""
    return np.random.default_rng(42)


@pytest.fixture
def anchors() -> np.ndarray:
    """The 8-anchor production layout."""
    return ANCHORS_8


@pytest.fixture
def ball_params() -> BallParams:
    """Default regulation-ball physics parameters."""
    return BallParams()


@pytest.fixture
def standard_delivery() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A realistic ~38 m/s fast-bowler delivery: (release_pos, v0, spin)."""
    return make_delivery(speed_mps=38.0)


@pytest.fixture
def delivery_trajectory(
    standard_delivery: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    """(times, states[N, 6]) for the standard delivery, integrated through bounce."""
    release_pos, v0, spin = standard_delivery
    return integrate_trajectory(release_pos, v0, spin)
