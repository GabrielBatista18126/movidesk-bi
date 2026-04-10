# ════════════════════════════════════════════════════════════════
# agendar_etl.ps1 — Registra a tarefa agendada no Windows
#
# Execute UMA VEZ como Administrador para agendar o ETL:
#   powershell -ExecutionPolicy Bypass -File .\scripts\agendar_etl.ps1
#
# Depois o Windows roda o ETL automaticamente conforme configurado.
# ════════════════════════════════════════════════════════════════

$TaskName   = "MovideskBI_ETL"
$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ScriptPath = Join-Path $ProjectDir "scripts\run_etl.bat"
$LogDir     = Join-Path $ProjectDir "scripts\logs"

# Cria pasta de logs se não existir
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
    Write-Host "Pasta de logs criada: $LogDir"
}

# Remove tarefa anterior com o mesmo nome (para atualizar)
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Tarefa anterior removida."
}

# Ação: executar o .bat
$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$ScriptPath`""

# Gatilho 1: todos os dias úteis às 07:00 (carga da manhã)
$Trigger1 = New-ScheduledTaskTrigger `
    -Daily `
    -At "07:00AM"

# Gatilho 2: todos os dias úteis às 12:00 (carga do meio-dia)
$Trigger2 = New-ScheduledTaskTrigger `
    -Daily `
    -At "12:00PM"

# Gatilho 3: todos os dias às 18:00 (carga do fim do dia)
$Trigger3 = New-ScheduledTaskTrigger `
    -Daily `
    -At "06:00PM"

# Configurações da tarefa
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# Registra a tarefa (roda como o usuário atual, sem exigir login)
Register-ScheduledTask `
    -TaskName    $TaskName `
    -Action      $Action `
    -Trigger     @($Trigger1, $Trigger2, $Trigger3) `
    -Settings    $Settings `
    -Description "ETL incremental do Movidesk BI — atualiza clientes, tickets e time entries" `
    -RunLevel    Highest

Write-Host ""
Write-Host "✓ Tarefa '$TaskName' registrada com sucesso!"
Write-Host "  Executa diariamente às: 07:00 | 12:00 | 18:00"
Write-Host ""
Write-Host "Comandos úteis:"
Write-Host "  Ver status:    Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Rodar agora:   Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Remover:       Unregister-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Ver logs:      dir $LogDir"
