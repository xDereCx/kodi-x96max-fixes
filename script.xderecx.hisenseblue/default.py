import os
import shutil
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
BUNDLED_KEYMAP = os.path.join(ADDON_PATH, 'resources', 'files', 'custom_remote.xml')

TARGET_DIR = xbmcvfs.translatePath('special://userdata/keymaps')
TARGET_KEYMAP = os.path.join(TARGET_DIR, 'custom_remote.xml')

DIALOG = xbmcgui.Dialog()


def read(path):
    with open(path, 'rb') as f:
        return f.read()


def main():
    if not os.path.isfile(BUNDLED_KEYMAP):
        DIALOG.notification('Hisense blue button', 'Bundled file missing, reinstall this addon', icon=xbmcgui.NOTIFICATION_ERROR)
        return

    bundled = read(BUNDLED_KEYMAP)

    if os.path.isfile(TARGET_KEYMAP):
        current = read(TARGET_KEYMAP)
        if current == bundled:
            DIALOG.notification('Hisense blue button', 'Already installed, nothing to do', icon=xbmcgui.NOTIFICATION_INFO)
            return
        # custom_remote.xml is a generic Kodi filename, not something only
        # this addon could have created - a DIFFERENT existing file here is
        # very likely someone's own unrelated keymap customization, not a
        # stale copy of this addon's own install. Never silently clobber
        # that - ask first, and make clear what will be lost.
        if not DIALOG.yesno(
            'Hisense blue button',
            '%s already exists with different content - this looks like your own '
            'keymap customization, not a previous install of this addon.\n\n'
            'Overwrite it with this addon\'s blue-button-to-ContextMenu remap? '
            '(Your current file will be lost - back it up first if unsure.)' % TARGET_KEYMAP
        ):
            return
    else:
        if not DIALOG.yesno(
            'Hisense blue button',
            'This will install %s, remapping the blue button on a Hisense TV remote '
            '(received over HDMI-CEC) to open Kodi\'s ContextMenu, since the TV\'s own '
            'Menu button doesn\'t pass through CEC on this hardware.\n\n'
            'This is a GLOBAL keymap change - it affects the blue button everywhere in '
            'Kodi, not just this repo\'s addons. Continue?' % TARGET_KEYMAP
        ):
            return

    if not os.path.isdir(TARGET_DIR):
        xbmcvfs.mkdirs(TARGET_DIR)
    shutil.copy2(BUNDLED_KEYMAP, TARGET_KEYMAP)

    xbmc.log('[hisenseblue] installed %s' % TARGET_KEYMAP, xbmc.LOGINFO)
    DIALOG.ok('Hisense blue button', 'Installed. Restart Kodi for it to take effect.')


if __name__ == '__main__':
    main()
