# Logging JobInstance and JobExecution in Spring Batch

When operating Spring Batch, messages like "Job failed" or "Job completed" are rarely enough to identify **which run** occurred, whether it was a restart, which records were processed, and which step failed. A system may run the same Job hundreds of times per day; if logs are not tied to the identity of each execution, incident investigation becomes difficult.

Within the **Monitoring** topic of **Spring Batch Core Processing**, "Logging JobInstance and JobExecution" is the technique of emitting structured information about **JobInstance** and **JobExecution** at key milestones in the Job lifecycle. The goal is tracing a run from launch request to completion, while distinguishing the history of a logical unit of work from each individual attempt to run it.

This lesson covers the identity model, recommended log fields, using `JobExecutionListener`, linking Job and Step logs, caveats with asynchronous launchers, querying history via `JobExplorer`, and testing log output.

## 1. Understanding Job, JobInstance, and JobExecution Correctly

Spring Batch has three related yet distinct concepts:

- **`Job`:** the definition of work to perform, e.g., `dailySettlementJob`.
- **`JobInstance`:** a logical unit of work, identified by **Job name** and the set of **identifying JobParameters**. For example, the Job processing business date `2026-11-16`.
- **`JobExecution`:** a single attempt to run a JobInstance. If the first attempt fails and is restarted, it remains **the same JobInstance**, but gets a **new JobExecution**.

Example history:

```text
Job: dailySettlementJob
│
├── JobInstance #51
│   identifying parameters: {businessDate=2026-11-16}
│   ├── JobExecution #2001: FAILED
│   │   ├── StepExecution #3101: loadPaymentsStep     COMPLETED
│   │   └── StepExecution #3102: settlePaymentsStep  FAILED
│   └── JobExecution #2002: COMPLETED (restart)
│       └── StepExecution #3103: settlePaymentsStep  COMPLETED
│
└── JobInstance #52
    identifying parameters: {businessDate=2026-11-17}
    └── JobExecution #2003: COMPLETED
```

In this example:

| Field | Meaning | Value when searching logs |
| --- | --- | --- |
| `jobName` | Name of the Job definition, e.g., `dailySettlementJob`. | Filter by job type. |
| `jobInstanceId` | ID of the logical unit of work. | Group restarts belonging to the same business data. |
| `jobExecutionId` | ID of an actual run attempt. | Track status, errors, and timing of **one exact run**. |
| `stepName` | Name of the executed Step. | Isolate which stage encountered an issue. |
| `stepExecutionId` | ID of a single Step execution. | Distinguish Steps across restarts or different partitions. |
| `businessDate`/`windowKey` | Business parameter **approved for logging**. | Link business data to the execution unit. |

**Do not use `jobName` alone as a correlation key.** Two `JobExecution`s of the same Job name can run concurrently; the Job name alone cannot tell which run a log line belongs to.

### How Identifying JobParameters Affect JobInstance

Suppose there are two parameter sets:

```text
A: dailySettlementJob + businessDate=2026-11-16 + requestId=abc
B: dailySettlementJob + businessDate=2026-11-16 + requestId=xyz
```

If `requestId` is marked **identifying**, A and B are two distinct JobInstances. If `requestId` is **non-identifying** and `businessDate` is identifying, they map to the same JobInstance.

Therefore, logs should include both the actual IDs assigned by `JobRepository` and a safe business key (such as processing date). Avoid reconstructing JobInstance identity from arbitrary parameter strings and treating that as a unique ID.

## 2. Events to Log Across the Job Lifecycle

An easy-to-follow event sequence:

```text
Scheduler / API / Message consumer
  │
  ├─ batch.job.launch.requested    (job launch requested)
  │
  ├─ batch.job.launch.accepted     (JobRepository creates JobExecution)
  │   │
  │   ├─ batch.job.started         (Job starts executing)
  │   │
  │   ├─ batch.step.started        (Step starts)
  │   ├─ batch.step.finished       (Step ends)
  │   │
  │   └─ batch.job.finished        (Job ends)
  │
  └─ batch.job.launch.rejected     (failed to create execution)
```

Not every Job emits all events. For example, `JobExecutionAlreadyRunningException` can happen **before a new JobExecution is created**. In that case, a `launch.rejected` event occurs, with no new `jobExecutionId` to log.

