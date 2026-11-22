# Request Information on Errors in Java Logging

When an HTTP request fails, logging only `NullPointerException`, `Bad request`, or `Payment failed` is usually not enough for investigation. The person troubleshooting the incident also needs to know **which request failed, which feature it went through, what status it returned, how long it took, and which other logs it correlates with**. This set of information is called the **request context**.

In the **Exception logging** section of Java Core Logging, the goal of logging request context is to trace from an error back to the exact execution, determine its impact, connect events across components, and correlate with the HTTP response. **Request context does not mean logging the entire request.** Logs need to be sufficient for diagnosis while excluding secrets, unnecessary personal data, and untrusted input values.

## 1. Why Do Exceptions Need Request Context?

Suppose the application logs:

```text
ERROR java.lang.IllegalStateException: Cannot reserve inventory
```

The message indicates that an exception occurred, but it does not answer which request caused the error, which endpoint was affected, whether it was an internal error or a data error, or which earlier logs to look for.

An event with added context is much more useful:

```text
2026-11-09T10:15:30.125Z ERROR event=http_request_failed requestId=req-81 traceId=trace-27 method=POST route=/orders/{id}/reserve status=500 errorCode=INVENTORY_RESERVE_FAILED durationMs=128
java.lang.IllegalStateException: Cannot reserve inventory
    at com.example.orders.InventoryService.reserve(InventoryService.java:...)
    ...
```

This is an **illustrative log**, not the output of the program below. The ellipsis `...` represents stack frames that depend on the actual source code.

Thanks to `requestId=req-81`, an investigator can group logs belonging to the same request. `method=POST` and `route=/orders/{id}/reserve` clearly indicate the operation type without exposing the literal URL. `status=500` shows the outcome recorded by the application. `errorCode` is a stable classification code; `durationMs` helps detect slowness or timeouts. The stack trace is still needed to see the call flow and technical cause.

Key distinctions:

- **Exception** explains where the technical error occurred and its immediate cause.
- **Request context** tells you which operation the error occurred in and which execution it belongs to.
- **HTTP response** shows how the application responded to the caller; the response status and internal details do not necessarily match.
- **Traces/metrics** can supplement cross-service flow and impact level, especially when multiple requests fail concurrently.

## 2. Fields to Consider Logging When a Request Fails

| Field | Meaning | Safe Example / Note |
| --- | --- | --- |
| `timestamp` | Event timestamp, preferably with an explicit timezone | `2026-11-09T10:15:30.125Z` |
| `level` | Severity level per system policy | `WARN`, `ERROR`; JUL: `WARNING`, `SEVERE` |
| `event` | Stable event name for searching | `http_request_failed` |
| `requestId` | Identifier to group logs within a single execution | `req-81` |
| `traceId`, `spanId` | Link to distributed tracing if implemented | Values generated/controlled by the tracing system |
| `method` | HTTP method | `GET`, `POST`, `PUT`, `DELETE` |
| `route` / `endpoint` | Route template identifying the feature | `/orders/{id}` instead of a URI with IDs and sensitive queries |
| `status` | Determined or recorded HTTP status | `400`, `404`, `500`, `503` |
| `errorCode` | Stable error code suitable for aggregation and statistics | `INVALID_QUANTITY`, `UPSTREAM_TIMEOUT` |
| `durationMs` | Processing duration, used to evaluate slowness/timeouts | `128`; measured with a monotonic clock |
| `exceptionType` and `cause` | Exception type and technical cause | `IllegalArgumentException` along with `Throwable` |
| `service`, `component` | Service or component emitting the event | `order-service`, `OrderController` |
| `dependency`, `attempt` | Downstream dependency or retry step causing failure, if relevant | `inventory-api`, `attempt=2` |

**Not every event is required to have every field.** Log the fields needed to investigate the type of error at hand, keeping field names and data types consistent across components. For example, an error without an HTTP request (background job, message consumer) should use `jobId`, `messageId`, or `runId` instead of fabricating `method=GET`.

