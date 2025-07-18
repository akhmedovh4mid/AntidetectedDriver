import os
import sys
import logging
import argparse
import subprocess

from typing import List
from pathlib import Path


logging.basicConfig(
    level=logging.INFO,
    format='[%(name)s] [%(levelname)s] - %(message)s'
)
logger = logging.getLogger(name="start")

VENV_NAME = ".venv"

with open("requirements.txt", "r") as file:
    REQUIREMENTS = file.read().split("\n")

REQUIREMENTS = [i for i in REQUIREMENTS if i]

def create_venv():
    """Создает виртуальное окружение"""
    try:
        # Проверяем, не существует ли уже venv
        if Path(VENV_NAME).exists():
            logger.warning(f"Виртуальное окружение '{VENV_NAME}' уже существует")
            return True

        # Создаем venv
        logger.info(f"Создаем виртуальное окружение '{VENV_NAME}'...")
        result = subprocess.run(
            [sys.executable, "-m", "venv", VENV_NAME],
            check=True,
            capture_output=True,
            text=True
        )

        logger.debug(f"Вывод создания venv:\n{result.stdout}")
        logger.info("Виртуальное окружение успешно создано")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка при создании venv: {e}")
        logger.error(f"Stderr:\n{e.stderr}")
        return False
    except Exception as e:
        logger.exception(f"Непредвиденная ошибка при создании venv: {e}")
        return False


def install_packages():
    """Устанавливает пакеты в виртуальное окружение"""
    try:
        # Определяем пути
        python_path = Path(VENV_NAME) / ("Scripts" if os.name == "nt" else "bin") / "python"
        pip_path = Path(VENV_NAME) / ("Scripts" if os.name == "nt" else "bin") / "pip"

        # Особое обновление pip для Windows
        logger.info("Особое обновление pip...")
        update_cmd = [str(python_path), "-m", "pip", "install", "--upgrade", "pip"]
        update_result = subprocess.run(
            update_cmd,
            capture_output=True,
            text=True
        )

        if update_result.returncode != 0:
            logger.warning(f"Предупреждение при обновлении pip: {update_result.stderr}")
        else:
            logger.info("Pip успешно обновлен")
            logger.debug(f"Вывод обновления:\n{update_result.stdout}")

        # Установка основных пакетов
        logger.info("Устанавливаем основные пакеты...")
        for package in REQUIREMENTS:
            logger.info(f"Устанавливаю {package}...")
            install_cmd = [str(python_path), "-m", "pip", "install", package]
            install_result = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True
            )

            if install_result.returncode != 0:
                logger.error(f"Ошибка установки {package}: {install_result.stderr}")
            else:
                logger.info(f"{package} успешно установлен")

        return True

    except Exception as e:
        logger.exception(f"Непредвиденная ошибка при установке пакетов: {e}")
        return False


def verify_installation() -> bool:
    """Проверяет успешность установки пакетов"""
    try:
        pip_path = Path(VENV_NAME) / ("Scripts" if os.name == "nt" else "bin") / "pip"
        list_result = subprocess.run(
            [str(pip_path), "list"],
            capture_output=True,
            text=True
        )

        installed_packages = list_result.stdout.lower()
        missing_packages = [
            pkg for pkg in REQUIREMENTS
            if pkg.split('>')[0].split('<')[0].split('=')[0].lower() not in installed_packages
        ]

        if missing_packages:
            logger.warning(f"Не удалось установить: {', '.join(missing_packages)}")
            return False

        logger.info("Все пакеты успешно установлены и проверены")
        return True
    except Exception as e:
        logger.exception(f"Ошибка при проверке пакетов: {e}")
        return False


def build():
    """Основная функция"""
    # configure_logging(level=logging.DEBUG)

    logger.info("=== Начало настройки окружения ===")

    if not create_venv():
        logger.error("Создание venv завершилось с ошибкой")
        sys.exit(1)

    if not install_packages():
        logger.error("Установка пакетов завершилась с ошибкой")
        sys.exit(1)

    if not verify_installation():
        logger.warning("Некоторые пакеты не установились корректно")

    logger.info("\nНастройка завершена!")
    logger.info(f"Активируйте окружение командой:")
    logger.info(f"  Windows:  {VENV_NAME}\\Scripts\\activate")
    logger.info(f"  Linux/Mac:  source {VENV_NAME}/bin/activate")

def parse_args():
    parser = argparse.ArgumentParser(description="Настройка параметров парсинга")

    parser.add_argument(
        "--excel_path",
        "-e",
        type=str,
        required=True,
        help='Путь к Excel файлу с исходными данными'
    )

    return parser.parse_args()

def activate_and_run():
    # Определяем пути
    venv_path = Path(".venv")
    main_script = Path("main.py")

    args = parse_args()

    # Проверяем существование виртуального окружения
    if not venv_path.exists():
        build()

    # Проверяем существование main.py
    if not main_script.exists():
        print("Ошибка: Файл main.py не найден!")
        sys.exit(1)

    # Команда активации в зависимости от ОС
    if os.name == 'nt':  # Windows
        activate_script = venv_path / "Scripts" / "activate.bat"
        command = f'call "{activate_script}" && python {main_script} --excel_path {args.excel_path}'
    else:  # Linux/Mac
        activate_script = venv_path / "bin" / "activate"
        command = f'source "{activate_script}" && python3 {main_script} --excel_path {args.excel_path}'

    # Запускаем
    try:
        print(f"Активируем окружение и запускаем {main_script}...")
        if os.name == 'nt':
            subprocess.run(command, shell=True, check=True)
        else:
            subprocess.run(['/bin/bash', '-c', command], check=True)

    except KeyboardInterrupt as e:
        return

    except subprocess.CalledProcessError as e:
        print(f"Ошибка при запуске: {e}")
        sys.exit(1)

if __name__ == "__main__":
    activate_and_run()


