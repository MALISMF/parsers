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


def _index_by_address(rows: list[dict[str, Any]], address_col: str) -> dict[str, dict[str, Any]]:
    """
    Индексирует строки по адресу. Если адрес дублируется, берём первую встреченную строку.
    Это удобно для Tvil, где иногда встречаются повторы.
    """
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        addr = (row.get(address_col) or "").strip()
        if not addr:
            continue
        out.setdefault(addr, row)
    return out


def _norm(s: Any) -> str:
    return ("" if s is None else str(s)).strip()


def merge_catalogs(
    match_results_path: Path,
    ostrovok_hotels_path: Path,
    tvil_hotels_path: Path,
    output_path: Path,
) -> None:
    matches = _read_csv_rows(match_results_path)
    ostrovok_rows = _read_csv_rows(ostrovok_hotels_path)
    tvil_rows = _read_csv_rows(tvil_hotels_path)

    ostrovok_by_address = _index_by_address(ostrovok_rows, "address")
    tvil_by_address = _index_by_address(tvil_rows, "address")

    matched_ostrovok_addresses: set[str] = set()
    matched_tvil_addresses: set[str] = set()

    out_rows: list[dict[str, Any]] = []
    next_id = 1

    def add_row(row: dict[str, Any]) -> None:
        nonlocal next_id
        row = dict(row)
        row["merged_id"] = next_id
        next_id += 1
        out_rows.append(row)

    # 1) Замэтченные пары -> одна строка
    for m in matches:
        o_addr = _norm(m.get("ostrovok_address"))
        t_addr = _norm(m.get("tvil_address"))
        matched_ostrovok_addresses.add(o_addr) if o_addr else None
        matched_tvil_addresses.add(t_addr) if t_addr else None

        o = ostrovok_by_address.get(o_addr, {})
        t = tvil_by_address.get(t_addr, {})

        add_row(
            {
                "match_type": _norm(m.get("match_type")) or "matched",
                "address_score": _norm(m.get("address_score")),
                "name_score": _norm(m.get("name_score")),
                # Канонические поля (удобно для дальнейшей агрегации)
                "city": _norm(o.get("city")) or _norm(t.get("city")),
                "name": _norm(o.get("name")) or _norm(m.get("ostrovok_name")) or _norm(t.get("name")) or _norm(m.get("tvil_name")),
                "address": _norm(o.get("address")) or o_addr or _norm(t.get("address")) or t_addr,
                "rooms_number": _norm(o.get("rooms_number")) or _norm(t.get("rooms_number")),
                # Ostrovok
                "ostrovok_ota_hotel_id": _norm(o.get("ota_hotel_id")),
                "ostrovok_master_id": _norm(o.get("master_id")),
                "ostrovok_name": _norm(o.get("name")) or _norm(m.get("ostrovok_name")),
                "ostrovok_address": o_addr or _norm(o.get("address")),
                "ostrovok_url": _norm(o.get("url")),
                "ostrovok_rooms_number": _norm(o.get("rooms_number")),
                # Tvil
                "tvil_hotel_id": _norm(t.get("tvil_hotel_id")),
                "tvil_name": _norm(t.get("name")) or _norm(m.get("tvil_name")),
                "tvil_address": t_addr or _norm(t.get("address")),
                "tvil_url": _norm(t.get("url")),
                "tvil_rooms_number": _norm(t.get("rooms_number")),
            }
        )

    # 2) Не замэтченные из Ostrovok
    for o in ostrovok_rows:
        o_addr = _norm(o.get("address"))
        if not o_addr or o_addr in matched_ostrovok_addresses:
            continue
        add_row(
            {
                "match_type": "unmatched_ostrovok",
                "address_score": "",
                "name_score": "",
                "city": _norm(o.get("city")),
                "name": _norm(o.get("name")),
                "address": o_addr,
                "rooms_number": _norm(o.get("rooms_number")),
                "ostrovok_ota_hotel_id": _norm(o.get("ota_hotel_id")),
                "ostrovok_master_id": _norm(o.get("master_id")),
                "ostrovok_name": _norm(o.get("name")),
                "ostrovok_address": o_addr,
                "ostrovok_url": _norm(o.get("url")),
                "ostrovok_rooms_number": _norm(o.get("rooms_number")),
                "tvil_hotel_id": "",
                "tvil_name": "",
                "tvil_address": "",
                "tvil_url": "",
                "tvil_rooms_number": "",
            }
        )

    # 3) Не замэтченные из Tvil
    for t in tvil_rows:
        t_addr = _norm(t.get("address"))
        if not t_addr or t_addr in matched_tvil_addresses:
            continue
        add_row(
            {
                "match_type": "unmatched_tvil",
                "address_score": "",
                "name_score": "",
                "city": _norm(t.get("city")),
                "name": _norm(t.get("name")),
                "address": t_addr,
                "rooms_number": _norm(t.get("rooms_number")),
                "ostrovok_ota_hotel_id": "",
                "ostrovok_master_id": "",
                "ostrovok_name": "",
                "ostrovok_address": "",
                "ostrovok_url": "",
                "ostrovok_rooms_number": "",
                "tvil_hotel_id": _norm(t.get("tvil_hotel_id")),
                "tvil_name": _norm(t.get("name")),
                "tvil_address": t_addr,
                "tvil_url": _norm(t.get("url")),
                "tvil_rooms_number": _norm(t.get("rooms_number")),
            }
        )

    # Стабильный порядок: matched сначала, потом unmatched (как добавляли)
    fieldnames = [
        "merged_id",
        "match_type",
        "address_score",
        "name_score",
        "city",
        "name",
        "address",
        "rooms_number",
        "ostrovok_ota_hotel_id",
        "ostrovok_master_id",
        "ostrovok_name",
        "ostrovok_address",
        "ostrovok_url",
        "ostrovok_rooms_number",
        "tvil_hotel_id",
        "tvil_name",
        "tvil_address",
        "tvil_url",
        "tvil_rooms_number",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)

    logger.info(
        "Готово: %s строк (matched=%s, unmatched_ostrovok=%s, unmatched_tvil=%s) -> %s",
        len(out_rows),
        sum(1 for r in out_rows if r.get("match_type") not in ("unmatched_ostrovok", "unmatched_tvil")),
        sum(1 for r in out_rows if r.get("match_type") == "unmatched_ostrovok"),
        sum(1 for r in out_rows if r.get("match_type") == "unmatched_tvil"),
        output_path,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    base_dir = Path(__file__).resolve().parent
    repo_root = base_dir.parent

    match_results_dir = base_dir / "match-results"
    merge_results_dir = base_dir / "merge-results"
    ostrovok_catalog_dir = repo_root / "ostrovok-data" / "catalog"
    tvil_catalog_dir = repo_root / "tvil-data" / "catalog"

    match_results = latest_csv_file(match_results_dir)
    ostrovok_hotels = latest_csv_file(ostrovok_catalog_dir)
    tvil_hotels = latest_csv_file(tvil_catalog_dir)

    if not match_results:
        raise SystemExit(f"Не найдены CSV в {match_results_dir} (сначала запустите fuzzy-matcher2.py)")
    if not ostrovok_hotels:
        raise SystemExit(f"Не найдены CSV Ostrovok в {ostrovok_catalog_dir}")
    if not tvil_hotels:
        raise SystemExit(f"Не найдены CSV Tvil в {tvil_catalog_dir}")

    merge_results_dir.mkdir(parents=True, exist_ok=True)
    merge_catalogs(
        match_results_path=match_results,
        ostrovok_hotels_path=ostrovok_hotels,
        tvil_hotels_path=tvil_hotels,
        output_path=merge_results_dir / "matched-catalog.csv",
    )
