# pages/_01_dashboard.py
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
    89: 'Ямало-Ненецкий АО',
    91: 'Республика Крым', 92: 'Севастополь',
}


def group_reason(text):
    """группировка свободных формулировок причин расторжения в смысловые категории"""
    t = str(text).lower()
    if any(w in t for w in ['соглаш', 'обоюдн', 'взаимн']):
        return 'Соглашение сторон'
    if any(w in t for w in ['односторонн', 'отказ заказчик', 'отказ поставщик']):
        return 'Односторонний отказ'
    if any(w in t for w in ['наруш', 'неисполн', 'не выпол', 'по вине']):
        return 'Нарушение условий'
    if any(w in t for w in ['срок', 'просрочк']):
        return 'Нарушение сроков'
    if any(w in t for w in ['качеств', 'недостатк', 'дефект', 'несоответств']):
        return 'Несоответствие качеству'
    if any(w in t for w in ['потребност', 'необходимост', 'отсутств', 'отпал']):
        return 'Отсутствие потребности'
    if any(w in t for w in ['банкрот', 'ликвидац']):
        return 'Банкротство поставщика'
    if any(w in t for w in ['суд', 'арбитраж']):
        return 'Судебное решение'
    if any(w in t for w in ['статья', 'ст. ', '44-фз', 'гк рф']):
        return 'Юридические основания'
    return 'Прочие причины'