### How Do Request ID and Trace ID Differ?

`requestId` is typically used to connect all logs belonging to one request within a service or across a chain of services if propagated. A system can choose its own way to issue IDs; **there is no mandatory standard** requiring every application to name or generate IDs with the same algorithm.

`traceId` typically identifies an entire distributed trace; `spanId` identifies a single step within that trace. They are useful when a request passes through a gateway, service A, service B, and a database. **A request ID does not automatically create a distributed trace**; linking them requires creating/propagating context and configuring appropriate instrumentation.

If accepting an ID from a client-provided header, you need a clear policy on trust level, format, length, and write permissions. A common approach is for the application or gateway to validate the received ID or generate a trusted ID itself. Do not treat an arbitrary user-supplied string as if it were already an internal correlation ID.

## 3. Logging the Right Path and Request Content Without Leaking Data

When an exception occurs, developers often want to log `request.getRequestURI()`, `request.getQueryString()`, all headers, or the body. Doing so can put sensitive data into logs.

**Prefer the route template** determined by the router/framework:

```text
method=GET route=/users/{userId}/orders
```

**Avoid logging the literal URL**, such as:

```text
GET /users/987654/orders?access_token=secret&email=someone@example.test
```

The actual URL may contain user IDs, emails, tokens, or private search queries. Even path parameters can be sensitive. If storing an identifier is strictly required for investigation, choose an approved type, apply intentional masking/hashing, and clearly define retention periods and access controls.

For HTTP headers, only log values that have been reviewed and allowed. **Do not log verbatim** `Authorization`, `Cookie`, `Set-Cookie`, API keys, session tokens, client certificates, passwords, or payment details. `User-Agent`, `Referer`, and `X-Forwarded-For` can also be long, untrusted, or contain private information; log them only with a clear purpose and safe handling.

**Client IP:** `remoteAddr` may be the reverse proxy's address, while `X-Forwarded-For` can be spoofed by the client if the proxy has not established a trust boundary. If IP addresses are needed for investigation, you must properly identify the trusted proxy chain and comply with personal data retention policies. Do not infer "who caused the error" from an IP address alone.

**Request body:** may contain large JSON payloads, images, passwords, keys, payment cards, and sensitive business data. Do not dump the entire body into exception logs by default. Usually you only need `errorCode`, the operation name, record count, approved internal IDs, and a few validated fields.

## 4. Connecting Request Context with Exceptions at the Right Boundary

A common structure for an HTTP application:

```text
HTTP request
   |
   v
Middleware / Filter: receive or generate requestId, open context, record start time
   |
   v
Router / Controller: resolve route template and invoke business logic
   |
   v
Service -> Repository / HTTP client / dependency
   |
   +-- Exception is thrown up to the error-handling boundary
   v
Exception handler: classify error, determine HTTP status and errorCode
   |
   v
Log a failure event with request context + Throwable
   |
   v
HTTP response and close/clean up context
```

The diagram only illustrates **logical responsibilities**, not a fixed filter/controller class imposed on every framework. A real application may classify exceptions in a global exception handler, middleware, interceptor, or another error boundary; what matters is having **one primary place responsible** for logging errors per request.

If the repository layer logs the full exception and rethrows it, the service logs it again, and the controller logs it a third time, a single failure can produce multiple duplicate stack traces. Useful conventions include:

- Lower-level components can add context to the exception while **preserving the cause**.
- The boundary that has full request context and the HTTP outcome logs the exception at the appropriate level.
- Intermediate retries can concisely log `attempt`, `dependency`, and `outcome`; only treat the operation as a final failure when the retry policy is exhausted.
- If a framework already logs errors with complete data, check it before adding duplicate logging in application code.

