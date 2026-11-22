# Log Routers in Java Logging Architecture

## 1. What Is a Log Router and Why Is It Needed?

In a small application, every log message can go to the terminal screen together. As a system grows larger, log records serve different purposes: operational logs need to appear in the console or a monitoring system; alerts need early attention; audit logs require access control and retention policies; debug logs may only be needed in test environments.

A **log router** is the component that applies rules to decide **which records are forwarded to which destinations**, potentially routing a single record to multiple destinations or dropping unsuitable records. Rules are typically based on severity level, logger name, event type, service, environment, or context fields in the record. In Java libraries, this functionality usually resides in the combination of `Logger`, `Filter`, `Handler`/`Appender`, and propagation configuration; in centralized systems, a log collector agent or processing pipeline may also route records again.

Visualize it as follows:

```text
Java Code
    |
    v
Logger (event source and log level)
    |
    v
Filter / routing rules
    |-------------------|--------------------|
    v                   v                    v
Console / stdout     File / audit         Alert / collector
    |                   |                    |
    v                   v                    v
Centralized          Controlled           Analysis / alerting
collection           storage
```

The key point is that **creating events**, **deciding the path**, **formatting**, and **writing to a destination** are responsibilities that can be separated. Business code should describe what happened; logging configuration decides where it needs to go. As a result, adding a new storage destination usually does not require modifying log statements scattered throughout the application.

## 2. Placing the Router Correctly in the Architecture

A common logging pipeline consists of the following steps:

1. **Producer (log emitter):** executing code calls the logging API, for example `logger.info("order.created")`, optionally attaching an exception and context.
2. **Logger:** carries the source classification name and applies the allowed level or source-level filter. If blocked at this step, the event will not reach any handler.
3. **Router and filters:** selects one or more sinks according to policy. Filters on each sink can differ.
4. **Formatter/encoder:** converts a `LogRecord` or event object into a text line or JSON, formatted with timestamp, level, structured fields, and stack trace.
5. **Handler/appender (local sink):** writes to the console, file, queue, or supported destination.
6. **Centralized collector/pipeline (if present):** reads stdout/files or receives forwarded data, and can further filter, mask data, distribute, and store according to policy.

For example, an application might output JSON to stdout so that a sidecar agent in the same container collects and sends it to an analytics system. In that case, **the application routes to stdout; the centralized pipeline routes to storage**. These two control layers should not be confused.

### Routing Types

| Criterion | Rule Example | Suitable Scenario |
| --- | --- | --- |
| Level (`level`) | `WARNING`/`ERROR` to the alert channel | Detecting anomalies that require attention. |
| Source (`logger name`) | `com.example.payment` to the payment channel | Separating functional groups for investigation. |
| Event type | `event.type=audit` to the audit store | Applying specialized retention/access control. |
| Service/environment | `service=checkout`, `env=prod` to the production index | Separating data by source and environment. |
| Outcome/component | `outcome=failed` or `component=database` to a dedicated analysis route | Investigating specific failures or bottlenecks. |

A router can perform:

- **Exclusive routing (single destination):** audit logs only go to a controlled store.
- **Fan-out (multiple destinations):** the same alert goes into both the general operational stream and the alert stream.
- **Intentional dropping:** `DEBUG` logs are unnecessary in production.
- **Transforming/masking data before forwarding:** changing structure or removing sensitive fields according to policy; care is required because multiple copies may traverse different routes.

**Routing alone does not make events reliable.** A log line blocked by the source level, lost due to a full queue, or not flushed before process termination cannot be recovered by downstream routers through destination-selection rules alone.

## 3. Distinguishing Log Levels, Loggers, Filters, Handlers, and Propagation

In `java.util.logging` (JUL, built into the JDK):

- **`Logger`:** hierarchical classification name, e.g., `app.orders`; each logger has its own level and may have a parent logger.
- **`LogRecord`:** data for a single event such as level, logger name, message, timestamp, and throwable.
- **`Filter`:** a function that decides whether a record may pass; can be attached to a logger or a handler.
- **`Handler`:** the sink for records. `ConsoleHandler`, `FileHandler`, and other handlers are responsible for publishing records.
- **`Formatter`:** chooses how to represent the record before writing.
- **`useParentHandlers`:** controls forwarding records up to the parent logger's handlers; very important for avoiding duplicate writes.

In JUL, the levels from most severe to most detailed are typically:

```text
SEVERE > WARNING > INFO > CONFIG > FINE > FINER > FINEST
(ALL allows all levels; OFF blocks all levels)
```

