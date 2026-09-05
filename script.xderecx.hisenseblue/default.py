import json
import os
import sys
import shutil
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
BUNDLED_KEYMAP = os.path.join(ADDON_PATH, 'resources', 'files', 'custom_remote.xml')

TARGET_DIR = xbmcvfs.translatePath('special://userdata/keymaps')
TARGET_KEYMAP = os.path.join(TARGET_DIR, 'custom_remote.xml')
BACKUP_KEYMAP = TARGET_KEYMAP + '.hisenseblue-backup'

# Kodi has no uninstall hook for script add-ons - clicking "Uninstall" in
# the add-on browser just deletes this add-on's own folder, it never runs
# any of our code. So "restore the original keymap" can only ever be this
# separate, explicit action (run it BEFORE uninstalling, same as
# fontinstall.py's install/remove pair for decorative fonts) - there is no
# way to hook Kodi's own uninstall button for this.
STATE_FILE = os.path.join(PROFILE, 'state.json')

DIALOG = xbmcgui.Dialog()


def read(path):
    with open(path, 'rb') as f:
        return f.read()


def _load_state():
    if not os.path.isfile(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    if not os.path.isdir(PROFILE):
        xbmcvfs.mkdirs(PROFILE)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f)


def install():
    if not os.path.isfile(BUNDLED_KEYMAP):
        DIALOG.notification('Hisense blue button', 'Bundled file missing, reinstall this addon', icon=xbmcgui.NOTIFICATION_ERROR)
        return

    bundled = read(BUNDLED_KEYMAP)
    state = _load_state()

    if state.get('installed'):
        DIALOG.notification('Hisense blue button', 'Already installed, nothing to do', icon=xbmcgui.NOTIFICATION_INFO)
        return

    if os.path.isfile(TARGET_KEYMAP):
        current = read(TARGET_KEYMAP)
        if current == bundled:
            # matches our own file already (e.g. state.json was lost/cleared
            # but the actual keymap survived) - nothing to back up, just
            # record that we consider it installed from here on
            state['installed'] = True
            state['had_backup'] = False
            _save_state(state)
            DIALOG.notification('Hisense blue button', 'Already installed, nothing to do', icon=xbmcgui.NOTIFICATION_INFO)
            return
        # custom_remote.xml is a generic Kodi filename, not something only
        # this addon could have created - a DIFFERENT existing file here is
        # very likely someone's own unrelated keymap customization. Never
        # silently clobber that - ask first, and back it up so "Restore
        # original keymap" can bring it back later.
        if not DIALOG.yesno(
            'Hisense blue button',
            '%s already exists with different content - this looks like your own '
            'keymap customization, not a previous install of this addon.\n\n'
            'A backup will be kept (restorable via this addon\'s "Restore original '
            'keymap" action). Overwrite it with this addon\'s blue-button-to-ContextMenu '
            'remap?' % TARGET_KEYMAP
        ):
            return
        shutil.copy2(TARGET_KEYMAP, BACKUP_KEYMAP)
        had_backup = True
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
        had_backup = False

    if not os.path.isdir(TARGET_DIR):
        xbmcvfs.mkdirs(TARGET_DIR)
    shutil.copy2(BUNDLED_KEYMAP, TARGET_KEYMAP)

    state['installed'] = True
    state['had_backup'] = had_backup
    _save_state(state)

    xbmc.log('[hisenseblue] installed %s' % TARGET_KEYMAP, xbmc.LOGINFO)
    DIALOG.ok('Hisense blue button', 'Installed. Restart Kodi for it to take effect.')


def remove():
    state = _load_state()
    if not state.get('installed'):
        DIALOG.notification('Hisense blue button', 'Not installed by this addon, nothing to do', icon=xbmcgui.NOTIFICATION_INFO)
        return

    if state.get('had_backup') and os.path.isfile(BACKUP_KEYMAP):
        shutil.copy2(BACKUP_KEYMAP, TARGET_KEYMAP)
        os.remove(BACKUP_KEYMAP)
        msg = 'Restored your original %s from backup.' % TARGET_KEYMAP
    elif os.path.isfile(TARGET_KEYMAP):
        # there was no file here before we installed - restoring "the
        # original" means removing it entirely, back to that same absence
        os.remove(TARGET_KEYMAP)
        msg = 'Removed %s (there was no file here before this addon installed it).' % TARGET_KEYMAP
    else:
        msg = '%s was already gone.' % TARGET_KEYMAP

    state['installed'] = False
    state['had_backup'] = False
    _save_state(state)

    xbmc.log('[hisenseblue] removed %s' % TARGET_KEYMAP, xbmc.LOGINFO)
    DIALOG.ok('Hisense blue button', msg + ' Restart Kodi for it to take effect.')


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'remove':
        remove()
    else:
        install()
