"""Manual TEN heater mode switch: OID 4=manual, 1=automatic."""
from __future__ import annotations

from datetime import timedelta
import logging
import requests
from requests.auth import HTTPDigestAuth, HTTPBasicAuth

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity, UpdateFailed

from .const import DOMAIN
from .sensor import _read

_LOGGER = logging.getLogger(__name__)
MODE_OID = '/1/2/2/108/0'
SOAP_ACTION = 'http://ws01.lom.ch/soap/writeDP'


def _write_mode(config, mode):
    """Uses the exact writeDpRequest shape supplied by the owner."""
    assert mode in (1, 4)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" '
           'xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/" '
           'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
           'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
           'xmlns:ns="http://ws01.lom.ch/soap/">'
           '<SOAP-ENV:Body><ns:writeDpRequest><ref><oid>/1/2/2/108/0</oid><prop/></ref>'
           '<dp><index>0</index><name/><prop/><desc/>'
           f'<value>{mode}</value><unit/><timestamp>0</timestamp></dp>'
           '</ns:writeDpRequest></SOAP-ENV:Body></SOAP-ENV:Envelope>')
    auth_class = HTTPBasicAuth if config.get('authentication') == 'Basic' else HTTPDigestAuth
    response = requests.post(f"http://{config['host']}/ws", data=xml.encode('utf-8'),
                             auth=auth_class(config['username'], config['password']),
                             headers={'Content-Type': 'text/xml; charset=utf-8', 'SOAPAction': SOAP_ACTION}, timeout=15)
    response.raise_for_status()
    if b'Fault' in response.content or b'fault' in response.content:
        raise ValueError('SOAP returned a fault')


class ModeCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, config):
        self.config = config
        self._attr_unique_id = f"web2com_{config['host']}_manual_heater_mode"
        super().__init__(hass, _LOGGER, name='Web2Com TEN mode', update_interval=timedelta(seconds=15))

    async def _async_update_data(self):
        try:
            return str(await self.hass.async_add_executor_job(_read, self.config, MODE_OID))
        except Exception as err:
            raise UpdateFailed(f'TEN mode unavailable: {err}') from err


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    config = {**entry.data, **entry.options}
    coordinator = ModeCoordinator(hass, config)
    await coordinator.async_refresh()
    async_add_entities([TenModeSwitch(coordinator, config)])


class TenModeSwitch(CoordinatorEntity, SwitchEntity):
    _attr_name = 'Manual heater mode'
    _attr_translation_key = 'manual_heater_mode'
    _attr_icon = 'mdi:radiator'


    def __init__(self, coordinator, config):
        super().__init__(coordinator)
        self.config = config
        self._attr_unique_id = f"web2com_{config['host']}_manual_heater_mode"
        self._attr_device_info = {'identifiers': {(DOMAIN, f"gateway_{config['host']}")},
                                  'name': 'Ochsner Web2Com', 'manufacturer': 'Ochsner',
                                  'model': 'Web2Com Gateway'}

    @property
    def is_on(self):
        return self.coordinator.data == '4'

    async def async_turn_on(self, **kwargs):
        await self.hass.async_add_executor_job(_write_mode, self.config, 4)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_executor_job(_write_mode, self.config, 1)
        await self.coordinator.async_request_refresh()
