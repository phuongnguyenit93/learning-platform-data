# Cost Allocation Using Showback and Chargeback Models

An enterprise may have multiple product teams sharing a subscription, an Azure Kubernetes Service (AKS) cluster, networking, an observability platform, and data services. When the Azure bill increases, the question "which team is responsible for that increase?" is often harder to answer than "which service incurred the fee?" Part of the spend can be traced directly to an application via resource ID or tags, but much of it consists of **shared costs**, commitment purchases, or charges lacking a clear resource owner.

In the **Cost Management** chapter of the Microsoft Azure track (**CLOUD_PROVIDERS_AZURE**), this lesson teaches how to design two allocation mechanisms: **showback** (cost transparency for consuming teams) and **chargeback** (posting allocated costs to internal budgets or accounting ledgers). The material connects subscription/resource group management, Microsoft Entra ID, networking, compute, storage, databases, monitoring, security, and operating an Azure application.

The goal is an allocation method that is **fair, explainable, reproducible, and reconciled to the grand total**. A solid model lets product teams see the cost impact of engineering decisions without distorting invoices or creating duplicate charges.

> **Example convention:** Monetary amounts, percentages, transactions, and cost codes in this lesson are hypothetical figures for practice, not current Azure invoices or unit rates. Data export formats, permissions, and automated allocation capabilities also depend on agreement type, billing scope, and supported Azure features.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish showback, chargeback, direct cost, shared cost, unallocated cost, and cost-accountable units.
2. Build a mapping model across **billing scope → subscription → resource → application → cost center**.
3. Establish tag/metadata standards and handle untagged costs, charges without resource IDs, or shared resources.
4. Select allocation drivers for networking, AKS nodes, shared databases, observability, and platform services.
5. Calculate fixed-percentage, consumption-based, and weighted allocations; verify pre/post totals.
6. Distinguish actual cost, amortized cost, purchases, credits, taxes, and invoice data in internal reporting.
7. Design a phased rollout from showback to controlled chargeback, dispute resolution, and change tracking.
8. Propose data schemas, dashboards, quality thresholds, and an operating cadence for a FinOps program.

## 2. How Do Showback and Chargeback Differ?

**Showback** reports the costs a team or product is consuming. Teams see their direct charges, allocated shared costs, and usage trends, without necessarily executing budget transfers or accounting journal entries.

**Chargeback** applies approved allocation rules to **record costs against cost centers, budgets, business units, or internal ledgers**. It is a financial governance decision. It does not mean Azure issues separate invoices to each application team.

| Criterion | Showback | Chargeback |
| --- | --- | --- |
| Goal | Create transparency and usage accountability | Assign actual financial accountability |
| Output | Dashboards, breakdown tables, cost reports | Finalized allocation tables, budget transfer / journal proposals |
| Data rigor | Must be consistent; may show labeled estimates | Requires reconciliation, documentation, rule versioning, and sign-off |
| Dispute handling | Collaborate to fix mappings and drivers | Formal dispute, adjustment, and audit workflow |
| Benefit | Engineers understand cost drivers | Incentivizes budget-aligned optimization |
| Risk | Reports ignored if not paired with action | Unfair allocations create perverse incentives |

**Example:** A shared AKS node pool costs 1,800 USD in a month. The showback report attributes 900 USD to Orders, 540 USD to Catalog, and 360 USD to Analytics. Chargeback takes those same reconciled and approved numbers to post costs across three cost centers. **The original Azure invoice remains the organization's underlying expense.**

A sensible rollout starts with showback, validates data and methodology, and only then advances to chargeback. Never begin charging teams while large amounts of spend remain unattributed.

## 3. Clearly Defining Allocation Targets

Accurate allocation first requires answering **"who is accountable?"** and **"which product owns the spend?"** The two answers do not always coincide.

| Entity | Example | Responsibility |
| --- | --- | --- |
| **Business unit** | Commerce | Manages budget at business level |
| **Cost center** | CC-410 | Accounting unit receiving chargeback |
| **Application / product** | orders-api | Product whose cost is measured |
| **Workload** | online-checkout | Business flow consuming resources |
| **Team / owner** | orders-platform | Accountable for operations and optimization |
| **Environment** | dev, staging, prod | Separates non-production testing from production |
| **Shared service** | AKS platform, API gateway, monitoring | Generates shared spend for multiple products |
| **Billing scope** | Billing account/profile/section, subscription | Data source and payment boundary |

A **cost center** is an accounting or budget management unit. One application may have two supporting teams, while one cost center may fund multiple applications. Maintain a versioned mapping table rather than guessing from resource names.

### 3.1. Governance Scopes Do Not Exactly Match Billing Scopes

On Azure, resources live inside subscriptions and resource groups; billing accounts/profiles/sections may follow a separate hierarchy per agreement. An invoice can span multiple subscriptions plus charges detached from any resource group.

~~~mermaid
flowchart TD
    B["Billing scope / cost period"] --> E["Cost Details and other charges"]
    E --> D["Owner/resource-mapped costs"]
    E --> S["Shared cost pools"]
    E --> U["Unallocated / pending review"]
    D --> A["Applications and cost centers"]
    S --> R["Allocation rules + driver metrics"]
    R --> A
    A --> SH["Showback report"]
    SH --> CH["Approved chargeback ledger"]
    U --> GOV["FinOps / budget owners resolve"]
~~~

Under some agreements, financial data access differs from resource Azure RBAC. Someone with Contributor on a resource group cannot necessarily download invoices or view negotiated contract discounts. Cost data pipelines therefore need properly scoped billing read access and controlled storage.

## 4. Categorizing Costs Before Allocating

Do not feed every cost line into a single proportional split. Categorize first:

| Category | Meaning | Examples | Handling |
| --- | --- | --- | --- |
| **Direct cost** | Cleanly tied to one application/cost center | Dedicated App Service plan, dedicated Orders DB | Allocate 100% directly |
| **Shared cost** | Consumed by multiple applications | Shared AKS nodes, NAT Gateway, Log Analytics workspace | Allocate via measurable driver or approved rule |
| **Platform overhead** | Supports the entire platform/organization | Security baseline, shared CI/CD runners | Follow org policy or hold in platform cost center |
| **Unallocated cost** | Insufficient evidence to assign owner | Untagged spend, unknown resources, missing mapping | Hold in triage bucket; avoid arbitrary splitting |
| **Commitment/purchase** | Reservation/savings plan purchases or benefits | Upfront reservation fee | Choose actual/amortized per goal; avoid double counting |
| **Non-usage / financial** | Taxes, support, refunds, credits, Marketplace, etc. | Support plan fees and adjustments | Apply dedicated finance policy or keep at billing level |

