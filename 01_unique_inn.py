# =========================================================
# ЭТАП 1: СОЗДАНИЕ НОВОЙ БД С УНИКАЛЬНЫМИ ПОСТАВЩИКАМИ
# =========================================================
# Файл: 01_create_suppliers_db.py

import sqlite3
import os
from datetime import datetime

print("="*60)
print("ЭТАП 1: СОЗДАНИЕ НОВОЙ БАЗЫ ДАННЫХ")
print("="*60)

# Пути к базам данных
OLD_DB_PATH = r"C:\Users\user\Desktop\dipl\gosplan3.db"
NEW_DB_PATH = r"C:\Users\user\Desktop\dipl\vigruzka\gosplan_construction.db"

# Проверяем существование старой БД
if not os.path.exists(OLD_DB_PATH):
    print(f"❌ Ошибка: Старая БД не найдена по пути {OLD_DB_PATH}")
    exit(1)

print(f"📁 Старая БД: {OLD_DB_PATH}")
print(f"📁 Новая БД: {NEW_DB_PATH}")

# =========================================================
# 1. ПОДКЛЮЧЕНИЕ К БАЗАМ ДАННЫХ
# =========================================================
# Подключаемся к старой БД (только чтение)
old_conn = sqlite3.connect(OLD_DB_PATH)
old_conn.row_factory = sqlite3.Row  # чтобы обращаться по именам колонок
old_cursor = old_conn.cursor()

# Создаем/подключаемся к новой БД
new_conn = sqlite3.connect(NEW_DB_PATH)
new_cursor = new_conn.cursor()

print("\n✅ Подключение к базам данных выполнено")

# =========================================================
# 2. ПОЛУЧАЕМ УНИКАЛЬНЫХ ПОСТАВЩИКОВ ИЗ СТАРОЙ БД
# =========================================================
print("\n🔍 Получение списка поставщиков из старой БД...")

# Сначала создаем временное представление для разбора suppliers_csv
old_cursor.execute("""
    CREATE TEMP VIEW IF NOT EXISTS temp_suppliers AS
    SELECT DISTINCT 
        TRIM(value) as supplier_inn
    FROM contracts_analytic, 
         json_each('["' || REPLACE(suppliers_csv, ',', '","') || '"]')
    WHERE suppliers_csv IS NOT NULL 
        AND suppliers_csv != ''
""")

# Теперь получаем статистику по каждому поставщику
query = """
    WITH supplier_contracts AS (
        SELECT 
            TRIM(value) as supplier_inn,
            ca.is_terminated,
            ca.price,
            ca.region
        FROM contracts_analytic ca,
             json_each('["' || REPLACE(ca.suppliers_csv, ',', '","') || '"]')
        WHERE ca.suppliers_csv IS NOT NULL 
            AND ca.suppliers_csv != ''
            AND ca.is_terminated IS NOT NULL
    )
    SELECT 
        supplier_inn,
        COUNT(*) as contract_count,
        SUM(is_terminated) as terminated_count,
        AVG(is_terminated) * 100 as risk_percent,
        AVG(price) as avg_price,
        GROUP_CONCAT(DISTINCT region) as regions
    FROM supplier_contracts
    GROUP BY supplier_inn
    HAVING contract_count >= 3
    ORDER BY contract_count DESC
"""

old_cursor.execute(query)
suppliers = old_cursor.fetchall()

print(f"✅ Найдено {len(suppliers)} поставщиков с >=3 контрактами")

# Покажем топ-10 для примера
print("\n📊 Топ-10 поставщиков по количеству контрактов:")
for i, row in enumerate(suppliers[:10], 1):
    print(f"  {i}. ИНН: {row['supplier_inn']}, "
          f"Контрактов: {row['contract_count']}, "
          f"Риск: {row['risk_percent']:.1f}%")

# =========================================================
# 3. СОЗДАНИЕ СТРУКТУРЫ НОВОЙ БД
# =========================================================
print("\n🏗️  Создание структуры новой БД...")

# Таблица поставщиков
new_cursor.execute("""
    CREATE TABLE IF NOT EXISTS suppliers (
        supplier_inn TEXT PRIMARY KEY,
        total_contracts_old INTEGER,
        terminated_contracts_old INTEGER,
        risk_percent_old REAL,
        avg_price_old REAL,
        regions_old TEXT,
        selected_for_download INTEGER DEFAULT 1,
        downloaded_at TEXT,
        notes TEXT
    )
""")

# Таблица для отслеживания выгрузки
new_cursor.execute("""
    CREATE TABLE IF NOT EXISTS download_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_inn TEXT,
        stage TEXT,
        contracts_found INTEGER,
        procedures_found INTEGER,
        started_at TEXT,
        completed_at TEXT,
        status TEXT,
        error_message TEXT
    )
""")

