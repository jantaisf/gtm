#!/usr/bin/env python3
"""
Phase 2 Part 2: cARR Pipeline Runner

Executes the 4 SQL transformation steps in order against BigQuery,
producing the full derived table chain from raw tables to carr_rep_rollup.

Usage:
    python3 run_pipeline.py
    python3 run_pipeline.py --as-of-date 2025-06-30
    python3 run_pipeline.py --step 3
    python3 run_pipeline.py --dry-run

Options:
    --as-of-date YYYY-MM-DD   Evaluation date for active contract resolution.
                               Default: today. Use a 2024/2025 date when running
                               against the synthetic dataset.
    --step N                   Run only step N (1-4).
    --dry-run                  Print SQL without executing.
"""

import argparse
import sys
import time
from datetime import date
from pathlib import Path

from google.cloud import bigquery

GCP_PROJECT = "openclaw-gateway-491103"
BQ_DATASET  = "gtm"
SQL_DIR     = Path(__file__).parent / "sql"

PIPELINE_STEPS = [
    ("01_stg_active_contracts.sql",     "stg_active_contracts",   "Resolve active contracts (handles mid-year expansions)"),
    ("02_stg_monthly_consumption.sql",  "stg_monthly_consumption","Aggregate monthly usage (excludes orphaned + rogue logs)"),
    ("03_carr_account.sql",             "carr_account",            "Compute account-level cARR + health tiers"),
    ("04_carr_rep_rollup.sql",          "carr_rep_rollup",         "Roll up cARR to rep + region level"),
]


def execute_step(
    client: bigquery.Client,
    sql_file: str,
    as_of_date: str,
    dry_run: bool,
) -> float:
    path = SQL_DIR / sql_file
    if not path.exists():
        print(f"  ✗ File not found: {path}")
        sys.exit(1)

    sql = path.read_text().replace("{as_of_date}", f"DATE '{as_of_date}'")

    if dry_run:
        print(f"  [dry-run] {sql_file}")
        print("  " + "─" * 60)
        print(sql[:600] + (" ..." if len(sql) > 600 else ""))
        return 0.0

    t0  = time.time()
    job = client.query(sql)
    job.result()
    elapsed = time.time() - t0

    if job.errors:
        print(f"  ✗ Errors: {job.errors}")
        sys.exit(1)

    return elapsed


def main():
    parser = argparse.ArgumentParser(description="Run cARR pipeline")
    parser.add_argument(
        "--as-of-date", metavar="YYYY-MM-DD", default=str(date.today()),
        help="Evaluation date (default: today)",
    )
    parser.add_argument(
        "--step", type=int, choices=[1, 2, 3, 4],
        help="Run only this step",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print SQL without executing",
    )
    args = parser.parse_args()

    client = None if args.dry_run else bigquery.Client(project=GCP_PROJECT)

    print(f"\n── cARR Pipeline ───────────────────────────────────────────────")
    print(f"   Project    : {GCP_PROJECT}.{BQ_DATASET}")
    print(f"   As-of date : {args.as_of_date}")
    print(f"   Mode       : {'DRY RUN' if args.dry_run else 'LIVE'}\n")

    steps = [PIPELINE_STEPS[args.step - 1]] if args.step else PIPELINE_STEPS
    total = 0.0

    for i, (sql_file, table, description) in enumerate(steps, start=args.step or 1):
        print(f"Step {i}: {description}")
        print(f"  → {GCP_PROJECT}.{BQ_DATASET}.{table}")
        elapsed = execute_step(client, sql_file, args.as_of_date, args.dry_run)
        total  += elapsed
        if not args.dry_run:
            print(f"  ✓ {elapsed:.1f}s\n")

    if not args.dry_run:
        print(f"── Done ─────────────────────────────────────────────────────────")
        print(f"   Total time : {total:.1f}s")
        print(f"\n   Output tables:")
        for _, table, _ in (steps if args.step else PIPELINE_STEPS):
            print(f"   · {GCP_PROJECT}.{BQ_DATASET}.{table}")


if __name__ == "__main__":
    main()
