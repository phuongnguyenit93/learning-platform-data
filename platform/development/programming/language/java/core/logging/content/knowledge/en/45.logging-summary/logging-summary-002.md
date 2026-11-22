# Flow from Logger to Destination — Java Logging Summary

## 1. The Big Picture

When a Java application calls `logger.info(...)` or `logger.error(..., exception)`, the log line **does not automatically appear immediately in a file or dashboard**. The call passes through components with distinct responsibilities: the logging API, backend/provider, level and filter decisions, event/context, appender or handler, encoder/formatter, output resource, and then potentially through a shipper/collector and centralized storage system.

An overview diagram:

~~~text
Java Application
    |
    | logger.info("Order {} created", orderId)
    v
Logging API / facade (SLF4J, Log4j API, or JUL)
    |
    | Actual provider/binding/implementation
    v
Logger / configuration / effective level / filters
    |
    +-- disabled / DENY ----------> no log at destination
    |
    v
Logging event: time, level, logger name, message,
               arguments, Throwable, MDC/ThreadContext ...
    |
    +-- sync ----------------------+
    |                             |
    +-- async queue / ring buffer-+--> [bounded; may block/drop]
                                  |
                                  v
                      Appender or JUL Handler
                                  |
                       filters, routing, failover
                                  |
                                  v
                        Formatter / Layout / Encoder
                                  |
                           text, JSON, bytes
                                  |
                                  v
                   Console / File / Socket / Syslog / ...
                                  |
                 +----------------+----------------+
                 |                                 |
             local sink                    shipper/collector
                                                   |
                                           parse/enrich/redact
                                                   |
                                                   v
                                            index / archive
                                                   |
                                                   v
                                             query / alert
~~~

**Key point:** "called the logger" does not mean "the log was accepted", "enqueued" does not mean "durably written", and "written to stdout" does not mean "indexed for searching on a dashboard". Every boundary can have filters, buffers, connection failures, or retries.

This summary describes the **flow from logger to destination** in Java Core Logging, and then connects it to common backends such as Logback, Log4j 2, and observability systems.

## 2. Commonly Confused Terms

| Component | What is it? | What it usually is NOT |
| --- | --- | --- |
| **Logger** | Entry point for code to emit events, by name or class | Does not necessarily write to a file itself |
| **Logging API** | Interface called by the developer | Not necessarily the implementation |
| **SLF4J** | Facade/API with a provider that selects a backend | Not a standalone file appender |
| **Backend/provider** | Logging execution system such as Logback | Not a log dashboard |
| **Level** | Severity of the request: INFO, WARN, ERROR... | Not a guarantee that it will be stored |
| **Filter** | ACCEPT/DENY/NEUTRAL condition depending on the backend | Not necessarily run in only one place |
| **LogEvent / LogRecord** | Data of a single logging event | Not synonymous with a single line of text |
| **MDC/ThreadContext** | Context attached to a thread/request | Does not automatically propagate across all async boundaries |
| **Appender (Logback/Log4j 2)** | Component that receives events and outputs to a destination | Not the same as a formatter |
| **Handler (JUL)** | Component that outputs `LogRecord` in `java.util.logging` | Not a Logback Appender |
| **Layout/Formatter** | Converts an event into a text representation | Does not necessarily perform I/O itself |
| **Encoder** | Turns information into bytes/format for writing | Not a collector-side parsing tool |
| **Sink** | Console, file, network endpoint, stream... | Not durable storage by default |
| **Collector** | Receives and processes logs from sources | Does not necessarily have the event indexed yet |
| **Index/storage** | Storage destination for querying or archiving | Does not automatically guarantee proper retention |

A backend may integrate different steps within the same class. The diagram above is a **mental model**, not a fixed call stack shared across all versions and frameworks.

## 3. Step 1: Application Calls the Logger

Example application using SLF4J:

~~~java
// Fragment: requires org.slf4j.Logger and LoggerFactory in dependencies.
private static final org.slf4j.Logger log =
    org.slf4j.LoggerFactory.getLogger(OrderService.class);

public void createOrder(String orderId) {
    log.info("eventCode=ORDER_CREATE_REQUESTED orderId={}", orderId);
}
~~~

A log call contains:

- **Requested level:** `INFO` in this case.
- **Logger name:** usually the `OrderService` class name or an explicitly chosen name.
- **Message template:** text with placeholders that can be formatted lazily.
- **Arguments:** the `orderId` value.
- **Throwable (optional):** so the backend preserves the stack trace and cause chain.
- **Context:** `requestId`/`traceId` from MDC or instrumentation, if present.

Separating the message template and arguments helps avoid unnecessary string concatenation and lets the backend format messages conditionally. However, **all argument expressions are still evaluated by Java before calling the method**:

~~~java
// Illustrative fragment: expensiveLookup() still runs before log.debug(...).
log.debug("Details: {}", expensiveLookup());

// If computation is expensive, guard first:
if (log.isDebugEnabled()) {
    log.debug("Details: {}", expensiveLookup());
}
~~~

Some APIs also support `Supplier` or fluent logging that allows lazy data preparation, but you must use the right version/binding. Do not claim that all parameterized logging approaches automatically avoid the cost of calling argument-building methods.

**Regarding exceptions:** when you want to attach a throwable, use the explicit overload:

~~~java
log.error("Order creation failed", exception);
~~~

Do not replace this with `printStackTrace()` plus another `logger.error` call. `printStackTrace()` writes directly to a separate stream, bypassing the backend's level configuration, MDC, and appenders.

## 4. Step 2: Logging API Selects the Actual Implementation

### 4.1. SLF4J Facade and Provider

SLF4J defines the API that applications/libraries use. With **SLF4J 2.x**, the **ServiceLoader** mechanism discovers a **provider** on the classpath/module path; the provider routes to a backend such as Logback Classic, Log4j 2 via the appropriate adapter, or JUL via `slf4j-jdk14`.

~~~text
Application calls org.slf4j.Logger
            |
            v
        slf4j-api 2.x
            |
        ServiceLoader
            |
            +--> Logback Classic provider --> Logback Core Appenders
            |
            +--> Log4j 2 SLF4J provider --> Log4j Core Appenders
            |
            +--> slf4j-jdk14 provider --> JUL Logger/Handler
