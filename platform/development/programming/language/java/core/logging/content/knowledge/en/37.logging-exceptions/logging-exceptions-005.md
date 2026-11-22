# Do Not Log the Same Error Multiple Times — Logging and Exceptions in Java

## 1. The Phenomenon of One Error Being Logged Repeatedly

A request may pass through a controller, service, repository, and error handler. If **each layer catches the exception, logs an ERROR, and rethrows**, the same failure appears multiple times in the logs:

~~~text
ERROR Repository - Connection refused
java.sql.SQLException: connection refused
  ...

ERROR OrderService - Could not create order
java.sql.SQLException: connection refused
  ...

ERROR OrderController - Request failed
com.example.OrderCreationException: cannot create order
Caused by: java.sql.SQLException: connection refused
  ...

ERROR GlobalExceptionHandler - Internal server error
com.example.OrderCreationException: cannot create order
Caused by: java.sql.SQLException: connection refused
  ...
~~~

In the scenario above, there is only **one technical error** and **one failed HTTP request**, yet there are four logging events at the ERROR level. The consequences include:

- Investigation noise: it is hard to tell whether there was one incident or four.
- Alerts and analytics count more ERRORs than the actual number of logical failures.
- Increased CPU, memory, I/O, index storage, and ingest cost because a long stack trace is repeated.
- Personal data or secrets are logged multiple times if the exception contains sensitive information.
- Ambiguous handling responsibility: every layer logs, and no single layer is clearly responsible for recording the final outcome.

**The solution is not to turn off all ERROR logs**, but to establish clear *ownership*: **each logical failure has one layer responsible for recording the outcome**, while lower layers preserve context/cause or perform recovery without logging the same error again.

"Log once" does not mean the entire system may only log one line across all requests, or that a given type of `SQLException` may only be logged once per day. Two independent requests that both fail are two separate failures; each failure can have its own event with its `requestId`.

## 2. A Logging Event Is Not the Same as a Single Text Line

A single call to `logger.error(message, exception)` can produce **one event**, yet the pattern layout prints it across multiple stack trace lines:

~~~text
ERROR requestId=req-42 code=ORDER_FAILED
com.example.OrderCreationException: cannot create order
    at com.example.OrderService.create(...)
Caused by: java.sql.SQLException: connection refused
    at com.example.Repository.save(...)
    ... 5 more
~~~

The "Caused by" lines are the cause chain belonging to **the same Throwable**, not a new log call. If you grep and count by the number of ERROR/stacktrace lines without understanding multiline formatting, it is very easy to misreport.

Conversely, a single event may intentionally be routed to both **console and file**. Two records in two sinks are not always a bug. You need to distinguish three phenomena:

| Situation | Nature | What to check |
| --- | --- | --- |
| Repository logs then throws, handler logs again | Two calls to the logging API | Call-site and `requestId` |
| Same appender attached to child logger and ROOT | One event emitted twice due to additivity | Logger/backend configuration |
| Collector reads from two sources or retries | Duplicate record after leaving the JVM | Agent, retry, dedup, and `eventId` |

When reporting duplicate logs, ask: **is it a duplicate event, a duplicate line, or a duplicate logical failure?** Those are three different problems, and each has a different fix.

## 3. The "Throw or Log" Rule in a Pipeline

An effective engineering rule:

- **Catch and rethrow** because it cannot be handled here: usually do not log ERROR at this point.
- **Catch and wrap the exception to add context:** pass the original cause into the new exception and rethrow, without logging again.
- **Catch and perform a successful fallback:** you may log a WARN/metric when observing degradation is useful, rather than reporting that the overall operation failed.
- **Catch to retry:** track each attempt with metrics/tracing and DEBUG level if needed; only log ERROR when the operation finally fails at the boundary.
- **Catch to return an HTTP error, terminate a job, or move a message to a DLQ:** this is usually the place to record one terminal event with the throwable and context.
- **Expected validation/business errors:** do not default to ERROR with a full stack trace; an access log or metric may be sufficient.
- **Cannot handle it:** let the exception propagate to a layer with an appropriate policy rather than catching it just to log.

