# Chunk step transaction boundaries in Spring Batch

In Spring Batch, a chunk-oriented step processes data in groups of items. A group is read, processed, and written within one transaction; when the transaction commits, the changes of that chunk become confirmed results. If a chunk fails and the transaction rolls back, the transactional changes of the current chunk are undone, while chunks committed earlier are kept.

Understanding the **transaction boundary** correctly helps you determine which data is committed together, why part of a job may have completed before an error occurs, and what is needed to retry or restart safely. The chunk transaction boundary also explains why a database rollback cannot by itself undo emails, HTTP requests, or messages already sent to external systems.

## 1. What is a transaction boundary?

A transaction boundary is the span during which a group of operations is managed as a single unit of commit or rollback. For a chunk-oriented step, Spring Batch typically opens one transaction per chunk.

For example, a step with a commit interval of 100:

```java
@Bean
Step importOrdersStep(JobRepository jobRepository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<Order> reader,
                      ItemProcessor<Order, OrderEntity> processor,
                      ItemWriter<OrderEntity> writer) {
    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

The value `100` specifies the maximum number of input items gathered for a chunk before committing. It does not mean the whole job runs in one transaction, nor does it mean each item has its own transaction.

If the source has 250 items, a typical split is:

```text
Chunk 1: items 1..100    -> transaction 1 -> COMMIT
Chunk 2: items 101..200  -> transaction 2 -> COMMIT
Chunk 3: items 201..250  -> transaction 3 -> COMMIT
```

Each chunk has its own transaction boundary. If chunk 3 fails, chunks 1 and 2, which have already committed, still exist. Spring Batch does not automatically roll the whole job back to the state before chunk 1.

## 2. Lifecycle of a chunk transaction

Conceptually, processing a chunk goes as follows:

1. Spring Batch begins a transaction using the `PlatformTransactionManager` configured for the step.
2. The reader supplies items until the commit interval is reached or the reader reports that input is exhausted.
3. The processor handles each item if the step has a processor.
4. The writer writes the chunk's output items.
5. Spring Batch updates the state and execution context required for the step.
6. The transaction commits; the chunk is confirmed as complete.
7. The step begins the next transaction to process the next chunk.

```text
Step starts
    |
    v
BEGIN TRANSACTION
    |
    v
READ -> PROCESS -> WRITE
    |
    v
Update checkpoint / step state
    |
    v
COMMIT
    |
    +---- more input? ---- Yes ----> BEGIN next transaction
    |
    +---- No ----------------------> Step completes
