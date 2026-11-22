# Throughput Trade-offs in Asynchronous Logging (Java)

## 1. Objectives

**Asynchronous logging** allows business logic threads to place log events into a buffer/queue so that another worker thread can format and send them to the destination (console, file, collector, network, etc.). This approach typically makes logging calls return faster during **bursts** (short traffic spikes), but it does not infinitely increase the actual write capacity of the disk or log collection system.

What you need to understand in **“Throughput Trade-offs”** is that when you speed up application threads, you trade that off for buffer memory, handoff overhead, log visibility latency, and an unavoidable decision when the buffer is full: **block the sending thread, drop logs, or process them via another path**.

After this lesson, you will be able to:
- Distinguish between **application log-generation** throughput, **enqueue** rate, **actual destination processing** rate, and event loss rate.
- Predict when a queue will fill up using the generation rate (λ), consumption rate (μ), and queue capacity (Q).
- Compare synchronous logging, asynchronous logging, and queue-full handling policies.
- Configure key options in Logback/Log4j 2 and measure performance using realistic workloads.
- Choose appropriate policies for diagnostic logs, critical errors, and high-reliability audit logs.

## 2. Data Flow and Throughput Metrics

### 2.1. Synchronous vs. Asynchronous

**Synchronous logging (simplified):**

```text
Request thread -> create LogEvent -> format/write via appender -> return to business logic
                                           |
                                           +-> file / stdout / collector
```

**Asynchronous logging (simplified):**

```text
Request threads -> create/capture LogEvent -> [bounded QUEUE] -> worker -> appender -> destination
       |                  (enqueue)                  |                        |
       +---- continue business logic early           |                        +-> slow I/O still exists
                                                     +-> backlog / full
```

In real implementations, part of the work—creating the event, checking the level, collecting timestamp/MDC, and sometimes formatting or copying data—still happens on the thread calling `logger.info(...)`. “Async” means the log delivery path is decoupled; it does not mean the entire logging cost is zero.

| Metric | Symbol | Meaning |
| --- | --- | --- |
| Generation rate | λ (events/s) | Number of events the application wants to log per second |
| Actual sink processing rate | μ (events/s) | Number of events the worker/appender actually delivers/writes successfully per second, depending on the measurement point |
| Queue capacity | Q (events) | Maximum number of events that can wait in the buffer |
| Queue depth | q(t) | Number of events waiting at time t; typically 0 ≤ q(t) ≤ Q |
| Business throughput | requests/s or ops/s | Number of requests/tasks the application completes per second |
| Call latency | duration of the log call | Time the application thread waits at `logger.info(...)` |
| Delivery latency | time from creation to destination receipt | Includes queue wait time, processing, and transport |
| Drop rate | events/s or % | Events discarded due to policy or errors |

Do not equate the **number of successfully enqueued events** with the number of durably written events. At runtime, the queue may still have a backlog, the worker may be in the middle of processing an event, or a remote destination may not have acknowledged storage yet. To verify end-to-end delivery, measure at the appropriate acknowledgment point.

### 2.2. Steady State and Overload

Assume a bounded queue that starts empty, with roughly constant generation and consumption rates:

- If **λ < μ**, the worker can keep up over the long term; the queue absorbs short fluctuations. This does not eliminate spikes caused by GC, I/O, or lock contention.
- If **λ = μ**, the system is balanced on average but can still fill up during bursts; headroom is needed for variance.
- If **λ > μ** continuously, the backlog grows by approximately **λ − μ** events/second. A bounded queue will eventually fill up: increasing Q only **delays** when it becomes full, rather than solving the long-term throughput mismatch.

Estimate when the queue starts empty:

```text
time until full ≈ Q / (λ − μ)     (when λ > μ)
```

**Illustrative hypothetical example**, not an actual benchmark: an application generates 12,000 events/s; the destination can only process 10,000 events/s; the queue holds 6,000 events. The backlog grows by about 2,000 events/s, so the queue may fill up in roughly **3 seconds** if that rate persists and no earlier shedding/dropping mechanism kicks in. Increasing the queue to 60,000 events pushes this point out to about 30 seconds, but the consumption rate remains 10,000 events/s.

In systems with multiple producer threads, variable event sizes, multiple appenders, or unstable networks, λ and μ must be measured over time windows; the formula above is an approximate model for capacity reasoning, not a guarantee of exact time-to-full.

## 3. Throughput Benefits of Async Logging

### 3.1. Reducing Application Wait Time on Log Calls

