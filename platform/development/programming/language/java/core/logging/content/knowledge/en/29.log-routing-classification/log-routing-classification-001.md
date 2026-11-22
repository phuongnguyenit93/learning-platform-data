# Log Routing in Java: Event Routing and Classification

## 1. What is Log Routing?

**Log routing** is the process of deciding **where a logging event will be sent**, potentially across one or more destinations: console, file, `stdout`/`stderr` streams, monitoring systems, collectors, message brokers, or a dedicated storage channel. The decision is typically based on **severity level**, **logger/package name**, **event type**, **marker**, or **business context**.

For example, an ordering service might apply the following rules:

- INFO/DEBUG logs for routine operations are sent to the **application** channel.
- WARN/ERROR logs are additionally sent to the **alert** channel to draw attention from the monitoring system.
- Audit events such as permission changes or refunds go through a separate **audit** channel, regardless of which component emits them.
- Logs containing sensitive data must have that information stripped or masked **before being emitted** to any destination.

Conceptual processing flow:

```text
Business code -> Logger -> level check/Filter -> Routing
                                                  |
                         +------------------------+-----------------------+
                         |                        |                       |
                    APPLICATION                 ALERT                   AUDIT
                    console/file              warn/error            audit sink
                         |                        |                       |
                         +------------------------+-----------------------+
                                                  |
                                            Log collector
```

This is a conceptual diagram; a real-world architecture may route within the JVM, at the log collection agent, or in a centralized system. **Routing does not inherently mean filtering out:** an event can be sent to **multiple destinations** (fan-out), or to only a single destination (exclusive routing), depending on design rules.

**Classification** answers "which group does this log belong to?"; **routing** answers "which channel does this log go to?". An event can be classified by level and logger name, yet still require appender/handler configuration to know where it is written.

## 2. Components Involved in Routing

| Concept | Role | Example |
| --- | --- | --- |
| Logger | Where code emits events; typically hierarchically named | `com.example.orders.PaymentService` |
| Level | Classifies severity/detail | `DEBUG`, `INFO`, `WARN`, `ERROR` |
| Filter | Decides to accept/deny an event based on rules | Accept only WARN and above |
| Handler / Appender | Destination that processes log events | JUL `Handler`; Logback/Log4j 2 `Appender` |
| Formatter / Encoder / Layout | Encodes messages for the destination | Plain text, pattern, JSON |
| MDC / ThreadContext | Context attributes attached to the event | `requestId`, `service`, `operation` |
| Marker or event type | Label expressing event type independent of level | `SECURITY`, `AUDIT` |
| Collector/agent | Aggregates, parses, or forwards logs outside the JVM | Log collection and storage service |

There are two decision layers that are often confused:

1. **Does the logger create/pass the event?** For example, a logger at INFO level normally does not emit DEBUG events.
2. **Which appender/handler does a created event go to?** An appender can have its own filter, its own output path, and its own error-handling policy.

If an event has already been blocked at the logger layer, simply adding an appender below it usually **cannot recover it**. Conversely, a logger allowing INFO does not guarantee a handler will receive INFO if the handler only accepts WARN and above.

### 2.1. Routing by Level

A common rule is:

```text
INFO, DEBUG   -> application
WARN, ERROR   -> application + alert
AUDIT         -> audit (classified by dedicated logger/marker)
```

Note: if WARN/ERROR events are routed to both `application` and `alert`, the system **intentionally has two copies at two destinations**. This is fan-out. If only a single destination is required, you must build **exclusion rules** for the destinations; you cannot simply add a threshold filter for `alert` and assume `application` will no longer receive WARN/ERROR.

Level is suitable for assessing severity, but it is not enough to distinguish business categories: an `INFO` log could be a routine log or an important audit event.

### 2.2. Routing by Logger and Package Name

Java loggers typically have names like `com.example.payment`, `com.example.security`. The backend can be configured specifically for a name or name hierarchy:

```text
com.example.audit.*       -> audit sink
com.example.integration.* -> integration sink
root / remaining          -> application sink
```

The strength is that you do not need to change `logger.info(...)` calls everywhere if the architecture already defines sensible package/logger boundaries. However, Java packages do not necessarily align with business boundaries. A class handling both audit and routine operations may need a **separate logger/marker**, rather than routing all logs of that class to audit.

