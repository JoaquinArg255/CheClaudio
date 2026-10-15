"""Carga de config.json (y de los ajustes que se cambian hablando, en preferencias.json)."""
import json
from pathlib import Path

from .texto import normalizar

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO = RAIZ / "config.json"
# Lo que se ajusta por voz ("hablá más bajo") se guarda aparte para no reescribir config.json.
PREFERENCIAS = RAIZ / "preferencias.json"

_PREDETERMINADO = {
    "nombres": ["claudio"],
    "modelo": "auto",
    "dispositivo": "auto",
    "microfono": None,
    "umbral_microfono": 0.008,
    "vocabulario": [],
    "correcciones": {},
    "responder_con_voz": True,
    "voz": "es_AR-daniela-high",
    "volumen_voz": 0.35,
    "segundo_plano": True,
    "traer_lo_ya_abierto": True,
    "segundos_atento": 2.5,
    "segundos_para_contestar": 7,
    "confirmar_mensajes": True,
    "reproductor": "spotify",
    "musica_a_gusto": None,
    "cerebro": {"activo": True, "modelo": "claude-haiku-5-5", "esfuerzo": "low", "modo": "hibrido",
                "razonar": False, "buscar_en_internet": True,
                "modelo_para_programar": "claude-sonnet-5-5"},
    "avisar_consultas": {"activo": True, "segundos_minimos": 45},
    "avatar": {"activo": True, "escala": 1.0},
    "no_cerrar": ["claude"],
    "sitios": {},
    "apps": {},
    "proyectos": {},
}


def _mezclar(config: dict, propio: dict) -> None:
    for clave, valor in propio.items():
        # En las secciones (cerebro, avatar) lo que no se escribió conserva su valor por defecto.
        seccion = isinstance(valor, dict) and clave not in ("sitios", "apps", "proyectos", "correcciones")
        config[clave] = {**config.get(clave, {}), **valor} if seccion else valor


def cargar(ruta: Path = ARCHIVO) -> dict:
    config = dict(_PREDETERMINADO)
    # config.json es personal y no se sube al repo: sin él se usa el de ejemplo.
    base = ruta if ruta.exists() else ruta.with_name("config.example.json")
    for archivo in (base, PREFERENCIAS):
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
    PREFERENCIAS.write_text(json.dumps(preferencias, ensure_ascii=False, indent=2), encoding="utf-8")
