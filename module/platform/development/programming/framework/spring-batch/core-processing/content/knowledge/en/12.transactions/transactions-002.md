# Where does a transaction begin and commit?

In Spring Batch, transactions are managed at the **Step** level. For a chunk-based Step, Spring Batch typically opens one transaction per chunk: the transaction begins before the chunk is processed, covers the reads, processing, and writes of that chunk, and commits when the chunk completes successfully. If the chunk hits an error that requires rollback, the changes belonging to the transaction are undone.

This means a Job does not run in a single transaction from start to finish. Each Step has its own transaction boundary; with a chunk-oriented Step, each chunk is a transaction unit. Chunks that have already committed are kept if a later chunk fails.

To determine exactly where a transaction begins and ends, you need to look at the Step type, the chunk size, the transaction manager, how the reader/writer use resources, and the propagation configuration of the services called during processing.

## 1. A Job has no transaction spanning the whole process

A Job can consist of multiple Steps. The JobLauncher creates an execution request, and Spring Batch stores metadata about JobExecution and StepExecution in the JobRepository. The Job then coordinates the Steps according to the declared flow.

~~~text
JobLauncher
    |
    v
JobRepository: creates JobExecution
    |
    v
Job starts
    |
    v
Step A
  transaction of Step A
    |
    v
Step A ends
    |
    v
Step B
  transaction of Step B
    |
    v
Step B ends
    |
    v
Job completes
~~~

Each Step can use its own transaction manager and transaction configuration. When Step A completes, Step A's transactions have ended before the flow moves to Step B. If Step B fails, the data committed by Step A is not automatically rolled back.

For example, an order import Job:

1. **validateFileStep**: validates the input file.
2. **importOrdersStep**: writes the orders in chunks.
3. **createSummaryStep**: creates a report.

If **createSummaryStep** fails, the committed chunks of **importOrdersStep** still exist. Spring Batch can restart the Job and continue based on the saved state and checkpoints; it does not reopen a single transaction to undo the entire Job.

Operations that manage JobExecution and StepExecution in the JobRepository also have their own transactions according to the repository configuration. Do not confuse the transaction that creates the JobExecution with the transaction that processes the data of a chunk.

## 2. Chunk-oriented Step: one transaction per chunk

With chunk processing, **chunk(size, transactionManager)** specifies the chunk size and the transaction manager used to manage the Step's transactions.

For example:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

With a chunk size of 100, Spring Batch gathers at most 100 items into one processing unit before committing. Suppose the source has 250 items:

| Chunk | Items | Transaction |
|---|---:|---|
| Chunk 1 | 1–100 | Transaction 1 |
| Chunk 2 | 101–200 | Transaction 2 |
| Chunk 3 | 201–250 | Transaction 3 |

The last chunk may be smaller than the configured size. If chunk 3 fails, the transaction of chunk 3 may roll back; the two earlier transactions, which have already committed, are kept.

### Sequence of a chunk

Conceptually, a chunk is executed as follows:

~~~text
Begin transaction
        |
        v
ItemReader reads items
        |
        v
ItemProcessor processes items
        |
        v
ItemWriter writes the items
        |
        v
Update ItemStream state
and Step metadata
        |
        v
COMMIT transaction
        |
        v
Begin next chunk
~~~

Spring Batch coordinates the chunk loop and the transaction. The chunk's transaction is opened before the chunk's read/process/write operations take place. After the writer completes and the framework updates the necessary state, the transaction is committed.

If an error requires rollback:

~~~text
Begin transaction
        |
        v
Reader -> Processor -> Writer
                         |
                         v
                    Exception
                         |
                         v
                      ROLLBACK
                         |
                         v
          Retry / Skip / Step fails
~~~

How the reader is called again after a rollback depends on the reader type and the fault-tolerant policy. For example, the framework may buffer items already read in some situations; a reader based on a transactional source may have its own rollback behavior.

## 3. Where does the transaction begin in a chunk Step?

Spring Batch implements a chunk-oriented Step through **TaskletStep**. TaskletStep uses the transaction manager to run each tasklet invocation inside a transaction. With a chunk-oriented Step, the chunk processing is implemented inside that tasklet.

