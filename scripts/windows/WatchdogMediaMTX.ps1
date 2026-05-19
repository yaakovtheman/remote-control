param(
    [Parameter(Mandatory = $true)][string]$MediamtxExe,
    [Parameter(Mandatory = $true)][string]$MediamtxCfg,
    [Parameter(Mandatory = $true)][string]$LogFile,
    [Parameter(Mandatory = $true)][string]$PidFile,
    [Parameter(Mandatory = $true)][string]$WatchdogPidFile
)

# Watchdog writes to its own log so it doesn't conflict with mediamtx stdout.
$WatchdogLog = [System.IO.Path]::ChangeExtension($LogFile, $null) + "_watchdog.log"

Set-Content -Path $WatchdogPidFile -Value $PID

function Get-Timestamp { Get-Date -Format "yyyy-MM-dd HH:mm:ss" }
function Log([string]$msg){ Add-Content -Path $WatchdogLog -Value ("[$(Get-Timestamp)] $msg") }

function Is-MediamtxRunning {
    if (-not (Test-Path -LiteralPath $PidFile)) { return $false }
    $raw = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($raw -notmatch '^\d+$') { return $false }
    $proc = Get-Process -Id ([int]$raw) -ErrorAction SilentlyContinue
    return ($null -ne $proc -and -not $proc.HasExited)
}

while ($true) {
    Start-Sleep -Seconds 5

    if (-not (Is-MediamtxRunning)) {
        Log "MediaMTX not running  -  restarting"

        try {
            $p = Start-Process `
                -FilePath $MediamtxExe `
                -ArgumentList "`"$MediamtxCfg`"" `
                -RedirectStandardOutput $LogFile `
                -RedirectStandardError "$LogFile.err" `
                -WindowStyle Hidden `
                -PassThru

            Set-Content -Path $PidFile -Value $p.Id
            Log "Restarted with PID $($p.Id)"
        }
        catch {
            Log "Restart failed: $_"
        }
    }
}
