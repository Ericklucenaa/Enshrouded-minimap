"""Idiomas do painel F8 e da janelinha de atualizacao: Portugues, English, Espanol.

O texto em portugues e a chave; T guarda (ingles, espanhol). A escolha fica no opcoes.json
("idioma": "pt" | "en" | "es"); sem escolha, segue o idioma do Windows.
"""
import ctypes
import json
import os

IDIOMAS = [('pt', 'Português'), ('en', 'English'), ('es', 'Español')]
_atual = ['pt']


def _opcoes_path():
    return os.path.join(os.environ.get('LOCALAPPDATA', ''), 'EnshroudedMinimap', 'opcoes.json')


def idioma_do_windows():
    try:
        prim = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
    except (AttributeError, OSError):
        return 'pt'
    return {0x16: 'pt', 0x0A: 'es'}.get(prim, 'en')


def carregar():
    """Le o idioma escolhido (ou detecta o do Windows) e ativa."""
    try:
        with open(_opcoes_path(), encoding='utf-8-sig') as f:
            escolhido = json.load(f).get('idioma')
    except (OSError, ValueError):
        escolhido = None
    return definir(escolhido if escolhido in dict(IDIOMAS) else idioma_do_windows())


def definir(codigo):
    _atual[0] = codigo if codigo in dict(IDIOMAS) else 'pt'
    return _atual[0]


def atual():
    return _atual[0]


def t(texto):
    if _atual[0] == 'pt' or texto not in T:
        return texto
    return T[texto][0 if _atual[0] == 'en' else 1]


