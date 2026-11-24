# Rollback When the Writer Fails

In Spring Batch, a chunk-oriented Step typically processes each chunk inside a transaction. When an **ItemWriter** throws an exception while writing a chunk, Spring Batch applies the Step's rollback policy. If the exception is classified as requiring rollback, the chunk's transaction is aborted and changes made to resources participating in that transaction are undone.

This protects database data when the writer has already written part of the chunk before hitting an error. For example, a writer executes 100 inserts, the first 60 succeed, and the 61st fails. If all statements use the chunk's same database transaction, rollback undoes all 60 earlier inserts as well.

However, rollback only undoes resources that actually participate in the transaction. Sent emails, HTTP requests already processed by a server, or files written directly are not automatically restored. Therefore, when a writer fails, you must identify the transaction manager, write resources, exception types, and retry/skip policies before concluding which data has been undone.

## 1. How Does the Transaction Wrap the Writer Call?

With chunk processing, a transaction is opened for each chunk. The reader reads items, the processor produces results, and the writer writes the chunk within the execution scope managed by the Step.

~~~text
Start chunk transaction
          |
          v
ItemReader reads item
          |
          v
ItemProcessor processes item
          |
          v
ItemWriter.write(chunk)
          |
          +---- Succeeds
          |         |
          |         v
          |    Update checkpoint
          |         |
          |         v
          |       COMMIT
          |
          +---- Throws exception
                    |
                    v
              Rollback policy
                    |
                    v
                 ROLLBACK
                    |
                    v
           Retry / Skip / Step FAILED
~~~

The transaction manager is passed into the chunk configuration:

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

In this example, each chunk of up to 100 items is one transaction unit of the Step. After the writer returns successfully, the framework still updates stream state and metadata before committing the transaction. Thus, the writer completing does not guarantee the chunk has committed; an error in a later phase can still cause the transaction to roll back.

## 2. What Happens When the Writer Partially Writes and Then Fails?

Suppose a chunk contains 100 orders. The writer inserts the orders sequentially into the same database:

~~~text
Chunk of 100 orders
          |
          v
INSERT order 1   -> succeeds
INSERT order 2   -> succeeds
...
INSERT order 60  -> succeeds
INSERT order 61  -> fails
          |
          v
Exception escapes writer
          |
          v
Transaction rollback
          |
          v
Changes within the transaction
are rolled back
~~~

If all insert statements participate in the same database transaction, the statements executed before the error are also rolled back. After rollback, the database does not retain the first 60 orders of that chunk.

Previously committed chunks remain intact. For example, a Step has a chunk size of 100 and committed the first two chunks, but the third chunk fails:

| Chunk | Result | Data |
|---|---|---|
| Chunk 1 | COMMIT | Preserved |
| Chunk 2 | COMMIT | Preserved |
| Chunk 3 | ROLLBACK | Chunk changes undone |
| Chunk 4 | Not yet run | Not yet processed |

The rollback of chunk 3 does not reverse the transactions already committed in chunks 1 and 2. When the Job restarts, the Step can resume from the checkpoint saved at the most recent commit if the reader supports state restoration.

## 3. Conditions for Writer Data to Actually Roll Back

For rollback to take effect on data written by the writer, consider the following conditions:

1. The writer uses a transactional resource, such as a database that supports transactions.
2. The writer participates in the transaction managed by the Step.
3. The writer and Step use the matching transaction manager and resource.
4. The exception propagates out of the writer so the framework detects it.
5. The rollback policy classifies the exception as requiring rollback.
6. No independent transaction committed earlier containing the same changes.

Example with JDBC:

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

If the writer's DataSource is the same DataSource managed by the Step's transaction manager, the write statements can participate in the chunk transaction through Spring JDBC.

If the writer uses a different DataSource or opens an independent connection and commits it, the Step's transaction does not automatically roll back those changes. Check how connections are obtained and managed; do not rely solely on the writer being called inside a transactional Step.

## 4. Example Writer Sharing the Same Database Transaction

A typical JDBC setup binds the transaction manager to the business DataSource:

~~~java
@Bean
public PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
~~~

The writer uses the same DataSource:

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

When a write statement fails and the transaction rolls back, database changes in the chunk are undone according to the database's transaction semantics.

Do not acquire a new connection inside the writer and commit it manually:

~~~java
// Unsuitable example when you want the writer to participate in the chunk transaction.
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    // Write data...
    connection.commit();
}
~~~

