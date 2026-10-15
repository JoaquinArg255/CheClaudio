"""Programas chicos a pedido: "haceme un programa que...".

Lo escribe otro Claude, aparte del de la charla, que solo puede crear archivos
dentro de la carpeta del programa (Documentos\\Programas de Claudio\\<nombre>).
No ejecuta nada: deja el código y un LEEME.txt que dice cómo usarlo.
"""
import asyncio
import logging
import re
import threading
from pathlib import Path

from win32com.shell import shell, shellcon

from .texto import normalizar

registro = logging.getLogger("che_claudio")

_INSTRUCCIONES = """\
Escribís programas chicos para una persona que los pidió hablando con su asistente de voz. Trabajás en una \
carpeta vacía que es solo para este programa: creá ahí los archivos, con rutas relativas, y nada fuera de ella. \
No podés ejecutar nada, así que revisá el código leyéndolo antes de terminar.

Hacelo simple y que funcione de una: un solo archivo si alcanza, sin dependencias que haya que instalar salvo \
que el pedido las necesite. Si no dicen el lenguaje, usá Python, o una página HTML sola si es algo para ver. \
Nombres y comentarios en castellano. Agregá un LEEME.txt de pocas líneas que diga qué hace y cómo se abre o \
se ejecuta en Windows.

Al terminar respondé con una sola oración, para decir en voz alta: qué hiciste y cómo se usa. Sin rutas, \
sin listas, sin markdown."""

_haciendo: set[str] = set()


def carpeta() -> Path:
    destino = Path(shell.SHGetKnownFolderPath(shellcon.FOLDERID_Documents, 0, None)) / "Programas de Claudio"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _carpeta_para(nombre: str) -> Path:
    base = re.sub(r"[^a-z0-9]+", " ", normalizar(nombre)).strip()[:40] or "programa"
    destino, numero = carpeta() / base, 2
    while destino.exists() and any(destino.iterdir()):
        destino, numero = carpeta() / f"{base} {numero}", numero + 1
    destino.mkdir(parents=True, exist_ok=True)
    return destino


async def _escribir(pedido: str, destino: Path, modelo: str) -> str | None:
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

    opciones = ClaudeAgentOptions(
        system_prompt=_INSTRUCCIONES,
        model=modelo,
        tools=["Read", "Write", "Edit", "Glob"],  # ni comandos ni internet
        allowed_tools=["Read", "Glob"],
        permission_mode="acceptEdits",  # escribe sin preguntar, pero solo dentro de su carpeta
        setting_sources=[],
        strict_mcp_config=True,
        cwd=str(destino),
        max_turns=30,
    )
    resumen = None
    async for mensaje in query(prompt=pedido, options=opciones):
        if isinstance(mensaje, ResultMessage):
            resumen = None if mensaje.is_error else mensaje.result
            registro.info("Programa en %s: %s turnos, por API costaría US$ %.4f (con tu plan descuenta cupo)",
                          destino.name, mensaje.num_turns, mensaje.total_cost_usd or 0)
    return resumen


def programar(pedido: str, nombre: str, modelo: str, avisar, al_terminar=None) -> str:
    """Arranca en otro hilo (lleva un minuto o más). Devuelve qué decir mientras tanto."""
    if len(_haciendo) >= 2:
        return "Ya estoy haciendo dos programas, esperá a que termine uno"
    destino = _carpeta_para(nombre)
    _haciendo.add(destino.name)

    def trabajar() -> None:
        try:
            resumen = asyncio.run(_escribir(pedido, destino, modelo))
            hechos = [a for a in destino.rglob("*") if a.is_file()]
            if not hechos:
                avisar(f"No pude hacer el programa {destino.name}, probá pedírmelo de otra forma")
                return
            registro.info("Programa %s: %s", destino, ", ".join(a.name for a in hechos))
            avisar(f"Terminé el programa {destino.name}. {' '.join((resumen or '').split())[:300]} "
                   "Quedó en Documentos, Programas de Claudio.")
            if al_terminar:
                al_terminar(destino)
        except Exception:
            registro.exception("Falló hacer el programa %s", destino.name)
            avisar(f"Algo salió mal haciendo el programa {destino.name}")
        finally:
            _haciendo.discard(destino.name)

    threading.Thread(target=trabajar, daemon=True, name="programador").start()
    return f"Me pongo a hacer el programa {destino.name}; lleva un minuto o dos y te aviso cuando esté"
