"""Platform for Kostal Plenticore sensors."""
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ICON,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_HOST,
    CONF_NAME,
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_POWER,
    ENERGY_KILO_WATT_HOUR,
    PERCENTAGE,
    POWER_WATT,
    STATE_UNAVAILABLE,
)
from homeassistant.helpers import config_validation as cv, entity_platform, service
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SCOPE_PROCESS_DATA,
    SCOPE_SETTING,
    SENSOR_PROCESS_DATA,
    SERVICE_SET_VALUE,
    SENSOR_SETTINGS_DATA,
)


_LOGGER = logging.getLogger(__name__)


def format_round(state):
    try:
        return round(float(state))
    except (TypeError, ValueError):
        return state


def format_energy(state):
    try:
        return round(float(state) / 1000, 1)
    except (TypeError, ValueError):
        return state


def format_inverter_state(state):
    try:
        value = int(state)
    except (TypeError, ValueError):
        return state

    if value == 0:
        return "Off"
    if value == 1:
        return "Init"
    if value == 2:
        return "IsoMEas"
    if value == 3:
        return "GridCheck"
    if value == 4:
        return "StartUp"
    if value == 6:
        return "FeedIn"
    if value == 7:
        return "Throttled"
    if value == 8:
        return "ExtSwitchOff"
    if value == 9:
        return "Update"
    if value == 10:
        return "Standby"
    if value == 11:
        return "GridSync"
    if value == 12:
        return "GridPreCheck"
    if value == 13:
        return "GridSwitchOff"
    if value == 14:
        return "Overheating"
    if value == 15:
        return "Shutdown"
    if value == 16:
        return "ImproperDcVoltage"
    if value == 17:
        return "ESB"
    return "Unknown"


def format_em_manager_state(state):
    try:
        value = int(state)
    except (TypeError, ValueError):
        return state

    if value == 0:
        return "Idle"
    if value == 1:
        return "n/a"
    if value == 2:
        return "Emergency Battery Charge"
    if value == 4:
        return "n/a"
    if value == 8:
        return "Winter Mode Step 1"
    if value == 16:
        return "Winter Mode Step 2"

    return "Unknown"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    process_data_entities = []
    for mid, did, sn, sd, fm in SENSOR_PROCESS_DATA:
        # get function for string
        fm = globals()[str(fm)]

        process_data_entities.append(
            PlenticoreProcessDataSensor(
                coordinator, entry.entry_id, entry.title, mid, did, sn, sd, fm
            )
        )

    async_add_entities(process_data_entities)

    setting_entities = []
    for mid, did, sn, sd, fm in SENSOR_SETTINGS_DATA:
        # get function for string
        fm = globals()[str(fm)]

        setting_entities.append(
            PlenticoreSettingSensor(
                coordinator, entry.entry_id, entry.title, mid, did, sn, sd, fm
            )
        )

    async_add_entities(setting_entities)

    await coordinator.async_refresh()

    platform = entity_platform.current_platform.get()

    platform.async_register_entity_service(
        SERVICE_SET_VALUE,
        {vol.Required("value"): str},
        "set_new_value",
    )

    return True


class PlenticoreProcessDataSensor(CoordinatorEntity):
    """Representation of a Plenticore process data Sensor."""

    def __init__(
        self,
        coordinator,
        entry_id,
        platform_name: str,
        module_id: str,
        data_id: str,
        sensor_name: str,
        sensor_data: dict,
        formatter: callable,
    ):
        super().__init__(coordinator)
        self.entry_id = entry_id
        self.platform_name = platform_name
        self.module_id = module_id
        self.data_id = data_id

        self._sensor_name = sensor_name
        self._sensor_data = sensor_data
        self._formatter = formatter

        self.coordinator.register_entity(self)

    @property
    def scope(self):
        return SCOPE_PROCESS_DATA

    @property
    def unique_id(self):
        return f"{self.entry_id}_{self._sensor_name}"

    @property
    def name(self):
        return f"{self.platform_name} {self._sensor_name}"

    @property
    def unit_of_measurement(self):
        return self._sensor_data.get(ATTR_UNIT_OF_MEASUREMENT, None)

    @property
    def icon(self):
        return self._sensor_data.get(ATTR_ICON, None)

    @property
    def device_class(self):
        return self._sensor_data.get(ATTR_DEVICE_CLASS, None)

    @property
    def state(self):
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return STATE_UNAVAILABLE

        try:
            raw_value = self.coordinator.data[self.scope][self.module_id][self.data_id]
        except KeyError:
            return STATE_UNAVAILABLE

        return self._formatter(raw_value) if self._formatter else raw_value

    @property
    def device_info(self):
        """Device info."""
        return self.coordinator.device_info


class PlenticoreSettingSensor(PlenticoreProcessDataSensor):
    """Representation of a Plenticore setting value Sensor."""

    def __init__(
        self,
        coordinator,
        entry_id,
        platform_name: str,
        module_id: str,
        data_id: str,
        sensor_name: str,
        sensor_data: dict,
        formatter: callable,
    ):
        super().__init__(
            coordinator,
            entry_id,
            platform_name,
            module_id,
            data_id,
            sensor_name,
            sensor_data,
            formatter,
        )

    @property
    def scope(self):
        return SCOPE_SETTING

    async def set_new_value(self, value):
        await self.coordinator.write_setting(self.module_id, self.data_id, value)
