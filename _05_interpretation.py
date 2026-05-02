# pages/_05_interpretation.py
import streamlit as st
import pandas as pd
import plotly.express as px
import os
from config import MODELS_DIR

# читаемые названия признаков для отображения
FEATURE_LABELS = {
    'procedures_count':         'Количество процедур по контракту',
    'log_price':                'Логарифм цены контракта',
    'has_penalty':              'Наличие штрафов',
    'supplier_avg_price':       'Средняя цена контрактов поставщика',
    'supplier_total_contracts': 'Число контрактов в истории поставщика',
    'contract_duration_days':   'Длительность контракта (дни)',
    'log_penalty_total':        'Логарифм суммы штрафов',
    'penalty_per_procedure':    'Штрафы на одну процедуру',
    'penalty_count':            'Количество штрафов',
    'penalty_severity':         'Тяжесть штрафов (доля от цены)',
    'is_buildings':             'Строительство зданий (ОКПД2 41.x)',
    'has_penalty':              'Наличие штрафов',
    'supplier_regions_count':   'Число регионов работы поставщика',
    'is_specialized':           'Специализированные работы (43.x)',
    'is_infrastructure':        'Инфраструктурные работы (42.x)',
    'supplier_avg_suppliers':   'Среднее число соисполнителей',
    'region':                   'Регион',
    'is_multi_supplier':        'Контракт с несколькими поставщиками',
}


def translate(df):
    """переводит технические названия признаков в читаемые"""
    df = df.copy()
    df['Признак'] = df['Признак'].map(lambda x: FEATURE_LABELS.get(x, x))
    return df


def safe_float(d, *keys):
    """безопасное чтение числового значения по нескольким возможным ключам"""
    for k in keys:
        if k in d:
            try:
                return float(d[k])
            except Exception:
                pass
    return 0.0


def render_recommendations(top_factors, model_type):
    """
    формирует текстовые рекомендации для заказчиков на основе топ-факторов риска.
    рекомендации статические, но привязаны к реальным топ-факторам из модели.
    """
    st.subheader("Практические рекомендации для заказчиков")
    st.markdown(
        "На основе анализа ключевых факторов риска сформированы следующие рекомендации "
        "для снижения вероятности расторжения строительных контрактов."
    )

    recs = {
        'Наличие штрафов':
            "Наличие штрафов — сильнейший предиктор расторжения. "
            "Усильте мониторинг исполнения на ранних этапах: фиксируйте нарушения и "
            "применяйте штрафные санкции своевременно, не допуская их накопления.",
        'Количество штрафов':
            "Повторные штрафы резко увеличивают риск. "
            "При двух и более нарушениях рекомендуется провести внеплановую проверку "
            "хода исполнения и рассмотреть вопрос о досрочном расторжении по соглашению сторон.",
        'Логарифм цены контракта':
            "Крупные контракты расторгаются чаще. "
            "Для контрактов свыше 50 млн руб. рекомендуется разбивка на этапы с "
            "промежуточной приёмкой и банковскими гарантиями на каждый этап.",
        'Цена контракта':
            "Крупные контракты расторгаются чаще. "
            "Для контрактов свыше 50 млн руб. рекомендуется разбивка на этапы с "
            "промежуточной приёмкой и банковскими гарантиями на каждый этап.",
        'Длительность контракта (дни)':
            "Длительные контракты несут повышенный риск. "
            "Для контрактов сроком более года рекомендуется устанавливать контрольные точки "
            "и предусматривать механизм обновления гарантийного обеспечения.",
        'Инфраструктурные работы (42.x)':
            "Инфраструктурные контракты — наиболее рискованная категория. "
            "Требуйте расширенный пакет гарантий и независимую техническую экспертизу "
            "на этапе приёмки.",
        'Специализированные работы (43.x)':
            "Специализированные работы связаны с повышенным риском. "
            "Проверяйте наличие у поставщика профильных допусков СРО и квалифицированных "
            "субподрядчиков до заключения контракта.",
        'Число контрактов в истории поставщика':
            "Опытные поставщики расторгают контракты реже. "
            "При выборе между поставщиками с равной ценой отдавайте предпочтение тому, "
            "у кого больше успешно завершённых контрактов.",
    }

    shown = 0
    if top_factors is not None:
        for factor in top_factors:
            if factor in recs:
                st.markdown(f"""
                <div class="info-box" style="margin-bottom:10px;">
                    <b>{factor}</b><br>{recs[factor]}
                </div>
                """, unsafe_allow_html=True)
                shown += 1

    # общие рекомендации если конкретных не нашлось
    if shown == 0:
        st.markdown("""
        <div class="info-box">
            <b>Общие рекомендации</b><br>
            Тщательно проверяйте историю поставщика по ИНН перед заключением контракта.
            Разбивайте крупные контракты на этапы с промежуточной приёмкой.
            Усиливайте контроль при наличии первых штрафных процедур.
        </div>
        """, unsafe_allow_html=True)


