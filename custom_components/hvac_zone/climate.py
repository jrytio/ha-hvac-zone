"""The zone as a climate entity, in room-average terms."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ZoneConfigEntry
from .coordinator import ZoneCoordinator
from .entity import ZoneEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZoneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ZoneClimate(entry.runtime_data)])


class ZoneClimate(ZoneEntity, ClimateEntity):
    """Shows the room average and the heat/cool points the zone aims for.

    Setting the points shifts the schedule for a while (a bump); the zone
    goes back to its schedule when the bump ends.
    """

    _attr_name = None
    _attr_hvac_modes = [HVACMode.HEAT_COOL]
    _attr_hvac_mode = HVACMode.HEAT_COOL
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_target_temperature_step = 1

    def __init__(self, coordinator: ZoneCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "climate")

    @property
    def current_temperature(self) -> float | None:
        average = self.coordinator.data.room_average
        return round(average, 1) if average is not None else None

    @property
    def current_humidity(self) -> float | None:
        return self.coordinator.readings.humidity

    @property
    def target_temperature_low(self) -> float:
        return self.coordinator.data.heat_point

    @property
    def target_temperature_high(self) -> float:
        return self.coordinator.data.cool_point

    @property
    def min_temp(self) -> float:
        return self.coordinator.engine.settings.failsafe_floor

    @property
    def max_temp(self) -> float:
        return self.coordinator.engine.settings.failsafe_ceiling

    @property
    def hvac_action(self) -> HVACAction | None:
        action = self.coordinator.thermostat.hvac_action
        try:
            return HVACAction(action) if action else None
        except ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "thermostat_low": data.low,
            "thermostat_high": data.high,
            "period": data.period,
            "status": data.status,
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        low = kwargs.get(ATTR_TARGET_TEMP_LOW)
        high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
        readings = self.coordinator.readings
        await self.coordinator.async_command(
            lambda engine, now: engine.set_points(now, readings, low, high)
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Only heat/cool exists; the zone is never off."""
