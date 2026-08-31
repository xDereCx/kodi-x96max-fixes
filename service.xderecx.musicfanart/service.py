import os
import re
import json
import time
import threading
import urllib.request
import urllib.parse

import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon

ADDON = xbmcaddon.Addon()
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
CACHE_DIR = os.path.join(PROFILE, 'cache')
if not xbmcvfs.exists(PROFILE):
    xbmcvfs.mkdirs(PROFILE)
if not xbmcvfs.exists(CACHE_DIR):
    xbmcvfs.mkdirs(CACHE_DIR)

WINDOW_VISUALISATION = 12006
WINDOW = xbmcgui.Window(WINDOW_VISUALISATION)
PROPERTY = 'ArtistSlideshow.Image'
THEAUDIODB_KEY = '2'
ROTATE_SECONDS = 12


def get_max_images():
    try:
        return max(1, ADDON.getSettingInt('max_images'))
    except Exception:
        return 100
ILLEGAL_CHARS = '<>:"/\\|?*'


def log(msg):
    xbmc.log('[MusicFanart] %s' % msg, xbmc.LOGINFO)


def safe_name(name):
    for ch in ILLEGAL_CHARS:
        name = name.replace(ch, '_')
    return name.strip()


def http_get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {'User-Agent': 'xDereCx-MusicFanart/1.0'})
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode('utf-8'))


def fetch_theaudiodb(artist):
    try:
        url = 'https://theaudiodb.com/api/v1/json/%s/search.php?s=%s' % (
            THEAUDIODB_KEY, urllib.parse.quote(artist))
        data = http_get_json(url)
        artists = data.get('artists') or []
        if not artists:
            return []
        a = artists[0]
        urls = []
        for key in ('strArtistFanart', 'strArtistFanart2', 'strArtistFanart3', 'strArtistFanart4'):
            v = a.get(key)
            if v:
                urls.append(v)
        return urls
    except Exception as e:
        log('theaudiodb error for %s: %s' % (artist, e))
        return []


def get_mbid(artist):
    try:
        url = 'https://musicbrainz.org/ws/2/artist/?query=%s&fmt=json&limit=1' % urllib.parse.quote(artist)
        data = http_get_json(url, headers={'User-Agent': 'xDereCx-MusicFanart/1.0 (kodi addon)'})
        artists = data.get('artists') or []
        if artists and artists[0].get('score', 0) >= 90:
            return artists[0]['id']
    except Exception as e:
        log('musicbrainz error for %s: %s' % (artist, e))
    return None


def fetch_fanarttv(artist_mbid):
    key = ADDON.getSetting('fanarttv_key')
    if not key or not artist_mbid:
        return []
    try:
        url = 'https://webservice.fanart.tv/v3/music/%s?api_key=%s' % (artist_mbid, key)
        data = http_get_json(url)
        return [i['url'] for i in data.get('artistbackground', [])]
    except Exception as e:
        log('fanarttv error for mbid %s: %s' % (artist_mbid, e))
        return []


def fetch_deezer(artist):
    # No API key needed. Mainly useful as a fallback for Slovak/Czech and
    # other regional artists that TheAudioDB/fanart.tv (English-language,
    # MusicBrainz-ID-based) tend not to have at all. Deezer only gives a
    # single square artist photo (not a wide fanart background), but a
    # decent photo beats a blank background.
    try:
        url = 'https://api.deezer.com/search/artist?q=%s' % urllib.parse.quote(artist)
        data = http_get_json(url)
        results = data.get('data') or []
        if not results:
            return []
        a = results[0]
        for key in ('picture_xl', 'picture_big'):
            v = a.get(key)
            if v:
                return [v]
        return []
    except Exception as e:
        log('deezer error for %s: %s' % (artist, e))
        return []


def get_real_playing_file():
    # xbmc.Player().getPlayingFile() returns a musicdb://songs/... virtual
    # URL (not a real filesystem path) when the track was started from the
    # Kodi music library view, rather than played directly from a file
    # browser. Player.GetItem's "file" property resolves to the actual
    # on-disk path in that case, so prefer it and only fall back to
    # getPlayingFile() (e.g. for non-library playback) if it's unavailable.
    try:
        req = json.dumps({
            'jsonrpc': '2.0', 'id': 1, 'method': 'Player.GetItem',
            'params': {'playerid': 0, 'properties': ['file']}
        })
        resp = json.loads(xbmc.executeJSONRPC(req))
        f = resp.get('result', {}).get('item', {}).get('file')
        if f and not f.startswith('musicdb://'):
            return f
    except Exception as e:
        log('Player.GetItem error: %s' % e)
    return None


def download(url, dest):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if len(data) < 2000:
            return False
        with open(dest, 'wb') as f:
            f.write(data)
        return True
    except Exception as e:
        log('download error %s: %s' % (url, e))
        return False


class Rotator(threading.Thread):
    def __init__(self, monitor):
        super(Rotator, self).__init__()
        self.monitor = monitor
        self.images = []
        self.lock = threading.Lock()
        self.daemon = True

    def set_images(self, images):
        with self.lock:
            self.images = images

    def run(self):
        idx = 0
        while not self.monitor.abortRequested():
            with self.lock:
                images = list(self.images)
            if images:
                WINDOW.setProperty(PROPERTY, images[idx % len(images)])
                idx += 1
            if self.monitor.waitForAbort(ROTATE_SECONDS):
                break


