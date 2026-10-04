# -*- coding: utf-8 -*-
"""House status picture (1920x1080 PNG) for a skin background: the floor plans with each room's temperature
(red = below its setpoint, green = ok, flame = needs heat / heating) and the items marked status=true drawn in
their rooms, problems below; items without a room on a plan go to a strip at the bottom. The picture can be kept
in a part of the screen (top 3/4, left 3/4) that the skin's menu does not cover. Pure Python (canvas.py);
data = the add-on's model and metadata."""
import os
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
    def __init__(self, media):
        f = os.path.join(media, 'font')

        def font(name):
            return canvas.Font(os.path.join(f, name + '.png'), os.path.join(f, name + '.json'))
        self.title = font('bold-44')
        self.floor = font('bold-30')
        self.temps = [font('bold-36'), font('bold-30'), font('bold-26')]   # largest that fits the room
        self.text = font('regular-24')
        self.small = font('regular-20')
        self._icons = {}
        self.icondir = os.path.join(media, 'icons', 'small')

    def icon(self, name, size=36):
        key = (name, size)
        if key not in self._icons:
            path = os.path.join(self.icondir, '%s-%d.png' % (name, size))
            if not os.path.exists(path):
                path = os.path.join(self.icondir, 'info-%d.png' % size)
            self._icons[key] = canvas.read_mask(path)
        return self._icons[key]


def _state_text(item):
    if item.get('type') == 'Switch' and item.get('state') in ('ON', 'OFF'):
        return '✔' if item['state'] == 'ON' else '✘'
    return oh.display_state(item)


def _icon_colour(item, icon):
    on = item.get('type') == 'Switch' and item.get('state') == 'ON'
    return ORANGE if (icon == 'flame' and on) else BLUE


def _room_temps(model, loc):
    for eq in model.equipment_at.get(loc, []):
        c, t = model.role_point(eq, 'temperature'), model.role_point(eq, 'setpoint')
        if c or t:
            return (oh.number(c) if c else None), (oh.number(t) if t else None)
    return None, None


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