### 2.3. Routing by Marker and Context

A **Marker** is an event label, such as `SECURITY`. In the SLF4J API, you can create a marker and attach it to a logging call:

```java
import org.slf4j.Logger;
import org.slf4j.Marker;
import org.slf4j.MarkerFactory;

// Inside a class with a Logger log field and prepared event data:
Marker security = MarkerFactory.getMarker("SECURITY");
log.warn(security, "Authentication rejected for reason={}", reasonCode);
```

This is an **integration snippet**, requiring the SLF4J dependency, a `log` variable, and `reasonCode`; it is not a standalone Java application. Attaching a marker **does not automatically route**: the backend must have a filter/rule that recognizes that marker. You also need to verify whether the provider stores or exports the marker in the expected way.

**MDC** (Mapped Diagnostic Context) or **Log4j 2 ThreadContext** provides attributes such as `requestId` or `tenantGroup`. They aid searching and can support context-based routing, but:

- You must **propagate context** across asynchronous boundaries (executors, callbacks, reactive pipelines) according to the framework mechanism.
- You must **clear context** when the task finishes so reused worker threads do not carry stale values.
- Do not use arbitrary user-supplied values as file names, topics, or routing paths; validate against an allowlist of valid destinations.
- Avoid creating thousands of appenders/queues per `requestId` or per individual tenant without limits and lifecycle management.

## 3. Java 17: Example of Routing INFO and Warnings to Two Streams

`java.util.logging` (JUL) is built into the JDK. We can configure two `Handler` instances: an `APP` channel receiving INFO, and an `ALERT` channel receiving WARNING/SEVERE. In this example, `APP` prints to `stdout`, while `ALERT` prints to `stderr`.

Save the file **`RoutingLogDemo.java`**:

```java
import java.io.PrintStream;
import java.util.function.Predicate;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RoutingLogDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.routing");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler app = new LevelRouteHandler(
                System.out,
                "APP",
                level -> level.intValue() >= Level.INFO.intValue()
                        && level.intValue() < Level.WARNING.intValue());

        Handler alert = new LevelRouteHandler(
                System.err,
                "ALERT",
                level -> level.intValue() >= Level.WARNING.intValue());

        logger.addHandler(app);
        logger.addHandler(alert);
        try {
            logger.fine("hidden details");
            logger.info("Service started");
            logger.warning("Retry scheduled");
            logger.severe("Storage unavailable");
        } finally {
            logger.removeHandler(app);
            logger.removeHandler(alert);
            app.close();
            alert.close();
        }
    }

    private static final class LevelRouteHandler extends Handler {
        private final PrintStream destination;
        private final String channel;
        private final Predicate<Level> accepts;

        LevelRouteHandler(PrintStream destination,
                          String channel,
                          Predicate<Level> accepts) {
            this.destination = destination;
            this.channel = channel;
            this.accepts = accepts;
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (record == null || !isLoggable(record)
                    || !accepts.test(record.getLevel())) {
                return;
            }

            destination.println(channel + " ["
                    + record.getLevel().getName() + "] "
                    + record.getMessage());
        }

        @Override
        public void flush() {
            destination.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }
}
```

Compile and run:

```bash
javac RoutingLogDemo.java
java RoutingLogDemo
```

**`stdout`** output:

```text
APP [INFO] Service started
```

**`stderr`** output:

```text
ALERT [WARNING] Retry scheduled
ALERT [SEVERE] Storage unavailable
```

When a terminal displays both streams on one screen, **the interleaving order of `stdout`/`stderr` may vary**; the blocks above describe the contents of each stream without guaranteeing overall ordering. The example uses fixed messages for easy comparison.

Execution mechanism:

1. `logger.setLevel(Level.INFO)` blocks `FINE` events before they reach the handlers.
2. `setUseParentHandlers(false)` prevents propagating logs to the root JUL handler, avoiding duplicate printing outside the two custom channels.
3. The `APP` handler accepts levels from INFO up to below WARNING; the `ALERT` handler accepts WARNING and above. Both use `Level.intValue()` to compare JUL levels.
4. Each `Handler.publish(...)` checks state with `isLoggable(record)`, evaluates the rule, and writes to its assigned stream. This is **exclusive** routing for the levels used in the example.
5. `finally` removes the custom handlers. `close()` in the example only flushes; it **does not close `System.out` or `System.err`**, which are process-wide streams.

