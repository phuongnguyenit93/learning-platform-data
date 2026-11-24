# Reducing Logs on Large Jobs in Spring Batch

## 1. Why Does a Large Batch Job Easily Generate Too Many Logs?

In a Spring Batch application, record counts can reach millions or tens of millions. If `ItemReader`, `ItemProcessor`, and `ItemWriter` each emit an `INFO` line per item, log volume scales linearly with records even during normal operation. With retries, skips, rollbacks, or parallel execution, the same item can appear in logs multiple times.

Suppose a job processes **10 million orders**:

| Logging Strategy | Approx. Log Count | Characteristics |
|---|---:|---|
| One line per item | 10,000,000 | Heavy I/O and storage overhead; hard to find important events. |
| One line per 1,000-item chunk | 10,000 | Smaller, yet still large across many continuously running jobs. |
| One line per 10,000 items processed | ~1,000 | Suitable for low-frequency progress tracking. |
| Start/finish logs per step | A few lines per step | Compact and easy to read final outcomes, but lacks mid-run progress. |

The main costs of excessive logging go beyond file size. Every log call can incur parameter evaluation, string formatting, stack-trace creation, appender synchronization, stdout writes, container-runtime forwarding, collector ingestion, indexing, and long-term retention.

For a large job, the goal is **keeping enough information for operations and debugging** with moderate log volume. You need to know *which job is running, how far along it is, how many items succeeded/failed, and what specific error occurred* without turning logs into a replica of all processed data.

```text
                  Very large batch job
                          |
          +---------------+---------------+
          |               |               |
       Item/Chunk      Step/Job     Infrastructure
          |               |               |
    Detailed logs   Start, progress,  Metrics / traces /
    when debugging  outcome logs      JobRepository
          |               |               |
       Sampling     INFO/WARN/ERROR   Continuous tracking
          +---------------+---------------+
                          |
               Sufficient diagnostic data
               with low log volume
```

## 2. Identifying Noisy Log Sources

In Spring Batch, logs originate from business code, the framework, and third-party libraries. Before cutting logs, identify which source emits what.

| Source | Common Log Pattern | Risk at Large Scale |
|---|---|---|
| `ItemReader` | `Read item ID=...` on every `read()` | Can generate millions of log lines. |
| `ItemProcessor` | Printing input/output on every `process()` | Costly and risks exposing sensitive data. |
| `ItemWriter` | `Writing ...` for every item | Repeated logs when chunks roll back/retry. |
| `ItemReadListener`/`ItemProcessListener`/`ItemWriteListener` | Logging inside `afterRead`, `afterProcess`, `afterWrite` | Invoked very frequently in chunk-oriented steps. |
| `SkipListener` | Stack trace per skipped item | During mass data errors, log volume spikes sharply. |
| `ChunkListener` | Logging every commit or every chunk error | Noisy when chunk size is small or retries are frequent. |
| `StepExecutionListener` | Logging at step start/end | Low volume; ideal place for summary logs. |
| `JobExecutionListener` | Logging at job start/end | Suitable for job-level outcomes. |
| Spring Batch/JDBC/SQL loggers | Transaction, SQL, bind, or execution details | `DEBUG`/`TRACE` output can be enormous. |
| HTTP clients, Kafka, ORM, external libraries | Requests/responses, queries, exceptions | Can multiply logs per outbound call. |

Distinguish two situations:

1. **Excessive logs from application per-item logging**: solved mainly by relocating logs, aggregating metrics, sampling, and rate limiting.
2. **Excessive logs from framework/libraries at `DEBUG` or `TRACE`**: solved first via `logging.level` configuration, before tuning appenders or sampling.

Raising framework logger levels alone will not silence `INFO` lines emitted by business code. Conversely, removing processor logs while leaving `org.springframework.jdbc` at `TRACE` still produces huge output.

## 3. Defining Observability Goals Before Optimizing

Not all log lines have equal value. A balanced design typically keeps these categories:

| Event | Suggested Frequency | Suggested Level | Data to Keep |
|---|---|---|---|
| Job started | Once per `JobExecution` | `INFO` | `jobName`, `jobExecutionId`, approved business keys. |
| Step started | Once per `StepExecution` | `INFO` | `stepName`, `stepExecutionId`, `jobExecutionId`. |
| Step in progress | By chunk/item milestone or time interval | `INFO` or `DEBUG` | Aggregate counters, elapsed time, progress if total is known. |
| Step completed | Once when callback fires | `INFO` or `WARN` | `BatchStatus`, `ExitStatus`, read/write/skip/rollback, duration. |
| Job completed | Once when callback fires | `INFO` or `ERROR` by status | Final status and duration. |
| Critical error failing step | Once per significant failure, deduplicated | `ERROR` | Error type, execution IDs, stack trace in one designated place. |
| Skipped items | Step summary, or bounded sample | `WARN`/`DEBUG` | Skip counts by type, error code, allowed technical IDs. |
| Item details for debugging | Only when explicitly enabled | `DEBUG`/`TRACE` | Non-sensitive IDs, masked/redacted values. |

