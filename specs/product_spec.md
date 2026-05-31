## Project Brief

**Context & Scenario**

Our Go-To-Market (GTM) organization is transitioning from a traditional, upfront Annual Recurring Revenue (ARR) model to a hybrid Consumption-based business model. Sales leadership is currently debating how to appropriately measure success, incentivize the right behaviors, and compensate sales representatives in this new paradigm.

We need a new "North Star" metric for the GTM organization that balances initial contract bookings with sustained platform usage over a customer's lifecycle.

**Your Role:** You are the Principal PM leading this initiative. You need to define this metric, build a working prototype of the data pipeline to calculate it, ensure data quality, and prepare an executive presentation for the VP of Sales and the CFO to secure a final decision.

To complete this, you are expected to utilize a spec-driven AI development approach (using AI coding tools like Cursor or Claude Code, paired with Markdown specs) to go rapidly from concept to working prototype.

---

# Product Spec: Consumed ARR (cARR)
## North Star Metric for Prisma Cloud GTM — Hybrid Consumption Model

**Version:** 1.0
**Owner:** Principal PM, Analytics & AI
**Stakeholders:** VP of Sales, CFO
**Status:** Proposed — pending executive alignment
**Last Updated:** May 2026

> **Product scope note:** This spec covers the Prisma Cloud capability set (cloud security posture, workload protection, code security).

---

## 1. Problem Statement

Palo Alto Networks is transitioning Prisma Cloud from an Annual Recurring Revenue (ARR) model to a hybrid consumption-based model, with credits corresponding to the resources protected and the features utilized.  This creates a critical measurement gap:

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

### 2.5 Intended Behavioral Drivers

cARR is designed to shift incentives at every layer of the GTM organization. The behaviors it is explicitly intended to reward — and suppress — are:

**Behaviors to reward**

| Behavior | How cARR Rewards It |
|---|---|
| Selling the right-sized deal | Overselling credits the customer won't use directly lowers cARR; reps are incentivized to right-size commits |
| Fast time-to-value | New accounts ramping to ≥80% consumption within 90 days trigger an activation bonus; slow onboarding costs attainment |
| Deep platform adoption | Reps who coach customers to expand workload coverage drive consumption rate up, lifting their cARR |
| Proactive renewal risk management | Farmers' quota is tied to cARR, not just renewal bookings — they have a direct financial incentive to intervene on At Risk accounts before renewal |
| Expansion from genuine usage | Expansion flag accounts (2+ months >120%) represent organic demand; reps are credited for converting that signal into a larger contract |

**Behaviors to suppress**

| Behavior | How cARR Suppresses It |
|---|---|
| Overselling / shelfware deals | A $500K deal at 4% consumption contributes only $20K to cARR — the rep's attainment number reflects the shelfware reality |
| Sandbagging credits at renewal | Renewing flat on a low-consumption account doesn't improve cARR; the rep must drive adoption, not just resign the paper |
| Ignoring post-sale onboarding | Under a pure bookings model, the rep's job ends at signature. Under cARR, onboarding quality is in their comp |
| Cherry-picking easy renewals | cARR weight for Farmers is 70%; avoiding at-risk accounts lowers their total attainment |

---

### 2.6 Retention and Churn as Secondary Metrics

cARR is the North Star, but retention and churn metrics provide the lagging validation that cARR predictions are accurate. Together they form a leading/lagging system:

```
cARR attainment (leading) → predicts → NRR / Gross Retention (lagging)
```

**Net Revenue Retention (NRR)**

```
NRR = (Beginning ARR + Expansion ARR - Contraction ARR - Churned ARR) / Beginning ARR
```

- cARR attainment rate is the leading indicator; NRR at renewal is the outcome it should predict
- Target: cARR-based NRR forecast within ±10% of actual NRR (see §9 Success Criteria)
- PANW disclosed NRR of ~119–120% in FY2024; an org-wide cARR attainment of ≥85% should support similar NRR levels in the consumption model

**Gross Revenue Retention (GRR)**

```
GRR = (Beginning ARR - Churned ARR - Contraction ARR) / Beginning ARR
```

