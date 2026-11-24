# Tasklet idempotency on restart

In Spring Batch, a `Tasklet` performs a piece of work on each call to `execute()`. The work may be deleting old data, generating a report, closing an accounting period, calling an external service, or processing a data set. When a Job fails and is restarted, the Step containing the Tasklet may be executed again. If the Tasklet creates side effects on every run without checking the previous state, the system may delete data by mistake, create duplicate reports, send multiple notifications, or perform a business operation twice.

**Idempotency** allows an operation to be performed repeatedly with the same business identifier while the final result remains correct and no unintended extra effects are created. For a Tasklet, you need to design idempotency together with the transaction, checkpoint, JobParameters, and the external systems the Tasklet interacts with.

## 1. Why does a Tasklet need idempotency on restart?

A Tasklet is usually used for a work step with a clear nature, such as creating a summary table for a business day:

```text
Job: dailySettlementJob
    |
    +--> Tasklet: prepareSettlement
    |
    +--> Step: calculateTransactions
    |
    +--> Tasklet: publishSettlementReport
```

Suppose `prepareSettlement` creates a settlement-period record. The Tasklet succeeds, but the later Step fails. When the Job is restarted, Spring Batch normally skips a Step that is `COMPLETED` and continues from the Step that has not completed. However, if a Tasklet Step fails after it has already created a side effect, or is configured to run again after completion, the Tasklet may be called once more.

An example of a non-idempotent Tasklet:

```java
public class CreateReportTasklet implements Tasklet {

    private final ReportService reportService;

    public CreateReportTasklet(ReportService reportService) {
        this.reportService = reportService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        reportService.createNewReport();
        return RepeatStatus.FINISHED;
    }
}
```

Each time `execute()` is called, the service may create a new report. If the same business job is executed again, the result may be multiple identical reports.

An idempotent Tasklet needs to recognize the logical job it is processing and determine whether the corresponding side effect has already been performed. This identifier should be stable across restarts.

## 2. Distinguishing Tasklet invocation, Step execution, and Job restart

There are three levels to distinguish:

- **Tasklet invocation:** a single call to `Tasklet.execute()`. If the Tasklet returns `RepeatStatus.CONTINUABLE`, the framework may call `execute()` again within the same StepExecution.
- **StepExecution:** a specific execution of a Step. If the Step fails and the Job is restarted, the framework may create a new StepExecution for the re-run.
- **JobInstance:** represents the logical business job, identified by the Job name and identifying JobParameters. A JobInstance may have multiple JobExecutions across restarts.

In a `TaskletStep`, each Tasklet call is performed within the Step's transaction. When the Tasklet returns `CONTINUABLE`, the framework repeats the call; each iteration has its own transaction boundary. When the Tasklet returns `FINISHED`, the Step ends successfully if there is no other error.

```text
JobInstance: closeBusinessDay(businessDate=2026-11-15)
    |
    +-- JobExecution #101
          |
          +-- StepExecution #201
                |
                +-- execute() -> CONTINUABLE -> transaction commit
                +-- execute() -> CONTINUABLE -> transaction commit
                +-- execute() -> exception    -> transaction rollback

Restart the same JobInstance
    |
    +-- JobExecution #108
          |
          +-- New StepExecution
                +-- Tasklet is called again according to metadata/checkpoint
```

For a Tasklet that runs only once and returns `FINISHED`, if the call fails before the Step completes, a restart may call the entire logic again from the beginning. For a Tasklet that processes multiple parts and returns `CONTINUABLE`, a checkpoint can help continue from the part that has been committed.

## 3. The idempotency key must represent the business job

A common way to prevent duplicate execution is to create a stable *idempotency key* for the operation. The key should be based on a business key, for example the settlement date, customer code, data source code, or business type.

For example:

```text
operationKey = "settlement:2026-11-15"
```

If the Tasklet restarts for the same settlement period, the key stays the same. If the business period changes, the key will be different.

Do not use `JobExecution.getId()` as the idempotency key for a business operation that must prevent duplicates across restarts. Each restart creates a new JobExecution, so the execution ID changes. You can use the `JobInstance` ID if the key only needs to be stable within one JobInstance, or better, build the key directly from normalized business parameters so it still has meaning when the system recreates the metadata.

An example of reading parameters and creating the key:

```java
JobParameters parameters = contribution.getStepExecution().getJobParameters();
String businessDate = parameters.getString("businessDate");

if (businessDate == null || businessDate.isBlank()) {
    throw new IllegalArgumentException("businessDate is required");
}

String operationKey = "settlement:" + businessDate.trim();
```

Parameters that identify the same job must be normalized before the key is created. If one call uses `2026-11-15` and another uses `2026/11/15`, the two strings can create two different keys even though they represent the same business date.

