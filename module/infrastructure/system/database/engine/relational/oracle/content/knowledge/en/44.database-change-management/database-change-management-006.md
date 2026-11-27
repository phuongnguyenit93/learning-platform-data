# Batched Data Backfilling, Controlling Redo/Undo, and Resumability

Backfilling is the process of populating or transforming existing data after a schema or application logic change. For example, a system adds a `NORMALIZED_EMAIL` column to store normalized email addresses, adds `CUSTOMER_TIER` computed from historical data, or migrates a column to a new format. On large tables, running a single `UPDATE` statement can create a very long transaction, hold row locks for an extended duration, consume massive undo, generate huge redo volume, and put pressure on archive logs or Data Guard.

The standard solution is splitting work into small batches (chunks), committing at controlled boundaries, saving checkpoints, and designing operations to be safely re-runnable. The goal is not merely finishing the backfill quickly, but knowing exactly how far processing has reached, being able to resume after failures, avoiding overwriting fresh data, and preventing degradation of user-facing systems beyond acceptable thresholds.

## 1. Backfilling Within a Schema Change

### 1.1. What Is a Backfill?

Backfilling updates existing records to satisfy a new structure or data rule. Common scenarios include:

- Adding a new column and computing values for historical data.
- Normalizing data such as emails, area codes, statuses, or units of measure.
- Migrating data from an old column to a new column.
- Populating a new foreign key or reference code.
- Assigning default values based on new business rules.
- Moving data into target partitions or tables during upgrades.
- Generating derived data for search, reporting, or classification.

Backfilling differs from DDL migrations. DDL changes structure, such as `ALTER TABLE ADD COLUMN`; backfilling modifies row-by-row data. Both parts usually need coordination within an expand-and-contract plan so old and new application versions can coexist during the transition period.

### 1.2. The Expand-and-Contract Model

A safe online rollout typically consists of:

1. **Expand:** add new columns/tables in a compatible state, usually allowing `NULL` initially.
2. **Compatible deploy:** new application code starts writing both old and new columns, or reading the new column with fallback to the old column.
3. **Backfill:** populate legacy data in batches while the application continues operating.
4. **Validate:** verify row counts, values, and business rules.
5. **Switch:** switch the application to use the new column as its primary source.
6. **Contract:** once the compatibility period ends, remove legacy read/write paths and drop old columns in a separate migration.

Never add a new column, backfill, drop the old column, and deploy dependent code in one uninterrupted change with no verification gates. Separating steps enables progressive rollout, catching issues, and rolling back before legacy data is removed.

### 1.3. Business Example

Suppose the `CUSTOMERS` table currently has `EMAIL`, and we need to add `EMAIL_NORMALIZED` for case-insensitive search:

```sql
ALTER TABLE app.customers ADD (
    email_normalized VARCHAR2(320 CHAR)
);
```

The new application will write `EMAIL` and `EMAIL_NORMALIZED` simultaneously. Legacy rows need to be backfilled:

```sql
UPDATE app.customers
SET email_normalized = LOWER(TRIM(email))
WHERE email_normalized IS NULL;
```

The simple statement above may work for small tables. For tables with millions or hundreds of millions of rows, running it in one shot can produce an enormous, long-running transaction. This lesson focuses on chunking the work, controlling resources, and ensuring resumability after interruptions.

## 2. Designing Scope and Safety Conditions

### 2.1. Defining the Dataset to Backfill

Before executing, identify:

- Target tables, partitions, and columns.
- Expected row count and key distribution.
- Transformation expressions and `NULL`/invalid-value edge cases.
- Primary key or `ROWID` used for chunking.
- How to recognize that a row is already complete.
- How to handle rows updated by the application during the backfill.
- Dependent triggers, indexes, constraints, audits, materialized view logs, or CDC streams.
- Allowed load windows and redo/undo/lag limits.

Perform a preliminary count of rows to process:

```sql
SELECT COUNT(*) AS rows_to_backfill
FROM app.customers
WHERE email_normalized IS NULL;
```

If the table is huge, even `COUNT(*)` can consume significant I/O. You can use statistics for an initial estimate while explicitly noting it is an estimate; for exact planning, use a measurement method suited to the table and workload.

### 2.2. Completion Conditions Must Be Unambiguous

Do not use `target_column IS NULL` as the sole completion indicator if `NULL` is a valid transformation output. For instance, if `PHONE_NORMALIZED` can be `NULL` because the source phone number is absent, the backfill cannot distinguish processed rows from unprocessed rows.

You can use one of these approaches:

- A status flag column such as `BACKFILL_DONE = 'Y'`.
- A checkpoint table storing completed key ranges.
- A work queue table holding row keys and per-row status.
- A version/migration marker attached to each record.
- A rule verifying the new result has been populated and validated.

Choose an option fitting your schema change constraints, write amplification overhead, and traceability needs. Do not add a marker column purely for convenience if it substantially increases cost on every production transaction with no plan to remove it.

### 2.3. Never Overwrite Fresh Application Updates

When a backfill runs concurrently with the application, both may update the same row. Suppose the backfill reads an old email value, computes the normalized email, and writes to the new column. Meanwhile, the user changes their email and the application writes the new value. If the backfill writes using the value it read earlier, it could overwrite the newer result.

Mitigation techniques:

- Compute the value from the source column directly inside the `UPDATE` statement rather than reading first and writing stale data later.
- Use `WHERE target_column IS NULL` or an incomplete marker to avoid overwriting application-written values.
- If staging through external code, include `ROW_VERSION`/`UPDATED_AT` and update only when the source version still matches.
- Deploy dual-writes before backfilling so all new writes keep both columns updated.
- Perform a final catch-up pass or reconciliation before switching reads to the new column.

Conditional update example:

```sql
UPDATE app.customers
SET email_normalized = LOWER(TRIM(email))
WHERE customer_id > :low_id
  AND customer_id <= :high_id
  AND email_normalized IS NULL;
```

The final predicate preserves values already written by the application. This holds only when `NULL` means unprocessed; if `NULL` is a valid output, use a dedicated marker.

## 3. Splitting Work into Batches/Chunks

### 3.1. Why Not UPDATE the Entire Table at Once?

A single transaction updating millions of rows can:

- Hold row locks across massive row sets for a long time.
- Generate huge undo to support rollback and consistent reads.
- Generate huge redo and rapidly fill archive logs.
- Prolong rollback time if the job fails near completion.
- Increase contention with application transactions.
- Expose other long-running queries to undo pressure and `ORA-01555` errors.
- Cause sustained I/O, CPU, and buffer cache pressure.
- Force Data Guard or downstream replication to apply massive redo spikes.

Batching creates smaller transactions. Each batch commits independently; if a later batch fails, earlier batches remain completed and checkpoints allow resuming.

### 3.2. Choosing Batch Size

No single batch size fits every table. The right size depends on:

- Row width and number of updated columns.
- Number of indexes to maintain.
- Triggers, constraints, audits, and cascades.
- Contention level with the application.
- Redo/undo generation rate and archive/storage capacity.
- Commit latency and row lock duration.
- Allowed degree of parallelism.

Start by testing a few hundred or a few thousand rows per batch, then measure duration, redo, undo, locks, and application latency. For narrow rows with few indexes, batches can be larger; for wide rows, many indexes/LOBs, or hot tables, smaller batches are safer.

The goal is keeping each transaction's duration and resource consumption within controllable limits. Do not size batches purely by row count; 5,000 rows with multiple LOBs and indexes can be heavier than 50,000 small rows.

### 3.3. Chunking by Primary Key Range

If the table has a numeric or stably ordered primary key, split into ranges:

```text
Batch 1: customer_id > 0      AND customer_id <= 10000
Batch 2: customer_id > 10000  AND customer_id <= 20000
Batch 3: customer_id > 20000  AND customer_id <= 30000
...
```

Example SQL:

```sql
UPDATE app.customers
SET email_normalized = LOWER(TRIM(email))
WHERE customer_id > :low_id
  AND customer_id <= :high_id
  AND backfill_done = 'N';
```

Primary key ranges are easy to checkpoint and resume after failures. However, if keys are skewed or have large gaps, row counts per batch may vary unevenly. Measure row counts across ranges and rebalance if needed.

### 3.4. Chunking by ROWID

`ROWID` can split a table into physical regions and works conveniently for parallel processing. Oracle provides `DBMS_PARALLEL_EXECUTE` to create chunks by `ROWID`. Remember that `ROWID` is a row's physical address in a segment; it can change after row movement, table move/redefinition, or certain structural reorganizations. Never use `ROWID` as a long-term business identifier or as a checkpoint across operations that can alter `ROWID`.

`ROWID` works well when chunking for a single controlled run while no structural reorganization occurs. If long-lived checkpoints across multiple deployments are needed, primary keys or a durable work queue are easier to manage.

### 3.5. Chunking by Partition

For partitioned tables, backfill partition by partition or subpartition by subpartition:

- Start with older, colder partitions.
- Process partitions by month/quarter or date range.
- Measure load and validate each partition before moving to the next.
- Monitor both global indexes and local indexes throughout.

Partition pruning reduces read/write scope when predicates filter on the partition key. However, updating the partition key can move rows across partitions or require `ENABLE ROW MOVEMENT` depending on the case; evaluate carefully before running.

## 4. Checkpoints and Resumability

### 4.1. What Is a Checkpoint?

A checkpoint records committed work progress. If a process stops, an application restarts, or a database session disconnects, the worker reads the checkpoint and resumes from the unfinished portion.

A simple control table:

```sql
CREATE TABLE app.backfill_control (
    task_name       VARCHAR2(100) PRIMARY KEY,
    last_completed_id NUMBER,
    high_water_id   NUMBER,
    status          VARCHAR2(20) NOT NULL,
    updated_at      TIMESTAMP(6) WITH TIME ZONE NOT NULL
);
```

Example row:

```sql
INSERT INTO app.backfill_control (
    task_name, last_completed_id, high_water_id, status, updated_at
)
VALUES (
    'CUSTOMER_EMAIL_V1', 0, 9000000, 'RUNNING', SYSTIMESTAMP
);
COMMIT;
```

`high_water_id` bounds the dataset for the backfill run. New rows created after establishing the range must be handled by dual-writes, CDC, or a dedicated catch-up pass. Never assume every ID below the high-water mark is already committed and visible in the same snapshot if active transactions are still open.

### 4.2. Updating Data and Checkpoint in the Same Transaction

