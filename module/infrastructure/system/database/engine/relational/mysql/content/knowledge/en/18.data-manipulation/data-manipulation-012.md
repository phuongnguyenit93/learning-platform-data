# Chunking by a Stable Key and Avoiding Oversized Transactions

A historical orders table can contain tens of millions of rows. When transitioning the status of old data, purging expired logs, or normalizing a column, running a single UPDATE/DELETE across the whole table can create an enormous transaction, hold locks for a long time, generate massive undo/redo logs, spike I/O load, and cause replicas to fall behind. If the process is interrupted mid-way, restarting also makes it difficult to determine which portion has already completed.

The common solution is to split the work into small batches along a stable key. Each batch processes a deterministic key range or set of IDs, commits independently, and saves a checkpoint so the next run can resume. This reduces lock hold times and limits the amount of work that must be retried. In exchange, the overall job is no longer a single atomic transaction; you must design idempotency, checkpoints, and reconciliation to handle failures between batches.

## 1. Why Should You Avoid Processing Millions of Rows in One Transaction?

In InnoDB, an oversized transaction causes significant strain:

- **Long-held locks:** other transactions must wait when they touch rows or index ranges currently locked.
- **Growing undo logs:** InnoDB retains old row versions for rollback and consistent reads; long-running transactions can prevent purge from cleaning up old history.
- **Large redo and binary logs:** generates heavy I/O, increases log volume, and adds replication work.
- **Costly rollbacks:** if an error occurs near the end of the transaction, the server may have to undo an enormous volume of changes.
- **Higher deadlock and lock-wait probability:** multiple threads updating data across broad ranges contend easily.
- **Harder progress recovery:** if a client disconnects or a job stops, you must re-determine what has already committed.
- **Operational side effects:** replica lag, buffer pool churn, backup durations, and maintenance windows can all increase.

For example, the following statement might update the entire order history:

    UPDATE orders
    SET archived = 1
    WHERE created_at < '2024-01-01';

If the predicate matches millions of rows, the statement can run for a long time and hold a massive transaction. Batching bounds the row count per commit:

    UPDATE orders
    SET archived = 1
    WHERE created_at < '2024-01-01'
    ORDER BY id
    LIMIT 1000;

This is a simple example of capping rows. To resume accurately across multiple runs, you need a stable cursor/checkpoint strategy. Simply repeating a LIMIT statement without recording progress can re-scan data, reprocess rows, or miss rows when the dataset changes.

## 2. What Is a Stable Key?

A key used for chunking should have these properties:

1. **Unique:** each row has a distinct key value, usually the primary key.
2. **Immutable:** the value does not change over the row's lifetime.
3. **Ordered:** can be sorted consistently to determine the next row.
4. **Indexed:** locating rows past the checkpoint does not require scanning the entire table again.
5. **Aligned with the job scope:** the key pairs cleanly with business predicates to target the right dataset.

An auto-incrementing numeric primary key such as `id` is usually the most convenient choice. If the table uses a composite key, you can use a unique key tuple such as `(tenant_id, event_id)` or `(created_at, id)`. Ensure the comparison order and continuation predicate include all components so rows are neither duplicated nor skipped.

Do not use mutable columns such as `status`, `updated_at`, or display names as the primary cursor. If a cursor value changes while the job is running, a row can shift ahead of or behind the scanned position.

## 3. Keyset Pagination Instead of OFFSET

### 3.1. The Problem with OFFSET

OFFSET-style pagination:

    SELECT id
    FROM orders
    ORDER BY id
    LIMIT 1000 OFFSET 500000;

MySQL still must walk past all rows before the offset before returning the next slice. The larger the offset, the higher the cost of reading and discarding rows. When data is inserted or deleted concurrently, relative row positions shift, causing later pages to repeat or skip rows.

### 3.2. Using the Last Processed Key

Keyset pagination remembers the last key value from the previous batch:

    SELECT id
    FROM orders
    WHERE id > 500000
    ORDER BY id
    LIMIT 1000;

If the batch returns IDs from 500001 to 501000, the new checkpoint is 501000. The next batch starts with `id > 501000`. Comparing against an indexed key lets MySQL seek directly to the starting point instead of skipping hundreds of thousands of rows.

General pattern:

    SELECT id
    FROM orders
    WHERE id > :last_id
    ORDER BY id
    LIMIT :batch_size;

