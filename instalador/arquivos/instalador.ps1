# Instalador do Melhorias Enshrouded: Shroudweave Minimap 0.5.15 + Shroudtopia 0.2.1, painel F8,
# tempo dos buffs, editor de save e desativador remoto de altar (XHL).
# Compatível com Windows PowerShell 5.1 (já vem no Windows 10/11). Aberto pelo "Instalar Melhorias.bat".
# -Atualizar: modo silencioso chamado pelo painel (.exe) quando há versão nova no GitHub.
param([switch]$Atualizar)

$ErrorActionPreference = 'Stop'
$PKG = $PSScriptRoot
$APP_NAME = 'Melhorias Enshrouded'
$MOD_ID = 'minimap_mod'
$DLLS = @('winmm.dll', 'shroudtopia.dll')
$BACKUP_ROOT = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Enshrouded Minimap Backups'
$LOCAL_DIR = Join-Path $env:LOCALAPPDATA 'EnshroudedMinimap'   # painel, versão instalada e opções escolhidas
$PANEL_NAMES = @('MelhoriasEnshrouded', 'PainelMinimapa')     # nome atual e o de antes da 1.4.0
$PANEL_EXE = Join-Path $LOCAL_DIR 'MelhoriasEnshrouded.exe'
$DESKTOP = [Environment]::GetFolderPath('Desktop')
$SHORTCUT = Join-Path $DESKTOP 'Jogar Enshrouded (Melhorias).lnk'
$EDITOR_SHORTCUT = Join-Path $DESKTOP 'Editor de Save Enshrouded.lnk'
$OLD_FILES = @((Join-Path $LOCAL_DIR 'PainelMinimapa.exe'), (Join-Path $DESKTOP 'Jogar Enshrouded com Painel.lnk'))
$VISUAL_FILES = @('embervale_minimap_frame.rgba', 'embervale_player_arrow.rgba')
$VISUALS = [ordered]@{ 'Moderno (recomendado)' = 'moderno'; 'Original (bronze)' = 'original' }
$ALTAR_DIR = 'XHL-Remote-Altar-Close'      # desativador remoto de altar (XHL), carregado pelo dinput8.dll do XHL
$CHAIN_INI = 'dinput8-chain.ini'           # lista de DLLs extras que o carregador do XHL abre junto
$PREV_DINPUT = 'dinput8-anterior.dll'      # dinput8.dll de outro mod que existia antes (continua carregado)

$POSITIONS = [ordered]@{
    'Embaixo à direita' = 'bottom-right'; 'No meio à direita' = 'middle-right'; 'Em cima à direita' = 'top-right'
    'Embaixo à esquerda' = 'bottom-left'; 'No meio à esquerda' = 'middle-left'; 'Em cima à esquerda' = 'top-left'
}
$ORIENTATIONS = [ordered]@{ 'Norte sempre para cima' = 'north-up'; 'Gira junto com o personagem' = 'rotating' }
$STYLES = [ordered]@{ 'Colorido (recomendado)' = 'default'; 'Cores originais do jogo' = 'original' }

# ---------------- funções (sem interface) ----------------

function Get-Sha256($path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLower() }

