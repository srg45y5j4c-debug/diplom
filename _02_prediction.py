# pages/_02_prediction.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
import requests
import os
from datetime import datetime
from config import DB_PATH, MODELS_DIR

# базовый url и префикс api госплан (те же константы что в etl-скриптах)
GOSPLAN_BASE = os.getenv("GOSPLAN_BASE_URL", "https://v2.gosplan.info").rstrip("/")
GOSPLAN_PREFIX = os.getenv("GOSPLAN_API_PREFIX", "/fz44").rstrip("/")
GOSPLAN_API_KEY = os.getenv("GOSPLAN_API_KEY", "")
GOSPLAN_API_KEY_HEADER = os.getenv("GOSPLAN_API_KEY_HEADER", "X-API-KEY")

# порядок признаков должен совпадать с порядком при обучении
# порядок признаков строго совпадает с feature_columns.txt который создаётся при обучении.
# has_termination_doc и supplier_terminated_share — удаляются ml-скриптами перед обучением,
# поэтому здесь их нет. после переобучения моделей порядок обновится автоматически.
FEATURE_ORDER = [
    'log_price', 'region',
    'is_buildings', 'is_infrastructure', 'is_specialized', 'is_multi_supplier',
    'contract_duration_days',
    'has_penalty', 'penalty_count', 'log_penalty_total', 'procedures_count',
    'penalty_per_procedure', 'penalty_severity',
    'supplier_total_contracts', 'supplier_avg_price',
    'supplier_regions_count', 'supplier_avg_suppliers',
]

# читаемые названия признаков
FEATURE_LABELS = {
    'log_price':               'Цена контракта',
    'has_penalty':             'Наличие штрафов',
    'contract_duration_days':  'Длительность контракта',
    'penalty_count':           'Количество штрафов',
    'log_penalty_total':       'Общая сумма штрафов',
    'procedures_count':        'Количество процедур',
    'penalty_per_procedure':   'Штрафы на процедуру',
    'penalty_severity':        'Тяжесть штрафов',
    'supplier_total_contracts':'Опыт поставщика (контракты)',
    'supplier_avg_price':      'Средняя цена у поставщика',
    'supplier_regions_count':  'Регионов у поставщика',
    'supplier_avg_suppliers':  'Среднее число соисполнителей',
    'penalty_x_experience': 'Штраф × опыт поставщика',
    'price_x_duration':     'Цена × длительность контракта',
    'penalty_x_price':      'Тяжесть штрафа × цена',
    'region':                  'Регион',
    'is_buildings':            'Строительство зданий',
    'is_infrastructure':       'Инфраструктурные работы',
    'is_specialized':          'Специализированные работы',
    'is_multi_supplier':       'Несколько поставщиков',
}

def get_feature_order():
    """возвращает порядок признаков ровно как при обучении модели"""
    features_path = os.path.join(MODELS_DIR, "..", "feature_columns.txt")
    features_path = os.path.normpath(features_path)

    if os.path.exists(features_path):
        with open(features_path, "r", encoding="utf-8") as f:
            order = [line.strip() for line in f if line.strip()]

        order = [
            c for c in order
            if c not in ("has_termination_doc", "supplier_terminated_share")
        ]
        return order

    return FEATURE_ORDER

def _gosplan_session():
    """создаёт http-сессию для запросов к api госплан с нужными заголовками"""
    s = requests.Session()
    s.trust_env = False
    headers = {
        "Accept": "application/json",
        "User-Agent": "riskanalyzer-app/1.0",
    }
    if GOSPLAN_API_KEY:
        headers[GOSPLAN_API_KEY_HEADER] = GOSPLAN_API_KEY
    s.headers.update(headers)
    return s


def _safe_get(d, *path):
    """безопасный доступ к вложенным ключам словаря"""
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def fetch_contract_from_api(reg_num: str):
    """
    получает данные контракта по регистрационному номеру через
    GET /fz44/contracts/{reg_num}
    возвращает словарь с полями контракта или None при ошибке
    """
    url = f"{GOSPLAN_BASE}{GOSPLAN_PREFIX}/contracts/{reg_num}"
    try:
        s = _gosplan_session()
        r = s.get(url, timeout=15)
        if r.status_code == 404:
            return None, "Контракт не найден в API ГосПлан."
        if r.status_code == 422:
            return None, "Некорректный формат регистрационного номера."
        if r.status_code != 200:
            return None, f"API вернул статус {r.status_code}."
        data = r.json()
        return data, None
    except requests.exceptions.Timeout:
        return None, "Превышено время ожидания ответа от API ГосПлан (15 сек)."
    except requests.exceptions.ConnectionError:
        return None, "Нет соединения с API ГосПлан. Проверьте интернет-подключение."
    except Exception as e:
        return None, f"Ошибка при обращении к API: {e}"


