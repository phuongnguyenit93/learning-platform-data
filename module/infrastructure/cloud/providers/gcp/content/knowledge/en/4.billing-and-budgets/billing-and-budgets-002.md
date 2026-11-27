# Billing Access Management and Cost Reconciliation on Google Cloud

> **Chapter:** Billing and Budgets  
> **Lesson:** Billing Access Management and Cost Reconciliation

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and database services, while learning how to select services, secure resources, automate releases, and monitor reliability alongside costs. A technically sound system must still answer **who can view or modify billing details, which team owns each cost, and whether total internal costs reconcile with billing statements**.

This lesson moves from Cloud Billing structure, IAM, and separation of duties to invoice reconciliation workflows, cost allocation, and setting up data for FinOps. Examples use **hypothetical** organization names, monetary amounts, and identifiers; you do not need access to a live billing account to follow the workflow.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish between a **Cloud Billing account**, **Google Cloud project**, **Google payments profile**, payer, and cost owner.
2. Choose the right IAM scopes and roles for billing administrators, finance/accounting, FinOps, project owners, budget managers, and BigQuery export consumers.
3. Differentiate **viewing costs**, **managing budgets**, **linking projects to a billing account**, **managing payment methods**, and **accessing billing documents**.
4. Reconcile **usage-date costs** with the **billing/invoice period**, recognizing credits, discounts, taxes, adjustments, account-level transactions, and shared costs.
5. Design **showback/chargeback** by project, labels, product groups, and shared cost allocation rules, and handle unallocated portions.
6. Use Cloud Billing Reports/Cost table and BigQuery export data to investigate discrepancies, report by the proper period, and implement spend-control measures.

## 2. Map of entities and permission boundaries

A **Cloud Billing account** collects usage costs for linked projects and is responsible for payment according to the account model. A **Google Cloud project** contains or scopes many technical resources. A project can be linked to only **one** Cloud Billing account at a time, while one billing account can pay for **many** projects.

A **Google payments profile** is the associated payment information and payment method system. Permissions on a payments profile and Cloud Billing IAM roles **are not identical**. Depending on the account type, certain Cloud Billing account permissions also allow payment actions via the Console, whereas full administrative control of a payments profile may require separate permissions configured in Google payments.

~~~mermaid
flowchart TB
    Org["Organization / Folder"] --> Dev["Project: development"]
    Org --> Prod["Project: production"]
    Org --> Data["Project: data-analytics"]
    Dev --> B["Cloud Billing account"]
    Prod --> B
    Data --> B
    B --> Pay["Google payments profile / payment workflow"]
    B --> Reports["Reports, Cost table, Budgets"]
    B --> Export["Billing export → BigQuery dataset"]
    Admin["IAM on Billing account"] -. "Grants view/manage access" .-> B
    ProjectIAM["IAM on Project"] -. "Project-level permissions" .-> Prod
    DatasetIAM["IAM on BigQuery dataset"] -. "Read access to exported data" .-> Export
~~~

The diagram illustrates **three distinct permission layers**:

- **Billing-account IAM**: who can view costs across the entire billing account, manage budgets/export configurations, and administer the account.
- **Project IAM**: who can manage resources, view costs within the project scope, or perform billing link operations with the corresponding permissions.
- **BigQuery dataset IAM and payments permissions**: who can read exported cost data, view billing documents, and manage payment details in the financial system.

**Important warning:** Granting billing view permissions on a single project does not automatically grant permission to view costs for all projects, and having access to BigQuery export data does not equate to Cloud Billing account administrative permissions.

### 2.1. Three frequently confused responsibilities

| Question | Deciding entity / scope | Typical owner |
|---|---|---|
| Who pays for the resources? | Billing account and associated payments configuration | Finance / billing admin |
| Who generates the costs? | Workloads in projects, services, SKUs, regions, resources | Development / operations teams |
| Which center is the cost charged to? | Internal allocation rules based on projects, labels, cost centers, and shared items | FinOps + finance + service owners |

