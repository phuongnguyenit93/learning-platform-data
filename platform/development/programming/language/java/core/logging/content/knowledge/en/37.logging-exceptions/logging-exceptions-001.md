# Logging at the Boundary: Recording Exceptions Where Responsibility Lies in Java

## 1. What does "logging at the boundary" mean?

In **Java Core Logging and exception handling**, a *boundary* is the point where a component **takes final responsibility for the outcome of an operation**: returning an HTTP response, completing a job, deciding to ACK/retry/dead-letter a message, ending a CLI command, or handing off an error to an external system.

A useful principle is: **log the exception at the boundary that has enough context to decide how to handle it**, rather than having every intermediate layer catch the error, log a stack trace, and rethrow it. The log entry here should describe **which operation failed, the final outcome, a stable error code, the correlation ID, and the necessary exception/cause**, rather than just saying "An error occurred".

A typical flow:

```text
HTTP request
    |
    v
Controller ----------- receives request / delegates processing
    |
    v
Service -------------- applies business logic, may translate exceptions
    |
    v
Repository ----------- calls DB / downstream, may throw IOException
    |
    +-> error propagates up, preserving cause
    |
    v
HTTP exception boundary
    +-> decides HTTP status and public response
    +-> logs one failure event with request ID, error code, throwable
    +-> returns sanitized response to client
```

For example, if the repository loses its connection, having three layers all call `logger.error("Failed", ex)` and rethrow produces multiple nearly identical stack traces. One well-informed exception log at the request boundary is usually far more useful than three duplicate records that can inflate error counts on dashboards.

**This is not a rule that says "there can only be one log in the entire system"**: the gateway, service A, and service B can each record separate events for actions *at their own boundaries*, such as retries exhausted in A and HTTP 502 at the gateway. However, within **a single processing flow of the same component**, avoid logging the same throwable multiple times just because it passes through multiple `catch` blocks.

### How do boundaries differ from intermediate layers?

| Location | Responsibility | Logging decision |
| --- | --- | --- |
| Repository/DAO | Access DB, filesystem, network | Usually throws the exception for the caller to decide; do not log full stack and rethrow |
| Domain/service | Apply business rules, translate errors, add context | Wrap exception with cause if needed; log only if actually **handling/recovering** or recording an independent business event |
| HTTP/controller boundary | Finalize request status, response, error code | Log at the appropriate level based on final outcome and request context |
| Scheduled/background job boundary | Finalize job success/failure, next retry/schedule | Log once after determining the outcome; avoid letting exceptions silently disappear in a Future |
| Message consumer boundary | Finalize ACK, retry, requeue, or dead-letter | Log the terminal decision; avoid logging ERROR on every attempt during normal retries |
| Application entry point | Finalize exit code/resource cleanup | Log fatal/unhandled when no higher boundary exists |
| Framework/server | May automatically log unhandled errors | Review default logging to avoid duplicates from both framework and application |

A boundary **is not necessarily the topmost method on the call stack**. It is the place where an operation is concluded, converted into a status, or handed off under a clear contract. A service can act as the boundary for a subsystem if it handles the error itself, returns a fallback, and does not propagate the exception further.

## 2. Distinguishing actions when catching exceptions

A `catch` block can do several different things; the choice of whether to log must follow **the handling intent**, not the notion that "there is a `catch` block so we must log".

| Situation | Primary approach | Where to log the full exception? |
| --- | --- | --- |
| Only aware of the error, no authority to handle it | Let the exception propagate or wrap preserving the cause | At the final handling boundary |
| Converting infrastructure errors into domain errors | Throw a new exception with the original cause | At the boundary deciding the outcome; avoid logging at each translation |
| Fully recovered via a valid fallback | Return fallback; event has a recovered outcome | May log WARN/INFO at the recovery point if valuable; do not report the whole operation as failed if it succeeded |
| Retried and exhausted attempts | Finalize as failed/timeout/dead-letter | Log one complete terminal event; individual attempts can be tracked via metrics |
| Expected invalid input | Return 400 or a valid domain error | Usually no full ERROR stack needed; use error codes, counts, security policy |
| Unexpected error at API | Return safe response, emit error signal | Boundary logs ERROR with a controlled throwable |
| Independent audit required | Emit structured audit event per policy | Audit does not replace exception logs; may need a separate durable pipeline |

An intermediate layer may have information that the boundary does not know, but **it does not need to log in order to add information**. It can wrap the appropriate exception type with a sanitized message and the original cause, or pass structured context up along with the operation.

### Pattern to avoid: logging and rethrowing at every layer

```java
try {
    repository.save(entity);
} catch (SQLException ex) {
    logger.error("Save failed", ex);
    throw ex;
}
```

