# Exporting Billing Data to BigQuery

> **Chapter:** Billing and Budgets  
> **Module:** CLOUD_PROVIDERS_GCP

When managing multiple projects on Google Cloud, Cloud Billing Reports provide quick cost visibility, yet engineering and finance teams often need deeper answers: *How much does the production project spend compared to development? Which service drove the invoice up? Which SKU generated data transfer fees? How were discounts and credits applied?* When you need SQL-queryable data for internal reporting or joins with owner/team metadata, **Cloud Billing export to BigQuery** is the right tool.

This lesson belongs to **CLOUD_PROVIDERS_GCP**, a module exploring Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases. Across deployment scenarios, learners must know how to choose services, secure resources, automate releases, and monitor reliability alongside cost. This lesson focuses on configuring export pipelines, understanding the schema, writing queries, and operating cost reports properly.

After this lesson, learners will be able to:

1. Explain the differences between Cloud Billing Reports, Budgets, and data exported to BigQuery.
2. Choose the right export type among Standard, Detailed, Pricing, FOCUS, and CUD metadata.
3. Prepare the billing account, project, IAM permissions, BigQuery API, dataset, and location.
4. Enable export in the Console, verify generated tables, and understand backfill scope.
5. Write SQL aggregating costs by project, service, SKU, time, and credits.
6. Handle delayed tables, invoice mismatches, missing labels, and cost duplication.

## 1. Data flow from Cloud Billing to BigQuery

A **Cloud Billing account** is a payment account linked to one or more Google Cloud projects. When export is enabled, Google Cloud automatically writes usage/cost records into the configured **BigQuery dataset**. Users with query permissions on that dataset can then run GoogleSQL, create views, build dashboards, or maintain summary tables.

~~~mermaid
flowchart LR
  subgraph APP["Cost-generating projects"]
    P1["app-dev"]
    P2["app-prod"]
    P3["data-prod"]
  end
  P1 --> B["Cloud Billing account"]
  P2 --> B
  P3 --> B
  B --> EX["Cloud Billing export"]
  EX --> DS["BigQuery dataset in FinOps project"]
  DS --> SQL["SQL / Views / Scheduled queries"]
  SQL --> DASH["Reports / Dashboards"]
  SQL --> FIN["Cost variance investigations"]
~~~

| Component | Role | Example |
| --- | --- | --- |
| **Billing account** | Paying entity receiving costs across multiple projects | Corporate billing account |
| **Workload project** | Runs VMs, GKE, Cloud Run, Cloud SQL and incurs usage | `app-prod` |
| **Export project** | Hosts the dataset, manages permissions and BigQuery costs | `finops-admin` |
| **Dataset** | Container for data tables and views | `billing_export` |
| **Export table** | Table created and populated by the Billing service | `gcp_billing_export_v1_...` |
| **Query job** | Queries tables in BigQuery; may incur query costs | Net cost analysis by project |

For **Standard** and **Detailed usage exports**, the table records usage/cost data across **all projects paid by that same billing account**, not only the project hosting the BigQuery dataset. The project storing the export must have billing enabled and be linked to the target billing account per current setup documentation.

### 1.1. Why not rely solely on Cloud Billing Reports?

| Need | Reports/Budgets | Export + BigQuery |
| --- | --- | --- |
| View cost trends by project, service | Built-in, visual interface | Write SQL queries or build dashboards |
| Set spend thresholds and receive alerts | Use Budgets & alerts | Requires a separate alerting mechanism if driven by SQL |
| Allocate by team, cost center, internal rules | Depends on built-in filters | Flexibly combine labels, tags, and metadata tables |
| Analyze invoices, adjustments, credits, SKUs | Summary reports | Access granular records for custom calculations |
| Join with app catalogs or owner tables | Limited | Use `JOIN` across authorized datasets |
| Produce custom recurring reports | Built-in options available | Use views, scheduled queries, and BI tools |

**Do not treat BigQuery export as a real-time feed**: individual services report usage on varying schedules; export pipelines have latency and no fixed delivery SLA. Budget alerts also do not automatically stop all services when thresholds are crossed. Exports support analysis and decision-making, while automated responses must be engineered separately.

## 2. Exportable data types

Cloud Billing offers several export options. Distinguish **incurred cost data** from **pricing catalogs** or **commitment metadata**.

