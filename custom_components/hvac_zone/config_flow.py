"""Config flow for the HVAC Zone integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
)
import probatio as vol

from .const import (
    CONF_HUMIDITY,
    CONF_OUTDOOR_MEAN,
    CONF_ROOM_SENSORS,
    CONF_SPREAD_SENSORS,
    CONF_THERMOSTAT,
    DOMAIN,
)

_TEMPERATURES = EntitySelector(
    EntitySelectorConfig(domain="sensor", device_class="temperature", multiple=True)
)


def _sensor_fields(defaults: dict[str, Any]) -> dict[Any, Any]:
    def key(name: str, required: bool = False) -> Any:
        marker = vol.Required if required else vol.Optional
        if name in defaults:
            return marker(name, description={"suggested_value": defaults[name]})
        return marker(name)

    return {
        key(CONF_ROOM_SENSORS, required=True): _TEMPERATURES,
        key(CONF_SPREAD_SENSORS): _TEMPERATURES,
        key(CONF_HUMIDITY): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class="humidity")
        ),
        key(CONF_OUTDOOR_MEAN): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class="temperature")
        ),
    }


class HvacZoneConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a zone: one real thermostat and the rooms it serves."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_THERMOSTAT])
            self._abort_if_unique_id_configured()
            name = user_input.pop(CONF_NAME)
            return self.async_create_entry(title=name, data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): TextSelector(),
                vol.Required(CONF_THERMOSTAT): EntitySelector(
                    EntitySelectorConfig(domain="climate")
                ),
                **_sensor_fields({}),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HvacZoneOptionsFlow()


class HvacZoneOptionsFlow(OptionsFlow):
    """Change which sensors feed the zone. The thermostat stays fixed."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(_sensor_fields(current))
        )
