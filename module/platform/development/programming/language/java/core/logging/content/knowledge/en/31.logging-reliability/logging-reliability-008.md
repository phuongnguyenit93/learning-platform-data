# Flush on Crash in Java Logging: Limits, Safeguards, and Verification

## 1. What Does "Flush on Crash" Actually Mean?

In **logging reliability**, "flush on crash" is a way to reduce the risk of losing log events when an application or JVM terminates abnormally. The first thing to understand: **a process that has already been terminated cannot execute another flush command after the moment it dies**. We can only reduce the window of unbuffered data **before an incident**, coordinate shutdown while the system is still under control, and use more reliable storage infrastructure if records truly must survive a crash.

Java logging can pass through multiple layers:

~~~text
Business thread
   │ logger.error("...") / logger.info("...")
   ▼
Logging event: level + message + exception + context
   │
   ├─ Synchronous logger/appender: processed immediately on the calling thread
   │
   └─ Async queue / ring buffer: event may still be waiting
         │
         ▼
      Background consumer
         │
         ▼
      Encoder / BufferedWriter / byte buffer
         │ flush()
         ▼
      OS page cache / file system / socket
         │ force() / fsync or ACK commitment at destination
         ▼
      Local storage / collector / durable log store
~~~

A `logger.info(...)` call returning does not necessarily prove the data has traversed all layers. "Flush" may refer to **draining the async queue**, **flushing the writer/appender buffer**, or **forcing data down to the storage device**. These three actions have different contracts; a single word "flush" cannot guarantee all three.

### Key States

| State | Meaning | Remaining Risk |
| --- | --- | --- |
| Created | Caller has created or prepared the log event | Not yet filtered or received by the backend |
| Accepted/enqueued | Event has entered the async queue or been accepted by the appender | JVM dies before the consumer processes it; a full queue may drop it |
| Consumed/encoded | Consumer has processed it and possibly produced bytes | Bytes may still reside in the Java/encoder buffer |
| Writer flushed | `flush()` pushes the Java buffer down to the stream/OS | Does not equate to durable persistence if the OS or host crashes |
| File forced | `FileChannel.force(...)` attempts to push changes to the storage device | Guarantees depend on the local filesystem, hardware, and sync scope |
| Remote acknowledged | Collector receives/writes data under a specific ACK contract | A "received" ACK is not necessarily a "durably committed" ACK |

Do not treat a regular log file as a committed transaction. If the business requires **zero loss of audit events**, you must design a write-ahead log, durable queue, transactional outbox, or data store with appropriate durability acknowledgments.

## 2. JVM Termination Types and Flush Capability

| Scenario | What Can Usually Happen? | Can You Rely on Shutdown Hooks? |
| --- | --- | --- |
| Application finishes normally | Lifecycle-management code closes/flushes appenders; JVM runs shutdown sequence | Can run; still must organize proper shutdown order |
| `System.exit(code)` | Initiates the JVM shutdown sequence and registered hooks | Hooks are usually started, but may be time-bounded by the environment |
| SIGTERM/interrupt handled by the JVM | JVM can perform a controlled shutdown depending on the platform | Has a chance; not an absolute guarantee when there are timeouts or forced termination |
| `Runtime.getRuntime().halt(code)` | JVM terminates forcibly, without starting/waiting for shutdown hooks | **No** |
| SIGKILL / `kill -9` or Windows `TerminateProcess` | Operating system terminates the process | **Cannot be relied upon** |
| JVM fatal error/native crash | JVM may stop without going through the normal lifecycle | No guarantee |
| Power loss/OS crash/device failure | Both the process and the operating system may stop working | No opportunity to flush after the incident |

An uncaught exception in **a single thread** is not by default a "JVM crash." The thread's handler may log the stack trace and other threads continue running; the application can also catch and handle the exception proactively. Do not simulate a crash by merely throwing a `RuntimeException` in a task and then concluding whether shutdown hooks run or not.

**`System.exit(...)` differs from `Runtime.halt(...)`.** The JDK explicitly states that `halt` does not initiate shutdown hooks. Therefore, the practical example in section 5 uses `halt` in a child process to test what happens if a writer is not closed.

## 3. Distinguishing Java Buffers, OS Cache, and Durable Storage

### 3.1. `BufferedWriter.flush()`

