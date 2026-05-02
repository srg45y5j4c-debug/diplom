# =========================================================
# ПРОВЕРКА СТАТИСТИКИ ВЫГРУЗКИ КОНТРАКТОВ
# =========================================================
# Запускать после завершения Этапа 2

import sqlite3
from datetime import datetime
import os

# =========================================================
# КОНСТАНТЫ
# =========================================================
DB_PATH = r"C:\Users\user\Desktop\dipl\vigruzka\gosplan_construction.db"
REPORT_DIR = r"C:\Users\user\Desktop\dipl\vigruzka"  # папка для сохранения отчета

# =========================================================
# ПОДКЛЮЧЕНИЕ К БД
# =========================================================
print("="*60)
print("СТАТИСТИКА ВЫГРУЗКИ КОНТРАКТОВ")
print("="*60)
print(f"📁 База данных: {DB_PATH}")
print()

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# =========================================================
# 1. ОБЩАЯ СТАТИСТИКА ПО ТАБЛИЦАМ
# =========================================================
print("📊 ОБЩАЯ СТАТИСТИКА")
print("-" * 40)

cursor.execute("SELECT COUNT(*) FROM contracts")
contracts_cnt = cursor.fetchone()[0]
print(f"📦 Контрактов (таблица contracts): {contracts_cnt:,}")

cursor.execute("SELECT COUNT(*) FROM contract_suppliers")
links_cnt = cursor.fetchone()[0]
print(f"🔗 Связей контракт-поставщик: {links_cnt:,}")

cursor.execute("SELECT COUNT(*) FROM supplier_download_log")
logs_cnt = cursor.fetchone()[0]
print(f"📋 Записей в журнале выгрузки: {logs_cnt}")

print()

# =========================================================
# 2. СТАТИСТИКА ПО ПОСТАВЩИКАМ
# =========================================================
print("👤 СТАТИСТИКА ПО ПОСТАВЩИКАМ")
print("-" * 40)

cursor.execute("""
    SELECT 
        COUNT(DISTINCT supplier_inn) as unique_suppliers
    FROM contract_suppliers
""")
unique_suppliers = cursor.fetchone()[0]
print(f"👥 Уникальных поставщиков в связках: {unique_suppliers:,}")

cursor.execute("""
    SELECT 
        status, 
        COUNT(*) as count,
        SUM(contracts_found) as total_contracts
    FROM supplier_download_log
    GROUP BY status
""")
print("📊 Статусы обработки поставщиков:")
for status, count, total in cursor.fetchall():
    status_symbol = "✅" if status == "success" else "❌"
    print(f"  {status_symbol} {status}: {count} поставщиков, найдено контрактов: {total}")

print()

# =========================================================
# 3. СТАТИСТИКА ПО МУЛЬТИ-ПОСТАВЩИКАМ
# =========================================================
print("👥 МУЛЬТИ-ПОСТАВЩИКИ")
print("-" * 40)

cursor.execute("""
    SELECT 
        is_multi_supplier,
        COUNT(*) as count,
        ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM contracts), 2) as percent
    FROM contracts
    GROUP BY is_multi_supplier
    ORDER BY is_multi_supplier DESC
""")
for flag, cnt, pct in cursor.fetchall():
    if flag == 1:
        print(f"  👥 С несколькими поставщиками: {cnt:,} ({pct}%)")
    else:
        print(f"  👤 С одним поставщиком: {cnt:,} ({pct}%)")

print()

# =========================================================
# 4. СТАТИСТИКА ПО СТАТУСАМ КОНТРАКТОВ
# =========================================================
print("📈 СТАТИСТИКА ПО СТАТУСАМ")
print("-" * 40)

cursor.execute("""
    SELECT 
        stage,
        COUNT(*) as count,
        ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM contracts WHERE stage IN ('ET', 'EC')), 2) as percent
    FROM contracts
    WHERE stage IN ('ET', 'EC')
    GROUP BY stage
    ORDER BY stage
""")
for stage, cnt, pct in cursor.fetchall():
    status_name = "Расторгнуто (ET)" if stage == "ET" else "Завершено (EC)"
    print(f"  {status_name}: {cnt:,} ({pct}%)")

# Дополнительно посчитаем контракты с другими статусами (если есть)
cursor.execute("""
    SELECT 
        COUNT(*) as count
    FROM contracts
    WHERE stage NOT IN ('ET', 'EC')
""")
other_cnt = cursor.fetchone()[0]
if other_cnt > 0:
    print(f"  ⚠️ Другие статусы: {other_cnt}")

print()

# =========================================================
# 5. ТОП-10 ПОСТАВЩИКОВ ПО КОЛИЧЕСТВУ КОНТРАКТОВ
# =========================================================
print("🏆 ТОП-10 ПОСТАВЩИКОВ ПО КОЛИЧЕСТВУ КОНТРАКТОВ")
print("-" * 40)

