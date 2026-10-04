# -*- coding: utf-8 -*-
"""openHAB Home - Kodi plugin: browse/control openHAB by its semantic model; floor plans and the house status
come from item metadata (namespace 'kodi', see README), so nothing house-specific is in this code."""
import os
import sys
import time
import urllib.parse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

ADDON = xbmcaddon.Addon()
sys.path.insert(0, os.path.join(ADDON.getAddonInfo('path'), 'resources', 'lib'))
import openhab as oh  # noqa: E402
import floorplan  # noqa: E402

BASE = sys.argv[0]
HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].lstrip('-').isdigit() else -1
PARAMS = dict(urllib.parse.parse_qsl(sys.argv[2][1:])) if len(sys.argv) > 2 else {}
NAME = ADDON.getAddonInfo('name')
ROLES = ('temperature', 'setpoint', 'mode', 'heating')   # kodi metadata values on points (see README)


def S(sid):
    return ADDON.getLocalizedString(sid)


def url(**kw):
    return BASE + '?' + urllib.parse.urlencode(kw)


def notify(msg, icon=xbmcgui.NOTIFICATION_INFO):
    xbmcgui.Dialog().notification(NAME, msg, icon, 4000)


def flag(cfg, key):
    return str(cfg.get(key, '')).lower() in ('true', '1', 'yes')


def client():
    token = ADDON.getSetting('token')
    if not token:
        xbmcgui.Dialog().ok(NAME, S(32020))
        ADDON.openSettings()
        return None
    try:
        timeout = int(float(ADDON.getSetting('timeout') or 8))
    except ValueError:
        timeout = 8
    return oh.OpenHAB(ADDON.getSetting('url') or 'http://localhost:8080', token, timeout)


def load():
    c = client()
    if c is None:
        return None, None
    try:
        return c, c.items()
    except oh.OpenHABError as err:
        notify(S(32021) % err, xbmcgui.NOTIFICATION_ERROR)
        return c, None


# ---- model ---------------------------------------------------------------------------------------

