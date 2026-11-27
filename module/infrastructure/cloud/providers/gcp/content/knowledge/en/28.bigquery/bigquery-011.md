# Row-Level Security, Column-Level Security, and Data Masking in BigQuery

A company has an `orders` table containing multi-region orders, customer email addresses, and revenue. The APAC analytics team should only see APAC orders; finance can view all orders and raw emails; analysts only need masked emails. Relying on people to remember `WHERE sales_region = 'APAC'` or omit the email column in SQL means a single query mistake can leak data.

**BigQuery** provides three complementary control layers beyond standard IAM:

- **Row-level security (RLS):** restricts which **rows** a user can query via row access policies.
- **Column-level security (CLS):** restricts which **columns** a user can read in raw form via policy tags and fine-grained permissions.
- **Dynamic data masking:** lets authorized groups view **masked values** instead of raw column values using data policies.

This lesson belongs to the **BigQuery** chapter of the `CLOUD_PROVIDERS_GCP` module. The outcome is a data governance design applicable across pipelines from Cloud Storage, Pub/Sub, Cloud Run/GKE, and Cloud SQL into BigQuery analytics: least-privilege access, auditing, query verification, and cost control. Mutating commands are strictly for an **approved lab project**—never run them against production tables.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish project/dataset/table IAM from query-time RLS, CLS, and masking.
2. Create row access policies with GoogleSQL DDL, understanding **deny by default** and **OR** semantics across policies.
3. Use **policy tag taxonomies** and `roles/datacatalog.categoryFineGrainedReader` to protect raw column values.
4. Use **data policies** and `roles/bigquerydatapolicy.maskedReader` to grant access to masked values.
5. Understand how RLS, CLS, and masking interact, plus limitations around views, queries, exports, and partition pruning.
6. Design multi-identity tests proving zero data leakage.
7. Operate policies via CLI/SQL, manage IAM, review audit logs, and control query costs.

## 1. Where Do the Three Control Layers Apply?

~~~mermaid
flowchart LR
    A["Principal + BigQuery job IAM"] --> T["Table query permission"]
    T --> R["Row access policies<br/>filter visible rows"]
    R --> C["Column policy tags / data policies<br/>raw, masked, denied"]
    C --> Q["SQL output per caller permissions"]
~~~

| Layer | Question | Example |
| --- | --- | --- |
| **IAM** | Can the caller create a query job and read the table? | `bigquery.jobs.create` + `bigquery.tables.getData` |
| **RLS** | Which **rows** can the caller see? | APAC team sees only `sales_region='APAC'` |
| **CLS** | Can the caller read **raw column values**? | Only finance/PII stewards see unmasked `customer_email` |
| **Masking** | If denied raw values, can the caller see a **masked value**? | Analysts see nullified/hashed/partially masked emails |

**Permission at one layer never substitutes for another.** Being listed in an RLS policy does not grant job-creation or table-read rights. Holding `bigquery.dataViewer` does not unlock a policy-tagged column. Holding Masked Reader does not expose rows excluded by RLS.

### 1.1. Desired Access Matrix Example

Table `bq_governance_lab.orders`:

| Group | Rows | Email | Revenue |
| --- | --- | --- | --- |
| `analytics-apac` | APAC only | Masked | Readable per table access |
| `analytics-emea` | EMEA only | Masked | Readable per table access |
| `finance` | All regions | Raw | Readable |
| `unapproved` | Zero rows or denied | Denied | Denied |

Assume the approved groups hold **baseline table access**; RLS and masking further narrow access. Group and domain names in this lab are placeholders—**not real email addresses**—and must be replaced with existing principals before creating policies.

## 2. How Does Row-Level Security Work?

A row access policy attaches directly to a **table** and defines:

- A policy name unique within the table.
- A list of granted users/groups/service accounts (`GRANT TO`).
- A filter expression (`FILTER USING`), similar to a `WHERE` clause.

Example:

~~~sql
CREATE ROW ACCESS POLICY apac_orders
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('group:analytics-apac@example.com')
FILTER USING (sales_region = 'APAC');
~~~

In BigQuery Studio, **replace `PROJECT_ID` and the group address with real lab values**; keep the backticks around the table identifier per GoogleSQL syntax. Creating a policy requires row-access policy admin permissions, table read access, and job-creation permissions.

