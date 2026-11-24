# BatchStatus of JobExecution

In Spring Batch, `JobExecution` represents a specific execution attempt of a job. The `BatchStatus` attribute indicates which stage that execution is in or what state it ended with: starting, running, stopping, completed, failed, or marked as unable to continue.

When monitoring a batch job, `BatchStatus` is the first piece of information to know whether the job is still running or has finished. However, this status does not fully describe the business outcome. A job can have `BatchStatus.COMPLETED` even if some items were skipped according to policy; a job can have a failed step while the flow is configured to end along a completed branch. Therefore, you should read `JobExecution.getStatus()` together with `ExitStatus`, individual step statuses, and business data.

## 1. JobExecution and BatchStatus

A `JobInstance` represents a logical business run identified by the job name and identifying `JobParameters`. Each time the job is launched or restarted, Spring Batch creates a separate `JobExecution` for that instance.

For example, a file import job for business date 2026-11-14 may have:

| Object | Meaning |
|---|---|
| `JobInstance` | Job `importOrdersJob` with `businessDate=2026-11-14` |
| `JobExecution` 101 | First run, failed at the data writing step |
| `JobExecution` 102 | Restart run, completed successfully |

Both `JobExecution` instances belong to the same `JobInstance`, but each has its own ID and status. `BatchStatus` is attached to each execution, not a single permanent status stored on `JobInstance`.

In code, you can read the status of an execution:

~~~java
JobExecution execution = jobLauncher.run(job, jobParameters);

BatchStatus status = execution.getStatus();
log.info("Job execution {} status={}", execution.getId(), status);
~~~

If the job runs synchronously, the `run()` call usually returns after the execution finishes. If an asynchronous launcher is used, the returned object may still be in a running state; you must look up the latest status from `JobExplorer`.

## 2. BatchStatus Values

`BatchStatus` is an enum defined by Spring Batch. Common statuses include:

| BatchStatus | Meaning |
|---|---|
| `STARTING` | Execution has been created and is in the startup phase |
| `STARTED` | Job or step is currently executing |
| `STOPPING` | A stop request has been issued and the framework is processing it |
| `STOPPED` | Execution has stopped |
| `COMPLETED` | Execution completed according to the framework flow and execution mechanism |
| `FAILED` | Execution ended due to an error that was not handled successfully |
| `ABANDONED` | Execution has been marked abandoned and cannot continue via normal restart |
| `UNKNOWN` | Execution status cannot be determined reliably |

These statuses describe the framework lifecycle. They are not custom codes for individual business outcomes. If you need to distinguish `COMPLETED_WITH_WARNINGS`, `COMPLETED_WITH_SKIPS`, or `NO_DATA`, use `ExitStatus` or a separate business status.

## 3. State Lifecycle of JobExecution

A typical execution passes through the starting, running, and ending phases:

~~~mermaid
stateDiagram-v2
    [*] --> STARTING
    STARTING --> STARTED
    STARTED --> COMPLETED
    STARTED --> FAILED
    STARTED --> STOPPING
    STOPPING --> STOPPED
    STOPPED --> [*]
    COMPLETED --> [*]
    FAILED --> [*]
    ABANDONED --> [*]
    UNKNOWN --> [*]
~~~

The diagram illustrates common branches, not every internal state transition that can occur in every version or recovery scenario. For example, `ABANDONED` is usually the result of an administrative operation, while `UNKNOWN` is typically associated with situations where it is impossible to confirm where the execution ended.

Practical meaning:

- `STARTING` and `STARTED` indicate the job does not yet have a final outcome.
- `STOPPING` indicates a stop request is being processed; the job should not yet be considered stopped.
- `STOPPED`, `FAILED`, and `COMPLETED` are terminal statuses commonly observed in operations.
- `ABANDONED` and `UNKNOWN` must be handled carefully because they affect restart capability.

You should not rely on a single status read to conclude that a job has finished if the execution is in `STARTING`, `STARTED`, or `STOPPING`.

## 4. STARTING and STARTED

`STARTING` appears when Spring Batch has created the execution and is preparing to launch the job. The framework needs to initialize related components, check state, and start the flow.

`STARTED` indicates the job is executing. Steps may be running or waiting according to the flow structure. In a job with parallel flows, multiple steps can run concurrently while the JobExecution still holds a single overall status.

