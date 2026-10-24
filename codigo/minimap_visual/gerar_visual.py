"""Gera a moldura e a seta do minimapa (Shroudweave Minimap) num estilo moderno.

Saida: saida/embervale_minimap_frame.rgba (1024x1024) e saida/embervale_player_arrow.rgba (512x512),
RGBA 8 bits sem alfa pre-multiplicado, o mesmo formato dos arquivos originais do mod.
Tambem gera saida/preview.png comparando com o visual original.

Medidas da moldura original (raio em px, centro 512): o mapa aparece ate ~r=360 e o anel
opaco vai de ~360 a ~440. O anel novo precisa cobrir a borda do mapa nessa mesma faixa.
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'saida')
MOD = r'C:\Program Files (x86)\Steam\steamapps\common\Enshrouded\mods\minimap_mod'

# ---------- estilo ----------
ACCENT = (255, 181, 71)          # ambar: pilula do N e brilho da seta
RING_TOP = (30, 38, 47)           # anel: tom de cima ...
RING_BOTTOM = (11, 15, 20)        # ... e de baixo (efeito vidro)
RING_ALPHA = 0.90
R_INNER, R_OUTER = 364.0, 410.0   # anel; no jogo o mapa aparece ate ~r=372 e continua por baixo do anel
LETTERS = {'N': -90, 'L': 0, 'S': 90, 'O': 180}   # pontos cardeais em portugues
FONT_BOLD = r'C:\Windows\Fonts\segoeuib.ttf'
FONT_SEMI = r'C:\Windows\Fonts\seguisb.ttf'

SIZE = 1024
C = SIZE / 2


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def band(r, a, b, aa=0.75):
    """1 dentro de [a,b], com borda suavizada (anti-aliasing analitico)."""
    return smoothstep(a - aa, a + aa, r) * (1 - smoothstep(b - aa, b + aa, r))


class Canvas:
    """Acumula camadas em RGBA pre-multiplicado (float) e devolve RGBA reto em 8 bits."""

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


def frame():
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32) + 0.5
    r = np.hypot(x - C, y - C)
    cv = Canvas(SIZE)

    # sombra externa e sombra interna (da profundidade ao mapa)
    cv.over((0, 0, 0), 0.42 * (1 - smoothstep(R_OUTER - 2, R_OUTER + 34, r)) * (r > R_OUTER - 2))
    cv.over((0, 0, 0), 0.38 * smoothstep(R_INNER - 26, R_INNER, r) * (r < R_INNER + 1))

    # anel de vidro escuro com degrade vertical
    t = np.clip((y - (C - R_OUTER)) / (2 * R_OUTER), 0, 1)[..., None]
    ring_col = (np.array(RING_TOP) * (1 - t) + np.array(RING_BOTTOM) * t)
    cv.over(ring_col, RING_ALPHA * band(r, R_INNER, R_OUTER))

    # filetes claros nas bordas do anel
    cv.over((255, 255, 255), 0.42 * band(r, R_INNER, R_INNER + 2.2, 0.6))
    cv.over((255, 255, 255), 0.13 * band(r, R_OUTER - 1.6, R_OUTER, 0.6))

    # marcas a cada 10 graus (maiores a cada 30), sem passar por cima das letras
    hi = Image.new('RGBA', (SIZE * 4, SIZE * 4))
    d = ImageDraw.Draw(hi)
    for deg in range(0, 360, 10):
        if any(abs(((deg - (ang % 360)) + 180) % 360 - 180) < 12 for ang in LETTERS.values()):
            continue
        major = deg % 30 == 0
        r0, r1 = (R_OUTER - 15, R_OUTER - 6) if major else (R_OUTER - 11, R_OUTER - 6)
        th = math.radians(deg)
        p0 = (4 * (C + r0 * math.cos(th)), 4 * (C + r0 * math.sin(th)))
        p1 = (4 * (C + r1 * math.cos(th)), 4 * (C + r1 * math.sin(th)))
        d.line([p0, p1], fill=(255, 255, 255, 150 if major else 75), width=9 if major else 6)

    # pontos cardeais
    rc = (R_INNER + R_OUTER) / 2
    for letter, ang in LETTERS.items():
        th = math.radians(ang)
        cx, cy = 4 * (C + rc * math.cos(th)), 4 * (C + rc * math.sin(th))
        # no jogo a moldura aparece com ~1/3 do tamanho: letras pequenas aqui somem la
        if letter == 'N':
            rad = 4 * 34
            d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=ACCENT + (255,))
            d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(255, 255, 255, 120), width=8)
            font, fill = ImageFont.truetype(FONT_BOLD, 4 * 42), (24, 16, 6, 255)
        else:
            rad = 4 * 27
            d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=(12, 16, 21, 245),
                      outline=(255, 255, 255, 70), width=8)
            font, fill = ImageFont.truetype(FONT_SEMI, 4 * 32), (235, 240, 245, 240)
        d.text((cx, cy), letter, font=font, fill=fill, anchor='mm')
    cv.over_image(hi.resize((SIZE, SIZE), Image.LANCZOS))
    return cv.to_image()


def arrow():
    S, k = 512, 4  # desenha 4x maior e reduz (bordas lisas)
    pts = [(256, 40), (420, 452), (256, 362), (92, 452)]   # um pouco menor que a original: sobra espaco p/ o brilho
    big = [(x * k, y * k) for x, y in pts]

    glow = Image.new('RGBA', (S * k, S * k))
    gd = ImageDraw.Draw(glow)
    gd.polygon(big, fill=ACCENT + (255,))
    gd.line(big + [big[0]], fill=ACCENT + (255,), width=k * 34, joint='curve')
    glow = glow.filter(ImageFilter.GaussianBlur(k * 12))
    ga = np.asarray(glow, np.float32).copy()
    ga[..., 3] = np.minimum(ga[..., 3] * 1.6, 235)
    glow = Image.fromarray(ga.astype(np.uint8), 'RGBA')

    body = Image.new('RGBA', (S * k, S * k))
    d = ImageDraw.Draw(body)
    d.polygon(big, fill=(10, 14, 19, 255))                 # contorno escuro (le bem em mapa claro)
    inset = shrink(pts, 15)
    d.polygon([(x * k, y * k) for x, y in inset], fill=(255, 255, 255, 255))
    # metade direita levemente sombreada: da volume sem enfeite
    right = [inset[0], inset[1], inset[2]]
    d.polygon([(x * k, y * k) for x, y in right], fill=(214, 224, 234, 255))

    out = Image.alpha_composite(glow, body)
    return out.resize((S, S), Image.LANCZOS)


def shrink(pts, dist):
    """Recuo simples de um poligono convexo/seta em direcao ao centroide das bordas."""
    n = len(pts)
    lines = []
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
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
        t = ((q[0] - p[0]) * dq[1] - (q[1] - p[1]) * dq[0]) / den
        res.append((p[0] + dp[0] * t, p[1] + dp[1] * t))
    return res


def preview(frame_img, arrow_img, path):
    """Mostra moldura nova x original sobre um pedaco do mapa real do mod."""
    def disc(frame_im, arrow_im):
        raw = open(os.path.join(MOD, 'embervale_realmap_default_2048.rgba'), 'rb').read()
        world = Image.frombytes('RGBA', (2048, 2048), raw).convert('RGB')
        crop = world.crop((760, 1180, 760 + 190, 1180 + 190)).resize((95, 95), Image.BILINEAR)
        crop = crop.resize((760, 760), Image.NEAREST)          # imita o "pixelado" do map_sample_step
        base = Image.new('RGBA', (SIZE, SIZE), (24, 22, 20, 255))
        mask = Image.new('L', (SIZE, SIZE))
        ImageDraw.Draw(mask).ellipse([C - 372, C - 372, C + 372, C + 372], fill=255)
        layer = Image.new('RGBA', (SIZE, SIZE)); layer.paste(crop, (int(C - 380), int(C - 380)))
        base.paste(layer, (0, 0), mask)
        base.alpha_composite(frame_im)
        a = arrow_im.resize((96, 96), Image.LANCZOS)
        base.alpha_composite(a, (int(C - 48), int(C - 48)))
        return base

    orig_f = Image.frombytes('RGBA', (1024, 1024), open(os.path.join(MOD, 'embervale_minimap_frame.rgba'), 'rb').read())
    orig_a = Image.frombytes('RGBA', (512, 512), open(os.path.join(MOD, 'embervale_player_arrow.rgba'), 'rb').read())
    sheet = Image.new('RGBA', (2 * SIZE, SIZE), (24, 22, 20, 255))
    sheet.paste(disc(orig_f, orig_a), (0, 0))
    sheet.paste(disc(frame_img, arrow_img), (SIZE, 0))
    sheet.convert('RGB').resize((SIZE, SIZE // 2), Image.LANCZOS).save(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    f, a = frame(), arrow()
    assert f.size == (1024, 1024) and a.size == (512, 512)
    open(os.path.join(OUT, 'embervale_minimap_frame.rgba'), 'wb').write(f.tobytes())
    open(os.path.join(OUT, 'embervale_player_arrow.rgba'), 'wb').write(a.tobytes())
    if '--sem-preview' not in sys.argv:
        preview(f, a, os.path.join(OUT, 'preview.png'))
    print('gerado em', OUT)


if __name__ == '__main__':
    main()
