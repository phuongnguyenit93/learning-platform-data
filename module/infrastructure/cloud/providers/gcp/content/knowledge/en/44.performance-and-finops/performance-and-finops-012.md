# Unit Economics, Showback, and Chargeback on Billing Data

A company operates multiple products on Google Cloud: an ordering API on Cloud Run, analytics on BigQuery, databases on Cloud SQL, and shared GKE clusters. The Cloud Billing invoice tells the company how much it owes, yet fails to answer three vital management questions:

1. How much cloud cost goes into one successful transaction, one thousand API requests, or one active customer?
2. How much does each team, product, and cost center genuinely consume, including shared infrastructure and discounts?
3. Should those amounts simply be **reported transparently**, or **allocated as internal financial charges** to each department?

**Unit economics** measures cost per unit of business value. **Showback** delivers cost reports to consuming teams without transferring budgets between units. **Chargeback** allocates or posts real costs into internal budgets, management ledgers, or financial systems under approved rules. All three require normalized cloud billing data, resource ownership metadata, business volume metrics, and a reconciliation workflow.

In the **CLOUD_PROVIDERS_GCP** module, Cloud Billing export to BigQuery connects project/IAM governance, resource labels, GKE, Cloud Run, BigQuery, Cloud Monitoring, and FinOps. This lesson focuses on designing a trustworthy cost model, writing reusable SQL queries, handling unallocated spend, and using unit cost to drive decisions rather than blindly slashing invoices.

After this lesson, you will be able to:

- Distinguish unit economics, cost allocation, showback, and chargeback.
- Enable and choose among standard, detailed, pricing, and FOCUS Cloud Billing exports.
- Understand `cost`, `credits`, `cost_at_list`, `cost_type`, `invoice.month`, and usage timestamps.
- Use projects, labels, tags, resources, and ownership mappings to allocate costs.
- Build normalized BigQuery views, reconcile invoices, and avoid duplicating cost rows when using `UNNEST`.
- Allocate shared costs using transparent drivers while preserving total cost parity.
- Calculate cost per request, transaction, customer, or data unit with the right denominator.
- Build showback dashboards and controlled chargeback workflows.
- Manage CUDs, promotions, taxes, adjustments, late-arriving data, access control, and data quality.

## 1. Three Concepts and Their Purposes

### Unit Economics

Unit economics answers: **"How much does it cost to produce one unit of business outcome?"**

Examples:

- Cloud cost per 1,000 successful API requests.
- Infrastructure cost per completed order.
- BigQuery cost per active report consumed.
- Storage and processing cost per GiB of customer data.
- Inference cost per accepted AI response.

A basic formula:

\[
Unit\ Cost = \frac{Attributed\ Cloud\ Cost}{Completed\ Business\ Units}
\]

For APIs, you can use `Cost per 1,000 successful requests = Cost / Successful requests * 1,000`. The denominator must be a clearly defined business-value unit—never default to CPU-seconds or load balancer HTTP requests if the business cares about successful transactions.

### Showback

Showback displays who consumed resources and their estimated or recorded spend, with no mandatory internal accounting entries. The goal is creating accountability, visibility, and optimization incentives.

For example, a monthly dashboard reports: the Payments team consumed 12,000 currency units in production—7,000 in direct costs and 5,000 in shared infrastructure allocated via a published driver.

### Chargeback

Chargeback uses the same data and allocation rules, yet also posts charges to cost centers, budgets, intercompany accounts, or managerial ledgers. Because it carries real financial impact, chargeback requires:

- Approved calculation rules and effective dates.
- Clear owners for every line and explicit handling of `unallocated`.
- Total cost reconciliation against source data.
- Period-close, dispute, adjustment, and audit processes.
- Clear distinction between internal reports and actual vendor invoices.

Chargeback **does not mean Google Cloud issues separate invoices to each team**. It is an internal enterprise accounting or cost-allocation mechanism.

| Attribute | Unit Economics | Showback | Chargeback |
|---|---|---|---|
| Core question | How much does one unit cost? | Which team is consuming how much? | Which team bears how much cost? |
| Inputs | Allocated cost + business volume | Cloud spend + ownership | Cost ledger + allocation policy + approvals |
| Output | Efficiency KPIs | Dashboards or reports | Internal journal entries / budget allocations |
| Budget impact | Indirect | Primarily visibility | Direct |
| Control rigor required | Clear metric definitions | Verified allocations | Reconciliation, period lock, and audit |

## 2. FinOps Data Architecture on Google Cloud

A cost reporting system should separate raw billing data from internal allocation rules and business KPIs. Never alter raw export data to "make budgets match."

~~~mermaid
flowchart LR
    A[Cloud Billing account] --> B[BigQuery billing export]
    B --> C[Canonical billing view]
    D[Project / labels / tags / resource inventory] --> E[Ownership mapping]
    C --> F[Allocation engine]
    E --> F
    G[Business metrics: requests / orders / users] --> H[Unit economics mart]
    F --> H
    F --> I[Showback dashboard]
    F --> J[Approved chargeback ledger]
    H --> K[Product / Finance / Engineering]
    I --> K
    J --> L[Finance / ERP / GL]
    M[Controls: reconciliation / quality / audit] --> F
    M --> J
~~~

You can organize data layers as:

