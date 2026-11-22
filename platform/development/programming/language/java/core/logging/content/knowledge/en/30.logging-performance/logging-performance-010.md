# Optimizing the Hot Path for Logging in Java

## 1. What Does Hot-Path Optimization Mean?

A **hot path** is an execution path called at high frequency or one that directly determines the latency of a critical operation: handling each HTTP request, each message from a queue, each transaction, each iteration over elements of a large loop, or a section of code inside a critical section. If that path continuously produces logs, the small cost of a single log call can accumulate into significant CPU, memory allocation, GC, I/O, contention, and tail latency (p95/p99).

In Java, a seemingly simple logger call may have to:

1. Evaluate arguments at the **call site** before invoking the API.
2. Check the log level, filters, and context.
3. Construct the message, convert objects to strings, and format timestamps/exceptions.
4. Create a log event, capturing MDC and required metadata.
5. Pass it to an appender/handler, sometimes queuing it asynchronously.
6. Serialize, encode, and write to console/file/network.
7. Wait on downstream or undergo buffer policies when load increases.

**Goal:** reduce cost on the frequent path while preserving correctness, diagnosability, and security. Do not aim to "delete all logs" or "make everything async" at all costs.

After this lesson, you should be able to distinguish **cost when a level is disabled** from **cost when a level is enabled**, use lazy logging safely, understand the impact of sinks and queues, know when to apply sampling/rate limiting, and measure results by throughput, allocation, and latency rather than just glancing at a few console lines.

## 2. Start with a Cost Model

Let's break an event down into its parts:

~~~text
Business code
   │
   ├─ Prepare arguments (can be very expensive)
   ├─ Check logger/level
   ├─ Build event + context + exception
   ├─ Filter / layout / encoder
   ├─ Appender / Handler
   │    ├─ Synchronous write → I/O → stdout/file/socket
   │    └─ Async enqueue → queue → worker → I/O
   └─ Return control to business thread
~~~

A qualitative way to think about it:

~~~text
Total logging cost ≈
  number of times through the call site
  × (preparation cost that always happens
     + check / event creation cost when writable)
  + sink write, contention, and queue processing cost
~~~

This is a **mental model**, not an exact timing formula. In an async pipeline, cost may shift to the worker/collector rather than disappearing. Total CPU and I/O still exist.

| Condition | Cost That Usually Remains | What to Watch For |
| --- | --- | --- |
| DEBUG disabled | Evaluating Java arguments before the call; string concatenation; object creation if written poorly | Lazy evaluation, guards, and avoiding side effects |
| DEBUG enabled but event filtered at appender | Part of the message/event/context may already have been created | Place filters early when appropriate; measure per specific backend |
| INFO enabled, synchronous console/file | Formatting, locking/synchronization, system calls, flushing, downstream limits | Reduce event count, appropriate batching/async, improve sink |
| Async appender queue has space | Event creation/capture, enqueueing, producer–consumer synchronization | Allocation, queue capacity, thread context |
| Async queue full | Blocking, fallback, dropping, or other policy depending on backend | Tail latency, backpressure, event loss, metrics |
| Centralized log collection | Network, serialization, collector, parsing, indexing | Volume, cardinality, storage cost, retention |

An important milestone: **a thread-safe logger does not mean a logger call is free**, and **asynchronous logging does not mean non-blocking or lossless logging**.

## 3. Identify Hot Paths Before Fixing

Examples of high-risk locations:

~~~java
// Snippet inside a batch processing method.
for (Order order : orders) {
    log.debug("order={} payload={}", order.id(), expensiveSerialize(order));
    process(order);
}
~~~

The snippet above is an SLF4J example, not a standalone Java program. The `expensiveSerialize(order)` method still runs **before** `log.debug` receives its arguments, even when the DEBUG level is disabled. If the loop has hundreds of thousands of elements, this cost is far greater than the log-level comparison itself.

Other code patterns to review include:

- Logging on every collection iteration or every byte/record/message.
- Logging while holding a `synchronized`/Lock; I/O can prolong lock hold times.
- Logging inside a retry loop, timeout loop, or high-frequency error path, causing a **log storm**.
- `toString()` on large object graphs, JSON serialization, or expensive stack trace collection.
- Creating many unnecessary metadata fields per event, or overly verbose debug configuration.
- Calling `System.out.println` directly many times on a hot path.
- Creating/flushing a new file, HTTP request, or network producer per event.

Before optimizing, confirm with a profiler, metrics, and log rate that logging is actually the bottleneck. If most of the time is spent in database queries, replacing a string concatenation in a logger may not noticeably change p99.

## 4. The Java Rule: Arguments Are Evaluated Before the Call

This is the most fundamental and easiest mistake to fix.

