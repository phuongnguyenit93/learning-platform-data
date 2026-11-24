# Tasklet for one-time operations

In Spring Batch, `Tasklet` suits a Step that performs a single independent action that can be completed in one call, such as deleting temporary data, calling a stored procedure, checking a condition, preparing a resource, or moving a file. For this kind of work, the application does not need to build a pipeline that reads, processes, and writes each item as in chunk-oriented processing.

A Tasklet usually returns `RepeatStatus.FINISHED` once the operation completes. This result tells Spring Batch that the Tasklet does not need to be called again in the current Step. That is the meaning of "one-time operation": one execution of the Step's logic can complete with a single call to `execute`. It does not mean the action will happen exactly once during the entire lifetime of the application; a Job can be launched with a new JobInstance, or a Step can be run again on restart according to the configured policy.

## 1. What is a Tasklet?

`Tasklet` is the Spring Batch interface used to represent a unit of work. The main contract looks like this:

```java
public interface Tasklet {
    RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception;
}
```

The `execute` method receives two context objects:

- `StepContribution` lets the Tasklet access information about the Step execution and contribute some information, such as counters or the contribution status.
- `ChunkContext` provides the context of the call, including the `StepContext`, the `StepExecution`, and related attributes.

A Tasklet does not require an `ItemReader`, `ItemProcessor`, or `ItemWriter`. The operation's logic is placed in `execute` or delegated to a dedicated service.

## 2. RepeatStatus.FINISHED signals that the operation is complete

For a Tasklet that performs an independent action, the `execute` method normally returns `RepeatStatus.FINISHED` after the action succeeds:

```java
@Bean
Step cleanupStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CleanupService cleanupService) {

    return new StepBuilder("cleanupStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                cleanupService.deleteTemporaryData();
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

In the example, the Step calls the temporary-data cleanup service once. When the service finishes normally, the Tasklet returns `FINISHED` and the Step can end successfully.

If `execute` throws an exception, Spring Batch treats the Step execution as failed and handles it according to the Step's transaction mechanism, status, and error policy. You should not catch an exception and still return `FINISHED` if the actual operation has not completed; that can cause the Job to report success even though the work was left unfinished.

## 3. How does a TaskletStep call a Tasklet?

When a Tasklet is attached to a Step with `.tasklet(...)`, Spring Batch creates a Tasklet-oriented Step. While running, the framework calls `execute` and looks at the `RepeatStatus` to decide whether to keep repeating:

```text
TaskletStep starts
       |
       v
Open transaction
       |
       v
Tasklet.execute(...)
       |
       +-- FINISHED ------> Complete the Step
       |
       +-- CONTINUABLE --> Call the Tasklet again
       |
       +-- Exception ----> Roll back per the transaction
                            and handle the Step failure