In production systems, a custom handler must consider I/O errors, synchronization, performance, lifecycle, and how to report internal errors without creating recursive logging loops. This example focuses on demonstrating routing and does not replace a full logging backend.

### 3.1. Why Not Simply Use Two ConsoleHandlers?

JUL's standard `ConsoleHandler` outputs to `System.err` by default. Two regular `ConsoleHandler` instances can be filtered by level, but they still share the same stream. To send INFO to `stdout` and warnings to `stderr` in a standalone example, we use handlers with explicit destinations. In real applications, Logback/Log4j 2 have console appenders that directly configure each stream, which is usually easier to use.

## 4. Routing with Logback Classic

When an application uses **SLF4J + Logback Classic**, we can separate output using **appenders** and the **logger hierarchy**. The following example is `src/main/resources/logback.xml` in an application that already has a compatible Logback dependency:

```xml
<configuration>
    <appender name="APPLICATION"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>APP %d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ALERT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>WARN</level>
        </filter>
        <encoder>
            <pattern>ALERT %d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="AUDIT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>AUDIT %d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.audit" level="INFO" additivity="false">
        <appender-ref ref="AUDIT"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="APPLICATION"/>
        <appender-ref ref="ALERT"/>
    </root>
</configuration>
```

**Exact interpretation:**

- `APPLICATION` receives events reaching the root appenders, with no separate filter to exclude WARN/ERROR.
- `ALERT` only accepts WARN and above thanks to `ThresholdFilter`.
- `AUDIT` receives events from the `com.example.audit` logger and child loggers inheriting this path, depending on specific configuration.
- `additivity="false"` on `com.example.audit` stops event propagation from the audit branch up to the root appenders. As a result, audit events in this branch do not go to `APPLICATION` and `ALERT` by default.
- For a regular logger with an effective level of INFO, `INFO` goes to `APPLICATION`; `WARN` and `ERROR` go to **both `APPLICATION` and `ALERT`**. Having two records in two streams is **intentional fan-out**.
- `root level="INFO"` does not necessarily re-filter DEBUG logs that were already accepted by a child logger with level DEBUG and propagated via additivity; to restrict at the appender, an appropriate filter is needed.

This is **in-JVM** routing configuration. If `stdout` and `stderr` are collected into the same index by a collector, you need a `channel`/stream label or structured log field to distinguish them; two streams do not automatically mean two separate durable storage locations.

### 4.1. Logging Business Events with a Dedicated Logger

In an application with SLF4J, example code:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class AuditEvents {
    private static final Logger AUDIT =
            LoggerFactory.getLogger("com.example.audit");

    public void permissionChanged(String operationId) {
        AUDIT.info("Permission changed, operationId={}", operationId);
    }
}
```

This is a Java class that compiles **in a project with the SLF4J API**; it requires a runtime backend and configuration for logs to reach the intended destination. According to the Logback configuration above, the `com.example.audit` logger routes to `AUDIT`.

Using a dedicated logger name is one way to classify; **do not include raw tokens, passwords, or sensitive data in audit messages**. For audit records that must be retained, the console appender in the example only illustrates the path and does not provide durable storage guarantees.

### 4.2. Additivity: A Common Reason for Duplicate Logs

In Logback, a child logger can forward events up to its ancestors' appenders. When attaching an appender to a child logger while keeping default additivity, events can be written by both the logger's own appender and the root appenders. This is not caused by code calling `log.info(...)` twice.

Example configuration:

```xml
<logger name="com.example.audit" level="INFO">
    <appender-ref ref="AUDIT"/>
