## Project Brief

**Context & Scenario**

Our Go-To-Market (GTM) organization is transitioning from a traditional, upfront Annual Recurring Revenue (ARR) model to a hybrid Consumption-based business model. Sales leadership is currently debating how to appropriately measure success, incentivize the right behaviors, and compensate sales representatives in this new paradigm.

We need a new "North Star" metric for the GTM organization that balances initial contract bookings with sustained platform usage over a customer's lifecycle.

**Your Role:** You are the Principal PM leading this initiative. You need to define this metric, build a working prototype of the data pipeline to calculate it, ensure data quality, and prepare an executive presentation for the VP of Sales and the CFO to secure a final decision.

To complete this, you are expected to utilize a spec-driven AI development approach (using AI coding tools like Cursor or Claude Code, paired with Markdown specs) to go rapidly from concept to working prototype.

---

# Product Spec: cACV — Consumed ACV
## North Star Metric for Prisma Cloud GTM — Hybrid Consumption Model

> **Terminology:** Throughout this spec, **ACV** (Annual Contract Value) refers to the contracted annual commitment. **cACV** (Consumed ACV) is the portion of ACV backed by actual platform usage. The two are distinct: ACV is what was sold; cACV is what is being realized.

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

## 2. The North Star Metric: Consumed ARR (cACV)

### 2.1 Definition

**Consumed ARR is the portion of contracted ACV (Annual Contract Value) that is backed by actual platform usage.**

It answers the question: *"Of the revenue we've booked, how much is the customer actually realizing?"*

> **Naming note:** cACV is an *imputed run-rate*, not recognized revenue. It equals `ACV × consumption_rate` and will not reconcile to PANW's reported ARR. Finance should treat it as a GTM health and forecasting metric — distinct from GAAP revenue recognition. Consider labeling it "cACV (GTM metric)" in any materials shared with investors to prevent confusion with reported ARR. **ACV** is used throughout this spec for the contracted annual value; it carries no GAAP connotation and will not cause confusion with recognized revenue.

### 2.2 Formula

```
cACV               = min(ACV × consumption_rate, ACV)
expansion_signal_acv = max(ACV × consumption_rate − ACV, 0)

consumption_rate   = trailing_90d_avg(monthly_credits_consumed / included_monthly_compute_credits)
```

**Where:**
- `ACV` (`annual_commit_dollars`) — the annualized contract value from the account's active contract
- `monthly_credits_consumed` — sum of Prisma Cloud credits consumed from `daily_usage_logs` for the calendar month
- `included_monthly_compute_credits` — the monthly Prisma Cloud credit allowance from the `contracts` table
- `trailing_90d_avg` — average consumption rate across the last 3 complete calendar months

**Cap rationale:** cACV is capped at ACV. This preserves the "% of bookings realized" narrative — a portfolio at 105% average consumption rate should not show attainment above 100%. Over-consumption is a positive signal but belongs in a separate metric (`expansion_signal_acv`) that feeds the upsell pipeline, not the attainment calculation.

**Example:**

| Account | ACV | Consumption Rate | cACV | Expansion Signal |
|---|---|---|---|---|
| Healthy customer | $200K | 92% | $184K | — |
| Shelfware | $300K | 4% | $12K | — |
| Overage (expansion signal) | $80K | 138% | $80K | $30K |
| New account (<90 days) | $150K | — | Excluded (ramping) | — |

### 2.3 Aggregation Levels

| Level | Definition |
|---|---|
| **Account cACV** | `annual_commit_dollars × consumption_rate` per account |
| **Rep cACV** | Sum of account cACV across all active accounts owned by the rep |
| **Region cACV** | Sum of rep cACV within a region |
| **Org cACV** | Total — the Board-level North Star |

### 2.4 cACV Attainment Rate

```
cACV Attainment = cACV / ACV
```

This is the headline health ratio for the CFO. A portfolio at 78% attainment means 22% of booked ACV is at risk of non-renewal.

---

### 2.5 Intended Behavioral Drivers

cACV is designed to shift incentives at every layer of the GTM organization. The behaviors it is explicitly intended to reward — and suppress — are:

**Behaviors to reward**

