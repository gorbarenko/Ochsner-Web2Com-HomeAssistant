"""Stable catalog, circuit-scoped aliases and conservative control allowlist."""
from __future__ import annotations
import json
from pathlib import Path
from .const import DEFAULT_SENSORS, DOMAIN

DEVICE_NAMES = {'hc1': 'Контур 1 — тепла підлога', 'hc2': 'Контур 2 — радіатори',
                'heaters': 'ТЕНи', 'terminal': 'Room Terminal'}
TEMPERATURE_CODES = {'03:01': 'base', '03:12': 'design_outdoor', '03:13': 'design_flow',
                     '03:21': 'heating_limit', '03:51': 'day', '03:53': 'night',
                     '07:09': 'manual_temperature'}
MODE_OPTIONS = {'automatic': 1, 'manual': 4}  # Off is read-only until verified on the hardware.
CIRCUIT_MODES = {'standby': 0, 'automatic': 1, 'normal': 4, 'reduced': 5, 'manual': 7}


def device_key(oid):
    return {'2': 'heaters', '4': 'hc1', '5': 'hc2'}.get(oid.split('/')[3], 'terminal')


def device_info(identity, group):
    identifier = f'gateway_{identity}' if group == 'terminal' else f'gateway_{identity}_{group}'
    info = {'identifiers': {(DOMAIN, identifier)}, 'name': DEVICE_NAMES[group],
            'manufacturer': 'Ochsner', 'model': 'Room Terminal' if group == 'terminal' else 'Web2Com'}
    if group != 'terminal':
        info['via_device'] = (DOMAIN, f'gateway_{identity}')
    return info


def load_catalog():
    extras = json.loads(Path(__file__).with_name('extra_sensors.json').read_text())
    by_oid = {d['id']: d for d in extras}
    result = []
    for raw in [*DEFAULT_SENSORS, *extras]:
        d = {**by_oid.get(raw['id'], {}), **raw}
        d.setdefault('key', 'oid_' + d['id'].strip('/').replace('/', '_'))
        d['device'] = device_key(d['id'])
        d.setdefault('enabled_by_default', True)
        result.append(d)
    return list({d['id']: d for d in reversed(result)}.values())


def deduplicate(definitions, preferred_keys=()):
    """Choose one entity, retain every alias key for registry/history migration."""
    groups = {}
    ranks = {key: i for i, key in enumerate(preferred_keys)}
    for raw in definitions:
        d = dict(raw)
        d.setdefault('device', device_key(d['id']))
        identity = (d['device'], d.get('code') or d['id'])
        groups.setdefault(identity, []).append(d)
    result = []
    for items in groups.values():
        items.sort(key=lambda d: (ranks.get(d['key'], 100000), not d.get('enabled_by_default', True)))
        winner = dict(items[0])
        winner['aliases'] = list({(a['key'], a['id']) for d in items
                                  for a in [d, *({'key': k, 'id': o} for k, o in d.get('aliases', []))]})
        result.append(winner)
    return result


def controls(definitions):
    result = []
    for d in definitions:
        code = d.get('code')
        group = d['device']
        if group in ('hc1', 'hc2') and code in TEMPERATURE_CODES:
            result.append({**d, 'kind': 'number', 'control_key': f'{group}_{TEMPERATURE_CODES[code]}_control'})
        elif group in ('hc1', 'hc2') and code == '03:50':
            result.append({**d, 'kind': 'select', 'control_key': f'{group}_operating_mode', 'options': CIRCUIT_MODES})
        elif d['id'] == '/1/2/2/108/0':
            result.append({**d, 'kind': 'select', 'control_key': 'heater_operating_mode', 'options': MODE_OPTIONS})
    return result
