# Step Starting, Running, Completing, and Failing

In Spring Batch, a `Step` is a unit of work inside a `Job`. A Job usually consists of several Steps that run in sequence or branch depending on the result of the previous Step. When a Step is executed, Spring Batch creates a `StepExecution` object to record that specific execution: the start and end times, the status, the number of items read/written, the skip counts, the error information, and the checkpoint data.

The Step lifecycle helps the application and operators know whether a piece of work has started, is running, has completed, has stopped in a controlled way, or has failed. Understanding these statuses correctly also helps you decide when a Job can be restarted and when you need to investigate before re-running.

## 1. How Do Step and StepExecution Differ?

A `Step` describes the work to be done. For example, `importCustomersStep` can read a customer file, validate each line, and write valid data to the database. A Step definition is usually created as a bean and referenced in a Job.

A `StepExecution` represents one run of a Step within a `JobExecution`. It stores the state of that run. If a Job is restarted after failing, Spring Batch creates a new `JobExecution` and may create a new `StepExecution` for the Step that needs to run again. Therefore, you should not treat the Step bean and the StepExecution as the same object:

- A `Step` is a definition that can be used across many runs.
- A `StepExecution` is the data that tracks one specific execution of a Step.
- A `JobExecution` contains the `StepExecution`s that correspond to the Steps performed in that Job run.

For example, a customer import Job has three Steps:

```text
customerImportJob
       |
       v
validateFileStep
       |
       v
importCustomersStep
       |
       v
writeSummaryStep
```

Each time a Step is run, Spring Batch writes a corresponding execution record in the JobRepository metadata. This lets the application look up the history of each Step instead of only knowing whether the Job as a whole ultimately succeeded or failed.

## 2. The Statuses in the Step Lifecycle

The state of a `StepExecution` is represented by `BatchStatus`. During execution, the status can pass through the following main milestones:

```text
        StepExecution is created
                  |
                  v
              STARTING
                  |
                  v
               STARTED
                  |
          +-------+--------+
          |                |
          v                v
      COMPLETED          FAILED

Controlled stop case:
      STARTED -> STOPPING -> STOPPED
```

This is a general diagram. Some statuses may exist only very briefly or appear only in specific operational situations. Not every execution lets you observe all of the intermediate statuses.

### STARTING — The Step Is Being Prepared

`STARTING` indicates that the StepExecution has been created and the launch is being prepared. Spring Batch sets up the execution information, associates the StepExecution with the JobExecution, and prepares to move on to executing the Step.

This status is usually only a short phase. In the normal execution flow, the Step soon moves to `STARTED`. If a monitoring system reads the metadata right at the moment of launch, it can observe `STARTING`.

### STARTED — The Step Is Running

`STARTED` indicates that the Step has started doing its work. Spring Batch records the start time and updates the metadata. Depending on the type of Step, the work may be running a `Tasklet`, or iterating over items in the chunk-oriented processing model.

While the Step is running, the necessary counters and state are updated. With chunk processing, after each successful chunk commit, the framework saves the progress and the appropriate checkpoint in the JobRepository. If a Step processes a large amount of data, the `STARTED` status can last quite a long time.

When you see a Step in the `STARTED` status, the operator needs to distinguish a Step that is truly still running from stale metadata left over after the process was stopped abruptly. Do not launch another execution for the same JobInstance just because the run time seems long; first check the process and the current JobExecution state.

### COMPLETED — The Step Completed Successfully

`COMPLETED` indicates that the Step ended following a successful execution flow. Spring Batch records the end time, updates the metadata, and allows the Job to move on to the next Step or to finish if this is the last Step.

`COMPLETED` does not necessarily mean every input record was written to the destination. For example, a Step can be configured to skip some invalid items. The Step can still complete with the `COMPLETED` status while `skipCount` is greater than 0. Therefore, you need to look at the counters and the business results too, not only at the status.

When a Job is restarted, a Step that is `COMPLETED` is usually skipped to avoid re-running work that has already been completed. You can change that behavior with the `allowStartIfComplete(true)` configuration when you really need to redo a completed Step.

### FAILED — The Step Failed

`FAILED` indicates that the Step could not complete normally because it encountered an error. The cause can be an exception in the reader, processor, or writer; a database connection error; invalid input data; or an error from a dependent service.

Spring Batch stores the failed status along with the exception information and the related counters. The Job usually moves to a failed status unless another flow is configured for the Step's result.

When a Step processes by chunk, the chunks committed before the point of failure remain in the database. The chunk that is inside a transaction is rolled back if that transaction fails. Therefore, the number of items read can be greater than the number of items written successfully. On restart, Spring Batch can continue from the saved checkpoint if the reader and Step support state recovery.

