# Async Appender in Java Logging

## 1. What Problem Does an Async Appender Solve?

In Java Logging, an **appender** is the component that receives a created log event and sends it to a destination such as the console, a file, or a collector over the network. The name **handler** usually appears in `java.util.logging` (JUL), while **appender** is common in Logback and Log4j 2. Although the names differ, both participate in processing and outputting log records.

With a **synchronous** appender, the thread running business logic may directly perform both formatting and writing the data:

```text
Request-processing thread
  |
  +-- process order
  +-- logger.info(...)
        |
        +-- check level/filter
        +-- appender formats message
        +-- write to console/file/socket  [may wait on I/O]
        |
  +-- continue processing request
```

In the **asynchronous** model, the logging call typically puts the event into a queue; a separate thread pulls the event out and performs the work of the destination appender:

```text
Request-processing thread (producer)
  |
  +-- logger.info(...)
        |
        +-- check level/filter
        +-- prepare/snapshot required data
        +-- enqueue event into queue
        |
  +-- continue processing request

                 Event queue
                  [A][B][C]...
                       |
                       v
                 Worker thread (consumer)
                       |
                       v
               File/Console/Collector
```

The goal is to **reduce the time the business thread spends waiting on logging work**, especially when the formatter or I/O is expensive. However, the word "async" **does not mean the logger never blocks, all logs are guaranteed to be saved, or throughput is always better**. Actual behavior depends on the queue, overload policy, destination appender, flush configuration, and application shutdown process.

A log event that is **successfully placed into the queue** may still **not yet be written to a file/console**. Therefore, three milestones must be distinguished:

1. **The logger receives the call** from the application.
2. **The queue accepts the event** (may block or drop if overloaded).
3. **The destination appender writes or forwards the event** (may fail, buffer, or lose connection).

These milestones are distinct; a successful `logger.info` call cannot be used to assert that the record has been durably persisted.

## 2. How Do Synchronous and Asynchronous Appenders Differ?

| Aspect | Synchronous Appender | Asynchronous Appender |
|---|---|---|
| Thread performing I/O | Usually the thread emitting the log | Usually a separate worker thread |
| Logging call latency | May incur formatting/writing cost | Usually lower when the queue has space and only enqueuing occurs |
| When the write destination is very slow | The business thread may wait on I/O | The queue grows; afterward the producer may block or events may be dropped |
| Memory | No large dedicated backlog needed | Has queue, events/metadata, and capacity monitoring needs |
| When the process dies abruptly | Risk of losing buffers or partial writes | Additional risk of losing events waiting in the queue |
| Ordering | Follows synchronous execution flow and sink mechanism | Must account for multiple producers, workers, appenders, and collectors |
| Shutdown management | Still needs proper flush/close | Especially needs queue draining, flushing, and wait limits |
| Complexity | Usually simple | Adds queue policy, consumer lifecycle, and monitoring |

**When is it beneficial?** If requests generate many logs and the sink (console in a container, file, or network) has variable latency, an async appender can help reduce direct impact on business thread latency.

**When is it less beneficial?** With low log volume or a very fast sink, adding a queue, scheduling, and context snapshots can create unnecessary overhead. When the queue is continuously full, async only **moves the bottleneck** rather than removing I/O limits.

## 3. The Producer–Queue–Consumer Mechanism

A typical pipeline has three components:

- **Producer:** the application thread calling `log.info(...)`, `log.error(...)`, etc. After passing the level/filter, the backend creates a log event and prepares the data to retain.
- **Queue:** a bounded buffer holding events while waiting to be written, usually using a thread-safe structure. Queue size is a memory/backlog limit to manage, not "bigger is always better."
- **Consumer:** the thread that pulls events out and passes them to the wrapped appender or destination backend; it may format and write to console/file/network.

Example:

```text
Peak: 1,000 events/s arriving for 3 seconds
Sink: at most 600 events/s during the same period

Backlog growth rate ≈ 400 events/s
After 3 seconds, theoretical backlog ≈ 1,200 events
```

These numbers only **illustrate the math at a constant rate**, without accounting for batching, producer blocking, discarding, bursts, overhead, or a full queue. If the queue is small enough, it will hit its threshold before reaching the theoretical backlog; at that point, the overload policy decides whether to block or drop events.