You can picture it like this:

1. The Step starts.
2. Spring Batch opens a transaction for the chunk execution.
3. The chunk-oriented tasklet reads items and calls the processor and writer.
4. The framework updates the ExecutionContext and StepExecution.
5. If there is no error requiring rollback, the transaction manager commits.
6. The Step continues the loop with the next chunk.

So, when asking “where does the transaction begin?”, the practical answer is: **at the chunk execution boundary managed by TaskletStep**, using the transaction manager passed into the chunk configuration.

You do not need to call begin() or commit() yourself in an ItemReader, ItemProcessor, or ItemWriter. If these components use Spring JDBC or services with an appropriate transaction propagation, they will join the current transaction.

## 4. Where does the transaction end and commit?

The transaction ends when the chunk processing callback completes successfully and there is no error forcing a rollback. At that point the transaction manager performs the commit.

Some things happen before the commit:

- The reader finishes supplying the chunk's items.
- The processor processes the items.
- The writer finishes writing the results.
- The ItemStreams update their state in the ExecutionContext.
- The StepExecution updates the counters and state that need to be saved.
- The JobRepository stores execution metadata according to the transaction configuration.

If all operations participate in the same transaction manager and the same transactional resource, the business data and metadata can be committed consistently. If they reside in independent databases, transaction managers, or resources, you cannot assume that a single commit confirms all of them.

After the commit, that chunk is considered complete. The Step begins a new transaction for the next chunk.

### A writer completing does not mean the transaction has committed

A successful return from ItemWriter.write() only indicates that the writer has finished its write call. The transaction can still fail in later steps, for example when updating metadata or during the commit itself.

Therefore:

- A writer completing does not mean the chunk has committed.
- Flushing a buffer does not mean the transaction has committed.
- Only after the transaction commits successfully are the changes belonging to the transaction confirmed.

This is an important point when the writer writes files, calls APIs, or works with resources that do not participate in the database transaction.

## 5. What are the transaction boundaries of a Tasklet Step?

A Tasklet Step also has its transactions managed by Spring Batch. With an ordinary Tasklet, each call to **Tasklet.execute()** is performed within one transaction of the Step.

For example:

~~~java
@Bean
public Step cleanupStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    return new StepBuilder("cleanupStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                // Delete temporary data in the database.
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
~~~

When the Tasklet returns **RepeatStatus.FINISHED**, the Step completes after that call. If the Tasklet returns **RepeatStatus.CONTINUABLE**, Spring Batch may call the Tasklet again; each execution is managed in a transaction according to the Step's configuration.

For example, a Tasklet that does its work in multiple passes:

~~~java
@Bean
public Step rebuildIndexStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        IndexService indexService) {

    return new StepBuilder("rebuildIndexStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                ExecutionContext context = chunkContext
                        .getStepContext()
                        .getStepExecution()
                        .getExecutionContext();

                long lastId = context.getLong("lastId", 0L);
                long nextId = indexService.rebuildNextBatch(lastId, 500);

                if (nextId == lastId) {
                    return RepeatStatus.FINISHED;
                }

                context.putLong("lastId", nextId);
                return RepeatStatus.CONTINUABLE;
            }, transactionManager)
            .build();
}
~~~

In this example, the Tasklet processes one batch of data per call. Progress is saved in the Step ExecutionContext. If one call fails, the transaction of that call may roll back. Earlier calls that have already committed are kept.

If a Tasklet performs only one long operation, not split into multiple passes, the transaction typically lasts for the entire execute() call. Consider timeouts, locks, and the amount of data when designing.

## 6. The transaction manager determines which resources are managed

The transaction manager is the component that coordinates the Step's transactions. For JDBC applications, **DataSourceTransactionManager** or **JdbcTransactionManager** bound to the appropriate DataSource is typically used. For JPA, use the transaction manager corresponding to the EntityManagerFactory.

An example Step configuration using a JDBC transaction manager:

~~~java
@Bean
public Step updateOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("updateOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(50, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Components that use the same transaction manager and the corresponding resource can participate in the open transaction.

For example:

- A JdbcTemplate using the same DataSource can participate in the current JDBC transaction.
- A JPA repository using the same JPA transaction manager can participate in the corresponding JPA transaction.
- An ordinary HTTP client does not participate in the JDBC transaction.
- Writing a file with a BufferedWriter is not automatically managed by the database transaction.
- A different database with its own transaction manager does not automatically commit/roll back together with the main database.

The transaction manager does not automatically turn every Java call into a transactional operation. Identify the actual resources each component uses.

## 7. JobRepository and the chunk transaction

The JobRepository stores metadata about JobInstance, JobExecution, StepExecution, and ExecutionContext. As a chunk completes, Spring Batch updates the execution metadata and stream state.

When the JobRepository and the writer use the same database and the same transaction manager, the appropriate metadata updates can participate in the chunk's transaction. This helps the business state and the checkpoint be confirmed consistently.

If the JobRepository uses a different database or transaction manager, you need to consider how the transactions are configured. Two independent transactions do not automatically become one distributed transaction.

An example of a risky scenario:

~~~text
Transaction A: business database
  |
  +--> Writer writes orders
  |
  +--> COMMIT succeeds

Transaction B: JobRepository
  |
  +--> Save checkpoint
  |
  +--> COMMIT fails
~~~

When the business data has been committed but the checkpoint has not been saved, a restart may reprocess part of the data. The writer needs a strategy to prevent duplicate writes, such as a unique business key, upsert, or idempotency.

If the metadata commits but the business data in another resource does not, that situation also needs to be handled according to the chosen transaction architecture. With multiple resources, consider XA/JTA when a distributed transaction is truly needed, or use an outbox, idempotency, and reconciliation when more appropriate.

## 8. @Transactional inside Reader, Processor, and Writer

Services called from the reader, processor, or writer can use **@Transactional**. However, you need to understand propagation to know whether they join the chunk transaction or create their own.

### REQUIRED

**Propagation.REQUIRED** is the default. If a transaction already exists, the method joins the current transaction; if not, Spring creates a new one.

~~~java
@Service
public class OrderService {

    @Transactional
    public void updateOrder(Order order) {
        // Joins the current chunk transaction
        // if using the same transaction manager.
    }
}
~~~

If the service is called from the processor or writer on the same execution thread and uses the same transaction manager, the operation typically joins the chunk transaction. When the chunk rolls back, the service's changes are also rolled back.

### REQUIRES_NEW

**Propagation.REQUIRES_NEW** suspends the current transaction and creates an independent one:

~~~java
@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(String message) {
        // Transaction independent of the chunk transaction.
    }
}
~~~

If the new transaction commits successfully, the audit record may still exist even when the outer chunk rolls back. This can be the desired behavior when you need to keep a trace of processing attempts, but it is not appropriate if the audit must reflect only committed data.

### NOT_SUPPORTED

**Propagation.NOT_SUPPORTED** suspends the current transaction while the method executes. Operations inside are not protected by the chunk transaction. If the method writes data, that change may persist even if the chunk rolls back.

Choose the propagation according to the business meaning. Do not use REQUIRES_NEW merely to avoid a transaction error without first determining the impact when the chunk fails.

Note: **@Transactional** is applied through Spring's proxy mechanism in ordinary cases. Calling another transactional method in the same object through self-invocation may not go through the proxy, and therefore does not trigger the interceptor as expected.

## 9. Isolation, propagation, and timeout of a Step

Besides the transaction manager, a Step can be configured with a transaction attribute to control isolation, propagation, and timeout.

For example:

~~~java
DefaultTransactionAttribute transactionAttribute =
        new DefaultTransactionAttribute();

transactionAttribute.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);

transactionAttribute.setTimeout(60);

Step step = new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .transactionAttribute(transactionAttribute)
        .build();
~~~

Some common attributes:

| Attribute | Effect |
|---|---|
| Isolation level | Specifies the isolation level when reading/writing transactional data |
| Propagation | Specifies whether to start a new transaction or join the current one |
| Timeout | Limits transaction time, as supported by the transaction manager |
| Read-only | A hint for a read-only transaction where appropriate for the resource |

