# Request and Scheduler Correlation in Spring Batch Monitoring

A batch job can run for seconds, minutes, or hours. When a run fails, the operations team's first question is often not "what was the exception?" but: **"Which request or scheduler triggered this run, which data period did it process, and what output did it produce?"**

In web applications, the initial request may finish immediately after returning `202 Accepted` while the job continues running on another thread. In scheduled systems, the same job may be triggered multiple times by different nodes or by a retry. If logs show only the job name and exception text, it becomes hard to connect the launch cause to execution status, input data, and output side effects.

**Correlation** is the practice of tying related events into a single observable chain using stable identifiers. For Spring Batch, you need to link **request/scheduler trigger → launch attempt → JobInstance → JobExecution → StepExecution → logs, traces, metrics, and outputs**.

This lesson belongs to **Spring Batch Core Processing → Monitoring**, focusing on correlation ID design, passing context from HTTP or schedulers into jobs, tracking via `JobRepository`, handling asynchronous execution, MDC/tracing, retry/restart, duplicate launches, and safe observability practices. Examples use Spring Batch 5.x, Java 17+, and Spring Boot; table, field, and endpoint names are illustrative.

## 1. Why Does Correlation Matter in Batch Processing?

Suppose a REST API receives a request to import data for `2026-11-15`:

~~~text
09:00:00  Client -> POST /imports
09:00:00  API -> 202 Accepted, requestId=req-301
09:00:01  Job importOrdersJob starts in background
09:03:40  Step validateOrdersStep completes
09:08:12  Step writeOrdersStep fails
~~~

If at 09:08:12 the log says only `writeOrdersStep FAILED`, operators do not know which HTTP request triggered this failure. If two more imports arrive on the same day, relying solely on timestamps quickly leads to confusion.

For schedulers, the situation is similar:

~~~text
01:00:00  Scheduler trigger: dailyImportJob for businessDate=2026-11-15
01:00:02  Batch JobExecution=8102 starts
01:04:30  JobExecution=8102 FAILED
01:10:00  Scheduler/Operator retries same business period
01:10:01  JobExecution=8103 starts, same JobInstance
~~~

To understand the entire chain, the system must record the relationship among **processing period**, **trigger attempt**, and **execution attempt**. On a restart, `JobExecution` changes while `JobInstance` can stay the same. When a client retries a launch request, the new request's correlation ID may differ from the first request's correlation ID. Therefore, a single ID cannot stand in for all of these concepts.

## 2. Identifiers to Distinguish

| Identifier | Represents | When does it change? | Purpose |
|---|---|---|---|
| `requestId` | An incoming HTTP request to the API. | Usually new per request; client retries may send the same or a new ID depending on contract. | Find request logs, respond to caller. |
| `schedulerTriggerId` / `fireId` | A single scheduler firing. | Each trigger; some schedulers provide their own ID. | Trace schedule source, trigger, retry attempt. |
| `correlationId` | A chain of events to observe together. | Per system convention; usually generated at entry point and propagated. | Connect logs, audits, and traces across components. |
| `traceId` / `spanId` | A distributed trace / span in a tracing system. | Per trace/span lifecycle; long-lived jobs may start a new trace linked to the old trace. | Analyze service relationships and timing. |
| `businessKey` | Business unit of work, such as date + data source. | Changes when the actual work differs. | Distinguish processing periods and prevent duplicate launches. |
| `jobInstanceId` | A `JobInstance` in `JobRepository`. | Remains the same across restarts of the same instance. | Track a logical batch job. |
| `jobExecutionId` | A run attempt of a `JobInstance`. | New for each execution/restart. | Look up status and errors of a specific run. |
| `stepExecutionId` | A step execution within a job execution. | May differ across retry/restart executions. | Locate errors in a specific step. |

**`correlationId` is not `jobExecutionId`.** An HTTP request may not have created an execution yet; conversely, one JobInstance can have multiple executions due to restarts. Two duplicate requests may target the same JobInstance while only one is accepted by the launcher.

In operations, a useful key hierarchy is:

~~~text
correlationId + jobName + businessKey
    -> jobInstanceId
    -> jobExecutionId
    -> stepExecutionId
~~~

Not every log line must contain every field. An HTTP request reception log might not yet have a `jobExecutionId`; a running step's log should include the corresponding execution ID.

## 3. Correlation Flow Diagram from Trigger to Output

~~~mermaid
flowchart TD
    H["HTTP request\nrequestId / correlationId"] --> L["Launch service"]
    S["Scheduler trigger\nfireId / correlationId"] --> L
    L --> A["Launch attempt log / audit"]
    L --> J["JobLauncher"]
    J --> R["JobRepository\nJobInstance + JobExecution"]
    J --> E["JobExecutionListener"]
    E --> T["StepExecution / Reader / Processor / Writer"]
    T --> O["Logs / traces / metrics"]
    R --> Q["Status API / dashboard"]
    A --> Q
    O --> Q
