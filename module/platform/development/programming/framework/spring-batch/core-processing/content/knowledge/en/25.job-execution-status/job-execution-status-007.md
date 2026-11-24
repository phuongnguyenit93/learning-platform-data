# Status When a Job Stops Intentionally

In Spring Batch, when a Job is requested to stop intentionally, its execution status typically transitions through `STOPPING` and ends at `STOPPED`. This is a controlled termination: the Job stops accepting further work at a safe point, saves necessary metadata, and can be restarted later if Job policy permits.

`STOPPED` differs from `COMPLETED` and `FAILED`. `COMPLETED` indicates the Job finished the flow; `FAILED` indicates execution failed; `STOPPED` indicates the Job was halted before completion. An intentionally stopped Job can usually continue from saved state by restarting the same JobInstance.

## 1. Statuses Related to Stopping a Job

Spring Batch uses `BatchStatus` to represent the lifecycle state of JobExecution and StepExecution. Common statuses:

| BatchStatus | Meaning |
|---|---|
| `STARTING` | JobExecution is being initialized. |
| `STARTED` | Job is currently executing. |
| `STOPPING` | Stop request received; execution is proceeding toward a safe stop point. |
| `STOPPED` | Job stopped in a controlled manner and is no longer executing. |
| `COMPLETED` | Job completed normally along the flow. |
| `FAILED` | Job failed due to an exception or error condition. |
| `ABANDONED` | Execution marked permanently abandoned, not continued via normal restart. |
| `UNKNOWN` | Execution status cannot be determined with certainty. |

Typical state flow when requesting a running Job to stop:

```text
STARTED
   |
   | JobOperator.stop(executionId)
   v
STOPPING
   |
   | Step reaches a safe stopping point
   v
STOPPED
   |
   +--> Can restart the same JobInstance if policy allows
```

`STOPPING` is usually an intermediate state. A stop request does not mean the running thread is forcibly terminated immediately. The Step needs an opportunity to finish its current unit of work or check the stop signal at a safe point.

## 2. Distinguishing STOPPED, COMPLETED, and FAILED

These three statuses represent three different outcomes:

| Status | Typical Cause | Can Restart Same JobInstance? |
|---|---|---|
| `COMPLETED` | Steps and flow finished normally. | Usually no; JobInstance is already complete. |
| `FAILED` | Unhandled exception or a Step/flow failed. | Yes, if Job and Steps allow restart. |
| `STOPPED` | Operator or flow requested a controlled stop. | Yes, if Job and Steps allow restart. |
| `ABANDONED` | Execution was marked not to continue. | Not via the normal restart workflow. |

Examples:

- Operator needs to pause an import for database maintenance: request stop and the Job ends `STOPPED`.
- Reader hits an unhandled error: Job ends `FAILED`.
- All data is processed and Steps finish: Job is `COMPLETED`.
- An old execution is determined unresumable and abandoned by an admin: `ABANDONED`.

Do not mark a Job as `FAILED` just because an operator wants to stop it for maintenance. Using the stop mechanism makes clear it was an intentional control action while preserving proper restart capability.

## 3. Stopping a Running Job with JobOperator

The common operational API to request stopping a running JobExecution is `JobOperator.stop(executionId)`. This method issues a stop request using the JobExecution ID instead of directly killing the running thread.

Example service accepting a stop request:

```java
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class JobControlService {

    private final JobOperator jobOperator;

    public JobControlService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public boolean requestStop(long executionId) throws Exception {
        return jobOperator.stop(executionId);
    }
}
```

The boolean return value indicates the stop request was accepted by the API. It does not mean the Job has already transitioned to `STOPPED` at the moment the method returns. The application must continue monitoring JobExecution until the final status is `STOPPED`, `COMPLETED`, or `FAILED`.

The supplied ID must be a running JobExecution ID, not a JobInstance ID or StepExecution ID. If the execution has already ended or does not exist, JobOperator may throw an appropriate exception. Handle the race condition where the Job finishes right as the operator submits the stop request.

## 4. Stop Is a Controlled Request, Not Killing a Thread

When `JobOperator.stop()` is called, Spring Batch asks the Job to stop at a safe point. The exact mechanism depends on the Step type and when the signal is received.

With a chunk-oriented Step, an in-progress chunk is normally allowed to reach an appropriate boundary before the Step stops. This avoids interrupting a write mid-transaction. Committed chunks are preserved; if the current chunk rolls back due to an error or interruption, data in that transaction is undone.

With a Tasklet Step, stopping depends on timing and how the Tasklet performs its work. If the Tasklet is blocked in a long network call or loop without checking status, the stop request may not take effect until that call or iteration finishes. Tasklets should break long work into bounded units, check the stop signal appropriately, or save progress so execution can resume.

