"""Respuestas habladas.

Usa una voz neuronal de Piper, que corre en la PC (no manda el texto a ningún
servicio). Si no se puede cargar, cae a las voces clásicas de Windows.
"""
import logging
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from ..config import DATOS

registro = logging.getLogger("che_claudio")

CARPETA_VOCES = DATOS / "voces"
_ES_DE_PIPER = re.compile(r"^[a-z]{2}_[A-Z]{2}-.+-(x_low|low|medium|high)$")


_CUADROS = 30  # por segundo, para la animación de la boca


def _envolvente(audio: np.ndarray, frecuencia: int) -> list[float]:
    """Volumen de la voz por cuadro de animación, de 0 a 1."""
    muestras = max(1, frecuencia // _CUADROS)
    trozos = len(audio) // muestras
    if trozos == 0:
        return []
    niveles = np.sqrt(np.mean(audio[:trozos * muestras].astype(np.float32).reshape(trozos, muestras) ** 2, axis=1))
    maximo = float(niveles.max()) or 1.0
    return [min(1.0, float(n) / maximo * 1.3) for n in niveles]


def _envolvente_estimada(texto: str) -> list[float]:
    """Para cuando no se tiene el audio: una boca que se mueve lo que duraría decir el texto."""
    cuadros = int(max(1.0, len(texto) * 0.065) * _CUADROS)
    return [0.35 + 0.45 * abs(np.sin(i * 0.9)) for i in range(cuadros)]


_LARGO_TRAMO = 80  # caracteres por subtítulo: entre tres y cuatro renglones del cuadro


def tramos(texto: str) -> list[str]:
    """Corta lo que se va a decir en subtítulos cortos: por oración y, si hace falta, por comas."""
    resultado = []
    for oracion in re.split(r"(?<=[.!?…])\s+", texto.strip()):
        # Un poco de margen evita dejar colgada una palabra suelta en un subtítulo propio.
        while len(oracion) > _LARGO_TRAMO + 20:
            # Cortar en la última coma (o espacio) que deje el tramo dentro del largo.
            corte = max(oracion.rfind(", ", 0, _LARGO_TRAMO), oracion.rfind("; ", 0, _LARGO_TRAMO))
            corte = corte + 1 if corte > _LARGO_TRAMO // 3 else oracion.rfind(" ", 0, _LARGO_TRAMO)
            if corte <= 0:
                break
            resultado.append(oracion[:corte].strip())
            oracion = oracion[corte:].strip()
        if oracion:
            resultado.append(oracion)
    return resultado


def _motor_piper(nombre: str, al_hablar, volumen):
    import sounddevice as sd
    from piper import PiperVoice

    modelo = CARPETA_VOCES / f"{nombre}.onnx"
    if not modelo.exists():
        from piper.download_voices import download_voice

        registro.info("Descargando la voz %s...", nombre)
        CARPETA_VOCES.mkdir(parents=True, exist_ok=True)
        download_voice(nombre, CARPETA_VOCES)
    voz = PiperVoice.load(str(modelo))
    list(voz.synthesize("hola"))  # la primera síntesis es lenta: se hace ahora y no al responder

    def sintetizar(texto: str):
        trozos = list(voz.synthesize(texto))
        if not trozos:
            return None, 0
        audio = np.frombuffer(b"".join(t.audio_int16_bytes for t in trozos), dtype=np.int16)
        return audio, trozos[0].sample_rate

    preparador = ThreadPoolExecutor(max_workers=1)

    def decir(partes: list[str]) -> None:
        # Mientras suena una frase se va preparando la siguiente: arranca enseguida y sin baches.
        pendientes = [preparador.submit(sintetizar, parte) for parte in partes]
        for parte, pendiente in zip(partes, pendientes):
            audio, frecuencia = pendiente.result()
            if audio is None:
                continue
            cola = np.zeros(frecuencia // 10, dtype=np.int16)  # que no se corte el final
            sonido = np.clip(np.concatenate([audio, cola]) * volumen(), -32768, 32767).astype(np.int16)
            al_hablar(parte, _envolvente(audio, frecuencia))
            sd.play(sonido, frecuencia, blocking=True)

    return decir


def _motor_windows(preferida: str, al_hablar, volumen):
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    sapi = win32com.client.Dispatch("SAPI.SpVoice")
    voces = list(sapi.GetVoices())
    elegida = next((v for v in voces if preferida.lower() in v.GetDescription().lower()), None)
    elegida = elegida or next((v for v in voces if "spanish" in v.GetDescription().lower()), None)
    if elegida:
        sapi.Voice = elegida

    def decir(partes: list[str]) -> None:
        sapi.Volume = int(volumen() * 100)
        for parte in partes:
            al_hablar(parte, _envolvente_estimada(parte))
            sapi.Speak(parte)

    return decir


class Voz:
    def __init__(self, activa: bool = True, nombre: str = "es_AR-daniela-high", al_hablar=None,
                 volumen: float = 1.0):
        """`al_hablar(texto, envolvente)` se llama justo cuando empieza a sonar cada subtítulo.

        volumen: de 0 a 1, solo el de la voz del asistente (no toca el de la PC).
        """
        self._activa = activa
        self._nombre = nombre
        self._al_hablar = al_hablar or (lambda texto, envolvente: None)
        self.volumen = max(0.0, min(1.0, volumen))
        self._cola: queue.Queue = queue.Queue()
        self._candado = threading.Lock()
        self._libre = threading.Event()
        self._libre.set()
        if activa:
            # Cargar y hablar en un hilo aparte: ni el arranque ni las acciones esperan a la voz.
            threading.Thread(target=self._trabajar, daemon=True).start()

    def _crear_motor(self):
        if _ES_DE_PIPER.match(self._nombre):
            try:
                return _motor_piper(self._nombre, self._al_hablar, lambda: self.volumen)
            except Exception:
                registro.exception("No pude cargar la voz %s: uso la de Windows", self._nombre)
        try:
            return _motor_windows(self._nombre, self._al_hablar, lambda: self.volumen)
        except Exception:
            registro.exception("No pude iniciar ninguna voz")
            return None

    def _trabajar(self) -> None:
        motor = self._crear_motor()
        while True:
            texto = self._cola.get()
            try:
                if motor:
                    motor(tramos(texto))
            except Exception:
                registro.exception("Falló la voz")
            with self._candado:
                if self._cola.empty():
                    self._libre.set()

    def decir(self, texto: str) -> None:
        """Encola la frase y vuelve enseguida."""
        registro.info("Claudio: %s", texto)
        if self._activa and texto:
            with self._candado:
                self._libre.clear()
                self._cola.put(texto)
        elif texto:
            # Sin voz, al menos se leen los subtítulos, al ritmo en que se dirían.
            threading.Thread(target=self._solo_subtitulos, args=(texto,), daemon=True).start()

    def _solo_subtitulos(self, texto: str) -> None:
        for parte in tramos(texto):
            envolvente = _envolvente_estimada(parte)
            self._al_hablar(parte, envolvente)
            time.sleep(len(envolvente) / _CUADROS)

    def esperar(self, segundos: float = 20) -> None:
        """Espera a que termine de decir todo lo pendiente."""
        self._libre.wait(segundos)
