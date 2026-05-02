# sidebar.py
import streamlit as st
from datetime import datetime

def render_sidebar(models):
    """Отрисовка боковой панели в государственном стиле"""
    with st.sidebar:
        # =====================================================
        # ШАПКА: ЛОГОТИП И НАЗВАНИЕ
        # =====================================================
        st.markdown("""
        <div style="padding: 8px 0 16px 0;">
            <div style="font-size: 1.3rem; font-weight: 700; color: #003087;">
                🏛️ RiskAnalyzer
            </div>
            <div style="font-size: 0.78rem; color: #6b7280; margin-top: 2px;">
                Система оценки рисков расторжения контрактов
            </div>
            <div style="font-size: 0.72rem; color: #9ca3af; margin-top: 2px;">
                Прототип для государственного сектора · v1.0
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # =====================================================
        # НАВИГАЦИЯ
        # =====================================================
        st.markdown(
            "<p style='font-size:0.8rem; font-weight:600; color:#6b7280; "
            "text-transform:uppercase; letter-spacing:0.05em; margin-bottom:8px;'>"
            "Навигация</p>",
            unsafe_allow_html=True
        )

        page = st.radio(
            "Раздел:",
            [
                "Дашборд",
                "Прогнозирование риска",
                "Сравнение моделей",
                "Анализ поставщиков",
                "Интерпретация результатов"
            ],
            label_visibility="collapsed"
        )

        st.divider()

        # =====================================================
        # СОСТОЯНИЕ МОДЕЛЕЙ
        # =====================================================
        st.markdown(
            "<p style='font-size:0.8rem; font-weight:600; color:#6b7280; "
            "text-transform:uppercase; letter-spacing:0.05em; margin-bottom:8px;'>"
            "Состояние моделей</p>",
            unsafe_allow_html=True
        )

        if models and len(models) > 0:
            st.success(f"Загружено моделей: **{len(models)}**")

            for model_key, model_data in models.items():
                with st.expander(f"📊 {model_data.get('name', 'Модель')}"):
                    metrics = model_data.get('metrics', {})
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("F1-score", f"{metrics.get('f1', 0):.3f}")
                        st.metric("Precision", f"{metrics.get('precision', 0):.3f}")
                    with col2:
                        st.metric("ROC-AUC", f"{metrics.get('roc_auc', 0):.3f}")
                        st.metric("Recall", f"{metrics.get('recall', 0):.3f}")
        else:
            st.warning("Модели не загружены")
            st.info("Выполните этапы обучения (скрипты 05_0x)")

        st.divider()

        # =====================================================
        # СПРАВКА
        # =====================================================
        st.markdown(
            "<p style='font-size:0.8rem; font-weight:600; color:#6b7280; "
            "text-transform:uppercase; letter-spacing:0.05em; margin-bottom:8px;'>"
            "Справка</p>",
            unsafe_allow_html=True
        )

        with st.expander("Как использовать систему"):
            st.markdown("""
            1. **Дашборд** — общая статистика по контрактам
            2. **Прогнозирование** — оценка риска для нового контракта
            3. **Сравнение моделей** — анализ качества ML-моделей
            4. **Анализ поставщиков** — надёжность по ИНН
            5. **Интерпретация** — ключевые факторы риска
            """)

        with st.expander("Техническая поддержка"):
            st.markdown("""
            **Email:** support@gosplan.ru  
            **Телефон:** +7 (495) XXX-XX-XX  
            **Документация:** [ссылка на вики]
            """)

        st.divider()

        # =====================================================
        # ФУТЕР ПАНЕЛИ
        # =====================================================
        st.caption(f"Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        st.caption("© 2026 Государственное управление")

        return page