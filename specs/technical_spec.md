## Project Brief

**Context & Scenario**

Our Go-To-Market (GTM) organization is transitioning from a traditional, upfront Annual Recurring Revenue (ARR) model to a hybrid Consumption-based business model. Sales leadership is currently debating how to appropriately measure success, incentivize the right behaviors, and compensate sales representatives in this new paradigm.

We need a new "North Star" metric for the GTM organization that balances initial contract bookings with sustained platform usage over a customer's lifecycle.

**Your Role:** You are the Principal PM leading this initiative. You need to define this metric, build a working prototype of the data pipeline to calculate it, ensure data quality, and prepare an executive presentation for the VP of Sales and the CFO to secure a final decision.

To complete this, you are expected to utilize a spec-driven AI development approach (using AI coding tools like Cursor or Claude Code, paired with Markdown specs) to go rapidly from concept to working prototype.

---

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
| `employee_id` | STRING | PK — UUID |
| `name` | STRING | |
| `region` | STRING | Northeast / Southeast / Midwest / West / International |
| `segment` | STRING | Enterprise / Mid-Market |

#### `accounts`
| Column | Type | Notes |
|---|---|---|
| `account_id` | STRING | PK — UUID |
| `company_name` | STRING | |
| `industry` | STRING | |
| `employee_id` | STRING | FK → sales_reps.employee_id (current account owner; may differ from signing owner after reassignment) |

#### `contracts`
| Column | Type | Notes |
|---|---|---|
| `contract_id` | STRING | PK — UUID |
| `account_id` | STRING | FK → accounts.account_id |
| `owner_id` | STRING | FK → sales_reps.employee_id — rep who owned the account at signing |
| `start_date` | DATE | |
| `end_date` | DATE | Inclusive: `start_date + contract_term_months - 1 day` (e.g. 2026-01-01 + 12mo → 2026-12-31) |
| `annual_commit_dollars` | INTEGER | ACV — annualized contract value |
| `included_monthly_compute_credits` | INTEGER | Monthly credit allowance (Option A: use-it-or-lose-it per month) |
| `contract_term_months` | INTEGER | 12 / 24 / 36 — Enterprise skews multi-year |
| `contract_type` | STRING | `base` / `expansion` / `renewal` / `additional` |

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

### Step 0 — `dim_dates`

**Purpose:** Build a calendar dimension table covering 2000-01-01 through 2030-12-31 used for date spine joins and fiscal calendar alignment.

**Logic:**
1. Generate one row per calendar day via `GENERATE_DATE_ARRAY`
2. Derive standard calendar fields: `date_id`, `day_of_week`, `is_weekend`, month/quarter start and end flags
3. Derive PANW fiscal calendar fields: `fiscal_year`, `fiscal_year_name`, `fiscal_month`, `fiscal_quarter`, `fiscal_year_quarter`
   - PANW fiscal year ends July 31; FY starts August 1
   - FQ1 = Aug–Oct, FQ2 = Nov–Jan, FQ3 = Feb–Apr, FQ4 = May–Jul
   - `fiscal_month` formula: `MOD(calendar_month + 4, 12) + 1` → August = 1, July = 12
4. Expose explicit calendar aliases: `calendar_year`, `calendar_quarter`, `calendar_year_quarter`

**Output:** 29 columns; one row per day. Used as a date spine by downstream queries.

---

### Step 1 — `stg_active_contracts`

**Purpose:** Resolve which contract(s) are active per account and produce a single canonical row.

**Logic:**
1. Filter contracts where `as_of_date BETWEEN start_date AND end_date`
2. Exclude malformed contracts where `end_date < start_date`
3. For accounts with multiple active contracts (mid-year expansions):
   - ARR = **SUM** of `annual_commit_dollars` across all active contracts
   - Monthly credits = **SUM** of `included_monthly_compute_credits` across all active contracts
   - Primary contract = earliest `start_date` (used for reference fields and comp attribution)
   - Set `has_expansion = TRUE`
4. Join to `accounts` to carry `employee_id`, `company_name`, `industry`