class Model:
    def __init__(self, items):
        self.items = items
        self.sub_locations, self.equipment_at, self.points_at, self.points_of, self.sub_equipment = {}, {}, {}, {}, {}
        for name, it in items.items():
            cls, cfg = oh.semantics(it)
            if cls.startswith('Location') and cfg.get('isPartOf'):
                self.sub_locations.setdefault(cfg['isPartOf'], []).append(name)
            elif cls.startswith('Equipment'):
                if cfg.get('hasLocation'):
                    self.equipment_at.setdefault(cfg['hasLocation'], []).append(name)
                if cfg.get('isPartOf'):
                    self.sub_equipment.setdefault(cfg['isPartOf'], []).append(name)
            elif cls.startswith('Point'):
                if cfg.get('isPointOf'):
                    self.points_of.setdefault(cfg['isPointOf'], []).append(name)
                elif cfg.get('hasLocation'):
                    self.points_at.setdefault(cfg['hasLocation'], []).append(name)

    def by_label(self, names):
        return sorted(names, key=lambda n: oh.label(self.items[n]).lower())

    def kind_of(self, name, prefix):
        return name in self.items and oh.semantics(self.items[name])[0].startswith(prefix)

    def tops(self):
        """Floors (by item name), then outdoor locations that don't belong to a floor or another outdoor area."""
        floors = sorted(n for n in self.items if self.kind_of(n, 'Location_Indoor_Floor'))
        outdoor = []
        for n in self.items:
            if self.kind_of(n, 'Location_Outdoor'):
                parent = oh.semantics(self.items[n])[1].get('isPartOf')
                if not (self.kind_of(parent, 'Location_Outdoor') or self.kind_of(parent, 'Location_Indoor_Floor')):
                    outdoor.append(n)
        return floors + self.by_label(outdoor)

    def other_equipment(self):
        """Equipment whose location can't be reached from the floors/outdoor locations."""
        reachable, todo = set(), list(self.tops())
        while todo:
            loc = todo.pop()
            if loc not in reachable:
                reachable.add(loc)
                todo += self.sub_locations.get(loc, [])
        return self.by_label([e for loc, eqs in self.equipment_at.items() if loc not in reachable for e in eqs])

    def role_point(self, equipment, role):
        for p in self.points_of.get(equipment, []):
            if oh.kodi(self.items[p])[0] == role:
                return self.items[p]
        return None

    def equipment_summary(self, equipment):
        """'21 °C → 20 °C (programming)' from the temperature/setpoint/mode points of an equipment."""
        cur, sp, mode = (self.role_point(equipment, r) for r in ('temperature', 'setpoint', 'mode'))
        parts = []
        if cur:
            parts.append(oh.display_state(cur))
        if sp:
            parts.append('→ ' + oh.display_state(sp))
        if mode:
            parts.append('(' + oh.display_state(mode) + ')')
        return ' '.join(parts)

    def location_summary(self, loc):
        for eq in self.equipment_at.get(loc, []):
            s = self.equipment_summary(eq)
            if s:
                return s
        return ''

    def heating(self, loc):
        for eq in self.equipment_at.get(loc, []):
            p = self.role_point(eq, 'heating')
            if p and str(p.get('state')) == str(oh.kodi(p)[1].get('on', 'ON')):
                return True
        return False

    def sorted_points(self, equipment):
        def key(n):
            value, cfg = oh.kodi(self.items[n])
            if value in ROLES:
                return (0, ROLES.index(value), '')
            if cfg.get('order') is not None:
                try:
                    return (1, float(cfg['order']), '')
                except ValueError:
                    pass
            return (2 if not cfg.get('label') else 1, 999, oh.label(self.items[n]).lower())
        return sorted([p for p in self.points_of.get(equipment, []) if not flag(oh.kodi(self.items[p])[1], 'hidden')],
                      key=key)

    def problems(self):
        """[(text, link)] for items whose kodi metadata 'problem' condition matches their state."""
        out = []
        for n, it in self.items.items():
            cfg = oh.kodi(it)[1]
            if cfg.get('problem') and oh.matches(it, cfg['problem']):
                owner = oh.semantics(it)[1].get('isPointOf') or ''
                if cfg.get('problem_text'):
                    text = cfg['problem_text'].replace('{state}', oh.display_state(it))
                else:
                    who = oh.label(self.items[owner]) + ' – ' if owner in self.items else ''
                    text = '%s%s: %s' % (who, oh.label(it), oh.display_state(it))
                out.append((text, owner if owner in self.items else None))
        return sorted(out)


# ---- list items ----------------------------------------------------------------------------------

def folder(text, link, icon='DefaultFolder.png', info=''):
    li = xbmcgui.ListItem(text)
    li.setArt({'icon': icon, 'thumb': icon})
    if info:
        li.setLabel2(info)
    xbmcplugin.addDirectoryItem(HANDLE, link, li, isFolder=True)


def action_item(text, link, icon='DefaultAddonService.png', info=''):
    li = xbmcgui.ListItem(text)
    li.setArt({'icon': icon, 'thumb': icon})
    li.setProperty('IsPlayable', 'false')
    if info:
        li.setLabel2(info)
    xbmcplugin.addDirectoryItem(HANDLE, link, li, isFolder=False)


def point_item(model, name):
    it = model.items[name]
    icon = 'DefaultAddonService.png' if not oh.read_only(it) else 'DefaultIconInfo.png'
    action_item('%s: %s' % (oh.label(it), oh.display_state(it)), url(action='point', name=name), icon)


def end(content='files'):
    xbmcplugin.setContent(HANDLE, content)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)


# ---- views ---------------------------------------------------------------------------------------

def view_root():
    _, items = load()
    folder(S(32010), url(action='status'), 'DefaultIconInfo.png')
    if items:
        m = Model(items)
        for loc in m.tops():
            if floorplan.plan(items, loc):   # floors with a plan open it; the plan has a "room list" button
                action_item(oh.label(items[loc]), url(action='plan', name=loc), 'DefaultFolder.png', S(32015))
            else:
                folder(oh.label(items[loc]), url(action='loc', name=loc), 'DefaultFolder.png')
        if m.other_equipment():
            folder(S(32012), url(action='other'), 'DefaultFolder.png')
    if xbmc.getSkinDir() == AN5 and not an5_slot_with_us():
        action_item(S(32014), url(action='addmenu'), 'DefaultAddonProgram.png')
    action_item(S(32013), url(action='settings'), 'DefaultAddonProgram.png')
    end()


