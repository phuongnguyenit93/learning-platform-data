# Isolation levels of batch transactions

In Spring Batch, a step typically reads and writes data inside transactions managed by Spring. When multiple transactions access a database concurrently, the **isolation level** determines the degree to which one transaction sees changes made by other transactions. Choosing the right isolation level helps the batch read consistent data, avoid certain concurrency anomalies, and control the cost of locks or waiting.

The isolation level is especially important for jobs processing large datasets, jobs running concurrently with online applications, or multiple batch jobs updating the same set of tables. However, picking the highest level is not always best. A high isolation level can increase lock contention, reduce throughput, or cause transactions to be aborted due to conflicts. You need to balance business consistency requirements against the system's concurrency capacity.

## 1. What are a transaction and an isolation level?

A transaction is a unit of work managed by the database. Within a transaction, an application can read data, perform updates, and then commit or roll back. The isolation level describes the degree to which a transaction is isolated from concurrent changes made by other transactions.

For example, a batch job reads orders with status `READY`, calculates total amounts, and updates them to `PROCESSED`. While the batch is running, another application may also modify statuses or insert new orders. Without understanding the isolation level and how the database executes queries, the batch may read changing data, read a different value on a subsequent query, or miss/duplicate records during paging.

Isolation level is not an option specific to Spring Batch. It is a transaction/database concept represented by Spring via `TransactionDefinition` and `PlatformTransactionManager`.

## 2. Inconsistent read phenomena

Isolation levels are commonly explained through three main phenomena: dirty read, non-repeatable read, and phantom read.

### Dirty read

A dirty read occurs when transaction A reads a change that transaction B has not committed yet. If B rolls back, A has read data that never became committed data.

```text
Transaction A                 Transaction B
-------------                 -------------
                              UPDATE account
                              SET balance = 500
                              (not yet committed)
SELECT balance
-> reads 500
                              ROLLBACK

A has read a value that was not committed.
```

### Non-repeatable read

A non-repeatable read occurs when one transaction reads the same row twice and receives different values because another transaction committed an update between the two reads.

```text
Transaction A                 Transaction B
-------------                 -------------
SELECT balance
-> 1000
                              UPDATE account
                              SET balance = 800
                              COMMIT
SELECT balance
-> 800

The same row produces a different result within one transaction.
```

### Phantom read

A phantom read occurs when a transaction re-runs a conditional query and receives extra or missing rows because another transaction committed an insert, delete, or update that changed the result set.

For example, transaction A runs `SELECT * FROM orders WHERE status = 'READY'` and receives 100 rows. Transaction B inserts a new order with status `READY` and commits. If A runs the same query again and sees 101 rows, the newly appearing row is a phantom row.

The three phenomena above are a model to help understand isolation. How a specific database implements it may rely on locks, MVCC, snapshots, or a combination of mechanisms. Therefore, actual behavior also depends on the database management system and the query type.

## 3. Isolation levels in Spring

Spring represents isolation levels using constants in `TransactionDefinition`:

| Spring constant | Isolation level | General characteristics |
|---|---|---|
| `ISOLATION_DEFAULT` | Database default | Lets the database decide the default isolation level for the connection/transaction. |
| `ISOLATION_READ_UNCOMMITTED` | Read Uncommitted | May allow dirty reads; the lowest isolation level. |
| `ISOLATION_READ_COMMITTED` | Read Committed | Reads only committed data; the same row may change between two reads. |
| `ISOLATION_REPEATABLE_READ` | Repeatable Read | Protects repeatability of row reads per database semantics; phantom and snapshot behavior depend on the DBMS. |
| `ISOLATION_SERIALIZABLE` | Serializable | Highest isolation level under the SQL model; transactions behave equivalently to a serial order, may wait or be aborted due to conflicts. |

`ISOLATION_DEFAULT` is typically the default choice in Spring. It does not mean a fixed isolation level; it asks the transaction manager/database to use the datasource's default configuration.

