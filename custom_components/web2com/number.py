"""Verified temperature controls; no guessed writable ranges."""
from homeassistant.components.number import NumberEntity
from .const import DOMAIN
from .catalog import controls
from .control import ControlEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TemperatureNumber(coordinator, d) for d in controls(coordinator.definitions) if d['kind'] == 'number'])


class TemperatureNumber(ControlEntity, NumberEntity):
    _attr_native_unit_of_measurement = '°C'
    _attr_icon = 'mdi:thermometer'

    @property
    def native_value(self):
        return self.raw_value

    def limit(self, index):
        try:
            return self.limits()[index]
        except (ValueError, KeyError, TypeError):
            # An unavailable control has an inert UI, never usable fallback bounds.
            return (0, 0, 1)[index]

    @property
    def native_min_value(self):
        return self.limit(0)

    @property
    def native_max_value(self):
        return self.limit(1)

    @property
    def native_step(self):
        return self.limit(2)

    async def async_set_native_value(self, value):
        await self.write(value)
