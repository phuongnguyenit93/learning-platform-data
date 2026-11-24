# DataSourceTransactionManager

`DataSourceTransactionManager` is Spring Framework's implementation of `PlatformTransactionManager` for managing JDBC transactions on a single `DataSource`. It opens or acquires a JDBC `Connection`, binds that connection to the executing thread, and then commits or rolls back when the transaction ends.

In Spring Batch, this transaction manager is typically passed into a chunk-oriented step. As a result, JDBC operations run inside the same chunk transaction if they use the same `DataSource` via Spring-integrated APIs such as `JdbcTemplate` or `DataSourceUtils`.

Importantly, this transaction manager manages only a single JDBC `DataSource` resource using local transaction semantics. It does not automatically create distributed transactions across multiple databases, file systems, or HTTP services. When designing a batch job, determine precisely which resources participate in the transaction and which require idempotency, an outbox, or compensation.

## 1. Role of DataSourceTransactionManager

`DataSourceTransactionManager` implements the `PlatformTransactionManager` contract. It manages JDBC transactions by working directly with connections acquired from a `DataSource`.

Primary responsibilities:

- Acquire a JDBC connection when the transaction starts.
- Apply transaction attributes such as isolation level, read-only, and timeout when configured and supported by the driver.
- Bind the connection to the current thread so subsequent JDBC operations can reuse that connection.
- Commit when the transaction completes normally.
- Roll back when the transaction terminates under a condition requiring rollback.
- Return the connection to the pool or close it as managed by the `DataSource`.

`DataSourceTransactionManager` fits applications using a single JDBC database and needing local transactions for read/write operations. If an application uses JDBC and wants additional exception translation for commit/rollback failures, Spring also provides `JdbcTransactionManager`, an extension of `DataSourceTransactionManager`.

## 2. Connection is bound to the current thread

When a transaction begins, `DataSourceTransactionManager` obtains a connection from the `DataSource` and binds that connection to the thread via Spring's transaction synchronization mechanism. APIs like `JdbcTemplate` call `DataSourceUtils` to look up the bound connection and reuse it.

```text
Thread executing chunk
       |
       v
DataSourceTransactionManager
       |
       +--> get Connection from DataSource
       |
       +--> bind Connection to thread
       |
       v
JdbcTemplate / DataSourceUtils
       |
       +--> find bound connection
       +--> execute SQL on the same connection
       |
       v
Commit or rollback
       |
       +--> unbind and release Connection
```

As a result, multiple DAOs or repositories sharing a transaction manager and a `DataSource` can participate in the same transaction without passing connections across every method.

The transaction context is thread-bound. If code spawns a new thread or dispatches work to another executor, the new thread does not automatically inherit the parent thread's transaction connection. Each worker thread needs its own transaction or an explicitly designed transaction coordination mechanism.

## 3. Why use JdbcTemplate or DataSourceUtils?

To participate in transactions managed by `DataSourceTransactionManager`, JDBC operations must acquire connections through Spring's transaction-aware mechanism.

`JdbcTemplate` uses `DataSourceUtils` internally, making it the simplest choice:

```java
@Repository
public class OrderRepository {

    private final JdbcTemplate jdbcTemplate;

    public OrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void insert(Order order) {
        jdbcTemplate.update(
            "INSERT INTO ORDERS (ORDER_ID, CUSTOMER_ID, TOTAL) VALUES (?, ?, ?)",
            order.getOrderId(),
            order.getCustomerId(),
            order.getTotalAmount()
        );
    }
}
```

If you must use the JDBC API directly, acquire and release connections via `DataSourceUtils`:

```java
Connection connection = DataSourceUtils.getConnection(dataSource);
try (PreparedStatement statement = connection.prepareStatement(
        "UPDATE ORDERS SET STATUS = ? WHERE ORDER_ID = ?")) {
    statement.setString(1, "PROCESSED");
    statement.setLong(2, orderId);
    statement.executeUpdate();
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
```

