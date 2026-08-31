import argparse
import os
import glob
from .exporter import export_notebook
from .importer import import_to_notebook
from .watcher import start_watching, find_file_recursively
from .utils import log_success, log_error, log_info

def main_export():
    parser = argparse.ArgumentParser(description="Экспорт Jupyter Notebook (.ipynb) в чистый Python-скрипт с аутпутами.")
    parser.add_argument("-i", "--input", help="Путь или имя файла .ipynb (по умолчанию все .ipynb в текущей папке)")
    parser.add_argument("-o", "--output", help="Путь для сохранения .py файла")
    args = parser.parse_args()

    if args.input:
        resolved, matches = find_file_recursively(args.input)
        if matches:
            log_error(f"Найдено несколько файлов с именем '{args.input}':")
            for m in matches:
                print(f"  • {os.path.relpath(m, '.')}")
            return
        if not resolved:
            log_error(f"Файл '{args.input}' не найден в текущей папке и её подкаталогах.")
            return
            
        try:
            out = args.output if args.output else os.path.splitext(resolved)[0] + '_exported.py'
            export_notebook(resolved, out)
            log_success(f"Экспортирован: {os.path.relpath(resolved, '.')} -> {os.path.relpath(out, '.')}")
        except Exception as e:
            log_error(f"Ошибка экспорта {args.input}", str(e))
    else:
        files = glob.glob("*.ipynb")
        if not files:
            log_info("В текущей папке не найдено файлов .ipynb")
            return
        for f in files:
            try:
                out = os.path.splitext(f)[0] + '_exported.py'
                export_notebook(f, out)
                log_success(f"Экспортирован: {f} -> {out}")
            except Exception as e:
                log_error(f"Ошибка экспорта {f}", str(e))

def main_import():
    parser = argparse.ArgumentParser(description="Обратный импорт из Python-скрипта (_exported.py) в Jupyter Notebook (.ipynb).")
    parser.add_argument("-i", "--input", help="Путь или имя файла _exported.py (по умолчанию все *_exported.py в текущей папке)")
    parser.add_argument("-o", "--output", help="Путь для сохранения .ipynb файла")
    args = parser.parse_args()

    if args.input:
        resolved, matches = find_file_recursively(args.input)
        if matches:
            log_error(f"Найдено несколько файлов с именем '{args.input}':")
            for m in matches:
                print(f"  • {os.path.relpath(m, '.')}")
            return
        if not resolved:
            log_error(f"Файл '{args.input}' не найден в текущей папке и её подкаталогах.")
            return
            
        try:
            out = args.output if args.output else (resolved[:-12] + '.ipynb' if resolved.endswith('_exported.py') else os.path.splitext(resolved)[0] + '.ipynb')
            import_to_notebook(resolved, out)
            log_success(f"Импортирован: {os.path.relpath(resolved, '.')} -> {os.path.relpath(out, '.')}")
        except Exception as e:
            log_error(f"Ошибка импорта {args.input}", str(e))
    else:
        files = glob.glob("*_exported.py")
        if not files:
            log_info("В текущей папке не найдено файлов *_exported.py")
            return
        for f in files:
            try:
                out = f[:-12] + '.ipynb'
                import_to_notebook(f, out)
                log_success(f"Импортирован: {f} -> {out}")
            except Exception as e:
                log_error(f"Ошибка импорта {f}", str(e))

def main_watch():
    parser = argparse.ArgumentParser(description="Фоновый 2-way sync между .ipynb и *_exported.py файлами.")
    parser.add_argument("path", nargs="?", default=None, help="Папка или имя файла для отслеживания")
    parser.add_argument("-i", "--input", help="Конкретный файл (.ipynb или _exported.py) для отслеживания")
    args = parser.parse_args()
    
    target = args.input or args.path or "."
    start_watching(target)
