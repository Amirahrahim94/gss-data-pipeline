"""Tests for the raw loader (source/pipeline/load_raw.py).

They show that a load is safe to repeat, that loading the cuts in either order gives
the same result, that the overlap is not duplicated, and that bad input fails
deliberately and leaves the database unchanged. Each test uses a fresh temporary
database. Most tests use the respondents with id_ <= 400 from each cut so they run
quickly; one test loads the full extracts.

Run from the project root:  python -m unittest discover -s source/tests -v
"""
import ast
from functools import lru_cache
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source" / "pipeline"))

import duckdb  # noqa: E402
import load_raw  # noqa: E402
from extract_reader import read_extract  # noqa: E402

RAW = ROOT / "source" / "data" / "raw"
CFG = json.loads((ROOT / "source" / "config" / "extract_config.json").read_text(encoding="utf-8"))
FILE_A, FILE_B = "gss_cut_a_2016_2018.json", "gss_cut_b_2018_2022.json"
SMALL = 400  # keep respondents with id_ <= SMALL; 2018 respondents stay in both cuts


@lru_cache(maxsize=2)
def read_records(name):
    return ast.literal_eval((RAW / name).read_text(encoding="utf-8"))["data"]


def subset(name):
    return [dict(r) for r in read_records(name) if int(r["id_"]) <= SMALL]


class LoaderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.db = self.tmp / "test.duckdb"
        self.a, self.b = subset(FILE_A), subset(FILE_B)

    # helpers ---------------------------------------------------------------
    def make_dir(self, files):
        """files: {file name: list of records (or raw text)} -> a new raw folder."""
        folder = Path(tempfile.mkdtemp(dir=self.tmp))
        for name, content in files.items():
            text = content if isinstance(content, str) else repr({"data": content})
            (folder / name).write_text(text, encoding="utf-8")
        return folder

    def load(self, files, cfg=None):
        return load_raw.run(self.make_dir(files), cfg or CFG, self.db)

    def query(self, sql):
        con = duckdb.connect(str(self.db))
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()

    def fingerprint(self):
        return self.query("select source_file, year, id_, record_sha256 from raw.gss_responses order by 1, 2, 3")

    def count(self, where="1 = 1"):
        return self.query(f"select count(*) from raw.gss_responses where {where}")[0][0]

    @staticmethod
    def statuses(results):
        return {r["file"]: r["status"] for r in results}

    # re-runs and order -----------------------------------------------------
    def test_first_load_loads_every_record(self):
        results = self.load({FILE_A: self.a, FILE_B: self.b})
        self.assertEqual(self.statuses(results), {FILE_A: "loaded", FILE_B: "loaded"})
        self.assertEqual(self.count(), len(self.a) + len(self.b))

    def test_running_twice_changes_nothing(self):
        files = {FILE_A: self.a, FILE_B: self.b}
        self.load(files)
        before = self.fingerprint()
        second = self.load(files)
        self.assertEqual(self.statuses(second), {FILE_A: "skipped", FILE_B: "skipped"})
        self.assertEqual(self.fingerprint(), before)

    def test_loading_in_either_order_gives_the_same_records(self):
        self.db = self.tmp / "ab.duckdb"
        self.load({FILE_A: self.a})
        self.load({FILE_B: self.b})
        a_then_b = self.fingerprint()
        self.db = self.tmp / "ba.duckdb"
        self.load({FILE_B: self.b})
        self.load({FILE_A: self.a})
        self.assertEqual(self.fingerprint(), a_then_b)

    def test_overlap_is_kept_once_per_file_and_agrees(self):
        self.load({FILE_A: self.a, FILE_B: self.b})
        keys_a = {(r["year"], str(r["id_"])) for r in self.a}
        keys_b = {(r["year"], str(r["id_"])) for r in self.b}
        distinct = self.query("select count(*) from (select year, id_ from raw.gss_responses group by 1, 2)")[0][0]
        shared = self.query("select count(*) from (select year, id_ from raw.gss_responses "
                            "group by 1, 2 having count(*) > 1)")[0][0]
        disagree = self.query("select count(*) from (select year, id_ from raw.gss_responses "
                              "group by 1, 2 having count(distinct record_sha256) > 1)")[0][0]
        self.assertEqual(distinct, len(keys_a | keys_b))
        self.assertEqual(shared, len(keys_a & keys_b))
        self.assertGreater(shared, 0)
        self.assertEqual(disagree, 0)

    def test_changed_file_replaces_its_rows(self):
        self.load({FILE_A: self.a})
        shorter = self.a[:-10]
        results = self.load({FILE_A: shorter})
        self.assertEqual(self.statuses(results), {FILE_A: "loaded"})
        self.assertEqual(self.count(f"source_file = '{FILE_A}'"), len(shorter))

    # bad input -------------------------------------------------------------
    def test_conflicting_overlap_fails_and_rolls_back(self):
        self.load({FILE_A: self.a})
        changed = [dict(r) for r in self.b]
        target = next(r for r in changed if r["year"] == "2018")
        target["educ"] = "CHANGED"
        results = self.load({FILE_B: changed})
        self.assertEqual(self.statuses(results), {FILE_B: "failed"})
        self.assertIn("different answers", results[0]["error"])
        self.assertEqual(self.count(), len(self.a))
        self.assertEqual(self.count(f"source_file = '{FILE_B}'"), 0)
        failed = self.query(f"select count(*) from raw.load_log where extract_id = '{FILE_B}' and status = 'failed'")
        self.assertEqual(failed[0][0], 1)
        self.assertEqual(self.statuses(self.load({FILE_B: self.b})), {FILE_B: "loaded"})

    def test_bad_file_fails_but_the_other_file_still_loads(self):
        with_duplicate = self.a + [dict(self.a[0])]
        results = self.load({FILE_A: with_duplicate, FILE_B: self.b})
        self.assertEqual(self.statuses(results), {FILE_A: "failed", FILE_B: "loaded"})
        self.assertIn("bad record", next(r for r in results if r["file"] == FILE_A)["error"])
        self.assertEqual(self.count(f"source_file = '{FILE_A}'"), 0)
        self.assertEqual(self.count(f"source_file = '{FILE_B}'"), len(self.b))

    def test_unusable_file_fails_but_the_other_file_still_loads(self):
        results = self.load({FILE_A: "this is not an extract", FILE_B: self.b})
        self.assertEqual(self.statuses(results), {FILE_A: "failed", FILE_B: "loaded"})

    def test_changed_column_set_is_rejected_until_the_database_is_rebuilt(self):
        self.load({FILE_A: self.a})
        extra = [{**r, "extra": "x"} for r in self.a]
        results = self.load({FILE_A: extra})
        self.assertEqual(self.statuses(results), {FILE_A: "failed"})
        self.assertIn("rebuild", results[0]["error"])
        self.assertEqual(self.count(), len(self.a))  # the usable table is untouched
        self.db = self.tmp / "rebuilt.duckdb"  # rebuilding means a fresh database from the sources
        self.assertEqual(self.statuses(self.load({FILE_A: extra})), {FILE_A: "loaded"})
        self.assertEqual(self.query("select count(*) from raw.gss_responses where extra = 'x'")[0][0], len(extra))

    def test_unusable_respondent_keys_reject_the_file(self):
        for number, bad in enumerate([None, "", " 7", ".i:  Inapplicable", 3.5, True]):
            with self.subTest(key=bad):
                self.db = self.tmp / f"key{number}.duckdb"
                records = [dict(r) for r in self.a]
                records[0]["id_"] = bad
                results = self.load({FILE_A: records})
                self.assertEqual(self.statuses(results), {FILE_A: "failed"})
                self.assertIn("invalid key", results[0]["error"])

    def test_a_record_with_different_columns_rejects_the_file(self):
        records = [dict(r) for r in self.a]
        del records[3]["educ"]
        results = self.load({FILE_A: records})
        self.assertEqual(self.statuses(results), {FILE_A: "failed"})
        self.assertIn("columns differ", results[0]["error"])

    def test_unreadable_file_is_a_failed_file_not_a_crash(self):
        folder = self.make_dir({FILE_B: self.b})
        (folder / "gss_cut_unreadable.json").mkdir()  # reading a folder raises an OSError
        by_file = self.statuses(load_raw.run(folder, CFG, self.db))
        self.assertEqual(by_file["gss_cut_unreadable.json"], "failed")
        self.assertEqual(by_file[FILE_B], "loaded")

    def test_reader_rejects_non_finite_numbers_and_nested_values(self):
        records = [dict(r) for r in self.a[:5]]
        records[1]["wtssnrps"] = float("nan")
        records[2]["age"] = {"nested": 1}
        path = self.tmp / "odd.json"
        path.write_text(json.dumps({"data": records}), encoding="utf-8")  # writes NaN
        extract = read_extract(path, CFG["key_columns"])
        self.assertEqual((len(extract.rows), len(extract.problems), extract.record_count), (3, 2, 5))

    def test_reader_keeps_the_exports_own_metadata(self):
        extract = read_extract(RAW / FILE_A, CFG["key_columns"])
        self.assertEqual(sorted(extract.metadata), ["codes", "variables"])
        self.assertEqual(extract.record_count, 5215)

    def test_failure_after_the_insert_rolls_back_everything(self):
        self.load({FILE_A: self.a})
        with mock.patch.object(load_raw, "check_shared_respondents", side_effect=RuntimeError("boom")):
            results = self.load({FILE_B: self.b})
        self.assertEqual(self.statuses(results), {FILE_B: "failed"})
        self.assertIn("boom", results[0]["error"])
        self.assertEqual(self.count(), len(self.a))
        logged = self.query(f"select status from raw.load_log where source_file = '{FILE_B}'")
        self.assertEqual(logged, [("failed",)])

    def test_provider_metadata_is_stored_and_replaced_with_the_file(self):
        self.load({FILE_A: (RAW / FILE_A).read_text(encoding="utf-8")})
        saved = self.query(f"select metadata_json from raw.extract_metadata where extract_id = '{FILE_A}'")
        self.assertEqual(sorted(json.loads(saved[0][0])), ["codes", "variables"])
        self.assertEqual(self.query("select count(*) from raw.extract_metadata")[0][0], 1)
        self.assertEqual(self.statuses(self.load({FILE_A: (RAW / FILE_A).read_text(encoding="utf-8")})),
                         {FILE_A: "skipped"})

    def test_missing_or_changed_metadata_forces_a_reload(self):
        text = (RAW / FILE_A).read_text(encoding="utf-8")
        self.load({FILE_A: text})
        con = duckdb.connect(str(self.db))
        con.execute("update raw.extract_metadata set metadata_json = '{}'")
        con.close()
        self.assertEqual(self.statuses(self.load({FILE_A: text})), {FILE_A: "loaded"})
        con = duckdb.connect(str(self.db))
        con.execute("delete from raw.extract_metadata")
        con.close()
        self.assertEqual(self.statuses(self.load({FILE_A: text})), {FILE_A: "loaded"})

    def test_metadata_rolls_back_with_a_failed_load(self):
        with mock.patch.object(load_raw, "check_shared_respondents", side_effect=RuntimeError("boom")):
            self.load({FILE_A: self.a})
        self.assertEqual(self.query("select count(*) from raw.extract_metadata")[0][0], 0)

    def test_control_table_name_is_refused_as_raw_table(self):
        for reserved in ("load_log", "extract_metadata"):
            with self.subTest(table=reserved):
                self.db = self.tmp / f"{reserved}.duckdb"
                with self.assertRaisesRegex(load_raw.LoadError, "reserved"):
                    self.load({FILE_A: self.a}, {**CFG, "raw_table": reserved})

    def test_records_key_and_file_size_limit_come_from_the_config(self):
        cfg = {**CFG, "records_key": "respondents"}
        text = repr({"respondents": self.a})
        self.assertEqual(self.statuses(self.load({FILE_A: text}, cfg)), {FILE_A: "loaded"})
        failed = self.load({FILE_B: repr({"data": self.b})}, cfg)  # wrong list name for this config
        self.assertEqual(self.statuses(failed), {FILE_B: "failed"})
        self.assertIn("respondents", failed[0]["error"])
        self.db = self.tmp / "limit.duckdb"
        limited = self.load({FILE_A: text}, {**cfg, "max_file_bytes": 100})
        self.assertEqual(self.statuses(limited), {FILE_A: "failed"})
        self.assertIn("max_file_bytes", limited[0]["error"])

    def test_overlap_count_is_logged_per_file_at_load_time(self):
        self.load({FILE_A: self.a, FILE_B: self.b})
        shared = {tuple(r[k] for k in ("year", "id_")) for r in self.a} & \
                 {tuple(r[k] for k in ("year", "id_")) for r in self.b}
        logged = dict(self.query("select extract_id, overlap_records from raw.load_log where status = 'loaded'"))
        self.assertEqual(logged, {FILE_A: 0, FILE_B: len(shared)})  # the second file loaded sees the overlap

    def test_a_repair_reload_is_logged_as_a_warning(self):
        self.load({FILE_A: self.a})
        con = duckdb.connect(str(self.db))
        con.execute(f"delete from raw.gss_responses where extract_id = '{FILE_A}' and id_ = '1'")
        con.close()
        with self.assertLogs("load_raw", level="WARNING") as captured:
            self.load({FILE_A: self.a})
        self.assertTrue(any("reloading" in line for line in captured.output))

    def test_bulk_load_preserves_text_nulls_and_special_characters(self):
        samples = [None, "", "None", "NULL", ".i:  Inapplicable", "00123",
                   'comma, quote" and backslash\\', "line1\nline2", "CR\rLF\r\nend",
                   "tab\tvalue", "Melayu العربية 中文", "  spaces  "]
        records = [{"year": "2022", "id_": str(i), "answer": value}
                   for i, value in enumerate(samples)]
        self.assertEqual(self.statuses(self.load({FILE_A: records})), {FILE_A: "loaded"})
        stored = self.query("select answer from raw.gss_responses order by cast(id_ as integer)")
        self.assertEqual([row[0] for row in stored], samples)
        self.assertEqual(self.statuses(self.load({FILE_A: records})), {FILE_A: "skipped"})

    def test_bulk_temporary_files_are_cleaned_after_success(self):
        original = tempfile.TemporaryDirectory
        scratch = self.tmp / "bulk_files"
        scratch.mkdir()
        with mock.patch.object(load_raw.tempfile, "TemporaryDirectory",
                side_effect=lambda **kw: original(dir=scratch, **kw)):
            self.assertEqual(self.statuses(self.load({FILE_A: self.a})), {FILE_A: "loaded"})
        self.assertEqual(list(scratch.iterdir()), [])

    def test_bulk_temporary_files_are_cleaned_after_insert_failure(self):
        original = tempfile.TemporaryDirectory
        scratch = self.tmp / "bulk_files"
        scratch.mkdir()
        fake = mock.Mock()
        fake.execute.side_effect = RuntimeError("bulk insert failed")
        with mock.patch.object(load_raw.tempfile, "TemporaryDirectory",
                side_effect=lambda **kw: original(dir=scratch, **kw)):
            with self.assertRaisesRegex(RuntimeError, "bulk insert failed"):
                load_raw.insert_rows(fake, "gss_responses", ["answer"], [["text"]])
        self.assertEqual(list(scratch.iterdir()), [])

    # completeness ----------------------------------------------------------
    def test_a_partly_stored_file_is_not_skipped_and_is_repaired(self):
        self.load({FILE_A: self.a})
        con = duckdb.connect(str(self.db))
        con.execute(f"delete from raw.gss_responses where source_file = '{FILE_A}' and id_ = '1'")
        con.close()
        self.assertLess(self.count(), len(self.a))
        self.assertEqual(self.statuses(self.load({FILE_A: self.a})), {FILE_A: "loaded"})
        self.assertEqual(self.count(), len(self.a))

    def test_rows_without_a_load_record_are_not_trusted(self):
        self.load({FILE_A: self.a})
        con = duckdb.connect(str(self.db))
        con.execute("delete from raw.load_log")
        con.close()
        self.assertEqual(self.statuses(self.load({FILE_A: self.a})), {FILE_A: "loaded"})
        self.assertEqual(self.count(), len(self.a))

    def test_an_edited_stored_answer_is_detected_and_repaired(self):
        self.load({FILE_A: self.a})
        con = duckdb.connect(str(self.db))
        con.execute(f"update raw.gss_responses set age = 'tampered' where extract_id = '{FILE_A}' and id_ = '1'")
        con.close()
        self.assertEqual(self.statuses(self.load({FILE_A: self.a})), {FILE_A: "loaded"})
        self.assertEqual(self.count("age = 'tampered'"), 0)

    def test_stable_extract_id_survives_a_rename(self):
        cfg = {**CFG, "extract_ids": {FILE_A: "cut_a", "gss_cut_a_renamed.json": "cut_a"}}
        self.load({FILE_A: self.a}, cfg)
        results = self.load({"gss_cut_a_renamed.json": self.a}, cfg)
        self.assertEqual(self.statuses(results), {"gss_cut_a_renamed.json": "skipped"})
        self.assertEqual(self.count(), len(self.a))

    def test_two_files_sharing_an_extract_id_are_refused(self):
        cfg = {**CFG, "extract_ids": {FILE_A: "same", FILE_B: "same"}}
        with self.assertRaises(load_raw.LoadError):
            self.load({FILE_A: self.a, FILE_B: self.b}, cfg)

    def test_repeated_field_names_reject_the_file(self):
        for text in ['{"data": [{"year": "2016", "id_": "1", "age": "1", "age": "2"}]}',
                     "{'data': [{'year': '2016', 'id_': '1', 'age': '1', 'age': '2'}]}"]:
            with self.subTest(text=text[:20]):
                self.db = self.tmp / f"dup{abs(hash(text))}.duckdb"
                results = self.load({FILE_A: text})
                self.assertEqual(self.statuses(results), {FILE_A: "failed"})
                self.assertIn("repeated field name", results[0]["error"])

    def test_column_clashing_with_a_metadata_column_is_rejected(self):
        for clash in ("run_id", "Extract_ID"):
            with self.subTest(column=clash):
                self.db = self.tmp / f"clash{clash}.duckdb"
                records = [{**r, clash: "x"} for r in self.a[:5]]
                results = self.load({FILE_A: records})
                self.assertEqual(self.statuses(results), {FILE_A: "failed"})
                self.assertIn("clash", results[0]["error"])

    def test_columns_that_differ_only_by_case_are_rejected(self):
        records = [{**r, "AGE": "x"} for r in self.a[:5]]
        results = self.load({FILE_A: records})
        self.assertEqual(self.statuses(results), {FILE_A: "failed"})
        self.assertIn("case", results[0]["error"])

    def test_database_rejects_a_duplicate_respondent_year(self):
        self.load({FILE_A: self.a})
        con = duckdb.connect(str(self.db))
        try:
            with self.assertRaises(Exception):  # duckdb.ConstraintException on real DuckDB
                con.execute(f"insert into raw.gss_responses (extract_id, year, id_) "
                            f"select extract_id, year, id_ from raw.gss_responses limit 1")
        finally:
            con.close()

    # evidence --------------------------------------------------------------
    def test_load_log_has_one_row_per_file_per_run(self):
        files = {FILE_A: self.a, FILE_B: self.b}
        self.load(files)
        self.load(files)
        rows = self.query("select source_file, status, records_loaded from raw.load_log order by started_at, source_file")
        statuses = sorted((f, s) for f, s, _ in rows)
        self.assertEqual(statuses, [(FILE_A, "loaded"), (FILE_A, "skipped"), (FILE_B, "loaded"), (FILE_B, "skipped")])

    # isolation -------------------------------------------------------------
    @unittest.skipIf(getattr(duckdb, "IS_STUB", False), "needs real DuckDB file locking")
    def test_second_process_is_refused_with_a_clear_message(self):
        holder = subprocess.Popen(
            [sys.executable, "-c",
             f"import duckdb, time; c = duckdb.connect({str(self.db)!r}); print('ready', flush=True); time.sleep(20)"],
            stdout=subprocess.PIPE, text=True)
        def cleanup_holder():
            if holder.poll() is None:
                holder.kill()
            holder.wait()
            holder.stdout.close()
        self.addCleanup(cleanup_holder)
        self.assertEqual(holder.stdout.readline().strip(), "ready")
        with self.assertRaises(load_raw.LoadError) as caught:
            load_raw.connect(self.db)
        self.assertIn("another run", str(caught.exception))

    # the real extracts -----------------------------------------------------
    def test_real_extracts_totals_and_overlap(self):
        results = load_raw.run(RAW, CFG, self.db)
        self.assertEqual(self.statuses(results), {FILE_A: "loaded", FILE_B: "loaded"})
        self.assertEqual(self.count(), 5215 + 5892)
        distinct = self.query("select count(*) from (select year, id_ from raw.gss_responses group by 1, 2)")[0][0]
        shared = self.query("select count(*) from (select year, id_ from raw.gss_responses "
                            "group by 1, 2 having count(*) > 1)")[0][0]
        self.assertEqual(distinct, 8759)
        self.assertEqual(shared, 2348)


if __name__ == "__main__":
    unittest.main()
