import argparse
import os
import glob
import time
from .exporter import export_notebook
from .watcher import start_watching
from .utils import log_success, log_error

def main_export():
    parser = argparse.ArgumentParser(description="NBExport - Конвертация Jupyter Notebook в Python скрипт для LLM.")
    parser.add_argument('-i', '--input', type=str, help="Путь к исходному .ipynb файлу или директории. По умолчанию - текущая папка.")
    parser.add_argument('-o', '--output', type=str, help="Путь к результирующему .py файлу (только если конвертируется один файл).")
    args = parser.parse_args()
    
    input_path = args.input or os.getcwd()
    
    if os.path.isdir(input_path):
        notebooks = glob.glob(os.path.join(input_path, '*.ipynb'))
    elif input_path.endswith('.ipynb') and os.path.exists(input_path):
        notebooks = [input_path]
    else:
        notebooks = []
        
    if not notebooks:
        print(f"Не найдено .ipynb файлов по пути: {input_path}")
        return
        
    for nb in notebooks:
        if args.output and len(notebooks) == 1:
            out_file = args.output
        else:
            out_file = os.path.splitext(nb)[0] + '_exported.py'
            
        try:
            start = time.time()
            export_notebook(nb, out_file)
            duration = time.time() - start
            log_success(f"{os.path.basename(nb)} -> {os.path.basename(out_file)}", duration)
        except Exception as e:
            log_error(f"{os.path.basename(nb)}", str(e))

def main_watch():
    parser = argparse.ArgumentParser(description="NBWatch - Автоматическое слежение и конвертация Jupyter Notebooks.")
    parser.add_argument('path', nargs='?', type=str, default='.', help="Папка для слежения. По умолчанию - текущая папка.")
    args = parser.parse_args()
    
    start_watching(args.path)

if __name__ == '__main__':
    main_export()
