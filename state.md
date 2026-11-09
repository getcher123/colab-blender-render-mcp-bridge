# Состояние проекта

Дата передачи в GitHub: **2026-11-09**. Этот файл хранит подтверждённый checkpoint; он не заменяет проверку живой сессии. Действующая задача этапа — перенести гайды, скрипты, структуру и контекст в `getcher123/colab-blender-render-mcp-bridge`, проверить маршруты следующего агента.

## Краткий статус

| Область | Подтверждённое состояние | Источник / граница актуальности |
| --- | --- | --- |
| Исходная цель A100 | Выполнена 2026-11-08 | [render_report.json](evidence/a100/render_report.json) |
| Файлы A100 | Восстановлены, SHA256/CRC/12 manifest entries проверены 2026-11-09 | [archive recovery](evidence/a100/archive_recovery_verification.json), ZIP в репозитории |
| MCP frontend | 8 tools + правильный notebook на 09:32:50 UTC 2026-11-09 | [tools](evidence/recovery/restore_20261109_tools_final.json), [snapshot](evidence/recovery/restore_20261109_final_snapshot.json) |
| Исполнение через MCP | `COLAB_MCP_RECOVERY_OK` в 09:28:38.813598 UTC | [smoke](evidence/recovery/smoke.json), [RPC](evidence/recovery/restore_20261109_run_smoke.json) |
| Runtime последнего checkpoint | Новая стандартная CPU-среда, Python 3.13.18; GPU не выделялась | `gpu_probe: null`, `blender_present: false`, `render_executed: false` |
| Drive save | Явный File → Save; UI «Изменения сохранены»; затем настоящий UI-export | [verification](evidence/recovery/verification.json) |
| Проверка при миграции | Проверены файлы, patch и маршруты; live MSI/Colab не изменялись | [validation](evidence/provenance/repository_validation.json) |

## Где продолжать

- Существующий Windows-проект: `C:\Users\Ivan\Projects\colab-blender-mcp` на MSI. Python bridge: `vendor\colab-mcp\.venv\Scripts\python.exe`.
- Рабочая вкладка: https://colab.research.google.com/drive/1vioZDVMV7P_eCazGrLWQ0C17mIFJJpqS — `Blender_Colab_A100_Working_2026-11-09.ipynb`.
- Историческая вкладка A100: https://colab.research.google.com/drive/10fsfs2oTmAX8pugr-hK0mo1nodmDB7qK — источник результатов, не обязательна для продолжения.
- Notebook checkpoint: 15 ячеек = 14 исходных ячеек + recovery smoke. Intro ID `ZGa228Vinvws`, smoke ID `5a8JvwHlopZw`. Перед использованием ID сверить свежий snapshot.
- Во время recovery наблюдались bridge PID `45108` и listener `127.0.0.1:49796`. Это исторические значения конкретного запуска; повторно использовать их без проверки процесса нельзя.
- Remote Desktop Commander при восстановлении использовал MSI device ID `d4468825-14f3-43bd-98a6-6c8b8888ebf7`. Доступность этого устройства у нового агента заранее не предполагается.

Последняя сохранённая verification составлена в 09:38:18.352953 UTC. Последнее доказательство живой связи в ней относится к 09:32:50 UTC. Текущий статус процесса, очереди и VM после этой отметки неизвестен до свежей проверки. У миграции нет live MCP request ID: перенос не отправлял запросов в Colab.

## Что именно выполнено

### 8 ноября: рендер

`a100_pipeline_20261108_v1_run_3`: старт 16:44:39.038 UTC, завершение 16:52:52.970 UTC, exit 0. Blender 4.5.15 LTS (`5afeabba6097`), NVIDIA A100-SXM4-80GB, driver 580.82.07, CUDA, 1600 × 1000, 96 samples, AgX. CPU tracing отключён; OIDN работает на CPU. Все 8 полей `verification` истинны. 1 960 GPU samples и 1 955 записей процесса подтверждают GPU UUID/PID; пик 99% / 3 168 MiB.

Рендер 490,448 с включал около 483 с до первого sample при подготовке CUDA kernels. Исторический L4 результат (7,961 с) не является сопоставимым benchmark. Он сохранён отдельно в [evidence/l4](evidence/l4).

Экспортный RPC достиг 600-секундного timeout, но архив сохранился в output ячейки исторического notebook. Timeout не означал потерю артефактов или отмену работы.

### 9 ноября: восстановление результатов и MCP

