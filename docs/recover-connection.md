# Восстановление соединения

Сначала прочитать [state](../state.md) и пройти read-only часть [connect-existing](connect-existing.md). Выяснить, какой слой недоступен: процесс bridge, stdio MCP, frontend notebook, вычислительная среда или сохранение Drive. [Troubleshooting](troubleshooting.md) связывает наблюдаемые симптомы с действиями.

## A. Bridge жив, но tools notebook отсутствуют

Если heartbeat свежий, очередь понятна и доступен только `open_colab_browser_connection`, выполнить один bootstrap. Сначала выбрать **один** корень. Для существующего MSI:

```powershell
$ProjectRoot = 'C:\Users\Ivan\Projects\colab-blender-mcp'
```

Для нового clone, созданного по setup route:

```powershell
$ProjectRoot = Join-Path $env:USERPROFILE 'Projects\colab-blender-render-mcp-bridge'
```

Дальнейшие команды общие для выбранного корня:

```powershell
$McpPython = Join-Path $ProjectRoot 'vendor\colab-mcp\.venv\Scripts\python.exe'
$McpCli = Join-Path $ProjectRoot 'mcp_call.py'
$Bootstrap = & $McpPython $McpCli --project-dir $ProjectRoot open_colab_browser_connection --tool-timeout 90 --detach | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $Bootstrap.submitted) { throw 'Bootstrap не принят; сначала исправьте локальный bridge.' }
```

Для нового clone использовать его `$ProjectRoot`, а не путь MSI. Upstream ждёт frontend до 60 с; patch защищает startup task от отмены этим ожиданием. Если UI-подключение произойдёт позже, сначала проверять tools и существующий request, а не отправлять bootstrap заново.

## B. Привязать правильный notebook через браузер

1. Восстановить штатный контекст подключённого Browser. Для автоматизации прочитать его действующую skill-инструкцию. После потери контекста не предполагать, что прошлые tab ID всё ещё действуют.
2. Найти вкладку, открытую bootstrap. Upstream может создать scratchpad `notebooks/empty.ipynb`; он иногда виден только в пользовательском списке `browser.user.openTabs`, а не среди уже управляемых tabs.
3. Использовать **актуальный fragment этого bootstrap** только локально для текущего bridge. Он содержит данные доступа и порт. Не печатать/коммитить его и не брать значение из старого лога.
4. Открыть нужный рабочий Drive notebook с актуальным fragment через разрешённый Browser. Если scratchpad уже занял единственное WebSocket-соединение, сначала штатно отключить его MCP connection, затем подключить целевую вкладку. Не закрывать рабочие документы до сохранения.
5. Подтвердить штатный Connect и необходимые browser prompts. Loopback MCP server и этот браузер должны быть на одной машине. Не менять глобальные browser security flags и не обходить отказ доступа через CDP, registry или profile-файлы.
6. Проверить текущие 8 tools и `get_cells`, затем сопоставить URL и содержимое. Результат bootstrap со значением `true` не удостоверяет Drive ID.