A project is a useful starting point for attribution, but items like **network egress**, support fees, shared resources, or billing-account-level charges may not fit cleanly inside a single project/team the way the organization wants to account for them.

## 3. Cloud Billing IAM: roles, scopes, and least privilege

Google Cloud provides several specialized IAM roles. Choose roles based on the **task to be performed**, verifying the resource scopes that support each role and its included permissions at the time of assignment.

| IAM role | ID | Primary scope and capabilities | Should not be used in place of |
|---|---|---|---|
| Billing Account Administrator | `roles/billing.admin` | Broad administration of the billing account, account permissions, configurations, and cost information | Everyday report viewing role |
| Billing Account Costs Manager | `roles/billing.costsManager` | View costs, manage budgets, and export **cost data**; not full account admin | Managing payment methods or linking projects |
| Billing Account Viewer | `roles/billing.viewer` | Read account cost/transaction data; suited for reconciliation | Editing billing settings and assigning roles |
| Project Billing Costs Manager | `roles/billing.projectCostsManager` | Supports viewing/analyzing billing data restricted to projects where cost-viewing permission is granted | Account-wide cost viewing |
| Billing Account User | `roles/billing.user` | Allows using a billing account to link projects when paired with appropriate project-level permissions | Viewing all costs or administering the billing account |
| Project Billing Manager | `roles/billing.projectManager` | Manages linking/unlinking a billing account for a project, combined with required billing account permissions | Managing VMs, DBs, or application code |
| Billing Account Creator | `roles/billing.creator` | Allows creating supported types of billing accounts at the organization scope | Default role for every engineer |

**Check conditions, not just similar-sounding names:** to link an existing project to a billing account, the operator typically needs **permissions on both the project and the billing account** (for example, `roles/billing.projectManager` on the project **and** `roles/billing.user` on the target billing account). Having only one of the two roles may not be sufficient. Project open/create permissions, organization policies, and billing account status can also affect the operation.

The **Project Billing Costs Manager** role must be paired with cost-viewing permissions on the corresponding project; assigning a role at the billing account level alone does not guarantee the user can see costs for every project. Likewise, permission to view the billing page does not implicitly allow changing payment methods.

> **Principle:** Avoid using `roles/owner`, `roles/editor`, or `roles/billing.admin` merely to allow viewing cost tables. Choose the role with the least privilege required for the job and review assignments periodically.

### 3.1. Separation of duties (SoD) matrix

A small organization with three projects (`dev`, `prod`, `analytics`) sharing one billing account can divide duties as follows:

| Group | Required permissions | Scope to restrict to | Tasks not granted by default |
|---|---|---|---|
| **Billing admin** | Manage account and billing IAM policies | Assigned Billing account | Application deployment permissions unless needed |
| **Finance/accounting** | View transactions, invoices, and costs for reconciliation | Billing account; payments profile as required | Modifying VMs/GKE/technical IAM |
| **FinOps** | View trends, create budgets, manage cost exports when assigned | Relevant Billing account, analytics dataset | Changing payment methods or production resources |
| **Service owners/app teams** | View their own project's costs; receive budget alerts | Assigned project | Viewing other projects' costs and payment documents |
| **Data analytics team** | Read restricted cost views/datasets | BigQuery dataset/views | Billing account IAM admin or full payments access |
| **Auditors** | Read access during the audit window | Reports/documents needed for reconciliation | Write access, closing accounts, or unlinking projects |

Groups should be granted access via **Google Groups** where appropriate, with a designated group owner and an approval workflow. If elevated permissions are needed for incident response, use time-bound emergency access with audit logging.

### 3.2. Controlled permission-granting workflow

