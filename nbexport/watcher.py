import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from .exporter import export_notebook
from .utils import log_info, log_success, log_error, calculate_sha256

class NotebookHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_modified = {}
        self.hashes = {}
        self.debounce_seconds = 0.5

    def is_ignored(self, path):
        parts = path.split(os.sep)
        ignored = {'.git', '.venv', '__pycache__', '.ipynb_checkpoints', '.vscode', '.idea'}
        return any(p in ignored for p in parts)

    def process(self, event):
        if event.is_directory or not event.src_path.endswith('.ipynb'):
            return
            
        if self.is_ignored(event.src_path):
            return

        current_time = time.time()
        path = event.src_path
        
        if path in self.last_modified:
            if current_time - self.last_modified[path] < self.debounce_seconds:
                return
                
        self.last_modified[path] = current_time
        
        # Debounce sleep to wait for file writing to finish
        time.sleep(self.debounce_seconds)
        
        current_hash = calculate_sha256(path)
        if not current_hash:
            return
            
        if path in self.hashes and self.hashes[path] == current_hash:
            return
            
        self.hashes[path] = current_hash
        
        try:
            start = time.time()
            export_notebook(path)
            duration = time.time() - start
            out_file = os.path.splitext(path)[0] + '_exported.py'
            log_success(f"{os.path.basename(path)} -> {os.path.basename(out_file)}", duration)
        except Exception as e:
            log_error(f"{os.path.basename(path)}", str(e))

    def on_modified(self, event):
        self.process(event)
        
    def on_created(self, event):
        self.process(event)

def start_watching(path: str):
    abs_path = os.path.abspath(path)
    log_info(f"Начинаем слежение за .ipynb файлами в: {abs_path}")
    log_info("Нажмите Ctrl+C для выхода.")
    
    event_handler = NotebookHandler()
    observer = Observer()
    observer.schedule(event_handler, abs_path, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
