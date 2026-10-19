"""Web2Com SOAP sensors with individual polling intervals."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity, UpdateFailed
import ochsner_web2com.web2com as web2com

from .const import DOMAIN, DEFAULT_SENSORS

_LOGGER = logging.getLogger(__name__)


def _read(config: dict, oid: str):
    auth = web2com.AUTH.BASIC if config.get("authentication") == "Basic" else web2com.AUTH.DIGEST
    client = web2com.Service(config["host"], config["username"], config["password"], auth=auth)
    response = client.get_value(oid)
    if not response or len(response) < 2:
        raise ValueError(f"Bad SOAP response for {oid}")
    return response[1]


class Web2ComCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, config, definition):
        self.config, self.definition = config, definition
        super().__init__(hass, _LOGGER, name=f"Web2Com {definition['unique_id']}",
                         update_interval=timedelta(seconds=definition['scan_interval']))

    async def _async_update_data(self):
        try:
            return await self.hass.async_add_executor_job(_read, self.config, self.definition['id'])
        except Exception as err:
            raise UpdateFailed(f"Cannot read {self.definition['id']}: {err}") from err


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    config = {**entry.data, **entry.options}
    entities = []
    for definition in DEFAULT_SENSORS:
        coordinator = Web2ComCoordinator(hass, config, definition)
        await coordinator.async_refresh()
        entities.append(Web2ComSensor(coordinator, config, definition))
    async_add_entities(entities)


class Web2ComSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, config, definition):
        super().__init__(coordinator)
        self._definition = definition
        self._attr_has_entity_name = True
        self._attr_name = None
        self._attr_unique_id = f"web2com_{config['host']}_{definition['key']}"
        self._attr_translation_key = definition['key']
        self._attr_native_unit_of_measurement = definition.get('unit_of_measurement') or None
        cls = definition.get('device_class')
        self._attr_device_class = SensorDeviceClass.TEMPERATURE if cls == 'temperature' else (SensorDeviceClass.ENERGY if cls == 'energy' else None)
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING if cls == 'energy' else (SensorStateClass.MEASUREMENT if cls == 'temperature' else None)
        self._attr_device_info = {
            'identifiers': {(DOMAIN, f"gateway_{config['host']}")},
            'name': 'Ochsner Web2Com', 'manufacturer': 'Ochsner',
            'model': 'Web2Com Gateway', 'configuration_url': f"http://{config['host']}/"
        }

    @property
    def native_value(self):
        value = self.coordinator.data
        if value in ('', None):
            return None
        if self._attr_device_class is not None:
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        return value