1. **Describe the need:** does the requester need to view reports, edit budgets, create exports, link projects, or manage payments?
2. **Identify the target:** billing account, project, BigQuery dataset, and/or payments profile.
3. **Select the lowest-privilege role:** use the table above and check the official permission list rather than guessing by role name.
4. **Obtain resource owner approval:** verify the billing account ID, project ID, recipient group, duration, and purpose.
5. **Grant at the right scope:** on the **Billing → Account management / Permissions** page or the IAM page of the relevant resource; menu labels may vary.
6. **Verify:** the recipient tests the exact approved task and confirms unauthorized actions remain restricted.
7. **Monitor and revoke:** periodically review members, groups, IAM policies, audit logs, and temporary access.

Distinguish between **cloud IAM** and **Google payments permissions**. An employee who needs to update a payment card or billing address may need permissions in Google payments; assigning a technical role on a project will not satisfy that need.

## 4. Access-control scenario: two teams, one billing account

Suppose `ExampleCo` has:

- `project-web-prod`: Cloud Run serving APIs and Cloud SQL storing transaction data.
- `project-data-batch`: BigQuery and analytics jobs.
- `project-shared`: shared networking, monitoring, or pipeline resources.
- Billing account `BA-EXAMPLE`: pays for all three projects.

The finance team needs total costs and billing documents. The web team only needs to see `project-web-prod` costs. FinOps needs to manage budgets and receive cost data to build dashboards. Infrastructure engineers occasionally need to link new projects to the billing account.

**Proposed design:**

1. Finance: billing account read permissions as needed; separate payments permissions if handling documents/payments.
2. Web team: cost-viewing permissions scoped to `project-web-prod`, without visibility into all projects.
3. FinOps: cost/budget management roles on the billing account and appropriate permissions on the BigQuery dataset; grant export configuration rights only if operating the pipeline.
4. Infrastructure engineers: `Project Billing Manager` on assigned projects and `Billing Account User` on the target billing account; revoke when the task ends.
5. Billing admin: a small approved group managing IAM and account settings. Do not grant admin permissions to service accounts deploying Cloud Run/GKE.

**Permission testing:** a web team member signs in and can only see costs within their allowed scope; they cannot edit payments or billing IAM. Accounting sees sufficient reconciliation data; they cannot stop production VMs. Infrastructure engineers verify link status for the right project before making changes.

## 5. Understanding cost concepts for accurate reconciliation

### 5.1. Usage/charge period vs. billing/invoice period

**Usage time** and **the period in which charges are invoiced** can differ. Billing data for a workload running at month-end may be recorded late or appear in a different invoice period. Reports by usage date are helpful for trend analysis; reports by **billing/invoice period** are the proper starting point for reconciling periodic invoice totals.

| Perspective | Used to answer | Risk if confused |
|---|---|---|
| Usage date / charge period | When did the workload incur costs? | Monthly total may differ from that month's invoice total |
| Billing period / invoice month | Which items were recorded on this period's invoice? | Poor visibility into when workloads actually ran |
| Project / service / SKU | Who and which service generated the cost? | Not every charge maps cleanly to a project |
| Invoice number | Which specific document was issued? | One billing period can have multiple invoices/documents depending on the billing model |
| Gross cost, savings/credits, tax, adjustments | How is the period-end total formed? | Treating gross cost as the payable amount can be wrong |

A **SKU** is a specific product/pricing unit (such as a compute type, storage capacity, or network traffic). When investigating anomalies, drill down from **billing account → project → service → SKU → location/resource** where data and permissions allow.

### 5.2. Components on financial reports

- **Usage cost / gross usage:** consumption cost before certain deductions; presentation varies by report.
- **Discount, credit, CUD, promotion:** conditional cost reductions or credits; verify which items are already reflected in totals and which appear as separate entries.
- **Tax, surcharge, adjustment:** may appear at the **invoice level**, not pre-allocated down to projects.
- **Payment / transaction:** paying funds or adjusting balances does not necessarily equal that period's consumption cost.
- **Currency:** uses the currency configured on the billing account; when aggregating multiple accounts in different currencies, use an approved exchange-rate rule and conversion date.