Do not use `Thread.stop()` or manually interrupt Spring Batch threads. Forced interruption can skip cleanup, leave transactions or resources in an unsafe state, and cause metadata not to reflect the true business outcome.

## 5. Monitoring Status After Sending a Stop Request

After requesting a stop, the application should query JobExecution to confirm whether the Job has actually finished. You can use `JobExplorer`:

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

@Service
public class JobStatusService {

    private final JobExplorer jobExplorer;

    public JobStatusService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public BatchStatus getStatus(long executionId) {
        JobExecution execution = jobExplorer.getJobExecution(executionId);
        if (execution == null) {
            throw new IllegalArgumentException(
                    "JobExecution not found: " + executionId);
        }
        return execution.getStatus();
    }
}
```

An admin endpoint can return status `STOPPING` immediately after receiving the request, and the client can poll until the Job transitions to a terminal state. In a multi-instance environment, JobExplorer must read metadata from the same persistent repository used by the running Job.

Do not rely solely on the boolean returned by `stop()` to display that the Job has stopped. Read the actual status from JobRepository/JobExplorer.

## 6. Stopping at Chunk Boundaries and Impact on Checkpoints

With a chunk Step, Spring Batch manages transactions per chunk. When a stop request arrives while a chunk is running, the Step typically needs to complete or roll back the current transaction unit before stopping.

```text
Chunk 1: READ / PROCESS / WRITE -> COMMIT
Chunk 2: READ / PROCESS / WRITE -> COMMIT
             |
             +--> Receive stop request
             |
             v
       Stop at safe point
             |
             v
          STOPPED

Restart same JobInstance
             |
             v
       Resume from committed checkpoint
```

Checkpoints are persisted at appropriate commit boundaries. Chunks committed before stopping are retained. When restarting the same JobInstance, stateful Readers can resume from the latest checkpoint.

Do not assume a stop always happens cleanly between two chunks. If the request arrives while the Writer is executing, the outcome depends on when the Step checks the signal and how the transaction concludes. Design Writers to be idempotent so data remains safe if a chunk has to be retried.

## 7. Stopping a Job via Flow Transitions

In addition to external stop requests, a Job flow can intentionally terminate in `STOPPED` status. This is useful when business logic needs to pause at a specific point and designate which Step to start from on restart.

Spring Batch provides the `stopAndRestart(step)` transition in the flow builder. For example, after validating data, a Job can intentionally stop if approval is required; upon restart, the flow resumes from the designated processing Step.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;

@Bean
public Job approvalJob(
        JobRepository jobRepository,
        Step validateRequestStep,
        Step processApprovedRequestStep) {

    return new JobBuilder("approvalJob", jobRepository)
            .start(validateRequestStep)
            .on("WAIT_FOR_APPROVAL")
            .stopAndRestart(processApprovedRequestStep)
            .from(validateRequestStep)
            .on("COMPLETED")
            .to(processApprovedRequestStep)
            .end()
            .build();
}
```

The example assumes `validateRequestStep` can return `ExitStatus("WAIT_FOR_APPROVAL")` when waiting for human approval. Transition `stopAndRestart(processApprovedRequestStep)` ends the Job in a stopped state and sets the continuation point when the JobInstance is restarted.

Flow transitions are chosen based on the Step's ExitStatus. Therefore, the Step must set ExitStatus to the exact code the flow checks. You can set a custom code in a Tasklet or Step listener:

```java
contribution.setExitStatus(new ExitStatus("WAIT_FOR_APPROVAL"));
return RepeatStatus.FINISHED;
```

This is a stop driven by business rules declared in the flow, distinct from a stop request sent to a running Job via JobOperator.

## 8. Distinguishing stop, end, fail, and abandon in Flows

Spring Batch flow builders have terminal transitions with distinct meanings:

| Transition | Outcome | Restart Same JobInstance |
|---|---|---|
| `.end()` | Ends flow normally; Job is usually `COMPLETED`. | Cannot restart an already completed JobInstance. |
| `.fail()` | Ends flow with error status; Job is `FAILED`. | Can restart if Job allows. |
| `.stop()` | Ends flow with `STOPPED` status. | Can restart depending on state and configuration. |
| `.stopAndRestart(step)` | Stops flow and designates the Step to start from on restart. | Can restart from the specified Step. |

`abandon` is an administrative action on JobExecution via JobOperator, not a transition replacing `.stop()`. When abandoned, the execution is marked `ABANDONED` and cannot continue via normal restart.

Choose `STOPPED` when you want to pause and preserve the ability to resume; choose `FAILED` when there is an error to fix; choose `COMPLETED` when the unit of work is done; only abandon when you have decided to discard that execution permanently.

