# Происхождение файлов и проверка артефактов

Репозиторий собран из проверенного полного пакета `Blender_Colab_A100_Full_2026-11-09.zip`. В нём 54 файла; каждому исходному файлу сопоставлен путь Git, содержимое включённого архива или явно обозначенное место в полном пакете. Машиночитаемая карта — [source_to_repository.json](../evidence/provenance/source_to_repository.json). Исходные [inventory](../evidence/provenance/source_package_inventory.json) и [SHA256SUMS](../evidence/provenance/source_package_SHA256SUMS.txt) сохранены без изменения и используют **пути исходного пакета**, а не новую структуру Git.

## Что доступно непосредственно в Git

| Материал | Путь | Статус |
| --- | --- | --- |
| Постоянная сессия и CLI | [mcp_bridge.py](../mcp_bridge.py), [mcp_call.py](../mcp_call.py) | Исходные байты сохранены |
| Vendor patch | [patches/colab-mcp-windows.patch](../patches/colab-mcp-windows.patch) | Три исходные правки; применимость к pinned revision проверена |
| Blender installer и renderer | [scripts/blender](../scripts/blender) | Исходные байты, совпадают с embedded кодом |
| Исторические recovery scripts | [scripts/recovery](../scripts/recovery) | Исходные байты; назначение и ограничения ниже |
| Рабочий UI-export | [15-cell notebook](../notebooks/Blender_Colab_A100_Working_2026-11-09.ipynb) | Настоящий экспорт Drive, неизменённый |
| Новый clean template | [14-cell notebook](../notebooks/Blender_Colab_GPU_Test.ipynb) | Производная версия; изменения открыто описаны |
| Исторические гайды | [docs/history](history/README.md) | Весь текст сохранён, добавлено предупреждение и адаптированы Markdown-ссылки |
| A100 evidence | [evidence/a100](../evidence/a100) | Report, CSV, logs, MCP response, manifest, recovery verification |
| Recovery evidence | [evidence/recovery](../evidence/recovery) | CPU smoke, настоящий tools/snapshot, промежуточная и финальная verification |
| L4 evidence | [evidence/l4](../evidence/l4) | Отдельные report/install/CSV/logs; A100-цель там не выполнена |
| Исходные `.blend` и PNG A100 | [A100 ZIP](../artifacts/a100/Blender_Colab_A100_Render_2026-11-08.zip) | Полный оригинальный архив, без повторной упаковки |
| Preview A100 | [assets/test_render_A100.png](../assets/test_render_A100.png) | Тот же PNG, что внутри оригинального ZIP |

Evidence JSON/CSV/logs сохраняют исходные байты, включая CRLF, где они были. `.gitattributes` отключает для `evidence/` преобразование переводов строк. Пути вроде `C:\Users\Ivan\...` и `output/...` внутри старых report не переписаны: это provenance того запуска. Новые пути отражены только в карте переноса и текущих гайдах.

## Оригинальный A100 ZIP

Имя: `Blender_Colab_A100_Render_2026-11-08.zip`; размер 2 792 148 байт; SHA256 `1ff57a0dfd72144ee4459644f33f14954042c7ad410ee425ed7415e4b1bfe7cf`.

Архив содержит 12 файлов и `manifest.json` в форме списка:

| Группа | Файлы внутри ZIP |
| --- | --- |
| Код | `install_blender.py`, `render_test.py` |
| Метаданные/проверка | `install.json`, `gpu_probe.json`, `mcp_smoke.json` |
| Установка | `install_output.log` |
| Результат | `output/test_scene.blend`, `output/test_render.png`, `output/render_report.json` |
| Телеметрия/лог | `output/gpu_samples.csv`, `output/blender_gpu_processes.csv`, `output/blender_render.log` |

`.blend`: 4 873 511 байт, SHA256 `70d2d5afd6e1ca5765b0350dadd30c204f2e782b8181133b582b144c876c5f31`.

PNG: 1 662 354 байта, SHA256 `cb891c24fd5c545b24fb2e1fb8a3adba3bed818ce43ea2fd5ed827bb205e1efc`.

Локальная проверка из корня clone, Python 3.10+:

```powershell
python .\scripts\verify_bundle.py .\artifacts\a100\Blender_Colab_A100_Render_2026-11-08.zip --expect-sha256 1ff57a0dfd72144ee4459644f33f14954042c7ad410ee425ed7415e4b1bfe7cf
```

Verifier не распаковывает архив и не запускает Blender. Он проверяет digest архива, CRC, безопасные уникальные пути, полное соответствие manifest составу ZIP, размеры и SHA256 каждого файла. Поддерживаются исторический list manifest и новый object с `files`. Лимит просмотра — 512 MiB суммарного распакованного размера; для более крупных будущих сцен нужен отдельный проверенный маршрут, а не отключение проверки.

