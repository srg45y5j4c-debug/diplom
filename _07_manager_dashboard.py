# pages/_07_manager_dashboard.py
# сводный дашборд для роли "руководитель" —
# только ключевые показатели рынка, без ml-деталей

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
from config import DB_PATH

REGION_NAMES = {
    1: 'Республика Адыгея', 2: 'Республика Башкортостан',
    3: 'Республика Бурятия', 4: 'Республика Алтай',
    5: 'Республика Дагестан', 6: 'Республика Ингушетия',
    7: 'Кабардино-Балкарская Республика', 8: 'Республика Калмыкия',
    9: 'Карачаево-Черкесская Республика', 10: 'Республика Карелия',
    11: 'Республика Коми', 12: 'Республика Марий Эл',
    13: 'Республика Мордовия', 14: 'Республика Саха (Якутия)',
    15: 'Республика Северная Осетия-Алания', 16: 'Республика Татарстан',
    17: 'Республика Тыва', 18: 'Удмуртская Республика',
    19: 'Республика Хакасия', 20: 'Чеченская Республика',
    21: 'Чувашская Республика', 22: 'Алтайский край',
    23: 'Краснодарский край', 24: 'Красноярский край',
    25: 'Приморский край', 26: 'Ставропольский край',
    27: 'Хабаровский край', 28: 'Амурская область',
    29: 'Архангельская область', 30: 'Астраханская область',
    31: 'Белгородская область', 32: 'Брянская область',
    33: 'Владимирская область', 34: 'Волгоградская область',
    35: 'Вологодская область', 36: 'Воронежская область',
    37: 'Ивановская область', 38: 'Иркутская область',
    39: 'Калининградская область', 40: 'Калужская область',
    41: 'Камчатский край', 42: 'Кемеровская область',
    43: 'Кировская область', 44: 'Костромская область',
    45: 'Курганская область', 46: 'Курская область',
    47: 'Ленинградская область', 48: 'Липецкая область',
    49: 'Магаданская область', 50: 'Московская область',
    51: 'Мурманская область', 52: 'Нижегородская область',
    53: 'Новгородская область', 54: 'Новосибирская область',
    55: 'Омская область', 56: 'Оренбургская область',
    57: 'Орловская область', 58: 'Пензенская область',
    59: 'Пермский край', 60: 'Псковская область',
    61: 'Ростовская область', 62: 'Рязанская область',
    63: 'Самарская область', 64: 'Саратовская область',
    65: 'Сахалинская область', 66: 'Свердловская область',
    67: 'Смоленская область', 68: 'Тамбовская область',
    69: 'Тверская область', 70: 'Томская область',
    71: 'Тульская область', 72: 'Тюменская область',
    73: 'Ульяновская область', 74: 'Челябинская область',
    75: 'Забайкальский край', 76: 'Ярославская область',
    77: 'Москва', 78: 'Санкт-Петербург',
    79: 'Еврейская АО', 83: 'Ненецкий АО',
    86: 'Ханты-Мансийский АО', 87: 'Чукотский АО',
    89: 'Ямало-Ненецкий АО', 91: 'Республика Крым', 92: 'Севастополь',
}


