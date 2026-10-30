"""Leitura e escrita do container de save do Enshrouded (.ksd / SV2C).

Layout descoberto por engenharia reversa:
  0x00  'SV2C'  u16 versao  u16 tamanho_cabecalho(0x30)
  0x08  u32 tamanho_total_do_arquivo
  0x0C  16 bytes GUID do save
  0x1C  u32 contador de saves   0x20 u32 timestamp unix   0x24 u32 0
  0x28  u32 offset_do_indice - 0x28   0x2C u32 numero_de_blocos
  0x30  blocos 'S2BH' em sequencia:
          'S2BH' u32 versao  u8 tipo  u8 compactado(1=zstd)  u32 ?  payload
  ...   padding com zeros ate alinhar em 16
  indice: N x (u32 off_nome_relativo, u32 len_nome, u32 offset, u32 tamanho, u32 xxh3_64(bloco) & 0xffffffff)
  tabela de strings com os nomes dos blocos
"""
import struct

import xxhash
import zstandard

HEADER_SIZE = 0x30
BLOCK_HDR = 14


def block_hash(raw: bytes) -> int:
    return xxhash.xxh3_64(raw).intdigest() & 0xFFFFFFFF


class Block:
    def __init__(self, name, raw, entry_name_off, entry_name_len):
        self.name = name
        self.hdr = raw[:BLOCK_HDR]
        self.type = raw[8]
        self.compressed = raw[9] == 1
        self._raw = raw
        self._name_off = entry_name_off
        self._name_len = entry_name_len
        payload = raw[BLOCK_HDR:]
        if self.compressed:
            self.data = zstandard.ZstdDecompressor().decompressobj().decompress(payload)
        else:
            self.data = bytes(payload)
        self.dirty = False

    def set_data(self, data: bytes):
        self.data = bytes(data)
        self.dirty = True

    def raw(self) -> bytes:
        if not self.dirty:
            return self._raw
        if self.compressed:
            cctx = zstandard.ZstdCompressor(level=9, write_checksum=False, write_content_size=True)
            payload = cctx.compress(self.data)
        else:
            payload = self.data
        return self.hdr + payload


class SaveFile:
    def __init__(self, data: bytes):
        if data[:4] != b'SV2C':
            raise ValueError('Arquivo nao e um save SV2C do Enshrouded')
        self.header = bytearray(data[:HEADER_SIZE])
        idx = struct.unpack_from('<I', data, 0x28)[0] + 0x28
        count = struct.unpack_from('<I', data, 0x2C)[0]
        self.strings = data[idx + 20 * count:]
        self.blocks = []
        for k in range(count):
            eo = idx + 20 * k
            name_off, name_len, off, size, h = struct.unpack_from('<IIIII', data, eo)
            name = data[eo + name_off:eo + name_off + name_len].decode('utf-8', 'replace')
            raw = data[off:off + size]
            if raw[:4] != b'S2BH':
                raise ValueError(f'Bloco {name} corrompido (sem S2BH)')
            if block_hash(raw) != h:
                raise ValueError(f'Hash do bloco {name} nao confere - arquivo corrompido?')
            self.blocks.append(Block(name, raw, name_off, name_len))

    @classmethod
    def load(cls, path):
        with open(path, 'rb') as f:
            return cls(f.read())

    @property
    def dirty(self):
        return any(b.dirty for b in self.blocks)

    def block(self, name) -> Block:
        for b in self.blocks:
            if b.name == name:
                return b
        raise KeyError(name)

    def build(self) -> bytes:
        out = bytearray(self.header)
        entries = []
        for b in self.blocks:
            raw = b.raw()
            entries.append((len(out), len(raw), block_hash(raw)))
            out += raw
        out += b'\0' * (-len(out) % 16)
        idx = len(out)
        for k, b in enumerate(self.blocks):
            off, size, h = entries[k]
            # a tabela de strings fica logo apos o indice, entao os offsets relativos de nome nao mudam
            out += struct.pack('<IIIII', b._name_off, b._name_len, off, size, h)
        out += self.strings
        struct.pack_into('<I', out, 0x08, len(out))
        struct.pack_into('<I', out, 0x28, idx - 0x28)
        struct.pack_into('<I', out, 0x2C, len(self.blocks))
        result = bytes(out)
        # valida: precisa reabrir e trazer exatamente os mesmos dados
        check = SaveFile(result)
        for a, c in zip(self.blocks, check.blocks):
            if a.name != c.name or a.data != c.data:
                raise RuntimeError(f'Falha de verificacao ao reconstruir o bloco {a.name}')
        return result

    def info(self):
        return {
            'guid': bytes(self.header[0x0C:0x1C]).hex(),
            'save_counter': struct.unpack_from('<I', self.header, 0x1C)[0],
            'timestamp': struct.unpack_from('<I', self.header, 0x20)[0],
            'blocks': [{'name': b.name, 'type': b.type, 'compressed': b.compressed,
                        'size': len(b.data), 'dirty': b.dirty} for b in self.blocks],
        }
