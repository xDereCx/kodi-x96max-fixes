#-*- coding: UTF-8 -*-
import difflib
import hashlib
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


# the exhaustive set of source names a fully human (non-hybrid) result can
# ever have - see fetch_human_translation[_synced]. Anything else, hybrid
# or not, is deliberately NOT in this set.
_FULLY_HUMAN_NAMES = frozenset((
    'LyricsTranslate', 'KaraokeTexty', 'KaraokeTexty (CS)', 'KaraokeTexty (SK)',
))


def is_fully_human_source(name):
    # unlike is_human_source(), this is False for a hybrid result (e.g.
    # "KaraokeTexty (92%)[CR]+ DeepL (8%)", see gui.py's gap-filling) -
    # used to decide whether a cached translation should be trusted
    # forever or always re-attempted. A fully human match can't improve
    # any further, but a hybrid one might (a better site match, or an
    # improvement to the alignment logic itself) - re-checking it is
    # cheap and gives that a chance instead of freezing on the first
    # partial result forever.
    #
    # Deliberately an exact whitelist match against the small fixed set of
    # fully-human names, NOT "is_human_source(name) and <hybrid marker>
    # not in name" - the hybrid display format has already changed once
    # this session (" + " to "[CR]+"), and a cache file written under the
    # older format was confirmed live to slip through a marker-absence
    # check like that (it doesn't contain the CURRENT marker, so it reads
    # as "not hybrid" even though it obviously is), permanently freezing a
    # stale hybrid result and displaying the raw internal format string.
    # An exact whitelist can't be fooled by a marker format change since
    # it doesn't care what a hybrid name looks like at all.
    return name in _FULLY_HUMAN_NAMES


# Czech and Slovak each have a handful of letters the other alphabet
# doesn't use at all - a cheap, reliable way to tell actual page CONTENT
# apart from what its DOMAIN claims. Confirmed live: karaoketexty.sk
# served a song whose translation column was entirely Czech (30 cz-only
# diacritics, 0 sk-only ones) - the site's own domain/language pairing is
# not something this addon can trust blindly.
_CZ_ONLY_CHARS = frozenset('ěřů')
_SK_ONLY_CHARS = frozenset('äľĺŕô')


def _detect_sk_cs(text):
    if not text:
        return None
    lower = text.lower()
    cz = sum(lower.count(c) for c in _CZ_ONLY_CHARS)
    sk = sum(lower.count(c) for c in _SK_ONLY_CHARS)
    if cz > sk and cz > 0:
        return 'cs'
    if sk > cz and sk > 0:
        return 'sk'
    return None  # inconclusive - too short, or no distinguishing diacritics at all


def human_translation_lang(lines, source, target_lang):
    # the actual language of a human source's text - used so a hybrid
    # result's DeepL gap-fill translates into the SAME language as the
    # human lines it's supplementing, instead of silently mixing e.g.
    # Czech human lines with Slovak machine-filled ones in one song's
    # translation panel. Detects from the real fetched CONTENT first
    # (see _detect_sk_cs) rather than trusting the domain/source name,
    # since those aren't reliable (see above) - only falls back to the
    # source-name suffix (KaraokeTexty cross-fallback, "(CS)"/"(SK)") or
    # target_lang itself when detection is inconclusive (short/plain text).
    detected = _detect_sk_cs(' '.join(l for l in (lines or []) if l))
    if detected:
        return detected
    if source and source.startswith('KaraokeTexty'):
        if '(CS)' in source:
            return 'cs'
        if '(SK)' in source:
            return 'sk'
    return target_lang


def credit_domain_for_source(source, target_lang):
    # maps a source name (as returned by fetch_human_translation[_synced])
    # back to the actual site domain to credit/link, for the end-of-song
    # "translation by X, support them" message. "KaraokeTexty" alone means
    # it used target_lang's own domain; "KaraokeTexty (CS)"/"(SK)" means
    # the cross-fallback domain was used instead - that suffix, not
    # target_lang, decides which one.
    if not source:
        return None
    if source.startswith('KaraokeTexty'):
        if '(CS)' in source:
            lang = 'cs'
        elif '(SK)' in source:
            lang = 'sk'
        else:
            lang = target_lang
        domain = _KARAOKETEXTY_DOMAIN.get(lang, '')
        return domain[4:] if domain.startswith('www.') else (domain or None)
    if source == 'LyricsTranslate':
        return 'lyricstranslate.com'
    return None


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


