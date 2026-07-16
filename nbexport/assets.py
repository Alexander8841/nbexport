import os
import shutil
import base64

class AssetManager:
    def __init__(self, notebook_path: str):
        self.notebook_path = notebook_path
        self.notebook_dir = os.path.dirname(os.path.abspath(notebook_path))
        nb_name = os.path.splitext(os.path.basename(notebook_path))[0]
        self.assets_dir_name = f"{nb_name}_exported_assets"
        self.assets_dir_path = os.path.join(self.notebook_dir, self.assets_dir_name)
        self.has_assets = False

    def prepare_directory(self):
        """Очищает папку перед новым экспортом и создает .gitignore."""
        if os.path.exists(self.assets_dir_path):
            try:
                shutil.rmtree(self.assets_dir_path)
            except Exception:
                pass # Игнорируем ошибки удаления, если файл занят
        
    def _ensure_dir_exists(self):
        if not self.has_assets:
            os.makedirs(self.assets_dir_path, exist_ok=True)
            gitignore_path = os.path.join(self.assets_dir_path, '.gitignore')
            with open(gitignore_path, 'w', encoding='utf-8') as f:
                f.write("*\n")
            self.has_assets = True

    def save_image(self, cell_idx: int, plot_idx: int, base64_data: str) -> str:
        """Сохраняет изображение и возвращает относительный путь."""
        self._ensure_dir_exists()
        filename = f"cell_{cell_idx:02d}_plot_{plot_idx}.png"
        filepath = os.path.join(self.assets_dir_path, filename)
        
        try:
            image_data = base64.b64decode(base64_data)
            with open(filepath, 'wb') as f:
                f.write(image_data)
        except Exception:
            pass
            
        return f"{self.assets_dir_name}/{filename}"

    def save_text(self, cell_idx: int, text_content: str) -> str:
        """Сохраняет длинный текст и возвращает относительный путь."""
        self._ensure_dir_exists()
        filename = f"cell_{cell_idx:02d}_output.txt"
        filepath = os.path.join(self.assets_dir_path, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text_content)
        except Exception:
            pass
            
        return f"{self.assets_dir_name}/{filename}"