| Behavior | How cACV Rewards It |
|---|---|
| Selling the right-sized deal | Overselling credits the customer won't use directly lowers cACV; reps are incentivized to right-size commits |
| Fast time-to-value | New accounts ramping to ≥80% consumption within 90 days trigger an activation bonus; slow onboarding costs attainment |
| Deep platform adoption | Reps who coach customers to expand workload coverage drive consumption rate up, lifting their cACV |
| Proactive renewal risk management | Account Managers' quota is tied to cACV, not just renewal bookings — they have a direct financial incentive to intervene on At Risk accounts before renewal |
| Expansion from genuine usage | Expansion flag accounts (2+ months >120%) represent organic demand; reps are credited for converting that signal into a larger contract |

**Behaviors to suppress**

| Behavior | How cACV Suppresses It |
|---|---|
| Overselling / shelfware deals | A $500K deal at 4% consumption contributes only $20K to cACV — the rep's attainment number reflects the shelfware reality |
| Sandbagging credits at renewal | Renewing flat on a low-consumption account doesn't improve cACV; the rep must drive adoption, not just resign the paper |
| Ignoring post-sale onboarding | Under a pure bookings model, the rep's job ends at signature. Under cACV, onboarding quality is in their comp |
| Cherry-picking easy renewals | cACV weight for Account Managers is 70%; avoiding at-risk accounts lowers their total attainment |

**Known v1 gaming risk — Account Manager credit-burning:** Account Managers at 70% cACV weight are incentivized by raw consumption, which creates an inverse failure mode: pushing customers to run unnecessary scans, protect idle servers or decommissioned infrastructure, or otherwise burn credits without delivering security value. cACV cannot distinguish active threat response from passive credit burn. This is flagged as a v1 risk; an engagement quality signal (alerts acted on, policies deployed, active users) is the v2 mitigation. In v1, CS managers should watch for accounts with high consumption rate but low security outcomes — a pattern detectable through manual QBR review.

---

### 2.6 Retention and Churn as Secondary Metrics

cACV is the North Star, but retention and churn metrics provide the lagging validation that cACV predictions are accurate. Together they form a leading/lagging system:

```
cACV attainment (leading) → predicts → NRR / Gross Retention (lagging)
```

**Net Revenue Retention (NRR)**

```
NRR = (Beginning ARR + Expansion ARR - Contraction ARR - Churned ARR) / Beginning ARR
```

- cACV attainment rate is the leading indicator; NRR at renewal is the outcome it should predict
- Target: cACV-based NRR forecast within ±10% of actual NRR (see §9 Success Criteria)
- PANW disclosed NRR of ~119–120% in FY2024; an org-wide cACV attainment of ≥85% should support similar NRR levels in the consumption model

**Gross Revenue Retention (GRR)**

```
GRR = (Beginning ARR - Churned ARR - Contraction ARR) / Beginning ARR
```

- GRR strips out expansion, isolating pure churn and downsell risk
- Accounts in Shelfware or Inactive tier with renewals within 180 days are the primary GRR risk pool
- `acv_at_risk` (sum across at-risk tier accounts) is the GRR exposure number the CFO monitors

**Logo Churn Rate**

```
Logo Churn = Accounts lost at renewal / Total accounts up for renewal
```

- A secondary signal for CS prioritization — high cACV attainment should correlate with low logo churn
- Spike & Drop accounts (`is_spike_drop = TRUE`) are the highest-risk cohort for logo churn; they consumed heavily at onboarding but have since gone dark

**The leading/lagging relationship**

| cACV Signal | Lagging Metric Risk |
|---|---|
| Org attainment falls below 80% | NRR compression at next renewal cycle |
| Shelfware rate exceeds 10% | GRR deterioration within 2 quarters |
| Expansion flag conversion < 30% | NRR plateaus; growth shifts entirely to new logos |
| Ramping accounts fail to reach Healthy in 90 days | Elevated logo churn at first renewal |

> **v1 note:** The NRR outcome bands in the prediction table above (≥90% → strong renewal, etc.) are starting hypotheses derived from industry analogues, not PANW-specific renewal data. Treat them as directional guidance for v1. The primary value of this framework is establishing the *measurement habit* — tracking cACV attainment alongside NRR outcomes at every renewal cohort — so the bands can be empirically recalibrated after 12–18 months. Plan a formal calibration milestone; commit to adjusting thresholds if the data contradicts them.

Tracking both cACV (real-time) and NRR/GRR (at renewal) allows the team to validate — and over time calibrate — whether the health tier thresholds and attainment targets in this spec are set correctly.

