import json
import re
import os
import uuid

CELL_HEADER_PATTERN = re.compile(
    r'^#\s*%%\s*\[?(?:Cell\s+\d+\s*\|\s*)?(Markdown|Code|markdown|code)(?:\s*\|\s*(?:id:)?([a-zA-Z0-9_-]+))?\]?',
    re.IGNORECASE
)

# Alternative simple format: # %% [code:id] or # %% [markdown:id]
ALT_CELL_HEADER_PATTERN = re.compile(
    r'^#\s*%%\s*\[?(markdown|code|Markdown|Code):([a-zA-Z0-9_-]+)\]?',
    re.IGNORECASE
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
                # Trim trailing blank lines
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
            # Remove leading '# ' or '#'
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


def import_to_notebook(py_path: str, notebook_path: str = None) -> bool:
    """
    Imports changes from an exported .py script back into the .ipynb notebook.
    Preserves notebook metadata and unedited cell outputs.
    """
    if not notebook_path:
        if py_path.endswith('_exported.py'):
            notebook_path = py_path[:-12] + '.ipynb'
        elif py_path.endswith('_sync.py'):
            notebook_path = py_path[:-8] + '.ipynb'
        elif py_path.endswith('.py'):
            notebook_path = os.path.splitext(py_path)[0] + '.ipynb'
            
    if not os.path.exists(py_path):
        raise FileNotFoundError(f"Файл {py_path} не найден.")
        
    with open(py_path, 'r', encoding='utf-8') as f:
        py_content = f.read()
        
    parsed_cells = parse_exported_py(py_content)
    if not parsed_cells:
        raise ValueError(f"Не удалось извлечь ячейки из {py_path}. Проверьте наличие маркеров # %%.")
        
    # Read existing notebook or create new structure
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
    for parsed in parsed_cells:
        cid = parsed['id']
        ctype = parsed['cell_type']
        
        # Prepare source as list of strings with trailing newline for nbformat
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
    
    with open(notebook_path, 'w', encoding='utf-8') as f:
        json.dump(existing_nb, f, indent=1, ensure_ascii=False)
        
    return True
