from thefuzz import fuzz
from thefuzz import process
import csv
import sys
from datetime import date
from pathlib import Path
import logging

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(line_buffering=True)

logger = logging.getLogger(__name__)

class FuzzyMatcher:
    def __init__(self):
        self.match_column = "address"
        self.name_column = "name"

        # match threshold >=98 so it's a good match
        self.address_match_threshold = 98
        self.name_match_threshold = 98

        # Для названий используем более точный scorer token_sort_ratio, чтобы "Гостиница" не матчилась на "Гостиница Восточная" со 100%
        self.name_scorer = fuzz.token_sort_ratio
        self.address_scorer = fuzz.token_set_ratio

    def _build_name_to_address_map(self, address_to_name):
        """Строит словарь {название: адрес} для обратного поиска."""
        return {name: address for address, name in address_to_name.items() if name}


    def latest_csv_file(self, directory):
        """Последний по дате CSV в директории (формат YYYY-MM-DD.csv)."""
        if not directory.is_dir():
            return None
        files = sorted(directory.glob("*.csv"))
        return files[-1] if files else None

    def load_address_name_map(self, csv_file):
        """Читает CSV и возвращает словарь {адрес: название отеля}."""
        mapping = {}
        try:    
            with open(csv_file, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    address = row.get(self.match_column)
                    name = row.get(self.name_column, "")
                    if address and address not in mapping:
                        mapping[address] = name
        except Exception as e:
            logger.error("Не удалось прочитать %s: %s", csv_file, e)
        return mapping
    
    def match_catalogs(self, ostrovok_map, tvil_map):
        """Нечётко сопоставляет отели из двух каталогов {адрес: название}.

        Два прохода: по адресам (порог self.address_match_threshold) и по названиям (порог self.name_match_threshold).
        Возвращает список совпадений.
        """

        results = []
        matched_pairs = set()
        ostrovok_name_to_address = self._build_name_to_address_map(ostrovok_map)
        tvil_name_to_address = self._build_name_to_address_map(tvil_map)

        # 1. Проход по адресам: если порог по адресу >= 98 — мэтчим
        ostrovok_addresses = list(ostrovok_map.keys())
        tvil_addresses = list(tvil_map.keys())
        for address in ostrovok_addresses:
            best_match, address_score = process.extractOne(
                address,
                tvil_addresses,
                scorer=self.address_scorer,
            )
            ostrovok_name = ostrovok_map[address]
            tvil_name = tvil_map.get(best_match, "") if best_match else ""
            name_score = self.name_scorer(ostrovok_name, tvil_name) if ostrovok_name and tvil_name else None

            if address_score >= self.address_match_threshold:
                results.append({
                    'match_type': 'address',
                    'ostrovok_address': address,
                    'tvil_address': best_match,
                    'address_score': address_score,
                    'ostrovok_name': ostrovok_name,
                    'tvil_name': tvil_name,
                    'name_score': name_score,
                })
                matched_pairs.add((address, best_match))

        # 2. Проход по названиям: если порог по названию высокий — мэтчим (без дубликатов)
        ostrovok_names = list(ostrovok_map.values())
        tvil_names = list(tvil_map.values())
        for ostrovok_name in ostrovok_names:
            best_name_match, name_score = process.extractOne(
                ostrovok_name,
                tvil_names,
                scorer=self.name_scorer,
            )
            ostrovok_address = ostrovok_name_to_address.get(ostrovok_name, "")
            tvil_address = tvil_name_to_address.get(best_name_match, "")
            address_score = fuzz.token_set_ratio(ostrovok_address, tvil_address) if tvil_address else None

            if name_score is not None and name_score >= self.name_match_threshold and (ostrovok_address, tvil_address) not in matched_pairs:
                results.append({
                    'match_type': 'name',
                    'ostrovok_address': ostrovok_address,
                    'tvil_address': tvil_address,
                    'address_score': address_score,
                    'ostrovok_name': ostrovok_name,
                    'tvil_name': best_name_match,
                    'name_score': name_score,
                })
                matched_pairs.add((ostrovok_address, tvil_address))

        return results

    
    def save_results(self, results, output_file):
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
    base_dir = Path(__file__).resolve().parent
    repo_root = base_dir.parent
    ostrovok_catalog_dir = repo_root / "ostrovok-data" / "catalog"
    tvil_catalog_dir = repo_root / "tvil-data" / "catalog"
    match_results_dir = base_dir / "match-results"

    matcher = FuzzyMatcher()
    ostrovok_csv = matcher.latest_csv_file(ostrovok_catalog_dir)
    tvil_csv = matcher.latest_csv_file(tvil_catalog_dir)
    
    if not ostrovok_csv:
        logger.warning("CSV каталога Ostrovok не найден в %s", ostrovok_catalog_dir)
    if not tvil_csv:
        logger.warning("CSV каталога Tvil не найден в %s", tvil_catalog_dir)

    ostrovok_map = matcher.load_address_name_map(ostrovok_csv) if ostrovok_csv else {}
    tvil_map = matcher.load_address_name_map(tvil_csv) if tvil_csv else {}

    results = matcher.match_catalogs(ostrovok_map, tvil_map)
    results.sort(key=lambda r: r["address_score"], reverse=True)

    match_results_dir.mkdir(parents=True, exist_ok=True)
    out_path = match_results_dir / f"{date.today().isoformat()}.csv"
    matcher.save_results(results, out_path)