| Event | Appropriate log point | Recommended fields |
| --- | --- | --- |
| Launch requested | Scheduler layer or service calling launcher/operator | `jobName`, `trigger`, `requestId`, allowed business parameters |
| Launch accepted | Immediately after launch call returns | `jobInstanceId`, `jobExecutionId`, initial status |
| Job started | `JobExecutionListener.beforeJob` | instance/execution IDs, `jobName`, start timestamp |
| Step started/finished | `StepExecutionListener` or equivalent observer | execution IDs, `stepName`, record counts |
| Job finished | `JobExecutionListener.afterJob` | `BatchStatus`, `ExitStatus`, duration, and error count |
| Rejected/launch error | `catch` block in scheduler/service | exception type, Job name, request ID; non-sensitive info |

Separating **accepted** and **finished** is critical with asynchronous launchers: returning from `run(...)` does not mean the Job succeeded.

## 3. Essential Log Fields and Log Levels

A Job-finished event should answer: which Job, which instance, which execution, how did it finish, and how long did it take?

```text
INFO  batch.job.finished
      jobName=dailySettlementJob
      jobInstanceId=51
      jobExecutionId=2002
      status=COMPLETED
      exitCode=COMPLETED
      durationMs=4280
```

This illustrates field structure, not a mandate for one specific log format. Hypothetical values such as IDs and duration are purely illustrative.

Recommended conventions:

| Field | Content | Suggestion |
| --- | --- | --- |
| `event` | `batch.job.started`, `batch.job.finished`, ... | Keep names stable across code versions. |
| `jobName` | Job name. | Keep the exact name defined in Spring Batch. |
| `jobInstanceId` | ID from `JobInstance`. | Used to link restart attempts. |
| `jobExecutionId` | ID from `JobExecution`. | Used to open metadata of the exact execution. |
| `batchStatus` | `COMPLETED`, `FAILED`, `STOPPED`, ... | Reflects execution status. |
| `exitCode` | Exit code from `ExitStatus`. | May be an application-customized code. |
| `durationMs` | Elapsed time between start and end timestamps. | Compute only when both valid timestamps are present. |
| `failureCount` | Count of collected exceptions. | Useful for diagnostics; not the skipped record count. |
| `trigger` | `scheduler`, `manual`, `api`, `retry`,... | Identifies trigger source when multiple launch paths exist. |
| `businessDate` | Date/data window approved for logging. | Never log parameters containing private data or secrets. |
| `traceId`/`requestId` | Correlation ID from the calling system. | Helps connect application logs with external services. |

**Recommended log levels:**

- `INFO` for major Job/Step state transitions and normal completion outcomes.
- `WARN` for handleable abnormal outcomes, such as an intentional `STOPPED` Job, ignored triggers, or skips crossing a business warning threshold.
- `ERROR` when a Job fails or a severe launch error occurs; distinguish real failures from valid rejections like an already-running Job.
- `DEBUG` for safely filtered parameters, branching decisions, and diagnostic details.
- `TRACE` for ultra-detailed information only when needed, with volume and security controls.

If a Job processes millions of records, **never emit an INFO log for every item**. Log at Job/Step/chunk boundaries or emit summary counters; logging per record can turn logging into the pipeline bottleneck.

## 4. Automatic Logging with `JobExecutionListener`

`JobExecutionListener` is the right extension point for consistent logging across every run of a Job. It has two main callbacks:

- `beforeJob(JobExecution execution)`: invoked before the Job executes its steps.
- `afterJob(JobExecution execution)`: invoked after Job execution finishes with a terminal status, ideal for recording results.

The example below uses **Spring Batch 5.x**, **Spring Boot 3.x**, and **SLF4J**. In Spring Batch 6.x, some types move to subpackages; log contents and callback semantics stay the same.

