# Output Synchronization in Java Console Logging

## 1. Concept and Goals

**Output synchronization** in **Console logging** is the coordination of threads that write logs to the console together so that **the content of each record is not unexpectedly interleaved**. When a Java application runs multiple concurrent tasks, multiple threads may call **System.out.print/println**, **System.err.print/println**, **Logger.info()**, or write through a logging framework's **ConsoleHandler/ConsoleAppender**.

Example of two expected events:

~~~text
INFO | worker=A | event=task.started
WARNING | worker=B | event=task.retry
~~~

If a single event is split into multiple separate print calls, the result *may* become unreadable:

~~~text
INFO | worker=WARNING | worker=B | event=task.retry
A | event=task.started
~~~

This is an **illustration of possible interleaving**, not stdout behavior that is guaranteed to happen on every run. The cause is that multiple threads are scheduled independently by the CPU and can write between each other's operations.

To design console logging properly, you must distinguish:

1. **Per-record atomicity:** each log message is emitted intact, without being mixed with parts of another event.
2. **Mutual exclusion:** at any given time, only one party is allowed to execute the protected write operation.
3. **Ordering:** which event is written before which event. A lock by itself **does not dictate** the order in which threads acquire the lock.
4. **Flushing:** pushing bytes in a buffer to the underlying output layer. Flushing is **not synonymous** with atomicity or durability.
5. **Durability:** whether the record survives a crash, disconnection, or collector failure.

**Synchronized, ordered, and flushed are three different properties.** A system with intact log lines but interleaved ordering is completely valid when requests run concurrently.

## 2. stdout and stderr Are Two Different Streams

Java has two standard output streams:

| Component | Common Destination | Characteristics |
| --- | --- | --- |
| **System.out** | stdout | Program results and normal output |
| **System.err** | stderr | Diagnostics and errors |
| **java.util.logging.ConsoleHandler** | **System.err** | JUL Handler, defaults to SimpleFormatter |
| **Log4j 2 Console Appender** | SYSTEM_OUT or SYSTEM_ERR | Selected via target in log4j2.xml |
| **Logback ConsoleAppender** | System.out or System.err | Selected via target in logback.xml |
| **StreamHandler(System.out, formatter)** | stdout | JUL Handler with a chosen OutputStream |

Both stdout and stderr can appear in **the same terminal**, but the OS, IDE, and container runtime may route them to **two different pipes or collectors**. Shared screen display **does not prove they share the same lock or the same ordering**.

Example:

~~~java
System.out.println("INFO | event=started");
System.err.println("WARNING | event=retry");
~~~

Each statement is an operation on its respective stream. If multiple threads are working concurrently and an external tool merges the two streams, the displayed order may differ from expectations. **You cannot lock only System.out and assume System.err is also protected.**

**Recommendation:** choose a consistent console pipeline/destination for any group of logs you need to compare, and add timestamps and correlation IDs. Do not treat the order of merged lines from stdout/stderr as a total business order.

## 3. Why Does Log Interleaving Happen?

Common scenarios:

- **One record consists of multiple print calls:** one thread prints a prefix, and another thread inserts a message before the first thread prints the suffix.
- **Multi-line formatter:** a stack trace or block of information is emitted across multiple calls, and another thread can interleave in between.
- **Multiple independent writers:** code uses System.out while a backend uses a different ConsoleAppender or StreamHandler.
- **Two backends writing to the console:** each backend has its own synchronization mechanism and does not automatically coordinate on a shared lock.
- **Multiple processes:** two JVMs or other tools write to the same terminal/pipe.
- **stdout and stderr are merged:** a collector/IDE may add buffering and alter the observed order.
- **A log event carries mutable data:** an asynchronous writer formats late, after the data has already been modified by another thread.
- **Missing context identifiers:** lines are completely intact, but readers mistake the ordering of requests A and B for a synchronization bug.

Example of risky code:

~~~java
System.out.print("INFO | worker=" + workerName);
System.out.println(" | event=" + eventName);
~~~

The above is a **snippet**, assuming the two variables already exist. Another thread can run between the two calls.

A simpler, better approach:

~~~java
String line = "INFO | worker=" + workerName
        + " | event=" + eventName;
System.out.println(line);
~~~

Building the **entire line** and calling println once reduces the risk of interleaving when sharing a single PrintStream. However, it **does not order** lines between threads A and B, and does not protect against other writers that do not share the same mechanism.

## 4. How Thread-Safe Is PrintStream.println()?

