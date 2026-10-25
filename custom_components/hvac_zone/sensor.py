"""Why the zone is doing what it does."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ZoneConfigEntry
from .coordinator import ZoneCoordinator
from .entity import ZoneEntity


@dataclass(frozen=True, kw_only=True)
class ZoneSensorDescription(SensorEntityDescription):
    value: Callable[[ZoneCoordinator], Any]


def _rounded(value: float | None) -> float | None:
    return round(value, 1) if value is not None else None


SENSORS: tuple[ZoneSensorDescription, ...] = (
    ZoneSensorDescription(
        key="offset",
        translation_key="offset",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda c: _rounded(c.engine.state.offset),
    ),
    ZoneSensorDescription(
        key="spread",
        translation_key="spread",
        device_class=SensorDeviceClass.TEMPERATURE_DELTA,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda c: _rounded(c.readings.spread),
    ),
    ZoneSensorDescription(
        key="status",
        translation_key="status",
        value=lambda c: c.data.status[:255],
    ),
    ZoneSensorDescription(
        key="fan",
        translation_key="fan",
        value=lambda c: c.data.fan_reason[:255],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZoneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        ZoneSensor(entry.runtime_data, description) for description in SENSORS
    )


class ZoneSensor(ZoneEntity, SensorEntity):
    entity_description: ZoneSensorDescription

    def __init__(
        self, coordinator: ZoneCoordinator, description: ZoneSensorDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "status":
            return None
        data = self.coordinator.data
        return {
            "reasons": list(data.reasons),
            "thermostat_low": data.low,
            "thermostat_high": data.high,
            "would_write": data.write_band,
            "writing": self.coordinator.writing,
            "last_error": self.coordinator.last_error,
        }
