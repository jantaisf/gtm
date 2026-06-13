-- ─────────────────────────────────────────────────────────────────────────────
-- 09_vw_org_summary.sql
-- Semantic layer view: org-level and regional Consumption ACV summary.
--
-- Consumers: CFO, Finance, Board, Regional VPs
-- Grain:     One row per rollup_level per as_of_date
--              rollup_level = 'region'    → one row per region
--              rollup_level = 'org_total' → one row for the full portfolio
-- Spec ref:  technical_spec.md §14.1
--
-- Design notes:
--   · Uses UNION ALL of region-level and org-total aggregations to produce a
--     single view that BI tools can filter with: WHERE rollup_level = 'region'
--     for regional views or rollup_level = 'org_total' for board decks.
--   · Intentionally excludes rep_name and employee_id. Finance and the CFO
--     see aggregate data only; rep-level detail requires explicit access grant
--     to vw_rep_portfolio (see technical_spec.md §14.2).
--   · Ramping accounts are excluded from the attainment denominator (total_acv)
--     to match the methodology in vw_rep_portfolio and vw_comp_input.
--   · attainment_rate is rounded to 4 decimal places to match precision
--     used throughout the pipeline (e.g., 0.7456 = 74.56%).
--   · NRR_leading_indicator = total_cacv / total_acv interpreted at portfolio
--     level. Not a true NRR calculation (which requires cohort tracking) but
--     a directional leading indicator aligned with the North Star metric.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW `openclaw-gateway-491103.gold.vw_org_summary` AS

WITH

base AS (
  SELECT
    ca.region,
    ca.as_of_date,

    -- Totals (mature accounts only for attainment denominator)
    COUNTIF(NOT ca.is_new_account)                                AS total_mature_accounts,
    COUNTIF(ca.is_new_account)                                    AS total_ramping_accounts,
    COUNT(*)                                                      AS total_accounts,

    SUM(CASE WHEN NOT ca.is_new_account
             THEN ca.annual_commit_dollars ELSE 0 END)            AS total_acv,
    SUM(ca.cacv)                                                  AS total_cacv,
    SUM(ca.acv_at_risk)                                           AS total_acv_at_risk,
    SUM(ca.expansion_signal_acv)                                  AS total_consumption_overage_acv,

    ROUND(
      SAFE_DIVIDE(
        SUM(ca.cacv),
        SUM(CASE WHEN NOT ca.is_new_account THEN ca.annual_commit_dollars END)
      ), 4
    )                                                             AS attainment_rate,

    -- Health tier counts
    COUNTIF(ca.health_tier = 'Expansion')                         AS accounts_expansion,
    COUNTIF(ca.health_tier = 'Healthy')                           AS accounts_healthy,
    COUNTIF(ca.health_tier = 'At Risk')                           AS accounts_at_risk,
    COUNTIF(ca.health_tier = 'Shelfware')                         AS accounts_shelfware,
    COUNTIF(ca.health_tier = 'Inactive')                          AS accounts_inactive,
    COUNTIF(ca.health_tier = 'Ramping')                           AS accounts_ramping_tier,

    -- ACV by tier (for board-level waterfall charts)
    SUM(CASE WHEN ca.health_tier = 'Expansion'
             THEN ca.annual_commit_dollars ELSE 0 END)            AS acv_expansion,
    SUM(CASE WHEN ca.health_tier = 'Healthy'
             THEN ca.annual_commit_dollars ELSE 0 END)            AS acv_healthy,
    SUM(CASE WHEN ca.health_tier IN ('At Risk', 'Shelfware', 'Inactive')
             THEN ca.annual_commit_dollars ELSE 0 END)            AS acv_at_risk_tiers,

    COUNT(DISTINCT ca.employee_id)                                AS total_reps,
    CURRENT_TIMESTAMP()                                           AS refreshed_at

  FROM `openclaw-gateway-491103.gtm.cacv_account` ca
  JOIN `openclaw-gateway-491103.raw.sales_reps`   sr
    ON sr.employee_id = ca.employee_id
  GROUP BY ca.region, ca.as_of_date
),

-- ── Regional rollup ──────────────────────────────────────────────────────────
regional AS (
  SELECT
    'region'         AS rollup_level,
    region           AS region,
    as_of_date,
    total_acv,       total_cacv,          total_acv_at_risk,
    total_consumption_overage_acv,
    attainment_rate,
    total_accounts,  total_mature_accounts, total_ramping_accounts,
    accounts_expansion, accounts_healthy, accounts_at_risk,
    accounts_shelfware, accounts_inactive,  accounts_ramping_tier,
    acv_expansion,   acv_healthy,         acv_at_risk_tiers,
    total_reps,
    refreshed_at
  FROM base
),

-- ── Org total rollup ─────────────────────────────────────────────────────────
org_total AS (
  SELECT
    'org_total'      AS rollup_level,
    'All Regions'    AS region,
    as_of_date,
    SUM(total_acv)                                                AS total_acv,
    SUM(total_cacv)                                               AS total_cacv,
    SUM(total_acv_at_risk)                                        AS total_acv_at_risk,
    SUM(total_consumption_overage_acv)                            AS total_consumption_overage_acv,
    ROUND(
      SAFE_DIVIDE(SUM(total_cacv), SUM(total_acv)), 4
    )                                                             AS attainment_rate,
    SUM(total_accounts)                                           AS total_accounts,
    SUM(total_mature_accounts)                                    AS total_mature_accounts,
    SUM(total_ramping_accounts)                                   AS total_ramping_accounts,
    SUM(accounts_expansion)                                       AS accounts_expansion,
    SUM(accounts_healthy)                                         AS accounts_healthy,
    SUM(accounts_at_risk)                                         AS accounts_at_risk,
    SUM(accounts_shelfware)                                       AS accounts_shelfware,
    SUM(accounts_inactive)                                        AS accounts_inactive,
    SUM(accounts_ramping_tier)                                    AS accounts_ramping_tier,
    SUM(acv_expansion)                                            AS acv_expansion,
    SUM(acv_healthy)                                              AS acv_healthy,
    SUM(acv_at_risk_tiers)                                        AS acv_at_risk_tiers,
    SUM(total_reps)                                               AS total_reps,
    MAX(refreshed_at)                                             AS refreshed_at
  FROM base
  GROUP BY as_of_date
)

SELECT * FROM regional
UNION ALL
SELECT * FROM org_total

ORDER BY
  as_of_date     DESC,
  rollup_level   ASC,   -- 'org_total' sorts before 'region' alphabetically → flip in BI tool if needed
  attainment_rate DESC
;
