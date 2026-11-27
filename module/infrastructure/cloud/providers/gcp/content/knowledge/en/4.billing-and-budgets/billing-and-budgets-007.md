# Cloud Billing Reports and Cost Table Analysis

> **Chapter:** Billing and Budgets  
> **Module:** **CLOUD_PROVIDERS_GCP** — Explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and database services. Through deployment scenarios, learners know how to select services, secure resources, automate releases, and monitor reliability alongside costs.

When running systems on Google Cloud, knowing that a VM, Cloud Run service, or GKE cluster is healthy is not enough: teams must also know **where costs are accruing, why they change, which unit owns them, and how operational metrics tie back to invoices**. The two foundational tools in the Google Cloud console are **Cloud Billing Reports** and the **Cost table**.

This lesson focuses on how to **read, filter, group, compare, explain, and reconcile costs** with these two tools. It is a core skill for setting budgets, monitoring spend, and making architectural decisions across Compute Engine, GKE, Cloud Run, storage, databases, and networking.

## Learning objectives

After this lesson, learners will be able to:

1. State the purpose and boundaries between **Billing Reports**, **Cost table**, invoices/statements, and **Cloud Billing export to BigQuery**.
2. Choose the right time basis: **Charge period (formerly Usage date)** or **Billing period (formerly Invoice month)**.
3. Use **Project, Service, SKU, Location, Label** dimensions and filters to pinpoint cost sources.
4. Distinguish **list cost, usage cost, savings/credits, taxes, adjustments, rounding**, and invoice totals.
5. Reconcile Cost table figures with an invoice/statement and explain common variances.
6. Build a verifiable workflow to investigate cost spikes, allocate costs across teams, and produce auditable FinOps reports.

## 1. The big picture: how costs flow from resources to invoices

Resources are created inside a **project**; the project links to a **Cloud Billing account** to record usage costs for billable services. One billing account can pay for multiple projects. Conversely, the **organization/folder/project** hierarchy serves resource governance and does not dictate how invoices are split.

~~~mermaid
flowchart TD
    O["Organization / Folder"] --> P1["Project: shop-dev"]
    O --> P2["Project: shop-prod"]
    O --> P3["Project: analytics"]
    P1 --> R1["Cloud Run / Storage"]
    P2 --> R2["GKE / Cloud SQL"]
    P3 --> R3["BigQuery"]
    B["Cloud Billing account"] -. "Billing link" .-> P1
    B -. "Billing link" .-> P2
    B -. "Billing link" .-> P3
    B --> REP["Billing Reports: trends and breakdown"]
    B --> COST["Cost table: invoice-period details"]
    B --> EXP["BigQuery export: custom analytics"]
    B --> DOC["Invoice / Statement"]
~~~

Key distinctions:

- **Project ID** identifies the source of resource consumption, not an invoice number.
- **Billing account** is the cost-aggregation scope; permissions to view costs on an individual project can differ from permissions to view the entire billing account.
- **Service** is a product category such as Compute Engine, Cloud Storage, or Cloud Run.
- **SKU** describes a specific billable usage type within a service—such as a compute capacity unit, network transfer, or storage class. One service can generate many SKUs.
- **Invoice/statement** is the period's billing document, which may include usage charges, discounts, credits, adjustments, taxes, and rounding according to account configuration.

Therefore, a single application can incur costs across **multiple projects, multiple services, and multiple SKUs**. For example, a Cloud Run API can accrue charges for execution, Cloud SQL access, Cloud Storage, logging, and network egress. To optimize the true root cause, you cannot rely on a single aggregate number.

## 2. Choosing the right tool before analyzing

| Question | Appropriate tool | Why |
|---|---|---|
| On which day and in which service are costs rising? | **Billing Reports** | Provides time-series charts, filters, and grouping by service/project/SKU |
| Which project is the most expensive this month? | **Billing Reports** | Compares totals, selects timeframe, and groups by project |
| What is the projected month-end cost if current trends continue? | **Billing Reports** | Provides forecasts when time basis and filters support them |
| Why was last period's billing document X dollars? | **Cost table** | Shows details by billing period, document, taxes, credits, and line items |
| Need a CSV explaining every SKU on the invoice? | **Cost table** | Offers nested or flat tables, customizable columns, and CSV export |
| Allocate by multiple labels and aggregate monthly with custom logic? | **Billing export to BigQuery** | Detailed SQL queries, joins with supplemental data, and custom dashboards |
| Want to set spend thresholds and send alerts? | **Budgets & alerts** | Tracks spend targets; does not block spending by default |

**Reports and the Cost table are not two views guaranteed to produce the exact same number.** Reports can use usage dates or billing periods; the Cost table is built specifically to inspect charge lines tied to **an invoice/statement**. Even within Reports, changing filters or savings options alters the total.

### 2.1. Required access permissions

To view all data for a Cloud Billing account, users are typically granted an appropriate role such as **Billing Account Viewer**, **Billing Account Costs Manager**, or **Billing Account Administrator** on the billing account. The underlying permission for viewing spend data is **billing.accounts.getSpendingInformation**; opening account-level Reports also depends on related billing account permissions.

