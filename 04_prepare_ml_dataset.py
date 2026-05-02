# 04_prepare_ml_dataset.py
# формирование ml-датасета из базы данных.
# объединяет контракты, процедуры и характеристики поставщиков.
# сохраняет x_features.csv, y_target.csv и feature_columns.txt в data_dir.

import sqlite3
import pandas as pd
import numpy as np
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))
from config import DB_PATH, DATA_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(DATA_DIR, "create_ml_dataset.log"), encoding="utf-8"
        ),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("ml-dataset")

log.info("=" * 60)
log.info("ЭТАП 4: ФОРМИРОВАНИЕ ML-ДАТАСЕТА")
log.info(f"база данных: {DB_PATH}")
log.info("=" * 60)

conn = sqlite3.connect(DB_PATH)

# шаг 1: базовые данные из таблицы contracts
log.info("\n1. загрузка базовых данных из contracts...")

df = pd.read_sql_query("""
    SELECT
        reg_num,
        stage,
        is_terminated,
        price,
        region,
        customer_inn,
        suppliers_count,
        is_multi_supplier,
        CASE WHEN okpd2_csv LIKE '%41.%' THEN 1 ELSE 0 END AS is_buildings,
        CASE WHEN okpd2_csv LIKE '%42.%' THEN 1 ELSE 0 END AS is_infrastructure,
        CASE WHEN okpd2_csv LIKE '%43.%' THEN 1 ELSE 0 END AS is_specialized,
        julianday(COALESCE(exe_end, published_at)) - julianday(exe_start)
            AS contract_duration_days
    FROM contracts
    WHERE stage IN ('ET', 'EC')
      AND is_terminated IS NOT NULL
      AND price > 0
""", conn)

log.info(f"   загружено {len(df)} контрактов")

# шаг 2: агрегация признаков из процедур
log.info("\n2. агрегация признаков из procedures_flat...")

df_proc = pd.read_sql_query("""
    SELECT
        reg_num,
        MAX(has_penalty)                                   AS has_penalty,
        COUNT(CASE WHEN has_penalty = 1 THEN 1 END)        AS penalty_count,
        SUM(COALESCE(penalty_amount, 0))                   AS penalty_total,
        MAX(has_termination)                               AS has_termination_doc,
        COUNT(*)                                           AS procedures_count,
        GROUP_CONCAT(DISTINCT termination_reason_name)     AS termination_reasons
    FROM procedures_flat
    GROUP BY reg_num
""", conn)

log.info(f"   загружено {len(df_proc)} контрактов с процедурами")

# шаг 3: характеристики поставщиков
# важно: supplier_terminated_share вычисляется по всей истории поставщика.
# этот признак несёт риск утечки данных (data leakage) если поставщик
# входит одновременно в train и test — ml-скрипты удаляют его перед обучением.
log.info("\n3. расчёт характеристик поставщиков...")

df_supp = pd.read_sql_query("""
    WITH supplier_stats AS (
        SELECT
            cs.supplier_inn,
            COUNT(DISTINCT cs.reg_num)   AS supplier_total_contracts,
            AVG(c.is_terminated)         AS supplier_terminated_share,
            AVG(COALESCE(c.price, 0))    AS supplier_avg_price,
            COUNT(DISTINCT c.region)     AS supplier_regions_count,
            AVG(c.suppliers_count)       AS supplier_avg_suppliers
        FROM contract_suppliers cs
        JOIN contracts c ON cs.reg_num = c.reg_num
        WHERE c.stage IN ('ET', 'EC')
          AND c.is_terminated IS NOT NULL
        GROUP BY cs.supplier_inn
    )
    SELECT
        cs.reg_num,
        MAX(ss.supplier_total_contracts)  AS supplier_total_contracts,
        MAX(ss.supplier_terminated_share) AS supplier_terminated_share,
        MAX(ss.supplier_avg_price)        AS supplier_avg_price,
        MAX(ss.supplier_regions_count)    AS supplier_regions_count,
        MAX(ss.supplier_avg_suppliers)    AS supplier_avg_suppliers
    FROM contract_suppliers cs
    LEFT JOIN supplier_stats ss ON cs.supplier_inn = ss.supplier_inn
    GROUP BY cs.reg_num
""", conn)

log.info(f"   рассчитано для {len(df_supp)} контрактов")

conn.close()

# шаг 4: объединение всех признаков
log.info("\n4. объединение признаков...")

ml_df = df.copy()
ml_df = ml_df.merge(df_proc, on='reg_num', how='left')
ml_df = ml_df.merge(df_supp,  on='reg_num', how='left')
log.info(f"   размер после объединения: {ml_df.shape}")

# шаг 5: очистка данных
log.info("\n5. очистка данных...")

initial = len(ml_df)
ml_df = ml_df.drop_duplicates(subset=['reg_num'])
log.info(f"   удалено дубликатов: {initial - len(ml_df)}")

# удаляем контракты с нереальной длительностью
ml_df = ml_df[ml_df['contract_duration_days'].isna() | (ml_df['contract_duration_days'] >= 0)]
log.info(f"   после фильтра длительности: {len(ml_df)}")

log.info(f"\n   распределение целевой переменной:")
log.info(f"   {ml_df['is_terminated'].value_counts(dropna=False).to_dict()}")
log.info(f"   доля расторжений: {ml_df['is_terminated'].mean()*100:.2f}%")

