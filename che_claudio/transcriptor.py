"""Voz a texto con Whisper, local (no manda audio a ningún servicio)."""
import ctypes
import logging
import os
import re
import site
from pathlib import Path

import numpy as np

registro = logging.getLogger("che_claudio")

# Orienta al modelo sobre cómo se escribe el llamado y el tipo de frases.
_PISTA = "Che Claudio, abrí Spotify y poné música."


def _cuda_lista() -> bool:
    """True solo si la placa y las librerías de NVIDIA están: sin cuDNN el proceso se cae."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() == 0:
            return False
    except Exception:
        return False
    # pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 las deja acá.
    for paquetes in site.getsitepackages():
        for carpeta in Path(paquetes, "nvidia").glob("*/bin"):
            os.add_dll_directory(str(carpeta))
            os.environ["PATH"] = f"{carpeta};{os.environ['PATH']}"
    try:
        ctypes.WinDLL("cublas64_12.dll")
        ctypes.WinDLL("cudnn_ops64_9.dll")
        return True
    except OSError:
        return False


class Transcriptor:
    def __init__(self, modelo: str = "auto", dispositivo: str = "auto", vocabulario=(), correcciones=None):
        """vocabulario: nombres que se dicen seguido (canales, equipos, programas), para que los escriba bien.
        correcciones: {"lo que suele entender mal": "lo que se dijo"}, se aplican al texto ya transcripto."""
        from faster_whisper import WhisperModel

        self._pista = _PISTA + (" " + ", ".join(vocabulario) + "." if vocabulario else "")
        self._correcciones = [(re.compile(rf"\b{re.escape(mal)}\b", re.I), bien)
                              for mal, bien in (correcciones or {}).items()]

        if dispositivo == "auto":
            dispositivo = "cuda" if _cuda_lista() else "cpu"
        if modelo == "auto":
            # El grande entiende mucho mejor, pero sin placa de video tarda varios segundos por frase.
            modelo = "large-v3-turbo" if dispositivo == "cuda" else "small"
        self.modelo = modelo
        self.dispositivo = dispositivo
        precision = "float16" if dispositivo == "cuda" else "int8"
        self._modelo = WhisperModel(modelo, device=dispositivo, compute_type=precision)

    def transcribir(self, audio: np.ndarray) -> str:
        segmentos, _ = self._modelo.transcribe(
            audio, language="es", beam_size=5, vad_filter=True,
            condition_on_previous_text=False, initial_prompt=self._pista,
        )
        texto = " ".join(s.text.strip() for s in segmentos if s.no_speech_prob < 0.6).strip()
        for mal, bien in self._correcciones:
            texto = mal.sub(bien, texto)
        return texto
