# pages/__init__.py
from ._01_dashboard import render_dashboard
from ._02_prediction import render_prediction
from ._03_model_comparison import render_model_comparison
from ._04_supplier_analysis import render_supplier_analysis
from ._05_interpretation import render_interpretation

__all__ = [
    'render_dashboard',
    'render_prediction', 
    'render_model_comparison',
    'render_supplier_analysis',
    'render_interpretation'
]