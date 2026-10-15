"""Proyectos de programación: "levantá cancha libre" arranca sus servicios y abre la página.

Se definen en config.json ("proyectos"). Cada paso corre oculto, sin ventana que
moleste, y deja lo que imprime en proyectos/<proyecto>/<paso>.log. Lo que queda
corriendo se anota en proyectos/activos.json, así se puede bajar aunque Claudio
se haya reiniciado en el medio.
"""
import json
import logging
import re
import socket
import subprocess
import threading
import time
from pathlib import Path

from .config import RAIZ
from .texto import mejor_coincidencia, normalizar

registro = logging.getLogger("che_claudio")

_CARPETA = RAIZ / "proyectos"
_ACTIVOS = _CARPETA / "activos.json"
_ESPERA_PASO = 180  # segundos para un paso que tiene que terminar (por ejemplo, levantar la base)
_ESPERA_PUERTO = 240  # segundos para que un servicio empiece a responder


def _responde(puerto: int) -> bool:
    try:
        with socket.create_connection(("localhost", puerto), timeout=0.5):
            return True
    except OSError:
        return False


def _nombre_de_archivo(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", normalizar(texto)).strip("_") or "paso"


class Proyectos:
    def __init__(self, definidos: dict, avisar, abrir_pagina):
        """`avisar(texto)` cuenta cómo terminó; `abrir_pagina(url, mostrar)` abre la página del proyecto."""
        self._definidos = {normalizar(nombre): definicion for nombre, definicion in (definidos or {}).items()}
        self._avisar = avisar
        self._abrir_pagina = abrir_pagina
        self._levantando: set[str] = set()

    def nombres(self) -> list[str]:
        return list(self._definidos)

    def pasos(self, nombre: str) -> list[str]:
        return [paso.get("nombre", "paso") for paso in self._definidos[nombre].get("pasos", [])]

    def resolver(self, pedido: str) -> str | None:
        norma = normalizar(pedido)
        if norma in self._definidos:
            return norma
        contienen = [n for n in self._definidos if set(n.split()) <= set(norma.split())]
        return contienen[0] if contienen else mejor_coincidencia(norma, self._definidos, minimo=0.7)

    # --- Lo que está corriendo -------------------------------------------------

    @staticmethod
    def _activos() -> dict:
        try:
            return json.loads(_ACTIVOS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _guardar(activos: dict) -> None:
        _CARPETA.mkdir(exist_ok=True)
        _ACTIVOS.write_text(json.dumps(activos, ensure_ascii=False, indent=2), encoding="utf-8")

    def estado(self, nombre: str) -> str:
        pasos = self._definidos[nombre].get("pasos", [])
        partes = [f"{paso.get('nombre', 'paso')} {'responde' if _responde(paso['puerto']) else 'no responde'}"
                  for paso in pasos if paso.get("puerto")]
        return f"{nombre}: " + (", ".join(partes) if partes else "no tiene servicios para revisar")

    # --- Levantar --------------------------------------------------------------

    def levantar(self, nombre: str, mostrar: bool) -> str:
        """Arranca en otro hilo (puede tardar más de un minuto). Devuelve qué decir mientras tanto."""
        if nombre in self._levantando:
            return f"Ya estoy levantando {nombre}, te aviso cuando esté"
        self._levantando.add(nombre)
        threading.Thread(target=self._levantar, args=(nombre, mostrar), daemon=True, name="proyecto").start()
        return f"Levantando {nombre}, te aviso cuando esté listo"

    def _levantar(self, nombre: str, mostrar: bool) -> None:
        try:
            self._avisar(self._arrancar(nombre, mostrar))
        except Exception:
            registro.exception("Falló levantar %s", nombre)
            self._avisar(f"Algo salió mal levantando {nombre}")
        finally:
            self._levantando.discard(nombre)

    def _arrancar(self, nombre: str, mostrar: bool) -> str:
        definicion = self._definidos[nombre]
        raiz = Path(definicion.get("carpeta", "."))
        if not raiz.exists():
            return f"No encontré la carpeta de {nombre}"
        salidas = _CARPETA / _nombre_de_archivo(nombre)
        salidas.mkdir(parents=True, exist_ok=True)
        lanzados, esperando = [], []
        for paso in definicion.get("pasos", []):
            titulo, puerto = paso.get("nombre", "paso"), paso.get("puerto")
            if puerto and _responde(puerto):
                registro.info("Proyecto %s: %s ya estaba levantado", nombre, titulo)
                continue
            archivo = salidas / f"{_nombre_de_archivo(titulo)}.log"
            with open(archivo, "w", encoding="utf-8", errors="replace") as salida:  # el proceso se queda con su copia
                proceso = subprocess.Popen(paso["comando"], cwd=raiz / paso.get("carpeta", ""), shell=True,
                                           stdout=salida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
            registro.info("Proyecto %s: arranqué %s (%s)", nombre, titulo, paso["comando"])
            if paso.get("esperar"):
                try:
                    codigo = proceso.wait(_ESPERA_PASO)
                except subprocess.TimeoutExpired:
                    proceso.kill()
                    codigo = -1
                if codigo != 0:
                    registro.warning("Proyecto %s: falló %s, ver %s", nombre, titulo, archivo)
                    return f"No pude levantar {nombre}: falló el paso {titulo}. El detalle quedó en el registro del proyecto"
                continue
            lanzados.append({"paso": titulo, "pid": proceso.pid})
            if puerto:
                esperando.append((titulo, puerto, proceso))
        if lanzados:
            activos = self._activos()
            activos[nombre] = activos.get(nombre, []) + lanzados
            self._guardar(activos)

        limite = time.monotonic() + definicion.get("espera", _ESPERA_PUERTO)
        while esperando:
            for titulo, puerto, proceso in list(esperando):
                if _responde(puerto):
                    esperando.remove((titulo, puerto, proceso))
                elif proceso.poll() is not None:
                    return f"No pude levantar {nombre}: {titulo} se cerró solo. El detalle quedó en el registro del proyecto"
            if esperando and time.monotonic() > limite:
                return f"{nombre} está tardando demasiado: {esperando[0][0]} todavía no responde"
            time.sleep(1)
        pagina = definicion.get("abrir")
        if pagina:
            self._abrir_pagina(pagina, mostrar)
        return f"Listo, {nombre} ya está levantado" + (" y te dejé la página abierta" if pagina else "")

    # --- Bajar -----------------------------------------------------------------

    def bajar(self, nombre: str) -> str:
        activos = self._activos()
        lanzados = activos.pop(nombre, [])
        for lanzado in lanzados:
            subprocess.run(["taskkill", "/PID", str(lanzado["pid"]), "/T", "/F"], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        self._guardar(activos)
        definicion = self._definidos[nombre]
        raiz = Path(definicion.get("carpeta", "."))
        for paso in definicion.get("pasos", []):
            if paso.get("al_bajar"):
                subprocess.run(paso["al_bajar"], cwd=raiz / paso.get("carpeta", ""), shell=True, capture_output=True,
                               timeout=_ESPERA_PASO, creationflags=subprocess.CREATE_NO_WINDOW)
        if lanzados:
            time.sleep(1.5)  # que los puertos terminen de liberarse antes de mirar qué quedó
        siguen = [paso.get("nombre", "paso") for paso in definicion.get("pasos", [])
                  if paso.get("puerto") and _responde(paso["puerto"])]
        if siguen:
            # Lo arrancó otro (una terminal, el editor): no es de Claudio y no lo toca.
            return f"Bajé lo que yo había levantado de {nombre}, pero sigue corriendo {', '.join(siguen)}: no lo arranqué yo"
        return f"Listo, bajé {nombre}" if lanzados else f"No tenía nada levantado de {nombre}"
