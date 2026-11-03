"""Gera a versão do minimapa para o enshrouded.exe novo (porta o perfil "current" 26082781 -> build novo).

Uso: python port.py <pasta do código> <enshrouded.exe novo> <pasta mmport> [--write]
Sem --write só confere e lista as diferenças.
"""
import hashlib, json, os, re, struct, sys, bisect
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP

SRC, EXE, MM = sys.argv[1], sys.argv[2], sys.argv[3]
WRITE = '--write' in sys.argv
S = lambda *p: os.path.join(SRC, 'src', *p)
pe = pefile.PE(EXE, fast_load=True)
img = pe.get_memory_mapped_image()
raw = open(EXE, 'rb').read()
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
M = {int(k, 16): int(v, 16) for k, v in json.load(open(os.path.join(MM, 'final_map.json'))).items()}
KNOWN_OFFSETS = {(0x828, 0x830), (0x830, 0x838)}   # campo que andou 8 bytes nesta atualização
# primaryRow: o nop de alinhamento ficou 1 byte menor (66 0f 1f 44 00 00 -> 0f 1f 44 00 00); o resto é igual
REVIEWED = {(0xd8f428, 0xda485d)}
MANUAL = {0xd8f428: 0xda485d}
problems = []
text = [s for s in pe.sections if s.Characteristics & 0x20000000]


def norm_ins(i):
    """instrução sem os deslocamentos relativos"""
    ops = []
    for op in i.operands:
        if op.type == X86_OP_MEM:
            ops.append(('m', op.mem.base, op.mem.index, op.mem.scale, None if op.mem.base == X86_REG_RIP else op.mem.disp, op.mem.segment))
        elif op.type == X86_OP_IMM:
            ops.append(('i', None if (i.group(1) or i.group(2) or i.group(7)) else op.imm))
        else:
            ops.append(('r', op.reg))
    return (i.mnemonic, i.size, tuple(ops))


def compare(old_rva, old_bytes, new_rva, label, data=False):
    new_bytes = bytes(img[new_rva:new_rva + len(old_bytes)])
    if new_bytes == old_bytes:
        return new_bytes, []
    if data:
        return new_bytes, [f'dados diferentes (aceito: tabela/constante remapeada)']
    a = list(md.disasm(old_bytes, old_rva)); b = list(md.disasm(new_bytes, new_rva))
    diffs = []
    pa = sum(x.size for x in a); pb = sum(x.size for x in b)
    for x, y in zip(a, b):
        if norm_ins(x) == norm_ins(y):
            # confere se o alvo relativo foi para o lugar mapeado (quando o alvo é conhecido)
            for ox, oy in zip(x.operands, y.operands):
                if ox.type == X86_OP_IMM and (x.group(1) or x.group(2) or x.group(7)) and x.imm_size == 4:
                    if ox.imm in M and M[ox.imm] != oy.imm:
                        diffs.append(f'!! {x.mnemonic} alvo {hex(ox.imm)} foi para {hex(oy.imm)} mas o mapa diz {hex(M[ox.imm])}')
                if ox.type == X86_OP_MEM and ox.mem.base == X86_REG_RIP:
                    t0 = x.address + x.size + ox.mem.disp; t1 = y.address + y.size + oy.mem.disp
                    if t0 in M and M[t0] != t1:
                        diffs.append(f'!! [rip] {hex(t0)} foi para {hex(t1)} mas o mapa diz {hex(M[t0])}')
            continue
        # campo conhecido que mudou? / endereço de tabela (RVA absoluto no deslocamento) que bate com o mapa?
        ok = False; why = '   campo conhecido: '
        if (x.mnemonic, x.size) == (y.mnemonic, y.size):
            dx = [op.mem.disp for op in x.operands if op.type == X86_OP_MEM]
            dy = [op.mem.disp for op in y.operands if op.type == X86_OP_MEM]
            if dx and dy and (dx[0], dy[0]) in KNOWN_OFFSETS: ok = True
            elif dx and dy and dx[0] in M and M[dx[0]] == dy[0]: ok = True; why = '   tabela no endereço mapeado: '
        if not ok and (old_rva, new_rva) in REVIEWED: ok = True; why = '   revisado à mão: '
        diffs.append((why if ok else '!! ') + f'{x.mnemonic} {x.op_str}  ->  {y.mnemonic} {y.op_str}')
    # bytes que sobram depois da última instrução inteira (assinatura cortada no meio)
    if pa < len(old_bytes) and old_bytes[pa:] != new_bytes[pb:]:
        diffs.append(f'   cauda (instrução cortada) {old_bytes[pa:].hex()} -> {new_bytes[pb:].hex()}')
    return new_bytes, diffs


