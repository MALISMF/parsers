import math
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path
from plotly.subplots import make_subplots
import h3

st.set_page_config(
    page_title="Загруженность СР · Иркутская область",
    layout="wide",
)


BASE = Path(__file__).parent

_theme = st.get_option("theme.base")
_is_dark = _theme == "dark"

_legend_bg = "rgba(30,30,30,0.85)" if _is_dark else "rgba(255,255,255,0.85)"
_legend_font_color = "#ffffff" if _is_dark else "#000000"

def _rooms_per_hotel_series(part: pd.DataFrame) -> pd.Series:
    cols = []
    if "ostrovok_rooms_number" in part.columns:
        cols.append(pd.to_numeric(part["ostrovok_rooms_number"], errors="coerce"))
    if "tvil_rooms_number" in part.columns:
        cols.append(pd.to_numeric(part["tvil_rooms_number"], errors="coerce"))
    if not cols:
        return pd.Series(0.0, index=part.index, dtype="float64")
    return pd.concat(cols, axis=1).max(axis=1)


def _rooms_total(row):
    vals = []
    for col in ["ostrovok_rooms_number", "tvil_rooms_number"]:
        try:
            v = float(row.get(col, float("nan")))
            if not pd.isna(v):
                vals.append(v)
        except (TypeError, ValueError):
            pass
    return int(max(vals)) if vals else None


def _prepare_source_view(df: pd.DataFrame, source_mode: str) -> pd.DataFrame:
    view = df.copy()
    num_cols = [
        "avg_occupancy_pct", "avg_free_rooms_pct", "avg_free_rooms", "avg_capacity", "min_price",
        "ostrovok_occupancy_pct", "tvil_occupancy_pct",
        "ostrovok_free_rooms_pct", "tvil_free_rooms_pct",
        "ostrovok_free_rooms", "tvil_free_rooms",
        "ostrovok_rooms_number", "tvil_rooms_number",
        "ostrovok_capacity", "tvil_capacity",
        "ostrovok_min_price", "tvil_min_price",
    ]
    for col in num_cols:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce")

    has_ostrovok = (
        view.get("ostrovok_rooms_number", pd.Series(index=view.index, dtype="float64")).notna()
        | view.get("ostrovok_free_rooms", pd.Series(index=view.index, dtype="float64")).notna()
    )
    has_tvil = (
        view.get("tvil_rooms_number", pd.Series(index=view.index, dtype="float64")).notna()
        | view.get("tvil_free_rooms", pd.Series(index=view.index, dtype="float64")).notna()
    )

    if source_mode == "matched_only":
        match_col = "match-type" if "match-type" in view.columns else "match_type"
        if match_col in view.columns:
            view = view[view[match_col].astype(str).str.strip().eq("matched")].copy()
        view["occ_display"] = view.get("avg_occupancy_pct")
        view["free_rooms_pct_display"] = view.get("avg_free_rooms_pct")
        view["free_rooms_display"] = view.get("avg_free_rooms")
        view["rooms_total_display"] = _rooms_per_hotel_series(view)
        view["capacity_display"] = view.get("avg_capacity")
        view["min_price_display"] = view.get("min_price")
    elif source_mode == "ostrovok":
        view = view[has_ostrovok].copy()
        view["occ_display"] = view.get("ostrovok_occupancy_pct")
        view["free_rooms_pct_display"] = view.get("ostrovok_free_rooms_pct")
        view["free_rooms_display"] = view.get("ostrovok_free_rooms")
        view["rooms_total_display"] = view.get("ostrovok_rooms_number")
        view["capacity_display"] = view.get("ostrovok_capacity")
        view["min_price_display"] = view.get("ostrovok_min_price")
    elif source_mode == "tvil":
        view = view[has_tvil].copy()
        view["occ_display"] = view.get("tvil_occupancy_pct")
        view["free_rooms_pct_display"] = view.get("tvil_free_rooms_pct")
        view["free_rooms_display"] = view.get("tvil_free_rooms")
        view["rooms_total_display"] = view.get("tvil_rooms_number")
        view["capacity_display"] = view.get("tvil_capacity")
        view["min_price_display"] = view.get("tvil_min_price")
    else:
        view["occ_display"] = view.get("avg_occupancy_pct")
        view["free_rooms_pct_display"] = view.get("avg_free_rooms_pct")
        view["free_rooms_display"] = view.get("avg_free_rooms")
        view["rooms_total_display"] = _rooms_per_hotel_series(view)
        view["capacity_display"] = view.get("avg_capacity")
        view["min_price_display"] = view.get("min_price")

    if source_mode == "all":
        source_values = []
        has_ostrovok = has_ostrovok.reindex(view.index, fill_value=False)
        has_tvil = has_tvil.reindex(view.index, fill_value=False)
        for idx in view.index:
            o, t = bool(has_ostrovok.loc[idx]), bool(has_tvil.loc[idx])
            if o and t:
                source_values.append("Ostrovok, Tvil")
            elif o:
                source_values.append("Ostrovok")
            elif t:
                source_values.append("Tvil")
            else:
                source_values.append("—")
        view["source_label"] = source_values
    elif source_mode == "ostrovok":
        view["source_label"] = "Ostrovok"
    elif source_mode == "tvil":
        view["source_label"] = "Tvil"
    elif source_mode == "matched_only":
        view["source_label"] = "Объединенные"
    else:
        view["source_label"] = "—"
    return view


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
        "ostrovok_occupancy_pct",
        "tvil_occupancy_pct",
        "ostrovok_free_rooms_pct",
        "tvil_free_rooms_pct",
        "ostrovok_free_rooms",
        "tvil_free_rooms",
        "ostrovok_capacity",
        "tvil_capacity",
        "avg_capacity",
        "ostrovok_min_price",
        "tvil_min_price",
        "min_price",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["lat", "lon"])
    df = df[df["lat"].between(45, 70) & df["lon"].between(85, 120)]

    return df


