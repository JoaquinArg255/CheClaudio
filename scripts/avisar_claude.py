"""Hace que Claudio avise en voz alta cuando Claude Code termina una consulta larga.

Lo llaman dos hooks de Claude Code (en ~/.claude/settings.json):
  avisar_claude.py empezo   al mandar una consulta: anota la hora
  avisar_claude.py termino  cuando Claude termina: si tardó lo suficiente, agenda el aviso

De Claudio solo carga la configuración (tiene que ser instantáneo): deja el aviso en
datos/recordatorios.json, que el asistente relee solo. Si Claudio no está corriendo, no hace nada.
"""
import ctypes
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from che_claudio import config as configuracion  # noqa: E402  (solo lee json: no carga voz ni modelos)

_EN_CURSO = configuracion.DATOS / "cerebro" / "consultas_en_curso.json"
_RECORDATORIOS = configuracion.DATOS / "recordatorios.json"


def _leer(archivo: Path, vacio):
    try:
        return json.loads(archivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return vacio


def _claudio_escuchando() -> bool:
    """El asistente que escucha tiene tomado este candado (ver _unica_instancia en __main__)."""
    candado = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, "CheClaudioAsistente")  # SYNCHRONIZE
    if candado:
        ctypes.windll.kernel32.CloseHandle(candado)
    return bool(candado)


def main() -> None:
    try:
        datos = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        datos = {}
    sesion = datos.get("session_id") or "sin-sesion"
    config = configuracion.cargar()["avisar_consultas"]
    if not config["activo"]:
        return
    en_curso = _leer(_EN_CURSO, {})
    ahora = time.time()
    en_curso = {s: t for s, t in en_curso.items() if ahora - t < 24 * 3600}  # sesiones que nunca terminaron

    if sys.argv[1:] == ["empezo"]:
        en_curso[sesion] = ahora
    else:
        inicio = en_curso.pop(sesion, None)
        demoro = ahora - inicio if inicio else 0
        if demoro >= config["segundos_minimos"] and _claudio_escuchando():
            carpeta = Path(datos.get("cwd") or "").name
            minutos = round(demoro / 60)
            cuanto = f" Tardó {minutos} minutos." if minutos >= 2 else ""
            mensaje = f"Claude terminó la consulta{' de ' + carpeta if carpeta else ''}, ya la podés revisar.{cuanto}"
            avisos = _leer(_RECORDATORIOS, [])
            avisos.append({"cuando": datetime.now().replace(microsecond=0).isoformat(), "mensaje": mensaje})
            _RECORDATORIOS.write_text(json.dumps(avisos, ensure_ascii=False, indent=2), encoding="utf-8")
    _EN_CURSO.parent.mkdir(parents=True, exist_ok=True)
    _EN_CURSO.write_text(json.dumps(en_curso), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # un aviso que falla no tiene que molestar a Claude Code
