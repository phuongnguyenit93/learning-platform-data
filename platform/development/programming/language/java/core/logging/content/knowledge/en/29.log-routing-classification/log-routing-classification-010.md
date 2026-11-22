# Testing Routing in Java Core Logging

## Objectives

This lesson belongs to the **Routing and Classification** group, focusing on **Testing Routing**. After this lesson, you will be able to read a logging configuration to predict which events go to which appender/sink, design a routing test case matrix covering both expected-inclusion and expected-exclusion cases, write a Java 17 program to self-test log routes, and verify the path from the application to a log collector or search system.

**Routing** is the decision to send a log event to one or more processing destinations based on attributes such as logger name, level, marker, event type, or context. For example: normal business logs to stdout, application errors to an error file, and audit events to an audit sink. **Testing routing** means proving those rules work correctly, even when context is missing, under multithreading, overload, or sink failures.

A complete routing test must include both **positive assertions** (the right event appears in the right place) and **negative assertions** (the event does not appear where it is not allowed). Simply seeing a log line in the console is not enough to conclude that the entire routing setup is correct.

## 1. Understanding the Layers That Determine Log Paths

A typical Java system has multiple points that influence the outcome:

```text
Application / library log call
          |
          v
Logger isEnabled / effective level
          |
          v
Logger filter, event creation, context capture
          |
          v
Appender references + additivity / routing rules
          |
          +----> Console appender ----> container stdout ----> log agent ----+
          |                                                                |
          +----> File appender ------> file/rotation -----> file shipper ---+--> collector --> parser/index --> search
          |                                                                |
          +----> Audit appender -----> audit destination -------------------+
          |
          +----> Async queue/worker (if configured on the appropriate route)
```

This is a conceptual diagram and does not assert that every logging framework processes events in the exact same physical order. In some configurations, filtering happens before event creation; in others, filters are attached to appenders or queues. When debugging, rely on the framework and configuration **actually running**, not just an XML/YAML file that looks right.

Key concepts:

| Component | Function | What to check |
| --- | --- | --- |
| **Logger** | Entry point where the application calls logging, usually named by class/package | Are the logger name and effective level correct? |
| **Log level** | Determines which severity levels proceed further | Is `DEBUG` dropped at the source? Are `WARN`/`ERROR` retained? |
| **Filter** | Accepts, denies, or passes an event based on conditions | Does the rule live on the logger, appender, or collector? Does it drop the wrong events? |
| **Appender/Handler** | Writes events to console, file, network, or other destinations | Does the event reach the right sink and get encoded successfully? |
| **Additivity / parent handlers** | Allows events to propagate up to parent/root loggers | Does it cause duplicate events or route sensitive logs to the wrong path? |
| **Routing key** | Level, logger, marker, MDC/ThreadContext, or event code used to select a path | Does the key come from a trusted source? Is there a fallback when missing or invalid? |
| **Async queue** | Decouples producers from writers | Is successful enqueuing mistaken for confirmed delivery to the destination? |
| **Collector / index** | Receives, processes, stores, and makes logs queryable | Did an event reach the appender only to be dropped later in the pipeline? |

**Routing differs from filtering:** routing selects destinations; filtering decides whether an event continues along a route. An event can be intentionally **fanned out** to two sinks; another event should appear in only one sink. Every test must clearly specify which cases are **exclusive routes** and which are **fan-out** (one-to-many).

## 2. Writing Explicit Routing Rules Before Testing

Consider a checkout service with three routes:

- **CONSOLE**: application logs at `INFO` or `WARN` collected by the container agent.
- **ERROR_FILE**: application logs at `ERROR` for investigation.
- **AUDIT**: logs from the `com.example.audit` logger sent to a dedicated audit destination, bypassing the default application appenders.

Here we **intentionally design each event to follow only one route**. This is an illustrative policy, not a mandatory pattern for every system. Another system might want `ERROR` written to both console and file, or send audit events to an additional security pipeline.

Based on this policy, create an expectation matrix:

| ID | Source Logger | Level | Event Code | CONSOLE | ERROR_FILE | AUDIT |
| --- | --- | --- | --- | :---: | :---: | :---: |
| R1 | `com.example.checkout.OrderService` | `DEBUG` | `cache.detail` | No | No | No |
| R2 | `com.example.checkout.OrderService` | `INFO` | `order.created` | Yes | No | No |
| R3 | `com.example.checkout.PaymentClient` | `WARN` | `payment.retry` | Yes | No | No |
| R4 | `com.example.checkout.PaymentClient` | `ERROR` | `payment.failed` | No | Yes | No |
| R5 | `com.example.audit.AccessAudit` | `INFO` | `role.changed` | No | No | Yes |
| R6 | `com.example.audit.AccessAudit` | `ERROR` | `access.denied` | No | No | Yes |

Check all of the following simultaneously:

1. **Present in the right place:** for example, R4 has exactly one record in `ERROR_FILE`.
2. **Absent from the wrong places:** R4 must not be duplicated in `CONSOLE`, and R5 must not leak into application error logs.
3. **Count:** exclusive routing expects each event to be stored once in the target route, while R1 expects 0. With intentional fan-out, the expected copy count may be greater than 1.
4. **Content:** log level, event code, timestamp, service, environment, trace ID, or audit context are not lost or corrupted.
5. **Timing:** with async logging or a collector/index, logs may arrive later; tests should use an explicit wait deadline rather than checking immediately and declaring failure.

Do not treat log level as the sole way to distinguish audit events. An audit event may be at `INFO` or `ERROR` and still must go to the audit route according to classification rules. If compliance events require separate durability guarantees, the destination and storage mechanism must meet those requirements; in-memory async queues or local files do not automatically guarantee audit durability.

## 3. Identifying an Event for Testing

To avoid mixing up logs from concurrent runs, each test event should have a **unique identifier** generated by the test, such as `test_event_id=route-test-20261110-7b2c`. Use the same ID in the source event and in sink queries.

Distinguish between:

- `test_event_id`: identifies **one** specific test event; used to count occurrences.
- `trace_id`: groups multiple related spans/logs of the **same trace**; not unique per log event.
- `request_id`: can group logs of a single request; one request has many events.
- `event_code`: classifies the event type, such as `payment.failed`; thousands of events can share the same code.

Illustrative JSON log example for post-routing comparison:

```json
{
  "timestamp": "2026-11-10T02:00:00.000Z",
  "level": "ERROR",
  "service": "checkout",
  "environment": "staging",
  "logger": "com.example.checkout.PaymentClient",
  "event": "payment.failed",
  "test_event_id": "route-test-20261110-7b2c",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

The values in this JSON are **illustrative**, not Java's default output. If production uses a schema like `event.code` or `service.name`, use those exact field names in tests. Testing with a unique event ID also helps detect unexpected duplicates when two appenders push to the same index.

**Do not use real customer data or secrets as test payloads.** For sensitive-routing tests, use synthetic events without PII that still include all fields needed to prove the policy.

## 4. Four Essential Types of Routing Tests

### 4.1. Unit Tests for Routing Decision Logic

Encapsulate the routing policy in a class/function with clear inputs: logger, level, event code, marker, and context. The output can be the set of allowed routes, such as `{CONSOLE}`, `{ERROR_FILE}`, or `{AUDIT}`.

Test cases must cover rule **boundaries**: `DEBUG` just below the threshold, `INFO` at the threshold; `ERROR` instead of `WARN`; audit and application loggers with similar names; empty, unknown, or unusual-character routing keys. A test that only sends "happy path" events is insufficient.

Do not assume that returning `route = AUDIT` means the event has been durably stored. Unit tests only prove the routing decision function.

### 4.2. Tests Against the Actual Logging Framework

Initialize the corresponding Logback/Log4j 2/JUL configuration in tests and attach controllable appenders/handlers, such as an in-memory buffer. Emit the events from matrix R1–R6, and verify **exact target lists** with no unintended duplicates. With Logback, you can use `ListAppender` to capture `ILoggingEvent` in tests that include framework dependencies; with JUL, you can create a custom `Handler` as shown in the runnable example below.

Pay attention to **logger hierarchy**, root level, appender references, filters, and additivity. A standalone routing function can be correct while the framework configuration still misroutes events because a rule is overridden or events propagate up to the root logger.

### 4.3. Integration Tests Through Real Sinks

Test through console/file or a staging collector to catch issues invisible to in-memory tests: file permissions, mount paths, JSON encoders, rotation/rolling policies, network errors, timeouts, buffering, sidecars/agents, and config maps. For file appenders, verify events reach the right file and do not appear in others; use dedicated test filenames or scoped cleanup to avoid colliding with live operational logs.

### 4.4. End-to-End Tests on the Log Backend

After emitting an event with `test_event_id`, search in the **correct index/namespace/source name** and time range. For async/indexing pipelines, poll repeatedly with a bounded timeout and reasonable interval. Proving an event reached the sink does not mean it reached the backend; also verify parsers, transport, collector routing rules, retention, and access permissions.

For audit/security logs, also verify who is **not allowed to read** those logs, not just where they are stored. An audit record written to the right sink but copied to a public console still violates policy.

## 5. Standalone Java 17: Self-Testing Log Routing

This example uses **JDK 17+** without SLF4J, Logback, or Spring Boot. It defines three `Handler` instances as in-memory mock sinks:

- `console` receives `INFO` and `WARNING` from the application logger.
- `error` receives `SEVERE` from the application logger.
- `audit` receives all levels from the audit logger configured in the example.

JUL uses `WARNING` and `SEVERE` instead of the `WARN`/`ERROR` names commonly seen in SLF4J. The handlers here simply **collect event lists** for verification and print them after emission completes, making the ordering and stdout deterministic. The example verifies both level-filtered events (`FINE`) and that audit events do not leak into application appenders.

Create the file **`RoutingCheckDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Predicate;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RoutingCheckDemo {
    private static final class RouteHandler extends Handler {
        private final String route;
        private final Predicate<LogRecord> condition;
        private final List<String> events = new ArrayList<>();

        RouteHandler(String route, Predicate<LogRecord> condition) {
            this.route = route;
            this.condition = condition;
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record) || !condition.test(record)) {
                return;
            }
            events.add("route=" + route
                    + " level=" + record.getLevel().getName()
                    + " event=" + record.getMessage());
        }

        @Override
        public void flush() {
        }

        @Override
        public void close() {
        }

        List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    private static void expect(String name,
                               List<String> actual,
                               List<String> expected) {
        if (!actual.equals(expected)) {
            throw new IllegalStateException(name
                    + " expected=" + expected + " actual=" + actual);
        }
    }

    public static void main(String[] args) {
        Logger application = Logger.getLogger("demo.routing.application");
        Logger audit = Logger.getLogger("demo.routing.audit");

        application.setUseParentHandlers(false);
        audit.setUseParentHandlers(false);
        application.setLevel(Level.INFO);
        audit.setLevel(Level.ALL);

        RouteHandler console = new RouteHandler("console",
                record -> record.getLevel().intValue()
                        >= Level.INFO.intValue()
                        && record.getLevel().intValue()
                        < Level.SEVERE.intValue());
        RouteHandler error = new RouteHandler("error",
                record -> record.getLevel().intValue()
                        >= Level.SEVERE.intValue());
        RouteHandler auditRoute = new RouteHandler("audit",
                record -> true);

        application.addHandler(console);
        application.addHandler(error);
        audit.addHandler(auditRoute);

        try {
            application.fine("query-detail");
            application.info("request-ok");
            application.warning("retry-scheduled");
            application.severe("payment-failed");
            audit.info("permission-changed");
            audit.severe("access-denied");

            expect("console", console.snapshot(), List.of(
                    "route=console level=INFO event=request-ok",
                    "route=console level=WARNING event=retry-scheduled"));
            expect("error", error.snapshot(), List.of(
                    "route=error level=SEVERE event=payment-failed"));
            expect("audit", auditRoute.snapshot(), List.of(
                    "route=audit level=INFO event=permission-changed",
                    "route=audit level=SEVERE event=access-denied"));

            if (application.isLoggable(Level.FINE)) {
                throw new IllegalStateException("FINE must be disabled");
            }

            console.snapshot().forEach(System.out::println);
            error.snapshot().forEach(System.out::println);
            auditRoute.snapshot().forEach(System.out::println);

            System.out.println("console_count=" + console.snapshot().size());
            System.out.println("error_count=" + error.snapshot().size());
            System.out.println("audit_count=" + auditRoute.snapshot().size());
            System.out.println("fine_enabled="
                    + application.isLoggable(Level.FINE));
            System.out.println("routing_test=PASS");
        } finally {
            application.removeHandler(console);
            application.removeHandler(error);
            audit.removeHandler(auditRoute);
            console.close();
            error.close();
            auditRoute.close();
        }
    }
}
```

Compile and run:

```bash
javac RoutingCheckDemo.java
java RoutingCheckDemo
```

**Exact stdout** of the program:

```text
route=console level=INFO event=request-ok
route=console level=WARNING event=retry-scheduled
route=error level=SEVERE event=payment-failed
route=audit level=INFO event=permission-changed
route=audit level=SEVERE event=access-denied
console_count=2
error_count=1
audit_count=2
fine_enabled=false
routing_test=PASS
```

Why is the output deterministic?

1. `application.setLevel(Level.INFO)` causes `FINE query-detail` to be dropped at the logger before reaching any `Handler`.
2. `console` checks levels from `INFO` up to below `SEVERE`; `error` only accepts `SEVERE` and above. The two conditions do not overlap for the emitted events.
3. The audit logger has its own `Handler` and does not attach the console/error handlers. `setUseParentHandlers(false)` prevents events from propagating to parent/root handlers and causing duplicates or unintended routes.
4. `expect` compares **both content and count** of each list; only when there are no discrepancies does it print `routing_test=PASS`.
5. Calls are executed sequentially on a single thread, and handlers write only to memory. In an async or multithreaded system, you need synchronization for test data and drain waits; never assume sink order matches emission order.

**Experiment:** change the `console` condition to `record -> true` and rerun. The `payment-failed` event will appear in both `console` and `error` lists; `expect("console", ...)` will throw `IllegalStateException`. This is a **regression test for exclusive routing**, catching misrouted duplicates rather than merely asserting that the error record exists in the error file.

Another experiment is removing `application.setUseParentHandlers(false)`: the application may emit additional output from parent/root handlers depending on the runtime JUL configuration. Because the program above tests via internal handlers, it cannot automatically detect every duplicate from external handlers; testing the real path requires observing stdout/files and other appenders/handlers in the test environment.

## 6. Testing Routing with SLF4J + Logback

An application using SLF4J and Logback can route by **logger name** and **level** using appenders and filters. Below is an illustrative **`logback.xml`** implementing the three routes from matrix R1–R6; compatible SLF4J/Logback libraries are required on the classpath. The files `logs/application-error.log` and `logs/audit.log` must be in a location where the process has write permissions.

```xml
<configuration>
    <appender name="APP_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>ERROR</level>
            <onMatch>DENY</onMatch>
            <onMismatch>NEUTRAL</onMismatch>
        </filter>
        <encoder>
            <pattern>%d{ISO8601} %-5level logger=%logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="APP_ERROR"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/application-error.log</file>
        <append>true</append>
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>ERROR</level>
        </filter>
        <encoder>
            <pattern>%d{ISO8601} %-5level logger=%logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="AUDIT_FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/audit.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level logger=%logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.audit"
            level="INFO" additivity="false">
        <appender-ref ref="AUDIT_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="APP_CONSOLE"/>
        <appender-ref ref="APP_ERROR"/>
    </root>
