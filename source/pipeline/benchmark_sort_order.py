"""Show what sorting fct_response by variable_name does for the most expensive query (Q1).

The extracts give only 157,662 response rows (two DuckDB row groups), too few for the sort to
change timings. This script copies marts.fct_response N times into a temporary database
(default 100, about 15.8 million rows) in two layouts, runs the query against each and prints:

  - how many row groups each scan of fct_response read (from EXPLAIN ANALYZE),
  - the median run time with all threads and with one thread,
  - whether both layouts return identical results.

"appended" stacks the copies batch after batch, which is what loading extract after extract
incrementally would give: every row group holds every variable. "sorted" is the same rows
ordered by variable_name, survey_year, as the fct_response model now writes them.

This tests the layout, not full-GSS performance: the copy repeats the same rows and the same
18 variables, so it compresses and processes more easily than 75,700 real respondents with
7,000 diverse variables would. Row-group counts carry over to real data; timings do not.

It also prints the plan summary for the query against the real warehouse table. The warehouse
is opened read-only and never changed. Run the pipeline first: the query is read from dbt's
compiled analyses. --query picks another analysis by file name (without .sql).

Usage:  python source/pipeline/benchmark_sort_order.py [--query NAME] [--copies N] [--repeats R] [--db PATH]
"""
import argparse
import os
import re
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
# DBT_TARGET_PATH is where dbt writes in Docker (see the Dockerfile); locally it is unset.
ANALYSES = (Path(os.environ.get("DBT_TARGET_PATH", ROOT / "dbt/target"))
            / "compiled/gss_pipeline/analyses")
# dbt writes tables as "<database>"."marts"."<table>"; swap in the benchmark copies.
FCT_REFERENCE = re.compile(r'"[^"\s]*"\."marts"\."fct_response"')
DIM_REFERENCE = re.compile(r'"[^"\s]*"\."marts"\."dim_respondent"')


def row_groups_scanned(con, sql):
    """The 'Row Groups Scanned: a / b' lines from EXPLAIN ANALYZE, one per table scan."""
    plan = con.sql("explain analyze " + sql).fetchall()[0][1]
    return re.findall(r"Row Groups Scanned: (\d+ / \d+)", plan), \
        re.search(r"Total Time: ([0-9.]+s)", plan).group(1)


def median_ms(con, sql, repeats):
    times = []
    for _ in range(repeats):
        started = time.perf_counter()
        con.sql(sql).fetchall()
        times.append(time.perf_counter() - started)
    return round(statistics.median(times) * 1000)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--query", default="q1_prayer_by_religion_raised")
    p.add_argument("--copies", type=int, default=100)
    p.add_argument("--repeats", type=int, default=9)
    p.add_argument("--db", default=os.environ.get(
        "GSS_DB_PATH", str(ROOT / "source/data/warehouse/gss.duckdb")))
    args = p.parse_args()

    compiled = ANALYSES / f"{args.query}.sql"
    if not compiled.exists():
        sys.exit(f"{compiled} not found: run python source/pipeline/run_pipeline.py first")
    query = compiled.read_text(encoding="utf-8")
    if not FCT_REFERENCE.search(query):
        sys.exit(f"{args.query} does not read fct_response")

    warehouse = duckdb.connect(args.db, read_only=True)
    scans, total = row_groups_scanned(warehouse, query)
    rows = warehouse.sql("select count(*) from marts.fct_response").fetchall()[0][0]
    print(args.query)
    print(f"Warehouse ({rows:,} rows): total {total}; row groups read per scan: {scans}")
    warehouse.close()

    folder = tempfile.mkdtemp()
    try:
        con = duckdb.connect(str(Path(folder) / "benchmark.duckdb"))
        # DuckDB runs a statement again when its result is fetched, so DDL is only executed.
        con.execute(f"attach '{args.db}' as warehouse (read_only)")
        con.execute(f"""
            create table fct_appended as
            select f.* replace (f.respondent_year_id || '-' || copy.i as respondent_year_id)
            from range({args.copies}) as copy(i), warehouse.marts.fct_response as f
            order by copy.i""")
        # The query may join dim_respondent (for weights); copy it with the same new keys.
        con.execute(f"""
            create table dim_copies as
            select d.* replace (d.respondent_year_id || '-' || copy.i as respondent_year_id)
            from range({args.copies}) as copy(i), warehouse.marts.dim_respondent as d""")
        con.execute("""
            create table fct_sorted as
            select * from fct_appended order by variable_name, survey_year""")
        con.execute("checkpoint")
        rows = con.sql("select count(*) from fct_sorted").fetchall()[0][0]
        print(f"\nScaled copy: {args.copies} copies, {rows:,} rows")

        results = {}
        for table in ("fct_appended", "fct_sorted"):
            sql = DIM_REFERENCE.sub("dim_copies", FCT_REFERENCE.sub(table, query))
            scans, _ = row_groups_scanned(con, sql)
            all_threads = median_ms(con, sql, args.repeats)
            con.execute("set threads = 1")
            one_thread = median_ms(con, sql, args.repeats)
            con.execute("reset threads")
            # Compare as unordered rows: ties in a query's ORDER BY may come back in any order.
            results[table] = sorted(map(repr, con.sql(sql).fetchall()))
            print(f"  {table:<13} row groups read per scan: {', '.join(scans)}")
            print(f"  {'':<13} median {all_threads} ms (all threads), {one_thread} ms (1 thread)")
        same = results["fct_appended"] == results["fct_sorted"]
        print(f"\nIdentical results: {'yes' if same else 'NO'}")
        con.close()
        return 0 if same else 1
    finally:
        shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