def report(label, old_rva, new_rva, diffs):
    bad = [d for d in diffs if d.startswith('!!')]
    if bad: problems.append((label, hex(old_rva), bad))
    print(f'{label:28s} {hex(old_rva):>10} -> {hex(new_rva):<10} ' + ('igual' if not diffs else f'{len(diffs)} diferença(s)'))
    for d in diffs: print('        ' + d)


cbytes = lambda s: bytes(int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]{1,2})\b', s))
fmt_c = lambda b: ','.join(f'0x{x:02x}' for x in b)
fmt_sv = lambda b: ''.join(f'\\x{x:02x}' for x in b)


# ---------- 1) assinaturas do arquivo ----------
sig_h = open(S('client_1_0_file_signatures.h'), encoding='utf-8').read()
body = sig_h.split('CurrentSignatureBytes[] = {', 1)[1].split('};', 1)[0]
sb = cbytes(body)
tab = re.findall(r'\{\s*0x([0-9a-fA-F]+)u,\s*(\d+)u,\s*(\d+)u,\s*(true|false)\s*\}', sig_h.split('CurrentSignatures[] = {', 1)[1])
newsb = bytearray(); newtab = []
print('== assinaturas do arquivo')
for a, o, n, e in tab:
    a, o, n = int(a, 16), int(o), int(n)
    na = M[a]
    nb, d = compare(a, sb[o:o + n], na, 'assinatura', data=(e == 'false') or a == 0xbc2554)
    report('assinatura', a, na, d)
    newtab.append((na, len(newsb), n, e)); newsb += nb
assert len(newsb) == len(sb)

# ---------- 2) guards (MatchX26082781) ----------
gh = open(S('client_1_0_guards.h'), encoding='utf-8').read()
print('== guards')
def patch_guards(text_):
    out = []
    for fn in re.split(r'(?=^bool Match)', text_, flags=re.M):
        if '26082781()' not in fn.split('\n', 1)[0]:
            out.append(fn); continue
        arrays = dict(re.findall(r'const std::uint8_t (b\d+)\[\] = \{([^}]*)\};', fn))
        for rva, name in re.findall(r'BytesMatchRva\((0x[0-9a-f]+),(b\d+),', fn):
            r0 = int(rva, 16); nr = M[r0]
            nb, d = compare(r0, cbytes(arrays[name]), nr, 'guard', data=(r0 in (0x13b9edc, 0xbc2554)))
            report('guard ' + fn.split('(')[0][5:], r0, nr, d)
            fn = re.sub(r'(const std::uint8_t ' + name + r'\[\] = \{)[^}]*(\};)', lambda m_: m_.group(1) + fmt_c(nb) + m_.group(2), fn, count=1)
            fn = fn.replace(f'BytesMatchRva({rva},{name},', f'BytesMatchRva({hex(nr)},{name},')
        out.append(fn)
    return ''.join(out)
gh2 = patch_guards(gh)

# ---------- 3) menu_visibility_1_0.h (currentGuards) ----------
mh = open(S('menu_visibility_1_0.h'), encoding='utf-8').read()
print('== menu')
cur = mh.split('constexpr Guard currentGuards[] = {', 1)[1].split('};', 1)[0]
newcur = cur
for rva, sv in re.findall(r'\{(0x[0-9a-f]+), "((?:\\x[0-9a-f]{2})*)"sv\}', cur):
    r0 = int(rva, 16); nr = M[r0]
    ob = bytes(int(x, 16) for x in re.findall(r'\\x([0-9a-f]{2})', sv))
    nb, d = compare(r0, ob, nr, 'menu', data=(r0 == 0xbc2554))
    report('menu', r0, nr, d)
    newcur = newcur.replace(f'{{{rva}, "{sv}"sv}}', f'{{{hex(nr)}, "{fmt_sv(nb)}"sv}}')
mh2 = mh.replace(cur, newcur)
mh2 = mh2.replace('currentBuild ? 0xc4fc40u', f'currentBuild ? {hex(M[0xc4fc40])}u').replace('currentBuild ? 0xbc24bau', f'currentBuild ? {hex(M[0xbc24ba])}u')
mh2 = mh2.replace('UiContextRva = 0x281b498', 'UiContextRva = 0x281b498')  # chave antiga (passa pelo Rva())

