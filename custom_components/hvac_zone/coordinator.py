"""Runs one zone: reads Home Assistant, asks the engine, writes the thermostat."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
import logging
from typing import Any

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_HUMIDITY,
    CONF_OUTDOOR_MEAN,
    CONF_ROOM_SENSORS,
    CONF_SPREAD_SENSORS,
    CONF_THERMOSTAT,
    DOMAIN,
    SAVE_DELAY,
    STORE_VERSION,
    TICK,
    WIDEN_PAUSE,
)
from .lib import (
    HEAT_COOL,
    Decision,
    Readings,
    Thermostat,
    ZoneEngine,
    ZoneSettings,
    ZoneState,
)

_LOGGER = logging.getLogger(__name__)


def zone_config(entry: ConfigEntry) -> dict[str, Any]:
    """The entry's entities; the options flow overrides the original choice."""
    return {**entry.data, **entry.options}


class ZoneCoordinator(DataUpdateCoordinator[Decision]):
    """Ticks once a minute, and soon after the thermostat changes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=TICK,
        )
        config = zone_config(entry)
        self.thermostat_id: str = config[CONF_THERMOSTAT]
        self.room_sensors: list[str] = list(config.get(CONF_ROOM_SENSORS, []))
        self.spread_sensors: list[str] = list(config.get(CONF_SPREAD_SENSORS, []))
        self.humidity_sensor: str | None = config.get(CONF_HUMIDITY)
        self.outdoor_sensor: str | None = config.get(CONF_OUTDOOR_MEAN)
        self.engine = ZoneEngine(ZoneSettings())
        self.writing = False
        self.fan_enabled = False
        self.readings = Readings()
        self.thermostat = Thermostat(available=False)
        self.last_error: str | None = None
        # A thermostat change caused by our own write must not be read before
        # the write is recorded, or it looks like a change made at the wall.
        self._lock = asyncio.Lock()
        self._store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )

    # ── Persistence ────────────────────────────────────────────────────────

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.engine = ZoneEngine(
            ZoneSettings.from_dict(data.get("settings")),
            ZoneState.from_dict(data.get("state")),
        )
        self.writing = bool(data.get("writing", False))
        self.fan_enabled = bool(data.get("fan_enabled", False))

    def _stored(self) -> dict[str, Any]:
        return {
            "settings": self.engine.settings.as_dict(),
            "state": self.engine.state.as_dict(),
            "writing": self.writing,
            "fan_enabled": self.fan_enabled,
        }

    async def async_save(self) -> None:
        await self._store.async_save(self._stored())

    # ── Wiring ─────────────────────────────────────────────────────────────

    @callback
    def async_start(self) -> None:
        """Re-run soon after the thermostat changes, to catch wall changes."""

        @callback
        def _changed(event: Event[EventStateChangedData]) -> None:
            self.hass.async_create_task(self.async_request_refresh())

        assert self.config_entry is not None
        self.config_entry.async_on_unload(
            async_track_state_change_event(self.hass, [self.thermostat_id], _changed)
        )

    # ── Commands from the entities ─────────────────────────────────────────

    async def async_command(
        self, action: Callable[[ZoneEngine, datetime], None]
    ) -> None:
        async with self._lock:
            action(self.engine, dt_util.now())
        await self.async_refresh()

    async def async_set_setting(self, key: str, value: Any) -> None:
        self.engine.settings = self.engine.settings.with_value(key, value)
        await self.async_refresh()

    async def async_set_writing(self, on: bool) -> None:
        self.writing = on
        if on:
            # Take over from whatever is on the thermostat now.
            self.engine.state.written = None
            self.engine.state.override = None
        await self.async_refresh()

    async def async_set_fan_enabled(self, on: bool) -> None:
        self.fan_enabled = on
        await self.async_refresh()

    # ── The tick ───────────────────────────────────────────────────────────

    async def _async_update_data(self) -> Decision:
        async with self._lock:
            return await self._async_tick()

    async def _async_tick(self) -> Decision:
        now = dt_util.now()
        self.readings = self._read_sensors()
        self.thermostat = self._read_thermostat()
        decision = self.engine.update(
            now,
            self.readings,
            self.thermostat,
            writing=self.writing,
            fan_enabled=self.fan_enabled,
        )
        if self.writing:
            await self._apply(now, decision)
        self._store.async_delay_save(self._stored, SAVE_DELAY)
        return decision

    async def _apply(self, now: datetime, decision: Decision) -> None:
        self.last_error = None
        if decision.write_band:
            try:
                wide = self._widened(decision.low, decision.high)
                if wide is not None:
                    await self._set_band(*wide)
                    await asyncio.sleep(WIDEN_PAUSE)
                await self._set_band(decision.low, decision.high)
            except HomeAssistantError as err:
                self.last_error = f"band write failed: {err}"
                _LOGGER.warning("%s: %s", self.thermostat_id, self.last_error)
            else:
                self.engine.record_write(
                    now, decision.low, decision.high, retry=decision.retry
                )
        if decision.fan_mode is not None:
            try:
                await self.hass.services.async_call(
                    CLIMATE_DOMAIN,
                    SERVICE_SET_FAN_MODE,
                    {
                        ATTR_ENTITY_ID: self.thermostat_id,
                        ATTR_FAN_MODE: decision.fan_mode,
                    },
                    blocking=True,
                )
            except HomeAssistantError as err:
                self.last_error = f"fan write failed: {err}"
                _LOGGER.warning("%s: %s", self.thermostat_id, self.last_error)
            else:
                self.engine.record_fan_write(now, decision.fan_mode)

    def _widened(self, low: int, high: int) -> tuple[int, int] | None:
        """The band covering both the current and the new one, if different.

        A thermostat that keeps a minimum gap between its setpoints may clamp
        the new low against the old high (or the reverse) when both move the
        same way. Widening first means the gap never shrinks on the way.
        """
        current = self.thermostat
        if (
            current.hvac_mode != HEAT_COOL
            or current.target_low is None
            or current.target_high is None
        ):
            return None
        wide = (
            min(round(current.target_low), low),
            max(round(current.target_high), high),
        )
        return wide if wide != (low, high) else None

    async def _set_band(self, low: int, high: int) -> None:
        await self.hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {
                ATTR_ENTITY_ID: self.thermostat_id,
                ATTR_HVAC_MODE: HEAT_COOL,
                ATTR_TARGET_TEMP_LOW: low,
                ATTR_TARGET_TEMP_HIGH: high,
            },
            blocking=True,
        )

    # ── Reading Home Assistant ─────────────────────────────────────────────

    def _number(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    def _numbers(self, entity_ids: list[str]) -> tuple[float, ...]:
        values = (self._number(entity_id) for entity_id in entity_ids)
        return tuple(value for value in values if value is not None)

    def _read_sensors(self) -> Readings:
        return Readings(
            room_temps=self._numbers(self.room_sensors),
            spread_temps=self._numbers(self.spread_sensors),
            humidity=self._number(self.humidity_sensor),
            outdoor_mean=self._number(self.outdoor_sensor),
        )

    def _read_thermostat(self) -> Thermostat:
        state = self.hass.states.get(self.thermostat_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return Thermostat(available=False)
        attrs = state.attributes
        return Thermostat(
            available=True,
            hvac_mode=state.state,
            hvac_action=attrs.get(ATTR_HVAC_ACTION),
            current_temperature=_float(attrs.get(ATTR_CURRENT_TEMPERATURE)),
            target_low=_float(attrs.get(ATTR_TARGET_TEMP_LOW)),
            target_high=_float(attrs.get(ATTR_TARGET_TEMP_HIGH)),
            target_temperature=_float(attrs.get(ATTR_TEMPERATURE)),
            fan_mode=attrs.get(ATTR_FAN_MODE),
        )


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except TypeError, ValueError:
        return None
