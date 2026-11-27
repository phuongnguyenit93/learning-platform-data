# BigLake and Querying Data Outside BigQuery

A training platform stores raw learning events as **Parquet/CSV in Cloud Storage**. The analytics team wants to use BigQuery SQL to aggregate learner lesson completions without loading a copy of the entire dataset into BigQuery every time a new file arrives. Meanwhile, the governance team does not want to grant every analyst direct read access to a bucket containing sensitive data. **BigLake tables** solve both needs: querying data that resides outside BigQuery storage and **delegating source access through a Cloud resource connection**.

In the **Data Governance and Analytics** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson connects IAM, Cloud Storage, BigQuery, VPC, and data processing services (Dataflow/Spark) to choose the right external access type, enforce least privilege, and manage data freshness, performance, and cost. The primary example uses **GoogleSQL** with a **BigLake external table over Cloud Storage**; this is not a guide for copying data into BigQuery native tables.

**After this lesson, you will be able to:**

1. Distinguish between a **BigLake table**, a standard external table, an object table, a federated query, and an Iceberg managed table.
2. Explain **access delegation** via a connection service account and design IAM so consumers cannot bypass the table.
3. Create and query a BigLake external table over Cloud Storage files using SQL and test permissions for data owners and analysts.
4. Choose formats, schemas, file layouts, Hive partitioning, and metadata caching based on workload.
5. Identify consistency, DML, location, and cost limitations, and determine when to **load into BigQuery**.
6. Troubleshoot 403 errors, missing files, and slow queries, and practice with mock data.

## 1. Map of Ways BigQuery Queries External Data

BigQuery can **store table metadata/schema** while the actual data resides in Cloud Storage or another system. Depending on the source and purpose, you must choose the right resource type.

| Access Method | Typical Sources | How Permissions Are Granted | Best Suited When |
| --- | --- | --- | --- |
| **BigLake external table** | Cloud Storage; Amazon S3/Azure Blob via BigQuery Omni as supported | **Access delegation** via a connection and IAM on the BigLake table | A data lake requiring governance, SQL, and controlled sharing |
| **Non-BigLake external table** | Cloud Storage, Bigtable, Google Drive | The querying user typically needs permissions on **both the table and the external source** | Ad hoc exploration or sources that do not support BigLake |
| **Object table** | Unstructured files in Cloud Storage | Connection service account; rows reflect **object metadata** | Searching/classifying images, documents, and videos |
| **Federated query** | Cloud SQL, AlloyDB, Spanner, or supported databases | Connection to the database; `EXTERNAL_QUERY` or appropriate external dataset | Joining/reading operational data still residing in the source DB |
| **BigQuery native table** | Data loaded/written into managed BigQuery storage | IAM at dataset/table/view level | Repeated queries, performance optimization, BigQuery-native management |
| **Apache Iceberg managed table** | Iceberg-formatted data in a user-managed bucket | Connection + BigQuery-managed table/catalog per product | A lakehouse needing an open format **and writes/updates via DML** |

**Critical distinction:** a BigLake external table over Parquet/CSV is **not** the same as an **Iceberg managed table**. Standard external tables in this model are **read** by BigQuery and do not support `INSERT`/`UPDATE`/`DELETE` into source files via DML. Iceberg managed tables have their own metadata lifecycle, DML support, and storage optimization; do not use the `CREATE EXTERNAL TABLE` example here and assume you created an Iceberg managed table.

### 1.1. BigLake Does Not Move Source Files

~~~mermaid
flowchart LR
    ETL["Dataflow / Spark<br/>writes Parquet"] --> GCS["Cloud Storage<br/>raw/curated objects"]
    OWNER["Data steward"] --> BQ["BigQuery BigLake table<br/>schema, metadata, IAM"]
    BQ -->|"Cloud resource connection<br/>service account"| GCS
    A["Analyst / BI"] -->|"SQL + table permissions"| BQ
    BQ --> R["Query result"]
~~~

**Source data remains in the bucket.** The `CREATE EXTERNAL TABLE` operation only declares a table pointing to the objects; it does not automatically create an ingest pipeline, copy files, or rewrite schemas on existing files.

### 1.2. When to Choose Another Option?

- **Small CSV, one-off analysis:** a non-BigLake external table or direct load can be simpler when source permission separation is unnecessary.
- **Large Parquet, multiple teams reading with tiered permissions:** a BigLake table + connection + row/column policies is a strong candidate.
- **Repeated low-latency dashboards running continuously:** benchmark **loading into a BigQuery native table** or materializing a curated layer; external tables add source-read overhead.
- **Google Sheets/Bigtable data:** use the appropriate external table; **do not** pick a BigLake Cloud Storage table just because of the "BigLake" name.
- **Querying Cloud SQL/AlloyDB directly:** evaluate `EXTERNAL_QUERY` and that system's connection; external SQL has its own dialect and limitations.

## 2. Access Delegation: Separating Table Read Access from Bucket Read Access

### 2.1. Permission Diagram

~~~mermaid
flowchart TB
    U["Analyst: query only"] -->|"bigquery.jobs.create<br/>on job project"| JOB["BigQuery query job"]
    U -->|"bigquery.tables.getData<br/>on BigLake table"| T["BigLake table"]
    T -->|"Connection ID"| C["Cloud resource connection"]
    C -->|"Identity: connection service account"| S["Cloud Storage bucket/prefix"]
    OWNER["Data owner"] -->|"Create table, grant permissions<br/>and audit"| T
    OWNER -->|"Grant storage.objects.get/list<br/>to connection SA"| S
    U -. "No Storage Object Viewer" .-> S
~~~

With a **non-BigLake external table**, the analyst needs permissions on the table **and** the Cloud Storage objects (or corresponding source). With a **BigLake table**, the connection has its **own service account** to read the files, while the analyst only needs query job and table read permissions. This forms the foundation for enforcing **row-level/column-level** policies in BigQuery without granting users read access to raw files.