The logged status must reflect the **actual handled outcome**: an input error classified as `400` should not automatically be logged at the same severity as an unexpected `500`. If the connection drops before the response is sent, the `status` field in the log may only be the **intended status**, which should be noted clearly or represented using an appropriate `responseCommitted`/`outcome` field.

## 5. Classifying Errors and Choosing Log Levels for Failed Requests

| Scenario | Typical HTTP Status | Log Level to Consider | Notes |
| --- | --- | --- | --- |
| Invalid client payload | `400`, `422` depending on API | `INFO`/`WARN`; JUL `INFO`/`WARNING` | Usually an expected scenario; avoid verbose stack traces if they do not aid investigation |
| Resource not found | `404` | `INFO` or `WARN` depending on context | Not every `404` is a server error |
| Unauthenticated / unauthorized | `401`, `403` | Dedicated security policy | Do not log credentials or tokens; limit exposure of access details |
| Rate limited | `429` | `INFO`/`WARN` depending on design | Log reason code and rate-limit policy at an allowed level |
| Transient dependency failure | `502`, `503`, `504` if used by API | `WARN` or `ERROR` based on impact | Include dependency, timeout, retries, and final outcome |
| Unexpected exception | `500` | `ERROR`; JUL `SEVERE` | Keep stack trace and correlation ID; keep client response generic |

This table is only a **guideline**: HTTP codes, log levels, and whether to include a stack trace depend on the API contract, severity, recoverability, and operational policy. For example, `IllegalArgumentException` might represent invalid input at a validation boundary, or it might be an internal programming bug. **Do not map every exception solely by its class name.**

Client response messages should be designed separately from internal log messages: the client might receive `{"errorCode":"INVALID_QUANTITY","requestId":"req-81"}`, while the log retains the exception and technical context. Do not return stack traces or internal file paths in public HTTP responses.

## 6. Standalone Java 17 Example: Logging Errors with Request Context

The program below runs on **JDK 17+**, using `java.util.logging` with no external dependencies. To avoid depending on a server or framework, it **simulates** an HTTP request using a `RequestContext` record; in a real application, `requestId`, `method`, and `route` are obtained from middleware/router after safety validation.

A request with an invalid quantity returns `400` while logging `requestId`, `method`, `route`, `status`, `errorCode`, and the `Throwable`. A valid request returns `200` and is not mistakenly logged as an error.

Save the file as **`RequestErrorContextDemo.java`**:

```java
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RequestErrorContextDemo {
    private static final Logger LOGGER =
            Logger.getLogger(RequestErrorContextDemo.class.getName());

    private record RequestContext(
            String requestId, String method, String route) {
    }

    private static ConsoleHandler configureLogging() {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                StringBuilder text = new StringBuilder()
                        .append(record.getLevel().getName())
                        .append(" | ")
                        .append(formatMessage(record))
                        .append(System.lineSeparator());

                if (record.getThrown() != null) {
                    StringWriter buffer = new StringWriter();
                    record.getThrown().printStackTrace(
                            new PrintWriter(buffer));
                    text.append(buffer);
                }
                return text.toString();
            }
        });

        LOGGER.addHandler(console);
        return console;
    }

    private static int handle(RequestContext request, int quantity) {
        try {
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            return 200;
        } catch (IllegalArgumentException error) {
            String message =
                    "event=http_request_failed"
                    + " requestId=" + request.requestId()
                    + " method=" + request.method()
                    + " route=" + request.route()
                    + " status=400"
                    + " errorCode=INVALID_QUANTITY";

            LOGGER.log(Level.WARNING, message, error);
            return 400;
        }
    }

    public static void main(String[] args) {
        ConsoleHandler console = configureLogging();
        try {
            RequestContext request =
                    new RequestContext("req-81", "POST", "/orders/{id}");

            System.out.println("invalidStatus=" + handle(request, -2));
            System.out.println("validStatus=" + handle(request, 3));
        } finally {
            LOGGER.removeHandler(console);
            console.close();
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 RequestErrorContextDemo.java
java RequestErrorContextDemo
```