This is an illustrative snippet; it requires appropriate `repository`, `entity`, logger, and exception types. If the final caller also logs the stack trace, logging in the repository creates a duplicate without adding any handling decision. Worse, if the error occurs thousands of times when the system is overloaded, each layer can multiply ERROR logs by three or four, drowning out other signals and wasting resources.

In cases where the caller needs to distinguish domain errors:

```java
try {
    repository.save(entity);
} catch (SQLException ex) {
    throw new PersistenceUnavailableException(
            "Cannot complete persistence operation", ex);
}
```

This is a **non-standalone illustrative snippet**; `PersistenceUnavailableException` is a custom application exception. Having the constructor accept `ex` as the cause is crucial. If you create `new PersistenceUnavailableException("...")` and **omit the cause**, the stack trace at the boundary will make it hard to tell why the DB call failed. When internal correlation is needed, you can include a non-sensitive operation code or resource ID, but do not put SQL containing secrets or request bodies into the message.

A `catch` block that only does `throw ex;` usually does not need to exist if it performs no cleanup, translation, or control flow. For cleanup, prefer `try-with-resources` or an appropriate `finally` block.

## 3. Understanding the "log once" rule properly

A common guideline is **"log an exception once, at the point it is handled"**. This is a **design rule**, not a property automatically enforced by Java.

- **Same exception, same operation:** do not print the same stack trace in the repository, service, controller, and filter just because the exception passes through them.
- **Multiple separate operations:** if service B returns an error to service A, B can log the failure of the request to B; after exhausting retries, A can log the failure of **operation A**. These events have different `service.name`, `event.name`, request/trace IDs, and responsibilities.
- **Recovery occurs:** if a downstream call times out and a cache fallback succeeds, do not report the entire HTTP request as failed just because an intermediate exception occurred. Log "fallback used" if needed and measure the degraded-service rate.
- **Frameworks also have boundaries:** Servlet containers, Spring MVC exception resolvers, schedulers, or messaging frameworks may log uncaught exceptions automatically. You must know who owns the error event to avoid having the application log once and the framework log again.
- **Audit/security differs from operational errors:** an access-denied event under an audit policy may need full recording even though 403 is an expected outcome and does not need an ERROR stack trace.

If you are unsure which layer should log, ask: **"Who is responsible for determining the final outcome, triggering retries, or returning the error externally?"** That is usually the most logical place.

## 4. Logging exceptions with the right API to preserve stack traces and causes

Common APIs in Java:

### SLF4J (with a suitable Logback or Log4j2 backend)

```java
logger.error("Operation failed", ex);
logger.error("Order failed orderId={}", safeOrderId, ex);
```

In SLF4J, passing the `Throwable` using the proper overload or as the last argument in the message pattern allows the backend to process the stack trace. Do not change this to:

```java
logger.error("Operation failed: {}", ex.getMessage());
logger.error("Operation failed: " + ex);
```

The latter two only pass **constructed text** and typically do not preserve the full cause/stack trace in the structured logging event. However, **not every stack trace is safe to emit**: exception messages from downstream calls can contain tokens, SQL literals, file paths, request URLs, or customer data. For sensitive data, apply redaction/formatting policies, log access controls, and careful field selection rather than assuming every ERROR can safely print the full Throwable.

### java.util.logging (JUL)

```java
logger.log(
        java.util.logging.Level.SEVERE,
        "event=request.failed error_code=DOWNSTREAM_UNAVAILABLE",
        ex);
```

JUL uses `Level.SEVERE` for severe errors; the Handler/Formatter decides the content and destination. Do not assume JUL `WARNING` and `SEVERE` are identical APIs to SLF4J `WARN`/`ERROR`. You need to configure the actual handlers, filters, formatters, and levels.

### Preserving the root cause when wrapping

```java
throw new OrderServiceUnavailableException(
        "Order operation unavailable", originalIOException);
```

This is illustrative code; the custom exception needs a constructor that accepts a cause. You can inspect `getCause()` to understand the deeper reason, but **do not strip away all wrapper layers**: the service-level exception explains which operation failed, while the root cause reveals whether DB, HTTP, I/O, or validation was the technical reason. The logging event should retain both the operation/context and the cause chain.

**Watch out for suppressed exceptions:** `try-with-resources` can attach exceptions thrown while closing a resource to `Throwable.getSuppressed()`. A full stack trace formatter can display both cause and suppressed exceptions; printing only `ex.getMessage()` can lose them.

## 5. Standalone Java 17 example: one boundary, one error event

