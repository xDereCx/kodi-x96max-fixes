import json

import xbmc
import xbmcaddon
import xbmcgui

import migration
import service
from resources.lib.utils import housekeeper

ADDON = xbmcaddon.Addon()
ADDONNAME = ADDON.getAddonInfo('name')
ADDONICON = ADDON.getAddonInfo('icon')

CONFLICTING_ADDON_ID = 'script.timers'


def disable_conflicting_addon() -> None:
    # The original (unfixed) addon and this fork can't both run as the
    # timers service - whichever Kodi picks second silently loses. If the
    # original is installed and enabled, disable it automatically instead
    # of leaving the user to discover and resolve the conflict themselves.
    # Same pattern as this repo's CU LRC Lyrics fork.
    try:
        req = json.dumps({
            'jsonrpc': '2.0', 'id': 1, 'method': 'Addons.GetAddonDetails',
            'params': {'addonid': CONFLICTING_ADDON_ID, 'properties': ['enabled']}
        })
        resp = json.loads(xbmc.executeJSONRPC(req))
        addon = resp.get('result', {}).get('addon')
        if not addon or not addon.get('enabled'):
            return
        xbmc.executeJSONRPC(json.dumps({
            'jsonrpc': '2.0', 'id': 1, 'method': 'Addons.SetAddonEnabled',
            'params': {'addonid': CONFLICTING_ADDON_ID, 'enabled': False}
        }))
        xbmc.log('[script.xderecx.timers] disabled conflicting %s (both can\'t run as the timers service)' % CONFLICTING_ADDON_ID, xbmc.LOGINFO)
        xbmcgui.Dialog().notification(
            ADDONNAME, 'Disabled original Timers addon (conflicts with this fork)',
            icon=ADDONICON, time=5000, sound=False)
    except Exception as e:
        # most common case: script.timers simply isn't installed, which
        # GetAddonDetails reports as a JSON-RPC error, not an empty result -
        # nothing to do either way
        xbmc.log('[script.xderecx.timers] conflicting-addon check skipped: %s' % e, xbmc.LOGDEBUG)


if __name__ == "__main__":

    disable_conflicting_addon()
    migration.migrate()
    housekeeper.cleanup_outdated_timers()
    service.run()
