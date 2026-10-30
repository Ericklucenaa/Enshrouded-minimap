"""Gera data/game_db.json (ID do item -> nome, tipo, raridade...) a partir dos arquivos do jogo.

Uso:
  1. kfc-parser.exe unpack -g "<pasta do jogo>" -o <saida> -f tItemInfo,tSkillTreeResource,tLocaTagCollectionResource
     (kfc-parser: https://github.com/Brabb3l/kfc-parser - so le os arquivos, nao altera o jogo)
  2. python gerar_banco.py "<pasta do jogo>" <saida>

Rode de novo depois de atualizacoes grandes do jogo.
"""
import glob
import json
import os
import re
import struct
import sys
import uuid

APP_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(APP_DIR, 'data', 'game_db.json')


def fnv1a(data: bytes) -> int:
    h = 0x811C9DC5
    for c in data:
        h = ((h ^ c) * 0x01000193) & 0xFFFFFFFF
    return h


def guid_key(g):
    """Chave do texto traduzido = FNV-1a dos bytes do GUID (layout little-endian)."""
    return fnv1a(uuid.UUID(g).bytes_le) if g else None


def read_kfc_contents(game_dir):
    d = open(os.path.join(game_dir, 'enshrouded.kfc'), 'rb').read()
    if d[:4] != b'KFC4':
        raise SystemExit('enshrouded.kfc com formato inesperado')

    def loc(i):
        p = 0x10 + i * 8
        off, cnt = struct.unpack_from('<II', d, p)
        return p + off, cnt
    ko, kn = loc(7)
    vo, _ = loc(8)
    out = {}
    for i in range(kn):
        key = struct.unpack_from('<IIII', d, ko + 16 * i)
        off, _flags, ci = struct.unpack_from('<IHH', d, vo + 16 * i)
        out[key] = (off, ci)
    return out


def read_loca(game_dir, contents, h):
    off, ci = contents[(h['size'], h['hash0'], h['hash1'], h['hash2'])]
    with open(os.path.join(game_dir, f'enshrouded_{ci:03}.dat'), 'rb') as f:
        f.seek(off)
        d = f.read(h['size'])
    _, n = struct.unpack_from('<II', d, 0)
    texts = {}
    for i in range(n):
        p = 8 + 24 * i
        k, ro, ln = struct.unpack_from('<III', d, p)
        t = d[p + 4 + ro:p + 4 + ro + ln].decode('utf-8', 'replace')
        texts[k] = re.sub(r'<[^>]+>', '', t).strip()  # tira marcacoes como <b> e <lorename>
    return texts


WEAPON_KINDS = [
    ('dagger', 'Adaga'), ('sword', 'Espada'), ('axe', 'Machado'), ('hammer', 'Martelo'), ('mace', 'Maça'),
    ('club', 'Clava'), ('spear', 'Lança'), ('bow', 'Arco'), ('staff', 'Cajado'), ('wand', 'Varinha'),
    ('shield', 'Escudo'), ('torch', 'Tocha'), ('grenade', 'Explosivo'), ('bomb', 'Explosivo'),
]
ARMOR_SLOTS = {'Armour_Head': 'Cabeça', 'Armour_UpperBody': 'Peito', 'Armour_LowerBody': 'Pernas',
               'Armour_Arms': 'Mãos', 'Armour_Feet': 'Pés'}
CATEGORY_TYPES = {
    'Materials': 'Material', 'Ammunition': 'Munição', 'BuildTools': 'Construção', 'Tools': 'Ferramenta',
    'WeaponGem': 'Gema / Runa', 'Blueprints': 'Projeto', 'Collectibles': 'Colecionável',
    'AnimalFood': 'Ração animal', 'Instrument': 'Instrumento', 'FishingRod': 'Ferramenta',
    'Customization': 'Aparência', 'ColorPalette': 'Aparência', 'Currency': 'Moeda',
}