~~~

In the same runtime, you must configure a provider compatible with the SLF4J API and avoid multiple competing providers. **With no provider**, SLF4J 2.x may warn and use a NOP implementation, so code calls the logger yet the console/file shows no events at all. **With multiple providers**, SLF4J warns and you should not rely on whichever provider happens to be picked.

With **SLF4J 1.7 and earlier**, the term is **binding** using the `StaticLoggerBinder` mechanism. Do not drop in a 1.7 binding and assume SLF4J 2.x will use it as a 2.x provider. When upgrading versions, check the dependency tree and bootstrap warnings.

Example dependencies to align by version:

~~~text
slf4j-api (API)
logback-classic (provider + Logback Classic)
logback-core (backend component)
~~~

These are illustrative artifact names, **not a BOM or specific version numbers**. For Log4j 2, provider/adapter artifacts and dependencies must be version-compatible. Consult the official documentation before choosing.

### 4.2. How Do JUL and Log4j API Differ?

- **JUL / `java.util.logging`:** built into the JDK, Logger → `LogRecord` → Handler → Formatter → output. Does not require SLF4J.
- **Log4j API + Log4j Core:** Logger from the API passes through `LoggerContext`/`Configuration`/`LoggerConfig`, Filters, `AppenderRef`/Appender, and Layout.
- **SLF4J + Logback:** code calls the facade, the Logback provider creates an event and dispatches to appenders according to the logger hierarchy and config.

**Do not use "SLF4J logger" as the name for the entire backend**, because level decisions, routing, encoding, and output usually belong to the implementation/configuration.

### 4.3. Bridges Between Logging Frameworks

Libraries may use JUL or Commons Logging while the application standardizes on SLF4J/Logback. Bridges route those logging requests into the target backend, but a **bridge loop** can cause recursion or loss of control:

~~~text
JUL -> SLF4J bridge -> SLF4J provider back to JUL -> ...
~~~

You need to establish a **single routing direction**, exclude opposing bridges/providers, inspect the dependency tree, and run integration tests. Do not copy every bridge JAR "just to be safe," because more is not better.

## 5. Step 3: Logger Name and Effective Level

In Logback/Log4j 2, logger names typically use a dot-separated hierarchy:

~~~text
ROOT
  |
  +-- com.example
           |
           +-- com.example.orders
                      |
                      +-- com.example.orders.OrderService
~~~

A logger without its own level can inherit an **effective level** from the nearest configured ancestor in the hierarchy. For example:

~~~text
ROOT: INFO
com.example.orders: DEBUG
com.example.orders.OrderService: (not explicitly set)
~~~

In Logback, `OrderService` inherits `DEBUG` from `com.example.orders`. Therefore, debug logging can be enabled for the orders area even though `ROOT` is configured at `INFO`.

Typical Logback level ordering:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

A logging request is enabled if the request's severity is **greater than or equal to the effective level** (before filters). If the effective level is `INFO`, `DEBUG` is dropped at the level check, while `INFO`, `WARN`, and `ERROR` can proceed.

**Do not infer the level from message text:** an `INFO` message can contain the word "error", and JUL uses `SEVERE` instead of `ERROR`. Backends may have additional levels (for example, Log4j 2 has `FATAL`); map levels according to the tool actually running.

**An important Logback detail:** an event already enabled on a child logger can be forwarded to an ancestor's appender via **additivity**; the parent logger's level is not necessarily re-evaluated as a new gate for that event. Thus **ROOT=INFO** does not guarantee the `ROOT` appender will not see `DEBUG` events created by a child logger with effective level `DEBUG`. If you want to filter at the appender itself, configure an appropriate filter/threshold.

## 6. Step 4: Filters and Evaluation Order

Level alone does not decide whether an event proceeds. Filters allow selection by logger, marker, context, message, appender, and custom conditions.

Examples:

- Drop health-check success logs by rule.
- Keep `WARN`/`ERROR` while throttling high-volume `DEBUG` logs.
- Block logs containing disallowed fields.
- Route security audit logs to a separate sink with its own policy.
- Reject events that do not match the schema or have oversized payloads.

**Filter order is not identical across all frameworks:**

- **JUL:** Logger checks level, then Logger Filter if present; if passed, sends `LogRecord` to Handlers. Each Handler has its own level/filter.
- **Logback:** has early **TurboFilter**s, then basic level selection and logging event creation, then **Appender filters** and routing.
- **Log4j 2:** Filters can be present at the Logger stage, `LoggerConfig`, `AppenderRef`/`AppenderControl`, and Appender; the API uses `ACCEPT`/`DENY`/`NEUTRAL` states.

Therefore, "level → filter → event" is a **simplified diagram**, not a mechanical order for every implementation. For accurate diagnosis, consult the respective documentation and active configuration.

**Where an event is filtered out**, the calling code does not throw an exception just because a `DEBUG` record was not emitted. If someone says "I called the logger and saw no logs", inspect every filter, level, and destination before claiming the logger is broken.

## 7. Step 5: Creating the Logging Event / LogRecord and Context

A logging event contains more information than the displayed text:

| Field | Description | Common source |
| --- | --- | --- |
| Timestamp | Time the log/event was created | Clock/framework |
| Level | INFO/WARN/ERROR or JUL Level | Log method + backend |
| Logger name | Component/class that created the event | Logger instance |
| Thread name | Thread that emitted the event | Runtime/logging backend |
| Template and arguments | Message before/after formatting | Logger call |
| Throwable | Exception and cause chain | `logger.error(msg, ex)` |
| MDC/ThreadContext | `requestId`/`traceId`/correlation IDs | Request/tracing context |
| Marker/structured fields | `eventCode`, `operation`, `outcome` | SLF4J/fluent/backend API |
| Caller location | Class/method/file/line | Stack walking if enabled |

**One event can be printed as multiple lines** due to a throwable stack trace, and can also produce two outputs at two sinks; do not equate line count or output count with event count.

In **JUL**, the Java API uses `LogRecord` between Logger and Handler. When a `LogRecord` is handed off to another thread, caller information may be inferred lazily and not always accurately if the backend/handler has not captured context on the originating thread; Oracle documentation notes forcing source class/method inference before handoff when needed.

