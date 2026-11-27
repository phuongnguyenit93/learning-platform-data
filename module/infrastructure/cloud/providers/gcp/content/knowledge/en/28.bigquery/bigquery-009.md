# Materialized Views, BI Engine, and Query Acceleration

A Java application displays a daily revenue dashboard by store. Order data resides in **BigQuery** with hundreds of millions of rows; every page load re-runs the same `GROUP BY` query. To reduce latency and cost, you can **organize the source table** with partitioning and clustering, create a **materialized view** for frequently queried aggregates, and evaluate **BI Engine** for interactive dashboards with eligible queries.

This lesson belongs to the **BigQuery** chapter of the **CLOUD_PROVIDERS_GCP** module, linking data service choices to projects/IAM, Cloud Run/GKE, release automation, reliability, and cost control. The focus is on **diagnosing bottlenecks and choosing the right acceleration mechanism**, not merely memorizing resource creation commands.

After this lesson, you will be able to:

- Distinguish **logical views**, **materialized views (MVs)**, **query-result cache**, and **BI Engine**.
- Create partitioned and clustered tables, aggregate materialized views, and verify result correctness.
- Explain **incremental refresh**, **smart tuning/query rewrite**, `max_staleness`, and cases requiring base table reads.
- Create/adjust a BI Engine reservation by **project and location**, configure preferred tables, and diagnose why a query was not accelerated.
- Read query plans, bytes processed, slot-ms, `materialized_view_statistics`, and `bi_engine_statistics` to evaluate performance.
- Query from a Java application via ADC and least-privilege IAM, avoiding MV permission pitfalls.
- Select solutions based on SLOs, data freshness, refresh/storage/BI capacity costs, and rollback readiness.

> **Lab limits:** project and dataset names are illustrative; commands creating tables, MVs, or reservations must only run in an approved test project. BI Engine reservations can **incur charges even with low query volume**; never enable them in production purely to benchmark. Examples use **GoogleSQL** and a single consistent region.

## 1. Diagnose Before Buying More Capacity

~~~mermaid
flowchart LR
  A["Cloud Run Java API / BI dashboard"] --> Q["BigQuery SQL"]
  Q --> P["Partition pruning + clustering"]
  P --> M["Materialized view: precomputed aggregates"]
  M --> E["BI Engine: in-memory, vectorized"]
  E --> R["Dashboard output"]
  Q --> O["Query plan + JOBS_BY_PROJECT"]
  O --> C["Measure P95, bytes, slot-ms, cache-hit, cost"]
~~~

A slow query can stem from **reading too many bytes**, **heavy shuffles/joins**, **scanning too many partitions**, **slot contention**, **client result transfer time**, or suboptimal SQL. MVs and BI Engine help only when the data and queries are **eligible**; they will not fix a query returning 10 million rows or a Java API bottlenecked on Cloud SQL.

| Mechanism | What It Stores | When Active | Guarantees Speedup for All SQL? |
|---|---|---|---|
| **Partitioning/clustering** | Physical layout of source table data | Queries filter on partition/cluster keys | No; depends on predicates and data layout |
| **Logical view** | Saved SQL definition | Executes SQL at query time | No; does not store results |
| **Materialized view** | Precomputed SQL results and refresh metadata | Direct query or eligible optimizer rewrite | No; depends on SQL shape, freshness, and cost |
| **Query-result cache** | Previous query output | Queries meeting cache-reuse rules | No; can be invalidated or ineligible |
| **BI Engine** | Frequently used columns/data in reserved memory | Supported queries with available capacity | No; may run FULL/PARTIAL/FALLBACK |
| **Slot reservation/edition** | Compute capacity for query jobs | Workloads needing steady compute/concurrency | No; does not eliminate wasteful scans |

The usual priority order is **measure → project columns / prune partitions → filter before JOINs → inspect query plan → consider MV → consider BI Engine**. Avoid provisioning a reservation before knowing which tables and columns dashboards actually query.

## 2. Unified Lab: Store Revenue Dashboard

This example creates a dataset in **`asia-southeast1`**; run in Bash/Cloud Shell with an account authorized to create datasets, tables, and queries in the lab project.

~~~bash
PROJECT_ID="my-bigquery-lab"
LOCATION="asia-southeast1"
DATASET="analytics_lab"

gcloud config set project "$PROJECT_ID"
gcloud services enable bigquery.googleapis.com
bq --location="$LOCATION" mk --dataset "$PROJECT_ID:$DATASET"
~~~

If the dataset already exists, inspect its location and owner—**do not create a duplicate**. A dataset with the same name in another region cannot be queried by jobs in a mismatched location; BI Engine capacity must also match the location. Permissions to create datasets/tables are distinct from reading production data.

### Step 1 — Create a Partitioned Table with Synthetic Data

Run the following SQL script in BigQuery Studio in `asia-southeast1`; replace **`MY_PROJECT`** with your real lab project first:

~~~sql
CREATE OR REPLACE TABLE `MY_PROJECT.analytics_lab.orders` (
  order_id STRING NOT NULL,
  order_date DATE NOT NULL,
  store_id STRING NOT NULL,
  amount NUMERIC NOT NULL,
  status STRING NOT NULL
)
PARTITION BY order_date
CLUSTER BY store_id;

INSERT INTO `MY_PROJECT.analytics_lab.orders`
  (order_id, order_date, store_id, amount, status)
SELECT
  FORMAT('ORD-%06d', n),
  DATE_ADD(DATE '2026-11-01', INTERVAL MOD(n, 14) DAY),
  CONCAT('STORE-', CAST(1 + MOD(n, 10) AS STRING)),
  CAST(10 + MOD(n, 150) AS NUMERIC),
  IF(MOD(n, 7) = 0, 'CANCELLED', 'PAID')
