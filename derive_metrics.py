import csv
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def latest_csv_file(directory: Path) -> Path | None:
    """Последний по имени CSV в директории (формат YYYY-MM-DD.csv)."""
    if not directory.is_dir():
        return None
    files = sorted(directory.glob("*.csv"))
    return files[-1] if files else None


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _norm(s: Any) -> str:
    return ("" if s is None else str(s)).strip()


def _to_float(x: Any) -> float | None:
    s = _norm(x)
    if not s:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _to_int(x: Any) -> int | None:
    f = _to_float(x)
    if f is None:
        return None
    try:
        return int(round(f))
    except Exception:
        return None


def _safe_percent(numer: float, denom: float) -> float | None:
    if denom <= 0:
        return None
    return 100.0 * numer / denom


def _mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    return sum(vals) / len(vals)


def _min(vals: list[float]) -> float | None:
    return min(vals) if vals else None


def _max(vals: list[float]) -> float | None:
    return max(vals) if vals else None


def _fmt(x: float | int | None, ndigits: int = 2) -> str:
    if x is None:
        return ""
    if isinstance(x, int):
        return str(x)
    return f"{x:.{ndigits}f}"


def build_metrics(
    merged_hotels_path: Path,
    ostrovok_stats_path: Path,
    tvil_stats_path: Path,
    output_path: Path,
) -> None:
    merged_rows = _read_csv_rows(merged_hotels_path)
    o_stats = _read_csv_rows(ostrovok_stats_path)
    t_stats = _read_csv_rows(tvil_stats_path)

    o_by_id: dict[str, dict[str, Any]] = { _norm(r.get("ota_hotel_id")): r for r in o_stats if _norm(r.get("ota_hotel_id")) }
    t_by_id: dict[str, dict[str, Any]] = { _norm(r.get("tvil_hotel_id")): r for r in t_stats if _norm(r.get("tvil_hotel_id")) }

    out_rows: list[dict[str, Any]] = []

    for row in merged_rows:
        o_id = _norm(row.get("ostrovok_ota_hotel_id"))
        t_id = _norm(row.get("tvil_hotel_id"))
        o = o_by_id.get(o_id, {})
        t = t_by_id.get(t_id, {})

        free_vals: list[float] = []

        # Ostrovok
        o_free = _to_float(o.get("free_rooms_amount"))
        if o_free is not None:
            free_vals.append(o_free)

        # Tvil
        t_free = _to_float(t.get("free_rooms_amount"))
        if t_free is not None:
            free_vals.append(t_free)

        out = dict(row)
        out.update(
            {
                # Источники (как есть из statistics)
                "ostrovok_rooms_num": _norm(o.get("rooms_num")),
                "ostrovok_free_rooms_amount": _norm(o.get("free_rooms_amount")),
                "ostrovok_max_capacity": _norm(o.get("max_capacity")),
                "ostrovok_available_rooms_percent": _norm(o.get("available_rooms_percent")),
                "ostrovok_min_price": _norm(o.get("min_price")),
                "tvil_rooms_num": _norm(t.get("rooms_num")),
                "tvil_free_rooms_amount": _norm(t.get("free_rooms_amount")),
                "tvil_max_capacity": _norm(t.get("max_capacity")),
                "tvil_available_rooms_percent": _norm(t.get("available_rooms_percent")),
                "tvil_min_price": _norm(t.get("min_price")),
                # Агрегаты по свободным "номерам" (из разных источников)
                "free_rooms_min": _fmt(_min(free_vals)),
                "free_rooms_avg": _fmt(_mean(free_vals)),
                "free_rooms_max": _fmt(_max(free_vals)),
            }
        )
        out_rows.append(out)

    # Поля: исходные + добавленные метрики (в конце)
    if not merged_rows:
        raise SystemExit("merged_hotels.csv пустой или не прочитан")

    base_fields = list(merged_rows[0].keys())
    metric_fields = [
        "ostrovok_rooms_num",
        "ostrovok_free_rooms_amount",
        "ostrovok_max_capacity",
        "ostrovok_available_rooms_percent",
        "ostrovok_min_price",
        "tvil_rooms_num",
        "tvil_free_rooms_amount",
        "tvil_max_capacity",
        "tvil_available_rooms_percent",
        "tvil_min_price",
        "free_rooms_min",
        "free_rooms_avg",
        "free_rooms_max",
    ]
    fieldnames = base_fields + [f for f in metric_fields if f not in base_fields]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)

    logger.info("Готово: %s -> %s", len(out_rows), output_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    base_dir = Path(__file__).parent

    merged_hotels = base_dir / "merged_hotels.csv"
    ostrovok_stats = latest_csv_file(base_dir / "ostrovok-tables" / "statistics")
    tvil_stats = latest_csv_file(base_dir / "tvil-tables" / "statistics")

    if not merged_hotels.exists():
        raise SystemExit(f"Не найден файл: {merged_hotels}")
    if not ostrovok_stats:
        raise SystemExit("Не найдены CSV Ostrovok в ostrovok-tables/statistics")
    if not tvil_stats:
        raise SystemExit("Не найдены CSV Tvil в tvil-tables/statistics")

    build_metrics(
        merged_hotels_path=merged_hotels,
        ostrovok_stats_path=ostrovok_stats,
        tvil_stats_path=tvil_stats,
        output_path=base_dir / "merged_hotels_with_metrics.csv",
    )

