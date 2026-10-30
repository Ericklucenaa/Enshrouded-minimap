"""Enshrouded Save Editor - servidor local (http://127.0.0.1:8765)."""
import glob
import json
import os
import shutil
import struct
import subprocess
import sys
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.character import PlayerCharacter, parse_character_data, set_character_name
from core.ksd import SaveFile
from core.minimap import Minimap, find_game_dir

APP_DIR = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, 'frozen', False)  # dentro do MelhoriasEnshrouded.exe (opcao --editor)
LOCAL_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'EnshroudedMinimap')
RES_DIR = getattr(sys, '_MEIPASS', APP_DIR)                       # static/ e data/ (so leitura)
DATA_DIR = os.path.join(LOCAL_DIR, 'editor') if FROZEN else APP_DIR  # backups, nomes e cache
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
LABELS_FILE = os.path.join(DATA_DIR, 'labels.json')
IMG_CACHE = os.path.join(DATA_DIR, 'cache', 'img')
IDLE_EXIT_S = 180  # no .exe nao ha janela para fechar: sai sozinho quando a pagina para de consultar
last_request = [time.time()]
WIKI = 'https://enshrouded.wiki.gg'
WIKI_UA = 'EnshroudedSaveEditor/1.0 (uso pessoal)'
PORT = 8765
API_VERSION = 9  # a interface confere isso para detectar um servidor antigo ainda aberto
LOCK = threading.Lock()
SAFE_NAME = re.compile(r"^[\w .,'()&+-]{1,80}$")


def steam_dirs():
    dirs = [r'C:\Program Files (x86)\Steam', r'C:\Program Files\Steam']
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as k:
            dirs.insert(0, os.path.normpath(winreg.QueryValueEx(k, 'SteamPath')[0]))
    except OSError:
        pass
    return dirs


def installed_game_dir():
    """Pasta do jogo anotada pelo instalador (no PC de amigos o jogo pode estar em outro disco)."""
    try:
        with open(os.path.join(LOCAL_DIR, 'opcoes.json'), encoding='utf-8-sig') as f:
            d = json.load(f).get('game_dir')
        return d if d and os.path.exists(os.path.join(d, 'enshrouded.exe')) else None
    except (OSError, ValueError):
        return None


def find_save_dirs():
    dirs = [os.environ['ENSHROUDED_SAVE_DIR']] if os.environ.get('ENSHROUDED_SAVE_DIR') else []
    for steam in steam_dirs():
        for d in glob.glob(os.path.join(steam, 'userdata', '*', '1203620', 'remote')):
            if os.path.normcase(d) not in map(os.path.normcase, dirs):
                dirs.append(d)
    sg = os.path.join(os.path.expanduser('~'), 'Saved Games', 'Enshrouded')
    if glob.glob(os.path.join(sg, '*.ksd')) or glob.glob(os.path.join(sg, '*', '*.ksd')):
        dirs.append(sg)
    return [d for d in dirs if glob.glob(os.path.join(d, '*.ksd'))]


GAME_DIR = installed_game_dir() or find_game_dir()
GAME_LOG = os.path.join(GAME_DIR, 'enshrouded.log') if GAME_DIR and os.path.exists(os.path.join(GAME_DIR, 'enshrouded.log')) else None
# no .exe instalado as cores da moldura ficam em %LOCALAPPDATA%\EnshroudedMinimap (cores/)
MINIMAP = Minimap(GAME_DIR, LOCAL_DIR if FROZEN else os.path.join(APP_DIR, 'minimap_visual'))
ENTER_WORLD = re.compile(rb"\[Session\] started transition from 'Lobby' to '\w+'")
LEAVE_WORLD = re.compile(rb"\[Session\] started transition from '\w+' to 'Lobby'")
MENU_READY = re.compile(rb"\[pregame\] start creation step Save2")