Из реально скачанного `Blender_Colab_GPU_Test_executed_A100.ipynb` (6 028 069 байт) извлечён оригинальный ZIP из ячейки index 7, ID `60JyQaCoFYp6`. Проверены имя/размер/SHA256 архива, безопасные пути, CRC, 12 manifest entries, report и телеметрия. Два агента независимо проверяли результат. Новый render и повторное открытие `.blend` в Blender не выполнялись; `.blend` подтверждён hash/header и логом сохранения.

Тяжёлая историческая вкладка зависала после reload. Причина не установлена; большой base64 output — возможный фактор. Отдельная гипотеза о Local Network Access как причине раннего сбоя подключения также не подтверждена. Для продолжения создана и сохранена лёгкая рабочая копия; старый notebook уже не нужен для доступа к исходным артефактам.

Промежуточный [copy checkpoint](evidence/recovery/intermediate_copy_verification.json) отражает 14 ячеек до сохранения и содержит `requires_drive_save: true`. Финальный [recovery report](evidence/recovery/verification.json) отражает сохранённые 15 ячеек. Промежуточное evidence оставлено неизменённым.

### Передача в GitHub

Bridge, CLI, patch, установщик, renderer и extractor перенесены с сохранением содержимого. Созданы единые маршруты подключения/установки/восстановления/рендера, отдельные guides и карта provenance. Исторические гайды сохранены в `docs/history/` с пояснением и исправлением Markdown-ссылок под новую структуру; они не являются вложенными `AGENTS.md`.

Рабочий 15-cell UI-export сохранён побайтно. Производный чистый шаблон для новых запусков отличается от исходного 14-cell notebook: исправлены A100 metadata, output получает отдельный run ID, повторная запись в непустой output запрещена, exporter читает фактический `OUTPUT_DIR`. Изменены code cells 2/8/12 и пояснение cell 11 (нумерация с нуля); embedded installer/renderer не менялись. Историческая проверка «все 14 источников совпадают» относится к исходной версии из полного пакета, не к новой производной.

## Контрольные суммы ключевых оригиналов

| Объект | Байты | SHA256 |
| --- | ---: | --- |
| Исходный A100 ZIP | 2 792 148 | `1ff57a0dfd72144ee4459644f33f14954042c7ad410ee425ed7415e4b1bfe7cf` |
| A100 PNG | 1 662 354 | `cb891c24fd5c545b24fb2e1fb8a3adba3bed818ce43ea2fd5ed827bb205e1efc` |
| A100 `.blend` | 4 873 511 | `70d2d5afd6e1ca5765b0350dadd30c204f2e782b8181133b582b144c876c5f31` |
| Реальный working UI-export | 75 534 | `6892ee035aa1f34a9675c5ded25a762023d4f565645258c69443b74b6c7f9bf1` |
| Исторический executed UI-export | 6 028 069 | `787456f2b006575984627cfec353ec436ff7bf2ff01702a8a78336deb33fd25a` |
| Исходный clean notebook до миграции | 74 292 | `b9869e21cdf4989520aa3d4541469141a8c2775e7af27d0d8f6afa7bf7242923` |
| Полный исходный handoff ZIP | 14 288 213 | `ba3389693a98b4b6158f45a63d7e32e2ac74c12c6ccca86a5f971e866eecf021` |

Производный clean notebook имеет другой hash; актуальное значение — в [карте переноса](evidence/provenance/source_to_repository.json). Исходные checksum records не переписывались под новую структуру.

## Следующий шаг

Если задача — принять контекст, закончить чтение [маршрутов](docs/agent-routes.md) и проверить локальный A100 ZIP. Live-подключение для этого не требуется.

Если задача — продолжить управление существующим Colab, пройти [connect-existing](docs/connect-existing.md): статус → проверка процесса/очереди → 8 tools → идентичность notebook. При проблеме перейти в [recover-connection](docs/recover-connection.md). При отсутствии доступа к MSI подготовить новую локальную установку через [setup-windows](docs/setup-windows.md); новый clone сам по себе не подключается к старому loopback.

Новый render имеет смысл только при новой задаче. Тогда открыть производный шаблон отдельной копией в Drive, выбрать/проверить фактическую A100 и пройти [render-and-export](docs/render-and-export.md). Старый A100-комплект, исторические evidence и действующий рабочий документ не перезаписывать.

Открытых обязательных работ для доказательства исходного A100-результата нет. Неизвестны до следующей live-проверки: доступность MSI, состояние bridge/очереди, browser binding, текущая VM/GPU и доступность Drive для нового агента. Права GitHub не предоставляют доступ к аккаунту Colab.