**Do not treat logs as the sole source of truth for batch results.** `JobRepository` stores `JobExecution`, `StepExecution`, and `ExecutionContext`; metrics observe time-series measurements; committed business data confirms processing outcomes. Logs should illuminate meaningful events and link back to those sources.

## 4. Simplest First Step: Configure Sensible Logging Levels

Spring Boot applications use SLF4J as the logging API, typically backed by Logback when using standard starters. Configure levels in `application.yml`:

```yaml
logging:
  level:
    root: INFO
    com.example.batch: INFO
    com.example.batch.reader: WARN
    com.example.batch.processor: WARN
    org.springframework.batch: WARN
    org.springframework.jdbc: WARN
    org.hibernate.SQL: WARN
```

This is an **illustrative configuration**; replace `com.example.batch` with your actual package. Intent:

- Keep intentional business and summary events at `INFO`.
- Suppress per-item `INFO` logs from readers/processors when using package-scoped loggers.
- Prevent framework loggers from emitting `DEBUG`/`TRACE` during large job runs.
- `WARN` and `ERROR` continue to be recorded if loggers/appenders are configured accordingly.

Be aware: raising `com.example.batch.processor` to `WARN` can **hide genuinely needed `INFO` events** if all code shares one logger/package. Over the long term, separate loggers for **lifecycle summaries** from loggers for **per-item details**, or move item details down to `DEBUG`.

### 4.1. Move Frequent Logs Down to DEBUG/TRACE

Original noisy pattern:

```java
@Override
public Order process(Order order) {
    log.info("Processing order {}", order.getId());
    return normalize(order);
}
```

Change to:

```java
@Override
public Order process(Order order) {
    log.debug("Processing order id={}", order.getId());
    return normalize(order);
}
```

`Order` and `normalize(...)` are illustrative application types. At default `INFO`, the `DEBUG` line is not emitted. During incident triage, `DEBUG` can be enabled with bounded scope/duration to inspect details. However, **enabling DEBUG across millions of items still creates huge log volume**; pair it with sampling when needed.

### 4.2. Avoid Building Expensive Messages Before Level Checks

SLF4J supports `{}` placeholders:

```java
log.debug("Processing order id={} status={}",
        order.getId(), order.getStatus());
```

This is generally better than manual string concatenation:

```java
log.debug("Processing order " + order.getId()
        + ", payload=" + expensiveJsonSerialization(order));
```

Even when `DEBUG` is off, Java must still evaluate **argument expressions** before calling the logger. Thus, placeholders do not prevent `expensiveJsonSerialization(order)` from running if passed as an argument. When preparing costly log payloads, use a guard:

```java
if (log.isDebugEnabled()) {
    log.debug("Order id={} snapshot={}",
            order.getId(), safeDebugSnapshot(order));
}
```

`safeDebugSnapshot(...)` should avoid secrets/sensitive payloads and must not perform mandatory business logic. `isDebugEnabled()` skips snapshot generation when DEBUG is off, though it does not reduce volume once DEBUG is enabled; sampling is still needed for high event counts.

## 5. Moving from Per-Item Logs to Step Summary Logs

`StepExecutionListener` is the ideal place to emit **one summary message** for a step execution. In Spring Batch 5.x, `afterStep` receives `StepExecution`, providing read/write/filter/skip/commit/rollback counters and status.

Example using Java 17+ and Spring Batch 5.2.x:

```java
import java.time.Duration;
import java.time.LocalDateTime;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public final class StepSummaryLogListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepSummaryLogListener.class);

    @Override
    public void beforeStep(StepExecution step) {
        log.info("batch.step.started jobExecutionId={} stepExecutionId={} stepName={}",
                step.getJobExecution().getId(),
                step.getId(),
                step.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        long durationMs = elapsedMillis(step);

        String message = "batch.step.finished jobExecutionId={} "
                + "stepExecutionId={} stepName={} status={} exitCode={} "
                + "read={} written={} filtered={} skipped={} "
                + "commits={} rollbacks={} durationMs={}";

        Object[] fields = {
                step.getJobExecution().getId(),
                step.getId(),
                step.getStepName(),
                step.getStatus(),
                step.getExitStatus().getExitCode(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getSkipCount(),
                step.getCommitCount(),
                step.getRollbackCount(),
                durationMs
        };

        if (step.getStatus() == BatchStatus.COMPLETED) {
            log.info(message, fields);
        } else {
            log.warn(message, fields);
        }

        return null; // Observe only; do not alter ExitStatus.
    }

    private static long elapsedMillis(StepExecution step) {
        LocalDateTime start = step.getStartTime();
        LocalDateTime end = step.getEndTime();
        return start != null && end != null
                ? Duration.between(start, end).toMillis()
                : -1L;
    }
}
```