1. **Raw export:** tables written by Cloud Billing into BigQuery; read-only and never mutated.
2. **Canonical layer:** views with a stable schema calculating gross/net and separating invoice vs. usage months.
3. **Ownership layer:** project, tag, label, team, product, and cost center mappings with effective dates.
4. **Allocation ledger:** every item assigned directly or split by rule; total sum strictly conserved.
5. **Business metrics:** orders, successful requests, users, or jobs from operational systems.
6. **Unit economics + reporting:** marts and dashboards by product/team/period.
7. **Chargeback journal:** frozen, audited, Finance-approved period snapshot.

Layering lets you refine allocation rules without corrupting original Cloud Billing data. When Finance asks "why did team A jump 12%?", you can trace from the dashboard back through rules, line items, and invoices.

## 3. Choosing and Configuring Cloud Billing Exports

Cloud Billing supports exporting data to BigQuery in several formats. Export setup happens on the Billing account in Google Cloud Console, not from user-written BigQuery tables.

| Export Type | Typical Table | Used For |
|---|---|---|
| Standard usage cost | `gcp_billing_export_v1_<ACCOUNT_ID>` | Cost breakdown by project, SKU, service, region, labels, tags |
| Detailed usage cost | `gcp_billing_export_resource_v1_<ACCOUNT_ID>` | Resource-level attribution where services emit resource details |
| Pricing data | `cloud_pricing_export` | Reference SKU prices and pricing models, variance analysis |
| FOCUS usage cost | Dedicated Google-provided dataset/table, subject to launch-stage limits | Normalization per FinOps Open Cost and Usage Specification |
| CUD metadata | Supplemental commitment export, depending on availability | Commitment analysis and CUD benefit allocation |

**Never `UNION ALL` standard and detailed exports from the same billing account** to compute totals, because detailed export already contains all standard fields. Doing so doubles every cost. Pick one primary source—typically detailed export when resource attribution is needed.

### Enabling Export via Console

1. Select the Billing account paying for the target projects.
2. Create or pick a dedicated FinOps data project with an appropriate BigQuery dataset.
3. Navigate to **Billing → Billing export → BigQuery export**.
4. Enable standard or detailed usage export as needed; optionally enable pricing export separately.
5. Verify the billing account export service account has write access to the dataset and report readers have read access.
6. Wait for data to begin exporting; inspect tables, columns, latest timestamps, and amounts.

If your organization has multiple billing accounts, ingest each account properly and ensure no line item is double-counted. Never assume all projects sit under a single billing account.

### Latency and Historical Scope

Billing export is not a real-time event stream. When newly enabled, initial rows can take hours to appear, and retroactive backfill can take days depending on configuration and location. Backfill depth depends on export type, dataset location, and enablement date; **never assume full history prior to enablement is automatically available**.

Google may evolve export table schemas over time. To keep dashboards from breaking when new columns arrive, build canonical views with controlled column lists, schema tests, and migration plans.

## 4. Understanding Cloud Billing Fields Properly

| Field in Standard/Detailed Export | Meaning and Notes |
|---|---|
| `billing_account_id` | Billing account for the line; reconciliation key across multi-account setups |
| `invoice.month` | Invoice period in `YYYYMM`; may differ from the month usage occurred |
| `usage_start_time`, `usage_end_time` | Usage interval; used for operational analysis and unit economics |
| `project.id`, `project.name` | Project incurring the charge; some lines have no project |
| `service.id`, `sku.id` | Service/SKU identifiers; prefer IDs for mappings and descriptions for display |
| `cost` | Cost under the applicable consumption model and contract pricing, **before summing the credits array** |
| `cost_at_list` | Cost at list price under the default consumption model, populated where supported |
| `credits` | Array of credits/discounts attached to the line; `credits.amount` is typically negative |
| `cost_type` | `regular`, `tax`, `adjustment`, or `rounding_error` |
| `currency` | Billing currency; never sum USD and VND as one number |
| `usage.amount`, `usage.unit` | Usage volume in the SKU's native unit |
| `usage.amount_in_pricing_units` | Usage volume in pricing units; not business units |
| `labels` | Repeated key/value resource labels; incomplete across some services/SKUs |
| `project.labels` | Project-level labels; usable as ownership fallback |
| `tags` | Repeated Resource Manager tags; includes key, value, namespace, and inherited flag |
| `resource.name` | Resource identifier in detailed export where supported by the service |
| `export_time` | Export timestamp, useful for checking freshness and late adjustments |

### Three Cost Views That Must Never Be Mixed

- **List cost:** catalog list price before commercial terms, typically referencing `cost_at_list` where present and applicable.
- **Cost before credits:** sum of `cost` at the billing account's applicable rate, which may already include negotiated pricing.
- **Cost after credits:** sum of `cost` plus `credits.amount`; used as the baseline for net cost analysis per policy.

Never call `SUM(cost)` "list price" when the billing account has negotiated pricing. Never subtract `cost - credits` when `credits.amount` is already negative: e.g., cost 100 and credits -20 yields net **80**, not 120.

### Credits Do Not Equal Operational Efficiency

Credits can include Free Tier, sustained use, committed use, spend-based discounts, promotions, or other credit types. If a team receives a one-time promotional credit, net unit cost drops even though engineering efficiency did not change. Report **gross, discounts, promotions, and net** separately when evaluating unit economics trends.

Commitment fees, commitment credits, and CUD sharing policies may appear on different projects/SKUs than the consuming workloads. Chargeback must decide explicitly whether to allocate those fees and credits to benefiting workloads, to a commitment budget owner, or to a central FinOps pool.

## 5. Two Types of Months: Usage Month and Invoice Month

**Usage month** is based on when usage occurred in the reporting timezone. **Invoice month** is based on `invoice.month` on the Cloud Billing row.

