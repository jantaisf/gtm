## Project Brief

**Context & Scenario**

Our Go-To-Market (GTM) organization is transitioning from a traditional, upfront Annual Recurring Revenue (ARR) model to a hybrid Consumption-based business model. Sales leadership is currently debating how to appropriately measure success, incentivize the right behaviors, and compensate sales representatives in this new paradigm.

We need a new "North Star" metric for the GTM organization that balances initial contract bookings with sustained platform usage over a customer's lifecycle.

**Your Role:** You are the Principal PM leading this initiative. You need to define this metric, build a working prototype of the data pipeline to calculate it, ensure data quality, and prepare an executive presentation for the VP of Sales and the CFO to secure a final decision.

To complete this, you are expected to utilize a spec-driven AI development approach (using AI coding tools like Cursor or Claude Code, paired with Markdown specs) to go rapidly from concept to working prototype.

---

# Technical Spec: Consumption ACV Data Pipeline
## Prisma Cloud Consumption ACV — End-to-End Architecture

**Version:** 1.0
**Owner:** Principal PM, Analytics & AI
**Depends on:** product_spec.md v1.0
**Status:** Implementation-ready
**Last Updated:** May 2026

---

## 1. Architecture Overview

The pipeline follows a **medallion architecture** (Bronze → Silver → Gold) with a **star schema** at the Gold layer. A semantic layer sits above Gold, joining dimension and fact tables into denormalized views — so downstream consumers (dashboard, BI tools, Salesforce) see a single flat table, while the underlying model retains the scalability and flexibility of a proper star schema.

