# Instalador do Shroudweave Minimap 0.5.15 + Shroudtopia 0.2.1 para Enshrouded.
# Compatível com Windows PowerShell 5.1 (já vem no Windows 10/11). Aberto pelo "Instalar Minimap.bat".
# -Atualizar: modo silencioso chamado pelo PainelMinimapa.exe quando há versão nova no GitHub.
param([switch]$Atualizar)

$ErrorActionPreference = 'Stop'
$PKG = $PSScriptRoot
$MOD_ID = 'minimap_mod'
$DLLS = @('winmm.dll', 'shroudtopia.dll')
$BACKUP_ROOT = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Enshrouded Minimap Backups'
$LOCAL_DIR = Join-Path $env:LOCALAPPDATA 'EnshroudedMinimap'   # painel, versão instalada e opções escolhidas
$PANEL_EXE = Join-Path $LOCAL_DIR 'PainelMinimapa.exe'
$SHORTCUT = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Jogar Enshrouded com Painel.lnk'
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
    $p = @(Get-Process PainelMinimapa -ErrorAction SilentlyContinue)
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

function Save-LocalInfo($game, $visual, $painel, $altar, $color) {
    New-Item -ItemType Directory -Force -Path $LOCAL_DIR | Out-Null
    Copy-Item -LiteralPath (Join-Path $PKG 'versao.json') -Destination (Join-Path $LOCAL_DIR 'versao.json') -Force
    $o = [ordered]@{ game_dir = $game; visual = $visual; painel = [bool]$painel; altar = [bool]$altar; color = $color }
    [IO.File]::WriteAllText((Join-Path $LOCAL_DIR 'opcoes.json'), ($o | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
}

function Install-Panel($game, $log) {
    Stop-Panel
    New-Item -ItemType Directory -Force -Path $LOCAL_DIR | Out-Null
    Copy-WithRetry (Join-Path $PKG 'painel\PainelMinimapa.exe') $PANEL_EXE
    Deploy-Cores $log
    $sh = (New-Object -ComObject WScript.Shell).CreateShortcut($SHORTCUT)
    $sh.TargetPath = $PANEL_EXE
    $sh.Arguments = '--abrir-jogo'
    $sh.WorkingDirectory = $LOCAL_DIR
    $sh.Description = 'Abre o Enshrouded com o painel do minimapa (F8) e mantém o minimapa atualizado'
    $sh.IconLocation = (Join-Path $game 'enshrouded.exe') + ',0'
    $sh.Save()
    & $log 'Painel F8 instalado e atalho "Jogar Enshrouded com Painel" criado na Área de Trabalho.'
}

function Remove-Panel($log) {
    Stop-Panel
    $had = $false
    foreach ($p in $PANEL_EXE, $SHORTCUT) { if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force; $had = $true } }
    if ($had) { & $log 'Painel F8 e atalho removidos.' }
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
        for ($i = 0; $i -lt 40 -and (Get-Process PainelMinimapa -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Milliseconds 500 }
        if (Test-GameRunning $game) { throw 'o jogo está aberto; tento de novo na próxima vez' }
        $bad = Test-Package
        if ($bad.Count) { throw ('pacote corrompido: ' + ($bad -join ', ')) }
        Install-Minimap $game $null $log
        Set-Visual $game $o.visual $log
        if ($o.painel) { Install-Panel $game $log }
        $color = if ($o.color) { $o.color } else { 'ambar' }
        Apply-Color $game $color $log
        # quem instalou antes do altar existir (sem a opcao salva) recebe o altar na atualizacao
        $altar = if ($null -eq $o.altar) { $true } else { [bool]$o.altar }
        if ($altar) { Install-Altar $game $log } else { Remove-Altar $game $log }
        Save-LocalInfo $game $o.visual $o.painel $altar $color
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

$font = New-Object Drawing.Font('Segoe UI', 9.5)
$form = New-Object Windows.Forms.Form
$form.Text = 'Instalador — Minimapa e Relógio para Enshrouded'
$form.ClientSize = New-Object Drawing.Size(600, 690)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.Font = $font
$form.BackColor = [Drawing.Color]::White

function Add-Control($ctrl, $x, $y, $w, $h) {
    $ctrl.Location = New-Object Drawing.Point($x, $y)
    if ($w) { $ctrl.Size = New-Object Drawing.Size($w, $h) }
    $form.Controls.Add($ctrl); return $ctrl
}

$header = New-Object Windows.Forms.Panel
$header.BackColor = [Drawing.Color]::FromArgb(28, 38, 48)
Add-Control $header 0 0 600 74 | Out-Null
$title = New-Object Windows.Forms.Label
$title.Text = 'Minimapa e Relógio do Jogo'
$title.Font = New-Object Drawing.Font('Segoe UI Semibold', 16)
$title.ForeColor = [Drawing.Color]::White
$title.AutoSize = $true
$title.Location = New-Object Drawing.Point(18, 10)
$header.Controls.Add($title)
$sub = New-Object Windows.Forms.Label
$sub.Text = 'Shroudweave Minimap 0.5.15 + Shroudtopia 0.2.1 para Enshrouded'
$sub.ForeColor = [Drawing.Color]::FromArgb(190, 205, 215)
$sub.AutoSize = $true
$sub.Location = New-Object Drawing.Point(20, 44)
$header.Controls.Add($sub)

$lblGame = Add-Control (New-Object Windows.Forms.Label) 18 88 560 20
$lblGame.Text = 'Pasta do Enshrouded:'
$txtGame = Add-Control (New-Object Windows.Forms.TextBox) 18 110 460 26
$btnBrowse = Add-Control (New-Object Windows.Forms.Button) 486 108 96 28
$btnBrowse.Text = 'Procurar...'
$lblGameStatus = Add-Control (New-Object Windows.Forms.Label) 18 140 564 20

$grp = Add-Control (New-Object Windows.Forms.GroupBox) 18 168 564 262
$grp.Text = 'Opções'
function Add-Combo($label, $map, $y) {
    $l = New-Object Windows.Forms.Label; $l.Text = $label; $l.Location = New-Object Drawing.Point(14, ($y + 4)); $l.AutoSize = $true
    $c = New-Object Windows.Forms.ComboBox; $c.DropDownStyle = 'DropDownList'
    $c.Location = New-Object Drawing.Point(170, $y); $c.Size = New-Object Drawing.Size(240, 26)
    foreach ($k in $map.Keys) { [void]$c.Items.Add($k) }
    $c.SelectedIndex = 0
    $grp.Controls.Add($l); $grp.Controls.Add($c); return $c
}
$cbPos = Add-Combo 'Posição na tela:' $POSITIONS 26
$cbOri = Add-Combo 'Orientação do mapa:' $ORIENTATIONS 60
$cbSty = Add-Combo 'Cores do mapa:' $STYLES 94
$cbVis = Add-Combo 'Visual da moldura:' $VISUALS 128
function Add-Check($text, $x, $y = 166) {
    $c = New-Object Windows.Forms.CheckBox; $c.Text = $text; $c.Checked = $true; $c.AutoSize = $true
    $c.Location = New-Object Drawing.Point($x, $y); $grp.Controls.Add($c); return $c
}
$chkClock = Add-Check 'Relógio do jogo' 14
$chkWeather = Add-Check 'Clima' 170
$chkFog = Add-Check 'Esconder áreas não exploradas' 260
$chkPanel = Add-Check 'Painel F8 dentro do jogo + atalho na Área de Trabalho (com atualização automática)' 14 198
$chkAltar = Add-Check 'Desativar Altar de Chama pelo mapa-múndi (mod XHL)' 14 228

$lblVc = Add-Control (New-Object Windows.Forms.LinkLabel) 18 440 564 20

$btnInstall = Add-Control (New-Object Windows.Forms.Button) 18 468 200 38
$btnInstall.Text = 'Instalar'
$btnInstall.Font = New-Object Drawing.Font('Segoe UI Semibold', 11)
$btnInstall.BackColor = [Drawing.Color]::FromArgb(46, 125, 50)
$btnInstall.ForeColor = [Drawing.Color]::White
$btnInstall.FlatStyle = 'Flat'
$btnUninstall = Add-Control (New-Object Windows.Forms.Button) 228 468 140 38
$btnUninstall.Text = 'Desinstalar'
$btnClose = Add-Control (New-Object Windows.Forms.Button) 482 468 100 38
$btnClose.Text = 'Fechar'

$txtLog = Add-Control (New-Object Windows.Forms.TextBox) 18 518 564 154
$txtLog.Multiline = $true; $txtLog.ReadOnly = $true; $txtLog.ScrollBars = 'Vertical'
$txtLog.BackColor = [Drawing.Color]::FromArgb(245, 247, 249)

$log = { param($m) $txtLog.AppendText((Get-Date -Format 'HH:mm:ss') + '  ' + $m + "`r`n"); [Windows.Forms.Application]::DoEvents() }

function Select-ByValue($combo, $map, $value) {
    $i = 0
    foreach ($k in $map.Keys) { if ($map[$k] -eq $value) { $combo.SelectedIndex = $i; return }; $i++ }
}

function Update-GameStatus {
    $g = $txtGame.Text.Trim()
    $ok = $g -and (Test-Path -LiteralPath (Join-Path $g 'enshrouded.exe'))
    if (-not $ok) {
        $lblGameStatus.ForeColor = [Drawing.Color]::Firebrick
        $lblGameStatus.Text = '✖ enshrouded.exe não está nessa pasta. Use "Procurar..." e escolha a pasta do jogo.'
        $btnInstall.Enabled = $false; $btnUninstall.Enabled = $false; return
    }
    $installed = Test-Path -LiteralPath (Join-Path $g "mods\$MOD_ID\minimap_mod.dll")
    $lblGameStatus.ForeColor = [Drawing.Color]::ForestGreen
    $lblGameStatus.Text = '✔ Jogo encontrado.' + $(if ($installed) { ' O minimapa já está instalado: "Instalar" atualiza/reconfigura.' } else { '' })
    $btnInstall.Enabled = $true; $btnUninstall.Enabled = $installed
    $btnInstall.Text = $(if ($installed) { 'Reinstalar / Aplicar' } else { 'Instalar' })
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
    try {
        $o = Get-Content -LiteralPath (Join-Path $LOCAL_DIR 'opcoes.json') -Raw | ConvertFrom-Json
        Select-ByValue $cbVis $VISUALS $o.visual
        $chkPanel.Checked = [bool]$o.painel
        if ($null -ne $o.altar) { $chkAltar.Checked = [bool]$o.altar }
    } catch { }  # primeira instalação: fica o padrão (moderno + painel)
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
        Install-Minimap $g $opts $log
        Set-Visual $g $visual $log
        if ($chkPanel.Checked) { Install-Panel $g $log } else { Remove-Panel $log }
        $color = try { (Get-Content -LiteralPath (Join-Path $LOCAL_DIR 'opcoes.json') -Raw | ConvertFrom-Json).color } catch { $null }
        if (-not $color) { $color = 'ambar' }
        Apply-Color $g $color $log
        if ($chkAltar.Checked) { Install-Altar $g $log } else { Remove-Altar $g $log }
        Save-LocalInfo $g $visual $chkPanel.Checked $chkAltar.Checked $color
        & $log 'PRONTO!'
        $how = if ($chkPanel.Checked) { "Abra o jogo pelo atalho 'Jogar Enshrouded com Painel' na Área de Trabalho.`nDentro do jogo, F8 abre o painel do minimapa.`nAs atualizações chegam sozinhas por esse atalho." } else { 'Abra o Enshrouded normalmente pela Steam e entre no mundo.' }
        [Windows.Forms.MessageBox]::Show("Instalado!`n`n$how`n`n" +
            "F10: mostrar/esconder`n+ / - : zoom`nF9 / F11: diminuir / aumentar" +
            $(if ($chkAltar.Checked) { "`n`nAltar: no mapa-múndi, clique no Altar de Chama e confirme com um segundo clique." } else { '' }),
            'Pronto', 'OK', 'Information') | Out-Null
    } catch {
        & $log ('ERRO: ' + $_.Exception.Message)
        [Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Erro', 'OK', 'Error') | Out-Null
    } finally { $form.UseWaitCursor = $false; Update-GameStatus }
})

$btnUninstall.Add_Click({
    $g = $txtGame.Text.Trim()
    if (-not (Confirm-Ready $g)) { return }
    $r = [Windows.Forms.MessageBox]::Show('Remover o minimapa? Um backup é feito antes.', 'Desinstalar', 'YesNo', 'Question')
    if ($r -ne 'Yes') { return }
    try { Uninstall-Minimap $g $log; & $log 'Minimapa desinstalado.' }
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
        $lblVc.ForeColor = [Drawing.Color]::ForestGreen
    } else {
        $lblVc.Text = '⚠ Falta o Visual C++ x64 (o mod precisa dele). Clique aqui para baixar e instalar.'
        $lblVc.LinkArea = New-Object Windows.Forms.LinkArea(46, 25)
        $lblVc.ForeColor = [Drawing.Color]::DarkOrange
    }
    $btnInstall.Select()  # sem isso a primeira lista fica com o foco e pode abrir sozinha
})

[void]$form.ShowDialog()
