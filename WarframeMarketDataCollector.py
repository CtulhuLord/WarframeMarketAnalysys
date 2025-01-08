import requests
import json
import time
import argparse
import sys
from tqdm import tqdm

def get_item_data(item_url):
    """Получает данные об отдельном предмете."""
    try:
        response = requests.get(item_url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при получении данных с {item_url}: {e}")
        return None

def process_item_data(item_data):
    """Извлекает нужные поля из данных предмета, обрабатывая наборы."""

    if not item_data or "payload" not in item_data or "item" not in item_data["payload"]:
        print(f"Некорректные данные предмета: {item_data}")
        return None

    item = item_data["payload"]["item"]
    item_id = item.get("id")

    if not item_id:
        print(f"Отсутствует id для предмета: {item}")
        return None

    result = {
        "id": item_id,
    }

    if "items_in_set" in item and isinstance(item["items_in_set"], list):
        for set_item in item["items_in_set"]:
            if set_item.get("id") == item_id:
                result["url_name"] = set_item.get("url_name")
                result["ducats"] = set_item.get("ducats")
                result["trading_tax"] = set_item.get("trading_tax")

                # Проверяем, является ли найденный элемент сетом
                if result["url_name"] and result["url_name"].endswith("set"):
                    set_components = []
                    for component in item["items_in_set"]:
                        if component.get("url_name") and component.get("url_name") != result["url_name"]:
                            set_components.append(component.get("url_name"))
                    result["components"] = set_components
                break  # Прерываем цикл после обработки нужного элемента
    return result

def fetch_item_data(item_name):
    """Получает данные о предмете с warframe.market."""
    url = f"https://api.warframe.market/v1/items/{item_name}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к warframe.market: {e}")
        return None

def main():
    """Собирает информацию о предметах и сохраняет в файл."""
    parser = argparse.ArgumentParser(description="Собирает данные о предметах Warframe Market.")
    parser.add_argument("-n", "--num_items", type=int, default=0,
                        help="Количество предметов для проверки (0 - все).")
    parser.add_argument("--test", action="store_true", help="Запустить в тестовом режиме для strun_prime_receiver.")
    parser.add_argument("--item", type=str, help="Запустить в тестовом режиме для указанного предмета")
    parser.add_argument("-o", "--output", type=str, default="warframe_items.json", help="Имя выходного файла") # Добавлено

    args = parser.parse_args()
    output_filename = args.output  # Получаем имя файла из аргументов

    items_to_process = []

    if args.test or args.item:
        item_name = args.item if args.item else "strun_prime_receiver"
        items_to_process.append({"url_name": item_name})
        print(f"Запуск в тестовом режиме. Запрос для: {item_name}")
    else:  # Обычный режим
        base_url = "https://api.warframe.market/v1"
        items_url = f"{base_url}/items"

        try:
            items_response = requests.get(items_url)
            items_response.raise_for_status()
            items_data = items_response.json()["payload"]["items"]
            num_items_to_check = args.num_items if args.num_items > 0 else len(items_data)
            items_to_process = items_data[:num_items_to_check]  # Используем список из API
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при получении списка предметов: {e}")
            return
        except json.JSONDecodeError as e:
            print(f"Ошибка при разборе JSON: {e}")
            return
        except Exception as e:
            print(f"Произошла непредвиденная ошибка: {e}")
            return
    
    all_items_data = []
    with tqdm(total=len(items_to_process), desc="Обработка предметов") as pbar:
        for item in items_to_process: # Используем созданный список
            item_details_url = f"https://api.warframe.market/v1/items/{item['url_name']}"
            item_data = get_item_data(item_details_url)
            if item_data:
                processed_item = process_item_data(item_data)
                all_items_data.append(processed_item)
            time.sleep(0.1)
            pbar.update(1)

    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(all_items_data, f, indent=4, ensure_ascii=False)
        print(f"Данные о {len(all_items_data)} предметах сохранены в файл {output_filename}")
    except Exception as e:
        print(f"Ошибка при записи в файл: {e}")

if __name__ == "__main__":
    main()