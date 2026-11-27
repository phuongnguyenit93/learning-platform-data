# Deploying Schema Changes on Large Tables Under Active Application Traffic

## Objectives

After this lab, you will be able to:

- Plan MySQL schema changes on tables with tens or hundreds of millions of rows while the application continues serving traffic.
- Distinguish between Online DDL, Instant DDL, and online schema change tools.
- Use expand/contract to maintain compatibility during rolling deployments.
- Design batched backfills with checkpoints, idempotency, and crash-resume capability.
- Evaluate metadata locks, long-running transactions, replication lag, disk space, and workload impact.
- Define abort thresholds, rollback points, forward fixes, and the contract phase.
- Build a runbook with go/no-go criteria, observability, and post-deployment reconciliation.

## 1. Practice Context

An e-commerce system runs on MySQL InnoDB 8.4. The `orders` table holds roughly 120 million rows and grows by several hundred thousand rows daily. APIs, workers, and reports read and write to the table continuously. The engineering team wants to rename the `status` column to `order_status` while increasing its length from `VARCHAR(24)` to `VARCHAR(32)` to align with a new status convention.

During the period when both columns coexist, assume status values still fit within 24 characters and stay within the domain understood by V1. If longer values or new statuses must be written, widen the old column and update compatibility across all legacy readers before emitting those values; widening the column at the database layer alone is insufficient if V1 code still validates the old enum/domain.

Current schema:

~~~sql
CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(24) NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_orders_customer_created (customer_id, created_at)
) ENGINE=InnoDB;
~~~

Operational constraints:

- The API must keep serving requests throughout the entire process.
- Multiple application instances are updated via rolling deployment.
- Workers and cron jobs may run longer than an API deployment window.
- Replicas serve reports and selected read queries.
- Zero order updates may be dropped during backfill.
- The migration must be pausable if latency, lock waits, or replication lag exceed thresholds.

At the DDL level, this change looks simple: add a new column and drop the old one. Yet on a 120-million-row table, selecting the DDL algorithm, migrating data, coordinating multiple application versions, and handling failures are what determine success.

## 2. Design Principles Before Running DDL

Schema changes on large tables must be treated as a multi-phase release workflow rather than a single `ALTER TABLE` statement.

A safe workflow typically consists of:

1. **Discover:** inventory applications, queries, jobs, and consumers dependent on the old schema.
2. **Prepare:** test DDL, disk headroom, metadata locks, replication impact, and recovery procedures.
3. **Expand:** add new columns, indexes, or objects in a backward-compatible way.
4. **Deploy compatible code:** roll out code capable of reading/writing old and new structures.
5. **Backfill:** copy historical data into the new structure in batches.
6. **Validate:** reconcile data consistency and application behavior.
7. **Switch:** gradually shift read paths to the new structure.
8. **Contract:** remove old dependencies and drop legacy structures once all old consumers have drained.

Never skip discovery. A column may be queried by the core API, yet also appear in cron jobs, CSV exports, stored procedures, views, triggers, BI dashboards, ETL pipelines, or ad-hoc queries.

### 2.1. Dependency inventory

Before modifying the schema, locate every reference to `orders.status`:

- Entity/ORM mappings and native SQL inside application codebases.
- API instances, workers, queue consumers, cron jobs, and batch imports.
- Stored procedures, functions, triggers, views, and events.
- Reports, dashboards, ETL/CDC jobs, and data warehouses.
- Operational scripts, admin tools, and manual queries.
- Replicas, delayed replicas, backup/restore pipelines, and CDC consumers.

Query logs or Performance Schema can uncover currently running queries, yet cannot prove a periodic job will not run later. Combine source search, deployment inventories, job schedules, distributed traces, and discussions with system owners.

### 2.2. Application/schema compatibility matrix

Design release versions to preserve the old structure for as long as any dependent code remains active:

| Version | Reads | Writes | Schema Condition |
|---|---|---|---|
| Current V1 | status | status | Old schema |
| Compatible V2 | status | Both status and order_status | Expanded |
| Read-switched V3 | order_status | Both columns | Backfill verified |
| New-only V4 | order_status | order_status | Safe to contract after V2/V3 and all old consumers drain |

V2 and V3 can coexist once the new column is added: both write both columns, differing only in which column they read. Once V4 begins writing exclusively to the new column, the old column becomes stale for rows updated by V4. That marks the point of no return where rolling back to `status`-only readers is no longer safe. Treat the transition to write-new-only as an intentional milestone following observation and sign-off.

## 3. Evaluating Large-Table Change Approaches

Before choosing how to run DDL, verify which algorithm the specific operation supports on your exact MySQL version, storage engine, and table definition.

### 3.1. Three common InnoDB algorithms

| Algorithm | Behavior | Expected Impact |
|---|---|---|
| INSTANT | Modifies metadata for supported operations without rebuilding the table | Much faster, yet still requires a metadata lock; constrained by version and structure |
| INPLACE | Storage engine applies the change; may scan or rebuild internally depending on operation | May permit concurrent DML, yet still consumes I/O, CPU, and disk space |
| COPY | Builds a table copy, copies all rows, then swaps | Can require massive space and severely restrict concurrent writes |

