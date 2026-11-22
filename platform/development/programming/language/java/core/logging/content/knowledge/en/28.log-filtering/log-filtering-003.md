# Filtering by Logger in Java

## 1. Learning Objectives

In a Java application, different components emit logs simultaneously: controllers, services, repositories, HTTP clients, JDBC, schedulers, and third-party libraries. When you only care about logs from a specific group such as `com.example.orders`, you need to **select, discard, or route events based on the name of the logger** emitting the record. This is what **filtering by logger** means.

After this lesson, you will be able to distinguish a logger name from a class name and a thread name; understand how logger names form a hierarchy; choose the right place to apply a filter; write a JUL example that runs on Java 17; and configure Logback/Log4j 2 to write logs by namespace without accidentally misfiltering or dropping important logs.

It is important to distinguish three things right away:

- **Filtering by logger name:** based on the event's `loggerName`, for example accepting only `com.example.orders.OrderService` and other loggers in the orders group.
- **Adjusting level per logger:** setting DEBUG for orders and WARN for the HTTP client. This limits the level of detail of events right at the source.
- **Routing to an appender/handler:** sending all logs to the console while directing only orders logs into `orders.log`.

These three can work together, but they are not equivalent.

## 2. Logger Name and Namespace Tree

Logging APIs allow naming loggers. When using SLF4J, the common approach is:

```java
// Illustrative snippet; requires SLF4J and the OrderService class in the application.
org.slf4j.Logger logger =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

// A business name can be used instead of a class name.
org.slf4j.Logger audit =
        org.slf4j.LoggerFactory.getLogger("business.audit.orders");
```

With `OrderService` in the `com.example.orders` package, the class-based logger is typically named `com.example.orders.OrderService`. A set of names might look like:

```text
com.example
├── com.example.orders
│   ├── com.example.orders.OrderService
│   └── com.example.orders.audit.AuditWriter
├── com.example.payments
│   └── com.example.payments.PaymentService
└── com.example.orders2
    └── com.example.orders2.LegacyService
```

In this example, `com.example.orders` is a namespace with dot-separated child names. When writing a string-based filter, you must distinguish:

| Matching approach | Result |
| --- | --- |
| `name.equals("com.example.orders")` | Only the logger with that exact name |
| `name.startsWith("com.example.orders.")` | Selects child loggers in the orders namespace |
| Combining the two conditions above | Selects the namespace itself and its descendants |
| `name.startsWith("com.example.orders")` | **Wrong if an exact namespace is needed**: also matches `orders2` |

The corresponding name-checking helper:

```java
static boolean belongsTo(String loggerName, String namespace) {
    return loggerName != null
            && (loggerName.equals(namespace)
                || loggerName.startsWith(namespace + "."));
}
```

A logger name does not have to match a class or package name. An application can use `business.audit.orders` inside code located in a different package. In that case, filtering by logger name still works, whereas assuming "filter by the class's package" can be wrong. Always check the actual logger name written in the logs.

Do not confuse **logger name** with **thread name**. A single logger `com.example.orders.OrderService` can be called by dozens of threads; conversely, a single request-processing thread can log through multiple loggers.

## 3. Where Are Events Filtered?

```text
logger.info("Order accepted")
           |
           v
  Check logger level
           |  May reject the event before creating/writing
           v
  Filter at logger/context (if any)
           |
           v
  Forward to handler/appender via logger hierarchy
           |
           +---- CONSOLE: receives multiple namespaces
           |
           +---- ORDERS_FILE: filters by logger name
           |
           v
  Formatter/Encoder -> stdout, file, or collector
```

| Location | Example | Scope |
| --- | --- | --- |
| Level on logger | DEBUG for `com.example.orders` | Adjusts the event level produced by the logger/descendants via inheritance |
| Filter at logger | JUL `Logger.setFilter(Filter)` | Can drop records directly when the logger is called |
| Early filter at logging context | Logback `TurboFilter` | Intervenes at the context level before the event is dispatched to appenders |
| Filter at handler/appender | JUL `Handler.setFilter`, Logback `Filter<ILoggingEvent>` | Affects only a single output path; other appenders may still write |
| Configuration routing | Log4j 2 `LoggerConfig`, Logback logger/appender refs | Selects which sinks receive events based on logger name/hierarchy |
| Post-collection query | Searching by the `logger_name` field | Filters only stored records; does not reduce logs generated by the application |

