# логистическая регрессия с кросс-валидацией и pipeline
# изменения vs предыдущей версии:
# 1. используется sklearn pipeline (scaler + модель едины)
# 2. убраны абсолютные пути — используется config.py
# 3. gridsearchcv, кросс-валидация, dummyclassifier — сохранены
# 4. сохраняется pipeline целиком (не нужен отдельный scaler.pkl)

import pandas as pd
import numpy as np
import joblib
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import logging
import os
import sys
import warnings
warnings.filterwarnings('ignore')

# ml-скрипты лежат в diplom/, config.py — в diplom/app/
# добавляем diplom/app/ в путь для импорта config
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))   # .../diplom
APP_DIR    = os.path.join(SCRIPT_DIR, "app")              # .../diplom/app
sys.path.insert(0, APP_DIR)
from config import DATA_DIR, MODELS_DIR

from sklearn.model_selection import (
    train_test_split,
    GridSearchCV,
    StratifiedKFold,
    cross_validate
)
from sklearn.linear_model import LogisticRegression
from sklearn.dummy import DummyClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    classification_report, confusion_matrix,
    roc_auc_score, roc_curve, precision_recall_curve,
    f1_score, precision_score, recall_score, accuracy_score
)

# настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(DATA_DIR, "logistic_regression.log"), encoding="utf-8"
        ),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("logistic_regression")

log.info("=" * 60)
log.info("ЭТАП 5.1: ЛОГИСТИЧЕСКАЯ РЕГРЕССИЯ (С КРОСС-ВАЛИДАЦИЕЙ)")
log.info("=" * 60)

# загрузка данных
log.info("\n1. Загрузка данных...")

X_path        = os.path.join(DATA_DIR, "X_features.csv")
y_path        = os.path.join(DATA_DIR, "y_target.csv")
features_path = os.path.join(DATA_DIR, "feature_columns.txt")

X = pd.read_csv(X_path)
y = pd.read_csv(y_path).values.ravel()

with open(features_path, 'r', encoding='utf-8') as f:
    feature_names = [line.strip() for line in f.readlines()]

log.info(f"   Загружено: X shape {X.shape}, y shape {y.shape}")

# удаление признаков с утечкой данных
log.info("\n2. Проверка на утечку данных (data leakage)...")

# признаки, вычисляемые из целевой переменной — удаляем!
# supplier_terminated_share уже исключён на этапе 04_prepare_ml_dataset.py
# has_termination_doc удаляем здесь — создаётся только для расторгнутых контрактов
leakage_features = ["has_termination_doc"]
# interaction features используются только логрег — для неё оставляем все

for feature in leakage_features:
    if feature in X.columns:
        X = X.drop(columns=[feature])
        feature_names = [f for f in feature_names if f != feature]
        log.warning(f"⚠️ Удалён признак с утечкой: {feature}")

log.info(f"   ✅ Признаков после удаления утечек: {len(feature_names)}")

# анализ дисбаланса классов
log.info("\n3. Анализ распределения классов:")

class_dist = pd.Series(y).value_counts().sort_index()
balance_ratio = class_dist[1] / class_dist[0]
log.info(f"   Успешно (0):     {class_dist[0]} ({class_dist[0]/len(y)*100:.2f}%)")
log.info(f"   Расторгнуто (1): {class_dist[1]} ({class_dist[1]/len(y)*100:.2f}%)")
log.info(f"   Коэффициент дисбаланса: 1:{1/balance_ratio:.1f}")

# разделение на train/test
log.info("\n4. Разделение данных (70/30, stratify)...")

X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=0.30,
    random_state=42,
    stratify=y,
    shuffle=True
)

log.info(f"   Обучающая выборка: {X_train.shape}")
log.info(f"   Тестовая выборка:  {X_test.shape}")
log.info(f"   Доля расторжений в train: {y_train.mean()*100:.2f}%")
log.info(f"   Доля расторжений в test:  {y_test.mean()*100:.2f}%")

# baseline: dummyclassifier
log.info("\n5. Базовая модель (DummyClassifier — бейзлайн)...")

dummy_pipe = Pipeline([
    ('scaler', StandardScaler()),
    ('clf', DummyClassifier(strategy='most_frequent', random_state=42))
])
dummy_pipe.fit(X_train, y_train)

y_dummy_pred  = dummy_pipe.predict(X_test)
y_dummy_proba = dummy_pipe.predict_proba(X_test)[:, 1]

dummy_f1        = f1_score(y_test, y_dummy_pred, zero_division=0)
dummy_roc_auc   = roc_auc_score(y_test, y_dummy_proba)
dummy_precision = precision_score(y_test, y_dummy_pred, zero_division=0)
dummy_recall    = recall_score(y_test, y_dummy_pred, zero_division=0)

