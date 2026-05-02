# utils/data_loader.py
import sqlite3
import pandas as pd
import streamlit as st
import joblib
import os
from config import DB_PATH, MODELS_DIR


def _safe_float(d, *keys):
    """читает первое найденное числовое значение из словаря по списку ключей"""
    for k in keys:
        if k in d:
            try:
                return float(d[k])
            except Exception:
                pass
    return 0.0


def _best_row(csv_path):
    """возвращает строку с лучшим f1 из csv-файла метрик"""
    df = pd.read_csv(csv_path)
    f1_col = 'test_f1' if 'test_f1' in df.columns else 'f1'
    return df.sort_values(f1_col, ascending=False).iloc[0].to_dict()


@st.cache_resource
def load_models():
    """
    загружает все обученные pipeline-модели из папки data/models.
    каждый .pkl содержит полный pipeline (scaler + классификатор),
    что исключает необходимость отдельного сохранения scaler.
    результат кешируется в рамках сессии streamlit.
    """
    models = {}
    try:
        entries = [
            (
                'logistic',
                'logistic_regression_best.pkl',
                'logistic_metrics.csv',
                'Логистическая регрессия',
                '#003087',
            ),
            (
                'decision_tree',
                'decision_tree_best.pkl',
                'decision_tree_metrics.csv',
                'Дерево решений',
                '#166534',
            ),
            (
                'random_forest',
                'random_forest_best.pkl',
                'random_forest_metrics.csv',
                'Случайный лес',
                '#92400e',
            ),
            (
                'xgboost',
                'xgboost_best.pkl',
                'xgboost_metrics.csv',
                'XGBoost',
                '#1d4ed8',
            ),
            (
                'lightgbm',
                'lightgbm_best.pkl',
                'lightgbm_metrics.csv',
                'LightGBM',
                '#15803d',
            ),
            (
                'catboost',
                'catboost_best.pkl',
                'catboost_metrics.csv',
                'CatBoost',
                '#b45309',
            ),
            (
                'neural_network',
                'neural_network_best.pkl',
                'neural_network_metrics.csv',
                'Нейронная сеть (MLP)',
                '#6d28d9',
            ),
        ]

        for key, pkl_name, csv_name, label, color in entries:
            pkl_path = os.path.join(MODELS_DIR, pkl_name)
            csv_path = os.path.join(MODELS_DIR, csv_name)

            if not os.path.exists(pkl_path) or not os.path.exists(csv_path):
                continue

            models[key] = {
                'pipeline': joblib.load(pkl_path),
                'name':     label,
                'color':    color,
                'metrics':  _best_row(csv_path),
            }

        return models

    except Exception as e:
        st.error(f"Ошибка загрузки моделей: {e}")
        return {}