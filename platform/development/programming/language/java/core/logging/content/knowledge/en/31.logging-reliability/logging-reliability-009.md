# Shutdown Hooks and Logging Reliability in Java

## 1. What is a shutdown hook and why does logging need one?

A **shutdown hook** is a `Thread` registered with the JVM via `Runtime.getRuntime().addShutdownHook(...)`. When the JVM begins an **orderly shutdown**, it starts all registered hooks so the application has a chance to clean up: stop accepting new work, finish processing pending data, close connections, and **flush/close logging components**.

In a logging system, a call such as `logger.info("order created")` does not always mean that the line is already safely stored in a file or remote log store. Depending on the backend, the data may still be in:

- A handler/appender or encoder buffer.
- An **asynchronous logging** queue, waiting for a worker to write it.
- An I/O buffer, socket, or network transport channel.
- A log collector's memory before being persisted durably.

Therefore, a shutdown hook can serve as a **final line of defense during a controlled shutdown**: instructing the system to stop generating new events, waiting a reasonable amount of time for queues to drain, and flushing and closing open resources. However, a hook **does not turn logging into a durable transaction** and does not replace runtime reliability mechanisms.

### Two cases to distinguish

1. **Graceful shutdown:** The JVM has the opportunity to run hooks; the logging system can complete pending operations if given enough time and resources.
2. **Abrupt termination:** The JVM or host is terminated suddenly; hooks may **not run**, and logs in buffers or queues may be lost.

The goal of this lesson is to use hooks at the right time, avoid overestimating their ability to rescue logs, and design a verifiable application shutdown flow.

## 2. When are shutdown hooks executed?

The JVM initiates an orderly shutdown in these typical scenarios:

- No non-daemon threads remain running, so the JVM exits normally.
- The application calls `System.exit(status)` (if the call actually initiates shutdown).
- Certain termination signals sent by the operating system, such as `SIGTERM` on a platform/JVM that handles that signal to start shutdown.

Once shutdown begins, registered hooks are **started concurrently**, in **no guaranteed order**. The JVM waits for all hooks to finish before completing the orderly shutdown sequence.

You must not assume hooks will run in cases such as:

- `SIGKILL` (`kill -9`) on the respective operating system.
- `Runtime.getRuntime().halt(...)`, which bypasses the normal shutdown sequence.
- Power loss, host failure, forced process termination, or certain fatal JVM errors.
- A container being forcibly stopped by the platform after its grace period expires.

**Implication:** A shutdown hook is a *best-effort* mechanism when the JVM can shut down cleanly, **not a guarantee that every log event will survive every kind of failure**.

### Lifecycle of a hook

~~~text
RUNNING
   |
   | JVM starts orderly shutdown
   v
START SHUTDOWN HOOKS (no guaranteed order)
   |                 |
   |                 +--> Hook for database / other services
   |
   +--> Logging hook
           |
           +--> Avoid creating new log events unless necessary
           +--> Wait for worker/queue within a time limit
           +--> Flush buffers and close appender/handler
           |
           v
      HOOK FINISHED
   |
   v
JVM completes shutdown (unless forcibly terminated)
~~~

A `Thread` used as a hook must be in the **not yet started** state when registered. Do not call `start()` on it beforehand, do not register the same thread object multiple times, and do not rely on execution order between hooks. Once shutdown has started, attempts to register or unregister hooks may be rejected with `IllegalStateException`.

## 3. Standalone Java 17 example: flushing logs on JVM exit

To clearly illustrate the difference between **creating a log event** and **writing data to a file**, the example below intentionally uses a simple `Handler` that buffers messages in a `StringBuilder`. When the JVM shuts down, the hook calls `close()`, causing the handler to write the remaining data to a file.

This is an educational example of the logging lifecycle; **do not use this custom handler as a production logging backend**. Real-world backends already provide their own buffering, flushing, and lifecycle mechanisms. The example uses the standard `java.util.logging` (JUL) API and runs on **JDK 17 or later** with no external dependencies.

