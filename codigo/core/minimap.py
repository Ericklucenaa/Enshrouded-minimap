"""Preferencias do Shroudweave Minimap (mods.minimap_mod no shroudtopia.json).

O mod rele o shroudtopia.json enquanto o jogo roda, entao as mudancas valem na hora.
A moldura e a seta (visual) so sao carregadas quando o jogo abre.
"""
import hashlib
import json
import os
import re
import shutil

MOD_ID = 'minimap_mod'
VISUAL_FILES = ('embervale_minimap_frame.rgba', 'embervale_player_arrow.rgba')

KEY_RX = re.compile(r'^(F([1-9]|1[0-9]|2[0-4])|0x[0-9A-Fa-f]{2}|none)$')

# chave -> validador (devolve o valor normalizado ou levanta ValueError)
def _bool(v):
    if isinstance(v, bool):
        return v
    raise ValueError('precisa ser verdadeiro ou falso')


def _choice(*opts):
    def f(v):
        if v in opts:
            return v
        raise ValueError('valor invalido')
    return f


def _int(lo, hi):
    def f(v):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v or not lo <= v <= hi:
            raise ValueError(f'precisa ser um numero inteiro de {lo} a {hi}')
        return int(v)
    return f


def _key(v):
    if isinstance(v, str) and KEY_RX.match(v):
        return v if v in ('none',) or v.startswith('F') else '0x' + v[2:].upper()
    raise ValueError('tecla invalida (use F1-F24, 0x.. ou none)')


SCHEMA = {
    'active': _bool,
    'show_other_players': _bool, 'show_pings': _bool, 'show_waypoints': _bool,
    'show_world_markers': _bool, 'show_death_markers': _bool,
    'show_clock': _bool, 'show_weather': _bool, 'show_fog_of_war': _bool,
    'position': _choice('top-right', 'middle-right', 'bottom-right', 'top-left', 'middle-left', 'bottom-left'),
    'offset': _int(-540, 540),
    'map_orientation': _choice('north-up', 'rotating'),
    'map_style': _choice('default', 'original', 'bright'),
    'icon_style': _choice('original', 'world-map'),
    'map_light': _int(0, 100),
    'heading_smoothing_ms': _int(0, 250),
    'map_sample_step': _int(1, 4),
    'max_icons': _int(0, 256),
    'scale_percent': _choice(50, 75, 100, 125, 150, 175, 200),
    'toggle_key': _key, 'toggle_key_secondary': _key,
    'zoom_in_key': _key, 'zoom_in_key_secondary': _key,
    'zoom_out_key': _key, 'zoom_out_key_secondary': _key,
    'size_decrease_key': _key, 'size_increase_key': _key,
}


def find_game_dir():
    libs = [r'C:\Program Files (x86)\Steam']
    try:
        with open(os.path.join(libs[0], 'steamapps', 'libraryfolders.vdf'), encoding='utf-8') as f:
            libs += [p.replace('\\\\', '\\') for p in re.findall(r'"path"\s+"([^"]+)"', f.read())]
    except OSError:
        pass
    for lib in dict.fromkeys(libs):
        d = os.path.join(lib, 'steamapps', 'common', 'Enshrouded')
        if os.path.exists(os.path.join(d, 'enshrouded.exe')):
            return d
    return None


