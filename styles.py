# utils/styles.py
import streamlit as st

def apply_custom_styles():
    """Применение единых CSS-стилей в светлой государственной теме."""
    st.markdown("""
    <style>
        /* =====================================================
           ОБЩИЙ ФОН И ТИПОГРАФИКА
        ===================================================== */
        .main .block-container {
            background-color: #f8fafc;
            padding-top: 1.5rem;
        }

        h1, h2, h3 {
            color: #003087;
            font-weight: 600;
        }

        /* =====================================================
           МЕТРИЧЕСКИЕ КАРТОЧКИ
        ===================================================== */
        .metric-card {
            background-color: #ffffff;
            border: 1px solid #d1d5db;
            border-left: 4px solid #003087;
            border-radius: 8px;
            padding: 18px 20px;
            text-align: left;
        }
        .metric-card h3 {
            font-size: 0.82rem;
            color: #6b7280;
            margin: 0 0 6px 0;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .metric-card h2 {
            font-size: 1.8rem;
            color: #003087;
            margin: 0;
            font-weight: 700;
        }
        .metric-card .metric-sub {
            font-size: 0.78rem;
            color: #6b7280;
            margin-top: 4px;
        }

        /* =====================================================
           ИНДИКАТОРЫ УРОВНЯ РИСКА
        ===================================================== */
        .risk-high {
            background-color: #fee2e2;
            border: 1px solid #fca5a5;
            border-left: 5px solid #991b1b;
            padding: 16px 20px;
            border-radius: 8px;
            color: #7f1d1d;
            font-weight: 600;
            text-align: center;
        }
        .risk-medium {
            background-color: #fef3c7;
            border: 1px solid #fcd34d;
            border-left: 5px solid #92400e;
            padding: 16px 20px;
            border-radius: 8px;
            color: #78350f;
            font-weight: 600;
            text-align: center;
        }
        .risk-low {
            background-color: #dcfce7;
            border: 1px solid #86efac;
            border-left: 5px solid #166534;
            padding: 16px 20px;
            border-radius: 8px;
            color: #14532d;
            font-weight: 600;
            text-align: center;
        }

        /* =====================================================
           ИНФОРМАЦИОННЫЕ БЛОКИ
        ===================================================== */
        .info-box {
            background-color: #e8f0fe;
            border: 1px solid #a8c0f0;
            border-left: 5px solid #003087;
            border-radius: 8px;
            padding: 16px 20px;
            margin: 12px 0;
            color: #1e3a8a;
        }
        .info-box h3 {
            color: #003087;
            margin: 0 0 8px 0;
            font-size: 1rem;
        }
        .info-box ul {
            margin: 0;
            padding-left: 1.2rem;
        }

        /* =====================================================
           КАРТОЧКИ МОДЕЛЕЙ
        ===================================================== */
        .model-card {
            background-color: #ffffff;
            padding: 18px 20px;
            border-radius: 8px;
            border: 1px solid #d1d5db;
            margin-bottom: 12px;
        }
        .model-card.best {
            border: 2px solid #003087;
            background-color: #f0f5ff;
        }

        /* =====================================================
           КНОПКИ
        ===================================================== */
        .stButton > button {
            background-color: #003087;
            color: #ffffff;
            border: none;
            padding: 10px 22px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 0.9rem;
            transition: background-color 0.2s;
            width: 100%;
        }
        .stButton > button:hover {
            background-color: #1a3a70;
        }
        .stButton > button:active {
            background-color: #002060;
        }

        /* =====================================================
           БОКОВАЯ ПАНЕЛЬ
        ===================================================== */
        [data-testid="stSidebar"] {
            background-color: #f0f4f8;
            border-right: 1px solid #d1d5db;
        }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: #003087;
        }

        /* =====================================================
           ТАБЛИЦЫ
        ===================================================== */
        .stDataFrame {
            font-size: 13px;
        }

        /* =====================================================
           СКРЫТИЕ ЛИШНИХ ЭЛЕМЕНТОВ STREAMLIT
        ===================================================== */
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        .stDeployButton { display: none; }
        [data-testid="stSidebarNav"] { display: none; }
    </style>
    """, unsafe_allow_html=True)