As a **hypothetical** example, suppose an invoice period contains only these items:

| Line item | Illustrative amount (USD) |
|---|---:|
| Compute Engine / Cloud Run | 120.00 |
| Cloud SQL | 240.00 |
| Cloud Storage | 40.00 |
| Network egress | 30.00 |
| **Total usage before deductions** | **430.00** |
| Applicable credits/discounts | -35.00 |
| **Usage after deductions** | **395.00** |
| Hypothetical tax | +39.50 |
| Hypothetical adjustment | -5.00 |
| **Illustrative document total** | **429.50** |

This is an arithmetic exercise to understand **reconciliation components**, not an actual tax schedule or service pricing table. Only sum items present on the document and follow how the data source defines them; do not subtract credits a second time if the report already displays net cost.

## 6. Google Cloud tools for analysis and reconciliation

### 6.1. Cloud Billing Reports

In Google Cloud Console, select the proper **Cloud Billing account** and go to **Billing → Reports**. Depending on your permissions and the current UI, you can:

- Choose the time range by **charge period/usage date** or **billing period/invoice month**.
- Group by project, service, SKU, or supported analysis dimensions.
- Filter by project, service, label, or applicable criteria.
- Inspect cost trends and savings/credits within the selected scope.

To reconcile an invoice, start with the **full billing period**, **all projects, services, SKUs, and applicable deductions**; only filter afterward to trace root causes. A report filtered only to `project-web-prod` cannot be expected to match the billing account's document total.

### 6.2. Cost table and documents

The **Cost table report** is designed for viewing costs by invoice and can be exported as **CSV** for inspection. **Billing Reports** in billing-period mode may display aggregated costs for that period; if the period has multiple invoices, the report total may be a combined sum and **will not** equal a single invoice.

For periods with taxes, invoice-level credits, adjustments, or surcharges, open the appropriate report by invoice period and review all relevant line items. Usage-time views or project/service filters may omit invoice-level taxes and adjustments.

### 6.3. Billing export to BigQuery

When multi-month reporting, team-based allocation, or FinOps automation is needed, you can enable **Cloud Billing export to BigQuery**:

| Export type | Purpose | Notes |
|---|---|---|
| **Standard usage cost** | Trends by billing account, project, service, SKU, location, labels, credits | Many showback implementations can start here |
| **Detailed usage cost** | Trace cost sources to resources for supported services | Larger data volume; not every SKU includes full resource IDs |
| **Pricing data** | Analyze actual account-specific pricing catalogs | Separate permissions to configure/read; does not replace invoices |
| **FOCUS usage cost** (subject to availability and release status) | Analysis under the FinOps Open Cost and Usage Specification standard | Check support status and data rules at deployment time |

Exports are **not real-time data**. There is latency, backfill limitations, and differences depending on dataset location; data only begins collecting according to each export type's policy. Enable it early if the organization needs long-term history, record the start timestamp, and monitor the pipeline.

**Separate permissions:** permission to configure export on the billing account differs from permission to create/read the BigQuery dataset. Use a dedicated FinOps project/dataset, design scoped read access, auditing, retention, controlled view sharing, and monitor BigQuery storage/query costs.

### 6.4. Monitoring budgets and anomalies

An **alerts-only budget** notifies when actual or forecasted spend approaches thresholds; by default, it **does not automatically stop services or block billing charges**. Some scenarios/services may support a **spend cap budget** under specific conditions; check availability, behavior, and workload impact before treating it as a hard limit.

For example, a 1,000 USD/month production budget might alert at 50%, 80%, 100%, and when forecasted to exceed 110%. These are **illustrative levels** only. The response workflow needs clear recipients and responders, combined with SKU reports, anomaly detection, and checks for underutilized resources.

## 7. Period-end cost reconciliation workflow

Reconciliation serves two distinct goals:

1. **Financial reconciliation:** valid document totals and transactions are explained by line items in billing reports.
2. **Governance reconciliation:** those costs are attributed to projects, teams, products, and cost centers under a consistent policy.