This listener emits **two lifecycle logs per step** on normal execution paths: one at start and one when the finish callback fires. Log volume stays constant regardless of item count. `durationMs=-1` is an illustrative sentinel when timestamps are missing; it does not represent a real negative duration.

`afterStep` runs after normal processing errors, yet **is not guaranteed** if the JVM/process is killed or crashes. When a job stops abnormally, inspect repository state and monitoring; never treat a missing finish log as sole proof of job state.

`afterStep` returns an `ExitStatus` so the framework can adjust exit codes if desired. When a listener solely logs, **return `null`** to avoid inadvertently changing the batch job's outcome or flow.

### 5.1. Registering the Listener on the Right Step

`TaskletStep` example in Spring Batch 5.x:

```java
@Bean
StepSummaryLogListener stepSummaryLogListener() {
    return new StepSummaryLogListener();
}

@Bean
Step importOrdersStep(JobRepository repository,
                      PlatformTransactionManager transactionManager,
                      StepSummaryLogListener summaryListener) {
    return new StepBuilder("importOrders", repository)
            .tasklet((contribution, chunkContext) -> {
                // Business tasklet goes here.
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .listener(summaryListener)
            .build();
}
```

Relevant Spring Batch 5.x imports: `org.springframework.batch.core.Step`, `org.springframework.batch.core.repository.JobRepository`, `org.springframework.batch.core.step.builder.StepBuilder`, `org.springframework.batch.repeat.RepeatStatus`, `org.springframework.transaction.PlatformTransactionManager`, `org.springframework.context.annotation.Bean`. This shows a `@Configuration` body snippet assuming Spring has already provisioned the Batch infrastructure.

For chunk-oriented steps, `.listener(summaryListener)` also applies on the corresponding builder. Never expect a `@Component` bean to automatically receive callbacks unless wired to the step or registered via a listener mechanism.

### 5.2. `readCount` and `writeCount` Do Not Have to Match

Do not treat a mismatch between read and write counts as an automatic error. A processor may return `null` to filter items, items may be skipped, or a tasklet may issue SQL updates bypassing chunk item counters. Summary logs should include `filtered` and `skipped` so operators understand the difference.

## 6. Bounded Progress Tracking: Logging Every N Successful Chunks

Start/finish logs alone may be insufficient for a job running for hours. You can emit **interval progress logs**, such as once every 200 successfully committed chunks, rather than once per item.

In Spring Batch 5.x, `ChunkListener.afterChunk(ChunkContext)` runs after a chunk completes successfully outside the chunk transaction; `afterChunkError(ChunkContext)` reports chunk-level errors. Thus `afterChunk` is ideal for counting **successfully completed chunks**, while errors are summarized/logged separately.

The example below uses `ConcurrentHashMap` and `AtomicLong` so one listener bean can serve multiple `StepExecution`s without mixing progress across a single shared counter:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.batch.core.scope.context.ChunkContext;

public final class ThrottledChunkLogListener
        implements ChunkListener, StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(ThrottledChunkLogListener.class);

    private final long everyChunks;
    private final ConcurrentMap<Long, AtomicLong> counters =
            new ConcurrentHashMap<>();

    public ThrottledChunkLogListener(long everyChunks) {
        if (everyChunks <= 0) {
            throw new IllegalArgumentException("everyChunks must be positive");
        }
        this.everyChunks = everyChunks;
    }

    @Override
    public void beforeStep(StepExecution step) {
        counters.put(step.getId(), new AtomicLong());
    }

    @Override
    public void afterChunk(ChunkContext context) {
        StepExecution step = context.getStepContext().getStepExecution();
        long count = counters.computeIfAbsent(
                step.getId(), ignored -> new AtomicLong())
                .incrementAndGet();

        if (count % everyChunks == 0) {
            log.info("batch.step.progress jobExecutionId={} "
                            + "stepExecutionId={} stepName={} successfulChunks={} "
                            + "read={} written={} skipped={}",
                    step.getJobExecution().getId(),
                    step.getId(),
                    step.getStepName(),
                    count,
                    step.getReadCount(),
                    step.getWriteCount(),
                    step.getSkipCount());
        }
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        counters.remove(step.getId());
        return null;
    }
}
```

With a commit interval of 500 items, logging every 200 chunks emits roughly one progress milestone per 100,000 successfully processed items under normal conditions. This is only an **estimate**; retries/skips, rollbacks, filtering, and reader/writer logic can keep read/write counts from advancing uniformly. The sample relies on the `StepExecution` ID assigned when the step runs through `JobRepository`; unit tests constructing unsaved steps must supply a mock ID in the fixture.

Registering the listener on the builder:

```java
@Bean
ThrottledChunkLogListener throttledChunkLogListener() {
    return new ThrottledChunkLogListener(200);
}

