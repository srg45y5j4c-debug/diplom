# pages/_04_supplier_analysis.py
import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import requests
import os
from config import DB_PATH

GOSPLAN_BASE    = os.getenv("GOSPLAN_BASE_URL",       "https://v2.gosplan.info").rstrip("/")
GOSPLAN_PREFIX  = os.getenv("GOSPLAN_API_PREFIX",     "/fz44").rstrip("/")
GOSPLAN_API_KEY = os.getenv("GOSPLAN_API_KEY",        "")
GOSPLAN_HDR     = os.getenv("GOSPLAN_API_KEY_HEADER", "X-API-KEY")


def _api_session():
    s = requests.Session()
    s.trust_env = False
    s.headers.update({"Accept": "application/json", "User-Agent": "riskanalyzer/1.0"})
    if GOSPLAN_API_KEY:
        s.headers[GOSPLAN_HDR] = GOSPLAN_API_KEY
    return s


def fetch_supplier_from_api(inn: str) -> pd.DataFrame:
    """загружает все контракты поставщика из api госплан по ИНН"""
    session = _api_session()
    all_items = []

    # один запрос без фильтра по classifier и stage — api сам вернёт всё по поставщику
    # если не вернёт — пробуем постадийно
    try:
        # published_forpast=3y — максимальный период, иначе апи по умолчанию берёт 1 месяц
        r = session.get(
            f"{GOSPLAN_BASE}{GOSPLAN_PREFIX}/contracts",
            params={"supplier": inn, "limit": 100, "skip": 0,
                    "sort": "updated_at_desc", "published_forpast": "3y"},
            timeout=20
        )
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("items", [])
            all_items.extend(items)

            # если вернулось 100 — возможно есть ещё страницы
            skip = 100
            while len(items) == 100:
                r2 = session.get(
                    f"{GOSPLAN_BASE}{GOSPLAN_PREFIX}/contracts",
                    params={"supplier": inn, "limit": 100, "skip": skip,
                            "sort": "updated_at_desc", "published_forpast": "3y"},
                    timeout=20
                )
                if r2.status_code != 200:
                    break
                items = r2.json()
                if isinstance(items, dict):
                    items = items.get("items", [])
                if not items:
                    break
                all_items.extend(items)
                skip += 100
    except Exception:
        pass

    # если без фильтра ничего не вернулось — пробуем постадийно
    if not all_items:
        for stage in ["ET", "EC", "E", "IN"]:
            for classifier in ["41", "42", "43"]:
                skip = 0
                while True:
                    try:
                        r = session.get(
                            f"{GOSPLAN_BASE}{GOSPLAN_PREFIX}/contracts",
                            params={"supplier": inn, "classifier": classifier,
                                    "stage": stage, "limit": 100, "skip": skip,
                                    "sort": "updated_at_desc", "published_forpast": "3y"},
                            timeout=20
                        )
                        if r.status_code != 200:
                            break
                        data = r.json()
                        items = data if isinstance(data, list) else data.get("items", [])
                        if not items:
                            break
                        all_items.extend(items)
                        if len(items) < 100:
                            break
                        skip += 100
                    except Exception:
                        break

    if not all_items:
        return pd.DataFrame()

    rows = []
    for c in all_items:
        rows.append({
            "reg_num":       c.get("reg_num", ""),
            "exe_start":     (c.get("exe_start") or "")[:10],
            "price_mln":     round((c.get("price") or 0) / 1_000_000, 2),
            "region":        c.get("region"),
            "is_terminated": 1 if c.get("stage") == "ET" else 0,
            "status": {
                "ET": "Расторгнут", "EC": "Завершён",
                "E": "В исполнении", "IN": "Аннулировано"
            }.get(c.get("stage"), c.get("stage", "")),
        })

    # убираем дубликаты если один контракт пришёл из нескольких запросов
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["reg_num"])
    return df


