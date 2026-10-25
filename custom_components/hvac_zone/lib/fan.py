"""Fan circulation: mix the zone when the rooms drift apart.

Running the blower over a wet coil puts the water back into the house, so
the fan stays off while cooling, for a hold-off after cooling ends, at high
humidity, and after it sees humidity rise while it runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import FAN_AUTO, FAN_ON
from .settings import ZoneSettings

BAND_CONTINUOUS = "continuous"
BAND_PULSED = "pulsed"
BAND_OFF = "off"
LOCKOUT = timedelta(minutes=60)


@dataclass(frozen=True, slots=True)
class FanDecision:
    mode: str
    band: str
    reason: str
    started_humidity: float | None
    lockout_until: datetime | None


def in_window(now: datetime, settings: ZoneSettings) -> bool:
    clock = now.time()
    start, end = settings.fan_start, settings.fan_end
    if start <= end:
        return start <= clock < end
    return clock >= start or clock < end


def spread_band(spread: float | None, settings: ZoneSettings) -> str:
    if spread is None:
        return BAND_OFF
    if spread >= settings.fan_spread_continuous:
        return BAND_CONTINUOUS
    if spread >= settings.fan_spread_pulsed:
        return BAND_PULSED
    return BAND_OFF


def decide_fan(
    now: datetime,
    settings: ZoneSettings,
    *,
    spread: float | None,
    humidity: float | None,
    cooling: bool,
    last_cooling_end: datetime | None,
    lockout_until: datetime | None,
    started_humidity: float | None,
    running: bool,
) -> FanDecision:
    """What the fan should be doing now. `running` means we have it on."""
    band = spread_band(spread, settings)

    def auto(reason: str, lockout: datetime | None = lockout_until) -> FanDecision:
        return FanDecision(FAN_AUTO, band, reason, None, lockout)

    if lockout_until and now < lockout_until:
        return auto("locked out after a humidity rise")
    if not in_window(now, settings):
        return auto("outside the fan window")
    if cooling:
        return auto("cooling")
    holdoff = timedelta(minutes=settings.fan_holdoff_minutes)
    if last_cooling_end and now - last_cooling_end < holdoff:
        return auto("coil drying after cooling")
    if humidity is None:
        return auto("no humidity reading")
    if humidity >= settings.fan_max_humidity:
        return auto("humidity too high")
    if (
        running
        and started_humidity is not None
        and humidity - started_humidity >= settings.fan_humidity_rise
    ):
        return auto("humidity rose while the fan ran", now + LOCKOUT)

    if band == BAND_OFF:
        return auto("rooms balanced")
    if band == BAND_PULSED and now.minute % 30 >= 15:
        return FanDecision(
            FAN_AUTO, band, "pulse rest", started_humidity, lockout_until
        )
    started = started_humidity if running and started_humidity is not None else humidity
    return FanDecision(FAN_ON, band, f"mixing ({band})", started, lockout_until)