~~~

There are three context handoff points to design:

1. **At the entry point:** capture trigger source, business key, request/trigger ID, and correlation ID.
2. **At launch time:** persist correlation details needed by the job into durable metadata or an audit table, then obtain `jobExecutionId` from the launcher if execution creation succeeds.
3. **During execution:** attach `jobExecutionId`, `jobInstanceId`, and correlation ID to job and step logs/traces; upon completion, record terminal status and error details.

If you only place `correlationId` in the HTTP thread's MDC and launch the job asynchronously, that information is lost at step 2. MDC is thread-local and does not automatically become metadata persisted by Spring Batch.

## 4. Choosing a Correlation ID and HTTP Propagation Conventions

A straightforward convention:

- Clients may send `X-Request-ID` or an accepted correlation header.
- The gateway/API validates format and length limits; if missing or invalid, it generates a new ID.
- The API logs the ID upon receiving the request, passes it into the launch context, and echoes it in response headers so callers can cite it when reporting errors.
- Downstream callers reuse the same correlation ID when tracking one workflow; if standard trace context exists, propagate via W3C Trace Context headers per tracing infrastructure.

HTTP example:

~~~http
POST /batch/import-orders HTTP/1.1
Content-Type: application/json
X-Request-ID: req-20261115-301

{"businessDate":"2026-11-15","sourceId":"warehouse-A"}
~~~

A response might return:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
X-Request-ID: req-20261115-301

{
  "correlationId": "req-20261115-301",
  "jobInstanceId": 410,
  "jobExecutionId": 8102,
  "status": "STARTING"
}
~~~

`STARTING` is only an example status at response time; with a synchronous launcher, the job may already be `COMPLETED`/`FAILED` before the API responds. With an asynchronous launcher, `202` means the request was accepted for execution, **not** that the job processed data successfully.

**Do not blindly trust external headers.** Client-supplied correlation IDs are untrusted input: restrict characters and length, strip newlines/control characters to prevent log injection, and never embed personal data or access tokens in the ID.

If HTTP idempotency is required, add `Idempotency-Key` under its own contract. An ID used to link logs **does not by itself guarantee** once-only request handling.

## 5. Passing Correlation into Spring Batch via JobParameters

`JobParameters` is a simple way to pass launch context into `JobExecution` and store it in `JobRepository`. However, distinguish:

- **Identifying parameters:** define the `JobInstance` (e.g., `businessDate` and `sourceId`).
- **Non-identifying parameters:** auxiliary metadata that varies per launch (e.g., `correlationId` and `triggerType`).

Example:

~~~java
import java.time.LocalDate;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", LocalDate.of(2026, 11, 15).toString(), true)
    .addString("sourceId", "warehouse-A", true)
    .addString("correlationId", "req-20261115-301", false)
    .addString("triggerType", "HTTP", false)
    .toJobParameters();
~~~

Because `correlationId` is marked **non-identifying**, retrying a request for the same date and source does not automatically create a new `JobInstance` just because the tracking ID differs. This is the right choice when the goal is **same business work → same JobInstance**.

Conversely:

~~~java
// Anti-pattern for a batch running once per business period:
.addString("correlationId", randomId, true)
~~~

Every new correlation ID alters the instance key. If the scheduler generates a UUID per firing, this configuration accidentally turns duplicate business requests into separate instances.

### Limitations of JobParameters

`JobParameters` are persisted in the repository and often used in job logic. Therefore:

- Store only moderately sized, metadata-safe values, never entire HTTP payloads.
- Never store passwords, access tokens, sensitive PII, or authentication headers.
- Do not use job parameters as an audit store for **all rejected requests**: when a duplicate launch is blocked before creating a new execution, the rejected request's correlation ID will **not** be saved as a `JobExecution`.
- Do not assume a correlation ID stays constant across all restarts like a business key. A restart execution may come from a different request or scheduler trigger. To follow **the whole instance chain**, also use `jobInstanceId`/business keys.

A dedicated audit table is the right fit when you need to record every launch attempt and link multiple requests/triggers to the same JobInstance.

## 6. Shared Launch Service for HTTP and Scheduler

To ensure both trigger sources produce uniform metadata, build a service accepting `businessDate`, `sourceId`, `triggerType`, and `correlationId`. `JobRepository` state still governs whether the run is allowed to start.

~~~java
import java.time.LocalDate;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class ImportLaunchService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;

    public ImportLaunchService(
            JobLauncher jobLauncher,
            @Qualifier("importOrdersJob") Job importOrdersJob) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
    }

    public JobExecution launch(
            LocalDate businessDate,
            String sourceId,
            String triggerType,
            String correlationId)
            throws JobExecutionAlreadyRunningException,
                   JobRestartException,
                   JobInstanceAlreadyCompleteException,
                   JobParametersInvalidException {

        JobParameters params = new JobParametersBuilder()
            .addString("businessDate", businessDate.toString(), true)
            .addString("sourceId", sourceId, true)
            .addString("triggerType", triggerType, false)
            .addString("correlationId", correlationId, false)
            .toJobParameters();

        return jobLauncher.run(importOrdersJob, params);
    }
}
~~~

