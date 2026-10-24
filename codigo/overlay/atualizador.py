"""Atualizacao automatica do pacote do minimapa (usado pelo PainelMinimapa.exe ao abrir).

O instalador grava em %LOCALAPPDATA%\\EnshroudedMinimap\\versao.json a versao instalada e o
repositorio do GitHub. A cada abertura do atalho, comparamos com
https://github.com/<repo>/releases/latest/download/versao.json; se houver versao nova,
baixamos o .zip, conferimos o SHA-256 e chamamos o instalador em modo -Atualizar, que
espera este programa fechar, aplica a atualizacao mantendo as opcoes e reabre tudo.
Qualquer falha (sem internet, GitHub fora etc.) so e registrada: o jogo abre normalmente.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

LOCAL_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'EnshroudedMinimap')
VERSION_FILE = os.path.join(LOCAL_DIR, 'versao.json')
LOG_FILE = os.path.join(LOCAL_DIR, 'atualizacao.log')
UA = {'User-Agent': 'EnshroudedMinimap-Atualizador'}


def log(msg):
    try:
        os.makedirs(LOCAL_DIR, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + msg + '\n')
    except OSError:
        pass


def parse_version(v):
    return tuple(int(x) for x in str(v).lstrip('v').split('.') if x.isdigit())


def local_info():
    try:
        with open(VERSION_FILE, encoding='utf-8-sig') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def fetch(url, timeout):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def check():
    """Devolve o versao.json remoto se houver versao mais nova; senao None."""
    info = local_info()
    if not info or not info.get('repo'):
        return None
    base = f"https://github.com/{info['repo']}/releases/latest/download/"
    remote = json.loads(fetch(base + 'versao.json', 6))
    if parse_version(remote['versao']) <= parse_version(info.get('versao', '0')):
        return None
    remote['_base'] = base
    return remote


def download_and_launch(remote, progress=lambda msg: None):
    """Baixa, confere e dispara o instalador. Retorna True se o instalador foi iniciado."""
    progress(f"Baixando a versão {remote['versao']}…")
    data = fetch(remote['_base'] + remote['arquivo'], 120)
    if hashlib.sha256(data).hexdigest() != remote['sha256'].lower():
        raise ValueError('arquivo baixado nao confere com o SHA-256 publicado')
    progress('Instalando…')
    tmp = tempfile.mkdtemp(prefix='minimap-update-')
    zpath = os.path.join(tmp, 'pacote.zip')
    with open(zpath, 'wb') as f:
        f.write(data)
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():  # nada de caminhos fora da pasta temporaria
            if name.startswith(('/', '\\')) or '..' in name.replace('\\', '/').split('/'):
                raise ValueError('zip com caminho suspeito: ' + name)
        z.extractall(tmp)
    script = next((os.path.join(root, 'instalador.ps1') for root, _, files in os.walk(tmp) if 'instalador.ps1' in files), None)
    if not script:
        raise ValueError('instalador.ps1 nao encontrado no pacote')
    launch_detached(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-STA', '-WindowStyle', 'Hidden',
                     '-File', script, '-Atualizar'])
    log(f"atualizacao para {remote['versao']} iniciada ({script})")
    return True


def launch_detached(cmd):
    """Inicia um processo que sobrevive ao fechamento deste .exe.

    O .exe do PyInstaller roda dentro de um 'job' do Windows que fecha todos os filhos quando
    ele sai; o instalador (e o painel que ele reabre) morreriam junto. Primeiro tentamos sair
    do job; se o Windows nao deixar, pedimos ao WMI para criar o processo (fica fora do job).
    """
    try:
        subprocess.Popen(cmd, creationflags=0x01000000 | 0x08000000)  # CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW
        return
    except OSError as e:
        log(f'breakaway negado ({e}); usando WMI')
    line = subprocess.list2cmdline(cmd).replace("'", "''")
    subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                    f"Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine='{line}'}} | Out-Null"],
                   creationflags=0x08000000, check=True, timeout=30)


def run_with_window():
    """Checa e, se houver versao nova, mostra uma janelinha enquanto baixa. True = vai reiniciar."""
    try:
        remote = check()
    except Exception as e:  # noqa: BLE001 - sem internet etc.: segue sem atualizar
        log(f'checagem falhou: {e}')
        return False
    if not remote:
        return False
    import tkinter as tk
    root = tk.Tk()
    root.title('Minimapa — atualização')
    root.configure(bg='#11161c')
    root.resizable(False, False)
    lbl = tk.Label(root, text='Atualizando o minimapa…', fg='#eef2f6', bg='#11161c', font=('Segoe UI', 12), padx=28, pady=22)
    lbl.pack()
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    root.geometry(f'+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 2}')
    result = {'ok': False}

    def work():
        def progress(msg):
            lbl.config(text=f"Minimapa {remote['versao']}: {msg}")
            root.update()
        try:
            result['ok'] = download_and_launch(remote, progress)
        except Exception as e:  # noqa: BLE001
            log(f'atualizacao falhou: {e}')
        root.destroy()
    root.after(100, work)
    root.mainloop()
    return result['ok']


if __name__ == '__main__':
    print('versao local:', local_info())
    try:
        print('versao nova:', check())
    except Exception as e:  # noqa: BLE001
        print('falhou:', e)
    sys.exit(0)
