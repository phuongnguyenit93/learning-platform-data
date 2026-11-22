# Fallback Appenders in Java Logging

## 1. Goal: When the Primary Log Destination Fails

A Java application may write logs to a file, console, syslog, a log collection service, or a network endpoint. If the primary destination runs out of disk space, loses connectivity, or its appender reports an error, a common solution is a **fallback appender**: routing events that could not be written successfully to a **backup destination**.

Within the scope of this lesson, an **appender** is the log output component of backends such as Logback or Log4j 2; in `java.util.logging` (JUL), the closest equivalent concept is a `Handler`. **Fallback** is the action of processing along a backup branch after detecting a failure in the primary destination. It differs from always writing every log to two destinations.

After this lesson, you will be able to:
- Describe the log path when the primary appender succeeds, reports an error, is retried, or recovers.
- Distinguish between **failover**, **mirroring/dual-write**, **retry**, **buffering**, and **durable spool**.
- Write a standalone Java 17 example with JUL demonstrating routing an event to a backup handler.
- Configure **Log4j 2**'s `FailoverAppender`, understanding the error-propagation requirement from the primary appender and the limitations of this approach.
- Understand why **Logback does not have a universal built-in fallback** for all appenders; choose a custom wrapper or an appropriate log-export architecture.
- Design failure testing, observability, and log-preservation policies instead of merely seeing that "the application did not crash".

## 2. How Does a Fallback Appender Work?

Conceptual path:

```text
                  Log event
                      |
                      v
           Logger / level / filter
                      |
                      v
             Fallback controller
                      |
                 try Primary
                 /         \
             success    error detected
                |             |
                v             v
           Primary sink   Fallback sink
          (file/network)  (console/file/...)
                              |
                         write result
```

**Normal situation:** only the primary receives logs. If the primary **reports an error in a way the failover mechanism can detect**, the controller can route the event to the backup appender, pause attempts to the primary, and retry after an interval. The exact policy depends on the implementation.

**Crucial condition:** a fallback appender **does not automatically know about every failure**. If the primary catches an exception and only prints an internal warning, or if a network client accepts data into a buffer but fails to transmit it downstream, the failover mechanism may still see a "successful" call. If the process crashes before the fallback can run, in-JVM logic has no further chance to rescue the event.

**Do not conflate these concepts:**

| Mechanism | Behavior | Purpose |
| --- | --- | --- |
| Fallback/failover | Switches to the backup destination only after detecting that the primary failed | Maintain log output capability when one sink encounters a failure |
| Dual-write/mirroring | Sends the same event to both destinations under normal conditions | Keep an extra copy or feed two systems |
| Retry | Re-attempts a failed operation to the selected destination | Overcome transient errors; may create duplicate records |
| Buffering/async queue | Holds events in memory and writes them later | Reduce blocking, absorb bursts; risks data loss if the process dies |
| Durable spool/queue | Persists events to durable storage before forwarding | Reduce event loss across restarts according to the deployment contract |

When writing logs related to **audit/compliance** with zero-loss requirements, a standalone fallback is usually **not enough**. You need a durable persistence mechanism with acknowledgements and retry/idempotency rules.

## 3. Failure Modes That Fallback Must Consider

### Failures Detectable at Write Time

Examples:
- The appender opens a file and encounters a write error.
- The connection to a syslog server is refused or the network client throws an exception.
- An application-owned primary component actively marks itself `UNHEALTHY` and rejects incoming events.
- The target destination runs out of quota or hits an authentication error, and that error **is propagated back** to the failover mechanism.

For these cases, fallback can run if the exception or error state reaches the controller and the secondary remains operational.

### Failures Not Easily Detected Immediately

Examples:
- The appender writes to an in-memory buffer and returns success, but the background network worker fails later.
- The OS accepts bytes into the page cache, but the disk or collector has not confirmed persistence.
- UDP sends packets without receiving acknowledgements.
- An `AsyncAppender` accepts an enqueue, but the consumer is blocked or the queue drops events on its own.
- The appender writes a partial record and then throws an exception; it is impossible to tell whether the event on the primary is complete.

This is why fallback **does not mean "exactly-once delivery"**. Log loss or duplicate writes can occur when the primary writes partially and the controller then tries the backup.

## 4. Standalone Java 17 Example: Fallback with a JUL Handler

