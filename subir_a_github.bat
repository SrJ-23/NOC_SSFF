@echo off
set "PATH=%LOCALAPPDATA%\MinGit\cmd;C:\Program Files\Git\cmd;%PATH%"

echo =========================================================
echo         SUBIR ACTUALIZACIONES A GITHUB (NOC)
echo =========================================================
echo.

where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] No se encontro Git ni MinGit en el sistema.
    pause
    exit /b 1
)

echo [1/3] Preparando y agregando archivos modificados...
git add -A

echo.
git diff --staged --quiet
if %ERRORLEVEL% equ 0 goto :skip_commit

echo [2/3] Guardando cambios locales...
git commit -m "Actualizacion automatica NOC %DATE%"
goto :do_push

:skip_commit
echo [2/3] No hay archivos nuevos pendientes de registrar.

:do_push
echo.
echo [3/3] Subiendo cambios a GitHub...
git push origin main
if %ERRORLEVEL% equ 0 (
    echo.
    echo =========================================================
    echo   [OK] Cambios subidos a GitHub exitosamente.
    echo =========================================================
) else (
    echo.
    echo =========================================================
    echo   [ERROR] No se pudo subir los cambios a GitHub.
    echo =========================================================
)

echo.
pause