Create the file **`ShutdownHookLoggingDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ShutdownHookLoggingDemo {

    private static final class BufferedHandler extends Handler {
        private final Path target;
        private final StringBuilder pending = new StringBuilder();
        private boolean closed;

        BufferedHandler(Path target) {
            this.target = target;
            setLevel(Level.ALL);
        }

        @Override
        public synchronized void publish(LogRecord record) {
            if (closed || !isLoggable(record)) {
                return;
            }
            pending.append(record.getLevel().getName())
                    .append(": ")
                    .append(record.getMessage())
                    .append(System.lineSeparator());
        }

        @Override
        public synchronized void flush() {
            if (closed || pending.length() == 0) {
                return;
            }
            try {
                Files.writeString(
                        target,
                        pending.toString(),
                        StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE,
                        StandardOpenOption.APPEND);
                pending.setLength(0);
            } catch (IOException ex) {
                // Avoid calling back into the logger during shutdown.
                System.err.println("Log flush failed: " + ex.getMessage());
            }
        }

        @Override
        public synchronized void close() {
            if (closed) {
                return;
            }
            flush();
            closed = true;
        }
    }

    public static void main(String[] args) throws IOException {
        Path output = Path.of("logs", "shutdown-hook.log");

        if (args.length == 1 && "verify".equals(args[0])) {
            Files.readAllLines(output, StandardCharsets.UTF_8)
                    .forEach(System.out::println);
            return;
        }
        if (args.length != 0) {
            throw new IllegalArgumentException("Usage: [verify]");
        }

        Files.createDirectories(output.getParent());
        Files.deleteIfExists(output);

        BufferedHandler handler = new BufferedHandler(output);
        Logger logger = Logger.getLogger("demo.shutdown.hook");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);
        logger.addHandler(handler);

        Runtime.getRuntime().addShutdownHook(
                new Thread(handler::close, "logging-shutdown-hook"));

        logger.info("service started");
        logger.warning("work pending");

        System.out.println("main finished");
        // JVM exits normally; the hook flushes the buffer.
    }
}
~~~

Compile and run in a directory with write permissions:

~~~bash
javac ShutdownHookLoggingDemo.java
java ShutdownHookLoggingDemo
java ShutdownHookLoggingDemo verify
~~~

**Stdout from the first run:**

~~~text
main finished
~~~

**Stdout from the second run** (`verify` reads the file after the first JVM has exited):

~~~text
INFO: service started
WARNING: work pending
~~~

The file is created at the relative path **`logs/shutdown-hook.log`**, resolved from the process working directory. Given a writable directory and a normal shutdown, the file contains the two lines shown in the `verify` run. If the file cannot be written, the example prints an error to stderr; in that case, the flush cannot be considered successful.

### Program explanation

- `publish()` **only appends messages to the buffer** without writing to the file immediately. Thus, a successful `logger.info` call does not mean the file already exists.
- `BufferedHandler.flush()` writes the remaining content using `Files.writeString` and clears the buffer if the write succeeds. This is a real file write operation, not a `System.out` call.
- `close()` calls `flush()` and marks the handler as `closed`; calling `close()` again does not produce duplicate entries. **Idempotency** matters because multiple lifecycle managers might attempt to close the same handler.
- `synchronized` protects `pending` and `closed` when accessed concurrently by logging threads and the shutdown thread. It does not make all file I/O unconditionally safe.
- The hook calls **`handler.close()`** directly rather than going through the logger API, avoiding new log creation while the logging system is shutting down.
- The `verify` mode runs in **a new JVM** to read the result after the first JVM has exited; no hook or handler is registered in this branch.

**Important caveat:** JUL has an internal shutdown mechanism that closes handlers managed by `LogManager`. In a program using `Logger`, JUL's shutdown and a custom hook may both call `close()` in arbitrary order. The code above intentionally makes `close()` safe to call repeatedly, so the file is still written once under normal conditions. The example demonstrates **how to prepare cleanup at shutdown time**, not that JUL requires a custom hook to write any logs at all.

## 4. Flush, close, and durability are not the same thing

Three concepts are often conflated:

| Action | Primary meaning | What not to infer |
| --- | --- | --- |
| **Flush** | Pushes buffered data to the next output layer | Does not guarantee data is durably persisted on disk or a remote host |
| **Close** | Ends the resource lifecycle; typically flushes and closes streams/sockets/workers per component contract | Does not guarantee all network data reached its destination or all errors were handled |
| **Durability/acknowledgment** | Confirms data is retained by the system under a specific policy | Cannot be inferred solely from calling `logger.info` or `close` |

An asynchronous backend may place an event in a queue and return immediately. A hook calling flush/stop can help the worker move data from the queue to a file. However, data may still sit in the OS page cache, encounter a network interruption, or be held only temporarily by a collector before persistence.

If logs carry legal or financial integrity requirements, you need a dedicated storage/ingestion architecture: clearly defined receivers, acknowledgment mechanisms, durable storage, retries, deduplication, and monitoring. **Do not rely on a shutdown hook as the sole guarantee for a critical audit trail.**

## 5. Designing a shutdown hook properly

A well-designed hook typically has the following characteristics:

1. **Registered once**, after logging resources are initialized and before the system might need to shut down.
2. **Short and bounded:** perform only the necessary closing operations; if waiting for workers or exporters, enforce an appropriate timeout.
3. **Idempotent:** calling cleanup twice must not corrupt state, emit duplicate logs, or attempt to use an already-closed resource.
4. **Does not emit new logs through the closing backend:** if cleanup errors must be reported, consider a minimal diagnostic channel such as `System.err` depending on context.
5. **Handles errors locally:** catch and handle `IOException`/`InterruptedException` appropriately so a failure in one step does not prevent remaining resources from being cleaned up.
6. **Independent of hook order:** the logging hook must not assume it will run after every database, HTTP server, or scheduler hook.
7. **Never blocks indefinitely:** in containers or service managers, the platform will forcibly kill the process once the deadline is exceeded.

If the application needs to stop processing requests before closing logging, an explicit lifecycle orchestrator is a better design:

~~~text
Receive shutdown request
        |
        v
Stop accepting new work
        |
        v
Wait for in-flight work (bounded)
        |
        v
Stop producing new log events
        |
        v
Drain async logging queue
        |
        v
Flush/close logging backend
        |
        v
Exit process
~~~

This is **the desired sequence managed by an application lifecycle coordinator**, not an automatic order imposed by the JVM on shutdown hooks. If you simply register several separate hooks and hope the JVM runs them sequentially, the design is vulnerable to race conditions.

### What not to do inside a hook

- Do not call `System.exit(...)` from a shutdown hook itself: the JVM is already shutting down, and this call can cause an indefinite wait.
- Do not wait indefinitely on a thread that holds a lock or is waiting for the hook itself to finish.
- Do not initialize a new logging pipeline/backend while the rest of the system is closing.
- Do not perform unbounded network operations without a timeout, and do not assume a second shutdown signal will always rescue the process.
- Do not use a fixed `Thread.sleep` as a way to "guarantee logs are flushed." Sleeping proves neither that the queue is empty nor that the file is closed.

## 6. Async logging: logs can still be lost even with a hook

With asynchronous logging, the event flow typically looks like this:

~~~text
Worker thread: logger.info(event)
                      |
                      v
                   Async queue
                      |
                      v
                Background writer
                      |
                      v
              File / socket / collector
~~~

When a shutdown signal arrives, the challenge is not merely flushing an `OutputStream`, but also **draining pending events from the queue** and preventing other threads from enqueueing new events indefinitely.

Questions to answer from backend documentation and tests:

- Does `stop()` or `close()` **wait for the queue to drain**, or does it only reject new events?
- When the queue is full, does the backend **block, drop events, or fall back to synchronous writes**?
- Is there a shutdown wait limit; once the deadline expires, what happens to remaining events?
- When a network exporter fails, are there retries, timeouts, or temporary disk spooling?
- Can the hook run concurrently with another framework or backend shutdown?
- Has the collector confirmed durable storage of the event, or only received it over a socket?

**Rule of thumb:** when a backend or framework already manages logging shutdown, prefer its built-in lifecycle mechanism and configure its timeouts and queue policies. Registering an extra hook that redundantly calls `stop()` can cause races or close the backend prematurely if the lifecycle is not carefully coordinated.

## 7. JUL, Logback, Log4j 2: there is no single universal shutdown hook

### Java Util Logging (JUL)

In a JDK-only application, `java.util.logging.LogManager` typically has a JVM shutdown handler that closes handlers according to JUL's lifecycle. For standard `ConsoleHandler`/`FileHandler`, **you do not need to write an extra hook by default** just to call close. If your application creates a custom `Handler` with its own buffer or queue, you must define who owns the resource and who is responsible for shutting it down.

In particular, if you add a custom hook, `LogManager` and that hook may run concurrently. Resources should tolerate repeated `close()` calls or have clear lifecycle coordination.

### SLF4J with Logback

**SLF4J is a facade API** and is not uniformly responsible for how every logging backend shuts down. Logback has its own lifecycle for its logger context and appenders; when running inside a framework like Spring Boot, the framework typically manages starting and stopping logging.

If you manage the lifecycle yourself in a standalone application, use the stop/close API supported by the backend instead of assuming that closing an SLF4J logger will flush queues. **There is no standard `close()` method on `org.slf4j.Logger`** to replace backend lifecycle management.

### Log4j 2

Log4j 2 provides lifecycle management and shutdown mechanisms configured at the backend/context level. With async configurations, check the stop policy, timeouts, and whether pending events are drained on exit.

**Do not layer an extra hook on top of an existing shutdown system** without verifying the exact version, configuration, and closing order. When integrating with Spring Boot, Jakarta application servers, containers, or other frameworks, the application may already have a graceful shutdown lifecycle; the right cleanup point may be a framework lifecycle callback rather than a custom JVM hook.

## 8. Shutdown hooks and deployment environments

### Running directly on a host or as a service

In a typical CLI program, the JVM exits after the last non-daemon thread finishes. A hook can work as shown in section 3. If Java runs under a service manager, check how the service stops the process: does the system send a signal that allows orderly shutdown, or does it terminate forcibly? Is cleanup time capped?

### Docker and Kubernetes

In container platforms, the orchestrator typically asks the process to stop first and then forcibly terminates it after a grace period expires. On Linux/HotSpot, an appropriate termination signal such as `SIGTERM` usually gives the JVM a chance to run hooks; however, **this is not guaranteed** if the signal never reaches Java, the runtime does not handle it as expected, or the grace period runs out.

A common pitfall: a container starts via a shell wrapper that does not forward signals properly, so Java never receives the stop request as expected. Check the command/entrypoint, PID 1 signal handling, and the platform's shutdown timeout.

For systems with in-flight HTTP requests, you should:

1. Remove the instance from new request routing or stop accepting work.
2. Give in-flight requests a bounded window to finish.
3. Drain and close the logging system.
4. Exit the process before the container/service manager deadline.

If the system receives `SIGKILL` after a timeout, any still-running hooks will have no chance to finish. **Increasing the timeout** only helps when paired with monitoring and a reasonable wait window; it does not guarantee data survival if the host crashes.

## 9. Testing shutdown reliability

Do not run `System.exit(0)` once and conclude that logging is safe. Design tests that closely reflect the real system:

| Test case | What to observe |
| --- | --- |
| Normal exit | Hook runs, queue drains, handler/appender closes |
| Logging immediately before shutdown | Whether final events reach the destination |
| Stopping service/container with a signal | Whether the JVM receives the signal and has sufficient grace time |
| Async backend queue near capacity | Whether events are blocked/dropped or remain after timeout |
| Unwritable target file | Whether flush failures are detected; how many events are lost |
| Slow or unavailable remote collector | How timeouts, retries, and backpressure behave |
| Multiple hooks coexisting | Whether there are order dependencies or lock-induced deadlocks |
| Forced kill or abrupt power-off | Quantify log loss bounds and compensating mechanisms |

**Hands-on note for the section 3 code:** after running `java ShutdownHookLoggingDemo`, run `java ShutdownHookLoggingDemo verify` **only after the first process has exited**. Reading the file while the first process is still running may show no logs yet, because the buffer is intentionally not flushed until close. Do not treat this as a logger bug; it is the exact behavior used to demonstrate the concept.

To test `SIGKILL`, do so only in an isolated test environment: the expected behavior is that hooks do not run; do not use such a test to conclude that specific log lines will always be lost or always be preserved, as actual outcomes depend on the backend and write timing.

## 10. Common issues and how to fix them

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Final logs lost when JVM exits | Buffered/async queue not flushed or stopped | Check backend lifecycle and drain policy |
| Hook does not run | `SIGKILL`, `halt`, crash, or non-orderly shutdown | Use a controlled stop path; design for potential log loss on abrupt termination |
| Logs still missing even though hook ran | Grace period expired, write destination failed, network unacknowledged, or flush failed | Check timeouts, I/O errors, and acknowledgments |
| Application hangs during shutdown | Hook waits indefinitely, circular lock, or worker never stops | Bound wait times, fix shutdown order, and eliminate deadlocks |
| Logs or exceptions appear while closing logging | Another hook keeps emitting events after the appender closes | Coordinate stopping event production before closing the backend |
| Same handler closed multiple times | Custom hook duplicates framework/JUL shutdown | Assign a single lifecycle owner; make cleanup idempotent |
| No diagnostic output from hook | Logging backend is already closed or no longer accepting events | Do not depend on the logger itself to report errors during cleanup |
| File exists but collector is missing events | Writing to file and forwarding to collector are separate stages | Monitor the pipeline and ingestion acknowledgments |
| Shutdown logs appear out of order | Multiple hooks execute concurrently | Do not rely on hook order; include IDs, timestamps, or context |
| Program prints `main finished` but no file exists yet | Buffer only writes on close during shutdown | Wait for the JVM to exit before inspecting the destination |

## 11. Pre-production checklist

1. Identify the actual logging backend: JUL, Logback, Log4j 2, or another backend.
2. Check whether the backend/framework **already provides a shutdown mechanism**, and avoid duplicate closing.
3. Determine which events are written synchronously and which remain in queues/buffers.
4. Clearly define the sequence: **stop accepting work → finish in-flight work → stop generating logs → drain → flush/close**.
5. Set reasonable timeouts, guard against infinite waits, and test exporter/file failure scenarios.
6. Ensure cleanup can be invoked multiple times without duplicate records or fatal errors.
7. Verify signals, entrypoint behavior, and shutdown time limits in the deployment environment.
8. Distinguish between "handler closed" and "log durably stored at the final destination."
9. Plan for log loss risks during forced kills, crashes, or power failures.
10. Test both normal shutdowns and failure scenarios, measuring actual event loss.

### Self-check questions

**Q1.** `logger.info(...)` returns successfully—is the log line guaranteed to be in the file?  
**A:** No. The data may still be in a buffer or queue.

**Q2.** Why shouldn't you register one hook for the HTTP server and another for logging and assume logging will close after HTTP?  
**A:** The JVM starts hooks in no guaranteed order; they can run concurrently. Use a lifecycle coordinator if ordering is required.

**Q3.** Can a shutdown hook rescue logs when a process receives `SIGKILL`?  
**A:** No. That is not an orderly shutdown; you must plan for data loss prior to the kill.

**Q4.** Does a successful `flush()` always mean logs have reached the central search system?  
**A:** No. You must check what flush means for your specific backend, the network path, and the collector's acknowledgment mechanism.

**Q5.** When a framework already stops logging as part of its lifecycle, should you add a custom hook to call close again?  
**A:** Not by default. Only add one when necessary and when you understand the potential races, ownership, and lifecycle contracts.

**Key takeaway:** Shutdown hooks help clean up logging **when the JVM has an opportunity for an orderly shutdown**. Prefer your framework or backend's built-in shutdown mechanism first, design bounded and idempotent flush/close logic, stop producing events before stopping the writer, and always treat shutdown hooks as *best effort* rather than a zero-loss guarantee.