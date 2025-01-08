import asyncio
import aiohttp
import json
import logging
import time
import os
import glob
from tqdm.asyncio import tqdm_asyncio
from logging.handlers import RotatingFileHandler

# Настройка логирования с ротацией
log_format = '%(asctime)s - %(levelname)s - %(message)s'
log_file = 'warframe_market_orders.log'
log_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=1, encoding='utf-8')
log_handler.setFormatter(logging.Formatter(log_format))
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Уровень INFO, чтобы видеть важные сообщения
logger.addHandler(log_handler)

def cleanup_old_logs(log_file_base):
    """Удаляет старые лог-файлы, оставляя последние 2."""
    log_files = glob.glob(f"{log_file_base}*")
    log_files.sort(key=os.path.getmtime)
    if len(log_files) > 2:
        files_to_delete = log_files[:-2]
        for file_to_delete in files_to_delete:
            try:
                os.remove(file_to_delete)
                logger.info(f"Удален старый лог-файл: {file_to_delete}")
            except OSError as e:
                logger.error(f"Ошибка при удалении лог-файла {file_to_delete}: {e}")

# Кэш
cache = {}
CACHE_FILE = "item_orders_cache.json"
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        try:
            cache = json.load(f)
        except json.JSONDecodeError:
            logger.error("Ошибка декодирования кэша. Создан новый кэш.")
            cache = {} # Инициализация пустого кэша в случае ошибки

# URL API
BASE_URL = "https://api.warframe.market/v1"
HEADERS = {"Accept": "application/json"}

# Задержки и количество запросов
INITIAL_DELAY = 0.1
MAX_DELAY = 30.0
CONCURRENT_REQUESTS = 5 # Увеличил количество одновременных запросов для ускорения

async def fetch_data(session, url, current_delay=INITIAL_DELAY):
    """Асинхронно получает данные по URL с динамической задержкой и обработкой ошибок."""
    async with asyncio.Semaphore(CONCURRENT_REQUESTS):
        try:
            await asyncio.sleep(current_delay)
            async with session.get(url, headers=HEADERS, timeout=10) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            if e.status == 429:  # Too Many Requests
                logger.warning(f"Получен ответ 429 (Too Many Requests) от {url}. Увеличиваем задержку.")
                if current_delay < MAX_DELAY:
                    new_delay = min(current_delay * 2, MAX_DELAY)
                    return await fetch_data(session, url, new_delay) # Рекурсивный вызов с увеличенной задержкой
                else:
                    logger.error(f"Достигнута максимальная задержка ({MAX_DELAY} секунд) при запросе к {url}. Пауза и повторная попытка через 60 секунд.")
                    await asyncio.sleep(60) # Пауза в 60 секунд
                    return await fetch_data(session, url, INITIAL_DELAY) # Повторный запрос с начальной задержкой
            else:
                logger.error(f"Ошибка HTTP {e.status} при запросе к {url}: {e.message}")
                return None
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка при запросе к {url}: {e}")
            return None

async def get_item_orders(session, item_url_name):
    if item_url_name in cache: # Проверка кэша
        return cache[item_url_name]

    url = f"{BASE_URL}/items/{item_url_name}/orders"
    data = await fetch_data(session, url)
    if data and "payload" in data and "orders" in data["payload"]:
        cache[item_url_name] = data["payload"]["orders"] # Сохранение в кэш
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=4, ensure_ascii=False) # Сохранение кэша на диск
        return data["payload"]["orders"]
    else:
        logger.warning(f"Не удалось получить ордера для {item_url_name}")
        return None

async def get_online_orders(orders):
    if orders is None:
        return []
    online_orders = []
    for order in orders:
        if "user" in order and "online" in order["user"]: # Проверка наличия ключей
            if order["user"]["online"]:
                online_orders.append(order)
        else:
            logger.warning(f"В ордере отсутствует информация о пользователе или статусе онлайн: {order}") # Логируем проблемные ордера
    return online_orders

