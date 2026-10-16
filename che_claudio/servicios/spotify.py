"""Control de Spotify con la línea de comandos que trae la app (spotify_cli.exe).

Busca y reproduce sin tocar la ventana: Spotify puede quedar minimizado.
"""
import json
import logging
import os
import subprocess
import time
from pathlib import Path

import win32api
import win32con

from ..sistema import ventanas

registro = logging.getLogger("che_claudio")

EXE = "spotify.exe"
_ALIAS = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps"
_CLI = _ALIAS / "spotify_cli.exe"
_APP = _ALIAS / "Spotify.exe"


def disponible() -> bool:
    return _CLI.exists()


def _cli(*argumentos: str, espera: float = 15):
    """Ejecuta un comando de la CLI. Devuelve (ok, respuesta JSON o None)."""
    try:
        proceso = subprocess.run(
            [str(_CLI), *argumentos, "--format", "json"], capture_output=True, timeout=espera,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return False, None
    if proceso.returncode != 0:
        registro.debug("spotify_cli %s: %s", argumentos[0], proceso.stderr.decode("utf-8", "replace").strip())
        return False, None
    try:
        return True, json.loads(proceso.stdout.decode("utf-8", "replace") or "null")
    except ValueError:
        return True, None


_REINTENTAR_TRAS = 10 * 60  # si la app no se deja controlar, cada cuánto se vuelve a probar
_sin_control_desde = 0.0


def _lista() -> bool:
    ok, estado = _cli("status", espera=5)
    return ok and bool(estado) and estado.get("logged_in", False)


def sin_control() -> bool:
    """La app está abierta pero su línea de comandos no conecta (pasó tras una actualización de Spotify).
    Mientras dure no tiene sentido esperar: cada intento tarda medio minuto en fallar."""
    return bool(_sin_control_desde) and time.monotonic() - _sin_control_desde < _REINTENTAR_TRAS


def ventana() -> int | None:
    encontradas = ventanas.ventanas_de(EXE)
    return encontradas[0] if encontradas else None


def abrir(mostrar: bool = False, espera: float = 25) -> bool:
    """Deja Spotify corriendo. Si hay que iniciarlo, arranca minimizado y sin sacar el foco."""
    global _sin_control_desde
    if sin_control():
        return False
    if not _lista():
        if ventana():
            # Ya está abierta y con la sesión iniciada, pero no contesta: esperar no lo arregla.
            _sin_control_desde = time.monotonic()
            registro.warning("Spotify está abierto pero su línea de comandos no conecta")
            return False
        ventanas.bloquear_foco()
        try:
            win32api.ShellExecute(0, "open", str(_APP) if _APP.exists() else "spotify:", "--minimized", None,
                                  win32con.SW_SHOWMINNOACTIVE)
            limite = time.monotonic() + espera
            while not _lista():
                if time.monotonic() > limite:
                    if ventana():
                        _sin_control_desde = time.monotonic()
                    return False
                time.sleep(0.4)
        except win32api.error:
            return False
        finally:
            ventanas.desbloquear_foco()
    _sin_control_desde = 0.0
    if mostrar:
        ventanas.traer_al_frente(ventana())
    return True


def volumen() -> int | None:
    """Volumen de Spotify en esta PC, de 0 a 100 (aparte del volumen general de Windows)."""
    ok, datos = _cli("devices", "list", espera=5)
    propio = next((d for d in (datos or {}).get("devices", []) if d.get("is_self")), None) if ok else None
    return propio.get("volume") if propio else None


def fijar_volumen(nivel: int) -> bool:
    nivel = max(0, min(100, nivel))
    # Spotify redondea hacia abajo a sus propios escalones: medio punto de más y queda en el pedido.
    ok, _ = _cli("volume", f"{min(1.0, (nivel + 0.5) / 100) if nivel else 0:.3f}", espera=5)
    return ok


def _mejor_resultado(resultados: dict) -> dict | None:
    """El primer elemento de la categoría que Spotify considera más relevante."""
    for categoria in resultados.get("categories_order") or ("tracks", "artists", "albums", "playlists"):
        elementos = resultados.get(categoria) or []
        if elementos:
            return elementos[0]
    return None


def sonando() -> str | None:
    """"Canción, de Artista" si está reproduciendo; None si no."""
    ok, estado = _cli("now-playing", espera=5)
    actual = (estado or {}).get("currently_playing") if ok else None
    if not actual or not actual.get("is_playing"):
        return None
    cancion, separador, artista = actual.get("description", "").partition(" — ")
    return f"{cancion}, de {artista}" if separador else cancion


def reproducir(consulta: str, mostrar: bool = False) -> str | None:
    """Busca `consulta` y reproduce el mejor resultado. Devuelve qué quedó sonando, o None."""
    if not abrir():
        registro.warning("Spotify no abrió a tiempo")
        return None
    ok, resultados = _cli("search", consulta, "--limit", "5")
    elegido = _mejor_resultado(resultados or {}) if ok else None
    if not elegido:
        registro.warning("Spotify no encontró nada para '%s'", consulta)
        return None
    ok, _ = _cli("play", elegido["uri"])
    if not ok:
        return None
    if mostrar:
        ventanas.traer_al_frente(ventana())
    # La app tarda un instante en informar la canción nueva.
    for _ in range(10):
        actual = sonando()
        if actual:
            return actual
        time.sleep(0.3)
    return elegido.get("name")