def render_region_detail(conn, region_code, region_name, russia_risk):
    """детализация по выбранному региону — вызывается из аккордеона"""
    reg_stats = pd.read_sql_query("""
        SELECT
            COUNT(*)                           AS total,
            SUM(is_terminated)                 AS terminated,
            ROUND(AVG(is_terminated) * 100, 1) AS risk_pct,
            ROUND(AVG(price) / 1000000, 2)     AS avg_price_mln,
            ROUND(SUM(price) / 1000000, 1)     AS total_mln
        FROM contracts
        WHERE stage IN ('ET', 'EC') AND region = ?
    """, conn, params=[region_code]).iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Всего контрактов", f"{int(reg_stats['total']):,}")
    c2.metric("Расторгнуто",      f"{int(reg_stats['terminated']):,}")
    c3.metric("Доля расторжений", f"{reg_stats['risk_pct']:.1f}%",
              delta=f"{reg_stats['risk_pct'] - russia_risk:+.1f}% vs РФ",
              delta_color="inverse")
    c4.metric("Средняя цена",     f"{reg_stats['avg_price_mln']:.1f} млн руб.")

    col1, col2 = st.columns(2)

    with col1:
        # динамика по годам
        by_year = pd.read_sql_query("""
            SELECT
                SUBSTR(exe_start, 1, 4)            AS year,
                COUNT(*)                            AS total,
                SUM(is_terminated)                  AS terminated,
                ROUND(AVG(is_terminated) * 100, 1)  AS risk_pct
            FROM contracts
            WHERE stage IN ('ET', 'EC') AND region = ?
              AND exe_start IS NOT NULL
              AND SUBSTR(exe_start, 1, 4) >= '2014'
              AND CAST(SUBSTR(exe_start, 1, 4) AS INTEGER) <= CAST(strftime('%Y', 'now') AS INTEGER)
            GROUP BY year ORDER BY year
        """, conn, params=[region_code])

        if len(by_year) > 0:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=by_year['year'], y=by_year['total'],
                name='Всего', marker_color='#003087'
            ))
            fig.add_trace(go.Bar(
                x=by_year['year'], y=by_year['terminated'],
                name='Расторгнуто', marker_color='#991b1b'
            ))
            fig.add_trace(go.Scatter(
                x=by_year['year'], y=by_year['risk_pct'],
                name='Доля (%)', yaxis='y2',
                mode='lines+markers',
                line=dict(color='#92400e', width=2),
                marker=dict(size=7)
            ))
            fig.update_layout(
                barmode='group', height=300,
                margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(orientation='h', yanchor='bottom', y=1.02),
                yaxis=dict(title='Контрактов'),
                yaxis2=dict(title='Доля (%)', overlaying='y',
                            side='right', showgrid=False)
            )
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        # риск по типам строительства в регионе
        types = pd.read_sql_query("""
            SELECT
                CASE
                    WHEN okpd2_csv LIKE '%41.%' THEN 'Здания'
                    WHEN okpd2_csv LIKE '%42.%' THEN 'Инфраструктура'
                    WHEN okpd2_csv LIKE '%43.%' THEN 'Спецработы'
                    ELSE 'Прочее'
                END AS type,
                COUNT(*) AS total, SUM(is_terminated) AS terminated,
                ROUND(AVG(is_terminated) * 100, 1) AS risk_pct
            FROM contracts
            WHERE stage IN ('ET', 'EC') AND region = ?
            GROUP BY type ORDER BY risk_pct DESC
        """, conn, params=[region_code])

        if len(types) > 0:
            fig2 = px.bar(
                types, x='risk_pct', y='type', orientation='h',
                text='risk_pct', color='risk_pct',
                color_continuous_scale='RdYlGn_r',
                labels={'risk_pct': 'Доля расторжений (%)', 'type': 'Тип'}
            )
            fig2.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig2.update_layout(height=260, coloraxis_showscale=False,
                               margin=dict(l=0, r=60, t=10, b=0))
            st.plotly_chart(fig2, use_container_width=True)

    # причины расторжений в регионе
    reasons = pd.read_sql_query("""
        SELECT pf.termination_reason_info, COUNT(*) AS count
        FROM procedures_flat pf
        JOIN contracts c ON c.reg_num = pf.reg_num
        WHERE c.region = ? AND c.stage IN ('ET', 'EC')
          AND pf.termination_reason_info IS NOT NULL
          AND LENGTH(pf.termination_reason_info) > 3
        GROUP BY pf.termination_reason_info
        ORDER BY count DESC
    """, conn, params=[region_code])

    col3, col4 = st.columns(2)

    with col3:
        if len(reasons) > 0:
            reasons['group'] = reasons['termination_reason_info'].apply(group_reason)
            grouped = (
                reasons.groupby('group')['count'].sum()
                .reset_index().sort_values('count', ascending=False)
            )
            fig3 = px.pie(
                grouped, values='count', names='group',
                color_discrete_sequence=px.colors.qualitative.Set2, hole=0.35
            )
            fig3.update_traces(textposition='inside', textinfo='percent+label')
            fig3.update_layout(height=300, showlegend=False,
                               title_text='Причины расторжений')
            st.plotly_chart(fig3, use_container_width=True)

    with col4:
        # топ-5 заказчиков региона
        customers = pd.read_sql_query("""
            SELECT customer_inn,
                COUNT(*) AS total, SUM(is_terminated) AS terminated,
                ROUND(AVG(is_terminated) * 100, 1) AS risk_pct
            FROM contracts
            WHERE stage IN ('ET', 'EC') AND region = ?
            GROUP BY customer_inn
            HAVING COUNT(*) >= 3
            ORDER BY terminated DESC LIMIT 5
        """, conn, params=[region_code])

        if len(customers) > 0:
            customers.columns = ['ИНН заказчика', 'Контрактов', 'Расторгнуто', 'Риск (%)']
            st.markdown("**Топ-5 заказчиков по расторжениям**")
            st.dataframe(customers, use_container_width=True, hide_index=True)

    # сравнение с общероссийским уровнем
    compare_df = pd.DataFrame({
        'Территория':       ['Россия в целом', region_name],
        'Доля расторжений': [russia_risk, reg_stats['risk_pct']]
    })
    fig_cmp = px.bar(
        compare_df, x='Территория', y='Доля расторжений',
        text='Доля расторжений',
        color='Территория',
        color_discrete_map={
            'Россия в целом': '#003087',
            region_name:      '#991b1b'
        }
    )
    fig_cmp.update_traces(texttemplate='%{y:.1f}%', textposition='outside')
    fig_cmp.update_layout(height=280, showlegend=False,
                          yaxis_title='Доля расторжений (%)',
                          margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig_cmp, use_container_width=True)