def _split_column(col):
    # a column's individual lines are separated by <br>. Deliberately NOT
    # using col.find_all('br') + br.replace_with('\n') - that combination
    # silently drops lines under the old bs4 4.8.2 bundled with this Kodi
    # build (confirmed: modern bs4 gets the full line count from the exact
    # same page, old bs4 loses some). Splitting the raw inner-HTML string
    # on <br> with a plain regex instead only relies on decode_contents(),
    # which is stable across bs4 versions.
    #
    # The translation column can also contain a nested div.lyrics_authors
    # (translator credit link) and div.correct (a "report a correction"
    # link) block - neither is <br>-separated from the real lyric text, so
    # left in place it silently glues onto whichever line it trails,
    # corrupting that line's content match. Strip both out first.
    col = BeautifulSoup(str(col), 'html.parser')
    for junk in col.select('div.lyrics_authors, div.correct'):
        junk.decompose()
    out = []
    for chunk in re.split(r'<br\s*/?>', col.decode_contents()):
        text = re.sub(r'<[^>]+>', '', chunk)
        text = BeautifulSoup(text, 'html.parser').get_text().strip()
        # a "line" that's purely punctuation (e.g. a standalone ellipsis
        # used as its own <br>-separated line to mark a pause/trail-off,
        # where the original combines it into the surrounding line with
        # a comma instead) normalizes to nothing and has no real content
        # to align on either side - keeping it as its own pairs entry
        # breaks the merge-window logic below, which stops at the first
        # entry with nothing to match rather than skipping past it.
        # Drop it here so real content lines stay adjacent in the list.
        if text and _normalize_for_match(text):
            out.append(text)
    return out


def _karaoketexty_translator(soup):
    # the page-level translator credit ("Preklad pridal/a <username>"),
    # used for the end-of-song "translation by X, thanks to <username>"
    # credit message - not part of the actual lyric/translation content
    link = soup.select_one('p.author a')
    return link.get_text().strip() if link else None


def _karaoketexty_pairs(lang, artist, title, debug=False):
    # returns ([(source_line, translated_line), ...], translator_name) or
    # (None, None). Keeping both columns (not just the translation) lets
    # the caller align by matching actual line CONTENT against its own
    # original lyrics, instead of only comparing total line counts - this
    # matters because a verbatim repeated chorus is usually written out
    # fewer times on a lyrics site than it's actually sung/timed in the
    # original, so raw counts frequently don't match even when every
    # unique line's translation is genuinely available.
    url = _karaoketexty_find_url(lang, artist, title, debug=debug)
    if not url:
        return None, None
    html = _get(url, debug=debug, what='karaoketexty fetch')
    if not html:
        return None, None
    soup = BeautifulSoup(html, 'html.parser')
    pairs = []
    for row in soup.select('div.para_row'):
        col1 = row.select_one('span.para_col1')
        col2 = row.select_one('span.para_col2')
        if not col1 or not col2:
            continue
        src_lines = _split_column(col1)
        trans_lines = _split_column(col2)
        # zip() safely truncates to the shorter side if a row's two
        # columns ever have a mismatched line count within themselves
        pairs.extend(zip(src_lines, trans_lines))
    if not pairs:
        return None, None
    return pairs, _karaoketexty_translator(soup)


def _karaoketexty_lines(lang, artist, title, debug=False):
    pairs, _ = _karaoketexty_pairs(lang, artist, title, debug=debug)
    if not pairs:
        return None
    return [t for _, t in pairs]


_APOSTROPHE_VARIANTS = str.maketrans({
    '‘': "'", '’': "'", 'ʼ': "'", '`': "'",
    '“': '"', '”': '"',
})
_PUNCT_RE = re.compile(r'[^\w\s\']', re.UNICODE)
_SPACE_RE = re.compile(r'\s+')


def _normalize_for_match(text):
    # a single differing character (curly vs straight quote, a comma, a
    # trailing period, double spacing) would otherwise fail an exact-match
    # comparison even though the actual words are identical - normalize
    # both sides the same way before comparing so only real wording
    # differences count as a mismatch
    text = text.translate(_APOSTROPHE_VARIANTS).lower()
    # delete apostrophes entirely rather than treating them as a word
    # boundary - two independently-transcribed sources commonly differ on
    # whether a contraction keeps its apostrophe at all, and unlike other
    # punctuation this one sits *inside* a word, so replacing it with a
    # space would wrongly split one word into two
    text = text.replace("'", '')
    text = _PUNCT_RE.sub(' ', text)
    return _SPACE_RE.sub(' ', text).strip()


