# Choosing Synchronous vs. Asynchronous Launch in Spring Batch

A Spring Batch job may run in a few seconds or several hours. When designing how a job is launched, you must decide: **should the caller wait until the job finishes to receive the result, or simply submit the launch request and track the result later?** This is the choice between **synchronous launch** and **asynchronous launch**. It directly affects HTTP response times, application lifecycle, thread resources, observability, error handling, and reliability across system restarts.

This lesson belongs to **Spring Batch Core Processing → Design Decisions**. Examples use **Java 17, Spring Boot 3.x, and Spring Batch 5.x**. We will examine `JobLauncher` mechanics, `TaskExecutorJobLauncher` configuration, choosing launch modes for CLIs and REST APIs, `JobExecution` states, concurrency limits, metadata persistence, restarts, testing, and common pitfalls.

## 1. How Do Synchronous and Asynchronous Launch Differ?

**Synchronous launch:** the thread calling `JobLauncher.run(job, parameters)` normally executes the job and **waits until the job finishes** before the method returns. The caller can immediately inspect the terminal status such as `COMPLETED` or `FAILED`.

**Asynchronous launch:** `JobLauncher.run(...)` delegates job execution to another thread via a `TaskExecutor`. The method can **return before the job finishes**. The return value is the newly created `JobExecution`, though its status at that moment is usually still `STARTING` or `STARTED`, not a final outcome.

```text
SYNCHRONOUS

Caller thread:
   |
   +--> JobLauncher.run(job, parameters)
           |
           +--> JobRepository: create JobExecution
           +--> Job.execute(...)
                   |
                   +--> Step 1
                   +--> Step 2
                   +--> COMMIT / FAILED / STOPPED
           |
   <-------+ JobExecution with post-run status
   |
   +--> Caller handles result


ASYNCHRONOUS

Caller thread:                         Worker thread:
   |                                        |
   +--> JobLauncher.run(...)                |
           |                                |
           +--> create JobExecution         |
           +--> TaskExecutor.execute(...) --+--> Job.execute(...)
           |                                |       |
   <-------+ returns early                  |       +--> Step 1
   |                                        |       +--> Step 2
   +--> HTTP 202 / executionId              |       +--> final status
   |                                        |
   +--> GET execution status --------------> JobRepository / JobExplorer
```

The key difference is **whether the calling thread blocks**. It does **not** automatically make Spring Batch run faster, change `JobInstance` identity, turn the job into a durable queued task, or guarantee execution survives JVM shutdown.

## 2. Comparison Table for Design Decisions

| Criterion | Synchronous | Asynchronous |
| --- | --- | --- |
| When `JobLauncher.run()` returns | Typically after the job finishes | Potentially right after the execution is created and handed to the executor |
| Caller thread | Occupied for the entire execution | Released early |
| Returned `JobExecution` status | Usually already a terminal status | May still be `STARTING`/`STARTED` |
| Returning results in an HTTP request | Suitable only for very short jobs with clear timeouts | Appropriate for long jobs: return `202 Accepted` and execution ID |
| CLI run from cron / Kubernetes Job | Convenient so process exits with status code upon completion | Needs separate waiting/monitoring, otherwise process may exit early |
| Concurrency control | Caller blocks, still need to bound caller count | Must bound worker threads, queue, and concurrent jobs |
| Monitoring | Caller receives final outcome directly | Needs polling, listeners, events, or monitoring system |
| Error handling | Check terminal status right after `run()` | Never equate successful launch with job success |
| Lifecycle | Fits one-shot execution then JVM exit | Fits long-lived services or managed persistent executors |
| Crash durability | Job still risks crashing mid-run | Same risk; an in-process queue is not a durable queue |

**Practical rule of thumb:** If a process is invoked by a scheduler to perform one task and exit, synchronous is usually easier to operate. If an HTTP API must respond quickly while a job runs for minutes or hours, asynchronous is usually more suitable—provided you have a durable `JobRepository`, status tracking, load limits, and recovery procedures.

## 3. Understanding `JobLauncher`, `JobRepository`, and `JobExecution`

In Spring Batch, launching is not simply calling an arbitrary Java method:

```java
JobExecution execution = jobLauncher.run(job, jobParameters);
```

Typically, the launcher:

1. Works with `JobRepository` to resolve the `JobInstance` from **job name + identifying `JobParameters`**.
2. Checks preconditions such as whether the instance is already complete, an execution is already running, or the job is restartable.
3. Creates and persists the `JobExecution`.
4. Submits `Job.execute(...)` to the configured `TaskExecutor`.
5. Returns the `JobExecution` to the caller or throws an exception if launch is disallowed.

In Spring Batch 5, the standard implementation is:

```java
org.springframework.batch.core.launch.support.TaskExecutorJobLauncher
```

This class supports both modes depending on its `TaskExecutor`. With `SyncTaskExecutor`, execution runs on the calling thread; with `ThreadPoolTaskExecutor`, execution is dispatched to a pool thread.

### 3.1. Distinguishing Three Concepts