In some cases, users have **project-level cost-viewing permissions** and can see data only for permitted projects. Account-level features such as full invoice reconciliation, grouping by labels, or viewing account-wide charges may then be unavailable. If data appears missing, check **permission scope** before concluding costs are zero.

Cost-viewing permissions should follow least privilege. Billing reports can reflect sensitive projects, products, and business activity; do not share CSV exports or report URLs outside authorized scopes.

## 3. Cloud Billing Reports: viewing trends and cost breakdown

### 3.1. How to open and read the screen

In the **Google Cloud console**, open **Billing**, choose an accessible billing account, and open **Reports** under cost management. If you only have project-level view permissions, select the appropriate project before opening Billing; available views and features may differ.

The Reports page contains key sections:

1. **Time range:** selects the timeframe and the time basis for recording costs.
2. **Group by:** selects the analysis dimension, such as Service, Project, SKU, date, or location.
3. **Filters:** narrows by project, service, SKU, location, labels, and savings options where supported.
4. **Chart:** visualizes cost fluctuations over time; may display forecasts when eligible.
5. **Summary table and footer:** displays grouped figures, savings, and total cost within the filtered scope.

In the standard UI, the default preset is **Services — this month**, showing daily costs for the current month grouped by Service. Therefore, the first question when opening the page is: **which month, account/project scope, and savings mode am I looking at?**

### 3.2. Understanding Charge period vs. Billing period

This is the single most important distinction when reconciling reports:

| Attribute | **Charge period** (formerly Usage date) | **Billing period** (formerly Invoice month) |
|---|---|---|
| Analytical mindset | When usage actually occurred | Which billing period's document includes the charge |
| Time selector unit | Day or date range | Invoice month / billing period |
| Primary use case | Pinpointing when costs started rising, tracking the current month | Reconciling invoices, viewing document-level taxes/adjustments |
| Forecast | May appear if range ends in the future and filters support it | No forecast in this mode |
| Taxes, invoice-level adjustments | Not shown as an invoice-mode total | Can be included in totals with full scope and proper permissions |
| Total vs. invoice | Does not necessarily match | Can match period total when unfiltered with full permissions; if multiple invoices exist in a month, Reports aggregates by month |

For example, 10 resource units are used on **October 31**, yet processing finalizes and posts to the **November** statement. A **Charge period** report may record that cost under late October usage dates, while the Cost table for the November invoice contains that charge line. This can be a **valid timing difference**, not necessarily a billing error.

Costs have processing and update latency. Freshly generated usage does not necessarily appear immediately; the most recent days should be treated as **still finalizing**, not closed books.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant M as Usage Metering System
    participant B as Cloud Billing
    participant I as Invoice/Statement
    A->>M: Uses resources on Oct 31
    M-->>B: Records charge after processing
    B->>B: Charge period report by usage date
    B-->>I: Assigned to invoice period when generated
    Note over B,I: Usage month can differ from invoice period
~~~

### 3.3. Grouping by Service, Project, SKU, and time

**Group by** controls table rows and chart stacking. Common choices include:

- **Service:** which service drives most of the cost, such as Compute Engine or Cloud Storage.
- **Project:** which environment or product is consuming resources.
- **SKU:** whether the specific increase is from compute, storage, requests, or egress.
- **Location: Region or multi-region:** inspect cost distribution by reported location; do not assume per-zone grouping is supported.
- **Date > Project / Date > Service / Date > SKU:** pinpoint when a shift began and which component moved.
- **Label key:** analyze costs by resource label values where supported by reporting, permissions, and data.
- **Project hierarchy / applications:** useful when environments use organizational hierarchy and supported features.

**How to drill down from total to root cause:**

~~~mermaid
flowchart TD
    T["Monthly total cost increases"] --> P["Group by Project"]
    P --> S["Pick spiking project → Group by Service"]
    S --> K["Pick service → Group by SKU"]
    K --> D["Group by Date > SKU"]
    D --> Q{"Which SKU category increased?"}
    Q -->|"Compute"| C["Check VM/GKE/Cloud Run, CPU, memory, runtime"]
    Q -->|"Storage"| ST["Check capacity, storage class, operations"]
    Q -->|"Network"| N["Check egress, locations, routing paths"]
    C --> F["Correlate with deployments and telemetry"]
    ST --> F
    N --> F
~~~

If you only group by Service, a spike caused by **Cloud SQL backup storage** gets lumped together with other SKUs under the same service. You must drill down to SKU and resource level to separate legitimate load growth from misconfiguration or over-provisioning.

### 3.4. Filters and their impact

Filters make reports easier to read, but also mean **the displayed total no longer represents the entire billing account**. For instance, filtering to project `shop-prod` can exclude account-level support fees or services running in other projects.

When saving analysis results, record:

~~~text
Billing account: [share-approved identifier]
Time range type: Charge period / Billing period
From – To: [dates or month]
Group by: Project / Service / SKU / ...
Filters: [project, service, SKU, location, label, savings]
Currency: [billing account currency]
Generated at: [timestamp of screenshot/export]
Audience / Owner: [responsible owner]
~~~

If two people report different figures, compare the **entire parameter set**, not just screenshots of the total dollar amount.

### 3.5. Resource labels and cost-attribution limits

Labels such as **team=payments**, **application=checkout**, and **environment=production** help view costs by accountability. However:

- Reports using **resource labels** may not display **project labels** in the same way.
- Not every charge type carries resource labels.
- Newly added labels generally apply only to tagged usage from that point forward; they do not retroactively tag history.
- Support charges or billing-account-level fees may not tie to a specific project or resource.

Therefore, a **Charges for other usage / unallocated** row does not prove all resources are untagged; it may stem from non-labelable charges or report settings.

## 4. Reading dollar figures: usage cost, savings, credits, and invoice charges

Billing systems present multiple kinds of monetary columns. Understand **which total you are reading** before judging a service as "expensive" or "cheap."

| Concept | Practical meaning | What to note |
|---|---|---|
| **List cost** | Cost calculated at public list prices where that field is available | Shown only in certain modes/accounts; not the final payable amount |
| **Usage cost / Cost** | Usage cost calculated at rates applicable to the billing account | May already reflect contract pricing; check report type |
| **Savings / credits** | Savings, credits, or promotional adjustments where applicable | May appear as direct price reductions or credit rows depending on mechanics |
| **Subtotal / Net cost** | Total after relevant deductions within the current view scope | Read column headers and savings toggles rather than guessing from chart colors |
| **Tax** | Tax on the invoice/statement | Not necessarily allocated per SKU or visible in filtered reports |
| **Adjustment / correction** | Billing-operations adjustments | May belong to a different document period than the usage period |
| **Rounding** | Document-level rounding variance | Small lines can still explain discrepancies during reconciliation |
| **Currency / exchange rate** | Currency and exchange rate applied to the billing account | Never compare two figures in different currencies directly |

An **illustrative** calculation, not a rigid formula for every UI view:

~~~text
Usage cost at applicable rates                   300.00 USD
Credit reductions                                -40.00 USD
Account-level support / fees                      15.00 USD
Invoice tax                                       25.00 USD
Rounding adjustment                                0.01 USD
----------------------------------------------------------
Illustrative document total                      300.01 USD
~~~

The **260.00 USD** figure (300 - 40) may represent a post-credit usage subtotal; it does not equal the **300.01 USD** document total because support, tax, and rounding remain. In real data, support, credits, or taxes may appear in **separate rows and groupings**; read the report's actual columns and footer rather than blindly adding per this illustration.

### 4.1. Credits do not always work the same way as discounts

A system may receive:

- Promotional or trial credits (if eligible).
- Usage-based or commitment-based discounts under current program mechanics.
- Contract-negotiated discounts.
- Invoice-level adjustments/credits.

Mechanics for some **committed use discounts (CUDs)** can vary between **credit-based** and **discount-based consumption models**. Never assume all savings sit inside a single "Credits" column. When analyzing CUDs, examine commitment fees, eligible usage, active consumption model, and net cost impact.

### 4.2. Forecasts are not invoices

Forecasts in Billing Reports estimate future costs using modeled signals. They help spot trends, but can shift due to sales campaigns, configuration changes, adding GKE clusters, or purchasing commitments.

Forecasts do not replace **budgets**, do not guarantee the month-end bill, and must not be treated as closed accounting figures. When sharing forecasts, record the snapshot timestamp and filter criteria.

## 5. Cost table: detailed reconciliation with an invoice or statement

The **Cost table** is a tabular report focused on **costs tied to an invoice/statement for a selected billing period**. It answers: "What is on this month's invoice—from which projects, services, and SKUs—and what taxes and adjustments apply?"

Typical path: **Google Cloud console → Billing → select billing account → Cost management → Cost table**. Requires cost-viewing permissions on the billing account; project-only viewers do not have the same account-wide reconciliation view.

### 5.1. Main sections of the Cost table

- **Header:** displays invoice/statement metadata such as account, period, document number, date, total amount, and currency; available fields vary by account and document type.
- **Table:** cost rows shaped by display configuration, grouping, and filters.
- **Footer:** sum of currently displayed rows, potentially including taxes, adjustments, and rounding.
- **Table configuration:** choose nested/flat view, Group by, and label keys.
- **Columns:** toggle columns to inspect or export.
- **Download CSV:** exports data constrained by the current report configuration.

Per Google Cloud documentation, under **default, unfiltered settings**, the Cost table footer matches the corresponding invoice/statement total. When you filter to a specific project or service, the footer updates to a **filtered total**, no longer matching the full document total. This is the single most important rule of reconciliation.

### 5.2. Nested table vs. flat table

| Mode | Structure | When to use |
|---|---|---|
| **Nested (default)** | Expandable hierarchy levels, e.g., **Project > Service > SKU > Consumption model** | Quickly find the costliest project and drill down to SKUs and consumption models |
| **Flat (No grouping)** | Each row is a cost/credit item aggregated at the table's grain | Filtering, column comparisons, CSV downloads, or Excel/BI ingestion |
| **Custom grouping** | Arrange supported dimensions as needed | Analyzing costs by labels, SKUs, or internal groupings |

Example branch of a nested table:

~~~text
Project: shop-prod                         150.00 USD
  Service: Compute Engine                  100.00 USD
    SKU: CPU usage                          65.00 USD
    SKU: Memory usage                       20.00 USD
    SKU: Storage                            15.00 USD
  Service: Cloud Storage                    50.00 USD
    SKU: Object storage                     32.00 USD
    SKU: Operations / network               18.00 USD
