"""Platform for Kostal Plenticore sensors."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    STATE_UNAVAILABLE,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
    PERCENTAGE,
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_POWER,
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    ATTR_ICON,
)
from homeassistant.helpers import config_validation as cv, entity_platform, service
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SCOPE_PROCESS_DATA, SCOPE_SETTING


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


# module-id, process-data-id, name, sensor-properties
BASIC_DATA = [
    (
        "devices:local",
        "Inverter:State",
        "Inverter State",
        {},
        format_inverter_state,
    ),
    (
        "devices:local",
        "Grid_P",
        "Grid Power",
        {ATTR_UNIT_OF_MEASUREMENT: POWER_WATT, ATTR_DEVICE_CLASS: DEVICE_CLASS_POWER},
        format_round,
    ),
    (
        "devices:local",
        "HomeBat_P",
        "Home Power from Battery",
        {ATTR_UNIT_OF_MEASUREMENT: POWER_WATT, ATTR_DEVICE_CLASS: DEVICE_CLASS_POWER},
        format_round,
    ),
    (
        "devices:local",
        "HomeGrid_P",
        "Home Power from Grid",
        {ATTR_UNIT_OF_MEASUREMENT: POWER_WATT, ATTR_DEVICE_CLASS: DEVICE_CLASS_POWER},
        format_round,
    ),
    (
        "devices:local",
        "HomeOwn_P",
        "Home Power",
        {ATTR_UNIT_OF_MEASUREMENT: POWER_WATT, ATTR_DEVICE_CLASS: DEVICE_CLASS_POWER},
        format_round,
    ),
    (
        "devices:local",
        "HomePv_P",
        "Home Power from PV",
        {ATTR_UNIT_OF_MEASUREMENT: POWER_WATT, ATTR_DEVICE_CLASS: DEVICE_CLASS_POWER},
        format_round,
    ),
    (
        "devices:local:ac",
        "P",
        "AC Power",
        {ATTR_UNIT_OF_MEASUREMENT: POWER_WATT, ATTR_DEVICE_CLASS: DEVICE_CLASS_POWER},
        format_round,
    ),
    (
        "devices:local:pv1",
        "P",
        "DC1 Power",
        {ATTR_UNIT_OF_MEASUREMENT: POWER_WATT, ATTR_DEVICE_CLASS: DEVICE_CLASS_POWER},
        format_round,
    ),
    (
        "devices:local:pv2",
        "P",
        "DC2 Power",
        {ATTR_UNIT_OF_MEASUREMENT: POWER_WATT, ATTR_DEVICE_CLASS: DEVICE_CLASS_POWER},
        format_round,
    ),
]

BATTERY_DATA = [
    (
        "devices:local",
        "PV2Bat_P",
        "PV to Battery Power",
        {ATTR_UNIT_OF_MEASUREMENT: POWER_WATT, ATTR_DEVICE_CLASS: DEVICE_CLASS_POWER},
        format_round,
    ),
    (
        "devices:local",
        "EM_State",
        "Energy Manager State",
        {},
        format_em_manager_state,
    ),
    ("devices:local:battery", "Cycles", "Battery Cycles", {}, format_round),
    (
        "devices:local:battery",
        "P",
        "Battery Power",
        {ATTR_UNIT_OF_MEASUREMENT: POWER_WATT, ATTR_DEVICE_CLASS: DEVICE_CLASS_POWER},
        format_round,
    ),
    (
        "devices:local:battery",
        "SoC",
        "Battery SoC",
        {ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE, ATTR_DEVICE_CLASS: DEVICE_CLASS_BATTERY},
        format_round,
    ),
]

STATISTIC_DATA = [
    (
        "scb:statistic:EnergyFlow",
        "Statistic:Autarky:Day",
        "Autarky Day",
        {ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE},
        format_round,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:Autarky:Month",
        "Autarky Month",
        {ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE},
        format_round,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:Autarky:Total",
        "Autarky Total",
        {ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE},
        format_round,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:Autarky:Year",
        "Autarky Year",
        {ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE},
        format_round,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:OwnConsumptionRate:Day",
        "Own Consumption Rate Day",
        {ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE},
        format_round,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:OwnConsumptionRate:Month",
        "Own Consumption Rate Month",
        {ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE},
        format_round,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:OwnConsumptionRate:Total",
        "Own Consumption Rate Total",
        {ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE},
        format_round,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:OwnConsumptionRate:Year",
        "Own Consumption Rate Year",
        {ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE},
        format_round,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHome:Day",
        "Home Consumption Day",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHome:Month",
        "Home Consumption Month",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHome:Year",
        "Home Consumption Year",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHome:Total",
        "Home Consumption Total",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHomeBat:Day",
        "Home Consumption from Battery Day",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHomeBat:Month",
        "Home Consumption from Battery Month",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHomeBat:Year",
        "Home Consumption from Battery Year",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHomeBat:Total",
        "Home Consumption from Battery Total",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHomeGrid:Day",
        "Home Consumption from Grid Day",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHomeGrid:Month",
        "Home Consumption from Grid Month",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHomeGrid:Year",
        "Home Consumption from Grid Year",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHomeGrid:Total",
        "Home Consumption from Grid Total",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHomePv:Day",
        "Home Consumption from PV Day",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHomePv:Month",
        "Home Consumption from PV Month",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHomePv:Year",
        "Home Consumption from PV Year",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyHomePv:Total",
        "Home Consumption from PV Total",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyPv1:Day",
        "Energy PV1 Day",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyPv1:Month",
        "Energy PV1 Month",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyPv1:Year",
        "Energy PV1 Year",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyPv1:Total",
        "Energy PV1 Total",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyPv2:Day",
        "Energy PV2 Day",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyPv2:Month",
        "Energy PV2 Month",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyPv2:Year",
        "Energy PV2 Year",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:EnergyPv2:Total",
        "Energy PV2 Total",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:Yield:Day",
        "Energy Yield Day",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:Yield:Month",
        "Energy Yield Month",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:Yield:Year",
        "Energy Yield Year",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
    (
        "scb:statistic:EnergyFlow",
        "Statistic:Yield:Total",
        "Energy Yield Total",
        {
            ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            ATTR_DEVICE_CLASS: DEVICE_CLASS_ENERGY,
        },
        format_energy,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    all_data = []
    all_data.extend(BASIC_DATA)
    all_data.extend(BATTERY_DATA)
    all_data.extend(STATISTIC_DATA)

    async_add_entities(
        [
            PlenticoreProcessDataSensor(
                coordinator, entry.entry_id, entry.title, mid, pid, sn, sd, fm
            )
            for mid, pid, sn, sd, fm in all_data
        ]
    )

    async_add_entities(
        [
            PlenticoreSettingSensor(
                coordinator,
                entry.entry_id,
                entry.title,
                "devices:local",
                "Battery:MinSoc",
                "MinSoc",
                {},
                format_round,
            )
        ]
    )

    await coordinator.async_refresh()

    platform = entity_platform.current_platform.get()
    print(platform)

    @service.verify_domain_control(hass, DOMAIN)
    async def async_service_handle(service_call: ServiceCall):
        print(service_call)
        entities = await platform.async_extract_from_service(service_call)
        print(entities)

    # platform.async_register_entity_service(
    #     "foo",
    #     {},
    #     async_service_handle,
    # )

    hass.services.async_register(
        DOMAIN,
        "bar",
        async_service_handle,
        cv.make_entity_service_schema({}),
    )

    return True


class PlenticoreProcessDataSensor(CoordinatorEntity):
    """Representation of a Plenticore Sensor."""

    def __init__(
        self,
        coordinator,
        entry_id,
        platform_name: str,
        module_id: str,
        process_data_id: str,
        sensor_name: str,
        sensor_data: dict,
        formatter: callable,
    ):
        super().__init__(coordinator)
        self.entry_id = entry_id
        self.platform_name = platform_name
        self.module_id = module_id
        self.process_data_id = process_data_id

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
        module = (
            self.coordinator.data[SCOPE_PROCESS_DATA].get(self.module_id)
            if self.coordinator.data is not None
            else None
        )
        processdata = module.get(self.process_data_id) if module is not None else None
        state = processdata.value if processdata is not None else STATE_UNAVAILABLE

        if state is not None and state is not STATE_UNAVAILABLE and self._formatter:
            state = self._formatter(state)

        return state

    @property
    def device_info(self):
        """Device info."""
        return self.coordinator.device_info


class PlenticoreSettingSensor(PlenticoreProcessDataSensor):
    """Representation of a Plenticore Sensor."""

    def __init__(
        self,
        coordinator,
        entry_id,
        platform_name: str,
        module_id: str,
        process_data_id: str,
        sensor_name: str,
        sensor_data: dict,
        formatter: callable,
    ):
        super().__init__(
            coordinator,
            entry_id,
            platform_name,
            module_id,
            process_data_id,
            sensor_name,
            sensor_data,
            formatter,
        )

    @property
    def scope(self):
        return SCOPE_SETTING

    @property
    def state(self):
        """Return the state of the sensor."""
        module = (
            self.coordinator.data[SCOPE_SETTING].get(self.module_id)
            if self.coordinator.data is not None
            else None
        )
        processdata = module.get(self.process_data_id) if module is not None else None
        state = processdata if processdata is not None else STATE_UNAVAILABLE

        if state is not None and state is not STATE_UNAVAILABLE and self._formatter:
            state = self._formatter(state)

        return state