For sequential workers, a critical principle is updating batch data and checkpoint progress inside the same transaction:

```sql
UPDATE app.customers
SET email_normalized = LOWER(TRIM(email)),
    backfill_done = 'Y'
WHERE customer_id > :last_id
  AND customer_id <= :batch_end
  AND backfill_done = 'N';

UPDATE app.backfill_control
SET last_completed_id = :batch_end,
    updated_at = SYSTIMESTAMP
WHERE task_name = 'CUSTOMER_EMAIL_V1';

COMMIT;
```

If the transaction rolls back, both batch data and checkpoint roll back together. If it commits, both become durable together. Avoid committing data first and updating the checkpoint in a separate transaction; if the process dies between the two, state becomes ambiguous and the batch must be re-run.

When multiple workers run concurrently, a single `last_completed_id` cannot represent each worker's progress. Use a chunk/work queue table with per-chunk status, or use `DBMS_PARALLEL_EXECUTE` to track chunk states.

### 4.3. Determining the Next Batch

One way to select the upper bound for the next N keys in Oracle:

```sql
SELECT MAX(customer_id) AS batch_end
FROM (
    SELECT customer_id
    FROM app.customers
    WHERE customer_id > :last_id
      AND customer_id <= :high_water_id
    ORDER BY customer_id
)
WHERE ROWNUM <= :batch_size;
```

The resulting `batch_end` is the highest key among at most N subsequent keys. The worker then processes `(last_id, batch_end]`. When no rows remain, `batch_end` is `NULL` and the range is complete.

The query requires a supporting index on the chunking key. On very large tables, avoid incrementing `OFFSET` because the database must skip progressively more rows. Keyset ranges or chunk metadata scale much better.

### 4.4. Idempotency: Re-Running Without Corrupting Data

An idempotent backfill can re-run over the same dataset without producing wrong results. Example:

```sql
UPDATE app.customers
SET email_normalized = LOWER(TRIM(email))
WHERE customer_id > :low_id
  AND customer_id <= :high_id
  AND backfill_done = 'N';
```

Once `backfill_done` is `'Y'`, re-running the range skips already-processed rows. However, idempotency is more than adding `IS NULL` or a marker. Check:

- Is the transformation expression deterministic, yielding the same output for the same input?
- Could the input have changed since the previous run?
- Are triggers or side effects re-fired?
- Are sequences incremented or messages/emails sent inside the transaction?
- Can a batch commit partially?
- Could retries create duplicate records in auxiliary tables?

If backfilling writes into another table, use unique keys/MERGE or event IDs to prevent duplicate inserts. If calling external services, use an outbox/idempotency key and never assume Oracle rollback undoes external side effects.

### 4.5. Per-Chunk Checkpoints Instead of a Single Pointer

For parallel execution, a chunk table can store:

| Column | Purpose |
|---|---|
| `TASK_NAME` | Migration run identifier. |
| `CHUNK_ID` | Chunk identifier. |
| `LOW_KEY`, `HIGH_KEY` | Key boundaries for the chunk. |
| `STATUS` | `PENDING`, `RUNNING`, `DONE`, or `FAILED` per application convention. |
| `ATTEMPT_COUNT` | Retry count. |
| `STARTED_AT`, `COMPLETED_AT` | Execution timestamps. |
| `ROWS_UPDATED` | Number of rows updated. |
| `ERROR_CODE`, `ERROR_MESSAGE` | Error details stripped of sensitive data. |

Workers claim a chunk, process it, and mark it complete. If a worker dies, leases or timeouts allow the chunk to be reclaimed. Prevent two workers from processing the same chunk simultaneously if operations are not idempotent.

## 5. Batched PL/SQL Backfill Examples

### 5.1. Sequential Worker Pattern

The example below assumes:

- `CUSTOMER_ID` is a unique, stable key.
- `BACKFILL_DONE = 'N'` denotes unprocessed rows.
- The new application already populates `EMAIL_NORMALIZED` and sets the marker on new rows.
- `HIGH_WATER_ID` was recorded prior to execution.

```sql
DECLARE
    l_last_id       NUMBER;
    l_high_water_id NUMBER;
    l_batch_end     NUMBER;
    l_batch_size    PLS_INTEGER := 2000;
    l_rows          PLS_INTEGER;
BEGIN
    SELECT last_completed_id, high_water_id
    INTO l_last_id, l_high_water_id
    FROM app.backfill_control
    WHERE task_name = 'CUSTOMER_EMAIL_V1'
    FOR UPDATE;

    LOOP
        SELECT MAX(customer_id)
        INTO l_batch_end
        FROM (
            SELECT customer_id
            FROM app.customers
            WHERE customer_id > l_last_id
              AND customer_id <= l_high_water_id
            ORDER BY customer_id
        )
        WHERE ROWNUM <= l_batch_size;

        EXIT WHEN l_batch_end IS NULL;

        UPDATE app.customers
        SET email_normalized = LOWER(TRIM(email)),
            backfill_done = 'Y'
        WHERE customer_id > l_last_id
          AND customer_id <= l_batch_end
          AND backfill_done = 'N';

        l_rows := SQL%ROWCOUNT;

        UPDATE app.backfill_control
        SET last_completed_id = l_batch_end,
            updated_at = SYSTIMESTAMP
        WHERE task_name = 'CUSTOMER_EMAIL_V1';

        COMMIT;

        DBMS_OUTPUT.PUT_LINE(
            'Completed through customer_id=' || l_batch_end ||
            ', rows updated=' || l_rows
        );

        l_last_id := l_batch_end;
    END LOOP;

    UPDATE app.backfill_control
    SET status = 'DONE', updated_at = SYSTIMESTAMP
    WHERE task_name = 'CUSTOMER_EMAIL_V1';
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
```