### Latency and Throughput

Async can reduce **synchronous time at the call site**, but does not necessarily reduce **the time from when an event occurs to when it appears at the collector**. A long queue can cause events to "arrive late."

To evaluate this, you should measure at least:

- p50/p95/p99 request duration with logging enabled.
- Total events/s written by the sink.
- Queue depth and remaining capacity over time.
- Number of dropped events (if the backend exposes metrics/hooks).
- Latency from event timestamp → time received by the sink/collector.
- CPU, heap, GC, I/O, and behavior under peak load.

Do not rely solely on a microbenchmark calling `log.debug` with the level disabled; that result does not measure actual logging cost.

## 4. Logback AsyncAppender: Components and Limitations

In Logback Classic, `ch.qos.logback.classic.AsyncAppender` is the asynchronous appender commonly used with SLF4J. It wraps a destination appender (for example `ConsoleAppender` or `RollingFileAppender`) and passes log events through a queue for a worker thread to process.

A valid topology:

```text
SLF4J API
    |
    v
Logback logger hierarchy
    |
    v
ASYNC appender
    |
    +-- queue
           |
           v
         worker
           |
           v
      CONSOLE appender
           |
           v
        stdout
```

Things to note:

1. `ASYNC` does not write to a file/console on its own: it must be attached to a **destination appender**.
2. If root directly references both `CONSOLE` and `ASYNC` (while `ASYNC` also references `CONSOLE`), a single event may be output **twice**.
3. Common versions of Logback Classic support **one destination appender per AsyncAppender**; if you want separate output paths, you must design the corresponding routing/appenders rather than assuming one async wrapper can arbitrarily attach multiple destinations.
4. `AsyncAppender` does not turn messages into JSON, does not auto-generate trace IDs, and does not guarantee durability; those requirements belong to the event creation API, encoder, and collection system.

## 5. Configuring Logback AsyncAppender

Example `logback.xml` using a console appender underneath:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>64</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>0</maxFlushTime>
        <includeCallerData>false</includeCallerData>
        <appender-ref ref="CONSOLE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

This is a **Logback Classic configuration**, not syntax for a JUL `Handler`. Some properties, default values, and supported capabilities vary by version; consult the manual for your specific version before deciding on production values.

### Meaning of Each Property

| Property | Role | Notes |
|---|---|---|
| `queueSize` | Limits the number of events waiting in the queue | Increasing the queue uses more memory and may lengthen time to reach the sink |
| `discardingThreshold` | Controls the threshold at which events considered less important may be dropped | `0` disables selective dropping based on this threshold; does not guarantee zero log loss |
| `neverBlock` | Decides whether to avoid blocking the producer when the queue is full | `false` allows waiting for the queue; `true` may drop events when enqueuing fails |
| `maxFlushTime` | Time to wait for the worker to process the queue when stopping the appender, usually in ms | `0` in Logback means wait indefinitely on stop; if the sink hangs, shutdown can hang |
| `includeCallerData` | Whether to collect additional caller location info (class/method/file/line) | Collecting stack/caller data is expensive; do not enable when unnecessary |
| `appender-ref` | Specifies the underlying destination appender | If the destination is missing, events have nowhere to be written as intended |

With `discardingThreshold`, Logback Classic treats lower-level events (typically TRACE/DEBUG/INFO) as candidates for dropping when the queue is nearly full. The purpose is to prioritize WARN/ERROR levels under overload; exact behavior should be verified per version/configuration. Setting `discardingThreshold=0` **does not turn the queue into durable storage**.

With `neverBlock=false`, if the queue is full, the thread emitting the log may **wait** until space becomes available. This generally prioritizes keeping events over immediate-drop configurations, but forfeits part of async's latency benefit when the sink cannot keep up.

With `neverBlock=true`, the producer usually does not wait; if the event cannot be placed into the queue, the backend may **drop the event**, including important events if the queue is genuinely full. Therefore, do not enable it just because you want "logging not to affect requests" without explicitly accepting the risk of data loss.

## 6. Runnable Java 17+ Example: SLF4J + Logback AsyncAppender

