# Transaction timeout

In Spring Batch, a transaction timeout limits how long a Step transaction is allowed to run according to the configuration of the transaction manager and underlying resources. Timeouts prevent transactions from holding connections, locks, or resources too long when queries are slow, the database is congested, or processing a chunk does not finish as expected.

A chunk-oriented Step typically opens a transaction per chunk. A TaskletStep opens a transaction per Tasklet invocation. Therefore, a transaction timeout typically applies to a chunk or a Tasklet invocation, not the total runtime of the Job.

When a transaction exceeds the limit, resource access operations may fail and the transaction is rolled back according to the transaction manager's policy. However, a transaction timeout is not a timer that guarantees immediate termination of any running Java code, HTTP request, or thread. You must distinguish a transaction timeout from a query timeout, lock timeout, and network/socket timeout.

## 1. What is a transaction timeout?

A transaction timeout is a deadline declared for a new transaction. In Spring, timeouts are usually expressed in seconds via TransactionDefinition or TransactionAttribute. The transaction manager uses this value to apply limits to the transaction and managed resources.

For example, if a chunk is configured with a 60-second timeout, the application is requesting that the chunk's transaction finish within the set limit. If work exceeds the limit, subsequent database operations may raise timeout errors; the current transaction cannot be considered completed successfully.

Some purposes of transaction timeout:

- Prevent transactions from holding connections and locks too long.
- Limit waiting time when the database or resource responds slowly.
- Allow the Step to fail clearly instead of keeping a transaction open indefinitely.
- Provide a basis for classifying transient errors and applying controlled retries.
- Protect other transactions that need to use the same database resources.

A transaction timeout does not automatically optimize a slow query. If a query consistently takes 90 seconds and the timeout is set to 60 seconds, increasing the timeout may allow the query to finish but does not solve the performance root cause. You must inspect execution plans, indexes, locks, data volume, and system load.

## 2. At which boundary does timeout apply in Spring Batch?

### Chunk-oriented Step

With a chunk-oriented Step, Spring Batch reads, processes, and writes a group of items inside the chunk's transaction. After the writer completes and related updates succeed, the transaction commits.

~~~text
Chunk 1
  |
  +-- open transaction
  |
  +-- read items
  +-- process items
  +-- write chunk
  +-- update metadata/checkpoint
  |
  +-- commit

Chunk 2
  |
  +-- open new transaction
  |
  +-- read / process / write
  |
  +-- commit
~~~

The transaction timeout is measured for each individual chunk's transaction. If a Step processes 1,000 chunks, a 60-second timeout does not mean the entire Step can only run for at most 60 seconds. Each chunk has its own transaction according to the Step's processing lifecycle.

However, if a chunk contains many items or each item has slow processing, transaction duration can grow. Large chunk sizes, processors calling remote services, or writers executing multiple queries can cause a transaction to exceed its timeout.

### TaskletStep

TaskletStep invokes the Tasklet within a transaction. If the Tasklet returns CONTINUABLE, the Step keeps calling the Tasklet on subsequent passes; each pass is managed by its own transaction.

~~~text
Tasklet pass 1: open transaction -> process -> commit
Tasklet pass 2: open transaction -> process -> commit
Tasklet pass 3: open transaction -> process -> commit
~~~

If the Tasklet performs the entire long job in a single execute call, one transaction may have to cover that entire job. If the Tasklet divides work into small parts and returns CONTINUABLE after each part, each pass can finish its own transaction. This division requires checkpoints or durable state so restarts know which parts are already complete.

### Timeout is not a time limit for the entire Job

A Job often comprises multiple Steps, and a chunk-oriented Step has many transactions. A Job can run for hours even though each chunk transaction lasts only a few seconds. A transaction timeout limits each transaction as configured, not the total runtime of the Job.

If the system needs to cap the total runtime of a Job or the wait time of an external process, a separate coordination mechanism or timeout is required for that purpose. Do not use a transaction timeout as a Job deadline.

## 3. Configuring timeout for a chunk-oriented Step

In Spring Batch 5 and later, you can create a TransactionAttribute and pass it to StepBuilder via transactionAttribute:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    DefaultTransactionAttribute transactionAttribute =
            new DefaultTransactionAttribute();
    transactionAttribute.setTimeout(60);

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .transactionAttribute(transactionAttribute)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

