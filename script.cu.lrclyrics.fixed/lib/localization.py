import os
import re

import xbmcaddon
import xbmcvfs

ADDON = xbmcaddon.Addon()
CWD = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))

# order must match the addon_language spinner options in settings.xml -
# index into this list is what the setting actually stores
INTERFACE_LANGS = ['en', 'es', 'de', 'sk', 'cs']

_LANG_FOLDERS = {
    'en': 'resource.language.en_gb',
    'es': 'resource.language.es_es',
    'de': 'resource.language.de_de',
    'sk': 'resource.language.sk_sk',
    'cs': 'resource.language.cs_cz',
}

_PO_CACHE = {}

# msgctxt "#32001" \n msgid "..." \n msgstr "..." - only numbered entries
# (skips the "Addon Summary"/"Addon Description" msgctxt pair, which use a
# non-numeric context and aren't looked up by id)
_ENTRY_RE = re.compile(
    r'msgctxt\s+"#(\d+)"\s*\r?\n'
    r'msgid\s+"((?:[^"\\]|\\.)*)"\s*\r?\n'
    r'msgstr\s+"((?:[^"\\]|\\.)*)"'
)


def _unescape(text):
    return text.replace('\\"', '"').replace('\\n', '\n')


def _parse_po(path):
    strings = {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except OSError:
        return strings
    for num, msgid, msgstr in _ENTRY_RE.findall(content):
        # an empty msgstr means this language's translators never filled it
        # in - fall back to the msgid text itself, which for every strings.po
        # in this addon is already plain English
        text = msgstr if msgstr else msgid
        if text:
            strings[int(num)] = _unescape(text)
    return strings


def _load(lang_code):
    if lang_code not in _PO_CACHE:
        folder = _LANG_FOLDERS.get(lang_code, _LANG_FOLDERS['en'])
        path = os.path.join(CWD, 'resources', 'language', folder, 'strings.po')
        _PO_CACHE[lang_code] = _parse_po(path)
    return _PO_CACHE[lang_code]


def current_language():
    # re-read every call (not cached) so a settings change takes effect on
    # the next string lookup without needing a Kodi restart, same as every
    # other ADDON.getSetting*() call elsewhere in this addon
    try:
        idx = ADDON.getSettingInt('addon_language')
    except Exception:
        idx = 0
    if 0 <= idx < len(INTERFACE_LANGS):
        return INTERFACE_LANGS[idx]
    return 'en'


def get_string(id_):
    lang = current_language()
    strings = _load(lang)
    if id_ in strings:
        return strings[id_]
    if lang != 'en':
        en = _load('en')
        if id_ in en:
            return en[id_]
    # last-resort fallback: Kodi's own mechanism, which follows Kodi's
    # system language rather than this addon's own setting - only reached
    # for an id that exists in neither this language's strings.po nor
    # English's, which shouldn't happen for any id this addon actually uses
    return ADDON.getLocalizedString(id_)