Here `businessDate` + `sourceId` represent the business processing period. Both HTTP and scheduler sources submitting the same work target the same `JobInstance`. `triggerType` and `correlationId` explain **who requested it** without altering the unit of work.

Depending on policy, a request arriving when the instance is already `COMPLETED` may hit `JobInstanceAlreadyCompleteException`; while running, it may hit `JobExecutionAlreadyRunningException`. If the prior run was `FAILED` and the job allows restarts, calling with the same identifying parameters creates **a new JobExecution for the same JobInstance**.

**The audit flow must capture both successful and failed launch attempts.** The service can log at entry with the correlation ID before calling the launcher, and then log the execution ID after the launcher returns. When the launcher throws an exception, log the outcome and requested business key, and look up the existing execution if the caller needs a link to the active run.

## 7. Launching from a REST API: The Request Finishes Before the Job

With an API, two independent lifecycles exist:

1. **Request lifecycle:** receive request, validate, decide launch, return response.
2. **Job lifecycle:** create execution, run steps/chunks, save checkpoints, and finish.

If the job is asynchronous, the request finishes in milliseconds while the job runs for minutes. Never rely solely on servlet filters or request MDC to attach correlation to the batch job.

An illustrative controller:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.batch.core.JobExecution;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

record ImportRequest(LocalDate businessDate, String sourceId) {}

record LaunchResponse(
    Long jobInstanceId,
    Long jobExecutionId,
    String correlationId,
    String status
) {}

@RestController
@RequestMapping("/batch")
class ImportController {

    private final ImportLaunchService launchService;

    ImportController(ImportLaunchService launchService) {
        this.launchService = launchService;
    }

    @PostMapping("/import-orders")
    ResponseEntity<LaunchResponse> launch(
            @RequestBody ImportRequest request,
            @RequestHeader(value = "X-Request-ID", required = false)
            String incomingRequestId) throws Exception {

        // Demo: in practice, validate header format/length.
        String correlationId =
            incomingRequestId == null || incomingRequestId.isBlank()
                ? UUID.randomUUID().toString()
                : incomingRequestId;

        JobExecution execution = launchService.launch(
            request.businessDate(),
            request.sourceId(),
            "HTTP",
            correlationId
        );

        LaunchResponse response = new LaunchResponse(
            execution.getJobInstance().getInstanceId(),
            execution.getId(),
            correlationId,
            execution.getStatus().name()
        );
        return ResponseEntity.accepted()
            .header("X-Request-ID", correlationId)
            .body(response);
    }
}
~~~

This example focuses on propagating correlation. A production API also needs request body validation, authorization, launcher exception mapping, and persistence of launch attempt outcomes. If the controller catches all exceptions and returns an undifferentiated `500`, clients cannot tell whether an execution is already running.

Provide a tracking endpoint such as:

~~~http
GET /batch/executions/8102
~~~

The response can include `jobExecutionId`, `jobInstanceId`, `jobName`, business key, `STARTED/COMPLETED/FAILED` status, start/end timestamps, and sanitized error summaries. When querying details from `JobExplorer`, enforce access control because metadata can include business parameters.

### Do Not Confuse "Request Accepted" with "Job Succeeded"

When the API returns `202 Accepted`, it marks request acceptance—not proof that the batch completed. Dashboards should separate these milestones:

| Milestone | Example | Assessment |
|---|---|---|
| `launch.requested` | API receives request at 09:00:00 | Records incoming request. |
| `launch.accepted` | JobExecution 8102 created | Batch now has an execution to track. |
| `job.started` | Execution enters execution phase | Actual processing begins. |
| `step.failed` | writeOrdersStep fails at 09:08:12 | Failure isolated to a specific step. |
| `job.failed` | JobExecution 8102 `FAILED` | Final outcome is unsuccessful. |

Never collapse all of these into a single "request success" metric or a `status=OK` field.

## 8. Launching from a Scheduler: Trigger Identity and Business Period

A scheduler lacks an HTTP request ID, yet always has trigger source details. If a scheduler like Quartz supplies a fire identifier, trigger name, and scheduled fire time, pass the needed fields into monitoring. With Spring's `@Scheduled` alone, the application can generate a `schedulerTriggerId` per callback while using a fixed schedule name to identify the source.

Example running at 01:00 in the business timezone to process the previous day:

~~~java
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.UUID;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class DailyImportScheduler {

    private static final ZoneId BUSINESS_ZONE =
        ZoneId.of("Asia/Ho_Chi_Minh");

    private final ImportLaunchService launchService;

    DailyImportScheduler(ImportLaunchService launchService) {
        this.launchService = launchService;
    }

    @Scheduled(cron = "0 0 1 * * *", zone = "Asia/Ho_Chi_Minh")
    void importPreviousBusinessDay() throws Exception {
        LocalDate businessDate =
            LocalDate.now(BUSINESS_ZONE).minusDays(1);

        String correlationId = UUID.randomUUID().toString();

        launchService.launch(
            businessDate,
            "warehouse-A",
            "SCHEDULER",
            correlationId
        );
    }
}
~~~

This example uses a UUID as a **non-identifying correlation ID** for each scheduler firing, while `businessDate` and `sourceId` are identifying. Two pods firing at the scheduled hour still resolve to the same `JobInstance` when sharing a repository and date-calculation rule.

Useful scheduler fields include:

| Field | Example | Role |
|---|---|---|
| `triggerType` | `SCHEDULER` | Distinguishes source from HTTP/manual/event. |
| `scheduleName` | `daily-order-import` | Identifies the configured schedule. |
| `scheduledFor` | `2026-11-16T01:00:00+07:00` | Scheduled execution time, for comparison with actual start time. |
| `firedAt` | `2026-11-16T01:00:02+07:00` | Timestamp when the callback fired. |
| `schedulerTriggerId` | `fire-782` | Identifies a single firing, if provided by the scheduler. |
| `businessDate` | `2026-11-15` | Data period to process. |
| `correlationId` | `e6f7...` | Links callback logs to the created execution. |

`@Scheduled` by itself does not provide a standard `fireId` like dedicated schedulers do. If exact schedule auditing (misfires, retries, cluster coordination) is required, capture real scheduler metadata or persist a dedicated trigger record.

**Distinguish `scheduledFor` from `businessDate`.** A schedule firing on the 16th may process data for the 15th. If one node calculates the date in UTC and another in Vietnam time, they can produce two different business keys for the same intended run.

## 9. Attaching Correlation to Logs via MDC

SLF4J/Logback's `Mapped Diagnostic Context` (MDC) adds context fields to logs emitted on threads carrying that MDC. For batch jobs, a `JobExecutionListener` can install the correlation ID and execution ID when the job starts and clear them when the job ends.

Example:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class CorrelationJobExecutionListener
        implements JobExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(CorrelationJobExecutionListener.class);

    @Override
    public void beforeJob(JobExecution execution) {
        install(execution);
        log.info("batch.job.started");
    }

    @Override
    public void afterJob(JobExecution execution) {
        try {
            install(execution);
            log.info("batch.job.finished status={} exitCode={}",
                execution.getStatus(),
                execution.getExitStatus().getExitCode());
        } finally {
            MDC.remove("correlationId");
            MDC.remove("jobName");
            MDC.remove("jobInstanceId");
            MDC.remove("jobExecutionId");
        }
    }

    private void install(JobExecution execution) {
        String correlationId =
            execution.getJobParameters().getString("correlationId");

        if (correlationId == null || correlationId.isBlank()) {
            MDC.remove("correlationId");
        } else {
            MDC.put("correlationId", correlationId);
        }

        MDC.put("jobName",
            execution.getJobInstance().getJobName());
        MDC.put("jobInstanceId",
            String.valueOf(execution.getJobInstance().getInstanceId()));
        MDC.put("jobExecutionId",
            String.valueOf(execution.getId()));
    }
}
~~~

Attach the listener to the job:

~~~java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step readAndWriteOrdersStep,
        CorrelationJobExecutionListener correlationListener) {
    return new JobBuilder("importOrdersJob", jobRepository)
        .listener(correlationListener)
        .start(readAndWriteOrdersStep)
        .build();
}
~~~

When a job runs on a single thread in the usual way, MDC installed in `beforeJob` appears in logs emitted on that same thread. However, **MDC is ThreadLocal**, so the listener does not automatically guarantee correlation appears in step worker threads, async executors, or libraries with their own thread pools.

`afterJob` clears MDC so pooled threads reused later do not carry stale data from a prior execution. In async pipelines or custom listeners, also enforce cleanup at the proper thread/task boundary: if an error happens before the listener ends normally, context management needs a reliable cleanup strategy.

### A Structured Log Line

~~~json
{
  "timestamp": "2026-11-16T09:08:12+07:00",
  "level": "ERROR",
  "event": "batch.step.failed",
  "correlationId": "req-20261115-301",
  "triggerType": "HTTP",
  "jobName": "importOrdersJob",
  "jobInstanceId": 410,
  "jobExecutionId": 8102,
  "stepName": "writeOrdersStep",
  "stepExecutionId": 9204,
  "businessDate": "2026-11-15",
  "sourceId": "warehouse-A",
  "errorCode": "OUTPUT_WRITE_FAILED"
}
~~~