def fetch_procedures_from_api(reg_num: str):
    """
    получает процедуры контракта через
    GET /fz44/contracts/{reg_num}/procedures
    возвращает список процедур или пустой список при ошибке
    """
    url = f"{GOSPLAN_BASE}{GOSPLAN_PREFIX}/contracts/{reg_num}/procedures"
    try:
        s = _gosplan_session()
        r = s.get(url, timeout=15)
        if r.status_code != 200:
            return [], f"API процедур вернул статус {r.status_code}."
        data = r.json()
        # api может вернуть список напрямую или обёрнутый в items/data
        if isinstance(data, list):
            return data, None
        for key in ("items", "data", "results"):
            if isinstance(data.get(key), list):
                return data[key], None
        return [], None
    except Exception as e:
        return [], f"Ошибка при загрузке процедур: {e}"


def parse_contract_fields(api_data: dict) -> dict:
    """
    извлекает нужные поля из ответа GET /contracts/{reg_num}.
    структура полей взята из etl-скрипта 02_download_contracts.py.
    """
    price = api_data.get("price") or 0
    region = api_data.get("region") or 77
    okpd2 = api_data.get("okpd2") or []
    if isinstance(okpd2, str):
        okpd2_str = okpd2
    else:
        okpd2_str = ",".join(str(x) for x in okpd2)

    exe_start = api_data.get("exe_start") or ""
    exe_end   = api_data.get("exe_end")   or api_data.get("published_at") or ""

    # длительность в днях
    duration = 180
    try:
        if exe_start and exe_end:
            d_start = datetime.fromisoformat(exe_start[:10])
            d_end   = datetime.fromisoformat(exe_end[:10])
            delta = (d_end - d_start).days
            if delta > 0:
                duration = delta
    except Exception:
        pass

    suppliers = api_data.get("suppliers") or []
    if isinstance(suppliers, str):
        suppliers = [s.strip() for s in suppliers.split(",") if s.strip()]
    suppliers_count = len(set(suppliers)) if suppliers else 1
    is_multi = 1 if suppliers_count > 1 else 0

    stage = api_data.get("stage", "")
    is_terminated = 1 if stage == "ET" else 0

    return {
        "price":          float(price),
        "region":         int(region),
        "okpd2_str":      okpd2_str,
        "duration_days":  duration,
        "suppliers":      suppliers,
        "suppliers_count": suppliers_count,
        "is_multi":       is_multi,
        "stage":          stage,
        "is_terminated":  is_terminated,
        "subject":        api_data.get("subject", ""),
        "customer_inn":   api_data.get("customer", ""),
        "exe_start":      exe_start,
        "exe_end":        exe_end,
        "updated_at":     api_data.get("updated_at", ""),
    }


def parse_procedures_fields(procedures: list) -> dict:
    """
    агрегирует процедуры из GET /contracts/{reg_num}/procedures.
    структура полей взята из etl-скрипта 03_download_procedures_for_contracts.py.
    """
    penalty_count = 0
    penalty_total = 0.0
    has_termination = 0
    termination_reason = ""
    procedures_count = len(procedures)
    penalty_details = []

    for item in procedures:
        src = item.get("source") or {}

        # штрафы
        pen = _safe_get(src, "penalties", "penaltyAccrual")
        if isinstance(pen, dict):
            penalty_count += 1
            amount = pen.get("accrualAmount") or 0
            try:
                penalty_total += float(amount)
            except Exception:
                pass
            party = pen.get("contractParty", "")
            reason = _safe_get(pen, "penaltyReason", "name") or ""
            penalty_details.append({
                "дата": item.get("published_at", "")[:10],
                "сумма (руб.)": float(amount),
                "сторона": party,
                "основание": reason,
            })

        # расторжение
        termination = src.get("termination")
        if isinstance(termination, dict):
            has_termination = 1
            termination_reason = (
                _safe_get(termination, "reasonInfo") or
                _safe_get(termination, "reason", "name") or ""
            )

    return {
        "procedures_count": procedures_count,
        "penalty_count":    penalty_count,
        "penalty_total":    penalty_total,
        "has_termination":  has_termination,
        "termination_reason": termination_reason,
        "penalty_details":  penalty_details,
    }


def load_supplier_history(inn: str) -> dict:
    """
    загружает историческую статистику поставщика из локальной бд
    для обогащения признаков модели
    """
    defaults = {
        "total_contracts": 10,
        "avg_price_mln":   5.0,
        "regions_count":   1,
        "avg_suppliers":   1.0,
    }
    try:
        conn = sqlite3.connect(DB_PATH)
        result = pd.read_sql_query("""
            SELECT
                COUNT(*)                   AS total_contracts,
                AVG(c.price) / 1000000     AS avg_price_mln,
                COUNT(DISTINCT c.region)   AS regions_count,
                AVG(c.suppliers_count)     AS avg_suppliers
            FROM contract_suppliers cs
            JOIN contracts c ON cs.reg_num = c.reg_num
            WHERE cs.supplier_inn = ?
              AND c.stage IN ('ET', 'EC')
        """, conn, params=[inn])
        conn.close()
        row = result.iloc[0]
        if pd.notna(row['total_contracts']) and int(row['total_contracts']) > 0:
            return {
                "total_contracts": int(row['total_contracts']),
                "avg_price_mln":   float(row['avg_price_mln'] or 5.0),
                "regions_count":   int(row['regions_count'] or 1),
                "avg_suppliers":   float(row['avg_suppliers'] or 1.0),
            }
    except Exception:
        pass
    return defaults