`INPLACE` does not mean zero data copy or rebuild. `LOCK=NONE` does not mean zero locking of any kind. Exact support depends on the DDL type, MySQL version, InnoDB, row format, indexes, foreign keys, and table attributes.

### 3.2. Verifying support upfront

To append a new column at the end of the table when your version/conditions support instant add column, explicitly request `INSTANT`:

~~~sql
SET SESSION lock_wait_timeout = 5;

ALTER TABLE orders
    ADD COLUMN order_status VARCHAR(32) NULL,
    ALGORITHM=INSTANT;
~~~

`ALGORITHM=INSTANT` makes the migration fail cleanly if unsupported instead of silently falling back to an expensive table rebuild. However, never assume every `ADD COLUMN` is instant. Verify version limits, instant row version counts, column placement, and actual table structure; rehearse on a production-like replica.

To add an index:

~~~sql
ALTER TABLE orders
    ADD INDEX idx_orders_order_status_created
        (order_status, created_at),
    ALGORITHM=INPLACE,
    LOCK=NONE;
~~~

On InnoDB for supported operations, `LOCK=NONE` allows concurrent DML for most of the index build. If the server rejects that combination, the statement fails explicitly. Let the migration fail visibly rather than silently taking a lock that causes unexpected downtime.

Building an index on 120 million rows remains heavy work: it reads rows, sorts keys, writes index pages, consumes I/O, and can increase replication lag. Online DDL reduces write blocking; it does not make index creation free.

### 3.3. When to consider an online schema change tool

If direct DDL requires a table rebuild, lock duration is unacceptable, or copy throttling is needed, evaluate online schema change tools:

| Tool | High-Level Mechanism | What to Evaluate |
|---|---|---|
| gh-ost | Creates a ghost table, copies in chunks, and applies new changes from the binlog before cut-over | Requires suitable binlog format and stable unique key; lacks general foreign key support; verify triggers/topology |
| pt-online-schema-change | Creates a shadow table, copies in chunks, and uses triggers to sync ongoing writes | Evaluate existing triggers, foreign key handling, privileges, and per-DML trigger overhead |
| MySQL Online DDL | Uses InnoDB's native mechanism for supported operations | Simpler when requirements are supported, yet may still scan/rebuild and requires MDL |

Never run table-copy tools in production using blind default commands. Rehearse against a schema matching production's primary keys, foreign keys, triggers, generated columns, partitioning, replication topology, and write throughput.

With `gh-ost`, verify binlog requirements, row image, unique keys, and topology. With `pt-online-schema-change`, assess foreign key handling and existing triggers; sync triggers increase cost on every write. Both tools require disk headroom for the shadow table, indexes, binlogs, and operational buffers.

## 4. Preparing Before the Deployment Window

Never start without a baseline and explicit abort criteria. Capture normal operating metrics prior to migration so you can separate DDL impact from normal traffic variance.

### 4.1. Capturing a baseline

Record at minimum:

- Row counts and table/index sizes.
- `INSERT`/`UPDATE`/`DELETE` rates and query p50/p95/p99 latency.
- CPU, IOPS, disk throughput, and free disk space.
- Buffer pool usage and hit rate.
- Active connections, running threads, and long transactions.
- Lock waits and deadlocks.
- Replica lag and binlog apply speed.
- Binlog generation rate and retention.
- Application error rates, timeouts, and connection pool saturation.

Do not take just a single point-in-time snapshot. Capture baselines covering peak hours and scheduled batch jobs to understand real headroom.

### 4.2. Checking long transactions and metadata locks

Long-running transactions can hold shared metadata locks compatible with reads/writes, forcing `ALTER` to wait. Once a DDL waits on a metadata lock, subsequent queries queue behind it and cause sudden pile-ups.

Inspect active InnoDB transactions:

~~~sql
SELECT
    trx_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_seconds,
    trx_mysql_thread_id,
    trx_state,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Inspect metadata locks on the table:

~~~sql
SELECT
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS,
    OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'sales_app'
  AND OBJECT_NAME = 'orders';
~~~

Combine `performance_schema.threads`, `SHOW PROCESSLIST`, or `sys.schema_table_lock_waits` to locate sessions holding or waiting on locks. Before running DDL, establish who owns handling long transactions and under what criteria a session may be killed. Never kill sessions blindly without understanding what their transactions are doing.

### 4.3. Checking disk space and logs

When using online schema change tools or rebuilding DDL, budget space for:

- Original table and shadow/copy table.
- New secondary indexes.
- Temporary files and sort buffers used during MySQL DDL execution.
- Generated redo/undo and binary logs.
- Replica storage and backup impact.
- Headroom for ongoing application writes during the copy.

If the source table is 500 GB, a 500 GB shadow table plus indexes will not fit on a volume with 200 GB free. Factor in data growth during the migration window as well.

### 4.4. Backups and recovery

Prior to high-risk changes:

- Confirm the latest backup succeeded.
- Verify binary logs/PITR cover recovery to the desired timestamp.
- Verify the backup restores cleanly in an isolated environment.
- Document RPO/RTO and recovery owners.
- Define how new writes arriving after the backup will be preserved.

