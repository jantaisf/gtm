#!/usr/bin/env python3
"""
Phase 2 Part 3: Automated Data Quality Tests

Runs assertions against BigQuery raw tables to catch data anomalies
before they corrupt the cARR metric calculation.

Tests:
    [ERROR]   test_null_primary_keys          — NULL PKs in any table
    [ERROR]   test_negative_credits           — negative compute_credits_consumed
    [ERROR]   test_malformed_contracts        — end_date < start_date
    [ERROR]   test_duplicate_log_ids          — duplicate log_id values
    [ERROR]   test_contracts_missing_accounts — contracts referencing unknown accounts
    [ERROR]   test_accounts_missing_reps      — accounts referencing unknown reps
    [WARNING] test_orphaned_usage             — logs with unknown account_ids
    [WARNING] test_out_of_contract_usage      — logs outside all contract windows
    [WARNING] test_shelfware_rate             — alert if >15% of accounts have zero usage
    [INFO]    test_overlapping_contracts      — accounts with multiple active contracts
    [INFO]    test_new_account_rate           — % of accounts in Ramping status

Usage:
    python3 dq_tests.py
    python3 dq_tests.py --as-of-date 2025-06-30
    python3 dq_tests.py --as-of-date 2025-06-30 --fail-on-error
    python3 dq_tests.py --as-of-date 2025-06-30 --output results.json

Exit codes:
    0  All tests passed (or only warnings/info)
    1  One or more ERROR tests failed (only with --fail-on-error)
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from google.cloud import bigquery

GCP_PROJECT = "openclaw-gateway-491103"
DS_RAW      = f"`{GCP_PROJECT}.raw`"
DS_STAGING  = f"`{GCP_PROJECT}.staging`"
DS_GTM      = f"`{GCP_PROJECT}.gtm`"
DS          = DS_RAW   # DQ tests run against raw tables


# ─────────────────────────────────────────────────────────────────────────────
# Result container
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DQResult:
    test_name: str
    severity:  Literal["ERROR", "WARNING", "INFO"]
    passed:    bool
    row_count: int = 0
    detail:    str = ""
    sample_rows: list = field(default_factory=list)


def run_query(client: bigquery.Client, sql: str, as_of_date: str = "") -> list[dict]:
    if as_of_date:
        sql = sql.replace("{as_of_date}", f"DATE '{as_of_date}'")
    return [dict(r) for r in client.query(sql).result()]


# ─────────────────────────────────────────────────────────────────────────────
# ERROR tests — these indicate data integrity problems
# ─────────────────────────────────────────────────────────────────────────────

def test_null_primary_keys(client, **_) -> DQResult:
    """NULL primary keys in any raw table."""
    sql = f"""
    SELECT 'sales_reps'        AS tbl, COUNT(*) AS nulls FROM {DS}.sales_reps        WHERE rep_id      IS NULL
    UNION ALL
    SELECT 'accounts',                  COUNT(*)          FROM {DS}.accounts           WHERE account_id  IS NULL
    UNION ALL
    SELECT 'contracts',                 COUNT(*)          FROM {DS}.contracts          WHERE contract_id IS NULL
    UNION ALL
    SELECT 'daily_usage_logs',          COUNT(*)          FROM {DS}.daily_usage_logs   WHERE log_id      IS NULL
    """
    rows   = run_query(client, sql)
    total  = sum(r["nulls"] for r in rows)
    bad    = [r["tbl"] for r in rows if r["nulls"] > 0]
    return DQResult(
        test_name="test_null_primary_keys",
        severity="ERROR",
        passed=(total == 0),
        row_count=total,
        detail=f"{total} NULL primary keys in: {bad or 'none'}",
        sample_rows=rows,
    )


def test_negative_credits(client, **_) -> DQResult:
    """Usage logs with negative compute_credits_consumed."""
    sql = f"""
    SELECT COUNT(*) AS cnt
    FROM {DS}.daily_usage_logs
    WHERE compute_credits_consumed < 0
    """
    rows  = run_query(client, sql)
    count = rows[0]["cnt"] if rows else 0
    return DQResult(
        test_name="test_negative_credits",
        severity="ERROR",
        passed=(count == 0),
        row_count=count,
        detail=f"{count} rows with negative compute_credits_consumed",
    )


def test_malformed_contracts(client, **_) -> DQResult:
    """Contracts where end_date < start_date."""
    sql = f"""
    SELECT contract_id, account_id, start_date, end_date
    FROM {DS}.contracts
    WHERE end_date < start_date
    LIMIT 20
    """
    rows = run_query(client, sql)
    return DQResult(
        test_name="test_malformed_contracts",
        severity="ERROR",
        passed=(len(rows) == 0),
        row_count=len(rows),
        detail=f"{len(rows)} contracts with end_date before start_date",
        sample_rows=rows[:5],
    )


def test_duplicate_log_ids(client, **_) -> DQResult:
    """Duplicate log_id values in daily_usage_logs."""
    sql = f"""
    SELECT log_id, COUNT(*) AS cnt
    FROM {DS}.daily_usage_logs
    GROUP BY 1
    HAVING COUNT(*) > 1
    LIMIT 10
    """
    rows = run_query(client, sql)
    return DQResult(
        test_name="test_duplicate_log_ids",
        severity="ERROR",
        passed=(len(rows) == 0),
        row_count=len(rows),
        detail=f"{len(rows)} duplicate log_ids found",
        sample_rows=rows[:5],
    )


def test_contracts_missing_accounts(client, **_) -> DQResult:
    """Contracts referencing account_ids not in the accounts table."""
    sql = f"""
    SELECT c.contract_id, c.account_id
    FROM {DS}.contracts c
    LEFT JOIN {DS}.accounts a ON a.account_id = c.account_id
    WHERE a.account_id IS NULL
    LIMIT 20
    """
    rows = run_query(client, sql)
    return DQResult(
        test_name="test_contracts_missing_accounts",
        severity="ERROR",
        passed=(len(rows) == 0),
        row_count=len(rows),
        detail=f"{len(rows)} contracts reference non-existent account_ids",
        sample_rows=rows[:5],
    )


def test_accounts_missing_reps(client, **_) -> DQResult:
    """Accounts referencing rep_ids not in the sales_reps table."""
    sql = f"""
    SELECT a.account_id, a.rep_id
    FROM {DS}.accounts a
    LEFT JOIN {DS}.sales_reps sr ON sr.rep_id = a.rep_id
    WHERE sr.rep_id IS NULL
    LIMIT 20
    """
    rows = run_query(client, sql)
    return DQResult(
        test_name="test_accounts_missing_reps",
        severity="ERROR",
        passed=(len(rows) == 0),
        row_count=len(rows),
        detail=f"{len(rows)} accounts reference non-existent rep_ids",
        sample_rows=rows[:5],
    )


# ─────────────────────────────────────────────────────────────────────────────
# WARNING tests — expected anomalies that must be monitored
# ─────────────────────────────────────────────────────────────────────────────

def test_orphaned_usage(client, **_) -> DQResult:
    """Logs where account_id does not exist in the accounts table (ghost accounts)."""
    sql = f"""
    SELECT l.account_id, COUNT(*) AS orphan_count
    FROM {DS}.daily_usage_logs l
    LEFT JOIN {DS}.accounts a ON a.account_id = l.account_id
    WHERE a.account_id IS NULL
    GROUP BY 1
    ORDER BY 2 DESC
    LIMIT 10
    """
    rows  = run_query(client, sql)
    total = sum(r["orphan_count"] for r in rows)
    return DQResult(
        test_name="test_orphaned_usage",
        severity="WARNING",
        passed=(total == 0),
        row_count=total,
        detail=f"{total} orphaned log rows across {len(rows)} unknown account_ids — excluded from cARR",
        sample_rows=rows[:5],
    )


def test_out_of_contract_usage(client, **_) -> DQResult:
    """Logs for valid accounts where the date falls outside all contract windows."""
    sql = f"""
    SELECT COUNT(*) AS cnt
    FROM {DS}.daily_usage_logs l
    INNER JOIN {DS}.accounts a ON a.account_id = l.account_id
    WHERE NOT EXISTS (
      SELECT 1 FROM {DS}.contracts c
      WHERE c.account_id = l.account_id
        AND l.date BETWEEN c.start_date AND c.end_date
        AND c.end_date >= c.start_date
    )
    """
    rows  = run_query(client, sql)
    count = rows[0]["cnt"] if rows else 0
    return DQResult(
        test_name="test_out_of_contract_usage",
        severity="WARNING",
        passed=(count == 0),
        row_count=count,
        detail=f"{count} log rows with usage outside all contract windows — excluded from cARR",
    )


def test_shelfware_rate(client, as_of_date: str, **_) -> DQResult:
    """
    % of active accounts with zero usage in the trailing 90 days.
    Alert threshold: > 15%.
    """
    sql = f"""
    WITH usage_90d AS (
      SELECT DISTINCT account_id
      FROM {DS}.daily_usage_logs
      WHERE date BETWEEN DATE_SUB({{as_of_date}}, INTERVAL 90 DAY) AND {{as_of_date}}
        AND compute_credits_consumed > 0
    ),
    active_accounts AS (
      SELECT DISTINCT account_id
      FROM {DS}.contracts
      WHERE start_date <= {{as_of_date}}
        AND end_date   >= {{as_of_date}}
        AND end_date   >= start_date
    )
    SELECT
      COUNT(*)                                             AS active_accounts,
      COUNTIF(u.account_id IS NULL)                       AS zero_usage_accounts,
      ROUND(COUNTIF(u.account_id IS NULL) / COUNT(*), 4)  AS shelfware_rate
    FROM active_accounts aa
    LEFT JOIN usage_90d u USING (account_id)
    """
    rows = run_query(client, sql, as_of_date)
    if not rows:
        return DQResult(test_name="test_shelfware_rate", severity="INFO",
                        passed=True, detail="No active accounts found")
    r         = rows[0]
    rate      = float(r.get("shelfware_rate") or 0)
    threshold = 0.15
    return DQResult(
        test_name="test_shelfware_rate",
        severity="WARNING",
        passed=(rate <= threshold),
        row_count=int(r.get("zero_usage_accounts") or 0),
        detail=(
            f"Shelfware rate: {rate:.1%} "
            f"({r.get('zero_usage_accounts')} of {r.get('active_accounts')} active accounts). "
            f"Alert threshold: {threshold:.0%}"
        ),
        sample_rows=rows,
    )


# ─────────────────────────────────────────────────────────────────────────────
# INFO tests — expected patterns worth surfacing
# ─────────────────────────────────────────────────────────────────────────────

def test_overlapping_contracts(client, as_of_date: str, **_) -> DQResult:
    """
    Accounts with more than one simultaneously active contract.
    Expected for mid-year expansion accounts — informational only.
    """
    sql = f"""
    SELECT account_id, COUNT(*) AS active_contracts
    FROM {DS}.contracts
    WHERE start_date <= {{as_of_date}}
      AND end_date   >= {{as_of_date}}
      AND end_date   >= start_date
    GROUP BY 1
    HAVING COUNT(*) > 1
    ORDER BY 2 DESC
    LIMIT 20
    """
    rows = run_query(client, sql, as_of_date)
    return DQResult(
        test_name="test_overlapping_contracts",
        severity="INFO",
        passed=True,
        row_count=len(rows),
        detail=f"{len(rows)} accounts have >1 active contract (mid-year expansions — expected)",
        sample_rows=rows[:5],
    )


def test_new_account_rate(client, as_of_date: str, **_) -> DQResult:
    """
    % of active accounts in Ramping status (contract < 90 days old).
    Informational — high rate is normal after a strong bookings quarter.
    """
    sql = f"""
    WITH active AS (
      SELECT DISTINCT account_id, MIN(start_date) AS earliest_start
      FROM {DS}.contracts
      WHERE start_date <= {{as_of_date}}
        AND end_date   >= {{as_of_date}}
        AND end_date   >= start_date
      GROUP BY 1
    )
    SELECT
      COUNT(*)                                                          AS active_accounts,
      COUNTIF(earliest_start >= DATE_SUB({{as_of_date}}, INTERVAL 90 DAY)) AS ramping_accounts,
      ROUND(
        COUNTIF(earliest_start >= DATE_SUB({{as_of_date}}, INTERVAL 90 DAY)) / COUNT(*), 4
      )                                                                 AS ramping_rate
    FROM active
    """
    rows = run_query(client, sql, as_of_date)
    r    = rows[0] if rows else {}
    rate = float(r.get("ramping_rate") or 0)
    return DQResult(
        test_name="test_new_account_rate",
        severity="INFO",
        passed=True,
        row_count=int(r.get("ramping_accounts") or 0),
        detail=(
            f"Ramping accounts: {rate:.1%} "
            f"({r.get('ramping_accounts')} of {r.get('active_accounts')}) — excluded from cARR"
        ),
        sample_rows=rows,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

ALL_TESTS = [
    test_null_primary_keys,
    test_negative_credits,
    test_malformed_contracts,
    test_duplicate_log_ids,
    test_contracts_missing_accounts,
    test_accounts_missing_reps,
    test_orphaned_usage,
    test_out_of_contract_usage,
    test_shelfware_rate,
    test_overlapping_contracts,
    test_new_account_rate,
]

SEV_ICON = {"ERROR": "✗", "WARNING": "⚠", "INFO": "ℹ"}


def main():
    parser = argparse.ArgumentParser(description="Run cARR data quality tests")
    parser.add_argument(
        "--as-of-date", metavar="YYYY-MM-DD", default=str(date.today()),
        help="Evaluation date (default: today)",
    )
    parser.add_argument(
        "--fail-on-error", action="store_true",
        help="Exit with code 1 if any ERROR test fails",
    )
    parser.add_argument(
        "--output", metavar="FILE",
        help="Write JSON results to FILE",
    )
    args   = parser.parse_args()
    client = bigquery.Client(project=GCP_PROJECT)

    print(f"\n── Data Quality Report ─────────────────────────────────────────")
    print(f"   Project    : {GCP_PROJECT}  (raw / staging / gtm)")
    print(f"   As-of date : {args.as_of_date}\n")
    print(f"  {'Test':<40} {'Sev':<9} {'Status':<8} {'Rows'}")
    print("  " + "─" * 68)

    results: list[DQResult] = []

    for fn in ALL_TESTS:
        try:
            result = fn(client, as_of_date=args.as_of_date)
        except Exception as e:
            result = DQResult(
                test_name=fn.__name__,
                severity="ERROR",
                passed=False,
                detail=f"Test execution failed: {e}",
            )
        results.append(result)

        icon   = SEV_ICON[result.severity]
        status = "PASS" if result.passed else "FAIL"
        print(f"  {result.test_name:<40} {icon} {result.severity:<7} {status:<8} {result.row_count:,}")
        if not result.passed:
            print(f"    → {result.detail}")

    errors   = [r for r in results if r.severity == "ERROR"   and not r.passed]
    warnings = [r for r in results if r.severity == "WARNING" and not r.passed]
    passed   = [r for r in results if r.passed]

    print("\n  " + "─" * 68)
    print(f"  {len(passed)}/{len(results)} passed · {len(errors)} errors · {len(warnings)} warnings")

    if args.output:
        output = [
            {
                "test_name":   r.test_name,
                "severity":    r.severity,
                "passed":      r.passed,
                "row_count":   r.row_count,
                "detail":      r.detail,
                "sample_rows": r.sample_rows,
            }
            for r in results
        ]
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2, default=str)
        print(f"\n  Results written to {args.output}")

    if args.fail_on_error and errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
