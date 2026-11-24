# Tasklet transaction boundary

In Spring Batch, `Tasklet` is a way to build a step that performs a unit of work defined by the application, such as cleaning up old data, calling a stored procedure, generating a summary file, or performing an administrative operation. When it runs in a `TaskletStep`, the `Tasklet.execute(...)` method is executed inside a transaction managed by the step.

The important point is that the tasklet's transaction boundary is tied to **each call to `execute`**. If the tasklet returns `RepeatStatus.FINISHED`, the step ends after that call. If the tasklet returns `RepeatStatus.CONTINUABLE`, Spring Batch calls the tasklet again for the next iteration; each subsequent call has its own transaction. Therefore, a tasklet can run in a single transaction or split its work into several short transactions depending on how it uses `RepeatStatus`.

The transaction boundary determines which operations are committed or rolled back together, which metadata is saved along with the checkpoint, and where the tasklet can continue from on restart. Understanding this boundary correctly helps you avoid holding a transaction too long, avoid writing partial data, and design tasklets that can recover after a failure.

## Tasklet and TaskletStep

`Tasklet` is a simple interface with a single method:

```java
public interface Tasklet {
    RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception;
}
```

A tasklet returns one of the commonly used repeat statuses:

| Result | Meaning |
| --- | --- |
| `RepeatStatus.FINISHED` | The tasklet's work is complete; the step can end successfully |
| `RepeatStatus.CONTINUABLE` | There is more work; the framework continues calling `execute` in the next iteration |

`TaskletStep` is the type of step that executes a tasklet. It coordinates the transaction, calls the tasklet, updates the `StepExecution` and `ExecutionContext`, and then repeats if the tasklet returns `CONTINUABLE`.

General flow:

```text
TaskletStep starts
       |
       v
Open a transaction for one execute call
       |
       v
Tasklet.execute(...)
       |
       +----> change business data
       |
       +----> update ExecutionContext
       |
       v
Update StepExecution / metadata
       |
       v
COMMIT or ROLLBACK
       |
       v
RepeatStatus?
    /        \
FINISHED   CONTINUABLE
    |           |
    v           +----> open a new transaction and call execute again
End the step
```

The diagram shows the boundary at a conceptual level. Spring Batch manages calling the tasklet and saving metadata within the step's lifecycle; in the ordinary case the application does not need to manually open a transaction around each `execute` call.

## Where is the transaction opened?

When `TaskletStep` executes an iteration, it uses the `PlatformTransactionManager` configured for the step to begin a transaction. Inside that transaction, the framework calls `Tasklet.execute(...)`. After the tasklet returns normally, Spring Batch applies the step's contribution, updates the execution context, and saves the changes to the `StepExecution` metadata according to the step's lifecycle. The transaction is then committed.

If the tasklet throws an exception or a metadata update fails, the transaction can roll back according to the step's transaction attribute. By default, `TaskletStep` is designed to roll back when the tasklet throws an exception; if the application customizes the transaction attributes, you need to understand the new rollback rule clearly.

With JDBC or JPA, business operations participate in the same transaction when they use the right resource and transaction manager. For example, if a tasklet calls a `JdbcTemplate` that uses the same `DataSource` as the step's transaction manager, the SQL statement usually participates in the active transaction. If the tasklet calls a service that uses a different transaction manager, or writes to a system outside the database, that operation is not automatically part of the current transaction.

## Configuring the transaction manager for a TaskletStep

In Spring Batch 5, the transaction manager is passed directly when declaring a tasklet step with `StepBuilder`:

```java
@Bean
Step archiveOldOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ArchiveOldOrdersTasklet tasklet) {

    return new StepBuilder("archiveOldOrdersStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
```

`transactionManager` manages the transaction of each `execute` call. In older Spring Batch versions, the builder declaration may differ; use the API that matches your project's version. Do not skip the transaction manager or create a manager that does not manage the datasource the tasklet is using.

An example of a tasklet that updates database data:

```java
public class ArchiveOldOrdersTasklet implements Tasklet {

    private final JdbcTemplate jdbcTemplate;

    public ArchiveOldOrdersTasklet(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        jdbcTemplate.update("""
                UPDATE orders
                SET status = 'ARCHIVED'
                WHERE status = 'COMPLETED'
                  AND completed_at < CURRENT_DATE - INTERVAL '90 days'
                """);

        return RepeatStatus.FINISHED;
    }
}
```

This is a PostgreSQL SQL example. The tasklet runs the update statement and then returns `FINISHED`; if the update and the metadata repository both participate in the step's transaction, the related changes can commit or roll back together. With another database, the date arithmetic syntax may need to be adjusted.

## One execute call corresponds to one transaction

For a tasklet that returns `FINISHED` right after one operation, all the work in the `execute` call lies within one step transaction. This suits small, short-running work that can be performed as an atomic unit.

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    jdbcTemplate.update("DELETE FROM temporary_records WHERE created_at < ?", cutoff);
    jdbcTemplate.update("INSERT INTO cleanup_audit(job_date, deleted_at) VALUES (?, CURRENT_TIMESTAMP)",
            businessDate);

    return RepeatStatus.FINISHED;
}
```

If both statements use the step's datasource and transaction manager, they belong to the same transaction. If the second statement fails and the error triggers a rollback, the first delete statement is rolled back as well. This is the benefit of grouping database operations that need to be consistent into the same tasklet invocation.

However, the transaction exists for the entire time `execute` is running. If the tasklet processes millions of records, calls a slow API, or waits for an external system, the transaction can hold a connection and locks for too long. In that case, split the work into small units and return `CONTINUABLE` after each completed unit.

## RepeatStatus.CONTINUABLE creates multiple short transactions

A tasklet can process part of the work in each `execute` call and then return `RepeatStatus.CONTINUABLE`. `TaskletStep` ends the current call's transaction before performing the next iteration. In this way, each page, file segment, or group of records can be committed separately.

For example, a tasklet that processes data page by page:

```java
public class ProcessOrdersByPageTasklet implements Tasklet {

    private final OrderPageReader reader;
    private final OrderPageWriter writer;

    public ProcessOrdersByPageTasklet(
            OrderPageReader reader,
            OrderPageWriter writer) {
        this.reader = reader;
        this.writer = writer;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext context =
                contribution.getStepExecution().getExecutionContext();
        int page = context.getInt("nextPage", 0);

        List<Order> orders = reader.readPage(page);
        if (orders.isEmpty()) {
            return RepeatStatus.FINISHED;
        }

        writer.writePage(orders);
        context.putInt("nextPage", page + 1);

        return RepeatStatus.CONTINUABLE;
    }
}
```

In the example, `reader` and `writer` are application components that illustrate reading/writing one page. When each `execute` call completes:

1. The tasklet reads the next page based on `nextPage`.
2. The tasklet writes that page.
3. The tasklet updates `nextPage` in the `ExecutionContext`.
4. The tasklet returns `CONTINUABLE`.
5. Spring Batch updates the context and step metadata and then commits the transaction.
6. The next iteration begins with a new transaction.

If `writer.writePage` and the `ExecutionContext` are saved in the same transaction resource, the page's data and the `nextPage` checkpoint can commit together. If an error occurs before the commit, both changes roll back; the next call will re-read the page that was not committed. When there is no more data, the tasklet returns `FINISHED` so the step ends.

This is a way to split work into multiple short transactions, but the tasklet is still a tasklet step. If the business needs to process each item with skip/retry, read/write statistics, and richer chunk semantics, a chunk-oriented step is usually more suitable.

## Comparing the transaction boundary of a Tasklet and a chunk step

Both tasklet steps and chunk-oriented steps use transactions, but the unit of work inside the transaction differs.

| Aspect | TaskletStep | Chunk-oriented step |
| --- | --- | --- |
| Execution unit | One call to `Tasklet.execute` | One chunk of items |
| Transaction boundary | Usually one transaction per execute call | One transaction per chunk |
| Repeated processing | The tasklet returns `CONTINUABLE` to request the next iteration | The framework repeats reader/process/writer per commit interval |
| Reader/processor/writer | The tasklet organizes the logic itself if needed | The framework orchestrates the three components |
| Checkpoint | The tasklet usually manages state itself in the `ExecutionContext` | Readers/writers can integrate `ItemStream` to save state |
| Suitable for | A single business operation or a self-defined unit of work | Processing a set of items with commit, skip, retry, and per-chunk statistics |

A tasklet that performs a large loop inside a single `execute` call still has only one transaction for that entire invocation. Writing a `for` or `while` in a tasklet does not by itself create a new transaction for each loop iteration. To get a separate transaction for each unit, you can return `CONTINUABLE` after each unit or use a chunk-oriented step.

## Transactions and the ExecutionContext

The `ExecutionContext` stores the state needed to recover a job or step. For a tasklet that processes over multiple iterations, this is a suitable place to store checkpoints such as the next page, the last processed ID, a file name, or the work state.

An example of getting and updating the context:

```java
ExecutionContext context =
        contribution.getStepExecution().getExecutionContext();

