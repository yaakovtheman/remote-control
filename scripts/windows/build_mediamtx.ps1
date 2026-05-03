param(
    [Parameter(Mandatory = $true)][string]$ScanJsonPath,
    [Parameter(Mandatory = $true)][string]$ConfigJsonPath,
    [Parameter(Mandatory = $true)][string]$MediaMtxYamlPath
)

$ErrorActionPreference = 'Stop'

$d = Get-Content -Raw -LiteralPath $ScanJsonPath | ConvertFrom-Json

$camUser = 'admin'
$camPass = 'Aa123456!'

if (Test-Path -LiteralPath $ConfigJsonPath) {
    try {
        $cfg = Get-Content -Raw -LiteralPath $ConfigJsonPath | ConvertFrom-Json
        if ($null -ne $cfg.camera_user -and -not [string]::IsNullOrWhiteSpace([string]$cfg.camera_user)) {
            $camUser = [string]$cfg.camera_user
        }
        if ($null -ne $cfg.camera_pass -and -not [string]::IsNullOrWhiteSpace([string]$cfg.camera_pass)) {
            $camPass = [string]$cfg.camera_pass
        }
    }
    catch {
        # keep defaults
    }
}

$cams = @()
if ($d.cameras) {
    $cams = @($d.cameras)
}

$lines = New-Object System.Collections.Generic.List[string]
$i = 1

if ($cams.Count -gt 0) {
    $lines.Add('paths:') | Out-Null
    foreach ($cam in $cams) {
        if ($null -eq $cam.ip -or [string]::IsNullOrWhiteSpace([string]$cam.ip)) {
            continue
        }
        $ip = [string]$cam.ip
        $lines.Add(('  cam{0}:' -f $i)) | Out-Null
        $src = '    source: rtsp://' + $camUser + ':' + $camPass + '@' + $ip + ':554/profile1'
        $lines.Add($src) | Out-Null
        $lines.Add('    rtspTransport: tcp') | Out-Null
        $i++
    }
}

if ($lines.Count -eq 0) {
    Set-Content -LiteralPath $MediaMtxYamlPath -Value 'paths: {}' -Encoding utf8
}
else {
    Set-Content -LiteralPath $MediaMtxYamlPath -Value ($lines -join [Environment]::NewLine) -Encoding utf8
}
