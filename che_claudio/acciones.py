"""Ejecuta las acciones que entendió el intérprete."""
import ctypes
import logging
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, quote_plus

import pywintypes
import win32api

from . import archivos, lanzador, multimedia, notas, spotify, ventanas, youtube
from . import config as configuracion
from .recordatorios import describir_hora
from .catalogo import Catalogo
from .interprete import Accion, hora_hablada, plataforma_de
from .proyectos import Proyectos
from .texto import normalizar, parecido

registro = logging.getLogger("che_claudio")

_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
          "octubre", "noviembre", "diciembre")

_BUSCADORES = {
    "google": ("Google", "https://www.google.com/search?q={}", quote_plus),
    "youtube": ("YouTube", "https://www.youtube.com/results?search_query={}", quote_plus),
    "wikipedia": ("Wikipedia", "https://es.wikipedia.org/w/index.php?search={}", quote_plus),
    "maps": ("Maps", "https://www.google.com/maps/search/{}", quote),
    "mercadolibre": ("Mercado Libre", "https://listado.mercadolibre.com.ar/{}", quote),
    "spotify": ("Spotify", "spotify:search:{}", quote),
}

# Ejecutables cuyo nombre no se parece a como se los nombra en castellano.
_EJECUTABLES = {
    "calculadora": "calculatorapp", "bloc de notas": "notepad", "notas": "notepad", "paint": "mspaint",
    "administrador de tareas": "taskmgr", "terminal": "windowsterminal", "consola": "windowsterminal",
    "visual studio code": "code",
}


# Acciones que abren algo que se puede ver o no, según se pida.
_SE_VEN = {"abrir", "buscar", "archivo", "nota"}

# "una pestaña de Brave", "otra pestaña con YouTube", "la pestaña de configuración de Bluetooth".
_PESTANA = re.compile(r"^(?:(?:otra|una|nueva|la)\s+)?pestana(?:\s+nueva)?"
                      r"(?:\s+(?:de|del|en|con)\s+(?:el\s+|la\s+|mi\s+)?(?P<resto>.+))?$")
_PESTANA_NUEVA = "chrome://newtab"  # la entienden Brave, Chrome y Edge
_SEGUNDOS_PARA_APAGAR = 60

# El escritorio y las consolas (el asistente puede estar corriendo en una).
_NUNCA_CERRAR = {"explorer", "python", "pythonw", "windowsterminal", "cmd", "conhost", "openconsole", "powershell",
                 "pwsh"}


class Salir(Exception):
    """Se pidió apagar el asistente."""


