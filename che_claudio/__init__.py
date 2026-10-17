"""Che Claudio: asistente de voz para Windows."""
import ctypes
import os

# El paquete winrt trae un msvcp140.dll viejo. Si se carga antes que Whisper,
# el proceso se cae al iniciar el modelo. Cargar primero el del sistema hace
# que todos usen ese.
try:
    ctypes.WinDLL(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "msvcp140.dll"))
except OSError:
    pass

# Sin esto, en pantallas con zoom el avatar se ve borroso y las capturas salen recortadas.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (AttributeError, OSError):
    pass
