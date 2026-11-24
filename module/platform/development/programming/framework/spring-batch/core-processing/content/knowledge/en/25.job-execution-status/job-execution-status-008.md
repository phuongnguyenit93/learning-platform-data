# Status When an Operator Stops a Job

In Spring Batch, an operator can request to stop a running job via `JobOperator.stop(executionId)`. This is a controlled stop request: the framework marks the execution as stopping, then the running step detects the signal at a safe point and terminates according to its lifecycle. The job normally transitions through `STOPPING` and ends at `STOPPED`.

`STOPPING` and `STOPPED` have different meanings. `STOPPING` indicates that the stop request has been recorded, yet the job may still be processing. `STOPPED` is the terminal state once the execution flow has stopped. Therefore, a `true` result from the stop command should only be interpreted as the API accepting the request; the application still needs to observe `JobExecution` to confirm the job actually reaches `STOPPED`.

An operator stop is normally a graceful stop, not a command to kill threads or immediately cancel an active SQL statement, HTTP call, or running processor. With a chunk step, the framework usually stops at a chunk boundary after handling the current transaction. With a tasklet, the signal is typically handled at a safe iteration point after the current `execute` call returns. Consequently, the time from sending the request until the job stops depends on current processing time and the responsiveness of external resources.

## JobOperator and JobExecution

`JobOperator` is the operational API for jobs, providing operations such as launch, restart, stop, and querying executions. When an operator wants to stop a job, they must pass the **JobExecution ID** of the active run.

```java
@Service
public class BatchControlService {

    private final JobOperator jobOperator;

    public BatchControlService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public boolean requestStop(long jobExecutionId) throws Exception {
        return jobOperator.stop(jobExecutionId);
    }
}
```

`jobExecutionId` is the ID of a specific execution attempt, not the `JobInstance` ID, `Job` ID, or `StepExecution` ID. One `JobInstance` can have multiple `JobExecution` records due to restarts; to stop the running attempt, you must use the active execution ID.

In production applications, verify operational permissions and confirm which job the execution belongs to before allowing a stop. Never accept an arbitrary ID from a request and invoke the operator without authorization checks.

## Status Lifecycle During Operator Stop

A running job typically follows this general status sequence:

```text
STARTING
   |
   v
STARTED
   |
   | JobOperator.stop(executionId)
   v
STOPPING       <- stop request recorded
   |
   | step receives signal at safe point
   v
STOPPED        <- execution finished
```

The `STOPPING` status can persist for some time. For example, a processor may be handling a slow item or a writer may be writing a large chunk. Operators should not report to users that the job has completely stopped simply because the stop API returned successfully.

| `BatchStatus` | Meaning in a Stop Scenario |
| --- | --- |
| `STARTED` | Job is executing normally |
| `STOPPING` | Stop requested; job has not finished stopping |
| `STOPPED` | Job stopped as requested and can be restarted if configuration permits |
| `COMPLETED` | Job finished normally before the stop request took effect or no work remained to stop |
| `FAILED` | Job ended due to an execution error, not simply a graceful stop |
| `ABANDONED` | Execution marked abandoned/not to continue via normal restart workflow |
| `UNKNOWN` | Status undetermined or requires metadata/resource investigation |

`BatchStatus` describes the execution status. `ExitStatus` is the outcome code used for flows and reporting. For a normal stop, `ExitStatus` is usually `STOPPED`, though during investigation you should read both values rather than inferring one from the other.

## A Stop Request Is Not an Instant Stop

Spring Batch coordinates stopping at points where the framework can finish work and persist state safely. This avoids cutting across a transaction or leaving checkpoints reflecting uncommitted work.

### With a chunk-oriented step

A chunk step processes a group of items within a single transaction. If a stop request arrives while the processor or writer is processing a chunk, the framework normally lets the current chunk reach its processing boundary. If the chunk completes successfully, the writer and checkpoint are updated and the transaction commits; afterward, the step detects the stop signal and does not start the next chunk.

