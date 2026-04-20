"""
Объединяет matched-catalog.csv с ежедневной статистикой Ostrovok и Tvil.

Вход (относительно папки matching/):
  - merge-results/matched-catalog.csv
  - ../ostrovok-data/daily/statistics/<latest>.csv
  - ../tvil-data/daily/statistics/<latest>.csv

Выход:
  - ../all-data/<YYYY-MM-DD>.csv
"""

import csv
import logging
import sys
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(line_buffering=True)

def _extract_date_from_path(p: Path):
    if not p:
        return None
    try:
        datetime.strptime(p.stem, "%Y-%m-%d")
        return p.stem
    except Exception:
        return None

logger = logging.getLogger(__name__)

def _run_date():
    """Дата запуска по RUN_TZ (по умолчанию Asia/Irkutsk)."""
    tz_name = os.environ.get("RUN_TZ", "Asia/Irkutsk")
    try:
        return datetime.now(ZoneInfo(tz_name)).date()
    except Exception:
        return date.today()

class DailyStatsMerger:
    def run(self, catalog_path, ostrovok_stats_dir, tvil_stats_dir, output_path):
        """Входная точка: координирует поиск файлов, слияние и сохранение."""
        
        # 1. Поиск файлов
        ostrovok_stats_path = self.latest_csv_file(ostrovok_stats_dir)
        tvil_stats_path = self.latest_csv_file(tvil_stats_dir)

        # 2. Проверки наличия файлов
        if not catalog_path.is_file():
            logger.error("Нет файла каталога %s — сначала выполните слияние каталогов.", catalog_path)
            return
        
        if not ostrovok_stats_path:
            logger.error("Не найден CSV статистики Ostrovok в %s", ostrovok_stats_dir)
            return
            
        if not tvil_stats_path:
            logger.error("Не найден CSV статистики Tvil в %s", tvil_stats_dir)
            return

        logger.info("Используемый каталог: %s", catalog_path)
        logger.info("Статистика Ostrovok: %s", ostrovok_stats_path)
        logger.info("Статистика Tvil: %s", tvil_stats_path)

        # 3. Выполнение слияния
        final_rows = self.merge(catalog_path, ostrovok_stats_path, tvil_stats_path)
        
        # 4. Сохранение результата
        if final_rows:
            self.save_results(final_rows, output_path)

    def merge(self, catalog_path, ostrovok_stats_path, tvil_stats_path):
        """Основная логика объединения статистики с каталогом."""
        logger.info("Начало процесса объединения ежедневной статистики...")
        
        catalog = self._read_csv_rows(catalog_path)
        ostrovok_stats = self._read_csv_rows(ostrovok_stats_path)
        tvil_stats = self._read_csv_rows(tvil_stats_path)

        # Индексы по идентификаторам
        o_by_id = {}
        for row in ostrovok_stats:
            key = self._norm(row.get("ota_hotel_id"))
            if key:
                o_by_id[key] = row

        t_by_id = {}
        for row in tvil_stats:
            key = self._norm(row.get("tvil_hotel_id"))
            if key:
                t_by_id[key] = row

        output_rows = []

        for cat in catalog:
            merged_id = self._norm(cat.get("merged_id"))
            match_type = self._norm(cat.get("match_type"))
            if match_type in {"address", "name"}:
                match_type = "matched"
            city = self._norm(cat.get("city"))
            name = self._norm(cat.get("name"))
            address = self._norm(cat.get("address"))
            o_hotel_id = self._norm(cat.get("ostrovok_ota_hotel_id"))
            t_hotel_id = self._norm(cat.get("tvil_hotel_id"))

            # Данные из ежедневной статистики
            o_stat = o_by_id.get(o_hotel_id, {})
            t_stat = t_by_id.get(t_hotel_id, {})

            o_capacity = self._to_float(o_stat.get("max_capacity"))
            t_capacity = self._to_float(t_stat.get("max_capacity"))
            o_rooms_num = self._to_float(cat.get("ostrovok_rooms_number"))
            t_rooms_num = self._to_float(cat.get("tvil_rooms_number"))
            o_free_rooms = self._to_float(o_stat.get("free_rooms_amount"))
            t_free_rooms = self._to_float(t_stat.get("free_rooms_amount"))
            o_avail_pct = self._to_float(o_stat.get("available_rooms_percent"))
            t_avail_pct = self._to_float(t_stat.get("available_rooms_percent"))
            o_min_price = self._to_float(o_stat.get("min_price"))
            t_min_price = self._to_float(t_stat.get("min_price"))

            # available_rooms_percent — доля свободных номеров; загрузка = 100 − free%
            o_occ_pct = (100.0 - o_avail_pct) if o_avail_pct is not None else None
            t_occ_pct = (100.0 - t_avail_pct) if t_avail_pct is not None else None
            avg_occupancy_pct = self._avg_of(o_occ_pct, t_occ_pct)
            
            avg_capacity = self._avg_of(o_capacity, t_capacity)
            avg_capacity = str(int(round(float(avg_capacity)))) if avg_capacity != "" else ""

            output_rows.append({
                "merged_id": merged_id,
                "match-type": match_type,
                "city": city,
                "name": name,
                "address": address,
                
                "ostrovok_rooms_number": int(o_rooms_num) if o_rooms_num is not None else "",
                "tvil_rooms_number": int(t_rooms_num) if t_rooms_num is not None else "",
                
                "ostrovok_free_rooms": int(o_free_rooms) if o_free_rooms is not None else "",
                "tvil_free_rooms": int(t_free_rooms) if t_free_rooms is not None else "",
                
                "min_free_rooms": self._min_of(o_free_rooms, t_free_rooms),
                "avg_free_rooms": self._avg_of(o_free_rooms, t_free_rooms),
                "max_free_rooms": self._max_of(o_free_rooms, t_free_rooms),
                
                "ostrovok_free_rooms_pct": int(o_avail_pct) if o_avail_pct is not None else "",
                "tvil_free_rooms_pct": int(t_avail_pct) if t_avail_pct is not None else "",
                "avg_free_rooms_pct": self._avg_of(o_avail_pct, t_avail_pct),
                
                "ostrovok_occupancy_pct": o_occ_pct,
                "tvil_occupancy_pct": t_occ_pct,
                "avg_occupancy_pct": avg_occupancy_pct,
                
                "ostrovok_capacity": int(o_capacity) if o_capacity is not None else "",
                "tvil_capacity": int(t_capacity) if t_capacity is not None else "",
                "avg_capacity": avg_capacity,
                
                "ostrovok_min_price": int(o_min_price) if o_min_price is not None else "",
                "tvil_min_price": int(t_min_price) if t_min_price is not None else "",
                "min_price": self._min_of(o_min_price, t_min_price),
            })

        return output_rows

    def save_results(self, rows, output_path):
        """Записывает итоговый список строк в файл и выводит статистику."""
        fieldnames = [
            "merged_id", "match-type", "city", "name", "address",
            "ostrovok_rooms_number", "tvil_rooms_number",
            "ostrovok_free_rooms", "tvil_free_rooms",
            "min_free_rooms", "avg_free_rooms", "max_free_rooms",
            "ostrovok_free_rooms_pct", "tvil_free_rooms_pct", "avg_free_rooms_pct",
            "ostrovok_occupancy_pct","tvil_occupancy_pct","avg_occupancy_pct",
            "ostrovok_capacity", "tvil_capacity", "avg_capacity",
            "ostrovok_min_price", "tvil_min_price", "min_price",
        ]
        
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
            
            total   = len(rows)
            matched = sum(1 for r in rows if r["ostrovok_free_rooms"] != "" and r["tvil_free_rooms"] != "")
            only_o  = sum(1 for r in rows if r["ostrovok_free_rooms"] != "" and r["tvil_free_rooms"] == "")
            only_t  = sum(1 for r in rows if r["ostrovok_free_rooms"] == "" and r["tvil_free_rooms"] != "")

            logger.info("--- ИТОГО СТАТИСТИКА ---")
            logger.info("Всего строк сохранено: %d", total)
            logger.info("Оба источника данных: %d", matched)
            logger.info("Только Ostrovok: %d", only_o)
            logger.info("Только Tvil: %d", only_t)
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

    def _norm(self, v):
        """Вспомогательный метод для нормализации строк."""
        return str(v).strip() if v is not None else ""

    def _to_float(self, v):
        try:
            return float(self._norm(v)) if self._norm(v) else None
        except ValueError:
            return None

    def _avg_of(self, *vals):
        nums = [v for v in vals if v is not None]
        if not nums:
            return ""
        return f"{sum(nums) / len(nums):.2f}"

    def _min_of(self, *vals):
        nums = [v for v in vals if v is not None]
        return str(int(min(nums))) if nums else ""

    def _max_of(self, *vals):
        nums = [v for v in vals if v is not None]
        return str(int(max(nums))) if nums else ""


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent 
    repo_root = base_dir.parent               

    sys.path.insert(0, str(repo_root))
    run_date = _run_date()
    try:
        from log_config import setup_logging, get_log_file_path
        setup_logging(log_file=get_log_file_path(run_date.isoformat()))
    except ImportError:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        logger.warning("Модуль log_config не найден, логирование в файл отключено.")

    catalog_path = base_dir / "merge-results" / "matched-catalog.csv"
    o_stats_dir = repo_root / "ostrovok-data" / "daily" / "statistics"
    t_stats_dir = repo_root / "tvil-data" / "daily" / "statistics"

    merger = DailyStatsMerger()

    ostrovok_stats_path = merger.latest_csv_file(o_stats_dir)
    tvil_stats_path = merger.latest_csv_file(t_stats_dir)

    o_stat_date = _extract_date_from_path(ostrovok_stats_path)
    t_stat_date = _extract_date_from_path(tvil_stats_path)


    output_date = o_stat_date or t_stat_date or run_date.isoformat()
    output_file = repo_root / "all-data" / f"{output_date}.csv"

    merger.run(catalog_path, o_stats_dir, t_stats_dir, output_file)