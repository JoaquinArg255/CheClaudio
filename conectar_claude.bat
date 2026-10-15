@echo off
rem Se corre una sola vez: inicia sesion en Claude con tu cuenta, para que Claudio pueda pensar.
cd /d "%~dp0"
chcp 65001 >nul
set CLAUDE=.venv\Lib\site-packages\claude_agent_sdk\_bundled\claude.exe
echo Se va a abrir el navegador para que inicies sesion con tu cuenta de Claude.
echo.
"%CLAUDE%" auth login
echo.
"%CLAUDE%" auth status
pause
