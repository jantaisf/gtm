#!/usr/bin/env python3
"""
Upload demo snapshot CSVs to BigQuery.

Reads dashboard/demo_data/accounts.csv and rep_rollup.csv,
aligns them to the live BigQuery schema, remaps employee_ids to
real reps from raw.sales_reps, and overwrites:
    gtm.cacv_account
    gtm.cacv_rep_rollup

Run:
    python3 data_generation/upload_demo_to_bq.py
"""

from pathlib import Path
import pandas as pd
from google.cloud import bigquery

GCP_PROJECT   = "openclaw-gateway-491103"
DEMO_DATA_DIR = Path(__file__).parent.parent / "dashboard" / "demo_data"

client = bigquery.Client(project=GCP_PROJECT)

print("\n── Uploading demo snapshot to BigQuery ──────────────────────────")

# ── Step 1: fetch real employee_ids from raw.sales_reps ──────────────────────
print("  Loading real sales reps from raw.sales_reps...")
reps_bq = client.query(
    f"SELECT employee_id, name, region, segment FROM `{GCP_PROJECT}.raw.sales_reps`"
).to_dataframe()
print(f"  Found {len(reps_bq)} reps in BigQuery")

# ── Step 2: load demo CSVs ────────────────────────────────────────────────────
accounts_demo = pd.read_csv(DEMO_DATA_DIR / "accounts.csv")
rollup_demo   = pd.read_csv(DEMO_DATA_DIR / "rep_rollup.csv")
print(f"  Demo accounts: {len(accounts_demo):,} rows")
print(f"  Demo rollup  : {len(rollup_demo):,} rows")

# ── Step 3: remap employee_ids ────────────────────────────────────────────────
# The demo CSVs have synthetic employee_ids that don't exist in raw.sales_reps.
# Map demo rep names → real employee_ids by pairing on position within
# each region × segment bucket (order-stable, no name matching needed).

demo_reps = (
    rollup_demo[["employee_id", "rep_name", "region", "segment"]]
    .drop_duplicates("employee_id")
    .sort_values(["region", "segment", "rep_name"])
    .reset_index(drop=True)
)

real_reps = (
    reps_bq[["employee_id", "region", "segment"]]
    .sort_values(["region", "segment", "employee_id"])
    .reset_index(drop=True)
)

# Build demo_id → real_id mapping within each region × segment bucket
id_map = {}
for (region, segment), demo_grp in demo_reps.groupby(["region", "segment"]):
    real_grp = real_reps[
        (real_reps["region"] == region) & (real_reps["segment"] == segment)
    ].reset_index(drop=True)

    for i, demo_row in demo_grp.reset_index(drop=True).iterrows():
        real_row = real_grp.iloc[i % len(real_grp)]
        id_map[demo_row["employee_id"]] = real_row["employee_id"]

print(f"  Mapped {len(id_map)} demo employee_ids → real employee_ids")

# Apply mapping
accounts_demo["employee_id"]      = accounts_demo["employee_id"].map(id_map).fillna(accounts_demo["employee_id"])
accounts_demo["signing_owner_id"] = accounts_demo["signing_owner_id"].map(id_map).fillna(accounts_demo["signing_owner_id"])
rollup_demo["employee_id"]        = rollup_demo["employee_id"].map(id_map).fillna(rollup_demo["employee_id"])

# ── Step 4: align to BigQuery schemas ────────────────────────────────────────

# gtm.cacv_account — drop dashboard-only columns not in BQ schema
acct_bq_cols = [
    "account_id", "employee_id", "signing_owner_id", "company_name", "industry",
    "primary_contract_id", "contract_start_date", "contract_end_date",
    "contract_term_months", "annual_commit_dollars", "included_monthly_compute_credits",
    "has_expansion", "active_contract_count", "trailing_90d_avg_rate",
    "months_of_data", "max_monthly_rate", "overage_months", "zero_usage_months",
    "expansion_flag", "is_spike_drop", "low_data_flag", "is_new_account",
    "health_tier", "cacv", "expansion_signal_acv", "acv_at_risk",
    "as_of_date", "calculated_at",
]
accounts_upload = accounts_demo[[c for c in acct_bq_cols if c in accounts_demo.columns]].copy()

# gtm.cacv_rep_rollup — drop rep_name/region/segment (derived via JOIN in dashboard)
rollup_bq_cols = [
    "employee_id", "region", "segment", "total_accounts", "ramping_accounts",
    "mature_accounts", "total_acv", "total_cacv", "total_acv_at_risk",
    "total_expansion_signal_acv", "cacv_attainment_rate",
    "accounts_expansion", "accounts_healthy", "accounts_at_risk",
    "accounts_shelfware", "accounts_inactive", "accounts_ramping",
    "acv_expansion", "acv_healthy", "acv_at_risk_tiers",
    "expansion_opportunities", "expansion_acv_pipeline",
    "spike_drop_accounts", "mid_year_expansion_accounts",
    "avg_consumption_rate", "as_of_date", "calculated_at",
    "region_rank", "org_rank",
]
rollup_upload = rollup_demo[[c for c in rollup_bq_cols if c in rollup_demo.columns]].copy()

# rep_name is stored in cacv_rep_rollup in BQ — keep it if present
if "rep_name" in rollup_demo.columns and "rep_name" not in rollup_upload.columns:
    rollup_upload.insert(1, "rep_name", rollup_demo["rep_name"])

# ── Step 5: upload ────────────────────────────────────────────────────────────
def upload(df: pd.DataFrame, table: str):
    table_ref  = f"{GCP_PROJECT}.{table}"
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )
    print(f"  Uploading {table} ({len(df):,} rows)...", end=" ", flush=True)
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()
    print("✓")

upload(accounts_upload, "gtm.cacv_account")
upload(rollup_upload,   "gtm.cacv_rep_rollup")

print("\n── Done ──────────────────────────────────────────────────────────")
print("   Restart the Streamlit app to load the updated data from BigQuery.")