# заполнение пропусков нулями для числовых признаков
numeric_fill = [
    'price', 'suppliers_count', 'contract_duration_days',
    'has_penalty', 'penalty_count', 'penalty_total',
    'procedures_count', 'has_termination_doc',
    'supplier_total_contracts', 'supplier_terminated_share',
    'supplier_avg_price', 'supplier_regions_count', 'supplier_avg_suppliers'
]
for col in numeric_fill:
    if col in ml_df.columns:
        ml_df[col] = ml_df[col].fillna(0)

binary_fill = ['is_buildings', 'is_infrastructure', 'is_specialized', 'is_multi_supplier']
for col in binary_fill:
    if col in ml_df.columns:
        ml_df[col] = ml_df[col].fillna(0).astype(int)

# шаг 6: обработка выбросов (winsorizing на 1-99 перцентиль)
log.info("\n6. обработка выбросов...")

def cap_outliers(df, col, lower=0.01, upper=0.99):
    if col not in df.columns:
        return
    lo = df[col].quantile(lower)
    hi = df[col].quantile(upper)
    df[col] = df[col].clip(lo, hi)
    log.info(f"   {col}: [{lo:.2f}, {hi:.2f}]")

for col in ['price', 'penalty_total', 'contract_duration_days']:
    cap_outliers(ml_df, col)

# шаг 7: создание дополнительных признаков
log.info("\n7. создание признаков...")

ml_df['log_price']         = np.log1p(ml_df['price'] / 1_000_000)
ml_df['log_penalty_total'] = np.log1p(ml_df['penalty_total'] / 1_000)
ml_df['penalty_per_procedure'] = (
    ml_df['penalty_count'] / (ml_df['procedures_count'] + 1)
)
ml_df['penalty_severity']  = ml_df['penalty_total'] / (ml_df['price'] + 1)

log.info(f"   итоговая размерность: {ml_df.shape}")

# шаг 8: финальный датасет
log.info("\n8. формирование финального датасета...")

feature_columns = [
    # признаки контракта
    'log_price', 'region',
    'is_buildings', 'is_infrastructure', 'is_specialized',
    'is_multi_supplier', 'contract_duration_days',
    # признаки из процедур
    'has_penalty', 'penalty_count', 'log_penalty_total',
    'procedures_count', 'has_termination_doc',
    'penalty_per_procedure', 'penalty_severity',
    # признаки поставщика
    # supplier_terminated_share исключён — вычисляется из целевой переменной (data leakage)
    # используется только для аналитики в дашборде, в модель не идёт
    'supplier_total_contracts',
    'supplier_avg_price', 'supplier_regions_count', 'supplier_avg_suppliers',
    # interaction features — взаимодействия для логистической регрессии
    'penalty_x_experience', 'price_x_duration', 'penalty_x_price',
]

# 8.5. interaction features — создаём до формирования X чтобы попали в датасет
log.info("\n8.5. interaction features для логистической регрессии...")
ml_df['penalty_x_experience'] = (
    ml_df['penalty_count'] * ml_df['supplier_total_contracts']
)
ml_df['price_x_duration'] = (
    ml_df['log_price'] * ml_df['contract_duration_days']
)
ml_df['penalty_x_price'] = (
    ml_df['penalty_severity'] * ml_df['log_price']
)
log.info("   добавлены: penalty_x_experience, price_x_duration, penalty_x_price")

available = [c for c in feature_columns if c in ml_df.columns]
missing   = set(feature_columns) - set(available)
if missing:
    log.warning(f"   отсутствуют признаки: {missing}")

X = ml_df[available].copy()
y = ml_df['is_terminated'].copy()

# удаляем строки с пропуском в целевой переменной
valid = y.notna()
X = X[valid]
y = y[valid]

# приводим типы
y = y.astype(int)
for col in X.select_dtypes(include='object').columns:
    X[col] = pd.to_numeric(X[col], errors='coerce').fillna(0)

log.info(f"\n   признаков:  {X.shape[1]}")
log.info(f"   объектов:   {X.shape[0]}")
log.info(f"   успешно (0): {(y==0).sum()}")
log.info(f"   расторгнуто (1): {(y==1).sum()}")
log.info(f"   доля расторжений: {y.mean()*100:.2f}%")

log.info("\n9. сохранение...")
os.makedirs(DATA_DIR, exist_ok=True)

X_path        = os.path.join(DATA_DIR, "X_features.csv")
y_path        = os.path.join(DATA_DIR, "y_target.csv")
features_path = os.path.join(DATA_DIR, "feature_columns.txt")
full_path     = os.path.join(DATA_DIR, "ml_dataset.csv")

X.to_csv(X_path, index=False)
y.to_csv(y_path, index=False, header=True)
ml_df.to_csv(full_path, index=False)

with open(features_path, 'w', encoding='utf-8') as f:
    for feat in available:
        f.write(f"{feat}\n")

log.info(f"   X_features.csv:      {X_path}")
log.info(f"   y_target.csv:        {y_path}")
log.info(f"   feature_columns.txt: {features_path}")
log.info(f"   ml_dataset.csv:      {full_path}")

# шаг 10: итоговая статистика
log.info("\n" + "=" * 60)
log.info("СТАТИСТИКА ПО ДАТАСЕТУ")
log.info("=" * 60)
log.info(f"\n{X.describe().to_string()}")
log.info("\nэтап 4 завершён")
log.info("следующий шаг: python 05_01_logistic_regression.py")