@st.cache_data(ttl=300)
def load_occupancy_timeseries(all_data_dir: Path, cities: tuple = (), hotels: tuple = (), source_mode: str = "all") -> pd.DataFrame:
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
        if cities and "city" in part.columns:
            part = part[part["city"].isin(cities)]
        if hotels and "name" in part.columns:
            part = part[part["name"].isin(hotels)]
        part = _prepare_source_view(part, source_mode)
        if "occ_display" not in part.columns:
            continue
        if part.empty:
            continue
        part["occ_display"] = pd.to_numeric(part["occ_display"], errors="coerce")
        m = part["occ_display"].mean()
        if pd.isna(m):
            continue
        room_sum = float(pd.to_numeric(part["rooms_total_display"], errors="coerce").sum(skipna=True)) if "rooms_total_display" in part.columns else 0.0
        free_sum = float(pd.to_numeric(part["free_rooms_display"], errors="coerce").sum(skipna=True)) if "free_rooms_display" in part.columns else 0.0
        free_pct_mean = float(pd.to_numeric(part["free_rooms_pct_display"], errors="coerce").mean(skipna=True)) if "free_rooms_pct_display" in part.columns else round(100.0 - float(m), 1)
        rows.append({"date": day, "avg_occupancy_pct": float(m), "avg_free_rooms_pct": free_pct_mean, "total_rooms_sum": room_sum, "free_rooms_sum": free_sum})
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values("date")
    out["date"] = pd.to_datetime(out["date"])
    return out