This skeleton illustrates transaction/checkpoint pairing; adapt column names, data types, batch size, logging, and task claiming to your real system. `FOR UPDATE` holds a lock on the control row across the loop, so this pattern fits a single controller worker. For multiple workers, do not share a single checkpoint row this way.

### 5.2. Limitations of High-Water Marks

`HIGH_WATER_ID` bounds the target key range of a backfill, but does not automatically create a consistent snapshot. If a transaction obtained an ID below the high-water mark yet committed only after the worker passed that range, the row could be missed. Oracle sequences do not guarantee commit order matches ID order.

To avoid missed rows:

- Establish a baseline using an appropriate snapshot/SCN when a consistent dataset is required.
- Or coordinate a brief write freeze when capturing the high-water mark and draining open transactions.
- Or use CDC/change logs to capture changes occurring during backfill.
- Run a final catch-up/reconciliation pass before switching the application to the new data.

If the backfill only populates a derived column and the application dual-writes all new changes, verify dual-write is deployed across every writer: APIs, batch jobs, integrations, triggers, and admin tools. One missed writer can leave unbackfilled rows after the job completes.

## 6. Using DBMS_PARALLEL_EXECUTE

### 6.1. When Should You Use It?

Oracle provides `DBMS_PARALLEL_EXECUTE` to split a DML task into multiple chunks and execute them via Scheduler workers. The package supports chunking by `ROWID` or numeric column ranges, tracking status, and resuming failed chunks.

It fits well when:

- The table is large enough to benefit from multiple workers.
- Ranges can be split independently.
- The DML statement is safe to run per chunk.
- The DBA has the required privileges and Scheduler resources.
- Parallelism can be capped to avoid overloading the system.

Do not spin up many workers just to finish faster if the table is hot, storage is saturated, or redo/archive is already a bottleneck. Parallelization can sharply raise aggregate load and slow down production applications.

### 6.2. Creating Tasks and Chunking by ROWID

Illustrative example creating a task, chunking `APP.CUSTOMERS`, and running the update:

```sql
BEGIN
    DBMS_PARALLEL_EXECUTE.CREATE_TASK(
        task_name => 'CUSTOMER_EMAIL_BACKFILL'
    );

    DBMS_PARALLEL_EXECUTE.CREATE_CHUNKS_BY_ROWID(
        task_name   => 'CUSTOMER_EMAIL_BACKFILL',
        table_owner => 'APP',
        table_name  => 'CUSTOMERS',
        by_row      => TRUE,
        chunk_size  => 5000
    );

    DBMS_PARALLEL_EXECUTE.RUN_TASK(
        task_name      => 'CUSTOMER_EMAIL_BACKFILL',
        sql_stmt       => q'[
            UPDATE app.customers
            SET email_normalized = LOWER(TRIM(email)),
                backfill_done = 'Y'
            WHERE ROWID BETWEEN :start_id AND :end_id
              AND backfill_done = 'N'
        ]',
        language_flag  => DBMS_SQL.NATIVE,
        parallel_level => 4
    );
END;
/
```

`by_row => TRUE` requests chunks sized approximately by row count; `chunk_size` sets the target rows per chunk. `parallel_level` caps concurrent workers per configuration. This example uses `ROWID` for a one-off backfill; if the table might be moved/reorganized while the task runs, halt structural changes or pick a more stable chunking strategy.

`DBMS_PARALLEL_EXECUTE` manages chunk progress and commits chunk by chunk during execution. Therefore, some chunks may commit while others fail. Keep the SQL idempotent and restricted to incomplete rows so resuming is safe.

### 6.3. Chunking by Numeric Column

If the table has a stable numeric key and you want key-range chunking, the package supports `CREATE_CHUNKS_BY_NUMBER_COL`. This ties more naturally to business checkpoints and avoids `ROWID` dependence. Pick a well-distributed column, typically the primary key or an indexed unique numeric column.

Before use, confirm package signatures for your Oracle version and execute privileges. If keys have gaps or skew, row counts per range can vary; choose chunk size/range based on real data.

### 6.4. Monitoring Chunks and Resuming

Inspect tasks and chunks via the corresponding views:

```sql
SELECT task_name, status, table_owner, table_name, chunk_type
FROM user_parallel_execute_tasks
WHERE task_name = 'CUSTOMER_EMAIL_BACKFILL';
```

```sql
SELECT status, COUNT(*) AS chunk_count
FROM user_parallel_execute_chunks
WHERE task_name = 'CUSTOMER_EMAIL_BACKFILL'
GROUP BY status
ORDER BY status;
```

If a task has failed chunks, inspect each chunk's status and error details, then fix the root cause before continuing. The package provides `RESUME_TASK` to re-run unfinished chunks:

```sql
BEGIN
    DBMS_PARALLEL_EXECUTE.RESUME_TASK(
        task_name      => 'CUSTOMER_EMAIL_BACKFILL',
        parallel_level => 2
    );
END;
/
```