| Component | Role | Restart Consequence |
| --- | --- | --- |
| `Job` | Processing pipeline definition composed of `Step`s | Definition is typically reused |
| `JobInstance` | A logical job unit identified by job name and identifying parameters | Preserved when restarting the right instance |
| `JobExecution` | One execution attempt of an instance with its own ID and status | Restart creates a new execution under the same instance |

Example:

```text
Job name: dailyReportJob
Identifying parameters:
    businessDate=2026-11-16
    region=VN

JobInstance A
  ├── JobExecution #1001: FAILED
  └── JobExecution #1002: COMPLETED (restart)
```

Launching synchronously or asynchronously **does not alter these identity rules**. Reusing identifying parameters may be rejected if the instance is already `COMPLETED` (`JobInstanceAlreadyCompleteException`) or currently running (`JobExecutionAlreadyRunningException`); for a `FAILED` instance, it can restart if the job allows it.

### 3.2. A Returned `JobExecution` Is Not a Promise of Success

With a synchronous launcher:

```java
JobExecution execution = syncLauncher.run(job, parameters);

if (execution.getStatus() == BatchStatus.COMPLETED) {
    // Job completed according to Spring Batch criteria.
} else {
    // Job finished unsuccessfully, or status needs inspection.
}
```

With an asynchronous launcher:

```java
JobExecution execution = asyncLauncher.run(job, parameters);

long executionId = execution.getId();
BatchStatus observedStatus = execution.getStatus();

// observedStatus may be STARTING or STARTED.
// Do not conclude the job succeeded here.
```

A synchronous job can **return a `JobExecution` with status `FAILED` without throwing an exception to the caller**. Conversely, errors during execution creation, parameter validation, or launch guards can throw exceptions before the job starts. Therefore, both paths must handle **launch exceptions** and **resulting job status**.

## 4. Configuring a Synchronous Launcher in Spring Batch 5

An explicit launcher can use `SyncTaskExecutor`:

```java
package com.example.batch.launch;

import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.support.TaskExecutorJobLauncher;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.SyncTaskExecutor;

@Configuration
public class SyncLaunchConfig {

    @Bean("syncJobLauncher")
    JobLauncher syncJobLauncher(JobRepository jobRepository)
            throws Exception {

        TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
        launcher.setJobRepository(jobRepository);
        launcher.setTaskExecutor(new SyncTaskExecutor());
        launcher.afterPropertiesSet();
        return launcher;
    }
}
```

`SyncTaskExecutor` executes the task on the calling thread, so by the time `run()` returns, the job has normally finished. This example creates a bean named `syncJobLauncher`; in applications with multiple `JobLauncher` beans, use `@Qualifier` when injecting to avoid picking the wrong launcher.

In a Spring Boot project using only defaults, you usually **do not need to define a launcher manually**. Spring Batch/Spring Boot already auto-configures the launcher from `JobRepository`; check your active launch setup before adding extra beans. The config above is useful when intentionally managing both launch modes side by side.

### 4.1. Calling Synchronously from a Service

```java
package com.example.batch.launch;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class SyncDailyReportService {

    private final JobLauncher launcher;
    private final Job dailyReportJob;

    public SyncDailyReportService(
            @Qualifier("syncJobLauncher") JobLauncher launcher,
            @Qualifier("dailyReportJob") Job dailyReportJob) {
        this.launcher = launcher;
        this.dailyReportJob = dailyReportJob;
    }

    public JobExecution runForDate(String businessDate) throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .addString("region", "VN", true)
                .toJobParameters();

        JobExecution execution = launcher.run(dailyReportJob, params);
        if (execution.getStatus() != BatchStatus.COMPLETED) {
            // Caller decides how to handle FAILED/STOPPED per contract.
            // Never rely solely on run() not throwing an exception.
        }
        return execution;
    }
}
```

This method returns `JobExecution` so the caller can inspect status and ID. In production applications, validate the date, region, launch authorization, and input identity before building parameters. String `businessDate` is illustrative; normalize via `LocalDate.parse(...)` and ISO formatting.

## 5. Configuring an Asynchronous Launcher with a Thread Pool

A controlled configuration typically uses `ThreadPoolTaskExecutor`, avoiding spawning unbounded threads per request:

```java
package com.example.batch.launch;

import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.support.TaskExecutorJobLauncher;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AsyncLaunchConfig {

    @Bean("batchLaunchExecutor")
    ThreadPoolTaskExecutor batchLaunchExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("batch-launch-");
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(60);
        executor.initialize();
        return executor;
    }

    @Bean("asyncJobLauncher")
    JobLauncher asyncJobLauncher(
            JobRepository jobRepository,
            @Qualifier("batchLaunchExecutor") TaskExecutor executor)
            throws Exception {

        TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
        launcher.setJobRepository(jobRepository);
        launcher.setTaskExecutor(executor);
        launcher.afterPropertiesSet();
        return launcher;
    }
}
```

