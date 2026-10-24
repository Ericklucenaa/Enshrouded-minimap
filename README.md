# Minimapa e Relógio para Enshrouded

Minimapa no canto da tela com a hora do jogo (sol de dia, lua de noite) e o clima, com visual moderno e um painel dentro do jogo para mudar as opções.

## Como instalar

1. Feche o Enshrouded.
2. Baixe o **`Instalador-Minimap-Enshrouded.zip`** da [versão mais recente](../../releases/latest).
3. **Extraia** o .zip (não rode de dentro dele).
4. Dê dois cliques em **`Instalar Minimap.bat`**, escolha as opções e clique em **Instalar**.
5. Abra o jogo pelo atalho **"Jogar Enshrouded com Painel"** que aparece na Área de Trabalho.

> Se o Windows mostrar "O Windows protegeu o computador", clique em **Mais informações → Executar assim mesmo**.

## No jogo

| Tecla | O que faz |
|---|---|
| **F8** | Abre e fecha o painel do minimapa (setas para escolher e mudar, Esc fecha) |
| **F10** | Mostra / esconde o minimapa |
| **+ / -** | Zoom |
| **F9 / F11** | Diminui / aumenta o minimapa |

## Desativar Altar de Chama pelo mapa

No mapa-múndi, clique no ícone de um Altar de Chama seu e confirme com um segundo clique para desativá-lo de longe. Reative antes que ele se apague. Vem marcado no instalador (opção "Desativar Altar de Chama pelo mapa-múndi").

## Atualizações

Quem abre o jogo pelo atalho **"Jogar Enshrouded com Painel"** recebe as versões novas sozinho: o atalho confere aqui se há versão nova, baixa, confere a assinatura do arquivo e atualiza antes de abrir o jogo, mantendo as opções de cada um.

## Desinstalar

Abra o `Instalar Minimap.bat` de novo e clique em **Desinstalar**. Antes de instalar ou desinstalar, o instalador guarda uma cópia do que já existia em `Documentos\Enshrouded Minimap Backups`.

## Observações

- Só precisa estar no PC de quem joga; o servidor não precisa de nada.
- Precisa do Microsoft Visual C++ x64 (o instalador avisa e dá o link se faltar).
- É um mod não oficial. Depois de uma atualização do Enshrouded ele pode parar de funcionar até sair uma versão nova.

## O que tem neste repositório

- [`instalador/`](instalador) — o pacote completo, igual ao das versões publicadas: minimapa, carregador Shroudtopia, desativador remoto de altar (XHL), painel F8 e o instalador. Também dá para baixar a pasta e rodar o `Instalar Minimap.bat`.
- [`codigo/`](codigo) — código do painel F8, da atualização automática, do visual moderno, do instalador e do script de publicação.

## Créditos

- **Shroudweave Minimap** — elxokker (original) e Aerox912 — [GitHub](https://github.com/Aerox912/Enshrouded-minimap) · [Nexus](https://www.nexusmods.com/enshrouded/mods/143)
- **Shroudtopia** — s0t7x / Miguel Oppermann (original), versão de compatibilidade Shroudweave
- **XHL Remote Altar Close** — XHL — [Nexus](https://www.nexusmods.com/enshrouded/mods/180)
- Visual moderno, painel F8, instalador e atualização automática feitos para este pacote.

Os mods incluídos são distribuídos sob a licença MIT; as licenças estão na pasta `arquivos\licencas` do instalador. Enshrouded é marca da Keen Games; este é um projeto independente da comunidade.
