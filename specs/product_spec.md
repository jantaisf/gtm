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

## Executive Summary

Palo Alto Networks is transitioning Prisma Cloud to a hybrid consumption-based model where customers commit to an annual credit pool rather than a fixed seat count. This creates a measurement gap: two $500K contracts look identical in ARR yet can represent entirely different business realities — one fully consumed and on track to expand, the other untouched and quietly becoming a churn liability.

This spec defines **Consumption ACV** — the portion of contracted ACV backed by actual platform usage — as the North Star metric for the Prisma Cloud GTM organization. The headline portfolio measure, **Consumed ACV Rate** (Consumption ACV ÷ Total ACV), gives the CFO a forward-looking indicator of renewal health rather than a lagging revenue figure. In the worked example in §3.3, four active accounts produce $587K of consumed ACV against $940K booked — a 62.4% rate, with $353K in unconsumed ACV representing the renewal exposure the account team must close before contract renewal.

The spec covers: background and market context (§2); the full metric definition and formula (§3); health tier classification for every account from Expansion Signal to Churned (§4); quota setting and compensation implications (§6); a four-audience executive dashboard (§8); and downstream integrations with Salesforce, Xactly/CaptivateIQ, and Gainsight (§9). A working v1 prototype is available (`streamlit run dashboard/app.py`). Open questions requiring VP of Sales and CFO sign-off — including comp go-live timing, quota caps, and correction workflows — are documented in §11.

**Status: Proposed — pending executive alignment.**

---

## Table of Contents

