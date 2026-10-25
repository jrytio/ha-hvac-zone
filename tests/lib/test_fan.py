"""The circulation guards, in order."""

from datetime import datetime, timedelta

from custom_components.hvac_zone.lib import (
    BAND_CONTINUOUS,
    BAND_OFF,
    BAND_PULSED,
    FAN_AUTO,
    FAN_ON,
    ZoneSettings,
    decide_fan,
)

S = ZoneSettings()
NOON = datetime(2026, 10, 24, 12, 5)


def fan(now=NOON, **kw):
    args = dict(
        spread=8.0,
        humidity=45.0,
        cooling=False,
        last_cooling_end=None,
        lockout_until=None,
        started_humidity=None,
        running=False,
    )
    args.update(kw)
    return decide_fan(now, S, **args)


def test_unbalanced_and_dry_runs_continuously():
    d = fan()
    assert (d.mode, d.band) == (FAN_ON, BAND_CONTINUOUS)
    assert d.started_humidity == 45.0


def test_pulsed_rests_half_the_time():
    assert fan(spread=4.0).mode == FAN_ON
    rest = fan(now=NOON.replace(minute=20), spread=4.0)
    assert (rest.mode, rest.band) == (FAN_AUTO, BAND_PULSED)


def test_balanced_rooms():
    assert fan(spread=2.0).band == BAND_OFF
    assert fan(spread=2.0).mode == FAN_AUTO


def test_guards():
    assert fan(now=NOON.replace(hour=18)).mode == FAN_AUTO
    assert fan(cooling=True).reason == "cooling"
    assert fan(last_cooling_end=NOON - timedelta(minutes=30)).mode == FAN_AUTO
    assert fan(last_cooling_end=NOON - timedelta(minutes=61)).mode == FAN_ON
    assert fan(humidity=None).mode == FAN_AUTO
    assert fan(humidity=50.0).mode == FAN_AUTO
    assert fan(lockout_until=NOON + timedelta(minutes=1)).mode == FAN_AUTO


def test_humidity_rise_locks_out():
    d = fan(humidity=47.0, started_humidity=45.0, running=True)
    assert d.mode == FAN_AUTO
    assert d.lockout_until == NOON + timedelta(minutes=60)


def test_running_keeps_its_starting_humidity():
    d = fan(humidity=46.0, started_humidity=45.0, running=True)
    assert (d.mode, d.started_humidity) == (FAN_ON, 45.0)
