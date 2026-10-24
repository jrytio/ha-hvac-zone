"""Shared base for the zone's entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZoneCoordinator


class ZoneEntity(CoordinatorEntity[ZoneCoordinator]):
    """One entity of a zone, all grouped under the zone's device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ZoneCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        assert entry is not None
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="HVAC Zone",
            model="Zone",
        )
