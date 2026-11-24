# Logging in Job Listeners in Spring Batch

## 1. Lesson Objectives

In Spring Batch, a job can be launched by a scheduler, an internal API, an operational command, or another job. When processing thousands or millions of records, knowing that “the job was invoked” is not enough to know **whether the job started executing, what status it ended with, how long it took, and where an error occurred**.

`JobExecutionListener` is a job-level extension point for recording key events right before and after Spring Batch executes a `JobExecution`. Placing logging here gives every execution a consistent audit trail without scattering start/finish log statements across every step.

In this lesson under the **Logging** group of **Spring Batch Core Processing**, you will learn how to:

- Distinguish logs from a scheduler/`JobLauncher` from logs in a `JobExecutionListener`.
- Use the two callbacks `beforeJob` and `afterJob`.
- Log the job name, instance ID, execution ID, safe business parameters, `BatchStatus`, `ExitStatus`, duration, and total record counts.
- Register a listener with `JobBuilder` in Spring Batch 5.x.
- Classify `INFO`, `WARN`, and `ERROR` logs; handle stack traces and sensitive data.
- Understand listener limitations when a job launch is rejected, a process is killed abruptly, execution runs asynchronously, or a job is restarted.
- Test logging behavior and observe results from a real job.

The examples use Java 17+, Spring Boot 3.x, Spring Batch 5.x, and SLF4J. In other versions, a few configuration APIs may differ, but the approach to organizing logs around the execution lifecycle remains similar.

## 2. Where JobExecutionListener Fits in the Processing Flow

A simple flow looks like this:

```text
Scheduler / REST / CLI
         |
         | call JobLauncher.run(job, parameters)
         v
     JobRepository
         |
         | create / validate JobExecution
         v
      Job starts
         |
         +-- JobExecutionListener.beforeJob(execution)
         |       -> log start event
         |
         +-- Step 1
         |      Reader -> Processor -> Writer
         |
         +-- Step 2
         |      Reader -> Processor -> Writer
         |
         +-- JobExecutionListener.afterJob(execution)
         |       -> log final status, duration, counts, errors
         |
         v
     Save metadata / return result to launcher
```

**Key distinction:** the listener belongs to the **JobExecution** lifecycle, whereas the scheduler belongs to the **launch request** lifecycle. If a scheduler re-invokes an already completed `JobInstance` and `JobLauncher` throws `JobInstanceAlreadyCompleteException`, Spring Batch does not create a new execution, so job listener callbacks are not executed for that rejected request.

Therefore:

- Logs in the **scheduler/launch coordinator** answer “who requested the run, when, and was the request accepted?”.
- Logs in the **job listener** answer “which execution started and how did it end?”.
- Logs in the **step/chunk/item listener** answer “which phase read, wrote, skipped, or handled what error?”.

All three log sources can be correlated using the job name, `jobInstanceId`, `jobExecutionId`, and a `correlationId` if the system requires one.

### Scope of Each Callback

| Callback | Timing and Data | What to Do |
| --- | --- | --- |
| `beforeJob(JobExecution)` | When a JobExecution is about to run its steps | Record start time, execution ID, job name, data period, trigger source if available |
| `afterJob(JobExecution)` | After job execution finishes under normal lifecycle flow | Log final status, exit code, duration, counts, and primary error |
| `beforeStep/afterStep` | Before/after each StepExecution | Log step-level details, warn on steps with abnormal record counts |
| `onReadError/onWriteError/onSkip...` | When an operation error occurs or an item is skipped | Support investigating specific errors; control log frequency |

`JobExecutionListener` is not called for **every cron trigger**. It is tied to an actual execution that has entered the job's processing flow.

## 3. JobInstance and JobExecution in Log Messages

Spring Batch distinguishes:

- **`Job`:** the job definition, for example `dailyReportJob`.
- **`JobInstance`:** the job name combined with `JobParameters` marked as identifying, for example `businessDate=2026-11-15`.
- **`JobExecution`:** a single attempt to execute that instance.

Suppose the November 15 aggregation job fails on the first run and then succeeds on restart:

```text
JobInstance 1201: dailyReportJob + businessDate=2026-11-15
   |
   +-- JobExecution 9001: FAILED
   |
   +-- JobExecution 9002: COMPLETED
```

If you only log `jobName=dailyReportJob` and `businessDate=2026-11-15`, it is hard to tell logs from the initial run apart from the restart. If you only log `jobExecutionId`, operators have a hard time telling which data period the execution is processing. You should therefore log **both the safe business key and the execution ID**.

Example of two log lines:

```text
event=batch.job.finished job=dailyReportJob instanceId=1201 executionId=9001 businessDate=2026-11-15 status=FAILED
event=batch.job.finished job=dailyReportJob instanceId=1201 executionId=9002 businessDate=2026-11-15 status=COMPLETED
```

This trail clearly shows one instance with two executions, not two different business periods.

## 4. Fields to Log in a Job Listener

A consistently structured log message is much easier to search than arbitrary prose scattered across places.

| Field | Source | Purpose |
| --- | --- | --- |
| `event` | Fixed value such as `batch.job.started` / `batch.job.finished` | Filter by event type |
| `job` | `execution.getJobInstance().getJobName()` | Identify the job |
| `jobInstanceId` | `execution.getJobInstance().getInstanceId()` | Identify the logical processing period |
| `jobExecutionId` | `execution.getId()` | Identify the run attempt |
| `businessDate` | Whitelisted from `JobParameters` | Identify the data period |
| `status` | `execution.getStatus()` | Final job-level status |
| `exitCode` | `execution.getExitStatus().getExitCode()` | Result that can be customized by a flow/step |
| `durationMs` | Execution start and end timestamps | Track SLA, latency |
| `readCount` / `writeCount` / `skipCount` | Sum across the execution's `StepExecution`s | Track processing volume |

Do not log the entire `JobParameters` by default: they may contain tokens, customer identifiers, sensitive paths, or business data. Instead, explicitly pick fields allowed in logs, such as a business date or a non-sensitive internal batch code.

### BatchStatus and ExitStatus Are Not the Same

`BatchStatus` represents the lifecycle status: `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, `STOPPED`, and several other statuses.

`ExitStatus` is the exit code used to evaluate the outcome and drive flow transitions; this code can be customized, such as `NO_DATA`. A job can have `BatchStatus.COMPLETED` while `ExitStatus` carries a business code other than `COMPLETED`. When investigating, logging both helps avoid wrong conclusions.

## 5. Implementing the Listener with SLF4J

Spring Boot starters typically already provide logging via SLF4J and a logging backend such as Logback. There is no need to add a new logging system just to log from a listener.

Implementation example:

```java
package com.example.batch.logging;

import java.time.Duration;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.stereotype.Component;

