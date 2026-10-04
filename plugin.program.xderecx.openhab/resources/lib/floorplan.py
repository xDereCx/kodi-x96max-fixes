# -*- coding: utf-8 -*-
"""Floor plans built from openHAB item metadata (namespace 'kodi', see README) and the Kodi window drawing them.

On a location item (room, corridor, outdoor area):  kodi="plan" [x=…, y=…, w=…, h=…]
  optional: floor=<floor item> (when the location is not part of the floor in the semantic model, e.g. a yard
  drawn on the ground floor plan), label=…, x2/y2/w2/h2 + label2 … x9/y9/w9/h9 + label9 = further, non-selectable
  rectangles of the same room (L-shaped rooms, niches).
On the floor item (optional): kodi="plan" [w=…, h=…] = size of the drawing; default = bounding box of the rooms.
Units are free (cm, pixels of a drawing…); the window scales them to the screen.
"""
import xbmc
import xbmcgui

import openhab as oh

COLORS = {'ok': 'FF3A4048', 'empty': 'FF2A2E33', 'heating': 'FFC2501E', 'problem': 'FFA02828',
          'outdoor': 'FF4A4A4A'}
ACTION_BACK = (9, 10, 92, 216, 247, 257, 275, 61467, 61448)
ALIGN_CENTER = 0x00000002 | 0x00000004   # XBFONT_CENTER_X | XBFONT_CENTER_Y
ALIGN_CENTER_X = 0x00000002


def _num(cfg, key):
    try:
        return float(cfg.get(key))
    except (TypeError, ValueError):
        return None


def floor_of(items, name):
    """The floor a location is drawn on: kodi config 'floor', else the first Floor up the isPartOf chain."""
    floor = oh.kodi(items[name])[1].get('floor')
    if floor:
        return floor
    seen, cur = set(), name
    while cur in items and cur not in seen:
        seen.add(cur)
        cls, cfg = oh.semantics(items[cur])
        if cls.startswith('Location_Indoor_Floor'):
            return cur
        cur = cfg.get('isPartOf')
    return None


def plan(items, floor):
    """{'size': (w, h), 'areas': [(location, x, y, w, h, kind, label)]} or None if the floor has no plan."""
    areas = []
    for name, it in items.items():
        value, cfg = oh.kodi(it)
        if value != 'plan' or name == floor or floor_of(items, name) != floor:
            continue
        rect = [_num(cfg, k) for k in ('x', 'y', 'w', 'h')]
        if None in rect:
            continue
        kind = 'outdoor' if oh.semantics(it)[0].startswith('Location_Outdoor') else 'room'
        areas.append((name, rect[0], rect[1], rect[2], rect[3], kind, cfg.get('label')))
        for n in range(2, 10):   # further, non-selectable rectangles of the same room (L/U shapes, niches)
            extra = [_num(cfg, '%s%d' % (k, n)) for k in ('x', 'y', 'w', 'h')]
            if None not in extra:
                areas.append((name, extra[0], extra[1], extra[2], extra[3], 'part', cfg.get('label%d' % n) or ''))
    if not areas:
        return None
    fcfg = oh.kodi(items[floor])[1] if floor in items else {}
    w = _num(fcfg, 'w') or max(a[1] + a[3] for a in areas)
    h = _num(fcfg, 'h') or max(a[2] + a[4] for a in areas)
    return {'size': (w, h), 'areas': sorted(areas, key=lambda a: (a[2], a[1]))}


def _bridges(part, main, max_gap=14):
    """Screen rectangles that fill the gap (a drawn wall, up to max_gap px) between a part and its main rectangle
    where they face each other, so that they look like one room."""
    px, py, pw, ph = part
    mx, my, mw, mh = main
    out = []
    ov_y = (max(py, my) + 2, min(py + ph, my + mh) - 2)
    ov_x = (max(px, mx) + 2, min(px + pw, mx + mw) - 2)
    if ov_y[1] > ov_y[0]:
        if 0 <= mx - (px + pw) <= max_gap:                # part left of main
            out.append((px + pw - 2, ov_y[0], mx - (px + pw) + 4, ov_y[1] - ov_y[0]))
        elif 0 <= px - (mx + mw) <= max_gap:              # part right of main
            out.append((mx + mw - 2, ov_y[0], px - (mx + mw) + 4, ov_y[1] - ov_y[0]))
    if ov_x[1] > ov_x[0]:
        if 0 <= my - (py + ph) <= max_gap:                # part above main
            out.append((ov_x[0], py + ph - 2, ov_x[1] - ov_x[0], my - (py + ph) + 4))
        elif 0 <= py - (my + mh) <= max_gap:              # part below main
            out.append((ov_x[0], my + mh - 2, ov_x[1] - ov_x[0], py - (my + mh) + 4))
    return out


