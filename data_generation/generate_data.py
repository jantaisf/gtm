#!/usr/bin/env python3
"""
Phase 1: Synthetic B2B SaaS Data Generator
Prisma Cloud GTM — cARR North Star Metric

Generates four relational tables covering 12 months of data (2024):
  - sales_reps       ~50 rows
  - accounts         ~1,000 rows
  - contracts        ~1,200 rows
  - daily_usage_logs ~200,000 rows

Edge cases injected:
  [1] Spike & Drop       — 5% of accounts burn 90% of credits in Month 1, then near-zero
  [2] Shelfware          — 10% of accounts have high ARR but zero usage logs
  [3] Consistent Overages — 15% of accounts consume 120%+ of monthly credits every month
  [4] Mid-Year Expansions — ~5% of accounts get a second, larger overlapping contract
  [5] Orphaned/Rogue Usage — ~300 log rows with invalid account_ids or out-of-contract dates

Usage:
    # Generate CSVs locally (output/ folder)
    python generate_data.py

    # Generate + upload to BigQuery
    python generate_data.py --upload

    # Preview row counts only
    python generate_data.py --dry-run

Requirements:
    pip install -r requirements.txt
    gcloud auth application-default login   # for --upload
"""

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

# ── Reproducibility ───────────────────────────────────────────────────────────
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker()
Faker.seed(SEED)

# ── BigQuery destination ──────────────────────────────────────────────────────
GCP_PROJECT = "openclaw-gateway-491103"
BQ_DATASET  = "gtm"

# ── Simulation window ─────────────────────────────────────────────────────────
SIM_START = date(2024, 1, 1)
SIM_END   = date.today()

# ── Table sizes ───────────────────────────────────────────────────────────────
N_REPS      = 50
N_ACCOUNTS  = 1_000
N_CONTRACTS = 1_200          # ~1,000 base + expansions + extras

# Accounts whose contract started within this many days of today will be flagged
# as `new_account = TRUE` in the Phase 2 metric pipeline and excluded from
# cARR calculations (insufficient consumption history for trailing 90-day rate).
NEW_ACCOUNT_THRESHOLD_DAYS = 90

# ── Edge case fractions ───────────────────────────────────────────────────────
FRAC_SPIKE_DROP  = 0.05   # 5%  of accounts
FRAC_SHELFWARE   = 0.10   # 10% of accounts
FRAC_OVERAGE     = 0.15   # 15% of accounts
FRAC_EXPANSION   = 0.05   # 5%  of accounts get a second mid-year contract
N_ORPHAN_LOGS    = 300    # rows with bad/missing account references

# ── Prisma Cloud credit pricing reference ────────────────────────────────────
# Source: Prisma Cloud Business Edition = 100 credits at $9,000/year
#   → $90/credit/year baseline (list price, no volume discount)
#
# PANW volume discount ladder (applies to Prisma Cloud multi-year commits):
#   Standard commit (Mid-Market, 1 yr)  : $90/credit/year  (no discount)
#   Large commit   (Enterprise, 2–3 yr) : ~$72/credit/year (~20% volume discount)
#   Shelfware      (large commit, low usage): ~$79/credit/year (~12.5% discount)
#   Overage        (PAYG, above commit) : $90/credit/year  (no discount; billed at list)
#
# Note: Cloud NGFW hourly compute and GB traffic tier pricing is NOT applicable here.
# Prisma Cloud credits cover cloud workload protection units, not network throughput.
CREDIT_PRICE_MIDMARKET   = 90   # $/credit/year — list price, no volume discount
CREDIT_PRICE_ENTERPRISE  = 72   # $/credit/year — ~20% volume discount (2–3 yr term)
CREDIT_PRICE_SHELFWARE   = 79   # $/credit/year — ~12.5% discount (large commit, low usage)
CREDIT_PRICE_OVERAGE     = 90   # $/credit/year — PAYG list price; no discount on overages