This configuration sets illustrative bounds: **2 core threads, max 4 threads, queue capacity 20**. With a positive queue capacity, `ThreadPoolTaskExecutor` normally queues tasks once core threads are busy, scaling threads up to max only after the queue fills. Thus `maxPoolSize=4` does not mean four jobs always run concurrently right away.

`setWaitForTasksToCompleteOnShutdown(true)` and `setAwaitTerminationSeconds(60)` express intent to drain the executor when the application context closes. They **cannot guarantee a multi-hour batch finishes** if the process is killed, the container hits its graceful shutdown deadline, or the host loses power. Coordinate shutdown policies, infrastructure timeouts, `JobRepository`, and recovery procedures.

### 5.1. Async Launch Does Not Equal a Durable Queue

```text
POST /launch
     |
     v
TaskExecutorJobLauncher
     |
     +--> JobRepository creates JobExecution
     |
     +--> ThreadPoolTaskExecutor queue (in-JVM)
                   |
                   +--> Worker thread runs job
```

The `ThreadPoolTaskExecutor` queue lives **in process memory**. If the JVM dies before a queued job runs, a request that already returned `202` may never produce a completed execution. Created `JobExecution` metadata may also remain in `STARTING`/`STARTED` and require reconciliation per operational procedures.

If the system requires **accepting a request once and guaranteeing execution even across JVM restarts**, add a durable orchestration mechanism—such as a message broker/queue with acks and idempotency, a properly configured persistent Quartz scheduler, Kubernetes Jobs, or a command table polled by workers. `JobRepository` records batch execution history, but **does not replace a durable submission queue**.

## 6. Which Mode Fits Each Trigger Point?

### 6.1. Command Line, Cron, and Kubernetes Job: Usually Synchronous

An external scheduler typically runs an executable JAR, waits for the process to exit, and checks the process exit code:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 \
  region=VN

echo "Exit code: $?"
```

In Spring Boot, `--spring.batch.job.name` is an application property, while `businessDate=...` and `region=...` are **non-option arguments** converted into `JobParameters` by Boot 3's startup job runner. In this setup, the startup runner must be enabled, typically via `spring.batch.job.enabled=true`.

When the job runs synchronously in a one-shot batch process, the scheduler can tie JVM termination to job completion. Still, **the JVM exit code must be mapped from batch outcome** when needed; `BatchStatus.FAILED` does not automatically produce a non-zero exit code in all setups. Use `ExitCodeGenerator` and `SpringApplication.exit(context)` per application policy.

If you replace the startup runner's launcher with an async launcher and the JVM exits right after `SpringApplication.run(...)` returns, the job may be cut off before finishing, outputs may remain uncommitted, and the scheduler's exit code will misreport success. For CLI jobs run by cron or Kubernetes Jobs, **never switch to async merely to make the Java command return faster**.

### 6.2. REST API Triggering Long-Running Jobs: Usually Asynchronous

An HTTP request should have short timeouts and connection hold times. If a job takes 45 minutes, do not hold an HTTP request open until completion:

```text
Client POST /batch/jobs/daily-report
      |
      | Launch accepted
      v
HTTP 202 Accepted
Location: /batch/executions/1003
Body: { "executionId": 1003, "status": "STARTING" }

Client GET /batch/executions/1003
      |
      v
HTTP 200 OK
Body: { "executionId": 1003, "status": "STARTED" }

Client GET /batch/executions/1003
      |
      v
HTTP 200 OK
Body: { "executionId": 1003, "status": "COMPLETED" }
```

`202 Accepted` means **the launch request was accepted per API contract**, not that the job succeeded. Clients must poll terminal status or subscribe to application-level callbacks/events. If submission cannot be queued due to saturation, the API must return an appropriate error/response rather than faking completion.

### 6.3. In-Service Internal Scheduling: Lifecycle-Dependent

If a long-lived service uses `@Scheduled`, async can avoid blocking scheduler threads, **but** you still need concurrency caps, stop policies, a dedicated thread pool, and handling for in-flight jobs during service redeployments.

If the internal scheduler is designed to run one job at a time and needs the result before starting the next job, synchronous may be simpler. When using `@Scheduled` to launch manually via `JobLauncher`, set `spring.batch.job.enabled=false` so Boot does not auto-launch jobs at startup as well.

### 6.4. Orchestrator Running Multiple Dependent Jobs

Example:

```text
importOrdersJob ---> reconcileJob ---> publishJob
```

If orchestration waits for import to succeed before running reconcile, synchronous invocation expresses the flow cleanly when each command is managed by the orchestrator. With async, the orchestrator must capture the execution ID, **wait for terminal status**, handle timeouts/cancellations/failures, and only then trigger downstream dependencies. "Launch succeeded" alone never proves a dependency is satisfied.

## 7. Designing an Asynchronous REST API with Spring Batch

A clean API separates **submit** and **query status**; responses return only necessary fields, never exposing raw `JobExecution`, `JobParameters`, or internal exception messages.

### 7.1. API Contract

```text
POST /batch/jobs/daily-report
Content-Type: application/json

{
  "businessDate": "2026-11-16",
  "region": "VN"
}

