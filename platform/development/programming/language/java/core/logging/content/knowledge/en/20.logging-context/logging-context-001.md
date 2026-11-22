# Logging Context in Java Logging

## 1. What is logging context?

**Logging context** is the set of information that helps readers understand **which request, operation, component, and processing state a log event belongs to**. The log level and message tell you what happened; the context helps determine **under what circumstances it happened** so you can investigate and correlate events.

A log line without context:

~~~text
WARN Payment provider timed out
~~~

The same event with context:

~~~text
2026-11-09T12:34:56.789Z WARN
service=checkout
logger=com.example.payment.PaymentClient
event_code=PAYMENT_ATTEMPT_TIMEOUT
request_id=req-42
trace_id=trace-abc
operation=authorize
attempt=2
provider=primary-gateway
outcome=retrying
message="Payment provider timed out"
~~~

The second example shows that this is a failure **of a single attempt** that is being retried, which request it belongs to, and which part of the system it occurred in. Not every field is required for every log, but **the right chosen fields** help distinguish a normal event, a retry attempt, and a final failure.

**Context is not the Logger itself or the message.** A logger named **com.example.payment.PaymentClient** represents the emitting source, whereas per-request context can differ each time that class handles a request. A single shared Logger used across millions of requests can still record different `request_id` values without creating new Loggers.

### Practical goals

- Correlate logs belonging to the same request, job, or transaction.
- Trace the execution path across multiple layers and services.
- Identify the current operation and the involved dependency.
- Distinguish individual retry attempts from the final outcome.
- Find the root cause of an exception without guessing from the message.
- Support querying by `event_code`, `service`, `release`, or `trace`.
- Protect sensitive data by selecting only the necessary fields.

**Principle:** Context must be **properly scoped**, **attached to the event**, **cleaned up according to its lifecycle**, and **free of data beyond what is authorized to be collected**.

## 2. What types of context does a log event have?

They can be grouped into the following categories:

| Category | Example fields | Source |
| --- | --- | --- |
| **Event metadata** | timestamp, level, logger_name, event_code | Logger or logging backend |
| **Application/resource** | service, environment, release, instance_id | Deployment configuration |
| **Execution** | thread_name, operation, attempt | Code and runtime |
| **Request/correlation** | request_id, correlation_id, trace_id, span_id | Request middleware, tracing |
| **Business (permitted)** | order_id, payment_operation, outcome | Selected business data |
| **Error** | error_type, reason_code, cause, stack trace | Throwable and error handling |
| **Performance** | duration_ms, size_bytes, retry_count | Measured at the source |

### Static context

Some fields rarely change during an instance's lifecycle:

~~~json
{
  "service": "checkout",
  "environment": "production",
  "release": "2.4.1",
  "region": "ap-southeast-1"
}
~~~

These fields are usually configured at the **backend, JSON encoder, or collector**, rather than passed manually into every log call.

### Dynamic per-request context

A specific request might have:

~~~json
{
  "request_id": "req-42",
  "trace_id": "trace-example",
  "operation": "createOrder"
}
~~~

These fields must change according to the exact request/job, and must not leak to another request on the same thread.

### Event-specific context

A `PAYMENT_RETRY` event might add:

~~~json
{
  "event_code": "PAYMENT_RETRY",
  "attempt": 2,
  "reason_code": "GATEWAY_TIMEOUT",
  "outcome": "retrying"
}
~~~

There is no need to attach **attempt=2** to every log in the request, because some events do not belong to the second attempt. The narrower a context's scope, the closer it should be declared to where the event is emitted.

## 3. How does context differ from message, Logger name, and log level?

Suppose the Java code is written as:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);

log.info("Order created, orderId={}", orderId);
~~~

This is illustrative code using **org.slf4j.Logger** and **LoggerFactory**, assuming the classes are imported, the `orderId` variable exists, and the code is inside an appropriate class/method scope.

Three components:

- **Logger name:** Usually the class name **OrderService** or its full package name, helping locate the emitting source.
- **Level INFO:** The priority level of the event.
- **Message:** Describes the action—here, creating an order.

If you need to query **order_id** and **request_id** separately, embedding everything into the message may force the system to parse strings. With backends that support structured logging, you should add **named fields** instead of merely concatenating them into a sentence.

**Do not create a new Logger for every request ID.** Logger names are relatively stable categories; creating millions of loggers named after requests can increase resource usage and make level configuration by package/class hard to control.

## 4. How are logging context and structured logging related?

**Logging context** is the information attached to an event. **Structured logging** is the way information is represented as typed fields, such as JSON or key-value pairs.

Not all context has to be in JSON. For example:

~~~text
INFO [request_id=req-42] Order created
~~~

