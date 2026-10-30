"""Gera a moldura e a seta do minimapa (Shroudweave Minimap).

Anel fino e discreto, com um MARCADOR DE NORTE FIXO (triangulo da cor de destaque,
sem letras) que fica legivel mesmo com o mapa girando. A cor de destaque e um
parametro, entao geramos varias versoes em cores/<cor>/ para trocar dentro do jogo.

Saida: cores/<cor>/embervale_minimap_frame.rgba (1024x1024) e .../embervale_player_arrow.rgba
(512x512), RGBA 8 bits (mesmo formato do mod). saida/ recebe a cor padrao (ambar).
"""
import math
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'saida')
CORES = os.path.join(HERE, 'cores')
MOD = r'C:\Program Files (x86)\Steam\steamapps\common\Enshrouded\mods\minimap_mod'

# cores de destaque (so o marcador de norte e o brilho da seta mudam de cor)
COLORS = {
    'ambar': (255, 181, 71),
    'azul': (86, 196, 255),
    'verde': (82, 214, 130),
    'vermelho': (255, 96, 96),
    'branco': (236, 242, 250),
}
DEFAULT_COLOR = 'ambar'

RING_TOP = (30, 38, 47)
RING_BOTTOM = (11, 15, 20)
RING_ALPHA = 0.88
R_INNER, R_OUTER = 369.0, 400.0   # anel mais fino (31 px) do que antes
CARDINALS = {'N': -90, 'E': 0, 'S': 90, 'W': 180}  # so o N ganha o marcador grande

SIZE = 1024
C = SIZE / 2


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def band(r, a, b, aa=0.75):
    return smoothstep(a - aa, a + aa, r) * (1 - smoothstep(b - aa, b + aa, r))


class Canvas:
    def __init__(self, size):
        self.rgb = np.zeros((size, size, 3), np.float32)
        self.a = np.zeros((size, size), np.float32)

    def over(self, color, alpha):
        col = np.asarray(color, np.float32) / 255
        col = col if col.ndim == 3 else np.broadcast_to(col, self.rgb.shape)
        alpha = alpha.astype(np.float32)
        self.rgb = col * alpha[..., None] + self.rgb * (1 - alpha[..., None])
        self.a = alpha + self.a * (1 - alpha)

    def over_image(self, im):
        arr = np.asarray(im, np.float32) / 255
        self.over(arr[..., :3] * 255, arr[..., 3])

    def to_image(self):
        a = np.clip(self.a, 0, 1)
        rgb = np.where(a[..., None] > 1e-4, self.rgb / np.maximum(a[..., None], 1e-4), 0)
        out = np.dstack([np.clip(rgb, 0, 1) * 255, a * 255]).round().astype(np.uint8)
        return Image.fromarray(out, 'RGBA')


def frame(accent):
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32) + 0.5
    r = np.hypot(x - C, y - C)
    cv = Canvas(SIZE)

    # sombras externa e interna (profundidade)
    cv.over((0, 0, 0), 0.36 * (1 - smoothstep(R_OUTER - 2, R_OUTER + 30, r)) * (r > R_OUTER - 2))
    cv.over((0, 0, 0), 0.34 * smoothstep(R_INNER - 22, R_INNER, r) * (r < R_INNER + 1))

    # anel escuro fino com leve degrade (efeito vidro)
    t = np.clip((y - (C - R_OUTER)) / (2 * R_OUTER), 0, 1)[..., None]
    ring_col = (np.array(RING_TOP) * (1 - t) + np.array(RING_BOTTOM) * t)
    cv.over(ring_col, RING_ALPHA * band(r, R_INNER, R_OUTER))
    # filetes claros discretos
    cv.over((255, 255, 255), 0.30 * band(r, R_INNER, R_INNER + 1.8, 0.6))
    cv.over((255, 255, 255), 0.10 * band(r, R_OUTER - 1.4, R_OUTER, 0.6))

    # detalhes em alta resolucao (4x) e depois reduz
    k = 4
    hi = Image.new('RGBA', (SIZE * k, SIZE * k))
    d = ImageDraw.Draw(hi)

    def P(ang, rad):
        th = math.radians(ang)
        return (k * (C + rad * math.cos(th)), k * (C + rad * math.sin(th)))

    # marcas discretas a cada 30 graus (menos no N, que tem o marcador)
    for deg in range(0, 360, 30):
        if abs(((deg - (-90 % 360)) + 180) % 360 - 180) < 16:
            continue
        cardinal = deg % 90 == 0
        r0 = R_INNER + (7 if cardinal else 10)
        d.line([P(deg, r0), P(deg, R_OUTER - 5)], fill=(226, 234, 242, 190 if cardinal else 90),
               width=k * (5 if cardinal else 3))

    # MARCADOR DE NORTE: triangulo da cor de destaque, apontando para fora (sem letra)
    tip = P(-90, R_OUTER + 7)
    halfw = 15
    base_l = P(-90 - halfw, R_INNER + 1)
    base_r = P(-90 + halfw, R_INNER + 1)
    d.polygon([tip, base_r, base_l], fill=(10, 13, 18, 255))          # contorno escuro
    tip2 = P(-90, R_OUTER + 2)
    bl2 = P(-90 - halfw + 2, R_INNER + 5)
    br2 = P(-90 + halfw - 2, R_INNER + 5)
    d.polygon([tip2, br2, bl2], fill=accent + (255,))                 # preenchimento colorido

    cv.over_image(hi.resize((SIZE, SIZE), Image.LANCZOS))
    return cv.to_image()


