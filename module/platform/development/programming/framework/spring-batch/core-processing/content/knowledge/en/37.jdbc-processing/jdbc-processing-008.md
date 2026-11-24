# Deadlocks When Reading and Writing the Same Table

In Spring Batch, a Job may read records from a table and update that very same table within the same Step. For example, a Job selects transactions with status `READY`, processes them, and changes their status to `PROCESSED`. With a single worker, this flow may run smoothly. However, when multiple `JobExecution`s, partitions, or concurrent transactions access the table, the database can experience lock waits or deadlocks.

A **deadlock** occurs when two or more transactions hold locks that the other transactions need, forming an unresolvable wait cycle. The database detects the cycle and aborts one transaction as the deadlock victim. This is a database consistency protection mechanism; Spring Batch needs to roll back the corresponding chunk and can retry if the error is classified as transient.

Not every scenario of reading and writing the same table causes deadlocks. A plain `SELECT` on an MVCC database may not block `UPDATE`s at all. Risk depends on the database engine, isolation level, read query type, indexes, lock ordering, transaction duration, and number of concurrent workers. Beyond deadlocks, updating a column used in the read predicate can also cause paging to skip records even without any deadlock.

## 1. Context of Reading and Writing the Same Table

Suppose the `work_item` table holds tasks to process:

~~~sql
CREATE TABLE work_item (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    payload TEXT,
    processed_at TIMESTAMP
);
~~~

The reader fetches pending records:

~~~sql
SELECT id, status, payload
FROM work_item
WHERE status = 'READY'
ORDER BY id;
~~~

The writer updates status after processing:

~~~sql
UPDATE work_item
SET status = 'PROCESSED',
    processed_at = CURRENT_TIMESTAMP
WHERE id = :id;
~~~

A Step may wire the reader and writer as follows:

~~~text
work_item (status = READY)
       |
       v
    ItemReader
       |
       v
   ItemProcessor
       |
       v
    ItemWriter
       |
       v
UPDATE work_item
SET status = PROCESSED
~~~

This design is valid in many systems. Trouble arises when one transaction holds locks on rows or index entries while another transaction needs the same resources in a different order, or when the reader uses locking reads and holds locks for a long time while the chunk processes.

## 2. How Deadlocks Differ from Lock Waits

A **lock wait** occurs when one transaction must wait for a lock currently held by another transaction. Once the lock-holding transaction commits or rolls back, the waiting transaction can proceed.

A **deadlock** is a wait cycle. Example:

~~~text
Transaction A holds lock on row 1
Transaction B holds lock on row 2

Transaction A needs row 2 -> waits for B
Transaction B needs row 1 -> waits for A

       A waits for B
       B waits for A
             |
             v
          DEADLOCK
~~~

The database cannot wait indefinitely in this situation. It chooses one transaction as the victim, rolls it back, and returns an error to the application. The remaining transaction proceeds after locks are released.

| Phenomenon | Characteristics | Resolution |
|---|---|---|
| Lock wait | One transaction holds a lock while another waits | Shorten lock hold duration, review transactions and indexes |
| Deadlock | Transactions form a circular lock-wait graph | Analyze the deadlock graph, standardize access order, use bounded retry |
| Lock timeout | Transaction waits beyond configured timeout | Identify the blocker and tune timeouts/transactions |
| Pagination misses | Result set shifts when writer modifies filter condition | Stabilize input set or use appropriate reading/claiming strategy |

Deadlocks are typically transient at the transaction level, yet their underlying design cause can recur on every run. Simply raising retry limits without fixing lock ordering or transaction duration can slow down the Job and increase database load.

## 3. Why Can Reading and Writing the Same Table Cause Deadlocks?

Several common scenarios cause this:

1. Two workers read overlapping sets of rows and then update them in different orders.
2. The reader uses `SELECT FOR UPDATE` or locking hints and holds locks while the processor performs slow work.
3. One transaction reads/locks row A and the writer updates row B, while another transaction locks B and needs A.
4. The writer updates the main table, and triggers or foreign keys force the database to lock additional tables/indexes in a different order than another transaction.
5. Two `JobExecution`s concurrently process overlapping record ranges.
6. Partitions are not independent, causing multiple workers to update the same business key.