In Logback/Log4j 2, async appenders/loggers also have **caller data** caveats: computing stack location is expensive and may need to be explicitly enabled/captured at the right point. Do not enable `includeCallerData`/`includeLocation` broadly without need; cost and behavior must be measured on the actual backend.

## 8. MDC / ThreadContext Along the Path

**Mapped Diagnostic Context (MDC)** lets you attach common fields such as `requestId` to events emitted within the same context:

~~~java
// Fragment with SLF4J; requestId comes from trusted middleware.
org.slf4j.MDC.put("requestId", requestId);
try {
    service.process();
} finally {
    org.slf4j.MDC.remove("requestId");
}
~~~

In Logback `PatternLayout`, `%X{requestId}` can output the MDC value if the event retains its context:

~~~text
2026-11-10T03:30:05Z INFO requestId=req-42 com.example.OrderService - Order created
~~~

**Thread pool trap:** MDC is typically tied to thread context. When submitting tasks to `ExecutorService`, `@Async`, `CompletableFuture`, or reactive pipelines, data does not automatically propagate across all threads. If you forget cleanup, an old request's `requestId` can appear in the next request's logs because worker threads are reused.

- Create/validate `requestId` at the entry boundary.
- Set MDC when processing begins.
- Clean up with `try`/`finally` or the corresponding scope API.
- Propagate context across async tasks in a controlled way; do not copy `ThreadLocal` indiscriminately.
- Use appropriate trace instrumentation for Spring WebFlux/Reactor.
- Configure the encoder/appender to actually output MDC.
- Do not trust client-supplied headers without validation and a defined trust boundary.

**MDC holds technical context, not a place to stuff raw request bodies, tokens, or PII.** With multiple async hops, verify results at the index, not just on the thread running the controller.

## 9. Step 6: Appender / Handler Chooses the Destination

In **Logback**, an Appender is the interface/object that receives a logging event and performs output. Common appenders:

- `ConsoleAppender`: writes to the console stream.
- `FileAppender`: writes to a regular file.
- `RollingFileAppender`: writes to an active file and rolls over/archives according to policy.
- `AsyncAppender`: places events into a queue for processing on another thread and then forwards to a target appender.
- Network/custom appenders: send to a corresponding service or protocol.

In **Log4j 2**, an Appender typically uses a Layout/Manager to serialize and write to Console, File, RollingFile, Socket, or another destination. `LoggerConfig` holds `AppenderRef`s, levels/filters, and hierarchy links.

In **JUL**, the corresponding output concept is **Handler**: `ConsoleHandler`, `FileHandler`, `SocketHandler`, or a custom Handler. A Handler has a Formatter and Filter/Level; `ConsoleHandler` defaults to **`System.err`**, so you should not always say all JUL console logs go to `System.out`.

A **Logger** can send the same event to multiple appenders, such as Console and File. That is **intentional fan-out** when configured properly. If the same `ConsoleAppender` is referenced on both a child logger and `ROOT` with additivity, the event can appear twice at the same destination.

To diagnose missing or duplicate logs, ask:

1. Which logger received the request?
2. Which level/filter allowed it?
3. Which Appender/Handler is actually referenced?
4. Is parent forwarding/additivity active?
5. Has the Appender started and does it have sufficient resource permissions?
6. Is the Encoder/Layout attached properly?
7. Is there an async queue, network retry, or collector re-reading the data?

## 10. Additivity: One Event Can Reach Multiple Appenders

Logback logger hierarchy example:

~~~text
Logger com.example.orders
    |
    +--> CONSOLE appender on child logger
    |
    +--> (additivity=true) ROOT
                           |
                           +--> CONSOLE appender on ROOT
~~~

If the **same `CONSOLE` appender** is referenced at two levels, one log call can output **two copies to the same destination**. In Logback, default additivity is typically `true`. If you only want one console copy, attach the appender once at `ROOT` or set `additivity=false` when the child logger has its own route.

**Do not set `additivity=false` blindly:** a child logger without its own appender can lose output. Test all affected logger namespaces, especially security/audit.

Logback example avoiding duplicate `CONSOLE` references:

~~~xml
<configuration>
  <appender name="CONSOLE"
      class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n%ex{full}</pattern>
    </encoder>
  </appender>
  <logger name="com.example.orders" level="DEBUG"/>
  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

This is an **illustrative `logback.xml`**. Events from `com.example.orders` are enabled at effective level `DEBUG` and have a path to `CONSOLE` at `ROOT`, even though `ROOT` level is `INFO`. Specific behavior also depends on any other filters/appenders the application configures.

If you want audit logs to go to a separate store, you can add a dedicated logger with `additivity=false`, but make sure you attach an audit appender, failover policy, and separate retention. Do not share the same file for audit and debug if retention obligations differ.

## 11. Step 7: What Do Layout / Formatter / Encoder Do?

After an event is accepted and reaches an appender, the backend usually needs to convert the event into output:

~~~text
LoggingEvent / LogRecord
   |
   +--> PatternLayout / Formatter --> text
   |
   +--> JSON encoder/template ------> structured JSON
   |
   +--> binary/network serializer --> protocol bytes
   |
   v
byte stream / connection / storage
~~~

**Layout/Formatter** defines the display format: timestamp, level, logger, MDC, message, and exception. **Encoder** typically combines layout/serialization with byte generation, charset, and framing so the appender can write. Exact class names and boundaries vary by framework, so do not assume every backend has both as independent objects.

Logback text pattern example:

~~~text
%d{ISO8601} %-5level [%thread] %logger requestId=%X{requestId:-} - %msg%n%ex{full}
~~~

This can output:

~~~text
2026-11-10 10:30:05,123 INFO  [http-4] com.example.OrderService requestId=req-42 - Order created
~~~

The actual timestamp format depends on pattern/version/timezone. Likewise, a stack trace when a throwable is present can add multiple lines.

**Encoding and parsing are two opposite directions:**

- **Encoder in Java**: LogEvent → text/JSON/bytes.
- **Parser in collector**: bytes/text/JSON → normalized fields for search.

A timestamp parse error at the collector may be caused by an encoder format change, not a bug in `Logger.info`.

## 12. Structured JSON vs Text: Choose by Contract

