# Restart After a Database Commit

In a Spring Batch chunk-oriented step, the writer can write multiple items to the database and then the transaction commits. If the job stops right after that commit, the next run must determine precisely which data was durably persisted and which still needs processing. Spring Batch's restart mechanism relies on checkpoints stored in `JobRepository`, usually combined with state written by the reader and writer into `ExecutionContext`.

The core requirement is that business data and checkpoints must advance consistently. If the database committed a chunk while the checkpoint stayed at the old position, a restart may re-read and re-write already-processed items. If the checkpoint advanced while business data did not commit, a restart may skip items that were never persisted. When the writer and `JobRepository` participate in the same database transaction, Spring Batch can commit chunk data and checkpoints within the same transaction boundary. When they use different transaction managers or resources, you must design idempotency and reconciliation because natural atomicity between the two no longer exists.

## 1. Chunk Commits and Restart Are Two Halves of One Process

Spring Batch usually processes data in chunks. The reader fetches a group of items, the processor transforms each item, the writer persists the whole group, and then the chunk transaction commits.

Example with chunk size 100:

~~~text
Chunk 1: items 1-100    -> write -> commit
Chunk 2: items 101-200 -> write -> commit
Chunk 3: items 201-300 -> write -> commit
...
~~~

If the job fails after chunk 2 commits, a restart must resume from the checkpoint after item 200. The first two chunks are durably saved; the uncommitted next chunk must be re-executed from saved state.

A checkpoint is more than just the count of items read. It can include:

- The reader's current position in a file or resource.
- The last page/sort key read.
- Read/write counts and step status.
- Custom state saved by the reader or writer in `ExecutionContext`.
- Details needed to reopen resources and resume at the exact position.

Checkpoints are useful only if the data source and reader configuration still match that state. If input files change, query ordering changes, or resources are swapped between runs, the same checkpoint can point to different data.

## 2. Components Involved in Restart

| Component | Role |
|---|---|
| `JobInstance` | Represents one logical run identified by job name and identifying `JobParameters` |
| `JobExecution` | One concrete execution attempt of a `JobInstance`; restart creates a new `JobExecution` |
| `StepExecution` | Tracks one step execution attempt, including status and execution metrics |
| `JobRepository` | Persists metadata, execution status, and `ExecutionContext` |
| `ExecutionContext` | Stores state needed to restore on restart |
| `ItemStream` | Lifecycle for components to open resources, save state, and close resources |
| `PlatformTransactionManager` | Manages chunk transactions and enlisted resources |
| `ItemReader` | Reads items and records position/checkpoint if restartable |
| `ItemWriter` | Writes chunks and participates in the appropriate transaction |

Spring Batch does not automatically infer every read position from business tables. Stateful readers or components must implement `ItemStream` and persist needed info via `update(ExecutionContext)` when resuming from a prior position is required.

## 3. Execution Sequence of a Chunk

Conceptually, one chunk follows these steps:

1. The reader supplies the next items.
2. The processor transforms each item if configured.
3. The writer writes the chunk.
4. `ItemStream`s are asked to update state in `ExecutionContext`.
5. `StepExecution`/`ExecutionContext` are updated in `JobRepository`.
6. The transaction commits.

Simplified diagram:

~~~mermaid
sequenceDiagram
    participant R as ItemReader
    participant P as ItemProcessor
    participant W as JDBC ItemWriter
    participant C as Step/Chunk
    participant J as JobRepository
    participant DB as Database

    C->>R: read items
    R-->>C: chunk items
    C->>P: process items
    P-->>C: processed items
    C->>W: write chunk
    W->>DB: INSERT/UPDATE
    C->>R: ItemStream.update(context)
    C->>J: persist ExecutionContext and StepExecution
    C->>DB: commit transaction
~~~

The diagram depicts the case where `JobRepository` and the writer share a compatible transaction. Internal details can vary by version and configuration, but the principle to guarantee is that business changes and chunk checkpoints never commit independently in a way that leaves inconsistent state.

## 4. Why Must Database Commits and Checkpoints Stay Consistent?

Suppose the reader has read up to item 100 and the writer writes those items.

**Case A: Data commits, but checkpoint does not advance**

- The database contains results for items 1-100.
- `JobRepository` still holds the checkpoint before item 1.
- Restart re-reads items 1-100.
- If the writer is not idempotent, duplicates or unique-key failures can occur.

**Case B: Checkpoint advances, but data did not commit**

- `JobRepository` saves the checkpoint after item 100.
- The business database rolled back or failed to persist durably.
- Restart resumes at item 101.
- Items 1-100 are skipped despite having no results in the database.

Both cases represent divergence between progress metadata and business data. When checkpoints and the writer share a single database transaction, the transaction commits or rolls back both sets of changes together, minimizing this divergence window.

## 5. Same Transaction Manager and Same Database Resource

For JDBC data and restart metadata to commit atomically, you typically need:

- The JDBC writer uses the `DataSource` of the target database.
- `JobRepository` uses the same database resource.
- The chunk step uses a transaction manager managing that resource.
- Metadata writes and business data writes actually join the same transaction.