# ── Usage pattern weights (Prisma Cloud workload activity rhythm) ─────────────
# Weekday workload scans are ~40% heavier than weekend (CI/CD and prod deployments
# concentrate on business days; cloud workloads run lighter over weekends).
# Spike days: ~8% of days see a 2-3× surge driven by large batch scans,
# compliance sweeps, or incident response forensics.
WEEKDAY_WEIGHT  = 1.0
WEEKEND_WEIGHT  = 0.60
INCIDENT_PROB   = 0.08   # probability any given day is a high-scan day
INCIDENT_MULT   = 2.5    # credits multiplier on spike days

# ── Domain lookups ────────────────────────────────────────────────────────────
REGIONS    = ["Northeast", "Southeast", "Midwest", "West", "International"]
SEGMENTS   = ["Enterprise", "Mid-Market"]
INDUSTRIES = [
    "Financial Services", "Healthcare", "Government & Public Sector",
    "Technology", "Energy & Utilities", "Retail & E-Commerce",
    "Manufacturing", "Telecommunications", "Education",
]

OUTPUT_DIR = Path(__file__).parent / "output"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Sales Reps
# ─────────────────────────────────────────────────────────────────────────────

def build_sales_reps() -> pd.DataFrame:
    records = []
    for i in range(1, N_REPS + 1):
        records.append({
            "rep_id":   f"REP-{i:03d}",
            "name":     fake.name(),
            "region":   random.choice(REGIONS),
            "segment":  random.choice(SEGMENTS),
        })
    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Accounts
# ─────────────────────────────────────────────────────────────────────────────

def build_accounts(reps: pd.DataFrame) -> pd.DataFrame:
    rep_ids = reps["rep_id"].tolist()
    records = []
    for i in range(1, N_ACCOUNTS + 1):
        records.append({
            "account_id":   f"ACC-{i:04d}",
            "company_name": fake.company(),
            "industry":     random.choice(INDUSTRIES),
            "rep_id":       random.choice(rep_ids),
        })
    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Contracts  (+ edge case labels returned for usage generation)
# ─────────────────────────────────────────────────────────────────────────────