| Type | Primary data | Common table/destination | Best suited when |
| --- | --- | --- | --- |
| **Standard usage cost** | Billing account, project, service, SKU, usage, cost, credits, labels, invoice, currency | `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>` | Aggregating costs by project, service, SKU |
| **Detailed usage cost** | All Standard fields plus resource-level details for supported services | `gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>` | Pinpointing specific VMs/resources driving spikes |
| **Pricing data** | Account-specific pricing, SKU, unit, pricing tiers, region | `cloud_pricing_export` | Analyzing unit rates and pricing policies |
| **FOCUS usage cost** | Standardized usage/cost records per FinOps Open Cost and Usage Specification | Google-provided dataset with table `gcp_billing_export_focus_<BILLING_ACCOUNT_ID>` | Standardizing FinOps / multi-cloud data |
| **CUD metadata** | Commitments, product type, scope, term, committed quantity | Linked dataset with table `cud_subscriptions_export` | Tracking committed use discount portfolios |

**Start with Standard** if your goal is knowing which project spends the most or which service is growing. Enable **Detailed** only when resource-level dimensions are needed; detailed data typically consumes more storage and query scan cost.

Practical differences to note:

- Detailed includes Standard fields plus certain resource attributes, yet **not every service or SKU emits identical resource-level detail**.
- To break down **GKE** costs by workload/namespace, check and enable **GKE cost allocation** per its documentation; enabling Detailed alone does not guarantee all allocation dimensions.
- Pricing data is a separate export pipeline requiring different API/permission prerequisites from usage export.
- FOCUS/CUD metadata may be in **Preview** with different dataset creation and lifecycle rules. Under published docs, Google-provided FOCUS tables carry a **two-year TTL** policy.
- **Never sum Standard and Detailed into a single total**: the same usage appears in both tables, causing double counting.

### 2.1. Choosing an export type from the question to answer

- "How much did `app-prod` cost this month?" → Standard by project/invoice.
- "Which SKU drove Compute Engine growth?" → Standard by service and SKU.
- "Which specific VM accounts for the biggest share?" → Detailed by resource fields, where supported.
- "What is the SKU's rate by tier/consumption model?" → Pricing.
- "Which commitment contracts expire soon?" → CUD metadata combined with CUD management reports.
- "Need multi-provider normalization under FOCUS?" → Check FOCUS export and current schema version.

## 3. Preparing the billing account, project, and IAM

### 3.1. Choosing the storage project

A common layout:

~~~text
Cloud Billing account BILLING_ACCOUNT_ID
├── app-dev                (workload)
├── app-prod               (workload)
├── analytics-prod         (workload)
└── finops-admin           (export storage project)
    └── billing_export     (BigQuery dataset)
        ├── gcp_billing_export_v1_...
        └── gcp_billing_export_resource_v1_...
~~~

Using a dedicated FinOps project keeps permissions, budgets, and data lifecycles independent of application workloads. **Ensure the export project is linked to the exact billing account being exported.** Billing accounts and projects have a payment link; matching names does not guarantee a proper link.

### 3.2. Required roles

Google's documentation separates permissions by export type:

| Task | Permission prerequisites to check |
| --- | --- |
| Enable Standard/Detailed usage export | **Billing Account Costs Manager** or **Billing Account Administrator** on the billing account; **BigQuery User** on the dataset's project |
| Enable Pricing/CUD metadata export | **Billing Account Administrator** on the billing account; **BigQuery Admin** on the dataset's project, plus `resourcemanager.projects.update` per documentation |
| Create a new project | Organization-granted project creation permissions, typically Project Creator |
| Create datasets or enable APIs | Appropriate BigQuery/Service Usage permissions on the export project |
| Read tables and run SQL | Table data read access and query-job creation permissions on the execution project |

Permissions on the **billing account** and permissions on the **BigQuery project/dataset** are two separate layers. Someone who can view Billing Reports may lack permission to create datasets; someone with BigQuery access may lack permission to enable exports. Follow least-privilege IAM rather than granting broad Owner access to bypass permission errors.

### 3.3. APIs and costs

- **BigQuery API** must be enabled on the target project; the Console may prompt to enable it during setup.
- When enabling **Pricing data export**, enable **BigQuery Data Transfer Service API** on the dataset's project.
- Standard/Detailed usage exports do not require the Data Transfer Service API **solely** for cost export.
- BigQuery storage and queries/scheduled queries can incur costs. Set a budget on the export project and monitor its usage.

### 3.4. Choosing dataset location before creation

A BigQuery dataset's location **cannot be changed after creation**. Cloud Billing supports the two multi-regions **US/EU** and only selected individual regions.

| Dataset location | When **enabling usage export for the first time** | Key point to remember |
| --- | --- | --- |
| **US/EU multi-region** | Google can backfill data from the **first day of the prior month** relative to enablement | Historical data loads sequentially; catching up can take up to roughly five days |
| **Supported region** | Starts only from the **date export is enabled** | Does not retroactively backfill prior history |
| **Unsupported region** | Configuration cannot be saved | May return `Invalid dataset region` |