The example below uses **Java 17**, **Maven**, **SLF4J API**, and **Logback Classic**. Goal: show a business thread emitting INFO/WARN events while `ASYNC` sends them to the console via a queue.

With three events, the queue has plenty of space, `discardingThreshold=0`, and `neverBlock=false`. The program **intentionally stops the LoggerContext** so the worker finishes processing the queue before the process exits normally. The example does not simulate a crash or force the queue full; those cases do not have deterministic output.

### 6.1. Project Structure

```text
async-appender-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/logging/AsyncAppenderDemo.java
        └── resources/
            └── logback.xml
```

### 6.2. The `pom.xml` File

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>async-appender-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>com.example.logging.AsyncAppenderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` pulls in the appropriate Logback/SLF4J components according to its dependency declarations. The version in `pom.xml` is pinned **only to illustrate how to reproduce the lesson**, not as a claim that it is the latest release. In real projects, choose a supported version that has been checked against security advisories/BOMs.

### 6.3. The `src/main/resources/logback.xml` File

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>64</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>0</maxFlushTime>
        <includeCallerData>false</includeCallerData>
        <appender-ref ref="CONSOLE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

Only `ASYNC` is attached to root; `CONSOLE` is the **destination appender of ASYNC**, not attached directly to root as well. This configuration avoids duplicating output across two paths.

Setting `maxFlushTime=0` for the demo lets `stop` wait for the worker to drain the queue; in production, consider a bounded shutdown timeout if downstream can hang for a long time.

### 6.4. The `src/main/java/com/example/logging/AsyncAppenderDemo.java` File

```java
package com.example.logging;

