"""Build the dbt reference seeds (ref_*) from the extracts' own variable and code metadata.

Reads every file matching "input_files" in the config with the shared reader and writes
two CSV files that dbt loads with `dbt seed`:

  ref_variables.csv      one row per variable: label and question text
  ref_codes.csv          one row per variable and code: label, and its response type
                         ("answer" or the kind of special missing value)

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

from extract_reader import MISSING_TYPES, ExtractError, read_extract

ROOT = Path(__file__).resolve().parents[2]
LETTER = re.compile(r"^\.([a-z]):\s*(.*)$")


class SeedError(Exception):
    """The metadata cannot be turned into one consistent set of seeds."""


def collect(raw_dir, cfg):
    """Return (variables, codes) taken from every matching extract; they must all agree."""
    paths = sorted(Path(raw_dir).glob(cfg["input_files"]))
    if not paths:
        raise SeedError(f"no files matching {cfg['input_files']} in {raw_dir}")
    found = {}
    for path in paths:
        extract = read_extract(path, cfg["key_columns"], cfg.get("records_key", "data"),
                               cfg.get("max_file_bytes"))
        missing = [name for name in ("variables", "codes") if name not in extract.metadata]
        if missing:
            raise SeedError(f"{path.name}: no {' or '.join(missing)} section in the export")
        found[path.name] = (extract.metadata["variables"], extract.metadata["codes"])
    first_name, (first_variables, first_codes) = next(iter(found.items()))
    for name, (variables, codes) in found.items():
        if sorted(map(json.dumps, variables)) != sorted(map(json.dumps, first_variables)):
            raise SeedError(f"{name} and {first_name} describe the variables differently")
        if sorted(map(json.dumps, codes)) != sorted(map(json.dumps, first_codes)):
            raise SeedError(f"{name} and {first_name} define the codes differently")
    return first_variables, first_codes


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
        response_type = MISSING_TYPES.get(letter, f"missing_{letter}") if match else "answer"
        code_rows[(variable, code)] = [variable, code, label, response_type, letter]

    return [variable_rows[k] for k in sorted(variable_rows)], [code_rows[k] for k in sorted(code_rows)]


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
        variables, codes = build_tables(*collect(args.raw_dir, cfg))
    except (ExtractError, SeedError, KeyError, OSError) as error:
        sys.exit(f"Seeds not written: {type(error).__name__}: {error}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "ref_variables.csv", ["variable_name", "label", "question_text"], variables)
    write_csv(args.out_dir / "ref_codes.csv",
              ["variable_name", "code", "label", "response_type", "missing_code_letter"], codes)
    print(f"Wrote {len(variables)} variables and {len(codes)} codes to {args.out_dir}")


if __name__ == "__main__":
    main()
