# JobOperator and Control Operations in Spring Batch

## 1. What Problem Does JobOperator Solve?

In a batch processing system, launching a Job is only the first step. Once a Job goes into operations, an administrator or scheduler also needs to know which Jobs are running, proactively stop a run, resume failed work, start the next batch, or recover an execution stuck after a server crash.

`JobOperator` is **Spring Batch**'s Job lifecycle control API. It coordinates with metadata infrastructure to perform Job-level operations, rather than directly invoking individual Tasklets, ItemReaders, ItemProcessors, or ItemWriters.

After this lesson, you will be able to:

- Distinguish `start`, `restart`, and `startNextInstance`.
- Understand why `stop` is a **controlled stop request** rather than an immediate thread termination command.
- Handle `FAILED`, `STOPPED`, `ABANDONED`, and executions still `STARTED` after a process dies.
- Read status from `JobRepository` and recognize the difference between `BatchStatus` and `ExitStatus`.
- Implement a Job control layer with **Spring Batch 6.x**, while translating concepts back to **Spring Batch 5.2.x** APIs.
- Design safe operational controls in applications with schedulers, HTTP APIs, and multiple workers.

## 2. JobOperator in the Spring Batch Architecture

~~~text
Scheduler / REST Admin / CLI / JMX
                   |
                   v
              JobOperator
                   |
        +----------+-----------+
        |          |           |
        v          v           v
   JobRegistry  JobRepository  Job / Steps
    (Which Jobs  (Metadata,     (Execute
     can run)    checkpoints)   business logic)
                   |
                   v
             BATCH_* tables
                   |
                   v
             JobExecution
              StepExecution
             ExecutionContext
~~~

The components have distinct responsibilities:

| Component | Responsibility |
| --- | --- |
| `Job` | Defines the unit of work and Step flow. |
| `JobOperator` | Controls starting new runs, restarting, stopping, abandoning, or recovering executions depending on the version's API. |
| `JobRepository` | Stores and queries JobInstance, JobExecution, StepExecution, status, and checkpoints. |
| `JobRegistry` | Manages available Job definitions by name, supporting control across multiple Jobs. |
| `JobParameters` | Input arguments, where `identifying` parameters determine JobInstance identity. |
| `JobExecution` | A single execution attempt of a JobInstance; stores ID, status, timestamps, and errors. |
| `ExecutionContext` | State persisted across executions, especially when restarting a Step. |

**Key difference between the two major version lines:**

- **Spring Batch 5.2.x:** `JobOperator` is designed as an operational interface using Job names, execution IDs, and simple data—for example `start(String, Properties)`, `restart(long)`, `stop(long)`. `JobLauncher` is a separate API typically used to launch Jobs from application code.
- **Spring Batch 6.x:** `JobOperator` **extends `JobLauncher`** and supports strongly typed operations: `start(Job, JobParameters)`, `restart(JobExecution)`, `stop(JobExecution)`, `abandon(JobExecution)`, `startNextInstance(Job)`. Older methods accepting IDs or Job names may still exist but are marked **deprecated**. Metadata queries should be done through `JobRepository` and Job listings through `JobRegistry`.

Because the APIs differ, the main Java examples below use **Spring Batch 6.x**, while the closing section details how to apply them in 5.2.

## 3. Understanding Identity Before Controlling a Job

To operate jobs correctly, you must distinguish **JobInstance** and **JobExecution**.

~~~text
Job name = importOrders
Identifying JobParameters = businessDate: 2026-11-16
                       |
                       v
                 JobInstance #52
                    /       \
                   v         v
      JobExecution #400   JobExecution #401
         FAILED               COMPLETED
        first run              restart
~~~

With the same Job name and the same **set of identifying JobParameters**, Spring Batch resolves the same JobInstance. A restart creates a new JobExecution for the existing JobInstance, not a new data batch.

Example:

~~~java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
~~~

`businessDate` is an identifying parameter; `requestedBy` is merely non-identifying input metadata. Changing `businessDate` means requesting a different JobInstance. Changing a non-identifying parameter does not alter JobInstance identity, though you must still account for the Job's business constraints.

**Do not arbitrarily add an identifying timestamp or `run.id` on restart.** Doing so creates a new JobInstance and can reprocess already-handled data. When you want to resume the same failed batch, use the `restart` API on the appropriate execution.