When the queue is not full, producers typically only prepare the event and enqueue it; I/O is handled by the worker. For workloads with many requests and sudden log bursts, shortening the log call can reduce request latency and improve burst handling.

**Peak enqueue throughput** (how many events producers push into the queue over a short interval) can be higher than **sustained sink throughput** (how many events are actually processed by the destination over the long term). Do not report “logging runs at 100,000 events/s” just because 100,000 log calls returned in a short test: you must check whether the queue has fully drained and whether any events were dropped.

### 3.2. Batching, Reducing I/O Contention, and Coalescing Work

The worker can batch multiple events, write in bulk, and reduce the number of I/O interactions; some backends also optimize synchronization across producers. However, results depend on the backend, appender, encoder, CPU core count, destination type, and event size. There is no universal rule that async is always faster than sync.

### 3.3. Added Overhead

Async introduces:
- Producer/consumer handoff operations, memory synchronization, and worker wakeups.
- Events/buffers occupying heap memory, which can increase allocation and GC pressure.
- A delay between when business logic emits a log and when the log appears at the destination.
- More complex worker lifecycle, flushing, and error handling; errors on the worker may not propagate back to the calling thread.
- Potential CPU contention with business logic in environments with few cores.

If the sink is already very fast, log volume is low, or application threads contend heavily while enqueuing, the added overhead of async can cause **sustained throughput to be lower than sync**. Therefore, you must measure both near-empty queue states and overloaded queue states.

## 4. Queue Full: Every Choice Has a Cost

| Policy | When the queue is full | Impact on throughput and latency | Trade-offs / use cases |
| --- | --- | --- | --- |
| **Block / backpressure** | Producer waits for space | Reduces business throughput and increases p95/p99 during congestion; long-term event acceptance rate is capped by the sink | Prioritizes keeping accepted logs; must guard against timeouts and cascading stalls |
| **Drop / discard** | Drops events by priority or drops new events | Protects producer latency and maintains request throughput to some degree | Loss of observability; must count dropped events and choose which events can be discarded |
| **Synchronous fallback** | Calling thread writes directly when queue is full | Can preserve events, but unexpectedly incurs I/O cost on the hot path | Latency spikes, contention, and different behavior under high load |
| **Spill to disk/durable buffer** | Switches to a temporary storage mechanism with different durability | Reduces event loss if designed properly | Increases I/O, storage usage, and operational cost; requires limits and disk-full handling |
| **Reduce events at the source** | Lower DEBUG volume, sampling/rate limiting | Reduces λ closer to or below μ; effective for both throughput and memory | May lose diagnostic detail; must protect critical logs |

**There is no “no blocking, no log loss, no extra resource cost” policy when λ > μ persists.** If you cannot lose events, you must accept waiting/backpressure, invest in higher consumption capacity, reduce emission at the source, or design a separate durable write path.

An **unbounded queue** usually just shifts the problem to the heap or disk; when emission continuously outpaces the destination, the backlog keeps growing until it hits resource limits. In most service applications, an **explicitly bounded** queue with alerting metrics is easier to control.

## 5. Standalone Java 17+ Example: Buying Throughput with Log Loss

This is a **queue/worker simulation**, not a replacement for a real logging backend and **not a benchmark**. We intentionally hold the worker back from running to deterministically create a queue-full scenario: 5 events arrive at once, the queue holds 2 events, and `offer` does not wait. Thus, only 2 events are accepted.

Create the file **`AsyncLoggingTradeoffDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public class AsyncLoggingTradeoffDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);
        CountDownLatch startDrain = new CountDownLatch(1);

        Thread sink = new Thread(() -> {
            try {
                // Consume only after the producer has attempted to send all 5 events.
                startDrain.await();
                String event;
                while ((event = queue.poll()) != null) {
                    System.out.println("consumed=" + event);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "simulated-sink");
        sink.start();

        int accepted = 0;
        int dropped = 0;
        for (int i = 1; i <= 5; i++) {
            if (queue.offer("event-" + i)) {
                accepted++;
            } else {
                dropped++;
            }
        }

        System.out.println("accepted=" + accepted + " dropped=" + dropped);
        startDrain.countDown();
        sink.join();
    }
}
```

Run with JDK 17 or later:

```bash
javac AsyncLoggingTradeoffDemo.java
java AsyncLoggingTradeoffDemo
```

**Exact output for this scenario:**

```text
accepted=2 dropped=3
consumed=event-1
consumed=event-2
```