A charge may already be confirmed by accounting as **matching the invoice** while still not yet allocated to the **right team**.

~~~mermaid
flowchart TD
    A["Select billing account + invoice period"] --> B["Retrieve invoice/document + Cost table"]
    B --> C["Reconcile totals: usage, credits, taxes, adjustments"]
    C --> D{"Discrepancy?"}
    D -->|Yes| E["Check filters, invoice number, timing, charge type, currency"]
    E --> C
    D -->|No / explained| F["Allocate by project, service, labels"]
    F --> G["Identify shared and unallocated costs"]
    G --> H["Apply showback/chargeback rules"]
    H --> I["Approve, archive evidence, lock report figures"]
~~~

### Step 1. Lock the data source and scope

Specify the **billing account ID, organization name, currency, billing period**, list of invoices/documents, and data cutoff timestamp. Agree on the objective: reconciling the **period total**, **individual invoices**, or **individual projects**. Use appropriate viewing permissions; do not copy sensitive account numbers or payment details into technical tickets.

### Step 2. Pull the exact invoice period

In Billing Reports/Cost table:

- Select the invoice-period mode, including **all invoices** when reconciling the monthly total, or select the exact invoice when reconciling a single document.
- Ensure project, service, SKU, and savings filters **do not accidentally exclude charges**.
- Record the usage subtotal, savings/credits, taxes, adjustments, surcharges, and grand total after all components.
- For account charges not tied to a project, keep them in a **shared/unallocated** category rather than arbitrarily assigning them to the largest project.

### Step 3. Investigate discrepancies

| Discrepancy observed | Possibilities to check | Resolution |
|---|---|---|
| Usage month differs from invoice month | Late usage ingestion or different invoice period | Reconcile by invoice period; use charge date to explain |
| Project totals add up, but account total is higher | Taxes, adjustments, shared fees, projectless charges | Keep an unallocated group and compare against unfiltered Cost table |
| Net cost does not match | Credits subtracted twice, CUD/promotions omitted, or reporting representation mismatch | Separate gross, credits, and net per source; do not mix calculation methods |
| Period has more than one invoice | Monthly report aggregates multiple documents | Match each invoice number individually, then sum to verify |
| BigQuery has only partial data | Export delay, incomplete backfill, dataset change, or newly enabled | Wait for pipeline per internal SLA; reconcile against Console |
| Costs do not belong to the expected team | Wrong project, missing labels, shared resource, project transfer | Investigate owner/change logs; confirm allocation rules |
| Currency or rounding variance | Multiple currencies, exchange rates, line-item rounding | Never sum different currencies; publish conversion rules |

**Do not erase discrepancies by leaving an indefinite "other" line item.** Any variance line needs a reason, owner, status, and evidence. Unclear charges remain **unallocated**—do not guess their source.

### Step 4. Allocate to cost centers

A typical priority order is:

1. **Dedicated project per product/team:** has a clear owner and cost center.
2. **Useful labels/tags:** such as `team`, `env`, `app`, `cost-center`, where the service supports them and export data includes the corresponding fields.
3. **Service/SKU/resource mapping:** used when resources or charges lack labels but have a trusted ownership catalog.
4. **Shared costs:** allocated using an approved metric, such as usage ratio, request count, or fixed split.
5. **Unallocated:** build an exception list to improve metadata and policy coverage.

Newly applied labels **do not necessarily apply retroactively** to historical costs. Do not assume every charge type supports tracing down to individual resources or labels. Track the "unallocated" percentage explicitly as a FinOps data-quality KPI.

### Step 5. Approve and preserve an audit trail

Separate the person **preparing the allocation sheet**, the person **approving the numbers**, and the **billing permissions administrator** if organization size permits. Store report versions, cutoff period, access-controlled source links, filters used, BigQuery queries executed, allocation rules, and open exceptions.

