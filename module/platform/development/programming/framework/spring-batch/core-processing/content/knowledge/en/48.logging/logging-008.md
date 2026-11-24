# Structured Logging for Batch in Spring Batch Core Processing

When a Spring Batch application runs multiple jobs, steps, and restarts, log lines like `INFO - Finished processing orders` are hard to use during incident investigation. Operators need to know **which job**, **which execution**, **which step**, **what status**, **how many items were processed**, and **which phase failed**. If all details live inside an unstructured prose string, filtering in a log platform depends on how each developer phrased the English or Vietnamese sentence.

**Structured logging** writes each event as a record with stable fields, commonly as **one JSON object per line** (*JSON Lines*). In Spring Batch, this is especially effective because the framework already models execution identity and tracking cleanly: `JobInstance`, `JobExecution`, `StepExecution`, `BatchStatus`, `ExitStatus`, and step counters.

This lesson builds a complete design and implementation of structured batch logging—from configuring JSON output, adding execution context to MDC, logging job/step lifecycle events, and logging skips and errors, to searching, testing, and operating logs safely.

## 1. The Problem with Free-Text Logs

Consider three lines from two different runs:

```text
2026-11-16 01:01:04 INFO  Start importOrders
2026-11-16 01:01:07 ERROR Cannot write item
2026-11-16 01:01:10 INFO  importOrders finished
```

We cannot tell which `JobExecution` owns the write error, which step it was, whether items were retried or skipped, or whether `finished` means `COMPLETED` or `FAILED`. When two executions overlap, searching by `importOrders` mixes both log streams.

A structured record carries fields that a log platform can query directly:

```json
{
  "@timestamp": "2026-11-16T01:01:10.218Z",
  "level": "INFO",
  "service": "order-batch",
  "eventType": "batch.step.finished",
  "message": "Batch step finished",
  "jobName": "importOrders",
  "jobInstanceId": "305",
  "jobExecutionId": "4812",
  "stepName": "writeOrders",
  "stepExecutionId": "9207",
  "batchStatus": "COMPLETED",
  "exitCode": "COMPLETED",
  "readCount": 1000,
  "writeCount": 987,
  "filterCount": 10,
  "skipCount": 3,
  "durationMs": 42500
}
```

This is **illustrative JSON of an application-defined schema**. Default field names such as `@timestamp`, `logger_name`, or `log.level` vary across Logstash, ECS, GELF, and other encoders. Fields like `eventType`, `jobExecutionId`, and `skipCount` are explicitly added by the application via MDC or structured logging APIs; Spring Batch does not emit this entire object automatically on every log statement.

## 2. Logs Must Match Spring Batch's Identity Hierarchy

```text
Job: importOrders
 |
 +-- JobInstance 305 -- identifying params: businessDate=2026-11-15
 |     |
 |     +-- JobExecution 4811: FAILED
 |     |     +-- StepExecution 9206: loadOrders, FAILED
 |     |
 |     +-- JobExecution 4812: COMPLETED (restart)
 |           +-- StepExecution 9207: loadOrders, COMPLETED
 |
 +-- JobInstance 306 -- identifying params: businessDate=2026-11-16
       |
       +-- JobExecution 4813: STARTED
             +-- StepExecution 9208: loadOrders, STARTED
```

| Log Field | Typical Source | Purpose |
| --- | --- | --- |
| `jobName` | `jobExecution.getJobInstance().getJobName()` | Distinguish batch workflows |
| `jobInstanceId` | `jobExecution.getJobInstance().getId()` | Group run attempts of the same logical work |
| `jobExecutionId` | `jobExecution.getId()` | Primary key to find logs for **one exact run** |
| `stepName` | `stepExecution.getStepName()` | Identify the processing stage |
| `stepExecutionId` | `stepExecution.getId()` | Distinguish executions of the same step, including restarts |
| `batchStatus` | `getStatus().name()` | `STARTED`, `COMPLETED`, `FAILED`, `STOPPED`... |
| `exitCode` | `getExitStatus().getExitCode()` | Exit outcome, customizable by Batch flows |
| `businessDate` | Selected `JobParameters` | Business processing period, useful for shift/day lookup |
| `traceId`, `spanId` | Tracing infrastructure when enabled | Correlate logs with distributed traces |

**Do not equate `JobInstance` with `JobExecution`.** One instance can fail and restart successfully, producing two different execution IDs. To answer “which run failed?”, use `jobExecutionId`; to answer “has day X's job completed yet?”, examine the execution chain under the same instance.

`JobRepository` is the authoritative metadata source for execution status and counters. Logs are a stream of **observability and diagnostic events**; they can drop or duplicate in transit to centralized storage and never replace Batch transactional metadata.

## 3. Defining a Stable Log Field Contract