class Ejecutor:
    def __init__(self, config: dict, voz, confirmar, simular: bool = False, recordatorios=None):
        """`confirmar(pregunta) -> bool` le pregunta al usuario antes de algo que no se puede deshacer."""
        self._config = config
        self._voz = voz
        self._confirmar = confirmar
        self._simular = simular
        self._recordatorios = recordatorios
        self._catalogo = Catalogo(config["sitios"], config["apps"])
        self._decir = voz.decir  # a quién se le cuenta lo que pasó: al usuario o al cerebro
        self._proyectos = Proyectos(config.get("proyectos"), voz.decir, self._abrir_pagina)
        self._pestana_a_la_vista = False

    def ejecutar(self, accion: Accion) -> None:
        registro.info("-> %s", {k: v for k, v in vars(accion).items() if v not in (None, "")})
        if self._simular:
            self._mostrar_que_haria(accion)
        else:
            getattr(self, "_" + accion.tipo)(accion)

    def ejecutar_para_cerebro(self, accion: Accion) -> str:
        """Ejecuta sin hablar y devuelve lo que pasó, para que el cerebro decida qué decir."""
        informe: list[str] = []
        self._decir = informe.append
        self._pestana_a_la_vista = False
        try:
            self.ejecutar(accion)
        finally:
            self._decir = self._voz.decir
        resultado = " ".join(informe) or "Hecho."
        if accion.tipo in _SE_VEN:
            # Que el cerebro no diga "abierto en pantalla" cuando quedó minimizado.
            if self._a_la_vista(accion):
                resultado += " Quedó a la vista."
            elif self._pestana_a_la_vista:
                resultado += " Se abrió como pestaña nueva en el navegador que la persona tiene adelante: la está viendo."
            else:
                resultado += " Quedó en segundo plano: la persona no lo ve hasta que lo abra o pida verlo."
        return resultado

    def programas_parecidos(self, texto: str) -> list[str]:
        return self._catalogo.parecidos(texto)

    def proyectos(self) -> list[str]:
        return self._proyectos.nombres()

    def programar(self, pedido: str, nombre: str) -> str:
        """Encarga un programa chico; avisa en voz alta cuando está y deja su carpeta abierta, minimizada."""
        from . import programador

        if self._simular:
            return "(simulado) Empezaría a hacer el programa."
        return programador.programar(
            pedido, nombre, self._config["cerebro"]["modelo_para_programar"], self._voz.decir,
            lambda destino: lanzador.abrir(str(destino), mostrar=False, nombre=destino.name))

    def puede_abrir(self, nombre: str) -> bool:
        """¿Hay un programa o sitio conocido con ese nombre?"""
        norma = normalizar(nombre)
        pestana = _PESTANA.match(norma)
        if pestana:
            if not pestana.group("resto"):
                return True
            nombre = pestana.group("resto")
            if self._navegador(nombre):
                return True
        return plataforma_de(normalizar(nombre)) == "spotify" or self._catalogo.resolver(nombre) is not None

    def _a_la_vista(self, accion: Accion) -> bool:
        """Todo se hace en segundo plano salvo que se pida verlo ("y mostrámelo")."""
        if accion.segundo_plano is None:
            return not self._config["segundo_plano"]
        return not accion.segundo_plano

    def _mostrar_que_haria(self, accion: Accion) -> None:
        modo = "a la vista" if self._a_la_vista(accion) else "en segundo plano"
        if accion.tipo == "abrir":
            registro.info("   (simulado) %s: %s", modo, self._catalogo.resolver(accion.objetivo))
        elif accion.tipo == "archivo":
            try:
                carpeta, nombre = self._ubicar(accion)
            except LookupError:
                registro.info("   (simulado) no existe la carpeta %s", accion.carpeta)
                return
            encontrados = archivos.buscar(nombre, carpeta, accion.formato) if nombre or accion.formato else []
            registro.info("   (simulado) %s, carpeta: %s, archivos: %s", modo, carpeta, [a.name for a in encontrados])
        elif accion.tipo in ("reproducir", "buscar", "nota"):
            registro.info("   (simulado) %s", modo)
        elif accion.tipo == "recordatorio":
            registro.info("   (simulado) %s: %s", describir_hora(datetime.fromtimestamp(accion.valor)), accion.objetivo)
        elif accion.tipo == "mensaje":
            self._buscar_chat_sin_enviar(accion)
        elif accion.tipo in ("proyecto", "proyecto_detener"):
            nombre = self._proyectos.resolver(accion.objetivo)
            registro.info("   (simulado) %s, proyecto: %s, pasos: %s", modo, nombre,
                          self._proyectos.pasos(nombre) if nombre else [])
        elif accion.tipo in ("apagar", "reiniciar", "suspender"):
            registro.info("   (simulado) pediría confirmación antes de %s el equipo", accion.tipo)

    def _buscar_chat_sin_enviar(self, accion: Accion) -> None:
        """Para comprobar que WhatsApp anda: encuentra el chat pero no lo abre ni escribe."""
        from . import whatsapp

        try:
            with whatsapp.Sesion() as sesion:
                sesion.esperar_chats()
                chat = sesion.buscar_chat(accion.destinatario)
            registro.info("   (simulado) chat encontrado: %s. No se envió nada.", chat[1] if chat else "ninguno")
        except whatsapp.SinVincular:
            registro.info("   (simulado) WhatsApp no está vinculado: ejecutá vincular_whatsapp.bat")
        except Exception:
            registro.exception("   (simulado) falló WhatsApp")

    # --- Abrir, buscar, cerrar ------------------------------------------------

    def _ventanas_del_programa(self, *nombres: str, candidatas: list[int] | None = None) -> list[int]:
        """Ventanas del programa nombrado (por cualquiera de sus nombres): por ejecutable o por título."""
        pedidos = {normalizar(nombre) for nombre in nombres if nombre}
        ejecutables = {_EJECUTABLES.get(pedido, pedido.replace(" ", "")) for pedido in pedidos}
        encontradas = []
        for hwnd in ventanas.ventanas_visibles() if candidatas is None else candidatas:
            proceso = ventanas.exe_de(hwnd).removesuffix(".exe")
            if proceso in ("", "explorer"):  # el escritorio: cerrarlo ofrece apagar la PC
                continue
            # "Documento - Word", "notas.txt: Bloc de notas": el nombre de la app va al final.
            app_en_titulo = normalizar(re.split(r" [-–—] |: ", ventanas.titulo(hwnd))[-1])
            if app_en_titulo in pedidos or any(proceso == e or parecido(proceso, e) >= 0.85 for e in ejecutables):
                encontradas.append(hwnd)
        return encontradas

    @staticmethod
    def _navegador(nombre: str) -> str | None:
        """Ruta del navegador nombrado ("brave", "chrome"), o None si no es un navegador instalado."""
        ruta = lanzador.programa(nombre)
        return ruta if ruta and os.path.basename(ruta).lower() in lanzador.NAVEGADORES else None

    def _abrir_pagina(self, url: str, mostrar: bool, navegador: str | None = None) -> bool:
        """Abre una página como pestaña nueva en la ventana del navegador que ya está abierta."""
        elegido = navegador or lanzador.navegador_predeterminado()
        adelante = ventanas.exe_de(ventanas.ventana_activa())
        # Si el navegador es lo que tiene adelante, la pestaña nueva la ve aunque no se "muestre" nada.
        self._pestana_a_la_vista = bool(elegido) and not mostrar and adelante == os.path.basename(elegido).lower()
        return lanzador.abrir_url(url, mostrar=mostrar, navegador=navegador)

    def _abrir(self, accion: Accion) -> None:
        mostrar = self._a_la_vista(accion)
        # Algo que ya está abierto no se puede "abrir en segundo plano": pedirlo es querer verlo,
        # salvo que se aclare lo contrario.
        traer = mostrar or (accion.segundo_plano is None and self._config.get("traer_lo_ya_abierto", True))
        pestana = _PESTANA.match(normalizar(accion.objetivo))
        if pestana:
            resto = pestana.group("resto")
            navegador = self._navegador(resto) if resto else None
            if not resto or navegador or resto == "navegador":
                elegido = os.path.basename(navegador or lanzador.navegador_predeterminado() or "").lower()
                ya_abierto = bool(ventanas.ventanas_de(elegido)) if elegido else False
                mostrar = mostrar or (traer and ya_abierto)
                self._decir("Abro una pestaña nueva")
                accion.segundo_plano = not mostrar
                if not self._abrir_pagina(_PESTANA_NUEVA, mostrar, navegador):
                    self._decir("No pude abrir el navegador")
                return
            accion.objetivo = resto  # "una pestaña con YouTube": lo que importa es qué abrir
        if plataforma_de(normalizar(accion.objetivo)) == "spotify" and spotify.disponible():
            if traer and spotify.ventana():
                mostrar, accion.segundo_plano = True, False
            self._decir("Abriendo Spotify")
            if not spotify.abrir(mostrar):
                self._decir("No pude abrir Spotify")
            return
        destino = self._catalogo.resolver(accion.objetivo)
        if destino is None:
            # Sin adivinar ni mandar a Google: se dice que no está. Hablando con el usuario, además se anota.
            self._decir(f"No encontré ningún programa ni sitio que se llame {accion.objetivo}.")
            if self._decir == self._voz.decir:
                notas.anotar_pendiente(f"Abrir: {accion.objetivo}")
            return
        if destino.es_sitio:
            self._decir(f"Abriendo {destino.nombre}")
            abierto = self._abrir_pagina(destino.comando, mostrar)
        else:
            abiertas = self._ventanas_del_programa(destino.nombre, accion.objetivo,
                                                   candidatas=ventanas.ventanas_de_programas())
            if abiertas:
                if traer:
                    ventanas.traer_al_frente(abiertas[0])
                    accion.segundo_plano = False
                    self._decir(f"{destino.nombre} ya estaba en marcha: va al frente")
                else:
                    self._decir(f"{destino.nombre} ya estaba en marcha, quedó donde estaba")
                return
            self._decir(f"Abriendo {destino.nombre}")
            abierto = lanzador.abrir(destino.comando, mostrar=mostrar, nombre=destino.nombre)
        if not abierto:
            self._decir(f"No pude abrir {destino.nombre}")

    def _buscar(self, accion: Accion) -> None:
        nombre, plantilla, codificar = _BUSCADORES[accion.plataforma or "google"]
        self._decir(f"Buscando {accion.objetivo} en {nombre}")
        destino = plantilla.format(codificar(accion.objetivo))
        if accion.plataforma == "spotify":
            lanzador.abrir(destino, mostrar=self._a_la_vista(accion), nombre="spotify")
        else:
            self._abrir_pagina(destino, self._a_la_vista(accion))

    def _cerrar(self, accion: Accion) -> None:
        pedido = normalizar(accion.objetivo)
        if _EJECUTABLES.get(pedido, pedido.replace(" ", "")) == "spotify":
            multimedia.pausar("spotify")  # si su ventana queda en la bandeja, que al menos deje de sonar
        abiertas = self._ventanas_del_programa(accion.objetivo)
        for hwnd in abiertas:
            ventanas.cerrar(hwnd)
        if abiertas:
            self._decir(f"Cerrando {accion.objetivo}")
        else:
            self._decir(f"No encontré ninguna ventana de {accion.objetivo}")

    def _cerrar_todo(self, accion: Accion) -> None:
        """Cierra las ventanas de programas, salvo las excepciones (objetivo: nombres separados por coma)."""
        excepciones = [normalizar(e).replace(" ", "") for e in accion.objetivo.split(",") if e.strip()]
        excepciones += [normalizar(e).replace(" ", "") for e in self._config["no_cerrar"]]
        cerrados = set()
        for hwnd in ventanas.ventanas_de_programas():
            proceso = ventanas.exe_de(hwnd).removesuffix(".exe")
            titulo = normalizar(ventanas.titulo(hwnd)).replace(" ", "")
            if not proceso or proceso in _NUNCA_CERRAR:
                continue
            if any(e in proceso or proceso in e or e in titulo for e in excepciones):
                continue
            ventanas.cerrar(hwnd)
            cerrados.add(proceso)
        if cerrados:
            registro.info("Cerrados: %s", ", ".join(sorted(cerrados)))
            self._decir(f"Cerré {len(cerrados)} programas: {', '.join(sorted(cerrados))}")
        else:
            self._decir("No había nada para cerrar")

    # --- Archivos -------------------------------------------------------------

    def _ubicar(self, accion: Accion) -> tuple[Path | None, str]:
        """Carpeta donde buscar y nombre del archivo. Lanza LookupError si la carpeta no existe."""
        if not accion.carpeta:
            return None, accion.objetivo
        if accion.objetivo:
            carpeta = archivos.resolver_carpeta(accion.carpeta)
            if carpeta is None:
                raise LookupError(accion.carpeta)
            return carpeta, accion.objetivo
        # Se dijo de corrido "en la carpeta X tal archivo": hay que ver dónde termina la carpeta.
        separado = archivos.separar_carpeta(accion.carpeta)
        if separado is None:
            raise LookupError(accion.carpeta)
        return separado

    def _archivo(self, accion: Accion) -> None:
        mostrar = self._a_la_vista(accion)
        try:
            carpeta, nombre = self._ubicar(accion)
        except LookupError:
            self._decir(f"No encontré la carpeta {accion.carpeta}")
            return
        if not nombre and not accion.formato:
            if carpeta is None:
                self._decir("No entendí qué archivo buscar")
                return
            self._decir(f"Abriendo la carpeta {carpeta.name}")
            lanzador.abrir(str(carpeta), mostrar=mostrar, nombre=carpeta.name)
            return
        encontrados = archivos.buscar(nombre, carpeta, accion.formato)
        if not encontrados:
            self._decir(f"No encontré ningún archivo que se llame {nombre or accion.formato}")
            return
        elegido = encontrados[0]
        registro.info("Archivo: %s", elegido)
        self._decir(f"Abro {elegido.stem}")
        self._abrir_archivo(elegido, accion.programa, mostrar)

    def _abrir_archivo(self, ruta: Path, programa: str | None, mostrar: bool) -> None:
        ejecutable = lanzador.programa(programa) if programa else None
        if programa and not ejecutable:
            self._decir(f"No encontré {programa}, lo abro con el programa de siempre")
        if ejecutable is None:
            # Si lo abre un navegador conviene saberlo, para no taparle la pestaña al usuario.
            try:
                _, asociado = win32api.FindExecutable(str(ruta))
            except pywintypes.error:
                asociado = ""
            if os.path.basename(asociado).lower() in lanzador.NAVEGADORES:
                ejecutable = asociado
        if ejecutable and os.path.basename(ejecutable).lower() in lanzador.NAVEGADORES:
            lanzador.abrir_url(ruta.as_uri(), mostrar=mostrar, navegador=ejecutable)
        elif ejecutable:
            lanzador.abrir(ejecutable, f'"{ruta}"', mostrar=mostrar, nombre=ruta.stem)
        else:
            lanzador.abrir(str(ruta), mostrar=mostrar, nombre=ruta.stem)

    # --- WhatsApp -------------------------------------------------------------

    def _mensaje(self, accion: Accion) -> None:
        from . import whatsapp  # solo se carga si se usa

        if whatsapp.se_sabe_sin_vincular():
            # Ya se comprobó antes: no hace falta abrir el navegador oculto y esperar para saberlo.
            self._decir("WhatsApp no está vinculado. Ejecutá vincular WhatsApp y escaneá el código.")
            return
        self._decir(f"Busco a {accion.destinatario} en WhatsApp")
        try:
            with whatsapp.Sesion() as sesion:
                sesion.esperar_chats()
                chat = sesion.buscar_chat(accion.destinatario)
                if chat is None:
                    self._decir(f"No encontré ningún chat que se llame {accion.destinatario}")
                    return
                nombre = re.sub(r"[^\w\s]", "", chat[1]).strip() or accion.destinatario  # sin emojis, para decirlo
                registro.info("WhatsApp: chat '%s'", chat[1])
                if self._config["confirmar_mensajes"] and not self._confirmar(
                        f"¿Le mando {accion.objetivo} a {nombre}?"):
                    self._decir("Listo, no mando nada")
                    return
                if sesion.enviar(chat, accion.objetivo):
                    self._decir("Mensaje enviado")
                else:
                    self._decir("No pude confirmar que el mensaje se haya enviado")
        except whatsapp.SinVincular:
            self._decir("WhatsApp no está vinculado. Ejecutá vincular WhatsApp y escaneá el código.")
        except Exception:
            registro.exception("Falló WhatsApp")
            self._decir("No pude usar WhatsApp")

    # --- Música ---------------------------------------------------------------

    def _reproducir(self, accion: Accion) -> None:
        mostrar = self._a_la_vista(accion)
        plataforma = accion.plataforma or self._config["reproductor"]
        if plataforma == "youtube":
            url = youtube.primer_video(accion.objetivo) or youtube.url_resultados(accion.objetivo)
            self._abrir_pagina(url, mostrar)
            if mostrar or self._pestana_a_la_vista:
                self._decir(f"Pongo {accion.objetivo} en YouTube")
            else:
                # El navegador no arranca un video en una pestaña que nunca estuvo a la vista.
                self._decir(f"Dejé {accion.objetivo} abierto en YouTube. Arranca cuando mires la pestaña.")
            return
        self._decir(f"Pongo {accion.objetivo}")
        if not spotify.disponible():
            # Sin la línea de comandos de Spotify solo se puede dejar la búsqueda abierta.
            lanzador.abrir(_BUSCADORES["spotify"][1].format(quote(accion.objetivo)), mostrar=mostrar, nombre="spotify")
            self._decir("Te dejé la búsqueda abierta en Spotify")
            return
        actual = None if spotify.sin_control() else spotify.reproducir(accion.objetivo, mostrar)
        if actual:
            registro.info("Sonando: %s", actual)
            if self._decir != self._voz.decir:  # al cerebro sí le sirve saber qué quedó sonando
                self._decir(f"Quedó sonando {actual}.")
        elif spotify.sin_control():
            # Spotify está abierto pero no se deja manejar: que haya música igual, y que se sepa por qué.
            self._decir("Spotify está abierto pero no se deja controlar desde afuera (pasa después de que se "
                        "actualiza), así que va por YouTube.")
            self._reproducir(Accion("reproducir", accion.objetivo, "youtube", accion.segundo_plano))
        else:
            self._decir(f"No pude poner {accion.objetivo} en Spotify")

    def _musica_a_gusto(self, accion: Accion) -> None:
        """"Poné algo lindo": sin el cerebro para elegir, va lo que diga config.json (o lo dicho, tal cual)."""
        elegido = self._config.get("musica_a_gusto") or accion.objetivo
        self._reproducir(Accion("reproducir", elegido, accion.plataforma, accion.segundo_plano))

    @staticmethod
    def _origen(accion: Accion) -> str | None:
        """Dónde suena lo que hay que controlar: "spotify", "navegador" (YouTube) o None (lo que sea)."""
        return {"spotify": "spotify", "youtube": "navegador", "navegador": "navegador"}.get(accion.plataforma or "")

    def _pausar(self, accion: Accion) -> None:
        if not multimedia.pausar(self._origen(accion)) and accion.plataforma:
            self._decir(f"No había nada sonando en {accion.plataforma}")

    def _continuar(self, accion: Accion) -> None:
        if not multimedia.continuar(self._origen(accion)):
            self._decir("No hay nada para reproducir" + (f" en {accion.plataforma}" if accion.plataforma else ""))

    def _siguiente(self, accion: Accion) -> None:
        multimedia.siguiente(self._origen(accion))

    def _anterior(self, accion: Accion) -> None:
        multimedia.anterior(self._origen(accion))

    # --- Volumen (cada pulsación de la tecla mueve 2 puntos) -------------------

    def _volumen(self, accion: Accion) -> None:
        if accion.plataforma == "spotify":
            self._volumen_de_spotify(accion.valor)
            return
        ventanas.tecla(ventanas.VK_BAJAR_VOLUMEN, 50)
        ventanas.tecla(ventanas.VK_SUBIR_VOLUMEN, accion.valor // 2)

    def _volumen_relativo(self, accion: Accion) -> None:
        if accion.plataforma == "spotify":
            actual = None if spotify.sin_control() else spotify.volumen()
            if actual is None:
                self._decir("No pude leer el volumen de Spotify")
            else:
                self._volumen_de_spotify(actual + accion.valor)
            return
        tecla = ventanas.VK_SUBIR_VOLUMEN if accion.valor > 0 else ventanas.VK_BAJAR_VOLUMEN
        ventanas.tecla(tecla, abs(accion.valor) // 2)

    def _volumen_de_spotify(self, nivel: int) -> None:
        """Solo Spotify: el resto del sonido de la PC queda como está."""
        nivel = max(0, min(100, nivel))
        if spotify.fijar_volumen(nivel):
            self._decir(f"Spotify al {nivel} por ciento")
        else:
            self._decir("No pude cambiar el volumen de Spotify")

    def _silenciar(self, accion: Accion) -> None:
        ventanas.tecla(ventanas.VK_SILENCIO)

    # --- Recordatorios --------------------------------------------------------

    def _recordatorio(self, accion: Accion) -> None:
        momento = datetime.fromtimestamp(accion.valor)
        if self._recordatorios is None:
            self._decir("Los recordatorios solo funcionan con el asistente escuchando")
            return
        self._recordatorios.agregar(momento, accion.objetivo)
        self._decir(f"Dale, te aviso {describir_hora(momento)}")

    def _ver_recordatorios(self, accion: Accion) -> None:
        pendientes = self._recordatorios.pendientes() if self._recordatorios else []
        if not pendientes:
            self._decir("No tenés recordatorios pendientes")
            return
        detalle = "; ".join(f"{describir_hora(r.momento)}, {r.mensaje}" for r in pendientes[:5])
        self._decir(f"Tenés {len(pendientes)}: {detalle}")

    def _cancelar_recordatorio(self, accion: Accion) -> None:
        cancelados = self._recordatorios.cancelar(accion.objetivo) if self._recordatorios else []
        if cancelados:
            self._decir("Cancelé " + "; ".join(f"el de {describir_hora(r.momento)}, {r.mensaje}" for r in cancelados))
        else:
            self._decir("No encontré ese recordatorio")

    # --- Notas en el Bloc de notas ----------------------------------------------

    def _nota(self, accion: Accion) -> None:
        mostrar = self._a_la_vista(accion)
        ruta = None if accion.valor == 1 else notas.ultima_reciente()
        if ruta is None:
            ruta = notas.nueva(accion.objetivo)
            notas.abrir(ruta, mostrar)
            self._decir(f"Listo, lo escribí en una nota nueva: {ruta.stem[17:]}")
            return
        notas.agregar(ruta, accion.objetivo)
        if not notas.refrescar_vista(ruta):
            # Estaba cerrada o en otra pestaña: se reabre y se actualiza lo que muestra.
            notas.abrir(ruta, mostrar)
            for _ in range(15):
                time.sleep(0.2)
                if notas.refrescar_vista(ruta):
                    break
        self._decir("Listo, lo sumé a la nota")

    def _nota_borrar(self, accion: Accion) -> None:
        ruta = notas.ultima_reciente()
        borrada = notas.quitar_ultima_linea(ruta) if ruta else None
        if borrada is None:
            self._decir("No hay ninguna nota reciente con algo para borrar")
            return
        notas.refrescar_vista(ruta)
        self._decir(f"Borré la última línea de la nota: {borrada}")

    # --- Volumen de la voz de Claudio (no toca el de la PC) ---------------------

    def _volumen_voz(self, accion: Accion) -> None:
        self._fijar_volumen_voz(accion.valor)

    def _volumen_voz_relativo(self, accion: Accion) -> None:
        self._fijar_volumen_voz(round(self._voz.volumen * 100) + accion.valor)

    def _fijar_volumen_voz(self, nivel: int) -> None:
        nivel = max(5, min(100, nivel))  # en 0 no habría forma de oír la respuesta
        self._voz.volumen = nivel / 100
        configuracion.guardar_preferencia("volumen_voz", nivel / 100)
        self._decir(f"Listo, ahora hablo al {nivel} por ciento")

    # --- Varias ---------------------------------------------------------------

    def _hora(self, accion: Accion) -> None:
        dicha = hora_hablada(datetime.now(), con_franja=True)
        self._decir(dicha[:1].upper() + dicha[1:])

    def _fecha(self, accion: Accion) -> None:
        hoy = datetime.now()
        self._decir(f"Hoy es {_DIAS[hoy.weekday()]} {hoy.day} de {_MESES[hoy.month - 1]} de {hoy.year}")

    def _saludo(self, accion: Accion) -> None:
        self._decir("Acá estoy, ¿qué necesitás?")

    def _gracias(self, accion: Accion) -> None:
        self._decir("De nada")

    def _bloquear(self, accion: Accion) -> None:
        self._decir("Bloqueando el equipo")
        self._voz.esperar()
        ventanas.bloquear_equipo()

    def _salir(self, accion: Accion) -> None:
        self._decir("Chau, nos vemos")
        self._voz.esperar()
        raise Salir

    # --- Apagar el equipo (siempre con confirmación y con tiempo para arrepentirse) ----

    def _apagar(self, accion: Accion) -> None:
        self._programar_apagado("/s", "¿Seguro que apago la computadora?", "Apago")

    def _reiniciar(self, accion: Accion) -> None:
        self._programar_apagado("/r", "¿Seguro que reinicio la computadora?", "Reinicio")

    def _programar_apagado(self, modo: str, pregunta: str, verbo: str) -> None:
        if not self._confirmar(pregunta):
            self._decir("Listo, no toco nada")
            return
        hecho = subprocess.run(["shutdown", modo, "/t", str(_SEGUNDOS_PARA_APAGAR)], capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        if hecho.returncode:
            self._decir("Windows no me dejó hacerlo")
            return
        registro.info("%s el equipo en %s segundos", verbo, _SEGUNDOS_PARA_APAGAR)
        self._decir(f"{verbo} en un minuto: guardá lo que tengas abierto. Si te arrepentís, decime cancelá el apagado.")

    def _cancelar_apagado(self, accion: Accion) -> None:
        hecho = subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        self._decir("Listo, cancelé el apagado" if hecho.returncode == 0 else "No había ningún apagado en marcha")

    def _suspender(self, accion: Accion) -> None:
        if not self._confirmar("¿Suspendo la computadora?"):
            self._decir("Listo, no toco nada")
            return
        self._decir("Suspendo el equipo")
        self._voz.esperar()
        ctypes.windll.powrprof.SetSuspendState(0, 0, 0)

    # --- Proyectos de programación ---------------------------------------------

    def _proyecto(self, accion: Accion) -> None:
        nombre = self._proyecto_pedido(accion)
        if nombre:
            self._decir(self._proyectos.levantar(nombre, self._a_la_vista(accion)))

    def _proyecto_detener(self, accion: Accion) -> None:
        nombre = self._proyecto_pedido(accion)
        if nombre:
            self._decir(self._proyectos.bajar(nombre))

    def _proyecto_estado(self, accion: Accion) -> None:
        nombre = self._proyecto_pedido(accion)
        if nombre:
            self._decir(self._proyectos.estado(nombre))

    def _proyecto_pedido(self, accion: Accion) -> str | None:
        nombre = self._proyectos.resolver(accion.objetivo)
        if nombre is None:
            conocidos = ", ".join(self._proyectos.nombres()) or "ninguno"
            self._decir(f"No tengo cargado ningún proyecto que se llame {accion.objetivo}. Conozco: {conocidos}.")
        return nombre

    def _desconocido(self, accion: Accion) -> None:
        notas.anotar_pendiente(accion.objetivo)
        self._decir("No entendí o todavía no sé hacer eso. Lo anoté para más adelante.")