This is **an application-chosen log schema example**, not a list of fields Spring Batch outputs by default. Generating JSON logs requires configuring a suitable logging encoder; `MDC.put` only populates fields in the logging context without deciding output format.

In error logs, keep useful stack traces in internal log systems while using a stable `errorCode` for filtering and aggregation. Never dump entire items containing sensitive data into logs just for easier tracing.

## 10. Correlation in Steps, Chunks, and Multithreaded Processing

At the step level, helpful additional fields are `stepName` and `stepExecutionId`. A `StepExecutionListener` can attach them when a step starts and remove them when it ends:

~~~java
import org.slf4j.MDC;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class CorrelationStepExecutionListener
        implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        MDC.put("stepName", stepExecution.getStepName());
        MDC.put("stepExecutionId",
            String.valueOf(stepExecution.getId()));
    }

    @Override
    public org.springframework.batch.core.ExitStatus afterStep(
            StepExecution stepExecution) {
        MDC.remove("stepName");
        MDC.remove("stepExecutionId");
        return null; // Keep current ExitStatus unchanged.
    }
}
~~~

`StepExecutionListener.afterStep(...)` can return `null` when it does not intend to alter the exit status. This sample listener populates MDC for callbacks on **the same thread**; it does not yet handle item processing dispatched to separate worker executors.

### When Using TaskExecutor or Partitioning

A multithreaded step, asynchronous item processor, partitioned step, or remote chunking setup can process items on different threads or processes:

~~~text
Job thread (MDC: correlationId=A)
    |
    +--> Worker thread 1: read/process/write
    +--> Worker thread 2: read/process/write
    +--> Remote worker JVM: processes partition
~~~

The job thread's MDC does not automatically propagate to workers. With Spring's `ThreadPoolTaskExecutor`, attach a `TaskDecorator` to capture context at task submission and restore it inside the worker:

~~~java
import java.util.Map;

import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;
import org.springframework.context.annotation.Bean;

@Bean
TaskDecorator mdcTaskDecorator() {
    return task -> {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    };
}
~~~

Be sure to **attach the decorator to the exact executor used by the step**, such as via `ThreadPoolTaskExecutor.setTaskDecorator(...)`. Simply declaring a `TaskDecorator` bean does not make every executor in the application use it automatically. The decorator snapshots the submitting thread's MDC when the task is submitted; if the submitter lacks correlation at that moment, workers still will not receive it.

For remote partitioning or message-driven workers, put correlation fields into **message headers/payloads** with clear propagation and validation rules; a `TaskDecorator` inside the manager's JVM cannot transfer ThreadLocals to another JVM. Receiving workers must reconstruct their own logging context and clean it up afterward.

Beyond MDC, always retain **durable identifiers** (job/step execution IDs, business keys) in metadata or payloads. MDC makes logs searchable, but is never the source of truth for restarts or batch state.

## 11. Distributed Tracing: Linking Request Traces and Batch Executions

Standards-based tracing like OpenTelemetry uses `traceId`, `spanId`, and parent/child relationships to show call timing across services. However, jobs running for hours or processed asynchronously have a very different lifecycle from an HTTP request lasting a few milliseconds.

Two meaningful representations:

1. **Same trace across a suitably bounded workflow:** short-lived spans propagate context through async hops via the tracing infrastructure.
2. **New trace for the job, linked back to the triggering request trace:** record `triggerTraceId` or create a **Span Link** to the prior context if the tracing backend supports it. This works well for long-lived jobs, scheduled jobs, or restarts hours later.

A model:

~~~text
HTTP Trace T1
  └─ span POST /batch/import-orders
       └─ launch accepted, jobExecutionId=8102

Batch Trace T2  [link to T1]
  ├─ jobExecutionId=8102
  ├─ Step readOrders
  └─ Step writeOrders
~~~

If the job originates from a scheduler rather than HTTP, start a trace when the scheduler fires, then create traces/spans across the batch lifecycle. `correlationId` serves as a convenient bridge across logs, audits, and traces; `jobExecutionId` is the key into `JobRepository`.

**Do not assume Spring Batch automatically builds complete trace relationships across all versions and libraries.** Spring Boot Actuator, Micrometer Observation/Tracing, and OpenTelemetry provide observability building blocks; instrumentation coverage, async context propagation, and trace export depend on version and configuration. Explicitly verify where spans start, where span links are created, and which fields are persisted durably in your real system.

### Do Not Use `traceId` as a Business Key

A trace ID changes per request or retry. Using it as an identifying JobParameter causes same-day client retries to spawn new JobInstances. Trace IDs serve **observability**, while business keys serve **job identity**; never mix those two roles.

## 12. Metrics and Cardinality: Which IDs Belong in Tags?

Metrics answer aggregate questions: which job fails most often, how long runs take, where retries/skips are rising. Logs and traces answer detailed questions: which item caused execution 8102 to fail.