import ch.qos.logback.classic.LoggerContext;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class AsyncAppenderDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(AsyncAppenderDemo.class);

    public static void main(String[] args) {
        LOG.info("event=order_accepted orderId={}", "ORD-7");
        LOG.warn("event=retry_scheduled attempt={}", 1);
        LOG.info("event=order_completed orderId={}", "ORD-7");

        // When the example finishes normally, stop the context intentionally.
        // Stopping helps the worker process the already-enqueued events.
        LoggerContext context =
                (LoggerContext) LoggerFactory.getILoggerFactory();
        context.stop();
    }
}
```

This is a **standalone Java file within the Maven project described above**. Do not compile it separately with `javac` alone without a classpath because `LoggerFactory` and `LoggerContext` come from dependencies outside the JDK.

### 6.5. Running with Maven

In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

With the console appender above, the three lines **written by Logback to stdout** in a normal run are:

```text
INFO AsyncAppenderDemo - event=order_accepted orderId=ORD-7
WARN AsyncAppenderDemo - event=retry_scheduled attempt=1
INFO AsyncAppenderDemo - event=order_completed orderId=ORD-7
```

This is the verifiable message/event content; Maven may emit additional build-tool messages if the environment is configured differently. The order above reflects **one producer, one async queue, and one destination appender**. When there are multiple producers and multiple output paths, do not treat this as a global ordering guarantee in a distributed system.

### 6.6. Explaining Why the Output Is Correct

- The root logger at `INFO` accepts `INFO` and `WARN`; there are no DEBUG events in the program.
- All three events are passed to `ASYNC` instead of calling `CONSOLE` directly on the thread emitting the log.
- A 64-element queue is sufficient for the demo's three events, without needing to simulate overload.
- `discardingThreshold=0` prevents AsyncAppender's threshold-based selective dropping; `neverBlock=false` allows the producer to wait if space is needed.
- `%logger{0}` displays the last segment of the logger name as `AsyncAppenderDemo`, while the full logger name remains `com.example.logging.AsyncAppenderDemo`.
- `context.stop()` invokes the stop lifecycle of the appenders, helping flush the queue and close the write destination under normal conditions. Stopping can wait and depends on the worker/sink state; it is not a mechanism for preserving logs when the process is killed with `kill -9` or loses power.
- `<target>System.out</target>` sends events from this appender to **stdout**; do not confuse this with `java.util.logging.ConsoleHandler`, which typically uses stderr.

**Do not call `Thread.sleep(...)` to "wait for logs to finish."** Sleeping is unreliable; proper lifecycle stopping and flushing is better. In long-running server applications, the framework typically owns the `LoggerContext` and stops it during a proper shutdown phase; do not stop the context after every request.

## 7. Policy When the Queue Is Full: Block or Drop?

This is the most important decision when operating an async appender.

### 7.1. Prioritize Keeping Events — Accept That the Producer May Block

Logback example:

```xml
<queueSize>2048</queueSize>
<discardingThreshold>0</discardingThreshold>
<neverBlock>false</neverBlock>
```

This is a **reference configuration snippet** inside `<appender class="ch.qos.logback.classic.AsyncAppender">`, not a standalone XML file. It reduces the risk of losing logs due to threshold-based discarding; when the queue is full, the producer may wait.

Trade-off: if the write destination is continuously slow, request threads may block at log calls and p99 latency increases. This setting does not guarantee zero log loss on crashes, appender errors, collector disconnects, or other policies that drop events.

### 7.2. Prioritize Request Latency — Accept That Events May Be Lost

Example:

```xml
<queueSize>2048</queueSize>
<neverBlock>true</neverBlock>
```

When the queue has no space left, this mode may drop events instead of blocking the producer. Therefore, even for ERROR/WARN messages, **you should not guarantee that an event is written**. For general troubleshooting logs, this may be an acceptable trade-off; for mandatory audit, billing, or security logs, you must evaluate more carefully and typically need a **dedicated durable pipeline**.

### 7.3. Priority-Based Discarding

In many Logback Classic versions, `AsyncAppender` treats TRACE/DEBUG/INFO as less important than WARN/ERROR when the queue is nearly full. `discardingThreshold` controls the threshold at which these events begin to be dropped; setting `0` disables dropping based on that threshold.

However, distinguish between:

- **Threshold-based discard**: dropping certain events before the queue is truly full according to backend policy.
- **neverBlock-based discard**: when enqueuing fails because the queue is full, events may be dropped regardless of level.
- **Loss on shutdown/crash/downstream**: a separate risk that is not addressed simply by setting the threshold to 0.

Do not pick a configuration based solely on property names. Write it down as an operational policy: **which event types may be lost, when to block, how long to time out, and what signals will trigger alerts**.

## 8. Queue Size and Backpressure

### 8.1. A Large Queue Does Not Create Infinite Throughput

Suppose producers generate 4,000 events/s while the sink only processes 1,000 events/s; the backlog will grow by about 3,000 events/s while this load continues. A 12,000-element queue in an ideal model will fill up in about four seconds if initially empty and rates do not change.

Increasing the queue only **buys more time before blocking/dropping**, while using more RAM and increasing the gap between event timestamp and write time. A prolonged sink outage will fill even a large queue.

### 8.2. Memory Cost Is Not Just the Element Count

Each log event may hold a message, arguments, a `Throwable`, MDC/context, and related objects. A large exception record differs significantly from a few-byte message. Estimating queue memory as `queueSize × average event size` is only a starting point; you must measure heap allocation under representative load.

Do not use an oversized queue to hide a sink that is too slow. You need to address sink speed, reduce log volume, sample where appropriate, optimize the encoder, or design a better pipeline.

### 8.3. Backpressure Is Both a Technical and Business Decision

- **Block:** helps limit event loss from the queue, but impacts the application.
- **Drop:** prioritizes keeping the application moving, but reduces diagnostic information.
- **Sample:** records a fraction of repetitive events; must protect mandatory error/audit logs.
- **Spool/durable buffer:** requires a separate durable mechanism; not built into AsyncAppender's in-memory queue.

There is no single "always block" or "always drop" rule for every system. For payments, security audits, or financially impactful events, you may need a **transactional outbox, event store, or audit pipeline** instead of relying solely on asynchronous logging.

## 9. Log Levels and Filters Still Operate Before/Between Layers

AsyncAppender **does not replace the logger level**. For example:

```java
// SLF4J illustration snippet:
LOG.debug("event=cache_probe key={}", key);
```

If the logger's effective level is INFO, a DEBUG event is normally filtered out before reaching AsyncAppender; it does not enter the queue. Increasing `queueSize` will not make DEBUG appear.

In addition, filters on loggers/appenders may drop events before or after other steps depending on the backend. Check the actual topology:

```text
Logger level / filter
       |
       v