This code creates a transaction managed by the writer itself. If the writer commits independently, the Step's transaction manager cannot undo those changes if the chunk fails later.

For custom JDBC writers, prefer JdbcTemplate, NamedParameterJdbcTemplate, or DataSourceUtils to use the connection bound to the current Spring transaction. Avoid manual commits in the writer when the goal is to roll back the entire chunk.

## 5. Writer Throwing vs. Swallowing Exceptions

Spring Batch can apply error policies only when errors propagate to the framework.

Unsafe handling:

~~~java
@Override
public void write(Chunk<? extends Order> chunk) {
    try {
        repository.saveAll(chunk.getItems());
    } catch (DataAccessException ex) {
        log.error("Cannot write orders", ex);
        // Do not rethrow the exception.
    }
}
~~~

In this case, the writer catches the exception and returns normally. Spring Batch may treat the write call as successful and proceed to update checkpoints and commit. If partial data was written, the outcome may be unexpected.

A better approach:

~~~java
@Override
public void write(Chunk<? extends Order> chunk) {
    try {
        repository.saveAll(chunk.getItems());
    } catch (DataAccessException ex) {
        log.error("Cannot write order chunk", ex);
        throw ex;
    }
}
~~~

If you need to translate the exception to a custom type, preserve the root cause:

~~~java
throw new OrderWriteException(
        "Cannot persist the current order chunk",
        ex);
~~~

Do not catch an exception only to log it when the Step needs to know the write failed. Also avoid collapsing every exception into a generic type that loses information needed by retry/skip classifiers.

## 6. Rollback Policy and Exception Types

Rollback depends on the Step's rollback classifier and transaction attributes. Check the exception type, fault-tolerant configuration, and transaction policy of the Spring Batch/Spring version in use.

In a standard configuration, an unhandled write error fails the chunk and rolls back the transaction per the Step's default policy. For custom exceptions—especially checked exceptions—verify actual rollback rules rather than assuming every Throwable behaves identically.

You can configure the Step's transaction attributes to control isolation, propagation, and timeout:

~~~java
DefaultTransactionAttribute transactionAttribute =
        new DefaultTransactionAttribute();

transactionAttribute.setTimeout(60);

Step step = new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .transactionAttribute(transactionAttribute)
        .build();
~~~

Do not use broad rollback or noRollback settings just to keep a Step running. First understand what data the writer has modified and whether those changes could leave partial state.

## 7. Retry When the Writer Fails

If the writer encounters a potentially transient error, the Step can retry according to a fault-tolerant policy. Each attempt must obey proper transaction semantics; a failed write typically causes the current transaction to roll back before the framework makes the next attempt.

Example retrying a database deadlock:

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

Retry is appropriate when a subsequent attempt is likely to succeed, such as:

- Database deadlocks.
- Temporarily unavailable locks.
- Recoverable connection errors.
- Certain timeouts from external services.

Do not retry every write error. Constraint violations caused by invalid data usually do not resolve on retry. Invalid SQL or incompatible schemas must be fixed rather than retried futilely.

The retry limit must be finite. If backoff is needed, configure a wait policy between attempts to reduce pressure on an overloaded database.

## 8. Skip When the Writer Fails

Skip can be used when the writer fails because of a specific item and business rules allow excluding that item from the run's output.

For example, an order violates a write rule and can be placed in a rejected list:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
~~~

With write skip, Spring Batch may need to pinpoint the failing item by retrying the write in smaller groups or item by item, depending on the fault-tolerant mechanism. Thus, the writer may be called multiple times for different subsets of items.

This has an important consequence: **the writer must tolerate being called again**. Do not place non-idempotent side effects inside the writer while assuming write() is called strictly once per chunk.

Skip is inappropriate when an error prevents writing to the database altogether, such as the database being down or out of disk space. Skipping items individually in that situation only masks the outage and can lose large amounts of data.

## 9. Combining Retry and Skip for Write Errors

An exception can be configured as both retryable and skippable. In that case, Spring Batch can retry first; if retries are exhausted and the exception is still in the skippable group, the item can be skipped if the skip limit remains.

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

Policies must be clearly classified:

| Error Type | Handling Approach |
|---|---|
| Deadlock | Retry |
| Transient connection error | Bounded retry |
| Single order violates data constraint | Skip if business rules permit |
| Invalid SQL or schema mismatch | Fail |
| Database out of storage | Fail and resolve the incident |
| Failing item cannot be identified in an external batch | Typically fail or use a separate reconciliation workflow |

When retries are exhausted and the exception is not skippable, the Step fails. When the exception is skippable but total skips exceed skipLimit, the Step also fails.

## 10. Write Skip and Identifying the Failing Item

Unlike the processor, the writer typically receives the whole chunk. If a batch write statement fails, the exception may indicate only that the batch failed without pinpointing which item caused the error.

Spring Batch can use its fault-tolerant mechanism to re-examine the write and isolate the failing item. This may cause the writer to be invoked with smaller chunks during write-skip handling.

Example initial chunk:

~~~text
[A, B, C, D]
      |
      v
Writer writes entire chunk -> fails
      |
      v
Framework identifies failing item
      |
      +--> [A] -> succeeds
      +--> [B] -> fails -> skip if allowed
      +--> [C] -> succeeds
      +--> [D] -> succeeds
~~~

The diagram only illustrates the concept. How items are split, the number of writer invocations, and the retry order depend on configuration and framework version.

If the writer sends a single request for the whole chunk to an external API and the server returns a generic error without indicating the failing item, the framework cannot safely infer which record to skip. In that case, design the protocol to return per-item errors, or split batches proactively and reconcile.

## 11. SkipListener Recording Items Rejected by the Writer

When an item is skipped during the write phase, SkipListener can save the record and reason for later handling.

~~~java
@Component
public class OrderWriteSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedOrderRepository rejectedRepository;

    public OrderWriteSkipListener(
            RejectedOrderRepository rejectedRepository) {
        this.rejectedRepository = rejectedRepository;
    }

    @Override
    public void onSkipInRead(Throwable exception) {
        // Record read error if source information is available.
    }

    @Override
    public void onSkipInProcess(
            OrderInput item,
            Throwable exception) {
        // Record item skipped during processing.
    }

    @Override
    public void onSkipInWrite(
            Order item,
            Throwable exception) {

        rejectedRepository.save(
                RejectedOrder.from(item, exception.getMessage()));
    }
}
~~~

Registering the listener with the Step:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .listener(orderWriteSkipListener)
        .build();
~~~

SkipListener is invoked at the appropriate phase so error recording can participate in the chunk transaction. If rejectedRepository uses the same transaction manager and database, the error record can be committed with the chunk. If the listener sends data to an external system, a database rollback cannot undo that effect.

## 12. File Writers: Rollback Differs from Databases

Regular files do not participate in JDBC transactions. If a writer writes directly to a file and the database transaction then rolls back, bytes already written to the file are not automatically removed.

Example:

~~~text
Chunk transaction starts
        |
        v
Writer writes 50 lines to file
        |
        v
Writer encounters error on next line
        |
        v
Database transaction rolls back
        |
        v
File may still contain the 50 written lines
~~~

With FlatFileItemWriter, Spring Batch provides transactional buffering to coordinate file output with the chunk transaction when configured as transactional. Use built-in writers and verify configuration rather than managing streams manually without checkpoint/rollback support.

A custom writer writing directly to files needs a clear strategy:

- Write to a temporary file and publish only after the Job completes.
- Persist position or checkpoint for restart.
- Support truncating or restoring the uncommitted portion.
- Use output paths scoped by execution ID to avoid accidental overwrites.
- Reconcile files if the process terminates abnormally.

Do not assume a file writer has the same rollback semantics as JdbcBatchItemWriter.

## 13. Writers Calling APIs or External Systems

If a writer sends data to an HTTP API, message broker, or another service, the Step's database transaction does not automatically roll back effects that already occurred at the target system.

Example:

~~~text
Chunk starts
    |
    v
Send order A to API -> succeeds
    |
    v
Send order B to API -> succeeds
    |
    v
Send order C to API -> timeout
    |
    v
Chunk rolls back in database
~~~

The first two requests may already have been processed by the external system. If the Job retries the chunk, those requests may be sent again.

Ways to mitigate risk:

- Use a stable idempotency key derived from the order code.
- Require the target API to support checking whether a request was already processed.
- Write outbound requests to an outbox table in the same database transaction.
- Use a separate worker to send outbox entries and retry independently.
- Store external responses or transaction IDs for reconciliation.
- Design compensating operations if the target system does not support idempotency.