## 4. Main Operations of JobOperator

| Operation | Purpose | Important Result or Constraint |
| --- | --- | --- |
| `start(Job, JobParameters)` (6.x) | Start processing with a Job and parameters. | Returns `JobExecution`; duplicate parameters/job instances may be rejected or follow existing policy. |
| `startNextInstance(Job)` | Start a **new** JobInstance using a `JobParametersIncrementer`. | Use when the next batch is needed; **not** a substitute for restarting a failed batch. |
| `restart(JobExecution)` | Resume a JobInstance from a `FAILED` or `STOPPED` execution. | Produces a new JobExecution; succeeds only if the Job allows restart and metadata is valid. |
| `stop(JobExecution)` | Request a running Job to stop. | Returns whether the signal was accepted; status may stay `STOPPING` before reaching `STOPPED`. |
| `abandon(JobExecution)` | Mark an execution as no longer to be resumed. | Once `ABANDONED`, the framework will not restart this execution. |
| `recover(JobExecution)` (6.x) | Recover metadata for an execution stuck in `STARTED` after an abrupt shutdown. | Marks it `FAILED` and sets a recovery flag so it can be restarted when safe. |
| Query `JobRepository` / `JobRegistry` | Inspect status, history, and registered Jobs. | In 6.x prefer these APIs over legacy `get...` methods on JobOperator. |

Job control operates on **persisted state**. If the database holding `BATCH_*` tables loses data, JobOperator cannot automatically infer remaining checkpoints from business tables.

## 5. BatchStatus States and Control Flow

`BatchStatus` describes the technical state of an execution.

| Status | Meaning | Typical Action |
| --- | --- | --- |
| `STARTING` | Framework is preparing to run. | Monitor; do not send a duplicate launch request. |
| `STARTED` | Execution is active. | Monitor or request stop if needed. |
| `STOPPING` | Stop request sent, but Job has not finished yet. | Wait for terminal status; do not restart prematurely. |
| `STOPPED` | Stopped in a controlled manner. | Can restart if the Job permits. |
| `FAILED` | Execution ended due to an error. | Analyze root cause, fix data/conditions, and restart. |
| `COMPLETED` | Execution finished. | Do not restart the same completed JobInstance. |
| `ABANDONED` | Execution was abandoned. | Do not restart through normal mechanisms. |
| `UNKNOWN` | Metadata cannot reliably determine status. | Investigate before making any changes. |

Common flow:

~~~text
               start
                 |
                 v
              STARTING
                 |
                 v
               STARTED
              /   |   \
             /    |    \
       success   error  stop request
           |      |          |
           v      v          v
        COMPLETED FAILED   STOPPING
                                 |
                                 v
                              STOPPED

    FAILED / STOPPED -- restart --> STARTING (new execution)
    ABANDONED ---------X--------> restart
~~~

Distinguish **`BatchStatus`** and **`ExitStatus`**:

- `BatchStatus` indicates the execution lifecycle state managed by the framework.
- `ExitStatus` lets a Step/Job emit a more detailed exit signal, such as `COMPLETED WITH SKIPS` or custom flow-control codes.
- A Job with `BatchStatus.COMPLETED` can still carry a custom `ExitStatus`; operations systems should not infer everything from an exit code string while ignoring BatchStatus.

In an HTTP endpoint or dashboard, display status, exit code, execution ID, start/end timestamps, and error summaries if any. Never use a single boolean `running` flag to represent all states.

## 6. The start Operation: Launching a Job

In Spring Batch 6.x, the primary API form is:

~~~java
JobExecution execution = jobOperator.start(importOrdersJob, params);
long executionId = execution.getId();
~~~

Where:

- `importOrdersJob` is the configured Job bean.
- `params` is a JobParameters instance valid for the Job's validator.
- `executionId` is used to look up and control **that exact run**; do not control jobs by grabbing a random execution from all running Jobs.

**Note on using `JobParametersIncrementer`:** per the Spring Batch 6 Javadoc, if a Job defines an incrementer, `start(Job, JobParameters)` may compute the next parameter set using the incrementer and ignore the supplied parameter set. Therefore, if business logic requires precise control by processing date, clearly understand the Job's incrementer configuration and parameter selection. The `start` example using `businessDate` here assumes the Job **does not** attach an incrementer.

### Synchronous vs. Asynchronous Execution

