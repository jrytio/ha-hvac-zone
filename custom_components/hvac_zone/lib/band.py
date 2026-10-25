"""Pure band arithmetic: periods, the weather curve, failsafe limits."""

from __future__ import annotations

from datetime import datetime, time, timedelta
import math

from .settings import ZoneSettings

HYSTERESIS = 0.75


def is_day(now: datetime, settings: ZoneSettings) -> bool:
    clock = now.time()
    start, end = settings.day_start, settings.sleep_start
    if start <= end:
        return start <= clock < end
    return clock >= start or clock < end


def next_boundary(now: datetime, settings: ZoneSettings) -> datetime:
    """The next day-start or sleep-start after `now`."""
    candidates = []
    for moment in (settings.day_start, settings.sleep_start):
        at = _at(now, moment)
        if at <= now:
            at += timedelta(days=1)
        candidates.append(at)
    return min(candidates)


def _at(now: datetime, moment: time) -> datetime:
    return now.replace(hour=moment.hour, minute=moment.minute, second=0, microsecond=0)


def curve_cool_point(outdoor_mean: float | None, settings: ZoneSettings) -> float:
    """Day cool point from the outdoor 24 h mean, whole degrees.

    Linear between (cold, mild) and (mild, hot), flat outside them. With no
    outdoor reading the mild point is used.
    """
    s = settings
    if outdoor_mean is None:
        return float(s.cool_mild)
    points = sorted(
        [
            (s.outdoor_cold, s.cool_cold),
            (s.outdoor_mild, s.cool_mild),
            (s.outdoor_hot, s.cool_hot),
        ]
    )
    if outdoor_mean <= points[0][0]:
        return float(points[0][1])
    if outdoor_mean >= points[-1][0]:
        return float(points[-1][1])
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        if x0 <= outdoor_mean <= x1:
            if x1 == x0:
                return float(y1)
            value = y0 + (y1 - y0) * (outdoor_mean - x0) / (x1 - x0)
            return float(math.floor(value + 0.5))
    return float(s.cool_mild)


def settle(target: float, previous: int | None) -> int:
    """Round to a whole degree, holding the previous value inside hysteresis."""
    if previous is not None and abs(target - previous) < HYSTERESIS:
        return previous
    return math.floor(target + 0.5)


def clamp_band(low: int, high: int, settings: ZoneSettings) -> tuple[int, int]:
    """Apply the failsafe limits and the thermostat's minimum gap.

    The cool side wins a conflict: the heat point gives way first, and the
    cool point moves up only when the heat point is already at its floor.
    """
    floor = math.ceil(settings.failsafe_floor)
    ceiling = math.floor(settings.failsafe_ceiling)
    min_gap = math.ceil(settings.min_gap)
    high = min(max(high, floor + min_gap), ceiling)
    low = max(min(low, ceiling - min_gap), floor)
    if high - low < min_gap:
        low = max(high - min_gap, floor)
        high = max(high, low + min_gap)
    return low, high
