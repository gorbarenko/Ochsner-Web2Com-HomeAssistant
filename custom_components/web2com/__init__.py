"""Ochsner Web2Com v1.9.1."""
from homeassistant.const import Platform
from homeassistant.helpers.storage import Store
from homeassistant.helpers import device_registry as dr, entity_registry as er
from .catalog import DEVICE_NAMES, deduplicate, device_info, load_catalog
from .const import DOMAIN
from .coordinator import Web2ComCoordinator
from .discovery import discover
from .soap_client import Web2ComSOAPClient, OID_RE, CODE_RE

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT, Platform.NUMBER]


async def async_setup(hass, config):
    return True


async def async_migrate_entry(hass, entry):
    if entry.version > 2:
        return False
    if entry.version == 1:
        # The former options flow could change the effective host, and therefore IDs.
        identity = entry.options.get('host', entry.data['host'])
        hass.config_entries.async_update_entry(entry,
            data={**entry.data, 'identity_host': identity}, version=2)
    return True


async def async_setup_entry(hass, entry):
    config = {**entry.data, **entry.options}
    identity = entry.data.get('identity_host', entry.data['host'])
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    prefix = f'web2com_{identity}_'
    sensor_entries = [e for e in entries if e.domain == 'sensor' and e.unique_id.startswith(prefix)]
    sensor_entries.sort(key=lambda e: e.disabled_by is not None)
    preferred = [e.unique_id[len(prefix):] for e in sensor_entries]
    definitions = await hass.async_add_executor_job(load_catalog)
    catalog_store = Store(hass, 1, f'{DOMAIN}.{entry.entry_id}.discovered')
    cached = await catalog_store.async_load() or []
    cached = [d for d in cached if isinstance(d, dict) and d.get('discovered')
              and OID_RE.fullmatch(d.get('id', '')) and CODE_RE.fullmatch(d.get('code', ''))]
    definitions.extend(cached)
    if config.get('auto_discover', False):
        extra = await hass.async_add_executor_job(discover, Web2ComSOAPClient(config), definitions)
        definitions.extend(extra)
        await catalog_store.async_save([*cached, *extra])
    definitions = deduplicate(definitions, preferred)
    # Reuse registered duplicate aliases as the survivor. Never delete registry/history rows.
    devices = dr.async_get(hass)
    device_ids = {}
    for group in ('terminal', 'hc1', 'hc2', 'heaters'):
        device_ids[group] = devices.async_get_or_create(config_entry_id=entry.entry_id,
            **device_info(identity, group)).id
    for definition in definitions:
        for key, _ in definition['aliases']:
            entity_id = registry.async_get_entity_id('sensor', DOMAIN, prefix + key)
            if not entity_id:
                continue
            registered = registry.async_get(entity_id)
            changes = {'device_id': device_ids[definition['device']]}
            if key != definition['key'] and registered.disabled_by is None:
                changes['disabled_by'] = er.RegistryEntryDisabler.INTEGRATION
            registry.async_update_entity(entity_id, **changes)
    coordinator = Web2ComCoordinator(hass, entry, definitions)
    await coordinator.restore()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_update_listener))
    await coordinator.async_refresh()
    return True


async def _update_listener(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.store.async_save(coordinator.engine.snapshot())
        return True
    return False
