# Processing Large Datasets in Batches and Keeping Transactions Properly Sized

## 1. Why Split Large Datasets into Batches?

A Spring Data JDBC application may start with small operations: saving one customer, updating one order, or loading an aggregate by ID. As the system grows, the application may need to:

- Import hundreds of thousands of customers from files.
- Synchronize data from an external system.
- Update statuses for a large volume of orders.
- Generate daily or periodic aggregated data.
- Reprocess failed records after a deployment.
- Run maintenance jobs or backfill historical data.

Loading an entire dataset into a single `List`, processing everything, and calling `saveAll` once can consume excessive heap, hold long transactions, and generate huge SQL volume. Committing after every single record, on the other hand, inflates transaction start/commit overhead.

The standard solution is **batch processing**: read a group of records, process that group, write the data, and finish the transaction; then move on to the next group.

However, in JDBC several distinct concepts share the word "batch". Distinguish carefully between:

1. **Batch SQL:** how many executions of the same prepared statement are grouped together to reduce round trips.
2. **Application chunk:** how many items the application reads and processes in one pass.
3. **Transaction chunk:** how many items are written within one transaction before committing.

These three sizes may be equal, but they do not have to be. Setting SQL batch size to 500 does not make a transaction commit automatically every 500 items. Looping 500 items at a time also does not create separate transactions if the entire loop sits inside one outer transaction.

This lesson explains how to process large datasets in Spring Data JDBC, choose the right APIs for aggregates and repeated SQL, read data via streams or pages, scope transactions per chunk, and manage errors, checkpoints, and performance.

## 2. Distinguishing the Three Size Concepts

Suppose a job imports 100,000 customers.

| Concept | Example | Effect |
| --- | ---: | --- |
| Application chunk size | 500 customers | Limits objects retained in heap and items processed per pass. |
| JDBC batch size | 100 identical UPDATEs | Reduces network round trips to the database. |
| Transaction size / commit interval | 500 customers | Limits changes committed or rolled back together. |

One implementation might:

- Read 500 customers into one chunk.
- Write them using one or more JDBC batches of 100 statements each.
- Commit the transaction after all 500 customers are written.

Here, the JDBC batch size is 100 while the transaction size is 500.

~~~text
Read source
   |
   v
Application chunk: 500 items
   |
   +--> JDBC batch 1: 100 statements
   +--> JDBC batch 2: 100 statements
   +--> JDBC batch 3: 100 statements
   +--> JDBC batch 4: 100 statements
   +--> JDBC batch 5: 100 statements
   |
   v
COMMIT chunk transaction
   |
   v
Read next chunk
~~~

If a chunk requires multiple statements per aggregate, actual statements can far outnumber items. For example, an order has one root row and 20 line items. Saving 500 aggregates can emit several thousand SQL operations.

Therefore, do not size chunks solely by aggregate root count. Also consider child row counts, statement counts, payload size, and per-item processing duration.

## 3. What Does saveAll Mean in Spring Data JDBC?

A repository extending `CrudRepository` provides:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

You can call:

~~~java
List<Customer> customers = loadCustomers();
customerRepository.saveAll(customers);
~~~

`saveAll(Iterable<S>)` persists the passed aggregates and returns the saved instances. In Spring Data JDBC, saving an aggregate includes all members belonging to that aggregate.

### 3.1. saveAll Has No Commit Interval Parameter

The `CrudRepository.saveAll` API does not accept a `batchSize` or `commitInterval` parameter. Thus, callers cannot ask the method to split an unbounded input into groups of 500 items automatically.

At the `JdbcAggregateTemplate` level, Spring Data JDBC provides `saveAll`, `insertAll`, and `updateAll` to handle multiple aggregates. The framework builds batched aggregate changes for the supplied instances. However, that does not mean you can pass an unbounded dataset without consuming memory, nor that internal groups automatically commit in separate transactions.

If the application already loaded 200,000 aggregates into a `List` before calling `saveAll`, object allocation and retention costs have already occurred before the repository runs. When per-chunk transactions are required, callers must bound each invocation's aggregate count and set transaction boundaries appropriately.