Notations such as `:last_id`, `:high_id`, and `:batch_size` in these examples are application-bound parameters, not native MySQL prepared statement named-placeholder syntax. With JDBC, use positional `?` placeholders; client libraries may support their own named parameter syntax.

After successful processing, set `last_id` to the highest ID processed in the batch. Never advance the checkpoint to an unprocessed ID or before the corresponding work has committed.

### 3.3. Why Is a Unique ORDER BY Required?

If you sort only by a non-unique column, multiple rows can share the same value across batch boundaries—for example, many orders with the same `created_at`. In that case, add a unique key as a tie-breaker:

    SELECT id, created_at
    FROM orders
    WHERE created_at > :last_created_at
       OR (created_at = :last_created_at AND id > :last_id)
    ORDER BY created_at, id
    LIMIT 1000;

The cursor is the pair `(last_created_at, last_id)`. The continuation predicate must match the sort order: compare timestamp first, then ID when timestamps match. A suitable index is typically:

    CREATE INDEX idx_orders_created_id
    ON orders (created_at, id);

If `created_at` can change, it is not a stable cursor. Prefer an immutable primary key; use a composite key only when every component is guaranteed not to change while the job runs.

## 4. Chunking by Key Ranges

A common technique is to take `last_id`, select the next batch of IDs, and process the range from the previous ID up to the batch's ending ID.

### 4.1. Determining a High-Water Mark

At job start, you can capture the current maximum key:

    SELECT COALESCE(MAX(id), 0) AS high_id
    FROM orders;

Keep `high_id` as the upper bound for the run. Subsequent batch queries consider only `id <= high_id`:

    SELECT id
    FROM orders
    WHERE id > :last_id
      AND id <= :high_id
    ORDER BY id
    LIMIT 1000;

A high-water mark bounds the scope and prevents newly inserted rows with larger IDs from extending the job indefinitely. However, it is not a complete membership snapshot. Another transaction may have allocated an AUTO_INCREMENT ID smaller than `high_id` before committing while the job read the high-water mark, and then commit after the cursor has already passed that ID. Therefore, if late-appearing rows must not be missed, combine this with a fixed worklist, controlled write windows, or a post-job reconciliation pass.

### 4.2. Finding the Batch Boundary

Example picking up to 1000 eligible IDs:

    SELECT MAX(batch_ids.id) AS chunk_end
    FROM (
        SELECT id
        FROM orders
        WHERE id > :last_id
          AND id <= :high_id
          AND created_at < '2024-01-01'
        ORDER BY id
        LIMIT 1000
    ) AS batch_ids;

If `chunk_end` is not NULL, process the rows in that range:

    UPDATE orders
    SET archived = 1
    WHERE id > :last_id
      AND id <= :chunk_end
      AND created_at < '2024-01-01'
      AND archived = 0;

Because `chunk_end` is the final ID of the first 1000 eligible rows, this key range contains at most 1000 eligible rows as of batch selection. IDs may have gaps; that does not affect cursor correctness.

If concurrent updates alter eligibility between selection and UPDATE, the actual updated row count can be smaller. For operations that must process the exact selected set of IDs, store the batch's ID list in a temporary/work table or lock the target rows in the same transaction.

### 4.3. Do Not Use Global MAX(id) as the New Checkpoint

Global `MAX(id)` is the initial high-water mark, not the last processed ID. If a batch processes only 1000 rows while the checkpoint jumps to `MAX(id)`, all rows in between are skipped. The checkpoint must be the final key of the completed batch, or a range boundary that the job has completely scanned.

## 5. Batched Data Update Example

Suppose old orders must transition to ARCHIVED status. The table has primary key `id` and a suitable index for filtering.

    CREATE INDEX idx_orders_archive_scan
    ON orders (archived, id);

Select a batch of IDs:

    SELECT id
    FROM orders
    WHERE archived = 0
      AND id > :last_id
      AND id <= :high_id
      AND created_at < '2024-01-01'
    ORDER BY id
    LIMIT 1000;

The application records the batch's last ID as `chunk_end`, then updates:

    UPDATE orders
    SET archived = 1
    WHERE id > :last_id
      AND id <= :chunk_end
      AND archived = 0
      AND created_at < '2024-01-01';

Finally, commit and save the checkpoint. An index on `(archived, id)` helps filter `archived` and walk in ID order; however, because `created_at` is not in the index, MySQL must inspect rows further. If the table is very large, evaluate indexes for the actual workload, such as `(archived, created_at, id)` or `(created_at, id)`. The best index depends on selectivity and query order; do not create all variants mechanically.

