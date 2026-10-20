@echo off
cd /d "%~dp0"
where python >nul 2>nul && (set PY=python) || (set PY=py)
if /i "%1"=="online" (set RUN_ONLINE_TESTS=1& echo Schnelltests + Online-Tests mit echten Daten ...) else (echo Schnelltests ohne Internet ...  ^(mit Online-Tests: run_tests.bat online^))
%PY% -m unittest discover -s tests -v
set RC=%ERRORLEVEL%
if %RC%==0 (echo. & echo ALLE TESTS BESTANDEN) else (echo. & echo ACHTUNG: TESTS FEHLGESCHLAGEN)
if /i not "%2"=="nopause" pause
exit /b %RC%
