# Hands-On: Organizing Data Domains and Analytics Authorization

An enterprise has a **Sales** team owning order data, a **Customer** team managing customer profiles, and an **Analytics** team building dashboards. If every analyst had permission to read all tables, someone building a revenue report could also view emails, phone numbers, or data outside their job scope. The solution is not creating lots of projects and assuming data is safe by default: you need **owned data domains**, **data contracts**, and **authorization enforced at the right layer**.

This lesson belongs to the **Data Governance and Analytics** chapter of the **CLOUD_PROVIDERS_GCP** module. We combine projects, IAM, BigQuery, Cloud Storage, Knowledge Catalog, Java/Cloud Run applications, data pipelines, monitoring, and cost controls to deploy a **revenue analytics data product** with verifiable access permissions. Examples use mock data and GoogleSQL; later sections cover row-level security, column policy tags, masking, BigQuery sharing, and data-quality controls.

After this lesson, you will be able to:

- Distinguish **data domain**, **data owner**, **data steward**, **data producer**, and **data consumer**.
- Design project/dataset/table/view boundaries aligned with domains and environments.
- Separate permissions to **run query jobs** from permissions to **read data**, avoiding project-wide Viewer/Editor grants.
- Create a **BigQuery authorized view** so Analytics reads aggregates without permissions on the source table.
- Apply **row access policies**, column-level access control, and masking in appropriate scenarios.
- Verify permissions using two independent identities, inspect effective IAM, and build an incident runbook.
- Define data contracts, metadata/glossary/lineage, quality assertions, and access-request workflows.
- Estimate query/storage/governance costs and organize rollouts with rollback capability.

> **Lab boundaries:** all project IDs, Google Groups, service accounts, datasets, and email addresses below are **placeholders**. Never run IAM/DDL in a production project or on real data without approval. This lesson is a guide only and executes no commands on a GCP account. Creating query jobs, tables, scans, and related resources can incur charges.

## 1. A Data Domain Is a Business Responsibility, Not Just a Folder

A **data domain** is a business scope with clear accountability for semantics, quality, and how data is published. A domain can span multiple tables or projects, and a single project can host multiple datasets; **folder/project names do not automatically create access policies**.

| Domain | Data Sources | Published Data Product | Owner / Consumers |
|---|---|---|---|
| **Sales** | Orders, payments, refunds | Daily revenue by region | Sales owner → Analytics |
| **Customer** | Profiles, contact details, consent | Low-sensitivity customer segments | Customer owner → Marketing/Analytics |
| **Inventory** | Stock levels, receipts/issues | Available stock by SKU | Supply chain → Sales |
| **Analytics** | Approved data products | Dashboards / metric definitions | Analytics owner → decision makers |

### Roles That Should Not Be Collapsed Into One

| Role | Primary Responsibility | Does Not Automatically Receive |
|---|---|---|
| **Domain owner** | Decides intended usage, standards, and sharing policies | Project Owner across all of GCP |
| **Data steward** | Terminology, quality, classification, lineage, access requests | Read access to all PII columns |
| **Data engineer / producer** | Ingestion, schemas, pipelines, freshness, publication | Authority to grant IAM to anyone |
| **Platform/IAM team** | Project factory, service accounts, IAM, policies, auditing | Authority to define `net_revenue` business semantics |
| **Analytics consumer** | Queries published data, builds dashboards | Viewing raw/private tables or modifying policies |

A **data product** needs an owner, definition, output schema, quality criteria, refresh schedule, sensitivity classification, and access-request workflow. For example: "Completed paid revenue grouped by UTC date and region, excluding refunds, refreshed before 08:00, with recipients restricted to aggregates."

## 2. Sales → Analytics Domain Architecture

~~~mermaid
flowchart LR
  SRC["Cloud Run / Pub/Sub / Cloud SQL"] --> RAW["sales-private project<br/>sales_private.orders"]
  RAW --> VIEW["sales-private project<br/>sales_public.v_paid_daily<br/>authorized view"]
  VIEW --> Q["analytics-query project<br/>BigQuery query job / Java BI API"]
  Q --> BI["Dashboard"]
  CAT["Knowledge Catalog<br/>owner + glossary + lineage + quality"] --> RAW
  CAT --> VIEW
  IAM["IAM + source dataset authorization<br/>+ row/column policies"] --> RAW
  IAM --> VIEW
~~~

To keep operations easy to control, the lab uses **two Google Cloud projects**:

~~~text
DATA_PROJECT (e.g., company-sales-lab)
  ├── sales_private  ← BigQuery dataset, orders table containing PII
  │   └── orders
  ├── sales_public   ← Dataset strictly for analytics products
  │   └── v_paid_daily  ← Authorized logical view
  └── sales_rls_lab  ← Separate dataset to test row-level policies
      └── regional_orders

QUERY_PROJECT (e.g., company-analytics-lab)
  ├── group/caller permitted to create query jobs
  └── Java Cloud Run or BI client querying the view in DATA_PROJECT
~~~

| Boundary | Decision | Rationale |
|---|---|---|
| **Project** | Separate Sales data hosting from Analytics query/billing | Ownership, billing, job permissions, and quotas can be governed independently |
| **Dataset** | `sales_private` separate from `sales_public` | Avoids granting Data Viewer on PII tables when only views are needed |
| **View** | Exposes only aggregate `sale_date, region, paid_orders, revenue_minor` | Minimizes shared surface; omits emails and customer IDs |
| **IAM** | Consumers receive `jobUser` on QUERY_PROJECT and `dataViewer` on `sales_public` | No Data Viewer needed on `sales_private` |
| **Authorized view** | Source dataset authorizes that exact view to read source tables | View executes even when consumers lack source permissions |
| **Advanced security** | RLS / column policy tags / BigQuery masking where appropriate | Sensitive rows and columns carry dedicated policies |

**Important:** an authorized view is **not** a normal view with a `WHERE` clause. If an analyst still holds read access on `sales_private.orders` from a project/folder/organization role, they can bypass the view and query the source table directly. Always inspect **effective IAM** at every level, including inherited bindings.

### Environments and Locations

- Separate **dev/staging/prod** and **real/mock data**; never copy production PII into labs casually.
- Source datasets and authorized views must share the **same BigQuery location**; cross-region queries do not work automatically just from IAM.
- Query jobs have a defined **billing/execution project** and location; `QUERY_PROJECT` can differ from `DATA_PROJECT`.
- Cross-project billing does not alter data access permissions. VPC Service Controls, organization policies, data residency, and CMEK can still block actions even when BigQuery IAM permits them.