### 5.1. When You Need to Process the Exact Selected ID List

For complex operations with joins or mutable conditions, store IDs in a temporary table within the same session:

    CREATE TEMPORARY TABLE batch_order_ids (
        id BIGINT UNSIGNED NOT NULL PRIMARY KEY
    ) ENGINE=MEMORY;

    INSERT INTO batch_order_ids (id)
    SELECT id
    FROM orders
    WHERE id > :last_id
      AND id <= :high_id
      AND archived = 0
      AND created_at < '2024-01-01'
    ORDER BY id
    LIMIT 1000;

    UPDATE orders AS o
    JOIN batch_order_ids AS b ON b.id = o.id
    SET o.archived = 1
    WHERE o.archived = 0;

A temporary table freezes the batch's ID set. For large batches or progress that must survive reconnects, use an InnoDB work table instead of a temporary table. Temporary tables vanish when the session ends; MEMORY tables also have RAM limits and are not suited for all sizes.

## 6. Batching DELETE by a Stable Key

Purging old data should also follow an ordered key:

    DELETE FROM audit_events
    WHERE id > :last_id
      AND id <= :chunk_end
      AND created_at < '2023-01-01';

If you simply repeat `DELETE ... LIMIT 1000`, MySQL can delete chunks, but the application must ensure deterministic ordering and detect completion. The keyset pattern keeps progress observable and resumable after errors.

You can use:

    DELETE FROM audit_events
    WHERE created_at < '2023-01-01'
    ORDER BY id
    LIMIT 1000;

for simple chunked deletions. However, if precise resume is needed, fetch the ID list or range boundary, delete that batch, commit, and record the checkpoint. Never use OFFSET on a dataset being deleted because row positions shift after every batch and rows will be skipped.

### 6.1. Handling Foreign Keys and Child Tables

If parent rows are referenced by child tables, DELETE can be blocked by RESTRICT or cascade across ON DELETE CASCADE. One batch of 1000 parents can trigger thousands or millions of child row deletions. Account for cascade volume, not just the parent table row count.

For large relationships, delete children by foreign key first and then delete parents, with separate checkpoints per phase. If relying on cascades, benchmark affected row counts and execution time on a copy of the data. Never disable `foreign_key_checks` just to force DELETEs through.

## 7. Checkpoints to Resume After Job Interruption

A long-running job needs to persist progress outside the application loop. Example:

    CREATE TABLE batch_job_progress (
        job_name VARCHAR(100) NOT NULL,
        last_id BIGINT UNSIGNED NOT NULL DEFAULT 0,
        high_id BIGINT UNSIGNED NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
        updated_at TIMESTAMP NOT NULL
            DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (job_name)
    ) ENGINE=InnoDB;

Each job has one checkpoint row. `last_id` is the last key successfully processed; `high_id` is the upper bound captured at start; `status` shows whether the job is running or finished.

### 7.1. Updating Data and Checkpoint in the Same Transaction

When both the data table and the checkpoint table reside in MySQL/InnoDB, update both inside the same transaction:

    START TRANSACTION;

    UPDATE orders
    SET archived = 1
    WHERE id > :last_id
      AND id <= :chunk_end
      AND archived = 0
      AND created_at < '2024-01-01';

    UPDATE batch_job_progress
    SET last_id = :chunk_end
    WHERE job_name = 'archive-old-orders';

    COMMIT;

If the transaction rolls back, both the data changes and the checkpoint roll back together. If the commit succeeds yet the client disconnects before receiving the response, the next run reads the committed checkpoint and continues past `chunk_end`.

The `WHERE job_name` condition must match exactly one row. The application should check how many checkpoint rows were updated and handle cases where the job has not been initialized or was claimed by another worker.

### 7.2. Locking the Checkpoint Row to Prevent Concurrent Workers

If two processes might start the same job, read the checkpoint with `FOR UPDATE` inside a transaction:

    START TRANSACTION;

    SELECT last_id, high_id, status
    FROM batch_job_progress
    WHERE job_name = 'archive-old-orders'
    FOR UPDATE;

    -- Select and process a batch, update last_id.

    COMMIT;

Locking the progress row serializes workers for the same job if all workers follow this protocol. If batch selection and DML occur outside the transaction or workers do not lock the same coordination row, two workers can still pick overlapping ranges.

