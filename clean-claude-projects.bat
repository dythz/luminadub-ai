@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
:: Script de Limpeza Segura do .claude/projects
:: ============================================================
:: O que este script faz:
::   1. Remove projetos de paths que nao existem mais
::   2. Remove transricoes de sessoes antigas (.jsonl) completadas
::   3. Remove caches de subagentes de sessoes completadas
::   4. PRESERVA: memoria persistente (memory/), sessao ativa, e projeto atual
::
:: O que e SEGURO deletar:
::   - .jsonl = transricoes de conversas (nao afeta codigo nem memoria)
::   - subagents/ = cache temporario de sub-agentes
::   - tool-results/ = resultados de ferramentas em cache
::
:: O que NUNCA deletar:
::   - memory/ = memoria persistente do Claude entre sessoes
::   - Sessao ativa (usada agora)
:: ============================================================

echo.
echo ============================================
:::  LIMPEZA SEGURA - .claude/projects
::: ============================================
echo.

set "CLAUDE_DIR=%USERPROFILE%\.claude"
set "PROJECTS_DIR=%CLAUDE_DIR%\projects"
set "FREED=0"

:: ---- Verificar se o diretorio existe ----
if not exist "%PROJECTS_DIR%" (
    echo [ERRO] Diretorio %PROJECTS_DIR% nao encontrado.
    pause
    exit /b 1
)

:: ---- Detectar sessao ativa ----
set "ACTIVE_SESSION="
for %%f in ("%CLAUDE_DIR%\sessions\*.json") do (
    for /f "tokens=2 delims=:," %%a in ('findstr /i "sessionId" "%%f"') do (
        set "line=%%a"
        set "line=!line:"=!"
        set "line=!line: =!"
        set "ACTIVE_SESSION=!line!"
    )
)
if defined ACTIVE_SESSION (
    echo [INFO] Sessao ativa detectada: !ACTIVE_SESSION!
) else (
    echo [AVISO] Nenhuma sessao ativa detectada. Tenha cuidado.
)
echo.

:: ---- Calcular tamanho antes ----
for /f "tokens=1" %%a in ('dir /s "%PROJECTS_DIR%" 2^>nul ^| findstr /c:"File(s)"') do set "SIZE_BEFORE=%%a"
echo [INFO] Tamanho atual do projects: %SIZE_BEFORE% bytes
echo.

:: ============================================================
:: PASSO 1: Remover projetos de paths que nao existem mais
:: ============================================================
echo [PASSO 1] Verificando projetos de paths inexistentes...

:: Projetos com paths que claramente nao existem mais
set "REMOVED_PROJECTS=0"

:: C:\ (raiz do C) - nao e um projeto valido
if exist "%PROJECTS_DIR%\C--" (
    echo   - Removendo: C-- (path: C:\)
    rd /s /q "%PROJECTS_DIR%\C--" 2>nul
    set /a REMOVED_PROJECTS+=1
)

:: C:\Windows - nao e um projeto, foi acidental
if exist "%PROJECTS_DIR%\C--Windows" (
    echo   - Removendo: C--Windows (path: C:\Windows)
    rd /s /q "%PROJECTS_DIR%\C--Windows" 2>nul
    set /a REMOVED_PROJECTS+=1
)

:: C:\Windows\System32 - nao e um projeto, foi acidental
if exist "%PROJECTS_DIR%\C--WINDOWS-system32" (
    echo   - Removendo: C--WINDOWS-system32 (path: C:\Windows\System32)
    rd /s /q "%PROJECTS_DIR%\C--WINDOWS-system32" 2>nul
    set /a REMOVED_PROJECTS+=1
)

:: Downloads - paths antigos de downloads (projetos ja movidos)
if exist "%PROJECTS_DIR%\C--Users-dudu5-Downloads-CLAUDE" (
    echo   - Removendo: C--Users-dudu5-Downloads-CLAUDE
    rd /s /q "%PROJECTS_DIR%\C--Users-dudu5-Downloads-CLAUDE" 2>nul
    set /a REMOVED_PROJECTS+=1
)