A plain non-locking `SELECT` does not necessarily cause deadlocks. On MVCC databases, consistent reads usually read a snapshot without holding row locks that block writers. However, locking reads, higher isolation levels, index/range locks, or engines using locking reads for `SELECT` can create contention. Verify your actual database's behavior.

## 4. Deadlocks from Two Transactions Updating Rows in Different Orders

Suppose the table has two rows:

~~~text
id = 10
id = 20
~~~

Transaction A processes items in order 10 then 20:

~~~sql
UPDATE work_item SET status = 'DONE' WHERE id = 10;
UPDATE work_item SET status = 'DONE' WHERE id = 20;
~~~

Transaction B processes them in order 20 then 10:

~~~sql
UPDATE work_item SET status = 'DONE' WHERE id = 20;
UPDATE work_item SET status = 'DONE' WHERE id = 10;
~~~

A possible interleaving:

| Step | Transaction A | Transaction B |
|---|---|---|
| 1 | Locks row 10 | |
| 2 | | Locks row 20 |
| 3 | Needs row 20, waits for B | |
| 4 | | Needs row 10, waits for A |
| 5 | Database detects cycle and rolls back one transaction | |

To reduce risk, all transactions should access rows in the same lock order, such as ascending primary key order. Even if each item updates only one row, inspect triggers, cascades, indexes, and other transactions that could introduce extra lock dependencies.

Sorting items by ID in the reader can help, but only if every related write path follows the exact same order. A stable read order is insufficient if triggers or other services lock rows in reverse order.

## 5. Deadlocks from Locking Reads

A reader may use a locking query to hold rows during processing:

~~~sql
SELECT id, payload
FROM work_item
WHERE status = 'READY'
ORDER BY id
FOR UPDATE;
~~~

`FOR UPDATE` is common syntax in PostgreSQL, Oracle, and several other databases; exact syntax and behavior vary by engine. This query requests locks on selected rows so other transactions cannot perform conflicting updates until the transaction finishes.

If the processor makes API calls, performs heavy computation, or waits on external services before the writer finishes, the transaction can hold locks for a long time. Other workers may need those rows or related rows and form a wait cycle.

Do not use locking reads just to "avoid duplicate processing" without defining the required semantics. Claim/lease mechanisms, partitioning, or optimistic locking may be more suitable. If row locks are truly needed, keep transactions short and clearly define row ownership.

## 6. Reader and Writer May Use Different Connections/Transactions

Not all readers interact with chunk transactions the same way:

- `JdbcCursorItemReader` opens a cursor and uses a separate connection by default. There is an option to share an extended connection in some cases, requiring proper `ExtendedConnectionDataSourceProxy` configuration.
- `JdbcPagingItemReader` executes page queries and maintains paging/checkpoint state; each query may have different transaction/connection semantics than a cursor.
- A custom reader might use `JdbcTemplate`, a repository, or a self-managed connection.
- Writers typically use a connection managed by the transaction manager if the `DataSource` and transaction manager are configured compatibly.

Therefore, do not infer that `SELECT` and `UPDATE` definitely run on the same connection or in the same transaction merely because they belong to one Step. Verify the reader implementation, `DataSource`, transaction manager, connection sharing, and isolation level.

If reader and writer share a `DataSource` while the reader keeps a cursor on a separate connection, the cursor can outlive multiple chunk transactions. This affects snapshots, lock duration, and visibility of changes. With shared extended connections enabled, semantics differ again. Check the documentation for your Spring Batch version and database driver.

## 7. Chunk Transactions and Lock Hold Duration

In a chunk-oriented Step, Spring Batch manages transactions per chunk. When a chunk processes multiple items, the transaction typically wraps chunk processing and commits after the writer finishes along with corresponding metadata updates.

Conceptual flow:

~~~text
Begin chunk transaction
       |
       v
Read items
       |
       v
Process items
       |
       v
Write chunk
       |
       v