### 3.2. Saving Aggregates Can Emit Multiple SQL Statements

Spring Data JDBC persists by aggregate boundaries. For new aggregate roots, the framework inserts the root first and then inserts referenced entities. When saving an existing aggregate, the default strategy can delete referenced entities, update the root, and reinsert child entities according to the new aggregate state.

This means a `saveAll` call on 500 aggregates does not necessarily emit just 500 SQL statements. Cost also depends on the number of tables and child entities per aggregate.

If only one attribute changes per aggregate while aggregates hold large collections, evaluate the delete-and-reinsert cost. For simple bulk updates, a conditional SQL update statement may be more suitable, provided business rules permit bypassing the aggregate persistence pipeline.

### 3.3. When to Use saveAll?

`saveAll` is appropriate when:

- The set of aggregates is already bounded to a reasonable size.
- Every item must go through Spring Data JDBC mapping and persistence.
- Both roots and aggregate members must be saved.
- You want to preserve lifecycle callbacks, auditing, and optimistic locking from aggregate persistence.

If the source dataset is large, split it into chunks before calling `saveAll`. If you need to run a repeated UPDATE on many independent rows, consider `JdbcTemplate.batchUpdate`.

## 4. Splitting Aggregates into Chunks and Committing Each Chunk

Suppose a file contains new customers and each transaction should save at most 500 customers. You can separate source-reading coordination from transactional chunk writing across two beans.

### 4.1. Writer Processing One Chunk

~~~java
@Service
public class CustomerChunkWriter {

    private final CustomerRepository customers;

    public CustomerChunkWriter(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public void writeChunk(List<Customer> chunk) {
        customers.saveAll(chunk);
    }
}
~~~

Each call to `writeChunk` through the Spring proxy starts a transaction if no outer transaction exists. When the method finishes cleanly, the transaction commits. If an exception triggers rollback, all changes in that chunk roll back.

### 4.2. Coordinator Without an Enclosing Job-Wide Transaction

~~~java
@Component
public class CustomerImportCoordinator {

    private static final int CHUNK_SIZE = 500;

    private final CustomerChunkWriter writer;

    public CustomerImportCoordinator(CustomerChunkWriter writer) {
        this.writer = writer;
    }

    public void importCustomers(Iterator<Customer> source) {
        while (source.hasNext()) {
            List<Customer> chunk = new ArrayList<>(CHUNK_SIZE);

            for (int i = 0; i < CHUNK_SIZE && source.hasNext(); i++) {
                chunk.add(source.next());
            }

            writer.writeChunk(chunk);
        }
    }
}
~~~

The coordinator keeps only one chunk in memory at a time. Each call to the writer runs in its own transaction because the writer is a separate bean invoked through its proxy.

### 4.3. Why Not Put @Transactional on the Coordinator?

Suppose the coordinator has `@Transactional` and calls a writer annotated with `@Transactional` using the default `REQUIRED` propagation. The writer joins the existing transaction. Even if the coordinator calls the writer 200 times, all calls stay inside one single transaction.

~~~text
Coordinator @Transactional
  |
  +--> writeChunk(1)  REQUIRED: joins outer transaction
  +--> writeChunk(2)  REQUIRED: joins outer transaction
  +--> writeChunk(3)  REQUIRED: joins outer transaction
  |
  +--> COMMIT when coordinator finishes
~~~

To give each chunk its own transaction:

- Leave the coordinator non-transactional.
- Call a separate `@Transactional` writer bean per chunk.
- Or use `TransactionTemplate` to open and close a transaction for each unit of work.

In default proxy mode, self-invocation (one method calling another on the same object) bypasses the proxy. Placing the chunk writer on a separate bean keeps transaction boundaries clean.

### 4.4. When an Outer Transaction Is Unavoidable

If an outer transaction must exist for another reason, you can consider `Propagation.REQUIRES_NEW` on the writer. Spring suspends the outer transaction and opens an independent transaction for the chunk.

Do not use `REQUIRES_NEW` out of habit. The outer transaction still holds its connection/resources while the new transaction needs a second connection. With small pools and multiple threads, this can exhaust the connection pool. If the goal is merely per-chunk commits, a non-transactional coordinator is much simpler.

## 5. Using TransactionTemplate for Per-Chunk Transactions

Transactions can be controlled programmatically instead of via annotations:

~~~java
@Component
public class CustomerBatchWriter {

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactionTemplate;