# ---------- 4) vulkan_startup.h ----------
vh = open(S('vulkan_startup.h'), encoding='utf-8').read()
print('== vulkan')
blk = vh.split('bool MatchVulkanStartupCallsite()', 1)[1].split('bool PrepareVulkanStartupCallsite()', 1)[0]
arrays = dict(re.findall(r'const std::uint8_t (\w+)\[\] = \{([^}]*)\};', blk))
nblk = blk
for rva, name in re.findall(r'BytesMatchRva\((0x[0-9A-Fa-f]+), (\w+),', blk):
    r0 = int(rva, 16); nr = M[r0]
    nb, d = compare(r0, cbytes(arrays[name]), nr, 'vulkan')
    report('vulkan ' + name, r0, nr, d)
    nblk = re.sub(r'(const std::uint8_t ' + name + r'\[\] = \{)[^}]*(\};)', lambda m_: m_.group(1) + fmt_c(nb) + m_.group(2), nblk, count=1)
    nblk = nblk.replace(f'BytesMatchRva({rva}, {name},', f'BytesMatchRva({hex(nr).upper().replace("0X", "0x")}, {name},')
vh2 = vh.replace(blk, nblk)

# ---------- 5) dllmain: filtro nativo, slot global, campo 0x828 ----------
dm = open(S('dllmain.cpp'), encoding='utf-8').read()
print('== filtro nativo (dllmain)')
fblk = dm.split('bool HasVerifiedNativeFilterProbeCodeSpans()', 1)[1].split('bool NativeFilterProbeLayoutSupported()', 1)[0]
arrays = dict(re.findall(r'static constexpr std::uint8_t (\w+)\[\] = \{([^}]*)\};', fblk))
olds = sorted(M);
def predict_scan(r0, ob):
    # mascara relativos e procura perto do previsto
    mask = [True] * len(ob)
    for i in md.disasm(ob, r0):
        off = i.address - r0
        if (i.group(1) or i.group(2) or i.group(7)) and i.imm_size == 4:
            for k in range(i.imm_offset, i.imm_offset + 4): mask[off + k] = False
        for op in i.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP and i.disp_size == 4:
                for k in range(i.disp_offset, i.disp_offset + 4): mask[off + k] = False
    j = bisect.bisect_left(olds, r0)
    near = [olds[max(0, j - 1)], olds[min(len(olds) - 1, j)]]
    ds = [M[x] - x for x in near]
    lo, hi = r0 + min(ds) - 0x6000, r0 + max(ds) + 0x6000
    best = []
    for c in range(lo, hi):
        sc = 0
        for t, mk in enumerate(mask):
            if mk:
                if img[c + t] != ob[t]: break
                sc += 1
        else:
            best.append(c)
    return best, mask.count(True)
nf = fblk
for rva, name in re.findall(r'BytesMatchRva\((0x[0-9A-Fa-f]+), (\w+),', fblk):
    r0 = int(rva, 16); ob = cbytes(arrays[name])
    hits, fixed = ([MANUAL[r0]], 0) if r0 in MANUAL else predict_scan(r0, ob)
    if len(hits) != 1:
        problems.append(('filtro ' + name, hex(r0), [f'!! {len(hits)} candidatos {[hex(h) for h in hits[:5]]}']))
        print(f'filtro {name:22s} {hex(r0)} -> ?? {len(hits)} candidatos'); continue
    nr = hits[0]; M[r0] = nr
    nb, d = compare(r0, ob, nr, 'filtro')
    report('filtro ' + name, r0, nr, d)
    nf = re.sub(r'(static constexpr std::uint8_t ' + name + r'\[\] = \{)[^}]*(\};)', lambda m_: m_.group(1) + fmt_c(nb) + m_.group(2), nf, count=1)
    nf = nf.replace(f'BytesMatchRva({rva}, {name},', f'BytesMatchRva({hex(nr).upper().replace("0X", "0x")}, {name},')
dm2 = dm.replace(fblk, nf)
dm2 = dm2.replace('0x281E498', hex(M[0x281e498]).upper().replace('0X', '0x'))
assert dm2.count('ClientOffset(0x7E0,0x828)') == 1
dm2 = dm2.replace('ClientOffset(0x7E0,0x828)', 'ClientOffset(0x7E0,0x830)')

