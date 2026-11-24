# Restarting a flow after a failed step

A Job in Spring Batch typically consists of multiple Steps connected sequentially or branching based on execution outcomes. When a Step fails, the Job can end in the FAILED status. If the Job is designed to allow restarts, the next run can resume from the incomplete Step without re-executing Steps that already completed.

Restarting a flow is how Spring Batch recovers execution flow based on metadata persisted in `JobRepository`. For this to work properly, the application must preserve `JobInstance` identity, understand each Step's state, design appropriate transitions, and ensure re-executed operations are safe.

## 1. Distinguishing JobInstance, JobExecution, and StepExecution

These three concepts determine how Spring Batch recovers a Job:

| Concept | Role |
| --- | --- |
| **JobInstance** | Represents a logical processing run, identified by Job name and identifying `JobParameters` |
| **JobExecution** | A specific execution attempt of a `JobInstance`; restarting creates a new `JobExecution` |
| **StepExecution** | A specific execution attempt of a Step within a `JobExecution` |

Example of a daily order import Job:

~~~text
Job: dailyOrderImport
JobParameters: businessDate=2026-11-15
        |
        v
JobInstance A
        |
        +-- JobExecution #1: FAILED
        |       |
        |       +-- prepareInput: COMPLETED
        |       +-- importOrders: FAILED
        |       +-- publishReport: not run yet
        |
        +-- JobExecution #2: STARTED -> COMPLETED
                |
                +-- prepareInput: skipped
                +-- importOrders: re-run and COMPLETED
                +-- publishReport: runs
~~~

The second `JobExecution` belongs to the same `JobInstance` A because the Job name and identifying parameters did not change. `JobRepository` stores the history of both execution attempts and their associated `StepExecution`s.

Do not equate restarting with creating a new `JobInstance`. Restarting continues the same logical scope previously identified. If you change identifying `JobParameters`, Spring Batch can create a different `JobInstance`, and the new instance will not inherit the state of the old instance.

## 2. Conditions for restarting a Job

Restarting is only possible when the previous `JobInstance` has not completed successfully and the Job is allowed to restart.

Key conditions:

- The Job has the same name as the previous run.
- Identifying `JobParameters` match the `JobInstance` to be restarted.
- The Job is not configured with `preventRestart()`.
- The previous `JobExecution` ended in a restartable status, typically FAILED or STOPPED.
- The Steps that need to re-run have not exceeded `startLimit`.
- Readers/writers or Tasklets have appropriate recovery mechanisms if checkpoints are needed.

If the `JobInstance` is already COMPLETED, launching again with the same identifying parameters is normally rejected with `JobInstanceAlreadyCompleteException`. If the previous `JobExecution` is still running, a duplicate request may be rejected with `JobExecutionAlreadyRunningException`.

### Keeping JobParameters consistent on restart

Suppose the first run used:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFileId", "orders-2026-11-15", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
~~~

On restart, keep the identifying values identical:

~~~java
JobParameters restartParameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFileId", "orders-2026-11-15", true)
        .addString("requestedBy", "operator", false)
        .toJobParameters();
~~~

`requestedBy` is non-identifying, so it can change without creating a new `JobInstance`. However, do not change a non-identifying parameter if business logic depends on it to decide which data to process. Values that alter data scope must be designed as identifying.

Do not add a new timestamp or UUID to the identifying group merely to bypass the COMPLETED state. If a new business run is required, use a meaningful new revision or business key.

## 3. Restart in a Job with sequential Steps

In a linear Job, Spring Batch records the status of each Step:

~~~java
@Bean
public Job dailyImportJob(
        JobRepository jobRepository,
        Step prepareInputStep,
        Step importOrdersStep,
        Step publishReportStep) {

    return new JobBuilder("dailyImportJob", jobRepository)
            .start(prepareInputStep)
            .next(importOrdersStep)
            .next(publishReportStep)
            .build();
}
~~~

Suppose:

- `prepareInputStep` completes.
- `importOrdersStep` fails.
- `publishReportStep` has not run yet.

The `JobExecution` ends FAILED. When restarting the same `JobInstance`, Spring Batch normally skips `prepareInputStep` because the Step is already COMPLETED, re-executes `importOrdersStep`, and runs `publishReportStep` only after the import succeeds.

~~~text
First run:

prepareInputStep  ----> COMPLETED
        |
        v
importOrdersStep  ----> FAILED
        |
        v
publishReportStep ----> not run yet

Restart same JobInstance:

prepareInputStep  ----> skipped (already COMPLETED)
        |
        v
importOrdersStep  ----> re-run
        |
        v
publishReportStep ----> runs after import succeeds
~~~

This is the basic restart behavior. `JobRepository` supplies execution history so Spring Batch determines which Steps have finished and which Steps need to execute again.

## 4. Does a completed Step run again?

By default, a Step that is already COMPLETED is normally skipped when restarting a Job. This avoids repeating operations that already finished.

If a Step needs to run again on every restart, you can configure `allowStartIfComplete(true)`:

~~~java
@Bean
public Step prepareInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        PreparationService preparationService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        preparationService.prepareWorkspace();
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("prepareInputStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
~~~

With this configuration, the Step can execute again even if the previous execution was COMPLETED. Use it only when the operation is safe to repeat, such as validating or preparing a workspace idempotently.

Do not enable `allowStartIfComplete(true)` indiscriminately on Steps that send emails, move files, write records, or emit messages. Those operations can cause duplicate side effects when the Job restarts.

## 5. Flow transitions when a Step fails

A Job flow can branch based on a Step's `ExitStatus`. In the Java DSL, `on(...)` specifies the `ExitStatus` pattern used to select a transition.

For example, if import fails, the Job runs a failure-recording Step and then ends with a failed status:

~~~java
@Bean
public Job orderImportJob(
        JobRepository jobRepository,
        Step prepareInputStep,
        Step importOrdersStep,
        Step recordFailureStep,
        Step publishReportStep) {

    return new JobBuilder("orderImportJob", jobRepository)
            .start(prepareInputStep)
                .on("FAILED").fail()
            .from(prepareInputStep)
                .on("*").to(importOrdersStep)
            .from(importOrdersStep)
                .on("FAILED").to(recordFailureStep)
            .from(importOrdersStep)
                .on("*").to(publishReportStep)
            .from(recordFailureStep)
                .on("*").fail()
            .from(publishReportStep)
                .on("*").end()
            .end()
            .build();
}
~~~

This flow has the following branches:

- `prepareInputStep` fails: Job ends FAILED.
- `prepareInputStep` succeeds: move to `importOrdersStep`.
- `importOrdersStep` fails: run `recordFailureStep`.
- `recordFailureStep` completes: flow ends FAILED.
- `importOrdersStep` succeeds: move to `publishReportStep` and then finish normally.

Calling `fail()` makes the flow end in a failed status. When a `JobExecution` fails, the `JobInstance` can be restarted if restart conditions are met.

### Order of transition declarations

`ExitStatus` patterns should be declared from specific to general. For instance, `FAILED` is more specific than `*`. If a wildcard branch is matched prematurely in an improper setup, the failure branch may not route as expected.

`on("FAILED")` matches the Step's `ExitStatus` code. It does not directly check the `BatchStatus` enum, even though in a typical Step failure the default `ExitStatus` also has code `FAILED`.

## 6. Distinguishing FAILED, END, and COMPLETED in flows

An important point is that flow transitions can alter the Job's final outcome. A Step with `ExitStatus` FAILED does not necessarily cause the Job to always end FAILED if the flow is configured to handle that branch and terminate normally.

Common transitions:

| Transition | Meaning |
| --- | --- |
| on("FAILED").fail() | Ends the Job flow with a failed status |
| on("FAILED").to(recoveryStep) | Transitions to a recovery Step |
| on("*").to(nextStep) | Transitions to the next Step for remaining exit codes |
| on("COMPLETED").end() | Ends the flow along the completed branch |
| on("FAILED").stopAndRestart(restartStep) | Stops the Job and records the position to restart from the specified Step |

If the failure branch moves to `recoveryStep` and `recoveryStep` completes, the flow can move to another branch or terminate normally. Once a Job finishes COMPLETED, the same `JobInstance` normally cannot be restarted like a failed Job. Therefore, decide the goal clearly:

- Record the error while still treating the Job as complete from a business standpoint.
- Perform recovery and continue the Job.
- End the Job FAILED so an operator fixes the root cause and restarts.
- Stop the Job in STOPPED state and resume from a designated Step.

Do not use `end()` if the real intent is for the Job to be restartable after a failure. `end()` closes the flow in a completed status; `fail()` indicates the Job failed.

## 7. Using a recovery Step in the flow

A recovery Step can perform tasks such as:

- Recording the error code and business key.
- Moving faulty input to a quarantine area.
- Recording batch status for operational investigation.
- Sending alerts through a controlled mechanism.
- Preparing data so a subsequent restart can resume.

Example recovery Step recording failure details:

~~~java
@Bean
public Step recordFailureStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FailureAuditService auditService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        StepExecution currentStep =
                contribution.getStepExecution();

        auditService.recordFailure(
                currentStep.getJobExecutionId(),
                currentStep.getStepName(),
                currentStep.getExitStatus().getExitCode());

        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("recordFailureStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
~~~

In practice, the current `StepExecution` here is that of `recordFailureStep`, not the `importOrdersStep` that failed. To obtain details of the failed Step, look up the `StepExecution`s belonging to the current `JobExecution` via `JobExecution` or `JobExplorer` and select the specific Step to inspect.

If `recoveryStep` completes yet the flow subsequently calls `fail()`, the Job still ends FAILED. On restart, Spring Batch re-evaluates the flow from persisted execution state. Already COMPLETED Steps such as `prepareInputStep` or `recordFailureStep` are normally skipped; the failed Step executes again.

Recovery Steps should be idempotent. If the Step runs again due to another execution or flow design, recording the error should not produce duplicate records or unintended repeated notifications.

## 8. Using stopAndRestart when stopping at a specific point

Some Jobs should not immediately be marked FAILED, but instead need a controlled stop for operator review. You can use `stopAndRestart(...)` to end the Job in STOPPED status and record the restart position.

Example:

~~~java
return new JobBuilder("controlledImportJob", jobRepository)
        .start(validateInputStep)
            .on("FAILED").stopAndRestart(validateInputStep)
        .from(validateInputStep)
            .on("*").to(importOrdersStep)
        .from(importOrdersStep)
            .on("*").end()
        .end()
        .build();
~~~

This example merely illustrates the stop transition and restart position. Choose a restart Step suited to the data state. When the Job is STOPPED, the next run can resume at the recorded position after the cause of the stop is resolved.

`stopAndRestart` is not the same as `fail()`:

- `fail()` ends the Job with FAILED status.
- `stopAndRestart(step)` ends the Job in STOPPED status and specifies where the flow resumes on restart.
- `end()` ends the flow in a completed state.

Do not use STOPPED merely to mask technical errors. Use it when the workflow has an intentional pause/wait stage, such as waiting for approval or operator intervention.

## 9. startLimit and allowStartIfComplete

These two attributes directly affect restart flows:

**startLimit** limits how many times a Step is allowed to start. If the start count exceeds the limit, Spring Batch can throw `StartLimitExceededException`.

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .startLimit(3)
        .build();
~~~

In this example, the Step is allowed to start at most three times per the configured limit. Account for prior execution attempts during restart operations; avoid setting the limit too low if the workflow requires multiple recoveries.

**allowStartIfComplete** lets an already completed Step re-run when the Job restarts:

~~~java
return new StepBuilder("refreshReferenceDataStep", jobRepository)
        .tasklet(refreshTasklet, transactionManager)
        .allowStartIfComplete(true)
        .build();
~~~

The two properties solve different problems: `startLimit` caps start attempts, whereas `allowStartIfComplete` decides whether a COMPLETED Step runs again.

## 10. Flow restart and ExecutionContext

`JobRepository` stores metadata for `JobExecution`, `StepExecution`, and `ExecutionContext`. `ExecutionContext` lets components persist the progress needed to resume after a restart.

In a chunk-oriented Step, a reader can implement `ItemStream` to save checkpoints:

- `open(ExecutionContext)`: restores position or state.
- `update(ExecutionContext)`: saves current state at chunk boundaries.
- `close()`: releases resources.

Example of `FlatFileItemReader` supporting state persistence:

~~~java
@Bean
public FlatFileItemReader<OrderInput> orderReader(Resource inputFile) {
    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .delimited()
            .names("orderId", "customerCode", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

If a Step fails mid-chunk, the uncommitted chunk may have to be read and processed again. The reader can recover from the most recently committed checkpoint if state was saved and the data source remains stable.

Custom Tasklets do not automatically get fine-grained checkpoints. If a Tasklet performs partial work before throwing an exception, persist progress in `ExecutionContext` or a durable state store and keep checkpoints consistent with business data.

### Keeping input stable between runs

Checkpoints by line number or offset are accurate only if the file is not replaced. For databases, key-based checkpoints require a stable query ordering. If the source changes between the initial run and restart, the reader may skip or duplicate data.

You can use a file ID/version, snapshot, watermark, or keyset checkpoint so that restarts read the exact same data scope.

## 11. Restarting flows with multiple branches

In complex Jobs, a Step may branch by `ExitStatus` or the outcome from a `JobExecutionDecider`. On restart, the flow is re-evaluated based on persisted execution state and data.

Example flow:

~~~text
                  +----------------------+
                  |                      |
                  v                      |
prepareInput -> importOrders ------------+
                  |
                  +-- COMPLETED --> publishReport --> END
                  |
                  +-- FAILED ----> recordFailure --> FAIL
~~~

If `importOrders` fails and `recordFailure` completes, the Job still ends FAILED per the configured branch. When restarting the same `JobInstance`:

- `prepareInput` is already COMPLETED so it is usually skipped.
- `importOrders` is the failed Step so it runs again.
- If `importOrders` succeeds, the flow takes the success branch to `publishReport`.
- `recordFailure`, already COMPLETED from the prior execution, normally does not run again because the success flow does not enter the failure branch.

This is why flows must be designed to re-evaluate cleanly from a failed Step. Auxiliary Steps should be idempotent because they may be re-executed under different circumstances.

### JobExecutionDecider

If a flow branch depends on business data or persisted state, you can use `JobExecutionDecider` to determine the flow status:

~~~java
public class ImportDecision implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        boolean hasRejectedData =
                jobExecution.getExecutionContext()
                        .getBoolean("hasRejectedData", false);

        return hasRejectedData
                ? new FlowExecutionStatus("HAS_REJECTED")
                : FlowExecutionStatus.COMPLETED;
    }
}
~~~

The decider returns a `FlowExecutionStatus` to pick the next transition. When using a decider in a restartable flow, the data the decider relies on must be durably persisted and consistent. Do not rely on static variables or in-memory-only state because restarts can run on another process or node.

## 12. Restart and side effects

Restarting can re-execute a failed Step. If the Step writes data, sends messages, calls APIs, or creates files, re-execution can produce duplicate side effects.

Example:

~~~text
importOrdersStep:
  1. write 500 orders to database
  2. send notification to another system
  3. error before Step completes

Restart:
  Step re-runs
  -> risk of duplicate writes or sending notification a second time
~~~

To prevent errors:

- Use business keys or unique constraints to prevent duplicate writes.
- Design idempotent writers.
- Use an outbox to record events in the same data transaction.
- Use stable idempotency keys for external APIs.
- Record operation status to track which side effects already completed.
- Separate non-rollbackable operations from database transactions and design reconciliation mechanisms.

Database transaction rollbacks do not automatically recall HTTP requests, sent emails, emitted messages, or moved files. Flow restart only controls Step ordering; side-effect safety remains the application's design responsibility.

## 13. Restarting a Job via API

You can use `JobOperator` to restart a `JobExecution` that ended in a restartable state:

~~~java
long failedExecutionId = 12345L;
long newExecutionId =
        jobOperator.restart(failedExecutionId);
~~~

The specific API may throw exceptions related to a non-existent `JobExecution`, an already completed `JobInstance`, a non-restartable Job, or invalid `JobParameters`. Handle those cases in the orchestration layer and surface clear info to operators.

Another approach is calling `JobLauncher` with the same Job and identifying `JobParameters` when the prior execution was FAILED or STOPPED:

~~~java
JobExecution execution =
        jobLauncher.run(dailyImportJob, originalParameters);
~~~

If the old `JobInstance` is eligible for restart, `JobRepository` creates a new `JobExecution` for that instance. If the instance is already COMPLETED or currently running, the request can be rejected.

Do not generate new identifying parameters when the goal is a restart. In production operations, store the execution ID, business key, and identifying parameters so you can look up the exact execution to restart.

## 14. Observing flows and restart history

`JobExplorer` provides metadata-reading APIs to inspect `JobInstance`, `JobExecution`, and `StepExecution` history.

Example querying the `StepExecution`s of a `JobExecution`:

~~~java
JobExecution execution =
        jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    for (StepExecution stepExecution : execution.getStepExecutions()) {
        log.info(
                "step={}, status={}, exitStatus={}, read={}, write={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getExitStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount());
    }
}
~~~

When investigating a restart, cross-check:

- `JobInstance` ID and identifying `JobParameters`.
- `JobExecution` ID, `BatchStatus`, and `ExitStatus`.
- `StepExecution` for each Step across runs.
- Which Steps are COMPLETED, FAILED, or STOPPED.
- Persisted `ExecutionContext` and checkpoints.
- Which flow transition was selected after `ExitStatus`.
- The root exception and executed side effects.

You can query metadata tables to support operations, but do not directly update or delete rows to force a Job restart. Manually editing metadata can break foreign-key relationships, states, and checkpoints.

## 15. Common mistakes

### Changing identifying parameters on restart

`JobRepository` treats a new parameter set as a different `JobInstance`. Keep the Job name and identifying parameters identical when restarting an old instance.

### Using end() for a branch that needs restarting

`end()` terminates the flow in a completed status. If the goal is to leave the Job FAILED and restartable, use an appropriate `fail()` transition.

### Confusing ExitStatus with BatchStatus

Flow `on(...)` matches `ExitStatus` code. `BatchStatus` describes the execution lifecycle. The two statuses often align but are not the same concept.

### Completed Step re-running unexpectedly

Check `allowStartIfComplete(true)`. Enable it only when the Step needs to re-run and its operations are idempotent.

### Failed Step exceeding allowed run attempts

Check `startLimit`. If the limit is exceeded, Spring Batch can throw `StartLimitExceededException`.

### Recovery Step making the Job COMPLETED when restart is needed

If the error branch passes through `recoveryStep` and ends with `end()`, the Job may be marked completed. If operators need to fix the issue and restart, end the branch with `fail()` or design `STOPPED` intentionally.

### Flow wildcard shadowing the failure branch

Declare specific transitions like `FAILED` before wildcards. Check the Step's actual `ExitStatus` to ensure patterns match.

### Re-running Step causing duplicate side effects

Restarting does not automatically undo API calls, messages, or files already created. Use idempotency keys, unique keys, outbox, or compensation.

### Reader failing to restore checkpoint

Custom readers must support `ItemStream` or a durable checkpoint mechanism. Inputs must also remain stable between the first run and restart.

### Recovery logic relying on in-memory state

Restarts can execute on a different process or node. Use `JobRepository`, `ExecutionContext`, or a durable state store instead of static variables or singleton state.

## 16. Process for designing restartable flows

When building a restartable Job, establish:

1. Which identifying parameters uniquely identify a `JobInstance`?
2. Which Steps can fail and which Steps need to re-run?
3. Do any COMPLETED Steps need to re-run?
4. Does the FAILED branch end the Job, transition to recovery, or stop awaiting operations?
5. Does the recovery Step need to re-run on restart and is it idempotent?
6. Is `startLimit` large enough for the expected number of recovery attempts?
7. Where do readers/Tasklets save checkpoints, and are checkpoints consistent with committed data?
8. How are out-of-transaction side effects protected against duplication?
9. Which `ExitStatus` do flow transitions rely on, and are wildcards ordered properly?
10. Which `JobExecution` ID do operators look up and restart?

Test at least these scenarios: first Step fails, middle Step fails, recovery Step fails, successful restart, completed Step skipped, Step with `allowStartIfComplete`, and restart exceeding `startLimit`.

## Conclusion

Restarting a flow after a failed Step relies on `JobRepository` metadata, `StepExecution` statuses, and the same `JobInstance` identified by Job name plus identifying `JobParameters`. On restart, Spring Batch normally skips already COMPLETED Steps and re-runs failed Steps; `allowStartIfComplete` and `startLimit` adjust this behavior. Flow transitions use `ExitStatus` to pick branches: `fail()` leaves the Job in FAILED status so it can be restarted, a recovery Step can record or handle errors, and `end()` finishes the flow as completed. Safe restarts require durable checkpoints, stable inputs, and idempotent side effects.
