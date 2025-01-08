import asyncio
import aiohttp
import json
import logging
import time
from tqdm.asyncio import tqdm_asyncio  # Импортируем tqdm для asyncio

# Настройка логирования
logging.basicConfig(filename='collector.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def fetch_item_data(session, item_url_name):
    """Получает данные об одном предмете."""
    try:
        url = f"https://api.warframe.market/v1/items/{item_url_name}"
        async with session.get(url) as response:
            if response.status != 200:
                logger.error(f"Ошибка при запросе {item_url_name}: статус {response.status}")
                return None
            data = await response.json()
            return data["payload"]["item"] # Возвращаем непосредственно данные предмета
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка сети при запросе {item_url_name}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON для {item_url_name}: {e}")
        return None
    except KeyError as e:
        logger.error(f"Ошибка структуры JSON для {item_url_name}: Отсутствует ключ {e}")
        return None
    except Exception as e:
        logger.exception(f"Непредвиденная ошибка при запросе {item_url_name}: {e}")
        return None

async def fetch_all_items(session):
    """Получает список всех предметов."""
    try:
        url = "https://api.warframe.market/v1/items"
        async with session.get(url) as response:
            if response.status != 200:
                logger.error(f"Ошибка при запросе списка всех предметов: статус {response.status}")
                return None
            data = await response.json()
            return data["payload"]["items"]
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка сети при запросе списка всех предметов: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON списка предметов: {e}")
        return None
    except KeyError as e:
        logger.error(f"Ошибка структуры JSON списка предметов: Отсутствует ключ {e}")
        return None
    except Exception as e:
        logger.exception(f"Непредвиденная ошибка при запросе списка предметов: {e}")
        return None

async def main():
    start_time = time.time()
    logger.info("Начало сбора данных")

    try:
        async with aiohttp.ClientSession() as session:
            all_items_list = await fetch_all_items(session)

            if all_items_list is None:
                logger.error("Не удалось получить список всех предметов.")
                return

            all_items_data = {}

            # Используем tqdm_asyncio.as_completed для отображения прогресса
            tasks = [fetch_item_data(session, item["url_name"]) for item in all_items_list]
            for item_data in tqdm_asyncio.as_completed(tasks, desc="Загрузка данных о предметах", total=len(tasks)):
                if item_data:
                    all_items_data[item_data['url_name']] = item_data # Используем url_name из полученных данных

            with open("all_items_data.json", "w", encoding="utf-8") as f:
                json.dump(all_items_data, f, indent=4, ensure_ascii=False)

            logger.info("Сбор данных завершен.")

            # Проверка количества наименований (игнорируя вложения)
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