"""Plain data passed between Home Assistant and the zone engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

HEAT_COOL = "heat_cool"
HVAC_OFF = "off"
COOLING = "cooling"
FAN_ON = "on"
FAN_AUTO = "auto"


@dataclass(frozen=True, slots=True)
class Readings:
    """Sensor values for one update. Unavailable sensors are left out."""

    room_temps: tuple[float, ...] = ()
    spread_temps: tuple[float, ...] = ()
    humidity: float | None = None
    outdoor_mean: float | None = None
    outdoor_now: float | None = None

    @property
    def outdoor(self) -> float | None:
        """The current outdoor temperature, else the mean."""
        return self.outdoor_now if self.outdoor_now is not None else self.outdoor_mean

    @property
    def room_average(self) -> float | None:
        if not self.room_temps:
            return None
        return sum(self.room_temps) / len(self.room_temps)

    @property
    def spread(self) -> float | None:
        temps = self.spread_temps or self.room_temps
        if len(temps) < 2:
            return None
        return max(temps) - min(temps)


@dataclass(frozen=True, slots=True)
class Thermostat:
    """What the real thermostat reports."""

    available: bool = True
    hvac_mode: str | None = HEAT_COOL
    hvac_action: str | None = None
    current_temperature: float | None = None
    target_low: float | None = None
    target_high: float | None = None
    target_temperature: float | None = None
    fan_mode: str | None = FAN_AUTO

    def setpoints(self) -> tuple[str | None, float | None, float | None, float | None]:
        return (
            self.hvac_mode,
            self.target_low,
            self.target_high,
            self.target_temperature,
        )


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(slots=True)
class Bump:
    heat_delta: float
    cool_delta: float
    until: datetime


@dataclass(slots=True)
class Override:
    """A change someone made at the thermostat, honoured until `until`."""

    until: datetime
    seen: tuple[str | None, float | None, float | None, float | None]


@dataclass(slots=True)
class HumidityEvent:
    engage_average: float
    target: float | None = None
    stepped_at: datetime | None = None


@dataclass(slots=True)
class Written:
    """The last band we sent, and what the thermostat echoed back."""

    low: int
    high: int
    at: datetime
    seen_low: float | None = None
    seen_high: float | None = None
    retry: bool = False


@dataclass(slots=True)
class ZoneState:
    """Everything the engine remembers between updates and across restarts."""

    bump: Bump | None = None
    override: Override | None = None
    humidity: HumidityEvent | None = None
    offset: float | None = None
    offset_at: datetime | None = None
    proposed: tuple[int, int] | None = None
    written: Written | None = None
    cooling: bool = False
    heat_allowed: bool = True
    last_cooling_end: datetime | None = None
    fan_written: str | None = None
    fan_written_at: datetime | None = None
    fan_override_until: datetime | None = None
    fan_started_humidity: float | None = None
    fan_lockout_until: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "bump": self.bump
            and {
                "heat_delta": self.bump.heat_delta,
                "cool_delta": self.bump.cool_delta,
                "until": _dt(self.bump.until),
            },
            "override": self.override
            and {"until": _dt(self.override.until), "seen": list(self.override.seen)},
            "humidity": self.humidity
            and {
                "engage_average": self.humidity.engage_average,
                "target": self.humidity.target,
                "stepped_at": _dt(self.humidity.stepped_at),
            },
            "offset": self.offset,
            "offset_at": _dt(self.offset_at),
            "proposed": list(self.proposed) if self.proposed else None,
            "written": self.written
            and {**asdict(self.written), "at": _dt(self.written.at)},
            "cooling": self.cooling,
            "heat_allowed": self.heat_allowed,
            "last_cooling_end": _dt(self.last_cooling_end),
            "fan_written": self.fan_written,
            "fan_written_at": _dt(self.fan_written_at),
            "fan_override_until": _dt(self.fan_override_until),
            "fan_started_humidity": self.fan_started_humidity,
            "fan_lockout_until": _dt(self.fan_lockout_until),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ZoneState:
        """Load stored state. Anything unreadable starts fresh."""
        if not data:
            return cls()
        try:
            bump = data.get("bump")
            override = data.get("override")
            humidity = data.get("humidity")
            written = data.get("written")
            proposed = data.get("proposed")
            return cls(
                bump=bump
                and Bump(bump["heat_delta"], bump["cool_delta"], _parse(bump["until"])),
                override=override
                and Override(_parse(override["until"]), tuple(override["seen"])),
                humidity=humidity
                and HumidityEvent(
                    humidity["engage_average"],
                    humidity.get("target"),
                    _parse(humidity.get("stepped_at")),
                ),
                offset=data.get("offset"),
                offset_at=_parse(data.get("offset_at")),
                proposed=tuple(proposed) if proposed else None,
                written=written
                and Written(
                    written["low"],
                    written["high"],
                    _parse(written["at"]),
                    written.get("seen_low"),
                    written.get("seen_high"),
                    written.get("retry", False),
                ),
                cooling=data.get("cooling", False),
                heat_allowed=data.get("heat_allowed", True),
                last_cooling_end=_parse(data.get("last_cooling_end")),
                fan_written=data.get("fan_written"),
                fan_written_at=_parse(data.get("fan_written_at")),
                fan_override_until=_parse(data.get("fan_override_until")),
                fan_started_humidity=data.get("fan_started_humidity"),
                fan_lockout_until=_parse(data.get("fan_lockout_until")),
            )
        except KeyError, TypeError, ValueError:
            return cls()
