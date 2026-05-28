-- ─────────────────────────────────────────────────────────────────────────────
-- 02_stg_monthly_consumption.sql
-- Aggregates daily usage logs to monthly consumption per account.
--
-- Edge cases handled:
--   · Orphaned usage: INNER JOIN to accounts excludes ghost account_ids.
--   · Out-of-contract usage: JOIN requires log date within a contract window.
--   · Shelfware (zero logs): LEFT JOIN from contract months produces 0 consumption.
--   · Consumption rate capped at 2.0 to prevent extreme outliers skewing averages.
--
-- Output: one row per account per calendar month.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE TABLE `openclaw-gateway-491103.staging.stg_monthly_consumption` AS

WITH

-- Valid logs only: account must exist AND date must be within a contract window
clean_logs AS (
  SELECT
    l.account_id,
    l.date,
    l.compute_credits_consumed
  FROM `openclaw-gateway-491103.raw.daily_usage_logs` l
  -- Orphan guard: account must exist in accounts table
  INNER JOIN `openclaw-gateway-491103.raw.accounts` a
    ON a.account_id = l.account_id
  -- Out-of-contract guard: date must fall within at least one contract window
  INNER JOIN `openclaw-gateway-491103.raw.contracts` c
    ON  c.account_id = l.account_id
    AND l.date BETWEEN c.start_date AND c.end_date
    AND c.end_date >= c.start_date
),

-- Monthly usage aggregation
monthly_usage AS (
  SELECT
    account_id,
    DATE_TRUNC(date, MONTH)       AS usage_month,
    SUM(compute_credits_consumed) AS credits_consumed,
    COUNT(DISTINCT date)          AS active_usage_days
  FROM clean_logs
  GROUP BY 1, 2
),

-- Expand each contract into monthly rows (for shelfware LEFT JOIN)
contract_months AS (
  SELECT
    c.account_id,
    DATE_TRUNC(month_dt, MONTH)              AS contract_month,
    c.included_monthly_compute_credits
  FROM `openclaw-gateway-491103.raw.contracts` c
  CROSS JOIN UNNEST(
    GENERATE_DATE_ARRAY(
      DATE_TRUNC(c.start_date, MONTH),
      DATE_TRUNC(c.end_date,   MONTH),
      INTERVAL 1 MONTH
    )
  ) AS month_dt
  WHERE c.end_date >= c.start_date
)

SELECT
  cm.account_id,
  cm.contract_month                                                       AS usage_month,
  cm.included_monthly_compute_credits,
  COALESCE(mu.credits_consumed, 0)                                        AS credits_consumed,
  COALESCE(mu.active_usage_days, 0)                                       AS active_usage_days,
  -- Consumption rate: actual / allowance, capped at 2.0
  LEAST(
    SAFE_DIVIDE(COALESCE(mu.credits_consumed, 0), cm.included_monthly_compute_credits),
    2.0
  )                                                                       AS consumption_rate,
  CASE WHEN COALESCE(mu.credits_consumed, 0) = 0 THEN TRUE ELSE FALSE END AS is_zero_usage_month
FROM contract_months cm
LEFT JOIN monthly_usage mu
  ON  mu.account_id  = cm.account_id
  AND mu.usage_month = cm.contract_month
;
