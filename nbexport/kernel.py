import os
import json
import time
import atexit
import jupyter_client
from .assets import AssetManager
from .utils import clean_ansi

# Предотвращение конфликта нескольких OpenMP библиотек на Windows (PyTorch/MKL)
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

class NotebookKernelManager:
    """
    Управляет сессиями Jupyter-ядер (Headless Kernel Sessions) для каждого ноутбука.
    Поддерживает таймауты, перехват stdout/stderr/результатов, сохранение изображений
    через AssetManager и работу с разными Conda-окружениями.
    """
    def __init__(self):
        # notebook_abs_path -> (KernelManager, KernelClient, kernel_name)
        self._kernels = {}
        atexit.register(self.shutdown_all)

    def get_available_kernels(self) -> dict[str, str]:
        """Возвращает доступные jupyter kernelspecs (имя -> путь к спецификации)."""
        try:
            return jupyter_client.kernelspec.find_kernel_specs()
        except Exception:
            return {}

    def resolve_kernel_name(self, notebook_path: str, env_name: str = None) -> str:
        """Определяет подходящее имя ядра на основе переданного env_name или метаданных ноутбука."""
        specs = self.get_available_kernels()
        
        if env_name:
            clean_env = env_name.strip()
            # Прямое совпадение
            if clean_env in specs:
                return clean_env
            # Регистронезависимое совпадение
            for name in specs:
                if name.lower() == clean_env.lower():
                    return name
            # Если передали путь к conda env
            base_env = os.path.basename(clean_env.rstrip("/\\"))
            for name in specs:
                if name.lower() == base_env.lower():
                    return name
            raise ValueError(
                f"Окружение/ядро '{env_name}' не найдено в Jupyter kernelspecs. "
                f"Доступные ядра: {list(specs.keys())}"
            )

        # Пытаемся взять из метаданных ноутбука
        if os.path.exists(notebook_path):
            try:
                with open(notebook_path, 'r', encoding='utf-8') as f:
                    nb = json.load(f)
                meta_spec = nb.get('metadata', {}).get('kernelspec', {}).get('name')
                if meta_spec and meta_spec in specs:
                    return meta_spec
            except Exception:
                pass

        if 'python3' in specs:
            return 'python3'
        if specs:
            return next(iter(specs.keys()))
        return 'python3'

    def get_or_start_kernel(self, notebook_path: str, env_name: str = None) -> tuple[jupyter_client.KernelManager, jupyter_client.KernelClient]:
        """Получает активную сессию ядра или запускает новую."""
        key = os.path.abspath(notebook_path)
        target_kernel = self.resolve_kernel_name(notebook_path, env_name)
        
        if key in self._kernels:
            km, kc, current_kernel = self._kernels[key]
            if km.is_alive():
                # Если запрошено конкретное окружение и оно отличается от текущего - перезапускаем
                if env_name and current_kernel != target_kernel:
                    self.shutdown_kernel(notebook_path)
                else:
                    return km, kc
            else:
                self.shutdown_kernel(notebook_path)

        # Стартуем новое ядро
        working_dir = os.path.dirname(key)
        km = jupyter_client.KernelManager(kernel_name=target_kernel)
        km.start_kernel(cwd=working_dir)
        kc = km.client()
        kc.start_channels()
        kc.wait_for_ready(timeout=30)
        self._kernels[key] = (km, kc, target_kernel)
        return km, kc

    def execute_code(
        self,
        notebook_path: str,
        code: str,
        timeout: int = 60,
        env_name: str = None,
        save_to_cell_id: str = None
    ) -> dict:
        """
        Выполняет код в ядре ноутбука, собирает все выводы и сохраняет графики.
        Если указан save_to_cell_id, обновляет outputs и execution_count ячейки в .ipynb.
        """
        km, kc = self.get_or_start_kernel(notebook_path, env_name)
        msg_id = kc.execute(code)
        
        stdout_parts = []
        stderr_parts = []
        results = []
        saved_images = []
        error_info = None
        exec_count = None
        
        # Для сохранения в формате nbformat outputs
        nb_outputs = []
        assets = AssetManager(notebook_path)
        plot_counter = 1

        deadline = time.time() + timeout
        completed = False

        while time.time() < deadline and not completed:
            try:
                msg = kc.get_iopub_msg(timeout=1)
            except Exception:
                continue

            if msg.get('parent_header', {}).get('msg_id') != msg_id:
                continue

            mtype = msg.get('msg_type')
            content = msg.get('content', {})

            if mtype == 'execute_input':
                exec_count = content.get('execution_count')

            elif mtype == 'stream':
                name = content.get('name', 'stdout')
                text = content.get('text', '')
                clean_text = clean_ansi(text)
                if name == 'stdout':
                    stdout_parts.append(clean_text)
                else:
                    stderr_parts.append(clean_text)
                    
                nb_outputs.append({
                    "name": name,
                    "output_type": "stream",
                    "text": text
                })

            elif mtype == 'execute_result':
                data = content.get('data', {})
                exec_count = content.get('execution_count', exec_count)
                if 'text/plain' in data:
                    results.append(clean_ansi(data['text/plain']))
                nb_outputs.append({
                    "data": data,
                    "execution_count": exec_count,
                    "metadata": content.get('metadata', {}),
                    "output_type": "execute_result"
                })

            elif mtype == 'display_data':
                data = content.get('data', {})
                if 'image/png' in data:
                    saved_path = assets.save_image(0, plot_counter, data['image/png'])
                    saved_images.append(saved_path)
                    plot_counter += 1
                if 'text/plain' in data and 'image/png' not in data:
                    results.append(clean_ansi(data['text/plain']))
                nb_outputs.append({
                    "data": data,
                    "metadata": content.get('metadata', {}),
                    "output_type": "display_data"
                })

            elif mtype == 'error':
                ename = content.get('ename', '')
                evalue = content.get('evalue', '')
                traceback = content.get('traceback', [])
                clean_tb = [clean_ansi(l) for l in traceback]
                error_info = {
                    "ename": ename,
                    "evalue": evalue,
                    "traceback": clean_tb
                }
                nb_outputs.append({
                    "ename": ename,
                    "evalue": evalue,
                    "output_type": "error",
                    "traceback": traceback
                })

            elif mtype == 'status':
                if content.get('execution_state') == 'idle':
                    completed = True

        if not completed:
            self.interrupt_kernel(notebook_path)
            error_info = {
                "ename": "TimeoutError",
                "evalue": f"Ячейка превысила лимит времени выполнения ({timeout} сек)",
                "traceback": []
            }

        # Если задан save_to_cell_id - обновляем ячейку в файле .ipynb
        if save_to_cell_id and os.path.exists(notebook_path):
            try:
                with open(notebook_path, 'r', encoding='utf-8') as f:
                    nb = json.load(f)
                updated = False
                for cell in nb.get('cells', []):
                    if cell.get('id') == save_to_cell_id and cell.get('cell_type') == 'code':
                        cell['outputs'] = nb_outputs
                        cell['execution_count'] = exec_count
                        updated = True
                        break
                if updated:
                    tmp_path = f"{notebook_path}.tmp_run"
                    with open(tmp_path, 'w', encoding='utf-8') as f:
                        json.dump(nb, f, indent=1, ensure_ascii=False)
                    os.replace(tmp_path, notebook_path)
            except Exception as e:
                stderr_parts.append(f"\n[Warning: Не удалось сохранить вывод в ячейку .ipynb: {e}]")

        return {
            "status": "error" if error_info else "ok",
            "stdout": "".join(stdout_parts),
            "stderr": "".join(stderr_parts),
            "results": results,
            "saved_images": saved_images,
            "error": error_info,
            "execution_count": exec_count
        }

    def get_state(self, notebook_path: str) -> dict:
        """Возвращает информацию о текущем ядре и объявленных переменных (%whos)."""
        key = os.path.abspath(notebook_path)
        is_active = key in self._kernels and self._kernels[key][0].is_alive()
        kernel_name = self._kernels[key][2] if is_active else None

        whos_text = ""
        if is_active:
            res = self.execute_code(notebook_path, "%whos", timeout=10)
            whos_text = res.get('stdout', '')

        # Краткая статистика по ячейкам ноутбука
        cell_stats = {"total": 0, "code": 0, "markdown": 0}
        if os.path.exists(notebook_path):
            try:
                with open(notebook_path, 'r', encoding='utf-8') as f:
                    nb = json.load(f)
                cells = nb.get('cells', [])
                cell_stats["total"] = len(cells)
                cell_stats["code"] = sum(1 for c in cells if c.get('cell_type') == 'code')
                cell_stats["markdown"] = sum(1 for c in cells if c.get('cell_type') == 'markdown')
            except Exception:
                pass

        return {
            "notebook_path": key,
            "kernel_active": is_active,
            "kernel_name": kernel_name,
            "variables": whos_text.strip(),
            "cell_stats": cell_stats
        }

    def interrupt_kernel(self, notebook_path: str) -> dict:
        """Посылает сигнал прерывания (SIGINT) текущей выполняющейся ячейке."""
        key = os.path.abspath(notebook_path)
        if key in self._kernels:
            km, _, kernel_name = self._kernels[key]
            if km.is_alive():
                km.interrupt_kernel()
                return {"status": "success", "message": f"Ядро {kernel_name} прервано"}
        return {"status": "warning", "message": "Активное ядро для этого ноутбука не найдено"}

    def restart_kernel(self, notebook_path: str, env_name: str = None) -> dict:
        """Перезапускает ядро ноутбука (с опциональной сменой окружения)."""
        self.shutdown_kernel(notebook_path)
        km, _ = self.get_or_start_kernel(notebook_path, env_name)
        return {
            "status": "success",
            "message": f"Ядро успешно перезапущено ({km.kernel_name})",
            "kernel_name": km.kernel_name
        }

    def shutdown_kernel(self, notebook_path: str):
        """Останавливает ядро конкретного ноутбука."""
        key = os.path.abspath(notebook_path)
        if key in self._kernels:
            km, kc, _ = self._kernels.pop(key)
            try:
                kc.stop_channels()
                km.shutdown_kernel(now=True)
            except Exception:
                pass

    def shutdown_all(self):
        """Останавливает все запущенные ядра при завершении работы сервера."""
        for key in list(self._kernels.keys()):
            self.shutdown_kernel(key)

# Глобальный инстанс менеджера ядер
kernel_manager = NotebookKernelManager()
