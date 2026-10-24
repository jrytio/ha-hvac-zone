"""Write to thermostat (off is shadow mode) and fan circulation."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
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
    coordinator = entry.runtime_data
    async_add_entities([WriteSwitch(coordinator), FanSwitch(coordinator)])


class WriteSwitch(ZoneEntity, SwitchEntity):
    _attr_translation_key = "write"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZoneCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "write")

    @property
    def is_on(self) -> bool:
        return self.coordinator.writing

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_writing(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_writing(False)


class FanSwitch(ZoneEntity, SwitchEntity):
    _attr_translation_key = "fan_circulation"

    def __init__(self, coordinator: ZoneCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "fan_circulation")

    @property
    def is_on(self) -> bool:
        return self.coordinator.fan_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_fan_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_fan_enabled(False)
