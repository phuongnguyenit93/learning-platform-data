# Data Backfill by Stable Key and Resumability After Failure

Backfill is the process of populating or transforming data for existing rows after a schema change. Examples include adding a new column and computing its value from an existing column, normalizing historical data, populating classification codes, or migrating data into a new format. On large tables, backfills must be broken into small batches, track progress via a stable key, and persist checkpoints so execution can resume after a process stops.

A safe backfill coordinates three things: accurately identifying processed rows, avoiding overwriting newer application updates, and persisting progress in the same transaction as the data update. Storing only a processed row count or using `OFFSET` can cause the job to skip or reprocess rows when data changes. Writing a checkpoint before committing data can cause subsequent runs to skip rows that were never updated.

This lesson belongs to the **Schema Evolution** chapter of the **DATABASE_MYSQL** module. The module covers table design, data types, keys, SQL queries, indexes, transactions, privilege management, backups, and relational database operations. Content focuses on MySQL 8.0 and InnoDB; verify the version, isolation level, engine, and DDL behavior of your running system.

After this lesson, you will be able to:

- Design backfills ordered by a stable primary key or unique key.
- Use keyset pagination instead of `OFFSET`.
- Chunk batches, persist checkpoints, and resume execution after failures.
- Protect data while the application continues reading and writing during backfill.
- Handle composite keys, deleted rows, new rows, and batch retries.
- Throttle load on source, replicas, binary logs, and storage.
- Reconcile data to confirm backfill completion.

## 1. When does backfilling occur?

Backfilling is typically one step inside an expand-and-contract schema evolution strategy. Changes are rolled out in small phases so old and new applications can operate side by side during transition.

For example, an orders table initially stores customer names in `customer_name`. A new application feature requires `customer_name_normalized` for case-insensitive search:

~~~sql
ALTER TABLE sales.orders
  ADD COLUMN customer_name_normalized VARCHAR(200) NULL;
~~~

After adding the column, existing rows remain `NULL`. Backfilling computes data for those rows:

~~~sql
UPDATE sales.orders
SET customer_name_normalized = LOWER(TRIM(customer_name))
WHERE customer_name_normalized IS NULL;
~~~

For a few thousand rows, one `UPDATE` statement may finish quickly. On tens or hundreds of millions of rows, one huge statement can hold locks long, generate massive redo/undo and binary logs, spike replica lag, and disrupt online transactions. Splitting into small batches controls lock duration, load, and recoverability.

Common scenarios:

- Adding a new column derived from existing columns.
- Converting date formats, area codes, phone numbers, or normalized strings.
- Populating a new foreign key based on a reference table.
- Moving data from legacy columns into new structures.
- Populating default values according to new business rules.
- Materializing data for new indexes or search paths.

If a value can be derived automatically via a generated column without needing separate physical backfill, evaluate that option before building a backfill pipeline. Backfills fit cases requiring physical storage, stateful transformations, or calculations that cannot be expressed cleanly as a generated column.

## 2. Design principles

A reliable backfill process needs these properties:

1. **Deterministic ordering.** Every row is identified by a unique key that does not change during the run.
2. **Safe repeatability.** Re-running a batch does not corrupt already-correct data.
3. **Durable checkpoints.** Progress is stored in the database or a reliable state store.
4. **Atomic checkpoint with data.** Each batch's data updates and cursor position commit in the same transaction.
5. **Compatibility with concurrent writes.** The application can keep modifying data without the backfill overwriting newer values.
6. **Bounded resources.** Small batches, pause support, and adjustable throughput.
7. **Final reconciliation.** Never treat the cursor reaching the end of the key range as sole proof that every row is correct.

Never measure progress solely by counting updated rows. Rows may be deleted, inserted, filtered out, or have gaps in key values. A stable key marks the scanned position, while backfill predicates and reconciliation verify that values were accurately migrated.

## 3. Choosing a stable key

### 3.1. Prefer an immutable primary key

Example table with primary key `order_id`:

~~~sql
CREATE TABLE sales.orders (
  order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_name VARCHAR(200) NOT NULL,
  customer_name_normalized VARCHAR(200) NULL,
  updated_at TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (order_id)
) ENGINE=InnoDB;
~~~