FROM UNNEST(GENERATE_ARRAY(1, 10000)) AS n;
~~~

The dataset contains **10,000 synthetic orders**, 14 days, 10 stores, and two statuses. `NUMERIC` avoids floating-point rounding drift when summing revenue; in real financial systems, define currency, rounding rules, and refunds explicitly. Re-running `INSERT` will **double the rows**; to repeat the lab, use a dedicated test project/table with a controlled reset procedure.

~~~sql
SELECT COUNT(*) AS rows_total,
       COUNTIF(status = 'PAID') AS paid_rows,
       MIN(order_date) AS min_day,
       MAX(order_date) AS max_day
FROM `MY_PROJECT.analytics_lab.orders`;
~~~

**Expected:** 10,000 rows, `min_day = 2026-11-01`, and `max_day = 2026-11-14`. The lab compares **mechanisms** rather than proving speedups on a few thousand rows: on tiny tables, the optimizer may skip an MV simply because scanning the base table is already cheap.

### Step 2 — Baseline Query on the Base Table

~~~sql
SELECT
  order_date,
  store_id,
  COUNT(*) AS paid_orders,
  SUM(amount) AS revenue
FROM `MY_PROJECT.analytics_lab.orders`
WHERE status = 'PAID'
  AND order_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-07'
GROUP BY order_date, store_id
ORDER BY order_date, store_id;
~~~

This query achieves **partition pruning** by filtering `order_date` directly. `CLUSTER BY store_id` helps when queries filter/group by store on tables large enough for block layout to matter. Avoid `SELECT *`, avoid scanning all dates and filtering outside a subquery, and never assume `LIMIT 100` on a large table reduces bytes scanned.

**First measurement:** in BigQuery Console, inspect **Execution details → Query plan**, `total bytes processed`, `slot-ms`, query latency, and cache hit. Identical SQL can vary in runtime due to concurrent jobs, slot availability, and caching; measure multiple times under controlled conditions.

## 3. What Do Materialized Views Solve?

A **materialized view** pre-stores the result of a recurring calculation. For daily revenue, instead of scanning millions of orders and running `GROUP BY` on every dashboard load, queries can read the much smaller precomputed aggregates by `order_date, store_id`.

~~~text
orders (large table, continuously updated)
   │ SELECT order_date, store_id, COUNT(*), SUM(amount)
   ▼
mv_paid_daily (pre-stored aggregates, refreshed)
   │
   ├── Direct SELECT from MV
   └── BigQuery smart tuning: base-table queries rewritten when eligible
~~~

BigQuery supports **incremental materialized views** for eligible SQL patterns. When the base table is mostly **append-only**, BigQuery can refresh only the delta rather than recomputing everything. Updates/deletes or certain joins can invalidate incremental maintenance, trigger full refreshes, or force reads from the base table. **Never assume every materialized view is incremental by default.**

### Step 3 — Create an Aggregate MV with Partition Alignment

~~~sql
CREATE MATERIALIZED VIEW `MY_PROJECT.analytics_lab.mv_paid_daily`
PARTITION BY order_date
CLUSTER BY store_id
OPTIONS (
  enable_refresh = TRUE,
  refresh_interval_minutes = 60
)
AS
SELECT
  order_date,
  store_id,
  COUNT(*) AS paid_orders,
  SUM(amount) AS revenue
FROM `MY_PROJECT.analytics_lab.orders`
WHERE status = 'PAID'
GROUP BY order_date, store_id;
~~~

- `PARTITION BY order_date` on the MV aligns with the base table's partitioning, scoping both refreshes and queries to relevant partitions.
- `CLUSTER BY store_id` clusters on a **non-aggregate output column**, aiding workloads filtered by store.
- `refresh_interval_minutes = 60` requests background refreshes **no more frequently than every 60 minutes**; it is **not a hard SLA** that data will never be more than 60 minutes stale.
- MVs incur storage and refresh compute costs. If source data is tiny or dashboard usage is sparse, overhead may outweigh savings.

### Step 4 — Query Directly and Reconcile Results

~~~sql
SELECT order_date, store_id, paid_orders, revenue
FROM `MY_PROJECT.analytics_lab.mv_paid_daily`
WHERE order_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-07'
ORDER BY order_date, store_id;

-- Each day/store in the lab should match the baseline exactly.
WITH raw AS (
  SELECT order_date, store_id,
         COUNT(*) AS paid_orders, SUM(amount) AS revenue
  FROM `MY_PROJECT.analytics_lab.orders`
  WHERE status = 'PAID'
  GROUP BY order_date, store_id
),
agg AS (
  SELECT order_date, store_id, paid_orders, revenue
  FROM `MY_PROJECT.analytics_lab.mv_paid_daily`
)
SELECT COALESCE(raw.order_date, agg.order_date) AS day,
       COALESCE(raw.store_id, agg.store_id) AS store_id,
       raw.paid_orders AS base_count, agg.paid_orders AS mv_count,
       raw.revenue AS base_revenue, agg.revenue AS mv_revenue
FROM raw FULL OUTER JOIN agg
  ON raw.order_date = agg.order_date
 AND raw.store_id = agg.store_id
WHERE raw.paid_orders IS DISTINCT FROM agg.paid_orders
   OR raw.revenue IS DISTINCT FROM agg.revenue;
~~~

Expected reconciliation result: **0 rows** when no writes occur mid-comparison and the MV is read with default freshness semantics. On a continuously mutating source, two independent `SELECT`s can observe **different point-in-time snapshots**; pin the data, snapshot timestamp, or time travel if needed rather than concluding the system is wrong from a race condition.

## 4. Smart Tuning and Query Rewrite Limits

