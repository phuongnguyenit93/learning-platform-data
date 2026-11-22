# Application-Blocking Logging in Java Core Logging

## Objectives

This lesson belongs to the **Logging Reliability** group, covering the topic **Application-Blocking Logging**. "Logging-induced blocking" occurs when creating or transporting logs forces a business thread to **wait** before continuing execution, increasing response time, reducing throughput, or causing cascading stalls. This is a reliability risk: logging exists to observe failures, yet a poorly performing logging path can itself become the reason an application slows down or stops serving requests.

After this lesson, you will be able to:

- Explain the difference between a **blocked logger call**, a **stalled worker/sink**, **delayed logs**, and **dropped logs**.
- Identify common blocking points across synchronous logging, asynchronous logging, stdout/containers, files, networks, locks, and shutdown.
- Understand the relationship between queue capacity, log generation rate, log write rate, backpressure, and application latency.
- Read signals in thread dumps, Java Flight Recorder (JFR), metrics, and profilers to confirm the root cause.
- Run two standalone Java 17 examples: a synchronous handler holding a business thread and a bounded queue forcing a producer to wait.
- Choose an appropriate policy when the sink is slow or the queue is full, while balancing latency, observability, and the risk of log loss.

## 1. What Exactly Is "Blocked"?

In a Java application, logging methods such as `logger.info(...)` are typically called directly inside a request thread, scheduler, consumer, or business worker. If this method has to wait on a lock, an I/O device, or space in a queue, the **calling thread** cannot advance to the next business step.

Consider a request example:

```text
HTTP thread:
validate request
    |
    v
call logger.info("request accepted")
    |
    +---- synchronous appender waiting on file / stdout
    |          or
    +---- async enqueue waiting for queue space
    |
    v
call payment service
    |
    v
return HTTP response
```

If logging takes 500 ms before calling the payment service, the request incurs that extra wait time even though the business logic did nothing wrong. When many concurrent requests get stuck in logging, the web server's thread pool can become exhausted, new requests queue up, and timeouts cascade to other services.

**Distinguishing four situations:**

| Situation | What is happening | Impact on the application |
| --- | --- | --- |
| **Caller blocked** | Business thread waits in/at the logger call path | Request/consumer/job slows down right at the log call site |
| **Async writer stalled** | Background worker is waiting on disk/stdout/network; producers can still enqueue | Requests may look normal initially; backlog is growing |
| **Queue full + backpressure** | Producer cannot enqueue under a blocking policy | Async logging starts **blocking the caller**; p95/p99 may rise |
| **Log dropped/delayed downstream** | Events are dropped or arrive late at the collector/index | Logs may be missing or appear late, even when callers are not blocked |

In operations, the word "blocked" is **not identical** to `Thread.State.BLOCKED`. In Java, a thread stuck on the logging path can show `WAITING` (waiting on a condition/latch), `TIMED_WAITING` (waiting with a timeout), `BLOCKED` (waiting on a monitor), or `RUNNABLE` while a native I/O call is stalled. Always cross-check stack traces and wait times rather than diagnosing solely from the thread state name.

## 2. Causes of Logging Slowing Down the Application

### 2.1. Synchronous Appenders Performing I/O Directly on the Caller

With synchronous logging, execution typically flows through:

```text
request thread
  -> logger level/filter
  -> event creation / format
  -> appender lock (if any)
  -> write console/file/network
  -> return to business
```

Several operations can be slow: writing to a console whose pipe is full, a file on a slow or full disk, file rotation, a network-backed filesystem, encoding large exceptions, socket writes waiting on the network, external destination timeouts, or appender lock contention. The exact mechanism and wait duration depend on the logging framework, layout, appender, and infrastructure.

**Do not assume stdout is always fast.** In containers, `System.out` or `ConsoleAppender` typically writes to a stdout pipe managed by the runtime. If the pipe reader, log driver, or host I/O is congested, write operations can slow down or block the thread. Switching from files to stdout does not automatically eliminate the bottleneck.

### 2.2. Async Appenders Still Have Blocking Paths

With async logging:

```text
producers                              consumer
    |                                     |
    +--> event --> bounded queue -------->+--> formatter --> sink
                 ^                 |
                 |                 +--> slow sink
                 |
            queue full
                 |
       producer block / drop / fallback
```

