# Job Completion Signals in Spring Batch

## 1. What Is a Job Completion Signal?

When a Spring Batch job is triggered via cron, an API, or a scheduling system, two completely different moments occur:

1. **The job has been launched**: `JobLauncher` accepted the request and created a `JobExecution`.
2. **The job has finished**: `JobExecution` reached a terminal status, and processing outputs plus required metadata are observable.

A **job completion signal** is information sent to another system or an orchestration component indicating that **a specific run (`JobExecution`) has finished**, along with its outcome. This is an integration/design concept; Spring Batch provides lifecycle callbacks and metadata to implement it, rather than automatically guaranteeing delivery of a completion message to every external system.

For example, `dailySettlement` is run by the scheduler at 01:00 to reconcile the previous day's transactions. Once it finishes, the system needs to:

- If successful: allow sending reports, open data distribution steps, or trigger downstream jobs.
- If failed: emit alerts, hold unverified output data, and await intervention/restart.
- If stopped: report paused status and never assume success.
- For every outcome: record `jobExecutionId` so operators can trace it.

A good signal clearly identifies **which job, which execution, which business date, what status, and how it was observed**.

### Distinguishing Signal Types

| Signal | When created | Proves the job finished running? |
|---|---|---|
| Scheduler trigger | Cron or orchestrator reached trigger time | **No** |
| Job launch accepted | `JobLauncher.run(...)` created/returned `JobExecution` | **Not necessarily**; the launcher may run asynchronously |
| Step completed | A `StepExecution` finished | **No**; the job may have further steps |
| `JobExecutionListener.afterJob` | Framework reached the job termination phase | Yes, per current `JobExecution` status; local callback does not guarantee delivery to external receivers |
| `JobRepository` terminal status | `JobExplorer` observes `COMPLETED`, `FAILED`, or `STOPPED` | Yes for that execution, subject to metadata freshness |
| Durable completion event | Event record durably persisted and delivered to consumers | Suitable for orchestration when paired with IDs, status, and deduplication/loss handling |

A job ending in `FAILED` **is still “finished,”** but **is not “successfully completed.”** Name signals clearly: `JobFinished` for any terminal outcome, `JobSucceeded` only when genuinely `COMPLETED`.

## 2. Which Object Confirms Completion?

In Spring Batch, `JobExecution` represents **one execution attempt** of a `JobInstance`. It holds status, parameters, and error details. Commonly used properties:

| Property | Purpose |
|---|---|
| `JobExecution.getId()` | Unique technical ID for the run; used for lookups and idempotency |
| `getJobInstance().getJobName()` | Job name, e.g., `dailySettlement` |
| `getJobParameters()` | Parameters such as `businessDate=2025-05-12` |
| `getStatus()` | Execution `BatchStatus` |
| `getExitStatus().getExitCode()` | Exit code, customizable |
| `getStartTime()` / `getEndTime()` | Start and end timestamps recorded by the framework |
| `getAllFailureExceptions()` | Failure root-cause details for logging/observability |

**`BatchStatus` and `ExitStatus` differ**:

- `BatchStatus` represents the framework-managed execution state: `STARTING`, `STARTED`, `STOPPING`, `STOPPED`, `COMPLETED`, `FAILED`, `ABANDONED`, `UNKNOWN`.
- `ExitStatus` is an exit code customizable per business requirements, such as `COMPLETED_WITH_WARNINGS`. It is especially useful when driving step flow transitions.
- If downstream requires the job to be **technically successful**, check `BatchStatus.COMPLETED` first. If downstream needs to distinguish “with warnings” or “no data,” inspect the exit code or business metrics as well.

Example:

```text
JobExecution id=501
  jobName      = dailySettlement
  businessDate = 2025-05-12
  BatchStatus  = COMPLETED
  ExitStatus   = COMPLETED_WITH_WARNINGS
```

This execution succeeded in terms of `BatchStatus`, yet the application may choose **not to emit a report-ready signal** when the exit code flags severe warnings. Signal emission rules must follow the business contract, not assumptions based purely on callback names.

### Terminal vs. In-Progress States

```text
STARTING ──────> STARTED ──────> COMPLETED
                    │
                    ├──────────> FAILED
                    │
                    └──> STOPPING ───> STOPPED
```

This diagram illustrates common paths; real systems have exceptions such as startup/stop failures or stale metadata after a process crash. For signaling systems, `STARTING`, `STARTED`, and `STOPPING` **are not completion**.

A consumer may receive event types for:

- `COMPLETED`: terminal outcome of a successful execution.
- `FAILED`: execution ended unsuccessfully, typically with error details.
- `STOPPED`: execution stopped on request or flow transition.
- `ABANDONED`: execution marked abandoned, usually via admin action; distinguish from natural completion.
- `UNKNOWN`: reliable outcome could not be determined; never emit “success.”

If the goal is running downstream **only on success**, never emit a “ready” signal for `STOPPED`, `FAILED`, or `UNKNOWN`.

## 3. Completion Signals in Scheduling Context

A Spring Scheduler may be configured as:

```java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class SettlementSchedule {

    private final SettlementLauncher launcher;

    public SettlementSchedule(SettlementLauncher launcher) {
        this.launcher = launcher;
    }

    @Scheduled(cron = "0 0 1 * * *", zone = "Asia/Ho_Chi_Minh")
    public void startDailySettlement() throws Exception {
        launcher.launchForPreviousBusinessDay();
    }
}
```

For `@Scheduled` to run, the application must enable scheduling, e.g., with `@EnableScheduling` on a configuration class. This snippet **only describes the launch action**; it provides no “job succeeded” condition. Triggering at 01:00 says nothing about when the job completes, as the job may run for 5 minutes, 3 hours, or fail.

### 3.1. Synchronous vs. Asynchronous Launchers

With a `JobLauncher` using a synchronous task executor, `run(...)` normally returns only once the job thread completes. The caller can then inspect the returned status.

With an asynchronous launcher, `run(...)` may return an **in-progress** `JobExecution` while processing continues on another thread.

```text
Scheduler                JobLauncher                Job
    |                         |                       |
    |---- run(params) ------->|                       |
    |                         |----- execute() ------>|
    |<-- JobExecution --------|                       |
    |      (STARTING/STARTED if async)                |
    |                                                 |
    |                         ... processing data ... |
    |                                                 |
    |                         <---- finishes ---------|
```

Therefore, the following code **is unsafe if used to infer job completion across all configurations**:

```java
JobExecution execution = jobLauncher.run(job, parameters);
sendSuccessSignal(); // Wrong: job may still be running or already FAILED.
```

Instead, inspect `execution.getStatus()` only when the launcher is known to be synchronous, or use `afterJob`/metadata monitoring for asynchronous runs.

### 3.2. Capturing a Stable Business Date

A batch running at 01:00 typically processes the previous day's data, and that date should be pinned at launch time and passed in `JobParameters`:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;

public final class SettlementLauncher {

    private final JobLauncher jobLauncher;
    private final Job settlementJob;
    private final Clock clock;
    private final ZoneId businessZone;

    public SettlementLauncher(
            JobLauncher jobLauncher,
            Job settlementJob,
            Clock clock,
            ZoneId businessZone) {

        this.jobLauncher = jobLauncher;
        this.settlementJob = settlementJob;
        this.clock = clock;
        this.businessZone = businessZone;
    }

    public JobExecution launchForPreviousBusinessDay() throws Exception {
        LocalDate businessDate = LocalDate.now(
                clock.withZone(businessZone)
        ).minusDays(1);

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .toJobParameters();

        return jobLauncher.run(settlementJob, parameters);
    }
}
```

Because `businessDate` is an identifying parameter, the same job name and business date represent the same `JobInstance`. If the scheduler fires again while this run is active, Spring Batch may reject the duplicate launch; if the instance already completed, `JobInstanceAlreadyCompleteException` may occur. Handle these per orchestration policy, **never emitting a new completion signal from a failed launch attempt**.

## 4. Simple Approach: `JobExecutionListener.afterJob`

Spring Batch provides `JobExecutionListener` with two callbacks:

- `beforeJob(JobExecution)`: called before the job executes.
- `afterJob(JobExecution)`: called after the job ends **whether it succeeded or failed**.

This is a natural extension point to record audits, update metrics, or emit completion notifications from **within the process executing the job**.

### 4.1. Defining the Completion Signal Payload

```java
import org.springframework.batch.core.BatchStatus;