Text patterns are human-readable, but fragile with spaces, delimiters, multiline stack traces, and layout changes. Structured JSON Lines are usually easier to query:

~~~json
{"timestamp":"2026-11-10T03:30:05Z","level":"INFO","service":"order-service","logger":"com.example.OrderService","requestId":"req-42","eventCode":"ORDER_CREATED","message":"Order created"}
~~~

If using JSON Lines:

- **Each event becomes one JSON object on one physical line**.
- Messages containing quotes, backslashes, or newlines are escaped by the JSON serializer.
- Timestamp/timezone is explicitly defined; do not assume all times are UTC.
- Field types are consistent: `durationMs` is a number, not sometimes a string `"17ms"`.
- Exceptions can be a newline-escaped string field or a nested object.
- Do not add unbounded dynamic keys; control index schema/cardinality.
- Do not build JSON via manual string concatenation when untrusted data is present.
- Version or contract your fields, along with golden fixture tests.

**The Java standard library does not have a general-purpose JSON parser that every application is required to use**. For standard JSON serialization, use an encoder/backend or a maintained JSON library rather than splitting messages manually. If Log4j 2 uses JSON Template Layout or Logback uses a compatible JSON encoder, verify actual dependencies and versions.

**JSON does not automatically guarantee safety.** It can make PII fields easier to find; perform data minimization/redaction at the source and downstream.

## 13. Step 8: Synchronous vs Asynchronous

### Synchronous Path

~~~text
Application thread
    -> Logger enabled check
    -> event/filter
    -> Appender/Handler
    -> encode
    -> write to sink
    -> return to application
~~~

Pros: easier to reason about when the logging call finishes. Cons: caller latency can be affected by locks, disk I/O, network, or CPU-heavy encoders. **Even with a synchronous appender, returning from the log method does not by itself prove data was fsynced to disk or indexed by the collector.**

### Asynchronous Path

~~~text
Application thread                        Logging worker
    |                                          |
    v                                          |
 Logger enabled check                           |
    |                                          |
    v                                          |
 Capture event + context                        |
    |                                          |
    v                                          |
  bounded queue / ring buffer -----------------+
                                               |
                                               v
                                         Appender/Handler
                                               |
                                         encoder + sink
~~~

Pros: can reduce log-call latency and absorb bursts if the queue is large enough. Cons: the queue is bounded, so when the producer is persistently faster than the sink, it will fill up; it may block the caller, discard according to policy, or handle overflow differently depending on backend/config. Data still in the memory queue **can be lost if the process crashes**.

**Asynchronous logging does not increase the sustainable throughput of disk/network.** Actual sink capacity remains the ultimate limit. If 20,000 events/s arrive but the destination can only sustain 10,000 events/s, backlog grows until the queue fills.

### Do Not Confuse Two Concepts in Log4j 2

- **AsyncAppender**: an appender wrapping other appenders with a queue.
- **AsyncLogger**: asynchronous logging at the logger level, typically using Disruptor/ring buffer per Log4j 2 configuration.

They have different APIs/configs, queue-full policies, and costs; do not assume enabling `AsyncAppender` converts the entire `LoggerContext` to `AsyncLogger`. **Benchmark with real payloads and sinks** before claiming one approach is faster.

## 14. Logback Example: Single Flow to AsyncAppender then Console

An **illustrative `logback.xml`**, referencing only `AsyncAppender` from `ROOT` to avoid writing directly to `CONSOLE` a second time:

~~~xml
<configuration>
  <appender name="CONSOLE"
      class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <charset>UTF-8</charset>
      <pattern>%d{ISO8601} %-5level requestId=%X{requestId:-} %logger - %msg%n%ex{full}</pattern>
    </encoder>
  </appender>

  <appender name="ASYNC"
      class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>1024</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <maxFlushTime>5000</maxFlushTime>
    <appender-ref ref="CONSOLE"/>
  </appender>

  <logger name="com.example.orders" level="DEBUG"/>

  <root level="INFO">
    <appender-ref ref="ASYNC"/>
  </root>
</configuration>
~~~

Main flow:

~~~text
SLF4J logger com.example.orders.OrderService
        |
   Logback level/filters + event/MDC
        |
        v
     ASYNC queue
        |
       worker
        |
        v
   CONSOLE appender
        |
        v
    Pattern encoder -> stdout/stderr per appender -> container/collector
~~~

Points to verify:

- `queueSize=1024` is the **number of events** in the sample queue, not 1024 bytes.
- `discardingThreshold=0` disables `AsyncAppender`'s default threshold-based event discarding; it **does not guarantee zero log loss on crash, stop timeout, or backend failure**.
- `neverBlock=false` lets the caller wait when the queue is full per backend semantics, impacting latency.
- `maxFlushTime` is the drain wait limit on shutdown; if not drained within the timeout, events risk being lost.
- `AsyncAppender` typically allows only one downstream appender in common configurations; if multiple sinks are needed, design fan-out according to backend capabilities.
- Declare `CONSOLE` but **do not** attach it directly to `ROOT` alongside `ASYNC`, or a single event may be printed twice.
- Do not apply this configuration verbatim to mandatory non-lossy audit logs; evaluate durability/failure semantics separately.

No single async configuration fits every workload. For very fast sinks or low-volume apps, synchronous logging can be simpler and sufficient.

## 15. Log4j 2 Example: LoggerConfig, AppenderRef, Layout, Sink

Log4j 2 organizes around **`LoggerContext`**, **`Configuration`**, **`Logger`/`LoggerConfig`**, Filters, `AppenderRef`/`AppenderControl`, Appender, and Layout/Manager. A minimal **`log4j2.xml`** configuration:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <Console name="CONSOLE" target="SYSTEM_OUT">
      <PatternLayout
          pattern="%d{ISO8601} %-5p [%t] %c - %m%n%throwable"/>
    </Console>
  </Appenders>

  <Loggers>
    <Logger name="com.example.orders" level="debug"/>
    <Root level="info">
      <AppenderRef ref="CONSOLE"/>
    </Root>
  </Loggers>
</Configuration>
~~~

Illustrative path:

~~~text
Log4j API logger
  -> enabled/filter
  -> LoggerConfig (com.example.orders)
  -> AppenderRef from Root via additivity
  -> CONSOLE appender
  -> PatternLayout
  -> SYSTEM_OUT