already includes a human-readable context field, though a search system might still have to parse text.

A clearer JSON record:

~~~json
{
  "timestamp": "2026-11-09T12:34:56.789Z",
  "level": "INFO",
  "service": "orders",
  "logger_name": "com.example.orders.OrderService",
  "event_code": "ORDER_CREATED",
  "request_id": "req-42",
  "order_id": "ORD-42",
  "outcome": "success",
  "message": "Order created"
}
~~~

These fields must actually be preserved by the **encoder/layout and collector**. Simply adding context via a Java API does not mean it has been written to the file or ingested into the search system.

**Some context should be strings**, such as `request_id` and `trace_id`; **some should be numbers/booleans**, such as `attempt`, `duration_ms`, and `cache_hit`. Do not convert every value into a String if you need numeric filtering or aggregation. Traditional MDC is usually a String–String map, whereas a backend's key-value event mechanism can preserve richer types.

## 5. How long should context live?

The lifetime scope determines which values need to be set and when they must be cleared.

~~~text
Application / instance
  └── service, environment, release
      |
      └── request / message / job
          └── request_id, trace_id
              |
              └── operation
                  └── operation=createOrder
                      |
                      └── attempt
                          └── attempt=2, reason_code=TIMEOUT
                              |
                              └── a specific log event
                                  └── event_code, outcome, error_type
~~~

For example:
- **service** can be attached at the encoder/collector for the entire process.
- **request_id** is set at the start of request handling and removed when the request ends.
- **operation** is set upon entering an operation and restored to its previous value when the operation finishes.
- **attempt** is attached to a retry event or a narrow scope.
- **error_type** reflects the exception of that specific event.

**Do not store business context in mutable static variables shared across threads.** If one request updates a static variable **currentRequestId**, another request can log the wrong ID. Most context logging solutions use mechanisms tied to the execution flow or controlled context propagation.

## 6. What is MDC in SLF4J?

**MDC (Mapped Diagnostic Context)** is an SLF4J API for storing **String key–String value** pairs related to logging context, typically per-thread depending on the backend. For example, at the start of a request you set the request ID, and subsequent log calls downstream can have the layout include the request ID without manually passing the ID into every message.

Illustrative snippet with SLF4J:

~~~java
import org.slf4j.MDC;

MDC.put("request_id", requestId);
try {
    processRequest();
} finally {
    MDC.remove("request_id");
}
~~~

In this snippet, **requestId** and **processRequest()** are already defined in the application; this is not a standalone Java program. **MDC.put** does not automatically make the console display `request_id`: the backend must configure an appropriate `PatternLayout` or JSON encoder.

### Why must you clean up in `finally`?

A web server typically uses a thread pool:

~~~text
Thread worker-1:
   request A -> MDC request_id=A
   request A ends
   request B -> reuses worker-1
~~~

If request A forgets to clear MDC, the initial logs of request B may carry **request_id=A**, misleading investigations and leaking context between users.

**Always clean up or restore context in `finally`.** When there is no prior context and only a single key is set, `MDC.remove(key)` is usually sufficient. If nested code might **overwrite an existing key**, you should save and restore the previous context map rather than just calling `remove`.

Example of restoring the full SLF4J context within a scope:

~~~java
import java.util.Map;
import org.slf4j.MDC;

Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("operation", "reserveStock");
    processStockReservation();
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
~~~

This is an illustrative snippet, assuming **processStockReservation()** exists. The goal is to preserve `request_id` and `trace_id` from the outer scope while restoring **operation** afterward. **getCopyOfContextMap** returns a copy of the context if present; **setContextMap** restores the saved pairs.

The underlying MDC implementation and how context is bound to threads depend on the provider/backend. Do not treat MDC as a durable store for business state.

## 7. Log4j 2 ThreadContext

In **Log4j 2**, **ThreadContext** provides the mechanism for attaching context to logging events. Common constructs include:
- **Context Map:** Key–value pairs.
- **Context Stack:** Stack-ordered values, when that mechanism is genuinely needed.

Illustrative example:

~~~java
import org.apache.logging.log4j.ThreadContext;

ThreadContext.put("request_id", requestId);
try {
    processRequest();
} finally {
    ThreadContext.remove("request_id");
}
~~~

Just like MDC, code must clean up context when the request ends. When nested scopes might overwrite an existing key, design an appropriate snapshot/restore or scoped mechanism instead of always calling `remove` and losing the parent scope's value.

Log4j 2 provides scoped APIs such as **ThreadContext.putCloseable** in supported versions; verify its cleanup/restore behavior under nesting before using it in complex middleware.

