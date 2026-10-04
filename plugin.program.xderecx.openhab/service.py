# -*- coding: utf-8 -*-
"""Background service: every N minutes draws the house status picture and, in Aeon Nox 5, sets it as the
background (Custom<N>HomeItem.MultiFanart) of the add-on's main menu item. A new file name each time, so Kodi's
texture cache can't show an old picture; older pictures are deleted."""
import glob
import os
import sys
import time

import xbmc
import xbmcaddon
import xbmcvfs

ADDON = xbmcaddon.Addon()
PATH = ADDON.getAddonInfo('path')
sys.path.insert(0, os.path.join(PATH, 'resources', 'lib'))
import openhab as oh  # noqa: E402
import statusimage  # noqa: E402
from model import Model  # noqa: E402

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


def update(assets, outdir):
    if not setting_on('bg_enable'):
        return
    slot = an5_slot() if xbmc.getSkinDir() == AN5 else None
    if not slot:
        return
    token = ADDON.getSetting('token')
    if not token:
        return
    try:
        c = oh.OpenHAB(ADDON.getSetting('url') or 'http://localhost:8080', token,
                       int(float(ADDON.getSetting('timeout') or 8)))
        items = c.items()
    except Exception as err:  # openHAB down: keep the last picture
        log('status picture: openHAB not reachable: %s' % err, xbmc.LOGWARNING)
        return
    m = Model(items)
    path = os.path.join(outdir, 'status-%s.png' % time.strftime('%Y%m%d-%H%M%S'))
    try:
        secs = statusimage.render(m, path, {'title': S(32010), 'ok': S(32011), 'updated': S(32042)}, assets)
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


def main():
    monitor = xbmc.Monitor()
    outdir = xbmcvfs.translatePath('special://profile/addon_data/plugin.program.xderecx.openhab/background')
    os.makedirs(outdir, exist_ok=True)
    assets = statusimage.Assets(os.path.join(PATH, 'resources', 'media'))
    if monitor.waitForAbort(20):   # let Kodi and the skin start first
        return
    while not monitor.abortRequested():
        update(assets, outdir)
        try:
            minutes = max(1, int(float(ADDON.getSetting('bg_interval') or 5)))
        except ValueError:
            minutes = 5
        if monitor.waitForAbort(minutes * 60):
            break


if __name__ == '__main__':
    main()
