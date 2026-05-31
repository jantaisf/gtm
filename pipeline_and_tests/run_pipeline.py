#!/usr/bin/env python3
"""
Phase 2 Part 2: cACV Pipeline Runner

Executes 5 SQL transformation steps in order against BigQuery,
producing the full derived table chain from raw tables to cacv_rep_rollup.

Dataset layout:
    raw      — source tables (sales_reps, accounts, contracts, daily_usage_logs)
    staging  — stg_active_contracts, stg_monthly_consumption
    gtm      — dim_dates, cacv_account, cacv_rep_rollup

Steps:
    0  dim_dates               Calendar + PANW fiscal dimension (2000–2030)
    1  stg_active_contracts    Resolve active contracts per account
    2  stg_monthly_consumption Aggregate monthly usage; exclude orphaned/rogue logs
    3  cacv_account            Account-level cACV + health tiers
    4  cacv_rep_rollup         Rep + region cACV rollup

Usage:
    python3 run_pipeline.py
    python3 run_pipeline.py --as-of-date 2026-05-28
    python3 run_pipeline.py --step 3
    python3 run_pipeline.py --dry-run

Options:
    --as-of-date YYYY-MM-DD   Evaluation date for active contract resolution.
                               Default: today.
    --step N                   Run only step N (0–4).
    --dry-run                  Print SQL without executing.
"""

import argparse
import sys
import time
from datetime import date
from pathlib import Path

from google.cloud import bigquery

GCP_PROJECT = "openclaw-gateway-491103"
SQL_DIR     = Path(__file__).parent / "sql"

# (sql_file, destination_dataset, destination_table, description)
PIPELINE_STEPS = [
    ("00_dim_dates.sql",               "gtm",     "dim_dates",               "Build calendar dimension (2000-01-01 → today, incl. PANW fiscal calendar)"),
    ("01_stg_active_contracts.sql",    "staging", "stg_active_contracts",    "Resolve active contracts (handles mid-year expansions)"),
    ("02_stg_monthly_consumption.sql", "staging", "stg_monthly_consumption", "Aggregate monthly usage (excludes orphaned + rogue logs)"),
    ("03_cacv_account.sql",            "gtm",     "cacv_account",            "Compute account-level cACV + health tiers"),
    ("04_cacv_rep_rollup.sql",         "gtm",     "cacv_rep_rollup",         "Roll up cACV to rep + region level"),
]


def ensure_datasets(client: bigquery.Client):
    """Create raw, staging, and gtm datasets if they don't exist."""
    for ds_name in ("raw", "staging", "gtm"):
        ds_ref = bigquery.Dataset(f"{GCP_PROJECT}.{ds_name}")
        ds_ref.location = "US"
        try:
            client.create_dataset(ds_ref, exists_ok=True)
        except Exception as e:
            print(f"  ⚠ Could not ensure dataset {ds_name}: {e}")


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
    parser = argparse.ArgumentParser(description="Run cACV pipeline")
    parser.add_argument(
        "--as-of-date", metavar="YYYY-MM-DD", default=str(date.today()),
        help="Evaluation date (default: today)",
    )
    parser.add_argument(
        "--step", type=int, choices=[0, 1, 2, 3, 4],
        help="Run only this step (0 = dim_dates)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print SQL without executing",
    )
    args = parser.parse_args()

    client = None if args.dry_run else bigquery.Client(project=GCP_PROJECT)

    print(f"\n── cACV Pipeline ───────────────────────────────────────────────")
    print(f"   Project    : {GCP_PROJECT}")
    print(f"   Datasets   : raw → staging → gtm")
    print(f"   As-of date : {args.as_of_date}")
    print(f"   Mode       : {'DRY RUN' if args.dry_run else 'LIVE'}\n")

    if not args.dry_run:
        ensure_datasets(client)

    steps = [PIPELINE_STEPS[args.step]] if args.step is not None else PIPELINE_STEPS
    total = 0.0

    for i, (sql_file, dataset, table, description) in enumerate(steps, start=args.step or 1):
        print(f"Step {i}: {description}")
        print(f"  → {GCP_PROJECT}.{dataset}.{table}")
        elapsed = execute_step(client, sql_file, args.as_of_date, args.dry_run)
        total  += elapsed
        if not args.dry_run:
            print(f"  ✓ {elapsed:.1f}s\n")

    if not args.dry_run:
        print(f"── Done ─────────────────────────────────────────────────────────")
        print(f"   Total time : {total:.1f}s")
        print(f"\n   Output tables:")
        for _, dataset, table, _ in (steps if args.step else PIPELINE_STEPS):
            print(f"   · {GCP_PROJECT}.{dataset}.{table}")


if __name__ == "__main__":
    main()