---

## 3. Prisma Cloud Credit Pricing Model

Credits are the unit of value in every Prisma Cloud contract. The monthly credit allowance is derived from ACV at deal signing.

| Edition | Deal Profile | Pricing |
|---|---|---|
| **Business Edition** | Mid-Market, 1-year term, no volume discount | Contact PANW sales |
| **Enterprise Edition** | Enterprise, 2–3 year platform deal, ~30% volume discount typical | Contact PANW sales |
| **Overage (PAYG)** | Above-commit usage billed at Business list rate | Contact PANW sales |

**Credit consumption by workload type** (Enterprise Edition):

| Workload | Credits per Unit |
|---|---|
| VM (EC2, Azure VM, GCE) | 1 credit per VM |
| Host Defender (Linux/Windows) | 0.5 credits per host |
| Container Defender (host + all containers) | 5 credits per Defender |
| Serverless container (Fargate, Cloud Run) | 1 credit per container |
| Serverless function (Lambda, Azure Functions) | 1 credit per 6 functions |

**Sources:**
- **Credit consumption by workload type:** Prisma Cloud Compute Edition admin guide, Licensing section — [docs.prismacloud.io](https://docs.prismacloud.io/en/compute-edition/30/admin-guide/licensing/licensing).
- **Credit-based licensing model and Business / Enterprise tier structure:** Corroborated by user reviews on [PeerSpot](https://www.peerspot.com/products/prisma-cloud-by-palo-alto-networks-pricing). List pricing not publicly disclosed by PANW — contact your account team or the [PANW Partner Portal](https://partners.paloaltonetworks.com) for current rates.
- **~30% Enterprise discount:** Consistent with multi-year platform deal structures reported by Dell'Oro Group (see §14 Sources).

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
| **PANW Prisma Cloud** | Prisma Cloud Credits | **cACV = annual_commit × consumption_rate** |

**Snowflake precedent on compensation weighting:**
- New/greenfield reps: 70% bookings / 30% consumption
- Mature territory reps: 30% bookings / 70% consumption

---

## 5. Health Tier Classification

While cACV is a continuous metric, health tiers provide operational clarity for CS and sales prioritization:

| Health Tier | Consumption Rate | Interpretation | Action |
|---|---|---|---|
| **Expansion** | > 120% | Consistently over commit — upsell signal | Rep-led expansion motion |
| **Healthy** | 80–120% | On-track, full value realization | Maintain cadence |
| **At Risk** | 40–80% | Adoption lag — intervention needed | CS escalation within 30 days |
| **Shelfware** | 5–40% | Low utilization — churn risk | Executive sponsor outreach |
| **Inactive** | < 5% | Near-zero usage | Immediate save plan |
| **Ramping** | < 90 days old | Insufficient history | Excluded from cACV; tracked separately |

Health tiers are used for **dashboard visualization and CS prioritization only** — cACV itself uses the raw continuous consumption rate, not tiered multipliers.

> **v1 note:** The thresholds above (5% / 40% / 80% / 120%) are starting hypotheses, not empirically validated cutoffs. They are reasonable starting points based on industry analogues but have not been tested against PANW renewal cohort data. Plan a calibration review at 12–18 months once sufficient renewal outcomes are available. Thresholds should not be used as performance targets until validated.

---

## 6. Edge Case Handling

| Anomaly | Business Signal | cACV Treatment |
|---|---|---|
| **Shelfware** | Near-zero consumption rate over trailing 90 days | cACV reflects near-zero value; account flagged for save plan |
| **Spike & Drop** | Mass onboarding in month 1, then consumption collapses | Trailing 90-day window smooths the spike; correctly reflects current inactive state once spike ages out |
| **Consistent Overages** | Over-consuming commit for 2+ consecutive months | cACV capped at commit; excess reported as expansion signal; expansion flag surfaced to rep for upsell motion |
| **Mid-Year Expansion** | Customer signs additional contract before original expires | ARR and credits summed across all simultaneously active contracts; expansion flag set |
| **Orphaned Usage** | Usage logs reference an account not in the customer master | Excluded from cACV; surfaced in data quality report |
| **Out-of-contract Usage** | Usage logged before contract start or after contract end | Excluded from consumption rate calculation |
| **New Accounts** | Contract start within last 90 days — insufficient consumption history | Excluded from cACV; shown as "Ramping" until 90-day window matures |
| **Multi-year Contracts** | 2- or 3-year deal term | ACV used as-is (already annualized in contract); term stored for renewal forecasting and comp multiplier. See §12 for v1 ACV basis decision |

---

## 7. Proposed Compensation Framework

Modeled on Snowflake's territory-weighted hybrid approach:

| Role | Bookings Weight | cACV Weight | Rationale |
|---|---|---|---|
| **Account Executive (AE)** — new logos | 70% | 30% | Primary job is net new; consumption follows logo |
| **Account Manager (AM)** — renewals/expansion | 30% | 70% | Primary job is value realization and expansion |
| **Sales Engineer (SE)** — consumption overlay | 0% | 100% | Purely accountable for consumption growth |

**Activation bonus:** Any AE whose new account sustains ≥80% consumption rate through month 6 (not month 3) earns a one-time SPIF. The 6-month tenure requirement is intentional: paying at 90 days creates a Spike & Drop exploit where reps push aggressive onboarding in the window and the customer drops off after the bonus clears. Month 6 requires sustained adoption, not a burst.

**Incremental cACV (MongoDB model):** Account Managers are paid quarterly on incremental cACV above the account's baseline — usage growth driven by sales activity, not organic expansion.

### 7.1 Multi-Year ACV and Rep Credit

ACV is always the annualized value: a 3-year, $360K TCV deal has an ACV of $120K/year. The cACV denominator is always the current year's ACV — independent of term length.

Quota credit for multi-year deals includes a **term multiplier** to reward locking in long-term commits:

| Contract Term | ACV Quota Credit Multiplier |
|---|---|
| 1 year | 1.00× ACV |
| 2 years | 1.10× ACV |
| 3 years | 1.15× ACV |

**How it works:** An AE who closes a 3-year, $120K ACV deal receives $138K in quota credit at signing (1.15×). The cACV metric still uses $120K as the denominator each year — the multiplier is a comp incentive only, not a metric inflation.

**Account ownership through multi-year terms:** The AE who signs a multi-year deal receives the term multiplier credit at signing. From Year 2 onward, the assigned AM earns cACV attainment credit for that account. If the account churns before the committed term ends, a portion of the term multiplier is subject to clawback from the AE. Clawback terms and the Year 1→AM handoff timing require VP of Sales sign-off (see §13 Q10).

**Out of scope for v1:** Compensation design for channel partners and CSMs is a separate workstream and is not addressed in this spec. These roles interact with consumption outcomes but require distinct quota structures and attribution rules.

---

## 8. Quota Setting and Forecasting

### 8.1 Quota Setting with cACV

cACV enables quota design that reflects territory health, not just last year's bookings:

**Account Executive (AE) quotas — quality of sale**
- Quota includes a cACV ramp component: the new logo must reach a minimum consumption rate (e.g. ≥ 70%) within 90 days of go-live to count as full credit toward attainment
- This directly prices in onboarding quality and discourages overselling credits a customer won't use

**Account Manager (AM) quotas — incremental cACV**
- Base quota = maintain current cACV attainment rate across the portfolio
- Stretch quota = grow total cACV by X% through expansion and improved utilization
- Account Managers are measured on *incremental cACV* above baseline each quarter, not bookings — consumption growth driven by their activity, not contract auto-renewal

**Territory sizing and rebalancing**
- Use `total_cacv` per rep to identify overloaded territories (high cACV, low headroom for growth) vs. underloaded ones (low cACV, high ACV at risk needing intervention)
- Reassign accounts based on cACV capacity, not just account count or ARR — a rep carrying 20 Inactive accounts needs different support than one carrying 20 Healthy accounts

---

### 8.2 Forecasting with cACV

cACV provides two distinct forecasting signals: **renewal risk** (defensive) and **expansion pipeline** (offensive).

**Renewal risk forecast**
- `acv_at_risk = ACV - cACV` is the dollar value of committed ACV not backed by consumption
- Accounts with `health_tier IN ('At Risk', 'Shelfware', 'Inactive')` and a renewal within 90–180 days are the highest-priority save plays
- The org-level `acv_at_risk` sum is the CFO's leading indicator: if it trends above ~15% of total ARR, NRR will compress at the next renewal cycle

**Expansion pipeline forecast**
- Accounts with `expansion_flag = TRUE` (2+ consecutive months >120% consumption) have proven demand beyond their current commit — these are high-confidence upsell candidates
- `expansion_arr_pipeline` (sum of ARR for flagged accounts) quantifies the near-term expansion opportunity the team should be working

**NRR prediction**
- Trailing cACV attainment rate is a leading indicator of net revenue retention at renewal:

| Trailing cACV Attainment | Expected NRR Outcome |
|---|---|
| ≥ 90% | Strong renewal; likely expansion |
| 70–90% | Renewal probable; flat or slight compression |
| 50–70% | Renewal at risk; CS intervention required |
| < 50% | High churn probability; executive save plan |

- Target: cACV-based NRR forecast within ±10% of actual NRR at renewal (see §9 Success Criteria)

**Cohort-based calibration (v2)**
- Once sufficient renewal cohorts accumulate (12–18 months of data), regression against actual churn outcomes will allow the thresholds above to be empirically validated and refined per segment (Enterprise vs. Mid-Market) and industry vertical

---

## 9. Success Criteria



| KPI | Target | Window |
|---|---|---|
| Org-wide cACV Attainment | ≥ 85% | Rolling 90 days |
| Shelfware rate | ≤ 8% of active accounts | Monthly |
| Expansion flag conversion | ≥ 30% of flagged accounts → upsell within 180 days | Semi-annual |
| New account activation | ≥ 70% reach Healthy tier within 90 days of go-live | Quarterly |
| cACV forecast accuracy vs. actual NRR | Within ± 10% | At annual renewal |

---

## 10. v1 Scope

This section makes explicit what is and is not in scope for the initial launch of cACV. The metric is designed to ship, not to be perfect.

### In scope for v1

- cACV calculation at account, rep, region, and org level
- Health tier classification (6 tiers) based on trailing 90-day consumption rate
- `expansion_signal_acv` as a separate metric for over-consuming accounts (cACV itself capped at commit)
- AE / AM comp weighting (bookings vs. cACV), with activation bonus at month 6 and multi-year term multiplier
- Executive dashboard with 4 views (portfolio overview, region, rep leaderboard, account detail)
- Downstream signals to Salesforce CRM, compensation platform, CS platform, and BI layer
- Data quality framework (11 automated assertions) with orphaned and rogue usage handling
- Multi-year contract treatment: Year 1 ACV as the cACV basis *(v1 decision — see §13)*

### Explicitly out of scope for v1

| Out-of-scope item | Rationale | Where it goes |
|---|---|---|
| Channel partner / SE / CSM comp design | Distinct quota structures and attribution rules; separate workstream | Separate spec |
| Engagement quality signal (active usage vs. passive credit burn) | Requires additional instrumentation (login events, alert actions); acknowledged v1 risk | v2 roadmap |
| Real-time consumption updates | Daily batch sufficient for v1; near-real-time adds infra complexity | v2 roadmap |
| Health tier threshold calibration | Requires 12–18 months of renewal cohort data to validate | v2 milestone |
| NRR prediction band validation | Same dependency on renewal cohort data | v2 milestone |
| Multi-region currency normalization | Not relevant to current territory structure | v2 if needed |
| cACV as an externally reported metric | Requires audit trail, definition consistency, and investor alignment | CFO decision (§13 Q6) |

---

## 11. Executive Dashboard

The cACV dashboard is the primary operational interface for sales leadership. It serves four distinct audiences, each with different questions and a different level of granularity.

---

### Audience 1: VP of Sales / CFO — Portfolio Overview

**Key questions:**
- How much of our booked ARR is actually being consumed?
- What is our total churn exposure right now, in dollars?
- Where is our expansion pipeline coming from?
- Which regions are healthy and which are lagging?

**Metrics needed:**
- Total ACV vs. total cACV and overall attainment rate
- ACV at risk (committed dollars not backed by consumption)
- Expansion pipeline (ARR from accounts consistently over-consuming)
- cACV attainment and account health mix broken out by region
- Rep attainment distribution — are outliers pulling the average, or is underperformance broad?

---

### Audience 2: Regional VPs / Sales Ops — Region Breakdown

**Key questions:**
- How does my region compare to others on cACV attainment?
- What percentage of my portfolio is at risk of churn?
- Which health tiers dominate my region — do I have a shelfware problem or an expansion opportunity?

**Metrics needed:**
- cACV, ACV, and attainment rate per region, ranked
- ACV at risk and risk percentage of total ACV
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
- Rep-level cACV and attainment rate, ranked within region and org
- ACV at risk per rep
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
- Per-account consumption rate (trailing 90 days), health tier, and cACV
- ACV at risk per account
- Expansion flag (2+ months over commit) and spike/drop anomaly flag
- Contract start and end dates for renewal timing context

*For implementation details — stack, data flow, caching strategy, and fallback behavior — see the Technical Spec §8.*

---

## 12. Downstream System Integrations

cACV is most valuable when it flows beyond the dashboard into the systems reps and CS teams work in every day. Four downstream systems consume cACV data, each serving a distinct audience and purpose.

---

### Salesforce CRM

**Primary audience:** Sales reps, sales managers, revenue operations

**Purpose:** Surface cACV health signals in the tool reps use daily — so they can act on consumption trends without leaving their workflow. Key outcomes:
- Account health tier is visible on every Account record, informing renewal conversations
- Accounts flagged for expansion automatically generate an Opportunity, ensuring the signal gets worked
- Accounts with anomalous consumption patterns (spike & drop, near-zero usage) are flagged for CS review before they become surprises at renewal
- cACV attainment drives the renewal forecast category (Commit / Upside / Risk), giving the CFO a consumption-grounded pipeline view

An important attribution rule: the rep who currently owns the account gets cACV quota credit, but the rep who originally signed the deal retains comp attribution for that contract. Both ownership records are maintained and synced to Salesforce separately.

---

### Compensation Platform (e.g., Xactly, CaptivateIQ)

**Primary audience:** Finance, sales reps, sales managers

**Purpose:** Ensure quota attainment and commission calculations reflect consumption performance, not just bookings. Key outcomes:
- Account Manager quota attainment is calculated from cACV, not renewal bookings — a rep who resigns a shelfware account at flat ACV does not receive full attainment credit
- Accelerator and decelerator tiers are triggered by cACV attainment rate, rewarding reps whose portfolios over-consume and penalizing persistent underperformance
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

**Purpose:** Enable board-level visibility into whether the consumption model is working — and provide the analytical foundation to validate and calibrate cACV thresholds over time. Key reports:
- **NRR forecast:** Org-wide cACV attainment as the leading indicator of next-period net revenue retention
- **Renewal risk register:** Accounts with high ARR at risk and near-term contract expirations, for executive review
- **Expansion pipeline:** Accounts consistently over-consuming, quantified by ARR, for offensive planning
- **Cohort churn analysis:** cACV attainment by contract start quarter — the primary tool for validating whether health tier thresholds accurately predict actual churn outcomes
- **QBR regional pack:** cACV vs. ARR by region and rep for quarterly business reviews

*For field-level mappings, sync frequencies, and integration architecture — see the Technical Spec §9.*

---

## 13. Open Questions for Executive Alignment

The following decisions require VP of Sales and/or CFO sign-off before cACV can be operationalized. They are grouped by whether they block v1 launch or can be resolved post-launch.

---

### v1-Blocking Decisions

**1. Comp go-live timing** *(VP of Sales)*

Do we launch cACV-weighted comp in the same fiscal year as the metric, or shadow-track for 1–2 quarters first before paying on it? Shadow-tracking reduces risk but delays behavioral change. Paying immediately requires reps to trust the metric before it has a track record.

**Decision needed:** Same-year comp launch vs. shadow-tracking period; if shadow-tracking, how long and what triggers the switch.

---

**2. Single vs. dual quota** *(VP of Sales)*

Do reps carry a single blended attainment number (bookings + cACV weighted), or two separate quotas (one bookings, one cACV)? A single blended number is simpler but allows reps to trade off one against the other. Dual quotas create separate accountability but add comp system complexity.

**Decision needed:** Blended single quota or two separate quota lines.

---

**3. Overage revenue recognition** *(CFO)*

Over-consuming accounts generate `expansion_signal_acv` above their commit. Does Finance recognize that implied overage in the current quarter, or hold it until a contract amendment is signed? This determines whether expansion signal is a pipeline metric or an in-period revenue input.

**Decision needed:** In-period overage recognition vs. deferred to contract amendment.

---

**4. Multi-year ACV basis** *(CFO)*

**v1 default (recommended):** Use Year 1 ACV (`annual_commit_dollars`) as the cACV denominator — it's the value in the contract and the number sales is paid on. Year 2 and 3 are handled at renewal.

**Risk:** Year 1 of a ramp deal (e.g., 33% consumption on a 3-year ramp) can look like disaster even when on plan. Mitigant: flag ramp-structured deals separately; exclude from health tier penalties during the ramp period.

**Decision needed:** Confirm Year 1 ACV basis, or override with blended average annual value. If overriding, the pipeline calculation must change.

---

**5. Phased vs. big-bang rollout** *(VP of Sales)*

Launch cACV across all regions simultaneously, or pilot one region or segment first? A pilot reduces blast radius if the metric needs recalibration but creates a two-tier comp environment that can cause rep attrition in non-pilot regions.

**Decision needed:** Full launch vs. pilot region/segment; if pilot, which region and for how long.

---

### Post-Launch Decisions

**6. Quota relief for ramping accounts** *(VP of Sales)*

New accounts are excluded from cACV for 90 days. Should reps receive a corresponding quota reduction for accounts in the ramp window? Without it, a rep who closes several new logos in a quarter sees attainment suppressed until accounts mature.

**Decision needed:** Whether ramping accounts reduce the quota denominator during the ramp period.

---

**7. Portfolio attainment floor** *(VP of Sales)*

Should sustained low cACV attainment (e.g., below 60% for two consecutive quarters) trigger a performance review, independent of bookings performance?

**Decision needed:** Whether an attainment floor exists, at what threshold, and how it interacts with the PIP process.

---

**8. In-flight comp plan transition** *(VP of Sales + Finance)*

Reps who signed OTE plans before cACV was introduced have contractual expectations. Are those plans honored to year-end, prorated, or renegotiated? This is the highest change-management risk in the rollout.

**Decision needed:** Treatment of existing signed comp plans; legal review required.

---

**9. Board and investor reporting readiness** *(CFO)*

At what point does cACV move from an internal GTM metric to an externally disclosed one? This requires audit trail, definition consistency, and investor alignment on how it differs from reported ARR.

**Decision needed:** Threshold (accuracy, cohort size, audit readiness) for external disclosure; timeline.

---

**10. Multi-year account ownership and clawback** *(VP of Sales)*

The AE who closes a multi-year deal receives a term multiplier on quota credit at signing (§7.1). From Year 2 onward, the account transitions to an AM for cACV attainment. Two sub-decisions needed:

- **Handoff timing:** Does the AE-to-AM transition happen at contract signing, at the start of Year 2, or at a defined onboarding milestone?
- **Clawback terms:** If the account churns before the committed term ends, what portion of the term multiplier is recovered from the AE, over what window?

Without a defined clawback, the term multiplier creates an incentive for AEs to sign long-term deals without accountability for early churn. Without a clear handoff timing, both the AE and AM may assume the other is managing the account.

**Decision needed:** AE-to-AM handoff trigger; clawback percentage and recovery window; whether clawback applies differently to voluntary churn vs. involuntary (e.g., customer acquired).

---

## 14. Sources

- Metronome — [State of Usage-Based Pricing 2025](https://metronome.com/state-of-usage-based-pricing-2025)
- Palo Alto Networks — [Introducing Cortex Cloud (Feb 2025)](https://www.paloaltonetworks.com/blog/2025/02/announcing-innovations-cortex-cloud/)
- Palo Alto Networks — [Cortex Cloud Press Release](https://www.paloaltonetworks.com/company/press/2025/palo-alto-networks-introduces-cortex-cloud--the-future-of-real-time-cloud-security)
- erp.today — [SAP Shifts to AI Consumption Pricing (2025)](https://erp.today/sap-shifts-to-ai-consumption-pricing-as-agents-threaten-saas-revenue-model/)
- Constellation Research — [Enterprise Software 2025: Three Big Shifts](https://www.constellationr.com/blog-news/insights/enterprise-software-2025-three-big-shifts-watch)
- Dell'Oro Group — [The Shift from Prisma Cloud to Cortex Cloud](https://www.delloro.com/palo-alto-networks-reboots-cnapp-the-shift-from-prisma-cloud-to-cortex-cloud/)
- SiliconANGLE — [Cortex Cloud 2.0 and AgentiX (Oct 2025)](https://siliconangle.com/2025/10/28/palo-alto-networks-introduces-prisma-airs-2-0-cortex-cloud-2-0-agentix-secure-agentic-enterprise/)
