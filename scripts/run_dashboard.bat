@echo off
set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..") do set PROJECT_DIR=%%~fI
cd /d "%PROJECT_DIR%"
.venv\Scripts\streamlit.exe run dashboard/app.py --server.port 8502 --server.headless false
