# A Tasklet performs a single task in a Step

In Spring Batch, `Tasklet` is the way to define a unit of work inside a `Step` when the logic can be described as one complete task. Examples include deleting temporary data, calling a stored procedure, checking or preparing a file, sending a request to another system, creating a summary record, or moving a processed file.

Unlike chunk-oriented processing, where a Step reads, processes, and writes many items chunk by chunk, a Tasklet focuses on performing a single task. Spring Batch calls the Tasklet's `execute()` method and relies on the `RepeatStatus` value to know whether the Step is finished or needs to continue.

## 1. What is a Tasklet?

`Tasklet` is a simple Spring Batch interface with this method:

```java
public interface Tasklet {
    RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception;
}
```

The `execute()` method receives two objects:

- **`StepContribution`:** represents the contribution of this Tasklet execution to the `StepExecution`. You can use it to access the `StepExecution`, update counters, or add an ExitStatus.
- **`ChunkContext`:** provides the context of the execution, including the `StepContext` and chunk-scoped context attributes. You can use it to access JobParameters, the StepExecutionContext, or other relevant context data.

The method returns a `RepeatStatus`:

- **`RepeatStatus.FINISHED`:** the Tasklet has completed its work; the Step does not need to call the Tasklet again.
- **`RepeatStatus.CONTINUABLE`:** the Tasklet asks Spring Batch to call `execute()` one more time.

If the task only needs to run once, it usually returns `FINISHED`. If the task is divided into several passes and each call processes only part of the work, it can return `CONTINUABLE` until it is complete.

## 2. How is a Tasklet executed in a Step?

A `Tasklet` is run by Spring Batch inside a `TaskletStep`. The Step manages the execution lifecycle, transactions, state, and metadata. The simple flow:

```text
Job starts
    |
    v
TaskletStep creates a StepExecution
    |
    v
Tasklet.execute(contribution, chunkContext)
    |
    v
Perform the task
    |
    v
Return a RepeatStatus
    |
    +---- FINISHED ------> Step completes
    |
    +---- CONTINUABLE ---> Call execute() again
```

For a typical Tasklet that returns `FINISHED`, `execute()` is called once for that Step execution. If it returns `CONTINUABLE`, Spring Batch continues the loop and calls the Tasklet again. You must ensure that each iteration makes clear progress; if it always returns `CONTINUABLE` without changing state or having a stop condition, the Step can run forever.

In a `TaskletStep`, each Tasklet call is performed within a transaction managed by the Step's transaction manager. For a Tasklet that repeats with `CONTINUABLE`, the calls are managed in the loop's own separate transactions. Therefore, you should clearly understand which work is committed on each call and which state must be saved so the work can resume after a failure.

## 3. Declaring a Tasklet with Java configuration

In Spring Batch 5, you can create a Step with `StepBuilder` and pass in the `JobRepository` together with a `PlatformTransactionManager`:

```java
@Bean
Step cleanupTemporaryDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CleanupTemporaryDataTasklet tasklet) {

    return new StepBuilder("cleanupTemporaryDataStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
```

`tasklet(tasklet, transactionManager)` tells the Step which Tasklet to use and which transaction manager manages the transaction of each Tasklet execution.

The Tasklet definition can be a separate bean:

```java
@Component
public class CleanupTemporaryDataTasklet implements Tasklet {

    private final TemporaryDataService temporaryDataService;

    public CleanupTemporaryDataTasklet(
            TemporaryDataService temporaryDataService) {
        this.temporaryDataService = temporaryDataService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        int deleted = temporaryDataService.deleteExpiredRecords();
        contribution.incrementWriteCount(deleted);

        return RepeatStatus.FINISHED;
    }
}
```

This example calls a service to delete expired data, updates the write count, and finishes the Step. Updating the counter helps the metadata reflect part of the result, but `writeCount` does not replace business logs or a detailed report if you need to record the number of deleted records per group.

## 4. Use a lambda when the task is simple

If the work is short and does not need its own class, you can declare the Tasklet with a lambda:

```java
@Bean
Step generateControlFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ControlFileService controlFileService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        controlFileService.generateControlFile();
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("generateControlFileStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
```

A lambda suits tasks that are short, have little state, and are easy to understand. If the logic has many branches, complex dependencies, needs checkpoints, or needs to be tested separately, a class implementing `Tasklet` is usually clearer.

## 5. RepeatStatus and tasks that need multiple passes

A Tasklet does not have to be called only once. You can use `CONTINUABLE` to process work in multiple passes. For example, a cleanup task deletes at most 1,000 records per call to limit the transaction duration:

```java
@Component
public class DeleteExpiredRecordsTasklet implements Tasklet {

    private final TemporaryDataService service;

    public DeleteExpiredRecordsTasklet(TemporaryDataService service) {
        this.service = service;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        int deleted = service.deleteNextBatch(1_000);
        contribution.incrementWriteCount(deleted);

        if (deleted == 0) {
            return RepeatStatus.FINISHED;
        }

        return RepeatStatus.CONTINUABLE;
    }
}
```