**Smart tuning** is BigQuery's ability to **automatically rewrite** a query written against a base table to read an MV instead, even when the SQL **never mentions the MV**. Rewriting is an optimizer choice—not a guarantee every related query will be accelerated.

Reference conditions:

- The MV must reside in the same project as one of the query's base tables or in the project executing the query.
- Query and MV share the **same base tables**, and the MV supplies **all columns and rows** required by the query.
- Aggregations, joins, filters, and security policies must be eligible; the optimizer also weighs **cost** and freshness.
- Smart tuning does not apply to **non-incremental MVs**, MVs with `UNION ALL`/`LEFT OUTER JOIN`, MVs referencing logical views, or CDC-enabled tables per documented rules.

### Example Rewrite Eligible for MV Acceleration

~~~sql
-- Query against base table without referencing mv_paid_daily.
SELECT order_date, store_id,
       COUNT(*) AS paid_orders, SUM(amount) AS revenue
FROM `MY_PROJECT.analytics_lab.orders`
WHERE status = 'PAID'
  AND order_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-07'
GROUP BY order_date, store_id;
~~~

The lab MV already stores `order_date`, `store_id`, `COUNT(*)`, and `SUM(amount)` for rows with `status='PAID'`. This makes it a **candidate** for smart tuning; on 10,000 rows, the optimizer **may still read the base table** if that is cheaper.

Conversely, the queries below **cannot be satisfied by the MV**:

~~~sql
-- (A) Needs ALL orders, whereas the MV only includes status PAID.
SELECT order_date, SUM(amount)
FROM `MY_PROJECT.analytics_lab.orders`
GROUP BY order_date;

-- (B) Filters by order_id, which the MV does not store.
SELECT order_id, amount
FROM `MY_PROJECT.analytics_lab.orders`
WHERE order_id = 'ORD-000042';
~~~

An MV is not a universal index for every predicate. If dashboards also need `status='CANCELLED'` or individual `order_id` lookups, add appropriate summary tables or read models rather than expecting one MV to serve both.

### Confirming Whether the Optimizer Used the MV

In BigQuery Console, open **Execution details → Query plan**. If smart tuning selected the MV, the plan shows `READ ...mv_paid_daily`. Otherwise, inspect job statistics to see whether the MV was considered, chosen, or rejected:

~~~sql
SELECT
  creation_time,
  job_id,
  total_bytes_processed,
  total_slot_ms,
  cache_hit,
  TO_JSON_STRING(materialized_view_statistics) AS mv_stats
