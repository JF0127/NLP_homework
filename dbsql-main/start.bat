@echo off
:: must input a port
set PORT=%1
if "%PORT%"=="" (
    echo please input a port
    exit /b
) else (
    echo ###### PORT=%PORT% ###### >> server.log
)

:: try to kill the process which occupies the port
call stop.bat %PORT%

:: activate the environment and set variables
call D:\anaconda3\Scripts\activate.bat D:\anaconda3\envs\dbsql
if %errorlevel% neq 0 (
    echo cannot activate conda environment dbsql
    exit /b
)

set PYTHONPATH=.

:: start service
start /b python -m uvicorn dbsql.server.main:app --host 0.0.0.0 --port %PORT% >> server.log 2>&1
if %errorlevel% neq 0 (
    echo connot start uvicorn
    exit /b 1
)
echo service stop