</configuration>
```

Read this configuration in two groups:

- Application loggers inherit `root=INFO`: `DEBUG` is dropped; `INFO`/`WARN` go to `APP_CONSOLE` because the console filter only `DENY`s exact `ERROR`; `ERROR` goes to `APP_ERROR` via `ThresholdFilter` while being denied by the console filter.
- `com.example.audit` and its child loggers inherit their own rule, level `INFO`, `additivity=false`: events do not propagate to `root`, so they only reach `AUDIT_FILE` in this configuration. Audit `ERROR` events also go only to the audit file, **not automatically to `application-error.log`**.
- If audit events **also** need to appear in the error file, configure intentional, properly scoped fan-out, update the expectation matrix, and verify access permissions for each sink. Do not blindly enable additivity as a substitute for explicit route design.

**Testing an actual Logback configuration:**

1. Run the test with the intended backend/configuration; verify the config file is actually loaded and not overridden by `logging.config`, an environment profile, or another backend dependency.
2. Call logger `com.example.checkout.OrderService` at `DEBUG`, `INFO`, `WARN`, and `ERROR`; tag each event with a unique test ID.
3. Call `com.example.audit.AccessAudit` at `INFO` and `ERROR`.
4. Count events in console, `application-error.log`, and `audit.log`; compare against matrix R1–R6, including verifying **absence from wrong sinks**.
5. Check duplicate line counts when parent/additivity and appender refs change. If files already contain old logs, filter by `test_event_id` or use a dedicated file for the test run.
6. When production uses a JSON encoder, verify field parsing and index mapping; the XML example only uses a text pattern to illustrate routing.

In automated tests with Logback dependencies, `ch.qos.logback.core.read.ListAppender` can capture events from an appender for assertions, but it only proves an event passed through a Logback route. Verifying files, stdout, or collectors requires additional integration/end-to-end tests. In Logback, regular appender filters return `DENY`/`NEUTRAL`/`ACCEPT`; returning `ACCEPT` in one filter does not bypass filters at other layers.

### When Routing Does Not Depend Solely on Level

A service can route by marker, event type, or context such as `MDC["log_route"]`. For example:

```text
if logger startsWith "com.example.audit":
    route = AUDIT
