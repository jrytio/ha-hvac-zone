"""State and settings survive a round trip through storage."""

from datetime import datetime, time

from custom_components.hvac_zone.lib import ZoneSettings, ZoneState
from custom_components.hvac_zone.lib.models import (
    Bump,
    HumidityEvent,
    Override,
    Readings,
    Written,
)

AT = datetime(2026, 10, 24, 12, 0)


def test_state_round_trip():
    state = ZoneState(
        bump=Bump(-2, -2, AT),
        override=Override(AT, ("cool", None, None, 68.0)),
        humidity=HumidityEvent(72.0, 69.0, AT),
        offset=3.5,
        offset_at=AT,
        proposed=(66, 74),
        written=Written(66, 74, AT, 66.0, 74.0),
        cooling=True,
        last_cooling_end=AT,
        fan_written="on",
        fan_written_at=AT,
        fan_override_until=AT,
        fan_started_humidity=45.0,
        fan_lockout_until=AT,
    )
    assert ZoneState.from_dict(state.as_dict()) == state


def test_bad_state_starts_fresh():
    assert ZoneState.from_dict({"bump": {"until": 3}}) == ZoneState()
    assert ZoneState.from_dict(None) == ZoneState()


def test_settings_round_trip_and_bad_values():
    settings = ZoneSettings().with_value("gap", 4.0).with_value("day_start", time(7))
    assert ZoneSettings.from_dict(settings.as_dict()) == settings
    loaded = ZoneSettings.from_dict({"gap": "x", "nope": 1, "sleep_start": "bad"})
    assert loaded == ZoneSettings()


def test_readings():
    r = Readings(room_temps=(70.0, 72.0, 74.0), spread_temps=(65.0, 75.0))
    assert r.room_average == 72.0
    assert r.spread == 10.0
    assert Readings(room_temps=(70.0,)).spread is None
    assert Readings().room_average is None
