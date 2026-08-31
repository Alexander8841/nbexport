import time
import os
import sys
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from .exporter import export_notebook
from .importer import import_to_notebook
from .utils import log_info, log_success, log_error, calculate_sha256

class SyncHandler(FileSystemEventHandler):
    """
    Bidirectional Synchronization Handler for Jupyter Notebooks (.ipynb)
    and LLM-friendly Python scripts (_exported.py).
    Includes anti-loop hash verification to guarantee zero cyclic triggers.
    """
    def __init__(self, target_ipynb=None, target_py=None):
        self.last_modified = {}
        self.hashes = {}
        self.expected_synced_hashes = set()
        self.debounce_seconds = 0.4
        self.target_ipynb = os.path.normpath(os.path.abspath(target_ipynb)) if target_ipynb else None
        self.target_py = os.path.normpath(os.path.abspath(target_py)) if target_py else None

    def is_ignored(self, path):
        parts = path.split(os.sep)
        ignored = {'.git', '.venv', 'venv', '__pycache__', '.ipynb_checkpoints', '.vscode', '.idea', '_exported_assets', 'node_modules'}
        return any(p in ignored for p in parts)

    def process(self, event):
        if event.is_directory:
            return
            
        path = os.path.normpath(os.path.abspath(event.src_path))
        if self.is_ignored(path):
            return

        is_ipynb = path.endswith('.ipynb')
        is_exported_py = path.endswith('_exported.py')
        
        if not (is_ipynb or is_exported_py):
            return

        # If single-file mode is active, filter only for target files
        if self.target_ipynb or self.target_py:
            if path != self.target_ipynb and path != self.target_py:
                return

        current_time = time.time()
        if path in self.last_modified:
            if current_time - self.last_modified[path] < self.debounce_seconds:
                return
                
        self.last_modified[path] = current_time
        time.sleep(self.debounce_seconds)
        
        current_hash = calculate_sha256(path)
        if not current_hash:
            return
            
        # If this exact hash was produced by our own sync operation, ignore it
        if current_hash in self.expected_synced_hashes:
            self.expected_synced_hashes.remove(current_hash)
            self.hashes[path] = current_hash
            return

        # If file hasn't changed its content, ignore
        if path in self.hashes and self.hashes[path] == current_hash:
            return
            
        self.hashes[path] = current_hash
        
        # 1. Forward Sync: .ipynb -> _exported.py
        if is_ipynb:
            py_target = self.target_py if self.target_py else (os.path.splitext(path)[0] + '_exported.py')
            try:
                start = time.time()
                export_notebook(path, py_target)
                duration = time.time() - start
                
                new_py_hash = calculate_sha256(py_target)
                if new_py_hash:
                    self.expected_synced_hashes.add(new_py_hash)
                    self.hashes[py_target] = new_py_hash
                    
                log_success(f"[Export] {os.path.basename(path)} -> {os.path.basename(py_target)}", duration)
            except Exception as e:
                log_error(f"[Export Error] {os.path.basename(path)}", str(e))
                
        # 2. Reverse Sync: _exported.py -> .ipynb
        elif is_exported_py:
            ipynb_target = self.target_ipynb if self.target_ipynb else (path[:-12] + '.ipynb')
            try:
                start = time.time()
                import_to_notebook(path, ipynb_target)
                duration = time.time() - start
                
                new_ipynb_hash = calculate_sha256(ipynb_target)
                if new_ipynb_hash:
                    self.expected_synced_hashes.add(new_ipynb_hash)
                    self.hashes[ipynb_target] = new_ipynb_hash
                    
                log_success(f"[Import] {os.path.basename(path)} -> {os.path.basename(ipynb_target)}", duration)
            except Exception as e:
                log_error(f"[Import Error] {os.path.basename(path)}", str(e))

    def on_modified(self, event):
        self.process(event)
        
    def on_created(self, event):
        self.process(event)