log.info(f"   📊 DummyClassifier (strategy=most_frequent):")
log.info(f"      F1-score:  {dummy_f1:.4f}")
log.info(f"      ROC-AUC:   {dummy_roc_auc:.4f}")
log.info(f"      Precision: {dummy_precision:.4f}")
log.info(f"      Recall:    {dummy_recall:.4f}")
log.info(f"   ⚠️ Модель должна быть ЛУЧШЕ этого базового уровня!")

# gridsearchcv: подбор гиперпараметров
# pipeline(StandardScaler + LogisticRegression):
# - масштабирование обязательно для логрег
# - pipeline гарантирует: scaler.fit только на обучающих фолдах
# - параметры через clf__<param>
log.info("\n6. GridSearchCV: поиск оптимальных гиперпараметров...")

pipe = Pipeline([
    ('scaler', StandardScaler()),
    ('clf', LogisticRegression(max_iter=5000, random_state=42))
])

param_grid = {
    'clf__C':            [0.001, 0.01, 0.1, 1, 10],  # Обратная регуляризация
    'clf__class_weight': [None, 'balanced'],          # Балансировка классов
    'clf__solver':       ['lbfgs', 'liblinear'],      # Солвер
    'clf__penalty':      ['l2']                       # Тип регуляризации
}

cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

gs = GridSearchCV(
    pipe,
    param_grid=param_grid,
    scoring='f1',   # Оптимизируем по F1 (баланс precision/recall)
    cv=cv,
    n_jobs=-1,
    verbose=1
)

log.info("   ⏳ Выполняется поиск (это может занять минуту)...")
gs.fit(X_train, y_train)

log.info(f"\n   ✅ GridSearch завершён!")
log.info(f"   🏆 Лучшие параметры: {gs.best_params_}")
log.info(f"   📈 Лучший F1 (CV):   {gs.best_score_:.4f}")

best_pipeline = gs.best_estimator_

# оценка на тестовой выборке
log.info("\n7. Оценка лучшей модели на тестовой выборке...")

y_pred  = best_pipeline.predict(X_test)
y_proba = best_pipeline.predict_proba(X_test)[:, 1]

roc_auc   = roc_auc_score(y_test, y_proba)
precision = precision_score(y_test, y_pred)
recall    = recall_score(y_test, y_pred)
f1        = f1_score(y_test, y_pred)
accuracy  = accuracy_score(y_test, y_pred)

log.info(f"\n   📊 ИТОГОВЫЕ МЕТРИКИ (тест):")
log.info(f"      F1-score:  {f1:.4f} (✅ базовая: {dummy_f1:.4f})")
log.info(f"      ROC-AUC:   {roc_auc:.4f}")
log.info(f"      Precision: {precision:.4f}")
log.info(f"      Recall:    {recall:.4f}")
log.info(f"      Accuracy:  {accuracy:.4f}")

if f1 > dummy_f1:
    improvement = roc_auc - dummy_roc_auc  # сравниваем по auc — f1 dummy=0 даёт деление на ~0
    log.info(f"   улучшение auc vs baseline: +{improvement:.4f} ({dummy_roc_auc:.4f} → {roc_auc:.4f})")
else:
    log.warning("   ⚠️ ВНИМАНИЕ: Модель хуже бейзлайна! Требуется переосмысление.")

# кросс-валидация на обучающей выборке
log.info("\n8. Кросс-валидация лучшего пайплайна (5-fold на train)...")

scoring_metrics = ['f1', 'roc_auc', 'precision', 'recall', 'accuracy']
cv_results = cross_validate(
    best_pipeline,
    X_train, y_train,
    cv=cv,
    scoring=scoring_metrics,
    return_train_score=False
)

for metric in scoring_metrics:
    scores = cv_results[f'test_{metric}']
    log.info(f"   {metric.upper():10s}: {scores.mean():.4f} ± {scores.std():.4f}")

# интерпретация коэффициентов
log.info("\n9. Анализ коэффициентов модели...")

best_clf = best_pipeline.named_steps['clf']
intercept = best_clf.intercept_[0]
coef      = best_clf.coef_[0]

coef_df = pd.DataFrame({
    'Признак':                feature_names,
    'Коэффициент':            coef,
    'Абс_коэф':               np.abs(coef),
    'Вероятностный_множитель': np.exp(coef)   # odds ratio
}).sort_values('Абс_коэф', ascending=False)

log.info(f"\n   Intercept (базовый логит): {intercept:.4f}")
log.info(f"   Базовая вероятность:       {1/(1+np.exp(-intercept))*100:.2f}%")

log.info("\n   🔴 ТОП-10 ФАКТОРОВ, ПОВЫШАЮЩИХ РИСК:")
for _, row in coef_df[coef_df['Коэффициент'] > 0].head(10).iterrows():
    impact = (row['Вероятностный_множитель'] - 1) * 100
    log.info(f"      {row['Признак']:35s} | коэф={row['Коэффициент']:7.4f} | +{impact:.1f}%")

