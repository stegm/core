"""The Kostal Plenticore Solar Inverter integration."""
import asyncio
from datetime import timedelta
from collections import defaultdict

import logging

import voluptuous as vol

from kostal.plenticore import (
    PlenticoreApiClient,
    PlenticoreApiException,
)

from homeassistant.util.dt import utcnow
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.device_registry import async_get_registry

from .const import DOMAIN, SCOPE_PROCESS_DATA, SCOPE_SETTING

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

PLATFORMS = ["sensor"]


class PlenticoreApi(DataUpdateCoordinator):
    """Data Coordinator for fetching all state of the entities."""

    def __init__(self, hass, config, logger: logging.Logger):
        super().__init__(
            hass=hass,
            logger=logger,
            name="Plenticore",
            update_interval=timedelta(seconds=10),
            update_method=self._fetch_data,
        )
        self.hass = hass
        self._config = config
        self._login = False
        self._registered_entities = []

        self._client = PlenticoreApiClient(
            async_get_clientsession(hass), host=config[CONF_HOST]
        )

        self._device_info = {
            "identifiers": {(DOMAIN, config[CONF_HOST])},
            "name": config[CONF_NAME],
            "manufacturer": "Kostal",
        }

        # cache for the fetched process and settings data
        self._data = {SCOPE_PROCESS_DATA: {}, SCOPE_SETTING: {}}

        # contains all existing module/data ids after login
        self._existing_data_ids = {SCOPE_PROCESS_DATA: {}, SCOPE_SETTING: {}}

        # last update timestamp of setting values
        self._last_setting_update = None

        self._update_request = False
        self._process_request = {}
        self._setting_request = {}

    async def logout(self):
        if self._login:
            self._login = False
            await self._client.logout()
            _LOGGER.info("Logged out from %s.", self._config[CONF_HOST])

    def register_entity(self, entity):
        """Registers a entity on this instance."""
        self._registered_entities.append(entity)
        self._update_request = True

    def unregister_entity(self, entity):
        """Registers a entity on this instance."""
        self._registered_entities = [
            x for x in self._registered_entities if x.unique_id != entity.unique_id
        ]
        self._update_request = True

    @property
    def device_info(self):
        return self._device_info

    async def _update_device_info(self):
        device_settings = await self._client.get_setting_values(
            module_id="devices:local",
            setting_id=[
                "Properties:SerialNo",
                "Branding:ProductName1",
                "Branding:ProductName2",
                "Properties:VersionIOC",
                "Properties:VersionMC",
            ],
        )

        devices_local = device_settings["devices:local"]

        model = (
            devices_local["Branding:ProductName1"]
            + " "
            + devices_local["Branding:ProductName2"]
        )

        sw_version = (
            f'IOC: {devices_local["Properties:VersionIOC"]}'
            + f' MC: {devices_local["Properties:VersionMC"]}'
        )

        dev_registry = await async_get_registry(self.hass)
        device = dev_registry.async_get_device(
            identifiers={(DOMAIN, self._config[CONF_HOST])}, connections=set()
        )
        if device is not None:
            _LOGGER.info(
                "Update device_info model=%s, sw_version=%s.", model, sw_version
            )
            dev_registry.async_update_device(
                device.id, model=model, sw_version=sw_version
            )

    async def _udpate_existing_data(self):
        data = await self._client.get_settings()
        self._existing_data_ids[SCOPE_SETTING] = {
            m: set((y.id for y in x)) for m, x in data.items()
        }

        data = await self._client.get_process_data()
        self._existing_data_ids[SCOPE_PROCESS_DATA] = {
            m: set(v) for m, v in data.items()
        }

        self._update_request = True

    def _build_request(self, scope: str):
        existing = self._existing_data_ids[scope]
        request = defaultdict(list)

        for entity in self._registered_entities:
            if entity.scope == scope and entity.enabled:
                if (
                    entity.module_id in existing
                    and entity.data_id in existing[entity.module_id]
                ):
                    request[entity.module_id].append(entity.data_id)
                    entity.available = True
                else:
                    entity.available = False
                    _LOGGER.info(
                        "Entity '%s' is not available on plenticore.", entity.name
                    )

        return request

    async def _ensure_login(self):
        """Ensures that the default user is logged in."""
        if not self._login:
            await self._client.login(self._config[CONF_PASSWORD])
            await self._udpate_existing_data()
            await self._update_device_info()
            _LOGGER.info("Log-in successfully at %s.", self._config[CONF_HOST])
            self._login = True

    async def _fetch_data(self):
        """Fetch process data and setting values from the inverter."""
        if len(self._registered_entities) == 0:
            return {}

        await self._ensure_login()

        if self._update_request:
            _LOGGER.debug("Building new requests.")
            self._process_request = self._build_request(SCOPE_PROCESS_DATA)
            self._setting_request = self._build_request(SCOPE_SETTING)
            self._update_request = False

        if len(self._process_request) > 0:
            _LOGGER.debug("Fetching process data for: %s", self._process_request)
            data = await self._client.get_process_data_values(self._process_request)
            process_data = {m: {pd.id: pd.value for pd in data[m]} for m in data}
            self._data[SCOPE_PROCESS_DATA].update(process_data)

        # settings does not change that much so we poll this less often
        if self._last_setting_update is None or (
            utcnow() - self._last_setting_update
        ) >= timedelta(seconds=300):
            self._last_setting_update = utcnow()

            if len(self._setting_request) > 0:
                _LOGGER.debug("Fetching setting data for: %s", self._setting_request)
                setting_data = await self._client.get_setting_values(
                    self._setting_request
                )
                self._data[SCOPE_SETTING].update(setting_data)

        return self._data

    async def write_setting(self, module_id: str, setting_id: str, value: str):
        """Writes a new setting value to the inverter."""

        await self._ensure_login()

        _LOGGER.info("Writing '%s' to %s/%s.", value, module_id, setting_id)
        await self._client.set_setting_values(module_id, {setting_id: value})

        self._data[SCOPE_SETTING][module_id][setting_id] = value
        self._last_setting_update = None  # Force update of setting values next time
        self.async_set_updated_data(self._data)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Kostal Plenticore Solar Inverter component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Kostal Plenticore Solar Inverter from a config entry."""
    api = PlenticoreApi(hass, entry.data, _LOGGER)

    hass.data[DOMAIN][entry.entry_id] = api

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if unload_ok:
        # remove API object
        api = hass.data[DOMAIN].pop(entry.entry_id)
        try:
            await api.logout()
        except PlenticoreApiException:
            _LOGGER.exception("Error logging out from inverter.")

    return unload_ok