Conceptual configuration example:

~~~java
@Bean
public JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    insert into processed_order(order_id, amount)
                    values (:orderId, :amount)
                    """)
            .beanMapped()
            .build();
}

@Bean
public Step processOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        JdbcBatchItemWriter<Order> writer) {

    return new StepBuilder("processOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

This snippet assumes the writer and `JobRepository` are configured on the same transactional resource. Passing the same `DataSource` reference to two beans is not enough if different transaction managers or propagations prevent operations from sharing the transaction. Verify the actual configuration of `JobRepository` and the transaction manager.

## 6. When JobRepository Uses a Different Database

Some systems store business data in one database and Spring Batch metadata in a separate database. In that setup, a local transaction manager cannot atomically commit both databases together.

Example:

~~~text
Transaction A: business database
  - INSERT processed_order
  - COMMIT

Transaction B: batch metadata database
  - UPDATE StepExecution
  - UPDATE ExecutionContext
  - COMMIT
~~~

If the process stops after commit A but before commit B, the business database already holds the results while the checkpoint stays old. On restart, the chunk may re-execute.

If commit B happens before commit A, restart may skip items whose business data was never saved. Exact ordering depends on transaction orchestration, but when two resources are not atomic, never assume method call ordering eliminates every crash window.

Common mitigation strategies:

- Put `JobRepository` and the business writer on the same transactional resource if architecture permits.
- Make writers idempotent by business key.
- Use unique constraints to block duplicate inserts.
- Record processing status by source key in the business database.
- Run reconciliation after crashes.
- If multi-resource atomicity is truly required, evaluate XA/JTA and its operational costs before adopting it.

## 7. Same JobInstance on Restart

Restarting means resuming a failed or stopped `JobInstance`, not launching a brand-new instance.

A `JobInstance` is identified by job name and identifying `JobParameters`. On restart:

- Keep identifying parameters unchanged.
- Spring Batch creates a new `JobExecution` for the same `JobInstance`.
- `JobRepository` supplies the persisted execution context from the previous run.
- Steps can resume from committed state, depending on restartability and flow configuration.

If you add a new identifying parameter such as a run timestamp or increment `run.id`, you usually create a new `JobInstance`. The reader then starts from the beginning and output identities may also change.

A `JobInstance` that is already `COMPLETED` normally cannot be relaunched with the same identifying parameters as a fresh run. To reprocess intentionally, create a new instance using an output version or appropriate identifying parameter.

## 8. A New JobExecution Does Not Mean Reading from Scratch

Each restart creates a new `JobExecution` belonging to the same `JobInstance`. This distinguishes the initial run from restart attempts in metadata while keeping the job's logical identity intact.

Example:

| Attribute | First run | Restart run |
|---|---|---|
| `JobInstance` | `orders:businessDate=2026-11-15` | Same instance |
| `JobExecution` | ID 501 | ID 502 |
| `StepExecution` | ID 701 | New ID |
| Checkpoint | After item 200 | Restores checkpoint after item 200 |
| Output identity | Same output key | Same output resource/state |

IDs in the table are illustrative. What matters is that `JobExecution` ID changes while identifying parameters stay unchanged so `JobInstance` stays the same.

Do not use `JobExecution` ID as the sole output filename if a restart must resume the exact file from the previous run. You can record the execution ID in logs or manifests for auditing.

## 9. Readers Must Persist State to Restart

Stateful readers must support `ItemStream`. In the lifecycle:

- `open(context)` opens resources and restores position.
- `read()` returns the next item.
- `update(context)` saves the current position/checkpoint.
- `close()` releases resources.

Example custom reader saving an offset:

~~~java
public class OffsetOrderReader
        implements ItemStreamReader<Order> {

    private static final String OFFSET_KEY = "orderReader.offset";
    private int offset;

    @Override
    public void open(ExecutionContext context) {
        offset = context.containsKey(OFFSET_KEY)
                ? context.getInt(OFFSET_KEY)
                : 0;
    }

    @Override
    public Order read() {
        Order order = readAt(offset);
        if (order != null) {
            offset++;
        }
        return order;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(OFFSET_KEY, offset);
    }

    @Override
    public void close() {
        // Close resources if the reader opened any.
    }
}
~~~

This is a conceptual example. Offset positioning is only safe if the source has a stable order and each offset always points to the exact same item across restarts. For database queries, prefer a stable, unique sort key rather than relying on non-deterministic row ordering.

## 10. saveState and Reader Names

Built-in readers typically expose a `saveState` setting. When enabled, the reader stores state in `ExecutionContext` to resume after checkpoints:

~~~java
new JdbcPagingItemReaderBuilder<Order>()
        .name("orderPagingReader")
        .dataSource(dataSource)
        .selectClause("select order_id, amount")
        .fromClause("from source_order")
        .sortKeys(Map.of("order_id", Order.ASCENDING))
        .pageSize(100)
        .rowMapper(orderRowMapper)
        .saveState(true)
        .build();
~~~

The reader name must stay stable across runs of the same `JobInstance` because it is used to build keys in `ExecutionContext`. Changing `name` can prevent the reader from finding old state and cause it to start from the default position.

If multiple instances of the same reader type exist in one step, give each reader a distinct name so states do not overwrite each other. When using delegates or composites, ensure streams are registered and opened/closed properly.

## 11. JdbcPagingItemReader and Stable Sort Keys

For large databases, `JdbcPagingItemReader` reads page by page and persists position state for restart. It requires a deterministic, stable, and ideally unique sort key.

Example:

~~~sql
select order_id, customer_id, amount
from source_order
where status = 'READY'
order by order_id
~~~

If `order_id` is unique and immutable, the reader can continue after the last read key. If the sort key is not unique, multiple rows sharing the same key can blur page boundaries and risk missing or duplicating rows depending on the query provider.

Never use `ORDER BY` on a column with duplicate values without a tie-breaker. You can use a composite sort key, such as `created_at` and `order_id`, if supported properly by the reader/query provider API.

## 12. The Data Source Must Stay Stable Across Restarts

A checkpoint represents a position within a specific dataset. If the source changes between the initial run and restart, the same position can refer to different records.

Example:

- Initial query returns IDs 1-1000.
- The job commits up to ID 500.
- The source inserts a record with ID below 500 or changes status filter values.
- Restart resumes from the checkpoint, but the dataset no longer matches the initial run.

Results can miss new records, duplicate old ones, or shift order. Pin the input snapshot:

- Use a fixed business date/cutoff.
- Select the record set via a snapshot ID or high-water mark.
- Keep input files immutable.
- Use a staging table for the list of keys to process.
- Store a source version/checksum and verify it on restart.

When business queries filter on mutable statuses like `READY`/`PROCESSED`, pay special attention if the writer updates the source table itself, because that can alter the query results used by the reader.

## 13. Reading and Updating the Same Table

A common pattern reads rows with status `READY` and has the writer update them to `PROCESSED`:

~~~sql
select order_id, amount
from source_order
where status = 'READY'
order by order_id
~~~

~~~sql
update source_order
set status = 'PROCESSED'
where order_id = :orderId
~~~

As chunks commit, processed rows drop out of the `READY` filter. If the reader uses offset pagination or unstable page queries, the result set can shift and skip records.

A more stable strategy:

- Use keyset paging on an immutable ID.
- Capture a high-water mark at the start of the job.
- Query rows with ID greater than the last key and at most the high-water mark.
- Or claim a batch of records via an explicit transactional status/claim token.

Keyset example:

~~~sql
select order_id, amount
from source_order
where order_id > :lastOrderId
  and order_id <= :highWaterMark
order by order_id
fetch first 100 rows only
~~~

Row-limiting syntax depends on the database. The idea is fixing both order and source boundaries so offsets do not shift as processed rows leave the filter.

## 14. JdbcBatchItemWriter and Chunk Transactions

`JdbcBatchItemWriter` uses `NamedParameterJdbcTemplate` to write multiple items in a batch. When the writer uses a `DataSource` managed by the step's transaction manager, updates join the chunk transaction:

~~~java
@Bean
public JdbcBatchItemWriter<ProcessedOrder> processedOrderWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ProcessedOrder>()
            .dataSource(dataSource)
            .sql("""
                    insert into processed_order(order_id, amount)
                    values (:orderId, :amount)
                    """)
            .beanMapped()
            .assertUpdates(true)
            .build();
}
~~~

If the writer throws an exception before commit, the chunk transaction can roll back database changes in that chunk. On restart, checkpoints must not advance past uncommitted chunks.

For this behavior to work, the writer must use the right transactional resource. If the writer opens its own standalone connection outside the transaction, the database can commit independently of `JobRepository` and reader checkpoints.

## 15. Same Database Does Not Always Mean Same Transaction

Two beans can point to the same database server yet still fail to share the same transaction:

- Using two separate `DataSource` pools.
- Using two independent transaction managers.
- An operation opening a new connection not enlisted in the current transaction.
- Using `REQUIRES_NEW` propagation on a write operation.
- The writer calling a stored procedure or service that commits internally.

Therefore, check the transaction manager passed to `StepBuilder`, the writer's `DataSource`, and `JobRepository` configuration. Pay close attention to propagation on services invoked from processors or writers.

If a service uses `REQUIRES_NEW` to commit business data before the chunk transaction completes, a later exception can roll back chunk metadata without rolling back the separately committed business transaction. That causes duplicates on restart unless the operation is idempotent.

## 16. Commit Order and Crash Windows

A crash can occur at several points:

| Crash point | Expected outcome if sharing one transaction |
|---|---|
| Before writer writes | No business write or chunk checkpoint |
| While writer writes, before commit | Transaction rolls back during connection recovery |
| After writer writes, before transaction commit | Neither business write nor checkpoint is committed |
| After transaction commit | Chunk's business writes and checkpoint are durable |
| After commit, before job transitions to `COMPLETED` | Chunk remains committed; job execution may need restart/recovery |

Distinguish clearly: committing a chunk does not mean the entire job is `COMPLETED`. The job can stop after one committed chunk and before subsequent chunks or later steps. Restart resumes from the step's checkpoint.

If `JobRepository` and the business writer sit on two separate transactional resources, a crash window opens between the two commits. In that setup, idempotency and reconciliation are mandatory rather than assuming the chunk transaction spans both.

## 17. Idempotent Writers Are an Essential Safety Layer

Even when transactions are configured properly, idempotency remains valuable for scenarios such as:

- Intentional job re-runs.
- Duplicate input delivery.
- Side effects outside the database transaction.
- Writers integrating with APIs or non-transactional storage.
- Metadata and business databases not sharing a transaction.
- Operators recovering an execution from an indeterminate state.

An idempotent operation means executing the same business operation again does not create duplicate or corrupted outcomes. A common technique uses a stable business key and unique constraint:

~~~sql
create table processed_order (
    order_id bigint primary key,
    amount decimal(18, 2) not null,
    processed_at timestamp not null
);
~~~

The unique key prevents one order from being inserted twice. However, a duplicate key can fail the writer; the application must decide whether that represents a real error or indicates the item was already processed.

## 18. Upserts and Deliberate Duplicate Handling

Some databases support upserts or equivalent statements. For example, SQL in a specific dialect may use `ON CONFLICT`:

~~~sql
insert into processed_order(order_id, amount)
values (:orderId, :amount)
on conflict (order_id)
do update set amount = excluded.amount
~~~

Upserts prevent repeated execution from creating extra rows. Yet not every duplicate should blindly overwrite:

- If payloads match, it can be treated as a valid replay.
- If payloads differ, overwriting may hide a data conflict.
- If downstream already consumed the record, updating in place can alter history.

Another pattern is insert-if-absent or conflict-do-nothing, followed by verifying whether the existing record has the same payload/checksum. Pick semantics aligned with the business contract and target database.

## 19. Processing Ledger Table by Source Key

For file or API imports, you can store source identity and record key:

~~~sql
create table batch_processed_record (
    source_id varchar(200) not null,
    record_key varchar(200) not null,
    payload_hash varchar(64) not null,
    processed_at timestamp not null,
    primary key (source_id, record_key)
);
~~~

When writing a record:

1. Compute a stable `source_id` for the file/snapshot/API batch.
2. Use the record's business key.
3. Store a payload hash or version to detect same-key different-content collisions.
4. Insert within the same transaction as the business result.
5. If the key already exists, compare the payload hash and handle per duplicate policy.

This table acts as a deduplication ledger. Never use `JobExecution` ID as `source_id` when restarts create new executions that must recognize the same input.

## 20. Reader Checkpoints and Writer Idempotency Complement Each Other

Checkpoints avoid re-reading already-committed data when the reader preserves state properly. Idempotency protects the system when an item is re-delivered or when checkpoints cannot stay strictly atomic with business side effects.

The two mechanisms do not replace one another:

- Checkpoints do not prevent duplicates from re-delivering sources or fresh reprocessing runs.
- Idempotency does not help the reader resume at the right offset and could force the job to reprocess huge amounts of data unnecessarily.
- Sharing a transaction makes business writes and checkpoints commit atomically.
- Idempotency guards against retries, replays, or non-uniform transaction boundaries.

A resilient design usually combines all three: stable input sources, transaction-aware checkpoints, and idempotent writers.

## 21. How Does Chunk Size Affect Restart?

Chunk size determines how many items are processed within a single transaction:

~~~java
.chunk(100, transactionManager)
~~~

Small chunks:

- Shorter transactions.
- Fewer items rolled back on failure.
- More commits and metadata updates.
- Potentially lower throughput due to transaction overhead.

Large chunks:

- Fewer commits.
- Potentially higher throughput for suitable workloads.
- Locks held longer by transactions.
- Higher memory consumption.
- More items to reprocess on rollback.

Chunk size does not change the checkpoint rule: state is considered advanced past a chunk only when the transaction commits successfully as configured. Choose chunk size based on latency, locking, memory, batch throughput, and recovery cost.

## 22. Writers Must Not Commit Each Item Outside the Chunk

A custom writer might be tempted to open a connection and commit every single item:

~~~java
for (Order order : chunk) {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        save(order, connection);
        connection.commit();
    }
}
~~~

This detaches each item from the chunk transaction. If item 80 fails, the prior 79 items may already be committed while chunk metadata was never updated. A restart may re-send the whole chunk and create duplicates.

In a chunk-oriented step, prefer JDBC operations that join the active transaction. Never manually open/commit separate connections unless you have an explicit design for partial commits, idempotency, and reconciliation.

## 23. Transaction Propagation in Services Called by the Writer

If the writer invokes a service with its own transaction annotations, understand propagation:

- `REQUIRED` normally joins the existing transaction if one is active.
- `REQUIRES_NEW` creates an independent transaction and suspends the current one.
- `NOT_SUPPORTED` can run outside the active transaction.
- `SUPPORTS` joins if a transaction exists, otherwise runs non-transactionally.

A service saving business rows under `REQUIRES_NEW` can commit before the chunk transaction commits. If the writer subsequently fails, the outer transaction rolls back while the business rows remain persisted.

Keep chunk writes inside the same transaction whenever checkpoints and business writes must commit together. If independent commits are required, treat them as repeatable side effects and design explicit idempotency.

## 24. Database Triggers and Stored Procedures

A JDBC writer can fire triggers or invoke stored procedures. Identify all changes the database performs:

- Does the trigger write to another table inside the same database transaction?
- Does the procedure call external systems or commit independently?
- Are autonomous transactions or equivalents used?
- Does the procedure emit messages or update non-rollbackable state?
- Do retries create duplicate side effects?

Changes inside the same database transaction normally roll back with the calling transaction. However, if a procedure triggers out-of-transaction side effects or autonomous commits, checkpoints cannot shield those side effects.

Restart tests should cover the real behavior of triggers and procedures, not just the writer's SQL statement.

## 25. Handling Failures After Commits Before Job Completion

A job can commit several chunks and then fail on a later chunk:

~~~text
Chunk 1 -> COMMIT
Chunk 2 -> COMMIT
Chunk 3 -> WRITE ERROR -> ROLLBACK
JobExecution -> FAILED
~~~

When restarting the same `JobInstance`:

- The first two chunks are preserved.
- The failed chunk is reprocessed from the checkpoint.
- The reader must resume at the position corresponding to the last committed chunk.
- The writer must not create duplicates for already-committed data.

This is the standard restart scenario. There is no need to delete data from chunks 1 and 2 when transactions and checkpoints were saved properly and the job is designed to resume.

If business logic demands all-or-nothing across the entire job, chunk transactions alone are insufficient because earlier chunks already committed. Write into a staging/isolated version and publish results only after all steps succeed.

## 26. Restarting After a Process Kill

When a JVM or host is killed abruptly, `finally` blocks and close callbacks may not run. The database recovers open transactions through its own recovery mechanism, while metadata may reflect an unfinished execution.

When operating a restart:

1. Identify the `JobInstance` and latest `JobExecution`.
2. Verify open database transactions have completed recovery.
3. Inspect execution status in `JobRepository`.
4. Determine whether the execution is still considered running or marked failed/stopped.
5. Use the approved operational mechanism to stop or recover stale executions before restarting.
6. Restart with the same identifying parameters once status permits.
7. Verify business data and checkpoints after the re-run.

If metadata remains `STARTED` because the process died before updating status, launching with the same parameters may be rejected because an execution appears active. Do not ad-hoc edit metadata tables with raw SQL. Use `JobOperator` or your organization's approved recovery procedures compatible with your version and repository schema.

## 27. JobRepository Metadata Is Not a Business Ledger

`JobRepository` tracks operational state: job/step executions, execution contexts, read/write/commit/rollback counts, and restart metadata. It does not replace business tables for proving an order was processed per business contract.

For example:

- `StepExecution` `writeCount = 1000` shows the writer wrote that many items per step metrics.
- It does not automatically prove downstream records still exist, were unmodified, or were acknowledged by external systems.
- `JobExecution` `COMPLETED` does not prove out-of-transaction side effects were confirmed.

When business auditing is required, record business keys, source identities, payload versions, and outcomes in a dedicated table or manifest. Use `JobRepository` to coordinate lifecycle and restart, and use a business ledger for business reconciliation.

## 28. ExecutionContext Should Store Only Necessary Restart State

`ExecutionContext` should hold small, serializable data meaningful for recovery:

- Last processed ID or sort key.
- File byte offset or line number.
- Page number or token.
- Current resource index.
- Input checksum or version.
- Small state for custom readers/writers.

Do not store:

- Entire lists of already-read items.
- Connections, streams, or non-serializable objects.
- Exception objects or sensitive payloads.
- Large caches as a substitute for a database.
- Random state that cannot be reconstructed.

If state requires substantial data, persist it in a staging/ledger table and keep only the key/version in `ExecutionContext`.

## 29. saveState(false) and Its Consequences

Some readers/writers allow disabling state persistence:

~~~java
.saveState(false)
~~~

This can be appropriate if a step does not need restart or the component is designed to safely restart from the beginning. However, if a step must resume after commits, disabling state can cause the reader to start over from scratch or fail to restore the expected position.

If the reader starts over from the beginning, the writer must have idempotent semantics. If the writer is not idempotent, restart can create duplicates. If the output is a file, understand whether the writer truncates, appends, or restores the resource.

Do not mechanically enable `saveState` on non-restartable components; likewise, do not disable it when the workflow depends on checkpoints. Check the contract of each reader/writer.

## 30. JdbcCursorItemReader and Restart

`JdbcCursorItemReader` holds a JDBC cursor while reading. On restart, the reader must restore position from saved state and the query must return data in the exact same order.

Notes:

- The query must have a deterministic `ORDER BY`.
- Prefer a unique sort key.
- Do not change query parameters across restarts.
- Do not let the writer mutate the result set in a way that shifts the cursor/checkpoint.
- Verify driver/database behavior with cursors and transactions.
- Use a stable reader name and `saveState` as needed.

For very large datasets or mutating sources, key-based paging can be easier to control than cursors/offsets, depending on workload and database.

## 31. JdbcPagingItemReader and High-Water Marks

A paging reader can save page sort keys to resume. However, if the source continuously receives new records, the job might lack a stable endpoint or pick up new data outside the initial scope.

One pattern captures a high-water mark at job start:

~~~sql
select max(order_id) from source_order
~~~

Then every page uses:

~~~sql
where order_id > :lastOrderId
  and order_id <= :highWaterMark
order by order_id
~~~

Row-limiting syntax depends on the database. The idea is fixing ordering and source boundaries so offsets do not shift when processed rows drop out of filters.

The high-water mark must be persisted as an identifying job parameter or appropriate execution state so restarts reuse the exact same value. Recomputing max ID on restart can expand the input scope.

If older records can be updated or deleted, an ID high-water mark does not form a complete snapshot. Use snapshot isolation, a staging key table, or versioned sources as required.

## 32. StepExecution Metrics After Restart

After a restart, each `StepExecution` is a new execution; metrics on the current execution must be interpreted in the context of the `JobInstance` and previous executions.

Do not simply sum or compare a single count field without considering restart semantics. To verify business outcomes:

- Check the status of each execution.
- Identify the last committed checkpoint.
- Query business keys in the output table.
- Check duplicate counts by business key.
- Reconcile against input item counts in the snapshot.
- Inspect skip/filter counts and error ledgers.

Metrics support operations and observability, while business reconciliation confirms the final dataset is accurate.

## 33. Restartability of Steps and Flows

Not every step restarts the same way. Steps with non-idempotent side effects or no state may need redesigning.

Questions to answer:

- Is the step allowed to re-run after failure?
- Is an already `COMPLETED` step skipped when the job restarts?
- Is `allowStartIfComplete` set on steps meant to re-run intentionally?
- Do flow transitions on `ExitStatus` accidentally skip needed steps?
- Do downstream steps depend on staging outputs from upstream steps?
- When one partition fails, are succeeded partitions preserved and reused?

Never enable `allowStartIfComplete` just to work around restart errors. It can cause already-completed steps to re-run and create duplicate side effects if not idempotent.

## 34. Reprocessing Differs from Restart

Restart resumes a failed/stopped `JobInstance` using the same identifying parameters and saved checkpoints.

Reprocessing re-runs data under a new business request. It typically requires:

- A new `JobInstance` or new output version.
- Defining the input snapshot/version.
- A policy for handling existing records.
- Upsert/versioning or per-run output tables.
- A process for publishing the new output.

Do not increment `run.id` just to restart a failed job; doing so creates a new instance and reads from the beginning. Conversely, do not attempt to restart a `COMPLETED` instance to perform a fresh reprocessing run.

## 35. Transaction Isolation and Mutating Source Data

Isolation level governs what the reader sees inside a transaction. In long-running jobs, many chunks commit over time; each chunk can observe a different snapshot depending on the database and isolation.

Potential issues:

- New records inserted between two chunks.
- `READY` records updated to `PROCESSED` by another process.
- Sort keys or filter columns modified.
- Rows deleted before the reader reaches them.
- Restarts executing against a different snapshot than the first run.

If you need to process an exact fixed dataset, define an input snapshot or claim set upfront. Never assume per-chunk transactions preserve one snapshot across the whole job.

## 36. Claiming Records and Multiple Concurrent Jobs

When multiple jobs can read the same source table, two jobs could pick up the same `READY` record. A claim strategy is needed:

- Update status/claim token in a transaction before processing.
- Use database-appropriate locking, such as `SKIP LOCKED` if supported and semantically sound.
- Partition by non-overlapping keys.
- Use a staging table with unique keys for job/source identity.
- Use lease/claim expiry to recover records held by crashed workers.

Claim operations must be atomic so two jobs never claim the same record. On job restart, determine whether old claims are still valid or expired and safe to reclaim.

Do not rely only on output suffixes or `JobExecution` IDs to avoid two jobs processing overlapping inputs. Input ownership must be enforced at the database or orchestration layer.

## 37. Transactional Outbox for External Side Effects

If an event must be emitted after writing to the database, do not call a message broker directly inside the writer assuming database rollback will roll back the message on chunk failure.

Transactional outbox pattern:

1. Within the chunk transaction, write business rows.
2. Within that same transaction, insert an outbox event with a stable event ID.
3. Commit the database.
4. A separate publisher reads the outbox and sends messages.
5. The publisher marks events sent or consumers deduplicate by event ID.

If the process dies after database commit but before sending the message, the outbox retains the event for the publisher to pick up. If the publisher sends successfully but dies before marking sent, it may re-send; consumers must be idempotent.

This solves the crash window between database commits and out-of-transaction side effects that Spring Batch checkpoints cannot solve on their own.

## 38. Restart with Both Database Writer and File Writer in One Step

If a single chunk writes both a database and a file, verify whether both resources join the transaction. Database transactions do not automatically roll back normal file writes.

Example:

- Writer writes to the database successfully.
- Writer writes partially to a file.
- The chunk hits an error.
- The database rolls back, yet the file already received bytes.

Or conversely, the database commits while file flushing fails to finish. On restart, the file can fall out of sync with database tables.

Mitigations:

- Write staging files per chunk or per step, then publish after database/job completion.
- Treat the database as source of truth and generate files in a separate repeatable step.
- Write files using business-key/idempotent artifact strategies.
- Use manifests/checksums to verify complete output.

Do not treat placing a database writer and file writer inside a `CompositeItemWriter` as a distributed transaction.

## 39. Restart with Stored Procedures Updating Multiple Tables

A stored procedure can write multiple tables in one call. If all operations participate in the active JDBC transaction, rollback can undo those changes. Still, verify:

- Does the procedure commit internally?
- Does it call external services?
- Does it write audit rows using autonomous transactions?
- Does it update sequences/counters outside rollback semantics?
- Is the procedure idempotent when re-invoked with the same business key?

Restart tests must inspect the final state of all affected tables, not just the primary table. A stored procedure can leave hidden side effects invisible to writer unit tests.

## 40. Handling Duplicate Keys After Restart

If a restart re-sends already-committed items due to uncoordinated transactions/resources, unique constraints can catch duplicates. That is a useful signal, but it needs a policy:

- If the row already exists with identical payload, verify and treat as already processed if contract permits.
- If the row already exists with a different payload, raise a conflict.
- If duplicates stem from duplicate source records, log to an error ledger.
- If duplicates stem from retry after timeout, use an idempotency key to distinguish.

Never catch `DuplicateKeyException` and ignore everything indiscriminately. Doing so can hide business data conflicts or broken constraints.

## 41. Test Example: Restart After a Chunk Commits

An integration test should simulate:

1. Reader supplies items with stable business keys.
2. Writer persists the first chunk to the database.
3. The first chunk commits.
4. A test double forces a later chunk to fail intentionally.
5. The first `JobExecution` ends with status `FAILED`.
6. Restart with identical identifying parameters.
7. Reader resumes from the committed checkpoint.
8. Writer persists the remaining items.
9. Query the database and verify each business key has exactly one result.

You can use a writer test double or a processor throwing on a specific key for controlled failure. Do not use sleeps or timing races hoping the process stops right after commit.

## 42. Example: Verifying Business Rows After Restart

Once restart completes, tests should inspect actual database rows:

~~~java
List<Long> orderIds = jdbcTemplate.queryForList(
        "select order_id from processed_order order by order_id",
        Long.class);

assertEquals(List.of(1001L, 1002L, 1003L, 1004L), orderIds);

Integer duplicates = jdbcTemplate.queryForObject("""
        select count(*)
        from (
            select order_id
            from processed_order
            group by order_id
            having count(*) > 1
        ) duplicate_orders
        """, Integer.class);

assertEquals(0, duplicates);
~~~

This example assumes `order_id` is a unique business key and the database supports this query form. In real schemas, inspect payloads/versions too, not just row counts.

## 43. Verifying JobRepository State

Integration tests can also verify metadata:

- Both executions share the same `JobInstance`.
- The first `JobExecution` is `FAILED` or the status matching the injected failure.
- The restarted `JobExecution` has a new ID.
- The restarted `StepExecution` uses the persisted checkpoint.
- `ExecutionContext` holds expected reader/writer state.
- The final step finishes `COMPLETED`.

Avoid coupling too tightly to internal key names generated by framework readers unless part of the public contract. For custom readers, you can assert application-defined keys. For built-in readers, prioritize verifying behavior via resumed items and final output.

## 44. Testing Commit Boundaries with Failure Injection

To verify transactions, inject failures at key points:

- Before the writer.
- After the writer calls JDBC, before chunk commit.
- After one chunk commits and before the next chunk.
- Inside `ItemStream.update`.
- In the final step when `JobExecution` transitions status.

The goal is proving business data and checkpoints commit/roll back together per transaction design. Failure injection must be deterministic, such as a test double with a counter or hook enabled via test configuration.

Avoid adding production code purely to test a timing window when a test double or transaction synchronization can be used. Tests must check database contents and checkpoints after failure, not merely assert an exception was thrown.

## 45. Handling Stale Executions After a Crash

When a process dies, metadata may still read `STARTED`. Before restarting, operators should check:

- Has the old process genuinely stopped?
- Are any workers/partitions still running?
- Has the database finished recovering open transactions?
- Are incomplete staging resources left behind?
- Was the last execution context committed?
- Are any out-of-transaction side effects in an indeterminate state?

Never mark executions `FAILED` via direct SQL in production unless following an explicitly designed and controlled recovery procedure. Corrupting metadata can break `JobRepository`'s restart coordination.

## 46. Restarts and File/Database Output Versions

If a job produces both database data and file artifacts, tie them to the same output identity:

~~~text
jobKey = orders:2026-11-15:tenant-42:v1
database batch_key = orders:2026-11-15:tenant-42:v1
staging file = orders-2026-11-15-tenant-42-v1.tmp
published file = orders-2026-11-15-tenant-42-v1.csv
~~~

Restarting the same `JobInstance` resumes that staging artifact and database batch key. Intentional reprocessing creates a new version. Downstream consumers read published outputs only after verifying database/file/manifest alignment.

## 47. Common Pitfalls

| Scenario | Cause | Resolution |
|---|---|---|
| Restart writes duplicate rows | Business writes committed separately from checkpoints or reader restarted from scratch | Share transactional resource, save state, and make writer idempotent |
| Restart skips items | Checkpoint committed before business data or input changed | Synchronize transactions and pin input snapshot |
| Job creates a new `JobInstance` on restart | Added a new identifying parameter/run ID | Reuse the original identifying parameters |
| Reader re-reads entire file | `saveState` disabled or reader does not save state | Enable state and implement `ItemStream` properly |
| Reader skips records while paging | Non-unique sort key or changing query | Use stable unique keys/high-water marks |
| Data committed yet job remains `FAILED` | Job failed in a chunk/step after prior commits | Restart from checkpoint; do not delete committed chunks |
| Database rolled back yet API was still called | API side effect outside transaction | Use idempotency keys, outbox, or reconciliation |
| Same database yet checkpoints diverge | Writer opened a separate connection/transaction | Check `DataSource`, transaction manager, and propagation |
| Restart refuses to start execution | Metadata stuck in `STARTED` after process crash | Use proper recovery/`JobOperator` workflow |
| Large chunks must redo too many items | Chunk size too large for recovery cost | Tune chunk size against throughput and rollback cost |
| Reprocess overwrites old results | Reused business key/output path | Version outputs and define upsert rules |
| Duplicate keys silently ignored | Overly broad `DuplicateKeyException` catch | Compare payload/version and classify duplicates |
| Files out of sync with database | File writer not transactional with database | Stage, publish separately, and use manifests |
| Completed step re-runs unexpectedly | Misconfigured `allowStartIfComplete` or flow | Define explicit restart/reprocess semantics per step |

## 48. Process for Designing Restart After Database Commits

1. **Define transaction boundaries:** do the writer and `JobRepository` share the same transaction manager/resource?
2. **Inspect the writer:** does its JDBC connection join chunk transactions or commit on its own?
3. **Enable checkpoints:** do readers/writers support `ItemStream` and `saveState` appropriately?
4. **Keep component names stable:** reader/writer names never change across restarts.
5. **Preserve `JobInstance`:** restarts reuse identical identifying `JobParameters`.
6. **Stabilize inputs:** keep files, queries, high-water marks, and sort order consistent with checkpoints.
7. **Design business keys:** unique constraints or deduplication ledgers guard against double writes.
8. **Handle external side effects:** use outbox/idempotency/staging rather than assuming distributed rollback.
9. **Control chunk size:** balance commit overhead, locking, and recovery cost.
10. **Document crash recovery:** define procedures for stale executions and partial outputs.
11. **Test failures after commits:** restart the same instance and verify zero missing or duplicate records.
12. **Reconcile results:** verify business rows, checkpoints, error ledgers, and output manifests.

## 49. Key Principles to Remember

- Restart resumes a `JobInstance` with a new `JobExecution`; reuse identifying `JobParameters`.
- Chunk commits cover both business data and checkpoints when they participate in the same transaction.
- `JobRepository` stores metadata and `ExecutionContext`; it does not replace a business ledger.
- Readers/writers must persist state via `ItemStream` if resuming at an exact position is required.
- Keep reader names, writer names, input resources, queries, sort keys, and rollover configuration stable across restarts.
- Sharing a database server does not guarantee sharing a transaction; verify `DataSource`, transaction manager, and propagation.
- If `JobRepository` and business writers sit on separate resources, address crash windows with idempotency and reconciliation.
- `JdbcPagingItemReader` needs a stable, ideally unique sort key; input queries must have fixed scope.
- Avoid reading and updating the same table in ways that shift the result set; consider keyset paging, high-water marks, or claim sets.
- Unique constraints, business keys, and payload hashes detect or handle intentional duplicates.
- Upserts must not overwrite conflicting payloads without an explicit business rule.
- Chunk size governs transaction and recovery cost, not total job item count.
- Never commit individual items outside the chunk if checkpoints and business writes must be atomic.
- Out-of-transaction side effects require outbox, idempotency keys, staging, or reconciliation.
- Restart differs from reprocessing; reprocessing needs a new output identity/version and a policy for existing data.
- After crashes, execution metadata can become stale; follow controlled recovery procedures.
- Tests must inject failures deliberately, restart the same `JobInstance`, and verify real data has zero losses or duplicates.

Restarting after a database commit is safe when business data state and checkpoints are managed consistently. Use the same transactional resource for JDBC writers and `JobRepository` whenever possible, keep input sources stable, persist reader state accurately, and guard business keys with idempotency. For side effects outside the transaction, add an outbox, staging, or reconciliation so jobs recover without creating duplicates or dropping data.