// In the actual step's StepBuilder:
// .listener(throttledChunkLogListener)
```

A listener implementing both lifecycle interfaces is registered through `.listener(...)` appropriately. When wiring multiple listeners on a step, avoid creating two separate instances of the same listener and expecting them to share a counter.

**Concurrency note:** `AtomicLong` keeps counter increments safe when callbacks run concurrently. `StepExecution` counts at any mid-run moment are a *progress snapshot*; in a multi-threaded step, they may be actively changing. Step-end summary logs, metrics, and the repository are better sources for final figures. With multi-process partitioning, each worker has its own listener and `StepExecution`; never infer job-wide totals from a single worker's local counter.

**Restart note:** When a restart creates a new `StepExecution`, the listener's chunk counter resets to 0. That count tracks successful chunks **in the current execution**, not cumulative totals across all attempts of the job instance. Include `jobExecutionId` and `stepExecutionId` in logs to scope numbers accurately.

### 6.1. When Logging Every N Chunks Is Not Ideal

Chunk-count milestones can still be too noisy for tiny chunks or too silent when a single chunk runs very slowly. Alternatives:

- **By item count:** emit only when items cross a new threshold, e.g. every 50,000 items; track the prior milestone so repeated equal read counts do not duplicate logs.
- **By time interval:** at most one log every 30–60 seconds per step execution; fits variable-speed jobs, requiring monotonic clocks and atomic coordination across threads.
- **Hybrid:** log upon crossing a large item milestone **or** when a time window elapses, using a per-execution rate limiter while ensuring error/summary logs are never throttled out.
- **No progress logs:** rely on metrics and dashboards for throughput/latency, keeping logs strictly for lifecycle events and errors.

Never call `Thread.sleep(...)` inside readers/processors to slow down logging. That stalls real work; throttling belongs purely in **deciding whether to emit a log**.

## 7. Sampling Item Logs While Still Supporting Diagnostics

In some systems, a handful of item-level logs helps spot anomalous data or reproduce errors. **Sampling** keeps log volume bounded.

### 7.1. Periodic Sampling

Example emitting one `DEBUG` line per 10,000 items passing through a processor:

```java
public final class SamplingOrderProcessor
        implements ItemProcessor<Order, Order> {

    private static final Logger log =
            LoggerFactory.getLogger(SamplingOrderProcessor.class);

    private final AtomicLong seen = new AtomicLong();

    @Override
    public Order process(Order item) {
        long count = seen.incrementAndGet();

        if (log.isDebugEnabled() && count % 10_000 == 0) {
            log.debug("batch.item.sample count={} orderId={}",
                    count, item.getId());
        }

        return normalize(item);
    }
}
```

This uses `org.springframework.batch.item.ItemProcessor`, `java.util.concurrent.atomic.AtomicLong`, and `org.slf4j.Logger/LoggerFactory`; `Order` and `normalize(...)` are application components. While simple to illustrate sampling, **it has limitations to understand**:

- `AtomicLong` belongs to the **processor instance**, not reset automatically per `StepExecution`. If a singleton processor bean spans multiple executions, the counter keeps growing across runs; choose appropriate bean scope or explicit reset logic.
- If the processor is re-invoked due to retry/rollback, the counter measures **processor invocations**, not committed items.
- Position-based sampling can miss rare events or patterns aligned with the sampling period.
- If you must analyze *every invalid item*, sampling error logs cannot replace an audit/quarantine table or structured error store.

For large jobs, the safer default is **aggregate logging from `StepExecution`**, sampling items only when truly needed. When deterministic sampling by ID is desired so the same item stays sampled across runs, select items by hashing a **non-sensitive business key** instead of using a global counter. Understand hash behavior and never leak identities/PII into logs.

### 7.2. Never Apply Sampling Blindly to ERROR Logs

Do not use one sampling rate across all log levels. For example:

- `DEBUG` normal item details: sample aggressively or disable completely.
- `INFO` progress: rate-limit per step execution.
- `WARN` invalid data: aggregate by error type and log only a few approved examples.
- `ERROR` failing a step/job: always emit complete summary events and error codes/IDs for lookup; never drop fatal error logs via sampling.

If a batch hits 500,000 identical bad rows, emitting 500,000 `ERROR` stack traces helps no more than emitting **representative errors** alongside counts and root-cause buckets. When business rules require storing every rejected row, write them to a **quarantine table, error file, or dead-letter sink** with proper transaction/restart rules; logs are not a reliable business data store.

## 8. Aggregating Errors and Skip Stats Instead of Printing Stack Traces Every Time

In a fault-tolerant step, read/process/write callbacks can fire repeatedly around retries and rollbacks. If each callback logs the same exception with a stack trace, logs fill up with copies of one failure.

`StepExecution` provides total counters usable at step end:

```java
@Override
public ExitStatus afterStep(StepExecution step) {
    if (step.getSkipCount() > 0) {
        log.warn("batch.step.skips stepExecutionId={} "
                        + "readSkips={} processSkips={} writeSkips={} "
                        + "totalSkips={}",
                step.getId(),
                step.getReadSkipCount(),
                step.getProcessSkipCount(),
                step.getWriteSkipCount(),
                step.getSkipCount());
    }
    return null;
}
```

This is a **standalone callback sample**; if `StepSummaryLogListener` already has `afterStep`, merge the skip summary into that method instead of declaring two `afterStep` methods with the same signature in one class.

If root-cause breakdowns are needed, use `SkipListener` or error-point listeners to **increment counters by error category**, then emit one summary. To avoid unbounded memory growth, never accumulate full item objects/exceptions in a `Map`. Keep a bounded set of error categories and log only a few controlled sample records.

Example of error-log field design:

```text
batch.step.skips stepExecutionId=4102 totalSkips=231
batch.step.skip-categories stepExecutionId=4102 invalidFormat=170 missingReference=61
batch.step.failed stepExecutionId=4102 exceptionType=IllegalStateException
```

Never print full JSON payloads, SQL bind parameters, access tokens, payment details, or customer information just for debugging. Log systems typically have broader readership and different retention periods than business databases.

### 8.1. Designate One Place to Log Full Stack Traces

A clear operational rule:

1. A high-level error boundary logs one full stack trace **per meaningful failure**.
2. Other listeners log `exceptionType`/`errorCode` and execution IDs without repeating stack traces.
3. If the step recovers via retry, summary logs reflect the final outcome; do not treat every transient exception as a step failure.

For exceptions carrying sensitive content in messages or causes, apply data-filtering policies before logging. Just because an error was handled cleanly by the framework does not mean its raw exception message is safe to print verbatim.

## 9. Structured Logging Keeps Line Counts Low Yet Searchable

When centralized logs go to OpenSearch, Elasticsearch, Loki, or an observability platform, consistent structure enables fast queries without verbose explanatory lines. Sample summary event:

```json
{
  "event": "batch.step.finished",
  "jobName": "importOrdersJob",
  "jobExecutionId": 701,
  "stepName": "importOrders",
  "stepExecutionId": 902,
  "status": "COMPLETED",
  "exitCode": "COMPLETED",
  "readCount": 1000000,
  "writeCount": 995000,
  "filterCount": 5000,
  "skipCount": 0,
  "durationMs": 178200
}
```

This is an **illustrative data format**, not default output of `StepSummaryLogListener` from Section 5. To get real JSON fields, configure your logging backend/encoder or use structured logging supported by your Spring Boot version.

In Spring Boot 3.4+ with built-in structured logging, start with:

```yaml
logging:
  structured:
    format:
      console: ecs
