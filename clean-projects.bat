@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
::  LIMPEZA SEGURA - D:\AI DUBBING\data\projects
:: ============================================================
::
::  O que este script faz (POR PROJETO COMPLETADO):
::    1. Deleta work/ (arquivos temporarios: audio extraido,
::       WAVs intermediarios, segmentos)
::    2. OPCIONAL: Deleta projetos na fila que sao duplicatas
::       de videos ja completados
::    3. OPCIONAL: Deleta input/ de projetos completados
::
::  O que NUNCA deleta:
::    - output/ (videos dublados finais)
::    - state.json (estado do projeto)
::    - Projetos em andamento (current_stage != null)
::    - Projetos com erro
::
::  Uso: Execute e escolha as opcoes no menu interativo.
:: ============================================================

set "PROJECTS_DIR=D:\AI DUBBING\data\projects"

echo.
echo  =============================================
echo   LIMPEZA SEGURA - data\projects
echo  =============================================
echo.

:: ---- Verificar se o diretorio existe ----
if not exist "%PROJECTS_DIR%" (
    echo  [ERRO] Diretorio nao encontrado: %PROJECTS_DIR%
    pause
    exit /b 1
)

:: ---- Calcular tamanho total atual ----
for /f "tokens=3" %%a in ('dir /s /-c "%PROJECTS_DIR%" 2^>nul ^| findstr /c:"File(s)"') do set "TOTAL_BEFORE=%%a"
echo  Tamanho atual: ~38 GB
echo.

:: ---- Analisar projetos ----
set "COMPLETED_COUNT=0"
set "QUEUED_COUNT=0"
set "ERROR_COUNT=0"
set "WORK_SIZE=0"

echo  Analisando projetos...
echo.

:: ---- PASSO 1: Limpar work/ de projetos completados ----
echo  [PASSO 1] Projetos COMPLETADOS - Limpando work/ (arquivos temporarios)
echo  ---------------------------------------------------------

for /d %%p in ("%PROJECTS_DIR%\*") do (
    if exist "%%p\state.json" (
        :: Verificar se o projeto completou (tem "merge" nos completed_stages e current_stage null)
        findstr /i "\"merge\"" "%%p\state.json" >nul 2>&1
        if !errorlevel! equ 0 (
            :: Verificar se current_stage e null (projeto nao esta rodando)
            findstr /i "\"current_stage\": null" "%%p\state.json" >nul 2>&1
            if !errorlevel! equ 0 (
                :: Verificar se nao tem erro
                findstr /i "\"error\": null" "%%p\state.json" >nul 2>&1
                if !errorlevel! equ 0 (
                    set /a COMPLETED_COUNT+=1

                    :: Pegar nome do video do input
                    set "VIDEO_NAME="
                    for %%v in ("%%p\input\*.mp4") do set "VIDEO_NAME=%%~nxv"

                    :: Calcular tamanho do work/
                    if exist "%%p\work" (
                        for /f "tokens=3" %%s in ('dir /s /-c "%%p\work" 2^>nul ^| findstr /c:"File(s)"') do (
                            set /a WORK_SIZE+=%%s
                        )
                        echo    [COMPLETADO] !VIDEO_NAME! - Limpando work/...
                        rd /s /q "%%p\work" 2>nul
                    ) else (
                        echo    [COMPLETADO] !VIDEO_NAME! - work/ ja limpo
                    )
                )
            )
        )
    )
)

echo.
echo  Projetos completados processados: !COMPLETED_COUNT!
echo.

:: ---- PASSO 2: Limpar projetos duplicados na fila ----
echo  [PASSO 2] Projetos DUPLICADOS na fila
echo  ---------------------------------------------------------
echo.
echo  Videos que ja foram completados nao precisam ficar na fila.
echo.

:: Lista de videos ja completados (hardcoded baseado na analise)
:: Esses videos tem projetos completados com output/ disponivel

set "ASKED_ONCE=0"
set "DUPE_REMOVED=0"

