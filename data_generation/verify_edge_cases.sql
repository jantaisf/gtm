-- ─────────────────────────────────────────────────────────────────────────────
-- Edge Case Verification Queries
-- Project: openclaw-gateway-491103 | Dataset: gtm
-- Run each block independently in the BigQuery console
-- ─────────────────────────────────────────────────────────────────────────────


-- ── [1] SPIKE & DROP ─────────────────────────────────────────────────────────
-- Accounts that burned heavily in Month 1 then went near-zero.
-- Expect: ~50 accounts (~5%)

SELECT
  account_id,
  ROUND(month_1_credits, 0)                             AS month_1_credits,
  ROUND(remaining_credits, 0)                           AS credits_months_2_to_12,
  ROUND(month_1_credits / NULLIF(total_credits, 0), 2)  AS month_1_share
FROM (
  SELECT
    account_id,
    SUM(CASE WHEN DATE_TRUNC(date, MONTH) = '2024-01-01' THEN compute_credits_consumed ELSE 0 END) AS month_1_credits,
    SUM(CASE WHEN DATE_TRUNC(date, MONTH) > '2024-01-01'  THEN compute_credits_consumed ELSE 0 END) AS remaining_credits,
    SUM(compute_credits_consumed) AS total_credits
  FROM `openclaw-gateway-491103.gtm.daily_usage_logs`
  GROUP BY account_id
)
WHERE month_1_credits / NULLIF(total_credits, 0) > 0.80   -- Month 1 = 80%+ of all usage
  AND remaining_credits < 100                               -- Near-zero after
ORDER BY month_1_share DESC;


-- ── [2] SHELFWARE ─────────────────────────────────────────────────────────────
-- Accounts with an active contract but zero usage logs.
-- Expect: ~100 accounts (~10%)

SELECT
  a.account_id,
  a.company_name,
  a.industry,
  c.annual_commit_dollars,
  c.included_monthly_compute_credits
FROM `openclaw-gateway-491103.gtm.accounts` a
JOIN `openclaw-gateway-491103.gtm.contracts` c
  ON c.account_id = a.account_id
LEFT JOIN `openclaw-gateway-491103.gtm.daily_usage_logs` l
  ON l.account_id = a.account_id
WHERE l.account_id IS NULL
ORDER BY c.annual_commit_dollars DESC;


-- ── [3] CONSISTENT OVERAGES ───────────────────────────────────────────────────
-- Accounts that consumed 120%+ of their monthly credit allowance
-- in the majority of months they were active.
-- Expect: ~150 accounts (~15%)

WITH monthly_consumption AS (
  SELECT
    l.account_id,
    DATE_TRUNC(l.date, MONTH)                        AS usage_month,
    SUM(l.compute_credits_consumed)                  AS credits_consumed,
    MAX(c.included_monthly_compute_credits)          AS monthly_allowance
  FROM `openclaw-gateway-491103.gtm.daily_usage_logs` l
  JOIN `openclaw-gateway-491103.gtm.contracts` c
    ON  c.account_id = l.account_id
    AND l.date BETWEEN c.start_date AND c.end_date
  GROUP BY 1, 2
),
overage_summary AS (
  SELECT
    account_id,
    COUNT(*)                                              AS active_months,
    COUNTIF(credits_consumed > monthly_allowance * 1.20) AS overage_months,
    ROUND(AVG(credits_consumed / NULLIF(monthly_allowance, 0)), 2) AS avg_consumption_rate
  FROM monthly_consumption
  GROUP BY account_id
)
SELECT
  account_id,
  active_months,
  overage_months,
  avg_consumption_rate
FROM overage_summary
WHERE overage_months >= active_months * 0.5   -- overage in majority of months
ORDER BY avg_consumption_rate DESC;


-- ── [4] MID-YEAR EXPANSIONS ───────────────────────────────────────────────────
-- Accounts with more than one contract where the dates overlap.
-- Expect: ~50 accounts (~5%)

SELECT
  c1.account_id,
  c1.contract_id                  AS contract_1,
  c1.start_date                   AS c1_start,
  c1.end_date                     AS c1_end,
  c1.annual_commit_dollars        AS c1_arr,
  c2.contract_id                  AS contract_2,
  c2.start_date                   AS c2_start,
  c2.end_date                     AS c2_end,
  c2.annual_commit_dollars        AS c2_arr