Suppose a request runs on October 31, yet its charge posts to the November invoice. When measuring October cost per request, that spend belongs in October usage; when reconciling the vendor bill, it belongs in the November invoice. Looking at a single month without distinguishing them makes two individually accurate reports appear "out of sync."

| Purpose | Time Axis | Why |
|---|---|---|
| Product unit cost | Usage period, matching business KPI timezone | Aligns spend with the transactions generated |
| Actual vendor bill reporting | `invoice.month` | Reconciles to vendor billing cycles |
| Invoice-based chargeback | Invoice month and accounting cutoff policy | Matches internal financial close |
| Daily optimization | `usage_start_time` | Detects workload shifts near real time |
| Correction analysis | Both usage and invoice months | Spots late-arriving charges or retroactive adjustments |

For usage-based analytics, define the timezone explicitly; for financial monthly closes, use Finance's period definitions. Never treat `invoice.month` as "the cost of requests executed in that calendar month."

## 6. Normalizing Billing Data in BigQuery

Suppose you enabled **detailed usage cost export** into:

~~~text
finops-billing-prod.billing_raw.gcp_billing_export_resource_v1_XXXXXX_XXXXXX_XXXXXX
~~~

This name is an example. Substitute your organization's real project, dataset, and table. Before creating views, ensure dataset `finops_mart` exists and you hold view-creation permissions.

### Creating a Canonical View Without Multiplying Credits or Labels

~~~sql
CREATE OR REPLACE VIEW
  `finops-billing-prod.finops_mart.v_billing_canonical` AS
SELECT
  billing_account_id,
  invoice.month AS invoice_month,
  FORMAT_DATE('%Y%m', DATE(usage_start_time, 'Asia/Ho_Chi_Minh'))
    AS usage_month,
  DATE(usage_start_time, 'Asia/Ho_Chi_Minh') AS usage_date,
  usage_start_time,
  export_time,
  project.id AS project_id,
  project.name AS project_name,
  service.id AS service_id,
  service.description AS service_name,
  sku.id AS sku_id,
  sku.description AS sku_name,
  cost_type,
  currency,
  CAST(cost AS NUMERIC) AS cost_before_credits,
  COALESCE((
    SELECT SUM(CAST(c.amount AS NUMERIC))
    FROM UNNEST(credits) AS c
  ), NUMERIC '0') AS credit_amount,
  CAST(cost AS NUMERIC) + COALESCE((
    SELECT SUM(CAST(c.amount AS NUMERIC))
    FROM UNNEST(credits) AS c
  ), NUMERIC '0') AS net_cost,
  COALESCE((
    SELECT ANY_VALUE(t.value)
    FROM UNNEST(tags) AS t
    WHERE t.key = 'cost_center'
      AND t.namespace = 'YOUR_TAG_NAMESPACE'
  ), (
    SELECT ANY_VALUE(l.value)
    FROM UNNEST(labels) AS l
    WHERE l.key = 'cost_center'
  ), (
    SELECT ANY_VALUE(pl.value)
    FROM UNNEST(project.labels) AS pl
    WHERE pl.key = 'cost_center'
  ), 'unallocated') AS owner_key
FROM
  `finops-billing-prod.billing_raw.gcp_billing_export_resource_v1_XXXXXX_XXXXXX_XXXXXX`;
~~~

**Explanation:**

1. `CAST(cost AS NUMERIC)` and `credits` are computed per row; `credits` uses a scalar subquery so rows are never multiplied.
2. `tags`, `labels`, and `project.labels` likewise use scalar subqueries instead of `CROSS JOIN UNNEST` across multiple arrays.
3. Owner precedence checks `cost_center` tag in the governed namespace, then resource label, project label, and finally `unallocated`. This precedence is an **illustrative internal rule**, not an automatic Google default.
4. `usage_month` uses a consistent timezone; `invoice_month` preserves the invoice field untouched.
5. The view does not allocate shared costs yet; it prepares a clean foundation for the allocation step.

`ANY_VALUE` picks one value for the key, yet if sources carry conflicting values for the same key, it offers no business-logic guarantee. Add data quality checks and clear policies for invalid metadata. Replace `YOUR_TAG_NAMESPACE` with your governed organization namespace; never match solely by tag key when multiple organizations/namespaces can collide.

For financial reconciliations demanding extreme precision, sum values in micros or apply Finance-approved rounding rules, since `cost` and `credits.amount` may be exported as floating-point values. These examples use `NUMERIC` for simplicity; verify rounding tolerances against real invoices.

### Warning When `UNNEST`ing Multiple Repeated Fields

Suppose one line has 2 resource labels, 3 tags, and 2 credits. The query:

~~~sql
SELECT *
FROM `...` AS b,
UNNEST(b.labels) AS l,
UNNEST(b.tags) AS t,
UNNEST(b.credits) AS c;
~~~

can produce 2 × 3 × 2 = **12 rows** from a single export row. Running `SUM(cost)` afterward multiplies cost 12×. This query illustrates an **anti-pattern**—never use it in reports.

It is much safer to extract a single metadata value via correlated subqueries and sum credits inside a subquery on the original row, as shown in the canonical view above. If you must analyze multiple labels, run separate reports per key or build a bridge table with allocation weights summing strictly to 1.

## 7. Invoice Reconciliation Queries

Reconcile before publishing showback or chargeback. Never allocate from a dataset whose total does not reconcile.

### Total Cost/Credits by Invoice Month

