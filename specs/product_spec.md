## Project Brief

**Context & Scenario**

Our Go-To-Market (GTM) organization is transitioning from a traditional, upfront Annual Recurring Revenue (ARR) model to a hybrid Consumption-based business model. Sales leadership is currently debating how to appropriately measure success, incentivize the right behaviors, and compensate sales representatives in this new paradigm.

We need a new "North Star" metric for the GTM organization that balances initial contract bookings with sustained platform usage over a customer's lifecycle.

**Your Role:** You are the Principal PM leading this initiative. You need to define this metric, build a working prototype of the data pipeline to calculate it, ensure data quality, and prepare an executive presentation for the VP of Sales and the CFO to secure a final decision.

To complete this, you are expected to utilize a spec-driven AI development approach (using AI coding tools like Cursor or Claude Code, paired with Markdown specs) to go rapidly from concept to working prototype.

---

# Product Spec: Consumption ACV
## North Star Metric for Prisma Cloud GTM — Hybrid Consumption Model

> **Terminology:** Throughout this spec, **ACV** (Annual Contract Value) refers to the contracted annual commitment. **Consumption ACV** (Consumed ACV) is the portion of ACV backed by actual platform usage. The two are distinct: ACV is what was sold; Consumption ACV is what is being consumed.

**Version:** 1.0  
**Owner:** Principal PM, Analytics & AI  
**Stakeholders:** VP of Sales, CFO  
**Status:** Proposed — pending executive alignment  
**Last Updated:** May 2026  
**Prototype:** Run locally with `streamlit run dashboard/app.py`

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

## 2. The North Star Metric: Consumption ACV

### 2.1 Definition

**Consumption ACV is the portion of contracted ACV (Annual Contract Value) that is backed by actual platform usage.**

It answers the question: *"Of the revenue we've booked, how much is the customer actually consuming?"*

> **Naming note:** Consumption ACV is an *imputed run-rate*, not recognized revenue. It equals `ACV × consumption_rate` and will not reconcile to PANW's reported ARR. Finance should treat it as a GTM health and forecasting metric — distinct from GAAP revenue recognition. If used in any materials shared with investors, we can label it as "Consumption ACV (GTM metric)" to prevent confusion with reported ARR. **ACV** is used throughout this spec for the contracted annual value; it carries no GAAP connotation and will not cause confusion with recognized revenue.

> **Comp audit trail requirement:** Any Consumption ACV figure feeding a compensation calculation must be traceable to an immutable audit record that includes the pipeline run timestamp, pipeline version, and a before/after delta for any retroactive correction. Before integrating with a compensation platform, Finance and RevOps must define the correction workflow, approval chain, and rep dispute resolution process (see §13 Q8). Retroactive Consumption ACV corrections after commission payment require CFO sign-off. The full audit trail data model — `pipeline_run_log`, `fact_cacv_corrections`, ownership history, and contract amendment tables — is specified in the Technical Spec §3.2–3.3. The rep dispute resolution workflow and correction approval chain must be defined by Finance and RevOps before comp platform integration (see §13 Q8).

### 2.2 Formula

```
Consumption ACV     = ACV × consumption_rate(W)

Consumption Overage = MAX(Consumption ACV − ACV, 0)

consumption_rate(W) = trailing_W_avg(monthly_credits_consumed / included_monthly_compute_credits)
```

**Where:**
- `ACV` (`annual_commit_dollars`) — the annualized contract value from the account's active contract
- `monthly_credits_consumed` — sum of Prisma Cloud credits consumed from `daily_usage_logs` for the calendar month
- `included_monthly_compute_credits` — the monthly Prisma Cloud credit allowance from the `contracts` table
- `W` — lookback window; see table below. **For compensation and quota attainment, W = 90 days is the v1 assumption** (see Key Assumptions §2.2.2). This may be revisited by segment in v2: Enterprise accounts have longer deployment cycles that may benefit from a longer smoothing window; SMB accounts have more volatile usage patterns that may call for a shorter one.

#### 2.2.1 Standard Reporting Windows

The formula is intentionally window-agnostic. Three standard values of W are supported and stored in the pipeline:

| Window | Label | Use case | Characteristic |
|---|---|---|---|
| **7 days** | Weekly monitoring | AE / CS daily ops, early-warning alerts | Most responsive; noisier — single-week anomalies (holidays, migrations) can distort |
| **30 days** | Monthly review | MBR, monthly ops cadence | Balance of recency and stability |
| **90 days** | Quarterly · **comp default** | QBR, quota attainment, exec reporting, board metrics | Smooths seasonal variance; aligned to PANW quarterly comp cycle |

> **Window and comp integrity (v1 assumption):** Consumption ACV for quota attainment and compensation uses W = 90 days. This is a v1 policy assumption — shorter windows are gameable (a rep could coach a customer to spike credit burn in the final week of a quarter) and are more easily distorted by one-off events like migration weekends or holiday shutdowns. The 7-day and 30-day rates are stored alongside the 90-day rate for monitoring purposes and are explicitly labeled when surfaced in the dashboard or in reporting. Any report citing a non-90d Consumption ACV must carry a disclosure note. Segment-specific windows (e.g., a longer window for Enterprise, shorter for SMB) are a v2 consideration pending 12+ months of consumption data.

> **Annual lookback for YoY reporting:** The three standard windows above serve operational and comp purposes. For year-over-year Board and investor reporting, a trailing-12-month (annual) average consumption rate is standard practice — Snowflake, for example, publishes trailing-12-month consumed revenue as a Board metric. Whether PANW should publish a trailing-12-month Consumption ACV figure alongside the 90-day comp window is a CFO decision. v1 retains sufficient history to compute this figure once 12 months of data accumulate; no pipeline changes are required.

**Consumption Overage** is a derived metric — the portion of consumption above the contracted commit. It is always zero for accounts consuming at or below 100%, and positive for over-consuming accounts. Note that above-commit usage is billed at the Pay-As-You-Go (PAYG) list rate, so Consumption Overage underestimates the actual incremental revenue from overage; it is best treated as a demand signal rather than a revenue figure.

### 2.2.2 Key Assumptions (v1)

The following are explicit v1 design decisions, not empirically validated parameters. Each should be reviewed after 12–18 months of data or when expanding to new segments.

