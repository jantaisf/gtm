-- ─────────────────────────────────────────────────────────────────────────────
-- 01_stg_active_contracts.sql
-- Resolves the canonical active contract per account as of {as_of_date}.
--
-- Edge cases handled:
--   · Mid-year expansions: accounts with multiple simultaneously active
--     contracts. ARR basis = highest annual_commit_dollars contract.
--     Monthly credits = SUM across ALL active contracts.
--   · Malformed contracts (end_date < start_date): excluded.
--
-- Output: one row per account with at least one active contract.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE TABLE `openclaw-gateway-491103.staging.stg_active_contracts` AS

WITH active_contracts AS (
  SELECT
    c.contract_id,
    c.account_id,
    c.start_date,
    c.end_date,
    c.annual_commit_dollars,
    c.included_monthly_compute_credits,
    c.contract_term_months,
    -- Rank contracts per account by ARR desc to identify primary (highest value)
    ROW_NUMBER() OVER (
      PARTITION BY c.account_id
      ORDER BY c.annual_commit_dollars DESC, c.start_date ASC
    ) AS contract_rank
  FROM `openclaw-gateway-491103.raw.contracts` c
  WHERE
    c.end_date   >= c.start_date              -- exclude malformed
    AND c.start_date <= {as_of_date}
    AND c.end_date   >= {as_of_date}
),

-- ARR basis: highest-value active contract per account
primary_contracts AS (
  SELECT
    account_id,
    contract_id             AS primary_contract_id,
    start_date              AS contract_start_date,
    end_date                AS contract_end_date,
    annual_commit_dollars,
    contract_term_months
  FROM active_contracts
  WHERE contract_rank = 1
),

-- Total monthly credits: sum across ALL simultaneously active contracts
combined_credits AS (
  SELECT
    account_id,
    SUM(included_monthly_compute_credits) AS included_monthly_compute_credits,
    COUNT(*)                               AS active_contract_count
  FROM active_contracts
  GROUP BY account_id
)

SELECT
  p.account_id,
  a.rep_id,
  a.company_name,
  a.industry,
  p.primary_contract_id,
  p.contract_start_date,
  p.contract_end_date,
  p.annual_commit_dollars,
  p.contract_term_months,
  cc.included_monthly_compute_credits,
  cc.active_contract_count,
  CASE WHEN cc.active_contract_count > 1 THEN TRUE ELSE FALSE END AS has_expansion
FROM primary_contracts      p
JOIN combined_credits        cc USING (account_id)
JOIN `openclaw-gateway-491103.raw.accounts` a
  ON a.account_id = p.account_id
;
