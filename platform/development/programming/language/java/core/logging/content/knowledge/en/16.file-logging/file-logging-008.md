# Closing Files on Shutdown in Java Logging

## 1. Why Do We Need to Close Logging Files Properly?

A Java application that writes logs to files may hold **file descriptors**, **output streams**, **buffers**, **file locks**, and sometimes **asynchronous logging queues**. When the program stops, the goal is not merely to exit the JVM, but also to finish processing important records still in flight, release resources, and avoid closing files while other threads are still logging.

**Closing files on shutdown** means ending the lifecycle of logging resources at the right time: stopping log-producing sources, processing pending data, writing an appropriate shutdown event, and **flushing and closing** Handlers/Appenders owned by the application. If the application stops abruptly, these steps may not have time to run.

After this lesson, you will know how to:

- Distinguish between **publish**, **flush**, **close**, **stop logging context**, and **shutdown hook**.
- Use **java.util.logging.FileHandler** with the proper lifecycle, managing file locks and rotation.
- Stop workers before closing logging files, avoiding races between producers and the Handler.
- Write a Java 17 program with two ways to close a FileHandler: **try/finally** and **Runtime.addShutdownHook**.
- Run the example and verify the exact stdout, log file contents, and existence of the lock file.
- Understand cases where hooks cannot run: **SIGKILL**, **Runtime.halt**, JVM crash, power loss, and container deadlines.
- Distinguish shutdown behavior across JUL, Log4j2, Logback, and asynchronous logging pipelines.
- Understand why **flush/close** is not proof of durable storage for auditing.

**Scope:** This lesson belongs to the **File logging** group in **Java Core Logging**. The complete example uses JUL built into the JDK; no Maven or external libraries are needed. Other logging backends are mentioned to help you choose the right lifecycle API.

## 2. How Does a Log Line Reach a File?

The simple path:

~~~text
Java business code
    |
    | logger.info("event=order.created")
    v
Logger -> LogRecord
    |
    v
Handler / Appender -> Formatter / Layout
    |
    v
File output stream / buffers
    |
    v
Operating system / filesystem
~~~

With asynchronous logging:

~~~text
Business thread
    |
    v
Async queue / ring buffer
    |
    v
Background logging consumer
    |
    v
File Appender -> stream -> filesystem
~~~

In the asynchronous case, the Logger call may return when the record has **only just been placed into the queue**. In the synchronous case, the call may complete after the Handler processes the record, yet the data may still reside in the OS page cache.

**Do not equate a returning `logger.info` call with durably persisted data.** Durability depends on queues, the logging backend's policy, streams, the operating system, the filesystem, and storage.

### 2.1. publish, flush, and close

| Operation | Role | Closes the file? |
| --- | --- | --- |
| **publish(record)** | Receives and processes an event | Not by default |
| **flush()** | Pushes data buffered by the Handler/stream to the next layer | No |
| **close()** | Terminates the stream/handler and releases resources | Yes, for FileHandler |
| **Stop logging context** | Stops the backend, may drain async queues and close multiple Appenders | Depends on backend |
| **fsync/force** | Requests data synchronization at the file/storage layer via a specific API | Different from flush |

**flush is not fsync.** Even if a file is flushed and closed, data may still remain in the OS cache or storage layer; there is no absolute guarantee against power loss. Therefore, a regular log file should not be the sole source of truth when the system requires audit guarantees.

## 3. FileHandler in Java Util Logging

The JDK provides **java.util.logging.FileHandler**, which extends **StreamHandler**. It supports writing to a single file or rotating files based on pattern/limit/count.

According to the Java 17 documentation:
- FileHandler has **publish** and **close** methods, and inherits **flush**.
- Each completed record is flushed by FileHandler according to its implementation contract, but this is not equivalent to fsync.
- The default Formatter is **XMLFormatter**, if configuration is not changed.
- Configuration options include pattern, append, limit, count, level, filter, encoding, and formatter.
- FileHandler has a file locking mechanism to coordinate open resources.
- **FileHandler.close()** closes the files managed by the Handler.

Example snippet inside a method:

~~~java
import java.util.logging.FileHandler;
import java.util.logging.Logger;

Logger logger = Logger.getLogger("demo.file");
FileHandler handler = new FileHandler("logs/app.log", true);
logger.addHandler(handler);
~~~

This is **not a standalone program**. It requires a writable `logs` directory. The constructor's `true` argument requests appending according to FileHandler's mechanism; it does not mean multiple JVMs can safely write to the same file without coordination.

### 3.1. Who Must Close FileHandler?

Distinguish between two sources of Handler creation:

1. **Created by the application itself** with `new FileHandler` and attached to a Logger: the application owner must manage remove/flush/close.
2. **Created by LogManager/framework** via `logging.properties` or runtime configuration: the lifecycle may be managed by LogManager or the framework.

Do not close a shared Handler at the end of every request or inside a library that does not own the logging context.

### 3.2. Pattern for Closing an Owned Handler

When the application owns the Handler, after all log-producing threads have stopped:

~~~java
logger.removeHandler(handler);
try {
    handler.flush();
} finally {
    handler.close();
}
~~~

This is an illustrative snippet; it assumes `logger` and `handler` have already been created. **removeHandler** prevents the Logger from sending further events to the Handler via that direct attachment, but it **does not automatically wait for all producers currently publishing**. Producer/consumer coordination must be handled at the application layer.

### 3.3. Logger OFF Is Different from FileHandler.close

~~~java
logger.setLevel(java.util.logging.Level.OFF);
~~~

Setting a Logger to OFF only blocks normal events by level. It **does not release file descriptors, does not delete lock files, does not drain queues, and does not replace close()**. To stop resources, close the Handler or the logging context using the proper API.

## 4. Shutdown Order for a Service That Logs to Files

An intentional graceful shutdown typically proceeds as follows:

~~~text
Stop signal / application lifecycle
             |
             v
Stop accepting new requests or jobs
             |
             v
Stop schedulers and task-generating sources
             |
             v
Wait for running requests/workers to finish within deadline
             |
             v
Log a meaningful shutdown event
             |
             v
Drain async logging queue if present
             |
             v
Flush and close FileHandler / stop backend
             |
             v
Release remaining resources and exit JVM
~~~

In a real application, the order of database/network/worker shutdown also depends on inter-service dependencies. However, **if a component can still emit logs, you should not close the logging backend before that component stops**.

Example of an incorrect order:

~~~text
T0: Shutdown hook closes FileHandler
T1: Worker has not finished payment
T2: Worker logs event=payment.failed
T3: FileHandler is already closed; event loses its intended destination
~~~

A better order is:
- Stop accepting new payments.
- Wait for in-flight payments to complete or be canceled in a controlled manner.
- Log a work summary event.
- Close logging after the necessary events are emitted.

### 4.1. Shutdown Deadline

Graceful shutdown does not mean waiting indefinitely. If an executor does not stop before the deadline, the application needs a clear policy: report the status, request cancellation via interrupt, wait a bounded additional time, or accept the risk of losing events.

Illustrative example with ExecutorService:

~~~java
executor.shutdown();
if (!executor.awaitTermination(10, java.util.concurrent.TimeUnit.SECONDS)) {
    executor.shutdownNow();
}
logger.info("event=executor.shutdown_requested");
~~~

This snippet is not standalone: it requires `executor`, `logger`, and `InterruptedException` handling. Importantly, **shutdownNow does not guarantee that all tasks have stopped immediately**. Do not assume it is safe to close files right after `shutdownNow` while workers may still be logging.

## 5. How Do JVM Shutdown Hooks Work?

Java provides **Runtime.addShutdownHook(Thread)** to register a thread that runs when the JVM begins a normal shutdown.

Illustrative example:

~~~java
Runtime.getRuntime().addShutdownHook(
    new Thread(() -> cleanupResources(), "cleanup-hook"));
~~~

This snippet requires a valid `cleanupResources` method; it is not a standalone program.

According to Oracle Java 17 documentation:
- Hooks are run in an **unspecified order**.
- They may run **concurrently**.
- Hooks should be short, thread-safe, and avoid deadlocks.
- You should not blindly depend on services that also have their own hooks.
- Once JVM shutdown has started, you cannot arbitrarily register or unregister additional hooks.