The example below simulates two types of boundaries: an **HTTP request** and a **background job**. The repository throws an `IOException`, the service wraps it in `ItemUnavailableException` with the original cause, and the HTTP boundary catches and logs it **once** before returning a safe message. The background job has its own exception, and the job boundary records the failed outcome once.

The example uses **JUL in the JDK** and a custom `Handler` that prints only the level, event, exception type, and root-cause type so that stdout is **deterministic**, independent of timestamps, thread IDs, or varying stack traces. **Production systems should generally retain the full throwable in a protected sink**, depending on data classification. This handler is only for testing the concept, not a production logging backend.

Save with the exact filename **`BoundaryLoggingDemo.java`**:

```java
import java.io.IOException;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class BoundaryLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger("example.boundary");

    static final class ItemUnavailableException
            extends RuntimeException {
        ItemUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    record Response(int status, String body) {}

    private static void setupLogger() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }

                Throwable thrown = record.getThrown();
                Throwable root = thrown;
                while (root != null && root.getCause() != null) {
                    root = root.getCause();
                }

                String type = thrown == null
                        ? "none" : thrown.getClass().getSimpleName();
                String rootType = root == null
                        ? "none" : root.getClass().getSimpleName();

                System.out.printf(
                        "LOG level=%s %s exception=%s root_cause=%s%n",
                        record.getLevel().getName(),
                        record.getMessage(), type, rootType);
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };
        handler.setLevel(Level.ALL);
        LOG.addHandler(handler);
    }

    // Repository: throws an error without logging and rethrowing.
    private static String loadFromRepository(String itemId)
            throws IOException {
        if ("broken".equals(itemId)) {
            throw new IOException("upstream unavailable");
        }
        return "item:" + itemId;
    }

    // Service: translates and preserves the cause; does not log redundantly.
    private static String getItem(String itemId) {
        try {
            return loadFromRepository(itemId);
        } catch (IOException ex) {
            throw new ItemUnavailableException(
                    "Item backend unavailable", ex);
        }
    }

    // HTTP boundary: decides status, response, and error event.
    private static Response handleRequest(
            String requestId, String itemId) {
        try {
            return new Response(200, getItem(itemId));
        } catch (ItemUnavailableException ex) {
            LOG.log(
                    Level.SEVERE,
                    "event=http.request.failed request_id=" + requestId
                            + " error_code=ITEM_UNAVAILABLE",
                    ex);
            return new Response(
                    503, "Service temporarily unavailable");
        }
    }

    // Job boundary: logs when the job actually ends in failure.
    private static void runJob(String jobId, Runnable task) {
        try {
            task.run();
        } catch (RuntimeException ex) {
            LOG.log(Level.SEVERE,
                    "event=job.failed job_id=" + jobId, ex);
        }
    }

    public static void main(String[] args) {
        setupLogger();

        Response ok = handleRequest("req-001", "ok");
        System.out.printf(
                "HTTP req-001 status=%d body=%s%n",
                ok.status(), ok.body());

        Response unavailable = handleRequest("req-002", "broken");
        System.out.printf(
                "HTTP req-002 status=%d body=%s%n",
                unavailable.status(), unavailable.body());

        runJob("nightly-7", () -> {
            throw new IllegalStateException("checkpoint mismatch");
        });

        System.out.println("DONE");
    }
}
```

Compile and run with **Java 17+**:

```bash
javac BoundaryLoggingDemo.java
java BoundaryLoggingDemo
```

**Exact stdout:**

```text
HTTP req-001 status=200 body=item:ok
LOG level=SEVERE event=http.request.failed request_id=req-002 error_code=ITEM_UNAVAILABLE exception=ItemUnavailableException root_cause=IOException
HTTP req-002 status=503 body=Service temporarily unavailable
LOG level=SEVERE event=job.failed job_id=nightly-7 exception=IllegalStateException root_cause=IllegalStateException
DONE
```

Step-by-step explanation:

1. `req-001` succeeds: returns 200 with no ERROR log. This does not forbid separate access logging; this example illustrates **exception logging**, not full access logs.
2. `req-002` encounters an `IOException` in the repository. The service creates `ItemUnavailableException(..., ex)` so the cause is preserved; neither layer prints a stack trace. The boundary logs `SEVERE` once and chooses HTTP 503.
3. The client only receives `Service temporarily unavailable`, without seeing the internal message `upstream unavailable`, the Java exception name, or the stack trace. In production, a standard response mapping policy is required.
4. `runJob` catches `IllegalStateException` and logs a `job.failed` event at the job boundary. It has no HTTP status because it is a different type of operation.
5. The demo handler prints only the **type names** of the throwable and root cause, so the output is completely deterministic. `LogRecord` actually holds the `Throwable`; a real backend can render the stack trace, though you should evaluate sensitive data in exception messages.
6. `runJob` in the example treats the error as **terminal** and ends the job. If using a scheduler with a retry policy, do not swallow the exception in a way that makes the framework think the job completed; report the outcome to the scheduler/retry mechanism according to its contract.