**Exact stdout:**

```text
invalidStatus=400
validStatus=200
```

**Stderr** has the following exact opening line; the subsequent stack trace lines contain source line numbers and are illustrative only:

```text
WARNING | event=http_request_failed requestId=req-81 method=POST route=/orders/{id} status=400 errorCode=INVALID_QUANTITY
java.lang.IllegalArgumentException: quantity must be positive
    at RequestErrorContextDemo.handle(RequestErrorContextDemo.java:...)
    at RequestErrorContextDemo.main(RequestErrorContextDemo.java:...)
```

JUL's `ConsoleHandler` writes to **stderr**; if a terminal merges stdout and stderr, the interleaving order between the two streams is not strictly guaranteed. In `handle`, the exception is passed directly via `LOGGER.log(Level.WARNING, message, error)`, so the log record retains the `Throwable` object. The demo's formatter calls `printStackTrace` on the throwable to display error evidence. Here, `printStackTrace` writes into a **buffer managed by the formatter**, rather than being called directly from business code as a replacement for logging.

**Intentional choices in the demo:**

1. `RequestContext` is simulated data known to be safe. When integrating real HTTP, never concatenate untrusted input directly into the message.
2. `route=/orders/{id}` is a **route template**; there are no customer IDs, query strings, or tokens in the log.
3. `errorCode=INVALID_QUANTITY` is an application-defined error code, not a string taken from the client.
4. `status=400` is the outcome that `handle` actually returns; the example does not simulate cases where the response was already committed or the socket disconnected.
5. `LOGGER.setUseParentHandlers(false)` avoids extra lines from parent handlers so the output is easy to verify. In a real system, only change propagation after understanding the overall logging configuration.
6. Both the logger and handler in the example are set to `INFO`; the `WARNING` event is accepted. `ConsoleHandler` is removed and closed when the demo finishes.

This program demonstrates the **exception + request context** mechanism, not an HTTP server. In a real server, processing duration, the actual response status sent, and route information must come from the framework's pipeline rather than being inferred from the exception type.

## 7. Measuring Duration Without Confusing Processing Times

Duration is a useful signal when investigating timeouts or performance issues. In Java, to measure elapsed time within the same process, `System.nanoTime()` is commonly used:

```java
// Illustrative fragment within a single request-handling call.
long started = System.nanoTime();
try {
    processRequest();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    long durationMs =
            java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
    // Include durationMs in the request summary event.
}
```

This snippet requires the application's `processRequest()` method and does not run standalone. `System.nanoTime()` is suitable for computing **elapsed intervals**, not for use as a timestamp or for absolute comparisons across different processes or machines. Timestamps should come from a wall-clock with a timezone (typically UTC), while duration should come from a monotonic clock.

Do not log `durationMs=0` as a placeholder value when the system has not measured the time. If a request is still running or was cancelled, distinguish that state from a completed request; timings measured at the gateway, servlet filter, and downstream services will differ because each layer has its own scope.

## 8. Automatically Attaching Request IDs via Logging Context

With plain JUL, an easy-to-learn approach is to **pass context data explicitly**, as with the `RequestContext` record in the example. The default JUL logger does not provide an MDC like SLF4J does. Real-world frameworks typically have their own request scope, tracing, and context propagation mechanisms.

In projects using **SLF4J with a backend that supports MDC**, you can put a trusted ID into the MDC for the duration of request processing:

```java
// Fragment in a project with SLF4J; requestId and processRequest() already exist.
org.slf4j.MDC.put("requestId", requestId);
try {
    processRequest();
} finally {
    org.slf4j.MDC.remove("requestId");
}
```

This snippet requires the appropriate SLF4J API/provider and is not a pure-JDK program. For `requestId` to actually appear in the logs, **the backend's encoder/layout must be configured to read the MDC field**; calling `MDC.put` alone does not guarantee that printed messages include the ID.