Do not choose the highest isolation level for every Step. High isolation can increase lock contention and reduce the ability to run in parallel. Choose based on data consistency requirements and query characteristics.

The timeout also needs to fit the processing time of a chunk. If the chunk is too large or the writer is slow, the transaction may exceed the timeout. Measure the actual processing time before adjusting.

## 10. Which exceptions cause the transaction to roll back?

When an exception occurs while processing a chunk, Spring Batch applies the Step's rollback policy and the fault-tolerant configuration.

Cases that commonly cause a chunk to roll back:

- The reader throws an unhandled exception.
- The processor throws an exception that is not skipped/retried according to the configuration.
- The writer throws an exception.
- Updating the stream state or metadata fails.
- Committing the transaction fails.

With a Step that has retry, the framework can roll back the transaction of the attempt and then re-execute according to the retry policy. With skip, the framework can skip an item of an allowed error type and continue until the chunk can complete.

Not every exception must lead to a rollback in every configuration. A fault-tolerant Step can be configured with exception types that do not cause rollback using **noRollback(...)**. Use that policy carefully, because if the writer has already written part of the data and the transaction does not roll back, the result may be inconsistent.

An example retry and skip configuration:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
~~~

In the example, transient data access errors can be retried up to the limit; invalid order data can be skipped within the allowed limit. If the limit is exceeded or an unhandled error occurs, the Step fails.

## 11. Is the reader inside the transaction?

A call to **ItemReader.read()** takes place within the scope of chunk processing, but that does not mean every read source can roll back like a database.

For example:

- A reader using JDBC and the same transaction manager can read within the database transaction.
- A reader reading a file may advance the stream's read position; the file position does not automatically roll back with the database transaction.
- A reader taking messages from a transactional broker can coordinate acknowledge/rollback according to configuration.
- A reader calling a REST API cannot ask the remote server to roll back just because the database chunk failed.

For a stateful reader, Spring Batch uses **ItemStream** and **ExecutionContext** to store checkpoints. If the chunk rolls back, the read state may be restored or the items already read may be buffered, depending on the reader type and the framework mechanism.

Do not assume every read() call is physically undone. Check the specific reader and how it manages state.

## 12. Writer and transaction: finished writing does not necessarily mean committed

If the writer uses the same transaction manager and database as the Step, its write statements typically participate in the chunk transaction. When the transaction rolls back, those changes are undone by the database.

But if the writer:

- Writes a file using an ordinary stream.
- Sends an HTTP request.
- Sends an email.
- Writes to another database.
- Calls a service that uses REQUIRES_NEW.
- Pushes a message to a broker that does not participate in the transaction.

then those effects may not roll back together with the chunk transaction.

For example, a writer sends a request to an API to create an invoice and then the database rolls back. The API that created the invoice may still keep the result. When the chunk is retried, the API may receive the request again.

Commonly used approaches:

- Use an idempotency key for the API.
- Write the request for the external effect to an outbox in the same database transaction.
- Have a separate worker read the outbox and send the request.
- Use a unique key or upsert in the target system.
- Have a reconciliation mechanism when a multi-resource transaction cannot be atomic.

## 13. Where do listeners run relative to the transaction?

Spring Batch has listeners at the Step, chunk, read, process, and write levels. Listeners help with logging, collecting metrics, or updating operational state.

However, you should not infer transaction boundaries from callback names alone. Some callbacks are invoked inside the transaction, and some are invoked after the chunk has completed. The specific timing depends on the listener type and the lifecycle of the Step.

If you need to perform an action only after the transaction commits, use an appropriate Spring transaction after-commit mechanism or a durable outbox. Do not send important notifications from a callback without first determining whether that callback may be invoked before a rollback.

An example of a transaction synchronization:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                // Runs only after the current transaction commits.
            }
        });
~~~

This mechanism only works when there is a current Spring transaction and the callback is registered correctly within that transaction. For requirements to send events reliably across restarts or process crashes, an outbox is usually safer than an in-memory callback.

## 14. When is a transaction rolled back but the side effect remains?