A system operating multiple jobs needs standardized field names and types instead of letting each Java class invent ad-hoc names. Group them cleanly:

| Group | Recommended Fields | Principles |
| --- | --- | --- |
| Time | `@timestamp`, `durationMs` | ISO-8601 timestamp with timezone/UTC; duration in milliseconds |
| Origin | `service`, `environment`, `logger`, `thread`, `serviceVersion` | Use stable names; never put item IDs in origin tags |
| Classification | `eventType`, `level`, `message` | `eventType` is machine-readable; message is for humans |
| Job | `jobName`, `jobInstanceId`, `jobExecutionId` | Always attach IDs once metadata exists |
| Step | `stepName`, `stepExecutionId` | Attach to logs emitted inside a step |
| Outcome | `batchStatus`, `exitCode`, `errorType`, `errorCode` | Distinguish errors from final outcomes |
| Counters | `readCount`, `writeCount`, `filterCount`, `skipCount`, `rollbackCount` | Numeric types in JSON when emitting summaries |
| Business | `businessDate`, `sourceType`, `fileLogicalName` | Include only values approved for logging |
| Tracing | `traceId`, `spanId`, `correlationId` | Include when distributed tracing and upstream systems exist |

Use a fixed catalog of event names, for example:

```text
batch.job.started
batch.job.finished
batch.step.started
batch.step.finished
batch.item.skipped
batch.chunk.rollback
batch.execution.failed
batch.execution.recovery-requested
```

Practical rules:

1. **Stable field names:** never alternate between `jobId` and `jobExecution` for the same ID. Pick public names and use them consistently across modules.
2. **Consistent types:** `durationMs` and counters are numbers; `jobExecutionId` may be number or string, but stay consistent across schema and queries. SLF4J MDC stores strings, while `addKeyValue(...)` preserves numeric types when supported by the encoder.
3. **Explicit timezones:** log timestamps in UTC or ISO-8601 with offset. `businessDate` is a logical period, not necessarily the wall-clock date when logs were emitted.
4. **Prose-independent events:** dashboards should query `eventType=batch.step.finished`, not regex-match `Finished` in `message`.
5. **Version the schema when needed:** if breaking changes occur, add `schemaVersion` or apply ingestion-time mapping transforms.
6. **Avoid sensitive data:** specify explicitly which fields are permitted; never dump full `JobParameters`, `ExecutionContext`, or items.

## 4. Enabling JSON Logging with Spring Boot 3.4+

Starting in **Spring Boot 3.4**, structured logging is supported out of the box with **ECS**, **GELF**, and **Logstash** formats. When using Spring Boot's default logging setup, enable Logstash JSON via:

```yaml
spring:
  application:
    name: order-batch

logging:
  structured:
    format:
      console: logstash
```

Every emitted logger event is then formatted as JSON instead of a plain-text pattern. Use `ecs` if your organization standardizes on Elastic Common Schema, or `gelf` for GELF-compatible backends. Fields in **SLF4J MDC** and key-value pairs from the **SLF4J 2 fluent API** are included in JSON by Spring Boot's structured logging encoders.

To write JSON to an application-managed file:

```yaml
logging:
  file:
    name: logs/order-batch.jsonl
  structured:
    format:
      file: logstash
```

This is an **alternative or complement** to console output depending on environment. In Kubernetes or containers, writing one JSON event per line to **stdout** for log-agent collection is common; if writing to both console and file, configure ingestion to avoid duplicate indexing.

**Version limitation:** Spring Boot 3.3 and earlier lack full support for the `logging.structured.format.*` properties above. On older Boot versions or plain Spring Framework, configure a JSON encoder in Logback/Log4j2. If a custom `logback-spring.xml` is already present, Boot will not automatically replace its encoder; declare a compatible encoder there or switch back to Boot-managed logging config.

### Logback Encoder Option for Older Boot Projects

For Logback applications, `net.logstash.logback:logstash-logback-encoder` provides `LogstashEncoder`. Pick a version compatible with your Logback/Java versions and configure:

```xml
<!-- src/main/resources/logback-spring.xml -->
<configuration>
    <appender name="JSON_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="JSON_CONSOLE"/>
    </root>
</configuration>
```

This illustrates an **alternative configuration** when Boot lacks built-in structured logging. Pin a compatible encoder dependency version and avoid having multiple appenders ship the same event to the same ingest pipeline. Both built-in JSON encoders and `LogstashEncoder` only handle formatting; fields like `jobExecutionId` must still be supplied by the application.

## 5. Adding Context with SLF4J MDC

`MDC` (*Mapped Diagnostic Context*) is a key-value map attached to the **logging thread**'s context. Putting `jobExecutionId` into MDC lets loggers invoked on that thread attach the ID to every event without passing it through every reader, processor, and writer method.