~~~

Numbers only **illustrate hierarchy structure**, not real unit prices or actual data. Real datasets may also include discounts, credits, CUD fees, or adjustment lines.

### 5.3. Key columns to know

| Group | Common fields or columns | Helps answer |
|---|---|---|
| Account | Billing account ID / name | Which account owns the charge? |
| Resource | Project name, Project ID, Project number, Project hierarchy | Which project or organizational unit? |
| Product | Service description / ID | Which service generated the charge? |
| Rate/usage | SKU description / ID, Usage amount, Unit | What was consumed, and in what unit? |
| Time | Invoice month and available timestamp fields | Which invoice period, which usage? |
| Charge type | Cost type | Usage, Tax, Adjustment, or other row type? |
| Price & total | List cost, Unrounded cost, Cost | List value vs. applied cost, any rounding impact? |
| Savings | Credit type, Credit name, Credit ID / amount per config | Why was a reduction applied? |
| Classification | Label key/value per config | Which cost center, environment, or team? |
| Currency | Currency; exchange rate where applicable | In what currency is the total calculated? |

Not every column is visible by default or populated for every account. For instance, **List cost** relates to contract-pricing scenarios depending on timeframe and plan; to look up **SKU unit rates**, consult the **Pricing table** or BigQuery pricing export, as the Cost table does not necessarily include a SKU unit-price column.

**Unrounded cost** helps when totals show small rounding discrepancies. Always reconcile official document-level figures first, then use unrounded values to trace minor penny differences.

### 5.4. Costs not tied to a specific project

Some charges such as **support** belong to the billing account rather than a specific project. In the Cost table, they may appear under **Charges not specific to a project** or an equivalent bucket. Thus, the sum of selected projects may not equal the billing account total, even when every "active" project is selected.

### 5.5. Taxes, adjustments, and invoicing cycles

Document-level taxes and adjustments may only appear in full when viewing by **Billing period** with no scope filters; some charges require accounting by project or tax type. An invoice month differing from the calendar usage month also happens due to late reporting, corrections, or post-period adjustments.

Google Cloud can issue **multiple documents in a single period** for certain account or transaction configurations. In those cases, Reports in Billing period mode may combine all charges for the month, while the Cost table lets you inspect **each specific document** for reconciliation. Always check invoice/statement number, currency, publisher type (if any), and selected scope.

## 6. Workflow for reconciling Cost table with an invoice

A verifiable process:

1. **Identify the document:** record billing account, invoice/statement number, invoice month, currency, publisher type if applicable, and total amount on the document.
2. **Open Cost table:** select the matching billing account and document period.
3. **Reset to default filters:** do not exclude projects, services, SKUs, or credits so you see the document's full scope.
4. **Compare header and footer:** verify whether both match the document total; account for multiple documents in a period and any permission-scope differences.
5. **Use nested view:** expand Project → Service → SKU to explain the largest cost components.
6. **Switch to flat view if needed:** display Cost type, SKU ID, Cost, Credits, Tax, Unrounded cost, and relevant columns.
7. **Export CSV:** retain an unfiltered export as evidence first, then export filtered slices for investigation.
8. **Document variances:** if any appear, explicitly note the formula, timeframe, data type, rounding, and excluded lines.
9. **Cross-check with Reports:** when comparing by invoice period, select Billing period for the exact month and matching filters; remember Reports combines across multiple invoices in the same month.

~~~mermaid
flowchart TD
    I["Invoice/Statement: total X"] --> C["Cost table matching billing account + invoice"]
    C --> F{"Default filters and sufficient permissions?"}
    F -- "No" --> R["Clear filters / verify permissions and document"]
    R --> F
    F -- "Yes" --> M{"Footer matches document total?"}
    M -- "Yes" --> D["Drill down Project > Service > SKU"]
    M -- "No" --> E["Check month, multiple invoices, currency, publisher, credits, tax, rounding"]
    E --> M
    D --> V["Save CSV + reconciliation output"]
~~~

**Never compare a project-filtered Cost table total directly against an invoice total.** Filtering drops account-wide charges, taxes, or separately allocated adjustments from the dataset.

### 6.1. Illustrative reconciliation table

Suppose the October invoice has hypothetical figures:

| Line item | Amount (USD) |
|---|---:|
| Compute Engine usage | 140.00 |
| Cloud Run usage | 60.00 |
| Cloud Storage usage | 40.00 |
| Cloud SQL usage | 60.00 |
| Total usage cost | **300.00** |
| Credits/savings reductions | -40.00 |
| Account-wide support fee | 15.00 |
| Tax | 25.00 |
| Rounding | 0.01 |
| Invoice total | **300.01** |

A **Charge period** report showing only net usage may report 260.00 USD; the **Cost table** at default filters explains 300.01 USD. If you filter to `Project=shop-prod`, support or account-level lines may disappear. In reports, always state clearly what each figure represents.

### 6.2. Reading CSV exports accurately

When clicking **Download CSV** in the Cost table:

- Output reflects active **Group by**, **filters**, and **selected visible columns**.
- CSV is **flat** data; it has no indented tree like nested view. Including or omitting a column can cause readers to misinterpret row grain.
- Record the document name, download timestamp, column list, grouping, and filters alongside the file.
- If exporting a large dataset fails, apply targeted filters or change grouping; for recurring large-scale analytics, consider BigQuery export.
- Never sum a Project-level summary row together with its child Service/SKU rows: that will **double count**.

