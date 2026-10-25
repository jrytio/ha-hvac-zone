"""The zone end to end: shadow mode, writing, wall changes, buttons."""

from datetime import timedelta
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.hvac_zone.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import THERMOSTAT, ZONE, set_rooms, set_thermostat, setup_integration

NOON = "2026-10-24 12:00:00-04:00"


async def press(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )


async def switch_on(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": entity_id}, blocking=True
    )


async def test_shadow_mode_writes_nothing(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, house, calls, zone_entry
) -> None:
    freezer.move_to(NOON)
    await setup_integration(hass)
    assert zone_entry.state is ConfigEntryState.LOADED
    state = hass.states.get(ZONE)
    assert state.state == "heat_cool"
    assert state.attributes["current_temperature"] == 72
    assert state.attributes["target_temp_low"] == 69
    assert state.attributes["target_temp_high"] == 74
    # The thermostat reads 3.5 warm, so the band it would get is shifted.
    assert state.attributes["thermostat_low"] == 73
    assert state.attributes["thermostat_high"] == 78
    assert hass.states.get("switch.downstairs_zone_write_to_thermostat").state == "off"
    assert not calls["set_temperature"]


async def test_writing_puts_thermostat_in_auto(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, house, calls, zone_entry
) -> None:
    freezer.move_to(NOON)
    await setup_integration(hass)
    await switch_on(hass, "switch.downstairs_zone_write_to_thermostat")
    [call] = calls["set_temperature"]
    assert call.data == {
        "entity_id": THERMOSTAT,
        "hvac_mode": "heat_cool",
        "target_temp_low": 73,
        "target_temp_high": 78,
    }


async def test_wall_change_is_held_then_auto_again(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, house, calls, zone_entry
) -> None:
    freezer.move_to(NOON)
    await setup_integration(hass)
    await switch_on(hass, "switch.downstairs_zone_write_to_thermostat")
    set_thermostat(hass, "heat_cool", target_temp_low=73, target_temp_high=78)
    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    set_thermostat(hass, "cool", temperature=70)
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert (
        hass.states.get("binary_sensor.downstairs_zone_wall_change_held").state == "on"
    )
    assert len(calls["set_temperature"]) == 1

    freezer.tick(timedelta(hours=3, minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert (
        hass.states.get("binary_sensor.downstairs_zone_wall_change_held").state == "off"
    )
    assert calls["set_temperature"][-1].data["hvac_mode"] == "heat_cool"


async def test_off_is_put_back_to_auto(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, house, calls, zone_entry
) -> None:
    freezer.move_to(NOON)
    await setup_integration(hass)
    await switch_on(hass, "switch.downstairs_zone_write_to_thermostat")
    set_thermostat(hass, "heat_cool", target_temp_low=73, target_temp_high=78)
    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    set_thermostat(hass, "off")
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    # The mock never changes the thermostat, so it may be written more than once.
    assert len(calls["set_temperature"]) >= 2
    assert calls["set_temperature"][-1].data["hvac_mode"] == "heat_cool"


async def test_cooler_button_and_back_to_schedule(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, house, calls, zone_entry
) -> None:
    freezer.move_to(NOON)
    await setup_integration(hass)
    await press(hass, "button.downstairs_zone_cooler_for_a_while")
    assert hass.states.get(ZONE).attributes["target_temp_high"] == 72
    await press(hass, "button.downstairs_zone_back_to_schedule")
    assert hass.states.get(ZONE).attributes["target_temp_high"] == 74


async def test_setting_the_zone_bumps_it(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, house, zone_entry
) -> None:
    freezer.move_to(NOON)
    await setup_integration(hass)
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": ZONE, "target_temp_low": 66, "target_temp_high": 71},
        blocking=True,
    )
    attrs = hass.states.get(ZONE).attributes
    assert (attrs["target_temp_low"], attrs["target_temp_high"]) == (66, 71)


async def test_settings_persist_across_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, house, calls, zone_entry
) -> None:
    freezer.move_to(NOON)
    await setup_integration(hass)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.downstairs_zone_heat_cool_gap", "value": 4},
        blocking=True,
    )
    await hass.services.async_call(
        "time",
        "set_value",
        {"entity_id": "time.downstairs_zone_sleep_starts", "time": "21:00:00"},
        blocking=True,
    )
    await hass.config_entries.async_reload(zone_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("number.downstairs_zone_heat_cool_gap").state == "4.0"
    assert hass.states.get("time.downstairs_zone_sleep_starts").state == "21:00:00"
    assert hass.states.get(ZONE).attributes["target_temp_low"] == 70


async def test_fan_circulation(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, house, calls, zone_entry
) -> None:
    freezer.move_to(NOON)
    set_rooms(hass, 66, 75)
    await setup_integration(hass)
    assert hass.states.get("sensor.downstairs_zone_room_spread").state == "9.0"
    await switch_on(hass, "switch.downstairs_zone_write_to_thermostat")
    assert not calls["set_fan_mode"]
    await switch_on(hass, "switch.downstairs_zone_fan_circulation")
    [call] = calls["set_fan_mode"]
    assert call.data == {"entity_id": THERMOSTAT, "fan_mode": "on"}


async def test_unavailable_sensors_and_diagnostics(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, house, calls, zone_entry
) -> None:
    freezer.move_to(NOON)
    hass.states.async_set("sensor.living_temperature", "unavailable")
    set_thermostat(hass, "unavailable")
    await setup_integration(hass)
    assert hass.states.get(ZONE).attributes["current_temperature"] == 72
    info = await async_get_config_entry_diagnostics(hass, zone_entry)
    assert info["thermostat"]["available"] is False
    assert info["decision"]["write_band"] is False


async def test_band_is_widened_before_it_moves(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, house, calls, zone_entry
) -> None:
    """Raising both points goes through a wider band, so the gap never shrinks."""
    freezer.move_to(NOON)
    set_thermostat(hass, "heat_cool", target_temp_low=68, target_temp_high=73)
    with patch("custom_components.hvac_zone.coordinator.WIDEN_PAUSE", 0):
        await setup_integration(hass)
        await switch_on(hass, "switch.downstairs_zone_write_to_thermostat")
    writes = [
        (c.data["target_temp_low"], c.data["target_temp_high"])
        for c in calls["set_temperature"]
    ]
    assert writes == [(68, 78), (73, 78)]
