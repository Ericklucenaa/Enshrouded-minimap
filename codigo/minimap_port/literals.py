import json, os, re, sys
SRC = sys.argv[1]; MAPDIR = sys.argv[2]
m = {int(k, 16): int(v[0], 16) for k, v in json.load(open(os.path.join(MAPDIR, 'map.json'))).items()}
for f in ('named.json', 'rest.json'):
    for k, v in json.load(open(os.path.join(MAPDIR, f))).items():
        if k.endswith('cands'): continue
        m[int(k, 16)] = int(v, 16)
m[0x13b9edc] = 0x13d7edc
prof = open(os.path.join(SRC, 'src', 'client_1_0_profile.h'), encoding='utf-8').read()
old2cur = {int(a, 16): int(b, 16) for a, b in re.findall(r'case (0x[0-9a-f]+): return (0x[0-9a-f]+);', prof)}
json.dump({hex(k): hex(v) for k, v in sorted(m.items())}, open(os.path.join(MAPDIR, 'final_map.json'), 'w'), indent=1)
cur = set(old2cur.values())
print('perfil completo?', all(v in m for v in cur))
seen = {}
for root, _, files in os.walk(os.path.join(SRC, 'src')):
    for fn in files:
        if not fn.endswith(('.cpp', '.h', '.hpp')) or fn in ('client_1_0_file_signatures.h',): continue
        for ln, line in enumerate(open(os.path.join(root, fn), encoding='utf-8', errors='ignore'), 1):
            if 'BytesMatchRva' in line and fn == 'client_1_0_guards.h': continue
            for h in re.findall(r'0x([0-9a-fA-F]{6,7})\b', line):
                v = int(h, 16)
                if not (0x200000 <= v <= 0x2a00000): continue
                if v in old2cur: kind = 'chave-antiga(ok via Rva)'
                elif v in m: kind = 'atual-mapeado'
                else: kind = '???'
                seen.setdefault((kind, v), []).append(f'{fn}:{ln}')
for (kind, v), locs in sorted(seen.items()):
    if kind != 'chave-antiga(ok via Rva)':
        print(f'{kind:14s} {hex(v):10s} {", ".join(locs[:4])}')
