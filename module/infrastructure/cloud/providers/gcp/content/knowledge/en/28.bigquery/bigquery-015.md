# Hands-On Data Warehouse and Cost Analysis Dashboard

> **Chapter:** BigQuery  
> **Module:** CLOUD_PROVIDERS_GCP

An operations team manages multiple Google Cloud projects: APIs run on Cloud Run, analytics use BigQuery, data lives in Cloud Storage, and several workloads run on GKE. Cloud Billing Reports show total spend and high-level trends, yet the team needs deeper answers: **which service spiked this week, which project exceeded its budget, what is net cost after credits, and which `cost_center` labels are still missing?** This lesson builds a cost analytics pipeline following **Cloud Billing export → BigQuery → SQL views → Looker Studio (Data Studio) dashboard**.

This hands-on lesson belongs to the **CLOUD_PROVIDERS_GCP** module, connecting project/IAM organization, VPCs, Compute Engine, GKE, Cloud Run, and databases with reliability operations and cost control. The goal is **understanding the numbers and building a reconcilable dashboard**, not merely drawing pretty charts. All project names, datasets, billing accounts, and monetary figures in examples are **illustrative**.

**After this lesson, you will be able to:**

1. Choose the right Cloud Billing export type (**Standard**, **Detailed**, **Pricing**, **CUD metadata**) and know when resource-level data is required.
2. Create a dataset in a supported location and enable exports with appropriate IAM and budgets.
3. Interpret `cost`, `credits`, `invoice.month`, `usage_start_time`, `cost_type`, `project`, `service`, `sku`, `labels`, and `export_time`.
4. Write BigQuery SQL that **does not double-count costs** when unnesting repeated credits/labels.
5. Create standardized views and a daily-cost mart for dashboard reuse.
6. Design KPIs by project/service/day, dashboard filters, and an unallocated-cost breakdown.
7. Separate **usage costs** from **invoice totals**; reconcile taxes, adjustments, credits, and late-arriving data.
8. Keep the reporting pipeline itself inexpensive using dry runs, maximum bytes billed, partitioning/clustering, and sensible refresh rates.
9. Scope viewer permissions safely, and test a lab with synthetic data when you lack real billing access.

## 1. Target Architecture

~~~mermaid
flowchart LR
  CLOUD["Google Cloud services\nusage + charges"] --> BILL["Cloud Billing account"]
  BILL -->|"Managed export"| RAW["BigQuery dataset\nbilling_raw\nStandard/Detailed"]
  RAW -->|"SQL, schema checks"| VIEW["billing_mart\nv_cost_lines"]
  VIEW --> DAILY["v_daily_cost\nv_invoice_cost"]
  DAILY --> BI["Looker Studio / Data Studio\nCost Dashboard"]
  DAILY --> ALERT["Scheduled check / report\nthresholds and anomalies"]
  RAW --> QA["Reconciliation\nCloud Billing Reports/Invoice"]
~~~

**Three layers to separate:**

| Layer | Ownership | Function | Rule |
| --- | --- | --- | --- |
| **Raw export** | Managed writes by Cloud Billing | Raw cost/credit records; can receive late updates | Never manually edit/delete rows; do not expose broadly to dashboards |
| **Semantic/mart** | Analytics / FinOps team | Standardizes metrics/dimensions and net cost after credits | Maintain SQL versioning, tests, and clear KPI definitions |
| **Presentation** | BI team | Charts, filters, tables, refresh schedules | Read only explicitly authorized tables/views |

**Do not treat BigQuery as a spending blocker:** dashboards are for visibility and decision-making. **Cloud Billing Budgets**, quotas, policies, and resource scale-down/shutdown runbooks drive actual overspend response. Budget alerts are not hard spending caps.

## 2. Choosing the Right Cloud Billing Export

| Export Type | Typical Table / Dataset | When to Use |
| --- | --- | --- |
| **Standard usage cost** | `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>` | Trend dashboards by day, project, service/SKU, and credits |
| **Detailed usage cost** | `gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>` | **Resource-level** cost investigation; tables can be much larger |
| **Pricing** | `cloud_pricing_export` | Look up SKU/account pricing and model price changes |
| **CUD metadata** | Export-generated metadata tables | Analyze Committed Use Discount allocation and utilization |
| **FOCUS usage** | FOCUS export via Google-provided mechanism/dataset | Multi-cloud FinOps standardization; check availability/schema separately |

Examples here use the **Standard usage export** because it suffices for overview dashboards and typically lowers query costs compared to Detailed. To build a "Top 20 most expensive Compute Engine instances" table, enable **Detailed**; Standard **lacks** full resource-level identifiers. Never sum Standard and Detailed together: both report the same usage, causing **double counting**.

### 2.1. An Export Table Is Not a Static Invoice

- Data exports **periodically**, with no real-time streaming latency SLA.
- Services report usage at different cadences; the latest hours may be incomplete.
- Adjustments, taxes/rounding, or committed-use credits can arrive late.
- `export_time` records when the row was exported—**not** when the service was consumed.
- Schemas can gain new fields over time; expose a **view** as a stable contract for dashboards.

### 2.2. Location Choice Affects Backfill

Per Cloud Billing export documentation, for Standard/Detailed/FOCUS:

- Datasets in **US/EU multi-regions** can receive **backfilled data for the current month and prior month** when first enabled; backfilling can take several days.
- Datasets in a **supported single region** receive data only from the export enablement date forward, with **no historical backfill**.
- Exports support only a specific list of regions; **do not create a dataset in an arbitrary region assuming export will accept it**.
- Pricing exports do not backfill like usage exports.

Select the region based on data residency policies and historical backfill requirements **before** enabling export. Switching the export dataset later does not automatically migrate old rows into the new dataset.

## 3. Preparing the Project, IAM, Datasets, and Export Source