202 Accepted
Location: /batch/executions/1003

{
  "executionId": 1003,
  "batchStatus": "STARTING"
}
```

Checking status:

```text
GET /batch/executions/1003

200 OK
{
  "executionId": 1003,
  "batchStatus": "COMPLETED",
  "exitCode": "COMPLETED"
}
```

JSON values are illustrative. `exitCode` here is **Spring Batch's `ExitStatus`**, not the JVM exit code. For an active job, `exitCode` may be an incomplete or default value; clients must never treat it as final before a terminal status.

### 7.2. Illustrative Controller

```java
package com.example.batch.api;

import java.net.URI;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/batch")
public class DailyReportBatchController {

    public record LaunchRequest(String businessDate, String region) {}
    public record LaunchResponse(Long executionId, String batchStatus) {}
    public record ExecutionResponse(
            Long executionId, String batchStatus, String exitCode) {}

    private final JobLauncher launcher;
    private final Job dailyReportJob;
    private final JobExplorer jobExplorer;

    public DailyReportBatchController(
            @Qualifier("asyncJobLauncher") JobLauncher launcher,
            @Qualifier("dailyReportJob") Job dailyReportJob,
            JobExplorer jobExplorer) {
        this.launcher = launcher;
        this.dailyReportJob = dailyReportJob;
        this.jobExplorer = jobExplorer;
    }

    @PostMapping("/jobs/daily-report")
    public ResponseEntity<LaunchResponse> launch(
            @RequestBody LaunchRequest request) throws Exception {

        if (request == null || request.businessDate() == null) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Missing businessDate");
        }

        String businessDate;
        try {
            businessDate =
                    LocalDate.parse(request.businessDate()).toString();
        } catch (DateTimeParseException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "businessDate must be yyyy-MM-dd");
        }

        if (!"VN".equals(request.region())) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Unsupported region");
        }

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .addString("region", request.region(), true)
                .toJobParameters();

        JobExecution execution;
        try {
            execution = launcher.run(dailyReportJob, parameters);
        } catch (JobExecutionAlreadyRunningException
                | JobInstanceAlreadyCompleteException
                | JobRestartException ex) {
            // Demo contract chooses 409; a real API might return the existing ID.
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "An execution for this business request conflicts");
        } catch (JobParametersInvalidException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid job parameters");
        }

        long id = execution.getId();
        URI location = URI.create("/batch/executions/" + id);

        return ResponseEntity.accepted()
                .location(location)
                .body(new LaunchResponse(
                        id, execution.getStatus().name()));
    }

    @GetMapping("/executions/{id}")
    public ExecutionResponse status(@PathVariable long id) {
        JobExecution execution = jobExplorer.getJobExecution(id);
        if (execution == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Execution not found");
        }
        return new ExecutionResponse(
                execution.getId(),
                execution.getStatus().name(),
                execution.getExitStatus().getExitCode());
    }
}
```

This controller is an **architectural sample**, assuming `spring-boot-starter-web`, `JobExplorer`, a `dailyReportJob` bean, and `asyncJobLauncher` from Section 5. Set `spring.batch.job.enabled=false` when the API controls launches so Boot does not auto-run jobs at startup. Business jobs, datasources, security, and auditing are omitted from this example.

Design points:

- **Authenticate and authorize** before launching jobs. APIs must never let arbitrary clients pick arbitrary jobs or pass unchecked SQL/paths.
- **Idempotency:** if a client times out after the server accepted the request, it may retry. Define request idempotency keys or look up existing executions; the example above returns `409` for conflict cases.
- **Validation:** normalize `businessDate` and `region` before placing them into identifying `JobParameters`.
- **Never return raw exception messages** in HTTP responses or public logs; JDBC/HTTP errors can leak sensitive payloads.
- **Never return 200/COMPLETED immediately after async submit.** Async `run()` only confirms dispatch per launcher mechanics.
- **Query status from the repository**, never caching mutable `JobExecution` objects in a static in-memory `Map` as the sole source of truth.

### 7.3. HTTP `202` Does Not Mean Durable Acceptance

With the in-process thread pool example, `202` confirms the launcher accepted the request at response time; **it does not promise the queue survives a crash**. If business requirements demand durable acceptance, persist requests into a submission/outbox table or broker with transactions and idempotency, letting a worker process from durable state. Only then can the API legitimately advertise "durably accepted."

## 8. Job Status Must Be Observed Independently of Launch

Common `BatchStatus` values:

| Status | Meaning | How Clients Should Interpret |
| --- | --- | --- |
| `STARTING` | Execution created, preparing to run | Submitted / waiting to start; no result yet |
| `STARTED` | Job is executing | Continue monitoring |
| `STOPPING` | Stop requested | Not yet fully stopped |
| `STOPPED` | Job halted | Can check restart conditions |
| `COMPLETED` | Job finished per flow | Check any business/publish gates if applicable |
| `FAILED` | Job failed | Inspect errors and recovery path |
| `ABANDONED` | Execution marked abandoned | Handle via operational procedure |
| `UNKNOWN` | Reliable status cannot be determined | Never treat as success |

**`BatchStatus` differs from `ExitStatus`**: `ExitStatus` can carry business exit codes, such as a flow with tolerated skips. Both differ from the **JVM process exit code** observed by OS schedulers.

With asynchronous launch, capture the execution ID and poll status via `JobExplorer`:

```java
JobExecution current = jobExplorer.getJobExecution(executionId);