| Field | Logs/tracing | Metric label/tag |
|---|---|---|
| `jobName` | Should include | Usually suitable. |
| `stepName` | Should include at step level | Usually suitable if step count is bounded. |
| `status` / `exitCode` | Should include | Usually suitable with a bounded value set. |
| `triggerType` | Should include | Suitable with small value set: HTTP, SCHEDULER, MANUAL. |
| `correlationId` | Very useful | **Should not** be used as a standard tag. |
| `requestId` / `fireId` | Useful | Should not: nearly unique per request. |
| `jobExecutionId` / `jobInstanceId` | Useful | Should not: grows with every execution/instance. |
| `businessDate` | Useful in logs/audits | Use caution; ever-changing dates raise cardinality. |
| `sourceId` | Useful | Use as tag only if the source set is small and controlled. |

A metric carrying both `correlationId` and `jobExecutionId` creates a new time series for almost every single run. That overloads the metrics backend and destroys aggregation value. Keep high-cardinality IDs in **logs, traces, or audits**, and use dashboard drilldowns to move from aggregate metrics to specific executions.

A useful metric set:

- Launch counts: accepted, rejected as already running, rejected as already complete.
- Counts of `COMPLETED`, `FAILED`, or `STOPPED` executions by job/step.
- Job and step durations, plus wait latency from trigger to start.
- Items read, written, filtered, skipped, and retried within the scope supported by your metrics setup.
- Age of currently running executions and processing lag relative to `scheduledFor`.

When using built-in Spring Batch observability/metrics, inspect the exact metrics exported by your application version and add custom metrics only for missing signals. Do not assume identical metric names or tag sets across all versions.

## 13. Correlation During Duplicate Launches and HTTP Retries

This is a common source of confusion in monitoring.

Suppose:

~~~text
Request A: correlationId=req-A
            businessDate=2026-11-15, sourceId=warehouse-A
            -> JobInstance 410, JobExecution 8102 STARTED

Request B: correlationId=req-B (retry / second button click)
            businessDate=2026-11-15, sourceId=warehouse-A
            -> launch rejected because instance 410 is running
~~~

`req-B` does not automatically appear in the `JobParameters` of `JobExecution 8102`. Execution 8102 was created by request A; B is a **separate launch attempt**. To let operators search `req-B` and navigate to the running job, the API must log/audit B with the business key and, if looked up, `jobInstanceId=410`/`jobExecutionId=8102`.

An illustrative PostgreSQL audit table:

~~~sql
CREATE TABLE batch_launch_attempt (
    launch_attempt_id BIGSERIAL PRIMARY KEY,
    correlation_id VARCHAR(100) NOT NULL,
    trigger_type VARCHAR(30) NOT NULL,
    job_name VARCHAR(100) NOT NULL,
    business_key VARCHAR(250) NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    outcome VARCHAR(40) NOT NULL,
    job_instance_id BIGINT,
    job_execution_id BIGINT
);

CREATE INDEX idx_batch_launch_correlation
    ON batch_launch_attempt(correlation_id);
~~~

`outcome` values can be `REQUESTED`, `ACCEPTED`, `ALREADY_RUNNING`, `ALREADY_COMPLETE`, `RESTART_ACCEPTED`, or `ERROR` per application policy. This is an **optional application-managed audit table**, not part of Spring Batch's standard metadata schema.

When updating the audit table, consider crashes between creating an execution and writing the audit outcome. If that linkage is a strict business requirement, use an appropriate transaction or reconciliation mechanism; never assume two writes across separate systems are automatically atomic.

An audit store is also valuable when multiple channels trigger the same job: schedulers, APIs, and message listeners can all record launch attempts uniformly.

## 14. Restarts and Multi-Execution Correlation Chains

When a `JobExecution` fails and is validly restarted, `JobInstance` remains the same logical unit of work while the new execution receives a different ID. The restart trigger source can also differ from the original trigger:

~~~text
JobInstance=410  businessDate=2026-11-15  sourceId=warehouse-A
  |
  +-- JobExecution=8102
  |   correlationId=fire-782
  |   triggerType=SCHEDULER
  |   status=FAILED
  |
  +-- JobExecution=8103
      correlationId=req-restart-15
      triggerType=HTTP
      status=COMPLETED
~~~

To view the full history of the data period, search by **`JobInstance 410`** or business key; to investigate the specific failure, search by **`JobExecution 8102`**; to see who requested the restart, search by **`correlationId=req-restart-15`**.

In some flows, callers also need `parentCorrelationId` or `restartOfExecutionId` to document restart provenance. If storing these extra fields in `JobParameters`, mark them non-identifying when used solely for observability. Additional fields never replace the standard execution-instance relationship in `JobRepository`.

### One Job Triggering Another Job

If `parentJob` requests launching `childJob`, the child gets its own JobInstance/Execution. You can store `parentJobExecutionId` and `parentCorrelationId` in the child's metadata/audit, while generating a correlation ID suited to the call chain:

~~~text
Request req-301
  -> parentJobExecution=8102
        -> childJobExecution=8110
~~~

Do not automatically create a new child job instance every time the parent execution ID changes on restart, unless the parent execution ID is genuinely part of the child's business identity. Parent-child linkage is **observability lineage**; the child's business key should reflect the work the child performs.

## 15. Troubleshooting by Correlation: A Practical Investigation Example

Suppose a user reports "The import for the 15th has no results yet," providing `req-20261115-301`.

Actionable investigation flow:

1. **Find the entry point.** Search logs or audits by `correlationId` to see when the request/trigger arrived, the trigger source, business key, and launch outcome.
2. **Look up the execution.** If outcome is `ACCEPTED`, grab `jobExecutionId`; if `ALREADY_RUNNING`, locate the active execution via business key/`JobInstance`.
3. **Read Spring Batch metadata.** Via `JobExplorer`/dashboard, inspect `BatchStatus`, `ExitStatus`, start/end times, and each `StepExecution`.
4. **Isolate the step.** Filter logs by `jobExecutionId`, `stepExecutionId`, and error events; cross-check read/write/skip counts against the period's input data.
5. **Verify output.** Query records created by the writer or file/messaging results by business key; never rely solely on the API `202` status.
6. **Trace retries/restarts.** If the first execution `FAILED`, inspect subsequent executions of the same `JobInstance` and the launch attempt that initiated the restart.

Illustrative timeline:

| Time | Event | Correlation/Execution | Meaning |
|---|---|---|---|
| 09:00:00 | `launch.requested` | `req-301` | HTTP API receives request. |
| 09:00:00 | `launch.accepted` | `req-301` / `exec 8102` | Repository created execution. |
| 09:00:01 | `job.started` | `exec 8102` | Job starts. |
| 09:03:40 | `step.completed` | `stepExec 9203` | Read/validation step completes. |
| 09:08:12 | `step.failed` | `stepExec 9204` | Writer hits an error. |
| 09:08:13 | `job.failed` | `exec 8102` | Execution fails. |
| 09:10:00 | `launch.requested` | `req-302` | Operator requests restart. |
| 09:10:01 | `launch.accepted` | `req-302` / `exec 8103` | Same instance, new execution. |
| 09:14:00 | `job.completed` | `exec 8103` | Period completes after restart. |

The timeline shows `req-301` and `req-302` are two distinct triggers belonging to the same logical job. If a dashboard groups only by correlation ID, viewers may mistake them for two independent batches; always allow navigating from an execution to **its JobInstance and related executions**.

## 16. Correlation in Distributed Logs and Retention

In multi-service systems, standardize field names and formats before broad rollout:

| Internal standard field | Suggested format |
|---|---|
| `correlationId` | Short UTF-8 string, restricted characters and length. |
| `triggerType` | Bounded enum: `HTTP`, `SCHEDULER`, `MANUAL`, `MESSAGE`. |
| `jobName` | Spring Batch job name. |
| `jobInstanceId` / `jobExecutionId` | Numeric ID or string per log serializer convention. |
| `stepName` / `stepExecutionId` | Present once inside step scope. |
| `businessKey` | Normalized searchable representation, avoiding sensitive data. |
| `requestId` / `schedulerTriggerId` | Entry-point-specific ID. |
| `traceId` / `spanId` | System tracing standard; may not exist at every entry point. |
| `outcome` | Clearly categorized launch/job/step status value. |

For JSON logs, standardize **data types**: e.g., `jobExecutionId` is always a number or always a string, never varying by service. Standardize timestamp timezones (commonly ISO 8601/UTC in logs) and store `businessDate` explicitly in the business timezone.

**Retention for logs and metadata can differ.** Logs may be kept for days while `JobRepository` keeps history longer, or vice versa. If audit lookups are required months later, use a store with matching retention. `JobRepository` is an operational batch metadata store; do not assume it replaces legal or business audit trails.

Never log full HTTP requests or individual item payloads unless specifically required. Correlation works best when **IDs link cleanly**, without copying sensitive data into every system.

## 17. Testing Correlation from HTTP and Scheduler

Good tests verify the relationship among requests, executions, and audit data rather than merely checking that one log line contains an ID.