## 3. BigQuery IAM: Job Execution Rights vs. Data Read Rights

| Permission / Role | Typical Scope | Effect |
|---|---|---|
| `roles/bigquery.jobUser` | **QUERY_PROJECT** | Grants `bigquery.jobs.create` to execute queries in the project |
| `roles/bigquery.dataViewer` | `DATA_PROJECT.sales_public` or specific view | Reads granted tables/views without opening other datasets |
| `roles/bigquery.dataEditor` | Assigned producer dataset | Creates/modifies tables or views per role permissions |
| `roles/bigquery.dataOwner` | Governed dataset | Manages dataset data and ACLs; grant to very few principals |
| `roles/bigquery.metadataViewer` | Discoverable dataset | Views metadata without reading table rows |
| `roles/bigquery.securityAdmin` / policy tag admin | Security governance scope | Manages row policies/data policies/taxonomies; not an analyst role |

**Separating the two permissions:** having `bigquery.jobs.create` without `bigquery.tables.getData` → table queries are denied. Having Data Viewer on the view without `jobUser` on the **query-execution project** → cannot create jobs either. Never grant `roles/bigquery.jobUser` organization-wide when only one billing project is needed.

**Dataset IAM pitfall:** `bq add-iam-policy-binding` works on **tables/views**, **not on datasets**. In this lab, use **GoogleSQL DCL `GRANT ... ON SCHEMA`**, Console Dataset Sharing, or API/`bq update` when dataset access controls must be modified.

### Principles for Limiting Access

1. Use Google Groups aligned to **business roles**, e.g., `analytics-revenue@example.com`, rather than granting dozens of individual users.
2. A Java dashboard's runtime service account gets **product query** permissions, not IAM administration or data engineering rights.
3. Only the Sales governance group can edit authorized view SQL and authorize views on the source; reviewers must inspect every view SQL change.
4. Never grant `roles/viewer`/`roles/editor` at the root project to "quick-fix" a 403 error; broad/inherited roles can expose private tables.
5. Verify permissions from **org → folder → project → dataset → table/view**, plus row policies, column policies, masking, and perimeters.

## 4. Lab A — Creating the Sales Domain and an Analytics Data Product

The lab creates two isolated datasets in `DATA_PROJECT`. The operator is an **authorized platform/data engineer** able to enable APIs, create datasets/tables/views, and run queries. Never grant these privileges to analysts merely for testing.

### Step 1 — Prepare Projects and Datasets

~~~bash
DATA_PROJECT="company-sales-lab"
QUERY_PROJECT="company-analytics-lab"
LOCATION="asia-southeast1"

# Both projects must exist with valid billing/APIs/permissions beforehand.
gcloud services enable bigquery.googleapis.com --project="$DATA_PROJECT"
gcloud services enable bigquery.googleapis.com --project="$QUERY_PROJECT"

# Create LAB datasets only if absent; never touch production data.
bq --location="$LOCATION" mk --dataset "$DATA_PROJECT:sales_private"
bq --location="$LOCATION" mk --dataset "$DATA_PROJECT:sales_public"
bq --location="$LOCATION" mk --dataset "$DATA_PROJECT:sales_rls_lab"

bq --location="$LOCATION" show "$DATA_PROJECT:sales_private"
bq --location="$LOCATION" show "$DATA_PROJECT:sales_public"
~~~

Use the same location so views can reference source tables; real organizations may use separate projects per domain, though one domain does **not strictly have to** equal one project. Attach dataset labels, owners, classifications, and retention policies through standard IaC/org configs.

### Step 2 — Create the Private Source Table with GoogleSQL

In BigQuery Studio, select **DATA_PROJECT**, location `asia-southeast1`; replace `DATA_PROJECT` in the SQL with your real project ID:

~~~sql
-- Lab only: CREATE OR REPLACE can wipe existing table data.
CREATE OR REPLACE TABLE `DATA_PROJECT.sales_private.orders` (
  order_id STRING NOT NULL,
  order_date DATE NOT NULL,
  region STRING NOT NULL,
  customer_id STRING NOT NULL,
  customer_email STRING,
  amount_minor INT64 NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL
)
PARTITION BY order_date
CLUSTER BY region
OPTIONS (
  description = 'Sales domain: order events, restricted dataset'
);

INSERT INTO `DATA_PROJECT.sales_private.orders` (
  order_id, order_date, region, customer_id, customer_email,
  amount_minor, currency, status
)
VALUES
  ('O-101', DATE '2026-11-18', 'APAC', 'C-01',
   'alice@example.test', 12500, 'USD', 'PAID'),
  ('O-102', DATE '2026-11-18', 'APAC', 'C-02',
   'bob@example.test', 5000, 'USD', 'PAID'),
  ('O-103', DATE '2026-11-18', 'EMEA', 'C-03',
   'carol@example.test', 8600, 'USD', 'PAID'),
  ('O-104', DATE '2026-11-18', 'EMEA', 'C-04',
   'dan@example.test', 2000, 'USD', 'REFUNDED'),
  ('O-105', DATE '2026-11-18', 'APAC', 'C-05',
   'eve@example.test', 9000, 'USD', 'CANCELLED'),
  ('O-106', DATE '2026-11-18', 'EMEA', 'C-06',
   'fay@example.test', 12000, 'USD', 'PAID');
~~~

`example.test` emails are mock data. Production must collect minimal data, classify `customer_email` as **PII**, and enforce retention/consent. Use `INT64` in **minor units** to avoid floating-point errors; with multiple currencies, **never sum USD and EUR directly**. The lab uses USD only.

### Step 3 — Validate Source Data Quality

~~~sql
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT order_id) AS distinct_orders,
  COUNTIF(amount_minor <= 0 OR amount_minor IS NULL) AS invalid_amounts,
  COUNTIF(currency != 'USD') AS unexpected_currency,
  COUNTIF(status = 'PAID') AS paid_orders,
  SUM(IF(status = 'PAID', amount_minor, 0)) AS paid_revenue_minor
FROM `DATA_PROJECT.sales_private.orders`;
~~~

Expected results: `row_count=6`, `distinct_orders=6`, `invalid_amounts=0`, `unexpected_currency=0`, `paid_orders=4`, `paid_revenue_minor=38100`. A query returning 6 rows **does not prove** data is fresh or business-accurate; also check freshness, schema contracts, source batch IDs, duplicate order events, and refunds.