`FAILED` does not mean the entire Job must always be run from the beginning. If the Job allows restart and the metadata is still complete, the operator can fix the cause and then restart the same JobInstance. Spring Batch will rely on the state of each Step to determine which part needs to continue.

## 3. Other Statuses to Know

Besides the main statuses above, `BatchStatus` has some values that serve stopping and handling special situations:

| Status | Meaning |
|---|---|
| `STOPPING` | The Step is in the process of stopping on request; the framework needs to complete the stop safely |
| `STOPPED` | The Step has stopped in a controlled way; the Job can be restarted if the configuration and state allow it |
| `ABANDONED` | The StepExecution is marked as not to be continued; on restart, the corresponding Step may be skipped |
| `UNKNOWN` | The execution result cannot be determined with certainty; the metadata and the business impact must be investigated before continuing |

`STOPPING` usually appears when there is a request to stop a running Job or Step. The framework tries to bring the work to a safe boundary to end. `STOPPED` is different from `FAILED`: stopping is a deliberate action, while failure is a result caused by an error.

`ABANDONED` is typically used in operational processes to mark an execution that should not be restarted. This is a status that must be used deliberately because it affects how Spring Batch handles the Step when the Job is re-run.

`UNKNOWN` needs to be considered carefully. It can reflect a situation where the framework cannot determine the final status, such as a serious error while saving metadata. Do not automatically restart or delete metadata to get around this status; first cross-check the data that was written and verify the side effects of the previous run.

## 4. How Does the Lifecycle of a Step Unfold?

For an ordinary Step, the general sequence consists of the following phases:

1. **Job starts:** the JobLauncher launches the Job and the JobRepository creates or looks up the JobInstance and JobExecution.
2. **Job chooses a Step:** the Job's flow determines the next Step to run. A Step that has completed can be skipped on restart.
3. **StepExecution is created:** Spring Batch creates the object that tracks the Step execution and associates it with the JobExecution.
4. **Execution starts:** the status moves to `STARTED`, and the start time and metadata are updated.
5. **The work is performed:** the Tasklet or the read, process, and write cycle for items is run. The counters and checkpoints are updated as progress is made.
6. **End:** if the work succeeds, the Step moves to `COMPLETED`; if there is an unhandled error, the Step moves to `FAILED`; if there is a stop request, the Step may go through `STOPPING` to `STOPPED`.
7. **Metadata update:** the end time, status, ExitStatus, exception, and ExecutionContext are saved for monitoring or restart.

Listener callbacks let the application attach logic at appropriate milestones, such as logging when the Step starts or collecting metrics after the Step ends.

## 5. Example of Defining a Step and Monitoring Its Status

The following code illustrates a Step that uses a Tasklet in Spring Batch 5:

```java
@Bean
Step validateFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validateFileTasklet) {

    return new StepBuilder("validateFileStep", jobRepository)
            .tasklet(validateFileTasklet, transactionManager)
            .build();
}
```

When the Job executes this Step, Spring Batch manages the StepExecution and updates the corresponding status. The application can use a `StepExecutionListener` to observe the lifecycle:

```java
public class StepLoggingListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        System.out.println(
                "Starting step: " + stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        System.out.println(
                "Step status: " + stepExecution.getStatus());
        System.out.println(
                "Read count: " + stepExecution.getReadCount());
        System.out.println(
                "Write count: " + stepExecution.getWriteCount());
        System.out.println(
                "Skip count: " + stepExecution.getSkipCount());

        return null;
    }
}
```

In `afterStep`, returning `null` means the listener does not request a change to the current ExitStatus. A listener can return a different ExitStatus to supplement the result for the Job flow, but you need to do this deliberately because the ExitStatus can affect the next step.

A listener can be attached to the Step when building it:

```java
@Bean
Step validateFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validateFileTasklet,
        StepLoggingListener stepLoggingListener) {

    return new StepBuilder("validateFileStep", jobRepository)
            .tasklet(validateFileTasklet, transactionManager)
            .listener(stepLoggingListener)
            .build();
}
```

In a real application, you should use a logger instead of `System.out.println`, and attach the JobExecution ID and StepExecution ID to the log so that you can trace a specific run.

## 6. BatchStatus and ExitStatus Are Not the Same

These two concepts often appear together but serve two different purposes:

- **`BatchStatus`:** the lifecycle status managed by Spring Batch, for example `STARTED`, `COMPLETED`, `FAILED`, or `STOPPED`.
- **`ExitStatus`:** the result code that the Step returns to describe the execution result and to help control the Job flow. ExitStatus can contain a default exit code or a custom code.

For example, a Step can have `BatchStatus.COMPLETED` while a listener sets the ExitStatus to `COMPLETED_WITH_WARNINGS` so that the Job branches to a Step that checks the warnings. This is useful when the work has completed technically but the business needs to process further based on the result.