When a `BufferedWriter` has received text but the buffer is not yet full, characters may **not yet be pushed** down to `OutputStreamWriter`, `FileOutputStream`, and the operating system. Calling `writer.flush()` flushes the writer/stream buffers on the Java side according to the `Writer.flush()` contract.

~~~java
writer.write("event=order_paid");
writer.newLine();
writer.flush();
~~~

This is an illustrative snippet requiring that `writer` has already been created and managed. `flush()` changes when bytes reach the lower layer; it is **not** equivalent to guaranteeing "written to the physical device" in the event of power loss.

### 3.2. `FileChannel.force(boolean)`

For a local file, `FileChannel.force(true)` requests synchronizing changes to **content and metadata** down to the storage device; `force(false)` requests synchronizing at least the content. JDK 17 provides a strong contract for files residing on a **local storage device**, while explicitly stating there is no similar guarantee for files on non-local devices.

Important condition: data still in `BufferedWriter` **has not necessarily been written to the channel yet**. The correct order when using both layers is:

~~~java
writer.flush();                     // Push bytes down to FileOutputStream.
fileOutputStream.getChannel().force(true); // Sync file via the associated channel.
~~~

This snippet requires `writer` to be built on **that exact** `fileOutputStream`. Do not open another channel separately and call `force` assuming all buffers inside a logger are flushed; a channel has no knowledge of data sitting in another Java buffer.

In practice, durability also depends on the filesystem, device, controller, battery-backed cache, how directory metadata is fsynced when creating/renaming files, the network, and the storage layer's contract. `force(true)` does not automatically guarantee every point in the logging pipeline from application to collector.

### 3.3. Logger/Appender Flush

A file appender may have `immediateFlush=true` to flush its buffer after processing an event. However, if an **AsyncAppender** sits in front of it, events that have not yet reached the file appender cannot be affected by this property. Distinguish between:

- **Queue drain:** the worker has taken and processed events prior to a checkpoint.
- **Appender flush:** the appender has pushed bytes past its buffer.
- **Durable commit:** the storage layer or remote collector has a durability commitment.

There is no universal `Logger.flush()` method across JUL, SLF4J, Logback, and Log4j 2. You must use the lifecycle API or barrier mechanism of each backend.

## 4. Where Are Logs Lost During a Crash?

Consider an event created at 10:00:00.000 and the JVM being killed at 10:00:00.005:

1. **Before entering the queue:** the event may be filtered out or not yet received by the backend.
2. **In the async queue:** the producer has returned, but the consumer has not yet taken the event; the queue is in-process RAM data and disappears when the JVM dies.
3. **During encoding:** the consumer has taken the event but has not finished formatting it; the queue may already be empty even though the log has not reached the file.
4. **In the writer/encoder buffer:** the event has become text/bytes, but resides in a heap/direct buffer.
5. **In the OS page cache:** the JVM has flushed, but an OS crash or power loss can still lose unsynced data.
6. **In transit:** container stdout, pipes, sockets, logging agents, or collectors may each have their own buffers.
7. **At the collector:** HTTP 200, a successful TCP write, or "received" may not mean the record has been durably committed; check the specific contract.

If only the JVM dies while the operating system remains alive, bytes already flushed to the OS have a chance to continue being written and can be read immediately. If the OS or host itself dies, that conclusion no longer holds. Therefore, tests that "`kill -9` a Java process and then read the file" **do not verify** resilience against power loss.

## 5. Standalone Java 17 Example: Simulating Forced Termination of a Child JVM

Goal of the example: **compare three states of the same line of text** when a child JVM is terminated with `Runtime.halt(23)`. The parent Java process runs three child processes sequentially, reads the file after each child finishes, and prints the results.

- `buffered`: writes a small line to `BufferedWriter` and then halts without flushing.
- `flushed`: flushes the writer before halting.
- `forced`: flushes the writer, then calls `FileChannel.force(true)` before halting.

Create the file **CrashFlushDemo.java**:

