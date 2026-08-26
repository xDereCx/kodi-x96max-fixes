import os
import shutil
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
BUNDLED_FIX = os.path.join(ADDON_PATH, 'resources', 'skinfile', 'script-cu-lrclyrics-main.xml.dat')
DIALOG = xbmcgui.Dialog()


def find_skin_target():
    try:
        skin_addon = xbmcaddon.Addon('skin.aeon.nox.5')
    except RuntimeError:
        return None
    skin_path = xbmcvfs.translatePath(skin_addon.getAddonInfo('path'))
    return os.path.join(skin_path, '1080i', 'script-cu-lrclyrics-main.xml')


def main():
    if not os.path.isfile(BUNDLED_FIX):
        DIALOG.notification('Aeon Nox 5 fix', 'Bundled fix file missing, reinstall this addon', icon=xbmcgui.NOTIFICATION_ERROR)
        return

    target = find_skin_target()
    if not target:
        DIALOG.ok('Aeon Nox 5 fix', 'skin.aeon.nox.5 is not installed. Install/enable it first, then run this again.')
        return

    if not os.path.isfile(target):
        DIALOG.ok('Aeon Nox 5 fix', 'Expected skin file not found:\n%s\n\nThe skin layout may have changed; this fix may be out of date.' % target)
        return

    with open(target, 'rb') as f:
        current = f.read()

    with open(BUNDLED_FIX, 'rb') as f:
        fixed = f.read()

    if current == fixed:
        DIALOG.notification('Aeon Nox 5 fix', 'Already applied, nothing to do', icon=xbmcgui.NOTIFICATION_INFO)
        return

    if not DIALOG.yesno(
        'Aeon Nox 5: CU LRC Lyrics fix',
        'This will patch:\n%s\n\nto hide the topbar.png control that draws a dark band '
        'over lyrics text. A backup (.bak) of the current file will be kept if one '
        'does not already exist. Continue?' % target
    ):
        return

    backup = target + '.bak'
    if not os.path.isfile(backup):
        shutil.copy2(target, backup)

    shutil.copy2(BUNDLED_FIX, target)

    xbmc.log('[aeonnox5lyricsfix] patched %s' % target, xbmc.LOGINFO)
    DIALOG.ok('Aeon Nox 5 fix', 'Applied. Restart Kodi for it to take effect.')


if __name__ == '__main__':
    main()
