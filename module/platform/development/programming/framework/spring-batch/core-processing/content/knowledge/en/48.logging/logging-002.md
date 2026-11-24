# Logging in Step Listeners in Spring Batch

## 1. Why Log in a Step Listener?

A Spring Batch job typically consists of multiple steps such as reading data, validating conditions, transforming, and writing results. When a job runs on a schedule or operates in a production system, the key question is not merely *did the job run*, but also:

- Which step started, and in which job execution did it start?
- Did the step succeed, fail, or stop? What was the exact exit code?
- How many records were read, written, filtered, or skipped?
- How long did processing take? Were there abnormally many rollbacks/commits?
- Was the same step re-run after an error, or is this a new job instance?
- When a step fails, which execution's logs should be searched for the error?

`StepExecutionListener` is a Spring Batch extension point invoked at **step lifecycle boundaries**. It is the right place to emit events such as `batch.step.started`, `batch.step.finished`, or `batch.step.failed`, along with enough metadata for lookup.

```text
JobLauncher / JobOperator
          |
          v
      JobExecution
          |
          v
    StepExecution
          |
          +--> beforeStep(stepExecution)
          |         |
          |         +--> Log step start
          |
          +--> Reader / Processor / Writer
          |         or Tasklet
          |
          +--> afterStep(stepExecution)
                    |
                    +--> Log status and statistics
```

**Distinction:** `StepExecutionListener` observes **a single step execution**, not individual items. To inspect a read error on a specific row, a write error on a chunk, or why an item was skipped, combine it with `ItemReadListener`, `ItemProcessListener`, `ItemWriteListener`, `SkipListener`, or `ChunkListener`. Stuffing all logs into `StepExecutionListener` loses visibility into where an error originated.

## 2. The `StepExecutionListener` Lifecycle

In Spring Batch 5.x, the interface looks like this:

```java
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class ExampleStepListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        // Called before the step's processing logic starts.
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        // Called after the step's processing logic finishes,
        // including when processing fails under normal lifecycle flow.
        return null;
    }
}
```

Key points to remember:

| Callback | Timing | Loggable Data | Notes |
|---|---|---|---|
| `beforeStep(StepExecution)` | Before the step processes data | Job name, job execution ID, step name, step execution ID, controlled run info | Final counts are not yet available; do not log that the step succeeded. |
| `afterStep(StepExecution)` | After step logic completes or fails in normal execution flow | `BatchStatus`, `ExitStatus`, read/write/filter/skip/commit/rollback counts, duration, error info | This is the right moment to log step results. |

`afterStep` returns an `ExitStatus` so it **can influence the step's exit code**: Spring Batch combines the returned value with the existing `ExitStatus` via `ExitStatus.and(...)`. If the listener **only logs**, `return null;` so you do not inadvertently alter the exit code. Do not blindly return `ExitStatus.COMPLETED`, as it misleads readers about the listener's intent and can affect flow rules depending on how statuses are combined.

Per the Spring Batch 5.x/6.x API, exceptions thrown from `afterStep` are caught/logged by the framework and are **not propagated as an error that fails the step**. Therefore, do not use `afterStep` for mandatory validation that must throw an exception to fail the batch outcome; keep logging logic concise, fault-tolerant, and free of fragile network calls.

`beforeStep` runs on the step startup path. If this callback throws an exception, processing can be aborted; therefore, do not place unnecessary work inside `beforeStep` such as heavy reporting queries, synchronous HTTP calls, or loading millions of records.

**Callback limitation:** When a process is killed, power is lost, the JVM crashes, or the infrastructure terminates abnormally, `afterStep` may never be called. To detect hung jobs or lost heartbeats, also monitor repository state, metrics, and external watchdogs; listener logs are not an absolute guarantee of a completion record.

## 3. What Information Does `StepExecution` Provide?

The `StepExecution` object is the primary data source when logging in a step listener.

| Value | Spring Batch 5.x API | Meaning When Searching Logs |
|---|---|---|
| Job name | `step.getJobExecution().getJobInstance().getJobName()` | Type of job running, e.g. `dailySettlementJob`. |
| Job instance ID | `step.getJobExecution().getJobInstance().getInstanceId()` | Identifies the logical job instance. |
| Job execution ID | `step.getJobExecution().getId()` | Distinguishes runs/restarts of the same instance. |
| Step name | `step.getStepName()` | Identifies the step in the flow. |
| Step execution ID | `step.getId()` | Distinguishes step executions across retries/restarts and partitions. |
| Batch status | `step.getStatus()` | Framework status such as `COMPLETED`, `FAILED`, `STOPPED`. |
| Exit code | `step.getExitStatus().getExitCode()` | Outcome code usable by flow transitions. |
| Read count | `step.getReadCount()` | Number of items reported as read by the reader. |
| Write count | `step.getWriteCount()` | Number of items reported as written by the writer per chunk. |
| Filter count | `step.getFilterCount()` | Number of items filtered out by the processor returning `null`. |
| Skip count | `step.getSkipCount()` | Total skips across read, process, and write phases. |
| Commit count | `step.getCommitCount()` | Number of commits in the step. |
| Rollback count | `step.getRollbackCount()` | Number of rollbacks. |
| Failure exceptions | `step.getFailureExceptions()` | Exceptions recorded by the framework for this step execution. |
| Start/end time | `step.getStartTime()`, `step.getEndTime()` | Compute execution duration when both timestamps are non-null. |