A **charge with a Resource ID** can still be a shared cost. For example, all AKS nodes belong to the cluster resource group, yet the node pool serves multiple namespaces; you cannot assign 100% of node spend to the cluster team based solely on resource group.

An **untagged resource** is not necessarily "ownerless." Ownership may be traced via inventory, IaC state, CMDB, naming standards, or verified subscription mappings. Always log the **inference source and confidence level**, never unverified guesses.

## 5. Choosing the Cost Basis Before Calculating

**Actual cost** and **amortized cost** serve different analytical lenses. With reservations/savings plans, a purchase may record at purchase time in actual cost, whereas amortized cost distributes commitment value over time and/or benefit usage.

| Purpose | Basis to Consider | Notes |
| --- | --- | --- |
| Reconciling cash against invoice | Invoice/actual data matching agreement | Account for taxes, credits, refunds, support, Marketplace, cutoff |
| Analyzing application operating economics | Amortized cost when eligible commitments exist | Also track unutilized commitment portions |
| Short-term showback | One chosen basis clearly labeled on dashboard | Never mix actual and amortized in one total |
| Monthly chargeback | Policy basis approved by Finance | Version the report, source, rounding, and adjustments |

**Never add actual cost and amortized cost together** to produce a total. They can represent the same spend at different times. For datasets formatted in FOCUS or Cost Management exports, read the exact cost fields, pricing/charge categories, and available sources—never assume every Azure export shares identical column names.

### 5.1. Allocation Period and Currency

Every allocation run must lock down:

- Authorized billing account/section/subscription scope.
- Target month/period per **invoice** and selected usage window.
- Timezone, export timestamp, and preliminary vs. closed status.
- Source currency; exchange rate and rate source if converting.
- Cost type (actual/amortized), plus treatment of credits/taxes/support.
- Excluded rows and documented rationale.

Do not allocate part in USD and part in VND and sum them directly; never use today's spot FX rate to alter an already issued invoice amount.

## 6. Ownership Model: From Tags to Mapping Tables

### 6.1. Minimum Metadata Standard

Reference tag policy:

~~~yaml
application: orders-api
businessUnit: commerce
costCenter: CC-410
owner: orders-platform
environment: prod
managedBy: iac
dataClassification: internal
~~~

This is a **metadata example**, not a file that automatically deploys Azure tags. Integrate tags into IaC/pipelines and enforce via policy where appropriate. Never put PII, tokens, or passwords in tags.

Tags assist analysis where supported by services and surfaced in cost data. Still, **not every charge carries tags, not every resource supports tags identically, and tagging today does not automatically fix history**.

### 6.2. Ownership Resolution Precedence

A consistent resolution hierarchy:

1. **Approved direct mapping** by resource ID/application with effective dates.
2. **Valid `costCenter`/`application` tag** cross-checked against the owner catalog.
3. **Subscription/resource group ownership** when the boundary strictly serves one product.
4. **Platform/IaC/CMDB mapping table** verified by operations.
5. **Shared pool** when multiple applications consume the resource.
6. **Unallocated** when evidence is still missing.

Do not allow a coarse rule like "everything in this subscription belongs to Orders" to override an approved detailed mapping for shared platform infrastructure. Publish precedence rules explicitly.

### 6.3. Mappings Must Be Time-Bounded

Example:

| Resource / Resource Group | Owner | Effective From | Effective To | Source |
| --- | --- | --- | --- | --- |
| /subscriptions/.../orders-db | CC-410 | 2026-01-01 | Open | Approved CMDB |
| rg-commerce-shared | Shared-commerce | 2026-01-01 | Open | Platform inventory |
| orders-api (app ID) | CC-410 | 2026-01-01 | 2026-09-30 | Product catalog |
| orders-api (app ID) | CC-510 | 2026-10-01 | Open | Org reorganization |

When ownership changes mid-month, define splitting by **usage date** or an approved cutover rule. Mutating a single current-owner table and recomputing past months will silently rewrite historical reports.

## 7. Shared Cost Allocation Methods

No single formula is fair for every resource type. Choose a **driver closely tied to what causes the cost**, backed by reliable, auditable metrics.

### 7.1. Fixed Percentage Allocation

When granular telemetry is lacking, the organization may approve fixed pool percentages:

\[
A_{i,p}=C_p \times w_{i,p}
\]

Where \(C_p\) is the cost of pool \(p\), and \(w_{i,p}\) is the weight assigned to team \(i\). Constraints:

\[
\sum_i w_{i,p}=1,\qquad 0\leq w_{i,p}\leq 1
\]

Example for a 600 USD network gateway: Orders 50%, Catalog 35%, Analytics 15% → 300, 210, and 90 USD respectively.

Pros: easy to explain and implement. Cons: ignores daily consumption shifts; if kept too long, lighter consumers subsidize heavier ones. Best used as a time-boxed transition method.

### 7.2. Consumption-Based Allocation

Given driver metrics \(u_{i,p}\) per team:

\[
w_{i,p}=\frac{u_{i,p}}{\sum_j u_{j,p}},\qquad
A_{i,p}=C_p \times w_{i,p}
\]

Example gateway with 20 TiB verified egress: Orders 10 TiB, Catalog 7 TiB, Analytics 3 TiB. Shares are 50%, 35%, 15%, splitting the 600 USD pool into 300, 210, and 90 USD.

**Match the driver to the exact meter boundary:** measured ingress bytes do not always equal billable outbound bytes; raw API request counts are not necessarily a fair proxy for data transfer charges. Check meter names and traffic directions.

### 7.3. Weighted Allocation

When workloads have differing resource profiles, use a published composite driver. For example, a shared compute pool can weight **CPU request-hours** and **memory request-GiB-hours** using an approved blend, or build node-level cost attribution from resource usage/requests and node rates.