~~~sql
SELECT
  billing_account_id,
  invoice_month,
  currency,
  cost_type,
  ROUND(SUM(cost_before_credits), 2) AS cost_before_credits,
  ROUND(SUM(credit_amount), 2) AS credits,
  ROUND(SUM(net_cost), 2) AS net_cost
FROM `finops-billing-prod.finops_mart.v_billing_canonical`
WHERE invoice_month = '202610'
GROUP BY 1, 2, 3, 4
ORDER BY billing_account_id, invoice_month, currency, cost_type;
~~~

This query uses **invoice month**, keeping `regular`, `tax`, `adjustment`, and `rounding_error` so no reconciliation lines vanish. Totals may need standard rounding and cross-checking against the actual Cloud Billing account invoice.

### Breakdown by Usage Month

~~~sql
SELECT
  usage_month,
  currency,
  service_name,
  ROUND(SUM(net_cost), 2) AS net_cost
FROM `finops-billing-prod.finops_mart.v_billing_canonical`
WHERE usage_month BETWEEN '202609' AND '202610'
  AND cost_type = 'regular'
GROUP BY 1, 2, 3
ORDER BY usage_month, net_cost DESC;
~~~

This query reflects operational usage timing rather than monthly invoices. When Google Cloud posts corrections for prior usage, historical numbers can shift when re-running the view. For stable chargeback, freeze immutable snapshots at period close and track adjustments separately.

### Checking Lines Without a Project

Not every charge carries a `project.id`. Support fees, adjustments, or credits can post outside any project. Silently dropping `project.id IS NULL` rows causes allocations to fall short of the invoice. Route them to `central`, `shared`, or `unallocated` and handle per policy.

## 8. Ownership Models: Projects, Labels, Tags, and Mapping Tables

### Project-per-Team or Project-per-Product

Clean project boundaries simplify accountability and minimize unallocated spend. This is usually a strong foundation:

- `payments-prod` belongs to Product Payments.
- `catalog-prod` belongs to Product Catalog.
- `shared-network-prod` is shared platform infrastructure.
- `sandbox-research` belongs to the research group with a dedicated budget.

Still, a single project hosting multiple workloads requires labels/tags or drivers to split costs. Project ID does not always map 1:1 to cost center.

### Labels

Suggested standard labels on supported resources:

| Key | Example | Meaning |
|---|---|---|
| `cost_center` | `cc-210` | Financial cost-bearing unit |
| `product` | `checkout` | Product |
| `environment` | `prod` | Environment |
| `owner_team` | `payments` | Operating team |
| `workload` | `checkout-api` | Application component |

Labels are never retroactive prior to attachment, nor do they populate on every SKU or service type. Do not measure label coverage solely by count of labeled resources; measure the **percentage of spend** with valid ownership.

### Tags

Google Cloud Resource Manager tags provide IAM governance and hierarchy inheritance, making them well-suited for organization-governed cost centers. In billing exports, `tags` carry key, value, namespace, and inherited metadata where supported. Tags have propagation latency into exports and vary in coverage by resource type; they are not an automatic silver bullet for every charge.

### Effective-Dated Mapping Tables

When a project changes owners mid-month, never rewrite ownership on closed historical periods. Use an effective-dated mapping table:

| project_id | owner_key | product | valid_from | valid_to |
|---|---|---|---|---|
| `payments-prod` | `cc-210` | `checkout` | 2026-01-01 | 2026-11-01 |
| `payments-prod` | `cc-220` | `checkout` | 2026-11-01 | null |
| `shared-platform-prod` | `shared` | `platform` | 2026-01-01 | null |

Use half-open intervals `valid_from <= usage_date < valid_to` to avoid overlapping boundary dates. Enforce uniqueness/conflict checks, owner sign-off, and version/rule IDs on the mapping table.

### Recommended Attribution Precedence

1. Evidence-backed direct resource/tenant rules (resource ID, workload label).
2. Governance-approved cost-center tags.
3. Reliable resource/project labels.
4. Effective-dated project ownership mappings.
5. Shared pools by service or SKU.
6. `unallocated` with an assigned investigator; **never silently dropped from reports**.

Exact precedence is set by the organization and must be documented. When a project label and a tag conflict, alert and investigate rather than picking randomly for chargeback.

## 9. GKE, Shared Resources, and Allocation Limits

On GKE, a single cluster often serves multiple namespaces and teams. Detailed billing export does not split per-pod costs across every SKU by default. Enable **GKE cost allocation** to populate labels such as:

- `goog-k8s-cluster-name` for cluster name.
- `k8s-namespace` for namespace.
- `k8s-label/<key>` for supported Kubernetes labels.

After enabling GKE cost allocation, data takes time to appear; labeling pods/namespaces does not retroactively split historical charges. Certain resource types and operating models also carry documented limitations.

Avoid treating namespace as the sole cost center if one namespace serves multiple products. You can use `team` or `product` labels, requested resource ratios, or actual workload consumption metrics, provided the driver and impact are agreed upon before chargeback.

### Shared Costs Beyond GKE

Common shared items requiring allocation:

- Shared VPC, NAT, load balancers, egress, and CDN.
- Shared GKE control planes/node pools.
- Centralized logging, monitoring, and security scanning.
- Shared BigQuery reservations across multiple teams.
- Artifact Registry, CI/CD platforms, and secrets platforms.
- Support plans, license fees, or shared commitments.

If a service lacks reliable attribution telemetry, allocate using a transparent driver or retain it in a central pool. Never dump 100% of a shared resource's bill onto the team that provisioned it when other teams benefit equally.

## 10. Direct, Shared, and Unallocated Allocation Methods

