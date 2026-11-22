# Java Logging Performance Checklist: From Per-Call Cost to Production Pipeline

## 1. Purpose of the Checklist

The **Java Logging Performance Checklist** is a set of questions and verification checks to ensure a logging system is **useful enough for observability** without causing unacceptable costs in CPU, heap/GC, latency, I/O, network, queues, and storage. This is the **Java Logging summary**: learners must know not only how to write logger APIs, but also how to measure the impact of loggers, formatters, appenders, shippers, and backends on the application.

A "fast" system that drops all WARN/ERROR logs or loses audit logs is not a successful optimization. Conversely, logging every object, request body, and stack trace on every operation can degrade throughput and create security risks. The goal is to balance **usefulness, safety, reliability, and cost**.

**Checklist scope:**

- Java 17+; JUL (`java.util.logging`), SLF4J with Logback, Log4j 2.
- Logger API, levels/filters, parameterized logging, `Supplier`, and argument evaluation conditions.
- Encoders/layouts, exceptions, structured fields, MDC/ThreadContext.
- Synchronous vs. asynchronous appenders, queues, batching, drops, and shutdown.
- stdout/stderr, files, disk/rotation, network/OTLP/Collector, backend ingest, and queries.
- Benchmarks, load tests, profiling, metrics, budgets, security, and release gates.

**Foundational principle:** Every change must have a **baseline and re-measured results** in an equivalent environment. Increasing throughput while losing critical events or increasing p99 latency is a regression from an operational perspective.

## 2. Quick Pre-Release Checklist

Use the following checkboxes as a review gate. High-priority items are marked **Required** per this lesson's example policy; real projects must tie them to approved SLOs, threat models, logging contracts, and access controls.

- [ ] **Required:** Identify log classes that must be retained (security/audit/error) and classes that can be filtered/sampled (diagnostics).
- [ ] **Required:** Do not concatenate strings or serialize expensive payloads before DEBUG/TRACE calls that are usually disabled.
- [ ] **Required:** Use the template matching the API: JUL `{0}`, SLF4J/Log4j 2 `{}`; distinguish the formatter from argument evaluation.
- [ ] **Required:** Do not log tokens, passwords, raw headers/bodies, or PII outside policy, even when DEBUG is enabled.
- [ ] **Required:** Set bounds for queues, batches, event sizes, and total log volume.
- [ ] **Required:** Understand the policy when queues are full, exporters return 429/503, disks are full, or during shutdown/crash; do not implicitly promise zero loss.
- [ ] **Required:** Have metrics for dropped/rejected logs, queue depth, retries, exporter failures, and ingest lag.
- [ ] **Required:** Run throughput, p95/p99 latency, and allocation/GC checks with logging in the intended configuration.
- [ ] Fix or clearly record the backend, version, encoder, appender, log level, sink, and thread count in measurements.
- [ ] Alert on log storms, high-cardinality fields, repeated stack traces, and duplicate events.
- [ ] Include correctness checks: message, level, exception, correlation, sensitive data, and counts.
- [ ] Provide the ability to enable time-bounded diagnostic logging and automatically revert to the normal configuration.
- [ ] Have a rollback plan in case of performance/observability regressions after release.
- [ ] Have evidence that the pipeline through the Collector/backend still keeps critical logs searchable.

**Note:** This list is a starting point. Durability/audit requirements cannot be solved by optimizing the logger API alone; they must be enforced at the appropriate storage/workflow layer.

## 3. Choose Measurement Targets Before Optimizing

Explicitly state **which metrics are allowed to degrade and what level is unacceptable**.

| Category | Metric | Measurement Goal |
| --- | --- | --- |
| Application | Requests/s or jobs/s | Do not reduce throughput beyond budget |
| Application | p50/p95/p99 request latency | Do not increase tail latency due to I/O or queues |
| CPU | CPU utilization, cycles spent formatting | Find logging-related hot spots |
| Heap/GC | Allocated bytes/op, young GC rate, pause time | Check string/object churn |
| Logging | Log calls/s by level, filtered/s, accepted/s | Know how many logs are actually emitted |
| Logging | Message bytes/event, bytes/s | Measure encoder and sink impact |
| Async | Queue occupancy, enqueue wait, drop/discard | Identify saturation |
| Sink | File write latency/throughput, stdout blocking | Find I/O bottlenecks |
| Collector | Receive/refused, export/sent/failed, retries | Know whether records leave the pipeline |
| Backend | Ingest lag, indexed/queryable records, indexing errors | Distinguish "sent" from "stored" |
| Safety | Secret leaks, data classification, audit completeness | Ensure optimization does not break contracts |

**Measure against realistic workloads:** a cache-read route and a batch job processing 100,000 records differ in logging intensity. A single-threaded benchmark with a simple INFO statement can hide production contention. Also test with 1, 4, 16, or the number of concurrent workers matching real deployment; do not treat those numbers as universal thresholds.

Establish a baseline **before changing** encoders, log levels, queue sizes, or async modes. Every result must record the JDK version, JVM flags, machine/container CPU limits, GC, logging dependencies, output sink, volume, test date, and measurement methodology.

## 4. Data Path Map and Where Costs Arise

~~~text
Business code
    │ argument evaluation, toString/serialization
    ▼
Logger API / facade
    │ level, markers, filters
    ▼
Logging event
    │ template + parameters + MDC + exception
    ▼
Formatter / JSON encoder
    │ CPU, allocations, stack trace processing
    ▼
Sync handler / async queue
    │ lock/contention, enqueue, block, discard
    ▼
Console / rolling file / network exporter
    │ syscall, disk, stdout buffering, TLS/network
    ▼
Container runtime / shipper / Collector
    │ parse, multiline, enrich, batch, retry
    ▼
Backend / index / storage
    │ ingest, indexing, retention, query
~~~

Each layer can introduce different costs. If a log call is fast but the collector queue grows to the point of dropping events, benchmarking only the API will **report great numbers while the system becomes unreliable**. If a synchronous appender performs slow I/O on the request thread, p99 latency can spike even when CPU usage is low.

**Clearly define measurement boundaries:**

- **Caller cost:** time spent at the logger call on the business thread.
- **Encode cost:** time to produce text/JSON from a LogEvent.
- **Enqueue cost:** cost to push into an async queue, which may block when full.
- **Delivery/ingest cost:** up to the Collector/backend, usually asynchronous.
- **Total application cost:** request/worker throughput and tail latency.
- **Operational cost:** bytes/s, index size, storage cost, data risk, and investigation time.

An approach that speeds up the caller using async may **merely shift** CPU/memory/I/O to another thread rather than eliminating them.

## 5. API Checklist: Avoid Building Strings When the Level Is Disabled

Anti-pattern:

~~~java
// SLF4J/Log4j 2: string concatenation before the logger receives the argument.
log.debug("order=" + orderId + " state=" + expensiveState());
~~~

Even when DEBUG is off, Java still evaluates `expensiveState()`. Modern JDK string concatenation optimizations are not allowed to eliminate calls that have observable side effects.

Prefer this when values are already available:

~~~java
// SLF4J or Log4j 2.
log.debug("order={} state={}", orderId, state);
~~~

**But do not assume everything is lazy:**