if (current == null) {
    // Execution does not exist or is inaccessible.
} else if (current.getStatus().isRunning()) {
    // Keep monitoring; do not treat as complete.
} else {
    // Inspect final status and business outcome.
}
```

In a crash, metadata may remain `STARTING`/`STARTED` even though the process is dead. Therefore `isRunning()` in metadata **is not a live JVM heartbeat**. A robust monitor combines execution status, worker heartbeats/leases, and last-updated timestamps, alerting on stuck executions for controlled recovery.

### 8.1. Using a Listener for Completion Events

A `JobExecutionListener` can log final outcomes and emit events after a job finishes:

```java
package com.example.batch.launch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class ExecutionResultLogger implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(ExecutionResultLogger.class);

    @Override
    public void afterJob(JobExecution execution) {
        log.info(
                "event=batch_finished execution_id={} job={} "
                + "status={} exit_code={}",
                execution.getId(),
                execution.getJobInstance().getJobName(),
                execution.getStatus(),
                execution.getExitStatus().getExitCode());
    }
}
```

Attach the listener to `JobBuilder` when defining the job:

```java
return new JobBuilder("dailyReportJob", jobRepository)
        .listener(new ExecutionResultLogger())
        .start(reportStep)
        .build();
```

The listener runs on the job execution path, yet **logging or firing an event does not guarantee downstream delivery**. If downstream requires guaranteed notifications, use durable outbox/audit state and a separate notification retry mechanism. Also weigh how exceptions inside listeners impact the job and transactions.

## 9. Concurrency and Resource Limits Under Async

An async launcher lets callers return fast, but it does not mean the system can run unlimited jobs concurrently. Suppose each job uses four worker threads in a step, a datasource pool caps at 12 connections, and the launcher runs four jobs concurrently:

```text
4 asynchronous JobExecutions
        |
        +--> Job A: 4 chunk workers
        +--> Job B: 4 chunk workers
        +--> Job C: 4 chunk workers
        +--> Job D: 4 chunk workers

Possible business connection demand: ~16
Shared pool limit: 12
```

This is an **estimate** if each worker occasionally needs a connection; cursor readers, `JobRepository`, or writers may demand even more connections. Once the pool exhausts, jobs stall or fail even though the API quickly returned `202`.

### 9.1. Launcher Thread Pool vs. In-Step Executor Are Separate

| Component | What Does It Bound? |
| --- | --- |
| `batchLaunchExecutor` | Number of `JobExecution`s running concurrently in the JVM |
| Multi-threaded step `TaskExecutor` | Number of chunk workers inside **one** step |
| Partition handler/executor | Number of partitions processed concurrently |
| HikariCP datasource pool | Number of JDBC connections borrowed concurrently |
| Scheduler/orchestrator | Overlapping job requests dispatched across processes |

If each job spawns its own inner thread pool, threads and connections multiply. Never use an unbounded `SimpleAsyncTaskExecutor` in production just to keep the API non-blocking; use bounded pools/queues, metrics, and backpressure.

### 9.2. When the Executor or Queue Saturates

A launcher may fail to dispatch a task because the pool is full or shutting down. In API design:

- Never return a fake response claiming the job finished.
- Distinguish **request rejected before creation** from **execution created but dispatch failed**.
- Emit operational events and reconcile metadata for executions stuck in `STARTING` too long.
- Enforce rate limiting, capacity checks, or a durable queue.
- Return `429 Too Many Requests` or `503 Service Unavailable` per API contract with client retry/backoff.

**Subtle edge case:** `JobRepository` may already have persisted the `JobExecution` right before `TaskExecutor` rejects the task. Never assume an HTTP error proves "no execution was created." Maintain recovery and reconciliation for non-terminal executions.

### 9.3. Managing Duplicate Submissions

If two concurrent requests send:

```text
jobName=dailyReportJob
businessDate=2026-11-16
region=VN
```

Spring Batch uses identifying parameters to bind `JobInstance` and prevent several classes of duplicate runs in `JobRepository`. However, injecting a **random `run.id` per HTTP request** creates distinct instances that can reprocess the exact same data. For idempotent submissions, enforce an explicit request/batch key and duplicate policy (return existing execution ID, return conflict, or permit intentional new runs).

Never treat `JobExecutionAlreadyRunningException` or `JobInstanceAlreadyCompleteException` as critical system failures needing infinite retries. They normally reflect instance identity and state rules.

## 10. Transactions and Context in Asynchronous Runs

### 10.1. Do Not Carry the HTTP Thread's Transaction to the Batch Thread

Suppose an HTTP service inserts a row and launches an async job inside the same `@Transactional` method:

```text
HTTP thread:
    begin transaction
    insert batch_request
    asyncLauncher.run(job, params)
    commit transaction (afterward)