| Principal | Typical Minimum Permissions | Scope |
| --- | --- | --- |
| Connection creator | `bigquery.connections.create` permission or appropriate Connection Admin role | Project/location containing the connection |
| BigLake table creator | `bigquery.tables.create` and appropriate `bigquery.connections.delegate` | Approved dataset and connection |
| **Connection service account** | `roles/storage.objectViewer` or required object get/list permissions | Approved bucket/managed folder |
| Analyst | `roles/bigquery.dataViewer` on the **table** + `roles/bigquery.jobUser` on the job project | No permissions granted on the source bucket |
| Ingestion pipeline | Write permissions on approved prefixes | Does not need BigQuery Admin if only writing lake data |

The **job project** can differ from the project containing the table. The principal creating the query job needs `bigquery.jobs.create` on the **project running the job**, while data read permissions are checked at the table. BigQuery IAM granted at the project/folder/organization level can **inherit** down to many tables: inspect all bindings, not just direct table permissions.

### 2.2. Bypass Paths to Lock Down

Even with a properly secured BigLake table, data owners must avoid granting analysts:

1. **Direct Storage Object Viewer** on the raw data bucket: they could download files directly and bypass BigQuery filters/masking.
2. **Permissions to arbitrarily create or bind tables to a connection** (such as connection delegate/admin permissions): they could declare a new table without data masking policies.
3. `bigquery.objectRefs.read` permission on the connection when ObjectRef functions are in use: this can create an object-read path bypassing BigLake table controls.
4. Broad permissions inherited from other groups, service account impersonation, or previously exported data copies.

The connection service account should have the **smallest bucket scope needed for the workload**; if one connection can read an entire multi-tenant bucket, anyone permitted to delegate that connection has a large blast radius. Separate buckets by sensitivity/owner or use supported managed folders and IAM conditions where appropriate; verify effective permissions with IAM Policy Troubleshooter and negative tests.

**Do not confuse** the connection service account with the analyst's account or a Cloud Run service account submitting queries: each principal operates at a different layer. Never store JSON keys for the connection SA; BigQuery manages this identity.

## 3. Designing the Data Source Before Creating the Table

### 3.1. Choosing Formats Based on Query Needs

| Format | Strengths | Limitations to Consider |
| --- | --- | --- |
| **Parquet** | Columnar storage, compression, strong schema and column pruning | Too many tiny files or inconsistent schemas slow queries down |
| **ORC** | Columnar storage, suited for analytical data | Must verify data types and pipeline compatibility |
| **Avro** | Clear schema and record representation | For queries selecting only a few columns, can underperform Parquet |
| **CSV** | Easy to inspect, test, and exchange | Heavy parsing, implicit types, delimiter/quote/null edge cases |
| **Newline-delimited JSON** | Easy to write semi-structured data | Larger size, schema drift/inconsistent field types |

Cloud Storage external tables support the formats above per official documentation. For large data pipelines, **Parquet + partitioning by date/query pattern** is typically a worthwhile baseline to benchmark, though that does not mean every format or every query will be faster.

**One external table** can reference multiple schema-compatible files via a URI wildcard, such as `gs://lake/curated/enrollments/*.parquet`. Misnamed files or mismatched schemas are not automatically fixed by BigLake. Avoid leaving temporary files, manifests, old versions, or different-format files inside the wildcard folder.

### 3.2. Data Location and Consistency

Choose the **BigQuery dataset location, Cloud resource connection location, and bucket location** according to Google Cloud's colocated/supported locations rules. For simple labs, place all three in the **same region**. Do not assume a `US` multi-region name is equivalent to any single-region bucket; only use product-supported location pairings that satisfy data residency.

**External data does not have the same consistency semantics as BigQuery native tables.** If a pipeline is writing, renaming, or deleting files while a query runs, results can be inconsistent: queries may see an out-of-sync mix of old and new files or encounter read errors. To publish data safely, prefer:

1. Writing files to a dedicated **staging prefix** keyed by `run_id`.
2. Validating schema, row counts, checksums/manifests, and permissions.
3. Updating the **table URI/definition** or publication pointer through a controlled process only after the data is complete.
4. Never overwriting objects currently being queried; use immutable files and intentional retention/rollback.

For workloads requiring consistent snapshots and complex transaction management, consider an **Iceberg managed table** or loading into BigQuery native instead of treating a wildcard directory as a transactional table.

### 3.3. Folder Layout and Hive Partitioning

A common layout:

~~~text
gs://LEARNING_LAKE/curated/enrollments/
  event_date=2026-11-17/part-0000.parquet
  event_date=2026-11-18/part-0000.parquet
  event_date=2026-11-19/part-0000.parquet
~~~

A BigLake external table can declare **Hive partitioning** to speed up file discovery and read fewer partitions:

~~~sql
-- GoogleSQL: architectural example, do not run without lab data/prefix.
CREATE EXTERNAL TABLE `PROJECT_ID.lake_curated.enrollments_partitioned` (
  event_id STRING,
  tenant_id STRING,
  course_id STRING,
  status STRING
)
WITH PARTITION COLUMNS (event_date DATE)
WITH CONNECTION `PROJECT_ID.asia-southeast1.lake_connection`
OPTIONS (
  format = 'PARQUET',
  uris = ['gs://LEARNING_LAKE/curated/enrollments/*'],
  hive_partition_uri_prefix = 'gs://LEARNING_LAKE/curated/enrollments',
  require_hive_partition_filter = TRUE
);
~~~

When querying, filtering `event_date` with a literal or parameter enables **partition pruning**:

~~~sql
SELECT course_id, COUNT(*) AS enrollments
FROM `PROJECT_ID.lake_curated.enrollments_partitioned`
WHERE event_date = DATE '2026-11-18'
  AND status = 'ACTIVE'
GROUP BY course_id;
~~~

**Do not keep `event_date` as both a Hive partition column and a duplicate physical field in the table schema** if the engine/schema does not support duplicate declarations. `require_hive_partition_filter` prevents queries from scanning the entire lake when predicates are omitted. Designing overly granular partitions (such as by `event_id`) increases metadata/file overhead and complicates management.

## 4. Lab: BigLake Table on Cloud Storage with Access Delegation

**Objective:** use an **assigned lab bucket/dataset**, create a connection and BigLake table over mock events, and verify that an analyst can query via the table while **unable to read the files directly**. The resource creation commands below may incur charges; run them only in an **approved lab project**. Do not apply these example permissions in production.

### 4.1. Roles and Resources

Required setup:

- Dedicated **lab project, bucket, and BigQuery dataset**, with billing and the BigQuery Connection API enabled by an administrator as needed.
- Bucket and dataset in the same region, e.g., `asia-southeast1` if supported.
- A **data steward** principal permitted to create connections, grant IAM to the connection service account, and create tables; these tasks may be split across corresponding admins.
- A **lab analyst** principal with only `bigquery.jobs.create` on the job-execution project and `bigquery.tables.getData` on the specific lab table.
- Mock data with no real emails, card numbers, passwords, or learner personal data.

**Read-only preflight** before creating anything:

~~~bash
export PROJECT_ID="YOUR_APPROVED_LAB_PROJECT"
export LOCATION="asia-southeast1"
export BUCKET="YOUR_EXISTING_LAB_BUCKET"
export DATASET="biglake_demo_lab"
export CONNECTION_ID="lake_lab_connection"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project
gcloud storage buckets describe "gs://$BUCKET"
bq ls --project_id="$PROJECT_ID"
bq ls --connection --project_id="$PROJECT_ID" --location="$LOCATION"
~~~

Do not proceed if the dataset/connection name collides with someone else's resources or if the bucket fails location/security requirements. If you lack permission to create a connection or the API is disabled, notify the owner; **do not grant yourself Project Owner or enable APIs in production**.

### 4.2. Create a Mock CSV and Upload to a Dedicated Prefix

Example local file `events.csv`:

~~~csv
event_id,tenant_id,course_id,status,event_date
ev01,t-lab,java-basic,ACTIVE,2026-11-18
ev02,t-lab,java-basic,ACTIVE,2026-11-18
ev03,t-lab,python-basic,ACTIVE,2026-11-18
ev04,t-lab,java-basic,CANCELLED,2026-11-18
ev05,t-lab,python-basic,ACTIVE,2026-11-19
~~~

Upload only if `gs://$BUCKET/biglake-demo/$RUN_ID/` is a **new prefix owned by the lab**:

~~~bash
export RUN_ID="demo-run-001"  # Change ID if data with the same name already exists.
gcloud storage ls "gs://$BUCKET/biglake-demo/$RUN_ID/"

# WRITE OPERATION: mock file in an approved lab prefix.
gcloud storage cp ./events.csv \
  "gs://$BUCKET/biglake-demo/$RUN_ID/events.csv"
~~~

The expected input has **5 rows**: two `java-basic/ACTIVE` rows on the 18th, one `python-basic/ACTIVE` row on the 18th, one `python-basic/ACTIVE` row on the 19th, and one `CANCELLED` row. Never use `SELECT *` on tables containing real PII for testing.

### 4.3. Create the Cloud Resource Connection

In the confirmed project and region, the **data steward/connection admin** runs:

~~~bash
# WRITE OPERATION: create a dedicated connection for the lab.
bq mk --connection \
  --location="$LOCATION" \
  --project_id="$PROJECT_ID" \
  --connection_type=CLOUD_RESOURCE \
  "$CONNECTION_ID"

# READ-ONLY: retrieve the serviceAccountId auto-generated by BigQuery.
bq show --connection \
  "$PROJECT_ID.$LOCATION.$CONNECTION_ID"
~~~

The `bq show` output contains a `serviceAccountId` field, formatted like:

~~~text
connection-12345-abcde@gcp-sa-bigquery-condel.iam.gserviceaccount.com
~~~

The admin copies the **actual value** from the output rather than using the sample email. Next, grant **Storage Object Viewer** to the connection SA on the **lab** bucket (or a narrower object scope per supported IAM configuration) and inspect the IAM policy:

~~~bash
# Replace with the REAL connection serviceAccountId returned by bq show.
export CONNECTION_SA="CONNECTION_SERVICE_ACCOUNT_FROM_BQ_SHOW"

# PERMISSION CHANGE: executed only by an approved admin.
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$CONNECTION_SA" \
  --role="roles/storage.objectViewer"

# READ-ONLY: verify the binding just applied.
gcloud storage buckets get-iam-policy "gs://$BUCKET"
~~~

**Do not grant bucket permissions to the analyst.** If a shared bucket holds sensitive sources, do not grant access to the whole bucket just for a lab; choose a separate bucket or a prefix-restricted policy that has passed security review. When a connection is deleted, the service account's IAM binding on the bucket is **not necessarily revoked immediately**; cleanup must review and remove the binding.

### 4.4. Create the BigLake External Table via GoogleSQL

The `biglake_demo_lab` dataset must be created **beforehand** by the data owner in the same region as the connection and bucket. In BigQuery Studio (GoogleSQL), replace **project, region, bucket, and run ID** with your lab values, and run using an account permitted to create tables and delegate connections:

~~~sql
-- CREATE TABLE DDL: use only in a dedicated lab dataset.
CREATE EXTERNAL TABLE `YOUR_PROJECT.biglake_demo_lab.events_external` (
  event_id STRING,
  tenant_id STRING,
  course_id STRING,
  status STRING,
  event_date DATE
)
WITH CONNECTION `YOUR_PROJECT.asia-southeast1.lake_lab_connection`
OPTIONS (
  format = 'CSV',
  uris = ['gs://YOUR_EXISTING_LAB_BUCKET/biglake-demo/demo-run-001/events.csv'],
  skip_leading_rows = 1
);
~~~

**Important:** in the sample statement, `lake_lab_connection` and the bucket/project names **must be replaced** with the exact values from the previous step; if you created `lake_lab_connection`, keep that exact name. `skip_leading_rows=1` skips the CSV header; because the schema is explicitly declared, columns are mapped in file order.

Querying the BigLake table:

~~~sql
SELECT
  event_date,
  course_id,
  COUNT(*) AS active_events
FROM `YOUR_PROJECT.biglake_demo_lab.events_external`
WHERE status = 'ACTIVE'
GROUP BY event_date, course_id
ORDER BY event_date, course_id;
~~~

**Expected result:** three result rows: `2026-11-18` with `java-basic` = 2, `2026-11-18` with `python-basic` = 1, and `2026-11-19` with `python-basic` = 1. The data remains in Cloud Storage; this is an on-query aggregation.

### 4.5. Positive/Negative Tests Using Two Identities

The **data owner** grants the lab analyst only:

- `BigQuery Data Viewer` on the **`events_external` table** (not the entire source dataset if it holds other sensitive tables).
- `BigQuery Job User` on the project where the analyst runs queries.
- **No** Storage Object Viewer on the bucket, no connection create/bind permissions, and no role containing `bigquery.objectRefs.read` on the connection.

Test using the **analyst identity itself**, rather than running as the owner and assuming the outcome:

| Test | Expected Result |
| --- | --- |
| `SELECT event_date, COUNT(*) FROM events_external GROUP BY event_date` | **Allowed**, if job and table permissions are correct |
| `gcloud storage cat gs://.../events.csv` as the analyst identity | **Denied** when the analyst lacks bucket read permissions |
| Querying a table outside the granted scope | **Denied** unless inherited permissions exist elsewhere |
| Modifying the table URI/SQL definition to point to another file | **Denied** if the analyst lacks table edit / connection delegate permissions |
| Reading source files via the connection SA through the BigQuery table | **Allowed** per table definition and policies |

If the analyst **succeeds** in reading the bucket directly, inspect IAM at the bucket/project/organization levels, Google Group memberships, impersonation, and previously granted roles; do not treat access delegation as having isolated the source. If the BigLake query returns 403, check **three layers**: job project → table permissions → connection service account/bucket.

### 4.6. Controlled Lab Cleanup

In order: save any non-sensitive results → data owner revokes analyst permissions → delete **only the lab table** → revoke the connection SA's bucket IAM binding → delete **only the lab connection** if no consumers remain → delete `events.csv` and the lab dataset only if you are certain you own them.

~~~bash
# Inspect before deleting; never run destructive commands on shared resources.
bq show "$PROJECT_ID:$DATASET.events_external"
bq show --connection "$PROJECT_ID.$LOCATION.$CONNECTION_ID"
gcloud storage ls "gs://$BUCKET/biglake-demo/$RUN_ID/"

# CLEAN UP EXACT LAB RESOURCES after owner approval:
# bq rm -t "$PROJECT_ID:$DATASET.events_external"
# gcloud storage buckets remove-iam-policy-binding "gs://$BUCKET" \
#   --member="serviceAccount:$CONNECTION_SA" \
#   --role="roles/storage.objectViewer"
# bq rm --connection "$PROJECT_ID.$LOCATION.$CONNECTION_ID"
# gcloud storage rm "gs://$BUCKET/biglake-demo/$RUN_ID/events.csv"
~~~

Delete commands are **commented out** to prevent accidental copy-paste; verify exact resources, owners, and dependencies before uncommenting. Never delete a shared bucket, dataset, or connection just to clean up an exercise.

## 5. Metadata Caching: Faster, But Understand Freshness

For external tables pointing to **very large numbers of files**, each query can spend significant overhead listing and reading object metadata. BigLake supports **metadata caching** to reduce this overhead for supported formats, but it caches **file/partition metadata**, not full query result sets.

Two key options:

| Option | Meaning | Trade-off |
| --- | --- | --- |
| `max_staleness` | Use cached metadata only while the last refresh is within the accepted threshold | Overly stale cache falls back to querying metadata directly |
| `metadata_cache_mode = 'AUTOMATIC'` | Service refreshes automatically on a cycle, typically around 30–60 minutes | Delay in discovering new files depends on the refresh cycle |
| `metadata_cache_mode = 'MANUAL'` | Pipeline/data owner explicitly triggers refresh on schedule/cutover | Forgetting to refresh can serve stale cache or fall back depending on staleness |

Example of **another table** for Parquet (do not replace the CSV lab table in use):

~~~sql
CREATE EXTERNAL TABLE `PROJECT_ID.lake_curated.enrollments_cached`
WITH CONNECTION `PROJECT_ID.asia-southeast1.lake_connection`
OPTIONS (
  format = 'PARQUET',
  uris = ['gs://LEARNING_LAKE/curated/enrollments/*.parquet'],
  max_staleness = INTERVAL 4 HOUR,
  metadata_cache_mode = 'MANUAL'
);
~~~

Once the pipeline has written and verified the files, the data owner can refresh:

~~~sql
-- Run the job in the same BigQuery location as the external table.
CALL BQ.REFRESH_EXTERNAL_METADATA_CACHE(
  'PROJECT_ID.lake_curated.enrollments_cached'
);
~~~

**Key rules:**

