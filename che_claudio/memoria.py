"""Lo que Claudio sabe de quien lo usa: archivos markdown en `memoria/`.

- sobre_mi.md y los que agregue el usuario: lo que él quiere que sepa.
- recuerdos.md: datos que Claudio va guardando de lo que le cuentan.
- charlas.md: las últimas cosas que se dijeron, para retomar el hilo otro día.
"""
import re
from datetime import date, datetime

from .config import RAIZ

CARPETA = RAIZ / "memoria"
_RECUERDOS = CARPETA / "recuerdos.md"
_CHARLAS = CARPETA / "charlas.md"
_REPASADO = CARPETA / "repasado.txt"  # la última charla que ya se repasó para sacar recuerdos
_MAXIMO = 16_000  # caracteres de memoria que entran en las instrucciones del cerebro
_CHARLAS_GUARDADAS = 80  # intercambios; los más viejos se van borrando
# Cuando Claudio contestó mirando la pantalla o internet, su respuesta repite texto ajeno.
_DE_AFUERA = "Claudio (leyendo la pantalla o internet)"


def _leer(archivo) -> str:
    """El contenido sin los comentarios <!-- ... -->, que son ayuda para quien edita el archivo."""
    if not archivo.exists():
        return ""
    return re.sub(r"<!--.*?-->", "", archivo.read_text(encoding="utf-8"), flags=re.S).strip()


def cargar() -> str:
    """Todo lo recordado, como un solo texto: primero lo fijo, al final lo más reciente."""
    propios = sorted(a for a in CARPETA.glob("*.md") if a not in (_RECUERDOS, _CHARLAS))
    partes = []
    for archivo in [*propios, _RECUERDOS]:
        contenido = _leer(archivo)
        if contenido:
            partes.append(f"## {archivo.stem}\n{contenido}")
    texto = "\n\n".join(partes)
    if len(texto) > _MAXIMO:
        texto = "(...)\n" + texto[-_MAXIMO:]  # si crece demasiado se conserva lo más nuevo
    if _CHARLAS.exists():
        charlas = para_repasar(_CHARLAS.read_text(encoding="utf-8").strip().splitlines())
        texto += "\n\n## Últimas charlas (de más vieja a más nueva)\n" + "\n".join(charlas)
    return texto


def recuerdos() -> str:
    return _leer(_RECUERDOS)


def recordar(dato: str) -> None:
    CARPETA.mkdir(exist_ok=True)
    with open(_RECUERDOS, "a", encoding="utf-8") as archivo:
        archivo.write(f"- {date.today().isoformat()}: {' '.join(dato.split())}\n")


def anotar_charla(dicho: str, respuesta: str, de_afuera: bool = False) -> None:
    """Guarda un intercambio, en una línea, y descarta los más viejos.

    de_afuera: para responder miró la pantalla o buscó en internet.
    """
    CARPETA.mkdir(exist_ok=True)
    lineas = _CHARLAS.read_text(encoding="utf-8").splitlines() if _CHARLAS.exists() else []
    respuesta = " ".join(respuesta.split())
    recorte = respuesta if len(respuesta) <= 300 else respuesta[:300] + "..."
    quien = _DE_AFUERA if de_afuera else "Claudio"
    lineas.append(f"- {datetime.now():%d/%m %H:%M} | Persona: {' '.join(dicho.split())} | {quien}: {recorte}")
    _CHARLAS.write_text("\n".join(lineas[-_CHARLAS_GUARDADAS:]) + "\n", encoding="utf-8")


# --- Repaso: sacar recuerdos de lo conversado ---------------------------------

def charlas_sin_repasar() -> list[str]:
    """Los intercambios posteriores al último repaso."""
    if not _CHARLAS.exists():
        return []
    lineas = [linea for linea in _CHARLAS.read_text(encoding="utf-8").splitlines() if linea.startswith("- ")]
    ultima = _REPASADO.read_text(encoding="utf-8").strip() if _REPASADO.exists() else ""
    if ultima in lineas:
        lineas = lineas[len(lineas) - lineas[::-1].index(ultima):]
    return lineas


def para_repasar(lineas: list[str]) -> list[str]:
    """Las charlas como se le muestran a Claude (al conversar y al repasarlas): sin lo que Claudio leyó de
    la pantalla o de internet, que no lo dijo la persona y puede traer instrucciones ajenas."""
    return [linea.split(f" | {_DE_AFUERA}:")[0] + " | Claudio: (contó lo que vio en la pantalla o en internet)"
            if f" | {_DE_AFUERA}:" in linea else linea for linea in lineas]


def marcar_repasadas(lineas: list[str]) -> None:
    if lineas:
        _REPASADO.write_text(lineas[-1] + "\n", encoding="utf-8")
