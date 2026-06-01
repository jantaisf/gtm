# Prisma Cloud · cACV North Star Metric

**Consumed ACV (cACV)** is a prototype GTM metric for Palo Alto Networks Prisma Cloud's hybrid consumption model. It measures the portion of contracted ACV backed by actual platform usage — turning a bookings number into a leading indicator of renewal health and expansion pipeline.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://cacv-dashboard.streamlit.app)

---

## What's in this repo

| Path | Description |
|---|---|
| `specs/product_spec.md` | Metric definition, formula, compensation framework, open questions |
| `specs/technical_spec.md` | Medallion architecture (Bronze/Silver/Gold), star schema, pipeline logic |
| `data_generation/generate_data.py` | Synthetic data generator — 50 reps, 683 accounts, edge cases included |
| `pipeline_and_tests/sql/` | Five BigQuery SQL steps (dim_dates → silver → gold fact) |
| `pipeline_and_tests/run_pipeline.py` | Pipeline runner with `--as-of-date` and `--dry-run` flags |
| `pipeline_and_tests/dq_tests.py` | 11 automated data quality assertions |
| `dashboard/app.py` | Streamlit executive dashboard — 4 tabs, BigQuery + CSV demo mode |
| `dashboard/demo_data/` | Cached CSV snapshot for the live demo (no credentials required) |
| `comp_model.xlsx` | Spreadsheet model for AE/AM compensation under the cACV framework |

---

## Live Demo

The dashboard is deployed on Streamlit Community Cloud and runs on a committed CSV snapshot — no login or credentials required:

**[https://cacv-dashboard.streamlit.app](https://cacv-dashboard.streamlit.app)**

The demo shows:
- **Overview** — org-wide KPIs, cACV by region, health tier mix, attainment scatter by rep
- **By Region** — region comparison table + health tier stack chart
- **By Rep** — ranked leaderboard with ACV vs. cACV overlay, full rep table
- **Accounts** — per-account scatter (ACV vs. consumption rate), filterable by health tier

---

## Run Locally

### Prerequisites

- Python 3.10+
- GCP project with BigQuery enabled
- `gcloud auth application-default login`

### Setup

```bash
git clone https://github.com/jantaisf/gtm.git
cd gtm
pip install -r dashboard/requirements.txt
pip install -r data_generation/requirements.txt
```

### Generate data and run pipeline

```bash
# Generate synthetic data and upload to BigQuery
python3 data_generation/generate_data.py --upload

# Run full pipeline (Bronze → Silver → Gold)
python3 pipeline_and_tests/run_pipeline.py

# Run against a historical snapshot
python3 pipeline_and_tests/run_pipeline.py --as-of-date 2025-06-30

# Run data quality tests
python3 pipeline_and_tests/dq_tests.py
```

### Launch dashboard

```bash
streamlit run dashboard/app.py
```

The app connects to BigQuery automatically when GCP credentials are present. Without credentials it falls back to the committed CSV snapshot in `dashboard/demo_data/` — the same data powering the live demo.

---

## Architecture

```
Bronze (raw source tables)
  └── Silver (cleaned + conformed)
        └── Gold (dim_* + fact_cacv_snapshot)
              └── Semantic layer views (vw_rep_portfolio, vw_account_detail)
                    └── Dashboard · Salesforce · Comp Platform · BI
```

See `specs/technical_spec.md` for the full schema and pipeline documentation.

---

## Key metric

```
cACV = MIN(ACV × consumption_rate, ACV)

consumption_rate = trailing 90-day average of (monthly_credits_consumed / monthly_credit_allowance)
```

A rep with a $500K account at 4% consumption contributes $20K to cACV — not $500K. That's the point.
