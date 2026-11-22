# Correlation ID and Batch Processing in Java Logging

## 1. Why Does Batch Processing Need a Correlation ID?

A **Correlation ID** is an identifier used to link log events that belong to the **same meaningful processing flow**, even when they are emitted across multiple Java classes, multiple worker threads, multiple retries, or multiple services. For **batch** processing, a correlation ID is especially useful because a job can run for minutes or hours, be split into chunks, execute in parallel, and be restarted after a failure.

A batch importing 10,000 records can produce thousands of log lines:

~~~text
INFO  correlationId=corr-42 batchId=batch-42 batchRunId=run-1 event=batch.started
INFO  correlationId=corr-42 batchId=batch-42 batchRunId=run-1 itemId=item-001 event=item.started
WARN  correlationId=corr-42 batchId=batch-42 batchRunId=run-1 itemId=item-002 attempt=1 event=item.retry_scheduled
INFO  correlationId=corr-42 batchId=batch-42 batchRunId=run-1 itemId=item-002 attempt=2 event=item.succeeded
INFO  correlationId=corr-42 batchId=batch-42 batchRunId=run-1 event=batch.completed
~~~

The lines above are **illustrative data**. The Correlation ID lets you view the entire flow, while `batchId`, `batchRunId`, `itemId`, and `attempt` pinpoint a more specific scope.

**Key point:** A Correlation ID is for **observability and tracing**; it **does not by itself prevent an item from being processed twice, does not create a transaction, does not guarantee exactly-once delivery, and does not replace checkpoints or idempotency keys**. Safe batch processing requires combining identifiers, durable state, and retry/commit policies.

An easy-to-understand model:

~~~text
Correlation ID: corr-42       A business flow to trace
   |
   +-- Batch ID: batch-42     Logical unit of work
          |
          +-- Run ID: run-1  First run: partial processing, with failure
          |      +-- item-A attempt=1 -> succeeded
          |      +-- item-B attempt=1 -> failed
          |
          +-- Run ID: run-2  Rerun/resume
                 +-- item-B attempt=2 -> succeeded
~~~

In the model **chosen for this lesson**, the correlation ID and batch ID remain stable across both executions, while the run ID changes. That is a **valid design convention**, not a mandatory rule of Java or every batch framework. An organization may assign a new correlation ID for each trigger request or use a single parent ID for the entire workflow; what matters is defining it clearly and consistently.

## 2. Distinguishing ID Types in Batch Processing

| Field | Question it answers | Suggested scope and lifecycle |
| --- | --- | --- |
| `correlationId` | Which processing chain / investigation context do these logs belong to? | Kept stable within the defined workflow scope |
| `batchId` | Which logical batch of work is this? | Preserved across retries/resumes of the **same logical batch** |
| `batchRunId` | Which specific execution of the batch is this? | New for each start/restart treated as a new execution |
| `jobName` | Which type of batch/job is running? | Bounded values such as `nightly-import` |
| `itemId` / `recordId` | Which record / unit of work? | Durable ID to reconcile items |
| `chunkId` / `partitionId` | Which group/partition is processing? | System-managed chunk or partition scope |
| `attempt` | Which attempt number is this for the unit of work? | Incremented on retry according to a defined contract |
| `requestId` | Which HTTP/API request triggered the operation? | Usually changes per request; may end before the batch finishes |
| `traceId` / `spanId` | Which distributed trace/span is the event in? | Created/maintained by the tracing system |
| `idempotencyKey` | What key does the system use to prevent duplicate side effects? | Defined per **business side effect to deduplicate** |

**Do not concatenate these fields into a single string.** For example, `corr-42|batch-42|run-2|item-B|attempt-2` may be human-readable, but for structured search they should be separated into clearly named fields. Dynamic IDs differ in **cardinality** and lifecycle.

### 2.1. Correlation ID vs. Batch ID

A Correlation ID can span **multiple batches** triggered by a single workflow. For example, an end-of-day process might have an order import batch, a reconciliation batch, and a report-sending batch; all three can share the same `correlationId` while having different `batchId` values.

Conversely, the same batch may be started from a new request several hours later; depending on the contract, that request has its own correlation ID while the logical batch ID is preserved. You cannot assume they are always identical.

### 2.2. Batch ID vs. Run ID

`batchId=batch-42` identifies the **logical job**; `batchRunId=run-1` and `run-2` indicate two executions. When checkpoint/resume is used, keeping `batchId` stable lets you view overall progress, while changing `runId` isolates logs belonging to a specific execution.

In **Spring Batch**, `JobInstance` and `JobExecution` are framework concepts with their own semantics; you can map their internal IDs to application fields once you understand identifying job parameters and restart policies. **Do not assume `JobInstance.id == correlationId` or `JobExecution.id == batchRunId` by default** without designing the mapping.

### 2.3. Item ID vs. Attempt

An item retried three times is still the **same item**, for example `itemId=item-B` and `attempt=1/2/3`. Changing `itemId` on each retry makes it hard to count unique items and easily hides the problem of a single item failing repeatedly.

`attempt` can also be counted per **run** or across the entire **item** lifecycle; the contract must be documented clearly. This lesson increments `attempt` **across runs of the same item**, so `item-B attempt=2` in `run-2` means it is the second attempt for `item-B` across the entire logical batch.

### 2.4. Correlation ID vs. Idempotency Key

A **Correlation ID** links logs; an **idempotency key** controls whether the same request or side effect is applied repeatedly. A batch can redeliver a message after a crash even when the correlation ID does not change. If you are transferring money, updating balances, or sending important emails, you need transactions, a deduplication store, unique constraints, or an appropriate idempotent consumer mechanism.

**Do not use the correlation ID as an idempotency key by default**: a single correlation ID can cover many distinct valid items. An idempotency key usually needs to be tied to the specific side effect, such as `batchId + itemId + operation`, after verifying that the identifier scope is appropriate.

## 3. Choosing a Correlation ID Lifecycle for a Batch

Before writing code, answer: *"Which set of logs must be findable with a single ID?"*

Some common models:

| Scenario | What the Correlation ID should represent |
| --- | --- |
| An HTTP request running a synchronous batch | The request or the workflow handling that request |
| An API triggering an asynchronous batch that runs for hours | The created workflow/job, not just the HTTP request lifetime |
| A batch resumed after a restart | Can keep the original logical correlation ID; add a new run ID |
| A parent batch spawning multiple child batches | One parent correlation ID and child batch IDs; optionally add `parentId` |
| An item pushed across multiple services | Cross-service correlation ID if the contract allows; separate `itemId` |
| Multiple independent batches running concurrently | Distinct IDs; avoid assigning one shared ID to all jobs with the same name |
| A large batch split into partitions | Shared correlation ID/`batchId`; `partitionId`/`chunkId` distinguishes branches |

### 3.1. Generating IDs at a Trusted Boundary

If an API receives an `X-Correlation-ID` header from upstream, **do not treat every input as trustworthy**. You may accept an ID from a trusted gateway or tracing infrastructure; if it is missing or violates policy, the server generates one itself. Enforce length limits, character allowlists, and protection against CR/LF log injection.

Example **Java 17 snippet**, not a mandatory rule for every product:

~~~java
// rawCorrelationId may be null or come from an external header.
String correlationId =
        rawCorrelationId != null
        && rawCorrelationId.matches("[A-Za-z0-9_-]{1,64}")
        ? rawCorrelationId
        : java.util.UUID.randomUUID().toString();
~~~

This check blocks empty strings, overly long strings, and unwanted characters; it **does not prove that the ID source is trusted or globally unique**. If the ID plays a special role in security or reconciliation, a dedicated issuance/verification mechanism is required.

### 3.2. Do Not Put Sensitive Data in IDs

Do not use email addresses, phone numbers, access tokens, JWTs, card numbers, or payloads as a correlation ID or batch ID. IDs travel through many logs, collectors, dashboards, admin URLs, and support systems. Choose **opaque IDs** that reveal no business information and are permitted to be stored under data policies.

### 3.3. Persisting the Mapping at Batch Creation

An API might return early:

~~~json
{
  "status": "accepted",
  "batchId": "batch-42",
  "correlationId": "corr-42"
}
~~~

This is an **illustrative** response, not a Java rule. At batch creation time, store the `batchId → correlationId` mapping in a durable record or job metadata if workers will run after the request thread has finished. **Do not rely on the request thread's `ThreadLocal`/MDC to remember the correlation ID for hours.**

## 4. Batch Processing Flow: From Trigger to Completion

A typical pipeline:

~~~text
HTTP / Scheduler / Message Consumer
    |
    |  Create/select correlationId + batchId
    v
Persist batch metadata / enqueue command
    |
    v
Batch coordinator (batchRunId=run-1)
    |
    +----> Partition P-1 ----> Worker item-A
    |                             |
    |                             +--> item event
    |
    +----> Partition P-2 ----> Worker item-B
                                  |
                                  +--> retry / failure
    |
    v
Batch summary, checkpoint, status
    |
    v
Resume/restart (batchRunId=run-2) when needed
~~~

At every **asynchronous boundary**, the context must be passed explicitly in the task, message, or metadata. Never assume a `ThreadLocal` survives across processes, threads, containers, or after a job is saved to a database.

### 4.1. Recommended Batch Events

| Event name (illustrative) | When emitted | Recommended fields |
| --- | --- | --- |
| `batch.accepted` | Batch creation request is accepted | correlationId, batchId, jobName |
| `batch.started` | A batch execution starts | correlationId, batchId, batchRunId, attempt/run number |
| `batch.item.started` | An item starts processing (if detail is needed) | itemId, attempt, chunkId |
| `batch.item.retry_scheduled` | Item fails transiently and will be retried | itemId, attempt, reasonCode, nextRetryAt |
| `batch.item.succeeded` | Item completes its side effect per contract | itemId, attempt, durationMs |
| `batch.item.failed` | An attempt/item fails | itemId, attempt, error.type, retryable |
| `batch.checkpoint.saved` | Progress is durably saved | checkpointId, processedCount |
| `batch.finished` | A run ends with a clear outcome | batchRunId, outcome, succeeded/failed/skipped counts |
| `batch.completed` | The **logical batch** reaches final success state | batchId, totalCount, durationMs |

The names above are **illustrative conventions**, not event names required by JUL, SLF4J, or Spring Batch. A production event catalog must distinguish **per-run** events from **per-logical-batch** events. For example, `batch.finished outcome=partial` for `run-1` must not be interpreted by a dashboard as "the logical batch succeeded."

### 4.2. Do Not Log Every Item If Volume Does Not Allow It

A batch can have millions of items; emitting five INFO logs per item can generate millions of records, consuming CPU, disk/network bandwidth, and indexing cost. Options include:

- INFO for batch started/finished milestones and major checkpoints.
- WARN/ERROR for actionable failures; avoid logging the same full exception at every layer.
- DEBUG/TRACE or controlled sampling for per-item logs during investigation.
- Metrics/counters for processed/succeeded/failed/retried counts and duration.
- A durable status table for **per-item** outcomes if the business requires exact auditing.

A Correlation ID links what was logged, but **cannot recover events that were never emitted or were dropped by a queue/collector**. Actual item totals should come from a reliable state source and properly designed metrics, not just counting log lines.

## 5. Structured Logging Schema for Batch Processing

A structured JSON record:

~~~json
{
  "timestamp": "2026-11-09T10:15:00Z",
  "level": "WARN",
  "service": "import-worker",
  "eventCode": "BATCH-RETRY-001",
  "eventName": "batch.item.retry_scheduled",
  "correlationId": "corr-42",
  "batchId": "batch-42",
  "batchRunId": "run-1",
  "jobName": "nightly-import",
  "partitionId": "part-2",
  "chunkId": "chunk-07",
  "itemId": "item-B",
  "attempt": 1,
  "outcome": "retryable",
  "reasonCode": "DEPENDENCY_TIMEOUT",
  "retryDelayMs": 1000,
  "message": "Retry scheduled after dependency timeout"
}
~~~

This is an **illustrative application-defined schema**, not the default output of `Logger.warn(...)`. In a real pipeline, the JSON layout/encoder must actually emit these keys as **queryable fields** with their proper data types preserved: `attempt` and `retryDelayMs` are numbers, not strings.

### 5.1. Field and Data Type Conventions