A Job can run immediately on the calling thread or be dispatched to a `TaskExecutor`. Hence, the moment `start` returns **is not necessarily** when the Job finishes:

~~~text
Synchronous execution:
request --> start --> Job runs --> COMPLETED/FAILED --> response

Asynchronous execution:
request --> start --> JobExecution ID --> response
                   |
                   +--> TaskExecutor --> Job runs --> final status
~~~

In Spring Batch 6, `TaskExecutorJobOperator` supports execution via a TaskExecutor. With a synchronous executor, `start` blocks until the Job completes. With an asynchronous executor, the response may return while the Job is still `STARTING` or `STARTED`. Configure an executor suited to your application architecture and **always re-check status via JobRepository** when you need the final outcome.

For an asynchronous launch REST API, an appropriate response is **202 Accepted** with the execution ID and a tracking URL. Do not report "Job succeeded" just because `start` did not throw an exception.

## 7. The startNextInstance Operation: Creating a New Batch

`startNextInstance` uses the `JobParametersIncrementer` attached to a Job to generate new identifying parameters.

Example: a Job runs consecutive experimental batches and uses `run.id` to distinguish JobInstances:

~~~java
@Bean
Job demoJob(JobRepository repository, Step loadStep) {
    return new JobBuilder("demoJob", repository)
            .incrementer(new RunIdIncrementer())
            .start(loadStep)
            .build();
}
~~~

Once the Job has an appropriate incrementer:

~~~java
JobExecution next = jobOperator.startNextInstance(demoJob);
~~~

This method creates a **new JobInstance** with the next parameter set, even if the previous instance failed. It does not restore state from a failed instance.

| Scenario | Recommended Action |
| --- | --- |
| Nov 16 Job failed after writing partial data | `restart` the failed execution after fixing the root cause. |
| Nov 16 Job completed, want to run Nov 17 batch | `start` with the new businessDate, or `startNextInstance` if the incrementer generates the next date. |
| Experiment Job needs to run next version `run.id=42` | `startNextInstance` with an incrementer advancing `run.id`. |
| Old data failed and caller invokes `startNextInstance` to "fix" it | Risks creating a new batch and re-writing data; requires duplicate/idempotency controls. |

An incrementer is a **business strategy**. Incrementing `run.id` only creates a new identity; it does not automatically change source data. If a Job truly processes by date, you need a business-date incrementer or explicit `businessDate` parameter passing.

## 8. The restart Operation: Resuming an Old JobInstance

When the first JobExecution ends as `FAILED` or `STOPPED`, JobOperator can create a new execution within the **same JobInstance**:

~~~java
JobExecution previous = jobRepository.getJobExecution(failedExecutionId);

if (previous == null) {
    throw new IllegalArgumentException("Unknown execution");
}

JobExecution retried = jobOperator.restart(previous);
~~~

Restart relies on metadata persisted in `JobRepository`, including the `ExecutionContext` of Steps with recoverable state. By default, Steps already marked `COMPLETED` are skipped on restart; failed or stopped Steps continue per Job/Step logic. Exceptions apply when a Step uses `allowStartIfComplete(true)` or special flow configuration.

### Checkpoint Example

Suppose a Job reads 5 items and commits in chunks of 2 items:

~~~text
Execution #101:
  Item 1,2  -> COMMIT
  Item 3    -> error in processor
  Job       -> FAILED

Execution #102 after restart:
  Open reader from saved checkpoint
  Item 3,4  -> COMMIT
  Item 5    -> COMMIT
  Job       -> COMPLETED
~~~

A properly restarted Job ensures complete final data without duplicate writes; the new `JobExecution` has a different ID but shares the same `JobInstance` as the first run.

**Do not treat restart as an exactly-once guarantee across every system.** If a writer calls an API, sends emails, or publishes to a message broker outside the metadata transaction, side effects may already have succeeded before the Job failed. Use idempotency keys, unique constraints, outboxes, or reconciliation whenever outcomes span external systems.

### Reasons a Restart Can Fail

- The Job already completed for those identifying JobParameters.
- The Job is configured to disallow restarts, such as `preventRestart()`.
- A JobExecution is currently running or `STOPPING`.
- Metadata or ExecutionContext was deleted, corrupted, or became incompatible with the code version.
- The Job to recover is no longer defined/registered under that name.
- A Step exceeded `startLimit` or hit an incompatible configuration on restart.
- The execution is `ABANDONED`.

