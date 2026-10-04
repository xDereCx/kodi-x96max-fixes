# -*- coding: utf-8 -*-
"""House status picture (1920x1080 PNG) for a skin background: the floor plans with each room's temperature
(red = below its setpoint, green = ok, flame = needs heat / heating), problems, and the items marked
status=true in a strip at the bottom. Pure Python (canvas.py); data = the add-on's model and metadata."""
import os
import time

import canvas
import floorplan
import openhab as oh

W, H = 1920, 1080
BG = (16, 18, 21)
PANEL = (30, 34, 40)
ROOM, EMPTY, OUTDOOR = (52, 58, 66), (36, 40, 46), (44, 46, 50)
WHITE, GREY, DIM = (235, 235, 235), (165, 172, 182), (105, 112, 122)
RED, GREEN, ORANGE, BLUE = (240, 90, 90), (110, 205, 120), (255, 150, 60), (150, 190, 230)


class Assets:
    def __init__(self, media):
        f = os.path.join(media, 'font')

        def font(name):
            return canvas.Font(os.path.join(f, name + '.png'), os.path.join(f, name + '.json'))
        self.title = font('bold-44')
        self.floor = font('bold-30')
        self.temp = font('bold-36')
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


def _room_temps(model, loc):
    for eq in model.equipment_at.get(loc, []):
        c, t = model.role_point(eq, 'temperature'), model.role_point(eq, 'setpoint')
        if c or t:
            return (oh.number(c) if c else None), (oh.number(t) if t else None)
    return None, None


def _draw_plan(c, a, model, floor, box):
    """One floor plan in box (x, y, w, h): rooms, no names, temperature in red/green, flame when needed."""
    items = model.items
    pd = floorplan.plan(items, floor)
    x0, y0, bw, bh = box
    c.text(x0, y0, oh.label(items[floor]), a.floor, GREY)
    top = y0 + a.floor.height + 12
    pw, ph = pd['size']
    sc = min(bw / float(pw), (bh - (top - y0)) / float(ph))
    ox = x0 + int((bw - pw * sc) / 2)
    screen = [(loc, kind, ox + int(x * sc), top + int(y * sc), int(w * sc), int(h * sc))
              for loc, x, y, w, h, kind, _label in pd['areas']]
    mains = {s[0]: s[2:] for s in screen if s[1] != 'part'}
    for loc, kind, rx, ry, rw, rh in screen:
        has = bool(model.equipment_at.get(loc) or model.points_at.get(loc))
        colour = ROOM if has else (OUTDOOR if kind == 'outdoor' else EMPTY)
        if kind == 'part' and loc in mains:
            m = mains[loc]
            # same colour as its main rectangle, joined across the wall gap
            mhas = bool(model.equipment_at.get(loc) or model.points_at.get(loc))
            colour = ROOM if mhas else EMPTY
            for bx, by, bw2, bh2 in floorplan._bridges((rx, ry, rw, rh), m):
                c.rect(bx, by, bw2, bh2, colour)
        c.rect(rx + 2, ry + 2, rw - 4, rh - 4, colour)
    for loc, (rx, ry, rw, rh) in mains.items():
        cur, target = _room_temps(model, loc)
        need = cur is not None and target is not None and cur < target
        if cur is not None:
            txt = ('%.1f°' % cur).replace('.0°', '°')
            tw = a.temp.width(txt)
            c.text(rx + (rw - tw) // 2, ry + (rh - a.temp.height) // 2, txt, a.temp, RED if need else GREEN)
        if need or model.heating(loc):
            c.mask(rx + rw - 44, ry + 8, a.icon('flame', 36), ORANGE)


def _marked(items):
    """Items marked status=true as (order, label, item, icon), sorted."""
    marked = []
    for item in items.values():
        cfg = oh.kodi(item)[1]
        if str(cfg.get('status', '')).lower() in ('true', '1', 'yes'):
            try:
                order = float(cfg.get('order', 999))
            except ValueError:
                order = 999
            marked.append((order, oh.label(item).lower(), item, cfg.get('icon') or 'info'))
    marked.sort(key=lambda m: (m[0], m[1]))
    return marked


def render(model, path, texts, assets):
    """Draws the picture to `path`; texts: {'title','ok','updated'} (localised). Returns seconds taken."""
    t0 = time.time()
    it = model.items
    c = canvas.Canvas(W, H, BG)
    a = assets
    c.text(60, 34, texts['title'], a.title, WHITE)
    stamp = '%s %s' % (texts['updated'], time.strftime('%H:%M'))
    c.text(W - 60 - a.small.width(stamp), 52, stamp, a.small, DIM)

    marked = _marked(it)
    cols, rh = 5, 56
    rows = max(2, -(-len(marked) // cols))   # more rows -> lower plans, no item is dropped
    floors = [f for f in model.tops() if floorplan.plan(it, f)]
    plan_y, plan_h = 110, 832 - rows * rh
    if floors:
        gap = 40
        fw = (W - 120 - gap * (len(floors) - 1)) // len(floors)
        for i, floor in enumerate(floors):
            _draw_plan(c, a, model, floor, (60 + i * (fw + gap), plan_y, fw, plan_h))

    # problems (red) above the strip, or a quiet "everything is fine"
    y = plan_y + plan_h + 20
    problems = model.problems()
    if problems:
        x = 60
        for text, _owner in problems[:3]:
            c.mask(x, y, a.icon('warning', 36), RED)
            x = c.text(x + 46, y + 4, text, a.text, RED, 560) + 40
    else:
        c.mask(60, y, a.icon('ok', 36), GREEN)
        c.text(106, y + 4, texts['ok'], a.text, GREY)

    # strip with the items marked status=true
    sy = y + 60
    c.rect(60, sy, W - 120, H - sy - 30, PANEL)
    cw = (W - 120) // cols
    for i, (_o, _l, item, icon) in enumerate(marked):
        cx, cy = 60 + (i % cols) * cw + 20, sy + 14 + (i // cols) * rh
        on = item.get('type') == 'Switch' and item.get('state') == 'ON'
        c.mask(cx, cy, a.icon(icon, 36), ORANGE if (icon == 'flame' and on) else BLUE)
        st = _state_text(item)
        x = c.text(cx + 46, cy + 4, oh.label(item), a.text, WHITE, cw - 46 - 30 - a.text.width(st) - 16)
        c.text(x + 12, cy + 4, st, a.text, GREY)
    c.save_png(path)
    return time.time() - t0
