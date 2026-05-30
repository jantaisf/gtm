-- ─────────────────────────────────────────────────────────────────────────────
-- 00_dim_dates.sql
-- Calendar dimension table covering 2000-01-01 through current date.
--
-- Includes:
--   · Standard calendar fields (year, quarter, month, week, day)
--   · Day-of-week flags (is_weekday, is_weekend)
--   · PANW fiscal calendar (FY ends July 31; FY2025 = Aug 2024 → Jul 2025)
--   · Convenience labels (month_name, day_name, year_month, etc.)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE TABLE `openclaw-gateway-491103.gtm.dim_dates` AS

SELECT

  -- ── Primary key ────────────────────────────────────────────────────────────
  date,
  CAST(FORMAT_DATE('%Y%m%d', date) AS INT64)          AS date_id,        -- e.g. 20260101

  -- ── Calendar year ──────────────────────────────────────────────────────────
  EXTRACT(YEAR    FROM date)                           AS year,
  EXTRACT(QUARTER FROM date)                           AS quarter,
  CONCAT(CAST(EXTRACT(YEAR FROM date) AS STRING),
         '-Q', CAST(EXTRACT(QUARTER FROM date) AS STRING))
                                                       AS year_quarter,   -- e.g. 2026-Q1
  EXTRACT(MONTH   FROM date)                           AS month,
  FORMAT_DATE('%B', date)                              AS month_name,     -- e.g. January
  FORMAT_DATE('%b', date)                              AS month_short,    -- e.g. Jan
  FORMAT_DATE('%Y-%m', date)                           AS year_month,     -- e.g. 2026-01
  EXTRACT(WEEK    FROM date)                           AS week_of_year,
  EXTRACT(DAYOFYEAR FROM date)                         AS day_of_year,
  EXTRACT(DAY     FROM date)                           AS day_of_month,

  -- ── Day of week ────────────────────────────────────────────────────────────
  -- BigQuery DAYOFWEEK: 1 = Sunday, 7 = Saturday
  EXTRACT(DAYOFWEEK FROM date)                         AS day_of_week,
  FORMAT_DATE('%A', date)                              AS day_name,       -- e.g. Monday
  FORMAT_DATE('%a', date)                              AS day_short,      -- e.g. Mon
  CASE WHEN EXTRACT(DAYOFWEEK FROM date) IN (1, 7)
       THEN TRUE ELSE FALSE END                        AS is_weekend,
  CASE WHEN EXTRACT(DAYOFWEEK FROM date) NOT IN (1, 7)
       THEN TRUE ELSE FALSE END                        AS is_weekday,

  -- ── Month start / end flags ─────────────────────────────────────────────────
  CASE WHEN date = DATE_TRUNC(date, MONTH)
       THEN TRUE ELSE FALSE END                        AS is_month_start,
  CASE WHEN date = LAST_DAY(date, MONTH)
       THEN TRUE ELSE FALSE END                        AS is_month_end,
  DATE_TRUNC(date, MONTH)                              AS month_start_date,
  LAST_DAY(date, MONTH)                                AS month_end_date,

  -- ── Quarter start / end flags ───────────────────────────────────────────────
  CASE WHEN date = DATE_TRUNC(date, QUARTER)
       THEN TRUE ELSE FALSE END                        AS is_quarter_start,
  CASE WHEN date = LAST_DAY(date, QUARTER)
       THEN TRUE ELSE FALSE END                        AS is_quarter_end,

  -- ── Calendar year / quarter (explicit aliases for symmetry with fiscal_*) ───
  EXTRACT(YEAR    FROM date)                           AS calendar_year,
  EXTRACT(QUARTER FROM date)                           AS calendar_quarter,
  CONCAT(CAST(EXTRACT(YEAR FROM date) AS STRING),
         '-Q', CAST(EXTRACT(QUARTER FROM date) AS STRING))
                                                       AS calendar_year_quarter, -- e.g. 2026-Q1

  -- ── PANW fiscal calendar (FY ends July 31) ──────────────────────────────────
  -- FY2025 = Aug 1 2024 → Jul 31 2025
  -- Fiscal month 1 = August, fiscal month 12 = July
  CASE WHEN EXTRACT(MONTH FROM date) >= 8
       THEN EXTRACT(YEAR FROM date) + 1
       ELSE EXTRACT(YEAR FROM date)
  END                                                  AS fiscal_year,

  CONCAT('FY', CAST(
    CASE WHEN EXTRACT(MONTH FROM date) >= 8
         THEN EXTRACT(YEAR FROM date) + 1
         ELSE EXTRACT(YEAR FROM date)
    END AS STRING))                                    AS fiscal_year_name, -- e.g. FY2025

  -- Fiscal month: Aug=1, Sep=2, Oct=3, Nov=4, Dec=5, Jan=6,
  --               Feb=7, Mar=8, Apr=9, May=10, Jun=11, Jul=12
  MOD(EXTRACT(MONTH FROM date) + 4, 12) + 1           AS fiscal_month,

  -- Fiscal quarter: Aug-Oct=Q1, Nov-Jan=Q2, Feb-Apr=Q3, May-Jul=Q4
  CASE
    WHEN EXTRACT(MONTH FROM date) IN (8, 9, 10)  THEN 1
    WHEN EXTRACT(MONTH FROM date) IN (11, 12, 1) THEN 2
    WHEN EXTRACT(MONTH FROM date) IN (2, 3, 4)   THEN 3
    WHEN EXTRACT(MONTH FROM date) IN (5, 6, 7)   THEN 4
  END                                                  AS fiscal_quarter,

  CONCAT(
    'FY', CAST(
      CASE WHEN EXTRACT(MONTH FROM date) >= 8
           THEN EXTRACT(YEAR FROM date) + 1
           ELSE EXTRACT(YEAR FROM date)
      END AS STRING),
    '-Q',
    CAST(CASE
      WHEN EXTRACT(MONTH FROM date) IN (8, 9, 10)  THEN 1
      WHEN EXTRACT(MONTH FROM date) IN (11, 12, 1) THEN 2
      WHEN EXTRACT(MONTH FROM date) IN (2, 3, 4)   THEN 3
      WHEN EXTRACT(MONTH FROM date) IN (5, 6, 7)   THEN 4
    END AS STRING))                                    AS fiscal_year_quarter -- e.g. FY2025-Q1

FROM UNNEST(
  GENERATE_DATE_ARRAY('2000-01-01', '2030-12-31')
) AS date
ORDER BY date
;
