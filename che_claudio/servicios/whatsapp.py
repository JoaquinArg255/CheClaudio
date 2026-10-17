"""Mensajes de WhatsApp por WhatsApp Web, en un navegador oculto con perfil propio.

No toca la app de WhatsApp ni el navegador de uso diario: abre un Edge sin
ventana, con su propia sesión (se vincula una vez escaneando el QR), y lo maneja
por el protocolo de depuración. La sesión queda guardada en `perfil_whatsapp/`.
"""
import json
import logging
import re
import subprocess
import time
import urllib.error
import urllib.request

import websocket
import win32api

from ..config import DATOS
from ..sistema import lanzador, ventanas
from ..texto import normalizar, parecido

registro = logging.getLogger("che_claudio")

PERFIL = DATOS / "perfil_whatsapp"
_URL = "https://web.whatsapp.com"
_PID = PERFIL / "che_claudio.pid"
_PUERTO = PERFIL / "DevToolsActivePort"

_FILAS = '#pane-side [role="listitem"], #pane-side [role="row"]'
_JS_ESTADO = """(() => document.querySelector('#pane-side') ? 'listo'
    : document.querySelector('canvas') ? 'qr' : 'cargando')()"""
_JS_CENTRO = """((elemento) => {
    if (!elemento) return null;
    elemento.scrollIntoView({block: 'center'});
    const r = elemento.getBoundingClientRect();
    return {x: r.x + r.width / 2, y: r.y + r.height / 2};
})"""
_JS_BUSCADOR = """(document.querySelector('#side div[contenteditable="true"]')
    || document.querySelector('#side input, #side [role="textbox"]'))"""
_JS_REDACCION = """(() => {
    const cajas = document.querySelectorAll(
        '#main footer div[contenteditable="true"], #main div[contenteditable="true"][role="textbox"]');
    return cajas[cajas.length - 1];
})()"""
_JS_TITULOS = f"""(() => [...document.querySelectorAll('{_FILAS}')].map((fila, i) => {{
    const titulo = fila.querySelector('span[title]');
    return titulo ? {{i, titulo: titulo.getAttribute('title')}} : null;
}}).filter(Boolean))()"""
_JS_CHAT_ABIERTO = """(() => {
    const e = document.querySelector('#main header span[dir="auto"], #main header [title]');
    return e ? (e.getAttribute('title') || e.textContent) : null;
})()"""
_JS_ENVIO = """(() => {
    const salientes = document.querySelectorAll('#main .message-out');
    const ultimo = salientes[salientes.length - 1];
    return {
        salientes: salientes.length,
        ultimo: ultimo ? ultimo.innerText : null,
        pendiente: !!(ultimo && ultimo.querySelector('[data-icon="msg-time"]')),
    };
})()"""


class SinVincular(Exception):
    """WhatsApp Web pide escanear el QR: falta vincular (o se desvinculó)."""


# Comprobar que falta vincular lleva cerca de un minuto (hay que abrir el navegador oculto y esperar el
# QR): una vez sabido, queda anotado acá hasta que se vincule.
_SIN_VINCULAR = PERFIL / "sin_vincular"


def se_sabe_sin_vincular() -> bool:
    return _SIN_VINCULAR.exists() or not PERFIL.exists()


def _clave(texto: str) -> str:
    """Para comparar nombres de chats: sin tildes, emojis ni signos."""
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", normalizar(texto)).split())


def _coincidencia(pedido: str, titulo: str) -> float:
    pedido, titulo = _clave(pedido), _clave(titulo)
    if not pedido or not titulo:
        return 0.0
    if pedido == titulo:
        return 1.0
    if set(pedido.split()) <= set(titulo.split()):
        return 0.9  # "tortugas" para "Tortugas 2026"
    # Un nombre solo parecido ("Tortuga") nunca le gana a uno que tiene todas las palabras pedidas.
    return min(parecido(pedido, titulo), 0.89)


