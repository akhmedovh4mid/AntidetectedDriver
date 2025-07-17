import shutil

from pathlib import Path


class DirManager:
    @staticmethod
    def move_to_numbered_dir(source_dir: Path, target_dir: Path) -> Path:
        """
        Перемещает все файлы из исходной директории в новую пронумерованную поддиректорию
        внутри целевой директории. Нумерация начинается с 1 и увеличивается на основе
        существующих пронумерованных папок.

        Аргументы:
            source_dir: Путь к исходной директории с файлами для перемещения
            target_dir: Путь к целевой директории для создания пронумерованных поддиректорий

        Возвращает:
            Путь к созданной пронумерованной директории

        Исключения:
            FileNotFoundError: Если исходная директория не существует
            NotADirectoryError: Если исходный путь не является директорией
        """
        # Проверка существования и валидности исходной директории
        if not source_dir.exists():
            raise FileNotFoundError(f"Исходная директория не найдена: {source_dir}")
        if not source_dir.is_dir():
            raise NotADirectoryError(f"Указанный путь не является директорией: {source_dir}")

        # Создаем целевую директорию (если не существует)
        target_dir.mkdir(parents=True, exist_ok=True)

        # Получаем список существующих номеров поддиректорий
        existing_numbers = [
            int(folder.name)
            for folder in target_dir.iterdir()
            if folder.is_dir() and folder.name.isdigit()
        ]

        # Определяем следующий доступный номер
        next_number = max(existing_numbers) + 1 if existing_numbers else 1
        new_folder = target_dir / str(next_number)
        new_folder.mkdir()  # Создаем новую пронумерованную папку

        # Перемещаем все файлы из исходной директории
        for item in source_dir.iterdir():
            if item.is_file():
                shutil.move(str(item), str(new_folder / item.name))

        return new_folder

    @staticmethod
    def clear_directory(folder_path: Path) -> None:
        """
        Полностью очищает указанную папку, удаляя все её содержимое
        (файлы и подпапки), но сохраняет саму папку.

        Args:
            folder_path: Путь к папке, которую нужно очистить

        Raises:
            FileNotFoundError: Если папка не существует
            NotADirectoryError: Если путь ведёт не к папке
        """
        if not folder_path.exists():
            raise FileNotFoundError(f"Папка не найдена: {folder_path}")
        if not folder_path.is_dir():
            raise NotADirectoryError(f"Указанный путь не является папкой: {folder_path}")

        # Удаляем всё содержимое папки
        for item in folder_path.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