## 5. Lab B — Publishing an Authorized View Without Opening Raw Tables

An **authorized logical view** lets Analytics run SQL reading **only the columns/rows in the view** without permissions on `sales_private.orders`. Two **separate actions** are required:

1. Create the view in `sales_public` and grant consumers read access on **the view or that dataset**.
2. **Authorize the view** inside the **source dataset `sales_private`** so the view can read the source table on behalf of consumers.

### Step 1 — Define the Output Contract and Create the View

~~~sql
CREATE OR REPLACE VIEW `DATA_PROJECT.sales_public.v_paid_daily`
OPTIONS (
  description = 'Sales product v1: paid USD revenue by UTC date and region'
)
AS
SELECT
  order_date AS sale_date,
  region,
  COUNT(*) AS paid_orders,
  SUM(amount_minor) AS revenue_minor
FROM `DATA_PROJECT.sales_private.orders`
WHERE status = 'PAID'
  AND currency = 'USD'
GROUP BY sale_date, region
HAVING COUNT(*) >= 2;

-- Producer, who has source data permissions, verifies:
SELECT sale_date, region, paid_orders, revenue_minor
FROM `DATA_PROJECT.sales_public.v_paid_daily`
ORDER BY region;
~~~

**Expected output**:

| sale_date | region | paid_orders | revenue_minor |
|---|---|---:|---:|
| 2026-11-18 | APAC | 2 | 17,500 |
| 2026-11-18 | EMEA | 2 | 20,600 |

The view aims to **publish aggregates only**, omitting `customer_id/email` and preventing drill-downs to individual transactions. `HAVING COUNT(*) >= 2` is merely an **illustrative threshold** to reduce single-person cohort exposure, **not an anonymity guarantee**: combining external sources can still re-identify individuals; real products need privacy assessments and appropriate group-size/k-anonymity or privacy-preserving analytics criteria.

### Step 2 — Authorize *View → Source Dataset*

In Google Cloud Console, navigate to **DATA_PROJECT → BigQuery → Dataset `sales_private` → Sharing → Authorize views**, and select:

~~~text
DATA_PROJECT.sales_public.v_paid_daily
~~~

Add **that exact view** to `sales_private`'s authorized views and re-check dataset access. **Do not** grant the Analytics group `dataViewer` on `sales_private`. This is a source-governance step for the domain owner/platform team, not a self-service BI user action.

> You can use the BigQuery API or `bq update --source ...` to manage `view` access entries in IaC. When updating dataset ACLs via JSON, you must **preserve all existing access entries**; overwriting the list can accidentally revoke or expose access. Console is simpler for first-time learning.

An **authorized dataset** variant authorizes **all current and future views** in a dataset to read the source dataset. This reduces configuration overhead across hundreds of views, yet increases blast radius: anyone permitted to create/edit views in that dataset could create unintended read paths. For a lab product, **authorizing a single specific view** is easier to audit.

### Step 3 — Grant *Consumer → View Dataset* and *Query Project*

Once an approved real Google Group exists, the domain owner runs BigQuery **GoogleSQL DCL**:

~~~sql
-- Run as an identity with bigquery.datasets.update on sales_public.
-- Replace the example email with an actively managed Google Group.
GRANT `roles/bigquery.dataViewer`
ON SCHEMA `DATA_PROJECT`.sales_public
TO "group:analytics-revenue@example.com";
~~~

The Platform/IAM team grants **query job creation** to that same group in **QUERY_PROJECT**:

~~~bash
gcloud projects add-iam-policy-binding "$QUERY_PROJECT" \
  --member="group:analytics-revenue@example.com" \
  --role="roles/bigquery.jobUser"
~~~

**You do not need to grant `roles/bigquery.jobUser` on `DATA_PROJECT`** if consumers execute jobs in `QUERY_PROJECT`. In multi-product setups, you can grant `dataViewer` on the **individual view** rather than all of `sales_public` to avoid exposing metadata/data from other views.

### Step 4 — Verify Using the Consumer Identity Itself

Once Google Group/IAM propagation completes, authenticate the CLI as a **real account in the Analyst group**, or run Java/BI with the actual permitted runtime service account:

~~~bash
# Run query job on QUERY_PROJECT; read view from DATA_PROJECT.
# Set query project explicitly, matching the location of both datasets.
bq --project_id="$QUERY_PROJECT" --location="$LOCATION" \
  query --use_legacy_sql=false \
  'SELECT sale_date, region, paid_orders, revenue_minor
   FROM `DATA_PROJECT.sales_public.v_paid_daily`
   ORDER BY region'

# Querying the source table must be denied for the consumer.
bq --project_id="$QUERY_PROJECT" --location="$LOCATION" \
  query --use_legacy_sql=false \
  'SELECT customer_email FROM `DATA_PROJECT.sales_private.orders` LIMIT 1'
~~~

In the `bq` commands above, replace the literal `DATA_PROJECT` inside the SQL with the **real project ID**. **Never pretend to test another user by merely editing an email variable**; testing is only valid when authenticated as the real identity (user or SA) verified by Google Cloud.

**Two acceptance checks:**

- Querying the **authorized view succeeds** and returns the two aggregate rows.
- Querying **`sales_private.orders` directly returns `Access Denied`**. If the raw query succeeds, hunt down inherited roles or old bindings at project/folder/org/table level; **do not mark the lab passed**.

### Step 5 — Test Access Revocation

In an isolated test, the owner runs DCL `REVOKE roles/bigquery.dataViewer ON SCHEMA ...` for the test group, then the consumer re-runs the view query. Expect denial once IAM propagates. If the raw query still succeeds, that is a **source IAM** issue, not a view-revocation issue. Never remove view authorization while valid users or live dashboards still depend on it.

## 6. Lab C — Scoped Regional Row-Level Security

**Row-level security (RLS)** lets different users read the **same table** while seeing only rows matching a filter. If APAC should see only `region='APAC'` and EMEA only `region='EMEA'`, RLS beats maintaining duplicate regional tables.

**To avoid accidentally exposing PII**, the RLS lab uses a **separate `sales_rls_lab` dataset**, without granting Data Viewer on `sales_private`. The test table also contains only necessary columns.

### Step 1 — Create the Test Table

