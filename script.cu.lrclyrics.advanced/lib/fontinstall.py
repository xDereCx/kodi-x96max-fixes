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

# only fonts confirmed both (a) freely redistributable (OFL/Apache - all
# Google Fonts, license text fetched straight from google/fonts on GitHub,
# see each *-LICENSE.txt) and (b) full Slovak/Czech diacritic glyph coverage
# (checked with fontTools against ČčĎďĽľĹĺŇňŠšŤťŽžĚěŘřŮů - out of 120
# candidate Google Fonts "Display" category fonts, 94 passed; a plain
# "Bowlby One" was tried and rejected here - missing most diacritics - in
# favor of "Bowlby One SC", which does have full coverage). 12 families
# total, in 2 groups:
#   - original 3: Exo2, Ranchers, Luckiest Guy
#   - added (user-selected from rendered samples): Agbalumo, Alfa Slab One,
#     Bangers, Bowlby One SC, Playball, Racing Sans One, Rubik Dirt,
#     Staatliches, Titan One (Faster One was tried and later dropped).
#
# One entry per (family, size) actually used across the current-line
# display's 17 styles (15 ported from Aeon Nox 5 + 2 of this addon's own -
# LyricsW "wiggle", LyricsB "balloon pop") in script-cu-lrclyrics-advanced-main.xml.
# Sizes for the 15 ported styles are copied directly from Aeon Nox 5's own
# skin.aeon.nox.5/1080i/Font.xml (34 distinct font tokens there, collapsed
# onto these families but keeping each token's own real size, e.g.
# Lyrics12's 275pt scrolling marquee vs a 52-62pt secondary line) rather
# than flattening everything to one uniform size.
DECORATIVE_FONTS = (
    ('culrc_agbalumo_58', 'Agbalumo.ttf', 58),
    ('culrc_agbalumo_60', 'Agbalumo.ttf', 60),
    ('culrc_alfaslabone_120', 'Alfa_Slab_One.ttf', 120),
    ('culrc_alfaslabone_125', 'Alfa_Slab_One.ttf', 125),
    ('culrc_bangers_120', 'Bangers.ttf', 120),
    ('culrc_bangers_54', 'Bangers.ttf', 54),
    ('culrc_bangers_62', 'Bangers.ttf', 62),
    ('culrc_bowlbyonesc_120', 'Bowlby_One_SC.ttf', 120),
    ('culrc_bowlbyonesc_130', 'Bowlby_One_SC.ttf', 130),
    ('culrc_bowlbyonesc_140', 'Bowlby_One_SC.ttf', 140),
    ('culrc_exo2_110', 'Exo2-BlackItalic.ttf', 110),
    ('culrc_exo2_120', 'Exo2-BlackItalic.ttf', 120),
    ('culrc_exo2_275', 'Exo2-BlackItalic.ttf', 275),
    ('culrc_luckiestguy_120', 'Luckiest Guy.ttf', 120),
    ('culrc_luckiestguy_205', 'Luckiest Guy.ttf', 205),
    ('culrc_luckiestguy_220', 'Luckiest Guy.ttf', 220),
    ('culrc_playball_54', 'Playball.ttf', 54),
    ('culrc_playball_58', 'Playball.ttf', 58),
    ('culrc_racingsansone_104', 'Racing_Sans_One.ttf', 104),
    ('culrc_racingsansone_120', 'Racing_Sans_One.ttf', 120),
    ('culrc_racingsansone_130', 'Racing_Sans_One.ttf', 130),
    ('culrc_ranchers_120', 'Ranchers-Regular.ttf', 120),
    ('culrc_ranchers_155', 'Ranchers-Regular.ttf', 155),
    ('culrc_ranchers_165', 'Ranchers-Regular.ttf', 165),
    ('culrc_ranchers_60', 'Ranchers-Regular.ttf', 60),
    ('culrc_rubikdirt_52', 'Rubik_Dirt.ttf', 52),
    ('culrc_rubikdirt_54', 'Rubik_Dirt.ttf', 54),
    ('culrc_rubikdirt_56', 'Rubik_Dirt.ttf', 56),
    ('culrc_staatliches_120', 'Staatliches.ttf', 120),
    ('culrc_staatliches_60', 'Staatliches.ttf', 60),
    ('culrc_titanone_110', 'TitanOne.ttf', 110),
    ('culrc_titanone_120', 'TitanOne.ttf', 120),
    ('culrc_titanone_60', 'TitanOne.ttf', 60),
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


# separate from STATE_FILE (which only tracks skins actually patched) - this
# tracks every skin the user has ever been ASKED about, yes or no, so the
# one-time boot-time prompt (see default.py) never asks about the same skin
# twice regardless of the answer. Deliberately still an explicit yes/no
# dialog, never a silent auto-install - same "never silently" rule as the
# manual settings button, just reaching the user proactively once instead
# of requiring them to already know this feature exists and dig for it in
# settings (a real problem: nobody manually runs this for a fresh install
# on a new skin otherwise).
ASKED_STATE_FILE = os.path.join(PROFILE, 'font_patch_asked.json')


def _load_asked():
    if not xbmcvfs.exists(ASKED_STATE_FILE):
        return []
    try:
        f = xbmcvfs.File(ASKED_STATE_FILE)
        data = json.loads(f.readBytes())
        f.close()
        return data
    except Exception:
        return []


def already_asked(skin_id):
    return skin_id in _load_asked()


def mark_asked(skin_id):
    asked = _load_asked()
    if skin_id not in asked:
        asked.append(skin_id)
        if not xbmcvfs.exists(PROFILE):
            xbmcvfs.mkdirs(PROFILE)
        f = xbmcvfs.File(ASKED_STATE_FILE, 'w')
        f.write(json.dumps(asked).encode('utf-8'))
        f.close()


def auto_install_if_needed():
    # shared by default.py (checked once at every service start, including
    # right after a fresh install - Kodi doesn't wait for a reboot to start
    # a newly enabled service addon) and gui.py's onSettingsChanged monitor
    # callback (checked again on every Kodi settings change, since that's
    # also how a live skin switch is caught - Settings > Interface > Skin
    # is itself just another Kodi setting, and Kodi's Monitor.onSettingsChanged
    # fires globally, not just for this addon's own settings). Without the
    # second call site, switching skins mid-session would leave the new
    # skin's fonts uninstalled until the next full Kodi restart happened to
    # also be the first time that skin got used.
    # Returns (installed, result) - installed is False if nothing needed
    # doing (already installed, or already asked/attempted before).
    skin_id = xbmc.getSkinDir()
    if skin_id in installed_skins() or already_asked(skin_id):
        return False, None
    mark_asked(skin_id)
    ok, result = install()
    if ok and result:
        return True, result
    return False, None
