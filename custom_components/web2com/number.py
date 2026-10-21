"""Heating curves: bounded, opt-in controls, disabled until metadata is verified."""
from __future__ import annotations
import logging
import re
import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from xml.sax.saxutils import escape
from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .sensor import _read

_LOGGER = logging.getLogger(__name__)
# OIDs are read-confirmed on this device; their write permissions and bounds
# must be verified from the user's controller metadata before enabling.
CURVES = [
    ('hc1_base', 'Контур 1 — базова температура', '/1/2/4/108/0'),
    ('hc1_design_outdoor', 'Контур 1 — розрахункова зовнішня температура', '/1/2/4/108/1'),
    ('hc1_design_flow', 'Контур 1 — розрахункова подача', '/1/2/4/108/2'),
    ('hc1_heating_limit', 'Контур 1 — температурна межа опалення', '/1/2/4/108/3'),
    ('hc1_day', 'Контур 1 — денна температура', '/1/2/4/108/4'),
    ('hc1_night', 'Контур 1 — нічна температура', '/1/2/4/108/5'),
    ('hc2_base', 'Контур 2 — базова температура', '/1/2/5/108/0'),
    ('hc2_design_outdoor', 'Контур 2 — розрахункова зовнішня температура', '/1/2/5/108/1'),
    ('hc2_design_flow', 'Контур 2 — розрахункова подача', '/1/2/5/108/2'),
    ('hc2_heating_limit', 'Контур 2 — температурна межа опалення', '/1/2/5/108/3'),
    ('hc2_day', 'Контур 2 — денна температура', '/1/2/5/108/4'),
    ('hc2_night', 'Контур 2 — нічна температура', '/1/2/5/108/5'),
]


def _write(config, oid, value):
    # SOAP write layout is carried forward from the working heater select.
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" '
           'xmlns:ns="http://ws01.lom.ch/soap/">'
           f'<SOAP-ENV:Body><ns:writeDpRequest><ref><oid>{escape(oid)}</oid><prop/></ref>'
           '<dp><index>0</index><name/><prop/><desc/>'
           f'<value>{value:g}</value><unit/><timestamp>0</timestamp></dp>'
           '</ns:writeDpRequest></SOAP-ENV:Body></SOAP-ENV:Envelope>')
    auth_class = HTTPBasicAuth if config.get('authentication') == 'Basic' else HTTPDigestAuth
    response = requests.post(f"http://{config['host']}/ws", data=xml.encode(),
        auth=auth_class(config['username'], config['password']),
        headers={'Content-Type':'text/xml; charset=utf-8',
                 'SOAPAction':'http://ws01.lom.ch/soap/writeDP'}, timeout=(5,12))
    response.raise_for_status()
    if not response.content or b'Fault' in response.content or b'fault' in response.content:
        raise HomeAssistantError('Web2Com did not confirm a successful write')


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    config = {**entry.data, **entry.options}
    # No writable Number entities unless the user explicitly supplies verified
    # OID ranges in integration options (future configuration). Avoid arbitrary
    # fallback ranges on a live heating controller.
    bounds = config.get('verified_curve_bounds', {})
    entities = []
    for key, name, oid in CURVES:
        candidate = bounds.get(oid)
        if not isinstance(candidate, dict):
            continue
        try:
            low, high, step = (float(candidate[k]) for k in ('min','max','step'))
            if not (-80 <= low < high <= 120 and 0 < step <= 5):
                continue
        except (ValueError, TypeError, KeyError):
            continue
        entities.append(HeatingCurveNumber(hass, config, key, name, oid, low, high, step))
    async_add_entities(entities)


class HeatingCurveNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = '°C'
    _attr_icon = 'mdi:chart-bell-curve'
    def __init__(self, hass, config, key, name, oid, low, high, step):
        self.hass, self.config, self.oid = hass, config, oid
        self._attr_name = name
        self._attr_unique_id = f"web2com_{config['host']}_{key}_control"
        self._attr_native_min_value = low
        self._attr_native_max_value = high
        self._attr_native_step = step
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_entity_registry_enabled_default = False
        self._attr_device_info = {'identifiers': {(DOMAIN, f"gateway_{config['host']}")},
                                  'name': 'Ochsner Web2Com', 'manufacturer':'Ochsner', 'model':'Room Terminal'}

    async def async_update(self):
        try:
            self._attr_native_value = await self.hass.async_add_executor_job(_read, self.config, self.oid)
        except Exception as err:
            _LOGGER.warning('Unable to read %s: %s', self.oid, err)
            self._attr_available = False
        else:
            self._attr_available = True

    async def async_set_native_value(self, value):
        if not self.native_min_value <= value <= self.native_max_value:
            raise HomeAssistantError('Value outside confirmed controller limits')
        await self.hass.async_add_executor_job(_write, self.config, self.oid, value)
        await self.async_update()
        self.async_write_ha_state()
