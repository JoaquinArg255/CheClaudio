@echo off
rem Se corre una sola vez: abre WhatsApp Web para escanear el QR con el telefono.
cd /d "%~dp0"
chcp 65001 >nul
.venv\Scripts\python.exe -m che_claudio --vincular-whatsapp
pause