```text
Chunk 1 -> COMMIT
Chunk 2 -> processing when operator sends stop
          |
          v
       finish current chunk
          |
          v
       update checkpoint
          |
          v
          COMMIT
          |
          v
       receive stop signal
          |
          v
       step STOPPED
```

This is typical graceful stop behavior. If the current chunk itself throws an exception, the transaction may roll back according to rollback rules and the step may end `FAILED` rather than `STOPPED`. The final result depends on the actual error and when the stop signal is processed.

Large chunk sizes or slow per-item processing can lengthen stop times. If operations require faster stopping, consider reducing per-item processing duration, setting I/O timeouts, and choosing an appropriate commit interval. Avoid mechanically shrinking chunk sizes if doing so increases overhead or harms throughput.

### With a tasklet step

In `TaskletStep`, `Tasklet.execute(...)` is the unit of work invoked inside each iteration's transaction. If the tasklet is in the middle of a long `execute` call, the stop request is normally processed only after the current invocation returns at the next check point.

If a tasklet runs a very long internal loop without returning control to the framework, stop latency can be high. You can break work into small units, save checkpoints in `ExecutionContext`, and return `RepeatStatus.CONTINUABLE` so the framework has a chance to check the stop signal between units.

```java
public class ProcessPagesTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext context =
                contribution.getStepExecution().getExecutionContext();
        int page = context.getInt("nextPage", 0);

        processOnePage(page);
        context.putInt("nextPage", page + 1);

        return hasMorePages(page + 1)
                ? RepeatStatus.CONTINUABLE
                : RepeatStatus.FINISHED;
    }
}
```

The example processes one page per call to create a checkpoint between units. `processOnePage` and `hasMorePages` represent application logic. If a stop request arrives while processing a page, the current page must finish or roll back per transaction rules before the tasklet stops; the checkpoint must represent committed pages.

## Sending Stop via JobOperator

An application can obtain the execution ID from `JobExplorer` or from the launch result, then call `JobOperator.stop`.

```java
public boolean stopExecution(
        JobOperator jobOperator,
        long executionId) throws Exception {

    return jobOperator.stop(executionId);
}
```

The API may report an error if the execution is not found or is no longer in a stoppable state. Handle these cases separately:

- Non-existent ID: no matching execution exists.
- Execution already `COMPLETED`, `FAILED`, or `STOPPED`: no longer a running execution eligible for a stop request.
- Execution already `STOPPING`: stop request has already been sent; continue monitoring status instead of repeatedly sending stop requests.
- Execution running: stop request can be accepted and status will transition according to lifecycle.

Exact exception names and API signatures should be checked against the Spring Batch version in use. APIs commonly declare exceptions such as `NoSuchJobExecutionException` or `JobExecutionNotRunningException`.

### Retrieving running execution IDs

`JobOperator.getRunningExecutions(jobName)` can return running execution IDs for a job. `JobExplorer` also provides APIs to read `JobExecution` records and related statuses.

```java
Set<Long> runningIds = jobOperator.getRunningExecutions("dailyImportJob");

for (Long executionId : runningIds) {
    JobExecution execution = jobExplorer.getJobExecution(executionId);
    if (execution != null) {
        log.info("executionId={}, status={}",
                executionId, execution.getStatus());
    }
}
```

Do not rely solely on job name to stop if multiple executions run concurrently. Identify the exact execution ID, using business date, identifying parameters, or correlation ID.

## Monitoring STOPPING Until STOPPED

After issuing a stop request, the operator should re-read metadata to confirm whether the execution has actually stopped. An in-memory `JobExecution` object can be a stale snapshot; query again via `JobExplorer` to fetch the latest status from the repository.

```java
JobExecution current = jobExplorer.getJobExecution(executionId);
if (current != null) {
    BatchStatus status = current.getStatus();
    ExitStatus exitStatus = current.getExitStatus();

    log.info("executionId={}, batchStatus={}, exitStatus={}",
            executionId, status, exitStatus.getExitCode());
}
```

