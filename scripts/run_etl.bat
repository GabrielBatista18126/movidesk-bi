@echo off
:: ════════════════════════════════════════════════════════════════
:: run_etl.bat — Executa o ETL incremental do Movidesk BI
::               Chamado pelo Windows Task Scheduler
:: ════════════════════════════════════════════════════════════════

:: Descobre a raiz do projeto a partir da pasta deste script
set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..") do set PROJECT_DIR=%%~fI

:: Ajuste para o Python do seu ambiente virtual (ou Python global)
set PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe

:: Arquivo de log com data no nome (um arquivo por dia)
set LOG_FILE=%PROJECT_DIR%\scripts\logs\etl_%DATE:~6,4%%DATE:~3,2%%DATE:~0,2%.log

:: Cria a pasta de logs se não existir
if not exist "%PROJECT_DIR%\scripts\logs" mkdir "%PROJECT_DIR%\scripts\logs"

echo [%DATE% %TIME%] Iniciando ETL incremental... >> "%LOG_FILE%"

cd /d "%PROJECT_DIR%"
"%PYTHON%" -m etl.main >> "%LOG_FILE%" 2>&1

if %ERRORLEVEL% EQU 0 (
    echo [%DATE% %TIME%] ETL finalizado com sucesso. >> "%LOG_FILE%"
) else (
    echo [%DATE% %TIME%] ERRO: ETL terminou com codigo %ERRORLEVEL%. >> "%LOG_FILE%"
)
