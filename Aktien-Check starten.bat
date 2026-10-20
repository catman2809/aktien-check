@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul && (set PY=python) || (set PY=py)
echo Pruefe Abhaengigkeiten ...
%PY% -m pip install --quiet --disable-pip-version-check -r requirements.txt
%PY% aktien_check.py
pause
