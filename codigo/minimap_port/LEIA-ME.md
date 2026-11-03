# Porta do minimapa para builds novos do Enshrouded

O minimapa (Shroudweave Minimap, de Aerox912, baseado no de elxokker) só liga num
`enshrouded.exe` que ele conhece: confere o hash do arquivo e usa uns 70 endereços fixos do jogo.
A cada atualização do jogo ele mostra `unsupported client; no hooks installed` até alguém portar.

Esta pasta tem o que foi usado para portar a 0.5.17 para o build de **02/11/2026**
(`enshrouded.exe` sha256 `0403981f…13f2a6`).

## Como foi feito

Os scripts partem das assinaturas que o próprio mod traz (`src/client_1_0_file_signatures.h`
e os `Match*26082781` de `client_1_0_guards.h`): bytes do build anterior em cada endereço.

1. `scan.py`: mascara os deslocamentos relativos (call/jmp rel32, `[rip+x]`) e procura cada
   trecho no exe novo. Exige exatamente uma ocorrência.
2. `fuzzy.py`: para os trechos curtos ou alterados, prevê a posição pelo deslocamento dos
   vizinhos e procura perto.
3. `diff.py`: mostra instrução por instrução o que mudou num trecho.
4. `mapall.py`: junta o mapa e deduz endereços pelas referências (destinos de call e dados).
5. `named.py`: acha os descritores de sistema pelo nome (`player_camera_transform`, `fog_of_war`…)
   e a tabela do clima.
6. `rest.py`: acha os pontos de chamada do clima e da névoa e a constante 0.125 da névoa.
7. `literals.py`: lista todo endereço fixo no código e confere se está mapeado.
8. `port.py`: gera os arquivos novos. Sem `--write` só confere. Ele compara velho e novo
   instrução por instrução e só aceita diferenças em deslocamentos relativos, em campos
   conhecidos ou em casos revisados à mão. O resto vira "PROBLEMA".
9. `idtest.cpp`: compila com o `client_1_0_profile.h` do mod e diz se o exe é reconhecido.

`final_map.json` é o mapa (endereço no build 26082781 → endereço no build de 02/11).
`minimap-0.5.17-enshrouded-02nov.patch` é a diferença no código do mod.

## O que mudou nesta atualização (02/11/2026)

- **Endereços:** o código andou de +0x4cc0 a +0x19630, e os dados ~+0x1e000.
- **Campo de estrutura:** um campo de uma estrutura de entidades andou 8 bytes
  (`0x828→0x830`, `0x830→0x838`). No `dllmain.cpp`, `ClientOffset(0x7E0,0x828)` virou `0x830`.
- **Revisados à mão:**
  - o `nop` de alinhamento em `primaryRow` ficou 1 byte menor;
  - a tabela de saltos do menu mudou de lugar, com as 7 entradas deslocadas igualmente.

## Pegadinha: `bootDelay` do Shroudtopia

A 0.5.17 só consegue desenhar se estiver carregada **antes** de o jogo criar o Vulkan e o
swapchain, uns 0,3 s depois de abrir. Com a espera padrão do Shroudtopia (`"bootDelay": 3000`),
ela liga e recebe todos os dados, mas o log de decisão mostra `reject=snapshot-unknown`
(`extent=0x0 images=0/0`) e nada aparece.

O instalador agora grava `"bootDelay": 0` no `shroudtopia.json`.

Para diagnosticar casos assim:

- compile com `CL=/DESM_PRESENT_DECISION_TRACE` e ligue `"debug_logging": true` na seção
  `minimap_mod`: as linhas `pd1` mostram em que etapa o desenho desistiu;
- o patch também tem um contador `HUD diag` (só com `debug_logging`) que diz qual condição do
  gancho do HUD falha.

## Compilar

Precisa do Visual Studio 2022 Build Tools (C++):

```
MSBuild minimap_mod.vcxproj /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143
```

## Atualização de 03/11/2026 (hotfix do jogo)

`enshrouded.exe` sha256 `ce6fdba6…2147618`. O mapa atual (`final_map.json`) é 26082781 → 03/11;
o de 02/11 ficou em `final_map_02nov.json`, e o patch do código em `minimap-0.5.17-enshrouded-03nov.patch`.

**Caminho mais rápido para hotfix pequeno:** em vez de refazer tudo a partir das assinaturas,
traduzir o mapa do build anterior para o novo com `compose.py`. Para isso, **guarde uma cópia do
`enshrouded.exe` antes de cada atualização**: a Steam sobrescreve o arquivo.

    py compose.py final_map_02nov.json enshrouded_02nov.exe enshrouded_03nov.exe final_map.json

- código: o mesmo trecho (relativos mascarados) perto da posição antiga;
- dados: as instruções que leem o dado no build antigo, achadas no novo;
- o que sobrar, conferir à mão. Nesta vez foram 21 de 109:
  - funções com só um `call` diferente no começo (`0x2b3340`, `0x3071e0`);
  - tabelas de saltos (`0xbc2554`, `0xc50af8`/`0xc50b00`): todas as entradas −0x20;
  - slot global `0x281e498`: −0x1000, confirmado por 200 referências;
  - descritores de sistema: **use o `named.py`** (pelo nome). As referências `lea` enganam aqui;
  - tabela do clima: o `named.py` também acha.
- `port.py`: atualizar o `MANUAL`/`REVIEWED` do filtro `0xd8f428` (agora `0xda483d`) e rodar.
  Deu 0 problemas, com as mesmas diferenças aceitas de 02/11.
- reaplicar o contador `HUD diag` (está no patch) e compilar.

O que mudou no jogo: o código andou 0 ou −0x20, o `.rdata` e o `.data` −0x1000, e os
descritores de sistema −0xFC0. Nenhum campo de estrutura mudou.

**Pegadinha do auto-update:** o atalho "Jogar Enshrouded (Melhorias)" reinstala a última
*release* publicada. Para testar uma DLL nova antes de publicar, abra o jogo **pela Steam**.

O desativador de altar (XHL, ver `../xhl_port`) não precisou de mudança: a DLL corrigida em
02/11 continua achando tudo no build de 03/11 (`sites +0xC2FB7F +0xC2FE43 +0xD4A6FE +0x31A389`).
