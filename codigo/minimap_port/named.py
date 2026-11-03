import json, struct, sys
import pefile
EXE, MAP = sys.argv[1], sys.argv[2]
pe = pefile.PE(EXE, fast_load=True)
img = pe.get_memory_mapped_image()
base = pe.OPTIONAL_HEADER.ImageBase
m = json.load(open(MAP))
mp = {int(k, 16): int(v[0], 16) for k, v in m.items()}

# (descritor antigo, nome, função antiga) — valores do build 26082781 (já passados pelo Rva())
systems = [
    (0x1e04490, 'player_camera_transform', 0x2b2b60),
    (0x1e0e400, 'player_waypoints_ui', 0x30eb10),
    (0x1e04660, 'player_daytime_ui', 0x2b3340),
    (0x1e08620, 'client_update_daytime', 0x3027b0),
    (0x1e05560, 'ambient_effects', 0x2fd9a0),
    (0x1e063d0, 'clear_map_markers_for_ui', 0x2fefe0),
    (0x1e09410, 'custom_map_markers_ui', 0x303360),
    (0x1e0f970, 'replicate_map_markers_for_ui', 0x310cb0),
    (0x1e0a960, 'fog_of_war', 0x3071e0),
    (0x1e13e00, 'update_ui_data', 0x317e80),
    (0x1dea720, 'knowledge_query_mapmarker_visibility', 0x415140),
]
out = {}
for od, name, of in systems:
    s = name.encode() + b'\0'
    hits = []
    k = img.find(s)
    while k != -1:
        if k == 0 or img[k - 1] == 0: hits.append(k)
        k = img.find(s, k + 1)
    descs = []
    for sh in hits:
        needle = struct.pack('<QQ', base + sh, len(name))
        j = img.find(needle)
        while j != -1:
            fn = struct.unpack_from('<Q', img, j + 16)[0] - base
            descs.append((j, fn))
            j = img.find(needle, j + 1)
    print(f'{name}: strings={len(hits)} descritores={[(hex(d), hex(f)) for d, f in descs]}')
    if len(descs) == 1:
        d, f = descs[0]
        out[hex(od)] = hex(d)
        exp = mp.get(of)
        print(f'    descritor {hex(od)} -> {hex(d)} | função {hex(of)} -> {hex(f)}' +
              ('' if exp is None else ('  (bate com a assinatura)' if exp == f else f'  !!! assinatura diz {hex(exp)}')))
        if exp is None: out[hex(of)] = hex(f)

# tabela do clima: Clear, Rain, Snow, Blizzard em passos de 0x28, valor em +0x10
def strva(t):
    k = img.find(t.encode() + b'\0')
    while k != -1 and img[k - 1] != 0: k = img.find(t.encode() + b'\0', k + 1)
    return k
names = ['Clear', 'Rain', 'Snow', 'Blizzard']
cands = []
for k in range(0, len(img) - 0xa0, 8):
    pass
c = strva('Clear')
allc = []
k = img.find(b'Clear\0')
while k != -1:
    if img[k - 1] == 0: allc.append(k)
    k = img.find(b'Clear\0', k + 1)
for cs in allc:
    j = img.find(struct.pack('<Q', base + cs))
    while j != -1:
        ok = True
        for i, n in enumerate(names):
            p = struct.unpack_from('<Q', img, j + i * 0x28)[0] - base
            v = struct.unpack_from('<Q', img, j + i * 0x28 + 0x10)[0]
            if not (0 <= p < len(img) and img[p:p + len(n) + 1] == n.encode() + b'\0' and v == i): ok = False; break
        if ok: cands.append(j)
        j = img.find(struct.pack('<Q', base + cs), j + 1)
print('tabela do clima:', [hex(x) for x in cands])
if len(cands) == 1: out['0x1bbd820'] = hex(cands[0])
json.dump(out, open(MAP.replace('map.json', 'named.json'), 'w'), indent=1)