When a restart fails, inspect the exception, persisted state in JobRepository, and Step history before trying again. Generating a new identifying parameter may create a different JobInstance and mask the real error.

## 9. The stop Operation: Controlled Stopping

When invoking:

~~~java
JobExecution running = jobRepository.getJobExecution(executionId);
boolean accepted = jobOperator.stop(running);
~~~

`accepted == true` only confirms **the stop signal was sent/accepted**. It does not prove the Job has terminated. While the framework processes the signal, status may transition through:

~~~text
STARTED -> STOPPING -> STOPPED
             |
             +-- current reader / tasklet / writer
                 may still be executing
~~~

Spring Batch typically checks the stop signal only when the framework regains control, such as between iterations/chunks or after a Tasklet returns. If business code is blocked on a hung network API call, running a long SQL statement, or blocking a thread, the Job may not stop immediately. `stop` is not equivalent to `Thread.stop()`, `kill -9`, or rolling back all side effects that already happened.

When requesting a stop from an admin UI:

1. Obtain the **exact running JobExecution ID**.
2. Call `stop`; return "request accepted" or `STOPPING` status if applicable.
3. Re-query JobRepository afterward (via scheduled polling, events, or a status endpoint) until a terminal status like `STOPPED` appears.
4. Allow restart only after confirming the old execution has stopped and committed/rolled-back data is consistent.

If fast stopping is required, design Tasklets/readers/processors with timeouts, interruption responsiveness, or shorter chunks; do not try to force JobOperator to kill threads.

### What Happens to Already-Committed Data?

`stop` is a controlled stop, **not an undo operation**. Previously committed chunks remain. On restart, a Step designed as restartable can resume from its checkpoint. For non-transactional writers or external side effects, an idempotency strategy is required.

## 10. The abandon Operation: Closing Without Resuming

`abandon` marks a JobExecution as `ABANDONED`. The framework disallows restarting executions closed under this policy.

~~~java
JobExecution stale = jobRepository.getJobExecution(executionId);

// Execute only after confirming the execution is no longer running.
JobExecution abandoned = jobOperator.abandon(stale);
~~~

This fits cases where a run cannot/must not continue by operational decision—for example, source data was canceled and must be reprocessed under a controlled new JobInstance. It is a consequential business decision, not a routine cleanup step.

**Never call abandon on a genuinely running execution.** The API rejects it when it sees a running execution; when a process died leaving metadata as `STARTED`, handle the state via a recovery procedure first. Do not use abandon as a way to "clear errors" to make a dashboard look clean. Previously written business data is not automatically reverted.

Beyond JobExecution, Spring Batch also uses `ABANDONED` at the **StepExecution** level for certain flow-control and restart scenarios. Distinguish which object is being modified so you do not infer that an abandoned Step means the entire Job was abandoned.

## 11. The recover Operation in Spring Batch 6.x

If a JVM crashes abruptly, or a database or container loses power, there may be no opportunity to update metadata from `STARTED` to `FAILED` or `STOPPED`. JobRepository then sees an execution that looks active even though the real process is gone.

Spring Batch 6 adds:

~~~java
JobExecution stuck = jobRepository.getJobExecution(executionId);

// Confirmed that the old process truly stopped and checkpoints are safe.
JobExecution recovered = jobOperator.recover(stuck);

// Only then decide to run again.
JobExecution resumed = jobOperator.restart(recovered);
~~~

Per the 6.x API, `recover` marks an execution stuck in `STARTED` as `FAILED` and records `recovered=true` in the execution context to enable restartability.

**Preconditions before calling recover:**

- Verify the process/worker owning the execution **is no longer running**; check pod/process/node status, heartbeats, or reliable leases.
- Confirm data writes from the old execution have finished or are reconciled consistently; avoid running two executions of the same JobInstance concurrently.
- Inspect checkpoints and non-transactional effects; requests already sent to external systems may have succeeded.
- Decide whether to restart the same instance, abandon it, or initiate a manual reconciliation workflow.
- Record the operator, reason, and execution ID for audit.

`recover` does not automatically fix business data, undo completed HTTP calls, or guarantee checkpoint safety if a writer is not idempotent.

### Shutdown Hook in Spring Batch 6