- Only set `max_staleness` between **30 minutes and 7 days** when caching is enabled; `0` disables caching.
- If the cache exceeds `max_staleness`, queries can **read metadata from Cloud Storage** instead of using the cache; do not assume this automatically forces queries to fail.
- **Metadata caches expire after 7 days without a refresh.** Manual refresh requires `bigquery.tables.update` and `bigquery.tables.updateData` permissions—do not grant these to all analysts.
- If the **source URI** changes, automatic caching does not necessarily update right away: follow the documented manual refresh procedure (you may need to temporarily switch mode to MANUAL and back to AUTOMATIC).
- Queries through the table may not immediately reflect newly added or deleted objects while metadata remains cached. Define a clear "freshness SLA" and test reads right after pipeline completion.
- Metadata cache refreshes are jobs that can consume resources and incur costs; monitor both refresh performance and cost.

**Do not choose a 7-day staleness** for operational data needing updates every few minutes. Conversely, an immutable Parquet table per accounting close period can accept a longer threshold if the SLA allows it.

## 6. Extensions: Object Tables, Federated Queries, and Iceberg

BigLake is part of the **lakehouse and data governance** ecosystem, but not every external source uses the same table type or API.

### 6.1. Object Tables: Querying Metadata of Unstructured Objects

If a bucket stores certificate images, instructional videos, or PDFs, an **object table** represents files as metadata rows rather than trying to decode videos/PDFs into CSV-like columns. Example:

~~~sql
-- Requires a connection SA with object permissions on an approved bucket.
CREATE EXTERNAL TABLE `PROJECT_ID.lake_curated.course_assets`
WITH CONNECTION `PROJECT_ID.asia-southeast1.lake_connection`
OPTIONS (
  object_metadata = 'SIMPLE',
  uris = ['gs://LEARNING_LAKE/assets/*.pdf']
);
~~~

Object tables let you **filter by metadata/URI/size/type** and combine with supported unstructured data processing tasks. They **do not automatically extract PDF text** or provide full-text search across file contents; you need appropriate pipelines, remote functions, or models and separate permissions.

### 6.2. Federated Queries to Operational Databases

When the latest transactions still live in Cloud SQL/AlloyDB/Spanner, you can use a connection and `EXTERNAL_QUERY` written in the **source database dialect**:

~~~sql
-- GENERAL PATTERN: use only with an admin-approved DB connection.
SELECT *
FROM EXTERNAL_QUERY(
  'PROJECT_ID.asia-southeast1.approved_db_connection',
  'SELECT course_id, COUNT(*) AS cnt FROM enrollments GROUP BY course_id'
);
~~~

This is **not** a BigLake Cloud Storage table. `EXTERNAL_QUERY` sends SQL to the external DB and converts results into corresponding BigQuery types; you must evaluate connection credentials, network/database load, transaction consistency, and latency. On production OLTP systems, a large federated full scan can degrade transactional workloads. Consider copying data to the warehouse or using CDC for heavy reporting workloads.

### 6.3. Apache Iceberg Managed Tables: Open Format and Writing Data

**Apache Iceberg managed tables** (formerly referred to in docs as BigLake tables for Apache Iceberg) let BigQuery manage catalog/metadata while storing data in a **user-owned bucket** in an open format. They support DML, streaming via the Storage Write API per product conditions, schema evolution, and file/metadata optimization.

| Capability | BigLake Parquet/CSV External Table | Apache Iceberg Managed Table |
| --- | --- | --- |
| Data location | Files written by source systems in a bucket | Iceberg data/metadata in a user-owned bucket |
| BigQuery DML | **Does not** modify files directly via `UPDATE`/`DELETE` | **Supported** within managed table capabilities/limits |
| Schema/transactions | File schema controlled by producer; limited external consistency | Metadata/snapshot management per Iceberg and BigQuery |
| Multi-engine access | Can read the same Parquet/ORC files | Reads **Iceberg table metadata** via supported engines |
| Operations | Producer manages layout, schema, publication/cleanup | Service optimizes files/metadata per config; still needs IAM/monitoring |

**Never manually write or delete files under an Iceberg managed table's storage URI** outside supported management mechanisms; doing so can corrupt metadata and snapshots. When a transactional lakehouse is required, evaluate Iceberg managed separately rather than writing scripts to overwrite BigLake external table files.

## 7. Data Policies: Protecting Rows, Columns, and Tenants

BigLake combines **access delegation** with BigQuery's authorization policies. For Cloud Storage BigLake tables, you can apply row-level access policies, column-level policy tags, and data masking depending on supported features and editions.

### 7.1. Tenant-Based Row-Level Security Example

Suppose `events_external` holds multi-tenant data and lab-tenant analysts may only view `tenant_id='t-lab'`:

~~~sql
-- Only a data steward authorized to manage row access policies applies this.
CREATE ROW ACCESS POLICY only_lab_tenant
ON `YOUR_PROJECT.biglake_demo_lab.events_external`
GRANT TO ('group:approved-lab-analysts@example.com')
FILTER USING (tenant_id = 't-lab');
~~~

**This is a policy example**, not required in the lab unless you have a real/approved Google Group. Row policies must be designed **for every principal group needing access**; principals not matching a policy may see only permitted rows or be denied per product rules. Test using **representative identities**, rather than concluding a policy works based only on a high-privilege admin account.

**A table with a row-level policy does not filter the underlying bucket files:** a principal can still read the entire file if they have direct `storage.objects.get`. That is why access delegation and eliminating bypass read paths are core security prerequisites.

### 7.2. Column Policy Tags and Masking

Suppose a file contains `learner_email` and `payment_amount`. A data steward can attach policy tags to restrict raw value reads, grant Fine-Grained Reader under an approved taxonomy, or apply masking rules when only obfuscated values are needed. This mechanism **complements** table-level Data Viewer and does not replace job permission and source checks.

Safe workflow:

1. Classify columns (public/internal/confidential), defining intended use and ownership.
2. Attach policy tags and/or masking policies per BigLake table/location capabilities.
3. Grant raw-value read access to the fewest possible principals; most analysts should read only aggregated or masked data.
4. Test `SELECT` on permitted and restricted columns under different roles.
5. Carefully review **views, exports, or materialized copies**, because copied data requires equivalent protective policies elsewhere.

**Never rely on `SELECT *` as a contract for sharing sensitive data.** Schema evolution can expose newly added columns to table readers or break existing queries. Use **view projections with explicit column lists** over the BigLake table, or curated models tailored to business needs.

### 7.3. Layered Data Permissions

~~~text
Organization policy / VPC Service Controls (if enabled)
    → Project / dataset / BigLake table IAM
    → Query job permission + connection delegation
    → Row policies / column tags / masking
    → Cloud Storage bucket/object IAM of the connection service account
    → Application authorization per user/tenant and audit logs
~~~

Each layer mitigates a different risk. **VPC Service Controls do not replace IAM**, IAM does not automatically enforce per-tenant row filters, and a BigLake row filter does not protect files from a principal who has bucket permissions. For Cloud Run/GKE workloads running queries, use dedicated workload service accounts and never embed static service account keys in source code or container images.

## 8. Performance, Data Availability, and Cost

### 8.1. External Tables Are Not Automatically as Fast as Native Tables

| Issue | How to Assess | Mitigation |
| --- | --- | --- |
| Many tiny files (a few KB) | High file listing/metadata overhead | Compact files into Parquet sizes suited to the workload |
| Queries always scan many days | Missing partition filters, overly broad URI wildcards | Hive partition filters, partition aligned to query patterns |
| Slow CSV parsing | High CPU/bytes scanned | Convert curated data to Parquet/ORC |
| Frequently changing metadata | Stale cache or refresh not yet executed | Establish publication/freshness SLA and refresh post-ETL |
| Dashboards query repeatedly every minute | Re-scanning external data, high p95/cost | Load/materialize hot data into BigQuery native |
| Cross-region data | Network/egress charges, residency/location mismatch | Choose colocated locations and proper regional architecture |
| Queries run while files are deleted/overwritten | Inconsistent results or read errors | Immutable files, staging + publish/rollback |

**BigQuery dry runs** on external sources may not estimate bytes accurately; they sometimes return **0 or a lower bound** even though the real query still incurs charges. Do not rely on dry runs alone to approve a budget. Measure real jobs on lab inputs, bytes billed/processed, Cloud Storage requests/egress, and connection metrics.

### 8.2. Total Cost Model

\[
\text{TCO} \approx
C_{\text{BigQuery query/slots}}
+C_{\text{GCS storage/operations}}
+C_{\text{metadata refresh}}
+C_{\text{network/egress}}
+C_{\text{data pipeline/operations}}
\]

- **BigQuery:** query charges based on on-demand bytes processed or slot/capacity editions depending on the organization.
- **Cloud Storage:** storage, read/list operations, retrieval/egress by storage class and location; colder storage classes may carry retrieval fees.
- **BigLake metadata cache:** refresh jobs/resources and operational scheduling overhead.
- **Multi-cloud:** may incur BigQuery Omni charges, data transfer, and source-platform egress.
- **Access controls:** access delegation does not make data "free"; budgets, quotas, and large-query controls are still required.

**Budget alerts are not hard spending caps.** You can use reservations, quotas, and scoped query permissions to reduce blast radius, and always check official pricing pages for your rates and region at deployment time.

## 9. Runbook: BigLake Queries Failing or Returning Unexpected Data

| Symptom | Possible Cause | Check First |
| --- | --- | --- |
| `Access Denied: bigquery.jobs.create` | Analyst cannot create jobs in the execution project | Verify actual principal and `roles/bigquery.jobUser` IAM on the job project |
| `Access Denied` on BigLake table | Missing `bigquery.tables.getData` or row/column policy block | Check Data Viewer on the table, policy tags, row policies |
| 403 from Cloud Storage | Connection SA lacks object read/list permissions or bucket deny/other policy | `bq show --connection`, bucket IAM, exact object path |
| `bigquery.connections.delegate` error creating table | Table creator lacks delegation permission on the connection | Data steward grants delegate permission on that connection; do not grant project-wide Admin |
| Analyst succeeds in reading source files directly | Bucket/project/group IAM too broad or impersonation | Audit inherited roles and remove bypass paths per review |
| Query does not see new files | Metadata cache not refreshed or URI mismatch | Check `max_staleness`, cache mode, URI wildcard, run manifest |
| Query fails to read a file | Wrong format/schema, file deleted/modified mid-query, permission error | Inspect file listing, schema, object generation, and ETL publication |
| Location mismatch | Dataset, connection, and bucket not colocated | Cross-check supported locations; do not move production buckets arbitrarily |
| Slow or expensive query | Many small files, CSV, missing filters, cross-region, or caching | Query plan/job stats, file layout, partition pruning, bytes |
| `UPDATE` on external table fails | External tables are read-only for BigQuery DML | Use source pipeline, native table, or Iceberg managed table as appropriate |
| `EXTERNAL_QUERY` slow and source DB overloaded | Federation pushes heavy workload onto OLTP | Limit source query, cache/load into warehouse, and monitor DB metrics |

### 9.1. 403 Investigation Order

1. **Identify the actual principal:** the user running `bq`, CI identity, or Cloud Run/GKE runtime service account.
2. **Identify the job project:** does the principal have `bigquery.jobs.create`? Is the job project different from the dataset project?
3. **Check BigLake table permissions:** table ID, dataset location, row/column policies, inherited IAM.
4. **Check the connection:** is the connection ID in the right region? Is delegation granted for table creation? Does the service account ID still exist?
5. **Check Cloud Storage:** does the connection SA have object permissions on the current URI? Are bucket IAM and deny policies correct?
6. **Re-test** using the exact principal and a fresh query, recording the error code (redact bucket names/PII in reports).

