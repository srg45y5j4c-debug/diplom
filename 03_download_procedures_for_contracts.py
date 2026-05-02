# 03_download_procedures_for_contracts.py
# выгрузка процедур исполнения для всех контрактов из базы.
# пропускает контракты у которых процедуры уже выгружены (procedures_raw).
# поддерживает resume — при повторном запуске продолжает с непросмотренных.

import sqlite3
import requests
import time
from datetime import datetime
import json
import os
import logging
import hashlib
import concurrent.futures
from typing import Any, Dict, List, Optional, Tuple

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))
from config import DB_PATH, DATA_DIR

BASE_URL    = os.getenv("GOSPLAN_BASE_URL",       "https://v2.gosplan.info").rstrip("/")
API_PREFIX  = os.getenv("GOSPLAN_API_PREFIX",     "/fz44").rstrip("/")
API_KEY     = os.getenv("GOSPLAN_API_KEY",        "")
API_KEY_HDR = os.getenv("GOSPLAN_API_KEY_HEADER", "X-API-KEY")

SLEEP_BETWEEN = float(os.getenv("GOSPLAN_SLEEP",        "0.1"))
MAX_RETRIES   = int(os.getenv("GOSPLAN_MAX_RETRIES",    "6"))
HTTP_TIMEOUT  = int(os.getenv("GOSPLAN_HTTP_TIMEOUT",   "120"))
WORKERS       = int(os.getenv("GOSPLAN_WORKERS",        "5"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(DATA_DIR, "download_procedures.log"), encoding="utf-8"
        ),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("etl-procedures")


def make_session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    s.headers.update({
        "Accept":     "application/json",
        "Connection": "close",
        "User-Agent": "diploma-etl/1.0",
    })
    if API_KEY:
        s.headers[API_KEY_HDR] = API_KEY
    return s


def request_json(session, url) -> Tuple[int, Any, str]:
    r = session.get(url, timeout=HTTP_TIMEOUT)
    txt = r.text[:800]
    try:
        return r.status_code, r.json(), txt
    except Exception:
        return r.status_code, None, txt

def mark_raw_empty(conn, reg_num, status):
    data = []
    payload_json = json.dumps(data, ensure_ascii=False)
    payload_hash = stable_hash(data)
    conn.execute("""
        INSERT INTO procedures_raw(reg_num, fetched_at, payload_hash, payload_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(reg_num) DO UPDATE SET
            fetched_at=excluded.fetched_at,
            payload_hash=excluded.payload_hash,
            payload_json=excluded.payload_json
    """, (
        reg_num,
        datetime.now().isoformat(timespec="seconds"),
        f"EMPTY_{status}_{payload_hash}",
        payload_json
    ))

def request_json_with_retries(session, url) -> Tuple[int, Any, str]:
    backoff = 1.0
    last: Tuple[int, Any, str] = (0, None, "")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            status, data, txt = request_json(session, url)
            last = (status, data, txt)
            if status in (200, 404, 422):
                return last
            if status in (429, 500, 502, 503, 504):
                log.warning(f"временная ошибка {status}, попытка {attempt}/{MAX_RETRIES}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 20.0)
                continue
            return last
        except Exception as e:
            log.warning(f"запрос упал (попытка {attempt}/{MAX_RETRIES}): {e}")
            time.sleep(backoff)
            backoff = min(backoff * 2, 20.0)
    return last


def stable_hash(obj: Any) -> str:
    dumped = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


def safe_get(d: Dict, path: List[str]) -> Any:
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def to_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        return float(str(x).replace(" ", "").replace(",", "."))
    except Exception:
        return None


def init_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS procedures_raw (
            reg_num TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS procedures_flat (
            reg_num TEXT NOT NULL,
            doc_type TEXT,
            published_at TEXT,
            procedure_id TEXT,
            version_number TEXT,
            ordinal_number TEXT,
            current_contract_stage TEXT,
            has_termination INTEGER,
            termination_date TEXT,
            termination_reason_code TEXT,
            termination_reason_name TEXT,
            termination_reason_info TEXT,
            termination_paid REAL,
            has_penalty INTEGER,
            penalty_amount REAL,
            penalty_reason_code TEXT,
            penalty_reason_name TEXT,
            penalty_contract_party TEXT,
            is_cancel INTEGER,
            cancel_reason TEXT,
            raw_json TEXT,
            PRIMARY KEY (reg_num, procedure_id, version_number)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS procedures_errors (
            reg_num TEXT PRIMARY KEY,
            last_status INTEGER,
            last_error TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_procedures_flat_reg ON procedures_flat(reg_num)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_procedures_flat_published ON procedures_flat(published_at)")
    conn.commit()
    log.info("структура бд для процедур проверена/создана")


def upsert_error(conn, reg_num, status, err):
    conn.execute("""
        INSERT INTO procedures_errors(reg_num, last_status, last_error, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(reg_num) DO UPDATE SET
            last_status=excluded.last_status,
            last_error=excluded.last_error,
            updated_at=datetime('now')
    """, (reg_num, status, (err or "")[:500]))


def parse_procedure_item(reg_num: str, item: Dict) -> Dict:
    doc_type     = item.get("doc_type")
    published_at = item.get("published_at")
    src          = item.get("source") or {}

    version_number = src.get("versionNumber")
    ordinal_number = safe_get(src, ["executions", "ordinalNumber"])
    procedure_id   = src.get("id") or src.get("sid") or src.get("cancelledProcedureId")
    if procedure_id is None:
        procedure_id = f"{doc_type}:{ordinal_number}:{version_number}:{published_at}"

    termination   = src.get("termination")
    has_term      = 1 if isinstance(termination, dict) else 0
    pen           = safe_get(src, ["penalties", "penaltyAccrual"])
    has_pen       = 1 if isinstance(pen, dict) else 0
    is_cancel     = 1 if doc_type == "contractProcedureCancel" else 0

    return {
        "reg_num":                  reg_num,
        "doc_type":                 doc_type,
        "published_at":             published_at,
        "procedure_id":             str(procedure_id),
        "version_number":           str(version_number) if version_number is not None else None,
        "ordinal_number":           str(ordinal_number) if ordinal_number is not None else None,
        "current_contract_stage":   src.get("currentContractStage"),
        "has_termination":          has_term,
        "termination_date":         safe_get(src, ["termination", "terminationDate"]),
        "termination_reason_code":  safe_get(src, ["termination", "reason", "code"]),
        "termination_reason_name":  safe_get(src, ["termination", "reason", "name"]),
        "termination_reason_info":  safe_get(src, ["termination", "reasonInfo"]),
        "termination_paid":         to_float(safe_get(src, ["termination", "paid"])),
        "has_penalty":              has_pen,
        "penalty_amount":           to_float(safe_get(src, ["penalties", "penaltyAccrual", "accrualAmount"])),
        "penalty_reason_code":      safe_get(src, ["penalties", "penaltyAccrual", "penaltyReason", "code"]),
        "penalty_reason_name":      safe_get(src, ["penalties", "penaltyAccrual", "penaltyReason", "name"]),
        "penalty_contract_party":   safe_get(src, ["penalties", "penaltyAccrual", "contractParty"]),
        "is_cancel":                is_cancel,
        "cancel_reason":            src.get("reason") if is_cancel else None,
        "raw_json":                 json.dumps(item, ensure_ascii=False),
    }


def save_raw(conn, reg_num, data):
    payload_json = json.dumps(data, ensure_ascii=False)
    payload_hash = stable_hash(data)
    conn.execute("""
        INSERT INTO procedures_raw(reg_num, fetched_at, payload_hash, payload_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(reg_num) DO UPDATE SET
            fetched_at=excluded.fetched_at,
            payload_hash=excluded.payload_hash,
            payload_json=excluded.payload_json
    """, (reg_num, datetime.now().isoformat(timespec="seconds"), payload_hash, payload_json))


def save_flat_batch(conn, rows: List[Dict]):
    data = [
        (
            r["reg_num"], r["doc_type"], r["published_at"],
            r["procedure_id"], r["version_number"], r["ordinal_number"],
            r["current_contract_stage"],
            r["has_termination"], r["termination_date"],
            r["termination_reason_code"], r["termination_reason_name"],
            r["termination_reason_info"], r["termination_paid"],
            r["has_penalty"], r["penalty_amount"],
            r["penalty_reason_code"], r["penalty_reason_name"],
            r["penalty_contract_party"],
            r["is_cancel"], r["cancel_reason"], r["raw_json"],
        )
        for r in rows
    ]
    conn.executemany("""
        INSERT INTO procedures_flat (
            reg_num, doc_type, published_at,
            procedure_id, version_number, ordinal_number,
            current_contract_stage,
            has_termination, termination_date,
            termination_reason_code, termination_reason_name,
            termination_reason_info, termination_paid,
            has_penalty, penalty_amount,
            penalty_reason_code, penalty_reason_name,
            penalty_contract_party,
            is_cancel, cancel_reason, raw_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(reg_num, procedure_id, version_number) DO UPDATE SET
            doc_type=excluded.doc_type,
            version_number=excluded.version_number,
            ordinal_number=excluded.ordinal_number,
            current_contract_stage=excluded.current_contract_stage,
            has_termination=excluded.has_termination,
            termination_date=excluded.termination_date,
            termination_reason_code=excluded.termination_reason_code,
            termination_reason_name=excluded.termination_reason_name,
            termination_reason_info=excluded.termination_reason_info,
            termination_paid=excluded.termination_paid,
            has_penalty=excluded.has_penalty,
            penalty_amount=excluded.penalty_amount,
            penalty_reason_code=excluded.penalty_reason_code,
            penalty_reason_name=excluded.penalty_reason_name,
            penalty_contract_party=excluded.penalty_contract_party,
            is_cancel=excluded.is_cancel,
            cancel_reason=excluded.cancel_reason,
            raw_json=excluded.raw_json
    """, data)


def process_one(reg_num: str, session) -> Tuple[str, int, Any, str, float]:
    """обрабатывает один контракт — используется в threadpool"""
    start = time.time()
    url = f"{BASE_URL}{API_PREFIX}/contracts/{reg_num}/procedures"
    status, data, txt = request_json_with_retries(session, url)
    return reg_num, status, data, txt, time.time() - start


def main() -> None:
    log.info("=" * 60)
    log.info("ЭТАП 3: ВЫГРУЗКА ПРОЦЕДУР ПО КОНТРАКТАМ")
    log.info(f"база данных: {DB_PATH}")
    log.info("=" * 60)

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA cache_size=-2000000")
    conn.execute("PRAGMA temp_store=MEMORY")
    init_db(conn)

    # берём только контракты без процедур — resume работает автоматически
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.reg_num
        FROM contracts c
        LEFT JOIN procedures_raw pr ON pr.reg_num = c.reg_num
        WHERE pr.reg_num IS NULL
        ORDER BY c.reg_num
    """)
    contracts = [row[0] for row in cursor.fetchall()]
    log.info(f"контрактов без процедур: {len(contracts)}")

    if not contracts:
        log.info("все процедуры уже выгружены.")
        conn.close()
        return

    sessions  = [make_session() for _ in range(WORKERS)]
    processed = 0
    ok200     = 0
    s404      = 0
    s422      = 0
    other     = 0
    flat_batch: List[Dict] = []
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as executor:
        future_to_reg = {
            executor.submit(process_one, reg_num, sessions[i % WORKERS]): reg_num
            for i, reg_num in enumerate(contracts)
        }

        log.info(f"отправлено задач в пул: {len(future_to_reg)}")
        log.info(f"количество потоков: {WORKERS}")
        log.info("ожидаем первые ответы от API...")

        for future in concurrent.futures.as_completed(future_to_reg):
            reg_num, status, data, txt, req_time = future.result()

            processed += 1

            if status == 200 and isinstance(data, list):
                ok200 += 1
                save_raw(conn, reg_num, data)
                for item in data:
                    if isinstance(item, dict):
                        flat_batch.append(parse_procedure_item(reg_num, item))
                upsert_error(conn, reg_num, 200, "OK")
            elif status == 404:
                s404 += 1
                mark_raw_empty(conn, reg_num, 404)
                upsert_error(conn, reg_num, 404, txt or "Not Found")
            elif status == 422:
                s422 += 1
                mark_raw_empty(conn, reg_num, 422)
                upsert_error(conn, reg_num, 422, txt or "Unprocessable Entity")
            else:
                other += 1
                upsert_error(conn, reg_num, status, txt or "Unknown error")

            # сохраняем батч каждые 500 записей
            if len(flat_batch) >= 500:
                save_flat_batch(conn, flat_batch)
                flat_batch = []
                conn.commit()

            if processed % 100 == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed * 60 if elapsed > 0 else 0
                log.info(
                    f"прогресс: {processed}/{len(contracts)} "
                    f"({processed/len(contracts)*100:.1f}%) "
                    f"скорость: {rate:.0f} запр/мин "
                    f"200={ok200} 404={s404} 422={s422} other={other}"
                )

    # сохраняем остаток батча
    if flat_batch:
        save_flat_batch(conn, flat_batch)
        conn.commit()

    cursor.execute("SELECT COUNT(*) FROM procedures_flat")
    flat_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM procedures_raw")
    raw_cnt = cursor.fetchone()[0]

    log.info("\n" + "=" * 60)
    log.info("ВЫГРУЗКА ПРОЦЕДУР ЗАВЕРШЕНА")
    log.info("=" * 60)
    log.info(f"обработано контрактов: {processed}")
    log.info(f"200={ok200} 404={s404} 422={s422} other={other}")
    log.info(f"procedures_flat: {flat_cnt} записей")
    log.info(f"procedures_raw:  {raw_cnt} записей")
    log.info("\nследующий шаг: python 04_prepare_ml_dataset.py")

    conn.execute("PRAGMA synchronous=NORMAL")
    conn.close()


if __name__ == "__main__":
    main()