def view_location(name):
    _, items = load()
    if items:
        m = Model(items)
        for sub in m.by_label(m.sub_locations.get(name, [])):
            folder(oh.label(items[sub]), url(action='loc', name=sub), 'DefaultFolder.png', m.location_summary(sub))
        for eq in m.by_label(m.equipment_at.get(name, [])):
            folder(oh.label(items[eq]), url(action='equip', name=eq), 'DefaultAddonService.png',
                   m.equipment_summary(eq))
        for p in m.by_label(m.points_at.get(name, [])):
            point_item(m, p)
    end()


def view_equipment(name):
    _, items = load()
    if items:
        m = Model(items)
        for sub in m.by_label(m.sub_equipment.get(name, [])):
            folder(oh.label(items[sub]), url(action='equip', name=sub), 'DefaultAddonService.png')
        for p in m.sorted_points(name):
            point_item(m, p)
    end()


def view_other():
    _, items = load()
    if items:
        m = Model(items)
        for eq in m.other_equipment():
            folder(oh.label(items[eq]), url(action='equip', name=eq), 'DefaultAddonService.png')
    end()


def status_lines(m):
    """[(text, link or None, is_problem)]: problems, rooms with a temperature, items marked 'status'."""
    it = m.items
    problems = m.problems()
    out = [(t, l, True) for t, l in problems] or [(S(32011), None, False)]
    for loc in m.by_label([n for n in it if oh.semantics(it[n])[0].startswith('Location')]):
        s = m.location_summary(loc)
        if s:
            out.append(('%s: %s' % (oh.label(it[loc]), s), loc, False))
    marked = []
    for n, item in it.items():
        cfg = oh.kodi(item)[1]
        if flag(cfg, 'status'):
            try:
                order = float(cfg.get('order', 999))
            except ValueError:
                order = 999
            owner = oh.semantics(item)[1].get('isPointOf')
            marked.append((order, oh.label(item).lower(),
                           ('%s: %s' % (oh.label(item), oh.display_state(item)), owner if owner in it else None, False)))
    return out + [x[2] for x in sorted(marked)]


def view_status():
    _, items = load()
    if items:
        m = Model(items)
        for text, link, problem in status_lines(m):
            icon = 'DefaultIconError.png' if problem else 'DefaultIconInfo.png'
            if link and link in items:
                kind = 'loc' if oh.semantics(items[link])[0].startswith('Location') else 'equip'
                folder(text, url(action=kind, name=link), icon)
            else:
                action_item(text, url(action='noop'), icon)
    end()


# ---- floor plan ----------------------------------------------------------------------------------

def plan_info(m, plan_def):
    """{location: (state, name, detail)}; state = problem/heating/ok/empty."""
    it = m.items
    problem_locs = set()
    for _, owner in m.problems():
        if owner in it:
            problem_locs.add(oh.semantics(it[owner])[1].get('hasLocation'))
    info = {}
    for loc, *_ in plan_def['areas']:
        if loc not in it or loc in info:
            continue
        if loc in problem_locs:
            state = 'problem'
        elif m.heating(loc):
            state = 'heating'
        elif m.equipment_at.get(loc) or m.points_at.get(loc):
            state = 'ok'
        else:
            state = 'empty'
        info[loc] = (state, oh.label(it[loc]), m.location_summary(loc))
    return info


def open_path(path):
    """Opens a plugin folder from anywhere (also from a skin menu or widget, where Container.Update can't)."""
    xbmc.executebuiltin('ActivateWindow(Programs,"%s",return)' % path)


