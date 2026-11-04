"""Build the dbt reference seeds (ref_*) from the extracts' own variable and code metadata.

Reads every file matching "input_files" in the config with the shared reader and writes
three CSV files that dbt loads with `dbt seed`:

  ref_variables.csv          one row per variable: label and question text
  ref_codes.csv              one row per variable and code: label, and its response type
                             ("answer" or the kind of special missing value)
  ref_variable_validity.csv  one row per variable, survey year and ballot: whether
                             anyone on that ballot answered (is_asked, observed)

is_asked is observed, not read from the codebook: it is true when at least one respondent
in that year and ballot gave a real answer. The export carries no questionnaire design, so
this is the best machine-readable evidence available. It does not prove questionnaire
assignment: the GSS questionnaires are the authority, and a disagreement with them should be
fixed here. dbt uses the seed to tell "not on this
ballot" apart from "did not apply to this respondent", which share the code ".i".

The seeds are committed so the meaning of every code is reviewable without running
anything. Rerunning this script gives byte-identical files. If the extracts disagree about
a variable or a code, it stops and writes nothing: one set of seeds cannot describe both.

Usage:  python source/pipeline/build_reference_seeds.py [--raw-dir D] [--config F] [--out-dir D]
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

from extract_reader import MISSING_LABEL, MISSING_TYPES, ExtractError, read_extract

ROOT = Path(__file__).resolve().parents[2]
LETTER = re.compile(r"^\.([a-z]):\s*(.*)$")


class SeedError(Exception):
    """The metadata cannot be turned into one consistent set of seeds."""


def collect(raw_dir, cfg):
    """Return (variables, codes, records) from every matching extract.

    variables and codes must agree across extracts. records holds each respondent-year once
    ({key: record}); the loader already guarantees shared respondent-years are identical.
    """
    paths = sorted(Path(raw_dir).glob(cfg["input_files"]))
    if not paths:
        raise SeedError(f"no files matching {cfg['input_files']} in {raw_dir}")
    found, records = {}, {}
    for path in paths:
        extract = read_extract(path, cfg["key_columns"], cfg.get("records_key", "data"),
                               cfg.get("max_file_bytes"))
        missing = [name for name in ("variables", "codes") if name not in extract.metadata]
        if missing:
            raise SeedError(f"{path.name}: no {' or '.join(missing)} section in the export")
        found[path.name] = (extract.metadata["variables"], extract.metadata["codes"])
        for key, record in extract.rows.items():
            records.setdefault(key, record)
    first_name, (first_variables, first_codes) = next(iter(found.items()))
    # Sorted before comparing: two exports may list the same metadata in a different order.
    for name, (variables, codes) in found.items():
        if sorted(map(json.dumps, variables)) != sorted(map(json.dumps, first_variables)):
            raise SeedError(f"{name} and {first_name} describe the variables differently")
        if sorted(map(json.dumps, codes)) != sorted(map(json.dumps, first_codes)):
            raise SeedError(f"{name} and {first_name} define the codes differently")
    return first_variables, first_codes, records


def build_tables(variables, codes):
    """Turn the export's metadata into the rows of the two seeds."""
    variable_rows = {}
    for item in variables:
        name = item["name"]
        if name in variable_rows:
            raise SeedError(f"variable {name!r} is described twice")
        variable_rows[name] = [name, item.get("label") or "", item.get("Question Text") or ""]

    code_rows = {}
    for item in codes:
        variable, label = item["variableName"], item["label"]
        try:
            code = int(item["code"])
        except (TypeError, ValueError):
            raise SeedError(f"{variable}: code {item['code']!r} is not a whole number") from None
        if (variable, code) in code_rows:
            raise SeedError(f"{variable}: code {code} is defined twice")
        match = LETTER.match(label)
        letter = match[1] if match else ""
        # An unknown letter stays a missing type under its own name, never read as an answer.
        response_type = MISSING_TYPES.get(letter, f"missing_{letter}") if match else "answer"
        code_rows[(variable, code)] = [variable, code, label, response_type, letter]

    return [variable_rows[k] for k in sorted(variable_rows)], [code_rows[k] for k in sorted(code_rows)]


def is_real_answer(value):
    """A value counts as an answer unless it is empty or a special missing label."""
    return value is not None and str(value).strip() != "" and not MISSING_LABEL.match(str(value))


def build_validity(records, cfg):
    """One row per (variable, survey year, ballot): whether anyone there gave a real answer."""
    year_column, ballot_column = cfg["year_column"], cfg["ballot_column"]
    skip = set(cfg["key_columns"]) | {ballot_column}
    asked = {}
    for record in records.values():
        year, ballot = int(record[year_column]), record[ballot_column]
        for variable, value in record.items():
            if variable in skip:
                continue
            key = (variable, year, ballot)
            asked[key] = asked.get(key, False) or is_real_answer(value)
    return [[variable, year, ballot, str(is_asked).lower()]
            for (variable, year, ballot), is_asked in sorted(asked.items())]


def write_csv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--raw-dir", type=Path, default=ROOT / "source/data/raw")
    p.add_argument("--config", type=Path, default=ROOT / "source/config/extract_config.json")
    p.add_argument("--out-dir", type=Path, default=ROOT / "dbt/seeds")
    args = p.parse_args()
    try:
        cfg = json.loads(args.config.read_text(encoding="utf-8"))
        variables_meta, codes_meta, records = collect(args.raw_dir, cfg)
        variables, codes = build_tables(variables_meta, codes_meta)
        validity = build_validity(records, cfg)
    except (ExtractError, SeedError, KeyError, OSError) as error:
        sys.exit(f"Seeds not written: {type(error).__name__}: {error}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "ref_variables.csv", ["variable_name", "label", "question_text"], variables)
    write_csv(args.out_dir / "ref_codes.csv",
              ["variable_name", "code", "label", "response_type", "missing_code_letter"], codes)
    write_csv(args.out_dir / "ref_variable_validity.csv",
              ["variable_name", "survey_year", "ballot", "is_asked"], validity)
    print(f"Wrote {len(variables)} variables, {len(codes)} codes and {len(validity)} "
          f"validity rows to {args.out_dir}")


if __name__ == "__main__":
    main()