**A shutdown hook does not replace orderly shutdown.** It is only a fallback cleanup layer. If a framework already owns the logging backend and has its own shutdown mechanism, adding another hook may cause both sides to close resources at the same time.

### 5.1. Types of JVM Termination

| Scenario | Things to Note |
| --- | --- |
| `main` finishes and no non-daemon threads remain | JVM can execute the shutdown sequence and hooks |
| `System.exit(...)` | Initiates the shutdown sequence |
| Ctrl+C / signal handled by JVM | May trigger hooks, depending on OS/JVM |
| Framework lifecycle stop | May stop the backend via its own lifecycle |
| SIGTERM in a container | Can be graceful if the process receives it and has time |
| SIGKILL / TerminateProcess | No guarantee that hooks will run |
| `Runtime.getRuntime().halt(...)` | Bypasses normal shutdown |
| JVM crash / power loss | No guarantee of cleanup |
| Container force-killed after grace period | No guarantee that queues or hooks finish |

Never say "hooks always run." For forced termination or JVM abort, Oracle explicitly states that **there is no guarantee that shutdown hooks will be executed**.

### 5.2. Should You Log from a Shutdown Hook?

You should not rely on a log event inside a hook as proof that the application stopped cleanly. JUL LogManager, Log4j2, or a framework may also have a shutdown hook closing Handlers/Appenders concurrently. Because the order among hooks is not guaranteed, the final `logger.info` call may be lost.

You should **emit the `app.stopping` event during the graceful lifecycle** while logging is still active; the hook should only serve as fallback cleanup for resources not yet closed.

### 5.3. Idempotent Close

An application might close the Handler in `finally`, and then the hook is still invoked when the JVM exits. An **AtomicBoolean** prevents the application-controlled close branch from executing a second time:

~~~java
if (!CLOSED.compareAndSet(false, true)) {
    return;
}
handler.flush();
handler.close();
~~~

This is an illustrative snippet inside a method that already has `CLOSED` and `handler`. AtomicBoolean **does not replace mechanisms that prevent other threads from logging**; it only avoids repeating the close logic across the owner's two cleanup paths.

## 6. Complete Java 17+ Example

This program uses JUL `FileHandler` and has two modes:

1. Default mode: logs events and closes the file in `finally`.
2. **--hook** mode: returns from `main`; the JVM runs the fallback shutdown hook.
3. The log file is located at **demo-logs/shutdown-demo.log**.
4. The Formatter output has the form **LEVEL|message**, independent of timestamps.

**This code runs on Java 17+, without Maven, Gradle, or external libraries.**

### 6.1. ShutdownFileLoggingDemo.java

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ShutdownFileLoggingDemo {
    private static final Logger LOG = Logger.getLogger("demo.file.shutdown");
    private static final AtomicBoolean CLOSED = new AtomicBoolean();

    public static void main(String[] args) throws Exception {
        Path logPath = Path.of("demo-logs", "shutdown-demo.log");
        Files.createDirectories(logPath.getParent());

        FileHandler file = new FileHandler(logPath.toString(), false);
        file.setEncoding(StandardCharsets.UTF_8.name());
        file.setLevel(Level.INFO);
        file.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + "|" + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(file);

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            closeOnce(file);
            System.out.println("hook=completed");
        }, "file-log-shutdown"));

        if (args.length > 0 && "--hook".equals(args[0])) {
            LOG.info("event=app.started");
            LOG.warning("event=app.hook_mode");
            System.out.println("mode=hook");
            return;
        }

        try {
            LOG.info("event=app.started");
            LOG.info("event=task.completed");
            LOG.info("event=app.stopping");
        } finally {
            closeOnce(file);
        }
        System.out.println("mode=explicit;handlerClosed=" + CLOSED.get());
    }

    private static void closeOnce(FileHandler file) {
        if (!CLOSED.compareAndSet(false, true)) {
            return;
        }
        LOG.removeHandler(file);
        try {
            file.flush();
        } finally {
            file.close();
        }
    }
}
~~~

