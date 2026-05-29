# Technical Spec: cARR Data Pipeline
## Prisma Cloud Consumed ARR — End-to-End Architecture

**Version:** 1.0
**Owner:** Principal PM, Analytics & AI
**Depends on:** product_spec.md v1.0
**Status:** Implementation-ready
**Last Updated:** May 2026

---

## 1. Architecture Overview

```
┌─────────────────────────┐
│   Phase 1: Raw Data      │
│   BigQuery Dataset: gtm  │
│                          │
│  · sales_reps            │
│  · accounts              │
│  · contracts             │
│  · daily_usage_logs      │
└──────────┬──────────────┘
           │ SQL transforms
           ▼
┌─────────────────────────┐
│   Staging Layer          │
│                          │
│  · stg_active_contracts  │  Resolves overlapping contracts,
│  · stg_monthly_consumption│  cleans orphaned/rogue usage
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│   Metric Layer           │
│                          │
│  · carr_account          │  cARR per account + health tier
│  · carr_rep_rollup       │  cARR per rep + region
└──────────┬──────────────┘
           │ Python BigQuery client
           ▼
┌─────────────────────────┐
│   Dashboard              │
│   Streamlit + Plotly     │
│   (Phase 2 Part 4)       │
└─────────────────────────┘
```

---

## 2. BigQuery Schema

### Raw Tables (Phase 1 output)

#### `sales_reps`
| Column | Type | Notes |
|---|---|---|
| `rep_id` | STRING | PK — format `REP-NNN` |
| `name` | STRING | |
| `region` | STRING | Northeast / Southeast / Midwest / West / International |
| `segment` | STRING | Enterprise / Mid-Market |

#### `accounts`
| Column | Type | Notes |
|---|---|---|
| `account_id` | STRING | PK — format `ACC-NNNN` |
| `company_name` | STRING | |
| `industry` | STRING | |
| `rep_id` | STRING | FK → sales_reps.rep_id |

#### `contracts`
| Column | Type | Notes |
|---|---|---|
| `contract_id` | STRING | PK — format `CTR-NNNN` |
| `account_id` | STRING | FK → accounts.account_id |
| `start_date` | DATE | |
| `end_date` | DATE | Derived: start_date + contract_term_months calendar months (e.g. 2026-01-01 + 12mo = 2027-01-01) |
| `annual_commit_dollars` | INTEGER | ACV — annualized contract value |
| `included_monthly_compute_credits` | INTEGER | Monthly credit allowance (Option A: use-it-or-lose-it per month) |
| `contract_term_months` | INTEGER | 12 / 24 / 36 — Enterprise skews multi-year |

#### `daily_usage_logs`
| Column | Type | Notes |
|---|---|---|
| `log_id` | STRING | PK — format `LOG-NNNNNNN` |
| `account_id` | STRING | May reference non-existent accounts (orphan edge case) |
| `date` | DATE | May fall outside contract window (rogue usage edge case) |
| `compute_credits_consumed` | FLOAT | Daily credit burn |

### Derived Tables (Pipeline output)

| Table | Description |
|---|---|
| `stg_active_contracts` | One row per account — canonical active contract + summed credits |
| `stg_monthly_consumption` | One row per account per month — clean usage vs. allowance |
| `carr_account` | Account-level cARR, consumption rate, health tier, flags |
| `carr_rep_rollup` | Rep + region-level cARR rollup for dashboard and comp |

---

## 3. Pipeline Step-by-Step Logic

### Step 1 — `stg_active_contracts`

**Purpose:** Resolve which contract(s) are active per account and produce a single canonical row.

**Logic:**
1. Filter contracts where `as_of_date BETWEEN start_date AND end_date`
2. Exclude malformed contracts where `end_date < start_date`
3. For accounts with multiple active contracts (mid-year expansions):
   - ARR basis = contract with highest `annual_commit_dollars`
   - Monthly credits = **SUM** across all active contracts
   - Set `has_expansion = TRUE`
4. Join to `accounts` to carry `rep_id`, `company_name`, `industry`

**Edge cases handled:**
- Mid-year expansions → credits summed, ARR uses highest-value contract
- Malformed contracts → excluded via `end_date >= start_date` guard

---

### Step 2 — `stg_monthly_consumption`

**Purpose:** Aggregate daily usage to monthly totals per account, with edge case filtering.

**Logic:**
1. **Orphan guard:** `INNER JOIN accounts` — logs with unknown `account_id` are excluded
2. **Rogue usage guard:** `JOIN contracts ON date BETWEEN start_date AND end_date` — out-of-window logs excluded
3. Aggregate: `SUM(compute_credits_consumed)` grouped by `account_id`, `DATE_TRUNC(date, MONTH)`
4. **Shelfware guard:** `LEFT JOIN` from contract months — accounts with zero logs get `credits_consumed = 0`
5. Compute `consumption_rate = credits_consumed / included_monthly_compute_credits` (cap at 2.0 to limit outlier distortion)
6. Flag `is_zero_usage_month = TRUE` for months with no consumption

**Edge cases handled:**
- Orphaned usage → excluded via INNER JOIN
- Out-of-contract usage → excluded via date-range JOIN
- Shelfware (zero logs) → LEFT JOIN produces 0 consumption rate

