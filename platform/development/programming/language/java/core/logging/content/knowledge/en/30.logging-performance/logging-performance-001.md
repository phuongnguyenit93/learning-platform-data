# Logging Overhead in Java Core Logging

## 1. Where Can Logging Consume Resources?

**Logging overhead** is the amount of resources a Java application consumes from the moment it prepares data for an event, invokes the logger, checks the log level, formats, encodes, and dispatches the event until it is written to the console, a file, or a collection system. It can affect CPU, heap/GC, lock contention, I/O, network, storage, and request processing latency.

Example with SLF4J:

```java
logger.debug("orderId={} status={}", orderId, status);
logger.debug("order={}", loadAndSerializeOrder(orderId));
```

If `DEBUG` is disabled, the first line is usually very lightweight when `orderId` and `status` are already available. On the second line, **Java still calls `loadAndSerializeOrder(orderId)` before invoking `debug(...)`**. If that method queries a database or serializes a large object, the cost is still incurred even though no DEBUG line is emitted.

Therefore, reducing log volume only solves part of the problem; you need to understand **the work done at the call site**, inside the logger/backend, and across the transport pipeline. The goal is to avoid unnecessary log data while still keeping enough events for diagnostics and operations.

## 2. Lifecycle of a Log Event

```text
Business code
  -> evaluate arguments, compute strings/payload
  -> logging API (JUL, SLF4J, ...)
  -> check level/filter/sampling
  -> create event, timestamp, thread, MDC
  -> format message, Throwable, encode JSON/text
  -> appender: synchronous or async queue
  -> console/file/socket/collector
  -> ingest, index, storage
```

The exact order may vary depending on the framework, encoder, and async implementation. However, **Java method arguments are evaluated before the call**, so a logger filter cannot refund the time already spent building the arguments.

| Stage | Resources Potentially Consumed | Key Considerations |
| --- | --- | --- |
| Argument preparation | CPU, heap, sometimes DB/network | Payload-building methods run even if logging is disabled |
| Level/filter check | CPU | Complex filters also incur overhead |
| Event creation | Allocation, clock, thread context | Creating LogRecord, capturing MDC, caller data |
| Formatter/encoder | CPU, buffer | Placeholder substitution, JSON escaping, stack trace |
| Appender/queue | Lock, memory, contention | Synchronous waits on I/O; async must enqueue |
| Sink/transport | Disk/network/flush/retry | Console, file, OTLP, agent |
| Cloud backend | Ingest/index/storage | High volume and long retention increase cost |

Distinguish between **latency on the request thread** and **total system cost**. Moving logging from a synchronous to an asynchronous appender can reduce how long the request waits, but it still uses CPU, memory, and network on the consumer thread or in another process.

## 3. Eager Arguments: The Biggest Trap

All three of the following calls build data before the backend knows whether it needs to be written:

```java
logger.debug("payload=" + expensivePayload());
logger.debug(String.format("payload=%s", expensivePayload()));
logger.debug("payload={}", expensivePayload());
```

On the first line, string concatenation runs eagerly. The second line calls `String.format` eagerly. The third line uses a placeholder, allowing the backend to defer assembling the message, yet **`expensivePayload()` still runs**. If this method queries a DB, iterates over a large collection, or builds JSON, the cost does not disappear.

Similarly:

```java
logger.debug("user={}", user.toString());
```

`toString()` is called immediately. With SLF4J, if formatting is only needed when the level is enabled, you can pass the object directly:

```java
logger.debug("user={}", user);
```

The second approach usually lets the backend decide whether to call `toString()`. However, the `user` object must still be created beforehand, and `toString()` itself needs to be safe, free of side effects, and free of data leaks.

### Using Parameterized Logging Properly

```java
logger.info("requestId={} result={}", requestId, result);
```

This approach is generally better than manual string concatenation when the log might be disabled. With one or two arguments, some SLF4J overloads avoid allocating a varargs array; however, Java may still perform primitive boxing, call getters, or create temporary objects depending on the case. Do not draw firm conclusions about allocated bytes without benchmarking on the actual JDK and provider.

Log values can be formatted as JSON, but **structured logging is not free either**. The encoder must escape strings, process timestamps, convert numbers, format exceptions, and possibly copy buffers. Investing in structured formatting improves querying and correlation; optimization should weigh operational benefits rather than looking solely at formatter CPU.

## 4. Use Guards or Suppliers When Payloads Are Truly Expensive