CSV is an **analytical data export**, not a substitute for an official billing statement.

## 7. Scenario: investigating a cost increase from service to root cause

Suppose `shop-prod` monthly spend rises 35% compared to last month. The team should not immediately conclude "Google Cloud raised prices" or "GKE is too expensive" without knowing which SKUs changed.

### 7.1. Step 1: establish a baseline

In Reports:

1. Select the billing account and **Charge period** covering two comparable timeframes.
2. Filter to `Project=shop-prod`, keeping Savings filters consistent.
3. Choose Group by **Date > Service** to identify the **start date of the increase**.
4. Correlate with release logs, request traffic, batch schedules, and infrastructure changes.
5. Select the suspect service and Group by **SKU**.

Compare equal numbers of days, or normalize for remaining days in the month. Comparing **20 days of this month** against **all 31 days of last month** leads to false conclusions.

### 7.2. Step 2: analyze by workload category

| Workload / service | SKUs/cost drivers to check | Telemetry to compare |
|---|---|---|
| **Compute Engine** | vCPU, memory, persistent disks, GPUs, networking | VM count, machine types, runtime hours, CPU utilization, disks |
| **GKE** | Node Compute Engine resources, cluster/management fees if any, storage, networking | Node count, autoscaler, requests/limits, pods, workloads, cluster |
| **Cloud Run** | CPU, memory, requests or active billing-model units; networking and downstream services | Request count, concurrency, min instances, timeouts, processing volume |
| **Cloud Storage** | Stored GB, storage class, operations, retrieval, egress | Storage volume, object count, download frequency, lifecycle |
| **Cloud SQL** | Instance CPU/memory, storage, backups, networking | Query load, connection count, storage growth, HA, backups |
| **BigQuery** | Compute/analysis, storage, edition/capacity model if used | Bytes processed, slot utilization, queries, partitions |
| **Networking** | Internet/inter-region egress, load balancing, NAT, related paths | Bytes sent, traffic destination, region, network topology |
| **Observability** | Log ingestion/storage or active config-driven charges | Log volume, retention, sampling, metrics/traces |

**SKUs tell you what is being billed; monitoring tells you why resources were consumed.** Both sources must be cross-checked. For instance, higher egress during higher traffic is expected; higher egress after moving a connection to another region signals an architectural issue to fix.

### 7.3. Step 3: test a hypothesis

Suppose Reports reveals Cloud Storage networking SKUs surged after a new release. Engineering discovers images were previously cached via CDN, whereas the updated app fetches directly from a bucket in another region.

Verify:

- Does the start timestamp of the cost rise match the release timestamp?
- Did egress bytes and request counts climb proportionally?
- Did user count grow, or did only the network path change?
- If caching/routing is fixed, do latency, security, and cost all improve?
- Can we test on a fraction of traffic to measure before full rollout?

After identifying the cause, assign an owner to ship the config/code fix and watch Reports over the following days. Billing ingestion has latency, so avoid judging impact within minutes.

### 7.4. When is the Cost table needed?

If you are investigating an **increase on an issued invoice**, open the Cost table to verify the exact SKUs and the **tax/credit/adjustment** lines on that document. An invoice spike can come from an adjustment or late-posted usage from the end of the previous period rather than current-month traffic.

## 8. Allocating costs by project, team, and environment

### 8.1. A project is not always a cost center

Separating projects by application/environment simplifies IAM and cost attribution, yet one app may share a VPC, database, or platform services. Conversely, one project can host workloads from multiple teams.

Combine these layers:

- **Project:** primary unit for inventory and environment isolation.
- **Labels:** `team`, `application`, `environment`, `cost_center` on supported resources.
- **Shared-cost allocation rules:** define how support, networking, shared databases, or untagged resources are split.
- **Billing export:** multi-dimensional queries when built-in reports fall short.

Example monthly governance report:

| Cost group | Sample allocation rule | Risk |
|---|---|---|
| Resources tagged `cost_center` | Based on valid labels and billing period | Missing labels, mid-period label changes |
| Single-team dedicated project | Based on project ID | Support fees or shared services outside the project |
| Shared VPC/network | Split by measured ratio or internal policy | Egress telemetry may lack exact per-team granularity |
| Account-wide support | Defined split ratio; do not assume automatic per-project tie-out | Project sum does not equal account total |
| Shared credits | Transparent credit-sharing rule | Easy to misstate net cost across teams |

### 8.2. Distinguishing cost allocation from invoice reconciliation

**Cost allocation** answers "Which team bears which cost?" and can apply internal policy. **Invoice reconciliation** answers "Does our total payable match the billing document?" The two views can differ in **internal allocation logic**, though reconciled totals must still tie out.

A team might have 100 USD gross cost, 30 USD credits, and 5 USD allocated shared support. Whether to report the team at 100 gross, 70 net, or 75 net + allocation must be explicitly stated. Never change the formula between months without documenting it.

## 9. Cloud Billing export to BigQuery: when you need more than the UI