Worker thread:
    begin job
    read batch_request -> may not see newly inserted row yet
```

Spring's transaction context is thread-bound. **An async worker does not inherit the caller's uncommitted transaction.** Never launch inside a transaction and assume the worker sees uncommitted writes.

Safer patterns:

- Persist the request durably, commit first, and dispatch the job afterward.
- Use a transactional outbox or post-commit event listener with retry so requests are not lost if the process crashes between commit and dispatch.
- Have the job read committed/snapshot inputs rather than mutable request objects owned by the HTTP thread.

### 10.2. MDC, Security Context, and Request Scope

Thread-local data such as MDC correlation IDs, security contexts, or request-scoped beans **do not automatically propagate accurately** to worker threads. If a `traceId` is needed, pass an approved value via non-identifying `JobParameters` or a properly configured context-propagation mechanism; clear MDC in a `finally` block on workers to avoid cross-job log bleed.

Never pass `HttpServletRequest`, entities attached to the request thread's persistence context, transaction-bound objects, or references to soon-to-be-disposed contexts into a background job. Persist long-lived inputs as durable identities/snapshots and reload them inside the worker.

### 10.3. Do Not Confuse Task-Level Async with Job-Level Async

- **Async job launch:** `JobLauncher` offloads **the entire job** to an executor; the caller returns early.
- **Multi-threaded step:** one step processes chunks concurrently; the caller may still launch synchronously and wait for completion.
- **Async processor/writer:** processes items asynchronously within a step; unrelated to whether `JobLauncher.run()` blocks.
- **Partitioning/remote chunking:** distributes work, yet orchestration still decides how to wait for results.

A synchronously launched job can still run parallel steps, and an asynchronously launched job can still process items sequentially. These two design axes are **independent**.

## 11. Application Lifecycle and Graceful Shutdown

In long-lived HTTP services, async jobs often share a JVM with the web server. During redeployment:

1. Stop accepting new launch requests.
2. Update readiness probes so the load balancer stops routing traffic.
3. Give the executor/running jobs a window to finish, or send cooperative stop requests per contract.
4. Wait within the container/orchestrator shutdown grace period.
5. For unfinished jobs, use metadata and restart/recovery policies once the service comes back up.

Settings like `awaitTerminationSeconds` or Kubernetes `terminationGracePeriodSeconds` are **wait caps**, not guarantees that multi-hour jobs finish. If jobs must outlive API deployments, use **API writes durable request → separate batch worker picks up work → persists status**.

### 11.1. Stopping an Async Job

Spring Batch supports `JobOperator` to request stopping an execution with proper administrative authorization:

```java
boolean stopRequested = jobOperator.stop(executionId);
```

This is a **cooperative stop request**, not an instant thread kill. A tasklet blocked on I/O or a writer without timeouts may not stop immediately. Verify actual transition to `STOPPED`, handle open transactions, and distinguish **stop** from **restart** after resolving the issue.

Job-stop APIs must be strictly authorized, audited, and scoped so users cannot halt arbitrary executions outside their permissions.

## 12. Two-Stage Error Handling

With async launches, distinguish two stages:

**Stage A — Submission/launch:** caller invokes `JobLauncher.run(...)`. Failures include invalid parameters, missing job bean in context, duplicate instance, repository failure creating the execution, or executor task rejection.

**Stage B — Execution:** job has started running and can fail in reader, processor, writer, transaction, validation, or downstream APIs.

```text
POST /launch
    |
    +-- validation error --------> HTTP 400, job not started
    +-- already running ---------> HTTP 409 or idempotent lookup
    +-- system cannot accept ----> HTTP 503/429 per policy
    |
    +-- accepted ---------------> HTTP 202 + executionId
                                      |
                                      v
                                  JobExecution
                                   |       |
                               COMPLETED  FAILED/STOPPED
                                   |       |
                              publish?   alert/restart?
```

A successful HTTP response only reflects **Stage A**. If the job transitions to `FAILED` 10 minutes later, the server cannot retroactively change the earlier `202` response. Thus you need durable status endpoints, notifications, dashboards, or callbacks.

With synchronous launch, both stages happen within one call so the caller gets the outcome directly. However, if a synchronous job takes too long, an HTTP/proxy timeout can close the client connection **while the server keeps running the job**. Clients must never assume a request timeout means the job didn't run and blindly submit a new instance.

## 13. When Should You Separate Batch Workers into Their Own Architecture?

If jobs share these traits, simply swapping `SyncTaskExecutor` for `ThreadPoolTaskExecutor` is not enough:

- Jobs run for hours or consume heavy CPU/memory, degrading API latency.
- Multiple clients submit jobs concurrently, needing quotas, priority queues, and backpressure.
- Submissions must survive API restarts/deployments without losing accepted work.
- Workers need to scale independently of web servers.
- Auditing requests, retries, and durable status across multiple systems is required.
- Multi-job dependency workflows or strict deadlines exist.

Recommended architecture:

```text
Client
  |
  | POST /batch-requests  (idempotency key)
  v
