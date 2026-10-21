"""Serialized polling, last-good cache and verified writes; independent of HA."""
from __future__ import annotations
import math
import re
import threading
import time
from .soap_client import Web2ComSOAPError, numeric


class PollEngine:
    def __init__(self, client, definitions, clock=time.time, pause=time.sleep):
        self.client, self.definitions = client, definitions
        self.clock, self.pause = clock, pause
        self.lock = threading.Lock()
        self.cache, self.metadata, self.errors, self.due, self.failures = {}, {}, {}, {}, {}
        self.write_errors = {}
        self.group_retry = 0
        self.last_request = 0

    def request(self, method, *args):
        self.pause(max(0, 0.3 - (self.clock() - self.last_request)))
        try:
            return method(*args)
        finally:
            self.last_request = self.clock()

    def restore(self, saved):
        known = {d['id'] for d in self.definitions}
        for oid, item in (saved or {}).items():
            try:
                value, stamp = numeric(item['value']), numeric(item['updated'])
                if oid in known and 0 < stamp <= self.clock():
                    self.cache[oid] = {'value': value, 'updated': stamp}
            except (ValueError, KeyError, TypeError):
                continue
        # Metadata is intentionally never restored: controls need a live verification.

    def accept(self, oid, item):
        self.cache[oid] = {'value': numeric(item['value']), 'updated': self.clock()}
        self.metadata[oid] = item
        self.errors.pop(oid, None)
        self.failures.pop(oid, None)

    def stale(self, oid, interval=60):
        item = self.cache.get(oid)
        return not item or oid in self.errors or self.clock() - item['updated'] > max(90, interval * 3)

    def snapshot(self):
        return {oid: dict(item) for oid, item in self.cache.copy().items()}

    def poll(self, active):
        with self.lock:
            now = self.clock()
            due = [d for d in self.definitions if d['id'] in active and self.due.get(d['id'], 0) <= now]
            due.sort(key=lambda d: self.due.get(d['id'], 0))
            selected = due[:4]
            if not selected:
                return self.snapshot()
            results = {}
            expected = {d['id']: d.get('code') or self.metadata.get(d['id'], {}).get('code') for d in selected}
            if len(selected) > 1 and all(expected.values()) and now >= self.group_retry:
                try:
                    results = self.request(self.client.read_many, [d['id'] for d in selected], expected)
                except (Web2ComSOAPError, ValueError):
                    self.group_retry = now + 600
            for d in selected:
                oid = d['id']
                interval = max(15, int(d.get('scan_interval', 60)))
                try:
                    item = results.get(oid)
                    if item is None:
                        item = self.request(self.client.read, oid, expected[oid])
                    self.accept(oid, item)
                    self.due[oid] = self.clock() + interval
                except (Web2ComSOAPError, ValueError) as err:
                    self.errors[oid] = type(err).__name__
                    self.failures[oid] = self.failures.get(oid, 0) + 1
                    self.due[oid] = self.clock() + min(300, interval * 2 ** min(self.failures[oid], 4))
            return self.snapshot()

    @staticmethod
    def verify_control(control, meta):
        prop = meta.get('properties', '')
        if len(prop) < 3 or prop[1:3] != 'rw':
            raise ValueError('Controller does not grant read/write access')
        if control.get('code') and control['code'] != meta.get('code'):
            raise ValueError('Controller internal code changed')
        if control['kind'] == 'select':
            match = re.search(r'\benum\s*=\s*(-?\d+(?:\s*,\s*-?\d+)*)\s*$', prop)
            if not match:
                raise ValueError('No verified enum values')
            allowed = {int(v) for v in match[1].split(',')}
            options = {k: v for k, v in control['options'].items() if v in allowed}
            if not options:
                raise ValueError('No supported modes')
            return options
        low, high, step = (numeric(meta[k]) for k in ('min', 'max', 'step'))
        if meta.get('unit') not in ('°C', 'C', 'degC') or not -80 <= low < high <= 120 or not 0 < step <= 5:
            raise ValueError('Unverified temperature limits or unit')
        return low, high, step

    def write_control(self, control, requested):
        with self.lock:
            oid = control['id']
            # Fresh read immediately before every write; never trust stale metadata.
            meta = self.request(self.client.read, oid, control.get('code'))
            limits = self.verify_control(control, meta)
            if control['kind'] == 'select':
                if requested not in limits:
                    raise ValueError('Unsupported mode')
                value = limits[requested]
            else:
                value = numeric(requested)
                low, high, step = limits
                if not low <= value <= high or not math.isclose((value-low)/step, round((value-low)/step), abs_tol=1e-6):
                    raise ValueError('Value violates controller bounds or step')
            try:
                self.request(self.client.write, oid, value)
            except (Web2ComSOAPError, ValueError):
                self.errors[oid] = 'write_not_confirmed'
                self.write_errors[oid] = 'Write response not confirmed; command was not retried'
                self.due[oid] = 0
                raise
            # Only reads may be retried. Give asynchronous controllers time to settle.
            actual = None
            for delay in (1, 2, 4):
                self.pause(delay)
                try:
                    actual = self.request(self.client.read, oid, control.get('code'))
                    self.accept(oid, actual)
                except (Web2ComSOAPError, ValueError) as err:
                    self.errors[oid] = type(err).__name__
                    continue
                if math.isclose(actual['value'], value, rel_tol=0, abs_tol=1e-6):
                    self.write_errors.pop(oid, None)
                    return self.snapshot()
            self.due[oid] = 0
            if oid in self.errors:
                message = f'Write not confirmed for {oid}: requested {value:g}; latest readback failed'
            else:
                # A fresh but different value is NOT a stale reading.
                message = (f'Write not confirmed for {oid}: requested {value:g}, '
                           f'controller returned {actual["value"]:g}')
            self.write_errors[oid] = message
            raise Web2ComSOAPError(message)
