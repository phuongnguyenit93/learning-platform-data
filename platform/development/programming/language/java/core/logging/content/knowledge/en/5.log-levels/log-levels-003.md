# INFO — Log Level for Operational Events in Java Core Logging

## 1. What is INFO?

Within the **Log level** topic group, **INFO** is the level used to record normal operational events that are important enough for developers and operators to understand what the program did and what the outcome was. In Java SE, INFO is represented by the constant **java.util.logging.Level.INFO** in the **java.util.logging (JUL)** API.

For example, an application might log at INFO when it starts up successfully, finishes a background job, accepts an order, or rejects a request based on a known business rule. The goal of INFO is to capture **meaningful milestones** without logging every calculation, loop iteration, or method call.

~~~text
INFO | event=service.ready service=order-service version=1.2.0
INFO | event=order.accepted requestId=req-42 orderId=ord-7
INFO | event=job.completed jobId=job-19 count=250 durationMs=840
~~~

The three lines above illustrate an **application-chosen message format**, not JUL's default output. An INFO message can describe a success, a neutral outcome, or a **valid business rejection**. It does not automatically mean "there are no problems," nor does it guarantee that the record has been persisted to final storage.

**Practical takeaway:** when investigating a request, INFO should help answer "which step did the request reach, what was the key decision, and what was the final outcome?" Details needed only for debugging belong at FINE/FINER/FINEST or in another appropriate observability tool.

## 2. Where does INFO sit in the JUL level scale?

Common standard levels in JUL, ordered from highest threshold to lowest:

| Level | Level.intValue() | When to use | Passes Logger = INFO threshold? |
| --- | ---: | --- | --- |
| SEVERE | 1000 | Serious error; a critical operation or component failed | Yes |
| WARNING | 900 | Abnormal or degraded condition that needs attention | Yes |
| **INFO** | **800** | Operational milestones, notable business events and outcomes | **Yes** |
| CONFIG | 700 | Useful configuration information | No |
| FINE | 500 | General diagnostic information | No |
| FINER | 400 | More detailed diagnostic information | No |
| FINEST | 300 | Very granular detail | No |

JUL also provides **Level.ALL** to open the threshold for all levels and **Level.OFF** to disable logging for the corresponding component. Systems can define custom levels, so this table describes Java's standard levels.

When you write:

~~~java
logger.setLevel(Level.INFO);
~~~

The Logger **does not accept only the exact INFO level**. Under threshold rules, it lets through INFO and higher levels such as WARNING and SEVERE. Lower levels such as CONFIG and FINE do not pass. This is only one step in the pipeline: the **Logger Filter**, **Handler level**, **Handler Filter**, and output target can still drop the record.

Examples of calls at different levels:

~~~java
logger.fine("event=cache.lookup");       // Below INFO threshold
logger.info("event=service.ready");      // Meets threshold
logger.warning("event=backend.slow");    // Meets threshold
logger.severe("event=storage.failed");   // Meets threshold
~~~

These snippets are **usage examples inside code that already has a `logger` variable**, not standalone programs.

### Distinguishing INFO from WARNING, SEVERE, and FINE

- **INFO:** an expected event worth observing, such as **order.accepted** or **order.rejected reasonCode=INVALID_QUANTITY** when input violates a business rule.
- **WARNING:** an abnormal signal that could affect processing, such as a slow downstream dependency causing the system to retry.
- **SEVERE:** a serious failure condition, such as being unable to persist data and failing the request due to a system error.
- **FINE:** information for detailed diagnostics, such as cache hits/misses or internal algorithm steps.

Avoid elevating every HTTP 4xx or every expected exception to WARNING/SEVERE. Choose the level based on the **nature and impact** of the event rather than the Exception class name or the word "failed" in the message.

## 3. When should you emit an INFO log?

A good INFO log typically marks a **processing boundary**, a **state transition**, or a **business decision**.

| Event category | Sample event name | Fields to include if appropriate |
| --- | --- | --- |
| Service lifecycle | service.started, service.ready | service, version, environment |
| Background job completion | job.completed | jobId, outcome, processedCount, durationMs |
| Business action accepted | order.accepted | requestId, orderId, outcome |
| Rejected by a known rule | order.rejected | requestId, orderId, reasonCode |
| State transition | shipment.dispatched | shipmentId, oldStatus, newStatus |
| Data import batch completion | import.completed | batchId, importedCount, rejectedCount |
| Significant operational config change | mode.switched | component, oldMode, newMode, reasonCode |

