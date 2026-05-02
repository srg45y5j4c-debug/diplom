# 05_04_xgboost.py
# xgboost для бинарной классификации риска расторжения контракта.
# структура идентична остальным ml-скриптам (логрег, дерево, rf):
# pipeline + gridsearchcv + stratifiedkfold + dummyclassifier + cross_validate

import pandas as pd
import numpy as np
import joblib
import matplotlib.pyplot as plt
import seaborn as sns
import logging
import os
import sys
import warnings
warnings.filterwarnings('ignore')
# подавляем предупреждение sklearn о delayed/Parallel в python 3.14
warnings.filterwarnings('ignore', message='.*delayed.*', category=UserWarning)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR    = os.path.join(SCRIPT_DIR, "app")
sys.path.insert(0, APP_DIR)
from config import DATA_DIR, MODELS_DIR

from sklearn.model_selection import (
    train_test_split,
    GridSearchCV,
    StratifiedKFold,
    cross_validate
)
from sklearn.dummy import DummyClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    classification_report, confusion_matrix,
    roc_auc_score, roc_curve, precision_recall_curve,
    f1_score, precision_score, recall_score, accuracy_score
)

try:
    from xgboost import XGBClassifier
except ImportError:
    print("xgboost не установлен. установите: pip install xgboost")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(DATA_DIR, "xgboost.log"), encoding="utf-8"
        ),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("xgboost")

log.info("=" * 60)
log.info("ЭТАП 5.4: XGBOOST (С КРОСС-ВАЛИДАЦИЕЙ)")
log.info("=" * 60)

# загрузка данных
log.info("\n1. загрузка данных...")

X = pd.read_csv(os.path.join(DATA_DIR, "X_features.csv"))
y = pd.read_csv(os.path.join(DATA_DIR, "y_target.csv")).values.ravel()

with open(os.path.join(DATA_DIR, "feature_columns.txt"), "r", encoding="utf-8") as f:
    feature_names = [line.strip() for line in f.readlines()]

log.info(f"   загружено: X shape {X.shape}, y shape {y.shape}")

# удаление признаков с утечкой данных
log.info("\n2. проверка на утечку данных...")

# supplier_terminated_share уже исключён на этапе 04_prepare_ml_dataset.py
# has_termination_doc удаляем здесь — создаётся только для расторгнутых контрактов
leakage_features = [
    "has_termination_doc",
    # interaction features убираем — деревья и бустинг находят взаимодействия сами
    "penalty_x_experience", "price_x_duration", "penalty_x_price",
]
for feat in leakage_features:
    if feat in X.columns:
        X = X.drop(columns=[feat])
        feature_names = [f for f in feature_names if f != feat]
        log.warning(f"удалён признак с утечкой: {feat}")

log.info(f"   признаков после удаления: {len(feature_names)}")

# анализ дисбаланса классов
log.info("\n3. распределение классов:")
dist = pd.Series(y).value_counts().sort_index()
log.info(f"   успешно (0):     {dist[0]} ({dist[0]/len(y)*100:.2f}%)")
log.info(f"   расторгнуто (1): {dist[1]} ({dist[1]/len(y)*100:.2f}%)")

# вычисляем scale_pos_weight для xgboost — аналог class_weight='balanced'
# отношение числа отрицательных примеров к положительным
scale_pos_weight = int(dist[0] / dist[1])
log.info(f"   scale_pos_weight: {scale_pos_weight} (используется вместо class_weight)")

# разделение на train/test
log.info("\n4. разделение данных (70/30, stratify)...")

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.30, random_state=42, stratify=y, shuffle=True
)
log.info(f"   обучающая: {X_train.shape}, тестовая: {X_test.shape}")
log.info(f"   доля расторжений в train: {y_train.mean()*100:.2f}%")

# baseline: dummyclassifier
log.info("\n5. базовая модель (dummyclassifier)...")

dummy_pipe = Pipeline([
    ('scaler', StandardScaler()),
    ('clf',    DummyClassifier(strategy='most_frequent', random_state=42))
])
dummy_pipe.fit(X_train, y_train)
y_dummy_pred  = dummy_pipe.predict(X_test)
y_dummy_proba = dummy_pipe.predict_proba(X_test)[:, 1]

dummy_f1      = f1_score(y_test, y_dummy_pred, zero_division=0)
dummy_roc_auc = roc_auc_score(y_test, y_dummy_proba)
dummy_prec    = precision_score(y_test, y_dummy_pred, zero_division=0)