Once the task completes, confirm zero failed chunks remain and validate the data. After archiving metadata needed for audit, you can drop the task:

```sql
BEGIN
    DBMS_PARALLEL_EXECUTE.DROP_TASK(
        task_name => 'CUSTOMER_EMAIL_BACKFILL'
    );
END;
/
```

Verify view names, status columns, privileges, and package signatures for your version. Never drop a task while you still need to resume or investigate errors.

### 6.5. Privileges and Operations

`DBMS_PARALLEL_EXECUTE` relies on Scheduler and related privileges. Grant least privileges per Oracle documentation, such as package execute and appropriate job creation/execution rights. Never grant `DBA` just to make a task run.

Monitor worker counts, sessions, CPU, I/O, undo, redo, archive destinations, and application load. Cap `parallel_level` conservatively; start with 2–4 workers in test environments and measure before scaling up.

## 7. Undo: Role and Risks During Backfilling

### 7.1. What Is Undo Used For?

Oracle generates undo to store information needed for rollbacks and read consistency. When a transaction updates a row, Oracle keeps the before-image in an undo segment. Concurrent queries can use undo to read the data version matching the query's SCN.

Backfills updating many rows generate substantial undo. The larger the transaction, the more undo must be retained for rollback and the longer row locks persist. Batch commits end transactions more frequently, allowing Oracle to reuse undo once no other queries/transactions need it under retention rules.

Committing does not immediately clear every undo block. Undo may still be needed for consistent reads, flashback, and other purposes until eligible for reuse.

### 7.2. Undo Retention and ORA-01555

`UNDO_RETENTION` sets a target retention time for undo, though in many configurations it is not an absolute guarantee if the undo tablespace runs short on space. Long-running queries can hit `ORA-01555: snapshot too old` if undo needed for consistent reads has been overwritten.

Contributing factors:

- System-wide undo generation rate.
- Undo tablespace size and autoextend settings.
- Duration of long-running queries.
- Commit frequency and concurrent workloads.
- `UNDO_RETENTION` and the `RETENTION GUARANTEE` option.
- Undo generation spikes during backfills.

Do not blindly crank up `UNDO_RETENTION`. Without enough disk space, requesting longer retention increases space pressure and allocation failures. `RETENTION GUARANTEE` protects undo from being overwritten under certain conditions, yet can cause new DML to fail when the tablespace fills up. Enable it only after DBA assessment of capacity and impact.

### 7.3. Monitoring V$UNDOSTAT

`V$UNDOSTAT` provides undo statistics across time intervals, typically 10-minute buckets:

```sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       ssolderrcnt,
       nospaceerrcnt,
       tuned_undoretention
FROM v$undostat
ORDER BY begin_time DESC;
```

Useful columns:

- `UNDOBLKS`: undo blocks consumed in the interval.
- `TXNCOUNT`: transactions in the interval.
- `MAXQUERYLEN`: longest observed query duration.
- `SSOLDERRCNT`: snapshot-too-old error count in the interval.
- `NOSPACEERRCNT`: out-of-undo-space error count.
- `TUNED_UNDORETENTION`: retention time auto-tuned by Oracle based on runtime conditions.

Monitor trends before, during, and after backfilling. If `UNDOBLKS` spikes sharply, `NOSPACEERRCNT` is non-zero, or `SSOLDERRCNT` climbs, throttle load, adjust batch sizes, or resolve space capacity per DBA decisions.

### 7.4. Estimating Undo Requirements

You can make a rough estimate from undo generation rate and retention time:

```text
Approximate undo space ≈ undo generation rate × retention interval
```

This is only an initial estimate; add overhead for concurrent workloads, long transactions, extent allocation, and safety headroom. Use `V$UNDOSTAT` metrics from peak hours for realistic sizing rather than measuring only when idle.

## 8. Redo: Controlling Logged Change Volume

### 8.1. Backfill DML Generates Redo

Oracle uses redo to guarantee crash and media recovery. A standard `UPDATE` generates redo for both data changes and associated changes, including required undo blocks. Consequently, backfilling many rows generates substantial redo even when no other users are writing data.

Redo is not something you can turn off for a regular `UPDATE` by setting `NOLOGGING`. `NOLOGGING` mainly affects specific supported direct-path or bulk operations; it does not turn conventional DML into unlogged operations.

### 8.2. Impact on Online Redo and Archive Logs

Redo is written to online redo logs. On log switches in `ARCHIVELOG` mode, Oracle archives the older log group. Fast redo generation from a backfill can cause:

- More frequent log switches.
- Rapidly growing archive destination usage.
- Overloaded archive processes or standby network links.
- Rising Data Guard transport/apply lag.
- Storage I/O and backup/archive contention with the application.
- Database stalls or errors if archive destinations fill up or cannot write logs.

Therefore, forecast redo rates and verify archive capacity before running. A backfill might finish its SQL cleanly while taking down the system because the archive destination ran out of space.

### 8.3. Monitoring Redo Generation

Inspect system statistics:

```sql
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'redo size',
    'redo entries',
    'redo writes',
    'redo blocks written'
);
```

