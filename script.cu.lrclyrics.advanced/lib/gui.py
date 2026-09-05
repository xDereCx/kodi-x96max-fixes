#-*- coding: UTF-8 -*-
import threading
import time
from threading import Timer
from lib.utils import *
from lib.embedlrc import *
from lib.translate import strip_lrc_tags, translate_text, translate_lines, looks_like_english
from lib.humantranslate import fetch_human_translation, fetch_human_translation_synced, is_human_source, is_fully_human_source, credit_domain_for_source, human_translation_lang


# rapid-repeat left/right seek acceleration, same idea as Kodi's video OSD
SEEK_STREAK_WINDOW = 1.5
SEEK_STEPS = [10, 30, 60]

# how long the seek progress-bar overlay stays visible after the last
# left/right press before it auto-hides itself, same idea as Kodi's own
# video seek OSD
SEEK_OSD_HOLD = 1.5

# how long the "translation by X, support them at Y" credit stays on
# screen after the last timed lyric line has passed, human sources only
CREDIT_DISPLAY_SECONDS = 25


class _NullTranslationControl(object):
    # stand-in for control 112 (the translation line list) on skins that
    # ship their own native script-cu-lrclyrics-main.xml built before the
    # translation feature existed (e.g. skin.bello.10, skin.confluence) -
    # getControl(112) raises RuntimeError there, which used to crash
    # onInit() immediately and prevent the whole dialog from opening.
    # Translation is simply unavailable on such skins; every call here is
    # a harmless no-op instead of a crash.
    def reset(self):
        pass

    def addItem(self, item):
        pass

    def getListItem(self, i):
        return None

    def size(self):
        return 0

    def selectItem(self, i):
        pass


