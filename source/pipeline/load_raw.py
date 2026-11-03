"""Load raw survey extracts into DuckDB: the `raw` layer.

For every file matching "input_files" in the config:
  1. read and validate it (shared reader); any bad input rejects the whole file
  2. skip it only if a successful load of this exact content (extract id + SHA-256)
     is recorded in raw.load_log AND every stored row still matches the file
  3. otherwise, in ONE transaction: delete that extract's old rows, insert its rows and
     the export's own variables/codes metadata (raw.extract_metadata, the source for the
     ref_* seeds),
     check that respondent-years shared with other files have identical answers, write
     the load log, commit. Any error rolls the file back and a "failed" log row is
     written afterwards. A PRIMARY KEY on (extract_id, key columns) means the database
     itself rejects a respondent-year stored twice for one extract.

Each file is its own transaction, so a good file still loads when another fails.
The run exits 1 if any file failed. Values are stored as text, as received.

Extract identity: by default the file name, so a renamed file counts as a new extract.
To keep one identity across renames, map the file name to a stable id in the config
("extract_ids": {"file name": "id"}); rows and the log are then keyed by that id.

A schema change (different columns from the loaded table) is rejected. To apply
one, preserve the old database and rebuild from all source files into a new
database path. There is deliberately no in-place refresh that could destroy a usable
table if it failed part-way.

Evidence: raw.load_log (one row per file per run), raw.extract_metadata (current metadata per extract), and the text
log logs/pipeline.log (run id on every line, tracebacks included).

Settings: GSS_DB_PATH (database file) and GSS_LOG_DIR (log folder) may be set as
environment variables; data settings are in source/config/extract_config.json.

Usage:  python source/pipeline/load_raw.py [--raw-dir D] [--config F] [--db F]
"""
import argparse
import copy
import csv
import hashlib
import json
import logging
import os
import re
import sys
import time
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from extract_reader import RESERVED_COLUMNS, ExtractError, read_extract

ROOT = Path(__file__).resolve().parents[2]
CONTROL_TABLES = {"load_log", "extract_metadata"}
SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
META_COLUMNS = ["extract_id", "source_file", "file_sha256", "record_sha256", "run_id", "loaded_at"]
assert set(META_COLUMNS) == RESERVED_COLUMNS

logging.getLogger("load_raw").addHandler(logging.NullHandler())