def _hash8(text):
    # short content fingerprint for debug logging only - lets a real
    # content-vs-content mismatch be told apart from a matching-LOGIC bug
    # (e.g. two lines that normalize to the exact same string, confirmed
    # by an identical hash, yet still don't get matched) without ever
    # logging the actual lyric/translation text itself
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:8] if text else '--------'


_MAX_MERGE = 5
_FUZZY_MAX_WORD_DIFF = 1
_FUZZY_MIN_WORDS = 3


def _word_diff_count(a_words, b_words):
    # number of words that differ between two word sequences (inserted,
    # deleted, or replaced), via difflib's opcode diff - used instead of
    # a character-level ratio so "how many words differ" means the same
    # thing regardless of how long the line is
    sm = difflib.SequenceMatcher(None, a_words, b_words)
    diff = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != 'equal':
            diff += max(i2 - i1, j2 - j1)
    return diff


def align_by_content(original_lines, pairs, debug=False):
    # given our own original (possibly with repeated lines, e.g. a chorus
    # sung multiple times) and a list of (source_line, translated_line)
    # pairs scraped from a human site, build a translation for every
    # original line by matching its text against the scraped source
    # lines - so a repeated original line reuses whichever translation
    # its text matched, even if the human site only wrote that line once.
    #
    # A single original (timed) line sometimes corresponds to *several*
    # consecutive <br>-separated lines on the human site (e.g. our LRC has
    # one line combining two short phrases with a comma, while the site
    # writes each phrase as its own line) - confirmed live on a real song.
    # _normalize_for_match() already turns punctuation into spaces, so
    # normalized text from N consecutive site lines joined with a space
    # equals the normalized combined original line whenever this is the
    # case. Exact single-line matches are tried and applied first; only
    # the lines that don't match anything on their own fall through to
    # this merge-window check, per line, checking window sizes 2..3.
    #
    # Returns (result, matched_count); result is a list the same length
    # as original_lines (unmatched entries are ''), or None if nothing at
    # all matched.
    if not pairs:
        return None, 0
    norm_src = [_normalize_for_match(s) for s, _ in pairs]
    trans_lines = [t for _, t in pairs]

    lookup = {}
    for key, trans in zip(norm_src, trans_lines):
        if key and key not in lookup:
            lookup[key] = trans

    merged_lookup = {}
    # last-resort tier: same single lines as `lookup`, but with internal
    # whitespace removed too (not just punctuation) - catches a word split
    # differently across a <br> line-break or hyphenation quirk between
    # the two sources. This is strictly more permissive than the other
    # two tiers (dropping word boundaries can equate two genuinely
    # different phrases, e.g. "a live" vs "alive"), so it's only ever
    # consulted after both of them have already failed for a given line.
    concat_lookup = {}
    for start in range(len(pairs)):
        parts = []
        for length in range(1, _MAX_MERGE + 1):
            idx = start + length - 1
            if idx >= len(pairs) or not norm_src[idx]:
                break
            parts.append(idx)
            if length == 1:
                continue
            key = ' '.join(norm_src[start:start + length])
            if key not in merged_lookup:
                # strip any trailing comma/space the site's own line already
                # ends with before rejoining with our own ", " - confirmed
                # live, a site line ending "...jsem šilhal," joined with the
                # next produced a doubled ",," in the cached translation
                merged_lookup[key] = ', '.join(t.rstrip(' ,') for t in trans_lines[start:start + length])
        ckey = norm_src[start].replace(' ', '')
        if ckey and ckey not in concat_lookup:
            concat_lookup[ckey] = trans_lines[start]

    result = []
    matched = 0
    merged_hits = 0
    concat_hits = 0
    fuzzy_hits = 0
    for i, line in enumerate(original_lines):
        key = _normalize_for_match(line)
        trans = lookup.get(key) if key else None
        via = None
        if not trans and key:
            trans = merged_lookup.get(key)
            if trans:
                via = 'merged'
        if not trans and key:
            trans = concat_lookup.get(key.replace(' ', ''))
            if trans:
                via = 'concat'
        if not trans and key:
            # absolute last resort: a line that differs from a candidate
            # by exactly one WORD (a genuine wording variant between the
            # two sources, confirmed live) still isn't safe to discard.
            # Word-level diff count instead of a character-level
            # similarity ratio matters here: a short line (3-4 words)
            # with one wrong word can drop to a 70-80% character ratio
            # even though only one word out of several actually differs,
            # while the same single-word difference barely dents a long
            # line's ratio - a fixed percentage threshold is therefore
            # unreliable across different line lengths, but "at most one
            # differing word" means the same thing regardless of length.
            # Requires >=3 words on both sides so a 1-2 word line can't
            # trivially "match" almost anything.
            key_words = key.split()
            fuzzy_trans, fuzzy_diff = None, None
            if len(key_words) >= _FUZZY_MIN_WORDS:
                for cand_key, cand_trans in zip(norm_src, trans_lines):
                    cand_words = cand_key.split()
                    if len(cand_words) < _FUZZY_MIN_WORDS:
                        continue
                    diff = _word_diff_count(key_words, cand_words)
                    if fuzzy_diff is None or diff < fuzzy_diff:
                        fuzzy_diff, fuzzy_trans = diff, cand_trans
            if fuzzy_trans is not None and fuzzy_diff <= _FUZZY_MAX_WORD_DIFF:
                trans = fuzzy_trans
                via = 'fuzzy word-diff=%d' % fuzzy_diff
        if trans:
            matched += 1
            if via == 'merged':
                merged_hits += 1
            elif via == 'concat':
                concat_hits += 1
            elif via and via.startswith('fuzzy'):
                fuzzy_hits += 1
        result.append(trans or '')
        # diagnostic only (length + hit/miss, never the actual text)
        status = ('MATCH(%s)' % via) if via else ('MATCH' if trans else 'miss')
        log('align_by_content: line %2d len=%3d %s' % (i, len(line), status), debug=debug)
    log('align_by_content: matched %d/%d original lines (%d via merge, %d via concat, %d via fuzzy)' % (matched, len(original_lines), merged_hits, concat_hits, fuzzy_hits), debug=debug)
    if matched == 0:
        return None, 0
    return result, matched


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