Short example:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class MdcExample {
    private static final Logger log =
            LoggerFactory.getLogger(MdcExample.class);

    public void runWithContext(long jobExecutionId) {
        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("jobExecutionId",
                             Long.toString(jobExecutionId))) {
            log.info("Reading first input page");
            log.info("Reading second input page");
        }
        // putCloseable removes the key on close.
    }
}
```

Logs inside the block receive `jobExecutionId` if the encoder is configured to include MDC. `putCloseable` works well when log scope fits a single block. With multiple keys needing to preserve prior MDC values, copy the map, put keys, and **restore the old map in `finally`**.

Especially with thread pools, always clear MDC after each unit of work. Forgetting to do so lets a thread that handled `JobExecution 4811` be reused for `4812` while still carrying the stale ID—a serious correlation bug.

### Structured Fields for a Single Event

MDC fits values repeated across many log statements on the same thread. Numbers specific to a single summary event can go directly into the log call via the **SLF4J 2 fluent logging API**:

```java
log.atInfo()
   .addKeyValue("eventType", "batch.step.finished")
   .addKeyValue("readCount", step.getReadCount())
   .addKeyValue("writeCount", step.getWriteCount())
   .addKeyValue("filterCount", step.getFilterCount())
   .addKeyValue("skipCount", step.getSkipCount())
   .log("Batch step finished");
```

When the encoder supports key-value pairs, this keeps counters as **numbers** in JSON. How key-value pairs appear depends on the logging backend/encoder; with an unsupported plain-text pattern, those fields may not render as desired.

## 6. Logging Job Lifecycle Events via `JobExecutionListener`

`JobExecutionListener` runs before a job starts executing and after it completes or fails. It is the ideal place to emit **one start event and one finish event** per `JobExecution`.

Example for **Spring Batch 5.2.x, SLF4J 2, and Java 17**:

```java
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class JobEventLoggingListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(JobEventLoggingListener.class);

    @Override
    public void beforeJob(JobExecution execution) {
        withJobMdc(execution, () ->
                log.atInfo()
                   .addKeyValue("eventType", "batch.job.started")
                   .addKeyValue("batchStatus",
                           execution.getStatus().name())
                   .log("Batch job started"));
    }

    @Override
    public void afterJob(JobExecution execution) {
        withJobMdc(execution, () ->
                log.atInfo()
                   .addKeyValue("eventType", "batch.job.finished")
                   .addKeyValue("batchStatus",
                           execution.getStatus().name())
                   .addKeyValue("exitCode",
                           execution.getExitStatus().getExitCode())
                   .log("Batch job finished"));
    }

    private static void withJobMdc(
            JobExecution execution, Runnable logAction) {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            MDC.put("jobName",
                    execution.getJobInstance().getJobName());
            MDC.put("jobInstanceId",
                    String.valueOf(execution.getJobInstance().getId()));
            MDC.put("jobExecutionId",
                    String.valueOf(execution.getId()));
            logAction.run();
        } finally {
            // Preserve caller's MDC even if logAction fails.
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    }
}
```

These two callbacks open MDC **only while logging lifecycle events**, avoiding any assumption that the entire job always runs on a single thread. Even when reused concurrently across parallel executions, the listener keeps no `JobExecution` in shared mutable fields.

`afterJob` is invoked for both successful and failed executions per the listener contract. `batch.job.finished` means **the finish callback ran**; inspect `batchStatus` and `exitCode` to determine the outcome rather than assuming every `finished` means `COMPLETED`. To emit `ERROR` logs for failures, emit a separate `batch.execution.failed` event with sanitized exception details.

## 7. Attaching MDC During Step Processing

For a **synchronous single-threaded chunk-oriented step**, `StepExecutionListener.beforeStep` can set MDC keys before reader/processor/writer run; `afterStep` logs counters and removes the keys.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class StepEventLoggingListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepEventLoggingListener.class);

    @Override
    public void beforeStep(StepExecution step) {
        MDC.put("jobName",
                step.getJobExecution().getJobInstance().getJobName());
        MDC.put("jobInstanceId", String.valueOf(
                step.getJobExecution().getJobInstance().getId()));
        MDC.put("jobExecutionId", String.valueOf(
                step.getJobExecution().getId()));
        MDC.put("stepName", step.getStepName());
        MDC.put("stepExecutionId", String.valueOf(step.getId()));

        log.atInfo()
           .addKeyValue("eventType", "batch.step.started")
           .log("Batch step started");
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        try {
            log.atInfo()
               .addKeyValue("eventType", "batch.step.finished")
               .addKeyValue("batchStatus", step.getStatus().name())
               .addKeyValue("exitCode",
                       step.getExitStatus().getExitCode())
               .addKeyValue("readCount", step.getReadCount())
               .addKeyValue("writeCount", step.getWriteCount())
               .addKeyValue("filterCount", step.getFilterCount())
               .addKeyValue("readSkipCount", step.getReadSkipCount())
               .addKeyValue("processSkipCount",
                       step.getProcessSkipCount())
               .addKeyValue("writeSkipCount", step.getWriteSkipCount())
               .addKeyValue("skipCount", step.getSkipCount())
               .addKeyValue("commitCount", step.getCommitCount())
               .addKeyValue("rollbackCount", step.getRollbackCount())
               .log("Batch step finished");
        } finally {
            MDC.remove("stepExecutionId");
            MDC.remove("stepName");
            MDC.remove("jobExecutionId");
            MDC.remove("jobInstanceId");
            MDC.remove("jobName");
        }
        return null; // Do not modify the ExitStatus determined by Spring Batch.
    }
}
```

