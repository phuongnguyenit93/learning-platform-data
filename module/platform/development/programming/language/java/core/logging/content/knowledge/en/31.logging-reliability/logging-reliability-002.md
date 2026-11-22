# Duplicate Logging in Java Core Logging

## 1. What Is Duplicate Logging and Why Is It Dangerous?

**Duplicate logging** is the situation where a log event is written or collected multiple times unintentionally. Its impacts include noise during debugging, increased I/O and storage costs, inaccurate incident counts and alerts, as well as the risk of sending data to an inappropriate sink.

Three distinct phenomena need to be differentiated:

1. **One log event becomes multiple copies:** the code calls `logger.error(...)` only once, but the appender/handler receives the event twice due to hierarchical configuration, or the collection pipeline resends the same record.
2. **Multiple events describe one failure:** the repository logs the stack trace and rethrows; the service and controller also log the same exception. There are multiple distinct log calls, but they all refer to a single failure.
3. **Business logic actually runs again:** retries, message redelivery, or scheduler re-execution; these can produce valid log events even if their contents look similar.

Two identical lines are not enough to conclude duplication: two independent requests can encounter the same error. Conversely, three lines with different messages can all be redundant logs for a single failure.

~~~text
12:30:01.123 [worker-1] ERROR Checkout - event=payment_failed orderId=42
12:30:01.123 [worker-1] ERROR Checkout - event=payment_failed orderId=42
~~~

This is a **suspicious sign**. You need to compare the logger, thread, process, `requestId`, `eventId`, and output/collection paths. If an event is intentionally sent to both the console **and** an audit file, two sinks receiving it is not automatically a bug. The bug lies in the same sink receiving it repeatedly or metrics aggregating without distinguishing sources.

## 2. Find the Duplication Layer Before Fixing

Typical pipeline:

~~~text
Business code / library
    |
    v
SLF4J / Log4j API / java.util.logging
    |
    v
Logger level and hierarchy
    |
    +--> Appender/Handler A -> stdout/file
    |
    +--> Appender/Handler B -> stdout/file
                                |
                                v
                       Shipper / collector
                                |
                                v
                     Queue, batch, retry, exporter
                                |
                                v
                       Index / dashboard
~~~

How to isolate the layer:

- **In code:** set a breakpoint at the logger call or use a test appender to check whether one or multiple `LogEvent` instances are emitted.
- **In raw output:** inspect stdout/file of **a single process or pod**. If it is already duplicated there, prioritize checking the logger, appender/handler, and error-logging code.
- **In the collector:** if it appears once locally but twice in the backend, check the receiver, dual stdout/file paths, checkpoints/offsets, retries, and converging exporter routes.
- **In the dashboard:** if raw data is not duplicated but counts look abnormal, check queries that merge multiple indices/sinks or count `ERROR` logs instead of failed requests.
- **In business logic:** if multiple instances emit the same business event due to message redelivery, look for idempotency/retry mechanisms rather than just logging bugs.

Include `requestId`, `jobId`, `attempt`, `logger`, `instanceId`, and `eventId` if the system has a contract for generating per-event IDs. `requestId` typically links **multiple** events of a single request, so it cannot be used as a unique key for deduplication.

## 3. Logback: Additivity Causes an Event to Pass Through the Same Appender Twice

In Logback, loggers form a hierarchy by package/class name. By default, events from a child logger are forwarded to its own appenders **and** its ancestors' appenders; this mechanism is called **additivity**.

~~~text
root (CONSOLE)
    |
    +-- com.example.orders (CONSOLE)
            |
            +-- CheckoutService -> logger.error(...)
~~~

If `CONSOLE` is attached to both `com.example.orders` and `root`, the same event can reach the console twice.

Example of a `logback.xml` that **causes duplicates**:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="DEBUG">
        <appender-ref ref="CONSOLE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

**Default-style fix:** attach `CONSOLE` only at `root`; let the child logger adjust the level without re-attaching the appender:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

The child logger allows `DEBUG` events and forwards them to the root appender via additivity. Root's `INFO` level is not simply re-applied as another level filter to events already permitted by the child logger; an appender's own filter/threshold can still restrict output.

If you want to **separate** a package's logs into a file, you can set `additivity="false"` and attach a dedicated appender:

