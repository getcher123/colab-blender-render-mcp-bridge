# Windows: установка и запуск локального bridge

Этот маршрут предназначен для нового клона проекта. Для уже работающего MSI сначала прочитайте [state.md](../state.md): существующий проект находится в `C:\Users\Ivan\Projects\colab-blender-mcp`. Новый клон репозитория не переносит его `vendor`, `.venv`, очередь или живое соединение автоматически.

Скрипты рассчитаны на **Windows и PowerShell 5.1 или новее**. В среде подготовки репозитория Windows и PowerShell отсутствовали: команды проверены по коду и структуре, но установка и запуск этих двух `.ps1` на Windows здесь не выполнялись. Исторически рабочее подключение на MSI подтверждено отдельно в [state.md](../state.md).

## Зафиксированные компоненты

| Компонент | Версия или расположение |
|---|---|
| Официальный исходник | [googlecolab/colab-mcp](https://github.com/googlecolab/colab-mcp) |
| Git revision | `b9ab3899e0f1fa493390b1fd6d54aa2e464ecdf1` |
| Python проекта | `3.13.18` |
| uv | `0.13.7` |
| Пакет `colab-mcp` | `1.0.1` |
| Vendor | `vendor/colab-mcp` |
| Python bridge | `vendor/colab-mcp/.venv/Scripts/python.exe` |
| MCP server | `vendor/colab-mcp/.venv/Scripts/colab-mcp.exe` |
| Локальный patch | [colab-mcp-windows.patch](../patches/colab-mcp-windows.patch) |

Git и uv 0.13.7 должны быть заранее доступны в `PATH`. Установщики этого проекта не устанавливают и не обновляют их. Официальные инструкции: [Git for Windows](https://git-scm.com/downloads/win), [установка uv](https://docs.astral.sh/uv/getting-started/installation/). Проверка в PowerShell:

```powershell
git --version
uv --version
```

`setup.ps1` откажет при другой версии uv. Python 3.13.18 выбирает uv для проектной `.venv`; при необходимости uv может скачать управляемый им интерпретатор. Системный Python и его выбор по умолчанию не меняются. Существующий системный Python 3.10 на MSI не подходит для этой MCP-среды; upstream требует Python не ниже 3.13.

## 1. Новый клон

Выполните в PowerShell. Если каталог уже существует, используйте существующий клон после проверки его содержимого; не запускайте повторное клонирование поверх него.

```powershell
$BridgeProject = Join-Path $env:USERPROFILE 'Projects\colab-blender-render-mcp-bridge'
git clone https://github.com/getcher123/colab-blender-render-mcp-bridge.git $BridgeProject
if ($LASTEXITCODE -ne 0) { throw 'Не удалось клонировать проект.' }
Set-Location -LiteralPath $BridgeProject
.\scripts\windows\setup.ps1
if ($LASTEXITCODE -ne 0) { throw 'Установка остановилась; прочитайте причину выше.' }
```

Корень проекта вычисляется из расположения скрипта: `$PSScriptRoot/../..`. Скрипт можно вызывать из другого текущего каталога; при необходимости `-ProjectRoot` задаёт другой полный корень с `mcp_bridge.py`, `mcp_call.py` и `patches/colab-mcp-windows.patch`.

Установка выполняет следующие действия:

1. Проверяет Windows, Git, точную версию uv и обязательные файлы проекта.
2. Создаёт официальный vendor checkout без первоначального checkout, затем выбирает фиксированный revision в detached HEAD.
3. У существующего vendor проверяет собственный Git root, официальный origin, точный HEAD, отсутствие staged изменений и дополнительных untracked файлов. Изменения tracked файлов допустимы только в виде полного точного patch проекта.
4. Проверяет patch через `git apply --check` и применяет его один раз. Уже применённый точный patch проверяет через `git apply --reverse --check` без фактической отмены.
5. Выполняет из vendor `uv sync --frozen --no-dev --python 3.13.18`. `UV_PROJECT_ENVIRONMENT` временно указывает на проектную `.venv`, затем прежнее значение восстанавливается.
6. Проверяет Python, версию установленного пакета, наличие MCP SDK, server executable и неизменность tracked файлов сверх утверждённого patch.

Существующий vendor с другим origin или HEAD, дополнительные изменения, staged файлы либо несовместимая `.venv` вызывают отказ. Скрипт не выполняет `git reset`, `git clean`, удаление `.venv` или автоматическое переключение существующего vendor на другую ревизию. При отказе изучите конкретное состояние; отдельный свежий клон позволяет сохранить имеющуюся установку.

Установка не запускает bridge, MCP server, браузер, Colab runtime или GPU. PowerShell execution policy скрипты также не меняют; используйте принятую на вашем компьютере политику выполнения локальных скриптов.

## 2. Bridge в переднем плане

После успешной установки из корня клона:

```powershell
.\scripts\windows\start-bridge.ps1
```

Оставьте этот терминал открытым. Wrapper проверяет проектный Python и файлы, наличие старых запросов, состояние и свежесть heartbeat непосредственно перед запуском. Если bridge сообщает активное состояние с heartbeat не старше 20 секунд, второй процесс не запускается. Последнюю защиту от гонки обеспечивает OS lock в самом `mcp_bridge.py`; сохранённый PID не служит основанием для завершения процесса.

Если в `inbox` или `processing` остались JSON-запросы, wrapper остановится. Сначала прочитайте соответствующие запросы, результаты в `outbox` и фактические изменения notebook. Пример локального просмотра без запуска MCP:

```powershell
$BridgeProject = Join-Path $env:USERPROFILE 'Projects\colab-blender-render-mcp-bridge'
foreach ($QueuePart in @('inbox', 'processing', 'outbox')) {
    $QueuePath = Join-Path $BridgeProject ('bridge_state\' + $QueuePart)
    if (Test-Path -LiteralPath $QueuePath -PathType Container) {
        Get-ChildItem -LiteralPath $QueuePath -Filter '*.json' -File |
            Select-Object Name, Length, LastWriteTimeUtc
    }
}
```

После проверки и решения продолжить именно эту очередь:

```powershell
.\scripts\windows\start-bridge.ps1 -ResumeReviewedQueue
```

Оставшиеся `inbox` запросы могут выполниться при старте. Прерванные `processing` запросы bridge помечает `execution_uncertain: true` и не повторяет. Очередь читается по лексикографическому порядку имён JSON; при собственных `request_id` это не строгий порядок поступления. Ни wrapper, ни setup не очищают очередь.

Для управления существующим MSI можно вызвать новый wrapper, явно указав прежний корень. Сам по себе этот вызов ничего не переносит:

```powershell
.\scripts\windows\start-bridge.ps1 -ProjectRoot 'C:\Users\Ivan\Projects\colab-blender-mcp'
```

Перед этим сначала проверьте текущее соединение по [state.md](../state.md). Если прежний bridge жив, используйте его `mcp_call.py`; новый wrapper должен отказать при свежем активном heartbeat.

## 3. Проверка в другом терминале

Откройте второй PowerShell и задайте корень заново:

```powershell
$BridgeProject = Join-Path $env:USERPROFILE 'Projects\colab-blender-render-mcp-bridge'
Set-Location -LiteralPath $BridgeProject
$BridgePython = Join-Path $BridgeProject 'vendor\colab-mcp\.venv\Scripts\python.exe'
& $BridgePython .\mcp_call.py --status
& $BridgePython .\mcp_call.py __list_tools__ --tool-timeout 30 --wait-timeout 35
```

`--status` читает локальный JSON. Его exit code 0 не подтверждает живое подключение: проверьте `state`, `heartbeat_age_seconds` и фактические tools. `ready` означает готовность локального bridge принимать запросы, а не соединение с нужным notebook. Перед первоначальным Connect может быть доступен только bootstrap tool.

Для первого подключения вызовите bootstrap, запомнив уникальный ID. `--detach` нужен, чтобы локальный CLI не занимал терминал во время подтверждения в браузере:

```powershell
$BootstrapId = 'bootstrap_' + [Guid]::NewGuid().ToString('N')
& $BridgePython .\mcp_call.py open_colab_browser_connection --request-id $BootstrapId --tool-timeout 90 --wait-timeout 100 --detach
if ($LASTEXITCODE -ne 0) { throw 'Bootstrap не был поставлен в очередь.' }
```

В открытом обычном интерфейсе Colab завершите Connect для нужного notebook. Затем запросите результат **того же ID**, не отправляя bootstrap повторно:

```powershell
& $BridgePython .\mcp_call.py --result $BootstrapId --wait-timeout 100
$BootstrapFile = Join-Path $BridgeProject ('bridge_state\outbox\' + $BootstrapId + '.json')
if (Test-Path -LiteralPath $BootstrapFile -PathType Leaf) {
    $BootstrapResult = Get-Content -LiteralPath $BootstrapFile -Raw -Encoding UTF8 | ConvertFrom-Json
    [pscustomobject]@{
        WrapperOk = $BootstrapResult.ok
        McpError = $BootstrapResult.mcp_is_error
        BrowserConnected = $BootstrapResult.result.structuredContent.result
    }
}
& $BridgePython .\mcp_call.py __list_tools__ --tool-timeout 30 --wait-timeout 35
& $BridgePython .\mcp_call.py get_cells --tool-timeout 30 --wait-timeout 35
```

Реальный положительный bootstrap имеет `ok: true`, `mcp_is_error: false` и `result.structuredContent.result: true`. Верхнее `ok: true` при вложенном `false` подтверждает только успешный RPC; CLI в этом случае тоже возвращает 0. Если ожидание bootstrap истекло, соединение могло появиться позже: проверьте текущие tools и notebook перед новым действием.

После Connect ожидаются восемь tools: `open_colab_browser_connection`, `add_code_cell`, `add_text_cell`, `delete_cell`, `get_cells`, `move_cell`, `run_code_cell`, `update_cell`. Проверяйте не только число: свежий `get_cells` должен соответствовать выбранному notebook. Его полный результат хранится в указанном CLI `response_file`; при необходимости используйте `--result` с полученным ID и `--print-result` в локальном терминале. Не публикуйте raw bootstrap URL, токены, очередь и private логи.

Управление browser connection, локальным bridge и Colab runtime — отдельные состояния. Изменение или исполнение ячеек через MCP не доказывает сохранение notebook в Drive: выполните Save в UI и проверьте подтверждение. Отдельного Save tool среди восьми инструментов нет. Актуальный notebook и последние наблюдения перечислены в [state.md](../state.md); автоматический запуск GPU для восстановления контекста не требуется.

Для общей проверки идентичности и smoke в новом clone задайте переменные этого же корня:

```powershell
$ProjectRoot = $BridgeProject
$McpPython = $BridgePython
$McpCli = Join-Path $ProjectRoot 'mcp_call.py'
```

Теперь применимы **шаги 2–5** [connect-existing](connect-existing.md). Его шаг 1 с прежним путём MSI пропустите. В новом Drive-документе сверяйте содержимое своей копии и актуальные cell IDs; не запускайте исторический smoke ID без проверки. Перед smoke на отключённой среде проверьте настройку CPU, чтобы сохранённый GPU accelerator не выделил GPU.

## 4. Таймауты и остановка

| Ситуация `mcp_call.py` | Exit code | Что означает |
|---|---:|---|
| `--status`, файл существует | 0 | JSON прочитан; состояние может быть stale или stopped |
| `--status`, файла нет | 1 | Bridge для этого корня ещё не оставил status |
| `--detach`, request принят | 0 | Только постановка в очередь |
| Полученный wrapper `ok: true` | 0 | Нужно дополнительно проверить семантику результата tool |
| Полученный wrapper `ok: false` | 1 | Ошибка либо неопределённое выполнение; изучить результат |
| Некорректные аргументы, ID занят, bridge отсутствует или heartbeat stale | 2 | Новый request не принят |
| Истекло `--wait-timeout` | 3 | Клиент перестал ждать; queued request не отменён |

Максимальный `--tool-timeout` — 600 секунд; стандартный `--wait-timeout` — 660. Оба не увеличивают внутреннее 60-секундное ожидание browser bootstrap upstream. Patch с `asyncio.shield` защищает startup task при истечении этого ожидания; он не делает таймауты отменой удалённых действий. В clean notebook installer и Blender subprocess имеют собственный предел 1200 секунд, поэтому истечение MCP-таймаута не доказывает остановку ячейки. Прочитайте notebook и имеющийся `outbox`, затем получите итог по исходному ID.

Для штатной остановки поставьте отдельный уникальный запрос:

```powershell
& $BridgePython .\mcp_call.py __shutdown__ --tool-timeout 30 --wait-timeout 660
```

`__shutdown__` обрабатывается общей последовательной очередью. Он не прерывает выполняющийся RPC, не гарантирует выполнение всех остальных queued запросов и не отключает Colab runtime. Запросы, оставшиеся в `inbox`, сохраняются для следующего старта. Не завершайте процессы по историческому PID или порту из документации. При прерывании bridge или таймауте считайте возможные remote effects неопределёнными, пока они не проверены в notebook.

Коды самого `mcp_bridge.py`: 0 — штатный queued shutdown, 1 — ошибка работы, 2 — server executable отсутствует либо очередь уже занята другим bridge, 130 — обработанный `KeyboardInterrupt`. Необработанные ошибки файловой системы могут завершаться стандартной ошибкой Python. Wrapper возвращает код запущенного bridge; собственный отказ preflight возвращает 1.