You cannot guarantee exactly-once delivery between a database and an arbitrary API simply by placing HTTP calls inside ItemWriter.

## 14. Composite Writers and Failures Between Delegates

A writer can forward the same chunk to multiple delegates, such as one delegate writing to a database and another writing to a file.

~~~text
Composite writer
       |
       +--> Database writer
       |
       +--> File writer
       |
       +--> Audit writer
~~~

If the database writer succeeds but the file writer fails, the outcome depends on each delegate's resource and transaction:

- The database can roll back if it participates in the chunk transaction.
- The file may still retain written content without a proper transactional buffer.
- An audit writer using REQUIRES_NEW may have committed independently.
- An external API may have already processed the request.

A composite writer does not automatically create a distributed transaction across all delegates. Check each writer, invocation order, resource ownership, and rollback semantics.

If multiple targets must stay consistent, consider an outbox or a publish workflow with explicit states rather than writing directly to multiple resources without a shared transaction.

## 15. noRollback Is Not a Fix for Writer Errors

Spring Batch allows configuring certain exceptions not to force a rollback via noRollback(...). This setting changes rollback classification; it does not skip the item automatically nor repair partially written data.

Example:

~~~java
.faultTolerant()
.noRollback(ValidationWarningException.class)
~~~

Use this only when the exception genuinely represents a situation where the transaction can still complete safely. If the writer already performed several writes and then threw an exception, suppressing rollback can cause the chunk to commit partial state.

Distinguish the three mechanisms:

| Mechanism | Meaning |
|---|---|
| Retry | Re-execute the failed operation |
| Skip | Skip the item according to policy and limit |
| noRollback | Do not roll back the transaction for the specified exception |

If a writer fails due to a genuine write error, rollback is usually the required behavior. Do not use noRollback to force a Job forward when the data state is unknown.

## 16. Exceptions During Write vs. Exceptions During Commit

These two scenarios must be distinguished.

**Write failure** occurs while ItemWriter.write() is executing and throws an exception. Spring Batch can apply retry/skip policies, roll back the transaction, and reprocess as configured.

**Commit failure** occurs after the writer returns successfully, while the transaction manager is committing. For example, the connection drops during commit or the database rejects the commit.

With a commit failure, the actual outcome is sometimes ambiguous if the connection breaks at the exact moment the database processes the commit. The application may not know for certain whether the transaction committed based solely on the client-side exception.

When the commit outcome is uncertain:

- Do not assume rollback definitely happened.
- Do not blindly resend non-idempotent operations.
- Use business keys or unique constraints to check whether data already exists.
- Query state from the database after connectivity recovers.
- Design the writer to be safe to re-run.

This is a key reason for making writers idempotent.

## 17. Retries Cause Writer Re-invocation: Idempotency Is Essential

When a chunk rolls back and is retried, the writer may be invoked again with the same data. For a database writer participating in the transaction, the previous write rolled back so the retry can be safe under transaction semantics.

However, if the writer has effects outside the transaction, re-invocation can create duplicate records or send the same notification multiple times.

Example using a business key to prevent duplicate writes:

~~~sql
INSERT INTO orders (order_id, order_number, amount)
VALUES (:orderId, :orderNumber, :amount)
ON CONFLICT (order_id)
DO UPDATE SET
    order_number = EXCLUDED.order_number,
    amount = EXCLUDED.amount
~~~

Upsert syntax depends on the database. The goal is that the same business request can be reapplied without unintentionally creating an extra record.

For APIs, use idempotency keys. For events, use event IDs. For files, use temporary files scoped by JobExecution and publish under deterministic rules.

## 18. Monitoring Writer Failures and Rollbacks

Spring Batch listeners help observe write errors:

- ItemWriteListener.onWriteError: invoked when the writer throws an exception.
- ChunkListener.afterChunkError: observes a chunk taking the error branch after rollback.
- SkipListener.onSkipInWrite: records items skipped during the write phase.
- StepExecutionListener.afterStep: summarizes Step status upon completion.

Example write-error logging:

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
                "Writing chunk failed, itemCount={}",
                items.size(),
                exception);
    }
}
~~~

afterWrite only indicates that the writer call returned normally; it is not proof that the transaction committed. Use transaction logs and StepExecution status to distinguish write failures from commit failures.

Useful counters:

| Counter | Meaning |
|---|---|
| writeCount | Number of items written according to Step statistics |
| writeSkipCount | Number of items skipped in the write phase |
| rollbackCount | Number of recorded rollbacks |
| commitCount | Number of commits |
| status | Final status of the Step |
| exitStatus | Exit code of the Step |

Counters do not replace exception logs. For investigation, include JobExecution ID, StepExecution ID, partition name if any, and business keys in logs.

## 19. Testing Rollback When the Writer Fails

A valuable integration test should use a real transactional database or an embedded database, run the Step, and verify data after the writer throws an exception.

Conceptual example:

~~~java
@Test
void rollsBackAllRowsWhenWriterFailsMidChunk() throws Exception {
    ItemWriter<Order> failingWriter = chunk -> {
        jdbcTemplate.update(
                "INSERT INTO orders(id, order_number) VALUES (?, ?)",
                1L, "A");

        jdbcTemplate.update(
                "INSERT INTO orders(id, order_number) VALUES (?, ?)",
                2L, "B");

        throw new OrderWriteException("Simulated write failure");
    };

    JobExecution execution = launchJobWith(failingWriter);

    assertEquals(BatchStatus.FAILED, execution.getStatus());
    assertEquals(0, countOrders());
}
~~~

The illustrative test assumes both JDBC statements use the same DataSource and transaction manager as the Step. After rollback, neither row remains in the table.

To properly verify transaction boundaries, ensure the test does not open an outer transaction that alters observed behavior. You can query the database after the Job completes using an independent connection.

### Scenarios to Test

- Writer fails before writing the first item.
- Writer writes partially and then throws an exception.
- Writer fails due to deadlock and succeeds on retry.
- Retries are exhausted and the Step fails.
- Failing item is skipped and valid items are still written.
- Skip limit is exceeded.
- Writer uses a non-transactional resource.
- Composite writer has a delegate fail mid-way.
- Commit fails or commit outcome is ambiguous.
- Job restarts after rollback and resumes from the correct checkpoint.

## 20. Common Mistakes

### Writer Catches Exceptions and Does Not Rethrow

The framework does not know the write failed and may proceed to commit. Propagate the exception or wrap it in one preserving the root cause.

### Assuming All Writer Operations Roll Back

Only resources participating in the corresponding transaction roll back. Files, emails, HTTP calls, and separate databases may retain side effects.

### Manually Committing Connections in the Writer

An independently committed transaction cannot be undone by the outer chunk transaction. Use Spring JDBC infrastructure to participate in the current transaction.

### Retrying Non-Idempotent Writers

The writer may be called again after rollback or when isolating a write skip. Side effects may repeat. Use business keys, idempotency keys, or an outbox.

### Skipping Broad Database Errors

Database downtime or out-of-disk errors are not single-item errors. Skipping can cause widespread data loss. Let the Step fail and resolve the infrastructure issue.

### Using noRollback to Prevent Step Failure

noRollback does not mean the item is skipped. If the writer wrote partially, the transaction may commit an unintended state.

### Confusing afterWrite with a Successful Commit

afterWrite occurs after the writer call returns but before the chunk transaction completes. Data can still roll back after this callback.

### Ignoring writer.close()

Errors in close/finalization can fail the Step after earlier chunks have committed. Already-committed transactions cannot be rolled back simply because close failed.

## 21. Workflow for Diagnosing Writer Failures

When a writer fails, trace through these questions:

1. Did the exception arise inside write() or during transaction commit?
2. How much data did the writer write before failing?
3. Do the write operations share the same transaction manager and resource as the Step?
4. Does the writer open its own connection or commit a separate transaction?
5. Is the exception propagated out of the writer?
6. Does the rollback classifier treat the exception as requiring rollback?
7. Is the exception in the retryable set?
8. If retries are exhausted, is the exception skippable?
9. On write skip, can the framework isolate the failing item?
10. Does the writer have non-transactional side effects that require idempotency?
11. How many rollbacks, commits, and write skips does StepExecution record?
12. On restart, do the reader and writer restore from the appropriate checkpoint?

When a writer uses transactional resources properly and exceptions propagate to Spring Batch, rollback undoes all chunk changes on those resources. For files, APIs, or independent systems, add transactional buffers, idempotency, outbox patterns, or reconciliation. Distinguishing write failures, commit failures, and non-transactional side effects is the foundation for designing recoverable Jobs without data loss or duplicate writes.