**Example:** Enabling Standard export for the first time on **November 19, 2026** into a US multi-region dataset may receive data back to **October 1, 2026**, under currently published policy. Using a supported single region starts data collection only from the enablement date. This illustrates policy and historical scope, **not a guarantee that full data appears immediately on day one**.

Exceptions to remember:

- **Pricing export does not backfill** data prior to enablement.
- Disabling and re-enabling can leave an export gap during the disabled window.
- Switching to a new project/dataset **does not automatically copy** previously exported history to the new destination.
- Data deleted from export tables normally cannot be backfilled again on request.
- Choosing US/EU must comply with data residency policies. If the organization mandates a specific region, verify that region is supported and accept the lack of backfill.

Review Google's maintained location list at [Set up Cloud Billing data export](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-setup#dataset-locations). Never assume every BigQuery region is valid for Billing export.

### 3.5. Estimating data volume and BigQuery costs

Enabling Detailed generates more rows than Standard. When building dashboards, costs also arise from bytes scanned or materialized result tables. Control measures:

1. Pick the export type sufficient for your questions.
2. Restrict time ranges and select only required columns; check **bytes processed** before running heavy queries.
3. Use views to standardize schemas and summary tables for recurring reports.
4. Set budgets and monitor the FinOps project's own BigQuery spend.
5. Evaluate storage needs, access controls, and retention before enabling all export types broadly.

## 4. Enabling Standard/Detailed export in Google Cloud Console

### Step 1 — Prepare the project and dataset