~~~java
// Still evaluates expensiveState() BEFORE Logger.debug runs.
log.debug("order={} state={}", orderId, expensiveState());
~~~

When an argument is expensive, use a guard:

~~~java
if (log.isDebugEnabled()) {
    log.debug("order={} state={}", orderId, expensiveState());
}
~~~

Or the SLF4J **2.x Fluent API**:

~~~java
log.atDebug()
        .addArgument(orderId)
        .addArgument(() -> expensiveState())
        .log("order={} state={}");
~~~

These snippets require a defined logger and domain functions and **do not run on the JDK alone**; `log.atDebug()` here belongs to SLF4J 2.x. For Log4j 2, use the Supplier overloads/APIs appropriate for your version. For JUL:

~~~java
// JUL uses {0}, not SLF4J's {}.
LOG.log(java.util.logging.Level.FINE, "order={0}", orderId);

// Defer computing the entire message:
LOG.fine(() -> "state=" + expensiveState());
~~~

**Detailed checklist:**

- [ ] Do not call `String.format(...)`, `MessageFormat.format(...)`, JSON serializers, or expensive `toString()` methods in DEBUG/TRACE arguments before checking the level.
- [ ] Audit every `log.debug("x={}", expensive())` call: placeholders defer **formatting**, not **argument evaluation**.
- [ ] Do not place business side effects inside expressions used solely for logging.
- [ ] Only use guards/Suppliers where they provide real benefit; for already-available primitives/immutables, a template is usually sufficient.
- [ ] A level guard does not guarantee that every downstream filter/appender will accept the event; do not advertise it as a transaction guarantee.

## 6. How JUL, SLF4J, and Log4j 2 Differ at Measurement Points

| API | Standard Placeholders | Deferred Message/Argument | Layers to Test |
| --- | --- | --- | --- |
| JUL (JDK 17) | `{0}`, `{1}` via `MessageFormat` | `Logger.fine(Supplier<String>)`, `log(Level, Supplier<String>)` | `LogRecord`, `Handler`, `Formatter` |
| SLF4J 1.7 facade | `{}` | Parameterized; guarded expensive calculations | Provider/Logback/Log4j 2 backend |
| SLF4J 2.x | `{}` | Fluent `addArgument(Supplier<?>)` | `LoggingEventBuilder` + provider |
| Logback Classic | Follows SLF4J | Backend has its own layouts/async appenders | `ILoggingEvent`, appender, and encoder |
| Log4j 2 API/Core | `{}` with standard parameterized messages | Supplier APIs, async components | `LogEvent`, message factory, layout/appender |

Do not benchmark "SLF4J" without recording the **provider/backend**. SLF4J is a facade; the actual cost also depends on Logback or Log4j 2, pattern/JSON encoders, filters, and sinks. Avoid concluding that one backend is always faster than another based on non-equivalent microbenchmarks.

**Checklist:**

- [ ] Logger names, hierarchy, and effective levels are correct.
- [ ] The appender/handler layer also has appropriate filters/level thresholds.
- [ ] No additivity/parent handler configuration produces duplicate output.
- [ ] In tests, do not mutate the JVM-wide root logger and affect other tests.
- [ ] The logging framework/version and load test thread count match the expected runtime.
- [ ] Do not confuse `LogRecord.getMessage()` (the template) with the text after `Formatter.formatMessage`.

## 7. Standalone Java 17 Example: Checking Wasted Work When FINE Is Off

This is a runnable program that **requires no external libraries beyond JDK 17**. It uses `AtomicInteger` to count method invocations and does not claim to be a speed benchmark. The test verifies:

1. When `FINE` is disabled, string concatenation and direct argument calls still run **10 times** across 5 iterations.
2. `Supplier` and `isLoggable` **do not invoke** the lazy function when `FINE` is disabled.
3. When `FINE` is enabled, the Supplier is invoked and the message reaches the in-memory `Handler`.
4. JUL formats `{0}`, `{1}` properly via `Formatter.formatMessage`.
5. The Handler can capture 2 events without depending on console, file, network, or machine speed.