def classify(j):
    cat = j.get('category') or ''
    slot = (j.get('equipment') or {}).get('slot') or ''
    dn = (j.get('debugName') or '').lower()
    if slot == 'Spell':
        return 'Feitiço', ''
    if slot == 'Shield':
        return 'Escudo', ''
    if slot in ARMOR_SLOTS:
        return 'Armadura', ARMOR_SLOTS[slot]
    if slot == 'Armour_Ring':
        return 'Acessório', 'Anel'
    if re.search(r'pickaxe|tool_|lockpick|key_', dn):
        return 'Ferramenta', 'Picareta' if 'pickaxe' in dn else ''
    if slot in ('Glider', 'HookShot', 'Backpack'):
        return 'Ferramenta', {'Glider': 'Planador', 'HookShot': 'Gancho', 'Backpack': 'Mochila'}[slot]
    if cat == 'Weapons' or slot in ('MeleeWeapon', 'RangeWeapon', 'MidRangeWeapon'):
        for k, v in WEAPON_KINDS:
            if re.search(k, dn):
                return ('Ferramenta' if v == 'Tocha' else 'Arma'), v
        return 'Arma', ''
    if cat == 'Consumables':
        if dn.startswith('food') or '_food' in dn:
            return 'Comida', ''
        if 'potion' in dn:
            return 'Consumível', 'Poção'
        return 'Consumível', ''
    if cat == 'Equipment':
        return ('Aparência', '') if dn.startswith(('vanity', 'icon_')) else ('Armadura', '')
    return CATEGORY_TYPES.get(cat, cat or 'Outro'), ''


def main(game_dir, unpacked):
    loca_res = json.load(open(glob.glob(os.path.join(unpacked, 'LocaTagCollectionResource', '*.json'))[0], encoding='utf-8'))
    langs = {l['language']: l['data']['hash'] for l in loca_res['languages']}
    contents = read_kfc_contents(game_dir)
    pt = read_loca(game_dir, contents, langs['Pt_Br'])
    en = read_loca(game_dir, contents, langs['En_Us'])

    items = {}
    for path in glob.glob(os.path.join(unpacked, 'ItemInfo', '*.json')):
        j = json.load(open(path, encoding='utf-8'))
        iid = (j.get('itemId') or {}).get('value')
        k = guid_key(j.get('name'))
        if not iid or k not in pt:
            continue
        kind, sub = classify(j)
        dk = guid_key(j.get('description'))
        rng = j.get('itemLevelRange') or {}
        entry = items[f'{iid:08x}'] = {
            'pt': pt[k], 'en': en.get(k, ''), 'type': kind, 'sub': sub,
            'rarity': j.get('rarity') or '', 'stack': j.get('maxStackSize') or 1,
            'desc': pt.get(dk, '') if dk else '', 'debug': j.get('debugName') or '',
        }
        if rng.get('maxLevel'):
            # faixa de nivel que o jogo permite para o item (melhorias nao passam do maximo)
            entry['lvl'] = [rng.get('minLevel') or 1, rng['maxLevel']]

    skills = {}
    for path in glob.glob(os.path.join(unpacked, 'SkillTreeResource', '*.json')):
        for node in json.load(open(path, encoding='utf-8')).get('nodes', []):
            nid, nk = node['id']['value'], node['name']['value']
            if nid and nk in pt:
                skills[f'{nid:08x}'] = {'pt': pt[nk], 'desc': pt.get(node['description']['value'], ''),
                                        'type': node.get('type', ''), 'class': node.get('classAlignment', ''),
                                        'max': node.get('maxLevel', 0)}

    version = open(os.path.join(game_dir, 'enshrouded.kfc'), 'rb').read(4096)
    m = re.search(rb'\d{6,}\|[^|]+\|[0-9T:\-.Z]+', version)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({'game_version': m.group().decode() if m else '', 'items': items, 'skills': skills},
                  f, ensure_ascii=False, separators=(',', ':'))
    print(f'{len(items)} itens e {len(skills)} habilidades gravados em {OUT}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
