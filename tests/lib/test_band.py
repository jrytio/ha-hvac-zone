"""Periods, the weather curve, hysteresis and the failsafe clamp."""

from datetime import datetime, time

import pytest

from custom_components.hvac_zone.lib import (
    ZoneSettings,
    clamp_band,
    curve_cool_point,
    is_day,
    next_boundary,
    settle,
)

S = ZoneSettings()


@pytest.mark.parametrize(
    ("clock", "day"),
    [
        (time(5, 59), False),
        (time(6, 0), True),
        (time(20, 29), True),
        (time(20, 30), False),
    ],
)
def test_is_day(clock, day):
    assert is_day(datetime(2026, 10, 24, clock.hour, clock.minute), S) is day


def test_next_boundary_rolls_over_midnight():
    assert next_boundary(datetime(2026, 10, 24, 22, 0), S) == datetime(
        2026, 10, 25, 6, 0
    )
    assert next_boundary(datetime(2026, 10, 24, 6, 0), S) == datetime(
        2026, 10, 24, 20, 30
    )


@pytest.mark.parametrize(
    ("outdoor", "cool"),
    [
        (None, 74),
        (30, 72),
        (45, 72),
        (52.5, 73),
        (60, 74),
        (70, 75),
        (80, 76),
        (95, 76),
    ],
)
def test_curve(outdoor, cool):
    assert curve_cool_point(outdoor, S) == cool


def test_settle_holds_inside_hysteresis():
    assert settle(72.6, 72) == 72
    assert settle(72.8, 72) == 73
    assert settle(72.5, None) == 73


def test_clamp_keeps_failsafe_and_gap():
    assert clamp_band(66, 74, S) == (66, 74)
    assert clamp_band(50, 90, S) == (60, 80)
    # Too narrow: heat gives way first.
    assert clamp_band(70, 72, S) == (67, 72)
    # Cool pinned below the floor plus gap moves up.
    assert clamp_band(58, 62, S) == (60, 65)