long lastProcessedId = context.getLong("lastProcessedId", 0L);

// Process a portion of data starting after lastProcessedId.

context.putLong("lastProcessedId", newLastProcessedId);
```

In `TaskletStep`, Spring Batch updates the execution context and the step metadata within the transaction's lifecycle. If the context and the business data participate in the same transaction manager/resource, the checkpoint can be committed together with the processed data.

Do not store a checkpoint only in a field of the tasklet object. A tasklet bean can be reused across runs or by multiple executions depending on the scope and the application configuration. State in a field is not durably saved by the repository and can be lost when the process stops. Use the `ExecutionContext` for state that is needed on restart; keep the tasklet stateless when possible.

### What happens on restart?

Suppose a tasklet processes 10 pages, each invocation processes one page and commits a checkpoint after each page. If the process stops after page 6 has been committed, the restart can read `nextPage=6` and continue from page 6 according to the example's index convention. Pages that have already been committed do not need to run again.

If the process stops before the page 6 transaction commits, both the page 6 data and the corresponding checkpoint roll back when they share the same resource; the restart will process page 6 again. Therefore, the checkpoint must be updated in the same transaction as the portion of data it represents.

If the writer writes to a system outside the transaction, the checkpoint and the output may be out of sync. For example, a file or message has been written but the database transaction rolls back. On restart, the tasklet may repeat the output. You need to design file append/restart, a message event ID, or an idempotent operation to avoid duplicate results.

## Transaction manager and multiple resources

A transaction manager usually manages one specific kind of transaction resource, such as a JDBC datasource or a JPA entity manager factory. Operations in a tasklet automatically participate in the current transaction only when they use the right resource and the configured transaction manager.

### The same database and the same transaction manager

If a tasklet updates a business table with a `JdbcTemplate` that uses the same `DataSource` as the step's transaction manager, the SQL statement participates in the current transaction. The step's metadata updates can also participate in the same transaction if the `JobRepository` is configured on the same resource and an appropriate transaction manager.

```text
TaskletStep transaction
          |
          +---- UPDATE business_table
          |
          +---- INSERT audit_table
          |
          +---- Update StepExecution / ExecutionContext
          |
          +---- COMMIT or ROLLBACK
```

This is the easiest configuration to understand when business data and checkpoints need to be consistent. However, you must confirm that the operations really use the same transaction resource; the same database server or the same JDBC URL but with independently opened connections does not automatically mean the same transaction.

### Two datasources or two transaction managers

If the metadata and the business data are in two databases, each transaction manager can commit independently. The tasklet's transaction does not automatically guarantee an atomic commit across the two resources.

For example:

```text
Business DB transaction       Metadata DB transaction
         |                              |
         v                              v
   Write business data          Write checkpoint
         |                              |
      COMMIT                          ROLLBACK
         |                              |
         +---------- restart -----------+
                    |
                    v
            Data may be written again
