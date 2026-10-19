# -*- coding: utf-8 -*-
"""Tiny pure-Python RGB canvas with PNG read/write, rectangles, tinted alpha masks (icons) and bitmap-font text.
Kodi on CoreELEC has no Pillow, so the house status background is drawn with this. Reads 8-bit PNGs: the
add-on's greyscale assets as alpha masks, and colour images (e.g. Kodi's weather icons) scaled down."""
import json
import struct
import zlib


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}   # PNG colour type -> bytes per pixel (8-bit)


def read_png(path):
    """(width, height, channels, bytes) of an 8-bit, non-interlaced grey / RGB / grey+alpha / RGBA PNG."""
    with open(path, 'rb') as f:
        data = f.read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not a PNG: %s' % path)
    pos, idat, w, bpp = 8, b'', 0, 1
    while pos < len(data):
        length, ctype = struct.unpack('>I4s', data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + length]
        if ctype == b'IHDR':
            w, h, depth, colour, _, _, interlace = struct.unpack('>IIBBBBB', chunk)
            if depth != 8 or colour not in CHANNELS or interlace:
                raise ValueError('unsupported PNG (need 8-bit grey/RGB/RGBA, not interlaced): %s' % path)
            bpp = CHANNELS[colour]
        elif ctype == b'IDAT':
            idat += chunk
        elif ctype == b'IEND':
            break
        pos += 12 + length
    raw = zlib.decompress(idat)
    stride = w * bpp
    out = bytearray(stride * h)
    prev = bytearray(stride)
    i = 0
    for y in range(h):
        ftype = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        if ftype == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif ftype == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif ftype == 3:
            for x in range(stride):
                left = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 255
        elif ftype == 4:
            for x in range(stride):
                left = line[x - bpp] if x >= bpp else 0
                upleft = prev[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + _paeth(left, prev[x], upleft)) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, bpp, bytes(out)


def read_mask(path):
    """(width, height, bytes) of an 8-bit greyscale PNG (the grey value is used as alpha)."""
    w, h, bpp, data = read_png(path)
    if bpp != 1:
        raise ValueError('need an 8-bit grey PNG: %s' % path)
    return w, h, data


def read_image(path, size):
    """A colour PNG (RGBA/RGB/grey) scaled down to size x size (box filter): (size, size, RGBA bytes)."""
    w, h, bpp, data = read_png(path)
    out = bytearray(size * size * 4)
    for oy in range(size):
        y0, y1 = oy * h // size, max(oy * h // size + 1, (oy + 1) * h // size)
        for ox in range(size):
            x0, x1 = ox * w // size, max(ox * w // size + 1, (ox + 1) * w // size)
            r = g = b = al = n = 0
            for yy in range(y0, y1):
                base = (yy * w) * bpp
                for xx in range(x0, x1):
                    p = base + xx * bpp
                    if bpp >= 3:
                        a = data[p + 3] if bpp == 4 else 255
                        r += data[p] * a; g += data[p + 1] * a; b += data[p + 2] * a
                    else:
                        a = data[p + 1] if bpp == 2 else 255
                        r += data[p] * a; g += data[p] * a; b += data[p] * a
                    al += a
                    n += 1
            o = (oy * size + ox) * 4
            if al:
                out[o], out[o + 1], out[o + 2] = r // al, g // al, b // al
            out[o + 3] = al // n
    return size, size, bytes(out)


def hexcolour(argb):
    """'FFRRGGBB' or 'RRGGBB' -> (r, g, b)."""
    s = argb[-6:]
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


class Font:
    def __init__(self, png, js):
        self.w, self.h, self.atlas = read_mask(png)
        meta = json.load(open(js, encoding='utf-8'))
        self.height, self.pad, self.glyphs = meta['height'], meta['pad'], meta['glyphs']
        self.ascent = meta.get('ascent', self.height)   # baseline below the top of a line
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

    def image(self, x, y, img):
        """Draws a (w, h, RGBA bytes) image with its alpha."""
        iw, ih, data = img
        for dy in range(ih):
            yy = y + dy
            if not 0 <= yy < self.h:
                continue
            for dx in range(iw):
                o = (dy * iw + dx) * 4
                a = data[o + 3]
                xx = x + dx
                if a and 0 <= xx < self.w:
                    self._blend((yy * self.w + xx) * 3, (data[o], data[o + 1], data[o + 2]), a)

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
