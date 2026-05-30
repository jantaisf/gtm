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

The cARR dashboard is the primary operational interface for sales leadership. It is built in Streamlit + Plotly, connected live to BigQuery, and designed for three audiences: the VP of Sales (portfolio overview), regional managers (leaderboard and territory health), and CS leads (at-risk account triage).

### Views

**📊 Portfolio Overview** — VP of Sales / CFO
| Element | What It Shows |
|---|---|
| KPI strip (5 metrics) | Total ARR, Total cARR, cARR Attainment %, ARR at Risk $, Expansion Pipeline $ |
| cARR by Region bar chart | ARR (grey) overlaid with cARR (blue) per region; attainment % labeled inside each bar |
| Account Health Mix donut | Distribution of accounts across all 6 health tiers |
| Attainment scatter | Each rep plotted as ARR vs. cARR attainment %; bubble size = portfolio ARR; 80% and 100% reference lines |

**🗺️ By Region** — Regional VPs / Sales Ops
| Element | What It Shows |
|---|---|
| Region summary table | Reps, accounts, ARR, cARR, attainment, ARR at risk, expansion pipeline per region |
| Health tier stacked bar | % of accounts in each health tier per region — surfaces which regions carry the most churn risk |

**👤 By Rep — Leaderboard** — Sales Managers
| Element | What It Shows |
|---|---|
| Top / bottom callout cards | #1 rep (green) and lowest-attainment rep (red if <60%) with one-line summary |
| Horizontal ranked bar chart | Top 20 reps by cARR; ARR (grey) + cARR (blue) overlay with attainment % labeled |
| Full rep table | All reps with org rank, region rank, ARR, cARR, attainment, at-risk $, expansion opps, health tier breakdown |

**🏢 Accounts** — CS Leads / AEs
| Element | What It Shows |
|---|---|
| Health tier filter | Drill into a single tier (e.g., show only Shelfware accounts) |
| ARR vs. consumption scatter | Each account plotted by ARR commit vs. trailing 90d consumption rate; colored by health tier |
| Account detail table | Per-account: ARR, cARR, consumption rate, health tier, contract dates, expansion flag, spike/drop flag |

### Filters
- **As-of Date** — select any pipeline run date for point-in-time analysis
- **Region** — scope all views to a single region
- **Sales Rep** — scope to an individual rep's portfolio

---

## 11. Downstream System Integrations

cARR is most valuable when it flows beyond the dashboard into the systems reps and CS teams work in every day.

### Salesforce CRM

**Direction:** BigQuery `carr_account` → Salesforce Account object (nightly sync)

| cARR Field | Salesforce Field | Used For |
|---|---|---|
| `health_tier` | `Health_Tier__c` | Account list views, CS playbook triggers |
| `carr_attainment_rate` | `cARR_Attainment__c` | Renewal forecast category (Commit / Upside / Risk) |
| `arr_at_risk` | `ARR_at_Risk__c` | Renewal opportunity amount adjustment |
| `expansion_flag = TRUE` | Auto-create Expansion Opportunity | Expansion pipeline in rep's book |
| `is_spike_drop = TRUE` | Flag on Account for CS review | Save plan trigger |

The `signing_owner_id` vs. `employee_id` split is critical here: Salesforce must attribute cARR to the *current* account owner (for quota tracking) and the *signing owner* (for comp credit on the original deal).

### Compensation Platform (e.g., Xactly, CaptivateIQ)

**Direction:** BigQuery `carr_rep_rollup` → compensation engine (monthly/quarterly)

| Field | Comp Use |
|---|---|
| `total_carr` | Farmer quota attainment calculation |
| `carr_attainment_rate` | Tier multiplier for accelerators/decelerators |
| `expansion_arr_pipeline` | Expansion SPIF eligibility |
| New account reaching ≥80% within 90 days | Activation bonus trigger (requires joining `carr_account` on `contract_start_date`) |

### Customer Success Platform (e.g., Gainsight, Totango)

**Direction:** BigQuery `carr_account` → CS health score engine (daily)

| Health Tier | CS Action Triggered |
|---|---|
| Expansion | Handoff to AE for expansion motion |
| Healthy | Automated check-in cadence maintained |
| At Risk | CS escalation playbook opened within 30 days |
| Shelfware | Executive sponsor outreach playbook |
| Inactive | Immediate save plan; executive escalation |
| Ramping | Onboarding playbook; 90-day activation tracking |

### Business Intelligence / Board Reporting (e.g., Tableau, Looker)

**Direction:** BigQuery `carr_rep_rollup` + `carr_account` → BI layer (on-demand)

Key reports enabled:
- **Board NRR forecast:** org-wide cARR attainment as leading indicator of next-period NRR
- **Cohort analysis:** cARR attainment by contract start quarter → validate health tier thresholds against actual churn
- **Segment benchmarking:** Enterprise vs. Mid-Market attainment trends over time
- **Fiscal quarter close:** cARR vs. ARR by region for QBR packages

---

## 12. Open Questions for Executive Alignment

1. **Territory weighting:** Does the VP Sales accept the 70/30 → 30/70 Hunter/Farmer split, or does the current team structure require a different breakdown?
2. **Overage recognition:** When cARR exceeds ARR (consumption_rate > 1.0), does finance recognize overage revenue in the same period or defer to contract renewal?
3. **Multi-year contract ARR basis:** For 2- and 3-year contracts, should `annual_commit_dollars` be the Year 1 value or the average annual value across the full term?
4. **Ramping threshold:** Is 90 days the right window for new account exclusion, or should it align with PANW's standard customer onboarding SLA?
5. **Calibration timeline:** The multiplier tiers and attainment targets above are starting points. When will we have sufficient renewal cohort data to validate these against actual churn outcomes?

---

## 13. Sources

- Metronome — [State of Usage-Based Pricing 2025](https://metronome.com/state-of-usage-based-pricing-2025)
- Palo Alto Networks — [Introducing Cortex Cloud (Feb 2025)](https://www.paloaltonetworks.com/blog/2025/02/announcing-innovations-cortex-cloud/)
- Palo Alto Networks — [Cortex Cloud Press Release](https://www.paloaltonetworks.com/company/press/2025/palo-alto-networks-introduces-cortex-cloud--the-future-of-real-time-cloud-security)
- erp.today — [SAP Shifts to AI Consumption Pricing (2025)](https://erp.today/sap-shifts-to-ai-consumption-pricing-as-agents-threaten-saas-revenue-model/)
- Constellation Research — [Enterprise Software 2025: Three Big Shifts](https://www.constellationr.com/blog-news/insights/enterprise-software-2025-three-big-shifts-watch)
- Dell'Oro Group — [The Shift from Prisma Cloud to Cortex Cloud](https://www.delloro.com/palo-alto-networks-reboots-cnapp-the-shift-from-prisma-cloud-to-cortex-cloud/)
- SiliconANGLE — [Cortex Cloud 2.0 and AgentiX (Oct 2025)](https://siliconangle.com/2025/10/28/palo-alto-networks-introduces-prisma-airs-2-0-cortex-cloud-2-0-agentix-secure-agentic-enterprise/)