~~~sql
-- Run as domain owner with read access to sales_private.
CREATE OR REPLACE TABLE `DATA_PROJECT.sales_rls_lab.regional_orders`
PARTITION BY order_date
CLUSTER BY region
AS
SELECT order_id, order_date, region, amount_minor, status
FROM `DATA_PROJECT.sales_private.orders`;
~~~

**Important:** this copies data in the lab to practice clean permissions; in production, creating extra copies adds storage, retention, and deletion/sync duties. A newly CTAS-created table is **not yet protected by RLS**. **Never grant analysts read permissions before creating policies.**

### Step 2 — Create Row Access Policies

The Google Groups must already exist before running; replace `example.com` with your organization domain:

~~~sql
CREATE ROW ACCESS POLICY apac_only
ON `DATA_PROJECT.sales_rls_lab.regional_orders`
GRANT TO ('group:sales-apac@example.com')
FILTER USING (region = 'APAC');

CREATE ROW ACCESS POLICY emea_only
ON `DATA_PROJECT.sales_rls_lab.regional_orders`
GRANT TO ('group:sales-emea@example.com')
FILTER USING (region = 'EMEA');
~~~

Users not matching any row access policy **see zero rows**. Users matching **two policies** see the **union (OR)** of rows permitted by each policy, not just the intersection. Data Owners/Admins can edit or bypass-manage policies, so **always test with a regular consumer identity** to verify read behavior.

### Step 3 — Grant Data Viewer on the Test Dataset

~~~sql
GRANT `roles/bigquery.dataViewer`
ON SCHEMA `DATA_PROJECT`.sales_rls_lab
TO "group:sales-apac@example.com",
   "group:sales-emea@example.com";
~~~

Each tester also needs `roles/bigquery.jobUser` on **QUERY_PROJECT** (or whichever query project they are allowed to use). From both real identities:

~~~sql
SELECT order_id, region, amount_minor, status
FROM `DATA_PROJECT.sales_rls_lab.regional_orders`
ORDER BY order_id;
~~~

**Expected for single-group membership:** APAC sees `O-101`, `O-102`, `O-105` (3 rows); EMEA sees `O-103`, `O-104`, `O-106` (3 rows). A user in both groups sees 6 rows. If 0 rows return, distinguish **no matching RLS grant** from **IAM blocking the table/query job**. If 6 rows return when belonging to only one group, check for other policies like `FILTER USING (TRUE)`, overly broad roles, and inherited bindings.

### Step 4 — Inspect and Manage Policies

~~~sql
-- Requires permissions to inspect row policy metadata (e.g., BigQuery Security Admin).
SELECT
  table_name,
  row_access_policy_name,
  filter_predicate,
  creation_time,
  last_modified_time
FROM `DATA_PROJECT.sales_rls_lab.INFORMATION_SCHEMA.ROW_ACCESS_POLICIES`
WHERE table_name = 'regional_orders'
ORDER BY row_access_policy_name;
~~~

`ROW_ACCESS_POLICIES` shows **names, filter predicates, and metadata**, but **does not list grantee principals**. To audit who holds access, use Console/`bq`/API to read IAM policies on each row access policy. Never treat filter metadata as complete proof of effective principals.

**Leak prevention:** attach RLS **to the actual table** when row-level reads must be shared. If you place an authorized view over a source table that has RLS, **verify how source and view permissions interact** rather than assuming the view bypasses row policies. Java applications must also enforce tenant/owner authorization in business logic even when BigQuery filters rows.

## 7. Column-Level Access, Masking, and PII Controls

RLS restricts **rows**; it does not automatically hide `customer_email` for users permitted to see those rows. Three common options:

| Need | Tool | Notes |
|---|---|---|
| Analysts only need aggregates | **Authorized view** omitting PII and grouping data | Simple, easy to bound intended use |
| A group reads the table but not email/SSN | **Column-level access control** via policy tags or data governance tags | Column permissions are enforced even when queried via views referencing that column |
| Analysts need a non-raw email/ID form | **BigQuery data masking policies** | Masked Readers receive transformed values per policy |

### Policy Tag / Masking Workflow

1. Domain steward and security team classify `customer_email` as **PII/Confidential** and define who sees raw vs. masked values.
2. Create a **policy tag taxonomy** in the right location and attach the policy tag to `sales_private.orders.customer_email`.
3. **Enforce column-level access** with data policies; users needing raw data receive **Data Catalog Fine-Grained Reader** on that tag, in addition to table read permissions.
4. Where masking is needed, create a **data masking policy** on the tag (e.g., NULL/default/hash per supported rules) and grant **BigQuery Masked Reader** on that data policy.
5. Test with at least three identities: raw access, masked-only access, and neither. Verify reads both via direct SQL and via allowed views.

**Never write real data into tag names or descriptions.** Classification metadata is not a PII store. Policy tags, resource tags, and Knowledge Catalog glossaries/aspects are distinct mechanisms: **attaching a "customer email" business term does not create an IAM policy**. Likewise, do not treat standard hash functions as absolute anonymization; dictionary/correlation attacks can reverse them.

**When to choose policy tags over authorized views?** When teams need row-level table details while sensitive columns must stay protected consistently across many queries, policy tags beat asking every view author to remember omitting email. When consumers only need daily revenue, **do not grant source table access and try to patch over-broad access with column masking**: keep using an authorized aggregate view.

## 8. Data Contract: Analytics Agreement Between Sales and Analytics

IAM answers "who can access"; a **data contract** answers "which data may be used, what it means, how fresh it is, and how we know it's right." Example v1 contract for `v_paid_daily`:

| Field | Illustrative Contract |
|---|---|
| Name / owner | `sales.paid_daily.v1` — Sales domain owner |
| Consumers | Analytics revenue group and approved dashboards |
| Schema | `sale_date DATE`, `region STRING`, `paid_orders INT64`, `revenue_minor INT64` |
| Semantics | Only `status='PAID'` and `currency='USD'`; amounts in minor units |
| Scope | Aggregated by UTC date and region; cohort threshold `COUNT(*) >= 2` |
| Freshness | Day D data ready before 08:00 on D+1 (example) |
| Quality | No duplicate `(sale_date, region)`; non-negative revenue; reconciled with source |
| Sensitivity | No direct PII; aggregates still require privacy review |
| Change policy | Compatible column additions announced; metric semantic changes require v2 |
| Access / incident | Owner-approved, time-bounded grants, on-call contact and incident SLA |