FROM `MY_PROJECT.region-asia-southeast1.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND job_type = 'QUERY'
ORDER BY creation_time DESC
LIMIT 30;
~~~

In `materialized_view_statistics`, check fields such as `chosen` and `rejected_reason`. For example, `COST` means the optimizer found a cheaper plan. **Never force every query onto an MV** just because the MV exists; test direct MV queries too and compare latency, bytes, and slot-ms.

## 5. Refresh, Incremental Maintenance, and Data Freshness

### Five Concepts to Distinguish

| Concept | Effect | What It Does **Not** Mean |
|---|---|---|
| **Automatic refresh** | BigQuery updates materialized results in the background | Not a cron job guaranteed to run at exact minute ticks |
| **Incremental maintenance** | Computes updates from base-table deltas | Not every DML update/delete is incremental |
| **Default direct MV query** | BigQuery can combine the MV with unrefreshed base-table changes for fresh results | Does not strictly read only MV storage |
| **`max_staleness`** | Allows direct MV queries to return acceptably stale data for faster execution | Does not guarantee refresh jobs finish within that window |
| **Smart tuning on base queries** | Optimizer uses the MV while preserving exact base-query semantics | An MV's `max_staleness` **never** changes rewrite query results |

On **append-only** base tables with supported aggregations, BigQuery can usually update the MV incrementally from newly appended rows. When updates/deletes invalidate materialized state, BigQuery may fall back to reading the base table, refreshing more data, or skipping the MV; joins also carry specific incremental rules. If a workload modifies old partitions hourly, re-measure MV cost-effectiveness.

### Enabling Controlled Staleness

Suppose a dashboard tolerates data up to **4 hours** stale. You can alter the MV:

~~~sql
ALTER MATERIALIZED VIEW `MY_PROJECT.analytics_lab.mv_paid_daily`
SET OPTIONS (
  enable_refresh = TRUE,
  refresh_interval_minutes = 120,
  max_staleness = INTERVAL '4' HOUR
);
~~~

When **querying the MV directly**, if the latest refresh is within `max_staleness`, BigQuery can read the materialized data without merging fresh deltas from the base table. If the last refresh is older than `max_staleness`, BigQuery falls back to combining base data and the MV—**exceeding 4 hours does not immediately fail the query**. However, streaming buffers and certain MV/source types carry specific limits; if refreshes stay stalled too long, scan costs or query failures can rise.

**Critical point:** `max_staleness` **has zero effect** on base-table queries rewritten via **smart tuning**. If a dashboard's contract allows "reading precomputed aggregates up to 4 hours old," design it to **query the MV directly**, validate outputs, and monitor freshness.

### Observing Refresh After DML

~~~sql
-- Insert one order on a lab date to test.
INSERT INTO `MY_PROJECT.analytics_lab.orders`
  (order_id, order_date, store_id, amount, status)
VALUES ('ORD-EXTRA-1', DATE '2026-11-07',
        'STORE-1', NUMERIC '125.00', 'PAID');

-- Query the MV directly under its current staleness policy:
SELECT order_date, store_id, paid_orders, revenue
FROM `MY_PROJECT.analytics_lab.mv_paid_daily`
WHERE order_date = DATE '2026-11-07' AND store_id = 'STORE-1';
~~~

With `max_staleness` enabled, the dashboard **may not reflect** the new order until the next refresh. Re-running `INSERT` creates duplicate `order_id` rows because BigQuery does not enforce OLTP primary keys; insert **once** or use unique test IDs and a reset procedure. When instant per-transaction accuracy is required, read from the transactional store (Spanner/Cloud SQL) rather than relying solely on BI aggregates.

### Non-Incremental MVs: Trade-Offs

BigQuery supports `allow_non_incremental_definition = true` for certain complex SQL definitions, which **requires setting `max_staleness`**. These MVs perform **full refreshes** rather than incremental ones, **cannot be used by smart tuning**, and only benefit **direct** MV queries. If refreshing requires scanning multiple terabytes hourly, refresh costs can exceed dashboard savings; consider scheduled queries/ETL writing summary tables on an explicit cadence instead.

## 6. BI Engine: In-Memory Interactive Query Acceleration

**BigQuery BI Engine** uses **in-memory vectorized execution** to accelerate eligible `SELECT` queries. Unlike an MV, BI Engine **does not define precomputed aggregations**: it reserves memory per **project/location** and automatically caches hot columns/partitions for eligible queries.

~~~text
Dashboard / Java BI API
       │ SQL SELECT
       ▼
BigQuery query optimizer
       ├── query-result cache (if eligible)
       ├── MV rewrite/direct MV (if applicable)
       └── BI Engine in-memory + vectorized execution
             └── fallback to regular BigQuery slots when unsupported/out of RAM
~~~

| Scenario | Can BI Engine Help? | Notes |
|---|---|---|
| Repeated dashboard `SELECT`s over popular small/medium tables or MVs | **Yes** | Measure FULL/PARTIAL acceleration ratio |
| Queries touching few columns, filtered by date/store | **Yes** | Caches hot partitions/columns |
| Wildcard tables `orders_*` | **No** | Unsupported by BI Engine |
| External tables, non-SQL UDFs, certain SQL features | **Limited/No** | Check `biEngineReasons` in job stats |
| Tables with row-level security | **No** under current BI Engine support | Design auth carefully and measure fallback |
| Heavy multi-table JOINs scanning uncached tables | **Uncertain** | Combine with pre-aggregation/MVs or tune JOINs |
| Multiple accounts querying across regions | Must reserve capacity **in each location** | A Singapore reservation does not accelerate US jobs |

BI Engine is **not a Redis cache** that Java reads/writes explicitly; applications do not call a separate cache API. The Java backend still submits standard GoogleSQL via the BigQuery client, and BI Engine accelerates eligible execution automatically.

### Preferred Tables

You can specify **preferred tables** to dedicate BI Engine capacity to priority tables. When preferred tables are configured:

- Queries referencing tables outside the list do not use that BI Engine reservation.
- Multi-table JOINs typically accelerate only when **all participating tables** are in the preferred list.
- **Direct MV queries** require listing **both the MV and its base tables** in preferred tables to qualify for BI Engine acceleration.
- Logical views cannot be preferred tables; `JSON` columns do not receive equivalent acceleration.
- BI Engine caches only needed columns/partitions—so **a 1 GiB reservation does not require the entire base table to be under 1 GiB**, though insufficient capacity causes fallback.

### Creating a BI Engine Reservation in the Lab (Optional, Billable)

Run only with budget approval and minimum capacity estimation. This SQL example **creates or updates** the `default` reservation in your project/region (modifying an existing one if present):

~~~sql
ALTER BI_CAPACITY `MY_PROJECT.region-asia-southeast1.default`
SET OPTIONS (
  size_gb = 1,
  preferred_tables = [
    `MY_PROJECT.analytics_lab.orders`,
    `MY_PROJECT.analytics_lab.mv_paid_daily`
  ]
);
~~~

**Never run this on a shared project** without checking existing reservations and owners. `size_gb=1` is an illustrative allocation, not a production sizing recommendation. In the Console under **BigQuery → BI Engine**, select project/location, capacity, and preferred tables; managing BI reservations requires appropriate IAM permissions.

Check status and change history:

~~~sql
SELECT *
FROM `MY_PROJECT.region-asia-southeast1.INFORMATION_SCHEMA.BI_CAPACITIES`;

SELECT *
FROM `MY_PROJECT.region-asia-southeast1.INFORMATION_SCHEMA.BI_CAPACITY_CHANGES`
ORDER BY change_timestamp DESC
LIMIT 10;
~~~

BI Engine acceleration is decided per query—reported as **FULL**, **PARTIAL**, **FULL_INPUT**, or **DISABLED** in job statistics. Never treat "reservation exists" as proof dashboards are accelerated.

## 7. Monitoring MVs, BI Engine, and Query Plans

### Verify MV Refreshes Succeed

~~~sql
SELECT
  table_name,
  last_refresh_time,
  refresh_watermark,
  last_refresh_status
FROM `MY_PROJECT.analytics_lab.INFORMATION_SCHEMA.MATERIALIZED_VIEWS`
WHERE table_name = 'mv_paid_daily';
~~~

`last_refresh_time` records when the last refresh ran; `refresh_watermark` shows up to what source timestamp data is reflected in the materialized view. These two values can differ; if the base table had no changes, the watermark can advance without a physical refresh. A non-NULL `last_refresh_status` usually indicates an automatic refresh error—inspect its details and corresponding refresh job.

To locate automatic refresh jobs:

~~~sql
SELECT job_id, creation_time, state, error_result,
       total_bytes_processed, total_slot_ms
FROM `MY_PROJECT.region-asia-southeast1.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  AND job_id LIKE '%materialized_view_refresh_%'
ORDER BY creation_time DESC
LIMIT 50;
~~~

High refresh bytes when little data changed can point to base-table updates/deletes, partition expiration, full refreshes, or non-incremental SQL. Never judge optimization solely from one fast run caused by the query-result cache.