    public CustomerBatchWriter(
            JdbcTemplate jdbc,
            TransactionTemplate transactionTemplate
    ) {
        this.jdbc = jdbc;
        this.transactionTemplate = transactionTemplate;
    }

    public void writeChunk(List<CustomerRow> chunk) {
        transactionTemplate.executeWithoutResult(status -> {
            jdbc.batchUpdate(
                    """
                    INSERT INTO customer_import (
                        external_id,
                        email,
                        status
                    )
                    VALUES (?, ?, ?)
                    """,
                    chunk,
                    chunk.size(),
                    (ps, customer) -> {
                        ps.setString(1, customer.externalId());
                        ps.setString(2, customer.email());
                        ps.setString(3, customer.status());
                    }
            );
        });
    }
}
~~~

Each call to `writeChunk` runs inside a transaction managed by `TransactionTemplate`. When the callback returns, the transaction commits. If an exception escapes the callback, the transaction rolls back according to the transaction manager's rules.

`TransactionTemplate` uses the configured transaction manager by default. Ensure the transaction manager manages the same `DataSource` used by `JdbcTemplate`.

`TransactionTemplate` is handy when:

- You want transaction boundaries explicitly visible in code.
- You need to execute multiple chunks inside one coordinator.
- You prefer not to rely on splitting beans to avoid self-invocation issues.
- You need per-step control over propagation, timeout, or isolation.

## 6. JDBC batchUpdate for Many Identical Statements

When many rows need the same SQL statement, JDBC batching reduces round trips between the application and database. Instead of sending an individual UPDATE per row, the driver can group multiple binds/executions into a batch.

Spring provides batch APIs on `JdbcTemplate` and `NamedParameterJdbcTemplate`.

### 6.1. BatchPreparedStatementSetter

Example updating inventory:

~~~java
public int[] updateInventory(List<InventoryRow> rows) {
    return jdbcTemplate.batchUpdate(
            """
            UPDATE inventory
            SET available = ?
            WHERE sku = ?
            """,
            new BatchPreparedStatementSetter() {

                @Override
                public void setValues(PreparedStatement ps, int index)
                        throws SQLException {
                    InventoryRow row = rows.get(index);
                    ps.setInt(1, row.available());
                    ps.setString(2, row.sku());
                }

                @Override
                public int getBatchSize() {
                    return rows.size();
                }
            }
    );
}
~~~

`getBatchSize` reports the number of parameter sets in the batch. `setValues` is called to bind values for each element. The return value is an array of affected row counts reported by the JDBC driver. Drivers may return `-2` when exact counts are not supplied.

### 6.2. NamedParameterJdbcTemplate

When SQL uses named parameters, you can construct a batch from a list of objects:

~~~java
public int[] updateInventory(List<InventoryRow> rows) {
    SqlParameterSource[] batch =
            SqlParameterSourceUtils.createBatch(rows);

    return namedParameterJdbcTemplate.batchUpdate(
            """
            UPDATE inventory
            SET available = :available
            WHERE sku = :sku
            """,
            batch
    );
}
~~~

Java properties must match named parameter names. This is concise when objects already expose matching getters/properties.

### 6.3. Splitting JDBC Batches into Smaller Batches

Spring also offers an overload taking a `Collection`, batch size, and `ParameterizedPreparedStatementSetter`:

~~~java
int[][] updateCounts = jdbcTemplate.batchUpdate(
        """
        UPDATE inventory
        SET available = ?
        WHERE sku = ?
        """,
        inventoryRows,
        100,
        (ps, row) -> {
            ps.setInt(1, row.available());
            ps.setString(2, row.sku());
        }
);
~~~

Here, Spring splits parameter sets into JDBC batches of at most 100 statements. The return value is a 2D array: each outer element corresponds to one batch, and each inner element holds affected row counts per statement.

### 6.4. Batch Size Is Not Transaction Size

The following snippet uses batch size 100:

~~~java
@Transactional
public void updateAll(List<InventoryRow> rows) {
    jdbcTemplate.batchUpdate(SQL, rows, 100, setter);
}
~~~

If `rows` has 10,000 items, Spring executes multiple JDBC batches in one call, yet the method still runs inside a single transaction because of `@Transactional`.

To commit every 500 rows, split input into 500-row chunks and invoke a separate transactional method per chunk. Inside each chunk, you can still use JDBC batch size 100:

~~~text
Transaction chunk: 500 rows
  JDBC batch 1: 100 statements
  JDBC batch 2: 100 statements
  JDBC batch 3: 100 statements
  JDBC batch 4: 100 statements
  JDBC batch 5: 100 statements
COMMIT
~~~

## 7. When to Use saveAll vs. batchUpdate?

The two APIs serve different requirements:

| Need | Suitable API |
| --- | --- |
| Save aggregate roots along with child entities | Repository `saveAll` or `JdbcAggregateTemplate.saveAll` |
| Insert multiple aggregates with pre-assigned IDs | `JdbcAggregateTemplate.insertAll` |
| Update multiple existing aggregates | `JdbcAggregateTemplate.updateAll` or repository `saveAll` per entity state |
| Run the same UPDATE on many independent rows | `JdbcTemplate.batchUpdate` |
| Import flat data without aggregate lifecycle | `JdbcTemplate.batchUpdate` or `NamedParameterJdbcTemplate.batchUpdate` |
| Bulk-update rows sharing a single predicate | One `UPDATE ... WHERE ...` SQL statement if semantics allow |
| Import job requiring restart, retry, skip, and checkpoints | Spring Batch chunk-oriented processing |

### 7.1. Caveats When Using Bulk SQL

An `@Modifying @Query` or `JdbcTemplate.update` runs raw SQL directly. It does not invoke aggregate persistence lifecycle callbacks or events. Auditing fields such as `@LastModifiedDate` or `@LastModifiedBy` are also not updated unless the SQL explicitly sets those columns.

Bulk SQL also bypasses domain methods and aggregate optimistic locking. If you use it, manually preserve invariants, versions, auditing, and required side effects. Only use bulk SQL when business rules can be safely expressed in that statement.

## 8. Reading Large Datasets via Pages or Streams

Chunked writes are not enough if the read step still loads the entire table into the heap.

### 8.1. Page and Slice

A repository can declare query methods accepting `Pageable`:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    Slice<Customer> findByStatus(
            CustomerStatus status,
            Pageable pageable
    );
}
~~~