@Component
public class BatchJobLoggingListener implements JobExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(BatchJobLoggingListener.class);

    @Override
    public void beforeJob(JobExecution execution) {
        String jobName = execution.getJobInstance().getJobName();
        String businessDate =
            execution.getJobParameters().getString("businessDate");

        log.info(
            "event=batch.job.started job={} instanceId={} " +
            "executionId={} businessDate={} status={}",
            jobName,
            execution.getJobInstance().getInstanceId(),
            execution.getId(),
            businessDate,
            execution.getStatus()
        );
    }

    @Override
    public void afterJob(JobExecution execution) {
        String jobName = execution.getJobInstance().getJobName();
        String businessDate =
            execution.getJobParameters().getString("businessDate");

        BatchStatus status = execution.getStatus();
        String exitCode =
            execution.getExitStatus().getExitCode();

        long readCount = 0;
        long writeCount = 0;
        long filterCount = 0;
        long skipCount = 0;

        for (StepExecution step : execution.getStepExecutions()) {
            readCount += step.getReadCount();
            writeCount += step.getWriteCount();
            filterCount += step.getFilterCount();
            skipCount += step.getSkipCount();
        }

        Long durationMs = null;
        if (execution.getStartTime() != null &&
            execution.getEndTime() != null) {

            durationMs = Duration.between(
                execution.getStartTime(),
                execution.getEndTime()
            ).toMillis();
        }

        String message =
            "event=batch.job.finished job={} instanceId={} " +
            "executionId={} businessDate={} status={} exitCode={} " +
            "durationMs={} readCount={} writeCount={} " +
            "filterCount={} skipCount={}";

        Object[] fields = {
            jobName,
            execution.getJobInstance().getInstanceId(),
            execution.getId(),
            businessDate,
            status,
            exitCode,
            durationMs,
            readCount,
            writeCount,
            filterCount,
            skipCount
        };

        if (status == BatchStatus.FAILED) {
            log.error(message, fields);
            logFirstFailure(execution);

        } else if (status == BatchStatus.STOPPED ||
                   status == BatchStatus.UNKNOWN) {
            log.warn(message, fields);

        } else {
            log.info(message, fields);
        }
    }

    private void logFirstFailure(JobExecution execution) {
        List<Throwable> errors =
            execution.getAllFailureExceptions();

        if (errors.isEmpty()) {
            return;
        }

        Throwable first = errors.get(0);

        log.error(
            "event=batch.job.failure executionId={} exceptionType={}",
            execution.getId(),
            first.getClass().getName(),
            first
        );
    }
}
```

In this example:

1. `beforeJob` logs an opening event for each execution.
2. `afterJob` retrieves the final status and sums the counts across the `StepExecution`s belonging to that run.
3. Duration is calculated only when both timestamps have values.
4. `FAILED` is logged at `ERROR`; `STOPPED`/`UNKNOWN` at `WARN`; remaining statuses at `INFO`.
5. The example only logs the stack trace of the first error to avoid writing the same error dozens of times when multiple steps have reported exceptions.

The `Object[] fields` array corresponds to the `{}` placeholders in SLF4J. Another logging configuration can switch to JSON with dedicated fields, but what matters most is stable field names and complete correlation details.

**On privacy:** Stack traces can contain exception messages carrying business data. For sensitive data, restrict log access, strip unnecessary content, or log only standardized error codes. Never log raw request bodies, tokens, passwords, or entire input records.

**On counts:** The `readCount`, `writeCount`, and `skipCount` totals above belong to the **current JobExecution**. On restart, earlier executions keep their own counts. The total of a single execution is not necessarily the total number of unique records across the entire JobInstance over multiple restarts, especially when rollbacks and reprocessing occur.

## 6. Registering the Listener in JobBuilder

Declaring `@Component` alone is not enough to guarantee the listener will be used by a specific job. You must register the listener in the `Job` configuration.

Example of a simple tasklet job with a `JobRepository` and transaction manager:

```java
package com.example.batch.config;