log.info(f"   dummy f1={dummy_f1:.4f}, auc={dummy_roc_auc:.4f}")

# gridsearchcv
# xgboost не требует масштабирования, но pipeline используем
# для единообразия сохранения и инференса (один pkl-файл)
# параметры через clf__<param>
log.info("\n6. gridsearchcv: поиск гиперпараметров...")

pipe = Pipeline([
    ('scaler', StandardScaler()),
    ('clf', XGBClassifier(
        objective='binary:logistic',
        eval_metric='logloss',
        random_state=42,
        n_jobs=-1,
        verbosity=0,
        scale_pos_weight=scale_pos_weight   # балансировка классов
    ))
])

param_grid = {
    'clf__n_estimators':  [100, 300, 500],
    'clf__max_depth':     [3, 5, 7],
    'clf__learning_rate': [0.05, 0.1, 0.2],
    'clf__subsample':     [0.8, 1.0],
    'clf__colsample_bytree': [0.8, 1.0],
}

cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

gs = GridSearchCV(
    pipe,
    param_grid=param_grid,
    scoring='f1',
    cv=cv,
    n_jobs=-1,
    verbose=1
)

log.info("   выполняется поиск (может занять несколько минут)...")
gs.fit(X_train, y_train)

log.info(f"   лучшие параметры: {gs.best_params_}")
log.info(f"   лучший f1 (cv):   {gs.best_score_:.4f}")

best_pipeline = gs.best_estimator_

# оценка на тестовой выборке
log.info("\n7. оценка на тестовой выборке...")

y_pred  = best_pipeline.predict(X_test)
y_proba = best_pipeline.predict_proba(X_test)[:, 1]

roc_auc  = roc_auc_score(y_test, y_proba)
prec     = precision_score(y_test, y_pred)
rec      = recall_score(y_test, y_pred)
f1       = f1_score(y_test, y_pred)
accuracy = accuracy_score(y_test, y_pred)

log.info(f"   f1-score:  {f1:.4f} (baseline: {dummy_f1:.4f})")
log.info(f"   roc-auc:   {roc_auc:.4f}")
log.info(f"   precision: {prec:.4f}")
log.info(f"   recall:    {rec:.4f}")
log.info(f"   accuracy:  {accuracy:.4f}")

improvement = roc_auc - dummy_roc_auc  # сравниваем по auc — f1 dummy=0 даёт деление на ~0
if f1 > dummy_f1:
    log.info(f"   улучшение vs baseline: +{improvement:.1f}%")
else:
    log.warning("   модель хуже baseline — пересмотрите признаки")

# кросс-валидация на train
log.info("\n8. кросс-валидация (5-fold на train)...")

cv_results = cross_validate(
    best_pipeline, X_train, y_train,
    cv=cv,
    scoring=['f1', 'roc_auc', 'precision', 'recall', 'accuracy'],
    return_train_score=False
)
for metric in ['f1', 'roc_auc', 'precision', 'recall', 'accuracy']:
    scores = cv_results[f'test_{metric}']
    log.info(f"   {metric.upper():10s}: {scores.mean():.4f} ± {scores.std():.4f}")

# матрица ошибок и отчёт
log.info("\n9. classification report...")

cm = confusion_matrix(y_test, y_pred)
tn, fp, fn, tp = cm.ravel()
log.info(f"   tn={tn} fp={fp} fn={fn} tp={tp}")
log.info(f"\n{classification_report(y_test, y_pred, target_names=['успешно','расторгнуто'], digits=4)}")

# permutation importance
# xgboost имеет встроенную важность (gain, weight, cover),
# но permutation importance честнее — не смещена к высококардинальным признакам
log.info("\n10. permutation importance...")

X_test_tr = best_pipeline.named_steps['scaler'].transform(X_test)
best_clf  = best_pipeline.named_steps['clf']

perm = permutation_importance(
    best_clf, X_test_tr, y_test,
    n_repeats=10, random_state=42, n_jobs=-1, scoring='f1'
)

imp_df = pd.DataFrame({
    'Признак':         feature_names,
    'Важность (perm)': perm.importances_mean,
    'Std (perm)':      perm.importances_std,
    'Важность (gain)': best_clf.feature_importances_   # встроенная для справки
}).sort_values('Важность (perm)', ascending=False)

