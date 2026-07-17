@echo off
cd /d "%~dp0"
if not exist "LANLink.exe" (
  echo LANLink.exe is missing. Download the complete LANLink release package.
  pause
  exit /b 1
)
start "LANLink" "LANLink.exe"