`order_id` works well as a cursor provided the application never mutates key values after row creation. Batch selection can use:

~~~sql
SELECT order_id
FROM sales.orders
WHERE order_id > ?
ORDER BY order_id
LIMIT 500;
~~~

Each batch fetches up to 500 keys greater than the current cursor. After processing succeeds, the cursor advances to the highest key in that batch.

A stable key does not need to be contiguous. If key values are 1, 2, 7, 20, the job cleanly steps from 2 to 7, then 20. Never assume every integer key exists.

### 3.2. Avoid OFFSET on large tables

`OFFSET` pagination is generally unsuitable for large-scale backfills:

~~~sql
SELECT order_id
FROM sales.orders
ORDER BY order_id
LIMIT 500 OFFSET 500000;
~~~

As offset grows, the server must read and discard increasingly many rows before returning the requested batch. If rows are inserted or deleted concurrently, offset positions shift, causing skipped or duplicated rows.

Keyset pagination uses the last seen key value:

~~~sql
SELECT order_id
FROM sales.orders
WHERE order_id > ?
ORDER BY order_id
LIMIT 500;
~~~

This query leverages the primary key index and resumes from an exact position. With extra filter predicates, ensure a suitable index exists so each batch does not scan excessive rows.

### 3.3. Composite keys

Some tables use a composite primary key, such as `(tenant_id, order_id)`. The cursor must store all key components to pinpoint a unique position.

Lexicographical continuation can be written explicitly:

~~~sql
SELECT tenant_id, order_id
FROM sales.tenant_orders
WHERE tenant_id > ?
   OR (tenant_id = ? AND order_id > ?)
ORDER BY tenant_id, order_id
LIMIT 500;
~~~

Or using a row constructor in supported queries:

~~~sql
SELECT tenant_id, order_id
FROM sales.tenant_orders
WHERE (tenant_id, order_id) > (?, ?)
ORDER BY tenant_id, order_id
LIMIT 500;
~~~

Check the execution plan on your MySQL version to confirm index utilization. In the checkpoint, persist both `tenant_id` and `order_id`; storing only one component cannot uniquely identify position.

### 3.4. When no suitable key exists

If a table lacks a stable primary key or unique key, assess how rows will be identified before backfilling. Either add an appropriate key in a prior migration or use an existing unique key if it is truly unique and immutable.

Never use `updated_at` as the sole cursor if multiple rows share timestamps or timestamps change mid-run. Never use physical row position, default `SELECT` order, or non-unique columns as a checkpoint.

## 4. Choosing range bounds and high-water marks

For tables continuously receiving new rows, capture a high-water mark at the start of the backfill:

~~~sql
SELECT MAX(order_id) AS high_watermark
FROM sales.orders;
~~~

Suppose the result is 9000000. The job processes up to that bound:

~~~sql
SELECT order_id
FROM sales.orders
WHERE order_id > ?
  AND order_id <= 9000000
ORDER BY order_id
LIMIT 500;
~~~

A high-water mark gives the run a deterministic stopping point instead of chasing newly inserted rows forever. However, it does not replace concurrent-write protection.

If the application or an import pipeline can insert rows with keys less than or equal to the high-water mark, a new row could land behind the cursor and be missed on the initial pass. Even with `AUTO_INCREMENT`, never assume new keys are always strictly greater than the cursor across all systems, as explicit ID imports or delayed inserts may occur.

Mitigations:

- Enable dual-write or an equivalent sync mechanism before starting the backfill.
- Run a reconciliation pass after scanning the initial range.
- If continuous external writers exist, use a change log/CDC or change-tracking mechanism to catch trailing changes.
- Conclude the migration only once missing rows are reconciled and zero legacy write paths remain active.

For composite keys, the high-water mark must likewise include every key component.

## 5. Designing checkpoints

Checkpoints store a job's progress so execution can resume if the application, worker, or server stops. A dedicated table can be used:

~~~sql
CREATE TABLE ops.backfill_checkpoint (
  job_name VARCHAR(100) NOT NULL,
  last_order_id BIGINT UNSIGNED NULL,
  high_watermark BIGINT UNSIGNED NOT NULL,
  rows_scanned BIGINT UNSIGNED NOT NULL DEFAULT 0,
  rows_changed BIGINT UNSIGNED NOT NULL DEFAULT 0,
  status ENUM('PENDING', 'RUNNING', 'PAUSED', 'DONE', 'FAILED')
    NOT NULL DEFAULT 'PENDING',
  updated_at TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (job_name)
) ENGINE=InnoDB;
~~~

Field meanings:

- `job_name`: unique backfill run identifier; distinguishes different migrations.
- `last_order_id`: last key scanned and committed successfully; `NULL` indicates not yet started.
- `high_watermark`: upper bound of the current pass.
- `rows_scanned`: count of inspected rows, potentially including rows needing no update.
- `rows_changed`: count of rows actually modified by the update predicate.
- `status`: operational status indicating whether the job is running, paused, or done.

Checkpoint key types must match the actual key types. If the primary key is signed `BIGINT`, `UUID`, string, or composite, design cursor columns accordingly. For composite keys, store each component and maintain one checkpoint per worker/range when parallelizing.

Initialize the job once the range is determined:

~~~sql
INSERT INTO ops.backfill_checkpoint (
  job_name,
  last_order_id,
  high_watermark,
  status
)
SELECT
  'orders-normalize-name-v1',
  NULL,
  COALESCE(MAX(order_id), 0),
  'PENDING'
FROM sales.orders;
~~~

`COALESCE(MAX(...), 0)` in this example assumes unsigned keys starting at 1. If keys can be 0, negative, or non-numeric, use an appropriate sentinel or store a separate started flag.

Never store checkpoints in a local log file as the sole source of state. If the worker host is lost, local files diverge from committed database transactions.

## 6. Safe repeatable batch updates

Suppose we populate `customer_name_normalized` from `customer_name`. A batch processes keys from `last_id` to `batch_end`:

~~~sql
UPDATE sales.orders
SET customer_name_normalized = LOWER(TRIM(customer_name))
WHERE order_id > ?
  AND order_id <= ?
  AND customer_name_normalized IS NULL;
~~~

The predicate `customer_name_normalized IS NULL` makes the operation idempotent when the target value only needs to be populated once. If a batch re-runs, already-populated rows are skipped.

However, `NULL` can be a valid transformation outcome in some domains. In that case, `target IS NULL` cannot serve as the sole indicator of unprocessed rows. Add a dedicated status/version column or define another completion condition.

Example using a migration flag:

~~~sql
ALTER TABLE sales.orders
  ADD COLUMN name_backfill_version TINYINT UNSIGNED NOT NULL DEFAULT 0;
~~~

Then:

~~~sql
UPDATE sales.orders
SET customer_name_normalized = LOWER(TRIM(customer_name)),
    name_backfill_version = 1
WHERE order_id > ?
  AND order_id <= ?
  AND name_backfill_version = 0;
~~~

A flag is meaningful only if updated atomically alongside the target value in the same statement or transaction. Never split them into two separate commits.

## 7. Updating data and checkpoint in the same transaction

The most important rule for exact resumability: commit batch data updates and the batch cursor inside the same InnoDB transaction.

Processing flow for one batch:

1. Read the current checkpoint and determine the batch end key.
2. Start a transaction.
3. Update rows in the batch.
4. Update the checkpoint to the batch end key and progress counters.
5. Commit the transaction.
6. Only after commit, report batch completion or advance the in-memory cursor.

Illustrative transaction once the orchestrator has computed `@last_id`, `@batch_end`, and `@scanned_count`:

~~~sql
START TRANSACTION;

UPDATE sales.orders
SET customer_name_normalized = LOWER(TRIM(customer_name))
WHERE order_id > @last_id
  AND order_id <= @batch_end
  AND customer_name_normalized IS NULL;

SET @changed_rows = ROW_COUNT();

UPDATE ops.backfill_checkpoint
SET last_order_id = @batch_end,
    rows_scanned = rows_scanned + @scanned_count,
    rows_changed = rows_changed + @changed_rows,
    status = 'RUNNING'
WHERE job_name = 'orders-normalize-name-v1';

COMMIT;
~~~

