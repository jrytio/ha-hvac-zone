# HVAC Zone: design

One config entry per thermostat zone. A zone is one real thermostat and the
rooms it serves. The integration replaces a thermostat-wrapper integration
(such as Versatile Thermostat) plus the schedule and humidity automations
usually built around it.

## Rules the design follows

1. **The thermostat is never off because of us.** It stays in `heat_cool`
   (Auto). The integration only ever writes a low/high pair. If Home
   Assistant dies, the last pair stays on the thermostat, and that pair is
   always inside the failsafe limits (default heat ≥ 60°F, cool ≤ 80°F).
   The house can neither freeze nor overheat.
2. **Two numbers with a dead band.** The cool point comes from the weather.
   The heat point is the cool point minus a gap (default 5°F). Between the
   two, nothing runs.
3. **People win, for a while.** A change made at the wall or in the thermostat's
   own app counts as a manual override: a setpoint, a heat or cool mode, or a
   native comfort-setting resume. It's honoured until the hold expires
   (default 3 h) or the next schedule boundary, whichever comes first. Then
   the zone goes back to Auto and the band. **Off is the exception:** it is
   never honoured, and the next update puts the thermostat back in Auto. To
   really stop the zone, turn off "Write to thermostat" first.
4. **The room average is the truth.** The band is computed in
   room-average space, then shifted by the thermostat's sensor offset
   (thermostat reading minus room average, smoothed) before it's written.
   It's capped at ±5°F. Thermostats with a sensor several degrees off
   need more room than a ±2°F regulation cap gives, or the rooms drift far
   from the target overnight.
5. **Shadow mode first.** "Write to thermostat" starts off. The zone
   computes and shows everything but writes nothing until it's switched on.

## Band computation (pure, `lib/band.py` and `lib/engine.py`)

| Step | Rule |
| --- | --- |
| Period | Day from *day start* (06:00) to *sleep start* (20:30), else sleep |
| Cool point, day | Piecewise-linear curve on the outdoor 24 h mean: ≥ 80°F → 76, 60°F → 74, ≤ 45°F → 72 (all six numbers are settings) |
| Cool point, sleep | Sleep cool setting (69) |
| Bump | "Cooler/Warmer for a while", or setting the zone's climate entity, shifts the points for *bump hours*. It ends at the next period boundary |
| Humidity event | Starts when RH rises above 58% and ends when it falls below 52%. While it's on, the cool point is lowered to max(66, engage avg − 3, ⌊avg⌋ − 1), re-stepped every 15 min. This makes the AC run to remove moisture, bounded to 3°F per event |
| Heat point | Cool point − gap |
| Offset | EMA (≈30 min) of thermostat temp − room average, clamped to ±5 |
| Written pair | round(point + offset). Hysteresis: a written value moves only when its target is ≥ 0.75°F away |
| Failsafe | low ∈ [floor, ceiling − min gap], high ∈ [floor + min gap, ceiling], high − low ≥ min gap |

## Fan circulation (pure, `lib/fan.py`)

It runs inside a daily window
(09:00–17:00) when its switch is on:

| Spread (warmest − coldest room) | Fan |
| --- | --- |
| ≥ 6°F | on |
| 3–6°F | on for :00–:15 and :30–:45 |
| < 3°F | auto |

Wet-coil guards: no fan while the system is cooling, within 60 min of the end
of a cooling run, or at RH ≥ 50%. If RH rises 2 points or more above its value
when the fan started, the fan goes back to auto and is locked out for 60 min.
A fan change at the wall overrides the fan for the hold time.

## Manual-change detection

After every write, the zone records what it sent and when. A thermostat
state that differs from the last write (mode ≠ heat_cool, or low/high off by
≥ 1°F) is manual, unless it arrives within the 2-minute echo grace after
our own write (bridged thermostats report back late). Restarts are safe: the last write and any
override are persisted.

## Entities (per zone)

- `climate.<zone>`: room average and humidity, the effective heat/cool
  points (room space), hvac_action mirrored from the thermostat. Setting
  low/high starts a bump.
- `switch`: Write to thermostat (shadow mode when off), Fan circulation.
- `button`: Cooler for a while, Warmer for a while, Back to schedule.
- `number`: the curve (6), sleep cool, gap, bump degrees/hours, manual hold
  hours, failsafe floor/ceiling, min gap, fan thresholds.
- `time`: day start, sleep start, fan window start/end.
- `sensor`: thermostat offset, room spread, status (why the band is what it is).
- `binary_sensor`: humidity high, manual override.

Settings and runtime state persist in a `Store` per entry.

## Moving over from an existing setup

1. Take a full Home Assistant backup.
2. Add the zone in shadow mode and compare its band with what the current
   setup does for a day or so.
3. Disable (don't delete) the old automations and the old thermostat
   wrapper, so you can roll back. Then turn on Write to thermostat.
4. As a hardware backstop, set the thermostat's own installer limits for
   the maximum heat and minimum cool setpoints.
