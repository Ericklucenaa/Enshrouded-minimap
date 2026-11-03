import json, sys, bisect
sys.argv = [sys.argv[0]] + sys.argv[1:]
exec(open(__file__.replace('fuzzy.py', 'scan.py'), encoding='utf-8').read().split('res = {}')[0])
r = json.load(open(OUT))
ok = sorted((int(k, 16), int(e['hits'][0], 16)) for k, v in r.items() for e in v if e['exec'] and len(e['hits']) == 1)
olds = [o for o, _ in ok]

def predict(rva):
    i = bisect.bisect_left(olds, rva)
    lo = ok[max(0, i - 1)]; hi = ok[min(len(ok) - 1, i)]
    if hi[0] == lo[0]: return rva + (lo[1] - lo[0]), lo[1] - lo[0], hi[1] - hi[0]
    t = (rva - lo[0]) / (hi[0] - lo[0])
    d = (lo[1] - lo[0]) + t * ((hi[1] - hi[0]) - (lo[1] - lo[0]))
    return int(rva + d), lo[1] - lo[0], hi[1] - hi[0]

for rva, off, n, ex in sigs:
    if not ex: continue
    e = [x for x in r[hex(rva)] if x['n'] == n][0]
    if len(e['hits']) == 1: continue
    code = sigbytes[off:off + n]
    mask, refs, dec = masked(code, rva)
    p, dlo, dhi = predict(rva)
    lo_c, hi_c = rva + min(dlo, dhi) - 0x3000, rva + max(dlo, dhi) + 0x3000
    best = []
    for c in range(lo_c, hi_c):
        sc = sum(1 for t, m in enumerate(mask) if m and img[c + t] == code[t])
        best.append((sc, c))
    best.sort(reverse=True)
    fixed = mask.count(True)
    print(f'{hex(rva)} n={n} fixos={fixed} previsto={hex(p)} (delta {hex(dlo)}..{hex(dhi)})')
    for sc, c in best[:3]:
        print(f'    {hex(c)} delta={hex(c - rva)} acertos={sc}/{fixed}')
    print('    hits exatos perto:', [h for h in e['hits'] if abs(int(h, 16) - p) < 0x4000])
