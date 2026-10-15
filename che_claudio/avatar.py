"""El personaje en pantalla: flota sobre todo, no recibe clicks ni foco.

Se dibuja con Pillow cuadro a cuadro y se muestra en una ventana "layered" de
Windows, que permite transparencia por píxel (bordes suaves, sombra).
"""
import ctypes
import logging
import math
import random
import textwrap
import threading
import time
from ctypes import wintypes

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

registro = logging.getLogger("che_claudio")

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_kernel32 = ctypes.windll.kernel32

_WS_POPUP = 0x80000000
_WS_EX_LAYERED, _WS_EX_TRANSPARENT, _WS_EX_TOPMOST = 0x00080000, 0x00000020, 0x00000008
_WS_EX_TOOLWINDOW, _WS_EX_NOACTIVATE = 0x00000080, 0x08000000
_SW_HIDE, _SW_SHOWNOACTIVATE = 0, 4
_ULW_ALPHA, _AC_SRC_ALPHA = 0x2, 0x1
_HWND_TOPMOST = -1
_SWP_NOMOVE, _SWP_NOSIZE, _SWP_NOACTIVATE = 0x2, 0x1, 0x10
_SPI_GETWORKAREA = 0x30
_PM_REMOVE = 0x1

_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.DefWindowProcW.restype = ctypes.c_ssize_t
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID]
# Los identificadores son de 64 bits: sin declarar los tipos, ctypes los recorta o los rechaza.
_user32.GetDC.restype = wintypes.HDC
_user32.GetDC.argtypes = [wintypes.HWND]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateDIBSection.restype = wintypes.HBITMAP
_gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                    wintypes.HANDLE, wintypes.DWORD]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.c_void_p, ctypes.c_void_p, wintypes.HDC,
                                       ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wintypes.UINT]
_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.PeekMessageW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]


class _WNDCLASS(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", _WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte), ("SourceConstantAlpha", ctypes.c_ubyte),
                ("AlphaFormat", ctypes.c_ubyte)]


# --- Dibujo --------------------------------------------------------------------

_ANCHO, _ALTO = 400, 300  # tamaño lógico de la ventana
_SUPER = 2  # se dibuja al doble y se reduce: bordes suaves

_CELESTE = (116, 172, 223)
_BLANCO = (244, 247, 251)
_VISOR = (22, 35, 58)
_LUZ = (127, 231, 255)
_SOL = (246, 180, 14)
_ROSA = (255, 143, 177)