If the work to build the data is significant, check the log level first:

```java
if (logger.isDebugEnabled()) {
    String details = buildExpensiveDetails(order);
    logger.debug("order details={}", details);
}
```

This is an SLF4J snippet; `logger`, `order`, and `buildExpensiveDetails` must be declared in the program. The guard avoids calling the expensive method when DEBUG is disabled. It makes sense for serialization, iterating over many records, or performing computations; there is no need to wrap a call that simply passes an already available ID.

The JDK's **JUL (java.util.logging)** has overloads that accept a `Supplier<String>`:

```java
logger.log(java.util.logging.Level.FINE,
        () -> "details=" + buildExpensiveDetails(order));
```

When the `FINE` level is disabled on the logger, the supplier is not invoked. The work must stay **inside the lambda**; if you compute it beforehand and just pass the variable into the lambda, the benefit is lost.

**SLF4J 2.x** provides fluent logging with suppliers for arguments:

```java
logger.atDebug()
        .addArgument(() -> buildExpensiveDetails(order))
        .log("details={}");
```

This snippet requires SLF4J 2.x and a compatible provider; SLF4J 1.7 does not have the same fluent API. A supplier can avoid call-site work when the level is disabled, but if a filter at the appender/collector later drops the event, the payload may have already been built. Do not put business side effects inside a supplier, because when the log is not accepted, it may not run.

One detail: the log level can change between the `isDebugEnabled()` check and the `debug(...)` call. Guards are meant to avoid eager computation, not to act as a protocol guaranteeing atomic event writes.

## 5. Complete Java 17 Example: Eager, Lazy, and Guarded

The example below uses **only the JDK** to illustrate evaluation order. The logger accepts `INFO` and above and disables `FINE`. `buildPayload()` increments a counter each time it is called. The handler only counts received events without outputting additional log lines.

Create the file `LoggingCostDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingCostDemo {
    private static final AtomicInteger COMPUTATIONS =
            new AtomicInteger();
    private static final AtomicInteger PUBLISHED =
            new AtomicInteger();

    private static String buildPayload() {
        COMPUTATIONS.incrementAndGet();
        return "payload";
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("example.logging.cost");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    PUBLISHED.incrementAndGet();
                }
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };

        sink.setLevel(Level.ALL);
        logger.addHandler(sink);
        try {
            logger.fine("eager=" + buildPayload());
            int eager = COMPUTATIONS.get();

            logger.log(Level.FINE,
                    () -> "lazy=" + buildPayload());
            int lazy = COMPUTATIONS.get();

            if (logger.isLoggable(Level.FINE)) {
                logger.fine("guarded=" + buildPayload());
            }
            int guarded = COMPUTATIONS.get();

            logger.info(() -> "visible=" + buildPayload());

            System.out.printf(
                    "eager=%d lazy=%d guarded=%d final=%d published=%d%n",
                    eager, lazy, guarded,
                    COMPUTATIONS.get(), PUBLISHED.get());
        } finally {
            logger.removeHandler(sink);
            sink.close();
        }
    }
}
```

Compile and run:

```bash
javac LoggingCostDemo.java
java LoggingCostDemo
```

Exact stdout:

```text
eager=1 lazy=1 guarded=1 final=2 published=1
```

Why:

1. The `fine("eager=" + ...)` call still invokes `buildPayload()`: `eager=1` even though FINE is disabled.
2. The supplier in `logger.log(Level.FINE, ...)` is not invoked: `lazy=1`.
3. The guard does not satisfy `isLoggable(Level.FINE)`, so `guarded=1`.
4. `info` has its level enabled, so the supplier runs once, `final=2`, the Handler receives one event, and `published=1`.

This is a **semantics verification example**, not a nanosecond/op benchmark. `AtomicInteger` and the test Handler also have overhead; to evaluate production performance, you must measure the actual logger, formatter, and appender.

## 6. Message Creation and Stack Trace Costs

Each log record can allocate several temporary objects: strings, wrappers, varargs arrays, events, MDC copies, JSON buffers, byte arrays, or stack traces. When logging at high rates, an increased allocation rate can put pressure on GC and worsen p95/p99 latency.

Notable sources of overhead:

- **`toString()` on large objects** may traverse many fields, trigger lazy getters, or serialize unnecessary data.
- **`String.format`** does more processing than simple string concatenation; calling it before the logger incurs cost even when the log level is disabled.
- **Throwable**: creating `new Exception()` can capture a stack trace; do not instantiate a new exception for every normal checkpoint.
- **Caller location**: to record file, class, method, and line number, the backend may have to inspect the stack; in async logging, this information sometimes needs to be captured eagerly on the producer thread.
- **MDC/trace context**: adding or snapshotting too many fields makes each event larger and increases copying cost.
- **Long messages or complex JSON**: increase serialization CPU, buffer usage, network bytes, and indexing cost.

Example of avoiding dumping an object when only core information is needed:

```java
logger.info("orderId={} status={} itemCount={}",
        order.getId(), order.getStatus(), order.getItemCount());
```

Even so, the getters are still evaluated. Do not call getters that trigger I/O unnecessarily; if the log data is complex, use a guard or supplier.

When an error is actually caught, you can log the existing `Throwable`:

```java
try {
    processOrder(orderId);
} catch (RuntimeException ex) {
    logger.error("Order failed id={}", orderId, ex);
    throw ex;
}
```

This is an SLF4J example that requires `processOrder`, `logger`, and `orderId` from the application. `throw ex` is an error-handling choice depending on the contract; avoid having multiple layers log the same stack trace repeatedly, and do not create a new Throwable solely to capture a call stack when it is not needed.

## 7. GC, Synchronization, and Throughput Costs

For applications handling high request volumes, a slightly expensive log call multiplied millions of times can become significant. Estimation model:

```text
events_per_minute = requests_per_minute × logs_per_request

serialized_bytes_per_day ≈ events_per_day × average_bytes_per_event

total_cost ≈ log_creation + encoding + dispatch + transport
             + contention + GC + ingest/storage
```

These additions are only a conceptual model and do not mean CPU or latency scales strictly linearly with event count. Concurrent threads, JIT, buffering, compression, GC, and network latency make the relationship complex.

For example: 20,000 requests/minute, with each request producing 5 INFO logs, means roughly **100,000 events/minute**. Reducing duplicate records to 2 logs/request lowers volume to **40,000 events/minute** under unchanged traffic. That reduces load on the formatter, transport, and ingest; it does not imply application throughput increases by an exact factor of 2.5x.

Contention also arises when multiple threads write through a shared synchronous appender, file lock, or shared queue. Some formats require timestamp or caller extraction on every event. On thread pools, copying a large MDC can also increase allocations. Prefer logging IDs, statuses, durations, and error codes with diagnostic value rather than full requests/responses.

## 8. Async Logging: Reduces Request Waiting, Does Not Eliminate Total Cost

**Synchronous logging** can format and write directly on the thread emitting the log. **Asynchronous logging** typically writes to a queue for a consumer to process later. Async reduces waiting time on business threads when the queue has capacity, but the producer still has to prepare the event, snapshot context, and enqueue it; the consumer still encodes and performs I/O.

```text
worker A ---\
worker B ----+--> async queue --> consumer --> file/console/network
worker C ---/         |
                     +--> full: block / discard / fallback depending on config
```

| Behavior When Queue Is Full | Trade-off |
| --- | --- |
| Block producer | Can preserve events but increases latency or causes timeouts |
| Drop some DEBUG/INFO levels | Protects throughput but loses information; must count dropped events |
| Synchronous fallback write | Can cause latency spikes under high load |
| Spool/retry | Consumes memory/disk; must be bounded and tested for recovery |
| Pre-queue sampling | Reduces load early but must protect critical events |

Do not assume async guarantees **exactly-once** delivery. When a process crashes, unflushed events can be lost; when retrying after a network timeout, duplicate logs can appear. Check the shutdown/flush policy, queue capacity, backpressure, and retry behavior of your actual framework/backend.

## 9. Sampling and Filter Placement Affect Cost

Sampling repetitive successful INFO logs can reduce storage and network usage. However, **the later filtering happens, the less upstream log-creation cost is avoided**.

| Where Filtering Happens | Main Savings | Potential Remaining Cost |
| --- | --- | --- |
| Guard/call site before payload creation | Avoids data creation, event creation, and dispatch | Log-level check |
| Logger level/filter | Avoids formatting/dispatch when event is rejected | Arguments already evaluated |
| Appender/queue | Avoids some downstream I/O | Event creation and possibly encoding |
| Agent/Collector | Reduces downstream ingest/storage | JVM CPU and transport prior to the filter |
| Backend storage | Reduces retention/indexing | Most prior event creation and transmission |

