"""Painel do minimapa dentro do jogo.

F8 (com o Enshrouded em foco) abre/fecha um painel ao lado do minimapa.
  Setas cima/baixo: escolher   Setas esquerda/direita ou Enter: mudar   Esc ou F8: fechar
Cada mudanca vai direto para o shroudtopia.json, que o mod rele na hora.
Tambem mostra o tempo restante dentro dos circulos de buff (buffs.py), se ligado no painel.

A janela nunca pega o foco (o jogo continua ativo); as teclas chegam por um gancho de teclado
que so segura as setas/Enter/Esc enquanto o painel esta aberto. Fecha sozinho junto com o jogo.
"""
import ctypes
import json
import os
import sys
import time
import tkinter as tk
from collections import deque
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.minimap import Minimap, find_game_dir, record_color_choice  # noqa: E402
from buffs import BuffTimers  # noqa: E402

# ---------- ajustes ----------
GAME_EXE = 'enshrouded.exe'
DEFAULT_PANEL_KEY = 0x77    # F8 (a tecla que abre o painel; pode ser remapeada)
TITLE = 'Melhorias Enshrouded'
WIDTH = 452
ROW_H = 42
FONT = 'Segoe UI'
C_BG, C_CARD, C_ROW_SEL, C_LINE = '#0c1116', '#121a22', '#1a2530', '#223040'
C_TEXT, C_MUTED, C_FAINT, C_OFF = '#eef3f8', '#8d9cad', '#5b6a7a', '#2e3b49'
C_ACCENT, C_ACCENT_DIM, C_ON_ACCENT = '#ffb547', '#3a2c14', '#1a1206'
KEY_COLOR = '#010203'         # cor "invisivel" da janela (cantos arredondados)
WAIT_FOR_GAME_MIN = 30
GONE_GRACE_S = 120        # o jogo pode sumir e voltar ao iniciar pela Steam: so fecha depois de 2 min sem ele

DEBUG = False   # True registra no painel.log o que acontece ao apertar F8 (diagnostico)
VK_UP, VK_DOWN, VK_LEFT, VK_RIGHT, VK_RETURN, VK_ESCAPE, VK_TAB = 0x26, 0x28, 0x25, 0x27, 0x0D, 0x1B, 0x09
NAV_KEYS = {VK_UP, VK_DOWN, VK_LEFT, VK_RIGHT, VK_RETURN, VK_ESCAPE, VK_TAB}

POSITIONS = [('bottom-right', 'Embaixo à direita'), ('middle-right', 'Meio à direita'), ('top-right', 'Em cima à direita'),
             ('top-left', 'Em cima à esquerda'), ('middle-left', 'Meio à esquerda'), ('bottom-left', 'Embaixo à esquerda')]
COLOR_NAMES = {'ambar': 'Âmbar', 'azul': 'Azul', 'verde': 'Verde', 'vermelho': 'Vermelho', 'branco': 'Branco'}

# teclas remapeaveis. _k_panel = a tecla que abre o painel (so do painel); as demais vao para o shroudtopia.json
KEY_ITEMS = [('_k_panel', 'Abrir este painel'), ('toggle_key', 'Mostrar/esconder minimapa'),
             ('zoom_in_key', 'Mais zoom'), ('zoom_out_key', 'Menos zoom'),
             ('size_decrease_key', 'Diminuir minimapa'), ('size_increase_key', 'Aumentar minimapa')]
_VK_NAMES = {0x08: 'Backspace', 0x09: 'Tab', 0x0D: 'Enter', 0x20: 'Espaço', 0x25: '←', 0x26: '↑', 0x27: '→',
             0x28: '↓', 0x2D: 'Insert', 0x2E: 'Delete', 0x24: 'Home', 0x23: 'End', 0x21: 'PageUp', 0x22: 'PageDown',
             0xBB: '+', 0xBD: '-', 0xBC: ',', 0xBE: '.', 0xBF: '/', 0xC0: '`', 0xDB: '[', 0xDD: ']', 0xDC: '\\',
             0xBA: ';', 0xDE: "'", 0x6A: '* num', 0x6B: '+ num', 0x6D: '- num', 0x6F: '/ num', 0x6E: '. num',
             0xC1: '/ ABNT', 0xC2: '. num ABNT'}