else if level >= ERROR:
    route = ERROR_FILE
else:
    route = CONSOLE
```

This is **policy pseudocode**, not Logback configuration syntax. Condition order matters: placing the `level >= ERROR` branch before the audit branch can send an audit `ERROR` down the wrong route. If routing depends on MDC, test missing context, invalid context, thread handoffs, and stale context left over in thread pools.

Logback provides `SiftingAppender` to select appenders based on a discriminator such as an MDC value. This can create separate appenders per route value; you must bound the number of routes, file paths, and appender lifecycle. Never use untrusted request IDs directly as part of a file path or destination name, as this can cause high cardinality, create too many files, or leak data across user groups. For a problem with only three fixed routes, logger names and appender filters are usually easier to verify than complex dynamic routing configurations.

## 7. Log4j 2: Testing LoggerConfig, RoutingAppender, and Filters

Log4j 2 has layers including logger, `LoggerConfig`, `AppenderRef`, and appender. Filters can return `ACCEPT`, `DENY`, or `NEUTRAL`, and their effect depends on the evaluation stage. An event `DENY`ed at an earlier stage will not reach downstream routes; `ACCEPT` at one layer does not automatically prove every appender will receive the event.

`RoutingAppender` is an option when selecting an appender by a routing key. Below is an illustrative snippet; in a real project, use the exact XML and plugins matching your Log4j 2 version:

```xml
<Routing name="Classified">
    <Routes pattern="$${ctx:log_route}">
        <Route key="audit" ref="AuditFile"/>
        <Route key="error" ref="ErrorFile"/>
        <Route ref="MainConsole"/>
    </Routes>