```java
package example.batch.monitoring;

import java.time.Duration;
import java.time.LocalDateTime;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.stereotype.Component;

@Component
public class BatchExecutionLoggingListener
        implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(BatchExecutionLoggingListener.class);

    @Override
    public void beforeJob(JobExecution execution) {
        log.info(
            "batch.job.started jobName={} jobInstanceId={} "
                + "jobExecutionId={} batchStatus={} businessDate={}",
            execution.getJobInstance().getJobName(),
            execution.getJobInstance().getInstanceId(),
            execution.getId(),
            execution.getStatus(),
            execution.getJobParameters().getString("businessDate")
        );
    }

    @Override
    public void afterJob(JobExecution execution) {
        Long durationMs = elapsedMillis(
                execution.getStartTime(),
                execution.getEndTime()
        );

        log.info(
            "batch.job.finished jobName={} jobInstanceId={} "
                + "jobExecutionId={} batchStatus={} exitCode={} "
                + "durationMs={} failureCount={}",
            execution.getJobInstance().getJobName(),
            execution.getJobInstance().getInstanceId(),
            execution.getId(),
            execution.getStatus(),
            execution.getExitStatus().getExitCode(),
            durationMs,
            execution.getAllFailureExceptions().size()
        );

        for (StepExecution step : execution.getStepExecutions()) {
            log.info(
                "batch.step.finished jobExecutionId={} "
                    + "stepExecutionId={} stepName={} batchStatus={} "
                    + "readCount={} writeCount={} skipCount={} "
                    + "commitCount={} rollbackCount={}",
                execution.getId(),
                step.getId(),
                step.getStepName(),
                step.getStatus(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getSkipCount(),
                step.getCommitCount(),
                step.getRollbackCount()
            );
        }

        if (execution.getStatus() == BatchStatus.FAILED) {
            execution.getAllFailureExceptions().stream()
                    .findFirst()
                    .ifPresent(error -> log.error(
                        "batch.job.failure jobExecutionId={} "
                            + "exceptionType={}",
                        execution.getId(),
                        error.getClass().getName()
                    ));
        }
    }

    private static Long elapsedMillis(
            LocalDateTime started, LocalDateTime ended) {
        if (started == null || ended == null) {
            return null;
        }
        return Duration.between(started, ended).toMillis();
    }
}
```

In the code above:

1. `jobInstanceId` finds all attempts belonging to the same logical unit of work.
2. `jobExecutionId` connects each Step's logs to the exact execution.
3. `batchStatus` is Spring Batch's status enum.
4. `exitCode` comes from `ExitStatus`, which can differ from `batchStatus` if the application configures custom outcomes.
5. `businessDate` is a pre-approved **log-safe field**; never dump all `JobParameters`.
6. `durationMs` is computed only when both timestamps exist. If the callback or metadata persistence mechanism in a version has not yet populated `endTime` at that moment, the field can be `null`; do not guess.
7. `failureCount` indicates how many exceptions were collected, not directly how many items were retried or skipped.
8. Error logging prints only **the exception class name** by default; logging messages or stack traces must respect security rules because exceptions can contain input data.

To register the listener on a Job built via Java configuration:

```java
@Bean
Job dailySettlementJob(
        JobRepository jobRepository,
        Step settlementStep,
        BatchExecutionLoggingListener loggingListener) {

    return new JobBuilder("dailySettlementJob", jobRepository)
            .listener(loggingListener)
            .start(settlementStep)
            .build();
}
```

`Job`, `Step`, `JobBuilder`, and `JobRepository` are imported for your current Spring Batch version. This snippet assumes `settlementStep` is a Step bean already configured in the application.

**Register the listener on the Job configuration**, rather than only annotating `@Component`: a Spring-managed bean that is not attached to a Job will never have its callbacks invoked. Sharing a single stateless listener across multiple Jobs promotes a consistent log format.

### Why Not Log Only in the Scheduler?

The scheduler knows **who requested the run**, but does not necessarily know **when the Job ends**, especially with an asynchronous launcher. A listener executes within the Job lifecycle and can read details of the active execution. Both logging layers complement each other:

- Scheduler/service: logs the trigger source and errors **before the Job is accepted**.
- Listener: logs the outcomes **of a created JobExecution**.

A Job might be launched via REST API, cron, message consumer, or manual action; attaching the listener on the Job ensures no valid launch path is missed.

## 5. Logging Launch Requests and Errors Before JobExecution Creation

Some errors occur immediately when invoking the launcher: the Job is already running, the instance already completed, parameters are invalid, or the repository hits an error. In those cases, `afterJob` is not the sole place to observe failures.

Spring Batch 5.x example:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionException;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.launch.JobLauncher;

public final class BatchLaunchService {

    private static final Logger log =
            LoggerFactory.getLogger(BatchLaunchService.class);

    private final JobLauncher jobLauncher;
    private final Job job;

    public BatchLaunchService(JobLauncher jobLauncher, Job job) {
        this.jobLauncher = jobLauncher;
        this.job = job;
    }