Spring Batch 6 provides `JobExecutionShutdownHook` to attempt sending a stop request during controlled JVM shutdown:

~~~java
Thread hook = new JobExecutionShutdownHook(
        jobExecution, jobOperator);
Runtime.getRuntime().addShutdownHook(hook);
~~~

This hook helps in shutdown scenarios where the JVM allows shutdown hooks to run. It cannot guarantee execution when a process is forcibly killed (e.g., SIGKILL), on kernel panics, or on power loss. It is a helper safeguard, not a replacement for recovery planning and idempotency.

## 12. Control Layer Example in Spring Batch 6.x

The example below assumes:

- The Spring context already provides a `JobOperator` bean and a compatible **JDBC JobRepository**.
- A Job bean named `importOrdersJob` exists; this Job **does not attach a JobParametersIncrementer** so `businessDate` acts as the caller-supplied identifying parameter.
- The caller has already been authenticated and authorized before entering the service. The example is a service class, not a REST endpoint.

**BatchControlService.java**:

~~~java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.job.Job;
import org.springframework.batch.core.job.JobExecution;
import org.springframework.batch.core.job.parameters.JobParameters;
import org.springframework.batch.core.job.parameters.JobParametersBuilder;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class BatchControlService {

    private final JobOperator jobOperator;
    private final JobRepository jobRepository;
    private final Job importOrdersJob;

    public BatchControlService(
            JobOperator jobOperator,
            JobRepository jobRepository,
            @Qualifier("importOrdersJob") Job importOrdersJob) {
        this.jobOperator = jobOperator;
        this.jobRepository = jobRepository;
        this.importOrdersJob = importOrdersJob;
    }

    // Run a batch identified by business date.
    public JobExecution startForDate(String businessDate) throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .toJobParameters();

        return jobOperator.start(importOrdersJob, parameters);
    }

    // Return the persisted status (which may change after the call).
    public BatchStatus status(long executionId) {
        return requireExecution(executionId).getStatus();
    }

    // Send stop request; boolean does not mean already STOPPED.
    public boolean requestStop(long executionId) throws Exception {
        JobExecution execution = requireExecution(executionId);
        return jobOperator.stop(execution);
    }

    // Create a new JobExecution under the same failed/stopped JobInstance.
    public JobExecution restart(long executionId) throws Exception {
        JobExecution execution = requireExecution(executionId);
        BatchStatus status = execution.getStatus();

        if (status != BatchStatus.FAILED
                && status != BatchStatus.STOPPED) {
            throw new IllegalStateException(
                "Restart requires FAILED or STOPPED: " + status);
        }

        return jobOperator.restart(execution);
    }

    // Call only after verifying no worker is still executing.
    public JobExecution recoverAfterCrash(long executionId) {
        JobExecution execution = requireExecution(executionId);

        if (execution.getStatus() != BatchStatus.STARTED) {
            throw new IllegalStateException(
                "Recovery requires stale STARTED execution");
        }

        return jobOperator.recover(execution);
    }

    // Decide to abandon an execution that can no longer be resumed.
    public JobExecution abandon(long executionId) throws Exception {
        JobExecution execution = requireExecution(executionId);
        return jobOperator.abandon(execution);
    }

    private JobExecution requireExecution(long executionId) {
        JobExecution execution = jobRepository.getJobExecution(executionId);
        if (execution == null) {
            throw new IllegalArgumentException(
                "Unknown JobExecution: " + executionId);
        }
        return execution;
    }
}
~~~

**Reading the example accurately:**

- `startForDate` fits a Job identified by `businessDate`. Avoid designs where every request generates a random `run.id` when business rules require blocking duplicate batches.
- `status` re-reads from JobRepository; a previously returned `JobExecution` object may be stale if the Job runs asynchronously.
- `requestStop` returns **whether the signal was sent**. Clients must re-check whether the Job actually transitioned to `STOPPED`.
- `restart` pre-checks status to produce clear messages. True enforcement remains with the framework, since status can change between reading and invoking (race condition).
- `recoverAfterCrash` only performs the technical check for `STARTED`. Verifying that the old worker is dead and data is safe **must be done at the operations layer** before calling this method.
- `abandon` is a consequential operation; place it behind an approval step/operational workflow when required by the application.
- The `throws Exception` declarations keep the example concise; production code should map each Batch exception category to structured business responses.