if exist "%PROJECTS_DIR%\C--Users-dudu5-Downloads-VOX-AI-1-VOX-AI" (
    echo   - Removendo: C--Users-dudu5-Downloads-VOX-AI-1-VOX-AI
    rd /s /q "%PROJECTS_DIR%\C--Users-dudu5-Downloads-VOX-AI-1-VOX-AI" 2>nul
    set /a REMOVED_PROJECTS+=1
)

if exist "%PROJECTS_DIR%\C--Users-dudu5-Downloads-ALEXA" (
    echo   - Removendo: C--Users-dudu5-Downloads-ALEXA (projeto antigo)
    rd /s /q "%PROJECTS_DIR%\C--Users-dudu5-Downloads-ALEXA" 2>nul
    set /a REMOVED_PROJECTS+=1
)

if exist "%PROJECTS_DIR%\C--Users-dudu5-Downloads-AI-DUBBING" (
    echo   - Removendo: C--Users-dudu5-Downloads-AI-DUBBING (path antigo)
    rd /s /q "%PROJECTS_DIR%\C--Users-dudu5-Downloads-AI-DUBBING" 2>nul
    set /a REMOVED_PROJECTS+=1
)

if exist "%PROJECTS_DIR%\C--Users-dudu5-Downloads-AI-DUBBING-AI-DUBBING" (
    echo   - Removendo: C--Users-dudu5-Downloads-AI-DUBBING-AI-DUBBING (path antigo)
    rd /s /q "%PROJECTS_DIR%\C--Users-dudu5-Downloads-AI-DUBBING-AI-DUBBING" 2>nul
    set /a REMOVED_PROJECTS+=1
)

:: D:\video-dubber - projeto antigo diferente
if exist "%PROJECTS_DIR%\D--video-dubber" (
    echo   - Removendo: D--video-dubber (projeto diferente/antigo)
    rd /s /q "%PROJECTS_DIR%\D--video-dubber" 2>nul
    set /a REMOVED_PROJECTS+=1
)

:: D:\AI DUBBING\AI DUBBING - subdiretorio antigo (projeto foi movido)
if exist "%PROJECTS_DIR%\D--AI-DUBBING-AI-DUBBING" (
    echo   - Removendo: D--AI-DUBBING-AI-DUBBING (subpath antigo)
    rd /s /q "%PROJECTS_DIR%\D--AI-DUBBING-AI-DUBBING" 2>nul
    set /a REMOVED_PROJECTS+=1
)

echo   Projetos obsoletos removidos: !REMOVED_PROJECTS!
echo.

:: ============================================================
:: PASSO 2: Limpar sessoes completadas (exceto a ativa)
:: ============================================================
echo [PASSO 2] Limpando sessoes completadas...

set "CLEANED_SESSIONS=0"

:: Percorrer todos os projetos restantes
for /d %%p in ("%PROJECTS_DIR%\*") do (
    set "PROJ_DIR=%%p"
    set "PROJ_NAME=%%~nxp"

    :: PRESERVAR diretorio memory/ - NUNCA deletar
    :: (ja tratado abaixo - nao tocamos em memory/)

    :: Limpar .jsonl de sessoes completadas
    for %%s in ("!PROJ_DIR!\*.jsonl") do (
        set "SESSION_FILE=%%~nxs"
        set "SESSION_ID=!SESSION_FILE:.jsonl=!"

        :: Pular a sessao ativa
        if defined ACTIVE_SESSION (
            if /i "!SESSION_ID!"=="!ACTIVE_SESSION!" (
                echo   [PRESERVADO] Sessao ativa: !SESSION_ID!
            ) else (
                del /q "%%s" 2>nul
                set /a CLEANED_SESSIONS+=1
            )
        ) else (
            :: Sem sessao ativa detectada - deletar todas
            del /q "%%s" 2>nul
            set /a CLEANED_SESSIONS+=1
        )
    )

    :: Limpar subdiretorios de sessoes completadas (subagents/, tool-results/)
    for /d %%s in ("!PROJ_DIR!\*") do (
        set "SUBDIR_NAME=%%~nxs"
        :: PRESERVAR diretorio memory/
        if /i not "!SUBDIR_NAME!"=="memory" (
            :: Verificar se e um UUID (sessao)
            echo !SUBDIR_NAME! | findstr /r "^[0-9a-f]*-[0-9a-f]*-" >nul 2>&1
            if !errorlevel! equ 0 (
                :: E um diretorio de sessao - limpar subagents e tool-results dentro dele
                if exist "%%s\subagents" (
                    rd /s /q "%%s\subagents" 2>nul
                )
                if exist "%%s\tool-results" (
                    rd /s /q "%%s\tool-results" 2>nul
                )
            )
        )
    )
)