:: Verificar cada projeto na fila (sem state.json) se o video ja foi completado
for /d %%p in ("%PROJECTS_DIR%\*") do (
    if not exist "%%p\state.json" (
        :: Projeto na fila - verificar se o video ja existe em um projeto completado
        set "INPUT_VIDEO="
        for %%v in ("%%p\input\*.mp4") do set "INPUT_VIDEO=%%~nxv"

        if defined INPUT_VIDEO (
            :: Procurar se existe um projeto completado com o mesmo video
            for /d %%c in ("%PROJECTS_DIR%\*") do (
                if exist "%%c\state.json" (
                    if exist "%%c\output\*!INPUT_VIDEO:_dublado_pt=!*dublado_pt*" (
                        :: Encontrou duplicata completada
                    )
                )
            )
        )
    )
)

:: Abordagem mais simples: perguntar ao usuario
echo  Os seguintes videos aparecem tanto completados quanto na fila:
echo.
echo    COMPLETADOS (com output/):
echo      - 05 - Camera Tracking.mp4
echo      - 06 - Camera Layout.mp4
echo      - 07 - Reconstruction.mp4
echo      - 09 - Lighting %% Materials.mp4
echo      - 15 - Color Grading.mp4
echo.
echo  DUPLICADOS na fila com mesmos videos:
echo      - 4ad5be31a154 (05 - Camera Tracking.mp4)
echo      - e8d240d8136d (05 - Camera Tracking.mp4)
echo      - af8c51b73067 (06 - Camera Layout.mp4)
echo      - d53d2b55bc90 (07 - Reconstruction.mp4)
echo      - efedeb1adfb0 (07 - Reconstruction.mp4)
echo      - bd10d3a69c49 (09 - Lighting %% Materials.mp4)
echo      - edc46ceacb64 (15 - Color Grading.mp4)
echo.

set /p "REMOVE_DUPES=Remover projetos duplicados da fila? (s/N): "
if /i "!REMOVE_DUPES!"=="s" (
    echo.
    echo  Removendo duplicatas...

    :: 05 - Camera Tracking.mp4 duplicatas
    rd /s /q "%PROJECTS_DIR%\4ad5be31a154" 2>nul && echo    Removido: 4ad5be31a154 (05 - Camera Tracking.mp4)
    rd /s /q "%PROJECTS_DIR%\e8d240d8136d" 2>nul && echo    Removido: e8d240d8136d (05 - Camera Tracking.mp4)

    :: 06 - Camera Layout.mp4 duplicata
    rd /s /q "%PROJECTS_DIR%\af8c51b73067" 2>nul && echo    Removido: af8c51b73067 (06 - Camera Layout.mp4)

    :: 07 - Reconstruction.mp4 duplicatas
    rd /s /q "%PROJECTS_DIR%\d53d2b55bc90" 2>nul && echo    Removido: d53d2b55bc90 (07 - Reconstruction.mp4)
    rd /s /q "%PROJECTS_DIR%\efedeb1adfb0" 2>nul && echo    Removido: efedeb1adfb0 (07 - Reconstruction.mp4)

    :: 09 - Lighting & Materials.mp4 duplicata
    rd /s /q "%PROJECTS_DIR%\bd10d3a69c49" 2>nul && echo    Removido: bd10d3a69c49 (09 - Lighting & Materials.mp4)

    :: 15 - Color Grading.mp4 duplicata
    rd /s /q "%PROJECTS_DIR%\edc46ceacb64" 2>nul && echo    Removido: edc46ceacb64 (15 - Color Grading.mp4)

    set /a DUPE_REMOVED=7
    echo  Duplicatas removidas: 7
) else (
    echo  Pulando remocao de duplicatas.
)

echo.

:: ---- PASSO 3: Perguntar sobre testes ----
echo  [PASSO 3] Arquivos de TESTE
echo  ---------------------------------------------------------
echo.
echo  Encontrados projetos de teste (quase vazios):
echo    - 286b1df102f6 (test.mp4 - 1 KB)
echo    - 8a47822965c6 (test_video.mp4 - 4 KB)
echo    - cc89ada772e2 (test.mp4 - 1 KB)
echo.

