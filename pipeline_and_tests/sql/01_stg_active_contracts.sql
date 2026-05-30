-- ─────────────────────────────────────────────────────────────────────────────
-- 01_stg_active_contracts.sql
-- Resolves the canonical active contract per account as of {as_of_date}.
--
-- Edge cases handled:
--   · Mid-year expansions: accounts with multiple simultaneously active
--     contracts (additive expansion — customer added new workloads under a
--     separate contract). ARR = SUM across all active contracts.
--     Credits = SUM across all active contracts.
--     Primary contract = earliest start_date (for reference/comp attribution).
--   · Malformed contracts (end_date < start_date): excluded.
--
-- Output: one row per account with at least one active contract.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE TABLE `openclaw-gateway-491103.staging.stg_active_contracts` AS

WITH active_contracts AS (
  SELECT
    c.contract_id,
    c.account_id,
    c.owner_id,
    c.start_date,
    c.end_date,
    c.annual_commit_dollars,
    c.included_monthly_compute_credits,
    c.contract_term_months,
    -- Rank by start_date to identify the original (primary) contract
    ROW_NUMBER() OVER (
      PARTITION BY c.account_id
      ORDER BY c.start_date ASC, c.contract_id ASC
    ) AS contract_rank
  FROM `openclaw-gateway-491103.raw.contracts` c
  WHERE
    c.end_date   >= c.start_date              -- exclude malformed
    AND c.start_date <= {as_of_date}
    AND c.end_date   >= {as_of_date}
),

-- Primary contract = original (earliest start) — used for reference fields only
primary_contracts AS (
  SELECT
    account_id,
    contract_id  AS primary_contract_id,
    owner_id     AS signing_owner_id,
    start_date   AS contract_start_date,
    end_date     AS contract_end_date,
    contract_term_months
  FROM active_contracts
  WHERE contract_rank = 1
),

-- Aggregate across ALL simultaneously active contracts
combined_totals AS (
  SELECT
    account_id,
    SUM(annual_commit_dollars)            AS annual_commit_dollars,
    SUM(included_monthly_compute_credits) AS included_monthly_compute_credits,
    COUNT(*)                              AS active_contract_count
  FROM active_contracts
  GROUP BY account_id
)

SELECT
  p.account_id,
  a.employee_id,                    -- current account owner (may differ from signing owner)
  p.signing_owner_id,          -- rep who owned the account when original contract was signed
  a.company_name,
  a.industry,
  p.primary_contract_id,
  p.contract_start_date,
  p.contract_end_date,
  ct.annual_commit_dollars,    -- SUM across all active contracts
  p.contract_term_months,
  ct.included_monthly_compute_credits,  -- SUM across all active contracts
  ct.active_contract_count,
  CASE WHEN ct.active_contract_count > 1 THEN TRUE ELSE FALSE END AS has_expansion
FROM primary_contracts p
JOIN combined_totals   ct USING (account_id)
JOIN `openclaw-gateway-491103.raw.accounts` a
  ON a.account_id = p.account_id
;