def fetch_human_translation_synced(artist, title, target_lang, original_lines, debug=False):
    # for timed lyrics: like fetch_human_translation(), but aligns
    # KaraokeTexty results by matching original_lines content against the
    # site's own English column (see align_by_content) instead of only
    # accepting an exact total-count match - handles a verbatim repeated
    # chorus being written fewer times on the fan site than it's actually
    # sung. Returns (lines, source_name, translator_name, complete):
    # - lines is None only if nothing at all was found; otherwise it's a
    #   list the same length as original_lines, with '' at any position
    #   that didn't match anything human
    # - complete is True only if every position was filled - the caller
    #   should machine-translate just the remaining '' gaps rather than
    #   discarding an otherwise mostly-human result over a handful of
    #   genuinely missing lines (e.g. a chorus the fan site never
    #   transcribed in the original language at all)
    # translator_name is the individual credited translator if the site
    # shows one (KaraokeTexty), else None. Picks the best (highest
    # match count) partial result across every source tried.
    log('trying LyricsTranslate for %s - %s (%s)' % (artist, title, target_lang), debug=debug)
    lt_lines = _lyricstranslate_lines(artist, title, target_lang, debug=debug)
    if lt_lines and len(lt_lines) == len(original_lines):
        log('LyricsTranslate: got %d lines, matches original' % len(lt_lines), debug=debug)
        return lt_lines, 'LyricsTranslate', None, True
    log('LyricsTranslate: no exact-count match', debug=debug)

    best_lines, best_source, best_translator, best_matched = None, None, None, 0

    if target_lang not in _KARAOKETEXTY_DOMAIN:
        log('target language %s not supported by KaraokeTexty' % target_lang, debug=debug)
        return None, None, None, False

    langs_to_try = [target_lang]
    cross = _CROSS_FALLBACK.get(target_lang)
    if cross:
        langs_to_try.append(cross)

    for lang in langs_to_try:
        log('trying KaraokeTexty (%s) for %s - %s, content alignment' % (lang, artist, title), debug=debug)
        pairs, translator = _karaoketexty_pairs(lang, artist, title, debug=debug)
        if not pairs:
            log('KaraokeTexty (%s): no result' % lang, debug=debug)
            continue
        result, matched = align_by_content(original_lines, pairs, debug=debug)
        if not result:
            continue
        source = 'KaraokeTexty' if lang == target_lang else 'KaraokeTexty (%s)' % lang.upper()
        if matched == len(original_lines):
            log('KaraokeTexty (%s): 100%% content match (%d/%d)' % (lang, matched, len(original_lines)), debug=debug)
            return result, source, translator, True
        log('KaraokeTexty (%s): %d/%d lines matched, not complete' % (lang, matched, len(original_lines)), debug=debug)
        if matched > best_matched:
            best_lines, best_source, best_translator, best_matched = result, source, translator, matched

    if best_lines:
        return best_lines, best_source, best_translator, False
    return None, None, None, False