```
┌──────────────────────────────────────────────────────────────┐
│  BRONZE  ·  raw source tables, as-landed, no transforms       │
│                                                              │
│  bronze.sales_reps    bronze.accounts                        │
│  bronze.contracts     bronze.daily_usage_logs                │
└───────────────────────────┬──────────────────────────────────┘
                            │ SQL: clean, conform, resolve edge cases
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  SILVER  ·  cleaned, conformed, edge cases resolved           │
│                                                              │
│  silver.active_contracts   silver.monthly_consumption        │
└───────────────────────────┬──────────────────────────────────┘
                            │ SQL: build dimensions + calculate metrics
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  GOLD  ·  star schema — dimension tables + fact table         │
│                                                              │
│  gold.dim_dates       gold.dim_accounts                      │
│  gold.dim_reps        gold.dim_contracts                     │
│                                                              │
│  gold.fact_cacv_snapshot  (account × as_of_date grain)       │
└───────────────────────────┬──────────────────────────────────┘
                            │ semantic layer: JOIN dims + fact into
                            │ denormalized views for each consumer
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  SEMANTIC LAYER  ·  denormalized — one wide table per use case│
│                                                              │
│  gold.vw_rep_portfolio   (dashboard + comp platform)         │
│  gold.vw_account_detail  (CS platform + Salesforce)          │
└───────────────────────────┬──────────────────────────────────┘
                            │ Python BigQuery client
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  CONSUMERS                                                   │
│  Streamlit Dashboard · Salesforce · Comp Platform · BI layer │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. BigQuery Schema

> **Schema naming note:** The schema names `bronze`, `silver`, and `gold` are used throughout this spec to represent the three medallion architecture layers — raw ingestion, cleaned/conformed, and business-ready metrics respectively. These are conceptual labels for a prototype. PANW's actual BigQuery dataset names (e.g. `raw`, `staging`, `analytics`, or environment-prefixed variants like `prod_gtm`) would be substituted at implementation time in line with PANW's existing data platform naming conventions.

### Bronze — Raw Source Tables

As-landed data. No transforms applied. Pipeline reads from here; nothing writes back.

#### `bronze.sales_reps`
| Column | Type | Notes |
|---|---|---|
| `employee_id` | STRING | Primary Key — UUID |
| `name` | STRING | |
| `region` | STRING | Northeast / Southeast / Midwest / West / International |
| `segment` | STRING | Enterprise / Mid-Market |

#### `bronze.accounts`
| Column | Type | Notes |
|---|---|---|
| `account_id` | STRING | Primary Key — UUID |
| `company_name` | STRING | |
| `industry` | STRING | |
| `employee_id` | STRING | Foreign Key → dim_reps.employee_id (current owner; may differ from signing owner after reassignment) |

#### `bronze.contracts`
| Column | Type | Notes |
|---|---|---|
| `contract_id` | STRING | Primary Key — UUID |
| `account_id` | STRING | Foreign Key → bronze.accounts.account_id |
| `owner_id` | STRING | Foreign Key → dim_reps.employee_id — rep who owned the account at signing |
| `start_date` | DATE | |
| `end_date` | DATE | Inclusive: `start_date + contract_term_months - 1 day` (e.g. 2026-01-01 + 12mo → 2026-12-31) |
| `annual_commit_dollars` | INTEGER | ACV — annualized contract value |
| `included_monthly_compute_credits` | INTEGER | Monthly credit allowance (use-it-or-lose-it per month) |
| `contract_term_months` | INTEGER | 12 / 24 / 36 — Enterprise skews multi-year |
| `contract_type` | STRING | `base` / `expansion` / `renewal` / `additional` |

#### `bronze.daily_usage_logs`
| Column | Type | Notes |
|---|---|---|
| `log_id` | STRING | Primary Key — format `LOG-NNNNNNN` |
| `account_id` | STRING | May reference non-existent accounts (orphan edge case) |
| `date` | DATE | May fall outside contract window (rogue usage edge case) |
| `compute_credits_consumed` | FLOAT | Daily credit burn |

---

### Silver — Cleaned and Conformed Tables

Edge cases resolved. One canonical row per grain. No business metrics yet.

| Table | Grain | What it does |
|---|---|---|
| `silver.active_contracts` | One row per account | Resolves overlapping contracts; sums credits for mid-year expansions |
| `silver.monthly_consumption` | One row per account × month | Aggregates daily usage; applies orphan + rogue usage guards; zero-fills months with no logs |

---

### Gold — Dimension Tables

Descriptive attributes. Stable, slowly changing. Written once per pipeline run.

#### `gold.dim_dates`
Calendar + PANW fiscal calendar spine, 2000-01-01 → 2030-12-31. See Step 0 for column list.

#### `gold.dim_accounts`
| Column | Type | Notes |
|---|---|---|
| `account_id` | STRING | Primary Key |
| `company_name` | STRING | |
| `industry` | STRING | |

#### `gold.dim_reps`
| Column | Type | Notes |
|---|---|---|
| `employee_id` | STRING | Primary Key |
| `name` | STRING | |
| `region` | STRING | |
| `segment` | STRING | Enterprise / Mid-Market |

#### `gold.dim_contracts`
| Column | Type | Notes |
|---|---|---|
| `contract_id` | STRING | Primary Key |
| `account_id` | STRING | Foreign Key → dim_accounts |
| `signing_owner_id` | STRING | Foreign Key → dim_reps — rep at signing; preserved for comp attribution after reassignment |
| `start_date` | DATE | |
| `end_date` | DATE | |
| `annual_commit_dollars` | INTEGER | |
| `included_monthly_compute_credits` | INTEGER | |
| `contract_term_months` | INTEGER | |
| `contract_type` | STRING | |

---

### Gold — Fact Table

Measurable events and metrics at the lowest useful grain.

#### `gold.fact_cacv_snapshot`
**Grain:** one row per `account_id × as_of_date`. This is the single source of truth for all Consumption ACV metrics.

| Column | Type | Notes |
|---|---|---|
| `account_id` | STRING | Foreign Key → dim_accounts |
| `employee_id` | STRING | Foreign Key → dim_reps — current account owner |
| `contract_id` | STRING | Foreign Key → dim_contracts — primary active contract |
| `as_of_date` | DATE | Foreign Key → dim_dates |
| `annual_commit_dollars` | INTEGER | Degenerate dimension — ACV at snapshot time |
| `trailing_7d_avg_rate` | FLOAT | Consumption rate — 7-day trailing avg (last 7 days of daily usage ÷ daily credit allowance); weekly monitoring only |
| `trailing_30d_avg_rate` | FLOAT | Consumption rate — 30-day trailing avg (last 30 days of daily usage ÷ monthly credit allowance); monthly monitoring only |
| `trailing_90d_avg_rate` | FLOAT | Consumption rate — 90-day trailing avg (last 3 complete calendar months); **comp basis** |
| `cacv` | FLOAT | `ACV × trailing_90d_avg_rate`; NULL if ramping. Always uses 90d rate — see §2.2.1 |
| `expansion_signal_acv` | FLOAT | Consumption Overage: `MAX(Consumption ACV − ACV, 0)`; NULL if ramping |
| `acv_at_risk` | FLOAT | `ACV − Consumption ACV`; NULL if ramping |
| `health_tier` | STRING | Expansion / Healthy / At Risk / Shelfware / Inactive / Ramping |
| `is_new_account` | BOOLEAN | Contract start within last 90 days |
| `expansion_flag` | BOOLEAN | 2+ consecutive months >120% consumption |
| `is_spike_drop` | BOOLEAN | High historical peak, now near-zero |
| `has_expansion` | BOOLEAN | Multiple active contracts (mid-year expansion) |
| `months_of_data` | INTEGER | Months of consumption history available |
| `calculated_at` | TIMESTAMP | Pipeline run timestamp |

---

### Gold — Semantic Layer Views

The star schema is designed to be **queried through views, not directly**. Each view joins `fact_cacv_snapshot` to the relevant dimensions and pre-selects the columns needed by a specific consumer. To downstream users — the dashboard, Salesforce, the comp platform, BI tools — the data appears as a single denormalized table with no joins required.

This pattern provides:
- **Storage efficiency** — dimension attributes (rep name, region, company name) stored once in dim tables, not repeated in every fact row
- **Slowly Changing Dimension support** — if a rep's territory is reassigned or an account is renamed, the dim table is updated once; historical fact rows are unaffected, preserving audit history
- **BI tool compatibility** — Looker LookML, Tableau, and dbt all model natively against star schemas; the views expose a flat surface while the underlying joins remain maintainable
- **Blast-radius isolation** — adding a column to `dim_reps` (e.g., `hire_date`, `manager_id`) requires no changes to `fact_cacv_snapshot`
- **dbt-ready lineage** — `dim_*` and `fact_*` are first-class dbt model types; the view layer maps directly to dbt exposures
- **Aggregation correctness** — grain is explicit in the fact table; rollup views aggregate from a clean grain rather than pre-aggregated rows, eliminating double-counting risk

| View | Consumer | What it flattens |
|---|---|---|
| `gold.vw_rep_portfolio` | Dashboard Tab 2–3, comp platform | `fact_cacv_snapshot` + `dim_reps` aggregated to rep level |
| `gold.vw_account_detail` | Dashboard Tab 4, CS platform, Salesforce | `fact_cacv_snapshot` + `dim_accounts` + `dim_reps` + `dim_contracts` |

---

## 3. History Tracking

The pipeline captures three distinct types of history, each serving a different purpose. These are not interchangeable — collapsing them into a single pattern produces a model that is weak at all three jobs.

| History type | Question it answers | Pattern |
|---|---|---|
| **Point-in-time accuracy** | "What was the state at time X?" | SCD Type 2 on dimension tables |
| **Comp auditability** | "Why was rep X paid Y in month M?" | Pipeline run log + corrections audit table |
| **Source data changes** | "When and why did the underlying data change?" | Append-only change log tables in Bronze |

---

### 3.1 Slowly Changing Dimensions (Point-in-Time Accuracy)

**v1 default:** All dimension tables use **SCD Type 1** (overwrite on each pipeline run). Territory reassignments, account renames, and contract amendments take effect immediately and replace the prior value. Historical fact rows still join correctly because `fact_cacv_snapshot` is a snapshot table — but dimension attributes (rep name, region, segment) will reflect the *current* state, not the state at time of measurement.

**v1 limitation:** Any cohort analysis asking "what region drove the best activation rate in FY25?" will silently use today's territory mapping, not the territory at time of measurement. This is acceptable for a v1 operating dashboard but must be resolved before BI or board-level cohort reporting is expected to be reliable.

**v2 upgrade — SCD Type 2 fields** (add to `dim_reps` and `dim_contracts`):

| Field | Type | Notes |
|---|---|---|
| `surrogate_key` | INTEGER | Synthetic Primary Key — replaces natural key as Foreign Key in `fact_cacv_snapshot` |
| `valid_from` | DATE | Date this version became active |
| `valid_to` | DATE | NULL = current row; set to day before next version on update |
| `is_current` | BOOLEAN | Partition filter shorthand — `WHERE is_current = TRUE` returns latest |
| `dw_created_at` | TIMESTAMP | When this row was written to the warehouse |
| `change_reason` | STRING | `territory_reassignment` / `contract_amendment` / `acquisition` / `name_change` |

When Type 2 is active, `fact_cacv_snapshot` stores `surrogate_key` (not the natural key) as its Foreign Key, so each fact row is permanently bound to the dimension version that was current when the metric was calculated.

**Priority by table:**
- `dim_reps` — highest value; territory reassignments are frequent and directly affect regional reporting accuracy
- `dim_contracts` — high value; contract amendments change the ACV denominator retroactively
- `dim_accounts` — lower priority; account renames are uncommon

---

### 3.2 Pipeline Run Log and Corrections (Comp Auditability)

Any Consumption ACV figure flowing to a compensation platform must be traceable to the exact pipeline run that produced it, with an immutable record of any retroactive corrections. This is a finance requirement, not an analytics nice-to-have (see product_spec.md §2.1 and §9).

**New table: `pipeline_run_log`** — one row per pipeline execution:

| Field | Type | Notes |
|---|---|---|
| `run_id` | STRING | Primary Key — UUID |
| `as_of_date` | DATE | Snapshot date this run produced |
| `run_timestamp` | TIMESTAMP | Pipeline start time |
| `pipeline_version` | STRING | Git SHA or semantic version tag |
| `triggered_by` | STRING | `scheduled` / `manual` / `correction` |
| `status` | STRING | `running` / `success` / `failed` |
| `rows_written_fact` | INTEGER | Rows upserted to `fact_cacv_snapshot` |
| `rows_written_dims` | INTEGER | Rows upserted across all dim tables |
| `is_correction` | BOOLEAN | TRUE if this run overwrites a prior `as_of_date` snapshot |
| `correction_note` | STRING | Required when `is_correction = TRUE` |
| `correction_approved_by` | STRING | VP of Finance or CFO sign-off; required before comp platform sync |

**New table: `fact_cacv_corrections`** — delta record for every retroactive Consumption ACV change after commissions have been paid:

| Field | Type | Notes |
|---|---|---|
| `correction_id` | STRING | Primary Key — UUID |
| `pipeline_run_id` | STRING | Foreign Key → `pipeline_run_log.run_id` |
| `account_id` | STRING | |
| `as_of_date` | DATE | Snapshot period being corrected |
| `corrected_at` | TIMESTAMP | |
| `corrected_by` | STRING | |
| `old_cacv` | FLOAT | Value before correction |
| `new_cacv` | FLOAT | Value after correction |
| `old_health_tier` | STRING | |
| `new_health_tier` | STRING | |
| `correction_reason` | STRING | Required — free text |
| `comp_period_affected` | STRING | e.g. `FY26-Q1` — which pay period is impacted |
| `clawback_triggered` | BOOLEAN | |
| `clawback_amount` | FLOAT | NULL if clawback not triggered |
| `approved_by` | STRING | CFO sign-off required for corrections that affect already-paid commissions |

**Changes to `fact_cacv_snapshot`** — add two fields:

| Field | Type | Notes |
|---|---|---|
| `pipeline_run_id` | STRING | Foreign Key → `pipeline_run_log.run_id` — links every metric value to its source run |
| `is_correction` | BOOLEAN | TRUE if this row replaced a prior calculation for the same `account_id × as_of_date` |

This makes the full audit chain traceable: commission record → `vw_rep_portfolio` row → `fact_cacv_snapshot` row → `pipeline_run_log` entry → either a scheduled run or an approved correction.

---

### 3.3 Source Data Change Logs (Bronze Layer)

Two Bronze tables carry changes that directly affect Consumption ACV calculations and comp attribution. Without change logs for these, there is no way to distinguish "the metric moved because consumption changed" from "the metric moved because someone edited the source data."

**New table: `bronze.account_ownership_history`** — every rep-to-account assignment from initial signing through all subsequent reassignments:

| Field | Type | Notes |
|---|---|---|
| `ownership_id` | STRING | Primary Key — UUID |
| `account_id` | STRING | Foreign Key → `bronze.accounts` |
| `employee_id` | STRING | Foreign Key → `bronze.sales_reps` |
| `effective_from` | DATE | Start of this ownership period |
| `effective_to` | DATE | NULL = current owner |
| `change_type` | STRING | `initial_assignment` / `territory_rebalance` / `rep_departure` / `acquisition` |
| `source` | STRING | `salesforce_sync` / `manual` / `pipeline` |
| `created_at` | TIMESTAMP | |
| `created_by` | STRING | |
| `notes` | STRING | Optional — context for the change |

This table is what makes the `signing_owner_id` / current `employee_id` split on `dim_contracts` fully defensible at scale. The original signing owner is captured at contract creation; this table records every ownership change after that.

> **Data collection note:** This table must be populated from day one. Ownership history that isn't captured at time of reassignment cannot be reconstructed retroactively from the warehouse — it lives only in Salesforce's audit log or HR records.

**New table: `bronze.contract_amendments`** — every change to ACV, credit allowance, or contract term after the original contract is written:

| Field | Type | Notes |
|---|---|---|
| `amendment_id` | STRING | Primary Key — UUID |
| `contract_id` | STRING | Foreign Key → `bronze.contracts` |
| `amendment_type` | STRING | `acv_change` / `term_extension` / `credit_change` / `early_termination` |
| `field_changed` | STRING | `annual_commit_dollars` / `end_date` / `included_monthly_compute_credits` |
| `old_value` | STRING | Stored as STRING to handle mixed types; cast at query time |
| `new_value` | STRING | |
| `effective_date` | DATE | When the amendment takes effect on the contract (not when it was signed) |
| `signed_date` | DATE | When the amendment paperwork was executed |
| `created_at` | TIMESTAMP | |
| `created_by` | STRING | |
| `approved_by` | STRING | Required for `acv_change` amendments — affects the Consumption ACV denominator and comp calculations |

An ACV amendment changes the Consumption ACV denominator going forward. Without this table, a drop in attainment after a mid-year downsell looks identical to a drop caused by the customer reducing consumption — two situations that require completely different responses.

---

### 3.4 Priority and Phasing

| Addition | Priority | Phase | Rationale |
|---|---|---|---|
| `pipeline_run_log` + `pipeline_run_id` on `fact_cacv_snapshot` | P0 | v1 | CFO requirement — required before comp platform integration |
| `fact_cacv_corrections` | P0 | v1 | Immutable delta record for retroactive corrections and clawback evaluation |
| `bronze.account_ownership_history` | P1 | v1 | Must start day one — not reconstructable retroactively from the warehouse |
| `bronze.contract_amendments` | P1 | v1 | ACV and term changes affect the Consumption ACV denominator; needed to separate metric movement from data edits |
| SCD Type 2 on `dim_reps` | P2 | v2 | Required for accurate regional cohort analysis; acceptable to defer if v1 scope is point-in-time |
| SCD Type 2 on `dim_contracts` | P2 | v2 | Amendment history is surfaced via `contract_amendments` log for v1 |
| SCD Type 2 on `dim_accounts` | P3 | v2 | Account renames are uncommon; lower risk than rep or contract changes |

---

## 4. Pipeline Step-by-Step Logic

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

### Step 1 — `silver.active_contracts`

**Purpose:** Resolve which contract(s) are active per account and produce a single canonical row.

**Reads from:** `bronze.contracts`, `bronze.accounts`

**Logic:**
1. Filter contracts where `as_of_date BETWEEN start_date AND end_date`
2. Exclude malformed contracts where `end_date < start_date`
3. For accounts with multiple active contracts (mid-year expansions):
   - ACV = **SUM** of `annual_commit_dollars` across all active contracts
   - Monthly credits = **SUM** of `included_monthly_compute_credits` across all active contracts
   - Primary contract = earliest `start_date` (used for reference fields and comp attribution)
   - Set `has_expansion = TRUE`
4. Join to `bronze.accounts` to carry `employee_id`, `company_name`, `industry`

**Edge cases handled:**
- Mid-year expansions → both ACV and credits summed across all active contracts
- Malformed contracts → excluded via `end_date >= start_date` guard

---

### Step 2 — `silver.monthly_consumption`

**Purpose:** Aggregate daily usage to monthly totals per account, with edge case filtering.

**Reads from:** `bronze.daily_usage_logs`, `bronze.accounts`, `bronze.contracts`

**Logic:**
1. **Orphan guard:** `INNER JOIN bronze.accounts` — logs with unknown `account_id` are excluded
2. **Rogue usage guard:** `JOIN bronze.contracts ON date BETWEEN start_date AND end_date` — out-of-window logs excluded
3. Aggregate: `SUM(compute_credits_consumed)` grouped by `account_id`, `DATE_TRUNC(date, MONTH)`
4. **Shelfware guard:** `LEFT JOIN` from contract months — accounts with zero logs get `credits_consumed = 0`
5. Compute `consumption_rate = credits_consumed / included_monthly_compute_credits` (cap at 2.0 to limit outlier distortion)
6. Flag `is_zero_usage_month = TRUE` for months with no consumption

**Edge cases handled:**
- Orphaned usage → excluded via INNER JOIN
- Out-of-contract usage → excluded via date-range JOIN
- Shelfware (zero logs) → LEFT JOIN produces 0 consumption rate

---

### Step 3 — `gold.dim_accounts`, `gold.dim_reps`, `gold.dim_contracts`

**Purpose:** Populate dimension tables from Bronze sources. Run before the fact table step.

**Logic:**
- `dim_accounts` — distinct `account_id`, `company_name`, `industry` from `bronze.accounts`
- `dim_reps` — distinct `employee_id`, `name`, `region`, `segment` from `bronze.sales_reps`
- `dim_contracts` — full contract record from `bronze.contracts`, with `signing_owner_id` preserved separately from the current `employee_id` on the account

> **SCD note (v1):** Dimensions are replaced on each pipeline run (Type 1 SCD — overwrite). Territory reassignments and account renames take effect immediately. v2 can introduce Type 2 SCD (add `valid_from` / `valid_to`) to preserve history if audit requirements demand it.

---

### Step 4 — `gold.fact_cacv_snapshot`

**Purpose:** Compute account-level Consumption ACV (using 90-day rate for comp) and all three monitoring rates, then write the fact table.

**Reads from:** `silver.active_contracts`, `silver.monthly_consumption`, `gold.dim_dates`, `bronze.daily_usage_logs`

**Logic:**

1. **7-day rate** — from raw daily usage logs:
   ```sql
   trailing_7d_avg_rate =
     SUM(daily_credits_consumed, last 7 days) /
     (7.0 / 30.0 * included_monthly_compute_credits)
   ```
   Reads `bronze.daily_usage_logs` directly; not aggregated through `silver.monthly_consumption`.

2. **30-day rate** — from raw daily usage logs:
   ```sql
   trailing_30d_avg_rate =
     SUM(daily_credits_consumed, last 30 days) / included_monthly_compute_credits
   ```

3. **90-day rate** — from pre-aggregated monthly data (existing logic):
   ```sql
   trailing_90d_avg_rate = AVG(monthly_consumption_rate, last 3 complete calendar months)
   ```
   Uses `silver.monthly_consumption` — the same edge-case-guarded aggregation as before. This is the only rate used to compute `cacv` and health tiers (see product_spec.md §2.2.1).

4. Apply health tier classification using `trailing_90d_avg_rate` (see product_spec.md §5).
5. Flag new accounts: `is_new_account = TRUE` if `contract_start_date >= as_of_date - 90 days`
6. Compute Consumption ACV — **always uses 90-day rate**:
   ```sql
   cacv = CASE
     WHEN is_new_account THEN NULL
     ELSE ROUND(annual_commit_dollars * trailing_90d_avg_rate, 2)
   END

   -- Consumption Overage
   expansion_signal_acv = CASE
     WHEN is_new_account THEN NULL
     ELSE ROUND(GREATEST(
           annual_commit_dollars * trailing_90d_avg_rate - annual_commit_dollars,
           0), 2)
   END
   ```
   Over-consumption above the contracted commit is reported separately as Consumption Overage (`expansion_signal_acv`). `cacv` and `expansion_signal_acv` use `trailing_90d_avg_rate` exclusively — comp integrity requires this.

7. Compute `acv_at_risk = annual_commit_dollars - cacv`
8. Flag `expansion_flag = TRUE` if `overage_months >= 2`
9. Flag `is_spike_drop = TRUE` if `max_monthly_rate > 2.0 AND trailing_90d_avg_rate < 0.05`

**Edge cases handled:**
- Spike & Drop → trailing 90-day window smooths spike once it ages out; 7d/30d rates will reflect the drop immediately (useful early-warning signal)
- New accounts → excluded from Consumption ACV with `is_new_account` flag; 7d/30d rates still populated for activation monitoring
- Consistent overages → `expansion_flag` surfaced; Consumption Overage reported in `expansion_signal_acv`

> **Dashboard note:** The 7-day and 30-day rates are exposed as monitoring columns in `vw_account_detail`. The dashboard rate window selector switches which column is displayed for consumption rate fields — Consumption ACV values never change regardless of the selected window.

---

### Step 5 — `gold.vw_rep_portfolio`, `gold.vw_account_detail`

**Purpose:** Build semantic layer views that join `fact_cacv_snapshot` to dimension tables, presenting a denormalized surface to all downstream consumers.

**`vw_rep_portfolio`** — aggregates `fact_cacv_snapshot` to rep level, joining `dim_reps`:
- `total_acv`, `total_cacv`, `cacv_attainment_rate`
- Health tier account counts: `accounts_expansion`, `accounts_healthy`, `accounts_at_risk`, `accounts_shelfware`, `accounts_inactive`, `accounts_ramping`
- `expansion_opportunities`, `total_acv_at_risk`, `total_expansion_signal_acv` (Consumption Overage)
- `region_rank` and `org_rank` window functions for leaderboard
- Rep name, region, segment from `dim_reps`

**`vw_account_detail`** — one row per account, joining all four dim tables:
- All `fact_cacv_snapshot` metric columns, including all three rate columns: `trailing_7d_avg_rate`, `trailing_30d_avg_rate`, `trailing_90d_avg_rate`
- Account name, industry from `dim_accounts`
- Rep name, region, segment from `dim_reps`
- Contract term, type, start/end dates from `dim_contracts`

---

## 5. Metric Correctness Test Cases

These scenarios define the expected Consumption ACV output for given inputs. Use them as regression tests during refactors — if Consumption ACV changes unexpectedly on any of these, something broke.

| Scenario | ACV | M-3 Rate | M-2 Rate | M-1 Rate | Trailing Avg | Expected Consumption ACV | Expected Consumption Overage |
|---|---|---|---|---|---|---|---|
| Healthy steady-state | $200K | 0.90 | 0.94 | 0.91 | 0.917 | $183,400 | $0 |
| Shelfware | $300K | 0.05 | 0.03 | 0.02 | 0.033 | $9,900 | $0 |
| Inactive | $150K | 0.00 | 0.00 | 0.01 | 0.003 | $450 | $0 |
| Consistent overage (uncapped) | $80K | 1.35 | 1.40 | 1.42 | 1.390 | **$80,000** (capped) | **$31,200** |
| At risk — declining | $500K | 0.75 | 0.68 | 0.61 | 0.680 | $340,000 | $0 |
| Spike & Drop (spike aged out) | $120K | 0.04 | 0.03 | 0.02 | 0.030 | $3,600 | $0 |
| New account (ramping) | $250K | — | — | — | — | **NULL** | **NULL** |
| Mid-year expansion (2 active contracts, combined ARR) | $180K | 0.88 | 0.91 | 0.85 | 0.880 | $158,400 | $0 |
| Just at attainment target | $400K | 0.84 | 0.87 | 0.84 | 0.850 | $340,000 | $0 |

**Key assertions to encode as pipeline tests:**
- `cacv` is never NULL for a non-ramping account with ≥ 1 month of data
- `cacv <= annual_commit_dollars` always (cap holds)
- `expansion_signal_acv >= 0` always (Consumption Overage is never negative)
- `cacv + expansion_signal_acv = ROUND(annual_commit_dollars × trailing_90d_avg_rate, 2)` for all non-NULL rows
- `acv_at_risk = annual_commit_dollars - cacv` for all non-NULL rows

---

## 6. as_of_date Parameter

All pipeline steps accept an `as_of_date` parameter (default: `CURRENT_DATE()`).

**Why this matters:**
- The synthetic dataset covers Jan 2024 → today. Run with `--as-of-date 2025-06-30` to simulate a mid-year snapshot.
- Enables point-in-time analysis and backtesting of the metric.
- `stg_active_contracts` uses `as_of_date` to determine which contracts are active.
- `cacv_account` uses `as_of_date` to define the trailing 90-day window and new account threshold.

---

## 7. Technology Choices & Rationale

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| **Data warehouse** | BigQuery | Snowflake, Redshift | Free sandbox tier; serverless; strong Python client |
| **Pipeline style** | SQL (dbt-style) | PySpark, Pandas | Readable, auditable, portable to dbt in production |
| **Dashboard** | Streamlit + Plotly | Looker, Tableau, Metabase | Fastest iteration; Python-native; no BI license needed for prototype |
| **DQ framework** | Custom Python assertions | Great Expectations, dbt tests | Lower dependency overhead; same pattern ports to dbt tests |
| **Credit pricing model** | Option A (monthly bucket) | Annual pool, rollover | Clearest shelfware/overage signal; standard PANW contract structure |

---

## 8. File Structure

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
│   │   ├── 03_cacv_account.sql
│   │   └── 04_cacv_rep_rollup.sql
│   ├── run_pipeline.py           # Executes all 5 SQL steps (steps 0–4)
│   └── dq_tests.py              # Automated data quality assertions (11 tests)
├── dashboard/
│   ├── app.py                    # Streamlit executive dashboard
│   └── requirements.txt
└── README.md
```