### Direct Allocation

Direct costs assign to a single cost center when backed by strong evidence: dedicated projects, approved tags/labels, resource-to-workload mappings, or single-team consumption telemetry.

### Shared Cost Allocation

Shared costs require a driver agreed upon by infrastructure owners, product teams, and Finance.

| Shared Cost | Feasible Driver | Conditions to Verify |
|---|---|---|
| Shared GKE cluster | Requested or actual CPU/memory by namespace | Resource limits, system overhead, idle capacity |
| Shared BigQuery reservation | Slot-ms by job/team, reservation usage | Job labels, alignment with reservation assignments |
| Shared network egress | Bytes by application or service flow | Complete egress measurement without double-counting |
| Central logging | Ingested GiB or volume by service | Log routing and aggregated log metrics |
| Central security | Resource counts, risk tier, or % of direct spend | Fair rationale and stakeholder sign-off |
| Support plan | Spend share or fixed budget agreement | Treatment of non-resource-linked fees |

No driver is "mathematically perfect." What matters is being **simple, auditable, stable, and aligned with what teams can actually control**.

### Weighted Allocation Formula

For shared cost pool `S` and team `i`'s driver weight `w_i`:

\[
AllocatedSharedCost_i = S \times \frac{w_i}{\sum_{j=1}^{n}w_j}
\]

When the sum of drivers equals 0, never divide by zero or drop the chargeback pool. Route to a policy-defined fallback (such as `unallocated-shared`) and open an investigation.

### Two-Product Example

In one month, excluding taxes/adjustments to focus on operations:

| Item | Payments | Catalog |
|---|---:|---:|
| Direct net cost | 1,800 USD | 1,200 USD |
| Share of direct cost | 60% | 40% |
| Shared pool to allocate | Total pool: 600 USD | Split 60% / 40% |
| Allocated shared cost | 360 USD | 240 USD |
| **Total allocated** | **2,160 USD** | **1,440 USD** |

Total after allocation equals `2,160 + 1,440 = 3,600 USD`, matching `1,800 + 1,200 + 600`. Never keep 600 USD in a shared center while also adding 600 USD of allocated shared cost to teams in the same rollup report—that double-counts spend.

This example is illustrative, excluding CUD allocations, taxes, and adjustments. Real chargeback may define separate policies per cost category.

## 11. SQL Pattern for Allocating a Shared Pool

Suppose the canonical view exposes `owner_key`; `payments` and `catalog` hold direct costs, while shared items carry `shared-platform`. The example below allocates the shared pool proportionally by **positive direct net regular cost**.

~~~sql
WITH monthly AS (
  SELECT
    owner_key,
    SUM(net_cost) AS net_regular_cost
  FROM `finops-billing-prod.finops_mart.v_billing_canonical`
  WHERE invoice_month = '202610'
    AND currency = 'USD'
    AND cost_type = 'regular'
  GROUP BY 1
),
direct AS (
  SELECT
    owner_key,
    net_regular_cost AS direct_cost,
    GREATEST(net_regular_cost, NUMERIC '0') AS driver
  FROM monthly
  WHERE owner_key IN ('payments', 'catalog')
),
weights AS (
  SELECT
    owner_key,
    direct_cost,
    SAFE_DIVIDE(driver, SUM(driver) OVER ()) AS allocation_weight
  FROM direct
),
shared AS (
  SELECT COALESCE(SUM(net_regular_cost), NUMERIC '0') AS shared_cost
  FROM monthly
  WHERE owner_key = 'shared-platform'
)
SELECT
  w.owner_key,
  ROUND(w.direct_cost, 2) AS direct_cost,
  ROUND(s.shared_cost * w.allocation_weight, 2) AS allocated_shared_cost,
  ROUND(w.direct_cost + s.shared_cost * w.allocation_weight, 2)
    AS total_allocated_cost
FROM weights AS w
CROSS JOIN shared AS s
ORDER BY w.owner_key;
~~~

This is a didactic pattern. In production you must:

- Maintain an authoritative owner list rather than hardcoding two owners across an enterprise.
- Include `unallocated` and other owners in reconciliation tables so zero spend vanishes.
- Pick consumption-based drivers wherever measurable metrics exist.
- Separate commitment fees, taxes, and adjustments per policy.
- Handle zero driver totals explicitly (`SAFE_DIVIDE` returns NULL and must not drop unallocated pools).
- Allocate fractional rounding cents deterministically so rounded totals still match the pool exactly.
- Inspect negative costs and credits before applying proportional weights.

A production **allocation ledger** should include `source_line_id/rule_id/period/owner/weight/allocated_amount/allocation_version`, enforcing that weights for every eligible line sum to 1. If billing export lacks a unique natural line key, build a surrogate key from stable fields plus ingestion identifiers using tested deduplication logic—never assume a hash of `project+sku+date` is unique.

## 12. Computing Unit Economics with Business Metrics

Billing exports only supply cloud usage units such as GiB-months, vCPU-hours, SKU requests, or query bytes. **Business units** normally live in other systems:

- Successfully paid orders in the application database.
- Successful API requests in load balancer/Cloud Monitoring metrics.
- Active customers per product definitions.
- Accepted AI processing sessions.
- Data pipelines completed on schedule.

### Criteria for a Sound Denominator

1. Consistent business definition that does not silently shift.
2. No double-counting of retries or multi-step stages of one order.
3. Same timezone and measurement window as the cloud cost numerator.
4. Segmented along the same product/tenant/region boundaries as costs.
5. Auditable and traceable back to source events.