### If You Need to Select a Job by Name

In systems with multiple Jobs, do not grab an arbitrary Job bean from the ApplicationContext. Use `JobRegistry` to resolve registered Jobs and `JobRepository` to inspect existing JobExecutions.

In Spring Batch 6, query methods such as `JobOperator.getJobNames()`, `getRunningExecutions(String)`, `getSummary(long)`, and legacy lookup methods are deprecated; instead use:

~~~java
// Registered Jobs available for launching:
var registeredNames = jobRegistry.getJobNames();

// Running JobExecutions from metadata:
var running = jobRepository.findRunningJobExecutions("importOrdersJob");

// Look up an execution by ID:
var execution = jobRepository.getJobExecution(executionId);

// Execution history of a JobInstance:
var history = jobRepository.getJobExecutions(execution.getJobInstance());
~~~

Depending on the deployment topology, the list of **registered** Jobs may differ from the list of Jobs that **have historical metadata**. A Job with history in the database whose code/bean was removed cannot necessarily be relaunched from metadata alone.

## 13. Controlling from a REST API or Scheduler

An admin application might expose an endpoint set like the following (an interface design only, not a complete controller):

| HTTP | Example Path | Meaning | Appropriate Response |
| --- | --- | --- | --- |
| `POST` | `/admin/batch/jobs/import-orders/executions` | Start Job with `businessDate`. | 202 + executionId if async; report actual status if sync. |
| `GET` | `/admin/batch/executions/{id}` | Read BatchStatus, ExitStatus, timestamps, errors. | 200 with data read from repository. |
| `POST` | `/admin/batch/executions/{id}/stop` | Send stop. | 202 / "request accepted" message; keep polling. |
| `POST` | `/admin/batch/executions/{id}/restart` | Restart FAILED/STOPPED execution. | 202 + new executionId if handled asynchronously. |
| `POST` | `/admin/batch/executions/{id}/abandon` | Mark abandoned. | Allow only when policy agrees and execution is not running. |
| `POST` | `/admin/batch/executions/{id}/recover` | Recover stuck metadata. | Restrict to authorized operations roles after verifying worker is dead. |

Rules to design in from the start:

1. **Authentication and authorization** for every state-changing operation. Read permissions for executions can be broader than permissions for stop/restart/abandon/recover.
2. **Audit logging** recording caller, Job name, execution ID, reason, timestamp, and outcome. Do not print sensitive values from JobParameters to logs.
3. **Do not rely on a recently read status as a concurrency lock.** Two admins might click restart simultaneously; the framework and database metadata must protect state consistency.
4. **Define duplicate-request policies.** The same `businessDate` should not spawn multiple JobInstances if business rules allow only one batch. HTTP retries need idempotency.
5. **Return meaningful errors.** Missing executions can map to 404; invalid states or JobInstance conflicts to 409; infrastructure errors logged separately from business errors.
6. **Never expose an endpoint to kill threads by Job ID.** Stop is cooperative control; killing processes is an infrastructure-level action with different consequences.

### Scheduler in a Multi-Instance Environment

If multiple nodes control Jobs, all must share a common metadata store and compatible configuration. JobRepository enforces JobInstance uniqueness constraints and detects running executions via metadata, but it does not completely replace scheduler coordination, leases, leader election, or business idempotency.

For example, if two schedulers simultaneously request the same `businessDate`, only one can create a valid execution per JobInstance rules; the other will hit a conflict error. The scheduler layer must handle the error rather than immediately changing `run.id` to "retry" when data is not meant for two independent batches.

## 14. Error Handling and Abnormal States