**Schema evolution:** adding a nullable column to a view may not break some clients, whereas changing `revenue_minor` from cents to dollars under the same name is a **breaking semantic change**. When refund rules change, publish `v_paid_daily_v2`, run parallel comparisons, and migrate dashboards cleanly.

### SQL Quality Checks

~~~sql
-- Verify uniqueness of the output key.
SELECT sale_date, region, COUNT(*) AS duplicates
FROM `DATA_PROJECT.sales_public.v_paid_daily`
GROUP BY sale_date, region
HAVING COUNT(*) > 1;

-- Detect anomalous values per contract.
SELECT *
FROM `DATA_PROJECT.sales_public.v_paid_daily`
WHERE paid_orders < 2 OR revenue_minor < 0;

-- Reconcile source vs. view for groups with at least 2 PAID orders.
WITH expected AS (
  SELECT order_date AS sale_date, region,
         COUNT(*) AS paid_orders, SUM(amount_minor) AS revenue_minor
  FROM `DATA_PROJECT.sales_private.orders`
  WHERE status = 'PAID' AND currency = 'USD'
  GROUP BY sale_date, region
  HAVING COUNT(*) >= 2
),
actual AS (
  SELECT sale_date, region, paid_orders, revenue_minor
  FROM `DATA_PROJECT.sales_public.v_paid_daily`
)
SELECT * FROM expected
EXCEPT DISTINCT
SELECT * FROM actual;
~~~

All three queries should return **zero rows**. Reconciliation queries run only under a **domain owner/quality service account permitted to read sources**—never grant analysts source access just to "test datasets." For continuously updating data, compare at the same snapshot/timestamp or closed batch window; two queries run at different instants can briefly diverge.

## 9. Knowledge Catalog: Helping Users Discover and Understand Data Products

In current Google Cloud, **Knowledge Catalog** (formerly **Dataplex Universal Catalog**) supports asset discovery, business glossaries, metadata **aspects**, lineage, data quality, and data product management. **Data Catalog policy tags** remain the mechanism used in BigQuery column-level security; do not confuse the two product names simply because both handle metadata.

~~~mermaid
flowchart LR
  A["BigQuery sales_private.orders"] --> L["Lineage: source → transform → view"]
  L --> V["BigQuery sales_public.v_paid_daily"]
  G["Glossary: paid revenue"] --> V
  M["Aspect: owner, classification, SLA"] --> V
  D["Data quality: completeness, validity"] --> V
  V --> P["Data product: Sales Revenue v1"]
  P --> C["Analytics / BI consumer"]
~~~

### Minimum Metadata to Publish

| Attribute | Example | Maintained By |
|---|---|---|
| Display name | Sales Paid Revenue Daily | Data product owner |
| Technical asset | `DATA_PROJECT.sales_public.v_paid_daily` | Data engineer |
| Business term | "Paid revenue" | Sales steward |
| Description | PAID/USD only, excludes refunds/cancelled, daily UTC | Sales owner |
| Sensitivity | Internal aggregate; no emails, privacy-reviewed | Security + steward |
| Freshness / SLA | D+1 before 08:00 | Pipeline owner |
| Lineage | orders → paid daily view → dashboard | Pipeline/catalog integration |
| Quality score | Passing checks count, latest run date | Quality owner |
| Contact / runbook | Sales data product support group | Operations |

A **business glossary** aligns terminology: what "paid order" means, whether refunds are netted, which timezone defines day boundaries, and whether revenue includes tax. Assets link to terms via **glossary terms**. **Aspects** attach structured metadata such as owner, classification, contract version, and quality status. **Lineage** maps sources and dependencies so you know which dashboards break when a table changes.

In **Knowledge Catalog → Data products**, producers bundle reviewed assets alongside refresh contracts and onboarding guidance; consumers discover and **request access** through supported workflows. **Discovering a data product does not grant BigQuery read access:** the request workflow must provision/approve IAM or a data-product access group per policy; always re-test effective permissions.

### Applying to the Lab via Console

1. Open **Google Cloud Console → Knowledge Catalog** and search for `sales_public.v_paid_daily` (required APIs/permissions must be enabled per org).
2. Add a business description, link the "paid revenue" term, owner/contact, and appropriate metadata **aspects**.
3. Document in the data product contract: `sale_date` in UTC, `revenue_minor` in USD cents, cohort threshold ≥ 2, SLA D+1 08:00.
4. Connect/inspect lineage from `orders` to the view; if custom Java/SQL pipelines do not emit full lineage automatically, add metadata/lineage via supported mechanisms.
5. Create a **data quality scan** or rules on the table, inspect results, and publish the scorecard to the catalog if permitted.

**Limitations:** automatic metadata features, data products, access requests, and UI views vary by region, permissions, edition, and rollout; owners must confirm availability before making them production prerequisites.

## 10. Data Quality Scans and Trustworthy Signals

Beyond manual SQL checks, **Knowledge Catalog auto data quality** (formerly under Dataplex) runs scans on BigQuery tables applying rules for completeness, format, allowed values, uniqueness, or custom SQL. This is a **quality control**, not an access control or automated data-repair tool.

| Rule | Example for `orders` | Action on Violation |
|---|---|---|
| Completeness | `order_id`/`order_date` non-NULL | Block publish, send to quarantine |
| Uniqueness | One `order_id` does not appear with invalid duplicates | Inspect CDC/producer retries |
| Validity | `amount_minor > 0` for PAID | Quarantine and reconcile payments |
| Valid values | `currency` in allowed set; `status` matches enum | Version schema/contract |
| Freshness | Prior day's data present before 08:00 | Alert ingest owner |
| Reconciliation | View revenue total matches source for close period | Do not publish wrong dashboard |

Running scans can incur processing/BigQuery costs; the execution identity needs permissions to **read the target table, run data scans, and access related resources**. Publishing scorecards to Knowledge Catalog also requires metadata update permissions—never grant `roles/owner`.

Command to **run a scan previously created by the owner**:

~~~bash
gcloud dataplex datascans run sales-orders-quality \
  --project="$DATA_PROJECT" \
  --location="$LOCATION"
~~~

This command **does not create** `sales-orders-quality`. In Console, configure full-table or `order_date`-incremental scope, rules, schedule, IAM, notifications, and result export destination first; test on the lab dataset. **Passing quality does not prove data may be shared:** privacy policies and access approvals are still required.

### Why Glossaries and Policies Must Work Together