Sample snippet in a Logback configuration file, when the application already uses Logback:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level requestId=%X{requestId} %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

This is a **Logback configuration**, not meant for JUL or Log4j 2 as-is. In practice, you also need to decide on the timezone, how exceptions are rendered, JSON formatting if required by a log collector, and how to integrate with the framework's logging configuration.

### Why Must MDC Be Cleaned Up and Propagated Across Async Threads?

Thread pools reuse threads. If you attach `requestId` to a thread's MDC without calling `remove` or `clear` in a `finally` block, a subsequent request can be mistakenly tagged with the old ID. Similarly, submitting a task to an executor, calling `CompletableFuture`, or switching to another thread/reactive context **does not automatically guarantee** that MDC is propagated and cleaned up properly. You must use context propagation mechanisms supported by your framework or observability stack.

For a request spanning multiple services, you can pass a correlation ID via a standardized and validated HTTP header; distributed tracing uses its own propagation mechanism such as Trace Context when adopted by the system. Do not treat incoming header values as ground truth unless a trust boundary has been established.

## 9. Logging Exceptions in Structured Format

A structured event separates the free-form message from searchable fields. Illustrative JSON example:

```json
{
  "timestamp": "2026-11-09T10:15:30.125Z",
  "level": "ERROR",
  "event": "http_request_failed",
  "service": "order-service",
  "requestId": "req-81",
  "traceId": "trace-27",
  "method": "POST",
  "route": "/orders/{id}/reserve",
  "status": 500,
  "errorCode": "INVENTORY_RESERVE_FAILED",
  "durationMs": 128,
  "exceptionType": "java.lang.IllegalStateException",
  "message": "Cannot reserve inventory"
}
```

This is **hypothetical data for learning structure**, not output from `RequestErrorContextDemo`. Production systems may need a `stackTrace` field or the backend's standard error field to preserve full evidence. For line-based log collectors, the encoder can emit **one JSON object per line**, escaping newlines inside stack traces rather than multi-line pretty-printing; the exact syntax depends on the backend and its version.

The benefit of structured logging is being able to query `requestId`, `errorCode`, `status`, and `route` without parsing structure out of a prose sentence. Do not **hand-assemble JSON by concatenating strings** containing user input: use an official serializer/encoder, place untrusted values into data fields, and handle control characters properly.

Structured logging also does not automatically guarantee durable logs or prevent data leaks. You still need access controls, retention policies, size limits, sensitive-data handling, and verification of collection at the final destination.

## 10. Concrete Investigation Scenarios

### Scenario A: `400` Input Error

Log:

```text
WARNING event=http_request_failed requestId=req-81 method=POST route=/orders/{id} status=400 errorCode=INVALID_QUANTITY
```

Evidence shows the request was rejected according to an input validation rule. If this is an expected and frequent scenario, the application may not need to print a stack trace for every rejection. An investigator can filter `errorCode=INVALID_QUANTITY` by route to see which rule failed and whether there is an unusual spike. You do not need to log the entire payload to know that the quantity was invalid.

### Scenario B: Dependency Failure After Retries

```text
WARN requestId=req-82 dependency=inventory-api attempt=1 outcome=retry reason=timeout
WARN requestId=req-82 dependency=inventory-api attempt=2 outcome=retry reason=timeout
ERROR event=http_request_failed requestId=req-82 route=/orders/{id}/reserve status=503 errorCode=UPSTREAM_TIMEOUT attempts=3
```

This is an **illustrative log**. The first two lines are non-terminal attempts; the last line shows the request finally failing under the retry policy. During investigation, you should correlate logs with the same `requestId` and inspect timestamps, timeout impact, and the dependent service. Do not count these three lines as three independent failed requests.

### Scenario C: Unexpected `500` Exception