def vk_label(vk):
    if not vk:
        return 'nenhuma'
    if 0x70 <= vk <= 0x87:
        return 'F%d' % (vk - 0x6F)
    if vk in _VK_NAMES:
        return _VK_NAMES[vk]
    if 0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return '%d num' % (vk - 0x60)
    return '0x%02X' % vk


def vk_to_modfmt(vk):
    return 'F%d' % (vk - 0x6F) if 0x70 <= vk <= 0x87 else '0x%02X' % vk


def modfmt_to_vk(s):
    if not s or s == 'none':
        return None
    if s[0] == 'F' and s[1:].isdigit():
        return 0x6F + int(s[1:])
    try:
        return int(s, 16)
    except (ValueError, TypeError):
        return None


def _opcoes_path():
    return os.path.join(os.environ.get('LOCALAPPDATA', ''), 'EnshroudedMinimap', 'opcoes.json')


def load_option(key, default=None):
    try:
        with open(_opcoes_path(), encoding='utf-8-sig') as f:
            return json.load(f).get(key, default)
    except (OSError, ValueError):
        return default


def load_panel_key():
    try:
        v = load_option('panel_key')
        return int(v) if v else None
    except (ValueError, TypeError):
        return None


def record_option(key, value):
    try:
        p = _opcoes_path()
        if not os.path.isdir(os.path.dirname(p)):
            return
        o = {}
        if os.path.exists(p):
            with open(p, encoding='utf-8-sig') as f:
                o = json.load(f)
        o[key] = value
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(o, f, ensure_ascii=False, indent=2)
    except (OSError, ValueError):
        pass


def record_panel_key(vk):
    record_option('panel_key', int(vk))


def installed_version():
    try:
        with open(os.path.join(os.path.dirname(_opcoes_path()), 'versao.json'), encoding='utf-8-sig') as f:
            return json.load(f).get('versao')
    except (OSError, ValueError):
        return None


def open_editor():
    """Abre o editor de save (servidor local + navegador) em outro processo."""
    if getattr(sys, 'frozen', False):
        import atualizador  # launch_detached: o processo nao pode morrer junto com o painel
        atualizador.launch_detached([sys.executable, '--editor'])
    else:
        import subprocess
        app = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        subprocess.Popen([sys.executable, os.path.join(app, 'server.py')], cwd=app, creationflags=0x08000000)