### READ_UNCOMMITTED

Read Uncommitted allows a transaction to see uncommitted data from another transaction. This carries the risk of dirty reads. Some databases do not actually support this level and escalate the behavior to a higher level.

For business batch processing, this level is rarely suitable because a job could compute over data that is later rolled back. Consider it only when approximate data is acceptable and you clearly understand the database's semantics.

### READ_COMMITTED

Read Committed ensures a query only sees committed data. However, if the same transaction re-reads a row after another transaction commits an update, the later read may see the new value. The set of rows matching a query condition may also change.

This is a common level in many relational systems. It usually balances consistency and concurrency, though the batch needs a strategy if the dataset changes while processing is underway.

### REPEATABLE_READ

Repeatable Read aims to ensure that re-reading the same row within a transaction does not yield a changed value according to the database's semantics. This level usually prevents non-repeatable reads. How phantom reads are handled varies across DBMSs and implementations.

Some databases use MVCC to provide a consistent snapshot; others may use locks or range locks. Therefore, you should not infer solely from the isolation level name that every paging query or every phantom is handled the same way across all databases.

### SERIALIZABLE

Serializable is the highest isolation level under the SQL model. The database attempts to guarantee results equivalent to transactions running serially. To achieve that, the database may hold locks longer, block other transactions, or detect conflicts and abort a transaction.

For batch processing, Serializable can be useful when a business unit needs to read and update a dataset with strict consistency requirements. However, long-running transactions at this level can cause reduced throughput, lock contention, or serialization failures. The application needs an appropriate way to handle retries.

## 4. Comparing isolation levels

The table below describes the common SQL model. Check the documentation for the database in use because some DBMSs implement MVCC or locking in their own way.

| Isolation level | Dirty read | Non-repeatable read | Phantom read |
|---|---:|---:|---:|
| Read Uncommitted | May occur | May occur | May occur |
| Read Committed | No | May occur | May occur |
| Repeatable Read | No | No under standard semantics | May occur under standard SQL; database may be stronger |
| Serializable | No | No | No under the serializable model |

Higher isolation levels generally place more constraints on concurrent transactions. However, do not use this table alone to predict performance. For example, a database using MVCC may allow readers to keep reading a snapshot without blocking writers, whereas a locking query may block other transactions.

## 5. Transaction boundaries in Spring Batch

In a chunk-oriented step, Spring Batch typically creates one transaction per chunk. The reader fetches items, the processor processes them, and the writer writes the results; after the writer finishes, the framework commits the transaction. If an error occurs before the commit, the transaction may roll back according to the configuration.

```text
Chunk 1
  BEGIN TRANSACTION
    read items 1 ... N
    process items
    write chunk
  COMMIT

Chunk 2
  BEGIN TRANSACTION
    read items N+1 ... 2N
    process items
    write chunk
  COMMIT

Chunk 3 ...
```

The isolation level is applied to each chunk's transaction according to the step's transaction manager and transaction attribute. With a large chunk size, each transaction may last longer because it must read and write more items before committing. This affects lock hold time, contention levels, and the amount of work that has to be rolled back on error.

A multi-step job does not run in a single transaction from start to finish by default. Chunks or tasklet invocations have their own transactions as configured. When a later step fails, already committed chunks of an earlier step do not automatically roll back.

## 6. Configuring isolation for a chunk-oriented step

