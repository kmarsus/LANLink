$ErrorActionPreference = "SilentlyContinue"
Get-Process pythonw | Where-Object { $_.Path -like "*$([IO.Path]::DirectorySeparatorChar)LANLink$([IO.Path]::DirectorySeparatorChar)*" } | Stop-Process
Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath("Startup")) "LANLink.lnk")
Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath("Desktop")) "LANLink.lnk")
if (([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Get-NetFirewallRule -DisplayName "LANLink TCP" | Remove-NetFirewallRule
    Get-NetFirewallRule -DisplayName "LANLink Discovery" | Remove-NetFirewallRule
}
Write-Host "LANLink startup shortcuts and firewall rules removed. Settings and shared files were not deleted."