Backups are a data recovery mechanism, not a fast rollback button for a completed DDL. Restoring 500 GB can take hours and require traffic coordination; therefore, application rollbacks and forward fixes are usually the primary remediation while source data remains intact.

## 5. Expand Phase: Widening the Old Column and Adding the New Column

Because the requirement increases length from 24 to 32 characters, widen the existing column first so compatible versions can write identical values during dual-write:

~~~sql
SET SESSION lock_wait_timeout = 5;

ALTER TABLE orders
    MODIFY COLUMN status VARCHAR(32) NOT NULL,
    ALGORITHM=INPLACE,
    LOCK=NONE;
~~~

Run with `ALGORITHM=INPLACE, LOCK=NONE` only after confirming it is supported on your exact MySQL version and table definition. If the server rejects that algorithm/lock combination, stop to evaluate Online DDL alternatives or table-copy tools; never strip the clauses and re-run blindly in production. Widening `VARCHAR` can still trigger a scan/rebuild depending on conditions (such as crossing the 255-byte length-prefix boundary).

Once the old column is widened and verified, add `order_status` as nullable. V1 still uses only `status` and keeps running uninterrupted:

~~~sql
SET SESSION lock_wait_timeout = 5;

ALTER TABLE orders
    ADD COLUMN order_status VARCHAR(32) NULL,
    ALGORITHM=INSTANT;
~~~

If the instant statement fails, stop and diagnose why. Never remove `ALGORITHM=INSTANT` and retry immediately in production; doing so could trigger a heavy rebuild. Test on a replica and schedule Online DDL or a specialized tool if needed.

After expanding, inspect:

~~~sql
SHOW CREATE TABLE orders;

SELECT
    COUNT(*) AS total_rows,
    SUM(order_status IS NULL) AS rows_without_new_status
FROM orders;
~~~

Running `COUNT`/`SUM` across 120 million rows scans the table and generates I/O load. Run it only within your I/O budget, or substitute chunked checks or approved estimates. Immediately after adding a nullable column, having all rows with `order_status IS NULL` is expected.

Never enforce `NOT NULL` at this step while existing rows still lack values. Separate structural expansion from data backfill.

While V1 remains active, the application must continue emitting values valid under the old domain. Only after all legacy readers have drained may new versions emit longer strings or new domain values per a tested compatibility plan.

## 6. Deploying V2: Compatible Dual-Write

V2 continues reading `status` while writing both `status` and `order_status` in the same SQL statement or transaction.

Update example:

~~~sql
UPDATE orders
SET status = 'SHIPPED',
    order_status = 'SHIPPED',
    updated_at = NOW(6)
WHERE id = 90001;
~~~

Insert example:

~~~sql
INSERT INTO orders (
    customer_id,
    status,
    order_status,
    total_amount,
    created_at,
    updated_at
)
VALUES (
    501,
    'PENDING',
    'PENDING',
    125.50,
    NOW(6),
    NOW(6)
);
~~~

Dual-writes must be atomic. Avoid two separate non-transactional writes where a process could crash after updating the old column and before updating the new column.

During a rolling deployment, V1 instances can still write solely to `status`. Thus, do not assume new data is consistent or start switching reads yet. Wait until every V1 writer has drained:

- Old API instances have terminated.
- Old workers and queue consumers have restarted/drained.
- Old cron jobs have finished or been updated.
- Old import/maintenance scripts have been replaced.
- Zero processes remain capable of issuing SQL writing only `status`.

A deployment pipeline reporting success is not enough to prove all legacy writers stopped. Confirm via version heartbeats, instance inventories, job registries, and query logs.

### 6.1. When a legacy writer cannot be drained immediately

If an external system cannot upgrade right away, implement an explicit sync mechanism before backfill/switch. You may evaluate a temporary trigger or adapter service, provided you:

- Define a single source of truth for each phase.
- Handle `INSERT`, `UPDATE`, and `DELETE` as applicable.
- Prevent dual-write feedback loops between triggers and application code.
- Check existing triggers and execution order.
- Measure overhead across all DML.
- Set a retirement date and removal plan for the temporary mechanism.

Never assume a naive trigger cleanly handles every writer, bulk import, replication path, and schema evolution.

## 7. Backfilling 120 Million Rows in Batches

Once all writers perform dual-writes, historical rows still have `order_status IS NULL`. The backfill copies `status` into the new column.

### 7.1. Using primary-key keyset/range pagination

Avoid large `LIMIT ... OFFSET` queries because MySQL scans and discards progressively more rows. Paginate by primary key ranges:

~~~sql
UPDATE orders
SET order_status = status
WHERE id > 0
  AND id <= 10000
  AND order_status IS NULL;
~~~

The next batch processes 10000 through 20000, and so on. In production jobs, persist `low_id`, `high_id`, and checkpoints durably.

The `order_status IS NULL` predicate makes re-runs safe and avoids overwriting values already written by dual-writing applications. Because `status` in our example is `NOT NULL`, `NULL` in the new column reliably identifies un-backfilled rows. If the source column is nullable, add a dedicated migration flag or a rule distinguishing legitimate `NULL`s from unprocessed rows.

### 7.2. Short transactions per batch

Each batch must run in its own transaction:

~~~sql
START TRANSACTION;

