# Handling errors when a writer writes partially

In Spring Batch, `ItemWriter` typically receives an entire chunk and writes multiple items in a single call. If the writer writes several items and then encounters an error, the outcome depends on the resource the writer uses and whether that resource participates in the chunk transaction.

For a database using the same transaction manager as the Step, write statements executed before the exception are usually rolled back with the chunk. For directly written files, HTTP APIs, message brokers, or independent databases, changes already accepted by the external system may still remain after the Step's transaction rolls back.

Therefore, handling partial-write errors requires answering three questions:

1. Which operations had the writer already executed before the error?
2. Did those operations participate in the chunk transaction?
3. Upon retry, skip, or restart, can the writer be invoked again without creating duplicate data or inconsistent state?

## 1. Writers write by chunk

In a chunk-oriented Step, Spring Batch reads items, processes items, and passes the results to the writer. A transaction typically wraps the entire chunk processing cycle.

~~~text
Start transaction
        |
        v
ItemReader reads items
        |
        v
ItemProcessor processes items
        |
        v
ItemWriter.write(chunk)
        |
        +---- Write succeeds
        |         |
        |         v
        |   Update checkpoint
        |         |
        |         v
        |       COMMIT
        |
        +---- Write fails
                  |
                  v
          Rollback policy
                  |
                  v
              ROLLBACK
                  |
                  v
          Retry / Skip / FAILED
~~~

Example Step configuration:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

With a chunk size of 100, the writer typically receives up to 100 items in one invocation. If the writer fails, Spring Batch handles the exception according to the Step's transaction and fault-tolerance policies.

A chunk is not a sequence of independent commits per item. When a database writer participates in the same transaction, write operations in the chunk are confirmed when the transaction commits. If the transaction rolls back, all changes participating in that transaction are undone.

## 2. Example: writer writes partially then throws an exception

Suppose a chunk contains four orders: A, B, C, and D. The writer writes each order:

~~~java
public class OrderWriter implements ItemWriter<Order> {

    private final OrderRepository repository;

    public OrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            repository.save(order);

            if ("C".equals(order.orderNumber())) {
                throw new OrderWriteException(
                        "Simulated failure at order C");
            }
        }
    }
}
~~~

If `repository` uses the same database and transaction manager as the Step, the sequence can be:

~~~text
Chunk transaction starts
        |
        v
Write A -> succeeds inside transaction
        |
        v
Write B -> succeeds inside transaction
        |
        v
Write C -> exception thrown
        |
        v
Exception escapes writer
        |
        v
Transaction rolls back
        |
        v
A, B, and other changes
in the transaction are undone
~~~

Distinguish "SQL statement ran successfully" from "data committed". A and B may have been processed by the database, yet not confirmed by the transaction. If the transaction rolls back cleanly, those changes no longer exist in the database.

If the repository opens its own new transaction or commits each item individually, the outcome differs. In that case A and B may already be independently committed and the chunk transaction cannot undo them.

## 3. Conditions for rolling back everything already written

To roll back writes executed prior to an exception, operations must participate in the same rollback-capable transaction.

Important conditions:

- The writer uses a transactional database or resource.
- The writer uses the same transaction manager and resource managed by the Step.
- Write operations do not commit independently.
- The exception propagates out of the writer so the framework sees it.
- The Step's rollback policy classifies the exception as requiring rollback.
- No operations were committed in an independent transaction before the chunk failed.

JDBC writer example:

~~~java
@Bean
public JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO orders (id, order_number, amount)
                VALUES (:id, :orderNumber, :amount)
                """)
            .beanMapped()
            .build();
}
~~~

The transaction manager must manage the exact `DataSource` used by the writer:

~~~java
@Bean
public PlatformTransactionManager transactionManager(
        DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
~~~

With proper configuration, `JdbcBatchItemWriter` uses Spring JDBC infrastructure to participate in the current transaction. If a statement in the batch fails and the exception propagates, the chunk transaction can roll back changes made earlier.

With JPA, flushing `EntityManager` may send SQL to the database before commit. Flushing does not mean committing; if the transaction remains active and later rolls back, database changes belonging to that transaction are undone.

## 4. Do not commit item by item in the writer

A custom writer can accidentally break the chunk transaction if it acquires new connections directly and commits each item.

Unsuitable example when wanting whole-chunk rollback:

~~~java
@Override
public void write(Chunk<? extends Order> chunk) throws Exception {
    for (Order order : chunk) {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            saveOrder(connection, order);

            connection.commit();
        }
    }
}
~~~

Each item is committed in an independent transaction. If item C fails, the outer chunk transaction cannot roll back the already-committed transactions of A and B.

For custom JDBC writers, use `JdbcTemplate`, `NamedParameterJdbcTemplate`, or `DataSourceUtils` to obtain the connection bound to the current Spring transaction. Avoid calling `commit` directly if you want the writer to participate in the chunk transaction.

Also check the transaction propagation of services called by the writer. A method using `REQUIRES_NEW` starts an independent transaction; if that transaction commits, its data can persist even if the outer chunk rolls back.

## 5. Exceptions must propagate to Spring Batch

Spring Batch needs to know the writer failed in order to perform rollback and apply retry/skip policies.

An unsafe approach is catching the exception and only logging it:

~~~java
@Override
public void write(Chunk<? extends Order> chunk) {
    try {
        repository.saveAll(chunk.getItems());
    } catch (DataAccessException exception) {
        log.error("Could not write order chunk", exception);
        // Returns normally even though the write failed.
    }
}
~~~

When the writer returns normally, the framework may treat the write call as successful and proceed to update the checkpoint/commit. If partial data was written, state may be inconsistent with application intent.

A better approach:

~~~java
@Override
public void write(Chunk<? extends Order> chunk) {
    try {
        repository.saveAll(chunk.getItems());
    } catch (DataAccessException exception) {
        log.error("Could not write order chunk", exception);
        throw exception;
    }
}
~~~

If wrapping the exception in a custom type is required, preserve the cause:

~~~java
throw new OrderWriteException(
        "Could not persist the current chunk",
        exception);
~~~

Do not convert every error into one generic exception that strips information needed by the retry classifier, skip classifier, or diagnostic logs.

## 6. Distinguishing write failure from commit failure

There are two distinct failure points.

**Write failure** occurs while `ItemWriter.write()` is executing and throws an exception. The framework receives the error immediately during writing, then applies rollback and fault-tolerance policies.

**Commit failure** occurs after the writer returns successfully, while the transaction manager is committing. For example, the connection drops right as the database processes the commit.

For a write failure, the application usually knows the writer threw an exception before commit. For a commit failure caused by connection loss, the outcome can be ambiguous: the database may have committed while the client never received acknowledgement.

When the commit outcome is uncertain:

- Do not assume for certain that the data rolled back.
- Do not blindly repeat non-idempotent operations.
- Use business keys or unique constraints to verify state.
- Re-query the database once connectivity recovers.
- Design the writer to be safe to re-run.

Idempotency is an essential part of recovery when commit outcome cannot be determined from the client side.

## 7. Retrying when a writer writes partially

Retry suits transient errors where the next attempt has a chance to succeed, such as a database deadlock or short-lived connection failure.

Example:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

If the writer writes several items and then hits a deadlock, the current transaction is rolled back per policy. The framework can retry the work per the retry policy. Database changes from the rolled-back attempt will no longer exist if they genuinely participated in the same transaction.

Retry can cause the writer to be called again with the same chunk. Therefore, the writer must not assume each chunk is invoked only once. If the writer triggers non-transactional side effects, re-invocation can cause duplicate effects.

Retry specific exceptions, set finite limits, and consider backoff. Do not retry every `RuntimeException` because programming bugs, SQL errors, or invalid data usually do not resolve on their own.

## 8. Write skip when one item breaks the entire chunk

Write skip allows bypassing an item causing a write error if business rules accept dropping that item.

Example:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(DuplicateOrderException.class)
        .skipLimit(20)
        .build();
~~~

Because the writer typically receives the entire chunk, the framework may not immediately know which item caused the error. With write skip, Spring Batch can roll back the failed write and re-attempt the writer with smaller sets of items to isolate the failing item.

Illustration:

~~~text
Writer receives [A, B, C, D]
          |
          v
Chunk write fails
          |
          v
Roll back write
          |
          v
Isolate failing item
          |
          +--> A writes OK
          +--> B fails -> skip
          +--> C writes OK
          +--> D writes OK
          |
          v
Chunk continues per policy
~~~

This is a conceptual model. Exact writer invocation counts and splitting behavior depend on the fault-tolerance mechanism, writer type, and Spring Batch version.

Because the writer can be called again with different subsets of items, it must have clear transaction semantics and avoid non-idempotent side effects.

## 9. Retry and skip can be combined

An exception can be both retryable and skippable. The framework can retry first; if retries are exhausted, the item is skipped only if the exception is also allowed to be skipped and the skip limit has not been exceeded.

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
~~~

Classify errors by root cause:

| Writer error | Handling direction |
|---|---|
| Deadlock | Bounded retry |
| Temporary database connection loss | Retry or fail after limit |
| One item violates a data constraint | Skip if business rules permit |
| Invalid SQL or incompatible schema | Fail |
| Database out of disk space | Fail and resolve infrastructure incident |
| Unable to isolate failing item in external batch | Fail or use a dedicated reconciliation flow |

Do not skip broad infrastructure errors just to make the Job complete. A database unable to accept writes is a Step-wide failure, not an isolated item that can be safely discarded.

## 10. Recording skipped items

`SkipListener` provides separate callbacks for read, process, and write errors:

~~~java
public interface SkipListener<I, O> {
    void onSkipInRead(Throwable exception);
    void onSkipInProcess(I item, Throwable exception);
    void onSkipInWrite(O item, Throwable exception);
}
~~~

Example recording an item that failed in the writer:

~~~java
@Component
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedOrderRepository repository;

    public OrderSkipListener(RejectedOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onSkipInRead(Throwable exception) {
        // Record read error if source metadata is available.
    }

    @Override
    public void onSkipInProcess(
            OrderInput item,
            Throwable exception) {
        // Record processing error.
    }

    @Override
    public void onSkipInWrite(
            Order item,
            Throwable exception) {
        repository.save(
                RejectedOrder.from(item, exception.getMessage()));
    }
}
~~~

If the rejected record is written to the same database and transaction manager as the Step, it can participate in the appropriate transaction of the skip flow. If the listener sends an email or calls an API, those effects do not automatically roll back with the database.

Store the business key, exception type, source details, and associated `JobExecution`/`StepExecution`. Avoid storing sensitive payloads or huge stack traces in the rejected table.

## 11. File writers and partial writes

Standard files do not participate in JDBC transactions. If a writer writes several lines and then throws an exception, a database rollback does not automatically delete lines already written to the file.

~~~text
Chunk starts
    |
    v
Write line A to file
    |
    v
Write line B to file
    |
    v
Writing line C fails
    |
    v
Database transaction rolls back
    |
    v
File may still contain A and B
~~~

With `FlatFileItemWriter`, Spring Batch provides transactional buffering to coordinate output with chunk transactions when properly configured. Use built-in writers and verify transactional, `saveState`, and restart options rather than assuming file streams can roll back.

With custom file writers, you can use these strategies:

- Write to a temporary file per `JobExecution` or partition.
- Publish/rename to the final file only when the Job completes.
- Save checkpoints and write offsets for recovery.
- Truncate uncommitted portions on restart if the design permits.
- Run a post-failure output verification and reconciliation step.

Do not open the file in truncate mode on every writer invocation if multiple chunks must be written. Also do not close the file after every chunk if the writer is managed by the `ItemStream` lifecycle.

## 12. HTTP APIs, message brokers, and external side effects

When a writer sends data to an API or broker, the Step's database transaction does not automatically control the target system's transaction.

Example:

~~~text
Writer processes chunk
       |
       +--> API receives order A (succeeds)
       |
       +--> API receives order B (succeeds)
       |
       +--> API order C times out
       |
       v
Chunk fails
       |
       v
Database rolls back
       |
       v
API may still retain A and B
~~~

If the framework retries the chunk, requests A and B may be sent again. If the API does not support idempotency, the target system can create duplicate records or effects.

Protective measures:

- Use a stable idempotency key derived from the business key.
- Require the target system to recognize already-processed requests.
- Write outbound requests to an outbox in the same transaction as business data.
- Have a separate worker read the outbox and dispatch requests.
- Store external request IDs and response statuses for reconciliation.
- Design compensating actions if partial side effects cannot be avoided.

You cannot guarantee exactly-once between a database and an arbitrary API merely by making HTTP calls inside `ItemWriter`.

## 13. Transactional outbox for multi-target writers

If business data must be saved to a database and then sent to another system, an outbox persists the send request in the same transaction.

~~~text
Chunk transaction
       |
       +--> INSERT order
       |
       +--> INSERT outbox_event
       |
       v
     COMMIT
       |
       v
Outbox worker reads unsent events
       |
       v
Send to external system
       |
       v
Mark event as processed
~~~

If the transaction rolls back, both the order and the outbox event roll back. If commit succeeds and the JVM stops afterward, the event remains in the database for the worker to process later.

An outbox does not by itself guarantee exactly-once at the target system. The worker may resend if it does not receive confirmation or crashes before updating status. Therefore, the target system should still support idempotency or event ID deduplication.

## 14. Composite writers and multiple delegates

A composite writer can write the same chunk to multiple targets:

~~~text
Composite ItemWriter
       |
       +--> JDBC writer
       |
       +--> File writer
       |
       +--> HTTP writer
~~~

If the JDBC writer succeeds and then the file writer fails:

- JDBC changes can roll back if participating in the chunk transaction.
- The file may retain written content if transactional buffering is absent.
- Succeeded HTTP requests may not be revocable.
- A delegate using its own transaction may have committed independently.

A composite writer does not automatically turn its delegates into a distributed transaction. Determine invocation order, owned resources, and the transaction semantics of each delegate.

If targets must remain consistent, consider writing to one transactional source first and then using an outbox or a separate publish workflow. Avoid writing directly to multiple independent resources while assuming one rollback will undo all of them.

## 15. Which listeners help observe write errors?

Several listeners are useful:

- `ItemWriteListener.onWriteError`: called when the writer throws an exception.
- `ChunkListener.afterChunkError`: observes the error branch of a chunk after rollback.
- `SkipListener.onSkipInWrite`: records items skipped during writing.
- `StepExecutionListener.afterStep`: summarizes Step results.

Example:

~~~java
@Component
public class OrderWriteListener
        implements ItemWriteListener<Order> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderWriteListener.class);

    @Override
    public void beforeWrite(Chunk<? extends Order> items) {
        log.debug("Writing {} orders", items.size());
    }

    @Override
    public void afterWrite(Chunk<? extends Order> items) {
        log.debug("Writer returned for {} orders", items.size());
    }

    @Override
    public void onWriteError(
            Exception exception,
            Chunk<? extends Order> items) {
        log.error(
                "Writer failed for chunk with {} items",
                items.size(),
                exception);
    }
}
~~~

`afterWrite` only indicates the writer call returned normally. It does not prove the transaction committed. If transaction commit fails afterward, the chunk can still roll back.

Include `JobExecution` ID, `StepExecution` ID, partition name, and business keys in logs to pinpoint the exact chunk or worker that failed.

## 16. Monitoring rollbacks and write outcomes

`StepExecution` provides useful counters:

| Counter | Meaning |
|---|---|
| `writeCount` | Number of items written per Step statistics |
| `writeSkipCount` | Number of items skipped in the write phase |
| `commitCount` | Number of commits recorded |
| `rollbackCount` | Number of rollbacks recorded |
| `readCount` | Number of items read successfully per statistics |
| `filterCount` | Number of items filtered by the processor |
| `status` | Step execution status |
| `exitStatus` | Step exit status code |

You can summarize after the Step:

~~~java
@Override
public ExitStatus afterStep(StepExecution stepExecution) {
    log.info(
            "Step result: writes={}, writeSkips={}, commits={}, rollbacks={}",
            stepExecution.getWriteCount(),
            stepExecution.getWriteSkipCount(),
            stepExecution.getCommitCount(),
            stepExecution.getRollbackCount());

    return stepExecution.getExitStatus();
}
~~~

Counters help detect excessive rollbacks, unusual spikes in write skips, or a Step completing with fewer written items than expected. To find the root cause, combine counters with exception logs and business keys.

Do not assume `writeCount` equals the number of committed SQL statements if the writer writes to multiple tables or causes non-transactional side effects. Counters are Step execution metrics, not a substitute for target data reconciliation.

## 17. Testing a writer that writes partially and then fails

An integration test should run the Step against a transactional database and verify that changes made before the exception are gone after rollback.

Illustrative example:

~~~java
@Test
void rollsBackEarlierWritesWhenWriterFailsMidChunk() {
    ItemWriter<Order> failingWriter = chunk -> {
        jdbcTemplate.update(
                "INSERT INTO orders(id, order_number) VALUES (?, ?)",
                1L, "ORD-A");

        jdbcTemplate.update(
                "INSERT INTO orders(id, order_number) VALUES (?, ?)",
                2L, "ORD-B");

        throw new OrderWriteException("Failure after two inserts");
    };

    JobExecution execution = launchStepWith(failingWriter);

    assertEquals(BatchStatus.FAILED, execution.getStatus());
    assertEquals(0, countOrders());
}
~~~

This test assumes `jdbcTemplate` uses the same `DataSource` and transaction manager as the Step, inserts do not auto-commit, and the exception triggers rollback. After the Job ends, query using an independent connection to verify the data does not exist.

Do not wrap the test in an outer transaction that interferes with inspecting the Step transaction outcome. Observe the database after the Step's transaction has ended.

### Scenarios to test

- Writer fails before writing the first item.
- Writer writes partially and then throws an exception.
- Writer succeeds, but transaction commit fails.
- Deadlock is retried and then succeeds.
- Retries are exhausted.
- Write skip isolates the failing item.
- Skip limit is exceeded.
- Writer writes to a file and fails mid-way.
- Writer calls an API and is retried.
- Composite writer has a delegate fail in the middle.
- Job restarts after rollback and restores the checkpoint properly.

## 18. Testing writers with non-transactional side effects

For files or APIs, tests should prove that a database rollback does not automatically revoke external side effects.

Example using a mock API client:

~~~java
@Test
void externalRequestCanRemainAfterDatabaseRollback() {
    when(shippingClient.createShipment(any()))
            .thenReturn("TRACK-001");

    // Run Step: API is called, then writer/database fails.
    JobExecution execution = launchJobWithFailingWriter();

    assertEquals(BatchStatus.FAILED, execution.getStatus());
    verify(shippingClient).createShipment(any());
    assertEquals(0, countCommittedOrders());
}
~~~

This test illustrates that the API may have already received the request even though database data rolled back. In real applications, add tests for idempotency keys or outboxes to guarantee restarts do not create duplicate shipments.

## 19. Common mistakes

### Thinking the database keeps partial writes from a failing writer

If all operations participate in the same transaction and rollback succeeds, writes before the exception are also undone. Only operations committed independently or outside the transaction can remain.

### Writer catches the exception and returns normally

The framework may treat the write as successful and commit. Propagate exceptions out when write operations fail.

### Committing item by item manually

Already-committed independent transactions cannot be rolled back by the outer chunk transaction. Use Spring JDBC infrastructure to participate in the current transaction.

### Thinking files and HTTP APIs roll back with the database

Standard files and external APIs do not automatically participate in JDBC transactions. Use transactional buffering, staging, idempotency, or an outbox.

### Retrying a non-idempotent writer

The writer can be called again after rollback or while the framework isolates a failing item. Side effects may be repeated.

### Using skip for broad infrastructure errors

A down database or full disk is not an error belonging to a single item. Skipping can cause widespread data loss.

### Using noRollback to keep partial writes

`noRollback` changes rollback classification; it does not fix partial state. If a writer wrote several items and then threw an exception, the transaction may commit unintended results.

### Confusing afterWrite with a successful commit

`afterWrite` runs after the writer call returns, but before the chunk transaction finishes. Data can still roll back after the callback.

### Ignoring commit failures

Connection loss during commit can leave the client unsure whether the transaction was confirmed. Writers need business keys and idempotency.

## 20. Workflow for handling partial-write errors

When a writer fails, trace these points:

1. Did the exception occur inside `write()` or during transaction commit?
2. Which operations had the writer already executed before the error?
3. Do those operations share the Step's transaction manager and resource?
4. Did the writer open its own connection or commit a separate transaction?
5. Did the exception propagate out of the writer?
6. Does the rollback policy require rolling back for that exception?
7. Can the error be retried safely and what is the retry limit?
8. If retries are exhausted, is the item allowed to be skipped?
9. Can write skip isolate the exact failing item?
10. Does the writer have non-transactional side effects requiring idempotency?
11. Do files or APIs require staging, an outbox, or reconciliation?
12. Are `StepExecution` counters and logs sufficient to identify the failing chunk?
13. After a restart, do reader/writer restore from an appropriate checkpoint?

When a writer uses transactional resources properly and exceptions propagate to Spring Batch, rollback can undo all chunk changes on that resource, including writes executed before the failure. For files, APIs, or independent systems, add transactional buffering, staging, idempotency, an outbox, or reconciliation. Clearly distinguishing write failures, commit failures, and non-transactional side effects is the foundation for Jobs that can retry, skip, or restart without duplicate data or incomplete state.