public record JobCompletionSignal(
        long jobExecutionId,
        String jobName,
        String businessDate,
        BatchStatus batchStatus,
        String exitCode
) {
    public String idempotencyKey() {
        return jobExecutionId + ":finished";
    }
}
```

The key `jobExecutionId + ":finished"` uniquely identifies **one execution's completion event**. If the job `FAILED` and is restarted, the restart gets a new `jobExecutionId` and thus emits a distinct event. If business rules allow only one success report per day, consumers also need a business key by `jobName + businessDate`.

### 4.2. Decoupling Transport from the Listener

```java
public interface CompletionSignalSink {
    void publish(JobCompletionSignal signal);
}
```

This interface can be backed by a message broker, HTTP, an outbox table, or an audit store. Separating the sink allows unit tests to verify the listener without sending real emails or making API calls.

### 4.3. Listener Emitting Signals by Terminal Status

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public final class CompletionSignalListener
        implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(CompletionSignalListener.class);

    private final CompletionSignalSink sink;

    public CompletionSignalListener(CompletionSignalSink sink) {
        this.sink = sink;
    }

    @Override
    public void afterJob(JobExecution execution) {
        BatchStatus status = execution.getStatus();

        if (status != BatchStatus.COMPLETED
                && status != BatchStatus.FAILED
                && status != BatchStatus.STOPPED) {
            log.warn(
                    "Job ended with nonstandard status {}, executionId={}",
                    status,
                    execution.getId()
            );
            return;
        }

        JobCompletionSignal signal = new JobCompletionSignal(
                execution.getId(),
                execution.getJobInstance().getJobName(),
                execution.getJobParameters().getString("businessDate"),
                status,
                execution.getExitStatus().getExitCode()
        );

        try {
            sink.publish(signal);
        } catch (RuntimeException ex) {
            // Log error for observability/reconciliation.
            // Do not assume durable message delivery exists.
            log.error(
                    "Failed to publish completion signal for executionId={}",
                    execution.getId(),
                    ex
            );
        }
    }
}
```

Here `sink.publish(...)` illustrates publishing. If the sink involves network calls, enforce explicit timeouts so the callback never hangs. Catching exceptions shields job termination from a single notification failure, **but can drop the signal** if no storage/reconciliation exists; a later section introduces a more reliable pattern.

**Never use `afterStep` to signal that the entire job is done.** A job has multiple steps; after `afterStep`, subsequent steps may not have run yet or another branch may fail. Place job-level completion signals in `afterJob`.

### 4.4. Registering the Listener on the Job

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SettlementJobConfiguration {

    @Bean
    CompletionSignalListener completionSignalListener(
            CompletionSignalSink sink) {
        return new CompletionSignalListener(sink);
    }

    @Bean
    Job dailySettlementJob(
            JobRepository repository,
            Step validateTransactions,
            Step aggregateTransactions,
            CompletionSignalListener completionSignalListener) {

        return new JobBuilder("dailySettlement", repository)
                .start(validateTransactions)
                .next(aggregateTransactions)
                .listener(completionSignalListener)
                .build();
    }
}
```

`validateTransactions` and `aggregateTransactions` are assumed business steps declared separately. This configuration uses **Spring Batch 5.2.x** builder style. If you forget `.listener(completionSignalListener)`, unit tests calling `afterJob` directly still pass while the listener is never invoked at runtime; add an integration test to catch registration omissions.

## 5. Signal Success Only or Emit Every Terminal Outcome?

Two common contracts exist:

| Contract | Emitted signal | Suitable consumers |
|---|---|---|
| `JobFinished` | `COMPLETED`, `FAILED`, `STOPPED` with attached status | Operations dashboards, auditing, alerting, metrics |
| `JobSucceeded` / `ReportReady` | Only when `BatchStatus.COMPLETED` and business criteria pass | Downstream jobs, data publication, report dispatch |

Example listener emitting `ReportReady` only on success:

```java
@Override
public void afterJob(JobExecution execution) {
    if (execution.getStatus() != BatchStatus.COMPLETED) {
        return;
    }
    if (!"COMPLETED".equals(
            execution.getExitStatus().getExitCode())) {
        // Example policy: accept only warning-free completions.
        return;
    }

    String businessDate =
            execution.getJobParameters().getString("businessDate");

    reportReadyPublisher.publish(
            execution.getId(),
            businessDate
    );
}
```

This is an **illustrative business policy**; not every job must require exit code `COMPLETED`. If an app uses `COMPLETED_WITH_SKIPS` yet still permits report delivery, define the contract explicitly.

**“JobFinished” differs from “DataReady.”** A batch may finish cleanly per framework rules while outputs have not passed totals checks, checksums, or approvals. If downstream requires genuinely ready data, emit `DataReady` only after quality verification completes rather than tying it directly to every `COMPLETED`.

## 6. Observing Completion via `JobExplorer`

`JobExecutionListener` is an in-lifecycle callback, whereas schedulers/orchestrators may run in a separate process. In that case, **`JobExplorer` reads metadata from `JobRepository`** to check whether a job has finished.

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

public final class JobCompletionReader {

    private final JobExplorer explorer;

    public JobCompletionReader(JobExplorer explorer) {
        this.explorer = explorer;
    }

    public JobExecution findExecution(long executionId) {
        JobExecution execution = explorer.getJobExecution(executionId);

        if (execution == null) {
            throw new IllegalArgumentException(
                    "Unknown jobExecutionId: " + executionId
            );
        }

        return execution;
    }

    public boolean hasFinished(long executionId) {
        BatchStatus status = findExecution(executionId).getStatus();

        return status == BatchStatus.COMPLETED
                || status == BatchStatus.FAILED
                || status == BatchStatus.STOPPED
                || status == BatchStatus.ABANDONED;
    }

    public boolean hasSucceeded(long executionId) {
        return findExecution(executionId).getStatus()
                == BatchStatus.COMPLETED;
    }
}
```