def render_interpretation(models):
    """страница интерпретации моделей: коэффициенты, важность признаков, рекомендации"""
    st.header("Интерпретация моделей и ключевые факторы риска")

    if not models:
        st.warning("Модели не загружены.")
        return

    selected_key = st.selectbox(
        "Модель для анализа:",
        list(models.keys()),
        format_func=lambda x: models[x]['name']
    )
    model_data = models[selected_key]

    # метрики выбранной модели
    st.subheader("Метрики на тестовой выборке")
    metrics = model_data.get('metrics', {})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ROC-AUC",  f"{safe_float(metrics, 'test_roc_auc', 'roc_auc'):.4f}")
    c2.metric("Precision", f"{safe_float(metrics, 'test_precision', 'precision'):.4f}")
    c3.metric("Recall",    f"{safe_float(metrics, 'test_recall', 'recall'):.4f}")
    c4.metric("F1-score",  f"{safe_float(metrics, 'test_f1', 'f1'):.4f}")

    baseline = safe_float(metrics, 'dummy_f1')
    if baseline > 0:
        improvement = safe_float(metrics, 'improvement_vs_dummy')
        st.markdown(
            f"Улучшение по F1-score относительно DummyClassifier: "
            f"**+{improvement:.1f}%** (базовая линия F1 = {baseline:.4f})"
        )

    st.markdown("---")

    top_factor_names = []

    # логистическая регрессия: коэффициенты и odds ratios
    if selected_key == 'logistic':
        coef_path = os.path.join(MODELS_DIR, 'logistic_coefficients.csv')
        if not os.path.exists(coef_path):
            st.warning("Файл коэффициентов не найден. Выполните скрипт 05_01.")
            return

        coef_df = translate(pd.read_csv(coef_path))
        abs_col = 'Абс_коэф' if 'Абс_коэф' in coef_df.columns else 'Абсолютное значение'

        top_factor_names = coef_df.nlargest(5, abs_col)['Признак'].tolist()

        # текстовое резюме топ-факторов
        st.subheader("Ключевые факторы риска")
        top5 = coef_df.nlargest(5, abs_col)
        lines = []
        for i, (_, row) in enumerate(top5.iterrows(), 1):
            direction = "повышает" if row['Коэффициент'] > 0 else "снижает"
            mult = row.get('Вероятностный_множитель', None)
            pct = abs(mult - 1) * 100 if mult is not None else None
            pct_str = f" (odds ratio: {pct:.0f}%)" if pct is not None else ""
            lines.append(f"{i}. **{row['Признак']}** — {direction} риск расторжения{pct_str}.")
        st.markdown("\n".join(lines))

        st.markdown("---")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Факторы, повышающие риск")
            st.caption("признаки с положительным коэффициентом")
            pos = coef_df[coef_df['Коэффициент'] > 0].nlargest(10, abs_col)
            fig = px.bar(
                pos, x='Коэффициент', y='Признак', orientation='h',
                text_auto='.2f', color_discrete_sequence=['#991b1b']
            )
            fig.update_layout(height=420, margin=dict(l=0, r=20, t=10, b=0), yaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Факторы, снижающие риск")
            st.caption("признаки с отрицательным коэффициентом")
            neg = coef_df[coef_df['Коэффициент'] < 0].nlargest(10, abs_col)
            fig = px.bar(
                neg, x='Коэффициент', y='Признак', orientation='h',
                text_auto='.2f', color_discrete_sequence=['#166534']
            )
            fig.update_layout(height=420, margin=dict(l=0, r=20, t=10, b=0), yaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Полная таблица коэффициентов")
        st.dataframe(coef_df, use_container_width=True, hide_index=True)

    # дерево решений и случайный лес: permutation importance
    elif selected_key in ('decision_tree', 'random_forest', 'xgboost', 'lightgbm', 'catboost', 'neural_network'):
        file_map = {
            'decision_tree': 'decision_tree_feature_importance.csv',
            'random_forest': 'random_forest_feature_importance.csv',
            'xgboost':       'xgboost_feature_importance.csv',
            'lightgbm':      'lightgbm_feature_importance.csv',
            'catboost':      'catboost_feature_importance.csv',
            'neural_network': 'neural_network_feature_importance.csv',
        }
        path = os.path.join(MODELS_DIR, file_map[selected_key])

        if not os.path.exists(path):
            st.warning("Файл важности признаков не найден. Выполните обучение.")
            return

        imp_df = translate(pd.read_csv(path))
        perm_col = 'Важность (perm)' if 'Важность (perm)' in imp_df.columns else 'Важность'
        has_perm = perm_col == 'Важность (perm)'

        top_factor_names = (
            imp_df[imp_df[perm_col] > 0].nlargest(5, perm_col)['Признак'].tolist()
        )

        # текстовое резюме
        st.subheader("Ключевые факторы риска")
        if has_perm:
            st.caption(
                "permutation importance показывает, насколько снижается F1-score модели "
                "при случайном перемешивании значений каждого признака на тестовой выборке. "
                "Чем больше снижение — тем важнее признак."
            )

        top5 = imp_df[imp_df[perm_col] > 0].nlargest(5, perm_col)
        lines = []
        for i, (_, row) in enumerate(top5.iterrows(), 1):
            lines.append(
                f"{i}. **{row['Признак']}** — вклад {row[perm_col]:.3f}"
                + (f" ± {row['Std (perm)']:.3f}" if 'Std (perm)' in row else "")
            )
        st.markdown("\n".join(lines))

        st.markdown("---")

        st.subheader("Топ-15 признаков по важности")
        top15 = imp_df[imp_df[perm_col] > 0].nlargest(15, perm_col).sort_values(perm_col)

        xerr = 'Std (perm)' if 'Std (perm)' in top15.columns else None
        fig = px.bar(
            top15, x=perm_col, y='Признак', orientation='h',
            error_x=xerr, text_auto='.3f',
            color_discrete_sequence=['#003087']
        )
        fig.update_layout(
            height=520,
            margin=dict(l=0, r=60, t=10, b=0),
            xaxis_title=(
                "снижение F1 при перемешивании (permutation importance)"
                if has_perm else "важность признака"
            ),
            yaxis_title=None
        )
        st.plotly_chart(fig, use_container_width=True)

        # mdi для справки — не используется как основной показатель
        if has_perm and 'Важность (MDI)' in imp_df.columns:
            with st.expander("MDI-важность (справочно, не используется как основная метрика)"):
                st.caption(
                    "MDI (Mean Decrease Impurity) — встроенная важность случайного леса. "
                    "Смещена в сторону признаков с большим числом уникальных значений, "
                    "поэтому в качестве основной метрики используется permutation importance."
                )
                mdi15 = imp_df.nlargest(15, 'Важность (MDI)').sort_values('Важность (MDI)')
                fig_mdi = px.bar(
                    mdi15, x='Важность (MDI)', y='Признак', orientation='h',
                    text_auto='.3f', color_discrete_sequence=['#6b7280']
                )
                fig_mdi.update_layout(height=420, margin=dict(l=0, r=40, t=10, b=0))
                st.plotly_chart(fig_mdi, use_container_width=True)

        st.subheader("Полная таблица важности признаков")
        st.dataframe(imp_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # практические рекомендации на основе топ-факторов
    render_recommendations(top_factor_names, selected_key)

    st.markdown("---")
    st.subheader("SHAP-анализ")
    st.info(
        "SHAP (SHapley Additive exPlanations) позволяет объяснить предсказание модели "
        "для каждого конкретного контракта — какие признаки и на сколько сдвинули вероятность "
        "относительно среднего. Будет добавлен после финализации моделей."
    )