~~~

All other loggers can inherit `ROOT` according to the configuration. If `CONSOLE` is attached to both a child logger *and* `ROOT`, check additivity to avoid delivering the event to the same appender twice.

To put a filter on a single appender reference, Log4j 2 supports configuring level/filter on **`AppenderRef`**; an event can pass logger-level checks yet be rejected at the appender stage. **Do not assume setting root `level=INFO` makes every appender drop `DEBUG` from child loggers**; understand the hierarchy and each filter gate.

If switching to `AsyncAppender` in Log4j 2, illustrative fragment:

~~~xml
<Async name="ASYNC">
  <AppenderRef ref="CONSOLE"/>
</Async>
~~~

You also need `Root` to reference `ASYNC`, not `CONSOLE` directly unless fan-out is intentional. The fragment is not a complete file, and queue behavior depends on version/policy.

**Enabling global `AsyncLogger` is a different configuration**. Do not mix async mechanisms just to see more threads; multiple queue layers can increase latency, complicate flushing, and make log loss harder to explain.

## 16. Standalone Java 17+: Verifying Each Stage with JUL

To understand **Logger → level → Filter → LogRecord → Handler → Formatter → sink** in depth, this example uses **`java.util.logging`** built into the JDK. No external libraries or filesystem permissions are required.

A custom Handler:

- Checks level/filter via `isLoggable(record)`.
- Uses a Formatter to turn `LogRecord` into a deterministic string.
- Converts to UTF-8 bytes and writes into a `ByteArrayOutputStream` as an **in-memory mock sink**.
- Counts events reaching the Handler so it is not confused with line count.
- Disables parent handlers so output is not duplicated by global JUL configuration.

