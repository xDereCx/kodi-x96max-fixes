#-*- coding: UTF-8 -*-
import re
import urllib.parse
import requests
from lib.utils import log

# strips [mm:ss.xx] / [mm:ss] LRC timestamp tags so only the human-readable
# lines get sent to the translation API
TAG_RE = re.compile(r'\[\d+:\d+(?:[.:]\d+)?\]')

LINGVA_INSTANCE_DEFAULT = 'lingva.ml'

# cheap, English-only heuristic to skip pointlessly "translating" lyrics
# that are already in English when the target language is also English -
# not a real language detector (that would need work per target language,
# e.g. Slovak/Czech/German/Spanish stopword lists, to do safely), just
# common-word frequency, which is good enough for full-sentence lyrics
# without an extra API call or dependency. Only ever consulted when
# target_lang == 'en'.
_EN_STOPWORDS = frozenset((
    'the', 'and', 'you', 'i', 'to', 'a', 'of', 'in', 'is', 'it', 'for',
    'that', 'with', 'on', 'my', 'me', 'your', 'we', 'this', 'be', 'are',
    'was', 'have', 'not', 'but', 'all', 'so', 'just', 'know', 'like',
    'what', 'no', 'when', 'if', 'can', 'do', 'don', 'never', 'will',
    'now', 'they', 'she', 'he', 'her', 'him', 'our', 'us', 'up', 'out',
))
_WORD_RE = re.compile(r"[a-zA-Z']+")


def looks_like_english(text, min_words=15, threshold=0.12):
    words = _WORD_RE.findall(text.lower())
    if len(words) < min_words:
        # too short to trust the ratio either way - don't skip, let the
        # real translation call happen
        return False
    hits = sum(1 for w in words if w in _EN_STOPWORDS)
    return (hits / len(words)) >= threshold


def strip_lrc_tags(text):
    return TAG_RE.sub('', text)


def _deepl_endpoint(api_key):
    # free-tier keys are suffixed ":fx" and only work against the free
    # subdomain; paid keys 404 on it
    return 'https://api-free.deepl.com/v2/translate' if api_key.endswith(':fx') else 'https://api.deepl.com/v2/translate'


def _translate_deepl(text, target_lang, api_key, debug=False):
    if not text or not api_key:
        return None
    try:
        resp = requests.post(
            _deepl_endpoint(api_key),
            headers={'Authorization': 'DeepL-Auth-Key %s' % api_key},
            data={'text': text, 'target_lang': target_lang.upper()},
            timeout=10,
        )
        resp.raise_for_status()
        translations = resp.json().get('translations') or []
        if translations:
            return translations[0].get('text')
    except Exception as e:
        log('DeepL translation error: %s' % e, debug=debug)
    return None


def _translate_google(text, target_lang, debug=False):
    # unofficial endpoint (no key, no official ToS support) used by many
    # open-source translation tools - same underlying engine Lingva
    # proxies, but calling it directly removes the dependency on a public
    # Lingva instance's uptime specifically
    if not text:
        return None
    try:
        resp = requests.get(
            'https://translate.googleapis.com/translate_a/single',
            params={'client': 'gtx', 'sl': 'auto', 'tl': target_lang.lower(), 'dt': 't', 'q': text},
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=10,
        )
        resp.raise_for_status()
        segments = resp.json()[0] or []
        return ''.join(seg[0] for seg in segments if seg and seg[0])
    except Exception as e:
        log('Google translation error: %s' % e, debug=debug)
    return None


def _translate_lingva(text, target_lang, instance=LINGVA_INSTANCE_DEFAULT, debug=False):
    # free, no API key, auto-detects the source language - last-resort
    # fallback if the direct Google endpoint is also unreachable/blocked
    if not text:
        return None
    try:
        url = 'https://%s/api/v1/auto/%s/%s' % (instance, target_lang.lower(), urllib.parse.quote(text, safe=''))
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json().get('translation')
    except Exception as e:
        log('Lingva translation error: %s' % e, debug=debug)
    return None


def _translate_fallback(text, target_lang, instance, debug=False):
    result = _translate_google(text, target_lang, debug=debug)
    if result:
        return result, 'Google'
    result = _translate_lingva(text, target_lang, instance=instance, debug=debug)
    return result, ('Lingva' if result else None)


def translate_text(text, target_lang, api_key, lingva_instance=LINGVA_INSTANCE_DEFAULT, debug=False):
    # returns (translated_text, source_name) so the UI can show which
    # provider actually produced the result - source_name is None if all
    # three failed (translated_text is then also None)
    if not text:
        return None, None
    if api_key:
        result = _translate_deepl(text, target_lang, api_key, debug=debug)
        if result:
            return result, 'DeepL'
    return _translate_fallback(text, target_lang, lingva_instance, debug=debug)


def _translate_deepl_lines(lines, target_lang, api_key, debug=False):
    # DeepL accepts multiple "text" fields in one request and translates
    # each independently but returns them in the same order - this keeps
    # translated lines aligned 1:1 with the original timestamps in a
    # single API call, instead of guessing at how a joined blob got
    # re-wrapped or making one request per line
    if not lines or not api_key:
        return None
    try:
        resp = requests.post(
            _deepl_endpoint(api_key),
            headers={'Authorization': 'DeepL-Auth-Key %s' % api_key},
            data=[('text', line) for line in lines] + [('target_lang', target_lang.upper())],
            timeout=15,
        )
        resp.raise_for_status()
        translations = resp.json().get('translations') or []
        if len(translations) == len(lines):
            return [t.get('text', '') for t in translations]
    except Exception as e:
        log('DeepL translation error: %s' % e, debug=debug)
    return None


def _translate_fallback_lines(lines, target_lang, instance, debug=False, on_line=None):
    # no batch endpoint on either fallback - one request per non-empty
    # line, trying Google first per line then Lingva per line. on_line(i,
    # text, source), if given, fires after each line so the caller can
    # update a progressively-filling display (and show which provider is
    # actually being used right away) instead of waiting for the whole
    # song - a 30-40 line song means 30-40 sequential requests here
    result = []
    source = None
    for i, line in enumerate(lines):
        if not line.strip():
            result.append('')
            if on_line:
                on_line(i, '', source)
            continue
        translated = _translate_google(line, target_lang, debug=debug)
        source = 'Google'
        if translated is None:
            translated = _translate_lingva(line, target_lang, instance=instance, debug=debug)
            source = 'Lingva'
        if translated is None:
            return None, None
        result.append(translated)
        if on_line:
            on_line(i, translated, source)
    return result, source


def translate_lines(lines, target_lang, api_key, lingva_instance=LINGVA_INSTANCE_DEFAULT, debug=False, on_line=None):
    # returns (translated_lines, source_name), see translate_text().
    # on_line is only invoked for the per-line fallback path - DeepL's
    # batch call has no partial-progress point to report from
    if not lines:
        return None, None
    if api_key:
        result = _translate_deepl_lines(lines, target_lang, api_key, debug=debug)
        if result:
            return result, 'DeepL'
    return _translate_fallback_lines(lines, target_lang, lingva_instance, debug=debug, on_line=on_line)
