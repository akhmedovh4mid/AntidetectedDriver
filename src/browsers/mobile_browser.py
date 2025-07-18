import os
import time
import shutil
import certifi
import hashlib
import logging
import subprocess

from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Dict, List, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright, Request, Response

from src.models.location_data import LocationData


class PlaywrightMobileBrowser():
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
        self.device: str = 'iPhone 13'

        self.requests: Optional[Set[Request]] = set()
        self.responses: Optional[Set[Response]] = set()

        self.log_path = Path("src/logs/playwright_mobile_browser.log")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        self.base_dir = Path(__file__).parent.parent.parent
        self.temp_dir = self.base_dir.joinpath("temp")

        self.curl_path = Path("src/apps/curl/bin/curl.exe")

        self.log_level = log_level
        self.logger = logging.getLogger(self.__class__.__name__)
        self._setup_logging()

        self.browser = None
        self.context = None
        self.page = None

        self.max_workers = 6

    def __enter__(self) -> 'PlaywrightMobileBrowser':
        """Поддержка контекстного менеджера (with) - автоматический запуск браузера"""
        self.logger.debug("Вход в контекстный менеджер - запуск мобильного браузера")
        self.launch()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Автоматическое закрытие при выходе из контекста"""
        self.logger.debug("Выход из контекстного менеджера - закрытие мобильного браузера")
        self.close()

    def _add_context_stcripts(self) -> None:
        """Добавление скриптов для эмуляции мобильного устройства и обхода детекции"""
        self.logger.debug("Добавление скриптов контекста для эмуляции мобильного устройства")
        scripts = [
            # Эмуляция характеристик iPhone
            """
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 6,  // iPhone 13: 6 ядер
            });
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 4,  // iPhone 13: 4 ГБ RAM
            });
            """,
            # Обход детекции автоматизации
            """
            delete Object.getPrototypeOf(navigator).webdriver;
            window.navigator.chrome = { runtime: {}, };
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            """,
            # Эмуляция платформы
            """
            Object.defineProperty(navigator, 'platform', {
                get: () => 'iPhone'
            });
            """,
            # Эмуляция вендора
            """
            Object.defineProperty(navigator, 'vendor', {
                value: 'Apple Computer, Inc.',
                configurable: false,
                enumerable: true,
                writable: false
            });
            """,
            # Эмуляция WebGL
            """
            const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Apple Inc.';       // VENDOR
                if (parameter === 37446) return 'Apple GPU';        // RENDERER
                return originalGetParameter.call(this, parameter);  // Остальные параметры без изменений
            };

            const originalGetParameterWebGL2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Apple Inc.';
                if (parameter === 37446) return 'Apple GPU';
                return originalGetParameterWebGL2.call(this, parameter);
            };
            """,
            # Эмуляция Battery API
            """
            Object.defineProperty(navigator, 'getBattery', {
                value: () => Promise.resolve({
                    charging: false,
                    level: 0.77,
                    chargingTime: Infinity,
                    dischargingTime: 8940,
                    addEventListener: () => {}
                }),
                configurable: false,
                enumerable: true,
                writable: false
            });
            """,
            # Эмуляция Touch API
            """
            Object.defineProperty(navigator, 'maxTouchPoints', {
                get: () => 5
            });
            """,
            # Эмуляция Connection API
            """
            Object.defineProperty(navigator, 'connection', {
                get: () => ({
                    downlink: 10,
                    effectiveType: "4g",
                    rtt: 50,
                    saveData: false,
                    type: "cellular"
                })
            });
            """,
            # Эмуляция Screen Orientation
            """
            Object.defineProperty(screen, 'orientation', {
                get: () => ({
                    angle: 0,
                    type: "portrait-primary",
                    onchange: null
                })
            });
            """,
            # Эмуляция Device Pixel Ratio
            """
            Object.defineProperty(window, 'devicePixelRatio', {
                get: () => 3  // Типичное значение для современных смартфонов
            });
            """,
        ]

        for script in scripts:
            self.context.add_init_script(script)

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

    def _wait_load_full_page(
        self,
        timeout: int = 30,
        max_scroll_attempts: int = 10,
        request_timeout: float = 2.5
    ) -> None:
        """
        Ожидание полной загрузки страницы с прокруткой и проверкой активных запросов

        :param timeout: Максимальное время ожидания в секундах
        :param max_scroll_attempts: Максимальное количество попыток прокрутки
        :param request_timeout: Таймаут ожидания завершения запросов
        """
        self.logger.debug("Ожидание полной загрузки страницы с прокруткой")

        # 1. Ждем загрузки DOM и сети
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=timeout * 1000)
            self.page.wait_for_load_state("networkidle", timeout=timeout * 1000)
        except Exception as e:
            self.logger.warning(f"Превышено время ожидания загрузки страницы: {str(e)}")

        # 2. Прокручиваем страницу до конца (для ленивой загрузки)
        last_height = self.page.evaluate("""() => {
            const bodyHeight = document.body.scrollHeight;
            return bodyHeight > 0 ? bodyHeight : document.documentElement.scrollHeight;
        }""")
        scroll_attempts = 0

        while scroll_attempts < max_scroll_attempts:
            self.page.evaluate("""() => {
                const scrollHeight = document.body.scrollHeight > 0
                    ? document.body.scrollHeight
                    : document.documentElement.scrollHeight;
                window.scrollTo(0, scrollHeight);
            }""")
            self.logger.debug(f"Попытка прокрутки {scroll_attempts + 1}/{max_scroll_attempts}")

            try:
                self.page.wait_for_function("""(prevHeight) => {
                    const currentHeight = document.body.scrollHeight > 0
                        ? document.body.scrollHeight
                        : document.documentElement.scrollHeight;
                    return currentHeight > prevHeight;
                }""", arg=last_height, timeout=2000)
            except Exception:
                break

            new_height = self.page.evaluate("""() => {
                const bodyHeight = document.body.scrollHeight;
                return bodyHeight > 0 ? bodyHeight : document.documentElement.scrollHeight;
            }""")
            if new_height == last_height:
                self.logger.debug("Высота страницы не изменилась после прокрутки")
                break

            last_height = new_height
            scroll_attempts += 1

        # 3. Ждем завершения всех активных запросов
        start_time = time.time()
        while time.time() - start_time < timeout:
            current_requests = len(self.requests)
            time.sleep(0.2)

            if current_requests == len(self.requests):
                time.sleep(request_timeout)
                if current_requests == len(self.requests):
                    self.logger.debug("Новых запросов не обнаружено")
                    break
            else:
                self.logger.debug("Обнаружены новые запросы, сброс таймера")
                start_time = time.time()

    def _download_file(self, request: dict, download_dir: Path) -> Optional[Tuple[str, str]]:
        """
        Загрузка файла с обработкой ошибок и повторами
        """
        max_retries = 3
        retry_delay = 1
        url = request["url"]
        body = request["body"]

        self.logger.info(f"Начало загрузки файла: {url}")

        for attempt in range(max_retries):
            try:
                filename = os.path.basename(url).split("?")[0]
                hash_name = hashlib.sha256(url.encode()).hexdigest()
                filename_list = filename.split(".")

                hash_filename = f"{hash_name}"
                if len(filename_list) > 1:
                    hash_filename = f"{hash_name}.{filename_list[-1]}"
                filepath = download_dir / hash_filename

                self.logger.debug(f"Попытка {attempt + 1}/{max_retries}: Загрузка {url} в {filepath}")

                # Базовые параметры curl
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

                # Добавляем опцию для SSL (3 варианта в порядке приоритета)
                if Path(certifi.where()).exists():
                    self.logger.debug("Используется сертификат из certifi")
                    command.extend(["--cacert", str(Path(certifi.where()))])  # Используем certifi
                else:
                    self.logger.warning("Сертификат certifi не найден, отключаем проверку SSL")
                    command.append("--insecure")  # Fallback: отключаем проверку SSL

                # Добавляем URL в конец команды
                command.append(url)

                self.logger.debug(f"Выполняемая команда curl: {' '.join(command)}")

                # Выполняем запрос
                result = subprocess.run(
                    command,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8'
                )

                # Проверяем, что файл действительно скачан
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

        if body is not None:
            try:
                filename = os.path.basename(url).split("?")[0]
                hash_name = hashlib.sha256(url.encode()).hexdigest()
                filename_list = filename.split(".")

                hash_filename = f"{hash_name}"
                if len(filename_list) > 1:
                    hash_filename = f"{hash_name}.{filename_list[-1]}"
                filepath = download_dir / hash_filename

                self.logger.info(f"Используем fallback - сохранение body в файл: {filepath}")

                with open(filepath, 'wb') as file:
                    file.write(body)

                if filepath.exists() and filepath.stat().st_size > 0:
                    self.logger.info(f"Файл успешно сохранен из body: {filepath} ({filepath.stat().st_size} байт)")
                    return (url, hash_filename)
                else:
                    self.logger.error("Не удалось сохранить файл из body")
            except Exception as e:
                self.logger.error(f"Ошибка при сохранении body в файл: {str(e)}", exc_info=True)

        return None

    def _download_resources(self, requests: Set[Request], download_dir: str = "temp") -> Dict[str, str]:
        """
        Многопоточная загрузка всех ресурсов страницы
        """
        self.logger.info(f"Загрузка {len(requests)} ресурсов в {download_dir}")

        download_path = self.base_dir / download_dir
        download_path.mkdir(parents=True, exist_ok=True)

        result = {}
        content_type_list = [
            "audio", "audioworklet", "document", "embed",
            "empty", "font", "frame", "iframe", "image",
            "manifest", "object", "paintworklet", "report",
            "script", "serviceworker", "sharedworker", "style",
            "track", "video", "worker", "xslt"
        ]

        data = []
        for request in requests:
            ans = {"url": request.url, "body": None}
            if str(request.header_value("sec-fetch-dest")).lower() in content_type_list:
                count = 0
                while count < 3:
                    try:
                        ans["body"] = request.response().body()
                        break
                    except:
                        count += 1
                        time.sleep(0.2)
                        continue

            data.append(ans)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_request = {
                executor.submit(self._download_file, request=request, download_dir=download_path): request
                for request in data
            }

            for future in as_completed(future_to_request):
                ans = future.result()
                if ans:
                    result[ans[0]] = ans[1]

        self.logger.info(f"Успешно загружено {len(result)} ресурсов")
        return result

    def _replace_urls_in_html(self, html_content: str, url_mapping: Dict[str, str]) -> str:
        """
        Заменяет все URL в HTML-контенте на локальные пути согласно переданному маппингу.
        """
        if not html_content.strip():
            raise ValueError("Передан пустой HTML-контент")
        if not url_mapping:
            raise ValueError("Передан пустой словарь URL-маппинга")

        self.logger.info("Начало замены URL в HTML-контенте")
        self.logger.debug(f"Количество URL для замены: {len(url_mapping)}")

        try:
            modified_html = html_content

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

    def launch(self) -> None:
        """Запуск мобильного браузера с настройками устройства и прокси"""
        self.logger.info(f"Запуск мобильного браузера с устройством: {self.device}")
        try:
            self.playwright = sync_playwright().start()
            mobile = self.playwright.devices[self.device]

            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                ignore_default_args=['--enable-automation'],
                chromium_sandbox=False,
                proxy={'server': "socks5://127.0.0.1:2080"} if self.proxy else None,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-automation',
                    '--enable-touch-events',
                    '--simulate-touch-screen-with-mouse',
                ]
            )

            if self.location != None:
                self.logger.debug(f"Создание мобильного контекста с локалью: {self.location.locale}, геолокацией и почтовым индексом")
                self.context = self.browser.new_context(
                    **mobile,
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
                self.context = self.browser.new_context(**mobile)

            self._add_context_stcripts()
            self.page = self.context.new_page()
            self.page.emulate_media(color_scheme='light')

            # Подписка на события запросов и ответов
            self.page.on("request", lambda request: self.requests.add(request))
            self.page.on("response", lambda response: self.responses.add(response))

            self.logger.info("Мобильный браузер успешно запущен")
        except Exception as e:
            self.logger.error(f"Ошибка при запуске мобильного браузера: {str(e)}")
            raise

    def goto(self, url: str, delay: float = 0) -> None:
        """
        Переход по указанному URL с возможной задержкой

        :param url: Адрес для перехода
        :param delay: Задержка после загрузки (в секундах)
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

    def screenshot(self, screenshot_path: str) -> None:
        """
        Сохранение скриншота текущей страницы

        :param screenshot_path: Путь для сохранения файла
        """
        self.logger.info(f"Создание скриншота и сохранение в: {screenshot_path}")
        if not self.page:
            self.logger.error("Страница не инициализирована. Сначала вызовите launch()")
            raise RuntimeError("Страница не инициализирована. Сначала вызовите launch()")

        try:
            self.page.screenshot(
                path=screenshot_path,
                full_page=True,
                type="png",
                timeout=5000
            )
            self.logger.info("Скриншот успешно сохранен")
        except Exception as e:
            self.logger.error(f"Ошибка при создании скриншота: {str(e)}")
            raise

    def pdf(self, pdf_path: str) -> None:
        """
        Сохранение текущей страницы в PDF

        :param pdf_path: Путь для сохранения PDF файла
        """
        self.logger.info(f"Сохранение страницы в PDF: {pdf_path}")
        if not self.page:
            self.logger.error("Страница не инициализирована. Сначала вызовите launch()")
            raise RuntimeError("Страница не инициализирована. Сначала вызовите launch()")

        try:
            self.page.pdf(
                path=pdf_path,
                print_background=True,
                scale=1.0,
                margin={
                    "top": "0px",
                    "right": "0px",
                    "bottom": "0px",
                    "left": "0px"
                },
                prefer_css_page_size=True,
                display_header_footer=False,
                )
            self.logger.info("PDF успешно сохранен")
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении PDF: {str(e)}")
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

    def download_website(self, output_subdir: Optional[str] = None, make_zip: bool = True) -> bool:
        """
        Полное скачивание веб-сайта с возможностью архивации
        """
        self.logger.info(f"Начало загрузки веб-сайта: {self.page.url}")

        try:
            # Извлекаем домен из URL
            parsed_url = urlparse(self.page.url)
            domain = parsed_url.netloc.replace('www.', '').split(':')[0]
            folder_name = output_subdir if output_subdir else domain

            # Создаем директорию
            website_dir = self.temp_dir / folder_name
            website_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Создана выходная директория: {website_dir}")

            # Получаем ресурсы
            self._wait_load_full_page()
            html = self.page.content()
            url_mapping = self._download_resources(self.requests, website_dir)

            output_html_path = website_dir / 'index.html'
            with open(output_html_path, 'w', encoding='utf-8') as f:
                f.write(self._replace_urls_in_html(html, url_mapping))
            self.logger.info(f"Модифицированный HTML сохранен в: {output_html_path}")

            # Создаем архив при необходимости
            archive_path = None
            if make_zip:
                archive_path = str(website_dir) + ".zip"
                self.logger.info(f"Создание архива: {archive_path}")

                shutil.make_archive(
                    base_name=str(website_dir),
                    format='zip',
                    root_dir=website_dir
                )
                self.logger.info(f"Архив создан: {archive_path}")

                try:
                    shutil.rmtree(website_dir)
                    self.logger.info(f"Исходная директория удалена: {website_dir}")
                except Exception as e:
                    self.logger.error(f"Ошибка при удалении директории {website_dir}: {str(e)}")

            self.logger.info(f"Обработка веб-сайта завершена. Архив: {archive_path}")
            return True

        except Exception as e:
            self.logger.error(f"Ошибка при загрузке веб-сайта {self.page.url}: {str(e)}")
            return None
