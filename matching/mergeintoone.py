import csv
import logging
import sys
from datetime import date
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(line_buffering=True)

logger = logging.getLogger(__name__)

class CatalogMerger:
    def run(self, match_results_path, ostrovok_dir, tvil_dir, output_path):
        """Входная точка: координирует поиск файлов, слияние и сохранение."""
        
        # 1. Поиск необходимых файлов
        ostrovok_hotels = self.latest_csv_file(ostrovok_dir)
        tvil_hotels = self.latest_csv_file(tvil_dir)

        # 2. Проверки наличия файлов
        if not match_results_path.is_file():
            logger.error("Нет файла %s — сначала запустите fuzzy-matcher2.py", match_results_path)
            return
        
        if not ostrovok_hotels or not tvil_hotels:
            logger.error("Не найдены необходимые CSV каталоги в %s или %s", ostrovok_dir, tvil_dir)
            return

        # 3. Выполнение слияния
        final_rows = self.merge(match_results_path, ostrovok_hotels, tvil_hotels)
        
        # 4. Сохранение результата
        if final_rows:
            self.save_results(final_rows, output_path)

    def merge(self, match_results_path, ostrovok_hotels_path, tvil_hotels_path):
        """Основная логика объединения каталогов."""
        logger.info("Начало процесса слияния каталогов...")
        
        matches = self._read_csv_rows(match_results_path)
        ostrovok_rows = self._read_csv_rows(ostrovok_hotels_path)
        tvil_rows = self._read_csv_rows(tvil_hotels_path)

        ostrovok_by_address = self._index_by_address(ostrovok_rows, "address")
        tvil_by_address = self._index_by_address(tvil_rows, "address")

        matched_ostrovok_addresses = set()
        matched_tvil_addresses = set()
        out_rows = []
        next_id = 1

        # 1) Обработка совпадений (matched)
        logger.info("Обработка найденных совпадений из %s", match_results_path.name)
        for m in matches:
            o_addr = self._norm(m.get("ostrovok_address"))
            t_addr = self._norm(m.get("tvil_address"))
            
            if o_addr: matched_ostrovok_addresses.add(o_addr)
            if t_addr: matched_tvil_addresses.add(t_addr)

            o = ostrovok_by_address.get(o_addr, {})
            t = tvil_by_address.get(t_addr, {})

            out_rows.append({
                "merged_id": next_id,
                "match_type": self._norm(m.get("match_type")) or "matched",
                "address_score": self._norm(m.get("address_score")),
                "name_score": self._norm(m.get("name_score")),
                "city": self._norm(o.get("city")) or self._norm(t.get("city")),
                "name": self._norm(o.get("name")) or self._norm(m.get("ostrovok_name")) or self._norm(t.get("name")) or self._norm(m.get("tvil_name")),
                "address": self._norm(o.get("address")) or o_addr or self._norm(t.get("address")) or t_addr,
                "lat": self._norm(o.get("latitude")) or self._norm(t.get("latitude")),
                "lon": self._norm(o.get("longitude")) or self._norm(t.get("longitude")),
                "rooms_number": self._norm(o.get("rooms_number")) or self._norm(t.get("rooms_number")),
                "ostrovok_ota_hotel_id": self._norm(o.get("ota_hotel_id")),
                "ostrovok_master_id": self._norm(o.get("master_id")),
                "ostrovok_name": self._norm(o.get("name")) or self._norm(m.get("ostrovok_name")),
                "ostrovok_address": o_addr or self._norm(o.get("address")),
                "ostrovok_url": self._norm(o.get("url")),
                "ostrovok_rooms_number": self._norm(o.get("rooms_number")),
                "tvil_hotel_id": self._norm(t.get("tvil_hotel_id")),
                "tvil_name": self._norm(t.get("name")) or self._norm(m.get("tvil_name")),
                "tvil_address": t_addr or self._norm(t.get("address")),
                "tvil_url": self._norm(t.get("url")),
                "tvil_rooms_number": self._norm(t.get("rooms_number")),
            })
            next_id += 1

        # 2) Не замэтченные из Ostrovok
        for o in ostrovok_rows:
            o_addr = self._norm(o.get("address"))
            if not o_addr or o_addr in matched_ostrovok_addresses:
                continue
            out_rows.append({
                "merged_id": next_id,
                "match_type": "unmatched_ostrovok",
                "city": self._norm(o.get("city")),
                "name": self._norm(o.get("name")),
                "address": o_addr,
                "lat": self._norm(o.get("latitude")),
                "lon": self._norm(o.get("longitude")),
                "rooms_number": self._norm(o.get("rooms_number")),
                "ostrovok_ota_hotel_id": self._norm(o.get("ota_hotel_id")),
                "ostrovok_master_id": self._norm(o.get("master_id")),
                "ostrovok_name": self._norm(o.get("name")),
                "ostrovok_address": o_addr,
                "ostrovok_url": self._norm(o.get("url")),
                "ostrovok_rooms_number": self._norm(o.get("rooms_number")),
            })
            next_id += 1

        # 3) Не замэтченные из Tvil
        for t in tvil_rows:
            t_addr = self._norm(t.get("address"))
            if not t_addr or t_addr in matched_tvil_addresses:
                continue
            out_rows.append({
                "merged_id": next_id,
                "match_type": "unmatched_tvil",
                "city": self._norm(t.get("city")),
                "name": self._norm(t.get("name")),
                "address": t_addr,
                "lat": self._norm(t.get("latitude")),
                "lon": self._norm(t.get("longitude")),
                "rooms_number": self._norm(t.get("rooms_number")),
                "tvil_hotel_id": self._norm(t.get("tvil_hotel_id")),
                "tvil_name": self._norm(t.get("name")),
                "tvil_address": t_addr,
                "tvil_url": self._norm(t.get("url")),
                "tvil_rooms_number": self._norm(t.get("rooms_number")),
            })
            next_id += 1

        return out_rows

    def save_results(self, rows, output_path):
        """Записывает итоговый список строк в файл и выводит статистику."""
        fieldnames = [
            "merged_id", "match_type", "address_score", "name_score",
            "city", "name", "address", "lat", "lon", "rooms_number",
            "ostrovok_ota_hotel_id", "ostrovok_master_id", "ostrovok_name",
            "ostrovok_address", "ostrovok_url", "ostrovok_rooms_number",
            "tvil_hotel_id", "tvil_name", "tvil_address",
            "tvil_url", "tvil_rooms_number",
        ]
        
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
            
            logger.info("--- ИТОГО ---")
            logger.info("Всего строк в каталоге: %d", len(rows))
            logger.info("Совпадений (matched): %d", sum(1 for r in rows if r.get("match_type") not in ("unmatched_ostrovok", "unmatched_tvil")))
            logger.info("Только Ostrovok: %d", sum(1 for r in rows if r.get("match_type") == "unmatched_ostrovok"))
            logger.info("Только Tvil: %d", sum(1 for r in rows if r.get("match_type") == "unmatched_tvil"))
            logger.info("Результат сохранен в: %s", output_path)
        except Exception as e:
            logger.error("Не удалось сохранить результаты в %s: %s", output_path, e)

    def latest_csv_file(self, directory):
        """Находит последний по имени CSV файл в директории."""
        if not directory.is_dir():
            return None
        files = sorted(directory.glob("*.csv"))
        return files[-1] if files else None

    # --- Приватные утилиты ---

    def _norm(self, s):
        """Вспомогательный метод для нормализации строк."""
        return ("" if s is None else str(s)).strip()

    def _read_csv_rows(self, path):
        """Читает CSV и возвращает список словарей."""
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
                logger.info("Файл прочитан: %s (строк: %d)", path.name, len(rows))
                return rows
        except Exception as e:
            logger.error("Ошибка при чтении файла %s: %s", path, e)
            return []

    def _index_by_address(self, rows, address_col):
        """Индексирует строки по адресу для быстрого поиска."""
        out = {}
        for row in rows:
            addr = self._norm(row.get(address_col))
            if not addr:
                continue
            out.setdefault(addr, row)
        return out


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from log_config import setup_logging, get_log_file_path
        run_date = date.today().isoformat()
        setup_logging(log_file=get_log_file_path(run_date))
    except ImportError:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        logger.warning("Модуль log_config не найден, логирование в файл отключено.")

    base_dir = Path(__file__).resolve().parent
    repo_root = base_dir.parent

    match_results = base_dir / "match-results" / "matches.csv"
    ostrovok_dir = repo_root / "ostrovok-data" / "catalog"
    tvil_dir = repo_root / "tvil-data" / "catalog"
    output_file = base_dir / "merge-results" / "matched-catalog.csv"

    merger = CatalogMerger()
    merger.run(match_results, ostrovok_dir, tvil_dir, output_file)