### Verify BI Engine Actually Accelerated Queries

~~~sql
SELECT
  creation_time,
  job_id,
  cache_hit,
  total_bytes_processed,
  total_slot_ms,
  TO_JSON_STRING(bi_engine_statistics) AS bi_stats,
  TO_JSON_STRING(materialized_view_statistics) AS mv_stats
FROM `MY_PROJECT.region-asia-southeast1.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND job_type = 'QUERY'
ORDER BY creation_time DESC
LIMIT 50;
~~~

In API/`INFORMATION_SCHEMA` output:

- `biEngineMode` typically reports `FULL`, `PARTIAL`, or `DISABLED`. `accelerationMode` gives finer detail: `FULL_QUERY`, `FULL_INPUT`, `PARTIAL_INPUT`, or `BI_ENGINE_DISABLED`.
- When not accelerated, inspect `biEngineReasons`: `NO_RESERVATION`, `INSUFFICIENT_RESERVATION`, `TABLE_EXCLUDED`, `INPUT_TOO_LARGE`, `UNSUPPORTED_SQL_TEXT`, etc.
- `cache_hit = TRUE` means the query-result cache served the response, which can make measurements look artificially fast; to test BI Engine impact, re-run with **Use cached results = OFF**.
- `total_slot_ms`, `total_bytes_processed`, and elapsed time measure different dimensions; a BI Engine-accelerated query can report different slot usage than standard BigQuery execution and should not be priced from slot-ms alone.

Querying `JOBS_BY_PROJECT` requires project-wide job metadata permissions and can expose SQL containing sensitive parameters. Application teams inspecting only their own jobs should prefer `JOBS_BY_USER` or scoped job logs, leaving project-wide views to SREs/data admins.

### Monitoring BI Engine Capacity Usage

Track BigQuery BI Engine metrics in Cloud Monitoring—specifically **reserved/used bytes**, memory pressure, query acceleration, and project/location. When `used_bytes` approaches the reservation cap and queries fall back, you can expand capacity **or** narrow column projections, preferred tables, and pre-aggregations. Never add RAM for a query using unsupported SQL; fix the query first.

## 8. Calling BigQuery Properly from Java on Cloud Run

A Java dashboard API can query an MV directly via the **BigQuery Java client**. In production, consider a short-TTL backend cache, rate limiting, and avoiding long-lived synchronous HTTP requests waiting on heavy queries. The example below uses `com.google.cloud:google-cloud-bigquery`, Java 17+, a lab project, and runtime **Application Default Credentials (ADC)**.

~~~java
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.BigQueryOptions;
import com.google.cloud.bigquery.FieldValueList;
import com.google.cloud.bigquery.QueryJobConfiguration;
import com.google.cloud.bigquery.QueryParameterValue;
import com.google.cloud.bigquery.TableResult;

public final class RevenueDashboard {
    public static void main(String[] args) throws InterruptedException {
        // Example: projectId must come from validated config;
        // never concatenate raw SQL strings from untrusted input.
        String projectId = "my-bigquery-lab";
        BigQuery bigquery = BigQueryOptions.newBuilder()
            .setProjectId(projectId)
            .build()
            .getService();

        // Query the materialized view DIRECTLY; no automatic rewrite needed.
        String sql = """
            SELECT order_date, store_id, paid_orders, revenue
            FROM `MY_PROJECT.analytics_lab.mv_paid_daily`
            WHERE order_date BETWEEN @from_date AND @to_date
            ORDER BY order_date, store_id
            """.replace("MY_PROJECT", projectId);

        QueryJobConfiguration config = QueryJobConfiguration.newBuilder(sql)
            .addNamedParameter("from_date",
                QueryParameterValue.date("2026-11-01"))
            .addNamedParameter("to_date",
                QueryParameterValue.date("2026-11-07"))
            .setUseLegacySql(false)
            .setUseQueryCache(false) // benchmark only; adjust for production
            .setMaximumBytesBilled(1_000_000_000L) // on-demand safety cap
            .build();

        TableResult result = bigquery.query(config);
        for (FieldValueList row : result.iterateAll()) {
            System.out.printf("%s | %s | %d | %s%n",
                row.get("order_date").getStringValue(),
                row.get("store_id").getStringValue(),
                row.get("paid_orders").getLongValue(),
                row.get("revenue").getNumericValue());
        }
    }
}
~~~

**Design notes:**

- The SQL uses a **server-configured table name**; the two dates are bound with `QueryParameterValue` rather than concatenating request parameters, preventing SQL injection.
- The BigQuery client uses ADC (Cloud Run `--service-account`, GKE Workload Identity Federation); never bake JSON keys into containers.
- With real data, **never trust a client-supplied project ID or tenant ID** to route across datasets. Java must enforce authorization and permit querying only authorized datasets.
- `setMaximumBytesBilled` blocks on-demand queries exceeding the byte cap; **it does not replace budgets/quotas or cap BI Engine reservation fees**.
- Java services should enforce request timeouts, job polling, pagination, cancellation, rate limits, and Cloud Run concurrency. For long-running queries, submit async jobs and return an authorized job ID to poll results.
- In multi-region BigQuery setups, pass the **exact location** when creating jobs (via `JobId`/`JobInfo` per SDK version) matching the dataset/reservation location; do not rely on implicit environment defaults.
- BI Engine also requires a **supported edition/region**; verify entitlements, quotas, and capacity policies before enabling reservations—not just the dataset name.

### IAM for Java and Data Engineering Workflows

| Identity | Typical Permissions Needed | Principle |
|---|---|---|
| Cloud Run runtime SA | `roles/bigquery.jobUser` on query/billing project; `roles/bigquery.dataViewer` on target dataset/table/MV | Never grant `BigQuery Admin` just to read revenue |
| Data engineer / CI DDL | Table/MV creation and alter permissions (e.g., `bigquery.tables.create` and scoped updates) | Separate from runtime app SA |
| BI Engine capacity admin | Permissions to manage BI reservations/capacity | Do not grant to Java dashboard SA |
| SRE/FinOps | Job metadata, MV refresh, BI capacity, monitoring, and billing | Restrict access to SQL containing PII |

**MV permissions depend on underlying tables:** reading a standard materialized view checks permissions on both the MV and its base tables; to share aggregates **without granting base-table access**, configure an **authorized materialized view** per documentation. Never assume granting `Data Viewer` on the MV alone suffices in all cases.

### Row-Level and Column-Level Security

If a base table enforces **row-level access policies**, MV queries must still obey row policies; BigQuery may **not deliver typical MV performance gains**, and BI Engine has support limits. With **column-level access controls/data masking**, check permissions and query shapes before expecting acceleration. Never remove RLS or widen IAM just to force BI Engine acceleration.

## 9. Benchmarking and Optimizing Queries by Measurement

### Minimal Test Suite

| Test | Query | Metrics to Record |
|---|---|---|
| A | Baseline aggregate on `orders` | P50/P95 latency, bytes scanned/billed, slot-ms |
| B | Direct query on `mv_paid_daily` | Same metrics, refresh status/watermark |
| C | Re-run base SQL with MV in project | `materialized_view_statistics.chosen`, latency, cost |
| D | After enabling 1 GiB BI Engine, query MV/base | `biEngineMode`/`accelerationMode`, fallback reason |
| E | Ineligible query (wildcard table / unsupported JOIN) | `DISABLED` reason and fallback cost |

Measurement process:

1. **Pin workload and dataset/location**; record exact SQL text, row counts, partition filters, concurrency, and pricing mode.
2. **Disable cached query results** when comparing MV/BI Engine impact, since old cache hits return fast and cannot be credited to BI Engine.
3. Run multiple iterations during comparable load windows; compare **P50/P95** rather than a single fastest run. Measure cold vs. warm queries separately as BI Engine populates memory.
4. Verify correctness and freshness; when `max_staleness` is enabled, display "Updated as of..." or a clear freshness contract on the dashboard.
5. Sum total costs: **refresh + MV storage + BI reservation + query/billed bytes + downstream**. Never compare latency alone.
6. Keep or remove MV/BI Engine based on SLO attainment and net cost impact on real workloads.

### Low-Cost Optimizations to Try First

| Query Plan Signal | Action to Try |
|---|---|
| Heavy `READ` bytes from multi-year table | Filter partition column `order_date` directly; project only needed columns |
| High `shuffle bytes` after JOIN | Aggregate/filter early; avoid joining massive fact tables before grouping |
| Full scan for a handful of values | Evaluate clustering, search indexes, or a lookup-friendly layout |
| Long slot waits, rising P95 under concurrency | Evaluate reservations/editions/capacity rather than adding MVs alone |
| Many dashboards repeating identical aggregates | Materialized view or scheduled aggregate table |
| Near-real-time dashboard with many small metrics | BI Engine if SQL/workload is eligible; verify fallback and freshness |
| Java returning too many rows | Paginate, cap outputs, aggregate inside BigQuery |
| MV refresh costs outweigh benefits | Lower refresh frequency, batch updates, or switch to a scheduled query |

**When to use a scheduled query instead of an MV?** When aggregations are highly complex, require custom ETL logic, only need daily snapshots, or must write to a standalone table, scheduled queries have simpler semantics. However, each scheduled run recomputes larger datasets, whereas incremental MVs shine on recurring aggregates over append-heavy tables.

## 10. Costs, SLOs, and Deployment Decisions

The cost of "acceleration" must be measured across the **entire system**, not a single query:

~~~text
Total relevant cost
  = BigQuery storage for base tables and materialized results
  + query compute (on-demand bytes billed or editions/slots)
  + MV automatic/manual refresh compute
  + BI Engine capacity reservation over time/size
  + streaming/ingestion, Cloud Storage, network, Cloud Logging
  + Java API / Cloud Run / GKE and downstream services
~~~

**Exact prices, free tiers, and quotas vary by region, pricing model, and time.** Check actual Billing SKUs rather than estimating from SQL line counts. An MV can slash bytes scanned for thousands of repeated queries, yet frequent refreshes over tables with heavy DML updates can cost more than the savings.

### Rough Evaluation Formula

~~~text
Estimated monthly net savings
  = pre-optimization query compute cost
    - post-optimization query compute cost
    - MV refresh cost + MV storage cost
    - BI Engine reservation cost
    - additional operational overhead
~~~

Report two metric pairs together:

- **SLO:** e.g., dashboard P95 load under 2 seconds, data staleness at most 4 hours when `max_staleness` is displayed.
- **FinOps:** cost per 1,000 dashboard loads, total BigQuery/BI Engine spend per project, failed refresh count, and bytes scanned.

Never expand a BI Engine reservation when 500 ms of dashboard lag comes from front-end rendering or Java JSON serialization; layer-by-layer profiling reveals the true bottleneck.

### Architecture Decision Patterns

| Workload Pattern | Try First | Why |
|---|---|---|
| Queries reading a 7-day slice of a multi-year table | Partition filters + clustering | Cuts scan bytes without adding services |
| Many dashboards sharing daily/store `SUM/COUNT` | Incremental materialized view | Reuses aggregates; enables smart tuning |
| High-frequency interactive BI with supported SQL | BI Engine on preferred tables/MV | Cuts latency via memory and vectorization |
| Complex financial batch closed once per day | Scheduled aggregate table | Easier schedule and snapshot control |
| API returning payment status **right after commit** | Cloud SQL/Spanner for OLTP path | Never promise a BigQuery MV as real-time source of truth |
| Multi-tenant/partner data with strict row-level policies | Prioritize security correctness; re-benchmark MV/BI | RLS/masking can limit acceleration |

## 11. Runbook: MV/BI Engine Not Faster or Showing "Stale" Results

| Symptom | Common Cause | Check / Action |
|---|---|---|
| `CREATE MATERIALIZED VIEW` rejected | SQL/aggregate ineligible for incremental MV or missing permissions | Docs on supported patterns, `bigquery.tables.create` |
| MV refresh fails | Schema change, dropped base table, DML/partition invalidation | `INFORMATION_SCHEMA.MATERIALIZED_VIEWS.last_refresh_status`, refresh jobs |
| Base query does not use MV | Missing columns/rows in MV, mismatched SQL shape, or optimizer found cheaper plan | `materialized_view_statistics.chosen/rejected_reason`, query plan |
| Direct MV query still scans many bytes | Unrefreshed delta merge, freshness policy, or invalidated full refresh | Refresh watermark, base DML, `max_staleness` |
| Dashboard misses recent orders | `max_staleness` permits reading prior refresh snapshot | Check last refresh, display data-as-of, or query base table directly |
| BI Engine enabled yet `NO_RESERVATION` | Capacity missing or in wrong region/project | `BI_CAPACITIES`, query project/location |
| `INSUFFICIENT_RESERVATION` or `INPUT_TOO_LARGE` | Memory too small for referenced columns/partitions/JOINs | Used/reserved bytes, narrow columns/partitions, or resize |
| `TABLE_EXCLUDED` | Preferred table list omits base table/MV or a joined table | Verify `preferred_tables` against all query sources |
| `UNSUPPORTED_SQL_TEXT` | Wildcard table, external table, UDF, or unsupported SQL construct | Rewrite query, simplify, or accept slot fallback |
| Query is fast only on the second run | Query-result cache or BI Engine warmup | Disable result cache during benchmarks; measure cold/warm separately |
| `PERMISSION_DENIED` in Java reading MV | Runtime SA lacks `jobUser`/`dataViewer`, base-table access, or RLS/column policy | Identity, dataset/view IAM, authorized MV setup |
| `Location mismatch` | Dataset, query job, and BI reservation are in different locations | Align job location and verify dataset region |
| BigQuery bill rises after optimization | MV refresh/storage, BI reservation, or extra scans/JOINs | Billing by SKU, refresh job bytes, reservation size |

Read-only investigation commands:

~~~bash
PROJECT_ID="my-bigquery-lab"
LOCATION="asia-southeast1"

bq --location="$LOCATION" ls "$PROJECT_ID:analytics_lab"
bq --location="$LOCATION" show \
  "$PROJECT_ID:analytics_lab.mv_paid_daily"

# Replace JOB_ID with an actual ID from Console or INFORMATION_SCHEMA.
bq --location="$LOCATION" show --format=prettyjson \
  -j "JOB_ID"
~~~

When a query misses targets, capture **SQL text, Job ID, location, `cache_hit`, query plan, bytes, slot-ms, MV/BI statistics, and refresh timestamps** before tuning configs. A Java HTTP 500 might come from a timeout or backend exception unrelated to BI Engine—isolate which layer failed.

## 12. Extended Scenario: Multi-Area Retail Dashboard

An enterprise runs transactional databases on Cloud SQL/Spanner, Java services on Cloud Run, and a revenue dashboard:

~~~mermaid
flowchart TD
  A["Cloud SQL / Spanner: committed orders"] --> I["ELT / CDC / BigQuery ingestion"]
  I --> B["BigQuery orders: partition + cluster"]
  B --> MV["MV: paid revenue by day/store"]
  MV --> BI["BI Engine reservation: preferred tables"]
  BI --> J["Cloud Run Java Dashboard API"]
  J --> U["Charts / BI client"]
  M["Job metadata + Cloud Monitoring + Billing"] --> MV
  M --> BI
~~~

**Dual-path read design:**

- **Revenue reporting** tolerates SLO-defined lag, uses BigQuery MVs/BI Engine, and separates permissions to read aggregates.
- **Instant post-payment order status lookups** hit the transactional OLTP database. Never treat BigQuery/MV ingestion completion as confirmation that a payment succeeded.

In multi-region setups, keep datasets and BI Engine reservations in the **same location**. If sources span regions, build data sync pipelines and assess data residency and egress—never assume a reservation in region A accelerates jobs in region B. Multi-tenant dashboards must verify row-level and column-level policies; performance tuning must never relax data access controls.

### Rollout Workflow with Rollback

1. Data team reviews schemas, partition/cluster keys, and query patterns from job history.
2. Create a versioned MV in staging; reconcile numbers against the base query.
3. Benchmark latency/bytes/slot-ms and MV usage; enable `max_staleness` **only after business sign-off on freshness**.
4. Enable BI Engine in a lab project/location or dedicated reservation with an owner; inspect acceleration reasons.
5. Switch the Java API to read the MV behind a feature flag; canary a fraction of traffic and verify P95 and correctness.
6. If issues arise, **switch Java queries back to the base or aggregate table first**, then tear down unused capacity/MVs—never drop an MV while clients still query it.
7. Monitor refresh errors, BI memory pressure, billing, and data lag over time.

## 13. Pre-Production Checklist

- [ ] Baselines captured for queries, P50/P95 latency, scan bytes, slot-ms, query plans, and costs.
- [ ] Partition filters target the partition column directly; unnecessary `SELECT *` eliminated.
- [ ] MV definition selects only columns/rows needed by key queries and uses a supported SQL pattern.
- [ ] On partitioned base tables, MV uses matching partition alignment with expiration/invalidation reviewed.
- [ ] `last_refresh_time`, `refresh_watermark`, and `last_refresh_status` are monitored.
- [ ] Incremental refresh, smart tuning, and direct MV queries are distinguished; `chosen/rejected_reason` verified.
- [ ] `max_staleness` aligns with data SLOs, is surfaced in the UI, and is not mistaken for a hard refresh guarantee.
- [ ] BI Engine reservation sits in the right project/location with an approved budget and accurate `preferred_tables`.
- [ ] `bi_engine_statistics` tracked for FULL/PARTIAL/DISABLED modes and fallback reasons.
- [ ] Benchmarks disable query-result cache and evaluate both cold and warm workloads.
- [ ] Java runtime SA uses ADC with minimal `jobUser`/`dataViewer`; view/base IAM and RLS reviewed.
- [ ] Row/column security is never weakened for BI acceleration; debug logs contain no PII.
- [ ] Billing telemetry covers refresh compute, MV storage, BI reserved GiB, and rollback procedures.
- [ ] Java API enforces rate limits, query timeouts, and bounded HTTP request durations.

## 14. Applied Exercises

**Exercise 1 — Comparing Mechanisms.** Compare logical views, materialized views, query-result cache, and BI Engine across storage location, when to use each, freshness handling, and cost drivers.

**Exercise 2 — Partition Pruning.** An `orders` table holds 3 years of orders; a dashboard queries 7 days. Write a query filtering `order_date BETWEEN ...` and explain why `SELECT *`/full-table scans cost more. Suggest a clustering column when queries routinely filter by `store_id`.

**Exercise 3 — MV Lab.** Create `mv_paid_daily` with `COUNT(*)` and `SUM(amount)` by day and store, and reconcile it against the base table. Query the base table and show how to verify optimizer MV usage via `materialized_view_statistics`.

**Exercise 4 — Smart Tuning.** Why can't an MV containing only `status='PAID'` grouped by `order_date, store_id` answer a query looking up a specific `order_id` or summing across all statuses? Propose another table or read model.

**Exercise 5 — Freshness.** A BI dashboard tolerates up to 4 hours of lag, whereas live order status must be instant. Choose the read path for each feature; explain `max_staleness` and why smart tuning on base-table queries never returns "stale" MV results.

**Exercise 6 — BI Engine.** Create a 1 GiB reservation in the lab project/location with `preferred_tables` set to `orders` and `mv_paid_daily`. If a query joins a third table outside the preferred list, predict acceleration behavior and where to inspect the reason.

**Exercise 7 — Benchmarking.** Design an A/B/C/D test comparing the base query, direct MV query, base query with smart tuning, and BI Engine; which variables (cache, rows, location, concurrency) and metrics must you control and record?

**Exercise 8 — IAM/RLS.** A Cloud Run runtime SA has only `roles/bigquery.jobUser` on the project and gets `PERMISSION_DENIED` reading an MV. List the permissions/data access checks needed, the role of an authorized materialized view, and why row-level policies must not be deleted for speed.

**Exercise 9 — Cost Modeling.** A dashboard runs many repeated queries, while an MV refreshes frequently over a table receiving heavy hourly `UPDATE`s. List all cost components and propose how to compare incremental MVs, scheduled aggregate tables, partitioning, and BI Engine.

**Exercise 10 — Production Incident.** After deployment, BI Engine reports `TABLE_EXCLUDED`, MV `last_refresh_status` shows errors, and P95 climbs. Build a troubleshooting runbook ordered from IAM/location/SQL, refresh jobs, query plans, and preferred tables through rollback.

## Official References

- [BigQuery query performance overview](https://cloud.google.com/bigquery/docs/best-practices-performance-overview) — measuring I/O, shuffle, computation, and slots.
- [Optimize query computation](https://cloud.google.com/bigquery/docs/best-practices-performance-compute) — partition pruning, clustering, MVs, and BI Engine.
- [Introduction to materialized views](https://cloud.google.com/bigquery/docs/materialized-views-intro) — incremental refreshes and precomputation.
- [Create materialized views](https://cloud.google.com/bigquery/docs/materialized-views-create) — SQL, partition alignment, refreshes, and `max_staleness`.
- [Use materialized views](https://cloud.google.com/bigquery/docs/materialized-views-use) — smart tuning, `chosen`, and `rejected_reason`.
- [Monitor materialized views](https://cloud.google.com/bigquery/docs/materialized-views-monitor) — refresh jobs and `INFORMATION_SCHEMA.MATERIALIZED_VIEWS`.
- [Troubleshoot materialized views](https://cloud.google.com/bigquery/docs/materialized-views-troubleshoot) — invalidation and rewrite errors.
- [BI Engine introduction](https://cloud.google.com/bigquery/docs/bi-engine-intro) — in-memory/vectorized execution and SQL support.
- [Reserve BI Engine capacity](https://cloud.google.com/bigquery/docs/bi-engine-reserve-capacity) — reservations, preferred tables, and `BI_CAPACITIES`.
- [Monitor BI Engine](https://cloud.google.com/bigquery/docs/bi-engine-monitor) — `bi_engine_statistics`, job metadata, and Cloud Monitoring.
- [JOBS_BY_PROJECT information schema](https://cloud.google.com/bigquery/docs/information-schema-jobs) — job costs, caching, and query insights.
- [BigQuery Java client library](https://cloud.google.com/java/docs/reference/google-cloud-bigquery/latest/overview) — query jobs, parameters, and ADC.
- [BigQuery IAM](https://cloud.google.com/bigquery/docs/access-control) — jobUser, dataset/view access, and least privilege.
- [Using row-level security with other features](https://cloud.google.com/bigquery/docs/using-row-level-security-with-features) — impact on MVs and BI Engine.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) — compute, storage, and BI Engine capacity.
