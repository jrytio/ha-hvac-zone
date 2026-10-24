"""The zone engine: one update in, one decision out. No Home Assistant here.

The caller feeds `update()` the sensor readings and the thermostat's state,
applies the writes the returned `Decision` asks for, then reports them back
with `record_write()` / `record_fan_write()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math

from .band import clamp_band, curve_cool_point, is_day, next_boundary, settle
from .fan import BAND_OFF, decide_fan
from .models import (
    COOLING,
    FAN_AUTO,
    FAN_ON,
    HEAT_COOL,
    HVAC_OFF,
    Bump,
    HumidityEvent,
    Override,
    Readings,
    Thermostat,
    Written,
    ZoneState,
)
from .settings import ZoneSettings

ECHO_GRACE = timedelta(minutes=2)
OFFSET_TIME_CONSTANT = timedelta(minutes=30)
HUMIDITY_STEP = timedelta(minutes=15)
MAX_BUMP = 5


@dataclass(frozen=True, slots=True)
class Decision:
    period: str
    room_average: float | None
    base_cool: float
    cool_point: float
    heat_point: float
    offset: float
    low: int
    high: int
    write_band: bool
    fan_mode: str | None
    fan_band: str
    fan_reason: str
    status: str
    reasons: tuple[str, ...] = field(default_factory=tuple)


class ZoneEngine:
    def __init__(self, settings: ZoneSettings, state: ZoneState | None = None) -> None:
        self.settings = settings
        self.state = state or ZoneState()

    # ── Commands ────────────────────────────────────────────────────────────

    def bump(self, now: datetime, degrees: float) -> None:
        """Shift both points by `degrees` (negative is cooler), stacking."""
        current = self._active_bump(now)
        delta = degrees + (current.cool_delta if current else 0)
        delta = max(-MAX_BUMP, min(MAX_BUMP, delta))
        self.state.bump = Bump(delta, delta, self._bump_until(now))

    def set_points(
        self,
        now: datetime,
        readings: Readings,
        low: float | None,
        high: float | None,
    ) -> None:
        """Someone set the zone's own climate entity: bump to those points."""
        base_cool = self._base_cool(now, readings)
        base_heat = base_cool - self.settings.gap
        current = self._active_bump(now)
        cool_delta = (high - base_cool) if high is not None else None
        heat_delta = (low - base_heat) if low is not None else None
        if cool_delta is None:
            cool_delta = current.cool_delta if current else 0
        if heat_delta is None:
            heat_delta = current.heat_delta if current else 0
        self.state.bump = Bump(
            max(-MAX_BUMP, min(MAX_BUMP, heat_delta)),
            max(-MAX_BUMP, min(MAX_BUMP, cool_delta)),
            self._bump_until(now),
        )

    def resume_schedule(self) -> None:
        """Drop any bump and any wall override, and rewrite the band."""
        self.state.bump = None
        self.state.override = None
        self.state.written = None
        self.state.fan_override_until = None

    def record_write(self, now: datetime, low: int, high: int) -> None:
        self.state.written = Written(low, high, now)
        self.state.override = None

    def record_fan_write(self, now: datetime, mode: str | None) -> None:
        self.state.fan_written = mode
        self.state.fan_written_at = now

    # ── The update ─────────────────────────────────────────────────────────

    def update(
        self,
        now: datetime,
        readings: Readings,
        thermostat: Thermostat,
        *,
        writing: bool,
        fan_enabled: bool,
    ) -> Decision:
        s, st = self.settings, self.state
        reasons: list[str] = []

        self._track_offset(now, readings, thermostat)
        self._track_cooling(now, thermostat)
        self._expire(now)
        if writing:
            self._detect_manual(now, thermostat)

        average = readings.room_average
        if average is None:
            average = thermostat.current_temperature

        day = is_day(now, s)
        base_cool = self._base_cool(now, readings)
        if day:
            reasons.append(
                f"day {base_cool:.0f}°F"
                + (
                    f" from {readings.outdoor_mean:.0f}°F outdoor mean"
                    if readings.outdoor_mean is not None
                    else " (no outdoor mean)"
                )
            )
        else:
            reasons.append(f"sleep {base_cool:.0f}°F")

        cool = base_cool
        heat = base_cool - s.gap
        bump = self._active_bump(now)
        if bump:
            cool += bump.cool_delta
            heat += bump.heat_delta
            reasons.append(f"bump {bump.cool_delta:+.0f}°F until {bump.until:%H:%M}")

        cool = self._humidity(now, readings, average, cool, reasons)
        heat = min(heat, cool - s.gap) if not bump else min(heat, cool - 1)

        offset = st.offset if st.offset is not None else 0.0
        offset = max(-s.max_offset, min(s.max_offset, offset))
        previous = st.proposed
        low = settle(heat + offset, previous[0] if previous else None)
        high = settle(cool + offset, previous[1] if previous else None)
        low, high = clamp_band(low, high, s)
        st.proposed = (low, high)

        write_band = False
        if st.override:
            reasons.append(f"wall change held until {st.override.until:%H:%M}")
        elif not thermostat.available:
            reasons.append("thermostat unavailable")
        else:
            written = st.written
            write_band = (
                written is None
                or (written.low, written.high) != (low, high)
                or thermostat.hvac_mode != HEAT_COOL
            )

        fan_mode, fan_band, fan_reason = self._fan(
            now, readings, thermostat, fan_enabled
        )

        status = "; ".join(reasons)
        return Decision(
            period="day" if day else "sleep",
            room_average=average,
            base_cool=base_cool,
            cool_point=cool,
            heat_point=heat,
            offset=offset,
            low=low,
            high=high,
            write_band=write_band,
            fan_mode=fan_mode,
            fan_band=fan_band,
            fan_reason=fan_reason,
            status=status,
            reasons=tuple(reasons),
        )

    # ── Pieces ─────────────────────────────────────────────────────────────

    def _base_cool(self, now: datetime, readings: Readings) -> float:
        if is_day(now, self.settings):
            return curve_cool_point(readings.outdoor_mean, self.settings)
        return float(self.settings.sleep_cool)

    def _bump_until(self, now: datetime) -> datetime:
        return min(
            now + timedelta(hours=self.settings.bump_hours),
            next_boundary(now, self.settings),
        )

    def _active_bump(self, now: datetime) -> Bump | None:
        bump = self.state.bump
        return bump if bump and now < bump.until else None

    def _expire(self, now: datetime) -> None:
        st = self.state
        if st.bump and now >= st.bump.until:
            st.bump = None
        if st.override and now >= st.override.until:
            st.override = None
            # Force a fresh write so the thermostat goes back to Auto.
            st.written = None
        if st.fan_override_until and now >= st.fan_override_until:
            st.fan_override_until = None
            st.fan_written = None

    def _track_offset(
        self, now: datetime, readings: Readings, thermostat: Thermostat
    ) -> None:
        average = readings.room_average
        if average is None or thermostat.current_temperature is None:
            return
        sample = thermostat.current_temperature - average
        st = self.state
        if st.offset is None or st.offset_at is None:
            st.offset = sample
        else:
            elapsed = max((now - st.offset_at).total_seconds(), 0)
            alpha = 1 - math.exp(-elapsed / OFFSET_TIME_CONSTANT.total_seconds())
            st.offset += alpha * (sample - st.offset)
        st.offset_at = now

    def _track_cooling(self, now: datetime, thermostat: Thermostat) -> None:
        st = self.state
        cooling = thermostat.available and thermostat.hvac_action == COOLING
        if st.cooling and not cooling:
            st.last_cooling_end = now
        st.cooling = cooling

    def _detect_manual(self, now: datetime, thermostat: Thermostat) -> None:
        """Spot a change made at the wall or in the thermostat's own app."""
        st, s = self.state, self.settings
        if not thermostat.available:
            return
        seen = thermostat.setpoints()
        hold = timedelta(hours=s.manual_hold_hours)

        if thermostat.hvac_mode == HVAC_OFF:
            # Off is never honoured: with no heat a dead integration means
            # frozen pipes. The next write puts the thermostat back in Auto.
            st.override = None
            return

        if st.override:
            if seen != st.override.seen:
                st.override = Override(self._hold_until(now, hold), seen)
            return

        written = st.written
        if written is None:
            return
        if now - written.at < ECHO_GRACE:
            # Whatever the thermostat reports this soon is our own write
            # coming back, possibly adjusted (it enforces its own minimum gap).
            written.seen_low = thermostat.target_low
            written.seen_high = thermostat.target_high
            return

        expected_low = written.seen_low if written.seen_low is not None else written.low
        expected_high = (
            written.seen_high if written.seen_high is not None else written.high
        )
        changed = thermostat.hvac_mode != HEAT_COOL or (
            _differs(thermostat.target_low, expected_low)
            or _differs(thermostat.target_high, expected_high)
        )
        if changed:
            st.override = Override(self._hold_until(now, hold), seen)

        if (
            st.fan_written is not None
            and thermostat.fan_mode is not None
            and thermostat.fan_mode != st.fan_written
            and st.fan_written_at is not None
            and now - st.fan_written_at >= ECHO_GRACE
        ):
            st.fan_override_until = self._hold_until(now, hold)

    def _hold_until(self, now: datetime, hold: timedelta) -> datetime:
        return min(now + hold, next_boundary(now, self.settings))

    def _humidity(
        self,
        now: datetime,
        readings: Readings,
        average: float | None,
        cool: float,
        reasons: list[str],
    ) -> float:
        s, st = self.settings, self.state
        humidity = readings.humidity
        if humidity is not None and average is not None:
            if st.humidity is None and humidity > s.humidity_engage:
                st.humidity = HumidityEvent(engage_average=average)
            elif st.humidity is not None and humidity < s.humidity_release:
                st.humidity = None
        event = st.humidity
        if event is None:
            return cool
        if average is not None and (
            event.stepped_at is None or now - event.stepped_at >= HUMIDITY_STEP
        ):
            event.target = max(
                s.humidity_floor,
                event.engage_average - s.humidity_budget,
                math.floor(average) - 1,
            )
            event.stepped_at = now
        if event.target is None:
            return cool
        reasons.append(f"humidity event, cool to {event.target:.0f}°F")
        return min(cool, event.target)

    def _fan(
        self,
        now: datetime,
        readings: Readings,
        thermostat: Thermostat,
        enabled: bool,
    ) -> tuple[str | None, str, str]:
        """Return (fan mode to write or None, band, reason)."""
        st = self.state
        if st.fan_override_until:
            until = st.fan_override_until
            return None, BAND_OFF, f"wall change held until {until:%H:%M}"
        if not enabled:
            # Hand the fan back once if we were the ones running it.
            if st.fan_written == FAN_ON:
                return FAN_AUTO, BAND_OFF, "circulation switched off"
            return None, BAND_OFF, "circulation switched off"
        if not thermostat.available:
            return None, BAND_OFF, "thermostat unavailable"
        decision = decide_fan(
            now,
            self.settings,
            spread=readings.spread,
            humidity=readings.humidity,
            cooling=st.cooling,
            last_cooling_end=st.last_cooling_end,
            lockout_until=st.fan_lockout_until,
            started_humidity=st.fan_started_humidity,
            running=st.fan_written == FAN_ON,
        )
        st.fan_started_humidity = decision.started_humidity
        st.fan_lockout_until = decision.lockout_until
        mode: str | None = decision.mode
        if mode == FAN_AUTO and st.fan_written != FAN_ON:
            # Only hand back a fan we turned on; never take one someone else did.
            mode = None
        elif mode == thermostat.fan_mode and mode == st.fan_written:
            mode = None
        return mode, decision.band, decision.reason


def _differs(actual: float | None, expected: float | None) -> bool:
    if actual is None or expected is None:
        return False
    return abs(actual - expected) >= 1