class MAIN():
    def __init__(self):
        WIN.setProperty('culrc.running', 'true')
        self.get_settings()
        log('started as service: %s' % str(self.SETTING_SERVICE), debug=self.DEBUG)
        self.setup_main()
        self.main_loop()
        self.cleanup_main()

    def setup_main(self):
        self.fetchedLyrics = []
        self.current_lyrics = Lyrics(settings=self.lyricssettings)
        self.MyPlayer = MyPlayer(function=self.myPlayerChanged, clear=self.clear)
        self.Monitor = MyMonitor(function=self.update_settings)
        self.dialog = xbmcgui.Dialog()
        self.customtimer = False
        self.starttime = 0
        self.CULRC_QUIT = False
        self.CULRC_FIRSTRUN = False
        self.CULRC_NEWLYRICS = False
        self.CULRC_NOLYRICS = False

    def cleanup_main(self):
        # Clean up the monitor and Player classes on exit
        del self.MyPlayer
        del self.Monitor

    def get_settings(self):
        self.DEBUG = ADDON.getSettingBool('log_enabled')
        self.SETTING_OFFSET = ADDON.getSettingNumber('offset')
        self.SETTING_SAVE_LYRICS1LRC = ADDON.getSettingBool('save_lyrics1_lrc')
        self.SETTING_SAVE_LYRICS1TXT = ADDON.getSettingBool('save_lyrics1_txt')
        self.SETTING_SAVE_LYRICS2LRC = ADDON.getSettingBool('save_lyrics2_lrc')
        self.SETTING_SAVE_LYRICS2TXT = ADDON.getSettingBool('save_lyrics2_txt')
        self.SETTING_SEARCH_EMBEDDED = ADDON.getSettingBool('search_embedded')
        self.SETTING_SEARCH_LRC_FILE = ADDON.getSettingBool('search_lrc_file')
        self.SETTING_SEARCH_TXT_FILE = ADDON.getSettingBool('search_txt_file')
        self.SETTING_SERVICE = ADDON.getSettingBool('service')
        self.SETTING_SILENT = ADDON.getSettingBool('silent')
        self.SETTING_STRIP = ADDON.getSettingBool('strip')
        self.SETTING_READ_FILENAME = ADDON.getSettingBool('read_filename')
        self.SETTING_READ_FILENAME_FORMAT = ADDON.getSettingInt('read_filename_format')
        self.SETTING_SAVE_FILENAME_FORMAT = ADDON.getSettingInt('save_filename_format')
        self.SETTING_SAVE_LYRICS_PATH = ADDON.getSettingString('save_lyrics_path')
        self.SETTING_SAVE_SUBFOLDER = ADDON.getSettingBool('save_subfolder')
        self.SETTING_SAVE_SUBFOLDER_PATH = ADDON.getSettingString('save_subfolder_path')
        self.SETTING_CLEAN_TITLE = ADDON.getSettingBool('clean_title')
        self.SETTING_INTERNETRADIO = ADDON.getSettingBool('internetradio')
        self.SETTING_TRANSLATE = ADDON.getSettingBool('translate_enabled')
        # translation target language now follows the single addon_language
        # choice (also drives this addon's own menus/notifications, see
        # lib/localization.py) instead of its own separate free-text
        # setting - one language choice for the whole addon
        self.SETTING_TRANSLATE_LANG = current_interface_language()
        # a malformed empty <default></default> in settings.xml (fixed, but
        # a stale/partially-regenerated addon_data/settings.xml on an
        # existing install could still be missing this key) made Kodi throw
        # TypeError: Invalid setting type instead of returning '' - this
        # crashed MAIN.__init__() entirely, taking down lyrics display along
        # with translation, confirmed live. Never let a single missing/bad
        # setting take down the whole service again.
        try:
            self.SETTING_DEEPL_KEY = ADDON.getSettingString('deepl_api_key')
        except TypeError:
            self.SETTING_DEEPL_KEY = ''
        try:
            self.SETTING_LINGVA_INSTANCE = ADDON.getSettingString('lingva_instance') or 'lingva.ml'
        except TypeError:
            self.SETTING_LINGVA_INSTANCE = 'lingva.ml'
        self.lyricssettings = {}
        self.lyricssettings['debug'] = self.DEBUG
        self.lyricssettings['read_filename'] = self.SETTING_READ_FILENAME
        self.lyricssettings['read_filename_format'] = self.SETTING_READ_FILENAME_FORMAT
        self.lyricssettings['save_filename_format'] = self.SETTING_SAVE_FILENAME_FORMAT
        self.lyricssettings['save_lyrics_path'] = self.SETTING_SAVE_LYRICS_PATH
        self.lyricssettings['save_subfolder'] = self.SETTING_SAVE_SUBFOLDER
        self.lyricssettings['save_subfolder_path'] = self.SETTING_SAVE_SUBFOLDER_PATH
        self.lyricssettings['clean_title'] = self.SETTING_CLEAN_TITLE
        self.scrapers = []
        for scraper in os.listdir(LYRIC_SCRAPER_DIR):
            # meh to python3 creating folders
            if os.path.isdir(os.path.join(LYRIC_SCRAPER_DIR, scraper)) and scraper != '__pycache__' and ADDON.getSettingBool(scraper):
                exec ('from lib.culrcscrapers.%s import lyricsScraper as lyricsScraper_%s' % (scraper, scraper), globals())
                exec ('self.scrapers.append([lyricsScraper_%s.__priority__,lyricsScraper_%s.LyricsFetcher(debug=self.DEBUG, settings=self.lyricssettings),lyricsScraper_%s.__title__,lyricsScraper_%s.__lrc__])' \
                     % (scraper, scraper, scraper, scraper))
        self.scrapers.sort()
        if (ADDON.getSettingString('save_lyrics_path') == ''):
            ADDON.setSettingString(id='save_lyrics_path', value=os.path.join(PROFILE, 'lyrics'))
        if ADDON.getSettingBool('hide_dialog'):
            WIN.setProperty('culrc.hidedialog', 'True')
        else:
            WIN.clearProperty('culrc.hidedialog')

    def main_loop(self):
        # main loop
        while (not self.Monitor.abortRequested()) and (not self.CULRC_QUIT):
            # check if we are on the music visualization screen
            # do not try and get lyrics for any background media
            if self.proceed():
                if not self.CULRC_FIRSTRUN:
                    # only the first lyrics are fetched by main_loop, the rest is done through onAVStarted. this makes sure both don't run simultaniously
                    self.CULRC_FIRSTRUN = True
                    # notify user the script is searching for lyrics
                    if not self.SETTING_SILENT:
                        self.dialog.notification(ADDONNAME, LANGUAGE(32004), icon=ADDONICON, time=2000, sound=False)
                    # start fetching lyrics
                    self.myPlayerChanged()
                elif WIN.getProperty('culrc.force') == 'TRUE':
                    # we're already running, user clicked button on osd
                    WIN.setProperty('culrc.force','FALSE')
                    self.current_lyrics = Lyrics(settings=self.lyricssettings)
                    self.myPlayerChanged()
                # internetstreams may (like spotify) or may not (like many internet radio stations) generate onAVStarted callbacks to indicate a new song has started.
                # TODO: no idea how to differentiate between those automatically.
                # for now, add a setting for internet radio, which will cause issues with spotify and the likes.
                elif xbmc.getCondVisibility('Player.IsInternetStream') and self.SETTING_INTERNETRADIO:
                    self.myPlayerChanged()
            else:
                # we may have exited the music visualization screen, reset current lyrics so we show them again when re-entering the visualization screen
                if self.CULRC_FIRSTRUN:
                    self.current_lyrics = Lyrics(settings=self.lyricssettings)
                self.CULRC_FIRSTRUN = False
            xbmc.sleep(100)
        WIN.clearProperty('culrc.lyrics')
        WIN.clearProperty('culrc.islrc')
        WIN.clearProperty('culrc.source')
        WIN.clearProperty('culrc.haslist')
        WIN.clearProperty('culrc.running')
        WIN.clearProperty('culrc.hidedialog')
        WIN.clearProperty('culrc.translation')

    def get_lyrics(self, song, prefetch):
        log('searching memory for lyrics', debug=self.DEBUG)
        lyrics = self.get_lyrics_from_memory(song)
        if lyrics:
            if lyrics.lyrics:
                log('found lyrics in memory', debug=self.DEBUG)
            else:
                log('no lyrics found on previous search', debug=self.DEBUG)
            return lyrics
        # searching lyrics for the current song and no pre-fetched lyrics available, hide the gui
        if not prefetch:
            self.CULRC_NOLYRICS = True
        if song.title and self.proceed():
            lyrics = self.find_lyrics(song)
            if lyrics.lyrics and self.SETTING_STRIP:
                # replace CJK and fullwith colon (not present in many font files)
                lyrics.lyrics = re.sub(r'[ᄀ-ᇿ⺀-⺙⺛-⻳⼀-⿕々〇〡-〩〸-〺〻㐀-䶵一-鿃豈-鶴侮-頻並-龎]+', '', lyrics.lyrics).replace('：',':') 
        # no song title, we can't search online. try matching local filename
        elif (self.SETTING_SAVE_LYRICS2LRC or self.SETTING_SAVE_LYRICS2TXT) and self.proceed():
            lyrics = self.get_lyrics_from_file(song, True)
            if not lyrics:
                lyrics = self.get_lyrics_from_file(song, False)
        if not lyrics:
            lyrics = Lyrics(settings=self.lyricssettings)
            lyrics.song = song
            lyrics.source = ''
            lyrics.lyrics = ''
        if self.proceed():
            self.save_lyrics_to_memory(lyrics)
        return lyrics

    def find_lyrics(self, song):
        # search embedded lrc lyrics
        if self.SETTING_SEARCH_EMBEDDED and self.proceed(): # Add embedded lyrics for internet streams
            log('searching for embedded lrc lyrics', debug=self.DEBUG)
            try:
                lyrics = getEmbedLyrics(song, True, self.lyricssettings)
            except:
                lyrics = None
            if (lyrics):
                log('found embedded lrc lyrics', debug=self.DEBUG)
                return lyrics
        # search lrc lyrics from file
        if self.SETTING_SEARCH_LRC_FILE and self.proceed():
            log('searching for local lrc files', debug=self.DEBUG)
            lyrics = self.get_lyrics_from_file(song, True)
            if (lyrics):
                log('found lrc lyrics from file', debug=self.DEBUG)
                return lyrics
        # search lrc lyrics by scrapers
        for scraper in self.scrapers:
            if scraper[3] and self.proceed():
                try:
                    lyrics = scraper[1].get_lyrics(song)
                except Exception as e:
                    # a single scraper raising (bad API response shape,
                    # site layout change, etc.) must not abort every
                    # remaining scraper in the fallback chain - log and
                    # move on to the next one instead.
                    log('scraper error (%s), skipping: %s' % (scraper[0], e), debug=self.DEBUG)
                    lyrics = None
                if (lyrics):
                    log('found lrc lyrics online', debug=self.DEBUG)
                    self.save_lyrics_to_file(lyrics)
                    return lyrics
        # search embedded txt lyrics
        if self.SETTING_SEARCH_EMBEDDED and self.proceed(): # Add embedded lyrics for internet streams
            log('searching for embedded txt lyrics', debug=self.DEBUG)
            try:
                lyrics = getEmbedLyrics(song, False, self.lyricssettings)
            except:
                lyrics = None
            if lyrics:
                log('found embedded txt lyrics', debug=self.DEBUG)
                return lyrics
        # search txt lyrics from file
        if self.SETTING_SEARCH_TXT_FILE and self.proceed():
            log('searching for local txt files', debug=self.DEBUG)
            lyrics = self.get_lyrics_from_file(song, False)
            if (lyrics):
                log('found txt lyrics from file', debug=self.DEBUG)
                return lyrics
        # search txt lyrics by scrapers
        for scraper in self.scrapers:
            if not scraper[3] and self.proceed():
                try:
                    lyrics = scraper[1].get_lyrics(song)
                except Exception as e:
                    log('scraper error (%s), skipping: %s' % (scraper[0], e), debug=self.DEBUG)
                    lyrics = None
                if (lyrics):
                    log('found txt lyrics online', debug=self.DEBUG)
                    self.save_lyrics_to_file(lyrics)
                    return lyrics
        log('no lyrics found', debug=self.DEBUG)
        lyrics = Lyrics(settings=self.lyricssettings)
        lyrics.song = song
        lyrics.source = ''
        lyrics.lyrics = ''
        return lyrics

    def get_lyrics_from_memory(self, song):
        for l in self.fetchedLyrics:
            if (l.song == song):
                return l
        return None

    def get_lyrics_from_file(self, song, getlrc):
        lyrics = Lyrics(settings=self.lyricssettings)
        lyrics.song = song
        lyrics.source = LANGUAGE(32000)
        lyrics.lrc = getlrc
        if self.SETTING_SAVE_LYRICS1LRC or self.SETTING_SAVE_LYRICS1TXT:
            # Search save path by Cu LRC Lyrics
            lyricsfile = song.path1(getlrc)
            log('path1: %s' % lyricsfile, debug=self.DEBUG)
            if xbmcvfs.exists(lyricsfile):
                lyr = get_textfile(lyricsfile)
                if lyr != None:
                    lyrics.lyrics = lyr
                    return lyrics
        if self.SETTING_SAVE_LYRICS2LRC or self.SETTING_SAVE_LYRICS2TXT:
            # Search same path with song file
            lyricsfile = song.path2(getlrc)
            log('path2: %s' % lyricsfile, debug=self.DEBUG)
            # don't search online sources for saved lyrics files
            if xbmc.getCondVisibility('Player.IsInternetStream') or xbmc.getCondVisibility('Pvr.IsPlayingRadio'):
                return None
            if xbmcvfs.exists(lyricsfile):
                lyr = get_textfile(lyricsfile)
                if lyr != None:
                    lyrics.lyrics = lyr
                    return lyrics
        return None

    def save_lyrics_to_memory(self, lyrics):
        savedLyrics = self.get_lyrics_from_memory(lyrics.song)
        if (savedLyrics is None):
            self.fetchedLyrics.append(lyrics)
            self.fetchedLyrics = self.fetchedLyrics[-10:]

    def save_lyrics_to_file(self, lyrics, adjust=None):
        if isinstance (lyrics.lyrics, str):
            lyr = lyrics.lyrics
        else:
            lyr = lyrics.lyrics
        if adjust is not None:
            # the slider (and parser_lyrics, which now seeds self.syncadjust
            # from this same tag) always deals in absolute offset values, not
            # deltas - so the incoming adjust here already IS the final
            # value to persist, not something to add on top of what's
            # already in the file
            adjust = int(adjust * 1000)
            found = re.search(r'\[offset:(.*?)\]', lyr, flags=re.DOTALL)
            if found:
                lyr = lyr.replace(found.group(0) + '\n','')
            lyr = '[offset:%i]\n' % adjust + lyr
            # also update the in-memory copy, not just the file - if this
            # exact object is still sitting in MAIN's fetchedLyrics cache
            # when the OK/OSD reopen re-shows this song (very common,
            # since remove_lyrics_from_memory() below isn't guaranteed to
            # win the race against that reopen), a stale copy without the
            # offset tag would make parser_lyrics() re-derive offset=0
            # and silently undo the adjustment
            lyrics.lyrics = lyr
        if (self.SETTING_SAVE_LYRICS1LRC and lyrics.lrc) or (self.SETTING_SAVE_LYRICS1TXT and not lyrics.lrc):
            file_path = lyrics.song.path1(lyrics.lrc)
            success = self.write_lyrics_file(file_path, lyr)
        if (self.SETTING_SAVE_LYRICS2LRC and lyrics.lrc) or (self.SETTING_SAVE_LYRICS2TXT and not lyrics.lrc):
            file_path = lyrics.song.path2(lyrics.lrc)
            success = self.write_lyrics_file(file_path, lyr)

    def write_lyrics_file(self, path, data):
        try:
            if (not xbmcvfs.exists(os.path.dirname(path))):
                xbmcvfs.mkdirs(os.path.dirname(path))
            lyrics_file = xbmcvfs.File(path, 'w')
            lyrics_file.write(data)
            lyrics_file.close()
            return True
        except:
            log('failed to save lyrics', debug=self.DEBUG)
            return False

    def remove_lyrics_from_memory(self, lyrics):
        # delete lyrics from memory
        if lyrics in self.fetchedLyrics:
            self.fetchedLyrics.remove(lyrics)

    def delete_lyrics(self, lyrics):
        # delete lyrics from memory
        self.remove_lyrics_from_memory(lyrics)
        # delete saved lyrics
        if (self.SETTING_SAVE_LYRICS1LRC and lyrics.lrc) or (self.SETTING_SAVE_LYRICS1LRC and not lyrics.lrc):
            file_path = lyrics.song.path1(lyrics.lrc)
            success = self.delete_file(file_path)
        if (self.SETTING_SAVE_LYRICS2LRC and lyrics.lrc) or (self.SETTING_SAVE_LYRICS2LRC and not lyrics.lrc):
            file_path = lyrics.song.path2(lyrics.lrc)
            success = self.delete_file(file_path)

    def delete_file(self, path):
        try:
            xbmcvfs.delete(path)
            return True
        except:
            log('failed to delete file', debug=self.DEBUG)
            return False

    def myPlayerChanged(self, force=False):
        if not self.CULRC_FIRSTRUN:
            return
        global lyrics
        songchanged = False
        for cnt in range(5):
            song = Song.current(opt=self.lyricssettings)
            # force=True means this call came from onAVStarted - a new
            # playback stream genuinely just started, even if it's the
            # exact same track as before (e.g. repeat-one, or a short
            # playlist looping back to it). Song.__eq__ only compares
            # artist/title, so without this a same-song repeat would look
            # identical to "nothing changed" and silently skip re-showing
            # lyrics/translation entirely - confirmed live.
            if song and (force or self.current_lyrics.song != song):
                songchanged = True
                # clear the previous song's lyrics from the screen right away -
                # get_lyrics() below can take a few seconds (scraper lookups),
                # and until now the old lyrics stayed visible the whole time
                # since the WIN properties were only overwritten once the new
                # lyrics were actually found.
                self.clear()
                if xbmc.getCondVisibility('Player.IsInternetStream') and not xbmc.getInfoLabel('MusicPlayer.TimeRemaining'):
                    # internet stream that does not provide time, we need our own timer to sync lrc lyrics
                    self.starttime = time.time()
                    self.customtimer = True
                else:
                    self.customtimer = False
                log('Current Song: %s - %s' % (song.artist, song.title), debug=self.DEBUG)
                lyrics = self.get_lyrics(song, False)
                self.current_lyrics = lyrics
                # if we have found lyrics and have not skipped to another track while searching for lyrics, show lyrics
                if lyrics.lyrics and (song == Song.current(opt=self.lyricssettings)):
                    # signal the gui thread to display the next lyrics
                    self.CULRC_NOLYRICS = False
                    self.CULRC_NEWLYRICS = True
                    # double-check if we're still on the visualisation screen and check if gui is already running.
                    # A fast local .lrc lookup can finish before the PREVIOUS
                    # song's guiThread has cleared this flag (it only clears
                    # it after its doModal() call returns, slightly after the
                    # skin's own Window Deinit) - wait briefly for that
                    # instead of silently giving up, which used to skip
                    # showing lyrics/translation entirely for fast lookups.
                    if self.proceed():
                        for _ in range(20):
                            if WIN.getProperty('culrc.guirunning') != 'TRUE':
                                break
                            xbmc.sleep(100)
                    if self.proceed() and not WIN.getProperty('culrc.guirunning') == 'TRUE':
                        WIN.setProperty('culrc.guirunning', 'TRUE')
                        self.kwargs = {'service':self.SETTING_SERVICE, 'save':self.save_lyrics_to_file, 'remove':self.remove_lyrics_from_memory, 'delete':self.delete_lyrics, \
                                       'function':self.return_time, 'callback':self.callback, 'monitor':self.Monitor, 'offset':self.SETTING_OFFSET, 'strip':self.SETTING_STRIP, \
                                       'debug':self.DEBUG, 'settings':self.lyricssettings, 'translate':self.SETTING_TRANSLATE, \
                                       'translate_lang':self.SETTING_TRANSLATE_LANG, 'deepl_key':self.SETTING_DEEPL_KEY, \
                                       'lingva_instance':self.SETTING_LINGVA_INSTANCE, \
                                       'save_lyrics2':(self.SETTING_SAVE_LYRICS2LRC or self.SETTING_SAVE_LYRICS2TXT), \
                                       'song_restarted':force}
                        gui = guiThread(opt=self.kwargs)
                        gui.start()
                else:
                    # signal gui thread to exit
                    self.CULRC_NOLYRICS = True
                    if self.MyPlayer.isPlayingAudio() and not self.SETTING_SILENT and self.proceed():
                        # notify user no lyrics were found
                        self.dialog.notification(ADDONNAME + ': ' + LANGUAGE(32001), song.artist + ' - ' + song.title, icon=ADDONICON, time=2000, sound=False)
                break
            xbmc.sleep(50)
        # only search for next lyrics if current song has changed and we have not skipped to another track while searching for lyrics
        if xbmc.getCondVisibility('MusicPlayer.HasNext') and songchanged and (song == Song.current(opt=self.lyricssettings)):
            next_song = Song.next(opt=self.lyricssettings)
            if next_song:
                log('Next Song: %s - %s' % (next_song.artist, next_song.title), debug=self.DEBUG)
                self.get_lyrics(next_song, True)
            else:
                log('Missing Artist or Song name for next track', debug=self.DEBUG)

    def update_settings(self):
        self.get_settings()
        if not self.SETTING_SERVICE:
            # quit the script if mode was changed from service to manual
            self.CULRC_QUIT = True
        # Kodi's Monitor.onSettingsChanged fires for ANY settings change,
        # not just this addon's own - including Settings > Interface > Skin,
        # which is how a live skin switch is caught here. Without this, the
        # decorative-font auto-install (also run once at every service
        # start in default.py) would only ever notice a newly-switched-to
        # skin the next time Kodi happened to restart, not right when the
        # user actually switched to it.
        from lib import fontinstall
        installed, result = fontinstall.auto_install_if_needed()
        if installed:
            xbmcgui.Dialog().notification(ADDONNAME, LANGUAGE(32921), icon=ADDONICON, time=6000, sound=False)

    def callback(self, action):
        if action == 'quit':
            self.CULRC_QUIT = True
        elif action == 'newlyrics':
            if self.CULRC_NEWLYRICS:
                self.CULRC_NEWLYRICS = False
                return True
            return False
        elif action == 'nolyrics':
            return self.CULRC_NOLYRICS

    def proceed(self):
        return xbmc.getCondVisibility('Window.IsVisible(12006)') and not self.Monitor.abortRequested()

    def clear(self):
        WIN.clearProperty('culrc.lyrics')
        WIN.clearProperty('culrc.islrc')
        WIN.clearProperty('culrc.source')
        WIN.clearProperty('culrc.haslist')
        # deliberately NOT clearing culrc.translation(.source/.song) here -
        # the OK/OSD reopen trick calls this same clear() by resetting
        # current_lyrics to force myPlayerChanged() to treat the SAME song
        # as "changed", which would wipe the translation state before the
        # new GUI instance's _maybe_restore_translation() ever gets to
        # check it. The GUI's reset_controls() does the real
        # same-song-vs-different-song comparison and clears it there
        # instead, once it actually knows which song is being shown.

    def return_time(self):
        return self.customtimer, self.starttime


class guiThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        threading.Thread.__init__(self)
        self.kwargs = kwargs['opt']

    def run(self):
        # a fork-specific filename, not the classic "script-cu-lrclyrics-main.xml"
        # every upstream-styled skin (Confluence, Bello 10, etc.) already ships
        # its own native override of - Kodi's WindowXMLDialog prefers a skin's
        # own file over the addon's bundled one whenever the names match, so
        # those skins were silently hijacking this dialog with their old,
        # pre-fork layout (no control 112 for translation - confirmed live via
        # kodi.log: "RuntimeError: Non-Existent Control 112" under skin.bello.10).
        # A name no other skin's override matches means Kodi always falls
        # through to this addon's own bundled file, on every skin.
        ui = GUI('script-cu-lrclyrics-advanced-main.xml', CWD, 'Default', '1080i', opt=self.kwargs)
        ui.doModal()
        del ui
        WIN.clearProperty('culrc.guirunning')


class syncThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        threading.Thread.__init__(self)
        self.function = kwargs['function']
        self.adjust = kwargs['adjust']
        self.save = kwargs['save']
        self.remove = kwargs['remove']
        self.lyrics = kwargs['lyrics']
        self.Monitor = kwargs['monitor']

    def run(self):
        from lib import sync
        # dedicated window instead of the skin's shared DialogSlider.xml
        # (used for volume/seek/brightness too) - keeps our wider layout
        # from affecting anything else in Kodi
        dialog = sync.GUI('script-cu-lrclyrics-sync.xml' , CWD, 'Default', '1080i', offset=self.adjust, function=self.function, monitor=self.Monitor)
        dialog.doModal()
        adjust = dialog.val
        del dialog
        # safe new offset to file
        self.save(self.lyrics, adjust)
        # file has changed, remove it from memory
        self.remove(self.lyrics)