This example intentionally uses only a single thread and memory; it **does not test async logging, log durability, audit completeness, or real framework routing**. To verify production behavior, test at the actual HTTP/job boundary and confirm that events reach the backend.

## 6. HTTP boundary: finalizing the response and logging in the right place

For web applications, exception-handling points typically include `@RestControllerAdvice`/`@ExceptionHandler` in Spring MVC, Servlet error handlers/Filters designed for errors, or equivalents in other frameworks. Principles:

- **Exception-to-response mapping:** classify exceptions into stable error codes and appropriate HTTP statuses.
- **Do not leak internal details:** the public body should contain a safe `error_code`/message and request ID; never return stack traces, SQL queries, internal paths, or tokens.
- **Record the right outcome:** if an exception is handled as a valid HTTP 404/409, do not default to logging ERROR. If a backend times out and the request ultimately fails, ERROR may be appropriate.
- **Choose the right timing:** only consider an operation complete at the appropriate processing phase. For async/streaming requests, do not assume a controller return means the response is complete.
- **Avoid logging in two places:** the framework may automatically log unhandled exceptions; if `@ExceptionHandler` already logs and returns a response, server/access logging configuration should distinguish event types.
- **Cover early errors:** authentication filters, malformed requests, or 404 routing can happen before controller advice; separate logging at the corresponding boundary is needed if policy requires tracking them.

### Spring MVC illustration

```java
@RestControllerAdvice
class ApiExceptionHandler {
    private static final org.slf4j.Logger LOG =
            org.slf4j.LoggerFactory.getLogger(
                    ApiExceptionHandler.class);

    @ExceptionHandler(ItemUnavailableException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    public ApiError unavailable(ItemUnavailableException ex) {
        String requestId = TrustedRequestContext.currentRequestId();
        LOG.error(
                "event=http.request.failed error_code=ITEM_UNAVAILABLE request_id={}",
                requestId, ex);
        return new ApiError(
                "ITEM_UNAVAILABLE", "Service temporarily unavailable");
    }
}
```

**This is conceptual code, not a standalone runnable file**: it requires Spring MVC, appropriate imports/annotations, and definitions for `ItemUnavailableException`, `ApiError`, and `TrustedRequestContext`. `TrustedRequestContext` represents a request ID generated or validated at a trusted ingress; do not take an unvalidated ID from any arbitrary client header and treat it as a trusted identity. To verify runtime status/body behavior, add integration tests with the actual handler.

When multiple handlers exist, specify which handler produces the primary error log and which only translates the response. A broad global handler catching `Exception` can mask bugs, swallow `Error`, or make all errors look identical; never use it to "catch everything and return 200".

### Status codes alone do not fully express error severity

| HTTP outcome | Common meaning | Exception logging guidance |
| --- | --- | --- |
| `400` invalid input | Expected client error per contract | Usually DEBUG/INFO or metrics only; do not spam stack traces |
| `401` unauthenticated | Missing or failed authentication | May emit a structured security event; never log credentials |
| `403` unauthorized | Insufficient permissions | Audit/security per policy; do not treat as a server crash |
| `404` not found | Resource/route not found | May be normal behavior; watch for scanners/path probing |
| `409` conflict | Version/state conflict | Usually an expected outcome or business error worth analyzing |
| `429` rate limit | Client exceeded limit | Metrics/security rules; no full Throwable needed on every call |
| `500` unhandled | Unexpected error | ERROR with minimal context and cause |
| `502/503/504` upstream/dependency unavailable | Dependency failure, timeout, or unavailability | ERROR or WARN depending on policy and recoverability |

This is a **classification guide**, not a mandatory table for every application. A 404 on a critical endpoint might be anomalous, or repeated 403s might require a security alert. Conversely, a 503 during a retry that later succeeds does not mean the final HTTP request failed. Log outcomes according to the actual boundary.

## 7. Background jobs, schedulers, and thread boundaries

In background tasks, there is no HTTP exception handler taking responsibility. The boundary may be a job runner, a scheduler callback, or a task completion handler.

### ExecutorService and Future

With `ExecutorService.submit(...)`, exceptions in the task may be held inside the `Future`; the caller must call `get()` or check the result per contract to observe the failure. If the `Future` is ignored, the exception may not be represented as a reliable error event.