log.info("\n   🟢 ТОП-10 ФАКТОРОВ, СНИЖАЮЩИХ РИСК:")
for _, row in coef_df[coef_df['Коэффициент'] < 0].head(10).iterrows():
    impact = (1 - row['Вероятностный_множитель']) * 100
    log.info(f"      {row['Признак']:35s} | коэф={row['Коэффициент']:7.4f} | -{impact:.1f}%")

# матрица ошибок и classification report
log.info("\n10. Подробный отчёт классификации...")

cm = confusion_matrix(y_test, y_pred)
tn, fp, fn, tp = cm.ravel()

log.info(f"\n   Матрица ошибок:")
log.info(f"      True Negative:  {tn:5d} | False Positive: {fp:5d}")
log.info(f"      False Negative: {fn:5d} | True Positive:  {tp:5d}")

report = classification_report(
    y_test, y_pred,
    target_names=['Успешно (0)', 'Расторгнуто (1)'],
    digits=4
)
log.info(f"\n   Classification Report:\n{report}")

# сохранение результатов
log.info("\n11. Сохранение результатов...")
os.makedirs(MODELS_DIR, exist_ok=True)

# сохраняем Pipeline целиком (scaler + модель в одном файле)
# logistic_scaler.pkl больше не нужен — всё в pipeline
pipeline_path = os.path.join(MODELS_DIR, "logistic_regression_best.pkl")
joblib.dump(best_pipeline, pipeline_path)
log.info(f"   ✅ Pipeline: {pipeline_path}")

coef_path = os.path.join(MODELS_DIR, "logistic_coefficients.csv")
coef_df.to_csv(coef_path, index=False)
log.info(f"   ✅ Коэффициенты: {coef_path}")

metrics_dict = {
    'model':            'LogisticRegression (best pipeline)',
    'best_params':      str(gs.best_params_),
    'cv_f1_mean':       gs.best_score_,
    'test_f1':          f1,
    'test_roc_auc':     roc_auc,
    'test_precision':   precision,
    'test_recall':      recall,
    'test_accuracy':    accuracy,
    'dummy_f1':         dummy_f1,
    'improvement_vs_dummy': roc_auc - dummy_roc_auc
}

metrics_df = pd.DataFrame([metrics_dict])
metrics_path = os.path.join(MODELS_DIR, "logistic_metrics.csv")
metrics_df.to_csv(metrics_path, index=False)
log.info(f"   ✅ Метрики: {metrics_path}")

# визуализация
log.info("\n12. Построение графиков...")

plt.style.use('ggplot')
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle('Логистическая регрессия: Диагностика', fontsize=16, fontweight='bold')

# roc-кривая
ax = axes[0, 0]
fpr, tpr, _ = roc_curve(y_test, y_proba)
ax.plot(fpr, tpr, lw=2.5, label=f'LogReg (AUC={roc_auc:.3f})')
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
precision_curve, recall_curve, _ = precision_recall_curve(y_test, y_proba)
ax.plot(recall_curve, precision_curve, lw=2.5, label=f'LogReg (F1={f1:.3f})')
ax.axhline(y=dummy_precision, color='red', linestyle='--', lw=1.5, label='Dummy')
ax.set_xlabel('Recall')
ax.set_ylabel('Precision')
ax.set_title('Precision-Recall')
ax.legend()
ax.grid(True, alpha=0.3)

# топ коэффициентов (odds ratio)
ax = axes[1, 1]
top15 = coef_df.head(15).sort_values('Коэффициент')
colors = ['#991b1b' if x > 0 else '#166534' for x in top15['Коэффициент']]
ax.barh(range(len(top15)), top15['Коэффициент'], color=colors)
ax.set_yticks(range(len(top15)))
ax.set_yticklabels(top15['Признак'], fontsize=9)
ax.axvline(x=0, color='black', linewidth=0.7)
ax.set_xlabel('Коэффициент (лог. шансы)')
ax.set_title('Топ-15 факторов по влиянию')
ax.grid(True, alpha=0.3, axis='x')

plt.tight_layout()
plot_path = os.path.join(MODELS_DIR, 'logistic_regression_diagnostics.png')
plt.savefig(plot_path, dpi=150)
log.info(f"   ✅ График: {plot_path}")
plt.close()

# итоги
log.info("\n" + "=" * 60)
log.info("ИТОГИ ЛОГИСТИЧЕСКОЙ РЕГРЕССИИ")
log.info("=" * 60)
log.info(f"✅ F1-score (тест):  {f1:.4f}")
log.info(f"✅ ROC-AUC:          {roc_auc:.4f}")
log.info(f"✅ Precision/Recall: {precision:.4f} / {recall:.4f}")
log.info(f"улучшение auc vs baseline: +{roc_auc - dummy_roc_auc:.4f}")
log.info(f"\n✅ ЭТАП 5.1 ЗАВЕРШЁН — Pipeline сохранён в {pipeline_path}")
log.info("=" * 60)