-- ─────────────────────────────────────────────────────────────────────────────
-- 07_vw_comp_input.sql
-- Semantic layer view: compensation-ready monthly cACV per rep.
--
-- Consumers: Compensation platform (service account only — least-privilege access)
-- Grain:     One row per rep per as_of_date (monthly pipeline run)
-- Spec ref:  technical_spec.md §14.1, §14.2
--
-- Design notes:
--   · Ramping accounts (is_new_account = TRUE) are EXCLUDED from all figures.
--     Including them would produce NULL cacv values (not yet mature), which would
--     understate attainment and trigger incorrect commission clawbacks.
--   · pipeline_run_id is surfaced for audit traceability:
--       commission record → vw_comp_input row → cacv_account row → pipeline_run_log
--   · This view is intentionally narrow — only the columns the comp platform
--     needs. It does not expose account-level detail or anomaly flags.
--   · Finance locks comp periods by snapshotting this view at month-end:
--       SELECT * FROM gold.vw_comp_input WHERE as_of_date = '2025-06-30'
--     The result is immutable once saved to the comp platform.
--   · Access: grant SELECT to the comp platform service account only.
--     Revoke all other principals. (See technical_spec.md §14.2.)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW `openclaw-gateway-491103.gold.vw_comp_input` AS

SELECT
  -- ── Rep identifiers ──────────────────────────────────────────────────────
  ca.employee_id,
  sr.name        AS rep_name,
  sr.region,
  sr.segment,
  sr.manager_id,

  -- ── Comp period ──────────────────────────────────────────────────────────
  ca.as_of_date,

  -- ── Core comp metrics (mature accounts only) ──────────────────────────────
  -- Ramping accounts filtered in WHERE clause below
  COUNT(*)                                                        AS total_mature_accounts,

  -- Attainment denominator: ACV of mature accounts only
  SUM(ca.annual_commit_dollars)                                   AS total_acv,

  -- Attainment numerator: sum of cACV (capped at ACV per account)
  SUM(ca.cacv)                                                    AS total_cacv,

  -- Attainment rate: the figure used for commission tier calculation
  ROUND(
    SAFE_DIVIDE(SUM(ca.cacv), SUM(ca.annual_commit_dollars)), 4
  )                                                               AS cacv_attainment_rate,

  -- ACV at risk (informational — not used in comp calculation but useful
  -- for Finance reconciliation and disputed comp reviews)
  SUM(ca.acv_at_risk)                                             AS total_acv_at_risk,

  -- Consumption overage: revenue above the ACV cap (treated as upside/bonus
  -- pipeline, not base attainment — comp platform applies its own overage rate)
  SUM(ca.expansion_signal_acv)                                    AS total_consumption_overage_acv,

  -- ── Audit trail ──────────────────────────────────────────────────────────
  -- Ties each comp record back to the specific pipeline run that produced it.
  -- Required for dispute resolution and correction tracking (spec §10.3).
  MAX(ca.calculated_at)                                           AS pipeline_run_at,

  CURRENT_TIMESTAMP()                                             AS refreshed_at

FROM `openclaw-gateway-491103.gtm.cacv_account` ca
JOIN `openclaw-gateway-491103.raw.sales_reps`   sr
  ON sr.employee_id = ca.employee_id

-- ── Ramping exclusion ────────────────────────────────────────────────────────
-- Accounts in their first 90 days have no consumption history and a NULL cacv.
-- Excluding them ensures attainment_rate is calculated only over mature accounts.
WHERE ca.is_new_account = FALSE

GROUP BY
  ca.employee_id, sr.name, sr.region, sr.segment, sr.manager_id, ca.as_of_date

ORDER BY
  ca.as_of_date DESC,
  cacv_attainment_rate DESC NULLS LAST
;