def arrow(accent):
    S, k = 512, 4
    pts = [(256, 40), (420, 452), (256, 362), (92, 452)]
    big = [(x * k, y * k) for x, y in pts]

    glow = Image.new('RGBA', (S * k, S * k))
    gd = ImageDraw.Draw(glow)
    gd.polygon(big, fill=accent + (255,))
    gd.line(big + [big[0]], fill=accent + (255,), width=k * 34, joint='curve')
    glow = glow.filter(ImageFilter.GaussianBlur(k * 12))
    ga = np.asarray(glow, np.float32).copy()
    ga[..., 3] = np.minimum(ga[..., 3] * 1.6, 235)
    glow = Image.fromarray(ga.astype(np.uint8), 'RGBA')

    body = Image.new('RGBA', (S * k, S * k))
    d = ImageDraw.Draw(body)
    d.polygon(big, fill=(10, 14, 19, 255))
    inset = shrink(pts, 15)
    d.polygon([(px * k, py * k) for px, py in inset], fill=(255, 255, 255, 255))
    d.polygon([(inset[0][0] * k, inset[0][1] * k), (inset[1][0] * k, inset[1][1] * k),
               (inset[2][0] * k, inset[2][1] * k)], fill=(214, 224, 234, 255))

    return Image.alpha_composite(glow, body).resize((S, S), Image.LANCZOS)


def shrink(pts, dist):
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    lines = []
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        nx, ny = y1 - y0, -(x1 - x0)
        ln = math.hypot(nx, ny); nx, ny = nx / ln, ny / ln
        if (cx - x0) * nx + (cy - y0) * ny < 0:
            nx, ny = -nx, -ny
        lines.append(((x0 + nx * dist, y0 + ny * dist), (x1 - x0, y1 - y0)))
    res = []
    for i in range(n):
        (p, dp), (q, dq) = lines[i - 1], lines[i]
        den = dp[0] * dq[1] - dp[1] * dq[0]
        tt = ((q[0] - p[0]) * dq[1] - (q[1] - p[1]) * dq[0]) / den
        res.append((p[0] + dp[0] * tt, p[1] + dp[1] * tt))
    return res


def preview(path):
    """Amostra das cores sobre um pedaco do mapa real, no tamanho do jogo."""
    raw = open(os.path.join(MOD, 'embervale_realmap_default_2048.rgba'), 'rb').read()
    world = Image.frombytes('RGBA', (2048, 2048), raw).convert('RGB')
    crop = world.crop((760, 1180, 950, 1370)).resize((95, 95), Image.BILINEAR).resize((760, 760), Image.NEAREST)
    cells = []
    for name in COLORS:
        f = frame(COLORS[name]); a = arrow(COLORS[name])
        base = Image.new('RGBA', (SIZE, SIZE), (24, 22, 20, 255))
        mask = Image.new('L', (SIZE, SIZE))
        ImageDraw.Draw(mask).ellipse([C - 372, C - 372, C + 372, C + 372], fill=255)
        layer = Image.new('RGBA', (SIZE, SIZE)); layer.paste(crop, (int(C - 380), int(C - 380)))
        base.paste(layer, (0, 0), mask)
        base.alpha_composite(f)
        base.alpha_composite(a.resize((96, 96), Image.LANCZOS), (int(C - 48), int(C - 48)))
        cells.append(base.resize((360, 360), Image.LANCZOS))
    sheet = Image.new('RGBA', (360 * len(cells), 360), (18, 20, 24, 255))
    for i, c in enumerate(cells):
        sheet.paste(c, (360 * i, 0))
    sheet.convert('RGB').save(path)


def main():
    os.makedirs(CORES, exist_ok=True)
    for name, accent in COLORS.items():
        d = os.path.join(CORES, name)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'embervale_minimap_frame.rgba'), 'wb').write(frame(accent).tobytes())
        open(os.path.join(d, 'embervale_player_arrow.rgba'), 'wb').write(arrow(accent).tobytes())
    # saida/ = cor padrao (o instalador empacota isto como "visual_moderno")
    os.makedirs(OUT, exist_ok=True)
    for fn in ('embervale_minimap_frame.rgba', 'embervale_player_arrow.rgba'):
        shutil.copy2(os.path.join(CORES, DEFAULT_COLOR, fn), os.path.join(OUT, fn))
    if '--sem-preview' not in sys.argv:
        preview(os.path.join(OUT, 'preview.png'))
    print('gerado:', ', '.join(COLORS), '| padrao:', DEFAULT_COLOR)


if __name__ == '__main__':
    main()
