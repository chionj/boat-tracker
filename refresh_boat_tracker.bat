@echo off
rem Fetch fresh Craigslist listings, merge them, and rebuild the dashboard.
cd /d "%~dp0"
"C:\Users\johnc\AppData\Local\Programs\Python\Python312\python.exe" "boat_tracker\fetch_scan.py"
if errorlevel 1 (
  echo Fetch failed. Check network or Craigslist availability.
  exit /b 1
)
"C:\Users\johnc\AppData\Local\Programs\Python\Python312\python.exe" "boat_tracker\update_listings.py"
