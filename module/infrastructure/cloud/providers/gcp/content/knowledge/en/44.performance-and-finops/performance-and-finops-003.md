# Committed Use Discounts and Sustained Use Discounts

In the `CLOUD_PROVIDERS_GCP` module, learners explore Google Cloud from project governance, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases; thereby learning how to choose services, protect resources, automate releases, and monitor reliability and costs. The **Performance and FinOps** chapter focuses on data-driven operational decisions. This lesson explains two discount mechanisms on Google Cloud: **Committed Use Discounts (CUDs)** and **Sustained Use Discounts (SUDs)**.

The goal is not to chase the highest percentage discount on a price sheet, but to minimize **actual total cost** based on usage, architectural flexibility, and commitment risk. You will distinguish each discount type, understand how they apply and their order of precedence, work through calculation examples, analyze coverage/utilization, and build a controlled CUD purchasing process.

> **Data scope:** Policies, eligible machine series, discount rates, and CUD accounting models can change by SKU, billing account, contract, and over time. Monetary rates in the illustrative problems are **hypothetical for learning**, not Google Cloud quotes. Before purchasing, verify against the Cloud Billing Console, CUD recommendations, and official documentation at the time of decision.

## 1. Two Discount Mechanisms Solving Different Needs

A **Sustained Use Discount (SUD)** is a discount based on *running long enough within a month* for **eligible Compute Engine resources**. SUDs do not require signing a contract or purchasing upfront; Compute Engine calculates and applies them automatically to eligible usage on a Cloud Billing account. Typically, a resource must be used for more than 25% of the billing month before incremental discounts begin applying.

A **Committed Use Discount (CUD)** is a discount in exchange for committing to **purchase a minimum amount of resources or spend**, typically for **1 year or 3 years**. You must pay the commitment fee over the contract term whether you use all of it or not. CUDs fit workloads with a **stable and predictable baseline**.

| Criterion | SUD | CUD |
| --- | --- | --- |
| Must purchase a commitment? | No | Yes, typically 1 year or 3 years depending on the product |
| How it activates | Automatic on eligible usage | Purchase commitment per product/resource |
| Evaluation period | Based on portion of usage within the billing month | Based on commitment term and corresponding entitlement window |
| Constraints | Only eligible resources, machine series, and billing accounts | Scope depends on CUD type, SKU, region, and account |
| When workload drops sharply | No fixed SUD fee incurred | Still obligated to pay for the purchased commitment |
| Savings level | Scales with usage duration percentage, capped by series | Rates vary by product, SKU, term, and commitment type |
| Best fit | Long-running usage when you do not want to lock into a contract | Measured baseline with a long-term plan |
| Stackable on the same usage hour? | No | No: the same unit of usage cannot simultaneously receive both SUD and CUD |

Another term easily confused with CUDs is **reservation**: reserving Compute Engine capacity in a specific region/zone. **CUDs do not automatically reserve physical resource capacity**; if a workload needs capacity assurance, you must design a separate reservation and check how it links with commitments. SUDs do not reserve capacity either.

## 2. Distinguishing CUD Types

Google Cloud has two main CUD categories: **resource-based** and **spend-based**. Their discount scope, eligible resources, and billing mechanics differ.

### 2.1. Resource-Based CUDs

With a Compute Engine **resource-based commitment**, you commit to a specific amount of resources in **a region and an eligible machine configuration/series**. Resources can include vCPUs, memory, certain GPUs, Local SSDs, sole-tenant nodes, or licenses depending on product terms.

Example: a backend workload uses a steady amount of vCPU/RAM on N2 VMs in one region. You forecast that at least a certain amount of vCPU and RAM will always be running. Instead of paying 100% on-demand rates, you can purchase a resource-based commitment sized to the **hourly baseline**.

Key characteristics to note:

- Each commitment has a **purchasing project and region**; eligible usage must match the region, machine type/series, and eligibility rules.
- **CUD sharing** may allow resource-based commitments from one project to cover usage in other projects under the **same Cloud Billing account**, if settings and terms permit. Never assume it is always on or always off; inspect the current setting.
- VM shapes may change, but only **matching and eligible resources** are covered. Never assume any new VM automatically inherits an old VM's CUD.
- Certain commitments involving GPUs/Local SSDs have specific reservation requirements or purchasing mechanics. Check hardware-specific documentation.
- Resource-based CUDs fit a **stable capacity baseline**, but can become stranded waste if you migrate to another machine family/region that the commitment no longer covers.

### 2.2. Spend-Based CUDs

With a **spend-based commitment**, you commit to an amount of **eligible spend** over the contract term. The scope can be a single service or a group of services, depending on the CUD product.

