# =========================================================
# ЭТАП 2: ВЫГРУЗКА КОНТРАКТОВ ПО ИНН ПОСТАВЩИКА
# Таблицы:
#   - suppliers (у тебя уже есть)
#   - contracts (уникальные контракты)
#   - contract_suppliers (связка контракт-поставщик, мульти-поставщики)
#   - supplier_download_log (лог по поставщикам)
#   - etl_state (чекпоинты)
# =========================================================

import sqlite3
import requests
import time
from datetime import datetime
import json
import os
import logging
from typing import Any, Dict, List, Optional, Tuple

# =========================================================
# КОНСТАНТЫ
# =========================================================
BASE_URL = os.getenv("GOSPLAN_BASE_URL", "https://v2.gosplan.info").rstrip("/")
API_PREFIX = os.getenv("GOSPLAN_API_PREFIX", "/fz44").rstrip("/")
DB_PATH = os.getenv("GOSPLAN_DB_PATH", r"C:\Users\user\Desktop\diplom\data\gosplan_construction.db")

SLEEP_BETWEEN = float(os.getenv("GOSPLAN_SLEEP", "0.05"))  # пауза между запросами
MAX_RETRIES = int(os.getenv("GOSPLAN_MAX_RETRIES", "6"))
HTTP_TIMEOUT = int(os.getenv("GOSPLAN_HTTP_TIMEOUT", "120"))
LIMIT = int(os.getenv("GOSPLAN_LIMIT", "100"))
BATCH_SIZE = int(os.getenv("GOSPLAN_BATCH_LOG", "10"))

# Фильтры (строительство)
CLASSIFIERS = ["41", "42", "43"]     # ОКПД2 группы
STAGES = ["ET", "EC"]                # прекращено / завершено
SORT = "updated_at_desc"             # наиболее актуальные сверху

# Если надо ограничить период:
UPDATED_AFTER = os.getenv("GOSPLAN_UPDATED_AFTER", "")  # например "2025-01-01T00:00:00Z"
UPDATED_BEFORE = os.getenv("GOSPLAN_UPDATED_BEFORE", "") # опционально

