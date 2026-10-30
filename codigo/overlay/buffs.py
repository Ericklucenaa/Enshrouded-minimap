"""Tempo restante dentro de cada circulo de buff do Enshrouded (comida, agua, pocoes).

Le os efeitos ativos do character*.ksd (o jogo grava a cada ~30 s enquanto se joga) e faz a
contagem regressiva a partir do horario gravado no proprio save. Os circulos ficam no canto
superior esquerdo, um embaixo do outro, na mesma ordem dos efeitos no save. Descansado e
Toque da Pata o proprio jogo ja mostra em texto, entao ficam de fora.

Roda dentro do painel do minimapa (BuffTimers(root_do_painel)) ou sozinho (python buffs.py).
Janela sempre no topo que deixa os cliques passarem e so aparece com o jogo em foco.
Precisa do jogo em 'Janela sem bordas'.
"""
import ctypes
import glob
import os
import struct
import sys
import time
import tkinter as tk
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.efeitos import parse_effects  # noqa: E402
from core.ksd import SaveFile  # noqa: E402

# ---------- ajustes ----------
GAME_EXE = 'enshrouded.exe'
# posicao dos circulos medida num print em 2560x1440; em outras resolucoes escala pela altura
ICON_X, FIRST_Y, STEP, ICON_D = 52, 142, 53.3, 45
BASE_H = 1440
OFFSET_X, OFFSET_Y = 0, 0   # ajuste fino em pixels se ficar fora do centro
FONT_SIZE = 10
FG, WARN, CRIT, OUTLINE = '#ffffff', '#ffd75e', '#ff6b5e', '#000000'  # normal / < 5 min / < 1 min
KEY = '#010101'             # cor que vira transparente (quase preta: a borda do texto some no contorno)
MAX_ICONS = 8
WAIT_FOR_GAME_MIN = 30
STALE_SEC = 90              # sem save novo por esse tempo = fora do mundo; os tempos somem
APP_ID = '1203620'

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def process_exe(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
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


def game_in_front():
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    return process_exe(pid.value) == GAME_EXE


def game_running():
    arr = (wintypes.DWORD * 4096)()
    needed = wintypes.DWORD()
    if not ctypes.windll.psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(needed)):
        return True
    return any(process_exe(pid) == GAME_EXE for pid in arr[:needed.value // 4] if pid)


def steam_dirs():
    dirs = [r'C:\Program Files (x86)\Steam', r'C:\Program Files\Steam']
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as k:
            dirs.insert(0, os.path.normpath(winreg.QueryValueEx(k, 'SteamPath')[0]))
    except OSError:
        pass
    return dirs


def newest_save():
    pats = [os.path.join(d, 'userdata', '*', APP_ID, 'remote', 'character*.ksd') for d in steam_dirs()]
    pats.append(os.path.join(os.path.expanduser('~'), 'Saved Games', 'Enshrouded', 'character*.ksd'))
    files = [f for p in pats for f in glob.glob(p)]
    return max(files, key=os.path.getmtime) if files else None


def fmt(sec):
    sec = max(0, int(sec + 0.999))
    if sec >= 3600:
        return f'{sec // 3600}h{sec % 3600 // 60:02}'
    return f'{sec // 60}:{sec % 60:02}'


class BuffTimers:
    """Janela dos tempos. Com master, vira uma Toplevel do painel e segue o laco dele."""

    def __init__(self, master=None, enabled=lambda: True):
        self.standalone = master is None
        self.win = tk.Tk() if self.standalone else tk.Toplevel(master)
        self.enabled = enabled
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        self.win.configure(bg=KEY)
        self.win.attributes('-transparentcolor', KEY)
        scale = self.win.winfo_screenheight() / BASE_H
        self.x = ICON_X * scale + OFFSET_X
        self.y0 = FIRST_Y * scale + OFFSET_Y
        self.step = STEP * scale
        w = int(ICON_D * scale * 1.6)
        h = int(self.y0 + self.step * MAX_ICONS)
        self.font = ('Segoe UI', max(8, round(FONT_SIZE * scale)), 'bold')
        self.canvas = tk.Canvas(self.win, width=w, height=h, bg=KEY, highlightthickness=0)
        self.canvas.pack()
        self.left_edge = int(self.x - w / 2)
        self.win.geometry(f'{w}x{h}+{self.left_edge}+0')
        self.win.update_idletasks()
        self._click_through()
        self.visible = True
        self.seen_game = False
        self.started = time.time()
        self.last_reload = 0
        self.save_path = None
        self.save_mtime = 0
        self.saved_at = 0
        self.effects = []
        self.tick()

    def _click_through(self):
        hwnd = user32.GetParent(self.win.winfo_id())
        style = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
        # camada + clique atravessa + sem botao na barra + nunca rouba o foco do jogo
        user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20 | 0x80 | 0x8000000)

    def reload(self):
        path = newest_save()
        if not path:
            return
        mtime = os.path.getmtime(path)
        if path == self.save_path and mtime == self.save_mtime:
            return
        try:
            sf = SaveFile.load(path)
            effects = parse_effects(sf.block('player_character').data)
        except Exception:  # noqa: BLE001 - o jogo pode estar no meio da gravacao: tenta de novo depois
            return
        self.save_path, self.save_mtime = path, mtime
        self.saved_at = struct.unpack_from('<I', sf.header, 0x20)[0]
        # so os que tem circulo: efeitos com duracao que vieram de um item
        self.effects = [e for e in effects if e.total > 0 and e.item is not None]

    def draw(self, now):
        c = self.canvas
        c.delete('all')
        if now - self.saved_at > STALE_SEC:
            return
        elapsed = now - self.saved_at
        cx = self.x - self.left_edge
        for i, left in enumerate(l for l in (e.left - elapsed for e in self.effects) if l > 0):
            if i >= MAX_ICONS:
                break
            cy = self.y0 + i * self.step
            color = CRIT if left < 60 else WARN if left < 300 else FG
            text = fmt(left)
            for dx, dy in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1), (0, 2)):
                c.create_text(cx + dx, cy + dy, text=text, fill=OUTLINE, font=self.font)
            c.create_text(cx, cy, text=text, fill=color, font=self.font)

    def tick(self):
        try:
            self._tick()
        except Exception:  # noqa: BLE001 - anota e segue: nao pode derrubar o painel no meio do jogo
            import traceback
            traceback.print_exc()
            self.win.after(500, self.tick)

    def _tick(self):
        now = time.time()
        if now - self.last_reload > 5:
            if self.standalone:  # no painel quem fecha tudo junto com o jogo e o proprio painel
                if game_running():
                    self.seen_game = True
                elif self.seen_game or now - self.started > WAIT_FOR_GAME_MIN * 60:
                    self.win.destroy()
                    return
            self.last_reload = now
            self.reload()
        show = self.enabled() and game_in_front()
        if show:
            self.draw(now)
            self.win.attributes('-topmost', True)
        if show != self.visible:
            self.win.deiconify() if show else self.win.withdraw()
            self.visible = show
        self.win.after(500, self.tick)


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass
    kernel32.CreateMutexW(None, False, 'EnshroudedBuffsOverlay')
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)
    BuffTimers().win.mainloop()


if __name__ == '__main__':
    main()