For example, a text pattern in Log4j 2 can access the Context Map via the corresponding conversion such as **%X{request_id}**, depending on the layout. For structured JSON, you need a supported JSON layout and configuration to export the fields.

**SLF4J MDC and Log4j ThreadContext serve similar purposes, but they are not arbitrarily interchangeable APIs.** When an application uses SLF4J with a Log4j 2 provider, test that context actually flows through the real bridge/provider.

## 8. Where does context go in asynchronous execution?

This is one of the most critical issues in logging context.

In Java, a task may run across:
- **ExecutorService**.
- **CompletableFuture.supplyAsync/runAsync**.
- Web server thread pools.
- Scheduled jobs, queue consumers.
- Reactive/non-blocking frameworks.
- Service boundaries over HTTP, gRPC, or message brokers.

**MDC/ThreadContext is not propagated across these boundaries by default.** Under the basic model, a `ThreadLocal` belongs only to the current thread, whereas an async task may execute on a different thread. Both Java virtual threads and frameworks with their own context mechanisms require examining their specific semantics.

Example of missing propagation:

~~~text
Request thread:
   MDC request_id=req-42
   log: REQUEST_RECEIVED request_id=req-42

Executor thread:
   MDC is not set
   log: INVENTORY_RESERVED request_id=(missing)
~~~

If a logger on the worker thread reads the current MDC, it will not find `request_id` even though the work belongs to the same request.

### Capture, install, and restore

The standard pattern:

1. **Capture** a copy of the context when preparing to submit a task.
2. **Install** that context on the thread executing the task.
3. Perform the work and emit logs.
4. **Restore or clear** the previous context in `finally`.
5. Do not propagate disallowed fields across new boundaries.

Illustrative example with SLF4J MDC and `Executor`:

~~~java
Map<String, String> captured = MDC.getCopyOfContextMap();

executor.submit(() -> {
    Map<String, String> old = MDC.getCopyOfContextMap();
    try {
        if (captured == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }

        performTask();
    } finally {
        if (old == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(old);
        }
    }
});
~~~

This is an illustrative snippet, assuming variables, imports, and functions already exist. For production frameworks, use an **official context propagation mechanism** or an executor/task wrapper to avoid repeating error-prone logic in many places.

**Do not blindly propagate every ThreadLocal across requests.** Propagate only correlation fields and metadata that are genuinely needed, governed by a clear security policy.

## 9. Standalone Java 17 example: per-request context and propagation

The following example uses **java.util.logging** built into JDK 17, without requiring SLF4J/Logback. The goal is to illustrate these ideas:
- A single shared Logger for the entire program.
- Request context containing `request_id`, `trace_id`, and `operation`.
- Per-thread context held in a simple **ThreadLocal**.
- Opening a **scope** to add or overwrite context and **restoring the previous values** on close.
- Submitting a task to **ExecutorService**, explicitly transferring a copy of the context.
- Creating a **LogRecord containing a snapshot of the context** at the moment the event is emitted.
- A Handler that writes deterministic stdout, independent of timestamps or thread names.
- Verifying that the main thread's context has been cleared.

**Note:** This custom `ThreadLocal` and `Handler` are an **educational model**, not production MDC or standard tracing. In real applications, use SLF4J MDC, Log4j ThreadContext, OpenTelemetry context, or a framework-supported mechanism. The **trace-demo** value below is only an illustrative label, not a trace ID conforming to distributed tracing propagation standards.

