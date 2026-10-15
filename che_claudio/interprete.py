"""Convierte lo que se dijo en una lista de acciones.

No ejecuta nada: solo entiende. Así se puede probar sin micrófono ni efectos.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from .texto import Palabra, normalizar, parecido, tokenizar, unir


@dataclass
class Accion:
    tipo: str
    objetivo: str = ""  # qué abrir / reproducir / buscar / cerrar; nombre del archivo; texto del mensaje
    plataforma: str | None = None  # spotify, youtube, google, ...
    segundo_plano: bool | None = None  # False = "y mostrámelo"; None = no se aclaró
    valor: int | None = None  # volumen
    carpeta: str | None = None  # archivo: dónde buscar
    formato: str | None = None  # archivo: pdf, word, excel, powerpoint
    programa: str | None = None  # archivo: con qué abrirlo
    destinatario: str | None = None  # mensaje: chat o grupo


# --- Llamado ("che claudio") -------------------------------------------------

def _es_nombre(norma: str, nombres) -> bool:
    for nombre in nombres:
        if norma == nombre:
            return True
        # "checlaudio" pegado
        if norma.endswith(nombre) and len(norma) <= len(nombre) + 4:
            return True
        # "claudia", "cloudio"... pero no "audio"
        if norma[:1] == nombre[:1] and parecido(norma, nombre) >= 0.84:
            return True
    return False


def separar_llamado(texto: str, nombres=("claudio",)) -> list[Palabra] | None:
    """Si la frase arranca llamando al asistente devuelve lo que sigue; si no, None."""
    palabras = tokenizar(texto)
    for i, palabra in enumerate(palabras[:3]):
        if _es_nombre(palabra.norma, nombres):
            # Antes del nombre solo puede venir algo corto: "che", "eh", "hey"...
            if all(len(p.norma) <= 4 for p in palabras[:i]):
                return palabras[i + 1:]
            return None
    return None


# --- Vocabulario -------------------------------------------------------------

_ABRIR = {
    "abri", "abre", "abrir", "abrime", "abreme", "abrirme", "abris", "abres", "abra", "abran",
    "inicia", "iniciar", "iniciame", "ejecuta", "ejecutar", "lanza", "lanzar", "arranca", "arrancar",
    "entra", "entrar", "anda", "ve", "ir", "mostrame", "muestrame", "mostra", "muestra", "mostrar",
}
_ABRIR_A_LA_VISTA = {"mostrame", "muestrame", "mostra", "muestra", "mostrar"}
# "...y abrilo en Brave": se refiere al archivo de la orden anterior.
_ABRIR_ESO = {"abrilo", "abrila", "abrilos", "abrirlo", "abrelo", "abrimelo", "abremelo"}
_MENSAJE = {
    "manda", "mandale", "mandar", "mandales", "envia", "enviale", "enviar", "enviales",
    "escribi", "escribile", "escribe", "escribele", "escribir", "decile", "dile", "avisale", "avisa",
}
_REPRODUCIR = {
    "pone", "pon", "poner", "poneme", "ponme", "ponele", "pones", "ponga", "ponedme",
    "reproduci", "reproduce", "reproducir", "reproducime", "reproduceme", "reproducidme",
    "toca", "tocar", "tocame", "escuchar", "play",
}
_BUSCAR = {"busca", "buscar", "buscame", "buscas", "busque", "busques", "googlea", "googlear", "googleame"}
_CERRAR = {"cerra", "cierra", "cerrar", "cerrame", "cierrame", "cerras", "cierras"}

_OTROS_VERBOS = {
    "pausa", "pausar", "pausala", "para", "parar", "frena", "subi", "sube", "subir", "subile",
    "baja", "bajar", "bajale", "silencia", "silenciar", "mutea", "segui", "sigue", "continua",
    "reanuda", "bloquea", "pasa", "saltea", "salta", "cambia", "decime", "dime", "volve", "vuelve",
    "apaga", "apagar", "apagame", "reinicia", "reiniciar", "suspende", "suspender",
    "levanta", "levantame", "levantar",
}
# Proyectos de programación definidos en config.json: "levantá cancha libre", "bajá el proyecto X".
_LEVANTAR = {"levanta", "levantame", "levantar", "levantas", "levantes"}
_LEVANTAR_PROYECTO = _LEVANTAR | {"arranca", "arrancar", "arrancame", "inicia", "iniciar", "iniciame", "ejecuta",
                                  "ejecutar", "corre", "correr", "correme", "abri", "abrir", "abrime"}
_BAJAR_PROYECTO = {"baja", "bajar", "bajame", "detene", "detener", "deten", "para", "parar", "frena", "frenar",
                   "cerra", "cierra", "cerrar", "cerrame", "apaga", "apagar", "apagame", "corta", "cortar", "tira"}
# Notas: "escribí ..." sin destinatario es dictado; "escribí a Martín ..." es un WhatsApp.
_NOTA = {"anota", "anotame", "anotar", "apunta", "apuntame", "apuntar", "escribi", "escribime", "escribe",
         "escribir", "agrega", "agregale", "agregar", "suma", "sumale"}
_SUMAR = {"agrega", "agregale", "agregar", "suma", "sumale"}
_DESTINO_NOTA = {"bloc", "blog", "block", "bloque", "plug", "blok", "nota", "notas", "notepad",
                 "lista"}  # "blog", "plug": así lo oye
_RECORDAR = {"avisame", "avisarme", "avisar", "avisadme", "avisenme", "aviseme", "recordame", "recorda", "recordar",
             "recordarme", "recordadme", "recuerdame", "recuerdeme", "acordame", "despertame"}
_CANCELAR = {"cancela", "cancelame", "borra", "borrame", "elimina", "saca", "sacame"}
_VERBOS = (_ABRIR | _REPRODUCIR | _BUSCAR | _CERRAR | _OTROS_VERBOS | _ABRIR_ESO | _MENSAJE | _NOTA | _RECORDAR
           | _CANCELAR)
# Tras una coma no alcanzan para cortar la frase: también son palabras comunes.
_AMBIGUOS = {
    "para", "ve", "toca", "play", "pasa", "anda", "entra", "baja", "sube", "salta", "cambia", "ir",
    "manda", "envia", "escribe", "escribi", "avisa", "mostra", "muestra", "mostrar", "suma", "saca", "borra",
    "agrega",
}
_CONECTORES = {"y", "e", "despues", "luego", "tambien", "ademas"}

# "y mostrámelo" al final de la frase: lo pedido se abre a la vista.
_MOSTRAR_FINAL = {
    "mostramelo", "mostramela", "mostramelos", "mostrame", "mostralo", "mostrala", "muestramelo",
    "muestramela", "muestralo", "muestrame", "mostrarmelo", "mostrarlo", "mostra", "muestra", "mostrar",
}
_MOSTRAR_FRASES = (("en", "primer", "plano"), ("al", "frente"), ("a", "la", "vista"), ("en", "pantalla"))
_ANTES_DE_MOSTRAR = {"traelo", "traela", "ponelo", "ponela", "dejalo", "dejala", "quiero", "verlo"}

# Archivos
_MARCAS_ARCHIVO = {"archivo", "archivos", "documento", "documentos", "pdf", "carpeta"}
_FORMATOS = {"pdf": "pdf", "word": "word", "excel": "excel", "planilla": "excel", "powerpoint": "powerpoint",
             "presentacion": "powerpoint"}
_CARPETAS_CONOCIDAS = {"descargas", "escritorio", "documentos", "imagenes", "fotos", "musica", "videos"}
_PROGRAMAS = {
    "brave", "chrome", "google chrome", "edge", "microsoft edge", "firefox", "word", "excel", "powerpoint",
    "acrobat", "adobe", "visual studio code", "vs code", "code", "bloc de notas", "notepad", "paint",
}
_RELLENO_ARCHIVO = {"archivo", "archivos", "documento", "documentos", "llamado", "llamada"}
_BORDES_ARCHIVO = {"el", "la", "los", "las", "un", "una", "de", "del", "mi", "mis", "ese", "esa", "este", "esta",
                   "lo", "en", "que", "se", "llama", "nombre", "con"}

# Mensajes
_WHATSAPP = {"whatsapp", "wasap", "guasap"}
_SOBRE_MENSAJE = {"mensaje", "mensajito", "texto"} | _WHATSAPP
_HACIA = {"a", "al", "para"}
_ANTES_DEL_NOMBRE = {"mi", "mis", "el", "la", "al", "grupo", "chat", "contacto", "llamado", "llamada", "que", "se",
                     "llama", "de", "del"}
_ANTES_DEL_TEXTO = {"diciendo", "diciendole", "diciendoles", "que"}

_SI = {"si", "sisi", "sip", "dale", "ok", "okey", "okay", "obvio", "claro", "confirmo", "confirmado",
       "afirmativo", "mandalo", "mandaselo", "mandale", "envialo", "hacelo", "listo", "correcto", "exacto"}
_NO = {"no", "nop", "cancela", "cancelar", "cancelalo", "espera", "negativo", "dejalo", "nada"}

_MULETILLAS = {
    "por", "favor", "porfa", "porfi", "porfis", "quiero", "quisiera", "podes", "podrias", "podria",
    "puedes", "puede", "podeis", "necesito", "bueno", "dale", "eh", "ahora", "che", "oye", "me",
}
_COLA = {"favor", "porfa", "porfi", "porfis", "gracias"}

_ARTICULOS = {
    "el", "la", "los", "las", "un", "una", "mi", "mis", "a", "al", "en", "lo", "le",
    "app", "aplicacion", "programa", "pagina", "sitio", "web", "de", "del",
    "navegador", "juego", "ventana",
}
# "abrí el bloc de notas para anotar algo", "abrí Steam mientras hago otra cosa": lo que sigue no es el nombre.
_FIN_DEL_NOMBRE = {"para", "mientras", "porque", "asi", "cuando", "que"}
_DETERMINANTES = {"la", "el", "una", "un", "unas", "unos", "los", "las"}
_DESCRIPTORES = {"cancion", "canciones", "tema", "temas", "musica", "algo", "video", "videos", "videoclip"}
_ORDINALES = {"primer", "primero", "primera", "ultimo", "ultima", "nuevo", "nueva", "mejor"}
_VIDEO = {"video", "videos", "videoclip"}

_SEGUNDO_PLANO = (
    ("en", "segundo", "plano"), ("en", "2", "plano"), ("en", "2o", "plano"), ("en", "2º", "plano"),
    ("de", "fondo"), ("en", "background"), ("minimizado",), ("minimizada",),
)

_PLATAFORMAS = {
    "spotify": ("spotify", "spotifai", "espotifai", "spotifi", "espotify", "spoti"),
    "youtube": ("youtube", "you tube", "yutub", "yutube", "youtub", "iutub"),
    "google": ("google", "gugel", "internet", "la web"),
    "wikipedia": ("wikipedia",),
    "maps": ("maps", "google maps", "mapas", "el mapa"),
    "mercadolibre": ("mercado libre", "mercadolibre"),
}

_NUMEROS = {
    "cero": 0, "diez": 10, "veinte": 20, "treinta": 30, "cuarenta": 40, "cincuenta": 50,
    "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100,
    "minimo": 0, "mitad": 50, "maximo": 100,
}

_PISTA = r"(?:cancion|tema|pista)"
_SONANDO = r"(?:musica|cancion|tema|video|reproduccion|pista)"
_PONER = r"(?:pone|pon|poner|poneme|ponele|ponenle|ponle|ponelo|ponela|ponga)"
_EQUIPO = r"(?:pc|compu|computadora|computador|equipo|maquina|notebook)"
_ANTES_DE_PREGUNTA = r"(?:(?:y|a ver|decime|dime|sabes|me decis|podes decirme)\s+)*"
# Lo que suena: admiten "... de Spotify" / "... en YouTube" al final (ver _accion_de_musica).
_PATRONES_DE_MUSICA = (
    ("siguiente", re.compile(
        rf"^(?:(?:pone|pon|poneme|pasa|pasar|saltea|saltear|salta|saltar|cambia|cambiar|anda)\s+)?"
        rf"(?:a\s+|de\s+)?(?:la\s+|el\s+|al\s+)?"
        rf"(?:(?:siguiente|proxima|proximo|otra|otro)(?:\s+{_PISTA})?|{_PISTA}\s+siguiente)$"
        rf"|^(?:pasa|pasame|saltea|salteame|salta)\s+(?:de\s+|la\s+|el\s+|esta\s+|este\s+)?{_PISTA}$"
        # "cambiá la música", "cambiame de tema"
        rf"|^(?:cambia|cambiame|cambiar|cambio)(?:\s+(?:de|la|el|esta|este|esa|ese))?\s+(?:musica|{_PISTA})$"
        rf"|^(?:cambiala|cambialo)$")),
    ("anterior", re.compile(
        rf"^(?:(?:pone|pon|poneme|volve|vuelve|volver|anda)\s+)?(?:a\s+)?(?:la\s+|el\s+|al\s+)?"
        rf"(?:(?:anterior|previa|previo)(?:\s+{_PISTA})?|{_PISTA}\s+anterior)$")),
    ("pausar", re.compile(
        rf"^(?:pausa|pausar|pausala|pausalo|pausame|{_PONER}\s+(?:en\s+)?pausa|para|parar|parala|parame"
        rf"|frena|frenar|frenala|deten|detene|detener|corta|cortar|cortala)"
        rf"(?:\s+(?:a|al))?(?:\s+(?:la|el|esa|ese|esta|este))?(?:\s+{_SONANDO})?$")),
    ("continuar", re.compile(
        rf"^(?:segui|sigue|seguir|continua|continuar|reanuda|reanudar|despausa|despausar|play|dale\s+play"
        rf"|pone\s+play|reproduci|reproduce|reproducir)(?:\s+con)?(?:\s+(?:la|el|algo\s+de))?(?:\s+{_SONANDO})?$"
        # "poné" a secas es una frase cortada: para reanudar hay que nombrar qué.
        rf"|^(?:pone|pon|poner|poneme)(?:\s+con)?(?:\s+(?:la|el|algo\s+de))?\s+{_SONANDO}$")),
)
_PLATAFORMA_AL_FINAL = re.compile(r"\s+(?:(?:de|del|en|a|al)\s+)?(?:la\s+|el\s+|lo\s+de\s+)?([a-z]+(?:\s[a-z]+)?)$")
_PATRONES_FIJOS = (
    ("ver_recordatorios", re.compile(r"\b(?:que|cuales)\s+(?:recordatorios|avisos|alarmas)\b"
                                     r"|\bmis\s+(?:recordatorios|avisos|alarmas)\b")),
    # Solo la pregunta pelada: "¿a qué hora termina el bloque?" es otra cosa y la piensa el cerebro.
    ("hora", re.compile(rf"^{_ANTES_DE_PREGUNTA}(?:que\s+horas?\s+(?:es|son|tenes)|la\s+hora)(?:\s+(?:ahora|ya))?$")),
    ("fecha", re.compile(rf"^{_ANTES_DE_PREGUNTA}(?:que\s+(?:dia|fecha)\s+es|(?:la\s+)?fecha\s+de\s+hoy)(?:\s+hoy)?$")),
    ("bloquear", re.compile(
        r"^(?:bloquea|bloquear|bloqueame)\b.*\b(?:pc|compu|computadora|pantalla|equipo|sesion|maquina)\b")),
    # Antes que "apagar": "cancelá el apagado de la compu".
    ("cancelar_apagado", re.compile(
        r"^(?:cancela|cancelar|cancelame|frena|frenar|para|parar|deten|detene|detener)\b.*\b(?:apagado|reinicio)\b"
        r"|^no\s+(?:la\s+|lo\s+)?(?:apagues|reinicies)\b")),
    ("apagar", re.compile(rf"^(?:apaga|apagar|apagame|apagas)\b.*\b{_EQUIPO}\b")),
    ("reiniciar", re.compile(rf"^(?:reinicia|reiniciar|reiniciame|reinicias)\b.*\b{_EQUIPO}\b")),
    ("suspender", re.compile(rf"^(?:suspende|suspender|suspendeme|hiberna|hibernar)\b.*\b{_EQUIPO}\b")),
    ("salir", re.compile(
        r"^(?:chau|adios|apagate|cerrate|salir|sali|dormite|descansa|desactivate|hasta luego|nos vemos)\b")),
    ("saludo", re.compile(
        r"^(?:hola|buenas|buen dia|buenos dias|como estas|como andas|estas ahi|me escuchas)\b")),
    ("gracias", re.compile(r"^(?:muchas\s+)?gracias\b")),
)

_VOLUMEN_ABSOLUTO = re.compile(
    r"\bvolumen\b.*?\b(?:al?|en)\s+(?:el\s+|la\s+)?(\d{1,3}|" + "|".join(_NUMEROS) + r")\b")
_NIVEL = re.compile(r"\b(?:al?|en)\s+(?:el\s+|la\s+)?(\d{1,3}|" + "|".join(_NUMEROS) + r")\b")
_A_SU_VOZ = re.compile(r"\btu (?:voz|volumen)\b|\b(?:bajate|subite|bajarte|subirte)\b|^(?:habla|hablame|hablar|hables)\b")
_VOLUMEN_SUBIR = re.compile(
    r"^(?:subi|sube|subir|subile|subele|aumenta|aumentar|levanta|levantar)\b.*\bvolumen\b"
    r"|\bmas (?:fuerte|alto|volumen)\b|^(?:subi|sube|subile|subele)(?:\s+un (?:poco|poquito)|\s+mas|\s+mucho)?$")
_VOLUMEN_BAJAR = re.compile(
    r"^(?:baja|bajar|bajale|bajame|reduci|reduce|reducir|disminui|disminuye)\b.*\bvolumen\b"
    r"|\bmas (?:bajo|despacio|bajito)\b|\bmenos volumen\b|^(?:baja|bajale)(?:\s+un (?:poco|poquito)|\s+mas|\s+mucho)?$")
_DE_SPOTIFY = re.compile(r"\s+(?:de|del|en|a|al)\s+(?:el\s+|la\s+)?(?:spotify|spotifai|espotifai|spoti)\b")
_SILENCIAR = re.compile(
    r"^(?:silencia|silenciar|silencio|mutea|mutear|mute|desmutea|desmutear|desilencia)\b"
    r"|\b(?:saca|quita|sacale|quitale|activa|volve|devolve) el (?:sonido|audio|silencio|mute)\b")


# --- Piezas ------------------------------------------------------------------

def plataforma_de(norma: str) -> str | None:
    """Reconoce una plataforma por nombre, tolerando cómo la escribe el reconocedor."""
    for plataforma, alias in _PLATAFORMAS.items():
        if norma in alias:
            return plataforma
    if " " not in norma:
        for plataforma in ("spotify", "youtube"):
            if parecido(norma, plataforma) >= 0.8:
                return plataforma
    return None


def _sacar_segundo_plano(palabras: list[Palabra]):
    normas = [p.norma for p in palabras]
    for frase in _SEGUNDO_PLANO:
        n = len(frase)
        for i in range(len(normas) - n + 1):
            if tuple(normas[i:i + n]) == frase:
                return palabras[:i] + palabras[i + n:], True
    return palabras, None


def _sacar_plataforma(palabras: list[Palabra]):
    """Saca "en spotify" / "en youtube" del final o del principio."""
    normas = [p.norma for p in palabras]
    for n in (3, 2, 1):
        if len(palabras) > n and normas[-n - 1] in ("en", "por", "desde", "con"):
            plataforma = plataforma_de(" ".join(normas[-n:]))
            if plataforma:
                return palabras[:-n - 1], plataforma
    # "una canción en el Spotify"
    if len(palabras) > 2 and normas[-2] in ("el", "la") and normas[-3] in ("en", "por", "desde", "con", "de")             and plataforma_de(normas[-1]) in ("spotify", "youtube"):
        return palabras[:-3], plataforma_de(normas[-1])
    if normas and normas[0] in ("en", "por", "desde"):
        for n in (3, 2, 1):
            if len(palabras) > n:
                plataforma = plataforma_de(" ".join(normas[1:1 + n]))
                if plataforma:
                    return palabras[1 + n:], plataforma
    # "don't speak en Spotify, por favor, dale": lo que viene después de la plataforma ya no es el pedido.
    for i in range(1, len(palabras) - 1):
        if normas[i] in ("en", "por", "desde", "con") and plataforma_de(normas[i + 1]) in ("spotify", "youtube"):
            return palabras[:i], plataforma_de(normas[i + 1])
    return palabras, None


# Pedidos de música sin decir cuál: "una buena música", "lo que vos quieras", "algo que le guste a Sofía".
_MUSICA_A_GUSTO = re.compile(
    r"\b(?:lo|la|el) que (?:vos |tu |a vos |se te )?(?:quieras|quieres|queres|ocurra|prefieras|creas|elijas|gustes)\b"
    r"|\bque (?:me|le|nos|les) (?:guste|gusta|gustaria|gustara|vaya a gustar)\b"
    r"|\b(?:a (?:tu|mi) gusto|vos elegi|elegi vos|cualquier cosa|cualquiera|sorprendeme|algo para|musica para)\b"
    r"|^(?:(?:una|un|alguna|algun|algo de|otra|otro)\s+)?(?:(?:buena|buen|linda|lindo|otra)\s+)?"
    r"(?:musica|cancion|tema|temas|canciones|algo|temita|musiquita)"
    r"(?:\s+(?:buena|bueno|linda|lindo|copada|copado|piola|tranqui|tranquila|tranquilo|de fondo|que este buena))*$")


def _hasta_la_cortesia(palabras: list[Palabra]) -> list[Palabra]:
    """"don't speak por favor, dale" -> "don't speak"."""
    for i, palabra in enumerate(palabras):
        if i and palabra.norma in ("porfa", "porfi", "porfis", "gracias"):
            return palabras[:i]
        if i and palabra.norma == "por" and i + 1 < len(palabras) and palabras[i + 1].norma == "favor":
            return palabras[:i]
    return palabras


def _sin_prefijos(palabras: list[Palabra], prefijos) -> list[Palabra]:
    i = 0
    while i < len(palabras) - 1 and palabras[i].norma in prefijos:
        i += 1
    return palabras[i:]


def _sin_muletillas(palabras: list[Palabra]) -> list[Palabra]:
    while palabras and palabras[0].norma in _MULETILLAS:
        palabras = palabras[1:]
    while palabras and palabras[-1].norma in _COLA:
        palabras = palabras[:-1]
        if palabras and palabras[-1].norma == "por":
            palabras = palabras[:-1]
    return palabras


def _sin_descriptores(palabras: list[Palabra]):
    """"la canción don't speak" -> "don't speak". Avisa si se pidió un video."""
    normas = [p.norma for p in palabras]
    # "el primer video de...", "la última canción de...": el descriptor puede venir tras un artículo y un ordinal.
    i = 1 if normas[:1] and normas[0] in _DETERMINANTES else 0
    if i < len(normas) and normas[i] in _ORDINALES:
        i += 1
    if not (i < len(normas) and normas[i] in _DESCRIPTORES):
        i = 0
    if i < len(normas) and normas[i] in _DESCRIPTORES:
        es_video = normas[i] in _VIDEO
        i += 1
        if i < len(normas) and normas[i] in ("de", "del", "llamada", "llamado"):
            i += 1
        return palabras[i:], es_video
    return palabras, False


def _dividir_objetivos(palabras: list[Palabra]) -> list[list[Palabra]]:
    """"youtube y spotify" -> [youtube], [spotify]."""
    grupos, actual = [], []
    for palabra in palabras:
        if palabra.norma in ("y", "e") and actual:
            grupos.append(actual)
            actual = []
            continue
        actual.append(palabra)
        if palabra.corte:
            grupos.append(actual)
            actual = []
    if actual:
        grupos.append(actual)
    return grupos


def _clausulas(palabras: list[Palabra]) -> list[list[Palabra]]:
    """Corta "abrí X y poné Z" en una cláusula por verbo."""
    grupos, actual = [], []
    for i, palabra in enumerate(palabras):
        siguiente = palabras[i + 1].norma if i + 1 < len(palabras) else ""
        pregunta = palabra.norma == "que" and siguiente in ("hora", "dia", "fecha")
        if actual and (palabra.norma in _VERBOS or pregunta):
            tras_conector = actual[-1].norma in _CONECTORES
            tras_coma = actual[-1].corte and palabra.norma not in _AMBIGUOS
            if tras_conector or tras_coma:
                while actual and actual[-1].norma in _CONECTORES:
                    actual.pop()
                if actual:
                    grupos.append(actual)
                actual = []
        actual.append(palabra)
    if actual:
        grupos.append(actual)
    return grupos


def _volumen_de_su_voz(frase: str, paso: int) -> Accion | None:
    """"hablá más bajo", "bajate el volumen a 30", "subí tu voz": la voz de Claudio, no la PC."""
    if not _A_SU_VOZ.search(frase):
        return None
    m = _NIVEL.search(frase)
    if m:
        return Accion("volumen_voz", valor=_NUMEROS[m.group(1)] if m.group(1) in _NUMEROS else int(m.group(1)))
    if re.search(r"\b(?:baja|bajar|bajale|bajate|bajarte|bajo|bajito|despacio|menos)\b", frase):
        return Accion("volumen_voz_relativo", valor=-paso)
    if re.search(r"\b(?:subi|sube|subir|subile|subite|subirte|alto|fuerte)\b", frase):
        return Accion("volumen_voz_relativo", valor=paso)
    return None


def _accion_de_musica(frase: str) -> Accion | None:
    """"pasá de tema", "ponele pausa al video de YouTube", "cambiame la música de Spotify"."""
    plataforma = None
    m = _PLATAFORMA_AL_FINAL.search(frase)
    if m and plataforma_de(m.group(1)) in ("spotify", "youtube"):
        frase, plataforma = frase[:m.start()], plataforma_de(m.group(1))
    for tipo, patron in _PATRONES_DE_MUSICA:
        if patron.search(frase):
            return Accion(tipo, plataforma=plataforma)
    return None


def _accion_fija(frase: str) -> Accion | None:
    paso = 6 if re.search(r"\bun (?:poco|poquito)\b", frase) else 20 if re.search(r"\b(?:mucho|bastante)\b", frase) else 10
    su_voz = _volumen_de_su_voz(frase, paso)
    if su_voz:
        return su_voz
    de_musica = _accion_de_musica(frase)
    if de_musica:
        return de_musica
    # "subile un poco a Spotify", "el volumen de Spotify al 30": solo Spotify, no toda la PC.
    donde = None
    de_spotify = _DE_SPOTIFY.search(frase)
    if de_spotify:
        frase, donde = (frase[:de_spotify.start()] + frase[de_spotify.end():]).strip(), "spotify"
    m = _VOLUMEN_ABSOLUTO.search(frase)
    if m:
        valor = _NUMEROS[m.group(1)] if m.group(1) in _NUMEROS else int(m.group(1))
        return Accion("volumen", plataforma=donde, valor=max(0, min(100, valor)))
    if _VOLUMEN_SUBIR.search(frase):
        return Accion("volumen_relativo", plataforma=donde, valor=paso)
    if _VOLUMEN_BAJAR.search(frase):
        return Accion("volumen_relativo", plataforma=donde, valor=-paso)
    if donde:
        return None  # nombró a Spotify pero no era por el volumen
    if _SILENCIAR.search(frase):
        return Accion("silenciar")
    for tipo, patron in _PATRONES_FIJOS:
        if patron.search(frase):
            return Accion(tipo)
    return None


def _sacar_mostrar(palabras: list[Palabra]):
    """Saca un "y mostrámelo" del final, o un "en pantalla" / "al frente" de cualquier parte."""
    resto = list(palabras)
    pidio = False
    for frase in _MOSTRAR_FRASES:
        n = len(frase)
        for i in range(len(resto) - n + 1):
            if len(resto) > n and tuple(p.norma for p in resto[i:i + n]) == frase:
                del resto[i:i + n]
                pidio = True
                break
    while resto and resto[-1].norma in _COLA | {"por"}:
        resto.pop()
    if len(resto) > 1 and resto[-1].norma in _MOSTRAR_FINAL:
        resto.pop()
        pidio = True
    if not pidio:
        return palabras, False
    while resto and resto[-1].norma in _ANTES_DE_MOSTRAR | _CONECTORES:
        resto.pop()
    return resto, True


def _sacar_programa(palabras: list[Palabra]):
    """Saca "en Brave" / "con Word" del final."""
    normas = [p.norma for p in palabras]
    for n in (3, 2, 1):
        if len(palabras) > n and normas[-n - 1] in ("en", "con"):
            programa = " ".join(normas[-n:])
            if programa in _PROGRAMAS:
                return palabras[:-n - 1], programa
    return palabras, None


def _es_de_archivos(normas: list[str]) -> bool:
    if _MARCAS_ARCHIVO & set(normas):
        return True
    # "el word del informe" es un archivo; "word" a secas es el programa.
    return any(n in _FORMATOS and siguiente in ("de", "del", "llamado", "llamada", "que")
               for n, siguiente in zip(normas, normas[1:]))


def _sacar_carpeta(palabras: list[Palabra]):
    """Saca "en la carpeta X" o "en descargas" y devuelve el nombre de la carpeta."""
    normas = [p.norma for p in palabras]
    if "carpeta" in normas:
        marca = normas.index("carpeta")
        inicio = marca
        while inicio > 0 and normas[inicio - 1] in ("en", "la", "mi", "de", "del", "dentro", "una", "esa", "el"):
            inicio -= 1
        nombre = marca + 1
        while nombre < len(normas) and normas[nombre] in ("de", "del", "llamada", "que", "se", "llama"):
            nombre += 1
        # El nombre llega hasta donde se empieza a hablar del archivo.
        fin = next((i for i in range(nombre, len(normas)) if normas[i] in _MARCAS_ARCHIVO | set(_FORMATOS)),
                   len(normas))
        while fin < len(normas) and fin > nombre and normas[fin - 1] in _DETERMINANTES:
            fin -= 1
        return palabras[:inicio] + palabras[fin:], unir(palabras[nombre:fin])
    for i, norma in enumerate(normas):
        if norma in _CARPETAS_CONOCIDAS and i > 0:
            inicio = i
            while inicio > 0 and normas[inicio - 1] in ("en", "de", "el", "la", "mi", "mis", "los", "las"):
                inicio -= 1
            if inicio < i and normas[inicio] in ("en", "de"):
                return palabras[:inicio] + palabras[i + 1:], palabras[i].original
    return palabras, None


def _interpretar_archivo(palabras: list[Palabra], segundo_plano) -> Accion:
    """"en la carpeta seminario el archivo resumen parcial pdf en brave" -> qué buscar y dónde."""
    palabras, programa = _sacar_programa(palabras)
    palabras, carpeta = _sacar_carpeta(palabras)
    formato = next((_FORMATOS[p.norma] for p in palabras if p.norma in _FORMATOS), None)
    palabras = [p for p in palabras if p.norma not in _FORMATOS and p.norma not in _RELLENO_ARCHIVO]
    while palabras and palabras[0].norma in _BORDES_ARCHIVO:
        palabras = palabras[1:]
    while palabras and palabras[-1].norma in _BORDES_ARCHIVO:
        palabras = palabras[:-1]
    return Accion("archivo", unir(palabras), segundo_plano=segundo_plano, carpeta=carpeta, formato=formato,
                  programa=programa)


def _sin_mencion_de_whatsapp(palabras: list[Palabra]) -> list[Palabra]:
    """Saca "por whatsapp" / "en whatsapp": es el medio, no parte del mensaje."""
    limpias = []
    for palabra in palabras:
        if palabra.norma in _WHATSAPP and limpias and limpias[-1].norma in ("por", "en", "de"):
            limpias.pop()
            continue
        limpias.append(palabra)
    return limpias


def _interpretar_mensaje(palabras: list[Palabra]) -> Accion | None:
    """"un hola a mi grupo llamado tortugas" / "a Martín que diga llego tarde" -> texto y destinatario."""
    palabras = _sin_mencion_de_whatsapp(palabras)
    if palabras and palabras[0].norma in ("un", "una", "el", "este", "otro"):
        palabras = palabras[1:]
    if palabras and palabras[0].norma in _SOBRE_MENSAJE:
        palabras = palabras[1:]
    normas = [p.norma for p in palabras]
    if not palabras:
        return None

    if normas[0] in _HACIA:  # "a Martín que diga hola"
        resto = palabras[1:]
        corte = next((i for i, p in enumerate(resto) if i > 0 and p.norma in _ANTES_DEL_TEXTO), None)
        if corte is not None:
            nombre, texto = resto[:corte], resto[corte + 1:]
            if texto and texto[0].norma in ("diga", "dice", "digan"):
                texto = texto[1:]
        else:
            # Sin separador: el nombre es una palabra más las que sigan en mayúscula ("Martín Gómez").
            fin = 0
            while fin < len(resto) - 2 and resto[fin].norma in _ANTES_DEL_NOMBRE:
                fin += 1
            fin += 1
            while fin < len(resto) - 1 and not resto[fin - 1].corte and resto[fin].original[:1].isupper():
                fin += 1
            nombre, texto = resto[:fin], resto[fin:]
    else:  # "un hola a mi grupo llamado tortugas"
        ultimo = max((i for i, n in enumerate(normas) if n in _HACIA and 0 < i < len(normas) - 1), default=None)
        if ultimo is None:
            return None
        texto, nombre = palabras[:ultimo], palabras[ultimo + 1:]

    while len(nombre) > 1 and nombre[0].norma in _ANTES_DEL_NOMBRE:
        nombre = nombre[1:]
    if not nombre or not texto:
        return None
    # El mensaje va con su puntuación, salvo el punto final que agrega el reconocedor.
    contenido = " ".join(p.bruto or p.original for p in texto).rstrip(" .,;:")
    return Accion("mensaje", contenido[:1].upper() + contenido[1:], destinatario=unir(nombre))


def _texto_dicho(palabras: list[Palabra]) -> str:
    """Lo dictado tal cual, con su puntuación y mayúscula inicial, sin el punto final del reconocedor."""
    contenido = " ".join(p.bruto or p.original for p in palabras).strip().rstrip(" .,;:")
    return contenido[:1].upper() + contenido[1:]


def _sacar_destino_nota(palabras: list[Palabra]):
    """Saca "en el bloc de notas", "en una nota nueva", "a la lista". Devuelve (resto, pidió una nueva)."""
    normas = [p.norma for p in palabras]
    for inicio, norma in enumerate(normas):
        if norma not in ("en", "a", "al"):
            continue
        fin, nueva = inicio + 1, False
        while fin < len(normas) and normas[fin] in _DETERMINANTES | {"mi", "otro", "otra", "nuevo", "nueva"}:
            nueva = nueva or normas[fin] in ("otro", "otra", "nuevo", "nueva")
            fin += 1
        if fin < len(normas) and normas[fin] in _DESTINO_NOTA:
            fin += 1
            while fin < len(normas) and normas[fin] in ("de", "notas", "nuevo", "nueva", "texto"):
                nueva = nueva or normas[fin] in ("nuevo", "nueva")
                fin += 1
            return palabras[:inicio] + palabras[fin:], nueva
    return palabras, False


def _interpretar_nota(palabras: list[Palabra]) -> Accion | None:
    """"escribí que mañana compro pan", "anotá en una nota nueva: ...", "agregá a la lista leche"."""
    verbo, resto = palabras[0].norma, palabras[1:]
    normas = {p.norma for p in resto}
    if verbo in _SUMAR and not normas & _DESTINO_NOTA:
        return None  # "agregá" a secas puede ser cualquier cosa: que lo piense el cerebro
    resto, nueva = _sacar_destino_nota(resto)
    sumar = verbo in _SUMAR
    # Si después de esto no queda nada ("anotá lo siguiente..."), el dictado viene en la frase que sigue.
    while resto and resto[0].norma in ("tambien", "ademas", "que", "lo", "siguiente", "esto", "de", "eh", "em"):
        sumar = sumar or resto[0].norma in ("tambien", "ademas")
        resto = resto[1:]
    if not resto:
        return None
    # valor: 1 = nota nueva, 0 = sumar a la última, None = que decida (la última si es reciente).
    return Accion("nota", _texto_dicho(resto), valor=1 if nueva else 0 if sumar else None)


_NUMEROS_HORA = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
    "nueve": 9, "diez": 10, "once": 11, "doce": 12, "quince": 15, "veinte": 20, "veinticinco": 25,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "cuarto": 15, "media": 30,
}
_NUM = r"\d{1,3}|" + "|".join(_NUMEROS_HORA)
_EN_CUANTO = re.compile(
    rf"\ben\s+(?P<cantidad>{_NUM})\s*(?P<unidad>minutos?|min|horas?|hs|segundos?)"
    rf"(?:\s+y\s+(?P<extra>{_NUM})(?:\s+minutos?)?)?\b|\ben\s+(?P<media>media)\s+hora\b")
_A_LAS = re.compile(
    rf"\b(?P<dia>(?:pasado\s+)?manana|hoy)?\s*(?:a\s+)?las?\s+(?P<hora>\d{{1,2}}|una|uno|dos|tres|cuatro|cinco|seis|"
    rf"siete|ocho|nueve|diez|once|doce)(?:\s*[:.]\s*(?P<minutos>\d{{2}}))?(?:\s*(?:hs|horas))?"
    rf"(?:\s+y\s+(?P<y>{_NUM}))?(?:\s+menos\s+(?P<menos>{_NUM}))?"
    rf"(?:\s+(?:de\s+la\s+)?(?P<franja>manana|tarde|noche)|\s*(?P<ampm>am|pm))?\b")


def _valor(texto: str) -> int:
    return int(texto) if texto.isdigit() else _NUMEROS_HORA[texto]


def hora_hablada(momento: datetime, con_franja: bool = False) -> str:
    """Como se dice en voz alta: "son las 9 y 55", "es la 1 y media", "son las 4 en punto de la tarde"."""
    hora = momento.hour % 12 or 12
    minutos = {0: "en punto", 15: "y cuarto", 30: "y media"}.get(momento.minute, f"y {momento.minute}")
    franja = ""
    if con_franja:
        franja = (" de la noche" if momento.hour == 0 else " de la madrugada" if momento.hour < 6
                  else " de la mañana" if momento.hour < 12
                  else " del mediodía" if momento.hour == 12 else " de la tarde" if momento.hour < 20
                  else " de la noche")
    return f"{'es la' if hora == 1 else 'son las'} {hora} {minutos}{franja}"


def cuando(frase: str, ahora: datetime):
    """Busca un momento en la frase normalizada. Devuelve (momento, inicio, fin) o None."""
    m = _EN_CUANTO.search(frase)
    if m:
        if m.group("media"):
            return ahora + timedelta(minutes=30), m.start(), m.end()
        cantidad = 0.5 if m.group("cantidad") == "media" else _valor(m.group("cantidad"))
        unidad = m.group("unidad")
        segundos = cantidad * (3600 if unidad.startswith("h") else 1 if unidad.startswith("s") else 60)
        if m.group("extra"):
            segundos += 1800 if m.group("extra") == "media" else _valor(m.group("extra")) * 60
        return ahora + timedelta(seconds=segundos), m.start(), m.end()
    m = _A_LAS.search(frase)
    if not m:
        return None
    hora = _valor(m.group("hora"))
    minutos = int(m.group("minutos")) if m.group("minutos") else 0
    if m.group("y"):
        minutos += _valor(m.group("y"))
    if m.group("menos"):
        hora, minutos = hora - 1, 60 - _valor(m.group("menos"))
    franja = m.group("franja") or {"am": "manana", "pm": "tarde"}.get(m.group("ampm") or "")
    if franja in ("tarde", "noche") and hora < 12 and not (franja == "noche" and hora <= 4):
        hora += 12
    elif franja == "manana" and hora == 12:
        hora = 0
    if not (0 <= hora <= 23 and 0 <= minutos <= 59):
        return None
    dia = ahora.date() + timedelta(days={"manana": 1, "pasado manana": 2}.get(m.group("dia") or "", 0))
    momento = datetime.combine(dia, datetime.min.time()).replace(hour=hora, minute=minutos)
    if not franja and not m.group("dia") and hora <= 12 and momento <= ahora:
        # "a las 6" dicho a las 18:10 es a las 18, no mañana a la mañana.
        tarde = momento + timedelta(hours=12)
        momento = tarde if hora < 12 and tarde > ahora else momento + timedelta(days=1)
    elif momento <= ahora:
        momento += timedelta(days=1)
    return momento, m.start(), m.end()


# "avisame cuando sean las 7": lo que queda al sacar la hora no es un mensaje.
_RELLENO_DE_AVISO = {"que", "de", "para", "a", "me", "y", "cuando", "sea", "sean", "son", "es", "ya", "se", "hagan",
                     "haga", "den", "llegue", "lleguen"}


def _interpretar_recordatorio(palabras: list[Palabra], ahora: datetime, verbo: int = 0) -> Accion | None:
    """"avisame a las 6 y 21 que tengo que salir" -> cuándo y qué decir.

    verbo: posición del "avisame"; antes solo puede venir la hora ("en cinco minutos recordame que...").
    """
    resto = palabras[:verbo] + palabras[verbo + 1:]
    normas = [p.norma for p in resto]
    frase = " ".join(normas)
    encontrado = cuando(frase, ahora)
    if encontrado is None:
        return None  # sin hora clara, que lo resuelva el cerebro
    momento, inicio, fin = encontrado
    # Pasar las posiciones en el texto a posiciones de palabras.
    posiciones, posicion = [], 0
    for norma in normas:
        posiciones.append(posicion)
        posicion += len(norma) + 1
    fuera = [not (inicio <= desde < fin) for desde in posiciones]
    if any(f and p.norma not in _MULETILLAS | _CONECTORES for p, f in zip(resto[:verbo], fuera)):
        return None  # antes del verbo había algo más que la hora: es otra clase de frase
    sin_hora = [p for p, f in zip(resto[verbo:], fuera[verbo:]) if f]
    while sin_hora and sin_hora[0].norma in _RELLENO_DE_AVISO:
        sin_hora = sin_hora[1:]
    mensaje = _texto_dicho(sin_hora) if sin_hora else "Ya " + hora_hablada(momento)
    if palabras[verbo].norma == "despertame" and not sin_hora:
        mensaje = "Arriba, es hora de despertarse"
    return Accion("recordatorio", mensaje, valor=int(momento.timestamp()))


def _nombre_de_proyecto(palabras: list[Palabra]) -> str:
    """"el proyecto de cancha libre para ver el front" -> "cancha libre"."""
    for i, palabra in enumerate(palabras):
        if i and palabra.norma in _FIN_DEL_NOMBRE:
            palabras = palabras[:i]
            break
    while palabras and palabras[0].norma in _ARTICULOS | {"proyecto", "proyectos", "todo"}:
        palabras = palabras[1:]
    return unir(palabras)


def _interpretar_clausula(palabras: list[Palabra], ahora: datetime | None = None) -> list[Accion]:
    palabras, segundo_plano = _sacar_segundo_plano(palabras)
    if not palabras:
        return []
    fija = _accion_fija(" ".join(p.norma for p in palabras))
    if fija:
        return [fija]
    con_cola = palabras
    while con_cola and con_cola[0].norma in _MULETILLAS:
        con_cola = con_cola[1:]
    # El verbo puede venir después de la hora: "en cinco minutos recordame que...".
    avisar = next((i for i, p in enumerate(con_cola[:8]) if p.norma in _RECORDAR), None)
    if avisar is not None:
        recordatorio = _interpretar_recordatorio(con_cola, ahora or datetime.now(), avisar)
        if recordatorio or avisar == 0:
            return [recordatorio or Accion("desconocido", unir(con_cola))]
    avisos = {"recordatorio", "recordatorios", "aviso", "avisos", "alarma"}
    if len(con_cola) > 1 and con_cola[0].norma in _CANCELAR and avisos & {p.norma for p in con_cola[1:3]}:
        cual = next(i for i, p in enumerate(con_cola) if p.norma in avisos)
        resto = [p for p in con_cola[cual + 1:] if p.norma not in ("de", "que", "del", "la", "el")]
        return [Accion("cancelar_recordatorio", unir(resto))]
    if con_cola and con_cola[0].norma in _NOTA and not (
            con_cola[0].norma in _MENSAJE and len(con_cola) > 2 and con_cola[1].norma in _HACIA):
        nota = _interpretar_nota(con_cola)
        if nota:
            return [nota]
    if con_cola and con_cola[0].norma in _MENSAJE:
        # El final de la frase es parte del mensaje: no se le saca el "gracias".
        mensaje = _interpretar_mensaje(con_cola[1:])
        return [mensaje or Accion("desconocido", unir(con_cola))]
    palabras = _sin_muletillas(palabras)
    if not palabras:
        return []
    frase = " ".join(p.norma for p in palabras)
    fija = _accion_fija(frase)
    if fija:
        return [fija]

    verbo, resto = palabras[0].norma, palabras[1:]
    if verbo in _ABRIR_A_LA_VISTA:
        segundo_plano = False

    if verbo in _ABRIR_ESO:
        _, programa = _sacar_programa(resto)
        return [Accion("abrir_eso", programa=programa)]

    hay_proyecto = any(p.norma in ("proyecto", "proyectos") for p in resto)
    if verbo in _LEVANTAR or (hay_proyecto and verbo in _LEVANTAR_PROYECTO | _BAJAR_PROYECTO):
        nombre = _nombre_de_proyecto(resto)
        if nombre:
            tipo = "proyecto" if verbo in _LEVANTAR_PROYECTO else "proyecto_detener"
            return [Accion(tipo, nombre, segundo_plano=segundo_plano)]

    if verbo in _ABRIR | _BUSCAR and _es_de_archivos([p.norma for p in resto]):
        return [_interpretar_archivo(resto, segundo_plano)]

    if verbo in _ABRIR:
        video = next((i for i, p in enumerate(resto) if p.norma in _VIDEO), None)
        if video is not None and len(resto) > video + 2:
            # "abrime en otra pestaña el video de tal cosa": no es un programa, es reproducirlo en YouTube.
            pedido, _ = _sin_descriptores(resto[video:])
            pedido, _ = _sacar_plataforma(pedido)
            return [Accion("reproducir", unir(_hasta_la_cortesia(pedido)), "youtube", segundo_plano)]
        objetivos = []
        for objetivo in _dividir_objetivos(resto):
            objetivo = _sin_prefijos(objetivo, _ARTICULOS)
            corte = next((i for i, p in enumerate(objetivo) if i and p.norma in _FIN_DEL_NOMBRE), len(objetivo))
            objetivos.append(objetivo[:corte])
        acciones = [Accion("abrir", unir(o), segundo_plano=segundo_plano) for o in objetivos if o]
        if acciones:
            return acciones

    elif verbo in _REPRODUCIR:
        if not resto:
            return [Accion("desconocido", unir(palabras))]  # "poneme..." y nada más: la frase quedó cortada
        resto, plataforma = _sacar_plataforma(resto)
        resto = _hasta_la_cortesia(resto)
        while resto and resto[-1].norma in ("en", "por", "con", "de", "del", "y", "la", "el"):
            resto = resto[:-1]  # se cortó antes de terminar: "poneme don't speak en..."
        a_gusto = _MUSICA_A_GUSTO.search(" ".join(p.norma for p in resto))
        if a_gusto:
            # No dijo qué: lo elige el cerebro (o, sin él, lo que diga config.json).
            return [Accion("musica_a_gusto", unir(resto), plataforma, segundo_plano)]
        resto, es_video = _sin_descriptores(resto)
        if not resto:
            return [Accion("continuar", plataforma=plataforma)]  # "poné la canción": seguir con lo que estaba
        if plataforma is None and len(resto) <= 2 and plataforma_de(" ".join(p.norma for p in resto)):
            return [Accion("abrir", unir(resto), segundo_plano=segundo_plano)]  # "poné spotify"
        if plataforma is None and es_video:
            plataforma = "youtube"
        return [Accion("reproducir", unir(resto), plataforma, segundo_plano)]

    elif verbo in _BUSCAR:
        resto, plataforma = _sacar_plataforma(resto)
        if resto:
            return [Accion("buscar", unir(resto), plataforma, segundo_plano)]

    elif verbo in _CERRAR:
        if resto and resto[0].norma in ("todo", "todos", "todas"):
            # "cerrá todo menos Spotify y Discord"
            salvo = next((i for i, p in enumerate(resto) if p.norma in ("menos", "excepto", "salvo")), len(resto))
            excepciones = [unir(_sin_prefijos(o, _ARTICULOS)) for o in _dividir_objetivos(resto[salvo + 1:])]
            return [Accion("cerrar_todo", ",".join(excepciones))]
        resto = _sin_prefijos(resto, _ARTICULOS)
        if resto:
            return [Accion("cerrar", unir(resto))]

    elif plataforma_de(frase):  # solo "youtube"
        return [Accion("abrir", unir(palabras), segundo_plano=segundo_plano)]

    return [Accion("desconocido", unir(palabras))]


_ES_BLOC = {"bloc de notas", "notepad", "nota", "notas", "una nota", "nota nueva"}


def interpretar(entrada, ahora: datetime | None = None) -> list[Accion]:
    """Texto (o palabras) posterior al llamado -> acciones en orden."""
    palabras = tokenizar(entrada) if isinstance(entrada, str) else entrada
    palabras, mostrar = _sacar_mostrar(palabras)
    acciones: list[Accion] = []
    contexto = None  # (plataforma, segundo plano, acción "abrir" que la nombró)
    for clausula in _clausulas(palabras):
        for accion in _interpretar_clausula(clausula, ahora):
            if accion.tipo == "abrir_eso":
                # "...y abrilo en Brave" completa la búsqueda del archivo anterior.
                if accion.programa and acciones and acciones[-1].tipo == "archivo":
                    acciones[-1].programa = accion.programa
                continue
            if accion.tipo == "nota" and acciones and acciones[-1].tipo == "abrir" \
                    and normalizar(acciones[-1].objetivo) in _ES_BLOC:
                # "abrí un bloc de notas y escribí X": la nota ya se abre en un bloc de notas.
                accion.valor = 1
                accion.segundo_plano = acciones.pop().segundo_plano
            if accion.tipo == "abrir":
                plataforma = plataforma_de(normalizar(accion.objetivo))
                if plataforma:
                    contexto = (plataforma, accion.segundo_plano, accion)
            elif accion.tipo in ("reproducir", "buscar") and accion.plataforma is None and contexto:
                plataforma, segundo_plano, abrir = contexto
                if accion.tipo == "buscar" or plataforma in ("spotify", "youtube"):
                    # "abrí spotify y poné X": reproducir ya abre, sobra el "abrir".
                    accion.plataforma = plataforma
                    if accion.segundo_plano is None:
                        accion.segundo_plano = segundo_plano
                    acciones = [a for a in acciones if a is not abrir]
            acciones.append(accion)
    if mostrar:
        for accion in acciones:
            accion.segundo_plano = False
    for accion in acciones:
        # "levantá cancha libre para ver el front": quiere verlo aunque no diga "mostrame".
        if accion.tipo == "proyecto" and accion.segundo_plano is None and pide_mostrar(palabras):
            accion.segundo_plano = False
    return acciones


# Palabras con las que alguien pide ver algo sin decir "mostrámelo": "la ventana de WhatsApp",
# "quiero verlo", "traelo", "ponelo acá".
_QUIERE_VER = {
    "ver", "verlo", "verla", "verlos", "veo", "vea", "pantalla", "ventana", "frente", "adelante", "vista",
    "visible", "trae", "traeme", "traelo", "traela", "aca", "maximiza", "maximizar", "maximizalo", "agranda",
}


def pide_mostrar(palabras: list[Palabra]) -> bool:
    """¿Dijo algo que indique que quiere verlo en pantalla? Sin esto, el cerebro abre todo en segundo plano."""
    normas = [p.norma for p in palabras]
    if set(normas) & (_MOSTRAR_FINAL | _ABRIR_A_LA_VISTA | _QUIERE_VER):
        return True
    # El reconocedor a veces escribe "en batalla" o "en pantaya" por "en pantalla".
    if any(anterior == "en" and parecido(norma, "pantalla") >= 0.75 for anterior, norma in zip(normas, normas[1:])):
        return True
    return any(tuple(normas[i:i + len(f)]) == f for f in _MOSTRAR_FRASES for i in range(len(normas)))


_OFRECE_VERLO = re.compile(r"\b(?:en pantalla|a la vista|al frente|traiga|traigo|muestro|muestre|mostrartel[oa]"
                           r"|verl[oa]|quedo minimizad[oa]|quedo en segundo plano)\b")
_ACEPTA = _SI | {"quiero", "ponelo", "ponela", "traelo", "traela", "mostralo", "mostrala", "bueno", "porfa", "favor"}


def acepta_verlo(ofrecido: str, palabras: list[Palabra]) -> bool:
    """Claudio avisó que algo quedó en segundo plano (u ofreció mostrarlo) y la respuesta es un sí:
    "¿lo querés en pantalla?" - "sí, dale" / "lo quiero ya"."""
    if not _OFRECE_VERLO.search(normalizar(ofrecido)):
        return False
    normas = {p.norma for p in palabras}
    return bool(normas & _ACEPTA) and not normas & _NO


def frase_cortada(texto: str) -> bool:
    """¿La frase quedó por la mitad? El reconocedor la termina en puntos suspensivos o en una palabra suelta:
    "poneme...", "avisame cuando sean las", "poneme don't speak en"."""
    texto = texto.strip()
    if texto.endswith(("...", "…")):
        return True
    if texto.endswith(("?", "!")):
        return False  # "¿y para qué?" termina en una palabra suelta pero está entera
    palabras = tokenizar(texto)
    return len(palabras) > 1 and palabras[-1].norma in _COLGADAS


_COLGADAS = {"en", "de", "del", "a", "al", "las", "los", "el", "la", "un", "una", "y", "que", "con", "por", "para",
             "mi", "me", "le", "lo"}


def es_afirmacion(texto: str) -> bool:
    """¿La respuesta a una pregunta de confirmación fue un sí?"""
    normas = {p.norma for p in tokenizar(texto)}
    return bool(normas & _SI) and not normas & _NO
