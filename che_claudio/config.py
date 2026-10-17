"""Carga de la configuración.

config.example.json tiene todos los valores por defecto (es el único lugar donde están); config.json,
personal y fuera del repo, cambia los que quiera; preferencias.json guarda lo que se ajusta hablando.
"""
import json
from pathlib import Path

from .texto import normalizar

RAIZ = Path(__file__).resolve().parent.parent
# Lo que se genera al usarlo (registro, sesiones, recordatorios, voces...): es de cada uno y no va al repo.
DATOS = RAIZ / "datos"
EJEMPLO = RAIZ / "config.example.json"
ARCHIVO = RAIZ / "config.json"
# Lo que se ajusta por voz ("hablá más bajo") se guarda aparte para no reescribir config.json.
PREFERENCIAS = DATOS / "preferencias.json"


def _mezclar(config: dict, propio: dict) -> None:
    for clave, valor in propio.items():
        # En las secciones (cerebro, avatar) lo que no se escribió conserva su valor por defecto.
        seccion = isinstance(valor, dict) and clave not in ("sitios", "apps", "proyectos", "correcciones")
        config[clave] = {**config.get(clave, {}), **valor} if seccion else valor


def cargar(ruta: Path = ARCHIVO) -> dict:
    config = json.loads(EJEMPLO.read_text(encoding="utf-8"))
    for archivo in (ruta, PREFERENCIAS):
        if archivo.exists():
            with open(archivo, encoding="utf-8") as abierto:
                _mezclar(config, json.load(abierto))
    config["nombres"] = [normalizar(n) for n in config["nombres"]]
    # Las claves se comparan contra texto hablado ya normalizado.
    config["sitios"] = {normalizar(k): v for k, v in config["sitios"].items()}
    config["apps"] = {normalizar(k): v for k, v in config["apps"].items()}
    return config


def guardar_preferencia(clave: str, valor) -> None:
    preferencias = {}
    if PREFERENCIAS.exists():
        preferencias = json.loads(PREFERENCIAS.read_text(encoding="utf-8"))
    preferencias[clave] = valor
    PREFERENCIAS.parent.mkdir(parents=True, exist_ok=True)
    PREFERENCIAS.write_text(json.dumps(preferencias, ensure_ascii=False, indent=2), encoding="utf-8")
