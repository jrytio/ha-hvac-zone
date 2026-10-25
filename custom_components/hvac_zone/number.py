"""Every numeric setting of the zone."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ZoneConfigEntry
from .coordinator import ZoneCoordinator
from .entity import ZoneEntity
from .lib import NUMBER_SPECS, NumberSpec


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZoneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(ZoneNumber(entry.runtime_data, spec) for spec in NUMBER_SPECS)


class ZoneNumber(ZoneEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: ZoneCoordinator, spec: NumberSpec) -> None:
        """Initialize the number."""
        super().__init__(coordinator, spec.key)
        self._key = spec.key
        self._attr_translation_key = spec.key
        self._attr_native_min_value = spec.minimum
        self._attr_native_max_value = spec.maximum
        self._attr_native_step = spec.step
        self._attr_native_unit_of_measurement = spec.unit

    @property
    def native_value(self) -> float:
        return getattr(self.coordinator.engine.settings, self._key)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_setting(self._key, value)