def game_state():
    """'closed', 'menu' (no menu principal, fora de qualquer mundo) ou 'playing'.

    Pelo log do jogo: ao sair de um mundo ele recebe o save final ('Final Savegame received'),
    grava o character0.ksd e recria o sistema de saves do menu. Nesse ponto o arquivo pode ser editado.
    """
    if not game_running():
        return 'closed'
    if not GAME_LOG:
        return 'playing'
    try:
        with open(GAME_LOG, 'rb') as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4 * 1024 * 1024))
            tail = f.read()
    except OSError:
        return 'playing'

    def last(rx):
        m = None
        for m in rx.finditer(tail):
            pass
        return m.start() if m else -1
    enter, leave, menu = last(ENTER_WORLD), last(LEAVE_WORLD), last(MENU_READY)
    # no menu: o sistema de saves do menu foi criado depois da ultima entrada num mundo
    if menu > enter and (enter == -1 or leave > enter):
        return 'menu'
    return 'playing'


def game_running():
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq enshrouded.exe', '/NH'],
                             capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
        return 'enshrouded.exe' in out.lower()
    except Exception:
        return False


def load_game_db():
    try:
        with open(os.path.join(RES_DIR, 'data', 'game_db.json'), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'items': {}, 'skills': {}, 'game_version': ''}


GAME_DB = load_game_db()
# tipos que existem no jogo como pilhas simples (sem nivel/durabilidade)
STACKABLE = {'Material', 'Comida', 'Consumível', 'Munição', 'Feitiço', 'Construção', 'Gema / Runa',
             'Ração animal', 'Colecionável', 'Projeto', 'Moeda'}


def search_items(q, kind=None, limit=60):
    q = q.strip().lower()
    out = []
    for h, e in GAME_DB['items'].items():
        if kind and e['type'] != kind:
            continue
        if q and q not in e['pt'].lower() and q not in e['en'].lower() and q != h:
            continue
        out.append({'hash': h, **{k: e[k] for k in ('pt', 'en', 'type', 'sub', 'rarity', 'stack')}, 'lvl': e.get('lvl')})
    # comeca com a busca > contem a palavra inteira > resto; depois nomes mais curtos
    word = re.compile(r'\b' + re.escape(q) + r's?\b') if q else None

    def score(e):
        n = e['pt'].lower()
        return (0 if n.startswith(q) else 1 if word and word.search(n) else 2, len(n), n)
    out.sort(key=score)
    return out[:limit]


