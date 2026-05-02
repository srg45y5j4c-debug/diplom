# pages/_03_model_comparison.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from config import MODELS_DIR


def _get(row, *keys):
    """безопасное чтение метрики по нескольким возможным именам колонок"""
    for k in keys:
        if k in row and pd.notna(row[k]):
            try:
                return float(row[k])
            except Exception:
                pass
    return 0.0


def render_model_comparison():
    """страница сравнения всех обученных моделей по метрикам качества"""
    st.header("Сравнение моделей машинного обучения")
    st.markdown(
        "Все три модели обучены на одном датасете (173 496 контрактов) "
        "с 5-кратной стратифицированной кросс-валидацией (StratifiedKFold). "
        "Метрики рассчитаны на отложенной тестовой выборке (30%). "
        "Базовая линия (DummyClassifier) показывает результат тривиального предсказания — "
        "любая обученная модель должна её превосходить."
    )

    # загружаем метрики всех трёх моделей
    sources = [
        ("Логистическая регрессия", "logistic_metrics.csv"),
        ("Дерево решений",          "decision_tree_metrics.csv"),
        ("Случайный лес",           "random_forest_metrics.csv"),
        ("XGBoost",                 "xgboost_metrics.csv"),
        ("LightGBM",                "lightgbm_metrics.csv"),
        ("CatBoost",                "catboost_metrics.csv"),
    ]

    rows = []
    dummy_f1 = None

    for model_name, fname in sources:
        path = os.path.join(MODELS_DIR, fname)
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path)
        f1_col = 'test_f1' if 'test_f1' in df.columns else 'f1'
        best = df.sort_values(f1_col, ascending=False).iloc[0]

        f1  = _get(best, 'test_f1', 'f1')
        auc = _get(best, 'test_roc_auc', 'roc_auc')
        pre = _get(best, 'test_precision', 'precision')
        rec = _get(best, 'test_recall', 'recall')
        acc = _get(best, 'test_accuracy', 'accuracy')
        d_f1 = _get(best, 'dummy_f1')

        # сохраняем значение бейзлайна из первой загруженной модели
        if dummy_f1 is None and d_f1 > 0:
            dummy_f1 = d_f1

        rows.append({
            "Модель":               model_name,
            "ROC-AUC":              round(auc, 4),
            "Precision":            round(pre, 4),
            "Recall":               round(rec, 4),
            "F1-score":             round(f1, 4),
            "Accuracy":             round(acc, 4),
            "Улучшение vs Baseline": f"+{_get(best, 'improvement_vs_dummy'):.1f}%",
        })

    if not rows:
        st.warning("Метрики моделей не найдены. Выполните скрипты 05_01, 05_02, 05_03.")
        return

    # добавляем строку с бейзлайном для наглядного сравнения
    if dummy_f1 is not None:
        rows.insert(0, {
            "Модель":               "DummyClassifier (базовая линия)",
            "ROC-AUC":              0.5,
            "Precision":            round(dummy_f1, 4),
            "Recall":               round(dummy_f1, 4),
            "F1-score":             round(dummy_f1, 4),
            "Accuracy":             round(dummy_f1, 4),
            "Улучшение vs Baseline": "—",
        })

    comparison = pd.DataFrame(rows)

    # подсветка лучшего значения в каждой числовой колонке
    def highlight_best(s):
        try:
            numeric = pd.to_numeric(s, errors='coerce')
            is_best = numeric == numeric.max()
            return [
                'background-color: #dcfce7; color: #166534; font-weight: 600;' if v else ''
                for v in is_best
            ]
        except Exception:
            return ['' for _ in s]

    numeric_cols = ['ROC-AUC', 'Precision', 'Recall', 'F1-score', 'Accuracy']
    styled = comparison.style.apply(highlight_best, subset=numeric_cols)

    st.subheader("Сводная таблица метрик")
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # только обученные модели (без dummy) для графиков
    models_only = comparison[comparison['Модель'] != 'DummyClassifier (базовая линия)']

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("ROC-AUC")
        fig = px.bar(
            models_only.sort_values('ROC-AUC'),
            x='ROC-AUC', y='Модель', orientation='h',
            text='ROC-AUC', color_discrete_sequence=['#003087']
        )
        fig.update_traces(texttemplate='%{text:.3f}', textposition='outside')
        fig.update_layout(
            height=280, showlegend=False,
            margin=dict(l=0, r=50, t=10, b=0),
            xaxis_range=[0, 1.05]
        )
        if dummy_f1 is not None:
            fig.add_vline(x=0.5, line_dash='dash', line_color='gray',
                          annotation_text='baseline AUC=0.5')
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("F1-score")
        fig = px.bar(
            models_only.sort_values('F1-score'),
            x='F1-score', y='Модель', orientation='h',
            text='F1-score', color_discrete_sequence=['#1a56db']
        )
        fig.update_traces(texttemplate='%{text:.3f}', textposition='outside')
        fig.update_layout(
            height=280, showlegend=False,
            margin=dict(l=0, r=50, t=10, b=0),
            xaxis_range=[0, 1.05]
        )
        if dummy_f1 is not None:
            fig.add_vline(x=dummy_f1, line_dash='dash', line_color='gray',
                          annotation_text=f'baseline F1={dummy_f1:.3f}')
        st.plotly_chart(fig, use_container_width=True)

    # радар-диаграмма для сравнения моделей по всем метрикам сразу
    st.subheader("Радар-диаграмма")
    categories = ['ROC-AUC', 'Precision', 'Recall', 'F1-score', 'Accuracy']
    colors = ['#003087', '#166534', '#92400e', '#1d4ed8', '#15803d', '#b45309', '#6d28d9']

    fig_radar = go.Figure()
    for i, (_, row) in enumerate(models_only.iterrows()):
        vals = [row[c] for c in categories]
        vals.append(vals[0])
        fig_radar.add_trace(go.Scatterpolar(
            r=vals,
            theta=categories + [categories[0]],
            fill='toself',
            name=row['Модель'],
            line_color=colors[i % len(colors)],
            fillcolor=colors[i % len(colors)],
            opacity=0.2
        ))

    fig_radar.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        showlegend=True,
        height=420,
        margin=dict(l=40, r=40, t=30, b=30)
    )
    st.plotly_chart(fig_radar, use_container_width=True)

    # диагностические графики — загружаем сохранённые PNG из папки models
    st.subheader("Диагностические графики")
    st.markdown(
        "ROC-кривые, матрицы ошибок и Precision-Recall кривые, "
        "построенные при обучении каждой модели."
    )

    diag_files = [
        ("Логистическая регрессия", "logistic_regression_diagnostics.png"),
        ("Дерево решений",          "decision_tree_diagnostics.png"),
        ("Случайный лес",           "random_forest_diagnostics.png"),
    ]

    for model_name, fname in diag_files:
        path = os.path.join(MODELS_DIR, fname)
        if os.path.exists(path):
            with st.expander(f"Диагностика: {model_name}"):
                st.image(path, use_container_width=True)
        else:
            st.caption(f"График {fname} не найден — выполните обучение модели.")

    # структура дерева решений
    tree_path = os.path.join(MODELS_DIR, 'decision_tree_structure.png')
    if os.path.exists(tree_path):
        with st.expander("Структура дерева решений (глубина до 3)"):
            st.image(tree_path, use_container_width=True)

    # итоговый вывод о лучшей модели
    best = models_only.loc[models_only['F1-score'].idxmax()]

    st.markdown(f"""
    <div class="info-box">
        <h3>Рекомендуемая модель: {best['Модель']}</h3>
        <p>
            ROC-AUC: <b>{best['ROC-AUC']:.4f}</b> &nbsp;|&nbsp;
            F1-score: <b>{best['F1-score']:.4f}</b> &nbsp;|&nbsp;
            Precision: <b>{best['Precision']:.4f}</b> &nbsp;|&nbsp;
            Recall: <b>{best['Recall']:.4f}</b>
            {f"&nbsp;|&nbsp; Улучшение vs baseline: <b>{best['Улучшение vs Baseline']}</b>" if dummy_f1 else ""}
        </p>
    </div>
    """, unsafe_allow_html=True)