Bad example:

~~~java
// Fragment with repository and OrderCreationException from the application.
try {
    repository.save(order);
} catch (SQLException ex) {
    log.error("Database failed", ex); // First ERROR
    throw new OrderCreationException("Order failed", ex);
}

// Elsewhere at the HTTP boundary, it logs again:
log.error("Create order failed", ex); // Second ERROR
~~~

Better approach:

~~~java
// Service translates the exception, preserves the cause, and does not log:
try {
    repository.save(order);
} catch (SQLException ex) {
    throw new OrderCreationException("Order failed", ex);
}

// A designated boundary logs the failure outcome:
log.error("Create order failed", ex);
~~~

These fragments illustrate **policy**, not standalone Java programs; `repository`, `order`, exceptions, and logger are application variables/classes.

**Exception to the rule:** a security audit event or an independent business event may need to be recorded even if the terminal boundary already logs an ERROR. Those are not two identical stack traces; they serve different purposes and have different retention policies.

## 4. One Layer Owns the Final Outcome

Designate a log **owner** for each operation:

~~~text
HTTP request
    |
    v
Controller
    |
    v
Service  ------------> wrap exception + cause, do not log
    |
    v
Repository ----------> throw SQLException, do not log
    |
    v
@ExceptionHandler / request boundary
    |
    +--> 1 ERROR: requestId + code + exception
    |
    +--> 500 response with safe error code
~~~

Lower layers enrich business context via exceptions or structured result types. The boundary records the final outcome once it knows whether the operation truly succeeded or failed.

**The owner is not always `ControllerAdvice`.** If an error occurs in a scheduler, message consumer, HTTP gateway, or async pipeline, the owner may be a task runner, a listener error handler, or a service that actually recovered. Design consistently for each type of entry point.

For example, if a service hits a timeout but uses cached data and still returns HTTP 200:

~~~text
Remote API timeout
       |
Service uses cache -> business result succeeds
       |
       +--> metric fallback_total++
       +--> optionally WARN fallback=cache
       +--> NO ERROR stack trace required because the request recovered
~~~

If repository/service skip logging, but the error handler drops the cause or `requestId`, investigators will lack data. Therefore, "do not log in lower layers" must go hand in hand with **preserving the exception chain** and structured context.

## 5. Exception Logging Decision Table

| Situation | Handling | Appropriate logging policy |
| --- | --- | --- |
| Repository throws an error, service will rethrow | Propagate/wrap | No ERROR in intermediate layers |
| Service wraps `SQLException` into a business exception | Preserve cause | Do not log the same stack trace again |
| Unrecovered HTTP 500 | Handler/boundary | One ERROR with cause and `requestId` |
| Validation 400 | Return error to client | Usually no full-stack ERROR |
| Authentication/authorization denied | Apply security policy | Security/audit event if needed; no duplicate logs |
| First timeout, retries remaining | Metric/trace attempt | Avoid ERROR on every attempt |
| Retries exhausted | Throw aggregate exception with cause | One terminal ERROR at the owner |
| Cache fallback succeeds | Continue processing | WARN/metric according to degradation severity |
| Scheduled job fails | Job runner | One terminal event with `jobId` |
| Message moved to DLQ | Consumer boundary | One outcome event with `messageId` |
| Multiple independent items fail in a batch | Batch policy | Summary or per-item event with ID |
| Exception handled in `CompletableFuture` | One completion handler | Avoid logging in both callback and caller |

ERROR/WARN/INFO levels are **operational conventions**, not a judgment from Java itself. If a transient error has severe impact or security obligations, the team may need to record another event; the key is still distinguishing **an independent event from a repeated stack trace**.

## 6. Standalone Java 17+ Example: Log Exactly Once

This example uses **`java.util.logging` (JUL)** built into the JDK, with no external libraries required. The repository throws an error, the service wraps it in a business exception while preserving the cause, and the endpoint performs final handling. An in-memory `Handler` records **`LogRecord`** instances to verify the number of logging events.