def load_labels():
    try:
        with open(LABELS_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


# ---------------- wiki (enshrouded.wiki.gg) ----------------

def wiki_get(params):
    url = WIKI + '/api.php?' + urllib.parse.urlencode({**params, 'format': 'json'})
    req = urllib.request.Request(url, headers={'User-Agent': WIKI_UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise UserError(f'Nao consegui acessar a wiki: {e}')


def wiki_search(q):
    q = q.strip()
    if not q:
        return []
    base = {'action': 'query', 'prop': 'pageimages', 'piprop': 'thumbnail', 'pithumbsize': 96}
    res = wiki_get({**base, 'generator': 'prefixsearch', 'gpssearch': q, 'gpslimit': 24})
    pages = list(res.get('query', {}).get('pages', {}).values())
    if not pages:
        res = wiki_get({**base, 'generator': 'search', 'gsrsearch': q, 'gsrlimit': 24, 'gsrnamespace': 0})
        pages = list(res.get('query', {}).get('pages', {}).values())
    pages.sort(key=lambda p: p.get('index', 0))
    # so paginas com imagem costumam ser itens
    return [{'title': p['title']} for p in pages if 'thumbnail' in p and '/' not in p['title']]


def wiki_page_items(title):
    res = wiki_get({'action': 'parse', 'page': title, 'prop': 'images', 'redirects': 1})
    if 'error' in res:
        raise UserError('Pagina nao encontrada na wiki: ' + title)
    page_title = res['parse']['title']
    out = []
    for img in res['parse'].get('images', []):
        if not img.lower().endswith('.png'):
            continue
        name = img[:-4].replace('_', ' ')
        if name == page_title or not SAFE_NAME.match(name):
            continue
        out.append({'title': name})
    return {'page': page_title, 'items': out}


INFO_FILE = os.path.join(DATA_DIR, 'cache', 'wiki_info.json')
_info_cache = None

# (palavras-chave procuradas no Type da infobox e nas categorias da pagina, tipo em portugues)
TYPE_RULES = [
    (('ammo', 'arrow'), 'Munição'),
    (('food', 'meal', 'dish', 'drink'), 'Comida'),
    (('potion', 'consumable', 'elixir', 'bandage', 'antiseptic', 'fishing bait'), 'Consumível'),
    (('spell',), 'Feitiço'),
    (('ring', 'amulet', 'necklace', 'trinket', 'accessory', 'accessories'), 'Acessório'),
    (('shield',), 'Escudo'),
    (('helmet', 'head armor', 'chest armor', 'hand armor', 'leg armor', 'foot armor', 'armor', 'armour',
      'gloves', 'boots', 'pants', 'hood', 'mask', 'gauntlet'), 'Armadura'),
    (('sword', 'axe', 'club', 'mace', 'dagger', 'bow', 'staff', 'wand', 'weapon', 'spear', 'hammer',
      'greatsword', 'blade', 'powder ball'), 'Arma'),
    (('glider', 'grappling', 'tool', 'pickaxe', 'torch', 'rake', 'essential', 'lantern'), 'Ferramenta'),
    (('gem', 'rune'), 'Gema / Runa'),
    (('seed', 'plant', 'sapling', 'flower'), 'Planta / Semente'),
    (('building', 'roof', 'terrain', 'block'), 'Construção'),
    (('furniture', 'comfort', 'workbench', 'station', 'chest', 'altar', 'decoration'), 'Móvel'),
    (('material', 'ore', 'bar', 'ingot', 'resource'), 'Material'),
]


TYPE_RULES = [(re.compile(r'\b(?:' + '|'.join(map(re.escape, words)) + r')(?:s|es)?\b'), label)
              for words, label in TYPE_RULES]


def classify(raw_type, categories):
    # o Type da infobox tem prioridade; as categorias so entram se ele nao resolver
    for hay in ([raw_type.lower()], [c.lower() for c in categories]):
        for rx, label in TYPE_RULES:
            if any(rx.search(h) for h in hay):
                return label
    return raw_type or 'Outro'


def _infobox_field(text, field):
    m = re.search(r'\|\s*' + re.escape(field) + r'\s*=\s*([^\n|}]*)', text, re.I)
    if not m:
        return ''
    v = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]*)\]\]', r'\1', m.group(1))  # [[link|texto]] -> texto
    v = re.sub(r"'{2,}|\{\{[^}]*$", '', v).strip()
    return v


INFO_VERSION = 2
NOT_FOOD = re.compile(r'\b(potion|flask|elixir|bandage|antidote|antiseptic|tonic)s?\b', re.I)


def is_food(text, title):
    # a wiki chama comida de "Consumables"; o que diferencia e o buff longo (mm:ss) e a cozinha
    if NOT_FOOD.search(title):
        return False
    dur = _infobox_field(text, 'Duration')
    crafter = _infobox_field(text, 'Crafter').lower()
    workshop = ' '.join(_infobox_field(text, k) for k in ('Workshop', 'Workshop2')).lower()
    return (':' in dur or crafter == 'farmer'
            or any(w in workshop for w in ('kitchen', 'cooking', 'oven', 'grill', 'smoker')))


def _effects(text):
    out = []
    for k in range(1, 9):
        v = _infobox_field(text, f'Effects{k}')
        if v:
            out.append(v)
    return out


def _load_info():
    global _info_cache
    if _info_cache is None:
        try:
            with open(INFO_FILE, encoding='utf-8') as f:
                _info_cache = json.load(f)
        except (OSError, ValueError):
            _info_cache = {}
        if _info_cache.get('_v') != INFO_VERSION:
            _info_cache = {'_v': INFO_VERSION}
    return _info_cache


