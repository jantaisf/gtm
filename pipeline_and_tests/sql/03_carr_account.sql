-- ─────────────────────────────────────────────────────────────────────────────
-- 03_carr_account.sql
-- Computes account-level Consumed ARR (cARR).
--
-- Formula (product_spec.md §2.2):
--   cARR = annual_commit_dollars × trailing_90d_avg_consumption_rate
--
-- Edge cases handled:
--   · New accounts (<90 days): excluded from cARR, flagged as ramping.
--   · Spike & Drop: trailing 90-day window smooths spike once it ages out.
--   · Shelfware: 0 consumption rate → near-zero cARR.
--   · Consistent Overages: cARR > ARR; expansion_flag surfaced to rep.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE TABLE `openclaw-gateway-491103.gtm.carr_account` AS

WITH

-- Trailing 90-day window = last 3 complete calendar months
trailing_window AS (
  SELECT
    account_id,
    usage_month,
    consumption_rate,
    is_zero_usage_month,
    ROW_NUMBER() OVER (
      PARTITION BY account_id
      ORDER BY usage_month DESC
    ) AS month_rank
  FROM `openclaw-gateway-491103.gtm.stg_monthly_consumption`
),

trailing_stats AS (
  SELECT
    account_id,
    AVG(consumption_rate)        AS trailing_90d_avg_rate,
    COUNT(*)                     AS months_of_data,
    MAX(consumption_rate)        AS max_monthly_rate,
    MIN(consumption_rate)        AS min_monthly_rate,
    COUNTIF(consumption_rate > 1.2) AS overage_months,
    COUNTIF(is_zero_usage_month)    AS zero_usage_months
  FROM trailing_window
  WHERE month_rank <= 3
  GROUP BY account_id
),

health_classification AS (
  SELECT
    ts.account_id,
    ts.trailing_90d_avg_rate,
    ts.months_of_data,
    ts.max_monthly_rate,
    ts.min_monthly_rate,
    ts.overage_months,
    ts.zero_usage_months,

    -- Health tier (product_spec.md §4)
    CASE
      WHEN ts.trailing_90d_avg_rate > 1.20                      THEN 'Expansion'
      WHEN ts.trailing_90d_avg_rate BETWEEN 0.80 AND 1.20       THEN 'Healthy'
      WHEN ts.trailing_90d_avg_rate BETWEEN 0.40 AND 0.80       THEN 'At Risk'
      WHEN ts.trailing_90d_avg_rate BETWEEN 0.05 AND 0.40       THEN 'Shelfware'
      ELSE                                                            'Inactive'
    END AS health_tier,

    -- Expansion flag: consistently over commit for 2+ months
    CASE WHEN ts.overage_months >= 2 THEN TRUE ELSE FALSE END AS expansion_flag,

    -- Spike & drop: massive Month 1 spike, now near-zero
    CASE
      WHEN ts.max_monthly_rate > 2.0 AND ts.trailing_90d_avg_rate < 0.05
      THEN TRUE ELSE FALSE
    END AS is_spike_drop,

    -- Low data flag: fewer than 2 months of history
    CASE WHEN ts.months_of_data < 2 THEN TRUE ELSE FALSE END AS low_data_flag

  FROM trailing_stats ts
)

SELECT
  ac.account_id,
  ac.rep_id,
  ac.company_name,
  ac.industry,
  ac.primary_contract_id,
  ac.contract_start_date,
  ac.contract_end_date,
  ac.contract_term_years,
  ac.annual_commit_dollars,
  ac.included_monthly_compute_credits,
  ac.has_expansion,
  ac.active_contract_count,

  hc.trailing_90d_avg_rate,
  hc.months_of_data,
  hc.max_monthly_rate,
  hc.overage_months,
  hc.zero_usage_months,
  hc.expansion_flag,
  hc.is_spike_drop,
  hc.low_data_flag,

  -- New account flag: contract started within 90 days of as_of_date
  CASE
    WHEN ac.contract_start_date >= DATE_SUB({as_of_date}, INTERVAL 90 DAY)
    THEN TRUE ELSE FALSE
  END AS is_new_account,

  -- Health tier (NULL for new accounts — not enough history)
  CASE
    WHEN ac.contract_start_date >= DATE_SUB({as_of_date}, INTERVAL 90 DAY)
    THEN 'Ramping'
    ELSE hc.health_tier
  END AS health_tier,

  -- cARR: NULL for new accounts, direct multiplication for all others
  CASE
    WHEN ac.contract_start_date >= DATE_SUB({as_of_date}, INTERVAL 90 DAY)
    THEN NULL
    ELSE ROUND(ac.annual_commit_dollars * hc.trailing_90d_avg_rate, 2)
  END AS carr,

  -- ARR at risk = committed dollars not backed by consumption
  CASE
    WHEN ac.contract_start_date >= DATE_SUB({as_of_date}, INTERVAL 90 DAY)
    THEN NULL
    ELSE ROUND(
      ac.annual_commit_dollars - (ac.annual_commit_dollars * hc.trailing_90d_avg_rate), 2
    )
  END AS arr_at_risk,

  {as_of_date}        AS as_of_date,
  CURRENT_TIMESTAMP() AS calculated_at

FROM `openclaw-gateway-491103.gtm.stg_active_contracts` ac
LEFT JOIN health_classification hc
  ON hc.account_id = ac.account_id
;