This listener example assumes **batch-dedicated MDC keys have no prior values**, and `beforeStep`/`afterStep` execute on the same thread in a synchronous step model. If your application nests MDC scopes on the same thread, wrap each segment with a snapshot/restore of the prior map instead of removing keys; for parallel/partitioned steps, handle **thread-local propagation** as shown in Section 10.

At `afterStep` time, `readCount`, `writeCount`, `filterCount`, and the `skipCount` breakdowns reflect the summary Spring Batch has accumulated for the step. They are far more reliable than incrementing custom counters whenever a logger emits a message. `StepExecutionListener.afterStep` may return an `ExitStatus` to influence exit codes; returning `null` preserves the existing result.

### Registering Listeners in `JobBuilder` and `StepBuilder`

In Spring Batch 5.x configuration, attach listeners directly to the builders:

```java
@Bean
Job importOrdersJob(JobRepository repository, Step importOrdersStep) {
    return new JobBuilder("importOrders", repository)
            .listener(new JobEventLoggingListener())
            .start(importOrdersStep)
            .build();
}

@Bean
Step importOrdersStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, ProcessedOrder> processor,
        ItemWriter<ProcessedOrder> writer) {

    return new StepBuilder("importOrdersStep", repository)
            .<Order, ProcessedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(new StepEventLoggingListener())
            .build();
}
```

This snippet is excerpted from a `@Configuration` class; `Order`/`ProcessedOrder` types and reader/processor/writer beans must be defined by the application. Core imports belong to `org.springframework.batch.core.job.builder.JobBuilder`, `org.springframework.batch.core.step.builder.StepBuilder`, `org.springframework.batch.core.repository.JobRepository`, and `org.springframework.transaction.PlatformTransactionManager`.

Each step does not require a unique listener class; a **stateless** listener can be reused across steps. Just wire job and step listeners cleanly per your project's Spring Batch conventions to avoid emitting duplicate lifecycle events.

## 8. Logging Filter, Skip, Retry, and Failure Accurately

In Spring Batch, distinguish carefully:

- **Filter:** `ItemProcessor.process(item)` returns `null`, meaning the item is excluded by business rules. The framework increments `filterCount`; this is not an error.
- **Skip:** an exception during read/process/write is accepted by the `skipPolicy`, incrementing `readSkipCount`, `processSkipCount`, or `writeSkipCount`.
- **Retry:** an exception triggers a retry; if a subsequent attempt succeeds, the item is **not skipped** just because an exception occurred earlier.
- **Failure:** an unhandled exception transitions `StepExecution` and `JobExecution` to `FAILED`.

Do not emit `batch.item.skipped` from `ItemReadListener.onReadError` or `ItemWriteListener.onWriteError`: error callbacks can fire repeatedly during retries/rollbacks, whereas skips are only finalized after the framework applies its skip policy.

### Logging Skips with `SkipListener`