Example: **Compute flexible CUD** can cover eligible SKUs across **Compute Engine, Google Kubernetes Engine, and Cloud Run** under a Cloud Billing account. It is more flexible than resource-based commitments across machine variants, projects, and regions, though **not every SKU in those three services is eligible**.

- There are **service-specific spend-based CUDs** applying to a particular service, such as eligible CUD programs for Cloud SQL or other products. Each service defines its own eligible spend/regions.
- Compute flexible CUDs can cover **eligible usage** spread across multiple projects or services on the same billing account; CUDs cannot be shared across different billing accounts.
- Precedence rules may apply service-specific commitments before compute flexible commitments when usage falls under multiple scopes.
- In newer **spend-based CUD** programs, commitments are typically expressed in **discounted spend**; legacy programs may use **on-demand-equivalent spend** when purchasing. Do not mix up units during purchase.
- For newer products such as Flexible Savings Plans, the entitlement window may be **monthly**, rather than identical to traditional hourly commitments. Always check the terms of the specific commitment.

### 2.3. Comparing Options

| Workload | Evaluation Priority | Rationale |
| --- | --- | --- |
| VMs in the same family and region, running steady 24/7 | Resource-based CUD | Matches baseline CPU/RAM tightly by region/series. |
| VMs changing machine family or region with steady total eligible spend | Compute flexible CUD | Spend level is more stable than resource shape. |
| Team with eligible Compute Engine, GKE, and Cloud Run on one billing account | Compute flexible CUD | Can share eligible spend scope across multiple services. |
| Continuous Cloud SQL workload | Cloud SQL–specific CUD if eligible | Do not mistakenly rely on Compute Engine resource-based CUDs to cover a Cloud SQL bill. |
| Development VMs running business hours only, frequently resized | On-demand + scheduling/rightsizing, SUD if eligible | Long-term commitments can increase total cost. |
| Pilot workload with uncertain scale | Monitor before buying | Short historical data easily leads to bad forecasts. |

**Note:** Cloud Run discount pricing depends on billing mode and workload type. Do not assume "Cloud Run always gets X% off" or "all Cloud Run spend is eligible"; check the eligible SKU list and CUD rates for request-based, instance-based, jobs, functions, or worker pools individually.

## 3. How SUDs Work

### 3.1. The 25%, 50%, 75%, and 100% Monthly Tiers

SUDs apply to eligible resources used for more than **25% of the month**, increasing progressively with usage. Google Cloud uses 25%, 50%, 75%, and 100% incremental tiers to calculate tiered discounts. As a result, the **effective discount rate** across total monthly usage is lower than the marginal discount rate in the final tier.

For resource groups with a **30% maximum SUD**, the illustrative figures in Compute Engine documentation are:

| Monthly Equivalent Usage | Effective SUD on Total Eligible Usage |
| --- | --- |
| 25% or less | 0% |
| 50% | 10% |
| 75% | 20% |
| 100% | 30% |

Groups with a **20%** maximum SUD follow their own discount curve. Do not apply the 30% table to all VMs.

### 3.2. Which Resources/Machine Series Receive SUDs?

According to Compute Engine documentation, common machine series with SUDs include:

| Group | Maximum SUD for Full-Month Eligible Usage |
| --- | --- |
| N1 predefined/custom; M1/M2; certain N1 GPUs and sole-tenant resources | Up to 30% |
| N2/N2D predefined/custom; C2; corresponding sole-tenant resources | Up to 20% |
| E2, C3/C4, N4, and many newer series | **No SUD**; their on-demand pricing is structured differently |

The maximum rate applies only to **eligible program resources**; a VM's invoice also includes disks, images/licenses, networking, egress, and many SKUs that do not necessarily receive SUDs. SUDs do not apply to all GPUs, all machine types, or all Google Cloud products.

Limits to remember:

- SUD documentation applies to **Self-serve/Online Cloud Billing accounts**; do not assume every enterprise contract follows the same mechanism.
- SUDs apply to eligible VMs from **Compute Engine and GKE**; they do not apply to VMs created by **App Engine standard/flexible** or Dataflow per program exclusions.
- **SUDs do not apply to usage already covered by a CUD**.
- Does not apply to usage under corresponding Always Free quotas.
- SUDs usually appear as **monthly credits** on invoices/reports; they are not cash balances that carry over to another month.

### 3.3. Calculating an SUD Example

Suppose an **eligible N1 resource** has a hypothetical on-demand cost of **0.10 USD/hour** for just the SUD-eligible component, and the month has **720 hours**. The example intentionally excludes licenses, disks, networking, taxes, other discounts, and ineligible resources.