Suppose internal policy picks:

\[
s_i = 0.7 \times \frac{cpu_i}{\sum_j cpu_j}
      + 0.3 \times \frac{memory_i}{\sum_j memory_j}
\]

Since each normalized ratio sums to 1, \(\sum s_i = 1\). The **70% CPU / 30% memory** split is an internal governance assumption, not an Azure rule; it may poorly fit memory-bound or GPU-bound nodes. Test outputs and align with charged teams before adopting.

### 7.4. Business-Unit Metric Allocation

For uniform transactional platforms, some fees can split by **successful transactions, orders, active accounts, or completed jobs**. Do not apply the same unit across products with radically different cost profiles.

If a payment platform handles 100,000 valid transactions from Orders and 50,000 from Marketplace, transaction-weighted allocation of a platform fee may be reasonable. However, if costs scale primarily with payload size, raw request counts will distort results.

### 7.5. When Not to Allocate?

Costs lacking a reliable owner or driver should remain **unallocated** with an assigned investigator. Never split evenly just to make a report look "100% allocated." Enterprise security baselines or corporate support plans may also belong in **central IT** by policy; there is no mandate to push every dollar down to product teams.

## 8. Designing Clean Cost Pools

A **cost pool** groups charges sharing the same nature and allocation rule.

| Cost Pool | Source Data | Suggested Driver | Validation Checks |
| --- | --- | --- | --- |
| **AKS shared nodes** | Identified node VM/disk charges | CPU/memory consumption or requests per Pod/namespace | Total usage, idle nodes, DaemonSets, system namespaces |
| **API gateway** | Gateway compute/requests | Requests or traffic bytes per route/app | Separate routes, retries, and health probes |
| **Shared NAT/egress** | Properly grouped NAT/network meters | Egress bytes or relevant connection usage | Network path differences and traffic types |
| **Log Analytics workspace** | Ingestion/retention charges | Ingested GiB per app/team and retention | Sampling rules, shared logs, records missing application |
| **CI/CD runners** | Node/agent/compute or licenses | Build minutes, agent-hours, pipeline runs | Idle agent capacity and queue wait |
| **Shared database** | SQL compute/storage/backup | Query/DTU/vCore metrics, storage, transactions, or agreed key | Avoid treating all queries as equal cost |
| **Security baseline** | Governance/security tools | Protected resource count, workload coverage, or central policy | Avoid double counting direct security fees |

**Pools must be mutually exclusive.** If AKS node VMs are already in the AKS shared nodes pool, never add those same lines into an application's direct compute. Track original source row IDs and enforce "each charge belongs to at most one input bucket."

A pool can be split by cost behavior: e.g., three apps' log ingestion allocated by ingested bytes, while shared workspace overhead stays in central IT. Separating by cost behavior makes splits easier to defend.

## 9. AKS Cost Allocation Specifics

AKS clearly illustrates the gap between **how Azure bills** and **how enterprises account**. Invoices reflect underlying infrastructure such as node VMs, disks, load balancers, networking, and associated tiers; Kubernetes namespaces or Pods are not billed directly as line items on Azure invoices.

### 9.1. Separating Three Cost Layers

1. **Node capacity cost:** Provisioned VMs/nodes running workloads.
2. **Pod consumption/request cost:** CPU/memory requested or consumed by each workload.
3. **Unallocated/idle/system overhead:** Unused slack capacity, DaemonSets, system pods, platform overhead, and untraceable spend.

If total node cost is 1,800 USD and only 70% of capacity is actively consumed by apps, decide how to treat the **30% idle cost**. You can distribute idle capacity proportionally across active usage, or hold it in the platform cost center to incentivize rightsizing. Either approach works if agreed upon and published.

**Do not equate CPU usage with CPU requests.** In Kubernetes, requests reserve scheduling capacity; usage reflects actual consumption. Teams setting inflated requests tie up capacity and force extra nodes despite low usage. A fair model reports **both request-based and usage-based views** for insight, then selects an explicit basis for chargeback.

### 9.2. Data Required for AKS Allocation

- Pod/workload/namespace and **application**, **team**, **environment** labels.
- Node pool, node SKU, zone, and corresponding VM/node costs.
- Time-series CPU/memory requests and usage.
- Pod runtime windows, node provisioning intervals, and idle/system share.
- Persistent volumes/disks mapped to workloads.
- Shared ingress, load balancer, and outbound networking components.

You can use container/Kubernetes cost tooling, Prometheus/Azure Monitor metrics, or custom pipelines. Verify schemas, versions, and behavior; a tool displaying estimated workload costs **does not alter the Azure invoice**.

## 10. Azure Cost Management and Allocation Data Sources

### 10.1. Raw Cost Data

In the Azure Portal, **Cost Management → Cost Analysis** lets you explore spend by scope, service, resource, resource group, tag, or available attributes. **Cost Details** and **Cost Management Exports** extract granular rows for internal allocation pipelines.

Conceptual fields to map:

~~~text
BillingScope
BillingPeriod / UsageDate
SubscriptionId
ResourceId / ResourceGroup
Product / Service / MeterId / MeterName
ChargeType / PricingModel
Quantity / UnitOfMeasure
CostAmount / BillingCurrency
Tags
~~~

This is a **conceptual field model**, not an assertion that every Azure Cost Details file uses those exact column names. Export schemas vary by agreement, version, and data standard (such as FOCUS). When building ETL pipelines, inspect actual export headers and maintain an explicit schema mapping.

### 10.2. Azure Cost Management Cost Allocation Rules

Azure Cost Management provides **cost allocation** capabilities at supported scopes/scenarios. These rules reallocate costs for analytical views and have constraints on sources, targets, split types, and applicability. Verify scope support, permissions, and coverage on your billing account before relying on them.

**Do not assume a Cost Management allocation rule will:**

- Rewrite issued historical invoices.
- Automatically generate ERP chargeback journal entries for cost centers.
- Allocate every Marketplace fee, tax, purchase, or untagged resource.
- Replace granular Pod, query, or transaction telemetry in complex shared pools.