```

`ecs` stands for Elastic Common Schema format; additional keys depend on how your application emits logs and backend support. To emit fields with fixed names, use the SLF4J 2 fluent API with an encoder configured to preserve key-value pairs:

```java
log.atInfo()
        .addKeyValue("event", "batch.step.finished")
        .addKeyValue("stepExecutionId", step.getId())
        .addKeyValue("status", step.getStatus())
        .addKeyValue("readCount", step.getReadCount())
        .addKeyValue("writeCount", step.getWriteCount())
        .log("Step finished");
```

Not every appender emits these pairs as JSON fields. Select and configure a compatible encoder. `jobExecutionId` and `stepExecutionId` are valuable for log search, yet **should not be used as tags on every metric** because of high cardinality.

## 10. MDC and Correlation IDs: Use in Moderation

MDC (*Mapped Diagnostic Context*) attaches context such as job/step execution IDs to logs on the current thread. Inside a short callback, you can write:

```java
import org.slf4j.MDC;

void logSummary(StepExecution step) {
    try (MDC.MDCCloseable jobId = MDC.putCloseable(
                    "jobExecutionId",
                    String.valueOf(step.getJobExecution().getId()));
         MDC.MDCCloseable stepId = MDC.putCloseable(
                    "stepExecutionId", String.valueOf(step.getId()))) {

        log.info("batch.step.finished stepName={} status={}",
                step.getStepName(), step.getStatus());
    }
}
```

When the logging backend includes MDC in patterns/JSON, you can filter by ID without manually adding IDs to every message. However:

- MDC is **thread-scoped**. In multi-threaded steps, partitioning, or async processing, MDC does not reliably propagate to other threads automatically.
- Putting MDC in `beforeStep` and clearing only in `afterStep` risks leaking state when flows terminate abnormally or callbacks run on different threads.
- Clean up MDC via `try-with-resources`/`finally`, and use dedicated propagation if cross-thread correlation is needed.
- Never use MDC as a backdoor to dump all `JobParameters`; insert only approved keys.

Log volume drops primarily by emitting **fewer events**; MDC and structured fields make remaining events easier to search, rather than shrinking volume on their own.

## 11. Metrics Instead of Continuous Progress Logs

Common operational questions are “how long has this job been running?”, “how many steps are active?”, and “is read/write latency spiking?”. These fit **metrics** and dashboards far better than emitting logs every few seconds for items.

Spring Batch 5.2 provides Micrometer support with `spring.batch`-prefixed metrics, such as:

| Metric | Measurement Type | Meaning |
|---|---|---|
| `spring.batch.job` | Timer | Job execution duration, tagged by name and status. |
| `spring.batch.job.active` | Long task timer | Currently active jobs. |
| `spring.batch.step` | Timer | Step execution duration. |
| `spring.batch.step.active` | Long task timer | Currently active steps. |
| `spring.batch.item.read` | Timer | Item read duration. |
| `spring.batch.item.process` | Timer | Item process duration. |
| `spring.batch.chunk.write` | Timer | Chunk write duration. |

Built-in metrics are great for latency and state. They do not automatically replace every custom business counter. When measuring throughput or valid record totals, build application counters/gauges ensuring accurate semantics across retries/rollbacks. For instance, counting every `process()` call **does not always equal** committed items.

In Spring Boot, metrics are typically exposed via Micrometer/Actuator when matching dependencies and registries (e.g. Prometheus registry) are present and endpoints are properly configured and secured. Never assume “Micrometer is on the classpath, so dashboards must already be collecting data”.

**Keep cardinality low:** sensible tags are job name, step name, and bounded status enums. Never create metric tags for individual `orderId`s, arbitrary `fileName`s, or `jobExecutionId`s; millions of unique values overload metrics backends. Keep execution IDs in logs/traces while metrics aggregate by workload type.

A balanced operational model:

```text
Metrics       -> alert on latency, throughput, failure rate
Logs          -> lifecycle events and errors requiring investigation
JobRepository -> job/step status and checkpoints
Business DB   -> committed business outcomes
Traces        -> cross-service paths when analyzing latency
```

## 12. Async Logging: Reducing I/O Impact While Understanding Risks

When log volume remains significant, logging backends support **asynchronous appenders** so batch threads enqueue log events and a background thread flushes them to the destination. This reduces main-thread I/O blocking in many cases, yet **does not eliminate log creation cost** or reduce total bytes shipped if event counts stay the same.

Simple Logback configuration example in `src/main/resources/logback-spring.xml`:

```xml
<configuration>
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>

    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>2048</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <appender-ref ref="STDOUT"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