async def process_item_data(session, item_data): #добавил session
    try:
        if "en" in item_data and "item_name" in item_data["en"]:
            item_name = item_data["en"]["item_name"]
        elif "ru" in item_data and "item_name" in item_data["ru"]:
            item_name = item_data["ru"]["item_name"]
        else:
            logger.warning(f"Отсутствует название предмета на русском или английском url_name: {item_data.get('url_name', 'Неизвестно')}")
            return None

        orders = await get_item_orders(session, item_data["url_name"])
        online_orders = await get_online_orders(orders)

        if not online_orders:
            logger.warning(f"Нет онлайн ордеров для {item_name}")
            return None

        buy_prices = [order["platinum"] for order in online_orders if order["order_type"] == "buy"]
        sell_prices = [order["platinum"] for order in online_orders if order["order_type"] == "sell"]

        if not buy_prices or not sell_prices:
            logger.warning(f"Недостаточно данных о ценах для {item_name}")
            return None

        lowest_buy_price = min(buy_prices)
        highest_sell_price = max(sell_prices)
        price_difference = highest_sell_price - lowest_buy_price

        return {
            "item_name": item_name,
            "lowest_buy_price": lowest_buy_price,
            "highest_sell_price": highest_sell_price,
            "price_difference": price_difference,
        }
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка при запросе к API для {item_data.get('url_name', 'неизвестный предмет')}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Непредвиденная ошибка при обработке {item_data.get('url_name', 'неизвестный предмет')}: {e}")
        return None

def count_items(data):
    """Считает количество предметов в items_in_set."""
    count = 0
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict) and "items_in_set" in value and isinstance(value["items_in_set"], list):
                count += len(value["items_in_set"])
    return count

async def main():
    start_time = time.time()
    processed_items_count = 0 # Инициализация счетчика обработанных предметов
    try:
        async with aiohttp.ClientSession() as session:
            with open("all_items_data.json", "r", encoding="utf-8") as f:
                item_data = json.load(f)

            total_items = count_items(item_data)
            print(f"Найдено {total_items} предметов для обработки.")
            logger.info(f"Найдено {total_items} предметов для обработки.")

            all_tasks = []
            for item_group in item_data.values():
                if isinstance(item_group, dict) and "items_in_set" in item_group and isinstance(item_group["items_in_set"], list):
                    for item in item_group["items_in_set"]:
                        all_tasks.append(process_item_data(session, item))

            results = await tqdm_asyncio.gather(*all_tasks, desc="Обработка предметов", total=len(all_tasks))

            filtered_results = [result for result in results if result is not None] # Фильтрация None результатов
            processed_items_count = len(filtered_results) # Обновление счетчика после первой обработки

            # Цикл повторных попыток обработки неудачных запросов
            while processed_items_count < total_items:
                failed_tasks_indices = [i for i, result in enumerate(results) if result is None]
                if not failed_tasks_indices:
                    break  # Выход, если все задачи выполнены успешно
                logger.warning(f"Обработано {processed_items_count} из {total_items} предметов. Повторная попытка через 10 секунд.")
                print(f"Обработано {processed_items_count} из {total_items} предметов. Повторная попытка через 10 секунд.")
                await asyncio.sleep(10)
                new_tasks = [all_tasks[i] for i in failed_tasks_indices]
                results = await asyncio.gather(*new_tasks, desc=f"Повторная обработка {len(new_tasks)} предметов", total=len(new_tasks))
                filtered_results.extend([result for result in results if result is not None]) # Добавляем успешные результаты к общему списку
                processed_items_count = len(filtered_results) # Обновляем счетчик

            cleanup_old_logs(log_file)

            output_filename = "orders_data.json"
            with open(output_filename, "w", encoding="utf-8") as f:
                json.dump(filtered_results, f, indent=4, ensure_ascii=False)
            logger.info(f"Данные об ордерах сохранены в {output_filename}")
            print(f"Данные об ордерах сохранены в {output_filename}")
            print(f"Всего обработано {len(filtered_results)} предметов.") # Вывод общего количества обработанных предметов.
            logger.info(f"Всего обработано {len(filtered_results)} предметов.")

    except FileNotFoundError:
        logger.error("Файл all_items_data.json не найден.")
        print("Ошибка: файл all_items_data.json не найден. Запустите скрипт WarframeMarketAnalysys.py.")
    except json.JSONDecodeError:
        logger.error("Ошибка декодирования JSON в файле all_items_data.json")
        print("Ошибка: поврежден файл all_items_data.json.")
    except Exception as e:
        logger.exception(f"Произошла непредвиденная ошибка: {e}")
        print(f"Произошла непредвиденная ошибка: {e}")
    finally:
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"Время выполнения скрипта: {elapsed_time:.2f} секунд")
        print(f"Время выполнения: {elapsed_time:.2f} секунд")

if __name__ == "__main__":
    asyncio.run(main())