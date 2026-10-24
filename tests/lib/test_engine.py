"""The engine, one scenario at a time.

`Zone` plays both sides: it applies each decision to a fake thermostat the
way the coordinator would, so tests read as a timeline.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from custom_components.hvac_zone.lib import (
    FAN_AUTO,
    FAN_ON,
    HEAT_COOL,
    Readings,
    Thermostat,
    ZoneEngine,
    ZoneSettings,
)

START = datetime(2026, 10, 24, 12, 0)


class Zone:
    def __init__(self, settings: ZoneSettings | None = None, *, offset=0.0):
        self.engine = ZoneEngine(settings or ZoneSettings())
        self.now = START
        self.room = 72.0
        self.readings = Readings(
            room_temps=(72.0,),
            spread_temps=(70.0, 72.0),
            humidity=45.0,
            outdoor_mean=60.0,
        )
        self.offset = offset
        self.thermostat = Thermostat(
            hvac_mode="cool", target_temperature=76.0, current_temperature=72.0
        )
        self.writing = True
        self.fan_enabled = True
        self.writes = 0

    def at(self, **delta) -> Zone:
        self.now += timedelta(**delta)
        return self

    def wall(self, **changes) -> None:
        """Someone changes the thermostat by hand."""
        self.thermostat = replace(self.thermostat, **changes)

    def tick(self):
        self.thermostat = replace(
            self.thermostat, current_temperature=self.room + self.offset
        )
        self.readings = replace(self.readings, room_temps=(self.room,))
        d = self.engine.update(
            self.now,
            self.readings,
            self.thermostat,
            writing=self.writing,
            fan_enabled=self.fan_enabled,
        )
        if self.writing and d.write_band:
            self.thermostat = replace(
                self.thermostat,
                hvac_mode=HEAT_COOL,
                target_low=float(d.low),
                target_high=float(d.high),
                target_temperature=None,
            )
            self.engine.record_write(self.now, d.low, d.high)
            self.writes += 1
        if self.writing and d.fan_mode is not None:
            self.thermostat = replace(self.thermostat, fan_mode=d.fan_mode)
            self.engine.record_fan_write(self.now, d.fan_mode)
        return d

    @property
    def band(self):
        t = self.thermostat
        return t.hvac_mode, t.target_low, t.target_high


def test_first_tick_puts_thermostat_in_auto():
    z = Zone()
    d = z.tick()
    assert (d.low, d.high) == (69, 74)
    assert z.band == (HEAT_COOL, 69.0, 74.0)
    z.at(minutes=1).tick()
    assert z.writes == 1


def test_offset_moves_the_band_with_the_warm_sensor():
    z = Zone(offset=3.5)
    d = z.tick()
    assert (d.low, d.high) == (73, 78)  # 69/74 room, read 3.5 warm


def test_offset_is_capped():
    z = Zone(offset=9.0)
    d = z.tick()
    assert d.offset == 5.0


def test_shadow_mode_never_writes():
    z = Zone()
    z.writing = False
    d = z.tick()
    assert d.write_band  # it would, but the coordinator is told not to
    assert z.band == ("cool", None, None)


def test_sleep_and_weather():
    z = Zone()
    z.now = START.replace(hour=22)
    assert (z.tick().low, z.tick().high) == (64, 69)
    z = Zone()
    z.readings = replace(z.readings, outdoor_mean=85.0)
    assert z.tick().high == 76
    z = Zone()
    z.readings = replace(z.readings, outdoor_mean=40.0)
    assert (z.tick().low, z.tick().high) == (67, 72)


def test_bump_stacks_then_expires():
    z = Zone()
    z.tick()
    z.engine.bump(z.now, -2)
    assert z.tick().high == 72
    z.engine.bump(z.now, -2)
    assert z.tick().high == 70
    z.at(hours=3, minutes=1)
    assert z.tick().high == 74


def test_bump_ends_at_the_next_boundary():
    z = Zone()
    z.now = START.replace(hour=19)
    z.tick()
    z.engine.bump(z.now, -2)
    assert z.engine.state.bump.until == START.replace(hour=20, minute=30)


def test_set_points_on_the_zone_entity():
    z = Zone()
    z.tick()
    z.engine.set_points(z.now, z.readings, 66, 71)
    d = z.tick()
    assert (d.low, d.high) == (66, 71)


def test_resume_schedule_drops_bump_and_override():
    z = Zone()
    z.tick()
    z.engine.bump(z.now, -3)
    z.at(minutes=5).wall(target_high=70.0)
    z.tick()
    z.engine.resume_schedule()
    assert z.tick().high == 74
    assert z.band == (HEAT_COOL, 69.0, 74.0)


# ── Wall changes ───────────────────────────────────────────────────────────


def test_the_echo_of_our_own_write_is_not_a_wall_change():
    z = Zone()
    z.tick()
    # The thermostat nudges the low point to keep its own gap.
    z.at(seconds=30).wall(target_low=68.0)
    z.tick()
    z.at(minutes=10).tick()
    assert z.engine.state.override is None
    assert z.writes == 1


def test_wall_change_is_held_then_released():
    z = Zone()
    z.tick()
    z.at(minutes=10).wall(target_high=71.0)
    d = z.tick()
    assert not d.write_band
    assert z.engine.state.override.until == z.now + timedelta(hours=3)
    z.at(hours=2).tick()
    assert z.band[2] == 71.0
    z.at(hours=1, minutes=1).tick()
    assert z.band == (HEAT_COOL, 69.0, 74.0)


def test_another_wall_change_extends_the_hold():
    z = Zone()
    z.tick()
    z.at(minutes=10).wall(target_high=71.0)
    z.tick()
    z.at(hours=2).wall(target_high=70.0)
    z.tick()
    assert z.engine.state.override.until == z.now + timedelta(hours=3)


def test_off_then_a_wall_change_overnight():
    """Off is undone at once; a later wall change is held until morning."""
    z = Zone()
    z.now = START.replace(hour=23, minute=15)
    z.tick()
    assert z.band == (HEAT_COOL, 64.0, 69.0)
    # Someone switches it off: not honoured, back to Auto straight away.
    z.at(minutes=5).wall(hvac_mode="off")
    z.tick()
    assert z.band == (HEAT_COOL, 64.0, 69.0)
    # Early morning, cool to 68 at the wall.
    z.now = START.replace(day=25, hour=3, minute=45)
    z.wall(hvac_mode="cool", target_temperature=68.0, target_low=None, target_high=None)
    z.tick()
    assert z.engine.state.override.until == START.replace(day=25, hour=6)
    z.at(hours=2).tick()
    assert z.band[0] == "cool"
    # 06:00 is the day boundary: hold over, day band back in Auto.
    z.now = START.replace(day=25, hour=6)
    z.tick()
    assert z.band == (HEAT_COOL, 69.0, 74.0)


def test_unavailable_thermostat_is_left_alone():
    z = Zone()
    z.thermostat = Thermostat(available=False)
    d = z.tick()
    assert not d.write_band
    assert "thermostat unavailable" in d.status


# ── Humidity ───────────────────────────────────────────────────────────────


def test_humidity_event_steps_down_and_releases():
    z = Zone()
    z.readings = replace(z.readings, humidity=60.0)
    d = z.tick()
    assert d.high == 71  # floor(72) - 1
    assert d.low == 66
    z.room = 70.5
    assert z.at(minutes=10).tick().high == 71  # not yet a new step
    assert z.at(minutes=5).tick().high == 69  # budget: 72 - 3
    z.room = 68.0
    assert z.at(minutes=15).tick().high == 69  # budget holds
    z.readings = replace(z.readings, humidity=51.0)
    assert z.at(minutes=1).tick().high == 74


def test_humidity_event_respects_the_floor():
    z = Zone(ZoneSettings(humidity_floor=71))
    z.readings = replace(z.readings, humidity=60.0)
    z.room = 70.0
    assert z.tick().high == 71


# ── Fan ────────────────────────────────────────────────────────────────────


def test_fan_runs_when_unbalanced_and_hands_back():
    z = Zone()
    z.readings = replace(z.readings, spread_temps=(65.0, 75.0))
    z.tick()
    assert z.thermostat.fan_mode == FAN_ON
    z.readings = replace(z.readings, spread_temps=(70.0, 71.0))
    z.at(minutes=1).tick()
    assert z.thermostat.fan_mode == FAN_AUTO


def test_fan_someone_else_turned_on_is_left_on():
    z = Zone()
    z.wall(fan_mode=FAN_ON)
    d = z.tick()
    assert d.fan_mode is None
    assert z.thermostat.fan_mode == FAN_ON


def test_fan_wall_change_is_held():
    z = Zone()
    z.readings = replace(z.readings, spread_temps=(65.0, 75.0))
    z.tick()
    z.at(minutes=10).wall(fan_mode=FAN_AUTO)
    d = z.tick()
    assert d.fan_mode is None
    assert "wall change held" in d.fan_reason


def test_fan_stops_when_cooling_and_waits_for_the_coil():
    z = Zone()
    z.readings = replace(z.readings, spread_temps=(65.0, 75.0))
    z.tick()
    z.wall(hvac_action="cooling")
    z.at(minutes=1).tick()
    assert z.thermostat.fan_mode == FAN_AUTO
    z.wall(hvac_action="idle")
    z.at(minutes=1).tick()
    assert z.thermostat.fan_mode == FAN_AUTO
    z.at(minutes=61).tick()
    assert z.thermostat.fan_mode == FAN_ON


def test_fan_switch_off_hands_back_once():
    z = Zone()
    z.readings = replace(z.readings, spread_temps=(65.0, 75.0))
    z.tick()
    z.fan_enabled = False
    assert z.at(minutes=1).tick().fan_mode == FAN_AUTO
    assert z.at(minutes=1).tick().fan_mode is None


# ── Offset ─────────────────────────────────────────────────────────────────


def test_offset_follows_slowly():
    z = Zone(offset=2.0)
    z.tick()
    z.offset = 4.0
    d = z.at(minutes=30).tick()
    assert 3.2 < d.offset < 3.3  # 1 - e^-1 of the way