```

If the business data commits but the checkpoint rolls back, the tasklet may redo the portion of work that was already written. If the checkpoint commits before the business data, the tasklet may skip a portion of work that was not saved. When the resources are separated, you need a recovery strategy:

- Design write operations to be idempotent by business key.
- Record the processing state in the business system for reconciliation.
- Use an outbox when the tasklet needs to emit messages based on database changes.
- Determine how to recover when one resource commits while another fails.
- Consider a distributed transaction/XA only when atomicity across multiple resources is truly required and the infrastructure supports it.

## @Transactional inside a Tasklet

A tasklet often calls business services annotated with `@Transactional`. You need to understand propagation to know whether the service participates in the step's transaction or opens an independent one.

With `Propagation.REQUIRED`, the service participates in the active transaction if there is one. This is usually the appropriate choice when the service updates data that needs to commit together with the tasklet invocation.

```java
@Service
public class OrderArchiveService {

    @Transactional
    public int archive(LocalDate cutoffDate) {
        // JDBC/JPA statements participate in the current transaction
        // if they use the same transaction manager and resource.
        return 0;
    }
}
```

With `Propagation.REQUIRES_NEW`, the service suspends the current transaction and opens an independent one. If the service commits successfully and then the tasklet fails, the changes in the new transaction can still persist. This can break the assumption that all changes within one tasklet invocation will roll back together.

`Propagation.NESTED` relies on savepoints and on the support of the transaction manager/database. Not every resource supports it in the same way.

In addition, `@Transactional` relies on Spring's proxy mechanism. Calling another transactional method in the same instance through self-invocation may not go through the proxy, and the annotation may not be applied as expected. Place the transaction boundary on a bean/service that is called through the proxy, and confirm that the correct transaction manager is selected when the application has multiple datasources.

Normally, you do not need to wrap the entire `Tasklet.execute` in an additional `@Transactional` because `TaskletStep` already manages the transaction. Use transactions on child services when there is a clear reason related to propagation or business boundaries.

## Rollback when a tasklet fails

When an operation in a tasklet fails, the outcome depends on the exception type, the transaction attribute, and the resources participating in the transaction.

In `TaskletStep`, the default transaction attribute is designed to roll back when the tasklet throws an exception. If the application configures a custom transaction attribute, you need to clearly determine which exceptions trigger a rollback. For database resources participating in the transaction, uncommitted changes will roll back.

An example of a tasklet performing two operations:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    jdbcTemplate.update(
            "UPDATE account SET status = 'CLOSED' WHERE account_id = ?",
            accountId);

    jdbcTemplate.update(
            "INSERT INTO account_audit(account_id, action) VALUES (?, ?)",
            accountId,
            "CLOSED");

    return RepeatStatus.FINISHED;
}
```

If the audit insert statement throws an exception and both operations participate in the same transaction, the account update statement is rolled back as well. If the tasklet has already sent an email or made an HTTP call before the error occurred, that external operation is not automatically revoked.

### Checked exceptions and rollback rules

A tasklet can declare `throws Exception`. When you need to change the rollback rule, configure the step's transaction attribute using the API of the Spring Batch version in use. Do not assume that every exception in every service has the same rollback behavior: the `@Transactional` annotation on a service and the transaction attribute of `TaskletStep` are two configuration layers that can interact.

If a service uses `@Transactional` with its own rollback rule, for example `noRollbackFor`, the service may not mark the transaction rollback-only for a certain exception. However, `TaskletStep` still has its own transaction attribute when deciding how to handle an exception from `execute`. Check both layers when you see unexpected commit/rollback behavior.

## Transaction timeout and isolation level

A tasklet's transaction can be configured with a timeout and isolation appropriate to the work. A tasklet that runs for a long time in one invocation holds the transaction for a correspondingly long time, so the timeout needs to reflect the actual duration but should not be set so large that it hides a hung operation.

