"""Ochsner Web2Com sensors — shared, bounded polling."""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator, UpdateFailed

import ochsner_web2com.web2com as web2com

from .const import DEFAULT_SENSORS, DOMAIN
from .soap_client import Web2ComSOAPClient, Web2ComSOAPError

_LOGGER = logging.getLogger(__name__)
BATCH_LIMIT = 10
POLL_SECONDS = 60


def _read(config: dict, oid: str) -> float:
    """Read one OID in the executor; reject all non-success statuses."""
    auth = web2com.AUTH.BASIC if config.get("authentication") == "Basic" else web2com.AUTH.DIGEST
    client = web2com.Service(config["host"], config["username"], config["password"], auth=auth)
    result = client.get_value(oid)
    if not isinstance(result, (tuple, list)) or len(result) < 2:
        raise ValueError(f"Malformed result for {oid}: {result!r}")
    status, value = result[:2]
    if status != 200:
        raise ConnectionError(f"Web2Com read {oid} returned status {status}")
    return value


def load_definitions() -> list[dict]:
    """Keep stable keys and entity IDs from 1.8; suppress exact OID duplicates."""
    extras = json.loads(Path(__file__).with_name("extra_sensors.json").read_text(encoding="utf-8"))
    used_keys, used_oids = set(), set()
    definitions = []
    for source in [*DEFAULT_SENSORS, *extras]:
        definition = dict(source)
        oid = definition.get("id")
        key = definition.get("key") or ("oid_" + str(oid).strip("/").replace("/", "_"))
        if not oid or key in used_keys or oid in used_oids:
            continue
        definition["key"] = key
        used_keys.add(key)
        used_oids.add(oid)
        definitions.append(definition)
    return definitions


class Web2ComCoordinator(DataUpdateCoordinator):
    """One coordinator; slow diagnostic OIDs are round-robin polled."""

    def __init__(self, hass: HomeAssistant, config: dict, definitions: list[dict]):
        super().__init__(
            hass, _LOGGER, name="Ochsner Web2Com",
            update_interval=timedelta(seconds=POLL_SECONDS),
            always_update=True,
        )
        self.config = config
        self.primary = [d for d in definitions if d.get("enabled_by_default", True)]
        self.extra = [d for d in definitions if not d.get("enabled_by_default", True)]
        self.cursor = 0
        self.values: dict[str, float] = {}
        self.errors: dict[str, str] = {}

    async def _async_update_data(self) -> dict[str, float]:
        selected = list(self.primary)
        if self.extra:
            for _ in range(min(BATCH_LIMIT, len(self.extra))):
                selected.append(self.extra[self.cursor % len(self.extra)])
                self.cursor += 1
        successes = 0
        # Parent-level SOAP group reads are attempted only in small, verified
        # sibling sets. An incomplete response triggers scalar fallback.
        groups = {}
        for definition in selected:
            parent = definition["id"].rsplit("/", 1)[0]
            groups.setdefault(parent, []).append(definition)
        group_values = {}
        for parent, siblings in groups.items():
            if len(siblings) < 2 or len(siblings) > 8:
                continue
            try:
                mapping = await self.hass.async_add_executor_job(
                    Web2ComSOAPClient(self.config).read_group, parent
                )
                # Never accept guessed indexing or partial group data.
                if all(item["id"] in mapping for item in siblings):
                    group_values.update(mapping)
            except Exception as err:
                _LOGGER.debug("Group read %s unavailable; scalar fallback: %s", parent, err)
        for definition in selected:
            oid = definition["id"]
            try:
                self.values[oid] = (group_values[oid] if oid in group_values else
                    await self.hass.async_add_executor_job(_read, self.config, oid))
                self.errors.pop(oid, None)
                successes += 1
            except Exception as err:
                self.values.pop(oid, None)
                self.errors[oid] = str(err)
                _LOGGER.debug("Failed to read %s: %s", oid, err)
        if not successes and not self.values:
            raise UpdateFailed("Web2Com did not return any valid readings")
        return dict(self.values)