class MusicMonitor(xbmc.Player):
    def __init__(self, monitor, rotator):
        super(MusicMonitor, self).__init__()
        self.monitor = monitor
        self.rotator = rotator
        self.current_artist = None

    def onAVStarted(self):
        self._handle_change()

    def onPlayBackStarted(self):
        self._handle_change()

    def onPlayBackStopped(self):
        self.current_artist = None
        WINDOW.setProperty(PROPERTY, '')
        self.rotator.set_images([])

    def onPlayBackEnded(self):
        self.onPlayBackStopped()

    def _handle_change(self):
        try:
            if not self.isPlayingAudio():
                return
            tag = self.getMusicInfoTag()
            artist = tag.getArtist()
            playing_file = get_real_playing_file() or self.getPlayingFile()
        except Exception:
            return
        if not artist or artist == self.current_artist:
            return
        self.current_artist = artist
        threading.Thread(target=self._fetch_and_set, args=(artist, playing_file), daemon=True).start()

    def _guess_artist_folder(self, playing_file):
        # Library convention here is Artist/YYYY - Album/NN - Title.ext
        # (or Artist/YYYY - Album/CD NN/NN - Title.ext) -- walk up from the
        # track until we leave a "YYYY - ..." album-looking directory.
        try:
            path = xbmcvfs.translatePath(playing_file)
            d = os.path.dirname(path)
            for _ in range(3):
                parent = os.path.dirname(d)
                base = os.path.basename(d)
                if re.match(r'^(CD\s*\d+|\d{4}\s*-.*)$', base):
                    d = parent
                    continue
                return d
        except Exception as e:
            log('could not guess artist folder for %s: %s' % (playing_file, e))
        return None

    def _fetch_and_set(self, artist, playing_file):
        safe = safe_name(artist)
        use_library = ADDON.getSettingBool('save_to_library')
        subfolder = ADDON.getSetting('library_subfolder_name') or 'Fanart'
        artist_dir = None

        if use_library:
            guessed = self._guess_artist_folder(playing_file)
            if guessed:
                candidate = os.path.join(guessed, subfolder)
                try:
                    if not os.path.isdir(candidate):
                        os.makedirs(candidate)
                    testfile = os.path.join(candidate, '.write_test')
                    with open(testfile, 'w') as f:
                        f.write('ok')
                    os.remove(testfile)
                    artist_dir = candidate
                except Exception as e:
                    log('library folder not writable for %s (%s), falling back to private cache: %s' % (artist, candidate, e))

        if artist_dir is None:
            artist_dir = os.path.join(CACHE_DIR, safe)
            try:
                if not os.path.isdir(artist_dir):
                    os.makedirs(artist_dir)
            except Exception as e:
                log('private cache dir error for %s: %s' % (artist, e))
                return

        try:
            existing = sorted(
                os.path.join(artist_dir, f) for f in os.listdir(artist_dir)
                if f.lower().endswith(('.jpg', '.jpeg', '.png'))
            )
        except Exception as e:
            log('listing error for %s: %s' % (artist, e))
            existing = []

        if existing:
            log('using %d cached image(s) for %s while checking for more' % (len(existing), artist))
            self.rotator.set_images(existing)

        max_images = get_max_images()
        if len(existing) >= max_images:
            return

        if not existing:
            xbmcgui.Dialog().notification(
                'DC Artist Artwork DL',
                'Hľadám fanart pre %s...' % artist,
                icon=xbmcgui.NOTIFICATION_INFO, time=4000, sound=False)

        urls = fetch_theaudiodb(artist)
        mbid = get_mbid(artist)
        urls += fetch_fanarttv(mbid) if mbid else []
        urls += fetch_deezer(artist)

        if not urls:
            if not existing:
                log('no fanart found for %s' % artist)
                xbmcgui.Dialog().notification(
                    'DC Artist Artwork DL',
                    'Nič sa nenašlo pre %s' % artist,
                    icon=xbmcgui.NOTIFICATION_INFO, time=3000, sound=False)
            return

        # already-downloaded URLs are tracked in a sidecar file so re-runs
        # don't re-download the same ones under a new number
        seen_file = os.path.join(artist_dir, '.seen_urls')
        seen = set()
        if os.path.isfile(seen_file):
            with open(seen_file, 'r', encoding='utf-8') as f:
                seen = set(line.strip() for line in f if line.strip())

        new_urls = [u for u in urls if u not in seen]
        room = max_images - len(existing)
        saved = list(existing)
        next_num = len(existing) + 1
        for url in new_urls[:room]:
            if self.current_artist != artist:
                break
            dest = os.path.join(artist_dir, '%03d.jpg' % next_num)
            if download(url, dest):
                saved.append(dest)
                seen.add(url)
                next_num += 1

        with open(seen_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(seen)))

        if len(saved) > len(existing) and self.current_artist == artist:
            log('now have %d image(s) total for %s' % (len(saved), artist))
            self.rotator.set_images(sorted(saved))


def main():
    log('service starting')
    monitor = xbmc.Monitor()
    rotator = Rotator(monitor)
    rotator.start()
    player = MusicMonitor(monitor, rotator)
    if player.isPlayingAudio():
        player._handle_change()
    while not monitor.abortRequested():
        if monitor.waitForAbort(5):
            break
    WINDOW.setProperty(PROPERTY, '')
    log('service stopping')


if __name__ == '__main__':
    main()
