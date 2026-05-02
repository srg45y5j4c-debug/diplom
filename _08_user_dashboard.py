# pages/_08_user_dashboard.py
# мини-дашборд для роли "специалист по контрактам" —
# только контекст по выбранному региону для принятия решений

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


def render_user_dashboard():
    st.header("Статистика по региону")
    st.caption(
        "справочная информация об уровне риска расторжений в вашем регионе — "
        "помогает оценить контракт в контексте рынка"
    )

    try:
        conn = sqlite3.connect(DB_PATH)

        # средний риск по России для сравнения
        russia_risk = pd.read_sql_query(
            "SELECT ROUND(AVG(is_terminated)*100,1) AS r FROM contracts WHERE stage IN ('ET','EC')",
            conn
        ).iloc[0]['r']

        # список регионов с сортировкой по риску
        region_list = pd.read_sql_query("""
            SELECT region,
                COUNT(*) AS cnt,
                ROUND(AVG(is_terminated)*100,1) AS risk_pct
            FROM contracts WHERE stage IN ('ET','EC')
            GROUP BY region HAVING COUNT(*) >= 20
            ORDER BY risk_pct DESC
        """, conn)
        region_list['label'] = region_list['region'].map(
            lambda x: REGION_NAMES.get(int(x), f'Регион {x}')
        )

        selected_label = st.selectbox(
            "Выберите ваш регион:",
            options=region_list['label'].tolist(),
        )
        selected_row  = region_list[region_list['label'] == selected_label].iloc[0]
        selected_code = int(selected_row['region'])

        st.markdown("---")

        # метрики по региону
        reg = pd.read_sql_query("""
            SELECT COUNT(*) AS total, SUM(is_terminated) AS terminated,
                ROUND(AVG(is_terminated)*100,1) AS risk_pct,
                ROUND(AVG(price)/1000000,1) AS avg_mln,
                ROUND(SUM(price)/1000000,0) AS total_mln
            FROM contracts WHERE stage IN ('ET','EC') AND region = ?
        """, conn, params=[selected_code]).iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Контрактов в регионе", f"{int(reg['total']):,}")
        c2.metric("Расторгнуто",           f"{int(reg['terminated']):,}")
        c3.metric("Доля расторжений",      f"{reg['risk_pct']:.1f}%",
                  delta=f"{reg['risk_pct'] - russia_risk:.1f}% vs РФ ({russia_risk:.1f}%)",
                  delta_color="inverse")
        c4.metric("Средняя цена контракта", f"{reg['avg_mln']:.1f} млн руб.")

        # оценка уровня риска региона
        if reg['risk_pct'] < russia_risk - 3:
            st.success(
                f"Регион {selected_label} — **ниже среднего по РФ**. "
                f"Уровень расторжений {reg['risk_pct']:.1f}% против {russia_risk:.1f}% по стране."
            )
        elif reg['risk_pct'] > russia_risk + 3:
            st.warning(
                f"Регион {selected_label} — **выше среднего по РФ**. "
                f"Уровень расторжений {reg['risk_pct']:.1f}% против {russia_risk:.1f}% по стране. "
                "Рекомендуем тщательно проверять поставщиков."
            )
        else:
            st.info(
                f"Регион {selected_label} — **на уровне среднего по РФ** "
                f"({reg['risk_pct']:.1f}% vs {russia_risk:.1f}%)."
            )

        st.markdown("---")

        col1, col2 = st.columns(2)

        with col1:
            # топ-5 заказчиков региона по расторжениям
            st.subheader("Топ-5 заказчиков по расторжениям")
            st.caption("заказчики с наибольшим числом расторгнутых контрактов в вашем регионе")

            top_cust = pd.read_sql_query("""
                SELECT customer_inn,
                    COUNT(*) AS total,
                    SUM(is_terminated) AS terminated,
                    ROUND(AVG(is_terminated)*100,1) AS risk_pct
                FROM contracts WHERE stage IN ('ET','EC') AND region = ?
                GROUP BY customer_inn HAVING SUM(is_terminated) >= 1
                ORDER BY terminated DESC LIMIT 5
            """, conn, params=[selected_code])

            if not top_cust.empty:
                top_cust.columns = ['ИНН заказчика', 'Контрактов',
                                    'Расторгнуто', 'Риск (%)']

                def color_risk(val):
                    if isinstance(val, float):
                        if val >= 40:
                            return 'background-color: #fee2e2; color: #991b1b'
                        elif val >= 25:
                            return 'background-color: #fef3c7; color: #92400e'
                    return ''

                st.dataframe(
                    top_cust.style.applymap(color_risk, subset=['Риск (%)']),
                    use_container_width=True, hide_index=True
                )
            else:
                st.info("данных недостаточно")

        with col2:
            # риск по типам работ в регионе
            st.subheader("Риск по типам строительства")
            st.caption("в каком виде работ расторжений больше всего в вашем регионе")

            reg_types = pd.read_sql_query("""
                SELECT
                    CASE WHEN okpd2_csv LIKE '%41.%' THEN 'Здания'
                         WHEN okpd2_csv LIKE '%42.%' THEN 'Инфраструктура'
                         WHEN okpd2_csv LIKE '%43.%' THEN 'Спецработы'
                         ELSE 'Прочее' END AS type,
                    COUNT(*) AS cnt,
                    ROUND(AVG(is_terminated)*100,1) AS risk_pct
                FROM contracts WHERE stage IN ('ET','EC') AND region = ?
                GROUP BY type ORDER BY risk_pct DESC
            """, conn, params=[selected_code])

            if not reg_types.empty:
                fig = px.bar(
                    reg_types.sort_values('risk_pct'),
                    x='risk_pct', y='type', orientation='h',
                    color='risk_pct', color_continuous_scale='RdYlGn_r',
                    text='risk_pct',
                    labels={'risk_pct': 'Доля расторжений (%)', 'type': ''}
                )
                fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                fig.update_layout(
                    height=240, coloraxis_showscale=False,
                    margin=dict(l=0, r=60, t=10, b=0)
                )
                st.plotly_chart(fig, use_container_width=True)

        # динамика по годам в регионе
        st.subheader("Динамика расторжений в регионе по годам")
        by_year = pd.read_sql_query("""
            SELECT SUBSTR(exe_start,1,4) AS year,
                COUNT(*) AS total, SUM(is_terminated) AS terminated,
                ROUND(AVG(is_terminated)*100,1) AS risk_pct
            FROM contracts
            WHERE stage IN ('ET','EC') AND region = ?
              AND exe_start IS NOT NULL
              AND SUBSTR(exe_start,1,4) >= '2019'
              AND CAST(SUBSTR(exe_start,1,4) AS INTEGER) <= CAST(strftime('%Y','now') AS INTEGER)
            GROUP BY year ORDER BY year
        """, conn, params=[selected_code])

        if not by_year.empty:
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=by_year['year'], y=by_year['total'],
                name='Всего', marker_color='#003087'
            ))
            fig2.add_trace(go.Bar(
                x=by_year['year'], y=by_year['terminated'],
                name='Расторгнуто', marker_color='#991b1b'
            ))
            fig2.add_trace(go.Scatter(
                x=by_year['year'], y=by_year['risk_pct'],
                name='Риск (%)', yaxis='y2',
                mode='lines+markers',
                line=dict(color='#92400e', width=2), marker=dict(size=7)
            ))
            fig2.update_layout(
                barmode='group', height=300,
                margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(orientation='h', yanchor='bottom', y=1.02),
                yaxis=dict(title='Контрактов'),
                yaxis2=dict(title='Доля (%)', overlaying='y',
                            side='right', showgrid=False)
            )
            st.plotly_chart(fig2, use_container_width=True)

        conn.close()

    except Exception as e:
        st.error(f"ошибка загрузки данных: {e}")
        import traceback
        st.code(traceback.format_exc())