| Field | Suggested type | Rule |
| --- | --- | --- |
| `timestamp` | timestamp / ISO-8601 UTC string | Explicit timezone |
| `level` | string | Consistent with backend and mapping |
| `eventCode` / `eventName` | stable string | Must not contain dynamic `itemId`/`requestId` |
| `correlationId` | opaque string | Issued at a trusted boundary |
| `batchId` / `batchRunId` | opaque string | Clear logical-vs-execution mapping |
| `itemId` / `partitionId` / `chunkId` | string | Only when the event has that scope |
| `attempt` | integer | Incremented strictly per defined retry rules |
| `outcome` | enum string | E.g., started/succeeded/failed/partial |
| `durationMs` | number | In milliseconds; do not format as text with "ms" |
| `error.type` / `error.code` | string | For error events |
| `traceId` / `spanId` | string | Only when a real tracing context exists |
| `schemaVersion` | integer/string | When the pipeline needs contract governance |

Choose consistent field names. `batchRunId`, `batch_run_id`, and `jobExecutionId` may refer to the same concept across three systems, but **must not be assumed to be the same field** without a mapping. Ingestion needs a shared contract and tests.

### 5.2. JSON Lines Instead of Hard-to-Parse Messages

When using NDJSON, each event is serialized as a single JSON object on one physical line; newlines inside exception messages or stack traces must be escaped inside JSON strings. A batch event may carry a `Throwable` with many frames, but the entire exception should stay within one properly formatted field if the collector expects one event per line.

Never concatenate user data directly into `{"itemId":"..."}`: unescaped keys or values can break JSON and cause log injection. Use a reliable encoder and restrict sensitive data.

## 6. Correlation ID and MDC: Propagating IDs to Every Worker Log

**Mapped Diagnostic Context (MDC)** is a mechanism for storing key/value pairs for log events, typically bound to a thread or context. In an **SLF4J + Logback** setup, you can set:

~~~java
// Snippet within the batch processing scope, with validated IDs.
org.slf4j.MDC.put("correlationId", correlationId);
org.slf4j.MDC.put("batchId", batchId);
org.slf4j.MDC.put("batchRunId", batchRunId);
try {
    LOG.info("event=batch.started");
    executeBatch();
} finally {
    org.slf4j.MDC.remove("batchRunId");
    org.slf4j.MDC.remove("batchId");
    org.slf4j.MDC.remove("correlationId");
}
~~~

This snippet requires an SLF4J `Logger` and a corresponding `executeBatch` method; it is **not a standalone program**. Removing the three keys works when this scope **owns** them and does not need to restore prior values.

If a logger sits deep inside a service, it automatically picks up MDC fields on the same thread without passing parameters into every method. However, if the layout does not print MDC, you still will not see them in the console output.

### 6.1. Logback Pattern for Batch Processing

~~~xml
<!-- Snippet in logback.xml, with ConsoleAppender. -->
<appender name="CONSOLE"
          class="ch.qos.logback.core.ConsoleAppender">
    <target>System.out</target>
    <encoder>
        <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level correlationId=%X{correlationId:-none} batchId=%X{batchId:-none} batchRunId=%X{batchRunId:-none} itemId=%X{itemId:-none} %logger{36} - %msg%n</pattern>
        <charset>UTF-8</charset>
    </encoder>
</appender>
~~~

`%X{key:-none}` is how Logback's `PatternLayout` prints an MDC key with a fallback value when absent. This snippet is only an **appender definition**; it must be attached to `<root>` or a `<logger>` in a complete configuration. Production setups should consider a JSON encoder so IDs become structured fields rather than plain text.

### 6.2. Do Not Let MDC Outlive Its Scope

A thread-pool worker thread can process hundreds of different batches over the lifetime of a JVM. If you write:

~~~java
// WRONG: an exception before the remove line will leave the context on the thread.
MDC.put("batchId", batchId);
processItem();
MDC.remove("batchId");
~~~

and `processItem()` throws an exception, `remove` never runs. Items from another batch on the same worker could carry the **stale `batchId`**, misleading investigations and risking cross-batch data confusion.

Always use `try/finally`. For nested scopes or when a framework has already populated MDC, **snapshot and restore the entire map** so you do not wipe out the caller's context.

### 6.3. Snapshotting and Restoring Context with SLF4J

~~~java
// Snippet: requires importing java.util.Map and org.slf4j.MDC.
Map<String, String> previous = MDC.getCopyOfContextMap();

try {
    MDC.clear();
    MDC.put("correlationId", correlationId);
    MDC.put("batchId", batchId);
    MDC.put("batchRunId", batchRunId);
    LOG.info("event=batch.started");
} finally {
    if (previous == null || previous.isEmpty()) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
~~~

`MDC.getCopyOfContextMap()` returns a **copy** of the current map, which may be `null`. `MDC.setContextMap(...)` replaces the map on the **current thread**. This snippet intentionally starts with a clean context; if you need to preserve a framework-provided `traceId`, you must design a merge/allowlist instead of clearing it unintentionally.

**Avoid this misconception:** SLF4J's `MDC.putCloseable(key, value)` works well with `try-with-resources` and removes the key automatically, but closing that scope **does not necessarily restore the previous value** of the key in nested scopes. Explicit snapshot/restore is still required when caller context exists.

## 7. Propagating Correlation Context Across Worker Threads and Processes

### 7.1. Why Doesn't It Automatically Cross an `ExecutorService`?

A thread pool reuses threads that already existed before the batch started. `MDC`/`ThreadLocal` on the submitting thread does not automatically appear on the worker thread. Sometimes the worker sees an **empty** context; other times (if cleanup was broken) it sees **stale** values from a previous task.

The correct workflow within a single JVM:

1. **Capture** the context on the submitting thread **right before enqueuing the task**.
2. Pass the snapshot along with the task.
3. On the worker, **save** the worker's existing context.
4. **Install** the task's snapshot on the worker before logging and running logic.
5. In `finally`, **restore** the worker's prior context, even if the task throws.

SLF4J wrapper pattern (Java snippet, requires appropriate imports):

~~~java
static Runnable withMdc(Runnable task) {
    java.util.Map<String, String> captured =
            org.slf4j.MDC.getCopyOfContextMap();

    return () -> {
        java.util.Map<String, String> before =
                org.slf4j.MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                org.slf4j.MDC.clear();
            } else {
                org.slf4j.MDC.setContextMap(captured);
            }
            task.run();
        } finally {
            if (before == null) {
                org.slf4j.MDC.clear();
            } else {
                org.slf4j.MDC.setContextMap(before);
            }
        }
    };
}
~~~

Usage:

~~~java
// Snippet within the scope where the batch MDC has been set.
executor.submit(withMdc(() -> {
    LOG.info("event=batch.item.started");
    processItem();
}));
~~~

