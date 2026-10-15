"""Búsqueda de archivos y carpetas por nombre aproximado, como se los nombra al hablar."""
import os
import re
import time
from pathlib import Path

from win32com.shell import shell, shellcon

from .texto import normalizar, parecido

FORMATOS = {
    "pdf": (".pdf",),
    "word": (".docx", ".doc"),
    "excel": (".xlsx", ".xls", ".csv"),
    "powerpoint": (".pptx", ".ppt"),
}

_CONOCIDAS = {
    "escritorio": shellcon.FOLDERID_Desktop,
    "descargas": shellcon.FOLDERID_Downloads,
    "documentos": shellcon.FOLDERID_Documents,
    "imagenes": shellcon.FOLDERID_Pictures,
    "fotos": shellcon.FOLDERID_Pictures,
    "musica": shellcon.FOLDERID_Music,
    "videos": shellcon.FOLDERID_Videos,
}

# Carpetas enormes o de sistema donde no vale la pena buscar documentos.
_IGNORAR = {
    "appdata", "node_modules", "__pycache__", "site-packages", "venv", "env", "dist", "build", "target",
    "windows", "program files", "program files (x86)", "programdata", "$recycle.bin",
}
_VACIAS = {"de", "del", "la", "el", "los", "las", "y", "en", "para", "mi", "mis", "un", "una", "al", "con"}
_NUMEROS = {
    "uno": "1", "primer": "1", "primero": "1", "dos": "2", "segundo": "2", "tres": "3", "tercer": "3",
    "cuatro": "4", "cinco": "5", "seis": "6", "siete": "7", "ocho": "8", "nueve": "9", "diez": "10",
}

_PROFUNDIDAD = 8
_TIEMPO_MAXIMO = 12.0


def _terminos(texto: str) -> list[str]:
    """Palabras significativas: sin tildes, sin conectores y con los números en cifras."""
    palabras = re.split(r"[^a-z0-9]+", normalizar(texto))
    return [_NUMEROS.get(p, p) for p in palabras if p and p not in _VACIAS]


def _parecido_termino(buscado: str, candidato: str) -> float:
    if buscado == candidato:
        return 1.0
    if len(buscado) >= 3 and len(candidato) >= 3 and (candidato.startswith(buscado) or buscado.startswith(candidato)):
        return 0.9
    return parecido(buscado, candidato)


def _puntaje(buscados: list[str], nombre: str) -> float:
    """Qué tan bien coincide un nombre con lo buscado (0 = no coincide)."""
    presentes = _terminos(nombre)
    if not presentes:
        return 0.0
    # "cancha libre" dicho en dos palabras para algo escrito "CanchaLibre".
    pegado = "".join(buscados)
    if len(buscados) > 1 and max(parecido(pegado, p) for p in presentes) >= 0.85:
        return 0.95
    mejores =[max(_parecido_termino(b, p) for p in presentes) for b in buscados]
    flojos = sum(1 for m in mejores if m < 0.75)
    # Al dictar un nombre largo se tolera una palabra mal entendida.
    if flojos > (1 if len(buscados) >= 3 else 0):
        return 0.0
    return sum(mejores) / len(mejores)


def _recorrer(raiz: Path, profundidad: int = _PROFUNDIDAD):
    """Entradas (archivos y carpetas) bajo `raiz`, salteando lo oculto y lo pesado."""
    limite = time.monotonic() + _TIEMPO_MAXIMO
    pendientes = [(str(raiz), 0)]
    while pendientes and time.monotonic() < limite:
        carpeta, nivel = pendientes.pop()
        try:
            entradas = list(os.scandir(carpeta))
        except OSError:
            continue
        for entrada in entradas:
            nombre = entrada.name.lower()
            if nombre.startswith((".", "~$")):
                continue
            try:
                es_carpeta = entrada.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if es_carpeta:
                if nombre in _IGNORAR:
                    continue
                if nivel < profundidad:
                    pendientes.append((entrada.path, nivel + 1))
            yield entrada, es_carpeta, nivel


def resolver_carpeta(pedido: str) -> Path | None:
    """"descargas", "seminario", "trabajos de la facu" -> la carpeta del usuario que mejor coincide."""
    buscados = _terminos(pedido)
    if not buscados:
        return None
    if len(buscados) == 1 and buscados[0] in _CONOCIDAS:
        return Path(shell.SHGetKnownFolderPath(_CONOCIDAS[buscados[0]], 0, None))
    mejor, clave = None, None
    for entrada, es_carpeta, nivel in _recorrer(Path.home(), profundidad=5):
        if not es_carpeta:
            continue
        puntaje = _puntaje(buscados, entrada.name)
        if puntaje >= 0.8:
            sobrantes = len(_terminos(entrada.name)) - len(buscados)
            candidata = (-puntaje, sobrantes, nivel)
            if clave is None or candidata < clave:
                mejor, clave = Path(entrada.path), candidata
    return mejor


def separar_carpeta(pedido: str) -> tuple[Path, str] | None:
    """"seminario resumen parcial" -> (carpeta Seminario, "resumen parcial").

    Para cuando se dijo todo de corrido: prueba del tramo más largo al más corto.
    """
    palabras = pedido.split()
    for corte in range(len(palabras), 0, -1):
        carpeta = resolver_carpeta(" ".join(palabras[:corte]))
        if carpeta:
            return carpeta, " ".join(palabras[corte:])
    return None


def buscar(nombre: str, carpeta: Path | None = None, formato: str | None = None, cantidad: int = 5) -> list[Path]:
    """Archivos cuyo nombre coincide con lo dicho, del mejor al peor.

    Sin nombre devuelve los más recientes de ese formato.
    """
    buscados = _terminos(nombre)
    extensiones = FORMATOS.get(formato or "")
    candidatos = []
    for entrada, es_carpeta, _ in _recorrer(carpeta or Path.home()):
        if es_carpeta:
            continue
        base, extension = os.path.splitext(entrada.name)
        if extensiones and extension.lower() not in extensiones:
            continue
        puntaje = _puntaje(buscados, base) if buscados else 1.0
        if puntaje < 0.72:
            continue
        try:
            modificado = entrada.stat().st_mtime
        except OSError:
            continue
        sobrantes = len(_terminos(base)) - len(buscados) if buscados else 0
        candidatos.append((-round(puntaje, 2), sobrantes, -modificado, entrada.path))
    return [Path(ruta) for *_, ruta in sorted(candidatos)[:cantidad]]
