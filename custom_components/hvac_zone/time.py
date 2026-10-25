"""The zone's schedule times."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ZoneConfigEntry
from .coordinator import ZoneCoordinator
from .entity import ZoneEntity
from .lib import TIME_KEYS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZoneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(ZoneTime(entry.runtime_data, key) for key in TIME_KEYS)


class ZoneTime(ZoneEntity, TimeEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZoneCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, key)
        self._key = key
        self._attr_translation_key = key

    @property
    def native_value(self) -> time:
        return getattr(self.coordinator.engine.settings, self._key)

    async def async_set_value(self, value: time) -> None:
        await self.coordinator.async_set_setting(self._key, value)
