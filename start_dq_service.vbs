' Starts the DQ Agent as a silent background process (no console window)
' Run this file to launch the app — it stays running even after closing the terminal.

Dim WshShell
Set WshShell = CreateObject("WScript.Shell")

Dim appDir
appDir = "C:\Users\jandh\OneDrive\Documents\Miracle\DQ"

Dim cmd
cmd = appDir & "\venv\Scripts\streamlit.exe run " & appDir & "\src\app.py --server.port=8501 --server.headless=true"

WshShell.Run cmd, 0, False

WScript.Echo "DQ Agent is now running at http://localhost:8501"
