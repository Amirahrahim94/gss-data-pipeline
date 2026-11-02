"""Profile raw survey extracts (cuts) before building the pipeline.

Standard library only. Reads every file matching "input_files" in the config (any
number of cuts) and never modifies it. Dataset-specific names live in the config.

Reports: records per year, share of each response type per variable and year,
variables with no usable answers in a year, and ballot dependence. It describes
the data; enforcing rules is the loader's and dbt's job. Duplicate or keyless
records, inconsistent columns and shared respondents whose answers differ between cuts are listed in a
warning at the top and make the script exit 1.

Special missing codes are text like ".i:  Inapplicable" (letter after the dot).
"non_missing" only means "not a special missing code", not "valid".

Usage: python source/pipeline/profile_extracts.py [--raw-dir D] [--config F] [--out-dir D]
Output: data_profile_output.md and data_profile_detail.csv
"""
import argparse
import ast
import csv
import hashlib
import itertools
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MISSING = re.compile(r"^\.([a-z]):")
LABELS = {"i": "inapplicable", "n": "no_answer", "d": "dont_know",
          "s": "skipped_on_web", "y": "unavailable_that_year",
          "x": "unavailable_in_release", "r": "refused", "j": "no_job",
          "p": "not_applicable_or_not_imputable", "m": "combined_DK_NA_IAP",
          "z": "reserve_code", "u": "uncodable", "f": "missing_birthdate",
          "q": "not_imputable"}


def classify(value):
    """Return the response type of one raw value."""
    if value is None or not str(value).strip():
        return "blank"
    match = MISSING.match(str(value).strip())
    return LABELS.get(match[1], f"missing_{match[1]}") if match else "non_missing"


