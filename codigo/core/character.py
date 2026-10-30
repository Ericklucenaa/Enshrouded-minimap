"""Decodificacao dos blocos 'character_data' e 'player_character'.

player_character (offsets fixos observados em todos os saves):
  0x3A u32 nivel   0x3E u32 xp   0x42 u32 qtd_habilidades
  0x46 qtd x (u32 hash_habilidade, u8 flag)

Itens (equipamento e mochila) usam o mesmo formato de entrada:
  u8 slot, u32 hash_item, u16 quantidade, u8 flags, extras conforme flags:
    0x01 -> u8 (nivel/qualidade)      0x02 -> u32 durab_atual, u32 durab_max
    0x04 -> 8 bytes desconhecidos     0x10 -> u16 desconhecido
    0x20 -> 5 bytes desconhecidos
A lista de equipamento comeca depois do marcador e0 ff 00 00; a mochila vem
logo depois com cabecalho: u8 0x05, u8 qtd_mochila, u8 ?, u8 qtd_extra.
Os itens da mochila vem primeiro e logo em seguida os qtd_extra itens das linhas
extras liberadas pela bolsa equipada (slots contados a partir de 0 de novo).
"""
import struct

KNOWN_FLAGS = 0x01 | 0x02 | 0x04 | 0x10 | 0x20
LEVEL_OFF = 0x3A
EQUIP_MARKER = b'\xe0\xff\x00\x00'


class FormatError(Exception):
    pass


# ---------- character_data ----------

def parse_character_data(data: bytes):
    n = struct.unpack_from('<I', data, 5)[0]
    if n == 0 or n > 64 or 9 + n > len(data):
        raise FormatError('Nome do personagem nao encontrado')
    return {'name': data[9:9 + n].decode('utf-8', 'replace')}


def set_character_name(data: bytes, name: str) -> bytes:
    n = struct.unpack_from('<I', data, 5)[0]
    enc = name.encode('utf-8')
    if not 1 <= len(enc) <= 32:
        raise ValueError('O nome precisa ter entre 1 e 32 bytes')
    return data[:5] + struct.pack('<I', len(enc)) + enc + data[9 + n:]


# ---------- itens ----------

class Item:
    __slots__ = ('slot', 'hash', 'count', 'flags', 'level', 'dur_cur', 'dur_max', 'x4', 'x10', 'x20')

    def to_bytes(self) -> bytes:
        b = struct.pack('<BIHB', self.slot, self.hash, self.count, self.flags)
        if self.flags & 0x01:
            b += struct.pack('<B', self.level)
        if self.flags & 0x02:
            b += struct.pack('<II', self.dur_cur, self.dur_max)
        if self.flags & 0x04:
            b += self.x4
        if self.flags & 0x10:
            b += struct.pack('<H', self.x10)
        if self.flags & 0x20:
            b += self.x20
        return b

    def to_json(self):
        return {'slot': self.slot, 'hash': f'{self.hash:08x}', 'count': self.count, 'flags': self.flags,
                'level': self.level, 'dur_cur': self.dur_cur, 'dur_max': self.dur_max}

    def copy(self):
        c = Item()
        for k in self.__slots__:
            setattr(c, k, getattr(self, k))
        return c


def parse_item(d: bytes, p: int):
    if p + 8 > len(d):
        raise FormatError('fim dos dados')
    it = Item()
    it.slot, it.hash, it.count, it.flags = struct.unpack_from('<BIHB', d, p)
    if it.flags & ~KNOWN_FLAGS:
        raise FormatError(f'flag desconhecida {it.flags:#x}')
    q = p + 8
    it.level = it.dur_cur = it.dur_max = it.x10 = None
    it.x4 = it.x20 = None
    if it.flags & 0x01:
        it.level = d[q]; q += 1
    if it.flags & 0x02:
        it.dur_cur, it.dur_max = struct.unpack_from('<II', d, q); q += 8
    if it.flags & 0x04:
        it.x4 = d[q:q + 8]; q += 8
    if it.flags & 0x10:
        it.x10 = struct.unpack_from('<H', d, q)[0]; q += 2
    if it.flags & 0x20:
        it.x20 = d[q:q + 5]; q += 5
    if q > len(d):
        raise FormatError('fim dos dados')
    return it, q


