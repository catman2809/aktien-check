"""Erzeugt die App-Icons mit Kerzi, der Chartkerze (static/icon-*.png, apple-touch-icon.png).

Aufruf: python tools/make_icons.py
Kerzi ist in einem 100 × 120-Raster gezeichnet – dieselben Maße wie das SVG in index.html (kerziSVG).
"""
from pathlib import Path

from PIL import Image, ImageDraw

STATIC = Path(__file__).resolve().parent.parent / "static"
BG = (31, 79, 216)          # Markenblau (--accent)
BODY = (27, 175, 122)       # Kerzengrün
FACE = (11, 61, 39)
WICK = (255, 255, 255)
SS = 4                      # Supersampling für glatte Kanten


def kerzi(draw, ox, oy, k):
    """Kerzi (jubelnd, Arme hoch) mit Ursprung (ox, oy) und Maßstab k Pixel je Rastereinheit."""
    P = lambda x, y: (ox + x * k, oy + y * k)

    def line(a, b, w, col):
        draw.line([P(*a), P(*b)], fill=col, width=round(w * k))
        for x, y in (a, b):  # runde Enden
            cx, cy = P(x, y)
            r = w * k / 2
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    line((50, 6), (50, 114), 5, WICK)
    line((30, 52), (12, 34), 7, BODY)
    line((70, 52), (88, 34), 7, BODY)
    draw.rounded_rectangle([P(28, 26), P(72, 96)], radius=9 * k, fill=BODY)
    for ex in (41, 59):
        cx, cy = P(ex, 50)
        r = 4 * k
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=FACE)
    x0, y0 = P(39, 55)
    x1, y1 = P(61, 73)
    draw.arc([x0, y0, x1, y1], start=25, end=155, fill=FACE, width=round(3.4 * k))


def icon(size, rounded, content):
    """content: Anteil der Kantenlänge, den Kerzi in der Höhe einnimmt."""
    S = size * SS
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if rounded:
        d.rounded_rectangle([0, 0, S - 1, S - 1], radius=round(S * 0.225), fill=BG)
    else:
        d.rectangle([0, 0, S, S], fill=BG)
    k = S * content / 120
    kerzi(d, (S - 100 * k) / 2, (S - 120 * k) / 2, k)
    im = im.resize((size, size), Image.LANCZOS)
    return im if rounded else im.convert("RGB")


if __name__ == "__main__":
    icon(192, True, 0.74).save(STATIC / "icon-192.png")
    icon(512, True, 0.74).save(STATIC / "icon-512.png")
    icon(512, False, 0.58).save(STATIC / "icon-maskable-512.png")   # Inhalt im sicheren Kreis (80 %)
    icon(180, False, 0.70).save(STATIC / "apple-touch-icon.png")    # iOS rundet selbst ab, keine Transparenz
    print("Icons geschrieben nach", STATIC)
