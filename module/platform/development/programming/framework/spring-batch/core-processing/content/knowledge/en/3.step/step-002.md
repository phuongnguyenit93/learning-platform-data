# StepExecution and Execution Status

In Spring Batch, `StepExecution` is the object that records one specific execution of a `Step`. It tells you which Step ran, which Job run it belongs to, when it started and ended, what state it is in, how many items it read or wrote, how many commits or rollbacks occurred, and what state data needs to be retained for the next run.

`StepExecution` is an important part of the mechanism Spring Batch uses to manage and recover work. When you need to explain why a Step succeeded or failed, monitor processing progress, decide the next branch of a Job, or resume an interrupted Job, you usually have to examine the `StepExecution` together with `BatchStatus`, `ExitStatus`, `ExecutionContext`, and `JobRepository`.

## 1. Where Does StepExecution Fit in the Execution Model?

A Job is composed of one or more Steps. Each time a Step is executed, Spring Batch creates a `StepExecution` object to represent that run. A `StepExecution` belongs to a `JobExecution`, and a `JobExecution` represents one run of a Job instance.

The concepts relate to each other as follows:

```text
Job
 |
 +-- JobInstance
       |
       +-- JobExecution, first run
       |      |
       |      +-- StepExecution: validateInput
       |      +-- StepExecution: importOrders
       |      +-- StepExecution: archiveFile
       |
       +-- JobExecution, re-run
              |
              +-- StepExecution: importOrders
              +-- StepExecution: archiveFile
```

A `JobInstance` identifies one business run of a Job based on the Job name and the identifying JobParameters. A `JobExecution` is one attempt to run that JobInstance. If a Job fails and is restarted with the same identifying parameters, Spring Batch creates a new `JobExecution` for the same `JobInstance`. The Steps executed in that run have corresponding `StepExecution`s.

A `StepExecution` is therefore not the Step definition itself. The Step definition describes how the work is done; a `StepExecution` stores the information of one specific execution. The same Step can have multiple StepExecutions across different runs or restarts.

For example, `importOrdersStep` may run for the first time and fail after processing some chunks. When the Job is restarted, Spring Batch creates a new execution for that Step. The saved checkpoint state can be used to resume the work. The old StepExecution record remains as the history of the previous run.

## 2. What Information Does StepExecution Contain?

`StepExecution` provides the identification, status, timing, processing metrics, and execution context of one Step run.

### Identification and Association Information

Some commonly used properties:

| Property or method | Meaning |
|---|---|
| `getId()` | The ID of the StepExecution record stored in the JobRepository. |
| `getStepName()` | The name of the Step that this execution represents. |
| `getJobExecution()` | The parent JobExecution that contains this StepExecution. |
| `getJobExecutionId()` | The ID of the parent JobExecution. |
| `getVersion()` | The metadata version used for the optimistic locking mechanism. |
| `getStartTime()` | The time the Step started executing. |
| `getEndTime()` | The time the Step ended, if it has ended. |
| `getLastUpdated()` | The time the StepExecution metadata was most recently updated. |

The ID usually has a value only after the JobRepository saves the object. In an application, let Spring Batch create and manage the StepExecution rather than creating it yourself or editing the metadata directly.

### Status and Result

Two pieces of information that are often read together are:

- `getStatus()` returns a `BatchStatus`, which describes the execution status of the Step.
- `getExitStatus()` returns an `ExitStatus`, which describes the exit result that Spring Batch uses in flow control and reporting.

The two values are related but not synonymous. `BatchStatus` tells you whether the Step is running, completed, failed, or stopped. `ExitStatus` gives the result code and description of the run; an application can create custom exit codes to control Job branches.

### Processing Counters

For a Step that processes data, the counters help you observe progress and detect problems:

| Counter | Meaning |
|---|---|
| `getReadCount()` | Number of items read successfully. |
| `getWriteCount()` | Number of items written by the writer. |
| `getFilterCount()` | Number of items filtered by the processor, usually because the processor returned `null`. |
| `getCommitCount()` | Number of times the Step's transaction has committed. |
| `getRollbackCount()` | Number of times the Step's transaction has rolled back. |
| `getReadSkipCount()` | Number of items skipped because of an error during reading. |
| `getProcessSkipCount()` | Number of items skipped because of an error during processing. |
| `getWriteSkipCount()` | Number of items skipped because of an error during writing. |
| `getSkipCount()` | Total number of items skipped across all phases. |

These counters are useful for monitoring and diagnosis. They do not replace the business metrics stored in the target system. For example, `writeCount` tells you how many items the writer wrote according to the Step's statistics, but it does not by itself prove that every external system received and processed the data as expected.

### ExecutionContext

Each StepExecution has its own `ExecutionContext`. This is a state storage area for state that needs to persist across updates and can be used when restarting the Step. For example, a reader can store its current position in a file or the page index it is reading.

`StepExecution` is also linked to a `JobExecution`, so an application can access the Job-level context through the JobExecution. You need to distinguish these two scopes:

- The Step `ExecutionContext` stores the state of a single Step, usually checkpoints used to restart that Step.
- The Job `ExecutionContext` stores data that needs to be shared between Steps within the same JobExecution.

Do not substitute the two contexts for each other arbitrarily. Choose the scope according to the lifecycle and where the data needs to be used.

## 3. BatchStatus: The Execution Status of a Step

`BatchStatus` is an enum that represents the lifecycle state of a JobExecution or a StepExecution. Commonly seen values include:

| BatchStatus | Meaning |
|---|---|
| `STARTING` | The execution is being initialized before entering the running state. |
| `STARTED` | The execution is running. |
| `STOPPING` | A stop request has been received and the execution is waiting to stop safely. |
| `STOPPED` | The execution has stopped on request. |
| `COMPLETED` | The execution completed successfully according to its BatchStatus. |
| `FAILED` | The execution failed because of an error. |
| `ABANDONED` | The execution was marked as abandoned, and is usually not restarted like an ordinary failed Step. |
| `UNKNOWN` | The execution status, or whether it is safe to continue, cannot be determined with certainty. |

A Step usually goes from `STARTING` to `STARTED`, then ends in a final status such as `COMPLETED`, `FAILED`, or `STOPPED`. `STOPPING` is a transitional state during the stop process. This is the common way to understand the lifecycle; do not assume that every status must appear or that every run goes through an identical sequence.

### COMPLETED

`COMPLETED` indicates that the Step completed successfully according to its BatchStatus. When a JobInstance is restarted, a completed Step is usually skipped by Spring Batch to avoid redoing work that is already done. If the business needs a completed Step to run again in a restart, you can configure `allowStartIfComplete(true)` on the Step, but you must ensure that re-running the task is safe.

### FAILED

`FAILED` indicates that the Step did not complete normally because of an error. If the configuration and the restart conditions allow it, the JobInstance can be run again. Spring Batch creates a new execution for the re-run; the saved state and context from the previous run can be used for recovery.

Do not assume that every `FAILED` Step is automatically re-run immediately. A restart depends on the JobInstance, the JobExecution state, the Step configuration, the start limit, and how the application launches the Job.

### STOPPED and STOPPING

`STOPPING` indicates that a stop request has been recorded and the framework is trying to finish at a safe boundary. `STOPPED` is the status after the execution has stopped. In chunk processing, stopping usually has to wait until the current processing reaches an appropriate point so that state and transactions are handled consistently.

A stopped Job or Step does not mean a business failure. It can be restarted according to the application's policy if the metadata and checkpoints allow it.

### ABANDONED and UNKNOWN

`ABANDONED` is typically used when an execution is decided to be skipped in an operational or restart process. A Step in this status is not treated like an ordinary failed Step that can be automatically continued.

`UNKNOWN` needs to be considered carefully. It can indicate an uncertain state, for example when the system cannot safely determine how far the work progressed. Do not arbitrarily change the metadata from `UNKNOWN` to `FAILED` or `COMPLETED` just to make the Job continue. First, cross-check the business data and the state of the related resources.