def render_manager_dashboard():
    st.header("Сводка по рынку строительных контрактов")
    st.caption("данные из Единой информационной системы в сфере закупок (ЕИС)")

    try:
        conn = sqlite3.connect(DB_PATH)

        # ключевые показатели
        stats = pd.read_sql_query("""
            SELECT
                COUNT(*)                     AS total,
                SUM(is_terminated)           AS terminated,
                ROUND(AVG(is_terminated)*100, 1) AS risk_pct,
                ROUND(AVG(price)/1000000, 1) AS avg_price_mln,
                ROUND(SUM(price)/1000000000, 1) AS total_bln,
                COUNT(DISTINCT region)       AS regions
            FROM contracts WHERE stage IN ('ET','EC')
        """, conn).iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Контрактов в базе",    f"{int(stats['total']):,}")
        c2.metric("Расторгнуто",          f"{int(stats['terminated']):,}")
        c3.metric("Доля расторжений",     f"{stats['risk_pct']:.1f}%")
        c4.metric("Общий объём",          f"{stats['total_bln']:.0f} млрд руб.")

        st.markdown("---")

        col1, col2 = st.columns(2)

        with col1:
            # динамика по годам — только последние 5
            st.subheader("Динамика расторжений")
            dynamics = pd.read_sql_query("""
                SELECT SUBSTR(exe_start,1,4) AS year,
                    COUNT(*) AS total, SUM(is_terminated) AS terminated,
                    ROUND(AVG(is_terminated)*100,1) AS risk_pct
                FROM contracts
                WHERE stage IN ('ET','EC') AND exe_start IS NOT NULL
                  AND SUBSTR(exe_start,1,4) >= '2019'
                  AND CAST(SUBSTR(exe_start,1,4) AS INTEGER) <= CAST(strftime('%Y','now') AS INTEGER)
                GROUP BY year ORDER BY year
            """, conn)

            if len(dynamics) > 0:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=dynamics['year'], y=dynamics['risk_pct'],
                    mode='lines+markers+text',
                    text=dynamics['risk_pct'].apply(lambda x: f'{x:.1f}%'),
                    textposition='top center',
                    line=dict(color='#991b1b', width=2.5),
                    marker=dict(size=8), name='Доля расторжений'
                ))
                fig.update_layout(
                    height=260, margin=dict(l=0, r=0, t=10, b=0),
                    yaxis_title='Доля расторжений (%)',
                    xaxis_title='Год', showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            # топ рискованных регионов
            st.subheader("Регионы с высоким риском")
            regions = pd.read_sql_query("""
                SELECT region,
                    COUNT(*) AS cnt,
                    ROUND(AVG(is_terminated)*100,1) AS risk_pct
                FROM contracts WHERE stage IN ('ET','EC')
                GROUP BY region HAVING COUNT(*) >= 100
                ORDER BY risk_pct DESC LIMIT 8
            """, conn)
            regions['name'] = regions['region'].map(
                lambda x: REGION_NAMES.get(int(x), f'Регион {x}')
            )
            fig2 = px.bar(
                regions.sort_values('risk_pct'),
                x='risk_pct', y='name', orientation='h',
                color='risk_pct', color_continuous_scale='RdYlGn_r',
                text='risk_pct',
                labels={'risk_pct': 'Доля расторжений (%)', 'name': ''}
            )
            fig2.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig2.update_layout(
                height=280, coloraxis_showscale=False,
                margin=dict(l=0, r=50, t=10, b=0)
            )
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("---")

        # детализация по региону — для контекста принятия решений
        st.subheader("Детализация по вашему региону")
        st.caption("выберите регион чтобы увидеть контекст перед заключением контракта")

        region_list = pd.read_sql_query("""
            SELECT region, COUNT(*) AS cnt,
                ROUND(AVG(is_terminated)*100,1) AS risk_pct
            FROM contracts WHERE stage IN ('ET','EC')
            GROUP BY region HAVING COUNT(*) >= 20
            ORDER BY risk_pct DESC
        """, conn)
        region_list['label'] = region_list['region'].map(
            lambda x: REGION_NAMES.get(int(x), f'Регион {x}')
        ) + region_list['risk_pct'].apply(lambda r: f'  ({r:.1f}% риск)')

        options = dict(zip(region_list['label'], region_list['region'].astype(int)))
        selected_label = st.selectbox("Регион:", list(options.keys()))
        selected_code  = options[selected_label]

        reg = pd.read_sql_query("""
            SELECT COUNT(*) AS total, SUM(is_terminated) AS terminated,
                ROUND(AVG(is_terminated)*100,1) AS risk_pct,
                ROUND(SUM(price)/1000000,1) AS total_mln
            FROM contracts WHERE stage IN ('ET','EC') AND region = ?
        """, conn, params=[selected_code]).iloc[0]

        russia_risk = float(stats['risk_pct'])

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Контрактов в регионе", f"{int(reg['total']):,}")
        r2.metric("Расторгнуто",          f"{int(reg['terminated']):,}")
        r3.metric("Риск в регионе",       f"{reg['risk_pct']:.1f}%",
                  delta=f"{reg['risk_pct']-russia_risk:.1f}% vs РФ",
                  delta_color="inverse")
        r4.metric("Объём контрактов",     f"{reg['total_mln']:.0f} млн руб.")

        col3, col4 = st.columns(2)

        with col3:
            # топ-5 заказчиков в регионе по расторжениям
            top_cust = pd.read_sql_query("""
                SELECT customer_inn,
                    COUNT(*) AS total, SUM(is_terminated) AS terminated,
                    ROUND(AVG(is_terminated)*100,1) AS risk_pct
                FROM contracts WHERE stage IN ('ET','EC') AND region = ?
                GROUP BY customer_inn
                ORDER BY terminated DESC LIMIT 5
            """, conn, params=[selected_code])

            if len(top_cust) > 0:
                st.markdown("**Заказчики с наибольшим числом расторжений**")
                top_cust.columns = ['ИНН заказчика', 'Контрактов',
                                    'Расторгнуто', 'Риск (%)']
                st.dataframe(top_cust, use_container_width=True, hide_index=True)

        with col4:
            # типы работ в регионе
            reg_types = pd.read_sql_query("""
                SELECT
                    CASE WHEN okpd2_csv LIKE '%41.%' THEN 'Здания'
                         WHEN okpd2_csv LIKE '%42.%' THEN 'Инфраструктура'
                         WHEN okpd2_csv LIKE '%43.%' THEN 'Спецработы'
                         ELSE 'Прочее' END AS type,
                    COUNT(*) AS cnt,
                    ROUND(AVG(is_terminated)*100,1) AS risk_pct
                FROM contracts
                WHERE stage IN ('ET','EC') AND region = ?
                GROUP BY type ORDER BY risk_pct DESC
            """, conn, params=[selected_code])

            if len(reg_types) > 0:
                st.markdown("**Риск по типам работ в регионе**")
                fig3 = px.bar(
                    reg_types, x='risk_pct', y='type', orientation='h',
                    color='risk_pct', color_continuous_scale='RdYlGn_r',
                    text='risk_pct',
                    labels={'risk_pct': 'Доля расторжений (%)', 'type': ''}
                )
                fig3.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                fig3.update_layout(height=220, coloraxis_showscale=False,
                                   margin=dict(l=0, r=50, t=10, b=0))
                st.plotly_chart(fig3, use_container_width=True)

        conn.close()

    except Exception as e:
        st.error(f"ошибка загрузки данных: {e}")
        import traceback
        st.code(traceback.format_exc())