~~~java
import java.io.BufferedWriter;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public final class CrashFlushDemo {
    private static final String[] MODES =
            {"buffered", "flushed", "forced"};

    private static void runChild(String mode, Path path) throws Exception {
        // Do not close the stream: simulates an abruptly terminated JVM.
        FileOutputStream file = new FileOutputStream(path.toFile());
        BufferedWriter writer = new BufferedWriter(
                new OutputStreamWriter(file, StandardCharsets.UTF_8), 8192);
        writer.write("event=critical");
        writer.newLine();

        if ("flushed".equals(mode) || "forced".equals(mode)) {
            writer.flush();
        }
        if ("forced".equals(mode)) {
            file.getChannel().force(true);
        }
        Runtime.getRuntime().halt(23);
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 3 && "--child".equals(args[0])) {
            runChild(args[1], Path.of(args[2]));
            return;
        }

        Path directory = Files.createTempDirectory("flush-crash-demo-");
        String executable = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win")
                ? "java.exe" : "java";
        String java = Path.of(System.getProperty("java.home"),
                "bin", executable).toString();
        try {
            for (String mode : MODES) {
                Path path = directory.resolve(mode + ".log");
                Process process = new ProcessBuilder(
                        java, "-cp", System.getProperty("java.class.path"),
                        CrashFlushDemo.class.getName(),
                        "--child", mode, path.toString())
                        .start();
                int exit = process.waitFor();
                String content = Files.readString(path,
                        StandardCharsets.UTF_8).trim();
                if (content.isEmpty()) {
                    content = "<empty>";
                }
                System.out.println(mode + ": exit=" + exit
                        + " content=" + content);
                Files.deleteIfExists(path);
            }
        } finally {
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Compile and run in the directory containing the source file with **JDK 17+**:

~~~bash
javac --release 17 CrashFlushDemo.java
java CrashFlushDemo
~~~

**Exact stdout in a normal runtime environment with a local filesystem:**

~~~text
buffered: exit=23 content=<empty>
flushed: exit=23 content=event=critical
forced: exit=23 content=event=critical
~~~

The **parent** process exits with code `0`; all three **child** processes exit with code `23`. The example prints nothing to stderr under normal conditions.

**Result explanation:**

- `BufferedWriter` has an 8,192-character buffer; the small line is not enough to fill the buffer. When the child calls `halt(23)`, the code does not close/flush the writer, so the file is created but contains no text.
- When `writer.flush()` is called, the text moves to `FileOutputStream` and the OS. Because here **only the child JVM** stops, the parent process can read the bytes that reached the OS.
- The `forced` mode additionally calls `file.getChannel().force(true)` on the channel associated with that same flushed stream. The **read-back** result looks identical to `flushed`, but the request to sync to storage is stronger under the JDK contract for local files.
- You cannot prove the difference between `flushed` and `forced` simply by reading the file immediately after the child JVM stops: the OS is still running and holds its cache.
- Files are created in a temporary directory, one per mode, and then deleted. The program intentionally halts only the **child process** so it does not stop the host program or other applications.

This example is a lesson about **buffers and process termination**, not a logger implementation or an OS crash test. Do not add `Runtime.halt(...)` to business applications to "test flushing" in production; use an isolated test environment.

## 6. With java.util.logging (JUL): Flushing Handlers Does Not Save Every Crash

JUL is the logging system built into the JDK; common handlers operate synchronously unless the application adds an async mechanism of its own. `java.util.logging.Handler` provides `flush()` and `close()`; `StreamHandler` implements flushing for the target stream.

Illustrative snippet in an application that already has a `java.util.logging.Logger logger`:

~~~java
for (java.util.logging.Handler handler : logger.getHandlers()) {
    handler.flush();
}
~~~

This only flushes **handlers attached directly** to the logger; events may still be processed by a parent logger's handler or a custom async layer. It does not create a queue-draining mechanism for a custom async handler.

When using file logging:

- Verify that `FileHandler` and the formatter/handler levels are configured correctly.
- Determine the actual `publish` and `flush` timing of the handler; do not assume all custom handlers share the same semantics.
- If building a custom async handler, use an ordered barrier: stop accepting new events, wait for the worker to process events before the barrier, flush the target handler, and then confirm completion.
- If a handler remains unclosed when the process is halted via `halt`, `close()` or shutdown hooks will not have a guaranteed chance to run.
- `Handler.flush()` and `FileChannel.force(...)` are two different layers; the `Handler` API does not by itself commit an fsync to the device.

If high durability is required, evaluate the sink and application policy rather than merely adding a `flush()` call when an exception occurs.

## 7. With Logback Classic: immediateFlush and AsyncAppender

Logback `OutputStreamAppender` and `FileAppender` have an `immediateFlush` option. It defaults to `true` in the documented appenders, meaning that after the appender **actually receives and processes** an event, the output stream is flushed. When set to `false`, throughput may increase, but data sitting in the buffer risks being lost if the appender is not closed properly.

Example **logback.xml** for an application with Logback Classic properly installed:

~~~xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/app.log</file>
        <append>true</append>
        <immediateFlush>true</immediateFlush>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
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

Properties related to log loss:

| Property | Purpose | Limitation |
| --- | --- | --- |
| `immediateFlush=true` on FILE | Pushes the file appender's buffer after an event has been processed | Cannot flush events still in ASYNC's queue; is not fsync |
| `queueSize=2048` | Limits the number of events waiting in the queue | A larger queue increases the amount of in-RAM data at risk of loss on crash |
| `discardingThreshold=0` | Disables proactively discarding TRACE/DEBUG/INFO when the queue nears full | Does not provide a zero-loss guarantee on kill or sink failure |
| `neverBlock=false` | When the queue is full, producers are normally blocked to create backpressure | Can increase application latency; JVM can still die |
| `maxFlushTime=5000` | When stopping the async appender, waits up to 5 seconds for the worker to process pending events | Once the timeout expires, remaining pending logs may be lost |

By default, Logback `AsyncAppender` may drop TRACE/DEBUG/INFO when roughly 20% of queue capacity remains, to protect throughput. Changing `discardingThreshold` adjusts the policy; it does not eliminate log loss caused by crashes.

**Properly ordered graceful shutdown:**

1. Stop accepting new requests, messages, or jobs; wait for in-flight producers to finish within a deadline.
2. Ensure no threads continue generating critical logs into the context about to be stopped.
3. Stop `LoggerContext` via the framework/container lifecycle so `AsyncAppender` can drain its queue and the file appender can close/flush.
4. Ensure the container shutdown deadline covers the wait time; if SIGKILL arrives early, `maxFlushTime` will not help.

**Illustrative** snippet only for applications managing Logback's lifecycle themselves:

~~~java
ch.qos.logback.classic.LoggerContext context =
        (ch.qos.logback.classic.LoggerContext)
                org.slf4j.LoggerFactory.getILoggerFactory();
context.stop();
~~~

Do not call `context.stop()` on every request. Do not expect this snippet to run after `Runtime.halt`, SIGKILL, or power loss. In Spring Boot applications or containers that already manage the lifecycle, use the framework-owned lifecycle to avoid duplicate or premature stops.

## 8. With Log4j 2: AsyncAppender, Batch Flush, and Shutdown

Log4j 2 distinguishes between:

- **Async Appender:** an appender with a blocking queue where a worker takes events and forwards them to target appenders.
- **Async Logger:** uses Disruptor/ring buffer and asynchronous processing at the logger level.

Both introduce additional data that may reside in RAM when an incident occurs. Log4j 2 supports flushing the file appender's buffer at the end of an event or batch, but **no configuration makes all async loggers zero-loss when the process is killed**.

Example **log4j2.xml** for Async Appender:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <File name="FILE" fileName="logs/app.log"
              immediateFlush="true">
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

Key points to understand:

- `Async` is declared **after** the `FILE` appender it references to support proper shutdown ordering.
- `blocking=true` prefers blocking producers when the queue is full rather than immediately dropping events under certain queue-full policies; exact behavior depends on configuration and version.
- `shutdownTimeout=5000` limits how long the worker waits to process remaining logs when Async Appender stops. Per the documentation, `0` waits indefinitely in supported mechanisms, but cannot rescue a forcibly killed process.
- `immediateFlush=true` is the buffer-flushing policy of the file appender **after it receives an event**; events still waiting in the async queue have not been processed yet.
- `FileAppender` may flush at the end of a batch even when `immediateFlush=false` in async mode. "Flush to disk" in appender documentation often refers to the output buffer; still distinguish it from `FileChannel.force(...)`/true durable commits.

If the application manages Log4j 2 itself, it can use the shutdown API at the end of the lifecycle:

~~~java
org.apache.logging.log4j.LogManager.shutdown();
~~~

This snippet is for projects that already have the appropriate Log4j 2 API/backend. For framework-managed logging, coordinate with the lifecycle instead of stopping from a request. The configuration and API above do not make shutdown hooks magically run after `halt` or SIGKILL.

## 9. Shutdown Hooks: Useful on Normal Exit, Cannot Save a Crash

Shutdown hooks allow running code before the JVM terminates via the standard shutdown sequence, for example:

~~~java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> {
            // Only takes effect when the JVM actually runs the shutdown sequence.
            // Close the logger through the appropriate framework lifecycle.
        }, "logging-shutdown"));
