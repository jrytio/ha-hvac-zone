"""The tunable settings of one zone, with their bounds.

Each numeric setting becomes a number entity and each time setting a time
entity, so everything here is a slider or picker on a dashboard.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from datetime import time
from typing import Any


@dataclass(frozen=True, slots=True)
class NumberSpec:
    key: str
    name: str
    minimum: float
    maximum: float
    step: float
    unit: str


TEMP = "°F"
PERCENT = "%"
HOURS = "h"
MINUTES = "min"

NUMBER_SPECS: tuple[NumberSpec, ...] = (
    NumberSpec("cool_hot", "Cool point, hot weather", 70, 80, 1, TEMP),
    NumberSpec("cool_mild", "Cool point, mild weather", 68, 80, 1, TEMP),
    NumberSpec("cool_cold", "Cool point, cold weather", 66, 80, 1, TEMP),
    NumberSpec("outdoor_hot", "Outdoor mean, hot", 60, 100, 1, TEMP),
    NumberSpec("outdoor_mild", "Outdoor mean, mild", 40, 90, 1, TEMP),
    NumberSpec("outdoor_cold", "Outdoor mean, cold", 0, 70, 1, TEMP),
    NumberSpec("sleep_cool", "Sleep cool point", 64, 80, 1, TEMP),
    NumberSpec("gap", "Heat/cool gap", 4, 10, 1, TEMP),
    NumberSpec("heat_outdoor_below", "Heat only below outdoor", 30, 70, 1, TEMP),
    NumberSpec("heat_idle", "Heat point when warm outside", 50, 68, 1, TEMP),
    NumberSpec("bump_degrees", "Bump size", 1, 5, 1, TEMP),
    NumberSpec("bump_hours", "Bump length", 0.5, 8, 0.5, HOURS),
    NumberSpec("manual_hold_hours", "Wall change hold", 0.5, 8, 0.5, HOURS),
    NumberSpec("failsafe_floor", "Failsafe heat floor", 45, 68, 1, TEMP),
    NumberSpec("failsafe_ceiling", "Failsafe cool ceiling", 74, 90, 1, TEMP),
    NumberSpec("min_gap", "Thermostat minimum gap", 2, 10, 1, TEMP),
    NumberSpec("max_offset", "Offset limit", 0, 8, 0.5, TEMP),
    NumberSpec("humidity_engage", "Humidity event on above", 45, 80, 1, PERCENT),
    NumberSpec("humidity_release", "Humidity event off below", 40, 75, 1, PERCENT),
    NumberSpec("humidity_budget", "Humidity event budget", 1, 6, 1, TEMP),
    NumberSpec("humidity_floor", "Humidity event floor", 62, 76, 1, TEMP),
    NumberSpec("fan_spread_continuous", "Fan always on above", 2, 15, 0.5, TEMP),
    NumberSpec("fan_spread_pulsed", "Fan pulsed above", 1, 15, 0.5, TEMP),
    NumberSpec("fan_max_humidity", "Fan humidity ceiling", 30, 70, 1, PERCENT),
    NumberSpec("fan_humidity_rise", "Fan stops on humidity rise", 1, 10, 1, PERCENT),
    NumberSpec("fan_holdoff_minutes", "Fan wait after cooling", 0, 180, 5, MINUTES),
)

TIME_KEYS: dict[str, str] = {
    "day_start": "Day starts",
    "sleep_start": "Sleep starts",
    "fan_start": "Fan window starts",
    "fan_end": "Fan window ends",
}


@dataclass(frozen=True, slots=True)
class ZoneSettings:
    cool_hot: float = 76
    cool_mild: float = 74
    cool_cold: float = 72
    outdoor_hot: float = 80
    outdoor_mild: float = 60
    outdoor_cold: float = 45
    sleep_cool: float = 69
    gap: float = 5
    heat_outdoor_below: float = 50
    heat_idle: float = 62
    bump_degrees: float = 2
    bump_hours: float = 3
    manual_hold_hours: float = 3
    failsafe_floor: float = 60
    failsafe_ceiling: float = 80
    min_gap: float = 5
    max_offset: float = 5
    humidity_engage: float = 58
    humidity_release: float = 52
    humidity_budget: float = 3
    humidity_floor: float = 66
    fan_spread_continuous: float = 6
    fan_spread_pulsed: float = 3
    fan_max_humidity: float = 50
    fan_humidity_rise: float = 2
    fan_holdoff_minutes: float = 60
    day_start: time = time(6, 0)
    sleep_start: time = time(20, 30)
    fan_start: time = time(9, 0)
    fan_end: time = time(17, 0)

    def with_value(self, key: str, value: Any) -> ZoneSettings:
        if key not in {f.name for f in fields(self)}:
            raise KeyError(key)
        return replace(self, **{key: value})

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in TIME_KEYS:
            data[key] = data[key].isoformat(timespec="minutes")
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ZoneSettings:
        """Load stored settings, ignoring unknown keys and bad values."""
        settings = cls()
        if not data:
            return settings
        numbers = {spec.key for spec in NUMBER_SPECS}
        for key, value in data.items():
            try:
                if key in numbers:
                    settings = settings.with_value(key, float(value))
                elif key in TIME_KEYS:
                    settings = settings.with_value(key, time.fromisoformat(value))
            except TypeError, ValueError:
                continue
        return settings
