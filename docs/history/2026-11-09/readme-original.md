> Исторический документ. Содержательные записи относятся к состоянию указанного этапа; Markdown-ссылки адаптированы к структуре GitHub. Текущие инструкции: [AGENTS.md](../../../AGENTS.md), актуальное состояние: [state.md](../../../state.md). Оригинальные байты и прежние пути сохранены в полном исходном пакете; см. [историю](../README.md) и [provenance](../../provenance.md).

# Blender в Google Colab через MCP

## Результат и текущее состояние — 9 ноября 2026

**Подключение MCP восстановлено.** На 12:32:50 МСК (09:32:50 UTC) подтверждены все 8 инструментов официального Colab MCP, чтение правильного рабочего notebook и реальное исполнение проверочной ячейки. Рабочая копия явно сохранена через **Файл → Сохранить**, интерфейс подтвердил «Изменения сохранены»; затем notebook штатно скачан и проверен.

**Полный результат A100-рендера от 8 ноября сохранён вне Colab.** 9 ноября из сохранённого output исторического notebook восстановлены исходные `.blend`, PNG, полный JSON-отчёт, CSV-телеметрия и логи. Размер, SHA256 архива, ZIP CRC и все 12 записей manifest проверены; результат дополнительно проверен другим агентом. Основной `output/` — A100. Первый тест на L4 отделён в `previous_l4/`.

Текущая среда лёгкого рабочего notebook — **новая стандартная CPU-среда для проверки MCP**. Её smoke показывает `gpu_probe: null`, `blender_present: false`, `render_executed: false`. Это состояние текущей VM; оно не отменяет ранее выполненный A100-рендер и сохранённые файлы. Новая GPU-сессия для восстановления не выделялась, Blender и рендер повторно не запускались.

## С чего продолжать

