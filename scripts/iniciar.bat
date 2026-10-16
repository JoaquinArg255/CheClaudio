@echo off
rem Inicia el asistente con una ventana donde se ve lo que entiende.
cd /d "%~dp0.."
title Che Claudio
chcp 65001 >nul
.venv\Scripts\python.exe -m che_claudio %*
pause
