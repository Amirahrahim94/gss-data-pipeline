"""Check the raw survey files before loading them into the pipeline.

Uses Python's standard library and the project's extract_reader module.
Reads all files matching "input_files" in the config without changing them.
The config also specifies the respondent key, year column and ballot column.
Each survey extract is called a "cut" in the output.

The reports show record counts by year, response types for each variable,
variables with no non-missing answers, and differences between ballot groups.
The script also checks whether respondents shared by two cuts have the same
answers. A respondent-year means one respondent in one survey year.

Duplicate keys, missing keys, inconsistent columns and conflicting answers
are reported as warnings. If any problems are found, the reports are still
written, but the script exits with status 1 to signal that checks failed.
An unreadable input file stops the script immediately.

Special missing values contain codes such as ".i:  Inapplicable".
"non_missing" means the value is neither blank nor a special missing code;
it does not mean the answer has been validated. The loader and dbt enforce
the pipeline's data quality rules.

Usage: python source/pipeline/profile_extracts.py [--raw-dir D] [--config F] [--out-dir D]
Output: data_profile_summary.md and data_profile_detail.csv
"""
import argparse
import csv
import itertools
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from extract_reader import MISSING_TYPES, ExtractError, read_extract

ROOT = Path(__file__).resolve().parents[2]
MISSING = re.compile(r"^\.([a-z]):")


