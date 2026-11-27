# Archiving Old Data, Reporting Summaries, and Separating Analytical Workloads

As a MySQL system grows, transactional tables expand continuously while most business queries need only recent data. Monthly, quarterly, or multi-year reports must scan and aggregate vast numbers of records. Running heavy analytical queries directly on the primary serving OLTP workloads competes with application requests for CPU, I/O, buffer pool pages, connections, and metadata locks.

A sound scaling strategy combines three practices: defining data lifecycles and archiving old data per policy; building summary tables so reports avoid recomputing every detail; and offloading analytical workloads to read replicas or a dedicated analytics store. This lesson belongs to the **DATABASE_MYSQL** module, focusing on MySQL scaling and integration—from retention, archiving, and partitioning to ETL/CDC and reporting load control.

## 1. Distinguishing OLTP and OLAP

The two workload classes have distinct characteristics:

| Characteristic | OLTP — Transactional | OLAP — Analytical |
|---|---|---|
| Goal | Serve online business operations | Aggregate, compare, and analyze trends |
| Queries | Short, selective predicates, typically indexed | Multi-row scans, multi-table JOINs, GROUP BY |
| Writes | Many small INSERT/UPDATE/DELETE operations | Typically batch or streaming ingestion |
| Transactions | Short, requiring low latency and consistency | May read large snapshots, long-running processing |
| Optimization | Transaction throughput and p95/p99 latency | Scan throughput, report completion time |
| Resources | Must stay stable for user requests | Can consume heavy CPU, I/O, and memory |

OLTP examples: creating an order, deducting inventory, updating payment status. OLAP examples: total revenue by region over 24 months, customer retention rates, or order volume breakdowns by product and sales channel.

An SQL query that runs fast on small datasets can become an OLAP load when scanning tens of millions of rows. Do not classify a query by syntax alone; evaluate row counts, time ranges, cardinality, indexes, concurrency, and impact on active workloads.

## 2. Workload-Separation Architecture

A common architecture has three zones:

~~~text
                   Business application
                           |
                           v
                    MySQL Primary
                     OLTP workload
                           |
                 Asynchronous replication
                           |
             +-------------+-------------+
             |                           |
             v                           v
      Read Replica                CDC / ETL pipeline
  selective read queries                   |
  operational reports                      v
                                    Analytics Store
                                  fact / dimension /
                                  aggregate tables
                                           |
                                           v
                                  Dashboard / BI / ML
~~~

Component roles:

- **Primary:** handles write transactions and business queries requiring the latest data.
- **Read replica:** serves read queries that tolerate replication lag; offloads a portion of read traffic from the primary.
- **CDC/ETL:** streams changes or moves batch data to analytical systems.
- **Analytics store:** stores historical data, fact/dimension models, and aggregate tables designed for analytical queries.

A read replica is still a MySQL server that must apply relay logs and execute changes from the primary. An overly heavy report can increase replica lag, making reads stale and affecting other consumers. Thus, replicas are a useful offloading step, yet do not replace a dedicated analytics store when OLAP workloads are large or unpredictable.

### Choosing Where to Run Reports

| Report type | Suitable starting location |
|---|---|
| Looking up details of a recent order | Primary or replica depending on freshness requirements |
| Operational dashboard with lightweight queries | Read replica |
| Multi-month revenue aggregation over tens of millions of rows | Analytics store or summary table |
| Ad hoc analysis joining multiple fact tables | Analytical data warehouse |
| Reports requiring read-after-write immediately after a transaction | Primary or mechanism waiting for replica catch-up |

Do not mechanically route every `SELECT` to a replica. Read-after-write flows, inventory checks, payment confirmations, or permission checks may require the latest data and must read from the primary or use an appropriate consistency mechanism.

## 3. Building a Data Lifecycle Policy

Before archiving, determine which data still serves active transactions, which data needs historical lookup, and which data can be deleted.

A retention policy should specify:

- **Scope:** applicable tables, record types, and tenants/business units.
- **Time reference:** based on `created_at`, `closed_at`, `paid_at`, or business completion date.
- **Archival eligibility:** archive only completed records with no open transactions or active workflows.
- **Retention periods:** how long data stays in hot tables, in archives, and in backups.
- **Legal holds:** cases requiring retention despite reaching standard expiration.
- **Retrievability:** who may read old data, expected recovery/lookup latency, and access controls.
- **Final deletion:** how records are purged from databases, archives, replicas, and backups per policy.

Never apply a single retention period across every table. For instance, session tables may only need a few days, operational logs may stay for weeks or months, whereas completed orders may require multi-year lookup depending on business requirements.

