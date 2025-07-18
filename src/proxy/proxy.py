import json
import psutil
import logging
import subprocess

from pathlib import Path
from typing import Optional

from src.models.proxy_auth import ProxyAuth
from src.proxy.utils import proxy_config_with_auth, proxy_config_without_auth


class Proxy:
    def __init__(
        self,
        host: str,
        port: int,
        log_level: str = "INFO",
        proxy_auth: Optional[ProxyAuth] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.proxy_auth = proxy_auth
        self.process = None

        self.nekoray_path = Path("src/apps/nekoray/nekobox_core.exe")
        self.config_path = Path("src/configs/nekoray.json")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        self.log_path = Path("src/logs/proxy.log")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(self.__class__.__name__)
        self._setup_logging(log_level)

    def __enter__(self):
        """Поддержка контекстного менеджера - автоматический запуск при входе"""
        self.logger.debug("Вход в контекстный менеджер - запуск прокси")
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Автоматическая остановка при выходе из контекста"""
        self.logger.debug("Выход из контекстного менеджера - остановка прокси")
        self.stop()

    def _setup_logging(self, level: str):
        """Настройка формата и уровня логирования"""
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(self.log_path)
            ]
        )
        self.logger.setLevel(level)

    def _create_config(self) -> None:
        """Создает конфигурационный файл на диск в формате JSON."""
        self.logger.debug(f"Запись конфигурации в файл {self.config_path}")
        try:
            if self.proxy_auth:
                config = proxy_config_with_auth(
                    self.host, self.port,
                    self.proxy_auth.username,
                    self.proxy_auth.password,
                )
            else:
                config = proxy_config_without_auth(
                    self.host, self.port,
                )

            with self.config_path.open("w", encoding="utf-8") as file:
                json.dump(config, file, indent=2)
            self.logger.debug("Конфигурационный файл успешно записан")

        except Exception as e:
            self.logger.error(f"Ошибка записи конфигурации: {str(e)}")
            raise

    def start(self) -> bool:
        """
        Запускает NekoBox Core процесс
        """
        self.logger.info("Попытка запуска NekoBox Core")
        if self.is_running():
            self.logger.warning("NekoBox уже запущен!")
            return False

        try:
            self._create_config()
            self.process = subprocess.Popen(
                [str(self.nekoray_path.absolute()), "run", "-c", str(self.config_path.absolute())],
                stdout=None,
                stderr=None,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.logger.info(f"NekoBox запущен (PID: {self.process.pid})")
            return True
        except Exception as e:
            self.logger.error(f"Ошибка при запуске NekoBox: {str(e)}")
            return False

    def stop(self) -> bool:
        """
        Останавливает NekoBox Core процесс принудительно, используя kill через psutil
        (включая дочерние процессы)
        """
        self.logger.info("Попытка остановки NekoBox Core (принудительный kill через psutil)")

        if not self.is_running():
            self.logger.warning("NekoBox не запущен!")
            return False

        try:
            # Получаем psutil объект процесса
            ps_process = psutil.Process(self.process.pid)

            # Убиваем весь процесс и его дочерние процессы
            try:
                for child in ps_process.children(recursive=True):
                    try:
                        child.kill()
                        self.logger.debug(f"Убит дочерний процесс PID {child.pid}")
                    except psutil.NoSuchProcess:
                        pass

                ps_process.kill()
                self.logger.debug(f"Отправлен сигнал kill основному процессу PID {ps_process.pid}")

            except psutil.NoSuchProcess:
                self.logger.warning("Процесс уже завершился")
                self.process = None
                return True

            # Проверяем завершение
            try:
                gone, alive = psutil.wait_procs([ps_process], timeout=2)
                if alive:
                    self.logger.warning("Процесс не завершился после kill!")
                else:
                    self.logger.debug("Процесс успешно завершен")
            except psutil.NoSuchProcess:
                pass

            self.process = None
            self.logger.info("NekoBox успешно остановлен (kill через psutil)")
            return True

        except Exception as e:
            self.logger.error(f"Ошибка при остановке NekoBox: {str(e)}")
            return False

    def is_running(self) -> bool:
        """
        Проверяет, запущен ли процесс NekoBox Core (через psutil)
        """
        if self.process is None:
            self.logger.debug("Процесс не инициализирован")
            return False

        try:
            ps_process = psutil.Process(self.process.pid)
            running = ps_process.is_running()
            self.logger.debug(f"Состояние процесса: {'запущен' if running else 'остановлен'}")
            return running
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.logger.debug("Процесс не найден или нет доступа")
            return False