def fetch_procedures_for_supplier(reg_nums: list) -> pd.DataFrame:
    """загружает процедуры исполнения для списка контрактов из api госплан"""
    session = _api_session()
    all_rows = []

    for reg_num in reg_nums[:20]:  # ограничиваем 20 контрактами чтобы не перегружать апи
        try:
            r = session.get(
                f"{GOSPLAN_BASE}{GOSPLAN_PREFIX}/contracts/{reg_num}/procedures",
                timeout=15
            )
            if r.status_code != 200:
                continue
            data = r.json()
            items = data if isinstance(data, list) else data.get("items", [])
            for item in items:
                src  = item.get("source") or {}
                pen  = (src.get("penalties") or {}).get("penaltyAccrual")
                term = src.get("termination")

                # перевод типов процедур
                doc_type_map = {
                    "contractProcedure":         "Исполнение контракта",
                    "contractTermination":        "Расторжение контракта",
                    "contractPenalty":            "Штрафная санкция",
                    "contractAmendment":          "Изменение контракта",
                    "contractCompletion":         "Завершение контракта",
                    "contractSuspension":         "Приостановление",
                    "contractExecutionProcedure": "Процедура исполнения",
                }
                doc_type_raw = item.get("doc_type", "")
                doc_type     = doc_type_map.get(doc_type_raw, doc_type_raw)

                # сумма оплаты из executions
                exec_data = (src.get("executions") or {}).get("execution") or {}
                paid_rur  = exec_data.get("paidRUR") or exec_data.get("paid") or ""
                try:
                    paid_str = f"{float(paid_rur):,.0f} руб." if paid_rur else "—"
                except (ValueError, TypeError):
                    paid_str = "—"

                # документ оплаты
                pay_doc  = exec_data.get("payDoc") or {}
                doc_name = pay_doc.get("documentName") or "—"
                doc_date = pay_doc.get("documentDate") or "—"

                # инициатор расторжения
                initiator = "—"
                if isinstance(term, dict):
                    party = term.get("initiator") or term.get("party") or ""
                    if "заказч" in str(party).lower() or "customer" in str(party).lower():
                        initiator = "Заказчик"
                    elif "поставщ" in str(party).lower() or "supplier" in str(party).lower():
                        initiator = "Поставщик"
                    elif party:
                        initiator = str(party)

                all_rows.append({
                    "Дата":           (item.get("published_at") or "")[:10],
                    "Тип":            doc_type,
                    "Документ":       doc_name,
                    "Дата документа": doc_date,
                    "Сумма оплаты":   paid_str,
                    "Штраф":          "Да" if isinstance(pen, dict) else "—",
                    "Сумма штрафа":   f"{float(pen.get('accrualAmount', 0)):,.0f} руб."
                                      if isinstance(pen, dict) else "—",
                    "Расторжение":    "Да" if isinstance(term, dict) else "—",
                    "Инициатор":      initiator,
                    "Причина":        ((term or {}).get("reasonInfo") or
                                       (term or {}).get("reason", {}).get("name") or "—")
                                      if isinstance(term, dict) else "—",
                })
        except Exception:
            continue

    return pd.DataFrame(all_rows)


def get_risk_label(pct: float) -> str:
    if pct < 10:
        return "Надёжный"
    elif pct < 25:
        return "Средний риск"
    return "Высокий риск"


@st.cache_data(ttl=300)
def load_supplier_list(min_contracts: int) -> pd.DataFrame:
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("""
            SELECT cs.supplier_inn AS inn,
                COUNT(DISTINCT cs.reg_num)           AS total_contracts,
                SUM(c.is_terminated)                 AS terminated,
                ROUND(AVG(c.is_terminated)*100, 1)   AS risk_pct,
                ROUND(AVG(c.price)/1000000, 2)       AS avg_price_mln,
                COUNT(DISTINCT c.region)             AS regions_count,
                ROUND(SUM(c.price)/1000000, 1)       AS total_mln
            FROM contract_suppliers cs
            JOIN contracts c ON cs.reg_num = c.reg_num
            WHERE c.stage IN ("ET", "EC")
            GROUP BY cs.supplier_inn
            HAVING COUNT(DISTINCT cs.reg_num) >= ?
            ORDER BY terminated DESC
        """, conn, params=[min_contracts])
        conn.close()
        return df
    except Exception as e:
        st.error(f"ошибка загрузки: {e}")
        return pd.DataFrame()


