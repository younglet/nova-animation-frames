@echo off
title NAF Web Tools Server
cd /d "%~dp0"
echo.
echo  ═══════════════════════════════════════════
echo   NAF Web Tools Server
echo   Root:  %CD%
echo   Page:  http://localhost:6789/tools/web/demo.html
echo   API:   http://localhost:6789/api/examples
echo  ═══════════════════════════════════════════
echo.
echo  [INFO] Starting server on port 6789...
echo  [INFO] Press Ctrl+C to stop.
echo.

python tools\web\server.py 6789 --open

pause