---

### Step 3 — `carr_account`

**Purpose:** Compute account-level cARR using trailing 90-day consumption rate.

**Logic:**
1. For each account, take the **last 3 complete calendar months** of consumption data
2. Compute `trailing_90d_avg_rate = AVG(consumption_rate)` over those 3 months
3. Apply health tier classification (see product_spec.md §4)
4. Flag new accounts: `new_account = TRUE` if `contract_start_date >= as_of_date - 90 days`
5. Compute:
   ```
   cARR = annual_commit_dollars × trailing_90d_avg_rate   (if not new_account)
   cARR = NULL                                             (if new_account)
   ```
6. Compute `arr_at_risk = annual_commit_dollars - cARR`
7. Flag `expansion_flag = TRUE` if `overage_months >= 2`
8. Flag `is_spike_drop = TRUE` if `max_monthly_rate > 2.0 AND trailing_90d_avg_rate < 0.05`

**Edge cases handled:**
- Spike & Drop → trailing 90-day window smooths spike once it ages out
- New accounts → excluded from cARR with `new_account` flag
- Consistent overages → `expansion_flag` surfaced; cARR reflects true consumption

---

### Step 4 — `carr_rep_rollup`

**Purpose:** Aggregate account cARR to rep and region level for dashboard and compensation.

**Logic:**
1. Join `carr_account` to `sales_reps` on `rep_id`
2. Aggregate per rep:
   - `total_arr` = SUM of `annual_commit_dollars`
   - `total_carr` = SUM of `cARR` (excludes new_account NULLs)
   - `carr_attainment_rate` = `total_carr / total_arr`
   - Health tier counts: `accounts_expansion`, `accounts_healthy`, `accounts_at_risk`, `accounts_shelfware`, `accounts_inactive`, `accounts_ramping`
   - `expansion_opportunities` = count of `expansion_flag = TRUE`
   - `arr_at_risk` = SUM of `arr_at_risk`
3. Add `region_rank` and `org_rank` window functions for leaderboard

---

## 4. as_of_date Parameter

All pipeline steps accept an `as_of_date` parameter (default: `CURRENT_DATE()`).

**Why this matters:**
- The synthetic dataset covers Jan 2024 → today. Run with `--as-of-date 2025-06-30` to simulate a mid-year snapshot.
- Enables point-in-time analysis and backtesting of the metric.
- `stg_active_contracts` uses `as_of_date` to determine which contracts are active.
- `carr_account` uses `as_of_date` to define the trailing 90-day window and new account threshold.

---

## 5. Technology Choices & Rationale

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| **Data warehouse** | BigQuery | Snowflake, Redshift | Free sandbox tier; serverless; strong Python client |
| **Pipeline style** | SQL (dbt-style) | PySpark, Pandas | Readable, auditable, portable to dbt in production |
| **Dashboard** | Streamlit + Plotly | Looker, Tableau, Metabase | Fastest iteration; Python-native; no BI license needed for prototype |
| **DQ framework** | Custom Python assertions | Great Expectations, dbt tests | Lower dependency overhead; same pattern ports to dbt tests |
| **Credit pricing model** | Option A (monthly bucket) | Annual pool, rollover | Clearest shelfware/overage signal; standard PANW contract structure |

---

## 6. File Structure

```
gtm/
├── data_generation/
│   ├── generate_data.py          # Phase 1: synthetic data + BQ upload
│   └── requirements.txt
├── specs/
│   ├── product_spec.md           # Metric definition, formula, comp design
│   └── technical_spec.md        # This file
├── pipeline_and_tests/
│   ├── sql/
│   │   ├── 01_stg_active_contracts.sql
│   │   ├── 02_stg_monthly_consumption.sql
│   │   ├── 03_carr_account.sql
│   │   └── 04_carr_rep_rollup.sql
│   ├── run_pipeline.py           # Executes all 4 SQL steps
│   └── dq_tests.py              # Automated data quality assertions
├── dashboard/
│   ├── app.py                    # Streamlit executive dashboard
│   └── requirements.txt
└── README.md
```

---

## 7. Running the Pipeline

```bash
# Authenticate
gcloud auth application-default login

# Run full pipeline (uses today as as_of_date)
python3 pipeline_and_tests/run_pipeline.py

# Run against synthetic 2024-2025 data
python3 pipeline_and_tests/run_pipeline.py --as-of-date 2025-06-30

# Run data quality tests
python3 pipeline_and_tests/dq_tests.py --as-of-date 2025-06-30

# Launch dashboard
streamlit run dashboard/app.py
```

---

## 8. v2 Roadmap

| Enhancement | Effort | Value |
|---|---|---|
| Port SQL to dbt | Medium | Version-controlled lineage, automated tests, docs site |
| ML churn prediction | High | Predict which At Risk accounts churn at renewal |
| Real-time updates via Pub/Sub | High | Move from daily batch to near-real-time cARR |
| Cohort-based multiplier calibration | Medium | Validate health tier thresholds against actual churn cohorts |
| Feature-depth weighting | Medium | Weight credits by product tier (base NGFW vs. advanced security add-ons) |