~~~java
// Wrong when DEBUG is usually disabled:
log.debug("State = " + expensiveStateAsText());
log.debug("State = {}", expensiveStateAsText());
log.debug(String.format("State = %s", expensiveStateAsText()));
~~~

All three approaches call `expensiveStateAsText()` **before** the logger decides whether the event will be written.

In particular, SLF4J's placeholder syntax:

~~~java
log.debug("order={} status={}", orderId, status);
~~~

can avoid some string formatting work when the log level is disabled. However, if `orderId` or `status` is the **result of an expensive method**, that method is still executed before the call. Placeholders do not change Java's argument evaluation rules.

### 4.1. Guarding with isDebugEnabled / isLoggable

~~~java
// SLF4J snippet
if (log.isDebugEnabled()) {
    log.debug("State = {}", expensiveStateAsText());
}
~~~

Guards are useful when computing the data is solely for logging and costs significant CPU/I/O/allocation. If the inputs are just primitives, existing immutable `String`s, or a few local variables, adding a guard to every log statement can bloat the code without measurable benefit.

Do not make business logic depend on whether logging is enabled:

~~~java
// Wrong for correctness: state mutation only happens when DEBUG is enabled.
if (log.isDebugEnabled()) {
    log.debug("processed={}", processed.incrementAndGet());
}
~~~

If DEBUG is disabled, the counter will not increment. Move the business update outside the conditional block, capture the value, and then log if needed.

### 4.2. Supplier / Lazy Evaluation

Java Util Logging (JUL) supports an overload taking `Supplier<String>`:

~~~java
// Java 17 snippet; logger is java.util.logging.Logger.
logger.log(java.util.logging.Level.FINE,
        () -> expensiveStateAsText());
~~~

When the logger does not allow the FINE level, the message supplier does not need to be invoked. If the level matches, the JDK can ask the supplier to produce the message and pass it to the Handler. Note: **creating a lambda or capturing variables still has potential cost**; the JIT may optimize some cases, but it must not be assumed to be allocation-free in every application.

In SLF4J 2.x, the fluent logging API supports suppliers for arguments:

~~~java
// SLF4J 2.x snippet; requires SLF4J 2.x dependency and a corresponding provider.
log.atDebug()
   .setMessage("state={}")
   .addArgument(() -> expensiveStateAsText())
   .log();
~~~

The `expensiveStateAsText()` part should only be called when the builder actually evaluates the argument. This is not part of the SLF4J 1.7 API; with 1.7, you can use a guard instead. With Log4j 2, there are also overloads using `Supplier`/lazy messages depending on the version; choose the right API for the Log4j 2 version you are running, and do not assume SLF4J syntax works across all loggers.

**Distinguish lazy message construction from lazy business data:** if a supplier reads a mutable object at a different point in time, the logged content may not reflect the intended state. Capture an immutable snapshot before creating the supplier if the read must be consistent.

## 5. Complete Java 17 Program: Eager vs. Lazy When Logging Is Disabled

This example uses **JUL built into the JDK**, requires no Maven or SLF4J, and fixes the level at INFO to observe the exact number of message builds.

