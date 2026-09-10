import os
import xbmc
import xbmcgui
from lib import core

# Runs automatically on every Kodi startup (xbmc.service, start="startup"),
# unlike default.py which only runs when launched manually from Program
# Add-ons. Applies silently with no confirmation dialogs - every patch here
# is idempotent (a no-op once already applied) and keeps a .bak of anything
# it overwrites, so there is nothing destructive to confirm. This is what
# makes installing this addon on a fresh Aeon Nox 5 box "just work" with no
# separate manual step.

original_path = core.find_original_lyrics_addon()
if original_path:
    core.remove_original_lyrics_addon(original_path)
    xbmc.log('[aeonnox5skinfix] service: auto-removed conflicting %s' % core.ORIGINAL_LYRICS_ADDON_ID, xbmc.LOGINFO)

skin_roots = core.find_skin_roots()
if skin_roots:
    pending = core.find_pending(skin_roots)
    if pending:
        core.apply_pending(pending)
        xbmc.log('[aeonnox5skinfix] service: auto-applied %d patch(es) on startup' % len(pending), xbmc.LOGINFO)

        # Wait for the GUI to actually be up before showing a modal dialog -
        # this runs very early in Kodi's own startup sequence (xbmc.service,
        # start="startup"), and a yesno this early has been flaky/silently
        # skipped on this box before. 3s is the same delay idiom used
        # elsewhere in this project for the same reason.
        if not xbmc.Monitor().waitForAbort(3):
            if xbmcgui.Dialog().yesno(
                'Aeon Nox 5 Skin Fixes',
                'Applied %d fix(es). Restart Kodi now for them to take effect?' % len(pending)
            ):
                # No native "restart Kodi" builtin exists - Quit() only
                # relies on the platform service manager auto-relaunching it,
                # which is not guaranteed. systemctl is confirmed reliable on
                # this CoreELEC box. Backgrounded (&) so the request reaches
                # systemd before this same Kodi process gets killed by it.
                os.system('systemctl restart kodi &')