### Data Classification

| Tier | Characteristics | Handling |
|---|---|---|
| Hot data | Read/written frequently | Keep in properly indexed OLTP tables |
| Warm data | Rarely updated yet still queried | Can move to historical schemas/tables or replicas |
| Cold data | Rarely accessed, mainly for audits/history | Archive to cheaper storage or a data warehouse |
| Expired data | No valid retention purpose remains | Delete or anonymize per approved retention policy |

Archiving does not mean deleting. If older records must remain retrievable, define whether the application queries them via an archive table, a history service, or a data warehouse.

## 4. Designing Archive Tables

There are multiple ways to organize archives. The choice depends on data size, lookup frequency, constraints, and operational capability.

### Archive Table in the Same Schema/Instance

Example active orders table:

~~~sql
CREATE TABLE app.orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(15,2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_created_at (created_at),
    KEY idx_orders_customer_created (customer_id, created_at)
) ENGINE=InnoDB;
~~~

You can create a compatible archive table:

~~~sql
CREATE TABLE archive.orders_archive LIKE app.orders;
~~~

`CREATE TABLE ... LIKE` copies column definitions and indexes without copying data. Verify properties that are not copied completely as needed, especially foreign keys, triggers, partitions, privileges, and dependent objects.

Advantages:

- Easy to move data between two tables within the same MySQL instance.
- Preserves data types and keys matching the source table.
- Application can query history using dedicated queries.

Limitations:

- Data still consumes storage and backups on the same instance.
- Archive tables still incur index and maintenance overhead.
- `UNION` queries spanning hot and archive tables can become complex.
- Foreign keys, triggers, privileges, and purge policies must be managed separately.

If the goal is reducing storage on the primary, moving data to another schema on the same instance is usually insufficient. Archive to a separate instance or object storage/data warehouse.

### Archiving to a Separate Database or Instance

You can create a history database on the same instance or a separate server. Separating instances better isolates I/O, backups, and access privileges. However, moving across servers means data migration no longer fits in a single MySQL transaction; you need dedicated synchronization, verification, and checkpointing workflows.

### Archiving to Object Storage or a Data Lake

For very old data, export in CSV, Parquet, or a format supported by your analytics platform and store in object storage. The workflow needs:

- A manifest describing schema, time partition, row count, and checksums.
- Encryption at rest and in transit.
- Access controls and retention enforcement.
- Schema versioning to decode older data.
- File validation and restoration procedures.

MySQL does not turn object storage into a table you can `JOIN` directly. Applications or analytics platforms need a reader/ETL layer to access archived data.

## 5. Moving Old Data Safely in Batches

Never delete millions of records in a single transaction. An oversized transaction holds row locks for a long time, generates massive undo/redo logs, spikes replica lag, creates purge pressure, and makes rollbacks very expensive.

Moving in small batches bounds impact and enables resuming from checkpoints. Each batch should clearly define:

- Age and status eligibility conditions for archiving.
- Primary key range of the batch.
- Rows copied and rows deleted.
- Last completed checkpoint.
- Recovery behavior if a batch fails or reruns.

### Archival Eligibility Conditions

For example, archive only paid or cancelled orders that are closed and older than the cutoff:

~~~sql
SELECT order_id, status, created_at
FROM app.orders
WHERE created_at < '2025-01-01 00:00:00'
  AND status IN ('PAID', 'CANCELLED')
ORDER BY order_id
LIMIT 100;
~~~

Cutoffs should use UTC or a consistent timezone. Never evaluate "current time" per batch in a way that shifts the boundary mid-run; fix the cutoff for the entire run so the job resumes consistently.

### Moving Within the Same MySQL Instance

When both source and archive tables use InnoDB on the same instance, you can copy and delete in one transaction per primary key range. Example:

~~~sql
START TRANSACTION;

INSERT INTO archive.orders_archive (
    order_id, customer_id, status, total_amount, created_at
)
SELECT
    order_id, customer_id, status, total_amount, created_at
FROM app.orders
WHERE created_at < '2025-01-01 00:00:00'
  AND status IN ('PAID', 'CANCELLED')
  AND order_id > 100000
  AND order_id <= 101000;

DELETE FROM app.orders
WHERE created_at < '2025-01-01 00:00:00'
  AND status IN ('PAID', 'CANCELLED')
  AND order_id > 100000
  AND order_id <= 101000;

COMMIT;
~~~

This is an ID-range example; adjust range size according to data density and transaction duration. If either `INSERT` or `DELETE` fails, roll back the whole transaction to avoid copy-without-delete or delete-without-archive states. The archive table should have an appropriate unique key to detect duplicate records.