def wiki_info(titles):
    """Tipo, raridade, pilha e descricao de cada item (em lote, com cache em disco)."""
    cache = _load_info()
    titles = [t for t in dict.fromkeys(titles) if t and SAFE_NAME.match(t)]
    missing = [t for t in titles if t not in cache]
    for i in range(0, len(missing), 50):
        chunk = missing[i:i + 50]
        res = wiki_get({'action': 'query', 'titles': '|'.join(chunk), 'redirects': 1,
                        'prop': 'revisions|categories', 'rvprop': 'content', 'rvslots': 'main', 'cllimit': 'max'})
        q = res.get('query', {})
        alias = {n['from']: n['to'] for n in q.get('normalized', []) + q.get('redirects', [])}
        pages = {p['title']: p for p in q.get('pages', {}).values()}
        for t in chunk:
            target = alias.get(alias.get(t, t), alias.get(t, t))
            p = pages.get(target)
            if not p or 'missing' in p:
                cache[t] = {'found': False, 'type': 'Desconhecido'}
                continue
            text = p.get('revisions', [{}])[0].get('slots', {}).get('main', {}).get('*', '')
            cats = [c['title'].split(':', 1)[-1] for c in p.get('categories', [])
                    if 'Pages with' not in c['title'] and 'Stubs' not in c['title']]
            raw_type = _infobox_field(text, 'Type')
            stack = re.sub(r'\D', '', _infobox_field(text, 'Stack Size'))
            kind = classify(raw_type, cats)
            if kind == 'Consumível' and is_food(text, p['title']):
                kind = 'Comida'
            cache[t] = {
                'found': True, 'title': p['title'], 'raw_type': raw_type,
                'type': kind, 'rarity': _infobox_field(text, 'Rarity'),
                'stack': int(stack) if stack else None,
                'duration': _infobox_field(text, 'Duration'), 'effects': _effects(text),
                'description': _infobox_field(text, 'description'), 'categories': cats[:6],
            }
    if missing:
        os.makedirs(os.path.dirname(INFO_FILE), exist_ok=True)
        with open(INFO_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=1)
    return {t: cache[t] for t in titles if t in cache}


def wiki_image(name):
    """Baixa (uma vez) a miniatura do item e guarda em cache local."""
    if not SAFE_NAME.match(name):
        return None
    os.makedirs(IMG_CACHE, exist_ok=True)
    fname = name.replace(' ', '_')
    path = os.path.join(IMG_CACHE, fname + '.png')
    miss = path + '.missing'
    if os.path.exists(path):
        with open(path, 'rb') as f:
            return f.read()
    if os.path.exists(miss) and time.time() - os.path.getmtime(miss) < 86400:
        return None
    url = f'{WIKI}/wiki/Special:FilePath/{urllib.parse.quote(fname)}.png?width=96'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': WIKI_UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
            if not r.headers.get('Content-Type', '').startswith('image/'):
                raise ValueError('nao e imagem')
    except (urllib.error.URLError, TimeoutError, ValueError):
        open(miss, 'w').close()
        return None
    with open(path, 'wb') as f:
        f.write(data)
    return data


class State:
    def __init__(self):
        dirs = find_save_dirs()
        self.save_dir = dirs[0] if dirs else None
        self.path = None
        self.save = None
        self.mtime = None
        self.scan = None  # {'type','block','offsets':[...]}
        self.labels = load_labels()

    def files(self):
        if not self.save_dir:
            return []
        out = []
        for p in sorted(glob.glob(os.path.join(self.save_dir, '*.ksd'))):
            st = os.stat(p)
            out.append({'name': os.path.basename(p), 'size': st.st_size, 'mtime': st.st_mtime})
        return out

    def open(self, name):
        p = os.path.join(self.save_dir, os.path.basename(name))
        self.save = SaveFile.load(p)
        self.path = p
        self.mtime = os.path.getmtime(p)

    def require(self):
        if not self.save:
            raise UserError('Abra um arquivo de save primeiro')
        return self.save

    def pc(self):
        return PlayerCharacter(self.require().block('player_character').data)


class UserError(Exception):
    pass


S = State()

SCAN_TYPES = {'u8': ('<B', 1), 'u16': ('<H', 2), 'u32': ('<I', 4), 'f32': ('<f', 4)}


