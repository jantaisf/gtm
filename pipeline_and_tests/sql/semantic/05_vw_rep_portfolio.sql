-- ─────────────────────────────────────────────────────────────────────────────
-- 05_vw_rep_portfolio.sql
-- Semantic layer view: rep-level Consumption ACV portfolio rollup.
--
-- Consumers: Dashboard (Tabs 2–3), Compensation platform, QBR packs
-- Grain:     One row per sales rep per as_of_date
-- Spec ref:  technical_spec.md §14.1, §Step 5
--
-- Design notes:
--   · Ramping accounts are EXCLUDED from total_acv (the attainment denominator)
--     to avoid penalising reps who recently landed new logos. They are counted
--     separately in accounts_ramping and tracked via the onboarding activation view.
--   · consumption_overage_acv aggregates the upsell signal from accounts consuming
--     above their committed ACV. This feeds the expansion pipeline.
--   · region_rank and org_rank are pre-computed for leaderboard rendering without
--     requiring a second query from the BI tool.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW `openclaw-gateway-491103.gold.vw_rep_portfolio` AS

WITH rep_agg AS (
  SELECT
    ca.employee_id,
    sr.name                                                       AS rep_name,
    sr.region,
    sr.segment,
    sr.manager_name,
    sr.manager_id,

    -- ── Portfolio size ───────────────────────────────────────────────────────
    COUNT(*)                                                      AS total_accounts,
    COUNTIF(ca.is_new_account)                                    AS accounts_ramping,
    COUNTIF(NOT ca.is_new_account)                                AS accounts_mature,

    -- ── ACV totals (mature accounts only for attainment denominator) ─────────
    -- total_acv excludes Ramping so attainment_rate reflects actual utilisation
    SUM(CASE WHEN NOT ca.is_new_account
             THEN ca.annual_commit_dollars ELSE 0 END)            AS total_acv,
    SUM(ca.cacv)                                                  AS total_cacv,
    SUM(ca.acv_at_risk)                                           AS total_acv_at_risk,

    -- ── Expansion signals ────────────────────────────────────────────────────
    -- expansion_signal_acv: consumption above the ACV cap (over-consuming accounts)
    SUM(ca.expansion_signal_acv)                                  AS total_expansion_signal_acv,
    -- consumption_overage_acv is an alias used in comp reporting
    SUM(ca.expansion_signal_acv)                                  AS total_consumption_overage_acv,
    COUNTIF(ca.expansion_flag)                                    AS expansion_opportunities,

    -- ── cACV attainment rate ─────────────────────────────────────────────────
    -- = total_cacv / total_acv (mature accounts only)
    ROUND(
      SAFE_DIVIDE(
        SUM(ca.cacv),
        SUM(CASE WHEN NOT ca.is_new_account THEN ca.annual_commit_dollars END)
      ), 4
    )                                                             AS cacv_attainment_rate,

    -- ── Health tier breakdowns (account counts) ───────────────────────────────
    COUNTIF(ca.health_tier = 'Expansion')                         AS accounts_expansion,
    COUNTIF(ca.health_tier = 'Healthy')                           AS accounts_healthy,
    COUNTIF(ca.health_tier = 'At Risk')                           AS accounts_at_risk,
    COUNTIF(ca.health_tier = 'Shelfware')                         AS accounts_shelfware,
    COUNTIF(ca.health_tier = 'Inactive')                          AS accounts_inactive,

    -- ── ACV by health tier (for risk exposure reporting) ─────────────────────
    SUM(CASE WHEN ca.health_tier = 'Expansion'
             THEN ca.annual_commit_dollars ELSE 0 END)            AS acv_expansion,
    SUM(CASE WHEN ca.health_tier = 'Healthy'
             THEN ca.annual_commit_dollars ELSE 0 END)            AS acv_healthy,
    SUM(CASE WHEN ca.health_tier IN ('At Risk', 'Shelfware', 'Inactive')
             THEN ca.annual_commit_dollars ELSE 0 END)            AS acv_at_risk_tiers,

    -- ── Anomaly and watchlist counts ─────────────────────────────────────────
    COUNTIF(ca.is_spike_drop)                                     AS spike_drop_accounts,
    COUNTIF(ca.low_data_flag)                                     AS low_data_accounts,
    COUNTIF(ca.has_expansion)                                     AS mid_year_expansion_accounts,

    -- ── Average consumption rate (mature accounts only) ───────────────────────
    ROUND(AVG(CASE WHEN NOT ca.is_new_account
                   THEN ca.trailing_90d_avg_rate END), 4)         AS avg_consumption_rate_90d,

    -- ── Snapshot metadata ─────────────────────────────────────────────────────
    MAX(ca.as_of_date)                                            AS as_of_date,
    CURRENT_TIMESTAMP()                                           AS refreshed_at

  FROM `openclaw-gateway-491103.gtm.cacv_account` ca
  JOIN `openclaw-gateway-491103.raw.sales_reps`   sr
    ON sr.employee_id = ca.employee_id
  GROUP BY
    ca.employee_id, sr.name, sr.region, sr.segment, sr.manager_name, sr.manager_id
)

SELECT
  *,
  -- Leaderboard rankings (computed last so they span the full result set)
  RANK() OVER (PARTITION BY region ORDER BY total_cacv DESC NULLS LAST) AS region_rank,
  RANK() OVER (                   ORDER BY total_cacv DESC NULLS LAST) AS org_rank
FROM rep_agg
ORDER BY total_cacv DESC NULLS LAST
;