Consider the example of a Step that reads orders, calls a shipping API, and writes the status to the database:

~~~text
Chunk transaction begins
        |
        v
Read order
        |
        v
Call API to create shipment
        |
        v
API returns success
        |
        v
Write order status to database
        |
        v
Database error
        |
        v
ROLLBACK chunk transaction
~~~

After the rollback:

- The order status in the database may not have been updated.
- The shipment in the external system may have been created.
- On retry or restart, the same order may be processed again.

This is why you cannot rely on the database transaction to guarantee exactly-once for the whole system. Design operations outside the transaction to be idempotent or use an appropriate coordination mechanism.

## 15. Verifying transaction boundaries with logs and metrics

To determine where a transaction actually begins and commits, you can enable logging for the transaction manager and monitor the StepExecution counters.

Commonly useful figures:

| Counter | Meaning |
|---|---|
| readCount | Number of items read |
| writeCount | Number of items written |
| filterCount | Number of items filtered by the processor |
| commitCount | Number of chunk transactions committed |
| rollbackCount | Number of transactions rolled back |
| readSkipCount | Number of items skipped during read |
| processSkipCount | Number of items skipped during processing |
| writeSkipCount | Number of items skipped during write |

For example, with a chunk size of 100 and 1,000 items, if there is no skip/filter and each chunk commits once, commitCount is typically close to 10. However, retries, skips, errors, and how the reader terminates can affect the counters. Do not use a simple calculation to conclude exactly how many transactions ran in every case.

Transaction logs can help determine:

- Which transaction manager opened the transaction.
- Which connection is bound to the transaction.
- Whether a service joined the current transaction or opened a new one.
- When the commit or rollback occurred.
- Whether there was an exception during commit or cleanup.

## 16. Common misconceptions

### Thinking a Job runs in one transaction

A Job can consist of multiple Steps, and each Step has its own transaction boundary. A chunk Step has a transaction for each chunk.

### Thinking the transaction only begins when the writer writes

The chunk transaction is opened before the chunk performs its read/process/write operations. The reader and processor can participate in the transaction if they use appropriate transactional resources.

### Thinking a successful writer.write() means the chunk has committed

After write(), the framework still updates the stream state and metadata, and only then does the transaction manager commit. An error in the later phase can still cause a rollback.

### Thinking flush is commit

Flush pushes data out of the writer's buffer. Commit confirms the transaction. The two operations have different meanings.

### Thinking @Transactional(REQUIRES_NEW) rolls back together with the chunk

REQUIRES_NEW creates an independent transaction. If that transaction commits, the data may persist even if the outer chunk transaction rolls back.

### Thinking HTTP requests and file writes roll back automatically

These effects do not automatically participate in the database transaction. You need idempotency, an outbox, or a separate coordination mechanism.

### Thinking metadata and business data are always atomic

You can only expect consistent commit/rollback when they truly participate in the same transaction and an appropriate resource. Two independent databases are not automatically atomic.

## 17. Procedure for determining the transaction boundary in a Step

When reading or designing a Step, trace through the following points:

1. Determine whether the Step is a Tasklet or chunk-oriented.
2. For a chunk Step, read the value of **chunk(size, transactionManager)**.
3. Determine which transaction manager is being passed in.
4. Check which resources the Reader, Processor, and Writer use.
5. Check whether the services called have **@Transactional** and what propagation.
6. Determine whether the JobRepository shares the same database and transaction manager as the business data.
7. Check whether retry, skip, and noRollback change the rollback behavior.
8. Identify side effects outside the transaction such as files, HTTP, email, and messages.
9. Check at which boundary the ExecutionContext/checkpoint is updated.
10. Monitor commitCount, rollbackCount, and the transaction logs during a trial run.

If you understand these points clearly, you can answer precisely before which operation a transaction begins, which resources participate, when the commit occurs, and which data remains after a rollback.

With a chunk-oriented Step, remember that **each chunk is a transaction unit managed by TaskletStep**. With a Tasklet Step, the transaction surrounds each Tasklet invocation. The entire Job is not protected by a single transaction; consistency across Steps, databases, and external systems must be designed according to the actual resource boundaries.
