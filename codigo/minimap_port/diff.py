import sys
argv = sys.argv[:]
sys.argv = argv[:4]
exec(open(__file__.replace('diff.py', 'scan.py'), encoding='utf-8').read().split('res = {}')[0])
pairs = [(int(a, 16), int(b, 16)) for a, b in (p.split('=') for p in argv[4:])]
for old, new in pairs:
    for rva, off, n, ex in sigs:
        if rva != old: continue
        code = sigbytes[off:off + n]
        newc = img[new:new + n + 8]
        print(f'===== {hex(old)} -> {hex(new)} (n={n})')
        a = [(i.address - old, i.mnemonic + ' ' + i.op_str, i.bytes.hex()) for i in md.disasm(code, old)]
        b = [(i.address - new, i.mnemonic + ' ' + i.op_str, i.bytes.hex()) for i in md.disasm(newc, new)]
        bm = {x[0]: x for x in b}
        for o, t, h in a:
            nb = bm.get(o)
            same = nb and nb[2] == h
            print(('   ' if same else '>> ') + f'+{o:3x} {t:45s} | ' + (nb[1] if nb else '??'))
