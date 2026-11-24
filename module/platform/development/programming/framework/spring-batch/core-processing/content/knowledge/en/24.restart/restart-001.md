# What is a restartable job?

In Spring Batch, a **restartable Job** is a Job that can resume a failed or stopped unit of work from a saved state, instead of having to restart processing all data from the beginning. Spring Batch uses `JobRepository` to store execution metadata, and `ExecutionContext` to store checkpoints and Reader/Step state to determine the remaining work to resume.

Restart does not mean creating a new JobInstance. When restarting, the application typically uses the same Job name and the same identifying `JobParameters` to identify the previous JobInstance again. Spring Batch creates a new `JobExecution` for the next attempt, preserves the history of the previous run, and applies the restart policy of the Job and its Steps.

Restartability is a property that must be designed into the Job, Reader, Writer, and transaction boundaries. Simply calling `JobLauncher.run()` again does not automatically guarantee that data will resume at the right position or avoid duplicate writes.

## 1. What problem does a restartable job solve?

A batch job can process thousands or millions of records and run for a long time. If the application or database encounters an error near the end, re-running everything from the beginning can be time-consuming and produce duplicate side effects.

For example, a Job importing a file of 100,000 orders with a commit interval of 1,000:

```text
importOrdersJob
  |
  +--> Chunk 1: COMMITTED (1.000 orders)
  +--> Chunk 2: COMMITTED (1.000 orders)
  +--> ...
  +--> Chunk 70: COMMITTED
  +--> Chunk 71: FAILED / ROLLED BACK
  +--> Remaining chunks have not run yet
```

If the Job supports restart and the Reader saves checkpoints, the next run can resume from the most recently committed boundary. Already-committed chunks are preserved; the failed chunk is reprocessed according to the saved state.

Without durable metadata or a stateful Reader, the application might have to read from the beginning again. In that case, the Writer must tolerate repeated processing without creating duplicate data.

## 2. JobInstance and JobExecution on restart

Spring Batch distinguishes between the logical unit of work and individual execution attempts:

- `JobInstance`: a unit of work identified by the Job name and identifying JobParameters.
- `JobExecution`: a specific execution attempt of a JobInstance.
- `StepExecution`: a specific execution attempt of a Step within a JobExecution.

When a JobInstance fails and is restarted, the JobInstance remains the same, but a new JobExecution is created:

```text
Job: importOrdersJob
Identifying parameters: fileId=orders-2026-11-15
       |
       v
JobInstance #50
       |
       +--> JobExecution #101: FAILED
       |       importStep: FAILED
       |
       +--> JobExecution #108: COMPLETED
               importStep: resumes from checkpoint
```

Previous JobExecution history is not overwritten. This helps operators see which attempt failed, which attempt restarted, and the final outcome of each execution.

### Identifying JobParameters determine restarting the right instance

