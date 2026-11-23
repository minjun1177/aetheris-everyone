"""Draw the app icon (same design as web/icon.svg) as PNG and ICO.

    python packaging/make_icons.py

Writes packaging/icon.png (1024px) and packaging/icon.ico. PyInstaller turns
the PNG into the macOS .icns itself.
"""

import os

from PIL import Image, ImageChops, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = 1024
SCALE = 4


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def draw(size: int = SIZE) -> Image.Image:
    big = size * SCALE
    unit = big / 64
    gradient = Image.new("RGB", (big, big))
    pixels = gradient.load()
    stops = [(0.0, (0x4F, 0x6B, 0xFF)), (0.55, (0x7B, 0x4C, 0xF5)), (1.0, (0xC0, 0x4C, 0xF0))]
    for y in range(big):
        for x in range(0, big, 4):
            t = (x + y) / (2 * big)
            for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
                if p0 <= t <= p1:
                    color = lerp(c0, c1, (t - p0) / (p1 - p0))
                    break
            for dx in range(4):
                if x + dx < big:
                    pixels[x + dx, y] = color
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=int(16 * unit), fill=255)
    icon = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    icon.paste(gradient, (0, 0), mask)

    ring = Image.new("L", (big, big), 0)
    rd = ImageDraw.Draw(ring)
    cx, cy, rx, ry, width = 32 * unit, 33 * unit, 22 * unit, 8.5 * unit, 2.4 * unit
    rd.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), outline=255, width=int(width))
    ring = ring.rotate(24, center=(cx, cy), resample=Image.BICUBIC)
    white = Image.new("RGBA", (big, big), (255, 255, 255, 255))
    icon = Image.composite(white, icon, ImageChops.multiply(ring.point(lambda v: int(v * 0.45)), mask))

    star = [(32, 12), (36.6, 27.4), (52, 32), (36.6, 36.6), (32, 52), (27.4, 36.6), (12, 32), (27.4, 27.4)]
    layer = ImageDraw.Draw(icon)
    layer.polygon([(x * unit, y * unit) for x, y in star], fill=(255, 255, 255, 255))
    r = 3.2 * unit
    layer.ellipse((49 * unit - r, 19 * unit - r, 49 * unit + r, 19 * unit + r), fill=(255, 255, 255, 235))
    return icon.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    image = draw()
    image.save(os.path.join(HERE, "icon.png"))
    image.save(os.path.join(HERE, "icon.ico"), sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print("wrote", os.path.join(HERE, "icon.png"), "and icon.ico")