AsyncAppender policy
       |
       v
Queue
       |
       v
Worker + destination appender/filter/encoder
```

When logs are missing, distinguish between **filtered out upfront**, **dropped due to overload**, **not yet written by the consumer**, or **written but not collected by the collector**. Each cause has a different fix.

## 10. MDC, Thread Names, and Caller Data in Asynchronous Logging

### 10.1. Why Must Context Be Captured Before Switching Threads?

On a request thread, an event might have:

```text
logger=com.example.OrderService
thread=http-worker-12
traceId=trace-42
requestId=req-42
message=event=order_accepted
```

After enqueuing, the actual write happens on the appender's worker thread, which is **different** from the business thread. If the formatter simply reads `ThreadLocal` or the worker's current MDC at write time, the context may be empty or wrong.

In Logback Classic, the standard `AsyncAppender` prepares data for deferred processing, including the necessary message content and context such as MDC/thread name, before handing the event off to the worker. Therefore, patterns using Logback's MDC can still work with an async appender **when the application has populated MDC properly before calling the logger**.

MDC API example (SLF4J), **an illustration snippet inside a method that has `LOG`**:

```java
import org.slf4j.MDC;

MDC.put("requestId", "req-42");
try {
    LOG.info("event=order_accepted orderId={}", "ORD-7");
} finally {
    MDC.remove("requestId");
}
```

In `logback.xml`, you can use:

```xml
<pattern>%level requestId=%X{requestId} %logger{0} - %msg%n</pattern>
```

With appropriate Logback + SLF4J, the async appender can output the `req-42` value attached to the event even if the caller cleared MDC before the worker actually wrote it. This is an **example of log event context**, not evidence that MDC automatically propagates across application business threads.

### 10.2. MDC Across Other Business Threads Is a Separate Problem

If business code hands off work to an `ExecutorService`, `CompletableFuture`, virtual threads, or callbacks, the application still needs a strategy to **propagate context between tasks**. AsyncAppender only supports event logging after the event has been created. It does not automatically transfer a request ID from a controller to a task running on another thread.

Always clear MDC in `finally`, especially with thread pools, to prevent previous request info from leaking into subsequent requests.

### 10.3. Caller Data

Patterns that include the class, method, file, and line at the call site may require inspecting stack frames. In Logback, AsyncAppender's `includeCallerData` is usually **disabled by default** due to cost. If enabled:

```xml
<includeCallerData>true</includeCallerData>
```

the backend collects caller data early so it does not mistakenly attribute the worker appender as the source. However, collecting stack data can increase CPU and latency on the thread emitting the log, reducing the benefits of async. If you do not need line numbers/methods in production, do not enable it just to make the pattern longer.

## 11. Throwable, Stack Traces, and Mutable Data

### 11.1. Preserving Exceptions Properly

With SLF4J:

```java
// Illustration snippet, where error is a caught Throwable:
LOG.error("event=order_save_failed orderId={}", orderId, error);
```

The trailing `Throwable` object is typically recognized by the logger as the cause in appropriate parameterized logging overloads. AsyncAppender forwards the event to the destination appender; the destination's encoder/layout **must be capable of outputting exceptions** if you want stack traces.

Do not replace the exception object with:

```java
LOG.error("save failed: {}", error.getMessage());
```

That line only logs the message text, which can lose the stack trace and cause chain. Even a properly configured async setup cannot recover an exception if application code did not pass it into the event.

### 11.2. Mutable Arguments

Do not assume that passing a mutable object to the logger and mutating it right after the call will consistently output either the latest or oldest value. Backends often prepare/snapshot certain data before enqueuing, but not every custom object type is deep-copied.

For important information, prefer primitives, `String`, stable IDs, or intentionally snapshotted structured fields. Do not log entire entities containing lazy fields or secrets just because "async will handle it."

### 11.3. Root Cause and Formatting Cost

Long stack traces or JSON serialization can still consume significant CPU. Async can shift part of the cost to the worker, but event creation, argument expression evaluation, and message/context preparation **still occur on the caller side** depending on the backend. Do not conclude that async makes `buildExpensivePayload()` lazy:

```java
// buildExpensivePayload() is still invoked by Java before LOG.debug(...):
LOG.debug("payload={}", buildExpensivePayload());
```

If DEBUG is usually off, use a guard or an appropriate supplier/lazy API to defer expensive expressions; that is a separate concern from an asynchronous appender.

## 12. Logging to Multiple Destinations: Ordering, Duplication, and Reliability

### 12.1. One Async Path to One Destination

Example in `logback.xml`:

```xml
<root level="INFO">
    <appender-ref ref="ASYNC"/>