def classify(value):
    """Label a value as blank, a special missing type, or non_missing."""
    if value is None or not str(value).strip():
        return "blank"
    match = MISSING.match(str(value).strip())
    return MISSING_TYPES.get(match[1], f"missing_{match[1]}") if match else "non_missing"


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--raw-dir", type=Path, default=ROOT / "source/data/raw")
    p.add_argument("--config", type=Path, default=ROOT / "source/config/extract_config.json")
    p.add_argument("--out-dir", type=Path, default=ROOT / "docs")
    args = p.parse_args()
    # Read the config to find the input files and column names.
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    year, ballot = cfg["year_column"], cfg.get("ballot_column")

    paths = sorted(args.raw_dir.glob(cfg["input_files"]))
    if not paths:
        sys.exit(f"No files matching {cfg['input_files']} in {args.raw_dir}")
    # Read each cut and collect its records, column names and any input problems.
    cuts, problems, files, schemas = {}, [], [], {}
    for path in paths:
        try:
            ext = read_extract(path, cfg["key_columns"], cfg.get("records_key", "data"), cfg.get("max_file_bytes"))
        except ExtractError as error:
            sys.exit(f"Unusable input: {error}")
        cuts[path.stem], schemas[path.stem] = ext.rows, ext.columns
        problems += ext.problems
        files.append(f"- {path.name}: {len(ext.rows):,} usable of {ext.record_count:,} records, "
                     f"{ext.parser}, SHA-256 {ext.sha256}")
    # Report column differences between files. Profile only columns present in every file.
    # Leave respondent key columns out of the variable-level response summaries.
    first_name = next(iter(schemas))
    for name, columns in schemas.items():
        if columns != schemas[first_name]:
            problems.append(f"{name}: columns differ from {first_name} "
                            f"(only in this file: {sorted(columns - schemas[first_name])}, "
                            f"missing: {sorted(schemas[first_name] - columns)})")
    shared_columns = set.intersection(*schemas.values())
    first_row = next(iter(cuts[first_name].values()))
    variables = [c for c in first_row if c in shared_columns and c not in cfg["key_columns"]]

    # Compare every pair of cuts: count shared respondent keys and check their answers.
    overlap, conflict_found = [], False
    for a, b in itertools.combinations(cuts, 2):
        shared = cuts[a].keys() & cuts[b].keys()
        differ = [k for k in shared if cuts[a][k] != cuts[b][k]]
        overlap.append(f"- {a} / {b}: {len(shared):,} shared "
                       f"({len(shared) / len(cuts[a]):.1%} of {a}, {len(shared) / len(cuts[b]):.1%} of {b}); "
                       f"{len(differ):,} with different answers")
        if differ:
            conflict_found = True
            problems.append(f"{a} / {b}: {len(differ)} shared respondents have different answers, "
                            f"e.g. {differ[0]}")
    # List survey years that appear in only one cut.
    years = {n: {str(r[year]) for r in rows.values()} for n, rows in cuts.items()}
    for n in cuts:
        others = set().union(*(years[m] for m in cuts if m != n))
        overlap.append(f"- years only in {n}: {sorted(years[n] - others) or 'none'}")
    # Build a combined dataset with each respondent-year counted once.
    # If shared records disagree, skip the combined profile because choosing
    # one cut would require a rule for deciding which answers to trust.
    distinct = set().union(*(rows.keys() for rows in cuts.values()))
    overlap.insert(0, f"- distinct respondent-years overall: {len(distinct):,}")
    combined = {}
    if conflict_found:
        overlap.append("- combined profile and ballot comparison OMITTED: shared respondent-years "
                       "have conflicting answers, so there is no reliable combined set")
    else:
        for rows in cuts.values():
            for k, r in rows.items():
                combined.setdefault(k, r)

    # Summarise each cut separately and, when possible, the combined dataset.
    detail, tables, flags = [], [], []
    scopes = {**cuts} if conflict_found else {**cuts, "combined_distinct": combined}
    for scope, rows in scopes.items():
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
                # Count response types and calculate their share of records in this year.
                types = Counter(classify(row[v]) for row in group)
                special = n - types["non_missing"] - types["blank"]
                tables.append(f"| {y} | {v} | {types['non_missing'] / n * 100:.2f} | "
                              f"{special / n * 100:.2f} | {types['blank'] / n * 100:.2f} |")
                # Add detailed counts and missing-value labels to the CSV output.
                for t in sorted(set(types) | {"non_missing"}):
                    labels = {str(r[v]) for r in group if classify(r[v]) == t and t != "non_missing"}
                    detail.append({"cut": scope, "year": y, "variable": v, "response_type": t,
                                   "source_labels": " ; ".join(sorted(labels)), "count": types[t],
                                   "year_records": n, "percentage": round(types[t] / n * 100, 4)})
                # Flag variables with no non-missing answers in this year.
                if types["non_missing"] == 0:
                    top, count = types.most_common(1)[0]
                    flags.append(f"- {v} in {y} ({scope}): no non-missing values; "
                                 f"{count / n * 100:.0f}% are '{top}'")

    # Compare response coverage across ballot groups using the combined dataset.
    # Ballots are survey versions that may contain different sets of questions.
    ballots, no_ballot = [], 0
    if ballot and combined:
        # For each year, variable and ballot, store [non-missing count, total count].
        rates = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        for row in combined.values():
            # Skip records whose ballot label is blank or a special missing value.
            if classify(row[ballot]) != "non_missing":
                no_ballot += 1
                continue
            for v in variables:
                cell = rates[(str(row[year]), v)][row[ballot]]
                cell[0] += classify(row[v]) == "non_missing"
                cell[1] += 1
        for (y, v), by_b in sorted(rates.items()):
            pct = {b: ok / n * 100 for b, (ok, n) in by_b.items()}
            # Flag a gap of at least 40 percentage points between ballot groups.
            # This shows a coverage difference; it does not explain its cause.
            if max(pct.values()) - min(pct.values()) >= 40:
                ballots.append(f"- {v} in {y}: " + ", ".join(
                    f"{b} {pct[b]:.0f}% (n={by_b[b][1]:,})" for b in sorted(pct)))

    # Assemble the Markdown report, with input warnings shown first.
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
    out += ["", "## Observed response coverage by ballot", "",
            "Variables whose share of non-missing values differs by 40+ points between ballots "
            "(n = respondent-years in that ballot group). These are observed rates, not proof of "
            "questionnaire assignment: confirm the cause in the survey documentation. "
            f"Respondent-years with no usable ballot label are left out: {no_ballot:,}.", ""] + (
            ballots or (["- omitted"] if conflict_found else ["- none"]))
    out += ["", "## Response types by year and variable (unweighted)"] + tables

    # Save both reports, then print the summary sections to the terminal.
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "data_profile_summary.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    with (args.out_dir / "data_profile_detail.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(detail[0]))
        writer.writeheader()
        writer.writerows(detail)
    print("\n".join(out[:out.index("## Response types by year and variable (unweighted)")]))
    if problems:
        sys.exit(f"Exiting with status 1: {len(problems)} problem(s) while reading.")


if __name__ == "__main__":
    main()