- GRR strips out expansion, isolating pure churn and downsell risk
- Accounts in Shelfware or Inactive tier with renewals within 180 days are the primary GRR risk pool
- `arr_at_risk` (sum across at-risk tier accounts) is the GRR exposure number the CFO monitors

**Logo Churn Rate**

```
Logo Churn = Accounts lost at renewal / Total accounts up for renewal
```

- A secondary signal for CS prioritization — high cARR attainment should correlate with low logo churn
- Spike & Drop accounts (`is_spike_drop = TRUE`) are the highest-risk cohort for logo churn; they consumed heavily at onboarding but have since gone dark

**The leading/lagging relationship**

| cARR Signal | Lagging Metric Risk |
|---|---|
| Org attainment falls below 80% | NRR compression at next renewal cycle |
| Shelfware rate exceeds 10% | GRR deterioration within 2 quarters |
| Expansion flag conversion < 30% | NRR plateaus; growth shifts entirely to new logos |
| Ramping accounts fail to reach Healthy in 90 days | Elevated logo churn at first renewal |

Tracking both cARR (real-time) and NRR/GRR (at renewal) allows the team to validate — and over time calibrate — whether the health tier thresholds and attainment targets in this spec are set correctly.

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

### 4.1 The Shift to Consumption-Based Revenue

Consumption-based pricing is rapidly becoming the enterprise software standard, not an edge case:

- **67% of SaaS companies** now offer some form of usage-based pricing, up from 35% in 2020 — nearly doubling in five years. Among the largest software companies, 77% have incorporated consumption elements into their revenue model. *(Metronome, State of Usage-Based Pricing 2025)*
- **31% of companies** have adopted hybrid models that blend a committed subscription with a consumption overlay — exactly the structure Prisma Cloud uses. *(Metronome, 2025)*
- **SAP** announced in 2025 it is moving away from per-user and subscription pricing toward AI consumption-based billing as AI agents automate core enterprise workflows. *(erp.today, 2025)*
- **Salesforce** Einstein 1 now combines suite licensing with consumption credits for AI actions, signaling the shift even in legacy SaaS. *(Constellation Research, 2025)*

**Within cybersecurity specifically:**

| Vendor | Consumption Unit | Model |
|---|---|---|
| Microsoft Sentinel | GB ingested | Pure consumption — $2–4/GB; no seat floor |
| Lacework | Workload-hours | Usage-based CNAPP; scales with cloud footprint |
| CrowdStrike | Endpoints + flex credits | Seat base + flex consumption for AI/XDR modules |
| Wiz | Cloud workloads | Workload-count pricing tied to environment size |
| **PANW Prisma Cloud / Cortex Cloud** | Compute credits | **Hybrid — committed ARR + consumption overlay** |

PANW's credit model sits at the sophisticated end of this spectrum: unlike pure per-seat models it reflects *realized* security coverage, and unlike pure PAYG it provides revenue predictability for both the customer and PANW.

### 4.2 Comparable Metrics at Peer Companies

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
| **Mid-Year Expansion** | Multiple overlapping active contracts | Both ARR and credits summed across all simultaneously active contracts; `has_expansion = TRUE` |
| **Orphaned Usage** | `account_id` in logs not in Accounts table | Excluded from cARR; surfaced in DQ report |
| **Out-of-contract Usage** | Log date outside all contract windows | Excluded from consumption rate calculation |
| **New Accounts** | Contract start < 90 days ago | Excluded from cARR; shown as "Ramping" in dashboard |
| **Multi-year Contracts** | `contract_term_months` = 2 or 3 | `annual_commit_dollars` used as-is (already annualized); term stored for renewal forecasting |

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

## 8. Quota Setting and Forecasting

### 8.1 Quota Setting with cARR

cARR enables quota design that reflects territory health, not just last year's bookings:

**Hunter quotas — quality of sale**
- Quota includes a cARR ramp component: the new logo must reach a minimum consumption rate (e.g. ≥ 70%) within 90 days of go-live to count as full credit toward attainment
- This directly prices in onboarding quality and discourages overselling credits a customer won't use

**Farmer quotas — incremental cARR**
- Base quota = maintain current cARR attainment rate across the portfolio
- Stretch quota = grow total cARR by X% through expansion and improved utilization
- Farmers are measured on *incremental cARR* above baseline each quarter, not bookings — consumption growth driven by their activity, not contract auto-renewal