~~~xml
<!-- Snippet; ORDERS_FILE must be defined in the full configuration. -->
<logger name="com.example.orders" level="DEBUG" additivity="false">
    <appender-ref ref="ORDERS_FILE"/>
</logger>
~~~

Setting `additivity=false` **without a suitable appender** can cause that branch's logs to disappear. Therefore, do not disable additivity on every logger just to hide duplicates. Cases where an event intentionally goes to two **different** sinks should be preserved as designed.

## 4. Log4j 2: AppenderRef on Both Child Logger and Root

Log4j 2 uses `AppenderRef` and defaults `additivity` to `true`. The following `log4j2.xml` configuration has the same `CONSOLE` on both the child logger and root:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level %logger - %msg%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Logger name="com.example.orders" level="debug">
            <AppenderRef ref="CONSOLE"/>
        </Logger>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

There are two correct solutions depending on your goal:

- To use a single shared console: **remove `AppenderRef` from the child logger**, keep the appender only at `Root`, and still configure `level="debug"` if needed.
- To have the child logger write to `CONSOLE` on its own without inheriting from root: set `additivity="false"` on the child **and** keep `AppenderRef` on the child.

Example of the `Loggers` section using the second approach (snippet to replace in the full file):

~~~xml
<Loggers>
    <Logger name="com.example.orders" level="debug" additivity="false">
        <AppenderRef ref="CONSOLE"/>
    </Logger>
    <Root level="info">
        <AppenderRef ref="CONSOLE"/>
    </Root>
</Loggers>
~~~

Also check for **two appenders with different names that write to the same physical destination**. Different appender names do not guarantee that two files/outputs are truly independent. When using an audit file or dedicated appender, map out which events need to go to which destination before changing additivity.

## 5. Java Util Logging (JUL): Child Handler and Parent Handler

In `java.util.logging`, a `Logger` forwards each `LogRecord` to its own handlers; by default it also forwards to parent loggers' handlers via `useParentHandlers=true`. If the same `ConsoleHandler` or custom handler is attached to both child and parent, an event can be received twice.

How to handle it: inspect `getHandlers()` on the child logger and its ancestors; if root already owns the console, you usually do not need to attach the same handler on the child. When a logger has its own output, attach the handler intentionally and only then consider `setUseParentHandlers(false)`. Across the lifecycle, avoid calling `addHandler(...)` repeatedly every time a component initializes; clean up with `removeHandler(...)` and close the handler when no longer needed.

### Complete Java 17 Example

