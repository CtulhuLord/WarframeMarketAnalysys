import json
import requests
import time
import argparse
import os
import subprocess

def load_item_data(filename="warframe_items.json"):
    """Загружает данные о предметах из JSON файла.

    Args:
        filename: Имя файла JSON.

    Returns:
        Список словарей с данными о предметах или None в случае ошибки.
    """
    try:
        with open(filename, "r", encoding="utf-8") as f:
            item_data = json.load(f)
            return item_data
    except FileNotFoundError:
        print(f"Ошибка: Файл '{filename}' не найден.")
        return None
    except json.JSONDecodeError:
        print(f"Ошибка: Некорректный формат JSON в файле '{filename}'.")
        return None
    except Exception as e:
        print(f"Произошла ошибка при чтении файла: {e}")
        return None

if __name__ == "__main__":
    items = load_item_data()
    if items:
        print("Данные успешно загружены.")
        # Здесь можно добавить дальнейшую обработку данных, если необходимо
        # Например, print(items[0]) для вывода первого элемента
    else:
        print("Загрузка данных не удалась.")

def get_highest_price(url_name):
    """Получает наибольшую цену *покупки* предмета с Warframe.Market API с учетом приоритета статусов."""
    url = f"https://api.warframe.market/v1/items/{url_name}/orders"
    headers = {'accept': 'application/json', 'Platform': 'pc'}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        orders_data = response.json()

        order_info = (0, "not_order", "unknown", "unknown")

        if "payload" in orders_data and "orders" in orders_data["payload"]:
            orders = orders_data["payload"]["orders"]

            for status in ["ingame", "online", "offline"]:
                highest_price_for_status = 0
                order_info_for_status = (0, "not_order", "unknown", "unknown")
                for order in orders:
                    if order["order_type"] == "buy" and order["user"].get("status") == status:
                        if order["platinum"] > highest_price_for_status:
                            highest_price_for_status = order["platinum"]
                            user = order.get("user", {})
                            order_info_for_status = (highest_price_for_status, order["id"], user.get("status", "unknown"), user.get("ingame_name", "unknown"))

                if order_info_for_status[0] != 0:
                    order_info = order_info_for_status
                    return order_info

        return order_info

    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к API Warframe.Market для {url_name}: {e}")
        return 0, "api_error", "unknown", "unknown"
    except json.JSONDecodeError as e:
        print(f"Ошибка при обработке JSON ответа для {url_name}: {e}")
        return 0, "json_error", "unknown", "unknown"
    except KeyError as e:
        print(f"Ошибка структуры JSON ответа для {url_name}: Отсутствует ключ {e}")
        return 0, "json_structure_error", "unknown", "unknown"

        
def get_lowest_price(url_name):
    """Получает наименьшую цену продажи с Warframe.Market API с учетом приоритета статусов (ingame > online > offline).
       Прекращает поиск, если найдена цена для более приоритетного статуса.

    Args:
        url_name: URL имя предмета.

    Returns:
        Кортеж: (наименьшая цена, идентификатор заказа, статус пользователя, никнейм пользователя)
        или (0, "not_order", "unknown", "unknown"), если ошибка или нет заказов.
    """
    url = f"https://api.warframe.market/v1/items/{url_name}/orders"
    headers = {'accept': 'application/json', 'Platform': 'pc'}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        orders_data = response.json()

        order_info = (0, "not_order", "unknown", "unknown")

        if "payload" in orders_data and "orders" in orders_data["payload"]:
            orders = orders_data["payload"]["orders"]

            for status in ["ingame", "online", "offline"]: #Перебираем статусы в порядке приоритета
                lowest_price_for_status = float('inf')
                order_info_for_status = (0, "not_order", "unknown", "unknown")
                for order in orders:
                    if order["order_type"] == "sell" and order["user"].get("status") == status:
                        if order["platinum"] < lowest_price_for_status:
                            lowest_price_for_status = order["platinum"]
                            user = order.get("user", {})
                            order_info_for_status = (lowest_price_for_status, order["id"], user.get("status", "unknown"), user.get("ingame_name", "unknown"))

                if order_info_for_status[0] != 0: #Если для данного статуса нашли хоть один ордер, то останавливаем поиск по другим статусам
                    order_info = order_info_for_status
                    return order_info #Немедленно возвращаем результат, прекращая дальнейший поиск

        return order_info

    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к API Warframe.Market для {url_name}: {e}")
        return 0, "api_error", "unknown", "unknown"
    except json.JSONDecodeError as e:
        print(f"Ошибка при обработке JSON ответа для {url_name}: {e}")
        return 0, "json_error", "unknown", "unknown"
    except KeyError as e:
        print(f"Ошибка структуры JSON ответа для {url_name}: Отсутствует ключ {e}")
        return 0, "json_structure_error", "unknown", "unknown"

