"""Abre programas, páginas y archivos sin sacarle el foco a lo que se está usando.

Al abrir en segundo plano se bloquea por unos segundos el cambio de ventana activa
y un hilo vigila lo que aparece: las ventanas nuevas de lo que se abrió quedan
minimizadas y, si alguna alcanzó a ponerse al frente, se vuelve a la anterior.
"""
import logging
import os
import re
import threading
import time
import winreg

import pywintypes
import win32api
import win32con

from . import ventanas
from ..texto import normalizar

registro = logging.getLogger("che_claudio")

NAVEGADORES = {"brave.exe", "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "vivaldi.exe"}

# Cómo se nombran al hablar -> nombre del ejecutable.
_PROGRAMAS = {
    "edge": "msedge", "microsoft edge": "msedge", "google chrome": "chrome", "word": "winword",
    "power point": "powerpnt", "powerpoint": "powerpnt", "visual studio code": "code", "vs code": "code",
    "bloc de notas": "notepad", "notas": "notepad", "adobe": "acrobat", "acrobat reader": "acrobat",
}

_ESPERA_PRIMERA_VENTANA = 6.0
_ESPERA_ENTRE_VENTANAS = 3.0
_ESPERA_MAXIMA = 15.0


def _leer_registro(raiz, clave: str, valor: str = "") -> str | None:
    try:
        with winreg.OpenKey(raiz, clave) as abierta:
            return winreg.QueryValueEx(abierta, valor)[0]
    except OSError:
        return None


def programa(nombre: str) -> str | None:
    """Ruta del ejecutable de un programa nombrado al hablar ("brave", "word"), si está instalado."""
    norma = normalizar(nombre)
    exe = _PROGRAMAS.get(norma, norma.replace(" ", "")) + ".exe"
    clave = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
    ruta = _leer_registro(winreg.HKEY_CURRENT_USER, clave) or _leer_registro(winreg.HKEY_LOCAL_MACHINE, clave)
    return ruta.strip('"') if ruta and os.path.exists(ruta.strip('"')) else None


def navegador_predeterminado() -> str | None:
    identificador = _leer_registro(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice", "ProgId")
    comando = identificador and _leer_registro(winreg.HKEY_CLASSES_ROOT, rf"{identificador}\shell\open\command")
    ruta = re.match(r'"([^"]+)"|(\S+)', comando or "")
    ruta = ruta and (ruta.group(1) or ruta.group(2))
    return ruta if ruta and os.path.exists(ruta) else None


def _es_de_lo_abierto(hwnd: int, desde: float, nombre: str) -> bool:
    """¿Esta ventana nueva es de lo que se acaba de abrir, o de otra cosa que justo apareció?"""
    return ventanas.inicio_del_proceso(hwnd) >= desde - 1 or _se_llama(hwnd, nombre)


def _se_llama(hwnd: int, nombre: str) -> bool:
    """¿La ventana es del programa nombrado? Mira el ejecutable y el título."""
    if not nombre:
        return False
    proceso = ventanas.exe_de(hwnd).removesuffix(".exe")
    compacto = nombre.replace(" ", "")
    return bool(proceso) and (proceso in compacto or compacto in proceso) or nombre in normalizar(ventanas.titulo(hwnd))


def _mandar_al_fondo(hwnd: int, previa: int) -> None:
    era_la_activa = ventanas.ventana_activa() == hwnd
    ventanas.minimizar(hwnd)
    if era_la_activa:
        time.sleep(0.1)
        if ventanas.ventana_activa() != previa:
            ventanas.traer_al_frente(previa)
            # Traer al frente destraba el foco: se vuelve a trabar.
            ventanas.bloquear_foco()
            ventanas.desbloquear_foco()


def _vigilar(previa: int, conocidas: set, minimizadas: set, desde: float, nombre: str, mostrar: bool) -> None:
    inicio = time.monotonic()
    ultima = None  # cuándo apareció la última ventana de lo que se abrió
    try:
        while time.monotonic() - inicio < _ESPERA_MAXIMA:
            time.sleep(0.05)
            ahora = time.monotonic()
            activa = ventanas.ventana_activa()
            if activa in conocidas:
                previa = activa  # el usuario cambió de ventana por su cuenta
            for hwnd in set(ventanas.ventanas_visibles()) - conocidas:
                conocidas.add(hwnd)
                if not _es_de_lo_abierto(hwnd, desde, nombre):
                    continue
                if mostrar:
                    ventanas.traer_al_frente(hwnd)
                    return
                _mandar_al_fondo(hwnd, previa)
                ultima = ahora
            if mostrar and ahora - inicio > 1.0:
                # No apareció nada nuevo: ya estaba abierto (quizás minimizado o tapado). Se trae esa ventana.
                existente = next((h for h in ventanas.ventanas_de_programas() if _se_llama(h, nombre)), None)
                if existente:
                    ventanas.traer_al_frente(existente)
                    return
            # Una página nueva puede restaurar un navegador que estaba minimizado.
            if not mostrar and ahora - inicio < 2.5:
                for hwnd in [h for h in minimizadas if not ventanas.esta_minimizada(h)]:
                    minimizadas.discard(hwnd)
                    if _es_de_lo_abierto(hwnd, desde, nombre):
                        _mandar_al_fondo(hwnd, previa)
            if ultima is None and ahora - inicio > _ESPERA_PRIMERA_VENTANA:
                return
            if ultima is not None and ahora - ultima > _ESPERA_ENTRE_VENTANAS:
                return
    finally:
        if not mostrar:
            ventanas.desbloquear_foco()


def abrir(comando: str, parametros: str | None = None, *, mostrar: bool, nombre: str = "") -> bool:
    """Abre un programa, archivo o URI. `nombre` ayuda a reconocer sus ventanas."""
    previa = ventanas.ventana_activa()
    conocidas = set(ventanas.ventanas_visibles())
    minimizadas = {h for h in conocidas if ventanas.esta_minimizada(h)}
    desde = time.time()
    if not mostrar:
        ventanas.bloquear_foco()
    try:
        win32api.ShellExecute(0, "open", comando, parametros, None,
                              win32con.SW_SHOWNORMAL if mostrar else win32con.SW_SHOWMINNOACTIVE)
    except pywintypes.error:
        registro.exception("No pude abrir %s", comando)
        if not mostrar:
            ventanas.desbloquear_foco()
        return False
    threading.Thread(target=_vigilar, args=(previa, conocidas, minimizadas, desde, normalizar(nombre), mostrar)).start()
    return True


def abrir_url(url: str, *, mostrar: bool, navegador: str | None = None) -> bool:
    """Abre una página (o un archivo local) en el navegador indicado o en el predeterminado."""
    elegido = navegador or navegador_predeterminado()
    ejecutable = os.path.basename(elegido).lower() if elegido else ""
    nombre = ejecutable.removesuffix(".exe")
    # Siempre como pestaña nueva en la ventana del navegador que ya está abierta.
    if elegido:
        return abrir(elegido, f'"{url}"', mostrar=mostrar, nombre=nombre)
    return abrir(url, mostrar=mostrar, nombre=nombre)