When exporting CSVs or reconciliation sheets, apply read-only access for relevant stakeholders; restrict sharing of invoice details, payments profiles, and cost data for projects outside a recipient's scope.

## 8. Shared cost allocation example

Suppose two product projects have direct costs after deductions (excluding tax) as follows:

| Group | Direct cost (USD) | Shared resource consumption ratio |
|---|---:|---:|
| Team A — API | 500 | 60% |
| Team B — Batch | 300 | 40% |
| **Total** | **800** | **100%** |

A shared platform project incurs an additional **200 USD**. Internal policy approves allocating it proportionally by measured CPU hours across the two teams. Then:

- Team A receives **200 × 60% = 120 USD**, total showback **620 USD**.
- Team B receives **200 × 40% = 80 USD**, total showback **380 USD**.
- Total after allocation remains **1,000 USD**. Do not add the 200 USD to the shared project again after allocating it to the two teams, or you will double-count.

This is **showback**: teams see their attributed costs. **Chargeback** occurs only when the organization uses those results to actually record or transfer costs into internal budgets under finance policy. Both concepts may use the same underlying data, but they have different approval workflows.

If reliable CPU-hour data is unavailable yet, do not invent a 60/40 split. You can use an even split as an **approved interim rule**, clearly state the margin of error, and replace it with actual telemetry later.

## 9. BigQuery: illustrative cost query by invoice month

Suppose **Standard usage cost** billing export is enabled and the dataset contains the table `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>`. The illustrative query below aggregates costs by **project**, **service**, and **invoice month**.