def process_items_with_components(items, min_difference, num_items=None, shutdown=False): # Добавляем аргумент shutdown
    if not items:
        return

    items_with_components = [item for item in items if "components" in item]

    if num_items is not None:
        items_with_components = items_with_components[:num_items]

    output_filename = "profitable_items.txt"

    while True:  # Бесконечный цикл для повторной проверки
        profitable_items = []

        if os.path.exists(output_filename):
            try:
                with open(output_filename, "r", encoding="utf-8") as f:
                    profitable_items = [line.strip() for line in f]
            except Exception as e:
                print(f"Ошибка при чтении файла {output_filename}: {e}")

        items_to_check = items_with_components[:]

        for item in items_to_check:
            print("-" * 20)
            print(f"URL Name: {item['url_name']}")
            print("Components:")

            total_lowest_price = 0

            for component in item["components"]:
                lowest_price, _, _, _ = get_lowest_price(component)
                if lowest_price != float('inf') and lowest_price != 0:
                    total_lowest_price += lowest_price
                time.sleep(1)

            for component in item["components"]:
                print(f"  - {component}: Lowest Price = {get_lowest_price(component)[0]}")

            print(f"Total lowest price for components of {item['url_name']}: {total_lowest_price}")

            highest_price, _, _, _ = get_highest_price(item["url_name"])
            print(f"Highest buy price for {item['url_name']}: {highest_price}")

            difference = highest_price - total_lowest_price if highest_price and total_lowest_price else 0

            print(f"Difference between highest buy price and total lowest component price: {difference}")

            # Обновляем список и файл после *каждой* проверки предмета
            if isinstance(difference, int) and difference >= min_difference:
                if item['url_name'] not in profitable_items:
                    profitable_items.append(item['url_name'])
                    print(f"{item['url_name']} added to the list.")
            elif item['url_name'] in profitable_items:
                profitable_items.remove(item['url_name'])
                print(f"{item['url_name']} removed from the list.")
                
            try:
                with open(output_filename, "w", encoding="utf-8") as f:
                    for item_name in profitable_items:
                        f.write(item_name + "\n")
                print(f"Profitable items updated in {output_filename}")
            except Exception as e:
                print(f"Ошибка при записи в файл {output_filename}: {e}")

            print("-" * 20)

        if shutdown:  # Проверяем аргумент shutdown
            print("Shutdown argument provided. Initiating shutdown...")
            if os.name == 'nt':  # Для Windows
                subprocess.call(["shutdown", "/s", "/t", "1"]) # Выключение через 1 секунду
            elif os.name == 'posix':  # Для Linux/macOS
                subprocess.call(["shutdown", "-h", "now"]) # Немедленное выключение
            else:
                print("Shutdown command not implemented for this operating system.")
            break # Выходим из цикла после выключения

        time.sleep(60)  # Пауза перед следующей итерацией
    print("Processing complete.")


def main():
    parser = argparse.ArgumentParser(description="Получение цен на компоненты предметов Warframe с Warframe.Market.")
    parser.add_argument("-n", "--num-items", type=int, help="Количество предметов с components для обработки (по умолчанию обрабатываются все).")
    parser.add_argument("-m", "--min-difference", type=int, default=1, help="Минимальная разница в ценах для записи в файл (по умолчанию 1).")
    parser.add_argument("-s", "--shutdown", action="store_true", help="Выключить компьютер после завершения одной итерации цикла.") # Добавляем аргумент -s/--shutdown

    args = parser.parse_args()

    items = load_item_data()
    if not items:
        return

    process_items_with_components(items, args.min_difference, args.num_items, args.shutdown) # Передаем аргумент shutdown в функцию

if __name__ == "__main__":
    main()