For long-running jobs, never hold a single transaction open across all batches. Each batch starts a fresh transaction, locks the checkpoint, processes the batch, updates the checkpoint, and commits.

### 7.3. External Checkpoints

If the checkpoint lives in Redis, a file, or an external orchestrator, it cannot commit atomically with the MySQL transaction. The safe sequence is usually:

1. Commit the batch in MySQL.
2. Write the external checkpoint after commit succeeds.

If the process crashes between the two steps, the batch may run again. Thus the operation must be idempotent or backed by a ledger/unique key to recognize already-completed work. Writing the external checkpoint before commit risks marking progress before data commits, causing permanent skips.

## 8. Idempotency and Batch Retries

Batch jobs can encounter deadlocks, lock wait timeouts, dropped connections, or transient errors. Retries are essential, yet safe only if re-running the same batch causes no incorrect side effects.

Example setting a fixed target state:

    UPDATE orders
    SET archived = 1
    WHERE id > :last_id
      AND id <= :chunk_end
      AND archived = 0;

Re-running normally changes nothing further because rows already having `archived = 1` no longer satisfy the condition. This is nearly idempotent by target state.

By contrast:

    UPDATE account_balances
    SET balance = balance - 100
    WHERE id IN (...);

if retried after commit when the client missed the response, balances can be deducted twice. For additive/subtractive operations, payment generation, or notifications, you need idempotency keys, event ledgers, or verification before retrying.

### 8.1. Deadlocks and Lock Wait Timeouts

If a batch hits a deadlock, InnoDB chooses a victim transaction and rolls it back. The application should retry the entire batch transaction after a jittered backoff, up to a bounded retry count. Do not re-run only the final UPDATE statement if the transaction included multiple coordinated steps.

For a lock wait timeout, by default only the failing statement may roll back depending on `innodb_rollback_on_timeout`; the application should explicitly roll back the entire transaction before retrying to restore the connection to a clean state.

Never retry infinitely. Log the batch key range, attempt count, error, wait time, and final outcome.

## 9. Concurrent Data Changes During Batching

A stable key establishes ordering, but it does not freeze the dataset on its own.

### 9.1. New Rows Inserted After the Job Starts

If new IDs always exceed `high_id`, the `id <= high_id` bound excludes them from the current run. They can be processed in a later run.

However, AUTO_INCREMENT IDs can be allocated before a transaction commits. A transaction holding an ID below the high-water mark may commit late after the cursor has already passed that ID. Hence, a high-water mark is no substitute for a snapshot or a fixed worklist.

### 9.2. Mutable Filter Conditions

Suppose a job selects `status = 'PENDING'`. A row with an ID smaller than `last_id` is currently `DONE`, and another thread later changes it to `PENDING`. The cursor will not revisit that ID during the current pass. If every row matching the criteria at a defined point in time must be processed, capture membership via a snapshot/worklist or temporarily control writers.

### 9.3. Membership Control Strategies

- **Fixed worklist:** build the list of target IDs at start time, then chunk the worklist into batches. A staging table with `job_id`, `target_id`, and `status` can hold it.
- **Immutable data window:** select using an agreed cutoff and ensure the application does not mutate membership-determining attributes inside that window.
- **Pause writers / cutover:** fits migrations requiring an exact dataset when a maintenance window is acceptable.
- **Reconciliation pass:** after the main pass, re-scan processed ranges to catch late-arriving or newly eligible rows.
- **Queue / claim model:** workers claim individual rows or groups via status/lease, with timeouts and recovery for abandoned claims.

Choose the strategy based on consistency requirements. An archival job may accept a reconciliation pass; a primary-key migration or financial data conversion may require a strict worklist and reconciliation.

## 10. Worklists and Staging Tables

When you need to know the exact rows belonging to a job, create a worklist:

    CREATE TABLE batch_job_items (
        job_name VARCHAR(100) NOT NULL,
        target_id BIGINT UNSIGNED NOT NULL,
        item_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
        processed_at DATETIME NULL,
        PRIMARY KEY (job_name, target_id),
        KEY idx_job_status_id (job_name, item_status, target_id)
    ) ENGINE=InnoDB;

Load the initial ID set:

    INSERT INTO batch_job_items (job_name, target_id)
    SELECT
        'archive-old-orders',
        id
    FROM orders
    WHERE created_at < '2024-01-01'
      AND archived = 0;

Then pick a batch:

    SELECT target_id
    FROM batch_job_items
    WHERE job_name = 'archive-old-orders'
      AND item_status = 'PENDING'
    ORDER BY target_id
    LIMIT 1000;