Create the file **LoggingContextDemo.java**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingContextDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.orders.OrderService");

    private static final ThreadLocal<Map<String, String>> CONTEXT =
            ThreadLocal.withInitial(LinkedHashMap::new);

    private static final class Scope implements AutoCloseable {
        private final Map<String, String> before;

        private Scope(Map<String, String> before) {
            this.before = before;
        }

        @Override
        public void close() {
            if (before.isEmpty()) {
                CONTEXT.remove();
            } else {
                CONTEXT.set(before);
            }
        }
    }

    private static Scope withContext(Map<String, String> additions) {
        Map<String, String> before =
                new LinkedHashMap<>(CONTEXT.get());
        Map<String, String> next =
                new LinkedHashMap<>(before);
        next.putAll(additions);
        CONTEXT.set(next);
        return new Scope(before);
    }

    private static Map<String, String> snapshot() {
        return new LinkedHashMap<>(CONTEXT.get());
    }

    private static void logEvent(String code) {
        LogRecord record = new LogRecord(Level.INFO, code);
        record.setLoggerName(LOG.getName());

        // Snapshot at event creation time:
        record.setParameters(new Object[] {snapshot()});
        LOG.log(record);
    }

    private static final class ContextOutputHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }

            @SuppressWarnings("unchecked")
            Map<String, String> context =
                    (Map<String, String>) record.getParameters()[0];

            System.out.println(
                    record.getLevel().getName()
                    + " | request_id="
                    + context.getOrDefault("request_id", "-")
                    + " | trace_id="
                    + context.getOrDefault("trace_id", "-")
                    + " | operation="
                    + context.getOrDefault("operation", "-")
                    + " | " + record.getMessage());
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

    public static void main(String[] args) throws Exception {
        Handler output = new ContextOutputHandler();
        output.setLevel(Level.INFO);

        LOG.setLevel(Level.INFO);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(output);

        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try {
            try (Scope request = withContext(Map.of(
                    "request_id", "req-42",
                    "trace_id", "trace-demo",
                    "operation", "createOrder"))) {

                logEvent("REQUEST_RECEIVED");

                Map<String, String> captured = snapshot();

                Future<?> task = executor.submit(() -> {
                    try (Scope requestInWorker =
                            withContext(captured);
                         Scope operation =
                            withContext(Map.of(
                                    "operation", "reserveStock"))) {
                        logEvent("INVENTORY_RESERVED");
                    }
                });

                task.get();
                logEvent("REQUEST_COMPLETED");
            }

            System.out.println(
                    "CONTEXT_CLEARED=" + CONTEXT.get().isEmpty());
        } finally {
            executor.shutdown();
            CONTEXT.remove();
            LOG.removeHandler(output);
            output.close();
        }
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 LoggingContextDemo.java
java LoggingContextDemo
~~~

**Exact stdout of the demo:**

~~~text
INFO | request_id=req-42 | trace_id=trace-demo | operation=createOrder | REQUEST_RECEIVED
INFO | request_id=req-42 | trace_id=trace-demo | operation=reserveStock | INVENTORY_RESERVED
INFO | request_id=req-42 | trace_id=trace-demo | operation=createOrder | REQUEST_COMPLETED
CONTEXT_CLEARED=true
~~~

### Why are the three context lines correct?

1. **withContext(...)** copies the current context and then adds fields; it does not mutate the parent scope's Map.
2. The main thread opens a scope with `request_id`, `trace_id`, and `operation=createOrder`, then logs `REQUEST_RECEIVED`.
3. **snapshot()** creates a copy before submitting work to the executor, avoiding any dependency on whether the worker shares the same `ThreadLocal`.
4. The worker thread opens `requestInWorker` with the passed copy, then opens an inner scope that overrides `operation` to **reserveStock**.
5. When the worker finishes, the two scopes close in reverse order; the context is restored or cleared from the worker thread.
6. **task.get()** ensures the task completes before the main thread emits `REQUEST_COMPLETED`, making the output order deterministic and verifiable.
7. The main thread still retains `operation=createOrder`; the context inside the worker does not alter the main thread's context.
8. When the request scope closes, the main thread's original context was an empty map, so the `ThreadLocal` is removed and the check prints **CONTEXT_CLEARED=true**.
9. **LogRecord.setParameters** holds a copy of the context at event creation time. The Handler reads that copy rather than the `ThreadLocal` of the publishing thread; this is a key principle for asynchronous logging.
10. **setUseParentHandlers(false)** prevents parent JUL Handlers from printing unwanted log lines, and the custom Handler omits timestamps so the demo produces fixed stdout.

### Limitations of the example

- **Trace ID** is simulated data and does not perform distributed tracing.
- **ThreadLocal** only mimics part of MDC's behavior; it lacks backend integration, structured encoders, and framework propagation.
- **Handler** prints only three fixed fields; a production backend can output JSON, timestamps, exceptions, and many schema-defined fields.
- You should not copy an entire request object or payload into the context Map, due to security risks and added overhead.
- With multiple concurrent tasks, log ordering across tasks is not necessarily deterministic. The example uses a single-thread executor and `task.get` solely to verify how context is propagated and restored.
- Beyond context cleanup, production code must handle shutdown, interruption, timeouts, and task failures according to business requirements.

**Key takeaway:** Context must be **captured at boundaries**, **installed within the execution scope**, **attached to the event**, and **cleaned up or restored after use**. Do not rely on a mutable global variable like `currentRequestId`.

## 10. Context in SLF4J 2.x: MDC and key-value events

SLF4J 2.x offers two complementary sets of techniques.

### MDC: shared information across a scope

~~~java
MDC.put("request_id", requestId);
try {
    log.info("Validating order");
    validateOrder();
    log.info("Order validation completed");
} finally {
    MDC.remove("request_id");
}
~~~

This illustrative snippet assumes logger **log**, `requestId`, `validateOrder`, and the `MDC` import already exist. If the backend layout outputs MDC, **both logs** include `request_id` without the code needing to pass the ID into each call.

### Fluent key-value: information for a specific event

~~~java
log.atInfo()
        .addKeyValue("event_code", "ORDER_CREATED")
        .addKeyValue("order_id", orderId)
        .addKeyValue("amount_minor", amountMinor)
        .addKeyValue("currency", "VND")
        .log("Order created");
~~~

This is the **SLF4J 2.x** API, not SLF4J 1.7. The variables belong to the application method. The fluent API can attach fields to **a single event**, whereas MDC is used for context spanning multiple events within the same scope.

**Do not assume `addKeyValue` automatically turns logs into JSON.** The provider/backend and encoder/layout must be configured to output key-value pairs. Numeric values should generally remain numbers in structured events if the encoder supports them, rather than being forced into strings without reason.

When an exception occurs:

~~~java
log.atError()
        .addKeyValue("event_code", "ORDER_SAVE_FAILED")
        .addKeyValue("order_id", orderId)
        .addKeyValue("outcome", "failed")
        .setCause(exception)
        .log("Cannot persist order");
~~~

**setCause** passes the `Throwable` to the backend so it can output the cause chain and stack trace. Context does not replace the need to pass exceptions through the proper API.

## 11. How to display context in Logback

With **SLF4J + Logback**, `PatternLayout` can include MDC in text output using the **%X{key}** conversion. Example **logback.xml**:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} req=%X{request_id} trace=%X{trace_id} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