log.info("\n   топ-10 по permutation importance:")
for _, row in imp_df.head(10).iterrows():
    log.info(
        f"   {row['Признак']:35s}: "
        f"perm={row['Важность (perm)']:.4f} ± {row['Std (perm)']:.4f} | "
        f"gain={row['Важность (gain)']:.4f}"
    )

# сохранение результатов
log.info("\n11. сохранение...")
os.makedirs(MODELS_DIR, exist_ok=True)

pipeline_path = os.path.join(MODELS_DIR, "xgboost_best.pkl")
joblib.dump(best_pipeline, pipeline_path)
log.info(f"   pipeline: {pipeline_path}")

imp_path = os.path.join(MODELS_DIR, "xgboost_feature_importance.csv")
imp_df.to_csv(imp_path, index=False)
log.info(f"   важность признаков: {imp_path}")

metrics_df = pd.DataFrame([{
    'model':                 'XGBoost (best pipeline)',
    'best_params':           str(gs.best_params_),
    'cv_f1_mean':            gs.best_score_,
    'test_f1':               f1,
    'test_roc_auc':          roc_auc,
    'test_precision':        prec,
    'test_recall':           rec,
    'test_accuracy':         accuracy,
    'dummy_f1':              dummy_f1,
    'improvement_vs_dummy':  improvement
}])
metrics_path = os.path.join(MODELS_DIR, "xgboost_metrics.csv")
metrics_df.to_csv(metrics_path, index=False)
log.info(f"   метрики: {metrics_path}")

# визуализация
log.info("\n12. графики...")

plt.style.use('ggplot')
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle('XGBoost: диагностика', fontsize=16, fontweight='bold')

# roc-кривая
ax = axes[0, 0]
fpr, tpr, _ = roc_curve(y_test, y_proba)
ax.plot(fpr, tpr, lw=2.5, label=f'XGBoost (AUC={roc_auc:.3f})')
fpr_d, tpr_d, _ = roc_curve(y_test, y_dummy_proba)
ax.plot(fpr_d, tpr_d, lw=1.5, linestyle='--', label=f'Dummy (AUC={dummy_roc_auc:.3f})')
ax.plot([0, 1], [0, 1], 'k--', lw=1, alpha=0.3)
ax.set_xlabel('False Positive Rate')
ax.set_ylabel('True Positive Rate')
ax.set_title('ROC-кривая')
ax.legend(loc='lower right')
ax.grid(True, alpha=0.3)

# матрица ошибок
ax = axes[0, 1]
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=ax, cbar=False,
            xticklabels=['Успех', 'Расторжение'],
            yticklabels=['Успех', 'Расторжение'])
ax.set_title('Матрица ошибок')
ax.set_ylabel('Факт')
ax.set_xlabel('Прогноз')

# precision-recall
ax = axes[1, 0]
prec_curve, rec_curve, _ = precision_recall_curve(y_test, y_proba)
ax.plot(rec_curve, prec_curve, lw=2.5, label=f'XGBoost (F1={f1:.3f})')
ax.axhline(y=dummy_prec, color='red', linestyle='--', lw=1.5, label='Dummy')
ax.set_xlabel('Recall')
ax.set_ylabel('Precision')
ax.set_title('Precision-Recall')
ax.legend()
ax.grid(True, alpha=0.3)

# permutation importance топ-15
ax = axes[1, 1]
top15 = imp_df.head(15).sort_values('Важность (perm)')
ax.barh(top15['Признак'], top15['Важность (perm)'],
        xerr=top15['Std (perm)'], capsize=3, color='#1e40af')
ax.set_xlabel('снижение f1 при перемешивании')
ax.set_title('топ-15: permutation importance')
ax.grid(True, alpha=0.3, axis='x')

plt.tight_layout()
plot_path = os.path.join(MODELS_DIR, 'xgboost_diagnostics.png')
plt.savefig(plot_path, dpi=150)
log.info(f"   график: {plot_path}")
plt.close()

log.info("\n" + "=" * 60)
log.info("ИТОГИ XGBOOST")
log.info("=" * 60)
log.info(f"f1-score:  {f1:.4f}")
log.info(f"roc-auc:   {roc_auc:.4f}")
log.info(f"precision: {prec:.4f}")
log.info(f"recall:    {rec:.4f}")
log.info(f"улучшение auc vs baseline: +{improvement:.4f}")
log.info(f"pipeline сохранён: {pipeline_path}")
log.info("=" * 60)