def do_plan(floor):
    _, items = load()
    if not items:
        return
    plan_def = floorplan.plan(items, floor)
    if not plan_def:
        open_path(url(action='loc', name=floor))
        return
    m = Model(items)
    media = os.path.join(ADDON.getAddonInfo('path'), 'resources', 'media', '')
    texts = {'heating': S(32017), 'problem': S(32018), 'keys': S(32019), 'list': S(32016)}
    title = oh.label(items[floor]) if floor in items else floor
    sel = floorplan.show(title, plan_def, plan_info(m, plan_def), media, texts)
    if sel == 'LIST':
        open_path(url(action='loc', name=floor))
    elif sel:
        open_path(url(action='loc', name=sel))


# ---- Aeon Nox 5 main menu entry ----------------------------------------------------------------------
# Aeon Nox 5 keeps its main menu in skin strings Custom<N>HomeItem.* (Label, Path, Icon, Widget, WidgetLabel,
# WidgetType; Includes_Home.xml). Skin.SetString changes them live, no skin file is patched. Other skins store
# their menu differently - see README. RunAddon has no commas, so no quoting issues in Skin.SetString.
AN5 = 'skin.aeon.nox.5'
MENU_PATH = 'RunAddon(plugin.program.xderecx.openhab)'
WIDGET_PATH = 'plugin://plugin.program.xderecx.openhab/?action=status'
SLOTS = range(1, 7)


def an5_slot_with_us():
    for n in SLOTS:
        if xbmc.getInfoLabel('Skin.String(Custom%dHomeItem.Path)' % n) == MENU_PATH:
            return n
    return None


def an5_free_slot():
    for n in SLOTS:
        if not xbmc.getInfoLabel('Skin.String(Custom%dHomeItem.Label)' % n) and \
                not xbmc.getInfoLabel('Skin.String(Custom%dHomeItem.Path)' % n):
            return n
    return None


def an5_set_widget(n):
    xbmc.executebuiltin('Skin.SetString(Custom%dHomeItem.Widget,%s)' % (n, WIDGET_PATH))
    xbmc.executebuiltin('Skin.SetString(Custom%dHomeItem.WidgetLabel,%s)' % (n, S(32010)))
    xbmc.executebuiltin('Skin.SetString(Custom%dHomeItem.WidgetType,%s)' % (n, ADDON.getSetting('widgettype') or '1'))


def do_addmenu():
    if xbmc.getSkinDir() != AN5:
        xbmcgui.Dialog().ok(NAME, S(32025))
        return
    label = S(32036)
    n = an5_slot_with_us()
    if n:
        xbmcgui.Dialog().ok(NAME, S(32026) % (label, n))
        return
    n = an5_free_slot()
    if not n:
        xbmcgui.Dialog().ok(NAME, S(32027))
        return
    if not xbmcgui.Dialog().yesno(NAME, S(32028) % (label, n)):
        return
    xbmc.executebuiltin('Skin.SetString(Custom%dHomeItem.Label,%s)' % (n, label))
    xbmc.executebuiltin('Skin.SetString(Custom%dHomeItem.Path,%s)' % (n, MENU_PATH))
    xbmc.executebuiltin('Skin.SetString(Custom%dHomeItem.Icon,%s)' % (
        n, 'special://home/addons/plugin.program.xderecx.openhab/icon.png'))
    an5_set_widget(n)
    xbmc.sleep(300)
    ok = xbmc.getInfoLabel('Skin.String(Custom%dHomeItem.Path)' % n) == MENU_PATH
    notify(S(32029) % n if ok else S(32030), xbmcgui.NOTIFICATION_INFO if ok else xbmcgui.NOTIFICATION_ERROR)
    if ok:
        xbmc.executebuiltin('ReloadSkin()')


def do_setwidget():
    n = an5_slot_with_us() if xbmc.getSkinDir() == AN5 else None
    if not n:
        xbmcgui.Dialog().ok(NAME, S(32034))
        return
    an5_set_widget(n)
    notify(S(32035) % (ADDON.getSetting('widgettype') or '1'))
    xbmc.executebuiltin('ReloadSkin()')