This sample uses `queueSize=2048` and `neverBlock=false` to prioritize not dropping events on a full queue: during heavy backlogs, producers can **block** until queue space opens. That is an important trade-off because job throughput can suffer. With `neverBlock=true`, the app drops logs when the queue fills; decide whether event loss is acceptable. `discardingThreshold` also controls dropping lower-priority events in Logback; misconfiguration can lose critical diagnostics.

Risks to weigh:

- Process crashes can lose events still buffered in the queue.
- Too small a queue causes producer blocking/drops; too large a queue consumes memory and slows shutdown flushing.
- Async appenders mainly reduce I/O waiting; still avoid per-item logs and costly serialization.
- Stack traces and heavy events still incur encoding and storage costs.
- When customizing `logback-spring.xml`, understand how it interacts with Spring Boot's built-in logging properties and appenders.

Prioritize reducing **event counts** before tuning async queues; that usually delivers the biggest, cleanest win.

## 13. Log Rotation, Retention, and Log Collectors

Even after reducing application logs, storage and search still need lifecycle policies:

| Measure | Benefit | Considerations |
|---|---|---|
| Write stdout in containers | Easy integration with log collectors | Enforce size/retention limits in the container runtime or log platform. |
| Rotate files by size/time | Prevents unbounded single-file growth | Ensure collectors tail rotated files and clean old files properly. |
| Retention by log type | Cuts storage costs | Never truncate data required for mandatory audit/compliance. |
| Collector filtering/sampling | Reduces network/indexing load | Logs were already built by the app; collector filtering cannot refund CPU/I/O spent upstream. |
| Structured fields & smart indexing | Fast incident lookup | Avoid indexing high-cardinality fields or huge item blobs. |

If the application writes one million lines to stdout, having the collector retain only a subset **does not eliminate formatting and stdout write costs**. Application-boundary sampling is more economical when skippable events are well defined.

In systems requiring per-transaction auditing, observability logs and business audits are separate streams. Never thin out mandatory audit trails via random sampling; design dedicated audit records with explicit schemas, access controls, transactions, and retention.

## 14. Testing Log-Reduction Strategies

Never test by waiting for a tens-of-millions-of-records job on every build. Verify log emission logic at small scale first, then measure performance impact in an appropriate load-test environment.

### 14.1. Unit Testing the Summary Listener

Spring Boot Starter Test provides `OutputCaptureExtension` to capture console logs in tests. `spring-batch-test` offers `MetaDataInstanceFactory` to create `StepExecution` without running a whole job.

Illustrative dependencies for Spring Boot 3.x:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

JUnit Jupiter example:

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
class StepSummaryLogListenerTest {

    private final StepSummaryLogListener listener =
            new StepSummaryLogListener();