Session variables `@last_id`, `@batch_end`, and `@scanned_count` must be set by the orchestrator prior to running the transaction. In application code, prefer prepared statements and bound parameters.

Because data and checkpoint commit together:

- If an error occurs before commit, both data updates and checkpoint roll back.
- If commit succeeds yet the client disconnects before receiving the response, the next run reads the committed checkpoint and continues with the next batch.
- If a coordination bug causes a batch to re-run, idempotent predicates prevent overwriting completed rows.

Never commit the checkpoint before committing data. Doing so can mark a key range completed even though data was never updated.

### 7.1. Note on ROW_COUNT()

`ROW_COUNT()` returns the number of rows affected by the preceding statement per MySQL rules. For `UPDATE`, it typically reflects rows actually modified, not necessarily all rows scanned or matched if the new value equals the existing value.

If you need to report all three metrics, track them separately:

- `rows_scanned`: count of keys traversed.
- `rows_matched`: count of rows matching business predicates.
- `rows_changed`: count of rows whose values actually changed.

Do not use a single counter to infer both scan progress and mutated data volume.

## 8. Selecting batch boundaries

Two approaches are common.

### 8.1. Fetch a key list, then update

The application queries up to N next keys:

~~~sql
SELECT order_id
FROM sales.orders
WHERE order_id > ?
  AND order_id <= ?
ORDER BY order_id
LIMIT 500;
~~~

Take the last key as `batch_end`, then update the range from the previous cursor to that key in the same transaction as the checkpoint. This is easy to implement and leverages the primary key index.

If you want to target only the exact fetched key list rather than the range, you can use a temporary table or bound parameters in `IN (...)`, respecting statement size and placeholder limits. With range updates, rows newly inserted within the range prior to the update may also be updated; dual-writes remain necessary to protect rows inserted afterward.

### 8.2. Fixed key intervals

For numeric keys with suitable distribution, you can partition into fixed intervals like `[1, 10000]`, `[10001, 20000]`. Each range is an independent work unit.

This simplifies multi-worker parallelization since ranges can be pre-allocated. However, equal key spans do not mean equal row counts: data may have sparse gaps or dense clusters. Measure execution time and actual row counts per range.

For composite or string keys, interval partitioning must respect column comparison order and collation. Never compute intervals via arithmetic on strings or UUIDs. Instead, derive ranges from sorted actual keys or partition by tenant.

## 9. Concurrent writes from the application

Backfills usually run while the application reads and writes. If the application keeps writing only the old column after the backfill has passed a row, the new column immediately becomes stale.

Example:

1. Backfill reads `customer_name = 'An'` and writes `customer_name_normalized = 'an'`.
2. Application updates `customer_name = 'Bình'`.
3. If the application does not update the new column, the normalized value stays `'an'`, out of sync with the source.

Enable dual-writes or a synchronization mechanism before starting the backfill:

- New application code writes both old and new columns in the same transaction.
- Or use a well-designed, tested trigger to synchronize both columns.
- Or capture changes via change log/CDC and apply them to the new column.
- Stop writing the old column only after all applications have switched to the new schema and data is reconciled.

A typical rollout sequence:

1. Add the new column as nullable.
2. Deploy application code with compatible reads and dual-writes to both columns.
3. Confirm every writer is dual-writing.
4. Run batched backfill.
5. Run reconciliation to catch missed rows or concurrent updates.
6. Switch application reads to the new column.
7. Monitor for an observation window before stopping writes to the old column.
8. In a separate migration, consider setting `NOT NULL`, dropping legacy columns, or removing obsolete constraints.

Never run a backfill before accounting for legacy writers. When multiple application versions run concurrently, know precisely which version writes which column.

## 10. Avoiding overwriting newer data

If the transformation is computed directly in SQL from the current source column, the `UPDATE` reads the current source value at execution time and writes the target in the same statement. This is usually safer than reading data out to the application, computing externally, and writing back later.

If transformation must occur outside the database, use optimistic concurrency control. For instance, read `updated_at` or `version` with the row, then update only if unchanged:

~~~sql
UPDATE sales.orders
SET customer_name_normalized = ?,
    name_backfill_version = 1