### 3.1. Lab Model

| Item | Illustrative Value |
| --- | --- |
| Cloud Billing account | `XXXXXX-XXXXXX-XXXXXX` |
| BigQuery project | `LAB_BILLING_PROJECT` |
| Raw dataset | `billing_raw` |
| Mart dataset | `billing_mart` |
| Location | `US` (illustrative; verify data residency) |
| Standard table | `gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX` |
| Standardized view | `billing_mart.v_cost_lines` |
| Daily view | `billing_mart.v_daily_cost` |
| Invoice view | `billing_mart.v_invoice_cost` |
| Dashboard | `Cloud Cost Overview – Lab` |

**Security note:** Billing data can reveal project structure, resource inventories, and operational strategy. Use only an authorized **lab project/billing account**. If you lack Cloud Billing permissions, use the synthetic data in Section 11—**never request Billing Admin rights just to complete this exercise**.

### 3.2. Permission Requirements

- Enabling **usage cost** export generally requires **Billing Account Costs Manager or Billing Account Administrator** on the billing account, plus **BigQuery User** on the dataset project.
- Enabling **pricing/CUD metadata** requires higher roles; per documentation, this includes Billing Account Administrator, BigQuery Admin, and appropriate project update permissions.
- Creating datasets/tables/views requires appropriate BigQuery IAM; running SQL requires `bigquery.jobs.create` and read access on the referenced tables/views.
- Cloud Billing adds an **export service account** to the dataset to write rows. **Never delete or revoke** that binding when hardening IAM.
- Dashboard viewers only need read access to the **mart** and query execution under Data Studio's credential mode—never default access to raw billing tables.

Do not grant broad `roles/owner` or `roles/editor` just to fix a dashboard viewer error. Protect raw billing using a dedicated project/dataset, authorized views, or restricted aggregate tables.

### 3.3. Creating Datasets in the Lab Project

**Read-only checks before making changes:**

~~~bash
gcloud config get-value project
gcloud billing accounts list
bq ls --project_id=LAB_BILLING_PROJECT
~~~

The commands below **create datasets and may incur charges**; run only in an approved lab project. `US` is illustrative—switch to a Cloud Billing-supported location permitted by your policy:

~~~bash
bq --location=US mk --dataset LAB_BILLING_PROJECT:billing_raw
bq --location=US mk --dataset LAB_BILLING_PROJECT:billing_mart

bq show --format=prettyjson LAB_BILLING_PROJECT:billing_raw
bq show --format=prettyjson LAB_BILLING_PROJECT:billing_mart
~~~

**Do not create the Standard export table manually.** Once Cloud Billing export is enabled, Google Cloud automatically creates `gcp_billing_export_v1_...` inside the target dataset.

### 3.4. Enabling Export in Google Cloud Console

1. Open **Billing → Billing export → BigQuery export** and select the right billing account.
2. Click **Enable standard usage cost export**.
3. Select project `LAB_BILLING_PROJECT` and dataset `billing_raw`, then confirm.
4. If resource-level breakdowns are needed, enable **Detailed usage cost export** separately instead of expecting Standard to carry resource IDs.
5. Check the BigQuery tab to confirm the table appears; note the earliest data date and backfill window.
6. Audit the Billing export configuration, BigQuery IAM, and Billing Budgets; document dashboard ownership.

**Wait for real data to populate** before validating numbers; never create a dummy table and mistake it for real billing records. One billing account can pay for **multiple projects**—the export contains charges across all linked projects, not just the project hosting BigQuery.

## 4. Understanding the Schema Before Writing SQL

Key fields of the **Standard usage cost export**:

| Field | Type / Meaning | Caveat |
| --- | --- | --- |
| `billing_account_id` | Billing account generating the export | Can span multiple projects |
| `invoice.month` | Invoice month, `YYYYMM` format | **Can differ from usage month** |
| `usage_start_time` | Start of usage window (`TIMESTAMP`) | Not when the row was exported |
| `export_time` | Timestamp when Billing exported the row | Useful for freshness checks |
| `project.id`, `project.name` | Project incurring the charge | May be `NULL` for unattributed charges |
| `service.id/description` | Service, e.g., BigQuery | Group stably by ID when needed |
| `sku.id/description` | Specific usage SKU | One service has many SKUs |
| `cost` | Line item cost **before credits** | Not the final payable net amount |
| `credits` | **`ARRAY`** of credits with `amount`, type, etc. | Can be empty or hold multiple elements |
| `cost_type` | `regular`, `tax`, `adjustment`, `rounding_error` | Do not mix blindly into usage trends without context |
| `currency` | Billing account currency | **Never sum USD and VND together** |
| `labels`, `project.labels`, `tags` | Cost allocation metadata | Can be missing, delayed, or multi-valued |

**Net cost formula:**

\[
\text{Net cost} = \sum \text{cost} + \sum \text{credits.amount}
\]

In standard exports, `credits.amount` is typically negative, so you **add** credits rather than subtracting them again. For example, `cost = 120` with `credits = [-20, -10]` yields net = 90 (in the same currency).

### 4.1. Three Different "Dates/Months"

| Timestamp / Date | Example | Question Answered |
| --- | --- | --- |
| `DATE(usage_start_time)` | 2026-11-01 | On what date were resources consumed? |
| `invoice.month` | `202611` or `202612` | On which monthly invoice was the row billed? |
| `export_time` | 2026-11-04 08:10 UTC | When was the record exported/updated? |

Usage at the end of November can appear on December's invoice; never compare **November usage** totals against the **November invoice** and claim an "invoice error." Also standardize **timezones**: UTC vs. `Asia/Ho_Chi_Minh` shifts rows across day boundaries.

### 4.2. Watch Out for Nested Arrays

