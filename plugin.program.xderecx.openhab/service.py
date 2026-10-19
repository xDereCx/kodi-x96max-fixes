# -*- coding: utf-8 -*-
"""Background service: every N minutes draws the house status picture and, in Aeon Nox 5, sets it as the
background (Custom<N>HomeItem.MultiFanart) of the add-on's main menu item. A new file name each time, so Kodi's
texture cache can't show an old picture; older pictures are deleted."""
import glob
import importlib
import os
import re
import sys
import time

import xbmc
import xbmcaddon
import xbmcvfs

ADDON = xbmcaddon.Addon()
PATH = ADDON.getAddonInfo('path')
sys.path.insert(0, os.path.join(PATH, 'resources', 'lib'))
import canvas  # noqa: E402
import floorplan  # noqa: E402
import model  # noqa: E402
import openhab as oh  # noqa: E402
import statusimage  # noqa: E402

# reloaded in this order when the add-on is updated while the service keeps running (dependencies first)
LIBS = (canvas, oh, model, floorplan, statusimage)

AN5 = 'skin.aeon.nox.5'
MENU_PATH = 'RunAddon(plugin.program.xderecx.openhab)'


def log(msg, level=xbmc.LOGINFO):
    xbmc.log('[plugin.program.xderecx.openhab] ' + msg, level)


def S(sid):
    return ADDON.getLocalizedString(sid)


def an5_slot():
    for n in range(1, 7):
        if xbmc.getInfoLabel('Skin.String(Custom%dHomeItem.Path)' % n) == MENU_PATH:
            return n
    return None


def setting_on(key, default=True):
    v = ADDON.getSetting(key)
    return default if v == '' else v.lower() == 'true'


_last_skip = [None]


def skip(reason):
    """Logs why no picture is drawn, once per reason (not every interval)."""
    if _last_skip[0] != reason:
        _last_skip[0] = reason
        log('status picture not drawn: ' + reason)


def update(assets, outdir):
    if not setting_on('bg_enable'):
        return skip('switched off in the add-on settings')
    if xbmc.getSkinDir() != AN5:
        return skip('skin is %s, the background works in Aeon Nox 5 only' % xbmc.getSkinDir())
    slot = an5_slot()
    if not slot:
        return skip('the add-on is not in the Aeon Nox 5 main menu (open the add-on - Add to the main menu)')
    token = ADDON.getSetting('token')
    if not token:
        return skip('no API token in the add-on settings')
    _last_skip[0] = None
    try:
        c = oh.OpenHAB(ADDON.getSetting('url') or 'http://localhost:8080', token,
                       int(float(ADDON.getSetting('timeout') or 8)))
        items = c.items()
    except Exception as err:  # openHAB down: keep the last picture
        log('status picture: openHAB not reachable: %s' % err, xbmc.LOGWARNING)
        return
    m = model.Model(items)
    path = os.path.join(outdir, 'status-%s.png' % time.strftime('%Y%m%d-%H%M%S'))
    area = {'0': 'full', '1': 'top', '2': 'left'}.get(ADDON.getSetting('bg_area'), 'top')
    try:
        secs = statusimage.render(m, path, {'title': S(32010), 'ok': S(32011), 'updated': S(32042)}, assets, area)
    except Exception as err:
        log('status picture failed: %s' % err, xbmc.LOGERROR)
        return
    xbmc.executebuiltin('Skin.SetString(Custom%dHomeItem.MultiFanart,%s)' % (slot, path))
    for old in glob.glob(os.path.join(outdir, 'status-*.png')):
        if old != path:
            try:
                os.remove(old)
            except OSError:
                pass
    log('status picture %s drawn in %.1f s' % (os.path.basename(path), secs))


def disk_version():
    """Version in addon.xml on disk (the running code may be older: Kodi does not always restart a service
    when it updates its add-on - seen 2026-10-05, a box kept drawing with 2.6.0 code after the update to 2.6.3)."""
    try:
        with open(os.path.join(PATH, 'addon.xml'), encoding='utf-8') as f:
            m = re.search(r'<addon\b[^>]*\bversion="([^"]+)"', f.read())
        return m.group(1) if m else None
    except OSError:
        return None


def load_assets():
    # Kodi's default weather icon pack (weather.com codes 0-47), for metadata weather_icon
    wdir = xbmcvfs.translatePath('special://xbmc/addons/resource.images.weathericons.default/resources')
    return statusimage.Assets(os.path.join(PATH, 'resources', 'media'), wdir if os.path.isdir(wdir) else None)


def main():
    loaded = disk_version() or ADDON.getAddonInfo('version')
    log('background service %s started' % loaded)
    monitor = xbmc.Monitor()
    outdir = xbmcvfs.translatePath('special://profile/addon_data/plugin.program.xderecx.openhab/background')
    os.makedirs(outdir, exist_ok=True)
    assets = load_assets()
    if monitor.waitForAbort(20):   # let Kodi and the skin start first
        return
    while not monitor.abortRequested():
        now = disk_version()
        if now and now != loaded:   # add-on updated under the running service: take the new drawing code
            try:
                for lib in LIBS:
                    importlib.reload(lib)
                assets = load_assets()
                log('add-on updated %s -> %s: drawing code reloaded' % (loaded, now))
                loaded = now
            except Exception as err:
                log('reload after update to %s failed: %s' % (now, err), xbmc.LOGERROR)
                loaded = now   # do not retry every interval; a Kodi restart loads it
        update(assets, outdir)
        try:
            minutes = max(1, int(float(ADDON.getSetting('bg_interval') or 5)))
        except ValueError:
            minutes = 5
        if monitor.waitForAbort(minutes * 60):
            break


if __name__ == '__main__':
    main()