### 6.2. Compiling and Running

~~~bash
javac --release 17 -encoding UTF-8 ShutdownFileLoggingDemo.java
java ShutdownFileLoggingDemo
~~~

**Verified actual stdout of default mode:**

~~~text
mode=explicit;handlerClosed=true
hook=completed
~~~

**Contents of demo-logs/shutdown-demo.log:**

~~~text
INFO|event=app.started
INFO|event=task.completed
INFO|event=app.stopping
~~~

Explanation:
- `FileHandler` opens a file in `demo-logs`.
- `Logger` emits three events.
- The `finally` block calls `closeOnce`, removes the Handler, flushes, and closes before `main` finishes.
- The line `handlerClosed=true` shows that the application's cleanup branch ran.
- During JVM shutdown, the hook is still invoked, but `AtomicBoolean` prevents `closeOnce` from running again.
- The line `hook=completed` uses **System.out.println** to prove the hook ran in the example; **it is not file logging content**.

### 6.3. Running in Hook Mode

~~~bash
java ShutdownFileLoggingDemo --hook
~~~

**Verified stdout:**

~~~text
mode=hook
hook=completed
~~~

**Log file after the process exits:**

~~~text
INFO|event=app.started
WARNING|event=app.hook_mode
~~~

In this mode, `main` returns without explicitly calling `closeOnce`. The hook is invoked by the JVM during normal shutdown. However, **JUL LogManager also has its own mechanism to clean up Handlers during JVM shutdown**; observing that the file is closed is not proof that the application-written hook is the sole component closing the file in every environment.

### 6.4. Checking the Lock File

In the test runs, after the Java process exited, **shutdown-demo.log.lck** was no longer present in either mode. That is consistent with `FileHandler` no longer holding the session lock in the test environment. Do not generalize that every OS and filesystem always creates/deletes the exact same kind of lock file.

**Windows PowerShell:**

~~~powershell
Get-Content .\demo-logs\shutdown-demo.log -Encoding UTF8
Get-ChildItem .\demo-logs
~~~

**Linux/macOS:**

~~~bash
cat demo-logs/shutdown-demo.log
ls -la demo-logs/
~~~

**Note on `append=false`:** The demo uses `new FileHandler(path, false)` so the file has deterministic contents, meaning a subsequent run may overwrite the previous run's contents. Do not use this policy for production files where history must be preserved.

### 6.5. Why the Demo Does Not Solve All Production Problems

This is a single-threaded example. In a multi-threaded server, you must stop producers before closing. Furthermore, a hook is only a fallback. If the JVM is force-killed, it is possible for the JVM not to finish closing or for stdout not to be collected in time.

## 7. Closing Files in Multi-Threaded Applications

Suppose an `ExecutorService` logs through a `Logger` attached to a `FileHandler`. If you call `close` while the executor still has tasks, workers may continue emitting logs.

Practical order:

1. Mark the service as stopping and stop accepting new work.
2. Stop schedulers, subscriptions, or sources that create new tasks.
3. Call `shutdown` on the executor.
4. Wait for important tasks to complete within the allowed time.
5. If the deadline is nearly reached, decide on cancellation, status logging, or escalation according to policy.
6. Only when producers that need to log have stopped, emit the shutdown event.
7. Stop the async logging consumer if present, then close the file sink.
8. Terminate the process.

### 7.1. Check-Then-Act Race

Mistake:

~~~java
if (!closed) {
    logger.info("event=task.done");
}
~~~

This is an illustrative snippet inside a method with a variable. Between thread A checking `closed` and calling `Logger`, thread B may have already closed the Handler. Therefore, a single boolean does not guarantee safe logging.

**The architectural solution** is to coordinate the lifecycle of task producers, not to scatter `closed` checks across thousands of log call sites.

### 7.2. Async Pipeline

If the application uses Log4j2 `AsyncLogger`/`AsyncAppender` or another async backend:

~~~text
Producer -> Queue -> Background consumer -> File appender
~~~

