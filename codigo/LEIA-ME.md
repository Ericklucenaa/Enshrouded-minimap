# Código

Código das partes feitas para este pacote. Os mods de terceiros (minimapa, Shroudtopia e o desativador de altar do XHL) vêm prontos e estão em [`../instalador/arquivos`](../instalador/arquivos).

| Arquivo | O que é |
|---|---|
| `overlay/painel_minimapa.py` | Painel F8 dentro do jogo. Janela por cima do jogo que não rouba o foco; muda o `shroudtopia.json`, que o minimapa relê na hora. |
| `overlay/atualizador.py` | Atualização automática: confere `releases/latest/download/versao.json`, baixa o .zip, confere o SHA-256 e chama o instalador em modo `-Atualizar`. |
| `core/minimap.py` | Lê, valida e grava as opções do minimapa; troca o visual (moderno/original). |
| `minimap_visual/gerar_visual.py` | Gera a moldura e a seta do visual moderno (`.rgba`, mesmo formato do mod). |
| `instalador_build/publicar.py` | Recompila o `PainelMinimapa.exe` (PyInstaller), monta o pacote, gera o `SHA256SUMS.txt`, o .zip e publica a versão no GitHub. |

O instalador em si é [`../instalador/arquivos/instalador.ps1`](../instalador/arquivos/instalador.ps1) (Windows PowerShell 5.1, aberto pelo `Instalar Minimap.bat`).

## Compilar o painel

```
pip install pyinstaller
python instalador_build/publicar.py 1.2.3 --repo Ericklucenaa/Enshrouded-minimap
```

O `publicar.py` espera a mesma organização de pastas do projeto original (`overlay/`, `core/`, `minimap_visual/` e `instalador_build/pacote/` com o conteúdo de `../instalador`). Adicione `--publicar --notas "..."` para publicar a versão; precisa do `gh` (GitHub CLI) com login.