`ABANDONED` is treated here as **operationally finished** for stopping wait loops; it is not an indication of successful execution. An application may emit a separate `JobAbandoned` event rather than grouping it with normal termination.

### 6.1. Polling by Execution ID Instead of Guessing by Time

Example in an external system:

```text
POST /jobs/dailySettlement/launch
→ 202 Accepted
→ { "jobExecutionId": 501 }

GET /jobs/executions/501
→ { "status": "STARTED" }

GET /jobs/executions/501
→ { "status": "COMPLETED", "exitCode": "COMPLETED" }
```

These endpoints are **custom API examples**, not default Spring Batch REST endpoints. Clients should poll at intervals with timeouts and attempt caps. On timeout, return “no terminal outcome yet” or an inspection-needed status rather than guessing `FAILED` or `COMPLETED`.

**Never use `Thread.sleep(...)` as proof a job finished.** A 5-second sleep proves nothing about processing state. Poll metadata on conditions or use acknowledged events.

### 6.2. Querying by Business Date

To answer “is `dailySettlement` for `businessDate=2025-05-12` finished?”, distinguish:

- `JobInstance` represents the logical task per identifying parameters.
- `JobExecution` represents each attempt/restart of that instance.
- A single day may have execution `501=FAILED` followed by `509=COMPLETED` after restart.

If consumers care only about the **latest outcome**, query the last execution of that exact job instance (e.g., `JobExplorer.getLastJobExecution(jobName, jobParameters)` on supported versions). If full auditing is required, store events for **every execution**. Never grab an arbitrary earlier `COMPLETED` execution to assume a new scheduled run finished.

### 6.3. When `JobRepository` Reports `STARTED` for Too Long

If a worker/process dies without updating status, metadata may stay `STARTED`. Polling alone cannot distinguish a “very slow job” from a “dead job.” Combine:

- Worker or container liveness signals.
- Recent logs and processing metrics.
- Heartbeat timestamps or progress checkpoints if the app maintains them.
- Controlled recovery procedures for stale states.

Never assume a `STARTED` execution from yesterday is `COMPLETED` simply because its schedule window passed.

## 7. What Fields Should a Completion Signal Contain?

In systems with multiple schedulers and consumers, standardize the payload:

```json
{
  "eventType": "JobFinished",
  "eventVersion": 1,
  "eventId": "dailySettlement:501:finished",
  "jobName": "dailySettlement",
  "jobInstanceId": 80,
  "jobExecutionId": 501,
  "businessDate": "2025-05-12",
  "batchStatus": "COMPLETED",
  "exitCode": "COMPLETED",
  "summary": {
    "readCount": 12000,
    "writeCount": 12000,
    "skipCount": 0
  }
}
```

This is an **illustrative payload**, not a built-in Spring Batch schema. Real production events may also include UTC `occurredAt`, correlation ID, environment, schema version, and log lookup links. `readCount`/`writeCount` can be aggregated from `StepExecution`s; avoid double-counting when multi-step flows read/write the same records across steps.

Practical guidelines:

1. **Identify the execution**: scope `jobExecutionId` with job/repository/environment if IDs can collide across environments.
2. **Idempotency**: include `eventId` or a deterministic key so duplicate deliveries still process once semantically.
3. **Explicit status**: include both `BatchStatus` and `ExitStatus`.
4. **No sensitive data**: include only approved parameters; misconfigured `JobParameters` can contain secrets.
5. **Versioning**: include `eventVersion` so consumers can evolve payload schemas safely.
6. **Source reference**: carry IDs to cross-check `JobRepository` rather than trusting a potentially stale message blindly.

## 8. Why Publishing Directly in `afterJob` Can Drop Signals

