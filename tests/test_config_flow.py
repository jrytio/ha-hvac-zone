"""Adding a zone and changing its sensors."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hvac_zone.const import (
    CONF_HUMIDITY,
    CONF_ROOM_SENSORS,
    CONF_THERMOSTAT,
    DOMAIN,
)

from .conftest import HUMIDITY, ROOMS, THERMOSTAT


async def test_add_zone(hass: HomeAssistant, house) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Downstairs zone",
            CONF_THERMOSTAT: THERMOSTAT,
            CONF_ROOM_SENSORS: ROOMS,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Downstairs zone"
    assert result["data"] == {CONF_THERMOSTAT: THERMOSTAT, CONF_ROOM_SENSORS: ROOMS}


async def test_one_zone_per_thermostat(hass: HomeAssistant, house, zone_entry) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Again", CONF_THERMOSTAT: THERMOSTAT, CONF_ROOM_SENSORS: ROOMS},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_change_sensors(hass: HomeAssistant, house, zone_entry) -> None:
    await hass.config_entries.async_setup(zone_entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(zone_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ROOM_SENSORS: ROOMS[:1], CONF_HUMIDITY: HUMIDITY}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert zone_entry.runtime_data.room_sensors == ROOMS[:1]