In Java 17, System.out and System.err are instances of **java.io.PrintStream**. Common JDK implementations synchronize many operations when writing through the **same PrintStream**; therefore, a single **println(String)** call for the whole line is usually a consistent unit of printing relative to other calls on that same object.

Limits you must understand accurately:

1. **A println call does not combine multiple calls into a single transaction.** Printing a header, body, and newline with three statements still leaves points where another thread can interleave.
2. **There is no total order between two threads** just because both call println; which thread executes first depends on scheduling.
3. **System.out and System.err do not share a mandatory monitor.**
4. **System.setOut(...)** can replace the PrintStream. A lock on the old PrintStream does not automatically protect the new stream.
5. Writers or libraries using their **own OutputStream wrapper** do not necessarily share the same lock.
6. A multi-line event from a Formatter does not automatically have the same atomic boundary as a single println.
7. Multiple **JVMs/processes** do not share Java monitor objects.
8. A collector that receives bytes and then forwards, parses, and merges them can alter the displayed order.
9. **PrintStream** normally does not throw IOException directly on write errors, but instead tracks an error state inspectable via **checkError()**. This is not a log-persistence guarantee.

**Do not conclude:** “println is thread-safe, so all console logging is always ordered, lossless, and impossible to mix.” You must define the *unit to protect*, the *writer scope*, and the *ordering conditions*.

## 5. Mutual Exclusion Does Not Automatically Create Ordering

**Mutual exclusion** answers “can two threads write inside the protected region at the same time?” **Ordering** answers “which event must happen before which event?”

For example, with a lock:

~~~java
synchronized (CONSOLE_LOCK) {
    System.out.println(message);
}
~~~

This is a snippet assuming CONSOLE_LOCK and message exist. Two threads using the **same lock** will not be inside this region simultaneously, but thread B can still acquire the lock before thread A. Even if thread A is created first, **starting first does not mean printing first**.

When business logic requires:

~~~text
event=task.started
event=task.completed
~~~

there must be an appropriate processing relationship: Thread B waits on a **CountDownLatch**, **Future**, queue, or completion signal from step A before emitting event B. If tasks A and B are truly independent, interleaving them is completely valid; use requestId and workerId to distinguish them.

| Goal | Appropriate Mechanism |
| --- | --- |
| No character interleaving within a single message | Build the complete message; a thread-safe writer/Printer |
| No line interleaving within a block | Same lock for the whole block or queue the event as a whole |
| Event B is only created after A finishes | Latch/Future/barrier/business-level coordination |
| Preserve order of enqueued events | Single queue and single consumer |
| Identify which request an event belongs to | requestId/jobId/traceId |
| Data has left the buffer | flush()/backend policy |
| No log loss at the collector | Storage design, retries, shutdown, and monitoring |

A **lock is not a clock**, a **queue is not a transaction log**, and **flush is not fsync**.

## 6. Compact Option: One println per Event

In a CLI or learning example, the appropriate approach is usually:

~~~java
String line = "INFO | requestId=" + requestId
        + " | event=order.accepted orderId=" + orderId;
System.out.println(line);
~~~

This is a snippet requiring the variables to be declared. If the thread count is low and all use System.out, it is simple and leaves little opportunity for fragments of a single line to interleave.

**Avoid:**

~~~java
System.out.print("INFO | requestId=");
System.out.print(requestId);
System.out.println(" | event=order.accepted");
~~~

The three statements are not protected as a single unit. Another thread can still insert output between them.

Limitations of the “single println” approach:

- Does not help keep a **stack trace** formatted across multiple lines together.
- Lacks log levels/filtering or output selection needed in real applications.
- Does not address logs from **System.err**, multiple backends, or multiple processes.
- Does not establish a deterministic order between threads A/B.
- Does not automatically add timestamps, logger names, requestId, or access controls.

As an application grows, use a logging framework instead of scattering System.out.println across every class. That enables log volume control, level selection, Formatter/Encoder configuration, and centralized output destinations.

## 7. Using synchronized with a Shared Lock

When **it is mandatory to write multiple lines as a single unit** controlled by your own application code, use a clearly scoped lock:

~~~java
private static final Object OUTPUT_LOCK = new Object();

static void printBlock(String title, String detail) {
    synchronized (OUTPUT_LOCK) {
        System.out.println(title);
        System.out.println(detail);
    }
}
~~~

This is a snippet placed inside a Java class, not a standalone program.

Two threads calling **printBlock** both acquire OUTPUT_LOCK before printing. Thus, they will not interleave calls to **printBlock itself** in the middle of each other's blocks.

