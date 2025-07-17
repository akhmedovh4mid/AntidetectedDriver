from pathlib import Path
from typing import Dict, Union


class FileManager:
    @staticmethod
    def write_file(data: Dict[str, str], file_path: Union[Path, str]) -> None:
        """Читает файл в формате `key: value` и возвращает словарь."""
        text = "\n".join(f"{key}: {value}" for key, value in data.items())

        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as file:
            file.write(text)
