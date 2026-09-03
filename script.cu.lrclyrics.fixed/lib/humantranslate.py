#-*- coding: UTF-8 -*-
import re

import requests
from bs4 import BeautifulSoup

from lib.utils import log

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0 Safari/537.36',
}

# these two Czech/Slovak fan sites share the same layout, just a different
# domain and a slightly different URL word ("piesni" vs "pisni")
_KARAOKETEXTY_DOMAIN = {'sk': 'www.karaoketexty.sk', 'cs': 'www.karaoketexty.cz'}
_KARAOKETEXTY_PATH_PREFIX = {'sk': 'texty-piesni', 'cs': 'texty-pisni'}

# Czech and Slovak are close enough that a translation in the "wrong" one
# of the two is still a far better stand-in than a machine translation -
# used when the exact target language has no human translation available
_CROSS_FALLBACK = {'sk': 'cs', 'cs': 'sk'}

# LyricsTranslate.com itself covers all 5 of this addon's target languages,
# not just Czech/Slovak - used to bias the discovery search toward the
# right translation when a song has pages in multiple languages
_LT_LANG_NAME = {'en': 'english', 'es': 'spanish', 'de': 'german', 'sk': 'slovak', 'cs': 'czech'}

HUMAN_SOURCE_PREFIXES = ('LyricsTranslate', 'KaraokeTexty')


def is_human_source(name):
    return bool(name) and any(name.startswith(p) for p in HUMAN_SOURCE_PREFIXES)


def _get(url, params=None, debug=False, what=''):
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        log('%s error: %s' % (what, e), debug=debug)
        return None


# ---------------------------------------------------------------- KaraokeTexty

def _karaoketexty_find_url(lang, artist, title, debug=False):
    domain = _KARAOKETEXTY_DOMAIN.get(lang)
    if not domain:
        return None
    html = _get('https://%s/search' % domain, params={'q': '%s %s' % (artist, title)},
                 debug=debug, what='karaoketexty search')
    if not html:
        return None
    prefix = _KARAOKETEXTY_PATH_PREFIX[lang]
    m = re.search(r'href="(/%s/[a-z0-9-]+/[a-z0-9-]+)"' % prefix, html)
    if not m:
        log('karaoketexty (%s): search returned no matching link' % domain, debug=debug)
        return None
    url = 'https://%s%s' % (domain, m.group(1))
    log('karaoketexty (%s): found %s' % (domain, url), debug=debug)
    return url


def _karaoketexty_lines(lang, artist, title, debug=False):
    url = _karaoketexty_find_url(lang, artist, title, debug=debug)
    if not url:
        return None
    html = _get(url, debug=debug, what='karaoketexty fetch')
    if not html:
        return None
    soup = BeautifulSoup(html, 'html.parser')
    lines = []
    # each para_row is one verse: para_col1 = original, para_col2 =
    # translation, individual lines inside a column are separated by <br>.
    # Deliberately NOT using col.find_all('br') + br.replace_with('\n') -
    # that combination silently drops lines under the old bs4 4.8.2 bundled
    # with this Kodi build (confirmed: modern bs4 gets the full line count
    # from the exact same page, old bs4 loses some). Splitting the raw
    # inner-HTML string on <br> with a plain regex instead only relies on
    # decode_contents(), which is stable across bs4 versions.
    for row in soup.select('div.para_row'):
        col = row.select_one('span.para_col2')
        if not col:
            continue
        for chunk in re.split(r'<br\s*/?>', col.decode_contents()):
            text = re.sub(r'<[^>]+>', '', chunk)
            text = BeautifulSoup(text, 'html.parser').get_text().strip()
            if text:
                lines.append(text)
    return lines or None


# -------------------------------------------------------------- LyricsTranslate

def _lyricstranslate_find_url(artist, title, target_lang, debug=False):
    # LyricsTranslate's own search is behind a Cloudflare challenge that a
    # plain scripted request can't solve - a DuckDuckGo site: search finds
    # the same page without ever hitting lyricstranslate.com's own search
    lang_name = _LT_LANG_NAME.get(target_lang, target_lang)
    query = 'site:lyricstranslate.com %s %s %s' % (artist, title, lang_name)
    html = _get('https://html.duckduckgo.com/html/', params={'q': query},
                 debug=debug, what='lyricstranslate discovery search')
    if not html:
        return None
    urls = re.findall(r'https?://lyricstranslate\.com/[a-z]{2}/[a-z0-9-]+\.html', html)
    log('lyricstranslate discovery: found %d candidate url(s)' % len(urls), debug=debug)
    # an "-artist-lyrics.html" result is the artist's index page, not a
    # specific translation - prefer anything else if there's a choice
    for u in urls:
        if not u.endswith('-lyrics.html'):
            log('lyricstranslate discovery: using %s' % u, debug=debug)
            return u
    result = urls[0] if urls else None
    if result:
        log('lyricstranslate discovery: using %s (fallback, only artist index found)' % result, debug=debug)
    return result


def _lyricstranslate_lines(artist, title, target_lang, debug=False):
    url = _lyricstranslate_find_url(artist, title, target_lang, debug=debug)
    if not url:
        return None
    html = _get(url, debug=debug, what='lyricstranslate fetch')
    if not html:
        return None
    if 'Just a moment' in html[:2000]:
        # Cloudflare challenge page - not solvable from a scripted request,
        # treat exactly like any other failed source and move on
        log('lyricstranslate blocked by Cloudflare', debug=debug)
        return None
    soup = BeautifulSoup(html, 'html.parser')
    container = soup.select_one('div.translate-node-text')
    if not container:
        return None
    lines = []
    for par in container.select('div.par'):
        # per-line divs are named like ll-0-1, ll-0-2, ... in document order
        for div in par.select('div[class^="ll-"]'):
            text = div.get_text().strip()
            if text:
                lines.append(text)
    return lines or None


# --------------------------------------------------------------- orchestrator

def fetch_human_translation(artist, title, target_lang, debug=False):
    # returns (lines, source_name) or (None, None). No caller-side line-count
    # guarantee - for synced lyrics the caller must check the result lines
    # up against its own original line count before trusting it for sync,
    # since a human translation may merge/split lines differently
    log('trying LyricsTranslate for %s - %s (%s)' % (artist, title, target_lang), debug=debug)
    lines = _lyricstranslate_lines(artist, title, target_lang, debug=debug)
    if lines:
        log('LyricsTranslate: got %d lines' % len(lines), debug=debug)
        return lines, 'LyricsTranslate'
    log('LyricsTranslate: no result', debug=debug)

    if target_lang in _KARAOKETEXTY_DOMAIN:
        log('trying KaraokeTexty (%s) for %s - %s' % (target_lang, artist, title), debug=debug)
        lines = _karaoketexty_lines(target_lang, artist, title, debug=debug)
        if lines:
            log('KaraokeTexty: got %d lines' % len(lines), debug=debug)
            return lines, 'KaraokeTexty'
        log('KaraokeTexty (%s): no result' % target_lang, debug=debug)
        cross = _CROSS_FALLBACK.get(target_lang)
        if cross:
            log('trying KaraokeTexty cross-fallback (%s)' % cross, debug=debug)
            lines = _karaoketexty_lines(cross, artist, title, debug=debug)
            if lines:
                log('KaraokeTexty (%s) cross-fallback: got %d lines' % (cross, len(lines)), debug=debug)
                return lines, 'KaraokeTexty (%s)' % cross.upper()
            log('KaraokeTexty (%s) cross-fallback: no result' % cross, debug=debug)
    else:
        log('target language %s not supported by KaraokeTexty' % target_lang, debug=debug)

    return None, None
