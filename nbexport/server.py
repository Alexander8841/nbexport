import json
import os
from mcp.server.fastmcp import FastMCP
from .exporter import export_notebook, get_clean_text
from .importer import import_to_notebook, resolve_notebook_path
from .kernel import kernel_manager

mcp = FastMCP("nbexport")

@mcp.tool()
def nb_export(notebook_path: str, output_path: str = None, use_hidden_dir: bool = True) -> str:
    """
    Экспортирует Jupyter Notebook (.ipynb) в чистый Python-файл для анализа и редактирования LLM.
    По умолчанию сохраняет в скрытую папку .nbexport/ рядом с ноутбуком.

    Args:
        notebook_path: Абсолютный или относительный путь к файлу .ipynb.
        output_path: Опциональный путь для сохранения .py файла. Если не задан, сохраняется в .nbexport/<name>_exported.py.
        use_hidden_dir: Использовать ли папку .nbexport/ (по умолчанию True).
    """
    if not os.path.exists(notebook_path):
        return json.dumps({"status": "error", "message": f"Файл {notebook_path} не найден"}, ensure_ascii=False)
    try:
        res = export_notebook(notebook_path, output_path=output_path, use_hidden_dir=use_hidden_dir)
        return json.dumps({"status": "success", "data": res}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

@mcp.tool()
def nb_import(exported_py_path: str, notebook_path: str = None, force: bool = False, validate_syntax: bool = True) -> str:
    """
    Надежно импортирует изменения из Python-файла (_exported.py) обратно в Jupyter Notebook (.ipynb).
    Включает:
    - Контроль версий по SHA256 (предотвращает случайную перезапись параллельных правок в Jupyter)
    - AST-валидацию синтаксиса Python во всех кодовых ячейках
    - Автоматическое создание бэкапа в .nbexport/ (.nbexport/<name>.ipynb.bak)
    - Атомарную запись через временный файл
    - Сохранение аутпутов неизмененных ячеек

    Args:
        exported_py_path: Путь к экспортированному .py файлу (в т.ч. в папке .nbexport/).
        notebook_path: Опциональный путь к .ipynb (если не указан, определяется автоматически).
        force: Перезаписать .ipynb даже при несовпадении хэша SHA-256.
        validate_syntax: Проверять ли синтаксис кода ячеек перед сохранением.
    """
    if not os.path.exists(exported_py_path):
        return json.dumps({"status": "error", "message": f"Файл {exported_py_path} не найден"}, ensure_ascii=False)
    try:
        res = import_to_notebook(
            exported_py_path,
            notebook_path=notebook_path,
            force=force,
            validate_syntax=validate_syntax
        )
        return json.dumps(res, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

@mcp.tool()
def nb_read(notebook_path: str) -> str:
    """
    Возвращает чистое строковое представление ячеек и выводов ноутбука без создания файлов на диске.
    Идеально для быстрого чтения и ответов на вопросы пользователя по ноутбуку.

    Args:
        notebook_path: Путь к файлу .ipynb.
    """
    if not os.path.exists(notebook_path):
        return f"Ошибка: файл {notebook_path} не найден"
    try:
        return get_clean_text(notebook_path)
    except Exception as e:
        return f"Ошибка чтения ноутбука: {e}"

@mcp.tool()
def notebook_run_cell(
    notebook_path: str,
    code: str = None,
    cell_id: str = None,
    env_name: str = None,
    timeout: int = 60
) -> str:
    """
    Запускает код или конкретную ячейку в сессии ядра (Headless Kernel Session) данного ноутбука.
    Перехватывает stdout, stderr, результаты выражений и изображения (сохраняются через AssetManager).

    Args:
        notebook_path: Путь к файлу .ipynb.
        code: Python-код для выполнения. Если не указан, код будет взят из ячейки с cell_id.
        cell_id: Опциональный ID ячейки. Если указан, результаты выполнения автоматически запишутся в .ipynb.
        env_name: Имя Conda-окружения/ядра (например, 'llm_env', 'ml_base', 'python3'). По умолчанию из kernelspec ноутбука.
        timeout: Таймаут выполнения в секундах (по умолчанию 60).
    """
    if not os.path.exists(notebook_path):
        return json.dumps({"status": "error", "message": f"Файл {notebook_path} не найден"}, ensure_ascii=False)

    # Если code не передан, ищем его в ячейке ноутбука
    if not code and cell_id:
        try:
            with open(notebook_path, 'r', encoding='utf-8') as f:
                nb = json.load(f)
            for c in nb.get('cells', []):
                if c.get('id') == cell_id:
                    src = c.get('source', [])
                    code = "".join(src) if isinstance(src, list) else str(src)
                    break
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Не удалось прочитать ячейку {cell_id}: {e}"}, ensure_ascii=False)

    if not code:
        return json.dumps({"status": "error", "message": "Не указан ни code, ни существующий cell_id"}, ensure_ascii=False)

    try:
        res = kernel_manager.execute_code(
            notebook_path=notebook_path,
            code=code,
            timeout=timeout,
            env_name=env_name,
            save_to_cell_id=cell_id
        )
        return json.dumps(res, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

@mcp.tool()
def notebook_get_state(notebook_path: str) -> str:
    """
    Возвращает статус ядра ноутбука, список активных переменных (через %whos) и статистику ячеек.

    Args:
        notebook_path: Путь к файлу .ipynb.
    """
    if not os.path.exists(notebook_path):
        return json.dumps({"status": "error", "message": f"Файл {notebook_path} не найден"}, ensure_ascii=False)
    try:
        res = kernel_manager.get_state(notebook_path)
        return json.dumps(res, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

@mcp.tool()
def notebook_restart_kernel(notebook_path: str, env_name: str = None) -> str:
    """
    Перезапускает сессию ядра для указанного ноутбука (с опциональным переключением на другое Conda-окружение).

    Args:
        notebook_path: Путь к файлу .ipynb.
        env_name: Новое имя ядра/окружения (например, 'llm_env', 'ml_base', 'python3').
    """
    if not os.path.exists(notebook_path):
        return json.dumps({"status": "error", "message": f"Файл {notebook_path} не найден"}, ensure_ascii=False)
    try:
        res = kernel_manager.restart_kernel(notebook_path, env_name=env_name)
        return json.dumps(res, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

@mcp.tool()
def notebook_interrupt(notebook_path: str) -> str:
    """
    Посылает сигнал прерывания (SIGINT) ядру, если выполнение зависло или выполняется слишком долго.

    Args:
        notebook_path: Путь к файлу .ipynb.
    """
    try:
        res = kernel_manager.interrupt_kernel(notebook_path)
        return json.dumps(res, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def main():
    mcp.run()

if __name__ == "__main__":
    main()
