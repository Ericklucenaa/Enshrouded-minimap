"""Conta quantas vezes cada padrão (texto 'AA BB ?? CC') da DLL do altar aparece no .text do exe novo."""
import re, sys
import pefile
DLL, EXE = sys.argv[1], sys.argv[2]
pe = pefile.PE(EXE, fast_load=True)
text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
code = text.get_data(); base = text.VirtualAddress
d = pefile.PE(DLL)
rd = [s for s in d.sections if s.Name.startswith(b'.rdata')][0]
strs = [(rd.VirtualAddress + m.start(), m.group().decode()) for m in re.finditer(rb'[\x20-\x7e]{5,}', rd.get_data())]
pats = [(a, s) for a, s in strs if re.fullmatch(r'([0-9A-F]{2}|\?\?|%s)( ([0-9A-F]{2}|\?\?|%s))+', s)]


def to_re(p):
    out = b''
    for t in p.split():
        out += b'.' if t == '??' else (b'.' if t == '%s' else re.escape(bytes([int(t, 16)])))
    return re.compile(out, re.S)


for a, p in pats:
    hits = [base + m.start() for m in to_re(p).finditer(code)]
    print(f'{hex(a)} hits={len(hits):<3} {[hex(h) for h in hits[:4]]}  {p[:70]}')
