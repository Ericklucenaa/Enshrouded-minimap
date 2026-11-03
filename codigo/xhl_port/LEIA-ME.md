# Desativador remoto de altar (XHL) no build de 02/11/2026

O `XHL-Remote-Altar-Close.dll` é de terceiros e não tem código-fonte publicado. Ele acha as
funções do jogo por padrões de bytes guardados como texto dentro da própria DLL
(ex.: `40 53 48 83 EC 40 45 33 D2`).

`patcount.py <dll> <enshrouded.exe>` lista cada padrão e quantas vezes ele aparece no `.text`
do jogo.

## O que quebrou

Depois da atualização ele parava com:

    action entry init/push functions not found uniquely

O padrão do "push" (`48 83 EC 28 0F B6 81 ?? ?? ?? ?? 4C 8B C1 3C 10`) passou a aparecer
**2 vezes**. O compilador gerou duas cópias idênticas da função, em `0xd6cf30` e `0x1233f50`.
Nenhum padrão no começo da função consegue diferenciar as duas.

## Correção (1 byte)

Em RVA `0x1bb7` da DLL, depois de contar as ocorrências:

    cmp rcx, 1
    jne falha    ; 0F 85 6B 06 00 00   -> exigia exatamente 1
    jb  falha    ; 0F 82 6B 06 00 00   -> agora exige pelo menos 1

O mod usa a primeira ocorrência (menor endereço, `0xd6cf30`), que é a que o construtor da lista
chama. A segurança do mod continua: logo em seguida ele confere se o construtor da lista usa
mesmo essa função (`call 0x3a60`) e, se não usar, desliga sem mexer no jogo.

SHA-256:

- original: o da 1.0.0 do XHL;
- corrigida: `c0abd764e0d2e07cd9e4307579b003af82dc0e3c1bfe8e30a85d6dbdc9f46a33`.

Testado no jogo em 02/11/2026: `1.0.0 ready ... sites +0xC2FB9F +0xC2FE63 +0xD4A71E +0x31A389`.