API service
  |
  +--> Durable request store / outbox
                  |
                  v
            Scheduler / Queue
                  |
                  v
           Dedicated batch worker
                  |
                  +--> JobLauncher (typically synchronous inside worker)
                  +--> JobRepository
                  +--> Result / publish state
                  |
                  v
             Status/notification
                  |
                  v
                Client
```

At the API tier, processing looks "asynchronous" to the client because requests return fast. Yet **inside the batch worker, synchronous launch is often the best choice**: the worker only acks the message/command once the job reaches an acceptable terminal state. This is an important architectural distinction: **async to external callers does not have to mean async inside `JobLauncher` itself**.

Durable queues require proper ack, lease/visibility timeout, dead-letter, deduplication/idempotency, and at-least-once delivery contracts. `JobRepository` records batch history, not all of those queue mechanics.

## 14. Testing Synchronous and Asynchronous Choices

### 14.1. Testing Blocking Behavior with Latches

Using `Thread.sleep(1000)` makes CI tests flaky. Instead, use **`CountDownLatch`** to prove the job started and deterministically release it.

A test-fixture tasklet can look like:

```java
CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

Tasklet blockingTasklet = (contribution, chunkContext) -> {
    started.countDown();
    if (!release.await(10, TimeUnit.SECONDS)) {
        throw new IllegalStateException("TEST_RELEASE_TIMEOUT");
    }
    return RepeatStatus.FINISHED;
};
```

This snippet is a **test fixture** requiring imports for `java.util.concurrent.CountDownLatch`, `TimeUnit`, `Tasklet`, and `RepeatStatus`. Latches are strictly for tests—never use them to pause production jobs.

Two scenarios:

| Scenario | Setup | Expectation |
| --- | --- | --- |
| Synchronous | Call launcher on a separate test thread, await `started`, before `release` | Future for `run()` is **not done yet** |
| Asynchronous | Call async launcher, await `started`, before `release` | `run()` has already returned `JobExecution`; job is still running |
| After release | `release.countDown()` | Final execution transitions to `COMPLETED` |
| Job throws exception | Tasklet fails intentionally | Read `FAILED` from repository; do not infer from launch return |

For the sync test, invoke `run()` inside a separate `ExecutorService` so the test thread controls the latch:

```java
Future<JobExecution> submitted = testExecutor.submit(
        () -> syncLauncher.run(testJob, params));

assertThat(started.await(5, TimeUnit.SECONDS)).isTrue();
assertThat(submitted.isDone()).isFalse();