</root>
```

`ASYNC` wraps `CONSOLE`; events have **one path**. If you add:

```xml
<root level="INFO">
    <appender-ref ref="ASYNC"/>
    <appender-ref ref="CONSOLE"/>
</root>
```

while `ASYNC` still wraps `CONSOLE`, the same event can travel through both paths and appear twice. This is a topology error, not caused by calling `LOG.info` twice.

### 12.2. Multiple Appenders/Queues Do Not Create Global Ordering

A FIFO queue generally preserves **insertion order into that queue**. However, if multiple request threads log concurrently, queue insertion order reflects actual execution scheduling, not the business order of requests.

With two async appenders that have separate queues/workers, console and file may receive events at different times. Distributed collectors also perform batching and retries. When sequence investigation is needed, record **event timestamp, traceId/requestId, attempt, and sequence ID** when required by business logic; do not rely solely on line order in a file.

### 12.3. Do Not Confuse "Enqueued" with "Saved"

Logback AsyncAppender's queue lives in JVM memory. If the process is forcibly killed, the node loses power, or the container is removed without allowing graceful shutdown, events still in the queue can be lost. Even after the worker hands a record to a file appender, the OS still has its page cache and its own flush mechanisms.

If the business genuinely needs durability or exactly-once guarantees, do not use an in-memory async appender as the sole source of truth. Consider a transactional outbox, append-only durable event log, database transaction, or an appropriate audit architecture.

## 13. Shutdown and Flush: Where Logs Are Most Easily Lost

When the application stops, identify the mechanism managing the logging lifecycle:

1. The application stops accepting new work as appropriate.
2. Business tasks are asked to complete/stop according to policy.
3. The logging context or appender receives a `stop` signal.
4. The worker gets a chance to drain the queue, pass events to the destination appender, and flush/close.
5. The process exits within the allowed time window.

The example in section 6 calls:

```java
LoggerContext context =
        (LoggerContext) LoggerFactory.getILoggerFactory();
context.stop();
```

This is intentional shutdown logic for the **Logback demo**, not a pattern to insert after every business method. In Spring Boot or frameworks, the logging lifecycle is usually managed by the framework; do not manually stop the context in the middle of the server's lifecycle.

`maxFlushTime` controls the wait time on stop in Logback AsyncAppender. A value of `0` waits indefinitely and can hang shutdown if the destination appender is stuck; a positive value sets a wait limit, though if the timeout expires while items remain in the queue, some events may go unwritten. Consider:

- The container/orchestrator shutdown grace period.
- File/network sink latency and maximum backlog size.
- How many events could be lost if the process is forcibly terminated.
- The flush capability of the destination appender; not every network sink provides durability on its own.
- Observing unprocessed event counts on shutdown and reporting errors appropriately.

Do not use `Thread.sleep(1000)` as a "flush guarantee": if the backlog is large or the sink is slow, one second provides no certainty.

## 14. Logback AsyncAppender vs. Async Logging in Log4j 2

Logback AsyncAppender and async mechanisms in Log4j 2 share the goal of reducing work on the caller, but they are **not the same classes or configurations**.

### 14.1. Logback AsyncAppender

- Wraps a destination appender and uses a queue/worker.
- Configuration typically resides in `logback.xml`/`logback-spring.xml` (depending on the application).
- Has parameters related to queue size, discarding threshold, neverBlock, shutdown, and caller data.
- When used in Spring Boot, distinguish the actual Logback backend from the framework-selected starters/logging system.

### 14.2. Log4j 2 AsyncAppender

Log4j 2 provides an **AsyncAppender** that wraps other appenders with its own mechanism. Example **Log4j 2 configuration fragment**, not a complete file:

```xml
<Async name="ASYNC">
    <AppenderRef ref="CONSOLE"/>
