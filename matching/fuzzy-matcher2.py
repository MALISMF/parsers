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

        # Для названий используем более точный scorer token_sort_ratio
        self.name_scorer = fuzz.token_sort_ratio
        self.address_scorer = fuzz.token_set_ratio

    @staticmethod
    def _score_key(r):
        v = r.get("address_score")
        if v is None or v == "":
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    def run(self, ostrovok_dir, tvil_dir, output_file):
        # 1. Поиск файлов
        ostrovok_csv = self.latest_csv_file(ostrovok_dir)
        tvil_csv = self.latest_csv_file(tvil_dir)

        if not ostrovok_csv:
            logger.warning("CSV каталога Ostrovok не найден в %s", ostrovok_dir)
        if not tvil_csv:
            logger.warning("CSV каталога Tvil не найден в %s", tvil_dir)

        # 2. Загрузка данных
        ostrovok_map = self.load_address_name_map(ostrovok_csv) if ostrovok_csv else {}
        tvil_map = self.load_address_name_map(tvil_csv) if tvil_csv else {}
        existing = self.load_existing_matches(output_file)

        # 3. Матчинг
        new_results = self.match_catalogs(ostrovok_map, tvil_map)
        new_results.sort(key=self._score_key, reverse=True)

        # 4. Слияние и сохранение
        final_results = self.merge_with_existing(new_results, existing)
        final_results.sort(key=self._score_key, reverse=True)

        self.save_results(final_results, output_file)

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

    def load_existing_matches(self, output_file):
        """Загружает уже сохранённые матчи из единого файла."""
        existing = {}
        if not output_file.exists():
            return existing
        try:
            with open(output_file, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    key = (row.get("ostrovok_address", ""), row.get("tvil_address", ""))
                    existing[key] = row
            logger.info("Загружено существующих матчей: %d", len(existing))
        except Exception as e:
            logger.error("Не удалось прочитать существующие матчи из %s: %s", output_file, e)
        return existing

    def match_catalogs(self, ostrovok_map, tvil_map):
        """Нечётко сопоставляет отели из двух каталогов {адрес: название}."""
        results = []
        matched_pairs = set()
        matched_tvil_addresses = set()
        ostrovok_name_to_address = self._build_name_to_address_map(ostrovok_map)
        tvil_name_to_address = self._build_name_to_address_map(tvil_map)

        # 1. Проход по адресам
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
                matched_tvil_addresses.add(best_match)

        # 2. Проход по названиям
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
                matched_tvil_addresses.add(tvil_address)

        return results

    def merge_with_existing(self, new_results, existing):
        """Объединяет новые матчи с существующими."""
        merged = dict(existing)

        for row in new_results:
            key = (row.get("ostrovok_address", ""), row.get("tvil_address", ""))
            if key not in merged:
                logger.info(
                    "Новый матч [%s]: '%s' ↔ '%s'  (addr_score=%s, name_score=%s)",
                    row.get("match_type"),
                    row.get("ostrovok_name"),
                    row.get("tvil_name"),
                    row.get("address_score"),
                    row.get("name_score"),
                )
            merged[key] = row

        removed = set(existing.keys()) - {
            (r.get("ostrovok_address", ""), r.get("tvil_address", "")) for r in new_results
        }
        for key in removed:
            logger.warning(
                "Матч пропал из результатов: '%s' ↔ '%s'",
                existing[key].get("ostrovok_name"),
                existing[key].get("tvil_name"),
            )

        return list(merged.values())

    def save_results(self, results, output_file):
        """Сохраняет все матчи в единый файл."""
        fieldnames = ['ostrovok_address', 'tvil_address', 'address_score', 'ostrovok_name', 
        'tvil_name', 'name_score', 'match_type']
        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results)
            logger.info("Сохранено матчей: %d -> %s", len(results), output_file)
        except Exception as e:
            logger.error("Не удалось записать результаты в %s: %s", output_file, e)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from log_config import setup_logging, get_log_file_path

    run_date = date.today().isoformat()
    log_file = get_log_file_path(run_date)
    setup_logging(log_file=log_file)

    base_dir = Path(__file__).resolve().parent
    repo_root = base_dir.parent
    
    # Конфигурация путей
    ostrovok_dir = repo_root / "ostrovok-data" / "catalog"
    tvil_dir = repo_root / "tvil-data" / "catalog"
    output_path = base_dir / "match-results" / "matches.csv"

    # Запуск
    matcher = FuzzyMatcher()
    matcher.run(ostrovok_dir, tvil_dir, output_path)