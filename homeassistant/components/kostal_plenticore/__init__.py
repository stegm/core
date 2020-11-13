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

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCOPE_PROCESS_DATA, SCOPE_SETTING

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

PLATFORMS = ["sensor"]


class PlenticoreApi(DataUpdateCoordinator):
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
            "name": config[CONF_NAME],
            "manufacturer": "Kostal",
        }

    async def logout(self):
        if self._login:
            self._login = False
            await self._client.logout()

    def register_entity(self, entity):
        self._registered_entities.append(entity)

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

        self._device_info["model"] = (
            devices_local["Branding:ProductName1"]
            + " "
            + devices_local["Branding:ProductName2"]
        )
        self._device_info["identifiers"] = {
            (DOMAIN, devices_local["Properties:SerialNo"])
        }
        self._device_info["sw_version"] = (
            f'IOC: {devices_local["Properties:VersionIOC"]}',
            f'MC: {devices_local["Properties:VersionMC"]}',
        )

    async def _update_requests(self):
        """Builds sets, which data should be requested."""
        self._process_data_request = defaultdict(list)
        for entity in self._registered_entities:
            if entity.scope == SCOPE_PROCESS_DATA and entity.enabled:
                self._process_data_request[entity.module_id].append(
                    entity.process_data_id
                )

        self._setting_request = defaultdict(list)
        for entity in self._registered_entities:
            if entity.scope == SCOPE_SETTING and entity.enabled:
                self._setting_request[entity.module_id].append(entity.process_data_id)

    async def _fetch_data(self):
        if len(self._registered_entities) == 0:
            return {}

        if not self._login:
            await self._client.login(self._config[CONF_PASSWORD])
            await self._update_device_info()
            await self._update_requests()
            self._login = True

        if len(self._process_data_request) > 0:
            process_data = await self._client.get_process_data_values(
                self._process_data_request
            )
        else:
            process_data = None

        if len(self._setting_request) > 0:
            setting_data = await self._client.get_setting_values(self._setting_request)
        else:
            setting_data = None

        return {SCOPE_PROCESS_DATA: process_data, SCOPE_SETTING: setting_data}


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
