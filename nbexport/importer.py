import json
import re
import os
import uuid
import ast
import shutil
from .utils import calculate_sha256

CELL_HEADER_PATTERN = re.compile(
    r'^#\s*%%\s*\[?(?:Cell\s+\d+\s*\|\s*)?(Markdown|Code|markdown|code)(?:\s*\|\s*(?:id:)?([a-zA-Z0-9_-]+))?\]?',
    re.IGNORECASE
)

# Alternative simple format: # %% [code:id] or # %% [markdown:id]
ALT_CELL_HEADER_PATTERN = re.compile(
    r'^#\s*%%\s*\[?(markdown|code|Markdown|Code):([a-zA-Z0-9_-]+)\]?',
    re.IGNORECASE
)

SHA256_HEADER_PATTERN = re.compile(
    r'^#\s*SHA256:\s*([a-fA-F0-9]{64})',
    re.MULTILINE
)

def parse_exported_py(py_content: str):
    """
    Parses a python script exported by nbexport back into clean cell structures,
    completely ignoring and stripping all output blocks and metadata comments.
    """
    lines = py_content.splitlines()
    
    parsed_cells = []
    current_cell_type = None
    current_cell_id = None
    current_lines = []
    in_output_block = False
    in_cells_section = False
    
    for line in lines:
        stripped = line.strip()
        
        # Check for cell header
        match = CELL_HEADER_PATTERN.match(stripped)
        if not match:
            match = ALT_CELL_HEADER_PATTERN.match(stripped)
            
        if match:
            # Save previous cell if exists
            if current_cell_type is not None:
                while current_lines and current_lines[-1].strip() == '':
                    current_lines.pop()
                parsed_cells.append({
                    'cell_type': current_cell_type,
                    'id': current_cell_id,
                    'source': current_lines
                })
            
            in_cells_section = True
            in_output_block = False
            ctype_raw = match.group(1).lower()
            current_cell_type = 'markdown' if ctype_raw == 'markdown' else 'code'
            current_cell_id = match.group(2) if match.group(2) else uuid.uuid4().hex[:8]
            current_lines = []
            continue
            
        if not in_cells_section:
            # Skip file header, contents table, etc.
            continue
            
        # Handle output block delimiters
        if stripped.startswith('# --- OUTPUT') or stripped.startswith('# >>> OUTPUT'):
            in_output_block = True
            continue
            
        if stripped.startswith('# --- END OUTPUT') or stripped.startswith('# <<< OUTPUT'):
            in_output_block = False
            continue
            
        if in_output_block:
            continue
            
        # Filter metadata and helper comment lines inside cell
        if stripped.startswith('# Execution time:') or stripped.startswith('# Figure:') or \
           stripped.startswith('# Output truncated') or stripped.startswith('# Full output:'):
            continue
            
        # Content lines
        if current_cell_type == 'markdown':
            if line.startswith('# '):
                current_lines.append(line[2:])
            elif line.startswith('#'):
                current_lines.append(line[1:])
            else:
                current_lines.append(line)
        else: # code
            current_lines.append(line)
            
    # Add final cell
    if current_cell_type is not None:
        while current_lines and current_lines[-1].strip() == '':
            current_lines.pop()
        parsed_cells.append({
            'cell_type': current_cell_type,
            'id': current_cell_id,
            'source': current_lines
        })
        
    return parsed_cells

def resolve_notebook_path(py_path: str, notebook_path: str = None) -> str:
    """Определяет путь к .ipynb файлу по пути к .py скрипту с поддержкой .nbexport/."""
    if notebook_path:
        return os.path.abspath(notebook_path)
        
    norm_py = os.path.abspath(py_path)
    parent_dir, filename = os.path.split(norm_py)
    grandparent_dir, parent_name = os.path.split(parent_dir)
    
    if parent_name == ".nbexport":
        base_name = filename[:-12] if filename.endswith('_exported.py') else os.path.splitext(filename)[0]
        return os.path.join(grandparent_dir, f"{base_name}.ipynb")
        
    if filename.endswith('_exported.py'):
        return os.path.join(parent_dir, filename[:-12] + '.ipynb')
    if filename.endswith('_sync.py'):
        return os.path.join(parent_dir, filename[:-8] + '.ipynb')
        
    return os.path.join(parent_dir, os.path.splitext(filename)[0] + '.ipynb')