When an operational API observes an execution in `STARTING` or `STARTED`, it can return a running status and provide the execution ID for the client to query later. Do not launch a new execution simply because a final result is not yet visible; check whether the same `JobInstance` already has a running execution.

Example:

~~~java
if (execution.getStatus() == BatchStatus.STARTING
        || execution.getStatus() == BatchStatus.STARTED) {
    log.info("Job {} is still running", execution.getId());
}
~~~

In a multi-node system, `JobRepository` is the shared metadata source used to coordinate and prevent conflicting runs with the same identifier. Do not use an in-memory variable on a single node as the sole source of truth for job status.

## 5. STOPPING and STOPPED

`STOPPING` means a request to stop the execution has been made, but stopping has not yet completed. `STOPPED` is the status after the framework finishes processing the stop request.

You can request to stop a running execution through `JobOperator`:

~~~java
@Service
public class BatchControlService {

    private final JobOperator jobOperator;

    public BatchControlService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public boolean requestStop(long executionId) throws Exception {
        return jobOperator.stop(executionId);
    }
}
~~~

A stop request is usually a coordinated stop request, not a command that forcibly kills the thread immediately. A step may need to reach a safe point to finish a transaction or check the stop flag. Response time depends on the tasklet type, reader/writer, pending operations, and how components handle stopping.

For a chunk step, the framework usually has an opportunity to check the stop request at chunk processing boundaries. For a tasklet running a long loop or calling a slow external service, the code should be designed to check the stop status or have appropriate timeouts. Do not assume `JobOperator.stop()` will immediately interrupt an HTTP call or roll back an external side effect.

Once a stop request is accepted, the status may temporarily be `STOPPING`. Only when the execution actually finishes should it be treated as `STOPPED`.

## 6. COMPLETED

`COMPLETED` indicates the job execution ended along the flow as a completed run. This is the status commonly treated as success at the framework level.

However, `COMPLETED` alone does not prove:

- All source records were written.
- No items were filtered or skipped.
- Monetary totals, counts, or reconciliation checksums are correct.
- All side effects in APIs, files, or message brokers were confirmed.
- The outcome satisfies all business conditions.

For example, a step allows skipping up to 20 invalid lines. If only 3 lines are skipped, the step can complete normally and the job can reach `COMPLETED`. If the business requires every line to be imported, this is still an outcome that needs investigation or holding for review.

To determine completeness, combine:

- `JobExecution.getStatus()`.
- `JobExecution.getExitStatus()`.
- `StepExecution` and read/write/filter/skip counters.
- Reconciliation results and actual business data.

Once a `JobInstance` has completed, re-running with the same identifying `JobParameters` in the normal way does not create another execution to reprocess the same instance; Spring Batch typically rejects it with an instance-already-complete error. If you want to process a new business batch, you must use new identifying parameters appropriate for the new batch.

## 7. FAILED

`FAILED` indicates the job execution ended due to an error that was not handled successfully by the flow and step policy. Causes can be an exception in a reader, processor, writer, or tasklet, an initialization error, or an orchestration error.

When a job fails:

- One or more steps may have status `FAILED`.
- Previously `COMPLETED` steps may retain their committed data.
- The failing chunk is usually rolled back according to the transaction policy.
- Subsequent steps may not have run yet.
- Saved metadata and execution context are used to support investigation and restart.

Do not infer that `FAILED` means all data from the job was rolled back. Each chunk/step has its own transaction boundary; data committed before the error usually still persists.

You can read failures from the execution:

~~~java
JobExecution execution = jobExplorer.getJobExecution(executionId);
if (execution != null) {
    log.error("Job status={}, exit={}",
            execution.getStatus(),
            execution.getExitStatus());

    for (Throwable failure : execution.getAllFailureExceptions()) {
        log.error("Job failure", failure);
    }
}
~~~

A `FAILED` execution can usually be restarted if the job is configured as restartable, metadata state is valid, and step restart conditions are satisfied. If the job is declared non-restartable or a step has a policy preventing re-execution, follow a separate recovery procedure.

## 8. ABANDONED

`ABANDONED` indicates the execution has been marked as abandoned and should not be restarted through the normal process. This is usually an operational decision, for example when a failed execution has been determined to be impossible or undesirable to continue.

