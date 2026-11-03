"""Acha no enshrouded.exe novo onde foi parar cada trecho de código que o minimapa usa.

Lê a tabela de assinaturas do build 26082781 (client_1_0_file_signatures.h), mascara os
deslocamentos relativos (call/jmp/jcc rel32, [rip+disp32]) e procura no .text novo.
Também calcula, a partir de cada match, o novo destino de cada referência relativa
(funções chamadas e dados globais), para mapear endereços que não têm assinatura própria.
"""
import json, os, re, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP

SRC = sys.argv[1]          # pasta do código do minimapa
EXE = sys.argv[2]          # enshrouded.exe novo
OUT = sys.argv[3]          # json de saída

hdr = open(os.path.join(SRC, 'src', 'client_1_0_file_signatures.h'), encoding='utf-8').read()
body = hdr.split('CurrentSignatureBytes[] = {', 1)[1].split('};', 1)[0]
sigbytes = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]{2})', body))
sigs = [(int(a, 16), int(o), int(n), e == 'true') for a, o, n, e in
        re.findall(r'\{\s*0x([0-9a-fA-F]+)u,\s*(\d+)u,\s*(\d+)u,\s*(true|false)\s*\}', hdr.split('CurrentSignatures[] = {', 1)[1])]
assert len(sigbytes) == 2577 and len(sigs) == 51, (len(sigbytes), len(sigs))

pe = pefile.PE(EXE, fast_load=True)
img = pe.get_memory_mapped_image()
text = [s for s in pe.sections if s.Characteristics & 0x20000000]
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True


def masked(code, rva):
    """máscara (True = byte fixo) e lista de referências relativas [(pos, tamanho, destino_antigo, fim_instr)]"""
    mask = [True] * len(code); refs = []
    pos = 0
    for ins in md.disasm(code, rva):
        pos = ins.address - rva + ins.size
        off = ins.address - rva
        # call/jmp/jcc rel
        if ins.group(1) or ins.group(2) or ins.group(7):   # JUMP, CALL, BRANCH_RELATIVE
            for op in ins.operands:
                if op.type == X86_OP_IMM and ins.imm_size and ins.imm_offset:
                    if ins.imm_size == 4:
                        for i in range(ins.imm_offset, ins.imm_offset + 4): mask[off + i] = False
                        refs.append((off + ins.imm_offset, 4, op.imm, off + ins.size, 'code'))
                    # rel8 (jumps curtos) fica fixo: se a função mudou por dentro, não bate
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP and ins.disp_size == 4:
                for i in range(ins.disp_offset, ins.disp_offset + 4): mask[off + i] = False
                refs.append((off + ins.disp_offset, 4, ins.address + ins.size + op.mem.disp, off + ins.size, 'data'))
    # resto que não decodificou (assinatura cortada no meio de uma instrução): deixa fixo,
    # mas se for o começo de um call/jmp, mascara
    return mask, refs, pos


def search(code, mask):
    # procura a parte fixa mais longa primeiro e confere o resto
    best = (0, 0); i = 0
    while i < len(code):
        if mask[i]:
            j = i
            while j < len(code) and mask[j]: j += 1
            if j - i > best[1] - best[0]: best = (i, j)
            i = j
        else: i += 1
    anchor = code[best[0]:best[1]]
    hits = []
    for s in text:
        base = s.VirtualAddress; data = img[base: base + s.Misc_VirtualSize]
        k = data.find(anchor)
        while k != -1:
            start = k - best[0]
            if start >= 0 and all((not m) or data[start + t] == code[t] for t, m in enumerate(mask)):
                hits.append(base + start)
                if len(hits) > 20: return hits
            k = data.find(anchor, k + 1)
    return hits


res = {}
for rva, off, n, ex in sigs:
    code = sigbytes[off:off + n]
    if not ex:
        res.setdefault(hex(rva), []).append({'n': n, 'exec': False, 'hits': [], 'note': 'dado'})
        continue
    mask, refs, dec = masked(code, rva)
    hits = search(code, mask)
    entry = {'n': n, 'exec': True, 'hits': [hex(h) for h in hits], 'decoded': dec, 'masked': mask.count(False), 'refs': []}
    if len(hits) == 1:
        new = hits[0]
        for p, sz, old_t, end, kind in refs:
            disp = int.from_bytes(img[new + p: new + p + 4], 'little', signed=True)
            entry['refs'].append({'kind': kind, 'old': hex(old_t), 'new': hex(new + end + disp)})
    res.setdefault(hex(rva), []).append(entry)

json.dump(res, open(OUT, 'w'), indent=1)
ok = sum(1 for v in res.values() for e in v if e['exec'] and len(e['hits']) == 1)
tot = sum(1 for v in res.values() for e in v if e['exec'])
print(f'{ok}/{tot} trechos de código achados com match único')
for k, v in res.items():
    for e in v:
        if e['exec'] and len(e['hits']) != 1:
            print('  sem match único:', k, 'n=', e['n'], 'hits=', e['hits'][:5])
