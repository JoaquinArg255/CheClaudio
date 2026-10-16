"""Micrófono: escucha continua y recorte de frases por silencio."""
import queue
import time
import wave
from collections import deque

import numpy as np
import sounddevice as sd

FRECUENCIA = 16000  # la que espera Whisper
BLOQUE = 480  # 30 ms
_SEGUNDOS_BLOQUE = BLOQUE / FRECUENCIA

_PREVIO = 0.5  # audio que se conserva de antes de detectar voz
_SILENCIO_FIN = 0.9  # silencio que da por terminada la frase
_MINIMO = 0.24  # con menos sonido que esto es un ruido, no una frase
_MAXIMO = 15.0
_BLOQUES_PARA_AVISAR = int(1.25 / _SEGUNDOS_BLOQUE)  # medio segundo previo + lo que lleva decir "che Claudio"


def dispositivos() -> str:
    lineas = []
    predeterminado = sd.default.device[0]
    for indice, dispositivo in enumerate(sd.query_devices()):
        if dispositivo["max_input_channels"] > 0:
            api = sd.query_hostapis(dispositivo["hostapi"])["name"]
            marca = "*" if indice == predeterminado else " "
            lineas.append(f"{marca} {indice:3d}  {dispositivo['name']}  ({api})")
    return "\n".join(lineas)


def leer_wav(ruta: str) -> np.ndarray:
    """Carga un .wav PCM de 16 bits como float32 mono a 16 kHz."""
    with wave.open(ruta) as archivo:
        if archivo.getsampwidth() != 2:
            raise ValueError("Solo se admiten .wav PCM de 16 bits")
        canales, frecuencia = archivo.getnchannels(), archivo.getframerate()
        muestras = np.frombuffer(archivo.readframes(archivo.getnframes()), dtype=np.int16)
    audio = muestras.reshape(-1, canales).mean(axis=1).astype(np.float32) / 32768
    if frecuencia != FRECUENCIA:
        destino = np.arange(0, len(audio), frecuencia / FRECUENCIA)
        audio = np.interp(destino, np.arange(len(audio)), audio).astype(np.float32)
    return audio


def _resolver(dispositivo):
    """Un nombre aparece una vez por cada API de audio de Windows: se toma el primero."""
    if not isinstance(dispositivo, str):
        return dispositivo
    for indice, candidato in enumerate(sd.query_devices()):
        if candidato["max_input_channels"] > 0 and dispositivo.lower() in candidato["name"].lower():
            return indice
    raise ValueError(f"No hay ningún micrófono que se llame '{dispositivo}'. Probá con --dispositivos.")


class Microfono:
    def __init__(self, dispositivo=None, umbral_minimo: float = 0.008):
        dispositivo = _resolver(dispositivo)
        self._umbral_minimo = umbral_minimo
        self._cola: queue.Queue = queue.Queue()
        self._descartar = False
        self._vence = None
        self.al_empezar = None  # se llama con el comienzo de cada frase, mientras todavía se está hablando
        self._stream = sd.InputStream(
            samplerate=FRECUENCIA, blocksize=BLOQUE, channels=1, dtype="float32",
            device=dispositivo, callback=self._recibir,
        )

    def _recibir(self, datos, cuadros, tiempo, estado) -> None:
        self._cola.put(datos[:, 0].copy())

    def descartar(self) -> None:
        """Tira lo escuchado hasta ahora (por ejemplo, la propia voz del asistente)."""
        self._descartar = True

    def vencer_en(self, segundos: float | None) -> None:
        """Hace que `frases()` entregue None si pasan `segundos` sin que nadie hable."""
        self._vence = None if segundos is None else time.monotonic() + segundos

    def _bloques(self):
        with self._stream:
            while True:
                bloque = self._cola.get()
                if self._descartar:
                    while not self._cola.empty():
                        self._cola.get_nowait()
                    self._descartar = False
                    yield None
                    continue
                yield bloque

    def niveles(self):
        """Volumen de cada bloque, para calibrar el umbral."""
        for bloque in self._bloques():
            if bloque is not None:
                yield float(np.sqrt(np.mean(bloque ** 2)))

    def frases(self):
        """Entrega cada frase dicha como un array float32 a 16 kHz."""
        ruido = None
        previo = deque(maxlen=int(_PREVIO / _SEGUNDOS_BLOQUE))
        recientes = deque(maxlen=8)
        frase, silencio, activos = None, 0, 0
        for bloque in self._bloques():
            if bloque is None:
                previo.clear()
                recientes.clear()
                frase, silencio = None, 0
                continue
            nivel = float(np.sqrt(np.mean(bloque ** 2)))
            activo = nivel > max(self._umbral_minimo, (ruido or 0) * 3)
            if frase is None:
                if self._vence is not None and time.monotonic() > self._vence:
                    self._vence = None
                    yield None  # se acabó la espera y nadie habló
                # El piso de ruido sigue al ambiente; con voz se adapta mucho más lento.
                peso = 0.005 if activo else 0.05
                ruido = nivel if ruido is None else (1 - peso) * ruido + peso * nivel
                previo.append(bloque)
                recientes.append(activo)
                if sum(recientes) >= 5:
                    frase, silencio, activos = list(previo), 0, sum(recientes)
                    recientes.clear()
                continue
            frase.append(bloque)
            activos += activo
            if self.al_empezar and len(frase) == _BLOQUES_PARA_AVISAR:
                self.al_empezar(np.concatenate(frase))  # ya hay suficiente para reconocer el llamado
            silencio = 0 if activo else silencio + 1
            if silencio * _SEGUNDOS_BLOQUE >= _SILENCIO_FIN or len(frase) * _SEGUNDOS_BLOQUE >= _MAXIMO:
                audio = np.concatenate(frase)
                frase, silencio = None, 0
                previo.clear()
                if activos * _SEGUNDOS_BLOQUE >= _MINIMO:
                    yield audio