def neighbours(rects):
    """For each focusable rect index: (up, down, left, right) index of the nearest rect in that direction."""
    def centre(r):
        return r[0] + r[2] / 2.0, r[1] + r[3] / 2.0

    def overlap(a0, a1, b0, b1):
        return max(0, min(a1, b1) - max(a0, b0))

    out = []
    for i, a in enumerate(rects):
        ax, ay = centre(a)
        best = []
        for d in ('up', 'down', 'left', 'right'):
            cand = None
            for j, b in enumerate(rects):
                if j == i:
                    continue
                bx, by = centre(b)
                tol = 4   # only areas that lie entirely in that direction (edges may touch)
                if d == 'up' and b[1] + b[3] > a[1] + tol or d == 'down' and b[1] < a[1] + a[3] - tol \
                        or d == 'left' and b[0] + b[2] > a[0] + tol or d == 'right' and b[0] < a[0] + a[2] - tol:
                    continue
                if d in ('up', 'down'):
                    ov = overlap(a[0], a[0] + a[2], b[0], b[0] + b[2])
                    dist = abs(by - ay)
                else:
                    ov = overlap(a[1], a[1] + a[3], b[1], b[1] + b[3])
                    dist = abs(bx - ax)
                # side by side first (shared edge), else the closest centre
                score = (0, dist, -ov) if ov > 0 else (1, ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5, 0)
                if cand is None or score < cand[0]:
                    cand = (score, j)
            best.append(cand[1] if cand else i)
        out.append(best)
    return out