class GUI(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        xbmcgui.WindowXMLDialog.__init__(self)
        self.save = kwargs['opt']['save']
        self.remove = kwargs['opt']['remove']
        self.delete = kwargs['opt']['delete']
        self.function = kwargs['opt']['function']
        self.callback = kwargs['opt']['callback']
        self.Monitor = kwargs['opt']['monitor']
        self.SETTING_OFFSET = kwargs['opt']['offset']
        self.SETTING_SERVICE = kwargs['opt']['service']
        self.SETTING_STRIP = kwargs['opt']['strip']
        self.DEBUG = kwargs['opt']['debug']
        self.lyricssettings = kwargs['opt']['settings']
        self.SETTING_TRANSLATE = kwargs['opt']['translate']
        self.TRANSLATE_LANG = kwargs['opt']['translate_lang']
        self.DEEPL_KEY = kwargs['opt']['deepl_key']
        self.LINGVA_INSTANCE = kwargs['opt']['lingva_instance']
        self.SAVE_LYRICS2 = kwargs['opt']['save_lyrics2']
        # True only when this GUI instance exists because onAVStarted just
        # fired (a new playback stream genuinely started, even if it's the
        # exact same track repeating) - False for the OK/OSD "force" reopen
        # of a still-playing song, which deliberately wants translation
        # state preserved instead of reset. See reset_controls().
        self.SONG_RESTARTED = kwargs['opt']['song_restarted']
        self.dialog = xbmcgui.Dialog()
        # set here, not just in setup_gui() (which runs inside onInit()) - a
        # Back/menu press that reaches onAction before onInit() finishes
        # calls exit_gui(), which reads these; without this they don't exist
        # yet, exit_gui() crashes, the window never closes, and every
        # further Back repeats the same crash (confirmed live: only OK
        # worked, Back did nothing, kodi.log showed the same AttributeError
        # looping on every keypress).
        self._seek_hide_timer = None
        self._credit_hide_timer = None

    def onInit(self):
        self.matchlist = ['@', r'www\.(.*?)\.(.*?)', 'QQ(.*?)[1-9]', 'artist ?: ?.', 'album ?: ?.', 'title ?: ?.', 'song ?: ?.', 'by ?: ?.']
        self.text = self.getControl(110)
        self.label = self.getControl(200)
        try:
            self.text2 = self.getControl(112)
        except RuntimeError:
            self.text2 = _NullTranslationControl()
        self.setup_gui()
        self.process_lyrics()
        # we have processed the lyrics, reset the new lyrics bool, else we do it again when entering the main loop
        self.callback('newlyrics')
        self.gui_loop()

    def process_lyrics(self):
        global lyrics
        # default for the no-lyrics-found case below; parser_lyrics()
        # overrides this from the file's own [offset:N] tag whenever
        # there actually are timed lyrics to show
        self.syncadjust = 0.0
        self.selectedlyric = 0
        self.lyrics = lyrics
        self.stop_refresh()
        self.reset_controls()
        if self.lyrics.lyrics:
            self.show_lyrics(self.lyrics)
            self._maybe_restore_translation()
        else:
            WIN.setProperty('culrc.lyrics', LANGUAGE(32001))
            WIN.clearProperty('culrc.islrc')

        if self.lyrics.list:
            WIN.setProperty('culrc.haslist', 'true')
            self.prepare_list(self.lyrics.list)
        else:
            WIN.clearProperty('culrc.haslist')
            self.choices = []

    def gui_loop(self):
        # gui loop
        while self.showgui and (not self.Monitor.abortRequested()) and xbmc.Player().isPlayingAudio():
            # check if we have new lyrics
            if self.callback('newlyrics'):
                # show new lyrics
                self.process_lyrics()
            # check if we have no lyrics
            elif self.deleted or self.callback('nolyrics'):
                # no lyrics, close the gui
                self.exit_gui('close')
            elif not xbmc.getCondVisibility('Window.IsVisible(12006)'):
                # we're not on the visualisation screen anymore
                self.exit_gui('quit')
            xbmc.sleep(100)
        # music ended, close the gui
        if (not xbmc.Player().isPlayingAudio()):
            self.exit_gui('quit')
        # xbmc quits, close the gui 
        elif self.Monitor.abortRequested():
            self.exit_gui('quit')

    def setup_gui(self):
        WIN.clearProperty('culrc.haslist')
#        self.lock = threading.Lock()
        self.timer = None
        self.allowtimer = True
        self.refreshing = False
        self.blockOSD = False
        self.controlId = -1
        self.pOverlay = []
        self.choices = []
        self.scroll_line = int(self.get_page_lines() / 2)
        self.showgui = True
        self.deleted = False
        self.sync_dialog = None
        self.translation_synced = False
        self._seek_last_press_time = 0
        self._seek_last_action = None
        self._seek_streak = 0
        self._seek_hide_timer = None
        self._credit_hide_timer = None
        self._credit_shown_for_song = False

    def get_page_lines(self):
        # we need to close the OSD else we can't get control 110
        self.blockOSD = True
        if xbmc.getCondVisibility('Window.IsVisible(musicosd)'):
            xbmc.executebuiltin('Dialog.Close(musicosd,true)')
        self.text.setVisible(False)
        # numpages returns a string, make sure it's not empty
        while xbmc.getInfoLabel('Container(110).NumPages') and (int(xbmc.getInfoLabel('Container(110).NumPages')) < 2) and (not self.Monitor.abortRequested()):
            listitem = xbmcgui.ListItem(offscreen=True)
            self.text.addItem(listitem)
            xbmc.sleep(5)
        # xbmc quits, close the gui 
        if self.Monitor.abortRequested():
            self.exit_gui('quit')
        lines = self.text.size() - 1
        self.blockOSD = False
        return lines

    def refresh(self):
#        self.lock.acquire()
        #Maybe Kodi is not playing any media file
        try:
            customtimer, starttime = self.function()
            if customtimer:
                cur_time = time.time() - starttime
            else:
                cur_time = xbmc.Player().getTime()
            nums = self.text.size()
            pos = self.text.getSelectedPosition()
            if (cur_time < (self.pOverlay[pos][0] - self.syncadjust)):
                while (pos > 0 and (self.pOverlay[pos - 1][0] - self.syncadjust) > cur_time):
                    pos = pos -1
            else:
                while (pos < nums - 1 and (self.pOverlay[pos + 1][0] - self.syncadjust) < cur_time):
                    pos = pos +1
                if (pos + self.scroll_line > nums - 1):
                    self.text.selectItem(nums - 1)
                else:
                    self.text.selectItem(pos + self.scroll_line)
            self.text.selectItem(pos)
            if self.translation_synced:
                # translated lines are 1:1 with self.pOverlay (built from
                # the exact same list, see show_translation), so the same
                # index is always the right one - no separate search needed
                self._select_translation_line(pos)
            # self.setFocus(self.text)  # disabled: focus-steal fix
            if (self.allowtimer and cur_time < (self.pOverlay[nums - 1][0] - self.syncadjust)):
                waittime = (self.pOverlay[pos + 1][0] - self.syncadjust) - cur_time
                self.timer = Timer(waittime, self.refresh)
                self.refreshing = True
                self.timer.start()
            else:
                self.refreshing = False
                self._maybe_show_translation_credit()
#            self.lock.release()
        except:
            pass
#            self.lock.release()

    def stop_refresh(self):
#        self.lock.acquire()
        try:
            self.timer.cancel()
        except:
            pass
        self.refreshing = False
#        self.lock.release()

    def show_lyrics(self, lyrics):
        WIN.setProperty('culrc.lyrics', lyrics.lyrics)
        WIN.setProperty('culrc.source', lyrics.source)
        if lyrics.list:
            source = '%s (%d)' % (lyrics.source, len(lyrics.list))
        else:
            source = lyrics.source
        self.label.setLabel(source)
        if lyrics.lrc:
            WIN.setProperty('culrc.islrc', 'true')
            # sync is only meaningful for timed (lrc) lyrics, and a
            # first-time user has no way to know up/down does anything at
            # all here - a quick corner popup tells them once. Only once
            # per Kodi session (not per song, not on every OK/OSD reopen,
            # which also creates a fresh GUI instance) - WIN properties
            # reset naturally on the next real Kodi restart
            if not WIN.getProperty('culrc.synctip.shown'):
                xbmcgui.Dialog().notification(ADDONNAME, LANGUAGE(32012), icon=ADDONICON, time=3000, sound=False)
                WIN.setProperty('culrc.synctip.shown', 'true')
            self.parser_lyrics(lyrics.lyrics)
            for num, (time, line) in enumerate(self.pOverlay):
                cleanline = line.strip()
                parts = self.get_parts(cleanline)
                listitem = xbmcgui.ListItem(cleanline, offscreen=True)
                for count, item in enumerate(parts):
                    listitem.setProperty('part%i' % (count + 1), item)
                delta = 100000 # in case duration of the last line is undefined
                if num < len(self.pOverlay) - 1:
                    delta = (self.pOverlay[num+1][0] - time) * 1000
                listitem.setProperty('duration', str(int(delta)))
                listitem.setProperty('time', str(time))
                self.text.addItem(listitem)
        else:
            WIN.clearProperty('culrc.islrc')
            splitLyrics = lyrics.lyrics.splitlines()
            for line in splitLyrics:
                cleanline = line.strip()
                parts = self.get_parts(cleanline)
                listitem = xbmcgui.ListItem(cleanline, offscreen=True)
                for count, item in enumerate(parts):
                    listitem.setProperty('part%i' % (count + 1), item)
                self.text.addItem(listitem)
        self.text.selectItem(0)
        self.text.setVisible(True)
        xbmc.sleep(5)
        # self.setFocus(self.text)  # disabled: focus-steal fix
        if lyrics.lrc:
            if (self.allowtimer and self.text.size() > 1):
                self.refresh()

    def match_pattern(self, line):
        for item in self.matchlist:
            match = re.search(item, line, flags=re.IGNORECASE)
            if match:
                return True

    def get_parts(self, line):
        result = ['', '', '', '']
        parts = line.split(' ', 3)
        for count, item in enumerate(parts):
            result[count] = item
        return result

    def parser_lyrics(self, lyrics):
        found = re.search(r'\[offset:\s?(-?\d+)\]', lyrics)
        # self.syncadjust is the one source of truth for the current
        # offset (used live by refresh() and shown as the slider's
        # starting position) - previously this file-tag value was instead
        # baked directly into each line's time below, while self.syncadjust
        # got hard-reset to 0.0 in process_lyrics() for every new GUI
        # instance (including the OK/OSD reopen of the same song), so the
        # slider always looked reset even though the tag was still applied
        # via a *different* code path. Single source now avoids that split.
        self.syncadjust = float(found.group(1)) / 1000 if found else 0.0
        self.pOverlay = []
        tag1 = re.compile(r'\[(\d+):(\d\d)[\.:](\d\d)\]')
        tag2 = re.compile(r'\[(\d+):(\d\d)([\.:]\d+|)\]')
        lyrics = lyrics.replace('\r\n' , '\n')
        sep = '\n'
        for x in lyrics.split(sep):
            if self.match_pattern(x):
                continue
            match1 = tag1.match(x)
            match2 = tag2.match(x)
            times = []
            if (match1):
                while (match1): # [xx:yy.zz]
                    times.append(float(match1.group(1)) * 60 + float(match1.group(2)) + (float(match1.group(3))/100) + self.SETTING_OFFSET)
                    y = 6 + len(match1.group(1)) + len(match1.group(3))
                    x = x[y:]
                    match1 = tag1.match(x)
                for time in times:
                    self.pOverlay.append((time, x))
            elif (match2): # [xx:yy]
                while (match2):
                    times.append(float(match2.group(1)) * 60 + float(match2.group(2)) + self.SETTING_OFFSET)
                    y = 5 + len(match2.group(1)) + len(match2.group(3))
                    x = x[y:]
                    match2 = tag2.match(x)
                for time in times:
                    self.pOverlay.append((time, x))
        self.pOverlay.sort()
        # don't display/focus the first line from the start of the song
        self.pOverlay.insert(0, (00.00, ''))
        if self.SETTING_STRIP:
            poplist = []
            prev_time = []
            prev_line = ''
            for num, (time, line) in enumerate(self.pOverlay):
                if time == prev_time:
                    if len(line) > len(prev_line):
                        poplist.append(num - 1)
                    else:
                        poplist.append(num)
                prev_time = time
                prev_line = line
            for i in reversed(poplist):
                self.pOverlay.pop(i)

    def prepare_list(self, lyricslist):
        self.choices = []
        for song in lyricslist:
            listitem = xbmcgui.ListItem(song[0], offscreen=True)
            listitem.setProperty('lyric', str(song))
            listitem.setProperty('source', lyrics.source)
            self.choices.append(listitem)

    def reshow_choices(self):
        if self.choices:
            select = self.dialog.select(LANGUAGE(32005), self.choices, preselect=self.selectedlyric)
            if select > -1 and select != self.selectedlyric:
                self.selectedlyric = select
                self.stop_refresh()
                item = self.choices[select]
                source = item.getProperty('source').lower()
                lyric = eval(item.getProperty('lyric'))
                exec ('from lib.culrcscrapers.%s import lyricsScraper as lyricsScraper_%s' % (source, source))
                scraper = eval('lyricsScraper_%s.LyricsFetcher(debug=self.DEBUG, settings=self.lyricssettings)' % source)
                self.lyrics.lyrics = scraper.get_lyrics_from_list(lyric)
                self.text.reset()
                self.show_lyrics(self.lyrics)
                self.save(self.lyrics)

    def show_translation(self):
        if isinstance(self.text2, _NullTranslationControl):
            xbmcgui.Dialog().notification(ADDONNAME, LANGUAGE(32193), icon=ADDONICON, time=4000, sound=False)
            return
        # toggle: a second selection while the panel is already showing
        # just hides it again, instead of always re-fetching/re-showing
        if WIN.getProperty('culrc.translation'):
            WIN.clearProperty('culrc.translation')
            WIN.clearProperty('culrc.translation.source')
            WIN.clearProperty('culrc.translation.song')
            # explicit user close - stop auto-restoring on future tracks
            # too, until they turn it on again
            WIN.clearProperty('culrc.translation.active')
            self.text2.reset()
            self.translation_synced = False
            return
        # on-demand only, never fetched automatically per song - the user
        # asked for translation to be something they trigger for whatever
        # they're currently playing and curious about, not a background
        # job that burns API quota on every track
        # skip pointlessly translating English lyrics into English (burns
        # DeepL/Google/Lingva quota for no visible change) - only checked
        # for an English target, see looks_like_english()'s own comment
        # for why this isn't done for the other target languages too
        if self.TRANSLATE_LANG == 'en' and looks_like_english(strip_lrc_tags(self.lyrics.lyrics)):
            xbmcgui.Dialog().notification(ADDONNAME, LANGUAGE(32192), icon=ADDONICON, time=3000, sound=False)
            return

        # cache the translation wherever this box actually saves lyrics
        # (next to the music file if save_lyrics2 is on, else the
        # addon's own lyrics folder), not a fixed location that might be
        # dead/unused on a given setup
        if self.SAVE_LYRICS2:
            cache_path = self.lyrics.song.path2_translation(self.TRANSLATE_LANG)
        else:
            cache_path = self.lyrics.song.path1_translation(self.TRANSLATE_LANG)

        if self.lyrics.lrc:
            self._show_translation_synced(cache_path)
        else:
            self._show_translation_block(cache_path)

    def _show_translation_synced(self, cache_path):
        # timed lyrics: translate line-by-line so each translated line can
        # be highlighted in step with the original via the exact same
        # timestamps (self.pOverlay), instead of one static block of text
        original_lines = [line for _, line in self.pOverlay]
        translated_lines = None
        source = None
        if xbmcvfs.exists(cache_path):
            cached = get_textfile(cache_path)
            if cached is not None:
                # first line is the provider name (see write_translation_file)
                parts = cached.split('\n')
                if parts:
                    cached_source, candidate = parts[0], parts[1:]
                    if len(candidate) == len(original_lines):
                        # only ever trust a cached HUMAN translation as
                        # final - it's already the best tier available. Any
                        # machine-sourced cache (DeepL/Google/Lingva) is
                        # always re-attempted instead, since a human
                        # translation (or a DeepL upgrade over an old
                        # Google/Lingva fallback result) might be available
                        # now even if it wasn't when this was cached
                        if is_fully_human_source(cached_source):
                            translated_lines = candidate
                            source = cached_source
        if translated_lines is not None:
            # cache hit - already have everything, show it all at once
            self._populate_translation_list(translated_lines)
            self.translation_synced = True
            self._select_translation_line(self.text.getSelectedPosition())
            WIN.setProperty('culrc.translation', 'shown')
            WIN.setProperty('culrc.translation.source', source or '')
            # a cache-hit is only ever reached for a fully-human source
            # (is_fully_human_source gates what gets cached this way), so
            # the cached source name doubles as the credit name directly -
            # no percentages/DeepL suffix are ever part of it
            WIN.setProperty('culrc.translation.credit_source', source or '')
            # translator credit isn't part of the cache file, so a
            # cache-hit replay never has one - clear any stale value left
            # over from a previous song's live fetch
            WIN.clearProperty('culrc.translation.translator')
            WIN.setProperty('culrc.translation.song', self._song_fingerprint(self.lyrics.song))
            WIN.setProperty('culrc.translation.active', 'true')
            return

        xbmcgui.Dialog().notification(ADDONNAME, LANGUAGE(32179), icon=ADDONICON, time=3000, sound=False)
        # show the panel immediately with the original-language lines as
        # placeholders, then fill each one in as it arrives - DeepL's
        # single batch call resolves this almost instantly anyway, but
        # Google/Lingva have no batch endpoint (one request per line) and
        # used to leave the whole panel blank for 20-30s on a full song
        self._populate_translation_list(original_lines)
        self.translation_synced = True
        self._select_translation_line(self.text.getSelectedPosition())
        WIN.setProperty('culrc.translation', 'shown')
        WIN.setProperty('culrc.translation.song', self._song_fingerprint(self.lyrics.song))
        WIN.setProperty('culrc.translation.active', 'true')

        def _on_line(i, text, src):
            item = self.text2.getListItem(i)
            if item:
                item.setLabel(text.strip())
            # show which provider is actually being used as soon as the
            # first line succeeds, instead of leaving it blank for the
            # whole fetch (which can take 20-30s on Google/Lingva)
            if src and WIN.getProperty('culrc.translation.source') != src:
                WIN.setProperty('culrc.translation.source', src)

        # self.pOverlay (and therefore original_lines) includes blank
        # entries for bare timing markers with no lyric text - a scraped
        # human translation never has those, so the line count to compare
        # against is the non-empty subset, not the full array. Matching
        # human lines get spliced back into their original (non-empty)
        # positions so blank timing-marker slots stay blank and every
        # index still lines up with self.pOverlay's timestamps.
        non_empty_idx = [i for i, l in enumerate(original_lines) if l.strip()]
        non_empty_lines = [original_lines[i] for i in non_empty_idx]

        def _fetch():
            # human translation first (LyricsTranslate, KaraokeTexty.sk/.cz)
            # - KaraokeTexty results are content-aligned against our own
            # non-empty original lines (see align_by_content), so a
            # verbatim repeated chorus still resolves correctly even if
            # the fan site only wrote it out fewer times than it's
            # actually sung. LyricsTranslate has no easy access to its own
            # original-language column (loaded separately via AJAX), so it
            # still only qualifies on an exact total-count match. Nothing
            # usable here falls through to machine translation.
            human_lines, human_src, human_translator, human_complete = fetch_human_translation_synced(
                self.lyrics.song.artist, self.lyrics.song.title, self.TRANSLATE_LANG, non_empty_lines, debug=self.DEBUG)
            # credit_src is the bare human source name only (e.g.
            # "KaraokeTexty (CS)") - used for the end-of-song credit
            # message, which should never mention DeepL or a coverage
            # percentage even for a hybrid result. Kept separate from
            # `src` (below), which is the display/cache string and, for a
            # hybrid result, gains the "+ DeepL" part and a 2-line
            # percentage breakdown for the skin's source strip.
            credit_src = human_src
            if human_lines:
                if not human_complete:
                    # a handful of genuinely missing lines (e.g. a chorus
                    # the fan site never wrote out in the original
                    # language at all, so there was nothing to match
                    # against) shouldn't throw away an otherwise-good
                    # human translation for the rest of the song - machine
                    # translate only the specific gaps and splice them in
                    gap_pos = [i for i, t in enumerate(human_lines) if not t]
                    gap_originals = [non_empty_lines[i] for i in gap_pos]
                    total_lines = len(non_empty_lines)
                    covered = total_lines - len(gap_pos)
                    log('human translation from %s covers %d/%d lines - machine-filling %d gap(s)' % (human_src, covered, total_lines, len(gap_pos)), debug=self.DEBUG)
                    # gap-fill must land in the SAME language as the human
                    # lines it's supplementing, not always self.TRANSLATE_LANG -
                    # a KaraokeTexty cross-fallback result (human_src has a
                    # "(CS)"/"(SK)" suffix) is in the OTHER of the two
                    # languages, and mismatching here would mix e.g. Czech
                    # human lines with Slovak machine-filled ones
                    gap_lang = human_translation_lang(human_lines, human_src, self.TRANSLATE_LANG)
                    gap_lines, gap_src = translate_lines(gap_originals, gap_lang, self.DEEPL_KEY, lingva_instance=self.LINGVA_INSTANCE, debug=self.DEBUG)
                    if gap_lines:
                        # "» " prefix marks a machine-filled line within an
                        # otherwise-human hybrid result, so it's visible
                        # per-line in the panel itself, not just as an
                        # aggregate percentage in the source strip below
                        # the logo. Only ever applied here, inside the
                        # gap-fill branch - a fully human or fully machine
                        # result never goes through this code path, so
                        # neither ever gets marked. Not an actual emoji
                        # (e.g. 🤖/⚙) - font_translation is NotoSans-Regular,
                        # a text font with no color-emoji glyph and missing
                        # several symbol glyphs too (confirmed via its own
                        # cmap table: gear/star/diamond/lightning all
                        # missing); guillemet is present.
                        for gi, gline in zip(gap_pos, gap_lines):
                            human_lines[gi] = '» ' + gline
                        # shown 2-line in the skin's source strip (see
                        # script-cu-lrclyrics-main.xml.dat, now a textbox
                        # instead of a single-line label) via the [CR]
                        # break - is_fully_human_source() detects this
                        # hybrid case via the "[CR]+" marker (must stay in
                        # sync with this format)
                        human_pct = round(100 * covered / total_lines)
                        gap_pct = 100 - human_pct
                        human_src = '%s (%d%%)[CR]+ %s (%d%%)' % (human_src, human_pct, gap_src or 'DeepL', gap_pct)
                    # if even the gap machine-translation failed, those
                    # specific positions are left as '' rather than
                    # discarding the human lines that DID come through
                log('using human translation from %s (%d/%d lines)' % (human_src, len(human_lines), len(non_empty_lines)), debug=self.DEBUG)
                lines = list(original_lines)
                for idx, translated in zip(non_empty_idx, human_lines):
                    lines[idx] = translated
                src = human_src
            else:
                log('no usable human translation - falling back to machine translation', debug=self.DEBUG)
                lines, src = translate_lines(original_lines, self.TRANSLATE_LANG, self.DEEPL_KEY, lingva_instance=self.LINGVA_INSTANCE, debug=self.DEBUG, on_line=_on_line)
                human_translator = None
                credit_src = None
            if lines:
                self.write_translation_file(cache_path, src, '\n'.join(lines))
                WIN.setProperty('culrc.translation.source', src or '')
                WIN.setProperty('culrc.translation.translator', human_translator or '')
                WIN.setProperty('culrc.translation.credit_source', credit_src or '')
                # DeepL's single batch call never invokes on_line (that's
                # only used for the Google/Lingva per-line fallback), so
                # the list would otherwise keep showing the original-text
                # placeholders forever - make sure the final result always
                # lands regardless of which provider actually served it
                self._populate_translation_list(lines)
                if self.translation_synced:
                    self._select_translation_line(self.text.getSelectedPosition())
            else:
                self.dialog.ok(LANGUAGE(32178), LANGUAGE(32181))

        threading.Thread(target=_fetch, daemon=True).start()

    def _populate_translation_list(self, lines):
        self.text2.reset()
        for line in lines:
            cleanline = line.strip()
            listitem = xbmcgui.ListItem(cleanline, offscreen=True)
            # same part1-4 split as the original lyrics list (get_parts()) -
            # the bundled fallback dialog's multi-color current-line display
            # reads these for the translation column too
            for count, item in enumerate(self.get_parts(cleanline)):
                listitem.setProperty('part%i' % (count + 1), item)
            self.text2.addItem(listitem)
        # NOTE: tried calling self.setFocus(self.text2) here to cover the
        # rare case where <defaultcontrol>112</defaultcontrol> resolves
        # before translation is ready - reverted, since this method runs on
        # the background fetch thread (see _show_translation_synced's
        # threading.Thread(target=_fetch)), and setFocus() from a non-GUI
        # thread made the confirmed-working focusedlayout (bigger current
        # line) stop working entirely instead of just fixing the timing
        # edge case. <defaultcontrol> alone is the confirmed-working setup.

    def _select_translation_line(self, pos):
        # list 112 is a <control type="fixedlist"> with <focusposition>1</focusposition>
        # in the skin XML - Kodi itself always keeps the selected item at that
        # fixed on-screen slot (1 line of context above it, always), so a
        # plain selectItem() is all that's needed here. No lookahead/scroll
        # trick required - that was only ever a workaround for a plain
        # <control type="list">, which has no concept of a fixed focus slot.
        if self.text2.size() == 0:
            return
        self.text2.selectItem(pos)

    def _show_translation_block(self, cache_path):
        # untimed lyrics have nothing to sync against (no per-line
        # timestamps exist for the original either), so just show the
        # whole translated text as a static list, same as before
        text = None
        source = None
        if xbmcvfs.exists(cache_path):
            cached = get_textfile(cache_path)
            if cached is not None:
                # first line is the provider name (see write_translation_file)
                cached_source, _, cached_text = cached.partition('\n')
                # see _show_translation_synced for why only a cached human
                # translation is trusted - any machine-sourced cache is
                # always re-attempted in case a better tier is available now
                if is_fully_human_source(cached_source):
                    source, text = cached_source, cached_text
        if not text:
            xbmcgui.Dialog().notification(ADDONNAME, LANGUAGE(32179), icon=ADDONICON, time=3000, sound=False)
            # untimed lyrics have no per-line sync requirement, so any
            # human translation line count is usable - just join it back
            # into one block
            human_lines, human_src = fetch_human_translation(
                self.lyrics.song.artist, self.lyrics.song.title, self.TRANSLATE_LANG, debug=self.DEBUG)
            if human_lines:
                text, source = '\n'.join(human_lines), human_src
            else:
                text, source = translate_text(self.lyrics.lyrics, self.TRANSLATE_LANG, self.DEEPL_KEY, lingva_instance=self.LINGVA_INSTANCE, debug=self.DEBUG)
            if not text:
                self.dialog.ok(LANGUAGE(32178), LANGUAGE(32181))
                return
            self.write_translation_file(cache_path, source, text)

        self.text2.reset()
        for line in text.splitlines():
            self.text2.addItem(xbmcgui.ListItem(line.strip(), offscreen=True))
        self.translation_synced = False
        WIN.setProperty('culrc.translation', 'shown')
        WIN.setProperty('culrc.translation.source', source or '')
        WIN.setProperty('culrc.translation.song', self._song_fingerprint(self.lyrics.song))
        WIN.setProperty('culrc.translation.active', 'true')

    def write_translation_file(self, path, source, text):
        try:
            if not xbmcvfs.exists(os.path.dirname(path)):
                xbmcvfs.mkdirs(os.path.dirname(path))
            f = xbmcvfs.File(path, 'w')
            f.write((source or '') + '\n' + text)
            f.close()
        except Exception as e:
            log('failed to save translation: %s' % e, debug=self.DEBUG)

    def _show_seek_osd(self, delta):
        # a translucent progress bar + elapsed/total time, same idea as
        # Kodi's own video seek OSD - this modal dialog swallows that one
        # entirely (see the left/right handling in onAction), so without
        # this there is no visual feedback at all for where a seek landed.
        # Player.Progress/Player.Time/Player.Duration are built-in Kodi
        # infolabels the skin control binds to directly, so no per-frame
        # polling is needed here - only show/hide and the delta text are
        # driven from Python.
        WIN.setProperty('culrc.seekdelta', self._format_seek_delta(delta))
        WIN.setProperty('culrc.seekosd', 'true')
        if self._seek_hide_timer:
            self._seek_hide_timer.cancel()
        self._seek_hide_timer = Timer(SEEK_OSD_HOLD, self._hide_seek_osd)
        self._seek_hide_timer.daemon = True
        self._seek_hide_timer.start()

    def _hide_seek_osd(self):
        WIN.clearProperty('culrc.seekosd')
        WIN.clearProperty('culrc.seekdelta')

    def _maybe_show_translation_credit(self):
        # once the last timed line has passed, there's nothing left
        # competing for the lyrics area - a good moment to thank whoever
        # actually translated this (never for DeepL/Google/Lingva, only a
        # real human translation) and point at the site so it stays worth
        # scraping. Once per song, not re-shown on every refresh() call
        # that lands past the end.
        if self._credit_shown_for_song:
            return
        source = WIN.getProperty('culrc.translation.source')
        if not is_human_source(source):
            return
        domain = credit_domain_for_source(source, self.TRANSLATE_LANG)
        if not domain:
            return
        self._credit_shown_for_song = True
        # a hybrid result (e.g. "KaraokeTexty (92%)[CR]+ DeepL (8%)", see
        # _fetch()'s gap filling) still credits the human side only -
        # DeepL filled in a few lines it couldn't find a human match for,
        # it didn't do the translation, so neither it nor the coverage
        # percentages belong in a thank-you message. culrc.translation.
        # credit_source is set alongside .source specifically to carry
        # this bare name, rather than parsing it back out of the more
        # complex display string.
        display_source = WIN.getProperty('culrc.translation.credit_source') or source
        translator = WIN.getProperty('culrc.translation.translator')
        if translator:
            msg = LANGUAGE(32194) % (display_source, translator, domain)
        else:
            msg = LANGUAGE(32193) % (display_source, domain)
        WIN.setProperty('culrc.creditmsg', msg)
        WIN.setProperty('culrc.creditshow', 'true')
        if self._credit_hide_timer:
            self._credit_hide_timer.cancel()
        self._credit_hide_timer = Timer(CREDIT_DISPLAY_SECONDS, self._hide_translation_credit)
        self._credit_hide_timer.daemon = True
        self._credit_hide_timer.start()

    def _hide_translation_credit(self):
        WIN.clearProperty('culrc.creditshow')
        WIN.clearProperty('culrc.creditmsg')

    @staticmethod
    def _format_seek_delta(delta):
        sign = '+' if delta > 0 else '-'
        secs = abs(delta)
        if secs >= 60:
            return '%s%d:%02d' % (sign, secs // 60, secs % 60)
        return '%s%ds' % (sign, secs)

    def open_sync_dialog(self):
        # reuse an already-open slider instead of stacking a new one on top
        # each time up/down is pressed while one is already showing
        if self.sync_dialog and self.sync_dialog.is_alive():
            return
        self.sync_dialog = syncThread(adjust=self.syncadjust, function=self.set_synctime, save=self.save, lyrics=self.lyrics, remove=self.remove, monitor=self.Monitor)
        self.sync_dialog.start()

    def set_synctime(self, adjust):
        self.syncadjust = adjust

    def scrolltosync(self):
        old_time = xbmc.Player().getTime()
        item = self.text.getSelectedItem()
        new_time = float(item.getProperty('time'))
        self.syncadjust = new_time - old_time
        # safe new offset to file
        self.save(self.lyrics, self.syncadjust)
        # file has changed, remove it from memory
        self.remove(self.lyrics)

    def scroll_txt(self, actionId):
        pos = self.text.getSelectedPosition()
        nums = self.text.size()
        if actionId in (3, 105, 111, 603):  # up-ish actions
            pos = max(pos - 1, 0)
        else:  # down-ish actions
            pos = min(pos + 1, nums - 1)
        self.text.selectItem(pos)

    def context_menu(self):
        labels = ()
        functions = ()
        if self.choices:
            labels += (LANGUAGE(32006),)
            functions += ('select',)
        if WIN.getProperty('culrc.islrc') == 'true':
            labels += (LANGUAGE(32007),)
            functions += ('sync',)
        if lyrics.source != LANGUAGE(32002):
            labels += (LANGUAGE(32167),)
            functions += ('delete',)
        if self.SETTING_TRANSLATE and self.lyrics.lyrics:
            labels += (LANGUAGE(32184) if WIN.getProperty('culrc.translation') else LANGUAGE(32177),)
            functions += ('translate',)
        if labels:
            selection = self.dialog.contextmenu(labels)
            if selection >= 0:
                if functions[selection] == 'select':
                    self.reshow_choices()
                elif functions[selection] == 'sync':
                    self.open_sync_dialog()
                elif functions[selection] == 'delete':
                    self.lyrics.lyrics = ''
                    self.reset_controls()
                    self.deleted = True
                    self.delete(self.lyrics)
                elif functions[selection] == 'translate':
                    self.show_translation()

    def reset_controls(self):
        self.text.reset()
        self.label.setLabel('')
        WIN.clearProperty('culrc.lyrics')
        WIN.clearProperty('culrc.islrc')
        WIN.clearProperty('culrc.source')
        self.text2.reset()
        self.translation_synced = False
        # a fresh GUI instance for the OK/OSD reopen of the SAME song
        # would otherwise wipe out a translation the user had showing -
        # only clear it here for a genuinely different song; a matching
        # song has its panel silently restored from cache afterwards, see
        # _maybe_restore_translation(). self.SONG_RESTARTED forces a clear
        # even when the fingerprint matches - the artist|title fingerprint
        # alone can't tell "still the same playing instance" apart from
        # "this same track just started playing again from the top" (e.g.
        # repeat-one, or a short playlist looping back to it), confirmed
        # live: without this, a same-song repeat left the translation
        # panel stuck showing nothing on the new (empty) list control
        # while the WIN properties still claimed one was already "shown".
        if self.SONG_RESTARTED or WIN.getProperty('culrc.translation.song') != self._song_fingerprint(self.lyrics.song):
            WIN.clearProperty('culrc.translation')
            WIN.clearProperty('culrc.translation.source')
            WIN.clearProperty('culrc.translation.song')
            # genuinely new song - allow the end-of-lyrics credit to show
            # again (it's a once-per-song thing, see _maybe_show_translation_credit)
            self._credit_shown_for_song = False
            if self._credit_hide_timer:
                self._credit_hide_timer.cancel()
            self._hide_translation_credit()

    def _song_fingerprint(self, song):
        return '%s|%s' % (song.artist, song.title)

    def _maybe_restore_translation(self):
        # called after a fresh GUI instance shows lyrics again - either the
        # OK/OSD reopen of the same song (culrc.translation survived, see
        # clear()'s comment), or a genuinely new/next song. Translation is
        # "sticky" for the rest of the session once turned on
        # (culrc.translation.active): a new song reuses its cache if one
        # exists, or fetches a fresh one if not - same as pressing "Show
        # translation" manually, just automatic while the mode is on.
        # Never triggers on a fresh Kodi start with no prior track, and
        # stops once the user explicitly closes it (see toggle-off in
        # show_translation, which clears culrc.translation.active).
        if not self.SETTING_TRANSLATE or not self.lyrics.lyrics:
            return
        fingerprint = self._song_fingerprint(self.lyrics.song)
        already_shown = (WIN.getProperty('culrc.translation') == 'shown'
                          and WIN.getProperty('culrc.translation.song') == fingerprint)
        if not already_shown and WIN.getProperty('culrc.translation.active') != 'true':
            return
        # same English-into-English skip as show_translation() - "sticky"
        # mode following into a song that's already in English shouldn't
        # burn quota fetching a same-language "translation" either
        if self.TRANSLATE_LANG == 'en' and looks_like_english(strip_lrc_tags(self.lyrics.lyrics)):
            return
        if self.SAVE_LYRICS2:
            cache_path = self.lyrics.song.path2_translation(self.TRANSLATE_LANG)
        else:
            cache_path = self.lyrics.song.path1_translation(self.TRANSLATE_LANG)
        if self.lyrics.lrc:
            self._show_translation_synced(cache_path)
        else:
            self._show_translation_block(cache_path)

    def exit_gui(self, action):
        # in manual mode, we also need to quit the script when the user cancels the gui or music has ended
        if (not self.SETTING_SERVICE) and (action == 'quit'):
            # signal the main loop to quit
            self.callback('quit')
        self.allowtimer = False
        self.stop_refresh()
        self.showgui = False
        if self._seek_hide_timer:
            self._seek_hide_timer.cancel()
        WIN.clearProperty('culrc.seekosd')
        WIN.clearProperty('culrc.seekdelta')
        self.close()

    def onClick(self, controlId):
        if (controlId == 112):
            # list 112 (translation) is given real window focus so its
            # focusedlayout can show a bigger current line - see the skin
            # XML's comment above <control type="list" id="112">. Unlike
            # 110, it has no click-to-seek behavior of its own, so forward
            # OK presses to the exact same close-dialog/open-OSD logic as
            # onAction()'s ACTION_SELECT_ITEM case (which never fires while
            # a focused control's own onClick() already consumed the OK).
            if not xbmc.getCondVisibility("Window.IsVisible(10120)"):
                xbmc.executebuiltin("ActivateWindow(10120)")
                mon = self.Monitor
                def _reopen_when_osd_closes():
                    xbmc.sleep(300)
                    while xbmc.getCondVisibility('Window.IsVisible(10120)') and not mon.abortRequested():
                        xbmc.sleep(200)
                    if not mon.abortRequested():
                        WIN.setProperty('culrc.force', 'TRUE')
                threading.Thread(target=_reopen_when_osd_closes).start()
                self.exit_gui("quit")
        elif (controlId == 110):
            # will only work for lrc based lyrics
            try:
                item = self.text.getSelectedItem()
                stamp = float(item.getProperty('time'))
                xbmc.Player().seekTime(stamp)
                # without this, the line highlight only catches up whenever
                # the stale timer scheduled by the last refresh() call
                # happens to fire (its wait time was computed for the OLD
                # position) - could be several seconds, and looks like
                # "lyrics didn't follow the seek" until it self-corrects
                self.stop_refresh()
                self.refresh()
            except:
                pass

    def onFocus(self, controlId):
        self.controlId = controlId

    def onAction(self, action):
        actionId = action.getId()
        if (actionId in CANCEL_DIALOG):
            # dialog cancelled, close the gui
            self.exit_gui('quit')
        elif (actionId == 101) or (actionId == 117): # ACTION_MOUSE_RIGHT_CLICK / ACTION_CONTEXT_MENU
            self.context_menu()
        elif actionId in (1, 2):  # ACTION_MOVE_LEFT / ACTION_MOVE_RIGHT - seek
            # this modal dialog swallows all remote input, including the
            # left/right seek that would normally work during playback
            # with no dialog open at all - forward it manually instead of
            # leaving seeking dead the whole time lyrics are on screen.
            # Same rapid-repeat acceleration as Kodi's video seek OSD:
            # 1st press 10s, 2nd (within SEEK_STREAK_WINDOW) 30s, 3rd+ 1min
            player = xbmc.Player()
            if player.isPlayingAudio():
                now = time.time()
                if actionId == self._seek_last_action and (now - self._seek_last_press_time) <= SEEK_STREAK_WINDOW:
                    self._seek_streak = min(self._seek_streak + 1, len(SEEK_STEPS))
                else:
                    self._seek_streak = 1
                self._seek_last_press_time = now
                self._seek_last_action = actionId
                step = SEEK_STEPS[self._seek_streak - 1]
                delta = -step if actionId == 1 else step
                player.seekTime(max(0, player.getTime() + delta))
                self._show_seek_osd(delta)
                # same reason as onClick's lyric-line jump: refresh() only
                # reschedules itself for the NEXT line boundary each time it
                # runs, so without an immediate resync here the highlighted
                # line keeps following the pre-seek timeline until whatever
                # stale timer was already pending happens to fire
                self.stop_refresh()
                self.refresh()
        elif (actionId in ACTION_OSD):
            if not self.blockOSD:
                # mouse move constantly calls ACTION_OSD, process only once
                if not xbmc.getCondVisibility('Window.IsVisible(10120)'):
                    xbmc.executebuiltin('ActivateWindow(10120)')
        elif (actionId == 7):  # ACTION_SELECT_ITEM (OK) - close dialog, show OSD, reopen lyrics via culrc.force once OSD closes
            if not xbmc.getCondVisibility("Window.IsVisible(10120)"):
                xbmc.executebuiltin("ActivateWindow(10120)")
                mon = self.Monitor
                def _reopen_when_osd_closes():
                    xbmc.sleep(300)
                    while xbmc.getCondVisibility('Window.IsVisible(10120)') and not mon.abortRequested():
                        xbmc.sleep(200)
                    if not mon.abortRequested():
                        WIN.setProperty('culrc.force', 'TRUE')
                threading.Thread(target=_reopen_when_osd_closes).start()
                self.exit_gui("quit")
        elif (actionId in ACTION_CODEC):
            xbmc.executebuiltin('Action(PlayerProcessInfo)')
        elif (actionId in ACTION_UPDOWN) and WIN.getProperty('culrc.islrc') == 'true':
            # Up/down used to just nudge a hidden offset and pop a
            # notification (unclear which direction did what). Now it opens
            # the same slider dialog as the context menu's "Sync" option
            # instead - once it's open, Kodi's native slider control handles
            # further up/down presses itself (it becomes the focused
            # window), showing live which way is earlier vs. later.
            self.open_sync_dialog()
        elif (actionId in ACTION_UPDOWN) and WIN.getProperty('culrc.islrc') != 'true':
            # Plain (untimed) txt lyrics have no auto-scroll timer, and the
            # list never gets native focus (disabled as part of the OK
            # button/OSD fix, see setFocus comments above), so onFocus()
            # never fires and self.controlId never becomes 110 - up/down
            # would otherwise do nothing and only the first line ever shows.
            # Move the selection ourselves instead of relying on focus.
            self.scroll_txt(actionId)

class MyPlayer(xbmc.Player):
    def __init__(self, *args, **kwargs):
        xbmc.Player.__init__(self)
        self.function = kwargs['function']
        self.clear = kwargs['clear']

    def onAVStarted(self):
        self.clear()
        if xbmc.getCondVisibility('Window.IsVisible(12006)'):
            # this event means a new playback stream genuinely just started
            # (Kodi fires it again even when the exact same track repeats),
            # so always treat it as a song change - see myPlayerChanged()
            self.function(force=True)

    def onPlayBackStopped(self):
        self.clear()

    def onPlayBackEnded(self):
        self.clear()

class MyMonitor(xbmc.Monitor):
    def __init__(self, *args, **kwargs):
        xbmc.Monitor.__init__(self)
        self.function = kwargs['function']

    def onSettingsChanged(self):
        # sleep before retrieving the new settings
        xbmc.sleep(500)
        self.function()
