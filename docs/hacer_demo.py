"""Genera docs/demo.gif: una animación del personaje con el mismo código de dibujo que usa la app.

No es una grabación de pantalla: es el `Dibujante` real (che_claudio/avatar.py) dibujando cada
cuadro sobre un escritorio de mentira, con una conversación de ejemplo. Se corre con:

    .venv\\Scripts\\python.exe docs\\hacer_demo.py
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from che_claudio.avatar import Dibujante  # noqa: E402

ANCHO, ALTO, FPS = 720, 380, 12
AVATAR_X, AVATAR_Y = 330, 70

FONDO_ARRIBA, FONDO_ABAJO = (24, 31, 48), (14, 18, 30)
TEXTO, APAGADO, CELESTE, SOL = (230, 236, 247), (122, 134, 160), (116, 172, 223), (246, 180, 14)


def fuente(tamano: int, negrita: bool = False):
    for nombre in (("seguisb.ttf" if negrita else "segoeui.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(nombre, tamano)
        except OSError:
            continue
    return ImageFont.load_default()


F_TITULO, F_NORMAL, F_CHICA, F_MONO = fuente(15, True), fuente(15), fuente(12), fuente(13)
try:
    F_MONO = ImageFont.truetype("consola.ttf", 13)
except OSError:
    pass


def fondo() -> Image.Image:
    imagen = Image.new("RGB", (ANCHO, ALTO))
    lienzo = ImageDraw.Draw(imagen)
    for y in range(ALTO):
        k = y / ALTO
        lienzo.line([(0, y), (ANCHO, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(FONDO_ARRIBA, FONDO_ABAJO)))
    return imagen


FONDO = fondo()


# Cada escena: lo que se dice, lo que hace el asistente y lo que contesta.
ESCENAS = [
    {
        "dicho": "Che Claudio, abrí Spotify y poné Don't Speak",
        "acciones": ["abrir_app('spotify')", "reproducir('Don't Speak')"],
        "respuesta": "Listo, ya está sonando Don't Speak.",
        "pensando": 1.1,
    },
    {
        "dicho": "Che Claudio, tengo ganas de hacer unas cuentas",
        "acciones": ["ofrecer('abrir calculadora')"],
        "respuesta": "¿Querés que te abra la calculadora?",
        "pensando": 1.0,
        "seguimiento": ("Sí, dale", ["abrir_app('calculadora')"], "Abierta."),
    },
]

CPS = 22  # caracteres por segundo al "hablar" y al "escribir"


def cuadro(dib: Dibujante, t: float, estado: str, boca: float, burbuja: str, dicho: str, hablante: str,
           acciones: list[str], titulo_fase: str) -> Image.Image:
    imagen = FONDO.copy().convert("RGBA")
    lienzo = ImageDraw.Draw(imagen)

    lienzo.text((28, 24), "Che Claudio", font=F_TITULO, fill=TEXTO)
    lienzo.text((28, 46), "asistente de voz para Windows · segundo plano", font=F_CHICA, fill=APAGADO)

    # Lo que "se escucha".
    lienzo.rounded_rectangle((28, 86, 312, 160), 10, fill=(32, 42, 66), outline=(52, 66, 100))
    lienzo.text((42, 96), hablante, font=F_CHICA, fill=CELESTE)
    y = 116
    palabras, linea = dicho.split(), ""
    for palabra in palabras:
        if F_NORMAL.getlength(linea + " " + palabra) > 260:
            lienzo.text((42, y), linea.strip(), font=F_NORMAL, fill=TEXTO)
            y, linea = y + 20, ""
        linea += " " + palabra
    if linea.strip():
        lienzo.text((42, y), linea.strip() + ("|" if int(t * 3) % 2 == 0 and estado == "escuchando" else ""),
                    font=F_NORMAL, fill=TEXTO)

    # Registro de acciones.
    lienzo.text((28, 184), "Acciones", font=F_CHICA, fill=APAGADO)
    for i, accion in enumerate(acciones[-4:]):
        lienzo.text((28, 206 + i * 22), "› " + accion, font=F_MONO, fill=(150, 220, 170))

    lienzo.text((28, ALTO - 30), titulo_fase, font=F_CHICA, fill=SOL if estado == "escuchando" else APAGADO)

    # Personaje abajo a la derecha, como en la app.
    if estado != "oculto":
        avatar = dib.cuadro(t, estado, boca, burbuja)
        imagen.alpha_composite(avatar, (AVATAR_X, AVATAR_Y))
    return imagen.convert("RGB")


def construir() -> list[Image.Image]:
    dib = Dibujante(1.0)
    cuadros: list[Image.Image] = []
    t = 0.0

    def emitir(segundos, estado, burbuja="", dicho="", hablante="Vos", acciones=(), fase="", habla=False):
        nonlocal t
        for i in range(max(1, int(segundos * FPS))):
            boca = 0.0
            if habla:
                boca = max(0.0, math.sin(t * 17) * 0.5 + 0.5) * (0.6 + 0.4 * math.sin(t * 5.3))
            cuadros.append(cuadro(dib, t, estado, boca, burbuja, dicho, hablante, list(acciones), fase))
            t += 1 / FPS

    def escribir(texto, **datos):
        for n in range(1, len(texto) + 1):
            emitir(1 / CPS, "escuchando", dicho=texto[:n], **datos)

    def decir(texto, **datos):
        for n in range(1, len(texto) + 1):
            emitir(1 / CPS, "hablando", burbuja=texto[:n], habla=True, **datos)
        emitir(1.3, "hablando", burbuja=texto, **datos)

    emitir(1.0, "oculto", fase="en reposo: si no aparece el personaje, no te está escuchando")
    for escena in ESCENAS:
        fase = 'te escucha: apareció apenas dijiste "Che Claudio"'
        escribir(escena["dicho"], fase=fase)
        emitir(0.6, "escuchando", dicho=escena["dicho"], fase=fase)
        emitir(escena["pensando"], "pensando", dicho=escena["dicho"], fase="entendiendo la orden…")
        acciones = list(escena["acciones"])
        decir(escena["respuesta"], dicho=escena["dicho"], acciones=acciones, fase="respondiendo con voz y subtítulos")
        if "seguimiento" in escena:
            dicho, mas, respuesta = escena["seguimiento"]
            emitir(0.5, "escuchando", dicho="", fase="esperando tu respuesta (7 s)")
            escribir(dicho, fase="esperando tu respuesta (7 s)")
            emitir(0.5, "pensando", dicho=dicho, fase="entendiendo la orden…")
            acciones += mas
            decir(respuesta, dicho=dicho, acciones=acciones, fase="respondiendo con voz y subtítulos")
        emitir(1.0, "oculto", acciones=acciones, fase="en reposo: vuelve a ocultarse solo")
    return cuadros


def main() -> None:
    cuadros = construir()
    destino = RAIZ / "docs" / "demo.gif"
    destino.parent.mkdir(exist_ok=True)
    paleta = [c.convert("P", palette=Image.ADAPTIVE, colors=128) for c in cuadros]
    paleta[0].save(destino, save_all=True, append_images=paleta[1:], duration=int(1000 / FPS), loop=0,
                   optimize=True, disposal=1)
    print(f"{len(cuadros)} cuadros -> {destino} ({destino.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