A data product labeled "Aggregates only" whose view accidentally adds `customer_email` is a **security breaking change**, even if queries run and freshness passes. View/schema changes must pass **code review** across producer, steward, and security teams, plus permission tests for every consumer role.

## 11. Sharing Multiple Data Products: Authorized Datasets and BigQuery Sharing

An **authorized view** fits when a handful of views need source read access. With hundreds of views, an **authorized dataset** authorizes *all current and future views* in a dataset—requiring strict control over **who can create or edit views in that authorized dataset**.

**BigQuery sharing** (formerly **Analytics Hub**) is a **data exchange/listing/subscription** platform suited for publishing datasets via controlled discovery and subscription, internally or across organizations. Consumers get a **linked dataset** instead of copying data per project; never assume this grants PII access to every subscriber. Source IAM, policy tags, row filtering, and governance layers must still be designed and approved per supported capabilities.

| Mechanism | Best-Fit Scenario | Trade-Off to Govern |
|---|---|---|
| **Dataset/table IAM** | Group permitted to read detailed data directly | Broad access, lacks narrow purpose scoping |
| **Authorized view** | Sharing a specific subset of columns/rows/aggregates | Must review SQL and source authorization |
| **Authorized dataset** | Many authorized views sharing an owner | New views automatically inherit source read path |
| **Row policies** | Multiple groups on one table, each seeing a row slice | Union-of-policies, performance, and grantee audits |
| **Column tags/masking** | Consistent column-level PII protection across queries | Taxonomy/data policies and group/role semantics |
| **BigQuery sharing** | Publishing via data exchange with publisher/subscriber lifecycle | Listings/subscriptions/linked datasets and IAM must be controlled |
| **Knowledge Catalog data products** | Discovery, glossaries, contracts, access requests | Metadata **never replaces** actual BigQuery permissions |

**Start with the simplest option:** for a dashboard needing only aggregated revenue, the lab's authorized view is easy to understand, slow to churn, and straightforward to test. Do not spin up a data exchange or complex data mesh just to show two metrics to one team.

## 12. Java Cloud Run: Running Queries as the Consumer Identity

A Java 17+ service reads revenue via the BigQuery client using the **ADC** of its Cloud Run runtime service account. The runtime SA needs only `roles/bigquery.jobUser` on **QUERY_PROJECT** and `roles/bigquery.dataViewer` on **sales_public/view**. Never use a Sales producer JSON key or broad IAM impersonation to power dashboards.

In a Maven/Gradle project using Google Cloud Java libraries, add `com.google.cloud:google-cloud-bigquery`. The example below creates a job in the right project/location, parameterizes dates, and **queries only the authorized view**:

~~~java
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.BigQueryOptions;
import com.google.cloud.bigquery.FieldValueList;
import com.google.cloud.bigquery.Job;
import com.google.cloud.bigquery.JobId;
import com.google.cloud.bigquery.JobInfo;
import com.google.cloud.bigquery.QueryJobConfiguration;
import com.google.cloud.bigquery.QueryParameterValue;
import com.google.cloud.bigquery.TableResult;
import java.util.UUID;

public final class RevenueReader {
    public static void main(String[] args) throws InterruptedException {
        String queryProject = "company-analytics-lab";
        String dataProject = "company-sales-lab";
        String location = "asia-southeast1";
        BigQuery bigquery = BigQueryOptions.newBuilder()
            .setProjectId(queryProject).build().getService();

        // Table identifier controlled by server config, never taken from HTTP input.
        String sql = """
            SELECT sale_date, region, paid_orders, revenue_minor
            FROM `DATA_PROJECT.sales_public.v_paid_daily`
            WHERE sale_date BETWEEN @start_date AND @end_date
            ORDER BY sale_date, region
            """.replace("DATA_PROJECT", dataProject);

        QueryJobConfiguration query = QueryJobConfiguration.newBuilder(sql)
            .addNamedParameter("start_date",
                QueryParameterValue.date("2026-11-18"))
            .addNamedParameter("end_date",
                QueryParameterValue.date("2026-11-18"))
            .setUseLegacySql(false)
            .setMaximumBytesBilled(500_000_000L)
            .build();

        JobId jobId = JobId.newBuilder()
            .setProject(queryProject)
            .setLocation(location)
            .setJob("sales_view_" + UUID.randomUUID())
            .build();
        Job job = bigquery.create(JobInfo.newBuilder(query)
            .setJobId(jobId).build()).waitFor();

        if (job == null || job.getStatus().getError() != null) {
            throw new IllegalStateException(
                "BigQuery job failed or no longer exists");
        }
        TableResult result = job.getQueryResults();
        for (FieldValueList row : result.iterateAll()) {
            System.out.printf("%s | %s | %d | %d%n",
                row.get("sale_date").getStringValue(),
                row.get("region").getStringValue(),
                row.get("paid_orders").getLongValue(),
                row.get("revenue_minor").getLongValue());
        }
    }
}
~~~

This example is a **minimal console app**, omitting HTTP endpoints, input validation, timeouts/cancellation, pagination, metrics, and end-user authorization. For a real Cloud Run deployment:

- Attach a dedicated **runtime SA** to the service rather than a broad default service account.
- Cloud Run is an HTTP security boundary; **just because the Java API runs under an SA permitted to query the view does not mean every HTTP caller is authorized to see the dashboard**.
- Bound queries with date ranges/parameters, rate limits, and budgets; never concatenate user-supplied table names into dynamic SQL.
- Cross-project queries bill to `QUERY_PROJECT`; track job IDs, P95 latency, bytes billed, and Cloud Logging without logging PII or tokens.
- Use Google Groups/IAM or workload identity rather than key files in containers; periodically audit runtime principals and source/view permissions.

## 13. Monitoring Permissions, Quality, Cost, and Change Trails

A governance program that exists only on slides will miss **new inherited permissions**, **view SQL edits**, or **wrong numbers after a backfill**. Monitor both the data plane and control plane:

| Signal | Question to Answer | Owner |
|---|---|---|
| BigQuery IAM / dataset ACL | Can anyone besides the owner read `sales_private`? | IAM / Sales owner |
| Authorized views/datasets | Which views are authorized on the source? Any unexpected new views? | Sales owner |
| Row access policies | Active filters, grantees, any `TRUE` or overlapping grants? | Security / data steward |
| Policy tags / data policies | Which PII columns are protected, and who holds Fine-Grained/Masked Reader? | Privacy / security |
| Query jobs metadata | Who runs jobs, in which project, and how many bytes processed/billed? | SRE / FinOps |
| Data quality | DQ pass rate, duplicate IDs, missing dates, reconciliation mismatches | Data engineering |
| Freshness | Is Day D data available before 08:00 D+1? | Producer |
| Catalog metadata/lineage | Are owner, SLA, and downstream dashboards still accurate? | Data steward |
| Cloud Audit Logs | Who changed grants, view SQL, row policies, or dataset settings? | Security / SRE |
| Billing | Are query/storage/scan/metadata/governance costs exceeding budget? | FinOps |