At the source, a logger may not create a record if the event level is lower than the logger's effective threshold or is rejected by a filter. A record that passes the source can be delivered to handlers on the logger and handlers on its parent loggers when propagation is enabled. **Each handler also has its own level and filter**, so the same record can be accepted at one destination while being dropped at another.

Policy example:

| Event | Operational channel (INFO+) | Alert channel (WARNING+) | Audit channel (`app.audit`, INFO+) |
| --- | --- | --- | --- |
| `app.orders` / FINE | No | No | No |
| `app.orders` / INFO | Yes | No | No |
| `app.orders` / WARNING | Yes | Yes | No |
| `app.audit` / INFO | No | No | Yes |

A `WARNING` record appearing in both operational and alert channels **is intentional fan-out**; a record appearing twice in the same channel because a handler is attached to the child logger while also propagating to the parent is usually **configuration duplication**.

### Parent Loggers and Inheritance

Dot-separated logger names form a hierarchy—for instance, `app.orders` sits under `app`. If a child logger does not set its own level, it typically uses the effective level inherited from its parent. However, when forwarding an accepted record to the parent's handlers, **the parent logger's level is not a second filter pass for that record**; the parent's handlers still apply their own levels and filters. Therefore, controlling output solely via the parent logger's level can yield unexpected results.

In other backends such as Logback, the corresponding concepts are typically `Appender` and `additivity`. `SLF4J` mainly provides an API (facade) for application code; record-publishing rules depend on the backend in use. Do not assume JUL and Logback configurations or level names are completely interchangeable.

## 4. Java 17 Example: Routing by Source and Level

This example uses **the JDK's JUL, with no external libraries required**. A parent logger receives events from two child loggers: `lesson.route.orders` (order operations) and `lesson.route.audit` (audit). Three handlers represent three destinations via labels printed to stdout:

- `OPS`: order logs at `INFO` level and above.
- `ALERT`: order logs at `WARNING` level and above.
- `AUDIT`: audit logs at `INFO` level and above.

In practice, each handler can write to a different destination; here they all print to stdout so learners can clearly see routing decisions without depending on files or the network. Save as `LogRoutingDemo.java`:

```java
import java.util.logging.Filter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogRoutingDemo {

    static final class RoutedHandler extends Handler {
        private final String destination;

        RoutedHandler(String destination, Level minimum, Filter filter) {
            this.destination = destination;
            setLevel(minimum);
            setFilter(filter);
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            System.out.printf("%s | %s | %s | %s%n",
                    destination,
                    record.getLevel().getName(),
                    record.getLoggerName(),
                    record.getMessage());
        }

        @Override
        public void flush() {
            // Example writes directly to stdout; no separate buffer.
        }

        @Override
        public void close() {
            // Does not own System.out, so do not close this stream.
        }
    }

    public static void main(String[] args) {
        Logger router = Logger.getLogger("lesson.route");
        router.setLevel(Level.ALL);
        router.setUseParentHandlers(false);

        String ordersName = "lesson.route.orders";
        String auditName = "lesson.route.audit";

        Handler operations = new RoutedHandler(
                "OPS", Level.INFO,
                record -> ordersName.equals(record.getLoggerName()));

        Handler alerts = new RoutedHandler(
                "ALERT", Level.WARNING,
                record -> ordersName.equals(record.getLoggerName()));

        Handler audits = new RoutedHandler(
                "AUDIT", Level.INFO,
                record -> auditName.equals(record.getLoggerName()));

        router.addHandler(operations);
        router.addHandler(alerts);
        router.addHandler(audits);

        Logger orders = Logger.getLogger(ordersName);
        Logger audit = Logger.getLogger(auditName);
        orders.setLevel(Level.ALL);
        audit.setLevel(Level.ALL);

        orders.fine("order.cache.hit");
        orders.info("order.created");
        orders.warning("order.retry");
        audit.info("permission.changed");

        router.removeHandler(operations);
        router.removeHandler(alerts);
        router.removeHandler(audits);
        operations.close();
        alerts.close();
        audits.close();
    }
}
```

Compile and run with JDK 17+:

```bash
javac LogRoutingDemo.java
java LogRoutingDemo
```

Stdout:

```text
OPS | INFO | lesson.route.orders | order.created
OPS | WARNING | lesson.route.orders | order.retry
ALERT | WARNING | lesson.route.orders | order.retry
AUDIT | INFO | lesson.route.audit | permission.changed
```