**Territory sizing and rebalancing**
- Use `total_carr` per rep to identify overloaded territories (high cARR, low headroom for growth) vs. underloaded ones (low cARR, high arr_at_risk needing intervention)
- Reassign accounts based on cARR capacity, not just account count or ARR — a rep carrying 20 Inactive accounts needs different support than one carrying 20 Healthy accounts

---

### 8.2 Forecasting with cARR

cARR provides two distinct forecasting signals: **renewal risk** (defensive) and **expansion pipeline** (offensive).

**Renewal risk forecast**
- `arr_at_risk = annual_commit_dollars - cARR` is the dollar value of committed ARR not backed by consumption
- Accounts with `health_tier IN ('At Risk', 'Shelfware', 'Inactive')` and a renewal within 90–180 days are the highest-priority save plays
- The org-level `arr_at_risk` sum is the CFO's leading indicator: if it trends above ~15% of total ARR, NRR will compress at the next renewal cycle

**Expansion pipeline forecast**
- Accounts with `expansion_flag = TRUE` (2+ consecutive months >120% consumption) have proven demand beyond their current commit — these are high-confidence upsell candidates
- `expansion_arr_pipeline` (sum of ARR for flagged accounts) quantifies the near-term expansion opportunity the team should be working

**NRR prediction**
- Trailing cARR attainment rate is a leading indicator of net revenue retention at renewal:

| Trailing cARR Attainment | Expected NRR Outcome |
|---|---|
| ≥ 90% | Strong renewal; likely expansion |
| 70–90% | Renewal probable; flat or slight compression |
| 50–70% | Renewal at risk; CS intervention required |
| < 50% | High churn probability; executive save plan |

- Target: cARR-based NRR forecast within ±10% of actual NRR at renewal (see §9 Success Criteria)

**Cohort-based calibration (v2)**
- Once sufficient renewal cohorts accumulate (12–18 months of data), regression against actual churn outcomes will allow the thresholds above to be empirically validated and refined per segment (Enterprise vs. Mid-Market) and industry vertical

---

## 9. Success Criteria



| KPI | Target | Window |
|---|---|---|
| Org-wide cARR Attainment | ≥ 85% | Rolling 90 days |
| Shelfware rate | ≤ 8% of active accounts | Monthly |
| Expansion flag conversion | ≥ 30% of flagged accounts → upsell within 180 days | Semi-annual |
| New account activation | ≥ 70% reach Healthy tier within 90 days of go-live | Quarterly |
| cARR forecast accuracy vs. actual NRR | Within ± 10% | At annual renewal |

---

## 10. Executive Dashboard

The cARR dashboard is the primary operational interface for sales leadership. It serves four distinct audiences, each with different questions and a different level of granularity.

---

### Audience 1: VP of Sales / CFO — Portfolio Overview

**Key questions:**
- How much of our booked ARR is actually being consumed?
- What is our total churn exposure right now, in dollars?
- Where is our expansion pipeline coming from?
- Which regions are healthy and which are lagging?

**Metrics needed:**
- Total ARR vs. total cARR and overall attainment rate
- ARR at risk (committed dollars not backed by consumption)
- Expansion pipeline (ARR from accounts consistently over-consuming)
- cARR attainment and account health mix broken out by region
- Rep attainment distribution — are outliers pulling the average, or is underperformance broad?

---

### Audience 2: Regional VPs / Sales Ops — Region Breakdown

**Key questions:**
- How does my region compare to others on cARR attainment?
- What percentage of my portfolio is at risk of churn?
- Which health tiers dominate my region — do I have a shelfware problem or an expansion opportunity?

**Metrics needed:**
- cARR, ARR, and attainment rate per region, ranked
- ARR at risk and risk percentage of total ARR
- Health tier mix (% of accounts in each tier) per region
- Expansion pipeline by region

---

### Audience 3: Sales Managers — Rep Leaderboard

**Key questions:**
- Who are my top performers this quarter?
- Which rep has the most at-risk ARR and needs coaching now?
- How does each rep's book of business break down by health tier?
- Who has expansion opportunities they should be working?