A queue typically resides in memory and has finite capacity. When the worker writes to the sink slower than producers generate events over a sustained period, backlog grows. Once the queue is full, the logging framework must apply a policy: **block the producer**, **drop**, **discard by log level**, or **execute synchronously on the caller** in certain configurations/versions. Therefore, "async is enabled" is not enough to conclude that request threads cannot be affected by logging.

An event that has been enqueued successfully **is not guaranteed to have been written**: the worker may not have processed it yet, the process may be killed, the appender may encounter an error, or the collector may not have received it. Policies that reduce blocking time often increase the risk of log loss.

### 2.3. Lock Contention and Lock Ordering

Some encoders/appenders synchronize when multiple threads write to the same sink. If one thread holds the monitor for slow formatting or writing, other threads must wait for that monitor. Stack traces may show `Thread.State.BLOCKED` at a method related to an appender, `PrintStream`, or a shared lock.

A larger risk arises if the application **calls the logger while holding a business lock**. For example, thread A holds a cache lock and then stalls while logging; thread B needs the cache lock to serve another request. This can even form a wait cycle if the appender or a callback needs a lock held by thread B. You cannot conclude a deadlock just because a stack trace contains a logger name; you must prove a lock dependency cycle using thread dumps/JFR or a deadlock detector.

### 2.4. Event Preparation Overhead on the Caller

Even when enqueuing does not block, the business thread can spend CPU building arguments, calling `toString()`, serializing objects, formatting stack traces, capturing caller location, or copying MDC.

For example:

```java
logger.debug("payload=" + expensiveJsonSerialization(payload));
```

Java expressions are evaluated **before the method is called**, even when DEBUG is disabled. Parameterized logging:

```java
logger.debug("payload={}", expensiveJsonSerialization(payload));
```

avoids string concatenation at the call site, but still **executes** `expensiveJsonSerialization(payload)` before the call. With SLF4J, if building the data is very expensive and there is no suitable lazy support, you can use:

```java
if (logger.isDebugEnabled()) {
    logger.debug("payload={}", expensiveJsonSerialization(payload));
}
```

The snippets above use SLF4J with hypothetical variables/methods and are not standalone Java programs. `isDebugEnabled()` avoids preparation work when DEBUG is off, though configuration state can change between the check and the call; use it as a normal optimization, not a transactional guarantee. If your version supports a fluent/lazy `Supplier`, check its specific semantics before adopting it.

## 3. Queue Full: Why Does Latency Spike?

Let **λ** be the rate at which the application generates logs (events/second) and **μ** be the actual rate at which the worker/sink processes them (events/second):

- If `λ < μ` under steady conditions, the queue can drain its backlog between bursts.
- If `λ ≈ μ`, a small burst or pause can create a long queue and increase p99.
- If `λ > μ` for long enough, backlog grows by roughly `λ - μ` events/second until the bounded queue fills up, after which the backpressure policy dictates behavior.

For example, suppose a system emits **6,000 events/s** while the sink only processes **4,000 events/s**. Backlog grows by approximately 2,000 events/s in a simplified model. If the queue starts empty and holds 8,000 events, it can fill up in about 4 seconds at that load, ignoring variance and overhead. Once full:

- With **blocking enqueue**, logger call duration can grow in proportion to the rate at which the sink frees slots.
- With **non-blocking drop**, callers may return quickly, but some logs are lost.
- With **synchronous fallback**, business threads may directly bear I/O costs, causing unexpected tail latency.

**Increasing queue size only delays the time until it fills up** when `λ > μ` persists; it does not make the sink process faster. A larger queue also retains more objects on the heap and can make logs appear later. Solving sustained overload requires reducing log noise, optimizing the sink/collector, or increasing consumption capacity, alongside an explicit overload policy.

By Little's Law in steady state, `L = λ × W` within a consistent measurement boundary, where `L` is the average number of events waiting/in-process and `W` is the average time an event spends in that boundary. Do not use this formula as a latency guarantee when the queue is overflowing, events are being dropped, or the system is not in steady state.

