"""Shared controls: availability follows live, validated metadata."""
from homeassistant.exceptions import HomeAssistantError
from .entity import Web2ComEntity


class ControlEntity(Web2ComEntity):
    def __init__(self, coordinator, definition):
        super().__init__(coordinator, definition, definition['control_key'])
        self._attr_translation_key = definition['control_key']

    def limits(self):
        return self.coordinator.engine.verify_control(self.definition,
            self.coordinator.engine.metadata.get(self.oid, {}))

    @property
    def available(self):
        if not super().available or self.extra_state_attributes['stale']:
            return False
        try:
            self.limits()
        except (ValueError, KeyError, TypeError):
            return False
        return True

    async def write(self, value):
        try:
            await self.coordinator.write(self.definition, value)
        except Exception as err:
            raise HomeAssistantError(f'Web2Com: {err}') from err