def build_contracts(accounts: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Returns (contracts_df, edge_case_map).

    edge_case_map keys:
        shelfware  — set of account_ids with no usage
        spike_drop — set of account_ids with Month-1 spike then silence
        overage    — set of account_ids that consistently over-consume
        expansion  — set of account_ids that have a second mid-year contract
    """
    account_ids = accounts["account_id"].tolist()

    # Assign edge cases (mutually exclusive where it matters)
    shelfware  = set(random.sample(account_ids, int(N_ACCOUNTS * FRAC_SHELFWARE)))
    remaining  = [a for a in account_ids if a not in shelfware]
    spike_drop = set(random.sample(remaining, int(N_ACCOUNTS * FRAC_SPIKE_DROP)))
    remaining  = [a for a in remaining if a not in spike_drop]
    overage    = set(random.sample(remaining, int(N_ACCOUNTS * FRAC_OVERAGE)))
    expansion  = set(random.sample(account_ids, int(N_ACCOUNTS * FRAC_EXPANSION)))

    edge_cases = {
        "shelfware":  shelfware,
        "spike_drop": spike_drop,
        "overage":    overage,
        "expansion":  expansion,
    }

    contracts = []
    ctr_idx = 1

    def _contract_value(acc_id: str) -> tuple[int, int]:
        """
        Return (annual_commit_dollars, included_monthly_compute_credits).

        ARR ranges are calibrated to Prisma Cloud deal sizes:
          Mid-Market : $15K – $150K   (Prisma Cloud Business Edition)
          Enterprise : $100K – $1M    (Prisma Cloud Enterprise Edition)
          Shelfware  : $100K – $500K  (large commits that never activate)
          Overage    : $15K – $80K    (modest commits consistently exceeded)

        Credits are derived from ARR using Prisma Cloud credit pricing:
          $90/credit/year → monthly_credits = ARR / CREDIT_PRICE_PER_YEAR
          ±15% noise simulates negotiated discounts / premium tiers.
        """
        def _arr_to_monthly_credits(arr: int, price_per_year: int) -> int:
            # Annual credits = ARR / price_per_credit_per_year
            # Monthly allocation = annual_credits / 12
            # ±15% noise simulates deal-level negotiation
            annual_credits = arr / price_per_year
            noise = random.uniform(0.85, 1.15)
            return max(10, int(annual_credits * noise / 12))

        if acc_id in shelfware:
            arr = random.randint(100_000, 500_000)
            return arr, _arr_to_monthly_credits(arr, CREDIT_PRICE_SHELFWARE)
        if acc_id in overage:
            arr = random.randint(15_000, 80_000)
            return arr, _arr_to_monthly_credits(arr, CREDIT_PRICE_OVERAGE)
        # Normal: size by segment (proxy via rep_id range)
        rep_num = int(accounts.loc[accounts["account_id"] == acc_id, "rep_id"]
                      .iloc[0].split("-")[1])
        if rep_num <= 25:  # first 25 reps = Enterprise — volume discount applies
            arr = random.randint(100_000, 1_000_000)
            return arr, _arr_to_monthly_credits(arr, CREDIT_PRICE_ENTERPRISE)
        arr = random.randint(15_000, 150_000)
        return arr, _arr_to_monthly_credits(arr, CREDIT_PRICE_MIDMARKET)

    def _contract_term(acc_id: str) -> int:
        """
        Contract term in years (1, 2, or 3).
        Enterprise skews multi-year (larger upfront discount per PANW pricing).
        Mid-Market mostly annual.
        end_date = start_date + term_years * 365 days.
        """
        rep_num = int(accounts.loc[accounts["account_id"] == acc_id, "rep_id"]
                      .iloc[0].split("-")[1])
        if rep_num <= 25:  # Enterprise
            return random.choices([1, 2, 3], weights=[0.30, 0.45, 0.25])[0]
        return random.choices([1, 2, 3], weights=[0.70, 0.25, 0.05])[0]

    # Base contract — one per account, start dates spread across full window
    window_days = (SIM_END - SIM_START).days
    for acc_id in account_ids:
        arr, credits = _contract_value(acc_id)
        term  = _contract_term(acc_id)
        start = SIM_START + timedelta(days=random.randint(0, window_days))
        end   = start + timedelta(days=term * 365)
        contracts.append({
            "contract_id":                      f"CTR-{ctr_idx:04d}",
            "account_id":                       acc_id,
            "start_date":                       start,
            "end_date":                         end,
            "annual_commit_dollars":            arr,
            "included_monthly_compute_credits": credits,
            "contract_term_years":              term,
        })
        ctr_idx += 1

    # Edge case [4]: Mid-year expansion — second, larger overlapping contract
    for acc_id in expansion:
        base       = next(c for c in contracts if c["account_id"] == acc_id)
        exp_start  = base["start_date"] + timedelta(days=random.randint(150, 210))
        term       = _contract_term(acc_id)
        exp_end    = exp_start + timedelta(days=term * 365)
        multiplier = random.uniform(1.3, 2.5)
        contracts.append({
            "contract_id":                      f"CTR-{ctr_idx:04d}",
            "account_id":                       acc_id,
            "start_date":                       exp_start,
            "end_date":                         exp_end,
            "annual_commit_dollars":            int(base["annual_commit_dollars"] * multiplier),
            "included_monthly_compute_credits": int(base["included_monthly_compute_credits"] * multiplier),
            "contract_term_years":              term,
        })
        ctr_idx += 1

    # Pad to N_CONTRACTS with additional contracts on random accounts
    while len(contracts) < N_CONTRACTS:
        acc_id = random.choice(account_ids)
        arr, credits = _contract_value(acc_id)
        term  = _contract_term(acc_id)
        start = SIM_START + timedelta(days=random.randint(0, window_days))
        contracts.append({
            "contract_id":                      f"CTR-{ctr_idx:04d}",
            "account_id":                       acc_id,
            "start_date":                       start,
            "end_date":                         start + timedelta(days=term * 365),
            "annual_commit_dollars":            arr,
            "included_monthly_compute_credits": credits,
            "contract_term_years":              term,
        })
        ctr_idx += 1

    df = pd.DataFrame(contracts)
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"]   = pd.to_datetime(df["end_date"])
    return df, edge_cases


# ─────────────────────────────────────────────────────────────────────────────
# 4. Daily Usage Logs
# ─────────────────────────────────────────────────────────────────────────────

def build_usage_logs(
    accounts: pd.DataFrame,
    contracts: pd.DataFrame,
    edge_cases: dict,
) -> pd.DataFrame:
    """
    Generates daily usage rows per account based on their edge case category.

    Edge cases injected here:
        [1] Spike & Drop   — huge Month 1 burst, then near-zero tail
        [2] Shelfware      — skipped entirely (zero rows)
        [3] Overage        — daily consumption set at 120–160% of monthly budget
        [5] Orphaned/Rogue — appended at end: ghost account_ids + out-of-range dates
    """
    shelfware  = edge_cases["shelfware"]
    spike_drop = edge_cases["spike_drop"]
    overage    = edge_cases["overage"]

    # Build a lookup: account_id → primary contract (earliest start_date)
    primary = (
        contracts.sort_values("start_date")
        .groupby("account_id")
        .first()
        .reset_index()
        [["account_id", "start_date", "end_date", "included_monthly_compute_credits"]]
        .set_index("account_id")
    )

    all_dates = pd.date_range(SIM_START, SIM_END, freq="D")
    rows = []
    log_idx = 1

    for acc_id in accounts["account_id"]:

        # Edge case [2]: Shelfware — no usage rows at all
        if acc_id in shelfware:
            continue

        if acc_id not in primary.index:
            continue

        info = primary.loc[acc_id]
        monthly_budget = float(info["included_monthly_compute_credits"])
        daily_budget   = monthly_budget / 30.0

        # Dates within this account's contract window
        contract_dates = [
            d for d in all_dates
            if info["start_date"] <= d <= info["end_date"]
        ]
        if not contract_dates:
            continue

        # Edge case [1]: Spike & Drop
        if acc_id in spike_drop:
            annual_total  = monthly_budget * 12
            spike_pool    = annual_total * 0.90
            spike_days    = [d for d in contract_dates if (d - contract_dates[0]).days < 31]
            tail_days     = [d for d in contract_dates if (d - contract_dates[0]).days >= 31]

            for d in spike_days:
                daily_share = spike_pool / max(len(spike_days), 1)
                rows.append({
                    "log_id":                   f"LOG-{log_idx:07d}",
                    "account_id":               acc_id,
                    "date":                     d.date(),
                    "compute_credits_consumed": round(max(0, np.random.normal(daily_share, daily_share * 0.1)), 2),
                })
                log_idx += 1

            # Sparse, near-zero tail (sample ~10% of remaining days)
            # Guard: tail_days may be empty for contracts that started recently
            if tail_days:
                tail_sample = random.sample(tail_days, max(1, int(len(tail_days) * 0.10)))
            else:
                tail_sample = []
            for d in tail_sample:
                rows.append({
                    "log_id":                   f"LOG-{log_idx:07d}",
                    "account_id":               acc_id,
                    "date":                     d.date(),
                    "compute_credits_consumed": round(max(0, np.random.normal(1.5, 0.5)), 2),
                })
                log_idx += 1

        # Edge case [3]: Consistent Overages
        # Accounts whose cloud workload growth outpaces their contracted credit
        # allowance — overage billed at PAYG list price ($90/credit/year).
        elif acc_id in overage:
            overage_multiplier = random.uniform(1.20, 1.60)
            for d in contract_dates:
                day_weight = WEEKDAY_WEIGHT if d.weekday() < 5 else WEEKEND_WEIGHT
                is_incident = random.random() < INCIDENT_PROB
                multiplier  = INCIDENT_MULT if is_incident else overage_multiplier
                rows.append({
                    "log_id":                   f"LOG-{log_idx:07d}",
                    "account_id":               acc_id,
                    "date":                     d.date(),
                    "compute_credits_consumed": round(
                        max(0, np.random.normal(
                            daily_budget * multiplier * day_weight,
                            daily_budget * 0.12,
                        )), 2,
                    ),
                })
                log_idx += 1

        # Normal healthy usage — weekday/weekend rhythm + occasional incident spikes
        else:
            consumption_pct = random.uniform(0.65, 0.95)
            for d in contract_dates:
                # Skip ~20% of days (firewall still logs but below threshold)
                if random.random() < 0.20:
                    continue
                day_weight  = WEEKDAY_WEIGHT if d.weekday() < 5 else WEEKEND_WEIGHT
                is_incident = random.random() < INCIDENT_PROB
                multiplier  = INCIDENT_MULT if is_incident else consumption_pct
                rows.append({
                    "log_id":                   f"LOG-{log_idx:07d}",
                    "account_id":               acc_id,
                    "date":                     d.date(),
                    "compute_credits_consumed": round(
                        max(0, np.random.normal(
                            daily_budget * multiplier * day_weight,
                            daily_budget * 0.20,
                        )), 2,
                    ),
                })
                log_idx += 1

    # Edge case [5a]: Orphaned — account_id not in Accounts table
    ghost_ids = [f"ACC-GHOST-{i:03d}" for i in range(1, 101)]
    for _ in range(N_ORPHAN_LOGS // 2):
        rows.append({
            "log_id":                   f"LOG-{log_idx:07d}",
            "account_id":               random.choice(ghost_ids),
            "date":                     fake.date_between(SIM_START, SIM_END),
            "compute_credits_consumed": round(random.uniform(10, 500), 2),
        })
        log_idx += 1

    # Edge case [5b]: Rogue — valid account_id but date far outside contract window
    valid_ids = accounts["account_id"].tolist()
    for _ in range(N_ORPHAN_LOGS // 2):
        if random.random() < 0.5:
            rogue_date = SIM_START - timedelta(days=random.randint(60, 180))
        else:
            rogue_date = SIM_END + timedelta(days=random.randint(60, 180))
        rows.append({
            "log_id":                   f"LOG-{log_idx:07d}",
            "account_id":               random.choice(valid_ids),
            "date":                     rogue_date,
            "compute_credits_consumed": round(random.uniform(5, 300), 2),
        })
        log_idx += 1

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ─────────────────────────────────────────────────────────────────────────────
# BigQuery upload
# ─────────────────────────────────────────────────────────────────────────────

def upload_to_bigquery(tables: dict[str, pd.DataFrame]) -> None:
    try:
        from google.cloud import bigquery
        from google.api_core.exceptions import Conflict
    except ImportError:
        raise SystemExit("Missing dependency: pip install google-cloud-bigquery pyarrow")

    client = bigquery.Client(project=GCP_PROJECT)

    # Create dataset if it doesn't exist
    dataset_ref = bigquery.Dataset(f"{GCP_PROJECT}.{BQ_DATASET}")
    dataset_ref.location = "US"
    try:
        client.create_dataset(dataset_ref)
        print(f"  Created dataset: {BQ_DATASET}")
    except Conflict:
        print(f"  Dataset already exists: {BQ_DATASET}")

    bq_schemas = {
        "sales_reps": [
            bigquery.SchemaField("rep_id",   "STRING", mode="REQUIRED"),
            bigquery.SchemaField("name",     "STRING"),
            bigquery.SchemaField("region",   "STRING"),
            bigquery.SchemaField("segment",  "STRING"),
        ],
        "accounts": [
            bigquery.SchemaField("account_id",   "STRING", mode="REQUIRED"),
            bigquery.SchemaField("company_name", "STRING"),
            bigquery.SchemaField("industry",     "STRING"),
            bigquery.SchemaField("rep_id",       "STRING"),
        ],
        "contracts": [
            bigquery.SchemaField("contract_id",                      "STRING",  mode="REQUIRED"),
            bigquery.SchemaField("account_id",                       "STRING"),
            bigquery.SchemaField("start_date",                       "DATE"),
            bigquery.SchemaField("end_date",                         "DATE"),
            bigquery.SchemaField("annual_commit_dollars",            "INTEGER"),
            bigquery.SchemaField("included_monthly_compute_credits", "INTEGER"),
            bigquery.SchemaField("contract_term_years",              "INTEGER"),
        ],
        "daily_usage_logs": [
            bigquery.SchemaField("log_id",                    "STRING",  mode="REQUIRED"),
            bigquery.SchemaField("account_id",                "STRING"),
            bigquery.SchemaField("date",                      "DATE"),
            bigquery.SchemaField("compute_credits_consumed",  "FLOAT"),
        ],
    }

    for name, df in tables.items():
        table_ref  = f"{GCP_PROJECT}.{BQ_DATASET}.{name}"
        job_config = bigquery.LoadJobConfig(
            schema=bq_schemas[name],
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        print(f"  Uploading {name} ({len(df):,} rows)...", end=" ", flush=True)
        job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
        job.result()
        print("✓")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate GTM North Star synthetic dataset")
    parser.add_argument("--upload",   action="store_true", help="Upload tables to BigQuery after generation")
    parser.add_argument("--dry-run",  action="store_true", help="Show row counts only, no files written")
    args = parser.parse_args()

    print("\n── Generating synthetic B2B SaaS dataset ──────────────────────────")
    print(f"   Window : {SIM_START} → {SIM_END}")
    print(f"   Seed   : {SEED}\n")

    reps = build_sales_reps()
    print(f"  sales_reps      : {len(reps):>7,} rows")

    accounts = build_accounts(reps)
    print(f"  accounts        : {len(accounts):>7,} rows")

    contracts, edge_cases = build_contracts(accounts)
    print(f"  contracts       : {len(contracts):>7,} rows")
    print(f"    ↳ edge cases  : shelfware={len(edge_cases['shelfware'])}  "
          f"spike_drop={len(edge_cases['spike_drop'])}  "
          f"overage={len(edge_cases['overage'])}  "
          f"expansion={len(edge_cases['expansion'])}")

    usage = build_usage_logs(accounts, contracts, edge_cases)
    print(f"  daily_usage_logs: {len(usage):>7,} rows")
    print(f"    ↳ orphaned logs (ghost accounts)  : {N_ORPHAN_LOGS // 2}")
    print(f"    ↳ rogue logs (out-of-range dates) : {N_ORPHAN_LOGS // 2}")

    if args.dry_run:
        print("\n  [dry-run] No files written.")
        return

    tables = {
        "sales_reps":       reps,
        "accounts":         accounts,
        "contracts":        contracts,
        "daily_usage_logs": usage,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("\n── Writing CSVs ────────────────────────────────────────────────────")
    for name, df in tables.items():
        path = OUTPUT_DIR / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"  ✓ {path}")

    if args.upload:
        print("\n── Uploading to BigQuery ───────────────────────────────────────────")
        print(f"  Project : {GCP_PROJECT}")
        print(f"  Dataset : {BQ_DATASET}\n")
        upload_to_bigquery(tables)
        print(f"\n  Done. Tables live at {GCP_PROJECT}.{BQ_DATASET}")
    else:
        print(f"\n  Run with --upload to push to BigQuery ({GCP_PROJECT}.{BQ_DATASET})")


if __name__ == "__main__":
    main()