In Spring Batch 5 and later, you can configure a step's transaction attribute using `DefaultTransactionAttribute`. The following example selects Read Committed for the chunk's transaction:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    DefaultTransactionAttribute transactionAttribute =
            new DefaultTransactionAttribute();
    transactionAttribute.setIsolationLevel(
            TransactionDefinition.ISOLATION_READ_COMMITTED);
    transactionAttribute.setTimeout(120);

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .transactionAttribute(transactionAttribute)
            .build();
}
```

In the example:

- `chunk(500, transactionManager)` selects the chunk size and the transaction manager.
- `setIsolationLevel(...)` sets the isolation level for the step's transaction.
- `setTimeout(120)` sets the transaction timeout in seconds, if supported by the transaction manager.
- `transactionAttribute(...)` attaches the transaction attributes to the step.

If not configured explicitly, the step typically uses the default isolation provided by the transaction manager/database. Do not change isolation just because a job runs slowly; first determine whether the problem is lock contention, a slow query, an oversized chunk, or data contention.

## 7. Configuring isolation for a Tasklet step

A Tasklet step also uses a transaction manager. A similar transaction attribute can be applied:

```java
@Bean
Step reconcileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    DefaultTransactionAttribute transactionAttribute =
            new DefaultTransactionAttribute();
    transactionAttribute.setIsolationLevel(
            TransactionDefinition.ISOLATION_REPEATABLE_READ);

    Tasklet reconcileTasklet = (contribution, chunkContext) -> {
        // Read data and perform a reconciliation task.
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("reconcileStep", jobRepository)
            .tasklet(reconcileTasklet, transactionManager)
            .transactionAttribute(transactionAttribute)
            .build();
}
```

With a tasklet returning `RepeatStatus.CONTINUABLE`, the framework may call the tasklet multiple times. Transactions are managed per invocation and per step configuration. If the task needs to read a stable dataset across multiple invocations, design the transaction boundary and snapshot explicitly; do not assume all tasklet invocations run in a single long transaction.

## 8. Distinguishing step transaction isolation from JobRepository isolation

This is an easy point to confuse in Spring Batch. `JobRepository` also uses transactions to store metadata such as JobInstance, JobExecution, and StepExecution. When the repository creates metadata for a new execution, Spring Batch has a separate isolation setting for the create operation.

In traditional repository configuration, `isolationLevelForCreate` typically defaults to `ISOLATION_SERIALIZABLE`. The purpose is to reduce the risk of two concurrent requests simultaneously creating metadata for a JobInstance when the same job and identifying parameters are launched nearly at the same time.

This isolation **is different from the isolation of the transaction processing business data in the step**:

| Configuration | Scope | Purpose |
|---|---|---|
| Step transaction isolation | Transaction reading/writing data in a chunk or tasklet | Controls consistency when processing business data. |
| `JobRepository`'s `isolationLevelForCreate` | Transaction creating execution metadata | Protects registering JobInstance/JobExecution when concurrent launch requests occur. |

In Spring Batch configuration using `@EnableBatchProcessing`, the `isolationLevelForCreate` attribute controls the isolation for the repository's create operation as supported by the version. For example:

```java
@Configuration
@EnableBatchProcessing(
        isolationLevelForCreate = "ISOLATION_SERIALIZABLE")