    public JobExecution launch(JobParameters parameters)
            throws JobExecutionException {
        String businessDate = parameters.getString("businessDate");

        log.info("batch.job.launch.requested jobName={} businessDate={}",
                job.getName(), businessDate);

        try {
            JobExecution execution = jobLauncher.run(job, parameters);

            log.info(
                "batch.job.launch.accepted jobName={} "
                    + "jobInstanceId={} jobExecutionId={} batchStatus={}",
                job.getName(),
                execution.getJobInstance().getInstanceId(),
                execution.getId(),
                execution.getStatus()
            );
            return execution;

        } catch (JobExecutionException ex) {
            log.warn(
                "batch.job.launch.rejected jobName={} "
                    + "businessDate={} exceptionType={}",
                job.getName(),
                businessDate,
                ex.getClass().getSimpleName()
            );
            throw ex;
        }
    }
}
```

In production systems, the service can also receive a `requestId` or `triggerId` generated at the ingress layer. Having a stable ID per request lets you link `launch.requested` with `launch.accepted` or `launch.rejected`, even when no `jobExecutionId` exists yet.

The `launch.accepted` event **must never be named `job.finished`**. If the launcher uses an asynchronous executor, `execution.getStatus()` upon return may still be `STARTING` or `STARTED`. The terminal status must be read after execution completes.

### Categorizing Launch Errors

| Error | Common meaning | Log handling |
| --- | --- | --- |
| `JobExecutionAlreadyRunningException` | Same JobInstance is currently executing. | Log as a duplicate trigger or coordination condition; WARN/INFO per policy. |
| `JobInstanceAlreadyCompleteException` | JobInstance already completed. | Determine whether it is an intentional duplicate request or wrong identifying parameters. |
| `JobParametersInvalidException` | Parameters fail validation. | Log error type and safe parameter names; never log secret values. |
| `JobRestartException` | Invalid restart attempt. | Check prior status, restartability, and metadata. |
| Datasource/`JobRepository` error | Unable to create or persist execution normally. | Emit ERROR log with request/trace ID and investigate infrastructure. |

Do not assume every `JobExecutionException` is a business error inside a running JobExecution. In many cases, no Step ran at all.

## 6. Logging StepExecution to Explain Job Outcomes

`JobExecution` reflects the status of the whole Job; `StepExecution` reveals what the Job did in each step.

Example:

```text
INFO  batch.job.started  jobName=importOrdersJob
      jobInstanceId=72 jobExecutionId=810

INFO  batch.step.finished jobExecutionId=810
      stepExecutionId=1801 stepName=readOrders
      batchStatus=COMPLETED readCount=100 writeCount=100 skipCount=0

INFO  batch.step.finished jobExecutionId=810
      stepExecutionId=1802 stepName=writeOrders
      batchStatus=FAILED readCount=60 writeCount=40
      skipCount=0 rollbackCount=1

INFO  batch.job.finished jobName=importOrdersJob
      jobInstanceId=72 jobExecutionId=810
      batchStatus=FAILED exitCode=FAILED
```

Reading these logs identifies that the `writeOrders` Step had an issue in the specific run `jobExecutionId=810`. You cannot conclude that 100 records were written to the final destination just from `readOrders` completing; counts must be interpreted against the Job's structure and actual fixtures.

### Dedicated Listener for Steps

When you want logs immediately as a Step starts or finishes instead of waiting for the entire Job to finish, use `StepExecutionListener`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public final class BatchStepLoggingListener
        implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(BatchStepLoggingListener.class);

    @Override
    public void beforeStep(StepExecution step) {
        log.info(
            "batch.step.started jobExecutionId={} "
                + "stepExecutionId={} stepName={}",
            step.getJobExecutionId(),
            step.getId(),
            step.getStepName()
        );
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
            "batch.step.finished jobExecutionId={} "
                + "stepExecutionId={} stepName={} batchStatus={} "
                + "exitCode={} readCount={} writeCount={} skipCount={}",
            step.getJobExecutionId(),
            step.getId(),
            step.getStepName(),
            step.getStatus(),
            step.getExitStatus().getExitCode(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getSkipCount()
        );

        // Do not change the ExitStatus already decided for the Step.
        return step.getExitStatus();
    }
}
```

Register the listener on the Step when configuring the Step builder. In some setups, Spring Batch already emits logs at launcher/step layers; review logging configuration to avoid generating duplicate events. Never alter `ExitStatus` in a listener meant purely for logging.

