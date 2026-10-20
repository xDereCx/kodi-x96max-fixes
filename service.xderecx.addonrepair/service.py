import os
import re
import glob
import shutil
import sqlite3
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
ADDONS_DB_GLOB = '/storage/.kodi/userdata/Database/Addons*.db'

# These two ids are the ones confirmed (2026-10-20, box oco) to make Kodi
# reject an addon outright as "not compatible" when the addon's own
# <requires> import names an older version than what's actually installed
# - NOT just "too low to satisfy >=", which would be harmless, but rejected
# even though the real installed version numerically satisfies the import's
# declared minimum. Seen after a CoreELEC major-version OS update (20->21
# Omega) bumped the real xbmc.gui from 5.16.0 to 5.17.0: skin.aeon.nox.5
# still declared "<import addon=\"xbmc.gui\" version=\"5.15.0\" />" and Kodi
# flagged it incompatible regardless - the fix was only ever rewriting that
# one import line to match the real installed version exactly. The box
# "oby" already had this exact one-line fix applied (from an earlier,
# undocumented session) while "oco" did not, which is how this was found.
VERSION_SENSITIVE_IMPORTS = ('xbmc.gui', 'xbmc.python')

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


def addons_db_path():
    matches = sorted(glob.glob(ADDONS_DB_GLOB))
    return matches[-1] if matches else None


def find_incompatible_addon_ids():
    """addonIDs Kodi's own DB currently marks disabledReason=2 (incompatible)
    - read-only, used to scope the version-mismatch check to addons Kodi has
    actually rejected, never to ones that are simply disabled on purpose."""
    db_path = addons_db_path()
    if not db_path:
        return []
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            rows = conn.execute("SELECT addonID FROM installed WHERE disabledReason=2").fetchall()
        finally:
            conn.close()
        return [r[0] for r in rows]
    except Exception as e:
        log('could not read %s: %s' % (db_path, e))
        return []


def find_version_mismatches():
    """Return [(addon_id, dep_id, declared_version, system_version), ...]
    for every currently-incompatible addon whose own addon.xml declares a
    <requires> import of xbmc.gui or xbmc.python at a version strictly
    older than what's actually installed system-wide. See
    VERSION_SENSITIVE_IMPORTS above for why only these two ids."""
    mismatches = []
    for addon_id in find_incompatible_addon_ids():
        xml_path = os.path.join(STORAGE_ADDONS_DIR, addon_id, 'addon.xml')
        if not os.path.isfile(xml_path):
            continue
        try:
            with open(xml_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            log('could not read %s: %s' % (xml_path, e))
            continue
        for dep_id in VERSION_SENSITIVE_IMPORTS:
            m = re.search(r'<import\s+addon="%s"\s+version="([^"]+)"\s*/>' % re.escape(dep_id), content)
            if not m:
                continue
            declared = m.group(1)
            system_xml = os.path.join(SYSTEM_ADDONS_DIR, dep_id, 'addon.xml')
            system_v = addon_version(system_xml, dep_id)
            if system_v and version_tuple(declared) < version_tuple(system_v):
                mismatches.append((addon_id, dep_id, declared, system_v))
    return mismatches


def repair_version_mismatch(addon_id, dep_id, declared, system_v):
    """Rewrite just the one stale <import> line to match the real installed
    version, then clear Kodi's cached 'incompatible' row for this addon so
    the next FindAddons pass actually re-evaluates it fresh - a file edit
    alone was confirmed NOT enough on its own (2026-10-19/20, multiple
    addons): once Kodi caches disabledReason=2 for an addon it does not
    re-check it just because the file on disk changed underneath it."""
    xml_path = os.path.join(STORAGE_ADDONS_DIR, addon_id, 'addon.xml')
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            content = f.read()
        old = '<import addon="%s" version="%s" />' % (dep_id, declared)
        if old not in content:
            # tolerate the no-space-before-slash variant too
            old = '<import addon="%s" version="%s"/>' % (dep_id, declared)
        new = old.replace(declared, system_v)
        if old not in content:
            log('could not locate the exact import line for %s/%s in %s, skipping' % (addon_id, dep_id, xml_path))
            return False
        with open(xml_path, 'w', encoding='utf-8') as f:
            f.write(content.replace(old, new))
    except Exception as e:
        log('could not patch %s for %s: %s' % (xml_path, addon_id, e))
        return False

    db_path = addons_db_path()
    if db_path:
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            try:
                conn.execute("DELETE FROM installed WHERE addonID=?", (addon_id,))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            log('patched %s but could not clear its cached DB row: %s' % (addon_id, e))
    return True


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

    for addon_id, dep_id, declared, system_v in find_version_mismatches():
        log('%s declares %s %s but system has %s - rewriting the import line' % (
            addon_id, dep_id, declared, system_v))
        if repair_version_mismatch(addon_id, dep_id, declared, system_v):
            fixed.append(('%s (%s)' % (addon_id, dep_id), declared, system_v))
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