def render_dashboard():
    """главная аналитическая страница по всей базе контрактов"""
    st.header("Панель управления рисками")

    try:
        conn = sqlite3.connect(DB_PATH)

        # общая статистика
        # получаем доступные годы для фильтра
        years_df = pd.read_sql_query("""
            SELECT DISTINCT SUBSTR(exe_start, 1, 4) AS year
            FROM contracts
            WHERE stage IN ('ET', 'EC') AND exe_start IS NOT NULL
              AND SUBSTR(exe_start, 1, 4) >= '2014'
              AND CAST(SUBSTR(exe_start, 1, 4) AS INTEGER) <= CAST(strftime('%Y', 'now') AS INTEGER)
            ORDER BY year
        """, conn)
        available_years = ["Все годы"] + years_df['year'].tolist()

        selected_year = st.selectbox(
            "Период:", options=available_years, index=0,
            label_visibility="collapsed"
        )
        year_filter = (
            f"AND SUBSTR(exe_start, 1, 4) = '{selected_year}'"
            if selected_year != "Все годы" else ""
        )

        stats = pd.read_sql_query(f"""
            SELECT
                COUNT(*)                     AS total_contracts,
                SUM(is_terminated)           AS terminated_contracts,
                AVG(is_terminated) * 100     AS risk_percent,
                AVG(price)                   AS avg_price,
                COUNT(DISTINCT customer_inn) AS total_customers,
                COUNT(DISTINCT region)       AS total_regions
            FROM contracts
            WHERE stage IN ('ET', 'EC') {year_filter}
        """, conn).iloc[0]

        russia_risk = round(float(stats['risk_percent']), 1)

        if selected_year != "Все годы":
            st.info(
                f"Показаны данные за **{selected_year}** год. "
                "Графики и детальные блоки ниже отображают полную историю для контекста."
            )

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Всего контрактов</h3>
                <h2>{int(stats['total_contracts']):,}</h2>
            </div>""", unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Расторгнуто</h3>
                <h2>{int(stats['terminated_contracts']):,}</h2>
            </div>""", unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Доля расторжений</h3>
                <h2>{russia_risk:.1f}%</h2>
            </div>""", unsafe_allow_html=True)
        with col4:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Средняя цена</h3>
                <h2>{stats['avg_price']/1_000_000:.1f} млн руб.</h2>
            </div>""", unsafe_allow_html=True)
        with col5:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Регионов</h3>
                <h2>{int(stats['total_regions'])}</h2>
            </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # динамика расторжений по времени
        with st.expander("Динамика расторжений по времени", expanded=True):
            if selected_year == "Все годы":
                st.caption("как менялась доля расторжений год от года")
                dynamics = pd.read_sql_query("""
                    SELECT SUBSTR(exe_start, 1, 4) AS period,
                        COUNT(*) AS total, SUM(is_terminated) AS terminated,
                        ROUND(AVG(is_terminated) * 100, 1) AS risk_pct
                    FROM contracts
                    WHERE stage IN ('ET', 'EC') AND exe_start IS NOT NULL
                      AND SUBSTR(exe_start, 1, 4) >= '2014'
                      AND CAST(SUBSTR(exe_start, 1, 4) AS INTEGER) <= CAST(strftime('%Y', 'now') AS INTEGER)
                    GROUP BY period ORDER BY period
                """, conn)
                x_label = "Год"
            else:
                st.caption(f"помесячная динамика за {selected_year} год")
                dynamics = pd.read_sql_query(f"""
                    SELECT SUBSTR(exe_start, 1, 7) AS period,
                        COUNT(*) AS total, SUM(is_terminated) AS terminated,
                        ROUND(AVG(is_terminated) * 100, 1) AS risk_pct
                    FROM contracts
                    WHERE stage IN ('ET', 'EC') AND exe_start IS NOT NULL
                      AND SUBSTR(exe_start, 1, 4) = '{selected_year}'
                    GROUP BY period ORDER BY period
                """, conn)
                x_label = "Месяц"
            if len(dynamics) > 0:
                col1, col2 = st.columns(2)
                with col1:
                    fig = go.Figure()
                    fig.add_trace(go.Bar(x=dynamics['period'], y=dynamics['total'],
                        name='Всего', marker_color='#003087'))
                    fig.add_trace(go.Bar(x=dynamics['period'], y=dynamics['terminated'],
                        name='Расторгнуто', marker_color='#991b1b'))
                    fig.update_layout(barmode='group', height=300,
                        margin=dict(l=0, r=0, t=10, b=0),
                        legend=dict(orientation='h', yanchor='bottom', y=1.02),
                        xaxis_title=x_label)
                    st.plotly_chart(fig, use_container_width=True)
                with col2:
                    fig2 = go.Figure()
                    fig2.add_trace(go.Scatter(
                        x=dynamics['period'], y=dynamics['risk_pct'],
                        mode='lines+markers+text',
                        text=dynamics['risk_pct'].apply(lambda x: f'{x:.1f}%'),
                        textposition='top center',
                        line=dict(color='#991b1b', width=2.5), marker=dict(size=8)
                    ))
                    fig2.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                        yaxis_title='Доля расторжений (%)', xaxis_title=x_label)
                    st.plotly_chart(fig2, use_container_width=True)
        # риск по типам строительства
        with st.expander("Риск по типам строительства", expanded=True):
            type_stats = pd.read_sql_query(f"""
                SELECT
                    CASE WHEN okpd2_csv LIKE '%41.%' THEN 'Здания'
                         WHEN okpd2_csv LIKE '%42.%' THEN 'Инфраструктура'
                         WHEN okpd2_csv LIKE '%43.%' THEN 'Спецработы'
                         ELSE 'Прочее' END AS type,
                    COUNT(*) AS count,
                    AVG(is_terminated) * 100  AS risk,
                    SUM(price) / 1000000      AS total_mln,
                    AVG(price) / 1000000      AS avg_mln
                FROM contracts WHERE stage IN ('ET', 'EC') {year_filter}
                GROUP BY type ORDER BY risk DESC
            """, conn)

            # пояснение классификации типов работ по окпд2
            with st.expander("Что входит в каждую категорию?"):
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown("""
                    **Здания (ОКПД2 41.x)**
                    Строительство жилых и нежилых зданий:
                    - многоквартирные дома
                    - школы, больницы, детские сады
                    - административные здания
                    - торговые центры, склады
                    - производственные корпуса
                    """)
                with c2:
                    st.markdown("""
                    **Инфраструктура (ОКПД2 42.x)**
                    Строительство инженерных сооружений:
                    - автомобильные и железные дороги
                    - мосты, путепроводы, тоннели
                    - трубопроводы, сети водоснабжения
                    - электростанции, ЛЭП
                    - порты, аэродромы
                    """)
                with c3:
                    st.markdown("""
                    **Спецработы (ОКПД2 43.x)**
                    Специализированные строительные работы:
                    - снос и демонтаж зданий
                    - подготовка строительной площадки
                    - электромонтажные работы
                    - сантехника, вентиляция, кондиционирование
                    - отделочные и кровельные работы
                    """)
                with c4:
                    st.markdown("""
                    **Прочее**
                    Контракты со смежными кодами ОКПД2 (не 41–43),
                    которые попали в выборку через других поставщиков:
                    - монтаж видеонаблюдения и пожарной сигнализации
                    - оснащение спортивных и детских площадок
                    - электромонтажные и пусконаладочные работы
                    - благоустройство и праздничное оформление
                    - поставка и монтаж оборудования
                    """)

            col1, col2 = st.columns(2)
            with col1:
                fig = px.bar(type_stats, x='type', y='risk', color='risk',
                    color_continuous_scale='RdYlGn_r', text='count',
                    labels={'type': 'Тип работ', 'risk': 'Доля расторжений (%)'})
                fig.update_traces(texttemplate='%{text} контрактов', textposition='outside')
                fig.update_layout(height=340, coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                d = type_stats.copy()
                d['risk']      = d['risk'].round(2)
                d['total_mln'] = d['total_mln'].round(1)
                d['avg_mln']   = d['avg_mln'].round(1)
                d.columns = ['Тип работ', 'Контрактов', 'Риск (%)',
                             'Сумма (млн руб.)', 'Ср. цена (млн руб.)']
                st.dataframe(d, use_container_width=True, hide_index=True)

        # риск по ценовым диапазонам
        with st.expander("Риск по ценовым диапазонам контрактов"):
            st.caption("контракты какой стоимости расторгаются чаще всего")
            price_risk = pd.read_sql_query("""
                SELECT
                    CASE WHEN price < 1000000   THEN 'до 1 млн'
                         WHEN price < 5000000   THEN '1–5 млн'
                         WHEN price < 10000000  THEN '5–10 млн'
                         WHEN price < 50000000  THEN '10–50 млн'
                         WHEN price < 100000000 THEN '50–100 млн'
                         WHEN price < 500000000 THEN '100–500 млн'
                         ELSE 'свыше 500 млн' END AS price_range,
                    CASE WHEN price < 1000000   THEN 1
                         WHEN price < 5000000   THEN 2
                         WHEN price < 10000000  THEN 3
                         WHEN price < 50000000  THEN 4
                         WHEN price < 100000000 THEN 5
                         WHEN price < 500000000 THEN 6
                         ELSE 7 END AS sort_order,
                    COUNT(*) AS total, SUM(is_terminated) AS terminated,
                    ROUND(AVG(is_terminated) * 100, 1) AS risk_pct
                FROM contracts WHERE stage IN ('ET', 'EC') AND price > 0
                GROUP BY price_range, sort_order ORDER BY sort_order
            """, conn)

            col1, col2 = st.columns([2, 1])
            with col1:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=price_risk['price_range'], y=price_risk['risk_pct'],
                    marker_color=price_risk['risk_pct'],
                    marker_colorscale='RdYlGn_r',
                    text=price_risk['risk_pct'].apply(lambda x: f'{x:.1f}%'),
                    textposition='outside'
                ))
                fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0),
                    yaxis_title='Доля расторжений (%)',
                    xaxis_title='Ценовой диапазон', showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                d = price_risk[['price_range', 'total', 'terminated', 'risk_pct']].copy()
                d.columns = ['Диапазон', 'Контрактов', 'Расторгнуто', 'Риск (%)']
                st.dataframe(d, use_container_width=True, hide_index=True)

        # влияние штрафов
        with st.expander("Влияние штрафов на риск расторжения"):
            st.caption("штрафы — один из сильнейших предикторов расторжения")
            penalty_risk = pd.read_sql_query("""
                SELECT
                    CASE WHEN pf.penalty_count = 0  THEN 'Без штрафов'
                         WHEN pf.penalty_count = 1  THEN '1 штраф'
                         WHEN pf.penalty_count <= 3 THEN '2–3 штрафа'
                         WHEN pf.penalty_count <= 5 THEN '4–5 штрафов'
                         ELSE 'более 5 штрафов' END AS penalty_group,
                    CASE WHEN pf.penalty_count = 0  THEN 1
                         WHEN pf.penalty_count = 1  THEN 2
                         WHEN pf.penalty_count <= 3 THEN 3
                         WHEN pf.penalty_count <= 5 THEN 4
                         ELSE 5 END AS sort_order,
                    COUNT(*) AS total, SUM(c.is_terminated) AS terminated,
                    ROUND(AVG(c.is_terminated) * 100, 1) AS risk_pct,
                    ROUND(AVG(pf.penalty_total) / 1000, 1) AS avg_penalty_k
                FROM (
                    SELECT reg_num,
                        COUNT(CASE WHEN has_penalty=1 THEN 1 END) AS penalty_count,
                        SUM(COALESCE(penalty_amount, 0)) AS penalty_total
                    FROM procedures_flat GROUP BY reg_num
                ) pf
                JOIN contracts c ON c.reg_num = pf.reg_num
                WHERE c.stage IN ('ET', 'EC')
                GROUP BY penalty_group, sort_order ORDER BY sort_order
            """, conn)

            col1, col2 = st.columns([2, 1])
            with col1:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=penalty_risk['penalty_group'], y=penalty_risk['risk_pct'],
                    marker_color=penalty_risk['risk_pct'],
                    marker_colorscale='RdYlGn_r',
                    text=penalty_risk['risk_pct'].apply(lambda x: f'{x:.1f}%'),
                    textposition='outside'
                ))
                fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0),
                    yaxis_title='Доля расторжений (%)', showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                d = penalty_risk[['penalty_group','total','terminated','risk_pct','avg_penalty_k']].copy()
                d.columns = ['Группа','Контрактов','Расторгнуто','Риск (%)','Ср. штраф (тыс.)']
                st.dataframe(d, use_container_width=True, hide_index=True)

        # длительность vs риск
        with st.expander("Длительность контракта и риск расторжения"):
            st.caption("обоснование необходимости промежуточного контроля")
            duration_risk = pd.read_sql_query("""
                SELECT
                    CASE WHEN duration_days < 90   THEN 'до 3 мес.'
                         WHEN duration_days < 180  THEN '3–6 мес.'
                         WHEN duration_days < 365  THEN '6–12 мес.'
                         WHEN duration_days < 730  THEN '1–2 года'
                         ELSE 'более 2 лет' END AS duration_group,
                    CASE WHEN duration_days < 90   THEN 1
                         WHEN duration_days < 180  THEN 2
                         WHEN duration_days < 365  THEN 3
                         WHEN duration_days < 730  THEN 4
                         ELSE 5 END AS sort_order,
                    COUNT(*) AS total, SUM(is_terminated) AS terminated,
                    ROUND(AVG(is_terminated) * 100, 1) AS risk_pct,
                    ROUND(AVG(price) / 1000000, 1) AS avg_price_mln
                FROM (
                    SELECT is_terminated, price,
                        julianday(COALESCE(exe_end, published_at)) - julianday(exe_start) AS duration_days
                    FROM contracts
                    WHERE stage IN ('ET', 'EC') AND exe_start IS NOT NULL
                ) WHERE duration_days > 0
                GROUP BY duration_group, sort_order ORDER BY sort_order
            """, conn)

            col1, col2 = st.columns([2, 1])
            with col1:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=duration_risk['duration_group'], y=duration_risk['risk_pct'],
                    marker_color=duration_risk['risk_pct'],
                    marker_colorscale='RdYlGn_r',
                    text=duration_risk['risk_pct'].apply(lambda x: f'{x:.1f}%'),
                    textposition='outside'
                ))
                fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0),
                    yaxis_title='Доля расторжений (%)', showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                d = duration_risk[['duration_group','total','terminated','risk_pct','avg_price_mln']].copy()
                d.columns = ['Длительность','Контрактов','Расторгнуто','Риск (%)','Ср. цена (млн)']
                st.dataframe(d, use_container_width=True, hide_index=True)

        # рейтинг регионов + детализация по выбранному региону
        with st.expander("Анализ рисков по регионам", expanded=True):
            region_stats = pd.read_sql_query(f"""
                SELECT region, COUNT(*) AS count,
                    AVG(is_terminated) * 100 AS risk,
                    SUM(is_terminated) AS terminated
                FROM contracts WHERE stage IN ('ET', 'EC')
                GROUP BY region HAVING COUNT(*) >= 100
                ORDER BY risk DESC LIMIT 20
            """, conn)

            region_stats['region_name'] = region_stats['region'].map(
                lambda x: REGION_NAMES.get(int(x), f'Регион {x}')
            )

            # топ-20 горизонтальный bar
            fig_r = px.bar(
                region_stats.sort_values('risk'),
                x='risk', y='region_name', orientation='h',
                text='risk', color='risk',
                color_continuous_scale='RdYlGn_r',
                labels={'risk': 'Доля расторжений (%)', 'region_name': 'Регион'}
            )
            fig_r.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig_r.update_layout(height=540, coloraxis_showscale=False,
                                margin=dict(l=0, r=60, t=10, b=0))
            st.plotly_chart(fig_r, use_container_width=True)

            st.markdown("---")
            st.subheader("Детализация по региону")
            st.caption(
                "выберите регион из топ-20 для просмотра подробной статистики: "
                "динамика по годам, типы строительства, причины расторжений, заказчики"
            )

            # selectbox с регионами отсортированными по риску
            region_options = dict(zip(
                region_stats['region_name'],
                region_stats['region']
            ))
            selected_name = st.selectbox(
                "Регион для детализации:",
                options=list(region_options.keys()),
                index=0
            )
            selected_code = region_options[selected_name]

            render_region_detail(conn, selected_code, selected_name, russia_risk)

        # причины расторжений
        with st.expander("Анализ причин расторжения контрактов"):
            reasons_df = pd.read_sql_query("""
                SELECT termination_reason_info, COUNT(*) AS count
                FROM procedures_flat
                WHERE termination_reason_info IS NOT NULL
                  AND termination_reason_info != ''
                  AND LENGTH(termination_reason_info) > 3
                GROUP BY termination_reason_info ORDER BY count DESC
            """, conn)

            if len(reasons_df) > 0:
                total = reasons_df['count'].sum()
                reasons_df['group'] = reasons_df['termination_reason_info'].apply(group_reason)
                grouped = (
                    reasons_df.groupby('group')['count'].sum()
                    .reset_index().rename(columns={'count': 'Количество'})
                )
                grouped['Доля (%)'] = (grouped['Количество'] / total * 100).round(2)
                grouped = grouped.sort_values('Количество', ascending=False)
                grouped.rename(columns={'group': 'Группа причин'}, inplace=True)

                col1, col2 = st.columns([1, 1])
                with col1:
                    st.dataframe(grouped, use_container_width=True, hide_index=True)
                with col2:
                    fig_pie = px.pie(
                        grouped, values='Количество', names='Группа причин',
                        color_discrete_sequence=px.colors.qualitative.Set2, hole=0.35
                    )
                    fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                    fig_pie.update_layout(height=360, showlegend=False)
                    st.plotly_chart(fig_pie, use_container_width=True)

                st.subheader("Детализация по группе причин")
                selected_group = st.selectbox("Группа:", grouped['Группа причин'].tolist())

                # детализация по официальным причинам
                agreement_detail = pd.read_sql_query("""
                    SELECT COALESCE(pf.termination_reason_name, 'Причина не указана') AS reason_name,
                        COUNT(*) AS count
                    FROM procedures_flat pf
                    WHERE pf.has_termination = 1
                      AND pf.termination_reason_info IS NOT NULL
                    GROUP BY reason_name ORDER BY count DESC LIMIT 20
                """, conn)

                if len(agreement_detail) > 0:
                    total_ag = agreement_detail['count'].sum()
                    agreement_detail['Доля (%)'] = (
                        agreement_detail['count'] / total_ag * 100
                    ).round(1)
                    agreement_detail.columns = ['Официальная причина', 'Количество', 'Доля (%)']
                    col_ag1, col_ag2 = st.columns([1, 1])
                    with col_ag1:
                        st.dataframe(agreement_detail, use_container_width=True, hide_index=True)
                    with col_ag2:
                        fig_ag = px.bar(
                            agreement_detail.head(10).sort_values('Количество'),
                            x='Количество', y='Официальная причина',
                            orientation='h', text='Количество',
                            color_discrete_sequence=['#003087']
                        )
                        fig_ag.update_layout(height=360, margin=dict(l=0, r=40, t=10, b=0),
                                             yaxis_title=None)
                        st.plotly_chart(fig_ag, use_container_width=True)

        # топ-10 заказчиков
        with st.expander("Топ-10 заказчиков по числу расторжений"):
            top_customers = pd.read_sql_query(f"""
                SELECT customer_inn, COUNT(*) AS total,
                    SUM(is_terminated) AS terminated,
                    ROUND(AVG(is_terminated) * 100, 1) AS risk_pct,
                    ROUND(SUM(price) / 1000000, 1) AS total_mln
                FROM contracts WHERE stage IN ('ET', 'EC') {year_filter}
                GROUP BY customer_inn
                ORDER BY terminated DESC LIMIT 10
            """, conn)
            top_customers.columns = [
                'ИНН заказчика', 'Всего контрактов',
                'Расторгнуто', 'Доля (%)', 'Объём (млн руб.)'
            ]
            st.dataframe(top_customers, use_container_width=True, hide_index=True)

        # топ-10 поставщиков по числу расторжений
        with st.expander("Топ-10 поставщиков по числу расторжений"):
            top_suppliers = pd.read_sql_query(f"""
                SELECT cs.supplier_inn,
                    COUNT(DISTINCT cs.reg_num)               AS total,
                    SUM(c.is_terminated)                     AS terminated,
                    ROUND(AVG(c.is_terminated) * 100, 1)     AS risk_pct,
                    ROUND(SUM(c.price) / 1000000, 1)         AS total_mln
                FROM contract_suppliers cs
                JOIN contracts c ON cs.reg_num = c.reg_num
                WHERE c.stage IN ('ET', 'EC') {year_filter}
                GROUP BY cs.supplier_inn
                ORDER BY terminated DESC LIMIT 10
            """, conn)
            if not top_suppliers.empty:
                top_suppliers.columns = [
                    'ИНН поставщика', 'Всего контрактов',
                    'Расторгнуто', 'Доля (%)', 'Объём (млн руб.)'
                ]
                st.dataframe(top_suppliers, use_container_width=True, hide_index=True)
            else:
                st.info("нет данных за выбранный период")

        conn.close()

    except Exception as e:
        st.error(f"Ошибка при загрузке данных: {e}")
        import traceback
        st.code(traceback.format_exc())