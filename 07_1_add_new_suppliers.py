# 07_add_new_suppliers.py
# добавляет новых поставщиков в таблицу suppliers
# чтобы 02_download_contracts.py их подхватил в следующем запуске.
# запуск: python 07_add_new_suppliers.py

import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))
from config import DB_PATH

conn = sqlite3.connect(DB_PATH)

# новые поставщики — те что есть в contract_suppliers но не в suppliers
cursor = conn.execute("""
    SELECT DISTINCT cs.supplier_inn
    FROM contract_suppliers cs
    WHERE cs.supplier_inn NOT IN (
        SELECT supplier_inn FROM suppliers
    )
""")
new_inns = [row[0] for row in cursor.fetchall()]
print(f"новых поставщиков: {len(new_inns)}")

# добавляем в suppliers с флагом selected_for_download=1
conn.executemany("""
    INSERT OR IGNORE INTO suppliers (supplier_inn, selected_for_download, total_contracts_old)
    VALUES (?, 1, 0)
""", [(inn,) for inn in new_inns])

# удаляем из лога загрузки если вдруг там есть
conn.executemany("""
    DELETE FROM supplier_download_log
    WHERE supplier_inn = ?
""", [(inn,) for inn in new_inns])

conn.commit()
conn.close()
print("готово — теперь запустите: python 02_download_contracts.py")