Suppose **one row** has `cost=100` and two credits `-10`, `-5`. The query below is **wrong**:

~~~sql
-- WRONG: UNNEST can duplicate the parent row.
SELECT SUM(cost)
FROM `LAB_BILLING_PROJECT.billing_raw.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`,
UNNEST(credits) AS c;
~~~

Unnesting into two rows turns `SUM(cost)` into 200 instead of 100, and rows with empty credits can be dropped completely. **Correct pattern:** sum credits **per row inside a scalar subquery**, then aggregate.

## 5. Creating a Standardized View: One Source Row → One Analytical Row

Create `billing_mart.v_cost_lines` over the **Standard** export. Replace the export table name with your actual table from Explorer; do not run this SQL unless authorized to read billing data.

~~~sql
-- BigQuery GoogleSQL; create view in the same location as the source.
CREATE OR REPLACE VIEW
  `LAB_BILLING_PROJECT.billing_mart.v_cost_lines` AS
SELECT
  billing_account_id,
  DATE(usage_start_time, "Asia/Ho_Chi_Minh") AS usage_date,
  invoice.month AS invoice_month,
  usage_start_time,
  export_time,
  currency,
  COALESCE(project.id, "UNATTRIBUTED") AS project_id,
  COALESCE(project.name, "Unknown project") AS project_name,
  service.id AS service_id,
  service.description AS service_name,
  sku.id AS sku_id,
  sku.description AS sku_name,
  cost_type,
  CAST(cost AS NUMERIC) AS gross_cost,
  COALESCE(
    (SELECT SUM(CAST(c.amount AS NUMERIC))
     FROM UNNEST(credits) AS c), 0
  ) AS credit_amount,
  CAST(cost AS NUMERIC) + COALESCE(
    (SELECT SUM(CAST(c.amount AS NUMERIC))
     FROM UNNEST(credits) AS c), 0
  ) AS net_cost,
  COALESCE(
    (SELECT l.value FROM UNNEST(labels) AS l
     WHERE l.key = "cost_center" LIMIT 1),
    (SELECT p.value FROM UNNEST(project.labels) AS p
     WHERE p.key = "cost_center" LIMIT 1),
    "unallocated"
  ) AS cost_center
FROM
  `LAB_BILLING_PROJECT.billing_raw.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`;
~~~

**Why use a view?** It encapsulates net cost math, column aliases, and label fallback rules so every KPI shares one definition. When the export adds or shifts fields, update one view instead of ten charts. Note that a view **does not cache data or reduce scan cost on its own**: queries through the view still scan the underlying source table.

**Two important notes:**

- `cost_center` here prefers **resource labels**, then **project labels**, falling back to `unallocated`. If teams use identical label keys with inconsistent meanings, standardize the taxonomy first.
- Labels can be applied after usage occurred or be unsupported on certain SKUs; **`unallocated` does not automatically mean a team misspent**. Invoice taxes/adjustments often lack projects/cost centers and require separate internal allocation rules.

### 5.1. Daily Summary View for Operations Dashboards

~~~sql
CREATE OR REPLACE VIEW
  `LAB_BILLING_PROJECT.billing_mart.v_daily_cost` AS
SELECT
  usage_date,
  currency,
  project_id,
  project_name,
  service_id,
  service_name,
  cost_center,
  SUM(gross_cost) AS gross_cost,
  SUM(credit_amount) AS credits,
  SUM(net_cost) AS net_cost
FROM `LAB_BILLING_PROJECT.billing_mart.v_cost_lines`
WHERE cost_type = "regular"
GROUP BY 1, 2, 3, 4, 5, 6, 7;
~~~

`v_daily_cost` tracks **regular usage charges** (excluding tax, adjustments, and rounding) so operations dashboards stay clear. It is **not the payable invoice total**. If an organization uses multiple currencies, **always group by `currency`** and use separate scorecards/currency filters, or convert using an approved exchange-rate policy.

### 5.2. Invoice Total View for Reconciliation

~~~sql
CREATE OR REPLACE VIEW
  `LAB_BILLING_PROJECT.billing_mart.v_invoice_cost` AS
SELECT
  invoice_month,
  currency,
  cost_type,
  SUM(gross_cost) AS gross_cost,
  SUM(credit_amount) AS credits,
  SUM(net_cost) AS net_cost
FROM `LAB_BILLING_PROJECT.billing_mart.v_cost_lines`
GROUP BY 1, 2, 3;
~~~

**Purpose:** preserves `regular`/`tax`/`adjustment`/`rounding_error` separately for invoice reconciliation. When micro-unit precision (*micros*) is required, follow Google's sample pattern converting `cost`/`credits` to micro-units before summing to prevent floating-point drift; final reconciliation must also account for invoice rules and credit types.

### 5.3. Spot-Check a Few Rows Without Blindly Counting

~~~sql
-- Verify the table/view is readable and key fields populate properly
SELECT
  usage_date, invoice_month, project_id, service_name,
  currency, gross_cost, credit_amount, net_cost
FROM `LAB_BILLING_PROJECT.billing_mart.v_cost_lines`
WHERE usage_date >= DATE "2026-11-01"
  AND usage_date < DATE "2026-12-01"
LIMIT 20;
~~~

On an **unpartitioned** table, `LIMIT 20` usually **does not reduce bytes scanned**. Before running against a large billing export, use free **Preview**, run a dry run, and enforce maximum bytes billed. Cost optimization is covered in Section 9.

## 6. Practical KPI Queries

### 6.1. Top Projects and Services in a Usage Month

~~~sql
SELECT
  currency, project_id, service_name,
  ROUND(SUM(net_cost), 2) AS net_cost
FROM `LAB_BILLING_PROJECT.billing_mart.v_daily_cost`
WHERE usage_date >= DATE "2026-11-01"
  AND usage_date < DATE "2026-12-01"