def build_calendar_heatmap(ts: pd.DataFrame, metric_col: str, title: str, reverse_scale: bool = False) -> go.Figure:
    df = ts.copy()
    df["month"] = df["date"].dt.to_period("M")
    df["day"] = df["date"].dt.day
    months = sorted(df["month"].unique())
    ru_months = {1:"Январь",2:"Февраль",3:"Март",4:"Апрель",5:"Май",6:"Июнь",7:"Июль",8:"Август",9:"Сентябрь",10:"Октябрь",11:"Ноябрь",12:"Декабрь"}
    month_labels = [f"{ru_months[m.month]} {m.year}" for m in months]
    matrix, text_matrix, hover_matrix = [], [], []
    for m in months:
        row, text_row, hover_row = [], [], []
        month_data = df[df["month"] == m].set_index("day")[metric_col]
        label = f"{ru_months[m.month]} {m.year}"
        for day in range(1, 32):
            if day in month_data.index and not pd.isna(month_data[day]):
                val = round(month_data[day], 1)
                try:
                    dt = datetime(m.year, m.month, day)
                    ru_days = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
                    dow = ru_days[dt.weekday()]
                except ValueError:
                    dow = ""
                row.append(val)
                text_row.append(f"{val:.1f}%")
                hover_row.append(f"{day} {label} ({dow}): {val:.1f}%")
            else:
                row.append(None); text_row.append(""); hover_row.append("")
        matrix.append(row); text_matrix.append(text_row); hover_matrix.append(hover_row)
    cell_h = max(44, min(60, 400 // max(len(months), 1)))
    fig = go.Figure(go.Heatmap(
        z=matrix, x=list(range(1, 32)), y=month_labels,
        text=text_matrix, customdata=hover_matrix,
        texttemplate="%{text}", textfont={"size": 10},
        colorscale=[[0.00,"#ff5252"],[0.25,"#ffab00"],[0.50,"#ffff00"],[0.75,"#69f0ae"],[1.00,"#00e676"]] if reverse_scale else [[0.00,"#00e676"],[0.25,"#69f0ae"],[0.50,"#ffff00"],[0.75,"#ffab00"],[1.00,"#ff5252"]],
        zmin=0, zmax=100,
        colorbar=dict(title="%", thickness=12, len=0.8),
        hovertemplate="%{customdata}<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        xaxis=dict(title="День месяца", tickmode="linear", tick0=1, dtick=1, tickfont=dict(size=11), side="bottom"),
        yaxis=dict(title="", tickfont=dict(size=12), autorange="reversed"),
        margin=dict(t=60, b=50, l=110, r=50),
        height=max(180, len(months) * cell_h + 120),
    )
    return fig

def build_hexbin_layer(df_with_data: pd.DataFrame, resolution: int = 6):
    df = df_with_data.copy()
    df['h3_index'] = df.apply(lambda r: h3.latlng_to_cell(r['lat'], r['lon'], resolution), axis=1)
    hex_df = df.groupby('h3_index').agg(
        avg_occ=('occ_display', 'mean'),
        count=('name', 'count'),
    ).reset_index()
    features = []
    for _, row in hex_df.iterrows():
        boundary = h3.cell_to_boundary(row['h3_index'])
        coords = [[lng, lat] for lat, lng in boundary]
        coords.append(coords[0])
        features.append({
            'type': 'Feature',
            'id': row['h3_index'],
            'properties': {'avg_occ': round(row['avg_occ'], 1), 'count': int(row['count'])},
            'geometry': {'type': 'Polygon', 'coordinates': [coords]},
        })
    geojson = {'type': 'FeatureCollection', 'features': features}
    return hex_df, geojson


# ── Инициализация ─────────────────────────────────────────────────────────────
all_data_dir = BASE / "all-data"
all_csv_files = sorted(all_data_dir.glob("*.csv"))

st.markdown("## Загруженность средств размещения · Иркутская область")

if not all_csv_files:
    st.error("В папке all-data нет CSV. Убедитесь, что dashboard.py лежит рядом с all-data/ и matching/.")
    st.stop()

with st.sidebar:
    st.markdown("### Данные")
    choice_names = [p.name for p in all_csv_files]
    choice_labels = [p.stem for p in all_csv_files]
    selected_label = st.selectbox("Дата сбора данных", choice_labels, index=len(choice_labels) - 1, help="По этому срезу строятся карта и таблица.")
    selected_name = choice_names[choice_labels.index(selected_label)]
df = load_map_df(all_data_dir / selected_name)

with st.sidebar:
    st.markdown("### Навигация")
    st.markdown("""
<style>
.nav-btn {
    display: block;
    width: 100%;
    padding: 7px 12px;
    margin-bottom: 5px;
    border-radius: 6px;
    border: 1px solid rgba(128,128,128,0.3);
    background: transparent;
    color: inherit !important;
    text-decoration: none !important;
    font-size: 0.9em;
    transition: background 0.15s, border-color 0.15s;
    cursor: pointer;
}
.nav-btn:hover {
    background: rgba(128,128,128,0.15);
    border-color: rgba(128,128,128,0.6);
    text-decoration: none !important;
    color: inherit !important;
}
.nav-btn:visited {
    color: inherit !important;
}
.nav-anchor {
    display: block;
    position: relative;
    top: -80px;
    visibility: hidden;
}
</style>
<a class="nav-btn" href="#map">Карта</a>
<a class="nav-btn" href="#timeseries">Временная динамика</a>
<a class="nav-btn" href="#heatmap">Тепловая карта</a>
<a class="nav-btn" href="#weekday">По дням недели</a>
<a class="nav-btn" href="#cities">По городам</a>
<a class="nav-btn" href="#table">Данные</a>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Фильтры")
    source_label = st.selectbox("Источник", options=["Всё", "Ostrovok", "Tvil", "Объединенные"], index=0)
    source_mode = {"Всё": "all", "Ostrovok": "ostrovok", "Tvil": "tvil", "Объединенные": "matched_only"}[source_label]
    df = _prepare_source_view(df, source_mode)

    cities = sorted(df["city"].dropna().unique())
    sel_cities = st.multiselect("Город", cities, default=cities)

    all_hotels_in_cities = sorted(df[df["city"].isin(sel_cities)]["name"].dropna().unique()) if sel_cities else []
    sel_hotels = st.multiselect("Объект размещения", all_hotels_in_cities, default=[], placeholder="Все объекты")

    occ_series = pd.to_numeric(df["occ_display"], errors="coerce")
    if occ_series.notna().any():
        min_val = int(math.floor(occ_series.min()))
        max_val = int(math.ceil(occ_series.max()))
    else:
        min_val, max_val = 0, 100
    if min_val == max_val:
        max_val += 1
    occ_min, occ_max = st.slider("Загруженность, %", min_value=min_val, max_value=max_val, value=(min_val, max_val))

# Фильтрация
filtered_by_city = df[df["city"].isin(sel_cities)].copy()  # для столбчатой диаграммы
filtered = filtered_by_city.copy()
if sel_hotels:
    filtered = filtered[filtered["name"].isin(sel_hotels)]
filtered = filtered[
    filtered["occ_display"].isna() | filtered["occ_display"].between(occ_min, occ_max)
].copy()
filtered_by_city = filtered_by_city[
    filtered_by_city["occ_display"].isna() | filtered_by_city["occ_display"].between(occ_min, occ_max)
].copy()

def _format_int(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    try:
        return f"{int(round(float(x))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"

rooms_total_filtered = float(pd.to_numeric(filtered["rooms_total_display"], errors="coerce").sum(skipna=True)) if not filtered.empty and "rooms_total_display" in filtered.columns else float("nan")
free_total_filtered = float(pd.to_numeric(filtered["free_rooms_display"], errors="coerce").sum(skipna=True)) if not filtered.empty and "free_rooms_display" in filtered.columns else float("nan")

with st.container(border=True):
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Отелей на карте", len(filtered))
    c2.metric("Средняя загруженность", f"{filtered['occ_display'].mean():.1f}%" if not filtered.empty else "—")
    c3.metric("Среднее свободных мест, %", f"{filtered['free_rooms_pct_display'].mean():.1f}%" if not filtered.empty else "—")
    c4.metric("Всего номеров", _format_int(rooms_total_filtered))
    c5.metric("Свободных номеров", _format_int(free_total_filtered))

# Цвет: синий для отелей без данных, иначе шкала загруженности
filtered["has_data"] = filtered["occ_display"].notna()

filtered["hover"] = (
    "<b>" + filtered["name"].fillna("") + "</b><br>"
    + filtered["city"].fillna("") + "<br>"
    + "Источник: <b>"
    + filtered["source_label"].fillna("—")
    + "</b><br>"
    + "Свободных номеров: <b>"
    + filtered["free_rooms_display"].apply(lambda x: f"{int(round(x))} шт." if pd.notna(x) else "нет данных")
    + "</b><br>"
    + "Номерной фонд: <b>"
    + filtered["rooms_total_display"].apply(lambda x: f"{int(round(x))} шт." if pd.notna(x) else "нет данных")
    + "</b><br>"
    + "Свободно: <b>"
    + filtered["free_rooms_pct_display"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "нет данных")
    + "</b><br>"
    + "Загружено: <b>"
    + filtered["occ_display"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "нет данных")
    + "</b><br>"
    + "Минимальная цена: <b>"
    + filtered["min_price_display"].apply(lambda x: f"{int(round(x))} руб." if pd.notna(x) else "нет данных")
    + "</b><br>"
    + "Вместимость (доступные места): <b>"
    + filtered["capacity_display"].apply(lambda x: f"{int(round(x))} мест" if pd.notna(x) else "нет данных")
    + "</b>"
)

# Разделяем на два слоя: с данными и без
filtered_with = filtered[filtered["has_data"]].copy()
filtered_without = filtered[~filtered["has_data"]].copy()

fig = go.Figure()

# Подложка-бордер: отели без данных (рисуются первыми — лежат снизу)
if not filtered_without.empty:
    fig.add_trace(go.Scattermapbox(
        lat=filtered_without["lat"],
        lon=filtered_without["lon"],
        mode="markers",
        marker=go.scattermapbox.Marker(size=16, color="#333333", opacity=0.8),
        hoverinfo="skip",
        legendgroup="without_data",
        showlegend=False,
    ))

# Слой: отели без данных — синие
if not filtered_without.empty:
    fig.add_trace(go.Scattermapbox(
        lat=filtered_without["lat"],
        lon=filtered_without["lon"],
        mode="markers",
        marker=go.scattermapbox.Marker(size=12, color="#7fb3d3", opacity=0.8),
        customdata=filtered_without[["hover", "name"]].values,
        hovertemplate="%{customdata[0]}<extra></extra>",
        name="Нет данных о загруженности",
        legendgroup="without_data",
        showlegend=True,
    ))

# Подложка-бордер: отели с данными (рисуются после — лежат сверху)
if not filtered_with.empty:
    filtered_with["occ_fill"] = filtered_with["occ_display"].fillna(0)
    fig.add_trace(go.Scattermapbox(
        lat=filtered_with["lat"],
        lon=filtered_with["lon"],
        mode="markers",
        marker=go.scattermapbox.Marker(size=16, color="#333333", opacity=0.85),
        hoverinfo="skip",
        legendgroup="with_data",
        showlegend=False,
    ))

# Слой: отели с данными — цвет = загруженность
if not filtered_with.empty:
    fig.add_trace(go.Scattermapbox(
        lat=filtered_with["lat"],
        lon=filtered_with["lon"],
        mode="markers",
        marker=go.scattermapbox.Marker(
            size=12,
            color=filtered_with["occ_fill"],
            colorscale=[[0.00,"#00e676"],[0.25,"#69f0ae"],[0.50,"#ffff00"],[0.75,"#ffab00"],[1.00,"#ff5252"]],
            cmin=0, cmax=100,
            colorbar=dict(title="Загруженность %", thickness=12, len=0.7),
            opacity=0.9,
        ),
        customdata=filtered_with[["hover", "name"]].values,
        hovertemplate="%{customdata[0]}<extra></extra>",
        name="Объекты с данными",
        legendgroup="with_data",
        showlegend=False,
    ))

# Всегда добавляем легенду "Нет данных" (невидимый маркер если таких нет)
fig.add_trace(go.Scattermapbox(
    lat=[None], lon=[None],
    mode="markers",
    marker=go.scattermapbox.Marker(size=12, color="#7fb3d3", opacity=0.8),
    name="Нет данных о загруженности",
    legendgroup="without_data",
    showlegend=len(filtered_without) == 0,
))

fig.update_layout(
    mapbox=dict(style="open-street-map", zoom=5.5, center={"lat": 54.0, "lon": 103.5}),
    margin={"t": 0, "b": 0, "l": 0, "r": 0},
    dragmode="pan",
    height=650,
    legend=dict(x=0.01, y=0.99, bgcolor=_legend_bg, font=dict(color=_legend_font_color), itemsizing="constant"),
)

ts_occ = load_occupancy_timeseries(
    all_data_dir,
    tuple(sorted(sel_cities)),
    tuple(sorted(sel_hotels)),
    source_mode=source_mode,
)

# Подпись фильтров (переиспользуется ниже)
_filter_parts = []
if sel_cities and len(sel_cities) < len(cities):
    _filter_parts.append(f"Города: {', '.join(sel_cities)}")
if sel_hotels and len(sel_hotels) < len(all_hotels_in_cities):
    _filter_parts.append(f"Объекты: {', '.join(sel_hotels)}")
if source_mode != "all":
    _filter_parts.append(f"Источник: {source_label}")
_filter_caption = ("Фильтр: " + " · ".join(_filter_parts)) if _filter_parts else ""

# ── Карта ─────────────────────────────────────────────────────────────────────
st.markdown('<a class="nav-anchor" id="map"></a>', unsafe_allow_html=True)
with st.container(border=True):
    st.markdown("### Карта")
    _date_caption = f"Данные на: {Path(selected_name).stem}"
    st.caption(_date_caption)
    map_mode = st.radio("Режим карты", options=["Точки", "Сетчатая карта"], horizontal=True, label_visibility="collapsed")
    hex_resolution = None
    if map_mode == "Сетчатая карта":
        hex_resolution = st.slider("Детализация сетки", min_value=4, max_value=7, value=4, help="4 — крупные зоны, 7 — мелкие")

    if map_mode == "Сетчатая карта" and not filtered_with.empty:
        hex_df, geojson = build_hexbin_layer(filtered_with, resolution=hex_resolution)
        fig_hex = go.Figure(go.Choroplethmapbox(
            geojson=geojson,
            locations=hex_df['h3_index'],
            z=hex_df['avg_occ'],
            featureidkey='id',
            colorscale=[[0.00,'#00e676'],[0.25,'#69f0ae'],[0.50,'#ffff00'],[0.75,'#ffab00'],[1.00,'#ff5252']],
            zmin=0, zmax=100,
            marker_opacity=0.75,
            marker_line_width=0.5,
            colorbar=dict(title='Загруженность %', thickness=12, len=0.7),
            customdata=hex_df[['avg_occ', 'count']].values,
            hovertemplate='<b>Средняя загруженность:</b> %{customdata[0]:.1f}%<br><b>Объектов:</b> %{customdata[1]}<extra></extra>',
        ))

        # Точки поверх гексагонов
        _free = filtered_with[filtered_with['occ_display'] < 100].copy()
        _full = filtered_with[filtered_with['occ_display'] >= 100].copy()

        if not _free.empty:
            fig_hex.add_trace(go.Scattermapbox(
                lat=_free['lat'], lon=_free['lon'],
                mode='markers',
                marker=go.scattermapbox.Marker(size=10, color='#333333', opacity=0.85),
                hoverinfo='skip',
                legendgroup='hex_free',
                showlegend=False,
            ))
            fig_hex.add_trace(go.Scattermapbox(
                lat=_free['lat'], lon=_free['lon'],
                mode='markers',
                marker=go.scattermapbox.Marker(size=8, color='#111111', opacity=0.9),
                customdata=_free[['hover']].values,
                hovertemplate='%{customdata[0]}<extra></extra>',
                name='Есть свободные места',
                legendgroup='hex_free',
                showlegend=True,
            ))

        if not _full.empty:
            fig_hex.add_trace(go.Scattermapbox(
                lat=_full['lat'], lon=_full['lon'],
                mode='markers',
                marker=go.scattermapbox.Marker(size=10, color='#333333', opacity=0.85),
                hoverinfo='skip',
                legendgroup='hex_full',
                showlegend=False,
            ))
            fig_hex.add_trace(go.Scattermapbox(
                lat=_full['lat'], lon=_full['lon'],
                mode='markers',
                marker=go.scattermapbox.Marker(size=8, color='#ffffff', opacity=0.9),
                customdata=_full[['hover']].values,
                hovertemplate='%{customdata[0]}<extra></extra>',
                name='Загруженность 100%',
                legendgroup='hex_full',
                showlegend=True,
            ))

        fig_hex.update_layout(
            mapbox=dict(style='open-street-map', zoom=5.5, center={'lat': 54.0, 'lon': 103.5}),
            margin={'t': 0, 'b': 0, 'l': 0, 'r': 0},
            height=650,
            legend=dict(x=0.01, y=0.99, bgcolor=_legend_bg, font=dict(color=_legend_font_color), itemsizing='constant'),
        )
        st.plotly_chart(fig_hex, use_container_width=True, config={'scrollZoom': True}, key='map_hex')
    else:
        st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True}, key='map_chart')

    if _filter_caption:
        st.caption(_filter_caption)

# ── Временная динамика ─────────────────────────────────────────────────────────
st.markdown('<a class="nav-anchor" id="timeseries"></a>', unsafe_allow_html=True)
if ts_occ.empty:
    st.info("Нет данных для графиков динамики.")
else:
    with st.container(border=True):
        st.markdown("### Временная динамика")
        fig_ts = make_subplots(specs=[[{"secondary_y": True}]])

        _ru_days_short = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
        ts_occ["ru_day"] = ts_occ["date"].dt.weekday.map(lambda i: _ru_days_short[i])

        # Праздники — полное название для тултипа
        _ru_holidays_full = {
            "01-01": "Новый год", "01-02": "Новый год", "01-03": "Новый год",
            "01-04": "Новый год", "01-05": "Новый год", "01-06": "Новый год",
            "01-07": "Новый год", "01-08": "Новый год",
            "02-23": "День защитника", "03-08": "8 марта", "05-01": "1 мая",
            "05-09": "День Победы", "06-12": "День России",
            "11-04": "Нар. единство", "12-31": "Новый год",
        }
        ts_occ["holiday"] = ts_occ["date"].dt.strftime("%m-%d").map(_ru_holidays_full)
        ts_occ["holiday"] = ts_occ["holiday"].apply(lambda x: f" · {x}" if pd.notna(x) else "")

        fig_ts.add_trace(go.Scatter(
            x=ts_occ["date"], y=ts_occ["avg_occupancy_pct"],
            name="Загруженность, %", mode="lines+markers",
            line=dict(width=2, color="#3498db"),
            customdata=ts_occ[["ru_day", "holiday"]].values,
            hovertemplate="<b>%{x|%d.%m.%Y} · %{customdata[0]}%{customdata[1]}</b><br>Загруженность: <b>%{y:.1f}%</b><extra></extra>",
        ), secondary_y=False)

        fig_ts.add_trace(go.Scatter(
            x=ts_occ["date"], y=ts_occ["free_rooms_sum"],
            name="Свободных номеров (сумма)", mode="lines+markers",
            line=dict(width=2, color="#e67e22"),
            customdata=ts_occ[["ru_day", "holiday"]].values,
            hovertemplate="Свободных номеров: <b>%{y:.0f}</b><extra></extra>",
        ), secondary_y=True)

        # Выходные — серые полосы
        for d in ts_occ["date"]:
            if d.weekday() >= 5:
                fig_ts.add_vrect(
                    x0=d - pd.Timedelta(hours=12),
                    x1=d + pd.Timedelta(hours=12),
                    fillcolor="rgba(150,150,150,0.25)",
                    line_width=0,
                    layer="below",
                )

        # Праздники — жёлтые пунктирные линии
        _ru_holidays_short = {
            "01-01": "НГ", "01-02": "НГ", "01-03": "НГ", "01-04": "НГ",
            "01-05": "НГ", "01-06": "НГ", "01-07": "НГ", "01-08": "НГ",
            "02-23": "ДЗ", "03-08": "8М", "05-01": "1М", "05-09": "ДП",
            "06-12": "ДР", "11-04": "НЕ", "12-31": "НГ",
        }
        _holiday_legend_added = False
        for d in ts_occ["date"]:
            key = d.strftime("%m-%d")
            if key in _ru_holidays_short:
                fig_ts.add_vline(
                    x=d,
                    line_width=2,
                    line_dash="dot",
                    line_color="rgba(255,200,0,0.9)",
                    layer="below",
                )
                _holiday_legend_added = True

        # Легенда — выходные
        fig_ts.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=12, color="rgba(150,150,150,0.4)", symbol="square"),
            name="Выходные", hoverinfo="skip", showlegend=True,
        ), secondary_y=False)

        # Легенда — праздники (только если есть в данных)
        if _holiday_legend_added:
            fig_ts.add_trace(go.Scatter(
                x=[None], y=[None], mode="lines",
                line=dict(width=2, dash="dot", color="rgba(255,200,0,0.9)"),
                name="Праздники", hoverinfo="skip", showlegend=True,
            ), secondary_y=False)

        fig_ts.update_layout(
            xaxis_title="Дата",
            hovermode="x unified",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
            ),
            margin=dict(t=50, b=40, l=55, r=55),
        )
        fig_ts.update_yaxes(title_text="Загруженность, %", secondary_y=False)
        fig_ts.update_yaxes(title_text="Номеров / свободно, шт", secondary_y=True)
        st.plotly_chart(fig_ts, use_container_width=True, config={"scrollZoom": True})
        if _filter_caption:
            st.caption(_filter_caption)

    st.markdown('<a class="nav-anchor" id="heatmap"></a>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("### Тепловая карта загруженности")
        cal_metric = st.radio("Метрика", options=["avg_occupancy_pct", "avg_free_rooms_pct"], format_func=lambda x: "Загруженность, %" if x == "avg_occupancy_pct" else "Свободные места, %", horizontal=True)
        if cal_metric in ts_occ.columns:
            cal_title = "Средняя загруженность по дням, %" if cal_metric == "avg_occupancy_pct" else "Доля свободных мест по дням, %"
            fig_cal = build_calendar_heatmap(ts_occ, cal_metric, cal_title, reverse_scale=(cal_metric == "avg_free_rooms_pct"))
            st.plotly_chart(fig_cal, use_container_width=True, config={"scrollZoom": False})
            if _filter_caption:
                st.caption(_filter_caption)
        else:
            st.info("Недостаточно данных для построения тепловой карты.")

# ── Загруженность по дням недели ─────────────────────────────────────────────
st.markdown('<a class="nav-anchor" id="weekday"></a>', unsafe_allow_html=True)
if not ts_occ.empty:
    with st.container(border=True):
        st.markdown("### Загруженность по дням недели")
        if _filter_caption:
            st.caption(_filter_caption)

        _ru_days_full = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        dow_df = (
            ts_occ.assign(weekday=ts_occ["date"].dt.weekday)
            .groupby("weekday", as_index=False)["avg_occupancy_pct"]
            .agg(mean="mean", count="count")
        )
        dow_df["day_label"] = dow_df["weekday"].map(lambda i: _ru_days_full[i])
        dow_df["is_weekend"] = dow_df["weekday"] >= 5

        fig_dow = go.Figure(go.Bar(
            x=dow_df["day_label"],
            y=dow_df["mean"].round(1),
            marker_color=dow_df["is_weekend"].map({True: "#e67e22", False: "#3498db"}),
            text=dow_df["mean"].round(1).astype(str) + "%",
            textposition="outside",
            customdata=dow_df["count"].values,
            hovertemplate="<b>%{x}</b><br>Средняя загруженность: <b>%{y:.1f}%</b><br>Наблюдений: <b>%{customdata}</b><extra></extra>",
            showlegend=False,
        ))

        # Легенда вручную
        fig_dow.add_trace(go.Bar(x=[None], y=[None], marker_color="#3498db", name="Будни", showlegend=True))
        fig_dow.add_trace(go.Bar(x=[None], y=[None], marker_color="#e67e22", name="Выходные", showlegend=True))

        fig_dow.update_layout(
            xaxis=dict(categoryorder="array", categoryarray=_ru_days_full),
            yaxis=dict(title="Средняя загруженность, %", range=[0, max(dow_df["mean"].max() * 1.2, 10)]),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=50, b=40, l=55, r=20),
            bargap=0.3,
        )
        st.plotly_chart(fig_dow, use_container_width=True, config={"scrollZoom": False})

# ── Столбчатая диаграмма по городам ──────────────────────────────────────────
st.markdown('<a class="nav-anchor" id="cities"></a>', unsafe_allow_html=True)
with st.container(border=True):
    st.markdown("### Свободные места по городам")
    st.caption(_date_caption)
    city_chart_mode = st.pills("Показать по городам:", options=["Сумма свободных мест", "Среднее свободных мест"], default="Сумма свободных мест")
    if city_chart_mode in (None, "Сумма свободных мест"):
        df_city = filtered_by_city.groupby("city", as_index=False)["free_rooms_display"].sum()
        df_city = df_city.sort_values("free_rooms_display", ascending=False)
        total_free = df_city["free_rooms_display"].sum()
        fig_city = px.bar(df_city, x="city", y="free_rooms_display")
        fig_city.update_traces(marker_color="#4a90d9")
        fig_city.update_layout(showlegend=False, xaxis_title="Город", yaxis_title="Свободных мест (сумма, шт.)", margin=dict(t=30, b=40))
    else:
        df_city = filtered_by_city.groupby("city", as_index=False)["free_rooms_display"].mean()
        df_city = df_city.sort_values("free_rooms_display", ascending=False)
        fig_city = px.bar(df_city, x="city", y="free_rooms_display")
        fig_city.update_traces(marker_color="#4a90d9")
        fig_city.update_layout(showlegend=False, xaxis_title="Город", yaxis_title="Свободных мест (среднее, шт.)", margin=dict(t=10, b=40))
    st.plotly_chart(fig_city, use_container_width=True, config={"scrollZoom": False})
    if _filter_caption:
        st.caption(_filter_caption)

# ── Таблица ───────────────────────────────────────────────────────────────────
st.markdown('<a class="nav-anchor" id="table"></a>', unsafe_allow_html=True)
with st.container(border=True):
    st.markdown("### Данные")
    table_mode = st.radio(
        "Режим таблицы",
        options=["Основные показатели", "Полная таблица"],
        horizontal=True,
        label_visibility="collapsed",
    )
    search = st.text_input("Поиск", placeholder="Название или город...")
    if table_mode == "Основные показатели":
        table_cols = {
            "city": "Город", "name": "Название",
            "source_label": "Источник",
            "occ_display": "Загруженность %",
            "free_rooms_pct_display": "Свободно %",
            "free_rooms_display": "Свободных мест",
            "rooms_total_display": "Номерной фонд",
            "capacity_display": "Вместимость (доступные места)",
            "min_price_display": "Минимальная цена, руб",
        }
        available = {k: v for k, v in table_cols.items() if k in filtered.columns}
        table = (
            filtered[list(available.keys())]
            .rename(columns=available)
            .sort_values("Загруженность %", ascending=False, na_position="last")
            .reset_index(drop=True)
        )
        col_cfg = {}
        if "Загруженность %" in table.columns:
            col_cfg["Загруженность %"] = st.column_config.ProgressColumn("Загруженность %", min_value=0, max_value=100, format="%.1f%%")
        if "Свободно %" in table.columns:
            col_cfg["Свободно %"] = st.column_config.ProgressColumn("Свободно %", min_value=0, max_value=100, format="%.1f%%")
    else:
        table = filtered.drop(columns=["occ_display", "has_data", "hover", "occ_fill"], errors="ignore").reset_index(drop=True)
        col_cfg = {}
    if search:
        mask = pd.Series([False] * len(table), index=table.index)
        for col in ["Название", "Город", "name", "city"]:
            if col in table.columns:
                mask |= table[col].str.contains(search, case=False, na=False)
        table = table[mask]
    table = table.reset_index(drop=True)
    table.insert(0, "№", table.index + 1)
    st.dataframe(table, use_container_width=True, height=400, column_config=col_cfg, hide_index=True)