Update stream/checkpoint
       |
       v
Commit
~~~

If the reader executes a locking read inside this transaction, locks may be held throughout processor execution. Large chunks or slow processors lengthen transactions, increasing how long other transactions wait.

Causes of prolonged transactions:

- Overly large chunk sizes.
- Processor making REST/SOAP calls or waiting on message brokers.
- N+1 queries inside the processor.
- Writer updating many tables or calling heavy stored procedures.
- Missing database indexes for filter predicates or joins.
- Undersized connection pools causing transactions to hold connections longer.

Shortening transaction duration usually reduces lock contention. However, smaller chunks increase commit frequency and overhead. Measure against your real workload instead of picking chunk size purely by item count.

## 8. Isolation Levels and Read Behavior

Isolation levels govern how much a transaction sees changes from other transactions and what locks/snapshots the database uses. Exact behavior depends on the engine:

| Isolation | General meaning | Points to watch |
|---|---|---|
| READ UNCOMMITTED | May read uncommitted data on engines that support it | Dirty reads; unsuitable for many batch workloads |
| READ COMMITTED | Each statement sees committed data per engine semantics | May read a new snapshot per query; does not guarantee one dataset across the Step |
| REPEATABLE READ | Protects read repeatability per engine | Can increase locking or snapshot retention |
| SERIALIZABLE | Requires outcomes equivalent to serial execution | Can increase blocking, serialization failures, or deadlocks |

Some databases use MVCC so plain `SELECT`s do not lock rows needed by writers. For instance, PostgreSQL consistent reads under common isolation levels typically do not block `UPDATE`s the way locking reads do; MySQL InnoDB also distinguishes consistent reads from locking reads. SQL Server can use locking `READ COMMITTED` or row-versioning when `READ_COMMITTED_SNAPSHOT` is enabled. Never apply one blanket description to every database.

Do not lower the isolation level just to make deadlocks disappear. First, determine the consistency the Job requires: a full-run snapshot, statement-level committed reads, or exclusive row claiming. Then choose the matching isolation and locking strategy.

## 9. Distinguishing Deadlocks from Pagination Missing Records

A bug commonly mistaken for a deadlock occurs when the reader filters by status and the writer updates that very status.

Suppose the query uses offset pagination:

~~~sql
SELECT id, payload
FROM work_item
WHERE status = 'READY'
ORDER BY id
OFFSET :offset ROWS FETCH NEXT :pageSize ROWS ONLY;
~~~

Initially there are 6 `READY` rows and page size is 3:

~~~text
Page 1: id 1, 2, 3
Page 2: id 4, 5, 6
~~~

After page 1 is read and the writer changes status of 1, 2, 3 to `PROCESSED`, the `READY` set only contains 4, 5, 6. If the next page still uses `OFFSET 3`, the database skips the first three rows of the new result set and may return empty results. Rows 4, 5, 6 are skipped even though no deadlock occurred.

This is a shifting result-set pagination bug, not a lock cycle. It can be avoided by:

- Reading input IDs into staging/snapshot before updating status.
- Using keyset pagination with a unique and stable sort key.
- Using a claim strategy with explicit states.
- Avoiding predicate mutations that shift page datasets unpredictably for the reader.

`JdbcPagingItemReader` typically uses sort keys to resume from the last page position rather than every implementation using `OFFSET`. Even so, when query predicates change because the writer updates the same table, inspect the specific paging semantics and test restart scenarios. Never conflate pagination bugs with deadlocks.

## 10. Keyset Paging and Stable Sort Keys

Keyset paging fetches rows after the last key read, for example:

~~~sql
SELECT id, status, payload
FROM work_item
WHERE status = 'READY'
  AND id > :lastId
ORDER BY id
FETCH FIRST :pageSize ROWS ONLY;
~~~

The sort key should be:

- Non-null.
- Immutable throughout the Job run.
- Unique, or paired with a unique tie-breaker.
- Supported by an index matching both predicate and ordering.

With a composite sort key:

~~~sql
WHERE (created_at, id) > (:lastCreatedAt, :lastId)
ORDER BY created_at, id
~~~

