"""Humidity event and wall-change flags."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    async_add_entities([HumidityEvent(coordinator), WallOverride(coordinator)])


class HumidityEvent(ZoneEntity, BinarySensorEntity):
    _attr_translation_key = "humidity_event"

    def __init__(self, coordinator: ZoneCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "humidity_event")

    @property
    def is_on(self) -> bool:
        return self.coordinator.engine.state.humidity is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        event = self.coordinator.engine.state.humidity
        if event is None:
            return None
        return {"engage_average": event.engage_average, "cool_to": event.target}


class WallOverride(ZoneEntity, BinarySensorEntity):
    _attr_translation_key = "wall_override"

    def __init__(self, coordinator: ZoneCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "wall_override")

    @property
    def is_on(self) -> bool:
        return self.coordinator.engine.state.override is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        override = self.coordinator.engine.state.override
        return {"until": override.until.isoformat()} if override else None