---

## 9. Running the Pipeline

```bash
# Authenticate
gcloud auth application-default login

# (Re-)generate synthetic data and upload to BigQuery
python3 data_generation/generate_data.py --upload

# Run full pipeline — Bronze (unchanged) → Silver → Gold dims → Gold fact → Semantic views
python3 pipeline_and_tests/run_pipeline.py

# Run against a specific historical snapshot
python3 pipeline_and_tests/run_pipeline.py --as-of-date 2025-06-30

# Run only a single step (0 = dim_dates, 1 = silver.active_contracts, …, 5 = semantic views)
python3 pipeline_and_tests/run_pipeline.py --step 4

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

## 10. Dashboard Implementation

### Stack
- **Frontend:** Streamlit (Python) — single-file app (`dashboard/app.py`)
- **Charting:** Plotly Express + Plotly Graph Objects
- **Data:** BigQuery Python client (`google-cloud-bigquery`); queries cached with `@st.cache_data(ttl=300)`
- **Auth:** Google Application Default Credentials (ADC) — `gcloud auth application-default login`

### Data Flow

```
BigQuery                    Streamlit App
──────────────────────────────────────────────────────
gtm.cacv_rep_rollup    →    load_rep_rollup(as_of_date)   → sidebar rep list, all rep-level charts
gtm.cacv_account       →    load_accounts(as_of_date,      → account scatter, account detail table
                                region, employee_id)