</Routing>
```

This is a **configuration snippet**, not a complete `log4j2.xml`: it requires appenders named `AuditFile`, `ErrorFile`, and `MainConsole` to be defined, a logger referencing `Classified`, and compatible logging dependencies. In Log4j 2 XML, `$${ctx:log_route}` is a per-event context lookup in the `Routes` pattern; verify interpolation syntax for your specific version before deploying.

Illustrative test policy:

| `log_route` in ThreadContext | Expected |
| --- | --- |
| `audit` | Only to `AuditFile` |
| `error` | Only to `ErrorFile` |
| Missing or non-matching value | Follows configured default route (e.g., `MainConsole`) |
| Unusual characters or unapproved value | Does not create arbitrary sinks; applies controlled fallback |

Also check the effective logger level: if the caller is already filtered out by level, even a valid routing key will not make the event appear. `ThreadContext` in Log4j 2 is typically bound to the current execution context; for executor/async propagation, use appropriate framework integration or wrappers. Clean/restore context in `finally` so subsequent requests are not misrouted.

With dynamic routing by tenant/service, pay attention to maximum route count, appender lifecycle, memory/file-handle limits, permissions, and default values. Test load and security alongside correctness; tenant A's logs landing in tenant B's sink is far more dangerous than a normal event being duplicated.

## 8. Routing by MDC, Markers, and Classification Metadata

MDC (Mapped Diagnostic Context) attaches metadata to events, such as `trace_id`, `environment`, `tenant_group`, or `log_route`. **MDC is not an authorization system**, and its values may originate from untrusted input. When routing based on MDC:

1. Set values through a controlled mapping/validation layer using an allowlist of routes rather than letting clients pick sink names directly.
2. Define handling for empty, null, invalid keys, or missing traces.
3. Test handoffs across `ExecutorService`/`CompletableFuture`: context does not propagate automatically in all cases.
4. Clean and restore MDC/ThreadContext when a request finishes, especially in thread pools.
5. Verify that async appenders capture context into the event at the right moment; log worker threads must not read the background thread's own MDC by mistake.
6. If routing changes on retries or across async boundaries, test each case's logic rather than inferring from main-thread logs.

**Markers** allow classifying events with stable semantics, such as `AUDIT`, `SECURITY`, or `BUSINESS`. Markers or event codes are generally better than parsing substrings from message text. However, a marker named `AUDIT` does not automatically turn an event into a durable audit log; appenders, sinks, and policies still must be proven through testing.

If routing requires separating `environment=staging` and `production`, test both to prevent index cross-contamination. A log tagged `environment=staging` that lands in the production index is still a routing failure. Displaying the right field and writing to the right path are two independent assertions.

## 9. Additivity and Causes of Duplicate Logs

In many logging frameworks, logger names form a parent-child hierarchy. For example, `com.example.payment.Client` has ancestors `com.example.payment`, `com.example`, and `root`. If a child logger has its own appender while still propagating events upward, an event can be written by **both the child's appender and root**.

In Logback:

```xml
<logger name="com.example.payment"
        level="INFO"
        additivity="false">
    <appender-ref ref="PAYMENT_FILE"/>