**Scenario A — 50% monthly usage:** 360 hours.

~~~text
Eligible on-demand cost = 360 × 0.10 = 36.00 USD
Effective SUD at 50% of month = 10%
SUD credit = 36.00 × 10% = 3.60 USD
Net eligible compute cost = 36.00 − 3.60 = 32.40 USD
~~~

**Scenario B — full-month usage:** 720 hours.

~~~text
Eligible on-demand cost = 720 × 0.10 = 72.00 USD
Effective SUD for full month = 30%
SUD credit = 72.00 × 30% = 21.60 USD
Net eligible compute cost = 72.00 − 21.60 = 50.40 USD
~~~

SUD **does not mean "reaching hour 181 gives 30% off the entire bill"**. Discounts ramp up across usage tiers, and the effective rate only hits the cap when running full-month eligible usage.

If you replace N1 with an E2 VM, this SUD calculation does not apply. If 360 hours are already covered by a CUD, no additional SUD applies to that same usage.

## 4. Scope and Order of Application for CUDs and SUDs

A Cloud Billing account can simultaneously have resource-based CUDs, compute flexible CUDs, and SUD-eligible usage. **You do not multiply the three discount percentages together**.

Generally, for eligible Compute Engine usage:

1. Google Cloud applies **resource-based CUDs** to usage matching their scope/configuration.
2. Remaining eligible usage may be covered by **compute flexible CUDs**, following billing account and product commitment precedence rules.
3. Usage **not covered by commitments** is billed on-demand; if the resource itself and billing account qualify for SUDs, that portion may receive SUDs per program rules.

~~~mermaid
flowchart TD
  USAGE[Hourly eligible Compute Engine usage] --> R{Matched resource-based CUD?}
  R -->|Yes| RC[Apply resource-based CUD]
  R -->|No, remaining usage| F{Eligible flexible CUD capacity?}
  F -->|Yes| FC[Apply compute flexible CUD]
  F -->|No| OD[Charge on-demand]
  OD --> S{SUD eligible and monthly threshold met?}
  S -->|Yes| SC[Apply SUD on uncovered eligible usage]
  S -->|No| ND[No SUD]
~~~

This is a conceptual learning model; SKU/commitment attribution can be more complex when multiple spend-based commitments, service-specific commitments, credit programs, and specific billing account rules exist. Use CUD Analysis and billing export to verify **actual results**.

**No double-stacking:** claiming "resource-based CUD cuts 35% and SUD cuts another 30%" on the same usage is wrong. You only see both savings types on the same billing account because they apply to **different slices of usage**.

### 4.1. CUD Sharing and Scope

Traditional resource-based commitments are tied to the purchasing region and project; sharing across other projects depends on the **CUD sharing setting** and billing account type. Starting mid-2026, some newer accounts have different default CUD sharing settings than older accounts. Therefore, **check the actual setting**, do not infer from project age.

Spend-based commitments generally apply at the **Cloud Billing account scope**, but still have region conditions and specific eligible SKUs. A commitment for region A does not automatically transfer to region B if the product has regional constraints. Moving a project to **another billing account** can break applicability of existing commitments.

### 4.2. Is a Commitment a Reservation?

No. A CUD is a **pricing/cost** mechanism, not a default guarantee of regional/zonal capacity. When you need guaranteed availability of GPUs or scarce machines during scaling, review **Compute Engine Reservations** and rules for attaching commitments to reservations; do not treat a CUD purchase as proof that Google Cloud has reserved capacity.

## 5. Distinguishing CUD Coverage, Utilization, and Savings

Three FinOps metrics have distinct meanings:

| Metric | Meaning | What If It Is Low? |
| --- | --- | --- |
| **CUD coverage** | Share of **eligible usage/spend** covered by commitments in the period. | Much eligible usage remains on-demand; there may be an opportunity to buy more, if stable. |
| **CUD utilization** | Share of **purchased commitment** actually consumed in the period. | Paid capacity/spend went unused, creating wasted cost. |
| **CUD savings** | Actual savings per program and reporting definition. | Can be low due to usage drops, underutilization, scope mismatch, price changes, or wrong CUD type. |

Comparison ratios must use **the same unit type**. Do not add "10 vCPU + 20 GiB memory" to compute one combined utilization rate. Cloud Billing CUD Analysis also does not show aggregated utilization across multiple CUD types with different units.

Simple model:

~~~text
Coverage ≈ Eligible usage covered by CUD / Total eligible usage
Utilization ≈ Applied commitment / Purchased commitment
~~~