def scan_matches(data, typ, value, offsets=None):
    fmt, size = SCAN_TYPES[typ]
    if typ == 'f32':
        def ok(o):
            v = struct.unpack_from(fmt, data, o)[0]
            return abs(v - value) < 0.01
    else:
        target = struct.pack(fmt, int(value))
        def ok(o):
            return data[o:o + size] == target
    rng = offsets if offsets is not None else range(0, len(data) - size + 1)
    return [o for o in rng if o + size <= len(data) and ok(o)]


def backup_current(reason):
    base = time.strftime('%Y-%m-%d_%H-%M-%S')
    stamp, n = base, 1
    while os.path.exists(os.path.join(BACKUP_DIR, stamp)):
        n += 1
        stamp = f'{base}_{n}'
    dst = os.path.join(BACKUP_DIR, stamp)
    os.makedirs(dst)
    for p in glob.glob(os.path.join(S.save_dir, '*.ksd')):
        shutil.copy2(p, dst)
    with open(os.path.join(dst, 'motivo.txt'), 'w', encoding='utf-8') as f:
        f.write(reason)
    return stamp


# ---------------- API ----------------

def api(method, path, body):
    if path == '/api/state':
        return {
            'api_version': API_VERSION,
            'save_dir': S.save_dir, 'all_dirs': find_save_dirs(), 'files': S.files(),
            'open': os.path.basename(S.path) if S.path else None,
            'dirty': bool(S.save and S.save.dirty), 'game_running': game_running(), 'game_state': game_state(),
            'info': S.save.info() if S.save else None,
            'changed_on_disk': bool(S.path and os.path.getmtime(S.path) != S.mtime),
        }
    if path == '/api/setdir':
        d = body['dir']
        if not glob.glob(os.path.join(d, '*.ksd')):
            raise UserError('Nenhum arquivo .ksd nessa pasta')
        S.save_dir, S.save, S.path = d, None, None
        return {'ok': True}
    if path == '/api/open':
        S.open(body['file'])
        S.scan = None
        return {'ok': True}
    if path == '/api/reload':
        S.require()
        S.open(os.path.basename(S.path))
        return {'ok': True}

    if path == '/api/character':
        sv = S.require()
        names = [b.name for b in sv.blocks]
        if 'player_character' not in names:
            raise UserError('Este arquivo nao e um personagem (abra character*.ksd)')
        out = S.pc().to_json()
        out['name'] = parse_character_data(sv.block('character_data').data)['name']
        out['labels'] = S.labels
        hashes = {i['hash'] for i in out['equipment'] + out['backpack'] + out['extra']}
        out['db'] = {h: GAME_DB['items'][h] for h in hashes if h in GAME_DB['items']}
        out['skilldb'] = {s['hash']: GAME_DB['skills'][s['hash']] for s in out['skills'] if s['hash'] in GAME_DB['skills']}
        out['game_version'] = GAME_DB.get('game_version', '')
        return out
    if path == '/api/items/search':
        return {'items': search_items(body.get('q', ''), body.get('type') or None)}
    if path == '/api/character/update':
        sv = S.require()
        pc = S.pc()
        if 'level' in body:
            pc.level = int(body['level'])
            if not 1 <= pc.level <= 100:
                raise UserError('Nivel deve ficar entre 1 e 100')
        if 'xp' in body:
            pc.xp = int(body['xp'])
        sv.block('player_character').set_data(pc.build())
        if body.get('name'):
            cd = sv.block('character_data')
            cur = parse_character_data(cd.data)['name']
            if body['name'] != cur:
                cd.set_data(set_character_name(cd.data, body['name']))
        return {'ok': True}

    if path in ('/api/item/update', '/api/item/add', '/api/item/delete'):
        sv = S.require()
        pc = S.pc()
        if not pc.inventory_ok:
            raise UserError('Inventario nao pode ser editado: ' + str(pc.inventory_error))
        if path == '/api/item/update':
            it = pc.find(body['where'], int(body['slot']))
            apply_item_fields(it, body)
        elif path == '/api/item/add':
            where = body.get('where', 'backpack')
            if where not in ('backpack', 'extra'):
                raise UserError('So da para adicionar itens na mochila')
            used = {i.slot for i in pc.items(where)}
            slot = int(body['slot'])
            if slot in used:
                raise UserError(f'O slot {slot} ja esta ocupado')
            if not 0 <= slot <= 79:
                raise UserError('Slot invalido')
            new = make_new_item(pc, body)
            new.slot = slot
            apply_item_fields(new, body)
            pc.items(where).append(new)
        else:
            if body['where'] not in ('backpack', 'extra'):
                raise UserError('So da para remover itens da mochila')
            it = pc.find(body['where'], int(body['slot']))
            pc.items(body['where']).remove(it)
        sv.block('player_character').set_data(pc.build())
        return {'ok': True}

    if path == '/api/label':
        h = body['hash'].lower()
        if body.get('name'):
            S.labels[h] = body['name']
        else:
            S.labels.pop(h, None)
        with open(LABELS_FILE, 'w', encoding='utf-8') as f:
            json.dump(S.labels, f, ensure_ascii=False, indent=1)
        return {'ok': True}

    if path == '/api/wiki/search':
        return {'items': wiki_search(body.get('q', ''))}
    if path == '/api/wiki/page':
        return wiki_page_items(body.get('title') or 'Fell_Banshee')
    if path == '/api/wiki/info':
        return {'info': wiki_info(body.get('titles', [])[:200])}

    if path == '/api/block':
        b = S.require().block(body['name'])
        off = max(0, int(body.get('offset', 0)))
        ln = min(int(body.get('length', 512)), 4096)
        return {'name': b.name, 'size': len(b.data), 'offset': off, 'hex': b.data[off:off + ln].hex()}
    if path == '/api/block/write':
        b = S.require().block(body['name'])
        off = int(body['offset'])
        new = bytes.fromhex(body['hex'])
        if off < 0 or off + len(new) > len(b.data):
            raise UserError('Escrita fora dos limites do bloco')
        d = bytearray(b.data)
        d[off:off + len(new)] = new
        b.set_data(bytes(d))
        return {'ok': True}

    if path == '/api/scan/new':
        sv = S.require()
        typ, val = body['type'], float(body['value'])
        res = {}
        for b in sv.blocks:
            if b.name == 'fogofwar' and not body.get('include_fog'):
                continue
            res[b.name] = scan_matches(b.data, typ, val)
        S.scan = {'type': typ, 'hits': res}
        return scan_summary()
    if path == '/api/scan/next':
        if not S.scan:
            raise UserError('Faca um novo scan primeiro')
        if body.get('reload', True):
            S.open(os.path.basename(S.path))
        sv = S.require()
        typ, val = S.scan['type'], float(body['value'])
        res = {}
        for name, offs in S.scan['hits'].items():
            try:
                res[name] = scan_matches(sv.block(name).data, typ, val, offs)
            except KeyError:
                pass
        S.scan['hits'] = res
        return scan_summary()
    if path == '/api/scan/set':
        sv = S.require()
        typ = S.scan['type'] if S.scan else body['type']
        fmt, size = SCAN_TYPES[typ]
        v = float(body['value']) if typ == 'f32' else int(body['value'])
        b = sv.block(body['block'])
        d = bytearray(b.data)
        struct.pack_into(fmt, d, int(body['offset']), v)
        b.set_data(bytes(d))
        return {'ok': True}

    if path == '/api/save':
        sv = S.require()
        # A Steam so rele o tamanho dos arquivos de save quando o jogo abre. Com o jogo aberto (mesmo no menu)
        # um arquivo de tamanho diferente e rejeitado ("read error (read:X size:Y)") e o jogo grava o antigo por cima.
        if game_running():
            raise UserError('Feche o jogo antes de salvar. Com o jogo aberto, mesmo no menu, ele descarta o arquivo editado.')
        if os.path.getmtime(S.path) != S.mtime:
            raise UserError('O arquivo mudou no disco depois que voce abriu. Recarregue e refaca as alteracoes.')
        if not sv.dirty:
            raise UserError('Nada para salvar')
        data = sv.build()
        stamp = backup_current('Antes de salvar ' + os.path.basename(S.path))
        tmp = S.path + '.editor-tmp'
        with open(tmp, 'wb') as f:
            f.write(data)
        SaveFile.load(tmp)
        os.replace(tmp, S.path)
        S.open(os.path.basename(S.path))
        return {'ok': True, 'backup': stamp}

    if path == '/api/minimap':
        return MINIMAP.state()
    if path == '/api/minimap/save':
        try:
            return {'ok': True, 'saved': MINIMAP.save(body.get('values') or {})}
        except ValueError as e:
            raise UserError(str(e))
    if path == '/api/minimap/visual':
        try:
            MINIMAP.set_visual(body.get('kind'))
        except ValueError as e:
            raise UserError(str(e))
        return {'ok': True, 'running': game_running()}

    if path == '/api/backups':
        out = []
        for d in sorted(glob.glob(os.path.join(BACKUP_DIR, '*')), reverse=True):
            if os.path.isdir(d):
                try:
                    reason = open(os.path.join(d, 'motivo.txt'), encoding='utf-8').read()
                except OSError:
                    reason = ''
                out.append({'id': os.path.basename(d), 'reason': reason,
                            'files': [os.path.basename(p) for p in glob.glob(os.path.join(d, '*.ksd'))]})
        return {'backups': out}
    if path == '/api/backup/create':
        return {'id': backup_current(body.get('reason') or 'Backup manual')}
    if path == '/api/backup/restore':
        if game_running():
            raise UserError('Feche o jogo antes de restaurar um backup')
        src = os.path.join(BACKUP_DIR, os.path.basename(body['id']))
        files = glob.glob(os.path.join(src, '*.ksd'))
        if not files:
            raise UserError('Backup vazio')
        stamp = backup_current('Antes de restaurar o backup ' + body['id'])
        for p in files:
            SaveFile.load(p)
            shutil.copy2(p, S.save_dir)
        if S.path:
            S.open(os.path.basename(S.path))
        return {'ok': True, 'backup': stamp}

    raise UserError('Rota desconhecida: ' + path)