In the example:

- The chunk size is 100 items.
- The transaction manager manages the chunk's transaction.
- The timeout is set to 60 seconds.
- Each chunk is processed in its own transaction according to the Step configuration.

TransactionAttribute can also control propagation, isolation level, and rollback rules. If you only need to adjust the timeout, leaving the remaining attributes at their defaults usually avoids unnecessary behavior changes.

You can externalize the timeout to configuration:

~~~properties
batch.orders.chunk-size=100
batch.orders.transaction-timeout-seconds=60
~~~

Then inject the values into the Step configuration. Validate input values to avoid unexpected timeout settings:

~~~java
if (transactionTimeoutSeconds <= 0) {
    throw new IllegalArgumentException(
            "Transaction timeout must be positive");
}
~~~

The default value of transaction timeout can be represented by TransactionDefinition.TIMEOUT_DEFAULT, meaning use the default timeout of the transaction manager or resource. When a specific limit is needed for a Step, set an explicit value and verify that the transaction manager supports applying it that way.

## 4. Configuring timeout for a TaskletStep

TaskletStep also allows configuring TransactionAttribute. For example:

~~~java
@Bean
public Step reconcileBatchStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ReconciliationService reconciliationService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        reconciliationService.reconcileCurrentBatch();
        return RepeatStatus.FINISHED;
    };

    DefaultTransactionAttribute transactionAttribute =
            new DefaultTransactionAttribute();
    transactionAttribute.setTimeout(120);

    return new StepBuilder("reconcileBatchStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .transactionAttribute(transactionAttribute)
            .build();
}
~~~

Here the transaction timeout is 120 seconds for the Tasklet pass's transaction. If the Tasklet returns CONTINUABLE, subsequent passes are also executed according to the Step's transaction attributes.

If the Tasklet calls an external API that takes 5 minutes, a 120-second transaction timeout does not guarantee the HTTP request will be canceled after exactly 120 seconds. You must configure connect timeout, response/read timeout, or deadlines on the HTTP client. Also, avoid keeping a database transaction open while waiting on an API unless necessary.

## 5. Distinguishing timeout types

A batch system can have multiple layers of timeouts. They protect different resources and operations:

| Timeout type | Scope | Example |
| --- | --- | --- |
| **Transaction timeout** | Duration a transaction is allowed to exist per the transaction manager | A chunk must complete within 60 seconds |
| **Query/statement timeout** | Duration a SQL statement is allowed to execute | SELECT or UPDATE exceeds 20 seconds |
| **Lock timeout** | Time waiting to acquire a lock on the database | UPDATE must wait for another transaction to release a lock |
| **Connection timeout** | Time waiting to obtain a connection from the pool or establish a connection | HikariCP fails to provide a connection in time |
| **Network/socket timeout** | Time waiting for data over a network connection | JDBC driver or HTTP client waiting for response |
| **Job/operation deadline** | Total time a business process is allowed to run | A reconciliation batch must finish before cutoff |

Timeouts can interact but do not replace each other. For example, a 60-second transaction timeout does not necessarily cap a single SQL statement at 60 seconds if the driver or resource does not apply transaction timeout to the statement. A 20-second query timeout can stop a SQL statement before the transaction timeout occurs.

### Transaction timeout and query timeout

Query timeout is typically configured on a JDBC statement or JdbcTemplate. With JdbcTemplate, you can set a default query timeout for the template:

~~~java
JdbcTemplate jdbcTemplate = new JdbcTemplate(dataSource);
jdbcTemplate.setQueryTimeout(20);
~~~

When using JdbcTemplate, Spring applies appropriate statement and transaction timeout settings via the DataSourceUtils mechanism. When using JDBC directly, the application must ensure statements are bound to the transaction and timeouts are applied properly; do not assume every raw JDBC command automatically inherits Spring's full timeout.

Example using DataSourceUtils to apply transaction timeout to a statement:

~~~java
Connection connection = DataSourceUtils.getConnection(dataSource);
try {
    PreparedStatement statement =
            connection.prepareStatement("SELECT * FROM orders WHERE id = ?");

    try {
        statement.setLong(1, orderId);
        DataSourceUtils.applyTransactionTimeout(statement, dataSource);

        try (ResultSet resultSet = statement.executeQuery()) {
            // Read results.
        }
    } finally {
        statement.close();
    }
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
~~~

In ordinary applications, JdbcTemplate or repository abstractions are usually safer and easier to manage than manual JDBC.

### Transaction timeout and lock timeout

Transactions can slow down because they wait for locks. Lock timeouts are managed by the database and usually have separate DBMS-specific configurations. If the lock timeout is shorter than the transaction timeout, the database may return a lock error before the transaction reaches its overall limit.

When lock waits are observed, identify the transaction holding the lock, table update order, and contention level. Increasing the transaction timeout does not fix deadlocks or lock contention; sometimes it even forces other transactions to wait longer.

### Transaction timeout and network timeout

A SQL query or HTTP call can hang waiting on the network. Network/socket timeouts are controlled by the driver or client. A transaction timeout cannot always interrupt a hung network connection.

Configure timeouts for the JDBC driver, HTTP client, and message client according to service characteristics. Timeouts should have a sensible relationship with the transaction timeout and the overall operation deadline.

## 6. When is transaction timeout applied?

In Spring, timeout is an attribute of a new transaction. If a method joins an already existing transaction with REQUIRED propagation, it typically participates in the current transaction and cannot alter the timeout that was applied when that transaction began.

For example:

~~~java
@Transactional(timeout = 30)
public void updateOrders() {
    // ...
}
~~~

If updateOrders is called from a Tasklet running inside the Step's transaction, default REQUIRED propagation means the method joins the current transaction. The timeout annotation on the method does not automatically turn the running transaction into a 30-second transaction.

If the method is called independently and creates a new transaction via a Spring proxy, a 30-second timeout can be applied to that transaction, depending on the transaction manager.

Do not add REQUIRES_NEW just to force a timeout without considering the consequences. REQUIRES_NEW creates an independent transaction that can commit data even if the outer transaction rolls back. This alters atomicity and can leave metadata or business data out of sync.

### Note on self-invocation

With proxy-based transaction management, calling a @Transactional method from another method in the same object usually bypasses the proxy. Thus, annotations and timeouts may not be applied as expected. If a separate transaction is needed, organize beans and call boundaries properly instead of relying on self-invocation.

## 7. What happens when a transaction times out?

Specific behavior depends on the transaction manager, database, and resources. In a typical JDBC setup:

1. The Step starts a transaction for the chunk or Tasklet pass.
2. Reader, processor, or writer performs work.
3. The transaction exceeds the timeout.
4. A resource access operation may receive a timeout error, or the transaction is marked rollback-only.
5. The exception escapes the Step if not handled properly.
6. The transaction manager rolls back the current transaction.
7. StepExecution is recorded with a failure status if the Step has no suitable error-handling flow.

Several exceptions can appear depending on the layer:

- TransactionTimedOutException from Spring.
- QueryTimeoutException from Spring JDBC.
- SQLTimeoutException from JDBC.
- Database- or driver-specific exceptions.

Do not catch only a single exception class if drivers and resources can wrap errors differently. Classify using the exception hierarchy, root cause, and appropriate database error codes.

### Timeout does not necessarily halt Java code immediately

If a processor is running a pure CPU calculation for 90 seconds, a 60-second transaction timeout does not necessarily interrupt the thread at second 60. Timeout checks may only happen when the application accesses a resource or the transaction manager performs a commit operation.

For CPU-bound work or external calls, separate deadlines, cancellation, or timeouts are needed on the executing component. Do not rely on transaction timeout to control the execution time of arbitrary code.

## 8. Timeout, rollback, and Step status

If a timeout exception escapes a chunk transaction, the current transaction typically rolls back. Previously committed chunks remain intact.

~~~text
Chunk 1: processed successfully -> COMMIT
Chunk 2: processed successfully -> COMMIT
Chunk 3: exceeded transaction timeout -> ROLLBACK
Chunk 4: not yet processed
~~~

If the Step fails, the Job may end as FAILED or branch to an error-handling flow as configured. On restart, Spring Batch creates a new JobExecution for the same JobInstance if the Job allows restarts and identifying parameters are preserved.

With a multi-pass Tasklet, previously committed passes are not rolled back merely because a later pass times out. If the Tasklet does not save checkpoints, a restart may have to re-execute already completed work. Design idempotency or checkpoints to avoid creating duplicate data.

### Do not swallow timeout exceptions

Do not catch a timeout and return FINISHED:

~~~java
Tasklet tasklet = (contribution, chunkContext) -> {
    try {
        service.process();
    } catch (QueryTimeoutException ex) {
        log.error("Query timed out", ex);
    }

    return RepeatStatus.FINISHED;
};
~~~

Writing code like this can mark the Step as completed even though the database operation failed or the transaction was marked rollback-only. If a timeout error means work is incomplete, let the exception propagate so TaskletStep handles it:

~~~java
Tasklet tasklet = (contribution, chunkContext) -> {
    service.process();
    return RepeatStatus.FINISHED;
};
~~~

If logging is needed, log and rethrow the exception, preserving the cause.

## 9. Choosing an appropriate timeout

Too short a timeout can fail a Step when the system is only temporarily slow. Too long a timeout can hold connections and locks longer, prolonging incidents and impacting other transactions.

When choosing a timeout, consider:

- Normal processing time of a chunk or Tasklet pass.
- High-percentile processing time under realistic load, not just averages.
- Number of items and data size per chunk.
- Query, write, and commit latency.
- Expected lock wait times and database limits.
- External service call durations if any.
- Default transaction timeout of the transaction manager.
- Query timeout, connection timeout, and network timeout.
- Business process deadline requirements.

One approach is to measure chunk duration under normal and peak load, then set the timeout above normal operating levels while staying low enough to release resources during incidents. The buffer should be grounded in system metrics.

For example, if 99% of chunks finish in 8 seconds, but some take 25 seconds under high load, a 10-second timeout could trigger frequent failures. A 60-second timeout may be more suitable if the database and business requirements allow it. This is an illustrative example only; there is no single standard value for every application.

### Consider chunk size

Chunk size affects transaction duration. If an item averages 100 ms and a chunk has 500 items, sequential processing alone can take around 50 seconds, not counting reader, writer, commit, and overhead. A 30-second timeout may be insufficient.

You can:

- Reduce chunk size for shorter transactions.
- Optimize slow processors or queries.
- Use more efficient batch writes.
- Move non-transactional operations out of the transaction if business design permits.
- Increase timeout after assessing locks, connections, and database capacity.

Do not just raise the timeout to mask an unsuitable chunk size.

## 10. Timeouts when calling external services

A Tasklet or ItemProcessor sometimes calls a REST API, message broker, or other service. These calls typically fall outside the Step's JDBC transaction.

For example, a Tasklet opens a database transaction, calls an HTTP API taking 2 minutes, and only then updates status. If the transaction timeout is 60 seconds, the transaction may have expired before the HTTP call returns. Yet the request may still have been processed by the server.

A better design is usually:

1. Read or write preparatory state in a short transaction.
2. Commit the necessary state.
3. Make the remote call with connect/read timeouts and an idempotency key.
4. Record the result in a new transaction.
5. Potentially retry or reconcile if the remote outcome is indeterminate.

Not every business flow can be split this way. If atomicity across database and external systems is required, use suitable architectures like outbox, saga, or distributed transaction protocols supported by the systems. A single transaction timeout does not provide cross-service atomicity.

## 11. Retrying on timeout

Timeouts can be transient errors, but should not always be retried. Before retrying, determine:

- Did the timeout happen during connection acquisition, query execution, lock wait, or external service call?
- Has the operation already been executed by the server?
- Did the transaction definitely roll back?
- Could a retry cause duplicate side effects?
- Are there attempt limits and backoff?
- Are circuit breakers or concurrency limits needed?

For transient query errors, bounded retries may be appropriate. For a query that consistently times out due to missing indexes or full table scans, retries only add extra load to the database.

For HTTP timeouts, the client may not know whether the server processed the request. Use an idempotency key or query the operation status before resending.

In a chunk-oriented Step, retry can be configured for an appropriate exception:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

This example only illustrates retries for a group of transient data access errors. Inspect the actual exceptions emitted by the driver and how Spring translates them. Do not retry every QueryTimeoutException if timeouts are a symptom of overly slow queries or prolonged lock contention.

## 12. Monitoring transaction timeouts

To pinpoint where timeouts originate, combine Spring Batch metadata with application and database metrics.

### Spring Batch metadata

JobRepository stores JobExecution and StepExecution states. Use JobExplorer to inspect:

- Which JobExecution and StepExecution FAILED.
- ExitStatus and failure exception.
- Read count, write count, skip count, and commit count.
- Step start and end times.

Metadata tells you the Step failed, but may not suffice to pinpoint the exact SQL statement or resource causing the timeout.

### Application logs

Log Job name, JobExecutionId, Step name, business key, chunk size, and exception type. Do not log credentials or sensitive payloads.

### Database metrics

Monitor:

- Query duration and query timeouts.
- Lock waits, deadlocks, and long-open transactions.
- Connection pool usage and connection acquisition time.
- CPU, I/O, buffer/cache, and session counts.
- SQL queries with abnormal runtimes.

If a Step times out yet the database shows no slow queries, the cause may lie in the processor, external service calls, or CPU-bound code. Instrumenting each stage helps locate where time is being spent.

## 13. Common mistakes

### Confusing transaction timeout with Job timeout

Transaction timeout caps a chunk's or Tasklet pass's transaction. It does not cap the total runtime of the entire Job.

### Only setting @Transactional timeout on a service called inside a Step

If the service joins the current transaction with REQUIRED propagation, the annotation's timeout does not alter the timeout set when the Step transaction began. Configure the timeout at the boundary that actually creates the transaction.

### Increasing timeout to deal with slow queries

Raising the timeout may give a query more time, but does not fix missing indexes, poor execution plans, or lock contention. Investigate the query before increasing limits.

### Thinking transaction timeout cancels HTTP requests

The transaction manager does not automatically control timeouts of HTTP clients. Configure connect/read timeouts or deadlines on the client separately.

### Using long timeouts for transactions with many side effects

Long transactions hold resources longer and raise the chance that external side effects have occurred before rollback. Keep transactions short when possible and design idempotency.

### Retrying timeouts infinitely

Unbounded retries can overload an already strained database or service even further. Use retry limits, backoff, and exception classification.

### Not verifying the transaction manager and driver

Timeouts are applied differently across transaction managers, JDBC drivers, and databases. Test in a production-equivalent environment to verify actual behavior.

### Reducing timeout without checking chunk duration

An oversized chunk can exceed the timeout even when the system runs normally. Evaluate chunk size, item processing time, and writer alongside the timeout.

## 14. Procedure for configuring and handling timeouts

When implementing transaction timeouts for a Step, you can follow this sequence:

1. Identify the transaction boundary: per chunk or per Tasklet pass.
2. Measure normal and peak-load transaction durations.
3. Determine the time spent in reader, processor, writer, commit, and resource waits.
4. Choose a timeout with headroom suited to business requirements.
5. Configure TransactionAttribute on the Step or the boundary that actually creates the transaction.
6. Configure query, lock, connection, and network timeouts separately per resource.
7. Verify that the transaction manager and driver enforce the timeout as expected.
8. Test slow queries, lock waits, and hung external services.
9. Confirm rollback, BatchStatus, ExitStatus, and restartability.
10. Add bounded retries only for genuinely recoverable errors.

A timeout configuration is only considered suitable when it both protects resources and does not fail the Step under valid load. Keep monitoring after deployment because data volumes and load can change over time.

## Conclusion

Transaction timeout limits the duration of a transaction managed by the transaction manager. In Spring Batch, it typically applies to each chunk of a chunk-oriented Step or each Tasklet invocation, not the whole Job. It can be configured via TransactionAttribute and setTimeout, though it must be distinguished from query, lock, connection, and network timeouts. When a timeout occurs, the current transaction may roll back and the Step fail; previously committed chunks remain intact. Choose timeouts based on real metrics, keep transactions short, classify retries, and design checkpoints/idempotency for safe recovery.
