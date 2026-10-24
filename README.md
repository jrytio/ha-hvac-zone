# HVAC Zone

A Home Assistant integration that runs one HVAC zone through a real
thermostat. The thermostat always stays in heat/cool (Auto) with a band
inside failsafe limits, so if Home Assistant stops, the house can neither
freeze nor overheat. It's meant to replace a thermostat-wrapper integration
(such as Versatile Thermostat) and the automations built around it.

What it does, per zone:

- **Two numbers and a gap.** The day cool point follows the outdoor 24 h
  mean (≥ 80°F → 76, 60°F → 74, ≤ 45°F → 72). Sleep is a fixed point. Heat is
  cool minus a gap (5°F by default).
- **Room average, not the thermostat's own sensor.** The band is computed for
  the room average and shifted by the thermostat's measured offset (smoothed,
  capped at ±5°F).
- **People win, for a while.** A change at the wall or in the thermostat's app
  is held for 3 h or until the next day/sleep boundary. Off is never held: the
  thermostat goes straight back to Auto.
- **Cooler / Warmer for a while** buttons, and setting the zone's climate
  entity, shift the band for 3 h.
- **Humidity events** lower the cool point, bounded, to make the AC dry the air.
- **Fan circulation** runs the blower when rooms drift apart, with wet-coil
  guards (no fan while cooling, for an hour after, at high humidity, or when
  humidity rises while it runs).
- **Shadow mode.** Nothing is written until **Write to thermostat** is on.

The design and its reasons are in [docs/DESIGN.md](docs/DESIGN.md).

## Requirements

- Home Assistant 2026.9 or newer, with the unit system in **°F**. All settings
  and sensor values are read as °F.
- A thermostat entity that supports `heat_cool` with a low/high range.
- Room temperature sensors, and optionally a humidity sensor and a sensor with
  the outdoor 24 h mean temperature.

## Install

Add this repository to HACS as a custom integration, install **HVAC Zone**,
restart, then add a zone under Settings → Devices & services.

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

`custom_components/hvac_zone/lib/` holds all the logic and has no Home
Assistant imports; the rest is a thin layer that reads states, calls the
engine once a minute and writes the thermostat.