Not every category must use INFO. For example, a data import running every second may need aggregated metrics and fewer INFO logs, whereas a rare and critical business event may need explicit logging for investigation.

**Three useful questions before adding INFO:**

1. Without this log, would it be difficult to understand the system's state, outcome, or key decision?
2. Is the event meaningful enough to appear in production under real traffic?
3. Can a reader use the message and its accompanying fields to search, correlate, and explain what happened?

If the answers are mostly "no," the content is likely better suited for FINE, a metric, or tracing.

## 4. What should not be logged at INFO

Do not use INFO like a **println()** statement for every step of execution. The following practices quickly degrade log value:

- Logging every loop iteration, temporary variable, conditional check, map/filter operation, or high-frequency cache access.
- Logging the same "request started" event in the controller, service, and repository, causing operators to see three redundant lines.
- Logging entire request/response bodies or sensitive data just for debugging convenience.
- Logging a stack trace for an expected input validation case that was handled normally.
- Logging a heartbeat every second when the system has no need to analyze individual heartbeats.
- Logging **order.completed** before the transaction has actually committed, making the message contradict the actual state if a rollback occurs later.

In high-traffic systems, logging INFO for **every HTTP request** may be the intended purpose of an access log mechanism, but you must account for the cost and avoid duplicating the same information in other layers. INFO should not become a duplicate of every metric or trace.

## 5. What should a useful INFO log contain?

An example message better than "Finished":

~~~text
INFO event=order.rejected requestId=req-105 orderId=ord-23 outcome=REJECTED reasonCode=INVALID_QUANTITY
~~~

Components to consider:

- **timestamp:** when the event occurred; use a consistent convention, preferring UTC when centralizing logs.
- **level:** INFO, along with the logger or service name to identify the source.
- **event:** a stable event name such as order.rejected or job.completed.
- **requestId/correlationId/jobId:** identifiers that link records belonging to the same flow.
- **objectId:** necessary object identifiers permitted by data policy.
- **outcome and reasonCode:** standardized result and reason, convenient for querying.
- **durationMs, attempt, count:** useful figures for multi-step processing.

JUL automatically provides information such as level, timestamp, and logger name in `LogRecord`, but it **does not automatically generate event names, requestId, or traceId** for your application. If you want JSON-style structured logging, you need an appropriate formatter/encoder or pipeline; the INFO level itself does not dictate the data format.

Avoid interpolating raw user input directly into an unescaped message. Input containing newlines or control characters can forge log lines (**log injection**). Never log passwords, tokens, cookies, private keys, card data, or personal information beyond legitimate requirements.

## 6. Why does calling logger.info() produce no log output?

In JUL, a record must pass through multiple stages:

~~~text
logger.info(message)
     |
     v
Logger: does effective level allow INFO through?
     |-- No -> stop
     v
Logger: does Filter accept?
     |-- No -> stop
     v
Handler A: do level and Filter accept?
     |-- Yes -> Formatter -> console
     |
     +---- Handler B: do level and Filter accept?
     |          Yes -> Formatter -> file
     |
     +---- Handlers on parent Logger (if useParentHandlers=true)
                Check parent Handler's own conditions
~~~

**Conditions to understand accurately:**

1. **Logger level:** setting the Logger to WARNING blocks INFO. When a Logger uses **setLevel(null)**, its effective level can be inherited from the parent Logger hierarchy.
2. **Logger Filter:** can block a specific INFO event right at the source.
3. **Handler level:** if the Logger is at INFO but the Handler is at WARNING, that handler still drops INFO.
4. **Handler Filter:** can drop INFO based on event, source, or context.
5. **Parent Logger:** if **useParentHandlers=true**, the record can reach Handlers attached to parent Loggers. In JUL, the Filter/level of **those Handlers** takes effect; do not assume Filters on every parent Logger are re-executed for records propagating up from a child Logger.
6. **Output:** the Formatter, stream, file, or collector may be configured differently, encounter an I/O error, or not have flushed its buffer yet.

Illustration table when **Logger level = INFO** and no Filter rejects the record:

| Record | Handler level = ALL | Handler level = INFO | Handler level = WARNING |
| --- | --- | --- | --- |
| FINE | Blocked by Logger | Blocked by Logger | Blocked by Logger |
| INFO | Passes Handler threshold | Passes Handler threshold | Blocked by Handler |
| WARNING | Passes Handler threshold | Passes Handler threshold | Passes Handler threshold |
| SEVERE | Passes Handler threshold | Passes Handler threshold | Passes Handler threshold |