This is a **text logging configuration**, not JSON. Only after the code sets **MDC `request_id`/`trace_id`** can the pattern output those values in their respective positions.

For true **structured JSON**, you need a JSON encoder/layout compatible with your Logback version and must ensure MDC/SLF4J key-value pairs are serialized into fields according to your schema. Do not simply wrap `%msg` in curly braces and treat that as valid JSON.

### Checklist when context does not appear

- Did the code set MDC on the right thread?
- Was the field removed too early?
- Did an async operation lack propagation?
- Is Logback actually the active SLF4J provider at runtime?
- Does the pattern or JSON encoder output that MDC field?
- Is the collector keeping the field, or renaming/dropping it?

**Context present in MDC but ignored by the encoder will not be queryable on dashboards.** Always verify the actual output.

## 12. Context in Log4j 2 and Layouts

In Log4j 2, **ThreadContext** is typically accessed from a Layout via the corresponding pattern such as **%X{request_id}** or included in a JSON template depending on the backend.

Illustrative **log4j2.xml** configuration for text-only output:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="OUT" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%d{ISO8601} %-5p req=%X{request_id} trace=%X{trace_id} %c - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="OUT"/>
        </Root>
    </Loggers>
</Configuration>
~~~

The configuration above requires the appropriate Log4j 2 dependencies; it does **not** work as a `logback.xml` or JUL `logging.properties` file.

With a JSON layout, you can map fields from `ThreadContext`. You must test field names, dropped data or type changes, and `Throwable` handling when switching backends or upgrading versions.

**ThreadContext Map typically holds string values.** If you need `duration_ms` to be a true number in JSON, use a typed event field mechanism and an appropriate encoder rather than assuming every numeric string in MDC will be converted into a number by the collector.

## 13. Does Java Util Logging have built-in MDC?

**java.util.logging (JUL)** provides **Logger, LogRecord, Handler, Formatter, and Filter**, but it does not have a standardized key–value map MDC API like **org.slf4j.MDC**.

A JUL application can:
- Pass parameters into `LogRecord`.
- Create a custom `Formatter`/`Handler`.
- Use a dedicated context holder and capture a snapshot when creating a `LogRecord`.
- Use a tested bridge or adapter to route logs to a unified backend.

The Java 17 example above illustrates context using **ThreadLocal + Map + LogRecord.parameters**. This is a way to teach the underlying principle, not JUL's default structured logging API. Do not pass **LogRecord.parameters** directly into a standard `Formatter` and expect it to understand keys like `request_id`, `trace_id`, or `operation`.

**Do not randomly mix JUL Handlers with Logback Appenders or Log4j 2 Appenders.** Each backend has its own configuration system. If using a bridge, verify the pipeline and choose the right direction to avoid duplicate logs or forwarding loops.

## 14. Logging context and distributed tracing

**Tracing context** is used to connect spans across boundaries. Key fields:

| Field | Role |
| --- | --- |
| **trace_id** | Identifies the entire trace |
| **span_id** | Identifies an individual span |
| **trace flags** | Sampling information or tracing state per convention |
| **request_id** | ID of the request within the application |
| **correlation_id** | ID used to link steps according to a business contract |