```

For a one-time operation, returning `FINISHED` is the normal approach. `RepeatStatus.CONTINUABLE` means the Tasklet still has work to do and Spring Batch will call `execute` again in the Step's loop.

Each Tasklet call is performed in the transaction configured by the Step. Therefore, if a Tasklet returns `CONTINUABLE`, the calls can have their own transaction boundaries. For a one-time operation, this usually means one call does the work and ends; if multiple passes are needed, clearly define the checkpoint and the ability to re-run.

## 4. When should you use a Tasklet for a one-time operation?

A Tasklet suits work that can be described as an action with input and a result at the task level, without needing to process each item separately.

### Cleaning up temporary data

Before importing new data, the application may need to delete old staging data or expired temporary records. If the operation is a single SQL statement or an independent service call, a Tasklet is the natural choice.

```java
@Bean
Step clearStagingStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcTemplate jdbcTemplate) {

    return new StepBuilder("clearStagingStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                jdbcTemplate.update("DELETE FROM order_staging");
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

This is an illustrative example; a real SQL statement needs appropriate conditions to delete only data belonging to the batch or the permitted scope. If the table is very large or the delete creates a long transaction, consider a segmented deletion strategy, partitioning, or an appropriate database mechanism.

### Calling a stored procedure

If the database already has a stored procedure that handles an aggregation task or updates a data set, a Tasklet can call the procedure once:

```java
@Bean
Step refreshSummaryStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcTemplate jdbcTemplate) {

    return new StepBuilder("refreshSummaryStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                jdbcTemplate.update("call refresh_daily_summary()");
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

The syntax for calling a procedure depends on the database management system and how the procedure is declared. If the procedure returns output parameters or complex results, you can use `SimpleJdbcCall` or an appropriate JDBC API.

### Checking a condition before processing

A Step can confirm that the input file exists, check that a batch is in a state allowed for processing, or check a general business condition. If the condition is not met, the Tasklet can throw an appropriate exception so the Job stops at that Step.

```java
@Bean
Step verifyInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        InputFileService inputFileService) {

    return new StepBuilder("verifyInputStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                if (!inputFileService.isReady()) {
                    throw new IllegalStateException("Input file is not ready");
                }
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

If the check only confirms a quick condition, a Tasklet is suitable. If you need to check millions of records or analyze each line of data, use chunk processing or a dedicated data-set validation step.

### Preparing or releasing resources

A Tasklet can create a directory, initialize a staging table, prepare a manifest, close a resource, or clean up intermediate files. These operations usually do not need an item pipeline.

### Moving or archiving a file

After an import Step completes, the final Tasklet in the Job can move the input file to an archive directory or rename the file to mark it as processed. This operation is usually described as a single action.

When working with a filesystem, take into account the case where the file has been moved but the process stops before the Step's metadata is updated. A restart may call the Tasklet again. Check the source/target files and design the action so it can be re-run safely.

## 5. Declaring a Tasklet with Java configuration

In Spring Batch 5, a Tasklet is attached to a Step with `StepBuilder.tasklet(tasklet, transactionManager)`:

```java
@Bean
Step archiveInputFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ArchiveService archiveService) {

    Tasklet archiveTasklet = (contribution, chunkContext) -> {
        archiveService.archiveProcessedFile();
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("archiveInputFileStep", jobRepository)
            .tasklet(archiveTasklet, transactionManager)
            .build();
}
```

You can declare a Tasklet as a lambda for short logic, or create a separate class when the logic has many branches, needs complex dependencies, or needs independent unit tests.

### Extracting the Tasklet into a separate class

```java
@Component
public class ArchiveFileTasklet implements Tasklet {

    private final ArchiveService archiveService;

    public ArchiveFileTasklet(ArchiveService archiveService) {
        this.archiveService = archiveService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        archiveService.archiveProcessedFile();
        return RepeatStatus.FINISHED;
    }
}
```

Register this class in the Step:

```java
@Bean
Step archiveInputFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ArchiveFileTasklet archiveFileTasklet) {

    return new StepBuilder("archiveInputFileStep", jobRepository)
            .tasklet(archiveFileTasklet, transactionManager)
            .build();
}
```

A separate class separates responsibilities and makes testing easier. If the Tasklet holds mutable state, pay attention to scope and to the fact that the same bean may be used by multiple executions. Do not store state specific to one run in a field of a singleton Tasklet if Jobs may run concurrently.

## 6. Getting JobParameters and the execution context in a Tasklet

A one-time operation often needs parameters such as a file name or a business date. A Tasklet can read them from the `StepContribution` or `ChunkContext` through the `StepExecution` and `JobExecution`.

```java
@Bean
Step archiveFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ArchiveService archiveService) {

    return new StepBuilder("archiveFileStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                StepExecution stepExecution = contribution.getStepExecution();
                JobParameters parameters = stepExecution
                        .getJobExecution()
                        .getJobParameters();

                String inputFile = parameters.getString("inputFile");
                LocalDate businessDate = parameters.getLocalDate("businessDate");

                archiveService.archive(inputFile, businessDate);
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

The methods that retrieve parameters must match the type that was passed and the Spring Batch version. In the example, `businessDate` is stored as a date type; if the application passes the date as a string, you need to parse it according to the specified format.

If a Tasklet needs to share a result with the next Step, it can write small data to the Job `ExecutionContext`. If it only needs its own checkpoint, use the Step `ExecutionContext`. Do not store large business payloads in the context; store a key or a reference to data that is kept in an appropriate place.

## 7. Transactions for a one-time operation

A TaskletStep executes the Tasklet within the transaction configured for the Step. For a single call that returns `FINISHED`, database operations that participate in the transaction manager can be committed when the call completes normally or rolled back when an exception causes the transaction to fail.

For example, if a Tasklet performs an `UPDATE` statement with `JdbcTemplate` and uses the same transaction manager as the Step, the database change can participate in that transaction.

However, a transaction does not automatically undo every kind of side effect:

- An HTTP request that has already been sent to another system.
- An email that has already been sent.
- A file that has already been moved or deleted.
- An external system call that has already been accepted.

If a Tasklet both updates the database and calls an external API, rolling back the database transaction does not make the API forget the request it received. Separate the side effects, and use an idempotency key or a transactional outbox when you need to coordinate data and events.

If a stored procedure commits on its own or uses an independent transaction, you need to determine the database's actual transaction behavior. Do not assume the procedure always rolls back together with the Step's transaction.

## 8. "One-time" in a Tasklet does not mean exactly-once

A Tasklet that returns `FINISHED` after a single call only means the Step does not need to call the Tasklet again in the current loop. The action can still be performed again in other situations:

- The Job is launched with a new JobInstance with different identifying parameters.
- The Step fails and the Job is restarted according to the permitted policy.
- An external operation has completed but the process stops before the metadata records the Step as complete.
- A completed Step is configured with `allowStartIfComplete(true)` and is run again in an applicable restart.
- An operator deliberately re-launches the business process with a new identifier.

Therefore, a Tasklet does not by itself provide an exactly-once guarantee for external side effects. You need to distinguish "one call within one Step execution" from "happens exactly once across the entire system".

### Idempotent design

An idempotent operation can be called again and the final business result is still correct. For example:

- Delete temporary records for a specific `batchId`; deleting again causes no discrepancy.
- Create a directory if it does not exist.
- Move a file if the source file exists and the target file does not exist; if the target file already exists, check its content or state instead of blindly overwriting.
- Update a status by business key and the previous-state condition.
- Call an API with an idempotency key so the target system can recognize a repeated request.

If an operation cannot be repeated safely, you need a clear coordination and reconciliation mechanism before allowing a restart or re-launch.

## 9. Restart and re-running a Tasklet

Spring Batch stores the StepExecution state in the JobRepository. When a Job fails and is restarted, a Step that has not completed can be executed again according to the Job's and Step's policy. The Tasklet needs to be designed to handle this situation.

If a Step has completed, when the same JobInstance is restarted, Spring Batch normally skips that Step. You can configure `allowStartIfComplete(true)` so a completed Step is run again in an applicable restart:

```java
@Bean
Step refreshReferenceDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ReferenceDataTasklet tasklet) {

    return new StepBuilder("refreshReferenceDataStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

Only enable this option if the operation needs to run again when the Job is restarted and can be performed safely. It is not a way to re-launch a completed JobInstance with an ordinary launch command.

If a Job uses `preventRestart()`, the Job cannot be restarted after the previous execution ended in a state that allows restart. This is a Job-level policy; use it only when the business truly does not allow continuing the old execution. Do not use `preventRestart()` as a substitute for an idempotent design.

### Saving a checkpoint when a Tasklet has multiple passes

If a task has multiple phases or needs to be split into multiple passes, the Tasklet can store progress in the `ExecutionContext` and return `CONTINUABLE`:

```java
.tasklet((contribution, chunkContext) -> {
    ExecutionContext context = contribution
            .getStepExecution()
            .getExecutionContext();

    int page = context.getInt("nextPage", 0);
    boolean hasMore = migrationService.processPage(page);

    if (hasMore) {
        context.putInt("nextPage", page + 1);
        return RepeatStatus.CONTINUABLE;
    }

    return RepeatStatus.FINISHED;
}, transactionManager)
```

This is an illustrative skeleton for a multi-pass Tasklet, not a purely one-time operation example. The checkpoint must be updated consistently with the portion of work that has completed. If the work is inherently about processing many items and needs a commit interval, per-item skip/retry, or automatic checkpoints, chunk processing is usually more suitable.

## 10. When should you not use a Tasklet for a one-time operation?

A Tasklet is not a good choice if the actual work is processing a large set of items through the same pipeline.

For example, do not wrap the entire import of millions of rows in one big loop inside `execute` if you need to:

- Commit in groups to avoid long transactions.
- Track the number of items read, processed, written, and skipped.
- Retry or skip individual items.
- Restart from a read/write checkpoint.
- Use Spring Batch's standard readers and writers.

In that case, chunk processing organizes the work better and provides a more suitable item-management mechanism.

Conversely, you do not need to create a reader that returns a single item and a writer that merely calls a service in order to simulate a chunk step if the operation is really an independent action. A Tasklet expresses the meaning of the work directly.

## 11. Combining a Tasklet with a chunk Step in a Job

A Job can use a Tasklet for preparation/finishing operations and chunk processing for the data portion:

```text
Job: import-orders
  |
  v
Tasklet Step: check the file and prepare staging
  |
  v
Chunk Step: read, validate, transform, and write orders
  |
  v
Tasklet Step: create a report and archive the file
```

For example:

- The first Tasklet checks the input file and deletes the staging data belonging to the current batch.
- The Chunk Step processes the orders in groups and commits per chunk.
- The last Tasklet creates a summary report and moves the processed file.

This combination gives each Step a clear responsibility. The Tasklet handles independent actions; the chunk step handles the item pipeline.

## 12. Error handling in a Tasklet

A Tasklet can throw an exception when the operation fails. Spring Batch will handle the call's transaction and update the Step status according to the execution result.

For example, if a required file is not found, the Tasklet can throw an exception:

```java
if (!Files.exists(inputPath)) {
    throw new FileNotFoundException(
            "Required input file was not found");
}
```

Do not catch an exception and return `FINISHED` if the work is not complete. If you want to treat a case as having nothing to do, determine that it is a valid business result and record it clearly, and only then return `FINISHED`.

If an error is recoverable, choose a retry approach appropriate to the Step and ensure the operation can be repeated. If the error is not recoverable or the data is not trustworthy, let the Step fail and handle it through the restart/investigation process.

A Tasklet can use a listener to record the start/end time or a custom exit status. Do not put all the business logic into a listener; the main action should reside in the Tasklet or in the service the Tasklet calls.

## 13. Common mistakes

### Forgetting to return RepeatStatus.FINISHED

If a Tasklet returns `CONTINUABLE`, Spring Batch will call `execute` again. For a one-time operation, you need to return `FINISHED` after completion so the Step ends the loop.

### Thinking a Tasklet runs exactly once in every case

A Tasklet can be called again because of `CONTINUABLE`, a restart, a retry, or a new JobInstance. Clearly define the scope of "once" and design for idempotency.

### Catching an exception and still returning FINISHED

This can cause the Step to be marked successful even though the operation has not completed. Return `FINISHED` only when the result meets the requirements or when doing nothing is a clearly defined valid result.

### Putting a loop that processes millions of items in a single execute

A Tasklet can run a loop, but the application then has to manage commit, checkpoint, retry, skip, and statistics itself. If the work is item processing, a chunk step is usually more suitable.

### Assuming a database rollback undoes a file or API operation

The Step's transaction does not automatically undo filesystem operations or HTTP requests. Use state checks, an idempotency key, an outbox, or a reconciliation process.

### Storing execution state in a field of a singleton Tasklet

A singleton Tasklet bean can be used by multiple executions. Storing mutable business state in a field can cause Jobs to affect each other. Use the Job/Step ExecutionContext or an appropriate bean scope for per-execution state.

### Enabling allowStartIfComplete without considering side effects

This option allows a completed Step to be run again on restart. If the operation is not idempotent, re-running can create duplicate data or repeat an external action.

## 14. Process for designing a Tasklet for a one-time operation

When building a Tasklet-style Step, you can follow this sequence:

1. Determine whether the action can be completed as an independent unit or is really a multi-item pipeline.
2. Put the business logic into an appropriate service; keep `execute` short and focused on orchestration.
3. Pass dependencies through the constructor or bean parameters; do not arbitrarily create connections or resources on each call.
4. Determine the transaction manager and which resources actually participate in the transaction.
5. Return `RepeatStatus.FINISHED` when the action completes.
6. Let the exception propagate if the operation fails; do not mark a false success.
7. Design the operation to be safely re-runnable or define a clear recovery process.
8. Use the ExecutionContext if you need to store a checkpoint or share a result between Steps.
9. Check restart scenarios and new-JobInstance scenarios to avoid duplicate side effects.

| Work | Is a Tasklet suitable? | Reason |
|---|---|---|
| Call a stored procedure to refresh a summary table | Yes | A single system-level call. |
| Delete the staging data of a batch | Yes | A single SQL operation with a clear scope. |
| Check that an input file exists | Yes | A single pre-processing condition. |
| Archive a file after import | Yes | An independent filesystem operation; it needs a safely re-runnable design. |
| Create a directory or a marker file | Yes | A single preparation/finishing action. |
| Import millions of rows and validate each row | Usually not | Needs an item pipeline, a commit interval, and checkpoints. |
| Skip faulty records and retry items hit by transient errors | Usually not | Chunk processing has item-level fault tolerance. |

## Conclusion

A Tasklet suits an independent operation that can be completed in a single `execute` call, such as cleaning up data, calling a stored procedure, checking a condition, or archiving a file. After the operation succeeds, return `RepeatStatus.FINISHED` so Spring Batch ends the Step's loop. "One-time" only describes the call within one Step execution; a restart, a new JobInstance, or the `allowStartIfComplete(true)` configuration can still cause the action to run again. Therefore, understand the transaction boundary, let errors be reflected correctly, and design tasks to be idempotent whenever possible.
