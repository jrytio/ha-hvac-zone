"""Cooler or warmer for a while, and back to the schedule."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    async_add_entities(
        [
            BumpButton(coordinator, "cooler", -1),
            BumpButton(coordinator, "warmer", 1),
            ResumeButton(coordinator),
        ]
    )


class BumpButton(ZoneEntity, ButtonEntity):
    def __init__(self, coordinator: ZoneCoordinator, key: str, sign: int) -> None:
        """Initialize the button."""
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._sign = sign

    async def async_press(self) -> None:
        sign = self._sign
        await self.coordinator.async_command(
            lambda engine, now: engine.bump(now, sign * engine.settings.bump_degrees)
        )


class ResumeButton(ZoneEntity, ButtonEntity):
    _attr_translation_key = "resume"

    def __init__(self, coordinator: ZoneCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "resume")

    async def async_press(self) -> None:
        await self.coordinator.async_command(
            lambda engine, now: engine.resume_schedule()
        )
