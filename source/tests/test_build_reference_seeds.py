"""Tests for the reference-seed builder (source/pipeline/build_reference_seeds.py).

They cover build_validity, which decides where a question was asked: only a real answer
counts as evidence, so a ballot answered entirely with special missing codes is "not asked".

Run from the project root:  python -m unittest discover -s source/tests -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source" / "pipeline"))

from build_reference_seeds import build_validity  # noqa: E402

CFG = {"key_columns": ["year", "id_"], "year_column": "year", "ballot_column": "ballot"}


def record(year, id_, ballot, tvhours):
    return {"year": year, "id_": id_, "ballot": ballot, "tvhours": tvhours}


class BuildValidityTest(unittest.TestCase):
    def test_ballot_with_only_missing_codes_is_not_asked(self):
        records = {
            ("2018", "1"): record(2018, 1, "Ballot a", 3),
            ("2018", "2"): record(2018, 2, "Ballot c", ".i:  Inapplicable"),
            ("2018", "3"): record(2018, 3, "Ballot c", ".n:  No answer"),
        }
        self.assertEqual(build_validity(records, CFG), [
            ["tvhours", 2018, "Ballot a", "true"],
            ["tvhours", 2018, "Ballot c", "false"],
        ])

    def test_one_real_answer_makes_the_ballot_asked(self):
        records = {
            ("2018", "1"): record(2018, 1, "Ballot b", ".i:  Inapplicable"),
            ("2018", "2"): record(2018, 2, "Ballot b", 0),
        }
        self.assertEqual(build_validity(records, CFG), [["tvhours", 2018, "Ballot b", "true"]])

    def test_blank_and_null_are_not_answers(self):
        records = {
            ("2022", "1"): record(2022, 1, "Ballot a", None),
            ("2022", "2"): record(2022, 2, "Ballot a", "  "),
        }
        self.assertEqual(build_validity(records, CFG), [["tvhours", 2022, "Ballot a", "false"]])

    def test_key_and_ballot_columns_are_not_variables(self):
        rows = build_validity({("2018", "1"): record(2018, 1, "Ballot a", 2)}, CFG)
        self.assertEqual({row[0] for row in rows}, {"tvhours"})


if __name__ == "__main__":
    unittest.main()