## 4. ExitStatus: The Result Code of a Step

`ExitStatus` is an object that carries an exit code and an exit description. Spring Batch uses the exit status in Job flow control, especially when configuring transition branches based on Step results.

Some common exit codes are `COMPLETED`, `FAILED`, `EXECUTING`, `NOOP`, `STOPPED`, and `UNKNOWN`. An application can also create its own exit codes, such as `COMPLETED_WITH_NO_DATA` or `COMPLETED_WITH_WARNINGS`.

For example, a Step can have:

```java
ExitStatus exitStatus = stepExecution.getExitStatus();

String code = exitStatus.getExitCode();
String description = exitStatus.getExitDescription();
```

### Distinguishing BatchStatus from ExitStatus

| Situation | BatchStatus | ExitStatus |
|---|---|---|
| The Step runs successfully as normal | `COMPLETED` | Usually `COMPLETED` |
| The Step runs successfully but there is no data | May be `COMPLETED` | May be `COMPLETED_WITH_NO_DATA` |
| The Step encounters an unhandled error | `FAILED` | Usually `FAILED` |
| The Step stops on request | Usually `STOPPED` once the stop is finished | Usually `STOPPED` |

A Step can have `BatchStatus.COMPLETED` and a custom exit code. This is useful when the technical work has completed but the Job needs to branch based on a business result. Do not change the BatchStatus to `FAILED` just to drive a business branch if the Step actually completed normally; use ExitStatus for that purpose.

### Creating a Custom Exit Status with a Listener

`StepExecutionListener.afterStep` can return an `ExitStatus` to supplement or change the Step's exit status. Return `null` if the listener does not need to change the result.

```java
@Bean
StepExecutionListener noDataExitStatusListener() {
    return new StepExecutionListener() {
        @Override
        public void beforeStep(StepExecution stepExecution) {
            // You can record information when the Step starts.
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            if (stepExecution.getStatus() == BatchStatus.COMPLETED
                    && stepExecution.getReadCount() == 0) {
                return new ExitStatus("COMPLETED_WITH_NO_DATA");
            }
            return null;
        }
    };
}
```

Registering the listener on the Step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet importTasklet,
        StepExecutionListener noDataExitStatusListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .tasklet(importTasklet, transactionManager)
            .listener(noDataExitStatusListener)
            .build();
}
```

In a real application, the condition for detecting “no data” must fit the way the Step reads data. The example above illustrates how to use a listener and an exit code; not every Step is meaningful from a business perspective when judged only by `readCount`.

### Using ExitStatus to Control the Flow

A Job can branch according to the exit code:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        Step notifyNoDataStep,
        Step archiveStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(importOrdersStep)
                .on("COMPLETED_WITH_NO_DATA").to(notifyNoDataStep)
            .from(importOrdersStep)
                .on("COMPLETED").to(archiveStep)
            .from(importOrdersStep)
                .on("*").fail()
            .end()
            .build();
}
```

This is an example of the idea of routing by exit code. In a Job with many branches, you need to define all the transitions fully and check the order of the patterns so that you do not create unintended branches. Custom exit codes need to be consistent between the listener and the flow configuration.

## 5. How Is a StepExecution Created and Updated?

While running, Spring Batch coordinates the Step, the JobRepository, and related components to store the execution state.

At a high level:

1. The Job starts and Spring Batch creates a JobExecution for that run.
2. When a Step starts, the framework creates a StepExecution attached to the JobExecution.
3. The JobRepository stores the initial metadata and the execution status.
4. The Step runs the Tasklet or chunk logic, updating the counters, context, and state as needed.
5. When the transactions or appropriate update points complete, the metadata is written back through the JobRepository.
6. When the Step ends, the end time, BatchStatus, and ExitStatus are updated.

