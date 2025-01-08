import asyncio
import aiohttp
import json
import logging
import time
import os
from tqdm.asyncio import tqdm_asyncio
import sys

# Настройка логирования
log_format = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(filename='warframe_market_data.log', level=logging.INFO, format=log_format, encoding='utf-8')
logger = logging.getLogger(__name__)

# URL API
BASE_URL = "https://api.warframe.market/v1"

# Заголовки запроса
HEADERS = {"Accept": "application/json"}

async def fetch_data(session, url):
    """Асинхронно получает данные по URL с обработкой ошибок."""
    try:
        async with session.get(url, headers=HEADERS, timeout=10) as response:
            response.raise_for_status()
            return await response.json()
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка запроса к {url}: {e}")
        return None
    except asyncio.TimeoutError:
        logger.error(f"Превышено время ожидания при запросе к {url}")
        return None
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON ответа от {url}")
        return None

async def get_all_items(session):
    """Получает список всех предметов."""
    url = f"{BASE_URL}/items"
    data = await fetch_data(session, url)
    if data and "payload" in data and "items" in data["payload"]:
        return data["payload"]["items"]
    else:
        logger.error("Не удалось получить список предметов.")
        return None

async def get_item_details(session, item_url_name):
    """Получает детали предмета по его url_name."""
    url = f"{BASE_URL}/items/{item_url_name}"
    data = await fetch_data(session, url)
    if data and "payload" in data and "item" in data["payload"]:
        return data["payload"]["item"]
    else:
        logger.warning(f"Не удалось получить детали для {item_url_name}")
        return None

def remove_languages(data, languages_to_remove):
    """Удаляет указанные языковые данные из словаря."""
    for item_name, item_details in data.items():
        if "items_in_set" in item_details and isinstance(item_details["items_in_set"], list): #проверка на наличие items_in_set
            for item in item_details["items_in_set"]:
                for lang in languages_to_remove:
                    if lang in item:
                        del item[lang]
        else: #если items_in_set нет, значит это одиночный предмет
            for lang in languages_to_remove:
                if lang in item_details:
                    del item_details[lang]
    return data



async def main():
    start_time = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            all_items = await get_all_items(session)

            if all_items:
                all_items_data = {}
                tasks = [get_item_details(session, item["url_name"]) for item in all_items]
                results = await tqdm_asyncio.gather(*tasks, desc="Загрузка данных о предметах", unit="предмет", dynamic_ncols=True, file=sys.stdout)

                for i, item_details in enumerate(results):
                    if item_details:
                        all_items_data[all_items[i]["url_name"]] = item_details

                languages_to_remove = ["ko", "fr", "sv", "de", "zh-hant", "zh-hans", "pt", "es", "pl", "cs", "uk"]
                filtered_data = remove_languages(all_items_data, languages_to_remove)

                output_filename = "all_items_data_filtered.json"
                with open(output_filename, "w", encoding="utf-8") as f:
                    json.dump(filtered_data, f, indent=4, ensure_ascii=False)
                logger.info(f"Данные о всех предметах (кроме en и ru) сохранены в {output_filename}")

            else:
                logger.error("Не удалось получить список предметов. Завершение работы.")

    except Exception as e:
        logger.exception(f"Произошла непредвиденная ошибка: {e}")
    finally:
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"Время выполнения скрипта: {elapsed_time:.2f} секунд")

if __name__ == "__main__":
    asyncio.run(main())