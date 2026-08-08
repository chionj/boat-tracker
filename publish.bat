@echo off
rem Publishes the latest boat tracker dashboard to GitHub Pages.
rem Safe to run any time; does nothing if there are no changes.
cd /d "%~dp0"
copy /Y dashboard.html index.html >nul
git add -A
git commit -m "Daily boat tracker update %date% %time%"
git push origin main
