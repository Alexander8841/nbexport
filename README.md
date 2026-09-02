# NBExport

Утилита для **двусторонней синхронизации (2-way sync)** между Jupyter Notebooks (`.ipynb`) и Python-скриптами (`_exported.py`). 

Позволяет LLM-агентам (Claude, Cursor, Copilot, Antigravity) видеть выводы ячеек и редактировать чистый код, автоматически перенося изменения обратно в `.ipynb` без засорения ноутбука служебными комментариями.

---

## Установка

```bash
git clone https://github.com/Alexander8841/nbexport.git
cd nbexport
pip install -e .
```

---

## Использование

### 1. `nbwatch` — Фоновая двусторонняя синхронизация (основной режим)
```bash
nbwatch                     # Следить за всеми ноутбуками в текущей папке и подкаталогах
nbwatch -i model.ipynb      # Следить за конкретным файлом (поиск работает по подпапкам)
nbwatch model.ipynb         # То же самое без флага -i
```
* Сохранение в Jupyter/IDE → мгновенно обновляет `*_exported.py` с кодом и выводами.
* Сохранение `*_exported.py` агентом → мгновенно обновляет `.ipynb`.

### 2. `nbexport` — Разовый экспорт (`.ipynb` → `_exported.py`)
```bash
nbexport                    # Экспортировать все .ipynb в текущей папке
nbexport -i model.ipynb     # Экспортировать конкретный файл
```

### 3. `nbimport` — Разовый импорт (`_exported.py` → `.ipynb`)
```bash
nbimport                    # Импортировать все *_exported.py обратно в .ipynb
nbimport -i model_exported.py # Импортировать конкретный файл
```

---

## Формат файла `*_exported.py`

```python
# --- Notebook: analysis.ipynb ---
# Exported: 2026-08-31 12:00:00
# Cells:    2 (Markdown: 1, Code: 1)

# --- CONTENTS ---
# Cell 1   Markdown   [id:intro_01] 1. Анализ данных
# Cell 2   Code       [id:code_01] df.head()


# %% [Cell 1 | Markdown | id:intro_01]
# # 1. Анализ данных

# %% [Cell 2 | Code | id:code_01]
# Execution time: 0.15 sec
import pandas as pd
df = pd.read_csv('data.csv')
df.head()

# --- OUTPUT (execute_result) ---
#    id  value
# 0   1     10
# --- END OUTPUT ---
```

---

## Особенности

* **Cell ID (nbformat 4.5+)**: Ячейки привязаны к постоянным `id` — порядок, добавление и удаление ячеек синхронизируются без сбоев.
* **Smart Search**: При указании имени файла (`-i name.ipynb`) утилита автоматически находит его в подкаталогах.
* **Изоляция ассетов**: Графики (PNG) и длинные выводы (>100 строк) сохраняются в папку `*_exported_assets/`, не раздувая контекст модели.
* **Anti-Loop**: Защита от бесконечных циклов синхронизации на основе хэшей SHA256.
