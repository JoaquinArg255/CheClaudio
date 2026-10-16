"""El asistente en marcha: escucha, decide quién resuelve cada orden y conversa.

`Escucha` junta el micrófono con el reconocimiento de voz; `Asistente` reparte cada orden entre las
reglas (al instante) y el cerebro (Claude); `escuchar` es el bucle principal con la ventana de atención.
"""
import logging
import re
import time

from .interprete import (acepta_verlo, es_afirmacion, frase_cortada, interpretar, pide_mostrar,
                         separar_llamado)
from .texto import tokenizar

registro = logging.getLogger("che_claudio")

_SEGUNDOS_CONFIRMAR = 10  # cuánto espera el "sí" antes de mandar un mensaje
_SEGUNDOS_PARA_SEGUIR = 4.0  # si la frase quedó por la mitad, cuánto espera a que la terminen
# Lo que las reglas no resuelven (o resuelven con una frase hecha) va al cerebro.
_PARA_EL_CEREBRO = {"desconocido", "saludo", "gracias", "musica_a_gusto"}


class Escucha:
    """El micrófono más el reconocimiento: entrega lo que se va diciendo."""

    def __init__(self, config: dict, transcriptor, voz, avatar):
        from .voz.microfono import Microfono

        self._microfono = Microfono(config["microfono"], config["umbral_microfono"])
        self._frases = self._microfono.frases()
        self._transcriptor = transcriptor
        self._voz = voz
        self._avatar = avatar
        self._nombres = config["nombres"]
        if transcriptor.dispositivo == "cuda":  # en el procesador, transcribir dos veces cada frase pesa demasiado
            self._microfono.al_empezar = self._al_empezar_a_hablar

    def _al_empezar_a_hablar(self, comienzo) -> None:
        """Con el primer segundo de la frase ya se sabe si llamaron a Claudio: aparece antes de que terminen."""
        texto = self._transcriptor.transcribir(comienzo)
        if separar_llamado(texto, self._nombres) is not None:
            registro.debug("(lo llamaron: aparece) %s", texto)
            self._avatar.escuchando()

    def siguiente(self, segundos: float | None = None) -> str | None:
        """La próxima frase dicha. Con `segundos`, None si en ese tiempo nadie habló."""
        self._microfono.vencer_en(segundos)
        for audio in self._frases:
            if audio is None:
                return None
            texto = self._transcriptor.transcribir(audio)
            if texto:
                return texto
        return None

    def callar(self) -> None:
        """Espera a que el asistente termine de hablar y descarta lo que el micrófono oyó de él."""
        self._voz.esperar()
        self._microfono.descartar()

    def confirmar(self, pregunta: str) -> bool:
        self._voz.decir(pregunta)
        self.callar()
        respuesta = self.siguiente(_SEGUNDOS_CONFIRMAR)
        registro.info("Vos: %s", respuesta or "(silencio)")
        return bool(respuesta) and es_afirmacion(respuesta)


def confirmar_por_consola(siempre_si: bool):
    def confirmar(pregunta: str) -> bool:
        if siempre_si:
            registro.info("%s -> sí (--si)", pregunta)
            return True
        try:
            return es_afirmacion(input(f"{pregunta} [si/no] "))
        except EOFError:
            return False

    return confirmar


class Asistente:
    """Decide quién resuelve cada orden: las reglas (al instante) o el cerebro (conversando)."""

    def __init__(self, config: dict, voz, avatar, ejecutor, cerebro):
        self._siempre_cerebro = config["cerebro"]["modo"] == "siempre"
        self._voz = voz
        self._avatar = avatar
        self._ejecutor = ejecutor
        self._cerebro = cerebro
        self._novedades: list[str] = []  # órdenes resueltas por reglas, para que el cerebro esté al tanto
        self._ultima_respuesta = ""  # lo último que dijo el cerebro: "¿lo querés en pantalla?" - "sí"

    def atender(self, palabras, en_charla: bool = False, sin_llamado: bool = False) -> str:
        """Atiende lo dicho. Devuelve "pregunta" si quedó esperando respuesta, "ignorado" si no era
        para Claudio, o "listo".

        en_charla: es la respuesta a una pregunta suya (va directo al cerebro).
        sin_llamado: se dijo sin "Che Claudio", mientras él seguía atento; puede no ser para él.
        """
        from . import memoria
        from .cerebro import SinSesion

        texto = " ".join(p.bruto or p.original for p in palabras)
        acciones = interpretar(palabras)
        solo_dudas = all(a.tipo == "desconocido" for a in acciones)
        necesita_pensar = (
            en_charla or self._siempre_cerebro or any(a.tipo in _PARA_EL_CEREBRO for a in acciones)
            # "abrí tal cosa" con un nombre que las reglas no conocen: que lo piense antes de decir que no existe.
            or any(a.tipo == "abrir" and not self._ejecutor.puede_abrir(a.objetivo) for a in acciones))
        if self._cerebro and necesita_pensar:
            self._avatar.pensando()
            # Puede mostrar algo si lo pidieron ahora, o si avisó que algo quedó oculto y le dicen que sí.
            puede_mostrar = pide_mostrar(palabras) or acepta_verlo(self._ultima_respuesta, palabras)
            try:
                respuesta = self._cerebro.conversar(texto, self._novedades, puede_mostrar,
                                                    sin_llamado and not en_charla)
            except SinSesion:
                self._cerebro = None  # no se reintenta en cada orden
                self._voz.decir("Todavía no inicié sesión en Claude. Ejecutá conectar Claude para que pueda pensar.")
                respuesta = None
            self._novedades = []
            if respuesta:
                respuesta = re.sub(r"[*_#`]", "", respuesta).strip()
                if not respuesta.strip(". …"):
                    return "ignorado"  # el cerebro entendió que no le hablaban a él
                self._ultima_respuesta = respuesta
                memoria.anotar_charla(texto, respuesta, self._cerebro.leyo_de_afuera)
                self._voz.decir(respuesta)
                return "pregunta" if "?" in respuesta else "listo"
            if solo_dudas:
                if self._cerebro:  # hay sesión pero no contestó
                    self._voz.decir("No pude pensar una respuesta, probá de nuevo.")
                return "listo"
        if sin_llamado and solo_dudas:
            return "ignorado"  # sin llamado y sin sentido para las reglas: no era para él
        for accion in acciones:
            self._ejecutor.ejecutar(accion)
        self._novedades = (self._novedades + [texto])[-5:]
        self._ultima_respuesta = ""
        return "listo"


