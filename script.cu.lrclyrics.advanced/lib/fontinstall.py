import json
import os
import shutil

import xbmc
import xbmcgui
import xbmcvfs

from lib.utils import ADDON, ADDONNAME, ADDONICON, CWD, PROFILE, log

# Kodi's WindowXMLDialog (used by our own fallback dialog) never loads a
# Font.xml bundled with the addon itself - confirmed via kodi.log across
# several independent fix attempts (defaultRes variations, fontset id
# rename, a full debug-log walk of the window-open sequence: not one
# LoadFontsFromFile call for our path, ever). The only fonts a script
# dialog can actually use are whatever the ACTIVE skin's own Font.xml
# already defines. This module works around that by installing our own
# bundled decorative fonts directly into the active skin's own Font.xml,
# the same technique script.xderecx.aeonnox5lyricsfix uses for Aeon Nox 5,
# but generalized to whatever skin happens to be active and gated on the
# user explicitly running it (settings button), never silently.

# only fonts confirmed both (a) freely redistributable (OFL/Apache, not
# Nasalization - proprietary Typodermic EULA forbids redistribution) and
# (b) full Slovak/Czech diacritic glyph coverage (Fredoka One, PollerOne
# and Geomancy were ruled out here - missing most caron/acute letters,
# would reintroduce the exact diacritics bug this project already fixed)
DECORATIVE_FONTS = (
    ('culrc_exo2', 'Exo2-BlackItalic.ttf', 64),
    ('culrc_ranchers', 'Ranchers-Regular.ttf', 70),
    ('culrc_luckiestguy', 'Luckiest Guy.ttf', 60),
)

SOURCE_DIR = os.path.join(CWD, 'resources', 'fonts', 'decorative')
STATE_FILE = os.path.join(PROFILE, 'font_patch_state.json')
MARKER = '<!-- culrc-decorative-fonts-patch -->'


def _load_state():
    if not xbmcvfs.exists(STATE_FILE):
        return []
    try:
        f = xbmcvfs.File(STATE_FILE)
        data = json.loads(f.readBytes())
        f.close()
        return data
    except Exception:
        return []


def _save_state(state):
    if not xbmcvfs.exists(PROFILE):
        xbmcvfs.mkdirs(PROFILE)
    f = xbmcvfs.File(STATE_FILE, 'w')
    f.write(json.dumps(state).encode('utf-8'))
    f.close()


def _find_font_xmls(skin_root):
    found = []
    for dirpath, dirnames, filenames in os.walk(skin_root):
        for fn in filenames:
            if fn == 'Font.xml':
                found.append(os.path.join(dirpath, fn))
    return found


def _is_writable(path):
    # xbmcvfs.File()/mkdirs() silently fail (log an error, no Python
    # exception) on a read-only filesystem on this platform - confirmed
    # live: an early version of this function used xbmcvfs and returned
    # True on a read-only skin path, letting install() crash later inside
    # shutil.copy2() instead of failing cleanly here. Plain os/open() do
    # raise properly, so use those for the actual writability probe.
    if not os.access(path, os.W_OK):
        return False
    test_path = os.path.join(path, '.culrc_write_test')
    try:
        with open(test_path, 'wb') as f:
            f.write(b'test')
        os.remove(test_path)
        return True
    except OSError:
        return False


def _build_font_blocks():
    blocks = []
    for name, filename, size in DECORATIVE_FONTS:
        blocks.append(
            '\t\t<font>\n'
            '\t\t\t<name>%s</name>\n'
            '\t\t\t<filename>culrc/%s</filename>\n'
            '\t\t\t<size>%d</size>\n'
            '\t\t</font>\n' % (name, filename, size)
        )
    return ''.join(blocks)


def install():
    skin_id = xbmc.getSkinDir()
    skin_root = xbmcvfs.translatePath('special://skin/')
    if not skin_root or not xbmcvfs.exists(skin_root):
        return False, 'no active skin path found'
    if not _is_writable(skin_root):
        return False, '%s is on a read-only filesystem (common for the OS-bundled default skin) - can\'t install fonts into it' % skin_id

    font_xmls = _find_font_xmls(skin_root)
    if not font_xmls:
        return False, 'no Font.xml found under %s' % skin_root

    state = _load_state()
    already_done_paths = {entry['font_xml'] for entry in state if entry['skin_id'] == skin_id}
    fonts_dest_dir = os.path.join(skin_root, 'fonts', 'culrc')
    try:
        os.makedirs(fonts_dest_dir, exist_ok=True)
        for name, filename, size in DECORATIVE_FONTS:
            src = os.path.join(SOURCE_DIR, filename)
            dst = os.path.join(fonts_dest_dir, filename)
            shutil.copy2(src, dst)
    except OSError as e:
        return False, 'could not copy fonts into %s: %s' % (fonts_dest_dir, e)

    patched_count = 0
    for font_xml in font_xmls:
        if font_xml in already_done_paths:
            continue
        try:
            with open(font_xml, 'r', encoding='utf-8') as f:
                content = f.read()
            if MARKER in content:
                # already patched by us in a previous run this state file
                # doesn't know about (e.g. state file was cleared manually)
                state.append({'skin_id': skin_id, 'font_xml': font_xml, 'backup': None, 'skin_root': skin_root})
                continue
            blocks = MARKER + '\n' + _build_font_blocks()
            # insert right before each </fontset> close tag
            new_content = content.replace('</fontset>', blocks + '\t</fontset>')
            if new_content == content:
                log('fontinstall: no </fontset> found in %s, skipped' % font_xml, debug=True)
                continue
            backup_path = font_xml + '.culrc-backup'
            if not os.path.exists(backup_path):
                shutil.copy2(font_xml, backup_path)
            with open(font_xml, 'w', encoding='utf-8') as f:
                f.write(new_content)
        except OSError as e:
            log('fontinstall: failed to patch %s: %s' % (font_xml, e), debug=True)
            continue
        state.append({'skin_id': skin_id, 'font_xml': font_xml, 'backup': backup_path, 'skin_root': skin_root})
        patched_count += 1

    _save_state(state)
    return True, patched_count


def remove():
    state = _load_state()
    if not state:
        return False, 'no font patch is currently installed'
    restored = 0
    skin_roots = set()
    for entry in state:
        if entry.get('backup') and xbmcvfs.exists(entry['backup']):
            shutil.copy2(entry['backup'], entry['font_xml'])
            xbmcvfs.delete(entry['backup'])
            restored += 1
        if entry.get('skin_root'):
            skin_roots.add(entry['skin_root'])
    for skin_root in skin_roots:
        fonts_dest_dir = os.path.join(skin_root, 'fonts', 'culrc')
        if xbmcvfs.exists(fonts_dest_dir):
            xbmcvfs.rmdir(fonts_dest_dir, force=True)
    _save_state([])
    return True, restored


def installed_skins():
    state = _load_state()
    return sorted({entry['skin_id'] for entry in state})
