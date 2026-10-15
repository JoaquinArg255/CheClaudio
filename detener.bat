@echo off
rem Apaga el asistente cuando corre oculto.
cd /d "%~dp0"
chcp 65001 >nul
.venv\Scripts\python.exe -m che_claudio --detener
timeout /t 2 >nul
