"""Common identity and freshness attributes."""
from datetime import datetime, timezone
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .catalog import device_info


class Web2ComEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, definition, key=None):
        super().__init__(coordinator)
        self.definition = definition
        self.oid = definition['id']
        self._attr_unique_id = f"web2com_{coordinator.identity}_{key or definition['key']}"
        self._attr_device_info = device_info(coordinator.identity, definition['device'])

    async def async_added_to_hass(self):
        self.coordinator.register(self.oid)
        await super().async_added_to_hass()
        self.async_on_remove(lambda: self.coordinator.unregister(self.oid))

    @property
    def available(self):
        return self.oid in (self.coordinator.data or {})

    @property
    def raw_value(self):
        return (self.coordinator.data or {}).get(self.oid, {}).get('value')

    @property
    def extra_state_attributes(self):
        item = (self.coordinator.data or {}).get(self.oid, {})
        stamp = item.get('updated')
        return {'oid': self.oid, 'internal_code': self.definition.get('code'),
                'german_name': self.definition.get('german_name'),
                'last_success': datetime.fromtimestamp(stamp, timezone.utc).isoformat() if stamp else None,
                'stale': self.coordinator.engine.stale(self.oid, self.definition.get('scan_interval', 60)),
                'last_error': self.coordinator.engine.errors.get(self.oid)}