UPDATE orders
SET order_status = status
WHERE id > 10000
  AND id <= 20000
  AND order_status IS NULL;

COMMIT;
~~~

A batch size of 10,000 rows is only a starting point. Tune batch size based on execution time, lock waits, undo/redo volume, I/O, CPU, and replica lag. Start around 1,000–5,000 rows, measure, and adjust; there is no fixed universal optimum.

Short transactions bound rollback work and row lock duration. Never run a single `UPDATE` across all 120 million rows if the system must preserve stable latency.

### 7.3. Checkpointing and resumability

A migration control table can track progress:

~~~sql
CREATE TABLE schema_backfill_progress (
    migration_name VARCHAR(100) NOT NULL PRIMARY KEY,
    last_id BIGINT UNSIGNED NOT NULL,
    max_id BIGINT UNSIGNED NOT NULL,
    rows_updated BIGINT UNSIGNED NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL,
    updated_at TIMESTAMP(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;
~~~

Seed record example:

~~~sql
SET @orders_max_id = (
    SELECT COALESCE(MAX(id), 0)
    FROM orders
);

INSERT INTO schema_backfill_progress (
    migration_name, last_id, max_id, rows_updated, status
)
VALUES (
    'orders_order_status_v1', 0, @orders_max_id, 0, 'RUNNING'
);
~~~

Worker loop:

1. Once all V1 writers have drained, capture a high-water mark via `MAX(id)` and persist it for this run.
2. Read `last_id`.
3. Compute the next `high_id` using chunk size, capped at the high-water mark.
4. Start a transaction.
5. Run the range `UPDATE`.
6. Update the checkpoint and updated row count in the same transaction.
7. Commit.
8. Sleep or throttle based on live metrics.
9. Repeat until reaching the end of the range.

The checkpoint must commit in the same transaction as the batch. Updating the checkpoint before the `UPDATE` commits risks skipping rows after a crash. If a batch commits yet the checkpoint does not, the batch re-runs safely thanks to the idempotent `order_status IS NULL` filter.

Rows inserted above the high-water mark are already populated by V2 dual-writes, so the backfill does not need to chase a continuously growing `MAX(id)`. Never rely on `rows_updated` alone to prove every row was processed—ID gaps exist from deletes or auto-increment behavior. After reaching the high-water mark, still run validation queries checking for remaining `NULL`s or mismatches.

Read the high-water mark via primary key:

~~~sql
SELECT COALESCE(MAX(id), 0) AS max_id
FROM orders;
~~~

Store `max_id` with migration metadata so every resume uses the exact same bound. If the job must re-check data written during execution, verify all writers are dual-writing and run a supplementary range verification pass instead of arbitrarily shifting `max_id`.

### 7.4. Backfill worker pseudocode

~~~java
while (true) {
    Progress progress = progressRepository.load("orders_order_status_v1");
    long lowId = progress.lastId();
    long maxId = progress.maxId();
    long highId = Math.min(lowId + chunkSize, maxId);

    transactionTemplate.executeWithoutResult(status -> {
        int updated = jdbcTemplate.update("""
            UPDATE orders
               SET order_status = status
             WHERE id > ?
               AND id <= ?
               AND order_status IS NULL
            """, lowId, highId);

        progressRepository.advance(
            "orders_order_status_v1",
            highId,
            updated
        );
    });

    if (highId == maxId) {
        break;
    }

    throttleIfNeeded();
}
~~~

This pseudocode illustrates execution ordering, not a production-ready worker. Production code must handle version/high-water mark mismatches, deadlocks, lock wait timeouts, bounded retries, cancellation, concurrent checkpoint updates, and progress locking so two workers never process overlapping ranges.

If running multiple workers, partition non-overlapping ranges and store per-range leases/ownership. Never let two workers increment one shared checkpoint without synchronization.

### 7.5. Impact on replicas and workloads

Backfilling updates many rows, generating redo, undo, and binary logs. Replicas must apply all of those changes. If backfill throughput exceeds replica apply capacity, replication lag climbs.

Throttle based on:

- Replica lag and catch-up speed.
- CPU, I/O, and disk queue depth.
- Row lock waits and deadlocks.
- API p95/p99 latency.
- Waiting connection counts.
- Undo tablespace and binlog disk usage.

Whenever predefined thresholds are breached, shrink chunk size, increase sleep intervals, or pause the job. Never keep pushing just because individual batches still succeed.

## 8. Validating Data After Backfill

Do not switch reads to the new column merely because the job reports `COMPLETED`. Reconcile data against explicit criteria.

### 8.1. Checking for missing values

~~~sql
SELECT COUNT(*) AS missing_rows
FROM orders
WHERE order_status IS NULL;
~~~

### 8.2. Checking for mismatches

~~~sql
SELECT COUNT(*) AS mismatch_rows
FROM orders
WHERE NOT (order_status <=> status);
~~~

The `<=>` operator performs NULL-safe equality. In this example, both columns must hold identical values. If the new design remaps or normalizes values, compare using the defined mapping expression rather than raw equality.

On huge tables, both `COUNT` queries can scan most or all of the table. Run them over primary-key ranges with bounded concurrency while watching I/O. Persist per-chunk validation results to pinpoint any range that fails.

### 8.3. Checking business distributions

Compare counts per status:

~~~sql
SELECT status, COUNT(*) AS row_count
FROM orders
GROUP BY status
ORDER BY status;

SELECT order_status, COUNT(*) AS row_count
FROM orders
GROUP BY order_status
ORDER BY order_status;
~~~

Outputs must match per the mapping. If the table continues receiving writes, two separate queries executed at different moments may show legitimate small differences. Reconcile inside a single consistent snapshot or by bounded range/version, documenting how active mutations are accounted for.

### 8.4. Range-based reconciliation

Example checking an ID slice:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(order_status IS NULL) AS missing_rows,
    SUM(NOT (order_status <=> status)) AS mismatch_rows
FROM orders
WHERE id > 1000000
  AND id <= 1100000;
~~~

Save per-range results, timestamps, max IDs, and migration versions. Once all ranges pass, run a final sign-off verification using your approved method.

### 8.5. Enforcing `NOT NULL` once data is clean

If the target schema requires `order_status` to be non-nullable, add `NOT NULL` only after all historical rows are backfilled and dual-writing writers always populate it:

~~~sql
ALTER TABLE orders
    MODIFY COLUMN order_status VARCHAR(32) NOT NULL,
    ALGORITHM=INPLACE,
    LOCK=NONE;
~~~

This is a separate DDL step that must be rehearsed on the target version and schema. Adding `NOT NULL` may require a table scan or rebuild depending on conditions. If `LOCK=NONE` is unsupported, evaluate alternatives and maintenance windows before running. Never enforce the constraint while any `NULL` rows remain.

## 9. Adding Indexes for New Queries

Suppose V3 filters orders by `order_status` and timestamp:

~~~sql
SELECT id, customer_id, total_amount, created_at
FROM orders
WHERE order_status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 100;
~~~

Planned index:

~~~sql
ALTER TABLE orders
    ADD INDEX idx_orders_order_status_created
        (order_status, created_at),
    ALGORITHM=INPLACE,
    LOCK=NONE;
~~~

Index column ordering must align with workload and selectivity. Never add an index solely because a query contains a `WHERE` clause; examine `EXPLAIN`, cardinality, sort order, covering requirements, and other queries sharing the index.

Verify the execution plan:

~~~sql
EXPLAIN
SELECT id, customer_id, total_amount, created_at
FROM orders
WHERE order_status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 100;
~~~

After creating the index, monitor disk usage, buffer pool pressure, write rates, and query latency. Every secondary index adds `INSERT`/`UPDATE`/`DELETE` overhead and storage cost. A planned `ANALYZE TABLE` may be needed to refresh statistics; assess impact and timing before running.

## 10. Switch: Shifting Read Paths to the New Column

Once backfill and validation pass, deploy V3. V3 reads `order_status` while continuing to dual-write both columns. This allows:

- Older V2 instances to read `status` and write both.
- Newer V3 instances to read `order_status` and write both.
- Both versions to coexist smoothly during rolling deployments.

### 10.1. Shifting traffic via feature flags

Rollout sequence:

1. Deploy V3 with the new-read feature flag defaulting to OFF.
2. Enable it for a small canary group of instances or tenants.
3. Compare old vs. new reads in shadow mode if appropriate.
4. Monitor error rates, latency, NULL/mismatch counts, and business metrics.
5. Ramp traffic gradually.
6. Enable globally once stability criteria pass.
7. Maintain dual-writes throughout an observation window so reverting to reading the old column remains possible.

Never flip 100% of traffic simultaneously without canary evidence. If the new query uses a new index, watch both execution plans and database load as traffic ramps.

### 10.2. Shadow reads and comparison

In some systems, you can read both columns in the same request or run comparison queries on a small sample:

~~~sql
SELECT
    id,
    status,
    order_status,
    (status <=> order_status) AS values_match
FROM orders
WHERE id = ?;
~~~

Avoid shadow-reading on every request if it doubles load on a large table. Use a sampling rate, canary tenant, or test subset, and log mismatches only after scrubbing sensitive fields.

## 11. Contract: Removing the Legacy Column

Execute the contract phase only when:

- All readers use `order_status`.
- All writers run on compatible versions.
- Workers, cron jobs, reports, stored objects, CDC consumers, and legacy scripts no longer reference `status`.
- Dual-writes have been intentionally retired and the team accepts closing the rollback window.
- New data has remained stable long enough.
- Backups/PITR and forward recovery are verified.
- The drop DDL has been rehearsed on a comparably sized replica.

After deploying the write-new-only version (V4), wait for all dual-write instances to drain. At this point `status` is no longer updated by the new application; never roll back to code reading the old column because its data may be stale.

### 11.1. Dropping the column

~~~sql
SET SESSION lock_wait_timeout = 5;

ALTER TABLE orders
    DROP COLUMN status,
    ALGORITHM=INSTANT;
~~~

This example specifies `ALGORITHM=INSTANT` so the statement fails cleanly if instant drop is unsupported for the table/version. Do not strip the clause and retry with defaults without assessing table rebuild/copy risks. Instant drop eligibility depends on MySQL version, row format, table limits, and column dependencies; if unsupported, schedule Online DDL or use an appropriate tool.

Dropping a column still requires metadata locks. Before running, check long-running transactions, lock waits, and operational windows. Afterward, verify applications, views, routines, and downstream consumers no longer query the dropped column.

### 11.2. Removing legacy compatibility code

After contract:

- Remove dual-write code.
- Remove migration feature flags.
- Remove the backfill job and progress table once migration evidence is archived.
- Clean up temporary metrics after the observation window.
- Update ORM mappings, schema documentation, and runbooks.
- Verify migration state in your schema management tool.

Do not delete logs/checkpoints immediately upon job completion if needed for audits or investigations. Retain evidence per operational policy.

## 12. Metadata Locks and Controlling Wait Times

Even Online DDL requires metadata locks at certain stages. An open read transaction can hold a metadata lock, blocking `ALTER`. Once `ALTER` is queued waiting on a metadata lock with higher priority, incoming queries pile up behind it.

Before DDL:

~~~sql
SET SESSION lock_wait_timeout = 5;
~~~

`lock_wait_timeout` governs metadata lock wait duration. It differs from `innodb_lock_wait_timeout`, which governs InnoDB row lock waits.

Never leave `lock_wait_timeout` huge so a migration waits indefinitely in production. If MDL cannot be acquired quickly, fail fast, inspect blocking transactions, and retry during a cleaner window.

While DDL runs, monitor:

- Pending/granted metadata locks.
- Process list and long-running transaction ages.
- API latency and connection pool wait times.
- Online DDL progress via Performance Schema if instrumented for that operation/version.
- CPU/I/O and replication lag.

If DDL gets stuck waiting on MDL and builds a query queue, operators must identify the blocker and consider aborting the waiting DDL before impact spreads. Never kill a blocker without assessing its rollback cost and business impact.

## 13. Monitoring Online DDL and Online Schema Change Tools

### 13.1. Direct Online DDL

Track:

- Prepare, execution, and commit/cut-over durations.
- CPU, I/O, temporary disk space, and index size.
- `innodb_online_alter_log_max_size` when concurrent DML fills the online alter log.
- MDL waits at DDL start and finish.
- Replica lag and binlog volume.
- Error log and statement state.

If the online alter log overflows during heavy concurrent DML, `ALTER` can fail. Raising the limit is not always the sole fix; evaluate write rates, DDL size, runtime, and available disk space.

### 13.2. Table-copy tools

With `gh-ost` or `pt-online-schema-change`, monitor:

- Copy throughput and remaining rows.
- Throttling on replica lag, server load, and peak hours.
- Shadow table and index disk usage.
- Binlog growth and binlog read capacity.
- Trigger overhead (especially with `pt-online-schema-change`).
- Cut-over lock and metadata lock wait times.
- State of original tables, shadow tables, and artifacts if the tool aborts.

Never manually drop ghost/shadow tables without confirming the tool's state. Use the cleanup/abort commands specific to your tool version and runbook.

## 14. Abort Conditions and Go/No-Go Criteria

Set concrete thresholds before starting, grounded in real system SLOs.

Example decision table:

| Metric | Go | Illustrative Pause / No-Go |
|---|---|---|
| API p95 latency | Near baseline | Sustained >30% increase for 5 minutes |
| API error rate | No significant increase | Exceeds SLO or doubles baseline |
| Replica lag | Stable within limits | Exceeds 60 seconds and keeps climbing |
| Free disk space | Sufficient headroom | Drops below defined safe operational floor |
| Lock waits | No abnormal queueing | Prolonged rise in MDL/row lock waits |
| DB CPU/I/O | Headroom remaining | Sustained saturation or core workload degradation |
| Backfill throughput | Steady | Sharp drop, rising deadlocks, or timeouts |

Thresholds above are examples for building a runbook. Production teams must calibrate limits from baselines, SLOs, replica capacity, and recovery time.

### 14.1. Go/no-go gates before each phase

**Before expand:**

- DDL rehearsed on a replica.
- Algorithm and lock mode confirmed.
- Disk space and MDL checked.
- Backup/PITR verified.
- On-call operators and abort criteria ready.

**Before backfill:**

- V2 fully deployed.
- All V1 writers drained.
- Dual-write verified via tests and metrics.
- Checkpointing, retries, and throttling tested.
- Replica and storage headroom confirmed.

**Before switch:**

- Zero missing or mismatched rows per validation rules.
- New indexes built and execution plans verified.
- Canary new reads error-free.
- Reverting to old-column reads still safe because dual-write remains active.

**Before contract:**

- Zero legacy consumers remain.
- Rollback to old schema officially retired or covered by an alternative recovery plan.
- Dual-writes stopped in proper order.
- Drop DDL rehearsed with a clean MDL window.

## 15. Rollback, Pause, and Forward Fix

Not every phase shares the same rollback capability.

| Phase | Failure Handling |
|---|---|
| Before expand | Cancel the plan; zero data changes needed |
| After expand, new column unused | Keep new column to investigate, or drop if confirmed safe |
| During dual-write | Pause rollout/backfill; app can keep reading old column while it remains accurately updated |
| After backfill, before switch | Keep new column, fix mapping, and re-run batches; no need to drop yet |
| After read switch, still dual-writing | Revert read flag to old column if mismatch/lag is contained |
| After write-new-only | Old column may be stale; simple rollback to legacy code is unsafe |
| After contract | Requires forward migration or controlled restore/repair to restore legacy structure |

MySQL DDL like `ALTER TABLE` typically triggers implicit commits. Never rely on SQL `ROLLBACK` to undo schema changes. For migrations that already altered structure or copied tables, follow tool-specific cleanup or create a forward migration.

### 15.1. When backfill fails mid-run

If a batch hits a deadlock or timeout:

1. Roll back the current batch.
2. Do not advance the checkpoint.
3. Log the error, range, and timestamp.
4. Shrink batch size or resolve lock contention.
5. Retry with bounded backoff.
6. Resume from the committed checkpoint.
7. Run range validation once finished.

Never retry infinitely, as doing so can mask a persistent schema or workload problem.

### 15.2. When Online DDL aborts

If DDL fails:

- Read the MySQL error and server error log.
- Determine whether the change completed, rolled back internally, or left artifacts.
- Check `SHOW CREATE TABLE` and metadata.
- Check MDL, disk space, and replicas.
- Never immediately re-run without understanding the root cause.

When using `gh-ost` or `pt-online-schema-change`, follow the state inspection and cleanup commands for your tool version. Never guess table names to drop ghost/shadow tables manually.

## 16. Application Rollback vs. Schema Rollback

Application rollback typically means redeploying an older container image or binary. Schema rollback means restoring the database structure and data to its pre-change state. The two are not equivalent.

In our example:

- When only `order_status` has been added, V1 keeps working because `status` still exists.
- During V2 dual-write, you can stop V2 and stay on V1 if no breaking domain changes were introduced.
- When V3 reads the new column while dual-writing, you can toggle the flag back to old reads.
- Once V4 writes only the new column, `status` stops receiving updates; reverting to V1 would read stale old data.
- After dropping `status`, rolling back to old application code fails with `Unknown column`.

Therefore, define explicit rollback boundaries in the deployment plan. Beyond write-new-only, favor forward fixes while new data remains trustworthy. If the old schema truly must be restored, add new columns/tables and backfill backward from a verified source of truth.

## 17. Organizing Migration Code and Operations

Never bundle DDL, a 120-million-row backfill, and the contract drop into a single synchronous startup migration executed when the application boots.

Split into observable units:

1. `Vxxx__expand_orders_order_status.sql`: add the new column.
2. Release V2: dual-write.
3. Backfill job: standalone runner with checkpoints and throttling.
4. Validation job: verify data and indexes.
5. Release V3: switch reads.
6. Release V4: stop writing old column once the rollback window closes.
7. `Vyyy__contract_orders_status.sql`: drop the old column.

Flyway or Liquibase can version DDL scripts. Long-running backfills should be standalone jobs with persistent state and pause/resume controls. Never let a schema migration tool hold a giant transaction or hit default timeouts over hours.

Each step requires:

- An owner and approver.
- Preconditions.
- Exact commands or artifacts.
- Metrics to monitor.
- Completion criteria.
- Abort criteria.
- Resume or forward-fix instructions.
- Validation evidence.

## 18. Sample Deployment Runbook

### T-7 days: preparation

- [ ] Inventory every consumer of `orders.status`.
- [ ] Select direct DDL or an online schema change tool.
- [ ] Rehearse on a replica matching production size and write rate.
- [ ] Measure DDL duration, I/O, disk space, MDL, and replica lag.
- [ ] Verify backups/PITR and test restore.
- [ ] Define batch size, chunk size, checkpoints, and throttling.
- [ ] Build dashboards and alerts.
- [ ] Prepare feature flags and rollback points.

### T-1 day: readiness check

- [ ] Confirm MySQL/Connector/ORM versions match rehearsal.
- [ ] Verify free disk space and binlog retention.
- [ ] Check for long-running transactions and sessions holding MDL.
- [ ] Confirm replicas are healthy with normal baseline lag.
- [ ] Confirm on-call, DBA, and application owners are ready.
- [ ] Freeze unrelated DDL during the change window.

### Deploy day: expand

- [ ] Set `lock_wait_timeout` on the migration session.
- [ ] Widen the legacy `status` column if new length is required and algorithm was rehearsed.
- [ ] Run `ADD COLUMN order_status` with the tested algorithm.
- [ ] Inspect `SHOW CREATE TABLE` and metadata.
- [ ] Watch latency, error rates, MDL, CPU/I/O, and replicas.
- [ ] If anomalies occur, halt before deploying V2.

### Deploy day: application and backfill

- [ ] Deploy V2 via rolling deployment.
- [ ] Confirm all V1 writers have drained.
- [ ] Verify dual-write on newly arriving rows.
- [ ] Start backfill at low throughput.
- [ ] Monitor each batch and tune throttling.
- [ ] Pause if SLOs or replica lag breach thresholds.
- [ ] Resume from checkpoint once conditions stabilize.

### Post-backfill: validate and switch

- [ ] Check missing/mismatched rows per range.
- [ ] Reconcile status distributions and business metrics.
- [ ] Enforce `NOT NULL` on `order_status` if required by target schema and DDL was rehearsed.
- [ ] Build/verify new indexes and execution plans.
- [ ] Deploy V3 behind a feature flag.
- [ ] Canary, shadow compare, and ramp traffic gradually.
- [ ] Keep dual-write active during the observation window.

### Contract

- [ ] Confirm zero legacy readers/writers or external consumers remain.
- [ ] Sign off on closing the rollback window.
- [ ] Deploy V4 writing only the new column.
- [ ] Drain all dual-write instances.
- [ ] Run drop DDL per MDL/online plan.
- [ ] Verify applications, reports, routines, and CDC after contract.
- [ ] Remove legacy code/flags/jobs and update documentation.

## 19. Lab Exercises

Create a test table with an auto-increment primary key and enough rows to observe resource impact. You do not need 120 million rows upfront; start with a few million rows and scale to fit lab resources.

### Exercise 1: Measuring DDL

1. Create `orders` with the old schema and secondary index.
2. Seed synthetic data in batches.
3. Run `ADD COLUMN ... ALGORITHM=INSTANT`.
4. Measure duration and confirm DML keeps running.
5. Test a DDL requiring a rebuild on a copy; record disk usage and duration.
6. Run `ADD INDEX ... ALGORITHM=INPLACE, LOCK=NONE`.
7. Observe Performance Schema, I/O, and replication if a replica is attached.

### Exercise 2: Rolling deployment and dual-write

1. Run V1 using only `status`.
2. Add `order_status`.
3. Deploy V2 reading the old column and writing both.
4. Keep one V1 writer active to demonstrate why backfill/switch cannot start yet.
5. Drain the V1 writer.
6. Generate concurrent updates and confirm both columns stay synchronized.

### Exercise 3: Checkpointed backfill

1. Build a job updating by primary-key range.
2. Persist checkpoints in the same transaction as each batch.
3. Stop the job mid-run and restart it.
4. Run concurrent application updates during the backfill.
5. Verify the job never overwrites dual-written values.
6. Simulate a deadlock/timeout and test retries.
7. Reconcile `NULL`s and mismatches by range.

### Exercise 4: Switch and contract

1. Create an index serving queries on `order_status`.
2. Run `EXPLAIN` and benchmark the query.
3. Deploy V3 reading the new column while dual-writing.
4. Enable the canary feature flag and watch metrics.
5. Deploy V4 writing only the new column after closing the rollback window.
6. Drain V3 and all legacy consumers.
7. Drop `status` on a replica and observe MDL.
8. Verify zero failing queries or lingering legacy schema dependencies.

## 20. Completion Criteria

A migration is marked complete only when all applicable conditions hold:

- New schema exists with exact definitions and indexes.
- Historical data is backfilled and reconciled.
- All writers and readers use the new structure.
- Zero consumers depend on the old column.
- Replica lag returned to baseline.
- API latency, error rates, and DB resources are stable.
- No orphaned migration jobs or ambiguous checkpoints remain.
- Backups/PITR and deployment evidence are archived.
- Legacy column contracted as planned.
- Runbooks, schema documentation, and migration history are updated.

## Self-Check Questions

1. Why shouldn't you rename a column directly on a huge table while V1 is still running?
2. How does `ALGORITHM=INSTANT` differ from `INPLACE`?
3. Why can `LOCK=NONE` still hit metadata lock waits?
4. When should you pick `gh-ost` or `pt-online-schema-change` over direct `ALTER`?
5. Why must legacy writers drain before backfilling?
6. How does `order_status IS NULL` make the backfill idempotent?
7. Why must checkpoints commit in the same transaction as the data batch?
8. How does batch size impact row locks, redo/undo, and replica lag?
9. When is it safe to switch reads to the new column?
10. Why is write-new-only a critical rollback boundary?
11. Why aren't backups a fast schema rollback mechanism?
12. Which metrics must be watched before, during, and after DDL?

## Conclusion

Deploying schema changes on large active tables requires coordinating DDL, code, data, and operations across distinct phases. Inventory dependencies, choose rehearsed algorithms, expand schemas backward-compatibly, roll out dual-writes, drain legacy writers, backfill in checkpointed batches, reconcile data, canary-switch reads, and only then contract. Online DDL and table-copy tools minimize downtime, yet still consume resources and require metadata locks. A plan is safe only when backed by clear abort criteria, rollback boundaries, forward-fix paths, and an actionable runbook.

## References

- [MySQL 8.4 Reference Manual — ALTER TABLE](https://dev.mysql.com/doc/refman/8.4/en/alter-table.html)
- [MySQL 8.4 Reference Manual — InnoDB Online DDL](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl.html)
- [MySQL 8.4 Reference Manual — InnoDB Online DDL Operations](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html)
- [MySQL 8.4 Reference Manual — Metadata Locking](https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html)
- [MySQL 8.4 Reference Manual — Online DDL Space Requirements](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-space-requirements.html)
- [GitHub — gh-ost](https://github.com/github/gh-ost)
- [Percona Toolkit — pt-online-schema-change](https://docs.percona.com/percona-toolkit/pt-online-schema-change.html)
- [MySQL 8.4 Reference Manual — InnoDB System Variables](https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html)