~~~sql
-- Example only: replace BILLING_DATASET and BILLING_ACCOUNT_ID.
-- Choose the YYYYMM month matching the invoice period to analyze.
WITH usage_cost AS (
  SELECT
    invoice.month AS invoice_month,
    COALESCE(project.id, 'UNALLOCATED') AS project_id,
    service.description AS service_name,
    cost AS gross_cost,
    COALESCE((
      SELECT SUM(c.amount)
      FROM UNNEST(credits) AS c
    ), 0) AS credit_amount,
    currency
  FROM `billing-project.BILLING_DATASET.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
  WHERE invoice.month = '202611'
)
SELECT
  invoice_month,
  currency,
  project_id,
  service_name,
  ROUND(SUM(gross_cost), 2) AS gross_cost,
  ROUND(SUM(credit_amount), 2) AS credits,
  ROUND(SUM(gross_cost + credit_amount), 2) AS net_usage_cost
FROM usage_cost
GROUP BY invoice_month, currency, project_id, service_name
ORDER BY net_usage_cost DESC;
~~~

**How to read this:**

- `invoice.month` uses the `YYYYMM` format, which differs from filtering by the `usage_start_time` date.
- The `cost` field and entries in the `credits` array have specific representations. Credits are typically negative values; inspect actual data before building financial formulas.
- Rows without a `project.id` still matter and should be preserved as `UNALLOCATED`.
- `currency` is included in the grouping to avoid summing amounts in different currencies.
- Aggregating usage/credits alone is **not sufficient to guarantee an invoice match** when there are taxes, adjustments, invoice-level fees, multiple invoices, or export latency. Use the Cost table and invoice as the final source of reconciliation.
- BigQuery datasets incur storage/query charges depending on configuration; review scanned data volume, partitioning, and accessed data scope.

**Technical note:** Export table naming depends on export type and billing account; hyphens in project IDs are enclosed in BigQuery backticks in the example. Do not copy placeholder values like `BILLING_ACCOUNT_ID` or `202611` verbatim for production environments.

### 9.1. When to use Detailed export?

If costs spike in **Compute Engine** or **GKE**, detailed data can help identify resources, clusters, or allocation metadata where supported by the product. However, resource-level coverage **is not uniform across all services**. For GKE, check requirements for enabling **cost allocation** to receive certain workload/cluster cost fields.

Use **Standard export** for broad trends and **Detailed export** to drill into anomalous areas. For widely shared dashboards, create BigQuery views scoped to required projects and columns rather than granting every team read access to the account-wide raw table.

## 10. Investigation scenario: unexpected Cloud Run and Cloud SQL cost spike

One month, a product team notices that `project-web-prod` costs are 30% higher than forecast. Accounting confirms the account-wide invoice matches, so FinOps needs to determine the cause for allocation and remediation.

**Reasonable steps:**

1. Select the proper billing account and project; filter by **charge period** to pinpoint the day of the change while keeping the **invoice period** report for period-end reconciliation.
2. Group by **service/SKU**: check Cloud Run compute, Cloud SQL instance/storage/backup, and network egress.
3. Compare deployment changes: Cloud Run min instances, concurrency, instance count, Cloud SQL sizing, backup growth, request volume, and outbound data transfer.
4. Check Cloud Monitoring/Logging: traffic, latency, error rate, DB connections, CPU/storage; correlate with deployment milestones and campaigns.
5. If underlying metrics match, separate **costs from legitimate workload growth** from **costs caused by misconfiguration/inefficiency**, and create remediation actions with owners.
6. Update forecast/budget alerts and reflect the impact in the team's showback report; preserve the audit trail if accounting needs an explanation.

**Do not blame every Cloud Run cost increase on "broken autoscaling."** Costs may come from heavy Cloud SQL queries, backups, network egress, or shared resources. Investigate by SKU and actual metrics.

## 11. Monthly financial operations cadence

| Timing | Task | Owner | Output |
|---|---|---|---|
| Daily/weekly | Monitor budget alerts, anomalies, major SKU shifts | FinOps + service owners | Investigation tickets, updated forecasts |
| Period end / when documents are ready | Collect invoices, Cost table, matching transactions | Finance | Document reconciliation sheet |
| Once export data is complete | Aggregate by project/labels, allocate shared costs | FinOps | Draft showback table |
| Before locking numbers | Confirm credits, taxes, adjustments, variances, exceptions | Finance + FinOps | Period close sheet, explanation log |
| Periodically | Review IAM, project owners, labels, and budgets | Billing admin + service owners | Access report and allocation improvements |

**Change control:** changing a project's billing account or payment method can cause operational disruption or split invoice attribution. Follow an approved change process, record before/after states, and coordinate with finance.

### 11.1. Dataset to retain for each reconciliation period

Each period should have a governance record containing:

- Billing account (internal code or controlled ID), invoice period, currency, and invoice list.
- Gross/net usage totals after credits under clear definitions, taxes, adjustments, and document totals.
- Directly allocated amounts, shared allocations, unallocated amounts, and applied rules.
- CSV files/export tables or access-controlled links to sources, plus the data cutoff timestamp.
- List of discrepancies, assumptions, owners, confirmation dates, and approvers.

Do not share invoice copies or payments profile details through channels not approved by the organization.

## 12. Common mistakes and how to avoid them

| Mistake | Consequence | Prevention |
|---|---|---|
| Granting every engineer `roles/billing.admin` just to view costs | Over-privileged access, hard to audit | Use viewer or project-scoped cost roles |
| Assuming Project Owner includes admin rights over every billing account | Incorrect IAM boundary | Check both project IAM and billing account IAM |
| Using Project Billing Manager without permissions on the target account | Unable to link project | Verify the required role set on both resources |
| Giving app teams access to the company-wide raw billing dataset | Exposes other teams' costs | Use scoped views/datasets and appropriate IAM |
| Comparing invoice month against usage-date total for the same calendar month | Period mismatch and invoice confusion | Separate the two views and state the period clearly |
| Subtracting credits twice or omitting tax/adjustment | Incorrect financial totals | Distinguish gross, net, and invoice-level charges |
| Applying new labels and assuming historical data updates automatically | Inaccurate showback | Document effective dates and retain unallocated entries |
| Ignoring projectless charges | Allocation total does not reconcile | Track shared/unallocated items until resolved |
| Treating an alerts-only budget as a "spend shutoff valve" | Budget overruns | Design response workflows; check spend caps if supported |
| Treating BigQuery export as the final invoice | Misses taxes, adjustments, or delayed data | Close financials based on invoices/Cost table |

## 13. Role-based exercise (no live billing changes needed)

A training organization has three projects:

| Project | Owner | Services | Hypothetical period cost |
|---|---|---|---:|
| `academy-web` | Team Web | Cloud Run, Cloud SQL | 360 USD |
| `academy-data` | Team Data | BigQuery, Cloud Storage | 240 USD |
| `academy-shared` | Platform | Network/Monitoring | 100 USD |

There is also a **20 USD credit**, **70 USD hypothetical tax**, and a **10 USD cost-increasing adjustment**. Internal policy requires allocating the shared project at **70% Team Web / 30% Team Data**, while finance tracks taxes and adjustments separately from technical showback.

**Questions:**

1. What are the total direct/shared usage cost, cost after credits, and illustrative invoice total?
2. How much of the **shared** cost does each team receive? What is each team's technical showback total before credits?
3. Team Web only needs to view `academy-web` costs. Why should you not grant Billing Account Administrator?
4. An employee needs to link a new project to the billing account. Identify the two permission scopes that must be checked.
5. Finance sees `usage date` data differing from the invoice. List at least three possible causes.
6. If FinOps enables Standard export today, can they assume all historical data will automatically export in full?
7. If a budget sends a 100% alert, can you conclude all services will automatically stop? Explain.

**Check your answers:**

- Direct and shared usage cost before deductions: **700 USD**; minus 20 USD credit equals **680 USD**; plus 70 USD tax and 10 USD adjustment equals **760 USD** per the hypothetical inputs.
- Shared portion: **Team Web 70 USD**, **Team Data 30 USD**. Technical showback before credits/tax/adjustment: **Team Web 430 USD**, **Team Data 270 USD**; total remains **700 USD**.
- Remaining answers should mention least privilege; separate IAM at project/account levels; ingestion latency/period adjustments; backfill limits; and the difference between alerts and conditional spend caps.

## 14. Billing governance and reconciliation checklist

- [ ] Maintain a clear inventory of billing accounts, payments profiles, linked projects, and owners.
- [ ] Assign permissions at the proper scope: billing account, project, dataset, and payments profile.
- [ ] Separate viewing, editing budgets/exports, linking projects, and payment administration permissions.
- [ ] Define budget alert recipients, anomaly responders, and approved operational thresholds.
- [ ] Standardize the reconciliation period, currency, invoice numbers, and additive/deductive line items.
- [ ] Verify credits, discounts, taxes, adjustments, and projectless line items.
- [ ] Establish policies for shared cost allocation, labels, cost centers, and handling unallocated spend.
- [ ] Record when billing export was enabled, data limitations, and dataset access controls.
- [ ] Maintain a period-close schedule, preparer, approver, evidence trail, and discrepancy resolution process.

## 15. Official reference documentation

IAM permissions, budget capabilities, and export schemas may evolve. When implementing on live Google Cloud environments, verify current documentation and permissions:

- [Cloud Billing access control and permissions](https://docs.cloud.google.com/billing/docs/how-to/billing-access)
- [Cloud Billing roles and permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/billing)
- [Billing reports: View the charges on your invoices](https://docs.cloud.google.com/billing/docs/how-to/reports/charges-on-invoices)
- [Create, edit, or delete budgets and budget alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Export Cloud Billing data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Set up Cloud Billing data export to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-setup)
- [Understand the Cloud Billing data tables in BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables)

**Key takeaway:** Google Cloud reconciliation must connect **access permissions**, **usage metrics**, **invoice periods**, and **internal allocation rules**. When every cost item has a clear source, scope, owner, and explanation, teams can simultaneously protect resources and track reliability and spend throughout service delivery.