A **request ID** is not automatically a standard trace ID. When an application uses OpenTelemetry or a tracing framework, you should obtain `trace_id`/`span_id` from the **current span context**, rather than generating arbitrary ID strings that are not propagated across services.

### Propagating context across services

Conceptual example:

~~~text
Gateway:
   request_id=req-42, trace_id=t123, event=REQUEST_RECEIVED
      |
      v
Order Service:
   request_id=req-42, trace_id=t123, event=ORDER_VALIDATED
      |
      v
Payment Service:
   request_id=req-42, trace_id=t123, event=PAYMENT_RETRY
~~~

The **t123** values here are illustrative labels only, not `trace_id` values formatted for every protocol.

In production, context is usually propagated via **headers/tracing protocols** or message metadata, such as the **W3C Trace Context** specification for HTTP when supported by frameworks. Middleware must receive, validate, and propagate context properly; do not blindly trust any client-supplied correlation header if it could cause injection, data exposure, or cross trust boundaries.

**Logging context alone does not guarantee causal ordering.** Even when multiple services share the same `trace_id`, timestamps across hosts can suffer from clock skew. Combine traces, sequences, event types, and telemetry to understand ordering.

## 15. MDC and nested scopes: common pitfalls

Suppose a service sets:

~~~text
request_id=req-42
operation=createOrder
~~~

Inside the `reserveStock` method, we override:

~~~text
operation=reserveStock
~~~

After `reserveStock` finishes, **operation must return to `createOrder`**. If the inner scope simply calls `remove("operation")`, the parent context loses `operation`. That is why **snapshot and restore** are needed whenever a key might be overwritten.

Another mistake: a middleware sets `request_id` and downstream code calls **MDC.clear()** in `finally`, wiping out `trace_id` and fields managed by outer layers. If all context needs to be cleared at a request boundary, that must be an explicit policy; inside a child scope, clean up only what you own or restore the snapshot.

### Scope ownership

- Request middleware typically owns `request_id` and baseline context.
- Tracing middleware/instrumentation owns `trace_id` and `span_id`.
- A service operation can own `operation` and event-specific fields.
- A downstream library should not arbitrarily clear all of the caller's context.

**Context ownership is just as important as I/O resource ownership.** When it is unclear who sets a field, it is easy to clear too broadly, overwrite values, or retain values for too long.

## 16. What data should or should not be placed in context?

### Worth considering

- `service`, `environment`, `release`, `instance_id`.
- `request_id`, `trace_id`, `span_id` with proper format and source.
- `operation`, `event_code`, `outcome`.
- `error_type`, `reason_code`.
- `order_id` or `transaction_id` if policy permits.
- `attempt`, `duration_ms`, `size_bytes` on appropriate events.

### Avoid

- Passwords, access/refresh tokens, API keys, private keys.
- Authorization headers, login cookies, session secrets.
- Full request/response bodies.
- Payment card numbers, sensitive account data, or unnecessary PII.
- Large domain objects or references to mutable objects.
- Full URLs with query strings containing tokens or personal data.
- Unvalidated fields that can be manipulated by clients.

**Structured context can cause sensitive data to appear on every log line of a request.** If you store a token in MDC, not just one log is at risk of exposure; every layout that outputs MDC can repeat that token across dozens or hundreds of events.

### Client-supplied data

A request ID from a client header is not always trustworthy. The system may need to:
- Validate length and format.
- Generate an internal ID when the client does not provide one or the value is invalid.
- Prevent log injection via control characters.
- Never use a client-provided ID as an access credential or security identifier.
- Separate `external_correlation_id` from `internal_request_id` when required by contract.

## 17. Context and cardinality

**Cardinality** is the number of distinct values a field can take. Some fields have low cardinality: `level`, `service`, `environment`, `event_code`, `outcome`. Some fields have high cardinality: `request_id`, `trace_id`, `order_id`.

**High-cardinality fields do not mean they must be omitted from logs.** Request IDs are essential for finding a specific request. However, turning `request_id` into a metric label can create an excessive number of time series.

Distinguish between:
1. **Fields stored in logs** for investigation.
2. **Fields indexed** for fast querying.
3. **Metric labels** for grouping measurements.

Do not index every field simply because it exists in context. Set policies based on query frequency, retention, selectivity, and cost. Fields used to group dashboards should have a bounded set of values; avoid generating `event_code` values containing dynamic IDs.

### Log volume

Suppose a service emits **1,000 logs/second**, and each record after adding context is **600 bytes**:

~~~text
1,000 × 600 = 600,000 bytes/second
600,000 × 86,400 = 51.84 GB/day of raw data
~~~