Values in `V$SYSSTAT` are cumulative counters since instance startup. Capture snapshots before and after an interval to compute deltas and redo bytes/second. In multi-workload environments, these numbers reflect the entire database, not just the backfill.

Monitor log switches:

```sql
SELECT first_time, thread#, sequence#
FROM v$log_history
WHERE first_time >= SYSDATE - 1
ORDER BY first_time DESC;
```

In RAC, check by `THREAD#` since each redo thread has its own logs. Check archive destinations:

```sql
SELECT dest_id, status, error, destination
FROM v$archive_dest_status
WHERE status <> 'INACTIVE';
```

And archived log volume generated:

```sql
SELECT TRUNC(completion_time, 'HH24') AS hour_bucket,
       thread#,
       COUNT(*) AS archived_logs,
       SUM(blocks * block_size) AS bytes_archived
FROM v$archived_log
WHERE completion_time >= SYSDATE - 1
  AND archived = 'YES'
GROUP BY TRUNC(completion_time, 'HH24'), thread#
ORDER BY hour_bucket DESC, thread#;
```

These views may require appropriate catalog/dynamic performance view privileges. `V$ARCHIVED_LOG` can contain multiple rows per sequence due to multiple destinations/copies; filter or group by `DEST_ID`, `RESETLOGS_ID`, and status as appropriate for accurate architecture-specific accounting.

### 8.4. NOLOGGING Is Not a Universal Solution

`NOLOGGING` can reduce redo for certain operations such as direct-path inserts, CTAS, or index builds under specific conditions. However:

- Conventional `UPDATE` still generates redo.
- `FORCE LOGGING` at the database or tablespace level forces logging regardless of object `NOLOGGING` attributes.
- Some `NOLOGGING` operations prevent media recovery from reconstructing modified blocks without a subsequent backup.
- Data Guard/standbys can be impacted by unlogged operations depending on configuration and version.
- Post-operation backups may be mandatory per Oracle guidelines.

Never switch tablespaces/databases to `NOLOGGING` solely to speed up a backfill. For production data updates, prioritize batch sizing, pacing, execution windows, index strategy, and redo monitoring. If considering direct-path/`NOLOGGING` for a separate bulk load design, a DBA must assess recovery, standby, and backup implications upfront.

### 8.5. Indexes and Redo/Undo

When updating an indexed column, Oracle must also maintain the indexes. This increases redo, undo, logical I/O, and DML duration. Before backfilling, determine:

- Whether the target column is indexed.
- Whether function-based or composite indexes depend on it.
- Whether triggers/audits write extra records.
- Whether materialized view logs or replication capture depend on it.
- Whether building the index after backfilling makes more sense than maintaining it row-by-row.

Never drop production indexes/constraints on a whim just to speed up updates. Modifying index structures requires evaluating active queries, integrity, execution plans, and rebuild times, along with formal approval and a recovery plan.

## 9. Throttling Load and Choosing Parallelism

### 9.1. Pacing Between Batches

If batches run too fast and pressure redo/undo, you can:

- Reduce batch size.
- Lower `parallel_level` or fall back to a single worker.
- Add controlled pauses between batches.
- Run only during low-traffic windows.
- Pause when CPU, I/O, archive lag, or application latency crosses thresholds.
- Prioritize colder partitions or data segments first.

Do not scatter `DBMS_SESSION.SLEEP` across workers without measuring. Pauses are crude throttles; driving adjustments from clear metrics and thresholds is much better.

### 9.2. Running Multiple Workers

Parallelism boosts throughput but also increases:

- Concurrent row locks and block contention.
- Undo/redo generation rates.
- CPU and I/O load.
- Session and process counts.
- Archive log and standby apply pressure.
- Deadlock risk if chunks update multiple tables or overlapping keys in different orders.

Increase parallelism only after a single worker runs stably and bottlenecks are measured. Pick non-overlapping chunks; if chunks touch shared auxiliary tables or keys, design ordering and conflict handling carefully.

### 9.3. SKIP LOCKED for Work Queues

When using a queue table so multiple workers claim rows to process, `FOR UPDATE SKIP LOCKED` lets workers grab tasks not locked by peers:

```sql
SELECT task_id
FROM app.backfill_queue
WHERE status = 'PENDING'
ORDER BY task_id
FOR UPDATE SKIP LOCKED;
```

In production code, limit rows claimed per batch using Oracle-version-appropriate syntax, mark `RUNNING`, and commit the claim in an explicit transaction. `SKIP LOCKED` suits queues; it does not magically make arbitrary `UPDATE`s contention-free or immune to skipped rows. Use leases/timeouts to reclaim tasks if a worker dies after claiming.

### 9.4. Monitoring Long Sessions and Transactions

Find open transactions and undo usage:

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.module,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$transaction t
JOIN v$session s ON s.taddr = t.addr
ORDER BY t.used_ublk DESC;
```

`USED_UBLK` and `USED_UREC` show a transaction's undo consumption. Use `MODULE`/`ACTION` to identify backfill sessions, configurable via the application or `DBMS_APPLICATION_INFO`.

Also monitor `V$SESSION_LONGOPS`, `V$SESSION`, wait events, blocking sessions, and monitoring dashboards. Never kill a session solely because it has run long; rolling back a huge transaction can also take considerable time and cause heavy impact.

## 10. DML Error Logging and Handling Bad Rows

### 10.1. When Is Error Logging Needed?

In some backfills, a handful of rows contain invalid data causing conversion or constraint errors. When requirements permit processing valid rows while logging bad rows for later remediation, Oracle DML error logging is helpful.

Create an error log table:

```sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name => 'CUSTOMERS',
        err_log_table_name => 'ERR$_CUSTOMERS'
    );
