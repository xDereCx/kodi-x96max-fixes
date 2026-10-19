# -*- coding: utf-8 -*-
"""The house model from openHAB items (semantic model + 'kodi' metadata). No Kodi imports, so the plugin, the
background service and tests can all use it."""
import openhab as oh

ROLES = ('temperature', 'setpoint', 'mode', 'heating')   # kodi metadata values on points (see README)


def flag(cfg, key):
    return str(cfg.get(key, '')).lower() in ('true', '1', 'yes')

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