def _draw_items(c, a, rect, align, entries):
    """Status items inside a room rectangle (screen px): stacked from the top (left/right) or centred lines."""
    rx, ry, rw, rh = rect
    rows = []
    for item, icon, cfg in entries:
        st = _state_text(item)
        txt = st if flag(cfg, 'compact') else '%s %s' % (oh.label(item), st)
        rows.append((icon, txt, _icon_colour(item, icon), min(42 + a.small.width(txt), rw - 20), item))
    if align == 'center':
        lines, cur = [], []
        for r in rows:
            if cur and sum(q[3] for q in cur) + 24 * len(cur) + r[3] > rw - 20:
                lines.append(cur)
                cur = []
            cur.append(r)
        lines.append(cur)
        y = ry + (rh - ROW * len(lines) + 4) // 2
        for line in lines:
            x = rx + (rw - sum(r[3] for r in line) - 24 * (len(line) - 1)) // 2
            for icon, txt, col, w, _it in line:
                c.mask(x, y, a.icon(icon, 36), col)
                c.text(x + 42, y + 6, txt, a.small, WHITE, w - 42)
                x += w + 24
            y += ROW
        return
    y = ry + 10
    for icon, txt, col, w, _it in rows:
        x = rx + 10 if align == 'left' else rx + rw - 10 - w
        c.mask(x, y, a.icon(icon, 36), col)
        c.text(x + 42, y + 6, txt, a.small, WHITE, w - 42)
        y += ROW


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
        cur, target = _room_temps(model, loc)
        need = cur is not None and target is not None and cur < target
        if cur is not None:
            txt = ('%.1f°' % cur).replace('.0°', '°')
            f = next((f for f in a.temps if f.width(txt) <= rw - 12 and f.height <= rh - 8), a.temps[-1])
            c.text(rx + (rw - f.width(txt)) // 2, ry + (rh - f.height) // 2, txt, f, RED if need else GREEN)
        if need or model.heating(loc):
            wide = rw >= 90   # narrow room: flame at the bottom, below the number
            c.mask(rx + rw - 42 if wide else rx + (rw - 36) // 2, ry + 6 if wide else ry + rh - 42,
                   a.icon('flame', 36), ORANGE)
    groups = {}
    for loc, part, align, item, icon, cfg in placed:
        if loc in mains:
            groups.setdefault((loc, part, align), []).append((item, icon, cfg))
    for (loc, part, align), entries in groups.items():
        r = _rect(oh.kodi(items[loc])[1], part) if part != 1 else None
        _draw_items(c, a, screen(r) if r else mains[loc], align, entries)


def render(model, path, texts, assets, area='full'):
    """Draws the picture to `path`; texts: {'title','ok','updated'} (localised); area: full | top | left
    (everything inside that part of the screen). Returns seconds taken."""
    t0 = time.time()
    items = model.items
    a = assets
    aw, ah = AREAS.get(area, AREAS['full'])
    c = canvas.Canvas(W, H, BG)
    c.text(M, 26, texts['title'], a.title, WHITE)
    stamp = '%s %s' % (texts['updated'], time.strftime('%H:%M'))
    c.text(aw - M - a.small.width(stamp), 44, stamp, a.small, DIM)

    floors = []
    for f in model.tops():
        pd = floorplan.plan(items, f)
        if pd:
            floors.append((f, pd))
    on_plan = {loc for _f, pd in floors for loc, _x, _y, _w, _h, kind, _l in pd['areas'] if kind != 'part'}

    # status items: into their room (kodi config room=…, else the semantic location) when it is on a plan
    placed, strip = [], []
    for _o, _l, item, icon, cfg in _marked(items):
        loc = cfg.get('room') or _location_of(items, item['name'])
        if loc in on_plan:
            try:
                part = max(1, min(9, int(float(cfg.get('part', 1)))))
            except ValueError:
                part = 1
            align = cfg.get('align') if cfg.get('align') in ('left', 'right', 'center') else 'left'
            placed.append((loc, part, align, item, icon, cfg))
        else:
            strip.append((item, icon))

    cols = max(1, (aw - 2 * M) // 360)
    strip_h = (-(-len(strip) // cols)) * STRIP_ROW + 20 if strip else 0
    sy = ah - 20 - strip_h
    py = (sy if strip else ah - 20) - 52   # problems line
    top, gap = 96, 40

    if floors:
        avail_h = py - 16 - top - a.floor.height - 10
        avail_w = (aw - 2 * M - gap * (len(floors) - 1)) // len(floors)

        def fit(pd):
            pw, ph = pd['size']
            s = min(avail_w / float(pw), avail_h / float(ph))
            return int(pw * s), int(ph * s)
        # a floor with stretch=true (e.g. a sketch, not measured) gets the size of the largest plan in scale
        scaled = [fit(pd) for f, pd in floors if not flag(oh.kodi(items[f])[1] if f in items else {}, 'stretch')]
        ref = max(scaled, key=lambda s: s[0] * s[1]) if scaled else (avail_w, avail_h)
        sizes = [ref if flag(oh.kodi(items[f])[1] if f in items else {}, 'stretch') else fit(pd) for f, pd in floors]
        x = (aw - sum(s[0] for s in sizes) - gap * (len(floors) - 1)) // 2
        for (f, pd), (dw, dh) in zip(floors, sizes):
            _draw_plan(c, a, model, f, pd, x, top, dw, dh, placed)
            x += dw + gap

    problems = model.problems()
    if problems:
        x = M
        for text, _owner in problems[:3]:
            c.mask(x, py, a.icon('warning', 36), RED)
            x = c.text(x + 46, py + 4, text, a.text, RED, 560) + 40
    else:
        c.mask(M, py, a.icon('ok', 36), GREEN)
        c.text(M + 46, py + 4, texts['ok'], a.text, GREY)

    if strip:
        c.rect(M, sy, aw - 2 * M, strip_h, PANEL)
        cw = (aw - 2 * M) // cols
        for i, (item, icon) in enumerate(strip):
            cx, cy = M + (i % cols) * cw + 20, sy + 10 + (i // cols) * STRIP_ROW
            c.mask(cx, cy, a.icon(icon, 36), _icon_colour(item, icon))
            st = _state_text(item)
            tx = c.text(cx + 46, cy + 4, oh.label(item), a.text, WHITE, cw - 46 - 30 - a.text.width(st) - 16)
            c.text(tx + 12, cy + 4, st, a.text, GREY)
    c.save_png(path)
    return time.time() - t0
