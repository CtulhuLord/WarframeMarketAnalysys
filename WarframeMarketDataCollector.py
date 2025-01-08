import requests
import json
import logging
import time
import os
import glob
import argparse
from logging.handlers import RotatingFileHandler
from tqdm import tqdm

# Настройка логирования
log_format = '%(asctime)s - %(levelname)s - %(message)s'
log_file_base = 'collector'
log_file = f'{log_file_base}.log'
log_handler = RotatingFileHandler(log_file, maxBytes=3*1024*1024, backupCount=9, encoding='utf-8')
log_handler.setFormatter(logging.Formatter(log_format))
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(log_handler)

def cleanup_old_logs(log_file_base):
    log_files = glob.glob(f"{log_file_base}*.log")
    log_files.sort(key=os.path.getmtime)
    if len(log_files) > 10:
        files_to_delete = log_files[:-10]
        for file_to_delete in files_to_delete:
            try:
                os.remove(file_to_delete)
                logger.info(f"Удален старый лог-файл: {file_to_delete}")
            except OSError as e:
                logger.error(f"Ошибка при удалении лог-файла {file_to_delete}: {e}")

def fetch_all_items():
    url = "https://api.warframe.market/v1/items"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data["payload"]["items"]
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при получении списка предметов: {e}")
        return None

def fetch_item_data(item_url_name, retries=5, initial_delay=1, max_delay=60):
    url = f"https://api.warframe.market/v1/items/{item_url_name}"
    delay = initial_delay
    for attempt in range(retries):
        try:
            logger.debug(f"Запрос URL: {url} (Попытка {attempt+1})")
            response = requests.get(url, timeout=10) # Таймаут 10 секунд
            logger.debug(f"Статус ответа: {response.status_code}")
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 1))
                delay = min(delay * 2, max_delay)
                logger.warning(f"Получена ошибка 429 для {item_url_name}, повтор через {retry_after} секунд (попытка {attempt+1}).")
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            text = response.text
            logger.debug(f"Текст ответа (до 500 символов): {text[:500]}...")
            data = response.json()
            logger.debug(f"JSON данные: {data}")
            item_data = data.get("payload", {}).get("item")
            logger.debug(f"item_data: {item_data}")
            if item_data:
                if 'url_name' in item_data:
                    logger.info(f"Успешно получены данные для предмета: {item_url_name}")
                    return item_data
                else:
                    logger.error(f"В item_data отсутствует ключ 'url_name' для {item_url_name}. data: {data}")
                    return None
            else:
                logger.warning(f"Получены пустые данные для предмета {item_url_name}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при получении данных о предмете {item_url_name} (попытка {attempt+1}): {e}")
            if attempt < retries - 1:
                delay = min(delay * 2, max_delay)
                logger.info(f"Повторная попытка через {delay} секунд...")
                time.sleep(delay)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON для {item_url_name} (попытка {attempt+1}): {e}, текст ответа: {text[:500]}...", exc_info=True)
            return None
        except (KeyError, TypeError) as e:
            logger.error(f"Ошибка структуры данных для {item_url_name} (попытка {attempt+1}): {e}", exc_info=True)
            return None
    logger.error(f"Не удалось получить данные для {item_url_name} после {retries} попыток.")
    return None

def main():
    parser = argparse.ArgumentParser(description="Сбор данных с Warframe Market.")
    parser.add_argument("--limit", type=int, default=0, help="Ограничение количества обрабатываемых предметов (0 - все).")
    args = parser.parse_args()

    start_time = time.time()
    logger.info("Начало сбора данных")
    print("Начало сбора данных...")

    try:
        cleanup_old_logs(log_file_base)

        all_items_list = fetch_all_items()
        if all_items_list is None:
            logger.error("Не удалось получить список всех предметов.")
            print("Ошибка: не удалось получить список предметов.")
            return

        with open("all_items_list.json", "w", encoding="utf-8") as f:
            json.dump(all_items_list, f, indent=4, ensure_ascii=False)
        logger.info("Список всех предметов сохранен в all_items_list.json")
        print("Список всех предметов сохранен в all_items_list.json")

        all_items_data = {}
        successful_items = 0
        failed_items = 0

        items_to_process = all_items_list[:args.limit] if args.limit > 0 else all_items_list

        with tqdm(total=len(items_to_process), desc="Загрузка данных о предметах") as pbar:
            for item in items_to_process:
                item_data = fetch_item_data(item["url_name"])
                if item_data:
                    try:
                        all_items_data[item_data['url_name']] = item_data
                        successful_items += 1
                    except TypeError as e:
                        logger.error(f"Ошибка при добавлении данных в all_items_data для {item['url_name']}: {e}, item_data: {item_data}")
                        failed_items += 1 # Важно учесть и эту ошибку в failed_items
                else:
                    logger.warning(f"Не удалось получить данные для {item['url_name']}")
                    failed_items += 1 # <- Вот это было пропущено!

                time.sleep(0.5)
                pbar.update(1)

        with open("all_items_data.json", "w", encoding="utf-8") as f:
            json.dump(all_items_data, f, indent=4, ensure_ascii=False)

        logger.info(f"Успешно получено {successful_items} предметов.")
        logger.info(f"Не удалось получить {failed_items} предметов.")
        logger.info("Сбор данных завершен.")
        print("Сбор данных завершен.")

    except Exception as e:
        logger.exception(f"Произошла непредвиденная ошибка: {e}")
        print(f"Произошла непредвиденная ошибка: {e}")
    finally:
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"Время выполнения скрипта: {elapsed_time:.2f} секунд")
        print(f"Время выполнения: {elapsed_time:.2f} секунд")

if __name__ == "__main__":
    main()