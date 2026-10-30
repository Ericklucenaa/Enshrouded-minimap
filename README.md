# Melhorias Enshrouded

Pacote de melhorias para Enshrouded:

- **Minimapa** no canto da tela com a hora do jogo (sol de dia, lua de noite) e o clima, com visual moderno.
- **Tempo dos buffs**: quanto falta para acabar cada buff de comida, água e poção, dentro do próprio círculo do buff.
- **Painel F8** dentro do jogo, com abas, para mudar todas as opções na hora.
- **Editor de save** que abre no navegador.
- **Desativar Altar de Chama** pelo mapa-múndi.

## Como instalar

1. Feche o Enshrouded.
2. Baixe o **`Melhorias-Enshrouded.zip`** da [versão mais recente](../../releases/latest).
3. **Extraia** o .zip (não rode de dentro dele).
4. Dê dois cliques em **`Instalar Melhorias.bat`**, escolha as opções e clique em **Instalar**.
5. Abra o jogo pelo atalho **"Jogar Enshrouded (Melhorias)"** que aparece na Área de Trabalho.

> Se o Windows mostrar "O Windows protegeu o computador", clique em **Mais informações → Executar assim mesmo**.

## No jogo

| Tecla | O que faz |
|---|---|
| **F8** | Abre e fecha o painel (Tab troca de aba, setas escolhem e mudam, Esc fecha) |
| **F10** | Mostra / esconde o minimapa |
| **+ / -** | Zoom |
| **F9 / F11** | Diminui / aumenta o minimapa |

Todas as teclas podem ser trocadas no painel F8, aba **Teclas**.

## Tempo dos buffs

Mostra quanto falta para acabar cada buff de comida, água e poção, dentro do próprio círculo do buff (canto superior esquerdo). Fica amarelo nos últimos 5 minutos e vermelho no último minuto. Liga e desliga no painel **F8** → aba **Melhorias**.

- O tempo vem do save do personagem, que o jogo grava a cada ~30 s; entre uma gravação e outra a contagem segue em tempo real.
- Descansado e Toque da Pata não entram: o jogo já mostra o tempo deles em texto.
- Precisa do jogo em **Janela sem bordas**. A posição foi medida em 2560×1440 e se ajusta a outras resoluções pela altura da tela.

## Editor de save

Abra pelo atalho **"Editor de Save Enshrouded"** ou pelo painel **F8** → aba **Melhorias** → **Abrir**. Ele abre no navegador e mostra personagem, inventário e backups.

- Só grava com o **jogo fechado** (com o jogo aberto, ele descarta o arquivo editado).
- Sempre faz backup antes de gravar, em `%LOCALAPPDATA%\EnshroudedMinimap\editor\backups`, e restaura pelo próprio editor.
- Fecha sozinho alguns minutos depois que a página do navegador é fechada.

## Desativar Altar de Chama pelo mapa

No mapa-múndi, clique no ícone de um Altar de Chama seu e confirme com um segundo clique para desativá-lo de longe. Reative antes que ele se apague. Vem marcado no instalador (opção "Desativar Altar de Chama pelo mapa-múndi").

## Atualizações

Quem abre o jogo pelo atalho **"Jogar Enshrouded (Melhorias)"** recebe as versões novas sozinho: o atalho confere aqui se há versão nova, baixa, confere a assinatura do arquivo e atualiza antes de abrir o jogo, mantendo as opções de cada um. Quem tinha a versão antiga (atalho "Jogar Enshrouded com Painel") é atualizado do mesmo jeito, e os nomes antigos são trocados sozinhos.

## Desinstalar

Abra o `Instalar Melhorias.bat` de novo e clique em **Desinstalar**. Antes de instalar ou desinstalar, o instalador guarda uma cópia do que já existia em `Documentos\Enshrouded Minimap Backups`.

## Observações

- Só precisa estar no PC de quem joga; o servidor não precisa de nada.
- Precisa do Microsoft Visual C++ x64 (o instalador avisa e dá o link se faltar).
- É um mod não oficial. Depois de uma atualização do Enshrouded ele pode parar de funcionar até sair uma versão nova.

## O que tem neste repositório

- [`instalador/`](instalador) — o pacote completo, igual ao das versões publicadas: minimapa, carregador Shroudtopia, desativador remoto de altar (XHL), o `MelhoriasEnshrouded.exe` (painel F8, tempo dos buffs e editor de save) e o instalador. Também dá para baixar a pasta e rodar o `Instalar Melhorias.bat`.
- [`codigo/`](codigo) — código do painel, do tempo dos buffs, do editor de save, da atualização automática, do visual moderno e do script de publicação.

## Créditos

- **Shroudweave Minimap** — elxokker (original) e Aerox912 — [GitHub](https://github.com/Aerox912/Enshrouded-minimap) · [Nexus](https://www.nexusmods.com/enshrouded/mods/143)
- **Shroudtopia** — s0t7x / Miguel Oppermann (original), versão de compatibilidade Shroudweave
- **XHL Remote Altar Close** — XHL — [Nexus](https://www.nexusmods.com/enshrouded/mods/180)
- Visual moderno, painel F8, tempo dos buffs, editor de save, instalador e atualização automática feitos para este pacote.

Os mods incluídos são distribuídos sob a licença MIT; as licenças estão na pasta `arquivos\licencas` do instalador. Enshrouded é marca da Keen Games; este é um projeto independente da comunidade.