`JobRepository` is the component responsible for storing the metadata of JobExecutions and StepExecutions. In a configuration that uses the JDBC JobRepository, the metadata is usually stored in tables such as `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, `BATCH_JOB_EXECUTION_CONTEXT`, and `BATCH_STEP_EXECUTION_CONTEXT`. The table names and schema can be customized through configuration.

Do not update the metadata tables directly with ordinary SQL while a Job is running. Spring Batch uses update and versioning mechanisms to maintain consistency, including optimistic locking in the appropriate operations. Editing them directly can corrupt the state, the checkpoints, or the relationships between executions.

### The Role of the Version

A StepExecution has version information that is used in the JobRepository's optimistic locking mechanism. When multiple operations try to update the same execution record, the version helps detect updates based on stale data. This protects the metadata from some inconsistent concurrent-update scenarios.

An application should not increment the version itself or overwrite the metadata fields itself to resolve conflicts. Look for the actual operational cause, such as multiple launchers starting the same JobInstance or multiple processes trying to update the same execution.

## 6. Reading StepExecution in Code

### Access from a Tasklet

A Tasklet receives a `StepContribution` and a `ChunkContext`. You can get the StepExecution from the contribution to read the state and update the ExecutionContext:

```java
@Bean
Step prepareStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    return new StepBuilder("prepareStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                StepExecution stepExecution = contribution.getStepExecution();

                String stepName = stepExecution.getStepName();
                long currentReadCount = stepExecution.getReadCount();

                stepExecution.getExecutionContext()
                        .putString("preparation", "done");

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

This is how to get the execution context while the Step is running. The counters may not yet reflect the full final result until the chunk or the Step completes. Do not use a value read midway as the final summary figure.

### Access from a StepExecutionListener

A listener is suitable when you need to do processing before and after a Step, for example logging, checking counters, or setting the exit status:

```java
public class StepAuditListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        System.out.println("Starting: " + stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        System.out.println("Read: " + stepExecution.getReadCount());
        System.out.println("Written: " + stepExecution.getWriteCount());
        System.out.println("Status: " + stepExecution.getStatus());
        return null;
    }
}
```

`beforeStep` is called when the Step starts. `afterStep` is called when the Step ends and can return an additional exit status. A listener is an appropriate place to observe state; avoid putting all the item-processing logic in a listener, because that blurs the responsibilities of the reader, processor, writer, or Tasklet.

### Access to StepExecution in a Step-scoped Bean

With a `@StepScope` bean, you can obtain StepExecution properties through late binding:

```java
@Bean
@StepScope
ItemReader<OrderInput> orderReader(
        @Value("#{stepExecution}") StepExecution stepExecution) {

    String stepName = stepExecution.getStepName();
    // Initialize the reader based on the Step's context if needed.
    return createOrderReader(stepName);
}
```

Late binding lets the bean receive the active execution when the StepScope is opened. Do not access a StepExecution that does not yet exist while the application context is being initialized; StepScope solves this by deferring bean initialization until the proper execution scope.

## 7. Using StepExecution to Monitor Progress and Diagnose

When a Step processes large volumes of data, the StepExecution provides important metrics for understanding efficiency and detecting anomalies.

For example, a Step with these metrics:

| Metric | Illustrative value |
|---|---:|
| Read count | 10,000 |
| Write count | 9,850 |
| Filter count | 100 |
| Read skip count | 20 |
| Process skip count | 25 |
| Write skip count | 5 |
| Commit count | 100 |
| Rollback count | 3 |

These metrics suggest that some items were filtered or skipped, and that the Step had a few rollbacks. When analyzing, you need to combine the counters with the error logs, the exception types, the source data, and the actual results in the target system. Do not conclude that every item that was not written is an error: the processor may deliberately filter items, and skips may be a policy that has been permitted.

Some signs worth investigating:

- `readCount` increases but `writeCount` is abnormally low: look at the processor logic, filtering, skips, and write conditions.
- `rollbackCount` keeps increasing: look at transaction errors, deadlocks, timeouts, or writer errors.
- `readSkipCount`, `processSkipCount`, or `writeSkipCount` increase: check for bad data and the skip policy.
- The Step runs for a long time but the counters do not increase: look for a blocked reader, calls to external systems taking too long, or a transaction that has not completed.
- `COMPLETED` but the business result is incomplete: check the filter/skip logic, idempotency, and side effects outside the transaction.

## 8. Using JobExplorer to View Stored StepExecutions

In operations, you often need to look up executions that have finished or are running. `JobExplorer` provides an API for reading Job and Step metadata from the configured store.

For example, get a JobExecution by ID and then iterate over its StepExecutions:

```java
@Service
public class BatchExecutionQueryService {

    private final JobExplorer jobExplorer;

    public BatchExecutionQueryService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public void printStepExecutions(long jobExecutionId) {
        JobExecution jobExecution = jobExplorer.getJobExecution(jobExecutionId);
        if (jobExecution == null) {
            return;
        }

        for (StepExecution stepExecution : jobExecution.getStepExecutions()) {
            System.out.printf(
                    "step=%s, status=%s, exit=%s, read=%d, write=%d, commits=%d%n",
                    stepExecution.getStepName(),
                    stepExecution.getStatus(),
                    stepExecution.getExitStatus().getExitCode(),
                    stepExecution.getReadCount(),
                    stepExecution.getWriteCount(),
                    stepExecution.getCommitCount());
        }
    }
}
```

This is a query of metadata that has already been stored. While a Step is still running, the values read reflect the most recent metadata update, so they may lag behind the in-memory state of the executing process. `JobExplorer` is for querying; `JobRepository` is used by the framework to save and update executions.

In an environment with multiple applications or multiple launchers, make sure the components all use the correct metadata repository and have appropriate access rights. If you query a different repository from the one the Job is using, the data may not reflect the execution you expect.

## 9. StepExecution and Restart

Restart is one of the important reasons Spring Batch stores StepExecution and ExecutionContext. When a Job is interrupted, the framework needs to know which Steps have completed, which Steps have failed, and where the Step being resumed can recover its progress from.

### A Completed Step

When the same JobInstance is restarted, a Step that has a completed execution is usually skipped. This avoids repeating work that has already succeeded. If a Step needs to run again in a restart, you can use `allowStartIfComplete(true)`:

```java
@Bean
Step refreshReferenceDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet refreshTasklet) {

    return new StepBuilder("refreshReferenceDataStep", jobRepository)
            .tasklet(refreshTasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

Enable this option only when the operation can be safely re-run or when a mechanism for controlling side effects is already in place. If the Step sends payments, sends emails, or creates data that is not idempotent, re-running it can cause unwanted consequences.

### A Failed Step

When a Step fails, the Job can be restarted according to policy. The re-run has a new StepExecution, while the previous execution retains its history information. A reader or another component that supports restart can use the saved ExecutionContext to continue at the appropriate position.

For example, a file reader can store the line position it has processed. On restart, the reader restores the position from the context instead of re-reading the entire file. This mechanism works correctly only if the reader supports saving state and the stream is registered correctly.

### Checkpoint and ExecutionContext

The StepExecution's ExecutionContext is a common place to store checkpoints. For example, a Tasklet that processes by page can store the next page number:

```java
ExecutionContext context = stepExecution.getExecutionContext();
long nextPage = context.getLong("nextPage", 0L);

// After the current page has been processed successfully:
context.putLong("nextPage", nextPage + 1L);
```

The code only illustrates the context read/write operations. In a real application, the checkpoint must be updated consistently with the portion of work that has been completed, and it must be saved through the JobRepository. Do not advance the checkpoint before the corresponding work succeeds if doing so could cause a restart to skip unprocessed data.

With chunk processing, `ItemStream` provides callbacks such as `open`, `update`, and `close` so that reading/writing components can restore and save state. Spring Batch invokes the stream mechanism following the Step lifecycle; an application should use readers/writers that support restart rather than managing the read position outside the metadata by itself when it is not necessary.

### Start Limit

A Step can be configured with a limit on the number of starts using `startLimit`. If the limit is exceeded, the Step is not started again. The start limit is a policy that protects the number of executions; it does not replace the restart mechanism or idempotency control.

## 10. Termination and Step Stop Requests

A `StepExecution` can be marked as needing to terminate through the terminate-only flag. This is an internal mechanism that lets the Step recognize that it needs to stop at an appropriate safe point.

An example of checking the flag in the processing logic:

```java
if (stepExecution.isTerminateOnly()) {
    // Stop processing according to the Step's mechanism at an appropriate point.
}
```

In an ordinary application, stopping a Job should go through the appropriate Spring Batch control mechanism and launcher or through a designed operational procedure. Do not arbitrarily change the in-memory state or the metadata to force a Step to stop, because this can lose checkpoints or leave the stored state inconsistent with the actual work.

## 11. Common Mistakes When Working with StepExecution

### Confusing BatchStatus with ExitStatus

`BatchStatus` describes the execution status; `ExitStatus` describes the result used in flow control. When you want to create a “no data” branch while the Step still completes successfully, use an appropriate custom exit code instead of marking the Step as failed.

### Reading Counters Before the Step Ends and Treating Them as the Final Result

While running, the counters may still change. To summarize a Step, read the execution after the Step completes or from metadata that has been stably stored.

### Using the Job ExecutionContext in Place of the Step ExecutionContext

A reader's or Tasklet's own checkpoint usually belongs to the StepExecution. If you store it in the Job-level context by mistake, Steps may share inappropriate state or make restarts hard to predict. Choose the context according to the scope of use.

### Editing the Metadata Tables Yourself

Changing `BATCH_STEP_EXECUTION` or the context tables with direct SQL can corrupt the version, status, time, and checkpoint. Use the Spring Batch API to query or update through the mechanisms the framework supports.

### Assuming a Step Has Only One StepExecution Forever

A Step can have multiple StepExecutions across runs and restarts. When analyzing logs or metadata, you need to identify the correct JobInstance, JobExecution, and StepExecution instead of filtering only by Step name.

### Using ExecutionContext as a Business Data Store

ExecutionContext is designed to store execution state and checkpoints. Do not store large amounts of business data or use the context as the application's main data source. Store business data in an appropriate data store and keep only the keys, positions, or state you need in the context.

### Ignoring Restart Safety

A checkpoint cannot automatically undo side effects outside the transaction. If a Step has already sent an HTTP request or moved a file and then the process stops before the metadata is updated, the re-run may perform that operation again. You need to design idempotent operations, de-duplication keys, or a reconciliation process.

## 12. A Process for Reading and Analyzing a StepExecution

When a Step has an abnormal result, you can analyze it in the following order:

1. Identify the `JobInstance` and `JobExecution` to know whether this is the first run or a restart.
2. Find the right `StepExecution` by Step name and JobExecution ID.
3. Read the `BatchStatus`, `ExitStatus`, the start/end times, and the most recent update time.
4. Look at `readCount`, `writeCount`, `filterCount`, the skip counts, `commitCount`, and `rollbackCount`.
5. Check the failure exception and the Step's log to determine whether the error occurred in the reader, processor, writer, or transaction.
6. Look at the ExecutionContext if you need to understand the checkpoint or the data used for restart.
7. Cross-check the business data in the source and target systems before deciding to restart or to mark the execution as completed.

Do not look at just one `status` field and draw a conclusion about the whole result. For example, `BatchStatus.COMPLETED` together with `ExitStatus.COMPLETED_WITH_NO_DATA` can be a valid result from a business perspective; conversely, `COMPLETED` with missing target data may indicate that the filter logic, skips, or side effects outside the transaction need to be investigated.

## Conclusion

`StepExecution` records one specific execution of a Step, including its status, exit status, timing, processing counters, and ExecutionContext. `BatchStatus` tells you whether the Step is running, completed, failed, or stopped; `ExitStatus` describes the result code and can be customized to control the flow. The JobRepository stores the metadata so that Spring Batch can track history and support restart. When operating or handling errors, look at the StepExecution within the correct JobExecution, and combine the counters, context, and logs to understand exactly what happened.