- [1. Problem Statement](#1-problem-statement)
- [2. Background & Market Context](#2-background--market-context)
- [3. The North Star Metric: Consumption ACV](#3-the-north-star-metric-consumption-acv)
  - [3.1 Definition](#31-definition)
  - [3.2 Formula](#32-formula)
  - [3.2.2 Key Assumptions (v1)](#322-key-assumptions-v1)
  - [3.3 Consumed ACV Rate](#33-consumed-acv-rate)
  - [3.4 Aggregation Levels](#34-aggregation-levels)
  - [3.5 Intended Behavioral Drivers](#35-intended-behavioral-drivers)
  - [3.6 Retention and Churn as Secondary Metrics](#36-retention-and-churn-as-secondary-metrics)
- [4. Health Tier Classification](#4-health-tier-classification)
- [5. Lifecycle Management with Consumption ACV](#5-lifecycle-management-with-consumption-acv)
- [6. Quota Setting and Compensation](#6-quota-setting-and-compensation)
- [7. Success Criteria](#7-success-criteria)
- [8. Executive Dashboard](#8-executive-dashboard)
- [9. Downstream System Integrations](#9-downstream-system-integrations)
- [10. Scope and Roadmap](#10-scope-and-roadmap)
- [11. Open Questions for Executive Alignment](#11-open-questions-for-executive-alignment)
- [12. Sources](#12-sources)

---

## 1. Problem Statement

Palo Alto Networks is transitioning Prisma Cloud from an Annual Recurring Revenue (ARR) model to a hybrid consumption-based model, with credits corresponding to the resources protected and the features utilized.  This creates a critical measurement gap:

**ARR alone is no longer sufficient.** A $500K deal with zero credit consumption looks identical to a $500K deal with 95% utilization — yet they represent fundamentally different business realities. The first is a churn liability. The second is a healthy, expanding customer.

Sales leadership needs a single metric that:
- Reflects whether contracted revenue is being *realized* through platform usage
- Gives the CFO a leading indicator of renewal risk before it becomes churn
- Aligns sales rep incentives with long-term customer value, not just deal signing

---

## 2. Background & Market Context

Prisma Cloud contracts are denominated in **compute credits** — customers commit to an annual credit pool at signing (Business Edition: 1-year term; Enterprise Edition: 2–3 year, ~30% volume discount), and platform usage draws down against that pool daily. Consumption-based pricing is now the enterprise software standard: 85% of software companies offer some form of usage-based pricing *(Metronome, State of Usage-Based Pricing 2025)*, and peers like Snowflake and Databricks have built their GTM compensation models around trailing consumption metrics. As consumption models mature, GTM organizations are developing new metrics to measure whether contracted revenue is actually being realized — and to hold sales teams accountable for the full customer lifecycle, not just deal signing. This spec introduces Consumption ACV (§3) to address this gap for Prisma Cloud.

---

## 3. The North Star Metric: Consumption ACV

### 3.1 Definition

**Consumption ACV is the portion of contracted ACV (Annual Contract Value) that is backed by actual platform usage.**

It answers the question: *"Of the revenue we've booked, how much is the customer actually consuming?"*

> **Finance note:** Consumption ACV is an *imputed run-rate*, not recognized revenue. It equals `ACV × consumption_rate` and will not reconcile to PANW's reported ARR. Finance should treat it as a GTM health and forecasting metric — distinct from GAAP revenue recognition. If used in any materials shared with investors, we can label it as "Consumption ACV (GTM metric)" to prevent confusion with reported ARR. **ACV** is used throughout this spec for the contracted annual value; it carries no GAAP connotation and will not cause confusion with recognized revenue.

> **Comp audit trail requirement:** Any Consumption ACV figure feeding a compensation calculation must be traceable to an immutable audit record that includes the pipeline run timestamp, pipeline version, and a before/after delta for any retroactive correction. Before integrating with a compensation platform, Finance and RevOps must define the correction workflow, approval chain, and rep dispute resolution process (see §11 Q8). Retroactive Consumption ACV corrections after commission payment require CFO sign-off. The full audit trail data model — `pipeline_run_log`, `fact_cacv_corrections`, ownership history, and contract amendment tables — is specified in the Technical Spec §3.2–3.3. The rep dispute resolution workflow and correction approval chain must be defined by Finance and RevOps before comp platform integration (see §11 Q8).

### 3.2 Formula

```
Consumption ACV     = ACV × consumption_rate(W)

Consumption Overage = MAX(Consumption ACV − ACV, 0)

consumption_rate(W) = SUM(daily_credits_consumed over last W days)
                    / (included_monthly_compute_credits × W / 30)
```

**Where:**
- `ACV` (`annual_commit_dollars`) — the annualized contract value from the account's active contract
- `daily_credits_consumed` — credits consumed on a given day, from `daily_usage_logs` (one row per account per day)
- `included_monthly_compute_credits` — the monthly Prisma Cloud credit allowance from the `contracts` table; multiplied by W/30 to prorate the allotment to the exact window length
- `W` — lookback window; see table below. **For compensation and quota attainment, W = 90 days is the v1 assumption** (see Key Assumptions §3.2.2). This may be revisited by segment in v2: Enterprise accounts have longer deployment cycles that may benefit from a longer smoothing window; SMB accounts have more volatile usage patterns that may call for a shorter one.

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

### 3.2.2 Key Assumptions (v1)

The following are explicit v1 design decisions, not empirically validated parameters. Each should be reviewed after 12–18 months of data or when expanding to new segments.

| Assumption | v1 Value | Rationale | Segment / v2 note |
|---|---|---|---|
| Sales comp lookback window (W) | 90 days | Aligns with PANW quarterly comp cycle; smooths seasonal variance; not gameable within a single quarter | Enterprise/Mid-Market/SMB may warrant different windows in v2 |
| New account ramp window | 90 days | Minimum history for a reliable trailing average; consistent with the 90-day comp window | May extend to 120 days for large Enterprise deployments in v2 |
| Activation bonus threshold | ≥ 80% consumption by month 6 (Enterprise: month 9) | Sustained adoption signal; month 6 prevents Spike & Drop gaming | Threshold not validated against PANW renewal data |
| Expansion flag threshold | > 120% of committed ACV for 2+ consecutive months | Organic demand signal; two-month requirement filters one-off spikes | — |
| Health tier thresholds | 5% / 40% / 80% / 120% | Industry analogue starting points | Calibrate against actual renewal cohorts at 12–18 months |
| Org-wide Consumption ACV attainment target | ≥ 85% | See §7; calibrate as renewal data accumulates | — |

> **Open question — quota cap and expansion conversion:** For quota attainment purposes, Finance and Sales leadership may choose to cap Consumption ACV at a fixed percentage of ACV — for example, 120% — so that over-consuming accounts do not indefinitely inflate a rep's attainment in lieu of a commercial expansion conversation. The ideal outcome when a customer sustains consumption above their contracted commit is a formal expansion or true-up contract, not ongoing PAYG overage billing. Capping Consumption ACV attainment at (say) 120% of ACV creates a direct financial incentive for the rep to convert sustained over-consumption into a new, larger contract: once the cap is reached, additional attainment credit requires a signed expansion. The formula above is intentionally uncapped to give a complete picture of platform consumption. See §11 Q10.

**Example:**

| Account | ACV | Consumption Rate | Consumption ACV | Consumption Overage |
|---|---|---|---|---|
| Healthy customer | $200K | 92% | $184K | — |
| Shelfware | $300K | 4% | $12K | — |
| Overage | $80K | 138% | $110K | $30K |
| New account (<90 days) | $150K | — | Excluded (ramping) | — |

### 3.3 Consumed ACV Rate

```
Consumed ACV Rate = Total Consumption ACV / Total ACV
```

> **Ramping accounts are excluded from top-line numbers.** Accounts whose contract is less than 90 days old are in the ramp window and are excluded from both the numerator and denominator of the Consumed ACV Rate. Including them would artificially depress the portfolio rate — a customer who signed last week has had no meaningful time to consume credits. Ramping accounts are tracked separately and graduate into the main rate once the 90-day window closes. See §3.2.2 for the v1 ramp window assumption.

**The metric is ACV-weighted, not account-count-weighted.** A large shelfware account with $500K ACV at 4% consumption has far more impact on the portfolio rate than ten small healthy accounts at $10K ACV each. This is intentional — the CFO cares about dollar risk, not account count:

| Account | ACV | Consumption Rate | Consumption ACV | Notes |
|---|---|---|---|---|
| Enterprise A | $500K | 90% | $450K | Core platform customer |
| Enterprise B | $300K | 4% | $12K | Shelfware — drives most of the portfolio risk |
| Mid-Market C | $80K | 120% | $80K | Capped at ACV; Consumption Overage = $16K |
| Mid-Market D | $60K | 75% | $45K | Approaching At Risk threshold |
| **Portfolio total** | **$940K** | **62.4%** | **$587K** | |
| *SMB E (excluded)* | *$40K* | *—* | *—* | *Ramping — contract < 90 days* |

This is the headline health ratio for the CFO. A portfolio at **62.4%** means **$587K of the $940K booked ACV is being consumed — and $353K is not**. That $353K gap is the renewal exposure the account team must actively manage before contract renewal.

Note that Enterprise B alone ($300K ACV at 4%) pulls the Consumed ACV Rate from ~87% down to ~62%. A low Consumed ACV Rate at the portfolio level may trace back to a smaller number of low-consumption accounts — worth investigating before drawing broader conclusions.

### 3.4 Aggregation Levels

Both Consumption ACV and Consumed ACV Rate aggregate across the following hierarchy:

| Level | Definition |
|---|---|
| **Account** | `annual_commit_dollars × consumption_rate` per account; Consumed ACV Rate = that account's Consumption ACV / ACV |
| **Rep** | Sum of account Consumption ACV across all active accounts owned by the rep; Rep Consumed ACV Rate = Rep Consumption ACV / Rep ACV |
| **Region** | Sum of rep Consumption ACV within a region; Region Consumed ACV Rate = Region Consumption ACV / Region ACV |
| **Segment** | Sum of account Consumption ACV within a segment (Enterprise / Mid-Market / SMB); Segment Consumed ACV Rate = Segment Consumption ACV / Segment ACV — expected to differ materially across segments due to different deployment complexity and ramp timelines |
| **Org** | Total — the Board-level North Star; Org Consumed ACV Rate is the portfolio headline metric |
| **Cohort** | Sum of account Consumption ACV grouped by contract start quarter (e.g., all accounts signed in Q1 FY2025); the primary tool for detecting whether onboarding trends are improving or deteriorating over time. Cohort analysis is also the correct unit for validating health tier thresholds against actual renewal outcomes (see §3.6 v1 note). |

> **Why segment matters:** Enterprise, Mid-Market, and SMB accounts are likely to exhibit materially different ramp curves. Enterprise deployments span multiple business units and compliance domains and may take 6–9 months to reach steady-state consumption; SMB accounts may ramp faster but also drop off faster if the initial deployment is thin. A growing SMB mix can mask a deteriorating Enterprise rate (or vice versa), and a single Consumed ACV Rate target will be miscalibrated for at least one segment. v1 stores the data to compute segment-level rates; per-segment targets are a v2 calibration item once sufficient data has accumulated. See §3.2.2 Key Assumptions.

> **Source data note:** Daily usage logs (`daily_usage_logs`) are recorded at the account × day level — each row is the total credits consumed by one account on one day. `consumption_rate(W)` is computed by summing those daily rows over the last W days and dividing by the prorated W-day credit allotment (`included_monthly_compute_credits × W/30`). This means a 7-day window uses the last 7 days of actual usage against a 7-day allotment (not a monthly average), and a 90-day window uses the last 90 days against a 90-day allotment — consistent behavior at any window size. The aggregation hierarchy above describes how account-level Consumption ACV values are summed upward; it does not imply a different granularity of source data. In v1, the data pipeline already produces all levels on each run.
>
> Additional aggregation dimensions — by industry vertical or product module — could be added in v2 without changing the base formula. Whether those cut-points are operationally useful is an open question for Sales Ops and Finance; they are not required for v1.

---

### 3.5 Intended Behavioral Drivers

Consumption ACV is designed to shift incentives at every layer of the GTM organization. The behaviors it is explicitly intended to reward — and suppress — are:

**Behaviors to reward**

| Behavior | How Consumption ACV Rewards It |
|---|---|
| Selling the right-sized deal | Overselling credits the customer won't use directly lowers Consumption ACV; reps are incentivized to right-size commits |
| Fast time-to-value | New accounts ramping to ≥80% consumption within 90 days can trigger an activation bonus; slow onboarding costs attainment |
| Deep platform adoption | Reps who coach customers to expand workload coverage drive consumption rate up, lifting their Consumption ACV |
| Proactive renewal risk management | Account Managers' quota is tied to Consumption ACV, not just renewal bookings — they have a direct financial incentive to intervene on At Risk accounts before renewal |
| Expansion from genuine usage | Accounts consistently consuming more than 120% of their committed credits for 2+ months represent organic demand that has outgrown the contract; reps are credited for converting that signal into a larger deal. **v1 assumption:** the expansion motion requires a signed contract amendment or new order — PAYG overage alone does not qualify. This preserves the intent of Consumption ACV as a metric of *contracted* consumption, and ensures the rep's incentive is to formalize demand, not leave it in open-ended overage billing. Whether this is the right commercial process for PANW (vs. automatic true-up) is an open question for Sales and Finance. |
| Committing to longer contract terms | Longer multi-year contracts provide PANW with revenue visibility and reduce renewal overhead. This behavior can be reinforced through a paired mechanism in the comp plan — a term multiplier on ACV quota credit applied at signing — while the consumption weight holds the rep accountable for actual usage over the full term. The two work together: the multiplier rewards the commitment, the consumption weight rewards the realization. |

**Behaviors to suppress**

| Behavior | How Consumption ACV Suppresses It |
|---|---|
| Overselling / shelfware deals | A $500K deal at 4% consumption contributes only $20K to Consumption ACV — the rep's attainment number reflects the shelfware reality |
| Overselling at renewal | Expanding credit commitment on a low-consumption account compounds the shelfware problem — the higher ACV denominator pushes Consumed ACV Rate further down until adoption catches up |
| Ignoring post-sale onboarding | Under a pure bookings model, the rep's job ends at signature. Under Consumption ACV, onboarding quality is in their comp |
| Selective renewal bias (prioritising easy renewals over at-risk accounts) | Without a consumption-based metric, an Account Manager is incentivized to renew the accounts most likely to renew on their own — healthy customers who would re-sign with minimal intervention — and avoid investing time in accounts that need a costly save play. Under a bookings-only model this is rational; the AM who focuses on Healthy accounts will hit quota without touching a single Inactive one. Consumption ACV changes this calculus: the 70% Consumption ACV weight means a portfolio full of at-risk, shelfware, and inactive accounts directly suppresses the AM's total attainment — even if every renewing Healthy account resigns. The AM cannot achieve full attainment by serving only easy renewals. |
| Pushing long terms on weak accounts | A rep who locks in a long-term deal on a shelfware customer captures any term multiplier at signing — but poor Consumption ACV attainment across the portfolio will suppress their overall comp attainment, offsetting the gain |

**Known v1 gaming risk — credit-burning:** If Account Manager comp is weighted toward Consumption ACV attainment, an inverse failure mode emerges: pushing customers to run unnecessary scans, protect idle servers, or otherwise burn credits without delivering security value. Consumption ACV cannot distinguish active threat response from passive credit burn. This is flagged as a v1 risk; an engagement quality signal (alerts acted on, policies deployed, active users) is the v2 mitigation. In v1, managers should watch for accounts with high consumption rate but low security outcomes — a pattern detectable through manual QBR review.

---

### 3.6 Retention and Churn as Secondary Metrics

Consumption ACV is the North Star, but retention and churn metrics provide the lagging validation that Consumption ACV is tracking the right thing. Together they form a leading/lagging system: **Consumption ACV attainment is observable today, in real time; NRR and GRR are only known at renewal, months later.** If the design is correct, high Consumption ACV attainment today should predict strong NRR at the next renewal cycle. Tracking both allows the team to validate — and over time recalibrate — whether the health tier thresholds and attainment targets in this spec are set correctly.

In plain terms: a portfolio where most accounts are actually using the platform they bought is a portfolio that will renew. A portfolio full of shelfware will not. Consumption ACV attainment makes that renewal signal visible before the renewal invoice lands.

**Net Revenue Retention (NRR)**

```
NRR = (Beginning ARR + Expansion ARR - Contraction ARR - Churned ARR) / Beginning ARR
```

- Consumption ACV attainment rate is the leading indicator; NRR at renewal is the outcome it should predict
- Target: Consumption ACV-based NRR forecast within ±10% of actual NRR (see §7 Success Criteria)
- PANW disclosed NRR of ~119–120% in FY2024 ([*Palo Alto Networks Q2 FY2024 Earnings Call, Feb 20 2024*](https://investors.paloaltonetworks.com/events/event-details/q2-fy2024-palo-alto-networks-inc-earnings-call)). PANW has not separately disclosed NRR for FY2025; their public reporting now centres on Next-Generation Security (NGS) ARR growth. GRR and logo churn are not publicly disclosed.
- An org-wide Consumption ACV attainment of ≥85% is a portfolio health floor, not a direct NRR target. To see how attainment translates to GRR and NRR, break the portfolio into three tiers:

  | Tier | Consumed ACV | Hypothetical Mix | Renewal Outcome |
  |---|---|---|---|
  | At Risk | < 80% (At Risk + Shelfware + Inactive tiers — see §4) | 15% of portfolio ACV | Churn or contraction at renewal — **GRR headwind** |
  | Healthy | 80%–120% | 65% of portfolio ACV | Renews flat — **GRR anchor** |
  | Expansion | > 120% | 20% of portfolio ACV | Expands contract — **NRR accelerator** |

  **Illustrative math on a $10M ACV portfolio:**

  | | Calculation | Result |
  |---|---|---|
  | At Risk pool | $1.5M ACV; assume 50% churn → $750K lost | GRR drag: −7.5% |
  | Logo churn | At-risk accounts tend to be smaller, so 15% of ACV ≈ 20% of logos; 50% of those churn | **~10% logo churn rate** |
  | Healthy renewals | $6.5M renews flat | Neutral |
  | Expansion pool | $2.0M ACV; assume 30% expansion → +$600K | NRR lift: +6.0% |
  | **GRR** | ($10M − $750K) / $10M | **92.5%** |
  | **NRR** | ($10M − $750K + $600K) / $10M | **98.5%** |

  NRR crosses 100% when expansion dollars exceed at-risk losses — i.e., when the 20% expansion pool (>120%) grows fast enough to offset the 15% at-risk pool (<80%) churn. PANW's reported ~119% NRR reflects a much larger and faster-growing expansion engine than this baseline illustrates. **The 85% org-wide attainment target is not a claim that it directly produces 119% NRR** — it is a hypothesis that keeping the combined At Risk / Shelfware / Inactive pool small (≤15% of ACV) creates the conditions for strong GRR, and that converting the Expansion tier (≥30% upsell rate, per §7) drives NRR above 100%. Both require empirical validation once renewal cohort data accumulates (see v1 note below).

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

Per-account retention signals are shown in the Health Tier table in §4. At the org level, the key leading signals are:

- ✅ Org attainment ≥ 90% and trending up → strong NRR at next renewal cycle
- ✅ Shelfware + Inactive rate < 5% → GRR improvement within 2 quarters
- ✅ Expansion flag conversion ≥ 30% within 180 days → NRR above 100%
- ✅ ≥ 80% of ramping accounts reach Healthy within 90 days → low logo churn at first renewal
- ⚠️ Org attainment < 80% → NRR compression at next renewal cycle
- ⚠️ Shelfware + Inactive rate > 10% → GRR deterioration within 2 quarters
- ⚠️ Expansion conversion < 30% → NRR plateaus; growth depends entirely on new logos

> **v1 note:** The NRR outcome bands above are starting hypotheses derived from industry analogues, not PANW-specific renewal data. The primary value of this framework is establishing the *measurement habit* — tracking Consumption ACV attainment alongside NRR outcomes at every renewal cohort — so the bands can be empirically recalibrated after 12–18 months.

Tracking both Consumption ACV (real-time) and NRR/GRR (at renewal) allows the team to validate — and over time calibrate — whether the health tier thresholds and attainment targets in this spec are set correctly.

---

## 4. Health Tier Classification

While Consumption ACV is a continuous metric, health tiers provide operational clarity for CS and sales prioritization:

| Health Tier | Consumption Rate | Interpretation | Renewal Forecast Signal | Action |
|---|---|---|---|---|
| **Expansion** | > 120% | Consistently over commit — upsell signal | Renewal likely + expansion probable; NRR accelerator | Rep-led expansion motion |
| **Healthy** | 80–120% | On-track, full value realization | Renewal likely at flat ACV; GRR anchor | Maintain cadence |
| **At Risk** | 40–80% | Adoption lag — intervention needed | Renewal at risk; NRR compression likely | Account team escalation within 30 days |
| **Shelfware** | 5–40% | Low utilization — churn risk | High churn probability; GRR headwind | Executive sponsor outreach |
| **Inactive** | < 5% | Near-zero usage | High logo churn risk | Immediate save plan |
| **Ramping** | < 90 days old | Insufficient history | Excluded from NRR/GRR forecast | Tracked separately until window matures |

Health tiers are used for **dashboard visualization and CS prioritization only** — Consumption ACV itself uses the raw continuous consumption rate, not tiered multipliers.

> **v1 note:** The thresholds above (5% / 40% / 80% / 120%) are starting hypotheses, not empirically validated cutoffs. They are reasonable starting points based on industry analogues but have not been tested against PANW renewal cohort data. Plan a calibration review at 12–18 months once sufficient renewal outcomes are available. Thresholds should not be used as performance targets until validated.

---

## 5. Lifecycle Management with Consumption ACV

Consumption ACV is designed to reflect where a customer actually is in their adoption journey — not just what they signed. The table below defines how the metric behaves at each stage of the customer lifecycle, and when to act — not just what to eventually notice.

| Lifecycle Stage / Event | Consumption Signal | How Consumption ACV Responds | Detection & Action Window |
|---|---|---|---|
| **Onboarding (Ramp)** | Contract start within last 90 days | Excluded from portfolio rate; WoW credit growth monitored as the leading onboarding health signal | Flag if WoW growth is flat for 2 consecutive weeks (~day 14) → account team outreach; escalate if still flat at day 45; graduate at day 90 if ≥ 80% |
| **Spike & Drop** | High consumption in month 1, then collapses | Trailing 90-day window reflects current inactive state once the spike ages out | MoM decline > 40% in month 2 vs month 1 triggers flag (~day 45–60) → account team intervention within 14 days of flag |
| **Shelfware** | Near-zero consumption rate | Consumption ACV reflects near-zero value; account flagged for save plan | Flag after 30 consecutive days of < 5% consumption — don't wait for the 90-day trailing window to confirm what's visible at day 30 → executive sponsor outreach within 14 days |
| **Consistent Overages** | Over-consuming commit for 2+ consecutive months | Consumption Overage reported separately; expansion flag surfaced to rep | Month 1 overage noted as early signal; confirmed at month 2 (~day 60) → expansion motion initiated within 14 days |
| **Mid-Year Expansion** | Customer signs additional contract before original expires | Contracted ACV and credits summed across all simultaneously active contracts; expansion flag set | Event-driven — applied immediately on contract execution |
| **Multi-year Contracts** | 2- or 3-year deal term | Contracted ACV used as-is (already annualized); term stored for renewal forecasting and comp multiplier — see §11 for v1 ACV basis decision | Event-driven — applied at contract signing |

> **Data quality:** Usage records that cannot be matched to a customer lifecycle stage are excluded from Consumption ACV and surfaced in the data quality report rather than distorting the metric. This covers orphaned usage (logs referencing an account not in the customer master) and out-of-contract usage (logs falling before contract start or after contract end). Pipeline implementation details are in the Technical Spec.

---

## 6. Quota Setting and Compensation

PANW currently pays AEs on full TCV (Nikesh Arora, Q2 FY2024 earnings: *"our salespeople still get paid on TCV...they're still going to do a three-year deal or a five-year deal"*). TCV comp rewards signing without accountability for consumption — a rep can close a $500K shelfware account and never revisit it. Consumption ACV is designed to fix this. The examples below illustrate how the metric could be applied — specific thresholds and structures require VP of Sales and Finance alignment before adoption.

**Account Executives (AEs) — quality of sale**
- *Example:* Quota includes a Consumption ACV ramp component — the new logo must reach a minimum consumption rate (e.g. ≥ 70%) within 90 days of go-live to count as full credit toward attainment
- A portion of variable comp tied to consumption attainment incentivizes right-sized deals, proper onboarding, and early activation rather than overselling credits a customer won't use
- An activation bonus structure (e.g., sustained ≥80% consumption rate at month 6) directly rewards quality of sale

**Account Managers (AMs) — portfolio health**
- *Example:* Base quota = maintain current Consumption ACV attainment rate across the portfolio; stretch quota = grow total Consumption ACV by X% through expansion and improved utilization
- AMs measured on incremental Consumption ACV above baseline each quarter — not bookings — so an AM who resigns a shelfware account at flat ACV does not receive full attainment credit
- Surfacing over-consumption signals becomes financially meaningful: the AM has a direct incentive to flag expansion opportunities proactively

**Territory sizing**
- *Example:* Use total Consumption ACV per rep to identify overloaded vs. underloaded territories — a rep carrying 20 Inactive accounts needs different support than one carrying 20 Healthy accounts
- Reassign accounts based on Consumption ACV capacity, not just account count or ARR

**Behaviors the metric suppresses:** Overselling credits to inflate TCV, neglecting onboarding once a deal is signed, and renewing shelfware accounts without addressing underlying adoption gaps.

> **Snowflake precedent:** Snowflake ties AE comp to a 70% bookings / 30% consumption split, shifting to 30% bookings / 70% consumption for AMs managing mature portfolios. *(Snowflake, [Sales Compensation in a Consumption Pricing World](https://www.snowflake.com/en/blog/sales-compensation-in-a-consumption-pricing-world/))*

Detailed comp plan design — OTE splits, activation bonus amounts, role-level rules of engagement, and quota mechanics — is a separate workstream requiring VP of Sales, Finance, and HR alignment. This spec establishes the metric; comp design is the downstream application.

---

## 7. Success Criteria

Success for this initiative is measured across three dimensions: **business outcomes** (is the metric driving the right customer behaviors?), **metric accuracy** (does Consumption ACV actually predict renewal outcomes?), and **data reliability** (can the pipeline be trusted to feed comp and exec reporting?). The targets below are v1 starting hypotheses — they should be reviewed against actual renewal cohort data after 12–18 months.

<table>
<thead>
<tr><th>Category</th><th>KPI</th><th>Target</th><th>Window</th><th>Why it matters</th></tr>
</thead>
<tbody>
<tr>
  <td rowspan="4"><strong>Business Outcomes</strong></td>
  <td>Org-wide Consumption ACV Attainment</td>
  <td>≥ 85%</td>
  <td>Rolling 90 days</td>
  <td>The headline portfolio health number for the CFO — at 85%, the unconsumed ACV gap is small enough that GRR should remain stable at renewal</td>
</tr>
<tr>
  <td>Shelfware rate</td>
  <td>≤ 8% of active accounts</td>
  <td>Monthly</td>
  <td>Shelfware accounts are the leading indicator of logo churn; keeping this below 8% means the save plan backlog stays manageable</td>
</tr>
<tr>
  <td>Expansion flag conversion</td>
  <td>≥ 30% of flagged accounts → upsell within 180 days</td>
  <td>Semi-annual</td>
  <td>Validates that the expansion signal (sustained &gt;120% consumption) is being worked by reps, not just observed on a dashboard</td>
</tr>
<tr>
  <td>New account activation</td>
  <td>≥ 70% reach Healthy tier within 90 days of go-live</td>
  <td>Quarterly</td>
  <td>Tests whether the AE is right-sizing deals and coordinating onboarding — a low activation rate points to overselling or poor handoff</td>
</tr>
<tr>
  <td><strong>Metric Accuracy</strong></td>
  <td>Consumption ACV forecast accuracy vs. actual NRR</td>
  <td>Within ± 10%</td>
  <td>At annual renewal</td>
  <td>The core validity test: if health tiers predict renewal outcomes accurately, the metric is doing its job as a leading indicator</td>
</tr>
<tr>
  <td rowspan="2"><strong>Data Reliability</strong></td>
  <td>Pipeline data freshness</td>
  <td>Snapshot ≤ 24 hours old at time of dashboard load</td>
  <td>Every pipeline run</td>
  <td>Stale data erodes trust; reps and execs need to know the dashboard reflects yesterday's usage, not last week's</td>
</tr>
<tr>
  <td>Data quality test pass rate (ERROR tier)</td>
  <td>100% — zero ERROR failures</td>
  <td>Every pipeline run</td>
  <td>Any ERROR-level failure means a Consumption ACV figure fed to comp or exec reporting may be wrong — this is a zero-tolerance threshold</td>
</tr>
</tbody>
</table>

> **Note on shelfware threshold:** The data quality test in `dq_tests.py` alerts at >15% shelfware rate (a data integrity floor). The 8% target above is a performance ceiling — the org should be well below the alert level. If shelfware rate is between 8% and 15%, it requires a sales operations review; above 15%, it triggers the automated data quality alert and escalation to the data engineering team.

---

## 8. Executive Dashboard

**🔗 Prototype:** Run locally with `streamlit run dashboard/app.py` — no BigQuery credentials required, loads from the included synthetic data snapshot.

The Consumption ACV dashboard serves four distinct audiences, each with a different set of questions and level of granularity. *For implementation details — stack, data flow, caching strategy, and fallback behavior — see the Technical Spec §8.*

| Audience | Key Questions | Metrics |
|---|---|---|
| **VP of Sales / CFO** — Portfolio Overview | How much of our booked ACV is being consumed? What is our total churn exposure? Where is expansion pipeline coming from? | Total ACV vs. Consumption ACV; ACV at risk; expansion pipeline; attainment and health mix by region; rep attainment distribution |
| **Regional VPs / Sales Ops** — Region Breakdown | How does my region compare on attainment? What % of my portfolio is at churn risk? Do I have a shelfware problem or an expansion opportunity? | Consumption ACV and attainment rate per region ranked; ACV at risk; health tier mix by region; expansion pipeline by region |
| **Sales Managers** — Rep Leaderboard | Who are my top performers? Which rep has the most at-risk ACV and needs coaching now? Who has expansion opportunities they should be working? | Rep-level Consumption ACV and attainment rate ranked; ACV at risk per rep; health tier account counts per rep; expansion opportunity count and pipeline value |
| **CS Leads / AEs** — Account Detail | Which accounts are shelfware? Which are ready for an expansion conversation? What is the consumption trend heading into renewal? Which new accounts are stalling on ramp? | Per-account consumption rate, health tier, and Consumption ACV; ACV at risk; expansion flag; spike/drop anomaly flag; contract start and end dates |

---

## 9. Downstream System Integrations

Consumption ACV is most valuable when it flows into the systems reps and CS teams work in every day — not just a separate dashboard. *For field-level mappings, sync frequencies, and integration architecture — see the Technical Spec §9.*

| System | Audience | What Consumption ACV enables |
|---|---|---|
| **Salesforce CRM** | Sales reps, managers, RevOps | Health tier visible on every Account record; expansion flags auto-generate Opportunities; anomalous accounts flagged for review; attainment drives renewal forecast category (Commit / Upside / Risk). Attribution note: current account owner receives quota credit; original closing rep retains comp attribution — both records synced separately. |
| **Compensation Platform** (e.g., Xactly, CaptivateIQ) | Finance, sales reps, managers | AM quota attainment calculated from Consumption ACV, not renewal bookings; accelerator/decelerator tiers triggered by attainment rate; activation bonus paid at ≥80% consumption by day 90; expansion SPIFs tied to sustained over-consumption. |
| **Customer Success Platform** (e.g., Gainsight, Totango) | CS managers, CSMs | Health tier drives a CS health score; each tier triggers a defined playbook (expansion → AE handoff, at-risk → escalation within 30 days, shelfware → executive sponsor outreach, inactive → VP CS escalation); ramping accounts enter a 90-day onboarding playbook; data confidence surfaced alongside the score. |

---

## 10. Scope and Roadmap

Consumption ACV is designed to ship and build trust before expanding. v1 establishes the core metric and measurement habit; subsequent versions layer in calibration, quality signals, and commercial sophistication as the data matures.

### v1 — Launch

| What ships | Detail |
|---|---|
| **The metric** (§3) | Consumption ACV calculated as `ACV × consumption_rate(W)` at account, rep, region, segment, and org level. The headline portfolio measure — Consumed ACV Rate — gives the CFO a forward-looking renewal health indicator. Default window W = 90 days, aligned to PANW's quarterly comp cycle; 7-day and 30-day windows stored for monitoring. |
| **Health tiers** (§4) | Six tiers — Expansion, Healthy, At Risk, Shelfware, Inactive, Ramping — each with a defined consumption rate range, renewal forecast signal, and action. Thresholds (5% / 40% / 80% / 120%) are starting hypotheses to be calibrated in v2. |
| **Lifecycle management** (§5) | Six lifecycle stages tracked — from Onboarding through Consistent Overages and Multi-year Contracts — with detection windows and action triggers so teams act early rather than waiting for the 90-day trailing window to confirm what's visible sooner. |
| **Quota and comp signals** (§6) | Consumption ACV fed to the compensation platform to enable AE and AM attainment tracking. Quota design examples (ramp components, portfolio attainment) documented as illustrative starting points for VP of Sales and Finance alignment. |
| **Executive dashboard** (§8) | Four views covering portfolio overview (VP of Sales / CFO), regional breakdown (Sales Directors), rep leaderboard, and account detail (CS Leads / AEs). Built in Streamlit; runs locally against synthetic data with no BigQuery credentials required. |
| **Downstream integrations** (§9) | Consumption ACV signals flow to three systems: Salesforce CRM (health tier on every account record, expansion Opportunities auto-generated), compensation platform (attainment and commission calculations), and Customer Success platform (automated tier-triggered playbooks). |
| **Data quality** | 11 automated assertions covering orphaned usage, out-of-contract usage, negative consumption, stale snapshots, and more. Zero ERROR-tier failures required before any pipeline output feeds comp or exec reporting. |

### v2 — Calibrate and Deepen

v1 ships with reasonable hypotheses. v2 is about replacing them with evidence — and making the signal sharper once that evidence exists.

**Validate the hypotheses.** After 12–18 months of renewal cohorts, the team will have the data needed to answer a critical question: do our health tier thresholds actually predict churn? **Health tier threshold calibration** tests whether the 5% / 40% / 80% / 120% cutoffs hold up against real outcomes, and **NRR prediction band validation** does the same for the attainment → retention relationship. Both are currently starting hypotheses derived from industry analogues; v2 replaces them with PANW-specific evidence.

**Sharpen the signal.** In parallel, the metric itself gets more precise. An **engagement quality signal** distinguishes active platform use from passive credit burn — addressing the v1 risk that a rep could coach a customer to run unnecessary scans and inflate their consumption rate without delivering real security value. **Real-time consumption updates** (vs. daily batch) enable intra-quarter intervention, catching a spike-and-drop pattern while there's still time to act. And **segment-specific windows and targets** — tuned to Enterprise, Mid-Market, and SMB ramp curves — replace the single org-wide 90-day window with one calibrated to how each segment actually consumes.

### Beyond v2 — Long-Term Vision

Once Consumption ACV is trusted internally and calibrated against real renewal outcomes, the opportunity expands in three directions.

**Wider accountability.** The consumption accountability model extends beyond AEs and AMs. **Channel partner and CSM comp integration** brings the full customer-facing team into the same framework — closing the gap where partners and CSMs influence adoption but aren't measured on it. At the platform level, **cross-product consumption correlation** connects Prisma Cloud consumption with Cortex and other PANW product lines: a customer consuming deeply across multiple products is a fundamentally different retention and expansion profile than one relying on a single module.

**Strategic recognition.** A metric that earns CFO trust and audit readiness has the potential to become a board-level disclosure — **Consumption ACV as an externally reported metric**, alongside NRR, in the way Snowflake reports trailing consumed revenue. This shifts the narrative from "we think customers are healthy" to "here is the data" *(CFO decision — see §11 Q6)*.

**AI transforms measurement into action.** The long-term vision is a metric that doesn't just describe what happened, but tells teams what to do next. **AI-powered adoption recommendations** surface the specific features an account hasn't deployed and benchmark them against similar accounts that did. **Deal coaching at point of sale** flags oversell risk at deal structuring — before shelfware is created, not after. **Contract right-sizing at renewal** uses consumption trajectory to recommend the optimal credit commit, shifting the renewal conversation from backward-looking to forward-looking. And **natural language querying** makes all of this accessible to any rep or executive without navigating a dashboard — lowering the barrier to acting on consumption signals from hours to seconds.

---

## 11. Open Questions for Executive Alignment

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
10. **Consumption ACV cap for quota attainment** *(VP of Sales + Finance)* — Should Consumption ACV be capped at ACV when calculating quota attainment, so that over-consuming accounts cannot push a rep above 100% attainment on this metric alone? Capping preserves a clean "% of commit consumed" narrative; leaving it uncapped rewards over-consumption directly in the attainment number. Decision required before comp platform integration.

---

## 12. Sources

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