def load_supplier_profile(inn: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        summary = pd.read_sql_query("""
            SELECT cs.supplier_inn,
                COUNT(DISTINCT cs.reg_num)           AS total_contracts,
                SUM(c.is_terminated)                 AS terminated,
                ROUND(AVG(c.is_terminated)*100, 1)   AS risk_pct,
                ROUND(AVG(c.price)/1000000, 2)       AS avg_price_mln,
                ROUND(SUM(c.price)/1000000, 1)       AS total_mln,
                COUNT(DISTINCT c.region)             AS regions_count
            FROM contract_suppliers cs
            JOIN contracts c ON cs.reg_num = c.reg_num
            WHERE cs.supplier_inn = ? AND c.stage IN ("ET", "EC")
            GROUP BY cs.supplier_inn
        """, conn, params=[inn])

        by_year = pd.read_sql_query("""
            SELECT SUBSTR(c.exe_start, 1, 4) AS year,
                COUNT(*) AS contracts, SUM(c.is_terminated) AS terminated,
                ROUND(AVG(c.is_terminated)*100, 1) AS risk_pct
            FROM contract_suppliers cs
            JOIN contracts c ON cs.reg_num = c.reg_num
            WHERE cs.supplier_inn = ? AND c.stage IN ("ET", "EC")
              AND c.exe_start IS NOT NULL
            GROUP BY year ORDER BY year
        """, conn, params=[inn])

        recent = pd.read_sql_query("""
            SELECT c.reg_num, c.exe_start,
                ROUND(c.price/1000000, 2) AS price_mln, c.region,
                CASE c.is_terminated WHEN 1 THEN "Расторгнут" ELSE "Завершён" END AS status,
                c.is_terminated
            FROM contract_suppliers cs
            JOIN contracts c ON cs.reg_num = c.reg_num
            WHERE cs.supplier_inn = ? AND c.stage IN ("ET", "EC")
            ORDER BY c.exe_start DESC LIMIT 10
        """, conn, params=[inn])

        penalties = pd.read_sql_query("""
            SELECT COUNT(pf.rowid) AS penalty_procedures,
                ROUND(SUM(pf.penalty_amount)/1000, 1) AS total_penalty_k
            FROM contract_suppliers cs
            JOIN contracts c ON cs.reg_num = c.reg_num
            JOIN procedures_flat pf ON pf.reg_num = c.reg_num
            WHERE cs.supplier_inn = ? AND c.stage IN ("ET", "EC")
              AND pf.penalty_amount > 0
        """, conn, params=[inn])

        conn.close()
        return (summary.iloc[0] if len(summary) > 0 else None,
                by_year, recent, penalties.iloc[0])
    except Exception as e:
        st.error(f"ошибка профиля: {e}")
        return None, None, None, None


def render_profile(inn, summary, by_year, recent, penalties, source="db"):
    risk_label = get_risk_label(float(summary["risk_pct"]))
    risk_css = {"Надёжный": "risk-low", "Средний риск": "risk-medium",
                "Высокий риск": "risk-high"}[risk_label]

    st.subheader(f"Поставщик ИНН {inn}")
    st.markdown(f"""
    <div class="{risk_css}" style="text-align:left; font-size:1rem;">
        Статус: <b>{risk_label}</b> — доля расторжений {summary["risk_pct"]:.1f}%
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Всего контрактов", f"{int(summary['total_contracts'])}")
    c2.metric("Расторгнуто",      f"{int(summary['terminated'])}")
    c3.metric("Средняя цена",     f"{summary['avg_price_mln']:.1f} млн руб.")
    c4.metric("Регионов работы",  f"{int(summary['regions_count'])}")

    if penalties is not None:
        pen_cnt = int(penalties.get("penalty_procedures", 0) or 0)
        if pen_cnt > 0:
            st.metric("Штрафных процедур", f"{pen_cnt}")

    if by_year is not None and len(by_year) > 0:
        st.subheader("Динамика по годам")
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_trace(go.Bar(x=by_year["year"], y=by_year["contracts"],
                             name="Всего", marker_color="#003087"))
        fig.add_trace(go.Bar(x=by_year["year"], y=by_year["terminated"],
                             name="Расторгнуто", marker_color="#991b1b"))
        fig.update_layout(barmode="group", height=300,
                          margin=dict(l=0, r=0, t=10, b=0),
                          legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig, use_container_width=True)

    if recent is not None and len(recent) > 0:
        st.subheader("Последние 10 контрактов")
        cols_show = [c for c in recent.columns if c != "is_terminated"]
        disp = recent[cols_show].copy()
        if list(disp.columns) == ["reg_num", "exe_start", "price_mln", "region", "status"]:
            disp.columns = ["Номер контракта", "Дата начала",
                            "Цена (млн руб.)", "Регион", "Статус"]

        def color_row(row):
            s = row.get("Статус", row.get("status", ""))
            if s == "Расторгнут":
                return ["background-color: #fee2e2"] * len(row)
            return [""] * len(row)

        st.dataframe(disp.style.apply(color_row, axis=1),
                     use_container_width=True, hide_index=True)

    # процедуры исполнения — загружаем из api
    reg_col = "reg_num" if "reg_num" in recent.columns else "Номер контракта"
    reg_nums = recent[reg_col].dropna().tolist() if recent is not None else []

    if reg_nums:
        with st.expander("Процедуры исполнения контрактов", expanded=False):
            st.caption(
                "штрафы, отчёты об исполнении и процедуры расторжения "
                "по контрактам поставщика (данные из API ГосПлан)"
            )

            # выпадающий список для выбора конкретного контракта
            selected_reg = st.selectbox(
                "Выберите контракт:",
                options=reg_nums,
                format_func=lambda x: x
            )

            with st.spinner("загрузка процедур..."):
                proc_df = fetch_procedures_for_supplier([selected_reg])

            if proc_df.empty:
                st.info("процедуры исполнения по данному контракту не найдены.")
            else:
                has_penalty = (proc_df["Штраф"] == "Да").sum()
                has_term    = (proc_df["Расторжение"] == "Да").sum()
                total_proc  = len(proc_df)

                p1, p2, p3 = st.columns(3)
                p1.metric("Всего процедур", f"{total_proc}")
                p2.metric("Со штрафами",    f"{has_penalty}")
                p3.metric("С расторжением", f"{has_term}")

                def color_proc(row):
                    if row.get("Расторжение") == "Да":
                        return ["background-color: #fee2e2"] * len(row)
                    if row.get("Штраф") == "Да":
                        return ["background-color: #fef3c7"] * len(row)
                    return [""] * len(row)

                # убираем колонку "Контракт" — она и так выбрана выше
                display_proc = proc_df.drop(columns=["Контракт"], errors="ignore")
                st.dataframe(
                    display_proc.style.apply(color_proc, axis=1),
                    use_container_width=True, hide_index=True
                )



def _render_profile_tab():
    """вкладка поиска поставщика по ИНН — используется в обоих режимах"""
    st.markdown(
        "введите ИНН поставщика для получения полной истории контрактов из API ГосПлан."
    )
    inn_input = st.text_input("ИНН поставщика", max_chars=12, placeholder="10 или 12 цифр")

    if st.button("Загрузить профиль", type="primary"):
        if not inn_input.strip() or not inn_input.strip().isdigit():
            st.error("введите корректный ИНН (только цифры).")
        else:
            inn = inn_input.strip()
            with st.spinner("загружаем данные из API ГосПлан..."):
                api_df = fetch_supplier_from_api(inn)

            if api_df.empty:
                st.warning(
                    "поставщик не найден в API ГосПлан. "
                    "возможно, у поставщика нет строительных контрактов в ЕИС."
                )
                st.session_state.pop("supplier_profile", None)
            else:
                api_df["year"] = api_df["exe_start"].str[:4]
                by_year_api = (api_df.groupby("year")
                               .agg(contracts=("reg_num", "count"),
                                    terminated=("is_terminated", "sum"))
                               .reset_index())
                by_year_api["risk_pct"] = (
                    by_year_api["terminated"] / by_year_api["contracts"] * 100
                ).round(1)
                st.session_state["supplier_profile"] = {
                    "inn": inn,
                    "summary": {
                        "risk_pct":        round(api_df["is_terminated"].mean() * 100, 1),
                        "total_contracts": len(api_df),
                        "terminated":      int(api_df["is_terminated"].sum()),
                        "avg_price_mln":   round(api_df["price_mln"].mean(), 2),
                        "total_mln":       round(api_df["price_mln"].sum(), 1),
                        "regions_count":   api_df["region"].nunique(),
                    },
                    "by_year": by_year_api,
                    "recent":  api_df[["reg_num", "exe_start", "price_mln",
                                       "region", "status"]].head(10),
                }

    if "supplier_profile" in st.session_state:
        p = st.session_state["supplier_profile"]
        render_profile(p["inn"], p["summary"], p["by_year"], p["recent"], None)


def render_supplier_analysis(user_mode=False):
    st.header("Анализ надёжности поставщиков")

    if user_mode:
        st.markdown(
            "проверьте надёжность поставщика по ИНН — "
            "система покажет историю контрактов из API ГосПлан."
        )
        # в режиме специалиста — только профиль по ИНН, без рейтинга
        _render_profile_tab()
        return

    st.markdown(
        "данные основаны на реальной истории исполнения государственных контрактов. "
        "для поставщиков не найденных в базе — история загружается из API ГосПлан."
    )

    tab1, tab2 = st.tabs(["Рейтинг поставщиков", "Профиль поставщика по ИНН"])

    with tab1:
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            min_contracts = st.slider("Минимум контрактов", 1, 50, 10)
        with col_f2:
            risk_filter = st.multiselect(
                "Статус риска",
                ["Надёжный", "Средний риск", "Высокий риск"],
                default=["Надёжный", "Средний риск", "Высокий риск"]
            )
        with col_f3:
            inn_search = st.text_input("Поиск по ИНН", placeholder="часть ИНН")

        with st.spinner("загрузка..."):
            df = load_supplier_list(min_contracts)

        if df.empty:
            st.warning("данные не найдены.")
            return

        df["status"] = df["risk_pct"].apply(get_risk_label)
        filtered = df[df["status"].isin(risk_filter)]
        if inn_search:
            filtered = filtered[filtered["inn"].str.contains(inn_search, na=False)]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Поставщиков",  f"{len(filtered):,}")
        m2.metric("Надёжных",     f"{(filtered['status']=='Надёжный').sum():,}")
        m3.metric("Средний риск", f"{(filtered['status']=='Средний риск').sum():,}")
        m4.metric("Высокий риск", f"{(filtered['status']=='Высокий риск').sum():,}")

        display = filtered.copy()
        display.columns = ["ИНН", "Контрактов", "Расторгнуто", "Доля расторжений (%)",
                           "Ср. цена (млн руб.)", "Регионов",
                           "Общая сумма (млн руб.)", "Статус"]

        def color_status(val):
            if val == "Высокий риск":
                return "background-color: #fee2e2; color: #991b1b;"
            elif val == "Средний риск":
                return "background-color: #fef3c7; color: #92400e;"
            return "background-color: #dcfce7; color: #166534;"

        st.dataframe(
            display.sort_values("Доля расторжений (%)", ascending=False)
                   .style.applymap(color_status, subset=["Статус"]),
            use_container_width=True, hide_index=True
        )

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Распределение по уровню риска")
            sc = filtered["status"].value_counts().reset_index()
            sc.columns = ["Статус", "Количество"]
            fig = px.pie(sc, values="Количество", names="Статус",
                         color="Статус",
                         color_discrete_map={"Надёжный": "#dcfce7",
                                             "Средний риск": "#fef3c7",
                                             "Высокий риск": "#fee2e2"},
                         hole=0.4)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(height=340, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            st.subheader("Опыт vs доля расторжений")
            fig2 = px.scatter(
                filtered, x="total_contracts", y="risk_pct",
                color="status", size="total_contracts",
                hover_data=["inn", "terminated"],
                color_discrete_map={"Надёжный": "#166534",
                                    "Средний риск": "#92400e",
                                    "Высокий риск": "#991b1b"},
                labels={"total_contracts": "Количество контрактов",
                        "risk_pct": "Доля расторжений (%)", "status": "Статус"}
            )
            fig2.update_layout(height=340)
            st.plotly_chart(fig2, use_container_width=True)

    with tab2:
        _render_profile_tab()