import os
import time
import shutil
import hashlib
import certifi
import logging
import subprocess

from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Dict, List, Optional, Tuple
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from undetected_chromedriver import Chrome, ChromeOptions
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.models.location_data import LocationData
from src.models.network_resource import NetworkResource


class UndetectedBrowser():
    def __init__(
        self,
        proxy: bool = True,
        headless: bool = False,
        log_level: str = "INFO",
        location: Optional[LocationData] = None
    ) -> None:
        self.proxy = proxy
        self.headless = headless
        self.location = location

        self.log_path = Path("src/logs/undetected_chromedriver.log")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        self.base_dir = Path(__file__).parent.parent.parent
        self.temp_dir = self.base_dir.joinpath("temp")

        self.curl_path = Path("src/apps/curl/bin/curl.exe")

        self.log_level = log_level
        self.logger = logging.getLogger(self.__class__.__name__)
        self._setup_logging()

        self.logger.info("Инициализация UndetectedBrowser")
        self.logger.debug(f"Параметры: proxy={proxy}, headless={headless}")

        self.options: Optional[ChromeOptions] = None
        self.driver: Optional[Chrome] = None
        self.max_workers = 6

    def __enter__(self) -> "UndetectedBrowser":
        """Контекстный менеджер"""
        self.logger.debug("Вход в контекстный менеджер")
        self.launch()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Завершение работы контекста"""
        self.logger.debug("Выход из контекстного менеджера")
        self.close()

        try:
            self.close()
        except Exception as e:
            self.logger.error(f"Ошибка при закрытии браузера в контекстном менеджере: {str(e)}")
            if exc_type is None:
                raise

        if exc_type is not None:
            self.logger.error(
                f"Обнаружено исключение в контексте: {exc_type.__name__}",
                exc_info=(exc_type, exc_val, exc_tb)
            )
            return False

        return True

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

    def _set_geolocation(self) -> None:
        """Изменение настроек геолокации браузера"""
        self.logger.info("Начинаю установку геолокации...")
        try:
            lat = self.location.lantitude
            lon = self.location.longitude
            params = {
                "latitude": float(lat),
                "longitude": float(lon),
                "accuracy": 100
            }
            self.logger.debug(f"Устанавливаю координаты: {lat:.6f}, {lon:.6f}")
            self.driver.execute_cdp_cmd("Page.setGeolocationOverride", params)
            self.logger.info("Геолокация установлена")
        except Exception as e:
            self.logger.error(f"Ошибка установки геолокации: {str(e)}")
            raise

    def _monitoring_enable(self) -> None:
        """
        Включает мониторинг загрузки ресурсов на всех новых страницах.
        Внедряет JavaScript-трекер, который будет выполняться при создании каждой новой страницы.
        """
        script_path = "src/scripts/resource_load_tracker.js"
        self.logger.info(f"Включение мониторинга ресурсов (скрипт: {script_path})")

        try:
            self.logger.debug("Загрузка скрипта мониторинга")
            with open(script_path, "r", encoding="utf-8") as file:
                monitoring_script = file.read()

            if not monitoring_script.strip():
                raise ValueError("Скрипт мониторинга пуст")
            self.logger.debug(f"Размер скрипта: {len(monitoring_script)} байт")

            self.logger.debug("Внедрение скрипта через CDP")
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": monitoring_script}
            )

            self.logger.info("Мониторинг ресурсов успешно включен")

        except FileNotFoundError as e:
            self.logger.error(f"Файл скрипта не найден: {script_path}")
            raise
        except ValueError as e:
            self.logger.error(f"Ошибка валидации скрипта: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Критическая ошибка: {str(e)}", exc_info=True)
            raise

    def _apply_emulation_scripts(self) -> None:
        """Применяет скрипты для эмуляции мобильного устройства."""
        self.logger.info("Применение эмуляционных скриптов")
        try:
            scripts = [
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
                "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]})",
            ]

            for script in scripts:
                self.driver.execute_script(script)

            self.logger.info("Скрипты успешно применены")
        except Exception as e:
            self.logger.error(f"Ошибка выполнения скриптов: {str(e)}")
            raise

    def _wait_load_full_page(
        self,
        timeout: int = 30,
        max_scroll_attempts: int = 10,
        request_timeout: float = 5.0
    ) -> None:
        """
        Ожидание полной загрузки страницы с прокруткой
        и проверкой активных запросов
        """
        self.logger.info(f"Ожидание загрузки страницы (таймаут: {timeout} сек)")

        # 1. Ждем загрузки DOM
        try:
            self.logger.debug("Ожидание готовности DOM")
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script(
                    'return document.readyState') == 'complete'
            )
            self.logger.debug("DOM полностью загружен")
        except TimeoutException as e:
            self.logger.warning(f"Таймаут ожидания загрузки DOM: {str(e)}")

        # 2. Прокручиваем страницу до конца (для ленивой загрузки)
        self.logger.debug(f"Прокрутка страницы (макс. попыток: {max_scroll_attempts})")
        last_height = self.driver.execute_script("""
            const bodyHeight = document.body.scrollHeight;
            return bodyHeight > 0 ? bodyHeight : document.documentElement.scrollHeight;
        """)
        scroll_attempts = 0

        while scroll_attempts < max_scroll_attempts:
            self.logger.debug(f"Попытка прокрутки {scroll_attempts + 1}/{max_scroll_attempts}")
            self.driver.execute_script("""
                const scrollHeight = document.body.scrollHeight > 0
                    ? document.body.scrollHeight
                    : document.documentElement.scrollHeight;
                window.scrollTo(0, scrollHeight);
            """)

            try:
                WebDriverWait(self.driver, request_timeout).until(
                    lambda d: d.execute_script("""
                        const currentHeight = document.body.scrollHeight > 0
                            ? document.body.scrollHeight
                            : document.documentElement.scrollHeight;
                        return currentHeight > arguments[0];
                    """, last_height)
                )
            except TimeoutException:
                self.logger.debug("Высота страницы не изменилась")
                break

            new_height = self.driver.execute_script("""
                const bodyHeight = document.body.scrollHeight;
                return bodyHeight > 0 ? bodyHeight : document.documentElement.scrollHeight;
            """)
            if new_height == last_height:
                self.logger.debug("Достигнут конец страницы")
                break

            last_height = new_height
            scroll_attempts += 1

        # 3. Возвращаемся в начало страницы
        self.logger.debug("Возврат в начало страницы")
        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)

        # 4. Ожидание завершения сетевых запросов
        self.logger.debug("Ожидание завершения сетевых запросов")
        start_time = time.time()
        last_request_count = len(self._get_links())

        while time.time() - start_time < timeout:
            current_requests = len(self._get_links())
            time.sleep(0.2)

            if current_requests == last_request_count:
                time.sleep(request_timeout)
                if current_requests == len(self._get_links()):
                    self.logger.debug("Активные запросы отсутствуют")
                    break
            else:
                last_request_count = current_requests
                start_time = time.time()
                self.logger.debug(f"Обнаружены новые запросы ({current_requests} активных)")

        self.logger.info("Страница полностью загружена")

    def _get_links(self) -> List[NetworkResource]:
        """Получает список загруженных веб-ресурсов из JavaScript-переменной loadedResources."""
        script_path = "src/scripts/links.js"
        data: List[NetworkResource] = []

        with open(script_path, "r", encoding="utf-8") as file:
            links_script = file.read()

        links = self.driver.execute_script(links_script)
        data.extend([NetworkResource(url=item["url"], type=item["type"]) for item in links])

        requests = self.driver.execute_script("return window.loadedResources")
        data.extend([NetworkResource(url=item["name"], type=item["type"]) for item in requests])

        return data

    def _download_file(self, url: str, download_dir: Path) -> Optional[Tuple[str, str]]:
        """
        Загружает файл по URL с использованием curl.
        """
        self.logger.info(f"Начало загрузки файла: {url[:50]}...")
        max_retries = 1
        retry_delay = 1

        # Проверка существования curl
        if not self.curl_path.exists():
            self.logger.error(f"curl не найден по пути: {self.curl_path}")
            raise FileNotFoundError(f"curl executable not found at {self.curl_path}")

        for attempt in range(max_retries):
            try:
                filename = os.path.basename(url).split("?")[0]
                hash_name = hashlib.sha256(url.encode()).hexdigest()
                filename_list = filename.split(".")

                hash_filename = f"{hash_name}"
                if len(filename_list) > 1:
                    hash_filename = f"{hash_name}.{filename_list[-1]}"
                filepath = download_dir / hash_filename

                self.logger.debug(f"Попытка {attempt + 1}/{max_retries}")
                self.logger.debug(f"Имя файла: {filename}")
                self.logger.debug(f"Хэш: {hash_name}")
                self.logger.debug(f"Полный путь: {filepath}")

                # Формируем команду curl
                command = [
                    str(self.curl_path.absolute()),
                    "-o", str(filepath.absolute()),
                    "--silent",
                    "--show-error",
                    "--fail",
                    "--max-time", "30",
                    "--retry-delay", str(retry_delay),
                    "--retry", "3",
                    "--location"
                ]

                if self.proxy:
                    command.extend(["-x", "socks5h://127.0.0.1:2080"])
                    self.logger.debug("Используется прокси")

                # Настройки SSL
                if Path(certifi.where()).exists():
                    command.extend(["--cacert", str(Path(certifi.where()))])
                    self.logger.debug("Используются системные сертификаты")
                else:
                    command.append("--insecure")
                    self.logger.debug("Проверка сертификатов отключена")

                command.append(url)
                self.logger.debug(f"Команда: {' '.join(command)}")

                # Выполняем команду
                result = subprocess.run(
                    command,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8'
                )

                # Проверяем результат
                if filepath.exists():
                    file_size = filepath.stat().st_size
                    if file_size > 0:
                        self.logger.info(f"Файл успешно загружен ({file_size} байт)")
                        return (url, hash_filename)

                    self.logger.warning(f"Файл пуст (0 байт), удаляем...")
                    filepath.unlink()
                else:
                    self.logger.warning("Файл не был создан")

            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.strip() if e.stderr else "Неизвестная ошибка curl"
                self.logger.warning(f"Ошибка загрузки: {error_msg}")

                # Обработка SSL ошибок
                if "60" in error_msg and "--insecure" not in command:
                    self.logger.info("Обнаружена SSL ошибка, отключаем проверку сертификатов")
                    command.append("--insecure")
                    continue

            except Exception as e:
                self.logger.error(f"Неожиданная ошибка: {str(e)}", exc_info=True)
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Failed to download {url} after {max_retries} attempts") from e

            # Задержка перед повторной попыткой
            if attempt < max_retries - 1:
                delay = retry_delay * (attempt + 1)
                self.logger.info(f"Повтор через {delay} сек...")
                time.sleep(delay)

        self.logger.error(f"Не удалось загрузить файл после {max_retries} попыток")
        return None

    def _download_resources(self, urls: List[str], download_dir: str = "temp") -> Dict[str, str]:
        """
        Загружает список ресурсов в многопоточном режиме.
        """
        try:
            download_path = self.base_dir / download_dir
            download_path.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Начало загрузки {len(urls)} ресурсов в директорию: {download_path}")

            result = {}
            failed_downloads = 0

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_url = {
                    executor.submit(self._download_file, url=url, download_dir=download_path): url
                    for url in urls
                }

                for future in as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        download_result = future.result()
                        if download_result:
                            original_url, saved_filename = download_result
                            result[original_url] = saved_filename
                            self.logger.debug(f"Успешно загружен: {url} → {saved_filename}")
                        else:
                            failed_downloads += 1
                            self.logger.warning(f"Не удалось загрузить: {url}")
                    except Exception as e:
                        failed_downloads += 1
                        self.logger.error(f"Ошибка при загрузке {url}: {str(e)}", exc_info=True)

            success_count = len(result)
            self.logger.info(
                f"Загрузка завершена. Успешно: {success_count}, "
                f"не удалось: {failed_downloads}, "
                f"всего: {len(urls)}"
            )

            if success_count == 0 and len(urls) > 0:
                self.logger.error("Не удалось загрузить ни одного ресурса")
                raise RuntimeError("All downloads failed")

            return result
        except Exception as e:
            self.logger.error(f"Критическая ошибка при загрузке ресурсов: {str(e)}", exc_info=True)
            raise

    def _replace_urls_in_html(self, html: str, url_mapping: Dict[str, str]) -> str:
        """
        Заменяет все URL в HTML-контенте на локальные пути согласно переданному маппингу.
        """
        if not html.strip():
            raise ValueError("Передан пустой HTML-контент")
        if not url_mapping:
            raise ValueError("Передан пустой словарь URL-маппинга")

        self.logger.info("Начало замены URL в HTML-контенте")
        self.logger.debug(f"Количество URL для замены: {len(url_mapping)}")

        try:
            modified_html = html

            for original_url, local_path in url_mapping.items():
                self.logger.debug(f"Заменяем: {original_url[:50]}... → {local_path}")

                url_variants = self._generate_url_variants(original_url)
                sorted_url_variants = sorted(url_variants, key=len, reverse=True)

                for url_variant in sorted_url_variants:
                    modified_html = modified_html.replace(url_variant, local_path)

            self.logger.debug("Удаление тегов <base>")
            soup = BeautifulSoup(modified_html, 'html.parser')
            for base_tag in soup.find_all('base'):
                base_tag.decompose()

            result = soup.prettify()
            self.logger.info("Замена URL завершена успешно")
            return result

        except Exception as e:
            self.logger.error(f"Ошибка при замене URL: {str(e)}", exc_info=True)
            raise

    def _generate_url_variants(self, url: str) -> List[str]:
        """
        Генерирует все возможные варианты URL для замены.
        """
        variants = [url]

        # Удаляем протокол
        no_protocol = url.replace("https://", "").replace("http://", "")
        variants.extend([f"./{no_protocol}", f"/{no_protocol}", no_protocol])

        # Генерируем варианты с относительными путями
        parts = no_protocol.split("/")
        for i in range(1, len(parts)):
            relative_path = "/".join(parts[i:])
            if len(relative_path) != 0:
                variants.extend([
                    f"./{relative_path}",
                    f"/{relative_path}",
                    relative_path
                ])

        # Добавляем варианты с параметрами запроса
        if '?' in url:
            base_url = url.split('?')[0]
            variants.extend(self._generate_url_variants(base_url))

        return list(set(variants))

    def _run_media_script(self) -> None:
        """Выполняет JavaScript-скрипт для создания скриншота всей страницы."""
        script_path = "src/scripts/media_script.js"

        with open(script_path, "r", encoding="UTF-8") as file:
            media_script = file.read()

        self.driver.execute_script(media_script)

    def launch(self) -> None:
        """Запускает undetected_chromedriver с настройками."""
        self.logger.info("Запуск браузера")
        try:
            self.options = ChromeOptions()
            self.logger.debug("Инициализация ChromeOptions")

            if self.headless:
                self.logger.debug("Режим headless включен")
                self.options.add_argument('--headless=new')
                self.options.add_argument('--disable-gpu')

            if self.proxy:
                self.logger.debug("Настройка прокси")
                self.options.add_argument(f'--proxy-server=socks5://127.0.0.1:2080')

                if self.location:
                    self.logger.debug(f"Установка локали: {self.location.locale}")
                    self.options.add_argument(f'--lang={self.location.locale}')
                    self.logger.debug(f"Установка часового пояса: {self.location.timezone}")
                    self.options.add_argument(f'--timezone={self.location.timezone}')

            self.options.add_argument('--disable-blink-features=AutomationControlled')
            self.options.add_argument('--disable-infobars')

            self.logger.debug("Создание экземпляра Chrome")
            self.driver = Chrome(
                options=self.options,
                headless=self.headless,
                use_subprocess=True,
            )

            if self.location:
                self._set_geolocation()

            self._monitoring_enable()
            self._apply_emulation_scripts()
            self.driver.set_window_size(1280, 720)
            self.logger.debug(f"Установлен размер окна: 1280x720")

            self.logger.info("Браузер успешно запущен")
        except Exception as e:
            self.logger.error(f"Ошибка запуска браузера: {str(e)}", exc_info=True)
            raise

    def close(self) -> None:
        """Закрытие браузера и освобождение ресурсов"""
        self.logger.info("Закрытие браузера")
        try:
            if hasattr(self, 'driver') and self.driver:
                try:
                    self.logger.debug("Завершение работы WebDriver")
                    self.driver.quit()
                    self.logger.debug("WebDriver успешно закрыт")
                except Exception as e:
                    self.logger.error(f"Ошибка при закрытии WebDriver: {str(e)}")
                    raise
                finally:
                    self.driver = None
                    self.logger.debug("WebDriver установлен в None")

            self.logger.info("Браузер успешно закрыт")
        except Exception as e:
            self.logger.error(f"Критическая ошибка при закрытии: {str(e)}", exc_info=True)
            raise

    def goto(self, url: str, delay: float = 0, timeout: float = 30.0) -> None:
        """
        Переход по указанному URL с возможной задержкой
        """
        self.logger.info(f"Переход по URL: {url}")
        self.logger.debug(f"Таймаут: {timeout} сек | Задержка: {delay} сек")

        if not hasattr(self, 'driver') or not self.driver:
            self.logger.error("Браузер не инициализирован")
            raise RuntimeError("Браузер не инициализирован. Сначала вызовите launch()")

        try:
            self.logger.debug("Выполнение перехода")
            self.driver.get(url)

            if delay > 0:
                self.logger.debug(f"Ожидание {delay} секунд")
                time.sleep(delay)

            self.logger.info(f"Успешно перешли по URL: {url}")

        except TimeoutException:
            self.logger.error(f"Таймаут ({timeout} сек) при переходе по URL")
            raise
        except Exception as e:
            self.logger.error(f"Ошибка перехода: {str(e)}", exc_info=True)
            raise RuntimeError(f"Не удалось перейти по URL {url}: {str(e)}") from e

    def pdf(self, pdf_path: str) -> None:
        """Сохранение страницы в PDF"""
        self.logger.info(f"Сохранение PDF: {pdf_path}")
        WebDriverWait(self.driver, 30).until(
            lambda d: d.execute_script("return typeof window.pdfBytes !== 'undefined';")
        )
        pdf_bytes = self.driver.execute_script("return window.pdfBytes;")
        if pdf_bytes:
            bytes_data = bytes(pdf_bytes)

            with open(pdf_path, "wb") as file:
                file.write(bytes_data)
            self.logger.info(f"PDF успешно сохранен как {pdf_path}")
        else:
            raise Exception(f"Ошибка сохранения PDF: {str(e)}")

    def screenshot(self, screenshot_path: str) -> None:
        """Сохранение скриншота страницы"""
        self.logger.debug("Сохранение изображения")
        WebDriverWait(self.driver, 30).until(
            lambda d: d.execute_script("return typeof window.screenshotBytes !== 'undefined';")
        )
        screenshot_bytes = self.driver.execute_script("return window.screenshotBytes;")
        if screenshot_bytes:
            bytes_data = bytes(screenshot_bytes)

            with open(screenshot_path, "wb") as file:
                file.write(bytes_data)
            self.logger.info(f"Скриншот сохранен: {screenshot_path}")
        else:
            raise Exception("Не удалось получить данные скриншота")

    def download_website(self, output_dir: Optional[str] = None, make_zip: bool = True) -> bool:
        """Скачивает весь веб-сайт."""
        start_time = time.time()
        self.logger.info(f"Скачивание веб-сайта")
        self.logger.debug(f"Выходная директория: {output_dir}")
        self.logger.debug(f"Создание ZIP: {'Да' if make_zip else 'Нет'}")

        try:
            self.logger.debug("Получение текущего URL...")
            parsed_url = urlparse(self.driver.current_url)
            domain = parsed_url.netloc.replace('www.', '').split(':')[0]
            folder_name = output_dir if output_dir else domain

            website_dir = self.temp_dir / folder_name
            website_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Создание рабочей директории: {website_dir}")

            self.logger.info("Ожидание полной загрузки страницы...")
            self._wait_load_full_page()
            self._run_media_script()

            self.logger.debug("Сбор всех ссылок на странице...")
            urls = set([item.url for item in self._get_links()])
            self.logger.info(f"Найдено {len(urls)} уникальных URL-адресов")

            self.logger.info("Получение исходного HTML...")
            html = self.driver.page_source

            self.logger.info("Загрузка ресурсов...")
            url_mapping = self._download_resources(urls=urls, download_dir=website_dir)
            self.logger.info(f"Загружено {len(url_mapping)} ресурсов")

            self.logger.info("Замена URL в HTML...")
            output_html_path = website_dir / 'index.html'
            new_html = self._replace_urls_in_html(html, url_mapping)

            self.logger.info(f"Сохранение модифицированного HTML: {output_html_path}")
            with open(output_html_path, 'w', encoding='utf-8') as f:
                f.write(new_html)

            archive_path = None
            if make_zip:
                archive_path = str(website_dir) + ".zip"
                self.logger.info(f"Создание архива: {archive_path}")

                shutil.make_archive(
                    base_name=str(website_dir),
                    format='zip',
                    root_dir=website_dir
                )
                self.logger.info(f"Архив успешно создан ({os.path.getsize(archive_path)/1024:.2f} KB)")

                self.logger.info(f"Удаление временной директории: {website_dir}")
                try:
                    shutil.rmtree(website_dir)
                    self.logger.debug("Директория успешно удалена")
                except Exception as e:
                    self.logger.warning(f"Не удалось удалить директорию: {str(e)}")

            total_time = time.time() - start_time
            self.logger.info(f"Скачивание завершено успешно за {total_time:.2f} сек")
            self.logger.info(f"Результат: {'ZIP архив: ' + archive_path if make_zip else 'Директория: ' + str(website_dir)}")
            return True

        except Exception as e:
            total_time = time.time() - start_time
            self.logger.error(f"Ошибка скачивания сайта (затрачено {total_time:.2f} сек)")
            self.logger.error(f"Причина: {str(e)}", exc_info=self.logger.level <= logging.DEBUG)
            return False