Each call processes at most 1,000 records. When there are no more records to delete, the service returns 0 and the Tasklet returns `FINISHED`. The earlier calls return `CONTINUABLE` so the Step continues.

This design needs a reliable stop condition. If the service always returns a number greater than 0 because the query cannot exclude records that have already been processed, the Tasklet can loop forever. You should log the number of records processed, limit the number of passes if necessary, and clearly define how to continue after a restart.

`CONTINUABLE` only asks for the Tasklet to be repeated within the current Step. It does not mean Spring Batch automatically launches a new Job or automatically waits for an external event.

## 6. Reading JobParameters and StepExecutionContext in a Tasklet

A Tasklet can get the Job's input parameters through `ChunkContext` or `StepContribution`. For example, a Tasklet that receives a business date and a file code:

```java
@Bean
@StepScope
Tasklet validateInputFileTasklet(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        @Value("#{jobParameters['businessDate']}") LocalDate businessDate,
        InputFileService inputFileService) {

    return (contribution, chunkContext) -> {
        inputFileService.validate(inputFile, businessDate);
        return RepeatStatus.FINISHED;
    };
}
```

`@StepScope` allows Spring to create the bean within the scope of the StepExecution, so JobParameters can be late-bound when the Step starts. Do not try to read the parameters of a future run in a singleton bean that is created when the application starts.

If you need to store a value for use in the next Step or on restart, you can use `ExecutionContext`:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    ExecutionContext context = contribution
            .getStepExecution()
            .getExecutionContext();

    context.putString("validatedFileVersion", "v3");
    return RepeatStatus.FINISHED;
}
```

The ExecutionContext at the StepExecution level can be saved together with the metadata and restored on restart, depending on when it is updated/committed and on the Step configuration. If the data needs to be used by the next Step, you can store it in the JobExecutionContext through an appropriate mechanism, such as `ExecutionContextPromotionListener`, which promotes selected keys from the Step context to the Job context.

## 7. Transactions and error handling in a Tasklet

The transaction manager passed to `tasklet()` determines the transaction that `TaskletStep` uses when calling the Tasklet. If the Tasklet performs database operations that participate in the same transaction manager, the changes can be committed when the call succeeds or rolled back when an exception causes the transaction to fail.

For example, if a Tasklet updates the status of a data batch and then throws an exception before the transaction commits, the database changes in the same transaction can be rolled back:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    batchRepository.markAsProcessing(batchId);
    batchRepository.updateSummary(batchId);

    if (hasInvalidState(batchId)) {
        throw new IllegalStateException("Batch state is invalid");
    }

    return RepeatStatus.FINISHED;
}
```

If an exception escapes `execute()`, the Step usually moves to `FAILED` and the current transaction is rolled back according to the configuration. Spring Batch records the failure status in the metadata. Avoid catching an exception and ignoring it if the actual task has not been completed; that can cause the Step to be marked `COMPLETED` even though the business result is incorrect.

Not every side effect lies within the database transaction. Calling a REST API, sending an email, writing a file, or publishing a message is usually not rolled back together with the database. If a Tasklet calls an external service and then fails at a later step, the external action may already have happened. Design idempotency keys, record intermediate state, use an outbox, or add a reconciliation step to handle restarts safely.

## 8. Restart and idempotency of a Tasklet

When a Tasklet fails, the Job can be restarted if the Job configuration and Step state allow it. However, a Tasklet does not automatically know how far an external task has progressed. Reliable restartability depends on how the Tasklet stores its progress and how it handles side effects.

For example, a Tasklet sends a file to a partner system. If the partner receives the file successfully but the application stops before Spring Batch saves the Step's completed state, a restart may send the file again.

Some measures:

- Attach a stable batch code or idempotency key to each submission.
- Store the sent status and the confirmation code from the target system.
- Use an immutable file name/version to detect that a file has already been received.
- Split the task into steps that can be reconciled, such as creating the file, sending the file, and confirming the result.
- If the Tasklet repeats many times, store a checkpoint after each committed unit of work.

Do not create a new UUID for each restart if the goal is to identify the same business task. The key must stay stable across executions of the same work.

## 9. How do Tasklet and chunk-oriented processing differ?

Both models run inside a Step but suit different kinds of work.

| Criterion | Tasklet | Chunk-oriented processing |
|---|---|---|
| Model | Performs one task in `execute()` | Reads, processes, and writes many items per chunk |
| Main components | `Tasklet` | `ItemReader`, `ItemProcessor`, `ItemWriter` |
| Completion control | `RepeatStatus.FINISHED` or `CONTINUABLE` | The reader returns `null` when the input is exhausted |
| Transaction | Each Tasklet call is managed within the TaskletStep's transaction | The transaction usually wraps one chunk |
| Suitable for | Cleanup, stored procedures, file creation, orchestration tasks | Import/export, converting and writing large numbers of items |
| Progress tracking | You must record it yourself if the task has multiple parts | Has item counters and checkpoints through the chunk/reader mechanism |

Examples:

- Cleaning a staging table with a single SQL statement or stored procedure: a Tasklet is usually suitable.
- Reading 2 million CSV rows, validating each row, then writing to a database: chunk-oriented processing is usually more suitable.
- Creating a manifest file after the import Steps have completed: a Tasklet may be suitable.

A Tasklet can still process many records, but if the logic is mainly looping over each item and needs a reader, processor, writer, skip, retry, and per-item checkpoints, chunk-oriented processing usually expresses the intent more clearly.

## 10. Using TaskletAdapter for an existing method

When you already have a service or legacy method that performs the task, you can use `MethodInvokingTaskletAdapter` to call that method instead of writing a new Tasklet class. The adapter is configured with the target object and the name of the method to call.

A general example:

```java
@Bean
MethodInvokingTaskletAdapter archiveTaskletAdapter(
        ArchiveService archiveService) {

    MethodInvokingTaskletAdapter adapter =
            new MethodInvokingTaskletAdapter();
    adapter.setTargetObject(archiveService);
    adapter.setTargetMethod("archiveCompletedFiles");
    return adapter;
}
```

The adapter is suitable when the existing method is compatible with the way the adapter invokes it and does not need complex `RepeatStatus` control logic. If you need to handle state, control multiple passes, update the context, or classify errors, implementing `Tasklet` directly is usually more flexible and easier to read. The adapter's API and configuration may differ across Spring Batch versions.

## 11. Logging, listeners, and observing a Tasklet

Because a Tasklet usually represents a task with business meaning, log clearly the start, the result, and the cause of failure. You can use `StepExecutionListener` to record the time before and after the Step:

```java
public class TaskletStepListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info("Starting step {} for job execution {}",
                stepExecution.getStepName(),
                stepExecution.getJobExecutionId());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info("Finished step {} with status {}",
                stepExecution.getStepName(),
                stepExecution.getStatus());
        return null;
    }
}
```

Besides the `BatchStatus`, you need to distinguish `ExitStatus`, which is the result code used to control the Job flow. A listener can add an ExitStatus if the business needs branching after the Step, but you should not change the result arbitrarily to hide errors.

Useful information to monitor:

- JobExecution ID and StepExecution ID.
- The business code or batch ID the Tasklet is processing.
- Start time, completion time, and the number of `execute()` calls.
- The number of records or files processed, if any.
- Confirmation codes from external systems and the retry count.
- The exception and the transaction state on failure.

Do not log passwords, access tokens, or sensitive payloads. If the Tasklet calls an external service, you should monitor the dependency's latency and error rate to distinguish failures of the task from failures of the dependent system.

## 12. Testing a Tasklet

A Tasklet can be tested like an ordinary Java class by mocking the dependent services and creating an appropriate `StepContribution` and `ChunkContext`. Cases worth checking include:

- The task succeeds and returns `RepeatStatus.FINISHED`.
- The task needs multiple passes and returns `CONTINUABLE` until the stop condition.
- The service throws an exception and the error is propagated so the Step can be marked as failed.
- JobParameters or ExecutionContext are read/written correctly.
- The task can be performed again without creating duplicate side effects.

For integration tests, you can run the Step with a test JobRepository and transaction manager to verify metadata, state, and restart. There is no need to call production systems; use a database and mock services intended for testing.

## 13. Common mistakes when using a Tasklet

**Always returning `CONTINUABLE`:** the Step loops forever if there is no stop condition. Define the progress and the completion condition for each pass.

**Returning `FINISHED` before the task is truly complete:** the Step is marked complete even though the work is unfinished. Return `FINISHED` only after confirming the required result.

**Using a Tasklet for a large data loop:** a single method that reads millions of records itself can lose the benefits of chunking, checkpoints, and per-item skip and retry. Consider chunk-oriented processing.

**Holding a transaction too long:** a Tasklet that performs all the large work in one call can hold connections and locks for a long time. Split the work into multiple passes with checkpoints, or use chunks where appropriate.

**Assuming a REST call rolls back together with the database:** an external system does not automatically participate in the Step's transaction. You need idempotency and a reconciliation mechanism.

**Catching an exception and still returning `FINISHED`:** the error is hidden and the Job may report success while the task failed. Handle an exception only when there is a clear policy, and record the corresponding result.

**Not saving the progress of a multi-pass Tasklet:** after a restart, the Tasklet may start over from the beginning or skip work. Store a checkpoint or design the task to be idempotent.

## Conclusion

`Tasklet` lets a Step perform a single task through `execute(StepContribution, ChunkContext)`. A Tasklet returns `RepeatStatus.FINISHED` when it is done or `CONTINUABLE` when it needs more passes. `TaskletStep` manages transactions, state, and metadata for the calls. A Tasklet suits cleanup, stored procedures, file creation, and orchestration work with a clear scope; chunk-oriented processing is more suitable when you need to read, process, and write a large number of items with per-chunk checkpoints. When a Tasklet calls an external service or performs a task that may be repeated, you need to control the transaction boundary, idempotency, progress, and logging to restart safely.