When you want to trace the progression of a request, consistent sampling by request/trace ID is usually easier to investigate than randomly keeping individual lines independently. ERROR, audit, and mandatory-retention events need separate policies. Do not use a sampled log set to calculate exact error/traffic rates; use independent metrics when full-traffic figures are needed.

## 10. Benchmarking Logging Properly

Measuring a loop with `System.nanoTime()` without warmup is easily skewed by JIT, GC, dead-code elimination, terminal buffering, and I/O. For microbenchmarks in Java, **JMH** helps configure proper warmup, JVM forks, iterations, and state; you still need to understand what you are measuring.

Separate into:

1. **Disabled level:** measure only the call-site cost of string concatenation, parameterized logging, guards, and suppliers.
2. **Enabled sink without I/O:** measure event creation, formatter, and allocations within the JVM.
3. **Enabled real sink:** file/console/network/OTLP, multiple threads, message sizes, and queue settings matching production.
4. **End-to-end:** measure request throughput, p95/p99 latency, bytes/sec, GC, queue backlog, dropped logs, and ingest latency.

Document the JDK/GC, hardware, API/backend version, format, log level, thread count, event size, queue capacity, buffering, and sink. Do not conclude that logger A is always faster than logger B based solely on a stdout benchmark on a personal machine. An improvement that reduces ns/op for disabled DEBUG may not help much if the real bottleneck is the console or Collector.

| Metric | Meaning |
| --- | --- |
| Throughput or ns/op | Time per operation in the defined workload |
| Allocation B/op, bytes/sec | Memory and GC pressure |
| CPU, GC pause | Overall JVM work |
| p95/p99 request latency | Impact on latency-sensitive requests |
| Queue depth/drop/retry | Congestion and signal loss |
| Serialized bytes/ingest rate | Log transmission and storage cost |

For async tests, wait for flush or a completion condition **with a timeout** according to the backend; do not use `Thread.sleep(1000)` as proof that all events were persisted. Verify unique event IDs and counts according to the drop/sampling policy.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `logger.debug("x=" + expensive())` | Builds data even when DEBUG is off | Guard or supplier |
| `logger.debug("{}", expensive())` thinking it is fully lazy | Placeholder is lazy, argument is eager | Guard/supplier for expensive calls |
| Calling `toString()` before the logger | Eager formatting and potential data exposure | Pick specific fields or let backend format when needed |
| Dumping large objects/responses every request | Steep CPU/heap/network increase | Log ID, status, duration, error code |
| Creating a new exception for every checkpoint | Expensive stack trace generation | Only log real Throwables when needed |
| Enabling caller file/line everywhere | Stack walk increases overhead | Enable purposefully |
| Enabling broad DEBUG in production | Volume explosion | Limit scope and duration |
| Treating async as free | Queue/consumer/GC still consume resources | Measure both request and total CPU |
| Filtering at the backend hoping to cut JVM CPU | Events are already created and sent | Filter early when appropriate |
| Not measuring dropped logs | Unnoticed signal loss during overload | Monitor queue, drop, and retry metrics |
| Benchmarking in an IDE with console output | I/O and JIT skew conclusions | Test with warmup and realistic load |
| Deleting all logs to improve speed | Impossible to investigate incidents | Keep critical logs, reduce duplicate events |

## 12. Logging Overhead Optimization Checklist

Before modifying a logging system, check each area in turn:

- **Call site:** are strings, JSON, queries, heavy getters, or exceptions being built/created even when the level is disabled?
- **API:** are parameterized logging and version-compatible guards/suppliers used when payloads are expensive?
- **Backend:** are too many fields, stack traces, MDC entries, caller locations, or duplicate appenders being formatted?
- **Concurrency:** are multiple threads experiencing contention, queue backlogs, drops, or producer blocking?
- **Storage:** are there repetitive INFO logs, excessive retention, or unnecessary indexed fields?
- **Observability quality:** after optimization, are error/audit logs, correlation IDs, and request investigation capabilities still intact?
- **Measurement:** have CPU, allocations, GC, throughput, p95/p99, network bytes, and dropped events been compared before and after?

**Remember:** logging overhead can occur **even before the logger decides whether to store the event** because Java evaluates arguments eagerly. The most impactful optimization steps are usually avoiding unnecessary payload construction, reducing duplicate events and data size, and then configuring encoders/appenders and pipelines appropriately based on actual measurements.
