# -*- coding: utf-8 -*-
"""House status picture (1280x720 PNG) for a skin background: problems, rooms with temperatures, status items.
Pure Python (canvas.py); everything shown comes from the same model/metadata as the add-on's lists."""
import os
import time

import canvas
import openhab as oh

W, H = 1280, 720
BG = (16, 18, 21)
PANEL = (30, 34, 40)
WHITE, GREY, DIM = (240, 240, 240), (170, 176, 186), (110, 116, 126)
RED, ORANGE, BLUE, GREEN = (235, 90, 90), (255, 150, 60), (150, 190, 230), (110, 200, 120)


class Assets:
    def __init__(self, media):
        f = os.path.join(media, 'font')
        self.title = canvas.Font(os.path.join(f, 'bold-44.png'), os.path.join(f, 'bold-44.json'))
        self.text = canvas.Font(os.path.join(f, 'regular-26.png'), os.path.join(f, 'regular-26.json'))
        self.bold = canvas.Font(os.path.join(f, 'bold-26.png'), os.path.join(f, 'bold-26.json'))
        self.small = canvas.Font(os.path.join(f, 'regular-20.png'), os.path.join(f, 'regular-20.json'))
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


def render(model, path, texts, assets):
    """Draws the picture to `path`. texts: {'title','ok','rooms','house','updated'} (localised)."""
    t0 = time.time()
    it = model.items
    c = canvas.Canvas(W, H, BG)
    a = assets
    # title + time
    c.text(60, 34, texts['title'], a.title, WHITE)
    stamp = '%s %s' % (texts['updated'], time.strftime('%H:%M'))
    c.text(W - 60 - a.small.width(stamp), 52, stamp, a.small, DIM)
    y = 110
    # problems (or "everything is fine")
    problems = model.problems()
    if problems:
        for text, _owner in problems[:4]:
            c.rect(60, y, W - 120, 46, (70, 30, 34))
            c.mask(72, y + 5, a.icon('warning'), RED)
            c.text(124, y + 8, text, a.text, WHITE, W - 200)
            y += 54
    else:
        c.mask(60, y, a.icon('ok'), GREEN)
        c.text(110, y + 3, texts['ok'], a.text, GREY)
        y += 50
    y += 12
    col_w = (W - 120 - 30) // 2
    # left column: rooms with a temperature
    rooms = []
    for loc in model.by_label([n for n in it if oh.semantics(it[n])[0].startswith('Location')]):
        cur = target = None
        for eq in model.equipment_at.get(loc, []):
            cur, target = model.role_point(eq, 'temperature'), model.role_point(eq, 'setpoint')
            if cur or target:
                break
        if cur or target:
            rooms.append((oh.label(it[loc]), cur, target, model.heating(loc)))
    # right column: items marked status=true
    marked = []
    for n, item in it.items():
        cfg = oh.kodi(item)[1]
        if str(cfg.get('status', '')).lower() in ('true', '1', 'yes'):
            try:
                order = float(cfg.get('order', 999))
            except ValueError:
                order = 999
            marked.append((order, oh.label(item).lower(), item, cfg.get('icon') or 'info'))
    marked.sort(key=lambda m: (m[0], m[1]))
    row_h = 44
    rows = max(1, (H - y - 70) // row_h)
    for col, (header, x) in enumerate(((texts['rooms'], 60), (texts['house'], 60 + col_w + 30))):
        c.rect(x, y, col_w, min(H - y - 30, 50 + row_h * rows), PANEL)
        c.text(x + 18, y + 10, header, a.bold, GREY)
    yy = y + 56
    for name, cur, target, heating in rooms[:rows]:
        x = 78
        c.mask(x, yy + 2, a.icon('flame' if heating else 'thermometer'), ORANGE if heating else BLUE)
        temp = oh.display_state(cur) if cur else ''
        if target:
            temp += ' → ' + oh.display_state(target)
        tw = a.text.width(temp)
        c.text(x + 46, yy + 5, name, a.text, WHITE, col_w - 18 - tw - 20 - (x + 46 - 60))
        c.text(60 + col_w - 18 - tw, yy + 5, temp, a.text, GREY)
        yy += row_h
    yy = y + 56
    x0 = 60 + col_w + 30
    for _o, _l, item, icon in marked[:rows]:
        on = item.get('type') == 'Switch' and item.get('state') == 'ON'
        colour = ORANGE if (icon == 'flame' and on) else BLUE
        c.mask(x0 + 18, yy + 2, a.icon(icon), colour)
        st = _state_text(item)
        sw = a.text.width(st)
        c.text(x0 + 64, yy + 5, oh.label(item), a.text, WHITE, col_w - 64 - 18 - sw - 20)
        c.text(x0 + col_w - 18 - sw, yy + 5, st, a.text, GREY)
        yy += row_h
    c.save_png(path)
    return time.time() - t0