**Edge cases handled:**
- Mid-year expansions → both ARR and credits summed across all active contracts
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
1. Join `carr_account` to `sales_reps` on `employee_id`
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
│   ├── generate_data.py          # Synthetic data generation + BigQuery upload
│   ├── verify_edge_cases.sql     # Ad-hoc BQ queries to validate edge case distributions
│   └── requirements.txt
├── specs/
│   ├── product_spec.md           # Metric definition, formula, comp design
│   └── technical_spec.md        # This file
├── pipeline_and_tests/
│   ├── sql/
│   │   ├── 00_dim_dates.sql             # Calendar + PANW fiscal dimension (2000–2030)
│   │   ├── 01_stg_active_contracts.sql  # Resolve active contracts per account
│   │   ├── 02_stg_monthly_consumption.sql
│   │   ├── 03_carr_account.sql
│   │   └── 04_carr_rep_rollup.sql
│   ├── run_pipeline.py           # Executes all 5 SQL steps (steps 0–4)
│   └── dq_tests.py              # Automated data quality assertions (11 tests)
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

# (Re-)generate synthetic data and upload to BigQuery
python3 data_generation/generate_data.py --upload

# Run full 5-step pipeline (uses today as as_of_date)
python3 pipeline_and_tests/run_pipeline.py

# Run against a specific historical snapshot
python3 pipeline_and_tests/run_pipeline.py --as-of-date 2025-06-30

# Run only a single step (0 = dim_dates, 1 = stg_active_contracts, …)
python3 pipeline_and_tests/run_pipeline.py --step 3

# Dry-run: print SQL without executing
python3 pipeline_and_tests/run_pipeline.py --dry-run

# Run data quality tests (11 assertions, ERROR / WARNING / INFO)
python3 pipeline_and_tests/dq_tests.py --as-of-date 2025-06-30

# DQ tests — fail CI on any ERROR
python3 pipeline_and_tests/dq_tests.py --fail-on-error --output results.json

# Launch dashboard
streamlit run dashboard/app.py
```

---

## 8. Dashboard Implementation

### Stack
- **Frontend:** Streamlit (Python) — single-file app (`dashboard/app.py`)
- **Charting:** Plotly Express + Plotly Graph Objects
- **Data:** BigQuery Python client (`google-cloud-bigquery`); queries cached with `@st.cache_data(ttl=300)`
- **Auth:** Google Application Default Credentials (ADC) — `gcloud auth application-default login`

### Data Flow

```
BigQuery                    Streamlit App
──────────────────────────────────────────────────────
gtm.carr_rep_rollup    →    load_rep_rollup(as_of_date)   → sidebar rep list, all rep-level charts
gtm.carr_account       →    load_accounts(as_of_date,      → account scatter, account detail table
                                region, employee_id)
gtm.carr_rep_rollup    →    load_available_dates()         → as-of-date selector in sidebar
raw.sales_reps         →    joined inside load_accounts()  → rep_name, region, segment on account rows
```

### Caching Strategy
- `load_rep_rollup` and `load_accounts`: 5-minute TTL — balances freshness with BQ query cost
- `load_available_dates`: 10-minute TTL — changes only when pipeline reruns
- `get_bq_client`: `@st.cache_resource` — single client instance per session (no reconnect overhead)

### Fallback Behavior
If `carr_rep_rollup` has no rows for the requested `as_of_date`, the app falls back to the latest available data (`ORDER BY calculated_at DESC`). `load_accounts` similarly falls back to a full table scan with in-memory filtering if the date-filtered query returns nothing.

---

## 9. Downstream System Integrations

### 9.1 Integration Architecture

```
BigQuery (gtm dataset)
        │
        ├─── Nightly export ──► Salesforce CRM        (Account health + expansion signals)
        ├─── Monthly export ──► Compensation platform  (Rep attainment for quota/commission)
        ├─── Daily export ───► CS platform             (Health scores + playbook triggers)
        └─── On-demand ──────► BI layer                (Board reporting, cohort analysis)