| Situation | Symptom | Resolution |
| --- | --- | --- |
| Starting a Job already completed with same identifying params | JobInstance already complete error | Confirm whether a new batch is genuinely needed; if so, supply valid new identifying params. |
| Start/restart while execution is still running | Running/conflict error | Do not launch parallel execution; re-read status and handle duplicate request. |
| Restarting a Job that disallows restart | `JobRestartException` or related exception | Check `preventRestart`, Step limits, and Job configuration. |
| Stop returns true but status stays STARTED/STOPPING | Tasklet/chunk has not yielded control yet | Monitor, inspect timeouts, and check stop responsiveness in business code. |
| Execution stuck STARTED after crash | Worker died before updating metadata | Verify environment; on Batch 6 consider `recover` then `restart`. |
| Execution is ABANDONED | JobInstance/execution cannot be restarted normally | Follow operational/reconciliation policy. |
| Cannot find Job name to restart | JobRegistry lacks the Job definition | Re-register the matching Job code/version or execute compatible migration steps. |
| ExecutionContext cannot be read/deserialized | Serializer, schema, or data structure version mismatch | Restore metadata compatibility per plan; never reset metadata arbitrarily. |
| Writer called external system then Step failed | Side effect already occurred while metadata says FAILED | Apply idempotency/reconciliation; restart only after understanding consequences. |
| Job fails repeatedly on the same record | Input remains invalid or skip/retry policy is unsuitable | Fix source/validation or handle failed record per process; do not spam restart. |

**Do not manually edit the `STATUS` column in `BATCH_JOB_EXECUTION` as a routine operation.** Metadata spans multiple tables, versions, and contexts that depend on one another. If manual intervention is unavoidable in an exceptional incident, back up first, confirm the real worker is stopped, reconcile transactions, and follow a controlled procedure.

## 15. Comparing 5.2 and 6.x APIs

| Operation | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| Start Job | `start(String jobName, Properties parameters)` | `start(Job job, JobParameters params)` |
| Restart | `restart(long executionId)`, returns execution ID | `restart(JobExecution previous)`, returns JobExecution |
| Stop | `stop(long executionId)` | `stop(JobExecution execution)` |
| Start next batch | `startNextInstance(String jobName)` | `startNextInstance(Job job)` |
| Abandon | `abandon(long executionId)` | `abandon(JobExecution execution)` |
| Recover stuck STARTED execution | Lacks 6.x's new `recover` API | `recover(JobExecution execution)` |
| List running executions | `getRunningExecutions(jobName)` on JobOperator | Prefer `JobRepository.findRunningJobExecutions(jobName)` |
| Look up by ID | `getSummary`, `getStepExecutionSummaries`, `JobExplorer` | Prefer `JobRepository.getJobExecution` and repository queries |
| List available Jobs | `JobRegistry` or `getJobNames()` | Prefer `JobRegistry.getJobNames()` |
| JobLauncher | Separate API | JobOperator extends JobLauncher |

### Example Using JobOperator in Spring Batch 5.2

In Spring Batch 5.2, operations take a **Job name** or **execution ID**. The snippet below illustrates **separate individual calls**, not a sequential call chain on a single execution:

~~~java
import java.util.Properties;
import org.springframework.batch.core.launch.JobOperator;

// Assumes Job "importOrders" is registered in JobRegistry.
Properties properties = new Properties();
properties.setProperty("businessDate", "2026-11-16");

// Start a JobInstance with the declared parameters:
Long startedId = jobOperator.start("importOrders", properties);

// For an existing FAILED or STOPPED execution:
Long restartedId = jobOperator.restart(failedExecutionId);

// Send stop signal to a running execution:
boolean accepted = jobOperator.stop(runningExecutionId);

// Create a new JobInstance using JobParametersIncrementer:
Long nextId = jobOperator.startNextInstance("importOrders");

// Abandon a no-longer-running execution:
jobOperator.abandon(staleExecutionId);
~~~

In Batch 5.2, `JobOperator` is provided via appropriate Batch configuration such as `@EnableBatchProcessing` (since Batch 5.0) or compatible Spring Boot configuration. A Job must be properly registered by name for name-based start/restart APIs to work.

**Upgrade note:** legacy ID/name-based APIs may still exist in Spring Batch 6.0 but are marked deprecated and slated for removal in future releases. When building new systems on 6.x, use the `Job`/`JobExecution` overloads and move lookups to repository/registry. Do not mechanically swap imports between 5.2 and 6.x while leaving method signatures unchanged.

## 16. Testing Control Operations

An operational test suite should verify both **status** and **actual data**, not just that an API call succeeded.