    @Test
    void logsOneSummaryForACompletedStep(CapturedOutput output) {
        StepExecution step = MetaDataInstanceFactory
                .createStepExecution("importOrders", 636L);
        step.setStatus(BatchStatus.COMPLETED);
        step.setReadCount(100_000);
        step.setWriteCount(99_500);
        step.setFilterCount(500);

        listener.beforeStep(step);
        assertNull(listener.afterStep(step));

        assertThat(output.getOut())
                .contains("batch.step.started")
                .contains("batch.step.finished")
                .contains("stepExecutionId=636")
                .contains("read=100000")
                .contains("written=99500");
    }
}
```

This test assumes `INFO` logging is enabled and a console appender writes to stdout. Adjust test config if your test profile disables console output or sets a higher threshold. This unit test verifies callback formatting, not that the listener is attached to an actual step.

### 14.2. Testing Throttling with Simulated Chunk Counts

For `ThrottledChunkLogListener(200)`, create a `StepExecution` with `MetaDataInstanceFactory`, build a `ChunkContext`, invoke `afterChunk` 199 times confirming no progress log appears, then invoke a 200th time confirming the log appears. After calling `afterStep`, run another `StepExecution` to verify counters reset per execution.

Tests should assert **boundary behavior** (199, 200, 201) plus state cleanup across executions. You do not need millions of real items to test rate-limiting math.

To test thread safety, invoke callbacks across multiple threads for distinct executions and verify each execution keeps its own cadence. That measures counter logic rather than full Spring Batch throughput.

### 14.3. Measuring Optimization Impact

When evaluating a log-reduction change, run the same workload/input in a load-test environment and compare:

| Metric | Before Optimization | Target After Optimization |
|---|---|---|
| Log events per 1,000 items | Very high with per-item logging | Reduced to target threshold. |
| Log bytes emitted/minute | Scales linearly with item count | Drops sharply on normal paths. |
| Throughput (items/s) | Degraded by logging overhead | Steady or higher as I/O drops. |
| CPU spent on serialization/logging | High when logging payloads | Lower once unnecessary formatting is removed. |
| Chunk latency p95/p99 | Elevated when appender/collector lags | Drops if logging was a bottleneck. |
| Time to diagnose failures | High noise hides root cause | Maintained or improved via clear events and IDs. |
| Missed alerts/incidents | Observability quality bar | Zero increase after sampling. |

If you do not know whether logging is the bottleneck, never conclude from line counts alone. Measure throughput, I/O, and diagnostic clarity before/after, because in some workloads the database or external API is the true bottleneck.

## 15. Restart, Retry, Partitioning, and Summary Logs

### 15.1. Retries/Rollbacks Can Cause an Item to Appear Multiple Times

In a fault-tolerant step, an item can be read/processed/written again. If a processor logs `INFO` on every invocation, logs can double-count items after rollbacks. Never treat **per-item log line counts** as committed item counts.

`StepExecution.getReadCount()`, `getWriteCount()`, `getSkipCount()`, and related fields reflect Batch-managed step statistics. When exact committed DB record counts are needed, verify against target business data or a transaction-aligned business counter.

### 15.2. Restarts Create New Execution IDs

A restart typically creates a new `JobExecution` under the same `JobInstance`, and re-run steps receive new `StepExecution`s. For example:

```text
jobInstanceId=51, jobName=nightlyImport
  jobExecutionId=901
    stepExecutionId=1101 status=FAILED
  jobExecutionId=902
    stepExecutionId=1105 status=COMPLETED