| Assumption | v1 Value | Rationale | Segment / v2 note |
|---|---|---|---|
| Sales comp lookback window (W) | 90 days | Aligns with PANW quarterly comp cycle; smooths seasonal variance; not gameable within a single quarter | Enterprise/Mid-Market/SMB may warrant different windows in v2 |
| New account ramp window | 90 days | Minimum history for a reliable trailing average; consistent with the 90-day comp window | May extend to 120 days for large Enterprise deployments in v2 |
| Activation bonus threshold | ≥ 80% consumption by month 6 (Enterprise: month 9) | Sustained adoption signal; month 6 prevents Spike & Drop gaming | Threshold not validated against PANW renewal data |
| Expansion flag threshold | > 120% of committed ACV for 2+ consecutive months | Organic demand signal; two-month requirement filters one-off spikes | — |
| Health tier thresholds | 5% / 40% / 80% / 120% | Industry analogue starting points | Calibrate against actual renewal cohorts at 12–18 months |
| Org-wide Consumption ACV attainment target | ≥ 85% | See §9; calibrate as renewal data accumulates | — |

> **Open question — quota cap and expansion conversion:** For quota attainment purposes, Finance and Sales leadership may choose to cap Consumption ACV at a fixed percentage of ACV — for example, 120% — so that over-consuming accounts do not indefinitely inflate a rep's attainment in lieu of a commercial expansion conversation. The ideal outcome when a customer sustains consumption above their contracted commit is a formal expansion or true-up contract, not ongoing PAYG overage billing. Capping Consumption ACV attainment at (say) 120% of ACV creates a direct financial incentive for the rep to convert sustained over-consumption into a new, larger contract: once the cap is reached, additional attainment credit requires a signed expansion. This is additive to the Expansion Signal SPIF in §7.2 Mechanism 2. The formula above is intentionally uncapped to give a complete picture of platform consumption. See §13 Q11.

**Example:**

| Account | ACV | Consumption Rate | Consumption ACV | Consumption Overage |
|---|---|---|---|---|
| Healthy customer | $200K | 92% | $184K | — |
| Shelfware | $300K | 4% | $12K | — |
| Overage | $80K | 138% | $110K | $30K |
| New account (<90 days) | $150K | — | Excluded (ramping) | — |

### 2.3 Aggregation Levels

| Level | Definition |
|---|---|
| **Account Consumption ACV** | `annual_commit_dollars × consumption_rate` per account |
| **Rep Consumption ACV** | Sum of account Consumption ACV across all active accounts owned by the rep |
| **Region Consumption ACV** | Sum of rep Consumption ACV within a region |
| **Org Consumption ACV** | Total — the Board-level North Star |

> **Source data note:** Daily usage logs (`daily_usage_logs`) are recorded at the account × day level — each row is the total credits consumed by one account on one day. "Account Consumption ACV" applies the formula to that account using its rolling daily usage aggregated to a monthly average, then trailed across the lookback window W. The aggregation hierarchy above describes how account-level Consumption ACV values are summed upward — it does not imply a different granularity of source data. In v1, the data pipeline already produces all four levels on each run.
>
> Additional aggregation dimensions — by industry vertical, product module, contract cohort, or customer segment (Enterprise / Mid-Market / SMB) — could be added in v2 without changing the base formula. Whether those cut-points are operationally useful is an open question for Sales Ops and Finance; they are not required for v1.

### 2.4 Consumption ACV Coverage Rate

```
Consumption ACV Coverage Rate = Total Consumption ACV / Total ACV
```

> **Naming note:** This ratio is referred to as "Consumption ACV Attainment" in the dashboard and in §9 success criteria because it measures how much of the portfolio's contracted ACV has been "attained" through consumption. It is distinct from *quota attainment* (a rep's Consumption ACV vs. their quota target). In contexts where that distinction is unclear — board decks, investor materials — "Coverage Rate" or "Consumption Coverage" is the preferred label.

This is the headline health ratio for the CFO. A portfolio at 78% coverage means 22% of booked ACV is not yet backed by consumption — that dollar amount is the renewal exposure the CS team needs to address.

**The metric is ACV-weighted, not account-count-weighted.** A large shelfware account with $500K ACV at 4% consumption has far more impact on the portfolio rate than ten small healthy accounts at $10K ACV each. This is intentional — the CFO cares about dollar risk, not account count. For a worked example showing this weighting effect:

| Account | ACV | Consumption Rate | Consumption ACV | Notes |
|---|---|---|---|---|
| Enterprise A | $500K | 90% | $450K | Core platform customer |
| Enterprise B | $300K | 4% | $12K | Shelfware — drives most of the portfolio risk |
| Mid-Market C | $80K | 120% | $80K | Capped at ACV; Consumption Overage = $16K |
| Mid-Market D | $60K | 75% | $45K | Approaching At Risk threshold |
| SMB E | $40K | — | Excluded | Ramping — contract < 90 days |

**Portfolio (excluding Ramping):** Total ACV = $940K · Total Consumption ACV = $587K · **Coverage Rate = 62.4%**

Note that Enterprise B alone ($300K ACV at 4%) pulls the portfolio rate from ~87% down to ~62%. A coverage rate problem at the portfolio level almost always traces to a small number of large, low-consumption accounts — which is where CS and manager attention should focus first.

---

### 2.5 Intended Behavioral Drivers

Consumption ACV is designed to shift incentives at every layer of the GTM organization. The behaviors it is explicitly intended to reward — and suppress — are:

**Behaviors to reward**

| Behavior | How Consumption ACV Rewards It |
|---|---|
| Selling the right-sized deal | Overselling credits the customer won't use directly lowers Consumption ACV; reps are incentivized to right-size commits |
| Fast time-to-value | New accounts ramping to ≥80% consumption within 90 days trigger an activation bonus; slow onboarding costs attainment |
| Deep platform adoption | Reps who coach customers to expand workload coverage drive consumption rate up, lifting their Consumption ACV |
| Proactive renewal risk management | Account Managers' quota is tied to Consumption ACV, not just renewal bookings — they have a direct financial incentive to intervene on At Risk accounts before renewal |
| Expansion from genuine usage | Accounts consistently consuming more than 120% of their committed credits for 2+ months represent organic demand that has outgrown the contract; reps are credited for converting that signal into a larger deal. **v1 assumption:** the expansion motion requires a signed contract amendment or new order — PAYG overage alone does not qualify. This preserves the intent of Consumption ACV as a metric of *contracted* consumption, and ensures the rep's incentive is to formalize demand, not leave it in open-ended overage billing. Whether this is the right commercial process for PANW (vs. automatic true-up) is an open question for Sales and Finance. |
| Committing to longer contract terms | Longer multi-year contracts provide PANW with revenue visibility and reduce renewal overhead. This behavior is rewarded not by Consumption ACV itself (which is a trailing usage measure, not a forward commitment measure) but through a **paired mechanism**: a term multiplier on ACV quota credit (1.2×–1.5× for 2–5 years) applied at signing. The Consumption ACV comp weight then holds the rep accountable for the usage outcomes on that long-term deal. The two work together — the multiplier rewards the commitment, the consumption weight rewards the realization. |