The coordinator reads page by page:

~~~java
int pageNumber = 0;
int pageSize = 500;
Slice<Customer> slice;

do {
    Pageable pageable = PageRequest.of(
            pageNumber,
            pageSize,
            Sort.by("id").ascending()
    );

    slice = customerRepository.findByStatus(
            CustomerStatus.ACTIVE,
            pageable
    );

    processChunk(slice.getContent());
    pageNumber++;
} while (slice.hasNext());
~~~

`Page` usually requires an extra count query for total elements. `Slice` only needs to know whether a next page exists; Spring Data JDBC fetches one extra row to determine whether data continues.

With large datasets, if total page count is unnecessary, `Slice` avoids the count query cost.

### 8.2. Limitations of Offset Pagination

`PageRequest.of(pageNumber, pageSize)` typically produces offset-based queries. As `pageNumber` grows huge, the database has to skip many rows before returning the next page. If data changes while the job runs, offsets can also cause rows to repeat or be skipped.

### 8.3. Keyset Pagination

Keyset pagination uses the key of the last read row as the starting point for the next pass:

~~~sql
SELECT id, email, status
FROM customers
WHERE id > :lastId
ORDER BY id
LIMIT :limit;
~~~

Repository example with custom SQL:

~~~java
@Query("""
    SELECT id, email, status
    FROM customers
    WHERE id > :lastId
    ORDER BY id
    LIMIT :limit
    """)