`ABANDONED` differs from `FAILED`:

- `FAILED` records a failed execution attempt; it can be restarted if configuration and state allow.
- `ABANDONED` indicates the execution has been actively excluded from the normal continuation workflow.

Do not mark an execution as abandoned just to clear an error status from a dashboard. Before abandoning, understand what data was committed, what side effects occurred, and how the business batch will be reprocessed.

Some operational situations may require abandoning the old execution and creating a new processing run with different identifying parameters or a different batch reference. This is a business decision requiring auditability, not a default workaround to bypass restart errors.

## 9. UNKNOWN

`UNKNOWN` indicates the framework or repository cannot determine the execution status reliably. This status requires caution because the application does not know for certain whether the job completed, failed, or was interrupted at some point.

Possible causes relate to:

- The JVM or host shutting down abruptly while updating metadata.
- Losing database connectivity at the exact moment of committing status.
- Inconsistent metadata or tampering outside Spring Batch mechanisms.
- Infrastructure errors preventing the framework from confirming the final outcome.

Do not automatically restart an `UNKNOWN` execution without investigation. If a side effect already occurred but metadata was not saved, re-running could create duplicate data. If data was not written, skipping the execution could leave missing data.

The handling procedure should include:

1. Check application logs and database logs around the time of the failure.
2. Read `JobExecution`, `StepExecution`, and execution context from `JobExplorer`.
3. Reconcile business data, outbox/messages, and output files.
4. Identify the last chunk/step that was definitely committed.
5. Perform recovery following an audited runbook; do not directly edit metadata tables to force statuses.

## 10. JobExecution BatchStatus vs. StepExecution BatchStatus

A job can consist of multiple steps. Each `StepExecution` has its own BatchStatus; `JobExecution` has a job-level BatchStatus. The two levels are related, but they are not always identical.

Example:

| Step | BatchStatus | Notes |
|---|---|---|
| `validateInputStep` | `COMPLETED` | Input validated |
| `importOrdersStep` | `FAILED` | Writer encountered an unhandled error |
| `reconcileStep` | No execution | Not run yet |
| JobExecution | `FAILED` | Flow ended due to error |

In a flow with conditional branches, the final job status also depends on transitions and how the flow ends. A step with a special exit code can lead to an `.end()`, `.fail()`, or `.stop()` branch. Therefore, you should not compute the job's BatchStatus by taking the last step's status or manually aggregating the enum from steps.

When investigating a job, read all `StepExecution` instances:

~~~java
for (StepExecution step : execution.getStepExecutions()) {
    log.info("Step {}: status={}, exitCode={}, reads={}, writes={}, skips={}",
            step.getStepName(),
            step.getStatus(),
            step.getExitStatus().getExitCode(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getSkipCount());
}
~~~

This helps identify which step actually failed, which steps completed, and which steps have not yet run.

## 11. BatchStatus vs. ExitStatus

`BatchStatus` is an enum describing the execution lifecycle. `ExitStatus` is a value object containing an exit code and an exit description. The exit code can be a standard value or a custom code set by the application.

| Criterion | BatchStatus | ExitStatus |
|---|---|---|
| Type | Enum | Value object |
| Purpose | Framework execution status | Exit code and outcome description |
| Values | STARTED, COMPLETED, FAILED, STOPPED... | COMPLETED, FAILED, COMPLETED_WITH_SKIPS... |
| Access | `getStatus()` | `getExitStatus()` |
| Used in flow | Not a string matched directly by `on(...)` | Exit code is used for transitions |

For example, a listener can set the exit code `COMPLETED_WITH_SKIPS` when a step has skips:

~~~java
@Override
public ExitStatus afterStep(StepExecution stepExecution) {
    if (stepExecution.getSkipCount() > 0
            && stepExecution.getStatus() == BatchStatus.COMPLETED) {
        return new ExitStatus("COMPLETED_WITH_SKIPS");
    }
    return null;
}
~~~

In this case, the step's BatchStatus can still be `COMPLETED`; the exit code merely adds information so the flow can choose the appropriate branch. `on("COMPLETED_WITH_SKIPS")` matches the exit code, not a new BatchStatus.

## 12. Impact of Flow Transitions on Final Job Status

The flow decides how the job ends after a step returns an exit status. Common transitions:

- `.to(nextStep)`: continue to another step/flow.
- `.end()`: end the flow along a completed branch.
- `.fail()`: end the flow with a failed outcome.
- `.stop()`: end the flow in a stopped state.

For example, a step with exit code `VALIDATION_REJECTED` can be handled according to business rules:

~~~java
return new JobBuilder("validateAndImportJob", jobRepository)
        .start(validateStep)
            .on("VALIDATION_REJECTED").end()
        .from(validateStep)
            .on("COMPLETED").to(importStep)
        .from(validateStep)
            .on("*").fail()
        .end()
        .build();
~~~

In the `.end()` branch, the flow can finish with a completed job status per the transition configuration, even if the preceding step had an exit code indicating rejected data. This is intentional behavior if the business considers rejecting invalid input a normally handled outcome. If you want the job marked as failed and restartable by policy, use an appropriate `.fail()` branch.

Similarly, `.stop()` is used when the job needs to end in a stopped state and be restartable from the configured point. Test the final status of `JobExecution`, rather than relying only on method names or step statuses.

## 13. Stopping and Restarting a Job

`STOPPED` usually means something different from `FAILED`: the job was requested to stop and terminated via the stop mechanism, rather than ending due to an unhandled error. A `STOPPED` execution can normally be restarted if the job and steps support restart.

Common workflow:

1. Job is in `STARTED`.
2. Operator calls `JobOperator.stop(executionId)`.
3. Job transitions to `STOPPING` while the framework processes the request.
4. Steps terminate at an appropriate safe point.
5. JobExecution transitions to `STOPPED`.
6. Operator restarts the same JobInstance with the original identifying parameters.

Restart does not necessarily re-run every step from the beginning. Spring Batch uses metadata and checkpoints to determine which steps completed and which step needs to resume. Completed steps are normally skipped during a standard restart, unless a configuration such as `allowStartIfComplete` requires re-execution.

Do not use `STOPPED` as a substitute for `FAILED` when there is a business error. Intentional stopping and failure are two distinct outcomes; dashboards and operational procedures must distinguish them.

## 14. Checking Status After Synchronous Execution

With a synchronous launcher, you can check the status immediately after `run()`:

~~~java
JobExecution execution = jobLauncher.run(job, parameters);

switch (execution.getStatus()) {
    case COMPLETED ->
            log.info("Job completed: {}", execution.getId());
    case FAILED ->
            log.error("Job failed: {}", execution.getId());
    case STOPPED ->
            log.warn("Job stopped: {}", execution.getId());
    default ->
            log.info("Job status is {}", execution.getStatus());
}
~~~

You should not use status alone to decide whether data is ready for downstream consumers. For `COMPLETED`, also check ExitStatus, skip count, reconciliation, and business batch state if output can be partial.

If the job launcher is configured asynchronously, the code above may execute while the execution is still `STARTING` or `STARTED`. In that case, return the execution ID and let the client poll the status later.

## 15. Querying Latest Status with JobExplorer

`JobExplorer` is a read-only API for querying metadata stored in `JobRepository`. It is useful for dashboards, status APIs, and operational tasks outside the thread that launched the job.

~~~java
@Service
public class JobStatusService {

    private final JobExplorer jobExplorer;

    public JobStatusService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public BatchStatus getStatus(long executionId) {
        JobExecution execution =
                jobExplorer.getJobExecution(executionId);

        if (execution == null) {
            throw new NoSuchElementException(
                    "JobExecution not found: " + executionId);
        }

        return execution.getStatus();
    }
}
~~~

When the launcher runs asynchronously, reload the execution by ID to read the latest status instead of holding onto the stale object from the request. `JobExplorer` reads metadata; do not modify status on the loaded object expecting changes to be written back to the repository.

A status API can return a DTO containing:

- `executionId`, `jobName`, `jobInstanceId`.
- `batchStatus` and `exitCode`.
- `startTime`, `endTime`, `lastUpdated`.
- Names and statuses of each step.
- Selected progress counters.

Do not return the entire ExecutionContext or exception payloads to users without proper access control and sensitive data filtering.

## 16. Checking Running Jobs and Avoiding Duplicate Launches

In an orchestration application, you may need to know whether a JobInstance already has a running execution. `JobExplorer` provides APIs to query instances/executions; `JobOperator` provides operational actions such as start, stop, restart, and abandon depending on configuration.

You should not check status only in a local variable before calling the launcher. Two nodes could simultaneously read that no job is running and both submit launch requests. `JobRepository` and Spring Batch's execution creation mechanism are responsible for managing identity and concurrency; the application needs to handle exceptions such as instance already running or instance already complete.

Example of checking status from the repository before displaying:

~~~java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution != null) {
    boolean running =
            execution.getStatus() == BatchStatus.STARTING
            || execution.getStatus() == BatchStatus.STARTED
            || execution.getStatus() == BatchStatus.STOPPING;

    if (running) {
        log.info("Execution {} has not reached a terminal state", executionId);
    }
}
~~~

