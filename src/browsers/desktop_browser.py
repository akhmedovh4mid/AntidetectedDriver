import time
import logging

from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright

from src.models.location_data import LocationData


class PlaywrightDesktopBrowser():
    def __init__(
        self,
        proxy: bool = True,
        headless: bool = False,
        log_level: str = "INFO",
        location: Optional[LocationData] = None,
    ) -> None:
        self.proxy = proxy
        self.headless = headless
        self.location = location
        self.device: str = 'Desktop Chrome'

        self.log_path = Path("src/logs/playwright_desktop_browser.log")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        self.log_level = log_level
        self.logger = logging.getLogger(self.__class__.__name__)
        self._setup_logging()

        self.browser = None
        self.context = None
        self.page = None

    def __enter__(self) -> 'PlaywrightDesktopBrowser':
        """Поддержка контекстного менеджера (with) - автоматический запуск браузера"""
        self.logger.debug("Вход в контекстный менеджер - запуск мобильного браузера")
        self.launch()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Автоматическое закрытие при выходе из контекста"""
        self.logger.debug("Выход из контекстного менеджера - закрытие мобильного браузера")
        self.close()

    def _setup_logging(self) -> None:
        """Настройка системы логирования с кастомным форматированием"""
        level = getattr(logging, self.log_level.upper(), logging.INFO)
        self.logger.setLevel(level)

        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        file_handler = logging.FileHandler(self.log_path)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        self.logger.propagate = False

    def launch(self) -> None:
        """Запуск мобильного браузера с настройками устройства и прокси"""
        self.logger.info(f"Запуск мобильного браузера с устройством: {self.device}")
        try:
            self.playwright = sync_playwright().start()
            device = self.playwright.devices[self.device]

            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                ignore_default_args=['--enable-automation'],
                chromium_sandbox=False,
                proxy={'server': "socks5://127.0.0.1:2080"} if self.proxy else None,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-automation',
                ]
            )

            if self.location != None:
                self.logger.debug(f"Создание мобильного контекста с локалью: {self.locale}, геолокацией и почтовым индексом")
                self.context = self.browser.new_context(
                    **device,
                    color_scheme="light",
                    locale=self.location.locale,
                    geolocation={"latitude": self.location.lantitude, "longitude": self.location.longitude},
                    permissions=["geolocation"],
                    extra_http_headers={
                        "X-Postal-Code": self.location.zipcode
                    },
                    timezone_id=self.location.timezone
                )
            else:
                self.logger.debug("Создание мобильного контекста без локали/геолокации")
                self.context = self.browser.new_context(**device)

            self.page = self.context.new_page()
            self.page.emulate_media(color_scheme='light')

            self.logger.info("Браузер успешно запущен")
        except Exception as e:
            self.logger.error(f"Ошибка при запуске браузера: {str(e)}")
            raise

    def goto(self, url: str, delay: float = 0) -> None:
        """
        Переход по указанному URL с возможной задержкой
        """
        self.logger.info(f"Переход по URL: {url}")
        try:
            self.page.goto(url)

            if delay > 0:
                self.logger.debug(f"Ожидание {delay} секунд после загрузки страницы")
                time.sleep(delay)
        except Exception as e:
            self.logger.error(f"Ошибка при переходе по URL {url}: {str(e)}")
            raise

    def close(self) -> None:
        """Закрытие браузера и освобождение ресурсов"""
        self.logger.info("Закрытие мобильного браузера и освобождение ресурсов")
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            self.logger.info("Мобильный браузер успешно закрыт")
        except Exception as e:
            self.logger.error(f"Ошибка при закрытии мобильного браузера: {str(e)}")
            raise
