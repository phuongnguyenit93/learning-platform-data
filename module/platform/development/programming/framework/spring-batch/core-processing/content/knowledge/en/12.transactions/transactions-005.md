# Transaction manager for databases

In Spring Batch, the transaction manager determines how a Step begins, commits, and rolls back transactions when processing data. For a database writer, the transaction manager must manage the correct DataSource or persistence resource that the writer uses. When configured correctly, the write operations in a chunk can be committed together or rolled back together if an error occurs.

The transaction manager also affects how checkpoints and metadata are stored. Therefore, when building a batch job, you need to distinguish the transaction of the business database from the transaction that the JobRepository uses to store execution state.

## 1. What does the transaction manager do?

Spring manages transactions through the PlatformTransactionManager abstraction. This abstraction lets the framework begin a transaction, join an existing transaction, and commit or roll back without forcing business code to issue BEGIN, COMMIT, or ROLLBACK commands itself.

In Spring Batch, the transaction manager is used by the Step to control the transaction of each processing unit. In a chunk-oriented Step, a chunk is typically one transaction:

~~~text
Begin transaction
      |
      v
Read items
      |
      v
Process items
      |
      v
Write chunk to database
      |
      v
Update checkpoint / stream state
      |
      v
Commit transaction
~~~

If the writer hits an error that causes the transaction to roll back, the changes on the resources participating in that transaction are undone. Chunks committed earlier are kept.

The transaction manager does not decide the business rules about what data to write. It manages the transaction boundary and coordinates with transaction resources such as a JDBC Connection or a JPA EntityManager.

## 2. PlatformTransactionManager and commonly used implementations

PlatformTransactionManager is Spring's common interface for imperative transactions. Common implementations for databases include:

| Transaction manager | Managed resource | Typical use case |
|---|---|---|
| DataSourceTransactionManager | JDBC DataSource | JDBC and JdbcTemplate |
| JdbcTransactionManager | JDBC DataSource | JDBC; adds SQL error translation at the transaction boundary |
| JpaTransactionManager | JPA EntityManagerFactory | Spring Data JPA or EntityManager |
| JtaTransactionManager | JTA transaction coordinator | Coordinating multiple resources that support distributed transactions |

Choose the implementation according to how the writer accesses the database:

- If the writer uses JdbcBatchItemWriter, JdbcTemplate, or direct JDBC, the transaction manager needs to manage the correct DataSource.
- If the writer uses JPA or a Spring Data repository, JpaTransactionManager is typically the appropriate choice for the corresponding EntityManagerFactory.
- If a transaction must coordinate multiple independent resources, you need to evaluate JTA or another design such as outbox/saga. Do not assume that two local transaction managers automatically form one atomic transaction.

### DataSourceTransactionManager and JdbcTransactionManager

DataSourceTransactionManager manages transactions for a JDBC DataSource. It binds a JDBC Connection to the current thread so that JDBC operations participate in that transaction when using the same DataSource and a Spring-supported access mechanism.

JdbcTransactionManager is a JDBC-specific variant that can translate some SQLExceptions arising from commit/rollback operations into Spring's exception hierarchy. In a modern Spring application, you can choose either one depending on the framework version and the project's conventions.

An example JDBC transaction manager configuration:

~~~java
@Bean
PlatformTransactionManager batchTransactionManager(DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
~~~

If the Spring version in use does not yet have JdbcTransactionManager, you can use DataSourceTransactionManager:

~~~java
@Bean
PlatformTransactionManager batchTransactionManager(DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
~~~

Do not arbitrarily create a new transaction manager for each writer. Components that need to participate in the same transaction must use the correct manager and resource according to the Step's configuration.

## 3. Attaching the transaction manager to a chunk-oriented Step

In Spring Batch 5, the transaction manager is passed directly into the chunk method of StepBuilder.

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager batchTransactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, batchTransactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

In the example:

- chunk(100, batchTransactionManager) configures the commit interval as 100 and selects the transaction manager for the chunk.
- The reader supplies items one at a time.
- The processor transforms or filters items.
- The writer writes the remaining items in the chunk.
- The framework manages the transaction per chunk.

If a chunk processes 100 items, the writer writes to the database in the current transaction. When all operations complete, the framework commits. If an error requiring rollback occurs before the commit, the transaction manager rolls back the chunk according to the configured rules.

With Spring Batch 4, the StepBuilder configuration can differ, especially how the transaction manager is passed into chunk. Use the API for the correct version instead of copying the Batch 5 example verbatim into an older project.

## 4. Example: a JDBC writer participating in the Step's transaction

JdbcBatchItemWriter uses a DataSource to write multiple items in a chunk. When the writer's DataSource is managed by the Step's transaction manager, the JDBC statements can participate in the same transaction.

~~~java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                insert into orders (id, customer_id, amount)
                values (:id, :customerId, :amount)
                """)
            .beanMapped()
            .build();
}
~~~

Step configuration:

~~~java
@Bean
Step writeOrdersStep(
        JobRepository jobRepository,
        @Qualifier("batchTransactionManager")
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        JdbcBatchItemWriter<Order> orderWriter) {

    return new StepBuilder("writeOrdersStep", jobRepository)
            .<Order, Order>chunk(200, transactionManager)
            .reader(orderReader)
            .writer(orderWriter)
            .build();
}
~~~

You need to ensure the two beans really use the same DataSource:

- The transaction manager is created with the target DataSource.
- JdbcBatchItemWriter is configured with that very DataSource.
- Do not open a new Connection with DriverManager inside the writer.
- Do not commit the Connection yourself in the writer.

If the writer obtains an independent JDBC Connection outside the Spring mechanism, the write operation may not participate in the Step's transaction. In that case, rolling back the chunk cannot undo the writes made on the independent connection.

## 5. Transaction manager with a JPA writer

If the writer uses JPA or Spring Data JPA, the transaction manager must manage the corresponding EntityManagerFactory.

For example:

~~~java
@Bean
PlatformTransactionManager orderJpaTransactionManager(
        EntityManagerFactory entityManagerFactory) {

    return new JpaTransactionManager(entityManagerFactory);
}
~~~

A writer can call a repository:

~~~java
public class OrderJpaWriter implements ItemWriter<Order> {

    private final OrderRepository orderRepository;

    public OrderJpaWriter(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        orderRepository.saveAll(chunk.getItems());
    }
}
~~~

A Step using the JPA transaction manager:

~~~java
@Bean
Step persistOrdersStep(
        JobRepository jobRepository,
        @Qualifier("orderJpaTransactionManager")
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemWriter<Order> orderJpaWriter) {

    return new StepBuilder("persistOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .writer(orderJpaWriter)
            .build();
}
~~~

In some configurations, Spring Data repositories participate in the transaction managed by JpaTransactionManager because they use the same EntityManagerFactory and the transaction-bound EntityManager. If a repository uses a different transaction manager or a different EntityManagerFactory itself, you need to re-check how it participates in the transaction.

With JPA, calling saveAll() does not necessarily mean the SQL has been sent immediately. The EntityManager may defer the flush until an appropriate time. A constraint error may surface at flush or commit, not necessarily right at the saveAll() line.

## 6. The chunk's transaction differs from the whole Job's transaction

A Job can contain multiple Steps. Each Step has its own transaction according to its configuration. With a chunk-oriented Step, a transaction is typically created and ended for each chunk.

For example, a Job with three Steps:

~~~text
Job
 |
 +--> Step A
 |      chunk 1 -> commit
 |      chunk 2 -> commit
 |
 +--> Step B
 |      chunk 1 -> commit
 |      chunk 2 -> rollback
 |
 +--> Step C (does not run on the successful flow)
~~~

If Step B fails, the chunks already committed in Step A still exist. Step B's transaction manager does not automatically roll back the transactions already completed by Step A.

Therefore, a multi-Step Job is not implicitly a single database transaction. If the business requires undoing multiple Steps that have already committed, you need to design compensation, staging, or a separate business process.

## 7. The Step's transaction manager and the JobRepository

The JobRepository stores Spring Batch metadata such as JobInstance, JobExecution, StepExecution, and ExecutionContext. Metadata update operations also need transactions.

You need to distinguish:

- **Step transaction manager:** manages the transaction of the chunk or tasklet, typically tied to the business database.
- **JobRepository transaction manager:** manages the transaction that stores metadata; it can use the same or a different transaction manager than the business database depending on the configuration.

If the business data and the JobRepository use the same database and the same transaction resource, they can participate in the same transaction in an appropriate configuration. In that case, business writes and the checkpoint can commit or roll back together.

If the JobRepository uses a separate database, the two places are not automatically atomic:

~~~text
Chunk processing
    |
    +--> Business database transaction
    |
    +--> JobRepository metadata transaction
~~~

A situation can occur where the business data has committed but the metadata has not been updated, or where the metadata and the business data are not in the same state after a system failure. You need to understand clearly which transaction manager is used for each resource and design the corresponding recoverability.

Do not assume that just because the JobRepository and the writer appear in the same Step, they definitely share a transaction. Check the actual configuration.

## 8. Configuring multiple DataSources

An application can use one database for business data and another database for Spring Batch metadata.

For example:

- batchMetaDataSource stores BATCH_JOB_INSTANCE, BATCH_JOB_EXECUTION, and the other metadata tables.
- businessDataSource stores orders, customers, and the other business tables.

You can declare separate transaction managers:

~~~java
@Bean
@Primary
PlatformTransactionManager businessTransactionManager(
        @Qualifier("businessDataSource") DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}

@Bean
PlatformTransactionManager batchMetadataTransactionManager(
        @Qualifier("batchMetaDataSource") DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
~~~

When configuring Spring Batch, you need to specify clearly which manager is used for the JobRepository and which for the Step writing business data, according to the configuration API of the version in use. For example, a Step can receive businessTransactionManager in chunk(...).

Do not rely on @Primary to guess that every component will pick the right manager. When there are multiple beans of the PlatformTransactionManager type, use an explicit @Qualifier at the configuration points.

### Two-database diagram

~~~text
Spring Batch Job
      |
      +---------------------------+
      |                           |
      v                           v
JobRepository                 Business Step
      |                           |
      v                           v
batchMetaDataSource           businessDataSource
      |                           |
      v                           v
BATCH_* tables                orders / customers
      |                           |
      v                           v
metadata transaction          chunk transaction
~~~

Two local transaction managers do not coordinate an atomic commit by themselves. If one transaction commits while the other fails, the application must have a way to detect and handle the out-of-sync state.

## 9. One transaction manager or several?

There is no single configuration suitable for every application. Base the decision on the actual resources.

| Architecture | Commonly used approach |
|---|---|
| JobRepository and business tables on the same DataSource | One appropriate transaction manager can manage the chunk and the metadata according to the configuration |
| Business JDBC writer on one DataSource | DataSourceTransactionManager or JdbcTransactionManager for that DataSource |
| JPA writer on one EntityManagerFactory | The corresponding JpaTransactionManager |
| Metadata and business data on two DataSources | Configure the manager explicitly for the repository and the Step; design consistency/recovery |
| A chunk writing to multiple independent databases | Evaluate JTA or split the process using outbox/staging |
| Writing to a database and calling an external API | Database transaction plus idempotency/outbox/compensation |

JTA can coordinate multiple resources if the database, driver, and environment support XA and are configured correctly. Distributed transactions increase operational complexity and have their own cost. For many modern systems, an outbox or an eventual consistency process can be simpler and easier to recover.

## 10. Propagation and the existing transaction

The Spring transaction manager uses transaction propagation to decide how a method participates in an existing transaction.

Commonly encountered propagation modes:

- **REQUIRED:** joins the existing transaction; if there is none, creates a new one.
- **REQUIRES_NEW:** suspends the current transaction and creates a new one.
- **SUPPORTS:** joins if a transaction exists; otherwise runs without a transaction.
- **MANDATORY:** requires a current transaction to exist.
- **NOT_SUPPORTED:** suspends the current transaction and runs without a transaction.
- **NEVER:** requires that no current transaction exists.

When a writer calls a service with @Transactional, the default REQUIRED typically makes the service join the running chunk transaction, if the correct transaction manager and resource are used.

For example:

~~~java
@Service
public class OrderWriteService {

    private final OrderRepository repository;

    public OrderWriteService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void saveOrders(List<Order> orders) {
        repository.saveAll(orders);
    }
}
~~~

If the method is called within the chunk transaction and uses the same transaction manager, the saveOrders operation typically participates in that transaction.

If you set REQUIRES_NEW, the service can commit independently of the chunk. When the chunk rolls back, the data already committed in the new transaction does not automatically roll back with the outer transaction. This can break the assumption that the whole chunk is an atomic unit.

Only use REQUIRES_NEW with clear intent, such as writing an independent audit that the business accepts keeping even if the chunk fails. Do not use it as a way to fix a transaction that is not configured correctly.

## 11. Rollback when the writer fails

When the writer throws an exception, Spring Batch handles it according to the Step's transaction and fault tolerance configuration.

If the error causes the transaction to roll back:

- Database operations participating in the current transaction are undone.
- The chunk's checkpoint is not considered successfully committed.
- The Step can retry or skip the item if the configuration allows.
- If the error is not handled, the Step can end with a FAILED status.

An example retry configuration for a transient error:

~~~java
return new StepBuilder("writeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

The names and the fault-tolerance API may differ by Spring Batch version. Choose appropriate exceptions and determine clearly whether retry is safe for the writer.

Not every exception has the same rollback behavior by default. Spring transactions have rollback rules per exception type, which can be customized. Check the rollback configuration when using custom exceptions or when you want a certain type of error not to cause a rollback.

If the writer calls an external API and then throws an error, the database transaction may roll back but the API has already performed the action. This is why a writer that targets something other than a database needs idempotency or a publish-after-commit mechanism.

## 12. Isolation level and locks

The transaction manager can also control the isolation level for a transaction. Isolation affects how a transaction sees data from other transactions and how the database handles locks.

Commonly encountered isolation levels:

| Isolation | General characteristics |
|---|---|
| READ_UNCOMMITTED | May read uncommitted data if the database supports it |
| READ_COMMITTED | Reads only committed data |
| REPEATABLE_READ | Data read within the transaction is protected from some concurrent changes |
| SERIALIZABLE | A stricter isolation level that can reduce concurrency and increase locking/contention |

The actual isolation level and detailed behavior depend on the database. For example, some databases implement isolation with MVCC and differ from the theoretical understanding.

For a batch job, a transaction that is too long can hold locks for a long time and affect online workloads. A smaller chunk size typically makes transactions shorter but increases the number of commits. Consider isolation, indexes, queries, commit interval, and concurrent load.

You can configure isolation/timeout for the Step's transaction using the corresponding transaction attribute APIs in the Spring Batch version in use. Do not raise isolation to SERIALIZABLE just to be “more certain” without measuring the impact and without identifying the consistency problem you need to solve.

## 13. A Tasklet Step also needs a transaction manager

A Tasklet Step does not use ItemReader/ItemWriter in chunks, but it can still run in a transaction. When configuring a Step with a tasklet, pass the transaction manager so Spring Batch manages the transaction of each Tasklet invocation according to the configuration.

~~~java
@Bean
Step archiveOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet archiveOrdersTasklet) {

    return new StepBuilder("archiveOrdersStep", jobRepository)
            .tasklet(archiveOrdersTasklet, transactionManager)
            .build();
}
~~~

If the Tasklet executes one SQL statement or multiple database operations, they can participate in this transaction when using the correct resource.

A Tasklet can be called repeatedly depending on RepeatStatus. For each execution, you need to clearly understand the corresponding transaction boundary. Do not assume that a whole long process inside a Tasklet can automatically roll back every outside effect.

## 14. Do not open connections and commit manually

A common mistake is a writer creating a JDBC connection itself with DriverManager and then committing or closing the connection inside write().

~~~java
// Avoid this approach in a writer that participates in the Step's transaction.
Connection connection = DriverManager.getConnection(url, user, password);
connection.setAutoCommit(false);
// Perform INSERT...
connection.commit();
connection.close();
~~~

This connection may be outside the transaction managed by Spring. When Spring Batch rolls back the chunk, the statements already committed manually are not undone.

Inject JdbcTemplate, a configured DataSource, or use JdbcBatchItemWriter. If you need direct JDBC, use a mechanism that obtains a Connection bound to the Spring transaction, such as DataSourceUtils, and do not commit/close a resource owned by the transaction manager yourself.

Similarly with JPA, do not create an independent EntityManager yourself if you want to participate in the Step's transaction. Use an EntityManager or Spring Data repository that is managed by Spring and uses the same EntityManagerFactory.

## 15. Transaction manager and threads

Spring's imperative transactions are typically bound to the executing thread. A chunk's transaction does not spread to another thread just because the code launches an asynchronous task.

For example, if the writer sends the data-writing work to a different executor and returns immediately, the new thread does not implicitly participate in the calling thread's chunk transaction. The Step may commit before the write task completes.

Do not launch asynchronous write work from a writer unless you have a clear design for:

- When the write completes relative to when the chunk commits.
- How to propagate the transaction context or use a separate transaction.
- How to wait for and handle errors from the child tasks.
- Idempotency and retryability.
- How to synchronize the checkpoint with the actual write results.

For parallel processing in Spring Batch, use an appropriate concurrency/partitioning model and understand the transaction boundary of each worker. Each worker/partition typically needs its own transaction and StepExecution according to the configuration.

## 16. Verifying the transaction manager configuration

When a database writer does not roll back as expected, check from the configuration down to the actual resource.

1. Determine whether the writer uses JDBC, JPA, or a separate client.
2. Determine the DataSource or EntityManagerFactory that the writer uses.
3. Check that the Step's transaction manager manages that very resource.
4. If there are multiple PlatformTransactionManagers, check the @Qualifier and the injected bean.
5. Check whether a service called from the writer joins the current transaction or creates its own.
6. Confirm the writer does not open its own connection, commit by itself, or write through another resource.
7. Check rollback rules, propagation, and isolation.
8. Determine which transaction manager and DataSource the JobRepository uses.
9. Check the SQL log, the transaction debug log, and the database state after the rollback.
10. Test an error occurring mid-chunk to confirm that all changes that should roll back really are undone.

Do not use a Job ending FAILED as the only evidence that the data has been rolled back. A Job can fail after some chunks have committed or after an effect outside the transaction has occurred.

## 17. Testing a Step's transaction

An integration test can run the Step with test data, deliberately make the writer throw an error on one item, and verify the transaction behavior.

Example scenario:

~~~text
Chunk size = 3
Input = [A, B, C, D, E, F]

Chunk 1:
  write A, B, C
  commit

Chunk 2:
  write D
  writer fails at E
  rollback

Expected result if everything is written in the same transaction:
  A, B, C exist
  D and E are not committed
  Step FAILED
~~~

When testing, use a real database in the test environment or an appropriate embedded database to verify actual transactions. A mock transaction manager only verifies interactions; it does not prove that the JDBC/JPA resource participated in the same transaction.

Scenarios to include:

- Successfully writing one chunk.
- An error in the writer rolling back the whole chunk.
- A retry being invoked again without creating duplicate data.
- Skip working correctly when configured.
- Two Steps using the transaction manager that matches their resource.
- Metadata and business data handled per the one-database or multi-database architecture.
- A Tasklet rolling back when a database operation fails.

## 18. Common configuration mistakes

**The transaction manager uses the wrong DataSource.** The writer writes using DataSource A but the Step uses a manager managing DataSource B. The write statements do not participate in the intended transaction.

**Multiple transaction managers but no Qualifier.** Spring may inject the wrong bean, or the application relies on @Primary while the Step needs a different manager.

**Treating the JobRepository and the business database as one transaction.** Two different DataSources do not commit/roll back atomically by themselves.

**Committing manually in the writer.** Part of the chunk may already be durable even though the rest fails.

**Using REQUIRES_NEW without intent.** Data can commit independently and not roll back with the chunk.

**Making writes asynchronous.** A new thread does not automatically participate in the chunk's transaction; the framework may commit before the write completes.

**A chunk that is too large or a transaction that is too long.** Locks, connections, and database resources can be held for a long time, reducing the ability to serve other workloads.

**Assuming every side effect rolls back.** Files, email, HTTP APIs, and message brokers are typically outside the database transaction.

## 19. Procedure for choosing a transaction manager

When designing a Spring Batch Step that writes to a database, follow this sequence:

1. Determine the write technology: JDBC, JPA, or another resource.
2. Determine the exact DataSource or EntityManagerFactory.
3. Choose the transaction manager that manages that resource.
4. Pass the manager into the Step's chunk(...) or tasklet(...).
5. Ensure the writer/service uses the same resource and participates in the Spring transaction.
6. Determine which manager the JobRepository uses to store metadata.
7. If the metadata and business data are on two resources, design consistency, restart, and reconciliation.
8. Choose the commit interval and isolation based on load, locks, and business requirements.
9. Test rollback, retry, and restart with a database in a test environment.

For a simple JDBC Step, a JdbcTransactionManager or DataSourceTransactionManager managing the same DataSource as the JdbcBatchItemWriter is typically an easy-to-understand configuration. For a JPA Step, use a JpaTransactionManager tied to the EntityManagerFactory that the repository uses. With multiple databases, configure the managers explicitly and do not rely on assumptions about atomic transactions.

The transaction manager is the component connecting Spring Batch to the database's transaction resources. When the Step uses the right manager, the writer participates in the right transaction and the checkpoint is stored in a consistently configured way, each chunk can become a reliable commit/rollback unit. That helps a batch job process data in parts, recover from errors, and coexist safely with other workloads on the database.

