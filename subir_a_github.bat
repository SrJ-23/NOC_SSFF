@echo off
setlocal enabledelayedexpansion

:: Asegurar que Git (MinGit o Git estándar) esté en el PATH
if exist "%LOCALAPPDATA%\MinGit\cmd" (
    set "PATH=%LOCALAPPDATA%\MinGit\cmd;%PATH%"
)
if exist "C:\Program Files\Git\cmd" (
    set "PATH=C:\Program Files\Git\cmd;%PATH%"
)

title Subir cambios a GitHub - NOC Servicios Fijos
color 0b

echo =========================================================
echo         SUBIR ACTUALIZACIONES A GITHUB (NOC)
echo =========================================================
echo.

:: Verificar si git está disponible
where git >nul 2>&1
if errorlevel 1 (
    color 0c
    echo [ERROR] No se encontro Git en el sistema.
    echo Por favor asegurese de tener Git o MinGit instalado.
    echo.
    pause
    exit /b 1
)

echo [1/3] Preparando y agregando archivos modificados...
git add -A

:: Verificar si hay cambios pendientes para commitear
git diff --staged --quiet
if errorlevel 1 (
    echo.
    echo Se detectaron cambios pendientes por guardar.
    set /p "commit_msg=Ingrese descripcion del cambio (Enter para mensaje automatico): "
    if "!commit_msg!"=="" (
        set "commit_msg=Actualizacion automatica NOC %DATE% %TIME%"
    )
    echo.
    echo [2/3] Creando commit: "!commit_msg!"
    git commit -m "!commit_msg!"
) else (
    echo.
    echo [2/3] No hay archivos nuevos por commitear (arbol limpio).
)

echo.
echo [3/3] Subiendo cambios a GitHub (rama main)...
echo.
git push origin main

if errorlevel 1 (
    echo.
    color 0c
    echo =========================================================
    echo   [ERROR] No se pudo subir los cambios a GitHub.
    echo   Revise su conexion o permisos del repositorio.
    echo =========================================================
) else (
    echo.
    color 0a
    echo =========================================================
    echo   [OK] !Cambios subidos a GitHub exitosamente!
    echo =========================================================
)

echo.
pause