**Metrics needed:**
- Rep-level cARR and attainment rate, ranked within region and org
- ARR at risk per rep
- Health tier account counts per rep (expansion, healthy, at risk, shelfware, inactive)
- Expansion opportunity count and pipeline value per rep

---

### Audience 4: CS Leads / AEs — Account Detail

**Key questions:**
- Which of my accounts are shelfware and haven't logged in for months?
- Which accounts are consistently over-consuming and ready for an expansion conversation?
- What is the consumption trend for a specific account heading into renewal?
- Which new accounts are ramping as expected vs. stalling?

**Metrics needed:**
- Per-account consumption rate (trailing 90 days), health tier, and cARR
- ARR at risk per account
- Expansion flag (2+ months over commit) and spike/drop anomaly flag
- Contract start and end dates for renewal timing context

*For implementation details — stack, data flow, caching strategy, and fallback behavior — see the Technical Spec §8.*

---

## 11. Downstream System Integrations

cARR is most valuable when it flows beyond the dashboard into the systems reps and CS teams work in every day. Four downstream systems consume cARR data, each serving a distinct audience and purpose.

---

### Salesforce CRM

**Primary audience:** Sales reps, sales managers, revenue operations

**Purpose:** Surface cARR health signals in the tool reps use daily — so they can act on consumption trends without leaving their workflow. Key outcomes:
- Account health tier is visible on every Account record, informing renewal conversations
- Accounts flagged for expansion automatically generate an Opportunity, ensuring the signal gets worked
- Accounts with anomalous consumption patterns (spike & drop, near-zero usage) are flagged for CS review before they become surprises at renewal
- cARR attainment drives the renewal forecast category (Commit / Upside / Risk), giving the CFO a consumption-grounded pipeline view

An important attribution rule: the rep who currently owns the account gets cARR quota credit, but the rep who originally signed the deal retains comp attribution for that contract. Both ownership records are maintained and synced to Salesforce separately.

---

### Compensation Platform (e.g., Xactly, CaptivateIQ)

**Primary audience:** Finance, sales reps, sales managers

**Purpose:** Ensure quota attainment and commission calculations reflect consumption performance, not just bookings. Key outcomes:
- Farmer quota attainment is calculated from cARR, not renewal bookings — a rep who resigns a shelfware account at flat ARR does not receive full attainment credit
- Accelerator and decelerator tiers are triggered by cARR attainment rate, rewarding reps whose portfolios over-consume and penalizing persistent underperformance
- The activation bonus is paid when a new account reaches ≥80% consumption within 90 days of go-live — directly incentivizing onboarding quality
- Expansion SPIFs are tied to accounts with sustained over-consumption, rewarding reps for converting organic demand signals into new contracts

---

### Customer Success Platform (e.g., Gainsight, Totango)

**Primary audience:** CS managers, Customer Success Managers (CSMs)

**Purpose:** Translate health tiers into automated playbooks so every at-risk account gets a timely, standardized intervention — without relying on manual review. Key outcomes:
- Health tier drives a CS health score, giving CSMs a single number that reflects consumption reality
- Each tier triggers a defined playbook: expansion accounts are handed off to AEs, at-risk accounts get a CS escalation within 30 days, shelfware accounts trigger executive sponsor outreach, and inactive accounts immediately escalate to VP CS
- Ramping accounts enter an onboarding playbook with 90-day activation milestones
- Data confidence is surfaced alongside the health score — an account with only 1 month of history is treated differently from one with 12 months

---

### Business Intelligence / Board Reporting (e.g., Tableau, Looker)

**Primary audience:** CFO, Board of Directors, VP of Sales

**Purpose:** Enable board-level visibility into whether the consumption model is working — and provide the analytical foundation to validate and calibrate cARR thresholds over time. Key reports:
- **NRR forecast:** Org-wide cARR attainment as the leading indicator of next-period net revenue retention
- **Renewal risk register:** Accounts with high ARR at risk and near-term contract expirations, for executive review
- **Expansion pipeline:** Accounts consistently over-consuming, quantified by ARR, for offensive planning
- **Cohort churn analysis:** cARR attainment by contract start quarter — the primary tool for validating whether health tier thresholds accurately predict actual churn outcomes
- **QBR regional pack:** cARR vs. ARR by region and rep for quarterly business reviews