With spend-based CUDs under the newer consumption model, usage already carries discounted rates; coverage reports may normalize by **on-demand-equivalent eligible cost** for comparison. Do not divide net billed spend across all SKUs directly by committed spend to claim coverage, because the numerator and denominator may be in different price bases.

### 5.1. Why High Coverage Does Not Guarantee Good Savings

A team buys 100 units of committed capacity but only uses 60 units consistently. They may show **100% coverage** on those 60 units while utilization is only **60%**; they still pay for the unused capacity. Conversely, a team with 100% utilization and 45% coverage fully consumes its commitment, leaving 55% of eligible usage on-demand. If that remainder is mostly spikes, buying more CUDs may not pay off.

### 5.2. Risk When Migrating Workloads

When deciding to move N2 VMs to another series, another region, Cloud Run, or serverless architectures, ask:

- Will the old commitment still cover the new eligible SKUs?
- How much time remains until expiration?
- Can CUD sharing let other projects absorb the committed capacity?
- If workloads migrate immediately, how much is the unused commitment fee?
- Are the projected savings of the new architecture large enough to offset remaining commitment costs?

Keeping an inefficient VM solely to "avoid wasting a CUD" can also be a sunk-cost fallacy. Compare **total cost going forward**, including unavoidable commitment fees and reducible variable costs.

## 6. CUD Calculation Examples and Break-Even Point

### 6.1. Resource-Based CUD (Hypothetical)

Suppose a standard capacity resource costs **1 USD/hour** on-demand at 10 units; a matching commitment costs **0.65 USD/hour** and covers up to 10 units/hour. Pricing in this example is **hypothetical**, not official discounts.

| Scenario | Actual Eligible Usage | Hypothetical On-Demand | Total CUD Cost Before Overage | Interpretation |
| --- | --- | --- | --- | --- |
| Running 10/10 units | 1.00 USD/h | 1.00 USD/h | 0.65 USD/h | Saves 0.35 USD/h if fully matched. |
| Running 9/10 units | 0.90 USD/h | 0.90 USD/h | 0.65 USD/h | Part of commitment unused, still saves vs. on-demand. |
| Running 6/10 units | 0.60 USD/h | 0.60 USD/h | 0.65 USD/h | Loses 0.05 USD/h vs. on-demand before SUD. |
| Running 16/10 units | 1.60 USD/h | 1.60 USD/h | 0.65 + 0.60 = 1.25 USD/h | 10 units covered; 6 units billed outside commitment. |

From the simple math:

~~~text
On-demand cost of 10 units = 1.00 USD/h
Commitment fee = 0.65 USD/h
Break-even usage fraction ≈ 0.65 / 1.00 = 65%
~~~

**65% is only the break-even point between CUD and pure on-demand** under these assumptions. When eligible on-demand usage can earn SUDs or other contract/credit discounts, the true break-even point may be higher. And if purchasing a spend-based CUD denominated in discounted spend, **do not mechanically apply the 10-unit resource-based CUD formula**.

### 6.2. Do Not Ignore SUDs in the Baseline Comparison

Suppose an SUD-eligible N1 resource workload runs all month. At 1.00 USD/h on-demand, a **maximum 30% SUD** on eligible usage can bring effective cost down to about 0.70 USD/h. A hypothetical 0.65 USD/h commitment at 100% utilization saves only about 0.05 USD/h more than the SUD alternative.

Thus, saying "buying a CUD saves 35%" is **insufficient** for a financial decision: compare against the **best alternative available to the organization**, including SUDs, existing commitments, rightsizing, scheduling, and contract pricing.

### 6.3. Separating Fixed and Variable Costs

To compare across the commitment lifecycle:

~~~text
Total cost with CUD
  = Commitment fees over term
  + Uncovered eligible usage at applicable rates
  + Non-eligible usage (disks, network, licences, ...)
  + Other platform and operations costs
  - Applicable separate savings

Total cost without new CUD
  = Eligible usage at applicable existing rates
  + Non-eligible usage
  + Other platform and operations costs
  - Existing applicable discounts (such as SUD)
~~~

Identical shared fees cancel out in comparisons, but keep items that change due to architecture or contract terms. Where **legacy CUD credit accounting** or **newer consumption model discounts** apply, ensure each fee/credit line is counted exactly once.

## 7. CUD Accounting in Cloud Billing: Legacy vs. Newer Model

A common mistake is looking at reduced total credits and concluding CUDs yielded savings equal to credits, whereas many spend-based CUDs now use **consumption model discounted rates**.

### 7.1. Legacy Credits

Some legacy CUD models record usage at on-demand rates and apply discounts via **credits**. Resource-based CUDs also emit fee/credit lines under Cloud Billing accounting. When analyzing, match usage, credits, and **commitment fees** in the right scope; summing credits while omitting commitment fees inflates savings.