An admin API can return `STOPPING` immediately after the request is accepted, and the client continues polling or listening for events until the execution reaches a terminal status. Use a finite timeout on waiting screens/APIs; if the timeout expires while the execution is still `STOPPING`, display the stopping state and allow operators to investigate further.

Never manually update `BATCH_JOB_EXECUTION.STATUS` with SQL to force `STOPPING` to `STOPPED`. Doing so bypasses step, transaction, thread, and repository lifecycles, potentially creating metadata inconsistent with work that is still running.

## JobExecution and StepExecution After Stopping

A job can consist of multiple steps. When stop is processed, the currently running step usually ends with `STOPPED`; previously completed steps retain `COMPLETED`. Steps that had not started have no completed `StepExecution`.

Example:

| Step | Status when parent job stops |
| --- | --- |
| `validateInputStep` | `COMPLETED` |
| Running `importOrdersStep` | `STOPPED` after receiving stop at safe point |
| Unstarted `summaryStep` | No execution or not started |

The `JobExecution` ends `STOPPED` when the flow is halted on request. During investigation, inspect individual step executions to see what completed, what stopped, and what never ran.

With split/parallel flows, multiple branches may be active. The stop signal must be handled by the relevant threads; a branch mid-transaction may need to reach a safe point. A branch that already committed is not rolled back just because another branch received a stop. Inspect all `StepExecution` records and actual outputs before restarting.

## Stop and Transactions/Checkpoints

Graceful stop is designed to preserve checkpoints at valid processing boundaries. With a chunk step, chunks committed prior to the stop remain; the current chunk usually completes before stopping if no error occurs. With a tasklet, each `execute` invocation has its own transaction; state should be updated alongside the committed unit of work.

```text
Chunk 1: COMMIT -> checkpoint 100
Chunk 2: COMMIT -> checkpoint 200
Chunk 3: stop request arrives while running
         -> finish/rollback based on chunk outcome
         -> if committed: checkpoint 300
         -> step STOPPED

Restart: resume from last committed checkpoint
```

Do not interpret stop as rolling back the entire step. Data from previously committed chunks is preserved. If stop arrives after a step finishes but before the job finishes completely, the final status depends on when the signal is handled in the flow.

### External non-transactional side effects

Stopping does not revoke side effects already accepted by external systems. For example, a processor sent an HTTP request or a writer published a message before the stop was handled. If the chunk subsequently rolls back or the job stops, that request/message may still exist.

Use idempotency keys, transactional outboxes, staging files, or a post-step publish workflow. On restart, the same item may be reprocessed if output was not confirmed in transaction metadata; side effects must be safe when repeated.

## Restarting After STOPPED

A job stopped by an operator can usually be restarted if the job is configured as restartable and metadata state permits. Restarting creates a new `JobExecution` for the same `JobInstance`, using the identifying parameters of the previous run.

You can restart via `JobOperator.restart(executionId)` or re-run the job via `JobLauncher` with the same identifying `JobParameters`, depending on how the application operates.

```java
long newExecutionId = jobOperator.restart(stoppedExecutionId);
```

The restart API can throw exceptions if the execution does not exist, the job is not restartable, the instance is already complete, or the status does not permit restart. Address operational errors rather than inventing new parameters to bypass the current state.

### Identifying parameters must remain stable

For example, a job is launched with:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceFile", "orders-2026-11-15.csv", true)
        .toJobParameters();
