"""Recordatorios: "avisame a las 6 y media que tengo que salir".

Se guardan en recordatorios.json, así sobreviven si el asistente se reinicia.
Si cuando llegaba la hora el asistente estaba apagado, avisa al arrancar.
"""
import json
import logging
import threading
import time
import winsound
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from .config import RAIZ
from .texto import normalizar

registro = logging.getLogger("che_claudio")

_ARCHIVO = RAIZ / "recordatorios.json"
_PERDIDOS_HASTA = timedelta(hours=12)  # más viejos que esto, ya no tiene sentido avisar


@dataclass
class Recordatorio:
    cuando: str  # ISO, hora local
    mensaje: str

    @property
    def momento(self) -> datetime:
        return datetime.fromisoformat(self.cuando)


def describir_hora(momento: datetime, ahora: datetime | None = None) -> str:
    """"a las 18:30", "mañana a las 8:00", "el 5/10 a las 9:00"."""
    ahora = ahora or datetime.now()
    hora = f"{momento.hour}:{momento.minute:02d}"
    dias = (momento.date() - ahora.date()).days
    if dias == 0:
        return f"a las {hora}"
    if dias == 1:
        return f"mañana a las {hora}"
    return f"el {momento.day}/{momento.month} a las {hora}"


class Recordatorios:
    def __init__(self, avisar, vigilar: bool = True):
        """`avisar(texto)` se llama cuando llega la hora (normalmente, decirlo en voz alta).

        vigilar: solo el asistente que escucha avisa; una orden escrita (--texto) solo agenda,
        y el que escucha lo toma porque relee el archivo cuando cambia.
        """
        self._avisar = avisar
        self._candado = threading.Lock()
        self._leido = 0.0
        self._lista: list[Recordatorio] = self._cargar()
        if vigilar:
            threading.Thread(target=self._vigilar, daemon=True, name="recordatorios").start()

    def _modificado(self) -> float:
        try:
            return _ARCHIVO.stat().st_mtime
        except OSError:
            return 0.0

    def _cargar(self) -> list[Recordatorio]:
        self._leido = self._modificado()
        try:
            return [Recordatorio(**r) for r in json.loads(_ARCHIVO.read_text(encoding="utf-8"))]
        except (OSError, ValueError, TypeError):
            return []

    def _guardar(self) -> None:
        datos = [asdict(r) for r in sorted(self._lista, key=lambda r: r.cuando)]
        _ARCHIVO.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        self._leido = self._modificado()

    def agregar(self, cuando: datetime, mensaje: str) -> Recordatorio:
        recordatorio = Recordatorio(cuando.replace(microsecond=0).isoformat(), mensaje.strip())
        with self._candado:
            if self._modificado() != self._leido:
                self._lista = self._cargar()
            self._lista.append(recordatorio)
            self._guardar()
        registro.info("Recordatorio %s: %s", describir_hora(cuando), recordatorio.mensaje)
        return recordatorio

    def pendientes(self) -> list[Recordatorio]:
        with self._candado:
            return sorted(self._lista, key=lambda r: r.cuando)

    def cancelar(self, pedido: str = "") -> list[Recordatorio]:
        """Cancela los que coinciden con el texto (o el próximo, si no se dice cuál)."""
        with self._candado:
            if not self._lista:
                return []
            palabras = [p for p in normalizar(pedido).split() if len(p) > 3]
            if palabras:
                cancelados = [r for r in self._lista if any(p in normalizar(r.mensaje) for p in palabras)]
            else:
                cancelados = [min(self._lista, key=lambda r: r.cuando)]
            self._lista = [r for r in self._lista if r not in cancelados]
            self._guardar()
            return cancelados

    def _vigilar(self) -> None:
        primera_vuelta = True
        while True:
            ahora = datetime.now()
            with self._candado:
                if self._modificado() != self._leido:  # otro proceso agregó o canceló alguno
                    self._lista = self._cargar()
                vencidos = [r for r in self._lista if r.momento <= ahora]
                if vencidos:
                    self._lista = [r for r in self._lista if r not in vencidos]
                    self._guardar()
            for recordatorio in vencidos:
                atraso = ahora - recordatorio.momento
                if atraso > _PERDIDOS_HASTA:
                    continue
                if primera_vuelta and atraso > timedelta(minutes=1):
                    texto = f"Mientras estaba apagado, tenías un aviso {describir_hora(recordatorio.momento, ahora)}: {recordatorio.mensaje}"
                else:
                    texto = f"Te aviso: {recordatorio.mensaje}"
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
                self._avisar(texto)
            primera_vuelta = False
            time.sleep(1)
