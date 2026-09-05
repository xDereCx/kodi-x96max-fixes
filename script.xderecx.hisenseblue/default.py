import os
import sys
import xml.etree.ElementTree as ET
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDONNAME = ADDON.getAddonInfo('name')
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
BUNDLED_KEYMAP = os.path.join(ADDON_PATH, 'resources', 'files', 'custom_remote.xml')

TARGET_DIR = xbmcvfs.translatePath('special://userdata/keymaps')
TARGET_KEYMAP = os.path.join(TARGET_DIR, 'custom_remote.xml')

# the exact value this addon's own remap sets - used both to add it
# (install) and to recognize it's specifically OUR entry, not the user's
# own unrelated remap of the same button, when removing (remove)
BLUE_VALUE = 'ContextMenu'

# only used by the boot-time auto-check (see bottom) - remembers that the
# user was already asked once, so a "no" or a dismissed dialog doesn't
# nag again on every single Kodi start. Not used by the manual
# install()/remove() settings actions, which always run when triggered.
ASKED_MARKER = os.path.join(PROFILE, 'asked_at_boot')

DIALOG = xbmcgui.Dialog()


def _sections():
    # the list of window-context section names this addon's own bundled
    # keymap covers - read from the bundled file itself rather than
    # hardcoded, so resources/files/custom_remote.xml stays the single
    # source of truth
    tree = ET.parse(BUNDLED_KEYMAP)
    return [child.tag for child in tree.getroot()]


def _fully_installed():
    if not os.path.isfile(TARGET_KEYMAP):
        return False
    try:
        tree = ET.parse(TARGET_KEYMAP)
    except ET.ParseError:
        return False
    root = tree.getroot()
    for name in _sections():
        section = root.find(name)
        if section is None:
            return False
        remote = section.find('remote')
        if remote is None:
            return False
        blue = remote.find('blue')
        if blue is None or (blue.text or '').strip() != BLUE_VALUE:
            return False
    return True


def install():
    if not os.path.isfile(BUNDLED_KEYMAP):
        DIALOG.notification(ADDONNAME, 'Bundled file missing, reinstall this addon', icon=xbmcgui.NOTIFICATION_ERROR)
        return False

    if _fully_installed():
        DIALOG.notification(ADDONNAME, 'Already installed, nothing to do', icon=xbmcgui.NOTIFICATION_INFO)
        return False

    if not os.path.isdir(TARGET_DIR):
        xbmcvfs.mkdirs(TARGET_DIR)

    if not os.path.isfile(TARGET_KEYMAP):
        if not DIALOG.yesno(
            ADDONNAME,
            'This will install %s, remapping the blue button on a Hisense TV remote '
            '(received over HDMI-CEC) to open Kodi\'s ContextMenu, since the TV\'s own '
            'Menu button doesn\'t pass through CEC on this hardware.\n\n'
            'This is a GLOBAL keymap change - it affects the blue button everywhere in '
            'Kodi, not just this repo\'s addons. Continue?' % TARGET_KEYMAP
        ):
            return False
        import shutil
        shutil.copy2(BUNDLED_KEYMAP, TARGET_KEYMAP)
        xbmc.log('[hisenseblue] installed %s' % TARGET_KEYMAP, xbmc.LOGINFO)
        return True

    # custom_remote.xml already exists - it's a generic Kodi filename that
    # could hold the user's own unrelated remaps (their own sections,
    # their own buttons, even other sections we don't touch at all).
    # MERGE our blue-button entry into it section by section instead of
    # overwriting the whole file, so anything already there survives.
    try:
        tree = ET.parse(TARGET_KEYMAP)
    except ET.ParseError as e:
        DIALOG.ok(ADDONNAME, 'Could not parse existing %s (%s) - fix or remove it manually first.' % (TARGET_KEYMAP, e))
        return False
    root = tree.getroot()

    conflicts = []
    for name in _sections():
        section = root.find(name)
        if section is not None:
            remote = section.find('remote')
            if remote is not None:
                blue = remote.find('blue')
                if blue is not None and (blue.text or '').strip() and (blue.text or '').strip() != BLUE_VALUE:
                    conflicts.append('%s: blue is already "%s"' % (name, blue.text.strip()))

    if conflicts:
        if not DIALOG.yesno(
            ADDONNAME,
            '%s already remaps blue to something else in %d place(s):\n%s\n\n'
            'Overwrite those with ContextMenu? (Everything else in the file is left untouched.)'
            % (TARGET_KEYMAP, len(conflicts), '\n'.join(conflicts))
        ):
            return False
    else:
        if not DIALOG.yesno(
            ADDONNAME,
            '%s already exists - this addon\'s blue-to-ContextMenu remap will be merged '
            'into it (nothing else in the file is touched). Continue?' % TARGET_KEYMAP
        ):
            return False

    for name in _sections():
        section = root.find(name)
        if section is None:
            section = ET.SubElement(root, name)
        remote = section.find('remote')
        if remote is None:
            remote = ET.SubElement(section, 'remote')
        blue = remote.find('blue')
        if blue is None:
            blue = ET.SubElement(remote, 'blue')
        blue.text = BLUE_VALUE

    ET.indent(tree, space='  ')
    tree.write(TARGET_KEYMAP, encoding='UTF-8', xml_declaration=False)

    xbmc.log('[hisenseblue] merged blue remap into %s' % TARGET_KEYMAP, xbmc.LOGINFO)
    return True


