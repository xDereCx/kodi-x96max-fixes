#-*- coding: UTF-8 -*-
'''
Scraper for https://lrclib.net/

lrclib

https://github.com/rtcq/syncedlyrics
'''

import requests
import difflib
import urllib.parse
from lib.utils import *

__title__ = "lrclib"
__priority__ = '110'
__lrc__ = True


class LyricsFetcher:
    def __init__(self, *args, **kwargs):
        self.DEBUG = kwargs['debug']
        self.settings = kwargs['settings']
        self.SEARCH_URL = 'https://lrclib.net/api/search?q=%s-%s'
        self.LYRIC_URL = 'https://lrclib.net/api/get/%i'

    def get_lyrics(self, song):
        log("%s: searching lyrics for %s - %s" % (__title__, song.artist, song.title), debug=self.DEBUG)
        lyrics = Lyrics(settings=self.settings)
        lyrics.song = song
        lyrics.source = __title__
        lyrics.lrc = __lrc__
        try:
            url = self.SEARCH_URL % (urllib.parse.quote(song.artist), urllib.parse.quote(song.title))
            response = requests.get(url, timeout=10)
            result = response.json()
        except:
            return None
        # lrclib.net returns a JSON *object* (e.g. an error/rate-limit
        # response) instead of the expected array of results for some
        # queries (observed for artist/title strings with diacritics) -
        # iterating a dict yields its string keys, so `item['artistName']`
        # below would crash with "string indices must be integers" and
        # silently abort every remaining scraper in the fallback chain.
        if not isinstance(result, list):
            log('%s: unexpected response (not a list), skipping' % __title__, debug=self.DEBUG)
            return None
        links = []
        for item in result:
            if not isinstance(item, dict):
                continue
            artistname = item.get('artistName')
            songtitle = item.get('name')
            songid = item.get('id')
            if not artistname or not songtitle or songid is None:
                continue
            if not ((difflib.SequenceMatcher(None, song.artist.lower(), artistname.lower()).ratio() > 0.8) and (difflib.SequenceMatcher(None, song.title.lower(), songtitle.lower()).ratio() > 0.8)):
                continue
            # a title/artist match can still be the wrong edit (radio edit,
            # remix, extended version, etc.) with different lyric timing,
            # which is a common cause of out-of-sync lyrics; reject
            # candidates whose reported duration is too far from ours
            item_duration = item.get('duration')
            if song.duration and item_duration and abs(item_duration - song.duration) > 3:
                log('%s: skipping duration mismatch for %s - %s (theirs %ss, ours %ss)' % (__title__, artistname, songtitle, item_duration, song.duration), debug=self.DEBUG)
                continue
            links.append((artistname + ' - ' + songtitle, self.LYRIC_URL % songid, artistname, songtitle))
        if len(links) == 0:
            return None
        elif len(links) > 1:
            lyrics.list = links
        for link in links:
            lyr = self.get_lyrics_from_list(link)
            if lyr:
                lyrics.lyrics = lyr
                return lyrics
        return None

    def get_lyrics_from_list(self, link):
        title,url,artist,song = link
        try:
            log('%s: search url: %s' % (__title__, url), debug=self.DEBUG)
            response = requests.get(url, timeout=10)
            result = response.json()
        except:
            return None
        if 'syncedLyrics' in result:
            lyrics = result['syncedLyrics']
            return lyrics