Note: the wrapper must be created at **submit** time; if you capture after the calling thread has already cleared MDC, the worker will miss IDs. Never share a single mutable map across tasks and mutate it while tasks are running.

### 7.2. `CompletableFuture`, Schedulers, and Callbacks

`CompletableFuture.supplyAsync(...)`, `thenApplyAsync(...)`, and callbacks in many frameworks can execute on different threads. Propagating context to the first stage **does not guarantee** that subsequent stages will have the same MDC. Every execution boundary needs a wrapper for `Runnable`/`Supplier`/`Function` or a framework context-propagation facility.

Do not force an entire batch to run synchronously just to make MDC appear; calling `Future.get()` in the hands-on example below is only for **deterministic stdout**, not for high-throughput batch architecture.

### 7.3. When Workers Run in Another Process or JVM

`ThreadLocal`/MDC only exists within a single process and its adapter context. If a batch coordinator sends messages via Kafka/RabbitMQ/SQS or writes jobs to a database for another worker to pick up, you must **include `correlationId`/`batchId`/`batchRunId`/`itemId` in the message envelope/headers or durable metadata** according to the contract.

~~~json
{
  "commandType": "ProcessBatchItem",
  "correlationId": "corr-42",
  "batchId": "batch-42",
  "batchRunId": "run-1",
  "itemId": "item-B",
  "attempt": 1
}
~~~

This is an illustrative envelope. The worker reads and validates the IDs, sets up the logging scope, processes the item, records state, and cleans up. If the message is redelivered, separate idempotency/deduplication is required; preserving `correlationId` does not prevent duplicate processing.

### 7.4. Async Logging vs. Async Business Execution

An `AsyncAppender` or async logger uses a worker dedicated to **writing logs**, not a worker executing business logic. The logging backend can snapshot the log event's MDC/context before enqueuing so the IDs are printed accurately. That **does not propagate MDC to an `ExecutorService`, Kafka consumer, or `CompletableFuture`** running business code.

With async logging, you still need to consider queue-full behavior, drops, flushing, and shutdown so you do not assume every mandatory log was persisted.

## 8. Standalone Java 17 Example: Batch Resume, Retry, and Context Isolation

The following example uses **only JDK 17**, with no Maven and no external logging backend required. Because **JUL has no built-in MDC in the JDK**, we create a `ThreadLocal<CorrelationContext>` to demonstrate the **capture/install/restore** rules; `LogRecord` captures the context at event emission time. This is a **correlation context demo** and should not be mistaken for a built-in JUL MDC API.

Scenario:

- Logical batch `batch-42` has correlation ID `corr-42`.
- Run `run-1`: `item-A` succeeds on the first try; `item-B` fails transiently on attempt 1. The run finishes with outcome `partial`.
- Run `run-2`: resumes `item-B` at attempt 2 and succeeds. The run finishes with outcome `succeeded`.
- Both runs execute through the **same single-thread executor**, making it possible to detect context leakage.
- Finally, emit one event on the worker and one event on the main thread **outside the batch scope**; both must report `none` for the IDs.

### 8.1. Complete Code: `BatchCorrelationDemo.java`

