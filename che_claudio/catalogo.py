"""Qué abrir cuando se pide algo por nombre: apps y sitios de config.json, o apps instaladas."""
import json
import logging
import re
import subprocess
import threading
from dataclasses import dataclass

from .texto import mejor_coincidencia, normalizar

registro = logging.getLogger("che_claudio")

_NO_LANZAR = ("uninstall", "desinstalar", "readme", "license", "documentation", "release notes")
_DOMINIO = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")


@dataclass
class Destino:
    nombre: str  # para decirlo en voz alta
    comando: str  # URL, ejecutable o URI
    es_sitio: bool = False


class Catalogo:
    def __init__(self, sitios: dict, apps: dict):
        self._sitios = sitios
        self._apps = apps
        self._instaladas: dict[str, tuple[str, str]] = {}  # norma -> (nombre, AppID)
        self._carga = threading.Thread(target=self._cargar_instaladas, daemon=True)
        self._carga.start()

    def _cargar_instaladas(self) -> None:
        """Lee el menú Inicio: cubre apps comunes y de la Store."""
        comando = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"
        try:
            salida = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", comando],
                capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW,
            ).stdout.decode("utf-8", "replace")
            apps = json.loads(salida)
        except (OSError, subprocess.SubprocessError, ValueError):
            registro.warning("No pude leer las apps del menú Inicio")
            return
        for app in apps if isinstance(apps, list) else [apps]:
            nombre, app_id = app.get("Name") or "", app.get("AppID") or ""
            norma = normalizar(nombre)
            if norma and app_id and not any(palabra in norma for palabra in _NO_LANZAR):
                self._instaladas.setdefault(norma, (nombre, app_id))

    def _instalada(self, norma: str) -> Destino:
        nombre, app_id = self._instaladas[norma]
        return Destino(nombre, "shell:AppsFolder\\" + app_id)

    def parecidos(self, texto: str, cantidad: int = 15) -> list[str]:
        """Nombres de programas instalados que contienen alguna palabra del texto."""
        self._carga.join(timeout=8)
        palabras = [p for p in normalizar(texto).split() if len(p) > 2]
        hallados = [nombre for norma, (nombre, _) in self._instaladas.items() if any(p in norma for p in palabras)]
        # Primero los que contienen más palabras de las pedidas.
        hallados.sort(key=lambda nombre: -sum(p in normalizar(nombre) for p in palabras))
        return hallados[:cantidad]

    def resolver(self, pedido: str) -> Destino | None:
        """Busca de lo más seguro a lo más aproximado."""
        self._carga.join(timeout=8)
        norma = normalizar(pedido)
        if not norma:
            return None
        if norma in self._apps:
            return Destino(pedido, self._apps[norma])
        if norma in self._instaladas:
            return self._instalada(norma)
        if norma in self._sitios:
            return Destino(pedido, self._sitios[norma], es_sitio=True)

        # El reconocedor a veces escribe distinto: "spotifai", "yutub".
        parecida = mejor_coincidencia(norma, list(self._apps) + list(self._sitios), minimo=0.82)
        if parecida in self._apps:
            return Destino(parecida, self._apps[parecida])
        if parecida:
            return Destino(parecida, self._sitios[parecida], es_sitio=True)

        # "code" -> "Visual Studio Code", "docker" -> "Docker Desktop".
        pedidas = set(norma.split())
        contienen = [n for n in self._instaladas if pedidas <= set(re.split(r"[^a-z0-9]+", n))]
        if contienen:
            return self._instalada(min(contienen, key=len))
        parecida = mejor_coincidencia(norma, self._instaladas, minimo=0.8)
        if parecida:
            return self._instalada(parecida)

        dominio = norma.replace(" punto ", ".").replace(" ", "")
        if _DOMINIO.match(dominio):
            return Destino(dominio, "https://" + dominio, es_sitio=True)
        return None