T = {
    # cabecalho, abas, rodape
    'mudanças valem na hora': ('changes apply instantly', 'los cambios se aplican al instante'),
    'Minimapa': ('Minimap', 'Minimapa'),
    'Mostrar': ('Show', 'Mostrar'),
    'Visual': ('Look', 'Visual'),
    'Melhorias': ('Extras', 'Extras'),
    'Teclas': ('Keys', 'Teclas'),
    'escolher': ('select', 'elegir'),
    'mudar': ('change', 'cambiar'),
    'aba': ('tab', 'pestaña'),
    'fechar': ('close', 'cerrar'),
    # aba Minimapa
    'Idioma / Language': ('Language / Idioma', 'Idioma / Language'),
    'Minimapa ligado': ('Minimap on', 'Minimapa activado'),
    'Posição': ('Position', 'Posición'),
    'Tamanho': ('Size', 'Tamaño'),
    'Orientação': ('Orientation', 'Orientación'),
    'Norte fixo': ('North up', 'Norte fijo'),
    'Gira com você': ('Rotates with you', 'Gira contigo'),
    'Máximo de ícones': ('Max icons', 'Máximo de iconos'),
    'Névoa (não explorado)': ('Fog (unexplored)', 'Niebla (sin explorar)'),
    'Embaixo à direita': ('Bottom right', 'Abajo a la derecha'),
    'Meio à direita': ('Middle right', 'Centro a la derecha'),
    'Em cima à direita': ('Top right', 'Arriba a la derecha'),
    'Em cima à esquerda': ('Top left', 'Arriba a la izquierda'),
    'Meio à esquerda': ('Middle left', 'Centro a la izquierda'),
    'Embaixo à esquerda': ('Bottom left', 'Abajo a la izquierda'),
    # aba Mostrar
    'Relógio do jogo': ('Game clock', 'Reloj del juego'),
    'Clima': ('Weather', 'Clima'),
    'Locais do mapa': ('Map locations', 'Lugares del mapa'),
    'Destino marcado': ('Marked waypoint', 'Destino marcado'),
    'Outros jogadores': ('Other players', 'Otros jugadores'),
    'Pings': ('Pings', 'Pings'),
    'Túmulos': ('Graves', 'Tumbas'),
    # aba Visual
    'Cores do mapa': ('Map colors', 'Colores del mapa'),
    'Colorido (HD)': ('Colorful (HD)', 'Colorido (HD)'),
    'Originais': ('Original', 'Originales'),
    'Ícones': ('Icons', 'Iconos'),
    'Moldura dourada': ('Golden frame', 'Marco dorado'),
    'Brilho do terreno': ('Terrain brightness', 'Brillo del terreno'),
    'Nitidez': ('Sharpness', 'Nitidez'),
    'Alta': ('High', 'Alta'),
    'Padrão': ('Default', 'Normal'),
    'Baixa': ('Low', 'Baja'),
    'Tema da moldura *': ('Frame theme *', 'Tema del marco *'),
    'Cor da moldura *': ('Frame color *', 'Color del marco *'),
    'Moderno': ('Modern', 'Moderno'),
    'Vidro': ('Glass', 'Vidrio'),
    'Tático': ('Tactical', 'Táctico'),
    'Premium': ('Premium', 'Premium'),
    'Original (bronze)': ('Original (bronze)', 'Original (bronce)'),
    'Âmbar': ('Amber', 'Ámbar'),
    'Azul': ('Blue', 'Azul'),
    'Verde': ('Green', 'Verde'),
    'Vermelho': ('Red', 'Rojo'),
    'Branco': ('White', 'Blanco'),
    # aba Melhorias
    'Tempo dos buffs': ('Buff timers', 'Tiempo de los buffs'),
    'Editor de save': ('Save editor', 'Editor de partidas'),
    'Apoiar o projeto (Ko-fi)': ('Support the project (Ko-fi)', 'Apoyar el proyecto (Ko-fi)'),
    'Abrir': ('Open', 'Abrir'),
    # aba Teclas
    'Abrir este painel': ('Open this panel', 'Abrir este panel'),
    'Mostrar/esconder minimapa': ('Show/hide minimap', 'Mostrar/ocultar minimapa'),
    'Mais zoom': ('Zoom in', 'Acercar'),
    'Menos zoom': ('Zoom out', 'Alejar'),
    'Diminuir minimapa': ('Shrink minimap', 'Reducir minimapa'),
    'Aumentar minimapa': ('Enlarge minimap', 'Agrandar minimapa'),
    'nenhuma': ('none', 'ninguna'),
    'Espaço': ('Space', 'Espacio'),
    '[aperte…]': ('[press…]', '[pulsa…]'),
    # avisos do rodape
    'cancelado': ('cancelled', 'cancelado'),
    'abrir painel: ': ('open panel: ', 'abrir panel: '),
    ' — pode pedir reiniciar': (' — may need a restart', ' — puede requerir reiniciar'),
    'erro: ': ('error: ', 'error: '),
    'aperte a nova tecla (Esc cancela)': ('press the new key (Esc cancels)', 'pulsa la nueva tecla (Esc cancela)'),
    'sem temas disponíveis': ('no themes available', 'no hay temas disponibles'),
    'tema: ': ('theme: ', 'tema: '),
    ' — reinicie o jogo': (' — restart the game', ' — reinicia el juego'),
    'este tema não tem cores': ('this theme has no colors', 'este tema no tiene colores'),
    'cor: ': ('color: ', 'color: '),
    'Ko-fi abrindo no navegador. Obrigado!': ('Opening Ko-fi in the browser. Thank you!',
                                              'Abriendo Ko-fi en el navegador. ¡Gracias!'),
    'editor abrindo no navegador…': ('opening the editor in the browser…', 'abriendo el editor en el navegador…'),
    '✔ tempo dos buffs ligado': ('✔ buff timers on', '✔ tiempo de los buffs activado'),
    '✔ tempo dos buffs desligado': ('✔ buff timers off', '✔ tiempo de los buffs desactivado'),
    '✔ aplicado': ('✔ applied', '✔ aplicado'),
    '✔ idioma: Português': ('✔ language: English', '✔ idioma: Español'),
    # janelinha de atualizacao
    'Melhorias Enshrouded — atualização': ('Melhorias Enshrouded — update', 'Melhorias Enshrouded — actualización'),
    'Atualizando o Melhorias Enshrouded…': ('Updating Melhorias Enshrouded…', 'Actualizando Melhorias Enshrouded…'),
    'Baixando a versão {v}…': ('Downloading version {v}…', 'Descargando la versión {v}…'),
    'Instalando…': ('Installing…', 'Instalando…'),
}
