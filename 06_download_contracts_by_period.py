# выгрузка всех строительных контрактов за период через GET /fz44/contracts

import sqlite3
import requests
import time
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))
from config import DB_PATH

# период выгрузки
# даты задаются в main() через DATE_FROM и DATE_TO

BASE_URL   = os.getenv("GOSPLAN_BASE_URL",    "https://v2.gosplan.info").rstrip("/")
API_PREFIX = os.getenv("GOSPLAN_API_PREFIX",  "/fz44").rstrip("/")
API_KEY    = os.getenv("GOSPLAN_API_KEY",     "")
API_KEY_HDR = os.getenv("GOSPLAN_API_KEY_HEADER", "X-API-KEY")

CLASSIFIERS   = ["41", "42", "43"]   # окпд2: здания, инфраструктура, спецработы
STAGES        = ["ET", "EC"]          # et = расторгнут, ec = завершён
LIMIT         = 100                   # максимум на страницу
SLEEP_BETWEEN = 0.2                   # пауза между запросами (сек)
MAX_RETRIES   = 6

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("download_by_period.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("etl-by-period")


def make_session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    s.headers.update({"Accept": "application/json", "User-Agent": "diploma-etl/3.0"})
    if API_KEY:
        s.headers[API_KEY_HDR] = API_KEY
    return s


class SkipLimitReached(Exception):
    """api вернул 422 — превышен лимит skip=1000, пагинация завершена"""
    pass


def request_with_retries(session, url, params) -> Any:
    backoff = 1.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(url, params=params, timeout=120)
            # 422 означает превышен лимит skip — не ретраим, сразу выходим
            if r.status_code == 422:
                raise SkipLimitReached(f"skip лимит исчерпан (422)")
            if r.status_code in (429, 500, 502, 503, 504):
                log.warning(f"временная ошибка {r.status_code}, попытка {attempt}/{MAX_RETRIES}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            r.raise_for_status()
            return r.json()
        except SkipLimitReached:
            raise
        except Exception as e:
            log.warning(f"запрос упал (попытка {attempt}/{MAX_RETRIES}): {e}")
            time.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
    raise RuntimeError(f"не удалось выполнить запрос после {MAX_RETRIES} попыток")


def normalize_list(data) -> List[Dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("items", "data", "results"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


def to_csv(v) -> str:
    if isinstance(v, list):
        return ",".join(str(x) for x in v if x is not None)
    return str(v) if v is not None else ""


def init_db(conn):
    """создаёт таблицы если их нет — совместимо с существующей бд"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contracts (
            reg_num TEXT PRIMARY KEY,
            stage TEXT,
            is_terminated INTEGER,
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
            is_multi_supplier INTEGER DEFAULT 0,
            fetched_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contract_suppliers (
            reg_num TEXT NOT NULL,
            supplier_inn TEXT NOT NULL,
            suppliers_count INTEGER,
            is_multi_supplier INTEGER,
            inserted_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (reg_num, supplier_inn)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS etl_period_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contracts_stage ON contracts(stage)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contracts_updated ON contracts(updated_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cs_supplier ON contract_suppliers(supplier_inn)")
    conn.commit()


def get_state(conn, key, default=""):
    row = conn.execute("SELECT value FROM etl_period_state WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_state(conn, key, value):
    conn.execute("""
        INSERT INTO etl_period_state(key, value) VALUES(?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, value))
    conn.commit()


def upsert_contract(conn, item: Dict):
    """сохраняет контракт и поставщиков — не трогает уже существующие если данные не изменились"""
    reg_num = item.get("reg_num")
    if not reg_num:
        return

    stage   = item.get("stage")
    is_term = 1 if stage == "ET" else (0 if stage == "EC" else None)

    suppliers = item.get("suppliers") or []
    if isinstance(suppliers, str):
        suppliers = [s.strip() for s in suppliers.split(",") if s.strip()]
    suppliers_count = len(set(suppliers))
    is_multi = 1 if suppliers_count > 1 else 0
    fetched_at = datetime.now().isoformat(timespec="seconds")

    conn.execute("""
        INSERT OR IGNORE INTO contracts (
            reg_num, stage, is_terminated,
            updated_at, published_at,
            price, currency_code, region,
            customer_inn, purchase_number, plan_number, position_number,
            exe_start, exe_end,
            subject, okpd2_csv, ktru_csv,
            suppliers_count, is_multi_supplier, fetched_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        reg_num, stage, is_term,
        item.get("updated_at"), item.get("published_at"),
        item.get("price"), item.get("currency_code"), item.get("region"),
        item.get("customer"), item.get("purchase_number"),
        item.get("plan_number"), item.get("position_number"),
        item.get("exe_start"), item.get("exe_end"),
        item.get("subject"),
        to_csv(item.get("okpd2")), to_csv(item.get("ktru")),
        suppliers_count, is_multi, fetched_at
    ))

    for inn in sorted(set(suppliers)):
        conn.execute("""
            INSERT OR IGNORE INTO contract_suppliers (reg_num, supplier_inn, suppliers_count, is_multi_supplier)
            VALUES (?,?,?,?)
        """, (reg_num, inn, suppliers_count, is_multi))


def fetch_page_dates(session, classifier, stage, skip, pub_after, pub_before) -> List[Dict]:
    url = f"{BASE_URL}{API_PREFIX}/contracts"
    params = {
        "classifier":       classifier,
        "stage":            stage,
        "published_after":  pub_after,
        "published_before": pub_before,
        "sort":             "published_at_asc",  # от старых к новым — resume работает корректно
        "limit":            LIMIT,
        "skip":             skip,
    }
    data = request_with_retries(session, url, params)
    return normalize_list(data)


def week_ranges(date_from: str, date_to: str):
    """генерирует понедельные диапазоны published_after/published_before.
    неделя даёт ~250 контрактов на комбинацию — хорошо ниже лимита skip=1000."""
    from datetime import date, timedelta

    start = date(int(date_from[:4]), int(date_from[5:7]), int(date_from[8:10]))
    end   = date(int(date_to[:4]),   int(date_to[5:7]),   int(date_to[8:10]))

    cur = start
    while cur <= end:
        week_end = min(cur + timedelta(days=6), end)
        after  = f"{cur.isoformat()}T00:00:00+00:00"
        before = f"{week_end.isoformat()}T23:59:59+00:00"
        yield after, before
        cur = week_end + timedelta(days=1)


def main():
    # период разбивается на месяцы автоматически —
    # это обходит ограничение api: skip не может превышать 1000
    DATE_FROM = "2025-10-29"
    DATE_TO   = "2026-04-29"

    log.info("=" * 60)
    log.info("ВЫГРУЗКА КОНТРАКТОВ ЗА ПЕРИОД (без фильтра по поставщику)")
    log.info(f"период:         {DATE_FROM} — {DATE_TO}")
    log.info(f"классификаторы: {CLASSIFIERS}")
    log.info(f"стадии:         {STAGES}")
    log.info(f"база данных:    {DB_PATH}")
    log.info("=" * 60)

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    init_db(conn)

    session  = make_session()
    total_saved = 0

    for pub_after, pub_before in week_ranges(DATE_FROM, DATE_TO):
        for classifier in CLASSIFIERS:
            for stage in STAGES:
                # ключ чекпоинта включает месяц — resume работает корректно
                combo_key = f"skip_{pub_after[:10]}_{classifier}_{stage}"
                skip = int(get_state(conn, combo_key, "0"))

                log.info(
                    f"\n[{pub_after[:10]} — {pub_before[:10]}] classifier={classifier} "
                    f"stage={stage} — skip={skip}"
                )

                while True:
                    try:
                        items = fetch_page_dates(
                            session, classifier, stage, skip,
                            pub_after, pub_before
                        )
                    except SkipLimitReached:
                        # api ограничивает skip=1000 — данные за этот период выбраны максимально
                        log.info(f"  достигнут лимит skip=1000, переходим дальше")
                        set_state(conn, combo_key, "0")
                        break
                    except Exception as e:
                        log.error(f"ошибка на skip={skip}: {e}")
                        break

                    if not items:
                        set_state(conn, combo_key, "0")
                        break

                    conn.execute("BEGIN")
                    for item in items:
                        upsert_contract(conn, item)
                    conn.commit()

                    total_saved += len(items)
                    skip += LIMIT
                    set_state(conn, combo_key, str(skip))

                    last_pub = items[-1].get("published_at", "")[:10]
                    log.info(
                        f"  +{len(items)} контрактов "
                        f"(last published_at: {last_pub}) "
                        f"| всего: {total_saved}"
                    )

                    time.sleep(SLEEP_BETWEEN)

    # итоговая статистика
    total_db = conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
    by_stage = conn.execute("""
        SELECT stage, COUNT(*), ROUND(AVG(is_terminated)*100,1)
        FROM contracts GROUP BY stage
    """).fetchall()

    log.info("\n" + "=" * 60)
    log.info("ВЫГРУЗКА ЗАВЕРШЕНА")
    log.info(f"добавлено/обновлено в этом запуске: {total_saved}")
    log.info(f"итого контрактов в базе:            {total_db}")
    for st, cnt, risk in by_stage:
        log.info(f"  стадия {st}: {cnt} контрактов, доля расторжений: {risk}%")
    log.info("=" * 60)
    log.info("\nследующий шаг:")
    log.info("  python 03_download_procedures_for_contracts.py")

    conn.close()


if __name__ == "__main__":
    main()