**As soon as a table has any row access policy, users not covered by a matching policy lose access to all rows**, even if they previously had table read permissions. Therefore, create a dedicated `TRUE` filter for admins/ETL pipelines needing full access **before enabling restrictive filters**.

~~~sql
CREATE ROW ACCESS POLICY full_for_finance
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('group:finance@example.com')
FILTER USING (TRUE);
~~~

`TRUE` grants **all rows**, while remaining subject to **column-level CLS and masking** as well as table IAM. Never use `allAuthenticatedUsers` or `TRUE` for overly broad groups.

### 2.1. Multiple Policies Combine with OR, Not AND

If a user belongs to **two groups**, BigQuery grants the union of rows allowed by **any** matching policy: **OR**, not AND.

~~~sql
-- An analyst in both the APAC group and the VIP group sees:
-- (sales_region='APAC') OR (segment='VIP').
CREATE ROW ACCESS POLICY vip_orders
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('group:analytics-apac@example.com')
FILTER USING (segment = 'VIP');
~~~

If the intent is "only VIP **within APAC**," combine both conditions into **the same policy**:

~~~sql
FILTER USING (sales_region = 'APAC' AND segment = 'VIP')
~~~

**Risk:** adding a broad policy can **expand** the rows a user sees. Treat every policy edit with the same rigor as an IAM change.

## 3. Identity-Based RLS Policies: Use with Care

You can use `SESSION_USER()` in the filter expression to match rows to the active caller:

~~~sql
CREATE ROW ACCESS POLICY own_orders
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('domain:example.com')
FILTER USING (owner_email = SESSION_USER());
~~~

This works when every row has a trustworthy `owner_email`. For many-to-many user–region mappings or management hierarchies, you can use a **subquery row access policy** referencing a protected mapping table. However, subquery policies carry **extra limitations**: Storage Read API support, masking compatibility, and filterable columns can differ from simple predicates. For workloads needing **CLS + masking**, prefer **simple filter predicates** or verify official compatibility before introducing subqueries.

Never trust a client-populated `owner_email` column without validation; RLS is only as reliable as the **integrity of the filter column**.

## 4. IAM for Policy Authors and Query Callers

| Role / Permission | Purpose |
| --- | --- |
| `roles/bigquery.admin` / `roles/bigquery.dataOwner` | Administer tables and row access policies within scope |
| `roles/bigquery.jobUser` | Create query jobs in the granted project |
| `roles/bigquery.dataViewer` | Read data in granted tables/datasets |
| `roles/bigquery.filteredDataViewer` | **Automatically managed** by BigQuery for `GRANT TO` grantees in row policies |
| `roles/datacatalog.categoryAdmin` | Create/manage taxonomies and policy tags |
| `roles/datacatalog.categoryFineGrainedReader` | View raw values of policy-tagged columns |
| `roles/bigquerydatapolicy.admin` | Create/administer BigQuery data policies |
| `roles/bigquerydatapolicy.maskedReader` | View masked values per granted data policy |

**Never grant `roles/bigquery.filteredDataViewer` manually via IAM.** BigQuery manages this role internally for row access policies. Table-level IAM must still be granted separately.

Administrators should separate duties: **Data Owner** manages schemas/tables, **Security/Data Policy Admin** manages classifications and masking, and **analysts** receive only query rights plus scoped rows and columns. Never give every Cloud Run app a service account with `bigquery.admin` just to avoid permission errors.

## 5. Column-Level Security: Taxonomies and Policy Tags

Under **Data Catalog policy tags**, an enterprise defines a classification **taxonomy**, for example:

~~~text
Taxonomy: commerce-classification
├── PUBLIC
├── INTERNAL
└── SENSITIVE
    ├── PII_EMAIL
    └── PII_PHONE
~~~

Attaching policy tag `PII_EMAIL` to column `customer_email` causes BigQuery to enforce column-level authorization on queries. Teams permitted to read **raw values** receive `roles/datacatalog.categoryFineGrainedReader` on the appropriate policy tag or taxonomy.

**Note:** a policy tag is a **governance resource** (a full resource name), not a descriptive string in `OPTIONS(description=...)`. A column takes **one policy tag** in this model; access can inherit down the taxonomy hierarchy.

### 5.1. CLS Configuration Workflow

