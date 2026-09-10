import xbmcgui
from lib import core

DIALOG = xbmcgui.Dialog()


def main():
    original_path = core.find_original_lyrics_addon()
    if original_path and DIALOG.yesno(
        'Aeon Nox 5 Skin Fixes',
        'The original %s addon is installed alongside script.cu.lrclyrics.fixed. '
        'Only one is needed - remove the original now?' % core.ORIGINAL_LYRICS_ADDON_ID
    ):
        core.remove_original_lyrics_addon(original_path)
        DIALOG.notification('Aeon Nox 5 Skin Fixes', 'Removed original %s' % core.ORIGINAL_LYRICS_ADDON_ID, icon=xbmcgui.NOTIFICATION_INFO)

    skin_roots = core.find_skin_roots()
    if not skin_roots:
        DIALOG.ok('Aeon Nox 5 Skin Fixes', 'skin.aeon.nox.5 is not installed. Install/enable it first, then run this again.')
        return

    pending = core.find_pending(skin_roots)
    if not pending:
        DIALOG.notification('Aeon Nox 5 Skin Fixes', 'Already applied, nothing to do', icon=xbmcgui.NOTIFICATION_INFO)
        return

    listing = '\n'.join('- %s' % rel_path for _, _, _, rel_path, _ in pending)
    if not DIALOG.yesno(
        'Aeon Nox 5 Skin Fixes',
        'This will patch/install %d skin file(s):\n%s\n\nA backup (.bak) of each original is kept if one does not already exist (new files this addon introduces need no backup). Continue?' % (len(pending), listing)
    ):
        return

    core.apply_pending(pending)
    DIALOG.ok('Aeon Nox 5 Skin Fixes', 'Applied %d patch(es). Restart Kodi for it to take effect.' % len(pending))


if __name__ == '__main__':
    main()
