# Продолжить на настроенном MSI

Маршрут для уже существующего `C:\Users\Ivan\Projects\colab-blender-mcp`. Новый GitHub clone может храниться рядом, но у каждого корня собственные vendor, очередь и процесс. Для новой установки используйте [setup-windows](setup-windows.md).

Если вы пришли из setup нового clone только для общей проверки, сохраните его `$ProjectRoot`, `$McpPython` и `$McpCli`, как указано в setup. **Пропустите шаг 1 с путём MSI и начните с шага 2.** Идентичность сравнивайте со своим явно выбранным Drive-документом; ожидаемые ID старого working notebook применимы только к нему.

Команды ниже выполняются на MSI через разрешённый локальный терминал/Remote Desktop Commander. Colab открыт в браузере той же машины: loopback сервера облачного агента и loopback MSI — разные адреса. Browser-действия выполняет один ведущий агент через подключённый Browser с его актуальными инструкциями.

## 1. Прочитать локальный статус

```powershell
$ProjectRoot = 'C:\Users\Ivan\Projects\colab-blender-mcp'
$McpPython = Join-Path $ProjectRoot 'vendor\colab-mcp\.venv\Scripts\python.exe'
$McpCli = Join-Path $ProjectRoot 'mcp_call.py'
if (-not (Test-Path -LiteralPath $McpPython -PathType Leaf)) {
    throw 'Python существующего проекта недоступен. Проверьте машину и project root.'
}
& $McpPython $McpCli --project-dir $ProjectRoot --status
```

Проверить `project_dir`, `server_command`, `pid`, `state`, `heartbeat_age_seconds`, `active_request`. Heartbeat должен быть актуальным; submit отказывает при возрасте больше 20 секунд или состоянии вне `ready`/`executing`. Exit 0 у `--status` говорит только о чтении файла. При расхождении системных часов не интерпретировать отрицательный возраст как доказательство здоровья.

При необходимости сверить именно наблюдаемый PID с процессом, не выводя полный command line с потенциальными приватными параметрами:

```powershell
$StatusPath = Join-Path $ProjectRoot 'bridge_state\status.json'
$BridgeStatus = Get-Content -LiteralPath $StatusPath -Raw -Encoding UTF8 | ConvertFrom-Json
$BridgeProcess = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + [int]$BridgeStatus.pid)
$BridgeProcess | Select-Object ProcessId, ParentProcessId, ExecutablePath, CreationDate
foreach ($QueuePart in @('inbox', 'processing', 'outbox')) {
    $QueuePath = Join-Path $ProjectRoot ('bridge_state\' + $QueuePart)
    if (Test-Path -LiteralPath $QueuePath -PathType Container) {
        Get-ChildItem -LiteralPath $QueuePath -Filter '*.json' -File |
            Select-Object Name, Length, LastWriteTimeUtc
    }
}
```

Не завершать процесс по старому PID из `state.md`. Если есть активный request, разобраться с ним до новой изменяющей команды. Подробности timeout и очереди — в [architecture](architecture.md).

## 2. Получить текущие tools

```powershell
& $McpPython $McpCli --project-dir $ProjectRoot __list_tools__ --tool-timeout 30 --wait-timeout 35
```

Ожидается точный набор: `open_colab_browser_connection`, `add_code_cell`, `add_text_cell`, `delete_cell`, `get_cells`, `move_cell`, `run_code_cell`, `update_cell`. Только bootstrap означает, что notebook frontend не подключён. При stale/error, timeout или отсутствующих tools перейти в [recovery](recover-connection.md).

Схемы сохраняются в `bridge_state/tools.json`. Это живой источник для формы аргументов; сохранённый [tools response](../evidence/recovery/restore_20261109_tools_final.json) нужен для сравнения checkpoint.

## 3. Проверить идентичность документа

В Browser проверить URL без auth fragment:

https://colab.research.google.com/drive/1vioZDVMV7P_eCazGrLWQ0C17mIFJJpqS

Затем прочитать ячейки. Пример использует UTF-8 JSON-файл, чтобы не зависеть от передачи кавычек в Windows PowerShell 5.1:

```powershell
$ArgumentDirectory = Join-Path $ProjectRoot 'bridge_state\arguments'
New-Item -ItemType Directory -Path $ArgumentDirectory -Force | Out-Null
$IdentityArguments = Join-Path $ArgumentDirectory ('identity_' + [Guid]::NewGuid().ToString('N') + '.json')
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($IdentityArguments, '{"includeOutputs":false}', $Utf8NoBom)
$IdentityRequest = & $McpPython $McpCli --project-dir $ProjectRoot get_cells --args-file $IdentityArguments --tool-timeout 30 --detach | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $IdentityRequest.submitted) { throw 'get_cells не поставлен в очередь.' }
& $McpPython $McpCli --project-dir $ProjectRoot --result $IdentityRequest.id --wait-timeout 35 --print-result
```

`--detach` печатает один JSON и позволяет надёжно захватить ID. Обычный синхронный submit печатает сначала JSON отправки, затем JSON результата: весь этот stdout нельзя считать одним объектом для `ConvertFrom-Json`.

Сверить вводную и содержимое с [working export](../notebooks/Blender_Colab_A100_Working_2026-11-09.ipynb). Последний checkpoint содержал 15 ячеек, intro `ZGa228Vinvws`, smoke `5a8JvwHlopZw`. После разрешённых пользователем изменений количество/ID могут отличаться: выяснить причину расхождения. `get_cells` сам по себе не возвращает удостоверенный Drive URL — нужны и Browser URL, и содержимое. Пустой scratchpad не является рабочим документом.

## 4. Доказать исполнение, если этого требует задача

Для read-only знакомства с контекстом исполнение не обязательно. Для подтверждения полного восстановления использовать короткий [smoke source](../scripts/colab/recovery_smoke.py): он читает Python/GPU/наличие Blender и печатает `COLAB_MCP_RECOVERY_OK`, без установки и рендера.

В существующей рабочей вкладке сначала прочитать и сверить исходник smoke. Если ячейка сохранила ID `5a8JvwHlopZw` и её код действительно тот же, можно запустить её:

```powershell
$SmokeArguments = Join-Path $ArgumentDirectory ('smoke_' + [Guid]::NewGuid().ToString('N') + '.json')
[System.IO.File]::WriteAllText($SmokeArguments, '{"cellId":"5a8JvwHlopZw"}', $Utf8NoBom)
$SmokeRequest = & $McpPython $McpCli --project-dir $ProjectRoot run_code_cell --args-file $SmokeArguments --tool-timeout 120 --detach | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $SmokeRequest.submitted) { throw 'Smoke не поставлен в очередь.' }
& $McpPython $McpCli --project-dir $ProjectRoot --result $SmokeRequest.id --wait-timeout 130 --print-result
```

Если такого ID/исходника нет, этот пример не выполнять. По текущей схеме `add_code_cell` создать отдельную smoke-ячейку в правильном документе и использовать фактически возвращённый новый ID. Не подставлять ID другой ячейки или исторического render.

До запуска на отключённом runtime проверить настройки notebook: для recovery должна быть выбрана стандартная CPU-среда. Исполнение следует выбранному accelerator, поэтому сохранённая настройка GPU может выделить GPU даже для короткого smoke. Уже работающую среду с данными не переключать ради smoke. Проверить свежую UTC-метку, ожидаемый marker, отсутствие Python error и факт `render_executed: false`. `gpu_probe: null` и `blender_present: false` допустимы и совпадают с сохранённым recovery checkpoint.

## 5. Завершить проверку

После изменения/исполнения ячеек явно выполнить **Файл → Сохранить** в Colab и дождаться подтверждения сохранения. Восемь MCP tools не включают отдельную команду сохранения Drive.

Обновить `state.md` новым временем и фактами, сохранив различие между CPU smoke и историческим A100. Для новой GPU-задачи перейти в [render-and-export](render-and-export.md). Если проверки не проходят — [recover-connection](recover-connection.md). После завершения работы — [handoff](handoff.md).