</Async>
```

Class names, attributes, queue size, blocking, and failover have Log4j 2 semantics; do not copy Logback's `<discardingThreshold>` or `<neverBlock>` tags directly into Log4j 2 XML.

### 14.3. Log4j 2 AsyncLogger

Log4j 2 also has **AsyncLogger**, an architectural approach distinct from merely wrapping an appender. Async loggers can be based on a ring buffer/Disruptor system and require appropriate configuration/dependencies per version. Distinguish between:

- AsyncAppender: the logger emits events to an async appender, which forwards them to a destination appender.
- AsyncLogger: asynchronous logging processing is integrated at the logger/context level with its own architecture.

Do not assume "AsyncLogger is always faster than AsyncAppender"; measure workload, contention, formatting, sink, garbage, queue/ring buffer, and overload policy together.

### 14.4. JUL Handler

`java.util.logging` has `Handler`, `ConsoleHandler`, `FileHandler`, `MemoryHandler`, and the ability to write custom handlers. **Standard JUL does not provide a generic AsyncAppender with the same API/configuration as Logback**. You can build a handler using a queue/worker or use a library/bridge to leverage an async backend.

JUL's `MemoryHandler` holds records in memory and pushes them to a target handler when a condition is met; it is **not a direct replacement** for a worker-queue async appender with separate producer/consumer threads. Having "memory" in the name does not imply non-blocking semantics.

## 15. Security in Asynchronous Logging

Async logging does not automatically strip sensitive data. Passwords, access tokens, API keys, session cookies, card details, emails, or payloads can appear in messages, exceptions, arguments, or MDC.

Because the queue holds events in RAM until the worker writes them, sensitive data can also exist in **queued memory**, in addition to files/collectors once written. Do not put sensitive data into logs, and control destinations, access permissions, and retention.

User-supplied data may contain newlines/control characters; the `{}` placeholder is not an escaping mechanism against log injection. If outputting JSON, use a standard encoder/serializer for proper escaping. For mandatory security or audit records, separate rules apply regarding integrity, durability, and traceability; do not rely on an in-memory async queue without a risk assessment.

Another point: when the queue is full and `neverBlock=true`, even ERROR events may be dropped. For events requiring security evidence, ensure a dedicated path that meets durability requirements rather than merely setting a high log level.

## 16. Practical Testing Before Enabling in Production

### 16.1. Testing Under Normal Load

Emit a controlled number of events and check messages, exceptions, MDC, stdout/file, levels, and ordering in a single-producer scenario. For the example in section 6, after `context.stop()`, expect all three enqueued events.

### 16.2. Burst Testing That Fills the Queue

Generate load higher than the sink's processing rate in a test environment, using a small queue and a controlled slow destination appender. Measure events generated, events written, producer latency, and queue recovery time.

Expectations **should not assume fixed output**, because thread scheduling depends on the machine, OS, and sink. The goal is to verify that the block/drop policy works as designed and to gather the necessary telemetry.

### 16.3. Testing Graceful Shutdown vs. Forced Shutdown

With an undrained backlog, compare:

- `context.stop()` under normal lifecycle.
- Shutdown with a wait timeout shorter than the backlog needs to process.
- Process forcibly terminated or container exceeding its grace period.

Do not trigger crash tests on production systems without a safety plan. Check for log loss and document risk acceptance for each event type.

### 16.4. Testing Context and Exceptions

- Enable `%X{requestId}` in the pattern when the application sets MDC; ensure the right ID appears on events even when the worker writes later.
- Verify no context leaks between request threads.
- Log a real exception and verify the stack trace/cause is output by the encoder.
- Evaluate `includeCallerData=true` if class/method/line is needed; measure overhead.

### 16.5. Testing Downstream Failures

Use a destination that is slow, failing writes, or temporarily disconnected (in a test environment). Verify how the appender handles errors, whether the queue backlogs/drops, whether errors surface in status/metrics, and whether request threads block.

**Note:** not every backend exposes a discarded-events counter through the same API. You may need a status listener, monitoring hook, appender wrapper, or version-appropriate metrics integration.

## 17. Troubleshooting: Missing Logs or Slow Application After Enabling Async

| Symptom | Cause to Check | Verification/Fix |
|---|---|---|
| INFO/DEBUG disappear under heavy load | Discarding threshold is prioritizing WARN/ERROR | Check discard policy and queue pressure |
| Even ERROR disappears | Queue full + `neverBlock=true`, crash, or sink failure | Check drop policy, stop, downstream, and risk level |
| Requests are slow despite async enabled | Full queue causes producer blocking, or event preparation is too heavy | Measure queue depth, p99, caller data, arguments, and sink throughput |
| Shutdown takes too long | `maxFlushTime=0` waits indefinitely, slow/hung sink | Review graceful timeout and set an appropriate policy |
| Logs lost on stop | No stop/flush, short timeout, or forced termination | Design lifecycle and check backlog |
| Logs duplicated twice | Root attaches both `ASYNC` and `CONSOLE`, additivity differs | Inspect the entire appender graph |
| Missing `requestId` | MDC not set before logging, context not propagated across tasks | Check setting and clearing MDC in business threads |
| Caller class/line wrong or missing | Caller data not captured on producer | Check pattern and `includeCallerData` |
| Strange log order | Multiple producers/queues/workers/collectors | Also rely on timestamp, traceId, and business sequence |
| Stack trace missing | Only `error.getMessage()` logged or encoder drops Throwable | Pass Throwable and check layout |
| Unparseable JSON | Manual string concatenation, message contains special characters | Use a structured encoder/serializer |
| DEBUG not appearing | Effective logger level/filter drops before queue | Check level and appender filters |
| Sudden heap growth | Large queue, events/Throwables/payloads holding lots of memory | Measure allocations, shrink payloads, and rebalance queue |
| Logs do not reach collector despite appearing in stdout | Agent/collector after appender is failing | Check pipeline and end-to-end delivery |

## 18. Design and Operations Checklist

Before choosing an async appender, answer:

1. **Where is the real bottleneck?** Logging I/O, JSON encoding, file flush, network, or business CPU processing?
2. **What is the priority?** Reducing p99 latency or retaining as many events as possible under all loads?
3. **How bounded is the queue?** Have you accounted for event memory footprint and drain time on shutdown?
4. **What happens when full?** Block, drop by level, drop all on `neverBlock`, sample, or use another durable mechanism?
5. **Which configuration is deployed?** Are `queueSize`, `discardingThreshold`, `neverBlock`, `maxFlushTime`, and `includeCallerData` properly understood?
6. **What is the destination appender?** Console, rolling file, socket/collector; are there additional buffering or loss points outside the queue?
7. **Are logs duplicated?** Only attach `ASYNC` at root when it already wraps `CONSOLE`; check additivity.
8. **Is context preserved?** MDC, traceId, thread name, exception; is caller data needed?
9. **Is there a valid shutdown mechanism?** Who stops the logging context, grace period, flush timeout, and how is unprocessed backlog reported?
10. **Have overload and downstream failures been tested?** Do not extrapolate production reliability from a three-event queue demo.
11. **Is there a risk of containing secrets?** Messages/Throwables/MDC and retention must be controlled both in RAM and at the sink.
12. **Are telemetry and alert thresholds in place?** Queue depth, dropped events, sink failures, request latency, and collector lag.
13. **Are there high audit/durability requirements?** If so, use a durable architecture rather than treating an in-memory queue as the sole data source.

## 19. Conclusion

An **async appender** decouples the log-emitting thread from most logging work using a queue and a dedicated worker. It can improve request latency when logging I/O is slow, but trades that off against **backlog, memory usage, potential blocking or dropping of events under overload, and the risk of losing records on shutdown/crash**.

In Logback, `AsyncAppender` is suitable once you understand `queueSize`, `discardingThreshold`, `neverBlock`, `maxFlushTime`, MDC/caller data, and the destination appender. In Log4j 2, distinguish `AsyncAppender` from `AsyncLogger`; in JUL, do not assume the same built-in async appender exists. Measure and test the entire pipeline rather than simply enabling async and assuming every log will arrive safely.
