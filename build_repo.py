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
# Anything else (README.md, keymaps/, build_repo.py, zips/, .git/) is skipped
# automatically since we only look for addon.xml presence.
EXCLUDE_DIRS = {'zips', '.git'}


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


def get_icon_rel(addon_xml_path):
    """The <icon> path exactly as addon.xml declares it -- Kodi resolves
    it relative to the addon's own folder both when installed AND when
    browsing an addon that isn't installed yet (fetched from datadir),
    so the packaged icon must live at that same relative path or the
    repository browser gets a 404 for the thumbnail."""
    tree = ET.parse(addon_xml_path)
    icon = tree.getroot().find('.//icon')
    return icon.text.strip() if icon is not None and icon.text else None


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


def write_index(dir_path, entries, title):
    """Minimal HTML directory listing so Kodi's HTTP file-browser (which
    parses <a href> links, same as an Apache/nginx autoindex page) can
    browse this folder over GitHub Pages -- raw.githubusercontent.com
    serves exact file paths only and has no directory listing at all,
    which is why 'Install from zip file' can't browse it."""
    with open(os.path.join(dir_path, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(f'<html><head><title>{title}</title></head><body>\n')
        f.write(f'<h1>{title}</h1>\n<ul>\n')
        for name in entries:
            f.write(f'<li><a href="{name}">{name}</a></li>\n')
        f.write('</ul>\n</body></html>\n')


def main():
    if os.path.isdir(ZIPS):
        shutil.rmtree(ZIPS)
    os.makedirs(ZIPS)

    addon_blocks = []
    addon_dirs = []
    for name, path, addon_xml in find_addons():
        addon_id, version = get_id_version(addon_xml)
        if addon_id != name:
            raise SystemExit(f'Folder name {name!r} does not match addon id {addon_id!r}')
        out_dir = os.path.join(ZIPS, addon_id)
        zip_path = zip_addon(path, addon_id, version, out_dir)
        shutil.copy2(addon_xml, os.path.join(out_dir, 'addon.xml'))
        icon_rel = get_icon_rel(addon_xml)
        has_icon = False
        if icon_rel:
            icon_src = os.path.join(path, icon_rel)
            if os.path.isfile(icon_src):
                icon_dst = os.path.join(out_dir, icon_rel)
                os.makedirs(os.path.dirname(icon_dst), exist_ok=True)
                shutil.copy2(icon_src, icon_dst)
                has_icon = True
        print(f'packaged {addon_id} {version} -> {os.path.relpath(zip_path, ROOT)}')

        entries = [os.path.basename(zip_path), 'addon.xml']
        if has_icon:
            entries.append(icon_rel)
        write_index(out_dir, entries, addon_id)
        addon_dirs.append(addon_id)

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

    write_index(ZIPS, [d + '/' for d in addon_dirs] + ['addons.xml', 'addons.xml.md5'], 'kodi-x96max-fixes repo')

    # GitHub Pages must not run this through Jekyll, which ignores/mangles
    # some file layouts by default -- .nojekyll disables that processing.
    open(os.path.join(ROOT, '.nojekyll'), 'a').close()


if __name__ == '__main__':
    main()