~~~

This illustrative snippet does not close any logger because each framework has a different API. **Shutdown hooks are not crash insurance**:

- The JVM does not start hooks on `Runtime.halt(...)`.
- SIGKILL, TerminateProcess, and native fatal crashes can bypass hooks.
- Power loss gives the program no chance to run.
- Hooks can run concurrently with no guaranteed order. If one hook stops logging before another hook logs, the final events may be lost.
- Container/orchestrator environments may force-kill after the graceful shutdown deadline.

Therefore, applications should orchestrate lifecycle **outside hooks whenever possible**: stop accepting work, wait for producers, close async logging, and then let the JVM exit. Use hooks as a fallback when no lifecycle manager exists; check to avoid registering duplicate hooks.

When a hook logs an error, provide a minimal diagnostic path such as stderr or a health signal; the logging backend currently being closed may no longer be able to report its own errors.

## 10. Do Console/stdout and Container Logs Need Flushing?

In containers, applications commonly write to stdout/stderr for the runtime or a logging agent to collect. A `System.out.println(...)` line may reach the container's pipe, but other layers follow:

~~~text
JVM PrintStream
    -> stdout/stderr pipe
    -> container runtime
    -> local log file / logging driver
    -> agent / collector
    -> remote storage/index
~~~

Calling `System.out.flush()` only affects the buffer of `PrintStream` and its underlying stream **inside the JVM**. It does not force the container runtime, log driver, network agent, or collector to write durably. If an application uses Logback `AsyncAppender` in front of a console appender, `System.out.flush()` **does not drain the Logback queue either**.