Takeaways:
1. `ArrayBlockingQueue<>(2)` has a fixed capacity of 2 events.
2. `offer(event)` returns `false` immediately when full; the producer is **not blocked**, but 3 events are lost before reaching the worker.
3. `CountDownLatch` ensures the worker starts only after the enqueue loop so the output is deterministic; in a real application, the worker runs concurrently and the number of dropped events depends on load.
4. `consumed` only means the simulated worker received the event; it **does not represent durable storage**. Production systems must separately measure successful file/collector writes.
5. `sink.join()` waits for the worker to finish, preventing the example from exiting before printing completes.

To test other policies in a real program, you can use:
- `queue.put(event)`: waits until space is available without automatically dropping; the call may block.
- `queue.offer(event, timeout, TimeUnit.MILLISECONDS)`: waits up to a timeout, then returns `false` if still full.
- `queue.offer(event)`: does not wait; increment a `dropped` counter yourself on failure.

These are JDK queue APIs; backends such as Logback or Log4j 2 have their own mechanisms and policies. Do not simply change `offer` to `put` in the `CountDownLatch` example above: because the worker is held back waiting for the producer, the producer would hang forever once the queue fills. When testing backpressure, let the consumer run concurrently and design proper shutdown/interrupt handling.

## 6. The Throughput Picture in Production

### 6.1. Tracking Event Counts at Each Stage

Place independent measurement points:

```text
generated -> accepted/enqueued -> dequeued -> appender success -> collector acknowledged
     |                |
     +-> filtered     +-> dropped / retry / fallback
```

Exact stages may vary by backend. You must distinguish **filtered** (not emitted due to log level or sampling) from **dropped** (intended to be logged, but discarded due to queue/policy). A dequeued event is not guaranteed to be written successfully; a record sent to stdout is not guaranteed to be received by the collector.

Useful metrics:
- `log_events_generated_total`, `log_events_dropped_total` by level/destination and reason if possible.
- Queue `size`, `capacity`, `remainingCapacity`, time spent at 80–100% utilization, and number of times producers were blocked.
- Appender success rate; write errors/timeouts/retries; flush time on shutdown.
- Duration of `log(...)` calls (p50/p95/p99) and end-to-end request latency (p95/p99).
- Application throughput (requests/s), CPU, GC pauses, heap, bytes/s to file/network, and collector health.

A “zero drops” metric is not enough to prove no logs were lost if you do not monitor shutdown, I/O failures, the collector, and backend limits. Configure early alerts when the queue grows continuously and when drops or append errors are non-zero.

### 6.2. Queue Size Trade-offs

A larger queue generally absorbs longer bursts, but:
- Uses more heap for event objects, strings, context, references, and overhead.
- Increases how long an event must wait before being written when the backlog is large.
- Extends drain time during shutdown; if the process is killed, more unprocessed events may be lost.

If 6,000 events are waiting in the queue and the worker writes at 10,000 events/s, an event at the tail of the queue may wait roughly **0.6 seconds** just for the backlog ahead of it (assuming FIFO and constant rate). This is estimated queue time only, excluding I/O/network and post-appender processing.

Memory in bytes must be calculated from the **actual event size after creation/capture** plus JVM overhead; “Q × text length” is only a rough estimate. Measure heap after warmup, during bursts, and during sustained backlogs—do not allocate a huge queue just because free memory is available.

### 6.3. Speeding Up Writes and Reducing Input Events

If the queue is constantly full, increasing Q is less effective than improving **μ** (choosing an appropriate file encoder, reducing CPU-heavy formatting, using suitable batching, increasing destination capacity, reducing network latency) or reducing **λ** (lowering log levels, controlled sampling, avoiding logging inside every loop iteration, aggregating repeated events into a single metric).

For example, if one request emits 100 logs and the application handles 200 requests/s, that generates about **20,000 events/s**. Reducing this to 10 high-value logs per request brings the emission rate down to about **2,000 events/s** without enlarging the queue. However, you must never sample or drop logs that are mandatory for business or compliance/audit requirements.

## 7. Configuration in Java Logging Backends

### 7.1. Logback `AsyncAppender`

This is an example **configuration snippet** for Logback; you must define an appropriate `FILE` appender and attach `ASYNC` to your application's logger/root:

```xml
<appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>4096</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <appender-ref ref="FILE"/>
</appender>
```

