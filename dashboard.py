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
def load_occupancy_timeseries(all_data_dir: Path, cities: tuple = (), hotels: tuple = ()) -> pd.DataFrame:
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
        if cities and "city" in part.columns:
            part = part[part["city"].isin(cities)]
        if hotels and "name" in part.columns:
            part = part[part["name"].isin(hotels)]
        if part.empty:
            continue
        part["avg_occupancy_pct"] = pd.to_numeric(part["avg_occupancy_pct"], errors="coerce")
        m = part["avg_occupancy_pct"].mean()
        if pd.isna(m):
            continue
        room_sum = float(_rooms_per_hotel_series(part).sum(skipna=True))
        free_sum = float(pd.to_numeric(part["avg_free_rooms"], errors="coerce").sum(skipna=True)) if "avg_free_rooms" in part.columns else 0.0
        free_pct_mean = float(pd.to_numeric(part["avg_free_rooms_pct"], errors="coerce").mean(skipna=True)) if "avg_free_rooms_pct" in part.columns else round(100.0 - float(m), 1)
        rows.append({"date": day, "avg_occupancy_pct": float(m), "avg_free_rooms_pct": free_pct_mean, "total_rooms_sum": room_sum, "free_rooms_sum": free_sum})
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values("date")
    out["date"] = pd.to_datetime(out["date"])
    return out


def build_calendar_heatmap(ts: pd.DataFrame, metric_col: str, title: str) -> go.Figure:
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
        colorscale=[[0.00,"#00e676"],[0.25,"#69f0ae"],[0.50,"#ffff00"],[0.75,"#ffab00"],[1.00,"#ff5252"]],
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
        avg_occ=('avg_occupancy_pct', 'mean'),
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
    st.markdown("### Фильтры")
    cities = sorted(df["city"].dropna().unique())
    sel_cities = st.multiselect("Город", cities, default=cities)

    all_hotels_in_cities = sorted(df[df["city"].isin(sel_cities)]["name"].dropna().unique()) if sel_cities else []
    sel_hotels = st.multiselect("Объект размещения", all_hotels_in_cities, default=[], placeholder="Все объекты")

    min_val = int(math.floor(df['avg_occupancy_pct'].min()))
    max_val = int(math.ceil(df['avg_occupancy_pct'].max()))
    if min_val == max_val:
        max_val += 1
    occ_min, occ_max = st.slider("Загруженность, %", min_value=min_val, max_value=max_val, value=(min_val, max_val))

# Фильтрация
filtered_by_city = df[df["city"].isin(sel_cities)].copy()  # для столбчатой диаграммы
filtered = filtered_by_city.copy()
if sel_hotels:
    filtered = filtered[filtered["name"].isin(sel_hotels)]
filtered = filtered[
    filtered["avg_occupancy_pct"].isna() | filtered["avg_occupancy_pct"].between(occ_min, occ_max)
].copy()
filtered_by_city = filtered_by_city[
    filtered_by_city["avg_occupancy_pct"].isna() | filtered_by_city["avg_occupancy_pct"].between(occ_min, occ_max)
].copy()

def _format_int(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    try:
        return f"{int(round(float(x))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"

rooms_total_filtered = float(_rooms_per_hotel_series(filtered).sum(skipna=True)) if not filtered.empty else float("nan")
free_total_filtered = float(pd.to_numeric(filtered["avg_free_rooms"], errors="coerce").sum(skipna=True)) if not filtered.empty and "avg_free_rooms" in filtered.columns else float("nan")

with st.container(border=True):
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Отелей на карте", len(filtered))
    c2.metric("Средняя загруженность", f"{filtered['avg_occupancy_pct'].mean():.1f}%" if not filtered.empty else "—")
    c3.metric("Среднее свободных мест, %", f"{filtered['avg_free_rooms_pct'].mean():.1f}%" if not filtered.empty else "—")
    c4.metric("Всего номеров", _format_int(rooms_total_filtered))
    c5.metric("Свободных номеров", _format_int(free_total_filtered))

# Цвет: синий для отелей без данных, иначе шкала загруженности
filtered["occ_display"] = filtered["avg_occupancy_pct"]
filtered["has_data"] = filtered["avg_occupancy_pct"].notna()

filtered["hover"] = (
    "<b>" + filtered["name"].fillna("") + "</b><br>"
    + filtered["city"].fillna("") + "<br>"
    + "Свободных номеров: <b>"
    + filtered["avg_free_rooms"].apply(lambda x: f"{int(round(x))} шт." if pd.notna(x) else "нет данных")
    + "</b><br>"
    + "Номерной фонд: <b>"
    + filtered.apply(lambda row: f"{_rooms_total(row)} шт." if _rooms_total(row) is not None else "нет данных", axis=1)
    + "</b><br>"
    + "Свободно: <b>"
    + filtered["avg_free_rooms_pct"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "нет данных")
    + "</b><br>"
    + "Загружено: <b>"
    + filtered["avg_occupancy_pct"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "нет данных")
    + "</b>"
)

# Разделяем на два слоя: с данными и без
filtered_with = filtered[filtered["has_data"]].copy()
filtered_without = filtered[~filtered["has_data"]].copy()

fig = go.Figure()

# Слой 1: отели с данными — цвет = загруженность
if not filtered_with.empty:
    filtered_with["occ_fill"] = filtered_with["avg_occupancy_pct"].fillna(0)
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
        showlegend=False,
    ))