</logger>
```

If `additivity="false"` is omitted and the audit logger continues propagating events to root, events can go to `AUDIT`, `APPLICATION`, and if WARN or above, also to `ALERT`.

You need a clear decision: do you want fan-out to multiple destinations or do you want the audit branch to have a single dedicated path? Then configure additivity and filters consistently. Setting `additivity="false"` on every logger without its own appender can leave events with no destination.

### 4.3. Strictly Exclusive Routing by Log Level

Configuring `ALERT` with a `ThresholdFilter` only restricts the **ALERT destination**; it does not automatically exclude warnings from `APPLICATION`.

If you want INFO only in `APPLICATION` and WARN/ERROR only in `ALERT`, you must place an exclusion rule on `APPLICATION`. You can use `LevelFilter` at INFO with matching accept/deny actions when only INFO is needed, though you must also account for DEBUG/TRACE if other loggers enable lower levels. For complex rules, choose a filter/evaluator appropriate for the backend version and thoroughly test each level.

## 5. Routing in Log4j 2

**Log4j 2** has its own appender, filter, and logger hierarchy mechanisms. Do not use `ch.qos.logback.*` classes to configure Log4j 2; whichever backend is active, use that backend's API and configuration.

The `log4j2.xml` example below demonstrates the same **fan-out** by severity and a dedicated route for the audit logger:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="APP" target="SYSTEM_OUT">
            <PatternLayout pattern="APP %-5p %c - %m%n"/>
        </Console>

        <Console name="ALERT" target="SYSTEM_ERR">
            <ThresholdFilter level="WARN"
                             onMatch="ACCEPT"
                             onMismatch="DENY"/>
            <PatternLayout pattern="ALERT %-5p %c - %m%n"/>
        </Console>

        <Console name="AUDIT" target="SYSTEM_OUT">
            <PatternLayout pattern="AUDIT %-5p %c - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.audit"
                level="info"
                additivity="false">
            <AppenderRef ref="AUDIT"/>
        </Logger>

        <Root level="info">
            <AppenderRef ref="APP"/>
            <AppenderRef ref="ALERT"/>
        </Root>
    </Loggers>
</Configuration>
```

This is a configuration for an application with a compatible **Log4j 2 Core**. The application must have the dependency and place the file where the backend loads it. Log4j 2 also provides `RoutingAppender` for dynamic destinations (e.g., grouping by an attribute), but that design is more complex because you must manage destination counts, file/topic names, appender lifetimes, and untrusted context values.

**Do not infer** that every application using SLF4J will understand both Logback XML and Log4j 2 XML. SLF4J is only a logging API; the actual provider/backend determines how routing works.

## 6. Routing by Context: Marker, Request ID, Tenant, and Audit

### 6.1. Context Serves Correlation, but Can Support Route Selection

An event may carry fields like:

```json
{
  "level": "WARN",
  "logger": "com.example.checkout.CheckoutService",
  "service": "checkout",
  "requestId": "req-123",
  "category": "PAYMENT",
  "message": "Payment provider timeout"
}
```

This is illustrative data; in practice, you should not manually construct JSON in every logger call if the backend already supports structured logging.

Router rules might be:

- `category=PAYMENT` → send a copy to the payment operations index.
- `level>=WARN` → alert channel.
- `category=AUDIT` → audit pipeline.
- `service=checkout` → add grouping attribute when aggregated at the collector.

**`requestId` is typically used to correlate events**, not as the name of a separate file/appender per request. If a system has millions of requests, creating millions of destinations will exhaust file descriptors, memory, and collection resources.

### 6.2. SLF4J MDC Example (Integration Snippet)

```java
import org.slf4j.MDC;

MDC.put("category", "PAYMENT");
MDC.put("requestId", requestId);

try {
    log.warn("Payment provider timed out, code={}", errorCode);
} finally {
    MDC.remove("category");
    MDC.remove("requestId");
}
```

This snippet requires `log`, `requestId`, `errorCode` from the application and an SLF4J provider that supports MDC. **Setting MDC alone does not create a router**: Logback/Log4j 2 or the collector must have rules that use the corresponding fields.

In a Java thread pool, using `finally` to clean up context prevents new requests from inheriting stale context. With `CompletableFuture`, executors, or reactive streams, context may not automatically appear on another thread. Use framework-appropriate propagation so logs are not misclassified.

### 6.3. Audit Requires Semantic Classification

An audit event typically needs fields such as **who**, **what action**, **which resource**, **timestamp**, **outcome**, and **correlation ID**, while avoiding unnecessary exposure of sensitive information. Do not assume that calling `log.info(...)` inside a class named `Audit` is sufficient to meet audit requirements.

If the system needs evidence resistant to log loss or tampering, you also need durable storage, read/write access controls, retention, integrity verification, and delivery path checks. Routing via ordinary console/file appenders does not automatically provide those guarantees.

## 7. In-JVM Routing vs. Collector Routing

