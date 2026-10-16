@echo off
rem Crea el entorno virtual e instala las dependencias. Se corre una sola vez.
cd /d "%~dp0.."

if not exist .venv (
    py -3 -m venv .venv || python -m venv .venv || goto :error
)
.venv\Scripts\python.exe -m pip install --upgrade pip || goto :error
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto :error

rem Con placa NVIDIA se instalan las librerias para transcribir mucho mas rapido (~1.3 GB).
where nvidia-smi >nul 2>nul && .venv\Scripts\python.exe -m pip install -r requirements-gpu.txt

echo.
echo Listo. Ejecuta scripts\iniciar.bat para empezar.
pause
exit /b 0

:error
echo.
echo Algo fallo en la instalacion. Revisa que Python 3.10 o superior este instalado.
pause
exit /b 1