Целевой документ recovery — [лёгкий working notebook](https://colab.research.google.com/drive/1vioZDVMV7P_eCazGrLWQ0C17mIFJJpqS). Для новой самостоятельной сессии можно открыть копию чистого шаблона в своём Drive и зафиксировать её новый URL; это новая копия, а не восстановленная старая VM.

Прочитать итог существующего bootstrap:

```powershell
& $McpPython $McpCli --project-dir $ProjectRoot --result $Bootstrap.id --wait-timeout 100 --print-result
& $McpPython $McpCli --project-dir $ProjectRoot __list_tools__ --tool-timeout 30 --wait-timeout 35
```

Нужны `ok: true`, отсутствие `mcp_is_error`/ошибки и семантический `result.structuredContent.result: true` для успешного bootstrap. Верхний `ok: true` с вложенным `false` — лишь завершённый RPC. Если boolean остался `false`, но frontend подключился позже, текущие tools/identity определяют фактическое состояние.

## C. Bridge stale, остановлен или завершился с ошибкой

Проверить свежесть status, текущий executable/PID и все очереди. `ready` со старым heartbeat не означает живой процесс. `executing` с текущим heartbeat может означать длительный RPC; не перезапускать его ради ускорения.

Перед стартом существующей очереди установить:

- какие файлы находятся в `inbox` и могут выполниться при запуске;
- какие находятся в `processing` с неопределёнными remote effects;
- какие ответы уже сохранены в `outbox`;
- завершилась ли ячейка в Colab после прекращения ожидания CLI;
- принадлежит ли наблюдаемый процесс именно этому project root.

Сначала читать результат исходного request ID через `--result`. При ошибке RPC и отсутствии окончательного ответа проверить UI execution state и фактические output/files в notebook. Нельзя считать timeout или `execution_uncertain` доказательством отсутствия эффекта. Автоматического replay нет.

Если живой bridge свободен и установлена необходимость перезапуска, отправить `__shutdown__`, дождаться его результата и фактической остановки. Он не прерывает active request и не выполняет гарантированный drain всей очереди:

```powershell
& $McpPython $McpCli --project-dir $ProjectRoot __shutdown__ --tool-timeout 30 --wait-timeout 660
& $McpPython $McpCli --project-dir $ProjectRoot --status
```

Для существующего MSI, когда старый процесс действительно завершён и очередь проверена, запустить один bridge в отдельном открытом терминале:

```powershell
& 'C:\Users\Ivan\Projects\colab-blender-mcp\vendor\colab-mcp\.venv\Scripts\python.exe' 'C:\Users\Ivan\Projects\colab-blender-mcp\mcp_bridge.py' --project-dir 'C:\Users\Ivan\Projects\colab-blender-mcp'
```

Для нового clone предпочтителен [start-bridge.ps1](../scripts/windows/start-bridge.ps1): он проверяет fresh heartbeat и наличие старых запросов. `-ResumeReviewedQueue` применяется только после разбора этой очереди; он не делает неизвестные запросы безопасными или отменёнными. OS lock bridge остаётся окончательной защитой от второго экземпляра.

При отсутствии vendor/Python на новой машине — [setup-windows](setup-windows.md). Не удалять старую `.venv` и не сбрасывать vendor, чтобы скрыть несовпадение версий. При неполадке процесса не выполнять массовое завершение Python-процессов.

## D. Сохранить результат recovery

Для существующего MSI вернуться в [connect-existing](connect-existing.md). Для нового clone продолжить раздел 3 [setup-windows](setup-windows.md), затем общие шаги 2–5 connect-existing с уже выбранным корнем; шаг 1 с путём MSI пропустить. Проверка одинакова: tools → identity → короткий smoke при необходимости. До запуска отключённого runtime проверить CPU accelerator для recovery: настройки сохранённого notebook могут запрашивать GPU. Явно сохранить notebook в UI и зафиксировать подтверждение Save. При существенных изменениях скачать фактический IPYNB штатным экспортом и проверить его как отдельный артефакт.

Записать UTC, project root, URL без fragment, фактические tools, request ID, runtime kind и оставшиеся неизвестные в `state.md`. Сохранить первоначальное evidence неизменённым; новый результат не должен переписывать recovery 2026-11-09.

## Особые исторические файлы

[restore_clean_notebook_20261109.py](../scripts/recovery/history/restore_clean_notebook_20261109.py) — одноразовый сценарий прошлого восстановления с жёсткими root, prefix и scratchpad ID. Он сохранён как контекст и **не предназначен для повторного запуска**. Для нового документа использовать UI Upload/Save a copy либо актуальные schemas и новые request IDs после проверки целевой вкладки.

[recover_a100_from_notebook.py](../scripts/recovery/recover_a100_from_notebook.py) извлекает конкретный исторический ZIP из скачанного executed notebook; он не восстанавливает live-соединение. Исходный ZIP уже есть в репозитории. Его назначение и запись рядом со скриптом описаны в [provenance](provenance.md).