WHERE order_id = ?
  AND updated_at = ?
  AND name_backfill_version = 0;
~~~

If the statement updates 0 rows, source data may have changed or another writer processed the row. Re-read and recompute; never overwrite blindly with stale values.

`updated_at` is suitable only when reliably updated on every relevant change and with sufficient precision. A monotonically increasing `version` column is clearer for contention detection. Low-resolution timestamps or manually set timestamps should not be relied upon as unique version tokens.

## 11. Transaction size and lock duration

Batches that are too large can:

- Hold row locks too long and stall application requests.
- Generate massive undo/redo logs.
- Increase commit latency and binary log spikes.
- Slow down replica apply.
- Increase the cost of transaction rollbacks.
- Saturate buffer pool and I/O, degrading other workloads.

Batches that are too small add overhead from excessive transactions, network round trips, and checkpoint updates. Choose batch size based on actual execution time, not row count alone.

A practical starting point is a few hundred to a few thousand rows per batch, tuned by row width and storage speed. Aim for transactions short enough to bound lock time while large enough to avoid spending most time on per-batch overhead.

Monitor application latency, lock waits, deadlocks, redo generation, binary log growth, and replica lag. If metrics breach thresholds, shrink batch size or pause.

## 12. Retrying on deadlocks, timeouts, or disconnects

Deadlocks and lock wait timeouts can happen when backfills contend with live transactions. Handle them cleanly:

1. Identify retryable errors such as deadlocks or lock wait timeouts.
2. Roll back the entire batch transaction.
3. Wait briefly with backoff and jitter.
4. Re-read the committed checkpoint from the database.
5. Re-run the batch from that cursor.
6. Cap retry attempts and alert when thresholds are exceeded.

Never resume from a key partway through a rolled-back batch. Because the batch transaction updates both data and checkpoint, rollback reverts both to pre-batch state.

If the client disconnects right after `COMMIT`, never guess from a timeout alone that the commit failed. Reconnect, read the checkpoint from the database, and decide from there. This is why durable database checkpoints matter far more than in-memory worker variables.

Do not automatically retry every SQL error. Schema errors, missing privileges, invalid data, or logic bugs must be classified and handled separately.

## 13. Multiple workers and work partitioning

Multiple workers can speed up backfills when ranges are independent and server capacity allows. Each worker needs a non-overlapping range or an explicit work-claiming mechanism.

Example range partitioning:

| Worker | order_id range |
|---|---|
| A | 1 to 2,000,000 |
| B | 2,000,001 to 4,000,000 |
| C | 4,000,001 to 6,000,000 |
| D | 6,000,001 to high-water mark |

Each worker stores its own checkpoint keyed by `job_name` and `worker_id`, or updates status in a range management table. Never let multiple workers update one shared global cursor without coordination locking; one worker can overwrite another worker's progress.

You can use a queue/range table with states `PENDING`, `RUNNING`, `DONE`, a lease expiration, and a worker owner. If a worker dies, its lease expires so another worker can reclaim the range. Claiming ranges and renewing leases must be transactional so two workers never claim the same range.

### 13.1. Caution with SKIP LOCKED

`SELECT ... FOR UPDATE SKIP LOCKED` is helpful for multi-worker queues, yet does not naturally fit a monotonic cursor. If a worker skips a locked row and advances its checkpoint past that key, the skipped row may never be processed again.

If using `SKIP LOCKED`, track per-row or per-range completion explicitly and implement a retry sweep for skipped rows. For sequential keyset backfills, it is usually simpler not to skip locks: wait within lock timeout, roll back the batch if needed, and retry from checkpoint.

### 13.2. Do not add workers when bottlenecked on shared resources

All workers contend for CPU, I/O, buffer pool, redo log, binary log, and replica apply. If the primary is saturated, adding workers degrades total throughput. Start with one worker, measure, and scale up gradually; pick worker count based on useful throughput and impact on live traffic.

## 14. Throttling and monitoring

Backfilling is a background workload yet produces real data mutations. Set thresholds so the job throttles down or pauses under high system load.

Signals to monitor:

- Mean and p95 application transaction latency.
- Lock waits, deadlocks, and timeouts.
- CPU, memory, disk IOPS, and storage latency.
- InnoDB redo/undo pressure and dirty pages.
- Binary log growth rate.
- Replica lag and applier status.
- Completed batches, rows scanned, and rows changed.
- Retry counts and inter-batch sleep durations.

You can add pauses between batches:

~~~text
while ranges remain to be processed:
    read committed checkpoint
    determine next batch
    run update + checkpoint in one transaction
    commit
    emit metrics
    if load exceeds threshold:
        pause or shrink batch
    else:
        sleep briefly then continue
~~~

This pseudocode describes orchestration flow; query execution and retries must be implemented in a client or worker with proper transaction control. Never run an unbounded loop inside a single long transaction.

If replica lag rises continuously, throttle down or pause the backfill so replicas catch up. If binary logs grow rapidly, confirm sufficient storage and retention for replicas/PITR before proceeding. Never purge logs just to free disk space if replicas or recovery pipelines still need them.

## 15. Reconciliation and completion verification

The cursor reaching the high-water mark proves only that the job scanned the key range per its rules. It does not prove every row has the right value. Late-inserted rows, skipped rows, conversion errors, or stray non-dual-writing writers may remain.

Run reconciliation queries after backfilling:

~~~sql
-- Rows not yet marked complete
SELECT COUNT(*) AS remaining
FROM sales.orders
WHERE order_id <= :high_watermark
  AND name_backfill_version = 0;

-- Inspect sample rows with mismatched values
SELECT order_id, customer_name, customer_name_normalized
FROM sales.orders
WHERE order_id <= :high_watermark
  AND NOT (
    customer_name_normalized <=> LOWER(TRIM(customer_name))
  )
LIMIT 100;
~~~

`<=>` is MySQL's null-safe equality operator, catching cases where one side is `NULL` and the other is not. If your conversion has different business rules, substitute that exact comparison expression.

On large tables, full-table reconciliation queries can generate heavy load. Chunk them by key ranges or use batched aggregates/checksums. Reconcile against a consistent snapshot or after writers are dual-writing to avoid chasing moving results during inspection.

Once all ranges finish and reconciliation passes, update job status:

~~~sql
UPDATE ops.backfill_checkpoint
SET status = 'DONE'
WHERE job_name = 'orders-normalize-name-v1'
  AND last_order_id >= high_watermark;
~~~

Completion checks must combine reconciliation results and writer status. Never mark `DONE` merely because the cursor passed the high-water mark if unconverted rows remain.

## 16. Complete backfill workflow example

Suppose `sales.orders` has primary key `order_id` and needs a normalized column populated. The new application already dual-writes `customer_name` and `customer_name_normalized`.

A worker can execute the following sequence:

~~~text
1. Read job checkpoint:
   last_order_id, high_watermark, status.

2. If status = DONE:
   stop.

3. Fetch batch:
   SELECT order_id
   FROM sales.orders
   WHERE order_id > last_order_id
     AND order_id <= high_watermark
   ORDER BY order_id
   LIMIT 500;

4. If no rows returned:
   run range reconciliation;
   mark DONE only if zero rows remain needing backfill.

5. Set batch_end = last scanned order_id.

6. START TRANSACTION.

7. UPDATE rows in range:
   SET customer_name_normalized = LOWER(TRIM(customer_name))
   WHERE order_id > last_order_id
     AND order_id <= batch_end
     AND name_backfill_version = 0;

8. Capture changed row count immediately after UPDATE.

9. UPDATE checkpoint:
   last_order_id = batch_end,
   increment rows_scanned and rows_changed.

10. COMMIT.

11. On transaction error:
    ROLLBACK, re-read checkpoint, retry batch with bounded attempts.

12. Emit metrics, throttle speed, and repeat.
~~~

In real code, batch reading, updating, and checkpointing must prevent another worker from mutating the same cursor. With a single worker, lock the checkpoint row using `SELECT ... FOR UPDATE` inside the transaction. With multiple workers, use per-worker/range checkpoints or range claiming.

Example locking the checkpoint row:

~~~sql
START TRANSACTION;

SELECT last_order_id, high_watermark, status
FROM ops.backfill_checkpoint
WHERE job_name = 'orders-normalize-name-v1'
FOR UPDATE;
~~~