`releaseConnection` does not close a connection managed by an active transaction; it releases it according to Spring's rules. Never call `connection.close()` directly on a connection obtained from `DataSourceUtils` inside a transaction, as doing so can close the connection the transaction is using.

If code calls `dataSource.getConnection()` directly on a standard pool, it may get a different connection from the one bound to the transaction. That SQL statement would then execute outside the chunk transaction and fail to roll back with other operations. Use a direct connection only when intentionally managing a separate transaction/resource and understanding the consequences.

## 4. Declaring DataSourceTransactionManager

In Java configuration, you can declare the transaction manager as a bean:

```java
@Configuration
public class BatchDatabaseConfiguration {

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

The bean accepts the application-configured `DataSource`, typically a connection pool created by Spring Boot or project datasource configuration. Ensure repositories, `JdbcTemplate`, and the transaction manager all point to the same `DataSource` when they need to share a transaction.

When using multiple transaction managers, name beans and inject with `@Qualifier` to avoid picking the wrong one:

```java
@Bean("ordersTransactionManager")
PlatformTransactionManager ordersTransactionManager(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
```

In Spring Batch 5, the transaction manager is passed explicitly into the chunk or tasklet step builder. This makes the step's transaction boundary clearly visible in configuration.

## 5. Passing the transaction manager to a chunk step

Example chunk step reading and writing orders via JDBC:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        @Qualifier("ordersTransactionManager") PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderRow, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

With `chunk(100, transactionManager)`, Spring Batch processes up to 100 items in one chunk transaction per step configuration. When the chunk completes, the transaction manager commits; if an exception triggers rollback, the current transaction rolls back.

A tasklet step also requires a transaction manager:

```java
@Bean
Step archiveStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet archiveTasklet) {

    return new StepBuilder("archive", jobRepository)
        .tasklet(archiveTasklet, transactionManager)
        .build();
}
```

Do not confuse the step's transaction manager with `JobRepository`. `JobRepository` persists job/step metadata; the transaction manager is used by the step to wrap chunk or tasklet processing transactions. Batch infrastructure configuration also needs a suitable transaction manager to manage metadata on the repository's datasource.

## 6. Transaction boundaries in chunk processing

In a chunk-oriented step, a single transaction typically wraps the processing of one chunk. The reader fetches items, the processor transforms them, the writer writes the chunk, and Spring Batch updates `ItemStream` state per lifecycle. When the chunk's work completes, the transaction commits.

```text
Chunk 1
  BEGIN
    read/process/write items 1..100
    update stream state
  COMMIT

Chunk 2
  BEGIN
    read/process/write items 101..200
    update stream state
  ROLLBACK if a rollback-triggering error occurs

Chunk 3
  runs only if step recovery/policy permits continuing
```

Chunk size is part of transaction design. Larger chunks reduce commit count, yet hold connections and transactions longer and increase the work rolled back on failure. Smaller chunks commit more frequently, yet can increase database overhead.

Do not assume each item has its own separate transaction when using chunk processing. If a different transaction boundary is required, design the step or service transactions explicitly.

## 7. Participating in transactions via @Transactional

A service invoked from a processor/writer can join the chunk transaction if it uses the same transaction manager and the default `REQUIRED` propagation.

```java
@Service
public class OrderUpdateService {

    private final JdbcTemplate jdbcTemplate;