**File: LoggingHotPathDemo.java**

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingHotPathDemo {
    private static final class CapturingHandler extends Handler {
        private final List<String> messages = new ArrayList<>();

        CapturingHandler() {
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                messages.add(record.getMessage());
            }
        }

        @Override
        public void flush() {
            // Messages are kept in memory.
        }

        @Override
        public void close() {
            // Example owns no external resources.
        }

        List<String> messages() {
            return List.copyOf(messages);
        }
    }

    private static String buildMessage(
            AtomicInteger builds, String label) {
        builds.incrementAndGet();
        return "payload-" + label;
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("example.hotpath");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        CapturingHandler handler = new CapturingHandler();
        logger.addHandler(handler);

        AtomicInteger builds = new AtomicInteger();

        try {
            // 1. Eager: even though FINE is disabled, the method still runs.
            logger.fine(buildMessage(builds, "eager-fine"));

            // 2. Lazy: FINE is disabled, so the supplier does not build a message.
            logger.log(Level.FINE,
                    () -> buildMessage(builds, "lazy-fine"));

            // 3. Guard: FINE is disabled, so the expensive method is not called.
            if (logger.isLoggable(Level.FINE)) {
                logger.fine(buildMessage(builds, "guarded-fine"));
            }

            // 4. INFO is enabled, so the supplier is called once.
            logger.log(Level.INFO,
                    () -> buildMessage(builds, "lazy-info"));

            // 5. Cheap, already-available message.
            logger.info("READY");

            System.out.println("messageBuilds=" + builds.get());
            System.out.println(
                    "logEvents=" + handler.messages().size());
            for (String event : handler.messages()) {
                System.out.println("event=" + event);
            }
        } finally {
            handler.flush();
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Run with JDK 17 or later in the directory containing the file:

~~~bash
javac -encoding UTF-8 LoggingHotPathDemo.java
java LoggingHotPathDemo
~~~

**Exact stdout:**

~~~text
messageBuilds=2
logEvents=2
event=payload-lazy-info
event=READY
~~~

**Step-by-step explanation:**

1. FINE is more detailed than INFO. With the logger at INFO, FINE events do not reach the Handler. However, Java already executed `buildMessage` in the `logger.fine(...)` call, so `builds` increments from 0 to 1.
2. The `logger.log(Level.FINE, Supplier<String>)` overload skips the message supplier when FINE is disabled, so `builds` does not increment.
3. The `isLoggable(Level.FINE)` guard also prevents calling `buildMessage`, so `builds` does not increment.
4. INFO is enabled; JUL invokes the supplier and `builds` increments to 2. `CapturingHandler` receives the message `payload-lazy-info`.
5. INFO `"READY"` is produced as a second event without calling `buildMessage`.

`CapturingHandler` uses memory only to **verify functionality and keep output deterministic**. It does not simulate formatter overhead, console/file I/O, or the concurrency of production logging. The result demonstrates **how many times the message is evaluated**, not that lazy is always faster than a guard down to the nanosecond on every JVM.

## 6. Choosing a Logging Strategy by Argument Computation Cost

| Content to Log | Recommendation | Reason |
| --- | --- | --- |
| An existing String/primitive | Use normal placeholders | Preparation cost is small; code stays simple |
| `toString()` or serializing a large DTO | Guard or supplier | Avoid building large strings when the level is disabled |
| DB/HTTP query solely to enrich a log | Avoid inside logging; consider removing | Do not trigger extra business I/O just for DEBUG |
| Stack trace from an existing exception | Log conditionally and rate-limit | Formatting stack traces can cost CPU/space; keep critical info |
| Business computation needed for subsequent logic | Compute once, reuse | Do not let log enablement alter logic |
| Small, structured set of fields | Structured/parameterized logging | Avoids string parsing and keeps schema clear |
| Payload containing sensitive data | Do not log raw; use a field allowlist | Both performance and security |
| Very high event volume, low value | Intentional sampling/rate limiting | Reduces total events generated and transmitted |

Do not apply a single technique uniformly. When a supplier is more complex than a guard, prefer code that is easy to inspect, then benchmark the actual workload.

## 7. Parameterized Logging: Understanding Exactly What It Optimizes

With SLF4J:

~~~java
// Snippet; assumes orderId is an existing String.
log.debug("order_id={}", orderId);
~~~

The logger can skip message formatting when DEBUG is disabled. However:

~~~java
// The method is still called before the logger checks the level.
log.debug("order={}", serializeOrder(order));
~~~

is not lazy. Some logging backends may defer `toString()` on an object passed directly, but **do not assume every provider/async encoder evaluates at the same time**. In particular, passing a mutable object into an async pipeline without capturing its state can produce inconsistent messages.

**Example of keeping a cheap snapshot:**

~~~java
// Java 17 snippet in application context.
record OrderSnapshot(String id, String status, long amountMinor) {}

OrderSnapshot snapshot = state.snapshot(); // Properly synchronized in state.
log.debug("order_id={} status={} amount_minor={}",
        snapshot.id(), snapshot.status(), snapshot.amountMinor());
~~~

Here `state.snapshot()` must actually capture a consistent state per the application's design. If `snapshot()` is expensive and only used for debugging, check the level before calling it. If the snapshot is also needed for business logic, create it once and reuse it. Do not put the `snapshot()` call inside a supplier if it must reflect **the exact moment the event was emitted** and could run after state changes.

### String Concatenation, String.format, and JSON Serialization

Avoid:

~~~java
log.debug("request=" + request + ", body=" + serialize(body));
log.debug(String.format("response=%s", serialize(response)));
~~~

If DEBUG is disabled, string concatenation and serialization may still have already occurred. Prefer:

~~~java
if (log.isDebugEnabled()) {
    log.debug("request_id={} response={}",
            requestId, serialize(response));
}
~~~

Even when DEBUG is enabled, **do not serialize large payloads by default**. Extract only a few allowed fields such as status, byte count, response type, or ID. Logging entire payloads increases CPU, GC, storage, and data-leak risk.

## 8. Log Levels and Configuration Policies for Hot Paths

A useful convention:

- **TRACE:** use only for narrow, time-bounded targeted debugging.
- **DEBUG:** development/diagnostic information; avoid enabling globally in production.
- **INFO:** notable milestones, not every small loop iteration.
- **WARN/ERROR:** anomalies or failures requiring attention; also prevent logging the same incident millions of times repeatedly.

Actual log levels depend on the environment. With Spring Boot:

~~~properties
logging.level.root=INFO
logging.level.com.example.orders.internal=DEBUG
~~~

This is a Spring Boot properties snippet and does not apply automatically to a plain JUL application. Levels on loggers/appenders and filters can interact; the actual provider configuration determines whether an event is written.

If a hot-path module emits 100,000 DEBUG events/second, enabling DEBUG for that single module for 30 minutes still produces a massive log volume. Estimate log rate and volume before changing levels, rather than relying solely on the level name.

### Do Not Use DEBUG as a Condition for Business Logic

Wrong:

~~~java
// DO NOT do this: when DEBUG is disabled, the update is skipped.
if (log.isDebugEnabled()) {
    int newValue = processed.incrementAndGet();
    log.debug("processed={}", newValue);
}
~~~

Better:

~~~java
int newValue = processed.incrementAndGet();
log.debug("processed={}", newValue);
~~~

These are snippets assuming `processed` and `log` are already declared. If `newValue` does not need to be stored for business logic and is only used for logging, you can choose another strategy, but the increment **must always happen** according to application logic. Logging is an observational side effect, not a condition for changing application state.

## 9. Log Less While Preserving Important Signal

When the log rate is too high, optimizing individual log lines is not enough. You need to reduce the number of emitted events.

### 9.1. Do Not Log Every Successful Processing Step

Instead of INFO per item:

~~~text
INFO processed item=1
INFO processed item=2
INFO processed item=3
...
~~~

you can emit a single batch summary:

~~~text
INFO batch_complete processed=1000 failed=0 elapsed_ms=280
~~~

When you need to trace a specific item, use a trace ID, temporary debug logging, or sampling. Do not replace all auditable business outcomes with a counter if they must be durably recorded.

### 9.2. Sampling

Sampling intentionally captures a subset of events, such as 1% of successful requests. There are two main approaches:

- **Random sampling:** each event has a probability of being selected. Good for high-volume statistics, though an individual request may only have a partial trace if different layers decide independently.
- **Deterministic sampling by trace/request ID:** the same ID yields the same selection decision under the same rule; useful for a more consistent history across multiple steps if services share the same logic.

Example snippet selecting a fraction via a stable hash:

~~~java
// Illustration: traceId is already validated and is not PII.
boolean keep = Math.floorMod(traceId.hashCode(), 100) == 0;
if (keep) {
    log.debug("trace_id={} detail={}", traceId, lightweightSummary);
}
~~~

This is not an exact 1% sampler for every dataset (hashes can distribute unevenly) and does not guarantee all services use the same function/rule. If your tracing backend provides a sampler, prefer that mechanism to preserve context. **Do not blindly sample** security events, audit logs, states requiring full tracking, or rare critical errors.

### 9.3. Rate Limiting and Log Storms

An external dependency failure can repeat thousands of times per second. Logging an ERROR with a full stack trace on every retry can slow the system down even further.

Common solutions:

- Log the first warning, then summarize the repeat count over a time window.
- Use a rate-limiting filter/appender if the backend provides one.
- Maintain metrics counters for total errors and alerting, even when detailed logs are throttled.
- Emit events on state transitions from healthy to unhealthy and on recovery, rather than spamming the same message.

A throttling policy should use a **stable grouping key** (error type, component) and bound the number of keys to avoid unbounded cardinality growth. Do not collapse all distinct errors into a generic `"error happened"` message to the point of losing diagnosability.

## 10. Appenders/Handlers and I/O Are Often the Real Bottleneck

Even when formatting is fast, writing to console/file/socket incurs OS and downstream costs. When many threads write to a single sink, the framework may have to synchronize or queue; lock contention and backpressure costs often spike under load.

### 10.1. Do Not Open Resources Per Event

Avoid custom logging like this:

~~~java
// Illustrative anti-pattern, not a standalone program.
try (FileWriter writer = new FileWriter("app.log", true)) {
    writer.write(message + "\n");
}
~~~

Every event can open/close a file, allocate objects, trigger system calls, and lack reliable rotation/encoding policies. Use a backend-managed appender for lifecycle, buffering, rotation, and permissions as required.

### 10.2. stdout in Containers

With Docker/Kubernetes, console logging to stdout/stderr is often easy to integrate with collectors and avoids multiple JVMs contending on a shared file. However, stdout is **not free**: the runtime logging driver, pipes, node disk, and collector all have throughput limits. If the appender flushes continuously or the sink is slow, latency can rise.

Distinguish:

- **Synchronous logging:** the business thread may wait for write/flush depending on appender behavior.
- **Asynchronous logging:** the business thread typically places the event into a queue and returns faster under normal conditions, but the producer still pays event creation/enqueue costs and is subject to the queue-full policy.
- **Direct remote logging:** some appenders perform network calls on the request path; if the backend slows down, an observability outage can cascade into an application outage. Consider an architecturally decoupled collector/buffer.

### 10.3. Flushing and Durability

Do not mechanically call flush/fsync on every event just to feel "safe." Durability levels differ:

1. The event has been passed to the logger.
2. The event is in the queue/buffer.
3. The event has been written to the stream/file by the writer.
4. The data has been accepted by the OS or remote collector.
5. The backend has durably stored and indexed it for querying.

Depending on the backend, there is no guarantee that level 1 implies level 5. If you need a lossless transaction log, design a proper audit/outbox/event store; ordinary operational logs do not replace a transactional source of truth.

## 11. Async Logging: Reduces I/O Waiting, Does Not Eliminate Cost

Async logging typically consists of producers on business threads and a worker consuming the queue:

~~~text
Thread 1 ──► [log event] ┐
Thread 2 ──► [log event] ├─► queue/ring buffer ─► logging worker ─► sink
Thread N ──► [log event] ┘
                          ▲
                          └── bounded capacity
~~~

**Potential benefits:** producers spend less time waiting on sink I/O and writes can be batched to reduce overhead. **Trade-offs:** higher memory footprint, queue processing, context handoff, delayed log visibility, and complex behavior when the queue fills up.

Verify the exact parameters:

| Question | Why It Matters |
| --- | --- |
| What is the queue/ring buffer capacity? | Bursts exceeding capacity can abruptly change behavior |
| What does the producer do when full? | Block, drop, call synchronously, or another policy depending on provider |
| Does an event hold mutable data? | The formatter may run after the state has changed |
| When are MDC/thread name/timestamp captured? | Context must reflect the thread creating the event, not the writer worker |
| How long does shutdown wait to flush? | Logs still in the queue can be lost if the process is killed |
| Are there metrics for queue depth/drops/block time? | Without measurement, real trade-offs are hard to see |
| Are there multiple queues/partitions? | Do not infer global display order from log call order |

With Logback, some applications wrap another appender in `AsyncAppender`. With Log4j 2, there are async appenders or async loggers depending on architecture/configuration. They are not uniform in queue implementation, overflow policy, discard threshold, or ordering; read the documentation for your **exact version** and test under realistic load.

**Do not try to fix a log storm merely by increasing queue size:** if downstream is persistently slower than event generation, a larger queue only delays the time until it fills and increases memory usage. You must reduce emission rate, adjust log levels, optimize the sink, or scale the pipeline appropriately.

## 12. Allocation, GC, and p99 Variance

On a hot path, each event may allocate:

- Temporary strings from concatenation, `String.format`, or `toString`.
- Arrays/varargs or object wrappers for placeholders.
- Immutable DTOs/snapshots built solely for logging.
- Log events, key/value lists, and MDC map copies.
- JSON bytes, buffers, and encoder allocations.
- Throwable stack traces or stack trace strings.
- Lambda/supplier objects if they capture data and the JVM does not scalar-replace them.

A small allocation is not necessarily a bottleneck: the JVM optimizes many short-lived objects very well. But at hundreds of thousands of events per second, allocation rate and GC pressure can affect throughput and tail latency. Do not conclude an optimization from counting lines of code or guessing what the JIT does; measure allocation rate or bytes/op when benchmarking.

### 12.1. Be Careful When Logging Collections and Object Graphs

~~~java
// Bad snippet for a hot path if items is very large.
log.debug("items={}", items);
~~~

If the log level is enabled, the backend may invoke the collection's `toString`, iterating through thousands of elements, building a huge string, and exposing data. A more reasonable approach:

~~~java
log.debug("item_count={} batch_id={}", items.size(), batchId);
~~~

If element data is needed for diagnosis, select only a few safe fields or take a bounded, intentional sample. Do not hold a mutable reference to a list in an async log event and assume the values were captured at call time.

### 12.2. Throwables and Stack Traces

~~~java
// SLF4J snippet: exception is an existing Throwable.
log.error("Failed to publish order_id={}", orderId, exception);
~~~

When an exception has already been created by business logic, passing it to the logger lets the backend format the stack trace only if the event is actually logged. Do not create an exception just to obtain a stack trace on every successful request, such as `new Exception().getStackTrace()`, unless there is a specific diagnostic requirement. For repeated errors, use rate limiting and aggregate metrics instead of logging the same stack trace continuously.

Make sure not to swallow exceptions or alter control flow just to cut logging costs. Error handling decisions belong to application logic, while logging describes those decisions.

## 13. MDC, Trace Context, and Structured Logging on Hot Paths

MDC (Mapped Diagnostic Context), `ThreadLocal`, or context propagation commonly provides `trace_id`, `request_id`, tenant-safe identifiers, and other metadata fields.

**Recommendations:**

1. Set stable fields at the **start of the request/task scope**, rather than calling `MDC.put`/`clear` on every event unnecessarily.
2. Clear or restore context in `finally` when thread pools reuse threads.
3. Propagate context to async tasks using your framework's proper mechanism; MDC does not automatically cross to new threads.
4. Limit map size and cardinality; do not put large payloads, tokens, or sensitive data into context.
5. Let the encoder/collector attach process/pod metadata where appropriate, rather than recreating it on every log line.

Example SLF4J snippet:

~~~java
// Within a request scope; requires an SLF4J backend supporting MDC.
try (org.slf4j.MDC.MDCCloseable ignored =
         org.slf4j.MDC.putCloseable("request_id", requestId)) {
    log.info("request accepted");
    doWork();
} // request_id is removed when the scope closes.
~~~

This illustrates a single scope. With nested scopes or when a key already held a previous value, simply removing it will not necessarily restore the prior value; when needed, snapshot and restore the old map in `finally`. Also note that the actual MDC provider may behave differently when using bridges or async logging.

### Is Structured Logging Always Faster Than Text?

There is no universal answer. A JSON encoder can make collector queries cleaner and avoid regex parsing, but JSON serialization itself consumes CPU and bytes. Different encoders vary in allocation cost, character escaping, timezone handling, and throwable formatting.

Measure against your actual backend:

- Bytes/event, events/s, and compression ratio.
- CPU on producer, logging worker, and collector.
- GC allocation and tail latency when changing encoders/layouts.
- Queryability and schema stability.

When using fields like `category=BUSINESS/TECHNICAL`, do not confuse hot-path optimization with stripping essential schema. Trim unnecessary fields, but keep identifiers needed for incident investigation and auditable events.

## 14. Lock Contention and Impact on Throughput

Logging can slow down multi-threaded paths even if each write uses little CPU, due to waiting on a lock or shared sink:

~~~text
worker-A ─┐
worker-B ─┼──► synchronized appender / shared output
worker-C ─┘               │
                           └── slow file / console / collector
~~~

If a thread holds an application lock and calls a synchronous appender, I/O wait time can extend how long that lock is held:

~~~java
// Snippet: avoid calling slow log I/O while holding a lock when possible.
synchronized (stateLock) {
    updateState();
    log.info("state updated");
}
~~~

When logic permits, capture the data to log under the lock, release the lock, and then log the event outside:

~~~java
String snapshot;
synchronized (stateLock) {
    updateState();
    snapshot = state.summary();
}
log.info("state={}", snapshot);
~~~

This is a snippet; `state.summary()` must produce a consistent, cheap, and safe snapshot by design. Moving the log call outside the lock can **change log ordering across threads**. Do not assume log line order equals business commit order; if event ordering must be verified, use a sequence/event ID or persist events in an appropriate durable mechanism.

Do not wrap every `logger.info` in `synchronized` to force global ordering: it can serialize the entire hot path and drive up p99.

## 15. Measure Properly: Do Not Benchmark by Eye

### 15.1. Metrics to Track

| Metric | What It Measures |
| --- | --- |
| Request throughput (RPS), messages/s | How much work the system completes with logging enabled/disabled |
| p50/p95/p99 latency | Response time distribution, especially the tail |
| CPU utilization, CPU profile | Time spent in formatting, encoder, I/O, and locks |
| Allocation rate, bytes/op, GC pauses | Allocation cost and GC impact |
| Log events/s, bytes/s | Total volume of logs generated and collected |
| Queue occupancy, dropped events, blocking time | Backpressure/overflow status of the async pipeline |
| File/network sink throughput | Bottlenecks in disk/runtime/collector/backend |
| Percentage of error events with sufficient context | Observability effectiveness, not just raw performance |

Optimizing logging CPU while dropping all ERROR logs is not an acceptable improvement. Performance must be evaluated **alongside reliability and operability requirements**.

### 15.2. Using JMH for Microbenchmarks

JMH is well-suited for comparing call-site cost, lazy vs. eager, and parameterized vs. string concatenation in a controlled environment. A proper benchmark generally needs:

- Sufficient warmup for the JIT.
- Multiple iterations and independent forks.
- Inputs that genuinely vary to avoid constant folding or dead-code elimination.
- Backend/appender/level matching the case being compared.
- Separate benchmarks for disabled-level vs. enabled-level cases.
- Measuring throughput and allocation, not just ns/op.
- Not writing massive volumes to a real console simultaneously, which distorts measurements.
- Verifying correctness and GC/thread contention metrics.

You can use JMH with your project's appropriate dependencies and plugins; the Java example in Section 5 **is not a JMH benchmark**. Counting `messageBuilds` proves lazy evaluation semantics; it does not measure real nanosecond timings.

### 15.3. Load Testing in a Production-Like Environment

Microbenchmarks do not fully reflect real application p99. Test at least these modes:

| Scenario | Objective |
| --- | --- |
| INFO, normal load | Baseline |
| DEBUG disabled, eager code | Uncover hidden call-site cost |
| DEBUG disabled, lazy/guarded code | Evaluate CPU/allocation reduction |
| DEBUG enabled for a hot package | Measure the impact of enabling logs for investigation |
| Sink/collector slow or unavailable | Observe backpressure, dropped events, tail latency |
| High-load burst | Check queue overflow/rotation |
| Shutdown/restart | Verify critical events flush as configured |

Change **one variable at a time**, keep workload and hardware comparable, and record both log levels and backend configuration so results are reproducible. Benchmarking with a no-op appender often shows API/formatting cost, but does not reveal real console/file/network costs. Conversely, benchmarking solely with a console may measure terminal limits rather than the logger.

## 16. Refactoring Examples by Situation

### 16.1. Before: Serializing the Entire Object on Every Item

~~~java
// SLF4J snippet
for (Order item : batch) {
    log.debug("item JSON={}", expensiveSerialize(item));
    process(item);
}
~~~

**After:** use a summary and only serialize when actually needed:

~~~java
for (Order item : batch) {
    if (log.isDebugEnabled()) {
        log.debug("item_id={} payload={}",
                item.id(), expensiveSerializeSafeFields(item));
    }
    process(item);
}
log.info("batch_completed count={}", batch.size());
~~~

If `process(item)` can mutate `item`, placing the log before or after must be semantically accurate. Log only safe fields; do not use `serializeSafeFields` as a nice-sounding name for dumping all data.

### 16.2. Before: Duplicate Exceptions on Every Retry

~~~java
// Snippet: an error warning repeated many times.
log.error("Remote unavailable, attempt={}", attempt, exception);
~~~

**After:** count with metrics (or an application counter), log on state transitions, and periodically emit a bounded summary. Still retain a few full records per policy; do not mask prolonged outages.

### 16.3. Before: Synchronous File Write Inside a Lock

~~~java
// Snippet
synchronized (lock) {
    update();
    log.info("updated={}", expensiveSnapshot());
}
~~~

**After:** capture the necessary data, release the lock, and then log. However, ensure the snapshot matches the same version as `update()` if required; do not re-read mutable fields after releasing the lock.

### 16.4. Before: Adding MDC on Every Log Statement

~~~java
// Snippet
for (Event event : events) {
    MDC.put("request_id", requestId);
    log.info("event={}", event.type());
    MDC.remove("request_id");
}
~~~

**After:** set MDC once for the request/task scope; clean up/restore at the right time and do not keep context longer than the work scope.

## 17. Optimizing by Version and Runtime Environment

| Runtime | What to Check |
| --- | --- |
| JUL in Java 17 | `log(Level, Supplier<String>)`, `isLoggable`, Handler config, logger level, `ConsoleHandler` typically writes to stderr |
| SLF4J 1.7 | Placeholders and `isDebugEnabled`; no SLF4J 2-style fluent supplier API |
| SLF4J 2.x | Fluent builder with `Supplier` arguments, compatible backend/provider |
| Logback | `AsyncAppender`, filters, pattern/encoder, logger levels, version-appropriate discard/queue policy |
| Log4j 2 | Async Logger/Async Appender, `Supplier` API, queue/ring buffer, queue-full policy, context capture |
| Spring Boot | `logging.level.*` and actual backend, `logback-spring.xml`/`log4j2-spring.xml` configuration |
| Docker/Kubernetes | stdout/stderr, runtime buffers, rotation, collector, resource limits, and backpressure |

In particular, changing a dependency or logging backend can alter batching behavior, default async policy, and how messages/context are captured. An optimization that is valid for one provider **is not automatically valid** for another. Record the Java version, provider, and benchmark configuration so you can re-verify on upgrades.

## 18. Optimizations That Are Easy to Get Wrong

1. **Putting side effects in log arguments:** when switching to a guard/supplier, business logic can be skipped.
2. **Enabling DEBUG globally to investigate one service:** increases CPU, I/O, and backend costs unnecessarily.
3. **Believing placeholders make all arguments lazy:** Java still evaluates arguments before the call.
4. **Believing async can never drop logs:** the overflow policy determines whether events are blocked, dropped, or fall back.
5. **Believing a logged message is durably stored:** it may only be in a queue/buffer.
6. **Holding mutable objects for a log worker to format later:** the content may differ from the state at event creation.
7. **Benchmarking with a no-op appender and extrapolating production p99:** does not simulate a real sink.
8. **Wrapping every log statement in `synchronized`:** turns logging into a serial bottleneck.
9. **Disabling all ERROR or audit logs to reduce load:** loses signal or violates reliability requirements.
10. **Logging secret payloads:** creates security risks and increases volume.
11. **Splitting log files by dynamic IDs:** increases sink cardinality, file handles, and rotation complexity.
12. **Forgetting to turn off debug after an incident:** prolongs costs and causes log storms.

## 19. Hot-Path Optimization Checklist in Real Projects

**Before making changes:**

- Pick a hot path proven by a profiler or load test to be affected.
- Measure baseline throughput, p95/p99, CPU, allocation, GC, and log bytes/s.
- Check which levels are enabled/disabled and where expensive arguments are evaluated.
- Identify the actual running backend and appender, rather than relying only on the SLF4J API.

**While making changes:**

- Move business logic and side effects out of logging conditionals.
- Use a guard or the right `Supplier` API when computing expensive data solely for logging.
- Keep events compact with sufficient context, and do not serialize sensitive payloads.
- Reduce event count in hot loops; use metrics, summaries, and controlled sampling.
- Avoid I/O under locks and avoid untested custom appenders.
- If using async, define capacity, overflow behavior, context capture, and shutdown flush.

**After making changes:**

- Test with DEBUG disabled **and** enabled; verify business logic is unchanged.
- Verify that messages, trace IDs, stack traces, and critical data remain intact.
- Run load tests with a production-like sink/collector under both normal load and bursts.
- Compare p99, CPU, allocation, and drop count; do not look at only one flattering metric.
- Put guardrails on debug configuration and a rollback plan in place.

## 20. Practice Exercises

### Exercise 1. Evaluating Eager vs. Lazy

Run `LoggingHotPathDemo.java` from Section 5. Explain why two events are logged yet `buildMessage` is called twice, including once that produces no log record. Change the logger level to FINE and predict the new evaluation count. Then run it and compare with the actual output.

### Exercise 2. Fixing a Hot Loop

Given a loop processing 100,000 items with an expensive `serializeOrder(item)`. Write three versions: eager string concatenation, placeholder with the expensive method, and guard/lazy. Disable DEBUG and measure allocation/CPU; explain why the placeholder version fails to avoid calling `serializeOrder`.

### Exercise 3. Testing Under a Slow Sink

Use a test application with an async appender and a controlled sink to simulate slow writes. Increase load until the queue approaches capacity. Collect queue depth, dropped events, request latency, and shutdown flush results. Explain the impact of the overflow policy.

### Exercise 4. Sampling Decisions

An endpoint returns success 50,000 times per minute, and each request emits two INFO logs. Propose changes: summaries/metrics, keeping ERRORs, and sampling a fraction of debug logs by trace ID. Clearly identify which audit or business-critical events must not be blindly sampled.

### Exercise 5. Reviewing Locked Code

Find a `synchronized` block containing a log that builds a large JSON payload. Design a safe snapshot and release the lock before serializing/writing if business requirements allow. Measure p99 across multiple threads and verify that log ordering may change.

## 21. Summary

To optimize logging on Java hot paths, **do not look only at the logger call**. Costs can arise before the logger because Java evaluates arguments eagerly, in the encoder during formatting or allocation, in the appender due to lock/I/O contention, and in the queue/collector when downstream is slow. Use lazy `Supplier`/guards for expensive arguments when levels are disabled, reduce unnecessary events, choose appropriate formats/sinks, and manage async backpressure.

Proper optimization must preserve business behavior, context, and critical logs. Measure improvements across CPU, allocation, p95/p99, throughput, **and** log drop rate; do not turn logging into a source of inaccuracy or data loss just to achieve better benchmark numbers.

### References

- Oracle Java 17 – java.util.logging.Logger and Supplier overloads: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 – Level: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Level.html
- Oracle Java 17 – Handler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html
- SLF4J User Manual, parameterized and fluent logging API: https://www.slf4j.org/manual.html
- Logback Manual – Configuration: https://logback.qos.ch/manual/configuration.html
- Logback Manual – Appenders: https://logback.qos.ch/manual/appenders.html
- Apache Log4j 2 – Performance: https://logging.apache.org/log4j/2.x/manual/performance.html
- Apache Log4j 2 – Async Logging: https://logging.apache.org/log4j/2.x/manual/async.html
- OpenJDK Java Microbenchmark Harness: https://github.com/openjdk/jmh