*For field-level mappings, sync frequencies, and integration architecture — see the Technical Spec §9.*

---

## 12. Open Questions for Executive Alignment

The following decisions require VP of Sales and/or CFO sign-off before cARR can be operationalized for compensation and reporting.

---

**1. Comp transition timeline and grandfathering** *(VP of Sales)*

How quickly do we shift rep compensation from bookings-weighted to cARR-weighted — and do we grandfather any existing OTE plans for reps mid-cycle? A hard cutover protects metric integrity but creates morale risk; a phased transition reduces disruption but delays the behavioral change.

**Decision needed:** Rollout timeline (next fiscal year vs. phased over 2 years) and whether current plans are protected through their existing term.

---

**2. Overage revenue recognition** *(CFO)*

When a customer consistently exceeds their credit commit, cARR will exceed their contracted ARR. Does Finance recognize the implied overage revenue in the current quarter, or hold it until a formal contract amendment is signed? This affects both the cARR number reps are measured on and the financial statements.

**Decision needed:** Whether over-consumption translates to in-period revenue recognition or deferred expansion bookings.

---

**3. Multi-year contract ARR basis** *(CFO)*

For 2- and 3-year deals, the annual commit can be calculated as the Year 1 value (lower, biased toward new logos) or the average annual value across the full term (higher, more representative of long-term commitment). The choice affects quota fairness, cARR magnitude, and how multi-year deals are incentivized vs. annual renewals.

**Decision needed:** Whether annual commit is Year 1 only or average annual value across the full contract term.

---

**4. Quota relief for ramping accounts** *(VP of Sales)*

New accounts are excluded from cARR for their first 90 days. Should reps receive quota relief — a temporary reduction in their cARR target — for accounts in this window? Without relief, a rep who closes several new logos in a quarter will see their attainment artificially suppressed until those accounts mature.

**Decision needed:** Whether ramping accounts reduce the rep's cARR quota denominator for the duration of the ramp period.

---

**5. Minimum portfolio attainment floor** *(VP of Sales)*

Should there be a floor below which sustained low cARR attainment triggers a formal performance review, independent of bookings performance? For example: if a rep's portfolio falls below 60% cARR attainment for two consecutive quarters, it surfaces in the performance process regardless of how many new deals they closed.

**Decision needed:** Whether a cARR attainment floor exists, and at what threshold it triggers management action.

---

**6. Board and investor reporting readiness** *(CFO)*

At what level of data maturity and forecast accuracy does cARR become an externally reportable metric — disclosed to investors alongside ARR and NRR? This requires agreement on definition consistency, audit trail, and the minimum number of renewal cohorts needed to validate the metric's predictive accuracy.

**Decision needed:** The accuracy and cohort-size thresholds required before cARR can be included in external financial disclosures.

---

## 13. Sources

- Metronome — [State of Usage-Based Pricing 2025](https://metronome.com/state-of-usage-based-pricing-2025)
- Palo Alto Networks — [Introducing Cortex Cloud (Feb 2025)](https://www.paloaltonetworks.com/blog/2025/02/announcing-innovations-cortex-cloud/)
- Palo Alto Networks — [Cortex Cloud Press Release](https://www.paloaltonetworks.com/company/press/2025/palo-alto-networks-introduces-cortex-cloud--the-future-of-real-time-cloud-security)
- erp.today — [SAP Shifts to AI Consumption Pricing (2025)](https://erp.today/sap-shifts-to-ai-consumption-pricing-as-agents-threaten-saas-revenue-model/)
- Constellation Research — [Enterprise Software 2025: Three Big Shifts](https://www.constellationr.com/blog-news/insights/enterprise-software-2025-three-big-shifts-watch)
- Dell'Oro Group — [The Shift from Prisma Cloud to Cortex Cloud](https://www.delloro.com/palo-alto-networks-reboots-cnapp-the-shift-from-prisma-cloud-to-cortex-cloud/)
- SiliconANGLE — [Cortex Cloud 2.0 and AgentiX (Oct 2025)](https://siliconangle.com/2025/10/28/palo-alto-networks-introduces-prisma-airs-2-0-cortex-cloud-2-0-agentix-secure-agentic-enterprise/)