Factors that commonly need consideration:

| Attribute | Meaning | When to care |
| --- | --- | --- |
| Propagation | Join the current transaction or create a new one | The tasklet calls a service with `@Transactional` |
| Isolation | The transaction's read/write isolation level | The tasklet reads and updates contended data |
| Timeout | The maximum time for the transaction | The tasklet has long database operations or waits for locks |
| Read-only | A hint for a read-only transaction if the manager supports it | The tasklet only queries and does not change data |
| Rollback rule | Which exceptions cause the transaction to roll back | The tasklet has checked exceptions or its own business rules |

TaskletStep supports configuring a transaction attribute. How a `TransactionAttribute` is attached to the step builder can differ between versions. When changing isolation or timeout, consider the database load, locks, query plans, and execution time; do not raise isolation to the highest level unless there is a corresponding consistency requirement.

## Calling an API, writing a file, or sending a message in a tasklet

Not every operation inside `execute` is protected by the database transaction.

### Calling an HTTP API

If a tasklet calls an external API to create a resource or update a status, a database rollback cannot automatically undo a request that the API has already processed. If the tasklet fails after the API succeeds, a restart may resend the request. Use an idempotency key, or an API that supports status queries, to avoid creating repeated effects.

### Writing a file

Writing a file does not implicitly participate in a JDBC transaction. If a tasklet writes part of a file and then fails, a database rollback does not delete the bytes already written. Write to a temporary file named by the execution identifier, save a checkpoint when you need to continue, and only publish the file after the step completes successfully. If you need to append on restart, you must determine the exact position and the way to recover.

### Sending a message

A message broker has its own transaction and does not automatically participate in the tasklet's database transaction. A message that the broker has accepted can still exist when the database transaction rolls back. You can use a transactional outbox to write the event in the same business transaction and then have a separate publisher send the message; consumers should process idempotently by event ID.

## Designing a long tasklet: splitting commit units

A tasklet that does all its work in one `execute` call can hold a transaction for too long. If you can split the work into independent units, process one unit per call and return `CONTINUABLE`.

Examples of ways to split:

- One database page per call.
- One file or one part of a file per call.
- One group of customers or one ID range per call.
- One partition or one sub-batch by business key.

Each unit should have a corresponding checkpoint. Only update the checkpoint after the unit's changes have been performed successfully in the transaction. When the tasklet returns `CONTINUABLE`, the framework commits the current transaction and then starts a transaction for the next unit.

Do not write your own loop over millions of items in a single `execute` if the requirement is periodic commits. In that case, a chunk-oriented step with `ItemReader`, `ItemProcessor`, and `ItemWriter` usually provides a more natural model, including a commit interval, skip/retry, and per-item statistics.

## Listeners and the transaction boundary

A tasklet step can use `StepExecutionListener`, `ChunkListener`, or another appropriate listener depending on need. You need to distinguish listener callbacks from the portion of work that lies within the tasklet's transaction. Do not assume that every callback runs in the same transaction as `execute`.

If a listener writes data that needs to commit atomically with the tasklet, determine the actual lifecycle and transaction manager of that callback. For important business operations, it is usually easier to control if they are done in the tasklet/service that participates in the step's transaction instead of relying on a side effect in a listener at an unclear point in time.

Listeners are suitable for logging, measuring time, adding metadata, or orchestrating tasks before/after a step. If a listener sends notifications externally, note that messages or emails do not roll back together with the database transaction.

## Common mistakes

### Thinking the whole step lifecycle has only one transaction

`TaskletStep` creates a transaction for each `execute` call. If the tasklet returns `CONTINUABLE`, the next iteration has a new transaction. Earlier operations that have already committed do not roll back when a later iteration fails.

### Using a large loop in a single execute

A long loop inside `execute` still holds one transaction for the entire invocation. This can hold locks and connections for a long time and enlarge the rollback scope. Split into multiple invocations with checkpoints, or move to a chunk step.

