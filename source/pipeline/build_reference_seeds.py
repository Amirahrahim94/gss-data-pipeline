"""Create the CSV reference files that explain the survey data to dbt.

A dbt seed is a CSV file that dbt loads into the database as a reference table.
This script reads the configured survey extracts and creates three seed files:

  ref_variables.csv
      Lists each variable, its description and its question text.

  ref_codes.csv
      Explains each variable's codes and readable labels. Also identifies
      genuine answers and special missing types, such as "don't know".

  ref_variable_validity.csv
      Records whether at least one real answer was observed for each variable,
      survey year and ballot (questionnaire version).

Important: the column is_asked describes observed answers, not a confirmed
questionnaire rule. True means at least one real answer was found in that group.
False means no real answer was found; it does not prove the question was not
asked. Downstream dbt models use this pattern to infer not_asked_on_ballot
from some .i values. That interpretation still needs questionnaire verification.

The source files are read without being changed. Shared respondent-year keys
are counted once when checking answer coverage. The loader is responsible for
checking that overlapping records have identical values; this script does not
repeat that check.

If extracts disagree about variable or code definitions, stop before writing
the seed files. All three sets of rows are prepared before writing starts,
but writing the three CSV files is not one atomic operation.

Commit the generated seeds so reviewers can inspect the definitions without
running the pipeline. Rows are sorted to keep the output stable when the
inputs and configuration are unchanged.

Usage: python source/pipeline/build_reference_seeds.py [--raw-dir D] [--config F] [--out-dir D]
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
    """An error that prevents the extracts from sharing one consistent set of reference definitions."""


def collect(raw_dir, cfg):
    """Read the matching extracts and collect definitions and respondent records.

    Return the variable definitions, code definitions and records keyed by
    respondent-year. For a key found in several files, keep the first record.
    This function checks agreement between metadata sections, not between
    overlapping respondents' answers."""
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
            # Keep the first record for a shared key so coverage does not count it twice.
            records.setdefault(key, record)
    first_name, (first_variables, first_codes) = next(iter(found.items()))
    # Compare sorted entries so a different list order alone does not cause a mismatch.
    for name, (variables, codes) in found.items():
        if sorted(map(json.dumps, variables)) != sorted(map(json.dumps, first_variables)):
            raise SeedError(f"{name} and {first_name} describe the variables differently")
        if sorted(map(json.dumps, codes)) != sorted(map(json.dumps, first_codes)):
            raise SeedError(f"{name} and {first_name} define the codes differently")
    return first_variables, first_codes, records


def build_tables(variables, codes):
    """Prepare the rows for ref_variables.csv and ref_codes.csv.

    Reject repeated variable definitions, repeated codes within a variable,
    and codes that cannot be converted to whole numbers. Classify special
    missing labels using the definitions shared with the extract reader."""
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
        # Keep an unfamiliar missing-code letter as missing_<letter>; do not call it an answer.
        response_type = MISSING_TYPES.get(letter, f"missing_{letter}") if match else "answer"
        code_rows[(variable, code)] = [variable, code, label, response_type, letter]

    return [variable_rows[k] for k in sorted(variable_rows)], [code_rows[k] for k in sorted(code_rows)]


def is_real_answer(value):
    """Check whether a value is non-empty and is not a special missing label.

    This does not check whether the answer is valid for its variable.
    Text such as "None" or "Never", and the number zero, can be real answers."""
    return value is not None and str(value).strip() != "" and not MISSING_LABEL.match(str(value))


def build_validity(records, cfg):
    """Summarise observed answer coverage by variable, year and ballot.

    is_asked becomes true if any record in that group has a non-empty value
    without a special missing label. Otherwise it stays false. This is an
    observation from the extracts, not proof of questionnaire assignment."""
    year_column, ballot_column = cfg["year_column"], cfg["ballot_column"]
    # Keys and ballot are not survey questions, so summarise only the other source fields.
    skip = set(cfg["key_columns"]) | {ballot_column}
    asked = {}
    for record in records.values():
        year, ballot = int(record[year_column]), record[ballot_column]
        for variable, value in record.items():
            if variable in skip:
                continue
            key = (variable, year, ballot)
            # Once an answer is found, this group stays true even if other records are missing.
            asked[key] = asked.get(key, False) or is_real_answer(value)
    # Sort rows and write booleans as the text true/false for the CSV seed.
    return [[variable, year, ballot, str(is_asked).lower()]
            for (variable, year, ballot), is_asked in sorted(asked.items())]


def write_csv(path, header, rows):
    """Write one seed file with a header and its prepared rows, replacing an existing file."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def main():
    """Read settings, prepare the three seeds, then write them to the output folder.

    If a handled error occurs during preparation, exit before writing files."""
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--raw-dir", type=Path, default=ROOT / "source/data/raw")
    p.add_argument("--config", type=Path, default=ROOT / "source/config/extract_config.json")
    p.add_argument("--out-dir", type=Path, default=ROOT / "dbt/seeds")
    args = p.parse_args()
    try:
        cfg = json.loads(args.config.read_text(encoding="utf-8"))
        # Prepare every seed before opening any output file.
        variables_meta, codes_meta, records = collect(args.raw_dir, cfg)
        variables, codes = build_tables(variables_meta, codes_meta)
        validity = build_validity(records, cfg)
    except (ExtractError, SeedError, KeyError, OSError) as error:
        sys.exit(f"Seeds not written: {type(error).__name__}: {error}")
    # Write the three files in order. A write failure can leave only some files updated.
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