def read_extract(path, keys):
    """Return (rows by respondent key, problems, parser, sha256, columns).

    Columns come from the first record; any record with a different column set
    is reported and skipped, so later code can rely on every row having them.
    """
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    try:
        data, parser = json.loads(text), "JSON"
    except json.JSONDecodeError:  # Data Explorer writes Python literals
        data, parser = ast.literal_eval(text), "Python literal (not strict JSON)"
    records = data.get("data") if isinstance(data, dict) else None
    if not isinstance(records, list) or not records or not isinstance(records[0], dict):
        sys.exit(f"{path.name}: expected a non-empty 'data' list of respondent dicts")
    columns = set(records[0])
    if not set(keys) <= columns:
        sys.exit(f"{path.name}: key columns {keys} are not all present")
    rows, problems = {}, []
    for i, row in enumerate(records):
        if not isinstance(row, dict) or set(row) != columns:
            problems.append(f"{path.name} record {i}: columns differ from the first record, skipped")
        elif any(row[k] in (None, "") for k in keys):
            problems.append(f"{path.name} record {i}: missing key, skipped")
        else:
            key = tuple(str(row[k]) for k in keys)
            if key in rows:
                problems.append(f"{path.name} record {i}: duplicate {key}, kept first")
            else:
                rows[key] = row
    if not rows:
        sys.exit(f"{path.name}: no usable records after validation")
    return rows, problems, parser, hashlib.sha256(raw).hexdigest(), columns


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--raw-dir", type=Path, default=ROOT / "source/data/raw")
    p.add_argument("--config", type=Path, default=ROOT / "source/config/profile_config.json")
    p.add_argument("--out-dir", type=Path, default=ROOT / "docs")
    args = p.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    year, ballot = cfg["year_column"], cfg.get("ballot_column")

    paths = sorted(args.raw_dir.glob(cfg["input_files"]))
    if not paths:
        sys.exit(f"No files matching {cfg['input_files']} in {args.raw_dir}")
    cuts, problems, files, schemas = {}, [], [], {}
    for path in paths:
        rows, found, parser, sha, columns = read_extract(path, cfg["key_columns"])
        cuts[path.stem], schemas[path.stem] = rows, columns
        problems += found
        files.append(f"- {path.name}: {len(rows):,} records, {parser}, SHA-256 {sha}")
    # Every file must have the same columns; profile only those they all share.
    first_name = next(iter(schemas))
    for name, columns in schemas.items():
        if columns != schemas[first_name]:
            problems.append(f"{name}: columns differ from {first_name} "
                            f"(only in this file: {sorted(columns - schemas[first_name])}, "
                            f"missing: {sorted(schemas[first_name] - columns)})")
    shared_columns = set.intersection(*schemas.values())
    first_row = next(iter(cuts[first_name].values()))
    variables = [c for c in first_row if c in shared_columns and c not in cfg["key_columns"]]

    # Overlap: shared respondents per pair, whether they agree, and each cut's own years.
    overlap = []
    for a, b in itertools.combinations(cuts, 2):
        shared = cuts[a].keys() & cuts[b].keys()
        differ = [k for k in shared if cuts[a][k] != cuts[b][k]]
        overlap.append(f"- {a} / {b}: {len(shared):,} shared "
                       f"({len(shared) / len(cuts[a]):.1%} of {a}, {len(shared) / len(cuts[b]):.1%} of {b}); "
                       f"{len(differ):,} with different answers")
        if differ:
            problems.append(f"{a} / {b}: {len(differ)} shared respondents have different answers, "
                            f"e.g. {differ[0]}")
    years = {n: {str(r[year]) for r in rows.values()} for n, rows in cuts.items()}
    for n in cuts:
        others = set().union(*(years[m] for m in cuts if m != n))
        overlap.append(f"- years only in {n}: {sorted(years[n] - others) or 'none'}")
    # Each respondent once; on a conflict the first cut wins (conflicts are flagged above).
    combined = {}
    for rows in cuts.values():
        for k, r in rows.items():
            combined.setdefault(k, r)
    overlap.insert(0, f"- distinct respondents overall: {len(combined):,}")

    detail, tables, flags = [], [], []
    for scope, rows in {**cuts, "combined_distinct": combined}.items():
        by_year = defaultdict(list)
        for row in rows.values():
            by_year[str(row[year])].append(row)
        tables += ["", f"### {scope}", "", "Records per year: " + ", ".join(
                   f"{y}: {len(g):,}" for y, g in sorted(by_year.items())), "",
                   "| year | variable | non-missing % | special missing % | blank % |",
                   "|---|---|---:|---:|---:|"]
        for y, group in sorted(by_year.items()):
            n = len(group)
            for v in variables:
                types = Counter(classify(row[v]) for row in group)
                special = n - types["non_missing"] - types["blank"]
                tables.append(f"| {y} | {v} | {types['non_missing'] / n * 100:.2f} | "
                              f"{special / n * 100:.2f} | {types['blank'] / n * 100:.2f} |")
                for t in sorted(set(types) | {"non_missing"}):
                    labels = {str(r[v]) for r in group if classify(r[v]) == t and t != "non_missing"}
                    detail.append({"cut": scope, "year": y, "variable": v, "response_type": t,
                                   "source_labels": " ; ".join(sorted(labels)), "count": types[t],
                                   "year_records": n, "percentage": round(types[t] / n * 100, 4)})
                if types["non_missing"] == 0:
                    top, count = types.most_common(1)[0]
                    flags.append(f"- {v} in {y} ({scope}): no non-missing values; "
                                 f"{count / n * 100:.0f}% are '{top}'")

    ballots = []
    if ballot:
        rates = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # (year, var) -> ballot -> [ok, n]
        for row in combined.values():
            for v in variables:
                cell = rates[(str(row[year]), v)][row[ballot]]
                cell[0] += classify(row[v]) == "non_missing"
                cell[1] += 1
        for (y, v), by_b in sorted(rates.items()):
            pct = {b: ok / n * 100 for b, (ok, n) in by_b.items()}
            if max(pct.values()) - min(pct.values()) >= 40:
                ballots.append(f"- {v} in {y}: " + ", ".join(f"{b} {r:.0f}%" for b, r in sorted(pct.items())))

    out = ["# Data profile of the raw extracts", ""]
    if problems:
        out += [f"**WARNING: {len(problems)} problem(s) while reading; figures may be unreliable. "
                "Records with duplicate keys, missing keys or different columns are excluded from all counts.**", ""]
        out += [f"- {x}" for x in problems[:10]] + [""]
    out += ["## Files read (never modified)", ""] + files
    out += ["", "## Respondents and overlap", ""] + overlap
    out += ["", "## Variables with no non-missing values in a year", "",
            "Cause is not established by the data alone (year, ballot or eligibility); "
            "only an explicit '.y' supports 'unavailable that year'.", ""] + (flags or ["- none"])
    out += ["", "## Variables whose answers depend on the ballot", "",
            "Share of non-missing values differs by 40+ points between ballots; "
            "confirm the cause in the survey documentation.", ""] + (ballots or ["- none"])
    out += ["", "## Response types by year and variable (unweighted)"] + tables

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "data_profile_output.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    with (args.out_dir / "data_profile_detail.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(detail[0]))
        writer.writeheader()
        writer.writerows(detail)
    print("\n".join(out[:out.index("## Response types by year and variable (unweighted)")]))
    if problems:
        sys.exit(f"Exiting with status 1: {len(problems)} problem(s) while reading.")


if __name__ == "__main__":
    main()
