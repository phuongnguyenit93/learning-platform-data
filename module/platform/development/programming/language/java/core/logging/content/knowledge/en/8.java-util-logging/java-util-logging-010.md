# Limitations of Java Util Logging (JUL)

## 1. Understanding JUL and the Scope of This Lesson

**Java Util Logging (JUL)** is the built-in logging system in the JDK, belonging to the `java.util.logging` package and the `java.logging` module. Applications can write logs without adding external libraries:

```java
import java.util.logging.Logger;

public class OrderService {
    private static final Logger LOG =
            Logger.getLogger(OrderService.class.getName());

    public void accept(String orderId) {
        LOG.info("event=order_accepted orderId=" + orderId);
    }
}
```

This is an **illustrative class** without a `main` method. JUL is not just `System.out.println`. Its core components include:

- `Logger`: receives event logging calls, applies levels and filtering rules.
- `Level`: `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST`, along with `OFF` and `ALL`.
- `LogRecord`: the data for a single event, including level, message, parameters, timestamp, logger name, source information, `Throwable`, and other metadata.
- `Handler`: sends events to the console, file, stream, socket, or custom destinations.
- `Formatter`: converts a `LogRecord` into a readable/writable string.
- `Filter`: accepts or rejects events based on custom conditions.
- `LogManager`: organizes loggers and manages configuration.

**The limitations of JUL** should be understood as the difference between **capabilities built into the JDK** and **capabilities that require custom extensions or external tools**. JUL can still be customized using handlers, formatters, filters, and bridges. The practical question is: are those features provided out of the box, easy to configure, backed by a suitable ecosystem, and worth the maintenance cost?

This lesson focuses on common limitations encountered when using JUL in systems with multiple components, centralized log storage, high log volume, or advanced observability requirements. It does not conclude that JUL is inherently unsuitable for all production applications.

## 2. Overview of Limitations and Workarounds

| Need | Standard JUL Support | What Must Be Added for Higher Requirements |
|---|---|---|
| Level | `SEVERE`, `WARNING`, `INFO`, `FINE`… | Name mapping and policies when integrating `ERROR/WARN/DEBUG/TRACE` |
| Formatting | `SimpleFormatter`, `XMLFormatter`, custom `Formatter` | JSON schema, structured encoder, and full field escaping |
| Contextual data | `LogRecord` with message, parameters, source, timestamp, and exception | MDC, `traceId`/`requestId`, named key–value fields |
| Output destinations | `ConsoleHandler`, `FileHandler`, `StreamHandler`, `SocketHandler`, `MemoryHandler` | Complex routing, retry, buffering, backpressure, and collectors |
| File rotation | `FileHandler` by size/file count | Daily rolling, compression, age-based retention, or special policies |
| Message template | `{0}`, `{1}` via `MessageFormat`/`formatMessage` | Does not understand SLF4J's `{}` by default |
| Lazy message | Supports `Supplier<String>` | Does not automatically defer all argument expressions |
| Async | Can integrate custom handler/queue | No feature-rich generic async appender built into the JDK |
| Configuration | `LogManager`, `logging.properties`, runtime API | Profiles, dynamic reload, centralized control, and framework integration |
| Observability | Event logs to aid diagnostics | Metrics, distributed tracing, correlation, and guaranteed audit trails |

Not having a feature built in **does not mean** it cannot be done with JUL. However, writing many custom extensions increases responsibility for correctness, safety, testing, and operations.

## 3. Formatting Limitations: Text and XML Built In, JSON Requires Additional Tools

JUL comes with `SimpleFormatter` for text and `XMLFormatter` for XML. Users can write a custom `Formatter`. However, standard JUL **does not provide a general-purpose JSON formatter/encoder with a business field schema** comparable to dedicated structured logging solutions.

Example of a structured format that an observability system might require:

```json
{
  "timestamp": "2026-11-09T08:15:03.125Z",
  "level": "ERROR",
  "service": "order-api",
  "logger": "com.example.orders.OrderService",
  "requestId": "req-42",
  "event": "order_save_failed",
  "orderId": "ORD-7"
}
```

This is an **illustrative JSON sample**, not automatic JUL output. To produce this format, the application must have a data source for each field, a formatter/serializer, and a mechanism to deliver records to a collector.

There are three common approaches:

1. Write a custom `Formatter` and use a reliable JSON serializer library to handle the fields.
2. Install a dedicated formatter/handler from an external library while keeping the JUL API.
3. Use an appropriate bridge to forward JUL events to a backend with a structured logging encoder.