gtm.cacv_rep_rollup    →    load_available_dates()         → as-of-date selector in sidebar
raw.sales_reps         →    joined inside load_accounts()  → rep_name, region, segment on account rows
```

### Caching Strategy
- `load_rep_rollup` and `load_accounts`: 5-minute TTL — balances freshness with BQ query cost
- `load_available_dates`: 10-minute TTL — changes only when pipeline reruns
- `get_bq_client`: `@st.cache_resource` — single client instance per session (no reconnect overhead)

### Fallback Behavior
If `cacv_rep_rollup` has no rows for the requested `as_of_date`, the app falls back to the latest available data (`ORDER BY calculated_at DESC`). `load_accounts` similarly falls back to a full table scan with in-memory filtering if the date-filtered query returns nothing.

---

## 11. Downstream System Integrations

### 11.1 Integration Architecture

```
BigQuery (gold dataset — semantic layer views)
        │
        ├─── Nightly export ──► Salesforce CRM        (vw_account_detail)
        ├─── Monthly export ──► Compensation platform  (vw_rep_portfolio)
        ├─── Daily export ───► CS platform             (vw_account_detail)
        └─── On-demand ──────► BI layer                (fact_cacv_snapshot + dim_* directly)
```

All operational exports read from the semantic layer views — `vw_account_detail` for account-level consumers, `vw_rep_portfolio` for rep-level consumers. The BI layer queries the underlying `fact_cacv_snapshot` and dim tables directly for maximum aggregation flexibility.

---

### 11.2 Salesforce CRM

**Sync:** Nightly batch via BigQuery → Salesforce REST API (or Salesforce Connect external object)
**Source:** `gold.vw_account_detail`

| BQ Field | Salesforce Object | Salesforce Field | Notes |
|---|---|---|---|
| `health_tier` | Account | `Health_Tier__c` | Picklist: Expansion / Healthy / At Risk / Shelfware / Inactive / Ramping |
| `cacv_attainment_rate` | Account | `Consumption ACV_Attainment__c` | Number (%) — drives renewal forecast category |
| `acv_at_risk` | Account | `ACV_at_Risk__c` | Currency — adjusts renewal opportunity amount |
| `expansion_flag = TRUE` | Opportunity (auto-create) | Stage = `Expansion Identified` | Creates new opp on Account if none exists in stage |
| `is_spike_drop = TRUE` | Account | `Spike_Drop_Flag__c` | Checkbox — triggers CS save plan task |
| `employee_id` | Account | `Owner` (current) | Routes to current account owner for quota |
| `signing_owner_id` | Account | `Signing_Owner__c` | Preserved for comp attribution on original deal |

---

### 11.3 Compensation Platform (e.g., Xactly, CaptivateIQ)

**Sync:** Monthly close via BigQuery scheduled export → CSV/SFTP or direct API
**Source:** `gold.vw_rep_portfolio`

| BQ Field | Comp Use |
|---|---|
| `total_cacv` | Farmer quota attainment numerator |
| `cacv_attainment_rate` | Accelerator / decelerator tier lookup |
| `total_acv` | ACV quota denominator for attainment % |
| `expansion_arr_pipeline` | Expansion SPIF eligibility flag |

**Activation bonus** (requires `gold.fact_cacv_snapshot` joined to `gold.vw_account_detail`):
```sql
-- Accounts that hit ≥80% consumption within 90 days of contract start
SELECT f.employee_id, f.account_id, a.company_name, f.trailing_90d_avg_rate
FROM gold.fact_cacv_snapshot f
JOIN gold.dim_accounts a USING (account_id)
WHERE f.is_new_account = FALSE                           -- just aged out of ramping
  AND f.as_of_date = @as_of_date
  AND f.trailing_90d_avg_rate >= 0.80
