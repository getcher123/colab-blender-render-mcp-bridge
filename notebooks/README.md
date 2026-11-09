# Ноутбуки

| Файл | Назначение | Происхождение |
| --- | --- | --- |
| [Blender_Colab_GPU_Test.ipynb](Blender_Colab_GPU_Test.ipynb) | Самостоятельный шаблон для нового GPU-прогона; 14 ячеек без outputs | Производная версия проверенного исходника |
| [Blender_Colab_A100_Working_2026-11-09.ipynb](Blender_Colab_A100_Working_2026-11-09.ipynb) | Точный экспорт сохранённого рабочего Drive notebook; 15 ячеек | Фактический UI Download IPYNB после явного Save 2026-11-09 |

Для нового рендера открыть чистый шаблон в Colab через GitHub/Upload и **сохранить отдельную копию в Drive**. Рабочий документ recovery и его экспорт остаются свидетельством прежнего checkpoint. [Подробный порядок запуска](../docs/render-and-export.md).

## Изменения чистого шаблона при переносе

Исходный clean notebook имел SHA256 `b9869e21cdf4989520aa3d4541469141a8c2775e7af27d0d8f6afa7bf7242923`. При переносе в Git исправлены:

- metadata `recorded_test_gpu`, `recorded_target_a100_met` и путь report: они ещё описывали L4, хотя вступление и итоговый отчёт уже относились к A100; результат явно помечен историческим;
- недостоверная для неисполненного шаблона metadata-подсказка `language_info.version: 3.12` удалена; реальная версия Python проверяется в runtime;
- cell 2: каждый запуск конфигурации получает UTC run ID с микросекундами и `OUTPUT_DIR = WORK_DIR / "runs" / RUN_ID / "output"`;
- cell 8: renderer отказывается начинать запись в непустой output directory;
- cell 11: пояснение нового экспорта;
- cell 12: архив берёт файлы именно из `OUTPUT_DIR`, а внутри ZIP сохраняет стабильные имена `output/…`; ZIP создаётся с уникальным именем и режимом exclusive create.

Нумерация здесь с нуля. Все остальные cell sources сохранены. Embedded `INSTALLER_SOURCE` дословно совпадает с [install_blender.py](../scripts/blender/install_blender.py); содержимое `%%writefile` совпадает с [render_test.py](../scripts/blender/render_test.py). Эти два скрипта не менялись.

`WORK_DIR` остаётся `/content/colab_blender`. Magic ячейки исходника также явно пишет `/content/colab_blender/render_test.py`. Если переносить весь WORK_DIR, нужно согласованно менять эту magic и код, который ищет Blender. Простое перемещение `.ipynb` в каталог `notebooks/` на это не влияет.

Свежий запуск рендера и установка Blender при подготовке GitHub не выполнялись. Изменения glue-кода проверены отдельно на локальном mock-наборе со старыми/новыми output, missing required file и guard от перезаписи. Проверка не является новым результатом GPU.

## Рабочий UI-экспорт сохранён неизменённым

75 534 байта, SHA256 `6892ee035aa1f34a9675c5ded25a762023d4f565645258c69443b74b6c7f9bf1`. В нём 14 исходных ячеек и отдельный smoke CPU recovery. Его оригинальный exporter рассчитан на `WORK_DIR/output`. Для нового рендера с отдельными каталогами использовать производный чистый шаблон; не переносить только новую переменную OUTPUT_DIR в старый exporter.

Утверждение исторической [verification](../evidence/recovery/verification.json) о совпадении всех 14 source cells относится к **исходному clean notebook** из полного пакета. Оно не выдаётся за сравнение с изменённым шаблоном этого репозитория. Точные mapping/hashes находятся в [provenance manifest](../evidence/provenance/source_to_repository.json).

Большой `Blender_Colab_GPU_Test_executed_A100.ipynb` с архивом внутри output находится в [полном исходном пакете](../docs/provenance.md). Основной A100 ZIP уже [доступен отдельно в Git](../artifacts/a100/Blender_Colab_A100_Render_2026-11-08.zip), поэтому для работы с результатом тяжёлый notebook открывать не нужно.