This is a rough estimate, before compression, indexing, replication, or retention. Adding context makes events more useful, but it also incurs write, encoding, network, and storage costs. Do not copy an entire request body into context just to "have enough information" when most of that data is never used for investigation.

## 18. Context snapshots in asynchronous logging

An often-overlooked detail: **an already-created event** may be processed later by a Handler/Appender on a different thread.

If a Formatter reads MDC/ThreadLocal **from the thread writing to the file**, rather than the context captured at event creation time, it may pick up the logging worker's context or no context at all.

Conceptual example:

~~~text
T0: Request thread creates event E with request_id=req-42
T1: E sits in the async appender's queue
T2: Request scope ends and clears context
T3: Log worker writes E to file
~~~

**Right:** Event E retains **req-42** that was snapshotted at T0.

**Wrong:** The worker at T3 reads its own current MDC and writes missing or wrong request information.

Backends that support asynchronous logging typically have a mechanism to prepare/capture event context. If you write a custom Handler or queue, you must design an explicit snapshot. The Java demo uses **new LinkedHashMap<>(CONTEXT.get())** when creating `LogRecord` to illustrate this.

At the same time, a snapshot should not hold a reference to a large mutable object that can still be modified after the event has been queued.

## 19. How do exceptions and context relate?

For exceptions, context should answer:
- Which **operation** failed?
- Which **request_id/trace_id**?
- Which **event_code/reason_code**?
- Is the **outcome** `failed` or `retrying`?
- What is the **error_type**?
- Is the **Throwable/cause** preserved?

SLF4J 2.x example:

~~~java
log.atError()
        .addKeyValue("event_code", "PAYMENT_AUTHORIZATION_FAILED")
        .addKeyValue("operation", "authorize")
        .addKeyValue("reason_code", "PROVIDER_TIMEOUT")
        .addKeyValue("outcome", "failed")
        .setCause(exception)
        .log("Payment authorization failed");
~~~

MDC may already carry `request_id` and `trace_id` from middleware. Event fields add `outcome` and `reason_code`; **setCause** preserves the `Throwable`.

**Do not use context as an excuse to log the same stack trace at every layer.** If Repository, Service, and Controller all log `ERROR` and rethrow, log volume is inflated. Choose the boundary responsible for the final error, while logging lower-level events only when they carry distinct, valuable context.

Do not place `exception.getMessage()` into a persistent request-wide context if it might contain sensitive data and only pertains to a single event.

## 20. Context with Spring Boot and other frameworks

In Spring Boot applications, request filters, interceptors, or observability instrumentation are usually the right place to:
- Set the request ID and correlation ID.
- Attach/read tracing context.
- Ensure cleanup when the request finishes, even if an exception occurs.
- Choose a JSON encoder or pattern in the backend configuration.
- Propagate context across framework-managed task executors where supported.

However, **exact mechanisms vary by Spring Boot, SLF4J, Logback/Log4j 2, and tracing framework version**. Do not assume every `Executor` or reactive pipeline automatically propagates MDC just because the project has tracing enabled.

A practical test checklist:

1. Request A has `request_id=A`.
2. Request B has `request_id=B`.
3. A and B run concurrently or reuse the same worker thread.
4. Every log for A/B must have the correct context.
5. After a request finishes, logs from subsequent tasks no longer contain the old request's ID.
6. A `CompletableFuture` submitted from A retains correlation when framework propagation is configured.
7. Exceptions still carry `trace_id` and do not skip context cleanup in `finally`.

In reactive systems, do not rely on `ThreadLocal` as a global assumption; check the context mechanism of Reactor or the relevant framework and how adapters bridge context to logging events.

## 21. Context in files, console, and collectors

Having context in Java is not enough; you must verify it actually appears in the output.

Example pipeline:

~~~text
Request middleware
    |
    | request_id, trace_id, operation
    v
SLF4J MDC / Log4j ThreadContext
    |
    v
Logger emits event
    |
    v
Backend: Layout / Encoder
    |
    +--> Console text pattern
    +--> File JSON lines
    |
    v
Collector -> parser -> index/storage -> dashboard
~~~

Common issues:
- The pattern lacks **%X{request_id}**, so the console is missing the request ID.
- The JSON encoder does not export MDC/key-value pairs.
- Fields are emitted under different names than the collector's schema expects.
- The collector drops fields due to size limits or schema allowlists.
- The source timestamp is overwritten by the ingestion timestamp.
- Request ID is a string, but the parser maps it to a different type.
- Logs are truncated mid-line during file rotation or overload.

**Integration tests across the entire pipeline are necessary.** A JSON event that has fields in a file can still lose them at the collector; search results are the real proof that operators can actually use the context.