### 7.2. Newer Spend-Based CUDs

Google Cloud introduced **Spend-based CUD discounts** where usage is priced at **discounted rates** under the matching **consumption model**, rather than always emitting a separate credit line to offset list price.

FinOps implications:

- `cost` in billing export may already reflect the discounted price for SKUs using the consumption model.
- You cannot conclude "no CUD credit means no CUD benefit."
- You must cross-check **consumption model**, commitment fees, eligible SKUs, and CUD Analysis.
- Old report templates relying on `credits.type` may not reflect full spend-based savings under the new model.
- Accounts with legacy commitments undergoing migration should check **Cloud Billing Overview** for their specific account's schedule; do not assume all accounts switch on the same date.

### 7.3. CUDs and Billing Attribution

Commitments purchased on a Cloud Billing account can be **attributed** back to consuming projects according to attribution settings. Consequently, opening Billing Reports for a single project may hide account-level fees or credits. Evaluating commitment effectiveness must start at the **billing-account scope**, then allocate internal costs according to FinOps policy.

With multiple teams, define **showback/chargeback** rules for unused commitment fees in advance. Otherwise, one team may book savings while another absorbs unused commitment charges.

## 8. Analyzing Data Before Purchasing

A sound CUD decision requires **hourly** data or the appropriate entitlement-window granularity, not just monthly averages. Weekday vs. weekend swings, autoscaling, and deployment schedules can push the baseline well below the average.

### 8.1. Questions to Answer

1. Over the last 30/60/90 days, what is the **eligible usage** per SKU, region, machine family, or service?
2. How much is already covered by **existing CUDs**? How much remains on-demand, under SUDs, or under other contract discounts?
3. What is the conservative percentile baseline (e.g., P10/P20 of eligible hourly usage)?
4. Are workloads planning to change regions, switch machine families, scale down, change clouds, or move to Cloud Run/GKE?
5. Will rightsizing, non-production auto-stop, scheduling, and caching lower the baseline?
6. Does a new commitment align with budget, cash flow, and approval policy?
7. Is usage outside commitments steady enough to justify buying more, or is it unpredictable spikes?

### 8.2. Using Billing Reports and CUD Analysis

In the Google Cloud Console (menu names may vary with UI updates):

1. Open **Billing** and select the right **Cloud Billing account**.
2. Open **Reports** or **Cost table** to inspect total cost, service/SKU, project, region, and savings filters.
3. Open **Committed use discounts (CUDs)** or **CUD Analysis**.
4. Select commitment type, time range, and scope.
5. Inspect **Coverage** (how much eligible usage/spend is covered), **Utilization** (how much commitment is used), **Savings**, and expiration dates.
6. Compare with **CUD Recommender**, then verify eligibility terms and upcoming workload changes.

Reports have update latency; the most recent day may be incomplete. If data has gaps or a new commitment started mid-period, do not use non-representative numbers to make large purchases.

### 8.3. Analyzing Cloud Billing Export with BigQuery

With Cloud Billing **standard/detailed usage cost export** enabled in BigQuery, SQL can group costs by service and SKU. Example query reading **cost after pricing but before credits** alongside total credits; replace the table name with your billing account's table:

~~~sql
SELECT
  invoice.month AS invoice_month,
  service.description AS service_name,
  sku.description AS sku_name,
  ROUND(SUM(cost), 2) AS cost_before_credits,
  ROUND(SUM(
    IFNULL(
      (SELECT SUM(c.amount) FROM UNNEST(credits) AS c),
      0)
  ), 2) AS credits_amount,
  ROUND(SUM(
    cost + IFNULL(
      (SELECT SUM(c.amount) FROM UNNEST(credits) AS c),
      0)
  ), 2) AS reported_cost_after_credits