### Step Counters Understood in Business Context

| Counter | Observational purpose |
| --- | --- |
| `readCount` | Number of items read under Step mechanics. |
| `writeCount` | Number of items successfully written under Step mechanics. |
| `filterCount` | Number of items filtered out by the processor. |
| `readSkipCount` / `processSkipCount` / `writeSkipCount` | Breakdown of where items were skipped. |
| `skipCount` | Total number of skipped items. |
| `commitCount` | Number of transaction commits recorded for the Step. |
| `rollbackCount` | Number of recorded rollbacks. |

Do not treat `readCount == writeCount` as a mandatory invariant for every Job. If the processor filters records, if a Step only validates data, or if the Job permits skips, the two counters can differ while the Job still ends `COMPLETED`.

## 7. Distinguishing `BatchStatus` and `ExitStatus` in Logs

The two properties serve different purposes:

```java
BatchStatus batchStatus = execution.getStatus();
String exitCode = execution.getExitStatus().getExitCode();
String exitDescription =
        execution.getExitStatus().getExitDescription();
```

- **`BatchStatus`:** execution status, e.g., `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, `STOPPED`.
- **`ExitStatus`:** completion outcome carrying `exitCode` and `exitDescription`, customizable by flows and listeners.

For example, a Job may have:

```text
batchStatus=COMPLETED
exitCode=COMPLETED_WITH_WARNINGS
```

This can be completely valid under the business contract if the Job finished with warnings. Logging only `status=COMPLETED` loses the extra exit information; logging both explains flow routing decisions.

**Do not log `exitDescription` verbatim by default** if it might contain stack traces, SQL queries, input data, or customer details. Log a standardized error code in general logs, and route detailed descriptions to a secure, policy-compliant store.

## 8. Linking Restarts by JobInstance

Review the event sequence:

```text
batch.job.started
  jobName=dailySettlementJob jobInstanceId=51 jobExecutionId=2001

batch.job.finished
  jobName=dailySettlementJob jobInstanceId=51
  jobExecutionId=2001 batchStatus=FAILED

batch.job.started
  jobName=dailySettlementJob jobInstanceId=51 jobExecutionId=2002

batch.job.finished
  jobName=dailySettlementJob jobInstanceId=51
  jobExecutionId=2002 batchStatus=COMPLETED
```

When investigating an error, filter by `jobInstanceId=51` first to see **all attempts**. Then filter by `jobExecutionId=2001` to examine only the failed attempt and its Steps.

A normal restart may skip re-running Steps that already `COMPLETED` previously. Therefore, `afterJob` logs only the `StepExecution`s actually belonging to the current `JobExecution`; do not assume a restart has the exact same list of `StepExecution`s as the initial run.

### Choosing Identifying Parameters

Spring Batch 5.x example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("triggerRequestId", "request-abc", false)
        .toJobParameters();
```

Here `businessDate` identifies the unit of work; `triggerRequestId` is marked non-identifying so a new launch request does not create a new JobInstance. This is appropriate only if business rules truly define one instance per processing day.

If a Job runs multiple distinct windows per day, use an identifying key representing the exact window, such as `windowStart`. Never change identifying parameters arbitrarily on restart, as doing so creates a new JobInstance and breaks the link to earlier history.

## 9. Logging in Asynchronous Jobs and Multithreaded Steps

### 9.1. Asynchronous JobLauncher

With an asynchronous launcher, the timeline looks like:

```text
Scheduler thread                   batch-worker thread
----------------                   -------------------
launch.requested
JobLauncher.run(...)
launch.accepted status=STARTING
return from scheduled method
                                   beforeJob -> job.started
                                   execute Step...
                                   afterJob -> job.finished
```

The `launch.accepted` line proves the Job was accepted to run, **not that the Job has finished**. To get the terminal status, re-read `JobExecution` via `JobExplorer` or use a monitoring mechanism with a timeout.

Spring Batch 5.x example:

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution == null) {
    // Possibly metadata is not ready yet or the ID does not exist.
} else {
    log.info(
        "batch.job.observed jobExecutionId={} batchStatus={} exitCode={}",
        execution.getId(),
        execution.getStatus(),
        execution.getExitStatus().getExitCode()
    );
}
```

In systems requiring polling, always enforce timeouts and terminal status checks; never poll infinitely. When a Job stops abruptly, metadata can remain `STARTED`. Inspect update timestamps and worker infrastructure before concluding the Job is definitely still running.

### 9.2. Multithreaded Steps and `MDC`

SLF4J `MDC` (*Mapped Diagnostic Context*) attaches IDs to log lines on the same thread:

```java
import org.slf4j.MDC;