    public OrderUpdateService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void markProcessed(long orderId) {
        jdbcTemplate.update(
            "UPDATE ORDERS SET STATUS = 'PROCESSED' WHERE ORDER_ID = ?",
            orderId
        );
    }
}
```

If `markProcessed` is called inside the chunk transaction and uses the same transaction manager, `REQUIRED` normally joins the existing transaction. When the chunk rolls back, this change rolls back as well.

Keep Spring's proxy mechanism in mind: calls to `@Transactional` must pass through the proxy for advice to apply. Self-invocation inside the same object bypasses standard proxy-based interception. Also ensure beans use the right transaction manager when the application has multiple datasources.

## 8. Propagation and REQUIRES_NEW

Propagation determines whether a transactional method joins an existing transaction or creates a new one.

| Propagation | General behavior | Impact inside a chunk |
|---|---|---|
| `REQUIRED` | Joins existing transaction; creates a new one if none exists | Usually fits services writing to the same database as the chunk |
| `REQUIRES_NEW` | Suspends current transaction and starts a new one | Can commit independently even if the outer chunk rolls back |
| `SUPPORTS` | Joins if a transaction exists, otherwise runs non-transactionally | Requires clear understanding of caller context |
| `MANDATORY` | Requires an existing transaction | Useful when the service must not be called standalone |
| `NOT_SUPPORTED` | Runs non-transactionally, suspending any current transaction | Unsuitable for operations that must roll back with the chunk |
| `NESTED` | Uses nested transaction/savepoint if supported by manager and driver | Allows partial rollback within the outer transaction |

`REQUIRES_NEW` must be used intentionally. For example, if a service writes an audit record in a new transaction and the outer chunk rolls back, the audit record persists. That may be right for auditing an attempt, but wrong if the record implies committed business completion.

`NESTED` depends on savepoint support from the JDBC driver and transaction manager. Do not assume every database or configuration supports nested transactions.

## 9. Rollback rules and checked exceptions

With Spring declarative transactions, `RuntimeException` and `Error` trigger rollback by default; checked exceptions do not automatically roll back under default rules unless an explicit rollback rule is configured.

Example requiring rollback on a checked exception:

```java
@Transactional(rollbackFor = PartnerFileException.class)
public void importPartnerFile() throws PartnerFileException {
    // JDBC operations needing the same transaction
}
```

In Spring Batch, a fault-tolerant step also has retry/skip and rollback classification. Therefore, distinguish the transaction manager's rollback rules from the step's skip/retry policy. An exception may be skippable yet still roll back the chunk before framework recovery; `noRollback` configuration has specific semantics and should be used only after understanding changes already made.

Do not catch and swallow exceptions inside a writer or service if Spring Batch needs to see the failure to roll back/retry/skip. Let exceptions propagate or translate them into meaningful exceptions.

## 10. Isolation levels

Isolation level controls how one transaction sees changes made by other transactions. `DataSourceTransactionManager` can apply an isolation level on the JDBC connection when a transaction begins, if supported by the driver/database.

Common JDBC levels:

| Isolation | General characteristics |
|---|---|
| `READ_UNCOMMITTED` | May read uncommitted changes from other transactions if supported by the database |
| `READ_COMMITTED` | Reads only committed data as of the read point |
| `REPEATABLE_READ` | Reduces the chance that re-reading the same row yields different values in one transaction; phantom behavior varies by database |
| `SERIALIZABLE` | High isolation level; can reduce concurrency and increase contention |

There is no single optimal isolation level for all batch jobs. Choose based on business correctness, database engine, query patterns, and load capacity. `SERIALIZABLE` can increase deadlocks or wait times; `READ_COMMITTED` suffices for many jobs, yet does not guarantee a single consistent snapshot across multiple chunks.

If a job needs a consistent snapshot for the entire run, evaluate snapshot isolation, watermarks, or snapshot staging. Separate per-chunk transactions do not automatically create a single snapshot across the entire job.

## 11. Timeout and read-only

Transaction definitions can specify a timeout and a read-only hint. `DataSourceTransactionManager` applies these properties to the connection according to driver and database capabilities.

- Timeout helps bound transaction duration; JDBC operations must use Spring-integrated APIs so statement timeouts can be applied appropriately.
- Read-only is a hint to the database/driver that can enable read optimizations; do not treat it as an absolute data protection mechanism.
- Chunk transaction timeout should align with query timeouts, HTTP client timeouts, and overall SLAs.

For writer steps, never mark the transaction read-only. For reader-only tasklets or query-only steps, read-only can be beneficial if supported by the database and properly configured.

## 12. DataSourceTransactionManager and JobRepository

`JobRepository` stores metadata such as JobInstance, JobExecution, StepExecution, execution context, and status. In JDBC setups, the repository uses a `DataSource` to persist metadata tables.

The chunk step's transaction manager manages business data processing transactions. The transaction manager used by `JobRepository` infrastructure manages metadata operations per repository configuration. Both roles can share one `DataSourceTransactionManager` if metadata and business data live in the same datasource, or use separate transaction managers if datasources are separate.

Example Spring Batch 5 infrastructure configuration specifying datasource and transaction manager beans explicitly:

```java
@Configuration
@EnableBatchProcessing(
    dataSourceRef = "batchDataSource",
    transactionManagerRef = "batchTransactionManager"
)
public class BatchInfrastructureConfiguration {
    // JobRepository and infrastructure components configured by Spring Batch
}
```

Annotation attributes and repository configuration must match your Spring Batch version. If the application configures `JobRepository` manually, specify the appropriate transaction manager for the metadata datasource.

If the metadata repository and business data reside in two different datasources, do not assume a local `DataSourceTransactionManager` can commit/roll back both atomically. Design consistency, restarts, and reconciliation for the case where one commits while the other fails.

## 13. Single DataSource or multiple DataSources?

`DataSourceTransactionManager` manages one `DataSource` at a time. When a chunk updates two independent databases, two local transaction managers do not automatically coordinate into a single shared transaction.

| Architecture | Management approach |
|---|---|
| Single database for metadata and business data | Can share DataSource/transaction manager with matching configuration |
| Two datasources, one datasource per step | Pick the transaction manager of the datasource each step manages |
| Single chunk writing two independent datasources | Two local managers do not guarantee global atomic commit |
| Multiple XA-capable resources needing atomicity | Consider JTA/XA transaction manager and matching infrastructure |
| Integrating database with files/APIs/message brokers | Typically use outbox, staging, idempotency, or compensation |

Do not create two `DataSourceTransactionManager` instances and expect both to roll back when one writer throws an exception. Only the transaction manager wrapping the step directly manages its resource's transaction; any other manager must be coordinated via a separate mechanism.

## 14. Combining database and file writers

A batch step may both write to a database and generate a file. However, JDBC transactions do not automatically roll back the file system. If the database rolls back after the file has been written directly, the file may contain content inconsistent with the database.

A generally safer design:

1. Write the file to a temporary name tied to JobExecution or batch ID.
2. Complete all chunks and verify output data.
3. Once the step/job meets success criteria, use a publish step to rename or move the file to its official location.
4. If the job fails, retain the temporary file for investigation or clean it up per policy.

`FlatFileItemWriter` provides transaction-aware buffering for chunks in certain configurations, yet does not turn the filesystem and database into an XA transaction. Test actual behavior with your transaction manager and filesystem.

## 15. DataSourceTransactionManager in partitioning

In a partitioned step, each worker `StepExecution` typically runs on its own thread when local partitioning uses a `TaskExecutor`. Because the transaction context is thread-bound, each worker gets its own JDBC transaction and its own connection from the pool.

```text
Manager step
    |
    +--> Worker partition 0 / Thread 1 / JDBC Connection 1
    |
    +--> Worker partition 1 / Thread 2 / JDBC Connection 2
    |
    +--> Worker partition 2 / Thread 3 / JDBC Connection 3