# Слой 2: отели без данных — синие
if not filtered_without.empty:
    fig.add_trace(go.Scattermapbox(
        lat=filtered_without["lat"],
        lon=filtered_without["lon"],
        mode="markers",
        marker=go.scattermapbox.Marker(size=12, color="#7fb3d3", opacity=0.8),
        customdata=filtered_without[["hover", "name"]].values,
        hovertemplate="%{customdata[0]}<extra></extra>",
        name="Нет данных о загруженности",
        showlegend=True,
    ))

# Всегда добавляем легенду "Нет данных" (невидимый маркер если таких нет)
fig.add_trace(go.Scattermapbox(
    lat=[None], lon=[None],
    mode="markers",
    marker=go.scattermapbox.Marker(size=12, color="#7fb3d3", opacity=0.8),
    name="Нет данных о загруженности",
    showlegend=len(filtered_without) == 0,  # показываем всегда для стабильности
))

fig.update_layout(
    mapbox=dict(style="open-street-map", zoom=5.5, center={"lat": 54.0, "lon": 103.5}),
    margin={"t": 0, "b": 0, "l": 0, "r": 0},
    dragmode="pan",
    height=650,
    legend=dict(x=0.01, y=0.99, bgcolor=_legend_bg, font=dict(color=_legend_font_color), itemsizing="constant"),
)

# Обработка клика по карте для фильтра отелей
ts_occ = load_occupancy_timeseries(all_data_dir, tuple(sorted(sel_cities)), tuple(sorted(sel_hotels)))

# Подпись фильтров (переиспользуется ниже)
_filter_parts = []
if sel_cities and len(sel_cities) < len(cities):
    _filter_parts.append(f"Города: {', '.join(sel_cities)}")
if sel_hotels and len(sel_hotels) < len(all_hotels_in_cities):
    _filter_parts.append(f"Объекты: {', '.join(sel_hotels)}")
_filter_caption = ("Фильтр: " + " · ".join(_filter_parts)) if _filter_parts else ""