## 9. STOPPED and ExitStatus

`BatchStatus` and `ExitStatus` are two different pieces of information:

- `BatchStatus` represents the lifecycle state of JobExecution/StepExecution.
- `ExitStatus` represents the exit outcome code and can hold custom codes for flows or reporting.

When a Job is stopped, the final `BatchStatus` is usually `STOPPED`; the default `ExitStatus` usually reflects code `STOPPED`, though it can be customized by a listener or flow. Therefore, when inspecting outcomes, read both values.

Example reading status:

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution != null) {
    BatchStatus batchStatus = execution.getStatus();
    String exitCode = execution.getExitStatus().getExitCode();

    log.info("JobExecution {} status={}, exitCode={}",
            executionId, batchStatus, exitCode);
}
```

Do not merely compare ExitStatus to the string `STOPPED` and conclude the Job has definitely stopped. Inspect BatchStatus and verify whether the execution is still `STOPPING`.

## 10. Restarting a STOPPED Job

A Job ending in `STOPPED` can usually be restarted if the Job is not configured with `preventRestart()` and relevant Steps can resume. When restarting, use the same identifying JobParameters to continue the same JobInstance.

You can restart using `JobOperator`:

```java
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class RestartService {

    private final JobOperator jobOperator;

    public RestartService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public Long restart(long stoppedExecutionId) throws Exception {
        return jobOperator.restart(stoppedExecutionId);
    }
}
```

`stoppedExecutionId` is the ID of the stopped JobExecution, not the JobInstance ID. JobOperator creates a new JobExecution for the same JobInstance if state and policy allow.

Another approach is calling `JobLauncher.run()` with the same Job and same identifying parameters. Spring Batch looks up the matching JobInstance and applies restart semantics. Do not add a new identifying UUID or timestamp if the goal is restarting; doing so creates a new JobInstance.

### Which Steps run again on restart?

- Steps already `COMPLETED` are normally skipped.
- Stopped or incomplete Steps can resume based on checkpoints and flow.
- Steps with `allowStartIfComplete(true)` can run again even if already completed.
- Steps that hit `startLimit` cannot start again.
- If the flow used `stopAndRestart(step)`, the restart point is determined by the configured Step.

Restarting does not necessarily re-run the entire Job from the first Step. It relies on metadata and flow configuration.

## 11. Intentional Stop vs. Abandon

`JobOperator.stop(executionId)` requests a running Job to stop in a controlled way. After stopping, the JobExecution can be restarted.

`JobOperator.abandon(executionId)` marks the execution as `ABANDONED`. This operation is for cases where operators decide not to continue that execution via normal restart. Do not use abandon simply to pause a Job.

| Operational Action | Appropriate API/Transition |
|---|---|
| Pause a running Job for maintenance and resume later | `JobOperator.stop(executionId)` |
| Stop flow per business condition and specify resume point | `.stopAndRestart(step)` |
| End flow successfully | `.end()` |
| End flow due to error | `.fail()` |
| Permanently discard an execution, no normal restart | `JobOperator.abandon(executionId)` |

Abandon is an administrative action affecting recoverability. Before abandoning, confirm business data is in a safe state and have a plan for handling remaining work.

## 12. Stop Requests When a Job Runs Asynchronously

With an asynchronous JobLauncher, the launch call can return as soon as the Job is submitted to an executor. The Job continues running on another thread. When stopping is needed, the application must use the created JobExecution ID and call `JobOperator.stop()`.

Typical management flow:

```text
API / Scheduler
    |
    v
JobLauncher (async)
    |
    v
JobExecution ID stored/returned
    |
    +------------------------+
    |                        |
    v                        v
Monitor status          Request stop
    |                        |
    |                   JobOperator.stop(id)
    |                        |
    +----------+-------------+
               |
               v
          JobExecution
               |
               v
       STOPPING -> STOPPED
