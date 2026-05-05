#requires -Version 5.1
<#
.SYNOPSIS
  מרכז שליטה — ממשק WinForms להפעלת סקריפטי ה- BAT הקיימים.

  קיצור דרך בשולחן העבודה (Desktop shortcut):
    Target:
      powershell.exe -ExecutionPolicy Bypass -File "C:\path\to\control\scripts\windows\ControlCenterGui.ps1"
    Start in (אופציונלי):
      C:\path\to\control\scripts\windows

  הרצה ידנית:
    powershell.exe -ExecutionPolicy Bypass -File ControlCenterGui.ps1

  הסקריפט מגדיר CONTROL_NONINTERACTIVE=1 לתהליך cmd — קבצי ה- BAT מדלגים על pause
  (התנהגות רגילה בלחיצה כפולה על ה- BAT לא משתנה).
#>

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$ScriptRoot = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ScriptRoot)) {
  $ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$RootDir = (Resolve-Path (Join-Path $ScriptRoot '..\..')).Path
$PidsDir = Join-Path $RootDir 'logs\pids'
$ConfigPath = Join-Path $RootDir 'app\config.json'
$SettingsWebPort = 8088

function Get-BrowserBaseUrl {
  $ip = '127.0.0.1'
  if (Test-Path -LiteralPath $ConfigPath) {
    try {
      $raw = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8
      $cfg = $raw | ConvertFrom-Json
      if ($null -ne $cfg.server_ip -and -not [string]::IsNullOrWhiteSpace([string]$cfg.server_ip)) {
        $ip = [string]$cfg.server_ip
      }
    }
    catch { }
  }
  return "http://${ip}:${SettingsWebPort}/"
}

function Test-PausePromptTail {
  param([string]$Tail)
  if ([string]::IsNullOrEmpty($Tail)) { return $false }
  # pause / PAUSE is localized; cover common English + Hebrew phrasing
  if ($Tail -match '(?i)Press any key') { return $true }
  if ($Tail -match 'להמשיך') { return $true }
  if ($Tail -match '(?i)Press any key to continue') { return $true }
  return $false
}

function Append-UiLog {
  param(
    [System.Windows.Forms.TextBox]$Box,
    [string]$Text,
    [System.Windows.Forms.Form]$Form
  )
  if ($null -eq $Box -or $null -eq $Form) { return }
  $suffix = if ($Text.EndsWith("`r`n")) { $Text } else { $Text + "`r`n" }
  if ($Form.InvokeRequired) {
    [void]$Form.Invoke([Action] { $Box.AppendText($suffix); $Box.SelectionStart = $Box.Text.Length; $Box.ScrollToCaret() })
  }
  else {
    $Box.AppendText($suffix)
    $Box.SelectionStart = $Box.Text.Length
    $Box.ScrollToCaret()
  }
}

function Set-ButtonsEnabled {
  param([bool]$Enabled, [System.Windows.Forms.Button[]]$Buttons)
  foreach ($b in $Buttons) {
    if ($null -ne $b) { $b.Enabled = $Enabled }
  }
}

function Invoke-ControlBat {
  param(
    [Parameter(Mandatory = $true)][string]$BatchFileName,
    [System.Windows.Forms.TextBox]$OutBox,
    [System.Windows.Forms.Form]$Form,
    [System.Windows.Forms.Button[]]$Buttons,
    [bool]$ManageButtons = $true
  )

  $batPath = Join-Path $ScriptRoot $BatchFileName
  if (-not (Test-Path -LiteralPath $batPath)) {
    Append-UiLog -Box $OutBox -Form $Form -Text ("קובץ לא נמצא: " + $batPath)
    return
  }
  if ($ManageButtons) {
    Set-ButtonsEnabled -Enabled $false -Buttons $Buttons
  }
  Append-UiLog -Box $OutBox -Form $Form -Text ("========== " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + " :: " + $BatchFileName + " ==========")

  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = 'cmd.exe'
  $psi.Arguments = '/c call "' + $batPath + '"'
  $psi.WorkingDirectory = $RootDir
  $psi.UseShellExecute = $false
  $psi.EnvironmentVariables['CONTROL_NONINTERACTIVE'] = '1'
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.CreateNoWindow = $true
  try {
    $cp = [int][Console]::OutputEncoding.CodePage
    $psi.StandardOutputEncoding = [System.Text.Encoding]::GetEncoding($cp)
  }
  catch {
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
  }
  $psi.StandardErrorEncoding = $psi.StandardOutputEncoding

  $proc = New-Object System.Diagnostics.Process
  $proc.StartInfo = $psi
  $proc.EnableRaisingEvents = $true

  $sb = New-Object System.Text.StringBuilder
  $sbLock = New-Object object

  $enqueueUiLine = {
    param([string]$x)
    [void]$Form.BeginInvoke([System.Windows.Forms.MethodInvoker] { Append-UiLog -Box $OutBox -Form $Form -Text $x })
  }

  $dataHandler = [System.Diagnostics.DataReceivedEventHandler] {
    param([object]$sender, [System.Diagnostics.DataReceivedEventArgs]$e)
    if ($null -eq $e.Data) { return }
    $line = $e.Data
    [System.Threading.Monitor]::Enter($sbLock)
    try { [void]$sb.AppendLine($line) }
    finally { [System.Threading.Monitor]::Exit($sbLock) }
    & $enqueueUiLine $line
  }

  $proc.add_OutputDataReceived($dataHandler)
  $proc.add_ErrorDataReceived($dataHandler)

  [void]$proc.Start()
  $proc.BeginOutputReadLine()
  $proc.BeginErrorReadLine()

  $lastGrow = 0
  $stall = [DateTime]::UtcNow

  while (-not $proc.HasExited) {
    [System.Windows.Forms.Application]::DoEvents()
    Start-Sleep -Milliseconds 80

    [System.Threading.Monitor]::Enter($sbLock)
    try {
      $len = $sb.Length
      $full = $sb.ToString()
    }
    finally { [System.Threading.Monitor]::Exit($sbLock) }

    if ($len -ne $lastGrow) {
      $lastGrow = $len
      $stall = [DateTime]::UtcNow
    }
    $tail = if ($full.Length -gt 800) { $full.Substring($full.Length - 800) } else { $full }
    if (($len -gt 40) -and (([DateTime]::UtcNow - $stall).TotalMilliseconds -gt 900)) {
      if (Test-PausePromptTail -Tail $tail) {
        Append-UiLog -Box $OutBox -Form $Form -Text '[ממשק] זוהתה בקשת Enter בסוף הסקריפט — סוגרים אוטומטית כדי לא לנעול את החלון.'
        try { $proc.Kill() } catch { }
        break
      }
    }
  }

  if (-not $proc.HasExited) {
    try { $proc.WaitForExit(3000) } catch { }
  }
  try { $proc.CancelOutputRead() } catch { }
  try { $proc.CancelErrorRead() } catch { }

  $proc.remove_OutputDataReceived($dataHandler)
  $proc.remove_ErrorDataReceived($dataHandler)

  $exitDisplay = '?'
  try {
    if ($proc.HasExited) { $exitDisplay = [string]$proc.ExitCode }
  }
  catch { }

  try { $proc.Dispose() } catch { }

  Append-UiLog -Box $OutBox -Form $Form -Text ("========== סיום (" + $BatchFileName + ") קוד יציאה: " + $exitDisplay + " ==========")
  if ($ManageButtons) {
    Set-ButtonsEnabled -Enabled $true -Buttons $Buttons
  }
}

function Get-ServiceSummary {
  $names = @(
    @{ Label = 'SettingsServer'; File = 'settings_server.pid' },
    @{ Label = 'RemotePiClient'; File = 'remote_pi_client.pid' },
    @{ Label = 'MediaMTX';       File = 'mediamtx.pid' }
  )
  $up = 0
  $lines = New-Object System.Collections.Generic.List[string]
  foreach ($n in $names) {
    $pf = Join-Path $PidsDir $n.File
    if (-not (Test-Path -LiteralPath $pf)) {
      $lines.Add(($n.Label + ': למטה (אין קובץ pid)'))
      continue
    }
    $pidText = (Get-Content -LiteralPath $pf -Raw -ErrorAction SilentlyContinue).Trim()
    if ([string]::IsNullOrWhiteSpace($pidText)) {
      $lines.Add(($n.Label + ': למטה (pid ריק)'))
      continue
    }
    $pidNum = 0
    if (-not [int]::TryParse($pidText, [ref]$pidNum)) {
      $lines.Add(($n.Label + ': למטה (pid לא מספרי)'))
      continue
    }
    $proc = Get-Process -Id $pidNum -ErrorAction SilentlyContinue
    if ($null -ne $proc) {
      $up++
      $lines.Add(($n.Label + ': פעיל (pid ' + $pidText + ')'))
    }
    else {
      $lines.Add(($n.Label + ': למטה (pid ישן ' + $pidText + ')'))
    }
  }
  $state = if ($up -eq 3) { 'רץ' } elseif ($up -eq 0) { 'עצור' } else { ('חלקי (' + $up + '/3)') }
  return [PSCustomObject]@{ State = $state; Detail = ($lines -join ' | ') }
}

function Get-PortSnippet {
  try {
    $r = netstat -ano 2>$null | Select-String -Pattern ':8088\s'
    if ($null -eq $r) { return '' }
    $txt = ($r | Select-Object -First 4 | ForEach-Object { $_.Line.Trim() }) -join ' ; '
    if ($txt.Length -gt 220) { return $txt.Substring(0, 217) + '...' }
    return $txt
  }
  catch { return '' }
}

# --- UI ---
$form = New-Object System.Windows.Forms.Form
$form.Text = 'מרכז שליטה'
$form.RightToLeft = [System.Windows.Forms.RightToLeft]::Yes
$form.RightToLeftLayout = $true
$form.Font = New-Object System.Drawing.Font('Segoe UI', 10.0, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Point)
$form.Size = New-Object System.Drawing.Size(820, 660)
$form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
$form.MaximizeBox = $false
$form.MinimizeBox = $true

$topPanel = New-Object System.Windows.Forms.Panel
$topPanel.Dock = [System.Windows.Forms.DockStyle]::Top
$topPanel.Height = 118
$topPanel.Padding = New-Object System.Windows.Forms.Padding(10, 10, 10, 6)

$lblState = New-Object System.Windows.Forms.Label
$lblState.AutoSize = $false
$lblState.Dock = [System.Windows.Forms.DockStyle]::Top
$lblState.Height = 26
$lblState.TextAlign = [System.Drawing.ContentAlignment]::MiddleRight
$lblState.Text = 'מצב: —'

$lblPorts = New-Object System.Windows.Forms.Label
$lblPorts.AutoSize = $false
$lblPorts.Dock = [System.Windows.Forms.DockStyle]::Top
$lblPorts.Height = 36
$lblPorts.TextAlign = [System.Drawing.ContentAlignment]::MiddleRight
$lblPorts.ForeColor = [System.Drawing.Color]::DimGray
$lblPorts.Text = 'פורטים: —'

$lblUrl = New-Object System.Windows.Forms.Label
$lblUrl.AutoSize = $false
$lblUrl.Dock = [System.Windows.Forms.DockStyle]::Top
$lblUrl.Height = 26
$lblUrl.TextAlign = [System.Drawing.ContentAlignment]::MiddleRight
$lblUrl.Text = ('כתובת: ' + (Get-BrowserBaseUrl))

$topPanel.Controls.Add($lblUrl)
$topPanel.Controls.Add($lblPorts)
$topPanel.Controls.Add($lblState)

$btnPanel = New-Object System.Windows.Forms.FlowLayoutPanel
$btnPanel.Dock = [System.Windows.Forms.DockStyle]::Top
$btnPanel.Height = 120
$btnPanel.Padding = New-Object System.Windows.Forms.Padding(10, 4, 10, 6)
$btnPanel.WrapContents = $true
$btnPanel.FlowDirection = [System.Windows.Forms.FlowDirection]::RightToLeft
$btnPanel.RightToLeft = [System.Windows.Forms.RightToLeft]::Yes

function New-BarButton {
  param([string]$HebrewText, [int]$Width = 150)
  $b = New-Object System.Windows.Forms.Button
  $b.Text = $HebrewText
  $b.Width = $Width
  $b.Height = 36
  $b.Margin = New-Object System.Windows.Forms.Padding(6, 6, 6, 6)
  $b.UseVisualStyleBackColor = $true
  return $b
}

$btnInstall = New-BarButton 'התקנה' 140
$btnStart = New-BarButton 'הפעלה' 140
$btnStop = New-BarButton 'עצירה' 140
$btnRestart = New-BarButton 'הפעלה מחדש' 160
$btnStatus = New-BarButton 'מצב' 120
$btnCleanup = New-BarButton 'ניקוי' 130
$btnBrowser = New-BarButton 'פתיחת מערכת' 170

$btnPanel.Controls.Add($btnBrowser)
$btnPanel.Controls.Add($btnCleanup)
$btnPanel.Controls.Add($btnStatus)
$btnPanel.Controls.Add($btnRestart)
$btnPanel.Controls.Add($btnStop)
$btnPanel.Controls.Add($btnStart)
$btnPanel.Controls.Add($btnInstall)

$split = New-Object System.Windows.Forms.Panel
$split.Dock = [System.Windows.Forms.DockStyle]::Fill
$split.Padding = New-Object System.Windows.Forms.Padding(10, 0, 10, 10)

$output = New-Object System.Windows.Forms.TextBox
$output.Multiline = $true
$output.ReadOnly = $true
$output.ScrollBars = [System.Windows.Forms.ScrollBars]::Both
$output.WordWrap = $false
$output.Dock = [System.Windows.Forms.DockStyle]::Fill
$output.Font = New-Object System.Drawing.Font('Segoe UI', 9.5, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Point)
$output.BackColor = [System.Drawing.Color]::FromArgb(250, 250, 252)

$lblLog = New-Object System.Windows.Forms.Label
$lblLog.Dock = [System.Windows.Forms.DockStyle]::Top
$lblLog.Height = 24
$lblLog.TextAlign = [System.Drawing.ContentAlignment]::MiddleRight
$lblLog.Text = 'פלט'

$split.Controls.Add($output)
$split.Controls.Add($lblLog)

$form.Controls.Add($split)
$form.Controls.Add($btnPanel)
$form.Controls.Add($topPanel)

$allButtons = @($btnInstall, $btnStart, $btnStop, $btnRestart, $btnStatus, $btnCleanup, $btnBrowser)

$refreshStatus = {
  $s = Get-ServiceSummary
  $lblState.Text = ('מצב: ' + $s.State + ' — ' + $s.Detail)
  $p = Get-PortSnippet
  if ([string]::IsNullOrWhiteSpace($p)) {
    $lblPorts.Text = 'פורטים: אין האזנה מזוהה ב-8088 (או netstat לא זמין)'
  }
  else {
    $lblPorts.Text = ('פורטים (8088): ' + $p)
  }
  $lblUrl.Text = ('כתובת: ' + (Get-BrowserBaseUrl))
}

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 2500
$timer.Add_Tick({ & $refreshStatus })
$form.Add_Shown({ & $refreshStatus; $timer.Start() })
$form.Add_FormClosed({ $timer.Stop(); $timer.Dispose() })

$btnInstall.Add_Click({ Invoke-ControlBat -BatchFileName 'Install.bat' -OutBox $output -Form $form -Buttons $allButtons })
$btnStart.Add_Click({ Invoke-ControlBat -BatchFileName 'StartControl.bat' -OutBox $output -Form $form -Buttons $allButtons })
$btnStop.Add_Click({ Invoke-ControlBat -BatchFileName 'StopControl.bat' -OutBox $output -Form $form -Buttons $allButtons })
$btnStatus.Add_Click({ Invoke-ControlBat -BatchFileName 'Status.bat' -OutBox $output -Form $form -Buttons $allButtons })
$btnCleanup.Add_Click({ Invoke-ControlBat -BatchFileName 'CleanupControl.bat' -OutBox $output -Form $form -Buttons $allButtons })

$btnRestart.Add_Click({
  Set-ButtonsEnabled -Enabled $false -Buttons $allButtons
  try {
    Append-UiLog -Box $output -Form $form -Text ("========== " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + " :: הפעלה מחדש (עצירה → המתנה → הפעלה) ==========")
    Invoke-ControlBat -BatchFileName 'StopControl.bat' -OutBox $output -Form $form -Buttons $allButtons -ManageButtons $false
    Start-Sleep -Seconds 2
    Invoke-ControlBat -BatchFileName 'StartControl.bat' -OutBox $output -Form $form -Buttons $allButtons -ManageButtons $false
  }
  finally {
    Set-ButtonsEnabled -Enabled $true -Buttons $allButtons
  }
})

$btnBrowser.Add_Click({
  try {
    $u = Get-BrowserBaseUrl
    Append-UiLog -Box $output -Form $form -Text ('פותח דפדפן: ' + $u)
    Start-Process $u
  }
  catch {
    Append-UiLog -Box $output -Form $form -Text ('שגיאה בפתיחת דפדפן: ' + $_.Exception.Message)
  }
})

[void]$form.ShowDialog()
