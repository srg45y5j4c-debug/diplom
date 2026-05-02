# app.py
import streamlit as st
import os
from config import APP_TITLE, APP_ICON, PAGE_LAYOUT, DB_PATH
from utils.styles import apply_custom_styles

st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout=PAGE_LAYOUT,
    initial_sidebar_state="expanded"
)

apply_custom_styles()

# проверка доступности базы данных при старте
if not os.path.exists(DB_PATH):
    st.error(
        f"База данных не найдена по пути: {DB_PATH}\n\n"
        "Убедитесь что файл gosplan_construction.db находится в папке data/."
    )
    st.stop()

# учётные данные пользователей
# в реальной системе хранить в бд с хешированием паролей
USERS = {
    "admin":   {"password": "admin123",   "role": "admin",    "name": "Администратор системы"},
    "manager": {"password": "manager123", "role": "manager",  "name": "Руководитель отдела закупок"},
    "user":    {"password": "user123",    "role": "user",     "name": "Специалист по контрактам"},
}


def _get(d, *keys):
    """безопасное чтение числовой метрики по нескольким возможным ключам"""
    for k in keys:
        if k in d:
            try:
                return float(d[k])
            except Exception:
                pass
    return 0.0


def render_login():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("""
        <div style="text-align:center; margin-bottom:2rem;">
            <h2 style="color:#003087; margin:8px 0 4px;">RiskAnalyzer</h2>
            <p style="color:#6b7280; font-size:0.9rem; margin:0;">
                Система оценки рисков расторжения госконтрактов
            </p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="background:#ffffff; border:1px solid #d1d5db;
                    border-top:4px solid #003087; border-radius:8px;
                    padding:28px 32px;">
            <p style="font-weight:600; color:#003087; margin:0 0 1rem; font-size:1rem;">
                Вход в систему
            </p>
        </div>
        """, unsafe_allow_html=True)

        login    = st.text_input("Логин", placeholder="Введите логин")
        password = st.text_input("Пароль", type="password", placeholder="Введите пароль")

        if st.button("Войти", use_container_width=True, type="primary"):
            if login in USERS and USERS[login]["password"] == password:
                st.session_state.authenticated = True
                st.session_state.role          = USERS[login]["role"]
                st.session_state.username      = login
                st.session_state.name          = USERS[login]["name"]
                st.rerun()
            else:
                st.error("Неверный логин или пароль")

        # демо-доступ скрыт под expander — не мешает на демонстрации
        with st.expander("Демо-режим"):
            st.markdown("""
            <div style="font-size:0.82rem; color:#6b7280;">
                Администратор: <code>admin</code> / <code>admin123</code><br>
                Руководитель: <code>manager</code> / <code>manager123</code><br>
                Специалист: <code>user</code> / <code>user123</code>
            </div>
            """, unsafe_allow_html=True)


