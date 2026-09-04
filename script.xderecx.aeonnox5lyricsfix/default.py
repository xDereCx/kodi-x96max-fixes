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


def main():
    skin_roots = find_skin_roots()
    if not skin_roots:
        DIALOG.ok('Aeon Nox 5 Skin Fixes', 'skin.aeon.nox.5 is not installed. Install/enable it first, then run this again.')
        return

    # installed is not the same as ACTIVE - xbmc.getSkinDir() is whichever
    # skin Kodi is actually running right now. Patching still proceeds (the
    # user may be about to switch to it, or just wants it ready ahead of
    # time), but nothing will be visibly different until they do switch -
    # worth telling them so a "nothing happened" report isn't confusing.
    if xbmc.getSkinDir() != 'skin.aeon.nox.5':
        DIALOG.notification('Aeon Nox 5 Skin Fixes', 'skin.aeon.nox.5 is installed but not the active skin - patches will apply but stay invisible until you switch to it', icon=xbmcgui.NOTIFICATION_INFO, time=6000)

    all_pending = []
    for skin_id, skin_root in skin_roots:
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
                all_pending.append(('patch', bundled, target, '%s: %s' % (skin_id, rel_path), desc))

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
                all_pending.append(('new', bundled, target, '%s: %s' % (skin_id, rel_path), desc))

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