For specialized needs, build an internal allocation pipeline from finalized exports and verified telemetry to produce showback reports and proposed chargeback ledgers. Whether using built-in features or custom pipelines, always enforce **total-cost conservation checks and rule version history**.

### 10.3. Supplemental Non-Invoice Data Sources

| Source | Data Provided | Role |
| --- | --- | --- |
| Azure Cost Details/Exports | Amounts, service, meter, scope, dates | Cost source |
| Azure Resource Graph / inventory | Resource ID, subscription, tags, resource type | Ownership enrichment |
| IaC / CMDB / product catalog | App-to-team, cost center, mapping effective dates | Owner resolution |
| Azure Monitor / Application Insights | Requests, dependencies, bytes, per-app log ingestion | Allocation drivers |
| Kubernetes metrics / cost tooling | CPU/memory requests/usage and namespaces | AKS drivers |
| Finance billing records | Invoices, credits, taxes, adjustments, commitment purchases | Reconciliation and accounting |

Keep a clear boundary between **official meter costs** and **telemetry-derived drivers**. If metrics are sampled or incomplete, resulting shares are estimates; label data quality transparently in reports.

## 11. End-to-End Allocation Pipeline

~~~mermaid
flowchart TD
    E["Azure Cost Export - raw source"] --> N["Normalize schema, currency, scope, charge type"]
    N --> R["Deduplicate / prevent overlapping rows"]
    R --> D["Direct ownership mapping"]
    R --> P["Shared cost pool assignment"]
    R --> U["Unallocated"]
    M["Per-app metrics/drivers"] --> V["Compute pool shares"]
    P --> V
    V --> A["Allocated ledger by cost center"]
    D --> A
    A --> C["Reconciliation: direct + allocated + unallocated"]
    U --> C
    C --> S["Showback dashboard"]
    S --> Q["Review, dispute, freeze"]
    Q --> F["Approved chargeback"]
~~~

### 11.1. Execution Steps

1. **Ingest source:** Pull exports for the exact billing scope/period/cost type, keeping raw files immutable with extraction timestamps.
2. **Normalize:** Map columns, currency, accounts, services/meters, charge types, resource IDs, and tags.
3. **Filter scope:** Separate out-of-basis lines per policy, such as taxes or support.
4. **Assign direct costs:** Join against time-bounded ownership mappings.
5. **Form pools:** Bucket shared lines so no single row enters two pools.
6. **Join drivers:** Pull matching metrics for the identical window, scope, and unit.
7. **Compute shares:** Validate non-negative drivers, sum-to-100% checks, and missing-data fallbacks.
8. **Allocate:** Generate ledger lines referencing source charge/pool, rule version, and owner.
9. **Reconcile:** Sum direct + allocated + unallocated; verify variance, rounding, and exceptions.
10. **Publish showback:** Share dollar amounts and drivers; collect team feedback.
11. **Approve chargeback:** Finance closes the period and issues allocation tables/journal entries per internal process.
12. **Monitor:** Inspect anomalies, resolve disputes, and refine rules for the next cycle.

**Every allocation period must be reproducible.** Identical data snapshots, mapping versions, driver versions, and rule versions must yield identical outputs. When updating rules, never overwrite closed reports—create new versions and traceable adjustments.

## 12. Complete Example: Three Teams Sharing Azure

Suppose in a hypothetical allocation period, an enterprise operates three products:

- **Orders** – cost center **CC-410**.
- **Catalog** – cost center **CC-420**.
- **Analytics** – cost center **CC-430**.

Underlying cost data has been normalized to a consistent analytical cost basis. To prevent double counting, **direct compute** here covers resources dedicated to each application, while **shared AKS nodes** holds only node costs not already included in the direct table.

### 12.1. Direct Costs

| Direct Cost | Orders | Catalog | Analytics | Total |
| --- | ---: | ---: | ---: | ---: |
| Dedicated app compute/services | 1,240 USD | 820 USD | 590 USD | 2,650 USD |
| Dedicated database | 360 USD | 280 USD | 210 USD | 850 USD |
| Dedicated storage | 150 USD | 100 USD | 50 USD | 300 USD |
| **Total direct** | **1,750 USD** | **1,200 USD** | **850 USD** | **3,800 USD** |

These items map 100% to owners via resource ID/IaC and cost centers active on the usage dates.

### 12.2. Shared Cost Pools and Drivers

| Pool | Total Amount | Selected Driver | Orders | Catalog | Analytics |
| --- | ---: | --- | ---: | ---: | ---: |
| AKS shared nodes | 1,800 USD | Verified CPU/memory share | 50% | 30% | 20% |
| Gateway/network | 600 USD | Egress bytes per application | 50% | 35% | 15% |
| Observability | 400 USD | Ingested GiB per application | 45% | 25% | 30% |
| Shared security | 200 USD | Weighted protected resource count | 50% | 30% | 20% |
| **Total shared pools** | **3,000 USD** | | | | |

Each **row** sums to 100%. You cannot apply Orders' 50% rate across every pool when each pool relies on a distinct driver.

### 12.3. Shared Pool Allocation Results

| Pool | Orders | Catalog | Analytics | Check |
| --- | ---: | ---: | ---: | ---: |
| AKS shared nodes | 900 USD | 540 USD | 360 USD | 1,800 USD |
| Gateway/network | 300 USD | 210 USD | 90 USD | 600 USD |
| Observability | 180 USD | 100 USD | 120 USD | 400 USD |
| Shared security | 100 USD | 60 USD | 40 USD | 200 USD |
| **Shared allocated** | **1,480 USD** | **910 USD** | **610 USD** | **3,000 USD** |

Single-line calculation:

\[
A_{\text{Catalog, Gateway}}=600\times 35\%=210\ \text{USD}
\]

### 12.4. Post-Allocation Showback

Suppose **200 USD** remains from meters whose owner is not yet verified. The interim decision is to hold it in **Unallocated** rather than forcing a split across the three teams.

| Component | Orders | Catalog | Analytics | Unallocated | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct | 1,750 | 1,200 | 850 | 0 | 3,800 |
| Shared allocated | 1,480 | 910 | 610 | 0 | 3,000 |
| Unidentified owner | 0 | 0 | 0 | 200 | 200 |
| **Total (USD)** | **3,230** | **2,110** | **1,460** | **200** | **7,000** |