```

If an operation in the chunk throws an exception that requires rollback, the current transaction is rolled back according to the transaction attribute and the fault-tolerance policy. If the exception is retried or skipped, Spring Batch coordinates again according to the configuration; if it cannot recover, the step/job ends in failure.

Internal details may differ by reader, writer, transaction manager, and retry/skip policy, but the key principle remains that the transactional operations of a chunk are grouped within the same commit boundary.

## 3. Which operations are inside the chunk transaction?

In a typical chunk step, reading, processing, and writing are performed within the chunk processing loop managed by the transaction. That does not mean every resource the components touch automatically participates in the transaction.

| Component/operation | Inside the chunk transaction? | Conditions or notes |
| --- | --- | --- |
| Reader reading from a database | Possibly | Requires an appropriate resource and transaction manager; cursor/paging readers have their own rules. |
| Processor computing in memory | Runs within the chunk processing loop | Changes to in-memory objects do not automatically become durable data. |
| Writer writing in the same database transaction | Yes | Must participate in the same transaction manager and the same transactional resource. |
| Step metadata updates | Managed by Spring Batch | Atomicity with business data depends on the repository configuration and transactional resource. |
| Calling an HTTP API | Normally no | An external HTTP service does not automatically participate in the database transaction. |
| Sending email or SMS | No | Cannot be recalled by a database rollback. |
| Publishing a message to a broker | Only with an appropriate enlistment mechanism | An ordinary publish call is not automatically in the same transaction as the database. |
| Writing to a file or object storage | Normally no | Requires a staging, commit/rename, or separate compensation mechanism. |

For example, if the writer uses `JdbcTemplate` with the same `DataSource` and transaction manager as the step, its write statements can participate in the chunk transaction. If the writer calls a REST API, the database transaction cannot force that API to undo its work when the chunk rolls back.

## 4. The role of PlatformTransactionManager

`PlatformTransactionManager` is the abstraction Spring uses to begin, commit, and roll back transactions. When creating a chunk step, the application passes the transaction manager to the builder:

```java
new StepBuilder("processStep", jobRepository)
    .<Input, Output>chunk(50, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .build();
```

The transaction manager must match the resource that needs to be protected. For example:

- `DataSourceTransactionManager` (or `JdbcTransactionManager` in modern Spring Framework) manages JDBC transactions for a single datasource.
- `JpaTransactionManager` manages JPA transactions for the corresponding `EntityManagerFactory`.
- `JtaTransactionManager` can coordinate distributed transactions when the resources support XA and are configured correctly.

If the application has multiple datasources, injecting the wrong transaction manager can cause the writer to write to a database that is not managed by the step's transaction. In that case, a chunk rollback cannot undo the writes to the other datasource.

In an application with multiple transaction managers, use `@Qualifier` to explicitly specify the manager for the chunk step, and make sure the repositories/writers that need to participate in the transaction are configured accordingly.

## 5. How does rollback affect a chunk?

Suppose the commit interval is 3. The first chunk writes three items and commits successfully. The second chunk writes two items, but the third item causes an error in the writer:

```text
Chunk 1: [A, B, C]
  BEGIN -> WRITE A,B,C -> COMMIT

Chunk 2: [D, E, F]
  BEGIN -> WRITE D,E -> error while writing F -> ROLLBACK

Transactional database result:
  A, B, C: remain (chunk 1 committed)
  D, E, F: no changes from chunk 2 are committed
```

The condition for this example to hold is that the writes of A, B, C, D, E, and F all participate in the same transaction manager and the same transactional resource. If the writer writes to a system outside the transaction, that write may still exist after the rollback.

Rollback does not necessarily return every in-memory component to its initial state. A modified Java object, a counter in a singleton, or the cursor of an external non-database source may still be changed. The transaction manager only undoes operations belonging to the resources it manages.

## 6. Retry and skip within the transaction boundary

A fault-tolerant chunk step can be configured to retry transient errors or skip faulty items:

```java
@Bean
Step resilientImportStep(JobRepository jobRepository,
                         PlatformTransactionManager transactionManager,
                         ItemReader<Order> reader,
                         ItemProcessor<Order, OrderEntity> processor,
                         ItemWriter<OrderEntity> writer) {
    return new StepBuilder("resilientImportStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(FlatFileParseException.class)
        .skipLimit(10)
        .build();
}
```

When an error that needs a retry occurs, the chunk may roll back and then be retried according to the policy. For an error that is allowed to be skipped, the framework handles the exception according to the skip policy and continues if the reader/processor/writer can recover safely.

Key points to remember:

- A retry may cause part of the logic in the chunk to be executed again.
- Skip does not mean the transaction does not roll back; in some situations a rollback is still needed so the framework can isolate the faulty item.
- `skipLimit` is the total skip limit of the step under the policy, not an independent limit for each of the read, process, and write phases.
- Chunks committed earlier are kept when a later chunk rolls back.
- Do not place side effects outside the transaction in the processor or writer and then assume a rollback will erase their effects.

Do not configure skip too broadly just so the job always runs to the end. Connection errors, authentication errors, or errors that make it impossible to determine the read position usually require stopping the job rather than skipping.

## 7. Transaction boundaries and restart

Spring Batch uses `JobRepository` together with `ExecutionContext` to store metadata and checkpoints. For a reader that supports restart, the read state is typically updated at the chunk boundary so that a restart can continue from the last committed checkpoint.

For example, a job reading a file with a commit interval of 100:

```text
Chunk 1: lines 1..100    -> write + checkpoint -> COMMIT
Chunk 2: lines 101..200  -> write + checkpoint -> COMMIT
Chunk 3: lines 201..300  -> error before commit

Restart:
  Restore the checkpoint of chunk 2
  Continue reading from the appropriate position after line 200
```

If chunk 3 has not committed, the durable state is typically still the checkpoint of chunk 2. The reader may re-read the items belonging to chunk 3. The writer must be safe to re-execute if there is a risk that effects have already occurred outside the transaction.

`ItemStream` provides callbacks related to reader/writer state:

- `open(ExecutionContext)` restores or initializes state.
- `update(ExecutionContext)` writes the checkpoint to the execution context.
- `close()` releases resources.

A custom reader needs to store enough state to continue from a checkpoint. If the reader consumes messages from a queue or calls an API with a cursor, a database rollback does not by itself return the external source to its earlier position. You need to design ack, offset, token, or idempotency appropriate to that source.

## 8. A job is not in a single transaction

A job can run multiple steps, and each step has multiple chunks. Spring Batch does not open a single long-running transaction from the beginning to the end of the whole job by default. For a chunk step, each chunk has its own transaction; steps also have their own lifecycle and transactions.

For example:

```text
Job: dailyImport
  |
  +-- ValidateStep
  |     transaction per step configuration
  |
  +-- ImportStep
  |     Chunk 1 -> transaction -> commit
  |     Chunk 2 -> transaction -> commit
  |     Chunk 3 -> transaction -> commit
  |
  +-- ReportStep
        transaction per step configuration
```

If `ReportStep` fails, the chunks of `ImportStep` that have already committed still exist. Re-running the whole business flow from scratch requires a separate reprocessing design, appropriate identifying parameters, and a mechanism for handling data already written. You cannot use a whole-job rollback to undo chunks committed earlier.

## 9. Tuning the commit interval and its effect on transactions

The commit interval determines the chunk size and the commit frequency. Choosing an appropriate value is a decision about performance, resources, and recoverability.

| Commit interval | Advantages | Trade-offs |
| --- | --- | --- |
| Small | Short transactions, fewer items rolled back, frequent checkpoints. | More commits and higher transaction/metadata overhead. |
| Large | Fewer commits, may increase throughput with a batch-efficient writer. | Longer transactions, resources held longer, and a rollback can affect more items. |

For example:

- An interval of 1 suits cases where each item needs its own transaction or a very small commit boundary is wanted, but the commit cost can be high.
- An interval of 100 is usually suitable for many data import tasks, but should be measured against actual record size and the database.
- An interval of 5,000 can be efficient with a bulk writer, but a long transaction can hold locks, connections, and memory for longer.

There is no single optimal commit interval for every job. Measure throughput, transaction time, lock wait, connection usage, rollback rate, and restartability before choosing.

## 10. Configuring the transaction attribute for a chunk step

Besides the transaction manager, a step can accept a `TransactionAttribute` to adjust the isolation level, timeout, and propagation behavior as needed.

For example, setting the isolation level and timeout:

```java
@Bean
Step controlledImportStep(JobRepository jobRepository,
                          PlatformTransactionManager transactionManager,
                          ItemReader<Order> reader,
                          ItemWriter<Order> writer) {
    DefaultTransactionAttribute transactionAttribute =
        new DefaultTransactionAttribute();
    transactionAttribute.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
    transactionAttribute.setTimeout(120);

    return new StepBuilder("controlledImportStep", jobRepository)
        .<Order, Order>chunk(200, transactionManager)
        .reader(reader)
        .writer(writer)
        .transactionAttribute(transactionAttribute)
        .build();
}
```

`READ_COMMITTED` and a 120-second timeout are only examples. Isolation levels are supported and enforced by the database in its own way; choosing a higher level may increase locking or reduce concurrency. The timeout must fit the normal processing time of a chunk and the timeouts at the database/driver.

The default propagation is usually `REQUIRED`, meaning transactional operations inside join the current transaction if they use the same transaction manager. Be careful when a service called from the processor or writer uses `REQUIRES_NEW`: the new transaction can commit independently and still exist even if the outer chunk transaction rolls back.

If you need rollback for a checked exception or a specific exception type, configure a rollback rule appropriate to the `TransactionAttribute` and the fault-tolerance policy. Do not assume every exception type has the same rollback behavior without checking the transaction configuration.

## 11. Transaction boundaries of a service called from a processor or writer

A service can be annotated with `@Transactional`. Whether the service participates in the chunk transaction depends on the propagation, the transaction manager, and how it is invoked through the Spring proxy.

An example service using `REQUIRED`:

```java
@Service
public class OrderPersistenceService {

    private final OrderRepository repository;

    public OrderPersistenceService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void save(OrderEntity order) {
        repository.save(order);
    }
}
```

If the service is called from a writer running inside the chunk transaction and uses the same transaction manager, `REQUIRED` typically joins the current transaction. When the chunk rolls back, the save operation also rolls back.

In contrast:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAudit(AuditEvent event) {
    auditRepository.save(event);
}
```

`REQUIRES_NEW` suspends the current transaction and opens a separate one. If the audit transaction commits and then the outer chunk rolls back, the audit record still exists. This can be the desired behavior for incident auditing, but it can cause discrepancies if the audit record is interpreted as confirmation that the business operation completed.

Besides propagation, watch out for self-invocation: calling a `@Transactional` method from another method in the same object typically does not go through the Spring proxy, so the annotation may not be applied as expected. Place the transaction boundary on an appropriate service bean and verify the actual configuration.

## 12. Resources outside the transaction and the transactional outbox

A database rollback only undoes resources managed by the transaction manager. For example, if the processor sends an email and then the writer's database write fails, the email already sent cannot be recalled by a rollback.

For messages or APIs that must be emitted after the data has been committed, you can use a transactional outbox:

```text
Chunk transaction
  |
  +-- Write business data
  |
  +-- Write outbox event
  |
  +-- COMMIT both in the same database
           |
           v
Outbox dispatcher
  |
  +-- Read PENDING events
  +-- Send message / call API
  +-- Mark as sent
```

The outbox ensures that the business data and the intent to send the event are stored in the same transaction if they use the same database and transaction manager. The dispatcher may resend on timeout or if it stops between publishing and updating the status; therefore the target consumer/API still needs a stable idempotency key.

If several resources must commit atomically, you can consider JTA/XA when all resources support it and it is operable. However, XA increases complexity and does not apply to every API or service. An outbox is often the more practical choice for message/API integration.

## 13. Listeners and timing within the transaction

A chunk step provides listeners to observe the processing lifecycle. Understand when each callback runs before putting logic in it:

| Callback | General timing | Suitable use |
| --- | --- | --- |
| `beforeChunk` | After the chunk transaction begins, before the chunk is processed. | Record a trace/metric for the start of the chunk. |
| `afterChunk` | After the chunk has committed successfully. | Record metrics or observability information after commit. |
| `afterChunkError` | When chunk processing encounters an error/rollback. | Logging, error metrics, or diagnostics. |
| `ItemWriteListener.afterWrite` | After the writer call but before the chunk transaction is certain to commit. | Observe the writer result; do not assume the commit has succeeded. |

Do not send emails or publish messages directly from a listener expecting the callback to provide exactly-once. Even with `afterChunk`, the process can still stop after the database commit but before the external effect completes. If the effect must be performed reliably, write an outbox event within the transaction and dispatch it separately.

## 14. Testing transaction boundaries

A useful way to verify transaction boundaries is to use a test database and a writer that performs several writes in the same chunk, then deliberately throws an exception in the middle. Expected result: operations belonging to the failed chunk are rolled back, while the earlier committed chunk still has its data.

An example writer simulating a failure after writing:

```java
public class FailingDatabaseWriter implements ItemWriter<OrderEntity> {

    private final JdbcTemplate jdbcTemplate;
    private int calls;

    public FailingDatabaseWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends OrderEntity> chunk) {
        calls++;
        for (OrderEntity order : chunk) {
            jdbcTemplate.update(
                "insert into imported_order(order_id, amount) values (?, ?)",
                order.getId(),
                order.getAmount()
            );
        }

        if (calls == 2) {
            throw new IllegalStateException("Simulated failure after write");
        }
    }
}
```

With a commit interval of 2 and four items, the first chunk writes two rows and commits. The second chunk writes two rows and then throws an exception; if `JdbcTemplate` uses the same datasource and transaction manager as the step, the two rows of the second chunk will roll back. After the job fails, the test can confirm that the database contains only the two rows of the first chunk.

For the test to reflect real transactions:

- Use a test database and an appropriate schema.
- Ensure `JdbcTemplate` and the step use the same `DataSource`/transaction manager.
- Do not wrap the test method in an outer transaction that causes the step's committed data to be rolled back when the test ends.
- Verify the `JobExecution`/`StepExecution` status and the actual number of rows in the database.
- Use separate identifying parameters so the test does not conflict with a previous execution.

A unit test that only mocks the repository does not prove a database rollback. You need an integration test with resources that actually participate in the transaction.

## 15. Common mistakes when designing transaction boundaries

**Assuming the whole job is one transaction:** a chunk step commits each group separately. An error in a later chunk does not undo earlier chunks.

**Using the wrong transaction manager:** the writer may write to a datasource not managed by the step's transaction. Verify the correct datasource, manager, and repository.

**Calling an API in the processor and expecting a rollback:** an HTTP call does not automatically participate in the database transaction. Split it out into an outbox or use idempotency.

**Using `REQUIRES_NEW` without understanding the consequences:** the inner transaction can commit independently and survive the chunk's rollback.

**Choosing a commit interval that is too large:** a long transaction can hold locks, connections, and memory for a long time, and also enlarges the rollback scope.

**Choosing a commit interval that is too small:** the number of commits and metadata updates increases, reducing throughput in some workloads.

**Ignoring checkpoints:** a database rollback does not automatically restore the cursor, file pointer, or offset of an external source. The reader needs to support restart.

**Sending messages in a listener:** the callback does not create an atomic transaction between the broker and the database. Use an outbox or a corresponding coordination mechanism.

**Not verifying the actual rollback:** a mock cannot prove the database undid the changes. Use an integration test with the same transaction manager.

## 16. How to choose transaction boundaries in production

When designing a chunk step, first determine which resources must commit together. Choose the transaction manager corresponding to the primary database or resource; make sure the writers and repositories that need to participate in the transaction are configured consistently. If business data and metadata are in different resources, assess clearly the possibility of independent commits and the recovery plan.

Choose the commit interval based on throughput, lock duration, connection usage, data size, and restart cost. Configure the isolation level, timeout, and rollback rules according to real requirements. For a non-transactional reader, store the checkpoint through `ExecutionContext` and make sure the source can continue from the committed position.

Finally, test the scenarios where the writer fails mid-chunk, retry, restart, and side effects that have already occurred in external systems. For emails, messages, or APIs that must be emitted after commit, use an outbox and idempotency to handle duplicate delivery safely.

The transaction boundary of a chunk step defines a group of items that are committed or rolled back together. When you clearly understand the scope of the transaction manager, how a chunk rolls back, checkpoints, and the resources outside the transaction, a Spring Batch application can keep data more consistent and recover correctly from errors that occur mid-processing.