### BigQuery Query Jobs Audit

~~~sql
-- Run in the exact location, e.g., asia-southeast1.
-- Restricted to principals permitted to inspect project-wide jobs.
SELECT
  creation_time,
  job_id,
  user_email,
  project_id,
  total_bytes_processed,
  total_bytes_billed,
  total_slot_ms,
  error_result
FROM `QUERY_PROJECT.region-asia-southeast1.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND job_type = 'QUERY'
ORDER BY creation_time DESC
LIMIT 50;
~~~

**Reading project-wide job metadata can expose sensitive SQL, principals, and usage patterns.** Do not grant `JOBS_BY_PROJECT` across the board to every analyst; for users inspecting their own queries, use `JOBS_BY_USER`/job APIs per permissions. Enable billing budgets and alerts by labels/project/owner; avoid running unbounded-byte queries in frequent checks.

### Separated Cost Attribution

~~~text
DATA_PROJECT:
  BigQuery table storage, view metadata
  + ingestion/loads, source DML, quality scans/lineage metadata
QUERY_PROJECT:
  query compute (on-demand bytes or reservations/slots)
  + Java Cloud Run/API workloads, dashboard refreshes
Shared infrastructure:
  Cloud Logging/Monitoring, networking, optional Catalog features
~~~

**Authorized views do not copy data**, yet querying a view still processes underlying tables and scans bytes. Row-level policies and masking also carry performance/cost trade-offs depending on the query. Using a separate `QUERY_PROJECT` for chargeback neither transfers ownership of `DATA_PROJECT` nor caps spend automatically—you still need quotas, budgets, `maximum_bytes_billed`, query validation, and monitoring.

## 14. Runbook When Users See the Wrong Data or Access Fails

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| `Access Denied: User does not have permission to create jobs` | Missing `roles/bigquery.jobUser` on **QUERY_PROJECT** | Job project, caller's effective IAM |
| `Access Denied` on `sales_public.v_paid_daily` | Missing Data Viewer on view/dataset | Consumer group/SA, `dataViewer` bindings |
| Permitted on view, denied on source table | View not authorized in `sales_private` or source permissions changed | Source dataset Sharing → Authorized views |
| Analyst can read `customer_email` in raw | Inherited Data Viewer from project/folder/org/table or overly broad role | Effective IAM, project/folder/org policies |
| View returns few or zero rows | `HAVING COUNT(*)>=2`, data not loaded yet, source policy, or SQL violates contract | Reconcile as domain owner identity |
| APAC tester also sees EMEA | Second policy with OR/TRUE, override role, or testing as admin identity | Row policy list/grantees, effective roles |
| APAC tester sees zero rows | Not in group, policy not propagated, missing table Data Viewer, or no matching rows | Group membership and policies/SQL |
| PII column readable in raw unexpectedly | Taxonomy not enforced, tag missing on column, Fine-Grained Reader too broad | Policy tags/data policies and IAM |
| Masked reader denied | Missing masking data policy or Masked Reader not bound to that policy | Data policy IAM, column tag |
| Has IAM, job blocked by perimeter violation | VPC Service Controls ingress/egress or org policy | Perimeter logs, project boundaries |
| Job fails with `Location mismatch` | Source/view/query job in incompatible locations | Dataset locations, job location |
| Queries suddenly get expensive | Dashboard lost partition filter, view SQL changed, broad scan | Job metadata, bytes/slot-ms, view version |
| Catalog shows product, query fails | Discovery metadata is not BigQuery IAM | Access request approval and real IAM bindings |
| Dashboard wrong after backfill | Source CDC/dedup changed or contract semantics shifted | Quality checks, lineage, snapshots, owner |

**Access-troubleshooting order:** confirm user identity → query project → `jobUser` → view/table Data Viewer → source authorization → RLS/column/masking → location/perimeter. Never "fix" IAM by granting `roles/owner` or opening the source dataset just to get past a 403. **Data-bug troubleshooting order:** check contract → source snapshot → view SQL → cohort suppression/row policies → pipeline/quality → dashboard.

## 15. Taking Data Products to Production Without Leaking Data

1. **Define domain:** owner/steward, glossary, intended use, PII classification, output schema, and retention period.
2. **Project/dataset design:** separate private sources from the publishing layer; verify locations, Shared VPC/CMEK/VPC-SC if used by the organization.
3. **Data contract and SQL review:** lock metric semantics, timezone, currency, freshness, and schema version; add unit tests.
4. **Security review:** grant permissions to the right groups/SAs on the **right source/view/query projects**; never use Project Viewer/Editor as a substitute for dataset controls.
5. **Authorize view:** source table owner authorizes the view; run positive and **negative** tests with real identities.
6. **RLS/masking as needed:** apply to specific tables/columns and test interactions with authorized views and multi-role groups.
7. **Metadata and DQ:** register the product in Knowledge Catalog; configure glossary, owner, lineage, quality rules, scorecard, and notifications.
8. **Canary:** switch one staging dashboard to the new view and verify outputs, P95 latency, bytes billed, and permitted users.
9. **Production cutover:** update catalog, access contract, and owner alerts; enforce time-bounded grants or periodic access reviews.
10. **Rollback:** point dashboards back to the prior approved view/version; **never delete sources or strip IAM broadly** while other consumers depend on them; treat data exposure as a security incident.

### Changing View SQL Is a Product Change

If `v_paid_daily` adds a `store_id` column, small cohorts can leak store-level information. Changing `COUNT(*) >= 2` to `>= 1` keeps access on the **same view** while altering its privacy guarantee. Require domain owner/steward reviews, disclosure testing, and versioned contracts—IAM does not audit SQL semantics automatically.

## 16. Pre-Handover Verification Checklist

- [ ] Domain owner and steward have named leads, responsibilities, and contact/on-call details.
- [ ] Raw/sensitive data and published analytics live in datasets with **distinct permissions**.
- [ ] `DATA_PROJECT` and `QUERY_PROJECT` have clear locations, billing, and project ownership.
- [ ] Consumers hold only `jobUser` in the query project and `dataViewer` on published resources.
- [ ] Authorized view is explicitly authorized by the **source dataset**; consumers hold no direct source grants.
- [ ] Tested **view query = OK** and **raw PII query = DENIED** using real identities.
- [ ] RLS testing uses a separate dataset or pre-protected table **before** granting viewer access.
- [ ] Policy tags/masking cover sensitive fields and are tested across raw/masked/denied roles.
- [ ] Audited inherited permissions across org/folder/project; no overly broad Editor/Owner roles.
- [ ] Data contract specifies metrics, timezone, currency, schema version, freshness, and quality.
- [ ] Knowledge Catalog metadata includes glossary/owner/lineage or an active update workflow.
- [ ] DQ checks, reconciliation, and alerts run under a dedicated **quality SA**.
- [ ] Java/BI dashboards use ADC and least-privilege service accounts; no JSON credentials in code.
- [ ] Audit logs, query job/billing dashboards, and periodic access review/revocation mechanisms exist.
- [ ] Rollout/backfill/revocation plans avoid breaking unrelated downstream dashboards.

## 17. Applied Exercises

**Exercise 1 — Identify domains.** A company has orders, customer records, inventory, and revenue reports. Sketch 4 domains, name owner/steward/producer/consumer roles, and define at least two data products with data contracts.

**Exercise 2 — Project layout.** Design `sales-private`, `sales-public`, and `analytics-query` as in the lab. Explain why private/public datasets must differ, why the query project needs no source Data Viewer, and what breaks when users hold inherited folder-level roles.

**Exercise 3 — Scoped IAM.** An analyst has `roles/bigquery.dataViewer` on `sales_public` yet cannot create query jobs. Name the missing permission, **which project** needs it, and why not to grant `BigQuery Admin`.

**Exercise 4 — Authorized view.** Create `v_paid_daily` per the lab and authorize it on `sales_private`. Using a real consumer identity, prove the view returns two rows while querying `customer_email` from the source table is denied. If the source query succeeds, what is your next step?

**Exercise 5 — Row-level security.** Group APAC sees only 3 rows and group EMEA sees only 3 rows. Write two `CREATE ROW ACCESS POLICY` statements and explain why someone belonging to both groups sees 6 rows.

**Exercise 6 — Column masking.** User A reads raw emails, B reads masked emails, and C cannot read the column. Propose taxonomy/tags, Fine-Grained Reader, Masked Reader, and test cases; explain how this differs from an authorized view that omits emails completely.

**Exercise 7 — Data contract.** The business changes revenue from "paid gross" to "net of refunds" and requires EUR alongside USD. List all versioned updates needed: schema, currency/FX, dashboards, glossary, data quality, and privacy review.

**Exercise 8 — Data quality.** The source table receives a duplicate `order_id`, a negative `amount_minor`, and a 3-hour pipeline delay. Write three SQL quality assertions and describe quarantine, alerting, and blocking bad product publication.

**Exercise 9 — Catalog vs. permissions.** An analyst sees "Sales Paid Revenue v1" in Knowledge Catalog, yet `SELECT` returns 403. List checks in order from access-request approval, `jobUser`, `dataViewer`, and authorized view up to project perimeter.

**Exercise 10 — Java runtime.** Java Cloud Run in `QUERY_PROJECT` needs to read a view in `DATA_PROJECT`. List at least two IAM bindings, ADC usage, query parameters, avoiding user-supplied table names, and where to inspect jobs/billing.

**Exercise 11 — Permission and cost audit.** A team granted `BigQuery Data Viewer` on the entire Sales project to the Analysts group to fix a dashboard. Build a plan to revoke it, audit dependents, replace with an authorized view, and monitor query costs.

**Exercise 12 — View-change incident.** A producer accidentally adds `customer_email` to an authorized view while consumers can query it. Write a runbook: assess scope, halt access, roll back the view, trace audit/query jobs, evaluate incident notification, and tighten review gates.

## Official References

- [BigQuery IAM roles](https://cloud.google.com/bigquery/docs/access-control) — Job User, Data Viewer, Data Owner, and scopes.
- [Grant access to datasets](https://cloud.google.com/bigquery/docs/control-access-to-resources-iam) — role inheritance, dataset/table/view controls.
- [GoogleSQL GRANT/REVOKE](https://cloud.google.com/bigquery/docs/reference/standard-sql/data-control-language) — `GRANT roles/bigquery.dataViewer ON SCHEMA`.
- [Create authorized views](https://cloud.google.com/bigquery/docs/create-authorized-views) — creating views and source authorization.
- [Authorized views](https://cloud.google.com/bigquery/docs/authorized-views) — consumer/job-project permissions and security interactions.
- [Authorized datasets](https://cloud.google.com/bigquery/docs/authorized-datasets) — sharing a set of views and view-editing caveats.
- [Introduction to row-level security](https://cloud.google.com/bigquery/docs/row-level-security-intro) — row filters and policy unions.
- [Manage row access policies](https://cloud.google.com/bigquery/docs/managing-row-level-security) — `CREATE ROW ACCESS POLICY`, IAM, auditing.
- [ROW_ACCESS_POLICIES information schema](https://cloud.google.com/bigquery/docs/information-schema-row-access-policies) — inspecting policy predicates.
- [Column-level security](https://cloud.google.com/bigquery/docs/column-level-security) — policy tags, fine-grained reads.
- [BigQuery data masking](https://cloud.google.com/bigquery/docs/column-data-masking) — masked data policies/readers.
- [Knowledge Catalog](https://cloud.google.com/knowledge-catalog/docs) — formerly Dataplex Universal Catalog, glossary/aspects/lineage.
- [Knowledge Catalog data products](https://cloud.google.com/knowledge-catalog/docs/data-products-overview) — product contracts and access workflows.
- [Knowledge Catalog data quality](https://cloud.google.com/knowledge-catalog/docs/use-auto-data-quality) — scans, rules, quality metrics.
- [BigQuery sharing](https://cloud.google.com/bigquery/docs/analytics-hub-introduction) — formerly Analytics Hub; data exchanges/listings/subscriptions.
- [JOBS_BY_PROJECT metadata](https://cloud.google.com/bigquery/docs/information-schema-jobs) — query auditing and cost.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) — query compute/storage and billing model selection.