## 22. Common mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Message-only logs with no correlation | Hard to find all events for a request | Attach `request_id`/`trace_id` with proper scope |
| Creating a Logger per request ID | Many unnecessary loggers/categories | Name Loggers by class/package |
| Using a static `currentRequestId` variable | Race conditions, mixed-up requests | Use scoped context and propagation |
| Not clearing MDC in a thread pool | Context leaks across requests | `finally`, scopes, and restore |
| Child scope removes parent scope's field | Missing context after returning | Snapshot and restore previous values |
| Assuming MDC automatically crosses Executor | Worker lacks IDs | Capture/install/restore |
| Formatter reads ThreadLocal during async write | Event gets wrong ID | Capture context onto event at creation |
| Setting MDC without configuring layout | Log output lacks fields | Verify encoder/`PatternLayout` |
| Putting dynamic order IDs inside `event_code` | High cardinality | Keep `event_code` stable, `order_id` separate |
| Putting tokens or payloads in MDC | Exposure across many log lines | Field allowlists, redaction |
| Using arbitrary `trace_id` not from tracing | Distributed queries fail to link | Read IDs from tracing context |
| Changing `request_id`/`attempt` types per service | Schema conflicts | Standardize data types |
| Repeating `ERROR` at every layer | Inflated incident counts | Choose a single final error-logging boundary |
| Never checking the collector | Fields lost after ingestion | End-to-end testing |
| Indexing every high-cardinality field | Higher cost | Selective indexing policy |
| Treating JSON as encryption | Data remains readable | Access control, retention, redaction |

## 23. Checklist for applying logging context in Java

1. **Categorize context:** Static per service, dynamic per request, operation, and event.
2. **Logger name:** Keep stable by class/package; do not create a Logger per request.
3. **Schema:** Use consistent field names and clear units where needed.
4. **Correlation IDs:** Propagate `request_id`, `trace_id`, and `span_id` from valid sources and scopes.
5. **Scope:** Set context at appropriate boundaries; clean up/restore in `finally`.
6. **Async:** Capture and propagate context across tasks/executors/queues using reliable mechanisms.
7. **Snapshot:** Events must hold context from emission time, not read it after the scope has ended.
8. **Backend:** Configure MDC/ThreadContext in Logback/Log4j 2 or an appropriate JUL approach.
9. **Output:** Verify that text patterns or JSON encoders actually emit the context.
10. **Throwable:** Attach causes to errors appropriately without losing stack traces.
11. **Security:** Never log tokens/passwords/cookies; limit personal data and payloads.
12. **Cost:** Review cardinality, indexing, log volume, and retention.
13. **Testing:** Cover concurrent requests, reused threads, async tasks, exceptions, and cleanup.
14. **Collector:** Verify fields/types after ingestion and searchability by `request_id`/`trace_id`.

## 24. Self-check questions

**1. How does logging context differ from a log message?**  
The message describes the event; context provides details such as request ID, operation, service, and outcome to show where that event belongs.

**2. Why shouldn't you create a Logger per request ID?**  
Logger names should be stable categories by class/package. A request ID is dynamic per-request context.

**3. Why must MDC be cleared or restored in `finally`?**  
Threads can be reused; without cleanup, logs from a later request will carry the previous ID.

**4. Does MDC automatically propagate across `ExecutorService`?**  
You should not assume so. You must capture, install, and restore context, or use framework-supported propagation.

**5. Why do nested scopes need to restore the previous context?**  
Because a child scope may overwrite the parent scope's `operation`; calling only `remove` would lose the previous value.

**6. When should an async event's context be captured?**  
It should be snapshotted at event creation time so that a backend worker processing it later still retains the original source context.

**7. How does SLF4J 2.x `addKeyValue` differ from MDC?**  
MDC typically holds context for multiple events within a scope; `addKeyValue` attaches fields to one specific event.

**8. Why might context present in MDC still not appear in a dashboard?**  
Because the layout, encoder, or collector may not export or retain that field.

**9. Should you put tokens in request MDC to make debugging easier?**  
No. Sensitive tokens can be repeated across many log lines. Use approved technical IDs instead.

**10. Does logging context automatically create standard tracing?**  
No. For `trace_id`/`span_id` to work across services, proper tracing context and propagation are required.

**Key takeaway:** **Logging context is information attached to an event to answer "what happened, where, and under which request and operation".** In Java, you can use SLF4J MDC, Log4j 2 ThreadContext, or a custom JUL mechanism. Keep context clearly scoped, propagate it properly across async boundaries, snapshot it onto events, clean up or restore it when scopes end, and emit only useful, safe fields. Proper context connects logs with traces and metrics without leaking information across requests.