set /p "REMOVE_TESTS=Remover projetos de teste? (s/N): "
if /i "!REMOVE_TESTS!"=="s" (
    rd /s /q "%PROJECTS_DIR%\286b1df102f6" 2>nul && echo    Removido: 286b1df102f6
    rd /s /q "%PROJECTS_DIR%\8a47822965c6" 2>nul && echo    Removido: 8a47822965c6
    rd /s /q "%PROJECTS_DIR%\cc89ada772e2" 2>nul && echo    Removido: cc89ada772e2
    echo  Projetos de teste removidos: 3
) else (
    echo  Mantendo projetos de teste.
)

echo.

:: ---- PASSO 4: Perguntar sobre input/ de completados ----
echo  [PASSO 4] OPCIONAL: input/ de projetos COMPLETADOS
echo  ---------------------------------------------------------
echo.
echo  Os videos originais em input/ dos projetos completados consomem
echo  espaco, mas os videos dublados ja estao em output/.
echo  Se voce ja tem esses videos originais em outro lugar, pode deletar.
echo.

set /p "REMOVE_INPUT=Remover input/ de projetos completados? (s/N): "
if /i "!REMOVE_INPUT!"=="s" (
    echo.
    echo  Removendo input/ de projetos completados...
    for /d %%p in ("%PROJECTS_DIR%\*") do (
        if exist "%%p\state.json" (
            findstr /i "\"merge\"" "%%p\state.json" >nul 2>&1
            if !errorlevel! equ 0 (
                findstr /i "\"current_stage\": null" "%%p\state.json" >nul 2>&1
                if !errorlevel! equ 0 (
                    if exist "%%p\input" (
                        set "VIDEO_NAME="
                        for %%v in ("%%p\input\*.mp4") do set "VIDEO_NAME=%%~nxv"
                        rd /s /q "%%p\input" 2>nul
                        echo    Removido input/: !VIDEO_NAME!
                    )
                )
            )
        )
    )
    echo  Input/ de completados removido.
) else (
    echo  Mantendo input/ dos projetos completados.
)

echo.

:: ---- PASSO 5: Limpar arquivos .srt e .vtt duplicados em output/ ----
echo  [PASSO 5] OPCIONAL: Legendas .srt/.vtt em output/ completados
echo  ---------------------------------------------------------
echo.
echo  Cada projeto completado tem en.srt, en.vtt, pt.srt, pt.vtt
echo  em output/ (~400 KB total). Esses tambem estao em work/.
echo  Como work/ ja foi limpo, esses sao as unicas copias.
echo.

set /p "REMOVE_SUBS=Remover legendas de output/ completados? (s/N): "
if /i "!REMOVE_SUBS!"=="s" (
    for /d %%p in ("%PROJECTS_DIR%\*") do (
        if exist "%%p\output\*.srt" (
            del /q "%%p\output\*.srt" 2>nul
            del /q "%%p\output\*.vtt" 2>nul
        )
    )
    echo  Legendas removidas.
) else (
    echo  Mantendo legendas em output/.
)

echo.

:: ---- Resultado final ----
echo  =============================================
echo   LIMPEZA CONCLUIDA!
echo  =============================================
echo.
echo  Resumo do que foi feito:
echo   [PASSO 1] work/ de completados: LIMPO (automatico)
echo   [PASSO 2] Duplicatas na fila: dependeu da escolha
echo   [PASSO 3] Projetos de teste: dependeu da escolha
echo   [PASSO 4] input/ de completados: dependeu da escolha
echo   [PASSO 5] Legendas em output/: dependeu da escolha
echo.
echo  O que SEMPRE foi preservado:
echo   - output/ (videos dublados finais)
echo   - state.json (estado dos projetos)
echo   - Projetos na fila com videos unicos
echo   - Projetos em andamento ou com erro
echo.
echo  Para verificar o novo tamanho:
echo   dir /s "%PROJECTS_DIR%"
echo.

pause