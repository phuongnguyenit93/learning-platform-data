# Flushing Async Logs in Java

## 1. What is async log flushing and what problem does it solve?

In **asynchronous logging**, calling `logger.info(...)` or `logger.error(...)` typically places an event into a queue or buffer and returns control to the application thread. A background thread takes those events, formats them, and forwards them to a file, console, network, or centralized system. As a result, business-logic threads spend less time waiting on I/O, but at any given moment there may still be logs **not yet written to the destination**.

**Flushing async logs** is the operation or process of ensuring that a group of events accepted before a defined point are **fully processed through the queue and their output buffers are pushed down to the target layer** according to the specific contract of the logger/appender. It is important to distinguish each layer to avoid assuming that a logging call has already persisted data safely.

~~~text
Application thread
   │ logger.info("order-created")
   ▼
[Queue / Ring Buffer] -- event accepted, may still be waiting
   │
   ▼
[Consumer / Async Appender] -- formats and forwards event
   │
   ▼
[Buffered writer / File appender] -- bytes may still be in buffer
   │ flush()
   ▼
[OS / File system / Network] -- pushed down to the next layer
   │ fsync / durable ACK (if supported and required by the system)
   ▼
[Durable storage / Remote collector]
~~~

The same word “written” can describe different milestones:

| Milestone | What has happened | What is not guaranteed |
| --- | --- | --- |
| **Accepted / enqueued** | The async logger accepted the event and may have returned to the caller | Whether the consumer has processed it; whether it will be discarded later |
| **Dispatched / processed** | The consumer took the event and called the target appender | Whether the appender buffer has been flushed; whether the target appender succeeded |
| **Flushed to OS / transport** | The writer/appender buffer has been pushed down to the stream, OS, or transport per the API | That a power loss or server crash will not lose data |
| **Durable / acknowledged** | There is a suitable durability commitment, e.g. sync storage or an explicit ACK contract from the receiving system | End-to-end guarantees beyond the scope of the ACK |

For example, `BufferedWriter.flush()` guarantees that characters remaining in the Java buffer are written to the underlying writer, but it is **not equivalent** to `FileChannel.force(true)` or an fsync guarantee. If logs are transmitted over the network, flushing on the sender side also does not mean the receiving system has stored them durably.

## 2. When is flushing needed?

Commonly important moments include:

1. **Graceful shutdown/redeploy:** stop accepting new work, wait for log-producing tasks to finish, let the logging context drain the queue, and flush and close appenders before the JVM stops.
2. **Switching or closing a sink:** before closing, rotating/changing a file, or disconnecting, pending records must be completed according to the appender/framework mechanism.
3. **Integration testing:** after emitting logs asynchronously, you need a verifiable completion point before opening the file to read or assert results.
4. **Checkpoints with explicit log requirements:** an administrative tool or workflow needs to wait for logs prior to that point to be processed. You must check whether the framework actually provides an appropriate drain/flush API.
5. **After a large write burst:** batch flushing at the appender layer can be used if supported, but you should not trigger a synchronous flush on every event if throughput is the goal.

**Do not flush by default after every request or every log statement.** Doing so can negate the benefits of async logging, increasing tail latency and I/O contention. If an audit event or financial transaction must be durably stored **before returning success**, use a mechanism with durable confirmation (database, outbox, durable queue, appropriate synchronization), rather than treating a standard async log file as a transactional source of truth.

## 3. Conditions for “flushed” to be truly meaningful

A proper flush design must clearly answer three questions:

**(a) Which set of events are we waiting for?** The flush point must be placed **after** the events that need to be guaranteed. With multiple concurrent threads, an event just created but not yet enqueued may fall **after** the flush point. During shutdown, you must control whether producers are still running.

**(b) Which stage are we waiting for?** Simply checking `queue.size() == 0` is not enough: the consumer may have taken the last event out of the queue but still be writing to a file or sending over the network. The completion milestone must be confirmed **after** the consumer has processed the preceding events and called flush on the sink.