def render_admin_sidebar(models):
    with st.sidebar:
        st.markdown("""
        <div style="padding:8px 0 16px 0;">
            <div style="font-size:1.2rem; font-weight:700; color:#003087;">RiskAnalyzer</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div style="background:#e8f0fe; border:1px solid #a8c0f0;
                    border-radius:6px; padding:8px 12px; margin-bottom:12px;">
            <div style="font-size:0.72rem; color:#6b7280; font-weight:600;
                        text-transform:uppercase; letter-spacing:0.05em;">Роль</div>
            <div style="font-size:0.9rem; color:#003087; font-weight:600;">Администратор</div>
            <div style="font-size:0.78rem; color:#6b7280;">{st.session_state.name}</div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        st.markdown(
            "<p style='font-size:0.78rem; font-weight:600; color:#6b7280; "
            "text-transform:uppercase; letter-spacing:0.05em; margin-bottom:8px;'>"
            "Навигация</p>", unsafe_allow_html=True
        )

        # порядок: сначала бизнес-задачи, потом ml-аналитика
        page = st.radio("Раздел", [
            "Дашборд",
            "Прогнозирование риска",
            "Анализ поставщиков",
            "Сравнение моделей",
            "Интерпретация результатов",
            "О системе",
        ], label_visibility="collapsed")

        st.divider()

        st.markdown(
            "<p style='font-size:0.78rem; font-weight:600; color:#6b7280; "
            "text-transform:uppercase; letter-spacing:0.05em; margin-bottom:8px;'>"
            "Модели</p>", unsafe_allow_html=True
        )

        if models:
            st.success(f"Загружено: **{len(models)}**")
            for k, v in models.items():
                m   = v.get('metrics', {})
                f1  = _get(m, 'test_f1', 'f1')
                auc = _get(m, 'test_roc_auc', 'roc_auc')
                st.markdown(
                    f"<div style='font-size:0.8rem; padding:4px 0; "
                    f"border-bottom:0.5px solid #e5e7eb;'>"
                    f"<b>{v['name']}</b><br>"
                    f"<span style='color:#6b7280;'>F1 {f1:.3f} · AUC {auc:.3f}</span></div>",
                    unsafe_allow_html=True
                )
        else:
            st.warning("Модели не загружены")
            st.caption("Запустите скрипты 05_0x")

        st.divider()

        if st.button("Выйти", use_container_width=True):
            for key in ['authenticated', 'role', 'username', 'name']:
                st.session_state.pop(key, None)
            st.rerun()

        return page


def render_manager_sidebar():
    with st.sidebar:
        st.markdown("""
        <div style="padding:8px 0 16px 0;">
            <div style="font-size:1.2rem; font-weight:700; color:#003087;">RiskAnalyzer</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div style="background:#fef3c7; border:1px solid #fcd34d;
                    border-radius:6px; padding:8px 12px; margin-bottom:12px;">
            <div style="font-size:0.72rem; color:#92400e; font-weight:600;
                        text-transform:uppercase; letter-spacing:0.05em;">Роль</div>
            <div style="font-size:0.9rem; color:#92400e; font-weight:600;">Руководитель</div>
            <div style="font-size:0.78rem; color:#92400e;">{st.session_state.name}</div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        page = st.radio("Раздел", [
            "Сводка по рынку",
            "Оценка риска контракта",
        ], label_visibility="collapsed")

        st.divider()

        with st.expander("Справка"):
            st.markdown("""
            **Сводка по рынку** — ключевые показатели рынка строительных контрактов: динамика расторжений, риски по регионам.

            **Оценка риска** — быстрая проверка контракта или поставщика перед принятием решения.
            """)

        st.divider()

        if st.button("Выйти", use_container_width=True):
            for key in ['authenticated', 'role', 'username', 'name']:
                st.session_state.pop(key, None)
            st.rerun()

        return page


def render_user_sidebar():
    with st.sidebar:
        st.markdown("""
        <div style="padding:8px 0 16px 0;">
            <div style="font-size:1.2rem; font-weight:700; color:#003087;">RiskAnalyzer</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div style="background:#dcfce7; border:1px solid #86efac;
                    border-radius:6px; padding:8px 12px; margin-bottom:12px;">
            <div style="font-size:0.72rem; color:#6b7280; font-weight:600;
                        text-transform:uppercase; letter-spacing:0.05em;">Роль</div>
            <div style="font-size:0.9rem; color:#166534; font-weight:600;">Пользователь</div>
            <div style="font-size:0.78rem; color:#6b7280;">{st.session_state.name}</div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        st.markdown(
            "<p style='font-size:0.78rem; font-weight:600; color:#6b7280; "
            "text-transform:uppercase; letter-spacing:0.05em; margin-bottom:8px;'>"
            "Навигация</p>", unsafe_allow_html=True
        )

        page = st.radio("Раздел", [
            "Статистика по региону",
            "Прогнозирование риска",
            "Анализ поставщиков",
        ], label_visibility="collapsed")

        st.divider()

        with st.expander("Как использовать"):
            st.markdown("""
            1. **Статистика** — уровень риска расторжений в вашем регионе
            2. **Прогнозирование** — введите параметры контракта и получите оценку риска
            3. **Анализ поставщиков** — проверьте надёжность поставщика по ИНН
            """)

        st.divider()

        if st.button("Выйти", use_container_width=True):
            for key in ['authenticated', 'role', 'username', 'name']:
                st.session_state.pop(key, None)
            st.rerun()

        return page


def render_about():
    """страница о системе — методология, источники данных, ограничения"""
    st.header("О системе")

    st.markdown("""
    <div class="info-box">
        <h3>RiskAnalyzer — система оценки рисков расторжения строительных госконтрактов</h3>
        <p>
            Разработана в рамках магистерской диссертации. Система предназначена для
            автоматизированной оценки вероятности расторжения контрактов в сфере строительства,
            заключённых в соответствии с Федеральным законом № 44-ФЗ.
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Источник данных")
        st.markdown("""
        **API ГосПлан (v2.gosplan.info)** — агрегатор данных Единой информационной
        системы в сфере закупок (ЕИС).

        - Период выгрузки: 2022–2026 гг.
        - Классификатор ОКПД2: 41.x (здания), 42.x (инфраструктура), 43.x (спецработы)
        - Стадии контрактов: ET (расторгнут), EC (завершён)
        - Размер выборки: более 200 000 контрактов
        - Уникальных поставщиков: более 20 000
        """)

        st.subheader("Целевая переменная")
        st.markdown("""
        **is_terminated** — бинарный признак расторжения контракта:
        - 1 (расторгнут) — стадия ET
        - 0 (завершён) — стадия EC

        Среднее по выборке: ~22% расторжений.
        """)

    with col2:
        st.subheader("Методология моделирования")
        st.markdown("""
        Обучено 6 моделей бинарной классификации:

        | Модель | Назначение |
        |--------|------------|
        | Логистическая регрессия | интерпретируемая baseline-модель |
        | Дерево решений | наглядность правил классификации |
        | Случайный лес | ансамблевая, устойчива к шуму |
        | XGBoost | градиентный бустинг, высокая точность |
        | LightGBM | быстрый градиентный бустинг |
        | CatBoost | бустинг, устойчив к категориальным признакам |

        Все модели обучены с:
        - **GridSearchCV** (подбор гиперпараметров)
        - **StratifiedKFold** (5 фолдов, сохранение пропорций классов)
        - **DummyClassifier** (базовая линия для сравнения)
        - **sklearn Pipeline** (исключает утечку данных при CV)
        """)

        st.subheader("Ограничения системы")
        st.markdown("""
        - Модели обучены на исторических данных — не учитывают новые регуляторные изменения
        - Признак «регион» закодирован числово — для линейных моделей это упрощение
        - Прогноз носит вероятностный характер и не является юридически значимым решением
        - Данные ограничены строительной отраслью (ОКПД2 41-43)
        """)

    st.subheader("Признаки модели")
    st.markdown("""
    | Признак | Описание |
    |---------|----------|
    | log_price | логарифм цены контракта (млн руб.) |
    | contract_duration_days | плановая длительность исполнения |
    | region | код региона РФ |
    | is_buildings / is_infrastructure / is_specialized | тип строительства |
    | is_multi_supplier | наличие нескольких поставщиков |
    | penalty_count | количество штрафных процедур |
    | log_penalty_total | логарифм суммы штрафов |
    | procedures_count | общее число процедур по контракту |
    | penalty_per_procedure | интенсивность штрафов |
    | penalty_severity | тяжесть штрафов (доля от цены) |
    | supplier_total_contracts | опыт поставщика |
    | supplier_avg_price | средняя цена контрактов поставщика |
    | supplier_regions_count | география работы поставщика |
    | supplier_avg_suppliers | среднее число соисполнителей |

    Признак `supplier_terminated_share` намеренно исключён из модели
    как вызывающий утечку данных (вычисляется из целевой переменной).
    Используется только в аналитических блоках дашборда.
    """)


# инициализация состояния
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    render_login()
    st.stop()

from utils.data_loader import load_models
models = load_models()

role = st.session_state.role

if role == "admin":
    page = render_admin_sidebar(models)

    if page == "Дашборд":
        from pages._01_dashboard import render_dashboard
        render_dashboard()
    elif page == "Прогнозирование риска":
        from pages._02_prediction import render_prediction
        render_prediction(models)
    elif page == "Анализ поставщиков":
        from pages._04_supplier_analysis import render_supplier_analysis
        render_supplier_analysis()
    elif page == "Сравнение моделей":
        from pages._03_model_comparison import render_model_comparison
        render_model_comparison()
    elif page == "Интерпретация результатов":
        from pages._05_interpretation import render_interpretation
        render_interpretation(models)
    elif page == "О системе":
        render_about()

elif role == "manager":
    page = render_manager_sidebar()

    if page == "Сводка по рынку":
        from pages._07_manager_dashboard import render_manager_dashboard
        render_manager_dashboard()
    elif page == "Оценка риска контракта":
        from pages._02_prediction import render_prediction
        render_prediction(models, simplified=True)

elif role == "user":
    page = render_user_sidebar()

    if page == "Статистика по региону":
        from pages._08_user_dashboard import render_user_dashboard
        render_user_dashboard()
    elif page == "Прогнозирование риска":
        from pages._02_prediction import render_prediction
        render_prediction(models, simplified=True)
    elif page == "Анализ поставщиков":
        from pages._04_supplier_analysis import render_supplier_analysis
        render_supplier_analysis(user_mode=True)