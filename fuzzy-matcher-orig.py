from thefuzz import fuzz
from thefuzz import process
import csv
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


MATCH_COLUMN = "address"
NAME_COLUMN = "name"
ADDRESS_MATCH_THRESHOLD = 98
NAME_MATCH_THRESHOLD = 98
# Для названий: token_sort_ratio, чтобы "Гостиница" не матчилась на "Гостиница Восточная" со 100%
NAME_SCORER = fuzz.token_sort_ratio


def latest_csv_file(directory: Path) -> Path | None:
    """Последний по имени CSV в директории (формат YYYY-MM-DD.csv)."""
    if not directory.is_dir():
        return None
    files = sorted(directory.glob("*.csv"))
    return files[-1] if files else None


def load_address_name_map(csv_path: Path) -> dict:
    """Читает CSV и возвращает словарь {адрес: название отеля}."""
    mapping: dict = {}
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                address = row.get(MATCH_COLUMN)
                name = row.get(NAME_COLUMN, "")
                if address and address not in mapping:
                    mapping[address] = name
    except Exception as e:
        logger.error("Не удалось прочитать %s: %s", csv_path, e)
    return mapping


def match_hotels(ostrovok: dict, tvil: dict) -> list[dict]:
    """Нечётко сопоставляет отели из двух словарей {адрес: название}.

    Два прохода: по адресам (порог 98) и по названиям (порог 98).
    Возвращает список совпадений.
    """

    results = []
    matched_pairs = set()

    # 1. Проход по адресам: если порог по адресу >= 98 — мэтчим
    ostrovok_addresses = list(ostrovok.keys())
    tvil_addresses = list(tvil.keys())
    for address in ostrovok_addresses:
        best_match, address_score = process.extractOne(
            address,
            tvil_addresses,
            scorer=fuzz.token_set_ratio,
        )
        ostrovok_name = ostrovok[address]
        tvil_name = tvil.get(best_match, "") if best_match else ""
        name_score = NAME_SCORER(ostrovok_name, tvil_name) if ostrovok_name and tvil_name else None

        if address_score >= ADDRESS_MATCH_THRESHOLD:
            results.append({
                'ostrovok_address': address,
                'tvil_address': best_match,
                'address_score': address_score,
                'ostrovok_name': ostrovok_name,
                'tvil_name': tvil_name,
                'name_score': name_score,
                'match_type': 'address',
            })
            matched_pairs.add((address, best_match))

    # 2. Проход по названиям: если порог по названию высокий — мэтчим (без дубликатов)
    ostrovok_names = list(ostrovok.values())
    tvil_names = list(tvil.values())
    for ostrovok_address, ostrovok_name in ostrovok.items():
        best_name_match, name_score = process.extractOne(
            ostrovok_name,
            tvil_names,
            scorer=NAME_SCORER,
        )
        tvil_address = None
        for addr, name in tvil.items():
            if name == best_name_match:
                tvil_address = addr
                break
        if name_score is not None and name_score >= NAME_MATCH_THRESHOLD and (ostrovok_address, tvil_address) not in matched_pairs:
            results.append({
                'ostrovok_address': ostrovok_address,
                'tvil_address': tvil_address,
                'address_score': fuzz.token_set_ratio(ostrovok_address, tvil_address) if tvil_address else None,
                'ostrovok_name': ostrovok_name,
                'tvil_name': best_name_match,
                'name_score': name_score,
                'match_type': 'name',
            })
            matched_pairs.add((ostrovok_address, tvil_address))

    return results


def save_results(results: list[dict], output_file: Path) -> None:
    """Сохраняет результаты сопоставления в CSV-файл."""
    fieldnames = ['ostrovok_address', 'tvil_address', 'address_score', 'ostrovok_name', 'tvil_name', 'name_score', 'match_type']
    try:
        with open(output_file, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        logger.info("Результаты сохранены в %s", output_file)
    except Exception as e:
        logger.error("Не удалось записать результаты в %s: %s", output_file, e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    base_dir = Path(__file__).parent

    ostrovok_csv = latest_csv_file(base_dir / "ostrovok-tables" / "hotels")
    tvil_csv = latest_csv_file(base_dir / "tvil-tables" / "hotels")

    if not ostrovok_csv:
        logger.warning("CSV-файл Ostrovok не найден")
    if not tvil_csv:
        logger.warning("CSV-файл Tvil не найден")

    ostrovok_map = load_address_name_map(ostrovok_csv) if ostrovok_csv else {}
    tvil_map = load_address_name_map(tvil_csv) if tvil_csv else {}

    results = match_hotels(ostrovok_map, tvil_map)
    results.sort(key=lambda r: r['address_score'], reverse=True)

    save_results(results, base_dir / 'match_results.csv')