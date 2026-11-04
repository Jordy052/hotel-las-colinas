@echo off
setlocal
cd /d "%~dp0"
python -m hotel_admin.web_api
if errorlevel 1 (
  echo.
  echo No se pudo iniciar la API. Revisa Python, las dependencias y el archivo .env de esta carpeta.
  pause
)