These counters reflect how Spring Batch updates step statistics. `readCount` does not necessarily equal `writeCount`: items may be filtered, skipped, or transformed by processing logic. A **tasklet** executing a multi-row SQL `UPDATE` does not automatically increment `writeCount` by the number of affected SQL rows. Interpret counts according to the actual step type.

`BatchStatus` and `ExitStatus` are two distinct concepts:

```text
BatchStatus = execution status recorded by the framework
ExitStatus  = outcome code used for flow/transitions

Example:
  BatchStatus = COMPLETED
  ExitStatus  = COMPLETED WITH SKIPS
```

Do not use `ExitStatus` as a complete substitute for `BatchStatus` when classifying success/failure. Conversely, if a flow branches on `.on("COMPLETED WITH SKIPS")`, logging only `BatchStatus.COMPLETED` can leave operators puzzled as to why the job took a different branch.

## 4. Practical Example: Listener Logging Step Start and Finish

This example uses **Java 17+, SLF4J, and Spring Batch 5.2.x**. For Spring Boot 3.x projects using standard starters, the SLF4J API and Logback are usually already included, so there is no need to call `System.out.println`.

```java
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public final class StepLoggingListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepLoggingListener.class);

    @Override
    public void beforeStep(StepExecution step) {
        log.info(
                "batch.step.started jobName={} jobExecutionId={} "
                        + "stepName={} stepExecutionId={}",
                jobName(step),
                step.getJobExecution().getId(),
                step.getStepName(),
                step.getId());
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        long durationMs = durationMillis(step);
        BatchStatus status = step.getStatus();
        String exitCode = step.getExitStatus().getExitCode();

        String message =
                "batch.step.finished jobName={} jobExecutionId={} "
                        + "stepName={} stepExecutionId={} status={} exitCode={} "
                        + "read={} written={} filtered={} skipped={} "
                        + "commits={} rollbacks={} durationMs={}";

        Object[] arguments = {
                jobName(step),
                step.getJobExecution().getId(),
                step.getStepName(),
                step.getId(),
                status,
                exitCode,
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getSkipCount(),
                step.getCommitCount(),
                step.getRollbackCount(),
                durationMs
        };

        if (status == BatchStatus.COMPLETED) {
            log.info(message, arguments);
        } else {
            log.warn(message, arguments);
        }

        List<Throwable> failures = step.getFailureExceptions();
        if (!failures.isEmpty()) {
            Throwable firstFailure = failures.get(0);
            log.error(
                    "batch.step.error jobExecutionId={} stepExecutionId={} "
                            + "failureCount={} exceptionType={}",
                    step.getJobExecution().getId(),
                    step.getId(),
                    failures.size(),
                    firstFailure.getClass().getName(),
                    firstFailure);
        }

        return null; // Observe and log only; do not alter ExitStatus.
    }

    private static String jobName(StepExecution step) {
        return step.getJobExecution()
                .getJobInstance()
                .getJobName();
    }

    private static long durationMillis(StepExecution step) {
        LocalDateTime started = step.getStartTime();
        LocalDateTime ended = step.getEndTime();
        return (started != null && ended != null)
                ? Duration.between(started, ended).toMillis()
                : -1L;
    }
}
```

**Design explanation:**

1. `LoggerFactory.getLogger(...)` creates a per-class logger so levels can be configured independently.
2. Uses SLF4J `{}` placeholders instead of repeated string concatenation; formatting happens only if the corresponding log level is enabled.
3. Always logs **job execution ID** and **step execution ID** to locate the exact run. Logging only `jobName`/`stepName` is insufficient because the same step can run multiple times.
4. Uses `INFO` for completed steps, `WARN` for non-normal completion statuses, and `ERROR` when exceptions are recorded in `StepExecution`.
5. Logs only the first exception and the exception count to avoid repeating stack traces excessively in a step with many item failures. This can be adjusted per your system's operational policy.
6. `durationMs = -1` in this example indicates start/end times are not yet available to compute duration, which is common when constructing mock metadata in unit tests. Do not interpret `-1` as an actual duration.
7. `return null` preserves the observation-only purpose and avoids accidentally altering job flow.