An appender-level filter **cannot resurrect** a log already rejected by the logger level. Conversely, a logger allowing INFO does not guarantee INFO will reach the file: an appender may have a WARN threshold, reject it via a filter, or encounter an I/O error.

When designing, ask: "Do I want to **prevent event generation**, **only change the output destination**, or **search after collection**?" The answer determines the right place to put the condition.

## 4. Standalone Java 17 Example with java.util.logging

The following example uses JUL, which is built into the JDK. We attach a custom `Handler` to the parent logger `lesson` and use `Handler.setFilter` to **print only events whose logger name is `lesson.orders` or belongs to the `lesson.orders.` namespace**.

In addition, we place a filter directly on the `lesson.orders` logger to clearly illustrate the difference between a filter at the emitting logger and a filter at a shared handler. The example requires no Maven, Gradle, or external libraries.

Create the file `LoggerNameFilterDemo.java`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggerNameFilterDemo {
    private static boolean belongsTo(String name, String namespace) {
        return name != null
                && (name.equals(namespace)
                    || name.startsWith(namespace + "."));
    }

    public static void main(String[] args) {
        Logger group = Logger.getLogger("lesson");
        group.setLevel(Level.ALL);
        group.setUseParentHandlers(false);

        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }
                System.out.printf("%s | %s | %s%n",
                        record.getLevel().getName(),
                        record.getLoggerName(),
                        record.getMessage());
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        output.setLevel(Level.ALL);
        output.setFilter(record ->
                belongsTo(record.getLoggerName(), "lesson.orders"));
        group.addHandler(output);

        try {
            Logger orders = Logger.getLogger("lesson.orders");
            Logger audit = Logger.getLogger("lesson.orders.audit");
            Logger orders2 = Logger.getLogger("lesson.orders2");
            Logger payments = Logger.getLogger("lesson.payments");

            orders.setLevel(null);
            audit.setLevel(null);
            orders2.setLevel(null);
            payments.setLevel(null);

            orders.setFilter(record ->
                    !"DROP_AT_LOGGER".equals(record.getMessage()));

            orders.info("order-accepted");
            orders.info("DROP_AT_LOGGER");
            audit.warning("audit-recorded");
            orders2.severe("wrong-prefix");
            payments.info("payment-approved");
        } finally {
            group.removeHandler(output);
            output.close();
        }
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac LoggerNameFilterDemo.java
java LoggerNameFilterDemo
```

**Exact** stdout when run in a fresh JVM with no external configuration interfering with the `lesson` namespace:

```text
INFO | lesson.orders | order-accepted
WARNING | lesson.orders.audit | audit-recorded
```

### Why Are There Only Two Lines?

1. `group.setLevel(Level.ALL)` lets child loggers inherit a level that does not block events. `group.setUseParentHandlers(false)` prevents forwarding records to the default root handler, which would produce extra timestamped logs on `stderr`.
2. `orders.info("order-accepted")` is accepted by the logger. The name `lesson.orders` matches the handler's condition, so it is printed.
3. `orders.info("DROP_AT_LOGGER")` is rejected by the filter **attached to the orders logger itself**. The record never reaches the handler.
4. `audit.warning("audit-recorded")` originates from the child logger `lesson.orders.audit`. The handler inspects the name and allows it. The filter on the parent logger `lesson.orders` **is not automatically invoked again** when an event emitted by a child logger is forwarded to parent handlers.
5. `orders2.severe("wrong-prefix")` is dropped by the handler despite its high SEVERE level, because `lesson.orders2` does **not** match the `lesson.orders.` namespace.
6. `payments.info("payment-approved")` is dropped by the handler because its name is in a different namespace.
7. `output.publish` calls `isLoggable(record)`, which checks the handler's level and filter. The `finally` block removes and closes the handler created by the example.

JUL's default `ConsoleHandler` typically uses a formatter that includes timestamps and prints to `stderr`. This example intentionally uses a handler that prints to `System.out` without timestamps so the output can be compared exactly.

**Limitations:** this example uses a synchronous handler that processes logs one event at a time. It demonstrates filtering and routing, not a full logging system with rotation, async queues, or collectors. If run inside an application that already has loggers/handlers configured on the same namespace, the output may differ; inspect the runtime state.

## 5. Two Types of JUL Filters Behave Differently

### Filter on a Logger

```java
// Integration snippet in an application that has a logger variable.
logger.setFilter(record ->
        !record.getMessage().startsWith("internal-"));
```

`Logger.setFilter` accepts a `java.util.logging.Filter`. The filter's `isLoggable(LogRecord)` method returns `true` to let the record proceed or `false` to drop it. The logger level is also checked: if the level has already rejected the event, the filter cannot make it be logged.

Key point to remember: a filter attached to a logger **is not an automatically inherited rule for all child loggers**. Under JUL's mechanism, when a child logger emits an event and forwards it to an ancestor's handlers, the parent logger's filter is not re-evaluated simply because the event passes through. Therefore, to filter a group of loggers on a shared output destination, you typically use a filter on the **shared handler**.

In addition, `setFilter` mutates runtime state. If two components call this method on the same logger, the later call replaces the earlier filter. Do not overwrite a filter managed by a framework or library without verifying ownership.

### Filter on a Handler

```java
// Integration snippet: handler owned by the application.
handler.setFilter(record -> {
    String name = record.getLoggerName();
    return name != null
            && (name.equals("com.example.orders")
                || name.startsWith("com.example.orders."));
});
```

A handler can receive records from multiple loggers through the hierarchy and the `useParentHandlers` flag. A filter on the handler evaluates every record the handler actually receives, allowing you to create a file containing only one namespace without forcing other loggers to stop emitting events.

However, three conditions must all be met:
- The logger allows creating the record according to its effective level and source filter.
- The record has a path to the handler (not cut off by `useParentHandlers=false` at a relevant point).
- The handler allows the record according to its own level and filter.

In JUL, `Logger.isLoggable(Level.INFO)` only reflects whether the logger accepts the level; it does not confirm that a handler or final output system has accepted the record.

## 6. Logback: Filtering by Name at the Appender

When using **SLF4J + Logback Classic**, an application typically has class-named loggers, inherited levels, and multiple appenders. If the goal is **for the console to receive all modules while `orders.log` contains only orders**, you can place a logger-name filter directly on the file appender.

Example `logback.xml` configuration snippet, requiring the `com.example.logging.OrdersOnlyFilter` class to be compiled and present on the classpath:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ORDERS_FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/orders.log</file>
        <append>true</append>
        <filter class="com.example.logging.OrdersOnlyFilter"/>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="ORDERS_FILE"/>
    </root>
</configuration>
```

The filter class to add to a Java project using Logback Classic:

```java
package com.example.logging;

import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.filter.Filter;
import ch.qos.logback.core.spi.FilterReply;

public final class OrdersOnlyFilter extends Filter<ILoggingEvent> {
    @Override
    public FilterReply decide(ILoggingEvent event) {
        String name = event.getLoggerName();
        boolean matches = name != null
                && (name.equals("com.example.orders")
                    || name.startsWith("com.example.orders."));
        return matches ? FilterReply.NEUTRAL : FilterReply.DENY;
    }
}
```

This is an **integration snippet** that requires Logback, not a JDK-only program. Both the XML and the filter class must be placed in the appropriate application resources/sources, and the file path must have appropriate write permissions.

**How it works:**
- `DENY` drops the event **at `ORDERS_FILE`**. That same event can still be written to `CONSOLE`.
- `NEUTRAL` does not actively block; subsequent filters and appender logic continue deciding. Do not arbitrarily replace it with `ACCEPT`, because `ACCEPT` may prevent later filters from being consulted.
- The `com.example.orders` logger has level `DEBUG`. Loggers in this namespace that do not declare their own level inherit this level accordingly.
- Root `INFO` does not mean `DEBUG` events emitted by orders loggers will be rejected a second time when passing through root appenders. In Logback, events already created by a child logger can propagate to ancestor appenders via **additivity**.
- The file appender never sees events that were already rejected at the logger level, even if the file filter would allow that logger name.

### When Should You Use TurboFilter?

Logback provides `TurboFilter` to make an earlier decision, before a full log event is created, based on logger name, level, marker, or content. It has **context-wide** scope, making it suitable when a rule must apply across all loggers, though it can block both console and file outputs. Choose `TurboFilter` only when you need to drop events at the source and have assessed the impact on important logs.

To **filter a single sink**, an appender-level filter like `OrdersOnlyFilter` is usually easier to control. To **reduce verbosity** from a noisy library, configuring the logger level by name is usually simpler.

### Additivity and Duplicate Logs

If you attach `CONSOLE` to both `com.example.orders` and root while `additivity=true`, the same event can be written twice. When designing dedicated routing, consider:

```xml
<!-- Configuration snippet; ORDERS_FILE is already declared elsewhere. -->
<logger name="com.example.orders" level="DEBUG" additivity="false">
    <appender-ref ref="ORDERS_FILE"/>
</logger>
```

This stops forwarding orders events to root appenders. If you also want orders written to the console, you must attach `CONSOLE` directly to the orders logger or reorganize the appenders. `additivity=false` changes the event forwarding path; it is **not** a message-based filter.

## 7. Log4j 2: Routing via LoggerConfig

Log4j 2 lets you configure loggers by namespace along with appender refs. The `log4j2.xml` example below routes orders to both a file and the console, while other modules go only to the console:

```xml
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%level %logger - %msg%n"/>
        </Console>

        <File name="ORDERS_FILE" fileName="logs/orders.log">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %level %logger - %msg%n"/>
        </File>
    </Appenders>

    <Loggers>
        <Logger name="com.example.orders"
                level="debug" additivity="false">
            <AppenderRef ref="ORDERS_FILE"/>
            <AppenderRef ref="CONSOLE"/>
        </Logger>

        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

When a `LoggerConfig` matches `com.example.orders`, loggers in that namespace use the `debug` level and the listed appender refs; `additivity=false` prevents forwarding events up to root. Other loggers follow root `info` and `CONSOLE`, unless a more specific configuration exists.

This example uses **routing** by logger name in the configuration hierarchy. If you need a more complex predicate over events reaching an appender, Log4j 2 also provides attachment points for `Filter` on logger configurations, appender references, or appenders. A message/regex filter does not automatically inspect `loggerName`; you must choose the right data and API.

When logs do not appear as configured in XML, check the actual backend. An application calling SLF4J might be using Logback and **not reading** `log4j2.xml`. Conversely, Log4j 2 can receive events through a bridge when properly configured; do not infer the backend solely from `logger.info(...)` calls in source code.

## 8. SLF4J and Spring Boot: Setting Levels by Logger Name

SLF4J is a unified facade/API; it does not define a universal `setFilter` API across all backends. To filter by logger, you must use the API or configuration of the active backend.

In Spring Boot, you can set levels by logger name via properties:

```yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
    com.example.payments: WARN
```

The expected result is that loggers in the orders namespace can emit `DEBUG` (unless overridden elsewhere), while payments has a `WARN` threshold. This is **per-logger level adjustment**, which is not enough by itself to create a file containing only orders. Routing requires Logback/Log4j 2 configuration or a downstream log system.

The effective level can be influenced by profiles, environment variables, external files, command-line properties, and runtime changes. If the application has Spring Boot Actuator and the endpoint is configured/authorized, `/actuator/loggers` can help inspect configured and effective levels. However, that API **does not prove** that a log passed an appender filter and was written to a file.

## 9. Comparing Commonly Confused Filter Types

Suppose a record has the following fields:

```text
logger_name = com.example.orders.OrderService
thread_name = http-worker-7
level       = INFO
message     = Order created
request_id  = req-42
trace_id    = 4bf92f3577b34da6a3ce929d0e0e4736
```

| Filter by | Question answered | Example use case |
| --- | --- | --- |
| Logger name | Which component emitted the event? | View only orders logs |
| Level | How severe/detailed is it? | Only WARN and above |
| Thread name | Which thread was executing? | Diagnose a hung worker |
| Message/exception | What specific event occurred? | Find timeouts or exceptions |
| Marker | What event tag was attached? | Group SECURITY/AUDIT logs |
| MDC/context | Which request, tenant, or user flow? | Look up `request_id` |
| Trace ID | Which cross-service operation? | Correlate logs in a distributed trace |
| Log backend query | Which records were stored? | Search records within a time range |

Do not use logger name as a substitute for trace ID. Every request may use the same `OrderService` logger; a single request may also log across many loggers. Instead of filtering out data for a one-off investigation, it is usually better to retain appropriate data and query by trace/context when needed.

## 10. Verifying Filters in a Real Environment

Do not conclude a filter works merely because a config file has a `<logger>` line or a filter class exists in source code. Verify runtime behavior with the following steps.

**Step 1 — Confirm the process/backend.** Record the build, JVM, profile, actual logging provider, and loaded configuration source. If using SLF4J, you can inspect the factory class:

```java
// Integration snippet requiring SLF4J on the application classpath.
System.out.println(
        org.slf4j.LoggerFactory.getILoggerFactory()
                .getClass().getName());
```

**Step 2 — Inspect effective levels, routing, and filters.** For JUL, inspect `getLevel`, `getParent`, `getUseParentHandlers`, `getFilter`, and `getHandlers`, along with each handler's level/filter. For Logback, inspect configured/effective levels, `isAdditive`, directly attached appenders, and filter configuration. For Log4j 2, inspect the active `LoggerConfig`, appender refs, and filters using the appropriate version's API.

**Step 3 — Emit probe logs at four logger names:**

1. Exact name `com.example.orders`.
2. Child name `com.example.orders.OrderService`.
3. Similar-looking name outside the namespace `com.example.orders2.LegacyService`.
4. Unrelated group name `com.example.payments.PaymentService`.

Include a unique probe ID in the message or structured field, such as `LOGGER_FILTER_PROBE_2026_11`, then check both the console and the target file/collector. Do not enable DEBUG across an entire production application just to test a filter.

**Step 4 — Compare expected vs. observed at each sink.** If the goal is "orders.log contains only orders", the console may still display other modules. If the goal is "suppress noisy logs across all destinations", a single appender filter is not enough.

**Step 5 — Verify negative cases.** A lookalike namespace like `orders2` must not be selected. A child logger like `orders.api` must be selected if descendants are intended. DEBUG events must be received when both logger and appender allow them. No duplicate records should appear due to additivity.

Table for recording test results:

| Event source | Console | Orders file |
| --- | --- | --- |
| `com.example.orders` | Yes, if level allows | Yes |
| `com.example.orders.api` | Yes, if level allows | Yes |
| `com.example.orders2` | Yes, if level allows | No |
| `com.example.payments` | Yes, if level allows | No |

The table above describes the **expected** behavior of the Logback configuration in Section 6, not proof that the system actually ran. Actual results must come from probe logs and reading the real output destinations.

## 11. Common Pitfalls

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| `orders2` appears in the orders file | Using `startsWith("...orders")` without a namespace boundary | Match exact name or append `"."` to the prefix |
| Filter on JUL parent does not block child logger logs | Parent logger Filter is not re-evaluated when events travel to handlers | Attach the Filter to the shared handler or the emitting logger |
| Appender allows DEBUG but no events appear | Logger effective level rejects events before the appender receives them | Check the logger's effective level |
| Logback root is INFO yet child DEBUG logs still appear | Child event was already created and propagated to the root appender | To filter at the sink, set a threshold/filter on the appender |
| Duplicate logs | An appender is attached at multiple levels with additivity still enabled | Check appender refs, reorganize, or set additivity appropriately |
| Dedicated file is missing logs | Wrong appender filter, path, write permissions, or lifecycle | Check appender status and run a probe log |
| Logger name differs from class name | Logger was named manually or via a wrapper creating a different logger | Inspect the runtime logger name in emitted events |
| XML changes have no effect | Wrong backend, wrong config file, active profile, or not reloaded | Identify the loaded resource from startup diagnostics |
| Need per-request filtering but filtered by package | One package handles many concurrent requests | Use MDC/trace ID with the appropriate mechanism |
| Important error logs are also blocked | Rule drops ERROR/WARN or namespace is too broad | Define exceptions and test error/audit paths |

## 12. Operational and Security Notes

- **Early filtering has different costs and effects than late filtering.** Dropping events at the logger reduces log creation/writing work, but loses those events across all sinks. Filtering at the appender leaves other destinations intact; filtering at query time affects only how stored data is viewed.
- **Avoid expensive predicates on every event.** Avoid I/O, network calls, or unnecessary regexes in filters. Exact name matching and dot-delimited prefix checks are usually readable, fast, and testable.
- **Ensure audit/security logs are not dropped.** If critical events must be preserved, avoid overly broad rules that accidentally drop ERROR or AUDIT logs. Best-effort logging does not replace a durable event-recording system.
- **Check async logging.** Records may sit in a queue before reaching a sink; consider queue overflow, drop policies, and shutdown flushing. "Not visible immediately" does not mean a filter dropped it.
- **Do not put sensitive data into probes.** Never log passwords, tokens, PII, or real payloads. Logger filtering is not an access-control mechanism for log records.
- **Be careful with runtime changes.** `setFilter`, `setLevel`, and context reload/reset mutate process behavior. Read-only checks should focus on inspecting state and running environment-appropriate probes.
- **Match the backend and version.** JUL, Logback, and Log4j 2 have different filter attachment points and semantics; read the API documentation for the running backend before applying configuration.

## 13. Practice Questions with Answers

**Question 1.** Which condition selects `app.orders` and `app.orders.api` without selecting `app.orders2`?

Answer: `name != null && (name.equals("app.orders") || name.startsWith("app.orders."))`.

**Question 2.** In JUL, does a filter on a parent logger always run when a child logger sends an event to the parent's handler?

Answer: **No**. A parent logger's filter is not automatically invoked on records emitted by a child logger. A filter placed on the handler is the way to apply a shared condition to events reaching that handler.

**Question 3.** If Logback root is `INFO` while the `app.orders` logger has level `DEBUG`, can an orders `DEBUG` event reach an appender attached to root?

Answer: **Yes**, if the event is created and additivity routes it to that appender. The root level is not necessarily re-applied at the appender; to block `DEBUG` at a sink, use an appender-level threshold/filter.

**Question 4.** All logs must go to the console, and `orders.log` must contain only orders. Where should the filter be placed?

Answer: **On the appender writing `orders.log`**, or by routing the logger namespace to a dedicated appender. Avoid placing a context-wide filter that drops events from other modules if they still need to appear on the console.

## 14. Completion Checklist

A logger-filtering solution is considered correct when:

1. Actual logger names and namespace conventions have been verified.
2. Name-matching conditions accurately distinguish the logger, its descendants, and lookalike namespaces.
3. The goal is clear: reduce logs at the source, filter a single appender, or query at the backend.
4. Level inheritance, Filter, handler/appender, and additivity have all been considered.
5. Probe logs have been tested from the main logger, a child logger, a lookalike logger, and an unrelated logger.
6. Results are verified at each target destination, not just by reading the config file.
7. Error/audit logs and async shutdown policies are accounted for before deployment.

**Key takeaway:** Filtering by logger means selecting events by **the identity of the emitting component**. Understanding where decisions are made — logger, context, handler/appender, or log collector — enables intentional routing, reduces noise, and preserves critical logs for diagnostics.