After reading and validating status, the worker determines the batch, updates data and checkpoint, and commits. Never hold the checkpoint lock while sleeping or processing data outside the database; keep transactions short so other workers are not unnecessarily blocked.

## 17. Common pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Batches get slower over time | Large `OFFSET`, missing index, or overly wide batch | Switch to keyset pagination, check `EXPLAIN`, and shrink range. |
| Rows are skipped | Unstable cursor, new rows inserted behind cursor, or `SKIP LOCKED` without reconciliation | Use a unique key, dual-write/change capture, and a final reconciliation sweep. |
| Newer data overwritten | Backfill computed old values outside DB and updated without version checks | Compute from current source column or use optimistic version predicates. |
| Checkpoint ahead of data | Checkpoint updated in a separate transaction | Commit data updates and checkpoint in the same InnoDB transaction. |
| Job reprocesses completed rows | Non-durable checkpoint or non-idempotent batch | Persist cursor in DB and use safely repeatable update predicates. |
| Job marked DONE while NULLs remain | Cursor treated as sole completion check | Run reconciliation against actual data invariants. |
| Deadlocks or lock timeouts | Batches contend with live transactions or other workers | Roll back entire batch, backoff, shrink batch, and partition ranges. |
| Replica lag spikes | Backfill generates heavy row events and apply load | Throttle rate, reduce workers, monitor binlogs and replicas. |
| Workers overwrite checkpoints | Shared cursor without coordination | Create per-worker/range checkpoints or lock range claims. |
| Retries cause duplicate side effects | Retrying business actions involving external side effects | Use idempotency keys and transactional outbox for side effects. |

## 18. Practice exercises

### Exercise 1: Backfill a new column

Create `sales.orders` with at least 100,000 rows. Add `customer_name_normalized` and write a worker updating by `order_id` in batches of 500 rows. Compare duration against a single full-table `UPDATE` and observe lock waits, redo volume, and replica lag.

### Exercise 2: Stop and resume

Stop the worker after several committed batches. Restart the worker from the database checkpoint. Confirm no key ranges were skipped and completed batches were not mis-updated.

### Exercise 3: Simulate concurrent writes

During the backfill, use another session to update `customer_name`. Test two designs: updating only the old column versus dual-writing both columns. Observe which case leaves the normalized column stale and explain how reconciliation detects it.

### Exercise 4: Composite keys

Create a table with primary key `(tenant_id, order_id)`. Write keyset pagination across both columns, store the composite cursor, and iterate across multiple tenants. Confirm ordering neither duplicates nor skips rows.

### Exercise 5: Multiple workers and retries

Split the table into four non-overlapping ranges. Run independent workers, induce a deadlock or lock timeout in a test environment, and verify each worker rolls back, re-reads its checkpoint, and resumes the right range.

## 19. Checklist before concluding a backfill

- [ ] Table has a stable primary key or unique key for deterministic ordering.
- [ ] Cursor stores all key components when using composite keys.
- [ ] Batch queries use keyset pagination backed by a suitable index.
- [ ] High-water mark is recorded along with a plan for concurrent inserts.
- [ ] Application dual-writes or change capture is active prior to backfill.
- [ ] Update predicates are idempotent and never overwrite newer data.
- [ ] Checkpoints are persisted durably in the database.
- [ ] Data updates and checkpoint updates commit in the same transaction.
- [ ] Batch size, worker count, and retry policies are bounded.
- [ ] Pause/resume controls and error tracking are implemented.
- [ ] Lock waits, deadlocks, redo, binlogs, and replica lag are monitored.
- [ ] Reconciliation ran against the exact conversion rules.
- [ ] `DONE` is marked only after confirming data is genuinely complete.
- [ ] Dual-writes or legacy columns are removed only in a separate contract phase.

Reliable backfills rely on stable keys, repeatable batches, and checkpoints committed atomically alongside data. When the application writes concurrently during transition, dual-writes or change capture protect incoming changes, while reconciliation catches any missed rows. Start with small batches, measure impact on workload and replicas, scale speed carefully, and conclude the migration only after data is reconciled and the application has fully switched to the new schema.