However, there are limitations:

- **All parties involved must use the same OUTPUT_LOCK**. Another place calling System.out.println directly can still print between the two lines of the block.
- This lock does not automatically protect stderr or other Writers.
- Java locks do not synchronize across different processes.
- If System.out has been replaced, you still have to evaluate the entire output path.
- Do not hold the lock during **heavy computation, network calls, or unnecessary external I/O**.
- Avoid calling Logger inside a lock-held region if the backend has its own lock and could create a **lock-ordering deadlock**.
- Under high log traffic, a shared lock can become a **contention hotspot**.

Another option is **synchronized(System.out)**, but that depends on the current stream object and whether other parties use the same monitor. An **application-owned lock** expresses the protection scope more clearly.

**Rule:** if you do not control all writers, synchronized inside one class alone is not enough. Unify the logging pipeline or pick a single writer.

## 8. Single Console Writer with BlockingQueue

With multiple producers, an architecture with **multiple threads producing events and one thread writing to the console** centralizes synchronization:

~~~text
Producer A ---+
              |
Producer B ---+----> BlockingQueue<Event>
              |               |
Producer C ---+               v
                       console-writer
                             |
                             v
                        System.out
~~~

**Advantages:**

- Each event is built completely before being placed in the queue.
- Producers do not contend directly for console printing rights.
- A single consumer can process events sequentially and format them consistently.
- You can use **ArrayBlockingQueue** to bound memory usage.
- Easy to attach metrics for queue depth, output latency, and rejected event counts.
- Stopping the writer can be managed centrally.

**Disadvantages:**

- **Full queue** requires backpressure or an explicit discard policy.
- **put()** can block producers when the consumer cannot keep up.
- **offer()** can return false; code must not ignore the result if dropping events is unacceptable.
- Process termination before the queue drains can lose logs.
- Producer threads can be interrupted or fail, requiring shutdown handling and completion signals.
- Ordering between two producers is the **actual enqueue order**, not thread start order.
- A single writer still does not control third-party libraries calling System.err/println outside the queue.

In production, prefer a **built-in Async Appender/AsyncLogger** from an established backend rather than building custom logging infrastructure, unless you have a very specific reason.

## 9. Standalone Java 17+ Program: Queue and Writer Thread

This example uses two producer threads **A** and **B**, one writer thread, a bounded queue, and two **CountDownLatch** instances. The latches make the order of the three events **deterministic for the test**; the queue ensures each event is printed intact by a single writer.