try (MDC.MDCCloseable context =
        MDC.putCloseable(
                "jobExecutionId",
                String.valueOf(execution.getId()))) {

    log.info("processing batch chunk");
}
```

Example Logback pattern that reads MDC:

```text
%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level
jobExecutionId=%X{jobExecutionId:-} [%thread] %logger - %msg%n
```

However, MDC relies on **thread-local state**. When `TaskExecutor` dispatches work to worker threads or a Step uses multiple threads, the caller thread's MDC does not automatically appear in workers.

Two approaches:

1. **Pass IDs directly as log arguments** in listeners, Steps, and tasks: straightforward, independent of MDC propagation across threads.
2. If MDC is needed across all worker logs, use a `TaskDecorator` or controlled wrapper to **capture context, apply it in the worker, and restore the prior context in `finally`**. This is critical with thread pools because worker threads are reused.

Example `TaskDecorator` propagating the context present at submission time:

```java
import java.util.Map;

import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> original = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (original == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(original);
                }
            }
        };
    }
}
```

Attach this decorator to `ThreadPoolTaskExecutor` when configuring executors for paths needing MDC propagation. **The decorator only captures context existing at submit time**: if `jobExecutionId` has not yet been placed in MDC when the task is created, the decorator cannot know it. Listener logs can still pass IDs explicitly so everything remains traceable.

Also, never call `MDC.put(...)` without `MDC.remove(...)`/`MDC.clear()` when the scope exits. Thread pools reuse workers for other Jobs, which would stamp logs with a stale ID from a previous run.

### 9.3. Partitioning and Remote Workers

With partitioning or remote chunking, one JobExecution can spawn multiple StepExecutions or processes on different workers. Propagate a **job-level correlation ID** via messages/headers or safe metadata; log on workers with `jobExecutionId`, `stepExecutionId`, `partitionId`, and business IDs where appropriate.

Do not rely solely on thread names or hostnames, as one JobExecution can span multiple threads or hosts, and thread names are reused across runs.

## 10. Querying History with `JobExplorer` and JobRepository

**Logs support observability; Spring Batch metadata is the authoritative source for execution status and history.** When logs are lost due to log pipeline failures or killed processes, reconcile against `JobRepository`.

`JobExplorer` provides the metadata read interface. Example:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

public final class BatchHistoryReader {

    private final JobExplorer jobExplorer;

    public BatchHistoryReader(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution findExecution(Long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
```

After fetching a JobExecution, you can access:

```java
JobExecution execution = reader.findExecution(2001L);

if (execution != null) {
    String jobName = execution.getJobInstance().getJobName();
    Long instanceId = execution.getJobInstance().getInstanceId();
    Long executionId = execution.getId();
    BatchStatus status = execution.getStatus();

    // Use the IDs and status to cross-reference centralized logs.
}
```

You can also fetch recent instances by Job name and then inspect the executions belonging to each instance:

```java
jobExplorer.getJobInstances("dailySettlementJob", 0, 20)
        .forEach(instance -> {
            jobExplorer.getJobExecutions(instance)
                    .forEach(execution -> log.info(
                        "batch.job.history jobName={} "
                            + "jobInstanceId={} jobExecutionId={} status={}",
                        instance.getJobName(),
                        instance.getInstanceId(),
                        execution.getId(),
                        execution.getStatus()
                    ));
        });
```

This snippet is an on-demand **history-reading** operation for admin tools or monitoring tasks. Do not run full history queries on every processed item; continuous metadata reads place unnecessary load on the database.

### SQL for Cross-Checking Metadata

