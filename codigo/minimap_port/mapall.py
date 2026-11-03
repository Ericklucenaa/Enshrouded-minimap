import json, sys, re
argv = sys.argv[:]
sys.argv = argv[:4]
exec(open(__file__.replace('mapall.py', 'scan.py'), encoding='utf-8').read().split('res = {}')[0])
r = json.load(open(OUT))
manual = {0x9b6e60: 0x9c26c0, 0x9b4230: 0x9bf920, 0x9b43d0: 0x9bfac0, 0xbc230b: 0xbd139b, 0xbc2554: 0xbd15f4,
          0xbc1fc6: 0xbd1056, 0xbc24ba: 0xbd154a, 0xbc24e9: 0xbd1579, 0xd6c860: 0xd80e70, 0xeaa9b2: 0xec1d02,
          0xfd4620: 0xfeda70}
m = {}
src = {}
for k, v in r.items():
    for e in v:
        if e['exec'] and len(e['hits']) == 1: m[int(k, 16)] = int(e['hits'][0], 16); src[int(k, 16)] = 'assinatura'
m.update(manual); src.update({k: 'assinatura (conferida à mão)' for k in manual})
# referências relativas (call/jmp/lea/mov [rip]) de todos os trechos mapeados
for rva, off, n, ex in sigs:
    if not ex or rva not in m: continue
    code = sigbytes[off:off + n]
    mask, refs, dec = masked(code, rva)
    new = m[rva]
    for p, sz, old_t, end, kind in refs:
        disp = int.from_bytes(img[new + p:new + p + 4], 'little', signed=True)
        nt = new + end + disp
        if old_t in m and m[old_t] != nt: print('CONFLITO', hex(old_t), hex(m[old_t]), hex(nt))
        if old_t not in m: m[old_t] = nt; src[old_t] = f'referência em {hex(rva)}'
# dados: 0x13b9edc (assinatura de dado, 4 bytes)
prof = open(os.path.join(SRC, 'src', 'client_1_0_profile.h'), encoding='utf-8').read()
need = sorted(set(int(x, 16) for x in re.findall(r'return (0x[0-9a-f]+);', prof)))
missing = [x for x in need if x not in m]
print('endereços do perfil:', len(need), 'mapeados:', len(need) - len(missing))
for x in missing: print('  falta', hex(x))
json.dump({hex(k): [hex(v), src[k]] for k, v in sorted(m.items())}, open(OUT.replace('scan.json', 'map.json'), 'w'), indent=1)