```java
Future<?> future = executor.submit(() -> runScheduledOperation());
try {
    future.get();
} catch (ExecutionException ex) {
    logger.error("event=job.failed job_id={}", jobId, ex.getCause());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    logger.warn("event=job.wait_interrupted job_id={}", jobId);
}
```

This is an illustrative snippet requiring `executor`, `logger`, `jobId`, and imports/logic; it does not run standalone. `ExecutionException` wraps the task's error; you can log either the wrapper or its cause depending on the context you need to keep, without losing the original information. When encountering `InterruptedException`, **restore the interrupt flag** if you do not propagate the exception; do not swallow it and wait indefinitely.

If a task logs ERROR itself and throws an exception, and the caller of `future.get()` logs again, you will get two identical events. Choose the true owner of the outcome: **the job itself** if it handles and finishes there, or **the orchestrator** when it observes the final outcome from the `Future`.

### CompletableFuture and reactive pipelines

In `CompletableFuture`, an exception may be wrapped in `CompletionException` or passed to `exceptionally`/`handle`/`whenComplete` callbacks. Do not attach multiple `whenComplete` callbacks that all log ERROR for the same error and then log again at HTTP response mapping. Decide clearly which callback handles it and which simply propagate.

In reactive code, error signals can occur asynchronously. Hooks like `doOnError` may log on subscription/retry; **each retry can produce another log** even if the overall operation eventually succeeds. Choose between per-attempt diagnostics and terminal failure events, and use proper context propagation instead of assuming `ThreadLocal` is always populated.

### Scheduled tasks

Different schedulers handle task exceptions according to their own rules (stopping the schedule, logging, rescheduling, or holding the error in a Future). Do not assume the exception "will automatically be logged somewhere". Check the actual framework/scheduler, define where `SUCCESS`/`FAILED` status is finalized, and emit job outcome metrics. Do not catch `Throwable` broadly to swallow serious JVM errors just to keep the scheduler running.

## 8. Message consumers: ACK, retry, and dead-letter boundaries

A message consumer has a very clear boundary: **after processing, the consumer decides to ACK/commit offset, retry/requeue, or route to a dead-letter queue (DLQ)**. Logging must align with that decision.

```text
Message received
   -> validate
   -> process
      +-> success: commit/ACK, success metric
      +-> transient error: retry per policy
      +-> unprocessable error: reject/DLQ or stop per policy
   -> log terminal event based on final decision
```

For example:

- If the broker allows 5 retries, do not emit 5 ERROR stack traces with the message "processing failed permanently" on the very first attempt.
- You can emit controlled DEBUG/WARN logs for retry attempts with `attempt`, `max_attempts`, `message_id`, and a reason code; a retry counter metric is usually more useful than multiple identical stack traces.
- When retries are exhausted and the message moves to the DLQ, the consumer boundary emits a **terminal failure event** recording the decision and cause, logically once where possible.
- If a message is rejected due to an invalid schema, apply a dedicated poison-message policy to avoid infinite retries that bloat logs and the DLQ.
- If a handler catches an exception, logs it, and then **acknowledges despite not processing it**, the message can be lost permanently. Never do that just to "make red errors go away".

**Important caveat:** logging and ACK/offset commit do not form an atomic transaction just because they are in the same method. A consumer might process successfully, time out during ACK, and retry, leading to duplicates. Use idempotency/deduplication for critical business side effects and document the actual broker/framework semantics.

In messaging frameworks that automatically log unhandled exceptions, if a handler catches, logs, and rethrows to trigger a retry, the framework may print the same throwable again. When handing off to the framework, you can simply **propagate and let it log**, or adjust configuration so the terminal event is logged by the proper owner.

## 9. Retry boundaries and transient errors

An operation may encounter short-lived errors and then succeed. In that case, the final boundary should describe **the outcome after all attempts**, not necessarily fire ERROR alerts on every attempt.

| Progression | Suggested log | Useful metric |
| --- | --- | --- |
| Attempt 1 times out; attempt 2 succeeds | `recovered` outcome event or DEBUG retry; do not mark request failed | `retry_attempts_total` |
| Retries exhausted, 503 response | One terminal ERROR with error code and attempt count | `operations_failed_total` |
| Non-retryable input error | `rejected`/`denied` outcome per policy; possibly no full stack | `invalid_requests_total` |
| Circuit breaker is open | State transition log or rate-limited event; avoid WARN on every call under high traffic | `circuit_breaker_open_total` |
| Timeout due to client cancellation | Classify as cancellation; check whether the task is still running | `cancelled_operations_total` |