Tuple comparison syntax varies by database; it can also be rewritten as an equivalent `OR` condition.

Keyset paging mitigates offset-shifting issues when the result set changes. However, if the writer updates `status` so rows stop matching the predicate, or new rows are inserted with keys smaller than the checkpoint, the reader still needs an explicit snapshot/eligibility policy.

## 11. Reading a Snapshot Then Updating Status in Separate Steps

A clean way to reduce contention between reading and writing the same table is separating input selection from source table updates:

~~~text
Step 1: Snapshot IDs to process
   work_item (READY)
        |
        v
   staging_batch_item

Step 2: Process IDs in staging
   staging_batch_item
        |
        v
   Processor
        |
        v
   Writer updates work_item

Step 3: Reconcile batch
   Summarize COMPLETED / FAILED
~~~

Example staging table:

~~~sql
CREATE TABLE batch_work_item (
    batch_id VARCHAR(80) NOT NULL,
    item_id BIGINT NOT NULL,
    state VARCHAR(20) NOT NULL,
    PRIMARY KEY (batch_id, item_id)
);
~~~

A preparation step inserts eligible IDs into `batch_work_item`. Subsequent Steps read staging by `batch_id`, while the writer updates `work_item`. Because the input set is fixed, status updates on the source table do not alter the list of items to process.

Rules are needed to prevent two Jobs from snapshotting the same item simultaneously. You can claim rows when building staging, enforce unique constraints, or run a claim transaction with a clear locking strategy. Staging also requires cleanup/retention and failure recovery.

## 12. Claiming Rows Instead of SELECT Then UPDATE

When multiple workers pull work from one table, a "SELECT READY then later UPDATE PROCESSED" pattern can let two workers read the same row before either updates it. An atomic claim mechanism is needed.

Some databases support `SKIP LOCKED` or similar locking hints so workers grab rows not locked by other workers. PostgreSQL example:

~~~sql
WITH picked AS (
    SELECT id
    FROM work_item
    WHERE status = 'READY'
    ORDER BY id
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE work_item w
SET status = 'IN_PROGRESS',
    claimed_by = :workerId,
    claimed_at = CURRENT_TIMESTAMP
FROM picked
WHERE w.id = picked.id
RETURNING w.id, w.payload;
~~~

This is PostgreSQL syntax, not portable SQL. MySQL, Oracle, and SQL Server have their own syntax/locking hints. `SKIP LOCKED` prevents workers from waiting on rows locked by peers, though it does not eliminate all deadlocks and can cause starvation if a row stays locked repeatedly.

A claim workflow can:

1. Select and update `READY` rows to `IN_PROGRESS` in a short transaction.
2. Commit the claim so other workers cannot pick the same rows.
3. Process items under the claim token/worker ID.
4. Update status to `COMPLETED` or `FAILED`.
5. Use a lease/timeout to reclaim abandoned work if a worker dies.

If claiming and processing happen in the same long transaction, locks stay held throughout processing. To release locks early, commit the claim first and provide a lease/recovery mechanism for dead or disconnected workers.

## 13. Partitioning to Reduce Overlap

Partitioning can reduce deadlocks when each worker receives a non-overlapping data range:

~~~text
Manager Step
    |
    +--> Worker 0: id 1..10000
    |
    +--> Worker 1: id 10001..20000
    |
    +--> Worker 2: id 20001..30000
~~~

When each worker reads and updates rows within its own range, the chance of two workers contending on the same row drops. However, partitioning only works well if:

- Ranges do not overlap.
- Writers do not update rows outside their range.
- Triggers/foreign keys do not create contention on a shared summary row.
- Related tables are locked in a consistent order.
- No other Job concurrently processes the same business keys.

If partitioning by customer while all workers update one global summary row, that summary row becomes a hotspot. You can write detailed rows in parallel and aggregate in a separate Step.

## 14. Reducing Transaction Duration

One of the most effective measures is shortening how long transactions hold locks:

- Choose a moderate chunk size and benchmark it.
- Avoid slow network calls inside the transaction when they can be separated.
- Avoid repeated auxiliary queries in the processor.
- Create indexes for filter predicates and joins.
- Update only the columns that actually need changing.
- Do not hold cursors/locking reads longer than necessary.
- Avoid nested transactions or unintended propagation.
- Ensure connections return to the pool once the Step/transaction ends.

For example, if a processor calls a pricing service taking 2 seconds per item and the chunk has 500 items, the transaction holds resources for a very long time. You can move enrichment/lookups outside the write transaction, use caches/snapshots, or pre-process before running a short update transaction.

Not every operation can be split out of the transaction while preserving semantics. If data can change between reading and writing, verify a version or expected status condition on update.

## 15. Conditional Updates and Optimistic Locking

A writer can update by ID and expected state:

~~~sql
UPDATE work_item
SET status = 'PROCESSED',
    version = version + 1,
    processed_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND status = 'IN_PROGRESS'
  AND version = :expectedVersion;
~~~

If the update count is 0, another worker may have updated the row or the version no longer matches. This signals a conflict to handle, not necessarily a deadlock.

Optimistic locking fits when conflicts are rare and you do not want to hold locks from read time to write time. Define explicit conflict-handling behavior: re-read and retry, mark a conflict state, or fail the item.

Never ignore an update count of 0 when the item must be written. Conditional updates and affected-row checks detect races instead of silently overwriting newer data.

## 16. How Indexes Affect Lock Footprint

Missing indexes can force the database to scan many rows/pages to locate data, lengthening queries and potentially locking wider ranges depending on engine and isolation. Indexes do not eliminate deadlocks by themselves, but they typically shrink scanned row counts and lock hold times.

Example query:

~~~sql
SELECT id, payload
FROM work_item
WHERE status = 'READY'
ORDER BY id;
~~~

A suitable index might lead with `status` followed by `id`:

~~~sql
CREATE INDEX ix_work_item_status_id
    ON work_item(status, id);
~~~

Exact indexing depends on selectivity, query plans, and the database. When updating `status`, the database must also update indexes containing `status`, so excessive indexes can increase write overhead and locking. Inspect execution plans and measure before adding indexes.

Joins, triggers, and foreign keys can also touch additional tables/indexes. The deadlock graph often reveals the actual contended resources, which are not always the rows in the initial reader table.

## 17. Standardizing Resource Access Order

If a chunk updates multiple tables, every execution path should access tables and rows in the same order. Example:

~~~text
Order -> Account -> Ledger
~~~

Do not let one transaction update `Account` then `Order` while another updates `Order` then `Account` if both can wait on each other.

Guidelines:

- Sort ID lists before performing bulk updates.
- Keep table update order consistent across all services and triggers.
- Never hold locks on one table while invoking unrelated code before updating another table.
- Include cascades and triggers when analyzing lock order.
- If using stored procedures, verify access order inside the procedure.

Standardizing lock order is a vital preventive measure, though databases can still deadlock on index pages, range locks, or other transactions. Combine it with bounded retries and deadlock monitoring.

## 18. Retrying Deadlocks in Spring Batch

Databases usually pick one transaction as the deadlock victim and return an error to the application. When the error is classified as transient, Spring Batch can retry the chunk/item per fault-tolerance configuration.

Example:

~~~java
return new StepBuilder("processWorkItemsStep", jobRepository)
        .<WorkItem, WorkItem>chunk(100, transactionManager)
        .reader(workItemReader)
        .processor(workItemProcessor)
        .writer(workItemWriter)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

`DeadlockLoserDataAccessException` is a common exception type in some Spring JDBC configurations. Translated exceptions can vary by Spring Framework version, database driver, and vendor error codes. Inspect root causes and actual exception translation before configuring retries; do not catch all `DataAccessException`s if non-transient errors are included.

You can add backoff to keep workers from retrying simultaneously right away:

~~~java
.faultTolerant()
.retry(DeadlockLoserDataAccessException.class)
.retryLimit(3)
.backOffPolicy(new ExponentialBackOffPolicy())
~~~

Exact backoff APIs and configuration depend on your Spring Batch version. Tune initial interval, multiplier, and max interval to match transaction times and database load.

Retry only handles the specific deadlock occurrence. If all workers continually lock the same resources in the same conflicting pattern, retries increase load and Job runtime without fixing the root cause.

## 19. Chunk Rollback and Idempotency

When a deadlock victim rolls back, the entire transaction for that chunk can be undone. Spring Batch may re-execute processing per the retry policy.

Therefore, processors and writers must be safe when re-invoked:

- Do not send emails or non-idempotent messages directly inside the processor.
- Do not call external transaction-creating APIs without an idempotency key.
- Do not increment in-memory business counters and treat them as committed item counts.
- Use unique constraints/business keys to prevent duplicate inserts.
- Move side effects to an outbox if events must be emitted only after database commit.

If the writer updates the same database within the chunk transaction, rollback undoes those updates. However, side effects to systems outside the database do not roll back automatically. On retry, those side effects can execute twice.

For status-based updates, use expected status/version conditions to detect items already handled by another worker. Retry rules must distinguish transient deadlocks from business conflicts.

## 20. Distinguishing Deadlock Retry from Skip

Deadlocks are normally transient transaction errors better suited for bounded retry than skipping items. Skipping an item simply because the database temporarily failed to grant a lock can lose valid data.

| Error | Typically Appropriate Behavior |
|---|---|
| Deadlock victim | Retry transaction/chunk with limit and backoff |
| Lock timeout | Analyze blocker; retry if error is transient and operation is safe |
| Optimistic version conflict | Re-read or handle conflict per business rules |
| Permanent data violation | Fail or skip per business policy |
| SQL syntax/configuration error | Fail fast |
| Database unavailable | Retry per infrastructure policy, then fail if threshold exceeded |

If retries exhaust their limit, the Step should fail so operations can investigate. Never raise `skipLimit` to turn deadlocks into skipped records.

## 21. Diagnosing Deadlocks from the Database

When deadlocks occur, gather evidence from the database rather than looking solely at Spring Batch stack traces.

Data to collect:

- Database engine and version.
- Transaction isolation levels.
- SQL statements of each involved transaction.
- Tables/indexes/rows/pages/key resources being locked.
- Which transaction holds the lock and which is waiting.
- Lock modes and lock acquisition order.
- Execution plans for the read/write queries.
- `JobExecution` ID, `StepExecution` ID, partition, and chunk involved.
- Transaction start times and deadlock timestamp.

Database deadlock graphs or deadlock reports typically identify the victim, owner, waiter, and resources. This is essential for pinning down the actual wait cycle.

Examples of engine-specific inspection:

- SQL Server captures deadlock graphs in Extended Events or the `system_health` session.
- PostgreSQL writes deadlock details to the server log when `log_lock_waits`/deadlock logging is configured; `pg_stat_activity` and `pg_locks` inspect live locks.
- MySQL InnoDB provides details via `SHOW ENGINE INNODB STATUS` and Performance Schema.
- Oracle offers traces/events and management views to analyze session waits and locks.

Exact commands and privileges depend on database/version. Do not run ad-hoc administrative queries on production without understanding their impact; prioritize preconfigured logs and monitoring.

## 22. Logs from Spring Batch and the Application

Application logs must correlate database errors to specific executions:

- Job name and `JobExecution` ID.
- Step name and `StepExecution` ID.
- Partition/worker identifier if applicable.
- Chunk or relevant business key.
- Exception type, `SQLState`, and vendor error code.
- Retry attempt.
- Transaction/chunk duration.

Do not log full payloads if they contain sensitive information. Business keys and correlation IDs are usually enough to tie logs to the deadlock report.

Spring Batch metadata records read/write/skip counts and `StepExecution` status. These counters narrow down the failing chunk/Step, but they do not replace the database deadlock graph.

## 23. Example Same-Table Reader/Writer Configuration

Simple example using `JdbcPagingItemReader` to read by ID and `JdbcBatchItemWriter` to update status:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<WorkItem> workItemReader(DataSource dataSource) {
    return new JdbcPagingItemReaderBuilder<WorkItem>()
            .name("workItemReader")
            .dataSource(dataSource)
            .selectClause("select id, status, payload")
            .fromClause("from work_item")
            .whereClause("where status = :status")
            .parameterValues(Map.of("status", "READY"))
            .sortKeys(Map.of("id", Order.ASCENDING))
            .pageSize(100)
            .rowMapper((rs, rowNum) -> new WorkItem(
                    rs.getLong("id"),
                    rs.getString("status"),
                    rs.getString("payload")))
            .saveState(true)
            .build();
}
~~~

Writer:

~~~java
@Bean
JdbcBatchItemWriter<WorkItem> workItemWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<WorkItem>()
            .dataSource(dataSource)
            .sql("""
                    UPDATE work_item
                    SET status = :newStatus,
                        processed_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                      AND status = :expectedStatus
                    """)
            .itemSqlParameterSourceProvider(item ->
                    new BeanPropertySqlParameterSource(item))
            .assertUpdates(true)
            .build();
}
~~~

