"""Pausa, play, siguiente y anterior sobre lo que esté sonando en Windows.

Usa las sesiones multimedia del sistema (las mismas del panel de volumen), que
permiten saber si algo está sonando: las teclas multimedia solo alternan a ciegas.
"""
import asyncio
import logging

from . import ventanas

registro = logging.getLogger("che_claudio")

try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as _Gestor,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as _Estado,
    )
except ImportError:  # sin winrt se usan las teclas multimedia
    _Gestor = None


def _sonando(sesion) -> bool:
    return sesion.get_playback_info().playback_status == _Estado.PLAYING


_NAVEGADORES = ("brave", "chrome", "msedge", "firefox", "opera", "vivaldi")


def _es_de(sesion, donde: str | None) -> bool:
    """¿La sesión es del origen pedido? donde: "spotify", "youtube"/"navegador" o None (cualquiera)."""
    if not donde:
        return True
    origen = sesion.source_app_user_model_id.lower()
    if donde == "spotify":
        return "spotify" in origen
    return any(navegador in origen for navegador in _NAVEGADORES)


async def _pausar(donde: str | None) -> int:
    gestor = await _Gestor.request_async()
    pausadas = 0
    for sesion in gestor.get_sessions():
        if _es_de(sesion, donde) and _sonando(sesion) and await sesion.try_pause_async():
            pausadas += 1
    return pausadas


async def _sobre_la_actual(operacion: str, donde: str | None) -> bool:
    gestor = await _Gestor.request_async()
    if donde:
        sesion = next((s for s in gestor.get_sessions() if _es_de(s, donde)), None)
    else:
        sesion = gestor.get_current_session()
    if sesion is None:
        return False
    if operacion == "continuar":
        return _sonando(sesion) or await sesion.try_play_async()
    if operacion == "siguiente":
        return await sesion.try_skip_next_async()
    return await sesion.try_skip_previous_async()


async def _descripcion() -> str | None:
    gestor = await _Gestor.request_async()
    sesion = gestor.get_current_session()
    if sesion is None:
        return None
    datos = await sesion.try_get_media_properties_async()
    if not datos.title:
        return None
    return f"{datos.title}, de {datos.artist}" if datos.artist else datos.title


def _ejecutar(corrutina, tecla_de_respaldo: int | None):
    if _Gestor is not None:
        try:
            return asyncio.run(corrutina)
        except Exception:  # la API de Windows puede fallar: quedan las teclas
            registro.exception("Falló el control multimedia de Windows")
    else:
        corrutina.close()
    if tecla_de_respaldo is None:
        return False
    ventanas.tecla(tecla_de_respaldo)
    return True


def _respaldo(tecla: int, donde: str | None) -> int | None:
    # La tecla multimedia no elige origen: si se pidió uno, mejor no hacer nada que tocar el otro.
    return None if donde else tecla


def pausar(donde: str | None = None) -> bool:
    """Pausa lo que esté sonando (todo, o solo en Spotify o en el navegador). False si no había nada."""
    return bool(_ejecutar(_pausar(donde), _respaldo(ventanas.VK_PLAY_PAUSA, donde)))


def continuar(donde: str | None = None) -> bool:
    return bool(_ejecutar(_sobre_la_actual("continuar", donde), _respaldo(ventanas.VK_PLAY_PAUSA, donde)))


def siguiente(donde: str | None = None) -> bool:
    return bool(_ejecutar(_sobre_la_actual("siguiente", donde), _respaldo(ventanas.VK_SIGUIENTE, donde)))


def anterior(donde: str | None = None) -> bool:
    return bool(_ejecutar(_sobre_la_actual("anterior", donde), _respaldo(ventanas.VK_ANTERIOR, donde)))


def que_suena() -> str | None:
    """"Canción, de Artista" de la sesión actual, si hay."""
    resultado = _ejecutar(_descripcion(), None)
    return resultado if isinstance(resultado, str) else None