def discover_definitions(config, existing):
    """List only known circuit branches once; do not scan the entire eBUS."""
    client = Web2ComSOAPClient(config)
    used = {d["id"] for d in existing}
    discovered = []
    for root in ("/1/2/2", "/1/2/4", "/1/2/5"):
        try:
            branches = client.list_children(root)[:18]
        except Exception as err:
            _LOGGER.info("Discovery skipped %s: %s", root, err)
            continue
        for branch in branches:
            # Only leafs one level down from known branches: 54 requests max;
            # avoid unknown deep paths and unsafe controller control tests.
            try:
                children = client.list_children(branch["oid"])[:15]
            except Exception:
                continue
            for item in children:
                oid = item["oid"]
                if oid in used or len(discovered) >= 80:
                    continue
                # Read flags are device-specific and are not assumed writable.
                props = item["properties"][:4]
                if 'r' not in props:
                    continue
                used.add(oid)
                discovered.append({"id": oid,
                    "key": "discovered_" + oid.strip('/').replace('/', '_'),
                    "name": item["name"] or oid,
                    "enabled_by_default": False,
                    "unit_of_measurement": None})
    return discovered


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    config = {**entry.data, **entry.options}
    definitions = await hass.async_add_executor_job(load_definitions)
    if config.get("auto_discover", False):
        additional = await hass.async_add_executor_job(discover_definitions, config, definitions)
        definitions.extend(additional)
        _LOGGER.info("Discovered %s additional Web2Com OIDs", len(additional))
    coordinator = Web2ComCoordinator(hass, config, definitions)
    # Register entities first; initial refresh is handled by the coordinator.
    async_add_entities([Web2ComSensor(coordinator, config, d) for d in definitions])
    await coordinator.async_refresh()


class Web2ComSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator: Web2ComCoordinator, config: dict, definition: dict):
        super().__init__(coordinator)
        self.definition = definition
        self._attr_has_entity_name = True
        self._attr_unique_id = f"web2com_{config['host']}_{definition['key']}"
        self._attr_entity_registry_enabled_default = definition.get("enabled_by_default", True)
        if self._attr_entity_registry_enabled_default:
            self._attr_translation_key = definition["key"]
        else:
            self._attr_name = definition.get("name", definition["key"])
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_unit_of_measurement = definition.get("unit_of_measurement") or None
        cls = definition.get("device_class")
        self._attr_device_class = (
            SensorDeviceClass.TEMPERATURE if cls == "temperature" else
            SensorDeviceClass.ENERGY if cls == "energy" else None
        )
        self._attr_state_class = (
            SensorStateClass.TOTAL_INCREASING if cls == "energy" else
            SensorStateClass.MEASUREMENT if cls == "temperature" else None
        )
        self._enum_map = definition.get("enum_map") or {}
        self._is_heater_mode = definition["key"] == "heater_mode_raw"
        if self._is_heater_mode:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = ["automatic", "manual", "off"]
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"gateway_{config['host']}")},
            "name": "Ochsner Web2Com",
            "manufacturer": "Ochsner",
            "model": "Room Terminal",
            "configuration_url": f"http://{config['host']}/",
        }

    @property
    def available(self) -> bool:
        return self.definition["id"] in (self.coordinator.data or {})

    @property
    def native_value(self):
        raw = (self.coordinator.data or {}).get(self.definition["id"])
        if raw is None or raw == "":
            return None
        if self._is_heater_mode:
            try:
                return {0: "off", 1: "automatic", 4: "manual"}.get(int(float(raw)))
            except (ValueError, TypeError):
                return None
        if self._enum_map:
            try:
                numeric = float(raw)
                code = str(int(numeric)) if numeric.is_integer() else str(numeric)
                return self._enum_map.get(code, str(raw))
            except (ValueError, TypeError):
                return str(raw)
        if self._attr_device_class is not None or self._attr_native_unit_of_measurement:
            try:
                return float(raw)
            except (ValueError, TypeError):
                return None
        return raw