```

When restarting, use the exact same identifying parameters. Do not add a new identifying timestamp or UUID just to re-launch; doing so creates a new `JobInstance` and can cause the job to read/write all data from the beginning.

If source files or output resources can change, store version/checksum info or use immutable resources so restarts resume against the exact original data.

### Which steps re-run?

Restarting does not necessarily re-run the entire job:

- Steps already `COMPLETED` are usually skipped per restart semantics.
- `STOPPED` steps can restart from saved checkpoints if step/job configuration allows.
- Steps not yet started will run when the flow reaches them.
- `allowStartIfComplete(true)` can cause an already completed step to run again during a restart.
- `startLimit` and restartability settings can restrict how many times a step may start.

Therefore, verify the restart behavior of every step, especially steps with non-transactional side effects. Never assume an operator stop will make the whole job re-run from scratch.

## Distinguishing Stop, Fail, Abandon, and Killing a Process

These states and operations have different meanings:

| Operation/Status | Meaning | Restart |
| --- | --- | --- |
| `JobOperator.stop` | Requests a graceful stop of a running execution | Usually restartable if configuration allows |
| `STOPPING` | Stop request is being processed | Not yet a terminal state |
| `STOPPED` | Execution stopped in a controlled manner | Usually restartable |
| `FAILED` | Execution failed due to an exception or error | May be restartable depending on job/step |
| `JobOperator.abandon` / `ABANDONED` | Marks execution abandoned, not continued via normal restart | Not restarted like normal stopped/failed executions |
| Kill JVM/container | Abruptly terminates process, not a graceful stop | Must handle incomplete execution and recover via metadata/resources |

Do not use `ABANDONED` as a substitute for `STOPPED`. Abandoning is a distinct operational decision, usually used when an execution should never continue. Likewise, do not equate killing a process with an operator stop; open transactions may roll back when resources close, but threads and non-database side effects are not terminated through a graceful lifecycle.

## Stopping When a Job Runs Asynchronously

So that an operator can send a stop from another thread or request while the job runs, applications commonly launch jobs asynchronously using `TaskExecutorJobLauncher` or an equivalent launcher configuration. If a synchronous launcher blocks the calling thread until the job finishes, administrative requests may need a separate channel to invoke stop.

Example launcher configuration with an executor:

```java
@Bean
TaskExecutorJobLauncher jobLauncher(
        JobRepository jobRepository,
        @Qualifier("jobExecutor") TaskExecutor jobExecutor) throws Exception {

    TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
    launcher.setJobRepository(jobRepository);
    launcher.setTaskExecutor(jobExecutor);
    launcher.afterPropertiesSet();
    return launcher;
}
```

This executor determines the thread that launches the job. It differs from the executor passed to `FlowBuilder.split(...)`, which coordinates parallel flows inside the job. Do not share one small pool for both the job launcher and nested flows without evaluating thread starvation risks.

With an async launcher, `JobLauncher.run(...)` can return while the job is still running. The caller receives the `JobExecution`/ID to monitor; operators use that ID to send a stop request later.

## Stopping When a Processor or I/O Is Blocked

An operator stop cannot guarantee immediate interruption of an active Java call. If a processor is waiting on an HTTP response, a reader on a database query, or a writer on a broker acknowledgement, the job may remain in `STOPPING` until that operation returns or throws an error.

To allow stops to complete in a reasonable time:

- Configure connect/read/request timeouts on HTTP clients.
- Set appropriate query timeouts on database statements.
- Configure timeouts on message receive/send and acknowledgements.
- Split long tasklets into small checkpointed units.
- Avoid long internal loops without status check points.
- Avoid arbitrary thread interruption if operations do not support safe cancellation.

If the application builds a long loop inside a tasklet, it can proactively check a stop flag or interruption per design, while ensuring transactions and checkpoints are not left inconsistent. Do not replace Spring Batch's stop mechanism with an unsynchronized `volatile` variable disconnected from execution metadata.

## Parallel Flows and Partitions During Stop

In a split flow or partitioned step, one job may have multiple active workers. An operator stop targets the parent `JobExecution`; actual stopping requires the relevant steps/workers to receive the signal and reach a safe point.

Points to note:

- A worker mid-chunk may finish its current transaction before stopping.
- Already completed branches retain `COMPLETED` status and committed data.
- Running branches can transition to `STOPPED` after receiving the signal.
- Remote partition workers need status propagation/stop coordination appropriate for their transport and handler.
- Side effects in external systems may persist after the job stops.

Do not assume a single stop request instantly kills all worker threads. Inspect `JobExecution`, each `StepExecution`, partition status, and worker logs. When using remote partitioning, test both the manager sending stop and workers receiving/completing the stop.

## Stopping in a Parent Job with JobStep

If a parent job has a `JobStep` launching a child job, define orchestration boundaries. Stopping the parent should not be assumed to kill the child process. The child job has its own execution and metadata; stopping the child depends on how `JobStep`, the launcher, and child execution are coordinated.

In a parent/child model, observe the parent `JobExecution`, the parent `StepExecution` of the `JobStep`, and the child `JobExecution`. If business rules require stopping both levels, the application needs a clear procedure to identify the child execution ID, send the appropriate stop, and wait for the child's terminal status before concluding the entire workflow has stopped.

Do not infer the child is `STOPPED` merely because the parent transitioned to `STOPPED`. Verify child metadata via `JobExplorer` or `JobOperator`.

## Stop and Listeners

Listeners may be invoked as the step/job transitions status after a stop. For example, `StepExecutionListener.afterStep` can observe the final status and return an additional `ExitStatus` per flow rules. However, a listener should not pretend a stop was a completion by overriding status without a business rule.

If notifications are needed when an operator stops a job, use `JobExecutionListener.afterJob` or external monitoring watching for `BatchStatus.STOPPED`. Notifications should be idempotent because restarts or callbacks/lifecycle events may be observed again in operational workflows.

Do not use `afterJob` to perform work expected to roll back with earlier chunks; this callback runs at a different lifecycle phase and is not inside a job-wide transaction.

## Testing Operator Stop

Testing stop requires running the job on a separate thread so the test thread can issue the stop request while the execution is active. Use latches/barriers to control timing, avoiding `Thread.sleep` and race conditions.

An integration test can perform:

1. Configure an async job launcher or launch the job on a separate executor in the test.
2. Use a test double tasklet/processor signaling via `CountDownLatch` once started.
3. Wait for the start signal with a finite timeout.
4. Obtain the `JobExecution` ID.
5. Call `jobOperator.stop(executionId)`.
6. Monitor `JobExplorer` until status reaches `STOPPED` or test timeout.
7. Verify `ExitStatus`, `StepExecution` records, checkpoints, and business data.

Example test coordination snippet:

```java
@Test
void operatorStopEndsExecutionAsStopped() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
            .addString("testRunId", UUID.randomUUID().toString(), true)
            .toJobParameters();

    JobExecution started = jobLauncher.run(job, parameters);
    long executionId = started.getId();

    assertTrue(taskStarted.await(5, TimeUnit.SECONDS));

    assertTrue(jobOperator.stop(executionId));

    await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> {
        JobExecution current = jobExplorer.getJobExecution(executionId);
        assertNotNull(current);
        assertEquals(BatchStatus.STOPPED, current.getStatus());
    });
}
```

The example assumes `jobLauncher` is configured asynchronously, `taskStarted` is a latch counted down by the test tasklet, and the test uses Awaitility to await terminal status. Ensure the test tasklet has a termination path once stop is handled; do not create an infinite loop or I/O without timeouts.

### Testing the intermediate STOPPING status

`STOPPING` may be observed immediately after sending stop, but tests should not mandate seeing this state because the job might stop too quickly and the intermediate state may be too brief. Stronger assertions are:

- The stop request is accepted while the execution is running.
- The execution eventually reaches `STOPPED` within timeout.
- The running step stops according to designed semantics.
- Previously completed steps retain their outcomes.

### Testing chunk boundaries

Place a latch in the processor or writer so the test issues stop while a chunk is in flight. After releasing the latch, verify the current chunk finishes or rolls back per fixture, the checkpoint does not advance past uncommitted data, and the step does not begin a new chunk after stop is processed.

Do not write tests relying on wall-clock processing time to hit exact stop moments. Explicit synchronization gives deterministic control over chunk state.

### Testing restart after STOPPED

After the job stops:

- Fetch the latest execution and assert `STOPPED` status.
- Restart with the same identifying parameters or `JobOperator.restart` per API.
- Verify the job creates a new `JobExecution` for the same `JobInstance`.
- Verify completed steps follow restart policy and the stopped step resumes from checkpoint.
- Reconcile business data to ensure no duplicate or missing output.

### Testing stops that cannot complete quickly

You can simulate an I/O call with a timeout longer than the test wait window to confirm the execution stays `STOPPING` while the call has not returned. Then release the call or let the timeout occur and verify the job reaches a terminal state. Tests must clean up threads/executors even if assertions fail.

## Common Operational Mistakes

### Reporting the job stopped when the stop API returns true

The API confirms the request was accepted; the execution may still be `STOPPING`. Re-read status via `JobExplorer` until `STOPPED` or another terminal status.

### Using the wrong ID

`JobOperator.stop` requires the `JobExecution ID`, not job instance ID or step execution ID. Retrieve the ID from launch or `JobExplorer`.

### Expecting stop to interrupt processors immediately

The framework normally stops at a safe point. Long-running processors or blocked I/O extend stop duration. Configure timeouts and split work into smaller units.

### Confusing STOPPED with FAILED

`STOPPED` is the result of a controlled stop; `FAILED` reflects an execution failure. Inspect `BatchStatus`, `ExitStatus`, and failure exceptions.

### Confusing STOPPED with ABANDONED

Abandoning is a decision not to continue the execution via normal restart semantics. Use stop for graceful stops and only abandon under an intentional operational workflow.

### Thinking all data was rolled back

Committed chunks remain persisted. Inspect checkpoints and business data before restarting or re-running.

### Ignoring child/worker executions

Parent jobs, child jobs, parallel flows, and remote workers maintain separate metadata. Inspect all relevant levels before concluding the entire workflow stopped.

### Restarting with new parameters

New identifying parameters create a new `JobInstance` and can re-run from the beginning. Restarting the same logical job requires keeping identifying parameters stable.

## Graceful Stop Design Principles

When implementing operator stop in production, determine:

1. Where do operators retrieve the exact `JobExecution ID`?
2. Which roles are authorized to issue stop requests?
3. How does the response API distinguish request accepted from execution stopped?
4. Do chunks/tasklets have safe stop points and bounded processing durations?
5. Do database, HTTP, and broker calls have appropriate timeouts?
6. Do readers/writers have checkpoints for restarting?
7. Do non-transactional side effects have idempotency or an outbox?
8. How are parallel branches, partition workers, and child jobs monitored and stopped?
9. Do job restarts reuse the same identifying parameters?
10. Does monitoring alert on executions stuck in `STOPPING` for too long?

A sound stop capability follows three clear steps: issue the request via `JobOperator`, monitor status until the execution genuinely stops, and provide restart details based on checkpoints and identifying parameters. Never edit metadata directly to force status; let Spring Batch complete the step/job lifecycle.

## Summary

Operators use `JobOperator.stop(jobExecutionId)` to request stopping a specific run. Status normally moves from `STARTED` to `STOPPING`, then `STOPPED` when the step processes the signal at a safe point. Stopping is cooperative/graceful: the current chunk or `Tasklet.execute` call usually needs to finish or roll back before the step stops; blocked processors and I/O can lengthen stop times. `STOPPING` is not a terminal status and API acceptance does not mean the job has stopped. Committed chunks persist; restarts usually reuse the same identifying parameters and saved checkpoints. Distinguish `STOPPED` from `FAILED`, `ABANDONED`, and process kills; with parallel flows or parent/child jobs, inspect all related executions rather than looking only at parent status.