def make_new_item(pc, body):
    """Cria o item novo copiando o formato de um item parecido que o personagem ja tem."""
    if body.get('template'):
        tpl_where, tpl_slot = body['template']
        return pc.find(tpl_where, int(tpl_slot)).copy()
    h = str(body.get('hash') or '').lower()
    entry = GAME_DB['items'].get(h)
    if not entry:
        raise UserError('Item desconhecido. Escolha um item da lista.')
    owned = [i for i in pc.backpack + pc.extra + pc.equipment if i.hash == int(h, 16)]
    if owned:
        return owned[0].copy()

    def kind(it):
        e = GAME_DB['items'].get(f'{it.hash:08x}')
        return (e['type'], e['sub']) if e else (None, None)
    same_sub = [i for i in pc.backpack + pc.extra + pc.equipment if kind(i) == (entry['type'], entry['sub'])]
    same_type = [i for i in pc.backpack + pc.extra + pc.equipment if kind(i)[0] == entry['type']]
    for pool in (same_sub, same_type):
        if pool:
            return pool[0].copy()
    if entry['type'] in STACKABLE:
        tpl = [i for i in pc.backpack + pc.extra if i.flags == 0]
        if tpl:
            return tpl[0].copy()
    raise UserError(f'Para adicionar um item do tipo "{entry["type"]}", você precisa ter pelo menos um item '
                    'desse tipo no inventário para servir de modelo (nível, durabilidade etc.).')