cursor.execute("""
    SELECT 
        cs.supplier_inn,
        COUNT(*) as contracts_count,
        SUM(CASE WHEN c.is_terminated = 1 THEN 1 ELSE 0 END) as terminated_count,
        ROUND(SUM(CASE WHEN c.is_terminated = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as risk_percent
    FROM contract_suppliers cs
    JOIN contracts c ON cs.reg_num = c.reg_num
    GROUP BY cs.supplier_inn
    ORDER BY contracts_count DESC
    LIMIT 10
""")
print(f"{'№':<3} {'ИНН':<15} {'Контрактов':<12} {'Расторжений':<12} {'Риск':<8}")
print("-" * 55)
for i, (inn, total, term, risk) in enumerate(cursor.fetchall(), 1):
    print(f"{i:<3} {inn:<15} {total:<12,} {term:<12} {risk:<8}%")

print()

# =========================================================
# 6. ИТОГОВЫЕ ПОКАЗАТЕЛИ ДЛЯ ПОЯСНИТЕЛЬНОЙ ЗАПИСКИ
# =========================================================
print("📋 ИТОГОВЫЕ ПОКАЗАТЕЛИ ДЛЯ ПОЯСНИТЕЛЬНОЙ ЗАПИСКИ")
print("-" * 40)

# Обработано поставщиков
cursor.execute("SELECT COUNT(*) FROM supplier_download_log WHERE status = 'success'")
processed = cursor.fetchone()[0]

# Ошибки
cursor.execute("SELECT COUNT(*) FROM supplier_download_log WHERE status = 'failed'")
errors = cursor.fetchone()[0]

print(f"✅ Обработано поставщиков: {processed}")
print(f"❌ Ошибок при выгрузке: {errors}")
print(f"📦 Уникальных контрактов: {contracts_cnt:,}")
print(f"🔗 Связей контракт-поставщик: {links_cnt:,}")

# =========================================================
# 7. СОХРАНЕНИЕ ОТЧЕТА В ПАПКУ VIGRUZKA
# =========================================================
print("\n💾 Сохранение отчета...")

# Создаем папку если её нет
os.makedirs(REPORT_DIR, exist_ok=True)

# Формируем полный путь к файлу
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
report_filename = f"download_stats_{timestamp}.txt"
report_path = os.path.join(REPORT_DIR, report_filename)

with open(report_path, "w", encoding="utf-8") as f:
    f.write("="*60 + "\n")
    f.write("СТАТИСТИКА ВЫГРУЗКИ КОНТРАКТОВ\n")
    f.write("="*60 + "\n\n")
    
    f.write(f"Дата отчета: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"База данных: {DB_PATH}\n\n")
    
    f.write("📊 ОБЩАЯ СТАТИСТИКА\n")
    f.write("-"*40 + "\n")
    f.write(f"Контрактов (таблица contracts): {contracts_cnt:,}\n")
    f.write(f"Связей контракт-поставщик: {links_cnt:,}\n")
    f.write(f"Записей в журнале выгрузки: {logs_cnt}\n\n")
    
    f.write("👤 СТАТИСТИКА ПО ПОСТАВЩИКАМ\n")
    f.write("-"*40 + "\n")
    f.write(f"Уникальных поставщиков в связках: {unique_suppliers:,}\n")
    f.write(f"Обработано поставщиков: {processed}\n")
    f.write(f"Ошибок при выгрузке: {errors}\n\n")
    
    f.write("📈 СТАТИСТИКА ПО СТАТУСАМ КОНТРАКТОВ\n")
    f.write("-"*40 + "\n")
    cursor.execute("SELECT stage, COUNT(*) FROM contracts WHERE stage IN ('ET', 'EC') GROUP BY stage")
    for stage, cnt in cursor.fetchall():
        f.write(f"  {stage}: {cnt}\n")
    f.write("\n")
    
    f.write("👥 МУЛЬТИ-ПОСТАВЩИКИ\n")
    f.write("-"*40 + "\n")
    cursor.execute("SELECT is_multi_supplier, COUNT(*) FROM contracts GROUP BY is_multi_supplier")
    for flag, cnt in cursor.fetchall():
        f.write(f"  is_multi_supplier={flag}: {cnt}\n")
    f.write("\n")
    
    f.write("📋 ИТОГОВЫЕ ПОКАЗАТЕЛИ ДЛЯ ПОЯСНИТЕЛЬНОЙ ЗАПИСКИ\n")
    f.write("-"*40 + "\n")
    f.write(f"contracts_cnt = {contracts_cnt}\n")
    f.write(f"links_cnt = {links_cnt}\n")
    f.write(f"processed = {processed}\n")
    f.write(f"errors = {errors}\n")

print(f"✅ Отчет сохранен в файл: {report_path}")

conn.close()
print("\n✅ Проверка завершена")