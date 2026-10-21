"""Bounded read-only discovery, restricted to the three known controller branches."""
import time
from .soap_client import CODE_RE, Web2ComSOAPError
from .catalog import device_key


def discover(client, existing, pause=time.sleep):
    known = {d['id'] for d in existing}
    result = []
    requests_left = 25
    for root in ('/1/2/2', '/1/2/4', '/1/2/5'):
        if requests_left <= 0:
            break
        requests_left -= 1
        try:
            pause(0.3)
            branches = client.list_children(root)
        except Web2ComSOAPError:
            continue
        for branch in branches[:7]:
            if requests_left <= 0:
                break
            requests_left -= 1
            try:
                pause(0.3)
                leaves = client.list_children(branch['id'])
            except Web2ComSOAPError:
                continue
            for item in leaves:
                if item['id'] in known or len(result) >= 80 or item['properties'][1:2] != 'r' or not CODE_RE.fullmatch(item['code']):
                    continue
                known.add(item['id'])
                result.append({**item, 'key': 'discovered_' + item['id'].strip('/').replace('/', '_'),
                    'device': device_key(item['id']), 'enabled_by_default': False,
                    'scan_interval': 300, 'discovered': True})
    return result