Simple example:

```text
Final step finishes
       |
       v
JobRepository records terminal status
       |
       v
afterJob is called
       |
       v
HTTP / message broker publish
       |
       v
Consumer receives "JobFinished"
```

Failures can occur between steps:

- Job completes in the database, but the JVM is killed before publishing.
- Broker/HTTP has a transient error; the listener logs the exception and exits.
- Publisher sends the message, times out before receiving ACK, and retries, producing **two messages**.
- Consumer processes the message and crashes before acking, causing broker redelivery.
- A `JobExecution` is restarted, creating a new execution and emitting another event.

Thus, `afterJob` fits **best-effort notifications**, logs, and metrics. When completion signals are mandatory for downstream processing or financial workflows, use a **durable, idempotent mechanism**.

### 8.1. A Pattern: Reconciliation + Outbox

Instead of relying solely on callbacks, build a periodic reconciler reading finished executions from `JobRepository` and writing signal records into an outbox table. A separate publisher picks up outbox rows and delivers them to the broker/downstream API.

```text
                 Spring Batch Job
                        |
                        v
                 JobRepository
                        |
        +---------------+---------------+
        |                               |
        v                               v
  afterJob (fast hint)       Reconciler (periodic scan)
        |                               |
        +---------------+---------------+
                        |
                        v
                Outbox table
                  (UNIQUE key)
                        |
                        v
             Publisher / dispatcher
                        |
                        v
               Message broker / API
                        |
                        v
            Idempotent downstream
```

Advantage of the reconciler: even if `afterJob` never ran or publishing failed, any job with a terminal state in `JobRepository` is still discovered.

Sample outbox table (illustrative SQL, adjust per database):

```sql
CREATE TABLE batch_completion_outbox (
    event_id        VARCHAR(160) PRIMARY KEY,
    job_execution_id BIGINT NOT NULL,
    event_type      VARCHAR(40) NOT NULL,
    payload_json    TEXT NOT NULL,
    delivery_status VARCHAR(20) NOT NULL,
    created_at      TIMESTAMP NOT NULL
);
```

Use a unique key representing one logical event, e.g., `(environment, jobExecutionId, eventType)` if multiple environments share a table. Producers insert deterministic `event_id`s; repeated reconciler scans ignore existing rows via transactional upserts/unique constraints.

The publisher transitions rows from `PENDING` to `DELIVERED` upon proper ACK. **Do not assume “exactly once” across database and broker solely because an outbox exists**: crashing after send but before ACK can redeliver messages. Consumers must deduplicate by `eventId`/business key inside business transactions.

### 8.2. Separating the Outbox from `JobRepository` Tables

The outbox is an **application-designed mechanism**, not generated by `spring-batch-core`. Editing `BATCH_JOB_EXECUTION` directly or adding arbitrary columns to Spring Batch infrastructure tables is discouraged. Place the outbox in dedicated application schema/tables with clear delivery and retention policies.

If strict atomicity is required between job status and event creation, design transaction boundaries and reconciliation explicitly. Merely inserting a row into an outbox inside `afterJob` **does not automatically commit atomically** with all Batch metadata and business writes.

## 9. Orchestrating Downstream Jobs After Completion

A common use case:

```text
00:30 Import job
   |
   | only when COMPLETED + validated
   v
01:00 Aggregation job
   |
   | only when COMPLETED
   v
Publish report
```

Three architectural options:

| Approach | Best suited when | Notes |
|---|---|---|
| **One Spring Batch job with multiple steps** | Steps form one logical workflow sharing Batch infrastructure | Use `.next(...)` or conditional flows; minimal external orchestration |
| **Listener triggers next job** | Simple in-process workflow where best-effort reliability suffices | Must handle errors, relaunches, duplicates, and avoid blocking the listener |
| **Event/outbox + orchestrator** | Independent jobs across processes/teams or needing durable delivery | Use correlation IDs, idempotency keys, and status tracking |

### 9.1. When Possible, Use Step Flow Instead of Cross-Step Signaling

When stages are genuinely two steps of one job:

```java
@Bean
Job importAndAggregate(
        JobRepository repository,
        Step importStep,
        Step aggregateStep) {

    return new JobBuilder("importAndAggregate", repository)
            .start(importStep)
            .next(aggregateStep)
            .build();
}
```

When `importStep` prevents flow continuation based on its outcome, Batch flow controls the transition as configured. For custom exit-code branching, use flow transitions like `.on("COMPLETED")`, `.to(...)`, `.from(...)` following `ExitStatus` semantics.