The `WorkItem` model in this example needs `id`, `expectedStatus`, and `newStatus` properties, or the provider must supply those parameters from the real model. This snippet focuses on illustrating the query and conditional update; adapt the DTO/provider to your application.

Reading and updating the same table this way must be tested with concurrent data mutations. `sortKeys` using a unique key helps the reader continue in stable order. Yet when the writer changes `status`, verify the query provider, checkpoint, and predicate to ensure the input set does not mutate in a way that drops records.

If multiple workers execute the Step concurrently, partition IDs into non-overlapping ranges or use a claim strategy. Adding `@StepScope` alone does not give each thread inside the same Step its own reader.

## 24. A Batch Claim Design

When multiple workers pull work concurrently, a design can use a batch ID and claim token:

~~~sql
UPDATE work_item
SET status = 'IN_PROGRESS',
    batch_id = :batchId,
    claimed_by = :workerId,
    claimed_at = CURRENT_TIMESTAMP
WHERE id IN (
    SELECT id
    FROM work_item
    WHERE status = 'READY'
    ORDER BY id
    FETCH FIRST :batchSize ROWS ONLY
);
~~~

This is illustrative SQL only; subquery/locking syntax and atomicity depend on the database. Under high concurrency, use an engine-safe atomic claim statement with proper locks or `SKIP LOCKED`/locking hints, and inspect update counts.