For example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("fileId", "orders-2026-11-15", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

`fileId` is an identifying parameter, whereas `requestedBy` does not participate in identification. When restarting, you must use the same identifying parameters to point to the same JobInstance. If you change `fileId` or add a new identifying UUID, Spring Batch may create a new JobInstance instead of restarting the old instance.

Do not add a new timestamp or UUID to identifying parameters on every retry just to avoid duplicate-launch errors. Doing so turns the invocation into a new job instance and can cause all data to be reprocessed.

## 3. State conditions for restarting

Restartability depends on the previous JobExecution status and the Job configuration.

| Previous status | Typical behavior when relaunching with the same identifying parameters |
|---|---|
| Never run | Creates a new JobInstance and JobExecution. |
| `STARTED` or currently running | Rejects duplicate launch, typically with `JobExecutionAlreadyRunningException`. |
| `FAILED` | Can create a new JobExecution to restart if the Job allows it. |
| `STOPPED` | Can restart if the status and configuration allow it. |
| `COMPLETED` | Does not restart the same JobInstance; typically receives `JobInstanceAlreadyCompleteException`. |
| `ABANDONED` | Does not resume via normal restart. |
| `UNKNOWN` | Requires investigating metadata and actual state before deciding. |

Restart is primarily intended to resume unfinished work. If a Job is already `COMPLETED` and business requirements call for reprocessing the data, you must create a new JobInstance using a business-meaningful identifying parameter such as `reprocessVersion` or `correctionBatchId`.

## 4. How does JobRepository store restart information?

`JobRepository` manages metadata for JobInstance, JobExecution, StepExecution, and ExecutionContext. In a typical database configuration, the default metadata tables include:

| Table | Role |
|---|---|
| `BATCH_JOB_INSTANCE` | Stores JobInstance identity. |
| `BATCH_JOB_EXECUTION` | Stores execution attempts of a JobInstance and their status. |
| `BATCH_JOB_EXECUTION_PARAMS` | Stores JobParameters for each execution. |
| `BATCH_STEP_EXECUTION` | Stores status, timestamps, and counters for StepExecution. |
| `BATCH_JOB_EXECUTION_CONTEXT` | Stores Job ExecutionContext. |
| `BATCH_STEP_EXECUTION_CONTEXT` | Stores Step ExecutionContext. |

Because metadata is stored durably, execution history can survive application stops and restarts. If an in-memory repository is used, metadata can be lost when the process terminates; therefore, that configuration is unsuitable when restart across application restarts is required.

JobRepository stores execution metadata, not business data tables. Order, customer, or import result data still need to be stored in the appropriate application tables.

## 5. ExecutionContext and checkpoints

`ExecutionContext` is a key-value store attached to a JobExecution or StepExecution. Readers and `ItemStream` components can use the context to store state needed for restarting.

For example, `FlatFileItemReader` stores the line position already read:

```java
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.core.io.FileSystemResource;

FlatFileItemReader<Order> orderReader =
        new FlatFileItemReaderBuilder<Order>()
                .name("orderFileReader")
                .resource(new FileSystemResource("data/orders.csv"))
                .delimited()
                .names("id", "customerId", "amount")
                .targetType(Order.class)
                .saveState(true)
                .build();
```

`saveState(true)` allows the Reader to persist state to ExecutionContext. When a Step commits a chunk, Spring Batch invokes the state-update mechanism on `ItemStream` components to save the checkpoint in alignment with the transaction.

On restart, the Reader can reopen the source and restore the reading position from the context. Keep the Reader name stable across runs because this name is typically used to namespace keys in ExecutionContext.

### Job ExecutionContext and Step ExecutionContext

Two commonly used scopes:

- **Step ExecutionContext:** stores checkpoints or state specific to a single Step, such as the read position in a file.
- **Job ExecutionContext:** stores small pieces of information that need to be shared across multiple Steps within the same JobExecution, such as a batch ID or input validation results.

Do not store entire file contents or large business payloads in ExecutionContext. Store only checkpoints, keys, or small metadata; primary data belongs in an appropriate database or file storage.

## 6. Readers must support restart

Not every `ItemReader` automatically supports position recovery. A Reader that wants to participate in checkpointing must implement `ItemStream` or be wrapped by an appropriate state-managing component.

Spring Batch built-in readers such as `FlatFileItemReader`, `JdbcCursorItemReader`, and `JdbcPagingItemReader` can save state when configured appropriately. Custom readers should implement the `open`, `update`, and `close` methods of `ItemStream` to manage state.

A general example of a reader that manages its own index:

```java
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamReader;

public class RestartableListReader implements ItemStreamReader<String> {

    private static final String CURRENT_INDEX = "current.index";

    private final List<String> items;
    private int index;

    public RestartableListReader(List<String> items) {
        this.items = items;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        this.index = executionContext.containsKey(CURRENT_INDEX)
                ? executionContext.getInt(CURRENT_INDEX)
                : 0;
    }

    @Override
    public String read() {
        if (index >= items.size()) {
            return null;
        }
        return items.get(index++);
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putInt(CURRENT_INDEX, index);
    }

    @Override
    public void close() {
        // Release resources if the reader uses any.
    }
}
```

The example above illustrates how to save and restore an index; in a real application, the `items` source must remain stable between the initial run and the restart. If the list changes or item ordering changes, the same index may point to a different record. With a database, use a stable sort key and a deterministic query order.

## 7. Writers must be safe when items are reprocessed

Checkpoints cannot guarantee that every side effect occurs only once. If an item was already sent to an external system but the chunk rolled back before the checkpoint committed, a restart can send that item again.

Therefore, Writers must be designed to be idempotent:

- Use a unique constraint on the business key.
- Use upsert or `MERGE` with deterministic update rules.
- Use an idempotency key when calling external APIs.
- Write messages to a transactional outbox in the same transaction as business data.
- Avoid blind increments or inserts without a deduplication key on retry.

For example, if a Job imports orders, the unique key could be `(source_system, source_order_id)`. When the same order is written again after a restart, it will update or be recognized as already existing according to policy, rather than inserting a duplicate row.

Restartability and idempotency complement each other: checkpoints reduce the amount of work that has to be redone; idempotency protects data if part of the work still has to run again.

## 8. Configuring a restartable Job

Jobs in Spring Batch are restartable by default unless configured to prevent restarting. A Step and Job can be configured as follows:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportJobConfig {

    @Bean
    public Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<Order> reader,
            ItemProcessor<Order, ProcessedOrder> processor,
            ItemWriter<ProcessedOrder> writer) {

        return new StepBuilder("importStep", jobRepository)
                .<Order, ProcessedOrder>chunk(500, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .build();
    }

    @Bean
    public Job importOrdersJob(
            JobRepository jobRepository,
            Step importStep) {

        return new JobBuilder("importOrdersJob", jobRepository)
                .start(importStep)
                .build();
    }
}
```

`.preventRestart()` is not called in the configuration above, so the Job retains the default restart policy. The Reader must support state if you want to restore the reading position; the Writer must be designed to handle data reprocessing safely.

### Preventing Job restart with preventRestart()

If a Job cannot be safely re-run, you can declare:

```java
return new JobBuilder("oneTimeJob", jobRepository)
        .preventRestart()
        .start(oneTimeStep)
        .build();
```

Once the Job has a failed run, any restart request will be rejected with `JobRestartException`. Use this option only when business rules strictly prohibit restarting. If it is possible to make the Reader/Writer idempotent and save checkpoints, it is generally better to retain recoverability.

## 9. Step allowStartIfComplete and startLimit

A restartable Job does not mean every Step runs again. During a restart, Steps that are already `COMPLETED` are normally skipped. Two Step options affect this behavior:

### allowStartIfComplete(true)

By default, a completed Step is skipped when a Job restarts. You can configure `allowStartIfComplete(true)` if you want that Step to run again on restart:

```java
return new StepBuilder("refreshReferenceDataStep", jobRepository)
        .tasklet(refreshReferenceDataTasklet, transactionManager)
        .allowStartIfComplete(true)
        .build();
```

Enable this only when the operation is safe if executed multiple times. For example, refreshing a reference table with upsert may be appropriate; sending emails, charging payments, or emitting notifications without idempotency can produce duplicate side effects.

### startLimit(n)

`startLimit(n)` limits how many times a Step is allowed to start:

```java
return new StepBuilder("fragileStep", jobRepository)
        .tasklet(fragileTasklet, transactionManager)
        .startLimit(3)
        .build();
```

When the limit is exceeded, Spring Batch refuses to start the Step again. `startLimit` is not the retry count for an individual item; it limits how many times a StepExecution can be started according to the Step policy. Use it for tasks with explicit operational limits, not as a substitute for an item retry policy.

## 10. Restarting via JobLauncher

To restart a failed Job, you can call `JobLauncher.run()` with the same Job and identifying JobParameters. Spring Batch looks up the corresponding JobInstance and creates a new JobExecution if the status and configuration permit it.

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("fileId", "orders-2026-11-15", true)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importOrdersJob, parameters);
```

If the previous run failed, a subsequent call with the same identifying parameters can restart that instance. If the previous run was `COMPLETED`, the call is typically rejected with `JobInstanceAlreadyCompleteException`. If an execution is currently running, a duplicate call is typically rejected with `JobExecutionAlreadyRunningException`.

Do not add a new identifying parameter just to force the Job to run again. If you want a new processing run, use a business-meaningful correction code or version and understand that it represents a new JobInstance.

## 11. Restarting via JobOperator

`JobOperator` provides an operational API to restart a JobExecution by ID:

```java
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class JobRestartService {

    private final JobOperator jobOperator;

    public JobRestartService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public Long restart(long failedExecutionId) throws Exception {
        return jobOperator.restart(failedExecutionId);
    }
}
```

`failedExecutionId` is the ID of the JobExecution to restart. You must verify that this is the execution of the right JobInstance and that its status is restartable. In operational applications, you should restrict restart permissions, audit who requested it, and verify that input data has been fixed if the root cause of failure still exists.

## 12. Transaction boundaries make restart reliable

Chunk Steps typically commit transactions per chunk. When a chunk fails, that chunk's transaction rolls back; previously committed chunks are preserved. This is a critical recovery boundary for restarting.

```text
JobExecution #1: FAILED
  Chunk 1: COMMITTED
  Chunk 2: COMMITTED
  Chunk 3: ROLLED BACK
  Chunk 4: not run yet

Restart the same JobInstance
  |
  v
JobExecution #2
  Restore checkpoint after Chunk 2
  Continue processing Chunk 3
```

Do not wrap the entire Job in a single outer transaction. If all chunks participate in an outer transaction, intended chunk commits may not become independent commits; a failure near the end of the Job could roll back a massive amount of data and break restart expectations.

For a Tasklet, the transaction is managed per `execute()` call. If a Tasklet performs a file move or calls an API, non-database side effects do not roll back automatically. You must design state checks before re-executing.

## 13. Readers and data sources must remain stable

A checkpoint is only meaningful if the same position still points to the same slice of data on restart. Some risks include:

- The source file is replaced after the initial run.
- Database data changes order because the query lacks a stable `ORDER BY`.
- A paging query uses offsets while new records are inserted/deleted, shifting page boundaries.
- A partition plan is recomputed with different ranges.
- A custom Reader does not save state properly after commit.

To ensure reliable restarts:

1. Use immutable files or store a checksum/version of the input file.
2. Use queries with deterministic ordering based on a unique key.
3. For mutable data, use snapshots, watermarks, or a data cutoff timestamp.
4. Store stable partition range information in ExecutionContext.
5. Keep reader names and ExecutionContext structures compatible across runs.

If the source data changes without a snapshot, a restart may miss or double-read items even when the checkpoint is accurately restored to the old position.

## 14. Restart and skip/retry

Restart, retry, and skip are three distinct mechanisms:

- **Retry:** retries a failing operation within the same execution according to the retry policy.
- **Skip:** skips an item when the exception is skippable and the skip limit has not been exceeded.
- **Restart:** creates a new JobExecution for an unfinished JobInstance and resumes from saved metadata/checkpoints.

On restart:

- Items in already-committed chunks are generally not re-read if the Reader restores its checkpoint properly.
- Items in rolled-back chunks may be read and processed again.
- Items skipped in already-committed chunks are usually before the checkpoint and will not be encountered again.
- Items skipped in a rolled-back chunk may be skipped again when the chunk is re-executed.

Therefore, reject listeners or error-recording operations must be idempotent. If a skip limit needs to accumulate across multiple JobExecutions, store a separate business counter rather than relying solely on the skip count of a single execution.

## 15. Testing restartability

A Job should only be considered restartable after verifying both metadata and business data after a restart.

Useful test scenario:

1. Prepare fixed input data and identifying JobParameters.
2. Run the Job the first time and trigger a controlled failure after a few committed chunks.
3. Verify that the first JobExecution is `FAILED`, earlier chunks committed, and the checkpoint was saved.
4. Fix the failure condition or dependency so the Job can proceed.
5. Restart the same JobInstance using the same identifying JobParameters.
6. Verify that the new JobExecution has a different ID while the JobInstance ID matches the first run.
7. Verify that the Reader resumes from the checkpoint, the Writer creates no duplicate data, and the Job finishes in the expected state.
8. Verify that non-database side effects such as files, messages, or API calls are not unintentionally duplicated.

With Spring Batch Test, `JobLauncherTestUtils` supports launching Jobs/Steps; `JobExplorer` or `JobRepository` can query JobExecution and StepExecution history. Tests should use the same identifying parameters between the initial run and the restart. Adding a new identifying UUID will create a new JobInstance in the test and stop testing restart.

## 16. Common pitfalls

| Pitfall | Consequence | Resolution |
|---|---|---|
| Confusing restart with launching a new JobInstance | Reprocesses all data as a separate unit of work. | Keep identifying JobParameters unchanged when restarting. |
| Reader does not save state | Restart may read from the beginning or fail to restore position. | Use a Reader supporting ItemStream and enable state saving. |
| Data source changes between runs | Checkpoint may point to different data, causing lost or duplicate items. | Use immutable files, snapshots, or watermarks. |
| Non-idempotent Writer | Retried items can create duplicate records or side effects. | Use unique constraints, upserts, idempotency keys, or outbox. |
| Unintended use of `preventRestart()` | A failed Job cannot resume the same JobInstance. | Configure only when business rules strictly forbid restarting. |
| Enabling `allowStartIfComplete(true)` on a Step with side effects | Completed Steps may re-run and repeat/amplify side effects. | Ensure the Step is idempotent before enabling it. |
| Confusing `startLimit` with retry limit | Limits how many times a Step can start rather than item retries. | Use a retry policy for items; use startLimit for Step start attempts. |
| Using an in-memory repository for restarts across process restarts | Metadata can be lost when the application stops. | Use a durable database-backed JobRepository. |
| Wrapping the entire Job in one transaction | Chunks cannot commit independently and rollbacks are overly broad. | Place transaction boundaries at the Step/chunk level. |

## Conclusion

A restartable Job is a Job that can resume an unfinished JobInstance by creating a new JobExecution and using saved metadata/checkpoints. This capability relies on a durable JobRepository, stable identifying JobParameters, state-saving Readers, Step/chunk-level transaction boundaries, and a Writer capable of handling repeated processing safely. `preventRestart()`, `allowStartIfComplete(true)`, and `startLimit()` tune restart policies at the Job or Step level. Test by intentionally failing a Job mid-run and restarting the same JobInstance, while verifying that output data and side effects are neither lost nor duplicated.