def escuchar(config: dict, escucha: Escucha, voz, avatar, asistente: Asistente) -> None:
    from .acciones import Salir

    registro.info('Escuchando. Decí "Che %s, ..." (Ctrl+C para salir)', config["nombres"][0].capitalize())
    # Mientras el personaje está en pantalla, Claudio sigue atento: lo que se diga no necesita el
    # "Che Claudio". Cuando se va, deja de escuchar hasta que lo vuelvan a llamar.
    atento_hasta, en_charla = 0.0, False
    lo_llamaron = False  # acaba de responder "¿Sí?": lo que sigue es para él, sin duda
    while True:
        restante = atento_hasta - time.monotonic()
        texto = escucha.siguiente(max(restante, 0.1) if atento_hasta else None)
        if texto is None:  # se acabó la espera sin que hablara
            atento_hasta, en_charla, lo_llamaron = 0.0, False, False
            avatar.ocultar()
            continue
        palabras = separar_llamado(texto, config["nombres"])
        sin_llamado = palabras is None
        if sin_llamado and lo_llamaron:
            # "Che Claudio" - "¿Sí?" - "poné música": es la orden del llamado, aunque no repita el nombre.
            texto = f"{config['nombres'][0].capitalize()}, {texto}"
            palabras, sin_llamado = separar_llamado(texto, config["nombres"]), False
        lo_llamaron = False
        if sin_llamado and not atento_hasta:
            registro.debug("(sin llamado) %s", texto)  # lo que no es para Claudio no se guarda
            avatar.ocultar()  # por si apareció al oír el comienzo de la frase
            continue
        # Una pausa para pensar corta la frase por la mitad ("poneme..."): se espera el resto antes de actuar.
        for _ in range(2):
            if not (palabras or sin_llamado) or not frase_cortada(texto):
                break
            avatar.escuchando()
            resto = escucha.siguiente(_SEGUNDOS_PARA_SEGUIR)
            if not resto:
                break
            if separar_llamado(resto, config["nombres"]) is not None:
                texto, sin_llamado = resto, False  # volvió a llamarlo: empieza de nuevo
            else:
                texto = f"{texto.rstrip(' .…')} {resto}"
            palabras = separar_llamado(texto, config["nombres"])
        if sin_llamado:
            palabras = tokenizar(texto)
        else:
            registro.info("Vos: %s", texto)
        resultado = "listo"
        try:
            if palabras:
                avatar.pensando()
                resultado = asistente.atender(palabras, en_charla, sin_llamado)
            else:
                voz.decir("¿Sí?")
                resultado = "llamado"
        except Salir:
            return
        except Exception:
            registro.exception("Falló la orden")
            voz.decir("Algo salió mal")
        if resultado == "ignorado":
            registro.info("(entendió que no era para él) %s", texto)
            # Sigue atento lo que le quedaba, sin renovarlo.
            avatar.escuchando() if atento_hasta else avatar.ocultar()
            continue
        if sin_llamado:
            registro.info("Vos (sin llamarlo): %s", texto)
        escucha.callar()
        # Tras el "¿Sí?" o una pregunta suya hace falta más tiempo para arrancar a hablar que tras una respuesta.
        espera = config["segundos_para_contestar"] if resultado in ("llamado", "pregunta") else config["segundos_atento"]
        atento_hasta, en_charla = time.monotonic() + espera, resultado == "pregunta"
        lo_llamaron = resultado == "llamado"
        avatar.escuchando()


def por_texto(texto: str, config: dict, asistente: Asistente, voz) -> None:
    """Una orden escrita. Si el cerebro pregunta algo, se le puede contestar por teclado."""
    from .acciones import Salir

    palabras = separar_llamado(texto, config["nombres"]) or tokenizar(texto)  # el llamado es opcional
    try:
        en_charla = False
        while asistente.atender(palabras, en_charla) == "pregunta":
            voz.esperar()
            palabras, en_charla = tokenizar(input("> ")), True
    except (Salir, EOFError):
        pass
    voz.esperar()
    time.sleep(1.5)  # que el avatar termine la frase antes de cerrar