## 4. Java 17 Example: Demonstrating a Synchronous Handler Blocking the Request Thread

The following example uses **JDK 17**, with only `java.util.logging` and `CountDownLatch`. A `Handler` simulates a sink that must wait for a signal before returning. The request thread calling `logger.info(...)` cannot proceed until the `Handler` is released. Because the program does not rely on sleep durations or machine speed, its output is deterministic.

Create the file **`BlockingLoggerDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class BlockingLoggerDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch enteredHandler = new CountDownLatch(1);
        CountDownLatch releaseHandler = new CountDownLatch(1);
        AtomicBoolean loggerReturned = new AtomicBoolean(false);

        Logger logger = Logger.getLogger("demo.blocking");
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);

        Handler slowSink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }

                enteredHandler.countDown();
                try {
                    releaseHandler.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }

            @Override
            public void flush() {
            }

            @Override
            public void close() {
            }
        };
        slowSink.setLevel(Level.ALL);
        logger.addHandler(slowSink);

        Thread request = new Thread(() -> {
            logger.info("request-accepted");
            loggerReturned.set(true);
        }, "http-request");

        try {
            request.start();
            enteredHandler.await();

            System.out.println("logger_returned_before_release="
                    + loggerReturned.get());

            releaseHandler.countDown();
            request.join();

            System.out.println("logger_returned_after_release="
                    + loggerReturned.get());
            System.out.println("request_finished="
                    + !request.isAlive());
        } finally {
            releaseHandler.countDown();
            request.join();
            logger.removeHandler(slowSink);
            slowSink.close();
        }
    }
}
```

Compile and run:

```bash
javac BlockingLoggerDemo.java
java BlockingLoggerDemo
```

**Exact stdout:**

```text
logger_returned_before_release=false
logger_returned_after_release=true
request_finished=true
```

**Why is this correct?**

1. `request` calls `logger.info(...)`; JUL dispatches the `LogRecord` to the `Handler` on the **same thread** as the caller.
2. The `Handler` signals `enteredHandler.countDown()` and then waits on `releaseHandler.await()`; at the moment the main thread receives the signal, `logger.info(...)` still cannot return, so `loggerReturned=false`.
3. The main thread allows the `Handler` to proceed via `releaseHandler.countDown()`. The request finishes the logger call, sets `loggerReturned=true`, and `join()` guarantees it has terminated before printing the next results.
4. The `Handler` does not print the event itself so stdout contains only the three verification lines. `setUseParentHandlers(false)` disables JUL parent handlers to prevent unexpected output.
5. `finally` releases the latch even if the program is interrupted while waiting and removes the `Handler` so test configuration does not linger after completion.

This is a **simulation of a stalled sync sink**, not a measurement of disk, container, or network latency. In a real application, a sink may wait on a file write, stdout pipe, socket, lock, or flush. Measure with `System.nanoTime()` around the logging call to obtain caller latency figures; do not treat the two boolean flags in this example as real latency.

**Experiment:** remove `releaseHandler.countDown()` from the `try` block while keeping `finally`. The three output lines will no longer appear in the original order because the program will wait on `join()` until `finally` releases the latch (and `finally` only runs after leaving `try`), creating an indefinite self-wait. Do not run this modification without a timeout in a test environment. The lesson is that waiting on a logger/sink must not be designed around mutual lock-waiting cycles.

## 5. Java 17 Example: Bounded Async Queue Forcing the Producer to Wait for Space

Queue mechanics are a cause independent of a slow `Handler`: when a queue is full, `BlockingQueue.put` **waits** until it can insert the element or the thread is interrupted. `offer` without a timeout can return `false` immediately when full; `offer` with a timeout can wait for a bounded duration. These options clearly illustrate the tradeoff between blocking and log loss.

Create the file **`AsyncQueueBackpressureDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class AsyncQueueBackpressureDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        queue.put("first");

        CountDownLatch beforePut = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<?> pending = pool.submit(() -> {
                beforePut.countDown();
                try {
                    queue.put("second");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(e);
                }
            });

            beforePut.await();
            boolean notFinishedWhileFull;
            try {
                pending.get(100, TimeUnit.MILLISECONDS);
                notFinishedWhileFull = false;
            } catch (TimeoutException expected) {
                notFinishedWhileFull = true;
            }

            String first = queue.take();
            pending.get();
            String second = queue.take();

            System.out.println("capacity=1");
            System.out.println("not_finished_while_full="
                    + notFinishedWhileFull);
            System.out.println("first=" + first);
            System.out.println("second=" + second);
            System.out.println("queue_empty=" + queue.isEmpty());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile/run with JDK 17+:

```bash
javac AsyncQueueBackpressureDemo.java
java AsyncQueueBackpressureDemo
```

**Exact stdout:**

```text
capacity=1
not_finished_while_full=true
first=first
second=second
queue_empty=true
```

The queue has only one slot and already holds `first` before the worker attempts `put("second")`. `Future.get(100, ...)` cannot return a completed result until someone removes `first` from the queue, so the wait times out. Only after `queue.take()` can the worker enqueue `second`, and `pending.get()` ensures it has finished before main takes the next event.

**Limitations of this test:** `not_finished_while_full` proves the task could not complete while the queue was full; it does not measure the exact number of milliseconds the worker actually spent inside `put`, because the JVM scheduler may delay when the worker begins calling `put` after the `beforePut` signal. The 100 ms value is an illustrative deadline, not an SLO or benchmark. Measuring actual blocked time requires instrumentation around enqueue and diagnosing stacks/metrics under representative load.

In real logging frameworks, the queue may be a `BlockingQueue`, a ring buffer, or another structure; this example illustrates boundedness and backpressure and **does not assume Logback/Log4j 2 use this exact code**. Events in the queue here are just strings, with no `LogRecord`, layout, or log sink.

## 6. Logback: Which Configurations Can Block Application Threads?

With SLF4J + Logback Classic, an `AsyncAppender` receives events from loggers and passes them to a worker that sends them to target appenders. Logback provides important configuration options:

- `queueSize`: maximum number of events in the queue; increasing capacity helps absorb larger bursts, but consumes RAM and can increase log appearance delay.
- `discardingThreshold`: remaining-capacity threshold at which `AsyncAppender` may drop lower-level events according to policy; not synonymous with a full queue. In typical Logback Classic, TRACE/DEBUG/INFO levels are eligible to be discarded under this policy.
- `neverBlock=false`: when unable to enqueue, the producer may **wait** until queue space becomes available. This prioritizes keeping events through the queue layer at the cost of potentially increasing caller latency.
- `neverBlock=true`: uses a non-blocking path when the queue is full, which can **drop events** instead of waiting. This requires a log-loss/monitoring policy and you must not treat events as persisted.
- `maxFlushTime`: budget for waiting on the worker to drain when the appender stops; forced shutdown or exceeding the timeout can leave events unwritten.
- `includeCallerData`: when enabled to compute caller location data, the producer may incur higher overhead because it must resolve the stack/caller.

Example **`logback.xml`** for exploring backpressure policies; requires compatible Logback/SLF4J dependencies and an environment permitted to write to stdout:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>1024</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <includeCallerData>false</includeCallerData>
        <maxFlushTime>5000</maxFlushTime>
        <appender-ref ref="CONSOLE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

**Correct interpretation:**

1. The application typically enqueues first, and then the worker calls the `CONSOLE` appender. When stdout is slow, events can accumulate in the queue.
2. `discardingThreshold=0` disables early discarding based on remaining capacity; it does not make the queue unbounded.
3. `neverBlock=false` allows the producer to wait when the queue is full, so **this configuration does not guarantee "logger.info never blocks"**.
4. `maxFlushTime=5000` limits the drain wait window during stop per Logback's mechanism; it is not a maximum allowed block time for every `logger.info` call.
5. Using `ConsoleAppender` does not guarantee that logs have been received by the collector/index. Evaluating end-to-end requires examining the container and backend pipeline.

If you change `neverBlock=true`, you must **measure dropped events** under overload and verify the policy for important events. Do not simply change a setting and consider reliability fully solved. If you want to reduce log volume, restricting levels/packages/noisy events at the source is often more effective than letting the queue fall into overflow.

**When should you use async logging?** When sink costs can be decoupled from the caller and the system accepts the designed queuing/backpressure model. Do not send critical, sole-copy audit logs through an in-memory-only queue and claim a zero-loss guarantee. Audit logs need a durable storage path designed for specific business and regulatory requirements.

## 7. Log4j 2: AsyncLogger, AsyncAppender, and Queue-Full Policies

Log4j 2 offers **AsyncLogger** and **AsyncAppender**. `AsyncLogger` uses a ring buffer based on LMAX Disruptor in supported configurations. `AsyncAppender` is a mechanism that hands events off to a worker before reaching target appenders. The two approaches differ in implementation, overhead, context capture, and queue-full policies depending on the version.

With `AsyncLogger`, you must check the actual **AsyncQueueFullPolicy** configuration. When the buffer is full, a system may execute logging work on the current thread, wait, or discard events at certain levels depending on the policy. If it falls back to synchronous writing on the caller, something that is "async" in normal operation can still cause sudden latency spikes during an incident.

Checkpoints:

- Verify you are running in the intended async mode; inspect dependencies and the configuration loaded by the framework.
- Identify the queue/ring buffer size, the queue-full strategy, and how `ERROR`/`WARN` events are handled.
- Measure publish time on the caller **when load exceeds sink capacity**, not just throughput benchmarks with an empty queue.
- Verify the cost of caller location, ThreadContext/MDC capture, and exception messages/stack traces.
- Observe queue utilization, discards/drops, and error status if the stack exposes metrics.
- Test slow stdout/file/network sinks, rolling files, shutdown, retries, or an unavailable collector.

Do not copy properties from online examples without checking the documentation for your project's **exact Log4j 2 version**; property names, default policies, and configuration modes can change. In particular, do not treat "async logger" and "non-blocking logging" as synonymous concepts.

## 8. How Does Application-Blocking Logging Differ from Lost Logs?

A strategy can only be judged "good" when considering **latency, the number of logs received, and event criticality** together.

| Policy when sink/queue is slow | Caller impact | Observability and durability |
| --- | --- | --- |
| **Blocking enqueue** | Caller may wait a long time, exhausting request pools | Fewer events lost at the queue due to being full if progress continues; still can lose logs on crash/sink error |
| **Non-blocking offer/drop** | Enqueue path can be fast | Events are dropped when full; requires metrics and priority policies |
| **Bounded wait then fallback/drop** | Partially caps wait time caused by enqueue | Depends on framework/logic; fallback path and log loss must be clearly defined |
| **Synchronous fallback** | Caller directly bears formatter/I/O under overload | May retain more events, but increases tail latency |
| **Sampling/rate limiting at source** | Steadily reduces pressure on queue/sink | Intentionally drops low-value events; must preserve metrics/critical events |
| **Separate audit/critical path** | Different business paths depending on event type | Requires dedicated durability, access, and recovery design |

Some log types can be sampled or aggregated, such as successful healthchecks, cache hits, or repetitive debug logs. However, transaction failure logs, security alerts, and audit logs must follow dedicated policies; they cannot be arbitrarily dropped just to improve p99. For business events requiring durability, you may need a transactional outbox, a durable broker, or an appropriate audit store rather than relying on a general-purpose logger for transaction correctness.

**Note on bounded wait:** Not every logging framework exposes a "wait at most N ms then drop" option. If you want that strategy, inspect the actual API/implementation and ensure it does not unintentionally alter the semantics of audit/critical logs.

## 9. Diagnosis: Confirming Logging Is the Bottleneck

Common symptoms:

- Request p95/p99 latency rises at the same time as a log volume spike or collector congestion.
- Application CPU is not particularly high, yet many request threads are waiting; the web server thread pool is full.
- Log appearance lag increases, queue utilization is high, "appender queue full" warnings appear, or sink write rate drops.
- Many thread stacks repeat in appender/`PrintStream`/`BlockingQueue.put`/`LockSupport.park` paths.
- Incident timing coincides with a full disk, rolling file, stdout driver slowdown, network logging outage, or changing log level to DEBUG.
- Application throughput drops when verbose logging is enabled and recovers after reducing volume in a test environment.

### 9.1. Reading Thread Dumps Properly

Take multiple thread dumps at short intervals while the incident is ongoing, and identify business threads and common call stacks. Example **illustrative stack**, not an actual dump:

```text
"http-nio-8080-exec-17" WAITING
  at java.util.concurrent.locks.LockSupport.park(...)
  at java.util.concurrent.ArrayBlockingQueue.put(...)
  at ...AsyncAppender...append(...)
  at ...Logger.info(...)
  at com.example.checkout.OrderService.process(...)
