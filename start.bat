@echo off
setlocal enabledelayedexpansion
title LuminaDub AI - Iniciando...
echo.
echo  +======================================+
echo  ^|     LuminaDub AI - Limpeza e Inicio  ^|
echo  +======================================+
echo.

echo [1/6] Limpando cache Python...
if exist "__pycache__" rmdir /s /q "__pycache__" 2>nul
if exist "stages\__pycache__" rmdir /s /q "stages\__pycache__" 2>nul
if exist "models\__pycache__" rmdir /s /q "models\__pycache__" 2>nul
if exist "ui\__pycache__" rmdir /s /q "ui\__pycache__" 2>nul
echo      Cache removido.

echo.
echo [2/6] Limpando projetos antigos...
if not exist "data\projects" (
    echo      Nenhum projeto encontrado.
) else (
    for /d %%p in ("data\projects\*") do (
        if exist "%%p\output" (
            echo      Limpando %%p\output...
            rmdir /s /q "%%p\output" 2>nul
        )
        if exist "%%p\work" (
            echo      Limpando %%p\work...
            rmdir /s /q "%%p\work" 2>nul
        )
        if exist "%%p\state.json" (
            del /q "%%p\state.json" 2>nul
        )
    )
    echo      Outputs antigos removidos.
)

echo.
echo [3/6] Verificando dependencias...
pip install waitress >nul 2>&1
echo      OK.

echo.
echo [4/6] Matando processos nas portas 5000 e 7860...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    echo      Matando PID %%a na porta 5000...
    taskkill /f /pid %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":7860 " ^| findstr "LISTENING"') do (
    echo      Matando PID %%a na porta 7860...
    taskkill /f /pid %%a >nul 2>&1
)
echo      Portas liberadas.

echo.
echo [5/6] Verificando Ollama...
where ollama >nul 2>&1
if !errorlevel! equ 0 (
    echo      Ollama encontrado.
) else (
    echo      AVISO: Ollama nao encontrado. Traducao IA nao estara disponivel.
    echo      Instale em: https://ollama.com
)

echo.
echo [6/6] Iniciando LuminaDub AI...
echo      Servidor: http://localhost:5000
echo.
python server.py
pause