| Scenario | Input | What to verify |
|---|---|---|
| HTTP request with ID | Header `X-Request-ID=req-A` | Launch records `correlationId=req-A`; response and audit are queryable. |
| HTTP request missing ID | No header | Gateway/API generates a valid ID, returns it, and passes it to the job. |
| HTTP request with unsafe header | Oversized ID or contains newlines | Request is sanitized/rejected per contract, preventing log injection. |
| Scheduled run | Fixed business date | Logs show `triggerType=SCHEDULER` and trigger ID; execution has the right business key. |
| Asynchronous job | API returns before job finishes | Job logs still carry correlation/JobExecution IDs after request thread exits. |
| Two duplicate launches | Same identifying parameters, different correlations | Only one execution is accepted; both launch attempts remain queryable. |
| Restart after FAILED | Same business key, new correlation | JobInstance stays the same; JobExecution is new; audit shows restart source. |
| Multithreaded step | Worker threads differ from launcher thread | Worker logs carry context by design or remain traceable via execution metadata. |
| Remote worker | Message carries job/partition correlation | Remote worker receives and logs the right ID without relying on origin JVM's MDC. |
| Metrics | Many distinct correlation IDs | Metrics do not spawn a new time series per request/execution ID. |

Service-level tests can build `JobParameters` with differing `correlationId`s yet identical `businessDate`/`sourceId` and assert identifying flags are right. Integration tests should launch a real job against a test repository, read back `JobExecution.getJobParameters()`, and query the application audit table where present.

For async tests, synchronize on job start/completion using explicit test synchronization mechanisms. Never prove correlation by calling `Thread.sleep(...)` and hoping the job ran: tests quickly become flaky on CI.

## 18. Common Mistakes

### "There is already a traceId in HTTP logs, so the batch job will find it automatically"

Not guaranteed. The HTTP request may finish before the job runs. Tracing context and MDC typically live only within a specific thread/task scope. To investigate batches hours later, **persist linking IDs in metadata/audits** and propagate context to workers whenever logs must share the same ID.

### "Make correlationId an identifying parameter so querying is easier"

This usually creates a new JobInstance per request, defeating duplicate-launch detection. Keep **business keys** identifying, and keep correlation IDs non-identifying or in an audit table.

### "Having JobExecution ID is enough; we don't need request ID"

A rejected launch may never create a new execution. Without logging the request/trigger ID at the entry point, you will not know who requested that launch or why the UI received "already running."

### "Having requestId is enough; we don't need JobInstance"

A job may restart under a new request ID while still processing the same data period. Searching only by request ID misses prior execution history of the same instance.

### "The launcher's MDC will appear in every thread"

MDC is thread-local and does not propagate automatically to all executors or processes. Use task context propagation, message headers, and scoped listeners. Always clear MDC so thread pools never leak context across jobs.

### "Put every ID into metric tags"

Nearly unique IDs create massive cardinality; metrics systems can exhaust resources and struggle to aggregate. Put those IDs in logs/traces/audits; metrics should use only bounded categories.

### "Store the full request payload in JobParameters for debugging"

`JobParameters` is durable metadata that may appear in logs or dashboards; storing secrets/PII or large payloads creates risk. Store only fields needed for identity, execution, and correlation; keep large or sensitive payloads in a dedicated store with proper access control.

### "If the scheduler fires at 01:00, businessDate must be today"

Many jobs process the previous day or a dedicated reconciliation window. Compute dates using the business timezone and period rules, never by inferring from log timestamps or node clocks.

## 19. A Correlation Design Workflow You Can Apply Immediately

1. **Define the business key** for the job (e.g., `businessDate` + `sourceId`) and identify identifying parameters.
2. **Standardize entry points** across HTTP, scheduler, manual triggers, and messages, including `triggerType`, request/trigger ID, and `correlationId`.
3. **Record the launch attempt before calling the launcher**, then update the accepted/rejected/error outcome, attaching `jobInstanceId`/`jobExecutionId` if created.
4. **Pass required metadata into the execution**, using non-identifying JobParameters or an audit store for correlation fields.
5. **Add structured logs** at job/step boundaries, including terminal statuses and Spring Batch IDs.
6. **Design context propagation for async/remote workers**, separating transient MDC/tracing from durable metadata.
7. **Build drilldown dashboards** from request/trigger to JobInstance, JobExecutions, and StepExecutions; support viewing restart chains.
8. **Keep metric cardinality bounded**, leaving detailed IDs in logs, traces, or audits.
9. **Test the hard edge cases**, especially duplicate launches, HTTP timeouts, multi-node schedulers, restarts, and multithreaded steps.

## Conclusion

In Spring Batch monitoring, **request and scheduler correlation** is the ability to answer completely: *who triggered the job, for which data period, whether the launch was accepted or rejected, which execution ran, how each step behaved, and whether the final output was right*. Achieving that requires combining **entry-point IDs**, **business keys**, **JobRepository metadata**, **context-rich logs/traces**, and, where needed, a **launch audit** capturing even requests that failed to create an execution.

Keep `businessDate`/business keys in the role of identifying `JobInstance`; treat `correlationId` and `traceId` as observability links; use `jobExecutionId` to inspect individual runs and `jobInstanceId` to view the full lifecycle across restarts. When these keys are cleanly linked, operators can trace from an HTTP request or scheduler firing straight to the exact failing step—even long after the request ended and while the job runs on another thread or node.