Meaning:
- `queueSize`: event queue capacity (e.g., 4,096), not the number of threads.
- `discardingThreshold=0`: disables **early** discarding of low-level events when the queue nears capacity.
- `neverBlock=false`: when the queue is truly full, producers may block waiting for space rather than proactively dropping under the `neverBlock` option.
- Even with these settings, logs can still be lost if the process crashes, shutdown does not finish flushing in time, the appender fails, or the destination is unreliable; durability guarantees cannot be inferred.

According to Logback documentation, `AsyncAppender` defaults to a queue of 256 events and a policy that discards TRACE/DEBUG/INFO events when the queue reaches about 80% capacity; `neverBlock` defaults to `false`. This creates an **intentional trade-off**: reducing producer blocking by sacrificing lower-level logs. Check your exact version and any overridden settings before interpreting drop rates.

If you set `neverBlock=true` so producers never wait when the queue is full, you must accept dropped events and monitor the impact. For critical audit logs, a throughput-first policy alone is usually insufficient.

`includeCallerData` (class/method/file/line) can add significant overhead, so enable it intentionally. Proper shutdown requires closing the `LoggerContext`/appender so the worker has a chance to drain; `maxFlushTime` controls the wait time, and still cannot protect against hard kills or power loss.

### 7.2. Log4j 2: AsyncLogger and AsyncAppender

Log4j 2 provides two distinct mechanisms:
- **AsyncAppender**: places events into a queue and dispatches them to target appenders on a separate thread; `bufferSize` and queue-full policies vary by version/configuration.
- **AsyncLogger**: uses the LMAX Disruptor for the asynchronous event pipeline; you can make all loggers async or mix sync and async loggers. Requires the corresponding dependencies per the Log4j 2 documentation for your version.

Both remain bounded by sink speed. `AsyncQueueFullPolicy` can cause events to be dropped, threads to wait, or events to be processed on the calling thread, depending on configuration. Do not assume that “enabling AsyncLogger” always yields higher throughput or never blocks. Placing an async processor in front of another async appender can also add extra queuing/latency without increasing μ.

**Benchmark numbers and defaults from older versions are not guarantees for the current version.** You must benchmark your actual application with the same log configuration, write destination, core count, payload, frequency, and load profile.

## 8. How to Benchmark Throughput Properly

A reliable performance test must separate **instantaneous event acceptance rate** from **completed write rate**, while observing p99 latency, drops, and backlog.

1. **Define objectives:** Can debug logs be dropped, or must 100% be retained? What is the request latency SLO? Are there audit or maximum-flush-on-shutdown requirements?
2. **Keep the workload identical:** Same requests/second, events/request, message size, level, context/MDC, JSON/text layout, stack traces, file/collector destination, and retention. Do not compare sync writing to disk against async that merely enqueues and exits.
3. **Run a baseline:** Disable the logs being measured (to establish application cost), then test sync and async. Warm up the JVM/JIT, run multiple iterations, and report hardware/JDK/backend versions. JMH can be used for microbenchmarking logger calls, but integration/end-to-end benchmarks are needed to measure disk/collector performance.
4. **Run three phases:** Load below sink capacity, short bursts, and sustained overload. Measure while the queue grows, after the queue is full, and until it completely drains—avoid ending the test before the worker finishes.
5. **Report complete metrics:** requests/s, `log(...)` p99, request p99, generated/accepted/written/dropped, queue occupancy, memory, CPU/GC, bytes/s, errors, and shutdown time. Compare across equal time windows.
6. **Inject controlled faults:** Slow down or briefly disconnect the collector, throttle disk speed, or spike the log rate; verify queue-full policy, error visibility, flush/recovery behavior, and actual event loss.

**Example interpretation guide:**

| Observation | Reasonable inference |
| --- | --- |
| Async producer returns quickly, queue grows continuously, sink cannot keep up | Deferring processing debt into a backlog; sustained throughput has not improved |
| Request throughput is high, drop rate increases | Log completeness has been traded off for business responsiveness |
| Queue is full, request p99 spikes sharply | Backpressure or sync fallback may be hitting the hot path |
| Async has good p99 during bursts, but performs worse than sync under steady sustained load | Async overhead and sink limits are becoming apparent |
| Queue stays low, written/s ≥ generated/s over a suitable window, no errors | Signs of equilibrium, though end-of-pipeline and shutdown still need verification |

Avoid benchmarking only with **ConsoleAppender** if production writes to files or a collector; console I/O has different characteristics and read speeds. Avoid putting `System.out.println` inside a benchmark loop: that is also a very expensive I/O operation that skews measurements. Use tools and destinations that match real workloads.