This check serves display/troubleshooting purposes. It does not replace the concurrency control mechanism of `JobRepository` during launch.

## 17. Status and Restartability

BatchStatus is an important factor when deciding whether to restart, but not the only factor.

| Execution Status | Common Handling |
|---|---|
| `COMPLETED` | JobInstance has completed; do not restart the same instance via the normal path |
| `FAILED` | Can restart if job is restartable, metadata is valid, and step allows it |
| `STOPPED` | Can usually restart from saved state if configuration supports it |
| `ABANDONED` | Do not continue restarting this execution via the normal procedure |
| `UNKNOWN` | Requires investigation and controlled recovery before deciding |
| `STARTING` / `STARTED` | Running; do not treat as a finished execution for restart |
| `STOPPING` | Stop request in progress; wait for final status before restarting |

Other conditions include:

- Whether the job is configured with `preventRestart()`.
- Whether completed steps are allowed to re-run via `allowStartIfComplete`.
- Whether readers/writers properly save and restore state.
- Whether identifying JobParameters match the previous run.
- Whether writer side effects are idempotent when uncommitted portions are reprocessed.

A `FAILED` job does not automatically guarantee a safe restart. Before restarting, inspect committed data, non-transactional outputs, and dependency states.

## 18. JobExecution Status in Parallel Flows

When a job has parallel flows via `split(TaskExecutor)`, multiple steps can run concurrently while still belonging to a single `JobExecution`. `JobExecution` holds the job-level status; each `StepExecution` holds the status of its own branch/step.

Example:

| Flow | Step | BatchStatus |
|---|---|---|
| Customer flow | `importCustomersStep` | `COMPLETED` |
| Product flow | `importProductsStep` | `FAILED` |
| Job | `parallelImportJob` | Usually `FAILED` if the flow terminates due to the failed branch |

Do not infer job status from a single branch. When investigating, examine all step executions, exit statuses, and flow transitions. If the job is designed with a recovery branch for a failed flow, the final status also depends on the recovery branch and how the flow terminates.

Transactions for individual steps/flows are independent. One failed flow does not roll back chunks already committed by another flow. Therefore, a `FAILED` JobExecution does not mean all outputs from parallel flows were discarded.

## 19. Timestamps and Metadata Related to Status

In addition to BatchStatus, `JobExecution` has useful timestamps:

- `startTime`: when the execution started.
- `endTime`: when the execution finished, if it has finished.
- `lastUpdated`: when the execution metadata was most recently updated.

You can use these fields to calculate duration and detect executions that appear stuck. However, `lastUpdated` is not a heartbeat guaranteeing that the job is actively processing items; a long step may not update metadata frequently depending on configuration and checkpoint intervals.

Example:

~~~java
Duration duration = null;
if (execution.getStartTime() != null
        && execution.getEndTime() != null) {
    duration = Duration.between(
            execution.getStartTime(),
            execution.getEndTime());
}
~~~

To detect a stuck job, combine status, lastUpdated, logs, step metrics, thread dumps, and dependency health. Do not manually mark a job `FAILED` solely because the execution has not updated for a period without verifying actual progress.

## 20. Testing JobExecution BatchStatus

Tests should verify job-level status, per-step status, and business outcomes.

Cases to include:

1. Successful job: verify `JobExecution` ends in `COMPLETED`.
2. Unhandled exception: verify job/step has `FAILED` under default flow.
3. Stop: request stop on a running job and verify the final status is `STOPPED` once the framework finishes processing.
4. Restart after FAILED: same identifying JobParameters create a new execution for the same JobInstance and the job resumes from checkpoint.
5. Restart after STOPPED: verify steps resume from saved state.
6. Flow end/fail/stop: verify transitions determine the correct final status of JobExecution.
7. Custom ExitStatus: verify custom exit codes are not mistaken for a new BatchStatus.
8. Parallel flow: verify status of each branch and overall job status.
9. Async launcher: verify initial returned object may not be final status and JobExplorer returns the updated status.
10. Completed instance: verify the same JobInstance is not accidentally re-launched as a new batch.

Success test example:

~~~java
JobExecution execution =
        jobLauncherTestUtils.launchJob(jobParameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());
assertNotNull(execution.getEndTime());

StepExecution step = execution.getStepExecutions()
        .stream()
        .filter(item -> item.getStepName().equals("importOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.COMPLETED, step.getStatus());
assertEquals(100, step.getWriteCount());
~~~

This example assumes the job runs synchronously, the step executes, and the writer writes exactly 100 items. If the processor filters items or the step skips items, the write count must be adjusted to match the test data.

For stop or async tests, synchronize tests using a latch/barrier or polling with timeout instead of arbitrary sleep calls. Restart tests must preserve JobRepository metadata between the initial run and the restart run.

## 21. Common Pitfalls

**Treating STARTED as job success.** STARTED only indicates execution is in progress. Only read final results after the execution reaches a terminal state.

**Treating STOPPING as stopped.** STOPPING means a stop request is being processed; wait for STOPPED before restarting or releasing resources.

**Assuming FAILED means all data was rolled back.** Committed chunks/steps remain persisted. Reconcile data and checkpoints.

**Assuming COMPLETED means complete data.** The job may have skipped/filtered items or the flow may have an intentional completion branch. Check ExitStatus, counters, and reconciliation.

**Confusing BatchStatus with ExitStatus.** BatchStatus is a lifecycle enum; ExitStatus is an exit code used for transitions. Read both.

**Reading status from a stale object with an async launcher.** Reload using JobExplorer by execution ID.

**Restarting a job that is STARTED or STOPPING.** First verify the old execution has ended and the repository reflects its final status.

**Creating new identifying JobParameters when restarting.** This can create a new JobInstance and reprocess from the beginning. Keep the original batch's identifying parameters.

**Manually editing BatchStatus in the database.** Metadata tables are managed by Spring Batch. Use JobOperator and controlled recovery procedures.

**Looking only at JobExecution without inspecting StepExecution.** Job-level status does not clearly show which step failed or which branches never ran.

## 22. Workflow for Reading and Handling BatchStatus

When receiving an execution ID from an API or dashboard, you can follow this sequence:

1. Use `JobExplorer` to load the latest `JobExecution`.
2. Read `BatchStatus` to determine whether the execution is running or finished.
3. Read `ExitStatus` to understand the exit code and flow branch.
4. Iterate over `StepExecution` instances to find steps that are running, failed, stopped, or completed.
5. Inspect counters, exceptions, and checkpoints for investigation.
6. Reconcile business data and committed side effects.
7. If still running, continue monitoring; if STOPPING, wait for the stop to complete.
8. If FAILED or STOPPED, determine restartability and use the same identifying parameters when restarting.
9. If ABANDONED or UNKNOWN, follow the recovery runbook and audit before taking further action.
10. If COMPLETED, release output only after business completeness conditions are met.

## Conclusion

The `BatchStatus` of `JobExecution` describes the lifecycle of a job run: `STARTING`, `STARTED`, `STOPPING`, `STOPPED`, `COMPLETED`, `FAILED`, `ABANDONED`, or `UNKNOWN`. The status helps the system know whether the execution is running, finished, failed, or requires operational intervention. It belongs to `JobExecution`, because a single `JobInstance` can have multiple executions due to restarts.

Distinguish `BatchStatus` from `ExitStatus`, read individual `StepExecution` statuses, and verify business data before concluding a batch succeeded. `STOPPED` and `FAILED` can be restarted if configuration and metadata allow; `ABANDONED` is not continued normally; `UNKNOWN` requires investigation before acting. With an asynchronous launcher, use `JobExplorer` to read the latest status. Framework status is the basis for orchestration, while output completeness and accuracy must be confirmed by separate business checks.