Predicates in `INSERT` and `DELETE` must match identically. If rows might be updated concurrently, lock or re-verify row state inside the transaction; better yet, archive only data that is closed and business-immutable. Never delete rows solely from a stale ID list if status or retention eligibility may have changed.

After each batch, record the checkpoint and row counts. You can call `ROW_COUNT()` right after `INSERT` and `DELETE` to capture affected rows; the orchestrating job should compare both counts and mark the batch complete only after commit succeeds.

### Moving to a Separate Archive Server

A standard InnoDB transaction cannot atomically commit across two independent MySQL servers. Use a checkpointed workflow:

1. Fix the ID range and cutoff.
2. Export or read source data in batches.
3. Load into target staging/archive using unique keys to catch duplicates.
4. Compare row counts, chunk checksums, and key business fields.
5. Persist a verified manifest/checkpoint on the target system.
6. Only after confirming target completeness, delete from source within the exact verified range.
7. If the job reruns, skip or reconcile existing records without creating duplicates.

If data can still change during export, take a consistent snapshot or use CDC to capture post-snapshot changes. Otherwise, the archive may miss updates or preserve stale state.

### Parent-Child Relationships and Constraints

When archiving a parent table, check child tables referencing it. You may need to archive child tables first, retain parent records in the hot table until dependencies clear, or store historical records in a denormalized/FK-free model with explicit business identifiers.

Never delete parent rows before handling child relationships. Do not assume an archive table in another schema/database preserves all source foreign keys; check FK limits and retrieval paths before moving data.

## 6. Batch-Deleting Expired Data

Once data is archived and verified, delete it from hot tables in batches:

~~~sql
DELETE FROM app.orders
WHERE created_at < '2025-01-01 00:00:00'
  AND status IN ('PAID', 'CANCELLED')
ORDER BY order_id
LIMIT 1000;
~~~

Repeat until no matching rows remain. Pause between batches as needed to ease I/O and replication pressure. Ensure an index supports the filter predicate—such as an index leading with `created_at` or a composite index matching `status` and `created_at`.

Never run large `DELETE` jobs during peak hours without monitoring:

- Execution duration and rows per batch.
- Row lock waits and deadlocks.
- Undo/redo volume, history list length, and purge lag.
- Binary logs, relay logs, and replica lag.
- Free disk space and log file growth rate.
- OLTP application latency and error rates.

If `DELETE` fires cascades, triggers, or audit writes, actual cost can far exceed the directly deleted row count. Measure impact on a production-like replica.

### Idempotency and Checkpoints

An archive job must be resumable after process crashes or network interruptions. Each batch should track:

- Unique `run_id`.
- Fixed cutoff.
- Start/end keys or last cursor.
- Status (`PENDING`/`RUNNING`/`VERIFIED`/`COMPLETED`/`FAILED`).
- Source row count, target row count, and checksums.
- Start/end timestamps and error details.

Never advance the checkpoint before target data is committed and verified. If checkpoints live in a different system from the archive database, design write ordering and reconciliation to handle crashes between the two commits.

## 7. Using Partitioning to Manage Time-Series Data

Partitioning divides a logical table into physical segments by rule. For historical tables with a timestamp column, `RANGE` partitioning lets you drop old time ranges quickly via DDL rather than row-by-row `DELETE`s.

Example monthly partitioned event table:

~~~sql
CREATE TABLE app.order_events (
    event_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    order_id BIGINT NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    payload JSON NULL,
    PRIMARY KEY (event_id, created_at),
    KEY idx_order_created (order_id, created_at)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p_before_2026_11
        VALUES LESS THAN ('2026-11-01 00:00:00'),
    PARTITION p202611
        VALUES LESS THAN ('2026-12-01 00:00:00'),
    PARTITION p202612
        VALUES LESS THAN ('2027-01-01 00:00:00'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
~~~

This example illustrates the structure; create future partitions before incoming data hits `MAXVALUE` and establish a calendar-based partition naming process. The primary key includes `created_at` because in MySQL partitioned tables, every unique key must include all columns used in the partition expression. Consequently, `event_id` is no longer guaranteed unique table-wide by that primary key alone.

### Dropping Old Partitions

When a partition passes retention and data has been archived or is no longer needed:

~~~sql
ALTER TABLE app.order_events
  DROP PARTITION p202611;
~~~

`DROP PARTITION` destroys all data inside that partition. It is a destructive operation; confirm cutoff, backups, archive manifest, and partition name before running. It does not automatically export data to an archive.

### Limitations to Know

- Every `UNIQUE` key on a partitioned table must include all partitioning columns.
- InnoDB partitioned tables do not support foreign keys under MySQL constraints.
- Certain index types, storage engines, data types, and DDL operations carry specific restrictions.
- Partition pruning helps only when queries filter properly on the partition key.
- Too many partitions increase metadata and management overhead.
- Partitioning does not replace indexes; each partition still needs appropriate indexes.

Do not partition every table simply because it is large. Partition only when query/retention rules are clear, data distributes well, and operations has processes to create, archive, drop, and monitor partitions.

### Partitioning Is Not Archiving

Partitioning manages and drops data ranges within the same table/instance. Archiving moves data to another store with independent access and retention policies. If history must be kept after dropping a partition, export/verify first or exchange/move the partition to an archive table prior to dropping.

## 8. Designing Summary Tables for Reporting

A daily recurring report does not need to scan the entire transaction table every run. You can build summary tables by day, store, product, or region so dashboards read far less data.

For example, an order fact table holds many millions of rows while a dashboard only needs daily revenue and order count per store. Create a summary table:

~~~sql
CREATE TABLE analytics.daily_sales (
    sales_date DATE NOT NULL,
    store_id BIGINT NOT NULL,
    order_count BIGINT NOT NULL,
    gross_amount DECIMAL(18,2) NOT NULL,
    updated_at TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (sales_date, store_id),
    KEY idx_daily_sales_store_date (store_id, sales_date)
) ENGINE=InnoDB;
~~~

Aggregation jobs on the analytics store can recompute a single day or date range:

~~~sql
START TRANSACTION;

DELETE FROM analytics.daily_sales
WHERE sales_date = '2026-11-18';

INSERT INTO analytics.daily_sales (
    sales_date, store_id, order_count, gross_amount
)
SELECT
    DATE(created_at) AS sales_date,
    store_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS gross_amount
FROM analytics.fact_orders
WHERE created_at >= '2026-11-18 00:00:00'
  AND created_at <  '2026-11-19 00:00:00'
  AND status = 'PAID'
GROUP BY DATE(created_at), store_id;

COMMIT;
~~~

Deleting and recomputing a bounded time window lets the job rerun safely without double-counting revenue. This example assumes `fact_orders` is already loaded into the analytics store and refreshes one day at a time. With concurrent jobs, use coordination locks or versioning so two jobs never delete/overwrite the same date window.

Never run this directly on the primary if aggregation scans a large OLTP table. Source data from a replica/CDC or analytics store, and write summaries where reporting queries run.

### Multi-Level Summaries

Summaries can be built at different granularities:

| Summary table | Grain — level of detail | Example query |
|---|---|---|
| `daily_sales` | Day × store | Daily revenue |
| `monthly_sales` | Month × region | Regional growth comparison |
| `product_sales` | Day × product | Top-selling products |
| `customer_activity` | Customer × month | Repeat purchase frequency |

Define grain explicitly. If a summary table has a day × store grain, you cannot derive per-product revenue from it without a product dimension or a separate summary table.

### Using `GROUP BY` and `ROLLUP`

For small datasets or ad hoc reports, MySQL can aggregate directly:

~~~sql
SELECT
    YEAR(created_at) AS sales_year,
    MONTH(created_at) AS sales_month,
    store_id,
    SUM(total_amount) AS gross_amount
FROM analytics.fact_orders
WHERE created_at >= '2025-01-01'
  AND created_at <  '2026-01-01'
  AND status = 'PAID'
GROUP BY
    YEAR(created_at),
    MONTH(created_at),
    store_id
WITH ROLLUP;
~~~

`ROLLUP` produces subtotal and grand total rows. Applications must distinguish `NULL` values generated by subtotals from genuine `NULL`s in source data. For recurring reports or large datasets, summary tables offer more predictable cost than recomputing every time.

### No Automatic Materialized Views in MySQL

MySQL does not provide auto-refreshing materialized views like some other database engines. Summary tables are typically maintained via scheduled events, batch applications, external schedulers, or ETL/CDC pipelines. Manage refresh schedules, idempotency, checkpoints, and reconciliation explicitly.

## 9. Choosing a Summary Update Strategy

There are three common approaches:

| Strategy | How it works | Best fit |
|---|---|---|
| Full refresh | Recompute the entire summary and replace the old version | Small datasets or long refresh windows |
| Incremental batch | Process only new time intervals or ID ranges | Large tables with checkpoints and mostly append-only data |
| CDC-based | Apply `INSERT`/`UPDATE`/`DELETE` events to the analytical model | Low latency and continuous change processing |

### Full Refresh

Advantages: simple logic and easy reconciliation. Drawbacks: re-reads all data, heavy I/O, and can cause downtime if replacement is non-atomic.

A safer pattern computes into a staging table, validates it, and then swaps versions or replaces data within an appropriate transaction. Never `TRUNCATE` a table actively queried by dashboards unless blank windows are acceptable.

### Incremental Batch

Persist a watermark such as update timestamp or monotonic key:

~~~sql
SELECT
    order_id,
    customer_id,
    status,
    total_amount,
    updated_at
FROM app.orders
WHERE updated_at > '2026-11-18 10:00:00'
  AND updated_at <= '2026-11-18 10:05:00'
ORDER BY updated_at, order_id;
~~~

Watermarks must have a deterministic order. If multiple rows share the same `updated_at`, pair it with a unique key to form a composite cursor, e.g., `(updated_at, order_id)`. Use a small overlap window combined with primary-key upserts at the target to avoid missing rows from coarse timestamp resolution, clock skew, or late-committing transactions.

If older rows can be `UPDATE`d or `DELETE`d, incremental scanning solely on `created_at` is insufficient. You need a reliable `updated_at`, tombstones, audit tables, or CDC to capture changes.

### CDC from the Binary Log

Change Data Capture reads mutation events from the MySQL binary log and streams them to other systems. A CDC pipeline typically:

1. Takes an initial snapshot or establishes a starting position.
2. Reads the binlog in commit order.
3. Applies row events to target models.
4. Saves processed checkpoints/offsets.
5. Resumes reading after restarts.

CDC fits continuous synchronization needs, yet requires managing binlog retention, schema evolution, large transactions, ordering, duplicate delivery, and replayability. Consumers should be idempotent because pipelines can replay events upon restarts or checkpoint recovery.

## 10. Synchronizing Data via Replicas and CDC

MySQL replication is typically asynchronous. The primary may commit before replicas apply the transaction. Consequently, reports reading from replicas can trail recent transactions.

### Monitoring Replica Lag

On a replica, inspect replication status per your version:

~~~sql
SHOW REPLICA STATUS\G
~~~

Useful fields include:

- `Replica_IO_Running` and `Replica_SQL_Running`.
- `Seconds_Behind_Source`.
- `Last_IO_Error` and `Last_SQL_Error`.
- `Source_Log_File`, `Read_Source_Log_Pos`.
- `Relay_Source_Log_File`, `Exec_Source_Log_Pos`.
- `Retrieved_Gtid_Set` and `Executed_Gtid_Set` when using GTIDs.

Field names differ in older versions (e.g., `Master` instead of `Source`). `Seconds_Behind_Source` is not an exact metric in every scenario; `NULL` can indicate an indeterminate state. Also monitor applier queues, executed GTIDs, transaction durations, and application-observed lag.

### Reports Needing the Latest Data

If a user just created an order and immediately opens the confirmation page, reading from a replica may miss the order. Options:

- Read from the primary during a read-after-write window.
- Wait for the replica to execute up to the committed GTID before reading.
- Attach a consistency token/version to the request and route reads accordingly.
- Design the UI to indicate syncing state if the business accepts eventual consistency.

Never assume every replica holds the exact same data as the primary at the same instant.

### Binlog Retention for CDC

CDC consumers can experience outages longer than planned. If MySQL purges binlogs before the consumer reads up to the needed position, the pipeline cannot resume from its old offset and may have to re-snapshot.

Set retention long enough based on:

- Maximum plausible outage duration.
- Peak binlog generation rate.
- Consumer recovery and backlog replay time.
- Disk space allocated for binlogs.
- Backup and point-in-time recovery policies.

Never purge binary logs merely to free disk space while replicas or CDC consumers still depend on those files.

## 11. Designing Analytical Data Models

Analytical data warehouses typically organize data into facts and dimensions:

- **Fact table:** stores measurable events or metrics that can be aggregated, such as orders, order lines, and payments.
- **Dimension table:** describes analytical attributes such as customers, products, stores, dates, and sales channels.

Example:

~~~text
                 dim_customer
                       |
dim_date ---- fact_order_line ---- dim_product
                       |
                  dim_store
                       |
                  dim_channel
~~~

Fact tables require an explicit grain. For instance, one row per order line item, not per order. If you run `SUM(total_amount)` on an order-line table where `total_amount` is the order-level total, revenue gets multiplied by the line-item count. Define grain and measures before writing reports.

### Dimensions That Change Over Time

Product names, categories, regions, or customer segments can change. When historical reports must reflect attributes as of the transaction date, track dimension history—for example, Slowly Changing Dimension Type 2 with `effective_from`, `effective_to`, and a `current_record` flag.

Simply overwriting current attributes causes historical reports to shift retroactively. Choose history tracking based on business needs rather than assuming dimensions are immutable.

### Standardizing Units and Timezones

Before aggregating, align on:

- Currencies and exchange-rate conversion rules.
- The timezone defining reporting dates.
- Rules for refunds, cancellations, and revenue adjustments.
- Definitions of valid orders and revenue recognition timing.
- Handling late-arriving data or corrections applied after aggregation.

For example, an order created at 23:30 UTC falls on a different calendar day when reported in Vietnam time. Never use `DATE(timestamp)` without establishing the business timezone.

## 12. Handling Late-Arriving Data and Historical Changes

Incremental pipelines often assume new data is strictly append-only. In reality, an older order may be refunded, change status, update store attribution, or be deleted per business rules. If summaries only add new events without accounting for historical mutations, reports gradually drift.

Scenarios requiring explicit rules:

- **Late-arriving data:** transactions with an earlier event time that arrive in the pipeline hours or days later.
- **Corrections:** amounts or statuses of historical records are amended.
- **Deletes/tombstones:** source records are deleted, requiring summaries to subtract or remove their prior contribution.
- **Duplicate events:** CDC or batch pipelines replay the same event.
- **Out-of-order events:** events arrive out of business sequence.

### Recomputing a Recent Rolling Window

A straightforward technique recomputes a recent window of days on every run—such as 3–7 days, depending on observed data delay. Run `DELETE` by date followed by `INSERT` of recomputed values inside a transaction on the analytics store. This handles late-arriving data within that window.

Adjustments older than the window require a dedicated correction/backfill flow. Never assume all late-arriving data falls within the last few days.

### CDC Requires Keys and Application Ordering

With CDC, store processed event IDs or source keys and checkpoints. If an event is redelivered, the consumer detects it and avoids applying it twice. For `UPDATE`s, capture before/after values or enough context to recalculate measures. For `DELETE`s, process tombstones or delete events to remove records from facts/summaries.

Never rely solely on timestamps as event keys when multiple changes can share the same timestamp. Use stable identifiers and binlog positions/offsets or GTIDs to preserve order and checkpoints.

## 13. Optimizing Reporting Queries

Offloading analytics does not mean SQL tuning can be ignored. A report scanning billions of rows can still choke an analytics store, inflate costs, and delay data freshness.

### Index-Friendly Time-Range Filtering

Avoid wrapping timestamp columns in functions inside filter predicates when range scans are needed:

~~~sql
-- Typically harder to utilize index on created_at
SELECT COUNT(*)
FROM analytics.fact_orders
WHERE DATE(created_at) = '2026-11-18';

-- Range form is generally more index-friendly
SELECT COUNT(*)
FROM analytics.fact_orders
WHERE created_at >= '2026-11-18 00:00:00'
  AND created_at <  '2026-11-19 00:00:00';
~~~

Half-open intervals `[start, end)` avoid microsecond boundary bugs and compose cleanly across consecutive days. Compute boundaries in the reporting timezone first, then convert to the consistent storage timezone.

### Selecting Only Needed Columns

Avoid `SELECT *` on large fact tables. Read only the dimension keys and measures required for aggregation. Reducing read width lowers I/O and memory needed for sorting, hashing, and grouping.

### Inspecting Execution Plans

~~~sql
EXPLAIN
SELECT
    store_id,
    SUM(total_amount)
FROM analytics.fact_orders
WHERE created_at >= '2026-11-01'
  AND created_at <  '2026-12-01'
  AND status = 'PAID'
GROUP BY store_id;
~~~

Check:

- Access type and partition pruning if the table is partitioned.
- Chosen index key and column order.
- Estimated rows versus actual rows.
- Temporary tables, filesorts, and `GROUP BY` cost.
- Join order and dimension cardinalities.

If your MySQL version supports it, run `EXPLAIN ANALYZE` in an appropriate environment to inspect actual row counts and timings. `EXPLAIN ANALYZE` executes the query; never run heavy reports casually on the production primary.

### Indexing for Reporting Workloads

Composite indexes must match filter predicates and access order. For example, a report filtering by `status` and `created_at` may require a different index than one filtering by `store_id` and `created_at`. Do not add per-report indexes without measuring write amplification and storage cost.

On large fact tables, secondary indexes increase storage, ingestion time, and maintenance cost. Analytical stores may use fewer indexes than OLTP, relying on time partitioning or columnar storage on dedicated platforms.

### Bounding Ad Hoc Queries

Enforce query timeouts, default date-range bounds, and concurrency limits for dashboards and ad hoc users. An unfiltered query without a date bound can scan the entire history; require users to specify a time window or run via batch pipelines.

## 14. Report Consistency

A report may read multiple tables or multiple ingestion batches. If different parts are read at different points in time, aggregate results can become inconsistent.

Handling options:

- Run queries inside a single consistent snapshot when multiple tables on one MySQL instance must align in time.
- Stamp analytics tables with `batch_id` or `data_version` and publish a batch only after all related tables finish loading.
- Load into staging schemas/tables and swap to the verified version.
- Display the last-updated timestamp on dashboards.
- For CDC-fed data, publish the applied checkpoint/GTID so users understand freshness.

In MySQL InnoDB, a `REPEATABLE READ` transaction provides a consistent read snapshot. However, overly long read transactions pin old snapshots and increase undo/purge pressure. Run long reports on an analytics store or dedicated snapshot rather than holding multi-hour transactions on the primary.

### Freshness and Correctness Are Distinct Metrics

- **Freshness:** how recent the latest ingested data is.
- **Correctness:** whether ingested data is complete, deduplicated, gap-free, and adheres to business rules.

A pipeline can be very fresh yet wrong due to duplicate events; or accurate yet one hour behind. Track both; never use replica lag alone to claim a report is accurate.

## 15. Backups, Recovery, and Retention of Archived Data

Archives are still data requiring protection. Moving data out of hot tables does not mean backups can be skipped.

Backup policies should cover:

- Scheduled backups of both OLTP and archive databases.
- Backups of the analytics store, or verified rebuildability from sources/CDC if chosen deliberately.
- Binary logs retained long enough for point-in-time recovery and CDC recovery.
- Archive file manifests and checksums.
- Encryption, access control, and backup storage locations.
- Periodic restore drills measuring RPO/RTO.
- Backup retention aligned with data deletion policies, including aging backups that still hold expired records.

If data deletion mandates apply to backups too, enforce backup expiration or platform-compliant purge procedures. Deleting a row from the primary does not immediately erase it from immutable backups.

### Archive Reconciliation

A per-batch manifest can store:

| Field | Purpose |
|---|---|
| `run_id` | Run identifier |
| `source_table` | Source table |
| `cutoff` | Fixed retention cutoff |
| `min_key` / `max_key` | Key range of the batch |
| `row_count` | Rows exported/loaded |
| `checksum` | Chunk-level reconciliation value |
| `schema_version` | Data schema version |
| `completed_at` | Verification timestamp |
| `status` | Batch status |

Compute checksums per chunk or over a deterministically ordered manifest. Never compare only a `SUM` of a numeric column, because two distinct datasets can yield the same sum.

## 16. Load Control and Scheduling

Run archiving, ETL, and reporting on schedules or within resource limits. Avoid running multiple full-table scan or index-rebuild jobs concurrently.

### Throttling Jobs

- Cap rows per batch.
- Pause between batches when CPU, I/O, or replica lag crosses thresholds.
- Lower ETL concurrency when the primary experiences peak load.
- Stagger archive, backup, and heavy reporting schedules if they share storage.
- Halt safely when disk space or binlog usage crosses alert thresholds.
- Support resuming from verified checkpoints.

### Monitoring Metrics

| Metric | Why it matters |
|---|---|
| OLTP p95/p99 latency | Detects impact on user requests |
| CPU and storage latency/IOPS | Measures resource contention |
| Replica lag and applier queue | Ensures read/CDC targets do not fall too far behind |
| Binlog volume and free disk | Prevents running out of disk or losing logs needed for CDC |
| Batch throughput and error rate | Detects slow jobs or recurring failures |
| Summary freshness | Shows how current report outputs are |
| Archive row counts/checksums | Confirms complete data transfer |
| Long transactions and lock waits | Detects jobs holding snapshots/locks too long |

Set thresholds from real baselines. A 5-second replica lag may be fine for an internal dashboard yet unacceptable for a payment confirmation screen.

## 17. Implementation Roadmap from OLTP to Analytics

**Phase 1 — Assessment**

1. Identify the fastest-growing tables and hot/cold data ratios.
2. Analyze reporting queries currently running on the primary.
3. Define freshness SLAs, retention, and historical lookup latency requirements.
4. Measure CPU, I/O, buffer pool, binlogs, and replica lag.
5. Map constraints, FKs, triggers, and application dependencies.

**Phase 2 — Design**

1. Choose archive tables, an archive instance, or object storage.
2. Choose read replicas, CDC, or batch ETL for each dataset.
3. Define grain, facts, dimensions, and summary tables.
4. Define watermarks/checkpoints, idempotency keys, and late-arriving data rules.
5. Design backups, restores, and retention for both source and archive.

**Phase 3 — Rehearsal**

1. Use a production-sized copy of data.
2. Run batch archiving and test failure recovery/resume.
3. Compare row counts, checksums, and sample records.
4. Simulate replica lag, binlog retention pressure, and CDC restarts.
5. Reconcile report outputs against verified source queries.
6. Measure OLTP impact and tune throttling.

**Phase 4 — Rollout**

1. Start with a single table or narrow time range.
2. Monitor latency, I/O, disk, replication, and application errors.
3. Verify archive/analytics integrity before deleting hot data.
4. Gradually expand tables and data ranges.
5. Switch dashboards to analytics once outputs reconcile.

**Phase 5 — Operations**

1. Schedule archiving, CDC, summary refreshes, and backups.
2. Monitor freshness, correctness, and backlogs.
3. Audit retention, legal holds, and purge processes.
4. Rehearse archive restores and report backfills.
5. Update schema contracts whenever applications modify source tables.

## 18. Common Design Mistakes

- **Archiving before verifying:** source data deleted while the archive lacks rows or has corrupted bytes.
- **Using a bare timestamp as a watermark:** misses multiple records sharing a timestamp or late-committing transactions.
- **Accumulating summaries on job retries:** revenue or order counts get doubled.
- **Reading solely from replicas:** reports miss fresh transactions and users suspect data loss.
- **Running heavy reports on the only replica:** replication lag spikes and degrades other read flows.
- **Dropping partitions without archiving:** permanently loses all data in the partition.
- **Ignoring FKs/child tables:** archiving parents breaks referential integrity or leaves orphan lookups failing.
- **Omitting schema versions:** older archived data cannot be decoded accurately after schema changes.
- **Insufficient binlog retention:** CDC cannot resume after outages.
- **Deleting backups too late or lacking retention:** data purged from primary persists in backups beyond allowed policy windows.

## 19. Operational Checklist

**Retention and Archiving**

- [ ] Retention policy defined per data tier/category.
- [ ] Only completed, eligible records are archived.
- [ ] Cutoff and batch ranges are fixed.
- [ ] Copy and delete execute in the same transaction when on the same instance.
- [ ] Across servers, staging, manifests, checksums, and verification precede purging.
- [ ] FKs, triggers, indexes, and app dependencies reviewed.
- [ ] Jobs are checkpointed and safe to rerun.

**Reporting and Summaries**

- [ ] Fact and summary table grains explicitly defined.
- [ ] Refresh jobs are idempotent.
- [ ] Late-arriving updates/deletes and duplicate events handled.
- [ ] Reporting queries use time filters and matching indexes.
- [ ] `EXPLAIN`/`EXPLAIN ANALYZE` checked in an appropriate environment.
- [ ] Dashboards display freshness/data version.

**Offloading and Recovery**

- [ ] Primary, replica, or analytics store selected per freshness SLA.
- [ ] Replication lag and binlog retention monitored.
- [ ] Backups/restores and archive reconciliation in place.
- [ ] Load limits, batch sizes, and pause/resume controls configured.
- [ ] CDC failures, backfills, and historical data recovery rehearsed.

## References

- [MySQL Reference Manual — Replication](https://dev.mysql.com/doc/refman/8.0/en/replication.html)
- [MySQL Reference Manual — Binary Log](https://dev.mysql.com/doc/refman/8.0/en/binary-log.html)
- [MySQL Reference Manual — Partitioning](https://dev.mysql.com/doc/refman/8.0/en/partitioning.html)
- [MySQL Reference Manual — InnoDB Consistent Read](https://dev.mysql.com/doc/refman/8.0/en/innodb-consistent-read.html)
- [MySQL Reference Manual — EXPLAIN](https://dev.mysql.com/doc/refman/8.0/en/explain.html)
- [MySQL Reference Manual — LOAD DATA](https://dev.mysql.com/doc/refman/8.0/en/load-data.html)

## Conclusion

Scaling MySQL for historical data and reporting requires decoupling data lifecycles from transactional traffic. Define retention first, archive in checkpointed batches, and purge only after verification; use partitioning when time-based rules apply while understanding unique-key and foreign-key limits; build summaries at clear grains with idempotent refreshes; and route analytical workloads to replicas or analytics stores based on freshness requirements. Combine CDC/ETL, backups, checksums, throttling, and monitoring so historical data remains retrievable while the primary continues serving OLTP reliably.