GROUP BY 1, 2, 3
ORDER BY net_cost DESC
LIMIT 15;
~~~

**Never add amounts across different currencies.** If `project_id = UNATTRIBUTED`, do not automatically blame the project hosting the billing export—it represents charges without a project ID.

### 6.2. 7-Day Cost Trend by Service

~~~sql
SELECT
  usage_date, currency, service_name,
  ROUND(SUM(net_cost), 2) AS daily_net_cost
FROM `LAB_BILLING_PROJECT.billing_mart.v_daily_cost`
WHERE usage_date BETWEEN DATE "2026-11-12" AND DATE "2026-11-18"
GROUP BY 1, 2, 3
ORDER BY usage_date, service_name;
~~~

Compare against the prior 7 days when investigating growth. Higher absolute spend can reflect healthy traffic growth; to measure **efficiency**, pair cost with unit metrics such as requests, GB processed, or orders.

### 6.3. Unallocated Cost Ratio

~~~sql
SELECT
  currency,
  ROUND(SUM(IF(cost_center = "unallocated", net_cost, 0)), 2)
    AS unallocated_net_cost,
  ROUND(SUM(net_cost), 2) AS total_net_cost,
  SAFE_DIVIDE(
    SUM(IF(cost_center = "unallocated", net_cost, 0)),
    NULLIF(SUM(net_cost), 0)
  ) AS unallocated_ratio
FROM `LAB_BILLING_PROJECT.billing_mart.v_daily_cost`
WHERE usage_date >= DATE "2026-11-01"
  AND usage_date < DATE "2026-12-01"
GROUP BY currency;
~~~

`SAFE_DIVIDE` prevents division by zero. If large credits make net cost negative, this ratio **falls outside 0–100%**; in that case, use gross usage cost or a documented allocation denominator in the KPI definition.

## 7. Looker Studio (Data Studio) Dashboard: From SQL View to Charts

**Data Studio** is the name used in current BigQuery connection docs; many teams call it **Looker Studio**. Both names here refer to the same BI reporting tool connecting to BigQuery—**not** Looker (Google Cloud core) with LookML.

### 7.1. Configuring the Data Source

1. Open Looker Studio/Data Studio and choose **Report → Add data**.
2. Select the **Google BigQuery** connector.
3. Choose **Project → Dataset `billing_mart` → View `v_daily_cost`**. You can use **Custom Query**, though testing SQL directly in BigQuery first is safer.
4. Choose the **billing project** paying for query execution and a credential mode matching policy.
5. Verify field types: `usage_date` as Date; `net_cost`, `gross_cost`, `credits` as numeric/currency; `currency` as dimension.
6. Share the report with scoped viewers and test using an account lacking raw export permissions.

**Least privilege:** Querying requires `bigquery.jobs.create` on the execution project plus read permissions on target views/tables. If viewers should not access raw rows, use **authorized views** or **scoped aggregate tables** rather than granting Data Viewer across all of `billing_raw`. Using **Owner's credentials** on a data source lets viewers see results their own accounts cannot query directly—treat it as an authorization decision, not a cosmetic toggle.

### 7.2. Suggested Dashboard Layout

~~~text
┌───────────────────── Cloud Cost Overview ─────────────────────┐
│ Date range   Project   Service   Cost center   Currency       │
├────────────────┬────────────────┬────────────────────────────┤
│ Net usage cost │ Gross usage    │ Credits                    │
├────────────────┴────────────────┴────────────────────────────┤
│ Line chart: Daily net cost (by usage_date)                    │
├───────────────────────────┬───────────────────────────────────┤
│ Bar: Top 10 services      │ Bar: Top 10 projects              │
├───────────────────────────┴───────────────────────────────────┤
│ Table: Project × Service × Cost center × Net cost             │
├───────────────────────────────────────────────────────────────┤
│ Unallocated cost + Notes: export delay, invoice != usage      │
└───────────────────────────────────────────────────────────────┘
~~~

| Component | Dimension | Metric | Question Answered |
| --- | --- | --- | --- |
| Scorecard "Net usage cost" | Date range + currency | `SUM(net_cost)` | Operating cost after credits |
| Scorecard "Gross" | Date range + currency | `SUM(gross_cost)` | Cost before credits |
| Scorecard "Credits" | Date range + currency | `SUM(credits)` | Total applied credits |
| Time series | `usage_date` | `SUM(net_cost)` | Which day spiked unexpectedly? |
| Top services | `service_name` | `SUM(net_cost)` | Which services drive the most spend? |
| Top projects | `project_id` | `SUM(net_cost)` | Which projects need investigation? |
| Cost center table | `cost_center` | `SUM(net_cost)` | How much remains unallocated? |

**Label charts accurately:** Name this scorecard **Net usage cost**, not "Invoice due," because the daily view excludes `tax/adjustment/rounding` and groups by usage date. Build a **separate Invoice Reconciliation page** backed by `v_invoice_cost`, filtered by `invoice_month`, displaying all cost types.

### 7.3. Filters and Formatting

- Add a **Date range control** on `usage_date`, defaulting to "Last 30 days" or an approved window.
- Add dropdown filters for `project_id`, `service_name`, `cost_center`, and `currency`.
- Display currency clearly in metrics/titles. Never show `$` on VND figures.
- Keep "Unknown/unallocated" visible in charts to highlight tagging gaps instead of filtering it out.
- For top-N charts, provide a **full detail table and CSV export** (subject to IAM) for investigators.
- Set sensible refresh/cache intervals; never auto-refresh dashboards every few seconds when Billing exports lack real-time SLAs.

## 8. Reconciling Numbers Before Sharing

**A dashboard is trustworthy only when its metric definitions and reporting periods reconcile against official billing.**