Crash risks:

- Events still in the logging queue.
- Bytes still in the Java stream or pipe when the process is killed.
- Logging driver/agent has not yet processed or sent them in time.
- Collector received them but has not committed; network errors and retries can create duplicate records.

Verify the buffering, retry, ACK, and backpressure policies of each layer in production. If durability beyond the JVM is required, rely on a dedicated store/queue rather than just flushing stdout before exiting.

## 11. Designing Reliability by Log Criticality

Not every event needs the cost of fsync and synchronous waiting.

| Event Type | Usually Appropriate Guarantee Level | Operational Decision |
| --- | --- | --- |
| Diagnostic DEBUG/TRACE | Partial loss on crash is acceptable | Async, batching, sampling, volume control |
| Routine operational INFO | Reduce loss via appender flush and graceful shutdown | Monitor backlog/drops, controlled timeouts |
| Critical ERROR/WARN | May need a priority sink and write-failure alerts | Avoid intentional drops if investigation needs are high |
| Mandatory audit/transaction state changes | Needs an appropriate **durability commitment** before the critical business step | Transactional outbox, durable stream/database, acknowledgment |
| Crash diagnostics | Should have a path outside the async logger where feasible | stderr, prior crash dump/JFR, platform logs |

If the same event is written to both a file and a remote collector, define the actual commitment: "at least one sink receives," "both sinks commit," or "no loss when one replica dies." No single generic configuration automatically achieves all goals.

**Write-ahead log and outbox:** critical data is written alongside the business transaction or to a durable queue with an ACK policy. After a crash, workers can replay; idempotency, event IDs, and deduplication are required. This is a reliable event-storage architecture, not a `flush=true` logger option.

## 12. Measuring the Window of Logs at Risk of Loss When the App Dies

You can estimate the number of events pending in RAM at a given moment:

~~~text
pending ≈ accepted_events - successfully_delivered_events
~~~

If the log ingestion rate is 4,000 events/second and the pipeline lags by about 2 seconds at a given point, there may be roughly **8,000 pending events** (a simple estimate when the backlog roughly corresponds to 2 seconds of traffic). You cannot use this number to claim exactly 8,000 events will be lost, because some have already been processed/flushed by the sink or reside in layers outside the JVM.

Metrics worth observing:

- Queue depth/ring buffer occupancy; enqueue and consume rates.
- Number of events dropped/discarded when the queue is full; overflow rate.
- Appender I/O errors, failed deliveries, and retries.
- Flush/drain/shutdown wait times; timeouts and remaining backlog.
- Latency from event creation timestamp to collector timestamp.
- Disk usage, fsync/force errors, network errors, quotas.
- Missing record rate in events with sequential IDs or test markers.

