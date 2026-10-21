"""Per-device stale indicators; retained values never imply a healthy connection."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .catalog import DEVICE_NAMES, device_info
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([StaleSensor(coordinator, group) for group in DEVICE_NAMES])


class StaleSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = 'stale_data'
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, group):
        super().__init__(coordinator)
        self.group = group
        self._attr_unique_id = f'web2com_{coordinator.identity}_{group}_stale'
        self._attr_device_info = device_info(coordinator.identity, group)

    @property
    def available(self):
        return True

    @property
    def is_on(self):
        definitions = [d for d in self.coordinator.definitions if d['id'] in self.coordinator.active
                       and (self.group == 'terminal' or d['device'] == self.group)]
        return not definitions or any(self.coordinator.engine.stale(d['id'], d.get('scan_interval', 60)) for d in definitions)