### 9.2. When Jobs Are Truly Independent

Suppose the import and aggregation jobs live in separate services. The consumer receives `JobFinished`, verifies `status=COMPLETED` and matching `businessDate`, and builds `JobParameters` for downstream.

```java
public void onJobFinished(JobCompletionSignal signal) {
    if (signal.batchStatus()
            != org.springframework.batch.core.BatchStatus.COMPLETED) {
        return;
    }

    if (!"dailyImport".equals(signal.jobName())) {
        return;
    }

    // Orchestrate aggregation for exact businessDate.
    // Consumer needs idempotency by jobName + businessDate.
    triggerAggregateOnce(signal.businessDate());
}
```

`triggerAggregateOnce(...)` illustrates an orchestration call. Never run downstream twice simply because a broker redelivered the message; persist trigger state by business key or rely on identifying `JobParameters` paired with `JobLauncher` exception handling.

### 9.3. Scheduler Overlap

If cron runs hourly while an execution takes 90 minutes, two executions for different data windows or a duplicate launch for a `JobInstance` can occur. The prior run's completion signal may arrive **after** the next run's launch signal. Consumers must never assume **event arrival order matches schedule order**.

Handle this using `businessDate`/`windowStart`/`windowEnd` and explicit coordination locks. If a business flow requires strict sequential order, enforce coordination locks or observable concurrency limits rather than inferring order from cron times.

## 10. Restarts and “Job Completed” Semantics

One `JobInstance` can go through multiple attempts:

```text
JobInstance (dailySettlement, businessDate=2025-05-12)
   |
   +-- JobExecution 501: FAILED
   |      event: JobFinished(501, FAILED)
   |
   +-- JobExecution 509: STOPPED
   |      event: JobFinished(509, STOPPED)
   |
   +-- JobExecution 517: COMPLETED
          event: JobFinished(517, COMPLETED)
          event: ReportReady(2025-05-12)
```

Two event types have distinct keys:

- **Execution-finished event**: keyed by `jobExecutionId`; each terminated attempt can produce an event.
- **Business-result-ready event**: keyed by `jobName + identifying business parameters`; typically one event signaling that day's data is ready, regardless of retries/restarts.

If consumers process financials, reports, or payouts, deduplicating solely by `jobExecutionId` may **not suffice**: two different executions might accidentally trigger the same business action. Derive idempotency keys from the business domain.

**Never invent a new `run.id` to “restart” a job.** New identifying parameters create a separate `JobInstance`. Proper restarts rely on the existing job instance and persisted state, with restart-safe reader/writer configuration.

## 11. Testing Completion Signals

Separate two test goals:

1. Does the listener emit the right event for each input status?
2. Does a real job run register the listener, reach the right status, and produce the event?

### 11.1. Unit Testing the Listener with a Mock Sink

Example using JUnit Jupiter and Mockito for Spring Batch 5.x:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

import static org.mockito.Mockito.mock;

class CompletionSignalListenerTest {

    private final CompletionSignalSink sink =
            mock(CompletionSignalSink.class);

    private final CompletionSignalListener listener =
            new CompletionSignalListener(sink);

    private JobExecution execution(BatchStatus status) {
        JobInstance instance = new JobInstance(7L, "dailySettlement");

        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", "2025-05-12")
                .toJobParameters();

        JobExecution execution = new JobExecution(instance, params);
        execution.setId(501L);
        execution.setStatus(status);
        execution.setExitStatus(
                status == BatchStatus.COMPLETED
                        ? ExitStatus.COMPLETED
                        : ExitStatus.FAILED
        );

        return execution;
    }

    @Test
    void emitsCompletionSignalWhenJobCompleted() {
        JobExecution execution = execution(BatchStatus.COMPLETED);
        ArgumentCaptor<JobCompletionSignal> captor =
                ArgumentCaptor.forClass(JobCompletionSignal.class);

        listener.afterJob(execution);

        verify(sink).publish(captor.capture());

        JobCompletionSignal signal = captor.getValue();
        assertEquals(501L, signal.jobExecutionId());
        assertEquals("dailySettlement", signal.jobName());
        assertEquals("2025-05-12", signal.businessDate());
        assertEquals(BatchStatus.COMPLETED, signal.batchStatus());
        assertEquals("COMPLETED", signal.exitCode());
    }

    @Test
    void emitsFailedStatusAsFinishedNotAsSuccess() {
        listener.afterJob(execution(BatchStatus.FAILED));

        ArgumentCaptor<JobCompletionSignal> captor =
                ArgumentCaptor.forClass(JobCompletionSignal.class);
        verify(sink).publish(captor.capture());

        assertEquals(BatchStatus.FAILED,
                captor.getValue().batchStatus());
    }