```

Do not keep an API request transaction open for the entire duration of the Job or while waiting for the Job to stop. Persist the execution ID, return an appropriate control response, and provide an endpoint/status view for monitoring.

If the application runs across multiple instances, JobOperator and JobExplorer must access the shared metadata repository. Stop signals must reach the right execution and the worker must be able to observe stop signals per Spring Batch mechanisms.

## 13. Handling Long Tasklets and Cooperative Stopping Points

A Tasklet executing a long service call or large loop may not respond quickly to a stop request if it lacks checkpoints. Do not write a Tasklet performing hours of work in a single `execute()` invocation without checkpoints or chunking.

Design approaches:

1. Break work into small units, each able to finish and persist state.
2. Use a chunk-oriented Step if the work involves reading/processing/writing many items.
3. For iterative Tasklets, persist progress in ExecutionContext or a database so it can resume.
4. Set timeouts on HTTP/database calls so stopping does not wait indefinitely on a hung dependency.
5. Ensure resource cleanup in `finally` blocks or appropriate lifecycle callbacks.

If business logic needs to check stop signals inside a loop, use safe coordination with StepExecution/JobExecution and check at unit-of-work boundaries. Never directly edit BatchStatus in the database or interrupt threads to force status to `STOPPED`.

## 14. Listeners and Auditing When a Job Stops

`JobExecutionListener.afterJob()` is invoked when the Job terminates, including when the final status is `STOPPED` or `FAILED`. Listeners can read BatchStatus and ExitStatus to record audits or emit notifications.

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class JobAuditListener implements JobExecutionListener {

    @Override
    public void beforeJob(JobExecution jobExecution) {
        // Record start.
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        if (jobExecution.getStatus() == BatchStatus.STOPPED) {
            // Record that the Job stopped intentionally or via flow stop.
        }
    }
}
```

In real systems, store execution ID, JobInstance ID, stop timestamp, currently executing Step, and the requester/source of the stop if available. Avoid using a mutable field in a singleton listener to hold requester or start time; attach data to JobExecution or a separate audit record.

If sending emails or messages when a Job stops, prevent duplicates if the listener or orchestration process is re-invoked. You can write events to an outbox keyed by execution ID and dispatch after commit.

## 15. Testing Intentionally Stopped Jobs

Write integration tests using `JobRepository` and `JobLauncherTestUtils` or `JobOperator` to verify real status transitions, rather than mocking a single Java method.

Scenarios to test:

1. **Stop a running Job:** launch a Job with a Step that runs long enough or uses a control latch; call `JobOperator.stop(executionId)`; verify the Job transitions from `STOPPING` to `STOPPED`.
2. **Restart a STOPPED Job:** use the same identifying JobParameters; verify the new JobExecution belongs to the same JobInstance and the Step resumes from checkpoint.
3. **Stop request too late:** let the Job finish before calling stop; verify the application handles an execution that is no longer running.
4. **stopAndRestart flow:** configure a Step returning the matching ExitStatus; verify the Job stops and restarts from the designated Step.
5. **Abandon:** verify the execution is marked `ABANDONED` and is not treated as a normally restartable Job.
6. **Listener:** verify `afterJob()` receives `STOPPED` accurately and audits are not duplicated.

For asynchronous Jobs, tests must await terminal status using synchronization mechanisms with timeouts. Avoid long `Thread.sleep()` calls assuming the Job has stopped; poll `JobExplorer` or use latches/test hooks to coordinate timing.

When testing restarts, keep identifying JobParameters unchanged. Adding a new identifying parameter causes Spring Batch to create a new JobInstance and the test will no longer verify restarting the stopped execution.

## 16. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Treating `STOPPING` as fully stopped | Job may still be finishing a chunk or cleanup. | Monitor until reaching a terminal state like `STOPPED`. |
| Using thread kill to stop a Job | Can skip cleanup or leave transactions/resources unsafe. | Use `JobOperator.stop()` and cooperative stopping points. |
| Confusing STOPPED with FAILED | Reporting and restart workflows misrepresent the cause. | Use stop for intentional halts, fail for errors. |
| Confusing stop with abandon | Execution may be marked unrestartable. | Only abandon when discarding the execution permanently. |
| Assuming stop completes as soon as the API returns | The boolean only reflects request acceptance, not that the Job stopped. | Poll JobExecution via JobExplorer. |
| Sending stop to the wrong JobExecution ID | Fails to stop the intended execution. | Look up and validate the ID before calling JobOperator. |
| Long Tasklet without checkpoints | Job responds slowly to stop or waits for long operations to finish. | Split work, set timeouts, and persist progress. |
| Restarting with new identifying parameters | Creates a new JobInstance instead of resuming the stopped Job. | Reuse the original instance's identifying parameters. |
| Sending stop notifications without deduplication | Audits/notifications can duplicate on retry or restart. | Bind idempotency keys to execution ID or use an outbox. |

## Conclusion

When a Job is stopped intentionally, Spring Batch normally transitions status from `STARTED` to `STOPPING` and then `STOPPED` after reaching a safe stopping point. Use `JobOperator.stop(executionId)` to request a stop and monitor JobExecution until it truly terminates; never forcibly kill threads. `STOPPED` differs from `FAILED`, `COMPLETED`, and `ABANDONED`: a stopped Job can usually restart the same JobInstance if policy permits. With chunk Steps, checkpoints and transactions let work resume from committed chunks; with long Tasklets, split work and save progress. Testing stop, restart, flow transitions, and auditing makes intentional stopping safe and easy to operate.
