import os
import re
import shutil

import xbmc
import xbmcvfs
import xbmcgui
import xbmcaddon

ADDON = xbmcaddon.Addon()
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))

SYSTEM_ADDONS_DIR = '/usr/share/kodi/addons'
STORAGE_ADDONS_DIR = '/storage/.kodi/addons'

RESTART_NEEDED_MARKER = os.path.join(PROFILE, 'restart_needed')


def log(msg):
    xbmc.log('[AddonRepair] %s' % msg, xbmc.LOGINFO)


def addon_version(xml_path, addon_id):
    # Must anchor on the <addon id="..."> root tag's own version attribute -
    # a naive "first version=\"...\" in the file" regex instead matches the
    # XML declaration itself (<?xml version="1.0"?>) and silently reports
    # "1.0" for every single addon, no matter its real version. Confirmed
    # live 2026-10-19 debugging this exact bug on box oco before finding it.
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            content = f.read()
        m = re.search(r'<addon\s+id="%s"[^>]*\bversion="([^"]+)"' % re.escape(addon_id), content)
        return m.group(1) if m else None
    except Exception as e:
        log('could not read %s: %s' % (xml_path, e))
        return None


def version_tuple(v):
    parts = []
    for p in re.split(r'[.\-+]', v):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def find_stale():
    """Return [(addon_id, storage_version, system_version), ...] for every
    addon id that is a genuine bundled system addon (has a folder directly
    under /usr/share/kodi/addons) AND also has an older local copy sitting
    in /storage/.kodi/addons. Deliberately narrow: an id with no local copy
    at all (the normal case for ~40 of ~45 system addons) or a local copy
    that's equal or newer is left completely alone."""
    if not os.path.isdir(SYSTEM_ADDONS_DIR):
        log('no %s on this platform, nothing to do' % SYSTEM_ADDONS_DIR)
        return []

    try:
        system_ids = os.listdir(SYSTEM_ADDONS_DIR)
    except Exception as e:
        log('could not list %s: %s' % (SYSTEM_ADDONS_DIR, e))
        return []

    stale = []
    for addon_id in system_ids:
        system_xml = os.path.join(SYSTEM_ADDONS_DIR, addon_id, 'addon.xml')
        storage_xml = os.path.join(STORAGE_ADDONS_DIR, addon_id, 'addon.xml')
        if not os.path.isfile(system_xml) or not os.path.isfile(storage_xml):
            continue
        tv = addon_version(system_xml, addon_id)
        sv = addon_version(storage_xml, addon_id)
        if not tv or not sv:
            continue
        if version_tuple(sv) < version_tuple(tv):
            stale.append((addon_id, sv, tv))
    return stale


def repair():
    stale = find_stale()
    for addon_id, sv, tv in stale:
        storage_dir = os.path.join(STORAGE_ADDONS_DIR, addon_id)
        log('%s is stale (storage=%s, system=%s) - removing %s' % (addon_id, sv, tv, storage_dir))
        try:
            shutil.rmtree(storage_dir)
        except Exception as e:
            log('could not remove %s: %s' % (storage_dir, e))
    return stale


def main():
    log('checking for stale local copies of bundled system addons')
    if not xbmcvfs.exists(PROFILE):
        xbmcvfs.mkdirs(PROFILE)

    fixed = repair()
    if fixed:
        summary = ', '.join('%s (%s -> %s)' % f for f in fixed)
        log('repaired: %s - a Kodi restart is required for this to take effect' % summary)
        f = xbmcvfs.File(RESTART_NEEDED_MARKER, 'w')
        f.write(b'1')
        f.close()
        xbmcgui.Dialog().notification(
            'DC Addon Repair',
            'Fixed stale addon(s): %s. Restart Kodi to apply.' % ', '.join(a for a, _, _ in fixed),
            icon=xbmcgui.NOTIFICATION_INFO, time=10000, sound=False)
    elif xbmcvfs.exists(RESTART_NEEDED_MARKER):
        # a previous start found and removed a stale copy; nothing stale is
        # left now, which confirms the restart already happened and the fix
        # actually took effect - clear the marker so we stay quiet from now on
        xbmcvfs.delete(RESTART_NEEDED_MARKER)
        log('previous repair confirmed applied after restart, marker cleared')
    log('check complete, nothing stale found' if not fixed else 'check complete')


if __name__ == '__main__':
    main()
