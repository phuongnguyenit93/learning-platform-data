# The Cost of Logging in Java

## 1. Logging Provides Value, but Consumes Resources

Logging helps trace events, diagnose bugs, explain state transitions, and monitor operations. In return, a log record can go through multiple stages: expression evaluation, level filtering, log object creation, message formatting, passing to a handler/appender, writing to a file/console/network, and then storage and indexing. These stages consume **CPU, memory, I/O, bandwidth, storage capacity, and request processing time**.

The cost depends on logging frequency, message size, log level, formatter type, synchronous/asynchronous write path, collection pipeline, and actual load. Therefore, there is no universal answer like "one log line costs X ms". The design goal is to keep the traces that genuinely aid diagnosis while controlling the resource cost paid.

A useful evaluation should answer:

- How many **log events/second** are generated per instance and across the entire system?
- When a log level is disabled, does the program still **evaluate arguments, concatenate strings, or serialize objects**?
- When logging is enabled, which part runs on the **request-serving thread** and which part runs on the log-processing thread?
- How many **actual bytes** does each event cost when written and stored? How long is it retained? Is it replicated/indexed?
- When the destination is slow, does the system **block, grow memory, retry, or drop logs**?
- Do the events being recorded actually help reconstruct the context of an error or monitor operating conditions?

## 2. Where Does the Cost Sit Along a Log Record's Path?

~~~text
Business code
  -> evaluate log call arguments (Java evaluates arguments)
  -> check level and filter at logger
  -> create record, capture timestamp/thread/context/Throwable
  -> formatter or encoder converts to text/JSON
  -> handler/appender; write directly or enqueue
  -> console, file, log driver, or network collector
  -> compression, indexing, retention, querying
~~~

**This diagram is a conceptual model.** Different frameworks may reorder these stages; the formatter may run on the application thread or a worker thread depending on configuration, and handler-level filtering may occur after the message has already been computed.

| Component | Potential Costs | Symptoms |
| --- | --- | --- |
| Message construction | String concatenation, calling `toString()`, building JSON, reading expensive values | CPU/allocations rise even when the log level is disabled |
| Record and metadata | Intermediate objects, timestamp, caller location, stack trace, context | Heap/GC increases, profiler shows formatter or stack inspection |
| Synchronization | Lock contention, flush, shared output stream | Threads get blocked, low throughput under load |
| I/O | Console/file writes, disk sync, rotation/compression, network sends | Disk/network usage rises, p95/p99 latency stretches |
| Asynchronous queue | Enqueue/dequeue, holding many objects waiting to be written, backpressure | Queue depth grows, GC pressure or dropped events |
| Centralized logging system | Ingestion, parsing, indexing, replication, retention | Stored GB and ingestion/query bills increase |
| Redundant data | Duplicate records, per-iteration loop logs, oversized payloads | Important signals get buried in "noise" |

Do not measure only the application's CPU. When logs are offloaded to a collector or an async worker, the cost may move off the calling thread, but it still exists elsewhere in the system.

## 3. Disabled Logs Are Not Necessarily "Free"

### 3.1. Call Arguments Are Evaluated First

In Java, expressions passed to a method are evaluated before that method is called:

~~~java
// Illustrated inside a method that already has LOG and order.
LOG.fine("order=" + expensiveOrderDescription(order));
~~~

If `FINE` is disabled, the logger will not emit a record, but `expensiveOrderDescription(order)` has already run. It might invoke an expensive `toString()`, perform computations, load data, or build a large string.

The same issue applies with parameterized arguments:

~~~java
// Java Util Logging (JUL):
LOG.log(Level.FINE, "order={0}", expensiveOrderDescription(order));
~~~

Placeholders can defer **formatting** the event, but the argument `expensiveOrderDescription(order)` is still evaluated by Java before the `LOG.log(...)` call begins. This same principle applies when using logging APIs outside the JDK such as SLF4J: placeholder syntax does not make argument expressions automatically lazy.