The shutdown order must give the consumer a chance to process the queue before closing the File Appender. You need to test scenarios with full queues, slow sinks, timeouts, drop policies, and network/disk errors.

Do not close the low-level file appender before the async backend completes its stop according to contract. And do not claim async logging will preserve every log if the process receives SIGKILL or is overloaded.

## 8. File Rotation and Locks During Shutdown

JUL `FileHandler` can be configured via **logging.properties**:

~~~properties
handlers = java.util.logging.FileHandler
.level = INFO
java.util.logging.FileHandler.level = INFO
java.util.logging.FileHandler.pattern = logs/service-%u-%g.log
java.util.logging.FileHandler.limit = 1048576
java.util.logging.FileHandler.count = 5
java.util.logging.FileHandler.append = true
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
~~~

This is a configuration example, not Java code. Ensure `logs/` is writable and JUL actually loads the properties.

**`FileHandler.close` does not replace retention.** Rotation creates generations according to `pattern`/`count`; closing the Handler does not mean deleting all old files. You need separate policies for disk space, retention period, and access permissions.

### 8.1. Why Does `.lck` Exist?

`FileHandler` uses a lock mechanism to avoid conflicting use of file resources. While a process is still running, **do not manually delete the `.lck` file just because you see it**. Before cleaning up a leftover lock after a crash, check the process, file pattern, write permissions, and deployment environment.

An application with multiple replicas or multiple JVMs sharing a filesystem needs separate paths/locks/rotation or an appropriate log collection architecture. Do not assume the same log file can be safely written from all processes.

### 8.2. Is Resetting JUL Dangerous?

**`java.util.logging.LogManager.getLogManager().reset()`** resets JUL configuration JVM-wide, which can remove/close Handlers across many Loggers. Do not use `reset` to clean up one file of a running module while other components still need logging.

If a Handler was created from JUL `logging.properties`, `LogManager` has lifecycle management mechanisms and options such as **`<logger>.handlers.ensureCloseOnReset`**. Unless you have a very specific requirement, do not disable default Handler closing mechanisms and then neglect cleanup responsibility.

## 9. Differences with Log4j2 and Logback

### 9.1. Log4j2

Log4j2 has its own `LoggerContext`, File/RollingFile Appenders, and shutdown mechanism. According to Log4j2 documentation, many applications have a shutdown hook managed by the backend; web/framework environments may replace that mechanism with an integrated lifecycle.

When the application truly **owns the LoggerContext** and needs to close it manually, the Log4j API provides:

~~~java
org.apache.logging.log4j.LogManager.shutdown();
~~~

This is a **Log4j2-dependent snippet** and does not compile with pure JDK. Overloads can select a specific context; do not assume it will close every `LoggerContext` in a multi-classloader JVM.

In Spring Boot or an application server, you usually let the framework own the lifecycle. A library should not call `shutdown` itself and cause other components to lose logs.

### 9.2. Logback

Logback has its own `LoggerContext` and Appenders. When the application itself creates and owns the context, it can stop it using the appropriate lifecycle API, typically **`LoggerContext.stop()`**. When a framework owns it, let the framework do it.

Do not call JUL `FileHandler.close` to close a Logback `RollingFileAppender`; they are resources belonging to two different logging systems.

### 9.3. Do You Need to Register a Second Shutdown Hook?

Not by default. If JUL or the backend already has cleanup logic, another hook can run concurrently and contend over shutdown ordering. You need one clear lifecycle owner; an application hook should only be a fallback when truly needed, kept short and idempotent.

## 10. Production, Containers, and Durability

### 10.1. Graceful Container Termination

When a container is about to stop, the application usually has a grace period to drain in-flight requests, stop workers, and shut down logging. If it exceeds that time, the runtime may force-kill the process and hooks are not guaranteed to run.

You should:
- Ensure the Java process actually receives the signal.
- Stop accepting new traffic before closing logs.
- Wait for workers with a bounded timeout.
- Let the logging context stop within the remaining time.
- Measure actual timings when the system is under load.
- Define a policy for when not all records can be drained.

### 10.2. Console Logging Does Not Eliminate Shutdown Concerns

