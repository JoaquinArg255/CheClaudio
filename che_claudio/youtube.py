"""Búsqueda en YouTube sin API: se lee la página de resultados."""
import re
import urllib.error
import urllib.request
from urllib.parse import urlencode

_CABECERAS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}
_PRIMER_VIDEO = re.compile(r'"videoRenderer":\{"videoId":"([\w-]{11})"')


def url_resultados(consulta: str) -> str:
    return "https://www.youtube.com/results?" + urlencode({"search_query": consulta})


def primer_video(consulta: str) -> str | None:
    """URL del primer video para la búsqueda, o None si no se pudo averiguar."""
    pedido = urllib.request.Request(url_resultados(consulta), headers=_CABECERAS)
    try:
        with urllib.request.urlopen(pedido, timeout=8) as respuesta:
            pagina = respuesta.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    encontrado = _PRIMER_VIDEO.search(pagina)
    return f"https://www.youtube.com/watch?v={encontrado.group(1)}" if encontrado else None