JUL does not use the name `Appender` for an output target; it uses `Handler`. This example builds a custom `FallbackHandler` wrapping two handlers:
- `PrimaryHandler` prints `PRIMARY ...`, but **intentionally throws an exception** for the message `primary-down`.
- `BackupHandler` prints `FALLBACK ...`.
- The controller catches the primary's failure and forwards the **same `LogRecord`** to the backup.

This is a deterministic failure simulation for learning the behavior without needing to induce a real system fault.

Create the file `FallbackAppenderDemo.java`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class FallbackAppenderDemo {
    private static final class PrimaryHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            if ("primary-down".equals(record.getMessage())) {
                throw new IllegalStateException("simulated primary failure");
            }
            System.out.printf("PRIMARY %s | %s%n",
                    record.getLevel().getName(), record.getMessage());
        }

        @Override
        public void flush() {
            System.out.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }

    private static final class BackupHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            System.out.printf("FALLBACK %s | %s%n",
                    record.getLevel().getName(), record.getMessage());
        }

        @Override
        public void flush() {
            System.out.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }

    private static final class FallbackHandler extends Handler {
        private final Handler primary;
        private final Handler backup;
        private int fallbackCount;

        FallbackHandler(Handler primary, Handler backup) {
            this.primary = primary;
            this.backup = backup;
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            try {
                primary.publish(record);
            } catch (RuntimeException failure) {
                fallbackCount++;
                backup.publish(record);
            }
        }

        int fallbackCount() {
            return fallbackCount;
        }

        @Override
        public void flush() {
            try {
                primary.flush();
            } finally {
                backup.flush();
            }
        }

        @Override
        public void close() {
            try {
                primary.close();
            } finally {
                backup.close();
            }
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lesson.fallback.demo");
        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);

        Handler primary = new PrimaryHandler();
        Handler backup = new BackupHandler();
        primary.setLevel(Level.ALL);
        backup.setLevel(Level.ALL);

        FallbackHandler fallback = new FallbackHandler(primary, backup);
        fallback.setLevel(Level.ALL);
        logger.addHandler(fallback);

        try {
            logger.info("primary-ok");
            logger.warning("primary-down");
            logger.info("primary-restored");
            System.out.println("fallbackCount=" + fallback.fallbackCount());
        } finally {
            logger.removeHandler(fallback);
            fallback.close();
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac FallbackAppenderDemo.java
java FallbackAppenderDemo
```

**Exact stdout** in a fresh JVM, with no JUL configuration other than the `lesson.fallback.demo` namespace:

```text
PRIMARY INFO | primary-ok
FALLBACK WARNING | primary-down
PRIMARY INFO | primary-restored
fallbackCount=1
```

### Explaining the Output

1. `logger.info("primary-ok")` is handled by `PrimaryHandler`, so no fallback occurs.
2. `logger.warning("primary-down")` causes the primary to **throw `IllegalStateException` before printing**. `FallbackHandler` catches the error, increments the counter, and routes the record to the backup.
3. `logger.info("primary-restored")` tries the primary again and succeeds, because this example retries **per event**; it has **no** circuit breaker state or retry cooldown interval.
4. `fallbackCount=1` reflects **the number of times the backup branch was invoked after a primary failure**, not a guarantee that a remote log system durably stored the record.
5. `Logger.setUseParentHandlers(false)` prevents extra output through the default root handler; the handlers write to `System.out` without timestamps, so stdout is deterministic.

**Why does the code only catch `RuntimeException`?** That is just the simplified scope of the example. In a real application, a handler's I/O errors may be caught by the library and reported only via an `ErrorManager` or status manager; in that case, the wrapper never sees an exception and fallback will not trigger. An appender can also fail during `flush()` or `close()` rather than `publish()`. A production failover mechanism must have a clear error-detection contract, handle secondary failures, and enforce proper timeouts and lifecycle management.

**Other limitations:** If `BackupHandler.publish()` also throws an exception, this example lets the error propagate to the caller, which is not a good fault-tolerance policy for most applications. If the primary already wrote the event before throwing an exception, the backup may write a **duplicate**. The counter does not mean "number of logs saved". This sample code is meant to demonstrate the *fallback conditional path*, not to serve as a production logging library.

## 5. Log4j 2: Built-in `FailoverAppender`

Log4j 2 Core supports `FailoverAppender`, allowing you to declare a **primary appender**, a list of **failover appenders**, and a retry interval for the primary. When the primary reports an error through Log4j 2's mechanism, failover can switch to the secondary.

Here is an **illustrative** configuration for a project already using Log4j 2 Core. Save it as `log4j2.xml` on the appropriate classpath, with the target directory and write permissions provisioned for the environment:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <File name="PRIMARY_FILE"
              fileName="logs/primary.log"
              ignoreExceptions="false">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
        </File>

        <Console name="BACKUP_CONSOLE" target="SYSTEM_ERR">
            <PatternLayout pattern="FALLBACK %d{ISO8601} %-5p %c - %m%n"/>
        </Console>

        <Failover name="RESILIENT"
                  primary="PRIMARY_FILE"
                  retryIntervalSeconds="30">
            <Failovers>
                <AppenderRef ref="BACKUP_CONSOLE"/>
            </Failovers>
        </Failover>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="RESILIENT"/>
        </Root>
    </Loggers>
</Configuration>
```

### Why Set `ignoreExceptions="false"`?

The failover mechanism needs to **receive an error signal** from the primary. In Log4j 2, appenders can often catch and report errors internally; for `FailoverAppender` to detect certain failures from the primary, the primary must be configured with `ignoreExceptions="false"`. If the primary swallows the error, the controller may assume the write succeeded and skip the backup.

**Do not attach the backup as a second appender directly under root** if the goal is *to write to the backup only when the primary fails*. When root references both `PRIMARY_FILE` and `BACKUP_CONSOLE`, that is **dual-write**, not conditional failover. In the example XML, root references only `RESILIENT`.

### Component Breakdown

- `PRIMARY_FILE`: the primary destination is `logs/primary.log`.
- `BACKUP_CONSOLE`: when an error observable by the failover mechanism occurs, events are routed to `System.err`. This is an illustrative choice relatively independent of the primary file path, but it is **not durable storage** if `stderr` is not captured and persisted by a collector.
- `RESILIENT`: the name of the coordinating appender, which must be attached to a logger/root so events flow through it.
- `primary="PRIMARY_FILE"`: the name of the primary appender; must reference a declared and validly initialized appender.
- `<Failovers>`: the list of fallback targets under Log4j 2's mechanism. Multiple backups can be configured, but you should verify the failure policy and priority order for your specific version.
- `retryIntervalSeconds="30"`: sets the wait interval between attempts to retry the primary after a failure. This is not a guarantee that the primary recovers in exactly 30 seconds, nor is it a mechanism to replay all logs that went to the backup.
- `Root level="info"`: only events that pass the logging threshold of the root or corresponding logger reach the appender. Failover cannot recover events filtered out earlier.

### Conditions and Limitations

1. Fallback can only trigger when the primary **reports an observable error**. A remote appender that puts bytes into a network buffer and reports success can fail downstream without `FailoverAppender` knowing.
2. **Initialization** errors differ from **runtime** errors. If a file, appender, or configuration fails to initialize from the start, check Log4j 2 startup/status diagnostics. Do not assume all bootstrap failures automatically trigger the same fallback path as runtime failures.
3. `retryIntervalSeconds` does not create a durable queue and does not replay events written to the fallback back to the primary when the primary recovers.
4. If container `stdout`/`stderr` is not collected or gets truncated, the backup can also be lost.
5. If the primary wrote **partially** before reporting an error, resending the event to the backup can create duplicate records. An event ID/sequence and appropriate downstream handling are required if duplicates must be detected.
6. If an `AsyncAppender` or async logger sits in front of the failover controller, pay attention to queue policies, drops, and where errors are detected. A successful enqueue does not guarantee the final sink received the event.

You should not test real failures by manually changing permissions on or deleting active log files in production. Use a test environment, a simulated filesystem, or an appender that can actively emit error signals; verify using status logs and event IDs.

## 6. Logback: Do Not Assume a `FailoverAppender` Like Log4j 2

In Logback Classic/Core, common components include `ConsoleAppender`, `FileAppender`, `RollingFileAppender`, `AsyncAppender`, and filters. However, **do not assume Logback provides a built-in `FailoverAppender` equivalent to Log4j 2 with the same XML tag/name** across versions.

Common alternatives:

- **Custom wrapper appender** that manages primary and backup, with status/error checks, retry/backoff, counters, flush/stop, and failover. You must understand Logback's API/lifecycle and error-reporting strategy; many appenders handle exceptions via the status manager rather than throwing to the caller.
- **Write to the console and let an external collector manage redundancy**. For containers, writing to `stdout`/`stderr` with a durable agent/collector is often simpler than trying to handle every network failure inside the JVM.
- **Controlled dual-write** to two independent appenders: not fallback, but suitable if you accept the cost/duplicates and clearly understand the failure domains.
- **External durable spool/queue** outside the logging pipeline for events with high reliability requirements; suitable when retries across restarts are needed.

### Logback Example: Dual-Write, Not Failover

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/app.log</file>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

In this configuration, **both appenders receive logs from root under normal conditions**. This reduces dependence on a single destination, but it does not perform conditional switching when `FILE` fails. If the real requirement is "console only when the file breaks", you need an appropriate failover component; two `<appender-ref>` entries cannot be called fallback.

**Important note:** `AsyncAppender` is an asynchronous queue, **not** a backup appender. Async configuration can keep producers from waiting on I/O, but it has queue overflow, flush limits, and potential event loss on shutdown. `RollingFileAppender` rotates files according to a rollover policy; it does **not** automatically switch to an independent sink when the filesystem fails.

## 7. Reliable Fallback Architecture: State and Deadlines

A custom failover usually needs state rather than "trying the primary on every event" like the demo:

```text
HEALTHY
  | primary error (clearly reported)
  v
DEGRADED / FALLBACK_ACTIVE
  | new logs -> backup
  | measure errors, cap capacity, schedule primary checks
  v
PROBING_PRIMARY
  |-- probe fails    --> FALLBACK_ACTIVE (backoff)
  |-- probe succeeds --> HEALTHY
```

This is similar to a circuit breaker, with several considerations:
- **Do not spam a failing primary:** trying on every event while the primary is down can spike latency/CPU and generate a flood of exceptions. Use backoff, a retry interval, or an appropriate circuit breaker.
- **Do not treat a probe as a delivery guarantee:** a successful probe does not mean the collector persisted all previous events.
- **Concurrency:** multiple threads can emit logs concurrently. State transitions must be thread-safe, avoiding lock contention or blocking operations on the logging hot path.
- **Timeouts:** a hanging network sink is often just as dangerous as one throwing exceptions. If the primary blocks indefinitely, fallback will never be attempted. Enforce finite timeouts at the client/transport layer for the technology in use.
- **Fallback capacity:** a backup file can fill up; a `stdout` pipe can block; an in-memory queue can overflow. Measure backlog, dropped events, and deadlines.
- **Recovery semantics:** when the primary returns, new logs can go back to the primary, but logs sent to the backup do not move automatically. To unify them, you need a read/replay process and downstream duplicate handling.
- **Shutdown:** when the appender/queue still holds events, drain, flush, and close primary/backup following the proper lifecycle. In containers, the shutdown deadline must fit within the termination grace period.

A good controller should clearly define when an event is considered **accepted**, **emitted**, **persisted**, or **acknowledged**. Do not use a generic `success` label for all states.

## 8. Which Fallback Destination Should You Choose?

No single option fits every environment. Compare failure domains:

| Primary | Possible Backup | Advantages | Key Risks |
| --- | --- | --- | --- |
| Remote TCP/HTTP appender | Local rolling file | Can retain logs during network outages | Disk full, no automatic replay after restart, permissions/rotation |
| Local file | Console `stderr` | Separate from file path; easy for container runtimes to collect | Console is not durable without a log collector |
| Remote collector A | Independent collector B | Off-host redundancy | Cost, retries, quotas, authentication, and correlated failures |
| Log exporter/agent | Durable local spool | Can support retransmission | Operational complexity, disk capacity, deduplication |
| Shared network storage | File on the same mount | Simple configuration | **No** failure isolation if the mount fails |

**Failure domain** matters: if primary and backup share a disk that is full, configuring two files does not let writing continue. Two collectors sharing the same credentials/token or the same gateway can also fail together.

In containers, sending application logs to `stdout`/`stderr` and letting the platform collect them is often sensible, but you must verify retention, backpressure, and concrete durability guarantees. A backup is not safe just because its name includes "backup".

**Security:** data in the backup needs the same protection as the primary: avoid logging tokens, passwords, personal data, connection strings, or sensitive payloads. Falling back to `stdout` may expose data to places with different access controls than the primary file.

## 9. Fallback, Event Ordering, and Integrity

While the primary is failing, some events go to the backup; after the primary recovers, new events return to the primary:

```text
T1: order-created      -> PRIMARY
T2: order-paid         -> BACKUP
T3: order-confirmed    -> BACKUP
T4: order-completed    -> PRIMARY
```

If you only inspect the primary, the business event sequence is broken. You must merge/query **both destinations** to follow the full trace. Timestamps and `event_id`/`trace_id` help correlate records, though timestamps do not necessarily guarantee strict ordering across threads or hosts.

Key issues:

1. **Ordering:** events passing through two independent sinks can be emitted or collected out of order; async queues further complicate observed ordering.
2. **Duplicates:** the primary writes an event and then throws an exception in a later step; the backup writes a duplicate copy.
3. **Loss:** both primary and backup can fail, a queue can overflow, or the process can die before flushing.
4. **Replay:** moving backup data back to the primary after recovery requires a dedicated tool or spool/replay mechanism; a typical `FailoverAppender` is not a message broker.
5. **Durability:** a successful file flush or socket write is not equivalent to a collector acknowledging durable storage.

If you need logs with evidentiary/audit value, the design requires explicit contracts for at-least-once delivery, deduplication, ordering, and idempotency. For critical transactions, events should be recorded in an appropriate durable storage mechanism.

## 10. Failure Detection and Avoiding Logging Loops

A classic design bug is calling **the same failing logger** inside a logging error handler:

```text
Primary appender fails
      |
      v
Error handler calls logger.error(...)
      |
      v
Same primary appender fails again
      |
      +----> recursion / stack overflow / log storm
```

Never log appender errors back through the same failing appender path. Better approaches:
- Metrics such as `primary_write_failures_total`, `failover_events_total`, and `fallback_write_failures_total`.
- An **independent** status logger or internal diagnostics channel of the logging backend.
- A minimal error channel such as `System.err` when appropriate, with **rate limiting** and no loop back into the same pipeline.
- Health status and alerts when fallback stays active for too long or approaches capacity.

Metrics should answer: when did the primary start failing, how many events went through fallback, is the backup still writable, are logs being dropped, and has the primary recovered?

"No exceptions in business code" **does not prove** the pipeline is healthy. Many appenders intentionally catch errors to avoid breaking business flows. Monitor status/error counters and the final sinks.

## 11. Intentional Testing

| Scenario | Expected Outcome to Verify |
| --- | --- |
| Primary healthy | Events go to primary; fallback receives none if using conditional failover |
| Primary throws before writing | Event routes to backup; failover counter increments |
| Primary writes partially then throws | Check for duplicates; do not claim exactly-once |
| Primary times out / blocks | Enforces deadline; fallback runs only if error/timeout reporting works |
| Primary reports internal error without throwing | Verify the failover controller **actually** receives the error signal |
| Primary missing at startup | Check diagnostics and appender initialization; do not assume runtime failover behavior |
| Backup also fails | Applies proper drop/alert/stop policy without recursive logging |
| Primary recovers | New logs switch back per retry policy; old backup logs do not auto-replay |
| Multiple concurrent producers | No failover state races, no deadlocks, accurate event counts |
| Queue full / async | Backpressure/drops can happen before the controller; measure accepted vs. emitted |
| JVM shutdown / `SIGTERM` | Drains/flushes within deadline; forced kill is not guaranteed |
| Fallback disk full | Triggers capacity alerts, rotation/retention, and defined policy |

### Log4j 2 Integration Test Procedure

1. Verify the process actually uses Log4j 2 Core, loads the intended `log4j2.xml`, and that `RESILIENT` is referenced by root/logger.
2. Log a probe with a unique ID, e.g., `FALLBACK_PROBE_001`, while the primary is healthy. Verify it appears only in the primary (when configured for conditional failover).
3. In a test environment, simulate the primary appender **throwing an error observable by `FailoverAppender`**; do not break a production filesystem. Log another test event, e.g., `FALLBACK_PROBE_002`.
4. Check backup `stderr`/collector for event `002`. Inspect diagnostics and metrics, confirming no unexpected exceptions leaked into business logic.
5. Restore the primary, wait for the configured retry interval, and log `FALLBACK_PROBE_003`. Verify the new event goes to the primary; observe where `002` remains stored.
6. Also test backup failure and shutdown scenarios. Compare emitted/dropped event counts instead of merely checking that "the application is still running".

Depending on the appender, errors may surface at startup, during `append`, `flush`, `close`, or in a background worker. Test conclusions must state the **specific failure mode simulated** and the backend version. Testing "missing directory for a file" does not by itself prove runtime write failover.

## 12. Common Mistakes

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| Attaching PRIMARY and BACKUP directly to root and calling it fallback | Both appenders may write every event | Use a failover controller or call it dual-write accurately |
| Primary swallows errors | Failover controller cannot detect the failure | Configure error propagation/status for the backend; in Log4j 2 check `ignoreExceptions` |
| Checking only for exceptions in the caller | Appenders may report errors internally or asynchronously | Check internal status, metrics, and final sinks |
| Using the same disk for both files | Disk full breaks both primary and backup | Choose separate failure domains |
| Assuming backup console is durable | Container/logging agent may drop lines | Verify retention/collector or use a durable spool |
| Retrying every event when primary is down | Log storms, high CPU/latency | Use backoff and retry limits / circuit breaker |
| Logging errors back into the same pipeline | Recursion and deadlock | Use an independent status channel with rate limiting |
| Switching to backup and forgetting to read it | Breaks event-sequence observability | Collect from both sinks and attach event IDs |
| Treating fallback as exactly-once | Duplicates or loss can occur | Define delivery semantics and idempotency |
| Treating successful enqueue as successful write | Queue/worker can fail later | Track emitted/ack metrics, flush/shutdown |
| Using Logback as if `<Failover>` XML exists by default | Config may be invalid or ignored | Use the API/extensions appropriate for the backend |
| Testing failures by deleting production files | Can corrupt live log streams and existing data | Use controlled fault injection in staging |

## 13. Choosing Based on Reliability Requirements

**If the goal is "the service must not slow down or fail when the log backend is disrupted":** consider an async appender with deadlines, local/console fallback, metrics, and an explicit drop policy. Accept that some logs may be lost under overload or crash.

**If the goal is "error logs always have a minimal observation path":** falling back to `stderr` can help when file/remote sinks break, provided the runtime/container collects `stderr` and the data is non-sensitive.

**If the goal is "never lose critical business events":** use a durable queue/outbox/transactional storage with dedicated acknowledgement and replay mechanisms. Logging is an observability channel, not a transactional database by default.

**If the application uses Log4j 2:** evaluate `FailoverAppender`, configure `ignoreExceptions="false"` on the primary, and run realistic fault-injection tests.

**If the application uses Logback or JUL:** use the appropriate API/architecture rather than assuming appender names are interchangeable across backends. If writing a custom wrapper, handle synchronization, primary/secondary errors, shutdown, retries, telemetry, payload limits, and resources.

## 14. Pre-Production Checklist

1. Identified the logging backend and the version **actually running**.
2. Identified the primary, backup, and the **failure domain** of each destination.
3. Verified that **error signals** from the primary reach the failover controller.
4. Documented fallback trigger conditions, retry intervals, and recovery criteria.
5. Tested runtime failures, initialization failures, timeouts, and secondary failures.
6. Set up metrics/alerts for primary failures, active fallback, dropped events, and backup capacity.
7. Defined shutdown deadlines, flush/close behavior, and a plan for forced process kills.
8. Established a way to query logs in both primary and backup without losing event sequences.
9. Classified sensitive data and applied the same security/retention policies to the backup.
10. Agreed on durability requirements: best-effort, at-least-once with duplicates, or events persisted durably by another system.

**Conclusion:** A fallback appender improves **the ability to maintain a log output path** when the primary reports an error, but it does not provide an absolute guarantee that "every log will be saved". A sound design must detect real failures, place backups in a separate failure domain, observe failover activity, handle timeouts/retries, and test all failure branches. When reliability beyond best-effort is required, add a durable queue and destination acknowledgements.