# ---------- 6) perfil: Rva(), Vulkan, hash do exe ----------
ph = open(S('client_1_0_profile.h'), encoding='utf-8').read()
ph2 = re.sub(r'case (0x[0-9a-f]+): return (0x[0-9a-f]+);', lambda m_: f'case {m_.group(1)}: return {hex(M[int(m_.group(2), 16)])};', ph)
ph2 = ph2.replace('? 0xFBF573 : 0', f'? {hex(M[0xfbf54b] + (0xfbf573 - 0xfbf54b)).upper().replace("0X", "0x")} : 0')
ph2 = ph2.replace('? 0xFE0BE0 : 0', f'? {hex(M[0xfe0be0]).upper().replace("0X", "0x")} : 0')
sha = hashlib.sha256(raw).hexdigest()
b = bytearray(raw); pe_off = struct.unpack_from('<I', b, 60)[0]
b[pe_off + 8:pe_off + 12] = b'\0' * 4; b[pe_off + 24 + 64:pe_off + 24 + 68] = b'\0' * 4
meta = hashlib.sha256(b).hexdigest()
ph2 = re.sub(r'constexpr const char\* CurrentSha256 = "[0-9a-f]+";', f'constexpr const char* CurrentSha256 = "{sha}";', ph2)
ph2 = re.sub(r'MatchesMetadataVariant\(path, 35338312,\s*"[0-9a-f]+"\)', f'MatchesMetadataVariant(path, {len(raw)},\n            "{meta}")', ph2)

# ---------- 7) layout do arquivo ----------
lh = open(S('client_1_0_file_layout.h'), encoding='utf-8').read()
call_new = M[0xfbf54b] + (0xfbf573 - 0xfbf54b)
lh2 = lh.replace('StartupCallRva = 0x00fbf573', f'StartupCallRva = 0x{call_new:08x}').replace('StartupTargetRva = 0x00fe0be0', f'StartupTargetRva = 0x{M[0xfe0be0]:08x}')
# confere o call direto no exe novo
op = img[call_new]; rel = struct.unpack_from('<i', img, call_new + 1)[0]
print(f'== call do Vulkan em {hex(call_new)}: opcode {op:#x} destino {hex(call_new + 5 + rel)} (esperado {hex(M[0xfe0be0])}) alinhamento {call_new & 7}')
if op != 0xe8 or call_new + 5 + rel != M[0xfe0be0] or (call_new & 7) != 3: problems.append(('vulkan call', hex(call_new), ['!! call não confere']))

lines = []
for i in range(0, len(newsb), 16): lines.append('    ' + ', '.join(f'0x{x:02x}' for x in newsb[i:i + 16]) + ',')
sig_new = sig_h.split('inline constexpr std::uint8_t CurrentSignatureBytes[] = {')[0] + 'inline constexpr std::uint8_t CurrentSignatureBytes[] = {\n' + '\n'.join(lines) + '\n};\ninline constexpr Signature CurrentSignatures[] = {\n' + \
    '\n'.join(f'    {{ 0x{a:08x}u, {o}u, {n}u, {e} }},' for a, o, n, e in newtab) + '\n};' + sig_h.split('CurrentSignatures[] = {', 1)[1].split('};', 1)[1]

# tabela de saltos do menu: cada entrada tem que apontar para o mesmo "case" deslocado
ot = struct.unpack('<7I', bytes.fromhex('3023bc003a23bc004423bc004e23bc00bb23bc002824bc00ba24bc00'))
nt = struct.unpack_from('<7I', img, M[0xbc2554])
ds = {n - o for o, n in zip(ot, nt)}
print('== tabela de saltos do menu:', [hex(x) for x in nt], 'deslocamentos', [hex(d) for d in ds])
if len(ds) != 1 or nt[-1] != M[0xbc24ba]: problems.append(('tabela menu', hex(M[0xbc2554]), ['!! entradas não batem']))

print('\n==== PROBLEMAS:', len(problems))
for p in problems: print(p)
if WRITE and not problems:
    for f, t in (('client_1_0_file_signatures.h', sig_new), ('client_1_0_guards.h', gh2), ('menu_visibility_1_0.h', mh2),
                 ('vulkan_startup.h', vh2), ('dllmain.cpp', dm2), ('client_1_0_profile.h', ph2), ('client_1_0_file_layout.h', lh2)):
        open(S(f), 'w', encoding='utf-8', newline='').write(t)
    print('arquivos gravados')