After claiming, the worker reads:

~~~sql
SELECT id, payload
FROM work_item
WHERE batch_id = :batchId
  AND claimed_by = :workerId
  AND status = 'IN_PROGRESS'
ORDER BY id;
~~~

When processing finishes:

~~~sql
UPDATE work_item
SET status = 'PROCESSED',
    processed_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND batch_id = :batchId
  AND claimed_by = :workerId
  AND status = 'IN_PROGRESS';
~~~

The claim token prevents other workers from accidentally updating the item. You also need lease expiration and a claim-recovery process if a worker crashes. Without a lease, rows can stay stuck in `IN_PROGRESS` forever.

## 25. When to Separate Tables or Separate Steps

If reading and updating the same table continually causes lock contention, change the architecture:

- Create a staging table holding IDs to process.
- Separate the input snapshot Step from the status update Step.
- Write results to a separate output table and merge in a final Step.
- Use a queue or claim table to distribute work.
- Use a read replica/snapshot if replication lag is acceptable.
- Move aggregation work to a Step that runs after workers finish.

Reading from a read replica can reduce contention with writers on the primary, though replica data lags and is unsuitable when the Job must immediately see recent writes or claim rows exclusively. Never use a replica as a substitute for transaction/claim semantics.

Separating tables also carries costs: extra storage, cleanup, reconciliation, and handling partial states. Apply it only when concurrency, auditability, and restartability benefits justify the complexity.

## 26. Testing Deadlocks and Lock Contention

Do not test only with single-threaded runs. Write integration tests with two or more concurrent transactions on the real database engine.

Scenarios to test:

1. Two workers updating disjoint rows: no unexpected deadlocks.
2. Two workers updating the same rows in reverse order: confirm deadlock occurs and retry succeeds.
3. Locking reader holding rows while a writer runs: measure lock waits and confirm transactions complete cleanly.
4. Reader and writer sharing a table with changing status predicates: confirm no items are skipped.
5. Non-overlapping partition ranges: reconcile total business keys.
6. Concurrent claiming: each item is picked up by at most one worker.
7. Retry after deadlock: no duplicates or repeated side effects.
8. Restart after chunk rollback: checkpoints and database state remain consistent.
9. Transaction timeout: error is classified properly and not confused with deadlock.
10. Triggers/foreign keys: deadlock graph reveals no unexpected contested resources.

Use barriers/latches to synchronize when two transactions start, rather than relying on `Thread.sleep()` hoping to trigger a race. Run tests on a production-compatible database/driver because H2 has different locking and isolation semantics than many engines.

## 27. Investigation Checklist When a Job Hits Deadlocks

When a Step reports a deadlock, check systematically:

1. Is the root exception a deadlock, a lock timeout, or a connection failure?
2. Which transactions and resources does the database deadlock report identify?
3. Is the reader using locking reads or a high isolation level?
4. Which connections/transactions do the reader and writer use?
5. Are multiple `JobExecution`s or partitions reading overlapping ranges?
6. Do transactions update rows in the same order?
7. Which triggers, foreign keys, or indexes acquire additional locks?
8. How long do chunks and processors hold transactions open?
9. Do query plans use appropriate indexes?
10. Are retries bounded and are operations idempotent?
11. Are pagination/missing-record bugs occurring alongside deadlocks?
12. Do restarts resume with the same input snapshot and checkpoints?

The goal is finding the wait cycle and the conditions creating it, then fixing access order, transaction scope, claiming strategy, or data partitioning. Never diagnose the cause solely from the Step name or the fact that reader and writer touch the same table.

## 28. Common Pitfalls

**Assuming reading and writing the same table always deadlocks:** plain `SELECT`s on MVCC databases may not block writers. Check your database's actual locking behavior.

**Confusing lock waits with deadlocks:** one transaction waiting for a lock does not imply a cycle. Use deadlock graphs and lock monitoring.

**Using SELECT FOR UPDATE on every reader:** holding locks for long periods spikes contention. Use it only when explicit claim/locking semantics are needed.

**Running slow processors inside transactions:** network calls or heavy computation extend lock hold times. Move work outside or shorten transactions where possible.

**Two workers updating rows in different orders:** creates wait cycles. Standardize lock ordering and partition data without overlap.

**Using offset pagination while the writer mutates the predicate:** shrinking result sets can skip records. That is a paging bug, not a deadlock.

**Assuming @StepScope gives each thread its own reader:** `@StepScope` creates one instance per `StepExecution`, not per thread within a Step.

**Increasing retries without limit:** recurring deadlocks slow the Job and overload the database. Use retry limits, backoff, and fix root causes.

**Skipping deadlocks like data errors:** valid items can be lost. Deadlocks normally require retrying the transaction.

**Ignoring triggers and foreign keys:** deadlocks can involve tables/indexes different from the table queried by the reader.

**Using a read replica to claim data:** replicas can lag and do not provide the required locking semantics.

**Not testing restart after rollback:** retries can reprocess items; idempotency and consistent checkpoints are essential.

## Conclusion

Deadlocks when reading and writing the same table in Spring Batch do not stem simply from two operations touching one table. They happen when transactions form lock-wait cycles, commonly due to locking reads, overlapping data ranges, inconsistent update ordering, prolonged transactions, or additional locks from triggers/indexes. Obtain the database deadlock graph, verify reader isolation and connection semantics, standardize access order, partition without overlap, or use claiming/staging where needed. Shorten transaction durations and use bounded retries with backoff for transient deadlocks; keep processors and writers idempotent because chunks can roll back and retry. Also distinguish deadlocks from lock waits and pagination bugs caused by writers mutating read predicates. Test concurrency, rollback, and restart on the target database engine to guarantee no items are lost or duplicated.
