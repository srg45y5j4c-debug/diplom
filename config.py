# config.py
import os

# пути к данным
# структура проекта:
#   diplom/
#   ├── app/          <- здесь лежит config.py
#   │   ├── pages/
#   │   └── utils/
#   └── data/         <- здесь бд, csv и models/
APP_DIR    = os.path.dirname(os.path.abspath(__file__))
BASE_DIR   = os.path.dirname(APP_DIR)
DATA_DIR   = os.path.join(BASE_DIR, "data")
MODELS_DIR = os.path.join(DATA_DIR, "models")
DB_PATH    = os.path.join(DATA_DIR, "gosplan_construction.db")

# настройки приложения
APP_TITLE   = "RiskAnalyzer | Управление рисками исполнения госконтрактов"
APP_ICON    = "🏛"   # стандартный unicode — работает в streamlit
PAGE_LAYOUT = "wide"

# цветовая палитра для государственного сектора
COLORS = {
    'primary':       '#003087',
    'primary_light': '#1a56db',
    'primary_bg':    '#e8f0fe',
    'success':       '#166534',
    'success_bg':    '#dcfce7',
    'warning':       '#92400e',
    'warning_bg':    '#fef3c7',
    'danger':        '#991b1b',
    'danger_bg':     '#fee2e2',
    'gray_dark':     '#1f2937',
    'gray_mid':      '#6b7280',
    'gray_light':    '#f3f4f6',
    'border':        '#d1d5db',
    'white':         '#ffffff',
}