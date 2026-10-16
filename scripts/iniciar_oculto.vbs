' Inicia el asistente sin ventana. Lo que hace queda en datos\che_claudio.log.
' Para apagarlo: decir "Che Claudio, chau" o ejecutar scripts\detener.bat.
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
carpeta = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
shell.CurrentDirectory = carpeta
shell.Run """" & carpeta & "\.venv\Scripts\pythonw.exe"" -m che_claudio", 0, False