```

If many request threads repeat the same stack and the queue is full, that is strong evidence of logging backpressure. Even so, check the **actual** code and thread dumps to confirm whether an implementation calls `ArrayBlockingQueue.put`; Logback/Log4j 2 may use different classes/structures and produce different stacks.

With synchronous I/O, stacks may show `FileOutputStream`, `PrintStream`, socket writes, or encoders. Some I/O calls can remain in `RUNNABLE` state while waiting on native I/O, so do not filter only for threads in `BLOCKED`. For deadlocks, use `ThreadMXBean.findDeadlockedThreads()` or an appropriate tool to find monitor/ownable synchronizer cycles, then inspect lock owners and stacks.

### 9.2. Common Java Tools

- **`jcmd <pid> Thread.print`:** captures a thread dump; can be run multiple times for comparison.
- **Java Flight Recorder (JFR):** analyzes thread parks, blocked monitors, file/socket I/O, GC pauses, and execution context; available events depend on JDK version and recording settings.
- **ThreadMXBean / profiler:** inspects thread states, block/wait times, and CPU/allocation-heavy code paths.
- **Logger/appender/collector metrics:** queue depth/capacity, events/s, dropped count, disk writes, network retries, and ingest lag.
- **APM/tracing:** compares endpoint latency against logging call timestamps while checking context/trace IDs.

`jcmd <pid> Thread.print` is an example command in an environment with JDK tools, replacing `<pid>` with the actual process ID. Do not collect dumps/JFR indiscriminately from production if your organization has specific data-access procedures; stacks and events can contain sensitive information.

### 9.3. Measuring Caller Latency

Use `System.nanoTime()` around a specific logging call to measure elapsed duration within the same JVM:

```java
long started = System.nanoTime();
logger.info("processing payment");
long elapsedNs = System.nanoTime() - started;
```

This is a **snippet**, excluding logger declaration and where the result is recorded. Avoid logging `elapsedNs` immediately using the same logger on every measurement, as that generates additional traffic and can create a feedback congestion loop. Prefer a metric histogram or sampling instrumentation. Measure many times under realistic load and summarize p50/p95/p99, sample count, and drop rate; a single measurement is not representative.

Distinguish these milestones:

| Metric | Measurement boundary | Question answered |
| --- | --- | --- |
| **Caller logging duration** | Before logger call → after return | How long is the business thread held? |
| **Enqueue wait** | When enqueue begins → when accepted into queue | Is there backpressure from a full queue? |
| **Queue residence** | When entering queue → when taken by worker | Is there a worker/sink backlog? |
| **Sink completion** | When event is created → appender completes | Has it been written per the sink's semantics? |
| **Visibility latency** | When event is created → searchable in backend | How long until operators can see the log? |

"Sink completion" does not necessarily mean `fsync` to disk or durable acknowledgment from the collector; to measure durability, define the acknowledgment condition separately.

**Do not add p99 enqueue and p99 sink and call it end-to-end p99**: percentiles from different event sets do not add linearly. To measure end-to-end latency, attach an appropriate event ID/timestamp and compute latency per matched event.

## 10. Investigation Runbook for a Logging-Induced Blocking Incident

A concise runbook:

1. **Confirm impact:** endpoint p95/p99, request timeouts, active/queued request counts, thread pool utilization, and job/consumer lag.
2. **Check correlation with logging:** log volume by level/logger, message/stack trace sizes, recent config changes, queue depth, and sink throughput.
3. **Inspect thread dumps/JFR:** how many threads are stuck around logger/appender, queues, locks, or I/O; look for the same stack across multiple samples.
4. **Isolate the bottleneck:** if callers block while the queue is empty, check sync sinks/locks/formatting; if the queue is full, check consumer speed; if the JVM sink writes fast while search is slow, check the agent/collector/index.
5. **Choose safe load-shedding actions:** reduce DEBUG and log noise, inspect slow sinks/agents, scale collection capacity, or apply an approved policy. Do not disable ERROR/audit logs indiscriminately.
6. **Verify recovery:** caller p99 drops, throughput returns, queue recovers, critical logs continue arriving, and no events go missing outside policy.
7. **Prevent recurrence:** alert on queue occupancy/drops, run overload test scenarios, enforce log volume budgets, configure shutdown properly, and review logging changes.

**When immediate load shedding is needed:** first find the logger/package causing the burst and the slow sink. If policy permits, lowering the log level of a noisy package can cut pressure immediately. Do not flip `neverBlock` or configure discarding for all logs without checking data-loss risks. If a stalled logging sink is impacting requests, evaluate sink isolation and execute recovery according to the actual system's runbook.

## 11. Designing Logging So It Does Not Become a Single Point of Failure

### 11.1. Reducing Cost at the Source

- Use per-package/per-environment log levels; avoid prolonged system-wide DEBUG/TRACE.
- Use parameterized messages; check enabled levels before computing expensive data.
- Avoid serializing large payloads, entire object graphs, or repeated stack traces unnecessarily.
- Do not log the same exception repeatedly at every layer; choose meaningful error-reporting boundaries.
- Use metrics for counters/high-volume successes instead of emitting a log line every time.

### 11.2. Sink and Queue Design

- Use a bounded queue sized for bursts and RAM; measure backlog alongside the queue-full policy.
- Separate error or audit sinks into appropriate domains so a slow downstream does not block the entire logging path unnecessarily.
- Choose flushing, batching, retention/rotation, and log shipping suited to throughput and latency.
- Check the stdout pipeline in containers; the agent or logging driver can still be a bottleneck.
- Provide graceful shutdown/flush with clear bounds and monitoring. Do not treat an in-memory async queue as durable storage.
- Avoid logging inside hot locks, code that can re-enter the appender, or error callbacks of the logging framework itself.

### 11.3. Security and Correctness

- Do not log secrets, tokens, cookies, entire request bodies, or unnecessary personal data.
- When the pipeline fails, do not try to "save" logs by routing sensitive logs to another sink with broader access permissions.
- For audit trails requiring guaranteed persistence, design a dedicated durable write path or transactional mechanism per requirements; do not infer durability from `logger.info` returning successfully.
- Distinguish **filtered by policy**, **dropped due to overflow**, **sink write failed**, and **collector not ingested**. These four cases have different causes, ownership, and alerts.

## 12. Load Testing and Failure Injection Suite

A reliability test should run in staging or an equivalent controlled environment. Start with a baseline when the sink is healthy, then vary **one** factor at a time to isolate the cause.

| Scenario | How to test | Results to verify |
| --- | --- | --- |
| Normal | Steady load with representative log volume | Caller p50/p95/p99, queue depth, and end-to-end latency within budget |
| Log burst | Increase DEBUG logs or event volume briefly | Queue high-water mark, producer block/drop, recovery time |
| Slow sink | Simulate slow stdout/file/collector | Stalled worker, full queue, and impact on request latency |
| Sink down | Collector unreachable or file permission error in test env | Clear error/retry/drop policy, no unexpected infinite hangs |
| Queue full | Use low queue capacity or low sink rate in test | Block/drop/sync fallback policy behaves as configured |
| Lock contention | Multiple requests writing to same sink during slow processing | No lock chains or deadlocks formed; measure p99 |
| Shutdown | Graceful stop while queue still holds events | Worker flushes/drains within budget; unpersisted events accounted for |
| Crash/kill | Force-kill process in test env | Observed event loss matches design; do not assume zero loss |
| Sensitive logs | Payload containing fake tokens | Redaction/routing remains correct during errors and retries |

Run a **unique-event-ID test** to reconcile the number of events the application intended to emit, the number accepted by the queue, the number processed by the sink, the number received by the collector, and the number searchable. Counts do not have to match immediately due to async pipelines and retries; set an appropriate observation window and verify.

When comparing two configurations, keep workload, thread count, log level, message size, sink, CPU/memory, and log collector equivalent. A benchmark that only counts how many times `logger.info` returns per second can look very fast because events are being dropped or sitting in an unprocessed backlog; you must account for both written data and application latency.

### Example Measurement Targets

Suppose a team sets a budget of **caller logging p99 under 5 ms at target load**, zero `ERROR` events dropped at the queue layer in normal scenarios, and test events searchable in the backend within 10 seconds. These are **illustrative targets only**, not universal Java standards. You must define what "zero events dropped" means and specify exceptions such as process crashes, full disks, or network partitions; if the real requirement is durable auditing, use an appropriate storage mechanism.

Also track `logging_queue_utilization`, `logging_blocked_enqueue_duration`, `logging_dropped_events_total`, `logging_sink_errors_total`, throughput, and request latency. These metric names are examples and are not guaranteed to be exported out of the box by every framework version.

## 13. Common Misconceptions

| Misconception | More accurate statement |
| --- | --- |
| "AsyncAppender is enabled, so the logger will never block." | A full queue, queue policy, or synchronous fallback can directly impact callers. |
| "Only thread state BLOCKED means logging is blocking the app." | It can also be WAITING, TIMED_WAITING, or RUNNABLE in native I/O, depending on the mechanism. |
| "Increasing queue size will solve a slow sink." | It increases burst absorption time; sustained congestion remains whenever λ > μ. |
| "`neverBlock=true` guarantees reliability." | It can reduce producer waiting, but drops logs when the queue is full. |
| "`logger.info` returning means the log is saved." | Async may only have enqueued it; sync writes may not yet be durable or have reached the collector. |
| "Writing to stdout is always a non-blocking operation." | Pipes, logging drivers, and host I/O can become congested. |
| "All ERROR logs should be turned off for fast recovery." | This destroys diagnostic/audit visibility; instead find the noise source, bottleneck, and apply an appropriate policy. |
| "Low p99 log call latency means no logs are lost." | Many events may have been dropped; measure both drop rate and sink counts. |
| "When DEBUG is off, all message-building work disappears." | Java still evaluates argument expressions before calling the logger. |
| "One stack trace containing an appender proves the root cause." | Multiple samples, queue/sink metrics, timing correlation, and ruling out other causes are required. |

## 14. Operations Checklist and Self-Assessment

Before applying a logging configuration to production, answer these questions:

1. Does the application's logger use a sync appender, async appender, or both? Which paths can block business threads?
2. Does the queue have bounded capacity, and is the full-queue policy block, drop, discard, or fallback?
3. When stdout, files, or the collector are slow, what is the expected impact on endpoint p95/p99?
4. Are there logs that must never be lost? Does their storage mechanism truly meet durability requirements?
5. Which events can be reduced via levels, sampling, aggregation, or rate limiting before reaching the queue?
6. Which thread dumps/JFR recordings prove requests are waiting in logging, and which queue/sink metrics corroborate the conclusion?
7. On shutdown or process crash, how are in-memory events handled and how is log loss detected?
8. Have load, sink failure, backpressure, and end-to-end log recovery been tested before release?
9. When policy changes are needed to recover the service, what are the access controls and rollback/configuration audit procedures?

**Completion criteria:** You can explain the application-blocking paths caused by logging, run and reason through both Java 17 programs, distinguish blocking from delayed/dropped logs, read signals in thread dumps and metrics, and propose a policy that balances business latency with the log data that must be retained.

## References

- [Java 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): semantics of publishing `LogRecord` via `Handler`.
- [Java 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `put`/`offer`/`take` and waiting behavior.
- [Java 17 — Thread.State](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): `BLOCKED`, `WAITING`, `TIMED_WAITING`, and `RUNNABLE`.
- [Java 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): inspecting threads, contention, and deadlocks.
- [Logback — AsyncAppender](https://logback.qos.ch/manual/appenders.html#AsyncAppender): bounded queue, discarding, `neverBlock`, shutdown.
- [Apache Log4j 2 — Asynchronous Loggers](https://logging.apache.org/log4j/2.x/manual/async.html): `AsyncLogger`, `AsyncAppender`, and queue-full strategies.
- [Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/): recording JVM events to investigate wait/I/O/GC.
