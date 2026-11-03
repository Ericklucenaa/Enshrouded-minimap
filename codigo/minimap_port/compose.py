"""Traduz o mapa 26082781 -> 02/11 em 26082781 -> 03/11.

Para cada endereço do build de 02/11, acha o equivalente no build de 03/11:
- código: o mesmo trecho de instruções (relativos mascarados), procurado perto da posição prevista;
- dados: as instruções que referenciam o dado no build antigo são achadas no novo, e o destino
  delas no novo dá o endereço. Quando os dois métodos se aplicam, precisam concordar.
Uso: py compose.py final_map_02.json enshrouded_02nov.exe enshrouded_03nov.exe final_map.json
"""
import json, sys
import numpy as np
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP

MAP_IN, OLD, NEW, MAP_OUT = sys.argv[1:5]
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True


def load(p):
    pe = pefile.PE(p, fast_load=True)
    img = pe.get_memory_mapped_image()
    secs = {s.Name.rstrip(b'\0').decode(): (s.VirtualAddress, s.Misc_VirtualSize) for s in pe.sections}
    return img, secs


oimg, osec = load(OLD)
nimg, nsec = load(NEW)


def sec_of(secs, rva):
    for n, (a, z) in secs.items():
        if a <= rva < a + z: return n
    return None


def mask_code(code, rva):
    mask = [True] * len(code)
    for ins in md.disasm(code, rva):
        off = ins.address - rva
        if (ins.group(1) or ins.group(2) or ins.group(7)) and ins.imm_size == 4:
            for i in range(ins.imm_offset, ins.imm_offset + 4): mask[off + i] = False
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP and ins.disp_size == 4:
                for i in range(ins.disp_offset, ins.disp_offset + 4): mask[off + i] = False
    return mask


def find_code(rva, lo=-0x4000, hi=0x1000):
    """acha o trecho que começa em rva (build antigo) no build novo; janela cresce até ficar única"""
    for n in (24, 40, 64, 96, 160):
        code = bytes(oimg[rva:rva + n]); mask = mask_code(code, rva)
        fixed = [(t, code[t]) for t in range(n) if mask[t]]
        if len(fixed) < 12: continue
        t0, b0 = fixed[0]
        hits = []
        start, end = rva + lo, rva + hi
        region = nimg[start:end + n]
        k = region.find(bytes([b0]), 0)
        while k != -1:
            c = start + k - t0
            if all(nimg[c + t] == b for t, b in fixed):
                hits.append(c)
                if len(hits) > 1: break
            k = region.find(bytes([b0]), k + 1)
        if len(hits) == 1: return hits[0], n
        if not hits: return None, n
    return None, n


# referências [rip+disp32] no .text antigo (posição do disp32 cujo destino é o alvo)
ta, tz = osec['.text']
a = np.frombuffer(bytes(oimg[ta:ta + tz]), dtype=np.uint8).astype(np.uint32)
d = a[:-3] | (a[1:-2] << 8) | (a[2:-1] << 16) | (a[3:] << 24)
pos = np.arange(len(d), dtype=np.uint32)
dest = (pos + np.uint32(ta + 4) + d).astype(np.uint32)   # válido quando o disp32 é o fim da instrução
del a, d


def data_refs(target, want=6):
    out = []
    for p in np.nonzero(dest == np.uint32(target))[0][:400]:
        p = int(p) + ta
        for back in range(2, 9):     # começo da instrução
            s = p - back
            ins = next(md.disasm(bytes(oimg[s:s + 16]), s, 1), None)
            if not ins or ins.disp_size != 4 or s + ins.disp_offset != p: continue
            if not any(op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP and s + ins.size + op.mem.disp == target for op in ins.operands): continue
            out.append(s); break
        if len(out) >= want: break
    return out


def map_data(target):
    votes = {}
    for s in data_refs(target):
        ns, _ = find_code(s)
        if ns is None: continue
        ins = next(md.disasm(bytes(nimg[ns:ns + 16]), ns, 1), None)
        old = next(md.disasm(bytes(oimg[s:s + 16]), s, 1))
        if not ins or ins.mnemonic != old.mnemonic or ins.size != old.size: continue
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                t = ns + ins.size + op.mem.disp
                votes[t] = votes.get(t, 0) + 1
    return votes


def map_rdata_content(rva, n=48):
    """dados constantes: mesmos bytes perto da posição prevista (rdata andou ~-0x1000)"""
    blob = bytes(oimg[rva:rva + n])
    if len(set(blob)) < 6: return None
    lo = rva - 0x3000; region = bytes(nimg[lo:rva + 0x1000])
    k = region.find(blob)
    if k == -1 or region.find(blob, k + 1) != -1: return None
    return lo + k


M = {int(k, 16): int(v, 16) for k, v in json.load(open(MAP_IN)).items()}
out, bad = {}, []
for k, v in sorted(M.items(), key=lambda x: x[1]):
    s = sec_of(osec, v)
    how = ''
    if s == '.text':
        nv, n = find_code(v)
        how = f'código({n})'
        if nv is None:
            votes = map_data(v)        # dado dentro do .text (ex.: tabela de saltos)
            if len(votes) == 1: nv = next(iter(votes)); how = f'refs{list(votes.values())}'
    elif s in ('.rdata', '.data'):
        votes = map_data(v)
        cont = map_rdata_content(v) if s == '.rdata' else None
        if len(votes) == 1:
            nv = next(iter(votes)); how = f'refs{list(votes.values())}'
            if cont is not None and cont != nv: nv = None; how = f'CONFLITO refs={hex(next(iter(votes)))} conteúdo={hex(cont)}'
            elif cont is not None: how += '+conteúdo'
        elif len(votes) > 1:
            nv = None; how = 'refs discordam ' + str({hex(x): y for x, y in votes.items()})
        else:
            nv = cont; how = 'conteúdo' if cont is not None else 'sem refs nem conteúdo'
    else:
        nv = None; how = f'seção {s}'
    if nv is None: bad.append((hex(k), hex(v), s, how))
    else: out[hex(k)] = hex(nv)
    print(f'{hex(k):>10} {hex(v):>10} {s or "?":7s} -> {hex(nv) if nv is not None else "??":>10}  delta {(nv - v) if nv is not None else 0:+#x}  {how}')

print('\nmapeados', len(out), 'de', len(M))
for b in bad: print('FALTA', b)
json.dump(out, open(MAP_OUT, 'w'), indent=1)