def predict_risk(pipeline, feature_dict: dict):
    """прогнозирование через pipeline.
    порядок признаков берётся из самой модели если возможно —
    это гарантирует совместимость независимо от того какие признаки
    использовались при обучении (с interaction features или без).
    """
    try:
        # пробуем получить список признаков из pipeline
        # sklearn pipeline хранит feature_names_in_ в финальном шаге (классификаторе)
        order = None

        # способ 1: из финального шага pipeline
        for step_name, step in reversed(list(pipeline.steps)):
            if hasattr(step, 'feature_names_in_'):
                order = list(step.feature_names_in_)
                break

        # способ 2: pipeline сам знает признаки после sklearn 1.0
        if order is None and hasattr(pipeline, 'feature_names_in_'):
            order = list(pipeline.feature_names_in_)

        # способ 3: fallback — читаем из feature_columns.txt
        if order is None:
            order = get_feature_order()
            order = [f for f in order if f not in (
                "has_termination_doc", "supplier_terminated_share",
                "penalty_x_experience", "price_x_duration", "penalty_x_price"
            )]

        X = pd.DataFrame(
            [[feature_dict.get(f, 0) for f in order]],
            columns=order
        )
        return float(pipeline.predict_proba(X)[0, 1])
    except Exception as e:
        st.error(f"Ошибка при прогнозировании: {e}")
        return None


def get_risk_level(p: float):
    """возвращает уровень, css-класс и описание по вероятности p"""
    if p < 0.2:
        return 'НИЗКИЙ',  'risk-low',    'Контракт имеет высокие шансы на успешное исполнение.'
    elif p < 0.5:
        return 'СРЕДНИЙ', 'risk-medium', 'Контракт требует повышенного внимания при исполнении.'
    else:
        return 'ВЫСОКИЙ', 'risk-high',   'Значительный риск расторжения. Необходимо усилить контроль.'


def get_model_factors(selected_key: str):
    """
    извлекает топ-10 факторов из сохранённого файла важности/коэффициентов.
    возвращает датафрейм 'Фактор' / 'Вес' или None если файл не найден.
    """
    file_map = {
        'logistic':      'logistic_coefficients.csv',
        'decision_tree': 'decision_tree_feature_importance.csv',
        'random_forest': 'random_forest_feature_importance.csv',
    }
    fname = file_map.get(selected_key)
    if not fname:
        return None
    path = os.path.join(MODELS_DIR, fname)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
        if selected_key == 'logistic' and 'Абс_коэф' in df.columns:
            weight_col = 'Абс_коэф'
        elif 'Важность (perm)' in df.columns:
            weight_col = 'Важность (perm)'
        elif 'Важность' in df.columns:
            weight_col = 'Важность'
        else:
            return None
        df = df[['Признак', weight_col]].copy()
        df.columns = ['Признак', 'Вес']
        df['Фактор'] = df['Признак'].map(lambda x: FEATURE_LABELS.get(x, x))
        df = df[df['Вес'] > 0].nlargest(10, 'Вес')
        total = df['Вес'].sum()
        df['Вес'] = (df['Вес'] / total * 100).round(1)
        return df[['Фактор', 'Вес']].reset_index(drop=True)
    except Exception:
        return None

def get_linear_contributions(pipeline, features: dict):
    """считает вклад признаков для логистической регрессии"""
    order = get_feature_order()

    X = pd.DataFrame(
        [[features.get(f, 0) for f in order]],
        columns=order
    )

    model = pipeline.named_steps.get("model") or pipeline.steps[-1][1]

    if not hasattr(model, "coef_"):
        return None

    coefs = model.coef_[0]

    df = pd.DataFrame({
        "Признак": order,
        "Значение": X.iloc[0].values,
        "Коэффициент": coefs,
    })

    df["Вклад"] = df["Значение"] * df["Коэффициент"]
    df["Фактор"] = df["Признак"].map(lambda x: FEATURE_LABELS.get(x, x))
    df["Абс_вклад"] = df["Вклад"].abs()

    return df.sort_values("Абс_вклад", ascending=False)

def get_model_factors_text(selected_key: str) -> str:
    """возвращает текст с топ-5 факторами из файла важности для передачи в промпт"""
    file_map = {
        'decision_tree': 'decision_tree_feature_importance.csv',
        'random_forest': 'random_forest_feature_importance.csv',
        'xgboost':       'xgboost_feature_importance.csv',
        'lightgbm':      'lightgbm_feature_importance.csv',
        'catboost':      'catboost_feature_importance.csv',
    }
    fname = file_map.get(selected_key)
    if not fname:
        return ""
    path = os.path.join(MODELS_DIR, fname)
    if not os.path.exists(path):
        return ""
    try:
        import pandas as pd
        df = pd.read_csv(path)
        col = 'Важность (perm)' if 'Важность (perm)' in df.columns else 'Важность'
        top5 = df.nlargest(5, col)
        lines = []
        for _, row in top5.iterrows():
            feat = FEATURE_LABELS.get(row['Признак'], row['Признак'])
            lines.append(f"  - {feat}: высокий вклад в прогноз (важность {row[col]:.3f})")
        return f"Наиболее важные признаки модели ({selected_key}):\n" + "\n".join(lines)
    except Exception:
        return ""