class Minimap:
    def __init__(self, game_dir, visual_dir):
        self.game_dir = game_dir
        self.visual_dir = visual_dir  # tem as subpastas saida/ (moderno) e original/

    @property
    def mod_dir(self):
        return os.path.join(self.game_dir, 'mods', MOD_ID) if self.game_dir else None

    @property
    def config_path(self):
        return os.path.join(self.game_dir, 'shroudtopia.json')

    def installed(self):
        return bool(self.game_dir) and os.path.exists(os.path.join(self.mod_dir, 'minimap_mod.dll'))

    def defaults(self):
        with open(os.path.join(self.mod_dir, 'mod.json'), encoding='utf-8') as f:
            return json.load(f)['shroudtopia']['default']

    def _read_config(self):
        if not os.path.exists(self.config_path):
            return {'active': True, 'mods': {}}
        with open(self.config_path, encoding='utf-8-sig') as f:
            return json.load(f)

    def state(self):
        if not self.installed():
            return {'installed': False, 'game_dir': self.game_dir}
        cfg = self._read_config()
        values = dict(self.defaults())
        values.update(cfg.get('mods', {}).get(MOD_ID, {}))
        if values.get('map_style') == 'bright':
            values['map_style'] = 'default'
        return {'installed': True, 'game_dir': self.game_dir, 'values': values,
                'defaults': self.defaults(), 'visual': self.visual(),
                'visual_available': {k: self._has_visual(k) for k in ('moderno', 'original')},
                'colors': self.colors(), 'color': self.current_color()}

    def save(self, changes):
        if not self.installed():
            raise ValueError('Minimapa nao instalado')
        clean = {}
        for k, v in changes.items():
            if k not in SCHEMA:
                raise ValueError(f'Opcao desconhecida: {k}')
            try:
                clean[k] = SCHEMA[k](v)
            except ValueError as e:
                raise ValueError(f'{k}: {e}') from None
        cfg = self._read_config()
        entry = cfg.setdefault('mods', {}).setdefault(MOD_ID, {})
        entry.update(clean)
        if not os.path.exists(self.config_path + '.editor-bak') and os.path.exists(self.config_path):
            shutil.copy2(self.config_path, self.config_path + '.editor-bak')  # copia do primeiro estado
        tmp = self.config_path + '.editor-tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.config_path)
        return clean

    # ---- visual (moldura + seta) ----
    #  'moderno' = o visual novo, que vem em varias cores (pasta cores/<cor>/)
    #  'original' = o bronze que veio no mod (pasta original/)
    def _visual_src(self, kind):
        return os.path.join(self.visual_dir, {'moderno': 'saida', 'original': 'original'}[kind])

    def _has_visual(self, kind):
        return all(os.path.exists(os.path.join(self._visual_src(kind), f)) for f in VISUAL_FILES)

    @property
    def _cores_dir(self):
        return os.path.join(self.visual_dir, 'cores')

    def colors(self):
        d = self._cores_dir
        if not os.path.isdir(d):
            return []
        return [n for n in sorted(os.listdir(d))
                if all(os.path.exists(os.path.join(d, n, f)) for f in VISUAL_FILES)]

    def _sha_mod(self):
        return [_sha(os.path.join(self.mod_dir, f)) for f in VISUAL_FILES]

    def current_color(self):
        cur = self._sha_mod()
        for name in self.colors():
            if cur == [_sha(os.path.join(self._cores_dir, name, f)) for f in VISUAL_FILES]:
                return name
        return None

    def visual(self):
        cur = self._sha_mod()
        if self.current_color() is not None:
            return 'moderno'
        for kind in ('moderno', 'original'):
            if self._has_visual(kind) and cur == [_sha(os.path.join(self._visual_src(kind), f)) for f in VISUAL_FILES]:
                return kind
        return 'outro'

    def _backup_original(self):
        orig = self._visual_src('original')
        if self.visual() == 'outro' and not self._has_visual('original'):
            os.makedirs(orig, exist_ok=True)   # nunca perde o visual que estava instalado
            for f in VISUAL_FILES:
                shutil.copy2(os.path.join(self.mod_dir, f), os.path.join(orig, f))

    def _apply(self, src_dir):
        self._backup_original()
        for f in VISUAL_FILES:
            shutil.copy2(os.path.join(src_dir, f), os.path.join(self.mod_dir, f))

    def set_visual(self, kind):
        if kind not in ('moderno', 'original') or not self._has_visual(kind):
            raise ValueError('Visual indisponivel')
        self._apply(self._visual_src(kind))

    def set_color(self, name):
        if name not in self.colors():
            raise ValueError('Cor indisponivel')
        self._apply(os.path.join(self._cores_dir, name))


def _sha(path):
    try:
        with open(path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def record_color_choice(name):
    """Guarda a cor escolhida no opcoes.json do instalador, para a atualizacao nao reseta-la."""
    try:
        d = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'EnshroudedMinimap')
        if not os.path.isdir(d):
            return
        p = os.path.join(d, 'opcoes.json')
        o = {}
        if os.path.exists(p):
            with open(p, encoding='utf-8-sig') as f:
                o = json.load(f)
        o['color'] = name
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(o, f, ensure_ascii=False, indent=2)
    except (OSError, ValueError):
        pass
