"""Novos visuais do minimapa (moldura 1024x1024 + seta 512x512, RGBA 8 bits, mesmo formato do mod).

Estilos:
  vidro    - anel de vidro escuro translÃºcido, vinheta suave na borda do mapa, brilho na cor de destaque
  tatico   - HUD fino: dois filetes, rÃ©gua de graus, colchetes nos pontos cardeais
  premium  - aro grafite metÃ¡lico com reflexo, filete na cor de destaque e marcaÃ§Ãµes gravadas

Uso:
  python gerar_visual_v2.py --preview            # sÃ³ gera a folha de comparaÃ§Ã£o (saida/estilos_v2.png)
  python gerar_visual_v2.py <estilo>             # gera cores/<cor>/ com esse estilo para todas as cores
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = r'C:\Program Files (x86)\Steam\steamapps\common\Enshrouded\mods\minimap_mod'
COLORS = {
    'ambar': (255, 181, 71), 'azul': (86, 196, 255), 'verde': (82, 214, 130),
    'vermelho': (255, 96, 96), 'branco': (236, 242, 250),
}
SIZE = 1024
C = SIZE / 2
R_MAP = 372.0          # raio onde o mod recorta o mapa
K = 4                  # super-amostragem para os detalhes vetoriais

Y, X = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32) + 0.5
R = np.hypot(X - C, Y - C)
ANG = np.degrees(np.arctan2(Y - C, X - C))          # 0 = direita, -90 = topo


def ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def band(r, a, b, aa=0.8):
    return ss(a - aa, a + aa, r) * (1 - ss(b - aa, b + aa, r))


class Canvas:
    def __init__(self, size=SIZE):
        self.rgb = np.zeros((size, size, 3), np.float32)
        self.a = np.zeros((size, size), np.float32)

    def over(self, color, alpha):
        col = np.asarray(color, np.float32) / 255
        col = col if col.ndim == 3 else np.broadcast_to(col, self.rgb.shape)
        alpha = np.clip(alpha, 0, 1).astype(np.float32)
        self.rgb = col * alpha[..., None] + self.rgb * (1 - alpha[..., None])
        self.a = alpha + self.a * (1 - alpha)

    def over_image(self, im):
        arr = np.asarray(im, np.float32) / 255
        self.over(arr[..., :3] * 255, arr[..., 3])

    def image(self):
        a = np.clip(self.a, 0, 1)
        rgb = np.where(a[..., None] > 1e-4, self.rgb / np.maximum(a[..., None], 1e-4), 0)
        return Image.fromarray(np.dstack([np.clip(rgb, 0, 1) * 255, a * 255]).round().astype(np.uint8), 'RGBA')


def hi_canvas():
    im = Image.new('RGBA', (SIZE * K, SIZE * K))
    return im, ImageDraw.Draw(im)


def P(ang, rad):
    th = math.radians(ang)
    return (K * (C + rad * math.cos(th)), K * (C + rad * math.sin(th)))


def down(im):
    return im.resize((SIZE, SIZE), Image.LANCZOS)


def glow_layer(im, radius, strength=1.0):
    g = im.filter(ImageFilter.GaussianBlur(radius))
    a = np.asarray(g, np.float32).copy()
    a[..., 3] = np.minimum(a[..., 3] * strength, 255)
    return Image.fromarray(a.astype(np.uint8), 'RGBA')


def ang_dist(a, b):
    return np.abs((a - b + 180) % 360 - 180)


# ------------------------------------------------------------------ VIDRO
def frame_vidro(acc):
    cv = Canvas()
    ri, ro = R_MAP - 4, R_MAP + 20
    # vinheta interna: escurece a borda do mapa de forma suave (profundidade)
    cv.over((6, 9, 14), 0.55 * ss(ri - 70, ri, R) * (R < ri + 1))
    # sombra externa difusa
    cv.over((0, 0, 0), 0.40 * (1 - ss(ro, ro + 36, R)) * (R > ro - 1))
    # anel de vidro: escuro translÃºcido com degradÃª vertical
    t = np.clip((Y - (C - ro)) / (2 * ro), 0, 1)[..., None]
    col = np.array((34, 44, 58)) * (1 - t) + np.array((10, 14, 20)) * t
    cv.over(col, 0.78 * band(R, ri, ro))
    # reflexo de vidro na metade de cima
    refl = band(R, ri + 3, ri + 11, 2.5) * np.clip(-(Y - C) / ro, 0, 1) ** 1.5
    cv.over((255, 255, 255), 0.16 * refl)
    # filetes: interno claro, externo bem sutil
    cv.over((255, 255, 255), 0.42 * band(R, ri, ri + 1.6, 0.6))
    cv.over((255, 255, 255), 0.12 * band(R, ro - 1.2, ro, 0.6))
    # arco de destaque no topo, sumindo para os lados (brilho na cor escolhida)
    w = np.exp(-(ang_dist(ANG, -90) / 38) ** 2)
    cv.over(acc, 0.95 * w * band(R, ro - 4.5, ro - 1.5, 0.7))
    halo = Canvas(); halo.over(acc, w * band(R, ro - 6, ro, 1.0))
    cv.over_image(glow_layer(halo.image(), 10, 1.4))

    im, d = hi_canvas()
    for deg in range(0, 360, 45):
        if deg == 270:
            continue
        x, y = P(deg, (ri + ro) / 2)
        rr = K * (3.2 if deg % 90 == 0 else 2.0)
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(230, 238, 246, 200 if deg % 90 == 0 else 120))
    # indicador do topo: pÃ­lula na cor de destaque
    x, y = P(-90, (ri + ro) / 2)
    pw, ph = K * 26, K * 9
    d.rounded_rectangle([x - pw, y - ph, x + pw, y + ph], radius=ph, fill=(8, 11, 16, 255))
    d.rounded_rectangle([x - pw + K * 3, y - ph + K * 3, x + pw - K * 3, y + ph - K * 3], radius=ph - K * 3, fill=acc + (255,))
    cv.over_image(down(im))
    return cv.image()


# ------------------------------------------------------------------ TÃTICO
def frame_tatico(acc):
    cv = Canvas()
    ri, ro = R_MAP - 2, R_MAP + 24
    cv.over((4, 8, 12), 0.45 * ss(ri - 46, ri, R) * (R < ri + 1))
    cv.over((0, 0, 0), 0.30 * (1 - ss(ro, ro + 26, R)) * (R > ro - 1))
    # faixa escura translÃºcida bem leve
    cv.over((8, 12, 18), 0.62 * band(R, ri, ro))
    # filete interno na cor de destaque com brilho, externo branco fino
    inner = Canvas(); inner.over(acc, band(R, ri, ri + 2.4, 0.6))
    cv.over_image(glow_layer(inner.image(), 6, 1.2))
    cv.over(acc, band(R, ri, ri + 2.4, 0.6))
    cv.over((235, 242, 250), 0.55 * band(R, ro - 1.4, ro, 0.6))

    im, d = hi_canvas()
    # rÃ©gua de graus: a cada 5Â°, maior a cada 15Â° e 45Â°
    for deg in range(0, 360, 5):
        if ang_dist(np.float32(deg), np.float32(270)) < 9:
            continue
        big = deg % 45 == 0; mid = deg % 15 == 0
        L = 13 if big else (8 if mid else 4.5)
        a = 230 if big else (150 if mid else 80)
        d.line([P(deg, ro - 4 - L), P(deg, ro - 4)], fill=(232, 240, 248, a), width=K * (3 if big else 2))
    # colchetes nos pontos cardeais (menos o topo)
    for deg in (0, 90, 180):
        for s in (-1, 1):
            d.line([P(deg + s * 4, ro + 6), P(deg + s * 9, ro + 6)], fill=acc + (230,), width=K * 3)
    # topo: seta pequena apontando para dentro, na cor de destaque
    tip = P(-90, ri + 10); l = P(-90 - 4.2, ro + 4); r = P(-90 + 4.2, ro + 4)
    d.polygon([tip, r, l], fill=acc + (255,))
    cv.over_image(down(im))
    return cv.image()


# ------------------------------------------------------------------ PREMIUM
def frame_premium(acc):
    cv = Canvas()
    ri, ro = R_MAP - 4, R_MAP + 30
    cv.over((5, 6, 9), 0.50 * ss(ri - 56, ri, R) * (R < ri + 1))
    cv.over((0, 0, 0), 0.45 * (1 - ss(ro, ro + 40, R)) * (R > ro - 1))
    # aro grafite com luz vinda de cima-esquerda (metal escovado)
    light = np.cos(np.radians(ANG - (-135)))                  # 1 no canto de cima-esquerda
    prof = np.sin(np.clip((R - ri) / (ro - ri), 0, 1) * np.pi)  # bojo do aro
    base = 40 + 34 * light[..., None] * prof[..., None] + 26 * prof[..., None]
    col = np.concatenate([base * 0.92, base * 0.96, base * 1.06], axis=2)
    cv.over(np.clip(col, 0, 255), 0.97 * band(R, ri, ro))
    # brilho especular estreito
    spec = np.exp(-(ang_dist(ANG, -125) / 24) ** 2) * band(R, ri + 8, ri + 13, 1.5)
    cv.over((255, 255, 255), 0.35 * spec)
    # filete na cor de destaque por dentro e borda escura
    cv.over(acc, 0.95 * band(R, ri + 1, ri + 3.2, 0.6))
    cv.over((0, 0, 0), 0.7 * band(R, ri - 1, ri + 1, 0.6))
    cv.over((0, 0, 0), 0.6 * band(R, ro - 1.5, ro, 0.6))
    cv.over((255, 255, 255), 0.10 * band(R, ro - 3, ro - 1.5, 0.6))

    im, d = hi_canvas()
    # marcaÃ§Ãµes gravadas (escuro + realce claro deslocado)
    for deg in range(0, 360, 30):
        if deg == 270:
            continue
        big = deg % 90 == 0
        r0, r1 = ri + (9 if big else 13), ro - (7 if big else 11)
        d.line([P(deg, r0), P(deg, r1)], fill=(8, 9, 12, 230), width=K * (4 if big else 3))
        d.line([P(deg + 0.35, r0), P(deg + 0.35, r1)], fill=(255, 255, 255, 60), width=K * 1)
    # topo: losango na cor de destaque com borda escura
    cx, cy = P(-90, (ri + ro) / 2)
    s = K * 15
    d.polygon([(cx, cy - s), (cx + s * 0.75, cy), (cx, cy + s), (cx - s * 0.75, cy)], fill=(8, 9, 12, 255))
    s2 = s - K * 4
    d.polygon([(cx, cy - s2), (cx + s2 * 0.72, cy), (cx, cy + s2), (cx - s2 * 0.72, cy)], fill=acc + (255,))
    d.polygon([(cx, cy - s2), (cx + s2 * 0.72, cy), (cx, cy)], fill=tuple(min(255, c + 50) for c in acc) + (255,))
    cv.over_image(down(im))
    return cv.image()


# ------------------------------------------------------------------ SETAS
def _arrow(pts, acc, body, edge, glow_r, glow_a, inner=None, shade=None):
    S = 512
    big = [(x * K, y * K) for x, y in pts]
    out = Image.new('RGBA', (S * K, S * K))
    if glow_r:
        g = Image.new('RGBA', (S * K, S * K)); gd = ImageDraw.Draw(g)
        gd.polygon(big, fill=acc + (255,))
        out = Image.alpha_composite(out, glow_layer(g, K * glow_r, glow_a))
    # sombra projetada
    sh = Image.new('RGBA', (S * K, S * K)); sd = ImageDraw.Draw(sh)
    sd.polygon([(x, y + K * 14) for x, y in big], fill=(0, 0, 0, 170))
    out = Image.alpha_composite(out, sh.filter(ImageFilter.GaussianBlur(K * 9)))
    b = Image.new('RGBA', (S * K, S * K)); d = ImageDraw.Draw(b)
    d.polygon(big, fill=edge)
    if inner:
        d.polygon([(x * K, y * K) for x, y in inner], fill=body)
    if shade:
        d.polygon([(x * K, y * K) for x, y in shade], fill=tuple(int(c * 0.82) for c in body[:3]) + (255,))
    out = Image.alpha_composite(out, b)
    return out.resize((S, S), Image.LANCZOS)


def arrow_vidro(acc):
    pts = [(256, 46), (404, 440), (256, 352), (108, 440)]
    inner = [(256, 82), (378, 412), (256, 334), (134, 412)]
    shade = [(256, 82), (256, 334), (134, 412)]
    return _arrow(pts, acc, (250, 252, 255, 255), (12, 16, 22, 255), 16, 1.5, inner, shade)


def arrow_tatico(acc):
    pts = [(256, 40), (420, 448), (256, 380), (92, 448)]
    inner = [(256, 96), (372, 404), (256, 352), (140, 404)]
    return _arrow(pts, acc, (16, 20, 26, 255), acc + (255,), 12, 1.6, inner, None)


def arrow_premium(acc):
    pts = [(256, 40), (412, 452), (256, 372), (100, 452)]
    inner = [(256, 78), (386, 424), (256, 352), (126, 424)]
    shade = [(256, 78), (256, 352), (126, 424)]
    return _arrow(pts, acc, acc + (255,), (14, 15, 19, 255), 10, 1.2, inner, shade)


STYLES = {
    'vidro': (frame_vidro, arrow_vidro),
    'tatico': (frame_tatico, arrow_tatico),
    'premium': (frame_premium, arrow_premium),
}


def map_crop():
    raw = open(os.path.join(MOD, 'embervale_realmap_default_2048.rgba'), 'rb').read()
    world = Image.frombytes('RGBA', (2048, 2048), raw).convert('RGB')
    return world.crop((760, 1180, 950, 1370)).resize((760, 760), Image.BICUBIC)


def compose(fr, ar, crop, bg=(40, 44, 40)):
    base = Image.new('RGBA', (SIZE, SIZE), bg + (255,))
    mask = Image.new('L', (SIZE, SIZE))
    ImageDraw.Draw(mask).ellipse([C - R_MAP, C - R_MAP, C + R_MAP, C + R_MAP], fill=255)
    layer = Image.new('RGBA', (SIZE, SIZE)); layer.paste(crop, (int(C - 380), int(C - 380)))
    base.paste(layer, (0, 0), mask)
    base.alpha_composite(fr)
    base.alpha_composite(ar.resize((104, 104), Image.LANCZOS), (int(C - 52), int(C - 52)))
    return base


def preview(path):
    crop = map_crop()
    rows = []
    for name, (ff, af) in STYLES.items():
        cells = []
        for cname in ('azul', 'ambar', 'verde'):
            acc = COLORS[cname]
            cells.append(compose(ff(acc), af(acc), crop).resize((330, 330), Image.LANCZOS))
        rows.append((name, cells))
    W, H = 330 * 3 + 160, 330 * len(rows)
    sheet = Image.new('RGB', (W, H), (16, 18, 22))
    d = ImageDraw.Draw(sheet)
    for i, (name, cells) in enumerate(rows):
        d.text((18, 330 * i + 155), name.upper(), fill=(230, 235, 240))
        for j, c in enumerate(cells):
            sheet.paste(c.convert('RGB'), (160 + 330 * j, 330 * i))
    sheet.save(path)
    print('preview:', path)


def generate(style, outdir):
    ff, af = STYLES[style]
    for cname, acc in COLORS.items():
        d = os.path.join(outdir, cname)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'embervale_minimap_frame.rgba'), 'wb').write(ff(acc).tobytes())
        open(os.path.join(d, 'embervale_player_arrow.rgba'), 'wb').write(af(acc).tobytes())
    print('gerado', style, 'em', outdir)


if __name__ == '__main__':
    if '--preview' in sys.argv:
        preview(os.path.join(HERE, 'saida', 'estilos_v2.png'))
    else:
        generate(sys.argv[1], os.path.join(HERE, 'temas', sys.argv[1]))

