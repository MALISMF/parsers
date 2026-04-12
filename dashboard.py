import math
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path
from plotly.subplots import make_subplots

st.set_page_config(
    page_title="Загруженность СР · Иркутская область",
    layout="wide",
)

BASE = Path(__file__).parent


def _rooms_per_hotel_series(part: pd.DataFrame) -> pd.Series:
    """Номера на отель: max(ostrovok_rooms_number, tvil_rooms_number), без двойного счёта."""
    cols = []
    if "ostrovok_rooms_number" in part.columns:
        cols.append(pd.to_numeric(part["ostrovok_rooms_number"], errors="coerce"))
    if "tvil_rooms_number" in part.columns:
        cols.append(pd.to_numeric(part["tvil_rooms_number"], errors="coerce"))
    if not cols:
        return pd.Series(0.0, index=part.index, dtype="float64")
    return pd.concat(cols, axis=1).max(axis=1)


@st.cache_data(ttl=300)
def load_map_df(all_data_path: Path) -> pd.DataFrame:
    if not all_data_path.is_file():
        return pd.DataFrame()
    all_data = pd.read_csv(all_data_path, encoding="utf-8-sig")

    mc_path = BASE / "matching/merge-results/matched-catalog.csv"
    if not mc_path.exists():
        return pd.DataFrame()

    matched_catalog = pd.read_csv(mc_path, encoding="utf-8-sig")[
        ["merged_id", "lat", "lon"]
    ].dropna(subset=["lat", "lon"])


    df = all_data.merge(matched_catalog, on="merged_id", how="left")

    for col in [
        "avg_occupancy_pct",
        "avg_free_rooms_pct",
        "avg_free_rooms",
        "ostrovok_rooms_number",
        "tvil_rooms_number",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["lat", "lon"])
    df = df[df["lat"].between(45, 70) & df["lon"].between(85, 120)]

    return df


@st.cache_data(ttl=300)
def load_occupancy_timeseries(all_data_dir: Path) -> pd.DataFrame:
    """По каждому CSV в all-data (имя YYYY-MM-DD): загрузка %, сумма номеров, сумма свободных (avg_free_rooms)."""
    rows = []
    for p in sorted(all_data_dir.glob("*.csv")):
        try:
            day = datetime.strptime(p.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        try:
            part = pd.read_csv(p, encoding="utf-8-sig")
        except Exception:
            continue
        if "avg_occupancy_pct" not in part.columns:
            continue
        part["avg_occupancy_pct"] = pd.to_numeric(
            part["avg_occupancy_pct"], errors="coerce"
        )
        m = part["avg_occupancy_pct"].mean()
        if pd.isna(m):
            continue
        room_sum = float(_rooms_per_hotel_series(part).sum(skipna=True))
        if "avg_free_rooms" in part.columns:
            free_sum = float(
                pd.to_numeric(part["avg_free_rooms"], errors="coerce").sum(skipna=True)
            )
        else:
            free_sum = 0.0
        rows.append(
            {
                "date": day,
                "avg_occupancy_pct": float(m),
                "total_rooms_sum": room_sum,
                "free_rooms_sum": free_sum,
            }
        )
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values("date")
    out["date"] = pd.to_datetime(out["date"])
    return out


all_data_dir = BASE / "all-data"
all_csv_files = sorted(all_data_dir.glob("*.csv"))

st.markdown("## Загруженность средств размещения · Иркутская область")

if not all_csv_files:
    st.error(
        "В папке all-data нет CSV. "
        "Убедитесь, что dashboard.py лежит рядом с all-data/ и matching/."
    )
    st.stop()

with st.sidebar:
    st.markdown("### Данные")
    choice_names = [p.name for p in all_csv_files]
    selected_name = st.selectbox(
        "Файл из all-data",
        choice_names,
        index=len(choice_names) - 1,
        help="По этому файлу строятся карта и таблица.",
    )

df = load_map_df(all_data_dir / selected_name)

with st.sidebar:
    st.markdown("### Фильтры")
    cities = sorted(df["city"].dropna().unique())
    sel_cities = st.multiselect("Город", cities, default=cities)

    min_val = int(math.floor(df['avg_occupancy_pct'].min()))
    max_val = int(math.ceil(df['avg_occupancy_pct'].max()))

    if min_val == max_val:
        max_val += 1

    occ_min, occ_max = st.slider(
        "Загруженность, %",
        min_value=min_val,
        max_value=max_val,
        value=(min_val, max_val)
    )

filtered = df[df["city"].isin(sel_cities)]
filtered = filtered[
    filtered["avg_occupancy_pct"].isna()
    | filtered["avg_occupancy_pct"].between(occ_min, occ_max)
].copy()

def _format_int(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    try:
        return f"{int(round(float(x))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


rooms_total_filtered = (
    float(_rooms_per_hotel_series(filtered).sum(skipna=True))
    if not filtered.empty
    else float("nan")
)
free_total_filtered = (
    float(pd.to_numeric(filtered["avg_free_rooms"], errors="coerce").sum(skipna=True))
    if not filtered.empty and "avg_free_rooms" in filtered.columns
    else float("nan")
)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Отелей на карте", len(filtered))
c2.metric(
    "Средняя загруженность",
    f"{filtered['avg_occupancy_pct'].mean():.1f}%" if not filtered.empty else "—",
)
c3.metric(
    "Среднее свободных мест, %",
    f"{filtered['avg_free_rooms_pct'].mean():.1f}%" if not filtered.empty else "—",
)
c4.metric("Всего номеров", _format_int(rooms_total_filtered))
c5.metric("Свободных номеров", _format_int(free_total_filtered))

filtered["occ_display"] = filtered["avg_occupancy_pct"].fillna(0)
filtered["hover"] = (
    "<b>" + filtered["name"].fillna("") + "</b><br>"
    + filtered["city"].fillna("") + "<br>"
    + "Свободно: <b>"
    + filtered["avg_free_rooms_pct"].apply(
        lambda x: f"{x:.1f}%" if pd.notna(x) else "нет данных"
    )
    + "</b><br>"
    + "Загружено: <b>"
    + filtered["avg_occupancy_pct"].apply(
        lambda x: f"{x:.1f}%" if pd.notna(x) else "нет данных"
    )
    + "</b>"
)

fig = px.scatter_mapbox(
    filtered,
    lat="lat",
    lon="lon",
    color="occ_display",
    size=[10] * len(filtered),
    size_max=14,
    color_continuous_scale=[
        [0.00, "#00e676"],
        [0.25, "#69f0ae"],
        [0.50, "#ffff00"],
        [0.75, "#ffab00"],
        [1.00, "#ff5252"],
    ],
    range_color=[0, 100],
    hover_name="name",
    custom_data=["hover"],
    zoom=5.5,
    center={"lat": 54.0, "lon": 103.5},
    mapbox_style="open-street-map",
    height=650,
)
fig.update_traces(
    hovertemplate="%{customdata[0]}<extra></extra>",
    marker_opacity=0.9,
)
fig.update_coloraxes(
    colorbar_title="Загруженность %",
    colorbar_thickness=12,
    colorbar_len=0.7,
)
fig.update_layout(margin={"t": 0, "b": 0, "l": 0, "r": 0}, dragmode="pan")

st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True} )