`afterStep` may execute **before all final `ExitStatus`/metadata updates are persisted to the repository**, especially when multiple listeners participate. Logs inside this callback are a snapshot of state at callback time; if you need to guarantee the status is persisted and the entire job has finished, inspect `JobExecution`/`JobRepository` at the appropriate boundary.

### 4.1. Sample Log Output

```text
INFO  StepLoggingListener - batch.step.started jobName=dailySettlementJob jobExecutionId=701 stepName=calculateFees stepExecutionId=820
INFO  StepLoggingListener - batch.step.finished jobName=dailySettlementJob jobExecutionId=701 stepName=calculateFees stepExecutionId=820 status=COMPLETED exitCode=COMPLETED read=1200 written=1180 filtered=20 skipped=0 commits=13 rollbacks=0 durationMs=5384
```

If processing encounters an error:

```text
INFO  StepLoggingListener - batch.step.started jobName=dailySettlementJob jobExecutionId=702 stepName=calculateFees stepExecutionId=821
WARN  StepLoggingListener - batch.step.finished jobName=dailySettlementJob jobExecutionId=702 stepName=calculateFees stepExecutionId=821 status=FAILED exitCode=FAILED read=450 written=400 filtered=0 skipped=0 commits=5 rollbacks=1 durationMs=2750
ERROR StepLoggingListener - batch.step.error jobExecutionId=702 stepExecutionId=821 failureCount=1 exceptionType=java.lang.IllegalStateException
```

These are **illustrative logs**; actual numbers depend on chunking, transactions, and real data. In logs for a `TaskletStep` that does not process items in chunks, read/write counters may be 0 even when the tasklet interacts with a database.

## 5. Registering the Listener with a Step

Creating the `StepLoggingListener` class or adding `@Component` **does not automatically guarantee the listener will be invoked**. The listener must be registered in the step configuration (directly or via whatever listener registration mechanism the application uses).

### 5.1. Registering via Java Configuration