    @Test
    void doesNotEmitWhenStatusIsStillRunning() {
        listener.afterJob(execution(BatchStatus.STARTED));

        verify(sink, never()).publish(any());
    }
}
```

Add an extra `@Test` where `sink.publish(...)` throws an exception and assert the listener handles/logs the error per policy. If **durable delivery** is required, this unit test is insufficient: also test outbox/reconciliation, dispatcher retries, and consumer idempotency.

### 11.2. Full-Job Integration Test

Unit tests calling `afterJob(...)` directly will **not catch a missing `.listener(...)`** on `JobBuilder`. Use `spring-batch-test` to run the entire job via `JobLauncherTestUtils.launchJob(...)`.

Example test class with an isolated configuration, H2, and Spring Boot 3.x:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.CopyOnWriteArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
        classes = CompletionSignalIntegrationTest.TestApplication.class,
        properties = {
                "spring.batch.job.enabled=false",
                "spring.batch.jdbc.initialize-schema=always"
        }
)
class CompletionSignalIntegrationTest {

    @Autowired JobLauncherTestUtils testUtils;
    @Autowired RecordingSink sink;

    @Test
    void afterJobShouldRunOnceForCompletedJob() throws Exception {
        JobExecution execution = testUtils.launchJob();

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(1, sink.events.size());
        assertEquals(execution.getId().longValue(),
                sink.events.get(0).jobExecutionId());
        assertEquals(BatchStatus.COMPLETED,
                sink.events.get(0).batchStatus());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        RecordingSink recordingSink() {
            return new RecordingSink();
        }

        @Bean
        CompletionSignalListener completionListener(RecordingSink sink) {
            return new CompletionSignalListener(sink);
        }

        @Bean
        Step noOpStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager) {

            return new StepBuilder("noOpStep", repository)
                    .tasklet((contribution, chunkContext) ->
                            RepeatStatus.FINISHED, transactionManager)
                    .build();
        }

        @Bean
        Job completionTestJob(
                JobRepository repository,
                Step noOpStep,
                CompletionSignalListener listener) {

            return new JobBuilder("completionTestJob", repository)
                    .start(noOpStep)
                    .listener(listener)
                    .build();
        }
    }

    static class RecordingSink implements CompletionSignalSink {
        final List<JobCompletionSignal> events =
                new CopyOnWriteArrayList<>();

        @Override
        public void publish(JobCompletionSignal event) {
            events.add(event);
        }
    }
}
```

`@SpringBatchTest` provides Batch testing utilities. This test checks a successful job without external messaging and assumes isolated metadata per test. If the context is reused, ensure unique identifying job parameters or clean `JobRepository` before rerunning; otherwise a completed `JobInstance` will block subsequent test runs.

For async jobs, `launchJob(...)` or `JobLauncher.run(...)` may return before completion when the test reads immediately; wait via `JobExplorer` conditions or synchronous test fixtures, then assert after execution truly finishes.

### 11.3. Other Important Scenarios to Test

| Scenario | Verification condition |
|---|---|
| Job `COMPLETED` | Emits completion event with exact execution ID, status, and parameters |
| Job `FAILED` | Emits “finished failed” or alert; **never** emits `ReportReady` |
| Job `STOPPED` | Does not emit “ready”; allows appropriate restart workflow |
| First step succeeds, second fails | Does not emit success signal merely because the first step `COMPLETED` |
| `afterJob` callback unregistered | Integration test catches the missing event |
| Network error on publish | Logs/metrics emitted and retry/reconciliation triggers; never claims delivered |
| Publisher resends event | Consumer does not trigger business work twice |
| Restart execution with new ID | Emits new finished event, while `ReportReady` per `businessDate` does not duplicate |
| Scheduler overlap | Both executions are distinguished by ID and identifying parameters |
| Worker killed | Reconciler detects terminal status if persisted; if still `STARTED`, routes to recovery |
| Custom exit code | Downstream rules handle `COMPLETED_WITH_WARNINGS` or app-defined codes properly |

## 12. Monitoring and Operations

Completion signals are most useful alongside observability. Operational tooling should record at least:

```text
event=batch.job.finished
jobName=dailySettlement
jobExecutionId=501
businessDate=2025-05-12
batchStatus=COMPLETED
exitCode=COMPLETED
signalEventId=dailySettlement:501:finished
publishStatus=PENDING
```