Reports and the Cost table work well for interactive investigation. When you need scheduled analytics, multi-dimensional queries, ERP integration, or automated dashboards, enable **Cloud Billing export to BigQuery** (subject to permissions and BigQuery costs per your configuration).

Typical export types:

| Export type | Core data | When to use |
|---|---|---|
| **Standard usage cost** | Account, invoice month, service/SKU, project, cost, credits, labels, and other fields | Cost trends, totals by project/team/service |
| **Detailed usage cost** | Standard fields plus resource-level details for supported services | Tracing cost spikes down to VMs/disks or supported workloads |
| **Pricing export** | Pricing details and corresponding rate metadata | SKU rate analysis, consumption-model optimization |

Do not assume detailed export always contains **resource IDs for every resource in every service**. Some capabilities require extra configuration, such as enabling GKE cost allocation. Data exports continuously through billing pipelines, not synchronously in real time. Enable export early if you need full historical continuity; enabling late can leave historical gaps depending on export type and dataset location.

### 9.1. Querying total cost and credits by project

Example using **standard usage cost export**. Replace with your actual BigQuery table path; dataset read permissions must be granted separately. This is an **analytical query**, not a replacement for invoice reconciliation in the Cost table.

~~~sql
-- Total cost by project for a specific invoice month.
-- Replace BILLING_PROJECT.BILLING_DATASET.EXPORT_TABLE.
WITH line_items AS (
  SELECT
    invoice.month AS invoice_month,
    currency,
    COALESCE(project.id, '(no project)') AS project_id,
    service.description AS service_name,
    cost AS usage_or_charge_cost,
    IFNULL(
      (SELECT SUM(c.amount) FROM UNNEST(credits) AS c),
      0
    ) AS credits_amount
  FROM `BILLING_PROJECT.BILLING_DATASET.EXPORT_TABLE`
  WHERE invoice.month = '202610'
)
SELECT
  invoice_month,
  currency,
  project_id,
  ROUND(SUM(usage_or_charge_cost), 2) AS cost_before_credits,
  ROUND(SUM(credits_amount), 2) AS credits,
  ROUND(SUM(usage_or_charge_cost + credits_amount), 2) AS net_amount
FROM line_items
GROUP BY invoice_month, currency, project_id
ORDER BY net_amount DESC;
~~~

Explanation:

- **invoice.month = '202610'** refers to the October 2026 document period, which does not mean all usage occurred in October 2026.
- **credits** is a nested array; using a **per-row SELECT SUM over UNNEST** avoids duplicating cost when a row has multiple credits.
- **project.id** can be null/empty when a charge is not tied to a project.
- **currency** is kept in GROUP BY so different currencies are never summed together.
- The output sums **cost + credits** from export rows; to match a document, also check cost types, taxes, adjustments, publisher, rounding, and data completeness.

**Common SQL pitfall:** using **CROSS JOIN UNNEST(credits)** directly and then `SUM(cost)`. Rows with two credits double the cost, while rows with zero credits can be dropped. Aggregate credits in a per-row subquery as shown above.

### 9.2. Querying to identify SKUs spiking by usage date

~~~sql
SELECT
  DATE(usage_start_time) AS usage_date,
  project.id AS project_id,
  service.description AS service_name,
  sku.description AS sku_name,
  ROUND(SUM(cost), 2) AS cost_before_credits
FROM `BILLING_PROJECT.BILLING_DATASET.EXPORT_TABLE`
WHERE usage_start_time >= TIMESTAMP('2026-10-01')
  AND usage_start_time < TIMESTAMP('2026-11-01')
  AND project.id = 'shop-prod'
GROUP BY usage_date, project_id, service_name, sku_name
ORDER BY usage_date, cost_before_credits DESC;
~~~

This query intentionally uses **usage_start_time** instead of **invoice.month**, so its numbers may not match the document total. It is designed for pinpointing when costs began rising. Furthermore, **SUM(cost)** does not subtract credits or reflect other savings fields; name the column **cost_before_credits** to avoid confusion.

### 9.3. Notes when working with labels

You can query **UNNEST(labels)** to allocate by label. However, just like credits, a row with multiple labels gets duplicated if joined carelessly. Select the exact key:

~~~sql
SELECT
  COALESCE(
    (SELECT l.value
     FROM UNNEST(labels) AS l
     WHERE l.key = 'cost_center'
     LIMIT 1),
    'unallocated'
  ) AS cost_center,
  ROUND(SUM(cost), 2) AS cost_before_credits
FROM `BILLING_PROJECT.BILLING_DATASET.EXPORT_TABLE`
WHERE invoice.month = '202610'
GROUP BY cost_center
ORDER BY cost_before_credits DESC;
~~~

**Unallocated** means the record lacked the target label key; you cannot conclude the resource lacks all labels. If the same key is used inconsistently across environments, reports will also need a data-normalization step.

## 10. Common cost-interpretation mistakes

