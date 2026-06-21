@echo off
cd /d "%~dp0"

call venv\Scripts\activate.bat

start /b cmd /c "ping -n 3 127.0.0.1 >nul && start http://localhost:5000"

echo.
echo  =========================================
echo   Stock Monitor starting...
echo   http://localhost:5000
echo   Close this window to stop the server.
echo  =========================================
echo.

python app.py

pause