```

---

### 11.4 Customer Success Platform (e.g., Gainsight, Totango)

**Sync:** Daily via BigQuery → CS platform API
**Source:** `gold.vw_account_detail`

| Health Tier | CS Score Range | Automated Action |
|---|---|---|
| Expansion | 90–100 | Flag for AE expansion handoff |
| Healthy | 70–89 | Maintain check-in cadence |
| At Risk | 40–69 | Open CS escalation playbook; 30-day SLA |
| Shelfware | 20–39 | Executive sponsor outreach playbook |
| Inactive | 0–19 | Immediate save plan; escalate to VP CS |
| Ramping | N/A | Onboarding playbook; 90-day activation tracking |

Key field mapping from `gold.vw_account_detail`:
- `trailing_90d_avg_rate` → CS health score (normalized 0–100)
- `months_of_data` → data confidence indicator (low if < 2)
- `is_zero_usage_month` (from `silver.monthly_consumption`) → trigger for proactive outreach if ≥ 2 consecutive months flagged

---

### 11.5 BI / Board Reporting (e.g., Tableau, Looker)

**Source:** `gold.fact_cacv_snapshot` + `gold.dim_*` directly — the BI layer bypasses the semantic layer views and joins at will, enabling any aggregation not pre-built into the views.

Key reports enabled by the current data model:

| Report | Source | Key Fields |
|---|---|---|
| Board NRR forecast | `vw_rep_portfolio` | `total_cacv / total_acv` org-wide as NRR leading indicator |
| Renewal risk register | `fact_cacv_snapshot` + `dim_contracts` | `acv_at_risk`, `contract_end_date`, `health_tier` |
| Expansion pipeline | `fact_cacv_snapshot` + `dim_accounts` + `dim_reps` | `expansion_flag`, `annual_commit_dollars`, rep name |
| Cohort churn analysis | `fact_cacv_snapshot` + `dim_dates` | Attainment by `fiscal_year_quarter` of contract start |
| QBR regional pack | `vw_rep_portfolio` | `region`, `total_acv`, `total_cacv`, `accounts_at_risk` |

---

## 12. v2 Roadmap

| Enhancement | Effort | Value |
|---|---|---|
| Port SQL to dbt | Medium | Dims and facts become first-class dbt models with built-in lineage, tests, and a docs site |
| `fact_cacv_monthly` grain table | Medium | Add a monthly-grain fact table (account × month) enabling cohort curves, trend analysis, and any time-series BI report currently blocked by the snapshot grain |
| SCD Type 2 on `dim_reps` + `dim_contracts` | Medium | Add `valid_from` / `valid_to` and `surrogate_key` — preserves history of territory reassignments and contract amendments without rewriting fact data (see §3.1) |
| ML churn prediction | High | Predict which At Risk accounts churn at renewal, trained on `fact_cacv_monthly` cohort history |
| Real-time updates via Pub/Sub | High | Move from daily batch to near-real-time Consumption ACV; semantic layer views remain unchanged |
| Cohort-based multiplier calibration | Medium | Validate health tier thresholds against actual churn cohorts using `fact_cacv_monthly` + renewal outcomes |
| Feature-depth weighting | Medium | Weight credits by product tier (base NGFW vs. advanced security add-ons) |