### Cost per 1,000 Requests Example

Using the numbers above:

- Payments: 2,160 USD, 1,200,000 successful requests ⇒ `2,160 / 1,200,000 × 1,000 = 1.80 USD` per 1,000 requests.
- Catalog: 1,440 USD, 600,000 successful requests ⇒ `1,440 / 600,000 × 1,000 = 2.40 USD` per 1,000 requests.

Payments has higher total cloud spend yet **lower unit cost**. Looking solely at total invoices would lead to wrong conclusions. Still, examine workload complexity, request types, and SLOs before declaring Payments more efficient than Catalog.

### Joining the Allocation Mart with Business Metrics

Suppose two normalized internal tables exist:

- `finops_mart.monthly_allocated_cost`: `usage_month`, `product`, `currency`, `allocated_cost`.
- `product_metrics.monthly_success`: `usage_month`, `product`, `successful_requests`.

~~~sql
WITH c AS (
  SELECT
    usage_month,
    product,
    currency,
    SUM(allocated_cost) AS cloud_cost
  FROM `finops-billing-prod.finops_mart.monthly_allocated_cost`
  WHERE usage_month = '202610'
  GROUP BY 1, 2, 3
),
m AS (
  SELECT
    usage_month,
    product,
    SUM(successful_requests) AS requests
  FROM `finops-billing-prod.product_metrics.monthly_success`
  WHERE usage_month = '202610'
  GROUP BY 1, 2
)
SELECT
  c.usage_month,
  c.product,
  c.currency,
  c.cloud_cost,
  m.requests,
  ROUND(SAFE_DIVIDE(c.cloud_cost * 1000, m.requests), 4)
    AS cost_per_1000_successful_requests
FROM c
LEFT JOIN m
  ON c.usage_month = m.usage_month
 AND c.product = m.product;
~~~

These mart tables must be built by the enterprise according to the schema shown; they **do not appear automatically** just from enabling Billing export.

Crucial rule: **aggregate costs and business metrics to the exact same grain before joining**. Joining raw billing rows directly to raw request events multiplies cost rows and produces nonsense totals. When `requests` equals 0, `SAFE_DIVIDE` returns NULL—display "no valid denominator" rather than forcing `0 USD/unit`.

### Average vs. Marginal Unit Cost

Average unit cost includes fixed and shared costs. **Marginal cost** is the incremental cost of serving one additional unit of workload. These two diverge whenever autoscaling steps, CUDs, idle headroom, or fixed license fees exist.

For capacity decisions, examine both fixed/variable cost structure and throughput. A promotional discount lowers net unit cost without proving higher capacity efficiency.

## 13. Distinguishing Showback and Chargeback on Dashboards

### Showback Dashboard

A dashboard for product/engineering should display:

- Total cost before credits and after credits per period.
- Cost by project, product, owner/team, environment, service, and SKU.
- Direct, shared, centrally retained, and unallocated buckets.
- Percentage of cost with valid attribution.
- Period-over-period variance and drivers: workload growth, unit prices, discounts, architecture changes.
- Unit cost alongside its business denominator.
- Action items: unlabeled resources, idle spend, anomalies, forecasts.

Showback should expose **allocation formulas and rules**. If a team cannot understand why it was allocated 500 USD of shared NAT spend, it will struggle to optimize it.

### Chargeback Statement

Chargeback additionally requires:

| Field | Purpose |
|---|---|
| Accounting period | Internal accounting close period |
| Billing account / currency | Reconciliation inputs |
| Cost center and owner | Cost-bearing entity |
| Allocation policy/version | Active rule version |
| Direct cost | Directly attributed spend |
| Shared cost allocated | Allocated share of shared pools |
| Discounts/credits allocated | Credits/discounts applied per policy |
| Tax/adjustment policy | Handling of non-regular usage lines |
| Total chargeback | Final amount to post |
| Approval and status | Draft, reviewed, approved, posted, adjusted |
| Trace ID | Link to source rows, allocation ledger, and pipeline run |

Never implement chargeback by giving every team full access to raw billing exports that expose contract discounts or other projects' data. Use authorized views, policy tags, row-level security, or owner-scoped marts; Finance retains full access.

## 14. Period-Close and Reconciliation Process

Never post accounting journals from a dashboard that shifts hourly. A recommended workflow:

1. **Ingest:** verify export completeness up to cutoff time.
2. **Normalize:** apply canonical schema, timezone, and credit policies.
3. **Assign:** map direct ownership; keep the `unallocated` bucket explicit.
4. **Allocate:** split shared pools using active drivers.
5. **Reconcile:** verify pre- and post-allocation totals match source data and invoices.
6. **Quality gate:** check unallocated rate, label conflicts, null currencies, and missing metrics.
7. **Review:** circulate draft showback to owners and Finance.
8. **Dispute window:** allow owners to challenge allocations with evidence.
9. **Approve and freeze:** lock versioned calculations and close the period.
10. **Post chargeback:** export journal/ERP feeds and archive trace IDs.
11. **Adjust later:** late adjustments/corrections post in subsequent adjustment cycles or approved restatements.

### Mandatory Reconciliation Check

\[
\sum Direct + \sum Shared + \sum Unallocated + \sum Central
= \sum Source\ Net\ Costs
\]

On the left-hand side, `Shared` means **either allocated shares or retained central shared costs**, never both the unallocated shared pool and the allocated team shares simultaneously. In multi-tier allocations, reconcile at every stage.

### Precision and Discrepancies

Cloud Billing rows can include rounding errors, taxes, adjustments, or late-monetized usage. Agree upfront on:

- Authoritative source for invoice totals.
- Currency and FX conversion rules if multi-currency.
- Rounding rules and penny-allocation handling.
- Acceptable variance tolerance and escalation thresholds.
- Policies against silently restating closed periods.

Never blend `tax`, `rounding_error`, and `adjustment` into `regular` usage without notes, as doing so distorts engineering unit costs.

## 15. Data Quality Controls and Measuring Attribution Coverage

A production FinOps pipeline needs independent quality metrics:

| Check | Example SLI |
|---|---|
| Freshness | Hours since latest `export_time` at check time |
| Attribution coverage | % of net regular cost mapped to a valid owner |
| Unallocated spend | Dollars remaining in `unallocated` and trend |
| Mapping conflicts | Count of conflicting tag/label/project mappings |
| Reconciliation | Net cost delta before vs. after allocation |
| Denominator quality | % of product-months with valid business units |
| Audit completeness | % of chargeback lines carrying rule ID and source trace |
| Timeliness | % of periods closed before accounting deadline |

Example measuring unowned spend:

~~~sql
SELECT
  invoice_month,
  currency,
  ROUND(SUM(net_cost), 2) AS total_regular_net_cost,
  ROUND(SUM(IF(owner_key = 'unallocated', net_cost, 0)), 2)
    AS unallocated_net_cost,
  ROUND(
    100 * SAFE_DIVIDE(
      SUM(IF(owner_key = 'unallocated', ABS(net_cost), 0)),
      SUM(ABS(net_cost))
    ), 2
  ) AS unallocated_share_of_absolute_cost_pct
FROM `finops-billing-prod.finops_mart.v_billing_canonical`
WHERE cost_type = 'regular'
  AND invoice_month = '202610'
GROUP BY 1, 2;
~~~

The percentage metric uses **absolute cost** to prevent negative credits from pushing the denominator near zero or flipping signs. This is an operational coverage metric, not a budget utilization ratio for financial statements.

Never chase 100% coverage by dumping unexplained spend onto an arbitrary team. It is far healthier to keep `unallocated` transparent and shrink it via better ownership metadata.

## 16. CUDs, Free Tier, Promotions, and Shared Purchasing Benefits

Commitment discounts introduce major cost swings and demand explicit allocation rules:

- **CUD fees:** should commitment fees stay in central Finance, charge to the contract owner, or split across benefiting workloads?
- **CUD credits:** do received credits align with consuming workloads or post elsewhere?
- **Unused commitments:** who pays for unutilized commitment capacity? The purchaser or a shared pool?
- **Free Tier/promotions:** should free benefits pass straight to products or be isolated from operational efficiency metrics?
- **Negotiated pricing:** should list prices be visible to teams, and is contract pricing access-restricted?

Track at least two KPIs:

1. **Operational unit cost:** isolates one-time price/credit noise to measure pure engineering efficiency.
2. **Financial net unit cost:** post-credit cost per allocation policy aligned with budgets.

CUD metadata exports and Cloud Billing pricing exports help analyze discount mechanics, yet do not automatically decide internal beneficiaries. The allocation model still requires explicit FinOps policy.

## 17. Security, Access Control, and Operating Billing Data

Billing exports can reveal total spend, negotiated rates, project topologies, adopted services, and commitment strategies. This is sensitive financial data.

### IAM and Access

- Restrict raw billing dataset read access to FinOps/Finance and dedicated service accounts.
- Expose only authorized views or scoped marts to product teams.
- Apply BigQuery row-level security, column-level controls, and policy tags where needed.
- Separate permissions to edit allocation rules from permissions to approve/post chargeback.
- Secure CI/CD workflows, BigQuery scheduled queries, and Dataform/dbt jobs.
- Audit log all changes to policies, mappings, SQL, and export configurations.

### Cost of Analyzing Billing Data

BigQuery queries scanning months of raw billing data can grow expensive, especially across billions of rows. Mitigate by:

- Bounding time predicates in every query.
- Partitioning and clustering internal mart tables.
- Materializing daily/monthly summary tables.
- Running dry runs and setting `maximum_bytes_billed` on large queries.
- Never joining raw billing exports directly against raw clickstreams continuously.
- Saving immutable snapshots for closed chargeback periods.

If the export table is partitioned, inspect its actual partition column and filter on it to cut bytes scanned. Never modify schemas or partitioning on Google-managed raw export tables.

### Operational Monitoring

Cloud Monitoring and pipeline logs should alert on delayed exports, canonical view schema failures, abnormal spend jumps, rising unallocated percentages, or failed reconciliations. A FinOps dashboard still rendering stale or wrong numbers is a serious operational hazard.

## 18. End-to-End Pilot Workflow

Suppose an enterprise runs three groups: Payments, Catalog, and Shared Platform. It wants monthly showback reports first, transitioning to chargeback after a two-month pilot.

### Phase A: Data Foundation

1. Enable detailed usage cost export on the billing account.
2. Build the canonical view with explicit net cost and currency logic.
3. Define invoice month vs. usage month and separate them in dashboards.
4. Build effective-dated project, tag, and label mappings for the three cost centers.
5. Audit non-regular rows, credits, and unowned projects.

### Phase B: Showback Pilot

6. Compute direct costs while keeping the shared pool separate.
7. Select documented drivers for shared networking, logging, and GKE clusters.
8. Reconcile direct + allocated + unallocated/central back to source totals.
9. Publish dashboards by team, product, service, and environment.
10. Add unit costs from business-defined request/order counts.
11. Review reports with product owners and fix missing ownership metadata.

