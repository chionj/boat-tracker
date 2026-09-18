@echo off
cd /d "%~dp0"
call refresh_boat_tracker.bat
if errorlevel 1 (
  echo Refresh failed.
  exit /b 1
)
echo Refresh complete.
pause
