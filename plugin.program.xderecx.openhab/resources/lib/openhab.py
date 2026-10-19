# -*- coding: utf-8 -*-
"""Minimal openHAB REST client (no Kodi imports, so it can be tested outside Kodi)."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

NAMESPACE = 'kodi'   # item metadata namespace this add-on reads (see README)


class OpenHABError(Exception):
    pass


class OpenHAB:
    def __init__(self, url, token, timeout=8):
        self.base = url.rstrip('/') + '/rest'
        self.token = token.strip()
        self.timeout = timeout

    def _request(self, path, data=None, content_type=None):
        req = urllib.request.Request(self.base + path, data=data)
        if self.token:
            req.add_header('Authorization', 'Bearer ' + self.token)
        if content_type:
            req.add_header('Content-Type', content_type)
        req.add_header('Accept', 'application/json')
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as err:
            raise OpenHABError('HTTP %s: %s' % (err.code, path))
        except (urllib.error.URLError, OSError) as err:
            raise OpenHABError('%s: %s' % (self.base, getattr(err, 'reason', err)))
        return body

    def items(self):
        """All items (flat) with their semantics and kodi metadata, as {name: item}."""
        q = urllib.parse.urlencode({
            'recursive': 'false',
            'metadata': 'semantics,' + NAMESPACE,
            'fields': 'name,label,type,state,transformedState,groupNames,tags,metadata,'
                      'stateDescription,commandDescription,category',
        })
        data = json.loads(self._request('/items?' + q).decode('utf-8'))
        return {i['name']: i for i in data}

    def send_command(self, name, command):
        self._request('/items/' + urllib.parse.quote(name), data=str(command).encode('utf-8'),
                      content_type='text/plain; charset=utf-8')


# ---- item helpers ----------------------------------------------------------------------------------

def semantics(item):
    """(class, config) of the openHAB semantics metadata, e.g. ('Location_Indoor_Floor', {'isPartOf': ...})."""
    md = (item.get('metadata') or {}).get('semantics') or {}
    return md.get('value') or '', md.get('config') or {}


def kodi(item):
    """(value, config) of the item's 'kodi' metadata ('', {} if it has none)."""
    md = (item.get('metadata') or {}).get(NAMESPACE) or {}
    return (md.get('value') or '').strip(), md.get('config') or {}


def label(item):
    """kodi metadata label, else the item label, else the name."""
    return kodi(item)[1].get('label') or item.get('label') or item['name']


_NUM = re.compile(r'^(-?\d+(?:\.\d+)?)(?:E[-+]?\d+)?(\s.*)?$')


def display_state(item):
    """Readable state: transformedState if the item has one, else the label of a state option (state description),
    numbers rounded to 1 decimal."""
    st = item.get('transformedState') or item.get('state')
    if st in (None, 'NULL', 'UNDEF'):
        return '–'
    for opt in (item.get('stateDescription') or {}).get('options') or []:
        if opt.get('value') == st and opt.get('label'):
            return opt['label']
    m = _NUM.match(st)
    if m:
        num = float(m.group(1))
        unit = (m.group(2) or '').strip()
        txt = ('%d' % round(num)) if num == int(num) or abs(num) >= 100 else ('%.1f' % num)   # 1023 hPa, 21.5 °C
        return (txt + ' ' + unit).strip()
    return st


def number(item):
    """State as float, or None."""
    m = _NUM.match(item.get('state') or '')
    return float(m.group(1)) if m else None


def read_only(item):
    sd = item.get('stateDescription') or {}
    return bool(sd.get('readOnly'))


def options(item):
    """[(value, label)] from commandDescription.commandOptions or stateDescription.options."""
    cd = (item.get('commandDescription') or {}).get('commandOptions') or []
    if cd:
        return [(o['command'], o.get('label') or o['command']) for o in cd]
    sd = (item.get('stateDescription') or {}).get('options') or []
    return [(o['value'], o.get('label') or o['value']) for o in sd]


def matches(item, condition):
    """True if the item state matches a condition from the metadata, e.g. '!= online', '<= 20', '== ON',
    '!~ ^[-;]*$' (regex does not match), '~ ^ERR' (regex matches). NULL/UNDEF never match."""
    st = item.get('state')
    if st in (None, 'NULL', 'UNDEF') or not condition:
        return False
    m = re.match(r'^\s*(==|!=|<=|>=|<|>|!~|~)\s*(.*?)\s*$', str(condition))
    if not m:
        return False
    op, ref = m.groups()
    if op in ('~', '!~'):
        found = re.search(ref, st) is not None
        return found if op == '~' else not found
    num, refnum = number(item), None
    try:
        refnum = float(ref)
    except ValueError:
        pass
    if num is not None and refnum is not None:
        a, b = num, refnum
    else:
        a, b = st, ref
        if op not in ('==', '!='):
            return False
    return {'==': a == b, '!=': a != b, '<=': a <= b, '>=': a >= b, '<': a < b, '>': a > b}[op]