END;
/
```

Then attach `LOG ERRORS` to the DML statement:

```sql
UPDATE app.customers
SET email_normalized = LOWER(TRIM(email)),
    backfill_done = 'Y'
WHERE customer_id > :low_id
  AND customer_id <= :high_id
  AND backfill_done = 'N'
LOG ERRORS INTO app.err$_customers ('EMAIL_BACKFILL_V1')
REJECT LIMIT UNLIMITED;
```

Adapt schema/owner and error table names to your actual setup. `LOG ERRORS` logs supported row-level errors instead of aborting the entire DML on the first loggable error. Not every error type is caught by error logging; statement-level errors or unsupported cases will still fail the statement.

### 10.2. Never Ignore Errors Without a Process

After each batch, summarize the error table by tag, identify root causes, and decide:

- Fix source data and re-run failed rows.
- Quarantine rows for data owners to resolve.
- Accept skipping under approved business rules.
- Halt the migration if the error rate exceeds thresholds.

Never set `REJECT LIMIT UNLIMITED` and assume job success means every row was backfilled. Reconcile error counts, updated row counts, and pending row counts.

## 11. Monitoring Progress and Impact During Execution

### 11.1. Backfill-Level Metrics

Record per batch:

- Task/chunk ID and key range.
- Start time, end time, and duration.
- Expected rows, actually updated rows, and skipped rows.
- Error count and error codes.
- Committed checkpoint.
- Batch size and parallel level.
- Estimated redo/undo over the interval.

Never write sensitive row contents to logs. Use `DBMS_APPLICATION_INFO.SET_MODULE` and `SET_ACTION` to tag sessions:

```sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'DATA_BACKFILL',
        action_name => 'CUSTOMER_EMAIL_V1'
    );
END;
/
```

This helps DBAs correlate sessions with the backfill job in `V$SESSION` and monitoring tools.

### 11.2. Pause Thresholds

Define thresholds before execution, such as:

- Application p95 latency breaching SLA across consecutive intervals.
- CPU or storage latency exceeding operational limits.
- Undo tablespace nearing full or `NOSPACEERRCNT` rising.
- Archive destination running low on space.
- Data Guard transport/apply lag exceeding limits.
- Rising blocking sessions or deadlocks.
- Backfill error rate exceeding acceptable bounds.

When thresholds breach, lower parallelism or pause after the current batch. Avoid aborting mid-transaction unnecessarily. Commit checkpoints after every batch so resuming is clean.

### 11.3. Measuring Redo/Undo Over Time Intervals

To estimate redo rate, take two `V$SYSSTAT` snapshots separated by an interval and divide the `redo size` delta by elapsed seconds. To track undo, compare `V$UNDOSTAT` buckets. For archive pressure, monitor filesystem/ASM free space, archive log rate, and destination statuses.

Do not attribute 100% of database redo/undo to the backfill while application traffic is active. Combine module/action, session metrics, timestamps, and pre-run baselines to approximate isolated impact.

## 12. Completing and Validating the Backfill

### 12.1. Counting Remaining Pending Rows

If using a marker:

```sql
SELECT backfill_done, COUNT(*) AS row_count
FROM app.customers
GROUP BY backfill_done
ORDER BY backfill_done;
```

Or:

```sql
SELECT COUNT(*) AS rows_pending
FROM app.customers
WHERE backfill_done = 'N';
```

Do not rely solely on the final checkpoint. A chunk could be marked complete while specific rows were skipped by error logging or unmatched `WHERE` clauses. Inspect the actual data.

### 12.2. Checking Value Quality

Example check for normalized emails:

```sql
SELECT COUNT(*) AS invalid_normalized_values
FROM app.customers
WHERE backfill_done = 'Y'
  AND email IS NOT NULL
  AND email_normalized <> LOWER(TRIM(email));