In containers, many systems write to stdout/stderr and let the runtime/collector ingest them. This can be a reasonable choice, yet appenders, async queues, container log drivers, and collectors can still buffer or fail. Whether using files or console, verify end-to-end delivery of final events.

### 10.3. Why Log Files Do Not Replace Audit Storage

A diagnostic event like **event=payment.completed** is useful for investigation, but does not by itself prove a transaction was durably recorded. When auditability is required, you need a storage/transaction/outbox model or a recording channel with acknowledgments, retries, retention, integrity, and access control.

**`close`/`flush` helps with cleanup; it does not provide exactly-once guarantees or protection against all crash types.**

## 11. Common Mistakes

### 11.1. Closing Too Early

`FileHandler` is closed before workers log their final error. Stop producers first, then close the sink.

### 11.2. Relying Solely on Shutdown Hooks

SIGKILL, `halt`, crashes, or power loss can bypass hooks. Hooks are only a fallback.

### 11.3. Logging Inside a Shutdown Hook

Another hook may have already closed the backend. Emit final events during the graceful lifecycle, then stop logging.

### 11.4. Calling `LogManager.reset` Arbitrarily

Resetting JUL affects many Loggers/Handlers, not just one file. Close resources through their proper owner.

### 11.5. Believing `AtomicBoolean` Solves Concurrency

`AtomicBoolean` makes `closeOnce` idempotent; it does not stop threads that are currently publishing.

### 11.6. Closing the Appender Before the Async Consumer

Queued events may be lost. Stop the backend via the API that supports draining/shutdown.

### 11.7. Thinking `flush` Is `fsync`

`flush` does not guarantee that the OS/storage has durably persisted data on power loss.

### 11.8. Opening Multiple FileHandlers to the Same Path

This can cause locking or unexpected file naming. Manage a single owner or use an appropriate multi-instance architecture.

### 11.9. Deleting `.lck` While the App Is Running

This can break file coordination. Check processes and locks first.

### 11.10. Ignoring Append, Rotation, and Restarts

Files may be overwritten or grow unbounded; establish append/rotation/retention policies and test restarts.

### 11.11. Shutting Down the Backend from a Small Library

The backend may be a shared resource for the entire app. Only the owner/framework should stop it.

### 11.12. Waiting Indefinitely in a Shutdown Hook

This can exceed the container deadline and get the process killed. Keep hooks short, avoid deadlocks, and use reasonable timeouts.

## 12. Testing Checklist

| Scenario | What to Verify |
| --- | --- |
| Normal close | `app.stopping` event is emitted before `close` |
| Hook fallback | Runs during normal JVM shutdown |
| Double close | `closeOnce` is idempotent |
| Workers still running | File is not closed while producers have not stopped |
| Async queue | Drains according to contract and time limit |
| File lock | No longer held by an exited process |
| File rotation | Generations and retention match configuration |
| Append/restart | History is not unintentionally overwritten |
| Disk full/permission denied | Appropriate error handling path exists |
| SIGTERM | Reasonable time for shutdown |
| SIGKILL | Does not promise preserving final logs |
| Unicode | UTF-8 is preserved |
| Multiple processes | No improper file contention |
| Framework | `LoggerContext` is stopped by the proper owner |

### 12.1. Testing on Windows PowerShell

~~~powershell
javac --release 17 -encoding UTF-8 ShutdownFileLoggingDemo.java
java ShutdownFileLoggingDemo
Get-Content .\demo-logs\shutdown-demo.log -Encoding UTF8
Get-ChildItem .\demo-logs
java ShutdownFileLoggingDemo --hook
Get-Content .\demo-logs\shutdown-demo.log -Encoding UTF8
Get-ChildItem .\demo-logs
~~~

### 12.2. Testing on Linux/macOS

~~~bash
javac --release 17 -encoding UTF-8 ShutdownFileLoggingDemo.java
java ShutdownFileLoggingDemo
cat demo-logs/shutdown-demo.log
ls -la demo-logs
java ShutdownFileLoggingDemo --hook
cat demo-logs/shutdown-demo.log
ls -la demo-logs
~~~

