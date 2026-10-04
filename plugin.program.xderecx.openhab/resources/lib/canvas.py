# -*- coding: utf-8 -*-
"""Tiny pure-Python RGB canvas with PNG read/write, rectangles, tinted alpha masks (icons) and bitmap-font text.
Kodi on CoreELEC has no Pillow, so the house status background is drawn with this. Only the add-on's own
assets are read: 8-bit greyscale PNGs (colour type 0) used as alpha masks."""
import json
import struct
import zlib


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read_mask(path):
    """(width, height, bytes) of an 8-bit greyscale, non-interlaced PNG (the grey value is used as alpha)."""
    with open(path, 'rb') as f:
        data = f.read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not a PNG: %s' % path)
    pos, idat, w = 8, b'', 0
    while pos < len(data):
        length, ctype = struct.unpack('>I4s', data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + length]
        if ctype == b'IHDR':
            w, h, depth, colour, _, _, interlace = struct.unpack('>IIBBBBB', chunk)
            if depth != 8 or colour != 0 or interlace:
                raise ValueError('unsupported PNG (need 8-bit grey): %s' % path)
        elif ctype == b'IDAT':
            idat += chunk
        elif ctype == b'IEND':
            break
        pos += 12 + length
    raw = zlib.decompress(idat)
    out = bytearray(w * h)
    prev = bytearray(w)
    i = 0
    for y in range(h):
        ftype = raw[i]
        line = bytearray(raw[i + 1:i + 1 + w])
        i += 1 + w
        if ftype == 1:
            for x in range(1, w):
                line[x] = (line[x] + line[x - 1]) & 255
        elif ftype == 2:
            for x in range(w):
                line[x] = (line[x] + prev[x]) & 255
        elif ftype == 3:
            for x in range(w):
                left = line[x - 1] if x else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 255
        elif ftype == 4:
            for x in range(w):
                left = line[x - 1] if x else 0
                upleft = prev[x - 1] if x else 0
                line[x] = (line[x] + _paeth(left, prev[x], upleft)) & 255
        out[y * w:(y + 1) * w] = line
        prev = line
    return w, h, bytes(out)


def hexcolour(argb):
    """'FFRRGGBB' or 'RRGGBB' -> (r, g, b)."""
    s = argb[-6:]
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


class Font:
    def __init__(self, png, js):
        self.w, self.h, self.atlas = read_mask(png)
        meta = json.load(open(js, encoding='utf-8'))
        self.height, self.pad, self.glyphs = meta['height'], meta['pad'], meta['glyphs']
        self._cache = {}

    def glyph(self, ch):
        """(advance, cell width, [(dx, dy, alpha)] non-zero pixels) or None for unknown characters."""
        if ch in self._cache:
            return self._cache[ch]
        g = self.glyphs.get(ch)
        if not g:
            self._cache[ch] = None
            return None
        cx, cw, adv = g
        pts = []
        for dy in range(self.height):
            row = dy * self.w + cx
            for dx in range(cw):
                a = self.atlas[row + dx]
                if a:
                    pts.append((dx - self.pad, dy, a))
        self._cache[ch] = (adv, cw, pts)
        return self._cache[ch]

    def width(self, text):
        return sum((self.glyph(c) or self.glyph('?'))[0] for c in text)


class Canvas:
    def __init__(self, w, h, rgb=(16, 18, 21)):
        self.w, self.h = w, h
        self.px = bytearray(bytes(rgb) * (w * h))

    def rect(self, x, y, w, h, rgb):
        x0, y0, x1, y1 = max(0, x), max(0, y), min(self.w, x + w), min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(rgb) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            self.px[i:i + len(row)] = row

    def _blend(self, i, rgb, a):
        p = self.px
        inv = 255 - a
        p[i] = (p[i] * inv + rgb[0] * a) // 255
        p[i + 1] = (p[i + 1] * inv + rgb[1] * a) // 255
        p[i + 2] = (p[i + 2] * inv + rgb[2] * a) // 255

    def mask(self, x, y, mask, rgb):
        """Draws a (w, h, bytes) alpha mask in a colour (icons)."""
        mw, mh, data = mask
        for dy in range(mh):
            yy = y + dy
            if not 0 <= yy < self.h:
                continue
            base = dy * mw
            for dx in range(mw):
                a = data[base + dx]
                xx = x + dx
                if a and 0 <= xx < self.w:
                    self._blend((yy * self.w + xx) * 3, rgb, a)

    def text(self, x, y, text, font, rgb, max_width=None):
        """Draws text with its top at y; cut with '…' at max_width. Returns the x after the text."""
        if max_width is not None and font.width(text) > max_width:
            while text and font.width(text + '…') > max_width:
                text = text[:-1]
            text += '…'
        for ch in text:
            g = font.glyph(ch) or font.glyph('?')
            adv, _, pts = g
            for dx, dy, a in pts:
                xx, yy = x + dx, y + dy
                if 0 <= xx < self.w and 0 <= yy < self.h:
                    self._blend((yy * self.w + xx) * 3, rgb, a)
            x += adv
        return x

    def save_png(self, path, level=6):
        rows = bytearray()
        stride = self.w * 3
        for y in range(self.h):
            rows.append(0)
            rows += self.px[y * stride:(y + 1) * stride]

        def chunk(t, d):
            return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
        with open(path, 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n')
            f.write(chunk(b'IHDR', struct.pack('>IIBBBBB', self.w, self.h, 8, 2, 0, 0, 0)))
            f.write(chunk(b'IDAT', zlib.compress(bytes(rows), level)))
            f.write(chunk(b'IEND', b''))