Never temporarily grant `roles/editor`, `bigquery.admin`, and `storage.admin` together to resolve a 403—doing so breaks least privilege and can expose raw data.

### 9.2. Inconsistent Query Results

When a query produces unexpected numbers after an ETL run:

1. Compare the expected file count against actual files in the **published prefix**.
2. Determine whether the producer overwrote or deleted files while queries were running.
3. Verify schema and confirm the table references the right URI wildcard and partition/Hive prefix.
4. If metadata caching is enabled, inspect the last refresh time and staleness; the owner runs a manual refresh if appropriate.
5. Reconcile query results against the source manifest, row counts, and sample checksums.
6. Roll back to the previously verified prefix/table definition if needed; do not delete files immediately.

**Freshness issues are not always permissions issues**, and simply re-running the query will not fix stale caches or broken file publication.

## 10. Scenarios and Exercises

### A — Sharing Reports Without Opening the Bucket

An enterprise has 2 TB of Parquet in Cloud Storage. The analytics team may only view statistics on `course_id` and `status`; the sensitive `learner_email` column must not be exposed. The team wants to query via BigQuery without copying raw data.

**Question:** Choose a non-BigLake external table or BigLake? What are the permissions for the analyst and connection SA?

**Guidance:** Choose a **BigLake external table** with a Cloud resource connection. The connection SA reads the bucket/prefix via object permissions; the analyst receives BigQuery Job User on the job project and Data Viewer on the approved BigLake table/view, with **no** direct Storage Object Viewer. Use a view selecting only required columns plus policy tags/masking if protection is needed across multiple queries; verify direct bucket reads are denied.

### B — An Analyst Can Create Arbitrary New External Tables

A data steward grants an analyst group `bigquery.connections.delegate` on a connection that can read an entire multi-tenant bucket. One analyst uses that connection to create a new external table pointing to other files and reads data outside the approved report scope.

**Question:** What design flaw allowed this?

**Guidance:** **Connection delegation/binding permissions** were granted too broadly; the new table does not inherit policies from the reviewed reporting table. Narrow table-creation/delegation permissions, separate connections/buckets by sensitivity, and audit inherited IAM and bypass paths (`storage.objects.get`, ObjectRef). Do not fix only the original view.

### C — Metadata Cache and a 5-Minute Freshness SLA

A pipeline writes new Parquet files every 5 minutes. The BigLake table has `metadata_cache_mode='AUTOMATIC'`, which typically refreshes every 30–60 minutes, and `max_staleness=INTERVAL 4 HOUR`. The product owner requires reports to reflect new files within 5 minutes.

**Question:** Does the current configuration meet the SLA?

**Guidance:** **It cannot be guaranteed** with automatic refresh alone. The metadata cache may not yet reflect newly arrived files. Evaluate disabling the cache (trading off cost/latency), running manual refreshes after each publication, or using a suitable native/streaming sink; measure end-to-end freshness against the SLA rather than merely setting a staleness value.

### D — Queries on the Most Recent Day Are Very Slow

Data resides in millions of CSV files under `gs://lake/events/*`. Dashboards always query **a single day**, yet the table has no partitioning and queries use `SELECT *`.

**Question:** Propose three prioritized improvements.

**Guidance:** (1) Convert curated data to **Parquet**, avoiding tiny files; (2) organize **Hive partitioning** by date and enforce partition filters; (3) select only needed columns, and measure metadata caching and query stats. If dashboards run many times per minute, compare against loading/aggregating into a BigQuery native table.

### E — An "Updatable" Data Lake?

A team wants multiple Spark applications and BigQuery to jointly update enrollment statuses, requiring version rollback and snapshot management. They create a BigLake external table pointing to `events/*.parquet` and attempt an `UPDATE`.

**Question:** What is the appropriate alternative?

**Guidance:** A BigLake external table over raw files **does not support BigQuery DML**. If an open lakehouse with transactions/schema evolution is required, evaluate **Apache Iceberg managed tables** and each engine's supported interoperability scope; or use a native BigQuery table as the update target. Never manually edit files/manifests managed by Iceberg.

### F — Querying Cloud SQL Directly from BigQuery Slows Down OLTP

A BigQuery reporting job calls `EXTERNAL_QUERY` to full-scan the `orders` table on Cloud SQL every 5 minutes. During execution, database CPU spikes and API requests slow down.

**Question:** Will a BigLake Cloud Storage table automatically solve this?

**Guidance:** No. `EXTERNAL_QUERY` is direct federation to the operational DB, distinct from a BigLake table. You need bounded queries/filters, an appropriate read replica, or CDC/ETL landing analytical data into Cloud Storage/BigQuery. Align sync cadence, freshness, and source of truth with business requirements.

### Quantitative Exercise — Metadata and Query Volume

A lake holds **240,000 Parquet files** totaling **12 TiB**. A dashboard runs 50 times per day and needs only 1/24 of the data (one hour of the day). Assume partition pruning eliminates exactly 23/24 of the total data and file sizes are uniformly distributed.

1. **Ideal amount of data remaining to scan per query?** — `12 TiB / 24 = 0.5 TiB`, before column optimizations and overhead.
2. **Without pruning, what is the total logical volume across 50 queries?** — `50 × 12 = 600 TiB`.
3. **With effective pruning, what is the total?** — `50 × 0.5 = 25 TiB`.
4. **Can you immediately convert those numbers into exact billed dollars?** — **No**; column pruning, format, metadata operations, caching, query plans, tiers/capacity/pricing, and byte-measurement rules also apply.
5. **Should you set a 7-day metadata cache if new files arrive every hour?** — Only if that staleness is acceptable and an appropriate refresh schedule exists; do not use a large threshold as a substitute for partitioning.

