# Product Spec: Consumed ARR (cARR)
## North Star Metric for Prisma Cloud GTM — Hybrid Consumption Model

**Version:** 1.0
**Owner:** Principal PM, Analytics & AI
**Stakeholders:** VP of Sales, CFO
**Status:** Proposed — pending executive alignment
**Last Updated:** May 2026

---

## 1. Problem Statement

Palo Alto Networks is transitioning Prisma Cloud from a pure Annual Recurring Revenue (ARR) model to a hybrid consumption-based model anchored on Prisma Cloud compute credits. This creates a critical measurement gap:

**ARR alone is no longer sufficient.** A $500K deal with zero credit consumption looks identical to a $500K deal with 95% utilization — yet they represent fundamentally different business realities. The first is a churn liability. The second is a healthy, expanding customer.

Sales leadership needs a single metric that:
- Reflects whether contracted revenue is being *realized* through platform usage
- Gives the CFO a leading indicator of renewal risk before it becomes churn
- Aligns sales rep incentives with long-term customer value, not just deal signing

---

## 2. The North Star Metric: Consumed ARR (cARR)

### 2.1 Definition

**Consumed ARR is the portion of contracted ARR that is backed by actual platform usage.**

It answers the question: *"Of the revenue we've booked, how much is the customer actually realizing?"*

### 2.2 Formula

```
cARR = annual_commit_dollars × consumption_rate

consumption_rate = trailing_90d_avg(monthly_credits_consumed / included_monthly_compute_credits)
```

**Where:**
- `annual_commit_dollars` — the contracted ARR from the account's active contract
- `monthly_credits_consumed` — sum of Prisma Cloud credits consumed from `daily_usage_logs` for the calendar month
- `included_monthly_compute_credits` — the monthly Prisma Cloud credit allowance from the `contracts` table
- `trailing_90d_avg` — average consumption rate across the last 3 complete calendar months

**Example:**

| Account | ARR | Trailing 90d Consumption Rate | cARR |
|---|---|---|---|
| Healthy customer | $200K | 92% | $184K |
| Shelfware | $300K | 4% | $12K |
| Overage (expansion signal) | $80K | 138% | $110K |
| New account (<90 days) | $150K | — | Excluded (ramping) |

### 2.3 Aggregation Levels

| Level | Definition |
|---|---|
| **Account cARR** | `annual_commit_dollars × consumption_rate` per account |
| **Rep cARR** | Sum of account cARR across all active accounts owned by the rep |
| **Region cARR** | Sum of rep cARR within a region |
| **Org cARR** | Total — the Board-level North Star |

### 2.4 cARR Attainment Rate

```
cARR Attainment = cARR / Committed ARR
```

This is the headline health ratio for the CFO. A portfolio at 78% attainment means 22% of booked revenue is at risk of non-renewal.

---

## 3. Prisma Cloud Credit Pricing Model

Credits are the unit of value in every Prisma Cloud contract. The monthly credit allowance is derived from ARR at the time of deal signing.

| Edition | List Price | Typical Effective Price | Deal Profile |
|---|---|---|---|
| **Business Edition** | $90/credit/yr | $90/credit/yr | Mid-Market, 1-year term, no volume discount |
| **Enterprise Edition** | $180/credit/yr | ~$126/credit/yr | Enterprise, 2–3 year platform deal, ~30% discount |
| **Overage (PAYG)** | $90/credit/yr | $90/credit/yr | Above-commit usage billed at Business list rate |

**Credit consumption by workload type** (Enterprise Edition):

| Workload | Credits per Unit |
|---|---|
| VM (EC2, Azure VM, GCE) | 1 credit per VM |
| Host Defender (Linux/Windows) | 0.5 credits per host |
| Container Defender (host + all containers) | 5 credits per Defender |
| Serverless container (Fargate, Cloud Run) | 1 credit per container |
| Serverless function (Lambda, Azure Functions) | 1 credit per 6 functions |

*Source: Prisma Cloud Enterprise Edition licensing guide (PANW partner spec). Official list price not publicly published; figures from third-party research.*

---

## 4. Industry Benchmarks

This metric is consistent with how leading consumption-based companies measure revenue health:

| Company | Consumption Unit | Equivalent Metric |
|---|---|---|
| Snowflake | Credits | Consumed Revenue = credits used × price/credit |
| Databricks | DBUs | Consumed ARR = annualized trailing DBU usage |
| MongoDB | Queries/ops | Incremental ARR above usage baseline |
| OpenAI / Anthropic | Tokens | Revenue recognized on actual token consumption |
| **PANW Prisma Cloud** | Prisma Cloud Credits | **cARR = annual_commit × consumption_rate** |