FROM `openclaw-gateway-491103.gtm.contracts` c1
JOIN `openclaw-gateway-491103.gtm.contracts` c2
  ON  c2.account_id  = c1.account_id
  AND c2.contract_id > c1.contract_id        -- avoid duplicate pairs
  AND c2.start_date <= c1.end_date           -- dates overlap
  AND c2.end_date   >= c1.start_date
ORDER BY c1.account_id;


-- ── [5a] ORPHANED USAGE — ghost account_ids ───────────────────────────────────
-- Logs where account_id does not exist in the Accounts table.
-- Expect: ~150 rows

SELECT
  l.account_id,
  COUNT(*)                              AS orphan_log_count,
  MIN(l.date)                           AS earliest_log,
  MAX(l.date)                           AS latest_log,
  ROUND(SUM(l.compute_credits_consumed), 0) AS total_credits
FROM `openclaw-gateway-491103.gtm.daily_usage_logs` l
LEFT JOIN `openclaw-gateway-491103.gtm.accounts` a
  ON a.account_id = l.account_id
WHERE a.account_id IS NULL
GROUP BY l.account_id
ORDER BY orphan_log_count DESC;


-- ── [5b] ROGUE USAGE — dates outside contract window ─────────────────────────
-- Logs for valid accounts but where the date falls outside all their contracts.
-- Expect: ~150 rows

SELECT
  l.log_id,
  l.account_id,
  l.date,
  l.compute_credits_consumed
FROM `openclaw-gateway-491103.gtm.daily_usage_logs` l
INNER JOIN `openclaw-gateway-491103.gtm.accounts` a
  ON a.account_id = l.account_id        -- account exists
WHERE NOT EXISTS (
  SELECT 1
  FROM `openclaw-gateway-491103.gtm.contracts` c
  WHERE c.account_id = l.account_id
    AND l.date BETWEEN c.start_date AND c.end_date
)
ORDER BY l.account_id, l.date;


-- ── SUMMARY SCORECARD ─────────────────────────────────────────────────────────
-- One-shot view of all edge case counts vs. expectations.

SELECT 'Spike & Drop'       AS edge_case, COUNT(*) AS count, '~50'  AS expected FROM (
  SELECT account_id FROM (
    SELECT account_id,
      SUM(CASE WHEN DATE_TRUNC(date, MONTH) = '2024-01-01' THEN compute_credits_consumed ELSE 0 END) AS m1,
      SUM(compute_credits_consumed) AS total
    FROM `openclaw-gateway-491103.gtm.daily_usage_logs` GROUP BY 1
  ) WHERE m1 / NULLIF(total, 0) > 0.80 AND (total - m1) < 100
)
UNION ALL
SELECT 'Shelfware', COUNT(*), '~100' FROM (
  SELECT a.account_id FROM `openclaw-gateway-491103.gtm.accounts` a
  LEFT JOIN `openclaw-gateway-491103.gtm.daily_usage_logs` l ON l.account_id = a.account_id
  WHERE l.account_id IS NULL GROUP BY 1
)
UNION ALL
SELECT 'Orphaned Logs (ghost IDs)', COUNT(*), '~150' FROM (
  SELECT l.log_id FROM `openclaw-gateway-491103.gtm.daily_usage_logs` l
  LEFT JOIN `openclaw-gateway-491103.gtm.accounts` a ON a.account_id = l.account_id
  WHERE a.account_id IS NULL
)
UNION ALL
SELECT 'Rogue Logs (out-of-contract)', COUNT(*), '~150' FROM (
  SELECT l.log_id FROM `openclaw-gateway-491103.gtm.daily_usage_logs` l
  INNER JOIN `openclaw-gateway-491103.gtm.accounts` a ON a.account_id = l.account_id
  WHERE NOT EXISTS (
    SELECT 1 FROM `openclaw-gateway-491103.gtm.contracts` c
    WHERE c.account_id = l.account_id AND l.date BETWEEN c.start_date AND c.end_date
  )
)
UNION ALL
SELECT 'Mid-Year Expansions (accounts)', COUNT(*), '~50' FROM (
  SELECT DISTINCT c1.account_id FROM `openclaw-gateway-491103.gtm.contracts` c1
  JOIN `openclaw-gateway-491103.gtm.contracts` c2
    ON c2.account_id = c1.account_id AND c2.contract_id > c1.contract_id
    AND c2.start_date <= c1.end_date AND c2.end_date >= c1.start_date
);
