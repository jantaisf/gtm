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
- **BI tool compatibility** — the views expose a flat surface that any SQL-compatible BI platform can query without joins; production dashboards will be built on PANW's existing BI tooling
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

### 3.2 Audit Trail (Comp Auditability)

Consumption ACV drives compensation. That means **every figure that influences a paycheck must be fully auditable** — traceable from the commission record back to the raw source data, with an immutable record of any retroactive change. This is a finance and legal requirement, not an analytics nice-to-have (see product_spec.md §2.1 and §2.2.2).

The audit trail has four layers, each described below:

1. **Pipeline provenance** — every metric value is linked to the pipeline run that produced it (`pipeline_run_log`)
2. **Retroactive corrections** — any after-the-fact change to an already-paid figure is recorded in a non-destructive delta table (`fact_cacv_corrections`)
3. **Ownership history** — who owned each account at each point in time, for correct rep attribution (`account_ownership_history`, §3.3)
4. **Contract amendments** — changes to ACV or credit allowance that affect the denominator (`contract_amendments`, §3.3)

Before integrating with the compensation platform, Finance and RevOps must define and document:
- The correction workflow and required approvals at each tier (see product_spec.md §13 Q8)
- The rep dispute resolution process (how a rep challenges a calculated figure)
- The clawback policy and what events trigger a `clawback_triggered = TRUE` record
- The comp period cut-off rule (which pipeline run "locks" the comp period for a given quarter)

These process decisions cannot be inferred from the data model — they must be codified before the first live comp period.

#### Pipeline Run Log and Corrections

Any Consumption ACV figure flowing to a compensation platform must be traceable to the exact pipeline run that produced it, with an immutable record of any retroactive corrections.

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

**Default: today's date.** Running the pipeline or data quality tests without specifying `--as-of-date` produces a snapshot for the current calendar date. Explicitly passing `--as-of-date YYYY-MM-DD` overrides this for point-in-time analysis or backfills.

```bash
python3 pipeline_and_tests/run_pipeline.py                        # snapshot for today
python3 pipeline_and_tests/run_pipeline.py --as-of-date 2025-06-30  # historical snapshot
```

**Why this matters:**
- Enables point-in-time analysis and backtesting — run against any past date to reproduce a historical snapshot exactly.
- `stg_active_contracts` uses `as_of_date` to determine which contracts are active at that moment.
- `cacv_account` uses `as_of_date` to define the trailing 90-day window and the new account (Ramping) threshold.
- The pipeline is idempotent for a given `as_of_date` — running it twice for the same date overwrites the prior result rather than appending.

---

## 7. Technology Choices & Rationale

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| **Data warehouse** | BigQuery | Snowflake, Redshift | Free sandbox tier; serverless; strong Python client |
| **Pipeline style** | SQL (dbt-style) | PySpark, Pandas | Readable, auditable, portable to dbt in production |
| **Dashboard** | Streamlit + Plotly | PANW's existing BI platform | Fastest iteration for prototype; no BI license required. Production dashboards will be rebuilt on PANW's existing BI tooling, which connects directly to the BigQuery semantic layer views |
| **Data Quality framework** | Custom Python assertions | Great Expectations, dbt tests | Lower dependency overhead; same pattern ports to dbt tests |
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

# Data quality tests — fail CI on any ERROR
python3 pipeline_and_tests/dq_tests.py --fail-on-error --output results.json