If you want to attach `attempt=3` to the final event, obtain the attempt count from the retry library or operation context; do not guess from how many times a method was called. A repeated downstream failure across hundreds of requests can still validly produce multiple boundary events, so apply **rate limiting/aggregation and metrics** to avoid overwhelming the logging pipeline.

The "log once" principle does not mean erasing retry history. Use **metrics + bounded diagnostic logs** for individual attempts, and a **terminal event** for the outcome operators need to investigate.

## 10. Structured logging at the boundary

A good error record should answer **what operation failed, where, the outcome, the impact, and the cause**:

```json
{
  "timestamp": "2026-01-01T00:00:00Z",
  "event.name": "http.request.failed",
  "service.name": "catalog-api",
  "deployment.environment.name": "prod",
  "http.route": "/items/{itemId}",
  "http.method": "GET",
  "http.status_code": 503,
  "request_id": "req-002",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "error.code": "ITEM_UNAVAILABLE",
  "exception.type": "ItemUnavailableException",
  "cause.type": "IOException",
  "retry.attempts": 3,
  "message": "Item lookup failed after retry"
}
```

This is an **illustrative JSON schema**, not a set of attributes automatically recognized by every backend. OpenTelemetry semantic convention key names and collector/cloud log store mappings can change across versions. Choose a stable internal schema and map it appropriately to your backend.

Key fields:

| Field | Purpose | Notes |
| --- | --- | --- |
| `event.name` | Stable operation/event identifier | Do not use free-form messages as the event name |
| `error.code` | Logical error grouping for stats and queries | Not the same as the exception class |
| `exception.type` / cause | Diagnose error type | Stack traces may contain sensitive data |
| `request_id`/`job_id`/`message_id` | Locate operation outcome | IDs must come from a trusted source and be stable in scope |
| `trace_id` / `span_id` | Link to distributed trace | A request may have multiple spans; tracing may be sampled |
| `http.route` | Endpoint template | Avoid raw paths containing IDs/tokens in general logs |
| `http.status_code` | Final HTTP outcome | Do not use an anticipated value before exception mapping |
| `retry.attempts` | Number of attempts executed | Read from retry policy/runtime |
| `service.name` / environment | Distinguish failing service/layer | Helps interpret multiple error logs across microservices |
| `duration_ms` | Latency impact | Measure with a monotonic clock over the operation lifecycle |

In distributed systems, logging at two boundaries can produce two events with the same trace ID but **different event names, service names, and operations**. That is not necessarily a duplicate. When analyzing failures, group by trace ID, operation ID, and error code rather than assuming every ERROR corresponds to an independent failed request.

## 11. MDC, thread pools, and trustworthy context

To preserve correlation IDs, many logging backends support MDC (Mapped Diagnostic Context). However, standard MDC is thread-bound. In `ExecutorService`, `CompletableFuture`, or reactive pipelines, context does **not automatically** follow every task.

Conceptual pattern using SLF4J MDC:

```java
try (var ignored = org.slf4j.MDC.putCloseable(
        "request_id", trustedRequestId)) {
    service.handleRequest();
} catch (ServiceException ex) {
    logger.error("event=request.failed request_id={}",
            trustedRequestId, ex);
}
```

This is not a standalone program; it requires SLF4J, a logger, a service, and `trustedRequestId`. Note that `MDC.putCloseable` is a helper for the current scope; it does not automatically propagate context to a new worker thread, nor does it turn `request_id` into an authenticated identity. If a thread pool carries prior context, manage restore/cleanup per the framework contract to avoid leaking metadata across requests. Never put raw HTTP bodies or secrets into MDC.

**At the boundary, prefer context from trusted sources:**

- Request ID validated at ingress or regenerated when client input is invalid.
- Actor/principal from the authentication context, not from self-asserted client headers.
- Error code from server-side exception mapping/policy.
- Route template matched by the framework, not a raw path containing tokens.
- Service/deployment metadata from runtime configuration, not overridable by requests.

If a request ID is unavailable, still log the event with service, operation, and error code; do not fabricate actor identities or fake IDs. For sensitive business actions, audit trails have a different contract from operational error logging.

## 12. Security: avoiding information leaks when logging exceptions

Exceptions often contain low-level details: query URLs with tokens, DB connection strings, SQL statements, internal file paths, client payloads, or user data. **Combine useful context with data minimization**:

1. Never log plaintext passwords, API keys, access tokens, cookies, authorization headers, full request bodies, or unnecessary personal data.
2. Use `error.code` and permitted internal IDs instead of concatenating the entire exception message into a public text field.
3. Separate **client responses** (safe messages) from **server logs** (which may keep technical details in an access-controlled store). Never return `ex.toString()` or stack traces to the client.
4. Apply secret redaction at the source and in the pipeline where appropriate; collector-side masking is an extra layer and cannot erase data already written to stdout or earlier buffers.
5. Control log viewing permissions, storage regions, retention, and access auditing, especially when logs contain actor IDs, IPs, or sensitive resources.
6. If full stack traces are enabled in production, check exception message fields and the suppressed/cause chain; a filter that only masks the outer message can miss a secret deep in a cause.
7. Prevent log injection: use a JSON encoder with proper escaping; never trust raw client-supplied data as `event.name`, log level, or actor.

**Risk of "logging failures causing business logic to fail":** for operational logs, do not let a secondary exception during logging mask the original error or break the response if the logging pipeline fails. At the same time, do not silently catch-and-ignore indefinitely in mandatory audit systems. Choose a fail-open/fail-closed policy based on event type and business contract.

## 13. Should handled exceptions be logged as WARN?

There is no universal mapping from every Java exception class to a log level. The same `IOException` could be:

- A transient timeout during a retry where the operation eventually succeeds: perhaps only a DEBUG/INFO diagnostic or a metric.
- A timeout after exhausting retries resulting in HTTP 503: ERROR/WARN per policy, with a terminal event.
- A client-cancelled download error: usually not an automatic ERROR with a full stack on every request, though you should track the cancellation rate.
- An unexpected error causing data loss: requires ERROR, alerting, and appropriate remediation.

A decision guide:

| Boundary outcome | Commonly considered level | Priority content |
| --- | --- | --- |
| Success | INFO access log or metrics only | Route/operation, duration, status |
| Expected rejection | DEBUG/INFO/WARN or separate audit/security | Error code, actor/resource when appropriate, reason |
| Recovered/degraded | Bounded INFO/WARN | Fallback mode, dependency, retry count |
| Terminal failure | ERROR or JUL SEVERE | Operation, outcome, correlation, exception |
| Logging/audit mechanism failure | Dedicated operational alert | Queue/exporter errors, dropped records, gaps |
| Process cannot continue | FATAL if supported by backend, or ERROR/SEVERE | Lifecycle event, recovery status, avoid log loops |

Do not classify all 4xx responses as ERROR or all 5xx responses as WARN/ERROR without considering business semantics. Uncontrolled increases in INFO/WARN verbosity during repeated failures can cause a log storm; measure error counts with metrics and configure reasonable rate limiting/sampling **without dropping mandatory audits**.

## 14. Common anti-patterns

| Anti-pattern | Why it is harmful | Better alternative |
| --- | --- | --- |
| `catch (Exception ex) { log.error(..., ex); throw ex; }` at every layer | Duplicate stack traces, no outcome decision yet | Propagate/translate, log at the handling boundary |
| `catch (Exception ex) { return null; }` | Swallows error, caller assumes success or hits NPE later | Return error per contract, log outcome at boundary |
| Logging a message and dropping the throwable | Loses stack/cause/suppressed details | Use an overload accepting `Throwable` when safe |
| Wrapping an exception without its cause | Loses the root cause | `new DomainException("...", ex)` |
| Logging ERROR for every validation failure | Noise, alert fatigue, high cost | Expected 4xx per policy, metrics/security events if needed |
| Logging each retry attempt as a terminal failure | False alarms when operation recovers, log storm | Terminal event after retries + attempt metrics |
| Writing the exception into the HTTP response | Leaks paths, tokens, internal structure | Safe response code/message, request ID |
| Putting raw request/exception messages into MDC | Data leakage, thread reuse mixes context | Allowlisted fields, proper scoping/cleanup |
| Broad `catch (Throwable)` to "log everything" | Can hide serious `Error`s, OOM | Catch handleable error types; give fatal failures a separate policy |
| Logging the same Throwable in both repository and controller | Duplicates and unclear ownership | Repository preserves cause; controller/handler finalizes outcome |
| Logging a job error and forgetting to rethrow when the scheduler needs to retry | Scheduler assumes the job succeeded | Propagate outcome/exception per scheduler contract |
| Catching consumer errors, logging, and blindly ACKing | Message loss, violates at-least-once | ACK/retry/DLQ per policy |
| Using an ERROR log instead of an audit event | Lacks durability/actor/outcome guarantees | Separate audit pipeline when mandatory |
| Logger prints only `ex.getMessage()` | Message may be empty/sensitive, lacks cause | Stable code + controlled typed throwable |
| Assuming one `logger.error` call = one event received by backend | Async queues, filters, collectors can drop/retry | End-to-end probes, drop metrics, backpressure |

## 15. Testing boundary logging