FROM `BILLING_PROJECT.billing_dataset.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE usage_start_time >= TIMESTAMP("2026-09-01")
GROUP BY invoice_month, service_name, sku_name
ORDER BY invoice_month DESC, reported_cost_after_credits DESC;
~~~

**Query limitations:**

- It only groups `cost` and `credits` for line items present in the export; **it is not a complete CUD savings calculation**. Under the newer model, consumption-model discounts may already be baked into `cost`.
- One SKU can have multiple consumption models, so accurately measuring newer CUDs requires analyzing **consumption model** and fee lines per the current **detailed export** schema.
- The query may include taxes, adjustments, or fees depending on SKU and invoice month filters; results are not directly equivalent to baseline on-demand pricing.
- It cannot generate historical data before the date billing export was enabled. When history is missing, use Billing Reports/CUD Analysis or other authorized sources.
- Only authorized personnel should access BigQuery exports and cost reports; do not expose project IDs, contract discounts, or sensitive invoice data.

### 8.4. Reading Hourly Data

For resource-based CUDs, aggregate eligible vCPU/memory usage by **hour + region + machine series + billing-account scope** and examine the distribution. For Compute flexible CUDs, aggregate **eligible spend by consumption model/rules** within the exact billing account scope. Do not confuse total VM spend with eligible spend; licenses, persistent disks, or egress may not be covered by the package under review.

A useful report format:

| Time Window | Suitable Baseline Usage | Peak Usage | Existing CUD Coverage | Proposal |
| --- | --- | --- | --- | --- |
| Weekday off-peak hours | 8 units | 12 units | 6 units | Consider modest increase if baseline is durable |
| Weekday peak hours | 10 units | 18 units | 6 units | Variable overage: inspect P10/median |
| Weekends | 5 units | 9 units | 6 units | Do not raise CUD based solely on peak hours |
| Post-planned rightsizing | 4–7 units | 12 units | 6 units | Defer new purchases until metrics stabilize |

"Units" are illustrative only. In practice, analyze resource-based commitments by vCPU/RAM separately, and spend-based commitments by currency and eligible SKUs.

## 9. CUD Recommender and Purchase Approval

**CUD Recommender** in Google Cloud uses historical usage, existing commitments, and target coverage levels to suggest commitments for eligible products. A recommendation is not a buy order: it cannot know about planned shutdowns, contract changes, or migrations unless you factor those constraints into your review.

Recommended workflow:

1. Collect at least 30–90 representative days of usage; include seasonal data or a longer business cycle if available.
2. Exclude from the baseline any workloads scheduled for shutdown, rightsizing, or migration to ineligible resource types.
3. Compare **1-year** vs. **3-year**: three years typically offers steeper discounts but locks in transition risk longer.
4. Compare **resource-based** vs. **spend-based/flexible** based on resource stability vs. spend stability.
5. Use CUD Recommender and Pricing Calculator / commitment cost models to verify break-even against SUD-eligible alternatives.
6. Verify regions, SKU eligibility, account permissions, CUD sharing, and existing fees; obtain sign-off from FinOps + workload owner + spending authority.
7. Only authorized individuals execute the purchase in the Billing Console. **Never auto-purchase via a pipeline** without review and approval.

Commitments are binding: generally **they cannot be canceled, reduced, or shortened after purchase**. Details such as scope changes, migrations, or billing account transfers require checking specific terms and potentially contacting Cloud Billing Support. A single purchase can create multi-year financial obligations, so never treat it as an experimental config change that can be rolled back.

## 10. End-to-End FinOps Scenario

A company runs three workload groups:

- **Steady N2 backend VMs** in one region: 24/7 workload, predictable CPU/RAM, minimal architectural change expected over 12 months.
- **GKE batch processing**: scheduled jobs with fluctuating resource usage; unstable nighttime/weekend consumption.
- **Cloud Run API**: highly variable request counts, though aggregate eligible spend across services may be relatively stable.

Approach:

1. **N2 Backend:** check current maximum SUD for N2 (different from N1), evaluate a resource-based CUD for baseline vCPU/RAM in the region. Commit only to guaranteed steady usage, never peak capacity.
2. **GKE:** separate Compute Engine VM nodes eligible for resource-based CUD/SUD from services/SKUs covered under Compute flexible CUD; avoid double-counting.
3. **Cloud Run:** verify billing mode and eligible SKUs before including in Compute flexible CUD. If spend fluctuates hourly, verify whether aggregate eligible spend is durable enough for a commitment to pay off.
4. **Account:** verify all projects sit under the same Cloud Billing account, inspect CUD sharing settings, and check existing commitments.
5. **Optimize first:** eliminate idle VMs, rightsize, move fault-tolerant batch jobs to Spot VMs where reliability permits, and only then decide commitment amounts.
6. **Post-purchase monitoring:** review coverage, utilization, savings, and unused commitment fees weekly; adjust forecasts monthly and plan renewals before expiration.

A sound purchase plan might combine a resource-based CUD for the stable N2 portion and a **smaller** compute flexible CUD for remaining eligible spend—or skip compute flexible CUD altogether if volatility is too high. A high discount percentage cannot make up for unused commitment fees.

## 11. SUDs, CUDs, and Other Optimization Levers

CUDs and SUDs are **pricing optimizations**, not substitutes for **engineering efficiency**.

| Lever | Value | Risks / Notes |
| --- | --- | --- |
| VM/container rightsizing | Cuts actual CPU/RAM usage | Must load-test and measure SLOs after resizing |
| Off-hours non-production scheduling | Cuts running hours | May reduce SUD percentage, yet total bill drops sharply |
| Bounded autoscaling | Matches capacity to load | Do not commit to short-term spikes |
| Spot VMs for fault-tolerant batch | Low cost for interruptible workloads | Can be preempted; Compute flexible CUDs do not apply to Spot VMs |
| SUD for eligible VMs | Automatic, no lock-in | Limited to specific machine series/billing accounts |
| Resource-based CUD | Matches fixed hardware baseline | Region/series lock-in and fixed fees |
| Compute flexible CUD | Covers multi-service eligible spend | Depends on SKU eligibility and spend commitment |
| Cloud Run/GKE architectural optimization | Lower ops overhead, higher efficiency | Re-calculate pricing/costs and migration risk |

**The paradox example:** A test VM running 24/7 receives a 30% SUD; if shut down 16 hours/day and on weekends, the SUD percentage may drop or disappear. However, total usage hours fall sharply, so **the monthly bill is usually still lower**. Never leave a machine running just to "keep the SUD."

## 12. Monitoring Commitments After Purchase

Do not stop at the purchase transaction. Track on a fixed cadence:

### Weekly

- **Utilization** of each commitment and **coverage** of eligible spend.
- Uncovered spend during peak/off-peak hours; investigate why usage falls under or outside commitments.
- Workload shifts across machine types, regions, projects, services, or billing accounts.
- Share of costs that remain **ineligible** despite CUDs, such as licenses, storage, or networking.
- Spikes/SLO changes increasing capacity demand.

### Monthly

- Reconcile **CUD Analysis**, **Billing Reports**, cost tables, and full invoice-month data.
- Evaluate savings **net of commitment fees**, compared against on-demand + SUD + other optimizations.
- Enforce Finance and team accountability: who gets charged for unused commitment fees?
- Update forecasts, migration plans, and expiration dates.
- Propose additional purchases only if the baseline is durable; never react to a single traffic spike by buying more commitments.

### Before Commitment Expiration

- Recompute the baseline from current usage rather than copying old amounts.
- Check planned migrations, downsizing, region moves, and newer products.
- Compare current pricing terms against the original purchase terms.
- Decide to renew, narrow scope, or return to on-demand under allowed options.

## 13. Common Pitfalls

| Pitfall | Why It Is Wrong | Remedy |
| --- | --- | --- |
| "Every VM running all month gets 30% SUD" | Only eligible machine series/resources qualify; some cap at 20%, and many newer series have no SUD. | Check series/SKU and billing account eligibility. |
| "SUD requires opt-in registration" | SUD applies automatically to eligible usage. | Never buy a commitment just to get SUD. |
| "CUD and SUD stack on the same runtime hour" | Discount types are mutually exclusive on the same unit of usage. | Analyze covered and uncovered usage separately. |
| "Buy CUD equal to monthly average hours" | Commitments must match the baseline over time and scope. | Inspect hourly distributions, percentiles, and trough periods. |
| "CUD automatically reserves capacity" | Pricing discount contracts differ from capacity reservations. | Design separate reservations when capacity assurance is needed. |
| "All Cloud Run/GKE/VM spend gets compute flexible CUD" | Only selected eligible SKUs/billing modes qualify. | Check SKU Groups and service-specific pricing. |
| "No credit line means no CUD applied" | Newer spend-based CUDs use discounted consumption models. | Inspect consumption models and CUD Analysis. |
| "High coverage means we bought well" | Utilization may be low with idle fee waste. | Track coverage, utilization, and savings net of fees together. |
| "CUD Recommender output is enough to buy" | Historical models do not know future plans. | Add forecasts and FinOps/owner approvals. |
| "We can cancel commitments if workload drops" | Commitments create binding fee obligations for the term. | Review terms and require stop/go approval before purchase. |
| "Checking only one project's cost" | Commitment fees/savings may be attributed across the billing account. | Evaluate at the full billing-account level, then attribute to projects. |
| "Buy more CUDs to fix a sudden bill spike" | Spikes may not persist. | Investigate traffic, rightsizing, quotas, and baseline first. |

## 14. Hands-On Exercise: Reading and Analyzing CUDs/SUDs

Perform **read-only** without purchasing any commitment:

1. Select a Cloud Billing account where you have report-viewing permissions. If unavailable, use the lesson's hypothetical figures for calculation.
2. Open **Billing → Reports**, filter by Compute Engine; record eligible usage, SUD credits (if any), spend-based CUD discounts or resource-based CUD credits, and commitment fee lines.
3. Open **CUD Analysis → Coverage** for a 30-day or 90-day window; note the CUD-covered share vs. on-demand remainder.
4. Switch to **Utilization**, inspect each commitment or scope; note underutilized hours.
5. Take an example of one machine series with SUD and one without SUD. Explain why discount rates differ.
6. Suppose a workload has 18 months of remaining life; compare a 12-month vs. 36-month commitment on savings and lock-in risk.
7. Write a short **CUD purchase decision memo** covering baseline, expected savings, downside case, rollout/migration plan, and approver.
8. Propose a purchase only after the memo is reviewed and product terms are verified.

Summary table usable in reviews:

| Item | Questions to Answer Before Purchase |
| --- | --- |
| Candidate | Is the CUD resource-based or spend-based? |
| Scope | Specific billing account, project, region, machine family, and eligible SKUs? |
| Baseline | What is the lowest recurring usage/spend? |
| Existing savings | What SUDs, other CUDs, or contract pricing currently apply? |
| Terms | 1 or 3 years, recurring fee, committed spend unit, start date? |
| Risk | What happens if workloads stop/migrate, change regions, or underutilize? |
| Recovery | Can eligible usage from another project absorb the commitment? |
| Decision | Expected net savings, break-even, approvals, and review schedule? |

## 15. CUD and SUD Mastery Checklist

- [ ] Can explain that SUDs apply automatically to eligible usage exceeding 25% of the billing month.
- [ ] Remember that SUDs cap at 20% or 30% depending on series, and do not apply to all VM types.
- [ ] Distinguish resource-based CUDs from spend-based/flexible CUDs.
- [ ] Know that CUDs typically have 1- or 3-year terms and create fixed commitment fees.
- [ ] Understand that CUDs do not automatically guarantee reservations/capacity.
- [ ] Never apply SUD and CUD simultaneously to the same slice of usage.
- [ ] Know that resource-based CUDs carry region/series constraints, and sharing depends on billing account settings.
- [ ] Know that compute flexible CUDs can cover eligible Compute Engine/GKE/Cloud Run spend, though not every SKU.
- [ ] Distinguish legacy CUD credits from newer discounted consumption models.
- [ ] Can calculate coverage, utilization, and savings while verifying consistent units.
- [ ] Compare CUDs against on-demand **with SUD**, not just list price.
- [ ] Use Billing Reports, CUD Analysis, and CUD Recommender to evaluate before purchasing.
- [ ] Know that commitments are difficult or impossible to cancel/reduce after purchase; enforce an approval workflow.
- [ ] Size commitments to the baseline, not traffic peaks.
- [ ] Establish processes to track utilization, expiration, migrations, and unused fees.
- [ ] Consider rightsizing, scheduling, and Spot VMs before locking in multi-year spend.

## References

- [Google Cloud — Committed use discounts overview](https://docs.cloud.google.com/docs/cuds) — CUD types, service scope, and commitment terms.
- [Compute Engine — Committed use discounts overview](https://docs.cloud.google.com/compute/docs/instances/committed-use-discounts-overview) — resource-based and compute flexible CUDs, scope, eligible usage, and order of application.
- [Compute Engine — Resource-based CUDs](https://docs.cloud.google.com/compute/docs/instances/signing-up-committed-use-discounts) — configuring resource commitments, region and machine type constraints.
- [Compute Engine — Sustained use discounts](https://docs.cloud.google.com/compute/docs/sustained-use-discounts) — automatic mechanism, usage thresholds, eligible series, and 20%/30% rates.
- [Spend-based CUDs and consumption models](https://docs.cloud.google.com/docs/cuds-multiprice) — discounted prices replacing legacy credits, purchasing guide, and migration.
- [Compute Engine reservations with commitments](https://docs.cloud.google.com/compute/docs/instances/reservations-with-commitments) — distinguishing commitments and capacity reservations.
- [Cloud Billing — CUD Analysis](https://docs.cloud.google.com/billing/docs/how-to/analyze-cuds) — coverage, utilization, savings, and commitment effectiveness.
- [Cloud Billing — CUD recommendations](https://docs.cloud.google.com/docs/cuds-recommender) — usage insights and commitment level suggestions.
- [Cloud Billing — Savings and credits reports](https://docs.cloud.google.com/billing/docs/how-to/reports/savings-and-credits) — costs, discounts, credits, and attribution.
- [Cloud Billing — Compute flexible CUD savings](https://docs.cloud.google.com/billing/docs/how-to/cud-analysis-flexible) — calculating savings and eligible resources.
- [Cloud Billing — Export usage cost data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery) — setting up exports and analyzing invoices by SKU.
