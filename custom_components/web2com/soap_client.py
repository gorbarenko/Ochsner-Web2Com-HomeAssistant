"""Bounded, read-only SOAP discovery and group reads for Ochsner Room Terminal."""
from __future__ import annotations
import xml.etree.ElementTree as ET
import logging
import re
import requests
from requests.auth import HTTPDigestAuth, HTTPBasicAuth

_LOGGER = logging.getLogger(__name__)
SOAP_NS = 'http://schemas.xmlsoap.org/soap/envelope/'
NS = 'http://ws01.lom.ch/soap/'
OID_RE = re.compile(r'^/\d+(?:/\d+)*$')


def _local(tag):
    return tag.rsplit('}', 1)[-1].split(':')[-1]


def _child(el, name):
    return next((c for c in el if _local(c.tag) == name), None) if el is not None else None


def _text(el, name, default=None):
    found = _child(el, name)
    return found.text if found is not None and found.text is not None else default


class Web2ComSOAPError(Exception):
    pass


class Web2ComSOAPClient:
    def __init__(self, config):
        self.url = f"http://{config['host']}/ws"
        auth_type = HTTPBasicAuth if config.get('authentication') == 'Basic' else HTTPDigestAuth
        self.auth = auth_type(config['username'], config['password'])

    def _send(self, operation, inner):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" '
            'xmlns:ns="http://ws01.lom.ch/soap/">'
            f'<SOAP-ENV:Body><ns:{operation}>{inner}</ns:{operation}></SOAP-ENV:Body>'
            '</SOAP-ENV:Envelope>'
        )
        try:
            with requests.Session() as session:
                response = session.post(self.url, data=xml.encode('utf-8'), auth=self.auth,
                    headers={'Content-Type':'text/xml; charset=utf-8',
                             'SOAPAction': f'http://ws01.lom.ch/soap/{"listDP" if operation == "listDpRequest" else "readDP"}'},
                    timeout=(5, 12))
            response.raise_for_status()
            if not response.content:
                raise Web2ComSOAPError('Empty SOAP response')
            root = ET.fromstring(response.content)
            body = next((el for el in root.iter() if _local(el.tag) == 'Body'), None)
            if body is None:
                raise Web2ComSOAPError('SOAP Body missing')
            fault = _child(body, 'Fault')
            if fault is not None:
                raise Web2ComSOAPError('SOAP Fault: ' + ET.tostring(fault, encoding='unicode')[:500])
            return body
        except (requests.RequestException, ET.ParseError) as err:
            raise Web2ComSOAPError(str(err)) from err

    @staticmethod
    def _oid(oid):
        if oid != '' and not OID_RE.fullmatch(oid):
            raise ValueError('Unsafe or invalid OID')
        return oid

    def list_children(self, oid=''):
        self._oid(oid)
        # The listDpRequest is confirmed by a captured browser request.
        from xml.sax.saxutils import escape
        inner = f'<ref><oid>{escape(oid)}</oid><prop></prop></ref><startIndex>0</startIndex><count>0</count>'
        body = self._send('listDpRequest', inner)
        response = _child(body, 'listDpResponse')
        if response is None:
            raise Web2ComSOAPError('listDpResponse missing')
        children = []
        for node in response:
            if _local(node.tag) != 'dpLst':
                continue
            idx = _text(node, 'index')
            if idx is None or not idx.isdigit():
                continue
            children.append({
                'oid': f'{oid}/{idx}',
                'name': _text(node, 'name', ''),
                'properties': _text(node, 'prop', ''),
                'description': _text(node, 'desc', ''),
            })
        return children

    def read_group(self, parent_oid):
        """Read a parent OID in one SOAP request; reject unknown layouts.

        Return a mapping of leaf OID to text value; callers fall back to scalar
        reads if their known OIDs are not contained in the response.
        """
        self._oid(parent_oid)
        from xml.sax.saxutils import escape
        inner = (f'<ref><oid>{escape(parent_oid)}</oid><prop/></ref>'
                 '<startIndex>0</startIndex><count>20</count>')
        body = self._send('getDpRequest', inner)
        response = _child(body, 'getDpResponse')
        if response is None:
            raise Web2ComSOAPError('getDpResponse missing')
        found = {}
        for node in response:
            kind = _local(node.tag)
            if kind == 'dpCfg':
                value = _text(node, 'value')
                index = _text(node, 'index')
                if value is None:
                    continue
                if index is not None and index.isdigit():
                    found[f'{parent_oid}/{index}'] = value
                else:
                    found[parent_oid] = value
            elif kind in ('dpLst', 'dp'):
                index = _text(node, 'index')
                value = _text(node, 'value')
                if index is not None and index.isdigit() and value is not None:
                    found[f'{parent_oid}/{index}'] = value
        return found

    def discover(self, root='/1/2', max_nodes=120, max_depth=4):
        """Bounded discovery. Never write, only list nodes; no infinite recursion."""
        self._oid(root)
        pending = [(root, 0)]
        visited = set()
        results = {}
        while pending and len(visited) < max_nodes:
            parent, depth = pending.pop(0)
            if parent in visited:
                continue
            visited.add(parent)
            try:
                children = self.list_children(parent)
            except Web2ComSOAPError as err:
                _LOGGER.debug('OID discovery %s: %s', parent, err)
                continue
            for child in children:
                results[child['oid']] = child
                props = child['properties']
                if depth + 1 < max_depth and len(visited) + len(pending) < max_nodes:
                    if 'd' in props[:4] or child['description'] == 'unit':
                        pending.append((child['oid'], depth+1))
        return results
