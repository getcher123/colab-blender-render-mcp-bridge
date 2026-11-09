# Сторонние исходники

Bridge использует официальный [googlecolab/colab-mcp](https://github.com/googlecolab/colab-mcp/tree/b9ab3899e0f1fa493390b1fd6d54aa2e464ecdf1), revision `b9ab3899e0f1fa493390b1fd6d54aa2e464ecdf1`. Upstream содержит copyright Google Inc. и распространяется под Apache License 2.0; копия его [LICENSE](licenses/colab-mcp-APACHE-2.0.txt) сохранена для сопровождения [локального patch](patches/colab-mcp-windows.patch).

Vendor исходники и зависимости устанавливаются из закреплённого upstream и его `uv.lock`; они не включены в дерево этого репозитория. Описание локальных изменений — [decisions](docs/decisions.md) и [architecture](docs/architecture.md). Наличие копии upstream LICENSE не назначает автоматически эту лицензию всем собственным материалам проекта.

Blender binary и tar.xz в репозиторий не входят. [Установщик](scripts/blender/install_blender.py) получает закреплённый официальный archive и сверяет SHA256.