1. Choose a **taxonomy region matching the BigQuery data location**, such as `asia-southeast1`. The taxonomy project must belong to an organization per feature requirements.
2. Create the taxonomy and policy tags in the Console (**Policy tag taxonomies**) or via the Data Catalog API.
3. Select tag `PII_EMAIL` and **enable access control enforcement** / attach data policies per the supported UI and edition flow.
4. Grant `Fine-Grained Reader` to finance/PII stewards on the scoped tag.
5. Attach the tag to `customer_email` in the BigQuery table schema.
6. Test queries under **real team identities** and inspect audit logs.

If a user has table read access without column access, `SELECT customer_email` fails with **Access Denied**. `SELECT *` also fails if it touches a protected column the caller cannot read; explicitly project allowed columns or use `SELECT * EXCEPT(customer_email)`.

### 5.2. Attaching a Policy Tag via `bq` Schema

In your **lab** terminal, export the current schema:

~~~bash
bq show --schema --format=prettyjson \
  PROJECT_ID:bq_governance_lab.orders > orders-schema.json
~~~

On the `customer_email` column object, add the `policyTags` field with the real resource name:

~~~json
{
  "name": "customer_email",
  "type": "STRING",
  "mode": "NULLABLE",
  "policyTags": {
    "names": [
      "projects/PROJECT_ID/locations/asia-southeast1/taxonomies/TAXONOMY_ID/policyTags/TAG_ID"
    ]
  }
}
~~~

**This is only one column entry**, not the entire schema file. Keep all other columns and properties intact when updating:

~~~bash
# WARNING: mutates real table schema.
bq update PROJECT_ID:bq_governance_lab.orders orders-schema.json
~~~

Before updating, back up the original schema, verify the taxonomy/tag resource name, and confirm `bigquery.tables.setCategory` plus `datacatalog.taxonomies.get` permissions. Never overwrite a production schema using a single-column file.

## 6. Dynamic Data Masking: Queryable Without Exposing Raw Values

**Data masking** uses a **data policy** to bind a masking rule to principals. At query time, BigQuery returns transformed values to callers holding Masked Reader who lack raw read permissions.

~~~mermaid
flowchart TD
    T["Column customer_email has policy tag PII_EMAIL"] --> IAM{"What permission does principal hold?"}
    IAM -->|"Fine-Grained Reader via hierarchy"| RAW["Raw email"]
    IAM -->|"Masked Reader via data policy"| MASK["Masked email"]
    IAM -->|"No matching permission"| DENY["Access denied"]
~~~

Permission mapping example:

| Group | Permission on `customer_email` | Expected Result |
| --- | --- | --- |
| Finance | Matching Fine-Grained Reader | `alice@demo.invalid` |
| Analyst | Masked Reader on email policy | `aXXXX@...` or `NULL` per mask rule |
| Unapproved | Neither raw nor masked permissions | Column query rejected |

**Watch evaluation order when users belong to multiple groups:** policy tag **hierarchy** can cause raw or masked access to win depending on which tag level carries the binding. Never simply assume "Fine-Grained Reader always wins" under inherited bindings; test overlapping group memberships explicitly.

### 6.1. Common Masking Rules

| Rule | Behavior | Caveat |
| --- | --- | --- |
| **Nullify** | Returns `NULL` | Cannot distinguish or group distinct underlying values |
| **Default masking value** | Type-specific default placeholder | Not usable as accurate analytical values |
| **Email mask** | Preserves partial email structure | Can still leak domain or prefix hints |
| **First/last four characters** | Exposes 4 leading/trailing chars; masks middle | Requires compatible data type |
| **Hash (SHA-256)** | Deterministic digest of value | Enables linking identical values; **not encryption** |
| **Random hash** | Per-query random salt | Supported only on data policies attached **directly to columns**, unlike policy tags |
| **Date year mask** | Preserves year only | Drops month/day precision |
| **Custom masking routine** | Custom UDF for masking | Check permissions, types, and limits |

Hashing and masking do not replace **encryption**, tokenization, or access governance over raw data. For low-entropy values (phone numbers, postal codes), deterministic hashes remain vulnerable to inference/dictionary attacks. Masking also does not automatically render a dataset legally **anonymized** for all compliance purposes.

## 7. Creating Data Policies and Attaching Masking Rules

There are **two supported deployment paths**; pick one and stay consistent within an environment:

**Path A — Policy tags (common for centralized classification):**