class Sesion:
    """Un navegador con WhatsApp Web abierto. Usar con `with`."""

    def __init__(self, visible: bool = False):
        self._visible = visible
        self._proceso = None
        self._ws = None
        self._pedidos = 0

    # --- Navegador ------------------------------------------------------------

    def __enter__(self):
        navegador = lanzador.programa("edge") or lanzador.programa("chrome")
        if not navegador:
            raise RuntimeError("Hace falta Microsoft Edge o Google Chrome para WhatsApp Web")
        PERFIL.mkdir(parents=True, exist_ok=True)
        self._cerrar_anterior()
        _PUERTO.unlink(missing_ok=True)
        # Sin ventana el navegador se anuncia como "Headless" y WhatsApp lo rechaza.
        version = win32api.GetFileVersionInfo(navegador, "\\")["FileVersionMS"] >> 16
        agente = (f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  f"Chrome/{version}.0.0.0 Safari/537.36" + (f" Edg/{version}.0.0.0" if "edge" in navegador.lower() else ""))
        argumentos = [
            navegador, f"--user-data-dir={PERFIL}", "--remote-debugging-port=0", "--no-first-run",
            "--no-default-browser-check", "--lang=es-AR", "--window-size=1280,900", f"--user-agent={agente}",
            f"--app={_URL}" if self._visible else "--headless=new",
        ]
        self._proceso = subprocess.Popen(argumentos, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ventanas.anotar_proceso(_PID, self._proceso.pid)
        try:
            self._conectar()
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_):
        try:
            if self._ws:
                self._cdp("Browser.close")  # cierre prolijo: guarda la sesión
                self._ws.close()
        except Exception:
            pass
        if self._proceso:
            try:
                self._proceso.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self._proceso.kill()
        _PID.unlink(missing_ok=True)

    @staticmethod
    def _cerrar_anterior() -> None:
        """Si quedó un navegador de una corrida anterior, el perfil está tomado."""
        if ventanas.terminar_anotado(_PID):
            time.sleep(1)  # que suelte el perfil antes de abrir otro

    def _conectar(self) -> None:
        limite = time.monotonic() + 20
        while not _PUERTO.exists():
            if time.monotonic() > limite:
                raise RuntimeError("El navegador de WhatsApp no arrancó")
            time.sleep(0.1)
        base = f"http://127.0.0.1:{_PUERTO.read_text().split()[0]}"
        pagina = None
        while pagina is None and time.monotonic() < limite:
            try:
                destinos = json.load(urllib.request.urlopen(f"{base}/json/list", timeout=5))
                pagina = next((d for d in destinos if d["type"] == "page"), None)
                if pagina is None and not self._visible:
                    pedido = urllib.request.Request(f"{base}/json/new?about:blank", method="PUT")
                    pagina = json.load(urllib.request.urlopen(pedido, timeout=5))
            except (urllib.error.URLError, OSError, ValueError):
                pass
            if pagina is None:
                time.sleep(0.3)
        if pagina is None:
            raise RuntimeError("No pude conectarme al navegador de WhatsApp")
        self._ws = websocket.create_connection(pagina["webSocketDebuggerUrl"], suppress_origin=True, timeout=30)
        if not self._visible:
            self._cdp("Page.navigate", url=_URL)

    def _cdp(self, metodo: str, **parametros) -> dict:
        self._pedidos += 1
        self._ws.send(json.dumps({"id": self._pedidos, "method": metodo, "params": parametros}))
        while True:
            respuesta = json.loads(self._ws.recv())
            if respuesta.get("id") == self._pedidos:
                if "error" in respuesta:
                    raise RuntimeError(f"{metodo}: {respuesta['error'].get('message')}")
                return respuesta.get("result", {})

    def _js(self, expresion: str):
        resultado = self._cdp("Runtime.evaluate", expression=expresion, returnByValue=True)
        if "exceptionDetails" in resultado:
            raise RuntimeError(resultado["exceptionDetails"].get("text", "error de JavaScript"))
        return resultado["result"].get("value")

    def _click(self, elemento_js: str) -> bool:
        """Click real (por coordenadas) sobre el elemento que devuelve la expresión."""
        centro = self._js(f"{_JS_CENTRO}({elemento_js})")
        if not centro:
            return False
        for tipo in ("mousePressed", "mouseReleased"):
            self._cdp("Input.dispatchMouseEvent", type=tipo, x=centro["x"], y=centro["y"], button="left",
                      clickCount=1)
        return True

    def _enter(self) -> None:
        comunes = {"key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13}
        self._cdp("Input.dispatchKeyEvent", type="keyDown", text="\r", **comunes)
        self._cdp("Input.dispatchKeyEvent", type="keyUp", **comunes)

    # --- WhatsApp -------------------------------------------------------------

    def estado(self) -> str:
        """'listo' (se ven los chats), 'qr' (pide vincular) o 'cargando'."""
        return self._js(_JS_ESTADO)

    def esperar_chats(self, segundos: float = 60) -> None:
        limite = time.monotonic() + segundos
        veces_qr = 0
        while time.monotonic() < limite:
            estado = self.estado()
            if estado == "listo":
                _SIN_VINCULAR.unlink(missing_ok=True)
                time.sleep(1.0)  # termina de acomodar la lista
                return
            veces_qr = veces_qr + 1 if estado == "qr" else 0
            if veces_qr >= 3 and not self._visible:
                _SIN_VINCULAR.write_text("WhatsApp Web pidió el QR. Se borra solo al vincular.", encoding="utf-8")
                raise SinVincular
            time.sleep(1.0)
        raise TimeoutError("WhatsApp Web no terminó de cargar")

    def buscar_chat(self, nombre: str) -> tuple[int, str] | None:
        """Busca el chat por nombre. Devuelve (posición en la lista, nombre real) o None."""
        if not self._click(_JS_BUSCADOR):
            raise RuntimeError("No encontré el buscador de WhatsApp Web (¿cambió la página?)")
        self._cdp("Input.insertText", text=nombre)  # la página es nueva: el buscador está vacío
        mejor = anterior = None
        limite = time.monotonic() + 8
        while time.monotonic() < limite:
            time.sleep(0.7)
            filas = self._js(_JS_TITULOS) or []
            puntuadas = sorted(((-_coincidencia(nombre, f["titulo"]), f["i"], f["titulo"]) for f in filas))
            mejor = puntuadas[0] if puntuadas and -puntuadas[0][0] >= 0.8 else None
            if mejor and anterior and mejor[2] == anterior[2]:  # dos lecturas iguales: la lista ya se filtró
                return mejor[1], mejor[2]
            anterior = mejor
        registro.info("WhatsApp: no hay chats parecidos a '%s'", nombre)
        return None

    def enviar(self, chat: tuple[int, str], texto: str) -> bool:
        """Abre el chat, verifica que sea el correcto, escribe y envía."""
        posicion, titulo = chat
        if not self._click(f"document.querySelectorAll('{_FILAS}')[{posicion}]"):
            return False
        limite = time.monotonic() + 6
        while _clave(self._js(_JS_CHAT_ABIERTO) or "") != _clave(titulo):
            if time.monotonic() > limite:
                registro.warning("WhatsApp: no se abrió el chat esperado (%s)", titulo)
                return False
            time.sleep(0.3)
        antes = self._js(_JS_ENVIO)
        if not self._click(_JS_REDACCION):
            registro.warning("WhatsApp: no encontré dónde escribir el mensaje")
            return False
        self._cdp("Input.insertText", text=texto)
        time.sleep(0.4)
        escrito = self._js(f"(({_JS_REDACCION}) || {{}}).innerText") or ""
        if texto.strip() not in escrito:
            registro.warning("WhatsApp: el texto no quedó escrito, no envío nada")
            return False
        self._enter()
        # Enviado = la caja quedó vacía y el último mensaje ya no tiene el relojito.
        limite = time.monotonic() + 20
        while time.monotonic() < limite:
            time.sleep(0.5)
            vacia = not (self._js(f"(({_JS_REDACCION}) || {{}}).innerText") or "").strip()
            envio = self._js(_JS_ENVIO)
            if vacia and envio["salientes"] == 0 and time.monotonic() > limite - 16:
                return True  # la página cambió y no se pueden contar los mensajes: se da por enviado
            if vacia and envio["salientes"] >= max(1, antes["salientes"]) and not envio["pendiente"] \
                    and texto.strip() in (envio["ultimo"] or ""):
                time.sleep(1.0)
                return True
        return False


def vincular() -> bool:
    """Abre WhatsApp Web a la vista para escanear el QR. True si quedó vinculado."""
    with Sesion(visible=True) as sesion:
        print("Se abrió una ventana con WhatsApp Web.")
        print("En el teléfono: WhatsApp > Dispositivos vinculados > Vincular un dispositivo, y escaneá el QR.")
        print("Esperando (hasta 5 minutos)...")
        try:
            sesion.esperar_chats(300)
        except (TimeoutError, RuntimeError, websocket.WebSocketException, OSError):
            print("No se llegó a vincular.")
            return False
        print("Vinculado. Guardando la sesión...")
        time.sleep(8)  # que termine de sincronizar antes de cerrar
        return True
