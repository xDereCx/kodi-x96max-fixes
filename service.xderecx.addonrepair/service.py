import os
import re
import shutil
import zipfile
import tempfile
import urllib.request
import xml.etree.ElementTree as ET

import xbmc
import xbmcvfs
import xbmcgui
import xbmcaddon

ADDON = xbmcaddon.Addon()
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))

SYSTEM_ADDONS_DIR = '/usr/share/kodi/addons'
STORAGE_ADDONS_DIR = '/storage/.kodi/addons'

# This repo's own published addons.xml - the same one the repository addon
# itself points Kodi at. Used to self-heal stale *repo-fetched* dependency
# modules (script.module.beautifulsoup4, script.module.soupsieve, etc.) the
# same way SYSTEM_ADDONS_DIR is used for genuinely bundled system addons -
# Kodi's own "auto-upgrade a dependency during install" mechanism turned out
# not to reliably kick in for these (confirmed live 2026-10-19 on box oco:
# a stale script.module.beautifulsoup4 4.12.2 and script.module.soupsieve
# 2.4.1, both left over from the same years-old install as the stale
# xbmc.python, kept script.cu.lrclyrics.fixed's dependency check failing
# even after the xbmc.python fix, with no auto-upgrade happening on its own).
REPO_ADDONS_XML_URL = 'https://xderecx.github.io/kodi-x96max-fixes/zips/addons.xml'
REPO_ZIP_BASE = 'https://xderecx.github.io/kodi-x96max-fixes/zips'

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


def find_stale_system():
    """Return [(addon_id, storage_version, system_version), ...] for every
    addon id that is a genuine bundled system addon (has a folder directly
    under /usr/share/kodi/addons) AND also has an older local copy sitting
    in /storage/.kodi/addons. Deliberately narrow: an id with no local copy
    at all (the normal case for ~40 of ~45 system addons) or a local copy
    that's equal or newer is left completely alone."""
    if not os.path.isdir(SYSTEM_ADDONS_DIR):
        log('no %s on this platform, skipping system-addon check' % SYSTEM_ADDONS_DIR)
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


def repair_system(stale):
    for addon_id, sv, tv in stale:
        storage_dir = os.path.join(STORAGE_ADDONS_DIR, addon_id)
        log('%s is stale (storage=%s, system=%s) - removing %s so Kodi restores the bundled copy' % (
            addon_id, sv, tv, storage_dir))
        try:
            shutil.rmtree(storage_dir)
        except Exception as e:
            log('could not remove %s: %s' % (storage_dir, e))


def fetch_repo_versions():
    """{addon_id: version} for every addon this repo currently publishes,
    straight from its own live addons.xml (same URL the repository addon
    itself uses) - not from Kodi's local DB cache, which can lag behind."""
    try:
        req = urllib.request.Request(REPO_ADDONS_XML_URL, headers={'User-Agent': 'xDereCx-AddonRepair/1.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        return {el.get('id'): el.get('version') for el in root.findall('addon')}
    except Exception as e:
        log('could not fetch/parse %s: %s' % (REPO_ADDONS_XML_URL, e))
        return {}


def find_stale_repo_modules(repo_versions):
    """Return [(addon_id, storage_version, repo_version), ...] for every
    addon id this repo publishes that is ALSO already installed locally
    with a strictly older version. An id this repo doesn't publish, or one
    not installed at all yet, is left alone - Kodi's normal installer
    handles a genuinely fresh install on its own."""
    stale = []
    for addon_id, repo_v in repo_versions.items():
        storage_xml = os.path.join(STORAGE_ADDONS_DIR, addon_id, 'addon.xml')
        if not os.path.isfile(storage_xml):
            continue
        sv = addon_version(storage_xml, addon_id)
        if not sv or not repo_v:
            continue
        if version_tuple(sv) < version_tuple(repo_v):
            stale.append((addon_id, sv, repo_v))
    return stale


def repair_repo_module(addon_id, version):
    """Download this repo's own zip for addon_id at `version` and replace
    the stale local copy with it directly - the same end result as a real
    Kodi-GUI dependency auto-upgrade, done ourselves because that mechanism
    was confirmed NOT to reliably fire on its own for dependency-only
    modules (2026-10-19, box oco)."""
    url = '%s/%s/%s-%s.zip' % (REPO_ZIP_BASE, addon_id, addon_id, version)
    storage_dir = os.path.join(STORAGE_ADDONS_DIR, addon_id)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'xDereCx-AddonRepair/1.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
    except Exception as e:
        log('could not download %s: %s' % (url, e))
        return False

    tmp_zip = None
    try:
        fd, tmp_zip = tempfile.mkstemp(suffix='.zip')
        os.close(fd)
        with open(tmp_zip, 'wb') as f:
            f.write(data)
        with zipfile.ZipFile(tmp_zip) as zf:
            # sanity check: the zip must actually contain <addon_id>/addon.xml
            # at its top level before we touch anything on disk - a corrupt
            # or unexpected download should never get the chance to leave
            # the addon half-replaced
            names = zf.namelist()
            if not any(n == '%s/addon.xml' % addon_id for n in names):
                log('zip for %s does not contain %s/addon.xml, aborting repair' % (addon_id, addon_id))
                return False
            if os.path.isdir(storage_dir):
                shutil.rmtree(storage_dir)
            zf.extractall(STORAGE_ADDONS_DIR)
        return True
    except Exception as e:
        log('could not install downloaded zip for %s: %s' % (addon_id, e))
        return False
    finally:
        if tmp_zip and os.path.isfile(tmp_zip):
            os.remove(tmp_zip)


def repair():
    fixed = []

    system_stale = find_stale_system()
    repair_system(system_stale)
    fixed.extend(system_stale)

    repo_versions = fetch_repo_versions()
    if repo_versions:
        repo_stale = find_stale_repo_modules(repo_versions)
        for addon_id, sv, rv in repo_stale:
            log('%s is stale (storage=%s, repo=%s) - downloading current version' % (addon_id, sv, rv))
            if repair_repo_module(addon_id, rv):
                fixed.append((addon_id, sv, rv))
            else:
                log('%s could not be repaired this run, will retry next start' % addon_id)

    return fixed


def main():
    log('checking for stale addon copies (bundled system addons + this repo\'s own dependency modules)')
    if not xbmcvfs.exists(PROFILE):
        xbmcvfs.mkdirs(PROFILE)

    fixed = repair()
    if fixed:
        summary = ', '.join('%s (%s -> %s)' % f for f in fixed)
        log('repaired: %s' % summary)
        f = xbmcvfs.File(RESTART_NEEDED_MARKER, 'w')
        f.write(b'1')
        f.close()
        xbmcgui.Dialog().notification(
            'DC Addon Repair',
            'Fixed stale addon(s): %s. Restart Kodi to apply.' % ', '.join(a for a, _, _ in fixed),
            icon=xbmcgui.NOTIFICATION_INFO, time=10000, sound=False)
    elif xbmcvfs.exists(RESTART_NEEDED_MARKER):
        # a previous start found and fixed something; nothing stale is left
        # now, which confirms the fix actually took - clear the marker so we
        # stay quiet from now on
        xbmcvfs.delete(RESTART_NEEDED_MARKER)
        log('previous repair confirmed applied, marker cleared')
    log('check complete' if fixed else 'check complete, nothing stale found')


if __name__ == '__main__':
    main()