- [Рабочий notebook](https://colab.research.google.com/drive/1vioZDVMV7P_eCazGrLWQ0C17mIFJJpqS): **Blender_Colab_A100_Working_2026-11-09.ipynb**.
- [Исторический notebook A100-прогона](https://colab.research.google.com/drive/10fsfs2oTmAX8pugr-hK0mo1nodmDB7qK): источник сохранённых результатов; для текущего управления использовать лёгкую рабочую копию.
- Рабочий каталог MSI: `C:\Users\Ivan\Projects\colab-blender-mcp`.
- Сначала прочитать [AGENTS.md](agents-original.md) и [state.md](state-original.md).

В рабочем notebook 15 ячеек: 14 исходных ячеек чистого notebook и отдельная smoke-ячейка восстановления. Все 14 исходников сверены с текущим `Blender_Colab_GPU_Test.ipynb`; output smoke совпадает с сохранённым успешным MCP-ответом. Реальный экспорт этой рабочей копии: [Blender_Colab_A100_Working_2026-11-09.ipynb](../../../notebooks/Blender_Colab_A100_Working_2026-11-09.ipynb), 75 534 байта, SHA256 `6892ee035aa1f34a9675c5ded25a762023d4f565645258c69443b74b6c7f9bf1`.

Историческая тяжёлая вкладка зависала после reload. Техническая причина не установлена. Большой output с base64 — возможный фактор, а не подтверждённый диагноз. Её результаты уже сохранены; восстановление этой вкладки не является условием продолжения работы.

## Подтверждённый A100-рендер

Данные взяты из оригинального [render_report.json](../../../evidence/a100/render_report.json) и сверены с CSV, PNG, `.blend` и MCP-ответом.

| Параметр | Результат |
| --- | --- |
| Статус | `success_verified_a100`, `target_a100_met: true` |
| Blender | 4.5.15 LTS, build `5afeabba6097` |
| Фактический GPU | NVIDIA A100-SXM4-80GB, 81 920 MiB |
| NVIDIA driver / backend | 580.82.07 / CUDA |
| Изображение | 1600 × 1000, 96 samples, Cycles, AgX |
| Трассировка | A100; CPU-устройство Cycles отключено |
| Denoise | OpenImageDenoise на CPU |
| Время рендера / MCP-вызова | 490,448 с / 493,933 с |
| Телеметрия | 1 960 GPU samples и 1 955 записей процесса Blender |
| Пик GPU / память Blender | 99% / 3 168 MiB |
| Проверки | Все 8 полей `verification` истинны; GPU UUID и PID подтверждены CSV |

Около 483 секунд первого запуска прошло до `Sample 0/96` при подготовке CUDA kernels. Поэтому 490,448 секунды не являются замером установившейся скорости трассировки. Сравнивать это число напрямую с 7,961 секунды первого L4-теста некорректно. Дополнительный прогон ради бенчмарка не выполнялся.

Сцена — процедурный демонстрационный аппарат со стеклом, металлом, трубами и студийным освещением. Она служит проверкой рендера и не является инженерной моделью оборудования.

## Файлы и происхождение

| Файл или папка | Назначение |
| --- | --- |
| `output/` | Проверенные оригиналы A100: `.blend`, PNG, JSON, две CSV и render log |
| `previous_l4/` | Неизменённые исходные файлы первого L4-теста и пояснение |
| `Blender_Colab_GPU_Test.ipynb` | Чистый воспроизводимый исходник: 14 ячеек без outputs |
| `Blender_Colab_A100_Working_2026-11-09.ipynb` | Реальный текущий UI-экспорт: 14 исходных ячеек + smoke восстановления |
| `Blender_Colab_GPU_Test_executed_A100.ipynb` | Реальный UI-экспорт исторического notebook, включая output с архивом |
| `install_blender.py`, `render_test.py` | Полные исходники закреплённой установки и тестовой сцены |
| `mcp_bridge.py`, `mcp_call.py`, `colab-mcp-windows.patch` | Постоянная MCP-сессия, файловая очередь и три локальные правки upstream |
| `mcp_smoke.json`, `mcp_smoke_evidence.json` | Историческая проверка A100 от 8 ноября, 16:54:49 UTC |
| `mcp_recovery_smoke.json` | Проверка восстановленного MCP на новой CPU-среде от 9 ноября |
| `a100_render_mcp_evidence.json`, `a100_render_stdout.log` | Фактический успешный MCP-вызов A100-рендера и stdout |
| `A100_run_summary.json` | Сводка исходного stdout с обновлённым состоянием выгрузки; полный отчёт лежит в `output/` |
| `history/2026-11-08/` | Сохранённые прежние README, state и AGENTS; исторические инструкции |
| `package_inventory.json`, `SHA256SUMS.txt` | Состав и контрольные суммы окончательно сформированного пакета |

В рабочем каталоге доказательства восстановления находятся в `artifacts/recovery_2026-11-09/`; в финальном пакете они расположены в `recovery/` и `evidence/`. `verification_summary.json` подтверждает оригинальный архив A100, `current_notebook_verification.json` — актуальный notebook и фактический UI-экспорт. Сырые `bridge_state`, vendor, `.venv`, токены и приватные MCP logs не входят в пакет.

Проверенный исходный архив A100: 2 792 148 байт, SHA256 `1ff57a0dfd72144ee4459644f33f14954042c7ad410ee425ed7415e4b1bfe7cf`. PNG: `cb891c24fd5c545b24fb2e1fb8a3adba3bed818ce43ea2fd5ed827bb205e1efc`. `.blend`: `70d2d5afd6e1ca5765b0350dadd30c204f2e782b8181133b582b144c876c5f31`.

## Проверка и восстановление MCP на MSI

Проверенный маршрут: Remote Desktop Commander → локальный Python-клиент → stdio официального `googlecolab/colab-mcp` → WebSocket на loopback → открытая вкладка Colab → её вычислительная среда.

Upstream: revision `b9ab3899e0f1fa493390b1fd6d54aa2e464ecdf1`, package 1.0.1. Для MCP используется отдельный Python 3.13.18 в `vendor/colab-mcp/.venv`; системный Python не заменялся. Установленные vendor и окружение находятся на MSI и исключены из передаваемого пакета.

Сначала проверить свежий heartbeat и доступные инструменты:

```powershell
& 'C:\Users\Ivan\Projects\colab-blender-mcp\vendor\colab-mcp\.venv\Scripts\python.exe' 'C:\Users\Ivan\Projects\colab-blender-mcp\mcp_call.py' --status
& 'C:\Users\Ivan\Projects\colab-blender-mcp\vendor\colab-mcp\.venv\Scripts\python.exe' 'C:\Users\Ivan\Projects\colab-blender-mcp\mcp_call.py' __list_tools__
```

Свежий heartbeat подтверждает локальный bridge. Живое подключение Colab подтверждают инструменты ячеек и успешный `get_cells` правильного документа. Текущие 8 инструментов: `open_colab_browser_connection`, `add_code_cell`, `add_text_cell`, `delete_cell`, `get_cells`, `move_cell`, `run_code_cell`, `update_cell`.

Если frontend утрачен, выполнить штатный bootstrap текущего bridge:

```powershell
& 'C:\Users\Ivan\Projects\colab-blender-mcp\vendor\colab-mcp\.venv\Scripts\python.exe' 'C:\Users\Ivan\Projects\colab-blender-mcp\mcp_call.py' open_colab_browser_connection --detach
```

Bootstrap может открыть пустой scratchpad. Перед записью подтвердить URL и содержимое нужного рабочего notebook через `get_cells`. Для перепривязки использовать только штатный Browser plugin и актуальное подключение текущего bridge. URL fragment содержит данные доступа: не сохранять его в документацию и не публиковать. После изменений ячеек явно сохранить notebook и дождаться «Изменения сохранены».

Перезапуск требуется только при установленной неисправности свободного bridge. После проверки принадлежности процесса и отсутствия выполняющегося запроса:

```powershell
& 'C:\Users\Ivan\Projects\colab-blender-mcp\vendor\colab-mcp\.venv\Scripts\python.exe' 'C:\Users\Ivan\Projects\colab-blender-mcp\mcp_call.py' __shutdown__
& 'C:\Users\Ivan\Projects\colab-blender-mcp\vendor\colab-mcp\.venv\Scripts\python.exe' 'C:\Users\Ivan\Projects\colab-blender-mcp\mcp_bridge.py'
```

Вторую команду выполнять после подтверждённой остановки старого bridge. Очередь последовательная, таймаут CLI не отменяет удалённое выполнение. Для проверки уже отправленного запроса использовать `--result` с его фактическим ID. Не повторять изменяющий запрос вслепую и не переиспользовать исторические ID.

Три сохранённые правки vendor: bind на `127.0.0.1`; `asyncio.shield` только для startup task; конечный входящий WebSocket-лимит 16 MiB. Token/Origin-проверки сохранены. Наблюдавшиеся PID и порт являются состоянием конкретного процесса, а не конфигурацией будущего запуска.

## Следующая содержательная задача

Для нового реального рендера открыть рабочий notebook, выбрать A100, проверить фактически выданное устройство и выполнить чистые ячейки по порядку. Установщик закреплён на Blender 4.5.15 и проверяет SHA256 официального архива `0d2b8bb2efe97e6c8eb57de6b7322f8800e1984e3125b60decca5f6771e4773e`. Его содержимое дословно совпадает с `INSTALLER_SOURCE` чистого notebook и восстановленным A100-архивом.

Сохранять новый результат в отдельный каталог вывода. Текущий A100-комплект не перезаписывать; повторный рендер для доказательства уже завершённой цели не нужен. После значимого прогона скопировать результаты вне временной VM, проверить manifest и обновить `state.md`. Тариф, покупки вычислительных ресурсов и anti-idle обходы автоматически не менять и не запускать.
