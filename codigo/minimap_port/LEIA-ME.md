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
