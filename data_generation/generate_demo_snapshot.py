#!/usr/bin/env python3
"""
Demo Snapshot Generator
Generates realistic dashboard demo data (accounts.csv, rep_rollup.csv)
directly — without requiring a BigQuery connection or a full pipeline run.

The output mirrors the schema produced by run_pipeline.py so the Streamlit
dashboard can load it as a drop-in CSV fallback.

Target health tier distribution (primarily healthy, with visible variance):
    Expansion  15%  — consumption > 100% of commit; upsell signal
    Healthy    50%  — 70–99% of commit; the expected steady state
    At Risk    15%  — 40–69% of commit; renewal intervention needed
    Shelfware   8%  — 2–39% of commit; large commit, low activation
    Inactive    4%  — ~0% consumption; no recent platform activity
    Ramping     8%  — new accounts within 90 days; excluded from cACV

Run:
    python3 data_generation/generate_demo_snapshot.py
"""

import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

# ── Reproducibility ───────────────────────────────────────────────────────────
SEED = 99   # distinct from generate_data.py (seed=42) for a fresh set of names
random.seed(SEED)
np.random.seed(SEED)
fake = Faker()
Faker.seed(SEED)

# ── Snapshot parameters ───────────────────────────────────────────────────────
AS_OF_DATE     = date(2026, 6, 1)
CALCULATED_AT  = "2026-06-01 08:45:00+00:00"
OUTPUT_DIR     = Path(__file__).parent.parent / "dashboard" / "demo_data"

# ── Rep structure ─────────────────────────────────────────────────────────────
# (region, enterprise_count, midmarket_count) — mirrors generate_data.py
REGION_HEADCOUNT = [
    ("West",          5,  7),
    ("Northeast",     4,  5),
    ("Southeast",     3,  4),
    ("Midwest",       2,  4),
    ("International", 6, 10),
]

INDUSTRIES = [
    "Financial Services", "Healthcare", "Government & Public Sector",
    "Technology", "Energy & Utilities", "Retail & E-Commerce",
    "Manufacturing", "Telecommunications", "Education",
]

# ── Health tier configuration ─────────────────────────────────────────────────
# count        : target account count for this tier
# rate_range   : (min, max) trailing_90d_avg_rate; None = NULL (Ramping)
# short_noise  : std dev added to 90d rate to produce 7d rate (high volatility)
# mid_noise    : std dev added to 90d rate to produce 30d rate (moderate volatility)
TIER_CONFIG = {
    "Expansion": {"count": 100, "rate_range": (1.05, 1.60), "short_noise": 0.09, "mid_noise": 0.05},
    "Healthy":   {"count": 325, "rate_range": (0.72, 0.99), "short_noise": 0.10, "mid_noise": 0.05},
    "At Risk":   {"count": 100, "rate_range": (0.40, 0.69), "short_noise": 0.08, "mid_noise": 0.04},
    "Shelfware": {"count":  50, "rate_range": (0.02, 0.18), "short_noise": 0.02, "mid_noise": 0.01},
    "Inactive":  {"count":  25, "rate_range": (0.00, 0.00), "short_noise": 0.00, "mid_noise": 0.00},
    "Ramping":   {"count":  55, "rate_range": (None, None), "short_noise": 0.00, "mid_noise": 0.00},
}
# Total: 655 accounts

# ── ACV ranges by segment ─────────────────────────────────────────────────────
ACV_RANGES = {
    "Enterprise":  (200_000, 1_500_000),
    "Mid-Market":  (40_000,   280_000),
}

# ── Health tier thresholds (must match pipeline SQL) ─────────────────────────
# Expansion  rate >= 1.00
# Healthy    0.70 <= rate < 1.00
# At Risk    0.40 <= rate < 0.70
# Shelfware  0.00 < rate < 0.40
# Inactive   rate == 0.00


