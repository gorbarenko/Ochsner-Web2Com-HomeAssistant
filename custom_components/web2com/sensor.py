"""Circuit sensors retain historical unique IDs and last-good values."""
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN
from .entity import Web2ComEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([Web2ComSensor(coordinator, d) for d in coordinator.definitions])


class Web2ComSensor(Web2ComEntity, SensorEntity):
    def __init__(self, coordinator, definition):
        super().__init__(coordinator, definition)
        self._attr_translation_key = definition['key']
        self._attr_entity_registry_enabled_default = definition.get('enabled_by_default', True)
        if not self._attr_entity_registry_enabled_default:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if definition.get('discovered'):
            self._attr_name = definition.get('name', definition.get('code') or self.oid)
        self._attr_native_unit_of_measurement = definition.get('unit_of_measurement') or None
        self._attr_device_class = definition.get('device_class')
        if self._attr_device_class == 'temperature':
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif self._attr_device_class == 'energy':
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._enum_map = definition.get('enum_map') or {}
        if self._enum_map:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(dict.fromkeys(self._enum_map.values()))
        if definition['key'] == 'heater_mode_raw':
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = ['automatic', 'manual', 'off']

    @property
    def native_value(self):
        value = self.raw_value
        if value is None:
            return None
        if self.definition['key'] == 'heater_mode_raw':
            return {0: 'off', 1: 'automatic', 4: 'manual'}.get(value)
        if self._enum_map:
            return self._enum_map.get(str(int(value))) if value.is_integer() else None
        return value
