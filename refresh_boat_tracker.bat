@echo off
rem Refreshes the local dashboard from the latest scan data.
cd /d "%~dp0"
"C:\Users\johnc\AppData\Local\Programs\Python\Python312\python.exe" "boat_tracker\update_listings.py"
