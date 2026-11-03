"""Read and validate one raw extract. Shared by the profiler and the loader.

One reader means both tools apply the same rules. The Data Explorer writes Python
literals (single quotes) in files named .json, so strict JSON is tried first and
ast.literal_eval is the fallback (never eval).
"""
import ast
import hashlib
import json
import math
import re
from typing import NamedTuple

# Special missing labels look like ".i:  Inapplicable". They must never be identifiers.
MISSING_LABEL = re.compile(r"^\.[a-z]:")


# Response type for each special-missing letter (".i:  Inapplicable" -> "i"). One definition,
# shared by the profiler and the reference-seed builder, so they cannot disagree.
MISSING_TYPES = {"i": "inapplicable", "n": "no_answer", "d": "dont_know",
                 "s": "skipped_on_web", "y": "unavailable_that_year",
                 "x": "unavailable_in_release", "r": "refused", "j": "no_job",
                 "p": "not_applicable_or_not_imputable", "m": "combined_dk_na_iap",
                 "z": "reserve_code", "u": "uncodable", "f": "missing_birthdate",
                 "q": "not_imputable"}

# Columns the loader adds to every raw row; a source column may not use these names.
RESERVED_COLUMNS = {"extract_id", "source_file", "file_sha256", "record_sha256", "run_id", "loaded_at"}


class ExtractError(Exception):
    """The file cannot be used at all (unreadable, wrong structure, no usable records)."""


class Extract(NamedTuple):
    rows: dict          # {key tuple: record} for the records that passed validation
    problems: list      # one message per rejected or suspicious record
    parser: str         # "JSON" or "Python literal (not strict JSON)"
    sha256: str         # fingerprint of the file's bytes
    columns: set        # column names, taken from the first record
    record_count: int   # records in the file as received, before validation
    metadata: dict      # the export's own "variables" and "codes" sections, if present


def reject_repeated_fields(pairs):
    """JSON object hook: a repeated field name would silently keep only the last value."""
    obj = {}
    for name, value in pairs:
        if name in obj:
            raise ValueError(f"repeated field name {name!r}")
        obj[name] = value
    return obj


def parse_literal(text):
    """ast.literal_eval, but refuse repeated dictionary keys (it keeps the last silently)."""
    tree = ast.parse(text, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            names = [ast.literal_eval(k) for k in node.keys if k is not None]
            if len(names) != len(set(names)):
                raise ValueError("repeated field name in a record")
    return ast.literal_eval(tree)


def key_problem(value):
    """Why a respondent identifier is unusable, or None if it is fine."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return f"type {type(value).__name__}"
    text = str(value)
    if not text.strip():
        return "blank"
    if text != text.strip():
        return "surrounding whitespace"
    if MISSING_LABEL.match(text):
        return "special missing label"
    return None


def value_problem(value):
    """Why a value cannot be stored as received, or None if it is fine."""
    if value is None or isinstance(value, (str, int)):
        return None
    if isinstance(value, float):
        return None if math.isfinite(value) else "non-finite number"
    return f"unsupported type {type(value).__name__}"


def read_extract(path, keys, records_key="data", max_file_bytes=None):
    """Read and validate one file. Raise ExtractError only if it is unusable as a whole.

    records_key names the list of respondent records in the export; max_file_bytes
    (optional) refuses a larger file before it is parsed in memory.

    Columns come from the first record. A record is skipped and reported if its
    columns differ, a key or value is unusable, or its key is a duplicate (the first
    one is kept). The caller decides whether problems are fatal.
    """
    try:
        with path.open("rb") as handle:
            raw = handle.read() if max_file_bytes is None else handle.read(max_file_bytes + 1)
    except OSError as error:
        raise ExtractError(f"{path.name}: cannot be read ({error})") from error
    if max_file_bytes is not None and len(raw) > max_file_bytes:
        raise ExtractError(f"{path.name}: larger than max_file_bytes ({max_file_bytes:,})")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ExtractError(f"{path.name}: not valid UTF-8 ({error})") from error
    try:
        data, parser = json.loads(text, object_pairs_hook=reject_repeated_fields), "JSON"
    except json.JSONDecodeError:  # not strict JSON: try the provider's Python-literal format
        try:
            data, parser = parse_literal(text), "Python literal (not strict JSON)"
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError) as error:
            raise ExtractError(f"{path.name}: not JSON or a Python literal ({error})") from error
    except ValueError as error:  # strict JSON, but with a repeated field name
        raise ExtractError(f"{path.name}: {error}") from error

    records = data.get(records_key) if isinstance(data, dict) else None
    if not isinstance(records, list) or not records or not isinstance(records[0], dict):
        raise ExtractError(f"{path.name}: expected a non-empty '{records_key}' list of respondent dicts")
    columns = set(records[0])
    if not set(keys) <= columns:
        raise ExtractError(f"{path.name}: key columns {keys} are not all present")

    clashes = sorted(c for c in columns if str(c).lower() in RESERVED_COLUMNS)
    if clashes:
        raise ExtractError(f"{path.name}: column name(s) {clashes} clash with loader metadata columns")
    if len({str(c).lower() for c in columns}) != len(columns):
        raise ExtractError(f"{path.name}: column names collide when case is ignored")

    rows, problems = {}, []
    for i, row in enumerate(records):
        where = f"{path.name} record {i}"
        if not isinstance(row, dict) or set(row) != columns:
            problems.append(f"{where}: columns differ from the first record, skipped")
            continue
        bad_key = next(((k, key_problem(row[k])) for k in keys if key_problem(row[k])), None)
        if bad_key:
            problems.append(f"{where}: invalid key {bad_key[0]} ({bad_key[1]}), skipped")
            continue
        bad_value = next(((c, value_problem(v)) for c, v in row.items() if value_problem(v)), None)
        if bad_value:
            problems.append(f"{where}: unusable value in {bad_value[0]} ({bad_value[1]}), skipped")
            continue
        key = tuple(str(row[k]) for k in keys)
        if key in rows:
            problems.append(f"{where}: duplicate {key}, kept first")
        else:
            rows[key] = row
    if not rows:
        raise ExtractError(f"{path.name}: no usable records after validation")
    metadata = {name: data[name] for name in ("variables", "codes") if name in data}
    return Extract(rows, problems, parser, hashlib.sha256(raw).hexdigest(), columns,
                   len(records), metadata)