function Find-GameFolders {
    $steam = @('C:\Program Files (x86)\Steam', 'C:\Program Files\Steam')  # primeiro, pela grafia bonita
    foreach ($k in 'HKCU:\Software\Valve\Steam', 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam', 'HKLM:\SOFTWARE\Valve\Steam') {
        $p = Get-ItemProperty $k -ErrorAction SilentlyContinue
        if ($p.SteamPath) { $steam += ($p.SteamPath -replace '/', '\') }
        if ($p.InstallPath) { $steam += $p.InstallPath }
    }
    $libs = @()
    foreach ($s in ($steam | Select-Object -Unique)) {
        $libs += $s
        $vdf = Join-Path $s 'steamapps\libraryfolders.vdf'
        if (Test-Path -LiteralPath $vdf) {
            $libs += [regex]::Matches((Get-Content -LiteralPath $vdf -Raw), '"path"\s+"([^"]+)"') |
                ForEach-Object { $_.Groups[1].Value -replace '\\\\', '\' }
        }
    }
    foreach ($d in [IO.DriveInfo]::GetDrives() | Where-Object { $_.DriveType -eq 'Fixed' }) {
        $libs += (Join-Path $d.Name 'SteamLibrary')
    }
    $seen = @{}
    foreach ($lib in $libs) {
        $g = Join-Path $lib 'steamapps\common\Enshrouded'
        if (-not (Test-Path -LiteralPath (Join-Path $g 'enshrouded.exe'))) { continue }
        $g = (Get-Item -LiteralPath $g).FullName.TrimEnd('\')
        if (-not $seen.ContainsKey($g.ToLower())) { $seen[$g.ToLower()] = $true; $g }  # o registro da Steam usa minusculas
    }
}

function Test-GameRunning($game) {
    $exe = (Join-Path $game 'enshrouded.exe').ToLower()
    foreach ($p in Get-Process enshrouded -ErrorAction SilentlyContinue) {
        try { if ($p.Path -and $p.Path.ToLower() -eq $exe) { return $true } } catch { return $true }
    }
    return $false
}

function Test-VcRedist {
    foreach ($k in 'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64',
                   'HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64') {
        $p = Get-ItemProperty $k -ErrorAction SilentlyContinue
        if ($p -and $p.Installed -eq 1) { return $true }
    }
    return $false
}

function Test-Writable($dir) {
    $probe = Join-Path $dir ('.minimap-teste-' + [guid]::NewGuid().ToString('N'))
    try { [IO.File]::WriteAllText($probe, 'ok'); Remove-Item -LiteralPath $probe -Force; return $true } catch { return $false }
}

function Test-Package {
    # confere se nenhum arquivo do pacote foi corrompido ou trocado
    $bad = @()
    foreach ($line in Get-Content -LiteralPath (Join-Path $PKG 'SHA256SUMS.txt')) {
        if ($line -notmatch '^([0-9a-f]{64})\s+\*?(.+)$') { continue }
        $f = Join-Path $PKG ($Matches[2] -replace '/', '\')
        if (-not (Test-Path -LiteralPath $f) -or (Get-Sha256 $f) -ne $Matches[1]) { $bad += $Matches[2] }
    }
    return , $bad
}

function Read-Config($game) {
    $path = Join-Path $game 'shroudtopia.json'
    if (Test-Path -LiteralPath $path) { return (Get-Content -LiteralPath $path -Raw | ConvertFrom-Json) }
    return $null
}

function Write-Config($game, $cfg) {
    $json = $cfg | ConvertTo-Json -Depth 20
    [IO.File]::WriteAllText((Join-Path $game 'shroudtopia.json'), $json, (New-Object Text.UTF8Encoding $false))
}

function Backup-Existing($game, $log) {
    $items = @($DLLS + 'shroudtopia.json' + 'dinput8.dll' + $CHAIN_INI + $PREV_DINPUT |
        ForEach-Object { Join-Path $game $_ } | Where-Object { Test-Path -LiteralPath $_ })
    foreach ($m in $MOD_ID, $ALTAR_DIR) {
        $modDir = Join-Path $game "mods\$m"
        if (Test-Path -LiteralPath $modDir) { $items += $modDir }
    }
    if (-not $items) { & $log 'Nenhum arquivo anterior para guardar.'; return $null }
    $stamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
    $dest = Join-Path $BACKUP_ROOT $stamp
    $n = 2
    while (Test-Path -LiteralPath $dest) { $dest = Join-Path $BACKUP_ROOT "$stamp ($n)"; $n++ }
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    foreach ($i in $items) { Copy-Item -LiteralPath $i -Destination $dest -Recurse -Force }
    & $log "Backup do que já existia: $dest"
    return $dest
}

function Install-Minimap($game, $opts, $log) {
    Backup-Existing $game $log | Out-Null
    foreach ($d in $DLLS) { Copy-Item -LiteralPath (Join-Path $PKG "shroudtopia\$d") -Destination $game -Force }
    & $log 'Carregador Shroudtopia copiado (winmm.dll e shroudtopia.dll).'

    $mods = Join-Path $game 'mods'
    $modDir = Join-Path $mods $MOD_ID
    if (Test-Path -LiteralPath $modDir) { Remove-Item -LiteralPath $modDir -Recurse -Force }  # o mod pede só uma cópia
    New-Item -ItemType Directory -Force -Path $mods | Out-Null
    Copy-Item -LiteralPath (Join-Path $PKG $MOD_ID) -Destination $mods -Recurse -Force
    & $log "Minimapa copiado para $modDir"

    if ($null -eq $opts) {  # atualização automática: mantém tudo o que a pessoa configurou
        & $log 'Configurações do minimapa mantidas.'
        return
    }
    $cfg = Read-Config $game
    if (-not $cfg) {
        $cfg = Get-Content -LiteralPath (Join-Path $PKG 'shroudtopia\shroudtopia.default.json') -Raw | ConvertFrom-Json
        & $log 'shroudtopia.json criado.'
    } else {
        & $log 'shroudtopia.json existente mantido; só a parte do minimapa foi atualizada.'
    }
    if (-not $cfg.mods) { $cfg | Add-Member -NotePropertyName mods -NotePropertyValue ([pscustomobject]@{}) -Force }
    $entry = $cfg.mods.$MOD_ID
    if (-not $entry) { $entry = [pscustomobject]@{} }
    $values = [ordered]@{ active = $true; position = $opts.position; offset = 0; map_orientation = $opts.orientation
                          map_style = $opts.style; show_clock = $opts.clock; show_weather = $opts.weather
                          show_fog_of_war = $opts.fog }
    foreach ($k in $values.Keys) {
        if ($k -eq 'offset' -and $entry.PSObject.Properties[$k]) { continue }  # preserva ajuste fino feito à mão
        $entry | Add-Member -NotePropertyName $k -NotePropertyValue $values[$k] -Force
    }
    $cfg.mods | Add-Member -NotePropertyName $MOD_ID -NotePropertyValue $entry -Force
    Write-Config $game $cfg
    & $log 'Configuração salva.'
}

function Set-Visual($game, $kind, $log) {
    if ($kind -ne 'moderno') { & $log 'Visual original (bronze).'; return }
    foreach ($f in $VISUAL_FILES) {
        Copy-Item -LiteralPath (Join-Path $PKG "visual_moderno\$f") -Destination (Join-Path $game "mods\$MOD_ID") -Force
    }
    & $log 'Visual moderno aplicado (moldura e seta).'
}

function Deploy-Cores($log) {
    # leva as cores da moldura para %LOCALAPPDATA%\EnshroudedMinimap\cores (o painel F8 troca entre elas)
    $src = Join-Path $PKG 'cores'
    if (-not (Test-Path -LiteralPath $src)) { return }
    $dst = Join-Path $LOCAL_DIR 'cores'
    if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Recurse -Force }
    Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force
}

function Apply-Color($game, $color, $log) {
    # aplica a cor escolhida (moldura + seta). Sem cores/ ou sem cor, fica o padrao que o Set-Visual ja copiou.
    if (-not $color) { return }
    $src = Join-Path $LOCAL_DIR "cores\$color"
    if (-not (Test-Path -LiteralPath $src)) { return }
    foreach ($f in $VISUAL_FILES) {
        $sf = Join-Path $src $f
        if (Test-Path -LiteralPath $sf) { Copy-Item -LiteralPath $sf -Destination (Join-Path $game "mods\$MOD_ID") -Force }
    }
    & $log "Cor da moldura: $color."
}

function Stop-Panel {
    $p = @(Get-Process $PANEL_NAMES -ErrorAction SilentlyContinue)
    $p | Stop-Process -Force -ErrorAction SilentlyContinue
    $p | Wait-Process -Timeout 10 -ErrorAction SilentlyContinue
}

function Copy-WithRetry($src, $dst) {
    # logo depois de fechar o painel o Windows (ou o antivirus) ainda pode estar segurando o .exe
    for ($i = 1; ; $i++) {
        try { Copy-Item -LiteralPath $src -Destination $dst -Force -ErrorAction Stop; return }
        catch { if ($i -ge 40) { throw }; Start-Sleep -Milliseconds 500 }
    }
}

function Read-LocalOptions {
    try { return (Get-Content -LiteralPath (Join-Path $LOCAL_DIR 'opcoes.json') -Raw | ConvertFrom-Json) } catch { return $null }
}

function Save-LocalInfo($game, $visual, $painel, $altar, $color, $buffs, $editor) {
    New-Item -ItemType Directory -Force -Path $LOCAL_DIR | Out-Null
    Copy-Item -LiteralPath (Join-Path $PKG 'versao.json') -Destination (Join-Path $LOCAL_DIR 'versao.json') -Force
    # mantém o que o painel grava sozinho (tecla do painel etc.) e atualiza o resto
    $o = [ordered]@{}
    $old = Read-LocalOptions
    if ($old) { foreach ($p in $old.PSObject.Properties) { $o[$p.Name] = $p.Value } }
    $new = [ordered]@{ game_dir = $game; visual = $visual; painel = [bool]$painel; altar = [bool]$altar; color = $color
                       buffs = [bool]$buffs; editor = [bool]$editor }
    foreach ($k in $new.Keys) { $o[$k] = $new[$k] }
    [IO.File]::WriteAllText((Join-Path $LOCAL_DIR 'opcoes.json'), ($o | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
}

function New-Shortcut($path, $arguments, $desc, $icon) {
    $sh = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
    $sh.TargetPath = $PANEL_EXE
    $sh.Arguments = $arguments
    $sh.WorkingDirectory = $LOCAL_DIR
    $sh.Description = $desc
    $sh.IconLocation = $icon
    $sh.Save()
}

function Remove-OldNames($log) {
    # até a 1.3.0 o programa se chamava PainelMinimapa.exe e o atalho "Jogar Enshrouded com Painel"
    $had = $false
    foreach ($p in $OLD_FILES) { if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force; $had = $true } }
    if ($had) { & $log 'Nomes antigos (PainelMinimapa) removidos.' }
}

function Install-Panel($game, $editor, $log) {
    Stop-Panel
    New-Item -ItemType Directory -Force -Path $LOCAL_DIR | Out-Null
    Copy-WithRetry (Join-Path $PKG 'painel\MelhoriasEnshrouded.exe') $PANEL_EXE
    Remove-OldNames $log
    Deploy-Cores $log
    New-Shortcut $SHORTCUT '--abrir-jogo' "Abre o Enshrouded com o $APP_NAME (painel F8, tempo dos buffs) e mantém tudo atualizado" `
        ((Join-Path $game 'enshrouded.exe') + ',0')
    & $log 'Painel F8 instalado e atalho "Jogar Enshrouded (Melhorias)" criado na Área de Trabalho.'
    if ($editor) {
        New-Shortcut $EDITOR_SHORTCUT '--editor' 'Editor de save do Enshrouded (abre no navegador)' "$PANEL_EXE,0"
        & $log 'Atalho "Editor de Save Enshrouded" criado na Área de Trabalho.'
    } elseif (Test-Path -LiteralPath $EDITOR_SHORTCUT) {
        Remove-Item -LiteralPath $EDITOR_SHORTCUT -Force
        & $log 'Atalho do editor de save removido.'
    }
}

function Remove-Panel($log) {
    Stop-Panel
    $had = $false
    foreach ($p in @($PANEL_EXE, $SHORTCUT, $EDITOR_SHORTCUT) + $OLD_FILES) {
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force; $had = $true }
    }
    if ($had) { & $log 'Painel F8 e atalhos removidos.' }
}

function Test-IsXhlCore($path) {
    # o carregador do XHL muda de versao; reconhece pelo nome interno em vez do hash
    $bytes = [IO.File]::ReadAllBytes($path)
    return [Text.Encoding]::ASCII.GetString($bytes).Contains('XHL-Native-Host')
}

function Get-ChainEntries($game) {
    $ini = Join-Path $game $CHAIN_INI
    if (-not (Test-Path -LiteralPath $ini)) { return @() }
    return @(Get-Content -LiteralPath $ini | ForEach-Object { $_.Trim() } | Where-Object { $_ -and $_ -notmatch '^[\[;#]' })
}

function Set-ChainEntries($game, $entries) {
    $ini = Join-Path $game $CHAIN_INI
    if (-not $entries) { if (Test-Path -LiteralPath $ini) { Remove-Item -LiteralPath $ini -Force }; return }
    [IO.File]::WriteAllText($ini, "[Chain]`r`n" + (($entries | Select-Object -Unique) -join "`r`n") + "`r`n", (New-Object Text.UTF8Encoding $false))
}

function Install-Altar($game, $log) {
    $ours = Join-Path $PKG 'xhl\dinput8.dll'
    $dst = Join-Path $game 'dinput8.dll'
    if ((Test-Path -LiteralPath $dst) -and -not (Test-IsXhlCore $dst)) {
        # outro mod usa o nome dinput8.dll: guarda com outro nome e o carregador do XHL abre os dois
        Copy-Item -LiteralPath $dst -Destination (Join-Path $game $PREV_DINPUT) -Force
        Set-ChainEntries $game (@(Get-ChainEntries $game) + $PREV_DINPUT)
        & $log "O dinput8.dll de outro mod foi renomeado para $PREV_DINPUT e continua sendo carregado."
    }
    Copy-Item -LiteralPath $ours -Destination $dst -Force
    $mods = Join-Path $game 'mods'
    New-Item -ItemType Directory -Force -Path $mods | Out-Null
    $d = Join-Path $mods $ALTAR_DIR
    if (Test-Path -LiteralPath $d) { Remove-Item -LiteralPath $d -Recurse -Force }
    Copy-Item -LiteralPath (Join-Path $PKG "xhl\$ALTAR_DIR") -Destination $mods -Recurse -Force
    & $log 'Desativador remoto de altar instalado (no mapa-múndi: clique no altar e confirme).'
}

function Remove-Altar($game, $log) {
    $d = Join-Path $game "mods\$ALTAR_DIR"
    $had = Test-Path -LiteralPath $d
    if ($had) { Remove-Item -LiteralPath $d -Recurse -Force }
    # outros mods do XHL (native-plugin.ini) ainda precisam do carregador
    $others = @(Get-ChildItem -LiteralPath (Join-Path $game 'mods') -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'native-plugin.ini') })
    $dll = Join-Path $game 'dinput8.dll'
    if (-not $others -and (Test-Path -LiteralPath $dll) -and (Test-IsXhlCore $dll)) {
        Remove-Item -LiteralPath $dll -Force
        $prev = Join-Path $game $PREV_DINPUT
        if (Test-Path -LiteralPath $prev) {
            Move-Item -LiteralPath $prev -Destination $dll -Force   # devolve o dinput8.dll do outro mod
            Set-ChainEntries $game @(Get-ChainEntries $game | Where-Object { $_ -ne $PREV_DINPUT })
            & $log 'O dinput8.dll do outro mod voltou ao nome original.'
        }
    }
    if ($had) { & $log 'Desativador remoto de altar removido.' }
}

function Uninstall-Minimap($game, $log) {
    Backup-Existing $game $log | Out-Null
    Remove-Panel $log
    Remove-Altar $game $log
    if (Test-Path -LiteralPath $LOCAL_DIR) { Remove-Item -LiteralPath $LOCAL_DIR -Recurse -Force }
    $modDir = Join-Path $game "mods\$MOD_ID"
    if (Test-Path -LiteralPath $modDir) { Remove-Item -LiteralPath $modDir -Recurse -Force; & $log 'Pasta do minimapa removida.' }
    $mods = Join-Path $game 'mods'
    if ((Test-Path -LiteralPath $mods) -and -not (Get-ChildItem -LiteralPath $mods -Force)) { Remove-Item -LiteralPath $mods -Force }

    $cfg = Read-Config $game
    $others = @()
    if ($cfg -and $cfg.mods) {
        $cfg.mods.PSObject.Properties.Remove($MOD_ID)
        $others = @($cfg.mods.PSObject.Properties | ForEach-Object { $_.Name })  # .Properties.Name daria @($null) com 0 itens
    }
    if ($others.Count -gt 0) {
        Write-Config $game $cfg
        & $log ("Outros mods continuam instalados (" + ($others -join ', ') + "); o Shroudtopia foi mantido.")
        return
    }
    $json = Join-Path $game 'shroudtopia.json'
    if (Test-Path -LiteralPath $json) { Remove-Item -LiteralPath $json -Force }
    foreach ($d in $DLLS) {
        $f = Join-Path $game $d
        if (-not (Test-Path -LiteralPath $f)) { continue }
        if ((Get-Sha256 $f) -eq (Get-Sha256 (Join-Path $PKG "shroudtopia\$d"))) {
            Remove-Item -LiteralPath $f -Force; & $log "$d removido."
        } else {
            & $log "$d não é o deste pacote (pode ser de outro mod); deixei como estava."
        }
    }
}

if ($env:MINIMAP_INSTALLER_NOGUI) { return }  # usado nos testes: carrega só as funções

if ($Atualizar) {
    $logFile = Join-Path $LOCAL_DIR 'atualizacao.log'
    $log = { param($m) Add-Content -LiteralPath $logFile -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss ') + $m) -Encoding UTF8 }
    try {
        $o = Get-Content -LiteralPath (Join-Path $LOCAL_DIR 'opcoes.json') -Raw | ConvertFrom-Json
        $game = $o.game_dir
        for ($i = 0; $i -lt 40 -and (Get-Process $PANEL_NAMES -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Milliseconds 500 }
        if (Test-GameRunning $game) { throw 'o jogo está aberto; tento de novo na próxima vez' }
        $bad = Test-Package
        if ($bad.Count) { throw ('pacote corrompido: ' + ($bad -join ', ')) }
        # quem instalou antes de uma opção existir (sem ela salva) recebe a novidade ligada
        $altar = if ($null -eq $o.altar) { $true } else { [bool]$o.altar }
        $buffs = if ($null -eq $o.buffs) { $true } else { [bool]$o.buffs }
        $editor = if ($null -eq $o.editor) { $true } else { [bool]$o.editor }
        Install-Minimap $game $null $log
        Set-Visual $game $o.visual $log
        if ($o.painel) { Install-Panel $game $editor $log }
        $color = if ($o.color) { $o.color } else { 'ambar' }
        Apply-Color $game $color $log
        if ($altar) { Install-Altar $game $log } else { Remove-Altar $game $log }
        Save-LocalInfo $game $o.visual $o.painel $altar $color $buffs $editor
        & $log ('Atualizado para a versão ' + (Get-Content -LiteralPath (Join-Path $PKG 'versao.json') -Raw | ConvertFrom-Json).versao)
    } catch {
        & $log ('ERRO na atualização: ' + $_.Exception.Message)
    }
    # --sem-atualizar: se algo falhou, não tenta de novo agora (evita ficar em ciclo); só abre o jogo.
    # O WMI cria o painel fora do 'job' do .exe antigo; com Start-Process ele seria fechado junto.
    if (Test-Path -LiteralPath $PANEL_EXE) {
        try {
            Invoke-CimMethod -ClassName Win32_Process -MethodName Create -ErrorAction Stop `
                -Arguments @{ CommandLine = "`"$PANEL_EXE`" --abrir-jogo --sem-atualizar"; CurrentDirectory = $LOCAL_DIR } | Out-Null
        } catch {
            & $log ('WMI indisponível, abrindo direto: ' + $_.Exception.Message)
            Start-Process -FilePath $PANEL_EXE -ArgumentList '--abrir-jogo', '--sem-atualizar'
        }
    }
    return
}

# ---------------- interface ----------------

Add-Type -AssemblyName System.Windows.Forms, System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()

function Rgb($hex) { [Drawing.ColorTranslator]::FromHtml($hex) }
$C_BG = Rgb '#0c1116'; $C_BODY = Rgb '#111820'; $C_CARD = Rgb '#18212b'; $C_LINE = Rgb '#263443'
$C_TEXT = Rgb '#eef3f8'; $C_MUTED = Rgb '#8d9cad'; $C_ACCENT = Rgb '#ffb547'; $C_ON_ACCENT = Rgb '#1a1206'
$C_OK = Rgb '#6fd39a'; $C_WARN = Rgb '#ffb547'; $C_ERR = Rgb '#ff7b6e'
$VERSION = try { (Get-Content -LiteralPath (Join-Path $PKG 'versao.json') -Raw | ConvertFrom-Json).versao } catch { '' }

$font = New-Object Drawing.Font('Segoe UI', 9.5)
$form = New-Object Windows.Forms.Form
$form.Text = "$APP_NAME — Instalador"
$form.ClientSize = New-Object Drawing.Size(640, 768)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedSingle'
$form.MaximizeBox = $false
$form.Font = $font
$form.BackColor = $C_BODY
$form.ForeColor = $C_TEXT

function Add-To($parent, $ctrl, $x, $y, $w, $h) {
    $ctrl.Location = New-Object Drawing.Point($x, $y)
    if ($w) { $ctrl.Size = New-Object Drawing.Size($w, $h) }
    $parent.Controls.Add($ctrl); return $ctrl
}
function New-Label($text, $color, $size = 9.5, $style = 'Regular') {
    $l = New-Object Windows.Forms.Label
    $l.Text = $text; $l.ForeColor = $color; $l.AutoSize = $true; $l.BackColor = [Drawing.Color]::Transparent
    $l.Font = New-Object Drawing.Font('Segoe UI', $size, [Drawing.FontStyle]$style)
    return $l
}
function New-Card($title, $y, $h) {
    $p = New-Object Windows.Forms.Panel
    $p.BackColor = $C_CARD
    Add-To $form $p 20 $y 600 $h | Out-Null
    Add-To $p (New-Label $title $C_ACCENT 8.5 'Bold') 16 12 | Out-Null
    return $p
}
function Set-FlatButton($b, $bg, $fg, $border) {
    $b.FlatStyle = 'Flat'; $b.BackColor = $bg; $b.ForeColor = $fg; $b.Cursor = 'Hand'
    $b.FlatAppearance.BorderColor = $border; $b.FlatAppearance.BorderSize = 1
    $b.FlatAppearance.MouseOverBackColor = [Drawing.Color]::FromArgb([Math]::Min(255, $bg.R + 18), [Math]::Min(255, $bg.G + 18), [Math]::Min(255, $bg.B + 18))
}

# cabeçalho
$header = New-Object Windows.Forms.Panel
$header.BackColor = $C_BG
Add-To $form $header 0 0 640 100 | Out-Null
$accentBar = New-Object Windows.Forms.Panel
$accentBar.BackColor = $C_ACCENT
Add-To $header $accentBar 0 97 640 3 | Out-Null
Add-To $header (New-Label $APP_NAME $C_TEXT 20 'Bold') 22 14 | Out-Null
Add-To $header (New-Label 'Minimapa com relógio do jogo, tempo dos buffs, editor de save e painel F8' $C_MUTED 9.5) 25 56 | Out-Null
if ($VERSION) {
    $ver = New-Label "v$VERSION" $C_ON_ACCENT 9 'Bold'
    $ver.BackColor = $C_ACCENT; $ver.Padding = New-Object Windows.Forms.Padding(6, 2, 6, 2)
    Add-To $header $ver 560 22 | Out-Null
}

# pasta do jogo
Add-To $form (New-Label 'PASTA DO JOGO' $C_MUTED 8.5 'Bold') 20 114 | Out-Null
$txtGame = Add-To $form (New-Object Windows.Forms.TextBox) 20 136 494 28
$txtGame.BackColor = $C_BG; $txtGame.ForeColor = $C_TEXT; $txtGame.BorderStyle = 'FixedSingle'
$txtGame.Font = New-Object Drawing.Font('Segoe UI', 10)
$btnBrowse = Add-To $form (New-Object Windows.Forms.Button) 522 135 98 28
$btnBrowse.Text = 'Procurar...'
Set-FlatButton $btnBrowse $C_CARD $C_TEXT $C_LINE
$lblGameStatus = Add-To $form (New-Object Windows.Forms.Label) 20 170 600 20

# minimapa
$cardMap = New-Card 'MINIMAPA' 198 178
function Add-Combo($label, $map, $x, $y) {
    Add-To $cardMap (New-Label $label $C_MUTED 9) $x $y | Out-Null
    $c = New-Object Windows.Forms.ComboBox
    $c.DropDownStyle = 'DropDownList'; $c.FlatStyle = 'Flat'
    $c.BackColor = $C_BG; $c.ForeColor = $C_TEXT
    foreach ($k in $map.Keys) { [void]$c.Items.Add($k) }
    $c.SelectedIndex = 0
    return (Add-To $cardMap $c $x ($y + 20) 270 26)
}
$cbPos = Add-Combo 'Posição na tela' $POSITIONS 16 38
$cbOri = Add-Combo 'Orientação do mapa' $ORIENTATIONS 312 38
$cbSty = Add-Combo 'Cores do mapa' $STYLES 16 90
$cbVis = Add-Combo 'Visual da moldura' $VISUALS 312 90
function New-Check($parent, $text, $x, $y) {
    $c = New-Object Windows.Forms.CheckBox
    $c.Text = $text; $c.Checked = $true; $c.AutoSize = $true
    $c.ForeColor = $C_TEXT; $c.FlatStyle = 'Flat'; $c.Cursor = 'Hand'
    $c.FlatAppearance.BorderColor = $C_LINE; $c.FlatAppearance.CheckedBackColor = $C_ACCENT
    return (Add-To $parent $c $x $y)
}
$chkClock = New-Check $cardMap 'Relógio do jogo' 16 146
$chkWeather = New-Check $cardMap 'Clima' 170 146
$chkFog = New-Check $cardMap 'Esconder áreas não exploradas' 270 146

# melhorias
$cardExtra = New-Card 'MELHORIAS' 388 166
$chkPanel = New-Check $cardExtra 'Painel F8 no jogo + atalho na Área de Trabalho (com atualização automática)' 16 38
$chkBuffs = New-Check $cardExtra 'Tempo dos buffs dentro dos círculos (comida, água e poções)' 36 68
$chkEditor = New-Check $cardExtra 'Editor de save (atalho "Editor de Save Enshrouded")' 36 96
$chkAltar = New-Check $cardExtra 'Desativar Altar de Chama pelo mapa-múndi (mod XHL)' 16 128

$lblVc = Add-To $form (New-Object Windows.Forms.LinkLabel) 20 564 600 20
$lblVc.LinkColor = $C_ACCENT; $lblVc.ActiveLinkColor = $C_ACCENT

# botões
$btnInstall = Add-To $form (New-Object Windows.Forms.Button) 20 592 220 42
$btnInstall.Text = 'Instalar'
$btnInstall.Font = New-Object Drawing.Font('Segoe UI', 11, [Drawing.FontStyle]::Bold)
Set-FlatButton $btnInstall $C_ACCENT $C_ON_ACCENT $C_ACCENT
$btnUninstall = Add-To $form (New-Object Windows.Forms.Button) 250 592 150 42
$btnUninstall.Text = 'Desinstalar'
Set-FlatButton $btnUninstall $C_BODY $C_TEXT $C_LINE
$btnClose = Add-To $form (New-Object Windows.Forms.Button) 520 592 100 42
$btnClose.Text = 'Fechar'
Set-FlatButton $btnClose $C_BODY $C_MUTED $C_BODY

$txtLog = Add-To $form (New-Object Windows.Forms.TextBox) 20 648 600 104
$txtLog.Multiline = $true; $txtLog.ReadOnly = $true; $txtLog.ScrollBars = 'Vertical'
$txtLog.BackColor = $C_BG; $txtLog.ForeColor = $C_MUTED; $txtLog.BorderStyle = 'None'
$txtLog.Font = New-Object Drawing.Font('Consolas', 9)

$log = { param($m) $txtLog.AppendText((Get-Date -Format 'HH:mm:ss') + '  ' + $m + "`r`n"); [Windows.Forms.Application]::DoEvents() }

function Select-ByValue($combo, $map, $value) {
    $i = 0
    foreach ($k in $map.Keys) { if ($map[$k] -eq $value) { $combo.SelectedIndex = $i; return }; $i++ }
}

function Update-PanelDeps {
    # tempo dos buffs e editor rodam dentro do painel: sem ele, ficam desligados
    foreach ($c in $chkBuffs, $chkEditor) { $c.Enabled = $chkPanel.Checked; $c.ForeColor = $(if ($chkPanel.Checked) { $C_TEXT } else { $C_MUTED }) }
}

function Update-GameStatus {
    $g = $txtGame.Text.Trim()
    $ok = $g -and (Test-Path -LiteralPath (Join-Path $g 'enshrouded.exe'))
    if (-not $ok) {
        $lblGameStatus.ForeColor = $C_ERR
        $lblGameStatus.Text = '✖ enshrouded.exe não está nessa pasta. Use "Procurar..." e escolha a pasta do jogo.'
        $btnInstall.Enabled = $false; $btnUninstall.Enabled = $false; return
    }
    $installed = Test-Path -LiteralPath (Join-Path $g "mods\$MOD_ID\minimap_mod.dll")
    $lblGameStatus.ForeColor = $C_OK
    $lblGameStatus.Text = '✔ Jogo encontrado.' + $(if ($installed) { ' Já está instalado: "Aplicar" atualiza e reconfigura.' } else { '' })
    $btnInstall.Enabled = $true; $btnUninstall.Enabled = $installed
    $btnInstall.Text = $(if ($installed) { 'Aplicar' } else { 'Instalar' })
    try {
        $cfg = Read-Config $g
        $e = if ($cfg -and $cfg.mods) { $cfg.mods.$MOD_ID } else { $null }
        if ($e) {
            Select-ByValue $cbPos $POSITIONS $e.position
            Select-ByValue $cbOri $ORIENTATIONS $e.map_orientation
            Select-ByValue $cbSty $STYLES $(if ($e.map_style -eq 'bright') { 'default' } else { $e.map_style })
            if ($null -ne $e.show_clock) { $chkClock.Checked = [bool]$e.show_clock }
            if ($null -ne $e.show_weather) { $chkWeather.Checked = [bool]$e.show_weather }
            if ($null -ne $e.show_fog_of_war) { $chkFog.Checked = [bool]$e.show_fog_of_war }
        }
    } catch { & $log "Aviso: não consegui ler o shroudtopia.json atual ($($_.Exception.Message))." }
    $o = Read-LocalOptions
    if ($o) {  # sem opcoes.json (primeira instalação) fica tudo ligado
        Select-ByValue $cbVis $VISUALS $o.visual
        $chkPanel.Checked = [bool]$o.painel
        if ($null -ne $o.altar) { $chkAltar.Checked = [bool]$o.altar }
        if ($null -ne $o.buffs) { $chkBuffs.Checked = [bool]$o.buffs }
        if ($null -ne $o.editor) { $chkEditor.Checked = [bool]$o.editor }
    }
    Update-PanelDeps
}

function Confirm-Ready($g) {
    if (Test-GameRunning $g) {
        [Windows.Forms.MessageBox]::Show('Feche o Enshrouded antes de continuar.', 'Jogo aberto', 'OK', 'Warning') | Out-Null
        return $false
    }
    if (-not (Test-Writable $g)) {
        $r = [Windows.Forms.MessageBox]::Show("O Windows não deixou gravar na pasta do jogo.`n`nAbrir o instalador como administrador?",
            'Permissão necessária', 'YesNo', 'Question')
        if ($r -eq 'Yes') {
            Start-Process powershell.exe -Verb RunAs -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-STA',
                '-WindowStyle', 'Hidden', '-File', "`"$PSCommandPath`"")
            $form.Close()
        }
        return $false
    }
    return $true
}

$btnBrowse.Add_Click({
    $dlg = New-Object Windows.Forms.FolderBrowserDialog
    $dlg.Description = 'Escolha a pasta onde está o enshrouded.exe'
    if ($txtGame.Text -and (Test-Path -LiteralPath $txtGame.Text)) { $dlg.SelectedPath = $txtGame.Text }
    if ($dlg.ShowDialog() -eq 'OK') { $txtGame.Text = $dlg.SelectedPath }
})
$txtGame.Add_TextChanged({ Update-GameStatus })
$chkPanel.Add_CheckedChanged({ Update-PanelDeps })
$lblVc.Add_LinkClicked({ Start-Process 'https://aka.ms/vc14/vc_redist.x64.exe' })
$btnClose.Add_Click({ $form.Close() })

$btnInstall.Add_Click({
    $g = $txtGame.Text.Trim()
    if (-not (Confirm-Ready $g)) { return }
    $form.UseWaitCursor = $true; $btnInstall.Enabled = $false
    try {
        & $log 'Conferindo os arquivos do pacote...'
        $bad = Test-Package
        if ($bad.Count) { throw ('Arquivos do instalador corrompidos ou faltando: ' + ($bad -join ', ') + '. Baixe o pacote de novo.') }
        $winmm = Join-Path $g 'winmm.dll'
        if ((Test-Path -LiteralPath $winmm) -and (Get-Sha256 $winmm) -ne (Get-Sha256 (Join-Path $PKG 'shroudtopia\winmm.dll'))) {
            $r = [Windows.Forms.MessageBox]::Show("Já existe um winmm.dll diferente na pasta do jogo (pode ser de outro mod).`n`n" +
                "Ele vai para o backup e será substituído. Continuar?", 'Arquivo existente', 'YesNo', 'Warning')
            if ($r -ne 'Yes') { & $log 'Cancelado.'; return }
        }
        $opts = @{ position = $POSITIONS[$cbPos.SelectedItem]; orientation = $ORIENTATIONS[$cbOri.SelectedItem]
                   style = $STYLES[$cbSty.SelectedItem]; clock = $chkClock.Checked; weather = $chkWeather.Checked; fog = $chkFog.Checked }
        $visual = $VISUALS[$cbVis.SelectedItem]
        $panel = $chkPanel.Checked
        $buffs = $panel -and $chkBuffs.Checked
        $editor = $panel -and $chkEditor.Checked
        Install-Minimap $g $opts $log
        Set-Visual $g $visual $log
        if ($panel) { Install-Panel $g $editor $log } else { Remove-Panel $log }
        $o = Read-LocalOptions
        $color = if ($o -and $o.color) { $o.color } else { 'ambar' }
        Apply-Color $g $color $log
        if ($chkAltar.Checked) { Install-Altar $g $log } else { Remove-Altar $g $log }
        Save-LocalInfo $g $visual $panel $chkAltar.Checked $color $buffs $editor
        & $log 'PRONTO!'
        $how = if ($panel) {
            "Abra o jogo pelo atalho 'Jogar Enshrouded (Melhorias)' na Área de Trabalho.`n" +
            "Dentro do jogo, F8 abre o painel (Tab troca de aba).`nAs atualizações chegam sozinhas por esse atalho." +
            $(if ($buffs) { "`n`nTempo dos buffs: aparece dentro dos círculos de comida/água (jogo em Janela sem bordas)." } else { '' }) +
            $(if ($editor) { "`nEditor de save: atalho 'Editor de Save Enshrouded' (abre no navegador)." } else { '' })
        } else { 'Abra o Enshrouded normalmente pela Steam e entre no mundo.' }
        [Windows.Forms.MessageBox]::Show("Instalado!`n`n$how`n`n" +
            "F10: mostrar/esconder o minimapa`n+ / - : zoom`nF9 / F11: diminuir / aumentar" +
            $(if ($chkAltar.Checked) { "`n`nAltar: no mapa-múndi, clique no Altar de Chama e confirme com um segundo clique." } else { '' }),
            $APP_NAME, 'OK', 'Information') | Out-Null
    } catch {
        & $log ('ERRO: ' + $_.Exception.Message)
        [Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Erro', 'OK', 'Error') | Out-Null
    } finally { $form.UseWaitCursor = $false; Update-GameStatus }
})

$btnUninstall.Add_Click({
    $g = $txtGame.Text.Trim()
    if (-not (Confirm-Ready $g)) { return }
    $r = [Windows.Forms.MessageBox]::Show("Remover o $APP_NAME? Um backup é feito antes.", 'Desinstalar', 'YesNo', 'Question')
    if ($r -ne 'Yes') { return }
    try { Uninstall-Minimap $g $log; & $log "$APP_NAME desinstalado." }
    catch { & $log ('ERRO: ' + $_.Exception.Message); [Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Erro', 'OK', 'Error') | Out-Null }
    finally { Update-GameStatus }
})

$form.Add_Shown({
    $found = @(Find-GameFolders)
    if ($found.Count) {
        $txtGame.Text = $found[0]
        & $log ("Enshrouded encontrado em: " + $found[0])
        if ($found.Count -gt 1) { & $log ('Também achei: ' + (($found | Select-Object -Skip 1) -join '; ')) }
    } else {
        Update-GameStatus
        & $log 'Não achei o jogo sozinho. Clique em "Procurar..." e escolha a pasta onde está o enshrouded.exe.'
    }
    if (Test-VcRedist) {
        $lblVc.Text = '✔ Visual C++ x64 instalado (necessário para o mod).'
        $lblVc.LinkArea = New-Object Windows.Forms.LinkArea(0, 0)
        $lblVc.ForeColor = $C_OK
    } else {
        $lblVc.Text = '⚠ Falta o Visual C++ x64 (o mod precisa dele). Clique aqui para baixar e instalar.'
        $lblVc.LinkArea = New-Object Windows.Forms.LinkArea(46, 25)
        $lblVc.ForeColor = $C_WARN
    }
    $btnInstall.Select()  # sem isso a primeira lista fica com o foco e pode abrir sozinha
})

[void]$form.ShowDialog()