# Launch dashboard
streamlit run dashboard/app.py
```

### 9.1 Refresh Schedule

All pipeline runs are scheduled in **UTC** to avoid DST ambiguity across PANW's global operations. Three runs per day ensure each major region receives a fresh snapshot at both the start and end of its business day.

| Run | UTC Time | Americas | EMEA | APAC | Regional role |
|-----|----------|----------|------|------|---------------|
| 1 | 00:00 UTC | 5 PM PT / 8 PM ET (prior day) | 1 AM CET | 8 AM SGT | Americas EOD · APAC BOD |
| 2 | 08:00 UTC | 1 AM PT / 4 AM ET | 9 AM CET | 4 PM SGT | EMEA BOD · APAC EOD |
| 3 | 16:00 UTC | 9 AM PT / 12 PM ET | 5 PM CET | Midnight SGT | Americas BOD · EMEA EOD |

> **Note — Run 1 timing:** The 00:00 UTC run depends on upstream usage logs being fully ingested before midnight UTC. If daily usage data from cloud providers is not available until 01:00–02:00 UTC (a common pattern for usage metering pipelines), Run 1 should be shifted accordingly or skipped in favour of Runs 2 and 3. Validate ingestion SLAs with the platform data engineering team before setting the production schedule.

### 9.2 Upstream Data Dependencies

The pipeline is designed to be **event-driven** — each run should be triggered by a completion signal from the upstream ingestion job rather than on a fixed clock. If the upstream job is delayed, the pipeline run defers to the next scheduled window rather than starting against incomplete data.

| Source Table | Source System | Typical Ingestion Cadence | Pipeline Dependency |
|---|---|---|---|
| `bronze.daily_usage_logs` | Prisma Cloud metering API | Daily batch (last-mile, closes ~23:00 UTC prior day) | **Critical — pipeline must not start until this table is confirmed complete** |
| `bronze.contracts` | CRM (e.g., Salesforce CPQ) | Near-real-time CDC or nightly batch | Non-blocking after initial load; changes propagate on next run |
| `bronze.accounts` | CRM / MDM | Near-real-time CDC or nightly batch | Non-blocking after initial load |
| `bronze.sales_reps` | HRIS (e.g., Workday) | Daily or on-change | Non-blocking; rep roster changes are low-frequency |

**Recommended trigger pattern:**

```
upstream_ingestion_job completes
    → emits completion event (Pub/Sub, Airflow sensor, or dbt source freshness check)
    → pipeline_and_tests/run_pipeline.py is invoked with --as-of-date <today>
    → on success, data quality tests run automatically (dq_tests.py --fail-on-error)
    → on data quality failure, on-call alert is raised; downstream Gold tables are not refreshed
```

If event-driven triggering is not available at initial rollout, the fixed UTC schedule in §9.1 can be used as a fallback, with the understanding that Run 1 may occasionally execute before `bronze.daily_usage_logs` is fully populated.

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

### 11.5 BI / Board Reporting (PANW's existing BI platform)

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

---

## 13. Testing & Quality Checks

The test suite spans three layers. Each layer catches a different class of failure: bad source data (Layer 1), broken pipeline logic (Layer 2), and broken dashboard rendering (Layer 3).

```
Layer 1 — Data Quality (dq_tests.py)
    Catches problems in the Bronze tables before they corrupt metric output.
    Runs automatically after every pipeline execution.

Layer 2 — Metric Correctness (pipeline unit tests)
    Asserts that the Gold-layer fact table matches expected values for
    known input scenarios (§5). Catches regressions in SQL logic.

Layer 3 — Dashboard Smoke Tests
    Confirms the Streamlit app loads, queries BigQuery, and renders
    all four pages without an unhandled exception.
```

---

### 13.1 Layer 1 — Data Quality Tests (`dq_tests.py`)

Eleven assertions run against the Bronze tables. A **severity** controls what happens on failure:

- `ERROR` — data integrity is broken; the pipeline **must not proceed**. With `--fail-on-error`, the process exits with code 1, blocking downstream steps.
- `WARNING` — an expected anomaly (e.g., orphaned logs) that is handled by the pipeline but should be monitored for volume.
- `INFO` — a normal pattern worth surfacing (e.g., Ramping accounts). Always passes; never blocks.

| # | Test | Severity | What it catches | Pipeline impact |
|---|------|----------|-----------------|-----------------|
| 1 | `test_null_primary_keys` | ERROR | NULL `employee_id`, `account_id`, `contract_id`, or `log_id` in any Bronze table | Blocks pipeline |
| 2 | `test_negative_credits` | ERROR | Rows in `daily_usage_logs` where `compute_credits_consumed < 0` — likely metering errors | Blocks pipeline |
| 3 | `test_malformed_contracts` | ERROR | Contracts where `end_date < start_date` — makes active-contract resolution undefined | Blocks pipeline |
| 4 | `test_duplicate_log_ids` | ERROR | Duplicate `log_id` values — would double-count usage in monthly aggregation | Blocks pipeline |
| 5 | `test_contracts_missing_accounts` | ERROR | Contracts whose `account_id` has no matching row in `accounts` | Blocks pipeline |
| 6 | `test_accounts_missing_reps` | ERROR | Accounts whose `employee_id` has no matching row in `sales_reps` | Blocks pipeline |
| 7 | `test_orphaned_usage` | WARNING | Usage logs for `account_id` values not present in `accounts` — excluded from cACV | Logged; pipeline continues |
| 8 | `test_out_of_contract_usage` | WARNING | Usage for valid accounts that falls outside all contract windows — excluded from cACV | Logged; pipeline continues |
| 9 | `test_shelfware_rate` | WARNING | >15% of currently active accounts have zero usage in the trailing 90 days | Logged; pipeline continues |
| 10 | `test_overlapping_contracts` | INFO | Accounts with >1 simultaneously active contract (expected for mid-year expansions) | Informational only |
| 11 | `test_new_account_rate` | INFO | % of active accounts in Ramping status (contract < 90 days old) | Informational only |

**Running data quality tests:**

```bash
# Standard run against today's snapshot
python3 pipeline_and_tests/dq_tests.py

