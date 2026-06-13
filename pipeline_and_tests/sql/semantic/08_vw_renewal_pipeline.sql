-- ─────────────────────────────────────────────────────────────────────────────
-- 08_vw_renewal_pipeline.sql
-- Semantic layer view: renewal risk register sorted by urgency.
--
-- Consumers: CFO, Renewal desk, CS Leadership
-- Grain:     One row per account per as_of_date, within the renewal window
-- Spec ref:  technical_spec.md §14.1, Dashboard Tab 4 (Renewal Risk)
--
-- Design notes:
--   · Scoped to accounts renewing within 180 days. The CFO renewal cadence
--     focuses on the 90-day window; CS teams work the full 180-day horizon.
--     Both are included here and the consumer applies their own time filter.
--   · renewal_urgency_bucket is pre-computed for easy BI dashboard grouping
--     without requiring CASE logic in every downstream query.
--   · renewal_risk_score combines health tier and days_to_renewal into a
--     sortable composite: lower score = higher urgency. Derived from:
--       base_risk  = tier rank (Inactive=5, Shelfware=4, At Risk=3, Healthy=2, Expansion=1)
--       urgency    = 1 + FLOOR(days_to_renewal / 30)  (closer = more urgent)
--       risk_score = base_risk × urgency (lower is worse)
--   · Accounts with no consumption data (cacv IS NULL, i.e. Ramping) are
--     included but flagged — they represent real renewal risk from unknown
--     usage patterns. Finance and CS should treat them as a separate category.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW `openclaw-gateway-491103.gold.vw_renewal_pipeline` AS

WITH

tier_risk_rank AS (
  -- Map health tier to a risk severity score (higher = riskier)
  SELECT 'Inactive'  AS health_tier, 5 AS tier_risk UNION ALL
  SELECT 'Shelfware',                4              UNION ALL
  SELECT 'At Risk',                  3              UNION ALL
  SELECT 'Ramping',                  3              UNION ALL  -- unknown = treat as at-risk
  SELECT 'Healthy',                  2              UNION ALL
  SELECT 'Expansion',                1
),

renewal_base AS (
  SELECT
    ca.account_id,
    ca.company_name,
    ca.industry,
    ca.primary_contract_id,

    -- ── Contract timing ───────────────────────────────────────────────────
    ca.contract_start_date,
    ca.contract_end_date,
    ca.contract_term_months,
    DATE_DIFF(ca.contract_end_date, ca.as_of_date, DAY)          AS days_to_renewal,

    -- ── Renewal urgency bucket ─────────────────────────────────────────────
    CASE
      WHEN DATE_DIFF(ca.contract_end_date, ca.as_of_date, DAY) <= 30  THEN '0–30 days'
      WHEN DATE_DIFF(ca.contract_end_date, ca.as_of_date, DAY) <= 60  THEN '31–60 days'
      WHEN DATE_DIFF(ca.contract_end_date, ca.as_of_date, DAY) <= 90  THEN '61–90 days'
      ELSE                                                              '91–180 days'
    END                                                           AS renewal_urgency_bucket,

    -- ── ACV and cACV ──────────────────────────────────────────────────────
    ca.annual_commit_dollars,
    ca.cacv,
    ca.acv_at_risk,
    ca.expansion_signal_acv                                       AS consumption_overage_acv,

    -- ── Health ────────────────────────────────────────────────────────────
    ca.health_tier,
    ca.trailing_90d_avg_rate,
    ca.months_of_data,
    ca.is_new_account,
    ca.expansion_flag,
    ca.is_spike_drop,

    -- ── Rep and territory ────────────────────────────────────────────────
    ca.employee_id,
    sr.name        AS rep_name,
    sr.region,
    sr.segment,
    sr.manager_name,

    -- ── Snapshot metadata ─────────────────────────────────────────────────
    ca.as_of_date,
    CURRENT_TIMESTAMP() AS refreshed_at,

    -- ── Risk rank (for composite scoring below) ───────────────────────────
    tr.tier_risk

  FROM `openclaw-gateway-491103.gtm.cacv_account` ca
  JOIN `openclaw-gateway-491103.raw.sales_reps`   sr ON sr.employee_id = ca.employee_id
  JOIN tier_risk_rank                             tr ON tr.health_tier  = ca.health_tier

  -- Scope to the 180-day renewal window
  WHERE ca.contract_end_date BETWEEN ca.as_of_date AND DATE_ADD(ca.as_of_date, INTERVAL 180 DAY)
)

SELECT
  *,
  -- ── Composite renewal risk score ─────────────────────────────────────────
  -- Lower value = higher urgency. Combines tier severity and time pressure.
  -- tier_risk (1–5) × urgency_multiplier (1 = expiring soon, higher = further out)
  -- Inactive account expiring in 10 days scores 5; Expansion account in 170 days scores 6.
  ROUND(
    tier_risk * (1 + FLOOR(days_to_renewal / 30.0)), 2
  )                                                               AS renewal_risk_score

FROM renewal_base
ORDER BY
  renewal_risk_score ASC,      -- most urgent first
  acv_at_risk        DESC      -- largest dollar risk as tiebreaker
;
