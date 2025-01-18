"""
Adds support for Raspberry Pi GPIO thermostat units.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/climate.generic_thermostat/
"""
import logging

import voluptuous as vol

from homeassistant.components.climate import (
    ClimateDevice, PLATFORM_SCHEMA)
from homeassistant.components.climate.const import (
    FAN_OFF,
    FAN_DIFFUSE,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_HIGH
)
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT)
from homeassistant.helpers.event import track_state_change
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = ['input_number', 'sensor']

DEFAULT_NAME = 'Pi GPio Thermostat'

CONF_NAME = 'name'
CONF_TEMP_CONTROLLER = 'fan'
CONF_SENSOR = 'target_sensor'
CONF_SRV_TEMP_CONTROLLER = 'fan_service_controller'
CONF_FAN_MODE_LIST = 'fan_modes'
default_fan_mode_list = [
                FAN_OFF,
                FAN_DIFFUSE, 
                FAN_LOW, 
                FAN_MEDIUM, 
                FAN_HIGH]


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_TEMP_CONTROLLER): cv.entity_id,
    vol.Required(CONF_SENSOR): cv.entity_id,
    vol.Required(CONF_SRV_TEMP_CONTROLLER): cv.service,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(
            CONF_FAN_MODE_LIST,
            default=default_fan_mode_list,
        ): cv.ensure_list,
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the PiGPio thermostat."""
    name = config.get(CONF_NAME)
    temp_controller_entity_id = config.get(CONF_TEMP_CONTROLLER)
    sensor_entity_id = config.get(CONF_SENSOR)
    service_temp_controller = config.get(CONF_SRV_TEMP_CONTROLLER)

    add_devices([PiGPioThermostat(
        hass, name, temp_controller_entity_id, sensor_entity_id, service_temp_controller)])


class PiGPioThermostat(ClimateDevice):
    """Representation of a Raspberry Pi GPio device."""

    def __init__(self, hass, name, temp_controller_entity_id, sensor_entity_id,
        service_temp_controller):
        """Initialize the thermostat."""
        self.hass = hass
        self._name = name
        self.temp_controller_entity_id = temp_controller_entity_id
        self.service_temp_controller = service_temp_controller
        self._active = False
        self._cur_temp = None
        self._cur_operation = None
        self._attr_fan_mode = None
        self._fan_mode_id = 0
        
        self._unit = hass.config.units.temperature_unit

        track_state_change(hass, sensor_entity_id, self._sensor_changed)

        sensor_state = hass.states.get(sensor_entity_id)
        if sensor_state:
            self._update_temp(sensor_state)

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def name(self):
        """Return the name of the thermostat."""
        return self._name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def current_temperature(self):
        """Return the sensor temperature."""
        return self._cur_temp
    
    @property
    def current_fan_mode(self):
        """Return the fan mode."""
        return self._attr_fan_mode

    @property
    def current_operation(self):
        """Return current operation ie. heat, cool, idle."""
        return self._cur_operation
        # if self.ac_mode:
        #     cooling = self._active and self._is_device_active
        #     return STATE_COOL if cooling else STATE_IDLE
        # else:
        #     heating = self._active and self._is_device_active
        #     return STATE_HEAT if heating else STATE_IDLE

    def _sensor_changed(self, entity_id, old_state, new_state):
        """Called when temperature changes."""
        if new_state is None:
            return

        self._update_temp(new_state)
        self._control_heating()
        self.schedule_update_ha_state()

    def _update_temp(self, state):
        """Update thermostat with latest state from sensor."""
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)

        try:
            self._cur_temp = self.hass.config.units.temperature(
                float(state.state), unit)
        except ValueError as ex:
            _LOGGER.error('Unable to update from sensor: %s', ex)

    def _control_heating(self):
        fan_mode = 0 #shutdown
        if 50 <= self._cur_temp < 60:
            fan_mode = 1 # very low
        elif 60 <= self._cur_temp < 65:
            fan_mode = 2 # low
        elif 65 <= self._cur_temp < 70:
            fan_mode = 3 #medium
        elif 70 <= self._cur_temp:
            fan_mode = 4 #high
        
        self.hass.services.call(
            "pyscript",
            "change_GPio_fan_mode",
            {"mode": fan_mode},
            blocking=True
        )

        self._attr_fan_mode = default_fan_mode_list[fan_mode]
        self._fan_mode_id = fan_mode

    @property
    def _is_device_active(self):
        """If the toggleable device is currently active."""
        return self._fan_mode_id != 0