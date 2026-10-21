"""Operating modes constrained to known meanings and live enum permissions."""
from homeassistant.components.select import SelectEntity
from .const import DOMAIN
from .catalog import controls
from .control import ControlEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OperatingModeSelect(coordinator, d) for d in controls(coordinator.definitions) if d['kind'] == 'select'])


class OperatingModeSelect(ControlEntity, SelectEntity):
    @property
    def options(self):
        try:
            return list(self.limits())
        except (ValueError, KeyError, TypeError):
            return []

    @property
    def current_option(self):
        return next((k for k, v in self.definition['options'].items() if v == self.raw_value and k in self.options), None)

    async def async_select_option(self, option):
        await self.write(option)
