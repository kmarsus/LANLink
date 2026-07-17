$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppExe = Join-Path $ProjectDir "LANLink.exe"
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
    Write-Host "Requesting permission to configure Windows Firewall..." -ForegroundColor Yellow
    Start-Process powershell.exe -Verb RunAs -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$($MyInvocation.MyCommand.Path)`"")
    exit
}

Write-Host "Installing LANLink..." -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath $AppExe)) {
    throw "LANLink.exe is missing. Download and extract the complete LANLink release package before running the installer."
}

$StartupDir = [Environment]::GetFolderPath("Startup")
$StartupLink = Join-Path $StartupDir "LANLink.lnk"
$DesktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "LANLink.lnk"
$Shell = New-Object -ComObject WScript.Shell
foreach ($LinkSpec in @(
    @{ Path = $StartupLink; Args = "--no-browser" },
    @{ Path = $DesktopLink; Args = "" }
)) {
    $Shortcut = $Shell.CreateShortcut($LinkSpec.Path)
    $Shortcut.TargetPath = $AppExe
    $Shortcut.Arguments = $LinkSpec.Args
    $Shortcut.WorkingDirectory = $ProjectDir
    $Shortcut.Description = "LANLink office file sharing and remote support"
    $Shortcut.Save()
}

Get-NetFirewallRule -DisplayName "LANLink TCP" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Get-NetFirewallRule -DisplayName "LANLink Discovery" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "LANLink TCP" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -Profile Private | Out-Null
New-NetFirewallRule -DisplayName "LANLink Discovery" -Direction Inbound -Action Allow -Protocol UDP -LocalPort 53421 -Profile Private | Out-Null
Write-Host "Windows Firewall rules added for Private networks." -ForegroundColor Green

Start-Process -FilePath $AppExe -WorkingDirectory $ProjectDir
Write-Host "LANLink installed. It will start automatically when you sign in." -ForegroundColor Green