**Do not build JSON via string concatenation**: quotation marks, newlines, backslashes, and control characters in messages/exceptions must be escaped properly. Timezones, data types, keys, sizes, masking, and stack trace handling must be standardized. Merely outputting a line that looks like JSON does not guarantee the collector can parse it or that the data is stored reliably.

### 3.1. `SimpleFormatter` Is Customizable, but Not Like PatternLayout

JUL has the `java.util.logging.SimpleFormatter.format` property to change the text format, using `java.util.Formatter`-style conversions. Example `logging.properties`:

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format=%4$s %3$s - %5$s%6$s%n
```

In `SimpleFormatter`, `%4$s` is the level, `%3$s` is the logger name, `%5$s` is the formatted message, and `%6$s` is the Throwable part if present. This is **not** the `%level %logger %msg%n` pattern of Logback/Log4j 2.

For example, an application with a compiled main class `com.example.Main` can run:

```bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
```

This is an **illustrative command**; a real class and configuration file are required. A framework or container may customize how logging configuration is loaded. Changing the text format does not turn `requestId=...` inside the message into an independent JSON field.

## 4. Correlation Context Limitations: JUL Has No Standard MDC

A log record has a logger name, timestamp, message, level, and standard fields. However, with web requests, many tasks run interleaved; you need to know **which request/job an event belongs to**, usually via `requestId`, `traceId`, `spanId`, or `jobId`.

In Logback/SLF4J/Log4j 2, MDC or Thread Context is the standard mechanism for attaching context to logs. **Standard JUL does not have an equivalent MDC/key–value map API built into `LogRecord`**. You can log it manually:

```java
LOG.log(Level.INFO,
        "requestId={0} event=order_accepted orderId={1}",
        new Object[]{"req-42", "ORD-7"});
```

The displayed content includes the request ID, but at the standard `LogRecord` level, this is primarily a **message template and parameters**, not a map of named business fields. A collector that wants to query `requestId` separately may have to parse text or receive an additionally generated schema.

Solutions include passing context explicitly, creating a structured event model, using a custom handler/formatter, or integrating tracing and a backend that supports MDC. Do not put dynamic data into the **logger name** such as `Logger.getLogger("order." + orderId)`: logger names should remain stable by class/package or category.

**Thread pool note:** if you use `ThreadLocal` yourself for context, you must clean it up with `finally` and propagate it properly when switching to `ExecutorService`, `CompletableFuture`, or callbacks. Reused threads can cause a subsequent request to mistakenly inherit the previous request's context. A formatter cannot recover a context field that was never passed to the event.

## 5. Placeholders, Message Parameters, and Lazy Evaluation

### 5.1. JUL Does Not Use `{}` by Default

In JUL, parameterized messages typically use `MessageFormat` syntax:

```java
LOG.log(Level.INFO,
        "orderId={0} result={1}",
        new Object[]{"ORD-7", "ACCEPTED"});
```

Resulting message portion:

```text
orderId=ORD-7 result=ACCEPTED
```

A formatter should use `formatMessage(record)` to substitute parameters. If a custom formatter only calls `record.getMessage()`, the `{0}` template may remain unformatted.

Compared to JUL:

```java
// SLF4J (requires dependency and a declared log variable):
log.info("orderId={} result={}", orderId, result);

// JUL (JDK):
LOG.log(Level.INFO,
        "orderId={0} result={1}",
        new Object[]{orderId, result});
```

These lines are **API illustrations**, not standalone programs. SLF4J-style `{}` placeholders are not automatically substituted by JUL. `MessageFormat` also has its own rules for single quotes, numbers/dates, and locales; test carefully when logging multilingual content or when stable output is required.

### 5.2. JUL Supports Lazy Messages, but You Must Use the Right Overload

JUL provides overloads that accept `Supplier<String>`:

```java
// If the FINE level is disabled, the lambda does not need to be invoked:
LOG.log(Level.FINE, () -> buildDetailedMessage());
```

Meanwhile:

```java
// The method is called by Java before the logger receives the arguments:
LOG.log(Level.FINE, "detail={0}",
        new Object[]{buildDetailedMessage()});