The application fetches the ID list, updates the target data, and marks the items processed in the same transaction:

    START TRANSACTION;

    UPDATE orders
    SET archived = 1
    WHERE id IN (/* batch IDs */)
      AND archived = 0;

    UPDATE batch_job_items
    SET item_status = 'DONE',
        processed_at = CURRENT_TIMESTAMP
    WHERE job_name = 'archive-old-orders'
      AND target_id IN (/* same IDs */)
      AND item_status = 'PENDING';

    COMMIT;

A worklist enables resuming by item status rather than a single cursor. It adds storage and I/O overhead, yet is valuable when membership is complex, IDs are sparse, or multiple workers process in parallel. Items must be locked/claimed so two workers do not grab the same batch; `SELECT ... FOR UPDATE SKIP LOCKED` on MySQL 8.0 can help, provided claim state and leases are designed to recover from crashed workers.

`SKIP LOCKED` skips currently locked rows, so never advance a global cursor past skipped rows and declare the job finished. With a worklist, mark items `DONE` only when the batch actually processes them; skipped rows remain pending for another worker.

## 11. Small Transactions Still Need Consistent Lock Ordering

Batching shrinks the lock scope per transaction, but it does not eliminate deadlocks. If a transaction updates multiple tables or multiple rows, access them in the same order across all workers.

For example, if worker A updates `orders` then `order_items`, while worker B updates `order_items` then `orders`, the two transactions can hold crossing locks. Standardizing access order and keeping transactions short reduces risk.

When batching by ID, processing in ascending primary key order usually creates a stable access order:

    START TRANSACTION;

    SELECT id
    FROM orders
    WHERE id > :last_id
    ORDER BY id
    LIMIT 500
    FOR UPDATE;

After acquiring locks, perform the DML and `COMMIT` within the same transaction. Locking reads hold locks only during the transaction; if autocommit is enabled and no explicit transaction is open, locks may release as soon as the SELECT finishes. Account for isolation level, indexes, and InnoDB range locking; a locking read can lock extra index ranges depending on the plan and isolation level.

## 12. Choosing Batch Size

There is no single universal optimal batch size. Influencing factors include:

- Row size and number of indexes to update.
- Number of rows affected by triggers or foreign key cascades.
- Lock hold duration and commit time.
- IOPS, CPU, buffer pool, and concurrent OLTP traffic.
- Binary log volume and replica apply speed.
- Packet size if sending ID lists or multi-row statements.
- Deadlock rate, lock wait timeouts, and retry counts.

Start with a small batch, measure, and scale up gradually. Tune toward a target execution duration—for example, keeping each batch within a few hundred milliseconds to a few seconds depending on the system. If batches consistently take many seconds, lock waits climb, or replica lag grows, reduce batch size or add pauses between batches.

### 12.1. Adaptive Throttling

A job can adjust batch size or sleep between batches based on metrics:

- Average duration of recent batches.
- Lock waits and deadlocks.
- Server CPU and I/O.
- Replication lag.
- Business request load.

Example logic:

    if (replicaLag > lagThreshold || lockWaits > waitThreshold) {
        batchSize = max(minBatchSize, batchSize / 2);
        pauseBetweenBatches();
    } else if (batchDuration < targetDuration) {
        batchSize = min(maxBatchSize, batchSize + step);
    }

This is application control pseudocode, not SQL syntax. Enforce min/max bounds and avoid adjusting too aggressively to prevent oscillation.

## 13. Monitoring Progress and Verifying Results

A well-operated batch job should record:

| Metric | Purpose |
|---|---|
| Job name and run ID | Distinguish runs |
| Last key / high key | Track processed range |
| Batch size and affected rows | Detect empty or anomalous batches |
| Batch duration | Measure throughput and tune pacing |
| Retry / deadlock count | Detect contention |
| Error code and message | Diagnose failures |
| Replica lag | Monitor replication impact |
| Started / finished time | Estimate progress and remaining time |
| Reconciliation count | Catch late-arriving or missed rows |

After the job finishes, reconcile row counts using the same business predicate:

    SELECT COUNT(*) AS remaining_rows
    FROM orders
    WHERE archived = 0
      AND created_at < '2024-01-01';

If the result is expected to be 0, investigate every remaining row before declaring the job successful. You can verify by range, compare checksums, or reconcile source and target totals. Never rely solely on the final checkpoint: a checkpoint proves the cursor traversed a range, not that every row in that range reached the intended state in the presence of logic bugs or concurrent mutations.

