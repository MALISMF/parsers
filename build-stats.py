"""
Объединяет matched-catalog.csv с ежедневной статистикой Ostrovok и Tvil.

Вход:
  - matching/merge-results/matched-catalog.csv
  - ostrovok-data/daily/statistics/<latest>.csv
  - tvil-data/daily/statistics/<latest>.csv

Выход:
  - output/daily_stats_merged.csv
"""

import csv
import sys
from pathlib import Path


# ── утилиты ──────────────────────────────────────────────────────────────────

def latest_csv(directory: Path) -> Path | None:
    """Последний по имени CSV в директории."""
    files = sorted(directory.glob("*.csv"))
    return files[-1] if files else None


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def norm(v) -> str:
    return str(v).strip() if v is not None else ""


def to_float(v) -> float | None:
    try:
        return float(norm(v)) if norm(v) else None
    except ValueError:
        return None


def avg_of(*vals) -> str:
    nums = [v for v in vals if v is not None]
    if not nums:
        return ""
    return f"{sum(nums) / len(nums):.2f}"


def min_of(*vals) -> str:
    nums = [v for v in vals if v is not None]
    return str(int(min(nums))) if nums else ""


def max_of(*vals) -> str:
    nums = [v for v in vals if v is not None]
    return str(int(max(nums))) if nums else ""


# ── основная логика ───────────────────────────────────────────────────────────

def build(
    catalog_path: Path,
    ostrovok_stats_path: Path,
    tvil_stats_path: Path,
    output_path: Path,
):
    catalog = read_csv(catalog_path)
    ostrovok_stats = read_csv(ostrovok_stats_path)
    tvil_stats = read_csv(tvil_stats_path)

    # индексы по идентификаторам
    o_by_id: dict[str, dict] = {}
    for row in ostrovok_stats:
        key = norm(row.get("ota_hotel_id"))
        if key:
            o_by_id[key] = row

    t_by_id: dict[str, dict] = {}
    for row in tvil_stats:
        key = norm(row.get("tvil_hotel_id"))
        if key:
            t_by_id[key] = row

    output_rows = []

    for cat in catalog:
        merged_id   = norm(cat.get("merged_id"))
        city        = norm(cat.get("city"))
        name        = norm(cat.get("name"))
        address     = norm(cat.get("address"))
        o_hotel_id  = norm(cat.get("ostrovok_ota_hotel_id"))
        t_hotel_id  = norm(cat.get("tvil_hotel_id"))

        # rooms_number из каталога
        o_rooms_num = to_float(cat.get("ostrovok_rooms_number"))
        t_rooms_num = to_float(cat.get("tvil_rooms_number"))

        # данные из ежедневной статистики
        o_stat = o_by_id.get(o_hotel_id, {})
        t_stat = t_by_id.get(t_hotel_id, {})

        o_capacity        = to_float(o_stat.get("max_capacity"))
        t_capacity        = to_float(t_stat.get("max_capacity"))
        o_free_rooms      = to_float(o_stat.get("free_rooms_amount"))
        t_free_rooms      = to_float(t_stat.get("free_rooms_amount"))
        o_avail_pct       = to_float(o_stat.get("available_rooms_percent"))
        t_avail_pct       = to_float(t_stat.get("available_rooms_percent"))

        # occupancy_percent — среднее доступности по источникам, что есть
        occupancy_pct = avg_of(o_avail_pct, t_avail_pct)

        output_rows.append({
            "merged_id":           merged_id,
            "city":                city,
            "name":                name,
            "address":             address,
            "ostrovok_free_rooms": int(o_free_rooms) if o_free_rooms is not None else "",
            "tvil_free_rooms":     int(t_free_rooms) if t_free_rooms is not None else "",
            "avg_free_rooms":      avg_of(o_free_rooms, t_free_rooms),
            "min_free_rooms":      min_of(o_free_rooms, t_free_rooms),
            "max_free_rooms":      max_of(o_free_rooms, t_free_rooms),
            "occupancy_percent":   occupancy_pct,
            "ostrovok_capacity":   int(o_capacity) if o_capacity is not None else "",
            "tvil_capacity":       int(t_capacity) if t_capacity is not None else "",
        })

    fieldnames = [
        "merged_id", "city", "name", "address",
        "ostrovok_free_rooms", "tvil_free_rooms",
        "avg_free_rooms", "min_free_rooms", "max_free_rooms",
        "occupancy_percent",
        "ostrovok_capacity", "tvil_capacity",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    total   = len(output_rows)
    matched = sum(1 for r in output_rows if r["ostrovok_free_rooms"] != "" and r["tvil_free_rooms"] != "")
    only_o  = sum(1 for r in output_rows if r["ostrovok_free_rooms"] != "" and r["tvil_free_rooms"] == "")
    only_t  = sum(1 for r in output_rows if r["ostrovok_free_rooms"] == "" and r["tvil_free_rooms"] != "")

    print(f"Сохранено строк: {total}")
    print(f"  Оба источника: {matched}")
    print(f"  Только Ostrovok: {only_o}")
    print(f"  Только Tvil: {only_t}")
    print(f"  Результат: {output_path}")


# ── точка входа ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent

    catalog_path = repo_root / "matching" / "merge-results" / "matched-catalog.csv"

    o_stats_dir  = repo_root / "ostrovok-data" / "daily" / "statistics"
    t_stats_dir  = repo_root / "tvil-data"     / "daily" / "statistics"

    o_stats_path = latest_csv(o_stats_dir)
    t_stats_path = latest_csv(t_stats_dir)

    if not catalog_path.exists():
        sys.exit(f"Не найден каталог: {catalog_path}")
    if not o_stats_path:
        sys.exit(f"Нет CSV статистики в {o_stats_dir}")
    if not t_stats_path:
        sys.exit(f"Нет CSV статистики в {t_stats_dir}")

    print(f"Каталог:           {catalog_path}")
    print(f"Ostrovok stats:    {o_stats_path}")
    print(f"Tvil stats:        {t_stats_path}")

    output_path = repo_root / "output" / "daily_stats_merged.csv"
    build(catalog_path, o_stats_path, t_stats_path, output_path)