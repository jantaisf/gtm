-- ─────────────────────────────────────────────────────────────────────────────
-- 04_carr_rep_rollup.sql
-- Aggregates cARR from account level to rep and region level.
-- Used by the executive dashboard and sales compensation tracking.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE TABLE `openclaw-gateway-491103.gtm.carr_rep_rollup` AS

WITH rep_metrics AS (
  SELECT
    ca.employee_id,
    sr.name                                                     AS rep_name,
    sr.region,
    sr.segment,

    -- Portfolio size
    COUNT(*)                                                    AS total_accounts,
    COUNTIF(ca.is_new_account)                                  AS ramping_accounts,
    COUNT(*) - COUNTIF(ca.is_new_account)                       AS mature_accounts,

    -- ARR vs cARR (exclude ramping accounts from cARR sum)
    SUM(ca.annual_commit_dollars)                               AS total_arr,
    SUM(ca.carr)                                                AS total_carr,
    SUM(ca.arr_at_risk)                                         AS total_arr_at_risk,
    SUM(ca.expansion_signal_arr)                                AS total_expansion_signal_arr,

    -- cARR attainment rate = cARR / ARR (on mature accounts only)
    ROUND(
      SAFE_DIVIDE(
        SUM(ca.carr),
        SUM(CASE WHEN NOT ca.is_new_account THEN ca.annual_commit_dollars END)
      ), 4
    )                                                           AS carr_attainment_rate,

    -- Health tier breakdown (account counts)
    COUNTIF(ca.health_tier = 'Expansion')                       AS accounts_expansion,
    COUNTIF(ca.health_tier = 'Healthy')                         AS accounts_healthy,
    COUNTIF(ca.health_tier = 'At Risk')                         AS accounts_at_risk,
    COUNTIF(ca.health_tier = 'Shelfware')                       AS accounts_shelfware,
    COUNTIF(ca.health_tier = 'Inactive')                        AS accounts_inactive,
    COUNTIF(ca.health_tier = 'Ramping')                         AS accounts_ramping,

    -- ARR by health tier
    SUM(CASE WHEN ca.health_tier = 'Expansion'
        THEN ca.annual_commit_dollars ELSE 0 END)               AS arr_expansion,
    SUM(CASE WHEN ca.health_tier = 'Healthy'
        THEN ca.annual_commit_dollars ELSE 0 END)               AS arr_healthy,
    SUM(CASE WHEN ca.health_tier IN ('At Risk','Shelfware','Inactive')
        THEN ca.annual_commit_dollars ELSE 0 END)               AS arr_at_risk_tiers,

    -- Expansion pipeline
    COUNTIF(ca.expansion_flag)                                  AS expansion_opportunities,
    SUM(CASE WHEN ca.expansion_flag
        THEN ca.annual_commit_dollars ELSE 0 END)               AS expansion_arr_pipeline,

    -- Anomaly counts
    COUNTIF(ca.is_spike_drop)                                   AS spike_drop_accounts,
    COUNTIF(ca.has_expansion)                                   AS mid_year_expansion_accounts,

    -- Average consumption rate across mature portfolio
    ROUND(AVG(CASE WHEN NOT ca.is_new_account
              THEN ca.trailing_90d_avg_rate END), 4)            AS avg_consumption_rate,

    MAX(ca.as_of_date)                                          AS as_of_date,
    CURRENT_TIMESTAMP()                                         AS calculated_at

  FROM `openclaw-gateway-491103.gtm.carr_account` ca
  JOIN `openclaw-gateway-491103.raw.sales_reps` sr
    ON sr.employee_id = ca.employee_id
  GROUP BY
    ca.employee_id, sr.name, sr.region, sr.segment
)

SELECT
  *,
  -- Leaderboard rankings
  RANK() OVER (PARTITION BY region  ORDER BY total_carr DESC NULLS LAST) AS region_rank,
  RANK() OVER (                     ORDER BY total_carr DESC NULLS LAST) AS org_rank
FROM rep_metrics
ORDER BY total_carr DESC NULLS LAST
;