Create **`LogOnceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogOnceDemo {
    static final Logger LOG =
            Logger.getLogger("demo.web.boundary");
    static final List<LogRecord> EVENTS = new ArrayList<>();

    static class OrderCreationException extends RuntimeException {
        OrderCreationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String repository() {
        throw new IllegalStateException("database unavailable");
    }

    static String service() {
        try {
            return repository();
        } catch (IllegalStateException e) {
            // Do not log in intermediate layers.
            throw new OrderCreationException("cannot create order", e);
        }
    }

    static String endpoint() {
        try {
            return service();
        } catch (OrderCreationException e) {
            // This is the single terminal ERROR event.
            LOG.log(Level.SEVERE,
                    "requestId=req-42 action=CREATE_ORDER "
                    + "code=ORDER_FAILED", e);
            return "HTTP 500 requestId=req-42";
        }
    }

    public static void main(String[] args) {
        Handler memory = new Handler() {
            { setLevel(Level.ALL); }

            @Override
            public void publish(LogRecord r) {
                if (isLoggable(r)) EVENTS.add(r);
            }

            @Override public void flush() {}
            @Override public void close() {}
        };

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);
        LOG.addHandler(memory);
        try {
            String response = endpoint();
            System.out.println("response=" + response);
            System.out.println("logCount=" + EVENTS.size());

            LogRecord event = EVENTS.get(0);
            System.out.println("level=" + event.getLevel());
            System.out.println("hasThrowable=" +
                    (event.getThrown() != null));
            System.out.println("rootCause=" +
                    event.getThrown().getCause()
                            .getClass().getSimpleName());
            System.out.println("message=" + event.getMessage());
        } finally {
            LOG.removeHandler(memory);
            memory.close();
        }
    }
}
~~~

Compile/run:

~~~bash
javac LogOnceDemo.java
java LogOnceDemo
~~~

Verified stdout:

~~~text
response=HTTP 500 requestId=req-42
logCount=1
level=SEVERE
hasThrowable=true
rootCause=IllegalStateException
message=requestId=req-42 action=CREATE_ORDER code=ORDER_FAILED
~~~

**Result analysis:** `service` creates `OrderCreationException` using the `(String, Throwable)` constructor, so the cause remains `IllegalStateException`. Only `endpoint` calls `LOG.log(Level.SEVERE, message, e)`. The handler receives exactly one `LogRecord`, and `getThrown()` is non-null. `setUseParentHandlers(false)` prevents the event from propagating to parent handlers in this example.

**Limitations:** `endpoint()` returns the string `"HTTP 500 ..."` to simulate a response rather than running a real HTTP server. An in-memory `Handler` does not guarantee log durability; `ArrayList` is not a thread-safe container for multi-threaded tests. For production testing, test with an appropriate appender, concurrent requests, a real web boundary, and a collector.

With a custom JUL `Handler`, `publish()` should call `isLoggable(record)` to respect levels and filters. Count **`LogRecord`** instances rather than stack trace lines.

## 7. Preserve Cause and Suppressed Exceptions Instead of Logging at Every Layer

A `Throwable` in Java can carry:

- **Message:** describes the situation, not necessarily enough for investigation.
- **Stack trace:** where the error was created and propagated.
- **Cause:** the `Throwable` that caused this error, which can form a multi-level chain.
- **Suppressed exceptions:** additional errors, for example when `try-with-resources` closes a resource while another exception is being thrown.

If the service layer needs to translate `SQLException` into a business exception:

~~~java
// Fragment in a method that declares OrderCreationException.
catch (SQLException ex) {
    throw new OrderCreationException("Cannot create order", ex);
}
~~~

When the boundary logs the top-level exception, the backend can display both `OrderCreationException` and `SQLException` via "Caused by". There is no need to log `SQLException` separately in the repository just "so the stack trace isn't lost".

Common mistake:

~~~java
// WRONG: loses the cause.
catch (SQLException ex) {
    throw new IllegalStateException(ex.getMessage());
}
~~~

Do this instead:

~~~java
// PRESERVE CAUSE.
catch (SQLException ex) {
    throw new IllegalStateException("Order write failed", ex);
}
~~~

When you only want to rethrow the original exception, use `throw ex;` according to Java's catch/throws rules. Do not call `ex.printStackTrace()` and then throw, because that writes a stack trace to `stderr` outside the logging framework.

`try-with-resources` can produce suppressed exceptions. Do not log them separately in a loop when the parent exception already carries `getSuppressed()`. Test your actual pattern/encoder, because some formatters may truncate throwables depending on configuration; fix that at the **final output configuration**, not by scattering redundant logs.

## 8. SLF4J and Backends: Logging a Throwable as Part of the Event

In Spring Boot or large Java applications, code typically uses the **SLF4J API** with a Logback or Log4j 2 backend. To log the full exception, use the overload that takes a `Throwable`:

~~~java
// Fragment in a class with an org.slf4j.Logger named log.
log.error("Create order failed", exception);
~~~

The accompanying message helps readers understand which operation failed, and the `Throwable` lets the backend print the stack trace. With parameterized logging, a trailing `Throwable` argument is usually handled specially, but verify the **API/binding/backend and placeholder count** for your exact version. Use the explicit overload when you only need a message and a `Throwable`.

With **SLF4J 2.x**, there is a fluent API:

~~~java
// Fragment using SLF4J 2.x.
log.atError()
   .addKeyValue("requestId", requestId)
   .addKeyValue("errorCode", "ORDER_FAILED")
   .setCause(exception)
   .log("Create order failed");
~~~

This produces **one** event and attaches key-value context. You must call `.log(...)` to actually emit the event. Whether the backend renders key-values as structured fields or appends them to the message depends on the encoder/layout configuration; inspect the actual output.

Avoid writing:

~~~java
// Wrong strategy: two mechanisms emitting information for the same error.
exception.printStackTrace();
log.error("Create order failed", exception);
~~~

`printStackTrace()` writes directly to `stderr`, bypassing filters, MDC, and managed appenders. It can also be picked up by a collector from a separate stream, making one error look like two events.

Beyond reducing duplicate logs, protect sensitive data: `Throwable` messages from JDBC, HTTP, or third-party libraries may contain sensitive queries, inputs, or URLs. Select safe fields, apply redaction, and enforce access controls instead of returning raw exception details to API callers.

## 9. Spring MVC: One Global Handler Takes Responsibility

With Spring Web MVC, you can use **`@RestControllerAdvice`** and **`@ExceptionHandler`** as the terminal boundary for exceptions thrown from controllers. Underlying services only wrap/throw and do not emit an ERROR for the same logical failure.

Service **fragment** example (requires the corresponding domain classes and Spring `DataAccessException`):

~~~java
public Order create(CreateCommand command) {
    try {
        return repository.save(command);
    } catch (DataAccessException ex) {
        throw new OrderCreationException("Cannot create order", ex);
    }
}
~~~

Corresponding handler (requires Spring Web, SLF4J, and a `log` field in the class):

~~~java
@ExceptionHandler(OrderCreationException.class)
public ResponseEntity<ProblemDetail> onOrderFailure(
        OrderCreationException ex,
        HttpServletRequest request) {

    String requestId =
            String.valueOf(request.getAttribute("requestId"));

    // Single point emitting the final ERROR event.
    log.error("Create order failed requestId=" + requestId, ex);

    ProblemDetail body =
            ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);
    body.setTitle("Order creation failed");
    body.setDetail("The request could not be completed.");
    body.setProperty("requestId", requestId);

    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(body);
}
~~~

These snippets are **integration illustrations**, not standalone runnable programs; the handler must live inside a `@RestControllerAdvice` class with the appropriate imports, logger, and dependencies. `requestId` should be attached earlier by trusted middleware or a filter. If the request attribute is missing, define a policy rather than blindly trusting a spoofed header from the client.

Also account for other paths such as Spring Security, Servlet Filters, gateways, or proxies that return errors before the controller is reached. They have their own boundaries. An expected HTTP 400/401/403 does not automatically warrant a stack trace at ERROR level.

**Avoid multi-layer logging across frameworks:** controller catches and logs, rethrows so `@ExceptionHandler` logs, while an AOP aspect, interceptor, or error-tracking SDK also logs. Audit both custom exception handlers and automatic framework hooks.

## 10. Retries: Do Not Log ERROR on Every Attempt

A dependency that is temporarily unreachable might be retried 3 times:

~~~text
attempt 1: timeout -> log ERROR
attempt 2: timeout -> log ERROR
attempt 3: timeout -> log ERROR
terminal request failed -> log ERROR
~~~

Four ERRORs are not necessarily more valuable than one final ERROR with `attempts=3` and the full cause. A better structure:

~~~text
attempt 1: timeout -> retries_total++, tracing/DEBUG per policy
attempt 2: timeout -> retries_total++, tracing/DEBUG per policy
attempt 3: timeout -> retries exhausted, throw wrapper with cause
HTTP boundary: 1 ERROR outcome=FAILED attempts=3
~~~

Illustrative logic (fragment; client and metrics classes belong to the application):

~~~java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        return client.call();
    } catch (TransientNetworkException ex) {
        retryCounter.increment();
        if (attempt == maxAttempts) {
            throw new DownstreamUnavailableException(
                    "Downstream failed after retry", ex);
        }
        // Backoff/jitter per policy; do not log ERROR every time.
    }
}
~~~

Enforce deadline bounds, handle interruption/cancellation, and avoid retrying non-idempotent operations without appropriate business safeguards. If a retry succeeds, the operation can return 200 and only emit a WARN or metric for the fallback/retry.

**An operation is different from an attempt.** Do not use a shared `requestId`/`operationId` as an excuse to suppress signals from distinct requests. If a client retries with a new HTTP request, that may be a separate logical attempt and require its own outcome event per contract.

## 11. Batch Jobs, Async Tasks, and Message Listeners

### 11.1. Multi-Item Batches

A job may process 100 items, with two items failing independently. You can emit a summary log and failure count metric, or one event per item if operations teams need to handle individual records. Do not default to "one job = one error log", as that can erase evidence of independent item failures.

### 11.2. `CompletableFuture` and `ExecutorService`

An exception thrown in a worker thread might be logged in `whenComplete()`, and then caught and logged again at `join()`/`get()`. Choose one **terminal observer** responsible for logging, and propagate correlation context across the thread pool properly. Conversely, if every side assumes "another layer will log it", no event may be recorded at all.

### 11.3. Schedulers and Background Workers

There is no HTTP boundary, so the scheduler/job runner usually handles final error logging. Inner services only wrap the cause, letting the scheduler log one event with `jobId`/`runId`/`status` and retry metadata if the job genuinely fails.

### 11.4. Kafka/JMS/Message Brokers

Messages can be redelivered. If the listener, retry advice, and dead-letter handler all log an ERROR stack trace on every attempt, the collector can easily become saturated during a downstream outage. Assign ownership at the **consumer outcome boundary**. When a message enters the DLQ, emit an outcome event with `messageId` and reason plus retry/deadLetter metrics, without repeating the full stack trace every time.

### 11.5. Timeouts and Task Cancellation

If upstream times out while downstream keeps running, error events in the two systems may be two independent consequences. Use `traceId`/`spanId`, `requestId`, and `operationId` to correlate them before concluding they are duplicates. When catching `InterruptedException`, respect cancellation/interruption by design rather than catching it and silently looping forever.

## 12. Logback Additivity: One Call Can Still Print Twice

Sometimes the code calls `logger.error` only once, yet **the same appender is referenced on both a child logger and ROOT**:

~~~xml
<!-- Fragment illustrating a configuration prone to duplicate CONSOLE output. -->
<logger name="com.example.orders" level="INFO">
  <appender-ref ref="CONSOLE"/>
</logger>
<root level="INFO">
  <appender-ref ref="CONSOLE"/>
</root>
~~~

With default additivity, an event in `com.example.orders` passes through the child logger's appender and then propagates up to `ROOT`. If both reference `CONSOLE`, the event can be emitted twice.

A simple approach is to attach the appender only on `ROOT`:

~~~xml
<configuration>
  <appender name="CONSOLE"
            class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level requestId=%X{requestId:-} %logger - %msg%n%ex{full}</pattern>
    </encoder>
  </appender>

  <logger name="com.example.orders" level="INFO"/>

  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

This is a **`logback.xml`** configuration. It attaches `CONSOLE` only at `ROOT`; child logger events inherit the output path if they meet the level threshold.

An alternative is to attach the appender directly on the child logger and set **`additivity="false"`**, but you must ensure the child logger has a valid appender. Setting `additivity=false` and forgetting an appender can **drop logs**. Never tweak config just to hide duplicates in a way that drops required audit or file channels.

An event intentionally fanned out to both `FILE` and `CONSOLE` is normal. Define "no duplicates" per **same sink and same logical failure**, not "never appear in more than one sink".

## 13. Log4j 2 and Collectors Can Duplicate at Other Layers

Log4j 2 also has `LoggerConfig`/`AppenderRef` and additivity rules. An illustrative **`log4j2.xml`** attaching `CONSOLE` only at `ROOT`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
  <Appenders>
    <Console name="CONSOLE" target="SYSTEM_OUT">
      <PatternLayout
          pattern="%d{ISO8601} %-5p %c - %m%n%throwable"/>
    </Console>
  </Appenders>
  <Loggers>
    <Logger name="com.example.orders" level="info"/>
    <Root level="info">
      <AppenderRef ref="CONSOLE"/>
    </Root>
  </Loggers>
</Configuration>
~~~

Do not copy classes or elements between Logback and Log4j 2; verify the XML against the backend actually loaded. If there are additional `AppenderRef` entries on child or parent loggers, check both `additivity` and filters to see how many times an event is emitted.

Outside the JVM, a **log shipper/collector** can cause duplicates if it:

- reads both stdout and a file that already contains a copy of it;
- forwards through two pipelines into the same index;
- uses at-least-once retry and resends the same record after a lost ACK;
- is configured to ingest multiple times or replays from an archive.

If the local sink has one event but the dashboard shows two, investigate the **ingestion pipeline** instead of changing service code. With `eventId`/`correlationId`, you can separate retry duplicates from genuine failures.

Do not use a message-based filter like "same error type within 60 seconds" as a default fix: two independent requests with the same `SQLException` text still need to be counted accurately.

## 14. Put Enough Information in One Final Event

A useful terminal ERROR event typically needs:

- **`eventCode`/`errorCode`:** a stable code (`ORDER_FAILED`, `DEPENDENCY_TIMEOUT`) rather than just `Exception.toString()`.
- **`requestId`/`traceId`:** correlates logs across layers/services, with appropriate query permissions.
- **`operation`/`job`/`message ID`:** identifies the logical failure and distinguishes independent tasks.
- **`outcome`:** `FAILED`, `DEGRADED`, `RECOVERED` depending on the final result.
- **`attempt count`** if retries occurred.
- **`exception` and cause chain:** enough to find the root cause, while protecting sensitive data.
- **`service`/`environment`/`component`:** identifies where the error originated and which layer logged it.

Illustrative JSON example:

~~~json
{
  "level": "ERROR",
  "service": "order-service",
  "requestId": "req-42",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "operation": "CREATE_ORDER",
  "errorCode": "ORDER_FAILED",
  "outcome": "FAILED",
  "attempts": 3,
  "exceptionType": "OrderCreationException",
  "rootCauseType": "SQLException"
}
~~~

This is an example structure, not a real log record. In production, use a JSON/structured logging encoder instead of manually concatenating JSON from input data. Do not add emails, tokens, passwords, card numbers, cookies, or raw SQL parameters to "add context".

A `requestId` is a reference identifier, **not a log access token**. Do not put `requestId` into unbounded metric labels due to high cardinality. To the client, return only `errorCode`, `requestId`, and a safe message; never expose the raw stack trace.

## 15. Replace Multiple ERRORs with Purpose-Built Metrics and Tracing

Reducing duplicate stack traces does not mean losing error observability. Each signal has its own purpose:

| Signal | Value |
| --- | --- |
| One terminal ERROR | Root cause details and failure context |
| WARN for fallback | Indicates degraded but recovered behavior |
| DEBUG for attempts | Step-by-step investigation when enabled under control |
| `errors_total` metric | Counts failures by definition and `errorCode` |
| `retries_total` metric | Counts retries without multiplying stack traces |
| Tracing spans | Shows downstream errors and timing across hops |
| Audit/security event | Business/security evidence under an independent policy |

For example, when a provider times out 3 times and the request fails: `retries_total` may increment by 3, `errors_total` increments by 1, and one ERROR event has `attempts=3`. If it recovers on attempt 2, `retries_total` increments, while `errors_total` may not increment under a terminal-failure definition.

Metrics must be clearly defined and must not be derived purely by counting ERROR log lines. Multiline stack traces, Logback additivity, or collector retries will all skew counts based on raw text lines.

## 16. Testing "Log Exactly Once"

Do not use `grep` to count physical lines. With JUL, the test `Handler` in the example recording into `List<LogRecord>` demonstrates the pattern. In Logback you can use a test appender/`ILoggingEvent`; in Log4j 2 there is a corresponding test appender. With async backends, wait for drain/flush properly before asserting.

Suggested test matrix:

| Test case | Expected result |
| --- | --- |
| Repository fails, service wraps, boundary returns 500 | One ERROR at boundary, with full cause |
| Repository succeeds | No ERROR |
| Service recovery succeeds | No terminal ERROR; metric/WARN if needed |
| Retries twice then succeeds | No two ERROR stack traces; retry metric increments |
| Retries exhausted then fails | One terminal ERROR with attempts and cause |
| Validation 400 | No default ERROR stack trace |
| Two independent requests with the same error | Two terminal failures with different `requestId`s |
| Async callback then caller catches | Not logged at both terminal points |
| Single logger call with double additivity | Distinguish code events from appender duplicates |
| One local log, two central logs | Investigate forwarding/ingest |
| Throwable with suppressed exceptions | Cause and suppressed preserved where needed |
| Security/audit | Not accidentally dropped by log-once policy |

Also verify that sensitive exception messages do not appear in logs or HTTP responses. If ERROR logs are intentionally sent to multiple appenders, test at the **logging event layer** and verify each sink individually.

Do not create a global `Set<Throwable>` or `Set<String>` of "already logged" errors to suppress all errors with the same message. That can hide new failures, cause memory leaks, and corrupt metrics. **Designing ownership at the boundary** is the sustainable solution.

## 17. Diagnosing Duplicates in Production

When you see multiple identical ERRORs in a dashboard:

1. **Group by `requestId`, `traceId`, `jobId`/`messageId`:** do the logs belong to the same logical failure?
2. **Check call-site / logger name:** did repository, service, controller, and advice all log the same throwable?
3. **Inspect `Throwable` cause:** are multiple events sharing the same chain or are they independent exceptions?
4. **Check appenders and additivity:** is one event being emitted twice to the same local sink?
5. **Check fan-out:** is emitting the same event to `FILE` and `CONSOLE` intentional?
6. **Compare local vs. central:** if local has one event and central has two, check the shipper, retry logic, and collector.
7. **Review retry policy:** is ERROR being logged on each attempt before the boundary logs again?
8. **Assign one owner and fix the code:** remove unnecessary catch-log-rethrow, preserve cause and context.
9. **Retest:** verify `errors_total`, retry metrics, tracing, and audit logs do not lose data.
10. **Monitor after the change:** log volume drops while real logical failures remain visible.

A duplicate error can have **multiple causes at once**, such as code logging twice and the collector retrying each event. Before changing filter configs, identify which layer is introducing the duplication.

## 18. Common Mistakes

**Catch–log–throw at every layer.** Each layer wants to "not miss anything" and emits an ERROR, then the upper layer emits an ERROR too. Choose a terminal owner and preserve the cause.

**`printStackTrace()` plus `logger.error(..., ex)`.** Two output paths create duplicates and can bypass MDC/formatting. Use the logging framework consistently.

**Wrapping an exception without passing the cause.** Drops the root cause, tempting developers to log in lower layers to compensate. Pass the cause into the new exception's constructor.

**Treating every 400/404 as an ERROR stack trace.** Expected input errors usually belong in HTTP status codes and access logs/metrics, not stack traces signaling system incidents.

**Logging every retry as an independent ERROR.** During prolonged downstream outages, logs flood. Track attempts with metrics/traces; decide terminal errors based on the final outcome.

**Deduplicating solely by exception class/message.** Many real requests can share the same root cause. Global suppression distorts error rates and hides incident severity.

**Using `log.error("{}", ex)` carelessly.** Depending on parameterized logging and backends, the exception may be treated as an argument instead of a `Throwable`. Use the explicit `log.error("Operation failed", ex)` overload or fluent `.setCause(ex)` and verify the output.

**Setting `additivity=false` without attaching an appender.** Can cause the logger to output nothing. Routing changes must be tested to verify the intended destination receives events.

**Assuming one log call with multiline stack trace = duplicate.** Incorrect; count events, not lines.

**Disabling audit logs to reduce duplicates.** Audit logs have their own purpose and may be required even when an ERROR is already logged. Do not alter security policies in ways that hide outcomes.

## 19. Pre-Production Checklist

- [ ] Each operation has a designated owner for terminal ERRORs.
- [ ] Catch blocks that only wrap/rethrow do not log duplicate ERRORs.
- [ ] Exception wrappers preserve cause and suppressed information where appropriate.
- [ ] Error handlers do not log again if another component is already the designated owner.
- [ ] Expected errors such as validation are handled at the appropriate level, without defaulting to full stack traces.
- [ ] Retry attempts use metrics/traces/DEBUG appropriately instead of spamming stack traces.
- [ ] Async tasks, schedulers, and message consumers have clear error-handling boundaries.
- [ ] Logback/Log4j 2 configurations do not unintentionally reference the same appender at multiple levels.
- [ ] Collector forwarding/retry is checked if the dashboard shows duplicates.
- [ ] Terminal events include `requestId`/`traceId`, `errorCode`, `outcome`, and `Throwable`.
- [ ] Secrets, PII, raw request bodies, and stack traces are never exposed to clients.
- [ ] Tests count logging events, not text lines.
- [ ] Tests verify two independent failures are both counted.
- [ ] Error/retry metrics and security audit logs are not accidentally suppressed.
- [ ] Tests are run after changes to routing and retry configuration.

**Conclusion:** To **avoid logging the same error multiple times**, designate the layer responsible for the final outcome, have intermediate layers **preserve the cause and rethrow instead of logging and throwing**, emit one well-structured event at the boundary, and use metrics/tracing for attempts. Also check Logback/Log4j 2 additivity and the collector pipeline, because a single event can still be duplicated even when the code calls the logger only once.

## 20. References

- [Oracle Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): cause chain, stack trace, and suppressed exceptions.
- [Oracle Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): `log(Level, String, Throwable)` and `Handler`.
- [SLF4J FAQ](https://www.slf4j.org/faq.html): logging exceptions with `Throwable`.
- [SLF4J Manual](https://www.slf4j.org/manual.html): parameterized and fluent API.
- [SLF4J LoggingEventBuilder](https://www.slf4j.org/apidocs/org/slf4j/spi/LoggingEventBuilder.html): `setCause` and `addKeyValue`.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html): logger hierarchy, appenders, and additivity.
- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html): throwable and MDC output.
- [Apache Log4j 2 — Architecture](https://logging.apache.org/log4j/2.x/manual/architecture.html): `LoggerConfig` and appender propagation.
- [Apache Log4j 2 — Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html): throwable rendering.
- [Spring Framework — @ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): exception handling in MVC.
- [Spring Framework — @ControllerAdvice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html): shared exception handling across controllers.