**(c) How are failures reported?** Flushing can time out or hit an I/O error. The system should have a policy for how long to wait, whether to retry/failover, which channel to report errors to, and metrics for dropped events. If the async framework catches or logs errors internally on a background thread, the caller will not necessarily receive an exception.

Do not replace those conditions with `Thread.sleep(1000)`: waiting a fixed one second only increases the probability that the consumer finishes, without establishing a guarantee.

## 4. Standalone Java 17 example: using a barrier in the queue

The following example uses `ExecutorService.newSingleThreadExecutor()` as a **simulation of an async consumer** and `BufferedWriter` as the sink. Two write operations and a flush operation are submitted **in exact order** to the same executor. The `Future.get()` of the flush task acts as a **barrier**: when it returns normally, the consumer has finished running the two preceding operations and has called `writer.flush()`.

Create **AsyncFlushDemo.java**:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class AsyncFlushDemo {
    private static void append(BufferedWriter writer, String line) {
        try {
            writer.write(line);
            writer.newLine();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static void flush(BufferedWriter writer) {
        try {
            writer.flush();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    public static void main(String[] args) throws Exception {
        Path path = Path.of("async-demo.log");
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (BufferedWriter writer =
                     Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
            Future<?> first = worker.submit(
                    () -> append(writer, "event=start"));
            Future<?> second = worker.submit(
                    () -> append(writer, "event=done"));
            Future<?> barrier = worker.submit(() -> flush(writer));

            barrier.get(); // Wait for the preceding write operations and flush to finish.
            first.get();   // Detect IOException from the first write task.
            second.get();  // Detect IOException from the second write task.
            System.out.println("flush complete");
            System.out.println(Files.readAllLines(path, StandardCharsets.UTF_8));
        } finally {
            worker.shutdown();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                worker.shutdownNow();
            }
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 AsyncFlushDemo.java
java AsyncFlushDemo
~~~

**Exact stdout:**

~~~text
flush complete
[event=start, event=done]
~~~

The file `async-demo.log` contains two lines:

~~~text
event=start
event=done
~~~

**Why does the example work?**

- `newSingleThreadExecutor()` executes submitted tasks sequentially in the order they were submitted to the executor.
- `append(...)` writes to `BufferedWriter`. When the write task finishes, the data **may still be in the buffer**.
- The third task calls `writer.flush()`, followed by `barrier.get()` waiting for the flush to actually complete. Only then is the file read for verification.
- `first.get()` and `second.get()` detect exceptions from the two write tasks; waiting only on the barrier without checking earlier task failures can miss errors.
- `shutdown()` and `awaitTermination(...)` reclaim the executor; `try-with-resources` closes the writer. The order in the example is safe because the barrier has already completed before exiting the `try` block.

This is an **illustrative model**, not a production logger. The default executor has an unbounded queue fixed by `newSingleThreadExecutor()`; a real application needs capacity policies, backpressure, monitoring, timeouts, and error handling when the sink hangs. The barrier here only covers **tasks already enqueued before it on the same executor**. If other producers continue submitting concurrently, you must synchronize the log-acceptance point or stop the producers to establish a flush boundary. It also does not guarantee an OS fsync.

## 5. Flushing in Java Util Logging (JUL)

`java.util.logging.Handler` has the method:

~~~java
public abstract void flush();
~~~

According to the JDK documentation, the contract is to flush **any buffered output of the Handler**. `StreamHandler.flush()` likewise describes flushing buffered records in the stream. However:

- Standard JUL **does not make every `Logger` an async logger by default**. With synchronous handlers, `flush()` mainly pushes the stream buffer.
- If an application builds a custom `AsyncHandler` with its own queue delegating to a `FileHandler`, calling `underlyingFileHandler.flush()` **does not force** events still in the async queue to reach that handler first.
- A custom async handler that wants to support flushing needs a **drain barrier** or equivalent mechanism, calling the target handler's flush **after** all events up to that point have been processed, and clearly documenting timeouts and error reporting.
- JUL's `Logger` has no general-purpose `flush()` method. Iterating over `logger.getHandlers()` only sees handlers attached directly to that logger; parent loggers may also have handlers.

Example illustrating flushing existing handlers:

~~~java
for (java.util.logging.Handler handler : logger.getHandlers()) {
    handler.flush();
}
~~~

The snippet above requires `logger` to be declared and configured; it is **not a queue-draining solution** for all async architectures, and it does not cover parent logger handlers.

## 6. Logback: AsyncAppender draining on LoggerContext stop

In Logback Classic, `AsyncAppender` uses a `BlockingQueue` and a background worker to forward events to the target appender. When the application shuts down or redeploys, you must **stop the LoggerContext** so the async appender gets a chance to process remaining events in the queue. The stop method waits up to `maxFlushTime`.

Example **logback.xml** file (with appropriate Logback Classic and SLF4J dependencies):

~~~xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>app.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>2048</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>5000</maxFlushTime>
        <appender-ref ref="FILE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
~~~

Meaning of the parameters:

| Attribute | Effect and trade-offs |
| --- | --- |
| `queueSize=2048` | Up to 2,048 pending events in the AsyncAppender queue; should not be guessed arbitrarily if write/sink rates fluctuate. |
| `discardingThreshold=0` | Disables the default rule that proactively drops TRACE/DEBUG/INFO records when the queue is nearly full; **not** an absolute guarantee against log loss. |
| `neverBlock=false` | When the queue is full, producers may block until space is available; chooses backpressure instead of dropping events as with `neverBlock=true`. |
| `maxFlushTime=5000` | On stop, lets the worker wait up to about 5 seconds to finish flushing remaining events; events not processed in time risk being lost. |

In Logback, `maxFlushTime=0` means waiting **indefinitely** for the worker to finish on stop; this reduces the risk of losing events due to timeout but can hang shutdown if the sink is slow or unresponsive. Choose the timeout and the runtime environment's graceful termination period consistently.

For applications that **manage the Logback lifecycle themselves** (without a framework controlling it), the snippet below illustrates calling stop at the end of shutdown:

~~~java
import ch.qos.logback.classic.LoggerContext;
import org.slf4j.LoggerFactory;

// Execute once when the application stops, after producers have finished.
LoggerContext context =
        (LoggerContext) LoggerFactory.getILoggerFactory();
context.stop();
~~~

This is an illustrative snippet requiring the Logback library; it does not run standalone with only the JDK. In Spring Boot or a container, prefer the framework-managed lifecycle mechanism and ensure it is executed. **Do not call `context.stop()` at the end of every request**, because stopping disables the logging context and appenders for subsequent work.

**Note:** By default, Logback may discard less severe events when the queue reaches about 20% remaining capacity. `discardingThreshold=0` changes this discard policy, but it cannot save logs when the server is killed, disk space runs out, the sink fails, or shutdown exceeds its timeout.

## 7. Log4j 2: Async Appender and shutdownTimeout

Log4j 2 has both **Async Appender** (queue and background thread) and **Async Logger** (using Disruptor); these are two different architectural choices. This example uses **Async Appender**.

Create **log4j2.xml** on the classpath of an application configured with `log4j-api` and `log4j-core`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <File name="FILE" fileName="app.log">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
        </File>

        <Async name="ASYNC"
               bufferSize="1024"
               blocking="true"
               shutdownTimeout="5000">
            <AppenderRef ref="FILE"/>
        </Async>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="ASYNC"/>
        </Root>
    </Loggers>
</Configuration>
~~~

- `bufferSize` bounds the Async Appender queue.
- `blocking=true` makes the caller wait or applies the appropriate queue-full policy when there is no space; check the queue-full policy for your running Log4j version. Discard/failover configurations can alter this behavior.
- `shutdownTimeout=5000` allows waiting up to 5,000 ms for the worker to stop when the Async Appender shuts down. According to Log4j 2 documentation, a value of `0` waits until the queue is empty.
- The target appender `FILE` must be declared **before** the `ASYNC` appender that references it to support shutting down in the proper order.
- Log4j 2's Async Appender flushes the target appender buffer toward the OS **after a batch when the queue is empty**. That does not guarantee the data has been durably synced to the storage device.

If the application **manages Log4j 2 itself**, you can shut down the logging context at the end of the lifecycle:

~~~java
org.apache.logging.log4j.LogManager.shutdown();
~~~

`LogManager.shutdown()` is a synchronous operation that can wait for pending logs to be processed (including over the network) and stops the caller's corresponding context. Do not call it in normal request-handling code or in tests that continue writing to the same context. In container/framework-managed applications, coordinate with the lifecycle to avoid closing the context too early.

Do not confuse `immediateFlush=true` on a file appender with “the caller waits for the entire async queue”. That file appender setting only determines how it pushes its buffer **once the consumer has already called the appender**, while the queue ahead of it may still hold events.

## 8. Safe graceful shutdown sequence

A typical shutdown sequence:

~~~text
Receive shutdown signal
  → stop accepting new requests/messages/jobs
  → wait for or cancel in-flight tasks in a controlled manner
  → stop producers from generating new logs
  → stop logging context/async appender (drain queue + flush sink)
  → release files, sockets, logging workers
  → JVM exits within the runtime environment's deadline
~~~

Set the **JVM/container exit timeout larger than the total budget** for closing connections, finishing work, and flushing logs. If the container sends SIGKILL right after the timeout, shutdown hooks or logging workers get no further chance to run.

Distinguish between:

- **Graceful exit:** the logger is stopped and given a chance to drain the queue within the deadline.
- **Abrupt termination:** `kill -9`, JVM crash, OS failure, or power loss can lose any events not yet truly durable.
- **Hanging sink:** waiting indefinitely can keep the process alive; a timeout allows exiting, but you must accept that logs may be lost.
- **Still-active producers:** if a thread keeps emitting logs after the logging context has stopped, new events may be rejected or not written; coordinate the shutdown order.

Shutdown hooks can assist, but they do not replace container lifecycle management. Do not rely on `finally` blocks or shutdown hooks to claim guarantees when the JVM is forcibly killed.

## 9. Incorrect ways to “flush”

| Common mistake | Why it is wrong or insufficient | Appropriate approach |
| --- | --- | --- |
| Calling `logger.info(...)` and immediately opening the file to check | The call may have only enqueued the event; the consumer has not run yet | Use an official barrier/flush or stop the context in the test |
| `Thread.sleep(500)` before shutting down | No guarantee on drain time; depends on load and I/O | Wait for a completion signal with a meaningful deadline |
| Waiting until `queue.isEmpty()` | The consumer may still be processing the event it just took | Wait for the worker to finish + flush the target |
| Calling `System.out.flush()` when using an async file logger | Flushes the wrong stream and bypasses the logging queue | Use the corresponding async appender and file sink mechanisms |
| Enabling `immediateFlush=true` and believing every `logger.info` is synchronous | A queue still sits between the producer and the consumer | Distinguish flushing the sink from draining the queue |
| Setting `neverBlock=true` to reduce latency while expecting zero-loss | A full queue can drop events | Explicitly define log-loss tolerance, backpressure, and capacity |
| Waiting indefinitely on shutdown | A broken sink can prevent the process from exiting | Choose a deadline, monitoring, alerts, and a fallback path |
| Calling `LoggerContext.stop()` after every request | The context is stopped; subsequent requests no longer have active appenders as before | Close only at lifecycle shutdown |
| Treating `flush()` as fsync or a remote durable ACK | Flush usually only pushes data to the next layer | Use durable synchronization mechanisms if the business requires it |

## 10. Designing and operating to minimize log loss

**Queue policy.** Choose capacity, blocking, or discarding based on the log generation rate and sink processing rate. For example, if an application emits 8,000 events/sec during a burst while the sink processes 6,000 events/sec, the backlog grows by about 2,000 events/sec during the burst; a 10,000-element queue can fill up in roughly 5 seconds if starting empty and the load holds steady. This is only a rough back-of-the-envelope estimate for load testing, not a substitute for real benchmarking.

**Measure bottlenecks.** Observe pending event counts, drop rates, producer block time, sink throughput, I/O errors, flush latency, and stop duration. Metric names depend on the framework and monitoring system; do not assume every library exposes all of these metrics out of the box.

**Classify criticality.** Routine INFO/DEBUG logs can tolerate some risk of loss in exchange for throughput. Mandatory audit logs have stricter requirements: design durable storage/queues, ACK mechanisms, idempotency, and dedicated retry policies. An async log file is not a durable audit system by default.

**Manage the sink.** Identify whether data goes to a file, container stdout, a collection agent, or a network endpoint. For stdout collected by a container runtime, flushing inside the JVM only moves data to the pipe/stream; there are still buffers and loss risks along the collection pipeline outside the JVM. For network endpoints, “sent” is different from “server received” and “server committed”.

**Respect data boundaries.** Large files have their own rollover/rotation; do not externally close the appender's `FileOutputStream` or force a separate file handle assuming it will drain all data sitting in the logger's queue.

## 11. Testing flush and shutdown

Minimum test suite:

1. **No load:** write two events, wait on the appropriate barrier/flush, and verify they appear in the sink in the right order. The Java 17 example above tests this exact scenario.
2. **High load where the sink keeps up:** emit many logs concurrently, stop the producers, shut down the context, count logs with unique IDs versus accepted count, and measure drain time.
3. **Slow or paused sink:** test a full queue, verify the block/discard policy and lost-log count, and test the shutdown deadline.
4. **Shutdown with events still in the queue:** ensure closing the context actually waits for the worker within the deadline while no new producers remain.
5. **I/O errors:** disk full, unwritable file, disconnected network; observe how the framework reports errors via status logger, metrics, or ErrorManager, and check whether exceptions reach the caller.
6. **Forcible termination:** test non-graceful process termination in a test environment; record the number of missing logs to understand the design limits.

Tests must distinguish between **events for which producers called the logger**, **events the framework actually accepted**, and **events that appeared at the sink**. If the configuration allows dropping when the queue is full, counting a mismatch without knowing where events were dropped leads to wrong conclusions. When durability must be verified, write tests matching the fsync contract or the receiving system's acknowledgment, rather than merely re-reading a file right after `flush()`.

## 12. Self-check questions

1. Why might `logger.info(...)` have returned while the log line still does not appear in the file?
2. Why is `queue.isEmpty()` not enough to confirm that flushing is complete?
3. In the `AsyncFlushDemo` example, what makes `barrier.get()` meaningful? If a **different** executor were used for the barrier, what would no longer be guaranteed?
4. How does `BufferedWriter.flush()` differ from `FileChannel.force(true)`?
5. In Logback, how do `maxFlushTime=0` and `maxFlushTime=5000` differ? Why does `discardingThreshold=0` not mean zero-loss?
6. In Log4j 2, does `immediateFlush` force business threads to wait for the async queue to empty?
7. If an application running in a container receives SIGKILL before the async appender finishes stopping, which logs can be lost?
8. When audit logs require guaranteed durability, why is a confirmation mechanism beyond an async file logger needed?

**Answer hints:** (1) the log may have only been enqueued; (2) the consumer may still be writing; (3) the same single-threaded executor preserves order, whereas a different executor provides no barrier for the old queue; (4) flushing a Java buffer does not mean forcing to the storage device; (5) waiting indefinitely vs. up to 5 seconds, and other causes of log loss still exist; (6) no; (7) events not yet durable or committed by the receiving system; (8) explicit durability and acknowledgment are required.

## 13. Official references

- [Java SE 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): `flush()` and `close()` contracts.
- [Java SE 17 — StreamHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html): flushing the handler's record buffer.
- [Logback — AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html): `queueSize`, `discardingThreshold`, `neverBlock`, `maxFlushTime`, and shutdown.
- [Apache Log4j 2 — Delegating Appenders / Async](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html): queue, batch flush, `shutdownTimeout`, and queue full.
- [Apache Log4j 2 — Asynchronous loggers](https://logging.apache.org/log4j/2.x/manual/async.html): distinguishing Async Logger and Async Appender, queue-full policies.
- [Apache Log4j 2 — LogManager API](https://logging.apache.org/log4j/2.x/javadoc/log4j-api/org/apache/logging/log4j/LogManager.html): logging context shutdown method.