List<Customer> findNextChunk(
        @Param("lastId") long lastId,
        @Param("limit") int limit
);
~~~

The coordinator updates the checkpoint after a chunk succeeds:

~~~java
long lastId = checkpoint.load("customer-import");

while (true) {
    List<Customer> chunk =
            repository.findNextChunk(lastId, 500);

    if (chunk.isEmpty()) {
        break;
    }

    writer.writeChunk(chunk);

    lastId = chunk.get(chunk.size() - 1).id();
    checkpoint.save("customer-import", lastId);
}
~~~

Keyset pagination works well when a deterministic, unique sort key exists. When sorting across multiple columns, the cursor must hold the full sort key, such as `(created_at, id)`, and SQL must handle rows sharing timestamps properly.

The example uses `LIMIT` syntax common in PostgreSQL/MySQL. Adjust pagination syntax for other databases.

## 9. Using Stream to Read Large Results

Spring Data JDBC supports query methods returning `Stream`:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    Stream<Customer> streamByStatus(CustomerStatus status);
}
~~~

Usage:

~~~java
try (Stream<Customer> customers =
        customerRepository.streamByStatus(CustomerStatus.ACTIVE)) {

    customers.forEach(this::process);
}
~~~

Spring Data JDBC delivers elements as they arrive from the database, reducing the need to build a `List` holding all results. However, a `Stream` holds a database connection open until closed. Always close streams with try-with-resources to prevent connection leaks.

### 9.1. Stream Does Not Mean Short Transactions

If processing 2 million rows in a stream inside a `@Transactional` method, the transaction can remain open for the entire traversal. This holds a connection and potentially holds snapshots/locks depending on isolation level.

Avoid HTTP calls, emails, or slow work while holding an open cursor. When reading and writing in chunks with per-chunk commits, keyset pagination usually makes transaction lifetimes easier to manage because each read closes before write transactions begin.

### 9.2. When to Use Stream?

`Stream` fits when:

- You want sequential processing while avoiding materializing an entire `List`.
- You can reliably close the stream.
- Holding a connection for the read duration is acceptable.
- Per-item processing logic is relatively short.

If you need checkpoints, resume, retries, or per-chunk commits, consider keyset pagination or Spring Batch.

## 10. Choosing Transaction Size

No single transaction size fits every database and workload.

### 10.1. Transactions Too Small

Committing after every single row:

- Spends excessive time starting and committing transactions.
- Increases round trips and synchronization overhead.
- Nullifies JDBC batching benefits.
- Can sharply increase total job runtime.

### 10.2. Transactions Too Large

Writing hundreds of thousands of rows in a single transaction:

- Holds connections and locks for a long time.
- Bloats undo/redo logs or WAL.
- Increases replication lag and I/O pressure.
- Increases timeout risk.
- Makes rollbacks expensive when failures occur.
- Risks losing huge progress from one late failure.
- Can hold too many objects and aggregate changes in JVM heap.

### 10.3. Sizing by Measurement

Start with a bounded trial size, such as 100, 250, or 500 items, and measure on production-like database and data.

Factors to weigh:

- Statements per aggregate.
- Child rows per aggregate.
- Data size per row.
- Indexes, triggers, and foreign keys.
- JDBC driver and its batching behavior.
- Business processing time per item.
- Concurrent transactions.
- Connection pool and database limits.
- Tolerance for rolling back a chunk.

Do not keep raising batch size solely because one small trial ran faster. Measure sustained throughput, p95/p99 transaction durations, lock waits, memory, log volume, and replication lag.

## 11. Spring Batch and Chunk-Oriented Processing

When jobs have operational requirements like restart, checkpoints, retries, skips, job repositories, and progress tracking, Spring Batch offers chunk-oriented processing.

Processing flow:

~~~text
ItemReader
    |
    v
ItemProcessor (optional)
    |
    v
Accumulate commit-interval items
    |
    v
ItemWriter writes chunk
    |
    v
COMMIT transaction
    |
    v
Read next chunk
~~~

Example step configuration using modern Spring Batch APIs:

~~~java
@Bean
Step importCustomers(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer
) {
    return new StepBuilder("importCustomers", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Here, the commit interval is 500 items. Spring Batch reads and processes one chunk, invokes `ItemWriter`, and commits the transaction. If a chunk fails, the chunk's transaction rolls back according to step configuration.

### 11.1. Commit Interval vs. JDBC Batch Size

If `ItemWriter` uses `JdbcTemplate.batchUpdate` with batch size 100 inside a step with chunk size 500, a single chunk transaction contains multiple JDBC batches. Commit interval governs transaction boundaries; JDBC batch size governs how many statements are grouped per batch call.

### 11.2. Restarts and Idempotence

When a job stops mid-run, Spring Batch can use `ExecutionContext`/`JobRepository` to restore reader state per `ItemReader` configuration. `ItemWriter` must still be designed for retry and restart semantics.

If the job writes to a different database than the one storing `JobRepository`, those two databases do not automatically share a transaction. A crash at the wrong moment can commit business data before the checkpoint records, causing a chunk to replay. Idempotent writers or unique business keys prevent duplicates.

## 12. Checkpoints and Restartability

For custom jobs, checkpoints must be stored alongside completed progress.

Example table:

~~~sql
CREATE TABLE batch_checkpoint (
    job_name VARCHAR(100) PRIMARY KEY,
    last_processed_id BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

If business data and checkpoints live in the same database, update the checkpoint inside the same chunk transaction:

~~~java
@Transactional
public void writeChunk(List<Customer> chunk, long lastId) {
    customerRepository.saveAll(chunk);
    checkpointRepository.updateLastId("customer-import", lastId);
}
~~~

If the transaction commits, both data and checkpoint commit together. If it rolls back, both roll back.

If checkpoints live in a separate system without distributed transactions, accept that chunks may replay. Make the writer idempotent.

### 12.1. Idempotent Design

An idempotent operation can be re-executed without creating incorrect or duplicate results. Examples:

- Use external IDs backed by unique constraints.
- Use business-key upserts when supported by database/dialect.
- Use conditional UPDATEs transitioning only from expected states.
- Persist import batch IDs or idempotency keys.
- Avoid sending emails or charging payments directly inside retryable sections without deduplication.

Do not rely solely on checkpoints to prevent duplicate records. Checkpoints can lag or jobs can replay after a chunk already committed.

## 13. Handling Errors Within a Chunk

Suppose a chunk has 500 customers and record 420 violates a unique constraint. If the whole chunk runs in one transaction and the error triggers rollback, the 419 prior records in that chunk also roll back.

This keeps state consistent, yet requires a handling policy:

- Fix source data and rerun the chunk.
- Record failed rows to a quarantine table in an appropriate transaction.
- Use Spring Batch retries for transient failures like deadlocks or timeouts.
- Use bounded skips for well-defined data errors.
- Shrink chunk sizes when finer error isolation is needed.

Do not catch and swallow every exception. Once a database transaction is marked rollback-only, catching exceptions in code cannot return the transaction to a committable state.

### 13.1. Retries Must Be Bounded with Backoff

Retries help with transient errors like deadlocks or lock timeouts. You should:

- Retry only explicitly classified transient exceptions.
- Cap maximum retry attempts.
- Apply backoff between attempts.
- Ensure operations are safe to rerun.
- Log batch ID, checkpoint, and final root cause.

Never infinitely retry data errors such as oversized column values or constraint violations caused by bad input.

## 14. Optimistic Locking and Concurrency

If an aggregate has `@Version`, Spring Data JDBC checks the version on update. When another transaction has updated the aggregate, saving can throw `OptimisticLockingFailureException`.

In a batch, one conflict can roll back the whole chunk if all operations share one transaction. Decide how to handle it:

- Retry the whole chunk after reloading fresh data.
- Isolate failing items for separate handling.
- Record conflicts into a retry/review queue.

Do not disable optimistic locking just to force a job through. Overwriting fresh user updates can cause severe business bugs.

With multiple workers, partitioning data by non-overlapping ID ranges reduces contention. Still, ensure workers cannot touch the same aggregate or business key concurrently.

## 15. Bulk Updates and Aggregate Lifecycles

Some jobs only need to update one column across many rows:

~~~sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE created_at < :cutoff
  AND status = 'COMPLETED';
~~~

If this is a straightforward data transition allowed by business rules, a bulk SQL statement can be far more efficient than loading and saving every aggregate.

However, bulk SQL does not automatically fire domain methods, lifecycle callbacks, or Spring Data JDBC auditing callbacks. When using `@Modifying` or `JdbcTemplate`:

- Update audit columns directly in SQL if required.
- Add version predicates if optimistic concurrency is required.
- Enforce domain invariants via predicates/constraints.
- Publish application events or write outbox entries if post-commit notifications are needed.
- Inspect affected row counts.

If each aggregate follows complex transition rules, load and process through domain/application services instead of mutating in bulk via SQL.

## 16. Optimizing Both Reads and Writes in One Job

Import or sync jobs usually involve both reading a source and writing to the database.

### 16.1. Do Not Hold Write Transactions While Reading Files

Reading large files, parsing inputs, or calling external APIs should happen before or outside chunk write transactions. Transactions should wrap only what must commit or roll back atomically.

Example:

~~~text
Read file and parse 500 lines
        |
        v
Validate/normalize data
        |
        v
Open transaction
        |
        v
Write chunk to database
        |
        v
Commit
        |
        v
Read next 500 lines
~~~

Never hold database transactions open while waiting on files, HTTP responses, or user input.

### 16.2. Limit Threads and Connections

Running chunks in parallel occupies one connection per worker. Having more workers than pool or database capacity can lower throughput due to lock contention, context switching, and connection wait queues.

Start sequentially to establish a baseline. Then increase concurrency incrementally while measuring throughput and latency. Partition along stable keys to minimize workers colliding on the same rows.

### 16.3. Use Projections When Full Aggregates Are Unneeded

If a job only needs IDs and statuses for aggregation, do not load full aggregates with child collections. Use projections/DTO queries to reduce columns, objects, and query counts.

When modifying aggregates, load aggregates appropriate to the use case. Do not materialize huge object graphs just to extract a couple of scalar values.

## 17. Common Mistakes

| Symptom | Possible cause | Remedy |
| --- | --- | --- |
| Heap grows fast during import | Loading entire input into a `List` before writing | Read and process in bounded chunks. |
| `saveAll` is slow on large aggregates | Each aggregate has many child rows or updates delete/reinsert collections | Measure statements; review aggregate design and write paths. |
| Split `List` into chunks yet only one commit occurs | Loop remains inside an outer transaction | Put transactions on a separate writer bean or use `TransactionTemplate` per chunk. |
| Batch size is 100 yet transactions are still huge | JDBC batch size splits statement batches, not commits | Separate application chunks and transaction boundaries. |
| `Stream` holds connections too long | Stream not closed or consumed inside a long transaction | Use try-with-resources; consider keyset pagination. |
| Trailing pages repeat or miss rows | Using offsets while data mutates or non-deterministic sort | Use keyset with unique keys and checkpoints. |
| One error loses the entire job | Entire job in one transaction or missing checkpoints | Commit per chunk, store checkpoints, and design retry/resume. |
| Re-running job creates duplicates | Non-idempotent writer or lagging checkpoint | Use unique keys, idempotency keys, and consistent checkpoints. |
| Deadlocks spike as workers increase | Workers lock rows in conflicting orders | Non-overlapping partitions, consistent lock order, bounded retries. |
| Audit fields unchanged after bulk update | Direct SQL bypasses lifecycle callbacks | Update audit columns in SQL or use aggregate persistence. |
| Transaction timeouts | Chunks too large or external I/O inside transactions | Shrink transaction size and move I/O outside transactions. |

## 18. Workflow for Designing a Batch Job

When processing large datasets, follow these steps:

1. **Identify the business unit:** is one item a row, an aggregate, or a related group of rows?
2. **Choose the read path:** `Page`, `Slice`, `Stream`, keyset query, or Spring Batch `ItemReader`.
3. **Choose the write path:** repository `saveAll` for aggregates; `JdbcTemplate.batchUpdate` for repeated SQL; one bulk `UPDATE` for uniform transformations.
4. **Set application chunk size:** bound objects held and processed per pass.
5. **Set JDBC batch size:** for repeated statements, measure optimal statements per batch.
6. **Set transaction boundaries:** determine how many items commit together.
7. **Design error handling:** retry transient failures, skip bounded data errors per policy, and record failed items.
8. **Design checkpoints:** enable resuming after process stops.
9. **Ensure idempotence:** re-running a chunk must not create wrong or duplicate data.
10. **Measure and tune:** throughput, heap, transaction duration, lock waits, log volume, and replication lag.

## 19. Practice Exercises

**Exercise 1 — Bounded saveAll.** Generate 10,000 customers and split into chunks of 500. Call `repository.saveAll` per chunk, observing heap object counts and per-transaction duration.

**Exercise 2 — Per-chunk transactions.** Create separate coordinator and writer beans. Fail one chunk and verify earlier chunks committed while the failing chunk rolled back.

**Exercise 3 — Self-invocation.** Move the writer method into the coordinator class, call the `@Transactional` method directly, and observe transaction boundaries. Then extract it back into a separate bean to compare.

**Exercise 4 — JDBC batchUpdate.** Update 5,000 inventory rows with `BatchPreparedStatementSetter`. Compare against a loop updating one row at a time.

**Exercise 5 — Separating batch size and transaction size.** Use chunk size 500 and JDBC batch size 100. Observe batch call counts and commit timing.

**Exercise 6 — Page and Slice.** Write query methods returning `Page` and `Slice`. Enable SQL logging, compare count queries and next-page detection.

**Exercise 7 — Keyset pagination.** Read customers by ascending ID, persist checkpoints after each chunk, and resume the job after stopping mid-run.

**Exercise 8 — Stream.** Create a query method returning `Stream`, consume it inside try-with-resources, and verify connections are released once closed.

**Exercise 9 — Spring Batch.** Build a chunk-oriented step with commit interval 500. Fail `ItemWriter` on one chunk and observe rollback/restart behavior.

**Exercise 10 — Idempotence.** Run the same chunk twice. Use unique constraints or idempotency keys to ensure no duplicate records are created.

**Exercise 11 — Optimistic locking.** Run two workers concurrently updating an aggregate with `@Version`. Observe conflicts and implement retry or isolation handling.

**Exercise 12 — Bulk update.** Compare updating aggregates individually via repository against a single bulk `UPDATE`. Inspect auditing, versioning, and invariants in both approaches.

## 20. Key Takeaways

Processing large datasets requires distinguishing application chunk size, JDBC batch size, and transaction size. Chunks bound objects processed per pass; JDBC batches cut round trips for identical statements; transaction size dictates how many changes commit or roll back together.

Spring Data JDBC provides `saveAll` to persist multiple aggregates, yet that API takes no commit interval and does not replace splitting inputs into bounded chunks. Use `saveAll` when aggregate persistence is required; use `JdbcTemplate.batchUpdate` for many executions of the same SQL; use bulk `UPDATE` when business rules can be safely expressed in a single statement.

Read large datasets using `Page`, `Slice`, keyset pagination, or `Stream`. `Stream` avoids building a full `List` but keeps a connection open until closed. For jobs needing per-chunk commits and resume, keyset pagination or Spring Batch usually offers cleaner control.

Place transactions on the per-chunk writer. If the coordinator also carries an outer transaction, `REQUIRED` propagation merges chunks into one big transaction. Keep transactions short, keep external calls out of transactions, save checkpoints consistently, and make writers idempotent so replays are safe.

There is no universal optimal batch size. Measure on production-like data and tune based on child row counts, statement counts, lock waits, transaction durations, heap, log volume, and database capacity.

### References

- [Spring Data Relational – Persisting Entities and JdbcAggregateTemplate](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data Relational – JdbcAggregateOperations API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateOperations.html)
- [Spring Data Relational – Query Methods and Streaming Results](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Framework – JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html)
- [Spring Framework – Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Batch – Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch – Commit Interval](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/commit-interval.html)
