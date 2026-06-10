## Структура репозитория
 
```
.
├── dashboard.py                  # Streamlit-дашборд
├── log_config.py                 # Логирование + Telegram-уведомления
├── requirements.txt              # Зависимости дашборда (plotly, h3)
├── matching/
│   ├── fuzzy-matcher2.py         # Шаг 1: fuzzy-матчинг каталогов
│   ├── mergeintoone.py           # Шаг 2: единый каталог
│   ├── build-stats.py            # Шаг 3: дневная сводная статистика
│   ├── match-results/
│   │   └── matches.csv           # Накопленные пары совпадений
│   ├── merge-results/
│   │   └── matched-catalog.csv   # Единый каталог объектов
│   └── logs/                     # Логи запусков
├── all-data/                     # YYYY-MM-DD.csv — сводные дневные срезы
├── ostrovok-data/                # Данные парсера Ostrovok (daily/, catalog/)
├── tvil-data/                    # Данные парсера Tvil (daily/, catalog/)
├── .devcontainer/
│   └── devcontainer.json        
└── .github/workflows/
    └── match-and-merge.yml       # Автоматический пайплайн
```
 
## Форматы данных
 
### `matching/match-results/matches.csv`
 
| Колонка | Описание |
|---|---|
| `ostrovok_address` / `tvil_address` | Адреса в источниках |
| `address_score` | Схожесть адресов (0–100) |
| `ostrovok_name` / `tvil_name` | Названия в источниках |
| `name_score` | Схожесть названий (0–100) |
| `match_type` | По чему найден матч: `address` или `name` |
 
### `matching/merge-results/matched-catalog.csv`
 
| Колонка | Описание |
|---|---|
| `merged_id` | Сквозной ID объекта в едином каталоге |
| `match_type` | `address` / `name` / `unmatched_ostrovok` / `unmatched_tvil` |
| `address_score`, `name_score` | Оценки совпадения (для matched) |
| `city`, `name`, `address`, `lat`, `lon`, `rooms_number` | Сводные поля объекта |
| `ostrovok_*` | ID, название, адрес, URL, номерной фонд в Ostrovok |
| `tvil_*` | ID, название, адрес, URL, номерной фонд в Tvil |
 
### `all-data/YYYY-MM-DD.csv`
 
| Колонка | Описание |
|---|---|
| `merged_id`, `match_type`, `city`, `name`, `address` | Объект из единого каталога |
| `ostrovok_rooms_number` / `tvil_rooms_number` | Номерной фонд по источникам |
| `ostrovok_free_rooms` / `tvil_free_rooms` | Свободные номера по источникам |
| `min_free_rooms` / `avg_free_rooms` / `max_free_rooms` | Агрегаты по свободным номерам |
| `ostrovok_free_rooms_pct` / `tvil_free_rooms_pct` / `avg_free_rooms_pct` | Доля свободных номеров, % |
| `ostrovok_occupancy_pct` / `tvil_occupancy_pct` / `avg_occupancy_pct` | Загруженность (100 − free%), % |
| `ostrovok_capacity` / `tvil_capacity` / `avg_capacity` | Вместимость свободных номеров |
| `ostrovok_min_price` / `tvil_min_price` / `min_price` | Минимальная цена, ₽ |