`SkipListener` provides dedicated callbacks for items genuinely skipped. Simple example for a `String`-input/output pipeline:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class SkipEventLoggingListener
        implements SkipListener<String, String> {

    private static final Logger log =
            LoggerFactory.getLogger(SkipEventLoggingListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        report("read", error);
    }

    @Override
    public void onSkipInProcess(String item, Throwable error) {
        report("process", error);
    }

    @Override
    public void onSkipInWrite(String item, Throwable error) {
        report("write", error);
    }

    private void report(String phase, Throwable error) {
        log.atWarn()
           .addKeyValue("eventType", "batch.item.skipped")
           .addKeyValue("phase", phase)
           .addKeyValue("errorType",
                   error.getClass().getSimpleName())
           .log("Batch item skipped");
    }
}
```

Register this listener on a step builder with `faultTolerant()` and an appropriate skip policy, e.g.:

```java
.faultTolerant()
.skip(InvalidRecordException.class)
.skipLimit(20)
.listener(new SkipEventLoggingListener())
```

`InvalidRecordException` is an application-defined exception class. **Never log the raw item** or `error.getMessage()` when they might hold personal data, tokens, or sensitive file contents. If item traceability is required for data remediation, use an approved record ID (or policy-compliant secure hash) alongside lookups in the source system.

In the step summary, emit `readCount`, `writeCount`, `filterCount`, all three skip breakdowns, and `skipCount`. The identity `skipCount = readSkipCount + processSkipCount + writeSkipCount` defines step-level total skips; **never add `filterCount` to `skipCount`**. Per-item skip logs help diagnose causes, while `StepExecution` counters reflect the authoritative execution outcome.

### When Stack Traces Are Needed

For an exception that fails a step, emit at least one `ERROR` log carrying the stack trace and execution IDs for investigation:

```java
if (step.getStatus() == BatchStatus.FAILED
        && !step.getFailureExceptions().isEmpty()) {
    Throwable cause = step.getFailureExceptions().get(0);
    log.atError()
       .addKeyValue("eventType", "batch.execution.failed")
       .addKeyValue("errorType", cause.getClass().getSimpleName())
       .setCause(cause)
       .log("Batch step failed");
}
```

This block can run inside `afterStep` **before clearing MDC**, importing `org.springframework.batch.core.BatchStatus`. Avoid logging the exact same stack trace repeatedly across reader, writer, retry listener, and job listener. In production, designate one primary place for detailed errors while other callbacks record only error codes and correlation IDs. Stack traces can also reveal SQL queries or input data; enforce retention and redaction policies accordingly.

## 9. Example JSON Log Stream of a Run

Suppose `importOrders` with `jobExecutionId=4812` has step `loadOrders` read 500 items, filter 10, skip 2 in process, and write 488 items. Below are **illustrative events** in JSON Lines matching the chosen application schema:

```jsonl
{"@timestamp":"2026-11-16T01:00:00Z","level":"INFO","eventType":"batch.job.started","jobName":"importOrders","jobInstanceId":"305","jobExecutionId":"4812","message":"Batch job started"}
{"@timestamp":"2026-11-16T01:00:01Z","level":"INFO","eventType":"batch.step.started","jobName":"importOrders","jobInstanceId":"305","jobExecutionId":"4812","stepName":"loadOrders","stepExecutionId":"9207","message":"Batch step started"}
{"@timestamp":"2026-11-16T01:00:05Z","level":"WARN","eventType":"batch.item.skipped","jobExecutionId":"4812","stepName":"loadOrders","stepExecutionId":"9207","phase":"process","errorType":"InvalidRecordException","message":"Batch item skipped"}
{"@timestamp":"2026-11-16T01:00:45Z","level":"INFO","eventType":"batch.step.finished","jobExecutionId":"4812","stepName":"loadOrders","stepExecutionId":"9207","batchStatus":"COMPLETED","readCount":500,"writeCount":488,"filterCount":10,"processSkipCount":2,"skipCount":2,"message":"Batch step finished"}
{"@timestamp":"2026-11-16T01:00:46Z","level":"INFO","eventType":"batch.job.finished","jobName":"importOrders","jobInstanceId":"305","jobExecutionId":"4812","batchStatus":"COMPLETED","exitCode":"COMPLETED","message":"Batch job finished"}
```

Using `jobExecutionId=4812`, an operator can filter the full event chain, spot the failing step and skip reason, and verify current status in `JobRepository`. To confirm **every valid business record actually persisted**, still reconcile target data and filter/skip rules; a `COMPLETED` log alone does not prove data quality.

## 10. MDC in Multi-Threaded, Partitioned, and Async Batch Jobs

**MDC is typically thread-local.** When a job delegates work to a thread pool or worker process, `jobExecutionId`/`stepExecutionId` keys may not follow automatically. Key scenarios:

| Execution Model | Correlation Challenge | Approach |
| --- | --- | --- |
| Synchronous chunk step | Reader/processor/writer usually run on the step thread | `StepExecutionListener` sets/clears MDC per step lifecycle |
| Multi-threaded step with `TaskExecutor` | Worker threads do not inherit controlling thread's MDC automatically | Copy MDC into tasks and restore after each task |
| Partitioned step | Each partition has its own `StepExecution`/step name | Attach **the partition worker's** ID, not just the manager's ID |
| `AsyncItemProcessor`/`AsyncItemWriter` | Processing hops threads | Propagate correlation context deliberately; never assume MDC follows automatically |
| Remote partitioning/chunking | Runs on another JVM/process | Pass safe correlation fields in message headers/payload; rebuild MDC on worker |
| Outbound HTTP/API calls | Traces span distributed services | Use tracing propagation and attach `traceId`/`spanId` when available |

### Example Propagating MDC with `TaskDecorator`

In Spring Framework, a `TaskDecorator` captures MDC at task submission time, applies it on the executing thread, and restores the prior context afterwards:

```java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public class MdcCopyTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable delegate) {
        Map<String, String> submittingThreadContext =
                MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> workerThreadContext =
                    MDC.getCopyOfContextMap();
            try {
                if (submittingThreadContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(submittingThreadContext);
                }
                delegate.run();
            } finally {
                if (workerThreadContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(workerThreadContext);
                }
            }
        };
    }
}
```

Example configuration:

```java
@Bean
ThreadPoolTaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setThreadNamePrefix("batch-worker-");
    executor.setTaskDecorator(new MdcCopyTaskDecorator());
    executor.initialize();
    return executor;
}
```

This snippet assumes Spring's `ThreadPoolTaskExecutor` with `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor`. If a Batch step uses another executor, configure decoration on that specific executor. Copying MDC only handles **log fields**; it does not propagate Spring Batch `StepScope`/`JobScope`, transactions, or security contexts.

In a partitioned step, do not keep the partition master's `stepExecutionId` when a worker runs its own step execution with a distinct ID. When the worker starts, populate MDC from the **worker's `StepExecution`**. With queues/remote workers, set and clear MDC at the start/end of message handling to prevent context leaks across tasks.

## 11. Structured Logs, Tracing, and Micrometer: Distinct Roles

Three observability pillars work best side by side:

```text
JobRepository / JobExplorer
    -> JobExecution, StepExecution, BatchStatus, counters