With the default relational schema, you can find the JobInstance of an execution across two metadata tables:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE je.JOB_EXECUTION_ID = :execution_id;
```

Table names may vary with `tablePrefix`; schema details can vary by database engine and Spring Batch version. This SQL query is meant for investigation, **not for updating Job status**. Never manually edit metadata records to make logs "look right."

## 11. Distinguishing Logs, Metrics, and Tracing

Three observability signals are commonly used together:

| Signal | Question answered | How IDs are used |
| --- | --- | --- |
| **Logs** | What happened during a specific execution? | Attach `jobInstanceId`, `jobExecutionId`, `stepExecutionId`. |
| **Metrics** | How are error rates, runtimes, and throughput changing? | Low-cardinality tags: Job/Step name, status. |
| **Traces** | Which components/services did the work traverse? | Trace/span IDs linking operations when tracing is enabled. |

`jobExecutionId` is an invaluable search key in logs, yet **must not be used as a metric tag**: every run creates a new value, causing high cardinality in time-series databases. Likewise, never turn file paths, user IDs, or transaction IDs into metric labels.

Spring Batch includes observability and metric hooks depending on version and Micrometer setup. Even when automatic metrics are enabled, manual logs remain helpful for linking individual runs—just avoid duplicating two sets of metrics with the same meaning or double-recording each event.

## 12. Never Leak Data in Logs or Let Logging Break the Job

A `JobParameters` map may contain filenames, host paths, customer IDs, tokens, or connection strings. `ExecutionContext` may hold checkpoints and sensitive intermediate data. Therefore:

- **Log only allowlisted parameters** such as `businessDate` or pre-classified safe partition codes.
- Never dump `execution.getJobParameters()`, the full `ExecutionContext`, or item contents into INFO logs.
- Never automatically log access tokens, passwords, auth headers, account details, customer emails, or record payloads.
- If full technical error logs are required, enforce access controls, retention, and masking before sending to the log sink.
- Check the length and contents of `exitDescription` and exception messages before logging, as they can contain unsanitized data.
- Use SLF4J `{}` placeholders to avoid expensive string concatenation when a log level is disabled.

Inside listeners, avoid heavy operations and synchronous network calls. Logging is for observability; it should never mutate business state or introduce a new failure point for the Job. If the log sink experiences issues, rely on proper collection buffering and separate monitoring; do not assume every log line is durably persisted before the Job exits.

## 13. Testing JobInstance and JobExecution Logging

Beyond asserting Job status, you can verify that listeners emit all required correlation IDs. Spring Boot provides `OutputCaptureExtension` to capture log output in integration tests.

Spring Batch 5.x / Spring Boot 3.x example:

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@ExtendWith(OutputCaptureExtension.class)
class BatchExecutionLoggingIT {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("dailySettlementJob")
    private Job dailySettlementJob;

    @Test
    void shouldLogBothInstanceAndExecutionId(CapturedOutput output)
            throws Exception {

        jobLauncherTestUtils.setJob(dailySettlementJob);

        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", UUID.randomUUID().toString())
                .addString("businessDate", "2026-11-16")
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);

        assertThat(output.getOut())
                .contains("batch.job.started")
                .contains("batch.job.finished")
                .contains("jobExecutionId=" + execution.getId())
                .contains("jobInstanceId="
                        + execution.getJobInstance().getInstanceId());
    }
}
```

Assumptions for this test to be meaningful:

1. `dailySettlementJob` is registered with `BatchExecutionLoggingListener` from Section 4.
2. The Job has valid fixtures to complete successfully; the test snippet itself does not populate Job data.
3. The listener's logger level is `INFO` or lower and writes to an appender captured by `OutputCaptureExtension`.
4. The Job runs synchronously in the test; if executed asynchronously, wait for Job completion before asserting logs.
5. `JobRepository` and business test data are isolated so other tests are unaffected.

Do not assert **the entire log line string** including timestamps, thread names, durations, logger positions, or exact ordering across parallel tasks. Those vary by environment. Focus assertions on **event names** and **accurate IDs**.

### Testing Failure and Restart

A logging test suite for failure scenarios can:

1. Launch the Job with input engineered to fail a Step.
2. Assert `JobExecution.status == FAILED`.
3. Assert logs contain `batch.job.finished`, `batchStatus=FAILED`, `jobExecutionId`, and the expected error type.
4. Fix the failure condition and restart using **the same identifying parameters**.
5. Assert the restarted run has the same `jobInstanceId` as the first run, but a different `jobExecutionId`.
6. Verify logs contain two distinct finished events to trace each execution.

For restart tests, **do not clean metadata between the failed run and the restart**. Clean up only after assertions finish, using dedicated test `JobRepository` cleanup utilities.

## 14. Common Logging Mistakes

### Logging Only the Job Name

```text
INFO importOrdersJob completed
```

