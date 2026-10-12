# NBExport

Утилита для **двусторонней синхронизации (2-way sync)** между Jupyter Notebooks (`.ipynb`) и Python-скриптами (`_exported.py`), а также **полноценный MCP-сервер (Model Context Protocol)** с поддержкой автономных Headless Kernel Sessions для AI-агентов (Antigravity, Claude, Cursor).

Позволяет агентам:
1. Автономно читать ноутбуки (`nb_read`) без мусора и лишних файлов.
2. Безопасно экспортировать (`nb_export`) и накатывать правки (`nb_import`) с защитой от конфликтов по SHA-256 и AST-валидацией.
3. Выполнять код в ядре Jupyter (`notebook_run_cell`), перехватывать выводы, сохранять графики в ассеты и переключать Conda-окружения (`llm_env`, `ml_base`, `python3`).

---

## Установка

```bash
cd C:\Users\alexander\MyFiles\DS_Projects\nbexport
pip install -e .
```

---

## MCP-сервер (`nbexport-mcp`)

Сервер регистрируется в `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "nbexport": {
      "command": "C:/Users/alexander/miniconda3/python.exe",
      "args": ["-m", "nbexport.server"],
      "env": {
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

### Набор MCP-инструментов:

| Инструмент | Описание |
|---|---|
| `nb_export(notebook_path, [output_path], [use_hidden_dir])` | Экспортирует `.ipynb` в Python-скрипт (по умолчанию в скрытую папку `.nbexport/`) |
| `nb_import(exported_py_path, [notebook_path], [force], [validate_syntax])` | Накатывает изменения в `.ipynb` с AST-валидацией, проверкой хэша SHA-256 и бэкапом |
| `nb_read(notebook_path)` | Мгновенно возвращает чистый текст ноутбука и выводов без создания файлов |
| `notebook_run_cell(notebook_path, [code], [cell_id], [env_name], [timeout])` | Запускает код/ячейку в сессии ядра (ZeroMQ), сохраняет графики в ассеты и обновляет outputs |
| `notebook_get_state(notebook_path)` | Возвращает статус ядра, список объявленных переменных (`%whos`) и статистику ячеек |
| `notebook_restart_kernel(notebook_path, [env_name])` | Перезапускает ядро (с возможностью смены conda-окружения) |
| `notebook_interrupt(notebook_path)` | Прерывает зависшее выполнение ячейки (SIGINT) |

---

## CLI-использование

### 1. `nbwatch` — Фоновая двусторонняя синхронизация
```bash
nbwatch                     # Следить за всеми ноутбуками в текущей папке и подкаталогах
nbwatch -i model.ipynb      # Следить за конкретным файлом
```

### 2. `nbexport` — Разовый экспорт
```bash
nbexport                    # Экспортировать все .ipynb в текущей папке
nbexport -i model.ipynb     # Экспортировать конкретный файл
```

### 3. `nbimport` — Разовый импорт
```bash
nbimport                    # Импортировать все *_exported.py обратно в .ipynb
nbimport -i model_exported.py # Импортировать конкретный файл
```

---

## Особенности архитектуры

* **Headless Kernel Session**: Ядро запускается через `jupyter_client` в правильной рабочей директории с поддержкой виртуальных окружений Conda.
* **Cell ID (nbformat 4.5+)**: Ячейки строго привязаны к постоянным `id`.
* **Защита целостности**: AST-проверка синтаксиса предотвращает сохранение поврежденного кода в `.ipynb`.
* **Контроль конфликтов**: Проверка хэша SHA-256 защищает от перезаписи параллельных ручных правок в Jupyter.
* **Атомарная запись**: Запись через временные файлы и автоматическое создание бэкапов в скрытой папке `.nbexport/`.