### Self-Check Questions

1. **Does a BigLake external table store data inside BigQuery storage?** — No; the data stays in the external source.
2. **What is the biggest difference between BigLake and a non-BigLake external table?** — BigLake uses a connection service account to **delegate source access**.
3. **Does a BigLake analyst need Storage Object Viewer on the bucket?** — No, and typically **should not be granted it**.
4. **Why not grant analysts connection delegation permissions?** — They could create their own tables to bypass the approved table's row/column controls.
5. **Are CSV/Parquet files modified mid-query guaranteed to be completely consistent?** — No; not guaranteed like native tables.
6. **Does metadata caching cache query results as well?** — No; it primarily caches file/partition metadata.
7. **Can an external table be `UPDATE`d with BigQuery SQL?** — Not in the standard external table model.
8. **Does an object table automatically parse PDF contents into columns?** — No; it primarily represents object metadata.
9. **Is `EXTERNAL_QUERY` a BigLake Cloud Storage table?** — No; it is federation via a DB connection.
10. **When should you load into BigQuery native?** — When repeated queries require reliable latency/performance or consistency, after benchmarking/TCO analysis.

## 11. BigLake Design and Operations Checklist

| Check | Acceptance Criteria |
| --- | --- |
| **Source type** | Correctly chosen among BigLake, external table, object table, federation, or Iceberg based on format and read/write semantics |
| **Location** | Dataset, connection, and bucket colocated per docs; meets data residency |
| **IAM scope** | Query job permission, table Data Viewer, and connection SA Storage Object Viewer scoped to exact resources |
| **Anti-bypass** | Analysts have no direct storage read, connection delegate/admin, or unnecessary ObjectRef read |
| **Separation of duties** | Data steward approves tables/schemas/policies; ingestion pipeline only writes prefixes; analysts only query |
| **Schema** | Stable format and types, with handling for schema evolution, bad records, and nullable values |
| **File layout** | Parquet/ORC used where appropriate, partitioned by query patterns, small files minimized |
| **Freshness/consistency** | Staging, manifests, controlled publication, cache refreshes, and post-ETL read checks in place |
| **Data security** | Row/column policies, masking, IAM, VPC Service Controls as needed; negative tests passed |
| **Observability** | BigQuery job stats, Cloud Storage metrics, IAM audit logs, and source/connection error tracking |
| **Cost** | Measured bytes/query, storage/requests, metadata refreshes, egress, reservations/budgets |
| **Recovery** | Retained prior prefixes/versions, table definition rollback, safe deletion process, and assigned owner |

### Periodic Delegation Review Process

Quarterly or after every architectural change, the data steward should inventory **who can read BigLake tables**, **who can delegate connections**, **which buckets each connection SA can read**, and **what copies/exports exist**. Revoking a table binding **does not delete** data an analyst already exported earlier. During data exposure investigations, also inspect audit logs, inherited permissions, service account impersonation, and copies.

## 12. Official Google Cloud Documentation

- [Introduction to external data sources](https://cloud.google.com/bigquery/docs/external-data-sources) — overview of BigLake, object tables, non-BigLake external tables, and federation.
- [Introduction to BigLake tables](https://cloud.google.com/bigquery/docs/biglake-intro) — access delegation, supported formats/sources, and security model.
- [Create Cloud Storage BigLake tables](https://cloud.google.com/bigquery/docs/create-cloud-storage-table-biglake) — `CREATE EXTERNAL TABLE`, connections, Hive partitioning, and ACLs.
- [Cloud resource connections](https://cloud.google.com/bigquery/docs/create-cloud-resource-connection) — creating connections and finding `serviceAccountId`.
- [Introduction to external tables](https://cloud.google.com/bigquery/docs/external-tables) — DML limits, consistency, location, and performance.
- [Cloud Storage external tables](https://cloud.google.com/bigquery/docs/external-data-cloud-storage) — CSV, JSON, Parquet, Avro, ORC, and schemas.
- [Metadata caching for external data sources](https://cloud.google.com/bigquery/docs/metadata-caching-external-tables) — staleness, refresh modes, and caching trade-offs.
- [BQ.REFRESH_EXTERNAL_METADATA_CACHE](https://cloud.google.com/bigquery/docs/reference/system-procedures#bqrefresh_external_metadata_cache) — syntax, permissions, and prefix-level refreshes.
- [Object tables](https://cloud.google.com/bigquery/docs/object-table-introduction) — metadata and unstructured objects.
- [Federated queries](https://cloud.google.com/bigquery/docs/federated-queries-intro) — `EXTERNAL_QUERY` and database sources.
- [Apache Iceberg managed tables](https://cloud.google.com/bigquery/docs/biglake-iceberg-tables-in-bigquery) — comparing open-format models with DML.
- [BigQuery IAM](https://cloud.google.com/bigquery/docs/access-control), [row-level security](https://cloud.google.com/bigquery/docs/row-level-security-intro), [column-level security](https://cloud.google.com/bigquery/docs/column-level-security-intro) — data policies.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) and [Cloud Storage pricing](https://cloud.google.com/storage/pricing) — cost estimation.

**Conclusion:** BigLake creates a **metadata, query, and access governance** layer over data residing in Cloud Storage or supported object stores. Its strength is not just SQL access, but **access delegation via a connection service account**: consumers are granted permission on the **table**, without needing permissions on the **source files**. A production design is only trustworthy once you verify **least privilege, zero bypass read paths, valid schemas/locations, data freshness, and total query cost**. For lakehouse DML needs or high-performance dashboards, evaluate **Iceberg managed tables or BigQuery native tables** rather than assuming any external table can replace them.
