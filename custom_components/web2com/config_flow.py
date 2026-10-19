"""Config flow: manual LAN gateway configuration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers import selector
import ochsner_web2com.web2com as web2com

from .const import DOMAIN

CONF_HOST = "host"
CONF_AUTHENTICATION = "authentication"
CONF_SCAN_INTERVAL = "scan_interval"


def _schema(defaults=None):
    defaults = defaults or {}
    return vol.Schema({
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
        vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
        vol.Required(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
        vol.Required(CONF_AUTHENTICATION, default=defaults.get(CONF_AUTHENTICATION, "Digest")): vol.In(["Digest", "Basic"]),
    })


def _test_connection(data):
    auth = web2com.AUTH.BASIC if data[CONF_AUTHENTICATION] == "Basic" else web2com.AUTH.DIGEST
    client = web2com.Service(data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD], auth=auth)
    result = client.get_value("/1/2/2/126/1")
    if result is None or len(result) < 2:
        raise ValueError("Unexpected SOAP response")


class Web2ComConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            data = dict(user_input)
            data[CONF_HOST] = data[CONF_HOST].strip()
            if not data[CONF_HOST]:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(data[CONF_HOST])
                self._abort_if_unique_id_configured()
                try:
                    await self.hass.async_add_executor_job(_test_connection, data)
                except Exception:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(title=f"Ochsner Web2Com ({data[CONF_HOST]})", data=data)
        return self.async_show_form(step_id="user", data_schema=_schema(user_input), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return Web2ComOptionsFlow()


class Web2ComOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            data = dict(user_input)
            data[CONF_HOST] = data[CONF_HOST].strip()
            try:
                await self.hass.async_add_executor_job(_test_connection, data)
            except Exception:
                return self.async_show_form(step_id="init", data_schema=_schema(data), errors={"base": "cannot_connect"})
            return self.async_create_entry(title="", data=data)
        defaults = dict(self.config_entry.data)
        defaults.update(self.config_entry.options)
        return self.async_show_form(step_id="init", data_schema=_schema(defaults))