**Conservation check:**

\[
3,800+3,000+200=7,000
\]

\[
3,230+2,110+1,460+200=7,000
\]

Total allocated across the three teams is **6,800 USD**, or roughly **97.14%** of the 7,000 USD cost basis. **200 USD (2.86%)** lacks an owner and stays visible. Unallocated spend must have an assigned investigator, SLA deadline, and reason code.

**Important scope note:** 7,000 USD here is a **chosen internal cost basis** normalized for this learning scenario, excluding excluded items such as taxes or other financial entries. It does not automatically equal the cash amount payable on the Azure invoice.

### 12.5. Moving from Showback to Chargeback

During the showback review window, all three teams inspect the report and drivers and can raise feedback. Once Finance and budget owners sign off:

| Cost Center | Proposed Chargeback Amount | Notes |
| --- | ---: | --- |
| CC-410 / Orders | 3,230 USD | Direct costs + shared costs |
| CC-420 / Catalog | 2,110 USD | Direct costs + shared costs |
| CC-430 / Analytics | 1,460 USD | Direct costs + shared costs |
| Central / Unallocated | 200 USD | Pending owner verification |

Chargeback may take the form of **budget transfers or internal cost offsets**, depending on accounting systems. When posting, ensure each source dollar is charged back once only. Never record the full 7,000 USD in central IT as a final cost while also charging 6,800 USD to the three product teams without a matching offset entry.

## 13. Rounding While Preserving Totals

In practice, shares rarely divide cleanly to the exact cent. Splitting a 100 USD pool equally across three teams gives:

\[
100/3=33.3333\ldots
\]

Rounding each down to 33.33 USD totals only 99.99 USD. Rounding all three up to 33.34 USD totals 100.02 USD.

A straightforward fix is the **largest remainder method** at the smallest currency unit:

1. Compute exact unrounded values.
2. Convert to cents or the currency's smallest minor unit.
3. Floor each team's share to an integer minor unit.
4. Distribute leftover cents in descending order of fractional remainders, using a deterministic tie-breaker.
5. Assert that the sum of allocated amounts equals the exact pool total.

Splitting 100 USD three ways yields **33.34 + 33.33 + 33.33 = 100 USD**, following a published tie-break rule for which team gets the extra cent.

Avoid IEEE floating-point numbers for financial settlement whenever possible. Use exact decimal arithmetic or integer minor currency units, and standardize whether **rounding happens per pool/row or at the cost-center total**.

## 14. Designing the Allocation Data Schema

A minimal internal model separates **raw charges**, **owner mappings**, **driver measurements**, **rules**, and the **output ledger**.

### 14.1. Recommended Tables

| Table | Key Fields | Purpose |
| --- | --- | --- |
| **cost_source** | source_row_id, period, subscription, resource_id, meter_id, charge_type, amount, currency | Normalized raw charges |
| **ownership_map** | resource_pattern, application, cost_center, effective_from, effective_to, approved_by | Time-bounded ownership mapping |
| **pool_membership** | source_row_id, pool_id, classification_reason | Maps each charge to at most one pool |
| **allocation_rule** | rule_id, version, pool_id, driver, fallback, valid_from, valid_to | Allocation rules |
| **driver_values** | period, pool_id, application, measured_value, unit, data_quality | Driver measurements |
| **allocation_ledger** | allocation_id, period, source_or_pool_id, rule_version, target, allocated_amount, currency | Auditable allocation output |
| **reconciliation** | period, basis_total, direct_total, allocated_total, unallocated_total, diff, status | Conservation verification |

**`source_row_id`** must be stable enough to prevent duplicates if the same export is re-ingested. If the source lacks a unique ID, construct a conditional composite key from stable fields plus snapshot ID, while handling legitimate identical-looking rows properly.

### 14.2. Example Rule Definitions as Data

~~~yaml
period: "2026-11"
costBasis: amortized-operating-cost
currency: USD
rules:
  - pool: shared-aks-nodes
    method: measured-proportional
    driver: weighted-cpu-memory-consumption
    ruleVersion: 3
    missingDriverBehavior: keep-unallocated
  - pool: gateway-egress
    method: measured-proportional
    driver: attributable-egress-gib
    ruleVersion: 2
    missingDriverBehavior: keep-unallocated
  - pool: security-platform
    method: approved-fixed-percent
    weights:
      orders: 0.50
      catalog: 0.30
      analytics: 0.20
    ruleVersion: 1
    missingDriverBehavior: reject-rule
~~~

This is an **illustrative schema defined by this lesson**, not a native Azure Cost Management allocation rule format or API payload accepted verbatim by Azure.

### 14.3. Pseudocode for an Allocation Run

~~~text
source = load_frozen_cost_snapshot(period, scope, basis, currency)
assert no_duplicate_source_rows(source)

direct, shared, unallocated = classify_each_source_once(source)

ledger = assign_direct_costs(direct, ownership_map_version)

for pool in shared:
    rule = approved_rule_for(pool, period)
    driver = validated_driver_values(pool, period, rule.version)
    if driver.missing_or_invalid:
        unallocated.add(pool, reason="MISSING_DRIVER")
        continue

    shares = normalize_nonnegative_driver(driver)
    assert sum(shares) == 1
    amounts = allocate_with_deterministic_rounding(pool.amount, shares)
    assert sum(amounts) == pool.amount
    ledger.add(amounts, source_pool=pool.id, rule=rule.version)

assert source.in_scope_total == (
    sum(ledger.amounts) + sum(unallocated.amounts)
)
publish_showback(ledger, unallocated, source.snapshot_id)
~~~

When a pool spans multiple source rows, standardize whether you sum first and round once at pool level or round per row. Never feed the output ledger back in as a raw charge source, which creates cycles and double counting.

## 15. Data Quality Rules and Reconciliation

**Cost allocation is a financial data transformation**, so it requires controls comparable to core reporting systems.

### 15.1. Mandatory Invariants

For a fixed scope, period, currency, and cost basis:

\[
\text{Source total}
=\text{Direct allocated}
+\text{Shared allocated}
+\text{Unallocated}
\]

At the individual pool level:

\[
\text{Pool amount}=\sum_{i} \text{Allocated amount}_{i}
\]

And:

- Each source charge is classified exactly once.
- No rule uses negative weights, or weights not summing to 100% when full distribution is required.
- Ownership mappings carry effective dates, with no competing owners for the same row lacking a precedence rule.
- Drivers specify units, measurement windows, sources, and quality flags.
- Rounding neither destroys nor creates money.
- Foreign-currency lines are segregated until converted under an approved FX rule.

### 15.2. FinOps Program Quality Metrics

| Metric | Suggested Formula | Explanation |
| --- | --- | --- |
| **Allocation coverage** | (Direct + shared allocated) / in-scope total | Share of spend assigned to a target |
| **Unallocated rate** | Unallocated / in-scope total | Share requiring triage or held centrally |
| **Tag compliance** | Compliant resources / applicable resources | Does not directly reflect untagged dollar volume |
| **Rule coverage** | Shared pools with valid rules / total shared pools | Readiness for allocation |
| **Data freshness** | Period covered up to latest data timestamp | Is data mature enough for month-end close? |
| **Reconciliation difference** | Source total − output total | Must equal 0 within defined scope |
| **Disputed allocated cost** | Total disputed amount / total proposed chargeback | Measures owner acceptance |

A sample target might be **coverage above 95% and reconciliation difference equal to 0**. The 95% threshold is an organizational target, not an Azure standard. Never hide the remaining 5% by dumping it onto a default owner without evidence.

### 15.3. Late-Arriving Data and Corrections

Cost Management data can arrive late, adjust, refund, or shift periods. Therefore:

1. Publish **provisional** reports during an open month.
2. Close after sufficient ingestion lag and matching invoice availability.
3. Archive immutable snapshots, rule versions, shares, and outputs.
4. If later adjustments arrive, post a **correction ledger** to the relevant or subsequent period per Finance policy.
5. Never silently overwrite previously published showback/chargeback history.

Do not treat today's numbers as final merely because the calendar month just ended.

## 16. Reservations, Savings Plans, and Committed Spend

Commitments introduce a distinct nuance: cash payments and economic consumption of usage can appear at different times.

### 16.1. Choosing the Right Basis

When measuring **the true economic cost borne by compute-consuming teams**, an amortized basis helps by spreading commitment value over time and benefiting usage. When reconciling **the monthly cash invoice**, rely on actual purchase/charge entries on billing documents and matching actual cost data.

**Never add upfront reservation purchases back onto all cost centers** if amortized benefits are already included in the cost basis. That double-counts spend.

### 16.2. Unused Commitments

Suppose an eligible commitment costs a hypothetical 1,200 USD for a period, but only 80% is utilized per internal evaluation rules:

| Illustrative Component | Value |
| --- | ---: |
| Total commitment cost amortized to period | 1,200 USD |
| Portion matched to eligible usage (80%) | 960 USD |
| Unutilized portion (20%) | 240 USD |

The organization may choose to:

- Charge 960 USD to benefiting product teams and hold 240 USD in central FinOps/platform to incentivize better coverage; or
- Allocate the unused portion back to business units that requested the commitment under an approved policy.

**This is an internal policy choice**, not an exact depiction of Azure's per-transaction savings plan/reservation matching algorithm. In practice, use your account's actual utilization, coverage, and amortized datasets.

### 16.3. Benefits Do Not Mean Negative Fees

A workload covered by a reservation may display usage costs differing from pay-as-you-go, while the purchase sits in another billing scope. Reconcile **benefit utilization, unused commitments, sharing scopes, and charge categories** before posting items to cost-center reports.

## 17. Credits, Taxes, Marketplace, Support, and Financial Charges

For non-usage items, policy must clearly state **whether they are split or held centrally**:

| Item | Common Handling Options | Key Considerations |
| --- | --- | --- |
| **Promotional credit** | Assign to recipient entity or hold at billing level | Terms may restrict eligible services and validity |
| **Refund / adjustment** | Return to original cost center/pool if traceable | May post in a subsequent period |
| **Tax** | Per Finance/legal; often excluded from engineering showback | Legal entity, jurisdiction, and tax rules |
| **Support plan** | Central IT or allocated via enterprise policy | Not every fee carries a resource ID |
| **Marketplace** | Direct to purchasing product or shared policy | Publisher contracts and invoicing mechanics may vary |
| **Exchange difference** | Hold centrally or allocate per accounting policy | Never use spot rates to alter closed invoices |
| **Security compliance overhead** | By protected resources or central policy | Avoid double-counting fees already embedded in services |

**There is no universal rule** for these items. For legally/financially binding chargeback, rules on taxes, credits, and adjustments belong to Finance and corporate policy; engineering provides transparent data and formulas.

## 18. What Should a Showback Dashboard Display?

An engineering-focused dashboard should surface **root causes**, not just dollar totals.

| View | Contents | Question Answered |
| --- | --- | --- |
| **Overview** | Totals by cost center, trends, direct/shared/unallocated | How much are we spending? |
| **Cost drivers** | Compute, database, storage, network, logs, commitments | Which meters are driving cost up? |
| **Shared allocation** | Pool totals, drivers, weights, rule versions | Why was our team charged 900 USD for AKS? |
| **Quality** | Missing tags, missing drivers, unallocated spend, reconciliation | How trustworthy is this report? |
| **Unit economics** | Cost per successful order/job/transaction | What is our unit business cost? |
| **Actions** | Rightsizing, idle resources, log ingestion, storage retention | What levers can the team pull? |
| **Governance** | Period, currency, cost basis, snapshot, owner, approval status | Are these numbers finalized? |

### 18.1. Post-Allocation Unit Economics

Suppose Orders completes **250,000 valid orders** in the period on a **3,230 USD** cost basis:

\[
\text{Cost/order} = 3,230/250,000 = 0.01292\ \text{USD}
\]

\[
\text{Cost/1,000 orders}=12.92\ \text{USD}
\]

This is an illustrative calculation excluding broader corporate overhead. For month-over-month tracking, keep **successful-order definitions, cost scope, and allocation rules** consistent. Do not compare Orders' cost/order directly against Analytics' cost/job as if they measure the same unit.

### 18.2. Measuring Efficiency Without Perverse Incentives

