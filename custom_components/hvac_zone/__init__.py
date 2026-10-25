"""The HVAC Zone integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import ZoneCoordinator

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]

type ZoneConfigEntry = ConfigEntry[ZoneCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ZoneConfigEntry) -> bool:
    """Set up one zone."""
    coordinator = ZoneCoordinator(hass, entry)
    await coordinator.async_load()
    entry.runtime_data = coordinator
    await coordinator.async_refresh()
    coordinator.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ZoneConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ZoneConfigEntry) -> bool:
    """Unload a zone, saving its state first."""
    await entry.runtime_data.async_save()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