### 3.2. Level Guards or `Supplier`

If the message only needs to be computed when the level permits:

~~~java
// Illustrated in a scope that has LOG and order:
if (LOG.isLoggable(Level.FINE)) {
    LOG.fine("order=" + expensiveOrderDescription(order));
}

// JUL supports Supplier<String> since Java 8:
LOG.fine(() -> "order=" + expensiveOrderDescription(order));
~~~

`Logger.isLoggable(Level.FINE)` avoids executing the branch when the level is not accepted. The overload taking `Supplier<String>` only invokes the lambda when the logger level matches. Use this approach for expensive messages; for short constant strings, the optimization may be negligible.

**Do not put side effects inside a log-producing lambda.** Never update data, call state-mutating APIs, or perform required business checks inside a `Supplier`: if logging is disabled, the lambda will not run. Logging is an observability activity, not a required step for business logic correctness.

JUL can filter at **two layers**: the logger and the handler. If the logger accepts `FINE` but the handler only accepts `INFO` and above, record/message creation can still happen before the handler filters it out. Therefore, check both the logger level and the handler level, rather than only looking at the lines printed to the console.

### 3.3. Standalone Example Running on Java 17+

Create the file **LoggingCostDemo.java**:

~~~java
import java.util.logging.Level;
import java.util.logging.Logger;

public class LoggingCostDemo {
    private static final Logger LOG =
            Logger.getLogger(LoggingCostDemo.class.getName());

    private static int detailBuilds = 0;

    private static String buildDetails() {
        detailBuilds++;
        return "payload=" + "abcd".repeat(4);
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO); // FINE is disabled.

        LOG.fine("eager: " + buildDetails());
        LOG.fine(() -> "lazy: " + buildDetails());

        if (LOG.isLoggable(Level.FINE)) {
            LOG.fine("guarded: " + buildDetails());
        }