```

Both snippets assume `LOG` and `buildDetailedMessage()` already exist. In the second snippet, Java **evaluates the expression when creating the array**, even if the log is filtered out. This is a limitation of the call pattern, not proof that JUL completely lacks lazy logging. When parameterized formatting and cost optimization are needed, choose the appropriate API/overload and measure actual performance.

## 6. Outputs and File Policies Are Less Rich Than Dedicated Backends

JUL includes these handlers in the JDK:

- `ConsoleHandler`: outputs to the console, typically via `System.err`.
- `FileHandler`: writes to files, with rotation by **size threshold** and **file count**.
- `StreamHandler`: writes to an application-provided stream.
- `SocketHandler`: sends data over a socket; reliability must be handled in the overall architecture.
- `MemoryHandler`: buffers a number of records in memory and pushes them to a target handler based on a trigger condition; **not equivalent** to a general-purpose async appender.

For requirements like **daily file rotation, compressing old files, keeping exactly 14 days, and automatic age-based deletion**, standard `FileHandler` does not provide that full rolling policy set in a single built-in configuration. A dedicated handler/agent or a backend with suitable rolling policies is needed.

For centralized logging over the network, the application must decide:

1. When the collector is disconnected, should it retry, buffer, drop records, or block requests?
2. Are there limits on queue capacity, retry count, and backpressure?
3. If the application crashes before flushing, which events might be lost?
4. Could multiple processes write to the same files concurrently or exceed disk limits?
5. Who is responsible for retention, access permissions, and transport encryption if needed?

These are **operational problems**; swapping formatters does not solve them.

## 7. Asynchronous Writing and Performance

In a basic JUL configuration, handlers typically process logs on the event-emitting execution path; formatting and I/O can increase latency. This depends on the handler, formatter, buffering, operating system, and output target. There is no basis to conclude that every JUL application is slow.

The JDK **does not bundle a feature-rich generic async appender like some logging backends**. You can write a custom `Handler` using a queue and worker, use an external library, or write to stdout for a collection agent. When choosing async, you need clear rules for:

- Queue bounds and full-queue behavior: block, drop, prioritize, or shed load.
- When to format/snapshot context to avoid reading mutable data that has already changed.
- Flush/shutdown rules and the risk of losing records when the process dies.
- Emission order versus write order, and event timestamp versus I/O timestamp.
- Monitoring queue backlog, dropped events, CPU, allocations, and latency.

Async **does not automatically guarantee exactly-once delivery or zero log loss**. In low-load systems, a custom async handler can add more complexity than benefit. Measure throughput, latency, and memory before and after.

## 8. LogManager Configuration and Pitfalls Often Mistaken for API Limitations

JUL uses `LogManager` and can read `logging.properties` or be configured via API. Not every application automatically loads a file from an arbitrary path; containers and frameworks may use their own configuration or `LogManager`.

### 8.1. Check Levels on Both the Logger and the Handler

Example:

```java
LOG.setLevel(Level.FINE);
consoleHandler.setLevel(Level.INFO);
LOG.fine("event=debug_detail");
```

This snippet assumes `consoleHandler` is attached to `LOG`. The logger allows `FINE`, but the handler at `INFO` still drops the record. Conversely, if the logger only allows `INFO`, setting the handler to `ALL` will not make `FINE` appear.

Other factors include `Filter` instances on the logger/handler, inherited level configuration, where handlers are attached, and forwarding to parent loggers.

### 8.2. Parent Handlers Can Cause Duplicate Logs

With a logger named `com.example.orders.OrderService` and a hierarchical configuration, a record can be sent to both a directly attached handler and a parent logger's handler when `useParentHandlers` is enabled. As a result, a single `LOG.log(...)` call appears multiple times on the console.

`setUseParentHandlers(false)` can be appropriate in an example with a custom-configured handler, but in production you must understand the shared collection pipeline before disabling propagation; doing so carelessly can cause logs to disappear from the main pipeline.

### 8.3. Runtime Configuration and Environments

JUL provides an API to adjust logger levels at runtime and a `LogManager` mechanism to reload configuration in an implementation-specific way. This **does not mean** the JDK provides an admin UI, automatic file-change watching, a secure configuration distribution system, or production/staging profiles out of the box for every application.

When an application is deployed through a framework, check the actual logging stack and how the framework manages configuration. Placing `logging.properties` in a source directory does not guarantee the JVM will use it.

## 9. Ecosystem: JUL Is a Concrete API, SLF4J Is a Facade

When business code writes:

```java
private static final java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger(MyService.class.getName());
```

the code depends directly on the **JUL API**. In an application using SLF4J, logging calls go through a facade to a provider/backend such as Logback or Log4j 2; the backend can be swapped with fewer changes to application code.

However, **you do not necessarily have to rewrite every JUL line** to send logs to another backend. You can use a JUL → SLF4J bridge or integrate at the collection layer, depending on your goals.

When using a bridge, verify forwarding direction, levels, context, exceptions, logger names, and overhead. In particular, avoid configuring two opposing bridges that cause an infinite loop **JUL ↔ SLF4J/backend**, or attaching both an old JUL handler and a new bridge to the same destination, causing duplicate logs.

A bridge also **cannot automatically recover a `traceId` that was never attached to the event**. It can only forward existing data or whatever the adapter is designed to generate.

### Does `System.Logger` from Java 9 Solve Everything?

`java.lang.System.Logger` is a platform logging API introduced in Java 9 with a provider mechanism; it does not mean JUL automatically gains standard MDC, JSON encoders, async/rolling policies, and full distributed tracing. You must distinguish between the **API the application calls**, the **provider/backend that processes it**, and the **collector that stores it**.

## 10. Observability, Auditing, and Security

### Logs Do Not Replace Metrics or Traces

JUL records events emitted by the application, but it does not automatically create distributed traces across services, compute SLOs/error rates, or provide a complete metrics system. A series of logs sharing the same `traceId` helps correlate events; it does not provide parent/child span relationships or tracing system timings without additional integration.

For error metrics, do not assume **counting `SEVERE` lines** equals counting failed requests: a single exception may be logged at multiple layers, or records may be filtered/sampled. Metrics per unit of work should be designed explicitly.

### Regular Logs Are Not Automatically an Audit Trail

An `INFO "user changed role"` event does not guarantee an audit trail meeting requirements for integrity, access control, tamper resistance, retention period, or principal attribution. Those guarantees must be designed separately; they do not depend on the logger name or logging framework.

### No Automatic Comprehensive Redaction

JUL does not automatically mask passwords, access tokens, API keys, session cookies, or sensitive data in messages and exceptions. Custom `Filter`/`Formatter` implementations can help redact data, but you must check messages, parameters, `Throwable` instances, context, logger names, collectors, and storage destinations. Input containing newlines/control characters can cause **log injection** if a formatter allows multi-line spoofing; use deliberate escaping/encoding and avoid logging arbitrary payloads.

## 11. Standalone Java 17+ Example: Demonstrating Built-In JUL Limitations and Capabilities

The following example uses **only the JDK**, with no extra dependencies. It demonstrates how JUL handles `{0}` placeholders, does not understand `{}` by default, filters the `FINE` level before invoking a supplier, and retains `Throwable` for the formatter to process.

Create the file `JulLimitsDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class JulLimitsDemo {
    private static final Logger LOG =
            Logger.getLogger(JulLimitsDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String line = record.getLevel().getName()
                        + " | " + record.getLoggerName()
                        + " | " + formatMessage(record);
                Throwable error = record.getThrown();
                if (error != null) {
                    line += " exception="
                            + error.getClass().getSimpleName()
                            + ":" + error.getMessage();
                }
                return line + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        LOG.log(Level.INFO,
                "requestId={0} event=order_received orderId={1}",
                new Object[]{"req-42", "ORD-7"});

        LOG.info("SLF4J-style placeholder remains: {}");

        AtomicInteger supplierCalls = new AtomicInteger();
        LOG.log(Level.FINE, () -> {
            supplierCalls.incrementAndGet();
            return "expensive_detail";
        });
        LOG.info("fineSupplierEvaluations=" + supplierCalls.get());

        try {
            throw new IllegalStateException("cache unavailable");
        } catch (IllegalStateException error) {
            LOG.log(Level.SEVERE, "event=cache_refresh_failed", error);
        }

        console.flush();
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 JulLimitsDemo.java
java JulLimitsDemo
```

Lines printed to the console:

```text
INFO | JulLimitsDemo | requestId=req-42 event=order_received orderId=ORD-7
INFO | JulLimitsDemo | SLF4J-style placeholder remains: {}
INFO | JulLimitsDemo | fineSupplierEvaluations=0
SEVERE | JulLimitsDemo | event=cache_refresh_failed exception=IllegalStateException:cache unavailable
```

`ConsoleHandler` writes to **stderr** by default, so the output above is stderr content; the program does not write to stdout itself. The example formatter intentionally omits timestamps and prints only the exception type/message for stable output. In real operations, include timestamps, timezones, correlation IDs, and full stack traces/cause chains where appropriate.

**Output explanation:**

1. `formatMessage(record)` replaces `{0}` and `{1}` with `req-42` and `ORD-7`.
2. JUL does not substitute SLF4J-style `{}` in `LOG.info(...)` calls without parameters.
3. The `INFO` level filters out `FINE` before executing `Supplier<String>`; `supplierCalls` remains 0.
4. Setting the handler to `ALL` does not force the logger to emit `FINE` because the logger has already filtered out the event.
5. `LOG.log(Level.SEVERE, message, error)` preserves the `Throwable` in the record; the custom formatter decides which parts to output. Not printing the stack trace in this example **does not mean JUL does not support passing exceptions**.
6. Fields like `requestId` are embedded into the message text and do not automatically become JSON fields or MDC entries.

## 12. When to Keep Using JUL and When to Change

| Situation | Option to Consider | Reason |
|---|---|---|
| Small CLI/tool, minimal-dependency Java library | JUL is usually sufficient | Built into the JDK; basic logger, level, and handler support |
| Service with moderate logging volume, stdout collected by an agent | JUL can meet the need | External pipeline handles collection and storage |
| Multiple microservices needing JSON schema, MDC, and trace correlation | Dedicated backend/encoder or additional library | Reduces effort of self-implementing context and field mapping |
| Need async with backpressure, multiple destinations, rolling/compression/retention | Dedicated backend or proven handler/agent | Provides built-in operational policies |
| Framework already integrates SLF4J + a backend | Prefer checking and leveraging that stack | Avoids multiple configurations/bridges producing duplicate output |
| Large JUL system that works stably | Evaluate specific needs before migrating | Migration brings no automatic benefit without a real problem to solve |

**There is no rule that every large application must abandon JUL.** A properly configured JUL pipeline with a collection agent and clear requirements can still work well. Conversely, writing many custom handlers, formatters, thread contexts, and rolling policies just to avoid a dependency can introduce additional risk.

An improvement roadmap can follow this order: define goals → inspect the running API/backend/handlers → standardize events and levels → add context and masking → test a formatter/agent/bridge or alternative backend → measure latency, log loss, stack traces, duplicate volume, and searchability in a real environment.

## 13. Common Errors and How to Identify the Root Cause

| Symptom | What to Check | How to Resolve |
|---|---|---|
| `FINE` not printed even though enabled | Logger level, handler level, filters, and inheritance | Enable across the entire logging path, not just one level |
| Duplicate logs on console | Parent handlers, additivity/bridges, and collectors | Check `useParentHandlers` and the event path |
| `{}` placeholder left unformatted | Using SLF4J syntax in JUL | Use `{0}` and the proper parameter overload |
| `{0}` placeholder left unformatted | Formatter only reads `getMessage()` or parameters are missing | Use `formatMessage(record)` and pass arguments |
| Missing stack trace | `Throwable` not passed or formatter does not output it | Use an overload accepting `Throwable` and a suitable formatter |
| Missing `requestId` | Context not passed/logged, or lost across thread switches | Design correlation and verify async boundaries |
| Want JSON but only see text | JSON formatter/encoder not configured | Add an appropriate serializer/schema/collector |
| Files do not rotate daily | `FileHandler` configured by size/file count | Use a suitable rolling policy or agent |
| Application slows down when logging | Formatter, socket, console/file I/O, or log volume | Measure and tune; evaluate buffering/async |
| `logging.properties` has no effect | Not loaded, or framework owns logging | Check JVM properties, `LogManager`, and startup |
| Error log count exceeds failed requests | A single exception logged at multiple layers | Choose logging boundaries and unit-of-work metrics |

## 14. Checklist Before Concluding You Need to Leave JUL

1. **What specific capability is missing?** Text/JSON, context, tracing, rolling, retention, async, or just level configuration?
2. **Have you checked the actual handlers?** In many cases, missing logs are due to levels/filters/destinations rather than JUL lacking support.
3. **Can you add a formatter or collector while keeping things simple?** Factor in who will maintain it.
4. **Do you need true key–value fields or just readable messages?** A JSON schema and a text message are two different levels.
5. **Have throughput and reliability requirements been measured?** Do not assume async is better without verification.
6. **Are causes and stack traces preserved?** Custom formatters can easily drop exception details.
7. **Is sensitive data protected?** Check messages, parameters, `Throwable` instances, and storage locations.
8. **If adding a new bridge/backend, are there duplicate logs or loops?** Test across multiple environments.
9. **Have you tested end-to-end with the real collector?** Permissions, retention, encoding, JSON parsing, timestamps, and dropped data all matter.

JUL has many basic capabilities and is extensible. Its most notable limitations are **the lack of built-in modern conveniences for structured context, JSON, complex routing/rolling, async, configuration management, and cross-service observability**. The effective approach is to define your requirements, understand which layer is responsible, and choose a reasonable level of extension—rather than concluding that "not built into the JDK" means "impossible to do."
