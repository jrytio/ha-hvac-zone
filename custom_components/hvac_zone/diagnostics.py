"""Diagnostics for the HVAC Zone integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from . import ZoneConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ZoneConfigEntry
) -> dict[str, Any]:
    """Return the zone's inputs, settings, state and last decision."""
    coordinator = entry.runtime_data
    return {
        "data": dict(entry.data),
        "options": dict(entry.options),
        "writing": coordinator.writing,
        "fan_enabled": coordinator.fan_enabled,
        "readings": asdict(coordinator.readings),
        "thermostat": asdict(coordinator.thermostat),
        "settings": coordinator.engine.settings.as_dict(),
        "state": coordinator.engine.state.as_dict(),
        "decision": asdict(coordinator.data) if coordinator.data else None,
        "last_error": coordinator.last_error,
    }