class LoadError(Exception):
    """A file or the database cannot be loaded; the message says why."""


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def record_hash(row, columns):
    """Fingerprint of one record's values, so shared respondent-years can be compared."""
    payload = json.dumps([[c, None if row[c] is None else str(row[c])] for c in sorted(columns)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def quote(name):
    if not SAFE_NAME.match(name):
        raise LoadError(f"unsafe column or table name: {name!r}")
    return f'"{name}"'


def connect(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return duckdb.connect(str(db_path))
    except duckdb.Error as error:  # e.g. another process holds the write lock
        raise LoadError(f"cannot open {db_path}: {error}. Is another run using it?") from error


def setup(con):
    con.execute("create schema if not exists raw")
    con.execute("""create table if not exists raw.load_log (
        run_id varchar, extract_id varchar, source_file varchar, file_sha256 varchar, status varchar,
        records_read integer, records_loaded integer, overlap_records integer, error varchar,
        started_at timestamp, finished_at timestamp)""")
    con.execute("""create table if not exists raw.extract_metadata (
        extract_id varchar primary key, metadata_json varchar, run_id varchar, loaded_at timestamp)""")


def insert_rows(con, table, names, rows):
    """Bulk insert validated rows inside the caller's existing transaction.

    Python 3.12's QUOTE_NOTNULL writes NULL as unquoted empty, and all other
    values (including an empty string) as quoted text. DuckDB is told not to
    convert quoted empty values to NULL and not to infer column types.
    The temporary file is closed before DuckDB opens it (required on Windows).
    """
    if not rows:
        return
    columns = ", ".join(quote(c) for c in names)
    # quote() also validates identifiers before they enter the SQL type map.
    types = "{" + ", ".join(f"'{c}': 'VARCHAR'" for c in names) + "}"
    with tempfile.TemporaryDirectory(prefix="gss_bulk_") as directory:
        path = Path(directory) / "validated.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, quoting=csv.QUOTE_NOTNULL, lineterminator="\n")
            writer.writerows(rows)
        con.execute(
            f"insert into raw.{quote(table)} ({columns}) "
            f"select {columns} from read_csv(?, columns={types}, auto_detect=false, "
            "header=false, delim=',', quote='\"', escape='\"', nullstr='', "
            "allow_quoted_nulls=false, strict_mode=true)", [str(path)])


def table_columns(con, table):
    rows = con.execute(
        "select column_name from information_schema.columns "
        "where table_schema = 'raw' and table_name = ? order by ordinal_position",
        [table]).fetchall()
    return [r[0] for r in rows]


def write_log(con, run_id, extract_id, name, sha, status, read, loaded, error, started, overlap=0):
    con.execute("insert into raw.load_log values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [run_id, extract_id, name, sha, status, read, loaded, overlap, error, started, now_utc()])


def metadata_json(extract):
    """The export's own variables/codes sections as stable JSON text (input for the ref_* seeds)."""
    return json.dumps(extract.metadata, sort_keys=True, ensure_ascii=False, allow_nan=False)


def already_loaded(con, table, keys, columns, extract_id, sha, rows, metadata):
    """True only if this exact content was loaded successfully and is still stored intact.

    Beyond the log entry, every stored row is re-fingerprinted from its stored values and
    compared with the file, and the stored metadata must equal the file's, so truncated,
    edited or mis-fingerprinted data forces a reload.
    """
    stored_columns = table_columns(con, table)
    if not stored_columns or set(stored_columns) - set(META_COLUMNS) != set(columns):
        return False
    logged = con.execute(
        "select records_loaded from raw.load_log where extract_id = ? and file_sha256 = ? "
        "and status = 'loaded' order by finished_at desc limit 1", [extract_id, sha]).fetchone()
    if logged is None:
        return False
    saved = con.execute("select metadata_json from raw.extract_metadata where extract_id = ?",
                        [extract_id]).fetchone()
    if saved is None or saved[0] != metadata:
        return False
    names = ", ".join(quote(c) for c in ["record_sha256"] + columns)
    stored = {}
    for record_sha, *values in con.execute(
            f"select {names} from raw.{quote(table)} where extract_id = ? and file_sha256 = ?",
            [extract_id, sha]).fetchall():
        row = dict(zip(columns, values))
        if record_sha != record_hash(row, columns):
            return False
        stored[tuple(row[k] for k in keys)] = record_sha
    expected = {key: record_hash(row, columns) for key, row in rows.items()}
    return len(stored) == logged[0] and stored == expected


def previously_loaded(con, extract_id, sha):
    """True if the log says this exact content was loaded successfully before."""
    return con.execute("select count(*) from raw.load_log where extract_id = ? and file_sha256 = ? "
                       "and status = 'loaded'", [extract_id, sha]).fetchone()[0] > 0


def count_overlap(con, table, keys, extract_id):
    """How many of this extract's respondent-years are already stored under another extract.

    Counted at load time, so it depends on load order: the file loaded second reports the
    overlap, the first reports 0. The order-independent total is logged at the end of each run.
    """
    same = " and ".join(f"b.{quote(k)} = a.{quote(k)}" for k in keys)
    return con.execute(
        f"select count(*) from raw.{quote(table)} a where a.extract_id = ? and exists "
        f"(select 1 from raw.{quote(table)} b where b.extract_id <> a.extract_id and {same})",
        [extract_id]).fetchone()[0]


def count_shared(con, table, keys, conflicting=False):
    """Respondent-years in more than one file; or only those whose answers differ."""
    key_sql = ", ".join(quote(k) for k in keys)
    having = "count(distinct record_sha256) > 1" if conflicting else "count(distinct extract_id) > 1"
    return con.execute(f"select count(*) from (select 1 from raw.{quote(table)} "
                       f"group by {key_sql} having {having})").fetchone()[0]


def check_shared_respondents(con, table, keys):
    """Respondent-years in more than one file must have identical answers."""
    conflicts = count_shared(con, table, keys, conflicting=True)
    if conflicts:
        key_sql = ", ".join(quote(k) for k in keys)
        example = con.execute(
            f"select {key_sql} from raw.{quote(table)} group by {key_sql} "
            f"having count(distinct record_sha256) > 1 limit 1").fetchone()
        raise LoadError(f"{conflicts} shared respondent-year(s) have different answers "
                        f"across files, e.g. {example}")


def load_file(con, path, cfg, run_id, log):
    """Load one file. Return a result dict with status loaded, skipped or failed."""
    name, table, keys = path.name, cfg["raw_table"], cfg["key_columns"]
    extract_id = cfg.get("extract_ids", {}).get(name, name)
    started, timer = now_utc(), time.perf_counter()
    result = {"file": name, "status": "failed", "read": 0, "loaded": 0, "error": ""}
    sha = None

    def fail(message):
        result["error"] = message
        log.error("%s: FAILED after %.1fs: %s", name, time.perf_counter() - timer, message)
        write_log(con, run_id, extract_id, name, sha, "failed", result["read"], 0, message, started)
        return result

    try:
        extract = read_extract(path, keys, cfg.get("records_key", "data"), cfg.get("max_file_bytes"))
    except ExtractError as error:
        return fail(str(error))
    steps = {"read": time.perf_counter() - timer}  # seconds per step, shown in the log line
    sha, result["read"] = extract.sha256, extract.record_count
    if extract.problems:
        return fail(f"{len(extract.problems)} bad record(s), file rejected; first: {extract.problems[0]}")
    try:
        quote(table)
        for column in extract.columns:
            quote(column)
        metadata = metadata_json(extract)
    except (LoadError, ValueError, TypeError) as error:
        return fail(str(error))

    ordered = list(next(iter(extract.rows.values())))
    if already_loaded(con, table, keys, ordered, extract_id, sha, extract.rows, metadata):
        result["status"] = "skipped"
        log.info("%s: skipped, unchanged and verified complete (same SHA-256)", name)
        write_log(con, run_id, extract_id, name, sha, "skipped", result["read"], 0, None, started)
        return result

    if previously_loaded(con, extract_id, sha):
        log.warning("%s: same content was loaded before but the stored data is incomplete or "
                    "altered (or its metadata is missing); reloading it from the file", name)
    mark = time.perf_counter()
    loaded_at = now_utc()
    values = [[extract_id, name, sha, record_hash(row, ordered), run_id, loaded_at]
              + [None if row[c] is None else str(row[c]) for c in ordered]
              for row in extract.rows.values()]
    steps["prepare"] = time.perf_counter() - mark
    con.begin()
    try:
        existing = table_columns(con, table)
        if not existing:
            con.execute(f"create table raw.{quote(table)} (extract_id varchar, source_file varchar, file_sha256 varchar, "
                        f"record_sha256 varchar, run_id varchar, loaded_at timestamp, "
                        + ", ".join(f"{quote(c)} varchar" for c in ordered)
                        + ", primary key (extract_id, " + ", ".join(quote(k) for k in keys) + "))")
        elif set(existing) - set(META_COLUMNS) != set(ordered):
            raise LoadError("column set differs from the loaded table; to apply a schema change, "
                            "preserve the old database and rebuild all source files into a new "
                            "database path")
        con.execute(f"delete from raw.{quote(table)} where extract_id = ?", [extract_id])
        mark = time.perf_counter()
        insert_rows(con, table, META_COLUMNS + ordered, values)
        steps["insert"] = time.perf_counter() - mark
        mark = time.perf_counter()
        con.execute("delete from raw.extract_metadata where extract_id = ?", [extract_id])
        con.execute("insert into raw.extract_metadata values (?, ?, ?, ?)",
                    [extract_id, metadata, run_id, loaded_at])
        check_shared_respondents(con, table, keys)
        overlap = count_overlap(con, table, keys, extract_id)
        write_log(con, run_id, extract_id, name, sha, "loaded", result["read"], len(values), None,
                  started, overlap)
        steps["checks"] = time.perf_counter() - mark
        mark = time.perf_counter()
        con.commit()
        steps["commit"] = time.perf_counter() - mark
    except Exception as error:  # roll back whatever went wrong, then record it
        con.rollback()
        log.debug("traceback for %s", name, exc_info=True)
        return fail(f"{type(error).__name__}: {error}")
    result.update(status="loaded", loaded=len(values))
    log.info("%s: loaded %d records in %.1fs (%s), %d already stored from other extracts (%s)", name,
             len(values), time.perf_counter() - timer,
             ", ".join(f"{step} {seconds:.1f}s" for step, seconds in steps.items()), overlap, extract.parser)
    return result


def run(raw_dir, cfg, db_path):
    """Load every matching file; return a list of result dicts."""
    run_id = f"{datetime.now():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
    log = logging.LoggerAdapter(logging.getLogger("load_raw"), {"run_id": run_id})
    if cfg["raw_table"] in CONTROL_TABLES:
        raise LoadError(f"raw_table {cfg['raw_table']!r} is reserved for loader control tables")
    paths = sorted(Path(raw_dir).glob(cfg["input_files"]))
    if not paths:
        raise LoadError(f"no files matching {cfg['input_files']} in {raw_dir}")
    ids = [cfg.get("extract_ids", {}).get(p.name, p.name) for p in paths]
    if len(set(ids)) != len(ids):
        raise LoadError("two files share one extract id; check extract_ids in the config")
    log.info("run started: %d file(s), database %s", len(paths), db_path)
    timer = time.perf_counter()
    con = connect(Path(db_path))
    try:
        setup(con)
        results = [load_file(con, p, cfg, run_id, log) for p in paths]
        table, keys = cfg["raw_table"], cfg["key_columns"]
        if table_columns(con, table):
            log.info("overlap: %d respondent-year(s) in more than one file, %d with different answers",
                     count_shared(con, table, keys), count_shared(con, table, keys, conflicting=True))
    finally:
        con.close()
    log.info("run finished in %.1fs: %d loaded, %d skipped, %d failed", time.perf_counter() - timer,
             *(sum(r["status"] == s for r in results) for s in ("loaded", "skipped", "failed")))
    return results


class ConciseFormatter(logging.Formatter):
    """Console output: the message only, with no traceback (the file log keeps it)."""

    def format(self, record):
        record = copy.copy(record)
        record.exc_info = record.exc_text = None
        return super().format(record)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--raw-dir", type=Path, default=ROOT / "source/data/raw")
    p.add_argument("--config", type=Path, default=ROOT / "source/config/extract_config.json")
    p.add_argument("--db", type=Path,
                   default=Path(os.environ.get("GSS_DB_PATH", ROOT / "source/data/warehouse/gss.duckdb")))
    args = p.parse_args()

    log_dir = Path(os.environ.get("GSS_LOG_DIR", ROOT / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    pattern = "%(asctime)s %(levelname)s run=%(run_id)s %(message)s"
    logger = logging.getLogger("load_raw")
    logger.setLevel(logging.DEBUG)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(ConciseFormatter(pattern))
    logfile = logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8")
    logfile.setFormatter(logging.Formatter(pattern))
    logger.addHandler(console)
    logger.addHandler(logfile)
    run_failed = logging.LoggerAdapter(logger, {"run_id": "-"})

    try:
        cfg = json.loads(args.config.read_text(encoding="utf-8"))
        results = run(args.raw_dir, cfg, args.db)
    except LoadError as error:
        run_failed.error("RUN FAILED: %s", error)
        sys.exit(1)
    except Exception as error:  # unexpected: concise on screen, full traceback in the log file
        run_failed.error("RUN FAILED unexpectedly: %s: %s (traceback in %s)",
                         type(error).__name__, error, log_dir / "pipeline.log", exc_info=True)
        sys.exit(1)
    print(f"\n{'file':32} {'status':8} {'read':>6} {'loaded':>7}  error")
    for r in results:
        print(f"{r['file']:32} {r['status']:8} {r['read']:>6} {r['loaded']:>7}  {r['error']}")
    if any(r["status"] == "failed" for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