### 8.1. Keep Two Views Separate

- **Usage cost dashboard:** grouped by `usage_date`, focused on `cost_type="regular"`. Used to analyze trends, workload impact, and cost centers.
- **Invoice reconciliation:** grouped by `invoice.month`, including `regular`/`tax`/`adjustment`/`rounding_error` and matching credits. Compared against Cloud Billing invoices/Reports in the same currency and billing account.

The table below is a **synthetic** example, not real amounts:

| Line Item | Usage Month | Invoice Month | Cost Type | Gross | Credits | Net |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Compute Engine usage | 202611 | 202611 | regular | 120.00 | -20.00 | 100.00 |
| End-of-month BigQuery usage | 202611 | 202612 | regular | 10.00 | 0.00 | 10.00 |
| Invoice tax | — | 202611 | tax | 5.00 | 0.00 | 5.00 |
| Adjustment | 202610 | 202611 | adjustment | -2.00 | 0.00 | -2.00 |

**Result:** November Usage (regular) = 110.00; November Invoice (all cost types shown) = 103.00; **both are legitimately different** due to invoice cutoffs, taxes, and adjustments. Never "fix" discrepancies by forcing mismatched periods to equal each other.

### 8.2. Reconciliation Workflow

1. Match **billing account, currency, invoice month, timezone, and filters** to Cloud Billing Reports.
2. Compare **gross, credits, and net** broken down by `cost_type`.
3. Check export completeness using `MAX(export_time)` and latest usage timestamps; remember a recent `export_time` does not guarantee every product has finished reporting.
4. Inspect `project_id IS NULL` rows, adjustments, and rounding entries before allocating costs.
5. With CUDs, distinguish **commitment fees**, **credits**, and cost-allocation options; never double-add or double-subtract credits.
6. Document variances and explanations; once issued, the **invoice is the authoritative payment reference**.
7. Run this check as a repeatable monthly routine rather than tweaking dashboard numbers manually.

### 8.3. Checking Data Freshness

~~~sql
SELECT
  currency,
  MAX(export_time) AS last_export_time,
  MAX(usage_start_time) AS latest_usage_start,
  COUNT(*) AS rows_seen