```

When logging progress, always include `jobExecutionId` and `stepExecutionId`; progress counters in the new execution do not necessarily continue from the old execution's numbers. To follow restart chains of one instance, include `jobInstanceId`.

### 15.3. Partitioning and Multi-Threaded Steps

Each partition normally gets its own `StepExecution`. Never have every partition log a job-wide progress summary on every chunk; that multiplies logs by the partition count. Instead, let each worker emit sparse events with its partition/step execution ID, and aggregate job-wide progress via metrics or JobRepository.

In multi-threaded steps, mid-run progress counters change concurrently. An `AtomicLong` inside a singleton listener not keyed by execution will mix two concurrent jobs. Scope state by execution ID, synchronize properly, or use an execution-scoped bean. Never buffer full items in state merely for log summaries.

### 15.4. Paused Steps, Crashes, and Missing Final Logs

If a process loses power/crashes or infrastructure terminates the JVM, `afterStep`/`afterJob` may never run. An aggressively log-reduced job might lack recent progress trails. Maintain real-time metrics, repository job/step states, and long-running job alerts; they complement lifecycle logs.

## 16. Common Log-Reduction Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Changed `root` to WARN, yet console stays flooded | Code/libraries use specific logger overrides or other appenders; messages are at WARN/ERROR | Find offending loggers/classes, set proper levels, and remove per-item logs. |
| Job runs faster, yet critical errors disappear | Sampling/rate limits applied to final error logs too | Always keep failure summaries and execution IDs; sample only droppable logs. |
| `DEBUG` is off, yet CPU stays high on logging | Serialization or argument methods run before logger checks level | Use parameterized logging and `isDebugEnabled()` guards for expensive work. |
| Duplicate progress logs | Multiple listeners registered or threshold lacks per-execution tracking | Audit listeners; key counters/state by `StepExecution`. |
| Progress numbers jump backward after restart | New execution's counters start fresh | Include execution IDs; never merge counters across executions blindly. |
| “Success” log counts disagree with DB | Retries/rollbacks or processor logged before commit | Rely on step statistics and committed data, not item log counts. |
| Async appender drops logs | Queue overflow, `neverBlock=true`, crash before flush | Weigh drop vs block policies; monitor queue depth and shutdown flushing. |
| Added sampling, yet storage stays high | Multiple jobs/replicas, bulky payloads, or framework at TRACE | Cut application events, trim fields, tighten levels and collectors. |
| Enabling DEBUG to investigate slows job down | Processor logs every item | Scope DEBUG narrowly, combine with sampling, set an expiration window. |
| Logs leak sensitive data | Printing full items, params, context, or exception bodies | Allowlist log fields, mask sensitive values, separate audits when needed. |
| Zero mid-run visibility | Only start/finish logged on multi-hour steps | Add throttled progress logs or dashboard metrics. |
| Metrics backend overloaded | Item IDs or execution IDs used as metric tags | Keep tags low-cardinality; put execution IDs only in logs/traces. |

## 17. Step-by-Step Process to Reduce Logs on a Large Job

A practical workflow to improve observability while cutting costs:

1. **Measure baseline log volume:** capture lines/bytes per minute, volume by logger, job duration, and throughput.
2. **Identify top log producers:** readers, processors, writers, item listeners, SQL loggers, or framework internals.
3. **Classify events to keep:** lifecycle, errors, summary outcomes, and progress milestones vs debug details.
4. **Replace per-item logs with step/job summaries:** include execution IDs, status, exit code, and counters for clear investigation starting points.
5. **Pick a progress strategy:** log by item milestone, chunk count, or time interval tuned to job speed and duration.
6. **Aggregate skips and retries:** record totals and top causes; avoid repeating stack traces/payloads for thousands of identical bad items.
7. **Set logger levels:** disable DEBUG/TRACE by default on hot packages/frameworks while keeping controlled troubleshooting toggles.
8. **Use metrics for dashboards:** track latency, active jobs, throughput, and alerts instead of per-item log lines.
9. **Test log bounds:** verify threshold and step-end events, especially under retry/restart and multi-threaded steps.
10. **Re-measure impact:** compare log volume, throughput, latency, and troubleshooting speed; tune thresholds from real data.

### Hands-on Exercises

**Exercise 1 — From One Million Logs Down to Summaries**

Suppose `ItemProcessor` currently logs `INFO` for every item. Downgrade item logs to `DEBUG`, add `StepSummaryLogListener`, and include `read`, `written`, `filtered`, `skipped`, and `durationMs` in the step-end log. Unit-test with `MetaDataInstanceFactory` to confirm accurate fields.

**Exercise 2 — Progress Every 100 Chunks**

Register `ThrottledChunkLogListener(100)` on a chunk-oriented step. Run a test with many small chunks and observe zero progress logs for chunks 1–99, one event at chunk 100, and one event at step end. Account for rollbacks: failed chunks must not count as successful commits.

**Exercise 3 — Job with Heavy Data Errors**

Simulate 1,000 invalid items of the same type. Design aggregation for `readSkips`, `processSkips`, `writeSkips`, and representative error samples. Compare against writing 1,000 stack traces, and determine where full rejected items should be stored if business reconciliation requires them.

**Exercise 4 — Measuring Logging Overhead**

Run the same dataset under three settings: per-item `INFO` logging, per-item `DEBUG` logging with DEBUG disabled, and summary + throttled milestone logs only. Compare event counts, log bytes, throughput, and runtime while keeping database, input, and chunk size constant.

## 18. Official References

- [Spring Batch 5.2 — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/intercepting-execution.html): using `StepExecutionListener`, `ChunkListener`, and item listeners.
- [Spring Batch 5.2 — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/5.2/monitoring-and-metrics.html): built-in Micrometer metrics and available measurements.
- [Spring Batch 5.2 — `ChunkListener` Javadoc](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/ChunkListener.html): chunk callback timing and rollback notes.
- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): `logging.level`, Logback configuration, and structured logging.
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): observing metrics with Micrometer/Actuator.
- [Logback Manual — AsyncAppender](https://logback.qos.ch/manual/appenders.html#AsyncAppender): queues, discarding policies, and async logging trade-offs.
- [SLF4J Manual](https://www.slf4j.org/manual.html): parameterized logging, MDC, and fluent API.