Structured logs
    -> events, exceptions, correlation, investigation details

Metrics / tracing
    -> duration, throughput, active jobs, dependency latency
```

Spring Batch includes Micrometer-based observability/metrics in supported versions, with timers such as `spring.batch.job`, `spring.batch.step`, `spring.batch.item.read`, `spring.batch.item.process`, and `spring.batch.chunk.write`. These timers measure execution durations; **timer sample counts do not equal `StepExecution`'s `writeCount` or `skipCount`**.

Tracing can automatically inject `traceId`/`spanId` into logs via Spring Boot/Micrometer Tracing when configured. Preserve **both** trace IDs and batch IDs: a single `JobExecution` can span multiple traces or invoke multiple services, whereas trace IDs do not stay constant across restarts.

For a given run:

- Open `jobExecutionId` in the Batch dashboard to inspect job, step, status, and counters.
- Filter logs by `jobExecutionId`, then search for `ERROR` or `eventType=batch.item.skipped` to diagnose.
- Use `traceId`/`spanId` on logs to find slow database/API/queue calls.
- Use metrics to compare current period latency against historical baselines.

Never treat the logging system as the sole source of truth for committed item counts. Logs can lag during ingestion, get sampled, drop on process crashes, or duplicate on shipper retries; `JobRepository` remains the core execution record.

## 12. Searching and Aggregating Logs in Operational Tools

Once `jobExecutionId` is a dedicated JSON field, operators no longer rely on substring searches over prose. Illustrative query in Lucene/Kibana syntax:

```text
jobExecutionId:"4812" AND level:"ERROR"
```

Finding skips by step:

```text
jobName:"importOrders" AND stepName:"loadOrders"
AND eventType:"batch.item.skipped"
```

For Loki, keep low-cardinality stream labels like `service`/`environment` and parse JSON fields at query time:

```logql
{service="order-batch", environment="production"}
| json
| jobExecutionId="4812"
```

If JSON Lines logs are exported to a file for offline investigation, filter with `jq`:

```bash
jq -c 'select(.jobExecutionId == "4812" and .eventType == "batch.step.finished")' batch.jsonl
```

Query syntax depends on your log platform's mappings/indexes. Normalize field types during ingestion so one node does not emit `jobExecutionId` as a string while another emits a number. `jobExecutionId` has high cardinality; **do not make it a Prometheus label or Loki stream label** when running many executions. Keep the ID inside the event body and filter on parsed fields when querying.

### Questions Dashboards Can Answer

| Goal | Filter / Grouping |
| --- | --- |
| Find all logs of a single run | `jobExecutionId` |
| Find root cause of a failed step | `stepExecutionId`, `level=ERROR`, `errorType` |
| Spot abnormal spikes in a skip type | `eventType=batch.item.skipped`, grouped by `phase`/`errorType` |
| Confirm step completion and counts | `eventType=batch.step.finished`, cross-check `StepExecution` |
| Check restarts for a business period | `jobInstanceId`, comparing distinct `jobExecutionId`s |
| Track errors across deploy versions | `serviceVersion`, `environment`, `eventType` |

Counting `batch.item.skipped` log records helps spot trends, yet always reconcile with `StepExecution.skipCount`. Due to log replays, dropped events, or differing retention, the two counts do not always match.

## 13. Reliability and Cost of the Log Pipeline

Structured JSON is machine-friendly, yet does not automatically guarantee durable delivery. A typical pipeline looks like:

```text
Spring Batch process
   -> stdout / JSON appender
   -> container runtime or log file
   -> collector / forwarder
   -> queue / log storage / index
   -> search UI / alerting