| Scenario | How to Test | What to Assert |
| --- | --- | --- |
| First start | Start with fixed identifying params | New JobInstance and JobExecution exist; metadata persisted. |
| Duplicate start on COMPLETED batch | Start again with same identity | Rejected per policy; data is not written twice. |
| Restart after FAILED | Inject failure during processing, fix condition, restart | Two JobExecutions, one JobInstance; final data complete, no duplicates. |
| Restart after STOPPED | Use a long Step and send stop | Restart only after STOPPED; checkpoint works. |
| Non-instant stop | Tasklet intentionally runs long, send stop mid-work | Intermediate status observed and stop completes after code yields control. |
| StartNextInstance | Job using an incrementer | New JobInstance, identifying params incremented as expected. |
| Abandon | Non-running execution | Status is ABANDONED; restart is rejected. |
| Recover (6.x) | Simulate STARTED metadata after process stopped | Recover sets FAILED; restart creates new execution if data is safe. |
| Concurrent requests from two callers | Send concurrent start/restart with same identity | Does not spawn two duplicate business processes outside policy. |
| Stop via async executor | Start async then send stop | API returns signal before terminal status; final status read back from repository. |

Tests for `stop` and recovery need deterministic synchronization—for example, a `CountDownLatch` to know the Tasklet has started before sending stop. Avoid arbitrary `Thread.sleep` calls that make tests flaky. Never use force kill to simulate a graceful stop.

For **real crash-recovery** tests, use two separate processes and a persistent database. Single-JVM tests only prove restart/status logic under active test infrastructure.

## 17. Sample Operational Workflow

Suppose the daily order import Job for Nov 16 runs on a schedule:

~~~text
1. Scheduler start(importOrders, businessDate=2026-11-16)
   |
   v
2. Operator receives executionId=500 and monitors via repository
   |
   +-- COMPLETED --> finalize results, save audit and metrics
   |
   +-- FAILED -----> inspect Step/ExitStatus, verify data
   |                   |
   |                   +-- fix error --> restart(execution #500)
   |                                       |
   |                                       +-- execution #501
   |
   +-- STARTED ----> maintenance needed?
                       |
                       +-- stop(#500)
                              |
                              v
                           STOPPING
                              |
                              v
                           STOPPED
                              |
                              +-- restart(#500) when ready
~~~

If a node dies while the repository still records `STARTED`, confirm the execution is no longer running and data is consistent; on 6.x you can use `recover`. If the batch is permanently canceled, follow an audited `abandon` workflow. To process Nov 17, create a **new JobInstance** with new business parameters; do not confuse it with restarting Nov 16.

## 18. Practice Exercises

**Exercise 1 — Write a control service.** Create a Job named `importOrdersJob` accepting `businessDate`, and build a service with start, status, stop, and restart. Store execution IDs and use JobRepository to query status as needed.

**Exercise 2 — Stop checkpoint.** Create a chunk-oriented Step processing 20 items with chunk size 5. Send stop after at least one chunk has committed, observe intermediate states and restart outcome. Verify already-committed items are not written twice.

**Exercise 3 — Distinguish new batch vs. restart.** Configure a JobParametersIncrementer and call `startNextInstance` after a Job fails. Compare the JobInstance ID against `restart` on the same failed Job, and explain when to use each API.

**Exercise 4 — Simulate a crash.** On a persistent test database, persist a STARTED execution's metadata and terminate the test process in a controlled way. In a second process, verify the old process has ended and test the recover/restart flow on Batch 6.

**Exercise 5 — Operations dashboard.** Design a UI showing Job name, identifying JobParameters, execution ID, BatchStatus, ExitStatus, and timestamps. Enable Stop only when appropriate; show Restart only for FAILED/STOPPED; require confirmation/audit where required by the environment.

**Exercise 6 — Prevent duplicate requests.** Have two clients concurrently request running the same `businessDate`. Observe the response when one request is rejected and ensure the system does not auto-generate a new `run.id` to mask the conflict.

The expected outcome of these exercises is understanding **persisted state, JobInstance identity, commit boundaries, and framework control**, rather than just executing a few API calls.

## 19. Official References

- [Spring Batch 6 — Advanced Metadata Usage: JobOperator, stop, recover, abandon](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html)
- [Spring Batch 6 — JobOperator API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobOperator.html)
- [Spring Batch 6 — JobRepository API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/repository/JobRepository.html)
- [Spring Batch 6 — TaskExecutorJobOperator API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/support/TaskExecutorJobOperator.html)
- [Spring Batch 6 — JobExecutionShutdownHook API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/support/JobExecutionShutdownHook.html)
- [Spring Batch 5.2 — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html)
- [Spring Batch 5.2 — JobOperator API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/launch/JobOperator.html)

