import re
import hashlib
import time
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def clean_ansi(text: str) -> str:
    """Удаляет ANSI escape коды (цвета, форматирование) из текста."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def calculate_sha256(filepath: str) -> str:
    """Вычисляет SHA256 хеш файла."""
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""

def log_success(msg: str, duration: float = None):
    t = time.strftime("%H:%M:%S")
    if duration is not None:
        print(f"[{t}] \u2714 {msg} ({duration:.2f} s)")
    else:
        print(f"[{t}] \u2714 {msg}")

def log_error(msg: str, error: str = ""):
    t = time.strftime("%H:%M:%S")
    print(f"[{t}] \u2716 {msg}")
    if error:
        print(error)

def log_info(msg: str):
    t = time.strftime("%H:%M:%S")
    print(f"[{t}] \u2139 {msg}")