### Updating the checkpoint before the data

If the checkpoint commits before the business data is written, a restart may skip incomplete data. Update the context in the same transaction as the change the checkpoint represents when possible.

### Storing progress in a tasklet field

A field in an object is not durable metadata. When the process stops or the bean is reused, the state can be lost or mixed between executions. Store the checkpoint in the `ExecutionContext`.

### Unintentionally calling a service that uses REQUIRES_NEW

A service can commit independently of the tasklet transaction. When the tasklet rolls back, the data the service has committed still persists. Check the service's propagation and transaction manager.

### Assuming files or messages roll back together with the database

Files and message brokers are usually independent resources. Use temporary files, an outbox, event IDs, and idempotency to recover when resources do not commit together.

### Swallowing an exception and returning FINISHED

If a tasklet catches an exception, only logs it, and returns `FINISHED`, the framework may consider the invocation to have completed normally and commit the remaining changes. Only handle an exception when there is a clear recovery policy; if the tasklet cannot complete correctly, throw the exception so the step handles the failure.

## Testing the Tasklet's transaction boundary

You should test the success, rollback, multiple-iteration, and restart cases.

### Testing a successful commit

Run the tasklet against a test database and confirm that the business changes and the step metadata are written after the step completes. Check `BatchStatus.COMPLETED` and the data results.

### Testing rollback

Have the tasklet perform a database update and then throw an exception. Confirm that the uncommitted update is rolled back when using the same transaction resource. Check that the step is in a failed state and the metadata reflects the error.

### Testing CONTINUABLE

Create a tasklet that processes one unit per call, advances the checkpoint in the `ExecutionContext`, and returns `CONTINUABLE` until the data runs out. Confirm that each unit is committed separately and that the next call can read the saved checkpoint.

### Testing restart

Simulate a failure after some invocations have committed. Restart the same `JobInstance` with the old identifying parameters and confirm that the tasklet continues from the saved checkpoint, and does not reprocess the units that have already committed if the design requires that.

### Testing side effects outside the transaction

Simulate an API or publisher that has accepted a request and then have the tasklet throw an exception. Confirm that a database rollback does not automatically revoke the side effect, and check how the idempotency key or outbox handles the re-run.

## Principles for choosing the transaction boundary

When designing a tasklet, answer the following questions:

1. How much work does one `execute` call do and how long does it take?
2. Which operations need to commit or roll back together?
3. Does the tasklet return `CONTINUABLE` to split into multiple transactions?
4. Which checkpoint needs to be stored in the `ExecutionContext` for restart?
5. Do the business data and the metadata use the same transaction resource?
6. Does the tasklet call an API, write a file, or send a message outside the transaction?
7. Does the called service use `REQUIRED` propagation, `REQUIRES_NEW`, or a different transaction manager?
8. Are the timeout, isolation, and rollback rule appropriate to the work?
9. Can you switch to a chunk-oriented step if you need to process many items, skip/retry, and commit in batches?

For short operations that need atomicity, a single `execute` call returning `FINISHED` is usually enough. For long work, split it into small units, store a checkpoint in the `ExecutionContext`, and return `CONTINUABLE` so each unit has its own transaction. When a tasklet works with multiple resources, you must design for recoverability and idempotency because a database transaction does not cover files, APIs, or message brokers.

## Key takeaways

`TaskletStep` manages a transaction for each call to `Tasklet.execute`. A tasklet returns `FINISHED` to end the step; it returns `CONTINUABLE` to request the next call in a new transaction. Database and metadata changes only commit/roll back together when they participate in the same transaction resource and an appropriate transaction manager. Use the `ExecutionContext` to store durable checkpoints, and avoid keeping state in fields or holding a transaction too long. For files, APIs, and message brokers, you need idempotency, an outbox, or dedicated recovery mechanisms because side effects outside the database do not automatically roll back together with the tasklet transaction.
