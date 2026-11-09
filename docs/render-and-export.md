# Новый A100-рендер и экспорт

Маршрут выполняется при новой задаче пользователя. Завершённый A100-прогон 2026-11-08 уже доказан [исходным report](../evidence/a100/render_report.json) и [ZIP](../artifacts/a100/Blender_Colab_A100_Render_2026-11-08.zip). Перенос контекста не требует повторного рендера.

## Подготовка

1. Если используется MCP, пройти [подключение](connect-existing.md) или [recovery](recover-connection.md). Один ведущий управляет notebook/runtime.
2. Открыть [чистый шаблон](../notebooks/Blender_Colab_GPU_Test.ipynb) отдельным документом Colab и сохранить копию в Drive. Зафиксировать фактический новый URL; не перезаписывать working recovery notebook. При управлении через MCP **перепривязать единственное frontend-соединение к этой новой копии** по разделу B [recovery](recover-connection.md), используя её новый URL вместо исторического working URL. После binding проверить `get_cells` против производного шаблона и взять реальные cell IDs из этого snapshot. До такой проверки `run_code_cell` не отправлять: открытие новой вкладки само по себе не переключает MCP.
3. Выбрать A100 штатно в настройках runtime. Не менять тариф и не покупать вычислительные ресурсы автоматически. Выбор UI — запрос, а не доказательство фактически выделенного оборудования.
4. Выполнять ячейки последовательно, дожидаясь исхода каждой. Не запускать `run all` вслепую через очередь и не отправлять зависимые RPC параллельно.