ts_occ = load_occupancy_timeseries(all_data_dir)
st.markdown("### Временная динамика")
if ts_occ.empty:
    st.info("Нет данных для графика: в all-data нет CSV с именем YYYY-MM-DD и колонкой avg_occupancy_pct.")
else:
    fig_ts = make_subplots(specs=[[{"secondary_y": True}]])
    fig_ts.add_trace(
        go.Scatter(
            x=ts_occ["date"],
            y=ts_occ["avg_occupancy_pct"],
            name="Загруженность, %",
            mode="lines+markers",
            line=dict(width=2, color="#3498db"),
        ),
        secondary_y=False,
    )
    fig_ts.add_trace(
        go.Scatter(
            x=ts_occ["date"],
            y=ts_occ["free_rooms_sum"],
            name="Свободных номеров (сумма)",
            mode="lines+markers",
            line=dict(width=2, color="#e67e22"),
        ),
        secondary_y=True,
    )
    fig_ts.update_layout(
        xaxis_title="Дата",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=50, b=40, l=55, r=55),
    )
    fig_ts.update_yaxes(title_text="Загруженность, %", secondary_y=False)
    fig_ts.update_yaxes(title_text="Номеров / свободно, шт", secondary_y=True)
    st.plotly_chart(fig_ts, use_container_width=True, config={"scrollZoom": True})

# Таблица
st.markdown("### Данные")

table_cols = {
    "city":               "Город",
    "name":               "Название",
    "avg_occupancy_pct":  "Загруженность %",
    "avg_free_rooms_pct": "Свободно %",
    "avg_free_rooms":     "Свободно мест (avg)",
}
available = {k: v for k, v in table_cols.items() if k in df.columns}
table = (
    df[list(available.keys())]
    .rename(columns=available)
    .sort_values("Загруженность %", ascending=False, na_position="last")
    .reset_index(drop=True)
)

search = st.text_input("Поиск", placeholder="Название или город...")
if search:
    mask = (
        table["Название"].str.contains(search, case=False, na=False)
        | table["Город"].str.contains(search, case=False, na=False)
    )
    table = table[mask]

col_cfg = {}
if "Загруженность %" in table.columns:
    col_cfg["Загруженность %"] = st.column_config.ProgressColumn(
        "Загруженность %", min_value=0, max_value=100, format="%.1f%%"
    )
if "Свободно %" in table.columns:
    col_cfg["Свободно %"] = st.column_config.ProgressColumn(
        "Свободно %", min_value=0, max_value=100, format="%.1f%%"
    )

st.dataframe(table, use_container_width=True, height=400, column_config=col_cfg, hide_index=True)
st.markdown("### Загруженность номерного фонда по городам")

city_chart_mode = st.pills(
    "Показать по городам:",
    options=["Общее кол-во мест", "Среднее кол-во мест"],
    default="Общее кол-во мест",
)

if city_chart_mode in (None, "Общее кол-во мест"):
    df_city = df.groupby("city", as_index=False)["avg_free_rooms"].sum()
    total_free = df_city["avg_free_rooms"].sum()
    if total_free and total_free != 0:
        df_city["_pct_label"] = (
            df_city["avg_free_rooms"] / total_free * 100
        ).map(lambda x: f"{x:.1f}%")
    else:
        df_city["_pct_label"] = "0.0%"

    fig_city = px.bar(
        df_city,
        x="city",
        y="avg_free_rooms",
        color="city",
        text="_pct_label",
    )
    fig_city.update_traces(textposition="outside")
    fig_city.update_layout(
        showlegend=False,
        xaxis_title="Город",
        yaxis_title="Сумма (avg_free_rooms)",
        margin=dict(t=30, b=40),
    )
    st.plotly_chart(fig_city, use_container_width=True,  config={'scrollZoom': False })
else:
    df_city = df.groupby("city", as_index=False)["avg_free_rooms"].mean()
    fig_city = px.bar(df_city, x="city", y="avg_free_rooms", color="city")
    fig_city.update_layout(
        showlegend=False,
        xaxis_title="Город",
        yaxis_title="Среднее (avg_free_rooms)",
        margin=dict(t=10, b=40),
    )
    st.plotly_chart(fig_city, use_container_width=True,  config={'scrollZoom': False})