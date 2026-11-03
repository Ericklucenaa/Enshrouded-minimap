import json, struct, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP
EXE, MAP = sys.argv[1], sys.argv[2]
pe = pefile.PE(EXE, fast_load=True); img = pe.get_memory_mapped_image()
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
mp = {int(k, 16): int(v[0], 16) for k, v in json.load(open(MAP)).items()}

def calls_to(start, length, target):
    out = []
    for i in md.disasm(img[start:start + length], start):
        if i.mnemonic == 'call' and i.operands and i.operands[0].type == 2 and i.operands[0].imm == target:
            out.append(i.address)
    return out

res = {}
# chamada da amostra de clima: no build antigo 0x2fdd18 chama 0xa9d530, dentro de ambient_effects (0x2fd9a0)
w = calls_to(mp[0x2fd9a0], 0x800, mp[0xa9d530])
print('call clima ->', [hex(x) for x in w], ' previsto', hex(0x2fdd18 + 0x53b0))
# chamada da atualização da névoa: no build antigo 0x3072a4 chama 0x39c430, dentro de fog_of_war (0x3071e0)
f = calls_to(mp[0x3071e0], 0x400, mp[0x39c430])
print('call névoa ->', [hex(x) for x in f], ' previsto', hex(0x3072a4 + 0x53b0))
if len(w) == 1: res['0x2fdd18'] = hex(w[0])
if len(f) == 1: res['0x3072a4'] = hex(f[0])

# constante 0.125f (0x3e000000): referências [rip+x] a esse valor nas funções da névoa
for fn in (0x39ba00, 0x39c430, 0x39c5d0, 0x3071e0):
    n = mp.get(fn)
    if n is None: continue
    for i in md.disasm(img[n:n + 0x600], n):
        for op in i.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                t = i.address + i.size + op.mem.disp
                if 0 <= t < len(img) - 4 and img[t:t + 4] == b'\x00\x00\x00\x3e':
                    print(f'  0.125 em {hex(t)} usado por {hex(i.address)} ({i.mnemonic} {i.op_str}) na função {hex(fn)}->{hex(n)}')
                    res.setdefault('0x13b9edc_cands', []).append(hex(t))
        if i.mnemonic in ('ret', 'int3'): break
json.dump(res, open(MAP.replace('map.json', 'rest.json'), 'w'), indent=1)