| Symptom | Common cause | How to verify |
|---|---|---|
| Monthly Reports total differs from invoice | Viewing Charge period instead of Billing period; taxes/adjustments or late usage | Align periods; check time basis, taxes, and individual documents |
| Billing period Reports still differs from Cost table | Reports aggregates multiple invoices in a month; filters/savings differ | Check invoice count, publisher, filters, account permissions |
| Cost table footer differs from header | Filtered by project/SKU/service or viewing partial data | Reset filters, pick exact document, and re-compare |
| Sum of projects does not equal account total | Support or projectless charges | Look for Charges not specific to a project, taxes, adjustments |
| Most recent day looks unusually low | Billing data ingestion latency | Compare finalized days and wait for reporting processing |
| Gross rises while net drops | Credits/discounts or contract rate changed | Inspect Cost, List cost, savings, and credit types separately |
| Label `environment=prod` lacks history | Label applied late; service lacks labels in export | Check label start date, export schema, and coverage |
| Costs doubled in SQL | `UNNEST(credits/labels)` duplicated rows | Use per-row subquery aggregation or normalize before joining |
| CSV and on-screen table differ in detail level | Active Group by or selected export columns differ | Record filters, grouping, column list, and re-export |
| Wrong conclusion from currency mismatch | Comparing USD vs. VND or different billing-account currencies | Verify currency and exchange rates for the period |
| Network SKUs rise while app traffic stays flat | Routing changed, inter-region egress, backups/replication | Check regions, VPC, topology, and outbound data volume |
| Hard to attribute GKE costs to microservices | Multiple workloads share nodes or cost allocation disabled | Enable/verify workload cost allocation and metadata where supported |

A proper investigation needs **sufficiently granular evidence**: totals, project/service/SKU breakdown, timeframe, deployment changes, and operational metrics. Do not chase a matching number while ignoring how it was generated.

## 11. From cost analysis to governance action

### 11.1. Recurring FinOps cadence

| Cadence | Question | Action |
|---|---|---|
| Daily | Did any day spike abnormally? | Reports by day, service, and SKU; correlate with deploys/traffic |
| Weekly | How does month-end forecast compare to budget? | Check Reports forecast where supported; assign owners to investigate |
| Monthly | Does the invoice match cost figures? | Cost table, invoice, CSV, and reconciliation ledger |
| Monthly | Which costs remain unallocated? | Project/label reports, BigQuery export, and shared-cost rules |
| Quarterly | Is the architecture over- or under-provisioned? | Review VM/GKE sizing, Cloud Run concurrency, storage, backups, egress, commitments |

A good report assigns **one accountable owner per action**. For example, "Compute Engine rose 20%" is only an observation; "because the payments team tested upgrading two VMs to a larger machine type on Oct 12, we will measure CPU and decide to keep or downsize before Nov 20" is an actionable plan.

### 11.2. Turning findings into changes

- **Compute Engine:** check after-hours VMs, rightsizing, and orphaned disks.
- **GKE:** review requests/limits, autoscalers, pod density, node pools, and companion costs.
- **Cloud Run:** review min instances, concurrency, runtime, CPU allocation, and background work design.
- **Cloud Storage:** review lifecycle rules, storage classes, request/retrieval costs, and egress.
- **Cloud SQL:** review HA, instance count, machine sizing, storage, backups, and connection load.
- **BigQuery:** review partition/clustering pruning, bytes scanned, and capacity models.
- **Networking:** inspect regional traffic and eliminate hairpin or unnecessary transfers.

Every optimization must preserve **SLOs, security, and recoverability**. Never reduce redundancy or delete backups merely because a cost table highlights them as large line items.

### 11.3. Connecting to Budgets & alerts

Once you understand the baseline via Reports and the Cost table, create appropriately scoped budgets to monitor spend thresholds. Budget alerts generate **notifications** and normally do not act as a hard cap shutting down services. If building automated reactions upon threshold breach, add production impact checks, controlled execution identities, and proper notification channels.

## 12. Guided hands-on lab in Google Cloud console

This lab uses an account **with billing read permissions**; no new resources need to be provisioned. If you do not yet have access to a live billing account, work through the steps using screenshots or hypothetical data provided by your instructor.

### Part A — Reviewing trends

1. Open **Billing → Reports** on your assigned billing account.
2. Confirm **Charge period** mode and select **last month**; record the total and currency.
3. Choose **Group by Project** and list the three highest-cost projects.
4. Select one project, switch **Group by Service**, and identify the largest service.
5. Switch **Group by SKU** and identify the top two SKUs for that service.
6. Use **Date > SKU** (if supported in the UI) to identify the date of any noticeable increase.
7. Write a hypothesis for the cause and list the monitoring data required to verify it.

**Sample output:**

~~~text
Period: Charge period, 2026-10-01 to 2026-10-31
Account/project: [assigned]
Currency: [per account]
Highest project: [name] — [cost]
Highest service: [name] — [cost]
Highest SKU: [name] — [cost]
Increase start date: [date]
Hypothesis: [description]
Evidence to cross-check: [metric/deploy/traffic]
~~~

### Part B — Reconciling an invoice period

1. Open the **Cost table** in the same billing account.
2. Select the **invoice month** of an issued document and record the invoice number/currency.
3. Reset to **default filters**, and check whether header and footer match.
4. Keep the default nested view and drill down **Project → Service → SKU → Consumption model**.
5. Switch to **No grouping (flat)** to inspect Cost type, Credits, Tax, and Unrounded cost rows.
6. Download an unfiltered CSV; record the column set and export timestamp.
7. Filter to a single project and record the **filtered total**, explaining why it differs from the invoice total.
8. Open **Reports** in **Billing period** mode for the same month; compare and note if multiple documents or permission scopes differ.

