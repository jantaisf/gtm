-- ─────────────────────────────────────────────────────────────────────────────
-- 06_vw_account_detail.sql
-- Semantic layer view: full account-level detail for drill-down consumers.
--
-- Consumers: Dashboard (Account Detail tab), CS platform, Salesforce CRM
-- Grain:     One row per account per as_of_date
-- Spec ref:  technical_spec.md §14.1, §Step 5, §10.2
--
-- Design notes:
--   · All three trailing rate windows are exposed here (7d, 30d, 90d).
--     The dashboard rate-window selector switches which column to display;
--     Consumption ACV always uses the 90d window for comp purposes.
--   · Behavioural alert flags (early_shelfware_flag, onboarding_stall_flag,
--     spike_drop_early_flag) surface in this view for CS platform alerting.
--     They do NOT affect health_tier or cacv.
--   · days_to_renewal is pre-computed to simplify renewal desk sorting.
--   · Row-level security should be applied on employee_id = SESSION_USER()
--     for rep-facing consumers; CS managers see full region; RevOps sees all.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW `openclaw-gateway-491103.gold.vw_account_detail` AS

WITH

-- ── Trailing rate windows ────────────────────────────────────────────────────
-- Compute 7d (≈1 month) and 30d (≈2 month) windows alongside the 90d (3 month)
-- window already in cacv_account. Production can replace these with true
-- daily-grain calculations once daily_usage_logs are available at query time.
trailing_rates AS (
  SELECT
    account_id,
    -- 90d window: months 1–3 (already in cacv_account; recomputed here for join)
    AVG(CASE WHEN month_rank <= 3 THEN consumption_rate END) AS trailing_90d_avg_rate,
    -- 30d window: most recent 2 complete months
    AVG(CASE WHEN month_rank <= 2 THEN consumption_rate END) AS trailing_30d_avg_rate,
    -- 7d window: most recent 1 complete month
    AVG(CASE WHEN month_rank <= 1 THEN consumption_rate END) AS trailing_7d_avg_rate
  FROM (
    SELECT
      account_id,
      consumption_rate,
      ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY usage_month DESC) AS month_rank
    FROM `openclaw-gateway-491103.staging.stg_monthly_consumption`
  )
  GROUP BY account_id
),

-- ── Behavioural alert flags (spec §10.2) ────────────────────────────────────
alert_flags AS (
  SELECT
    account_id,

    -- Early shelfware: consumption dropped >40% in first 60 days
    CASE
      WHEN tr.trailing_7d_avg_rate < 0.30
        AND ca.months_of_data <= 2
        AND NOT ca.is_new_account
      THEN TRUE ELSE FALSE
    END AS early_shelfware_flag,

    -- Onboarding stall: new account with zero usage after 30 days
    CASE
      WHEN ca.is_new_account
        AND tr.trailing_7d_avg_rate = 0
        AND DATE_DIFF(CURRENT_DATE(), ca.contract_start_date, DAY) > 30
      THEN TRUE ELSE FALSE
    END AS onboarding_stall_flag,

    -- Spike & drop early: large spike followed by near-zero (before 90d avg smooths it)
    CASE
      WHEN tr.trailing_7d_avg_rate < 0.05
        AND ca.max_monthly_rate > 2.0
        AND ca.months_of_data <= 2
      THEN TRUE ELSE FALSE
    END AS spike_drop_early_flag

  FROM `openclaw-gateway-491103.gtm.cacv_account` ca
  JOIN trailing_rates tr USING (account_id)
)

SELECT
  -- ── Account identifiers ──────────────────────────────────────────────────
  ca.account_id,
  ca.company_name,
  ca.industry,
  ca.primary_contract_id,
  ca.active_contract_count,
  ca.has_expansion,

  -- ── Contract terms ───────────────────────────────────────────────────────
  ca.contract_start_date,
  ca.contract_end_date,
  ca.contract_term_months,
  ca.annual_commit_dollars,
  ca.included_monthly_compute_credits,
  DATE_DIFF(ca.contract_end_date, CURRENT_DATE(), DAY) AS days_to_renewal,

  -- ── Rep and territory ────────────────────────────────────────────────────
  ca.employee_id,
  sr.name        AS rep_name,
  sr.region,
  sr.segment,
  sr.manager_name,

  -- ── Consumption rate windows ─────────────────────────────────────────────
  -- 7d and 30d for monitoring; 90d is the authoritative comp window
  tr.trailing_7d_avg_rate,
  tr.trailing_30d_avg_rate,
  tr.trailing_90d_avg_rate,

  -- ── cACV metrics ─────────────────────────────────────────────────────────
  ca.health_tier,
  ca.cacv,
  ca.acv_at_risk,
  ca.expansion_signal_acv                               AS consumption_overage_acv,

  -- ── History depth ────────────────────────────────────────────────────────
  ca.months_of_data,
  ca.max_monthly_rate,
  ca.overage_months,
  ca.zero_usage_months,

  -- ── Boolean signals ──────────────────────────────────────────────────────
  ca.is_new_account,
  ca.expansion_flag,
  ca.is_spike_drop,
  ca.low_data_flag,
  af.early_shelfware_flag,
  af.onboarding_stall_flag,
  af.spike_drop_early_flag,

  -- ── Snapshot metadata ────────────────────────────────────────────────────
  ca.as_of_date,
  CURRENT_TIMESTAMP() AS refreshed_at

FROM `openclaw-gateway-491103.gtm.cacv_account` ca
JOIN `openclaw-gateway-491103.raw.sales_reps`   sr ON sr.employee_id = ca.employee_id
JOIN trailing_rates                             tr USING (account_id)
JOIN alert_flags                                af USING (account_id)
ORDER BY ca.acv_at_risk DESC NULLS LAST
;