def _clamp_rate(rate: float, tier: str) -> float:
    """Keep generated rate within the tier's valid window after noise is applied."""
    bounds = {
        "Expansion": (1.00, 3.0),
        "Healthy":   (0.70, 0.999),
        "At Risk":   (0.40, 0.699),
        "Shelfware": (0.01, 0.399),
        "Inactive":  (0.00, 0.00),
        "Ramping":   (None, None),
    }
    lo, hi = bounds[tier]
    if lo is None:
        return rate
    return float(np.clip(rate, lo, hi))


# ─────────────────────────────────────────────────────────────────────────────
# 1. Build reps
# ─────────────────────────────────────────────────────────────────────────────

def build_reps() -> pd.DataFrame:
    records = []
    for region, ent_count, mm_count in REGION_HEADCOUNT:
        for segment, count in [("Enterprise", ent_count), ("Mid-Market", mm_count)]:
            for _ in range(count):
                records.append({
                    "employee_id": str(uuid.uuid4()),
                    "rep_name":    fake.name(),
                    "region":      region,
                    "segment":     segment,
                })
    random.shuffle(records)
    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Build accounts
# ─────────────────────────────────────────────────────────────────────────────

def build_accounts(reps: pd.DataFrame) -> pd.DataFrame:
    rep_pool = reps.to_dict("records")

    rows = []

    for tier, cfg in TIER_CONFIG.items():
        rate_lo, rate_hi = cfg["rate_range"]
        short_noise = cfg["short_noise"]
        mid_noise   = cfg["mid_noise"]

        for _ in range(cfg["count"]):
            rep      = random.choice(rep_pool)
            segment  = rep["segment"]
            acv_lo, acv_hi = ACV_RANGES[segment]

            # ACV — log-uniform so small and large deals both appear
            acv = int(np.exp(np.random.uniform(np.log(acv_lo), np.log(acv_hi))) // 1000 * 1000)

            # Contract dates — active at AS_OF_DATE
            # Ramping: started within the last 60 days
            # Others: started 6–24 months ago, ends 3–18 months from now
            if tier == "Ramping":
                start = AS_OF_DATE - timedelta(days=random.randint(10, 85))
                term_months = random.choice([12, 24])
            else:
                start = AS_OF_DATE - timedelta(days=random.randint(180, 730))
                term_months = random.choices([12, 24, 36], weights=[0.50, 0.35, 0.15])[0]

            from dateutil.relativedelta import relativedelta
            end = start + relativedelta(months=term_months) - timedelta(days=1)

            # Monthly credit allocation (ACV / $126 per credit per year, ÷12 for monthly)
            monthly_credits = max(10, int(acv / 126 / 12 * random.uniform(0.85, 1.15)))

            # Consumption rates
            if tier == "Ramping":
                rate_90d  = None
                rate_30d  = None
                rate_7d   = None
            elif tier == "Inactive":
                rate_90d = 0.0
                rate_30d = 0.0
                rate_7d  = 0.0
            else:
                rate_90d = _clamp_rate(random.uniform(rate_lo, rate_hi), tier)
                # 30d and 7d have progressively more noise vs the 90d anchor
                rate_30d = _clamp_rate(
                    rate_90d + np.random.normal(0, mid_noise), tier
                )
                rate_7d  = _clamp_rate(
                    rate_90d + np.random.normal(0, short_noise), tier
                )

            # Derived metrics
            is_new    = tier == "Ramping"
            if is_new or rate_90d is None:
                cacv               = None
                expansion_signal   = None
                acv_at_risk        = None
                overage_months     = 0
                zero_usage_months  = 0
                max_monthly_rate   = None
                months_of_data     = random.randint(0, 2)
                expansion_flag     = False
            else:
                cacv             = round(acv * min(1.0, rate_90d), 2)
                expansion_signal = round(max(0.0, acv * (rate_90d - 1.0)), 2)
                acv_at_risk      = round(acv - cacv, 2)
                overage_months   = random.randint(2, 6) if tier == "Expansion" else (
                                   random.randint(0, 1) if tier == "Healthy" else 0)
                zero_usage_months = (random.randint(1, 3) if tier == "Shelfware" else
                                     (random.randint(5, 9) if tier == "Inactive" else 0))
                max_monthly_rate  = round(rate_90d * random.uniform(1.05, 1.40), 3)
                months_of_data    = random.randint(3, 12)
                expansion_flag    = tier == "Expansion" and overage_months >= 2

            has_expansion      = random.random() < 0.15
            is_spike_drop      = tier == "Inactive" and random.random() < 0.3
            low_data_flag      = months_of_data < 3 if months_of_data is not None else False

            rows.append({
                "account_id":                       str(uuid.uuid4()),
                "employee_id":                      rep["employee_id"],
                "signing_owner_id":                 rep["employee_id"],
                "company_name":                     fake.company(),
                "industry":                         random.choice(INDUSTRIES),
                "primary_contract_id":              str(uuid.uuid4()),
                "contract_start_date":              start.isoformat(),
                "contract_end_date":                end.isoformat(),
                "contract_term_months":             term_months,
                "annual_commit_dollars":            acv,
                "included_monthly_compute_credits": monthly_credits,
                "has_expansion":                    has_expansion,
                "active_contract_count":            2 if has_expansion else 1,
                "trailing_7d_avg_rate":             round(rate_7d,  4) if rate_7d  is not None else None,
                "trailing_30d_avg_rate":            round(rate_30d, 4) if rate_30d is not None else None,
                "trailing_90d_avg_rate":            round(rate_90d, 4) if rate_90d is not None else None,
                "months_of_data":                   months_of_data,
                "max_monthly_rate":                 max_monthly_rate,
                "overage_months":                   overage_months,
                "zero_usage_months":                zero_usage_months,
                "expansion_flag":                   expansion_flag,
                "is_spike_drop":                    is_spike_drop,
                "low_data_flag":                    low_data_flag,
                "is_new_account":                   is_new,
                "health_tier":                      tier,
                "cacv":                             cacv,
                "expansion_signal_acv":             expansion_signal,
                "acv_at_risk":                      acv_at_risk,
                "as_of_date":                       AS_OF_DATE.isoformat(),
                "calculated_at":                    CALCULATED_AT,
                "rep_name":                         rep["rep_name"],
                "region":                           rep["region"],
                "segment":                          segment,
            })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Aggregate to rep rollup
# ─────────────────────────────────────────────────────────────────────────────

def build_rep_rollup(accounts: pd.DataFrame, reps: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, rep in reps.iterrows():
        emp_id  = rep["employee_id"]
        rep_accts = accounts[accounts["employee_id"] == emp_id].copy()

        if rep_accts.empty:
            continue

        mature  = rep_accts[~rep_accts["is_new_account"]]
        ramping = rep_accts[rep_accts["is_new_account"]]

        total_acv     = int(rep_accts["annual_commit_dollars"].sum())
        total_cacv    = float(mature["cacv"].fillna(0).sum())
        total_risk    = float(mature["acv_at_risk"].fillna(0).sum())
        total_exp_sig = float(mature["expansion_signal_acv"].fillna(0).sum())
        att_rate      = round(total_cacv / total_acv, 4) if total_acv else 0.0

        tier_counts = rep_accts["health_tier"].value_counts().to_dict()

        # ACV by tier
        acv_expansion = int(rep_accts[rep_accts["health_tier"] == "Expansion"]["annual_commit_dollars"].sum())
        acv_healthy   = int(rep_accts[rep_accts["health_tier"] == "Healthy"]["annual_commit_dollars"].sum())
        acv_at_risk_t = int(rep_accts[rep_accts["health_tier"].isin(["At Risk","Shelfware","Inactive"])]["annual_commit_dollars"].sum())

        exp_opps     = int(rep_accts["expansion_flag"].sum())
        exp_pipeline = float(rep_accts[rep_accts["expansion_flag"]]["expansion_signal_acv"].fillna(0).sum())

        avg_rate = float(mature["trailing_90d_avg_rate"].dropna().mean()) if not mature.empty else 0.0

        rows.append({
            "employee_id":               emp_id,
            "rep_name":                  rep["rep_name"],
            "region":                    rep["region"],
            "segment":                   rep["segment"],
            "total_accounts":            len(rep_accts),
            "ramping_accounts":          len(ramping),
            "mature_accounts":           len(mature),
            "total_acv":                 total_acv,
            "total_cacv":                round(total_cacv, 2),
            "total_acv_at_risk":         round(total_risk, 2),
            "total_expansion_signal_acv": round(total_exp_sig, 2),
            "cacv_attainment_rate":      att_rate,
            "accounts_expansion":        tier_counts.get("Expansion", 0),
            "accounts_healthy":          tier_counts.get("Healthy", 0),
            "accounts_at_risk":          tier_counts.get("At Risk", 0),
            "accounts_shelfware":        tier_counts.get("Shelfware", 0),
            "accounts_inactive":         tier_counts.get("Inactive", 0),
            "accounts_ramping":          tier_counts.get("Ramping", 0),
            "acv_expansion":             acv_expansion,
            "acv_healthy":               acv_healthy,
            "acv_at_risk_tiers":         acv_at_risk_t,
            "expansion_opportunities":   exp_opps,
            "expansion_acv_pipeline":    round(exp_pipeline, 2),
            "spike_drop_accounts":       int(rep_accts["is_spike_drop"].sum()),
            "mid_year_expansion_accounts": int(rep_accts["has_expansion"].sum()),
            "avg_consumption_rate":      round(avg_rate, 4),
            "as_of_date":                AS_OF_DATE.isoformat(),
            "calculated_at":             CALCULATED_AT,
        })

    rollup = pd.DataFrame(rows)

    # Region rank (within segment × region) and org rank (by total_cacv)
    rollup["region_rank"] = (
        rollup.groupby(["region", "segment"])["total_cacv"]
              .rank(ascending=False, method="min")
              .astype(int)
    )
    rollup["org_rank"] = (
        rollup["total_cacv"]
              .rank(ascending=False, method="min")
              .astype(int)
    )

    return rollup.sort_values("org_rank").reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    from dateutil.relativedelta import relativedelta  # ensure import is available

    print("\n── Generating demo snapshot ─────────────────────────────────────────")
    print(f"   As-of date : {AS_OF_DATE}")
    print(f"   Output dir : {OUTPUT_DIR}\n")

    reps     = build_reps()
    accounts = build_accounts(reps)
    rollup   = build_rep_rollup(accounts, reps)

    # Summary
    tier_dist = accounts["health_tier"].value_counts()
    print("  Health tier distribution:")
    for tier in ["Expansion","Healthy","At Risk","Shelfware","Inactive","Ramping"]:
        n   = tier_dist.get(tier, 0)
        pct = n / len(accounts) * 100
        print(f"    {tier:<12} {n:>4}  ({pct:.0f}%)")

    mature = accounts[~accounts["is_new_account"]]
    avg_rate = mature["trailing_90d_avg_rate"].dropna().mean()
    avg_att  = rollup["cacv_attainment_rate"].mean()
    print(f"\n  Avg trailing 90-day consumption rate : {avg_rate:.1%}")
    print(f"  Avg rep Consumption ACV attainment   : {avg_att:.1%}")
    print(f"\n  Accounts : {len(accounts):,}")
    print(f"  Reps     : {len(rollup):,}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    accounts_path = OUTPUT_DIR / "accounts.csv"
    rollup_path   = OUTPUT_DIR / "rep_rollup.csv"

    accounts.to_csv(accounts_path, index=False)
    rollup.to_csv(rollup_path,   index=False)

    print(f"\n  ✓ {accounts_path}")
    print(f"  ✓ {rollup_path}")
    print("\n── Done ─────────────────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