```

All exports read from the two output tables: `carr_account` (account-level) and `carr_rep_rollup` (rep-level).

---

### 9.2 Salesforce CRM

**Sync:** Nightly batch via BigQuery → Salesforce REST API (or Salesforce Connect external object)
**Source table:** `gtm.carr_account`

| BQ Field | Salesforce Object | Salesforce Field | Notes |
|---|---|---|---|
| `health_tier` | Account | `Health_Tier__c` | Picklist: Expansion / Healthy / At Risk / Shelfware / Inactive / Ramping |
| `carr_attainment_rate` | Account | `cARR_Attainment__c` | Number (%) — drives renewal forecast category |
| `arr_at_risk` | Account | `ARR_at_Risk__c` | Currency — adjusts renewal opportunity amount |
| `expansion_flag = TRUE` | Opportunity (auto-create) | Stage = `Expansion Identified` | Creates new opp on Account if none exists in stage |
| `is_spike_drop = TRUE` | Account | `Spike_Drop_Flag__c` | Checkbox — triggers CS save plan task |
| `employee_id` | Account | `Owner` (current) | Routes to current account owner for quota |
| `signing_owner_id` | Account | `Signing_Owner__c` | Preserved for comp attribution on original deal |

---

### 9.3 Compensation Platform (e.g., Xactly, CaptivateIQ)

**Sync:** Monthly close via BigQuery scheduled export → CSV/SFTP or direct API
**Source table:** `gtm.carr_rep_rollup`

| BQ Field | Comp Use |
|---|---|
| `total_carr` | Farmer quota attainment numerator |
| `carr_attainment_rate` | Accelerator / decelerator tier lookup |
| `total_arr` | Quota denominator for attainment % |
| `expansion_arr_pipeline` | Expansion SPIF eligibility flag |

**Activation bonus** (requires `gtm.carr_account`):
```sql
-- Accounts that hit ≥80% consumption within 90 days of contract start
SELECT employee_id, account_id, company_name, carr_attainment_rate
FROM gtm.carr_account
WHERE is_new_account = FALSE                             -- just aged out of ramping
  AND contract_start_date >= DATE_SUB(as_of_date, INTERVAL 180 DAY)
  AND trailing_90d_avg_rate >= 0.80
```

---

### 9.4 Customer Success Platform (e.g., Gainsight, Totango)

**Sync:** Daily via BigQuery → CS platform API
**Source table:** `gtm.carr_account`

| Health Tier | CS Score Range | Automated Action |
|---|---|---|
| Expansion | 90–100 | Flag for AE expansion handoff |
| Healthy | 70–89 | Maintain check-in cadence |
| At Risk | 40–69 | Open CS escalation playbook; 30-day SLA |
| Shelfware | 20–39 | Executive sponsor outreach playbook |
| Inactive | 0–19 | Immediate save plan; escalate to VP CS |
| Ramping | N/A | Onboarding playbook; 90-day activation tracking |

Key field mapping:
- `trailing_90d_avg_rate` → CS health score (normalized 0–100)
- `months_of_data` → data confidence indicator (low if < 2)
- `zero_usage_months` → trigger for proactive outreach if ≥ 2 consecutive

---

### 9.5 BI / Board Reporting (e.g., Tableau, Looker)

**Source tables:** `gtm.carr_rep_rollup`, `gtm.carr_account`, `gtm.dim_dates`

Key reports enabled by the current data model:

| Report | Tables Used | Key Fields |
|---|---|---|
| Board NRR forecast | `carr_rep_rollup` | `total_carr / total_arr` org-wide as NRR leading indicator |
| Renewal risk register | `carr_account` | `arr_at_risk`, `contract_end_date`, `health_tier` |
| Expansion pipeline | `carr_account` | `expansion_flag`, `annual_commit_dollars`, `rep_name` |
| Cohort churn analysis | `carr_account` + `dim_dates` | Attainment by `fiscal_year_quarter` of contract start |
| QBR regional pack | `carr_rep_rollup` | `region`, `total_arr`, `total_carr`, `accounts_at_risk` |

---

## 10. v2 Roadmap

| Enhancement | Effort | Value |
|---|---|---|
| Port SQL to dbt | Medium | Version-controlled lineage, automated tests, docs site |
| ML churn prediction | High | Predict which At Risk accounts churn at renewal |
| Real-time updates via Pub/Sub | High | Move from daily batch to near-real-time cARR |
| Cohort-based multiplier calibration | Medium | Validate health tier thresholds against actual churn cohorts |
| Feature-depth weighting | Medium | Weight credits by product tier (base NGFW vs. advanced security add-ons) |