def import_to_notebook(py_path: str, notebook_path: str = None, force: bool = False, validate_syntax: bool = True) -> dict:
    """
    Imports changes from an exported .py script back into the .ipynb notebook.
    Features:
    - Version conflict checking via SHA256
    - AST validation for code cells
    - Automatic backup creation in .nbexport/ (.nbexport/<name>.ipynb.bak)
    - Atomic file write via temporary file
    - Preserves outputs and metadata of unedited cells
    """
    notebook_path = resolve_notebook_path(py_path, notebook_path)
            
    if not os.path.exists(py_path):
        raise FileNotFoundError(f"Файл {py_path} не найден.")
        
    with open(py_path, 'r', encoding='utf-8') as f:
        py_content = f.read()

    # 1. SHA256 Conflict Check
    if not force and os.path.exists(notebook_path):
        sha_match = SHA256_HEADER_PATTERN.search(py_content)
        if sha_match:
            expected_sha = sha_match.group(1).lower()
            current_sha = calculate_sha256(notebook_path).lower()
            if current_sha != expected_sha:
                raise ValueError(
                    f"Конфликт версий: файл {notebook_path} был изменен после экспорта. "
                    f"Ожидался хэш {expected_sha[:8]}, текущий {current_sha[:8]}. "
                    f"Используйте force=True для перезаписи."
                )
        
    parsed_cells = parse_exported_py(py_content)
    if not parsed_cells:
        raise ValueError(f"Не удалось извлечь ячейки из {py_path}. Проверьте наличие маркеров # %%.")
        
    # 2. AST Syntax Validation
    if validate_syntax:
        for idx, cell in enumerate(parsed_cells, 1):
            if cell['cell_type'] == 'code':
                code_text = "\n".join(cell['source'])
                try:
                    ast.parse(code_text)
                except SyntaxError as e:
                    raise SyntaxError(
                        f"Синтаксическая ошибка в ячейке {idx} [id:{cell['id']}], "
                        f"строка {e.lineno}: {e.msg}\n{e.text or ''}"
                    )

    # 3. Read existing notebook or create new structure
    existing_nb = None
    if os.path.exists(notebook_path):
        try:
            with open(notebook_path, 'r', encoding='utf-8') as f:
                existing_nb = json.load(f)
        except Exception:
            existing_nb = None
            
    if not existing_nb:
        existing_nb = {
            "cells": [],
            "metadata": {
                "language_info": {"name": "python"},
                "orig_nbformat": 4
            },
            "nbformat": 4,
            "nbformat_minor": 5
        }
        
    existing_cells_map = {}
    for cell in existing_nb.get('cells', []):
        cid = cell.get('id')
        if cid:
            existing_cells_map[cid] = cell
            
    new_cells = []
    num_code = 0
    num_markdown = 0
    
    for parsed in parsed_cells:
        cid = parsed['id']
        ctype = parsed['cell_type']
        if ctype == 'code':
            num_code += 1
        else:
            num_markdown += 1
        
        raw_source_lines = parsed['source']
        formatted_source = [l + '\n' for l in raw_source_lines[:-1]]
        if raw_source_lines:
            formatted_source.append(raw_source_lines[-1])
            
        if cid in existing_cells_map:
            cell = existing_cells_map[cid]
            cell['cell_type'] = ctype
            cell['source'] = formatted_source
            new_cells.append(cell)
        else:
            new_cell = {
                "cell_type": ctype,
                "id": cid,
                "metadata": {},
                "source": formatted_source
            }
            if ctype == 'code':
                new_cell["outputs"] = []
                new_cell["execution_count"] = None
            new_cells.append(new_cell)
            
    existing_nb['cells'] = new_cells
    
    # 4. Atomic write & Backup
    backup_path = None
    if os.path.exists(notebook_path):
        try:
            nb_dir = os.path.dirname(os.path.abspath(notebook_path))
            nb_name = os.path.basename(notebook_path)
            hidden_dir = os.path.join(nb_dir, ".nbexport")
            os.makedirs(hidden_dir, exist_ok=True)
            gitignore_path = os.path.join(hidden_dir, ".gitignore")
            if not os.path.exists(gitignore_path):
                try:
                    with open(gitignore_path, "w", encoding="utf-8") as gf:
                        gf.write("*\n")
                except Exception:
                    pass
            backup_path = os.path.join(hidden_dir, f"{nb_name}.bak")
            shutil.copy2(notebook_path, backup_path)
        except Exception:
            pass
            
    tmp_path = f"{notebook_path}.tmp.{uuid.uuid4().hex[:8]}"
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(existing_nb, f, indent=1, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, notebook_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
                
    return {
        "status": "success",
        "notebook_path": os.path.abspath(notebook_path),
        "backup_path": os.path.abspath(backup_path) if backup_path and os.path.exists(backup_path) else None,
        "cells_count": len(new_cells),
        "code_cells": num_code,
        "markdown_cells": num_markdown
    }
