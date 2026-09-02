import chardet
import json
import os
import re
import sys
import unicodedata
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDONNAME = ADDON.getAddonInfo('name')
ADDONICON = ADDON.getAddonInfo('icon')
ADDONVERSION = ADDON.getAddonInfo('version')
ADDONID = ADDON.getAddonInfo('id')
CWD = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
LANGUAGE = ADDON.getLocalizedString

CANCEL_DIALOG = (9, 10, 92, 216, 247, 257, 275, 61467, 61448,)
ACTION_OSD = (107, 163,)
ACTION_CODEC = (0, 27,)
ACTION_UPDOWN = (3, 4, 105, 106, 111, 112, 603, 604)
LYRIC_SCRAPER_DIR = os.path.join(CWD, 'lib', 'culrcscrapers')
WIN = xbmcgui.Window(10000)

def log(*args, **kwargs):
    if kwargs['debug']:
        message = '%s: %s' % (ADDONID, args[0])
        xbmc.log(msg=message, level=xbmc.LOGDEBUG)

CONFLICTING_ADDON_ID = 'script.cu.lrclyrics'

def disable_conflicting_addon():
    # The original (unfixed) addon and this fork can't both run as the
    # music lyrics service - whichever Kodi picks second silently loses.
    # If the original is installed and enabled, disable it automatically
    # instead of leaving the user to discover and resolve the conflict
    # themselves.
    try:
        req = json.dumps({
            'jsonrpc': '2.0', 'id': 1, 'method': 'Addons.GetAddonDetails',
            'params': {'addonid': CONFLICTING_ADDON_ID, 'properties': ['enabled']}
        })
        resp = json.loads(xbmc.executeJSONRPC(req))
        addon = resp.get('result', {}).get('addon')
        if not addon or not addon.get('enabled'):
            return
        xbmc.executeJSONRPC(json.dumps({
            'jsonrpc': '2.0', 'id': 1, 'method': 'Addons.SetAddonEnabled',
            'params': {'addonid': CONFLICTING_ADDON_ID, 'enabled': False}
        }))
        xbmc.log('%s: disabled conflicting %s (both can\'t run as the lyrics service)' % (ADDONID, CONFLICTING_ADDON_ID), xbmc.LOGINFO)
        xbmcgui.Dialog().notification(
            ADDONNAME, 'Disabled original CU LRC Lyrics (conflicts with this fork)',
            icon=ADDONICON, time=5000, sound=False)
    except Exception as e:
        # most common case: script.cu.lrclyrics simply isn't installed,
        # which GetAddonDetails reports as a JSON-RPC error, not an empty
        # result - nothing to do either way
        xbmc.log('%s: conflicting-addon check skipped: %s' % (ADDONID, e), xbmc.LOGDEBUG)

def deAccent(str):
    return unicodedata.normalize('NFKD', str).replace('"', '')

def get_textfile(filepath):
    try:
        f = xbmcvfs.File(filepath)
        data = f.readBytes()
        f.close()
        # Detect text encoding
        enc = chardet.detect(data)
        if enc['encoding']:
            return data.decode(enc['encoding'])
        else:
            return data
    except:
        return None

def get_artist_from_filename(*args, **kwargs):
    filename = kwargs['filename']
    SETTING_READ_FILENAME_FORMAT = kwargs['opt']['read_filename_format']
    DEBUG = kwargs['opt']['debug']
    try:
        artist = ''
        title = ''
        basename = os.path.basename(filename)
        # Artist - title.ext
        if SETTING_READ_FILENAME_FORMAT == 0:
            artist = basename.split('-', 1)[0].strip()
            title = os.path.splitext(basename.split('-', 1)[1].strip())[0]
        # Artist/Album/title.ext or Artist/Album/Track (-) title.ext
        elif SETTING_READ_FILENAME_FORMAT in (1,2):
            artist = os.path.basename(os.path.split(os.path.split(filename)[0])[0])
            # Artist/Album/title.ext
            if SETTING_READ_FILENAME_FORMAT == 1:
                title = os.path.splitext(basename)[0]
            # Artist/Album/Track (-) title.ext
            elif SETTING_READ_FILENAME_FORMAT == 2:
                title = os.path.splitext(basename)[0].split(' ', 1)[1].lstrip('-').strip()
        # Track Artist - title.ext
        elif SETTING_READ_FILENAME_FORMAT in (3,5):
            at = basename.split(' ', 1)[1].strip()
            artist = at.split('-', 1)[0].strip()
            title = os.path.splitext(at.split('-', 1)[1].strip())[0]
        # Track - Artist - title.ext
        elif SETTING_READ_FILENAME_FORMAT == 4:
            artist = basename.split('-', 2)[1].strip()
            title = os.path.splitext(basename.split('-', 2)[2].strip())[0]
        elif SETTING_READ_FILENAME_FORMAT == 6:
            artist = basename.split('-', 1)[0].strip()
            title = os.path.splitext(basename.split('-', 3)[3].strip())[0]
    except:
        # invalid format selected
        log('failed to get artist and title from filename', debug=DEBUG)
    return artist, title

class Lyrics:
    def __init__(self, *args, **kwargs):
        settings = kwargs['settings']
        self.song = Song(opt=settings)
        self.lyrics = ''
        self.source = ''
        self.list = None
        self.lrc = False

