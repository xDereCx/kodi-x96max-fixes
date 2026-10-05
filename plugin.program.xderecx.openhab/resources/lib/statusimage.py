# -*- coding: utf-8 -*-
"""House status picture (1920x1080 PNG) for a skin background: the floor plans with each room's temperature
(red = below its setpoint, green = ok, flame = needs heat / heating) and the items marked status=true drawn in
their rooms, problems below; items without a room on a plan go to a strip at the bottom. The picture can be kept
in a part of the screen (top 3/4, left 3/4) that the skin's menu does not cover. Pure Python (canvas.py);
data = the add-on's model and metadata."""
import os
import re
import time

import canvas
import floorplan
import openhab as oh
from model import flag

W, H = 1920, 1080
AREAS = {'full': (W, H), 'top': (W, H * 3 // 4), 'left': (W * 3 // 4, H)}
BG = (16, 18, 21)
PANEL = (30, 34, 40)
ROOM, EMPTY, OUTDOOR = (52, 58, 66), (36, 40, 46), (44, 46, 50)
WHITE, GREY, DIM = (235, 235, 235), (165, 172, 182), (105, 112, 122)
RED, GREEN, ORANGE, BLUE = (240, 90, 90), (110, 205, 120), (255, 150, 60), (150, 190, 230)
M = 50          # margin
ROW = 40        # row of an item drawn in a room
STRIP_ROW = 52  # row of the strip at the bottom


class Assets:
    def __init__(self, media, weather_dir=None):
        self.weather_dir = weather_dir   # Kodi weather icon pack (0.png … 47.png, na.png = weather.com codes)
        self._images = {}
        f = os.path.join(media, 'font')

        def font(name):
            return canvas.Font(os.path.join(f, name + '.png'), os.path.join(f, name + '.json'))
        self.title = font('bold-44')
        self.floor = font('bold-30')
        self.temps = [font('bold-36'), font('bold-30'), font('bold-26'), font('bold-22')]   # largest that fits
        self.text = font('regular-24')
        self.small = font('regular-20')
        self.tiny = font('regular-16')   # status items in crowded rooms (with 28 px icons)
        self.micro = font('regular-12')  # setpoint "(19°)" under a room temperature
        self._icons = {}
        self.icondir = os.path.join(media, 'icons', 'small')

    def weather(self, code, size):
        """Colour weather icon for a weather.com code (0-47) from Kodi's icon pack, or None."""
        if not self.weather_dir:
            return None
        try:
            name = '%d' % int(float(code))
        except (TypeError, ValueError):
            name = 'na'
        key = (name, size)
        if key not in self._images:
            path = os.path.join(self.weather_dir, name + '.png')
            if not os.path.exists(path):
                path = os.path.join(self.weather_dir, 'na.png')
            try:
                self._images[key] = canvas.read_image(path, size)
            except (OSError, ValueError):
                self._images[key] = None
        return self._images[key]

    def icon(self, name, size=36):
        key = (name, size)
        if key not in self._icons:
            path = os.path.join(self.icondir, '%s-%d.png' % (name, size))
            if os.path.exists(path):
                self._icons[key] = canvas.read_mask(path)
            else:   # no file in this size: scale the 56 px one down (box filter), e.g. 20 px for size=micro
                big = os.path.join(self.icondir, '%s-56.png' % name)
                if not os.path.exists(big):
                    big = os.path.join(self.icondir, 'info-56.png')
                self._icons[key] = _shrink_mask(canvas.read_mask(big), size)
        return self._icons[key]


def _shrink_mask(mask, size):
    """(w, h, alpha bytes) scaled down to size x size, box filter."""
    w, h, data = mask
    out = bytearray(size * size)
    for oy in range(size):
        y0, y1 = oy * h // size, max(oy * h // size + 1, (oy + 1) * h // size)
        for ox in range(size):
            x0, x1 = ox * w // size, max(ox * w // size + 1, (ox + 1) * w // size)
            s = n = 0
            for yy in range(y0, y1):
                row = yy * w
                for xx in range(x0, x1):
                    s += data[row + xx]
                    n += 1
            out[oy * size + ox] = s // n
    return size, size, bytes(out)


COLOURS = {'green': GREEN, 'red': RED, 'orange': ORANGE, 'blue': BLUE, 'white': WHITE, 'grey': GREY}


def _lookup(cfg, key, state):
    """Value for `state` from a kodi config list like map="OL=GRID,OB=BATT" (exact state, else its first word)."""
    pairs = dict(p.split('=', 1) for p in str(cfg.get(key) or '').split(',') if '=' in p)
    st = str(state or '')
    if st in pairs:
        return pairs[st]
    first = st.split(' ')[0]
    return pairs.get(first)


def _state_text(item, cfg=None):
    mapped = _lookup(cfg or {}, 'map', item.get('state'))
    if mapped is not None:
        return mapped
    if item.get('type') == 'Switch' and item.get('state') in ('ON', 'OFF'):
        return '✔' if item['state'] == 'ON' else '✘'
    return oh.display_state(item)


_CMP = re.compile(r'^(<=|>=|<|>)\s*(-?[0-9.]+)$')


def _text_colour(item, cfg, default):
    """colors="OL=green,OB=red" (state / its first word) or numeric conditions "<0=red,>0=green"."""
    col = _lookup(cfg or {}, 'colors', item.get('state'))
    if col is None and cfg and cfg.get('colors'):
        try:
            v = float(str(item.get('state')).split(' ')[0])
        except ValueError:
            v = None
        if v is not None:
            for pair in str(cfg['colors']).split(','):
                cond, _, name = pair.rpartition('=')
                m = _CMP.match(cond.strip())
                if m:
                    op, lim = m.group(1), float(m.group(2))
                    if {'<': v < lim, '>': v > lim, '<=': v <= lim, '>=': v >= lim}[op]:
                        col = name.strip()
                        break
    return COLOURS.get(col, default)


COLD, MILD, HOT = (70, 130, 255), (235, 235, 235), (240, 60, 60)


def _spectrum(state, rng):
    """Colour of a number: blue -> white -> red; rng = "low,high", values outside are clamped."""
    try:
        lo, hi = [float(v) for v in str(rng).split(',')[:2]]
        v = float(str(state).split(' ')[0])
    except (ValueError, TypeError):
        return None
    t = max(0.0, min(1.0, (v - lo) / (hi - lo))) if hi != lo else 1.0
    a, b, t = (COLD, MILD, t * 2) if t < 0.5 else (MILD, HOT, t * 2 - 1)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _icon_colour(item, icon, cfg=None):
    cfg = cfg or {}
    if cfg.get('icon_range'):              # e.g. tank temperature 18 -> 90 °C: blue -> red
        col = _spectrum(item.get('state'), cfg['icon_range'])
        if col:
            return col
    col = COLOURS.get(_lookup(cfg, 'icon_colors', item.get('state')))   # e.g. ON=orange,OFF=blue
    if col:
        return col
    on = item.get('type') == 'Switch' and item.get('state') == 'ON'
    return ORANGE if (icon == 'flame' and on) else BLUE


def _valve_temps(model, loc):
    """[(cur, target, heating, config of the temperature point)] for every equipment at loc with a temperature."""
    out = []
    for eq in model.equipment_at.get(loc, []):
        c, t = model.role_point(eq, 'temperature'), model.role_point(eq, 'setpoint')
        if not (c or t):
            continue
        h = model.role_point(eq, 'heating')
        heating = bool(h and str(h.get('state')) == str(oh.kodi(h)[1].get('on', 'ON')))
        out.append(((oh.number(c) if c else None), (oh.number(t) if t else None), heating,
                    oh.kodi(c)[1] if c else {}))
    return out


def _location_of(items, name, depth=0):
    """Semantic location of an item: itself if it is a location, else via hasLocation / isPointOf / isPartOf."""
    it = items.get(name)
    if not it or depth > 6:
        return None
    cls, cfg = oh.semantics(it)
    if cls.startswith('Location'):
        return name
    if cfg.get('hasLocation'):
        return cfg['hasLocation']
    for key in ('isPointOf', 'isPartOf'):
        if cfg.get(key):
            return _location_of(items, cfg[key], depth + 1)
    return None


def _marked(items):
    """Items marked status=true as (order, label, item, icon, config), sorted."""
    marked = []
    for item in items.values():
        cfg = oh.kodi(item)[1]
        if flag(cfg, 'status'):
            try:
                order = float(cfg.get('order', 999))
            except ValueError:
                order = 999
            marked.append((order, oh.label(item).lower(), item, cfg.get('icon') or 'info', cfg))
    marked.sort(key=lambda m: (m[0], m[1]))
    return marked


def _rect(cfg, part):
    """Rectangle of a room in plan units: part 1 = x/y/w/h, part n = xn/yn/wn/hn."""
    sfx = '' if part == 1 else str(part)
    r = [floorplan._num(cfg, k + sfx) for k in ('x', 'y', 'w', 'h')]
    return None if None in r else r


ALIGNS = ('left', 'right', 'center', 'top-left', 'top-right', 'bottom-left', 'bottom-right')
SIZES = ((36, 'small', ROW, 24), (28, 'tiny', 30, 14), (28, 'tiny', 27, 12))   # icon px, font, row, gap; crowded rooms


def _draw_items(c, a, rect, align, entries, items=None):
    """Status items inside a room rectangle (screen px): stacked in a corner (left/right = top corners,
    bottom-left/bottom-right) or centred lines. Smaller icons and font when they would not fit.
    rows=n (any item): at most n rows per column; justify=left: a right-corner column is left-aligned;
    text="{A} / {B}": value from a template ({A|n} = number without unit); noicon=true: text only."""
    rx, ry, rw, rh = rect
    cfgs = [cfg for _i, _ic, cfg in entries]
    if any(cfg.get('cols') for cfg in cfgs):
        # table rows across the whole rectangle: cols="left|centre|right" (templates); header=true: grey row
        font, row = a.tiny, 27
        y = ry + 4
        for _item, _icon, cfg in entries:
            parts = (_fmt(items, cfg.get('cols', '')) if items is not None else str(cfg.get('cols', ''))).split('|')
            left, mid, right = (parts + ['', '', ''])[:3]
            colr = GREY if flag(cfg, 'header') else WHITE
            c.text(rx + 8, y, left, font, colr)
            c.text(rx + (rw - font.width(mid)) // 2, y, mid, font, GREY)
            c.text(rx + rw - 8 - font.width(right), y, right, font, colr)
            y += row
        return
    if any(cfg.get('size') == 'micro' for cfg in cfgs):   # smallest: 12 px font, 20 px icons
        sizes = ((20, 'micro', 20, 10),)
    elif any(cfg.get('size') == 'mini' for cfg in cfgs):  # 16 px font with 20 px icons, tight rows
        sizes = ((20, 'tiny', 23, 10),)
    else:
        sizes = SIZES[1:] if any(flag(cfg, 'small') for cfg in cfgs) else SIZES
    try:
        max_rows = min(int(float(cfg['rows'])) for cfg in cfgs if cfg.get('rows'))
    except ValueError:
        max_rows = None
    justify_left = any(cfg.get('justify') == 'left' for cfg in cfgs)
    for isz, fname, row, gap in sizes:
        font = getattr(a, fname)
        rows = []
        for item, icon, cfg in entries:
            st = _fmt(items, cfg['text']) if (cfg.get('text') and items is not None) else _state_text(item, cfg)
            label = None if flag(cfg, 'compact') else (_fmt(items, oh.label(item)) if items is not None else oh.label(item))
            iw = 0 if flag(cfg, 'noicon') else isz + 6
            w = iw + (font.width(label) + 8 if label else 0) + font.width(st)
            rows.append((None if flag(cfg, 'noicon') else icon, label, st, _icon_colour(item, icon, cfg), _text_colour(item, cfg, WHITE), w))
        if align == 'center':
            lines, cur = [], []
            for r in rows:
                if cur and sum(q[5] for q in cur) + gap * len(cur) + r[5] > rw - 12:
                    lines.append(cur)
                    cur = []
                cur.append(r)
            lines.append(cur)
            fits = row * len(lines) <= rh - 8 and all(sum(q[5] for q in ln) + gap * (len(ln) - 1) <= rw - 12 for ln in lines)
        else:   # corners: further columns when the rows do not fit the height
            per = max(1, (rh - 12) // row)
            if max_rows:
                per = min(per, max_rows)
            cols = [rows[i:i + per] for i in range(0, len(rows), per)]
            fits = sum(max(r[5] for r in col) for col in cols) + gap * (len(cols) - 1) <= rw - 16
            if max_rows and per < max_rows and len(rows) > per:   # wanted more rows per column: smaller rows
                fits = False
        if fits:
            break

    def one(x, y, r):
        icon, label, st, icol, tcol, w = r
        tx, ty = x, y + (row - font.height) // 2 - 2
        if icon:
            c.mask(x, y + (row - isz) // 2 - 2, a.icon(icon, isz), icol)
            tx = x + isz + 6
        if label:
            tx = c.text(tx, ty, label, font, WHITE, rx + rw - tx - 4) + 8
        c.text(tx, ty, st, font, tcol, max(0, rx + rw - tx - 4))

    if align == 'center':
        y = ry + (rh - row * len(lines)) // 2
        for line in lines:
            x = rx + (rw - sum(r[5] for r in line) - gap * (len(line) - 1)) // 2
            for r in line:
                one(x, y, r)
                x += r[5] + gap
            y += row
        return
    bottom = align.startswith('bottom')
    right = align.endswith('right')
    x = rx + rw - 8 if right else rx + 8          # columns go inwards from the chosen side
    for col in cols:
        cw = max(r[5] for r in col)
        y = ry + rh - 8 - row * len(col) if bottom else ry + 8
        for r in col:
            one((x - (cw if justify_left else r[5])) if right else x, y, r)
            y += row
        x = x - cw - gap if right else x + cw + gap


def _deg(v):
    return ('%.1f°' % v).replace('.0°', '°')


def _draw_temp(c, a, area, cur, target, heating, small=False):
    """Temperature (red below the setpoint, green ok) centred in area (x, y, w, h), the setpoint in small
    type below it "(19°)"; the flame, when heat is needed or the valve heats, right of the number if it fits,
    else below; number font fitted to the area (small=True: start at the smallest size)."""
    x, y, w, h = area
    need = cur is not None and target is not None and cur < target
    flame = need or heating
    txt = _deg(cur)
    sp = '(%s)' % _deg(target) if target is not None else ''
    sh = a.micro.height if sp else 0
    for f in (a.temps[-1:] if small else a.temps):
        isz = 36 if f.height >= 30 else 28
        inline = f.width(txt) + (isz + 4 if flame else 0) <= w - 10 and f.height + sh <= h - 6
        below = f.width(txt) <= w - 10 and f.height + sh + (isz + 2 if flame else 0) <= h - 6
        if inline or below:
            break
    tw = f.width(txt)
    col = RED if need else GREEN
    block = f.height + sh + (isz + 2 if flame and not inline else 0)
    ty = y + (h - block) // 2
    if flame and inline:
        gx = x + (w - tw - isz - 4) // 2
        c.text(gx, ty, txt, f, col)
        c.mask(gx + tw + 4, ty + (f.height - isz) // 2, a.icon('flame', isz), ORANGE)
        cx = gx + tw // 2
    else:
        c.text(x + (w - tw) // 2, ty, txt, f, col)
        cx = x + w // 2
    if sp:
        c.text(cx - a.micro.width(sp) // 2, ty + f.height - 2, sp, a.micro, GREY)
    if flame and not inline:
        c.mask(x + (w - isz) // 2, ty + f.height + sh + 2, a.icon('flame', isz), ORANGE)


def _draw_plan(c, a, model, floor, pd, x0, y0, dw, dh, placed):
    """One floor plan, drawn dw x dh px below its name at (x0, y0): rooms (no names), temperature in red/green
    (font fitted to the room), flame when needed, status items placed in its rooms."""
    items = model.items
    c.text(x0, y0, oh.label(items[floor]), a.floor, GREY)
    top = y0 + a.floor.height + 10
    pw, ph = pd['size']
    sx, sy = dw / float(pw), dh / float(ph)   # equal for a plan in scale, different for a stretched one

    def screen(r):
        return x0 + int(r[0] * sx), top + int(r[1] * sy), int(r[2] * sx), int(r[3] * sy)
    areas = [(loc, kind) + screen((x, y, w, h)) for loc, x, y, w, h, kind, _l in pd['areas']]
    mains = {s[0]: s[2:] for s in areas if s[1] != 'part'}
    for loc, kind, rx, ry, rw, rh in areas:
        has = bool(model.equipment_at.get(loc) or model.points_at.get(loc))
        colour = ROOM if has else (OUTDOOR if kind == 'outdoor' else EMPTY)
        if kind == 'part' and loc in mains:   # joined to its main rectangle across the wall gap
            for bx, by, bw2, bh2 in floorplan._bridges((rx, ry, rw, rh), mains[loc]):
                c.rect(bx, by, bw2, bh2, colour)
        c.rect(rx + 2, ry + 2, rw - 4, rh - 4, colour)
    for loc, (rx, ry, rw, rh) in mains.items():
        valves = [v for v in _valve_temps(model, loc) if v[0] is not None]
        free = [v for v in valves if not (v[3].get('part') or v[3].get('at'))]
        for i, (cur, target, heating, cfg) in enumerate(valves):
            if cfg.get('at'):   # at="x,y": centre of the number in plan units
                try:
                    px, py = [float(v) for v in str(cfg['at']).split(',')]
                except ValueError:
                    px = py = None
                if px is not None:
                    cx, cy = x0 + int(px * sx), top + int(py * sy)
                    w2 = min(rw, 160)
                    _draw_temp(c, a, (cx - w2 // 2, cy - 40, w2, 80), cur, target, heating, flag(cfg, 'small'))
                    continue
            r = _rect(oh.kodi(items[loc])[1], int(float(cfg.get('part', 1)))) if cfg.get('part') else None
            if r:
                _draw_temp(c, a, screen(r), cur, target, heating, flag(cfg, 'small'))
            else:   # unplaced valves share the main rectangle, one below the other
                k, n = free.index((cur, target, heating, cfg)), len(free)
                _draw_temp(c, a, (rx, ry + rh * k // n, rw, rh // n), cur, target, heating, flag(cfg, 'small'))
    groups = {}
    for loc, part, align, item, icon, cfg in placed:
        area = _area(cfg)
        if area and (loc in mains or cfg.get('floor') == floor):   # own rectangle in plan units
            groups.setdefault(('area', area, align), []).append((item, icon, cfg))
        elif loc in mains:
            groups.setdefault((loc, part, align), []).append((item, icon, cfg))
    for (loc, part, align), entries in groups.items():
        if loc == 'area':
            _draw_items(c, a, screen(part), align, entries, items)
            continue
        r = _rect(oh.kodi(items[loc])[1], part) if part != 1 else None
        _draw_items(c, a, screen(r) if r else mains[loc], align, entries, items)


def _area(cfg):
    """area="x,y,w,h" (plan units) of a status item group, or None."""
    try:
        r = tuple(float(v) for v in str(cfg.get('area', '')).split(','))
    except ValueError:
        return None
    return r if len(r) == 4 else None


PANEL_W = 300   # left panel width incl. the gap to the plans (one column)
PANEL_W2 = 520  # with panel_columns >= 2
WICON = 64      # weather icon size in the panel


def _fmt(items, s):
    """'{Item_Name}' in a label or text template -> that item's readable state."""
    def one(m):
        it = items.get(m.group(1))
        if it is None:
            return '–'
        if m.group(2) == '|d':   # {Item|d}: a date as 04.10.
            mm = re.match(r'(\d{4})-(\d\d)-(\d\d)', str(it.get('state') or ''))
            return '%s.%s.' % (mm.group(3), mm.group(2)) if mm else '–'
        if m.group(2) == '|i':   # {Item|i}: rounded to a whole number, without the unit
            v = oh.number(it)
            return '%d' % round(v) if v is not None and v == v else '–'
        if m.group(2):   # {Item|n}: the number only, without the unit
            v = oh.number(it)
            return ('%.1f' % v).replace('.0', '') if v is not None and v == v else '–'
        return oh.display_state(it)
    return re.sub(r'\{([A-Za-z0-9_]+)(\|[ndi])?\}', one, str(s))


def _draw_panel(c, a, entries, x, y, h, items):
    """Status items marked panel=left as a column (panel_columns = grid of n columns): optional heading
    (panel_title on an item), per item the label in small type and the value below it. big=true: large value,
    wide=true: full width, section="…": sub-heading before the item, text="{A} / {B}": value from a template
    of item states (label may use {…} too)."""
    title = next((cfg.get('panel_title') for _i, _ic, cfg in entries if cfg.get('panel_title')), None)
    bottom = y + h
    if title:
        c.text(x, y, title, a.floor, GREY)
        y += a.floor.height + 14
    try:
        ncol = max(1, int(next((cfg.get('panel_columns') for _i, _ic, cfg in entries if cfg.get('panel_columns')), 1)))
    except ValueError:
        ncol = 1
    pw = PANEL_W2 if ncol > 1 else PANEL_W
    cw = (pw - 30) // ncol
    isz, vf = (36, a.text) if ncol == 1 else (28, a.small)

    def cell(cx, cy, item, icon, cfg, vfont, width):
        rh_ = a.tiny.height + vfont.height + 8
        img = a.weather(_fmt(items, cfg['weather_icon']), WICON) if cfg.get('weather_icon') else None
        if img:   # colour weather icon (Kodi's icon pack), taller row
            rh_ = max(rh_, WICON + 4)
            c.image(cx - 6, cy + (rh_ - WICON) // 2, img)
            tx = cx + WICON + 4
        else:
            c.mask(cx, cy + (rh_ - isz) // 2, a.icon(icon, isz), _icon_colour(item, icon, cfg))
            tx = cx + isz + 10
        cy += (rh_ - a.tiny.height - vfont.height) // 2 - 4 if img else 0
        value = _fmt(items, cfg['text']) if cfg.get('text') else _state_text(item, cfg)
        c.text(tx, cy, _fmt(items, oh.label(item)), a.tiny, DIM, width - isz - 14)
        c.text(tx, cy + a.tiny.height, value, vfont, _text_colour(item, cfg, WHITE), width - isz - 14)
        return rh_

    rh = a.tiny.height + vf.height + 8
    col = 0                                   # next free column in the current grid row
    for item, icon, cfg in entries:
        big, wide = flag(cfg, 'big'), flag(cfg, 'wide') or flag(cfg, 'big')
        if (cfg.get('section') or wide) and col:
            y, col = y + rh, 0                # finish the half-filled row
        if cfg.get('section'):
            sf = a.temps[-1]
            if y + 10 + sf.height > bottom:
                return
            c.text(x, y + 10, cfg['section'], sf, GREY)
            y += sf.height + 18
        if wide:
            vfont = a.temps[0] if big else vf
            h_ = a.tiny.height + vfont.height + (14 if big else 8)
            if y + h_ > bottom:
                return
            y += max(h_, cell(x, y, item, icon, cfg, vfont, pw - 30))
            continue
        if y + rh > bottom:
            return
        cell(x + col * cw, y, item, icon, cfg, vf, cw)
        col += 1
        if col == ncol:
            y, col = y + rh, 0


def render(model, path, texts, assets, area='full'):
    """Draws the picture to `path`; texts: {'title','ok','updated'} (localised); area: full | top | left
    (everything inside that part of the screen). Returns seconds taken."""
    t0 = time.time()
    items = model.items
    a = assets
    aw, ah = AREAS.get(area, AREAS['full'])
    c = canvas.Canvas(W, H, BG)
    # no title: the skin shows the menu item's name, and its top bar (RSS) covers the first ~40 px
    stamp = '%s %s' % (texts['updated'], time.strftime('%H:%M'))
    c.text(aw - M - a.small.width(stamp), 52, stamp, a.small, DIM)

    floors = []
    for f in model.tops():
        pd = floorplan.plan(items, f)
        if pd:
            floors.append((f, pd))
    on_plan = {loc for _f, pd in floors for loc, _x, _y, _w, _h, kind, _l in pd['areas'] if kind != 'part'}

    # status items: into their room (kodi config room=…, else the semantic location) when it is on a plan
    placed, strip, panel = [], [], []
    for _o, _l, item, icon, cfg in _marked(items):
        if cfg.get('panel') == 'left':   # column left of the plans (e.g. the weather)
            panel.append((item, icon, cfg))
            continue
        loc = cfg.get('room') or _location_of(items, item['name'])
        on_floor = cfg.get('floor') in [f for f, _pd in floors] and _area(cfg)   # free area on a floor, no room
        if loc in on_plan or on_floor:
            try:
                part = max(1, min(9, int(float(cfg.get('part', 1)))))
            except ValueError:
                part = 1
            align = cfg.get('align') if cfg.get('align') in ALIGNS else 'left'
            placed.append((loc, part, align, item, icon, cfg))
        else:
            strip.append((item, icon, cfg))

    cols = max(1, (aw - 2 * M) // 360)
    strip_h = (-(-len(strip) // cols)) * STRIP_ROW + 20 if strip else 0
    sy = ah - 20 - strip_h
    py = (sy if strip else ah - 20) - 52   # problems line
    top, gap = 50, 40   # below the skin's top bar
    pw_ = (PANEL_W2 if any(str(e[2].get('panel_columns', '1')) not in ('', '1') for e in panel) else PANEL_W) if panel else 0
    if panel:   # the problems line goes under the plans, the panel gets the full height
        _draw_panel(c, a, panel, M, top, (sy if strip else ah - 20) - 16 - top, items)

    px = M   # left edge of the problems line: first plan when there is a panel
    if floors:
        avail_h = py - 16 - top - a.floor.height - 10
        avail_w = (aw - 2 * M - pw_ - gap * (len(floors) - 1)) // len(floors)

        def stretched(f):
            return flag(oh.kodi(items[f])[1] if f in items else {}, 'stretch')
        # plans in scale share ONE scale (same units -> the house is equally large on every floor), the one that
        # fits the largest of them
        measured = [pd['size'] for f, pd in floors if not stretched(f)]
        scale = min(min(avail_w / float(pw), avail_h / float(ph)) for pw, ph in measured) if measured else 1.0

        def fit(pd):
            pw, ph = pd['size']
            return int(pw * scale), int(ph * scale)
        # a floor with stretch=true (e.g. a sketch, not measured) gets the size of the largest plan in scale
        scaled = [fit(pd) for f, pd in floors if not stretched(f)]
        ref = max(scaled, key=lambda s: s[0] * s[1]) if scaled else (avail_w, avail_h)
        sizes = [ref if stretched(f) else fit(pd) for f, pd in floors]
        total = sum(s[0] for s in sizes) + gap * (len(floors) - 1)
        x = aw - M - total if panel else (aw - total) // 2   # with a panel: plans on the right
        if panel:
            px = x
        for (f, pd), (dw, dh) in zip(floors, sizes):
            _draw_plan(c, a, model, f, pd, x, top, dw, dh, placed)
            x += dw + gap

    problems = model.problems()
    if problems:
        x = px
        for text, _owner in problems[:3]:
            room = aw - M - x - 46
            if room < 120:
                break
            c.mask(x, py, a.icon('warning', 36), RED)
            x = c.text(x + 46, py + 4, text, a.text, RED, min(560, room)) + 40
    else:
        c.mask(px, py, a.icon('ok', 36), GREEN)
        c.text(px + 46, py + 4, texts['ok'], a.text, GREY)

    if strip:
        c.rect(M, sy, aw - 2 * M, strip_h, PANEL)
        cw = (aw - 2 * M) // cols
        for i, (item, icon, cfg) in enumerate(strip):
            cx, cy = M + (i % cols) * cw + 20, sy + 10 + (i // cols) * STRIP_ROW
            c.mask(cx, cy, a.icon(icon, 36), _icon_colour(item, icon, cfg))
            st = _state_text(item, cfg)
            tx = c.text(cx + 46, cy + 4, oh.label(item), a.text, WHITE, cw - 46 - 30 - a.text.width(st) - 16)
            c.text(tx + 12, cy + 4, st, a.text, _text_colour(item, cfg, GREY))
    c.save_png(path)
    return time.time() - t0