# Historical snapshot
python3 pipeline_and_tests/dq_tests.py --as-of-date 2025-06-30

# Fail with exit code 1 on any ERROR (use in CI)
python3 pipeline_and_tests/dq_tests.py --fail-on-error

# Write structured results to JSON
python3 pipeline_and_tests/dq_tests.py --as-of-date 2025-06-30 --output results.json
```

The JSON output includes `test_name`, `severity`, `passed`, `row_count`, `detail`, and up to 5 `sample_rows` per failing test — sufficient for triage without a BigQuery console.

---

### 13.2 Layer 2 — Metric Correctness Tests

The scenarios in §5 define the exact expected output for nine representative accounts. These serve as regression tests: if Consumption ACV, Consumption Overage, or Health Tier changes unexpectedly on any scenario after a SQL refactor, a test should catch it before it reaches production.

**Assertions encoded as pipeline tests:**

| Assertion | Rule |
|---|---|
| Cap holds | `cacv <= annual_commit_dollars` for all non-NULL rows |
| Floor holds | `cacv >= 0` for all non-NULL rows |
| Overage non-negative | `expansion_signal_acv >= 0` for all non-NULL rows |
| Arithmetic identity | `cacv + expansion_signal_acv = ROUND(annual_commit_dollars × trailing_90d_avg_rate, 2)` for all non-NULL rows |
| At-risk identity | `acv_at_risk = annual_commit_dollars - cacv` for all non-NULL rows |
| Ramping accounts NULL | `cacv IS NULL` and `expansion_signal_acv IS NULL` for any account whose earliest contract start is within 90 days of `as_of_date` |
| No phantom accounts | Every `account_id` in `fact_cacv_snapshot` exists in `dim_accounts` |
| No phantom reps | Every `employee_id` in `fact_cacv_snapshot` exists in `dim_reps` |
| Rate window consistency | `trailing_90d_avg_rate` is always the rate used in the `cacv` calculation regardless of the display window selected in the dashboard |

**Suggested implementation:** These can be expressed as BigQuery `ASSERT` statements or as Python `pytest` tests that query the Gold tables and compare against the §5 fixture values. dbt users can encode them as `dbt test` assertions in `schema.yml`.

---

### 13.3 Layer 3 — Dashboard Smoke Tests

Minimal end-to-end checks that confirm the Streamlit app renders without errors against a live (or mock) BigQuery connection.

| Check | Description |
|---|---|
| App boots | `streamlit run dashboard/app.py` exits with code 0 on `--server.headless true` |
| All four pages load | Summary, Renewal Risk, Consumption Overage, and Account Detail each render without an unhandled exception |
| Empty-state handling | App degrades gracefully when `fact_cacv_snapshot` returns zero rows (e.g., new environment with no data) |
| Rate window fallback | When `trailing_7d_avg_rate` or `trailing_30d_avg_rate` columns are absent (older data schema), the app silently falls back to `trailing_90d_avg_rate` |
| Non-90d info banner | Selecting a 7d or 30d window in the sidebar surfaces the comp-window notice in Account Detail |

---

### 13.4 CI Integration

Recommended pipeline for an automated CI run (e.g., GitHub Actions, Cloud Build):

```
1. Run data quality tests with --fail-on-error
       python3 pipeline_and_tests/dq_tests.py --fail-on-error --output dq_results.json
       → Exit 1 on any ERROR severity failure; downstream steps are skipped.

2. Run pipeline
       python3 pipeline_and_tests/run_pipeline.py --as-of-date <today>
       → Creates/overwrites Gold tables.