echo   Sessoes antigas limpas: !CLEANED_SESSIONS!
echo.

:: ============================================================
:: PASSO 3: Limpar outros caches do .claude
:: ============================================================
echo [PASSO 3] Limpando caches adicionais...

:: Limpar paste-cache (cache temporario de clipboard)
if exist "%CLAUDE_DIR%\paste-cache" (
    echo   - Limpando paste-cache
    del /q "%CLAUDE_DIR%\paste-cache\*" 2>nul
)

:: Limpar shell-snapshots (snapshots de estado do shell)
if exist "%CLAUDE_DIR%\shell-snapshots" (
    echo   - Limpando shell-snapshots
    del /q "%CLAUDE_DIR%\shell-snapshots\*" 2>nul
)

:: Limpar backups antigos
if exist "%CLAUDE_DIR%\backups" (
    echo   - Limpando backups
    del /q "%CLAUDE_DIR%\backups\*" 2>nul
)

:: Limpar downloads antigos
if exist "%CLAUDE_DIR%\downloads" (
    echo   - Limpando downloads
    del /q "%CLAUDE_DIR%\downloads\*" 2>nul
)

:: Limpar cache
if exist "%CLAUDE_DIR%\cache" (
    echo   - Limpando cache
    del /q "%CLAUDE_DIR%\cache\*" 2>nul
)

echo.

:: ============================================================
:: PASSO 4: Verificar se sobraram diretorios vazios de projetos e limpar
:: ============================================================
echo [PASSO 4] Removendo diretorios vazios restantes...

set "EMPTY_REMOVED=0"
for /d %%p in ("%PROJECTS_DIR%\*") do (
    :: Verificar se o diretorio esta vazio (apenas memory/ pode estar presente)
    set "HAS_FILES=0"
    for /f %%a in ('dir /b "%%p" 2^>nul ^| find /c /v ""') do set "HAS_FILES=%%a"

    :: Se so tem memory/, verificar se memory/ tem conteudo
    set "HAS_OTHER=0"
    for %%f in ("%%p\*") do set "HAS_OTHER=1"

    :: Verificar se tem algo alem de memory/
    dir /b "%%p" 2>nul | findstr /v /i "^memory$" >nul 2>&1
    if !errorlevel! neq 0 (
        :: So tem memory/ ou esta vazio - verificar se memory tem conteudo
        if not exist "%%p\memory" (
            rd /q "%%p" 2>nul
            set /a EMPTY_REMOVED+=1
        )
    )
)
echo   Diretorios vazios removidos: !EMPTY_REMOVED!
echo.

:: ---- Resultado final ----
echo ============================================
echo   LIMPEZA CONCLUIDA!
echo ============================================
echo.
echo   Resumo:
echo   - Projetos obsoletos removidos: !REMOVED_PROJECTS!
echo   - Sessoes antigas limpas: !CLEANED_SESSIONS!
echo   - Diretorios vazios removidos: !EMPTY_REMOVED!
echo.
echo   Preservado:
echo   - Sessao ativa: !ACTIVE_SESSION!
echo   - Memoria persistente: memory/ (em todos os projetos)
echo   - Configuracoes: settings.json
echo.
echo Para verificar o novo tamanho, execute:
echo   dir /s "%PROJECTS_DIR%"
echo.

pause