~~~java
import java.io.IOException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class BatchCorrelationDemo {
    private static final Logger LOG =
            Logger.getLogger(BatchCorrelationDemo.class.getName());

    // Demo context: not a built-in MDC API in JUL.
    private static final ThreadLocal<CorrelationContext> CONTEXT =
            new ThreadLocal<>();

    private record CorrelationContext(
            String correlationId,
            String batchId,
            String batchRunId,
            String itemId,
            int attempt) {

        CorrelationContext item(String nextItemId, int nextAttempt) {
            return new CorrelationContext(
                    correlationId, batchId, batchRunId,
                    nextItemId, nextAttempt);
        }
    }

    private BatchCorrelationDemo() {
    }

    private static void restore(CorrelationContext previous) {
        if (previous == null) {
            CONTEXT.remove();
        } else {
            CONTEXT.set(previous);
        }
    }

    private static Runnable withContext(
            CorrelationContext captured, Runnable task) {
        return () -> {
            CorrelationContext workerBefore = CONTEXT.get();
            try {
                CONTEXT.set(captured);
                task.run();
            } finally {
                restore(workerBefore);
            }
        };
    }

    private static final class EventFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Object[] values = record.getParameters();
            CorrelationContext context =
                    (CorrelationContext) values[0];
            String outcome = (String) values[1];

            StringBuilder out = new StringBuilder();
            out.append(record.getLevel().getName());
            out.append(" correlationId=").append(context.correlationId());
            out.append(" batchId=").append(context.batchId());
            out.append(" batchRunId=").append(context.batchRunId());
            out.append(" itemId=").append(context.itemId());
            out.append(" attempt=").append(context.attempt());
            out.append(" event=").append(record.getMessage());
            out.append(" outcome=").append(outcome);

            if (record.getThrown() != null) {
                out.append(" errorType=").append(
                        record.getThrown().getClass().getSimpleName());
            }
            return out.append("\n").toString();
        }
    }

    private static void configureLogger() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler stdout =
                new StreamHandler(System.out, new EventFormatter()) {
                    @Override
                    public synchronized void publish(LogRecord record) {
                        super.publish(record);
                        flush();
                    }
                };
        stdout.setLevel(Level.ALL);
        LOG.addHandler(stdout);
    }

    private static void emit(
            Level level, String event, String outcome,
            Throwable error) {
        CorrelationContext captured = CONTEXT.get();
        if (captured == null) {
            captured = new CorrelationContext(
                    "none", "none", "none", "-", 0);
        }

        LogRecord record = new LogRecord(level, event);
        record.setParameters(new Object[] {captured, outcome});
        record.setThrown(error);
        LOG.log(record);
    }

    private static void submitAndAwait(
            ExecutorService executor,
            CorrelationContext context,
            Level level, String event,
            String outcome, Throwable error)
            throws InterruptedException, ExecutionException {

        Runnable task = withContext(context,
                () -> emit(level, event, outcome, error));

        Future<?> completed = executor.submit(task);
        completed.get();
    }

    private static void runBatch(
            ExecutorService executor, String runId,
            boolean firstRun)
            throws InterruptedException, ExecutionException {

        CorrelationContext before = CONTEXT.get();
        try {
            CorrelationContext batch = new CorrelationContext(
                    "corr-42", "batch-42", runId, "-", 0);

            CONTEXT.set(batch);
            emit(Level.INFO, "batch.started", "started", null);

            if (firstRun) {
                submitAndAwait(
                        executor, batch.item("item-A", 1),
                        Level.INFO, "batch.item.succeeded",
                        "succeeded", null);

                submitAndAwait(
                        executor, batch.item("item-B", 1),
                        Level.WARNING, "batch.item.failed",
                        "retryable", new IOException("temporary timeout"));

                emit(Level.WARNING, "batch.finished", "partial", null);
            } else {
                submitAndAwait(
                        executor, batch.item("item-B", 2),
                        Level.INFO, "batch.item.succeeded",
                        "succeeded", null);

                emit(Level.INFO, "batch.finished", "succeeded", null);
            }
        } finally {
            restore(before);
        }
    }

    public static void main(String[] args) throws Exception {
        configureLogger();

        ExecutorService executor =
                Executors.newSingleThreadExecutor();
        try {
            runBatch(executor, "run-1", true);
            runBatch(executor, "run-2", false);

            // Runs on the same worker, but no longer has the batch context.
            executor.submit(
                    () -> emit(Level.INFO, "worker.idle", "idle", null))
                    .get();

            // The main thread has also been restored.
            emit(Level.INFO, "main.idle", "idle", null);
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

### 8.2. Compile and Run

Save as **BatchCorrelationDemo.java**, then run:

~~~bash
javac -encoding UTF-8 BatchCorrelationDemo.java
java BatchCorrelationDemo
~~~

**Nine stdout lines produced by `EventFormatter`:**

~~~text
INFO correlationId=corr-42 batchId=batch-42 batchRunId=run-1 itemId=- attempt=0 event=batch.started outcome=started
INFO correlationId=corr-42 batchId=batch-42 batchRunId=run-1 itemId=item-A attempt=1 event=batch.item.succeeded outcome=succeeded
WARNING correlationId=corr-42 batchId=batch-42 batchRunId=run-1 itemId=item-B attempt=1 event=batch.item.failed outcome=retryable errorType=IOException
WARNING correlationId=corr-42 batchId=batch-42 batchRunId=run-1 itemId=- attempt=0 event=batch.finished outcome=partial
INFO correlationId=corr-42 batchId=batch-42 batchRunId=run-2 itemId=- attempt=0 event=batch.started outcome=started
INFO correlationId=corr-42 batchId=batch-42 batchRunId=run-2 itemId=item-B attempt=2 event=batch.item.succeeded outcome=succeeded
INFO correlationId=corr-42 batchId=batch-42 batchRunId=run-2 itemId=- attempt=0 event=batch.finished outcome=succeeded
INFO correlationId=none batchId=none batchRunId=none itemId=- attempt=0 event=worker.idle outcome=idle
INFO correlationId=none batchId=none batchRunId=none itemId=- attempt=0 event=main.idle outcome=idle
~~~

**Why is the output predictable?**

1. Only one worker thread is provided by `newSingleThreadExecutor()`, and each `Future.get()` waits for the previous task to finish, so item events appear in exact Java code order.
2. Runs `run-1` and `run-2` share `correlationId`/`batchId` but use different run IDs; `item-B` keeps its `itemId` across retries and increments `attempt` from 1 to 2.
3. `withContext(...)` captures the context built on the submitting thread, installs it on the worker before calling `emit`, and **restores `workerBefore` in `finally`**.
4. `emit(...)` captures an **immutable `CorrelationContext`** into the `LogRecord` before backend formatting; the formatter **does not read `ThreadLocal`** at format time. This is a safe design choice in case logging later moves to a backend with its own worker thread.
5. `record.setThrown(...)` attaches the `IOException` to the failed event; the demo formatter prints only `errorType` to keep stdout deterministic rather than printing the full stack trace. Production logging needs a layout that exposes the cause for investigation.
6. `runBatch(...)` restores the main thread's context in `finally`. The last two lines prove neither the main thread nor the worker still holds batch IDs outside the scope.

**Business-logic note:** this demo only **emits simulated events** and performs no real business I/O, transactions, checkpoints, or idempotency checks; therefore `batch.finished outcome=succeeded` in `run-2` is a result of the learning scenario, not proof that a real production batch committed every item.

**Concurrency note:** `Future.get()` only enforces deterministic ordering for learning. In a real parallel batch, log ordering across workers **is not guaranteed**, and business logic must never depend on logs arriving in ascending `itemId` order. Use properly scoped IDs, sequences, and counters when reconstructing progress.

### 8.3. Key Experiments to Try

1. Change `run-2` to `run-3`: only the second run's `batchRunId` changes; `correlationId` and `batchId` stay the same.
2. Change `batch.item.failed` to `batch.item.retry_scheduled` and try adding `nextRetryAt` to the structured event: this clarifies that a **retry was scheduled**, not merely that an error occurred.
3. Remove `restore(workerBefore)` in `withContext(...)` **only in your learning copy**: the `worker.idle` event can carry stale `item-B`/`run-2` values, demonstrating context leakage in a thread pool.
4. Remove `CONTEXT.set(captured)`: the worker no longer receives the batch's IDs; item logs may lack IDs or carry stale context.
5. Submit items across two workers without awaiting each task: log order may vary, but every event must still carry the right `correlationId`/`batchId`/`itemId`.
6. Have a task throw a real exception before completing: verify that `finally` still restores the context; handle `ExecutionException` in the coordinator rather than treating it as batch success.

## 9. On Retry, Restart, and Resume: Which IDs Should Be Kept?

### 9.1. Retry Within the Same Run

Example:

~~~text
correlationId=corr-42 batchId=batch-42 runId=run-1 itemId=item-B attempt=1 outcome=retryable
correlationId=corr-42 batchId=batch-42 runId=run-1 itemId=item-B attempt=2 outcome=succeeded
~~~

If this is the **same logical item** retried within the same execution, keep `correlationId`/`batchId`/`runId`/`itemId` and increment `attempt`. You can also log `reasonCode`, `retryDelayMs`, `retryPolicy`, and `error.type` for investigation.

### 9.2. Restart/Resume in Another Run

Example:

~~~text
correlationId=corr-42 batchId=batch-42 runId=run-1 itemId=item-B attempt=1 outcome=failed
correlationId=corr-42 batchId=batch-42 runId=run-2 itemId=item-B attempt=2 outcome=succeeded
~~~

In this lesson's convention, retrying after a restart increments `attempt` across the item's entire lifecycle. Another system might reset `attempt` per run and add `overallAttempt` or `retryCount`. **Never silently change a field's meaning across code branches.**

### 9.3. Message Replay Due to At-Least-Once Delivery

Kafka, RabbitMQ, or another queue may redeliver the same message if a consumer crashes before acknowledging. The redelivered message may carry the same `correlationId`/`batchId`/`itemId`, which is **not enough to conclude it was processed exactly once**.

The design needs:

- A durable business ID/key for the side effect to deduplicate.
- A commit/idempotency status check before reapplying the side effect.
- An ack/transaction/outbox policy suited to the system.
- Logging `redelivered`, `duplicateDetected`, or `skippedAsAlreadyProcessed` when meaningful.
- Counters distinguishing **attempt count** from **unique items** and **successful commits**.

For example, if an item is retried twice, the system may have three attempt logs but only **one succeeded item**. Dashboards must not count three attempt events as three processed transactions.

### 9.4. Cancelled or Timed-Out Batches

If a run is cancelled, timed out, or dead-lettered, log the exact outcome: `cancelled`, `timed_out`, or `dead_lettered`—do not collapse everything into `failed` if investigation or alerting workflows need to distinguish them. For mandatory audit logging, persist durable state first or coordinate with event emission to reduce inconsistency on crashes.

## 10. Chunking, Partitioning, and Fan-Out/Fan-In

### 10.1. Fan-Out Keeps Parent IDs and Adds Branch IDs

A batch split into three partitions:

~~~text
correlationId=corr-42 batchId=batch-42 runId=run-1 partitionId=P-0
correlationId=corr-42 batchId=batch-42 runId=run-1 partitionId=P-1
correlationId=corr-42 batchId=batch-42 runId=run-1 partitionId=P-2
~~~

Workers share the parent correlation IDs but have different `partitionId` values. When multiple items run concurrently, adding `itemId` and `attempt` prevents confusing one item's failure with another's.

If a partition must be rerun, depending on the design you can keep `partitionId` and increment `partitionAttempt`, or create a separate partition execution ID. Separate the **logical partition** from the **partition execution**, just like `batchId` and `batchRunId`.

### 10.2. Fan-In Aggregating Results

When workers finish, the coordinator can emit a summary event:

~~~json
{
  "eventName": "batch.finished",
  "correlationId": "corr-42",
  "batchId": "batch-42",
  "batchRunId": "run-1",
  "outcome": "partial",
  "itemsPlanned": 10000,
  "itemsSucceeded": 9700,
  "itemsFailed": 250,
  "itemsSkipped": 50,
  "durationMs": 124000
}
~~~

**Counter accuracy is the responsibility of the batch engine and business state**, not simply counting text lines. If an item has multiple attempts, `itemsFailed` must follow a clear definition: the number of items still failed when the run ended, or the number of failed attempts? Add a separate `attemptsFailed` field when needed.

### 10.3. Checkpoints and Progress

For long-running batches, checkpoint logs should include:

- `correlationId`/`batchId`/`batchRunId`.
- `checkpointId` or committed offset.
- processed/succeeded/failed/skipped counters at the checkpoint.
- consistently measured duration and throughput.
- a **log-safe** cursor/range containing no personal data or secrets.

Do not treat printing `checkpoint.saved` as equivalent to committing the checkpoint to storage. The log event should be emitted **after** the checkpoint save succeeds or under a verifiable transaction/event design; logging beforehand and crashing can reflect unpersisted state.

## 11. Correlation IDs with Spring Batch, Schedulers, and Message Consumers

### 11.1. Spring Batch

Spring Batch provides concepts such as `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext`, and job parameters. You can design a mapping:

- `batchId` ↔ logical business ID or a durable job instance key.
- `batchRunId` ↔ ID of a job execution.
- `stepId`/`stepName` ↔ step execution / step name when needed.
- `correlationId` ↔ workflow ID issued at the application boundary.

**This is a suggested mapping, not Spring Batch's default field names.** Check your identifying job parameters, restart policy, and how the framework stores execution metadata. Do not assume every `JobExecution` represents a new logical batch.

`ExecutionContext` and job metadata are better suited than `ThreadLocal` for **storing durable identifiers across restarts**. MDC is only for adding context to logs on the currently executing thread.

### 11.2. Schedulers

A scheduled task might have `jobName=nightly-reconcile` and `scheduleTime`, but each trigger needs a distinct `batchRunId`. If a schedule overlaps two executions, `jobName` alone is not enough to tell them apart.

`scheduledAt`, `startedAt`, and `finishedAt` are distinct milestones; to compute queue delay or duration, record each timestamp and unit explicitly rather than using log timestamps as a proxy for every phase.

### 11.3. Message Consumers

When a worker receives a message, it should:

1. Read the IDs from the message envelope/headers according to the schema.
2. Validate the IDs and determine whether the source is trusted.
3. Snapshot the consumer thread's current context.
4. Install the message's MDC/context, process, and log the outcome/`Throwable`.
5. Clean up/restore in `finally` before receiving the next message on the same thread.
6. Forward required IDs to downstream messages per contract, without blindly copying untrusted headers.

If a message has no `correlationId`, policy may generate a new ID, flag the missing upstream ID, and record a parent mapping if a link exists. Never silently reuse an old message's ID left in MDC.

### 11.4. Downstream Services and Tracing

If a batch calls downstream HTTP/gRPC services, it can pass the correlation ID via a trusted header or request field per contract. At the same time, the tracing system propagates **trace context** through its own mechanism. **Do not simply copy `correlationId` into `traceId`**: a trace ID must follow the tracing system's format and real trace/span semantics.

A long-running batch may span many traces, and one trace may include many spans within the same batch. `correlationId` serves as the long-lived investigation key linking traces to the logical batch, while `traceId` inspects a specific call path.

## 12. Avoiding Confusion Between Log Level, Event Code, and Batch Status

**A Correlation ID does not tell you whether an event is severe or successful.** Combine:

| Field | Responsibility |
| --- | --- |
| `correlationId` | Links events belonging to the same workflow |
| `eventCode`/`eventName` | Describes the registered event type |
| `level` | Severity of the event |
| `outcome` | Result of the item/run/batch at the time of logging |
| `batchStatus` | Durable status in the business engine (if present) |
| `error.type`/`error.code` | Categorizes failures for investigation |

For example, an attempt timeout may be `WARN` with `outcome=retryable`, while the batch ultimately ends as `succeeded`. Reusing a single `eventCode=BATCH_FAILED` for every retryable timeout can mislead dashboards into thinking the batch failed multiple times.

**Do not simply count `ERROR` logs by `correlationId`** to determine how many items failed: the same error may be logged by a service, a worker, and a coordinator, or a single item may fail across multiple attempts. Define distinct events for final outcomes, per-attempt events, and matching metrics.

## 13. Querying and Dashboards by `correlationId`

Assuming the system has ingested JSON with independent fields, the following queries are **pseudocode**, not exact syntax for Elasticsearch, Loki, Splunk, or SQL:

~~~text
-- View all logs belonging to a workflow:
FILTER correlationId = "corr-42"
SORT timestamp ASC

-- View only the run that encountered an issue:
FILTER batchId = "batch-42"
  AND batchRunId = "run-1"
SORT timestamp ASC

-- View an item retried across multiple runs:
FILTER batchId = "batch-42"
  AND itemId = "item-B"
SORT timestamp ASC

-- Count item attempts (not unique items):
FILTER eventName IN ("batch.item.started", "batch.item.failed")
GROUP BY batchId, itemId
~~~

These queries assume standardized field names, data within retention, and no dropped events at the collector. Each query engine has its own syntax, timezone handling, and indexing behavior.

### 13.1. Good Batch Investigation Questions

- Which logical batches had a `partial` outcome and were later resumed?
- Which run contained the first failure? Which partition/chunk/item?
- How many times was an item retried, and for what technical reason?
- How many **unique** items succeeded and were committed in total?
- What was the delay between enqueueing and starting the batch?
- Across which services/queues does this correlation ID appear?
- Are there signs of duplicate processing or idempotent skips?
- Are any logs missing `correlationId` because a boundary failed to apply context?

### 13.2. Cardinality and Metrics

`correlationId`, `batchId`, `batchRunId`, and `itemId` can take on huge numbers of values. They are great as **searchable log fields**, but should not be added by default as **time-series metric labels**. A metric such as:

~~~text
batch_items_processed_total{jobName="nightly-import",outcome="succeeded"}
~~~

has a bounded label set compared to attaching every `batchId`/`itemId`. Use metrics with cardinality-controlled labels, and use correlation IDs for investigation in logs and traces.

### 13.3. Which Data Source Is the Source of Truth?

- **Logs**: explain what happened, errors, and context.
- **Metrics**: aggregate throughput, latency, and retry/failure rates.
- **Tracing**: call/span relationships when instrumented.
- **Batch metadata/database**: durable state and commit/item outcomes when the business requires exact numbers.

Exact batch counts usually require reconciling against metadata/DB, especially when retries, crashes, duplicate deliveries, log sampling, or dropped queues occur.

## 14. Logging Failures and Preserving Causes

An item may encounter an `IOException` or a dependency error. When diagnostics are needed, log the full `Throwable` **at the responsible error-handling boundary**, along with `correlationId`/`batchId`/`runId`/`itemId` and `attempt`.

With SLF4J:

~~~java
// Snippet inside catch; MDC has been properly installed on the worker.
catch (java.io.IOException e) {
    LOG.warn("event=batch.item.retry_scheduled reason=dependency-timeout", e);
    scheduleRetry();
}
~~~

This snippet is only illustrative within a method that has `scheduleRetry` and a logging backend, not standalone Java source. For a batch with thousands of retries, you might log concise entries/metrics for expected retries and full traces on final failure or representative samples, **without losing diagnostic information or dropping mandatory audit events**.

When wrapping exceptions across layers, preserve the cause:

~~~java
// Snippet inside catch IOException.
throw new IllegalStateException("Cannot process batch item", e);
~~~

Do not just extract `e.getMessage()` into a new exception and discard the cause. With `try-with-resources`, suppressed exceptions can also matter; choose a formatter/JSON encoder that surfaces causes and suppressed exceptions per policy.

An `ERROR` record with the wrong correlation ID is worse than one missing an ID: it can point operators to **the wrong incident or customer**. Therefore, testing context isolation is just as important as testing context propagation.

## 15. Security and ID Integrity

### 15.1. A Correlation ID Is Not an Authentication Token

Knowing `correlationId=corr-42` does not prove the caller owns the batch or has permission to read its data. Batch status lookup APIs must still enforce **authentication and authorization** by account, tenant, and business permissions.

If a public response returns `correlationId` for support purposes, never turn that ID into a "log access password." Never use it as a substitute for permission checks.

### 15.2. Preventing Data Leaks Through ID Fields

- Use opaque IDs with no email, phone number, or token embedded.
- Enforce length limits and reject control characters and header spoofing.
- Do not log entire queue envelopes if they contain secrets.
- Restrict access to logs, archives, collectors, and runbooks.
- Define appropriate retention for batch-linking metadata and personal data.
- Use a JSON encoder that properly escapes untrusted strings; **escaping does not remove PII**.
- If a `tenantId` exists, verify that routing and search prevent cross-tenant viewing.

### 15.3. Context Leakage Is Both a Correctness and Privacy Risk

If a worker thread retains `tenantId` or `batchId` from a previous task, subsequent task logs can be tagged with the wrong tenant or batch. This is not merely hard to debug—it can corrupt alerting pipelines, investigation tools, or collector authorization routing. Always use `try/finally`, snapshot/restore, and thread-reuse tests.

## 16. Common Pitfalls with Correlation IDs and Batches

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Using one `jobName` as the correlation ID for all runs | Cannot distinguish concurrent runs | Separate IDs for workflow/batch/run |
| Generating a new correlation ID per item without a parent ID | Hard to view the whole batch | Keep `correlationId`/`batchId`, add `itemId` |
| Using the same ID for logical batch and run without a clear contract | Cannot separate restarts/resumes | Two fields with distinct lifecycles |
| Changing `itemId` on each retry | Miscounts unique items | Keep `itemId`, increment `attempt` |
| Counting attempt failures as final batch failures | Misleading dashboards/analytics | Separate per-attempt, per-run, and per-batch events |
| Arbitrarily using `correlationId` as an idempotency key | May wrongly block valid items | Scope idempotency keys to the specific side effect |
| Keeping IDs only in MDC without persisting to metadata | Link lost after restart/process handoff | Persist and propagate IDs durably |
| Forgetting context propagation to an executor | Workers have no IDs | Capture at submit, install at execute |
| Forgetting to restore MDC on workers | Next task inherits stale IDs | Restore snapshot in `finally` |
| Calling `MDC.clear()` deep inside a service | Loses caller-managed `traceId`/keys | Clear scope/ownership and restore |
| Assuming `AsyncAppender` propagates MDC to business executors | Business workers still lack IDs | Distinguish async logging from async tasks |
| Logging raw request headers as IDs | CRLF log injection, spoofed/oversized input | Trusted boundary + validation |
| Embedding tokens/emails in `correlationId` | Sensitive data leaks across systems | Use approved opaque IDs |
| Turning `requestId` into a metric label | Time-series explosion | Bounded labels; use IDs for log search |
| Using `batchId` as a per-item filename | Too many files or misrouting | Shared files / structured logging by field |
| Omitting a completion summary | Hard to tell partial/cancelled/succeeded apart | Summary event with counters and outcome |
| Logging completion before committing the checkpoint | False completion logs | Coordinate events with durable state |
| Assuming `correlationId` alone is enough for tracing | Missing call/span details | Add real tracing when needed |
| Logging `Throwable` at every layer | Duplicate incidents and log bloat | Choose responsible logging boundaries |
| Not testing item retries across multiple runs | Broken `attempt`, run ID, or linking | Test stateful retry/restart/resume |

## 17. Production Batch Implementation Checklist

1. **Define scope:** does `correlationId` link a single HTTP trigger, a workflow, or a logical batch across multiple runs?
2. **Define ID conventions:** how do `batchId`, `batchRunId`, `itemId`, `chunkId`/`partitionId`, `attempt`, and `correlationId` differ?
3. **Trusted ID source:** validate headers/inputs, generate an ID when missing, and never include secrets.
4. **Persist:** store `correlationId`/`batchId` with job metadata/messages so restarts remain traceable.
5. **Schema:** keep event field types and names consistent across JSON and collectors.
6. **Boundaries:** set logging context for the coordinator and every worker/task/message.
7. **Propagation:** capture context before submit; pass it to executors, callbacks, and other processes per contract.
8. **Cleanup:** restore in `finally` and test thread-pool reuse.
9. **Error handling:** preserve `Throwable`/cause on events needed for investigation; do not double-log every failure.
10. **Retry semantics:** keep the same ID for the same item, increment `attempt` per contract, and avoid double-counting.
11. **Idempotency:** design dedicated keys and durable state for business side effects.
12. **Checkpoints:** log outcomes only after committed state is confirmed.
13. **Metrics:** clearly define per-item/per-run/per-batch counters with cardinality-controlled labels.
14. **Security:** IDs must not grant unauthorized access; enforce permissions and retention on logs and metadata.
15. **Operational tests:** test concurrency, restarts, cancellations, duplicate deliveries, async exceptions, and collector drops.
16. **Monitoring:** watch for events missing IDs, mismatched IDs, stalled batches, retry spikes, duration, queue lag, and disk/ingest pressure.

## 18. Practice Exercises

1. **Distinguish:** a batch `B-42` runs twice as `R-1` and `R-2`. Which fields stay the same and which change under this lesson's convention?
2. **Java 17:** create `BatchCorrelationDemo.java`, run `javac`/`java`, and verify the nine stdout lines. Why do `worker.idle` and `main.idle` have `correlationId=none`?
3. **Retry:** `item-B` fails in `run-1` and succeeds in `run-2`. Why does `itemId` stay the same while `attempt` changes from 1 to 2?
4. **Context leak:** remove `restore(workerBefore)` in your learning copy. Predict how the `worker.idle` log will break and explain the impact when other jobs share the thread pool.
5. **SLF4J MDC:** write a `withMdc(Runnable)` wrapper that captures at submit and restores on the worker; compare it with only calling `MDC.put` in the coordinator.
6. **Distributed worker:** a coordinator produces messages for a Kafka consumer in another JVM. Which IDs should be in the envelope so the consumer can log and resume properly?
7. **Idempotency:** two identical messages for the same item are redelivered. Why doesn't the same `correlationId` prevent duplicate writes? Propose a key and commit/dedup mechanism.
8. **Structured schema:** write an NDJSON `batch.item.retry_scheduled` event with `attempt` as a number, `reasonCode`, and `retryDelayMs`, ensuring no tokens or raw payloads are included.
9. **Fan-out:** a batch has three partitions and 100 items. Distinguish `batchId`, `partitionId`, `itemId`, and `attempt`, and explain how to aggregate a summary without counting an item twice.
10. **Spring Batch:** explain the difference between `JobInstance` and `JobExecution`, then propose a mapping to `batchId`/`batchRunId` (without equating them by default).
11. **Metrics:** design processed/succeeded/failed/retried metrics and explain why `itemId`/`correlationId` should not be default labels.
12. **Security:** a client sends a correlation header containing CRLF and an email address. Write a handling policy and explain why the ID is not an access credential.
13. **Monitoring:** create a scenario where a batch is `partial` and then `succeeded` after a restart. Write a pseudocode query to view all logs by `correlationId` and another to view only `run-1`.
14. **Final outcome:** design a `batch.completed` event with counters from durable state; how does it differ from a single run's `batch.finished outcome=partial`?

## 19. Reference Documentation

- Logback Manual — Mapped Diagnostic Context: https://logback.qos.ch/manual/mdc.html
- SLF4J — MDC API: https://www.slf4j.org/api/org/slf4j/MDC.html
- Java SE 17 — `ExecutorService`, `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Spring Batch — Domain Language of Batch: https://docs.spring.io/spring-batch/reference/domain.html
- OpenTelemetry — Context propagation: https://opentelemetry.io/docs/concepts/context-propagation/
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

**Remember:** **A Correlation ID connects the logs of a workflow; `batchId`, `runId`, `itemId`, and `attempt` tell you which part of the workflow is being processed.** Define ID scopes clearly, persist and propagate IDs across every thread and process boundary, clean up MDC with `finally`, and distinguish **attempt**, **run**, and **logical batch** outcomes. A Correlation ID is an observability tool—not a replacement for idempotency, checkpoints, transactions, or access control. A solid design lets you investigate failures across retries and restarts while still measuring succeeded items accurately and preventing log cross-contamination between concurrent batches.