Do not only test that `catch` returns the right status; verify **the exact event count, location, error type, and absence of data leaks**.

| Scenario | Expectation |
| --- | --- |
| Repository throws IOException, service wraps | Cause chain exists; repository does not log full stack if not handling |
| HTTP boundary maps ItemUnavailable | One terminal error event with request ID + error code, returns safe status/body |
| Successful request | No exception ERROR event; independent access log/metric if configured |
| Expected validation failure | Correct 4xx/error code; no unnecessary ERROR stack trace |
| Retry fails first then succeeds | No terminal failure reported; retry metric increments |
| Retries exhausted | One terminal failure event with accurate attempt count and outcome |
| Worker task exception | Job owner receives error and decides retry/fail, not unintentionally swallowed |
| Future exception | Orchestrator observes outcome; no duplicate log with task |
| Message handler error | Consistent ACK/retry/DLQ; no erroneous ACK just because it was logged |
| Framework error before controller | Error/access logging covered per policy, no duplicate entries |
| Concurrent requests | No mixing of MDC, trace ID, or actor across threads |
| Exception message contains a secret | Secret does not appear in client response or unauthorized logs |
| Log backend/collector failure | Metrics and alerts exist; operational failure policy does not mask original exception |
| Querying in log backend | Event is searchable by service, event.name, request ID; not unexpectedly duplicated |

In unit tests, replace the logger with a controlled test appender/handler or capture events to assert exact `event.name`, level, throwable type/cause, and count. For async loggers, wait on a condition/flush with a timeout instead of using a hard-coded `Thread.sleep` to confirm the event arrived. In integration tests, enable the framework exception handler, middleware, and real backend to verify there is no double logging.

Do not measure exception counts by counting stack trace lines; one event can render across many lines. Count structured **log events** or event IDs.

## 16. Operations: logs do not replace metrics and traces

Boundary logging provides detailed events, but a reliable platform needs multiple signals:

- **Metrics:** failed operation counts, retry counts, latency, downstream timeouts, queue backlogs; suited for calculating rates/SLOs without parsing every log.
- **Tracing:** understanding which services and spans a request traverses; a single trace may contain multiple boundary events across different services, and traces may be sampled.
- **Structured logs:** investigating individual operations with status/error code/context, keeping exceptions controlled.
- **Audit events:** sensitive or legally mandated actions require separate guarantees and must not be arbitrarily sampled.

For example, when the payment service fails, there may be an ERROR event at the payment boundary and an ERROR event at the checkout boundary if checkout ultimately fails: these two events describe **two different operations**, so give them distinct event names, services, and outcomes. On dashboards, group by service/operation rather than summing all ERRORs to infer the number of failed requests.

Logging ERROR at every layer can also hide logging outages: when queues overload, they may begin dropping records, leaving operators without the most critical events. Monitor `dropped_logs`, exporter failures, ingest lag, and independent event probes if reliability requirements demand it.

## 17. Adoption checklist

- [ ] Have you identified the right **outcome-finalizing boundary** for HTTP requests, jobs, messages, CLIs, and workers?
- [ ] Do repositories/services only translate or propagate when not truly handling, avoiding duplicate stack log-and-rethrow?
- [ ] When wrapping exceptions, is `cause` preserved without breaking the chain/suppressed information?
- [ ] Are exceptions logged via an API that accepts `Throwable`, not just `getMessage()`, when policy permits?
- [ ] Do expected failures, recovered operations, terminal failures, and audits have distinct levels/outcomes?
- [ ] Are client responses/error codes safe, without exposing stack traces, tokens, or internal data?
- [ ] Are request/job/message IDs, service, event name, retry count, and trusted context included?
- [ ] Is MDC properly propagated and cleaned up across async/thread pools?
- [ ] Are terminal ERRORs avoided on individual retry attempts when the final operation succeeds?
- [ ] Do jobs/Futures/consumers avoid swallowing errors in ways that mislead the scheduler or broker about the outcome?
- [ ] Have you checked framework default logging, middleware dispatch, and async completion to prevent double logging?
- [ ] Do you have tests for event counts/types/Throwables, secret leakage, and end-to-end readback from the log backend?
- [ ] Do metrics, traces, and audit policies complement logging appropriately instead of being mixed together?

**Remember:** "logging at the boundary" does not mean pushing every exception to the very top or mechanically removing logs from lower layers. It means **every error event must have one owner, one clear handling outcome, and enough context to investigate**. Intermediate layers preserve or translate the cause; the boundary decides whether to return a response, retry, fall back, or terminate the task and logs accordingly. This approach reduces duplicate stack traces, cuts noise, protects data, and turns logs into trustworthy evidence of what actually happened.