When a system lacks a counter for logs **received by the sink**, relying solely on `queue.size()==0` leads to false conclusions: the worker may have dequeued an event and still be writing/flushing it. You need a post-processing completion milestone and a final check at the sink.

## 13. Shutdown Procedure to Reduce Log Loss

~~~text
SIGTERM / shutdown request
     │
     ▼
Stop accepting new requests, jobs, or messages
     │
     ▼
Wait for producers to finish (clear deadline)
     │
     ▼
Stop services still generating logs
     │
     ▼
Stop logging context / drain async queue
     │
     ▼
Flush & close target appender / handler
     │
     ▼
Signal process completion and exit JVM
~~~

This procedure only works while **the system still allows the process to run**. If the total graceful shutdown window is 30 seconds but business tasks take 29 seconds, the logger may have only 1 second left to drain; allocate time budgets across the entire exit path.

Practical decisions:

1. Set the drain timeout smaller than the overall process shutdown deadline.
2. If log volume is high, increase sink throughput and bound the backlog before relying on long timeouts.
3. Do not call `LoggerContext.stop()` or `LogManager.shutdown()` while producers are still writing critical logs.
4. Do not try to write a large burst of diagnostic logs inside a shutdown hook: it can fill the queue further and prolong shutdown.
5. Record failure metrics/status on an independent channel if the logging backend is no longer available.
6. Distinguish "queue drained" from "durable" in operational reports.

## 14. How to Test Crashes and Flushing?

### 14.1. Testing by Termination Type

| Test | Purpose | What It Does Not Prove |
| --- | --- | --- |
| Normal exit | Lifecycle close/flush works, files/logs are complete | Forced kill or power loss |
| `System.exit(...)` | Whether shutdown hooks/lifecycle run | `Runtime.halt`/SIGKILL |
| `Runtime.halt(...)` in a **child process** | Data still in JVM buffers is lost when the child stops | Durability against OS crash |
| Force-kill a test process | Evaluates loss of unprocessed events and collector logs | Power loss or storage corruption |
| Stopping before the async queue empties | Measures backlog/flush timeout/drops | Durability all the way to the final destination |
| Simulated I/O/network failures | Reaction when the sink cannot write | All real infrastructure failures |
| Isolated machine/VM/storage crash test | Tests fsync policy and recovery | Cannot be generalized to all hardware/filesystems |

Do not use crash injection on a production JVM or during real business processing. Tests should generate identifiable data using **event IDs/sequences**, create a dedicated sink, inspect logs after restart, and reconcile against the number of accepted events.

### 14.2. Proving at the Right Level

- **Line present in file after JVM halt:** proves bytes escaped certain JVM buffers and the OS can still read them.
- **Successful `force(true)` call on a local file:** per the JDK contract, a stronger request at the local storage device level.
- **Sent over socket/HTTP:** does not by default mean a remote durable commit; a proper ACK is required.
- **Properly closed logger context:** proves the graceful stop path was executed; proves nothing about forced kills.

For end-to-end tests, additionally verify the number of events **actually arriving** at the logging system, ordering (if contracted), duplicate count, and gaps; avoid checking only file existence or exit codes.

## 15. Common Pitfalls

| Pitfall | Why It Is Wrong | Correct Practice |
| --- | --- | --- |
| "On crash, we'll flush in `finally`" | `finally` does not run if the JVM is forcibly terminated | Use periodic flushing/sink policies; do not treat `finally` as a crash hook |
| Assuming shutdown hooks always run | `halt`, SIGKILL, native crashes, and power loss do not guarantee hooks | Treat hooks only as a graceful-shutdown aid |
| Calling `System.out.flush()` to drain Logback `AsyncAppender` | Flushes the wrong layer; the queue may still hold events | Stop/drain the proper logging context |
| `queue.isEmpty()` means logs are saved | Consumer may still be processing a dequeued event | Wait for confirmation after appender flush or durable ACK |
| `immediateFlush=true` means power-loss protection | Flushing stream buffers is not fsync | Use appropriate storage commitments |
| Calling `force(true)` before `writer.flush()` | Bytes still in the writer have not entered `FileChannel` | Flush the Java chain first, then force the associated channel |
| `FileChannel.force(true)` is an end-to-end guarantee | Does not cover async queues, remote collectors, or non-local storage | Define the scope of the guarantee |
| Increasing `queueSize` indefinitely to be "safe" | Increases RAM backlog and the number of events that can be lost on crash | Bounded queues, backpressure, throughput |
| Setting `neverBlock=true` while requiring zero loss | A full queue can drop events | Design drop/block policies according to requirements |
| Not monitoring `maxFlushTime` timeouts | Workers may still have unprocessed logs when the app stops | Measure pending logs, speed up the sink, and budget time |
| Running `Runtime.halt` tests directly in the main test process | Stops the test runner itself, yielding no results | Use an isolated child process as shown in the example |
| Testing only JVM halt and concluding power-loss resilience | OS page cache still exists after a child JVM dies | Needs separate OS/storage tests and fsync contracts |
| Writing mandatory audit logs to an async file logger and returning success | Creates a log-loss window on crash | Use durable transactions/outbox/ACK |