**Note:** The demo uses `append=false`, so the second mode may overwrite the file from the previous run. Do not use the demo path when practicing with production logs that require preserving history.

## 13. Extended Exercises

**Exercise 1 — Shutting down a worker pool.** Create multiple tasks logging concurrently through `FileHandler`, stop accepting new tasks, wait for the executor to finish, and then close the Handler. Explain the case where a task does not respond to interrupts.

**Exercise 2 — Append and rotation.** Change `FileHandler` to `append=true` and add `limit`/`count`. Run multiple times, observing file generations and locks after shutdown.

**Exercise 3 — Final error event.** Add a `try/catch` with a `Throwable` and log it before closing; inspect the stack trace with an appropriate Formatter.

**Exercise 4 — Log4j2 comparison.** Diagram the flow `AsyncLogger -> queue -> File Appender`; explain why you must not close the file directly before the context stops.

**Exercise 5 — Container.** Define the shutdown order for the HTTP listener, scheduler, workers, logger context, and process within a specific grace period. Describe how to measure lost events.

**Exercise 6 — Audit.** Design an audit storage channel with acknowledgment and retry; compare it with `FileHandler.flush` and `close`.

## 14. Self-Assessment Questions

**1. How does `FileHandler.flush` differ from `close`?**  
`flush` pushes buffered data according to the API; `close` terminates the Handler and releases file handles/locks.

**2. Does a shutdown hook always run on SIGKILL?**  
No.

**3. Do shutdown hooks run sequentially in registration order?**  
No. They can run concurrently in an unspecified order.

**4. Should you close the file first when receiving a shutdown request?**  
Not if workers are still emitting logs. Stop producers first.

**5. What problem does `AtomicBoolean CLOSED` solve in the demo?**  
It prevents the owner's `closeOnce` branch from running cleanup multiple times, not stopping producers.

**6. Does `FileHandler.close` delete old files?**  
No. Retention is a separate policy.

**7. Does closing the file guarantee data is safe against power loss?**  
No. `flush`/`close` is not equivalent to transactional durability.

**8. Does `LogManager.reset()` only close a single Handler?**  
No. It resets the JVM's JUL system and can close many Handlers.

**9. For Log4j2, which API should you use to stop when the application owns the context?**  
Use Log4j2's lifecycle API, such as `LogManager.shutdown` with the appropriate scope.

**10. If an async queue still has events, what should you do before closing?**  
Stop producers and let the consumer drain according to the backend's contract and deadline.

**11. Can you just use a single shared lock file for all replicas?**  
You should not assume that. You need an appropriate file-separation or log-collection policy, and verify locking/rotation.

**12. Why shouldn't you put the final log inside a shutdown hook?**  
The backend may already be closed by another hook; hook ordering is not guaranteed.

## 15. Official References

- Oracle JDK 17 FileHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html
- Oracle JDK 17 Handler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html
- Oracle JDK 17 LogManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html
- Oracle JDK 17 Runtime and shutdown hooks: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html
- Apache Log4j 2 Shutdown FAQ: https://logging.apache.org/log4j/2.x/faq.html
- Apache Log4j 2 Async Logging: https://logging.apache.org/log4j/2.x/manual/async.html

Cross-check documentation against the actual JDK, OS, framework, and backend used by your application. Signal behavior, file locking, async buffering, and shutdown timeouts can vary by runtime.

## 16. Core Takeaways

**Properly closing logging files on shutdown is managing an entire process, not simply calling `close()`.** With an application-owned JUL `FileHandler`, you need to stop record-producing sources, write the final event, remove the Handler, and then flush/close. A shutdown hook provides fallback cleanup during normal JVM shutdown, but does not guarantee handling every kind of force kill, crash, or power loss.

In frameworks and asynchronous logging systems, you must stop the logging context properly so queues and Appenders are handled according to contract. If events carry a durable storage obligation, use a dedicated audit/storage mechanism with acknowledgments rather than relying on plain text log files.

The Java 17 example was compiled and run in both modes; stdout, file contents, and lock files were all verified in the test environment. Those results provide a foundation for building a clear, tested shutdown procedure suited to operational needs.
