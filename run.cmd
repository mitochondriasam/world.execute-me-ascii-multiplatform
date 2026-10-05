@echo off
setlocal
where uv >nul 2>nul
if errorlevel 1 (
    echo uv was not found. Install uv, then run uv sync in this project. 1>&2
    exit /b 1
)
uv run --project "%~dp0." --locked python -B "%~dp0player.py" %*
exit /b %errorlevel%