class PlayerCharacter:
    def __init__(self, data: bytes):
        self.data = bytes(data)
        d = self.data
        self.level, self.xp, nsk = struct.unpack_from('<III', d, LEVEL_OFF)
        if not (0 < self.level <= 1000 and nsk <= 500):
            raise FormatError('Nivel/habilidades fora do esperado')
        p = LEVEL_OFF + 12
        self.skills = []
        for _ in range(nsk):
            h, f = struct.unpack_from('<IB', d, p)
            self.skills.append({'hash': f'{h:08x}', 'flag': f})
            p += 5
        self.skills_end = p
        self.inventory_ok = False
        self.inventory_error = None
        try:
            self._parse_inventory()
            self.inventory_ok = True
        except (FormatError, struct.error) as e:
            self.inventory_error = str(e)

    def _parse_inventory(self):
        # O trecho entre as habilidades e o equipamento (efeitos ativos etc.) muda de tamanho,
        # entao procuramos a posicao em que equipamento + mochila se encaixam exatamente.
        # O marcador e0 ff 00 00 dos saves antigos e so o ponto de partida mais provavel.
        d = self.data
        m = d.find(EQUIP_MARKER, self.skills_end)
        starts = ([m + 4] if m >= 0 else []) + list(range(self.skills_end, len(d) - 8))
        for p in starts:
            res = self._try_inventory(p)
            if res:
                (self.equip_start, self.equipment, self.equip_end, self.bag_hdr,
                 self.backpack, self.extra, self.bag_end) = res
                return
        raise FormatError('lista de equipamento/mochila nao encontrada')

    def _try_inventory(self, p):
        d = self.data
        start = p
        equipment = []
        ends = []  # posicao logo depois de cada item lido
        last = -1
        while True:
            try:
                it, q = parse_item(d, p)
            except (FormatError, struct.error, IndexError):
                break
            if it.slot != last + 1 if not equipment else it.slot <= last:
                break
            if not equipment and it.slot != 0:
                break
            equipment.append(it)
            ends.append(q)
            last = it.slot
            p = q
        # saves mais novos tem alguns bytes desconhecidos antes do cabecalho da mochila (ex.: 07 00,
        # 11 00 0a 00); eles sao preservados como estao. Esses bytes podem parecer mais um item de
        # equipamento, entao testamos do fim mais longo para o mais curto ate a mochila encaixar.
        for k in range(len(equipment), 2, -1):
            equip_end = ends[k - 1]
            for gap in range(0, 9):
                bag = self._try_backpack(equip_end + gap)
                if bag:
                    return (start, equipment[:k], equip_end, equip_end + gap) + bag
        return None

    def _try_backpack(self, p):
        d = self.data
        if p + 4 > len(d) or d[p] != 0x05:
            return None
        n_extra = d[p + 3]
        backpack, p = self._read_list(p + 4, d[p + 1])
        if backpack is None:
            return None
        extra, p = self._read_list(p, n_extra)
        if extra is None:
            return None
        return backpack, extra, p

    def _read_list(self, p, n):
        d = self.data
        items = []
        last = -1
        try:
            for _ in range(n):
                it, p = parse_item(d, p)
                if it.slot <= last:
                    return None, p
                items.append(it)
                last = it.slot
        except (FormatError, struct.error, IndexError):
            return None, p
        return items, p

    # ---- serializacao ----
    def build(self) -> bytes:
        d = bytearray(self.data)
        struct.pack_into('<II', d, LEVEL_OFF, self.level, self.xp)
        if not self.inventory_ok:
            return bytes(d)
        out = bytearray(d[:self.equip_start])
        for it in self.equipment:
            out += it.to_bytes()
        out += d[self.equip_end:self.bag_hdr]
        if len(self.backpack) > 255 or len(self.extra) > 255:
            raise ValueError('Itens demais na mochila')
        hdr = bytearray(d[self.bag_hdr:self.bag_hdr + 4])
        hdr[1] = len(self.backpack)
        hdr[3] = len(self.extra)
        out += hdr
        for it in sorted(self.backpack, key=lambda i: i.slot) + sorted(self.extra, key=lambda i: i.slot):
            out += it.to_bytes()
        out += d[self.bag_end:]
        rebuilt = bytes(out)
        PlayerCharacter(rebuilt)  # precisa voltar a ser legivel
        return rebuilt

    def find(self, where, slot):
        for it in self.items(where):
            if it.slot == slot:
                return it
        raise KeyError(f'slot {slot} nao encontrado')

    def items(self, where):
        return {'equipment': self.equipment, 'backpack': self.backpack, 'extra': self.extra}[where]

    def to_json(self):
        return {
            'level': self.level, 'xp': self.xp, 'skills': self.skills,
            'inventory_ok': self.inventory_ok, 'inventory_error': self.inventory_error,
            'equipment': [i.to_json() for i in self.equipment] if self.inventory_ok else [],
            'backpack': [i.to_json() for i in self.backpack] if self.inventory_ok else [],
            'extra': [i.to_json() for i in self.extra] if self.inventory_ok else [],
        }