## 4. Protecting database operations with a unique key and a transaction

If the Tasklet updates data in the same database and with the same transaction manager as the Step, you can use a table that records operations that have been performed. A unique key prevents two runs of the same job from creating two identical markers.

An example schema:

```sql
CREATE TABLE completed_batch_operation (
    operation_key VARCHAR(200) PRIMARY KEY,
    completed_at TIMESTAMP NOT NULL
);
```

The Tasklet uses an insert operation with conflict handling so it only performs the business operation when the key does not yet exist. The following example uses PostgreSQL syntax:

```java
public class CloseBusinessDayTasklet implements Tasklet {

    private final JdbcTemplate jdbcTemplate;

    public CloseBusinessDayTasklet(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String businessDate = contribution.getStepExecution()
                .getJobParameters()
                .getString("businessDate");

        if (businessDate == null || businessDate.isBlank()) {
            throw new IllegalArgumentException("businessDate is required");
        }

        String operationKey = "close-business-day:" + businessDate.trim();

        int inserted = jdbcTemplate.update("""
                INSERT INTO completed_batch_operation(operation_key, completed_at)
                VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT (operation_key) DO NOTHING
                """, operationKey);

        if (inserted == 0) {
            // This job was already committed in a previous execution.
            return RepeatStatus.FINISHED;
        }

        jdbcTemplate.update("""
                UPDATE daily_account
                SET closed = TRUE
                WHERE business_date = ?
                """, businessDate);

        return RepeatStatus.FINISHED;
    }
}
```

The important point is that inserting the marker and updating the business data must be in the same transaction. If the business update fails, the transaction rolls back both the marker and the business change; a restart can retry. If the transaction commits, the marker and the business change both exist; the next call sees the conflict and ends without repeating the side effect.

The example uses PostgreSQL `ON CONFLICT`. For other databases, use the corresponding upsert syntax or insert-if-absent mechanism. A real unique constraint in the database is required; merely checking with a `SELECT` before inserting is not enough to prevent two concurrent executions from both passing the check.

Make sure the `JdbcTemplate` uses a `DataSource` that belongs to the Step's transaction manager. If the marker and the business data use two different transaction managers, the atomicity described above is no longer guaranteed.

## 5. Updating by state instead of creating anew each time

Some Tasklets do not need a separate marker and can be designed so the operation sets the final state in an idempotent way.

For example, instead of adding an adjustment amount each time the Tasklet runs:

```sql
UPDATE account
SET balance = balance + 100
WHERE account_id = ?;
```

you can record the adjustment under a unique business key:

```sql
CREATE TABLE account_adjustment (
    adjustment_key VARCHAR(200) PRIMARY KEY,
    account_id BIGINT NOT NULL,
    amount DECIMAL(18, 2) NOT NULL
);
```

The Tasklet only adds an adjustment if the key does not yet exist, and then computes or updates the balance from the set of recorded adjustments. Re-running with the same key does not create a second adjustment.

An operation like `SET status = 'CLOSED'` is usually easier to make idempotent than an operation like `SET balance = balance + 100`, but you still need to consider the accompanying side effects and business rules. If every status set emits an email or event again, those side effects can still be repeated.

## 6. A Tasklet that processes multiple parts with CONTINUABLE and a checkpoint

A Tasklet can process data page by page or in small batches. Each `execute()` call processes one part and then returns `RepeatStatus.CONTINUABLE` so the framework calls it again. When a part completes, the Tasklet stores a checkpoint in the Step `ExecutionContext`.

An example of processing records by increasing ID:

```java
public class ProcessOrdersTasklet implements Tasklet {

    private static final String LAST_ID_KEY = "processOrders.lastId";
    private static final int PAGE_SIZE = 200;

    private final OrderRepository orderRepository;
    private final OrderService orderService;

    public ProcessOrdersTasklet(
            OrderRepository orderRepository,
            OrderService orderService) {
        this.orderRepository = orderRepository;
        this.orderService = orderService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext context = contribution.getStepExecution()
                .getExecutionContext();
        long lastId = context.getLong(LAST_ID_KEY, 0L);

        List<Order> page = orderRepository.findNextPage(lastId, PAGE_SIZE);
        if (page.isEmpty()) {
            return RepeatStatus.FINISHED;
        }

        for (Order order : page) {
            orderService.processIdempotently(order);
        }

        long newLastId = page.get(page.size() - 1).getId();
        context.putLong(LAST_ID_KEY, newLastId);

        return RepeatStatus.CONTINUABLE;
    }
}
```

In the example:

1. On the first call, the context does not yet have `LAST_ID_KEY`, so the Tasklet starts from ID `0`.
2. The Tasklet fetches at most 200 records with an ID greater than the checkpoint.
3. The Tasklet processes the page, updates the checkpoint to the last ID, and returns `CONTINUABLE`.
4. Spring Batch completes the transaction of that call and then calls `execute()` again.
5. When there are no more records, the Tasklet returns `FINISHED`.

`TaskletStep` manages saving the ExecutionContext and the Step metadata at the transaction boundaries of the loop. If a call fails before commit, the checkpoint of that call is not considered complete. On restart, the Tasklet can read the most recent saved checkpoint.

However, if `orderService.processIdempotently()` writes to a system outside the transaction, some orders may have been processed before the error occurred. When the Tasklet re-runs the page, the service must still recognize each order by a stable idempotency key. A checkpoint does not replace idempotency for external side effects.

## 7. Transaction and the order of checkpoint updates

For a multi-part Tasklet, the important order is: process the data portion, update the checkpoint, and then let the call's transaction commit. When the business update and the ExecutionContext are saved in an appropriate shared transaction, they can be committed consistently.

```text
One execute() call
       |
       +--> Read the page after the old checkpoint
       |
       +--> Perform the business update
       |
       +--> Write the new checkpoint to the Step ExecutionContext
       |
       +--> Transaction commit
```

If an exception occurs before commit and both the business update and the metadata participate in the same transaction, they are rolled back together. If a business side effect lies outside the transaction, the side effect may already have happened while the checkpoint was not saved. A restart will reprocess that portion; therefore the side effect must be idempotent.

Do not update the checkpoint before the page has finished processing. If the checkpoint advances but the business processing fails, a restart may skip data that has not been processed. Conversely, if the business work completes but the checkpoint has not been saved, part of the data may be processed again; idempotency makes the repeated processing safe.

For data sources that change while running, you need a stable sort key and consistent query conditions. An increasing ID, a watermark, or a snapshot can help avoid missing/re-reading records when the next page is fetched after a commit.

## 8. External side effects: APIs, messages, and email

The Step's database transaction does not automatically revoke an HTTP request that an external service has already processed, a message that a broker has already accepted, or an email that has already been sent.

For example, a Tasklet calls a payment API:

```java
paymentClient.capture(
        paymentId,
        amount,
        "capture:" + paymentId
);
```

The target API needs to support idempotency keys and store results by key. When the Tasklet calls with the same `capture:<paymentId>` again, the API returns the existing result instead of capturing again. If the API has no such mechanism, the Tasklet cannot guarantee by itself that the payment operation happens only once by checking a variable in memory.

### The outbox pattern for messages

If a Tasklet both updates the database and needs to emit an event, it can write the event to an outbox table in the same transaction as the business data:

```text
Tasklet transaction
    |
    +--> Update the settlement status
    +--> Insert the event into the outbox with a stable eventId
    +--> Commit

Separate publisher
    |
    +--> Read unsent events
    +--> Publish the event
    +--> Mark as sent
```

The publisher may resend an event if the process stops after the broker accepts the message but before the outbox status is updated. Consumers should deduplicate by `eventId`. The outbox helps guarantee that the business data and the intent to emit the event are written atomically in the database; it does not by itself turn the whole system into exactly-once.

Email usually has no rollback mechanism. Instead of sending an email directly in the Tasklet and then marking it complete, you can write the email request into an outbox or a notification table in the same transaction. A separate worker sends it and records the result, using a key to prevent creating duplicate requests.

## 9. Creating files and publishing reports idempotently

A Tasklet that generates a report file may fail after writing part of the file. On restart, if the Tasklet appends data to the same file without checking the state, the file may contain duplicate lines.

A common strategy:

1. Create a temporary file path based on the business key, for example `settlement-2026-11-15.tmp`.
2. Each time it is recreated, delete and rebuild the temporary file, or resume using a writer with supported checkpoints.
3. Write completely, flush, and close the file.
4. Check the line count or checksum if the business requires it.
5. Rename/publish the temporary file as the official file after completion.
6. If the official file already exists for the same business key, determine whether it is a completed result or a state that needs reconciliation.

Renaming a file can be atomic within the same filesystem, but do not assume a rename is atomic between two filesystems or on object storage. With object storage, you can use a versioned object key or a manifest pointer to publish only the completed version.

## 10. Completed Steps and allowStartIfComplete

When the same JobInstance is restarted after an earlier Step has `COMPLETED`, Spring Batch by default does not run that completed Step again. This helps avoid repeating the side effects of a successful Step when a later Step fails.

If you configure the Step with `allowStartIfComplete(true)`, a completed Step can be run again in the restart. In that case, the Tasklet must be idempotent because it may perform the same business work again.

For example:

```java
@Bean
public Step publishReportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        PublishReportTasklet tasklet) {

    return new StepBuilder("publishReportStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

Only enable `allowStartIfComplete(true)` when the business requires the Step to be performed again in a restart. If the Step has completed and does not need to run again, leaving the default is usually more suitable. Even without enabling this option, the Tasklet still needs to be safe for the case where an error occurs after a side effect but before the Step metadata is confirmed complete.

## 11. Distinguishing JobParameters, ExecutionContext, and the idempotency key

| Component | Role | Example |
|---|---|---|
| Identifying JobParameters | Identify the JobInstance and the logical job | `businessDate=2026-11-15` |
| Step ExecutionContext | Store the Step's checkpoint/progress | `lastProcessedOrderId=4200` |
| Job ExecutionContext | Store state that needs to be shared between Steps | `reportLocation=...` |
| Idempotency key | Identify a specific side effect to prevent duplicate execution | `close-business-day:2026-11-15` |

An idempotency key can be created from JobParameters but must be defined according to the business. An ExecutionContext that stores progress does not replace a unique key in the database or an idempotency key supported by an external system.

Do not use `JobExecutionId` as a business key that is stable across restarts because the ID changes between executions. Do not use `StepExecutionId` as an anti-duplication key for the same reason.

## 12. Common design mistakes

**Using the current timestamp as the idempotency key.** Each restart may produce a different timestamp, causing the system to treat the same job as a new operation. Use a stable business key.

**Marking complete before performing the side effect.** If the marker is committed first but the business operation fails, a restart may see the marker and skip work that has not been completed. The marker and the business update need to be in the same transaction, or there needs to be a clear recovery state machine.

**Performing the side effect outside the transaction and only then saving the checkpoint.** If the side effect succeeds but the checkpoint has not committed, the operation will be called again. You need idempotency at the destination or an outbox.

**Treating the ExecutionContext as an exactly-once mechanism.** The context helps store a checkpoint; it does not revoke side effects outside the transaction and does not prevent two concurrent executions if there is no lock/constraint where the data is written.

**Catching an exception and returning `FINISHED`.** Spring Batch will consider the Tasklet to have completed normally, even though the work may have been done only partially. Let the exception propagate or record the failure state under a clear design.

**Using a mutable field as the checkpoint.** A field in an object is lost when the process restarts and may not match the committed progress. Use the Step ExecutionContext or a durable state store.

**Enabling `allowStartIfComplete(true)` without protecting side effects.** A successful Step can be run again on restart. Only enable it when needed and design the operation to be idempotent.

## 13. Testing Tasklet idempotency

Do not only check that the Tasklet runs successfully once. You need to check the behavior when the same job is invoked multiple times:

- Call the Tasklet twice with the same business key: only one business result is created.
- Cause an error after writing the marker or while updating data: the transaction rolls back correctly and a re-call can complete.
- Cause an error after a side effect outside the transaction but before the checkpoint is saved: the re-call does not create a duplicate side effect.
- Restart after a page has been committed: the Tasklet continues from the saved checkpoint.
- Invoke two executions with the same business key concurrently: a unique constraint or an idempotency service prevents duplicate processing.
- Restart with a different business key: the new job is performed independently.

A conceptual-level test example:

```java
@Test
void repeatedExecutionDoesNotCloseBusinessDayTwice() throws Exception {
    Tasklet tasklet = new CloseBusinessDayTasklet(jdbcTemplate);

    StepContribution contribution = contributionWithBusinessDate("2026-11-15");
    ChunkContext chunkContext = new ChunkContext(new StepContext(stepExecution));

    tasklet.execute(contribution, chunkContext);
    tasklet.execute(contribution, chunkContext);

    assertEquals(1, countCompletedOperations("close-business-day:2026-11-15"));
    assertEquals(1, countBusinessDayCloseEvents("2026-11-15"));
}
```

A real test should run with an appropriate database transaction and also simulate an exception partway through. With an API or broker, use a fake server or a test container to check the idempotency key and the number of side effects recorded.

## 14. How to design an idempotent Tasklet

Before writing the Tasklet, determine the operation's business key, where the completed state is stored, and which transaction covers the side effects. With a database in the same transaction, use a unique constraint and write the marker together with the business change in one transaction. For long work, process page by page, store a checkpoint after each completed part, and ensure each item can be safely processed repeatedly. For APIs/messages/email, use an idempotency key at the destination system or an outbox; for files, write to a temporary location and then publish the complete result.

A Tasklet should let errors that truly fail the execution propagate to Spring Batch, so the framework rolls back and records the metadata in the correct state. On restart, the same logical job must be recognized by a stable key and every side effect must be safe to retry. This is the foundation that lets a Tasklet recover after a failure without creating duplicate data or missing business operations.
