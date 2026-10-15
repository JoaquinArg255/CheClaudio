' Inicia el asistente sin ventana. Lo que hace queda en che_claudio.log.
' Para apagarlo: decir "Che Claudio, chau" o ejecutar detener.bat.
Set shell = CreateObject("WScript.Shell")
carpeta = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = carpeta
shell.Run """" & carpeta & "\.venv\Scripts\pythonw.exe"" -m che_claudio", 0, False