Rewarding teams purely for cutting Azure spend can incentivize disabling essential logs, shrinking backup retention, or dropping replicas—degrading SLOs. Pair showback with **availability, latency, error budgets, security/compliance, and cost per successful business transaction**.

FinOps aims to drive better decisions about **value and efficiency**, not blindly force every infrastructure bill downward.

## 19. Chargeback: Approval Workflow and Internal Accounting Entries

Chargeback adds stricter controls beyond showback:

1. **Period close:** Source costs, drivers, rule versions, and unallocated items are validated.
2. **Owner sign-off:** Each team gets a review window to dispute incorrect mappings/drivers.
3. **FinOps approval:** Confirms model integrity, consistency, and exception classification.
4. **Finance confirmation:** Verifies tax, credit, adjustment, GL account, and currency policies.
5. **Ledger issuance:** Records period, internal voucher ID, target cost center, amount, source, and approver.
6. **Offsetting entries:** Follows GL rules so corporate expenses are never double-counted.
7. **Post-close adjustments:** Issues referenced reversals/corrections rather than silent edits.

### 19.1. Illustrative Journal Entry

Suppose central IT initially holds 6,800 USD of spend attributable to the three identified teams under internal accounting:

~~~text
Debit  CC-410 Orders:     3,230 USD
Debit  CC-420 Catalog:    2,110 USD
Debit  CC-430 Analytics:  1,460 USD
Credit Central IT pool:   6,800 USD
~~~

This is an **internal accountability transfer diagram illustrating totals**, not formal accounting guidance under a specific standard. GL account codes, debit/credit targets, taxes, and ERP postings must follow Finance rules. The **200 USD unallocated** remains managed centrally or in a suspense account per policy.

**Never issue fake Azure invoices** or represent internal chargeback statements as official Microsoft invoices. Intercompany billing, if used, requires separate legal and tax treatment.

### 19.2. Dispute Resolution Workflow

Scenario: Catalog claims a 120 USD resource in the network pool transferred ownership to Orders on the 15th of the month. Resolution steps:

1. Open a dispute ticket citing period, cost row/pool, owner, and evidence.
2. Verify ownership transfer date, measurement period, and active mappings.
3. Recalculate using the effective-date split policy if data supports it.
4. Obtain confirmation from both owners and FinOps.
5. If the period is already closed, record a referenced adjustment rather than silently mutating old ledgers.
6. Re-verify reconciliation after the adjustment.

Publish dispute deadlines upfront. If a team does not respond within the SLA window, apply pre-agreed default approval rules consistently rather than ad hoc exceptions.

## 20. Governance and Role Responsibilities

| Role | Responsibilities |
| --- | --- |
| **FinOps / Cloud economics** | Allocation rules, data quality, cost drivers, efficiency tracking |
| **Platform/SRE** | Shared service inventory, Kubernetes/observability/network metrics, infra optimization |
| **Product owner** | Ownership confirmation, service consumption, optimization plans, and disputes |
| **Finance** | Cost centers, chargeback policy, invoice reconciliation, ledgers, and approvals |
| **Cloud administrator** | Billing/Cost Management access, tagging policies, exports, subscription governance |
| **Security/Compliance** | Financial data access control, document retention, and audit evidence |

Every shared pool needs at least **one rule owner**, **one driver-data owner**, **a next review date**, and **a missing-data fallback policy**. Without clear rule ownership, chargeback loses credibility.

### 20.1. Protecting Financial Data

Cost data can expose negotiated rates, discounts, org structure, workloads, resource topology, and business volumes. Enforce:

- Microsoft Entra ID and role-based access scoped tightly.
- Separation between a team's showback visibility and org-wide pricing/invoice access.
- Access controls, network restrictions, and retention on export storage accounts.
- Zero access keys or billing secrets embedded in reports.
- Least-privilege managed identities/service principals for automated exports.
- Audit trails for rule changes, exceptions, approvals, and sensitive reads.

Product-team dashboards may expose only **allocated costs** and approved drivers, avoiding unnecessary exposure of negotiated rates or peer teams' details.

## 21. Common Mistakes

| Issue | Consequence | Fix |
| --- | --- | --- |
| Splitting the total invoice evenly across teams | Light consumers overpay unfairly | Classify direct/shared/non-usage first |
| Splitting all AKS costs by Pod count | Ignores Pod size and runtime differences | Use CPU/memory requests/usage and isolate idle |
| Using ingress bytes to split outbound egress | Driver mismatches the billable meter | Measure actual outbound or a closer proxy |
| Dumping all untagged spend onto Platform | Skewed ownership and no incentive to tag | Map from trusted sources; isolate pending items |
| Adding actual and amortized costs | Double-counts commitment purchases | Standardize on one consistent cost basis |
| Dropping unused reservation costs | Allocated sum falls below cost basis | Hold unutilized spend centrally or per policy |
| Applying today's tags to historical spend | Rewrites past chargeback numbers | Use time-bounded mappings and immutable snapshots |
| Percentages fail to sum to 100% | Money created or lost | Validate weights and use deterministic rounding |
| One charge enters two pools | Double counting | Track source row IDs and enforce single classification |
| Treating sampled requests as exact counts | Distorted allocation | Audit telemetry sampling; use reliable metrics |
| Eliminating unallocated by forcing 100% splits | Hides poor data hygiene | Keep unallocated visible with reason codes and owners |
| Treating Cost Management allocation as cash transfer | False expectations about invoices/GL | Separate cost analytics from ERP chargeback |
| Lacking a dispute process | Teams lose trust | Publish rules, evidence, and correction ledgers |
| Cost dashboards lacking SLO context | Cost cuts degrade service quality | Pair with latency, availability, security, and unit economics |
| Ignoring currency and period mismatches | Totals fail to reconcile | Lock scope, cost basis, billing period, and currency |

## 22. Hands-On Lab: Building a Showback and Chargeback Report

**Scenario:** Three teams—Orders, Catalog, and Analytics—consume Azure resources including a shared AKS cluster, shared gateway, log workspace, and security platform. You are an engineer partnering with FinOps to implement allocation.

### Step 1 — Define Scope

