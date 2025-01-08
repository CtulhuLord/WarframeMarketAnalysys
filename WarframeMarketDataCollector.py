import logging
import asyncio
import aiohttp
import json
import time
from tqdm.asyncio import tqdm_asyncio

# Logging Configuration (Optional, but recommended)
logging.basicConfig(
    filename='collector.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Create the logger (after logging config)
logger = logging.getLogger(__name__)

async def fetch_all_items(session):
    try:
        url = "https://api.warframe.market/v1/items"
        headers = {"Language": "en"}
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                logger.error(f"Ошибка при запросе списка всех предметов: {response.status}")
                return None
            data = await response.json()

            logger.debug(f"Ответ API (all_items): {json.dumps(data, indent=4, ensure_ascii=False)}")
            if "payload" not in data or "items" not in data["payload"]:
                logger.error(f"Некорректная структура ответа API: Отсутствуют ключи 'payload' или 'items'")
                return None

            return data["payload"]["items"]

    except aiohttp.ClientError as e:
        logger.error(f"Ошибка сети при запросе списка всех предметов: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON списка всех предметов: {e}")
        return None
    except KeyError as e:
        logger.error(f"Ошибка структуры JSON списка всех предметов: Отсутствует ключ {e}")
        return None
    except Exception as e:
        logger.exception(f"Непредвиденная ошибка: {e}")
        return None

async def fetch_item_data(session, item_url_name):
    await asyncio.sleep(0.1)
    return {'url_name': item_url_name, 'test': 'data'}

async def main():
    start_time = time.time()
    logger.info("Начало сбора данных")

    try:
        async with aiohttp.ClientSession() as session:
            all_items_list = await fetch_all_items(session)

            if all_items_list is None:
                logger.error("Не удалось получить список всех предметов.")
                return

            item_count = len(all_items_list) if all_items_list else 0
            logger.info(f"Получено {item_count} предметов.")

            if item_count == 0:
                logger.warning("Список предметов пуст. Проверьте запрос к API.")
                return

            all_items_data = {}

            tasks = [fetch_item_data(session, item["url_name"]) for item in all_items_list]
            for future in tqdm_asyncio.as_completed(tasks, desc="Загрузка данных о предметах", total=len(tasks)):
                logger.debug(f"Начало обработки предмета")
                try:
                    item_data = await future
                    if item_data:
                        all_items_data[item_data['url_name']] = item_data
                except Exception as e:
                    logger.exception(f"Ошибка при обработке предмета: {e}")

            with open("all_items_data.json", "w", encoding="utf-8") as f:
                json.dump(all_items_data, f, indent=4, ensure_ascii=False)

            logger.info("Сбор данных завершен.")

            with open("all_items_data.json", "r", encoding="utf-8") as f:
                loaded_data = json.load(f)

            item_count = len(loaded_data)
            logger.info(f"Количество сохраненных предметов: {item_count}")

    except Exception as e:
        logger.exception(f"Произошла непредвиденная ошибка: {e}")
    finally:
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"Время выполнения скрипта: {elapsed_time:.2f} секунд")

if __name__ == "__main__":
    asyncio.run(main())