1. Create taxonomy/tag `PII_EMAIL`.
2. Attach the tag to the email column.
3. Under **Policy tag taxonomies → Manage Data Policies**, create a data policy with a rule, such as **Email mask**.
4. Grant `roles/bigquerydatapolicy.maskedReader` to the analyst group on the **data policy**.
5. Grant `Fine-Grained Reader` separately to teams permitted raw access.
6. Verify by querying as each target identity, not only an admin account.

**Path B — Direct column-level data policies (no taxonomy required):** BigQuery Data Policy API v2 and DDL support creating policies and attaching them to a column's `data_policies` option. Some policy-management SQL syntax may be **Pre-GA/Preview**, so confirm availability in your edition/region before production adoption.

Illustrative **direct-attachment example** using `ALWAYS_NULL` per documentation:

~~~sql
-- Replace PROJECT_ID with your real lab project; match location.
CREATE DATA_POLICY `PROJECT_ID.region-asia-southeast1.email_null_lab`
OPTIONS (
  data_policy_type = "DATA_MASKING_POLICY",
  masking_expression = "ALWAYS_NULL"
);

ALTER TABLE `PROJECT_ID.bq_governance_lab.orders`
ALTER COLUMN customer_email SET OPTIONS (
  data_policies += [
    "{'name':'PROJECT_ID.region-asia-southeast1.email_null_lab'}"
  ]
);
~~~

Creating and attaching the policy **does not automatically grant Masked Reader** to analysts. Data policy IAM must be granted at the proper scope via Console/API—avoid project-wide grants. Raw read access can be granted via `RAW_DATA_ACCESS_POLICY`/fine-grained mechanisms matching the direct path. **Never mix policy tags and direct data policies on the same column without verifying compatibility.**

If using **data governance tags (Resource Manager tags)** instead of policy tags, note that it is a separate ABAC mechanism with its own feature/support matrix; do not assume Resource Manager tag names substitute for Data Catalog taxonomy resource names.

## 8. Combining RLS, CLS, and Masking: Scenarios to Test

Suppose an analyst in `analytics-apac` has table Data Viewer, Masked Reader on email, and an `APAC` RLS policy.

| Query | Expected Result |
| --- | --- |
| `SELECT order_id, sales_region, total FROM orders` | Only APAC rows, permitted columns |
| `SELECT customer_email FROM orders` | Only APAC rows, masked emails |
| `SELECT * FROM orders` | Succeeds if caller has **raw or masked** permission on every protected column |
| `SELECT * EXCEPT(customer_email) FROM orders` | Does not require access to excluded email column |
| Query for regions outside APAC | EMEA/AMER rows hidden by RLS |
| User lacking table Data Viewer | **Access denied** before row/masking policies help |
| User has Data Viewer, no raw/masked email role | Query selecting email fails with **Access denied** |

**RLS is applied before masking** in query semantics. Data masking has restrictions when **RLS uses a subquery**; per documentation, masking is compatible only with queries using **non-subquery row access policies**. If an RLS filter reads a CLS-protected column, verify the required Fine-Grained Reader access on that column.

### 8.1. Do Not Leave Views, Extracts, or Copies as Bypass Paths

- **Authorized views** offer another way to expose approved subsets, though their interaction with RLS/CLS/masking must be tested carefully.
- **Extract jobs** on RLS-protected tables export only rows the caller can read per supported rules. Do not assume exports solve every governance requirement around masked columns.
- Anyone permitted to **drop policies, alter schemas, or read copies/exports/raw sources** can bypass masked query paths. Govern **derived tables, scheduled queries, extracts, backups, destination buckets**, service account IAM, and audit logs.
- **Legacy SQL**, table previews, and some BI Engine / materialized view / Storage Read API capabilities have limited compatibility with RLS or masking; check feature limitations for every pipeline consumer.

## 9. Lab: Creating a Sample Table Without Real Data

**Run only in a lab project with Billing and permission to create BigQuery datasets/tables.** Use `asia-southeast1` consistently across dataset, taxonomy, and data policies. Never use real customer emails or orders.

### 9.1. Preflight

~~~bash
gcloud auth list
gcloud config get-value project
bq ls --project_id=PROJECT_ID

# Inspect configuration and permissions before writing:
gcloud services list --enabled --project=PROJECT_ID \
  --filter="name:bigquery.googleapis.com"
~~~

### 9.2. Create the Dataset and Table in BigQuery Studio