The file **`DuplicateLogDemo.java`** uses only the standard library. It demonstrates **one** event being logged twice when the same handler is attached to both parent and child.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class DuplicateLogDemo {
    private static final class ListHandler extends Handler {
        private final List<String> messages = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                messages.add(record.getMessage());
            }
        }

        @Override
        public void flush() {
            // No I/O to flush.
        }

        @Override
        public void close() {
            // No external resources to close.
        }

        int count() {
            return messages.size();
        }

        void clear() {
            messages.clear();
        }
    }

    public static void main(String[] args) {
        Logger parent = Logger.getLogger("lesson.duplicate");
        Logger child = Logger.getLogger("lesson.duplicate.orders");

        Level originalParentLevel = parent.getLevel();
        Level originalChildLevel = child.getLevel();
        boolean originalParentUse = parent.getUseParentHandlers();
        boolean originalChildUse = child.getUseParentHandlers();

        ListHandler sink = new ListHandler();
        sink.setLevel(Level.ALL);

        parent.setLevel(Level.ALL);
        child.setLevel(Level.ALL);
        parent.setUseParentHandlers(false); // Isolate from root.
        child.setUseParentHandlers(true);   // Allow propagation to parent.
        parent.addHandler(sink);
        child.addHandler(sink);             // Misconfiguration: attached in two places.

        try {
            child.info("event=order_saved eventId=e-1");
            System.out.println("before=" + sink.count());

            child.removeHandler(sink);     // Fix: only parent holds the sink.
            sink.clear();

            child.info("event=order_saved eventId=e-2");
            System.out.println("after=" + sink.count());
        } finally {
            child.removeHandler(sink);
            parent.removeHandler(sink);
            child.setUseParentHandlers(originalChildUse);
            parent.setUseParentHandlers(originalParentUse);
            child.setLevel(originalChildLevel);
            parent.setLevel(originalParentLevel);
            sink.close();
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 DuplicateLogDemo.java
java DuplicateLogDemo
~~~

**Deterministic stdout**:

~~~text
before=2
after=1
~~~

On the first call, `child.info(...)` creates one `LogRecord` that is delivered to `ListHandler` on `child` and then to the same handler on `parent`, yielding `before=2`. After removing the handler from `child`, the second event arrives only through `parent`, yielding `after=1`. `parent.setUseParentHandlers(false)` prevents the machine's default root handler from affecting the result. The `finally` block cleans up the handler and restores the logger configuration. The example runs sequentially for deterministic results; changing logger configuration while multiple threads are active requires lifecycle control.

The double-delivery mechanism through the hierarchy has been verified in JShell with the JDK; the APIs used are Java 17 compatible. The program requires no external logging libraries.

## 6. Logging the Same Exception at Multiple Layers

For example, a service calls a repository, and the repository catches an error, logs it, and rethrows it:

~~~java
// Snippet in Repository:
catch (SQLException e) {
    log.error("database save failed", e);
    throw e;
}

// Snippet in Service:
catch (SQLException e) {
    log.error("checkout failed", e);
    throw e;
}

// Snippet at HTTP boundary:
catch (SQLException e) {
    log.error("request failed", e);
    return errorResponse();
}
~~~

These are **three illustrative snippets**, not a standalone Java program. `log`, `errorResponse()`, and the corresponding `try` blocks are defined by the application. A single root error can generate **three** `LogEvent` instances and three stack traces. If a dashboard counts every `ERROR` line, one failed request can become three "incidents."

It is usually best to choose **one boundary responsible for logging the final error**. Lower layers can throw context-rich exceptions without printing the stack trace again. If a layer records a distinct event such as `retry_scheduled`, log that event separately with `attempt` and an appropriate level.

~~~java
// Service: add context and rethrow without repeating the stack trace.
throw new OrderPersistenceException("orderId=" + orderId, cause);

// Boundary: log the final error once.
log.error("event=checkout_failed orderId={}", orderId, exception);
~~~

The snippet above requires the application's `OrderPersistenceException` class, variables, and logger; it is not a standalone runnable file.

Another form of duplication occurs **within the same event**: code manually concatenates `exception.toString()` or a stack trace into the message and also passes the `Throwable` to the backend; the encoder may print the exception a second time. Pass the exception object according to the logging API and let the backend format the stack trace. Avoid logging the same `Throwable` at every layer just because each layer has a `catch`.

## 7. Retry, Future, and Callbacks: Two Similar Lines Can Be Valid

A logical operation may retry multiple times:

~~~text
event=payment_started orderId=42 attempt=1
event=payment_retry_scheduled orderId=42 attempt=1 reason=timeout
event=payment_started orderId=42 attempt=2
event=payment_succeeded orderId=42 attempt=2
~~~

These are **four events** across two attempts and must not be deduplicated by `orderId` or message alone. With a message broker providing at-least-once delivery, a message can be redelivered if the ACK is not confirmed. If business logic actually executes twice, you must design **idempotency** for the operation; deleting duplicate log entries does not fix a database or payment transaction that was processed twice.

With `ExecutorService.submit()`, exceptions from a task are typically held in the `Future`; a caller invoking `Future.get()` may receive an `ExecutionException`, with the root cause in `getCause()`. If the worker already logged the exception and the caller logs it in full again after `get()`, one failure produces two stack traces. Standardize where errors are logged: in the worker if it is responsible for handling them, or at the point where the result is retrieved if the caller is responsible.

With `CompletableFuture`, `whenComplete`, `handle`, and `exceptionally` callbacks can all observe the same failure. Placing `log.error(...)` in all callbacks without adding new information repeats a single error. Log only at the appropriate boundary and add `attempt` and `outcome` fields when events differ in meaning.

IDs need clear contracts:

| Field | Meaning | Can Be Used as Event Dedup Key? |
| --- | --- | --- |
| `requestId` / `traceId` | Correlates steps within a request/trace | No; each request has multiple events |
| `jobId` / `operationId` | Identifies a logical operation | Not sufficient; there may be multiple attempts |
| `attempt` | Distinguishes an execution/retry attempt | Must be paired with other IDs |
| `eventId` | Unique identifier of the source event, preserved across transport | Yes, if uniqueness and retention are guaranteed |
| `instanceId` / `podId` | Distinguishes the emitting source | Helps investigation, not sufficient alone |

## 8. Duplicate Logs in the Collector or Storage System

If the local console has only one line but the backend has two copies, check:

~~~text
App -> stdout ---> collector A --+
    -> app.log --> collector B --+--> same index

Collector -> send batch -> backend stored -> ACK lost
          -> timeout / retry -> same batch resent
~~~

Common scenarios:

1. The application writes the same event to stdout and a file, and both sources are tailed and ingested together without provenance metadata.
2. Two agents or two collector pipelines read the same file/receiver.
3. A batch is received by the backend, but the sender does not see the ACK, so it **retries** and may re-ingest it.
4. Offsets or file identity are reset after rotation, restart, or backfill, causing part of a file to be re-read.
5. Multiple instances genuinely produce similar events due to message redelivery; distinguish business-level issues from ingestion issues.

OpenTelemetry Collector supports queuing/retrying via certain exporter helpers; behavior depends on the exporter, version, backpressure, and destination. Retries improve delivery reliability during transient failures, but do not automatically guarantee exactly-once ingestion. If the backend supports it, you can use a **stable event ID** and idempotent ingest/deduplication with a well-designed ID retention window. Do not disable retries just to avoid duplicates if doing so risks losing critical logs.

**Do not drop every record with the same text and second-rounded timestamp.** Two real requests can occur within the same second and produce identical messages. When `eventId` is missing, combining timestamp, logger, thread, instance, `requestId`, and exception signature only yields **candidates** for investigation.

## 9. Do SLF4J Providers and Bridges Cause Duplicate Logs?

SLF4J is an API; Logback, Log4j 2, or another provider performs the actual writing. At runtime, there should normally be **one matching SLF4J provider**. A multiple-provider/binding warning is a signal that the classpath needs fixing, though it **does not automatically prove that every event is printed by all providers**; SLF4J has a provider selection mechanism that depends on the version.

Bridges route JUL, Commons Logging, or Log4j API calls to a central backend. Installing an incompatible reverse bridge can cause forwarding loops, initialization failures, or stack overflows. Inspect every component on the runtime classpath:

- Which API emits logs? `org.slf4j.Logger`, `org.apache.logging.log4j.Logger`, or `java.util.logging.Logger`?
- Which backend is active, and which `logback.xml`, `logback-spring.xml`, `log4j2.xml`, or JUL properties file is loaded?
- Use `mvn dependency:tree` or `gradle dependencies --configuration runtimeClasspath` and `dependencyInsight` to find providers/bridges pulled in via transitive dependencies.
- Ensure every source has a clear routing path without bidirectional bridge loops; verify again with a test appender after making changes.

Do not remove logging libraries at random, as a JAR may be a required API, bridge, or backend.

## 10. Testing and Fixing the Root Cause

### Test at the Right Sink

Use an in-memory test handler/appender to count **received records** rather than only mocking the number of logger calls:

1. Emit one event from a child logger and verify the shared console receives **exactly one** when the design requires one.
2. If there is a separate file/audit sink, verify each sink receives the number of events specified by the contract; `additivity=false` must not drop `ERROR`/`AUDIT` logs.
3. Throw an exception across repository -> service -> boundary and verify the stack trace count matches policy.
4. Test retries `attempt=1` and `attempt=2`, keeping both valid events.
5. Test `Future.get()` and `CompletableFuture` callbacks to catch multiple logs of the same failure.
6. Ship stdout/file to the collector and check whether two sources duplicate content in the same index.
7. Simulate batch retries, rotation, restarts, and dual collectors, then verify `eventId` and idempotent ingest state if applicable.
8. With multiple threads, compare IDs/sets of events; do not assert scheduler-dependent log ordering.

### Short Investigation Workflow

1. Pick a suspected duplicate event and record `timestamp`, `logger`, `thread`, `requestId`, `eventId`, `instance`, and source.
2. Count records in the raw log of a single process. If duplicated at the source, inspect the code and logger hierarchy.
3. Check `AppenderRef`/`additivity` in Logback/Log4j 2 or `getHandlers()`/`useParentHandlers` in JUL.
4. If messages differ but represent the same failure, check catch/rethrow, retries, and callbacks.
5. If it appears once locally, check whether the file/stdout is shipped twice, along with receivers/exporters, checkpoints, and retries.
6. Fix in a test environment and measure event counts at each sink; ensure no critical logs are lost.

## 11. "Fixes" That Lose Logs

| Quick Fix | Possible Consequence | Proper Solution |
| --- | --- | --- |
| Raise root level from INFO to ERROR | Hides INFO/DEBUG; two ERRORs still duplicate | Remove the duplicate appender/handler attachment |
| Set `additivity=false` on all child loggers | Branches without an appender lose output | Disable only on branches with a dedicated sink |
| Unconditionally disable console or file | Loses operational/audit output | Map out routing to each sink first |
| Drop records with identical messages | Erroneously merges real requests/attempts | Use an `eventId` contract and business criteria |
| Disable collector retries | Reduces duplicates but increases data loss | Use idempotent ingest and observable retries |
| Remove exception logging at all layers | Loses final failure details | Pick one boundary to log the stack trace |
| Change timestamp pattern/text color | Changes appearance, not event count | Test at the appender/handler |
| Arbitrarily exclude backends/bridges | Breaks framework logging | Analyze the dependency tree |

Two copies in **two different destinations** may be required by design. Do not sum log counts across all sinks as the number of business occurrences when the same event is fanned out to multiple places.

## 12. Distinguishing Duplicate Records from Valid Attempts

~~~text
eventId=e-101 requestId=req-1 attempt=1 event=charge_failed
eventId=e-101 requestId=req-1 attempt=1 event=charge_failed
eventId=e-102 requestId=req-1 attempt=2 event=charge_failed
eventId=e-103 requestId=req-2 attempt=1 event=charge_failed
~~~

If `eventId` is generated uniquely per event at the source and preserved across transport, the two `e-101` lines are duplicate candidates for the same event; `e-102` is a valid retry; `e-103` belongs to a different request. Drawing a final conclusion still depends on the event ID contract and the ingestion source.

~~~text
event=dao_failed requestId=req-1 cause=timeout
event=service_failed requestId=req-1 cause=timeout
event=http_failed requestId=req-1 status=500 cause=timeout
~~~

These are three different events from **one failure chain**. To measure failed requests, count based on `http_failed` or request outcome rather than summing all `ERROR` logs. To measure DB attempts, use `attempt` and the corresponding event.

## 13. Key Takeaways Checklist

- Identify the unit of "duplication": record, log call, failure, request, or attempt.
- Check the local source first, then appenders/handlers, collectors, and dashboards.
- Audit `additivity`, `AppenderRef` attachments, JUL parent handlers, and sinks pointing to the same destination.
- Establish the boundary responsible for logging exceptions and distinguish valid retries.
- Audit SLF4J providers/bridges and avoid forwarding loops.
- Attach `eventId`, `requestId`, `attempt`, and `instance` when needed; understand what each ID means.
- For pipelines with retries, check checkpoints, multiple sources, and ingestion idempotency.
- Test record counts at the sink and ensure `ERROR`/audit logs are preserved after fixes.
- Do not deduplicate by message alone; do not use log deduplication to mask business logic that actually ran twice.

**Principle:** find the **first point where the record count increases** and fix it at that layer. This eliminates unintended copies while preserving logs of genuinely distinct requests, retries, and incidents.

### Official References

- Logback — [Appender additivity and logger configuration](https://logback.qos.ch/manual/configuration-xml.html), [Logger hierarchy](https://logback.qos.ch/manual/architecture.html).
- Apache Log4j 2 — [Configuration and additivity](https://logging.apache.org/log4j/2.x/manual/configuration.html).
- Java SE 17 — [java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html).
- SLF4J — [Provider/binding warnings](https://www.slf4j.org/codes.html), [Manual](https://www.slf4j.org/manual.html).
- OpenTelemetry Collector — [Exporter queue/retry](https://github.com/open-telemetry/opentelemetry-collector/blob/main/exporter/exporterhelper/README.md), [Troubleshooting](https://opentelemetry.io/docs/collector/troubleshooting/).
