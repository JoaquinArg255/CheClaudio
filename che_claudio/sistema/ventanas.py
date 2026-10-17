"""Utilidades Win32: ventanas, foco, teclas y procesos."""
import ctypes
import os
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path

import pywintypes
import win32api
import win32con
import win32gui
import win32process

_kernel32 = ctypes.windll.kernel32
_user32 = ctypes.windll.user32
_dwmapi = ctypes.windll.dwmapi
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_DWMWA_CLOAKED = 14

VK_ALT = 0x12
VK_SILENCIO, VK_BAJAR_VOLUMEN, VK_SUBIR_VOLUMEN = 0xAD, 0xAE, 0xAF
VK_SIGUIENTE, VK_ANTERIOR, VK_PLAY_PAUSA = 0xB0, 0xB1, 0xB3

_LSFW_BLOQUEAR, _LSFW_DESBLOQUEAR = 1, 2
_candado_foco = threading.Lock()
_bloqueos_de_foco = 0


def _abrir_proceso(hwnd: int):
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return win32api.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    except pywintypes.error:
        return None


def exe_de(hwnd: int) -> str:
    """Nombre del ejecutable dueño de la ventana, en minúsculas ("spotify.exe")."""
    proceso = _abrir_proceso(hwnd)
    if not proceso:
        return ""
    ruta = ctypes.create_unicode_buffer(1024)
    largo = wintypes.DWORD(1024)
    if _kernel32.QueryFullProcessImageNameW(int(proceso), 0, ruta, ctypes.byref(largo)):
        return os.path.basename(ruta.value).lower()
    return ""


def inicio_de_pid(pid: int) -> float:
    """Cuándo arrancó el proceso con ese número (segundos desde 1970), o 0 si ya no existe."""
    try:
        proceso = win32api.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        return win32process.GetProcessTimes(proceso)["CreationTime"].timestamp()
    except (pywintypes.error, ValueError, OSError):
        return 0.0


def inicio_del_proceso(hwnd: int) -> float:
    """Cuándo arrancó el proceso dueño de la ventana (segundos desde 1970), o 0."""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
    except pywintypes.error:
        return 0.0
    return inicio_de_pid(pid)


def es_el_mismo(pid: int, inicio: float) -> bool:
    """¿Sigue vivo el proceso que arrancó a esa hora con ese número?

    Windows reutiliza los números: tras un reinicio, un número guardado puede ser de otro programa.
    """
    return bool(inicio) and abs(inicio_de_pid(pid) - inicio) < 1


def terminar(pid: int, inicio: float) -> bool:
    """Cierra el proceso y los que abrió, solo si sigue siendo el mismo. True si lo cerró."""
    if not es_el_mismo(pid, inicio):
        return False
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    return True


def anotar_proceso(ruta: Path, pid: int) -> None:
    """Guarda el número y la hora de inicio, para poder cerrarlo después sin equivocarse de proceso."""
    ruta.write_text(f"{pid} {inicio_de_pid(pid)}", encoding="utf-8")


def terminar_anotado(ruta: Path) -> bool:
    """Cierra el proceso anotado con `anotar_proceso`, si sigue siendo el mismo, y borra la nota."""
    try:
        pid, _, inicio = ruta.read_text(encoding="utf-8").strip().partition(" ")
        cerrado = terminar(int(pid), float(inicio or 0))
    except (OSError, ValueError):  # no había nota, o es de una versión anterior
        cerrado = False
    ruta.unlink(missing_ok=True)
    return cerrado


def ventanas_visibles() -> list[int]:
    """Ventanas principales con título."""
    encontradas = []

    def _visitar(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            encontradas.append(hwnd)
        return True

    win32gui.EnumWindows(_visitar, None)
    return encontradas


def ventanas_de_programas() -> list[int]:
    """Las ventanas que aparecen en la barra de tareas: sin paneles, superposiciones ni ventanas ocultas."""
    programas = []
    for hwnd in ventanas_visibles():
        if win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW:
            continue
        if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
            continue
        oculta = wintypes.DWORD()  # las apps de la Store suspendidas quedan "encapotadas"
        _dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), _DWMWA_CLOAKED, ctypes.byref(oculta), ctypes.sizeof(oculta))
        if not oculta.value:
            programas.append(hwnd)
    return programas


def ventanas_de(exe: str) -> list[int]:
    return [h for h in ventanas_visibles() if exe_de(h) == exe]


def titulo(hwnd: int) -> str:
    return win32gui.GetWindowText(hwnd)


def ventana_activa() -> int:
    return win32gui.GetForegroundWindow()


def esta_minimizada(hwnd: int) -> bool:
    return bool(win32gui.IsIconic(hwnd))


def minimizar(hwnd: int) -> None:
    """Minimiza. Si era la ventana activa, Windows le pasa el foco a la que estaba antes."""
    activa = win32gui.GetForegroundWindow() == hwnd
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE if activa else win32con.SW_SHOWMINNOACTIVE)
    except pywintypes.error:
        pass


def cerrar(hwnd: int) -> None:
    """Pide el cierre como si se apretara la X (la app puede preguntar si guardar)."""
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)


def bloquear_foco() -> None:
    """Impide que otros programas se pongan al frente. Una acción del usuario
    (click en otra ventana, Alt+Tab) lo destraba sola."""
    global _bloqueos_de_foco
    with _candado_foco:
        _bloqueos_de_foco += 1
        _user32.LockSetForegroundWindow(_LSFW_BLOQUEAR)


def desbloquear_foco() -> None:
    global _bloqueos_de_foco
    with _candado_foco:
        _bloqueos_de_foco = max(0, _bloqueos_de_foco - 1)
        if _bloqueos_de_foco == 0:
            _user32.LockSetForegroundWindow(_LSFW_DESBLOQUEAR)


def traer_al_frente(hwnd: int) -> bool:
    if not hwnd or not win32gui.IsWindow(hwnd):
        return False
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    if win32gui.GetForegroundWindow() != hwnd:
        try:
            win32gui.SetForegroundWindow(hwnd)
        except pywintypes.error:
            pass
    if win32gui.GetForegroundWindow() != hwnd:
        # Windows solo deja cambiar el foco a quien recibió la última entrada:
        # una pulsación de Alt nos da ese permiso.
        win32api.keybd_event(VK_ALT, 0, 0, 0)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except pywintypes.error:
            pass
        finally:
            win32api.keybd_event(VK_ALT, 0, win32con.KEYEVENTF_KEYUP, 0)
    for _ in range(10):
        if win32gui.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.05)
    return False


def tecla(vk: int, veces: int = 1) -> None:
    for _ in range(veces):
        win32api.keybd_event(vk, 0, 0, 0)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.01)


def bloquear_equipo() -> None:
    _user32.LockWorkStation()