Explanation of each decision:

1. `orders.fine("order.cache.hit")` passes the `ALL` level at the source, but does not meet the `INFO`/`WARNING` threshold of the matching handlers; it is not printed.
2. `orders.info("order.created")` matches the orders source and meets the level for `OPS`, but not for `ALERT`.
3. `orders.warning("order.retry")` matches both `OPS` and `ALERT`. Two lines with the same content under **two different destination labels** match the fan-out policy.
4. `audit.info("permission.changed")` only passes `AUDIT` thanks to the logger name filter, even though it also has level `INFO`.
5. `router.setUseParentHandlers(false)` prevents records from continuing to the JUL root logger's handlers and cluttering the demonstration output with unintended lines. In real applications, only disable propagation after verifying the logging intent of the entire logger tree.

Program note: the `RoutedHandler` class demonstrates the decision point with a synchronous print to stdout. It does **not** provide durable file writing, retries on failure, automatic sensitive-data masking, or queue management. A production handler must account for multi-threaded concurrency, record formatting, access permissions, and destination failures; prefer well-tested, properly configured handlers/appenders rather than writing complex data-transport mechanisms yourself.

## 5. Routing via Configuration Instead of Hardcoding Rules in Business Code

In real applications, calls like `logger.info(...)` should remain stable, while levels, filters, and appenders are declared through deployment configuration. The following example **illustrates Logback**, and is only used when the application already has SLF4J and Logback on the classpath; this is a backend configuration, not JUL code and not a standalone Java program:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="AUDIT_FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/audit.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.audit" level="INFO" additivity="false">
        <appender-ref ref="AUDIT_FILE" />
    </logger>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

In this configuration:

- Logs under `com.example.audit` are sent to `AUDIT_FILE` and do not propagate up to the root logger's `CONSOLE` because `additivity="false"`.
- Other loggers without dedicated configuration use the root `INFO` threshold and write to the console.
- `additivity="false"` prevents propagation, but **it can also drop the general collection route** if operations expects all logs to appear on the console. This rule must be chosen according to the actual routing diagram.
- Files inside a container can be deleted when the container is replaced; **writing an audit file does not equal reliable audit storage**. Access permissions, collection, retention, and assurance levels must be defined separately.

A channel dedicated to `ERROR` or `WARN` usually requires an appender threshold and/or a corresponding filter. A logger with level `INFO` does not automatically split `INFO` and `ERROR` into two destinations. When fan-out is needed, attach the exact appenders and filters for each destination, then verify the result with sample events.

## 6. Routing at the Centralized Collector

When a system has multiple services or containers, an additional routing layer outside the JVM is often needed:

```text
Service A --stdout--> collector ----> operational log search store
Service B --stdout--> collector ----> long-term archive
                          |
                          +--------> access-controlled audit channel
                          |
                          +--------> analyzer/alerting
```

This layer can route records to storage based on `service`, `environment`, `event.type`, or other normalized fields. An application that emits properly structured JSON logs with source metadata significantly simplifies centralized routing.

Example of a JSON event:

```json
{
  "timestamp": "2026-01-01T10:15:30Z",
  "level": "WARN",
  "service": "checkout",
  "environment": "prod",
  "logger": "com.example.checkout.PaymentService",
  "event": "payment.retry",
  "trace_id": "trace-42",
  "attempt": 2,
  "error_code": "UPSTREAM_TIMEOUT"
}
```

The collector can route based on `environment=prod` and `event=payment.retry`, while keeping `trace_id` to trace the execution. Do not create routes or metric labels per `trace_id` or per URL with unique IDs, because cardinality will grow uncontrollably. Dynamic fields are suitable for **detailed search**; bounded-cardinality fields are suitable for **aggregated grouping**.

Decision points for a real system:

- **Where to filter:** filtering in the JVM saves bandwidth and memory but discards data permanently; filtering after collection preserves broader analysis capability but increases cost.
- **Late, lost, or duplicate records:** asynchronous queues can fill up; collectors may retry after network errors and duplicate records. If exact counts are needed, define an event identifier and a deduplication/loss-handling policy.
- **Ordering:** records across threads, JVMs, or multiple destinations are not guaranteed to preserve global order; use timestamps and appropriate correlation IDs/trace IDs rather than relying on line order to infer causality.
- **Buffering:** asynchronous routing reduces wait time on the main processing path but can lose logs during crashes or congestion; synchronous routing can increase latency if a destination is slow.
- **Security and access control:** strip tokens, passwords, and sensitive personal data as early as possible; audit channels must have appropriate access permissions, retention, and tamper/deletion controls.
- **Storage cost:** `DEBUG` routes have shorter retention than incident routes; policies must still retain enough data for investigation when needed.