def do_removemenu():
    n = an5_slot_with_us()
    label = S(32036)
    if not n:
        xbmcgui.Dialog().ok(NAME, S(32031) % label)
        return
    if not xbmcgui.Dialog().yesno(NAME, S(32032) % (label, n)):
        return
    for key in ('Label', 'Path', 'Icon', 'Widget', 'WidgetLabel', 'WidgetType'):
        xbmc.executebuiltin('Skin.Reset(Custom%dHomeItem.%s)' % (n, key))
    notify(S(32033))
    xbmc.executebuiltin('ReloadSkin()')


# ---- point actions -------------------------------------------------------------------------------

def temperature_choices(item):
    sd = item.get('stateDescription') or {}
    lo = sd.get('minimum') if sd.get('minimum') is not None else 5
    hi = sd.get('maximum') if sd.get('maximum') is not None else 30
    step = sd.get('step') or 0.5
    vals, v = [], float(lo)
    while v <= float(hi) + 1e-9 and len(vals) < 200:
        vals.append(round(v, 2))
        v += float(step)
    return vals


def do_point(name):
    c, items = load()
    if not items or name not in items:
        return
    it = items[name]
    lbl, typ = oh.label(it), it.get('type', '')
    owner = oh.semantics(it)[1].get('isPointOf')
    if owner in items:
        lbl = '%s – %s' % (oh.label(items[owner]), lbl)
    if oh.read_only(it):
        notify('%s: %s' % (lbl, oh.display_state(it)))
        return
    command = None
    opts = oh.options(it)
    if typ == 'Switch':
        command = 'OFF' if it.get('state') == 'ON' else 'ON'
    elif opts:
        cur = it.get('state')
        i = xbmcgui.Dialog().select(lbl, [('● ' if v == cur else '   ') + l for v, l in opts])
        command = opts[i][0] if i >= 0 else None
    elif typ.startswith('Number:Temperature'):
        vals = temperature_choices(it)
        cur = oh.number(it)
        pre = min(range(len(vals)), key=lambda k: abs(vals[k] - cur)) if cur is not None else 0
        i = xbmcgui.Dialog().select('%s %s' % (lbl, S(32024) % oh.display_state(it)),
                                    [('%g °C' % v) for v in vals], preselect=pre)
        command = ('%g' % vals[i]) if i >= 0 else None
    elif typ in ('Dimmer', 'Rollershutter'):
        vals = list(range(0, 101, 10))
        i = xbmcgui.Dialog().select(lbl, ['%d %%' % v for v in vals])
        command = str(vals[i]) if i >= 0 else None
    elif typ.startswith('Number'):
        cur = oh.number(it)
        command = xbmcgui.Dialog().input(lbl, '' if cur is None else ('%g' % cur), type=xbmcgui.INPUT_NUMERIC) or None
    elif typ == 'String':
        cur = it.get('state') if it.get('state') not in ('NULL', 'UNDEF') else ''
        command = xbmcgui.Dialog().input(lbl, cur) or None
    else:
        notify('%s: %s' % (lbl, oh.display_state(it)))
        return
    if command is None:
        return
    try:
        c.send_command(name, command)
    except oh.OpenHABError as err:
        notify(S(32022) % err, xbmcgui.NOTIFICATION_ERROR)
        return
    notify('%s → %s' % (lbl, command))
    time.sleep(1)  # let openHAB update the state before the list is redrawn
    xbmc.executebuiltin('Container.Refresh')


# ---- router --------------------------------------------------------------------------------------

def main():
    action = PARAMS.get('action')
    name = PARAMS.get('name', '')
    if action is None:
        view_root()
    elif action == 'status':
        view_status()
    elif action == 'loc':
        view_location(name)
    elif action == 'equip':
        view_equipment(name)
    elif action == 'other':
        view_other()
    elif action == 'point':
        do_point(name)
    elif action == 'plan':
        do_plan(name)
    elif action == 'addmenu':
        do_addmenu()
        xbmc.executebuiltin('Container.Refresh')
    elif action == 'removemenu':
        do_removemenu()
    elif action == 'setwidget':
        do_setwidget()
    elif action == 'settings':
        ADDON.openSettings()
        xbmc.executebuiltin('Container.Refresh')


if __name__ == '__main__':
    main()