def render_result(probability: float, selected_key: str, pipeline=None, features=None, chart_key: str = "tab1"):
    """отображает результат прогноза: уровень риска, gauge и факторы из модели"""
    risk_level, risk_css, risk_text = get_risk_level(probability)

    col_res, col_interp = st.columns(2)

    with col_res:
        st.markdown(f"""
        <div class="{risk_css}">
            <div style="font-size:0.85rem; margin-bottom:4px; font-weight:500;">
                УРОВЕНЬ РИСКА
            </div>
            <div style="font-size:2.2rem; font-weight:700; margin-bottom:4px;">
                {risk_level}
            </div>
            <div style="font-size:1.6rem; font-weight:600; margin-bottom:4px;">
                {probability*100:.1f}%
            </div>
            <div style="font-size:0.82rem; opacity:0.85;">
                вероятность расторжения контракта
            </div>
        </div>
        """, unsafe_allow_html=True)

        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=round(probability * 100, 1),
            number={'suffix': '%', 'font': {'size': 28}},
            gauge={
                'axis': {'range': [0, 100]},
                'bar':  {'color': '#003087'},
                'steps': [
                    {'range': [0,  20], 'color': '#dcfce7'},
                    {'range': [20, 50], 'color': '#fef3c7'},
                    {'range': [50, 100], 'color': '#fee2e2'},
                ],
                'threshold': {
                    'line': {'color': '#003087', 'width': 3},
                    'thickness': 0.75,
                    'value': round(probability * 100, 1),
                }
            }
        ))
        fig_gauge.update_layout(height=220, margin=dict(l=20, r=20, t=20, b=0))
        st.plotly_chart(fig_gauge, use_container_width=True, key=f"gauge_{chart_key}")

    with col_interp:
        st.subheader("Интерпретация")
        st.markdown(f"_{risk_text}_")

        factors = get_model_factors(selected_key)
        if factors is not None:
            fig_bar = px.bar(
                factors.sort_values('Вес'),
                x='Вес', y='Фактор', orientation='h',
                text='Вес', color_discrete_sequence=['#003087']
            )
            fig_bar.update_traces(texttemplate='%{x:.1f}%', textposition='outside')
            fig_bar.update_layout(
                height=340,
                margin=dict(l=0, r=60, t=10, b=0),
                showlegend=False,
                xaxis_title="Вклад фактора в модель (%)",
                yaxis_title=None
            )
            st.plotly_chart(fig_bar, use_container_width=True, key=f"factors_{chart_key}")
            st.caption(
                "Вклад факторов рассчитан на основе коэффициентов выбранной модели. "
                "Детальный анализ — в разделе «Интерпретация результатов»."
            )
        else:
            st.info("Файл важности признаков не найден. Выполните обучение модели.")
        
    # блок "почему модель дала такой прогноз" — для всех моделей
    # при перерисовке страницы features берём из session_state если есть
    if features is None and 'last_features' in st.session_state:
        features    = st.session_state.get('last_features')
        probability = st.session_state.get('last_probability', probability)

    if features is not None:
        st.markdown("---")
        st.subheader("Почему модель дала такой прогноз")

        # данные контракта и поставщика в читаемом виде
        col_d1, col_d2 = st.columns(2)

        with col_d1:
            st.markdown("**Параметры контракта**")
            price_val = np.expm1(features.get("log_price", 0)) * 1_000_000
            duration  = features.get("contract_duration_days", 0)
            work_type = ("Строительство зданий" if features.get("is_buildings") else
                         "Инфраструктурные работы" if features.get("is_infrastructure") else
                         "Специализированные работы" if features.get("is_specialized") else "Прочее")
            penalty_c = features.get("penalty_count", 0)
            has_pen   = features.get("has_penalty", 0)

            st.markdown(f"""
            | Параметр | Значение |
            |---|---|
            | Цена контракта | {price_val/1_000_000:.1f} млн руб. |
            | Длительность | {int(duration)} дней |
            | Вид работ | {work_type} |
            | Штрафы | {"есть" if has_pen else "нет"} ({int(penalty_c)} шт.) |
            """)

        with col_d2:
            st.markdown("**Характеристики поставщика**")
            s_total  = features.get("supplier_total_contracts", 0)
            s_price  = features.get("supplier_avg_price", 0)
            s_reg    = features.get("supplier_regions_count", 0)

            st.markdown(f"""
            | Параметр | Значение |
            |---|---|
            | Контрактов в истории | {int(s_total)} |
            | Средняя цена контрактов | {s_price:.1f} млн руб. |
            | Регионов работы | {int(s_reg)} |
            """)

        # локальный вклад факторов — только в полном режиме
        _simplified = st.session_state.get('simplified_mode', False)
        if not _simplified and selected_key == "logistic" and pipeline is not None:
            contrib_df = get_linear_contributions(pipeline, features)
            if contrib_df is not None:
                top = contrib_df.head(7).copy()
                top["направление"] = top["Вклад"].apply(
                    lambda v: "повышает риск" if v > 0 else "снижает риск"
                )
                top["цвет"] = top["Вклад"].apply(
                    lambda v: "#991b1b" if v > 0 else "#166534"
                )

                fig_contrib = go.Figure()
                for _, row in top.sort_values("Вклад").iterrows():
                    fig_contrib.add_trace(go.Bar(
                        x=[row["Вклад"]],
                        y=[row["Фактор"]],
                        orientation="h",
                        marker_color=row["цвет"],
                        showlegend=False,
                    ))
                fig_contrib.update_layout(
                    title="Вклад факторов в прогноз (красный — повышает риск, зелёный — снижает)",
                    height=320,
                    margin=dict(l=0, r=40, t=40, b=0),
                    xaxis_title="вклад в логит вероятности расторжения",
                    yaxis_title=None,
                    barmode="overlay",
                )
                st.plotly_chart(fig_contrib, use_container_width=True)

        # сохраняем данные для AI в session_state — кнопка находится снаружи render_result
        st.session_state['ai_data'] = {
            'probability': probability,
            'selected_key': selected_key,
            'pipeline': pipeline,
            'features': features,
            'price_val': price_val,
            'duration': duration,
            'work_type': work_type,
            'has_pen': has_pen,
            'penalty_c': penalty_c,
            's_total': s_total,
            's_reg': s_reg,
        }


