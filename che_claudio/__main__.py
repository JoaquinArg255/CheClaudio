"""Punto de entrada: python -m che_claudio"""
import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from . import config as configuracion
from .interprete import separar_llamado

registro = logging.getLogger("che_claudio")

_ARCHIVO_PID = configuracion.DATOS / "che_claudio.pid"
_ARCHIVO_REGISTRO = configuracion.DATOS / "che_claudio.log"


def _preparar_registro(detalle: bool) -> None:
    registro.setLevel(logging.DEBUG if detalle else logging.INFO)
    formato = logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S")
    salidas = [RotatingFileHandler(_ARCHIVO_REGISTRO, maxBytes=500_000, backupCount=1, encoding="utf-8")]
    if sys.stdout is not None:  # con pythonw (modo oculto) no hay consola
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        salidas.append(logging.StreamHandler(sys.stdout))
    for salida in salidas:
        salida.setFormatter(formato)
        registro.addHandler(salida)


def _unica_instancia():
    """Dos asistentes escuchando ejecutarían todo dos veces."""
    import win32api
    import win32event
    import winerror

    candado = win32event.CreateMutex(None, False, "CheClaudioAsistente")
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        return None
    return candado


def _detener() -> None:
    from .sistema import ventanas

    guardado = _ARCHIVO_PID.read_text().strip() if _ARCHIVO_PID.exists() else ""
    pid, _, inicio = guardado.partition(" ")
    # Si quedó de una vez que se cortó la luz, ese número ahora puede ser de otro programa: no se toca.
    detenido = pid.isdigit() and ventanas.terminar(int(pid), float(inicio or 0))
    _ARCHIVO_PID.unlink(missing_ok=True)
    print("Che Claudio detenido." if detenido else "Che Claudio no está corriendo.")


def _medir_nivel(config: dict) -> None:
    from .voz.microfono import Microfono

    print(f"Umbral actual: {config['umbral_microfono']}. Hablá y mirá hasta dónde llega (Ctrl+C para salir).")
    maximo = 0.0
    for i, nivel in enumerate(Microfono(config["microfono"]).niveles()):
        maximo = max(maximo, nivel)
        if i % 10 == 9:
            print(f"\r{maximo:.4f} {'#' * min(60, int(maximo * 600)):<60}", end="", flush=True)
            maximo = 0.0


def main() -> None:
    parser = argparse.ArgumentParser(prog="che_claudio", description="Asistente de voz para Windows.")
    parser.add_argument("--texto", help="ejecuta una orden escrita, sin micrófono")
    parser.add_argument("--archivo", help="ejecuta la orden grabada en un archivo .wav")
    parser.add_argument("--simular", action="store_true", help="muestra qué haría, sin hacerlo (y sin usar el cerebro)")
    parser.add_argument("--mudo", action="store_true", help="no responde con voz")
    parser.add_argument("--sin-cerebro", action="store_true", help="solo reglas: no consulta a Claude")
    parser.add_argument("--detalle", action="store_true", help="muestra todo lo que escucha")
    parser.add_argument("--microfono", type=lambda v: int(v) if v.isdigit() else v,
                        help="número o nombre del micrófono (por defecto, el de config.json o el de Windows)")
    parser.add_argument("--dispositivos", action="store_true", help="lista los micrófonos")
    parser.add_argument("--nivel", action="store_true", help="medidor para calibrar el micrófono")
    parser.add_argument("--detener", action="store_true", help="detiene al asistente que corre oculto")
    parser.add_argument("--vincular-whatsapp", action="store_true", help="abre WhatsApp Web para escanear el QR")
    parser.add_argument("--si", action="store_true", help="con --texto o --archivo, confirma sin preguntar")
    args = parser.parse_args()

    configuracion.DATOS.mkdir(exist_ok=True)
    if args.detener:
        return _detener()
    if args.vincular_whatsapp:
        from .servicios import whatsapp

        whatsapp.vincular()
        return None
    config = configuracion.cargar()
    if args.microfono is not None:
        config["microfono"] = args.microfono
    if args.dispositivos:
        from .voz.microfono import dispositivos

        return print(dispositivos())
    if args.nivel:
        return _medir_nivel(config)

    _preparar_registro(args.detalle)
    from .acciones import Ejecutor
    from .asistente import Asistente, Escucha, confirmar_por_consola, escuchar, por_texto
    from .avatar import Avatar
    from .voz.habla import Voz

    avatar = Avatar(config["avatar"]["activo"] and not args.simular, config["avatar"]["escala"])
    voz = Voz(config["responder_con_voz"] and not args.mudo and not args.simular, config["voz"], avatar.hablar,
              config["volumen_voz"])

    def armar(confirmar, escuchando: bool = False) -> Asistente:
        from .recordatorios import Recordatorios

        # Solo el asistente que escucha avisa; una orden escrita solo agenda (el que escucha la toma).
        recordatorios = Recordatorios(voz.decir, vigilar=escuchando)
        ejecutor = Ejecutor(config, voz, confirmar, simular=args.simular, recordatorios=recordatorios)
        cerebro = None
        if config["cerebro"]["activo"] and not args.simular and not args.sin_cerebro:
            from .cerebro import Cerebro

            cerebro = Cerebro(config, ejecutor)
            cerebro.preparar()
        return Asistente(config, voz, avatar, ejecutor, cerebro)

    if args.texto:
        return por_texto(args.texto, config, armar(confirmar_por_consola(args.si)), voz)

    from .voz.transcriptor import Transcriptor

    registro.info("Cargando el reconocimiento de voz (la primera vez se descarga)...")
    transcriptor = Transcriptor(config["modelo"], config["dispositivo"], config["vocabulario"],
                                config["correcciones"])
    registro.info("Modelo '%s' listo en %s", transcriptor.modelo,
                  "la placa de video" if transcriptor.dispositivo == "cuda" else "el procesador")

    if args.archivo:
        from .voz.microfono import leer_wav

        texto = transcriptor.transcribir(leer_wav(args.archivo))
        registro.info("Vos: %s", texto)
        if separar_llamado(texto, config["nombres"]) is None:
            registro.info("No escuché el llamado")
            return None
        return por_texto(texto, config, armar(confirmar_por_consola(args.si)), voz)

    candado = _unica_instancia()
    if candado is None:
        registro.info("Che Claudio ya está corriendo.")
        return None
    from .sistema import ventanas

    _ARCHIVO_PID.write_text(f"{os.getpid()} {ventanas.inicio_de_pid(os.getpid())}")
    escucha = Escucha(config, transcriptor, voz, avatar)
    try:
        escuchar(config, escucha, voz, avatar, armar(escucha.confirmar, escuchando=True))
    except KeyboardInterrupt:
        pass
    finally:
        _ARCHIVO_PID.unlink(missing_ok=True)
        registro.info("Chau.")
    return None


if __name__ == "__main__":
    try:
        main()
    except Exception:
        registro.exception("Error fatal")  # en modo oculto no hay consola donde verlo
        raise