Create **`LoggerToSinkDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggerToSinkDemo {
    static class MemoryHandler extends Handler {
        final ByteArrayOutputStream sink = new ByteArrayOutputStream();
        int accepted;

        MemoryHandler() {
            setLevel(Level.ALL);
            setFormatter(new Formatter() {
                @Override public String format(LogRecord r) {
                    String cause = r.getThrown() == null
                        ? "none"
                        : r.getThrown().getClass().getSimpleName();

                    return r.getLevel() + "|" + r.getMessage()
                        + "|cause=" + cause + "\n";
                }
            });
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) return;

            sink.writeBytes(getFormatter().format(record)
                    .getBytes(StandardCharsets.UTF_8));
            accepted++;
        }

        @Override public void flush() {}
        @Override public void close() {}

        String contents() {
            return sink.toString(StandardCharsets.UTF_8);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.pipeline");

        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        AtomicInteger filterSeen = new AtomicInteger();
        logger.setFilter(record -> {
            filterSeen.incrementAndGet();
            return !record.getMessage().startsWith("DROP ");
        });

        MemoryHandler handler = new MemoryHandler();
        logger.addHandler(handler);

        try {
            logger.fine("requestId=req-42 stage=TRACE");

            logger.info("requestId=req-42 stage=START");

            logger.warning(
                    "DROP requestId=req-42 stage=NOISE");

            logger.log(Level.SEVERE,
                    "requestId=req-42 stage=FAILED",
                    new IllegalStateException(
                            "downstream unavailable"));

            System.out.print("sink:\n" + handler.contents());
            System.out.println(
                    "loggerFilterSeen=" + filterSeen.get());
            System.out.println("sinkEvents=" + handler.accepted);
        } finally {
            logger.removeHandler(handler);
            logger.setFilter(null);
            handler.close();
        }
    }
}
~~~

Run with Java 17 or later:

~~~bash
javac LoggerToSinkDemo.java
java LoggerToSinkDemo
~~~

**Verified exact stdout:**

~~~text
sink:
INFO|requestId=req-42 stage=START|cause=none
SEVERE|requestId=req-42 stage=FAILED|cause=IllegalStateException
loggerFilterSeen=3
sinkEvents=2
~~~

### Step-by-Step Walkthrough

1. The Logger has `Level.INFO`. The `logger.fine(...)` call at `FINE` is lower than `INFO`, so it is dropped **before the Logger Filter runs**; no `LogRecord` reaches the handler for this line.
2. `INFO` passes level and Filter, creating a `LogRecord`; `MemoryHandler` accepts it and Formatter produces a text line with `cause=none`.
3. `WARNING` passes level; the Filter sees text starting with `DROP ` and rejects it; this event never reaches the Handler.
4. `SEVERE` passes level and Filter, with `LogRecord` holding the `Throwable`; Formatter writes `cause=IllegalStateException`.
5. **`loggerFilterSeen=3`** because the Logger Filter inspected `INFO`, `WARNING`, and `SEVERE`, not `FINE` which was already blocked by level.
6. **`sinkEvents=2`** because only `INFO` and `SEVERE` passed all gates to reach the Handler; sink data has two lines.
7. The Handler converts the formatted string to UTF-8 bytes via `getBytes(StandardCharsets.UTF_8)` and writes to `ByteArrayOutputStream`.

**Limitations:** the sink is RAM, not a file/network/durable store. The example does not simulate async queues, concurrency, retries, checksums, fsync, or collector indexing. `Handler.accepted` is a single-threaded counter, not thread-safe for production use. The message-prefix filter only illustrates **a single gate**; do not use such filtering as a PII protection mechanism in real systems.

### Why Does the Example Use JUL?

JUL is built into Java 17, so the example runs with just `javac`/`java`. It illustrates the same mental model of **enabled check → event → output component → formatting → sink**, though **Logback and Log4j 2 have different pipelines/filters/APIs**. Do not copy a JUL `Handler` into a Logback `Appender` as if they were the same interface.

## 17. How Does an Error Event Travel Through the Layers?

Consider a use case where a user creates an order and the repository times out:

~~~text
HTTP POST /orders
    |
    v
Request filter attaches requestId=req-42
    |
    v
OrderController -> OrderService -> Repository
                                     |
                                     X timeout
                                     |
                          throw (preserving root cause)
                                     |
                            boundary handler
                                     |
                    logger.error("Order failed", ex)
                                     |
                                     v
                          Logger + backend/provider
                                     |
                         enabled by ERROR level?
                                     |
                                 Filter policy
                                     |
                           event + requestId + cause
                                     |
                           Appender / Async queue
                                     |
                             encoder JSON/text
                                     |
                         stdout/container or file
                                     |
                                 collector
                                     |
                                  log index
                                     |
                        support query requestId
~~~

**Do not catch/log/rethrow at every layer.** A single logic error can emit three identical stack traces if repository, service, and controller all log `ERROR`. Instead, preserve the `Throwable` cause and log **one terminal event** at the chosen boundary; metrics/tracing can supplement attempt/fallback context.

The client response and server logs need the **same `requestId`**, but do not return stack traces or internal details to the client. For expected 400 validation errors, you can use `INFO`/metrics/access logs per policy instead of `ERROR` with a full stack trace.

**A multiline exception stack trace is usually a single logging event.** If a shipper reads line by line without multiline handling, the dashboard may interpret it as multiple records. Fix framing/JSON encoding rather than grepping for every `"at ..."` line in code.

## 18. Local Sinks: Console, File, Rotation

### Console

In containers, console logging is often convenient because the runtime can collect stdout/stderr. However:

- `ConsoleAppender` writes to the configured stream, e.g. `SYSTEM_OUT`.
- JUL `ConsoleHandler` defaults to `System.err`.
- The container runtime may apply its own log rotation.
- When a container/pod is deleted, local logs are not kept indefinitely; a shipper/centralized store is needed for later querying.
- Writing to console does not automatically mean the collector has ACKed.

**Do not claim "logging to console is durable"**. There can be buffering, process crashes, pod restarts, disk evictions, or collector outages.

### File

`FileAppender`/`RollingFileAppender` writes to the filesystem according to path, permissions, charset, and policy. A file pipeline:

~~~text
LoggingEvent
   -> RollingFileAppender
   -> Encoder
   -> app.log (active)
   -> app.YYYY-MM-DD.log.gz (archived on rollover)
   -> Filebeat/collector tail
   -> index/archive
~~~

Rotation and retention are different: rollover splits files; archive cleanup requires `maxHistory`/`totalSizeCap` or a separate lifecycle. File retention on disk does not dictate index/backup retention. Check the active file, directory permissions, disk full, rotation during low log volume, and how the collector tracks file identity.

**Do not read and delete the active file to free space** without a plan; it can cause log loss or corrupt the collector registry.

## 19. Network Sinks and Collectors

When an appender/handler sends over socket/HTTP/protocol, there are additional stages:

~~~text
Application -> queue -> encoder -> network
                                    |
                        endpoint unavailable?
                                    |
                          retry/backoff/buffer
                                    |
                                 receiver
                                    |
                        parse/enrich/redact
                                    |
                             storage/index
~~~

Distinguish between:

- **Accepted:** the logger method accepts the request.
- **Enqueued:** the event sits in a memory/disk queue.
- **Processed:** the logging worker picked it up and passed it to the appender.
- **Emitted:** bytes have been written/sent out of the process per sink semantics.
- **Received/ACKed:** the receiver confirmed per protocol.
- **Indexed/archived:** data is stored per backend semantics.
- **Queryable:** available for queries, sometimes after a refresh/ingest lag.

There is **no universal logging API** that returns all of these states. You need metrics/traces across the collector, appender, and storage to measure end-to-end. A `SocketAppender` may only confirm writing to the OS buffer, not that the final system has stored it.

If the network goes down, decisions on **drop, block, retry, buffer, and failover** are part of observability and durability policy. For audit/security events that must not be lost, a different durable architecture may be needed than for application debug logging.

## 20. What Happens After the Sink?

Once data leaves the JVM, the flow typically includes:

1. **Container/file shipper** such as Filebeat, Fluent Bit, or an agent capable of reading from files/stdout.
2. **Framing/multiline:** determines event boundaries; Java `Throwable`s are often multiline in text format.
3. **Decoding/parsing:** from text/JSON into timestamp, severity, logger, MDC, and exception fields.
4. **Enrichment:** `service.name`, environment, host, and validated metadata.
5. **Redaction:** removes PII/secrets and enforces policy; best avoided at the source in the first place.
6. **Buffer/retry/backpressure:** handles temporary collector or storage overload.
7. **Indexing/archive:** stores according to schema/retention for querying or recovery.
8. **Dashboards/alerts:** query by `requestId`/`traceId`, `eventCode`, error rate, route, or service.

**A parsing error at the collector is not necessarily a bug in `Logger.info` in Java.** The encoder may have changed patterns, pretty-printed multiline JSON, omitted a timezone offset on timestamps, or changed a field type.

**Seeing an event queryable on a dashboard does not prove there are no duplicates or missing gaps.** Reconcile `eventId`/`requestId` and counts across defined boundaries.

## 21. Observing the Flow with Metrics: Where Can Logs Be Lost?

A stage-by-stage checklist:

| Stage | Metrics or evidence to have | Warning signs |
| --- | --- | --- |
| Application call | operation count, `eventCode` per policy | Multiple callsites logging one failure |
| Logger/level | effective configuration, enabled test | `DEBUG` blocked unexpectedly |
| Filter | rejected events per rule if supported by backend | Accidentally dropping audit logs |
| Async queue | depth, capacity, enqueue/drop/block | Queue full, latency spike |
| Appender/Handler | append successes/failures, flush errors | File permission, broken socket |
| Encoder | serialization errors, malformed output | Broken JSON escaping/schema |
| File/stdout | bytes produced, rotation, free disk | File not growing, disk full |
| Shipper | read offsets, received/retried/dropped | Corrupt registry or backlog |
| Collector | parsed/rejected, queue utilization | Broken multiline, parser drift |
| Backend | accepted/indexed, storage, mapping rejects | Ingest OK but index rejects |
| Query/alert | sample event readback, ingest lag | Data missing or false alerts |

Metric names depend on the implementation; do not assume Logback/Log4j 2 export every number automatically. You can use application instrumentation, agents, JMX, exporters, and backend APIs per version.

**Approximate backlog formula** for a queue:

~~~text
backlog_growth_events_per_second
  ≈ ingress_events_per_second - sustainable_output_events_per_second
~~~

When output is persistently slower than ingress, the queue eventually fills even if logs initially appear to be written quickly. Measure both **events/s** and **bytes/s**, because the same event count with large stack traces consumes far more I/O.

## 22. Performance of Each Stage

The cost of a log call is not just disk I/O:

- **Argument computation:** string/DTO builders run before the logger receives them.
- **Enabled check/filter:** usually cheap, yet adds up under very high call rates.
- **Event allocation:** metadata, message, `Throwable`, and MDC snapshot.
- **Caller data:** stack walking is expensive when exact file/line is needed.
- **Formatting:** regex/pattern/JSON serialization, timestamps, escaping, stack traces.
- **Contention:** locks in appenders or shared outputs.
- **Queue:** enqueueing, context switching, producer blocking when full.
- **Disk:** buffering, fsync policy, rotation/compression.
- **Network:** bandwidth, retries, TLS, backpressure.
- **Collector:** multiline, parser, enrichment, redaction, index mapping.

A benchmark that only calls `log.debug` with the level disabled does not measure appender capacity. A benchmark writing to `ByteArrayOutputStream` does not represent file/network. A benchmark measuring caller-side async latency does not prove events reached the sink.

Designing a fair benchmark:

1. Keep message/event sizes and exception/MDC ratios comparable to production.
2. Compare with identical effective levels and routing.
3. Separate caller latency, append throughput, and sink-confirmed throughput.
4. Observe CPU, allocation, GC, queue depth, and disk/network saturation.
5. Measure after proper warmup; test both burst and sustained rates.
6. Verify the number of events reaching the destination equals expected events when policy forbids drops.
7. For async, wait for drain/flush and record discarded events.
8. Test shutdown/crash/sink outage, not only steady state.

Do not take single-machine microbenchmark results and claim production log files or remote collectors will achieve the same speed.

## 23. Security Across the Entire Flow

Every stage carries data risks:

| Stage | Risk | Protection |
| --- | --- | --- |
| Application | Logging raw passwords, Cookies, Authorization headers | Do not log sensitive data at the source |
| MDC | Attaching user tokens to every event | Only use purposeful, validated IDs |
| Encoder | Messages with newlines causing log injection | Escaping/structured serialization |
| File/console | Broad OS/container permissions | Least privilege, permissions, rotation |
| Network | Plaintext or wrong endpoint | TLS/auth and system allowlists |
| Collector | Raw logs re-printed on parse failure | Protective redaction/quarantine |
| Storage | Broadly queryable index permissions | RBAC, retention, access audit |
| Archive/backup | Data persists after index deletion | Lifecycle, legal hold, deletion ledger |

An exception message from a library can contain sensitive URLs/queries/paths; do not pass raw `Throwable`s to every audience. **Client responses** usually only need `errorCode`/`requestId` and a safe message, without a stack trace.

If you want to eliminate PII, collector-only redaction is insufficient because raw copies may already sit in stdout, files, agent buffers, or archives. **Data minimization at the logger call** is the first line of defense.

When security/audit logs have integrity and retention requirements, design a separate channel with appropriate permissions and durability/retention. Do not apply sampling or discard policies to that data without review and approval.

## 24. Common Failures and How to Isolate Them

### 24.1. Logger Called, No Output

Check in order:

1. Is there a compatible provider/backend, or did SLF4J fall back to NOP?
2. Do the logger name and effective level allow the event?
3. Is a `TurboFilter`/Logger Filter/Appender Filter/`ThresholdFilter` rejecting it?
4. Is the Appender/Handler attached, started, and routed properly?
5. Did `additivity=false` leave the logger without an appender?
6. Is output going to stdout or stderr, which file, which container?
7. File/dir permissions, queue full, socket/collector errors?
8. Is the encoder producing invalid data or is the collector rejecting/failing to index?
9. If reading a dashboard: ingestion lag, query filter, timezone, and retention?

Do not flip root level to `DEBUG` across all of production just to "test easily," as it can spike volume and leak data. Target the specific namespace needing diagnosis with an appropriate time limit.

### 24.2. Logs Appearing Twice

Distinguish between:

- Code logging at multiple layers: catch–log–throw and then the handler logs again.
- Logback/Log4j 2 additivity: same appender on child logger and `ROOT`.
- One event intentionally fanned out to console and file.
- Shipper/collector reading the same data via two paths or at-least-once retries.
- A multiline stack trace **is not** multiple events.

Compare `eventId`/`requestId`, logger name, timestamp, destination, and callsite count to pinpoint where duplication starts. Do not suppress solely by exception message, because independent requests can share identical messages.

### 24.3. Text Present, Missing requestId

- Did middleware create and validate `requestId`?
- Was MDC set and cleared with the proper lifecycle?
- Did tasks crossing threads propagate context properly?
- Does the appender/encoder include `%X{requestId}` or the corresponding JSON field?
- Did the collector parser drop or mis-map the field?
- Does the response ID match the logged field?

Do not fabricate `requestId` at the collector from the "nearest event"; concurrent requests can be misattributed.

### 24.4. Logs Truncated or Lost Under Load

- Did the async queue fill/drop, or was the caller blocked?
- Did `maxFlushTime`/shutdown allow enough time to drain?
- Is the output sink slow, disk full, or network failing?
- How do collector/shipper retries and backpressure behave?
- Was a rotated file deleted before the shipper finished reading it?
- Did index quota/mapping conflicts/retention prevent querying?

Reconcile counts stage by stage. Unless the pipeline guarantees end-to-end at-least-once delivery, do not claim 100% delivery simply because the logger threw no errors.

## 25. End-to-End Testing Matrix

| Scenario | Expectation |
| --- | --- |
| Level `INFO`, calling `FINE`/`DEBUG` | Event blocked by appropriate effective level |
| Level passes, filter `DENY` | Does not reach appender; filter observable when needed |
| `Throwable` log | Single event with exception/cause chain |
| MDC `requestId` | Field present in output and matches response |
| Async task | Context not lost or mixed between requests |
| Appender filter | Only valid events reach the sink |
| Child logger and `ROOT` | No duplicates beyond intentional fan-out |
| File/console | Charset, newline, rolling, and permissions are correct |
| JSON encoder | Parser extracts fields/escaping/schema properly |
| Java stack trace | Multiline text grouped into a single event |
| Async queue full | Drop/block/fallback per policy and measurable |
| Shutdown | Drain/flush within designed limits |
| Collector down | Retry/backpressure/retention meet requirements |
| Security audit | Not sampled/dropped or leaked without authorization |
| Disk full | Error reported; does not crash entire app outside failure policy |
| Collector parse error | Metrics/quarantine present; no self-logging loop |
| Sink retry | Distinguish real duplicates from intentional fan-out |
| Indexing | Reconcile `eventId`/query/ingest timestamp |
| Retention | Logs retained and deleted per policy everywhere |
| Multiple independent requests | Real errors not suppressed due to identical messages |

The JUL program in the example tests **one segment** of the pipeline. Production testing needs Logback/Log4j 2 integration tests with real dependencies, collectors, and indexes in an isolated/simulated environment.

## 26. Practice: Mapping Your Project's Log Flow

Pick a specific logging statement, for example:

~~~java
log.error("Order creation failed", exception);
~~~

Fill in the table:

| Question | Record the actual answer |
| --- | --- |
| API | SLF4J 2.x, Log4j API, or JUL? |
| Provider/backend | Which Logback/Log4j 2/JUL version is running? |
| Logger name | Which class, namespace, and effective level? |
| Filters | Any `TurboFilter`/`ThresholdFilter`/marker/level rules? |
| Event | How are `Throwable`, MDC, `eventCode`, timestamp, and thread captured? |
| Routing | Which appenders directly/via hierarchy, and what is additivity? |
| Async | Which queue/ring buffer, and what are full/flush/shutdown policies? |
| Encoding | Which `PatternLayout`/JSON encoder, charset, and newline? |
| Local sink | Stdout/stderr, active file, rolling file, or socket? |
| Shipping | Which agent reads it, file identity, and multiline rules? |
| Collector | Which parser/schema/redaction/enrichment? |
| Storage | Which index/archive, retention, ACL, and query? |
| Evidence | `eventId`/`requestId` read back from destination, metrics at each stage? |

Use **a synthetic `requestId`** and a fixed `eventCode`, then observe each stage you are authorized to access. If the event is missing in the index but present in the local file, the issue is no longer at the logger enabled check; shift investigation to the shipper/collector/index.

Map out the actual path:

~~~text
OrderService.info
  -> SLF4J
  -> Logback
  -> com.example.orders effectiveLevel=INFO
  -> AsyncAppender
  -> RollingFileAppender
  -> app.log JSON Lines
  -> Filebeat
  -> Collector
  -> log index
  -> query requestId=req-demo
~~~

This is a reference example, not a confirmed configuration of a specific system.

## 27. Pre-Deployment Checklist

- [ ] Logging API/backend/provider are compatible, with no NOP or bridge loops.
- [ ] Effective levels and filter paths of critical namespaces are known.
- [ ] Logger name, `eventCode`, `requestId`, and `traceId` have a contract.
- [ ] `Throwable`/cause chain is passed properly, without repeated `printStackTrace()`.
- [ ] MDC setup, cleanup, and async propagation strategy is in place.
- [ ] Appenders/Handlers are started, configured with proper sinks and permissions.
- [ ] Additivity does not create duplicates or unintentionally drop logs.
- [ ] Encoder/formatter is verified with actual output and correct charset.
- [ ] JSON Lines/multiline handling matches generated logs.
- [ ] Async queue/full/shutdown/drop policies are documented and measured by metrics.
- [ ] Separate observability exists for application, shipper, collector, and index.
- [ ] Logger return is not treated as proof of fsync/index/ACK.
- [ ] PII/secret controls at source, redaction, ACLs, and retention are enforced at sinks.
- [ ] Normal, error, burst, shutdown, collector outage, and retry scenarios are tested.
- [ ] A sample `requestId`/`eventId` is reconciled end-to-end.
- [ ] A runbook exists to isolate lost/duplicate logs without blindly enabling `DEBUG`.

**Conclusion:** The Java Logging flow starts from a **Logger call**, is decided by the **API/provider/backend** and controlled via **levels/filters**, forms a **logging event containing message/`Throwable`/context**, travels to an **Appender or JUL Handler**, is converted by a **Layout/Formatter/Encoder** into output, and reaches **console, file, or network**. With a centralized system, logs continue through **shipper, collector, parser, index, and dashboard**. Understanding these boundaries reveals **where logs are blocked/lost/duplicated**, distinguishes **accepted events from stored data**, and enables verifiable decisions on performance, security, and reliability.

## 28. References

- [Oracle Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): enabled check, `Filter`, `LogRecord`, `Handler`, and parent handler propagation.
- [Oracle Java SE 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): `publish`, `isLoggable`, `Formatter`, `flush`, `close`.
- [Oracle Java SE 17 — java.util.logging.LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): event metadata and caller information during async handoff.
- [SLF4J Manual](https://www.slf4j.org/manual.html): facade, parameterized logging, providers, and fluent API.
- [SLF4J FAQ](https://www.slf4j.org/faq.html): SLF4J 2.x ServiceLoader/provider and version compatibility.
- [SLF4J Error Codes](https://www.slf4j.org/codes.html): missing/multiple providers, NOP behavior.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html): effective level, hierarchy, additivity, and request processing.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): appenders, layouts/encoders, `AsyncAppender`, and rolling.
- [Logback Manual — MDC](https://logback.qos.ch/manual/mdc.html): per-thread context, propagation, and cleanup.
- [Apache Log4j 2 — Architecture](https://logging.apache.org/log4j/2.x/manual/architecture.html): `LoggerContext`, `LoggerConfig`, `AppenderRef`, `Appender`, Layout/Manager.
- [Apache Log4j 2 — Filters](https://logging.apache.org/log4j/2.x/manual/filters.html): multiple filtering stages in the pipeline.
- [Apache Log4j 2 — Async logging](https://logging.apache.org/log4j/2.x/manual/async.html): asynchronous logger/appender, queue-full policy, and trade-offs.
- [Apache Log4j 2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html): configuring Loggers, Appenders, filters, and `AppenderRef`s.
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): timestamp, severity, body, resource, attributes, and tracing context.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): event scope, sensitive data, log security, and logging management.