Run GoogleSQL in **BigQuery Studio** with **Processing location = asia-southeast1** and replace `PROJECT_ID`. Table names in SQL blocks use backticks; after replacing the project ID, you can use identifiers like `demo-project.bq_governance_lab.orders`.

~~~sql
CREATE SCHEMA IF NOT EXISTS `PROJECT_ID.bq_governance_lab`
OPTIONS (location = "asia-southeast1");

-- DO NOT run CREATE OR REPLACE TABLE on non-lab data.
CREATE OR REPLACE TABLE `PROJECT_ID.bq_governance_lab.orders` (
  order_id STRING,
  sales_region STRING,
  customer_email STRING,
  customer_phone STRING,
  total NUMERIC,
  segment STRING
);

INSERT INTO `PROJECT_ID.bq_governance_lab.orders`
(order_id, sales_region, customer_email, customer_phone, total, segment)
VALUES
('o-001', 'APAC', 'a@demo.invalid', '0000000001', 125000, 'REGULAR'),
('o-002', 'EMEA', 'b@demo.invalid', '0000000002', 450000, 'VIP'),
('o-003', 'APAC', 'c@demo.invalid', '0000000003', 220000, 'VIP'),
('o-004', 'AMER', 'd@demo.invalid', '0000000004', 80000, 'REGULAR');
~~~

The **synthetic data** has 2 APAC rows, 1 EMEA row, and 1 AMER row. If an `orders` table already exists in the environment, **do not use `OR REPLACE`**; pick a new lab name or get owner approval.

### 9.3. Grant Table IAM Before Enabling RLS

To test queries under distinct accounts, grant job creation on the project and **Data Viewer on the lab dataset/table** to the three approved groups. An IAM administrator should apply these bindings—never grant project-wide Editor/Owner just for a demo.

Create or verify **real groups** replacing `finance@example.com`, `analytics-apac@example.com`, and `analytics-emea@example.com`. Non-existent principals cause `CREATE ROW ACCESS POLICY` to fail.

### 9.4. Create the Row Access Policies

~~~sql
-- Create the full-access policy first to preserve ETL/admin access.
CREATE ROW ACCESS POLICY finance_all
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('group:finance@example.com')
FILTER USING (TRUE);

CREATE ROW ACCESS POLICY apac_only
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('group:analytics-apac@example.com')
FILTER USING (sales_region = 'APAC');

CREATE ROW ACCESS POLICY emea_only
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('group:analytics-emea@example.com')
FILTER USING (sales_region = 'EMEA');
~~~

**Verify via CLI:**

~~~bash
bq ls --row_access_policies \
  PROJECT_ID:bq_governance_lab.orders

bq show --schema --format=prettyjson \
  PROJECT_ID:bq_governance_lab.orders
~~~

Expect APAC principals to see 2 rows, EMEA to see 1 row, finance to see 4 rows, and users without a matching row policy to be **denied row access**. **Always test as each target identity**, rather than inferring results from an admin's query, because admins may hold broader roles.

## 10. Lab: Restricting Raw Emails to Finance Only

Continuing from Section 9:

1. Under Data Catalog policy tag taxonomies in `asia-southeast1`, create taxonomy `commerce_lab` and tag `PII_EMAIL`.
2. Enable column-level access enforcement for the taxonomy/tag in the Console.
3. Grant `Fine-Grained Reader` on tag `PII_EMAIL` to the `finance` group.
4. Attach `PII_EMAIL` to `customer_email` on the lab table.
5. As an **APAC account without Fine-Grained Reader**, run `SELECT customer_email`: it must be denied before any masking policy is added.

**Never use your admin account to simulate an "unauthorized user."** Admins often hold Data Owner, Fine-Grained Reader, or policy-edit rights; test with a real security principal carrying exact target IAM.

### 10.1. Enable Masking for Analytics Groups

1. On tag `PII_EMAIL`, select **Manage Data Policies**.
2. Create data policy `mask_email_analyst_lab` with a rule such as **Email mask** or **Nullify**.
3. Grant **BigQuery Masked Reader** on the data policy to `analytics-apac` and `analytics-emea`; avoid broad project roles.
4. Query again as both analysts: only RLS-permitted rows appear, with email masked. As finance, raw emails appear via Fine-Grained Reader on the tag.
5. Run `SELECT order_id, sales_region, total` to confirm public columns remain accessible.