def render_prediction(models, simplified=False):
    """страница прогнозирования риска расторжения контракта"""
    st.header("Оценка риска расторжения контракта")
    st.markdown(
        "Система анализирует параметры контракта и историческую активность поставщика "
        "для расчёта вероятности расторжения."
    )

    if not models:
        st.error("Модели не загружены. Сначала выполните обучение (скрипты 05_0x).")
        return

    model_options = {k: v['name'] for k, v in models.items()}

    if simplified:
        # в упрощённом режиме берём лучшую модель по AUC автоматически
        best_key = max(
            models.keys(),
            key=lambda k: float(models[k].get('metrics', {}).get('test_roc_auc', 0)
                                or models[k].get('metrics', {}).get('roc_auc', 0))
        )
        selected_key = best_key
        st.caption(f"Используется лучшая модель: **{models[best_key]['name']}**")
    else:
        selected_key = st.selectbox(
            "Модель для прогнозирования:",
            list(model_options.keys()),
            format_func=lambda x: model_options[x]
        )

    pipeline = models[selected_key]['pipeline']
    # сохраняем режим для использования внутри render_result
    st.session_state['simplified_mode'] = simplified

    tab1, tab2 = st.tabs(["Планируемый контракт", "Действующий контракт"])

    # сценарий 1: прогноз по параметрам планируемого контракта
    with tab1:
        st.markdown(
            "Введите параметры планируемого контракта и ИНН поставщика. "
            "Система рассчитает вероятность расторжения до его заключения."
        )

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Параметры контракта")

            price = st.number_input(
                "Начальная цена контракта (руб.)",
                min_value=1, max_value=1_000_000_000_000,
                value=5_000_000, step=1, format="%d"
            )
            contract_duration = st.slider(
                "Плановая длительность (дней)",
                min_value=30, max_value=1095, value=180, step=30
            )
            region = st.selectbox(
                "Регион выполнения",
                options=[77, 78, 50, 23, 16, 66, 54, 61, 59, 52,
                         74, 63, 72, 89, 86, 24, 42, 31, 36, 47],
                format_func=lambda x: {
                    77: 'Москва', 78: 'Санкт-Петербург', 50: 'Московская область',
                    23: 'Краснодарский край', 16: 'Республика Татарстан',
                    66: 'Свердловская область', 54: 'Новосибирская область',
                    61: 'Ростовская область', 59: 'Пермский край',
                    52: 'Нижегородская область', 74: 'Челябинская область',
                    63: 'Самарская область', 72: 'Тюменская область',
                    89: 'Ямало-Ненецкий АО', 86: 'Ханты-Мансийский АО',
                    24: 'Красноярский край', 42: 'Кемеровская область',
                    31: 'Белгородская область', 36: 'Воронежская область',
                    47: 'Ленинградская область',
                }.get(x, str(x))
            )
            work_type = st.selectbox(
                "Вид работ (ОКПД2)",
                options=[1, 2, 3, 4],
                format_func=lambda x: {
                    1: 'Строительство зданий (41.x)',
                    2: 'Инфраструктурные работы (42.x)',
                    3: 'Специализированные работы (43.x)',
                    4: 'Прочее',
                }[x]
            )
            multi_supplier = st.checkbox("Контракт с несколькими поставщиками")

        with col2:
            st.subheader("Сведения о поставщике")

            inn_input = st.text_input(
                "ИНН поставщика (10 или 12 цифр)",
                max_chars=12,
                placeholder="например: 770512345678"
            )

            s_contracts = 10
            s_regions   = 1
            s_avg_price = price / 1_000_000
            s_avg_sup   = 1.0

            if st.button("Загрузить историю поставщика из базы"):
                if inn_input.isdigit() and len(inn_input) in (10, 12):
                    hist = load_supplier_history(inn_input)
                    st.session_state['s1_contracts']  = hist['total_contracts']
                    st.session_state['s1_regions']    = hist['regions_count']
                    st.session_state['s1_avg_price']  = hist['avg_price_mln']
                    st.session_state['s1_avg_sup']    = hist['avg_suppliers']
                    st.success(
                        f"Загружено из базы: {hist['total_contracts']} контрактов, "
                        f"{hist['regions_count']} регионов"
                    )
                else:
                    st.error("ИНН должен содержать 10 цифр (юридическое лицо) или 12 цифр (ИП).")

            s_contracts = st.number_input(
                "Количество контрактов в истории",
                min_value=1,
                value=st.session_state.get('s1_contracts', 10)
            )
            s_regions = st.number_input(
                "Количество регионов работы",
                min_value=1, max_value=89,
                value=st.session_state.get('s1_regions', 1)
            )
            s_avg_price = st.session_state.get('s1_avg_price', price / 1_000_000)
            s_avg_sup   = st.session_state.get('s1_avg_sup', 1.0)

        if st.button("Рассчитать риск", type="primary", use_container_width=True):
            warnings = []
            if price > 1_000_000_000 and contract_duration < 90:
                warnings.append(
                    "Крупный контракт (более 1 млрд руб.) с коротким сроком — нетипичная комбинация."
                )
            if s_contracts < 3:
                warnings.append(
                    "Поставщик с малым числом контрактов — история недостаточна для надёжного прогноза."
                )
            for w in warnings:
                st.warning(w)

            features = {
                'log_price':               np.log1p(price / 1_000_000),
                'contract_duration_days':  contract_duration,
                'has_penalty':             0,
                'penalty_count':           0,
                'log_penalty_total':       0,
                'procedures_count':        0,
                'penalty_per_procedure':   0,
                'penalty_severity':        0,
                'supplier_total_contracts': s_contracts,
                'supplier_avg_price':      s_avg_price,
                'supplier_regions_count':  s_regions,
                'supplier_avg_suppliers':  s_avg_sup,
                'region':                  region,
                'is_buildings':            1 if work_type == 1 else 0,
                'is_infrastructure':       1 if work_type == 2 else 0,
                'is_specialized':          1 if work_type == 3 else 0,
                'is_multi_supplier':       1 if multi_supplier else 0,
            }

            # interaction features — вычисляются из базовых признаков
            features['penalty_x_experience'] = (
                features['penalty_count'] * features['supplier_total_contracts']
            )
            features['price_x_duration'] = (
                features['log_price'] * features['contract_duration_days']
            )
            features['penalty_x_price'] = (
                features['penalty_severity'] * features['log_price']
            )

            probability = predict_risk(pipeline, features)
            if probability is not None:
                # сохраняем в session_state чтобы результат не пропал при нажатии AI-кнопки
                st.session_state['last_probability'] = probability
                st.session_state['last_features']    = features
                st.session_state['last_model_key']   = selected_key
                st.session_state['last_pipeline']    = pipeline
                # сбрасываем старый AI-комментарий — он для другого контракта/модели
                st.session_state.pop('ai_comment', None)
                st.markdown("---")
                render_result(probability, selected_key, pipeline, features, chart_key="tab1")

        # показываем результат из session_state если уже был рассчитан
        elif 'last_probability' in st.session_state and st.session_state.get('last_model_key') == selected_key:
            st.markdown("---")
            render_result(
                st.session_state['last_probability'],
                st.session_state['last_model_key'],
                st.session_state['last_pipeline'],
                st.session_state['last_features'],
                chart_key="tab1_cached"
            )

            tab_key = "tab1"

            # AI-комментарий — вынесен сюда чтобы не сбрасываться при нажатии кнопки
            groq_key = os.getenv("GROQ_API_KEY", "")
            if not groq_key:
                st.caption("для AI-вывода задайте GROQ_API_KEY. бесплатный ключ: console.groq.com")
            elif 'ai_data' in st.session_state:
                if st.button("Сформировать текстовый вывод", key=f"ai_btn_{tab_key}"):
                    d = st.session_state['ai_data']
                    risk_level_text = ("высокий" if d['probability'] >= 0.5 else
                                       "средний" if d['probability'] >= 0.2 else "низкий")
                    factors_text = ""
                    if d['selected_key'] == "logistic" and d['pipeline'] is not None:
                        contrib_df = get_linear_contributions(d['pipeline'], d['features'])
                        if contrib_df is not None:
                            lines_f = []
                            for _, row in contrib_df.head(5).iterrows():
                                direction = "повышает риск" if row["Вклад"] > 0 else "снижает риск"
                                lines_f.append(f"  - {row['Фактор']} ({row['Значение']:.2f}): {direction}")
                            factors_text = "Ключевые факторы (логрег):\n" + "\n".join(lines_f)
                    else:
                        factors_text = get_model_factors_text(d['selected_key'])

                    prompt = f"""Ты эксперт по государственным закупкам. Дай краткий профессиональный комментарий (3-4 предложения).
Вероятность расторжения: {d['probability']*100:.1f}% ({risk_level_text})
Цена: {d['price_val']/1_000_000:.1f} млн руб., длительность: {int(d['duration'])} дней
Вид работ: {d['work_type']}, штрафы: {"есть" if d['has_pen'] else "нет"} ({int(d['penalty_c'])} шт.)
Опыт поставщика: {int(d['s_total'])} контрактов, {int(d['s_reg'])} регионов
{factors_text}
Объясни почему такой прогноз и на что обратить внимание. Русский, деловой язык."""

                    with st.spinner("формируем вывод..."):
                        try:
                            import requests as req
                            resp = req.post(
                                "https://api.groq.com/openai/v1/chat/completions",
                                headers={"Content-Type": "application/json",
                                         "Authorization": f"Bearer {groq_key}"},
                                json={"model": "llama-3.3-70b-versatile",
                                      "messages": [
                                          {"role": "system", "content": "Эксперт по госзакупкам. Кратко, на русском."},
                                          {"role": "user", "content": prompt}],
                                      "max_tokens": 400, "temperature": 0.3},
                                timeout=30
                            )
                            if resp.status_code == 200:
                                st.session_state["ai_comment"] = resp.json()["choices"][0]["message"]["content"]
                            else:
                                st.warning(f"ошибка Groq: {resp.status_code}")
                        except Exception as e:
                            st.warning(f"ошибка: {e}")

            if "ai_comment" in st.session_state:
                st.markdown(f'''<div class="info-box">{st.session_state["ai_comment"]}</div>''', unsafe_allow_html=True)


    # сценарий 2: прогноз для действующего контракта через api госплан
    with tab2:
        st.markdown(
            "Введите регистрационный номер действующего контракта. "
            "Система получит его актуальные параметры и процедуры через API ГосПлан, "
            "включая текущие штрафы, и рассчитает вероятность расторжения."
        )

        reg_num = st.text_input(
            "Регистрационный номер контракта",
            placeholder="например: 2024100100123456789",
            max_chars=40
        )

        if st.button("Загрузить из API ГосПлан и рассчитать риск", type="primary"):
            if not reg_num.strip():
                st.error("Введите регистрационный номер контракта.")
            else:
                rn = reg_num.strip()

                with st.spinner("Загрузка данных контракта из API ГосПлан..."):
                    contract_data, err = fetch_contract_from_api(rn)

                if err:
                    st.error(f"Не удалось загрузить контракт: {err}")
                else:
                    with st.spinner("Загрузка процедур исполнения..."):
                        procedures, proc_err = fetch_procedures_from_api(rn)

                    if proc_err:
                        st.warning(f"Процедуры не загружены: {proc_err}. Расчёт без учёта штрафов.")

                    cf = parse_contract_fields(contract_data)
                    pf = parse_procedures_fields(procedures)

                    supplier_inn = cf['suppliers'][0] if cf['suppliers'] else ""
                    supplier_hist = load_supplier_history(supplier_inn) if supplier_inn else {
                        "total_contracts": 10, "avg_price_mln": 5.0,
                        "regions_count": 1, "avg_suppliers": 1.0,
                    }

                    log_price  = np.log1p(cf['price'] / 1_000_000)
                    log_pen    = np.log1p(pf['penalty_total'] / 1_000)
                    pen_per_pr = pf['penalty_count'] / max(pf['procedures_count'], 1)
                    pen_sev    = pf['penalty_total'] / max(cf['price'], 1)
                    okpd = cf['okpd2_str']

                    features = {
                        'log_price':               log_price,
                        'contract_duration_days':  cf['duration_days'],
                        'has_penalty':             1 if pf['penalty_count'] > 0 else 0,
                        'penalty_count':           pf['penalty_count'],
                        'log_penalty_total':       log_pen,
                        'procedures_count':        pf['procedures_count'],
                        'penalty_per_procedure':   pen_per_pr,
                        'penalty_severity':        pen_sev,
                        'supplier_total_contracts': supplier_hist['total_contracts'],
                        'supplier_avg_price':      supplier_hist['avg_price_mln'],
                        'supplier_regions_count':  supplier_hist['regions_count'],
                        'supplier_avg_suppliers':  supplier_hist['avg_suppliers'],
                        'region':                  cf['region'],
                        'is_buildings':            1 if '41.' in okpd else 0,
                        'is_infrastructure':       1 if '42.' in okpd else 0,
                        'is_specialized':          1 if '43.' in okpd else 0,
                        'is_multi_supplier':       cf['is_multi'],
                    }
                    # interaction features — вычисляются из базовых признаков
                    # нужны для логистической регрессии (деревья их не используют)
                    features['penalty_x_experience'] = (
                        features['penalty_count'] * features['supplier_total_contracts']
                    )
                    features['price_x_duration'] = (
                        features['log_price'] * features['contract_duration_days']
                    )
                    features['penalty_x_price'] = (
                        features['penalty_severity'] * features['log_price']
                    )

                    probability = predict_risk(pipeline, features)
                    if probability is not None:
                        # сохраняем всё в session_state — результат не пропадёт при нажатии AI-кнопки
                        st.session_state['tab2_cf']          = cf
                        st.session_state['tab2_pf']          = pf
                        st.session_state['tab2_probability'] = probability
                        st.session_state['tab2_features']    = features
                        st.session_state['tab2_model_key']   = selected_key
                        st.session_state['tab2_pipeline']    = pipeline
                        st.session_state.pop('ai_comment', None)

            # отображаем результат из session_state — показываем всегда если есть данные
            if 'tab2_probability' in st.session_state:
                cf          = st.session_state['tab2_cf']
                pf          = st.session_state['tab2_pf']
                probability = st.session_state['tab2_probability']
                features    = st.session_state['tab2_features']
                pipeline_t2 = st.session_state['tab2_pipeline']

                st.markdown("---")
                st.subheader("Данные из API ГосПлан")

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Цена контракта",    f"{cf['price']/1_000_000:.1f} млн руб.")
                c2.metric("Длительность",      f"{cf['duration_days']} дней")
                c3.metric("Штрафных процедур", f"{pf['penalty_count']}")
                c4.metric("Сумма штрафов",
                          f"{pf['penalty_total']/1000:.1f} тыс. руб." if pf['penalty_total'] > 0 else "—")

                if cf['subject']:
                    st.markdown(f"**Предмет контракта:** {cf['subject']}")

                if cf['stage'] == "ET":
                    st.markdown("""
                    <div class="risk-high" style="font-size:0.9rem; text-align:left;">
                        Внимание: контракт уже расторгнут (стадия ET).
                        Прогноз показывает вероятность, которую модель оценивала бы на основе текущих данных.
                    </div>
                    """, unsafe_allow_html=True)
                    st.markdown("<br>", unsafe_allow_html=True)

                if pf['penalty_details']:
                    with st.expander(f"Штрафные процедуры ({len(pf['penalty_details'])} шт.)"):
                        pen_df = pd.DataFrame(pf['penalty_details'])
                        pen_df['сумма (руб.)'] = pen_df['сумма (руб.)'].apply(lambda x: f"{x:,.0f}")
                        st.dataframe(pen_df, use_container_width=True, hide_index=True)

                if pf['has_termination'] and pf['termination_reason']:
                    st.info(f"Причина расторжения: {pf['termination_reason']}")

                st.markdown("---")
                render_result(probability, selected_key, pipeline_t2, features, chart_key="tab2")

            # AI-комментарий — всегда снаружи if-блока, не зависит от перерисовки
            if 'tab2_probability' in st.session_state:
                groq_key = os.getenv("GROQ_API_KEY", "")
                if not groq_key:
                    st.caption("для AI-вывода задайте GROQ_API_KEY. бесплатный ключ: console.groq.com")
                elif 'ai_data' in st.session_state:
                    if st.button("Сформировать текстовый вывод", key="ai_btn_tab2"):
                        d = st.session_state['ai_data']
                        risk_level_text = ("высокий" if d['probability'] >= 0.5 else
                                           "средний" if d['probability'] >= 0.2 else "низкий")
                        factors_text = ""
                        if d['selected_key'] == "logistic" and d['pipeline'] is not None:
                            contrib_df = get_linear_contributions(d['pipeline'], d['features'])
                            if contrib_df is not None:
                                lines_f = []
                                for _, row in contrib_df.head(5).iterrows():
                                    direction = "повышает риск" if row["Вклад"] > 0 else "снижает риск"
                                    lines_f.append(f"  - {row['Фактор']} ({row['Значение']:.2f}): {direction}")
                                factors_text = "Ключевые факторы (логрег):\n" + "\n".join(lines_f)
                        else:
                            factors_text = get_model_factors_text(d['selected_key'])

                        prompt = f"""Ты эксперт по государственным закупкам. Дай краткий профессиональный комментарий (3-4 предложения).
    Вероятность расторжения: {d['probability']*100:.1f}% ({risk_level_text})
    Цена: {d['price_val']/1_000_000:.1f} млн руб., длительность: {int(d['duration'])} дней
    Вид работ: {d['work_type']}, штрафы: {"есть" if d['has_pen'] else "нет"} ({int(d['penalty_c'])} шт.)
    Опыт поставщика: {int(d['s_total'])} контрактов, {int(d['s_reg'])} регионов
    {factors_text}
    Объясни почему такой прогноз и на что обратить внимание. Русский, деловой язык."""

                        with st.spinner("формируем вывод..."):
                            try:
                                import requests as req
                                resp = req.post(
                                    "https://api.groq.com/openai/v1/chat/completions",
                                    headers={"Content-Type": "application/json",
                                             "Authorization": f"Bearer {groq_key}"},
                                    json={"model": "llama-3.3-70b-versatile",
                                          "messages": [
                                              {"role": "system", "content": "Эксперт по госзакупкам. Кратко, на русском."},
                                              {"role": "user", "content": prompt}],
                                          "max_tokens": 400, "temperature": 0.3},
                                    timeout=30
                                )
                                if resp.status_code == 200:
                                    st.session_state["ai_comment"] = resp.json()["choices"][0]["message"]["content"]
                                else:
                                    st.warning(f"ошибка Groq: {resp.status_code}")
                            except Exception as e:
                                st.warning(f"ошибка: {e}")

            if "ai_comment" in st.session_state:
                    st.markdown(f'''<div class="info-box">{st.session_state["ai_comment"]}</div>''', unsafe_allow_html=True)