public class BatchInfrastructureConfiguration {
}
```

Do not change `isolationLevelForCreate` to tune a chunk's transaction. Conversely, changing a step's isolation does not change the mechanism protecting `JobRepository` metadata creation. In a Spring Boot application, Batch infrastructure may be auto-configured; inspect how the application's repository is actually configured before customizing it.

## 9. Isolation level and database readers

The isolation level affects how a reader sees data when other transactions concurrently modify the database.

### Cursor reader

`JdbcCursorItemReader` typically opens a cursor/ResultSet and reads sequentially. Depending on the database and driver, the cursor may see a snapshot as of open time, data according to the transaction, or specific semantics. The transaction and isolation level can affect snapshot retention time, locks, and visibility of new changes.

For long-running jobs, a cursor can hold a connection for a long time. Consider the pool, transaction timeout, isolation, and database resources. Do not assume a cursor always sees the exact same dataset across every DBMS.

### Paging reader

`JdbcPagingItemReader` executes multiple queries to fetch pages. If each page is read in a different transaction or a snapshot is not held across pages, data changing while the job runs can shift page boundaries.

For example, the reader reads the first page containing IDs 1–100. Meanwhile, another transaction inserts a new record whose ID falls before the page boundary. The next page query may return a different set than if no insert had occurred. Depending on the paging strategy and sort key, duplicate or skipped rows can occur.

To reduce risk:

- Use `ORDER BY` with a stable sort key, ideally a unique key.
- Pin the dataset using a batch ID, watermark, or timestamp.
- Avoid updating columns used in the filter condition or sort key while paging is in progress.
- Consider a snapshot transaction if the database and operational requirements support it.
- For volatile datasets, consider keyset pagination or a data-claiming strategy instead of offset paging.

Choosing Repeatable Read or Serializable does not automatically solve all paging issues if pages run in different transactions. Determine the actual transaction boundaries of the reader and the step.

## 10. Isolation level does not replace business locking

Suppose two batch jobs simultaneously query `READY` orders. Both can read the same order before either job updates the status. If each job processes in separate transactions with Read Committed, both can compute and execute side effects for the same order.

Raising the isolation level may reduce some kinds of conflicts, but it is not the sole or always suitable solution. Common design approaches include:

- Conditional atomic status updates, e.g., `UPDATE ... WHERE status = 'READY'` and checking the updated row count.
- Using a version column and optimistic locking to detect competing updates.
- Claiming a set of records by status or batch ID before processing.
- Using database locks or `SELECT ... FOR UPDATE` when suitable for the database and transaction boundary.
- Using mechanisms such as `SKIP LOCKED` if supported by the DBMS and the business allows skipping locked rows for another worker to process.
- Clearly partitioning data ranges between partitions/jobs to avoid two workers receiving the same item.
- Protecting results with unique constraints and idempotent writer operations.

Isolation governs how a transaction sees and interacts with concurrent changes. Business locking determines who has the right to process a unit of data. Both mechanisms often need to work together.

## 11. Isolation level, deadlocks, and lock contention

Higher isolation can often increase wait times or the number of locks depending on the database. In batch jobs, large chunk sizes and long transactions can cause locks to be held longer, making online requests or other batches wait.

A deadlock occurs when two or more transactions hold resources that the other needs, forming a wait cycle. For example:

```text
Transaction A holds lock on Order 1
Transaction B holds lock on Order 2

A needs Order 2  ---- waits for B
B needs Order 1  ---- waits for A