**Snowflake precedent on compensation weighting:**
- New/greenfield reps: 70% bookings / 30% consumption
- Mature territory reps: 30% bookings / 70% consumption

---

## 5. Health Tier Classification

While cARR is a continuous metric, health tiers provide operational clarity for CS and sales prioritization:

| Health Tier | Consumption Rate | Interpretation | Action |
|---|---|---|---|
| **Expansion** | > 120% | Consistently over commit — upsell signal | Rep-led expansion motion |
| **Healthy** | 80–120% | On-track, full value realization | Maintain cadence |
| **At Risk** | 40–80% | Adoption lag — intervention needed | CS escalation within 30 days |
| **Shelfware** | 5–40% | Low utilization — churn risk | Executive sponsor outreach |
| **Inactive** | < 5% | Near-zero usage | Immediate save plan |
| **Ramping** | < 90 days old | Insufficient history | Excluded from cARR; tracked separately |

Health tiers are used for **dashboard visualization and CS prioritization only** — cARR itself uses the raw continuous consumption rate, not tiered multipliers.

---

## 6. Edge Case Handling

| Anomaly | Detection | cARR Treatment |
|---|---|---|
| **Shelfware** | `consumption_rate < 0.05` | cARR reflects near-zero value; flagged for save plan |
| **Spike & Drop** | Month 1 > 50% annual credits; trailing rate < 5% | Trailing 90-day window smooths spike; correctly reflects current inactive state |
| **Consistent Overages** | `consumption_rate > 1.2` for 2+ consecutive months | cARR exceeds ARR; `expansion_flag = TRUE` surfaced to rep |
| **Mid-Year Expansion** | Multiple overlapping active contracts | Credits summed across all active contracts; ARR uses highest-value contract as basis |
| **Orphaned Usage** | `account_id` in logs not in Accounts table | Excluded from cARR; surfaced in DQ report |
| **Out-of-contract Usage** | Log date outside all contract windows | Excluded from consumption rate calculation |
| **New Accounts** | Contract start < 90 days ago | Excluded from cARR; shown as "Ramping" in dashboard |
| **Multi-year Contracts** | `contract_term_years` = 2 or 3 | `annual_commit_dollars` used as-is (already annualized); term stored for renewal forecasting |

---

## 7. Proposed Compensation Framework

Modeled on Snowflake's territory-weighted hybrid approach:

| Rep Type | Bookings Weight | cARR Weight | Rationale |
|---|---|---|---|
| **Hunter** (new logos) | 70% | 30% | Primary job is net new; consumption follows logo |
| **Farmer** (renewals/expansion) | 30% | 70% | Primary job is value realization and expansion |
| **Overlay SE** | 0% | 100% | Purely accountable for consumption growth |

**Activation bonus:** Any rep whose new account reaches >80% consumption rate within 90 days of go-live earns a one-time SPIFf. Incentivizes quality of sale, not just deal size.

**Incremental cARR (MongoDB model):** Farmers are paid quarterly on incremental cARR above the account's baseline — usage growth driven by sales activity, not organic expansion.

---

## 8. Success Criteria

| KPI | Target | Window |
|---|---|---|
| Org-wide cARR Attainment | ≥ 85% | Rolling 90 days |
| Shelfware rate | ≤ 8% of active accounts | Monthly |
| Expansion flag conversion | ≥ 30% of flagged accounts → upsell within 180 days | Semi-annual |
| New account activation | ≥ 70% reach Healthy tier within 90 days of go-live | Quarterly |
| cARR forecast accuracy vs. actual NRR | Within ± 10% | At annual renewal |

---

## 9. Open Questions for Executive Alignment

1. **Territory weighting:** Does the VP Sales accept the 70/30 → 30/70 Hunter/Farmer split, or does the current team structure require a different breakdown?
2. **Overage recognition:** When cARR exceeds ARR (consumption_rate > 1.0), does finance recognize overage revenue in the same period or defer to contract renewal?
3. **Multi-year contract ARR basis:** For 2- and 3-year contracts, should `annual_commit_dollars` be the Year 1 value or the average annual value across the full term?
4. **Ramping threshold:** Is 90 days the right window for new account exclusion, or should it align with PANW's standard customer onboarding SLA?
5. **Calibration timeline:** The multiplier tiers and attainment targets above are starting points. When will we have sufficient renewal cohort data to validate these against actual churn outcomes?