In a Job flow, the transition conditions are usually declared by the Step's exit code. An illustrative example:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importStep,
        Step notifyFailureStep,
        Step createReportStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(importStep)
                .on("FAILED").to(notifyFailureStep)
            .from(importStep)
                .on("*").to(createReportStep)
            .end()
            .build();
}
```

The flow above illustrates choosing the next Step by ExitStatus. When building a real flow, you need to declare all the necessary branches and check how the Job ends in each branch. A custom ExitStatus must match the declared transition conditions.

## 7. Monitoring a Step Through Metadata and Counters

Looking only at the `COMPLETED` or `FAILED` status is usually not enough to understand what a Step did. `StepExecution` also stores information that is useful for operations:

| Property | Meaning |
|---|---|
| `startTime` | The time the Step started |
| `endTime` | The time the Step ended |
| `lastUpdated` | The time the StepExecution metadata was most recently updated |
| `readCount` | Number of items read |
| `writeCount` | Number of items written |
| `filterCount` | Number of items filtered out by the processor |
| `readSkipCount` | Number of items skipped because of read errors |
| `processSkipCount` | Number of items skipped because of processing errors |
| `writeSkipCount` | Number of items skipped because of write errors |
| `commitCount` | Number of times the chunk's transaction was committed |
| `rollbackCount` | Number of rollbacks recorded |
| `failureExceptions` | The exceptions related to a failed execution |
| `executionContext` | The state stored to support resuming or restarting |

The counters help detect problems. For example, if `readCount` is high but `writeCount` is low, you need to look at `filterCount`, the skip counts, and the logs to understand whether the data was filtered or had errors. If the run time spikes, you may need to check the database, the source system, the target system, or the chunk size.

`JobRepository` stores the metadata for monitoring and restart. An application can query execution information through APIs such as `JobExplorer` or through monitoring interfaces built on that metadata. Keep the metadata durable in environments that need to track history or recover after the application restarts.

## 8. How Does Step Status Affect Restart?

The final status of a Step determines how Spring Batch handles the Step when the Job is restarted:

| Previous status | Common behavior on restart |
|---|---|
| `COMPLETED` | Skip the completed Step, unless `allowStartIfComplete(true)` is configured |
| `FAILED` | The Step can be executed again within the old JobInstance if the Job allows restart and the Step's limit has not been exceeded |
| `STOPPED` | The Job can be continued from the saved state if the configuration allows it |
| `ABANDONED` | The Step is marked as not to be continued in the restart |
| `UNKNOWN` | Needs manual handling and state verification before continuing |
| `STARTED` | May be running; the current execution needs to be verified before taking any action |

With a chunk-oriented Step, the checkpoint in the ExecutionContext lets the reader continue from the saved position. Chunks that were committed are retained; chunks that were not committed may have to be processed again. This works correctly only when the reader can save its state, the input data is stable, and the write operations are safe on retry.

If a Step calls an external service, sends an email, or writes a file, those side effects may not be inside the chunk's database transaction. A re-run may repeat an operation that happened before the process was stopped. Therefore, you need to use an idempotency key, a unique constraint, a transactional outbox, or a reconciliation mechanism appropriate to the business.

## 9. Common Mistakes When Reading Step Status

**Confusing `FAILED` with `STOPPED`:** `FAILED` indicates an error that prevented the Step from completing normally; `STOPPED` indicates a controlled stop. The remediation and the restart decision may differ.

**Assuming `COMPLETED` means there are no error records:** a Step that allows skips can still complete. You need to look at the skip count and the business results.

**Assuming a `STARTED` Step is definitely still active:** if the process is killed or the server has an incident, the metadata may not yet reflect the final state. Verify the process before launching again.

**Looking only at the Job status and ignoring the StepExecution:** a failed Job may be caused by a specific Step. Checking the StepExecution helps pinpoint the location and the cause.

**Treating BatchStatus and ExitStatus as one:** BatchStatus describes the lifecycle; ExitStatus describes the result code and can control the flow. Changing the ExitStatus does not mean changing the BatchStatus.

**Deleting metadata to clean up the state:** the metadata contains history and checkpoint information. Deleting it arbitrarily can destroy the ability to restart and leave the application not knowing which portion of the data has been processed.

## Conclusion

The Step lifecycle is tracked through `StepExecution`. A Step begins in the `STARTING` phase, moves to `STARTED` when executing, and then usually ends in `COMPLETED` or `FAILED`; it can also stop in a controlled way through `STOPPING` and `STOPPED`. `BatchStatus` gives the lifecycle state, while `ExitStatus` provides the result code used for flow control. When operating, look at the status, counters, exceptions, and checkpoints in the JobRepository together to understand exactly how far the Step has processed and whether it can be restarted safely.