```

Design principles:

1. **One JSON object per line:** stack traces must be escaped inside a JSON field; never emit unescaped multi-line strings that shatter log events.
2. **Avoid logging every successful item:** for 10 million items, `INFO` per item burns I/O, CPU, and index storage while slowing down the batch. Log at job/step boundaries, warning thresholds, and controlled progress intervals.
3. **Log errors judiciously:** skips can happen thousands of times; bound detailed logs while keeping official counts in metadata. If sampling is enabled, disclose clearly that logs do not represent every individual item.
4. **Define retention:** keep lifecycle summaries long enough for audits/investigations, while detailed technical logs can have shorter retention per system requirements.
5. **Manage backpressure:** if the logger/collector slows down, the batch itself must not stall for minutes on non-critical log events. With async appenders, understand the queue-full drop policy.
6. **Monitor the log pipeline itself:** dropped events, shipping errors, queue depth, and post-deploy searchability all matter. Never treat “the app is still running” as proof logs reached storage.
7. **Prevent duplicate shipping:** if an agent collects console logs, do not simultaneously configure an appender pushing the same events to the same store without deduplication.

### Periodic Progress Metrics

For jobs running for hours, emitting only `batch.step.started` and `batch.step.finished` creates long silent windows. You can emit `batch.step.progress` every N chunks or at a fixed interval with `readCount`, `writeCount`, `commitCount`, and timestamp. This is an application-added feature via listeners or monitoring services, not an automatic Spring Batch JSON event.

**Do not assume a job is hung just because no new log arrived**: a chunk may take a long time or wait on I/O. Combine process liveness, metadata timestamps, active metrics, transactions, and step behavior.

## 14. Data-Protection Rules in Structured Logs

Moving from plain text to well-structured JSON makes querying easier, yet also makes data leaks worse if raw objects are logged. Common sensitive sources in batch jobs include:

- `JobParameters` containing API tokens, passwords, internal paths, user IDs, customer codes, account numbers, or access keys.
- `ExecutionContext` containing checkpoints, scratch data, serialized objects, and business values.
- Items read from files, databases, queues, or partner requests.
- Exception messages embedding SQL statements, table names, input data, or external payloads.
- Headers/message contexts passed across remote processing systems.

Instead of:

```java
log.info("Job parameters: {}", jobExecution.getJobParameters());
log.error("Could not process record {}", item, exception);
```

log only approved fields:

```java
log.atInfo()
   .addKeyValue("eventType", "batch.input.selected")
   .addKeyValue("jobName",
           jobExecution.getJobInstance().getJobName())
   .addKeyValue("inputKind", "daily-order-file")
   .addKeyValue("businessDate", "2026-11-15")
   .log("Selected batch input");
```

`businessDate` is an illustrative safe business field here; in practice, pull it from validated parameters approved for logging. For customer/item IDs, log them only if policy permits; use a PII-free internal identifier or tokenize before logging. **Never treat a plain hash as guaranteed anonymization**, especially when the value domain is small or guessable.

Enforce environment-based log access controls, retention and deletion policies, export governance, and redaction in **both the application and the ingestion pipeline** when required. Never rely on the UI hiding a field while raw data sits in the backend log store.

## 15. Testing Structured Logs and MDC

You can test correlation context setup without launching an entire job. The example below tests `StepEventLoggingListener` using mock metadata from `spring-batch-test` and JUnit Jupiter:

```java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

import static org.junit.jupiter.api.Assertions.*;

class StepEventLoggingListenerTest {

    @AfterEach
    void clearMdc() {
        MDC.clear();
    }

