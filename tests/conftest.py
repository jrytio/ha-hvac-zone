"""Fixtures for the Home Assistant layer."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.hvac_zone.const import (
    CONF_HUMIDITY,
    CONF_OUTDOOR_MEAN,
    CONF_OUTDOOR_NOW,
    CONF_ROOM_SENSORS,
    CONF_SPREAD_SENSORS,
    CONF_THERMOSTAT,
    DOMAIN,
)

THERMOSTAT = "climate.downstairs"
ROOMS = ["sensor.living_temperature", "sensor.office_temperature"]
HUMIDITY = "sensor.downstairs_humidity"
OUTDOOR = "sensor.outdoor_mean"
OUTDOOR_NOW = "sensor.outdoor_temperature"
ZONE = "climate.downstairs_zone"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load the integration from custom_components."""


@pytest.fixture(autouse=True)
def no_widen_pause():
    """Don't wait between the widened band and the target in tests."""
    with patch("custom_components.hvac_zone.coordinator.WIDEN_PAUSE", 0):
        yield


@pytest.fixture(autouse=True)
def fahrenheit(hass: HomeAssistant) -> None:
    """The zone works in °F, like the house it was built for."""
    hass.config.units = US_CUSTOMARY_SYSTEM


def set_thermostat(hass: HomeAssistant, mode: str = "cool", **attrs) -> None:
    base = {
        "hvac_modes": ["off", "heat", "cool", "heat_cool"],
        "hvac_action": "idle",
        "current_temperature": 75.5,
        "temperature": 76,
        "fan_mode": "auto",
        "fan_modes": ["auto", "on"],
    }
    hass.states.async_set(THERMOSTAT, mode, {**base, **attrs})


def set_rooms(hass: HomeAssistant, *temps: float, humidity: float = 45) -> None:
    for entity_id, temp in zip(ROOMS, temps, strict=True):
        hass.states.async_set(entity_id, str(temp), {"unit_of_measurement": "°F"})
    hass.states.async_set(HUMIDITY, str(humidity), {"unit_of_measurement": "%"})
    hass.states.async_set(OUTDOOR, "60", {"unit_of_measurement": "°F"})
    # Cold enough that the heat point follows the band.
    hass.states.async_set(OUTDOOR_NOW, "40", {"unit_of_measurement": "°F"})


@pytest.fixture
def house(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    set_rooms(hass, 72, 72)


@pytest.fixture
async def calls(hass: HomeAssistant) -> dict[str, list[ServiceCall]]:
    """Record writes to the thermostat.

    The climate integration registers the real services when it loads, so
    load it first and replace them.
    """
    assert await async_setup_component(hass, "climate", {})
    return {
        "set_temperature": async_mock_service(hass, "climate", "set_temperature"),
        "set_fan_mode": async_mock_service(hass, "climate", "set_fan_mode"),
    }


@pytest.fixture
def zone_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Downstairs zone",
        unique_id=THERMOSTAT,
        data={
            CONF_THERMOSTAT: THERMOSTAT,
            CONF_ROOM_SENSORS: ROOMS,
            CONF_SPREAD_SENSORS: [],
            CONF_HUMIDITY: HUMIDITY,
            CONF_OUTDOOR_MEAN: OUTDOOR,
            CONF_OUTDOOR_NOW: OUTDOOR_NOW,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def setup_integration(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