Save as **ConsoleOutputSyncDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public final class ConsoleOutputSyncDemo {
    private record Event(String message, boolean stop) {}

    private static final BlockingQueue<Event> EVENTS =
            new ArrayBlockingQueue<>(8);

    private static final CountDownLatch FIRST =
            new CountDownLatch(1);
    private static final CountDownLatch SECOND =
            new CountDownLatch(1);

    public static void main(String[] args) throws InterruptedException {
        Thread writer = new Thread(() -> {
            try {
                while (true) {
                    Event event = EVENTS.take();
                    if (event.stop()) {
                        return;
                    }
                    System.out.println(event.message());
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "console-writer");

        Thread producerA = new Thread(() -> {
            try {
                EVENTS.put(new Event(
                        "INFO | worker=A | event=task.started", false));
                FIRST.countDown();

                SECOND.await();
                EVENTS.put(new Event(
                        "INFO | worker=A | event=task.completed", false));
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "producer-A");

        Thread producerB = new Thread(() -> {
            try {
                FIRST.await();
                EVENTS.put(new Event(
                        "WARNING | worker=B | event=task.retry", false));
                SECOND.countDown();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "producer-B");

        writer.start();
        producerA.start();
        producerB.start();

        producerA.join();
        producerB.join();
        EVENTS.put(new Event("", true));
        writer.join();

        System.out.println("records=3");
    }
}
~~~

### Compile and Run

With JDK 17 or newer:

~~~bash
javac ConsoleOutputSyncDemo.java
java ConsoleOutputSyncDemo
~~~

**Exact stdout under normal execution:**

~~~text
INFO | worker=A | event=task.started
WARNING | worker=B | event=task.retry
INFO | worker=A | event=task.completed
records=3
~~~

The program does not intentionally print anything to stderr. The INFO/WARNING labels are **log-simulating message strings**, not actual JUL Levels. The program requires only the plain JDK, with no Maven or external dependencies.

### Result Analysis

1. Producer A puts **task.started** into the queue before calling **FIRST.countDown()**.
2. Producer B proceeds only after **FIRST.await()**, so **task.retry** is enqueued after task.started.
3. Producer B calls **SECOND.countDown()** after enqueueing task.retry.
4. Producer A waits on **SECOND.await()**, so it enqueues task.completed only after task.retry.
5. **ArrayBlockingQueue** preserves the order of inserted elements; the writer takes each event and prints it in one call.
6. Main calls **join()** on both producers to know they have finished before enqueueing the stop event.
7. The writer exits only when it sees an event with **stop=true**. Main joins the writer, then prints records=3.
8. Because the ordering boundaries are enforced by latches, no matter how the scheduler interleaves A/B, the three events are always enqueued in that order.
9. If you remove the latches, events from the producers may reach the queue in a different order; the writer still prints each event intact.
10. The queue has capacity **8**, preventing unbounded RAM growth. When full, **put() blocks**; this is backpressure, which must be managed in real applications.

**Demo limitations:** if a thread is interrupted or the writer encounters an unexpected error, the catch block restores the interrupt flag but does not implement a full error-reporting/signaling protocol for the remaining threads. Production code must handle failures, timeouts, finally blocks, monitoring, and shutdown. **Do not copy a learning example as a complete production logging backend.**

## 10. Comparing the Strategies

| Option | Atomicity Within Cooperating Scope | Ordering | Complexity | When Appropriate |
| --- | --- | --- | --- | --- |
| Single println for the whole message | Call unit on the same JDK PrintStream | Not fixed across threads | Low | CLIs, small examples |
| synchronized on a shared lock | Entire block if all writers use the same lock | By lock acquisition order, not business order | Medium | Self-managed code with multiple print calls |
| Single writer thread + queue | Each queued event processed sequentially by writer | By enqueue order | Higher | Multiple producers/async output |
| Standard Console Appender/Handler | Depends on supported implementation/backend | Does not create multi-thread total order | Centralized config | Most real-world applications |

**Do not create a separate queue per module** and have multiple writers write to System.out: that brings back the problem of multiple independent write targets. A single backend may intentionally provide multiple Appenders, but each target must be understood and tested.

## 11. Console Logging with java.util.logging

**java.util.logging.Logger** has an API designed by Java SE to be safe to call from multiple threads. This allows multiple threads to use the same Logger without wrapping every info()/warning() call in **synchronized**.

**ConsoleHandler** in JUL extends StreamHandler and outputs LogRecords to **System.err**. It checks the level, Filter, and uses a Formatter when publishing. **StreamHandler** provides flush/close operations for the configured OutputStream.

Example **logging.properties** file:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
~~~

This is a sample JUL configuration for an application; it is not the configuration for ConsoleOutputSyncDemo, since that demo uses PrintStream/BlockingQueue directly.

In a JUL application, you can call:

~~~java
logger.log(Level.WARNING,
        "event=inventory.retry attempt={0}", 2);
~~~

This is a snippet, assuming logger and the Level import are already present.

**What a thread-safe Logger does NOT mean:**

- Threads emit logs in a fixed global order.
- A custom Formatter with mutable state is automatically thread-safe.
- Multi-line stack traces are automatically merged into one event by a collector.
- Two Handlers writing to stderr share an application-defined lock.
- A log has reached durable storage as soon as logger.log() returns.

**Avoid attaching duplicate ConsoleHandlers:** a child Logger with its own Handler and a parent Logger that also has a Handler can output the same LogRecord twice when **useParentHandlers=true**. Check the logger hierarchy before suspecting an interleaving bug.

## 12. Custom Handlers or Formatters Must Be Designed Thread-Safe

When writing a custom **Handler**, **Appender**, or **Formatter** with state, determine where synchronization belongs and avoid deadlocks.

A short illustrative Formatter:

~~~java
Formatter compact = new Formatter() {
    @Override
    public String format(LogRecord record) {
        return record.getLevel().getName()
                + " | " + formatMessage(record)
                + System.lineSeparator();
    }
};
~~~

This is a snippet importing java.util.logging.Formatter and LogRecord; compact is a Formatter variable, **not a standalone runnable program**. It does not print timestamps or Throwables, so it is not suitable as-is for systems that need stack traces.

Checklist for custom components:

1. If holding a **counter, cache, StringBuilder, or mutable buffer**, is there protection when multiple threads call it?
2. Does it format the **entire event** into one buffer before sending it to the stream?
3. Does it respect **isLoggable(record)**, levels, Filter, and the formatter contract?
4. If printing multiple lines, does it use the backend's proper output mechanism?
5. Could recursive logging inside a Handler/Filter cause a logging loop?
6. Are locks acquired in a consistent order to avoid deadlocks?
7. Is the **flush(), close(), shutdown** lifecycle managed properly?
8. Does it avoid closing **System.out/System.err** when the Handler does not own those streams?
9. Is it tested with multiple threads and multi-line exceptions?
10. Are output errors monitored rather than ignored?

Not every logging component shares a single JVM-wide lock. It is best to avoid replacing backend implementations if a standard Handler/Appender already meets your requirements.

## 13. Log4j 2 Console Appender

Log4j Core provides a **Console Appender**. Example **log4j2.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="STDOUT" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%d{ISO8601} %-5level [%t] %logger - %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="STDOUT"/>
        </Root>
    </Loggers>
</Configuration>
~~~

- **target=SYSTEM_OUT** selects stdout; **SYSTEM_ERR** can be used if needed.
- **PatternLayout** formats timestamp, level, thread name, logger name, and message.
- **Root level=info** filters out DEBUG/TRACE levels.
- This is a Log4j 2 Logger/Appender configuration, **not JUL ConsoleHandler**.
- Events from multiple threads are accepted by the backend, but can still appear in different orders across runs.
- If using AsyncLogger/AsyncAppender, understand Log4j 2's queuing, flushing, and shutdown behavior.

**Do not wrap every log call in synchronized in business code** if the backend already manages writing and locking. Your lock will not synchronize other Appenders and can introduce contention.

## 14. Logback Console Appender

Applications using **SLF4J + Logback** can declare **logback.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

Characteristics:

- ConsoleAppender receives a LogEvent and writes it to the selected stream.
- **Encoder** performs formatting; do not use Log4j 2's **PatternLayout** syntax for Logback.
- Thanks to SLF4J's unified API, multiple modules can share the same configuration.
- If the application has multiple SLF4J providers, resolve dependency conflicts first.
- **MDC** and thread names make multi-threaded logs easier to read, but the pattern/encoder must be configured accordingly.

**SLF4J is a facade**, while Logback/Log4j 2 are the backends responsible for executing output. Calling LoggerFactory alone is not enough to have a console writer if no provider is present at runtime.

## 15. Synchronous and Asynchronous Logging

**Synchronous logging** typically has the calling thread participate in the Appender's formatting/writing path and may wait for output. **Asynchronous logging** places events into a queue/ring buffer and lets a worker thread process them later.

| Aspect | Synchronous | Asynchronous |
| --- | --- | --- |
| Cost on business thread | Can be affected by console I/O | Usually smaller while queue has space |
| Where I/O happens | Backend's synchronous path | Dedicated worker |
| Queue | May not be needed | Required and must be managed |
| When console is slow | Calling thread may slow down | Queue grows, then blocks/drops/falls back |
| Shutdown | Fewer drain steps | Must drain and stop worker |
| Output errors | Closer to calling thread | May be reported late |
| Ordering across producers | Follows actual scheduling | Follows enqueue order and backend handling |
| Zero log loss guarantee | Not by default | Not by default |

Log4j 2 has **AsyncLogger** and **AsyncAppender**, while Logback has **AsyncAppender**. They have their own queue handling, log levels, and error policies; do not assume one backend's policy applies to another.

**Full queue:** may block producers, switch paths, or drop events according to policy. If logs are security-, audit-, or critical-transaction-related, explicitly determine whether discarding is permitted.

**Mutable arguments:** a LogEvent may be formatted after the logging method returns. Do not mutate objects attached as messages/context without a snapshot or a thread-safety contract.

**A worker writer serializes its own output path**, which does not mean it preserves the causal order of the entire distributed system.

## 16. Flush Does Not Mean Synchronized

A common mistake is adding **System.out.flush()** to prevent logs from mixing:

~~~java
System.out.print("INFO | ");
System.out.flush();
System.out.println("event=started");
~~~

This snippet illustrates a **misconception**. Flush only requests pushing buffered data down to the underlying layer; another thread can still write between print and println.

Distinguish:

- **Atomicity:** whether a record can be interleaved in the middle.
- **Flushing:** whether data is still in a Java/backend buffer or has been pushed to the underlying stream.
- **Ordering:** which record is enqueued, formatted, or written first.
- **Durability:** whether the collector/destination retains the data after a crash.

A PrintStream may enable autoFlush under certain conditions such as println, but **do not infer that all terminals, pipes, collectors, and log stores have synced to disk**.

JUL **ConsoleHandler** flushes according to its own mechanism. JUL **StreamHandler** has its own **flush()**, and **close()** may close the OutputStream, so be careful when passing System.out to a custom StreamHandler.

A logger may write properly and flush successfully, yet the log collector still loses records due to a closed pipe, an overloaded collector queue, or a lost connection. If durability is required, monitor the pipeline and design appropriate retries/storage.

## 17. Multi-Line Stack Traces and Output Synchronization

When an exception occurs, a log may span multiple lines:

~~~text
ERROR | event=order.persist.failed requestId=req-42
java.lang.IllegalStateException: storage unavailable
    at example.OrderService.save(OrderService.java:42)
Caused by: java.io.IOException: connection reset
    at example.StorageClient.write(StorageClient.java:27)
~~~

This is an **illustrative stack trace**, not the output of a real program run. If a custom Formatter prints each frame using separate unsynchronized operations, another thread can interleave between frames.

**Best practices:**

1. Pass **Throwable** via the proper API, such as JUL **logger.log(Level.SEVERE, message, ex)**, or SLF4J/Log4j 2 **LOG.error("event=order.failed id={}", id, ex)**.
2. Let a Formatter/Encoder with exception support produce a single consistent event.
3. If the collector treats each line as a separate log event, configure **multiline parsing** or structured exception fields.
4. If JSON contains newlines, **escape** them properly so they do not create malformed multiple records.
5. Avoid **logging the same Throwable at every layer and rethrowing**, which counts one incident as multiple errors.
6. Test concurrent exceptions and verify the collector does not mix the cause chains of two requests.
7. Include requestId/thread/service on each event to make investigation easier.

**Output synchronization inside the JVM** and **stack trace reassembly at the collector** are two separate problems. Do not use what looks right in a terminal to assume the log platform's parser will ingest it properly.

## 18. Log Ordering and Correlation Context

A multi-request scenario:

~~~text
INFO | worker=A | requestId=req-10 | event=order.started
INFO | worker=B | requestId=req-11 | event=order.started
INFO | worker=B | requestId=req-11 | event=order.completed
INFO | worker=A | requestId=req-10 | event=order.completed
~~~

The four lines above **are not corrupted/mixed**, yet they interleave according to independent processing times. This is normal concurrency behavior.

Useful fields:

| Field | Purpose |
| --- | --- |
| timestamp | Approximate time of the event |
| level | INFO/WARN/ERROR or backend level system |
| service/instance | Source in a multi-process system |
| thread | Thread that generated the event |
| requestId/jobId | Correlates lines belonging to the same business flow |
| traceId/spanId | Links to distributed tracing when integrated |
| event | Stable action name |
| outcome/reasonCode | Business outcome or reason |
| sequence | Order within a well-defined scope |

**Timestamps alone do not establish total order** across multiple machines due to clock skew, delayed formatting/queuing, and ingestion delays. Sequence numbers are also meaningful only within the scope that assigns them; per-process sequences do not automatically create a system-wide order.

In frameworks using SLF4J, **MDC** can attach requestId:

~~~java
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("requestId", requestId)) {
    LOG.info("event=order.accepted orderId={}", orderId);
}
~~~

This is a snippet, assuming variables already exist. MDC is typically tied to thread-local context and **does not automatically propagate across thread pools, CompletableFutures, or services**. When using thread pools, propagate context explicitly and clean it up after the request so that request B's logs do not carry request A's ID.

**Output synchronization** keeps lines intact; **correlation** identifies relationships between lines. Both are necessary in concurrent systems.

## 19. When Multiple Processes/Containers Log Together

A Java **synchronized lock** applies only within **a single JVM**. It cannot enforce ordering across two JVMs, two containers, or separate processes.

In real environments:

- Multiple processes may write to the same terminal or pipe; write atomicity depends on the OS and how libraries actually emit bytes.
- With POSIX pipes, **PIPE_BUF** bounds certain atomic write guarantees, but does not prove a Java LogEvent always maps to a single system call.
- stdout and stderr are often collected separately by a collector and merged by timestamp or ingestion time.
- A container can be killed before an async queue drains or the collector receives everything.
- Excessively long log lines can be split or truncated by platform limits.
- A service with multiple replicas does not share a cluster-wide queue/writer.
- Writing the same event to both a file and the console when the collector ingests both can produce duplicate events.
- Global ordering is not guaranteed simply because each JVM is synchronized internally.

**Do not use console text ordering as a business coordination protocol.** If you require “A must commit before B,” use transactions, queues, system-level locks/coordination, or a reliable event mechanism with sequences/offsets, and log for observability.

## 20. Performance, Lock Contention, and Security

Console logging can become a bottleneck if thousands of threads write concurrently:

- A shared lock can force business threads to wait on each other.
- A slow console/collector lengthens lock hold times.
- Overly verbose logging in loops increases I/O, object allocation, and GC pressure.
- An async queue reduces short-term latency but will fill up if the event rate continuously exceeds the write rate.
- An unbounded queue can exhaust RAM; use a bounded queue and an explicit overflow policy.
- Large stack traces and structured JSON increase formatting and ingestion costs.
- Non-thread-safe custom Filters/Formatters can cause hard-to-reproduce data corruption.
- Creating too many per-request Loggers/Appenders/Handlers can cause contention and duplicates.

Beyond concurrency, consider security:

1. **Never log tokens, passwords, cookies, private keys, card data**, or unnecessary user payloads.
2. Input containing newlines/control characters can cause **log injection**; use proper escaping and formatters.
3. Console logs are usually collected by the platform and may be retained longer than expected.
4. Manage **retention**, access permissions, backups, and policy-compliant deletion.
5. Do not use logs as a dumping ground for every debug detail when aggregated metrics suffice.
6. Use stable eventNames and appropriate context IDs instead of printing entire objects.
7. For audit requirements, do not assume an async queue or console output provides the required durability and integrity.

**Benchmark on a realistic system** before switching all synchronous loggers to async. Log volume, load levels, queue limits, p95/p99 latency, and collector lag matter more than assuming “async is always faster.”

## 21. Testing Output Synchronization

A concurrency test should not assert guarantees that do not exist.

**Testing record integrity:**

- Have each thread emit a distinct eventId or workerId/sequence.
- Use multiple threads and a known number of events.
- Verify each line contains the prefix/body of **a single event**.
- Verify no events are missing or duplicated under conditions where the policy does not intentionally discard.
- Test Vietnamese Unicode, long messages, multi-line exceptions, and output with control characters.
- Test scenarios with multiple Loggers/Handlers/Appenders.

**Testing ordering:**

- Without happens-before, assert only the **set of events** or per-producer order where guaranteed, not total order across threads A/B.
- If deterministic order is required, use **CountDownLatch**, Future, join, or a sequence protocol.
- Do not use **Thread.sleep(...)** as the primary way to enforce ordering; it does not guarantee predictable scheduler execution.
- With async logging, wait for the backend to **shutdown/drain** via its proper API before comparing output.

**Testing stdout and stderr:**

- Capture the two streams separately to verify where events are actually emitted.
- Be careful with **System.setOut/System.setErr** in parallel unit tests because they are JVM-global state.
- Verify behavior when a collector merges streams, as it can make observed order differ from code call order.
- With JUL, remember ConsoleHandler normally writes to stderr; with Log4j/Logback, verify the configured target.

**Testing failure/backpressure:**

- Test full queues, stopped consumers, interrupted threads, and shutdown.
- Check metrics for dropped logs or output errors.
- Measure throughput/latency when the console is slow, rather than only checking correct logs under low traffic.

The ConsoleOutputSyncDemo in section 9 has deterministic expected stdout because the latches establish ordering relationships. That **does not prove** every concurrent program has a fixed order.

## 22. Common Issues

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Two messages stuck on one line | Message built with multiple print calls | Build complete message, single writer or shared lock |
| Thread A's prefix, thread B's suffix | Two write operations interleaved | Lock entire block or use a queue |
| Lines intact but order changes | Different scheduling | Use context IDs; enforce happens-before if truly needed |
| stdout/stderr logs out of order | Two streams merged by collector | Inspect each stream separately |
| Logger logs twice | Parent/child Handlers, additivity, multiple providers | Inspect Appender/Handler paths |
| Stack trace split into multiple events | Collector lacks multiline handling | Use multiline parser/structured exceptions |
| Writer thread stuck | Slow console or queue/lock deadlock | Measure contention, backpressure, and shutdown |
| Queue grows RAM | Unbounded queue and slow writer | Bounded queue, metrics, overflow policy |
| Last logs vanish on stop | Async queue not drained or stream not flushed | Shut down backend via API and monitor |
| Flaky tests | Asserting order without synchronization | Use latch/join/Future or fix expectations |
| RequestId mixed between requests | MDC/ThreadLocal not cleaned up | Propagate context and clean up |
| Flushed but missing in collector | Flush does not guarantee delivery | Check pipe/collector/retention |
| Garbled Vietnamese characters | Charset mismatch | Standardize on UTF-8 end-to-end |
| Custom formatter outputs corrupt data | Non-thread-safe mutable state | Make stateless or synchronize properly |
| Secrets leaked in logs | Printing raw payloads/exceptions | Minimize data and escape input |

**Investigation flow:** identify stream → identify backend → check writer count and formatting → check locks/queues → evaluate ordering requirements → check collector/multiline → inspect metrics/errors.

## 23. Misconceptions to Avoid

**1. “Using synchronized means event B will arrive after A.”** No. A lock prevents concurrent access, not which thread acquires the lock first.

**2. “Every println is a transaction spanning all lines.”** No. Multi-line messages or multiple calls need another coordination mechanism.

**3. “System.out and System.err are the same stream.”** No. They may appear on the same screen, but they are collected/merged separately.

**4. “Adding System.out.flush() solves interleaving.”** No. Flush only drains buffers.

**5. “Async logging never loses logs.”** No. Full queues, process kills, or collector failures can lose records.

**6. “Lines must follow thread start order.”** No. Starting threads does not fix console write scheduling between them.

**7. “A thread-safe Logger means every custom Formatter is thread-safe.”** No. Custom Formatter/Handler state must be managed separately.

**8. “One lock protects every console-printing library.”** No. Only parties sharing the same lock coordinate.

**9. “Timestamps always reflect exact system-wide order.”** No. There is clock skew, buffering, and delayed ingestion.

**10. “Multi-line stack traces are always ingested by the collector as one record.”** No. Multiline support or structured logging is required.

**11. “Missing exceptions in logs are caused by synchronization.”** The Formatter may have omitted Throwable, or a filter/level blocked it.

**12. “Console logs do not need security.”** No. They are often stored by collectors and accessed by many people; data minimization and access control are needed.

## 24. Implementation Checklist

1. Define the **unit to protect**: a single line, a LogEvent, or a multi-line stack trace.
2. Identify the **actual destination**: stdout, stderr, or both streams.
3. Choose **one primary logging backend**, avoiding direct PrintStream calls and unnecessary multiple providers.
4. Build the **complete event** before emitting; if multiple prints are required, use a shared lock or a single writer.
5. If using **synchronized**, ensure all relevant writers actually share the same lock.
6. If using **BlockingQueue**, choose bounded capacity, overflow/backpressure, shutdown, and error handling.
7. If ordering is needed, establish **happens-before/sequence** where events are created/enqueued.
8. Add requestId/jobId/thread/service; propagate context across thread pools and clean up MDC.
9. Ensure Formatter/Encoder handles Throwable and multiline output properly.
10. Understand that **flush differs from delivery/durability**; verify the collector and shutdown behavior.
11. Check for duplicates caused by Logger hierarchy, Handlers, and additivity.
12. Test with multiple threads, multiple streams, long output, and real container environments.
13. Reduce volume, measure contention, queue depth, p95/p99, and dropped events.
14. Never log secrets; standardize charset, escaping, retention, and access control.

**Conclusion:** **Output synchronization** in console logging keeps each record clear when multiple threads emit events concurrently. However, **atomicity**, **ordering**, **flushing**, and **durability** are distinct requirements. For simple demos, a single println for the whole message is usually sufficient; for production systems, use a **backend-managed Console Appender/Handler** or **a single writer/queue pipeline with explicit policies**, and rely on correlation IDs rather than log display order.

## 25. Official References

- [Oracle Java SE 17 — PrintStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html): println, autoFlush, and checkError.
- [Oracle Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): Logger API used across multiple threads.
- [Oracle Java SE 17 — ConsoleHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html): System.err output and Handler lifecycle.
- [Oracle Java SE 17 — StreamHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html): Formatter, publish, flush, and close.
- [Oracle Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): happens-before coordination between threads.
- [Oracle Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): multi-threaded queue.
- [Apache Log4j 2 — Console Appender](https://logging.apache.org/log4j/2.x/manual/appenders/console.html): target and Layout.
- [Apache Log4j 2 — Asynchronous logging](https://logging.apache.org/log4j/2.x/manual/async.html): async logger/queue trade-offs.
- [Logback — ConsoleAppender](https://logback.qos.ch/manual/appenders-console-file.html): console target, encoder, and output behavior.