    @Test
    void addsAndRemovesStepCorrelationFields() {
        StepExecution execution =
                MetaDataInstanceFactory.createStepExecution();
        StepEventLoggingListener listener =
                new StepEventLoggingListener();

        listener.beforeStep(execution);
        try {
            assertEquals(execution.getStepName(),
                    MDC.get("stepName"));
            assertEquals(String.valueOf(execution.getId()),
                    MDC.get("stepExecutionId"));
            assertEquals(String.valueOf(
                    execution.getJobExecution().getId()),
                    MDC.get("jobExecutionId"));
        } finally {
            listener.afterStep(execution);
        }

        assertNull(MDC.get("stepExecutionId"));
        assertNull(MDC.get("jobExecutionId"));
    }
}
```

This test verifies **setting and clearing MDC on the same thread**. To confirm the emitted JSON actually carries `eventType` and numeric counters, add a logger/encoder integration test or capture log output and parse it as JSON. Scenarios worth testing:

| Scenario | Expectation |
| --- | --- |
| Job start/finish | Both `batch.job.started` and `batch.job.finished` share `jobExecutionId` |
| Two executions of the same instance | **Two** distinct `jobExecutionId`s with the same `jobInstanceId` |
| Step finishes after filter/skip | JSON summary counters match `StepExecution` |
| Retry followed by success | Not mislogged as a final skip |
| Thread pool reuses threads | Later job logs never inherit previous job IDs |
| Workers running different partitions | `stepExecutionId` reflects the executing worker's ID |
| Exception contains sensitive data | Data is stripped/redacted from emitted events |
| Encoder/collector failure | Operational signal alerts on dropped logs or failed ingestion |

When testing the full JSON encoder, avoid exact full-line string comparisons because timestamps, thread names, and key order can vary. Parse the JSON and assert **meaningful fields**, especially `eventType`, correlation IDs, statuses, and counters.

## 16. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Logs are JSON, yet lack `jobExecutionId` | ID not placed in MDC/key-value, or encoder ignores MDC | Set correlation fields in listeners and inspect actual JSON |
| Logs of two jobs mix IDs | Stale MDC left on reused pool thread | Clean/restore MDC in `finally` or callback scope |
| `ItemProcessor` logs lack step ID | Processor runs on another worker thread | Configure executor propagation or set context on workers |
| Partition logs carry manager step ID | Copied manager MDC to all workers | Re-apply each partition worker's own `StepExecution` ID |
| `COMPLETED` run has `ERROR` logs | An error was successfully retried/skipped | Check `BatchStatus`, counters, and skip policy; distinguish transient errors from final failures |
| Skip log count differs from `skipCount` | Logs sampled, dropped, replayed, or error callbacks mistaken for skips | Treat `StepExecution` as primary counter source |
| Numeric fields indexed as strings | All numbers placed in MDC (strings), inconsistent mapping | Use typed `addKeyValue` for summaries; standardize ingest mapping |
| Only message appears; key-values missing | Pattern/encoder does not support fluent key-value pairs | Enable structured encoder or add matching provider |
| Same event logged twice | Both console and file/collector ingest to one destination | Audit appenders and collection pipeline |
| Structured logging inactive with `logback-spring.xml` | Custom file uses PatternLayout instead of a JSON encoder | Configure a structured encoder inside custom Logback |
| Sudden spike in log volume | Per-item logging, huge objects, or full stack traces on every retry | Emit summary events, bound detail logs, enforce retention |
| Cannot find job by business date | Logged only execution timestamp without business date/logical key | Add safe business fields without dumping all parameters |
| Missing logs after crash | Buffer/queue not flushed or collector missed tail | Monitor pipeline, tune appender/flush, never replace `JobRepository` |

## 17. References and Version Scope

The Java examples for `JobExecutionListener`, `StepExecutionListener`, `SkipListener`, `JobExecution`, and `StepExecution` target **Spring Batch 5.2.x** with Java 17 and SLF4J 2. Spring Batch 6.x introduces some package/API changes, so adjust imports to your project version. Native structured logging properties require **Spring Boot 3.4 or later**; on earlier Boot releases, configure a JSON encoder explicitly.

- [Spring Boot Reference — Logging, Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot Blog — Structured logging in Spring Boot 3.4](https://spring.io/blog/2024/08/23/structured-logging-in-spring-boot-3-4/)
- [SLF4J Manual — MDC and Fluent Logging](https://www.slf4j.org/manual.html)
- [SLF4J API — `MDC`](https://www.slf4j.org/api/org/slf4j/MDC.html)
- [Spring Batch 5.2 API — `JobExecutionListener`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobExecutionListener.html)
- [Spring Batch 5.2 API — `StepExecutionListener`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/StepExecutionListener.html)
- [Spring Batch 5.2 API — `SkipListener`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/SkipListener.html)
- [Spring Batch 5.2 Reference — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/intercepting-execution.html)
- [Spring Batch 5.2 Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/5.2/monitoring-and-metrics.html)
- [logstash-logback-encoder — Logback JSON Encoder](https://github.com/logfellow/logstash-logback-encoder)

To make structured logging truly serve Spring Batch operations, standardize an **event schema**, bind `jobExecutionId`/`stepExecutionId` accurately to the execution context, log lifecycle and outcomes via listeners, and emit JSON through a matching encoder. For worker threads and remote partitions, propagate correlation context explicitly and always clean up MDC. When reading logs, distinguish **events** from **committed metadata**—use `JobRepository` to confirm statuses/counters and logs to diagnose root causes. Together, they form a searchable, safe, and reliable audit trail from job start through completion or failure.
