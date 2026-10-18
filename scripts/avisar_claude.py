"""Hace que Claudio avise en voz alta cuando Claude Code termina una consulta larga o te pregunta algo.

Lo llaman hooks de Claude Code (en ~/.claude/settings.json):
  avisar_claude.py empezo   al mandar una consulta (UserPromptSubmit): anota la hora
  avisar_claude.py termino  cuando Claude termina (Stop): avisa si terminó preguntando algo, o si tardó
  avisar_claude.py pregunta cuando Claude te hace una pregunta con opciones (PreToolUse de AskUserQuestion)
  avisar_claude.py permiso  cuando Claude necesita tu permiso para seguir (Notification)

De Claudio solo carga la configuración (tiene que ser instantáneo): deja el aviso en
datos/recordatorios.json, que el asistente relee solo. Si Claudio no está corriendo, no hace nada.
"""
import ctypes
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from che_claudio import config as configuracion  # noqa: E402  (solo lee json: no carga voz ni modelos)

_EN_CURSO = configuracion.DATOS / "cerebro" / "consultas_en_curso.json"
_RECORDATORIOS = configuracion.DATOS / "recordatorios.json"
_LARGO = 160  # caracteres que se dicen de la pregunta: más se vuelve un discurso


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


def _avisar(mensaje: str) -> None:
    """Lo deja para que Claudio lo diga en voz alta; si no está escuchando, no hace nada."""
    if not _claudio_escuchando():
        return
    avisos = _leer(_RECORDATORIOS, [])
    avisos.append({"cuando": datetime.now().replace(microsecond=0).isoformat(), "mensaje": mensaje})
    _RECORDATORIOS.write_text(json.dumps(avisos, ensure_ascii=False, indent=2), encoding="utf-8")


def _donde(datos: dict) -> str:
    carpeta = Path(datos.get("cwd") or "").name
    return f" en {carpeta}" if carpeta else ""


def _corto(texto: str) -> str:
    """Para decirlo en voz alta: sin marcas de formato, en una línea y sin pasarse de largo."""
    texto = " ".join(re.sub(r"[*_`#>|]", "", texto).split())
    return texto if len(texto) <= _LARGO else texto[:_LARGO].rsplit(" ", 1)[0] + "..."


def pregunta_final(respuesta: str) -> str | None:
    """La pregunta con la que Claude cerró su respuesta ("¿Querés que lo suba?"), o None.

    Solo mira el último párrafo: una pregunta citada en el medio de la respuesta no es para vos.
    """
    ultimo = respuesta.strip().split("\n\n")[-1]
    preguntas = re.findall(r"¿?[^.!?¿\n]*\?", ultimo)
    return preguntas[-1].strip() if preguntas else None


def aviso_de_pregunta(datos: dict) -> str | None:
    """AskUserQuestion: Claude te ofrece opciones y espera que elijas."""
    preguntas = (datos.get("tool_input") or {}).get("questions") or []
    if not preguntas:
        return None
    otras = len(preguntas) - 1
    mas = f" Y {otras} pregunta{'s' if otras > 1 else ''} más." if otras else ""
    return f"Claude te está preguntando algo{_donde(datos)}: {_corto(preguntas[0].get('question', ''))}{mas}"


def aviso_de_permiso(datos: dict) -> str | None:
    """Notification: solo cuando Claude espera tu permiso o un dato; "está esperando" a secas ya lo cubre Stop."""
    tipo, mensaje = datos.get("notification_type"), datos.get("message") or ""
    herramienta = re.search(r"permission to use (.+)", mensaje)
    if tipo == "permission_prompt":
        para = f" para usar {_corto(herramienta.group(1))}" if herramienta else ""
        return f"Claude necesita tu permiso{_donde(datos)}{para}."
    if tipo == "elicitation_dialog":
        return f"Claude te está pidiendo un dato{_donde(datos)}: {_corto(mensaje)}"
    return None


def main() -> None:
    try:
        datos = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        datos = {}
    config = configuracion.cargar()["avisar_consultas"]
    if not config["activo"]:
        return
    modo = sys.argv[1] if len(sys.argv) > 1 else ""
    if modo in ("pregunta", "permiso"):  # a mitad de la consulta: no cambia cuándo empezó
        aviso = aviso_de_pregunta(datos) if modo == "pregunta" else aviso_de_permiso(datos)
        if aviso:
            _avisar(aviso)
        return

    sesion = datos.get("session_id") or "sin-sesion"
    en_curso = _leer(_EN_CURSO, {})
    ahora = time.time()
    en_curso = {s: t for s, t in en_curso.items() if ahora - t < 24 * 3600}  # sesiones que nunca terminaron

    if modo == "empezo":
        en_curso[sesion] = ahora
    else:
        inicio = en_curso.pop(sesion, None)
        demoro = ahora - inicio if inicio else 0
        pregunta = pregunta_final(datos.get("last_assistant_message") or "")
        if pregunta:  # te espera a vos: se avisa aunque haya sido rápida
            _avisar(f"Claude te está preguntando algo{_donde(datos)}: {_corto(pregunta)}")
        elif demoro >= config["segundos_minimos"]:
            carpeta = Path(datos.get("cwd") or "").name
            minutos = round(demoro / 60)
            cuanto = f" Tardó {minutos} minutos." if minutos >= 2 else ""
            _avisar(f"Claude terminó la consulta{' de ' + carpeta if carpeta else ''}, ya la podés revisar.{cuanto}")
    _EN_CURSO.parent.mkdir(parents=True, exist_ok=True)
    _EN_CURSO.write_text(json.dumps(en_curso), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # un aviso que falla no tiene que molestar a Claude Code
