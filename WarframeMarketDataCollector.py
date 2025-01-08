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
log_file_base = 'collector'  # Базовое имя лог-файла
log_file = f'{log_file_base}.log' # Имя текущего лог файла
log_handler = RotatingFileHandler(log_file, maxBytes=3*1024*1024, backupCount=9, encoding='utf-8') # 3MB, 9 бэкапов (итого 10 файлов)
log_handler.setFormatter(logging.Formatter(log_format))
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(log_handler)

def cleanup_old_logs(log_file_base):
    """Удаляет старые лог-файлы, оставляя последние 10."""
    log_files = glob.glob(f"{log_file_base}*.log") # Изменено для поиска файлов с расширением .log
    log_files.sort(key=os.path.getmtime)
    if len(log_files) > 10:
        files_to_delete = log_files[:-10]
        for file_to_delete in files_to_delete:
            try:
                os.remove(file_to_delete)
                logger.info(f"Удален старый лог-файл: {file_to_delete}")
            except OSError as e:
                logger.error(f"Ошибка при удалении лог-файла {file_to_delete}: {e}")

async def fetch_all_items(session):
    url = "https://api.warframe.market/v1/items"
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()
            return data["payload"]["items"]
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка при получении списка предметов: {e}")
        return None

async def fetch_item_data(session, item_url_name):
    url = f"https://api.warframe.market/v1/items/{item_url_name}"
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()
            item_data = data.get("payload", {}).get("item") # Безопасный доступ к данным
            if item_data:
                items_in_set = item_data.get("items_in_set", [])
                item_data["items_in_set"] = [item.get("url_name") for item in items_in_set if item.get("url_name")]
            return item_data # Возвращаем непосредственно item_data
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка при получении данных о предмете {item_url_name}: {e}")
        return None
    except (KeyError, TypeError) as e: # Обработка KeyError и TypeError
        logger.error(f"Ошибка структуры данных для {item_url_name}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON для {item_url_name}: {e}")
        return None

async def main():
    start_time = time.time()
    logger.info("Начало сбора данных")
    print("Начало сбора данных...")

    try:
        cleanup_old_logs(log_file) # Очистка логов перед началом работы

        async with aiohttp.ClientSession() as session:
            all_items_list = await fetch_all_items(session)

            if all_items_list is None:
                logger.error("Не удалось получить список всех предметов.")
                print("Ошибка: не удалось получить список предметов.")
                return

            all_items_data = {}

            tasks = [fetch_item_data(session, item["url_name"]) for item in all_items_list]
            for future in tqdm_asyncio.as_completed(tasks, desc="Загрузка данных о предметах", total=len(tasks)):
                try:
                    item_data = await future
                    if item_data:
                        all_items_data[item_data['url_name']] = item_data
                    else:
                        logger.warning("Получены пустые данные для предмета.")
                except Exception as e:
                    logger.exception(f"Непредвиденная ошибка при обработке результата: {e}")

            saved_item_count = len(all_items_data)
            logger.info(f"Количество предметов, готовых к сохранению: {saved_item_count}")
            print(f"Готово к сохранению: {saved_item_count} предметов.")

            with open("all_items_data.json", "w", encoding="utf-8") as f:
                json.dump(all_items_data, f, indent=4, ensure_ascii=False)

            logger.info("Сбор данных завершен.")
            print("Сбор данных завершен.")

            with open("all_items_data.json", "r", encoding="utf-8") as f:
                loaded_data = json.load(f)

            loaded_item_count = len(loaded_data)
            logger.info(f"Количество сохраненных предметов (после чтения из файла): {loaded_item_count}")
            print(f"Сохранено: {loaded_item_count} предметов.")

            if saved_item_count != loaded_item_count:
                logger.error(f"Количество предметов перед записью ({saved_item_count}) не совпадает с количеством после чтения ({loaded_item_count})!")
                print("Ошибка: количество сохраненных предметов не совпадает с ожидаемым!")

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