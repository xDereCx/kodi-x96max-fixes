import os
import sys
import xml.etree.ElementTree as ET
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
BUNDLED_KEYMAP = os.path.join(ADDON_PATH, 'resources', 'files', 'custom_remote.xml')

TARGET_DIR = xbmcvfs.translatePath('special://userdata/keymaps')
TARGET_KEYMAP = os.path.join(TARGET_DIR, 'custom_remote.xml')

# the exact value this addon's own remap sets - used both to add it
# (install) and to recognize it's specifically OUR entry, not the user's
# own unrelated remap of the same button, when removing (remove)
BLUE_VALUE = 'ContextMenu'

DIALOG = xbmcgui.Dialog()


def _sections():
    # the list of window-context section names this addon's own bundled
    # keymap covers - read from the bundled file itself rather than
    # hardcoded, so resources/files/custom_remote.xml stays the single
    # source of truth
    tree = ET.parse(BUNDLED_KEYMAP)
    return [child.tag for child in tree.getroot()]


def install():
    if not os.path.isfile(BUNDLED_KEYMAP):
        DIALOG.notification('Hisense blue button', 'Bundled file missing, reinstall this addon', icon=xbmcgui.NOTIFICATION_ERROR)
        return

    if not os.path.isdir(TARGET_DIR):
        xbmcvfs.mkdirs(TARGET_DIR)

    if not os.path.isfile(TARGET_KEYMAP):
        if not DIALOG.yesno(
            'Hisense blue button',
            'This will install %s, remapping the blue button on a Hisense TV remote '
            '(received over HDMI-CEC) to open Kodi\'s ContextMenu, since the TV\'s own '
            'Menu button doesn\'t pass through CEC on this hardware.\n\n'
            'This is a GLOBAL keymap change - it affects the blue button everywhere in '
            'Kodi, not just this repo\'s addons. Continue?' % TARGET_KEYMAP
        ):
            return
        import shutil
        shutil.copy2(BUNDLED_KEYMAP, TARGET_KEYMAP)
        xbmc.log('[hisenseblue] installed %s' % TARGET_KEYMAP, xbmc.LOGINFO)
        DIALOG.ok('Hisense blue button', 'Installed. Restart Kodi for it to take effect.')
        return

    # custom_remote.xml already exists - it's a generic Kodi filename that
    # could hold the user's own unrelated remaps (their own sections,
    # their own buttons, even other sections we don't touch at all).
    # MERGE our blue-button entry into it section by section instead of
    # overwriting the whole file, so anything already there survives.
    try:
        tree = ET.parse(TARGET_KEYMAP)
    except ET.ParseError as e:
        DIALOG.ok('Hisense blue button', 'Could not parse existing %s (%s) - fix or remove it manually first.' % (TARGET_KEYMAP, e))
        return
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
            'Hisense blue button',
            '%s already remaps blue to something else in %d place(s):\n%s\n\n'
            'Overwrite those with ContextMenu? (Everything else in the file is left untouched.)'
            % (TARGET_KEYMAP, len(conflicts), '\n'.join(conflicts))
        ):
            return
    else:
        if not DIALOG.yesno(
            'Hisense blue button',
            '%s already exists - this addon\'s blue-to-ContextMenu remap will be merged '
            'into it (nothing else in the file is touched). Continue?' % TARGET_KEYMAP
        ):
            return

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
    DIALOG.ok('Hisense blue button', 'Merged into your existing keymap. Restart Kodi for it to take effect.')


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
        DIALOG.notification('Hisense blue button', 'Not installed, nothing to do', icon=xbmcgui.NOTIFICATION_INFO)
        return

    try:
        tree = ET.parse(TARGET_KEYMAP)
    except ET.ParseError as e:
        DIALOG.ok('Hisense blue button', 'Could not parse %s (%s) - fix or remove it manually.' % (TARGET_KEYMAP, e))
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
        DIALOG.notification('Hisense blue button', 'No matching blue remap found, nothing to do', icon=xbmcgui.NOTIFICATION_INFO)
        return

    if len(root) == 0:
        os.remove(TARGET_KEYMAP)
        msg = 'Removed %s entirely (nothing else was left in it).' % TARGET_KEYMAP
    else:
        ET.indent(tree, space='  ')
        tree.write(TARGET_KEYMAP, encoding='UTF-8', xml_declaration=False)
        msg = 'Removed this addon\'s blue remap (%d section(s)) from %s - everything else in it was left untouched.' % (removed, TARGET_KEYMAP)

    xbmc.log('[hisenseblue] ' + msg, xbmc.LOGINFO)
    DIALOG.ok('Hisense blue button', msg + ' Restart Kodi for it to take effect.')


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'remove':
        remove()
    else:
        install()