3. Run metric correctness assertions
       pytest pipeline_and_tests/test_metric_correctness.py
       → Queries Gold tables; asserts §13.2 rules hold.

4. Archive data quality results
       Upload dq_results.json as a build artifact for audit trail.
```

**Exit code contract:**
- `dq_tests.py` exits `0` if all ERROR-level tests pass (warnings and info do not affect the exit code unless `--fail-on-error` is set).
- `run_pipeline.py` exits `0` on success, `1` on any BigQuery job error.
- Metric correctness tests follow standard `pytest` exit codes (`0` = all pass, `1` = any failure).

---

### 13.5 Known Gaps (v2)

| Gap | Risk | Planned fix |
|---|---|---|
| No automated metric correctness test file exists yet | Medium — SQL regressions may go undetected | Add `pytest` fixture in `pipeline_and_tests/test_metric_correctness.py` encoding all §5 scenarios |
| Dashboard smoke tests are manual | Low for prototype; medium in production | Add `pytest` + `playwright` headless Streamlit tests |
| No schema change detection | Medium — upstream column renames silently break the pipeline | Add a Bronze schema fingerprint check to `dq_tests.py` (compare actual column names against expected schema) |
| Shelfware threshold (15%) is hardcoded | Low | Promote to a configurable parameter; alert threshold may differ by segment or quarter |
| Data quality tests don't cover Silver or Gold tables | Medium post-GA | Extend `dq_tests.py` with a `--layer silver\|gold` flag to run referential integrity checks on the downstream tables |

---

## 14. Semantic Layer Build-Out

### 14.0 What the Prototype Has

The current prototype implements a minimal semantic layer: two BigQuery views built in pipeline Step 5 that flatten the star schema into denormalized surfaces.

| View | Grain | Primary consumers |
|---|---|---|
| `gold.vw_rep_portfolio` | One row per sales rep | Dashboard tabs 2–3, compensation platform |
| `gold.vw_account_detail` | One row per account | Dashboard tab 6, CS platform, Salesforce |

These views are functional and sufficient for the prototype, but they do not cover all downstream consumers, do not enforce access control, and are not documented at the column level. The sections below describe what a production build adds.

---

### 14.1 Additional Views for Production

Each downstream consumer has different grain, column, and freshness requirements. Rather than exposing the raw Gold tables directly — which requires each consumer to write their own joins — production should add a view per consumer type.

| View | Grain | New vs. prototype | Consumer | Key columns added |
|---|---|---|---|---|
| `gold.vw_rep_portfolio` | Rep | Exists | Dashboard, comp platform | No change to existing columns; add `manager_id`, `manager_name` for rollup reporting |
| `gold.vw_account_detail` | Account | Exists | Dashboard, CS platform, Salesforce | No change; consider adding `days_to_renewal`, `contract_type` |
| `gold.vw_regional_summary` | Region | **New** | Regional VPs, Finance | Pre-aggregated region totals — `total_acv`, `total_cacv`, `attainment_rate`, `acv_at_risk`, tier counts |
| `gold.vw_renewal_pipeline` | Account, sorted by `contract_end_date` | **New** | CFO, Renewal desk | Accounts within 180-day renewal window; columns: `days_to_renewal`, `health_tier`, `acv_at_risk`, `cacv`, `trailing_90d_avg_rate` |
| `gold.vw_expansion_signals` | Account | **New** | AEs, Sales Managers | Accounts with `expansion_flag = TRUE` or `expansion_signal_acv > 0`; ordered by overage magnitude |
| `gold.vw_comp_input` | Rep × month | **New** | Compensation platform | Monthly Consumption ACV per rep; includes `run_id` from `pipeline_run_log` for audit trail; excludes Ramping accounts |
| `gold.vw_finance_snapshot` | Rep, Region, Org total | **New** | CFO, Finance, Board reporting | Aggregated Consumption ACV attainment and risk at org level; designed to feed CFO/board dashboards without raw access to rep-level data |

**Design rule:** Views are additive — adding a column or a new view never breaks an existing consumer. Removing or renaming a column is a breaking change and requires a deprecation window (see §14.4).

---

### 14.2 Access Control and Row-Level Security

The Gold tables and semantic views contain commercially sensitive compensation and forecast data. Production access should follow the principle of least privilege.

| Role | Access | Implementation |
|---|---|---|
| **Sales rep** | Own accounts and metrics only | BigQuery row-level security on `vw_account_detail` filtered by `employee_id = SESSION_USER()` |
| **Sales manager** | All accounts in their region | Row-level security filtered by `region` matching manager's assigned territories |
| **Regional VP** | Their region's reps and accounts | Same as manager; can also access `vw_regional_summary` for their region |
| **Revenue Operations** | All reps, all regions — read only | Full read on all `gold.*` views; no access to Bronze or Silver |
| **Compensation platform (service account)** | `vw_comp_input` only | Dedicated service account; no access to other views |
| **Finance / CFO** | Aggregate views only | `vw_finance_snapshot`, `vw_renewal_pipeline`; no rep-level detail unless explicitly granted |
| **Data Engineering** | Full read/write on all datasets | Pipeline execution; separate service account from consumer roles |

> **Note:** This access model is a starting point. PANW's actual role structure, territory hierarchy, and data governance policies will determine the final implementation. Row-level security rules should be reviewed with RevOps and Legal before go-live.

---

### 14.3 Column Documentation (Data Dictionary)

Every column in every production view should have a documented definition attached at the BigQuery schema level using `column_description` in the DDL, or as dbt column-level docs in `schema.yml`. The minimum required fields for each column entry:

| Field | Description |
|---|---|
| `column_name` | Exact column name as it appears in the view |
| `data_type` | BigQuery data type |
| `definition` | Plain-English definition — what the number means, not how it is calculated |
| `calculation` | Formula or SQL reference (e.g., "= `annual_commit_dollars × trailing_90d_avg_rate`, capped at `annual_commit_dollars`") |
| `grain` | What one row represents |
| `source` | Upstream table(s) and column(s) this value derives from |
| `nullability` | Conditions under which the column is NULL (e.g., "NULL for Ramping accounts") |
| `comp_use` | Whether this column feeds the compensation platform — if yes, any changes require CFO sign-off |

**Priority columns to document first** (highest comp and business risk):

- `cacv` — Consumption ACV; the metric used for compensation
- `expansion_signal_acv` — Consumption Overage; upsell signal
- `trailing_90d_avg_rate` — the rate used in all comp calculations
- `health_tier` — drives renewal risk classification and CS escalation
- `is_new_account` — determines whether an account is excluded from comp

---

### 14.4 View Versioning and Backward Compatibility

Once downstream systems (comp platform, Salesforce, CS tools) depend on semantic views, column changes become breaking changes. The recommended pattern:

```
1. New column needed  →  ADD to existing view (non-breaking, safe to deploy immediately)

