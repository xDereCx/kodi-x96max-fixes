import os
import shutil
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
SKINFILE_DIR = os.path.join(ADDON_PATH, 'resources', 'skinfile')
DIALOG = xbmcgui.Dialog()

# (bundled .dat filename, skin-relative path, one-line description shown in the confirm dialog)
PATCHES = [
    ('script-cu-lrclyrics-main.xml.dat', os.path.join('1080i', 'script-cu-lrclyrics-main.xml'),
     'hides the topbar.png dark band over lyrics text, adds the rotating-fanart background control'),
    ('MusicVisualisation.xml.dat', os.path.join('1080i', 'MusicVisualisation.xml'),
     'hides the static Player.Art(fanart) background so it cannot cover the rotating fanart image'),
    ('Font.xml.dat', os.path.join('1080i', 'Font.xml'),
     'fixes missing Slovak/Czech diacritics in 2 of 5 lyrics display fonts'),
]

# new files this addon introduces rather than patches - no original to
# back up, just installed/updated as-is if missing or out of date
NEW_FILES = [
    ('script-cu-lrclyrics-sync.xml.dat', os.path.join('1080i', 'script-cu-lrclyrics-sync.xml'),
     'dedicated wide sync-offset slider window, so it does not affect the shared DialogSlider.xml used for volume/seek/brightness'),
]


def find_skin_root():
    try:
        skin_addon = xbmcaddon.Addon('skin.aeon.nox.5')
    except RuntimeError:
        return None
    return xbmcvfs.translatePath(skin_addon.getAddonInfo('path'))


def main():
    skin_root = find_skin_root()
    if not skin_root:
        DIALOG.ok('Aeon Nox 5 Skin Fixes', 'skin.aeon.nox.5 is not installed. Install/enable it first, then run this again.')
        return

    pending = []
    for bundled_name, rel_path, desc in PATCHES:
        bundled = os.path.join(SKINFILE_DIR, bundled_name)
        target = os.path.join(skin_root, rel_path)
        if not os.path.isfile(bundled):
            xbmc.log('[aeonnox5skinfix] bundled file missing, reinstall this addon: %s' % bundled, xbmc.LOGERROR)
            continue
        if not os.path.isfile(target):
            xbmc.log('[aeonnox5skinfix] expected skin file not found, skin layout may have changed: %s' % target, xbmc.LOGWARNING)
            continue
        with open(bundled, 'rb') as f:
            fixed = f.read()
        with open(target, 'rb') as f:
            current = f.read()
        if current != fixed:
            pending.append(('patch', bundled, target, rel_path, desc))

    new_pending = []
    for bundled_name, rel_path, desc in NEW_FILES:
        bundled = os.path.join(SKINFILE_DIR, bundled_name)
        target = os.path.join(skin_root, rel_path)
        if not os.path.isfile(bundled):
            xbmc.log('[aeonnox5skinfix] bundled file missing, reinstall this addon: %s' % bundled, xbmc.LOGERROR)
            continue
        with open(bundled, 'rb') as f:
            fixed = f.read()
        current = None
        if os.path.isfile(target):
            with open(target, 'rb') as f:
                current = f.read()
        if current != fixed:
            new_pending.append(('new', bundled, target, rel_path, desc))

    all_pending = pending + new_pending
    if not all_pending:
        DIALOG.notification('Aeon Nox 5 Skin Fixes', 'Already applied, nothing to do', icon=xbmcgui.NOTIFICATION_INFO)
        return

    listing = '\n'.join('- %s' % rel_path for _, _, _, rel_path, _ in all_pending)
    if not DIALOG.yesno(
        'Aeon Nox 5 Skin Fixes',
        'This will patch/install %d skin file(s):\n%s\n\nA backup (.bak) of each original is kept if one does not already exist (new files this addon introduces need no backup). Continue?' % (len(all_pending), listing)
    ):
        return

    for kind, bundled, target, rel_path, desc in all_pending:
        if kind == 'patch':
            backup = target + '.bak'
            if not os.path.isfile(backup):
                shutil.copy2(target, backup)
        shutil.copy2(bundled, target)
        xbmc.log('[aeonnox5skinfix] %s %s (%s)' % ('patched' if kind == 'patch' else 'installed', target, desc), xbmc.LOGINFO)

    DIALOG.ok('Aeon Nox 5 Skin Fixes', 'Applied %d patch(es). Restart Kodi for it to take effect.' % len(all_pending))


if __name__ == '__main__':
    main()
