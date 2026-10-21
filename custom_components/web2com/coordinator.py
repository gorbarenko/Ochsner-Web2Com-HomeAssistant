"""One HA coordinator per gateway, with persistent last-good data."""
from __future__ import annotations
from datetime import timedelta
import logging
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .engine import PollEngine
from .soap_client import Web2ComSOAPClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class Web2ComCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, definitions):
        super().__init__(hass, _LOGGER, name='Ochsner Web2Com', update_interval=timedelta(seconds=5))
        self.config = {**entry.data, **entry.options}
        self.identity = entry.data.get('identity_host', entry.data['host'])
        self.definitions = definitions
        self.engine = PollEngine(Web2ComSOAPClient(self.config), definitions)
        self.store = Store(hass, 1, f'{DOMAIN}.{entry.entry_id}.last_good')
        self.active = {}

    def register(self, oid):
        self.active[oid] = self.active.get(oid, 0) + 1

    def unregister(self, oid):
        self.active[oid] -= 1
        if self.active[oid] <= 0:
            del self.active[oid]

    async def restore(self):
        self.engine.restore(await self.store.async_load())
        self.async_set_updated_data(self.engine.snapshot())

    async def _async_update_data(self):
        data = await self.hass.async_add_executor_job(self.engine.poll, set(self.active))
        self.store.async_delay_save(self.engine.snapshot, 30)
        return data

    async def write(self, control, value):
        try:
            data = await self.hass.async_add_executor_job(self.engine.write_control, control, value)
        finally:
            self.async_set_updated_data(self.engine.snapshot())
            self.store.async_delay_save(self.engine.snapshot, 1)
        return data