def level_range(item_hash):
    e = GAME_DB['items'].get(f'{item_hash:08x}')
    return (e['lvl'], e['pt']) if e and e.get('lvl') else (None, None)


def apply_item_fields(it, body):
    old_hash, old_level = it.hash, it.level
    if 'hash' in body and body['hash'] not in (None, ''):
        h = int(str(body['hash']).strip().lower().replace('0x', ''), 16)
        if not 0 < h <= 0xFFFFFFFF:
            raise UserError('ID de item invalido')
        it.hash = h
    if 'count' in body and body['count'] not in (None, ''):
        c = int(body['count'])
        if not 1 <= c <= 65535:
            raise UserError('Quantidade deve ficar entre 1 e 65535')
        it.count = c
    if it.flags & 0x01:
        rng, name = level_range(it.hash)
        if body.get('level') not in (None, ''):
            lv = int(body['level'])
            if not 0 <= lv <= 255:
                raise UserError('Nivel do item deve ficar entre 0 e 255')
            # so cobra a faixa quando o nivel muda (alguns saves antigos tem nivel fora da faixa atual)
            if rng and (lv != old_level or it.hash != old_hash) and not rng[0] <= lv <= rng[1]:
                raise UserError(f'{name}: o nível vai de {rng[0]} até {rng[1]} (máximo do equipamento).')
            it.level = lv
        elif rng and it.hash != old_hash and it.level is not None:
            # item trocado/copiado de um modelo: encaixa o nivel herdado na faixa do item novo
            it.level = min(max(it.level, rng[0]), rng[1])
    if it.flags & 0x02:
        for k in ('dur_cur', 'dur_max'):
            if body.get(k) not in (None, ''):
                setattr(it, k, max(0, int(body[k])))
        if it.dur_cur > it.dur_max:
            raise UserError('A durabilidade atual não pode passar da máxima')


