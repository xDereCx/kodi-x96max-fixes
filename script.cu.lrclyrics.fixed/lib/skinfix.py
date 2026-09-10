import os
import shutil
import xbmc
import xbmcaddon
import xbmcvfs

# Aeon Nox 5 skin patches - formerly a separate addon (script.xderecx.aeonnox5lyricsfix),
# merged directly into this addon 2026-09-10 to eliminate a mutual <requires>
# dependency cycle between the two (confirmed cause of a full GUI-thread
# freeze when installing either one from the repo - Kodi's addon-dependency
# resolver appears unable to safely walk a true A-requires-B-requires-A
# graph). This addon is Aeon Nox 5-only anyway (see addon.xml description),
# so there was no real reason for these to be two addons in the first place.

ADDON = xbmcaddon.Addon()
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
SKINFILE_DIR = os.path.join(ADDON_PATH, 'resources', 'skinfile')

# (bundled .dat filename, skin-relative path, one-line description shown in the confirm dialog)
PATCHES = [
    ('script-cu-lrclyrics-main.xml.dat', os.path.join('1080i', 'script-cu-lrclyrics-main.xml'),
     'hides the topbar.png dark band over lyrics text, adds the rotating-fanart background control'),
    ('MusicVisualisation.xml.dat', os.path.join('1080i', 'MusicVisualisation.xml'),
     'hides the static Player.Art(fanart) background so it cannot cover the rotating fanart image'),
    ('Font.xml.dat', os.path.join('1080i', 'Font.xml'),
     'fixes missing Slovak/Czech diacritics in 2 of 5 lyrics display fonts'),
    ('MusicOSD.xml.dat', os.path.join('1080i', 'MusicOSD.xml'),
     'fixes the OSD Lyrics button (control 703) calling the pre-fork original script.cu.lrclyrics instead of this addon'),
    ('DialogSeekBar.xml.dat', os.path.join('1080i', 'DialogSeekBar.xml'),
     "shows the native seek progress bar during music playback too, not just video - AN5's own copy required "
     "VideoPlayer.IsFullscreen (always false for audio) as well as Player.Seeking, so seeking during music never "
     "showed any visual feedback at all; added '| Window.IsActive(visualisation)' as an alternative, matching how "
     "Kodi's own reference Estuary skin already gates this same window"),
]

# new files this addon introduces rather than patches - no original to
# back up, just installed/updated as-is if missing or out of date
NEW_FILES = [
    ('script-cu-lrclyrics-sync.xml.dat', os.path.join('1080i', 'script-cu-lrclyrics-sync.xml'),
     'dedicated wide sync-offset slider window, so it does not affect the shared DialogSlider.xml used for volume/seek/brightness'),
]

# Aeon Nox 5 keeps a second, independent copy of itself installed as its own
# addon (skin.aeon.nox.5.skinbase) purely so its own "reset skin to default"
# feature has a pristine copy to restore from. It is not just a backup file
# sitting inside the live skin's folder - Kodi can make it the active skin's
# source of truth again at any time, so every patch/new-file here must be
# kept in sync on BOTH copies or a skin reset silently reverts every fix.
SKIN_IDS = ['skin.aeon.nox.5', 'skin.aeon.nox.5.skinbase']


def find_skin_roots():
    roots = []
    for skin_id in SKIN_IDS:
        try:
            skin_addon = xbmcaddon.Addon(skin_id)
        except RuntimeError:
            continue
        roots.append((skin_id, xbmcvfs.translatePath(skin_addon.getAddonInfo('path'))))
    return roots


def find_pending(skin_roots):
    pending = []
    for skin_id, skin_root in skin_roots:
        for bundled_name, rel_path, desc in PATCHES:
            bundled = os.path.join(SKINFILE_DIR, bundled_name)
            target = os.path.join(skin_root, rel_path)
            if not os.path.isfile(bundled):
                xbmc.log('[culrc.skinfix] bundled file missing, reinstall this addon: %s' % bundled, xbmc.LOGERROR)
                continue
            if not os.path.isfile(target):
                xbmc.log('[culrc.skinfix] expected skin file not found, skin layout may have changed: %s' % target, xbmc.LOGWARNING)
                continue
            with open(bundled, 'rb') as f:
                fixed = f.read()
            with open(target, 'rb') as f:
                current = f.read()
            if current != fixed:
                pending.append(('patch', bundled, target, '%s: %s' % (skin_id, rel_path), desc))

        for bundled_name, rel_path, desc in NEW_FILES:
            bundled = os.path.join(SKINFILE_DIR, bundled_name)
            target = os.path.join(skin_root, rel_path)
            if not os.path.isfile(bundled):
                xbmc.log('[culrc.skinfix] bundled file missing, reinstall this addon: %s' % bundled, xbmc.LOGERROR)
                continue
            with open(bundled, 'rb') as f:
                fixed = f.read()
            current = None
            if os.path.isfile(target):
                with open(target, 'rb') as f:
                    current = f.read()
            if current != fixed:
                pending.append(('new', bundled, target, '%s: %s' % (skin_id, rel_path), desc))
    return pending


def apply_pending(pending):
    for kind, bundled, target, rel_path, desc in pending:
        if kind == 'patch':
            backup = target + '.bak'
            if not os.path.isfile(backup):
                shutil.copy2(target, backup)
        shutil.copy2(bundled, target)
        xbmc.log('[culrc.skinfix] %s %s (%s)' % ('patched' if kind == 'patch' else 'installed', target, desc), xbmc.LOGINFO)


def apply_skin_fixes_silently():
    """Called once on every Kodi startup, before the lyrics service takes over.
    No confirmation dialog - every patch here is idempotent with a .bak kept,
    so there is nothing destructive to confirm, and this is what makes
    installing this addon on a fresh Aeon Nox 5 box 'just work'."""
    skin_roots = find_skin_roots()
    if not skin_roots:
        return 0
    pending = find_pending(skin_roots)
    if pending:
        apply_pending(pending)
        xbmc.log('[culrc.skinfix] auto-applied %d skin patch(es) on startup' % len(pending), xbmc.LOGINFO)
    return len(pending)
