"""Normalización y comparación de texto hablado."""
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

_BORDES = " \t\n¿?¡!.,;:\"()[]…«»“”%"
_CORTES = ",.;:!?…"


@dataclass
class Palabra:
    original: str  # como se dijo, sin puntuación en los bordes
    norma: str  # minúsculas y sin tildes, para comparar
    corte: bool = False  # venía seguida de coma, punto, etc.
    bruto: str = ""  # tal cual vino, con su puntuación


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y con espacios simples."""
    texto = unicodedata.normalize("NFD", texto.lower().replace("’", "'"))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return " ".join(texto.split())


def tokenizar(texto: str) -> list[Palabra]:
    palabras: list[Palabra] = []
    for bruto in texto.replace("’", "'").split():
        limpio = bruto.strip(_BORDES)
        corte = bruto.rstrip("\"”»)")[-1:] in _CORTES
        if not limpio:
            if corte and palabras:
                palabras[-1].corte = True
            continue
        palabras.append(Palabra(limpio, normalizar(limpio), corte, bruto))
    return palabras


def unir(palabras: list[Palabra]) -> str:
    return " ".join(p.original for p in palabras)


def parecido(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def mejor_coincidencia(buscado: str, candidatos, minimo: float = 0.8):
    """Devuelve el candidato más parecido a `buscado` (ya normalizado), o None."""
    mejor, puntaje = None, minimo
    for candidato in candidatos:
        p = 1.0 if candidato == buscado else parecido(buscado, candidato)
        if p > puntaje or (p == puntaje and mejor is None):
            mejor, puntaje = candidato, p
    return mejor