# ── Карта ─────────────────────────────────────────────────────────────────────
with st.container(border=True):
    st.markdown("### Карта")
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
        _full = filtered_with[filtered_with['avg_occupancy_pct'] >= 100].copy()
        _free = filtered_with[filtered_with['avg_occupancy_pct'] < 100].copy()

        if not _free.empty:
            fig_hex.add_trace(go.Scattermapbox(
                lat=_free['lat'], lon=_free['lon'],
                mode='markers',
                marker=go.scattermapbox.Marker(size=8, color='#111111', opacity=0.9),
                customdata=_free[['hover']].values,
                hovertemplate='%{customdata[0]}<extra></extra>',
                name='Есть свободные места',
                showlegend=True,
            ))

        if not _full.empty:
            fig_hex.add_trace(go.Scattermapbox(
                lat=_full['lat'], lon=_full['lon'],
                mode='markers',
                marker=go.scattermapbox.Marker(size=8, color='#ffffff', opacity=0.9),
                customdata=_full[['hover']].values,
                hovertemplate='%{customdata[0]}<extra></extra>',
                name='Загруженность 100%',
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

    _date_caption = f"Данные на: {Path(selected_name).stem}"
    if _filter_caption:
        st.caption(f"{_date_caption} · {_filter_caption}")
    else:
        st.caption(_date_caption)
# ── Временная динамика ─────────────────────────────────────────────────────────
if ts_occ.empty:
    st.info("Нет данных для графиков динамики.")
else:
    with st.container(border=True):
        st.markdown("### Временная динамика")
        fig_ts = make_subplots(specs=[[{"secondary_y": True}]])
        fig_ts.add_trace(go.Scatter(x=ts_occ["date"], y=ts_occ["avg_occupancy_pct"], name="Загруженность, %", mode="lines+markers", line=dict(width=2, color="#3498db")), secondary_y=False)
        fig_ts.add_trace(go.Scatter(x=ts_occ["date"], y=ts_occ["free_rooms_sum"], name="Свободных номеров (сумма)", mode="lines+markers", line=dict(width=2, color="#e67e22")), secondary_y=True)
        fig_ts.update_layout(xaxis_title="Дата", hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), margin=dict(t=50, b=40, l=55, r=55))
        fig_ts.update_yaxes(title_text="Загруженность, %", secondary_y=False)
        fig_ts.update_yaxes(title_text="Номеров / свободно, шт", secondary_y=True)
        st.plotly_chart(fig_ts, use_container_width=True, config={"scrollZoom": True})
        if _filter_caption:
            st.caption(_filter_caption)

    with st.container(border=True):
        st.markdown("### Тепловая карта загруженности")
        cal_metric = st.radio("Метрика", options=["avg_occupancy_pct", "avg_free_rooms_pct"], format_func=lambda x: "Загруженность, %" if x == "avg_occupancy_pct" else "Свободные места, %", horizontal=True)
        if cal_metric in ts_occ.columns:
            cal_title = "Средняя загруженность по дням, %" if cal_metric == "avg_occupancy_pct" else "Доля свободных мест по дням, %"
            fig_cal = build_calendar_heatmap(ts_occ, cal_metric, cal_title)
            st.plotly_chart(fig_cal, use_container_width=True, config={"scrollZoom": False})
            if _filter_caption:
                st.caption(_filter_caption)
        else:
            st.info("Недостаточно данных для построения тепловой карты.")

# ── Столбчатая диаграмма по городам ──────────────────────────────────────────
with st.container(border=True):
    st.markdown("### Загруженность номерного фонда по городам")
    city_chart_mode = st.pills("Показать по городам:", options=["Общее кол-во мест", "Среднее кол-во мест"], default="Общее кол-во мест")
    if city_chart_mode in (None, "Общее кол-во мест"):
        df_city = filtered_by_city.groupby("city", as_index=False)["avg_free_rooms"].sum()
        total_free = df_city["avg_free_rooms"].sum()
        df_city["_pct_label"] = (df_city["avg_free_rooms"] / total_free * 100).map(lambda x: f"{x:.1f}%") if total_free else "0.0%"
        fig_city = px.bar(df_city, x="city", y="avg_free_rooms", color="city", text="_pct_label")
        fig_city.update_traces(textposition="outside")
        fig_city.update_layout(showlegend=False, xaxis_title="Город", yaxis_title="Сумма (avg_free_rooms)", margin=dict(t=30, b=40))
    else:
        df_city = filtered_by_city.groupby("city", as_index=False)["avg_free_rooms"].mean()
        fig_city = px.bar(df_city, x="city", y="avg_free_rooms", color="city")
        fig_city.update_layout(showlegend=False, xaxis_title="Город", yaxis_title="Среднее (avg_free_rooms)", margin=dict(t=10, b=40))
    st.plotly_chart(fig_city, use_container_width=True, config={"scrollZoom": False})
    if _filter_caption:
        st.caption(f"{_date_caption} · {_filter_caption}")
    else:
        st.caption(_date_caption)

# ── Таблица ───────────────────────────────────────────────────────────────────
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
            "avg_occupancy_pct": "Загруженность %",
            "avg_free_rooms_pct": "Свободно %",
            "avg_free_rooms": "Свободных мест",
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
    st.dataframe(table, use_container_width=True, height=400, column_config=col_cfg, hide_index=True)