**Security expectation:** APAC analysts **cannot** retrieve raw emails; finance sees raw emails but does not bypass RLS without a `TRUE` policy; unapproved identities see zero data. With Nullify, email values return `NULL` while the column keeps its original schema type.

## 11. Positive and Negative Test Checklist

| Test Case | Outcome to Prove |
| --- | --- |
| APAC analyst queries unprotected columns | Exactly **2** APAC rows |
| EMEA analyst queries | Exactly **1** EMEA row |
| Finance with `TRUE` policy | All **4** synthetic rows |
| Analyst queries email before masked role | **Access denied** |
| Analyst queries email after masked role | **Masked** email, not raw |
| Finance queries email | Raw values, not unexpectedly masked |
| User with table Data Viewer only, no row policy | Cannot access protected rows |
| Analyst in both APAC and EMEA | **Union** of both policies (3 rows); explicitly approved |
| Analyst has raw policy tag but no table access | Still **Access denied** |
| ETL SA lacks `TRUE` row policy | Copy/transform job drops rows or fails |
| Sensitive columns via view/export/scheduled query | No derived asset widens data exposure |
| Policy or masking rule change | Change log, test results, and rollback ready |

**Testing order:** table/job IAM → RLS rows → CLS/masking columns → view/export/BI outputs. If `SELECT *` fails, test selecting only non-sensitive columns to isolate whether the block comes from CLS rather than RLS.

## 12. Operations: Safely Editing, Inspecting, and Cleaning Up Policies

All security policy edits must pass through code review and change approval. For RLS:

~~~sql
-- Replaces the definition and grantee list for a named policy.
CREATE OR REPLACE ROW ACCESS POLICY apac_only
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('group:analytics-apac@example.com')
FILTER USING (sales_region = 'APAC' AND segment = 'VIP');
~~~

**Warning:** this mutates live permissions; if you instead add a second policy, multiple policies **OR** together. Never assume adding a narrower policy restricts overall access while broader policies still exist.

Clean up the lab after owner confirmation:

~~~sql
-- WARNING: dropping all row policies removes row-level protection!
DROP ALL ROW ACCESS POLICIES
ON `PROJECT_ID.bq_governance_lab.orders`;
~~~

BigQuery **does not let you drop the last remaining policy with a single `DROP ROW ACCESS POLICY`**; you must use `DROP ALL ROW ACCESS POLICIES` to remove RLS completely. That can **re-open all rows to anyone holding table Data Viewer**, so run it only after revoking IAM or putting replacement protections in place.

To delete taxonomies, policy tags, or data policies, clean up **column attachments, raw/masked bindings, and referencing data policies** in dependency order. Never delete a production taxonomy to troubleshoot an analyst's permission error.

## 13. Auditing, Monitoring, and Cost

### 13.1. Verifying Query Outcomes and Access Controls

- **BigQuery Jobs / INFORMATION_SCHEMA** show jobs, callers, bytes processed, and errors; they do not replace **Cloud Audit Logs** for policy admin actions and data access trails.
- **BigQuery Job API** provides `rowLevelSecurityStatistics.rowLevelSecurityApplied` to indicate row access policies ran on queried tables; this field **does not prove masking rules worked**—verify with test identities.
- **Cloud Audit Logs** record queries and policy edits per audit log settings/permissions; configure alerts on changes to row policies, taxonomies, policy tags, or data policies.
- Audit **data lineage and derived assets**: authorized views, scheduled queries, destination tables, Cloud Storage extracts, and BI connectors.

Example job query in **BigQuery Studio** (requires job metadata permissions and matching location):

~~~sql
SELECT creation_time, user_email, job_id,
       total_bytes_processed, total_slot_ms,
       error_result.message AS error_message
