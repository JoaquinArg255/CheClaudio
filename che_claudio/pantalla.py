"""Captura de pantalla para que el cerebro pueda "mirar"."""
import base64
import io

from PIL import ImageGrab

_LADO_MAXIMO = 1568  # más grande no mejora lo que entiende el modelo


def capturar() -> str:
    """La pantalla principal como JPEG en base64."""
    imagen = ImageGrab.grab()
    imagen.thumbnail((_LADO_MAXIMO, _LADO_MAXIMO))
    salida = io.BytesIO()
    imagen.convert("RGB").save(salida, "JPEG", quality=80)
    return base64.b64encode(salida.getvalue()).decode("ascii")