**Behaviors to suppress**

| Behavior | How Consumption ACV Suppresses It |
|---|---|
| Overselling / shelfware deals | A $500K deal at 4% consumption contributes only $20K to Consumption ACV — the rep's attainment number reflects the shelfware reality |
| Sandbagging credits at renewal | Renewing flat on a low-consumption account doesn't improve Consumption ACV; the rep must drive adoption, not just resign the paper |
| Ignoring post-sale onboarding | Under a pure bookings model, the rep's job ends at signature. Under Consumption ACV, onboarding quality is in their comp |
| Selective renewal bias (prioritising easy renewals over at-risk accounts) | Without a consumption-based metric, an Account Manager is incentivized to renew the accounts most likely to renew on their own — healthy customers who would re-sign with minimal intervention — and avoid investing time in accounts that need a costly save play. Under a bookings-only model this is rational; the AM who focuses on Healthy accounts will hit quota without touching a single Inactive one. Consumption ACV changes this calculus: the 70% Consumption ACV weight means a portfolio full of at-risk, shelfware, and inactive accounts directly suppresses the AM's total attainment — even if every renewing Healthy account resigns. The AM cannot achieve full attainment by serving only easy renewals. |
| Pushing long terms on weak accounts | A rep who locks in a 5-year deal on a shelfware customer captures the 1.50× multiplier at signing — but poor Consumption ACV attainment across the portfolio suppresses their bookings commission rate via the accelerator, offsetting the gain |

**Known v1 gaming risk — Account Manager credit-burning:** Account Managers at 70% Consumption ACV weight are incentivized by raw consumption, which creates an inverse failure mode: pushing customers to run unnecessary scans, protect idle servers or decommissioned infrastructure, or otherwise burn credits without delivering security value. Consumption ACV cannot distinguish active threat response from passive credit burn. This is flagged as a v1 risk; an engagement quality signal (alerts acted on, policies deployed, active users) is the v2 mitigation. In v1, CS managers should watch for accounts with high consumption rate but low security outcomes — a pattern detectable through manual QBR review.

---

### 2.6 Retention and Churn as Secondary Metrics

Consumption ACV is the North Star, but retention and churn metrics provide the lagging validation that Consumption ACV is tracking the right thing. Together they form a leading/lagging system: **Consumption ACV attainment is observable today, in real time; NRR and GRR are only known at renewal, months later.** If the design is correct, high Consumption ACV attainment today should predict strong NRR at the next renewal cycle. Tracking both allows the team to validate — and over time recalibrate — whether the health tier thresholds and attainment targets in this spec are set correctly.

In plain terms: a portfolio where most accounts are actually using the platform they bought is a portfolio that will renew. A portfolio full of shelfware will not. Consumption ACV attainment makes that renewal signal visible before the renewal invoice lands.

**Net Revenue Retention (NRR)**

```
NRR = (Beginning ARR + Expansion ARR - Contraction ARR - Churned ARR) / Beginning ARR
```

- Consumption ACV attainment rate is the leading indicator; NRR at renewal is the outcome it should predict
- Target: Consumption ACV-based NRR forecast within ±10% of actual NRR (see §9 Success Criteria)
- PANW disclosed NRR of ~119–120% in FY2024 (*Palo Alto Networks Q2 FY2024 Earnings Call, Feb 2024*). PANW has not separately disclosed NRR for FY2025; their public reporting now centres on Next-Generation Security (NGS) ARR growth. GRR and logo churn are not publicly disclosed.
- An org-wide Consumption ACV attainment of ≥85% is a portfolio health floor, not a direct NRR target. The path from 85% attainment to 119%+ NRR requires the expansion engine: accounts in the Expansion tier (>120% consumption) drive net revenue above 100%. The 85% target sets a baseline for gross retention; NRR above 100% depends on how many of those healthy accounts grow. **The 85% ↔ 119% NRR connection should not be stated as a direct equivalence** — it is a hypothesis that 85% attainment creates the conditions (low churn, active expansion pipeline) that have historically produced PANW's NRR outcomes. This requires empirical validation once renewal cohort data accumulates (see v1 note below).

**Gross Revenue Retention (GRR)**

```
GRR = (Beginning ARR - Churned ARR - Contraction ARR) / Beginning ARR
```

- GRR strips out expansion, isolating pure churn and downsell risk
- Accounts in Shelfware or Inactive tier with renewals within 180 days are the primary GRR risk pool
- ACV at risk (sum across at-risk tier accounts) is the GRR exposure number the CFO monitors

**Logo Churn Rate**

```
Logo Churn = Accounts lost at renewal / Total accounts up for renewal
```

- A secondary signal for CS prioritization — high Consumption ACV attainment should correlate with low logo churn
- Spike & Drop accounts (those flagged for a spike-and-drop consumption pattern) are the highest-risk cohort for logo churn; they consumed heavily at onboarding but have since gone dark

**The leading/lagging relationship**

In a BI implementation this table should be colour-coded: green rows indicate signals that predict strong retention outcomes; red rows indicate risk signals. Both directions are shown here.

| Direction | Consumption ACV Signal | Lagging Metric Outcome |
|---|---|---|
| ✅ Positive | Org attainment ≥ 90% and trending up | Strong NRR at next renewal cycle; expansion pipeline active |
| ✅ Positive | Shelfware + Inactive rate falls below 5% | GRR improvement within 2 quarters; fewer save plays required |
| ✅ Positive | Expansion flag conversion ≥ 30% within 180 days | NRR accelerates above 100%; net-new logo dependency decreases |
| ✅ Positive | ≥ 80% of ramping accounts reach Healthy tier within 90 days | Low logo churn at first renewal; strong activation cohort |
| ⚠️ Risk | Org attainment falls below 80% | NRR compression at next renewal cycle |
| ⚠️ Risk | Shelfware + Inactive rate exceeds 10% | GRR deterioration within 2 quarters |
| ⚠️ Risk | Expansion flag conversion < 30% | NRR plateaus; growth depends entirely on new logos |
| ⚠️ Risk | Ramping accounts fail to reach Healthy in 90 days | Elevated logo churn at first renewal |