2. Column rename      →  ADD new column with new name; keep old name as alias for one quarter;
                         notify consumers; remove alias in the following quarter

3. Column removed     →  Same as rename — alias the old name to NULL (or a safe default) for
                         one quarter to allow consumers to migrate; then remove

4. New consumer view  →  Add new view; no impact on existing consumers

5. Metric logic change→  Bump view version suffix: vw_account_detail_v2
                         Run both versions in parallel for one full comp cycle;
                         migrate consumers; deprecate v1
```

> Any change to a column flagged `comp_use = TRUE` (see §14.3) requires written approval from the VP of Finance before deployment, regardless of whether it appears additive.

---

### 14.5 Metrics Layer (v2 Consideration)

The current semantic layer is SQL views in BigQuery — sufficient for the prototype and early production. As the number of consumers grows, a dedicated **metrics layer** ensures every team uses the same definition of Consumption ACV, regardless of which BI tool or API they query through.

Options to evaluate in v2:

| Tool | Approach | Fits when |
|---|---|---|
| **dbt metrics** | Define metrics in `schema.yml`; dbt generates the SQL | Already using dbt for transformations; want metrics in the same repo as models |
| **Cube.js** (or similar) | Standalone semantic/metrics API; caches and pre-aggregates | Multiple BI tools need the same metrics; want query acceleration |
| **LookML (Looker)** | Metrics defined in LookML models; explored via Looker UI | PANW's BI platform is Looker — definitions live in the BI layer, not the warehouse |
| **BigQuery BI Engine + views** | Stay in BigQuery; rely on views + caching | Simpler stack; single BI tool; fewer consumers |

The current SQL view approach maps cleanly to any of these options — the `gold.*` views become the source tables for whichever metrics layer is adopted. No pipeline changes are required when the metrics layer is added or swapped.
