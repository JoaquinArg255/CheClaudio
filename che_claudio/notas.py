"""Notas en el Bloc de notas: lo que dictás o escribe Claudio.

Cada nota es un archivo propio en Documentos\\Notas de Claudio, así nada se
pierde y nunca se escribe sobre pestañas que ya tenías abiertas. Para que la
ventana muestre lo agregado sin pedir el foco, se le manda el texto a su
control de edición, pero solo si su título es el de esta nota.
"""
import ctypes
import re
import time
from datetime import datetime
from pathlib import Path

import win32con
import win32gui
from win32com.shell import shell, shellcon

from .sistema import lanzador, ventanas

_RECIENTE = 30 * 60  # "escribí también..." se suma a la última nota si es de hace menos de esto
_EDITORES = ("RichEditD2DPT", "Edit")  # el del Bloc de notas nuevo y el del clásico


def carpeta() -> Path:
    destino = Path(shell.SHGetKnownFolderPath(shellcon.FOLDERID_Documents, 0, None)) / "Notas de Claudio"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _titulo(texto: str) -> str:
    """Las primeras palabras, sin caracteres que Windows no acepta en un nombre de archivo."""
    palabras = re.sub(r'[\\/:*?"<>|\r\n]+', " ", texto).split()
    titulo = " ".join(palabras[:6])
    return titulo[:40].strip(" .") or "Nota"


_PENDIENTES = "Cosas que Claudio todavía no sabe hacer.txt"


def ultima_reciente() -> Path | None:
    notas = sorted((p for p in carpeta().glob("*.txt") if p.name != _PENDIENTES),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if notas and time.time() - notas[0].stat().st_mtime < _RECIENTE:
        return notas[0]
    return None


def nueva(texto: str) -> Path:
    ruta = carpeta() / f"{datetime.now():%Y-%m-%d %H.%M} {_titulo(texto)}.txt"
    ruta.write_text(texto.rstrip() + "\n", encoding="utf-8")
    return ruta


def agregar(ruta: Path, texto: str) -> None:
    with open(ruta, "a", encoding="utf-8") as archivo:
        archivo.write(texto.rstrip() + "\n")


def quitar_ultima_linea(ruta: Path) -> str | None:
    """Borra la última línea escrita. Devuelve lo que borró, o None si la nota estaba vacía."""
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    while lineas and not lineas[-1].strip():
        lineas.pop()
    if not lineas:
        return None
    borrada = lineas.pop()
    ruta.write_text("\n".join(lineas) + ("\n" if lineas else ""), encoding="utf-8")
    return borrada


def anotar_pendiente(pedido: str) -> Path:
    """Suma a la lista de cosas que se le pidieron a Claudio y todavía no sabe hacer."""
    ruta = carpeta() / _PENDIENTES
    with open(ruta, "a", encoding="utf-8") as archivo:
        archivo.write(f"{datetime.now():%d/%m/%Y %H:%M}  {pedido.strip()}\n")
    return ruta


def abrir(ruta: Path, mostrar: bool) -> bool:
    return lanzador.abrir("notepad.exe", f'"{ruta}"', mostrar=mostrar, nombre=ruta.stem)


def refrescar_vista(ruta: Path) -> bool:
    """Si la nota está a la vista en un Bloc de notas, le pone el contenido actual. True si pudo."""
    contenido = ruta.read_text(encoding="utf-8")
    for hwnd in ventanas.ventanas_de("notepad.exe"):
        # El título es el de la pestaña activa: si no es esta nota, no se toca nada.
        if not ventanas.titulo(hwnd).startswith(ruta.name):
            continue
        editores = []
        win32gui.EnumChildWindows(
            hwnd, lambda h, _: editores.append(h) if win32gui.GetClassName(h) in _EDITORES else None, None)
        for editor in editores:
            if win32gui.IsWindowVisible(editor):
                ctypes.windll.user32.SendMessageW(editor, win32con.WM_SETTEXT, 0, ctypes.c_wchar_p(contenido))
                return True
    return False
