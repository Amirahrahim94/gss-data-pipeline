"""Read a downloaded survey file and check its structure and records.

This shared reader is used by other scripts, including the profiler, loader
and reference-seed builder, so they do not need separate file-reading rules.
It does not load a database or change the downloaded file.

Try standard JSON first. If that fails because of JSON syntax, try the
Python-literal format used by these GSS exports, which can contain single
quotes. Use ast.literal_eval to read that format; never execute it with eval.

Return valid records, a list of record problems, file information and the
export's variable/code metadata. A calling script decides what to do with
reported record problems. The loader rejects a file that has any problems.
If the file cannot be read or has no usable records, raise ExtractError."""
import ast
import hashlib
import json
import math
import re
from typing import NamedTuple

# Recognise special missing labels such as ".i: Inapplicable". Do not allow them in key fields.
MISSING_LABEL = re.compile(r"^\.[a-z]:")


# Translate each missing-code letter into a readable response type.
# The profiler and seed builder reuse this mapping instead of defining their own.
MISSING_TYPES = {"i": "inapplicable", "n": "no_answer", "d": "dont_know",
                 "s": "skipped_on_web", "y": "unavailable_that_year",
                 "x": "unavailable_in_release", "r": "refused", "j": "no_job",
                 "p": "not_applicable_or_not_imputable", "m": "combined_dk_na_iap",
                 "z": "reserve_code", "u": "uncodable", "f": "missing_birthdate",
                 "q": "not_imputable"}

# These names belong to the loader's tracking fields, so survey columns cannot use them.
RESERVED_COLUMNS = {"extract_id", "source_file", "file_sha256", "record_sha256", "run_id", "loaded_at"}


class ExtractError(Exception):
    """The file cannot be read or does not contain a usable set of records."""


class Extract(NamedTuple):
    """The result returned to a script after reading an extract.

    rows contains records that passed the checks; problems explains records
    left out. The remaining fields describe the source file and its metadata."""
    rows: dict          # Records that passed validation, indexed by a tuple such as ("2018", "1042").
    problems: list      # Messages explaining records skipped or duplicates found.
    parser: str         # Which file format was successfully read.
    sha256: str         # SHA-256 fingerprint used to identify the exact file content.
    columns: set        # Expected field names, taken from the first record.
    record_count: int   # Total source records, including those that fail checks.
    metadata: dict      # Original variable and code definitions, when provided.


def reject_repeated_fields(pairs):
    """Build a JSON object while checking for repeated field names.

    For example, reject {"year": 2018, "year": 2022} instead of silently
    keeping just the second year. json.loads calls this function for objects."""
    obj = {}
    for name, value in pairs:
        if name in obj:
            raise ValueError(f"repeated field name {name!r}")
        obj[name] = value
    return obj


def parse_literal(text):
    """Read Python-literal data after checking dictionaries for repeated keys.

    Inspect the parsed structure first because ast.literal_eval alone would
    keep only the last value for a repeated dictionary key."""
    tree = ast.parse(text, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            names = [ast.literal_eval(k) for k in node.keys if k is not None]
            if len(names) != len(set(names)):
                raise ValueError("repeated field name in a record")
    return ast.literal_eval(tree)


def key_problem(value):
    """Explain why a key field is invalid, or return None if it passes.

    A key component, such as year or respondent ID, must be an integer or
    non-blank string. Reject booleans, surrounding spaces and special missing
    labels so they cannot be used as respondent identifiers."""
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
    """Explain why an ordinary field value is unsupported, or return None.

    Accept nulls, strings, integers and finite decimal numbers. Booleans also
    pass because Python treats bool as a kind of int. Reject nested values
    such as lists or dictionaries, and non-finite numbers such as infinity.
    This checks the value's form, not its meaning for a survey question."""
    if value is None or isinstance(value, (str, int)):
        return None
    if isinstance(value, float):
        return None if math.isfinite(value) else "non-finite number"
    return f"unsupported type {type(value).__name__}"


def read_extract(path, keys, records_key="data", max_file_bytes=None):
    """Read a file and return its usable records plus any record problems.

    keys lists the fields that identify a record, usually year and id_.
    records_key names the list containing records, usually "data".
    max_file_bytes optionally limits how many bytes can be read before parsing.

    Use the first record's column names as the expected structure. Leave out
    later records with different columns, invalid keys or unsupported values.
    If keys repeat, keep the first valid record and report the duplicate.
    Record positions in messages start at zero.

    Raise ExtractError for a file-level problem. Otherwise return an Extract;
    the calling script decides whether reported record problems reject the file."""
    # Read bytes first so the fingerprint represents the original file content.
    # With a size limit, read one extra byte to detect a file that exceeds it.
    try:
        with path.open("rb") as handle:
            raw = handle.read() if max_file_bytes is None else handle.read(max_file_bytes + 1)
    except OSError as error:
        raise ExtractError(f"{path.name}: cannot be read ({error})") from error
    if max_file_bytes is not None and len(raw) > max_file_bytes:
        raise ExtractError(f"{path.name}: larger than max_file_bytes ({max_file_bytes:,})")
    try:
        # Also accept UTF-8 files that start with a byte-order mark.
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ExtractError(f"{path.name}: not valid UTF-8 ({error})") from error
    try:
        data, parser = json.loads(text, object_pairs_hook=reject_repeated_fields), "JSON"
    except json.JSONDecodeError:  # If JSON syntax fails, try the export's Python-literal format.
        try:
            data, parser = parse_literal(text), "Python literal (not strict JSON)"
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError) as error:
            raise ExtractError(f"{path.name}: not JSON or a Python literal ({error})") from error
    except ValueError as error:  # A repeated JSON field is an error, not a reason to try another format.
        raise ExtractError(f"{path.name}: {error}") from error

    # Require a top-level dictionary containing a non-empty list of records.
    records = data.get(records_key) if isinstance(data, dict) else None
    if not isinstance(records, list) or not records or not isinstance(records[0], dict):
        raise ExtractError(f"{path.name}: expected a non-empty '{records_key}' list of respondent dicts")
    columns = set(records[0])
    if not set(keys) <= columns:
        raise ExtractError(f"{path.name}: key columns {keys} are not all present")

    # Check names without case sensitivity, so Year and year cannot be separate columns.
    # Also prevent source fields from using the loader's reserved tracking names.
    clashes = sorted(c for c in columns if str(c).lower() in RESERVED_COLUMNS)
    if clashes:
        raise ExtractError(f"{path.name}: column name(s) {clashes} clash with loader metadata columns")
    if len({str(c).lower() for c in columns}) != len(columns):
        raise ExtractError(f"{path.name}: column names collide when case is ignored")

    # Collect record problems instead of stopping at the first invalid record.
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
        # Compare key values as text; integer 2018 and string "2018" identify the same year.
        key = tuple(str(row[k]) for k in keys)
        if key in rows:
            problems.append(f"{where}: duplicate {key}, kept first")
        else:
            rows[key] = row
    if not rows:
        raise ExtractError(f"{path.name}: no usable records after validation")
    # Pass through the export's definitions; this reader does not validate their contents.
    metadata = {name: data[name] for name in ("variables", "codes") if name in data}
    return Extract(rows, problems, parser, hashlib.sha256(raw).hexdigest(), columns,
                   len(records), metadata)