</logger>
```

This is a configuration fragment; `PAYMENT_FILE` must be defined in the real configuration. When `additivity=false`, events do not propagate to ancestor loggers' appenders. However, if the same appender is referenced multiple times elsewhere, or if the collector ingests data from multiple overlapping sources, duplicates can still appear in the pipeline. Test this using `test_event_id`.

In JUL, `Logger.setUseParentHandlers(false)` serves to block propagation to parent handlers. Specific APIs and semantics differ from Logback, so avoid copying attribute names across frameworks. When routing produces duplicates, inspect logger hierarchy, appender/handler refs, agents collecting both files and stdout, and collectors ingesting duplicate streams.

### Distinguishing Intentional Fan-Out from Unintended Duplicates

For example, `ERROR` going to both stdout and a file is valid **fan-out** if specified. If both a stdout agent and a file shipper send to the same index without a way to distinguish them, operators may see two records for the same event. Tests must count occurrences and pinpoint where the duplicate enters. Never mask a duplicate with blind deduplication at the dashboard before understanding the routing path, as that can hide a pipeline bug.

## 10. Testing Asynchronous Behavior and Sink Failures

Correct routing under normal conditions does not guarantee correctness under load:

- **Async logging:** An event may be enqueued without having reached the sink when the logger call returns. Tests must wait for the worker to drain or wait up to a bounded deadline, then compare event counts at the end.
- **Full queue:** Depending on the framework/policy, enqueuing may block, drop, discard lower-level events, or fall back to synchronous writes. Events missing from the sink due to overflow must be reported separately from events intentionally filtered out.
- **Unwritable file sink:** Missing permissions, full disk, invalid path, or rotation failure. Verify whether the framework reports error status, retries, falls back, or drops events.
- **Collector/network failure:** Events may exist in a file or stdout without being queryable in the backend. Test each hop and verify retry/buffering policies.
- **Shutdown:** For async workers, graceful shutdown needs sufficient drain and flush budget. Killing the process can lose in-memory events even when enqueuing succeeded.
- **Multiple instances:** The same `test_event_id` must be tagged with the right service/instance; machine clocks can drift and ingestion can reorder logs.

Collect metrics such as `route_selected_count`, `route_rejected_count`, `queue_dropped_count`, `sink_write_errors`, and `collector_ingest_lag` if the architecture supports them. Define measurement points clearly: some frameworks only report events received by an appender and do not know about events dropped earlier at the logger. Never claim "100% delivery" based solely on successfully processed events.

**Do not use a failing logger in an infinite loop to log errors about logging failures.** When a sink fails, report the error via internal status/diagnostics or appropriate monitoring to avoid recursive logging.

## 11. End-to-End Routing Testing in Staging

A practical end-to-end test scenario should follow these steps:

1. **Map the topology:** service, logging backend, appenders, file/stdout paths, log agent, collector, namespace/index, and access permissions.
2. **Capture effective configuration:** active profile, logger levels, filter chain, appender refs, additivity, routing keys, and default policy for missing keys.
3. **Emit test events:** use a unique `test_run_id` and unique `test_event_id` for each row in the matrix. Record expected routes and expected counts.
4. **Verify at JVM/sink:** test appender or file/console contains the expected events; use negative assertions to search for events in wrong sinks.
5. **Verify at collector:** inspect raw records, timestamps, field types, parsers, labels, and routing rules. Check for filters/transforms that might strip fields used for searching.
6. **Verify at index/search:** query within the right time window, namespace, environment, and permissions. Under eventual consistency, wait up to the deadline before declaring failure; count duplicates by `test_event_id`.
7. **Test failure modes:** temporarily disable a sink in the test environment, generate bursts, restart, and perform graceful stops; verify against policies and metrics.
8. **Restore:** return configurations and levels to their intended state; retain a test report containing actual routes, timings, event counts, and discovered defects.

Example result table you can save for each test run:

| Event | Expected | Actual | Count | Verdict |
| --- | --- | --- | ---: | --- |
| R2 / `order.created` | CONSOLE | CONSOLE | 1 | PASS |
| R4 / `payment.failed` | ERROR_FILE | ERROR_FILE | 1 | PASS |
| R5 / `role.changed` | AUDIT | AUDIT + CONSOLE | 2 | FAIL: leaked via root |
| R1 / `cache.detail` | None | None | 0 | PASS |

This is a **hypothetical report example**, not output from a real system. A negative test passes only when the relevant sinks have actually been checked; a search query returning 0 records due to a bad query or missing permissions does not prove the event is absent.

## 12. Common Routing Bugs

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| `INFO` logs vanish from all sinks | Effective level too high or early filter `DENY` | Check logger level and filters before examining appenders. |
| `ERROR` logs go to console instead of error file | Wrong `AppenderRef`/filter, unwritable file path | Check runtime config, appender status/errors, and level rules. |
| One event appears twice | Additivity, multiple appenders pointing to same sink, collector ingesting two sources | Check hierarchy, refs, and event IDs at each hop. |
| Audit event appears in app console | Audit logger still propagates to root, or marker/MDC rule doesn't match | Use an explicit audit route, run negative tests on console, and check permissions. |
| Log has valid routing key but is missing from sink | Blocked by level/other filter; sink failure or queue drop | Inspect every layer from producer to backend. |
| Subsequent request's logs land in previous request's sink | Stale MDC/ThreadContext in thread pool | Clean/restore context and test sequential multi-request flows. |
| Async logs lack routing key | Context not captured/propagated into event | Check pre-queue context capture and framework async mechanism. |
| Dynamic sink creates too many files/appenders | High-cardinality or unvalidated input used as route key | Enforce a bounded route allowlist and a controlled default route. |
| Staging logs land in production index | Inconsistent environment label/routing rule/agent config | Trace agent → collector → index path and test both environments. |
| Wrong timestamp or missing trace ID | Collector encoder/transform dropped fields | Compare records across JVM, sink, raw collector, and index. |
| Test counts fewer events than expected | Async not drained, level/filter drop, or queried too early | Use bounded waits, check drop counters, and inspect sink before backend. |
| Test PASSes even though log is misrouted | Asserts presence in one sink only; omits checks on other sinks | Write an expectation matrix with negative assertions for every case. |

## 13. Extending Tests for Security, Load, and Config Changes

### Security and Sensitive Data

An audit or security route must be tested for both **correctness** and **isolation**:

- Security logs must not appear in less-restricted consoles/indexes unless explicitly permitted by policy.
- Tenant/group A must not be able to create files or route into tenant/group B simply by sending arbitrary MDC values.
- Sink paths or topic names must never be constructed directly from untrusted input.
- Secrets, tokens, cookies, and personal data must be stripped/redacted before logs pass through inappropriate destinations.
- Read permissions, retention, encryption, and auditability of the sink itself must be tested separately; logger routing does not replace access control.

### Performance and Reliability

Testing with a handful of events can miss race conditions. After unit/integration tests PASS, run a representative load burst and check: route ratios, per-sink throughput, p95/p99 logger call latency, queue capacity, dropped events, log lag, and resource usage. Test low-frequency routes, such as 99% console and 1% audit, rather than testing only the main path.

Test configuration changes on staging with the next release candidate, run the same matrix, and compare; pay close attention to changes in logger names, additivity, appender refs, JSON field names, or dynamic routing mechanisms. Gate deployment pipelines with regression tests whenever routes affect alerting, security, or traceability.

### Criteria for Declaring PASS

A routing rule passes when:

- Events that should be kept **all appear** in the exact specified sinks within an acceptable deadline.
- Events forbidden from a sink are **truly absent** there after confirming the sink/test pipeline is operational.
- Occurrence counts match expected cardinality (exclusive or fan-out).
- Context, level, event code, and essential payload are preserved or transformed according to the approved schema.
- Missing/invalid routing keys, async overload, sink failures, and shutdown behave per the designed policy and are measured/monitored.
- There are no sensitive log leaks or cross-environment/cross-tenant misclassifications.

## 14. Self-Check Questions

1. Why is seeing `payment.failed` in `ERROR_FILE` not enough to conclude routing is correct?
2. In Logback, what happens when a child logger has its own appender but `additivity=true`?
3. Should an audit `ERROR` appear in `application-error.log`? Which documentation/spec should you consult to answer this?
4. Why cannot `trace_id` replace `test_event_id` when checking for duplicate logs?
5. If MDC is missing `log_route`, what should the system do and what conditions must be tested?
6. A log appears in stdout but is missing from the index after 1 second: which layers must be checked before concluding a routing bug?
7. What failures can a test miss if it only counts events at the sink when an async queue is full or the producer already filtered events?
8. How do you prove audit routing does not leak to console, especially with logger hierarchies and multi-source collectors?

**Completion criteria:** You can build an expected-routes matrix, run the Java 17 test, distinguish route/filter/additivity, pinpoint the root cause of lost or duplicate logs, and verify both **delivery to the right destination** and **absence from wrong destinations** from the JVM to the log backend.

## References

- [Oracle Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html) — levels, parent handlers, and APIs used in the example.
- [Oracle Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html) — processing and filtering `LogRecord` for a sink.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html) — logger hierarchy, additivity, and log levels.
- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html) — appender filters and `ACCEPT`, `DENY`, `NEUTRAL` results.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html) — appenders, configuration-based routing, and `SiftingAppender`.
- [Apache Log4j 2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html) — `LoggerConfig`, additivity, filters, and `AppenderRef`.
- [Apache Log4j 2 — Routing Appender](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html#RoutingAppender) — dynamic routing by context and routes.