Для открытия шаблона прямо из GitHub можно использовать [Colab GitHub notebook](https://colab.research.google.com/github/getcher123/colab-blender-render-mcp-bridge/blob/main/notebooks/Blender_Colab_GPU_Test.ipynb), затем Save a copy in Drive. Это создаёт новую копию, а не меняет документ по старому Drive URL.

## Порядок ячеек

| Code cell, индекс с нуля | Что делает | Что проверить до следующего шага |
| --- | --- | --- |
| 2 | `EXPECTED_GPU="A100"`, GPU guard, `RUN_ID`, новый `OUTPUT_DIR` | Фактически выдана A100; `GPU_GUARD_PASSED=True` |
| 4 | Записывает полный installer и выполняет закреплённую установку | SHA256 официального archive совпадает; Blender 4.5.15 найден |
| 6 | Записывает полный `render_test.py` | Исходник в `/content/colab_blender/render_test.py` |
| 8 | Повторный GPU guard, foreground Blender, report/CSV/logs | Exit 0, `success_verified_a100`, восемь verification-проверок |
| 10 | Читает текущий report и показывает PNG | Источником служит текущий `OUTPUT_DIR`, а не старая таблица во вступлении |
| 12 | Собирает ZIP из текущего output и вызывает штатный download | Файл реально скачан, затем проверен вне Colab |

Новый `OUTPUT_DIR` имеет вид `/content/colab_blender/runs/` + UTC run ID + `/output`. RUN_ID вычисляется самим notebook с микросекундами. Повторный запуск cell 8 с непустым output остановится до открытия render log. Для нового прогона сначала сохранить предыдущий комплект и начать с конфигурационной ячейки, которая выдаст новый run ID.

`WORK_DIR` не менять только в одном месте: ячейка `%%writefile` содержит абсолютный путь исходника. Для обычного нового запуска достаточно отдельного OUTPUT_DIR, что уже реализовано в шаблоне.

## Закреплённый Blender и проверка GPU

Установщик использует официальный `blender-4.5.15-linux-x64.tar.xz` и проверяет SHA256 двумя способами: против закреплённого значения и против официального checksum-файла. Ожидаемый hash:

```text
0d2b8bb2efe97e6c8eb57de6b7322f8800e1984e3125b60decca5f6771e4773e
```

При другом GPU guard останавливает установку. Альтернативный L4-прогон возможен только как отдельная явно выбранная задача, с `EXPECTED_GPU="L4"` и честным `target_a100_met:false`. Смена строки не создаёт A100.

Renderer запускается **внутри Blender**, а не обычным Python. Он проверяет фактическое оборудование, enabled CUDA device, процесс Blender в `nvidia-smi`, GPU UUID/PID, свежесть PNG и `.blend`. CPU-устройство трассировки отключается; CPU-подготовка сцены и OpenImageDenoise допустимы и не равны CPU tracing.

Отдельный [render_test.py](../scripts/blender/render_test.py) по умолчанию пишет в `/content/blender-a100/output`. Notebook всегда передаёт явный `--output-dir`, поэтому его новый каталог используется корректно. При ручном вызове также передавать путь явно и не рассчитывать на default.

## Ожидание и неопределённый исход

Bridge ограничивает MCP RPC 600 секундами. Notebook задаёт installer/render subprocess timeout 1200 секунд. Первый CUDA-прогон может долго готовить kernels; исторический A100 занимал 490,448 с, из которых около 483 с прошли до первого sample. Эти величины не являются обещанием времени будущего запуска.

Отправляя `run_code_cell`, сохранить фактический request ID. После `--wait-timeout` сначала использовать `--result` этого ID. Если завершился именно MCP timeout, повторное чтение outbox может показать уже зафиксированную ошибку, хотя удалённая ячейка ещё работает. Тогда проверить execution state в UI, актуальные outputs и файлы. **Не отправлять render повторно, пока исход первого запуска не установлен.** `__shutdown__` этого не исправляет и не прерывает выполняющийся код.

При ошибке скачать JSON/log текущего запуска отдельно для диагностики. Не заменять новый report историческим успешным report, чтобы «починить» комплект.

## Экспорт и сохранение

Exporter читает фактический `OUTPUT_DIR`. В ZIP пути нормализованы в `output/test_scene.blend`, `output/test_render.png`, `output/render_report.json`, CSV и log; исходники и installation metadata берутся из WORK_DIR. Поэтому новый уникальный каталог и manifest согласованы. `manifest.json` нового шаблона — объект с `files`; число записей зависит от наличия optional `install_deps.log`. Исторический A100 manifest был списком ровно из 12 записей.

В новом архиве также записаны RUN_ID и исходный путь output. ZIP создаётся с уникальным временем и exclusive mode; если файл уже существует, он не перезаписывается. Штатный `files.download` используется вместо печати многомегабайтного base64 в output. Успех cell 12 ещё не доказывает, что файл сохранился на компьютере — проверить фактическую загрузку.

Скачанный ZIP хранить отдельно для каждого запуска. Пример проверяет последний архив с точным префиксом, скачанный в стандартный Windows Downloads; перед проверкой показывает выбранный полный путь:

```powershell
$Downloads = Join-Path $env:USERPROFILE 'Downloads'
$NewBundle = Get-ChildItem -LiteralPath $Downloads -Filter 'Blender_Colab_GPU_Test_A100_*.zip' -File |
    Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $NewBundle) { throw 'Новый A100 ZIP в Downloads не найден.' }
$NewBundle | Select-Object FullName, Length, LastWriteTimeUtc
python .\scripts\verify_bundle.py $NewBundle.FullName
if ($LASTEXITCODE -ne 0) { throw 'Проверка архива не пройдена.' }
```

Команду выполнять из корня GitHub clone. Сверить имя и время с наблюдавшимся download текущего RUN_ID, а не полагаться только на сортировку. Если браузер сохраняет в другом каталоге, использовать наблюдаемый download path. Записать полученный SHA256 и manifest count в новый evidence/`state.md`. Проверка ZIP подтверждает целостность; GPU-доказательство требует чтения report и сопоставления UUID/PID/CSV.

После сохранения ZIP явно сохранить notebook в Drive и дождаться подтверждения. При необходимости скачать настоящий IPYNB как новый артефакт. Освобождать GPU штатным отключением runtime после подтверждения сохранения результатов. `__shutdown__` bridge не отключает Colab VM.

## Передача нового результата

Обновить `state.md` новым URL, UTC, RUN_ID, request ID, GPU, Blender, статусом report, hashes и местом сохранения. Исторические A100/L4 evidence оставить неизменёнными. Проверить новый комплект по [provenance route](provenance.md) и выполнить [handoff](handoff.md).
