# Write Transactions and Commits in Spring Batch

In Spring Batch, **ItemWriter** writes items that have been read and processed to the data destination. In a chunk-oriented Step, the writer usually runs inside the chunk's transaction. When the writer and the resources it writes to all participate in that transaction, Spring Batch can commit all changes when the chunk succeeds or roll back when the chunk fails.

Understanding transaction boundaries correctly helps avoid errors such as partially written data, committing too early, duplicate writes on retry, or believing that a database rollback can undo an HTTP request. This lesson explains how Spring Batch manages transactions for the writer, when commits happen, what happens on errors, how to configure transactions, and how to design write operations that are safe when a Job restarts.

## 1. Transactions in a Chunk-Oriented Step

A chunk-oriented Step divides data into groups. The framework reads items, passes them through the processor if there is one, and then passes the group of results to the writer. Each chunk is a processing unit tied to a transaction.

Configuration example:

~~~java
@Bean
Step writeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("writeOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
~~~

The parameter 100 is the commit interval. Spring Batch gathers up to 100 input items for a chunk before performing the write and completing that chunk's transaction. The last chunk may have fewer items when the reader runs out of data. If the processor filters an item by returning null, the number of items the writer receives will be smaller than the number of items read.

~~~mermaid
flowchart TD
    A["Begin chunk transaction"] --> B["Read item"]
    B --> C["Process item"]
    C --> D{"Reached commit interval or EOF?"}
    D -- "Not yet" --> B
    D -- "Yes" --> E["ItemWriter.write(chunk)"]
    E --> F{"Write succeeded?"}
    F -- "Yes" --> G["Commit"]
    F -- "No" --> H["Rollback"]
    G --> I["Next chunk"]
    H --> J["Handle error / retry / fail"]
~~~

A Step can process thousands of chunks. Therefore, a chunk's transaction is usually much shorter than the entire Job run time. Chunks that have already been committed are kept if a later chunk fails.

### Why does the writer need a transaction?

Suppose the writer writes 100 orders to a database. If it successfully writes 40 orders and then hits an error on the 41st, the transaction helps roll back the current chunk's changes, provided all those write operations participate in the same transaction. The database does not leave 40 half-written rows from the chunk.

Without an appropriate transaction, the system may persist a partial result. When the Job reruns, the application has to distinguish written data from unwritten data, which increases the complexity of idempotency and reconciliation logic.

## 2. Transaction Boundaries and Execution Order

At a conceptual level, a chunk is processed in this sequence:

1. Spring Batch begins the chunk's transaction.
2. The reader provides the input items.
3. The processor processes each item if configured.
4. The writer receives the output chunk and performs the write.
5. The framework updates execution information and the checkpoint according to the mechanisms of the Step and the JobRepository.
6. The transaction commits if all necessary operations succeed.

If an exception causes the chunk to fail and it is configured to roll back, the changes in the current transaction are undone. Spring Batch handles the error according to the Step's policy: it may retry, skip within the allowed limit, or mark the Step as failed.

~~~mermaid
sequenceDiagram
    participant S as Spring Batch
    participant TM as TransactionManager
    participant R as ItemReader
    participant P as ItemProcessor
    participant W as ItemWriter
    participant DB as Database

    S->>TM: Begin transaction
    loop Read up to the commit interval
        S->>R: read()
        R-->>S: Item
        S->>P: process(item)
        P-->>S: Output item or null
    end
    S->>W: write(chunk)
    W->>DB: Insert / update in batch
    DB-->>W: Success
    S->>TM: Commit
    TM-->>S: Transaction completed
~~~

The diagram describes the typical flow. The details of when the reader is called, buffering, and checkpoints depend on the reader type, the Step configuration, and the source resources. The core point is that the chunk's writer executes within the scope of the transaction that the Step manages.

### A commit is not a single event for the whole Job

If a Job processes 1,000,000 items with a commit interval of 1,000, the Job can create about 1,000 chunks. Each successful chunk has its own transaction commit.

When chunk 700 fails:

- Chunks 1 through 699, which have already been committed, still exist.
- The current chunk is rolled back if the error is of a type that requires rollback and the resources participate in the transaction.
- Subsequent chunks have not been processed.
- On restart, Spring Batch uses the metadata and checkpoint to continue from the saved state.

This is why you need to distinguish the state of the Job, the Step, and each chunk. A FAILED Job does not mean all data written within the Job is rolled back.

## 3. The Transaction Manager Passed into the Step

Spring Batch uses PlatformTransactionManager to control transactions. When configuring a chunk-oriented Step, pass the transaction manager into the chunk method:

~~~java
new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .build();
~~~

The transaction manager must manage the resource that the writer uses. For example:

- JdbcTransactionManager or DataSourceTransactionManager manages JDBC transactions for a DataSource.
- JpaTransactionManager manages JPA transactions for the corresponding EntityManagerFactory.
- JtaTransactionManager can coordinate transactions across multiple resources when the infrastructure and configuration support distributed transactions.

In many applications, the Spring Batch metadata and the business data share one database or the same transaction manager. In that case, updating the metadata and the data can be coordinated within the same transaction boundary according to the configuration. If they use different datasources or transaction managers, you must not assume that a single commit will automatically make both sides atomic.

### JDBC configuration example

~~~java
@Bean
PlatformTransactionManager batchTransactionManager(
        DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
~~~

The specific transaction manager class name depends on the Spring version and the application configuration. What matters is that the transaction manager is tied to the DataSource that the writer uses to write.

### The writer needs to use the same managed resource

JdbcBatchItemWriter example:

~~~java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO processed_order
                (order_id, customer_id, amount)
            VALUES
                (:orderId, :customerId, :amount)
            """)
        .beanMapped()
        .build();
}
~~~

If the writer uses the same DataSource that the transaction manager manages, the JDBC statements can participate in the chunk's transaction. Spring manages the connection bound to the current transaction; the writer should not open an independent connection on its own and commit separately.

If the writer creates a new connection itself, calls commit manually, or uses a different datasource, the write operations may fall outside the Step's transaction. In that case, a chunk rollback does not necessarily undo the data written over the independent connection.

## 4. How Do Commit and Rollback Work?

### When the chunk succeeds

Suppose the chunk contains 100 items and the writer writes all of them successfully:

1. The write operations are performed on resources participating in the transaction.
2. The writer finishes normally.
3. The framework completes the state and checkpoint updates according to the configuration.
4. The transaction manager commits.
5. The committed changes become durable according to the database's guarantees.

After the commit, the Job can move on to the next chunk.

### When the writer throws an exception

Suppose the writer hits a constraint error while writing the 70th item. If the exception causes the transaction to roll back:

- The inserts or updates of the current chunk are rolled back.
- The changes of previous chunks remain committed.
- The Step can retry, skip, or fail according to the configuration.
- When reprocessing, the reader or the framework may have to provide again the items belonging to the uncommitted chunk.

~~~mermaid
flowchart TD
    A["Chunk transaction"] --> B["Writer writes 100 items"]
    B --> C{"Error?"}
    C -- "No" --> D["Commit the whole chunk"]
    C -- "Yes" --> E["Roll back the current chunk"]
    E --> F{"Retry / skip configured?"}
    F -- "Retry" --> G["Retry according to the policy"]
    F -- "Skip" --> H["Skip the failing item according to the policy"]
    F -- "No" --> I["Step FAILED"]
~~~

Rollback only affects resources that participate in the transaction. If the writer has already sent an email or called an external API, a database rollback cannot retract that action.

### Runtime exceptions and checked exceptions

How Spring transactions handle rollback depends on the transaction attribute's rollback rules and the exception type. By default in many Spring transaction configurations, unchecked exceptions and Errors usually trigger a rollback, while checked exceptions do not necessarily roll back automatically.

Spring Batch can have Step rollback rules and fault-tolerant configuration. When designing a writer that throws checked exceptions, you need to understand the transaction attribute in use and test the actual rollback behavior. Do not assume all exceptions behave the same way.

If you need your own rules, you can configure rollback rules through the transaction attribute or the Step's policy. Change the rules only after you understand the impact on the chunk's data.

## 5. Configuring Transaction Attributes

In addition to the transaction manager, a Step can use transaction attributes to adjust propagation, isolation, timeout, and rollback rules.

Example:

~~~java
@Bean
TransactionAttribute chunkTransactionAttribute() {
    DefaultTransactionAttribute attribute =
        new DefaultTransactionAttribute();

    attribute.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED
    );
    attribute.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED
    );
    attribute.setTimeout(60);

    return attribute;
}
~~~

Attaching the transaction attribute to the chunk Step:

~~~java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        TransactionAttribute chunkTransactionAttribute,
        ItemReader<InputRecord> reader,
        ItemWriter<OutputRecord> writer) {

    return new StepBuilder("importStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(200, transactionManager)
        .reader(reader)
        .writer(writer)
        .transactionAttribute(chunkTransactionAttribute)
        .build();
}
~~~

The meaning of the attributes:

| Attribute | Meaning |
|---|---|
| Propagation | Specifies how the current transaction participates or creates another transaction |
| Isolation | The isolation level when reading and writing data concurrently |
| Timeout | The maximum time a transaction is allowed to run according to the configuration |
| Rollback rules | Specifies which exception types cause the transaction to roll back |

### Propagation

PROPAGATION_REQUIRED is the common choice: join the existing transaction or create a new one if none exists.

PROPAGATION_REQUIRES_NEW creates an independent transaction. If a writer service calls a REQUIRES_NEW method, the operation inside can commit even if the outer chunk transaction rolls back. This is sometimes useful for audit or error recording, but it must be used deliberately because it breaks the assumption that all changes in the writer belong to the same commit unit.

Do not use REQUIRES_NEW for primary business write operations if you expect them to roll back together with the chunk.

### Isolation

Isolation determines how a transaction sees concurrent changes from other transactions. For example, READ_COMMITTED prevents reading uncommitted data, but does not guarantee that every repeated query within the same transaction always returns the same result.

Choose isolation based on the database and the business. Isolation that is too high can increase locking or reduce concurrency; isolation that is too low can cause consistency problems in concurrent queries and updates.

### Timeout

Timeout limits the transaction's duration. The value needs to fit the chunk size, the batch write time, and the database load. A timeout that is too short can make a valid chunk fail; a timeout that is too long can hold locks for a long time when there is a problem.

Do not increase the timeout to hide a slow writer. Measure the processing time and optimize the SQL, indexes, batch size, or chunk size.

## 6. Commit Interval and Writer Performance

The commit interval directly affects the number of transactions and the amount of data in each chunk.

| Chunk size | Characteristics | Trade-off |
|---|---|---|
| Small | Frequent commits, few items per transaction | Easy to limit the rollback scope but increases transaction cost |
| Medium | Balances memory, batch writes, and commits | Usually a good starting point to measure |
| Large | Fewer transactions, larger write batches | Uses more memory, holds locks longer, and rollback is more expensive |

Examples:

- 1,000 items with a chunk size of 100 create about 10 chunks.
- 1,000 items with a chunk size of 500 create about 2 chunks.

The actual number of chunks also depends on EOF, filtering, skips, and how the Step handles errors.

### A larger chunk is not always faster

A large chunk can improve throughput when the database optimizes batch writes, but it can also:

- Hold the transaction and locks longer.
- Increase the memory needed to hold items.
- Make rollback take longer.
- Increase the amount of data to reprocess when a chunk fails.
- Put pressure on the transaction log or undo log.

Measure the time of the reader, processor, writer, commit, and rollback. If the writer is the bottleneck, you can optimize the batch SQL before increasing the chunk size.

### Batch writing

JdbcBatchItemWriter uses batch updates to send multiple SQL operations in groups. This is usually more efficient than calling a separate insert statement for each item.

Example SQL that can use named parameters to map properties:

~~~java
.sql("""
    INSERT INTO processed_order
        (order_id, customer_id, amount)
    VALUES
        (:orderId, :customerId, :amount)
    """)
.beanMapped()
~~~

For batch writes to be effective, consider indexes, constraints, triggers, network round-trips, and the JDBC driver configuration. The writer's batch size and the Step's commit interval are related but are not always one and the same parameter.

## 7. The Writer Must Not Commit the Chunk's Transaction Itself

A standard writer should perform the write operations and let the Spring transaction manager decide whether to commit or roll back.

Do not write:

~~~java
public void write(Chunk<? extends Order> chunk) throws Exception {
    Connection connection = dataSource.getConnection();

    try {
        connection.setAutoCommit(false);

        // Write data...

        connection.commit(); // Separate commit inside the writer.
    } catch (Exception ex) {
        connection.rollback();
        throw ex;
    } finally {
        connection.close();
    }
}
~~~

This code opens its own connection and commits separately. If the writer commits successfully and then a later operation in the chunk fails, the outer transaction cannot roll back the data already committed over the separate connection.

Use JdbcTemplate, NamedParameterJdbcTemplate, JdbcBatchItemWriter, or a DAO that uses a transaction-bound connection. Let the Step's transaction manager manage the commit.

Example of a custom writer using JdbcTemplate:

~~~java
public class OrderJdbcWriter implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;

    public OrderJdbcWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        jdbcTemplate.batchUpdate(
            """
            INSERT INTO processed_order(order_id, amount)
            VALUES (?, ?)
            """,
            chunk.getItems(),
            chunk.size(),
            (ps, order) -> {
                ps.setLong(1, order.orderId());
                ps.setBigDecimal(2, order.amount());
            }
        );
    }
}
~~~

JdbcTemplate uses Spring's connection management mechanism. When it uses the same DataSource and transaction manager as the Step, the batch operations can participate in the current transaction.

## 8. FlatFileItemWriter and Transactions

A file writer behaves differently from a JDBC writer. The file system does not participate in a database transaction on its own. However, Spring Batch's FlatFileItemWriter has a mechanism that coordinates with the transaction to manage the content written per chunk.

Example:

~~~java
@Bean
FlatFileItemWriter<Order> orderFileWriter() {
    return new FlatFileItemWriterBuilder<Order>()
        .name("orderFileWriter")
        .resource(new FileSystemResource("output/orders.csv"))
        .encoding(StandardCharsets.UTF_8.name())
        .headerCallback(writer ->
            writer.write("orderId,customerId,amount")
        )
        .delimited()
        .delimiter(",")
        .names("orderId", "customerId", "amount")
        .shouldDeleteIfExists(true)
        .build();
}
~~~

A few points to note:

- FlatFileItemWriter supports a transaction-aware write mechanism and by default coordinates with the chunk's transaction.
- If a chunk rolls back, the content pending commit can be handled by the writer's transaction-aware mechanism.
- Files already committed in earlier chunks still exist if a later chunk fails.
- The file system and the database do not automatically form a distributed transaction just because they are called in the same writer.
- If you use a writer with transactional behavior turned off, you are responsible for restoring the file when a chunk rolls back.

Do not assume the output file and the database always commit or roll back atomically together. If you need to create the final file only after the whole Job completes, you can write to a temporary file per chunk, and then use a completion Step to close, verify, and rename the file. The process needs to be designed to handle restart and leftover temporary files.

### Writing a temporary file and then publishing

A common model:

~~~mermaid
flowchart TD
    A["Chunk writer writes temporary file"] --> B["Chunks commit"]
    B --> C["Step verifies the file"]
    C --> D{"Job completed?"}
    D -- "Yes" --> E["Rename / publish the file"]
    D -- "No" --> F["Keep the temporary file for restart or handling"]
~~~

Renaming a file is usually atomic within the same filesystem if the operating system and filesystem conditions are met. When moving across filesystems or to object storage, the operation may not be atomic. Use file names that include a batch id, check the target file, and handle the case where publish is called again.

## 9. A Writer That Writes to Multiple Resources

A writer may need to write the same data to multiple destinations:

- The business database.
- A report file.
- A message broker.
- Another system's API.
- An object storage service.

If the resources do not share a transaction manager capable of coordinating distributed transactions, you cannot guarantee that all of them commit or roll back together.

For example:

1. The writer writes to the database successfully.
2. The writer sends a message to the broker successfully.
3. Another operation fails.
4. The database transaction rolls back, but the message has already been received by the broker.

The system may now be in an inconsistent state.

### CompositeItemWriter does not create a distributed transaction

CompositeItemWriter helps call multiple delegate writers in one flow:

~~~java
@Bean
CompositeItemWriter<Order> compositeOrderWriter(
        ItemWriter<Order> databaseWriter,
        ItemWriter<Order> auditWriter) {

    return new CompositeItemWriterBuilder<Order>()
        .delegates(databaseWriter, auditWriter)
        .build();
}
~~~

The composite writer only coordinates the calls. It does not create a distributed transaction between the database, a file, and an API on its own. Each delegate needs to participate in an appropriate transaction or have its own compensation mechanism and idempotency.

### Outbox pattern for a database and a message broker

If you need to update the database and publish a message, you can write both the business data and an outbox record within the same database transaction:

1. The writer updates the business table.
2. The writer adds an event to the outbox table.
3. The chunk transaction commits.
4. A separate publisher reads the outbox and sends the message.
5. The publisher marks the event as sent or handles retries.

~~~mermaid
flowchart TD
    A["Chunk writer"] --> B["Database transaction"]
    B --> C["Update business data"]
    B --> D["Add Outbox record"]
    C --> E["Commit"]
    D --> E
    E --> F["Outbox publisher"]
    F --> G["Message broker"]
~~~

The outbox makes writing business data and recording the intent to publish a message atomic within the same database. The publisher can still send duplicates if it does not receive an acknowledgment, so the consumer needs idempotency or deduplication.

### External APIs and idempotency

When the writer calls an API, no database transaction automatically undoes a request that the external system has already processed. Some ways to reduce risk:

- Send a stable idempotency key per item or batch id.
- Store the send status and the acknowledgment result.
- Use an outbox to separate committing data from sending the request.
- Retry with limits and classify transient errors.
- Have a reconciliation process when the request state is unclear.

Do not create a new idempotency key for each retry if you want the target system to recognize it as the same logical operation.

## 10. Skip, Retry, and Rollback When the Writer Hits an Error

A writer can encounter different kinds of errors:

- Unique constraint violation.
- Lost database connection.
- Timeout.
- Deadlock.
- Data that does not meet a constraint.
- Target service error.

Not every error should be handled the same way.

### Retry for transient errors

For example, deadlock errors or some database access errors can be retried:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(DeadlockLoserDataAccessException.class)
    .retryLimit(3)
    .build();
~~~

A retry usually causes the chunk or part of the operation to be executed again, depending on the error type and the Step's fault-tolerant mechanism. The writer must be designed so that retrying does not cause duplicate data or uncontrolled repeated side effects.

### Skip for identified data errors

You can skip a write error if the business allows it:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(DuplicateKeyException.class)
    .skipLimit(20)
    .build();
~~~

However, skipping a writer error does not simply mean skipping exactly one row. Spring Batch may roll back the chunk, identify the item that caused the error, and re-perform the operations using the fault-tolerant mechanism to skip the correct item. The writer needs behavior that is appropriate for this re-invocation process.

Only skip duplicate key errors if the data that actually already exists is equivalent to the desired result. If the old data differs from the new data, ignoring the duplicate can hide a business conflict.

### Distinguishing transient errors from permanent errors

| Error type | Usually appropriate handling |
|---|---|
| Transient deadlock | Retry with a limit |
| Interrupted database connection | Retry according to policy and timeout |
| Malformed data | Fail or skip with recording |
| Constraint violation due to bad data | Investigate, fail, or skip per business rules |
| API returns a transient error | Retry with backoff and idempotency |
| API rejects due to invalid data | Do not retry indefinitely |

Do not retry a permanent error many times, because it usually will not make the data valid. Conversely, do not arbitrarily skip infrastructure errors, because that can leave data missing.

## 11. Independent Transactions Inside the Writer

Some services called from the writer may declare a propagation different from the chunk's transaction.

For example, a method marked REQUIRES_NEW creates its own transaction:

~~~java
@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordWriteAttempt(String batchId, String itemId) {
        // Write the audit in an independent transaction.
    }
}
~~~

If the audit transaction commits successfully but the chunk transaction rolls back, the audit still exists. This can be useful for recording error events or attempts, but you need to understand that the audit describes an attempt, not committed business data.

Some points to consider:

- REQUIRES_NEW can leave the outer transaction suspended while the inner transaction runs.
- It may need an additional connection from the pool.
- When running with many items, the number of independent transactions can grow quickly.
- The audit may record more attempts than the number of items finally committed.
- If recording reject records, you need a key or batch id to avoid duplicates on retry.

Do not use REQUIRES_NEW just to dodge a transaction error or to ensure part of the writer always commits. Define clearly which data must exist independently and which data must roll back together with the chunk.

## 12. Transactions of a Tasklet Step vs. a Chunk Step

A Tasklet Step also runs in a transaction, but the transaction unit differs from a chunk-oriented Step.

| Step type | Typical transaction unit |
|---|---|
| Tasklet Step | Each Tasklet invocation |
| Chunk-oriented Step | Each chunk |

If a Tasklet performs a database update and returns FINISHED, the transaction of that invocation is completed according to the Step configuration.

If a Tasklet returns CONTINUABLE, the framework may call the Tasklet again using the repeat mechanism. Each invocation may have its own transaction according to the configuration.

With a chunk-oriented Step, a large Job is divided into many small transactions. This is a suitable model for importing, transforming, and writing large datasets.

Do not put a Job that processes millions of items into a Tasklet with a single transaction without a special reason. A long transaction can hold locks, increase the transaction log, and make restart difficult.

## 13. Metadata Transactions vs. Business Data

Spring Batch stores metadata in the JobRepository, while the writer usually writes business data. The two parts may use the same database or different datasources.

If the JobRepository and the writer use the same database and the same transaction manager and are configured appropriately, updating the business data and the checkpoint metadata can be coordinated in the same transaction. This helps avoid the situation where data has been committed but the checkpoint has not been saved, or vice versa.

If the metadata and the business data use two independent transaction managers, a commit on one side does not automatically commit the other. When an error occurs between the two commits, the system may need reconciliation or repeated processing.

Things to consider:

- Which datasource is the JobRepository using?
- Which datasource is the writer using?
- Which transaction manager does the Step receive?
- Do the DAOs or services called participate in the current transaction?
- Is there REQUIRES_NEW propagation or an independent connection?
- Does the transaction manager support coordinating multiple resources?

Do not assume by default that just because all beans run in the same Step, all operations are in a single transaction.

## 14. Transactions and Restart

The checkpoints of the reader, writer, and StepExecution help Spring Batch restore state when a Job fails. However, restart is only safe if the committed data and the saved state are consistent.

Suppose a Job processes three chunks:

~~~text
Chunk 1: write -> commit
Chunk 2: write -> rollback
Chunk 3: not yet run
~~~

On restart:

- Chunk 1 has been committed, so it is kept.
- Chunk 2 is reprocessed according to the checkpoint and the reader mechanism.
- Chunk 3 is processed after chunk 2 succeeds.

If the writer writes to a system outside the transaction, it can happen that the target system has received chunk 2's data but the database rolled back. On restart, chunk 2 is sent again and creates duplicate records.

Therefore, a writer should be designed in one of these directions:

- Idempotent: resending the same operation does not produce a different result.
- Has a unique key or upsert by business key.
- Has a status table to detect items already processed.
- Has an outbox mechanism or acknowledgment from the target system.
- Has a reconciliation process when it cannot be determined whether a request succeeded.

### Idempotent database writer

For example, instead of an insert that always causes a duplicate key error, you can use an upsert statement appropriate to the database:

~~~sql
-- Illustrative syntax, PostgreSQL style.
INSERT INTO processed_order(order_id, amount)
VALUES (:orderId, :amount)
ON CONFLICT (order_id)
DO UPDATE SET amount = EXCLUDED.amount;
~~~

An upsert is only appropriate when updating the old record with the new data is correct for the business. If a duplicate record must be treated as an error, keep the unique constraint and handle the duplicate according to a clear policy.

## 15. Monitoring Commits and Rollbacks

StepExecution stores counters that help observe transaction behavior:

| Property | Meaning |
|---|---|
| commitCount | Number of commits of the Step |
| rollbackCount | Number of rollbacks |
| readCount | Number of items read |
| writeCount | Number of items written |
| filterCount | Number of items filtered |
| readSkipCount | Number of read errors skipped |
| processSkipCount | Number of processing errors skipped |
| writeSkipCount | Number of write errors skipped |

For example, if rollbackCount rises high, check the logs to find the cause: deadlock, timeout, constraint error, or a failed writer side effect.

You can access StepExecution information in a listener:

~~~java
@Bean
StepExecutionListener transactionMetricsListener() {
    return new StepExecutionListener() {
        @Override
        public void beforeStep(StepExecution stepExecution) {
            // Record the start time.
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            log.info(
                "step={}, commits={}, rollbacks={}, writes={}",
                stepExecution.getStepName(),
                stepExecution.getCommitCount(),
                stepExecution.getRollbackCount(),
                stepExecution.getWriteCount()
            );
            return null;
        }
    };
}
~~~

The listener illustrates how to record statistics when the Step ends. In a real application, use an appropriate logging framework and metrics, and avoid logging sensitive item data.

The counters help detect trends, but they do not replace business data reconciliation. For example, a writeCount equal to the expected number of items does not guarantee every record is correct if the writer mapped the wrong column or wrote the wrong value.

## 16. Testing Writer Transactions

Transaction tests should verify both the commit and rollback cases. Do not only check whether the writer was called.

### Testing commit

An integration test can:

1. Prepare a test database.
2. Launch the Step with some input items.
3. Wait for the Job to complete.
4. Query the target table.
5. Verify that all valid items were written.
6. Verify that commitCount and writeCount are appropriate.

### Testing rollback

Create a writer or constraint that makes a chunk fail. After the Step fails, query the database to verify that no half-finished data remains from the rolled-back chunk.

Example scenario:

~~~text
Chunk 1: 100 items -> commit
Chunk 2: 100 items -> writer throws an exception
Expected result:
  - Chunk 1 still exists.
  - Chunk 2 leaves no partial data.
  - The Step records a rollback or failure according to the policy.
~~~

If the Step is configured with retry, check the number of attempts and the final result. If skip, verify that the skipped item is recorded and the remaining valid items are processed.

### Testing side effects outside the transaction

If the writer calls an API or a message broker, you need to test scenarios such as:

- The API received the request but the writer did not receive the response.
- The database rolls back after the API succeeded.
- The Job restarts and resends the item.
- The target system receives the same idempotency key multiple times.

The tests must verify that the side effect does not create duplicate or incorrect business results.

### Using test transactions correctly

Spring test can wrap a test method in a transaction on its own and roll back when the test ends. This is useful but can make the observed result differ from the Job's real transaction if it is not clearly controlled.

For batch testing, you need to distinguish the test's transaction, the JobRepository's transaction, and the Step's transaction. Use JobLauncherTestUtils or launch the Job in a test context with a configuration similar to the application to verify real behavior.

## 17. Common Design Mistakes

### Committing inside the writer on its own

A writer that commits over its own connection means the chunk transaction cannot roll back that operation. Use transaction-bound resources managed by Spring.

### Using the wrong transaction manager

If the Step uses the transaction manager of datasource A but the writer writes to datasource B, the write operation may not participate in the Step's transaction. Verify that the datasource and the transaction manager match.

### Believing every side effect rolls back

Emails, HTTP requests, messages already sent, or files already read by another system do not disappear when the database rolls back. Use an outbox, idempotency, or a compensation process.

### A chunk that is too large

A large chunk can hold locks for a long time, increase memory, and make rollback expensive. Choose the commit interval based on measurement.

### Retrying a non-idempotent writer

A writer that is called again can write duplicates or send the same request multiple times. Design write operations that can be safely repeated.

### Skipping duplicates without checking the data's meaning

A duplicate key may be an already-processed record or a data conflict. Skip only when the business determines the two results are equivalent.

### Using REQUIRES_NEW without intent

An independent transaction can commit even though the chunk rolls back. Use it only when the data needs to be saved independently and the consequences on retry have been handled.

### Confusing a database commit with publishing a file

A successful database write does not mean the file is also published atomically. Separate the temporary file write step from the final publish if needed.

### Not testing rollback

A writer may run successfully in a test with valid data but leave partial data on error. You need to create a controlled error to verify that the transaction really works.

## 18. Process for Designing a Safe Writer Transaction

When building a new writer, you can follow this sequence:

1. **Determine the destination:** database, file, queue, API, or multiple resources.
2. **Choose the transaction manager:** verify the manager manages the correct datasource and the necessary resources.
3. **Determine the chunk size:** choose the commit interval based on volume, write time, and rollback capability.
4. **Use transaction-bound APIs:** avoid opening your own connection and committing independently in the writer.
5. **Classify errors:** determine which errors to retry, skip, or fail the Step on.
6. **Design idempotency:** ensure retry and restart do not create duplicate data.
7. **Handle side effects outside the transaction:** consider an outbox, publish-after-commit, or a compensation mechanism.
8. **Design checkpoints:** ensure the reader and metadata recover correctly after a rollback.
9. **Record metrics:** monitor commits, rollbacks, write count, and write time.
10. **Test:** verify commit, rollback, retry, skip, and restart on a test database.

## 19. Key Takeaways

- A chunk-oriented Step uses a transaction per chunk, not a single transaction for the whole Job.
- ItemWriter performs writes within the chunk's transaction scope when it uses the correct resources and transaction manager.
- The writer should not open an independent connection or commit on its own.
- A commit makes the chunk's changes durable; a rollback undoes changes on the resources participating in the transaction.
- A chunk that has been committed is kept if a later chunk fails.
- The commit interval affects performance, memory, locks, and the rollback scope.
- Transaction attributes control propagation, isolation, timeout, and rollback rules.
- REQUIRES_NEW can commit independently of the chunk transaction.
- Files, APIs, and message brokers are not implicitly in the same transaction as the database.
- Retry and restart require the writer to have idempotency or an appropriate reconciliation mechanism.
- An outbox is a more reliable way to coordinate database updates and message publishing.
- Monitor commitCount, rollbackCount, and writeCount; test both commit and rollback.

When you understand the chunk's transaction boundary clearly and make sure the writer participates in the correct transaction manager, Spring Batch can write data in groups consistently, handle errors in a controlled way, and restart more safely.