FROM
  `LAB_BILLING_PROJECT.billing_raw.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
GROUP BY currency;
~~~

This query is read-only yet **incurs query charges**. When a view/mart refreshes on a schedule, distinguish the source's `last_export_time` from the mart's `last_mart_refresh_time`; never present dashboards as "live billing."

## 9. Preventing the Dashboard from Creating a Huge Bill

Every dashboard load, filter change, or refresh can trigger BigQuery queries. On a large raw export, querying through a view scans the raw table repeatedly and can get expensive. Manage **the cost of the cost-analytics system itself**.

### 9.1. Dry Run and Maximum Bytes Billed

~~~bash
# Estimate only; does not execute the real query
bq query \
  --project_id=LAB_BILLING_PROJECT \
  --use_legacy_sql=false \
  --dry_run \
  'SELECT COUNT(*) FROM `LAB_BILLING_PROJECT.billing_mart.v_daily_cost`'

# Execute with a 1 GiB billed-bytes cap (rejected if exceeded)
bq query \
  --project_id=LAB_BILLING_PROJECT \
  --use_legacy_sql=false \
  --maximum_bytes_billed=1073741824 \
  'SELECT currency, SUM(net_cost) AS cost
   FROM `LAB_BILLING_PROJECT.billing_mart.v_daily_cost`
   WHERE usage_date >= DATE "2026-11-01"
   GROUP BY currency'
~~~

*Dry run* checks syntax and estimates bytes processed; BigQuery charges nothing for dry runs. `maximum_bytes_billed` rejects queries exceeding the cap **before execution charges apply**. On clustered tables, pre-run estimates can exceed actual runtime bytes scanned.

**Never treat `LIMIT 10` as a cost-control tool** on unclustered tables. To inspect a few sample rows, use **BigQuery Preview** or `bq head` where supported instead of running `SELECT *` on the raw table.

### 9.2. Designing a Partitioned and Clustered Summary Mart

`v_daily_cost` is a **view**, not a partitioned table. When dashboards frequently scan months of raw export data, consider **materializing a summary table**:

~~~sql
-- Example creating a summary table in the LAB; incurs storage/query costs.
-- Do not schedule this full-overwrite statement blindly over huge raw datasets.
CREATE OR REPLACE TABLE
  `LAB_BILLING_PROJECT.billing_mart.daily_cost_snapshot`
PARTITION BY usage_date
CLUSTER BY project_id, service_id
AS
SELECT *
FROM `LAB_BILLING_PROJECT.billing_mart.v_daily_cost`;
~~~

Pointing dashboards to `daily_cost_snapshot` enables **partition pruning** when filtering directly on `usage_date` and block pruning when filtering on `project_id`/`service_id`. Trade-off: you pay storage charges and must **refresh the snapshot whenever raw exports receive new rows or late adjustments**.

**In production:** use Scheduled Queries or an approved pipeline to refresh recent partitions with checkpoints and duplicate checks. Refreshing only the **last 30 days** can miss late adjustments to older months—keep **periodic invoice reconciliation** and a backfill mechanism for late adjustments. Never alter the raw export; the mart is derived data.

### 9.3. Rules to Keep Reporting Costs Low

- Use the **Standard export** for overview dashboards; reserve Detailed for resource-level questions.
- Project only needed columns; avoid `SELECT *` against raw exports.
- On **partitioned tables**, filter the partition column and verify pruning. Never assume raw billing exports are partitioned to match your custom layout.
- Never wire user-facing charts directly to `SELECT * FROM raw`.
- Prefer daily/monthly aggregates when viewer counts are high.
- Align **data freshness** with actual export cadences rather than refreshing every few seconds.
- Monitor BigQuery job costs/bytes billed via Monitoring/Cloud Billing Reports before increasing refresh frequency.
- Track BigQuery query bytes billed per project and tag reporting jobs with labels when appropriate.

## 10. Permissions, Security, and Dashboard Governance

### 10.1. Who Can Do What?

| Role | Recommended Scope | Avoid Granting |
| --- | --- | --- |
| Billing export operator | Billing account + dataset setup | Org-wide Owner unless strictly required |
| FinOps analyst | Read raw/mart and run queries in analytics project | Delete/modify rights on raw export |
| Data engineer | Create/edit views, marts, scheduled queries | Billing admin if not operating exports |
| Dashboard consumer | Read **approved summary tables/views** | Full raw export or unneeded resource metadata |
| Pipeline identity | Write mart tables or run scheduled queries | Project Editor |
| Auditor | Read reconciliation reports and evidence | Rights to alter billing exports |

**`bigquery.jobs.create` is required** on the query execution project alongside read rights on target tables/views. With **Owner's credentials**, audit what data the owner exposes, since viewers may lack direct BigQuery access. With **Viewer's credentials**, every viewer needs appropriate query permissions; both modes have distinct access-control implications.

If a dashboard must expose **totals by cost center only**, build a separate daily aggregate table per cost center and grant Data Viewer on a narrow dataset. Never expose views containing sensitive `project_name`s, labels, or SKUs to unintended audiences.

### 10.2. Data Quality and Allocation Rules

- Standardize `cost_center` / `env` / `team` with consistent label/tag taxonomies.
- Distinguish **project-level** vs. **resource-level** labels; coverage rates often differ.
- Surface `UNATTRIBUTED`/`unallocated` explicitly instead of burying it inside "Other."
- For shared costs like networking, centralized logging, or commitment fees, define independent **allocation rules** rather than blaming the project hosting shared infra.
- Document gross, credits, net, invoice month, and usage date in a **data dictionary**.
- Enforce retention policies, audit logs, and BigQuery IAM across both raw billing and marts.

### 10.3. When Is BigQuery Row-Level Security Needed?

If a single physical table holds multiple cost centers and each team may view only its own spend, consider **row access policies** or per-team **authorized views**. However, if applying row-level security directly on the **raw export**, verify that Cloud Billing's system service account **retains full table read/write access per documentation** so exports do not break.

For labs, sharing **filtered/validated summaries** is safer and clearer. Real production security designs should undergo separate review by data and IAM teams.

## 11. Practicing with Synthetic Data — Without Real Billing Access

This section **can run directly in the BigQuery SQL editor** with only query permissions in a lab project—no Billing Account Admin or real export needed. It uses **inline** data without creating or modifying tables.

### 11.1. Synthetic Dataset

Assume currency VND, two days, and three usage rows:

| Date | Project | Service | Gross (VND) | Credits | Net (VND) |
| --- | --- | --- | ---: | ---: | ---: |
| 2026-11-17 | p-shop | Compute Engine | 120,000 | -15,000, -5,000 | 100,000 |
| 2026-11-17 | p-shop | BigQuery | 30,000 | 0 | 30,000 |
| 2026-11-18 | p-analytics | Cloud Storage | 50,000 | -5,000 | 45,000 |
| **Total** | | | **200,000** | **-25,000** | **175,000** |

The first example includes **two credits on a single row** to catch `UNNEST` cost-doubling bugs.

### 11.2. Complete Standalone SQL

~~~sql
-- Queries inline data; returns output without writing to any BigQuery table.
WITH sample AS (
  SELECT
    DATE "2026-11-17" AS usage_date,
    "p-shop" AS project_id,
    "Compute Engine" AS service_name,
    "VND" AS currency,
    NUMERIC "120000" AS cost,
    [STRUCT(NUMERIC "-15000" AS amount),
     STRUCT(NUMERIC "-5000" AS amount)] AS credits
  UNION ALL
  SELECT
    DATE "2026-11-17", "p-shop", "BigQuery", "VND",
    NUMERIC "30000",
    ARRAY<STRUCT<amount NUMERIC>>[]
  UNION ALL
  SELECT
    DATE "2026-11-18", "p-analytics", "Cloud Storage", "VND",
    NUMERIC "50000",
    [STRUCT(NUMERIC "-5000" AS amount)]
),
cost_lines AS (
  SELECT
    usage_date, project_id, service_name, currency,
    cost AS gross_cost,
    COALESCE(
      (SELECT SUM(c.amount) FROM UNNEST(credits) AS c),
      NUMERIC "0"
    ) AS credit_amount
  FROM sample
)
SELECT
  currency,
  project_id,
  SUM(gross_cost) AS gross_cost,
  SUM(credit_amount) AS credits,
  SUM(gross_cost + credit_amount) AS net_cost
FROM cost_lines
GROUP BY currency, project_id
ORDER BY project_id;
~~~

**Expected result:**

| Project | Gross (VND) | Credits (VND) | Net (VND) |
| --- | ---: | ---: | ---: |
| p-analytics | 50,000 | -5,000 | 45,000 |
| p-shop | 150,000 | -20,000 | 130,000 |

If a query uses `LEFT JOIN UNNEST(credits)` and sums `cost`, `p-shop` gross inflates to **270,000** because the Compute Engine row has two credits. Using `CROSS JOIN UNNEST(credits)` drops the creditless BigQuery row altogether; both are wrong for summing gross cost.

### 11.3. Extension Tasks

1. Modify the query to group by **`usage_date`**; confirm Nov 17 net = **130,000** and Nov 18 net = **45,000**.
2. Modify the query to group by **`service_name`** and find the service with the highest net cost.
3. Add a synthetic `cost_type = "tax"` row and show that the daily usage view excludes tax while the invoice view includes it.
4. Add a `cost_center` field setting one row to `unallocated`; write the unallocated ratio KPI query.
5. Explain why `SUM(cost) - SUM(credits.amount)` is wrong when credits are negative.
6. Add a row with `currency = "USD"` and update the query so **USD and VND are never summed together**.

**Never copy these synthetic figures into a production dashboard.** For pure visual demos, create an approved **separate sample dataset/table** or CSV source—never insert dummy rows into `billing_raw`.

## 12. End-to-End Lab: Cloud Billing → Auditable Dashboard

**Prerequisites:** Run only if provided a **Billing export lab dataset** and required IAM. Otherwise, complete Section 11 and diagram the dashboard—never request Billing Admin rights on company accounts.

| Step | Action | Evidence |
| --- | --- | --- |
| 1 | Record billing account, dataset location, export type | Do not confuse Standard with Detailed |
| 2 | Verify Standard table is populated | Table name, initial date range, `MAX(export_time)` |
| 3 | Create `billing_mart.v_cost_lines` | Net = cost + per-row credits |
| 4 | Create `v_daily_cost` and `v_invoice_cost` | Same source, distinct period/`cost_type` grouping |
| 5 | Dry run queries and set `maximum_bytes_billed` | Known byte estimates, no blind scans |
| 6 | Test one project for one week | Correct SQL grouping and currency |
| 7 | Connect Data Studio to the daily view | Connected data source with accurate field types |
| 8 | Build scorecards, time series, service/project bars | Date, project, and currency filters active |
| 9 | Build a separate invoice reconciliation page | Uses `invoice_month` and all cost types |
| 10 | Reconcile against Cloud Billing Reports | Document variances and causes |
| 11 | Share with a low-privilege test account | Zero unauthorized raw billing exposure |
| 12 | Document refresh interval, owner, and cost monitoring | Report has clear operational ownership |

**Cost-saving tip:** On real exports, test SQL over a **small date window** first and inspect export byte sizes before enabling wide dashboard refreshes.

## 13. Detecting Spend Changes: Practical Questions from the Dashboard

Beyond basic charts, one way to spot cost spikes is comparing the last **7 completed days** against the **prior 7 days**, grouped by project and currency. Given delayed Billing exports, treat spikes as **investigation signals**, not instant proof of a production runaway.

~~~sql
WITH by_day AS (
  SELECT
    usage_date, currency, project_id,
    SUM(net_cost) AS daily_cost
  FROM `LAB_BILLING_PROJECT.billing_mart.v_daily_cost`
  WHERE usage_date >= DATE_SUB(CURRENT_DATE("Asia/Ho_Chi_Minh"), INTERVAL 14 DAY)
    AND usage_date < CURRENT_DATE("Asia/Ho_Chi_Minh")
  GROUP BY 1, 2, 3
),
compared AS (
  SELECT
    currency,
    project_id,
    SUM(IF(
      usage_date >= DATE_SUB(CURRENT_DATE("Asia/Ho_Chi_Minh"), INTERVAL 7 DAY),
      daily_cost, 0
    )) AS last_7_days,
    SUM(IF(
      usage_date < DATE_SUB(CURRENT_DATE("Asia/Ho_Chi_Minh"), INTERVAL 7 DAY),
      daily_cost, 0
    )) AS previous_7_days
  FROM by_day
  GROUP BY 1, 2
)
SELECT
  currency, project_id,
  ROUND(previous_7_days, 2) AS previous_7_days,
  ROUND(last_7_days, 2) AS last_7_days,
  ROUND(last_7_days - previous_7_days, 2) AS delta,
  SAFE_DIVIDE(
    last_7_days - previous_7_days,
    NULLIF(previous_7_days, 0)
  ) AS change_ratio
FROM compared
ORDER BY delta DESC;
~~~

**When evaluating fluctuations:** compare workload volume (requests, storage GB, slot-hours), recent releases, CUDs, SKU pricing changes, credits, late exports, and calendar patterns (weekdays vs. weekends). Handle zero baselines or negative net baselines from credits/adjustments explicitly instead of displaying "+∞%."

**Never auto-terminate production solely because a query reports `delta > 0`.** Cloud Billing Budgets/Monitoring alerts and triage runbooks must define thresholds, owners, verification steps, and approved actions.

## 14. Common Issues and How to Investigate

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Export table missing | Export not enabled, wrong billing account/dataset, no data yet | Check Billing export config; allow hours for initial propagation |
| Missing prior-month costs | Dataset created in a single region without backfill | Do not assume data loss; check export location backfill rules |
| Dashboard totals are doubled | Summing Standard + Detailed, or `UNNEST(credits)` duplicating rows | Query one usage source; enforce one-row semantics in SQL |
| Net cost unexpectedly higher than gross | Subtracting negative credits a second time | Use `cost + SUM(credits.amount)` |
| Dashboard total differs from invoice | Using usage date, excluding tax/adjustment/rounding, currency mix | Reconcile by `invoice.month`, cost types, and currency |
| A project shows "0 cost" | Wrong project filter, `project.id` NULL, or export delay | Check filters, schema, and exported date coverage |
| Cost center label is blank | Missing label or SKU does not emit labels | Classify as `unallocated`; review taxonomy and label scope |
| Can open report yet gets Access Denied | Missing BigQuery Data Viewer/`jobs.create` or Owner/Viewer mode issue | Check effective query identity and permissions |
| Dashboard very slow or expensive | Scanning huge raw export on every refresh | Use dry runs, aggregates, partitioned mart, and caching |
| Breaks after schema update | View uses `SELECT *` or new field shifts schema | Project explicit stable columns in views and test |
| Today's daily cost looks low | Export incomplete or service reporting lag | Display "incomplete current day" note; avoid real-time SLAs |
| Project spend differs from official reports | Shared costs, CUD allocation, or taxonomy mismatch | Define allocation rules and reconcile |
| Wrong currency displayed | Mixed currencies or hardcoded `$` formatting | Group/filter by currency before building metrics |

**Investigation order:** billing account → export settings/dataset location → table/date coverage → IAM → SQL net/credits → invoice vs. usage period → labels/filters → dashboard credential mode → bytes billed/freshness.

## 15. Review Exercises with Suggested Answers

1. **How does Standard differ from Detailed export?** Standard suits overview analytics; Detailed adds resource-level identifiers.
2. **Can you sum Standard and Detailed together?** No; that can double-count the same usage.
3. **Cost = 100, credits = -20, -5. What is net cost?** 75, not 125.
4. **Why avoid `LEFT JOIN UNNEST(credits)` followed by `SUM(cost)`?** A source row with multiple credits duplicates `cost`.
5. **Are `invoice.month` and `usage_start_time` always in the same month?** No.
6. **Is `export_time` when resources were consumed?** No; it is when Billing exported the record.
7. **Can a dashboard enforce a hard spending cap?** No.
8. **Why doesn't `LIMIT 10` guarantee lower query costs?** It does not reduce bytes scanned on unclustered tables.
9. **How should credits in repeated fields be aggregated?** Sum credits **within each row** first, then aggregate across rows.
10. **Can VND and USD be summed in one KPI?** No, unless using an approved currency-conversion rule.
11. **Should a tax row be included in Net daily usage?** Not under our usage definition; it belongs in invoice reconciliation.
12. **If you enable Standard export today in a single region, do you get last year's data?** Usually no backfill prior to the enablement date.
13. **If you add a `cost_center` label today, will last month's billing rows gain that label?** No.
14. **Why put a view in front of the dashboard?** To standardize schema and KPI definitions and prevent divergent ad-hoc SQL.
15. **How do authorized views differ from owner's credentials on a dashboard?** Authorized views scope BigQuery access at the data layer; owner's credentials execute all dashboard queries as the report owner's identity.
16. **What optimizes dashboard costs?** Dry runs, maximum bytes billed, aggregate tables, partition filters, and sensible refresh rates.
17. **Which KPIs help investigate overspend?** Gross/net/credits, daily trends, top services/projects, unallocated spend, and period-over-period deltas.
18. **Which time grouping is used for month-end invoice reconciliation?** `invoice.month` including all cost types and credits.

## 16. Completion Checklist and References

- [ ] Data sourced from the right billing account without double-counting Standard and Detailed.
- [ ] Dataset location and backfill match policy; export covers the needed time range.
- [ ] Permissions separate export operator, BigQuery analyst, and dashboard consumer.
- [ ] A standardized view computes net cost from `cost` and per-row summed `credits`.
- [ ] `usage_date`, `invoice_month`, and `export_time` are clearly distinguished.
- [ ] `currency` is a mandatory dimension/filter to prevent cross-currency sums.
- [ ] Operations dashboard separates regular usage costs from tax/adjustment/invoice totals.
- [ ] Project/service/SKU/cost-center metadata and `unallocated` tracking are included.
- [ ] Dashboard filters tested across multiple projects and services.
- [ ] Dry runs, maximum bytes billed, and budgets protect the analytics project.
- [ ] Snapshots/aggregates have scheduled refreshes, late-adjustment handling, and reconciliation.
- [ ] Views/authorized tables protect raw billing; dashboard credential mode reviewed.
- [ ] KPI totals reconciled against Cloud Billing Reports/Invoices for matching period and currency.
- [ ] Refresh timestamps, owners, and partial-day freshness notices are displayed.
- [ ] Synthetic test confirms multi-credit rows never double-count `cost`.

**Official Google Cloud Sources:**

- [Export Cloud Billing data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery) — export types and scope.
- [Set up Cloud Billing data export](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-setup) — IAM, dataset location, backfill, and latency.
- [Understand export tables](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables) — Standard/Detailed/FOCUS and schemas.
- [Standard usage cost schema and queries](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage) — `cost`, `credits`, `invoice.month`, `labels`.
- [Detailed usage cost schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage) — resource-level costs.
- [Example queries for Billing data](https://docs.cloud.google.com/billing/docs/how-to/bq-examples) — reconciliation and credit math.
- [Cloud Billing Reports](https://docs.cloud.google.com/billing/docs/how-to/reports) — interpreting figures and Generate query.
- [Data Studio BigQuery connector](https://docs.cloud.google.com/data-studio/connect-to-google-bigquery) — connecting tables/views/custom SQL and credentials.
- [BigQuery visualization with Data Studio](https://docs.cloud.google.com/bigquery/docs/visualize-looker-studio) — building and sharing reports.
- [BigQuery: Estimate and control costs](https://docs.cloud.google.com/bigquery/docs/best-practices-costs) — dry run and maximum bytes billed.
- [Partitioned tables](https://docs.cloud.google.com/bigquery/docs/partitioned-tables) and [Clustered tables](https://docs.cloud.google.com/bigquery/docs/clustered-tables) — optimizing mart scans.
- [Cloud Billing budgets and alerts](https://docs.cloud.google.com/billing/docs/how-to/manage-budgets) — alerting and spend management workflows.
- [BigQuery IAM](https://docs.cloud.google.com/bigquery/docs/access-control) — least privilege, views, and jobs.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) — compute/storage and dashboard query costs.

**Key takeaway:** A trustworthy cost dashboard needs more than `SUM(cost)`. **Pick the right export source, sum credits per row, never mix currencies, separate usage dates from invoice months, reconcile regularly, and restrict access.** Use BigQuery views/marts to lock down KPI definitions, and Looker Studio/Data Studio to visualize them while keeping scanned bytes and operating costs under control.