# (chave, titulo, tipo, opcoes)  tipo: bool | cycle [(valor, rotulo)] | range (min, max, passo, sufixo)
#   | color | key | action. Chaves com _ ficam no opcoes.json (sao do painel), as outras no shroudtopia.json.
TABS = [
    ('Minimapa', [
        ('active', 'Minimapa ligado', 'bool', None),
        ('position', 'Posição', 'cycle', POSITIONS),
        ('scale_percent', 'Tamanho', 'cycle', [(n, f'{n}%') for n in (50, 75, 100, 125, 150, 175, 200)]),
        ('map_orientation', 'Orientação', 'cycle', [('north-up', 'Norte fixo'), ('rotating', 'Gira com você')]),
        ('max_icons', 'Máximo de ícones', 'range', (8, 128, 8, '')),
        ('show_fog_of_war', 'Névoa (não explorado)', 'bool', None),
    ]),
    ('Mostrar', [
        ('show_clock', 'Relógio do jogo', 'bool', None),
        ('show_weather', 'Clima', 'bool', None),
        ('show_world_markers', 'Locais do mapa', 'bool', None),
        ('show_waypoints', 'Destino marcado', 'bool', None),
        ('show_other_players', 'Outros jogadores', 'bool', None),
        ('show_pings', 'Pings', 'bool', None),
        ('show_death_markers', 'Túmulos', 'bool', None),
    ]),
    ('Visual', [
        ('map_style', 'Cores do mapa', 'cycle', [('default', 'Colorido (HD)'), ('original', 'Originais')]),
        ('icon_style', 'Ícones', 'cycle', [('original', 'Originais'), ('world-map', 'Moldura dourada')]),
        ('map_light', 'Brilho do terreno', 'range', (0, 100, 5, '')),
        ('map_sample_step', 'Nitidez', 'cycle', [(1, 'Alta'), (2, 'Padrão'), (3, 'Baixa')]),
        ('_color', 'Cor da moldura *', 'color', None),   # * vale ao reiniciar o jogo
    ]),
    ('Melhorias', [
        ('_buffs', 'Tempo dos buffs', 'bool', None),
        ('_editor', 'Editor de save', 'action', 'Abrir'),
    ]),
    ('Teclas', [(k, t, 'key', None) for k, t in KEY_ITEMS]),
]
ITEMS = [item for _, items in TABS for item in items]

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [('vkCode', wintypes.DWORD), ('scanCode', wintypes.DWORD), ('flags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


def process_exe(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return ''
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit('\\', 1)[-1].lower()
        return ''
    finally:
        kernel32.CloseHandle(h)


_fg_cache = [None, False]


def game_hwnd_in_front():
    """Janela do jogo se ele estiver em foco (com cache por janela: o gancho precisa ser rapido)."""
    hwnd = user32.GetForegroundWindow()
    if hwnd != _fg_cache[0]:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        _fg_cache[:] = [hwnd, process_exe(pid.value) == GAME_EXE]
    return hwnd if _fg_cache[1] else None


def game_running():
    arr = (wintypes.DWORD * 4096)()
    needed = wintypes.DWORD()
    if not ctypes.windll.psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(needed)):
        return True
    return any(process_exe(pid) == GAME_EXE for pid in arr[:needed.value // 4] if pid)


class Panel:
    def __init__(self, minimap):
        self.mm = minimap
        st = minimap.state()
        self.values = st['values']
        self.values['_color'] = st.get('color') or (minimap.colors() or [''])[0]
        self.values['_buffs'] = bool(load_option('buffs', True))
        self.panel_key = load_panel_key() or DEFAULT_PANEL_KEY
        self.capturing = None   # item de tecla aguardando a nova tecla, ou None
        self.tab, self.sel = 0, 0
        self.version = installed_version()
        self.open = False
        self.events = deque()
        self.status, self.status_until = '', 0
        self.hint_until = 0  # aviso "F8 abre o painel" na primeira vez que o jogo ganha foco
        self.seen_game, self.started, self.last_proc = False, time.time(), 0
        self.gone_since = None

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg=KEY_COLOR)
        self.root.attributes('-transparentcolor', KEY_COLOR)
        self.cv = tk.Canvas(self.root, bg=KEY_COLOR, highlightthickness=0, bd=0)
        self.cv.pack(fill='both', expand=True)
        self.root.withdraw()
        self.root.update_idletasks()
        self._no_activate()

        self._proc = HOOKPROC(self._hook)  # referencia viva: senao o Python libera o callback
        self.hook = user32.SetWindowsHookExW(13, self._proc, kernel32.GetModuleHandleW(None), 0)
        if not self.hook:
            raise OSError(ctypes.get_last_error(), 'nao consegui instalar o atalho de teclado')
        self.buffs = BuffTimers(self.root, enabled=lambda: self.values.get('_buffs', True))
        self.root.after(30, self.tick)

    def _no_activate(self):
        hwnd = user32.GetParent(self.root.winfo_id())
        style = user32.GetWindowLongW(hwnd, -20)
        # camada + clique atravessa + sem botao na barra + nunca rouba o foco do jogo
        user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20 | 0x80 | 0x8000000)

    # ---- teclado (roda dentro do loop de mensagens: so enfileira e responde rapido) ----
    def _hook(self, n, wparam, lparam):
        if n == 0:
            k = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents.vkCode
            down = wparam in (0x100, 0x104)
            if self.capturing is not None and game_hwnd_in_front():
                if down:                       # capturando: a proxima tecla vira o atalho
                    self.events.append(('capture', k))
                return 1
            if k == self.panel_key and game_hwnd_in_front():
                if down:
                    self.events.append('toggle')
                return 1
            if self.open and k in NAV_KEYS and game_hwnd_in_front():
                if down:
                    self.events.append(k)
                return 1
        return user32.CallNextHookEx(None, n, wparam, lparam)

    # ---- logica ----
    def handle(self, ev):
        if isinstance(ev, tuple) and ev[0] == 'capture':
            self._apply_capture(ev[1])
            return
        if ev == 'toggle':
            self.open = not self.open
            if DEBUG:
                print(time.strftime('%H:%M:%S'), 'toggle -> painel', 'ABERTO' if self.open else 'fechado')
            if self.open:
                self.reload_values()
            return
        items = TABS[self.tab][1]
        if ev == VK_ESCAPE:
            self.open = False
        elif ev == VK_TAB:
            self.tab, self.sel = (self.tab + 1) % len(TABS), 0
        elif ev == VK_UP:
            self.sel = (self.sel - 1) % len(items)
        elif ev == VK_DOWN:
            self.sel = (self.sel + 1) % len(items)
        elif ev in (VK_LEFT, VK_RIGHT, VK_RETURN):
            self.change(items[self.sel], -1 if ev == VK_LEFT else 1)

    def _apply_capture(self, vk):
        item = self.capturing
        self.capturing = None
        if item is None:
            return
        if vk == VK_ESCAPE:
            self.flash('cancelado')
            return
        key = item[0]
        if key == '_k_panel':
            self.panel_key = vk
            record_panel_key(vk)
            self.flash('abrir painel: ' + vk_label(vk))
            return
        try:
            self.mm.save({key: vk_to_modfmt(vk)})   # tecla do mod -> shroudtopia.json
            self.values[key] = vk_to_modfmt(vk)
            self.flash(vk_label(vk) + ' — pode pedir reiniciar')
        except Exception as e:  # noqa: BLE001
            self.flash('erro: ' + str(e)[:40])

    def change(self, item, step):
        key, _, kind, opts = item
        cur = self.values.get(key)
        if kind == 'key':
            self.capturing = item
            self.flash('aperte a nova tecla (Esc cancela)')
            return
        if kind == 'color':
            vals = self.mm.colors()
            if not vals:
                self.flash('sem cores disponíveis')
                return
            i = vals.index(cur) if cur in vals else 0
            new = vals[(i + step) % len(vals)]
            try:
                self.mm.set_color(new)
                record_color_choice(new)
                self.values['_color'] = new
                self.flash('cor: ' + COLOR_NAMES.get(new, new) + ' — reinicie o jogo')
            except Exception as e:  # noqa: BLE001
                self.flash('erro: ' + str(e)[:40])
            return
        if kind == 'action':
            if step < 0:
                return
            try:
                open_editor()
                self.flash('editor abrindo no navegador…')
            except Exception as e:  # noqa: BLE001
                self.flash('erro: ' + str(e)[:40])
            return
        if key == '_buffs':
            self.values['_buffs'] = not cur
            record_option('buffs', not cur)
            self.flash('✔ tempo dos buffs ' + ('ligado' if not cur else 'desligado'))
            return
        if kind == 'bool':
            new = not cur
        elif kind == 'cycle':
            vals = [v for v, _ in opts]
            i = vals.index(cur) if cur in vals else 0
            new = vals[(i + step) % len(vals)]
        else:
            lo, hi, st, _ = opts
            new = max(lo, min(hi, (cur if isinstance(cur, int) else lo) + st * step))
        try:
            self.mm.save({key: new})
            self.values[key] = new
            self.flash('✔ aplicado')
        except Exception as e:  # noqa: BLE001 - mostra no painel em vez de fechar
            self.flash('erro: ' + str(e)[:40])

    def reload_values(self):
        try:
            st = self.mm.state()          # pega mudancas feitas pelo editor
            buffs = self.values.get('_buffs', True)
            self.values = st['values']
            self.values['_color'] = st.get('color') or (self.mm.colors() or [''])[0]
            self.values['_buffs'] = buffs
        except Exception:  # noqa: BLE001
            pass

    def flash(self, msg):
        self.status, self.status_until = msg, time.time() + 1.6

    # ---- desenho ----
    def label(self, item):
        key, _, kind, opts = item
        v = self.values.get(key)
        if kind == 'bool':
            return None
        if kind == 'key':
            if self.capturing is item:
                return '[aperte…]'
            return vk_label(self.panel_key) if key == '_k_panel' else vk_label(modfmt_to_vk(v))
        if kind == 'color':
            return COLOR_NAMES.get(v, v or '—')
        if kind == 'cycle':
            return dict(opts).get(v, str(v))
        return f'{v}{opts[3]}'

    def keycap(self, x, y, text, fill=C_CARD, fg=C_MUTED, size=9):
        """Desenha uma tecla (ex.: [Tab]) com a ponta esquerda em x; devolve onde ela termina."""
        w = max(22, 9 + 7 * len(text))
        self._round(x, y - 10, x + w, y + 10, 6, fill=fill, outline=C_LINE)
        self.cv.create_text(x + w / 2, y, text=text, fill=fg, font=(FONT, size, 'bold'))
        return x + w

    def draw(self, hint_only=False):
        cv = self.cv
        cv.delete('all')
        if hint_only:
            w, h = 300, 46
            self._round(2, 2, w - 2, h - 2, 14, fill=C_BG, outline=C_LINE)
            cv.create_oval(16, h / 2 - 4, 24, h / 2 + 4, fill=C_ACCENT, outline='')
            cv.create_text(32, h / 2, anchor='w', text=TITLE, fill=C_TEXT, font=(FONT, 11, 'bold'))
            k = vk_label(self.panel_key)
            self.keycap(w - 16 - max(22, 9 + 7 * len(k)), h / 2, k, fill=C_ACCENT, fg=C_ON_ACCENT, size=10)
            return w, h
        name, items = TABS[self.tab]
        head, tabs_h, foot = 70, 46, 54
        w = WIDTH
        h = head + tabs_h + ROW_H * len(items) + 14 + foot
        self._round(2, 2, w - 2, h - 2, 18, fill=C_BG, outline=C_LINE)
        # cabecalho
        cv.create_oval(22, 24, 34, 36, fill=C_ACCENT, outline='')
        cv.create_oval(25, 27, 31, 33, fill=C_BG, outline='')
        cv.create_text(44, 30, anchor='w', text=TITLE, fill=C_TEXT, font=(FONT, 15, 'bold'))
        sub = 'mudanças valem na hora' + (f'  ·  v{self.version}' if self.version else '')
        cv.create_text(44, 52, anchor='w', text=sub, fill=C_FAINT, font=(FONT, 9))
        k = vk_label(self.panel_key)
        self.keycap(w - 22 - max(22, 9 + 7 * len(k)), 32, k, fill=C_ACCENT, fg=C_ON_ACCENT, size=10)
        # abas
        x, ty = 16, head + tabs_h / 2 - 4
        for i, (tname, _) in enumerate(TABS):
            tw = 18 + 7.6 * len(tname)
            if i == self.tab:
                self._round(x, ty - 14, x + tw, ty + 14, 14, fill=C_ACCENT_DIM, outline='')
                cv.create_text(x + tw / 2, ty, text=tname, fill=C_ACCENT, font=(FONT, 10, 'bold'))
            else:
                cv.create_text(x + tw / 2, ty, text=tname, fill=C_MUTED, font=(FONT, 10))
            x += tw + 4
        cv.create_line(16, head + tabs_h, w - 16, head + tabs_h, fill=C_LINE)
        # linhas
        dim = self.tab == 0 and not self.values.get('active', True)
        top = head + tabs_h + 7
        for i, item in enumerate(items):
            y = top + i * ROW_H
            sel = i == self.sel
            if sel:
                self._round(12, y + 3, w - 12, y + ROW_H - 3, 11, fill=C_ROW_SEL, outline='')
                self._round(12, y + 12, 16, y + ROW_H - 12, 2, fill=C_ACCENT, outline='')
            faded = dim and i > 0
            cv.create_text(30, y + ROW_H / 2, anchor='w', text=item[1],
                           fill=C_MUTED if faded else C_TEXT, font=(FONT, 11, 'bold' if sel else 'normal'))
            self.draw_value(item, w - 28, y + ROW_H / 2, sel, faded)
        # rodape: teclas ou aviso
        fy = h - foot / 2
        cv.create_line(16, h - foot, w - 16, h - foot, fill=C_LINE)
        if time.time() < self.status_until:
            cv.create_text(w / 2, fy, text=self.status, fill=C_ACCENT, font=(FONT, 10, 'bold'))
        else:
            x = 22
            for cap, what in (('↑↓', 'escolher'), ('←→', 'mudar'), ('Tab', 'aba'), ('Esc', 'fechar')):
                x = self.keycap(x, fy, cap) + 6
                cv.create_text(x, fy, anchor='w', text=what, fill=C_FAINT, font=(FONT, 9))
                x += 7 * len(what) + 16
        return w, h

    def draw_value(self, item, x, y, sel, faded):
        key, _, kind, opts = item
        v = self.values.get(key)
        cv = self.cv
        if kind == 'bool':
            on = bool(v)
            col = (C_ACCENT if on else C_OFF) if not faded else C_OFF
            self._round(x - 44, y - 12, x, y + 12, 12, fill=col, outline='')
            kx = x - 12 if on else x - 32
            cv.create_oval(kx - 8, y - 8, kx + 8, y + 8, fill=C_ON_ACCENT if on else '#c9d3dd', outline='')
            return
        if kind == 'range':
            lo, hi, _, suf = opts
            frac = (v - lo) / (hi - lo) if isinstance(v, (int, float)) else 0
            cv.create_text(x, y, anchor='e', text=f'{v}{suf}', fill=C_ACCENT if sel else C_TEXT, font=(FONT, 10, 'bold'))
            bx0, bx1 = x - 150, x - 42
            self._round(bx0, y - 2, bx1, y + 2, 2, fill=C_OFF, outline='')
            kx = bx0 + (bx1 - bx0) * min(1, max(0, frac))
            self._round(bx0, y - 2, max(bx0 + 4, kx), y + 2, 2, fill=C_ACCENT, outline='')
            cv.create_oval(kx - 6, y - 6, kx + 6, y + 6, fill=C_ACCENT if sel else '#c9d3dd', outline='')
            return
        if kind == 'action':
            tw = 22 + 7.5 * len(opts)
            self._round(x - tw, y - 13, x, y + 13, 13, fill=C_ACCENT if sel else C_CARD,
                        outline='' if sel else C_LINE)
            cv.create_text(x - tw / 2, y, text=opts + ' ↗', fill=C_ON_ACCENT if sel else C_TEXT, font=(FONT, 10, 'bold'))
            return
        txt = self.label(item)
        if sel:
            cv.create_text(x, y, anchor='e', text=f'‹  {txt}  ›', fill=C_ACCENT, font=(FONT, 10, 'bold'))
            return
        tw = 20 + 7 * len(txt)
        self._round(x - tw, y - 12, x, y + 12, 8, fill=C_CARD, outline='')
        cv.create_text(x - tw / 2, y, text=txt, fill=C_MUTED if faded else C_TEXT, font=(FONT, 10))

    def _round(self, x0, y0, x1, y1, r, **kw):
        r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
               x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self.cv.create_polygon(pts, smooth=True, splinesteps=12, **kw)

    def place(self, w, h, game):
        r = wintypes.RECT()
        user32.GetWindowRect(game, ctypes.byref(r))
        pos = self.values.get('position', 'bottom-right')
        right = pos.endswith('right')
        x = r.right - w - 40 if right else r.left + 40
        if pos.startswith('middle'):
            y = r.top + 70  # minimapa no meio: o painel vai para cima
        else:
            y = r.top + (r.bottom - r.top - h) // 2
        self.root.geometry(f'{w}x{h}+{x}+{y}')

    # ---- laco ----
    def tick(self):
        try:
            self._tick()
        except Exception:  # noqa: BLE001 - anota e segue: o painel nao pode morrer no meio do jogo
            import traceback
            traceback.print_exc()
            self.root.after(500, self.tick)

    def _tick(self):
        now = time.time()
        if now - self.last_proc > 5:
            self.last_proc = now
            if game_running():
                if not self.seen_game:
                    print(time.strftime('%Y-%m-%d %H:%M:%S'), 'jogo detectado')
                self.seen_game, self.gone_since = True, None
            else:
                if self.seen_game and self.gone_since is None:
                    self.gone_since = now
                closed = self.seen_game and now - self.gone_since > GONE_GRACE_S
                if closed or (not self.seen_game and now - self.started > WAIT_FOR_GAME_MIN * 60):
                    print(time.strftime('%Y-%m-%d %H:%M:%S'), 'painel encerrado:',
                          'jogo fechado' if closed else f'o jogo nao abriu em {WAIT_FOR_GAME_MIN} min')
                    user32.UnhookWindowsHookEx(self.hook)
                    self.root.destroy()
                    return
        changed = False
        while self.events:
            self.handle(self.events.popleft())
            changed = True
        game = game_hwnd_in_front()
        if game and not self.hint_until and not self.open:
            self.hint_until = now + 5
        show_hint = game and not self.open and now < self.hint_until
        visible = bool(game and (self.open or show_hint))
        if DEBUG and self.open and changed:
            print(time.strftime('%H:%M:%S'), 'desenho: jogo_em_foco=%s visivel=%s' % (bool(game), visible))
        if visible:
            w, h = self.draw(hint_only=not self.open)
            self.place(w, h, game)
            self.root.deiconify()
            self.root.attributes('-topmost', True)
        else:
            self.root.withdraw()
        self.root.after(30 if (self.open or changed) else 120, self.tick)


def installed_game_dir():
    """Pasta do jogo anotada pelo instalador (no PC de amigos o jogo pode estar em outro disco)."""
    import json
    path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'EnshroudedMinimap', 'opcoes.json')
    try:
        with open(path, encoding='utf-8-sig') as f:
            d = json.load(f).get('game_dir')
        return d if d and os.path.exists(os.path.join(d, 'enshrouded.exe')) else None
    except (OSError, ValueError):
        return None


def main():
    editor = '--editor' in sys.argv
    if getattr(sys, 'frozen', False):
        # no .exe sem console, sys.stderr e None: um erro fecharia o painel sem deixar rastro
        log_dir = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'EnshroudedMinimap')
        os.makedirs(log_dir, exist_ok=True)
        sys.stdout = sys.stderr = open(os.path.join(log_dir, 'editor.log' if editor else 'painel.log'),
                                       'a', encoding='utf-8', buffering=1)
        print(time.strftime('%Y-%m-%d %H:%M:%S'), 'editor iniciado' if editor else 'painel iniciado', sys.argv[1:])
    if editor:
        import server  # editor de save: servidor local em 127.0.0.1:8765 + navegador
        server.main()
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass
    kernel32.CreateMutexW(None, False, 'EnshroudedPainelMinimapa')
    if kernel32.GetLastError() == 183:
        # ja tem um painel aberto; se clicaram no atalho de novo com o jogo fechado, ao menos abre o jogo
        if '--abrir-jogo' in sys.argv and not game_running():
            os.startfile('steam://rungameid/1203620')
        print(time.strftime('%Y-%m-%d %H:%M:%S'), 'outro painel ja estava aberto')
        sys.exit(0)
    abrir_jogo = '--abrir-jogo' in sys.argv and not game_running()
    if abrir_jogo and getattr(sys, 'frozen', False) and '--sem-atualizar' not in sys.argv:
        import atualizador  # so na versao .exe instalada pelo instalador
        if atualizador.run_with_window():
            sys.exit(0)  # o instalador fecha/atualiza e reabre este programa com o jogo
    game_dir = installed_game_dir() or find_game_dir()
    if getattr(sys, 'frozen', False):
        # no .exe instalado as cores da moldura ficam em %LOCALAPPDATA%\EnshroudedMinimap (cores/)
        visual_dir = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'EnshroudedMinimap')
    else:
        visual_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'minimap_visual')
    mm = Minimap(game_dir, visual_dir)
    if not mm.installed():
        sys.exit('Minimapa nao instalado')
    if abrir_jogo:
        os.startfile('steam://rungameid/1203620')  # abre o Enshrouded pela Steam
    Panel(mm).root.mainloop()


if __name__ == '__main__':
    main()