## 14. Using EXPLAIN to Inspect Batch Queries

Keyset conditions require proper indexes. Inspect the ID selection query:

    EXPLAIN
    SELECT id
    FROM orders
    WHERE archived = 0
      AND id > 500000
      AND id <= 900000
      AND created_at < '2024-01-01'
    ORDER BY id
    LIMIT 1000;

Check:

- `key`: chosen index.
- `type`: access type, such as `range`, `ref`, or `ALL`.
- `rows`: estimated rows read.
- `filtered`: percentage of rows remaining after filtering.
- `Extra`: details on filtering, sorting, or covering indexes.

If the optimizer must scan too many rows because filter predicates lack an appropriate index, the batch will still be slow even though it updates only 1000 rows. Sometimes the ID-selection SELECT is the most expensive part of the job.

Do not add an index for a one-off run without weighing storage and write costs. Building a new index on a large table also takes time and can cause load or metadata locks; plan separately if needed.

## 15. Pitfalls to Avoid

- Do not run one giant transaction just to simplify code.
- Do not use large OFFSETs on a changing dataset.
- Do not use a mutable column as the cursor.
- Do not advance the checkpoint before batch data commits.
- Do not write an external checkpoint before committing data.
- Do not assume `MAX(id)` is a complete snapshot of all in-flight transactions.
- Do not retry additive/subtractive operations or event emissions without idempotency.
- Do not use `SKIP LOCKED` and permanently skip locked rows.
- Do not delete parent rows while ignoring child tables or cascades.
- Do not increase batch size while replica lag or lock waits are rising.
- Do not treat `affected_rows = 0` as always an error; rows may have already been processed or stopped matching the predicate.
- Do not treat a completed checkpoint as a substitute for reconciliation.

## 16. Batch Job Implementation Procedure

1. **Define the dataset:** business predicate, unique key, mutability, and handling of late-arriving rows.
2. **Choose the cursor:** prefer an immutable primary key; for composite keys, define exact sort order and continuation predicates.
3. **Establish a high-water mark or worklist:** choose based on membership guarantees and write concurrency.
4. **Create checkpoints:** store last key, upper bound, job status, and run ID.
5. **Choose initial batch size:** benchmark on staging or a representative copy of data.
6. **Execute per-batch transactions:** select batch, execute DML, update checkpoint in the same transaction, and commit.
7. **Apply bounded retries:** roll back the full transaction on error, back off, and retry only idempotent operations.
8. **Throttle by load:** monitor batch duration, lock waits, deadlocks, and replication lag.
9. **Resume after interruption:** read the committed checkpoint, verify job/run ownership, and continue.
10. **Reconcile:** re-scan remaining eligible rows, handle late arrivals, and verify totals.
11. **Close the job:** set status to `COMPLETED` only when business checks and reconciliation pass.

## 17. Safe Chunking Checklist

- Is the cursor key unique, immutable, ordered, and indexed?
- Does `ORDER BY` include a unique tie-breaker?
- Does the continuation predicate match the cursor sort order?
- Are large OFFSETs avoided?
- Is the high-water mark clearly distinguished from a snapshot?
- Could uncommitted transactions appear late with keys smaller than the cursor?
- Can eligibility predicates change while the job runs?
- Is a fixed worklist or reconciliation pass required?
- Do batch DML and checkpoint updates commit atomically together?
- If the checkpoint is external to the database, is the operation idempotent for retries?
- Could two workers process the same job/range concurrently? Is a lock/claim mechanism in place?
- Does the batch size bound lock hold duration and cascade impact?
- Are deadlocks, lock waits, undo/redo, binlog, and replica lag monitored?
- Are retry, resume, and failed-row handling planned separately?
- Has remaining eligible data been reconciled after the job finishes?

## Conclusion

Chunking by a stable key enables large data update or deletion jobs to recover after errors, bound lock hold durations, and keep each transaction small. Prefer keyset pagination on an immutable primary key, advance checkpoints only after batch commit, and update data and checkpoints in the same transaction whenever possible. A high-water mark does not create a snapshot on its own; late-committing rows or changing filter conditions can still be missed, so pair it with a worklist, writer controls, or reconciliation as required. Combining right-sized batches, idempotent retries, replication monitoring, and post-job reconciliation lets you run large data modifications safely.