def remove():
    # Kodi has no uninstall hook for script add-ons - clicking Uninstall in
    # the add-on browser just deletes this add-on's own folder, it never
    # runs any of our code, so this is the only way to actually undo the
    # keymap change. Strips out exactly the <blue>ContextMenu</blue>
    # entries THIS addon's own sections added, structurally - not a
    # file-level backup/restore - so it works correctly no matter whether
    # the file was: untouched since install, had its own content before
    # install, or was further edited by the user (their own sections,
    # their own remaps, even other buttons in the same sections this addon
    # touched) at any point afterward. Only ever removes a <blue> entry
    # whose value is still exactly "ContextMenu" - if the user has since
    # deliberately changed it to something else, that's their own edit and
    # is left alone.
    if not os.path.isfile(TARGET_KEYMAP):
        DIALOG.notification(ADDONNAME, 'Not installed, nothing to do', icon=xbmcgui.NOTIFICATION_INFO)
        return

    try:
        tree = ET.parse(TARGET_KEYMAP)
    except ET.ParseError as e:
        DIALOG.ok(ADDONNAME, 'Could not parse %s (%s) - fix or remove it manually.' % (TARGET_KEYMAP, e))
        return
    root = tree.getroot()

    removed = 0
    for name in _sections():
        section = root.find(name)
        if section is None:
            continue
        remote = section.find('remote')
        if remote is None:
            continue
        blue = remote.find('blue')
        if blue is not None and (blue.text or '').strip() == BLUE_VALUE:
            remote.remove(blue)
            removed += 1
        if len(remote) == 0 and not (remote.text or '').strip():
            section.remove(remote)
        if len(section) == 0 and not (section.text or '').strip():
            root.remove(section)

    if removed == 0:
        DIALOG.notification(ADDONNAME, 'No matching blue remap found, nothing to do', icon=xbmcgui.NOTIFICATION_INFO)
        return

    if len(root) == 0:
        os.remove(TARGET_KEYMAP)
        msg = 'Removed %s entirely (nothing else was left in it).' % TARGET_KEYMAP
    else:
        ET.indent(tree, space='  ')
        tree.write(TARGET_KEYMAP, encoding='UTF-8', xml_declaration=False)
        msg = 'Removed this addon\'s blue remap (%d section(s)) from %s - everything else in it was left untouched.' % (removed, TARGET_KEYMAP)

    xbmc.log('[hisenseblue] ' + msg, xbmc.LOGINFO)
    DIALOG.ok(ADDONNAME, msg + ' Restart Kodi for it to take effect.')


def _offer_restart():
    if DIALOG.yesno(ADDONNAME, 'Restart Kodi now for the new keymap to take effect?'):
        xbmc.executebuiltin('RestartApp')
    else:
        DIALOG.notification(ADDONNAME, 'Remember to restart Kodi later for it to take effect', icon=xbmcgui.NOTIFICATION_INFO, time=6000)


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'remove':
        remove()
    elif sys.argv == ['']:
        # boot-time auto-check (this addon also declares xbmc.service, see
        # addon.xml) - offers install once per box instead of requiring
        # the user to already know to go find this under Program add-ons.
        # Only ever asks once (tracked via ASKED_MARKER) even if the
        # answer was "no" - a install()/remove() run from the settings
        # screen is unaffected by this and always runs when triggered.
        if not _fully_installed() and not os.path.isfile(ASKED_MARKER):
            if not os.path.isdir(PROFILE):
                xbmcvfs.mkdirs(PROFILE)
            with open(ASKED_MARKER, 'w') as f:
                f.write('1')
            if install():
                _offer_restart()
    else:
        if install():
            DIALOG.ok(ADDONNAME, 'Installed. Restart Kodi for it to take effect.')
