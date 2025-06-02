@echo off

:: input the port
set PORT=%1
if "%PORT%"=="" (
    echo please input the port
    exit /b
)

:: find the process using port
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%"') do (
    set PID=%%a
    goto :KILL_PROCESS
)

echo port is not used
exit /b

:KILL_PROCESS
echo kill PID=%PID%
taskkill /F /PID %PID%