## 9. Decisions by Log Type and Reliability Requirements

- **DEBUG/TRACE diagnostic logs:** Consider sampling, rate limiting, and discarding under overload; must have drop metrics and allow targeted detailed enabling when needed.
- **INFO business logs:** Clearly define acceptable loss levels; many INFO events are useful, yet can be redundant on hot paths.
- **WARN/ERROR logs:** Generally require higher priority; avoid unconditional discard policies, though full queues and process crashes remain risks.
- **Audit, transactions, receipts, and durability/compliance-critical events:** Do not treat an in-RAM logging queue as the primary store. Consider durable write mechanisms, transactional outbox patterns, or dedicated audit systems with acknowledgments, retries, idempotency, and end-to-end verification; choose sync vs. async based on specific requirements.

**Flush does not mean fsync or collector acknowledgment.** Writing to a file, sending to stdout, and pushing to a centralized pipeline all offer different guarantees. When claiming “no log loss,” specify exactly which stage of the pipeline acknowledged success.

**Data protection:** Higher throughput can also spread sensitive data faster. Do not log passwords, tokens, cookies, or full sensitive payloads; apply data minimization, masking/redaction, and proper access control/retention policies.

## 10. Common Pitfalls

1. **Looking at enqueue throughput and concluding the sink is faster:** You must wait for drain and count actually processed events.
2. **Making the queue unbounded when the sink is slow:** Turns temporary congestion into heap, GC, and shutdown pressure.
3. **Enabling neverBlock/drop without counters:** Requests may look faster while observability silently degrades.
4. **Disabling early discard and assuming logs cannot be lost:** A full queue can still block, and appenders/shutdown can still fail.
5. **Using the same policy for DEBUG and audit logs:** Their criticality and durability goals are different.
6. **Doing heavy formatting before the logger call:** Even with an async backend, string concatenation or CPU-heavy functions in arguments execute on the producer; use parameterized logging/lazy evaluation per the API and avoid unnecessary expensive computation.
7. **Reading mutable arguments after enqueue:** The event may be consumed after the data has already changed; use immutable events/snapshots appropriate for the backend.
8. **Not measuring block counts or p99:** Good average throughput can hide terrible tail latency.
9. **Abrupt shutdown while a backlog remains:** Queued events may not reach the destination in time; verify backend stop/flush behavior and real operational shutdown paths.
10. **Concluding one backend is always fastest from a single benchmark table:** Workload, JDK, core count, appender type, and measurement point can change the ranking.

## 11. Practice Exercises

1. Run `AsyncLoggingTradeoffDemo` and confirm 2 events accepted and 3 dropped. Explain why the number of completed `offer` calls (5) differs from the number of consumed events (2).
2. Build a producer/consumer model without a latch where the consumer processes slowly; compare `offer`, `put`, and `offer` with a timeout. Measure producer wait time and count lost events.
3. In a Java application with Logback/Log4j 2, run three workloads: below capacity, burst, and sustained overload. Record requests/s, p99, queue depth, drops, and events completed at the destination.
4. Vary the queue size under the same sustained load. Verify whether **when congestion begins** changes while the **long-term sink rate** stays the same.
5. Define separate policies for diagnostic logs, WARN/ERROR, and audit logs; explicitly document latency SLOs, completeness targets, and log acknowledgment points.

## 12. Key Takeaways

- Async logging typically reduces logger call time and handles **bursts** well, but long-term write throughput is still bounded by the **sink**.
- When λ > μ persists, a bounded queue will fill up; enlarging the queue only extends how long you can absorb load, without increasing destination capacity.
- Blocking, dropping, and sync fallback are choices with clear trade-offs between **application latency/throughput** and **log completeness**.
- Measure requests/s, events written/s, queue depth, drops, p99, and drain/shutdown behavior. Never claim an optimization based solely on enqueued event counts.
- For high-reliability audit logs, use a write path with durability mechanisms and proper acknowledgments; an in-memory async queue is not enough.

### Official References

- Logback — *AsyncAppender*: https://logback.qos.ch/manual/appenders-async-sift.html
- Logback — *Throughput Benchmark*: https://logback.qos.ch/performance.html
- Apache Log4j 2 — *Asynchronous loggers*: https://logging.apache.org/log4j/2.x/manual/async.html
- Apache Log4j 2 — *Performance*: https://logging.apache.org/log4j/2.x/manual/performance.html
- Oracle Java SE 21 — *BlockingQueue*: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html