This log line does not reveal which run, which day's data, or whether it was a restart. Add `jobInstanceId`, `jobExecutionId`, and a safe business key.

### Confusing JobInstance ID with JobExecution ID

One JobInstance can have many JobExecutions. Putting `jobInstanceId` into the `jobExecutionId` field prevents operators from telling a failed run apart from its restart. Always call the proper getters on `JobExecution` and `JobInstance`.

### Assuming `JobLauncher.run(...)` Returning Means the Job Finished

With an asynchronous executor, returning means only that the Job was accepted. Log `launch.accepted` and rely on listeners or `JobExplorer` for the final outcome.

### Logging All `JobParameters` and `ExecutionContext`

This creates sensitive data exposure risks and bloated logs. Log an allowlist of pre-classified safe fields. For debugging checkpoints, use controlled administrative tools.

### Looking Only at `BatchStatus` and Ignoring `ExitStatus`

Applications may use custom exit codes such as `COMPLETED_WITH_WARNINGS`. Log both status and exit code to understand the published result accurately.

### Emitting INFO Logs for Every Item

At high volume, per-item logging increases latency, inflates storage cost, and buries critical events. Log at Job/Step boundaries and use metrics for throughput.

### Stale MDC After Thread Pool Worker Reuse

Forgetting to clear MDC in `finally` lets a new Job's logs inherit the previous Job's ID. Scope and restore context cleanly.

### Concluding a Job Stopped Just Because Logs Stopped

When a process dies or the log sink stalls, metadata may not reflect a terminal state yet. Cross-check `JobExplorer`, process health, update timestamps, and monitoring systems before deciding to restart or adjust metadata.

## 15. Hands-on Exercise

Build an `importInventoryJob` scheduled hourly to synchronize inventory. When encountering transient database errors, the Job can be restarted after the root cause is resolved.

**Exercise requirements:**

1. Define an identifying parameter `windowStart` for each hourly window. Verify two requests for the same window get the same JobInstance when other identifying parameters are unchanged.
2. Write a `JobExecutionListener` logging `batch.job.started` and `batch.job.finished` with `jobName`, `jobInstanceId`, `jobExecutionId`, `batchStatus`, and `exitCode`.
3. Write a `StepExecutionListener` logging read, write, filter, and skip counts per Step alongside execution IDs.
4. Add `launch.requested`/`launch.accepted`/`launch.rejected` logging in the orchestration layer.
5. Create a fixture that causes the Job to fail on its first run and succeed on restart. Query logs by `jobInstanceId` to observe **two distinct `jobExecutionId`s**.
6. Write a test using `OutputCaptureExtension` confirming both instance and execution IDs appear in logs.
7. Test with an asynchronous launcher; confirm `launch.accepted` can appear before `job.finished`.
8. Review all logged fields and strip any private, secret, or unapproved values.

An example of expected output:

```text
INFO batch.job.launch.requested jobName=importInventoryJob windowStart=10:00
INFO batch.job.started jobName=importInventoryJob jobInstanceId=100 jobExecutionId=800
ERROR batch.job.failure jobExecutionId=800 exceptionType=...
INFO batch.job.finished jobName=importInventoryJob jobInstanceId=100 jobExecutionId=800 batchStatus=FAILED
INFO batch.job.started jobName=importInventoryJob jobInstanceId=100 jobExecutionId=801
INFO batch.job.finished jobName=importInventoryJob jobInstanceId=100 jobExecutionId=801 batchStatus=COMPLETED
```

Searching by `jobInstanceId=100` shows the full history of the target window. Searching by `jobExecutionId=800` shows only the failed attempt. These two tracing keys complement each other and keep Spring Batch monitoring clear across retries, restarts, and parallel runs.

## References

- [Spring Batch Reference – Domain Language of Batch](https://docs.spring.io/spring-batch/reference/domain.html): relationships among `Job`, `JobInstance`, `JobExecution`, and `StepExecution`.
- [Spring Batch Reference – Intercepting Job Execution](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): metadata status, callbacks, and Job history.
- [Spring Batch Reference – Job and Step Listeners](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): Job/Step listeners and pre/post-execution actions.
- [Spring Batch Reference – Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): metadata tables storing execution history.
- [Spring Batch Reference – Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): observing batches via metrics and tracing.
- [Spring Boot Reference – Test Utilities](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): application testing and output capture tools.