Open [BigQuery Console](https://console.cloud.google.com/bigquery), choose the export project, and click **Create dataset** in Explorer. Example:

~~~text
Billing account : BILLING_ACCOUNT_ID
Export project  : finops-admin
Dataset ID      : billing_export
Dataset location: US (or an approved location)
~~~

Verify billing is enabled on the export project and that it is linked to the proper billing account. The dataset must reside in a location supported by Billing export. If customer-managed encryption keys (CMEK) are required, check specific rules; do not assume every CMEK setup works out of the box.

### Step 2 — Open Billing export

1. Open [Billing Console](https://console.cloud.google.com/billing).
2. Select the **Billing account** to export.
3. Go to **Billing export** → **BigQuery export** tab.
4. Click **Enable standard usage cost export** or **Enable detailed usage cost export**.
5. Choose the prepared export project and destination dataset.
6. Confirm Billing Account ID, Project ID, Dataset ID, and export type, then click **Save**.

For Pricing, enable **Pricing data export** separately and verify its API/permission prerequisites. For FOCUS/CUD metadata, follow their separate setup docs as procedures and datasets differ from Standard/Detailed.

**Do not manually create the export table or run `bq load`**. Cloud Billing creates and writes to the table automatically after successful setup. Console labels/buttons may shift across versions; verify against official docs before operating in production.

### Step 3 — Wait for data and verify

- Standard/Detailed usage exports can take **several hours** before initial rows appear.
- During historical backfill into US/EU multi-regions, data exports chronologically and may take up to **five days** to catch up to recent usage.
- Pricing export can take up to **48 hours** to emit its first records; thereafter, pricing exports daily.
- There is no guarantee that usage data always exports within a fixed number of minutes.

In BigQuery Explorer, open the dataset and inspect the tables. If using an authenticated CLI with proper permissions:

~~~bash
# List datasets in the project (read-only)
bq ls --project_id=FINOPS_PROJECT_ID

# List tables inside the dataset (read-only)
bq ls FINOPS_PROJECT_ID:billing_export
~~~

If the table does not appear immediately after clicking Save, that alone is not proof of a broken config. Verify the Billing account/project/dataset and export status before toggling export off and on repeatedly.

## 5. Table names and core schema

Once data arrives in BigQuery, common table names include:

~~~text
gcp_billing_export_v1_<BILLING_ACCOUNT_ID>
gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>
cloud_pricing_export
gcp_billing_export_focus_<BILLING_ACCOUNT_ID>
cud_subscriptions_export
~~~

FOCUS and CUD metadata tables use separate creation flows/destinations. **Always copy the exact full table name from BigQuery Explorer**, because the formatted Billing Account ID inside the actual table ID may differ from how it displays in the Console UI.

| Standard/Detailed field | Meaning |
| --- | --- |
| `billing_account_id` | Billing account associated with the charge |
| `project.id`, `project.name` | Cost-generating project; may be missing on some rows |
| `service.description` | Service generating usage |
| `sku.description` | Billable SKU |
| `usage_start_time`, `usage_end_time` | Usage time interval |
| `invoice.month` | Invoice month in `YYYYMM` format |
| `cost` | Line-item charge in `currency`, before subtracting the row's credits |
| `credits` | Array of row credits/discounts; `credits.amount` is typically negative |
| `cost_type` | Row type: `regular`, `tax`, `adjustment`, `rounding_error` |
| `currency` | Currency of cost/credits |
| `labels`, `project.labels`, `tags` | Attributes supporting cost allocation |
| `location` | Geographic dimensions depending on SKU/service |
| `export_time` | Timestamp when the record was exported |

The **Detailed** table adds resource-level fields such as `resource.name` and `resource.global_name`. These fields **are not populated uniformly across all services and charge lines**.

**Invoice month differs from usage month:** Usage on the last day of a month can be billed on the following month's invoice; taxes and adjustments also follow distinct posting rules. Hence totals grouped by `DATE(usage_start_time)` can differ from totals grouped by `invoice.month`.

**Schema can evolve:** Google may add fields as export capabilities expand. For stable reporting, wrap required columns in a normalized view and avoid relying on `SELECT *` or altering Google-managed table structures.

## 6. Accurately calculating costs and credits

**Gross cost** is the sum of `cost` across selected rows. **Credits** are reductions attached to rows, such as Free Tier, promotional credits, or committed use discounts. **Net cost** in educational/analytical reports is typically computed as:

~~~text
net_cost = SUM(cost + sum of credits.amount per row)
~~~

Hypothetical single-currency example:

| Line item | Cost | Credits | Net |
| --- | ---: | ---: | ---: |
| Compute Engine | 100 | -20 | 80 |
| Cloud Run | 10 | -3 | 7 |
| Cloud Storage | 15 | None | 15 |
| **Total** | **125** | **-23** | **102** |

A row can have **multiple credits** or zero credits. Directly running `CROSS JOIN UNNEST(credits)` and then `SUM(cost)` duplicates `cost` for rows with two credits and can drop rows with zero credits.

To count each cost line exactly once, use a *scalar subquery*:

~~~sql
-- Sum of credits for a single row, returning 0 if there are no credits
IFNULL(
  (SELECT SUM(c.amount) FROM UNNEST(credits) AS c),
  0
)
~~~

This expression sums the credits array per row without multiplying rows. For financial reporting, agree on rounding rules, `cost_type` inclusions, and data cutoff timestamps; do not assume `net_cost` automatically equals final cash paid across all payment methods, taxes, or adjustments.

## 7. GoogleSQL queries for practice

The examples below use **Standard usage cost export** and are read-only. Before running, replace the table name with the **exact table path** copied from BigQuery Explorer. Example format:

~~~text
FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC
~~~

`ABCDEF_123456_789ABC` is strictly a placeholder. In BigQuery SQL, enclose the full table identifier in backticks. Use a single usage export table per aggregation; never union Standard and Detailed for the same sum.

### 7.1. How many rows exist and how fresh is the data?

~~~sql
SELECT
  COUNT(*) AS total_rows,
  MIN(usage_start_time) AS earliest_usage,
  MAX(usage_start_time) AS latest_usage,
  MAX(export_time) AS latest_export
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC`;
~~~

- `total_rows = 0`: usage may not have accrued yet or export was just enabled.
- `latest_usage`: newest usage timestamp present in the table; does not prove all services have finished reporting.
- `latest_export`: latest export timestamp in the records—useful for assessing freshness, not an update guarantee.

On large datasets, unfiltered queries can scan significant bytes. After initial verification, filter time windows or query pre-aggregated tables for routine checks.

### 7.2. Cost by project for a single invoice month

~~~sql
SELECT
  invoice.month AS invoice_month,
  COALESCE(project.id, '(no-project)') AS project_id,
  currency,
  ROUND(SUM(cost), 2) AS gross_cost,
  ROUND(
    SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS credits_total,
  ROUND(
    SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS net_cost
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC`
WHERE invoice.month = '202611'
GROUP BY invoice_month, project_id, currency
ORDER BY net_cost DESC;
~~~

Output explicitly separates **gross**, **credits**, and **net**. Do not ignore the `(no-project)` group: certain Billing-account-level charges do not belong to a single project. Currency stays in `GROUP BY` so USD and VND are never summed into a meaningless number.

### 7.3. Cost by usage day and service

~~~sql
SELECT
  DATE(usage_start_time, 'UTC') AS usage_day,
  service.description AS service_name,
  currency,
  ROUND(
    SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS net_cost
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC`
WHERE usage_start_time >= TIMESTAMP('2026-11-01 00:00:00+00')
  AND usage_start_time < TIMESTAMP('2026-12-01 00:00:00+00')
GROUP BY usage_day, service_name, currency
ORDER BY usage_day, net_cost DESC;
~~~

Here, dates are normalized to **UTC**. If internal reporting requires Vietnam time, switch to `DATE(usage_start_time, 'Asia/Ho_Chi_Minh')` and adjust the timestamp bounds consistently.

A report of "November usage" **does not necessarily** match "invoice month 202611" because usage timestamps and invoice posting periods can differ.

### 7.4. Top SKUs by net cost in a period

~~~sql
SELECT
  service.description AS service_name,
  sku.description AS sku_name,
  currency,
  ROUND(
    SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS net_cost
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC`
WHERE invoice.month = '202611'
  AND cost_type = 'regular'
GROUP BY service_name, sku_name, currency
ORDER BY net_cost DESC
LIMIT 30;
~~~

Filtering `cost_type = 'regular'` helps analyze usage SKUs. Because it **excludes** tax, certain adjustment, and rounding rows, do not use this top-SKU output to claim full invoice reconciliation.

### 7.5. Cost by project `team` label

Suppose projects carry a standard `team` label:

~~~sql
SELECT
  COALESCE(
    (SELECT ANY_VALUE(l.value)
     FROM UNNEST(project.labels) AS l
     WHERE l.key = 'team'),
    '(unassigned-team)'
  ) AS team,
  currency,
  ROUND(
    SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS net_cost
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC`
WHERE invoice.month = '202611'
GROUP BY team, currency
ORDER BY net_cost DESC;
~~~

This allocates by **project labels**, not all resource labels or tags. When the label is absent, rows fall into the unassigned bucket. When labels change, historical rows typically reflect the resource's state when usage was recorded rather than updating retroactively.

For reliable cost allocation, define which labels are mandatory, who owns them, how missing labels are handled, and what formula splits shared costs like networking or platform services.

### 7.6. Checking cost by resource using the Detailed table

With Detailed export, you can group by resource fields:

~~~sql
SELECT
  project.id AS project_id,
  service.description AS service_name,
  COALESCE(resource.name, '(no-resource-name)') AS resource_name,
  currency,
  ROUND(
    SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS net_cost
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_resource_v1_ABCDEF_123456_789ABC`
WHERE invoice.month = '202611'
GROUP BY project_id, service_name, resource_name, currency
ORDER BY net_cost DESC
LIMIT 50;
~~~

Run this only against the Detailed table and verify the actual schema. `resource.name` can be NULL if a service/SKU does not emit resource-level metadata. Never assume charges without a resource name are "unowned."

### 7.7. Reconciliation breakdown by invoice month and cost type

~~~sql
SELECT
  invoice.month AS invoice_month,
  cost_type,
  currency,
  ROUND(SUM(cost), 2) AS gross_cost,
  ROUND(
    SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS credits_total,
  ROUND(
    SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS net_cost
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC`
WHERE invoice.month = '202611'
GROUP BY invoice_month, cost_type, currency
ORDER BY cost_type;
~~~

This is a strong starting point for matching invoices because no `cost_type` is excluded. If numbers still differ from the statement, check billing account scope, export completeness, taxes, adjustments, corrections, currency conversions, rounding rules, and contract terms.

**Best practice:** Explicitly document whether every report uses *usage month* or *invoice month*, which currency, whether credits are deducted, and whether taxes/adjustments are included. Missing any one of these makes two individually accurate charts impossible to compare directly.

## 8. From export table to FinOps dashboard

A reporting pipeline can follow this flow:

~~~mermaid
flowchart TD
  RAW["Cloud Billing export table (Google-managed)"] --> VIEW["Normalized & access-controlled view"]
  VIEW --> DAILY["Summary table by day / project / service"]
  DAILY --> BI["Dashboards & recurring reports"]
  DAILY --> REVIEW["Cost review meetings"]
  REVIEW --> ACTION["Correlate metrics, optimize configs"]
~~~

### 8.1. Standardizing fields with a BigQuery view

The raw export table is written by Google and its schema can evolve as services expand. Instead of letting every dashboard query `SELECT *` directly, an internal view can standardize required columns.

The example below is **view-creation/replacement DDL**, so run it only after receiving write permissions on the reporting dataset and verifying the target:

~~~sql
CREATE OR REPLACE VIEW
  `FINOPS_PROJECT_ID.billing_reporting.v_cost_standard` AS
SELECT
  billing_account_id,
  invoice.month AS invoice_month,
  DATE(usage_start_time, 'UTC') AS usage_day_utc,
  project.id AS project_id,
  service.description AS service_name,
  sku.description AS sku_name,
  currency,
  cost_type,
  cost AS gross_cost,
  IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0) AS credit_amount,
  cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0) AS net_cost
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC`;
~~~

The `billing_reporting` dataset is an example that must be pre-created in a compatible location. For users restricted to a single team, use dataset-level permissions, authorized views, or row/column-level policies as appropriate. **Only create your own views/tables**—never modify the raw Google-managed Billing export table.

### 8.2. Scheduled queries for daily reporting

A live dashboard querying raw tables repeatedly can scan the entire history and incur unnecessary BigQuery charges. Periodic summary tables help, provided you design for:

- **Realistic latency:** e.g., reporting yesterday's spend; never label it "real-time."
- **Refresh window:** because late usage and adjustments can arrive afterward, recompute an appropriate rolling window instead of appending only the newest day.
- **Single source of truth:** one usage export table and one clear net-cost definition per report.
- **Data quality checks:** monitor latest export date, NULL project/team rows, currencies, and `cost_type` values.
- **Query cost control:** reduce refresh frequency, inspect dry-run bytes processed, and share materialized summary tables across dashboards.

### 8.3. Pairing with Cloud Billing budgets

Cloud Billing Budgets and alerts notify you when spending approaches thresholds by project, service, or supported scopes. BigQuery export helps **explain why**: which service/SKU rose, in which project/team, and how much credits offset it. If you want alerts triggered from SQL outputs, build a separate scheduled workflow with notification permissions. Do not assume enabling export alone gives you overspend alerts.

## 9. Limitations and protecting exported data

### 9.1. Export streams have latency and adjustments

Each service sends usage to Billing on its own cadence; export loads records periodically with no fixed delivery deadline. Period-end charges, corrections, and adjustments can appear after the usage timestamp. When publishing daily/monthly reports, display the **data freshness timestamp** and schedule final reconciliation after the invoice closes.

### 9.2. Never modify Google-managed tables

Google creates and manages the export table and schema. Avoid:

- Altering columns or recreating the export table with a custom schema.
- Running `INSERT`/`MERGE` of custom rows into the export table, even to "patch" a missing window.
- Deleting tables/rows and assuming Google will automatically backfill them again.
- Disabling export or switching destinations without assessing the resulting data gap.

If you need to merge history across an old and new dataset, **leave both source tables untouched** and build a separate reporting view/table using `UNION ALL` with time filters to eliminate overlaps and prevent duplicates.

### 9.3. Preserve the export service account's permissions

Cloud Billing automatically grants Google-managed service accounts access to write into your dataset. Depending on export type, documented principals currently include:

~~~text
billing-export-bigquery@system.gserviceaccount.com
cloud-account-pricing@cloud-account-pricing.iam.gserviceaccount.com
~~~

Removing these principals from the dataset can stop export updates and cause missing data. CUD metadata uses a separate linked-dataset flow and does not follow the exact same service-account pattern as Standard/Pricing.

### 9.4. Securing financial data

Export tables can expose project names, labels, resource names, SKUs, and contract-related pricing or credit details. Make sure to:

1. Grant read access to raw tables strictly on a need-to-know basis.
2. Create filtered views/reports per application team when needed.
3. Control query-job creation permissions and BigQuery spend.
4. Never commit billing exports to public repositories or send them over unapproved channels.
5. Define retention, access auditing, and storage locations per corporate policy.
6. Review IAM whenever staff change teams or applications switch billing accounts.

### 9.5. FOCUS and long-term retention management

FOCUS is an option for FinOps standardization with its own schema and lifecycle. If your organization requires more than two years of historical reporting, note the **two-year TTL on Google-provided FOCUS tables** per current documentation and maintain long-term copies in organization-owned tables where permitted. Standard/Detailed tables have different policies and constraints; review each export type rather than applying one TTL assumption to all.

## 10. Troubleshooting common issues

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Unable to enable export | Missing Billing account or BigQuery project permissions | Check IAM for the exact **export type** and active signed-in account |
| `Invalid dataset region` | Location unsupported by Cloud Billing export | Choose another dataset in a supported location |
| Dataset not visible during setup | Wrong project, permissions, or billing link | Verify Billing Account ID, project, and IAM |
| Table not visible right after Save | Export pipeline initializing | Check export status and wait per docs; avoid toggling off/on |
| Table exists, missing recent days | Usage latency or backfill in progress | Check `MAX(export_time)`, `MAX(usage_start_time)`, and refresh schedule |
| Missing costs before enablement date | Regional dataset used, destination changed, or export previously disabled | Review backfill policy by location and setup history |
| Pricing export still empty | BigQuery Data Transfer Service API disabled or missing permissions | Verify API/IAM and up to 48-hour initialization window |
| Data stopped updating after IAM change | Export writer service account lost permissions | Check dataset access and Billing export status |
| SQL throws `Access Denied` | Missing table read or query-job permission | Check dataset IAM and execution project IAM |
| Cost totals doubled | Combining Standard + Detailed or `JOIN` on credits multiplying rows | Query a single usage table; sum credits via scalar subquery |
| Invoice total differs from usage report | Different time basis, currency, tax, adjustment, or delayed data | Compare `invoice.month` and `cost_type`; check invoice period |
| High BigQuery query cost | Full-table scans or frequent dashboard refreshes | Limit time range, check bytes processed, and use summary tables |

Diagnostic flow:

~~~text
Correct Billing Account ID?
  ↓
Correct export type, project, dataset, and location?
  ↓
Sufficient IAM, BigQuery API, and additional APIs?
  ↓
Table created, populated, and how fresh is it?
  ↓
Query uses correct schema, timeframe, currency, and cost type?
  ↓
Credits aggregated without multiplying rows?
  ↓
Data reconciled against Billing Console / invoice?
~~~

If data is missing, **do not reflexively disable and re-enable export as a first step**: doing so can create an additional gap in exported data. Before changing destinations, plan how to preserve history and unify old/new tables in a separate reporting layer.

## 11. Real-world scenario: controlling costs for an order-processing system

An engineering group manages three projects under one Billing account:

- `orders-dev`: testing Cloud Run APIs and Cloud Storage.
- `orders-prod`: production app with Cloud Run, Cloud SQL, Pub/Sub, and load balancing.
- `analytics-prod`: data pipelines and BigQuery.

The team needs visibility into development vs. production costs, which services/SKUs are climbing, and whether to optimize sizing. They can establish this workflow:

1. Designate `finops-admin` as the export project and grant appropriate analytics permissions.
2. Enable **Standard usage cost export** to capture data by project, service, SKU, invoice month, and credits.
3. Run reports by `invoice.month` for accounting; run reports by `usage_start_time` for operational trends.
4. Standardize `team` and `env` labels and track unowned costs.
5. Identify top cost-driving SKUs while carefully checking `cost_type`, currency, and data latency.
6. Correlate with Cloud Monitoring, logs, and release history to confirm root causes.
7. Enable Detailed when supported resource-level investigation is needed; use GKE cost allocation if GKE granularity is required.
8. Monitor budgets and measure savings after every technical change.

Example investigation hypotheses:

| Cost signal | Hypothesis to verify | Supplemental data sources |
| --- | --- | --- |
| Cloud Run spikes | Traffic growth, min instances, concurrency, or mis-sized CPU/memory | Cloud Run metrics, traffic, revision configs |
| Cloud SQL rises | Instance tier/HA, storage, backups, or networking | Cloud SQL metrics, instance & backup configs |
| Network egress grows | Internet traffic or cross-region connections | Networking SKUs, VPC, traffic paths |
| Unallocated GKE costs | Cost allocation disabled or missing labels | Detailed export, GKE allocation, and labels |
| FinOps BigQuery costs rise | Dashboard queries scanning excessive bytes | BigQuery job history, bytes processed |

Billing tables alone show **where costs increased**, not the technical root cause. Always cross-reference metrics, architectural changes, and release timelines.

### 11.1. Documenting optimization decisions

~~~text
Issue: Cloud Run costs in orders-prod climbed over two weeks
Evidence: Daily usage query, service, SKU, credits, and currency
Hypothesis: Higher traffic or altered instance/revision configuration
Further verification: Request count, p95 latency, min instances, logs
Plan: Tune concurrency or resource sizing after load testing
Risk: Performance/reliability degradation if over-trimmed
Evaluation: Cost/request and SLOs post-change
Owner: API team; next review date: ...
~~~

Cost reductions must be evaluated alongside availability, latency, resilience, and security. Never pick an option solely for a lower headline bill.

## 12. Lab exercise: exporting Standard usage cost and building reports

**Objective:** Set up Standard export, verify ingested data, and build cost reports by project, service, and invoice.

**Prerequisites:** IAM permissions on the billing account and export project, dataset in a valid location, and an approved BigQuery budget. Learners without configuration rights can complete the SQL portion on a read-only demo dataset.

### Part A — Setup

1. Record Billing Account ID, export Project ID, Dataset ID, location, and enablement date.
2. Choose Standard export and explain why Detailed is not needed initially.
3. Verify the project links to the right Billing account, IAM roles, and BigQuery API.
4. In Billing Console → Billing export → BigQuery export, enable and save Standard export.
5. Once the table appears, copy its exact table ID from BigQuery Explorer.
6. Run the verification query checking row count, earliest/latest usage, and export time.

### Part B — SQL analysis

Using the queries from Section 7, substitute your actual table ID and month:

- **By project:** Gross, credits, and net cost within the same invoice month.
- **By service/SKU:** Top usage costs and `cost_type` filters.
- **By day:** Usage-date cost trend with an explicitly stated timezone.

Write an explanation of potential variances across totals: differing scopes, invoice vs. usage time, taxes/adjustments, credits, delayed ingestion, currency, or unallocated spend.

### Part C — Quality report

| Question | Evidence to retain |
| --- | --- |
| When does data start? | Enablement date, location, and earliest usage timestamp |
| When was the latest export? | `MAX(export_time)` and verification timestamp |
| Which projects lack a `team` label? | List and cost of unlabeled projects |
| Does SQL calculate credits accurately? | Scalar subquery formula without row multiplication |
| Are taxes and adjustments included? | List of filtered/retained `cost_type` values |
| Does the report use invoice or usage time? | Field name, period, and timezone |
| Who can view the report? | IAM scope and security requirements |
| Is BigQuery exceeding expected cost? | Bytes scanned, refresh cadence, and budget |

### Part D — Scenario question

Suppose `orders-prod` spend increases while top SKUs show rising network egress. Provide at least **two hypotheses**, **three data points to collect for confirmation**, and **one post-optimization measurement**. Do not infer root cause from dollar amounts alone.

## 13. Self-check questions

1. Does Standard/Detailed export record data only for the project hosting the dataset, or for all projects under the Billing account?
2. When is Detailed needed instead of Standard?
3. Why is summing both Standard and Detailed incorrect?
4. How does enabling export for the first time in a US/EU multi-region differ from a supported single region regarding historical backfill?
5. Why does Pricing export require the BigQuery Data Transfer Service API?
6. For what reasons can `invoice.month` differ from the month of `usage_start_time`?
7. Why can a direct `JOIN` on `UNNEST(credits)` distort `SUM(cost)`?
8. Why must `cost_type` and `currency` be preserved during reconciliation?
9. How does changing the destination dataset affect historical data?
10. Why should you not grant every team read access to the company-wide raw export table?

**Hints:** (1) across the Billing account; (2) when supported resource-level details are needed; (3) duplicates usage; (4) multi-region can backfill from the start of the prior month on initial enablement, while single regions start from the enablement date; (5) Pricing-specific prerequisite; (6) delayed usage reporting, corrections/adjustments; (7) duplicates rows or drops zero-credit rows; (8) avoids mixing currencies, taxes, and regular usage; (9) does not automatically backfill history to the new destination; (10) broad financial data requires strict access control.

## 14. Checklist before using reports for decisions

- [ ] Verified Billing Account ID, export project, dataset, and export type.
- [ ] Checked IAM, BigQuery API, and Pricing-specific APIs.
- [ ] Location aligns with data policy and backfill limits are understood.
- [ ] Table contains data and freshness/latency is known.
- [ ] Single usage table used as total source to prevent double counting.
- [ ] SQL computes credits safely per row.
- [ ] Dashboards explicitly state invoice month vs. usage time, timezone, and currency.
- [ ] `cost_type` filters and adjustment handling are disclosed.
- [ ] NULL project/team rows and unallocated spend are handled.
- [ ] Google-managed tables remain untouched; reporting lives in separate views/tables.
- [ ] IAM, retention, audit, and invoice reconciliation processes are in place.
- [ ] Budget monitors BigQuery costs and optimization outcomes.

## 15. Official documentation

The following pages are updated by Google Cloud for products, schemas, and feature support; check current versions before production rollout:

- [Export Cloud Billing data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery) — overview and export types.
- [Set up Cloud Billing data export to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-setup) — IAM, APIs, datasets, locations, backfill.
- [Understand Cloud Billing data tables](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables) — auto-created tables, export schedule, and limits.
- [Standard usage cost schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage) — fields, invoices, credits, taxes/adjustments.
- [Detailed usage cost schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage) — resource-level metadata.
- [Example queries for Billing export](https://docs.cloud.google.com/billing/docs/how-to/bq-examples) — sample SQL queries.
- [Cloud Billing budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets) — budgets and notifications.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) — query/storage pricing.
- [GKE cost allocation](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cost-allocations) — extending GKE cost breakdown.

**Key takeaway:** Reliable FinOps reporting flows from **enabling the right export → understanding schema, latency, and location → calculating costs/credits accurately → allocating by project/team → verifying and optimizing**. The goal is to bring cost into architectural decisions alongside security, reliability, and performance.
