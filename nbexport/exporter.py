import json
import datetime
import os
import uuid
from .utils import clean_ansi, calculate_sha256
from .assets import AssetManager

def extract_exec_time(cell):
    meta = cell.get('metadata', {})
    
    # 1. Look for VS Code format
    vscode = meta.get('vscode', {})
    if 'end_execution_time' in vscode and 'start_execution_time' in vscode:
        end_str = vscode['end_execution_time'].replace('Z', '+00:00')
        start_str = vscode['start_execution_time'].replace('Z', '+00:00')
        try:
            diff = datetime.datetime.fromisoformat(end_str) - datetime.datetime.fromisoformat(start_str)
            return diff.total_seconds()
        except Exception:
            pass
            
    # 2. Look for Jupyter ExecuteTime extension
    exec_time = meta.get('ExecuteTime', {})
    if 'end_time' in exec_time and 'start_time' in exec_time:
        end_str = exec_time['end_time'].replace('Z', '+00:00')
        start_str = exec_time['start_time'].replace('Z', '+00:00')
        try:
            diff = datetime.datetime.fromisoformat(end_str) - datetime.datetime.fromisoformat(start_str)
            return diff.total_seconds()
        except Exception:
            pass
            
    # 3. Look for standard iopub timestamps
    execution = meta.get('execution', {})
    if 'iopub.status.idle' in execution and 'iopub.execute_input' in execution:
        end_str = execution['iopub.status.idle'].replace('Z', '+00:00')
        start_str = execution['iopub.execute_input'].replace('Z', '+00:00')
        try:
            diff = datetime.datetime.fromisoformat(end_str) - datetime.datetime.fromisoformat(start_str)
            return diff.total_seconds()
        except Exception:
            pass
            
    return None

def export_notebook(notebook_path: str, output_path: str = None) -> bool:
    if not output_path:
        output_path = os.path.splitext(notebook_path)[0] + '_exported.py'

    try:
        with open(notebook_path, 'r', encoding='utf-8') as f:
            nb = json.load(f)
    except Exception as e:
        raise Exception(f"Ошибка чтения {notebook_path}: {e}")
        
    assets = AssetManager(notebook_path)
    assets.prepare_directory()
    
    sha256_hash = calculate_sha256(notebook_path)
    cells = nb.get('cells', [])
    
    # Ensure every cell has an ID (nbformat 4.5+)
    nb_modified_for_ids = False
    for cell in cells:
        if 'id' not in cell or not cell['id']:
            cell['id'] = uuid.uuid4().hex[:8]
            nb_modified_for_ids = True
            
    if nb_modified_for_ids:
        try:
            with open(notebook_path, 'w', encoding='utf-8') as f:
                json.dump(nb, f, indent=1, ensure_ascii=False)
            sha256_hash = calculate_sha256(notebook_path)
        except Exception:
            pass
    
    num_markdown = sum(1 for c in cells if c.get('cell_type') == 'markdown')
    num_code = sum(1 for c in cells if c.get('cell_type') == 'code')
    
    lines = []
    
    # 1. HEADER
    lines.append(f"# --- Notebook: {os.path.basename(notebook_path)} ---")
    lines.append(f"# Exported: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"# SHA256:   {sha256_hash}")
    lines.append(f"# Cells:    {len(cells)} (Markdown: {num_markdown}, Code: {num_code})")
    lines.append("")
    
    # 2. CONTENTS
    lines.append("# --- CONTENTS ---")
    lines.append("")
    
    for i, cell in enumerate(cells, 1):
        ctype = cell.get('cell_type', 'code')
        cell_id = cell.get('id', '')
        source = cell.get('source', [])
        title = ""
        if source:
            first_line = source[0] if isinstance(source, list) else source.split('\n')[0]
            title = first_line.strip().replace('#', '').strip()
            if len(title) > 45:
                title = title[:42] + "..."
        if not title:
            title = "Empty"
        
        type_str = "Markdown" if ctype == 'markdown' else "Code"
        lines.append(f"# Cell {i:<3} {type_str:<10} [id:{cell_id}] {title}")
    
    lines.append("")
    lines.append("")
    
    # 3. CELLS
    for i, cell in enumerate(cells, 1):
        ctype = cell.get('cell_type', 'code')
        cell_id = cell.get('id', uuid.uuid4().hex[:8])
        source = cell.get('source', [])
        
        lines.append(f"# %% [Cell {i} | {ctype.capitalize()} | id:{cell_id}]")
        
        if ctype == 'code':
            exec_time_sec = extract_exec_time(cell)
            if exec_time_sec is not None:
                lines.append(f"# Execution time: {exec_time_sec:.2f} sec")
        
        source_lines = source if isinstance(source, list) else source.split('\n')
        
        if ctype == 'markdown':
            for line in source_lines:
                text = line.rstrip('\r\n')
                for part in text.split('\n'):
                    lines.append(f"# {part}")
        elif ctype == 'code':
            for line in source_lines:
                lines.append(line.rstrip('\r\n'))
            lines.append("")
            
            outputs = cell.get('outputs', [])
            if outputs:
                plot_idx = 1
                for out in outputs:
                    out_type = out.get('output_type', 'output')
                    lines.append(f"# --- OUTPUT ({out_type}) ---")
                    
                    if out_type == 'stream':
                        text_arr = out.get('text', [])
                        text = "".join(text_arr) if isinstance(text_arr, list) else str(text_arr)
                        text = clean_ansi(text)
                        
                        out_lines = text.split('\n')
                        if len(out_lines) > 100:
                            saved_path = assets.save_text(i, text)
                            lines.append(f"# Output truncated (100 of {len(out_lines)} lines)")
                            lines.append(f"# Full output: {saved_path}")
                            for l in out_lines[:100]:
                                lines.append(f"# {l}")
                        else:
                            for l in out_lines:
                                lines.append(f"# {l}")
                                
                    elif out_type in ['execute_result', 'display_data']:
                        data = out.get('data', {})
                        if 'image/png' in data:
                            saved_path = assets.save_image(i, plot_idx, data['image/png'])
                            lines.append(f"# Figure: {saved_path}")
                            plot_idx += 1
                        
                        if 'text/plain' in data:
                            text_arr = data['text/plain']
                            text = "".join(text_arr) if isinstance(text_arr, list) else str(text_arr)
                            text = clean_ansi(text)
                            out_lines = text.split('\n')
                            if len(out_lines) > 100:
                                saved_path = assets.save_text(i, text)
                                lines.append(f"# Output truncated (100 of {len(out_lines)} lines)")
                                lines.append(f"# Full output: {saved_path}")
                                for l in out_lines[:100]:
                                    lines.append(f"# {l}")
                            else:
                                for l in out_lines:
                                    lines.append(f"# {l}")
                                    
                    elif out_type == 'error':
                        lines.append(f"# ERROR: {out.get('ename')} - {out.get('evalue')}")
                        traceback = out.get('traceback', [])
                        text = "\n".join(traceback)
                        text = clean_ansi(text)
                        for l in text.split('\n'):
                            lines.append(f"# {l}")
                            
                    lines.append("# --- END OUTPUT ---")
        
        lines.append("")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
        
    return True
