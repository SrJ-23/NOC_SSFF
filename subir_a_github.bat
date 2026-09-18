@echo off
set "PATH=%LOCALAPPDATA%\MinGit\cmd;%PATH%"
echo === Subiendo cambios a GitHub ===
git push -u origin main
pause