In particular, **audit logs** used for regulatory requirements or business guarantees may require a dedicated transactional event stream and higher delivery guarantees than regular application logs. Configuring a router alone does not provide integrity or delivery guarantees.

## 7. Testing and Observing the Router Itself

A small configuration change can drop critical logs or duplicate record counts. Test using a source × level × destination matrix, similar to the table in Section 3.

Minimum test cases for the example in Section 4:

| Input | Expected Destination |
| --- | --- |
| `orders / FINE` | None. |
| `orders / INFO` | `OPS` only. |
| `orders / WARNING` | `OPS` and `ALERT`, one record per destination. |
| `audit / INFO` | `AUDIT` only. |
| `orders / SEVERE` | `OPS` and `ALERT`, if no additional filter is present. |

Beyond checking log paths, you need to know **whether the router itself is working**. Monitor the number of records entering, exiting to each destination, filtered out, dropped due to full queues, publish errors, and buffer latency if your tooling supports it. Distinguish between "no new logs because the service is not emitting events" and "the service is still running, but the pipeline is broken."

A useful manual check: emit a sample log with a known `event` and `trace_id` in a test environment, verify it appears in the right channel, the right number of times, at the right level, and with the right structure; then verify that a record containing data meant to be masked does not appear unmasked at any destination. Do not put real sensitive information into test data.

## 8. Common Design Mistakes

1. **Routing on unstable message strings:** changing wording or language breaks the rules. Prefer logger names, event codes, markers, or standardized structured fields.
2. **Setting levels on handlers while forgetting source levels:** events dropped early by the logger never reach any handler, even if the handler is set to `ALL`.
3. **Attaching appenders to both child and parent while forgetting propagation:** the same event appears duplicated in one channel. Check `useParentHandlers` (JUL) or `additivity` (backend).
4. **Disabling propagation for all loggers:** drops the general console/collector channel as well; only apply when there is a clear routing diagram.
5. **Using dynamic logger names per request/user:** destabilizes classification and increases complexity; use a fixed logger per component and store request IDs in context fields.
6. **Treating a successful send call as durable storage:** returning from `publish` or `logger.info` does not guarantee the record is in centralized storage, especially when buffers and networks are involved.
7. **Sending logs containing secrets to multiple destinations:** creates extra copies of sensitive data and makes control harder; mask at the source, and enforce permissions and retention at each destination.
8. **Doing heavy work in synchronous filters or handlers:** can slow down the business processing path; use dedicated processors and apply load limits.
9. **Believing a parent logger's level re-filters all child events:** in JUL, once a child logger accepts an event, parent handlers apply their own handler rules; misunderstanding this easily leaks or duplicates logs.
10. **Not testing when changing configuration:** can drop the audit channel or hide alerts during upgrades/deployments; always maintain a set of sample events to verify expected routes.

## 9. Practice Exercise

A Java application has three event lines: `checkout / INFO / order.created`, `checkout / WARNING / payment.retry`, and `audit / INFO / role.changed`. The requirements are: the operational channel receives all checkout events from `INFO` and above, the alert channel only receives checkout events from `WARNING` and above, and the audit channel only receives audit events from `INFO` and above. Questions:

1. Which destinations will each event reach?
2. If you only configure the `checkout` logger at level `INFO` and add one `WARNING` handler, is an `INFO` copy guaranteed to appear in the operational channel?
3. If the `payment.retry` log appears twice in the alert channel, which configuration locations need to be checked?
4. If the collector loses connection for 20 seconds, what questions must be answered before saying "no logs were lost"?

**Answer key:** `order.created` → operational; `payment.retry` → operational and alert; `role.changed` → audit. A `WARNING` handler does not write `INFO` records, so an operational handler with the appropriate level and filter is required. When duplicated, check multiple handlers targeting the same destination, parent–child logger relationships, and the collector's retry mechanism. On connection loss, you must check buffer type, queue limits, drop/retry policies, data retention time, process crashes, and whether the destination actually acknowledged receipt.

**Self-check:** If you can explain why an `INFO` line is lost even when a handler is set to `ALL`, how a `WARNING` is validly fanned out, the meaning of `additivity`/`useParentHandlers`, and the difference between in-JVM routing and collector routing, you have mastered the role of log routers in logging architecture.