`TaskletStep` example in Spring Batch 5.x:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportOrdersStepConfiguration {

    @Bean
    public StepLoggingListener stepLoggingListener() {
        return new StepLoggingListener();
    }

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            StepLoggingListener loggingListener) {

        return new StepBuilder("importOrders", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    // Replace with appropriate business logic.
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .listener(loggingListener)
                .build();
    }
}
```

A similar call can be placed on `SimpleStepBuilder` for a chunk-oriented step:

```java
return new StepBuilder("importOrders", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .listener(loggingListener)
        .build();
```

The second snippet is a **bean configuration body sample**, assuming `Order`, `orderReader`, `orderProcessor`, `orderWriter`, and `loggingListener` already exist with compatible types. `JobRepository` and the transaction manager must be properly configured if the step is actually run.

### 5.2. Using `@BeforeStep` and `@AfterStep` Annotations

Instead of implementing the interface, Spring Batch supports callback annotations:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.annotation.AfterStep;
import org.springframework.batch.core.annotation.BeforeStep;

public class AnnotatedStepLogCallbacks {

    private static final Logger log =
            LoggerFactory.getLogger(AnnotatedStepLogCallbacks.class);

    @BeforeStep
    public void onStart(StepExecution step) {
        log.info("batch.step.started stepName={} executionId={}",
                step.getStepName(), step.getId());
    }

    @AfterStep
    public ExitStatus onFinish(StepExecution step) {
        log.info("batch.step.finished stepName={} status={}",
                step.getStepName(), step.getStatus());
        return null;
    }
}
```

For a class containing annotated callbacks, register the instance on the step using the matching `.listener(...)` overload so the framework discovers the annotations:

```java
AnnotatedStepLogCallbacks callbacks = new AnnotatedStepLogCallbacks();

// When building the Step with the builder:
new StepBuilder("importOrders", jobRepository)
        .tasklet(tasklet, transactionManager)
        .listener(callbacks)
        .build();
```

In projects that need a listener reused across many steps, explicitly implementing `StepExecutionListener` is usually easier to search for and maintain. If a class already holds multiple lifecycle annotations or belongs to a component needing callbacks, annotations can be more convenient. **Do not register the same callback twice** (for example, both via the interface and via another configuration), as this can produce duplicate logs.

## 6. Designing Log Message Structure

A searchable log message typically consists of a **fixed event name** and consistent context fields:

```text
batch.step.started  jobName=... jobExecutionId=... stepName=... stepExecutionId=...
batch.step.finished jobName=... jobExecutionId=... stepName=... stepExecutionId=... status=... exitCode=... read=... written=... durationMs=...
batch.step.error    jobExecutionId=... stepExecutionId=... exceptionType=...
```

Suggested log fields:

| Field | Include? | Reason |
|---|---|---|
| `event`/event name | Yes | Quickly search for start/finish/error logs. |
| `jobName` | Yes | Aggregate by batch type. |
| `jobExecutionId` | Yes | Trace a single job execution. |
| `stepName` | Yes | Identify location in the flow. |
| `stepExecutionId` | Yes | Distinguish retries or partitions. |
| `status`, `exitCode` | Yes in finish log | Explain step status and flow transitions. |
| `read`, `written`, `filtered`, `skipped` | Yes when item/chunk-based | Support data reconciliation. |
| `commits`, `rollbacks` | Yes when transaction tracking matters | Detect abnormal rollbacks/retries. |
| `durationMs` | Recommended | Support performance investigation. |
| `businessDate`/`tenantCode` | Case-by-case | Log only if non-sensitive and permitted to display. |
| Tokens, passwords, customer info | No | Prevent leaking data into logging systems. |

Do not log raw `JobParameters`, raw `ExecutionContext`, item payloads, or full `StepExecution.toString()` by default. These objects can contain sensitive content, credentials, private paths, or excessive data volume. If you want to log a business date, extract **a single approved key** and verify whether that key counts as sensitive data in your system.

### 6.1. INFO, WARN, ERROR, and DEBUG

| Level | When to Use | Example |
|---|---|---|
| `INFO` | A step starts or finishes normally | `batch.step.started`, `status=COMPLETED`. |
| `WARN` | Step did not finish normally, skips increased, or status needs attention | `status=STOPPED`, `status=FAILED` in summary log. |
| `ERROR` | An actual exception/error occurred requiring investigation | `batch.step.error` with controlled exception info. |
| `DEBUG` | Detailed tracing for development or incident analysis | Chunk details, sanitized parameter values. |
| `TRACE` | Very deep tracing, rarely enabled in production | High-frequency info under strict control. |

**Do not log every item at `INFO`** in a job processing millions of records. That pattern generates huge log volume, incurs storage/ingestion costs, and can slow down processing itself. Log summaries in the step listener and add detail only through item/chunk listeners at an appropriate level.

## 7. Configuring Logging in Spring Boot

With Spring Boot 3.x, you can set dedicated log levels for the package containing your listeners:

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: order-batch

logging:
  level:
    root: INFO
    com.example.batch.listener: INFO
    org.springframework.batch: INFO
```

Adjust `com.example.batch.listener` to your actual package. By default, Spring Boot typically logs to the console using Logback when standard starters are present. There is no need to add a new logging dependency if the starter already provides an SLF4J backend.

When deep debugging is needed in tests, enable debug **only in the test profile**:

```yaml
# src/test/resources/application-test.yml
logging:
  level:
    com.example.batch.listener: DEBUG
    org.springframework.batch.core: DEBUG
```

Configure the minimum level sufficient for diagnostics. Enabling `DEBUG` for the entire framework or SQL in production can emit far more data than expected.

### 7.1. Structured Logging

When logs are shipped to a centralized platform such as Elastic Stack, OpenSearch, Loki, or an observability backend, **JSON with fixed fields** is usually much more convenient than parsing plain strings with regex.

On Spring Boot versions that support structured logging natively (such as Boot 3.4+), you can use:

```yaml
logging:
  structured:
    format:
      console: ecs
```

`ecs` stands for Elastic Common Schema format. If your environment uses a custom Logback encoder or backend, configure the matching encoder; the property above does not necessarily apply to every custom appender. When running in containers, writing JSON to stdout usually makes log collection easier than managing local files inside the container.

At the code level, event names and keys should have stable semantics. You can use the SLF4J 2 fluent API to supply key-value pairs when your backend/encoder supports them:

```java
log.atInfo()
        .addKeyValue("event", "batch.step.started")
        .addKeyValue("jobExecutionId", step.getJobExecution().getId())
        .addKeyValue("stepExecutionId", step.getId())
        .log("Step started");
```

This snippet uses **SLF4J 2.x**. Depending on the logging backend version, encoder configuration, and storage system, key-value pairs may appear as JSON fields or inside the message text. Inspect actual logs to verify the desired output format.

## 8. Tracing with MDC (Mapped Diagnostic Context)

In centralized logs, you often want to filter every line belonging to a `jobExecutionId` or `stepExecutionId`. SLF4J `MDC` lets you attach contextual values to the **current thread**; the logging backend can include these values in its pattern or JSON output.

Example of scoping MDC properly to a single callback:

```java
import org.slf4j.MDC;

public void logStepStart(StepExecution step) {
    try (MDC.MDCCloseable jobId = MDC.putCloseable(
                 "jobExecutionId",
                 String.valueOf(step.getJobExecution().getId()));
         MDC.MDCCloseable stepId = MDC.putCloseable(
                 "stepExecutionId",
                 String.valueOf(step.getId()))) {

        log.info("batch.step.started jobName={} stepName={}",
                step.getJobExecution().getJobInstance().getJobName(),
                step.getStepName());
    }
}
```

With Logback pattern logging, you can render MDC keys:

```yaml
logging:
  pattern:
    console: "%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] jobExecutionId=%X{jobExecutionId} stepExecutionId=%X{stepExecutionId} %logger{36} - %msg%n"
```

When the backend supports JSON structured logging, MDC entries can also be included as JSON fields depending on configuration.

**Important warning:** MDC is typically thread-local data. Putting values into MDC in `beforeStep` and clearing them in `afterStep` does not automatically propagate them to threads of a partitioned step, multi-threaded step, or asynchronous processor/writer. That pattern also risks leaking MDC if a callback does not run as expected. `MDC.putCloseable(...)` scopes context to an explicit block. If you need cross-thread correlation, design a dedicated `TaskDecorator`/propagation mechanism and clean up context after each task finishes. Do not assume MDC automatically follows every Spring Batch execution thread.

### 8.1. Choosing the Right Identifiers

- `jobName`/`stepName`: convenient for grouping multiple runs of the same type.
- `jobExecutionId`: identifies a specific job run; restarts generate a new execution.
- `stepExecutionId`: identifies a specific step execution, including partitions or restarts.
- `jobInstanceId`: useful when grouping retries/restarts of the same logical job instance.
- `businessDate` or business key: add only when permitted to log; keep the key explicit and avoid dumping the full parameter map.

One `jobExecutionId` can have multiple step executions; one step name can appear across many job executions. Combining these IDs is a far more reliable way to investigate an execution flow.

## 9. Choosing the Right Listener for Each Event Type

`StepExecutionListener` should focus on the overall picture of the step. Other listeners supply details at finer boundaries:

| Listener | Typical Callbacks | What to Log |
|---|---|---|
| `StepExecutionListener` | `beforeStep`, `afterStep` | Step start/finish, counters, status. |
| `ChunkListener` | `beforeChunk`, `afterChunk`, `afterChunkError` | Per-chunk outcome, commit timing, chunk/transaction errors. |
| `ItemReadListener` | `beforeRead`, `afterRead`, `onReadError` | Issues occurring in the reader. |
| `ItemProcessListener<I,O>` | `beforeProcess`, `afterProcess`, `onProcessError` | Processor transformation/validation errors. |
| `ItemWriteListener<T>` | `beforeWrite`, `afterWrite`, `onWriteError` | Writer data-output errors. |
| `SkipListener<T,S>` | `onSkipInRead`, `onSkipInProcess`, `onSkipInWrite` | Items skipped under the fault-tolerance policy. |
| `JobExecutionListener` | `beforeJob`, `afterJob` | Whole-job lifecycle and cross-step aggregation. |

Example for logging **the count of skipped items at the end of a step** without logging each item:

```java
@Override
public ExitStatus afterStep(StepExecution step) {
    if (step.getSkipCount() > 0) {
        log.warn(
                "batch.step.skipped stepExecutionId={} readSkips={} "
                        + "processSkips={} writeSkips={} totalSkips={}",
                step.getId(),
                step.getReadSkipCount(),
                step.getProcessSkipCount(),
                step.getWriteSkipCount(),
                step.getSkipCount());
    }
    return null;
}
```

This is an **illustrative/alternative callback option**; do not add a second `afterStep` method to the existing `StepLoggingListener` class that already has a method with the same signature. If you want to log skip counters in the class from Section 4, merge this body into the existing `afterStep`. When you need to know which specific record was skipped, use `SkipListener` and log only permitted technical identifiers.

### 9.1. Do Not Over-Infer from Counters

If `readCount=100`, `writeCount=80`, `filterCount=20`, the processor likely filtered 20 items. However, if `skipCount>0` or the writer transforms cardinality, relationships between counters can differ. Do not create a blanket alert like “readCount != writeCount is an error” for every step; understand the reader/processor/writer behavior and the skip/retry policy.

An elevated `rollbackCount` does not automatically mean the job ultimately failed; in a fault-tolerant step, several rollbacks can happen during retries and the step still ends `COMPLETED`. Logging counts alongside status and duration is much more informative than logging counts in isolation.

## 10. Logging Errors and Exceptions Safely

When `StepExecution` already holds `failureExceptions`, a logging listener can record stack traces for investigation. However, avoid three common mistakes:

1. **Logging the same exception repeatedly.** If `ItemReadListener`, `ChunkListener`, a tasklet `catch` block, and `StepExecutionListener` all log the same stack trace at `ERROR`, logs become cluttered with duplicate entries. Agree clearly on which layer logs the full error; other callbacks can log just the error code and IDs.
2. **Putting sensitive data inside exception messages.** SQL exceptions or HTTP exceptions may contain payloads, connection details, or user content. Before enabling stack traces in production, establish masking/redaction rules in the logger/backend.
3. **Hiding errors by catching and returning `COMPLETED`.** If a listener is solely responsible for logging, return `null`. Never silently override a step's `ExitStatus` to suppress failure reporting.

Example of minimal error logging without printing payloads:

```java
List<Throwable> failures = step.getFailureExceptions();
if (!failures.isEmpty()) {
    Throwable cause = failures.get(0);
    log.error("batch.step.error jobExecutionId={} stepExecutionId={} type={}",
            step.getJobExecution().getId(),
            step.getId(),
            cause.getClass().getSimpleName());
}
```

This snippet logs only **the exception type**, without a stack trace. When operations require a stack trace, pass the throwable as the final argument as shown in Section 4, and ensure access to the logging system is properly restricted.

If a batch step must fail because a business check failed, make that decision inside the step processing or design `ExitStatus`/flow transitions explicitly. A logging listener only reflects the state that already occurred; never turn logging into the source of business-logic decisions.

## 11. Logs and Transactions Inside a Step

A chunk-oriented step typically opens a transaction per chunk. When the step listener logs `batch.step.finished`, metadata may show multiple committed and rolled-back transactions. However, **logs and database transactions are two separate systems**:

```text
Chunk 1: write to database -> commit succeeds
Chunk 2: write to database -> rollback

Logs on stdout/appender may already have been written before the rollback.
```

Therefore, the existence of a line saying `INFO: writer processed item 123` does not prove item 123 was committed to the database. Verify `writeCount`, `commitCount`, `rollbackCount`, the final status, and the actual persisted data. If an outcome must publish an event exactly once after commit, use an appropriate mechanism such as a transactional outbox or post-commit event listener instead of relying on log ordering.

Inside `afterStep`, avoid starting a complex transaction to update business data merely to “mark a log”. Business work belongs in proper step processing components so rollbacks and restarts remain consistent.

## 12. Restart, Partitioning, and Parallel Processing

### 12.1. Restarts Create New Logs

When the same `JobInstance` is restarted after a failure, a **new `JobExecution`** is created. A step that needs to re-run also receives a new `StepExecution`, even though `jobName` and `stepName` stay the same.

```text
jobName=dailySettlementJob jobInstanceId=50
  jobExecutionId=701
    stepName=calculateFees stepExecutionId=820 status=FAILED
  jobExecutionId=703
    stepName=calculateFees stepExecutionId=824 status=COMPLETED
```

If you search only by step name, it is very easy to confuse results from the old run with the restart. Logs should always include explicit execution IDs. When tracing restarts across multiple executions, include `jobInstanceId` if your observability policy calls for it.

### 12.2. Partitioned Steps

In partitioning, a manager step splits work across multiple worker step executions. Step names may carry partition suffixes and distinct execution IDs. When logging in each worker:

```text
batch.step.started stepName=loadCustomers:partition0 stepExecutionId=901
batch.step.started stepName=loadCustomers:partition1 stepExecutionId=902
batch.step.finished stepName=loadCustomers:partition0 stepExecutionId=901 status=COMPLETED
batch.step.finished stepName=loadCustomers:partition1 stepExecutionId=902 status=COMPLETED
```

Lines may interleave due to concurrency; this is normal and not a sign of error. Trace by ID/partition key rather than relying on console appearance order. With **remote partitioning**, workers may run on different JVMs or services, so a shared log aggregator/trace ID is needed.

### 12.3. Multi-Threaded Steps

A `StepExecutionListener` may be invoked on the step coordination thread, while the reader/processor/writer execute on worker threads. That is another reason never to store metadata in a mutable instance field of a singleton listener or assume MDC automatically spreads to every thread. Prefer reading metadata from the `StepExecution` passed into the callback. For parallel item callbacks, use an explicit thread/task correlation solution.

### 12.4. Do Not Infer Absolute Ordering from Timestamps

When logs are collected from multiple replicas, threads, or hosts, clock skew and ingestion latency can prevent log line order from reflecting true causal order. Execution IDs and business sequences/events support investigation far better than relying on log timestamps alone.

## 13. Testing Step Logging Listeners

Because `StepExecutionListener` receives metadata objects without needing to launch an entire batch job, you can unit-test log formatting using `MetaDataInstanceFactory` from `spring-batch-test`.

### 13.1. Dependencies

Gradle Groovy example in Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot Starter Test includes `OutputCaptureExtension` to capture stdout/stderr written by console logging in tests. Results depend on actual logger and appender settings: if a test disables the console appender or sets the level higher than `INFO`, adjust assertions/config accordingly.

### 13.2. Unit Test with `OutputCaptureExtension`

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

@ExtendWith(OutputCaptureExtension.class)
class StepLoggingListenerTest {

    private final StepLoggingListener listener = new StepLoggingListener();

    @Test
    void logsStartAndFinishWithExecutionIds(CapturedOutput output) {
        StepExecution step = MetaDataInstanceFactory
                .createStepExecution("importOrders", 901L);
        step.setStatus(BatchStatus.COMPLETED);
        step.setReadCount(10);
        step.setWriteCount(9);
        step.setFilterCount(1);

        listener.beforeStep(step);
        assertNull(listener.afterStep(step));

        assertThat(output.getOut())
                .contains("batch.step.started")
                .contains("batch.step.finished")
                .contains("stepName=importOrders")
                .contains("stepExecutionId=901")
                .contains("read=10")
                .contains("written=9");
    }
}
```

Here `MetaDataInstanceFactory` **only creates mock metadata**. `listener.beforeStep(...)` and `listener.afterStep(...)` are called directly; no real job or reader runs. `assertNull(...)` verifies the listener does not ask to alter the exit code. Unit testing logs verifies event names and ID fields, but does not replace an integration test confirming the listener is properly registered on the real step.

### 13.3. Integration Test: Confirming the Listener Is Invoked During Step Execution

When tests need to confirm Spring Batch invokes the listener via the step configuration, use `@SpringBatchTest`, `@SpringBootTest`, `JobLauncherTestUtils`, and a dedicated test repository database. Core skeleton example:

```java
@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test")
class StepLoggingIntegrationTest {

    @Autowired
    JobLauncherTestUtils launcherTestUtils;

    @Autowired
    @Qualifier("importOrdersJob")
    Job job;

    @Test
    void stepRunsAndListenerIsInvoked() throws Exception {
        launcherTestUtils.setJob(job);

        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16")
                .toJobParameters();

        JobExecution execution = launcherTestUtils.launchJob(params);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        // Add OutputCaptureExtension or a test appender if you need to
        // explicitly assert the batch.step.started/finished events.
    }
}
```

This is an **integration test skeleton**: it assumes an `importOrdersJob` bean, a test datasource, the metadata schema, and the required Java imports already exist. Asserting `COMPLETED` alone does not prove log messages were emitted; to verify end-to-end logging, capture output with `OutputCaptureExtension` or a test appender and assert the expected contents. When running multiple tests with identical identifying parameters against one repository, clean up metadata or isolate the database to avoid `JobInstanceAlreadyCompleteException`.

## 14. Tracing a Run from Logs to Database Metadata

Step listener logs tie directly to the JDBC `JobRepository` metadata tables. For example, a log line shows:

```text
jobExecutionId=701 stepExecutionId=820 status=FAILED
```

In Spring Batch 5.x, you can query:

```sql
SELECT
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.EXIT_CODE,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.ROLLBACK_COUNT,
    je.JOB_EXECUTION_ID,
    ji.JOB_NAME
FROM BATCH_STEP_EXECUTION se
JOIN BATCH_JOB_EXECUTION je
    ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
JOIN BATCH_JOB_INSTANCE ji
    ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE se.STEP_EXECUTION_ID = 820;
```

In production, use prepared statements/bind parameters when accepting execution IDs from requests or scripts. Only **read** metadata for investigation; never directly edit `BATCH_STEP_EXECUTION.STATUS`, `EXIT_CODE`, or `BATCH_*_CONTEXT` to make logs look right. Framework-managed values may be tied to version fields and restart rules.

A systematic troubleshooting workflow:

1. Filter `batch.step.finished` or `batch.step.error` logs by `jobName`, time window, and environment.
2. Grab `jobExecutionId` and `stepExecutionId`, then search for all logs associated with that execution.
3. Review `status`, `exitCode`, `read/write/skip`, `rollbackCount`, `durationMs`, and exception type.
4. Query the corresponding metadata/operational reports if you need to confirm persisted state.
5. Compare against committed output data, and determine whether a restart with the same identifying parameters is needed.

## 15. Common Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| No `beforeStep`/`afterStep` logs | Listener not registered or step did not run | Check `.listener(...)`, job flow, and logging level. |
| `@Component` present but callbacks do not run | Bean was created but not wired to the step | Register the listener on the specific step. |
| Only start log seen, no finish log | JVM/process terminated abnormally, callback not invoked, or log collector dropped data | Inspect repository, application lifecycle, and log infrastructure. |
| Final log shows `COMPLETED` but flow branched elsewhere | Custom `ExitStatus` code or another listener modified exit code | Log both `BatchStatus` and `ExitStatus`; check listener ordering/config. |
| Step fails yet `afterStep` does not propagate an error | Exceptions in `afterStep` are only logged | Perform status-affecting validation in the appropriate place, not inside a logging callback. |
| `readCount` differs from `writeCount` | Filtering/skipping or different item-counting semantics | Inspect the processor and fault-tolerant policy. |
| `writeCount=0` even though SQL updated many rows | Tasklet ran raw SQL without updating batch item counters | Log row count from `JdbcTemplate.update(...)` in the tasklet logic if needed. |
| Duplicate log entries | Same listener registered twice, or multiple listeners logging the same event | Audit listener registration; standardize event names and log levels. |
| Missing `jobExecutionId` in worker thread logs | MDC does not propagate automatically across threads | Attach correlation at the appropriate boundary using a propagation mechanism. |
| Unit test sees no logs even though callback ran | Logger/appender disabled or level too high | Check `logging.level`, console appender, and test capture setup. |
| Logging slows the job down | Excessive per-item logging or slow synchronous I/O appender | Log at step/chunk level, use appropriate log levels, and review the logging pipeline. |
| Logs expose sensitive content | Printing full `JobParameters`, context, payloads, or exception messages | Use a metadata allowlist, masking, and log access controls. |

## 16. Hands-on Practice: Adding Logs to a Multi-Step Job

Suppose `nightlyImportJob` has three steps: `downloadFiles`, `validateRecords`, `saveRecords`.

**Exercise 1 — Add lifecycle logging:**

- Create `StepLoggingListener` implementing `StepExecutionListener`.
- Log `jobName`, `jobExecutionId`, `stepName`, and `stepExecutionId` in `beforeStep`.
- Log status, exit code, read/write/filter/skip, commit/rollback, and duration in `afterStep`.
- Return `null` from `afterStep` so logging does not alter business outcomes.
- Register the listener on all three steps, run the job, and observe the three start/finish log pairs.

**Exercise 2 — Failure scenario:**

- Intentionally make `validateRecords` fail and observe `BatchStatus.FAILED` along with the exception in `StepExecution`.
- Compare `beforeStep`/`afterStep` against `onProcessError` or `onSkipInProcess` events if using a chunk-oriented step.
- Fix the error condition and restart the job with the same identifying parameters; observe the new `jobExecutionId`/`stepExecutionId`.

**Exercise 3 — Diagnosing parallel processing:**

- Give `saveRecords` two partitions or multiple threads (if supported by the application).
- Add correlation IDs to logs and verify that interleaved lines can still be traced by execution ID.
- Try setting MDC inside a `try-with-resources` block and verify that metadata does not automatically appear on other threads without propagation.

**Exercise 4 — Automated log testing:**

- Use `MetaDataInstanceFactory` to create a `StepExecution` with `readCount=100`, `writeCount=95`, `filterCount=5`.
- Use `OutputCaptureExtension` to verify the expected fields are logged and `afterStep` returns `null`.
- Test `BatchStatus.FAILED` with a failure exception, then verify the log level/event name and error details appear in output.

## 17. Practical Guidelines for Real Projects

An effective logging listener typically follows these principles:

1. **Every step execution carries its own ID in logs.** This lets you distinguish initial runs, restarts, and partitions.
2. **Fixed event names and keys.** Search queries and alerts should not depend on prose sentences that change with the author.
3. **Log summary figures at the step level.** Enable per-item logging only during investigation and after accounting for cost.
4. **Do not interfere with flow control.** Logging-only `afterStep` returns `null`; business decisions belong in dedicated listeners/logic with explicit tests.
5. **Log both status and exit code.** They serve different roles when a job uses conditional flows.
6. **Limit emitted data.** Never push secrets, user data, or entire contexts into the logging system.
7. **Treat logs as an observability channel, not a transaction log.** Confirm commits and restarts via the repository, transactions, and actual data.
8. **Account for unexpected failures.** `afterStep` is not guaranteed during a process crash; external monitoring is required.
9. **Test both formatting and wiring when needed.** Unit tests verify log format; integration tests prove the listener is actually attached to the step.

## 18. Official References

- [Spring Batch Reference — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): `StepExecutionListener` interface, `ChunkListener`, `Item*Listener`, and `SkipListener` callbacks.
- [Spring Batch 5.2 — `StepExecutionListener` Javadoc](https://docs.spring.io/spring-batch/docs/5.2.7/api/org/springframework/batch/core/StepExecutionListener.html): `beforeStep`, `afterStep`, returning `null`, and exception handling contract.
- [Spring Batch 6.x — `StepExecutionListener` Javadoc](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/listener/StepExecutionListener.html): package changes in the Spring Batch 6 line.
- [Spring Batch Reference — Controlling Step Flow](https://docs.spring.io/spring-batch/reference/step/controlling-flow.html): the difference between `BatchStatus` and `ExitStatus`.
- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): configuring log levels, Logback, console appenders, and structured logging.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): ways to observe batch activity complementing listener logs.