**Sample output:**

| Field | Recorded value |
|---|---|
| Billing account | … |
| Invoice month | … |
| Invoice/statement number | … |
| Currency | … |
| Document total | … |
| Default Cost table total | … |
| Variance | … |
| Total after filtering one project | … |
| Why filtered total differs from invoice | … |
| Evidence link/CSV | … |

### Part C — Auditing cost-allocation quality

1. In Reports, try **Group by Label key** if permissions and data types permit.
2. Select a key such as **cost_center** or **team**, and record the unallocated amount.
3. Inspect the project and resource list to spot missing or inconsistent labels.
4. Propose a rule enforcing labels at resource creation (e.g., via Terraform modules or CI/CD pipelines).
5. Propose how to allocate **support** fees if they are account-level charges, rather than assuming automatic per-project assignment.

This section trains you to use billing data to uncover **metadata governance gaps**, beyond simple cost cutting.

## 13. Case study: invoice rises despite flat app traffic

**Hypothetical scenario.** An e-commerce platform runs a Cloud Run frontend, GKE backend, Cloud SQL database, and stores images in Cloud Storage. Three projects—**shop-dev**, **shop-prod**, and **data-analytics**—share one billing account. Last month, the invoice jumped 28%, while order volume grew roughly 3%.

**Investigation findings in Reports (hypothetical):**

| Step | Finding | Preliminary explanation |
|---|---|---|
| Group by Project | `shop-prod` drove most of the growth | Not primarily caused by `data-analytics` |
| Group by Service | Cloud Storage spiked; GKE grew slightly | Should not focus solely on tuning GKE nodes |
| Group by SKU | Cloud Storage networking fees increased | Data transfer volume is a likely culprit |
| Date > SKU | Increase started right after a frontend release | Time-correlated with an application change |
| Check Cloud Monitoring | Request count flat; bytes sent much higher | Images may be fetched repeatedly or routed differently |
| Inspect Cost table | Invoice month also had a tax adjustment | Part of the total variance was non-usage |

**Decision:** fix caching behavior and review image delivery configuration; monitor request counts and egress bytes before and after the change. Simultaneously, record the tax adjustment separately in accounting reports rather than blaming backend performance.

**Lesson:** to find optimization opportunities, use Reports by **Charge period + SKU + date**; to explain an invoice, use **Cost table by period and document number**. Then link findings to deployment changes and operational metrics to confirm root cause.

## 14. Self-check questions

1. A charge occurs late on Oct 31 but appears on the November invoice. Which mode should you use to find the usage date, and which tool to reconcile the invoice?
2. Why might **Project A + Project B** be less than the billing account total?
3. In the Cost table, you filter to Compute Engine and see a total smaller than the invoice. Can you conclude the invoice is wrong?
4. To know whether Cloud Run costs rose due to request count or execution duration, should you Group by Service or SKU?
5. **Cost = 100**, **credits = -20**, **tax = 10**, **support = 5**. Given these hypothetical figures, what are net usage and the illustrative document total if no other charges exist?
6. When combining `UNNEST(credits)` with `SUM(cost)` in BigQuery, what risk can occur?
7. Can forecasts in Reports be used as closed invoice figures?
8. To allocate costs by `cost_center`, why might project-level labels alone be insufficient?

**Suggested answers:**

- (1) Charge period when analyzing usage dates; Billing period/Cost table when analyzing the November document.
- (2) Account-level charges such as support, taxes, or projects/lines excluded by filters exist.
- (3) No; a filtered total is not the invoice total.
- (4) SKU to distinguish the specific consumption type, then cross-check Cloud Run metrics.
- (5) Net usage **80**; illustrative total **95**.
- (6) Duplicating cost when a row has multiple credits, or dropping rows that have no credits.
- (7) No; forecasts are trend-based estimates tied to filter scopes.
- (8) Resource labels are not automatically inherited by individual resources, and some charges do not carry labels.

## 15. Official reference documentation

The links below are Google Cloud docs for checking current UI and behavior:

- [Analyze billing data and cost trends with Reports](https://docs.cloud.google.com/billing/docs/how-to/reports)
- [View and download the cost details of your invoice or statement — Cost table](https://docs.cloud.google.com/billing/docs/how-to/cost-table)
- [Billing reports: View the charges on your invoices](https://docs.cloud.google.com/billing/docs/how-to/reports/charges-on-invoices)
- [Export Cloud Billing data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Structure of Standard usage cost data export](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage)
- [Billing reports: View forecasted costs](https://docs.cloud.google.com/billing/docs/how-to/reports/forecasted-costs)

Filter names, presets, columns, and discount mechanics may be updated by Google Cloud. For production systems, verify against your own account, permissions, billing period, and corresponding service documentation.

---

**Connection to the CLOUD_PROVIDERS_GCP track:** project organization, IAM, and VPC determine **who can create, operate, and view costs**; Compute Engine, GKE, Cloud Run, storage, and databases determine **which resources/SKUs generate costs**; Billing Reports reveal **trends and cost drivers**, the Cost table **reconciles document totals**, and exports, automation, and monitoring **turn cost insights into measurable spend controls**.