class PlanWindow(xbmcgui.WindowDialog):
    """Full-screen floor plan. .selected = chosen location, 'LIST' for the plain list, or None."""

    def __init__(self, title, plan_def, info, media, texts):
        super().__init__()
        self.selected = None
        self.buttons = {}
        W, H = 1280, 720
        top, margin = 90, 30
        pw, ph = plan_def['size']
        scale = min((W - 2 * margin) / float(pw), (H - top - margin - 50) / float(ph))
        ox = int((W - pw * scale) / 2)
        white, frame, clear = media + 'white.png', media + 'frame.png', media + 'clear.png'
        icons = media + 'icons/'

        self.addControl(xbmcgui.ControlImage(0, 0, W, H, white, colorDiffuse='F0101215'))
        self.addControl(xbmcgui.ControlLabel(margin, 20, W - 2 * margin, 40, title, font='font30',
                                             textColor='FFFFFFFF', alignment=ALIGN_CENTER_X))
        legend_y = 58
        self.addControl(xbmcgui.ControlImage(W // 2 - 260, legend_y, 22, 22, icons + 'flame.png', colorDiffuse=COLORS['heating']))
        self.addControl(xbmcgui.ControlLabel(W // 2 - 234, legend_y - 2, 120, 26, texts['heating'], font='font12',
                                             textColor='FFAAAAAA'))
        self.addControl(xbmcgui.ControlImage(W // 2 - 120, legend_y, 22, 22, icons + 'warning.png', colorDiffuse='FFE05050'))
        self.addControl(xbmcgui.ControlLabel(W // 2 - 94, legend_y - 2, 120, 26, texts['problem'], font='font12',
                                             textColor='FFAAAAAA'))
        self.addControl(xbmcgui.ControlLabel(W // 2 + 20, legend_y - 2, 300, 26, texts['keys'], font='font12',
                                             textColor='FFAAAAAA'))
        screen = []   # (loc, kind, rx, ry, rw, rh) before insets
        for loc, x, y, w, h, kind, override in plan_def['areas']:
            screen.append((loc, kind, override, ox + int(x * scale), top + int(y * scale), int(w * scale), int(h * scale)))
        # fills; parts of one room are bridged to its main rectangle across a wall-sized gap -> one shape (L, niches)
        mains = {s[0]: s for s in screen if s[1] != 'part'}
        for loc, kind, override, rx, ry, rw, rh in screen:
            state = info.get(loc, ('empty',))[0]
            color = COLORS['outdoor'] if kind == 'outdoor' and state in ('ok', 'empty') else COLORS[state]
            self.addControl(xbmcgui.ControlImage(rx + 2, ry + 2, rw - 4, rh - 4, white, colorDiffuse=color))
            if kind == 'part' and loc in mains:
                for bx, by, bw, bh in _bridges((rx, ry, rw, rh), mains[loc][3:]):
                    self.addControl(xbmcgui.ControlImage(bx, by, bw, bh, white, colorDiffuse=color))
        focusable, rects = [], []
        for loc, kind, override, rx, ry, rw, rh in screen:
            if kind == 'part':
                if override:
                    self.addControl(xbmcgui.ControlLabel(rx + 4, ry + rh // 2 - 13, rw - 8, 26, override,
                                                         font='font13', textColor='FFFFFFFF', alignment=ALIGN_CENTER_X))
                continue
            entry = info.get(loc, ('empty', loc, '', '', ''))
            state, name = entry[0], entry[1]
            cur, target = (entry[3], entry[4]) if len(entry) > 4 else ('', '')
            # temperature text by the room's width on screen: "22 → 18 °C", "22 °C" or nothing
            temp = ''
            if cur and target and rw >= 130:
                temp = '%s → %s' % (cur.replace(' °C', ''), target)
            elif cur and rw >= 56:
                temp = cur
            # button labels are single-line, so name and status are labels/icons under a transparent button
            title_y = ry + rh // 2 - (26 if temp else 13)
            self.addControl(xbmcgui.ControlLabel(rx + 2, title_y, rw - 4, 26, override or name,
                                                 font='font13' if rw >= 90 else 'font12',
                                                 textColor='FFFFFFFF', alignment=ALIGN_CENTER_X))
            if temp:
                if rw >= 130:   # thermometer icon left of a centred text block (text ~7 px per character)
                    tw = 7 * len(temp)
                    ix = rx + max(4, (rw - tw) // 2 - 24)
                    self.addControl(xbmcgui.ControlImage(ix, title_y + 28, 20, 20, icons + 'thermometer.png',
                                                         colorDiffuse='FFBBCCDD'))
                self.addControl(xbmcgui.ControlLabel(rx + 2, title_y + 26, rw - 4, 24, temp, font='font12',
                                                     textColor='FFDDDDDD', alignment=ALIGN_CENTER_X))
            if state == 'heating':
                self.addControl(xbmcgui.ControlImage(rx + rw - 30, ry + 6, 24, 24, icons + 'flame.png',
                                                     colorDiffuse='FFFFA040'))
            elif state == 'problem':
                self.addControl(xbmcgui.ControlImage(rx + rw - 30, ry + 6, 24, 24, icons + 'warning.png',
                                                     colorDiffuse='FFFFD0D0'))
            btn = xbmcgui.ControlButton(rx, ry, rw, rh, '', focusTexture=frame, noFocusTexture=clear)
            self.addControl(btn)
            self.buttons[btn.getId()] = loc
            focusable.append(btn)
            rects.append((rx, ry, rw, rh))
        bw = 240
        self.list_btn = xbmcgui.ControlButton(int((W - bw) / 2), H - 55, bw, 40, texts['list'], focusTexture=frame,
                                              noFocusTexture=clear, alignment=ALIGN_CENTER, font='font13',
                                              textColor='FFAAAAAA', focusedColor='FFFFFFFF')
        self.addControl(self.list_btn)
        for k, (u, d, l, r) in enumerate(neighbours(rects)):
            down = focusable[d] if d != k else self.list_btn
            focusable[k].setNavigation(focusable[u], down, focusable[l], focusable[r])
        if focusable:
            self.list_btn.setNavigation(focusable[-1], focusable[0], self.list_btn, self.list_btn)
            self.setFocus(focusable[0])

    def onControl(self, control):
        self.selected = 'LIST' if control == self.list_btn else self.buttons.get(control.getId())
        self.close()

    def onAction(self, action):
        if action.getId() in ACTION_BACK:
            self.close()


def show(title, plan_def, info, media, texts):
    """Opens the plan; returns the chosen location item, 'LIST' or None."""
    win = PlanWindow(title, plan_def, info, media, texts)
    win.doModal()
    sel = win.selected
    del win
    xbmc.sleep(50)
    return sel