        System.out.println("detailBuilds=" + detailBuilds);
        System.out.println("fineEnabled=" + LOG.isLoggable(Level.FINE));
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 LoggingCostDemo.java
java LoggingCostDemo
~~~

Exact **stdout** output:

~~~text
detailBuilds=1
fineEnabled=false
~~~

The first call evaluates `buildDetails()` before filtering, incrementing the counter from 0 to 1. The lambda and the level-guarded branch do not call `buildDetails()` because `FINE` is disabled. The two stdout lines come from `System.out.println` used for the exercise, not from the logger. The example disables parent handlers and attaches no other handler, so no log output is emitted to the screen.

If you change `LOG.setLevel(Level.INFO)` to `Level.FINE`, all three message-building expressions run, producing `detailBuilds=3` and `fineEnabled=true`. Even then, no log output appears automatically without a configured handler. Lesson: **event creation cost** and **event output cost** are two separate parts to examine.

## 4. Costs When Logging Is Actually Enabled

### 4.1. CPU, Objects, and Garbage Collection

Logging at `INFO`/`DEBUG` may require building messages, computing metadata fields, extracting exception details, handling request context, and encoding JSON/text. Many calls inside loops allocate strings, argument arrays, and short-lived records, increasing the allocation rate and triggering more frequent GC runs. Logging entire objects can trigger expensive `toString()` calls or include unnecessary data.

A long stack trace generates substantial data and formatting overhead. If the same exception is logged at multiple layers and then rethrown, the application creates duplicate logs and makes it harder to tell where the error is actually handled. Prefer logging the exception with context at the boundary responsible for error reporting; other layers should only add information when needed.

With formatters, including the caller's class/method/line can require stack inspection; in async configurations, check when the framework captures this information. Avoid enabling full caller location for every log on a hot path unless there is a specific need.

### 4.2. I/O and Latency

Logging to stdout inside a container still goes through an output stream and a log driver; logging to a file still requires disk writes, rotation, and possibly compression; logging over the network requires serialization, transmission, retries, or batching. A slow sink can stretch **p95/p99 tail latency** even if the average cost of a single line is small.

"Synchronous" does not mean every line is guaranteed to be `fsync`ed to disk immediately; many handlers use buffering. And "asynchronous" does not mean zero I/O cost: the work is merely shifted to another thread or another point in time.

### 4.3. Storage, Indexing, and Retention

Each event consumes bytes on the wire and at the storage destination. Total cost depends on event count, bytes/event, retention period, replicas, compression, indexes, and queries. With structured data, high-cardinality fields (such as request IDs) can make indexing/searching more expensive, depending on the collection solution. Do not log thousands of fields just because the system supports JSON.

## 5. Synchronous vs. Asynchronous: Strengths and Trade-Offs

### Synchronous

A synchronous handler/appender performs its write work on the calling thread's execution path. When the sink is slow, business threads may have to wait on the formatter, locks, or I/O; this directly affects throughput and latency. The synchronous path is generally simpler to observe, but it must be measured under concurrent load and when the collector/file system runs into trouble.

### Asynchronous

An async logger/appender typically places events into a queue so a worker can handle encoding/writing later. This **can reduce request wait time** and enable I/O batching, but it does not eliminate CPU, memory, or storage costs. It also introduces risks:

- **Bounded queue:** when full, depending on the library and configuration, it will block, drop, write on the calling thread, or apply another policy. Do not assume a single universal behavior across all appenders.
- **Oversized queue:** increases the number of objects retained in the heap, log delivery delay, and GC pressure; an unbounded queue can exhaust memory.
- **Crash/kill:** records still sitting in the queue/buffer may never reach the destination. Shutdown hooks and flushes reduce this risk, but do not provide an absolute durability guarantee.
- **Thread context:** data such as a framework's MDC may need to be captured into the record; not every thread-local transfers automatically to the worker.
- **Log collector failures:** without monitoring queue depth, dropped event counts, and drain time, the application may appear to run "fast" while losing traces right when an investigation is needed.

Example: a service processes requests in about 10 ms, but the log sink occasionally stalls for 40 ms. Async can reduce the direct impact on requests, yet if the sustained event production rate exceeds the consumption rate, the queue will eventually fill up. The design must explicitly state the priority between business latency and log retention.

If a class of events requires **preservation for reconciliation/audit requirements**, design a reliable write path suited to those requirements rather than treating an in-memory logger queue as a durable store.

## 6. Estimating Cost by Frequency

Let:

- `R` = number of log events per second **after filtering and sampling**.
- `S` = average bytes per encoded record, including the fields written.
- `T` = total retention time in seconds.
- `K` = number of raw data replicas if the storage mechanism replicates data.

Estimation formulas:

~~~text
Bytes/second = R × S
Raw stored bytes ≈ R × S × T
Bytes for K replicas, before compression and indexing ≈ R × S × T × K
~~~

Suppose a system logs **1,000 events/second**, averaging **250 UTF-8 bytes/event**, retained for **30 days**:

~~~text
1,000 × 250 = 250,000 bytes/second
250,000 × 86,400 = 21,600,000,000 bytes/day
21,600,000,000 × 30 = 648,000,000,000 bytes/30 days
                         = 648 GB in decimal units
~~~

Three full replicas equal roughly **1,944 GB (1.944 TB)** of raw data before compression and indexing. These numbers are an illustrative calculation, not a billing invoice: compression, replication, metadata, ingestion pricing, querying, storage tiering, and retention all change the actual outcome.

**Bytes are not characters.** A Java `String` counts in UTF-16 code units, while logs are usually encoded as UTF-8. Non-ASCII characters (such as Vietnamese) can take multiple bytes; JSON also adds field names, delimiters, and escapes. Measure log size after encoding or from the collection system, rather than counting characters in source code.

If you reduce frequency to 10% by dropping/sampling non-essential DEBUG records, the data volume of **that record group** drops proportionally (assuming average size stays constant). Do not extrapolate that total system cost drops by 90% if other log types are still kept and fixed costs remain.

## 7. Reducing Cost While Preserving Troubleshootability

### 7.1. Log at the Right Level for the Right Events

- Use levels that match the event's significance. JUL has `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, and `FINEST`; other frameworks may use `ERROR`, `WARN`, `DEBUG`, and `TRACE`.
- At `INFO`, favor key state milestones (startup, job completion, outcomes of major operations); avoid printing every loop iteration, every row, or the full payload of every request by default.
- At detailed levels such as `FINE/DEBUG/TRACE`, enable them only for the scope and duration needed for investigation, and consider capping record counts.
- For frequently repeating events, **metric counters/histograms** can represent occurrence counts and latency better than millions of text lines. Logs remain valuable for preserving the context of specific events.
- Do not repeat the same exception across multiple layers if no new information is added.

There is no mandatory rule that every API must write a per-request access log at the exact same level; observability requirements and volume depend on the application.

### 7.2. Avoid Computing Unnecessary Log Data

Use `Supplier`, `isLoggable`, or conditional computation when messages are expensive. Parameterized logging reduces formatting work, but does not defer evaluation of all arguments. If an object is too large, log only the needed fields such as `operation`, `requestId`, `outcome`, `durationMs`, and a safe error code.

Do not serialize entire objects or call expensive `toString()` methods as a default way to build messages. With ORM objects, `toString()` can access unintended properties or associations; never rely on side effects to print a log.

### 7.3. Manage Log Volume and Size

You can use sampling, rate limiting, or summary reporting for repeated events: for instance, instead of logging a warning on every retry attempt, log the final retry count, cause, and outcome. Sampling has a trade-off: rare errors may go unrecorded. For events that must be stored in full, choose a separate policy matching the reliability requirements.

Configure appropriate rotation, retention, compression, and index policies. Avoid high-cardinality fields if they do not serve useful queries. Distinguish temporary technical debug logs from operational reporting data that requires long-term retention.

### 7.4. Control Backpressure and Security

When using async logging, choose a bounded queue, clear alert thresholds, and an explicit full-queue policy. Measure **queue depth**, **enqueue/block time**, **dropped events**, and flush duration on shutdown. Test when the sink is unresponsive as well.

Do not log passwords, tokens, session cookies, application secrets, or excessive personal data. Selecting only safe fields right at the logging site is usually easier to control than logging everything and masking with regex afterward. Data masking also costs CPU and can miss new fields; never skip data protection requirements in the name of saving performance.

## 8. How to Measure Logging Cost More Accurately

A useful benchmark should include a **baseline** and comparison configurations under the same workload, JDK version, hardware, GC policy, and log collection system:

| Case | Purpose |
| --- | --- |
| DEBUG/FINE level disabled | Measure remaining overhead at call sites, argument evaluation, and filtering |
| Detailed level enabled, very light handler | Estimate record creation/formatting cost inside the JVM |
| Detailed level enabled, production-like sink | Measure real console/file/network/collector overhead as well |
| Async with a specific queue configuration | Observe request latency, backlog, GC, and drops/blocks |
| Fewer fields or sampling | Check volume/cost reduction and whether diagnostic power remains sufficient |

Track **request/s throughput, p50/p95/p99 latency, CPU, allocation rate, heap/GC, disk bytes, network bytes, log events/s, bytes/event, queue depth, dropped events**, and ingestion/storage cost if available. Measure performance while also verifying that the application still behaves correctly.

How to proceed:

1. Generate a realistic representative load: concurrent requests, varied payload sizes, realistic success/failure ratios, and an appropriate number of exceptions.
2. Warm up the JVM to avoid confusing class loading/JIT effects with logging overhead. Keep the environment configuration identical across comparisons.
3. Run multiple iterations and compare result distributions rather than relying on a single fast or slow run. Determine whether the sink or collector is the bottleneck.
4. Use **Java Flight Recorder (JFR)** or a profiler to inspect CPU, allocations, GC, and lock contention. To isolate a small Java operation, use a proper microbenchmarking tool like **JMH**; hand-written `System.nanoTime()` loops are easily skewed by JIT, compiler optimizations, and environmental noise.
5. Test slow/disconnected sink states, full queues, and shutdown. A configuration that performs well under normal conditions can spike p99 or lose logs during an incident.

**Note:** `LOG.info(...)` returning quickly does not prove that the entire logging pipeline is cheap. Async shifts work to another thread; buffering defers I/O until later. Conversely, benchmarks printing directly to an IDE console can be throttled by UI rendering and do not represent production.

## 9. Practical Scenarios

### A. Logging Inside a Large Loop

A job processes **500,000 records** and each record produces a 200-byte log: a single run emits around **100 MB of raw data**, before metadata, indexing, and replicas. If this runs repeatedly, log volume can far exceed its diagnostic value.

Appropriate approach: log `jobId`, start/end timestamps, success/failure counts, and duration; use metrics for totals and rates. Enable detailed logging only by specific ID, data sample, or investigation window. When you need to find failing records, log the ID and actual failure reason rather than every valid record.

### B. Overloaded Log Collector

An API emits 15,000 events/s while the consumer can only process 12,000 events/s over a sustained period. The backlog grows by an average of **3,000 events/s**, so an initially empty 10,000-event queue can fill up in roughly **3.33 seconds** if there is no variance and no throttling. Once the queue is full, the application may slow down or drop logs depending on the policy. Reducing low-value events, scaling sink capacity, bounding the queue, and alerting on backlog/drops must all be considered together.

## 10. Common Mistakes

| Mistake | Consequence | Better Practice |
| --- | --- | --- |
| Assuming a disabled log level uses zero resources | Arguments are still evaluated and strings built | Use lazy evaluation/guards when messages are expensive |
| Using placeholders and assuming all arguments are lazy | CPU-heavy functions run before the logger call | Avoid expensive expressions or guard by level |
| Logging `INFO` inside hot loops | Sudden spikes in CPU/I/O/storage | Use metrics, phase-level logs, or sampling |
| Logging oversized or duplicate objects/`Throwable`s | Higher allocations, bytes/s, harder to read | Log specific fields and stack traces at the right boundary |
| Assuming async is always fast and lossless | Queues can fill; crashes cause data loss | Measure backpressure/drops and design appropriate durability |
| Measuring only `LOG.info` call duration | Ignores workers, I/O, indexing, retention | Measure end-to-end and p95/p99 |
| Treating stdout as free | Console/log driver still incurs I/O | Test against the real output destination |
| Logging secrets for debugging convenience | Risk of data leaks through the log pipeline | Log safe fields only, restrict access/retention |

## 11. Self-Check Exercises

1. Run **LoggingCostDemo.java**, change `Level.INFO` to `Level.FINE`, and explain why the counter changes from `1` to `3`, even though the program still has no handler printing log lines.
2. Given 2,000 events/s, 500 bytes/event, and a 7-day retention period, estimate the raw data size in decimal GB. If 80% of events are sampleable DEBUG logs, recalculate when keeping only 10% **of the DEBUG group** while keeping all other logs unchanged.
3. For a queue receiving 15,000 events/s and draining 12,000 events/s, describe the full-queue behavior under three policies: block, drop, and synchronous fallback write. Which policies affect latency, and which can lose data?
4. Design a plan to compare INFO, DEBUG, and DEBUG with `Supplier`/sampling on the same API: define the workload, p95/p99 metrics, CPU/GC, bytes/s, queue depth, and error reproducibility, then state the criteria for choosing a configuration.

**Key takeaway:** logging cost includes message construction when disabled, record processing when enabled, I/O, and storage pipeline expenses. The reliable way to optimize is to **log the right events, compute data conditionally, control volume and queues, and measure under realistic workloads**.