## 16. Pre-Deployment Checklist

1. Define the **maximum acceptable log loss** for each event type: diagnostic, operational, security, and audit.
2. Identify the actual logging backend: JUL, Logback, Log4j 2, synchronous or async; do not infer solely from facade dependencies.
3. Map the event path from caller → queue → appender → file/stdout/network → collector.
4. Distinguish buffer flush, queue drain, file force/fsync, and durable acknowledgment; document where each contract applies.
5. If using async, configure queue size, drop/block policies, and stop deadlines to match volume and sink speed.
6. Ensure graceful shutdown stops producers first and only then stops the logger; check container timeouts.
7. Enable metrics for queue backlog, dropped events, sink errors, drain duration, and missing events.
8. Test normal exit, `System.exit`, `Runtime.halt` in a child process, and forced termination in a dedicated environment.
9. If durability across OS/power crashes is needed, choose storage/queues with appropriate commitments; do not treat `flush()` as sufficient.
10. Reconcile logs after restart by event ID, including missing/duplicate records; evaluate idempotency requirements for audit systems.

## 17. Self-Check Questions

1. When the JVM dies before `BufferedWriter.flush()`, why might a log line not appear even though `write()` returned?
2. Why does a file still being readable after `Runtime.halt(...)` **not** prove data will survive a power loss?
3. How does `writer.flush()` differ from `file.getChannel().force(true)`? Why does the order of the two calls matter?
4. If an async queue is not yet empty but `FileAppender.immediateFlush=true`, which events can still be lost?
5. How do `System.exit()` and `Runtime.halt()` differ regarding shutdown hooks?
6. Why cannot `AsyncAppender.maxFlushTime=5000` save an application hit by an immediate SIGKILL?
7. In Log4j 2, what is the difference between Async Logger and Async Appender in terms of where events are temporarily held?
8. Why does `System.out.flush()` not guarantee that a container's log collector has committed the log?
9. Why do some audit events require a transactional outbox instead of just writing to an async log file?
10. When crash testing, how should you distinguish created, enqueued, file-written, and durably ACKed events?

**Answer hints:** (1) data remains in the heap buffer; (2) the OS cache still exists after only a child JVM dies; (3) flush Java buffers first, force to storage second; (4) events still in the queue; (5) exit initiates shutdown, halt skips hooks; (6) the worker gets no chance to finish; (7) appender queue vs. logger ring buffer; (8) multiple layers sit behind the JVM; (9) durable commit and replay are required; (10) measure at each boundary rather than using a single "flushed" boolean.

## 18. Official Documentation

- [Java SE 17 — Runtime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `exit`, `halt`, shutdown hooks, and limits when a process is forcibly terminated.
- [Java SE 17 — Writer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Writer.html): `flush()` pushes Java buffers to the OS but does not guarantee writing to a physical device.
- [Java SE 17 — BufferedWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html): buffering and `flush()`.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `force(boolean)`, local guarantees, and limits for non-local files.
- [Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): JUL `flush()` and `close()`.
- [Logback — File/Console appenders](https://logback.qos.ch/manual/appenders-console-file.html): `immediateFlush` and risk of buffer loss on abrupt exit.
- [Logback — AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html): queue, `discardingThreshold`, `maxFlushTime`, and stop.
- [Apache Log4j 2 — Async loggers](https://logging.apache.org/log4j/2.x/manual/async.html): async benefits/trade-offs and notes on auditing.
- [Apache Log4j 2 — Async Appender](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html): queue and shutdown.
- [Apache Log4j 2 — Appenders](https://logging.apache.org/log4j/2.x/manual/appenders.html): `immediateFlush` and flushing buffers at the end of an event/batch.