class Song:
    def __init__(self, *args, **kwargs):
        self.artist = ''
        self.title = ''
        self.filepath = ''
        self.embed = ''
        self.source = ''
        self.duration = 0
        self.analyze_safe = True
        self.SETTING_SAVE_FILENAME_FORMAT = kwargs['opt']['save_filename_format']
        self.SETTING_SAVE_LYRICS_PATH = kwargs['opt']['save_lyrics_path']
        self.SETTING_SAVE_SUBFOLDER = kwargs['opt']['save_subfolder']
        self.SETTING_SAVE_SUBFOLDER_PATH = kwargs['opt']['save_subfolder_path']

    def __str__(self):
        return 'Artist: %s, Title: %s' % (self.artist, self.title)

    def __eq__(self, song):
        return (deAccent(self.artist) == deAccent(song.artist)) and (deAccent(self.title) == deAccent(song.title))

    def path1(self, lrc):
        if lrc:
            ext = '.lrc'
        else:
            ext = '.txt'
        # remove invalid filename characters
        artist = "".join(i for i in self.artist if i not in "\/:*?<>|")
        title = "".join(i for i in self.title if i not in "\/:*?<>|")
        if self.SETTING_SAVE_FILENAME_FORMAT == 0:
            return os.path.join(self.SETTING_SAVE_LYRICS_PATH, artist, title + ext)
        else:
            return os.path.join(self.SETTING_SAVE_LYRICS_PATH, artist + ' - ' + title + ext)

    def path2(self, lrc):
        if lrc:
            ext = '.lrc'
        else:
            ext = '.txt'
        dirname = os.path.dirname(self.filepath)
        basename = os.path.basename(self.filepath)
        filename = basename.rsplit('.', 1)[0]
        if self.SETTING_SAVE_SUBFOLDER:
            return os.path.join(dirname, self.SETTING_SAVE_SUBFOLDER_PATH, filename + ext)
        else:
            return os.path.join(dirname, filename + ext)

    @staticmethod
    def current(*args, **kwargs):
        kwargs = kwargs['opt']
        song = Song.by_offset(offset=0, opt=kwargs)
        return song

    @staticmethod
    def next(*args, **kwargs):
        # Disabled: any xbmc.getInfoLabel() call combining '.offset(N)' with
        # a MusicPlayer/Player info label (Title, Artist, Lyrics, Property,
        # Filenameandpath - not just Duration, which was the first one found)
        # can crash this Kodi build with a native SIGSEGV inside
        # CGUIInfoManager::GetMultiInfoLabel. Prefetching the next song's
        # lyrics is a nice-to-have, not essential - lyrics are still fetched
        # reactively once the next track actually starts playing - so this
        # is disabled entirely rather than chasing each individual label.
        return None

    @staticmethod
    def by_offset(*args, **kwargs):
        offset = kwargs['offset']
        SETTING_READ_FILENAME = kwargs['opt']['read_filename']
        SETTING_CLEAN_TITLE = kwargs['opt']['clean_title']
        song = Song(opt=kwargs['opt'])
        # '.offset(N)' combined with almost any MusicPlayer/Player info label
        # can crash this Kodi build with a native SIGSEGV inside
        # CGUIInfoManager::GetMultiInfoLabel (confirmed for Duration, Title,
        # Artist, Lyrics and Property) - by_offset is now only ever called
        # with offset=0 (see Song.next(), disabled for the same reason), so
        # offset_str is always empty, kept only so the info-label names below
        # stay unchanged.
        offset_str = ''
        song.filepath = xbmc.getInfoLabel('Player%s.Filenameandpath' % offset_str)
        song.title = xbmc.getInfoLabel('MusicPlayer%s.Title' % offset_str).replace('\\', ' & ').replace('/', ' & ').replace('  ',' ').replace(':','-').strip('.')
        song.artist = xbmc.getInfoLabel('MusicPlayer%s.Artist' % offset_str).replace('\\', ' & ').replace('/', ' & ').replace('  ',' ').replace(':','-').strip('.')
        song.embed = xbmc.getInfoLabel('MusicPlayer%s.Lyrics' % offset_str)
        song.source = xbmc.getInfoLabel('MusicPlayer%s.Property(culrc.source)' % offset_str)
        # used by scrapers to reject lyrics timed for a different edit/remix
        # of the same title (different duration = different recording).
        duration_label = xbmc.getInfoLabel('MusicPlayer.Duration') if offset == 0 else ''
        parts = duration_label.split(':') if duration_label else []
        try:
            secs = 0
            for p in parts:
                secs = secs * 60 + int(p)
            song.duration = secs
        except ValueError:
            song.duration = 0
        # some third party addons may insert the tracknumber in the song title
        regex = re.compile('\d\d\.\s')
        match = regex.match(song.title)
        if match:
            song.title = song.title[4:]
        if xbmc.getCondVisibility('Player.IsInternetStream') or xbmc.getCondVisibility('Pvr.IsPlayingRadio'):
            # disable search for embedded lyrics for internet streams
            song.analyze_safe = False
        if not song.artist:
            # We probably listen to online radio which usually sets the song title as 'Artist - Title' (via ICY StreamTitle)
            sep = song.title.find('-')
            if sep > 1:
                song.artist = song.title[:sep - 1].strip()
                song.title = song.title[sep + 1:].strip()
                # The title can contains some additional info in brackets at the end, so we remove it
                song.title = re.sub(r'\([^\)]*\)$', '', song.title)
        if (song.filepath and ((not song.title) or (not song.artist) or (SETTING_READ_FILENAME))):
            song.artist, song.title = get_artist_from_filename(filename=song.filepath, opt=kwargs['opt'])
        if SETTING_CLEAN_TITLE:
            song.title = re.sub(r'\([^\)]*\)$', '', song.title)
        return song
