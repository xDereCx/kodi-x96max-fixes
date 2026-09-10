import json
import os
import shutil
import xbmc
import xbmcaddon
import xbmcvfs

# The companion lyrics addon this one is built to patch skin support for.
# Deliberately NOT declared as a <requires> import in addon.xml - Kodi treats
# that as a hard dependency and refuses to uninstall either addon while the
# other is installed (confirmed live 2026-09-10, in both uninstall orders).
# Installed via JSON-RPC instead, a soft "make sure it's there" step that
# still gets a fresh box fully working with zero manual steps, but leaves
# both addons independently, freely uninstallable through the Kodi GUI.
LYRICS_ADDON_ID = 'script.cu.lrclyrics.fixed'


def ensure_lyrics_addon_installed():
    try:
        xbmcaddon.Addon(LYRICS_ADDON_ID)
        return False
    except RuntimeError:
        pass
    req = json.dumps({
        'jsonrpc': '2.0', 'id': 1, 'method': 'Addons.InstallAddon',
        'params': {'addonid': LYRICS_ADDON_ID}
    })
    resp = json.loads(xbmc.executeJSONRPC(req))
    ok = resp.get('result') == 'OK'
    xbmc.log('[aeonnox5skinfix] service: install of %s via JSON-RPC %s' % (LYRICS_ADDON_ID, 'succeeded' if ok else 'failed: %s' % resp), xbmc.LOGINFO if ok else xbmc.LOGERROR)
    return ok

ADDON = xbmcaddon.Addon()
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
SKINFILE_DIR = os.path.join(ADDON_PATH, 'resources', 'skinfile')

# (bundled .dat filename, skin-relative path, one-line description shown in the confirm dialog)
PATCHES = [
    ('script-cu-lrclyrics-main.xml.dat', os.path.join('1080i', 'script-cu-lrclyrics-main.xml'),
     'hides the topbar.png dark band over lyrics text, adds the rotating-fanart background control'),
    ('MusicVisualisation.xml.dat', os.path.join('1080i', 'MusicVisualisation.xml'),
     'hides the static Player.Art(fanart) background so it cannot cover the rotating fanart image'),
    ('Font.xml.dat', os.path.join('1080i', 'Font.xml'),
     'fixes missing Slovak/Czech diacritics in 2 of 5 lyrics display fonts'),
    ('MusicOSD.xml.dat', os.path.join('1080i', 'MusicOSD.xml'),
     'fixes the OSD Lyrics button (control 703) calling the pre-fork original script.cu.lrclyrics instead of script.cu.lrclyrics.fixed - silently did nothing once only the fork was installed'),
]

# new files this addon introduces rather than patches - no original to
# back up, just installed/updated as-is if missing or out of date
NEW_FILES = [
    ('script-cu-lrclyrics-sync.xml.dat', os.path.join('1080i', 'script-cu-lrclyrics-sync.xml'),
     'dedicated wide sync-offset slider window, so it does not affect the shared DialogSlider.xml used for volume/seek/brightness'),
]

# Aeon Nox 5 keeps a second, independent copy of itself installed as its own
# addon (skin.aeon.nox.5.skinbase) purely so its own "reset skin to default"
# feature has a pristine copy to restore from. It is not just a backup file
# sitting inside the live skin's folder - Kodi can make it the active skin's
# source of truth again at any time, so every patch/new-file here must be
# kept in sync on BOTH copies or a skin reset silently reverts every fix.
SKIN_IDS = ['skin.aeon.nox.5', 'skin.aeon.nox.5.skinbase']

# The original, unrelated upstream addon (different addon id entirely) that
# script.cu.lrclyrics.fixed was forked from. Kodi's <requires> dependency
# system only ever adds addons, never removes unrelated ones, so if both this
# original and the fork end up installed side by side there's no error -
# whichever one Kodi's skin-resource lookup happens to prefer wins silently.
ORIGINAL_LYRICS_ADDON_ID = 'script.cu.lrclyrics'


def find_original_lyrics_addon():
    try:
        original = xbmcaddon.Addon(ORIGINAL_LYRICS_ADDON_ID)
    except RuntimeError:
        return None
    return xbmcvfs.translatePath(original.getAddonInfo('path'))


def remove_original_lyrics_addon(original_path):
    shutil.rmtree(original_path, ignore_errors=True)
    xbmc.log('[aeonnox5skinfix] removed conflicting %s at %s' % (ORIGINAL_LYRICS_ADDON_ID, original_path), xbmc.LOGINFO)


def find_skin_roots():
    roots = []
    for skin_id in SKIN_IDS:
        try:
            skin_addon = xbmcaddon.Addon(skin_id)
        except RuntimeError:
            continue
        roots.append((skin_id, xbmcvfs.translatePath(skin_addon.getAddonInfo('path'))))
    return roots


def find_pending(skin_roots):
    pending = []
    for skin_id, skin_root in skin_roots:
        for bundled_name, rel_path, desc in PATCHES:
            bundled = os.path.join(SKINFILE_DIR, bundled_name)
            target = os.path.join(skin_root, rel_path)
            if not os.path.isfile(bundled):
                xbmc.log('[aeonnox5skinfix] bundled file missing, reinstall this addon: %s' % bundled, xbmc.LOGERROR)
                continue
            if not os.path.isfile(target):
                xbmc.log('[aeonnox5skinfix] expected skin file not found, skin layout may have changed: %s' % target, xbmc.LOGWARNING)
                continue
            with open(bundled, 'rb') as f:
                fixed = f.read()
            with open(target, 'rb') as f:
                current = f.read()
            if current != fixed:
                pending.append(('patch', bundled, target, '%s: %s' % (skin_id, rel_path), desc))

        for bundled_name, rel_path, desc in NEW_FILES:
            bundled = os.path.join(SKINFILE_DIR, bundled_name)
            target = os.path.join(skin_root, rel_path)
            if not os.path.isfile(bundled):
                xbmc.log('[aeonnox5skinfix] bundled file missing, reinstall this addon: %s' % bundled, xbmc.LOGERROR)
                continue
            with open(bundled, 'rb') as f:
                fixed = f.read()
            current = None
            if os.path.isfile(target):
                with open(target, 'rb') as f:
                    current = f.read()
            if current != fixed:
                pending.append(('new', bundled, target, '%s: %s' % (skin_id, rel_path), desc))
    return pending


def apply_pending(pending):
    for kind, bundled, target, rel_path, desc in pending:
        if kind == 'patch':
            backup = target + '.bak'
            if not os.path.isfile(backup):
                shutil.copy2(target, backup)
        shutil.copy2(bundled, target)
        xbmc.log('[aeonnox5skinfix] %s %s (%s)' % ('patched' if kind == 'patch' else 'installed', target, desc), xbmc.LOGINFO)