import com.example.batch.logging.BatchJobLoggingListener;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class DailyReportJobConfiguration {

    @Bean
    Step dailyReportStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager) {

        return new StepBuilder("dailyReportStep", repository)
            .tasklet((contribution, context) -> {
                // Process the report according to businessDate in JobParameters.
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
    }

    @Bean
    Job dailyReportJob(
            JobRepository repository,
            @Qualifier("dailyReportStep") Step step,
            BatchJobLoggingListener listener) {

        return new JobBuilder("dailyReportJob", repository)
            .start(step)
            .listener(listener)
            .build();
    }
}
```

From then on, every `JobExecution` of `dailyReportJob` executed through Spring Batch invokes the listener at the corresponding lifecycle points.

If a system has multiple jobs sharing the same log format, you can reuse a stateless listener that does not store per-execution state. Avoid storing the current `JobExecution` in a field of a singleton listener, because different jobs or multiple executions can run concurrently.

### Logging Configuration in Spring Boot

Example `application.yml`:

```yaml
spring:
  batch:
    job:
      enabled: false

logging:
  level:
    root: INFO
    com.example.batch.logging: INFO
```

Set `spring.batch.job.enabled=false` if the application wants a scheduler or dedicated entry point to explicitly invoke `JobLauncher`. If the requirement is to run automatically on Spring Boot startup, you can use an appropriate auto-launch mechanism; the listener still works when the job executes.

For production, forward logs to a centralized system capable of searching by `executionId` and `job`. Do not rely solely on local log files inside a container that may be replaced.

## 7. Sample Log Output from JobExecutionListener

Suppose a job has one step, reads 1,000 records, writes 998 records, and skips 2 error records according to the configured policy:

```text
INFO  event=batch.job.started job=dailyReportJob instanceId=321 executionId=1001 businessDate=2026-11-15 status=STARTED

INFO  event=batch.job.finished job=dailyReportJob instanceId=321 executionId=1001 businessDate=2026-11-15 status=COMPLETED exitCode=COMPLETED durationMs=4312 readCount=1000 writeCount=998 filterCount=0 skipCount=2
```

If the job fails in the writer:

```text
INFO  event=batch.job.started job=dailyReportJob instanceId=321 executionId=1002 businessDate=2026-11-15 status=STARTED

ERROR event=batch.job.finished job=dailyReportJob instanceId=321 executionId=1002 businessDate=2026-11-15 status=FAILED exitCode=FAILED durationMs=2830 readCount=600 writeCount=300 filterCount=0 skipCount=0

ERROR event=batch.job.failure executionId=1002 exceptionType=java.lang.IllegalStateException
      ... stack trace ...
```

The numbers above only illustrate the log format. In the case of chunk retry, rollback, or multiple steps, counts must be interpreted alongside specific metadata. Do not infer the final impact on the database solely from `writeCount`: inspect the target data when investigating discrepancies.

## 8. Do Listener Logs Replace Scheduler Logs?

No. Suppose the scheduler calls:

```java
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .toJobParameters();

jobLauncher.run(dailyReportJob, params);
```

If a run for the same `JobInstance` has already completed, the request is rejected, typically with `JobInstanceAlreadyCompleteException`. Because no new execution is created, the listener emits no `batch.job.started` or `batch.job.finished` log lines.

To record every time the scheduler **attempts a launch**, you need a layer calling the launcher with its own logging:

```java
try {
    log.info(
        "event=batch.launch.requested job={} businessDate={}",
        dailyReportJob.getName(),
        businessDate
    );

    JobExecution execution =
        jobLauncher.run(dailyReportJob, parameters);

    log.info(
        "event=batch.launch.accepted job={} executionId={}",
        dailyReportJob.getName(),
        execution.getId()
    );

} catch (JobInstanceAlreadyCompleteException ex) {
    log.info(
        "event=batch.launch.rejected reason=already_completed " +
        "job={} businessDate={}",
        dailyReportJob.getName(),
        businessDate
    );

} catch (JobExecutionAlreadyRunningException ex) {
    log.warn(
        "event=batch.launch.rejected reason=already_running " +
        "job={} businessDate={}",
        dailyReportJob.getName(),
        businessDate
    );
}
```

This snippet assumes `jobLauncher`, `dailyReportJob`, `parameters`, and `businessDate` are already declared in the coordinator class, along with the necessary exception imports.

To accurately audit every attempt—even if the process dies or logs are lost—you may need to persist a separate durable launch-request record. Listener logs provide **execution** information, while launch auditing is a broader requirement.

## 9. Error Logs, Log Levels, and Avoiding Noise

### Log Level Hierarchy

| Level | Example Usage |
| --- | --- |
| `INFO` | Job started, job completed, duration, item totals |
| `WARN` | Intentionally stopped job, unknown status, abnormal record count, duplicate launch request |
| `ERROR` | Job failed, callback encountered an error needing investigation, unhandled exception |
| `DEBUG` | Details of allowed parameters, internal check flow, or temporary diagnostic info |
| `TRACE` | Very detailed trace, enabled only when truly necessary and bounded |

Some systems treat `STOPPED` as a valid status triggered intentionally by an operator, so they may use `INFO` instead of `WARN`. Log levels should fit your operational policy, not a rigid rule from Spring Batch.

### Avoid Per-Item Logging at the Job Level

A job processing one million items can overwhelm the logging system if every record emits an `INFO` line. In `JobExecutionListener`, log aggregated summary events. If you need to observe item-level error details, use `SkipListener`, `ItemReadListener`, or the corresponding step-level listener, combined with rate limiting, sampling, and sensitive-data masking rules.

### Do Not Fail the Job Just Because an Auxiliary Logging System Fails

A job listener should perform fast, simple operations. Standard SLF4J logging does not require opening a direct network connection inside the callback. Avoid synchronous monitoring API calls with long timeouts or writing a complex audit transaction directly inside `afterJob`.

Exceptions thrown in callbacks can affect job completion or complicate metadata persistence, depending on timing and how the framework handles them. Therefore, if a listener calls an external system, control errors, timeouts, and the fail-open/fail-closed policy based on operational needs.

## 10. Logging on Restart

A `JobInstance` can have multiple `JobExecution`s. If a job fails and is restarted with the same identifying parameters, the listener is called for the **new execution**, producing another start/finish log pair.

```text
job=dailyReportJob instanceId=321 executionId=1001 status=FAILED
job=dailyReportJob instanceId=321 executionId=1002 status=COMPLETED
```

This log pair shows that the restart succeeded without creating a different JobInstance. Steps that already completed in the earlier execution may not run again in the subsequent execution unless configured to allow it. Thus, `readCount` of the restart execution can be smaller than the total record count for the entire data period.

When aggregating reports, do not sum `readCount` across all executions and treat it as the number of unique records processed. Items may be re-read due to rollbacks/restarts; use business data information and step statuses to interpret counts properly.

## 11. Thread Issues, MDC, and Asynchronous Launchers

### SLF4J MDC

MDC (Mapped Diagnostic Context) lets you attach keys such as `jobExecutionId` to logs without repeating every field in every log statement.

Example:

```java
import org.slf4j.MDC;

try (MDC.MDCCloseable ignored = MDC.putCloseable(
        "jobExecutionId",
        String.valueOf(execution.getId()))) {

    log.info(
        "event=batch.job.started job={}",
        execution.getJobInstance().getJobName()
    );
}
```

This snippet sets MDC only for the scope of the `try` block; exiting the block removes the newly added MDC entry. This is a safe way for the listener to avoid leaking a correlation ID to another job on a reused thread.

**Important:** MDC is typically bound to a thread. Setting MDC in `beforeJob` and removing it right after the callback **does not automatically give all logs in step/worker threads the same context**. If you need MDC across a multi-threaded job or an async executor, you must propagate the context to the relevant threads or log `jobExecutionId` directly from the execution context at the log site.

When logs require durable correlation, IDs stored in Batch metadata and safe non-identifying parameters are more reliable than relying solely on ThreadLocal.

### Asynchronous Launchers

Some `JobLauncher` configurations run jobs on an asynchronous executor. In that case:

- The scheduler calls `jobLauncher.run(...)` and may receive a JobExecution still in `STARTING` or `STARTED`.
- The listener runs on the job execution thread, not necessarily the scheduler thread.
- Seeing `batch.launch.accepted` does not mean `batch.job.finished` has been logged yet.
- To know the final result, you need the `afterJob` listener, `JobExplorer`, or a metadata observation system.

Do not log `COMPLETED` as soon as the launcher call returns without evidence that the execution has finished.

## 12. Cases Where the Listener Cannot Log

The listener accurately records events when it is invoked, but it does not cover every kind of infrastructure failure:

| Case | JobExecutionListener Logging Capability |
| --- | --- |
| Execution runs and finishes normally | `beforeJob` and `afterJob` are called per normal lifecycle |
| Job fails inside a step | Typically `afterJob` still runs and can log `FAILED` and errors |
| Job rejected because instance is already `COMPLETED` | No new execution is created; no corresponding callbacks |
| Job rejected because another execution is running | No job listener callback for the rejected request |
| Invalid parameters rejected by launcher before running | No guarantee callbacks are invoked |
| JVM/container killed abruptly | No guarantee `afterJob` runs in time |
| Logging backend disconnected or logs dropped | Callback may run, yet logs are still not saved |
| Listener not registered on the job | No listener logs even though the job runs |
| Job not triggered by the scheduler | No execution for the listener to log |

For system-wide monitoring, combine listener logs, launch coordinator logs, `JobRepository` metadata, and checks for **periods due that lack a successful execution**. “Missing on-time result” alerts help detect cases where the scheduler did not run even when there are no `ERROR` logs.

## 13. Testing Logs in JobExecutionListener

You do not need to launch an entire batch job just to verify that the listener formats the expected log lines. You can construct a `JobExecution` in a test and use Spring Boot's `OutputCaptureExtension` to capture output from the logging backend.

JUnit 5 example:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(OutputCaptureExtension.class)
class BatchJobLoggingListenerTest {

    private final BatchJobLoggingListener listener =
        new BatchJobLoggingListener();

    @Test
    void logsJobStartWithBusinessKey(CapturedOutput output) {
        JobInstance instance =
            new JobInstance(42L, "dailyReportJob");

        JobParameters parameters =
            new JobParametersBuilder()
                .addString("businessDate", "2026-11-15", true)
                .toJobParameters();

        JobExecution execution =
            new JobExecution(instance, parameters);

        execution.setStatus(BatchStatus.STARTED);

        listener.beforeJob(execution);

        assertThat(output.getOut())
            .contains("event=batch.job.started")
            .contains("job=dailyReportJob")
            .contains("businessDate=2026-11-15");
    }

    @Test
    void logsCompletedJob(CapturedOutput output) {
        JobInstance instance =
            new JobInstance(43L, "dailyReportJob");

        JobParameters parameters =
            new JobParametersBuilder()
                .addString("businessDate", "2026-11-16", true)
                .toJobParameters();

        JobExecution execution =
            new JobExecution(instance, parameters);

        execution.setStatus(BatchStatus.COMPLETED);

        listener.afterJob(execution);

        assertThat(output.getOut())
            .contains("event=batch.job.finished")
            .contains("status=COMPLETED")
            .contains("readCount=0");
    }
}
```

The test above verifies the log-message construction logic using a mock execution. The logging backend must be configured so console output is captured in the test environment. Having no real repository ID on `JobExecution` in this example is normal because the test does not run through `JobLauncher`.

For integration tests, use `spring-batch-test` to run the job against a test `JobRepository` and verify:

1. The listener is registered on the intended job.
2. A successful run emits one start event and one finish event with `BatchStatus.COMPLETED`.
3. A failed run emits a `FAILED` finish event and appropriate error details.
4. A restart produces logs with a new `jobExecutionId` while preserving `jobInstanceId`.
5. Re-invoking an already completed instance is rejected by the launcher and does **not** create a start log for a new execution.
6. When the job runs asynchronously, the finish status is logged when execution completes rather than immediately when the scheduler submits it.

You can assert both `JobExecution` metadata and the corresponding log lines to confirm observability reflects the actual execution state.

## 14. Designing Logs for Operations and Search

A convenient convention is for each event to consist of `key=value` pairs or JSON fields with stable names. If logs are collected by a system supporting structured logging, store `jobExecutionId` as a dedicated field for querying by ID.

Illustrative JSON example:

```json
{
  "event": "batch.job.finished",
  "job": "dailyReportJob",
  "jobInstanceId": 321,
  "jobExecutionId": 1001,
  "businessDate": "2026-11-15",
  "status": "COMPLETED",
  "exitCode": "COMPLETED",
  "durationMs": 4312,
  "readCount": 1000,
  "writeCount": 998,
  "skipCount": 2
}
```

The goal is **easy correlation and aggregation**; logs are not required to be JSON. If you use a plain-text format, keep field ordering and field names consistent.

Dashboards should track daily job duration, `FAILED` rate, restart counts, read/write/skip counts, and business periods not yet completed before their SLA deadline. Avoid using high-cardinality IDs like `jobExecutionId` as labels on time-series metrics if your monitoring backend cannot handle high cardinality; IDs belong in logs, traces, and metadata.

## 15. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Job runs but no listener logs appear | Forgot `.listener(listener)` in `JobBuilder` | Register the listener on the job |
| Only start log appears, no finish log | Process killed, logging failure, or listener exception | Cross-check JobRepository, container logs, health/infra incidents |
| Scheduler rejected without listener logs | No new JobExecution created | Log launch failures in the coordinator |
| Logged `COMPLETED` before job finished | Confused launcher accepted with job finished in async mode | Log final status from `afterJob` or metadata |
| Cannot distinguish restarts | Only logging job name | Log both `jobInstanceId` and `jobExecutionId` |
| Logs contain tokens or personal data | Printing full `JobParameters`/exceptions | Whitelist, mask/redact sensitive fields |
| Logs multiply to millions of lines | `INFO` logging per item | Use summary logs at job level, selective error logs at item level |
| Wrong MDC across jobs or threads | Forgot to clear MDC or failed to propagate context | Use try-with-resources and controlled context propagation |
| `readCount` differs from final DB record count | Filters, skips, rollbacks, restarts, or business logic | Reconcile step counts with target data |
| Listener causes secondary errors hurting batch status | Calling external systems in callbacks without error handling | Keep callbacks lightweight; retry/monitor out-of-band if needed |
| No job runs seen all day | Scheduler did not trigger, missing permissions, or misconfig | Monitor expected periods and audit launches outside listener |

## 16. Hands-on Exercise

Create a `dailyInventoryJob` with two steps: reading and normalizing inventory, then saving an aggregated summary. Register a `JobExecutionListener` that logs start and finish events with the fields: `job`, `jobInstanceId`, `jobExecutionId`, `businessDate`, `status`, `exitCode`, `durationMs`, `readCount`, `writeCount`, and `skipCount`.

Run four scenarios: the job completes successfully; the data-writing step throws an exception; restart the same data period after the error; the scheduler resubmits an already completed period. Compare the listener logs with JobRepository metadata and coordinator logs. Identify which scenario **has a launch request without listener callbacks** and which scenario has **multiple JobExecutions for the same JobInstance**.

Next, add a non-identifying `correlationId` to the job parameters and include it in logs without exposing sensitive data. If the application uses multiple threads, verify whether MDC propagates to worker threads as designed.

## 17. Summary

`JobExecutionListener` is the right central place to log **the lifecycle of a single job execution**. `beforeJob` provides the start trail; `afterJob` records the final status, duration, counts, and errors. Logs should include a business key, JobInstance ID, and JobExecution ID to distinguish periodic jobs from restarts. Register the listener in `JobBuilder`, keep its logic concise, avoid leaking sensitive data, and never assume every scheduler request creates a JobExecution. Combining listener logs with launch logs and Spring Batch metadata makes monitoring, investigating, and operating batch workloads far more reliable.