```

Partition 0's transaction commits independently of partitions 1 and 2. If partition 2 fails, data already committed by other partitions is not automatically rolled back.

The connection pool must accommodate the number of concurrent workers plus the needs of JobRepository, web requests, and other components. Raising `gridSize` or thread pool size without checking pool capacity can cause connection exhaustion, timeouts, and lower throughput.

## 16. Multi-threaded steps and transaction context

In a multi-threaded step, item processing can run across multiple threads depending on configuration. Transaction resources are managed per thread, not by sharing a single JDBC connection across threads.

Never pass a `Connection` or transaction-bound resource from one thread to another. Each thread must participate in transactions via mechanisms supported by Spring Batch and the transaction manager. Readers/writers must also be safe under concurrent access.

If business logic requires a dedicated transaction per independent data slice, partitioning usually models this more cleanly because each partition has its own StepExecution and transaction. Regardless of model, check connection pools, isolation, lock contention, and deadlock retry capability.

## 17. Configuring multiple transaction managers

When an application has multiple datasources, name each transaction manager clearly and inject the right manager into steps/services.

```java
@Bean("ordersTransactionManager")
PlatformTransactionManager ordersTransactionManager(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}

@Bean("auditTransactionManager")
PlatformTransactionManager auditTransactionManager(
        @Qualifier("auditDataSource") DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
```

A service can specify its manager:

```java
@Transactional(
    transactionManager = "auditTransactionManager",
    propagation = Propagation.REQUIRES_NEW
)
public void recordAttempt(AuditRecord record) {
    // Write audit using auditDataSource
}
```

This is a separate transaction. If the audit commits while the business transaction rolls back, the audit record remains. That may be the right requirement for recording attempt history; however, if the audit implies business completion, model status explicitly.

Do not use multiple transaction managers to manufacture atomicity across datasources. When true multi-resource transactions are required, use JTA/XA or an appropriate consistency pattern.

## 18. Nested transactions and savepoints

`DataSourceTransactionManager` can support nested transactions based on JDBC savepoints when supported by the driver and database. A nested transaction is not an independent transaction that commits durably before the outer transaction.

```text
Outer transaction
   |
   +--> SQL A
   |
   +--> SAVEPOINT
   |       |
   |       +--> SQL B
   |       +--> error -> rollback to savepoint
   |
   +--> SQL C
   |
   +--> COMMIT outer transaction
```

If the outer transaction rolls back, SQL A and SQL C still roll back even though the nested portion completed. Nested/savepoint fits when undoing a sub-operation inside a larger transaction, not as a replacement for `REQUIRES_NEW`.

Nested capability depends on `nestedTransactionAllowed` configuration, JDBC driver, and database. Test against your target platform before relying on savepoints in a batch job.

## 19. Deadlocks, lock timeouts, and retries

Batch jobs can contend for locks with online applications or other workers. The database may raise deadlocks or lock timeouts; the current transaction usually must roll back before retrying.

Retries can be configured on a fault-tolerant step for transient exceptions:

```java
return new StepBuilder("updateOrders", jobRepository)
    .<OrderRow, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(DeadlockLoserDataAccessException.class)
    .retryLimit(3)
    .build();
```

Exact exception types depend on the exception classes translated by the driver and Spring. In modern applications, you may encounter subclasses of `TransientDataAccessException`. Classify by actual exceptions, set bounded retry limits and backoff, and ensure the writer is idempotent.

Do not retry every `DataAccessException`. Schema, permission, SQL syntax, or deterministic constraint errors will not resolve themselves on retry.

## 20. Transaction timeout and chunk duration

Long transactions hold connections and locks longer. With large chunk sizes or a writer calling slow services while a transaction is open, the database can suffer contention and pool exhaustion.

Design must coordinate:

- Chunk size with SQL count and per-item processing duration.
- Transaction timeout with query timeout and dependency response times.
- Retry/backoff with overall job deadlines.
- Connection pool size with concurrent worker count.
- Lock ordering across writers to minimize deadlocks.

Avoid making HTTP calls or performing slow tasks inside a JDBC transaction if you can split preparation from post-commit side effects. A JDBC transaction manager does not enforce timeouts on HTTP clients.

## 21. Testing rollback with DataSourceTransactionManager

Integration tests should verify data actually rolls back in the database, not just that an exception was thrown.

Example service test:

```java
@Test
void rollsBackDatabaseChangesWhenRuntimeExceptionOccurs() {
    assertThatThrownBy(() -> transactionTemplate.execute(status -> {
        jdbcTemplate.update(
            "INSERT INTO ORDERS (ORDER_ID, STATUS) VALUES (?, ?)",
            9001L, "NEW");
        throw new IllegalStateException("forced failure");
    })).isInstanceOf(IllegalStateException.class);

    Integer count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM ORDERS WHERE ORDER_ID = ?",
        Integer.class, 9001L);

    assertThat(count).isZero();
}
```

This test assumes `TransactionTemplate` uses the same `DataSourceTransactionManager` as `JdbcTemplate`. Query the database after the transaction ends to verify the row was not committed.

For a Spring Batch step, write integration tests verifying:

1. The writer writes some rows and then throws an exception within the same chunk.
2. Rows from that chunk are rolled back.
3. Previously committed chunks remain intact.
4. Retry/skip combinations yield final data matching policy.
5. `ExecutionContext` checkpoints and restarts work properly.
6. Two partition workers have independent transactions and connections.
7. `REQUIRES_NEW` commits independently as designed.
8. A second datasource is not mistakenly assumed to roll back automatically with the first datasource.

## 22. Observing transactions in production

To investigate transaction issues, monitor:

- JobExecution ID and StepExecution ID.
- Job/step name and worker/partition if applicable.
- Database connection pool active/idle/pending counts.
- Transaction duration and timeouts.
- Deadlocks, lock waits, and rollback counts.
- Retry counts by exception category.
- Chunk read/write/skip counts.
- Query duration and connection errors.

Never log credentials, connection strings with passwords, or sensitive data. Enable debug transaction logging only during active investigation, as it produces high log volume and impacts performance.

## 23. Common mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Calling `dataSource.getConnection()` directly inside a transaction | May get a connection outside the transaction-bound connection | Use `JdbcTemplate` or `DataSourceUtils` |
| Passing the wrong DataSource to the transaction manager | SQL does not join the expected transaction | Use the exact DataSource and explicit qualifiers |
| Expecting one datasource's transaction manager to roll back another datasource | Second resource may commit independently | Use JTA/XA or outbox/compensation |
| Setting chunk size too large | Long transactions, long locks, and expensive rollbacks | Choose chunk size based on workload and database |
| Using `REQUIRES_NEW` without understanding consequences | Inner changes commit even when the chunk rolls back | Use only when an independent transaction is required |
| Confusing skip with noRollback | Item may skip while the chunk still rolls back during recovery | Distinguish skip policies from rollback classification |
| Sharing a JDBC Connection across threads | Connection/transaction is unsafe | Give each worker its own thread-bound transaction |
| Not sizing the connection pool for partitioning | Workers wait for connections or time out | Cap concurrency and size pool appropriately |
| Retrying all database errors | Config/schema errors repeat pointlessly | Retry only classified transient failures |
| Assuming DB and files commit atomically | File may persist when database rolls back | Use staging and a publish step |

## 24. Workflow for choosing DataSourceTransactionManager for a batch job

When configuring a job, determine in order:

1. Which datasource(s) does the step read from/write to?
2. Do the reader, writer, and services use the exact same DataSource?
3. Does each chunk need a local transaction or multi-resource coordination?
4. Which datasource holds JobRepository metadata and which transaction manager manages it?
5. Does JDBC access go through `JdbcTemplate`/`DataSourceUtils` to join transactions?
6. Are isolation, timeout, read-only, and rollback rules appropriate?
7. Are retry/skip configured separately for transient failures vs. data errors?
8. For partitioning, is the connection pool sufficient for concurrency?
9. Do non-database side effects have outbox/idempotency/compensation?
10. Do integration tests verify commits, rollbacks, restarts, and metadata?

## Conclusion

`DataSourceTransactionManager` manages local JDBC transactions for a single `DataSource`. It acquires a connection, binds it to the current thread, and controls commits/rollbacks. `JdbcTemplate` and `DataSourceUtils` reuse the bound connection so JDBC operations in readers, processors, writers, or services can join the chunk transaction.

In Spring Batch 5, pass the transaction manager into `.chunk(size, transactionManager)` or `.tasklet(tasklet, transactionManager)` to define the step's transaction boundary. Choose the right datasource, propagation, isolation, and timeout; avoid passing connections across threads or assuming multiple datasources/files/APIs roll back together automatically. With partitioning, each worker has its own transaction and needs appropriate connection pool capacity. Test commits/rollbacks against a real database, design retries for transient errors, and use outbox/idempotency or compensation for non-transactional side effects.