def scan_summary(limit=200):
    hits = []
    for name, offs in S.scan['hits'].items():
        for o in offs:
            hits.append({'block': name, 'offset': o})
    typ = S.scan['type']
    fmt, size = SCAN_TYPES[typ]
    sv = S.save
    for h in hits[:limit]:
        d = sv.block(h['block']).data
        h['value'] = struct.unpack_from(fmt, d, h['offset'])[0]
        lo = max(0, h['offset'] - 8)
        h['context'] = d[lo:h['offset'] + size + 8].hex()
        h['ctx_start'] = lo
    return {'type': typ, 'total': len(hits), 'hits': hits[:limit]}


# ---------------- HTTP ----------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        last_request[0] = time.time()
        if self.path in ('/', '/index.html'):
            with open(os.path.join(RES_DIR, 'static', 'index.html'), 'rb') as f:
                return self._send(200, f.read(), 'text/html; charset=utf-8')
        if self.path.startswith('/img/'):
            name = urllib.parse.unquote(self.path[5:].split('?')[0])
            data = wiki_image(name)
            if data:
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'max-age=86400')
                self.end_headers()
                self.wfile.write(data)
                return
            return self._send(404, {'error': 'sem imagem'})
        if self.path.startswith('/api/'):
            return self._handle({})
        self._send(404, {'error': 'nao encontrado'})

    def do_POST(self):
        last_request[0] = time.time()
        if self.headers.get('Origin') not in (None, f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}'):
            return self._send(403, {'error': 'origem nao permitida'})
        n = int(self.headers.get('Content-Length') or 0)
        try:
            body = json.loads(self.rfile.read(n) or b'{}')
        except ValueError:
            return self._send(400, {'error': 'JSON invalido'})
        self._handle(body)

    def _handle(self, body):
        try:
            with LOCK:
                res = api(self.command, self.path.split('?')[0], body)
            self._send(200, res)
        except UserError as e:
            self._send(400, {'error': str(e)})
        except Exception as e:  # noqa: BLE001 - mostra o erro na interface
            self._send(500, {'error': f'{type(e).__name__}: {e}'})


def main():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    url = f'http://127.0.0.1:{PORT}/'
    # no Windows, reuse_address deixa dois servidores na mesma porta; queremos erro nesse caso
    ThreadingHTTPServer.allow_reuse_address = False
    try:
        srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    except OSError:
        print(f'O editor ja esta aberto em outra janela ({url}). Feche a outra janela para usar esta versao.')
        webbrowser.open(url)
        return
    print(f'Enshrouded Save Editor rodando em {url}  (feche esta janela para encerrar)')
    if '--no-browser' not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    if FROZEN:
        def idle_watch():
            while time.time() - last_request[0] < IDLE_EXIT_S:
                time.sleep(15)
            print(time.strftime('%Y-%m-%d %H:%M:%S'), 'editor encerrado: pagina fechada')
            os._exit(0)
        threading.Thread(target=idle_watch, daemon=True).start()
    srv.serve_forever()


if __name__ == '__main__':
    main()