```text
ERROR event=http_request_failed requestId=req-83 method=GET route=/reports/{id} status=500 errorCode=UNEXPECTED_ERROR
java.lang.NullPointerException: ...
```

The full stack trace/cause must be logged to find the actual bug; `requestId` lets you inspect earlier logs for the same request. The client response should include a generic error code and reference ID, without returning stack trace details. Do not conclude the root cause merely from seeing `NullPointerException`; you must identify which object was null and why the precondition was violated.

## 11. Design Pitfalls When Logging Requests on Exceptions

| Mistake | Consequence | Improvement |
| --- | --- | --- |
| Logging only `exception.getMessage()` | Unknown request and lost stack trace/cause | Log `errorCode`, `requestId`, `route`, `status`, and `Throwable` at the appropriate boundary |
| Logging full URLs with query strings | Can leak tokens, emails, search queries | Prefer route templates, mask sensitive fields |
| Logging all headers/body | Leaks credentials, personal data, large payloads | Select only truly needed fields via an allowlist |
| Trusting `X-Forwarded-For` or client correlation IDs directly | Spoofed origin/identity, log injection | Validate/normalize through a trusted gateway |
| Logging the same exception in repository, service, and controller | Duplicate stack traces, hard to count real errors | Standardize on one full log point at the request boundary |
| `requestId` only on the error line, missing from earlier steps | Cannot trace request progression | Propagate and log the ID across key events |
| Forgetting to clean MDC when using thread pools | New requests carry stale context from old requests | Use `finally` and proper context propagation |
| Logging `status=200` before knowing the real outcome | Logs contradict the response | Log the actual status or distinguish intended status |
| Treating every `4xx` as a critical system error | Alert noise, drowning out actionable `5xx` errors | Choose levels based on impact and error classification |
| Logging raw input containing CR/LF | Can forge log lines or break parsers | Escape, enforce length limits, and use a structured encoder |
| Using `System.out.println` / `printStackTrace()` instead of logging exceptions | Loses level, category, correlation, and storage configuration | Use a logging API with `Throwable` |
| Logging too much data on exceptions | Increases latency, storage volume, and data-leak risk | Use error codes and minimal metadata sufficient for investigation |

**Log security:** Data from requests is untrusted input. Besides filtering secrets, you must handle control characters and enforce length limits to prevent log forging, parser breakage, or excessive overhead. Do not assume every `toString()` on a request object is safe; some implementations may include sensitive fields.

## 12. Implementation Checklist

When designing exception logging for HTTP requests, verify the following:

1. **Identification:** the request has a trusted `requestId`; `traceId`/`spanId` if the project uses tracing; events for the same request are linked.
2. **Accurate operation:** includes `method`, route template, and handling component; avoids full URLs/sensitive queries.
3. **Accurate outcome:** includes a stable `errorCode`, the decided/recorded HTTP status, outcome, and duration if measured.
4. **Accurate technical error:** preserves `Throwable`, stack trace, and `Caused by` chain for diagnosable errors; avoids pointless duplicate logs.
5. **Appropriate severity:** expected input errors and system errors are not lumped together; logging policy fits request volume.
6. **Data safety:** headers, body, IP, path parameters, and user info are evaluated before logging; no tokens or passwords are exposed.
7. **Context safety:** request context is properly propagated across async/executors and cleaned up after handling; no ID bleed between requests.
8. **Operability:** formatter/encoder keeps field names consistent; the log collector can locate the exact request and exception.
9. **Verification:** test a successful request, a `4xx` error, a `5xx` error, and a retry/timeout scenario; cross-check logs against responses.
10. **Resources:** size limits, retention periods, and access controls match the sensitivity of the permitted log data.

**Target outcome:** From a single exception event, an investigator can determine **which request failed, what operation it was performing, in which component, what result it returned, and where to find related traces**. Selective request context makes investigations faster and more accurate while avoiding turning the logging system into a store of sensitive HTTP data.