FROM `PROJECT_ID.region-asia-southeast1.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND job_type = 'QUERY'
ORDER BY creation_time DESC
LIMIT 100;
~~~

Never paste query results containing PII into public incident tickets; record only job IDs, request IDs, policy versions, and safe metrics.

### 13.2. Pricing and Query Optimization

**RLS has no separate per-feature surcharge**, yet queries still incur **BigQuery compute costs** by bytes processed or slots/reservations. Row policy filters do not automatically trigger **partition pruning**; to limit scanned partitions, users must include **`WHERE` predicates on the partition column** in their queries. Subquery row policies can scan mapping tables too, adding cost.

**Masking** can alter bytes scanned; Nullify/Default rules may avoid scanning raw column bytes in some queries. Never promise "masking always lowers bills" or "RLS always makes queries faster." Track real metrics in **Billing Reports/INFORMATION_SCHEMA**, balancing SLO latency and bytes processed.

## 14. Common Implementation Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Analyst sees more regions than intended | User matches multiple `GRANT TO` lists; policies OR together | Audit every policy applying to that user |
| Nobody except admins sees rows | Missing `TRUE` policy or wrong grantee | Add scoped full-access policy and retest |
| RLS policy creation fails | Group doesn't exist, missing IAM, unsupported expression | Check principals and permissions |
| RLS active yet `SELECT *` errors | Policy-tagged column lacks raw/masked access | Check CLS/data policy; query permitted columns |
| Analyst sees raw email | Fine-Grained Reader granted too broadly or inherited | Audit hierarchy and policy bindings |
| Masking does not apply to email | Tag/policy not attached to column, or Masked Reader missing | Check schema/data policies and principal |
| ETL/export job drops rows | Service account lacks `TRUE` row access policy | Review SA permissions and business requirements |
| Table preview stops working | RLS does not support table preview | Run a query under an authorized identity |
| Storage Read API query fails | Incompatible RLS subquery policy or masking | Use simple filters or a supported query path |
| Queries become more expensive | Missing partition pruning alongside RLS, or subquery table scans | Add partition filters to user queries and measure bytes |
| Admin test passes, analyst fails | Different principal, IAM, and policy bindings | Test under the real user or service account |
| Dropping policy leaks data | `DROP ALL` exposes rows to existing table viewers | Enforce change review, revoke IAM / prepare rollback |

## 15. End-to-End Scenario: Multi-Region Sales Data

**Context:** Commerce uses Cloud Run to ingest orders, Pub/Sub for events, and Dataflow/BigQuery for analytics. A central BigQuery table holds customer emails and regional revenue. Requirements:

- APAC analysts see only APAC orders, with masked emails.
- Finance sees all regions and raw emails.
- ETL services continue operating across the entire table.
- BI dashboards never expose raw PII.
- Compliance can audit who changed policies and when.

**Recommended architecture:**

~~~mermaid
flowchart LR
    SRC["Cloud Run / Dataflow"] --> T["BigQuery orders table"]
    T --> ROW["RLS by sales_region"]
    ROW --> COL["CLS policy tag PII_EMAIL"]
    COL --> MASK["Masking data policy"]
    MASK --> A["APAC analyst<br/>APAC rows + masked email"]
    MASK --> F["Finance<br/>all rows + raw email"]
    T --> AUD["Audit Logs + Jobs + Billing"]
~~~

Implementation steps:

1. Assign data owners, classify PII, and document residency/country rules.
2. Tighten baseline table IAM, create role-based groups/service accounts, and identify accounts needing full access.
3. Enable regional RLS and test every identity, especially overlapping group memberships.
4. Attach the policy tag to email and verify denial before granting Masked Reader.
5. Grant masked/raw access as needed; verify via BigQuery Studio, BI tools, and ETL connectors.
6. Set up logging/alerts for policy changes and audit derived tables/sinks.
7. Monitor query costs and run periodic audits so policies do not silently drive excessive scanning.

**Definition of success:** analysts cannot read raw emails or out-of-region rows, while finance/ETL operate across their authorized scope with verified test and audit evidence. Never treat an admin query screenshot as proof.

## 16. Exercises and Self-Check Questions

**Exercise 1 — Testing RLS.** Using the four-order dataset in Section 9, create APAC and EMEA policies and query as both groups.

*Pass criteria:* APAC sees 2 rows, EMEA sees 1 row; zero cross-region leakage.

**Exercise 2 — Overlapping Permissions.** A user belongs to both the APAC and EMEA groups. How many rows are visible?

*Answer:* 3 rows (union of both policies), assuming valid table IAM.

**Exercise 3 — Protecting Email.** Attach the policy tag and query email as an analyst before and after granting Masked Reader.

*Pass criteria:* Denied before; masked value after; finance sees raw values with Fine-Grained Reader.

**Exercise 4 — Auditing ETL.** A service account must copy/transform the entire table, has Data Viewer, yet sits outside every RLS policy. Why might the job fail or drop rows?

*Answer:* Because table IAM does not replace row policies. Grant an approved `TRUE` policy to that SA.

**Question 5.** Does RLS apply to rows or columns?

*Answer:* Rows; CLS/masking controls columns.

**Question 6.** Do two RLS policies for the same user combine with AND or OR?

*Answer:* OR. For AND, combine conditions inside the same filter.

**Question 7.** Should you manually grant `roles/bigquery.filteredDataViewer` to fix a query error?

*Answer:* No. BigQuery manages that role internally via row access policies.

**Question 8.** Is `SELECT *` safe when a user lacks permission on a sensitive column?

*Answer:* It can trigger Access Denied; select only permitted columns or grant appropriate raw/masked permissions.

**Question 9.** Does SHA-256 masking replace encryption and anonymization in all cases?

*Answer:* No. Deterministic hashes allow value correlation and inference.

**Question 10.** Are a data policy and a policy tag the same resource?

*Answer:* No. A tag classifies/labels columns; a data policy defines masking rules and raw/masked access bindings.

**Question 11.** Does a BigQuery RLS filter automatically trigger partition pruning for user queries?

*Answer:* No. User queries still need explicit partition filters.

**Question 12.** Is RLS compatible with all Storage Read API, Legacy SQL, and materialized view features?

*Answer:* No. Feature- and policy-specific restrictions apply; check documentation.

**Question 13.** Why is testing solely with an admin account insufficient?

*Answer:* Admins hold different IAM/policies from analysts, masking configuration bugs.

**Question 14.** What can happen when dropping the last row access policy using `DROP ALL`?

*Answer:* It removes row-level protection; anyone still holding table IAM can suddenly see more rows.

## 17. Production Deployment Checklist

- [ ] PII tables/columns classified with assigned owners and documented data inventory/lineage.
- [ ] Least-privilege table/job IAM separating policy admins from data consumers.
- [ ] RLS includes a scoped `TRUE` policy for approved admin/ETL groups—never broad grants.
- [ ] Team understands **OR** policy combination; overlapping memberships and deny-by-default tested.
- [ ] CLS policy tags/taxonomies match data location; Fine-Grained Reader scoped tightly.
- [ ] Masking rules reviewed against threat models; Masked Reader bound to specific data policies.
- [ ] Evaluated **policy tag** vs. **direct data policy** / data governance tag paths consistently.
- [ ] Positive/negative tests executed with real identities across BI, ETL, and Storage Read API as applicable.
- [ ] Masking is not treated as full cryptographic encryption or legal anonymization.
- [ ] Change reviews and backup/rollback scripts exist for editing, granting, revoking, or dropping RLS, tags, or data policies.
- [ ] Derived tables, authorized views, scheduled queries, exports, and backups audited.
- [ ] Audit Logs, job metadata, `rowLevelSecurityApplied`, and query failures monitored.
- [ ] Bytes scanned, partition pruning, slot usage, and Billing tracked continuously.
- [ ] Staging verification precedes production policy changes; zero real PII hardcoded in labs.

## 18. Conclusion

**RLS protects rows; CLS protects raw columns; masking exposes controlled masked representations.** Together they form layered identity-based access controls, yet they must pair with sound IAM, accurate data classification, governance over derived assets, and real-identity testing.

In BigQuery, an effective policy is more than valid DDL syntax: you must prove that **the right people see the right rows and columns in the allowed form, unauthorized callers are denied, and pipelines, costs, and audits remain safe**.

## Official References

- [Introduction to row-level security](https://cloud.google.com/bigquery/docs/row-level-security-intro)
- [Use row-level security](https://cloud.google.com/bigquery/docs/managing-row-level-security)
- [RLS with other BigQuery features](https://cloud.google.com/bigquery/docs/using-row-level-security-with-features)
- [Introduction to column-level access control](https://cloud.google.com/bigquery/docs/column-level-security-intro)
- [Restrict access with column-level security](https://cloud.google.com/bigquery/docs/column-level-security)
- [Introduction to data masking](https://cloud.google.com/bigquery/docs/column-data-masking-intro)
- [Mask column data](https://cloud.google.com/bigquery/docs/column-data-masking)
- [BigQuery DDL: CREATE DATA_POLICY](https://cloud.google.com/bigquery/docs/reference/standard-sql/data-definition-language)
- [BigQuery IAM roles and permissions](https://cloud.google.com/bigquery/docs/access-control)
- [BigQuery INFORMATION_SCHEMA JOBS](https://cloud.google.com/bigquery/docs/information-schema-jobs)
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing)
