# Código

Código das partes feitas para o Melhorias Enshrouded. Os mods de terceiros (minimapa, Shroudtopia e o desativador de altar do XHL) vêm prontos e estão em [`../instalador/arquivos`](../instalador/arquivos).

Tudo vira um programa só, o `MelhoriasEnshrouded.exe`: sem argumentos (ou com `--abrir-jogo`) é o painel F8 com o tempo dos buffs; com `--editor` é o editor de save.

| Arquivo | O que é |
|---|---|
| `overlay/painel_minimapa.py` | Painel F8 dentro do jogo, com abas (Tab troca). Janela por cima do jogo que não rouba o foco; muda o `shroudtopia.json`, que o minimapa relê na hora. Ponto de entrada do .exe. |
| `overlay/buffs.py` | Tempo restante dentro dos círculos de buff. Roda como janela do painel F8 (ou sozinho com `python overlay/buffs.py`). |
| `server.py`, `static/index.html` | Editor de save: servidor local em `127.0.0.1:8765` e a página. No .exe, backups e cache ficam em `%LOCALAPPDATA%\EnshroudedMinimap\editor`. |
| `core/efeitos.py` | Lê os efeitos ativos (buffs) do bloco `player_character` do save: duração total e restante em nanossegundos e o item que deu o efeito. |
| `core/ksd.py`, `core/character.py` | Leitura e gravação do container de save `.ksd` (SV2C, blocos zstd) e do bloco do personagem. |
| `data/game_db.json`, `gerar_banco.py` | Nomes dos itens e habilidades (gerado a partir dos arquivos do jogo com o kfc-parser). |
| `overlay/atualizador.py` | Atualização automática: confere `releases/latest/download/versao.json`, baixa o .zip, confere o SHA-256 e chama o instalador em modo `-Atualizar`. |
| `core/minimap.py` | Lê, valida e grava as opções do minimapa; troca o visual (moderno/original). |
| `minimap_visual/gerar_visual.py` | Gera a moldura e a seta do visual moderno (`.rgba`, mesmo formato do mod). |
| `instalador_build/publicar.py` | Recompila o `MelhoriasEnshrouded.exe` (PyInstaller), monta o pacote, gera o `SHA256SUMS.txt`, o .zip e publica a versão no GitHub. |

O instalador em si é [`../instalador/arquivos/instalador.ps1`](../instalador/arquivos/instalador.ps1) (Windows PowerShell 5.1, aberto pelo `Instalar Melhorias.bat`).

## Compilar

```
pip install pyinstaller xxhash zstandard
python instalador_build/publicar.py 1.2.3 --repo Ericklucenaa/Enshrouded-minimap
```

O `publicar.py` espera a mesma organização de pastas do projeto original (`overlay/`, `core/`, `static/`, `data/`, `minimap_visual/` e `instalador_build/pacote/Melhorias Enshrouded/` com o conteúdo de `../instalador`). Adicione `--publicar --notas "..."` para publicar a versão; precisa do `gh` (GitHub CLI) com login.