```

For complex transformations, share the exact same normalization function/logic across backfill and validation. Check `NULL`s, empty strings, Unicode characters, and edge cases.

### 12.3. Checking Indexes, Constraints, and Statistics

After backfilling:

- Confirm indexes are `VALID`.
- Confirm constraints are enabled and validated as required.
- Gather statistics for new columns/indexes when aligned with policy.
- Inspect execution plans for application queries.
- Confirm redo/archive rates and Data Guard lag returned to normal.
- Inspect the error table and resolve all failed rows.

If the new column appears in predicates or joins, updated statistics help the optimizer estimate selectivity accurately. Avoid gathering stats across everything immediately after backfill without assessing load and plan stability.

### 12.4. Removing Transitional Mechanisms

Only after backfill and validation succeed:

- Switch the application to read the new column.
- Monitor through the compatibility window.
- Stop dual-writing once all application versions have transitioned.
- Add `NOT NULL`, constraints, or indexes if required.
- Remove markers/work queues and old columns in a separate migration once the rollback window closes.

Do not delete checkpoints or error logs before archiving required audit evidence. Retain migration history per audit policy.

## 13. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Undo tablespace growing rapidly | Oversized batches, too many workers, or high concurrent workload. | Shrink batch/parallelism, check `V$UNDOSTAT`, evaluate capacity. |
| `ORA-30036` | Unable to extend undo segment due to lack of space. | Inspect datafiles/autoextend and undo usage, throttle load; DBA resolves space. |
| `ORA-01555` | Undo required for consistent read was overwritten. | Check query durations, undo generation/retention, and space; adjust workload. |
| Archive logs growing rapidly | Backfill generates heavy redo or archive destination is slow/full. | Monitor redo rate, log switches, archive destinations, and Data Guard lag; throttle batches. |
| `ORA-00257` | Archiver error, usually tied to archive destination issues. | Resolve archive space/status per DBA runbook before continuing writes. |
| Application blocked | Batch holds row locks long or updates hot rows. | Shrink batches, reorder/split scope, pick low-traffic windows. |
| Re-running backfill overwrites fresh data | Missing marker/version filter or expression reads stale data. | Use dual-writes, conditional updates, version checks, and catch-up passes. |
| Missed rows despite checkpoint reaching end | High-water excluded late-committing transactions or a writer was missed. | Review snapshot/SCN, CDC, write boundaries, and reconciliation. |
| Repeated batch creates duplicate data | Non-idempotent operation or checkpoint outside data transaction. | Use unique keys/MERGE/event IDs and atomic transaction checkpoints. |
| `DBMS_PARALLEL_EXECUTE` has failed chunks | Bad data, deadlocks, privilege, or resource issues. | Inspect chunk errors, fix root cause, then `RESUME_TASK`; keep SQL idempotent. |
| Data Guard lag increasing | Redo generation outpaces transport/apply throughput. | Lower parallelism, monitor standby, check bandwidth/storage. |

Never blindly raise `UNDO_RETENTION`, flip to `NOLOGGING`, or kill sessions to mask these errors. First diagnose the root cause and assess recoverability impact.

## 14. Sample Backfill Runbook

### Pre-Run

1. Define target data, transformation expressions, and completion markers.
2. Inspect chunking keys, indexes, partitions, triggers, constraints, and active writers.
3. Confirm the application supports dual-writes or a catch-up mechanism.
4. Capture an appropriate high-water/snapshot boundary.
5. Measure baseline redo/undo, archive rate, Data Guard lag, CPU, I/O, and app latency.
6. Select initial batch size and parallel level from rehearsals.
7. Prepare checkpoints, error tables, logging, and resume commands.
8. Confirm backup/recovery readiness and on-call DBA coverage for the execution window.

### During Execution

1. Tag backfill sessions with module/action.
2. Claim a chunk or compute the next range.
3. Execute conditional DML skipping already-completed rows.
4. Record updated row counts and errors.
5. Update checkpoints in the same transaction or let the chunk framework manage commits.
6. Commit per batch.
7. Monitor batch duration, redo/undo, archive usage, blocking, and app latency.
8. Throttle or pause if thresholds are breached.
9. On error, preserve checkpoints, analyze the failed batch, and resume only after verifying retry safety.

### Post-Run

1. Confirm all chunks finished with zero unresolved failed chunks.
2. Count remaining pending and error rows.
3. Reconcile new values against business rules.
4. Verify indexes, constraints, statistics, and execution plans.
5. Confirm archive/standby lag and system resources returned to baseline.
6. Switch application reads to the new data per rollout plan.
7. Archive reports, checkpoints, and error logs per policy.
8. Remove old markers/tasks only after the rollback window closes and approval is granted.

## 15. Key Principles to Remember

- Backfills on large tables should be split into measurable, resumable small transactions.
- Chunk by stable keys, `ROWID`, or partitions depending on table structure and task lifespan.
- Checkpoints must reflect committed data; ideally update them in the same transaction as the batch.
- Design idempotent DML and protect fresh application updates from being overwritten.
- High-water marks do not automatically yield consistent snapshots; handle in-flight transactions and new writes.
- Conventional `UPDATE`s generate redo and undo; `NOLOGGING` does not turn off redo for regular updates.
- Monitor `V$UNDOSTAT`, `V$SYSSTAT`, log switches, archive destinations, and Data Guard lag.
- Commit per batch to bound transaction size, locks, and rollback cost; avoid row-by-row commits.
- Scale parallelism gradually while measuring impact on live workloads.
- Use `DBMS_PARALLEL_EXECUTE` when chunk/job tracking is helpful; resume only after confirming safe SQL re-execution.
- Error logging isolates bad rows but does not replace reconciliation.
- Mark completion only after verifying checkpoints, pending counts, error logs, and data quality.

## Conclusion

Safe backfilling combines chunking, transaction boundaries, checkpoints, idempotency, and resource monitoring. Splitting data by key, `ROWID`, or partition bounds lock durations and per-transaction undo; committing checkpoints alongside data enables resuming after interruptions without starting over. Oracle still generates redo for conventional DML, so monitor redo rates, online/archive logs, undo usage, and Data Guard lag; `NOLOGGING` is not a switch to disable redo on `UPDATE`s. With `DBMS_PARALLEL_EXECUTE`, each chunk tracks its own state and can be resumed, yet the DML itself must remain safe to re-run. Ultimately, reconciling the actual data and resolving failed rows is what proves the backfill completed accurately.