def _fuente(tamano: int):
    for nombre in ("seguisb.ttf", "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(nombre, tamano)
        except OSError:
            continue
    return ImageFont.load_default()


class Dibujante:
    """Dibuja un cuadro del personaje según su estado. Sin ventanas: se puede probar suelto."""

    def __init__(self, escala: float = 1.0):
        self.escala = escala
        self.ancho, self.alto = int(_ANCHO * escala), int(_ALTO * escala)
        self._k = _SUPER * escala
        self._fuente = _fuente(int(15 * self._k))
        self._sombra = self._dibujar_sombra()
        self._proximo_parpadeo = time.monotonic() + 2
        self._mirada = (0.0, 0.0)
        self._mirada_destino = (0.0, 0.0)

    def _p(self, *valores):
        return [v * self._k for v in valores]

    def _dibujar_sombra(self) -> Image.Image:
        capa = Image.new("RGBA", (int(_ANCHO * self._k), int(_ALTO * self._k)), (0, 0, 0, 0))
        ImageDraw.Draw(capa).ellipse(self._p(278, 262, 362, 278), fill=(0, 0, 0, 90))
        return capa.filter(ImageFilter.GaussianBlur(6 * self._k))

    def _burbuja(self, lienzo: ImageDraw.ImageDraw, texto: str) -> None:
        lineas = []
        for parrafo in texto.split("\n"):
            lineas.extend(textwrap.wrap(parrafo, 30) or [""])
        if len(lineas) > 5:
            lineas = lineas[:5]
            lineas[-1] = lineas[-1][:27] + "..."
        alto_linea = 20
        alto = 16 + alto_linea * len(lineas)
        ancho = max(self._fuente.getlength(linea) for linea in lineas) / self._k + 24
        derecha, abajo = 248, 150
        izquierda, arriba = max(6, derecha - ancho), abajo - alto
        lienzo.rounded_rectangle(self._p(izquierda, arriba, derecha, abajo), 14 * self._k,
                                 fill=(255, 255, 255, 238), outline=_CELESTE + (255,), width=int(2 * self._k))
        lienzo.polygon(self._p(derecha - 2, abajo - 30, derecha + 14, abajo - 18, derecha - 2, abajo - 14),
                       fill=(255, 255, 255, 238))
        for i, linea in enumerate(lineas):
            lienzo.text(self._p(izquierda + 12, arriba + 7 + i * alto_linea), linea, font=self._fuente,
                        fill=_VISOR + (255,))

    def cuadro(self, t: float, estado: str, boca: float, texto: str) -> Image.Image:
        """estado: 'escuchando', 'pensando', 'hablando' o 'reposo'. boca: apertura 0..1."""
        imagen = self._sombra.copy()
        lienzo = ImageDraw.Draw(imagen)
        dy = 4 * math.sin(t * 2 * math.pi / 2.4)  # flota

        def p(*valores):
            return [v * self._k if i % 2 == 0 else (v + dy) * self._k for i, v in enumerate(valores)]

        # Antena con el sol: brilla cuando escucha.
        lienzo.line(p(320, 96, 320, 72), fill=_CELESTE + (255,), width=int(4 * self._k))
        if estado == "escuchando":
            halo = 10 + 5 * (1 + math.sin(t * 6)) / 2
            lienzo.ellipse(p(320 - halo, 64 - halo, 320 + halo, 64 + halo), fill=_SOL + (90,))
        lienzo.ellipse(p(311, 55, 329, 73), fill=_SOL + (255,))

        # Cuerpo con franja blanca, como la bandera.
        lienzo.rounded_rectangle(p(282, 200, 358, 250), 20 * self._k, fill=_CELESTE + (255,))
        lienzo.rectangle(p(282, 218, 358, 230), fill=(255, 255, 255, 255))

        # Cabeza y visor.
        lienzo.rounded_rectangle(p(255, 95, 385, 207), 38 * self._k, fill=_BLANCO + (255,),
                                 outline=_CELESTE + (255,), width=int(4 * self._k))
        lienzo.rounded_rectangle(p(268, 113, 372, 192), 26 * self._k, fill=_VISOR + (255,))

        # Ojos: parpadean y miran.
        ahora = time.monotonic()
        if ahora > self._proximo_parpadeo + 0.15:
            self._proximo_parpadeo = ahora + random.uniform(2.5, 5.5)
        parpadeo = self._proximo_parpadeo <= ahora <= self._proximo_parpadeo + 0.15
        if estado == "pensando":
            self._mirada_destino = (6.0, -6.0)
        elif random.random() < 0.01:
            self._mirada_destino = (random.uniform(-5, 5), random.uniform(-3, 3))
        mx = self._mirada[0] + (self._mirada_destino[0] - self._mirada[0]) * 0.15
        my = self._mirada[1] + (self._mirada_destino[1] - self._mirada[1]) * 0.15
        self._mirada = (mx, my)
        alto_ojo = 3 if parpadeo else (28 if estado == "escuchando" else 24)
        for cx in (300, 340):
            lienzo.rounded_rectangle(p(cx - 8 + mx, 146 - alto_ojo / 2 + my, cx + 8 + mx, 146 + alto_ojo / 2 + my),
                                     6 * self._k, fill=_LUZ + (255,))

        # Mejillas y boca.
        for cx in (284, 356):
            lienzo.rounded_rectangle(p(cx - 6, 170, cx + 6, 174), 2 * self._k, fill=_ROSA + (190,))
        alto_boca = 3 + 13 * max(0.0, min(1.0, boca))
        lienzo.rounded_rectangle(p(309, 176 - alto_boca / 2, 331, 176 + alto_boca / 2),
                                 min(alto_boca / 2, 5) * self._k, fill=_LUZ + (255,))

        # Pensando: puntitos que se turnan.
        if estado == "pensando":
            for i in range(3):
                radio = 3 + 2.5 * max(0.0, math.sin(t * 6 - i * 0.9))
                cx, cy = 346 + i * 13, 58
                lienzo.ellipse(p(cx - radio, cy - radio, cx + radio, cy + radio), fill=_CELESTE + (255,))

        if texto:
            self._burbuja(lienzo, texto)
        return imagen.reduce(_SUPER)


# --- Ventana -------------------------------------------------------------------

class Avatar:
    """Maneja el personaje desde cualquier hilo: los métodos solo cambian el estado."""

    # Estar en pantalla significa "te estoy escuchando": fuera de eso se queda apenas un instante.
    _FADE_IN, _FADE_OUT, _OCULTAR_TRAS = 0.2, 0.4, 1.5

    def __init__(self, activo: bool = True, escala: float = 1.0):
        self._activo = activo
        self._escala = escala
        self._candado = threading.Lock()
        self._estado = "reposo"
        self._texto = ""
        self._envolvente: list[float] = []
        self._inicio_habla = 0.0
        self._despues_de_hablar = "reposo"
        self._ocultar_en = 0.0
        self._seguir = True
        if activo:
            threading.Thread(target=self._correr, daemon=True, name="avatar").start()

    # --- API ---

    def _pasar_a(self, estado: str) -> None:
        """Cambia de estado; si está hablando, el cambio queda para cuando termine la frase."""
        with self._candado:
            if self._estado == "hablando":
                self._despues_de_hablar = estado
                return
            self._estado = estado
            if estado == "reposo":
                self._ocultar_en = time.monotonic() + self._OCULTAR_TRAS
            else:
                self._texto = ""  # escuchando o pensando: lo dicho antes ya no corresponde

    def escuchando(self) -> None:
        """Aparece con la antena encendida: está esperando que le hablen."""
        self._pasar_a("escuchando")

    def pensando(self) -> None:
        self._pasar_a("pensando")

    def hablar(self, texto: str, envolvente: list[float]) -> None:
        """Muestra el texto y mueve la boca según el volumen de cada cuadro (30 por segundo)."""
        with self._candado:
            if self._estado != "hablando":
                # Al terminar vuelve a como estaba: si escuchaba (seguía atento), sigue a la vista.
                self._despues_de_hablar = "escuchando" if self._estado == "escuchando" else "reposo"
            self._estado = "hablando"
            self._texto = texto
            self._envolvente = envolvente
            self._inicio_habla = time.monotonic()

    def reposo(self) -> None:
        """Termina la interacción: se oculta solo unos segundos después."""
        self._pasar_a("reposo")

    def ocultar(self) -> None:
        """Se va ya (o apenas termine la frase): Claudio dejó de escuchar."""
        self._pasar_a("reposo")
        with self._candado:
            if self._estado == "reposo":
                self._ocultar_en = 0.0

    def cerrar(self) -> None:
        self._seguir = False

    # --- Hilo de la ventana ---

    def _crear_ventana(self, ancho: int, alto: int):
        instancia = _kernel32.GetModuleHandleW(None)
        self._wndproc = _WNDPROC(lambda h, m, w, l: _user32.DefWindowProcW(h, m, w, l))
        clase = _WNDCLASS(lpfnWndProc=self._wndproc, hInstance=instancia, lpszClassName="CheClaudioAvatar")
        _user32.RegisterClassW(ctypes.byref(clase))
        area = wintypes.RECT()
        _user32.SystemParametersInfoW(_SPI_GETWORKAREA, 0, ctypes.byref(area), 0)
        self._x, self._y = area.right - ancho - 12, area.bottom - alto
        estilo = _WS_EX_LAYERED | _WS_EX_TRANSPARENT | _WS_EX_TOPMOST | _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE
        return _user32.CreateWindowExW(estilo, "CheClaudioAvatar", "Che Claudio", _WS_POPUP, self._x, self._y,
                                       ancho, alto, None, None, instancia, None)

    def _correr(self) -> None:
        try:
            dibujante = Dibujante(self._escala)
            ancho, alto = dibujante.ancho, dibujante.alto
            hwnd = self._crear_ventana(ancho, alto)
            pantalla = _user32.GetDC(None)
            memoria = _gdi32.CreateCompatibleDC(pantalla)
            cabecera = _BITMAPINFOHEADER(biSize=ctypes.sizeof(_BITMAPINFOHEADER), biWidth=ancho, biHeight=-alto,
                                         biPlanes=1, biBitCount=32)
            bits = ctypes.c_void_p()
            mapa = _gdi32.CreateDIBSection(memoria, ctypes.byref(cabecera), 0, ctypes.byref(bits), None, 0)
            _gdi32.SelectObject(memoria, mapa)
        except Exception:
            registro.exception("No pude crear el avatar")
            return
        mensaje = wintypes.MSG()
        visible, opacidad, inicio = False, 0.0, time.monotonic()
        while self._seguir:
            while _user32.PeekMessageW(ctypes.byref(mensaje), None, 0, 0, _PM_REMOVE):
                _user32.TranslateMessage(ctypes.byref(mensaje))
                _user32.DispatchMessageW(ctypes.byref(mensaje))
            ahora = time.monotonic()
            with self._candado:
                estado, texto, envolvente = self._estado, self._texto, self._envolvente
                transcurrido = ahora - self._inicio_habla
                if estado == "hablando" and transcurrido * 30 >= len(envolvente) + 6:
                    # Terminó la frase: pasa a lo que se pidió mientras hablaba.
                    self._estado = estado = self._despues_de_hablar
                    self._ocultar_en = ahora + self._OCULTAR_TRAS
                    if estado != "reposo":
                        self._texto = texto = ""
                quiere_verse = estado != "reposo" or ahora < self._ocultar_en
            boca = 0.0
            if estado == "hablando" and envolvente:
                boca = envolvente[min(int(transcurrido * 30), len(envolvente) - 1)]

            paso = 1 / 30
            if quiere_verse:
                opacidad = min(1.0, opacidad + paso / self._FADE_IN)
            else:
                opacidad = max(0.0, opacidad - paso / self._FADE_OUT)
            if opacidad > 0 and not visible:
                _user32.ShowWindow(hwnd, _SW_SHOWNOACTIVATE)
                _user32.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0, _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)
                visible = True
            elif opacidad == 0 and visible:
                _user32.ShowWindow(hwnd, _SW_HIDE)
                visible = False

            if visible:
                cuadro = np.asarray(dibujante.cuadro(ahora - inicio, estado, boca, texto))
                alfa = cuadro[..., 3:4].astype(np.uint16)
                bgra = np.empty_like(cuadro)
                bgra[..., :3] = (cuadro[..., 2::-1].astype(np.uint16) * alfa // 255).astype(np.uint8)
                bgra[..., 3] = cuadro[..., 3]
                ctypes.memmove(bits, bgra.tobytes(), bgra.nbytes)
                mezcla = _BLENDFUNCTION(0, 0, int(255 * opacidad), _AC_SRC_ALPHA)
                _user32.UpdateLayeredWindow(hwnd, pantalla, ctypes.byref(wintypes.POINT(self._x, self._y)),
                                            ctypes.byref(wintypes.SIZE(ancho, alto)), memoria,
                                            ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(mezcla), _ULW_ALPHA)
            time.sleep(max(0.0, paso - (time.monotonic() - ahora)))
        _user32.DestroyWindow(hwnd)
