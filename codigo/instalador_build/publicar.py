"""Monta (e opcionalmente publica no GitHub) uma versao nova do instalador do minimapa.

Uso:
  python instalador_build/publicar.py 1.0.1                     # so monta o .zip
  python instalador_build/publicar.py 1.0.1 --publicar --notas "o que mudou"

Passos: recompila o PainelMinimapa.exe, copia o visual moderno, grava a versao, refaz o
SHA256SUMS do pacote, gera o .zip e o versao.json que os PCs dos amigos consultam em
https://github.com/<repo>/releases/latest/download/versao.json
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)                                   # EnshroudedEditor
PKG_ROOT = os.path.join(HERE, 'pacote', 'Instalador Minimap Enshrouded')  # copia de trabalho do pacote
PKG = os.path.join(PKG_ROOT, 'arquivos')
OUT = os.path.join(HERE, 'release')
ZIP_NAME = 'Instalador-Minimap-Enshrouded.zip'               # sem espacos: o GitHub troca espaco por ponto
CONFIG = os.path.join(HERE, 'publicar.json')                   # {"repo": "usuario/repositorio"}
GH = shutil.which('gh') or os.path.expandvars(
    r'%LOCALAPPDATA%\Microsoft\WinGet\Packages\GitHub.cli_Microsoft.Winget.Source_8wekyb3d8bbwe\bin\gh.exe')
CHECKED_DIRS = ('shroudtopia', 'minimap_mod', 'visual_moderno', 'painel', 'xhl', 'cores')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def build_exe():
    print('> compilando PainelMinimapa.exe…')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--onefile', '--noconsole', '--name', 'PainelMinimapa',
                    '--paths', APP, '--paths', os.path.join(APP, 'overlay'), '--icon', os.path.join(HERE, 'painel.ico'),
                    '--distpath', os.path.join(HERE, 'dist'), '--workpath', os.path.join(HERE, 'work'),
                    '--specpath', HERE, '-y', '--log-level', 'WARN', os.path.join(APP, 'overlay', 'painel_minimapa.py')],
                   check=True, cwd=APP)


def assemble(version, repo):
    os.makedirs(os.path.join(PKG, 'painel'), exist_ok=True)
    shutil.copy2(os.path.join(HERE, 'dist', 'PainelMinimapa.exe'), os.path.join(PKG, 'painel', 'PainelMinimapa.exe'))
    os.makedirs(os.path.join(PKG, 'visual_moderno'), exist_ok=True)
    for f in ('embervale_minimap_frame.rgba', 'embervale_player_arrow.rgba'):
        shutil.copy2(os.path.join(APP, 'minimap_visual', 'saida', f), os.path.join(PKG, 'visual_moderno', f))
    # cores da moldura (o instalador coloca em %LOCALAPPDATA%\EnshroudedMinimap\cores para o painel trocar)
    cores_pkg = os.path.join(PKG, 'cores')
    if os.path.isdir(cores_pkg):
        shutil.rmtree(cores_pkg)
    shutil.copytree(os.path.join(APP, 'minimap_visual', 'cores'), cores_pkg)
    with open(os.path.join(PKG, 'versao.json'), 'w', encoding='utf-8') as f:
        json.dump({'versao': version, 'repo': repo}, f, indent=2)
    lines = []
    for d in CHECKED_DIRS:
        for root, _, files in os.walk(os.path.join(PKG, d)):
            for name in sorted(files):
                full = os.path.join(root, name)
                rel = os.path.relpath(full, PKG).replace('\\', '/')
                lines.append(f'{sha256(full)} *{rel}')
    lines.append(f"{sha256(os.path.join(PKG, 'versao.json'))} *versao.json")
    with open(os.path.join(PKG, 'SHA256SUMS.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(sorted(lines, key=lambda l: l.split('*', 1)[1])) + '\n')
    print(f'> pacote montado ({len(lines)} arquivos conferidos)')


def make_zip(version, notes):
    os.makedirs(OUT, exist_ok=True)
    zpath = os.path.join(OUT, ZIP_NAME)
    base = os.path.basename(PKG_ROOT)
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, _, files in os.walk(PKG_ROOT):
            for name in files:
                full = os.path.join(root, name)
                z.write(full, os.path.join(base, os.path.relpath(full, PKG_ROOT)))
    manifest = {'versao': version, 'arquivo': ZIP_NAME, 'sha256': sha256(zpath), 'notas': notes}
    with open(os.path.join(OUT, 'versao.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f'> {zpath} ({os.path.getsize(zpath) / 1e6:.1f} MB)')
    return zpath


def publish(version, repo, notes):
    print(f'> publicando v{version} em github.com/{repo}…')
    subprocess.run([GH, 'release', 'create', f'v{version}', os.path.join(OUT, ZIP_NAME), os.path.join(OUT, 'versao.json'),
                    '--repo', repo, '--title', f'Minimapa {version}', '--notes', notes or f'Versão {version}'], check=True)
    print(f'> pronto: https://github.com/{repo}/releases/tag/v{version}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('versao')
    ap.add_argument('--publicar', action='store_true')
    ap.add_argument('--notas', default='')
    ap.add_argument('--repo')
    ap.add_argument('--sem-compilar', action='store_true')
    a = ap.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+', a.versao):
        sys.exit('versao precisa ser no formato 1.2.3')
    cfg = json.load(open(CONFIG, encoding='utf-8')) if os.path.exists(CONFIG) else {}
    repo = a.repo or cfg.get('repo')
    if not repo:
        sys.exit('falta o repositorio: use --repo usuario/nome (fica salvo em publicar.json)')
    if a.repo:
        json.dump({'repo': repo}, open(CONFIG, 'w', encoding='utf-8'), indent=2)
    if not a.sem_compilar:
        build_exe()
    assemble(a.versao, repo)
    make_zip(a.versao, a.notas)
    if a.publicar:
        publish(a.versao, repo, a.notas)


if __name__ == '__main__':
    main()