> **v1 note:** The NRR outcome bands in the prediction table above (≥90% → strong renewal, etc.) are starting hypotheses derived from industry analogues, not PANW-specific renewal data. Treat them as directional guidance for v1. The primary value of this framework is establishing the *measurement habit* — tracking Consumption ACV attainment alongside NRR outcomes at every renewal cohort — so the bands can be empirically recalibrated after 12–18 months. Plan a formal calibration milestone; commit to adjusting thresholds if the data contradicts them.

Tracking both Consumption ACV (real-time) and NRR/GRR (at renewal) allows the team to validate — and over time calibrate — whether the health tier thresholds and attainment targets in this spec are set correctly.

---

## 3. Prisma Cloud Credit Pricing Model

Credits are the unit of value in every Prisma Cloud contract. The monthly credit allowance is derived from ACV at deal signing.

| Edition | Deal Profile |
|---|---|
| **Business Edition** | Mid-Market, 1-year term, no volume discount |
| **Enterprise Edition** | Enterprise, 2–3 year platform deal, ~30% volume discount typical |
| **Overage (PAYG)** | Above-commit usage billed at Business list rate |

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

- **85% of software companies** now offer some form of usage-based pricing. Among the largest software companies, 77% have incorporated consumption elements into their revenue model. *([Metronome, State of Usage-Based Pricing 2025](https://metronome.com/state-of-usage-based-pricing-2025))*
- **SAP** announced in 2025 it is moving away from per-user and subscription pricing toward AI consumption-based billing as AI agents automate core enterprise workflows. CEO Christian Klein: *"It would be foolish to still charge subscription base, because AI is so powerful that it will automate a lot of tasks."* *([erp.today, 2025](https://erp.today/sap-shifts-to-ai-consumption-pricing-as-agents-threaten-saas-revenue-model/))*
- **Salesforce** CEO Marc Benioff: *"We have per-user products which are for humans. And we have consumption products, they are for agents and robots."* — signaling the shift even in legacy SaaS. *([Metronome, State of Usage-Based Pricing 2025](https://metronome.com/state-of-usage-based-pricing-2025))*

**Within cybersecurity specifically:**

| Vendor | Consumption Unit | Model |
|---|---|---|
| Microsoft Sentinel | GB ingested | Pure consumption — $2–4/GB; no seat floor |
| Lacework | Workload-hours | Usage-based CNAPP; scales with cloud footprint |
| CrowdStrike | Endpoints + flex credits | Seat base + flex consumption for AI/XDR modules |
| Wiz | Cloud workloads | Workload-count pricing tied to environment size |
| **[PANW Prisma Cloud / Cortex Cloud](https://www.paloaltonetworks.com/blog/2025/02/announcing-innovations-cortex-cloud/)** | Compute credits | **Hybrid — committed ACV + consumption overlay** |

PANW's credit model sits at the sophisticated end of this spectrum: unlike pure per-seat models it reflects *realized* security coverage, and unlike pure PAYG it provides revenue predictability for both the customer and PANW.

### 4.2 Comparable Metrics at Peer Companies

| Company | Consumption Unit | Equivalent Metric |
|---|---|---|
| [Snowflake](https://www.snowflake.com/en/data-cloud/pricing-options/) | Credits | Consumed Revenue = credits used × price/credit |
| [Databricks](https://www.databricks.com/product/pricing) | DBUs | Consumed ACV = annualized trailing DBU usage |
| [MongoDB](https://www.mongodb.com/pricing) | Queries/ops | Incremental ACV above usage baseline |
| [OpenAI](https://openai.com/api/pricing/) / [Anthropic](https://www.anthropic.com/pricing) | Tokens | Revenue recognized on actual token consumption |
| **[PANW Prisma Cloud](https://www.paloaltonetworks.com/blog/2025/02/announcing-innovations-cortex-cloud/)** | Prisma Cloud Credits | **Consumption ACV = ACV × consumption_rate** |

**Snowflake precedent on compensation weighting:**
- New/greenfield reps: 70% bookings / 30% consumption
- Mature territory reps: 30% bookings / 70% consumption

---

## 5. Health Tier Classification

While Consumption ACV is a continuous metric, health tiers provide operational clarity for CS and sales prioritization:

| Health Tier | Consumption Rate | Interpretation | Action |
|---|---|---|---|
| **Expansion** | > 120% | Consistently over commit — upsell signal | Rep-led expansion motion |
| **Healthy** | 80–120% | On-track, full value realization | Maintain cadence |
| **At Risk** | 40–80% | Adoption lag — intervention needed | CS escalation within 30 days |
| **Shelfware** | 5–40% | Low utilization — churn risk | Executive sponsor outreach |
| **Inactive** | < 5% | Near-zero usage | Immediate save plan |
| **Ramping** | < 90 days old | Insufficient history | Excluded from Consumption ACV; tracked separately |

Health tiers are used for **dashboard visualization and CS prioritization only** — Consumption ACV itself uses the raw continuous consumption rate, not tiered multipliers.

> **v1 note:** The thresholds above (5% / 40% / 80% / 120%) are starting hypotheses, not empirically validated cutoffs. They are reasonable starting points based on industry analogues but have not been tested against PANW renewal cohort data. Plan a calibration review at 12–18 months once sufficient renewal outcomes are available. Thresholds should not be used as performance targets until validated.

---

## 6. Edge Case Handling

| Anomaly | Business Signal | Consumption ACV Treatment |
|---|---|---|
| **Shelfware** | Near-zero consumption rate over trailing 90 days | Consumption ACV reflects near-zero value; account flagged for save plan |
| **Spike & Drop** | Mass onboarding in month 1, then consumption collapses | Trailing 90-day window smooths the spike; correctly reflects current inactive state once spike ages out |
| **Consistent Overages** | Over-consuming commit for 2+ consecutive months | Consumption Overage reported separately; expansion flag surfaced to rep for upsell motion |
| **Mid-Year Expansion** | Customer signs additional contract before original expires | ARR and credits summed across all simultaneously active contracts; expansion flag set |
| **Orphaned Usage** | Usage logs reference an account not in the customer master | Excluded from Consumption ACV; surfaced in data quality report |
| **Out-of-contract Usage** | Usage logged before contract start or after contract end | Excluded from consumption rate calculation |
| **New Accounts** | Contract start within last 90 days — insufficient consumption history | Excluded from Consumption ACV; shown as "Ramping" until 90-day window matures |
| **Multi-year Contracts** | 2- or 3-year deal term | ACV used as-is (already annualized in contract); term stored for renewal forecasting and comp multiplier. See §12 for v1 ACV basis decision |

---

## 7. Proposed Compensation Framework

**Design principle:** Rather than giving Consumption ACV its own quota bucket that reps deprioritize, attach Consumption ACV outcomes to the thing each role already maximizes — bookings commission rate for AEs, portfolio health for AMs. The quota split is the floor; the accelerators and bonuses below are where behavioral change actually happens.

> **Context:** PANW currently pays AEs on full TCV (Nikesh Arora, Q2 FY2024 earnings: *"our salespeople still get paid on TCV...they're still going to do a three-year deal or a five-year deal"*). This framework is a deliberate departure — TCV comp rewards signing without accountability for consumption. Consumption ACV comp reform is the thesis of this spec.

> **Assumptions note:** The role structure, time allocations, and rules of engagement in §7.0 are modelled on broadly accepted enterprise SaaS patterns (Snowflake, industry benchmarks) and are intended as a starting framework, not a description of PANW's current sales org. PANW's actual AE and AM role definitions, existing compensation plans, territory ownership rules, and handoff processes may differ materially. Before this framework is adopted, the ROE definitions in §7.0.3 in particular — holding periods, expansion credit splits, renewal residuals, and poaching protection — will need to be reviewed and validated against PANW's existing comp agreements, Salesforce ownership model, and HR/legal requirements. These details should be worked through with VP of Sales, Sales Operations, and Finance before v1 rollout.

### 7.0 Role Definitions and Rules of Engagement

#### 7.0.1 Role Mandates

Two distinct roles own the GTM motion for Prisma Cloud accounts. The division is intentional — a single rep owning both acquisition and long-term consumption creates conflicting incentives: close fast vs. close right.

**Account Executive (AE) — Responsible for acquiring new business**

The AE's mandate is to acquire net-new logos and set them up for long-term consumption success. They are accountable for:

- Identifying, prospecting, and closing new Prisma Cloud accounts
- Right-sizing the initial credit commit — avoiding oversell that creates shelfware from day one
- Driving early platform activation through the 90-day ramp window
- Coordinating the CS and AM handoff before the holding period ends

The AE is not accountable for long-term retention after the holding period. Consumption accountability is specific to the accounts they close, measured through the activation bonus and their 30% Consumption ACV OTE weight.

**Account Manager (AM) — Responsible for growing existing business**

The AM's mandate is to maximize the long-term value of existing accounts through consumption growth, renewals, and expansion. They are accountable for:

- Maintaining and growing portfolio Consumption ACV attainment
- Renewing accounts at or above current ACV
- Surfacing Consumption Overage signals and coordinating upsell with AEs
- Executing save plans on At Risk, Shelfware, and Inactive accounts

The AM is not accountable for closing net-new logos. Their bookings accountability is limited to renewals and expansions within their existing portfolio.

**Sales Engineer (SE) — Responsible for driving platform consumption**

The SE is the technical overlay — responsible for workload instrumentation, onboarding acceleration, and identifying underutilized capabilities that would raise the consumption rate. Their OTE is 100% tied to consumption outcomes.

---

#### 7.0.2 How Each Role Spends Their Time

**Account Executive — indicative weekly allocation**

| Activity | ~% of Time | What This Looks Like |
|---|---|---|
| Pipeline development and new logo pursuit | 45% | Prospecting, SDR coordination, outbound, pipeline reviews |
| Active deal management | 35% | Discovery, demos, POC oversight, negotiation, close |
| Post-close activation (within holding period) | 15% | Onboarding coordination, ramp consumption monitoring, activation bonus tracking |
| Internal / CRM / forecasting | 5% | Salesforce hygiene, forecast calls, comp platform |

**Account Manager — indicative weekly allocation**

| Activity | ~% of Time | What This Looks Like |
|---|---|---|
| Portfolio health management | 35% | Consumption monitoring, health tier review, proactive outreach on At Risk accounts |
| Renewal pipeline management | 25% | Accounts renewing within 180 days — qualification, negotiation, save plays |
| Expansion surfacing and upsell coordination | 20% | Identifying Consumption Overage signals, briefing AEs on upsell candidates, QBR prep |
| Executive relationship management | 15% | QBRs, executive sponsor alignment, CS escalation support |
| Internal / CRM / forecasting | 5% | Salesforce hygiene, forecast calls, comp platform |

---

#### 7.0.3 Account Ownership and Rules of Engagement

**New logo:** AE owns from initial contact through close and the full holding period.

**Holding period:** After signing, the AE retains primary ownership and all expansion credit for:

| Segment | Holding Period |
|---|---|
| Mid-Market (ACV < $250K or 1-year term) | 6 months post-close |
| Enterprise (ACV ≥ $250K or multi-year term) | 12 months post-close |

The holding period floor is the average time for a Prisma Cloud deployment to reach full instrumentation. Handing off before the customer is live increases early churn risk and breaks the relationship continuity built during the sales cycle. During the holding period, the AM shadows the account — attending QBRs, reviewing consumption data, building executive relationships — but does not carry the account on their quota until formal handoff.

**Handoff:** At the end of the holding period, the AE transfers ownership to the AM. This requires a joint handoff call (AE + AM + customer executive sponsor), transfer of discovery notes, deal history, open commitments, and any red flags from the sales cycle, and Salesforce ownership updated.

**Post-handoff expansion:** Once an account is AM-owned, the AM surfaces the opportunity; the AE is brought in to close it. Bookings credit goes to the AE on the expansion deal; the AM earns the Expansion Signal SPIF for surfacing it (§7.2 Mechanism 2).

**Renewal:** AM-owned. The original closing AE receives a residual of 1–2% of ACV on named account renewals — consistent with enterprise SaaS benchmarks — but the renewal is the AM's quota responsibility.

**Poaching protection:** AEs cannot prospect into an account on an AM's quota book. If a net-new subsidiary or business unit of an AM-owned account is identified as a new opportunity, the AE and AM co-own the pursuit and split bookings credit at a ratio agreed by their shared manager.

**Ownership model rationale:** This framework uses a dedicated AM layer to own renewals and expansion while AEs focus exclusively on new logos. This is the right choice for Prisma Cloud at this stage: contract complexity is high (multi-year platform deals with credit structures), competitive intensity at renewal is meaningful (Wiz, CrowdStrike, Microsoft Sentinel are all active), and the CS team does not yet have the commercial capacity to own complex renewal negotiations independently. *(ClientSuccess, [Who Should Own SaaS Renewals](https://www.clientsuccess.com/resources/who-should-own-saas-renewals))*

---

#### 7.0.4 OTE Split

| Role | Bookings Weight | Consumption ACV Weight | Rationale |
|---|---|---|---|
| **Account Executive (AE)** | 70% | 30% | Primary responsibility is acquiring new business; consumption accountability is for the accounts they close |
| **Account Manager (AM)** | 30% | 70% | Primary responsibility is growing existing business; measured on portfolio health and retention |
| **Sales Engineer (SE)** | 0% | 100% | Purely accountable for consumption growth; no quota on bookings |

> **Snowflake precedent:** Snowflake uses an identical split — 70% bookings / 30% consumption for new logo AEs, shifting to 30% bookings / 70% consumption for AMs managing mature territories. The weights in this spec match that benchmark directly. *(Snowflake, [Sales Compensation in a Consumption Pricing World](https://www.snowflake.com/en/blog/sales-compensation-in-a-consumption-pricing-world/))*

---

### 7.1 AE Incentive Mechanisms

The primary incentive lever is the **70/30 OTE split defined in §7.0** — 30% of an AE's variable comp is tied directly to Consumption ACV attainment across their held accounts. A rep whose portfolio sits at 50% consumption attainment has lost half of their consumption OTE. No separate multiplier is needed; the weight does the work.

Two mechanisms sharpen the edges:

**Mechanism 1 — Activation bonus at month 6 (Enterprise: month 9)**

Any AE whose new account sustains ≥80% consumption rate through month 6 earns a one-time SPIF. The 6-month requirement prevents Spike & Drop gaming — paying at 90 days rewards a burst of onboarding activity that may not last. Month 6 requires sustained adoption.

**Exception for Enterprise accounts (ACV ≥ $250K or contract term ≥ 2 years):** the evaluation window extends to month 9. Large enterprise deployments span multiple cloud providers, business units, and compliance domains — full instrumentation takes longer. A month 6 check-in is still required for coaching, but the SPIF is earned at month 9 if ≥80% is sustained at that point.

**Mechanism 2 — Portfolio floor**

An AE cannot earn above 100% OTE if portfolio Consumption ACV attainment is below 60%. Prevents a rep from focusing exclusively on new logos while leaving a book full of shelfware unattended.

**Inherited-territory carve-out:** A rep who assumed ownership of accounts within the last 90 days is evaluated on the *improvement* in portfolio Consumption ACV from their inherited baseline, not the absolute attainment level. Requires VP of Sales sign-off to activate; tracked separately in the compensation platform.

### 7.2 AM Incentive Mechanisms

**Mechanism 1 — Quarterly Consumption ACV attainment (primary lever)**

Account Managers are paid quarterly on Consumption ACV attainment across their portfolio, not on renewal bookings. A single account is insufficient to hit quota by design — the AM needs a healthy portfolio. Base quota = maintain current attainment; stretch quota = grow portfolio Consumption ACV by X% through adoption and expansion.

**Mechanism 2 — Expansion signal bonus**

When an account starts generating over-consumption signal (consuming consistently above 100% of committed ACV), the AM earns a SPIF for surfacing the upsell opportunity — independent of whether the AE closes the expansion deal. This creates a direct financial incentive to flag over-consuming accounts proactively rather than waiting for the AE to notice.

*Rationale:* Consumption Overage is the AM's most valuable output after retention. Without a bonus, AMs have no incentive to surface it — the upside goes to the AE who closes the upsell.

### 7.3 Multi-Year ACV and Rep Credit

ACV is always the annualized value: a 3-year, $360K TCV deal has an ACV of $120K/year. The Consumption ACV denominator is always the current year's ACV. PANW platformization deals typically run 3–5 years (Arora, Q2 FY2024).

Quota credit for multi-year deals uses a **term multiplier** — meaningful incentive to lock in longer commits, without the quota-busting effect of full TCV credit:

| Contract Term | ACV Quota Credit | vs. Full TCV |
|---|---|---|
| 1 year | 1.00× ACV | = TCV |
| 2 years | 1.20× ACV | 40% less than TCV |
| 3 years | 1.35× ACV | 55% less than TCV |
| 5 years | 1.50× ACV | 70% less than TCV |

*Why not full TCV?* A 3-year $300K ACV deal at full TCV gives 128.6% of a $700K bookings quota on a single customer — the AE has no reason to pursue new logos. At 1.35× ACV, the same deal gives 57.9%, keeping the AE focused on new business while rewarding the multi-year commit. *(Modeled in `comp_model.xlsx`.)*

**Account ownership through multi-year terms:** The AE receives term multiplier credit at signing. From Year 2 onward, the AM earns Consumption ACV attainment credit. If the account churns before term end, a portion of the term multiplier is subject to clawback. Clawback terms and handoff timing require VP of Sales sign-off (see §13 Q10).

### 7.4 Phasing

| Mechanism | v1 | v2 |
|---|---|---|
| Role definitions and rules of engagement (§7.0) | ✓ | — |
| OTE split (70/30 AE, 30/70 AM) | ✓ | — |
| Term multiplier | ✓ | — |
| Activation bonus (month 6 / month 9) | ✓ | — |
| Portfolio floor (60% attainment gate) | ✓ | — |
| Expansion signal bonus for AMs | ✓ | — |
| Territory profile differentiation (greenfield vs. mature weighting) | — | ✓ (adjust OTE split based on territory maturity after 2+ quarters of data) |

v1 establishes the foundational structure — clean role separation, the OTE split as the primary behavioral lever, and the two AE mechanisms that reward activation and prevent portfolio neglect. v2 introduces territory-level weighting refinements once there is sufficient Consumption ACV history to segment territories by maturity.

**Out of scope:** Compensation design for channel partners and CSMs is a separate workstream not addressed in this spec.

---

## 8. Quota Setting and Forecasting

### 8.1 Quota Setting with Consumption ACV

Consumption ACV enables quota design that reflects territory health, not just last year's bookings:

**Account Executive (AE) quotas — quality of sale**
- Quota includes a Consumption ACV ramp component: the new logo must reach a minimum consumption rate (e.g. ≥ 70%) within 90 days of go-live to count as full credit toward attainment
- This directly prices in onboarding quality and discourages overselling credits a customer won't use

**Account Manager (AM) quotas — incremental Consumption ACV**
- Base quota = maintain current Consumption ACV attainment rate across the portfolio
- Stretch quota = grow total Consumption ACV by X% through expansion and improved utilization
- Account Managers are measured on *incremental Consumption ACV* above baseline each quarter, not bookings — consumption growth driven by their activity, not contract auto-renewal

**Territory sizing and rebalancing**
- Use total Consumption ACV per rep to identify overloaded territories (high Consumption ACV, low headroom for growth) vs. underloaded ones (low Consumption ACV, high ACV at risk needing intervention)
- Reassign accounts based on Consumption ACV capacity, not just account count or ARR — a rep carrying 20 Inactive accounts needs different support than one carrying 20 Healthy accounts

---

### 8.2 Forecasting with Consumption ACV

Consumption ACV provides two distinct forecasting signals: **renewal risk** (defensive) and **expansion pipeline** (offensive).

**Renewal risk forecast**
- ACV at risk (ACV minus Consumption ACV) is the dollar value of committed ACV not backed by consumption
- Accounts in the At Risk, Shelfware, or Inactive health tiers with a renewal within 90–180 days are the highest-priority save plays
- The org-level ACV at risk total is the CFO's leading indicator: if it trends above ~15% of total ACV, NRR will compress at the next renewal cycle

**Expansion pipeline forecast**
- Accounts flagged for expansion (2+ consecutive months >120% consumption) have proven demand beyond their current commit — these are high-confidence upsell candidates
- Expansion pipeline value (sum of ACV for flagged accounts) quantifies the near-term expansion opportunity the team should be working

**NRR prediction**
- Trailing Consumption ACV attainment rate is a leading indicator of net revenue retention at renewal:

| Trailing Consumption ACV Attainment | Expected NRR Outcome |
|---|---|
| ≥ 90% | Strong renewal; likely expansion |
| 70–90% | Renewal probable; flat or slight compression |
| 50–70% | Renewal at risk; CS intervention required |
| < 50% | High churn probability; executive save plan |

- Target: Consumption ACV-based NRR forecast within ±10% of actual NRR at renewal (see §9 Success Criteria)

**Cohort-based calibration (v2)**
- Once sufficient renewal cohorts accumulate (12–18 months of data), regression against actual churn outcomes will allow the thresholds above to be empirically validated and refined per segment (Enterprise vs. Mid-Market) and industry vertical

---

## 9. Success Criteria



| KPI | Target | Window |
|---|---|---|
| Org-wide Consumption ACV Attainment | ≥ 85% | Rolling 90 days |
| Shelfware rate | ≤ 8% of active accounts | Monthly |
| Expansion flag conversion | ≥ 30% of flagged accounts → upsell within 180 days | Semi-annual |
| New account activation | ≥ 70% reach Healthy tier within 90 days of go-live | Quarterly |
| Consumption ACV forecast accuracy vs. actual NRR | Within ± 10% | At annual renewal |
| Pipeline data freshness | Snapshot ≤ 24 hours old at time of dashboard load | Every pipeline run |
| Data quality test pass rate (ERROR tier) | 100% — zero ERROR failures | Every pipeline run |

> **Note on shelfware threshold:** The data quality test in `dq_tests.py` alerts at >15% shelfware rate (a data integrity floor). The 8% target above is a performance ceiling — the org should be well below the alert level. If shelfware rate is between 8% and 15%, it requires a sales operations review; above 15%, it triggers the automated data quality alert and escalation to the data engineering team.

---

## 10. v1 Scope

This section makes explicit what is and is not in scope for the initial launch of Consumption ACV. The metric is designed to ship, not to be perfect.

### In scope for v1

- Consumption ACV calculation at account, rep, region, and org level
- Health tier classification (6 tiers) based on trailing 90-day consumption rate
- Expansion signal dollars as a separate metric for over-consuming accounts (Consumption ACV itself capped at commit)
- AE / AM comp weighting (bookings vs. Consumption ACV), with activation bonus at month 6 and multi-year term multiplier
- Executive dashboard with 4 views (portfolio overview, region, rep leaderboard, account detail)
- Downstream signals to Salesforce CRM, compensation platform, CS platform, and BI layer
- Data quality framework (11 automated assertions) with orphaned and rogue usage handling
- Multi-year contract treatment: Year 1 ACV as the Consumption ACV basis *(v1 decision — see §13)*

### Explicitly out of scope for v1

| Out-of-scope item | Rationale | Where it goes |
|---|---|---|
| Channel partner / SE / CSM comp design | Distinct quota structures and attribution rules; separate workstream | Separate spec |
| Engagement quality signal (active usage vs. passive credit burn) | Requires additional instrumentation (login events, alert actions); acknowledged v1 risk | v2 roadmap |
| Real-time consumption updates | Daily batch sufficient for v1; near-real-time adds infra complexity | v2 roadmap |
| Health tier threshold calibration | Requires 12–18 months of renewal cohort data to validate | v2 milestone |
| NRR prediction band validation | Same dependency on renewal cohort data | v2 milestone |
| Multi-region currency normalization | Not relevant to current territory structure | v2 if needed |
| Consumption ACV as an externally reported metric | Requires audit trail, definition consistency, and investor alignment | CFO decision (§13 Q6) |

---

## 11. Executive Dashboard

**🔗 Prototype:** Run locally with `streamlit run dashboard/app.py` — no BigQuery credentials required, loads from the included synthetic data snapshot.

The Consumption ACV dashboard is the primary operational interface for sales leadership. It serves four distinct audiences, each with different questions and a different level of granularity.

---

### Audience 1: VP of Sales / CFO — Portfolio Overview

**Key questions:**
- How much of our booked ARR is actually being consumed?
- What is our total churn exposure right now, in dollars?
- Where is our expansion pipeline coming from?
- Which regions are healthy and which are lagging?

**Metrics needed:**
- Total ACV vs. total Consumption ACV and overall attainment rate
- ACV at risk (committed dollars not backed by consumption)
- Expansion pipeline (ARR from accounts consistently over-consuming)
- Consumption ACV attainment and account health mix broken out by region
- Rep attainment distribution — are outliers pulling the average, or is underperformance broad?

---

### Audience 2: Regional VPs / Sales Ops — Region Breakdown

**Key questions:**
- How does my region compare to others on Consumption ACV attainment?
- What percentage of my portfolio is at risk of churn?
- Which health tiers dominate my region — do I have a shelfware problem or an expansion opportunity?

**Metrics needed:**
- Consumption ACV, ACV, and attainment rate per region, ranked
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
- Rep-level Consumption ACV and attainment rate, ranked within region and org
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
- Per-account consumption rate (trailing 90 days), health tier, and Consumption ACV
- ACV at risk per account
- Expansion flag (2+ months over commit) and spike/drop anomaly flag
- Contract start and end dates for renewal timing context

*For implementation details — stack, data flow, caching strategy, and fallback behavior — see the Technical Spec §8.*

---

## 12. Downstream System Integrations

Consumption ACV is most valuable when it flows beyond the dashboard into the systems reps and CS teams work in every day. Four downstream systems consume Consumption ACV data, each serving a distinct audience and purpose.

---

### Salesforce CRM

**Primary audience:** Sales reps, sales managers, revenue operations

**Purpose:** Surface Consumption ACV health signals in the tool reps use daily — so they can act on consumption trends without leaving their workflow. Key outcomes:
- Account health tier is visible on every Account record, informing renewal conversations
- Accounts flagged for expansion automatically generate an Opportunity, ensuring the signal gets worked
- Accounts with anomalous consumption patterns (spike & drop, near-zero usage) are flagged for CS review before they become surprises at renewal
- Consumption ACV attainment drives the renewal forecast category (Commit / Upside / Risk), giving the CFO a consumption-grounded pipeline view

An important attribution rule: the rep who currently owns the account gets Consumption ACV quota credit, but the rep who originally signed the deal retains comp attribution for that contract. Both ownership records are maintained and synced to Salesforce separately.

---

### Compensation Platform (e.g., Xactly, CaptivateIQ)

**Primary audience:** Finance, sales reps, sales managers

**Purpose:** Ensure quota attainment and commission calculations reflect consumption performance, not just bookings. Key outcomes:
- Account Manager quota attainment is calculated from Consumption ACV, not renewal bookings — a rep who resigns a shelfware account at flat ACV does not receive full attainment credit
- Accelerator and decelerator tiers are triggered by Consumption ACV attainment rate, rewarding reps whose portfolios over-consume and penalizing persistent underperformance
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

**Purpose:** Enable board-level visibility into whether the consumption model is working — and provide the analytical foundation to validate and calibrate Consumption ACV thresholds over time. Key reports:
- **NRR forecast:** Org-wide Consumption ACV attainment as the leading indicator of next-period net revenue retention
- **Renewal risk register:** Accounts with high ARR at risk and near-term contract expirations, for executive review
- **Expansion pipeline:** Accounts consistently over-consuming, quantified by ARR, for offensive planning
- **Cohort churn analysis:** Consumption ACV attainment by contract start quarter — the primary tool for validating whether health tier thresholds accurately predict actual churn outcomes
- **QBR regional pack:** Consumption ACV vs. ARR by region and rep for quarterly business reviews

*For field-level mappings, sync frequencies, and integration architecture — see the Technical Spec §9.*

---

## 13. Open Questions for Executive Alignment

The following decisions require VP of Sales and/or CFO sign-off before Consumption ACV can be operationalized.

1. **Comp go-live timing** *(VP of Sales)* — Same-year comp launch or shadow-track for 1–2 quarters first before paying on it?
2. **Single vs. dual quota** *(VP of Sales)* — Single blended attainment number (bookings + Consumption ACV weighted) or two separate quota lines?
3. **Overage revenue recognition** *(CFO)* — Recognize Consumption Overage in-period or defer to contract amendment?
4. **Multi-year ACV basis** *(CFO)* — Confirm Year 1 ACV as the Consumption ACV denominator, or override with blended average annual value? *(v1 default: Year 1 ACV; ramp-structured deals flagged separately)*
5. **Phased vs. big-bang rollout** *(VP of Sales)* — Full launch across all regions or pilot one region/segment first?
6. **Quota relief for ramping accounts** *(VP of Sales)* — Do new accounts in the 90-day ramp window reduce the quota denominator during that period?
7. **Portfolio attainment floor** *(VP of Sales)* — Does sustained low Consumption ACV attainment (e.g., below 60% for two consecutive quarters) trigger a performance review independent of bookings?
8. **In-flight comp plan transition** *(VP of Sales + Finance)* — Are existing signed OTE plans honored to year-end, prorated, or renegotiated? *(highest change-management risk; legal review required)*
9. **Board and investor reporting readiness** *(CFO)* — What accuracy, cohort size, and audit readiness threshold triggers external disclosure of Consumption ACV?
10. **Multi-year account ownership and clawback** *(VP of Sales)* — When does the AE-to-AM handoff occur, and what portion of the term multiplier is clawed back if the account churns before term end?
11. **Consumption ACV cap for quota attainment** *(VP of Sales + Finance)* — Should Consumption ACV be capped at ACV when calculating quota attainment, so that over-consuming accounts cannot push a rep above 100% attainment on this metric alone? Capping preserves a clean "% of commit consumed" narrative; leaving it uncapped rewards over-consumption directly in the attainment number. Decision required before comp platform integration.

---

## 14. Sources

- Palo Alto Networks — [Q2 FY2024 Earnings Call Transcript, Feb 2024](https://investor.paloaltonetworks.com/news-releases/news-release-details/palo-alto-networks-reports-second-quarter-fiscal-2024-financial) — NRR ~119–120% disclosed; Nikesh Arora quote on TCV comp
- Metronome — [State of Usage-Based Pricing 2025](https://metronome.com/state-of-usage-based-pricing-2025)
- Palo Alto Networks — [Introducing Cortex Cloud (Feb 2025)](https://www.paloaltonetworks.com/blog/2025/02/announcing-innovations-cortex-cloud/)
- Palo Alto Networks — [Cortex Cloud Press Release](https://www.paloaltonetworks.com/company/press/2025/palo-alto-networks-introduces-cortex-cloud--the-future-of-real-time-cloud-security)
- erp.today — [SAP Shifts to AI Consumption Pricing (2025)](https://erp.today/sap-shifts-to-ai-consumption-pricing-as-agents-threaten-saas-revenue-model/)
- Dell'Oro Group — [The Shift from Prisma Cloud to Cortex Cloud](https://www.delloro.com/palo-alto-networks-reboots-cnapp-the-shift-from-prisma-cloud-to-cortex-cloud/)
- SiliconANGLE — [Cortex Cloud 2.0 and AgentiX (Oct 2025)](https://siliconangle.com/2025/10/28/palo-alto-networks-introduces-prisma-airs-2-0-cortex-cloud-2-0-agentix-secure-agentic-enterprise/)
- Snowflake — [Pricing Options](https://www.snowflake.com/en/data-cloud/pricing-options/)
- Databricks — [Pricing](https://www.databricks.com/product/pricing)
- MongoDB — [Pricing](https://www.mongodb.com/pricing)
- PeerSpot — [Prisma Cloud Pricing Reviews](https://www.peerspot.com/products/prisma-cloud-by-palo-alto-networks-pricing)
- Prisma Cloud — [Compute Edition Licensing Guide](https://docs.prismacloud.io/en/compute-edition/30/admin-guide/licensing/licensing)
