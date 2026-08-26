#!/usr/bin/env python3
"""Regenerate the zips/ directory (Kodi addon repository payload) from the
addon source directories in this repo's root.

Run this after adding a new addon folder or bumping an existing addon's
version in its addon.xml. Then git add/commit/push zips/ along with the
source change.

Usage: python3 build_repo.py
"""
import os
import re
import shutil
import hashlib
import zipfile
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
ZIPS = os.path.join(ROOT, 'zips')

# Folders at repo root that are Kodi addons (have addon.xml at their top level).
# Anything else (README.md, skin-overrides/, build_repo.py, zips/, .git/) is skipped
# automatically since we only look for addon.xml presence.
EXCLUDE_DIRS = {'zips', '.git', 'skin-overrides'}


def find_addons():
    addons = []
    for name in sorted(os.listdir(ROOT)):
        path = os.path.join(ROOT, name)
        if name in EXCLUDE_DIRS or not os.path.isdir(path):
            continue
        addon_xml = os.path.join(path, 'addon.xml')
        if os.path.isfile(addon_xml):
            addons.append((name, path, addon_xml))
    return addons


def get_id_version(addon_xml_path):
    tree = ET.parse(addon_xml_path)
    root = tree.getroot()
    return root.get('id'), root.get('version')


def zip_addon(addon_dir, addon_id, version, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, f'{addon_id}-{version}.zip')
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(addon_dir):
            dirnames[:] = [d for d in dirnames if d != '__pycache__']
            for fname in filenames:
                if fname.endswith('.pyc') or fname.endswith('.bak') or fname.endswith('.bak2'):
                    continue
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, os.path.dirname(addon_dir))
                zf.write(full, rel)
    return zip_path


def main():
    if os.path.isdir(ZIPS):
        shutil.rmtree(ZIPS)
    os.makedirs(ZIPS)

    addon_blocks = []
    for name, path, addon_xml in find_addons():
        addon_id, version = get_id_version(addon_xml)
        if addon_id != name:
            raise SystemExit(f'Folder name {name!r} does not match addon id {addon_id!r}')
        out_dir = os.path.join(ZIPS, addon_id)
        zip_path = zip_addon(path, addon_id, version, out_dir)
        shutil.copy2(addon_xml, os.path.join(out_dir, 'addon.xml'))
        for icon_rel in ('icon.png', 'resources/icon.png'):
            icon_src = os.path.join(path, icon_rel)
            if os.path.isfile(icon_src):
                shutil.copy2(icon_src, os.path.join(out_dir, 'icon.png'))
                break
        print(f'packaged {addon_id} {version} -> {os.path.relpath(zip_path, ROOT)}')

        xml_text = open(addon_xml, encoding='utf-8').read()
        xml_text = re.sub(r'<\?xml[^>]*\?>\s*', '', xml_text).strip()
        addon_blocks.append(xml_text)

    addons_xml_path = os.path.join(ZIPS, 'addons.xml')
    with open(addons_xml_path, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n')
        f.write('<addons>\n')
        for block in addon_blocks:
            f.write(block + '\n')
        f.write('</addons>\n')

    md5 = hashlib.md5(open(addons_xml_path, 'rb').read()).hexdigest()
    with open(addons_xml_path + '.md5', 'w', encoding='utf-8') as f:
        f.write(md5)

    print(f'wrote {os.path.relpath(addons_xml_path, ROOT)} (md5 {md5})')


if __name__ == '__main__':
    main()