"Passes threshold" does not guarantee the record is saved: Filters and destination write capability still need to be checked.

## 7. Standalone Java 17+ example

The following program demonstrates:

- The Logger accepts INFO and above.
- The Handler initially accepts all levels that reach it.
- FINE is blocked by the Logger; INFO and WARNING appear.
- After the Handler is changed to WARNING, INFO is no longer emitted even though the Logger still allows it.
- JUL messages using **{0}**, **{1}** parameters are substituted in the right positions by the Formatter.

Create the file **InfoLevelDemo.java** with the complete code below:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class InfoLevelDemo {
    private static final Logger LOG =
            Logger.getLogger("examples.logging.info");

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        output.setLevel(Level.ALL);
        LOG.addHandler(output);

        try {
            LOG.fine("event=cache.lookup");
            LOG.info("event=service.started service=catalog");
            LOG.log(Level.INFO,
                    "event=order.accepted orderId={0} quantity={1}",
                    new Object[] {"ord-7", 2});
            LOG.warning("event=inventory.slow dependency=stock");

            output.setLevel(Level.WARNING);
            LOG.info("event=order.completed status=OK");
            LOG.warning("event=dependency.retry dependency=stock");
        } finally {
            LOG.removeHandler(output);
            output.flush();
        }
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac InfoLevelDemo.java
java InfoLevelDemo
~~~

**Exact stdout:**

~~~text
INFO | event=service.started service=catalog
INFO | event=order.accepted orderId=ord-7 quantity=2
WARNING | event=inventory.slow dependency=stock
WARNING | event=dependency.retry dependency=stock
~~~

### Step-by-step explanation

1. **LOG.setUseParentHandlers(false)** prevents records from also propagating to parent Logger Handlers, avoiding duplicate output from environment configuration.
2. **LOG.setLevel(Level.INFO)** keeps `LOG.fine(...)` from being passed down to the Handler.
3. **output.setLevel(Level.ALL)** allows the Handler to accept both INFO and WARNING that passed the Logger in the first phase.
4. **LOG.info(...)** creates the first INFO log. **LOG.log(Level.INFO, ...)** creates the second log and passes an argument array.
5. The Formatter calls **formatMessage(record)**, which replaces **{0} → ord-7** and **{1} → 2**. This is JUL parameter syntax using `MessageFormat`, not SLF4J's **{}** syntax.
6. The first WARNING is also emitted because WARNING has a higher level value than INFO.
7. **output.setLevel(Level.WARNING)** raises the Handler threshold. Afterward, **LOG.info("event=order.completed...")** is dropped by the Handler, while the final WARNING is emitted.
8. **StreamHandler(System.out, Formatter)** uses stdout and a fixed format so output does not depend on timezone, locale, or the default `SimpleFormatter` format. **JUL's default ConsoleHandler typically writes to stderr**.
9. Overriding **publish()** and calling **flush()** pushes records to stdout immediately. The program does not close the Handler attached to `System.out`, because closing a `StreamHandler` can close the underlying `System.out` stream as well.

Corresponding decision table:

| Call | Logger level = INFO | Handler before/after level change | Result |
| --- | --- | --- | --- |
| FINE cache.lookup | Blocked | Does not reach Handler | Not emitted |
| INFO service.started | Allowed | ALL | Emitted |
| INFO order.accepted | Allowed | ALL | Emitted |
| WARNING inventory.slow | Allowed | ALL | Emitted |
| INFO order.completed | Allowed | WARNING | Not emitted |
| WARNING dependency.retry | Allowed | WARNING | Emitted |

This is a minimal example for learning purposes. In a real system, use the application's unified logging configuration and a proper log collection policy.

## 8. Common ways to log INFO in JUL

### A. The info(String) method

~~~java
logger.info("event=job.completed jobId=job-19 outcome=SUCCESS");
~~~

Use when the message is short, cheap to construct, and clear. This snippet assumes a **logger** variable of type **java.util.logging.Logger** is already available.

### B. The log(Level.INFO, message) method

~~~java
logger.log(Level.INFO, "event=service.ready service=catalog");
~~~

Use when you want a uniform API call across multiple levels. Requires importing **java.util.logging.Level**.

### C. JUL indexed parameters

~~~java
logger.log(Level.INFO,
        "event=order.accepted orderId={0} quantity={1}",
        new Object[] {orderId, quantity});
~~~

If the Formatter calls **formatMessage(record)**, arguments are inserted into the message using **MessageFormat**. Do not mistakenly use the **{}** placeholder syntax common in SLF4J. The code above is a snippet assuming **orderId** and **quantity** already exist.

### D. Deferring message construction with Supplier

~~~java
logger.info(() -> "event=batch.completed batchId=" + batchId
        + " processedCount=" + processedCount);
~~~

The **info(Supplier<String>)** overload has existed since Java 8. If the **Logger** blocks INFO by threshold, it does not need to invoke the Supplier to build the message. However, if the Logger accepts it but a **Handler** blocks it, the Supplier may already have been evaluated before the Handler filters it out. Lazy messages do not replace a well-designed level/Filter/Handler setup.

### E. Guarding an expensive computation manually

~~~java
if (logger.isLoggable(Level.INFO)) {
    logger.info(createExpensiveSummary());
}
~~~

**isLoggable(Level.INFO)** is useful when computing the message is expensive. This check tests loggability against the Logger's threshold; it **does not guarantee** the record will be written by a Handler. For simple strings, `Supplier` is usually more convenient.

Patterns A–E are code snippets inside an application context where required variables are already declared, not standalone Java files. The complete program in section 7 is a directly runnable example.

## 9. Configuring the INFO threshold in Java

There are two common approaches:

**In code:**

~~~java
Logger ordersLogger = Logger.getLogger("com.example.orders");
ordersLogger.setLevel(Level.INFO);
~~~

This sets the Logger threshold to INFO, while each Handler still applies its own level and Filter. This is a snippet that requires importing `Logger` and `Level`.

**Via LogManager and a logging.properties file**, for example:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
~~~

Running an application whose main class is **com.example.Main** with the JUL configuration:

~~~bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
~~~

This command is a **template for an application with class com.example.Main**, not the command to run the `InfoLevelDemo` example. In **InfoLevelDemo**, the code intentionally configures its own Logger/Handler and disables parent Logger Handlers to produce deterministic stdout; therefore, the root Logger's `ConsoleHandler` configuration in a properties file does not control that demo's output.

Keep in mind:

- **.level=INFO** configures the root Logger's level; a Logger that has not set its own level can inherit the effective level from its parent.
- **java.util.logging.ConsoleHandler.level=INFO** configures the ConsoleHandler's own level, which must be considered alongside the Logger threshold.
- `LogManager` reads configuration at initialization time. Programmatic configuration or frameworks can override certain properties.
- `ConsoleHandler` typically writes to **System.err**, not `System.out`, and `SimpleFormatter` includes different context fields than the custom example above.
- For applications using explicit modules, code depending on JUL requires **requires java.logging;** in `module-info.java`:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

The `module-info.java` snippet only illustrates JPMS usage; the single-file Java program in section 7 does not need this file.

## 10. INFO in concurrent, multi-service, and multi-output systems

In multi-request applications, INFO logs from different requests can interleave. Each individual INFO line needs correlation identifiers:

~~~text
INFO event=order.received requestId=req-42
INFO event=order.received requestId=req-43
INFO event=order.accepted requestId=req-42 orderId=ord-7
INFO event=order.rejected requestId=req-43 reasonCode=INVALID_QUANTITY
~~~

Log ordering does not necessarily imply a causal relationship between two requests. **requestId/correlationId** helps filter records for a single request; for background jobs, use an appropriate **jobId/messageId**.

When a request crosses into an `Executor`, `CompletableFuture`, virtual thread, or another service, context must be **propagated and cleared** using the proper mechanism. Never assume **ThreadLocal** or **MDC** automatically propagates across all asynchronous boundaries. Vanilla JUL does not automatically attach `traceId`/`spanId`; if using OpenTelemetry or a logging framework, integrate context propagation properly.

A Logger can have multiple Handlers: for example, console for operational events and a file for diagnostic archiving. Handler A might have threshold INFO and Handler B threshold WARNING; the same INFO record may only be emitted by A. If you only want to exclude one event type from the console, attach a Filter to the console Handler rather than placing a Filter on the source Logger, which would drop the log for all other Handlers too.

## 11. How do INFO, metrics, tracing, and audit logs differ?

| Tool | Best answers | Example |
| --- | --- | --- |
| INFO/application log | Specific progression and outcome of an event | order.rejected with requestId, reasonCode |
| Access log | HTTP request info at the server/proxy edge | method, route, status, latency |
| Metric | Rates, ratios, and aggregated trends | Request count, error rate, p95 latency |
| Distributed tracing | Path and timing across spans/services | Request slow in inventory service or database |
| Audit log | Evidence of actions requiring integrity and access control | Who changed permissions or approved a transaction |

Avoid turning INFO into a storage bin for **all** observability data. Metrics are generally better suited for high-frequency measurements and SLOs; tracing helps explain execution paths. Audit logs may carry legal requirements and tamper-resistance rules, so they **must not automatically** be replaced by ordinary INFO logs. In systems with auditing requirements, never arbitrarily sample or disable mandatory events.

## 12. Security and cost control when INFO is enabled

INFO is frequently enabled in production. Therefore, the INFO level should be managed as part of system design:

1. **Minimize data at the source:** do not log tokens, passwords, session cookies, API keys, transaction secrets, or sensitive bodies.
2. **Choose appropriate IDs:** log `requestId`, `jobId`, and `orderId` only when needed; follow data policies if IDs can be linked to individuals.
3. **Standardize events:** use stable names like `job.completed` and `reasonCode` instead of arbitrary user-supplied strings.
4. **Prevent log injection:** escape newlines and control characters when untrusted data must be output; use a formatter/encoder with clear rules.
5. **Manage volume:** do not log INFO inside hot loops; aggregate counts and durations when possible.
6. **Understand asynchronicity:** logger/collector pipelines may buffer and drop records on abrupt shutdown; the INFO level does not guarantee durable persistence.
7. **Define retention and read access:** specify retention periods, who can access logs, searchability, and ingest/long-term storage costs.
8. **Test under realistic load:** if adding INFO per request, measure log volume and CPU/I/O overhead, verifying no significant impact on business flows.

For example, in a job processing one million items, instead of logging INFO for every item, log INFO only at **job.started** and **job.completed** with **processedCount**, **failedCount**, and **durationMs**; per-item details can use controlled FINE/DEBUG or a dedicated error-handling mechanism.

## 13. Common mistakes when working with INFO

| Issue | Common cause | How to handle |
| --- | --- | --- |
| Calling info() produces no log | Logger is at WARNING/SEVERE or inherits a higher level | Check the Logger's effective level |
| INFO is lost even though Logger is at INFO | Handler is at WARNING or a Filter blocks it | Check Handler level and Filters |
| INFO appears twice | Handlers on both the Logger and parent Logger receive it | Check `useParentHandlers` and the Handler list |
| Test sees no stdout | JUL `ConsoleHandler` typically writes to stderr | Check stderr, or create a `StreamHandler(System.out)` for demos |
| Placeholder {0} is not substituted | Formatter does not call `formatMessage`, wrong parameters, or wrong API used | Use JUL `log(Level, String, Object[])` and an appropriate Formatter |
| INFO floods production | Logging too granularly or repeating across multiple layers | Log only meaningful events; use FINE/metrics |
| Correlation lost between lines | Missing `requestId`/`jobId` or context not propagated | Propagate correlation context properly across threads and services |
| Records contain sensitive data | Logging entire objects, payloads, or exception messages | Redact/minimize data at the source and configure encoders |
| INFO reports completion then transaction rolls back | Logging the outcome before confirmation | Move the log to the appropriate commit/success point |
| Config change does not change INFO behavior | `logging.properties` not loaded, different backend used, or code overrides it | Check the actual logging backend and runtime configuration |

**Note on frameworks:** SLF4J is a facade, while Logback and Log4j 2 are popular backends. They also have INFO, but their APIs and parameter syntax can differ from JUL. For example, **logger.info("orderId={}", id)** is SLF4J style, whereas JUL uses **{0}** with `MessageFormat` arguments. An application using SLF4J + Logback must inspect the actual backend's levels/Filters/Appenders rather than modifying JUL and assuming logs will change.

## 14. Checklist for using INFO on a new event

1. Does this event represent a genuinely important **state, decision, outcome, or operational boundary**?
2. If this is an anomaly, would WARNING/SEVERE be more appropriate? If it is step-by-step diagnostic info, would FINE be better?
3. Are the event name, outcome, and reasonCode stable for searching across versions?
4. Does it include **requestId/jobId** and necessary context without carrying sensitive data?
5. Is the expected INFO volume acceptable for CPU, I/O, and storage costs?
6. Do **Logger level**, **Logger Filter**, **Handler level**, **Handler Filter**, and the collector all allow this record to be written?
7. When testing success, valid rejection, and technical error branches, do the logs help distinguish all three outcomes?

**Conclusion:** **Level.INFO** is the level for recording normal but valuable operational milestones in Java Logging. Understanding INFO within the **Logger → Filter → Handler → Formatter/output** pipeline, logging events with context, and controlling volume costs will make logs a reliable source of truth for operations and troubleshooting.