release.countDown();
JobExecution finished = submitted.get(5, TimeUnit.SECONDS);
assertThat(finished.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

This code is a **test excerpt**: `testExecutor`, `syncLauncher`, `testJob`, `params`, `started`, `release`, AssertJ, and imports belong in the test class. Use `try/finally` to release latches and shut down executors even on assertion failures so the test suite never hangs. Give each test distinct identifying parameters or clean metadata **strictly inside a dedicated test database**.

For the async test, after `JobExecution initial = asyncLauncher.run(testJob, params)`, verify the call returned before `release` opens, then poll `JobExplorer.getJobExecution(initial.getId())` until terminal status within a finite timeout. Never assert an exact intermediate state like **`STARTING`**, since the thread scheduler may advance to `STARTED` almost instantly.

### 14.2. Testing Against Lost or Duplicate Jobs on Concurrent Submits

Requests sharing `jobName` and identifying parameters need deterministic outcomes:

- If already running: return conflict or link to active execution.
- If already completed: do not inadvertently launch a new job.
- If previously failed: restart if restartable and permitted by policy.
- If client retries after HTTP timeout: do not mint a new instance via random `run.id`.

Tests can fire two concurrent requests via a latch and count `JobInstance`/`JobExecution` rows in `JobRepository`. Expectations must reflect the application's idempotency design, not HTTP status codes alone.

### 14.3. Testing Final Status and Execution Failures

For async:

1. Submit job, capture execution ID.
2. Poll status until terminal state or test timeout.
3. For a passing fixture, verify `COMPLETED`.
4. For a fixture throwing in processor/writer, verify `FAILED` and ensure the status API never returns `COMPLETED`.
5. Check logs/metrics include execution ID without sensitive payloads.
6. Check listeners/notifications emit final events per rules, never solely on `STARTING`.

To verify crash recovery, integration tests must actually restart the process/worker and reconcile metadata/queues. Unit tests on `TaskExecutorJobLauncher` cannot prove an in-memory queue is durable.

### 14.4. Testing Capacity and Shutdown

A load test can configure a small executor (`core=1`, `max=1`, bounded queue), hold one job via latch, and submit additional requests. Verify:

- Rejected requests return proper error codes, never false success.
- Concurrent jobs never exceed configured bounds.
- No execution lingers unnoticed in `STARTING`.
- Stopping the context per policy does not lose track of work.
- DB connections, worker threads, and queue depth stay bounded.

This tests the **orchestration layer**, distinct from throughput benchmarking of a chunk step.

## 15. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using synchronous launcher for a 2-hour job in an HTTP request | HTTP timeouts, pinned request threads, client duplicate retries | Return `202`, track by execution ID, or use dedicated workers |
| Using async launcher in CLI and letting JVM exit | Job aborts early, exit code misreports status | Synchronous CLI or controlled wait for completion |
| Treating async `JobLauncher.run()` return as job success | False success reporting | Track `JobExecution` to terminal status |
| Using unbounded `SimpleAsyncTaskExecutor` | Uncontrolled thread/job spikes, DB overload | Bounded executor and backpressure |
| Generating random `run.id` per retry request | Multiple `JobInstance`s duplicating data processing | Stable identifying parameters and idempotent submission |
| Keeping status only in an in-memory `Map` | Lost job visibility on JVM restart | Persistent `JobRepository`, query via `JobExplorer` |
| Treating executor queue as a durable queue | Accepted requests lost on process crash | Durable command store/queue or orchestrator |
| Ignoring task rejections | Stuck executions, misleading API status | Bound load, return proper error, reconcile metadata |
| Passing entities/request-scoped beans to async threads | Closed context, uncommitted data, or race conditions | Persist snapshots durably and reload in worker |
| Not sizing executor relative to DB pool | Jobs stall waiting for JDBC connections | Budget total concurrency against connection pool |
| Exposing raw exception messages in status API | Leaks SQL, payloads, or sensitive details | Return vetted error codes and execution ID |
| Stopping async jobs with arbitrary `Thread.interrupt()` | Half-baked data or transactions | `JobOperator.stop` with graceful stop and timeout |
| Forgetting to disable Boot startup runner in API service | Jobs auto-run on deploy outside API requests | `spring.batch.job.enabled=false` |
| Restarting jobs with altered parameters | Loses checkpoints, duplicates work | Preserve identifying parameters on restart |
| Measuring HTTP latency instead of job duration | API looks fast while jobs miss SLAs | Track submission, queue delay, runtime, and publish |

## 16. Practice Exercises: Choosing Launch Mode by Requirement

Suppose you are building `dailyReportJob`, reading 500,000 orders, aggregating by region, and writing a report table:

1. **Synchronous baseline:** configure `SyncTaskExecutor`, run from a Java service or CLI. Record `run()` start time, return time, execution ID, and final status.
2. **Async launcher:** configure `ThreadPoolTaskExecutor` (`core=2`, `max=4`, bounded queue). Submit the same job and observe `run()` returning while the job is still active.
3. **Status API:** build `POST /batch/jobs/daily-report` returning `202` + `Location`, and `GET /batch/executions/{id}` returning status from `JobExplorer`. Do not serialize raw `JobExecution`.
4. **Duplicate submission:** send two requests with identical `businessDate` and `region`. Verify the system prevents two unintended concurrent business runs.
5. **Failure outcome:** have the processor throw an exception after acceptance. Confirm the initial HTTP `202` never causes terminal status to appear as `COMPLETED`.
6. **Long-running job:** hold a step with a latch. Observe the caller blocking under sync vs. returning early under async while the worker still holds resources.
7. **Executor saturation:** hold active jobs, fill the queue, and submit extra requests. Define appropriate error responses and detection for undispatched executions.
8. **CLI scheduler:** run the same job via `java -jar`, comparing exit-code handling under synchronous launch vs. risks when a startup launcher returns before completion.
9. **Graceful shutdown:** simulate restarting the service while an async job runs. Inspect metadata, stop/restart policies, and recoverability; explain why an in-memory queue cannot satisfy durability requirements.
10. **Architecture proposal:** for a job taking 45 minutes with 20 requests/day and zero lost commands during API deploys, choose between in-process async vs. API + durable queue + dedicated worker; justify using SLAs, concurrency, and recovery.

## 17. Final Decision Rule

Start with four questions:

1. **Does the caller genuinely need the final result in the same call?** If yes and runtime is short, synchronous fits.
2. **Must the caller respond quickly despite a long-running job?** If yes, asynchronous at the communication boundary is the right choice.
3. **Must the job continue reliably if the request-serving JVM restarts?** If yes, you need durable submission/workers or an external orchestrator—not just an in-JVM executor.
4. **Who is responsible for knowing whether the job succeeded or failed?** If you cannot name the status repository, monitoring mechanism, and recovery path, your async architecture is incomplete.

**Conclusion:** Synchronous vs. asynchronous launch is a choice about **coordination between caller and job execution**, not directly about item-processing speed. **Synchronous** keeps CLI batches and sequential workflows simple; **asynchronous** fits APIs/services needing fast responses, provided it is backed by durable state, concurrency bounds, idempotency, error tracking, and lifecycle management. For high durability, **an externally asynchronous API paired with workers launching Spring Batch synchronously inside** often delivers both fast responses and consistent execution control.
