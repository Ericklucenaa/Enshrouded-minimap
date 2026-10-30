"""Decodificacao dos efeitos ativos (buffs) guardados no bloco 'player_character'.

Ficam logo depois da lista de habilidades (ver character.py):
  u32 qtd_efeitos
  qtd x (u32 hash_efeito, i64 duracao_total_ns, i64 restante_ns, u16 flags, extras conforme flags):
    0x01 -> u8 (aparece no 'Toque da Pata' 1b940242, valor 28)
    0x02 -> u32 hash do item que deu o efeito (comida, pocao, bolsa d'agua)
    0x04 -> f32 (sempre 1.0 nos saves vistos)
    0x08 -> u8  (sempre 7 nos saves vistos)
    0x10 -> 8 bytes desconhecidos
Efeitos conferidos com a tela do jogo: cdbe9c80 Descansado, 1b940242 Toque da Pata; os de
comida/agua/pocao trazem o item (0x02) e sao os circulos do HUD, na ordem do save.
Duracao 0 = efeito permanente. Depois do ultimo efeito vem o marcador e0 ff do equipamento.
O jogo grava o character0.ksd mais ou menos a cada minuto enquanto se joga.
"""
import struct

from core.character import LEVEL_OFF, FormatError

EXTRA_SIZES = ((0x01, 1), (0x02, 4), (0x04, 4), (0x08, 1), (0x10, 8))
KNOWN_FLAGS = 0x1F
NS = 1_000_000_000


class Effect:
    __slots__ = ('hash', 'total', 'left', 'flags', 'item', 'level')

    def to_json(self):
        return {'hash': f'{self.hash:08x}', 'total': self.total, 'left': self.left,
                'item': f'{self.item:08x}' if self.item is not None else None, 'level': self.level}


def effects_start(d: bytes) -> int:
    nsk = struct.unpack_from('<I', d, LEVEL_OFF + 8)[0]
    return LEVEL_OFF + 12 + 5 * nsk


def parse_effects(d: bytes):
    """Lista de Effect com tempos em segundos (float)."""
    p = effects_start(d)
    n = struct.unpack_from('<I', d, p)[0]
    if n > 64:
        raise FormatError(f'{n} efeitos - formato mudou?')
    p += 4
    out = []
    for _ in range(n):
        e = Effect()
        e.hash, total, left, e.flags = struct.unpack_from('<IqqH', d, p)
        p += 22
        if e.flags & ~KNOWN_FLAGS:
            raise FormatError(f'flag de efeito desconhecida {e.flags:#x}')
        e.total, e.left = total / NS, left / NS
        e.item = e.level = None
        for bit, size in EXTRA_SIZES:
            if e.flags & bit:
                if bit == 0x01:
                    e.level = d[p]
                elif bit == 0x02:
                    e.item = struct.unpack_from('<I', d, p)[0]
                p += size
        out.append(e)
    if p > len(d):
        raise FormatError('fim dos dados')
    return out