Routing can happen in either place or in combination:

| Criterion | Inside the JVM Application | At the Collector/Agent |
| --- | --- | --- |
| Available information | Logger, level, marker, exception, MDC at event creation time | Fields serialized and transmitted to the collector |
| Ability to drop logs at source | Yes, helps reduce log transmission cost | Cannot recover CPU/bandwidth already spent before collector receipt |
| Centralized rule management | Requires deployment/config updates across instances | Easy to apply shared policies across multiple services |
| Impact on requests | Synchronous handler/appender or full queue can block producer | Usually indirect via agent/sink and backpressure mechanisms |
| Risk of information loss | Source-side filter permanently drops events | Collector cannot classify using fields not sent or already stripped |

A practical approach is to **keep full log structure at the source**, filter only data that must be dropped immediately, emit logs with a stable schema, and let the collector route further to individual indexes/sinks. However, security or audit records may require a dedicated path directly from the application.

Do not rely on vague text parsing like "if message contains `error`, route to alert" when structured `level` and `category` fields already exist. Regex extraction on messages breaks easily when formatting or wording changes.

## 8. Routing and Asynchronous Logging

When appenders/handlers use queues for asynchronous logging, routing must also account for **throughput and capacity**:

```text
many producers -> routing / filters -> bounded queues -> sinks
                                   +-> queue A: application
                                   +-> queue B: alert
                                   +-> queue C: audit
```

A log routed to three destinations **does not mean all three destinations will receive it successfully**. One queue may accept it while another is full; one sink may be slow while the others remain healthy. If consistency across multiple destinations is required, this is a delivery semantics problem more complex than attaching multiple appenders.

Key decisions:

1. How many events/how much memory is the queue bounded to, and when full does it **block, timeout, or drop**?
2. Is it acceptable for WARN/ERROR to be dropped when a sink is overloaded? If not, you need a durable path, latency budget, and explicit error policy.
3. Does audit logging share the same queue as DEBUG/INFO? Separating critical paths prevents noisy logs from impacting audit, though it does not guarantee durability on process crash.
4. On shutdown, how long are queued events flushed, and how is a failure to finish in time alerted?
5. Are there per-route metrics counting **accepted, dropped, written, delivery failed**?

Distinguish between **accepted into a queue** and **durably stored**. JVM memory, `stdout`, filesystem cache, and the collector can fail independently. Data that must be retained requires a pipeline suited to business requirements.

## 9. Designing Routes to Prevent Information Leakage

Routing is a **data flow** control point. If logs are sent to alert channels or third-party systems, you must determine what data is allowed to leave the application.

Principles:

- Never log passwords, access tokens, secrets, or unnecessary personal data in the first place; mask/redact at the source when appropriate.
- Do not derive file paths, Kafka topics, or indexes directly from unvalidated `tenantId`, `userId`, or HTTP header strings.
- Do not use arbitrary `requestId` values as metric labels or appender names due to high cardinality.
- Apply access control, retention, and deletion policies per sink; `audit` and `application` may have different requirements.
- Avoid feedback loops: an appender failing and logging errors back into itself, or a collector re-ingesting already-ingested logs.
- Rate-limit logs sent to alert channels to prevent "alert storms"; consider aggregation/rate limiting while preserving critical signals.

A regex filter that masks data after a message is built can be helpful, but it does not replace **not creating logs containing secrets** in the first place; exceptions, parameters, and context fields must also be reviewed.

## 10. Systematic Routing Testing

Testing should specify **inputs, copy counts, and target destinations**. A simple matrix:

| Event | APPLICATION | ALERT | AUDIT |
| --- | --- | --- | --- |
| Regular logger, INFO | Yes | No | No |
| Regular logger, WARN | Yes | Yes | No |
| Regular logger, ERROR | Yes | Yes | No |
| `com.example.audit` logger, INFO | No | No | Yes |
| `com.example.audit` logger, ERROR | No | No | Yes |

The table above matches the illustrated **Logback/Log4j 2 fan-out** configuration (assuming no other filters and appropriate logger levels). The JUL example in section 3 uses **exclusive routing**, so do not use this table to predict JUL results.

When writing integration tests, you can:

1. Emit an event for each level and each major logger, then collect events at each appender/sink.
2. Count the exact number of copies and compare against the matrix. Do not just assert "log exists" and ignore duplicates.
3. Verify child loggers, root, `additivity=false`, or `setUseParentHandlers(false)` in JUL.
4. Test marker/MDC-based routes with context **present**, **missing**, and **invalid**.
5. Test propagation across executors and context cleanup after worker threads are reused.
6. Simulate slow/unavailable sinks to verify timeout/drop/fallback behavior per route.
7. Test graceful shutdown, flushing, collector behavior, and retention at the level the system actually commits to.
8. Run tests with logs containing sensitive data to confirm it does not appear in restricted channels.

For asynchronous logs, tests must properly await drain/flush mechanisms rather than using an arbitrary `Thread.sleep(...)` and assuming logs have arrived.

### 10.1. Suggested Operational Metrics

If the framework/collector supports them or the application instruments them, useful metrics include:

- `log_route_events_total{route,level}`: number of routed events.
- `log_route_dropped_total{route,reason}`: number of events filtered out or dropped due to overload.
- `log_route_delivery_errors_total{route}`: write/send errors to the destination.
- `log_route_queue_depth{route}`: queue depth per route.
- `log_route_enqueue_latency_seconds{route}`: wait time to enqueue.

These are **suggested metric names**, not built-in metrics in every logging backend. Do not put log messages, request IDs, or user IDs into metric labels. Check both metrics and actual log counts at destinations, as some transmission/write errors only surface downstream.

## 11. Common Pitfalls

### Pitfall 1: "Once ALERT is attached, WARN no longer appears in APPLICATION"

False if both APP and ALERT receive events and APP has no filter excluding WARN. This is **fan-out**; an exclusion filter is required if exclusive routing is desired.

### Pitfall 2: "Setting root level to INFO will block DEBUG from all child loggers"

In Logback/Log4j 2, a child logger with level DEBUG can still create DEBUG events, and additivity can forward those events to root appenders. To enforce a limit at a sink, check that appender's filter/threshold according to the active backend. In JUL, you also need to understand that logger-level and handler-level are two separate steps.

### Pitfall 3: "Duplicate logs are caused by calling the logger twice"

It may be caused by an appender attached to both child and root loggers, additivity, or a collector pipeline ingesting the same source twice. Before changing code, inspect the routing topology and which appenders actually receive the event.

### Pitfall 4: "Once MDC is set, the router automatically understands it"

MDC is context data; routing rules must be configured separately. In async flows, context may not be propagated. A route based on `category` with a missing value needs a **default route** or explicit rejection policy to avoid silently dropping logs.

### Pitfall 5: "Putting each tenant in a separate file is definitely safer"

Without bounds on file count, appender objects, and data size, this approach can exhaust resources or allow path injection. Use a finite set of approved routes and enforce access control at storage.

### Pitfall 6: "Audit logs go to console, so they are reliable enough"

Not true for durable audit requirements. Collectors can stop, queues can fill, processes can be killed, and data can be altered; real audit requirements need appropriate storage, verification, and access-control design.

### Pitfall 7: "Routing to as many sinks as possible is better"

Fan-out increases serialization/write overhead, bandwidth, storage cost, and failure points. Only create routes with clear observability or business purposes; build an event → sink matrix to understand cost and retention policies.

## 12. Pre-Deployment Checklist

- Define **log categories**: application, alert, audit, security, integration, etc., with clear classification criteria.
- Map out the **logger/level/marker/context → appender/sink** matrix, explicitly noting exclusive routes vs. fan-out.
- Verify the active backend: JUL, Logback, Log4j 2, or another framework pipeline.
- Define filtering mechanisms at both **logger and appender**, along with additivity/parent handlers.
- Use a stable structured log schema, including timestamp, level, logger, service, and correlation ID where appropriate.
- Configure access control, data masking, retention, bandwidth, queues, and error policies for each sink.
- Test for duplicate logs, missing logs, wrong context, sink failures, overload, and shutdown.
- Monitor dropped log counts, latency, queue depth, and delivery errors per route.

**Key takeaway:** Log routing decides **which events go to which destinations**, while classification provides the information to make that decision. In Java, you need to understand logger levels, filters, handlers/appenders, and the logger hierarchy. A good rule clearly specifies **the happy path, potential duplicate writes, missing-context behavior, and what happens when a destination fails**.