This is sample data. In real implementations, source authoritative status from `JobExecution`, never inferring success just because a scheduler callback threw no exception.

Useful monitoring metrics:

- Executions ending in `COMPLETED`, `FAILED`, `STOPPED`.
- Latency from scheduler trigger to terminal execution.
- Latency from terminal execution to event delivery/ACK.
- Outbox events still `PENDING`, retry counts, and consumer duplicates skipped.
- Jobs remaining `STARTED` or `STOPPING` longer than the operational window.
- Jobs technically completed without producing expected business outputs.

When event publishing fails, alerts should include `jobExecutionId` and `eventId`. Operators can inspect metadata and replay the specific outbox event. Avoid rerunning an entire batch job merely because a **notification signal was lost** when business data already completed.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Emitting success right after `JobLauncher.run()` | Async job still running or will fail | Rely on `afterJob` or terminal status in `JobRepository` |
| Relying on `@Scheduled` finishing without exceptions | Proves only that the schedule fired | Read actual `JobExecution` |
| Using `afterStep` to conclude the whole job | Other steps have not run or may fail | Use job-level callbacks |
| Treating every `afterJob` as success | `afterJob` also runs for `FAILED` | Check `BatchStatus` |
| Storing only `jobName` without execution ID | Multiple runs cause event confusion | Include `jobExecutionId` and `businessDate` |
| Direct HTTP emit with no retry/reconcile | Signals lost if service crashes | Outbox + reconciler + idempotent consumer |
| Believing outbox alone gives “exactly once” | Duplicates can still occur on crash/retry | Deduplicate by event/business key |
| Using current date when receiving the event | Next-day consumer processes wrong date | Read date from pinned `JobParameters` |
| Always triggering downstream on `COMPLETED` | May skip quality checks | Use `DataReady` contract or exit-code policy |
| Using `Thread.sleep` to await completion | Slow and flaky tests | Poll with timeout, latches/futures, or sync launcher |
| Retrying delivery by restarting a `COMPLETED` job | Fails with `JobInstanceAlreadyCompleteException` | Replay the signal/outbox, do not rerun data |
| Unversioned event schema | Consumers break when producers change fields | Add `eventVersion` and handle compatibility |

## 14. Practice Exercise

Design a system with two jobs:

- `importSales` runs at 01:00, accepts identifying parameter `businessDate`, and ingests data.
- `buildDailyReport` triggers only when `importSales` data for that exact date is ready.

Requirements:

1. Create a `JobExecutionListener` for `importSales` emitting `JobFinished` with `jobExecutionId`, `businessDate`, `BatchStatus`, and `ExitStatus`.
2. Test all three outcomes `COMPLETED`, `FAILED`, and `STOPPED`; confirm only contract-passing runs emit `DataReady`.
3. Build a consumer handling `DataReady`, launching `buildDailyReport` for the exact business date and guarding duplicate launches by `businessDate`.
4. Simulate callback publish failure after job termination. Use an outbox table and reconciler so the event is still delivered.
5. Simulate the broker delivering the same event twice. Verify the consumer does not generate two reports for the same day.
6. Have the import job fail first and then restart successfully. Explain why two `JobFinished` events occur while only one “report data ready” event occurs per business key.
7. Write unit tests for the listener and an integration test running the real job via `spring-batch-test`, proving the listener is registered.
8. Run with an async launcher to prove the immediate return value of `JobLauncher.run(...)` is not proof of completion.

**Self-check question:** The scheduler logs `“Job launched successfully”` and receives `JobExecution id=501` in `STARTED` status. Should you send the email “Reconciliation succeeded” yet? **No.** Wait for a verified terminal result, then check success criteria and notification delivery.

## 15. References

- [Spring Batch 5.2 — Configuring a Job](https://docs.spring.io/spring-batch/reference/5.2/job/configuring.html): `JobExecutionListener`, `beforeJob`, and `afterJob`.
- [Spring Batch 5.2 — JobExecutionListener API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/JobExecutionListener.html): callback signatures and state notes.
- [Spring Batch 5.2 — Batch Status Versus Exit Status](https://docs.spring.io/spring-batch/reference/5.2/step/controlling-flow.html): distinguishing `BatchStatus` and `ExitStatus`.
- [Spring Batch — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, statuses, and metadata.
- [Spring Batch — JobExplorer API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/explore/JobExplorer.html): querying executions and job instances.
- [Spring Batch — Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, and integration tests.
- [Spring Framework — Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableScheduling`, `@Scheduled`, and schedule configuration.