Document billing scope, subscriptions, cost basis, currency, period, cutoff date, data sources, and target cost centers. Separately note out-of-basis items like taxes/credits if required by policy.

**Output:** A versioned, approved methodology sheet.

### Step 2 — Normalize Direct Ownership

Using the direct cost table in Section 12.1, map applications → cost centers. Verify the 3,800 USD direct pool is classified once, with zero overlap into the AKS pool.

**Output:** A direct ledger table referencing resource/cost rows.

### Step 3 — Define Shared Pools and Drivers

Using the pools in Section 12.2, for each pool:

- Explain why the driver matches the underlying meter's behavior.
- Record driver source, measurement period, and rule version.
- Verify non-negative weights summing to 100% per row.
- Define missing-data fallbacks and approval authority.

**Output:** A clear rules and drivers table.

### Step 4 — Compute Allocations

Calculate each pool:

- AKS: 900 / 540 / 360 USD.
- Gateway: 300 / 210 / 90 USD.
- Observability: 180 / 100 / 120 USD.
- Security: 100 / 60 / 40 USD.

Add direct costs and keep 200 USD unallocated separate.

**Expected result:** Orders **3,230 USD**, Catalog **2,110 USD**, Analytics **1,460 USD**, Unallocated **200 USD**, total **7,000 USD**.

### Step 5 — Simulate a Dispute

Suppose 120 USD of direct cost was misassigned to Catalog, while evidence proves it belongs to Orders. Propose the mapping correction and recalculate:

- Orders increases from **3,230** to **3,350 USD**.
- Catalog decreases from **2,110** to **1,990 USD**.
- Analytics and Unallocated stay unchanged.
- Grand total remains **7,000 USD**.

This changes **direct cost ownership** without altering the underlying invoice. If the period is closed, issue a versioned adjustment rather than silently editing past tables.

### Step 6 — Prepare Chargeback

Build an internal accountability transfer schedule showing cost center, period, currency, amount, source snapshot, rule version, dispute status, and approver. Explain the offsetting journal entry to avoid double-recording corporate spend.

**Pass criteria:** Ability to trace any chargeback figure back to source lines/drivers; zero reconciliation variance; explicit isolation of the 200 USD unallocated bucket.

## 23. Self-Check Questions

**Q1.** How do showback and chargeback differ in outcome?  
**Answer:** Showback informs teams of their costs; chargeback uses approved numbers to record budget accountability or internal accounting entries.

**Q2.** Should shared AKS node pool costs be assigned entirely to the cluster's resource group owner?  
**Answer:** Not automatically. Account for consuming workloads, idle capacity, and an appropriate allocation rule.

**Q3.** Why shouldn't request count serve as the single driver for every pool?  
**Answer:** Cost drivers vary: log ingestion scales with GiB, egress with bytes, compute with capacity, and databases with processing demand. Request count may correlate poorly.

**Q4.** In the worked example, how much shared cost does Orders bear?  
**Answer:** 900 + 300 + 180 + 100 = **1,480 USD**.

**Q5.** Showback totals 7,000 USD, yet only 6,800 USD maps to the three teams. Is that an error?  
**Answer:** No; 200 USD is transparently held in unallocated. All teams plus unallocated still equal 7,000 USD.

**Q6.** Can actual cost and amortized cost be summed for chargeback?  
**Answer:** No. They represent two views of the same spend, especially for commitments, and summing them risks double counting.

**Q7.** Why must ownership mappings retain effective dates?  
**Answer:** Because owners change over time; applying current owners retroactively can corrupt previously closed historical reports.

**Q8.** Does enabling Cost Management cost allocation rules make Microsoft issue separate invoices per namespace?  
**Answer:** No. Built-in allocation rules support analytical reporting within supported scopes; financial chargeback requires separate internal processes.

**Q9.** How should a 100 USD pool split evenly across three teams be rounded?  
**Answer:** Use a deterministic remainder rule, such as 33.34 + 33.33 + 33.33 = 100 USD.

**Q10.** If telemetry is sampled and incomplete, should the pool automatically be split across teams using guesses?  
**Answer:** Only under an approved fallback policy with confidence labels; otherwise hold unallocated pending investigation.

**Q11.** Why can an upfront reservation purchase make actual cost and amortized cost diverge?  
**Answer:** Actual cost may record the purchase at buy time, while amortized cost distributes commitment value over time/usage for economic analysis.

**Q12.** Should chargeback ever increase the organization's total expense?  
**Answer:** No. Chargeback reallocates internal accountability; offsetting entries and reconciliation must prevent doubling original expenses.

## 24. Enterprise Implementation Checklist

- [ ] Clearly define showback vs. chargeback, objectives, and approvers.
- [ ] Maintain a catalog of applications, owners, cost centers, shared services, and effective dates.
- [ ] Lock cost basis, currency, billing scope, and invoice/non-usage handling rules.
- [ ] Pull Azure Cost Details/Exports from trusted sources, preserving snapshots and schema mappings.
- [ ] Enforce tag standards, ownership mappings, and missing-tag triage workflows.
- [ ] Classify every source charge once into direct/shared/unallocated or policy-defined categories.
- [ ] Assign each shared pool a fitting driver, metric source, owner, rule version, and fallback policy.
- [ ] Define rules for idle AKS capacity, shared databases, networking, logs, and commitments.
- [ ] Avoid double-counting purchases with amortized usage or forcing splits without evidence.
- [ ] Validate shared allocation totals, deterministic rounding, reconciliation, and allocation coverage.
- [ ] Display direct/shared/unallocated, drivers, trends, and unit economics on dashboards.
- [ ] Grant cost-center owners read visibility and a clear dispute workflow.
- [ ] Require Finance approval, internal documentation, and offsetting entries for chargeback.
- [ ] Maintain period-close schedules, immutable snapshots, correction ledgers, and audit trails.
- [ ] Tie cost reporting to application SLOs, security, and reliability requirements.

Showback creates **visibility into where costs originate**, while chargeback turns that visibility into **governed financial accountability**. On Microsoft Azure, both rest on clean cost data, clear ownership, consumption-aligned drivers, total-conservation checks, and a traceable approval process. Combining these elements lets teams optimize infrastructure fairly and collaboratively while keeping invoices and financial reporting accurate.