def find_file_recursively(target_name: str, root_dir: str = "."):
    """
    Finds a file in root_dir or subdirectories.
    Returns:
      - (str, None): single exact match path
      - (None, list): multiple matches found
      - (None, None): not found
    """
    # 1. Direct check
    if os.path.exists(target_name):
        return (os.path.abspath(target_name), None)
        
    # Check with extensions
    if not (target_name.endswith('.ipynb') or target_name.endswith('.py')):
        for ext in ['.ipynb', '_exported.py', '.py']:
            cand = target_name + ext
            if os.path.exists(cand):
                return (os.path.abspath(cand), None)
                
    # 2. Recursive search in subdirectories
    filename = os.path.basename(target_name).lower()
    matches = []
    
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in {'.git', '.venv', 'venv', '__pycache__', '.ipynb_checkpoints', '.vscode', '.idea', '_exported_assets', 'node_modules'}]
        
        for f in files:
            f_lower = f.lower()
            if f_lower == filename:
                matches.append(os.path.join(root, f))
            elif not (filename.endswith('.ipynb') or filename.endswith('.py')):
                if f_lower in [f"{filename}.ipynb", f"{filename}_exported.py", f"{filename}.py"]:
                    matches.append(os.path.join(root, f))
                    
    # Deduplicate matching pairs (.ipynb vs _exported.py)
    if len(matches) == 1:
        return (os.path.abspath(matches[0]), None)
    elif len(matches) > 1:
        # If matches are just the .ipynb and _exported.py of the same notebook, treat as 1
        stem_map = {}
        for m in matches:
            base = os.path.basename(m)
            if base.endswith('_exported.py'):
                stem = base[:-12]
            elif base.endswith('.ipynb'):
                stem = base[:-6]
            elif base.endswith('.py'):
                stem = base[:-3]
            else:
                stem = base
            parent = os.path.dirname(os.path.abspath(m))
            key = (parent, stem.lower())
            if key not in stem_map:
                stem_map[key] = []
            stem_map[key].append(m)
            
        if len(stem_map) == 1:
            for m in matches:
                if m.endswith('.ipynb'):
                    return (os.path.abspath(m), None)
            return (os.path.abspath(matches[0]), None)
            
        return (None, matches)
    else:
        return (None, None)


def start_watching(target: str = "."):
    # 1. Directory watch mode
    if target == "." or os.path.isdir(target):
        watch_dir = os.path.abspath(target)
        if not os.path.exists(watch_dir):
            log_error(f"Папка не найдена: {target}")
            return
            
        log_info(f"Запущена двусторонняя синхронизация (2-way sync) в: {watch_dir}")
        log_info("Синхронизируются: *.ipynb <---> *_exported.py")
        log_info("Нажмите Ctrl+C для выхода.")
        
        event_handler = SyncHandler()
        observer = Observer()
        try:
            observer.schedule(event_handler, watch_dir, recursive=True)
            observer.start()
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        except Exception as e:
            log_error("Ошибка службы отслеживания", str(e))
        observer.join()
        return

    # 2. Single-file watch mode with smart recursive search
    resolved_path, matches = find_file_recursively(target)
    
    if matches:
        log_error(f"Найдено несколько файлов с именем '{target}':")
        for m in matches:
            print(f"  * {os.path.relpath(m, '.')}")
        print("Пожалуйста, укажите более точный путь к файлу.")
        return
        
    if not resolved_path:
        log_error(f"Файл '{target}' не найден в текущей папке и её подкаталогах.")
        return
        
    # Derive corresponding pair paths
    if resolved_path.endswith('.ipynb'):
        target_ipynb = resolved_path
        target_py = os.path.splitext(resolved_path)[0] + '_exported.py'
    elif resolved_path.endswith('_exported.py'):
        target_py = resolved_path
        target_ipynb = resolved_path[:-12] + '.ipynb'
    else:
        target_py = resolved_path
        target_ipynb = os.path.splitext(resolved_path)[0] + '.ipynb'
        
    rel_ipynb = os.path.relpath(target_ipynb, '.')
    rel_py = os.path.relpath(target_py, '.')
    
    log_info(f"Синхронизация файла: {rel_ipynb} <---> {rel_py}")
    
    # Auto-export if _exported.py is missing
    if os.path.exists(target_ipynb) and not os.path.exists(target_py):
        try:
            export_notebook(target_ipynb, target_py)
            log_success(f"Первичный экспорт: {os.path.basename(target_ipynb)} -> {os.path.basename(target_py)}")
        except Exception as e:
            log_error("Ошибка первичного экспорта", str(e))
            
    # Watch directory of the file (or current directory)
    watch_dir = os.path.dirname(target_ipynb) or "."
    
    log_info("Нажмите Ctrl+C для выхода.")
    
    event_handler = SyncHandler(target_ipynb, target_py)
    observer = Observer()
    try:
        observer.schedule(event_handler, watch_dir, recursive=False)
        observer.start()
        while True:
            time.sleep(1)
        observer.join()
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
    except Exception as e:
        log_error("Ошибка службы отслеживания", str(e))
