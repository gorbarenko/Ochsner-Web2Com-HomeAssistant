"""Strict, bounded Web2Com SOAP transport. No implicit write retries."""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

NS = 'http://ws01.lom.ch/soap/'
OID_RE = re.compile(r'^/\d+(?:/\d+){4}$')
CODE_RE = re.compile(r'^\d{2}:\d{2}$')


class Web2ComSOAPError(Exception):
    """A transport, protocol or readback failure."""


def local(tag):
    return tag.rsplit('}', 1)[-1]


def child(el, name):
    return next((c for c in el if local(c.tag) == name), None)


def text(el, name, default=''):
    node = child(el, name)
    return node.text.strip() if node is not None and node.text else default


def numeric(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Non-finite reading')
    return result


class Web2ComSOAPClient:
    def __init__(self, config):
        host = config['host']
        if not re.fullmatch(r'[A-Za-z0-9.\-]+(?::\d{1,5})?', host):
            raise ValueError('Enter a hostname or IPv4 address, optionally with port')
        self.url = f'http://{host}/ws'
        auth_type = HTTPBasicAuth if config.get('authentication') == 'Basic' else HTTPDigestAuth
        self.auth = auth_type(config['username'], config['password'])

    def _send(self, operation, inner):
        actions = {'getDpRequest': 'getDP', 'listDpRequest': 'listDP', 'writeDpRequest': 'writeDP'}
        xml = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
               f'xmlns:ns="{NS}"><s:Body><ns:{operation}>{inner}</ns:{operation}>'
               '</s:Body></s:Envelope>')
        try:
            with requests.Session() as session:
                response = session.post(self.url, data=xml.encode(), auth=self.auth,
                    headers={'Content-Type': 'text/xml; charset=utf-8',
                             'SOAPAction': NS + actions[operation]},
                    timeout=(3, 5), allow_redirects=False)
            if response.status_code != 200:
                raise Web2ComSOAPError(f'HTTP {response.status_code}')
            content = response.content
            if not content or len(content) > 1_000_000 or b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
                raise Web2ComSOAPError('Empty, oversized or unsafe SOAP response')
            root = ET.fromstring(content)
            body = next((el for el in root.iter() if local(el.tag) == 'Body'), None)
            if body is None or child(body, 'Fault') is not None:
                raise Web2ComSOAPError('SOAP body missing or fault returned')
            result = child(body, operation.replace('Request', 'Response'))
            if result is None:
                raise Web2ComSOAPError('Unexpected SOAP response')
            return result
        except (requests.RequestException, ET.ParseError) as err:
            # Do not expose host credentials or raw SOAP bodies to diagnostics.
            raise Web2ComSOAPError(type(err).__name__) from err

    @staticmethod
    def _oid(oid):
        if not OID_RE.fullmatch(oid):
            raise ValueError('Expected a leaf OID')
        return oid

    def read_many(self, oids, expected=None):
        """Semicolon group reads, as in ioBroker; never trust ambiguous ordering.

        Multi-OID responses need unique matching (index, internal code) pairs.
        Firmware without these identities uses scalar fallback in the engine.
        """
        if not 1 <= len(oids) <= 4 or len(set(oids)) != len(oids):
            raise ValueError('Invalid batch')
        for oid in oids:
            self._oid(oid)
        result = self._send('getDpRequest',
            f'<ref><oid>{escape(";".join(oids))}</oid><prop/></ref><startIndex>0</startIndex><count>-1</count>')
        nodes = [n for n in result if local(n.tag) == 'dpCfg']
        if len(nodes) != len(oids):
            raise Web2ComSOAPError('Partial or oversized response')
        found = {}
        for node in nodes:
            index, code = text(node, 'index'), text(node, 'name')
            if len(oids) == 1:
                oid = oids[0]
                if index != oid.rsplit('/', 1)[1]:
                    raise Web2ComSOAPError('Scalar index mismatch')
            else:
                matches = [o for o in oids if o.rsplit('/', 1)[1] == index and (expected or {}).get(o) == code]
                if len(matches) != 1:
                    raise Web2ComSOAPError('Ambiguous group identity')
                oid = matches[0]
            if oid in found or ((expected or {}).get(oid) and expected[oid] != code):
                raise Web2ComSOAPError('Unexpected or duplicate datapoint')
            try:
                value = numeric(text(node, 'value'))
            except (ValueError, TypeError) as err:
                raise Web2ComSOAPError('Invalid numeric reading') from err
            found[oid] = {'value': value, 'code': code, 'properties': text(node, 'prop'),
                'unit': text(node, 'unit'), 'min': text(node, 'minValue'),
                'max': text(node, 'maxValue'), 'step': text(node, 'step')}
        return found

    def read(self, oid, code=None):
        return self.read_many([oid], {oid: code} if code else None)[oid]

    def list_children(self, oid):
        if not re.fullmatch(r'/\d+(?:/\d+){2,3}', oid):
            raise ValueError('Discovery outside supported depth')
        result = self._send('listDpRequest',
            f'<ref><oid>{oid}</oid><prop/></ref><startIndex>0</startIndex><count>32</count>')
        children = []
        for node in result:
            index = text(node, 'index')
            if local(node.tag) != 'dpLst' or not index.isdigit():
                continue
            children.append({'id': f'{oid}/{index}', 'code': text(node, 'name'),
                             'properties': text(node, 'prop')})
        return children[:32]

    def write(self, oid, value):
        self._oid(oid)
        value = numeric(value)
        index = oid.rsplit('/', 1)[1]
        self._send('writeDpRequest', f'<ref><oid>{oid}</oid><prop/></ref>'
                   f'<dp><index>{index}</index><name/><prop/><desc/><value>{value:g}</value>'
                   '<unit/><timestamp>0</timestamp></dp>')