### Phase C: Controlled Chargeback

12. Obtain Finance approval on policies: taxes, CUDs, promotions, shared pools, rounding.
13. Establish close calendars, dispute windows, approvals, and versioning.
14. Produce immutable chargeback statements per closed period.
15. Export journal feeds to financial systems if formal chargeback is enforced.
16. Book late invoice corrections in subsequent adjustment cycles instead of silently editing locked periods.

### Phase D: Continuous Improvement

17. Diagnose rising unit costs: traffic mix, architecture, overprovisioning, SKU rates, or commitments.
18. Propose optimizations with forecasted savings and SLO impact checks.
19. Track before/after changes using consistent denominators.
20. Review allocation driver fairness quarterly.

## 19. Troubleshooting

| Symptom | Possible Cause | Remedy |
|---|---|---|
| Dashboard total is double the invoice | `UNION`ed standard and detailed exports or `UNNEST`ed multiple arrays | Query one primary export; use correlated subqueries for repeated fields |
| Sum of `cost` differs from bill paid | Omitted credits, taxes, adjustments, or rounding | Reconcile by `invoice.month`, `currency`, and `cost_type` |
| Cloud unit price dropped suddenly | Promotion, CUD credit, or negotiated rate change | Separate before-credits, promotions, discounts, and net |
| Unit cost rose despite flat requests | Shared allocation shifted, traffic mix changed, or fixed costs rose | Check rule versions, denominator, and cost decomposition |
| Project has no owner | Missing tag/label or newly created project | Use effective-dated mapping fallback; review unallocated |
| New labels missing on past months | Metadata is not retroactive | Never arbitrarily re-attribute history; use effective-dated rules |
| GKE namespace costs missing | GKE cost allocation not enabled or propagation lag | Enable GKE cost allocation; check SKU limits and latency |
| Usage month spend differs from invoice | Late-monetized usage, corrections, or timezone mismatch | Separate `usage_month` and `invoice_month`; close periods with adjustment rules |
| Chargeback differs from source by cents | Rounding per owner instead of post-allocation remainder handling | Apply deterministic remainder rules and reconcile post-`ROUND` |
| Cost per unit is 0 or NULL | Missing/zero denominator, negative credits, or bad `JOIN` | Audit business metrics, `SAFE_DIVIDE`, cohorts, and credit policies |
| One team sees another team's spend | Raw billing dataset permissions too broad | Enforce authorized views/RLS and test access controls |
| SQL breaks when Google adds fields | Queries used `SELECT *` or schema drift | Use stable canonical views and schema contract tests |

## 20. Pre-Publication Data Checklist

- [ ] Billing accounts and export types confirmed without double-counting standard/detailed.
- [ ] Export data covers full periods; freshness and backfill verified.
- [ ] Canonical view separates invoice month, usage month, and currency.
- [ ] Gross/list, before-credits, credits, and net are transparently defined.
- [ ] Zero row multiplication across repeated labels, tags, and credits.
- [ ] `regular`, `tax`, `adjustment`, and `rounding_error` clearly separated.
- [ ] Effective-dated ownership mapping exists across projects/resources/tags/labels.
- [ ] Shared costs have policies, drivers, owners, and zero-driver fallbacks.
- [ ] `unallocated`/central buckets exist with plans to shrink unowned spend.
- [ ] Post-allocation totals match pre-allocation totals per account/currency/period.
- [ ] CUDs, promotions, Free Tier, and commitment fees handled per policy.
- [ ] Business denominators are deduplicated at matching grain, timezone, and period.
- [ ] Unit cost definitions separate operational vs. financial views.
- [ ] Showback dashboards display direct/shared/allocated breakdowns with drill-downs.
- [ ] Chargeback enforces approvals, freezes, disputes, adjustments, and traceability.
- [ ] Raw billing access is restricted; marts enforce cost-center security.
- [ ] Schema drift, freshness, label coverage, and reconciliation checks are active.
- [ ] BigQuery analysis budget and data-quality alerts are configured.

## 21. Conclusion

**Unit economics** measures cloud spend against business outcomes; **showback** creates visibility into consumers and costs; **chargeback** turns allocation policies into internal financial accountability. All three only work when billing data is normalized and reconciled, ownership is trustworthy, shared costs use fair drivers, and business denominators are accurate.

On Google Cloud, detailed Cloud Billing exports and BigQuery provide a solid foundation for building a canonical cost layer, allocation marts, unit economics dashboards, and chargeback ledgers. Start with non-destructive reporting on top of raw data, keep unallocated costs visible, align rules with Finance and product owners, and only then post accounting journals. Ultimately, FinOps is not about slapping a label on every penny, but helping teams balance **value, performance, reliability, and cost**.

## References

- [Set up Cloud Billing data export to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-setup)
- [Understand Cloud Billing data tables](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables)
- [Standard usage cost export schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage)
- [Detailed usage cost export schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage)
- [Example queries for Cloud Billing data export](https://docs.cloud.google.com/billing/docs/how-to/bq-examples)
- [Get key spending insights from GKE cost allocation](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cost-allocations)
- [Google Cloud Billing reports and cost management](https://docs.cloud.google.com/billing/docs/how-to/reports)
- [BigQuery partitioned tables](https://docs.cloud.google.com/bigquery/docs/partitioned-tables)
- [BigQuery authorized views](https://docs.cloud.google.com/bigquery/docs/authorized-views)
- [FinOps Foundation: Framework](https://www.finops.org/framework/)