Целостность архива и доказательство GPU — разные проверки. Для GPU сверить `success_verified_a100`, `target_a100_met`, все `verification`, enabled Cycles devices, аппаратный GPU UUID, PID/namespace PID Blender и CSV. [Историческая проверка восстановления](../evidence/a100/archive_recovery_verification.json) уже фиксирует такую сверку. [MCP response](../evidence/a100/a100_render_mcp_evidence.json) связывает результат с реальным вызовом. `A100_run_summary.json` является производной сводкой stdout; полный report имеет приоритет.

## Как восстановили архив

2026-11-09 был штатно скачан реальный исторический executed notebook — 6 028 069 байт, SHA256 `787456f2b006575984627cfec353ec436ff7bf2ff01702a8a78336deb33fd25a`. В output ячейки index 7, ID `60JyQaCoFYp6`, сохранился ZIP в base64, хотя прежний export RPC достиг timeout.

[recover_a100_from_notebook.py](../scripts/recovery/recover_a100_from_notebook.py) проверяет точное имя/размер/hash этого архива, decoded payload, CRC и пути, фиксированный набор файлов, list manifest из 12 записей, report/GPU/CSV/PNG/header `.blend`. Он **специализирован под этот архив**, не является импортёром новых render ZIP.

Скрипт принимает путь к скачанному `.ipynb` и пишет `Blender_Colab_A100_Render_2026-11-08.zip`, `a100_artifacts/` и `verification_summary.json` **рядом с самим скриптом**. Отличающиеся существующие binary/artifact-файлы он не перезаписывает; summary может быть обновлена. Для повторной forensic проверки лучше скопировать script в отдельный `local_artifacts/forensic/` и запускать там с фактическим путём notebook. Обычному следующему агенту достаточно уже восстановленного ZIP в Git.

[restore_clean_notebook_20261109.py](../scripts/recovery/history/restore_clean_notebook_20261109.py) — исходный одноразовый сценарий реконструкции. В нём старый MSI root, фиксированные request IDs и ожидаемый пустой scratchpad ID. Его хранение передаёт историю, но не делает его подходящим для повторного исполнения. Текущий маршрут создания документа — Upload/Save a copy и свежая проверка identity.

## Два уровня версии notebook

Фактический рабочий экспорт: 75 534 байта, SHA256 `6892ee035aa1f34a9675c5ded25a762023d4f565645258c69443b74b6c7f9bf1`. Он сохранён без изменения. [Final verification](../evidence/recovery/verification.json) подтверждает 15 ячеек, smoke, Drive Save и совпадение первых 14 sources с исходным clean template.

Исходный clean template в полном пакете: 74 292 байта, SHA256 `b9869e21cdf4989520aa3d4541469141a8c2775e7af27d0d8f6afa7bf7242923`. Репозиторная версия изменяет metadata и ячейки 2/8/11/12 для безопасного нового output/export. Её hash зафиксирован в mapping; её нельзя представлять как прежний UI-export. [Точный список изменений](../notebooks/README.md).

## Полный исходный пакет

[Blender_Colab_A100_Full_2026-11-09.zip](https://chatgpt.com/library?file_id=libfile_fde3_f-c914bd2e88748191aeae0d3fbc48ccee_52da9a96997481919b53be3b1218b269&account_id=personal) — 14 288 213 байт, SHA256 `ba3389693a98b4b6158f45a63d7e32e2ac74c12c6ccca86a5f971e866eecf021`.

Ссылка требует доступа владельца к сохранённому файлу ChatGPT. Внешнему агенту такой доступ автоматически не предоставляется. Для основной работы, нового подключения и проверки A100 репозиторий самодостаточен; пакет нужен для точных прежних Markdown-байтов, исходного clean notebook до исправлений, тяжёлого executed notebook и binary-результатов старого L4. Если внешний агент должен выполнить именно forensic-проверку этих дополнительных оригиналов, владелец передаёт ему этот пакет разрешённым способом.

В Git не дублируются тяжёлый executed notebook с base64 и L4 `.blend`/PNG. A100 `.blend` уже включён в оригинальный ZIP, а PNG дополнительно доступен как preview. Каждый из этих вариантов явно указан для соответствующего исходного файла в mapping. Ни один исходный гайд или Python-скрипт не потерян.

## Упоминания, которых не было в исходном пакете

Исторические документы упоминают `mcp_large_payload_verification.json`, реконструированный `A100_run_record.ipynb`, прежнюю L4 smoke-пару, `A100_run_summary_before_recovery.json` и ранние checkpoint ZIP. Эти материалы отсутствуют среди 54 исходных файлов; они не созданы заново и не выданы за перенесённые originals. Неразрешимые Markdown-ссылки в историческом README заменены честным текстовым пояснением. Сохранённые descriptions таких проверок являются историческими записями, а не отдельным найденным первичным файлом.

## Проверка самого переноса

[repository_validation.json](../evidence/provenance/repository_validation.json) фиксирует состав, ссылки, маршруты, исходные hashes, patch, notebook/export tests и ограничения. Live подключение MSI, установка на Windows и новый GPU-render в ходе миграции не тестировались. Первичные UTC-метки recovery не заменяются временем Git commit.
