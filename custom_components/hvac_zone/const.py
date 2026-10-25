"""Constants for the HVAC Zone integration."""

from datetime import timedelta

DOMAIN = "hvac_zone"

CONF_THERMOSTAT = "thermostat"
CONF_ROOM_SENSORS = "room_sensors"
CONF_SPREAD_SENSORS = "spread_sensors"
CONF_HUMIDITY = "humidity_sensor"
CONF_OUTDOOR_MEAN = "outdoor_mean_sensor"

TICK = timedelta(minutes=1)
STORE_VERSION = 1
SAVE_DELAY = 30
# Time the thermostat gets to apply a widened band before the final one.
WIDEN_PAUSE = 3
