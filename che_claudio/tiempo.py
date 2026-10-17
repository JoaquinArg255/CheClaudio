"""Horas y fechas como se dicen: "en media hora", "a las 6 y cuarto", "son las 9 y media".

Lo usan las reglas (recordatorios), las acciones (qué hora es) y el cerebro (la fecha de cada mensaje).
"""
import re
from datetime import datetime, timedelta


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


_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
          "octubre", "noviembre", "diciembre")


def fecha_hablada(momento: datetime) -> str:
    """"viernes 16 de octubre de 2026"."""
    return f"{_DIAS[momento.weekday()]} {momento.day} de {_MESES[momento.month - 1]} de {momento.year}"


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