# =========================================================
# ЛОГИРОВАНИЕ
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("download_contracts.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("etl-contracts")

# =========================================================
# HTTP
# =========================================================
def make_session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    s.headers.update({
        "Accept": "application/json",
        "Connection": "close",
        "User-Agent": "diploma-etl/1.0",
    })
    # Если у тебя есть ключ — добавь сюда заголовок
    api_key = os.getenv("GOSPLAN_API_KEY", "")
    api_key_header = os.getenv("GOSPLAN_API_KEY_HEADER", "X-API-KEY")
    if api_key:
        s.headers.update({api_key_header: api_key})
    return s

def normalize_list(data: Any) -> Optional[List[Dict[str, Any]]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("items", "data", "results"):
            v = data.get(k)
            if isinstance(v, list):
                return v
    return None

def request_json(session: requests.Session, url: str, params: Dict[str, Any]) -> Tuple[int, Any, str]:
    r = session.get(url, params=params, timeout=HTTP_TIMEOUT)
    txt = r.text[:800]
    try:
        return r.status_code, r.json(), txt
    except Exception:
        return r.status_code, None, txt

def request_json_with_retries(session: requests.Session, url: str, params: Dict[str, Any]) -> Tuple[int, Any, str]:
    backoff = 1.0
    last: Tuple[int, Any, str] = (0, None, "")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            status, data, txt = request_json(session, url, params=params)
            last = (status, data, txt)

            # ожидаемые статусы
            if status in (200, 404, 422):
                return last

            # временные
            if status in (429, 500, 502, 503, 504):
                log.warning(f"Временная ошибка {status}, попытка {attempt}/{MAX_RETRIES}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 20.0)
                continue

            # прочие 4xx/5xx
            if 400 <= status < 600:
                log.error(f"HTTP ошибка {status}: {txt}")
                return last

            return last

        except Exception as e:
            log.warning(f"Request failed (attempt {attempt}/{MAX_RETRIES}): {e}")
            time.sleep(backoff)
            backoff = min(backoff * 2, 20.0)

    return last

# =========================================================
# БД
# =========================================================
def init_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # лог по поставщикам
    cur.execute("""
        CREATE TABLE IF NOT EXISTS supplier_download_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_inn TEXT,
            contracts_found INTEGER DEFAULT 0,
            started_at TEXT,
            completed_at TEXT,
            status TEXT,
            error_message TEXT
        )
    """)

    # уникальные контракты
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contracts (
            reg_num TEXT PRIMARY KEY,

            stage TEXT,
            is_terminated INTEGER,      -- 1 если ET, 0 если EC, NULL иначе

            updated_at TEXT,
            published_at TEXT,

            price REAL,
            currency_code TEXT,
            region INTEGER,

            customer_inn TEXT,
            purchase_number TEXT,
            plan_number TEXT,
            position_number TEXT,

            exe_start TEXT,
            exe_end TEXT,

            subject TEXT,
            okpd2_csv TEXT,
            ktru_csv TEXT,

            suppliers_count INTEGER DEFAULT 0,
            is_multi_supplier INTEGER DEFAULT 0, -- 1 если suppliers_count>1

            fetched_at TEXT
        )
    """)

    # связка контракт-поставщик (многие-ко-многим)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contract_suppliers (
            reg_num TEXT NOT NULL,
            supplier_inn TEXT NOT NULL,

            suppliers_count INTEGER,
            is_multi_supplier INTEGER,

            inserted_at TEXT DEFAULT (datetime('now')),

            PRIMARY KEY (reg_num, supplier_inn)
        )
    """)

    # чекпоинты
    cur.execute("""
        CREATE TABLE IF NOT EXISTS etl_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # индексы для скорости аналитики
    cur.execute("CREATE INDEX IF NOT EXISTS idx_contracts_stage ON contracts(stage)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_contracts_updated ON contracts(updated_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cs_supplier ON contract_suppliers(supplier_inn)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cs_regnum ON contract_suppliers(reg_num)")

    conn.commit()
    log.info("✅ Структура БД проверена/создана")

def get_state(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    cur = conn.cursor()
    cur.execute("SELECT value FROM etl_state WHERE key = ?", (key,))
    row = cur.fetchone()
    return row[0] if row else default

def upsert_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("""
        INSERT INTO etl_state(key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, value))
    conn.commit()

def to_csv(v: Any) -> str:
    if isinstance(v, list):
        return ",".join(str(x) for x in v if x is not None)
    if v is None:
        return ""
    return str(v)

def terminated_flag(stage: Optional[str]) -> Optional[int]:
    if stage == "ET":
        return 1
    if stage == "EC":
        return 0
    return None

def extract_suppliers_list(contract: Dict[str, Any]) -> List[str]:
    """
    /contracts обычно возвращает suppliers: [inn, inn...]
    Иногда может быть 'suppliers_csv' или что-то странное — страхуемся.
    """
    supp = contract.get("suppliers")
    if isinstance(supp, list):
        return [str(x) for x in supp if x]
    if isinstance(supp, str) and supp.strip():
        # вдруг csv
        return [x.strip() for x in supp.split(",") if x.strip()]
    return []

def upsert_contract_and_links(
    conn: sqlite3.Connection,
    contract: Dict[str, Any],
    searched_supplier_inn: str,
) -> None:
    reg_num = contract.get("reg_num")
    if not reg_num:
        return

    stage = contract.get("stage")
    is_term = terminated_flag(stage)

    suppliers_list = extract_suppliers_list(contract)
    # важно: если API вдруг не вернул suppliers[], хотя мы искали по supplier=...
    if not suppliers_list:
        suppliers_list = [searched_supplier_inn]
    else:
        # гарантируем, что искомый supplier тоже есть
        if searched_supplier_inn not in suppliers_list:
            suppliers_list.append(searched_supplier_inn)

    suppliers_count = len(set(suppliers_list))
    is_multi = 1 if suppliers_count > 1 else 0

    okpd2_csv = to_csv(contract.get("okpd2"))
    ktru_csv = to_csv(contract.get("ktru"))

    fetched_at = datetime.now().isoformat(timespec="seconds")

    # contracts (уникальная сущность)
    conn.execute("""
        INSERT INTO contracts (
            reg_num,
            stage, is_terminated,
            updated_at, published_at,
            price, currency_code, region,
            customer_inn, purchase_number, plan_number, position_number,
            exe_start, exe_end,
            subject, okpd2_csv, ktru_csv,
            suppliers_count, is_multi_supplier,
            fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(reg_num) DO UPDATE SET
            stage=excluded.stage,
            is_terminated=excluded.is_terminated,
            updated_at=excluded.updated_at,
            published_at=excluded.published_at,
            price=excluded.price,
            currency_code=excluded.currency_code,
            region=excluded.region,
            customer_inn=excluded.customer_inn,
            purchase_number=excluded.purchase_number,
            plan_number=excluded.plan_number,
            position_number=excluded.position_number,
            exe_start=excluded.exe_start,
            exe_end=excluded.exe_end,
            subject=excluded.subject,
            okpd2_csv=excluded.okpd2_csv,
            ktru_csv=excluded.ktru_csv,
            suppliers_count=excluded.suppliers_count,
            is_multi_supplier=excluded.is_multi_supplier,
            fetched_at=excluded.fetched_at
    """, (
        reg_num,
        stage, is_term,
        contract.get("updated_at"), contract.get("published_at"),
        contract.get("price"), contract.get("currency_code"), contract.get("region"),
        contract.get("customer"), contract.get("purchase_number"), contract.get("plan_number"), contract.get("position_number"),
        contract.get("exe_start"), contract.get("exe_end"),
        contract.get("subject"),
        okpd2_csv, ktru_csv,
        suppliers_count, is_multi,
        fetched_at
    ))

    # contract_suppliers (связки)
    for inn in sorted(set(suppliers_list)):
        conn.execute("""
            INSERT INTO contract_suppliers (reg_num, supplier_inn, suppliers_count, is_multi_supplier)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(reg_num, supplier_inn) DO UPDATE SET
                suppliers_count=excluded.suppliers_count,
                is_multi_supplier=excluded.is_multi_supplier
        """, (reg_num, inn, suppliers_count, is_multi))

# =========================================================
# API: контракты
# =========================================================
def fetch_contracts_page(
    session: requests.Session,
    supplier_inn: str,
    classifier: str,
    stage: str,
    skip: int
) -> Tuple[int, Optional[List[Dict[str, Any]]], str]:
    url = f"{BASE_URL}{API_PREFIX}/contracts"
    params: Dict[str, Any] = {
        "supplier": supplier_inn,
        "classifier": classifier,
        "stage": stage,
        "limit": LIMIT,
        "skip": skip,
        "sort": SORT,
    }
    if UPDATED_AFTER:
        params["updated_after"] = UPDATED_AFTER
    if UPDATED_BEFORE:
        params["updated_before"] = UPDATED_BEFORE

    status, data, txt = request_json_with_retries(session, url, params=params)
    if status == 200:
        items = normalize_list(data)
        if items is None:
            return status, None, txt
        return status, items, txt
    return status, None, txt

# =========================================================
# Основная обработка поставщика
# =========================================================
def process_supplier(conn: sqlite3.Connection, session: requests.Session, supplier_inn: str) -> int:
    found_total = 0

    for classifier in CLASSIFIERS:
        for stage in STAGES:
            skip = 0
            while True:
                status, items, txt = fetch_contracts_page(session, supplier_inn, classifier, stage, skip)

                if status == 200:
                    if items is None:
                        log.warning(f"⚠️ Неожиданный формат ответа 200 (не список): {txt}")
                        break

                    if not items:
                        break

                    for c in items:
                        upsert_contract_and_links(conn, c, supplier_inn)
                    found_total += len(items)

                    if len(items) < LIMIT:
                        break

                    skip += LIMIT
                    time.sleep(SLEEP_BETWEEN)

                elif status == 404:
                    break
                elif status == 422:
                    # обычно значит “не так задан параметр” или недопустимое сочетание
                    log.warning(f"⚠️ 422 для supplier={supplier_inn} classifier={classifier} stage={stage}: {txt}")
                    break
                else:
                    log.warning(f"⚠️ Ошибка {status} supplier={supplier_inn} classifier={classifier} stage={stage}: {txt}")
                    break

            # time.sleep(SLEEP_BETWEEN)

    return found_total

# =========================================================
# MAIN
# =========================================================
def main() -> None:
    log.info("=" * 60)
    log.info("ЗАПУСК ВЫГРУЗКИ КОНТРАКТОВ ПО ИНН ПОСТАВЩИКОВ")
    log.info("=" * 60)

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    init_db(conn)

    # список поставщиков
    cursor = conn.cursor()

    # предполагаю, что у тебя есть:
    # suppliers(supplier_inn TEXT, selected_for_download INTEGER, total_contracts_old INTEGER ...)
    cursor.execute("""
        SELECT s.supplier_inn
        FROM suppliers s
        WHERE s.selected_for_download = 1
        AND NOT EXISTS (
            SELECT 1
            FROM supplier_download_log l
            WHERE l.supplier_inn = s.supplier_inn
                AND l.status = 'success'
        )
        ORDER BY s.total_contracts_old DESC
    """)
    suppliers = [row[0] for row in cursor.fetchall()]
    log.info(f"📋 Осталось обработать поставщиков: {len(suppliers)}")
    total_suppliers = len(suppliers)


    session = make_session()

    processed = 0
    total_contracts = 0
    errors = 0

    # корректный resume без лексикографических сюрпризов
    for idx, supplier_inn in enumerate(suppliers, start=1):

        started_at = datetime.now().isoformat(timespec="seconds")
        log.info(f"\n{'='*50}\nПоставщик: {supplier_inn}\n{'='*50}")

        try:
            conn.execute("BEGIN")  # транзакция на поставщика

            found = process_supplier(conn, session, supplier_inn)

            conn.execute("""
                INSERT INTO supplier_download_log (supplier_inn, contracts_found, started_at, completed_at, status, error_message)
                VALUES (?, ?, ?, ?, 'success', NULL)
            """, (supplier_inn, found, started_at, datetime.now().isoformat(timespec="seconds")))

            conn.commit()

            processed += 1
            total_contracts += found
            log.info(f"✅ Готово: {supplier_inn}. Найдено контрактов (строк ответа API): {found}")

            cursor.execute("SELECT COUNT(*) FROM contracts")
            current_contracts = cursor.fetchone()[0]

            log.info(
                f"[{idx}/{total_suppliers}] "
                f"supplier={supplier_inn} | "
                f"api_rows={found} | "
                f"unique_contracts_in_db={current_contracts}"
            )

        except Exception as e:
            errors += 1
            conn.rollback()
            log.error(f"❌ Ошибка по {supplier_inn}: {e}", exc_info=True)

            conn.execute("""
                INSERT INTO supplier_download_log (supplier_inn, contracts_found, started_at, completed_at, status, error_message)
                VALUES (?, 0, ?, ?, 'failed', ?)
            """, (supplier_inn, started_at, datetime.now().isoformat(timespec="seconds"), str(e)))
            conn.commit()
            continue

        if processed % BATCH_SIZE == 0:
            log.info(f"\n📊 ПРОГРЕСС: поставщиков={processed}, contracts_api_rows={total_contracts}, errors={errors}")

    # итоговые счётчики в БД
    cursor.execute("SELECT COUNT(*) FROM contracts")
    contracts_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM contract_suppliers")
    links_cnt = cursor.fetchone()[0]

    log.info("\n" + "=" * 60)
    log.info("ВЫГРУЗКА ЗАВЕРШЕНА")
    log.info("=" * 60)
    log.info(f"✅ Поставщиков обработано: {processed}")
    log.info(f"📦 contracts (уникальные reg_num): {contracts_cnt}")
    log.info(f"🔗 contract_suppliers (связки): {links_cnt}")
    log.info(f"❌ Ошибок: {errors}")

    # распределение по мульти-поставщикам
    cursor.execute("""
        SELECT is_multi_supplier, COUNT(*)
        FROM contracts
        GROUP BY is_multi_supplier
        ORDER BY is_multi_supplier DESC
    """)
    log.info("\n👥 Мульти-поставщики (по contracts.is_multi_supplier):")
    for flag, cnt in cursor.fetchall():
        log.info(f"  is_multi_supplier={flag}: {cnt}")

    conn.close()

if __name__ == "__main__":
    main()