### 7.1. Create LoggingPerformanceChecklistLab.java

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingPerformanceChecklistLab {
    private static final Logger LOG = Logger.getLogger("lab.logging.performance");
    private static final AtomicInteger EAGER_CALLS = new AtomicInteger();
    private static final AtomicInteger LAZY_CALLS = new AtomicInteger();

    private static String eagerValue() {
        return "eager-" + EAGER_CALLS.incrementAndGet();
    }
    private static String lazyValue() {
        return "lazy-" + LAZY_CALLS.incrementAndGet();
    }

    record Captured(Level level, String rendered) {}

    static final class CapturingHandler extends Handler {
        private final List<Captured> events = new ArrayList<>();
        private final Formatter messageOnly = new Formatter() {
            @Override public String format(LogRecord record) {
                return formatMessage(record);
            }
        };
        CapturingHandler() { setLevel(Level.ALL); }
        @Override public void publish(LogRecord record) {
            if (!isLoggable(record)) return;
            events.add(new Captured(
                    record.getLevel(), messageOnly.format(record)));
        }
        @Override public void flush() {}
        @Override public void close() {}
        List<Captured> snapshot() { return List.copyOf(events); }
    }

    static void require(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        CapturingHandler sink = new CapturingHandler();
        boolean oldParent = LOG.getUseParentHandlers();
        Level oldLevel = LOG.getLevel();
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(sink);
        try {
            for (int i = 0; i < 5; i++) {
                LOG.fine("concat=" + eagerValue());
                LOG.log(Level.FINE, "param={0}", eagerValue());
                LOG.fine(() -> "supplier=" + lazyValue());
                if (LOG.isLoggable(Level.FINE)) {
                    LOG.fine("guard=" + lazyValue());
                }
            }
            require(EAGER_CALLS.get() == 10, "eager arguments");
            require(LAZY_CALLS.get() == 0, "disabled Supplier/guard");
            require(sink.snapshot().isEmpty(), "disabled records");
            System.out.printf(
                    "DISABLED eagerCalls=%d lazyCalls=%d emitted=%d%n",
                    EAGER_CALLS.get(), LAZY_CALLS.get(), sink.snapshot().size());

            LOG.setLevel(Level.FINE);
            LOG.fine(() -> "supplier=" + lazyValue());
            LOG.log(Level.INFO, "order={0} state={1}",
                    new Object[]{"ORD-42", "PAID"});
            List<Captured> events = sink.snapshot();
            require(events.size() == 2, "enabled event count");
            require(events.get(0).level() == Level.FINE
                    && events.get(0).rendered().equals("supplier=lazy-1"),
                    "enabled Supplier message");
            require(events.get(1).level() == Level.INFO
                    && events.get(1).rendered().equals(
                            "order=ORD-42 state=PAID"),
                    "parameterized JUL rendering");
            System.out.printf(
                    "ENABLED eagerCalls=%d lazyCalls=%d emitted=%d%n",
                    EAGER_CALLS.get(), LAZY_CALLS.get(), events.size());
            System.out.println("LAST=" + events.get(1).rendered());
        } finally {
            LOG.removeHandler(sink);
            LOG.setUseParentHandlers(oldParent);
            LOG.setLevel(oldLevel);
            sink.close();
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 LoggingPerformanceChecklistLab.java
java LoggingPerformanceChecklistLab
~~~

**Exact stdout:**

~~~text
DISABLED eagerCalls=10 lazyCalls=0 emitted=0
ENABLED eagerCalls=10 lazyCalls=1 emitted=2
LAST=order=ORD-42 state=PAID
~~~

**Stderr:** empty; **exit code:** `0` when assertions pass.

### 7.2. Valid Conclusions from the Lab

- Five iterations with two eager calls per iteration: `5 × 2 = 10`. Because `FINE` is disabled, **no events reach the handler**, yet both functions still ran.
- Supplier and guard only do work when the level allows it; during the disabled phase they did not execute.
- When FINE is enabled, the Supplier runs once, and the first event is `supplier=lazy-1`.
- The second event is `INFO`, and the formatter renders the template `order={0} state={1}` as `order=ORD-42 state=PAID`.
- The results **do not measure allocations, nanoseconds/op, or throughput**. The code runs synchronously on a single thread with an in-memory sink; this is a **correctness test for lazy evaluation**, and cannot be used to claim how fast Logback/Log4j 2, stdout, or an exporter is.

**Concurrency warning:** `ArrayList` in `CapturingHandler` is a single-threaded fixture. If writing a multi-threaded load test, you need a thread-safe collector, data snapshots, and appropriate completion barriers; do not read an unsynchronized list and infer correctness.

## 8. Message Construction Cost, StringBuilder, and JDK 17

A common code review mistake is changing:

~~~java
log.debug("id=" + id + " state=" + state);
~~~

to:

~~~java
log.debug(new StringBuilder().append("id=").append(id)
        .append(" state=").append(state).toString());
~~~

This **does not solve** eager message construction before the logger call. Modern JVMs/JDKs optimize string concatenation; allocation counts cannot be inferred merely from the number of `+` operators. The right optimization is **not doing wasted work**:

~~~java
log.debug("id={} state={}", id, state); // SLF4J/Log4j 2
~~~

If `state` requires calling `expensiveState()`, use a guard/Supplier. `String.format`, `MessageFormat.format`, JSON serialization, `Arrays.deepToString`, `Collectors.joining`, and custom `toString()` methods are also evaluated eagerly if called directly.

**Case-by-case evaluation:**

- Already-available `String` values: templates are sufficient in most cases.
- Primitives/small objects: varargs/boxing and logger method overhead may exist; measure if the hot path is especially sensitive.
- Large/mutable objects: do not dump the entire object just for investigation; use an allowlisted summary with length limits.
- Functions that read files/DB/network: **do not perform this work just to log DEBUG** unless designed/guarded and the impact is evaluated.
- Exceptions: pass `Throwable` to the proper overload; do not build strings from `exception.toString()` or stack traces on the caller side.

Do not turn every `log.debug` into a verbose `if` block when arguments are cheap. Keep code readable and use a profiler to focus on hot spots.

## 9. Log Categories and Appropriate Emission Levels

| Event Category | Policy-Appropriate Level | Performance Trade-off |
| --- | --- | --- |
| Rare, meaningful lifecycle events | INFO | Useful for diagnostics, moderate volume |
| Recoverable abnormal conditions | WARN/WARNING | Do not spam on every retry loop |
| Impactful failures | ERROR/SEVERE | Keep necessary exception/correlation, avoid duplicates |
| Internal branch/variable details | DEBUG/FINE | Enable purposefully and with bounds |
| Very detailed steps in loops/IO | TRACE/FINER/FINEST | Can be extremely high volume; usually off |
| Critical security/audit | Dedicated channel/event schema per policy | Do not rely solely on DEBUG level |

**Do not optimize by turning off all ERROR/AUDIT logs.** If the business requires mandatory trails, choose a durable recorder/stream with appropriate retention and protection. Console logs may be best-effort; do not replace a transactional outbox/audit store when transactional delivery is required.

**Checklist:**

- [ ] Do not emit INFO inside an inner loop for each item if only summary/batch statistics are needed.
- [ ] The same exception is not logged as ERROR across service, controller, and worker consecutively if the contract requires only one logical failure.
- [ ] Retry attempts are represented with `attempt`/`reasonCode` and rate-limited if they could cause a storm.
- [ ] Critical events remain present under the production configuration (levels/filters/sampling).
- [ ] Dynamic level changes have an approver, scope, expiration, and revert mechanism.

## 10. Cost in Hot Loops and N+1 Logging

Example:

~~~java
// Anti-pattern in a high-volume processing loop.
for (Order order : orders) {
    log.info("processing order={}", order.id());
    process(order);
}
~~~

This is illustrative code assuming `orders`, `Order`, `log`, and `process` are defined. If each batch processes 100,000 orders, it generates at least 100,000 INFO events, not counting retries, exception logs, and infrastructure logs.

An alternative depending on the goal:

~~~java
long processed = 0, failed = 0;
for (Order order : orders) {
    try {
        process(order);
        processed++;
    } catch (RecoverableOrderException e) {
        failed++;
        // Only log per-item if needed for investigation and permitted.
        // Keep a safe order reference/reason code in the error branch.
    }
}
log.info("batch processed={} failed={}", processed, failed);
~~~

This snippet requires domain types `Order`, `RecoverableOrderException`, and `process`; it is not a standalone program. In production code, explicitly decide retry behavior, exception handling, and business invariants before copying.

**Checklist:**

- [ ] Measure **events/business operation** at peak, not just average.
- [ ] Use batch/window summaries for aggregate information.
- [ ] Use metrics for counters/histograms; use logs for events with human-readable context.
- [ ] Do not sample audit/security logs that policy requires in full.
- [ ] Have a way to enable bounded diagnostics by service/route/trace to investigate a specific case.
- [ ] Do not replace persisting business state with a "batch succeeded" log when durability is required.

## 11. Log Format: Text, JSON, and Structured Events

A simple text pattern is often cheaper than a full-featured JSON encoder **in some workloads**, but total cost cannot be concluded from caller CPU alone. JSON enables field-level querying and reduces downstream regex parsing, but can incur:

- Conversion of object values, dates/times, numbers, and exceptions.
- Escaping Unicode/quotes/newlines and field validation.
- Generating many keys/metadata per event.
- Redacting/masking sensitive data.
- Mapping MDC/ThreadContext, markers, and key-value pairs.
- Increased raw bytes, index cardinality, or storage size.

Example structured event:

~~~json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "service.name": "orders-api",
  "severity": "WARN",
  "event.code": "DEPENDENCY_TIMEOUT",
  "trace_id": "0123456789abcdef0123456789abcdef",
  "reason_code": "DB_TIMEOUT",
  "attempt": 2,
  "duration_ms": 250
}
~~~

**This is illustrative JSON**, which does not mean this raw object is already OTLP. When using OpenTelemetry, `service.name` typically lives in the Resource, severity has `SeverityText`/`SeverityNumber`, and event fields may reside in attributes; they must be mapped properly through the bridge/collector.

**JSON/encoder checklist:**

- [ ] The encoder supports UTF-8 and standard escaping; never manually concatenate raw input into JSON.
- [ ] Keep event codes stable, limit extraneous fields, and version the schema when needed.
- [ ] Do not serialize entire DTOs to "save writing fields."
- [ ] Measure bytes/event before and after switching to structured logs.
- [ ] Test types: `attempt` as a number, `duration_ms` as a number, rather than forcing everything into strings.
- [ ] Test privacy on the actual encoder output, not just mocked events.
- [ ] Verify the parser/Collector shares the same schema/version to avoid rejections or field explosion.

## 12. Stack Traces: Cost and Investigative Value

A `Throwable` can be formatted into a multi-line stack trace, including causes and suppressed exceptions. If repeated on every retry or inside a loop, volume and CPU usage can become very large.

~~~java
// Pass Throwable so the backend handles it with proper structure.
log.error("request failed code={} attempt={}",
        safeReasonCode, attempt, failure);
~~~

This snippet is for SLF4J/Log4j 2 with `log` and variables already in scope. Check overloads/versions so `failure` is actually treated as a Throwable rather than an unintended format argument. For JUL:

~~~java
LOG.log(java.util.logging.Level.SEVERE,
        "request failed", failure);
~~~

**It is discouraged** to concatenate `failure` or its stack trace into a string and call `log.error("... " + failure)`: this easily loses cause information, increases eager work, and may leak data via `Throwable.getMessage()`.

**Checklist:**

- [ ] One logical failure only produces as many stack traces as genuinely needed.
- [ ] On frequent retries, use reason codes/counts/metrics instead of printing full stack traces every time unless policy requires it.
- [ ] Do not strip all exceptions just to save bytes if investigations need the cause.
- [ ] Limit log storms, size, and access permissions, but do not truncate away essential details without a marker.
- [ ] Check data minimization in messages, causes, and suppressed exceptions.
- [ ] Measure CPU/allocated bytes of exception layouts with logging enabled.

## 13. MDC/ThreadContext: Benefits and Overhead

MDC in SLF4J/Logback and ThreadContext in Log4j 2 provide context such as `trace_id`, `request_id`, and `tenant_ref` (when permitted). Context speeds up log search, but has overhead for updates, copying/propagation, and serialization.

With SLF4J:

~~~java
// Within a request scope; slf4j-api must be included in dependencies.
try (org.slf4j.MDC.MDCCloseable close =
             org.slf4j.MDC.putCloseable("request_id", safeRequestId)) {
    processRequest();
}
~~~

This is not a standalone snippet; it requires `processRequest` and `safeRequestId`. Note that `MDC.putCloseable` restores/removes the key on close per the API, but if code modifies the same key in between, read the semantics carefully and test your provider. With thread pools/reactive/async tasks, **MDC does not automatically propagate across all boundaries**; context must be passed/snapshotted according to the framework.

**Checklist:**

- [ ] Context contains only useful, allowlisted fields and no PII/secrets.
- [ ] Do not put a 100 KB JSON payload into MDC so every event repeats it.
- [ ] Clean up at the end of the scope to avoid leaking context between requests on the same thread.
- [ ] Context propagation is tested for executors, CompletableFuture, reactive pipelines, and message consumers.
- [ ] Do not assume `trace_id` is a low-cardinality metric label.
- [ ] Measure bytes/event and latency when adding multiple MDC/ThreadContext fields.
- [ ] Do not read the current consumer's `ThreadLocal` context and assume it is still valid when rendering on an async worker.

## 14. Synchronous Logging: When the Request Thread Writes to the Sink

In sync mode, a log call may wait on:

- Locks or contention inside the appender/handler.
- Formatters/encoders processing JSON, exceptions, and timestamps.
- Stream/file writes, flushes, and syscalls.
- Disk/network buffers or stdout pipes when the consumer is slow.
- File rollovers, compression, or permission errors depending on the backend.

**Do not infer from the name "sync" that fsync or remote commit has occurred.** `Writer.flush()`, `OutputStream.flush()`, and `FileChannel.force(...)` have different durability guarantees and still depend on the filesystem/storage. Flushing an appender does not prove the collector has indexed the event.

**Checklist:**

- [ ] Measure p95/p99 latency on request threads with INFO/WARN/ERROR enabled.
- [ ] Use near-production load tests with a real sink; do not benchmark logging to `/dev/null` and claim I/O is safe.
- [ ] Check latency spikes during rotation and peak log bursts.
- [ ] Cap logging per request/loop to avoid blocking bursts.
- [ ] When a sink fails, know whether the handler drops, reports errors, throws, blocks, or retries.
- [ ] Do not enable flush-per-record just for "safety" without understanding the cost and durability semantics.
- [ ] Do not ignore that container console output can block if the runtime log reader is slow.

## 15. Async Logging: Fast at the Caller Is Not the Whole System

Async appenders/loggers typically push events onto a queue for a worker to process. This can reduce the time request threads wait on formatting/I/O, in exchange for:

- Queue/worker memory and CPU.
- Enqueue/dequeue contention and cache effects.
- Delay from event time to sink.
- Full queues causing events to be discarded/blocked or falling back to sync per policy.
- Loss of pending events on `Runtime.halt`/SIGKILL/process crash.
- Snapshot risks for mutable arguments/context and deferred rendering.

~~~text
Request threads
    └─ log(event) → bounded queue ─┐
                                  ▼
                             async worker
                                ├─ format/encode
                                └─ write stdout/file/export
                                       │
                                       ▼
                                   Collector
~~~

**Async checklist:**

- [ ] Know the queue capacity and average/max event size.
- [ ] Know the discard-by-level, blocking, or fallback policy when the queue is full.
- [ ] Have metrics for queue depth, enqueue wait, drops/discards, and worker errors.
- [ ] Load test both short bursts and sustained load, not just steady-state throughput.
- [ ] After enqueuing, an event may not be emitted yet; tests must use proper barriers/drains/awaits.
- [ ] Have a shutdown lifecycle with enough time to drain; do not expect flushing on SIGKILL.
- [ ] Include sink failure and disk-full cases to test retries/drops.
- [ ] Test context snapshots and mutable parameters so logged content cannot mutate after emission.

**Do not make the queue unbounded** to avoid drops. An oversized queue increases heap pressure, OOM risk, and **ingestion lag**, masking downstream issues. You must explicitly define the policy when all events cannot be retained.

## 16. Logback AsyncAppender and Configuration Checks

In **Logback Classic**, `AsyncAppender` wraps another appender and pushes events onto a queue. A minimal learning configuration (requires Logback and a properly configured application):

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>1024</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>5000</maxFlushTime>
        <appender-ref ref="CONSOLE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
~~~

**Do not copy this config as a production default.** The values 1024/5000 ms are **illustrative** and must be sized for your throughput, tail latency, memory, and delivery policy. `discardingThreshold=0` disables discarding based on remaining capacity in common Logback configurations; it does **not** mean the queue cannot lose events if the process dies, the appender fails, or capacity is exhausted.

With Logback Classic, understand that:

- `queueSize` limits the number of queued events.
- `neverBlock=false` typically causes enqueue to **block when the queue is full**, increasing request latency while reducing drops at that layer.
- `neverBlock=true` may drop events when the queue is full instead of blocking the caller.
- `discardingThreshold` controls discarding lower-severity events when the queue is nearly full; defaults/behavior may vary by version. Test semantics against your exact runtime version.
- `maxFlushTime` limits how long shutdown waits for the worker to drain the backlog; it does **not** guarantee durability on kill/power loss.
- `AsyncAppender` is not a durable broker; events still in RAM can be lost.

**Practical testing:** Generate large volumes of DEBUG/INFO/WARN/ERROR events; measure queue depth, drops, p99, memory, and final emitted counts per level; test graceful stop and forced kill separately.

## 17. Log4j 2 AsyncAppender and Async Loggers

Log4j 2 has two distinct mechanisms:

- **AsyncAppender:** receives LogEvents via a queued appender.
- **Async Loggers:** asynchronous processing using a ring buffer/Disruptor depending on configuration and version.

Do not treat them as equivalent in benchmarks. Even with the same logger API, backend async mode, Disruptor dependency, queue size, wait strategy, location information, and layout can all change results.

**Checklist:**

- [ ] Explicitly choose either AsyncAppender or Async Loggers; avoid accidentally stacking multiple async layers/queues.
- [ ] Verify the configuration and required `log4j-core`/`disruptor` dependencies for your version.
- [ ] Measure queue/ring buffer utilization, blocked producers, drops, or errors when full.
- [ ] Measure throughput and latency at both the caller **and** when the sink receives the event.
- [ ] Do not enable `includeLocation`/caller location unless needed and its stack-capture overhead is measured.
- [ ] Depending on `immediateFlush`, batch/flush, and shutdown timeout settings, evaluate the event loss window.
- [ ] Verify `ThreadContext` and immutable event snapshots across async boundaries.
- [ ] Do not compare a warmed-up AsyncLogger sample against a sync appender writing to a network file and conclude one is "universally faster."

**Important:** Defaults and behavior can change across Log4j 2 versions, configurations, and appender targets. Consult the documentation for your project's exact version and test the actual deployed artifact.

## 18. stdout/stderr, Container Runtimes, and Blocking

In Kubernetes/containers, a common pattern is **writing JSONL/text to stdout/stderr** for a runtime/agent to collect. This is simpler than managing multiple files inside a container, but has its own costs:

- Console writes are still I/O; pipes/readers can be slow or block.
- The runtime may add CRI wrappers, split partial lines, and rotate logs at size limits.
- Writing a multi-line stack trace may cause the agent to create multiple records if the parser does not reassemble them.
- A JSONL line with unescaped quotes/newlines can break event boundaries.
- Sidecars/agents also consume CPU, disk, and network—they are not free.
- If you ship both a file **and** stdout containing the same event, the backend may count duplicates.

**Checklist:**

- [ ] Write to the intended stream/formatter; do not assume stderr means ERROR in every logger.
- [ ] Test maximum line length, CRI partials, Unicode, newlines, and stack trace parsers.
- [ ] Measure stdout bytes/s and runtime disk usage at peak.
- [ ] Ensure the node agent keeps up before local rotation/TTL deletes files.
- [ ] Alert when the log filesystem nears full or the shipper backlog grows.
- [ ] Do not use `kubectl logs` as a centralized retention store; use a backend for long-term queries.
- [ ] Do not send sensitive debug output to stdout when many users have downstream read access.

## 19. File Logging: Buffering, Rotation, Compression, and Disk

File appenders can fit VMs/bare-metal and environments needing local logs, but you must account for:

- Write/flush latency, thread contention, and buffer sizes.
- Time/size-based rollover and archive compression.
- File count and total bytes kept locally; disk full and inode exhaustion.
- File permissions, rotation while an agent is tailing, rename vs. copytruncate.
- Storage errors and the appender's error-reporting policy.
- Local retention vs. backend retention/snapshots.

**Do not confuse mechanisms:**

- JUL `FileHandler(limit,count)` rotates by file size/count, **not by retaining `count` days**.
- Logback `maxHistory` controls the number of archive periods, and `totalSizeCap` may delete earlier than expected if the size cap is reached.
- Log4j 2 RollingFile has rolling strategies and a Delete action; `IfLastModified` checks the file's mtime, not individual event timestamps.
- Archive compression can spike CPU at rollover, so benchmarks must cover rollover periods.
- Deleting local files does not delete events already in the backend; deleting a backend index does not automatically clear queues/backups/exports.

**Checklist:** Define retention/rotation clearly, test file access and shipper checkpoints, disk watermarks, cleaning job ownership, and behavior when nearly full. Do not truncate an active audit file as a quick fix without following preservation and approval procedures.

## 20. Network Exporters, OTLP, Retries, and Pipeline Latency

When a Java app or agent sends logs over HTTP/gRPC/OTLP, costs lie in TLS, batching, connection pools, retries, queues, and payload size. A logger call can return quickly while downstream falls hours behind.

~~~text
Java app logs
   → OTLP exporter or stdout/file shipper
   → Collector receiver
   → processors (parse/filter/batch/enrich)
   → exporter retry/queue
   → backend ingest/index
~~~

**Checklist:**

- [ ] Clarify the path: raw JSONL stdout must go through an agent/filelog parser; do **not** send it as an OTLP request and expect the receiver to understand it.
- [ ] Measure event timestamp → Collector observed timestamp → backend searchable timestamp; account for clock skew.
- [ ] Configure timeouts, backoff, queue caps, auth/TLS, and handling for HTTP 429/503.
- [ ] Have a rule for HTTP 400 invalid schema: reject/quarantine instead of retrying forever.
- [ ] Dropped/filtered records have metrics; do not track only bytes sent.
- [ ] Do not assume "exporter HTTP 200" always means the backend has durably stored/indexed the data.
- [ ] When an ACK is lost, retries can cause duplicates; use event IDs/deduplication if the workflow requires it.
- [ ] The Collector's own telemetry does not trigger a log storm loop when downstream is failing.
- [ ] Query canary/test events with unique IDs to verify the complete pipeline.
- [ ] Check backend quotas, index rejections, retention, and query latency—not just Java metrics.

**Ingestion lag** must be separated from request latency; a fast-caller solution whose backend takes too long to become searchable fails real-time investigation goals.

## 21. Log Volume, Cardinality, and Storage Cost

A seemingly small change like adding a raw payload or stack trace can multiply log volume several times over.

Estimation formula:

~~~text
eventsPerSecond = requestsPerSecond × eventsPerRequest
rawBytesPerSecond ≈ eventsPerSecond × avgBytesPerEvent
rawBytesPerDay = rawBytesPerSecond × 86,400
storedBytes ≈ rawBytesPerDay × measuredStorageFactor × retentionDays
~~~

`measuredStorageFactor` depends on compression, index overhead, replicas, metadata, and the backend; it is **not** a universal constant.

Illustrative example: `2,000 requests/s × 3 events/request × 400 bytes/event ≈ 2.4 MB/s raw`, which is roughly **207.36 GB raw/day** in decimal units. Without controlling duplicates/retries, actual bytes can be higher.

**Cardinality:**

- `service.name`, `environment`, `event_code` usually have bounded value sets, useful for filtering/aggregation.
- `trace_id`, `request_id`, `message_id`, `user_ref` have very high cardinality.
- Do not put granular IDs into **Prometheus metric labels**; in log backends, also verify the indexing/label strategy for your specific technology.
- Loki labels should not contain per-event trace IDs or request IDs due to stream/index/cardinality costs; keep them in structured metadata/body for querying when needed.
- Uncontrolled dynamic mapping of fields in OpenSearch/Elasticsearch can cause field explosion and high memory/index costs.

**Checklist:**

- [ ] Have budgets for events/s, bytes/s, peak bursts, and retention per class.
- [ ] No unbounded field growth (arbitrary user keys).
- [ ] Do not unconditionally index every JSON key.
- [ ] Reduce duplicates at the source rather than just looking for cheaper storage.
- [ ] Have sampling/rate-limit policies for diagnostics, without applying them to mandatory audit logs.
- [ ] Alert when ingest volume spikes unexpectedly after a deploy.

## 22. Sampling, Rate Limiting, and Preserving Signal

One way to save cost is **sampling** high-volume events where every individual record is rarely needed. For example, loop DEBUG logs might keep only a small sample, while lifecycle INFO and ERROR logs with key event codes are kept in full per policy.

**Distinctions to make:**

- **Request/trace head sampling:** decides early per trace, keeping context consistent if implemented properly.
- **Level/event log sampling:** drops a fraction of logs based on rules, volume, or priority.
- **Rate limiting:** caps logs per time window, optionally keeping a counter such as "suppressed N similar events."
- **Deduplication:** reduces duplicate logical events or retry copies based on a reliable identity.
- **Aggregation:** replaces many per-item logs with metric statistics or batch summaries.

**Checklist:**

- [ ] Know which events must be retained 100% for compliance/audit; never sample them silently.
- [ ] If sampling, track how many records were dropped and how queries should interpret counts.
- [ ] Keep rules consistent across replicas/collectors when needed.
- [ ] Do not apply random sampling and then infer true error counts from unadjusted raw counts.
- [ ] When investigating a specific trace, have a mechanism for bounded detailed logging with data protection.
- [ ] Do not let suppression hide important ERROR/WARN notifications without an appropriate counter/alert.

**Do not assume sampling always improves reliability:** reducing volume can keep the pipeline healthier, but removes context needed for investigation. Choose based on event class and query needs.

## 23. Backpressure, Full Queues, and Event Loss Policies

When log generation rate exceeds sink processing rate:

~~~text
log producer rate > exporter/sink service rate
         → queue depth increases
         → wait/drop/retry/disk spool per policy
         → latency, memory, loss, or backlog
~~~

**Main strategies:**

| Policy When Full | Pros | Risks |
| --- | --- | --- |
| Block caller | Reduces drops at that queue | Increases request p99, can hurt availability |
| Drop/discard low priority | Protects request latency/memory | Loses diagnostics; requires metrics and contract |
| Spill to bounded disk | Survives short outages without putting everything in RAM | Disk/quota/checkpoint/I/O and data management |
| Fallback sync | Can retain critical events when async fails | Sudden spike in caller latency |
| Fail operation | Gives a clear signal that logging failed | May conflict with availability; needs policy for audit |

There is no single right answer for all logs. Mandatory audit and debug diagnostics have different goals. **Do not claim "zero loss" when the queue is only in RAM** or there is no durable storage confirmation.

**Mandatory test:** what happens when the sink is intentionally 10x slower, the backend returns 429/503, the disk spool is nearly full, or the app process is killed? Record observed event loss/latency rather than benchmarking only under healthy conditions.

## 24. GC, Allocation, and JFR/JMH: How to Benchmark?

**JFR (Java Flight Recorder)** and profilers are the place to start when a real application sees CPU/GC increases. Look for hot spots such as `StringBuilder/StringConcatFactory`, `toString`, JSON encoders, `ThrowableProxy`/stack trace processing, logger locks, async queues, write syscalls, and disk/network waits. Inspect both disabled and enabled level phases.

**JMH (Java Microbenchmark Harness)** is suitable for measuring a small operation when comparing logger usage patterns:

- Include warmup, measurement, forks, JVM/JDK flags, and dead-code elimination management.
- Use equivalent logging backends/providers and sinks across variants.
- Check GC allocation rates and appropriate benchmark modes.
- Do not include real console I/O in one variant while using a no-op appender in another.
- Record message size, argument types, exception yes/no, threads, levels, and filters.
- Measure both call latency and throughput, but **do not infer end-to-end durability** from JMH.

**Do not use the Section 7 program as a speed benchmark.** The counter test there proves eager/lazy evaluation; it has no warmup or measurement controls. Conversely, a fast JMH microbenchmark **does not prove** production p99 latency won't degrade under disk/network/GC pressure.

**Measurement checklist:**

- [ ] Sufficient warmup; measure multiple forks/repetitions as appropriate.
- [ ] Do not include startup/class-loading time in steady-state measurements without stating it.
- [ ] Report stddev/percentiles/confidence intervals, not just a single best number.
- [ ] Compare workloads and configurations fairly at the same level.
- [ ] Verify the JIT has not eliminated unobservable measurements.
- [ ] Cover rollover, bursts, outages, and recovery with separate integration/load tests.
- [ ] Manage security for test fixtures and profiler artifacts as well.

## 25. Realistic Load Testing: Minimum Matrix

| Scenario | Configuration | Key Observations | Pass Criteria |
| --- | --- | --- | --- |
| Baseline | Logger configured, no diagnostics emitted | Baseline throughput/latency | Reference for comparison |
| DEBUG disabled, many call sites | Suppliers/guards and eager variants | CPU/calls/allocations | No unintended expensive calls |
| INFO steady | Small payloads, normal sink | events/s, bytes/s, p95/p99 | Within budget and no missing events |
| ERROR burst | Many exceptions/stack traces | CPU, GC, queue, sink | No OOM, follows alert/loss policy |
| JSON vs. text | Same semantic fields/volume | CPU, bytes, parse/schema | No loss of required information |
| Sync vs. async | Same sink/format/load | Caller latency, queue, drops | Trade-offs accepted |
| High concurrency | N threads matching workload | Lock contention, CPU, tail latency | No regression beyond SLO |
| File rotation | Hits size/time threshold | Latency spike, missing events | Lifecycle matches policy |
| Collector throttling | Temporary 429/503 | Queue/retry/drop/backoff | No storm/OOM |
| Disk full/permission | Sink error | Handler response, app availability | Clear signal and safe behavior |
| Graceful shutdown | Pending events present | Drain, timeout, incomplete | Matches contract, no kill guarantee claimed |
| SIGKILL/Runtime.halt | Forced process termination | Event loss window | Understood and risk-assessed |
| End-to-end pipeline | Query event ID from backend | Ingest lag, schema, completeness | Queryable within defined SLO |

**Do not use an INFO-only, cached-response workload** to conclude the optimal config for an ERROR burst. Exception events are more expensive than small messages; throughput is dominated by log size and sink behavior.

## 26. Copyable Performance Measurement Sheet

Fill in **actually measured** values in the template below (`<...>` are placeholders to fill in, not verified results):

~~~text
Experiment: logging-perf-<run-id>
Service/build/JDK: <name>/<version>/<JDK+flags>
Backend/provider: <JUL|Logback|Log4j2 + exact versions>
Sink/encoder: <stdout/file/network + layout/JSON schema>
Levels/filters: <effective logger/appender levels>
Traffic: <requests/s; concurrency; burst length>
Event mix: <DEBUG/INFO/WARN/ERROR ratios; bytes/event>
Baseline p50/p95/p99 latency: <values + units>
Candidate p50/p95/p99 latency: <values + units>
Baseline/candidate throughput: <values + units>
CPU/allocated bytes/op/GC pauses: <measured values>
Queue depth/drops/retry/exporter errors: <measured values>
Backend ingested/queryable events: <count and deadline>
Privacy/correlation/audit checks: <PASS/FAIL with evidence>
Decision/owner/revert plan: <approved or rejected with reason>
~~~

Before optimizing, define the project's **acceptance budget**. For example, "p99 does not increase beyond an approved threshold, mandatory events are not dropped, queues do not grow unbounded, and backend queries return the IDs" is a test contract; **there is no universal percentage threshold** for all organizations.

If tests run on shared CI, record background load or re-run in a reproducible environment. Compare data under the same JDK/GC/CPU quota; do not cite a "40% improvement" across two different environments.

## 27. Production Monitoring: Telemetry of the Logging Pipeline Itself

A pipeline can run comfortably for hours and then suddenly back up; therefore **continuous health monitoring is required**.

**JVM/appender layer:**

- Events generated by level and class; filtered/discarded if provided by the backend.
- Queue occupancy and enqueue wait time.
- Errors from file/network appenders.
- Bytes/s and events/s, average/max size.
- Worker thread errors and shutdown loss if observable.

**Agent/Collector layer:**

- Receiver accepted/refused records.
- Parser errors, truncated/oversized events, dropped by filters.
- Exporter sent/failed records, retries, backpressure, and queue depth.
- Disk buffer pressure, checkpoint lag, receiver/restart health.
- Ingest lag and count of logs missing required resource/trace/event codes.

**Backend/query layer:**

- Ingest/index rejections and latency, query p95/p99, retention/compaction health.
- Volume/cost by service, env, and event class.
- Duplicated events or expected-but-missing canary events.
- Access errors, tenant isolation, and sensitive data in logs.

**Metric naming depends on version/distribution.** Do not hard-code a metric name from an example and conclude the pipeline is broken when that metric does not exist in your Collector.

**High-value alerts:** Unbounded queue growth, drop rate exceeding policy, raw log bytes spiking after a release, CPU/GC rising with encoding, persistent exporter errors, canary event IDs not queryable by deadline.

## 28. Symptom-Based Troubleshooting

| Symptom | Likely Hypothesis | Next Check |
| --- | --- | --- |
| CPU increases with DEBUG off | Eager argument `toString/serialize/concat` | Profiler + Section 7 counter test |
| GC increases while events/s is low | Oversized object/exception/JSON fields | Allocation profile, bytes/event |
| Request p99 spikes during log bursts | Synchronous sink or async queue blocking | Thread dumps, queue metrics, syscall latency |
| App is fast, dashboard is slow | Agent/Collector/exporter/backend backlog | Ingest lag, queues, index rejects |
| WARN/ERROR lost at peak | Discard/drop policy or sink errors | Level-specific counts, queue full, shutdown |
| Same error logged multiple times | Double logging across layers, retries, or double shipping | Event ID, logger/additivity, source routes |
| Files grow too large | DEBUG spam, stack traces, retention not running | Rotation config, volume, cleaning errors |
| CPU spikes when switching text → JSON | Encoder/field conversion, Throwable rendering | Benchmark with identical semantic fields |
| Persistent Collector 429s | Quota/backpressure | Rate, exporter retries, queue/batch policy |
| One pod has no logs | Agent path/permissions/CRI/rotation | Raw runtime log and file cursor |
| Logs fail to parse | Raw newlines, invalid JSON, charset/partial records | Encoder output and parser fixtures |
| Secrets enter the index | Unfiltered DTO/exception/MDC dump | Stop propagation, security response, sanitization |
| Metrics show "no errors" while users report failures | Logging/metrics pipeline may be broken | User impact, probes, cross-signal triangulation |
| Optimization drops audit records | Wrong class sampled/discarded | Audit completeness test, durable contract |
| Benchmark is fast but production is slow | Non-equivalent sink/load/threads/JIT/config | Reproduce near-production, measure end-to-end |

**Investigation order:** Verify impact → locate bottleneck via metrics/traces/profiler → isolate one layer → change one variable → test correctness/perf → deploy with rollback. Do not reflexively increase queue size or turn off ERROR.

## 29. Security Review Is Also Performance Review

Some "quick optimizations" have bad consequences:

- Skipping JSON escaping to save CPU → log injection and parser errors.
- Dumping raw DTOs to save time picking fields → higher bytes, PII exposure, and storage costs.
- Turning off audit logs to reduce overhead → loss of evidence and policy violations.
- Sending unencrypted logs to remote endpoints → in-transit exposure.
- Keeping all DEBUG logs in the backend long-term → higher cost and larger data surface.
- Over-restricting access so SREs cannot investigate incidents → slower incident response.

**Security checklist for performance changes:**

- [ ] No exposure of passwords/tokens/cookies/auth headers or raw payloads; include synthetic sentinel tests.
- [ ] Keep necessary exception/trace context while excluding sensitive fields.
- [ ] Preserve JSON encoding/escaping and event size limits.
- [ ] Sampling/rate limiting never accidentally drops mandatory audit/security logs.
- [ ] Ensure TLS/auth for network export and tenant isolation in the backend.
- [ ] Retention/rotation matches each log class; neither keep nor delete indefinitely against policy.
- [ ] Profiler traces, heap dumps, and benchmark outputs are also treated as potentially sensitive artifacts.

**Conclusion:** Performance, investigability, and privacy must be measured together as three simultaneous axes.

## 30. Step-by-Step Improvement Plan in One Sprint

**Day 1 — Inventory and baseline:** Catalog call sites, levels, payloads, and sinks; enable instrumentation for throughput/latency/GC/queues. Define the mandatory event list.

**Day 2 — Fix eager evaluations:** Convert DEBUG string concatenation to parameterized logging, add Suppliers/guards on expensive paths, remove raw DTO/header dumps. Unit test disabled levels and privacy.

**Day 3 — Control volume:** Consolidate per-item diagnostics into batch summaries/metrics, add event codes, fix duplicate logging, and define sampling/rate limits for permitted channels.

**Day 4 — Measure formatters and sinks:** Benchmark text vs. structured, stack traces, sync vs. async, rollover, bursts, and exporter outages. Evaluate p99 and dropped records, not just CPU.

**Day 5 — E2E and rollout:** Query canary events in the backend, measure ingest lag, run incident/rollback drills, finalize release criteria and pipeline observability dashboards. Roll out gradually if your process allows; monitor for regressions.

This is only **an exercise structure**, not a schedule promising every project finishes in five days. Changes affecting security policies, compliance, or backend vendors require additional review/approval before rollout.

## 31. Acceptance Criteria and Evidence to Retain

A logging optimization is **accepted** when:

1. **Correctness:** Unit tests assert templates/levels/Throwables/correlation and required event counts; no message changes meaning.
2. **Performance:** Equivalent baseline/candidate measurements exist; throughput and p95/p99 latency fit within budget; CPU, allocation, and GC are reviewed.
3. **Reliability:** Mandatory events are not lost; full-queue/shutdown/outage behaviors are documented and tested; discard/error telemetry exists.
4. **Security:** No raw secrets, log injection, or out-of-policy read access expansion.
5. **Operability:** Dashboards, retention, and E2E queries work; missing-log runbooks are updated; owner and rollback plan exist.
6. **Reproducibility:** Benchmarks/tests can be re-run on the same backend/JDK/config, with measurements and parameters archived.

**Rejected** if you only report "logger is 30% faster" from a microbenchmark while request p99 degrades, queues drop WARN, error counts become unstable, or sensitive data enters the backend.

If logging throughput is a bottleneck, set concrete target thresholds such as `maxEventsPerSecond`, `maxBytesPerSecond`, and `maxDropRate` per class **confirmed by operations**, rather than treating guessed numbers as reality.

## 32. Common Mistakes When Optimizing Java Logging

| Mistake | Why It Is Ineffective or Dangerous | How to Fix |
| --- | --- | --- |
| Using `{}` while the argument still calls `expensive()` | Java evaluates arguments before the call | Supplier/guard |
| Treating `StringBuilder` as lazy logging | The string is still built before the logger | Template + args |
| Benchmarking only with DEBUG off | Ignores encoder/sink/stack trace costs when on | Measure both on and off |
| Single-threaded / no-op sink benchmarks | Misses contention/I/O | Multi-threaded load with real sink |
| Measuring throughput only | Ignores p99 latency and event drops | Measure tail latency + loss |
| Making async queues unbounded | RAM/OOM risk, higher lag | Bounded queue + metrics |
| Enabling `neverBlock=true` without monitoring | Can drop events when full | Overload test and measure drops |
| Treating flush as a durable commit | Stream flush != fsync/backend index | Define delivery boundaries |
| Logging stack traces on every retry | High CPU/bytes and duplicate evidence | Reason code + trace at key points |
| Dumping entire payloads into JSON | PII leaks, field explosion, index cost | Structured safe allowlist |
| Using trace IDs as metric labels | Extreme cardinality | Keep IDs in logs/traces |
| Sampling all WARN/ERROR | Loses critical context | Policy per event class |
| Writing file and stdout then shipping both | Duplicate ingest and cost | One primary route or proper dedup |
| Only increasing retention/index capacity | Does not fix source log storms | Reduce volume/duplicates first |
| Not measuring during rollover/shutdown | Misses spikes and loss windows | Test lifecycle events |
| Not monitoring the Collector | App is healthy while logs vanish | Internal telemetry/canary |
| Guessing version defaults | Config varies by backend | Pin versions and test behavior |
| Optimizing without a rollback path | Regressions can linger | Release gate and revert plan |

## 33. Self-Check Questions

1. Why does `log.debug("x={}", expensive())` still incur cost when DEBUG is off?
2. When is parameterized logging enough, and when is a Supplier/guard also needed?
3. Does JUL use `{0}` or `{}` placeholders?
4. In the lab, why is `eagerCalls=10` even though `emitted=0`?
5. Why are the lab results not a measurement of nanoseconds/op or bytes/op?
6. Is SLF4J a file/network logging backend on its own?
7. If AsyncAppender is faster at the caller, which other costs can increase?
8. Does a 1024-record queue mean 1024 records are preserved after SIGKILL?
9. Why can `neverBlock=true` lose diagnostics under overload?
10. Why is measuring only CPU without p99 latency incomplete?
11. When is a batch summary better than INFO per item?
12. Why can exception messages and stack traces be both expensive and unsafe?
13. Should `trace_id` be a Prometheus metric label?
14. When JSONL logs are shipped through a Collector, does HTTP 200 from the exporter prove the backend indexed them?
15. If no logs are found for a request, does that mean the request never ran?
16. Why must sync vs. async tests use the same sink/layout and workload?
17. Why is looking only at total log drops without distinguishing severity/event class dangerous?
18. When should you choose a durable audit store/outbox over best-effort diagnostic logging?
19. If DEBUG is sampled at 10%, can you infer the true event count from the raw DEBUG count?
20. Is a change that reduces bytes/s but drops correlation IDs considered a good optimization?
21. How do you ensure temporarily enabling DEBUG does not leave long-term risk?
22. What data must be collected to prove a logging performance regression has been fixed?

**Hints:** (1) arguments are evaluated before the method call; (2) use templates for available/cheap values, lazy evaluation for expensive ones; (3) `{0}`; (4) two eager calls/iteration × five; (5) it only tests counter correctness; (6) no, it needs a provider/backend; (7) worker CPU, queue memory, ingest lag, drops; (8) no; (9) drops events when the queue is full; (10) blocking and outliers; (11) when per-item volume is high and individual detail is unnecessary; (12) many frames/causes + secrets; (13) no; (14) not necessarily; (15) no, the pipeline or query may be broken; (16) for an apples-to-apples comparison; (17) WARN/AUDIT events may be lost; (18) when business needs complete/durable retention; (19) not without sampling semantics; (20) no, if correlation is part of the contract; (21) scope, expiration, revert, audit, and privacy; (22) baseline, candidate, config, workload, CPU/GC/p99, drops, ingest, and correctness.

## 34. Official References

- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): JUL level checks, parameter overloads, and `Supplier`.
- [Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): message/parameters/exception/metadata.
- [Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html): `formatMessage`.
- [Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): `publish`, `isLoggable`, and lifecycle.
- [Java SE 17 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/): performance observability and JFR API.
- [OpenJDK — JMH](https://github.com/openjdk/jmh): microbenchmarks with warmup/fork/measurement.
- [SLF4J Manual](https://www.slf4j.org/manual.html): parameterized logging, SLF4J 2 Fluent API, and Supplier arguments.
- [Logback — AsyncAppender](https://logback.qos.ch/manual/appenders.html#AsyncAppender): queue, discarding, blocking, and maxFlushTime.
- [Logback — RollingFileAppender](https://logback.qos.ch/manual/appenders-rolling.html): rolling/retention/size cap.
- [Apache Log4j 2 — Asynchronous Loggers](https://logging.apache.org/log4j/2.x/manual/async.html): async loggers/appenders, trade-offs, and configuration.
- [Apache Log4j 2 — Garbage-free logging](https://logging.apache.org/log4j/2.x/manual/garbagefree.html): allocations and performance considerations.
- [Apache Log4j 2 — Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html): layout costs and formatting fields.
- [OpenTelemetry — Collector Architecture](https://opentelemetry.io/docs/collector/architecture/): receivers/processors/exporters.
- [OpenTelemetry — Collector Troubleshooting](https://opentelemetry.io/docs/collector/troubleshooting/): measuring dropped/refused records, queues, and failures.
- [Kubernetes — Logging Architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/): stdout/stderr, rotation, CRI, and node-level agents.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data minimization, log injection, access control, and retention.

**Decision summary:** First eliminate wasted work and redundant logs; next measure encoders, sinks, queues, and pipelines under realistic load; finally optimize based on **throughput + p99 + loss + data security**, not on the speed of a single logger call alone.