The database detects the deadlock and aborts one transaction.
```

Some ways to reduce the risk:

- Update tables/rows in a consistent order across all transactions.
- Keep transactions short by choosing an appropriate chunk size.
- Create indexes for filter and join conditions to reduce scan/lock-hold time.
- Avoid calling APIs or doing slow work while a database transaction is open.
- Partition processing scopes across jobs or partitions.
- Design bounded retries for transient deadlock/serialization errors.

Do not raise isolation to Serializable just to avoid deadlocks. That level can worsen conflicts if transactions are long or multiple jobs access the same dataset concurrently.

## 12. Isolation level and retry when a transaction is aborted

In some databases, transactions running under Serializable or snapshot-based isolation may be aborted when conflicts are detected. The application needs to distinguish retryable errors from data or business errors that cannot recover on their own.

For example, you can configure retry for a transient exception type thrown by the database/driver:

```java
return new StepBuilder("updateBalancesStep", jobRepository)
        .<BalanceInput, BalanceUpdate>chunk(200, transactionManager)
        .reader(balanceReader)
        .processor(balanceProcessor)
        .writer(balanceWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

This example only illustrates a general retry policy. Determine the actual exception translated by the database driver and Spring, because serialization failure or deadlock can map to different exception types depending on the platform.

Retry must have a limit, appropriate backoff, and write logic capable of safe re-execution. If the writer sends requests to external systems or updates resources that do not participate in the transaction, a database rollback does not automatically undo those side effects.

## 13. Choosing an isolation level based on business needs

There is no single optimal isolation level for all batch jobs. You can use the following principles as a starting point for selection:

| Type of work | Level to consider | What to verify |
|---|---|---|
| Independent data import, no need to re-read the same row within a transaction | `READ_COMMITTED` or `DEFAULT` | Does the source data change while the job runs? |
| Reconciliation requiring repeated reads of the same row within a transaction | `REPEATABLE_READ` or appropriate snapshot | How does the database guarantee snapshots and how long does the transaction last? |
| Updating a dataset with strict serialization requirements | `SERIALIZABLE` or specific locking/claiming mechanism | Are blocking, retries, and serialization failures acceptable? |
| Reporting needing a consistent snapshot | Snapshot isolation or database-appropriate transaction | Can the snapshot be held for the full query scope? |
| Batch running alongside online systems | Usually start from `DEFAULT`/`READ_COMMITTED` and tune | How are lock contention, transaction duration, and update conflicts? |

For many jobs, a more effective approach can be defining a fixed dataset with a watermark or batch ID, then processing chunk by chunk with Read Committed. This avoids holding a very long Serializable transaction for the entire batch duration.

## 14. Example: pinning the dataset with a watermark

Suppose the batch needs to process all orders created before the start time. Instead of holding a long transaction to block all new inserts, the application can define a watermark at job start time:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("cutoffTime", "2026-11-15T00:00:00Z", true)
        .toJobParameters();
```

The reader uses the same cutoff for all queries:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE created_at < :cutoffTime
ORDER BY order_id
```

If the data condition and ordering remain stable, newly created records after the cutoff do not enter the current batch's processing set. The next batch can use a new cutoff.

A watermark does not by itself solve the case where an older record is updated or deleted while the job runs. If a complete snapshot is needed, choose a database-appropriate snapshot/transaction mechanism or copy the input data to an immutable set before processing.

## 15. `@Transactional` in services called from a processor or writer

A service called from a processor/writer can be annotated with `@Transactional`. However, if the service joins the open chunk transaction with the default `REQUIRED` propagation, it usually shares that transaction. Declaring a different isolation level on a method joining an existing transaction does not automatically create a new transaction with the new isolation.

For example:

```java
@Service
public class OrderLookupService {

    @Transactional(
            propagation = Propagation.REQUIRED,
            isolation = Isolation.SERIALIZABLE)
    public OrderEntity findOrder(String orderId) {
        // Queries within the current transaction if one already exists.
        return repository.findById(orderId).orElseThrow();
    }
}
```

If the method is called when a chunk transaction already exists, `REQUIRED` propagation typically joins the current transaction. The existing transaction's isolation takes effect; the annotation on the method does not automatically upgrade that transaction's isolation. Some transaction managers can be configured to validate joining a transaction with incompatible isolation, but you should not rely on a service annotation as a way to change the step's isolation.

If an independent transaction is genuinely needed, `REQUIRES_NEW` can create a separate transaction when supported by the transaction manager. However, it changes the commit boundary: the inner transaction can commit even if the outer chunk rolls back. Use it only when clearly required by the business and after evaluating impacts on restart, idempotency, and consistency.

Usually, configuring isolation on the step transaction is a clearer place for the entire read/process/write operation of a chunk.

## 16. Other factors affecting consistency

The isolation level is only one part of transaction design. A batch job is also affected by:

- **Transaction manager:** must manage the exact datasource or resource used by the reader/writer.
- **Transaction propagation:** whether a service joins the current transaction or creates a new one.
- **Transaction timeout:** overly long transactions may be aborted or hold resources too long.
- **Locking strategy:** pessimistic lock, optimistic lock, version column, or data claiming.
- **Chunk size:** affects transaction duration and rollback volume.
- **Query plan and indexes:** slow queries make transactions live longer.
- **MVCC/snapshot implementation:** determines how the database provides consistent data.
- **Non-database data sources:** files, APIs, and message brokers do not automatically participate in JDBC transactions.
- **Restart and idempotency:** items or non-transactional operations may be executed again.

Therefore, when data consistency bugs occur, examine the entire path from reader, transaction manager, processor, and writer to the database rather than just changing an isolation value.

## 17. Testing isolation levels in a realistic environment

Before deploying a new isolation level, verify the database behavior through controlled experiments:

1. Identify the database, version, JDBC driver, and transaction manager in use.
2. Check the default isolation of the database and connection pool.
3. Confirm which transaction manager the step actually uses.
4. Create two concurrent transactions to test dirty reads, non-repeatable reads, or phantoms according to the business case.
5. Measure lock wait times, deadlocks, serialization failures, and batch throughput.
6. Test with chunk sizes and datasets close to production.
7. Test restarts after a transaction rolls back or is aborted by the database.
8. Confirm the writer does not create duplicate data when items are reprocessed.

Also monitor per-chunk duration, retry counts, skip error counts, connection wait times, lock waits, and commit times. These metrics help determine whether an issue comes from isolation, queries, chunk size, or resource contention.

## 18. Common mistakes when configuring isolation for batch

| Issue | Possible cause | Approach |
|---|---|---|
| Thinking Serializable is always best | Ignoring lock cost, blocking, and serialization failures. | Choose a level based on consistency needs and measure real load. |
| Changing JobRepository isolation leaves chunk unchanged | Confusing `isolationLevelForCreate` with the step's transaction. | Configure the step's transaction attribute for the business transaction. |
| Adding `@Transactional(isolation=...)` to a service has no effect | The method joins the current chunk transaction with `REQUIRED`. | Configure on the step or design a new transaction when truly necessary. |
| Paging duplicates or misses rows | Unstable sort key or source data changes between pages. | Use a unique sort key, watermark, or snapshot. |
| Batch holds locks too long | Oversized chunks, slow transactions, or queries missing indexes. | Shorten transaction time, optimize queries, and re-measure chunk size. |
| Deadlocks when multiple jobs run concurrently | Transactions update rows in different orders or contend for the same data. | Standardize update order, partition data, and retry transient errors. |
| Retries cause duplicate writes | Side effects outside the transaction or non-idempotent writer. | Use business keys, idempotency keys, outbox, or reconciliation. |
| Reading data that changes across chunks | Each chunk is a separate transaction, no job-wide snapshot. | Pin the dataset with a watermark or use an appropriate snapshot. |

## 19. Key takeaways

- The isolation level determines how much a transaction sees changes from concurrent transactions.
- Dirty read, non-repeatable read, and phantom read are three phenomena to understand when choosing an isolation level.
- Spring provides `ISOLATION_DEFAULT`, `READ_UNCOMMITTED`, `READ_COMMITTED`, `REPEATABLE_READ`, and `SERIALIZABLE` via `TransactionDefinition`.
- A chunk-oriented step typically has a separate transaction per chunk; the whole job is not in a single transaction by default.
- Step isolation can be configured via `DefaultTransactionAttribute` and `.transactionAttribute(...)`.
- Step transaction isolation differs from `isolationLevelForCreate` used for `JobRepository` metadata creation transactions.
- Cursor and paging readers have different consistency behaviors; paging needs a stable sort key and a well-defined dataset.
- Isolation does not replace business locking, data claiming, unique constraints, or idempotency.
- Higher isolation levels can increase lock contention, blocking, or serialization failures; use bounded retries where appropriate.
- `@Transactional` on a service joining an existing transaction does not automatically elevate the chunk transaction's isolation.
- Choose isolation according to the database, business requirements, transaction boundaries, and concurrent jobs; verify with real experiments.

When designing batch transactions, start from data consistency requirements: whether the job needs to read a stable snapshot or only committed data, whether jobs can update the same records, and how long transactions last. Then select an appropriate isolation level, chunk size, and locking strategy. This approach helps batch jobs process data safely while maintaining throughput for concurrent applications.