# Таблица для хранения выгруженных контрактов (создадим позже, 
# но структуру определим сразу)
new_cursor.execute("""
    CREATE TABLE IF NOT EXISTS contracts (
        reg_num TEXT PRIMARY KEY,
        supplier_inn TEXT,
        price REAL,
        stage TEXT,
        is_terminated INTEGER,
        published_at TEXT,
        exe_start TEXT,
        exe_end TEXT,
        subject TEXT,
        okpd2_csv TEXT,
        customer_inn TEXT,
        region INTEGER,
        construction_type TEXT,
        fetched_at TEXT,
        FOREIGN KEY (supplier_inn) REFERENCES suppliers(supplier_inn)
    )
""")

new_cursor.execute("""
    CREATE TABLE IF NOT EXISTS procedures (
        reg_num TEXT,
        procedure_id TEXT,
        published_at TEXT,
        has_penalty INTEGER,
        penalty_amount REAL,
        has_termination INTEGER,
        termination_reason TEXT,
        termination_date TEXT,
        doc_type TEXT,
        fetched_at TEXT,
        PRIMARY KEY (reg_num, procedure_id),
        FOREIGN KEY (reg_num) REFERENCES contracts(reg_num)
    )
""")

# Индексы для ускорения
new_cursor.execute("CREATE INDEX IF NOT EXISTS idx_contracts_supplier ON contracts(supplier_inn)")
new_cursor.execute("CREATE INDEX IF NOT EXISTS idx_contracts_type ON contracts(construction_type)")
new_cursor.execute("CREATE INDEX IF NOT EXISTS idx_procedures_reg ON procedures(reg_num)")

new_conn.commit()
print("✅ Структура БД создана")

# =========================================================
# 4. СОХРАНЕНИЕ ПОСТАВЩИКОВ В НОВУЮ БД
# =========================================================
print("\n💾 Сохранение поставщиков в новую БД...")

saved_count = 0
for row in suppliers:
    try:
        new_cursor.execute("""
            INSERT OR REPLACE INTO suppliers 
            (supplier_inn, total_contracts_old, terminated_contracts_old, 
             risk_percent_old, avg_price_old, regions_old, selected_for_download)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (
            row['supplier_inn'],
            row['contract_count'],
            row['terminated_count'],
            row['risk_percent'],
            row['avg_price'],
            row['regions']
        ))
        saved_count += 1
        
        # Показываем прогресс каждые 100 записей
        if saved_count % 100 == 0:
            print(f"  ...сохранено {saved_count} поставщиков")
            new_conn.commit()
            
    except Exception as e:
        print(f"  ❌ Ошибка при сохранении {row['supplier_inn']}: {e}")

new_conn.commit()
print(f"✅ Сохранено {saved_count} поставщиков")

# =========================================================
# 5. СТАТИСТИКА ПО НОВОЙ БД
# =========================================================
print("\n📊 Статистика по новой БД:")

new_cursor.execute("SELECT COUNT(*) FROM suppliers")
total_suppliers = new_cursor.fetchone()[0]

new_cursor.execute("""
    SELECT 
        COUNT(*) as total,
        SUM(total_contracts_old) as total_contracts,
        AVG(risk_percent_old) as avg_risk
    FROM suppliers
""")
stats = new_cursor.fetchone()

print(f"  • Всего поставщиков: {total_suppliers}")
print(f"  • Всего контрактов (в старой БД): {stats[1]}")
print(f"  • Средний риск: {stats[2]:.1f}%")

# Распределение по риску
new_cursor.execute("""
    SELECT 
        CASE 
            WHEN risk_percent_old < 10 THEN 'Низкий (<10%)'
            WHEN risk_percent_old < 20 THEN 'Средний (10-20%)'
            WHEN risk_percent_old < 30 THEN 'Повышенный (20-30%)'
            ELSE 'Высокий (>30%)'
        END as risk_group,
        COUNT(*) as count
    FROM suppliers
    GROUP BY risk_group
    ORDER BY count DESC
""")

print("\n📈 Распределение по уровню риска:")
for row in new_cursor.fetchall():
    print(f"  • {row[0]}: {row[1]} поставщиков")

# =========================================================
# 6. ЭКСПОРТ СПИСКА ИНН ДЛЯ ДАЛЬНЕЙШЕЙ ВЫГРУЗКИ
# =========================================================
print("\n💾 Экспорт списка ИНН...")

# Сохраняем в текстовый файл для удобства
with open(r"C:\Users\user\Desktop\dipl\suppliers_list.txt", "w") as f:
    new_cursor.execute("SELECT supplier_inn FROM suppliers ORDER BY total_contracts_old DESC")
    for row in new_cursor.fetchall():
        f.write(f"{row[0]}\n")

print(f"✅ Список ИНН сохранен в suppliers_list.txt ({total_suppliers} строк)")

# =========================================================
# ЗАВЕРШЕНИЕ
# =========================================================
old_conn.close()
new_conn.close()

print("\n" + "="*60)
print("✅ ЭТАП 1 ЗАВЕРШЕН")
print("="*60)
print(f"📁 Новая БД создана: {NEW_DB_PATH}")
print(f"📄 Список ИНН: suppliers_list.txt")
print("\n🚀 Следующий шаг: выгрузка контрактов через API")