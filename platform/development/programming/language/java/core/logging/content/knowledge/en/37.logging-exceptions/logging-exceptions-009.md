# Technical Errors in Java Logging and Exceptions

## 1. What is a Technical Error?

A **technical error** is an error arising from software, infrastructure, or execution conditions that prevents an application from **completing an operation as expected**: database timeout, I/O failure, refused connection to a dependency, misconfiguration, resource exhaustion, serialization failure, a `NullPointerException` bug, or a broken background task.

In Java systems, exceptions represent and propagate error states. **Logging** is the mechanism that helps operators understand what happened, at which step, which request/job was involved, and what the impact was. These two goals are distinct:

- **Throw/propagate exception**: informs the caller that an operation failed so it can control execution flow, roll back, retry, or respond appropriately.
- **Log technical error**: provides diagnostic traces for observability and investigation.
- **Return an API result**: communicates with the client through a public contract, typically without exposing stack traces, SQL, tokens, or infrastructure details.
- **Metric/alert**: tracks error counts, error rates, latency, dependency health, and SLO impact.

A technical error **is not always a bug**, nor **does it automatically need an ERROR log at every layer**. A transient connection drop may be retried and recovered; a request cancelled by the client may be a normal event; an unexpected bug may need to be logged once at the processing boundary.

### Learning Objectives

After this lesson, you will be able to:
1. Distinguish **technical errors** from validation errors, business rejections, and expected denial cases.
2. Preserve the **cause chain**, stack trace, and classification metadata when translating exceptions across layers.
3. Design logs using a schema with `error_code`, `operation`, `request_id`, `dependency`, `outcome`, and error source.
4. Choose logging boundaries to avoid logging the same exception repeatedly across repository, service, controller, and framework layers.
5. Write and run a standalone Java 17 example with `java.util.logging` (JUL) that handles expected and technical errors without leaking sensitive exception messages.
6. Apply these principles to REST APIs, message processing, background jobs, retry/timeout handling, monitoring, and incident response.

## 2. Distinguishing Technical Errors from Business Errors

A ticketing system may reject a ticket purchase because seats are sold out. That is an **expected business outcome**. Conversely, if the service cannot connect to the database to check seat availability, that is a **technical error**. Both situations may cause a request to fail, but their handling and logging differ.

| Category | Example | Meaning | Typically Appropriate Response/Log |
| --- | --- | --- | --- |
| **Validation** | Missing required field, invalid date format | Input does not satisfy contract | 4xx response / validation code; not ERROR by default |
| **Business rejection** | Out of stock, insufficient balance, invalid state | System behaves correctly per business rules | Clear business code; INFO or audit as needed |
| **Authentication/authorization** | Unauthenticated or unauthorized | Access denied per policy | 401/403 per protocol; separate audit/security event |
| **Transient technical failure** | Network timeout, database temporarily unavailable, upstream rate limit | May recover depending on conditions | Bounded retry or 5xx error; warning/error depending on boundary |
| **Permanent technical/configuration failure** | Incompatible schema, misconfiguration, invalid service credentials | Usually not resolved by immediate retry | Error/alert with configuration code, deployment intervention |
| **Unexpected defect** | Internal invariant violation, `NullPointerException`, logic bug | Unanticipated / not part of contract | Log once at boundary, classify as `UNEXPECTED`, investigate |
| **Cancellation/interruption** | Client disconnect, valid task cancellation, thread interrupt | May be lifecycle control rather than system failure | Preserve cancellation semantics; do not escalate all cases to ERROR |

**Classify by semantics, not just by exception class.** An `IllegalArgumentException` might be caused by a client sending an invalid value or by an internal bug producing bad data. An `IOException` could be a transient timeout, a deleted file, or a connection closed during shutdown. A `SQLException` may carry a specific SQLState/error code. Deciding whether to retry or alert requires **operation context and the dependency's contract**.

### 2.1. Technical Failures Can Occur Even for Valid Client Requests

```text
Client POST /orders
       |
       v
Validate request          (PASS)
       |
       v
Business rule             (PASS)
       |
       v
Database write            (TIMEOUT)
       |
       v
Technical failure -> rollback/unknown commit? -> policy
```

A database timeout requires distinguishing **whether it is certain the write did not commit**. If the request was sent and the response was lost, the application might **not know whether the operation was executed**. Retrying without idempotency can create duplicate orders or duplicate transactions. Do not assume a retry is safe simply because the stack trace contains `TimeoutException`.

### 2.2. HTTP Status Is Not the Full Diagnosis

In REST APIs, a dependency failure may result in `503 Service Unavailable` or `502 Bad Gateway` depending on the service's role; an unexpected bug typically uses `500 Internal Server Error`. However, the mapping depends on the API contract, reverse proxy, retry semantics, and error type. Do not turn every technical error into `500`, and do not treat every `500` as having a single cause.

A field like `error_code=DEPENDENCY_TIMEOUT` is more useful than free-form text messages. Standardize public error codes separately from internal error codes if needed. Clients should never receive database hostnames, JDBC URLs, stack traces, or exception messages containing credentials.

## 3. Exceptions Are Signals; Logs Are Traces

A Java exception typically carries:
- **Type**: `IOException`, `TimeoutException`, `IllegalStateException`, or a custom exception.
- **Message**: an explanatory string that **may** contain data not permitted to be shared.
- **Cause**: the source exception in `getCause()`, allowing tracing back to the originating layer.
- **Stack trace**: the chain of call frames, file/line info, and `Caused by` sections when rendered.
- **Suppressed exceptions**: secondary errors thrown when closing resources in `try-with-resources` or similar mechanisms.
- **Context**: operational metadata such as operation, dependency, correlation ID, and retry attempt, which should generally be controlled **log fields** rather than raw payloads stuffed into the message.

Example error propagation path:

```text
Repository: IOException("read timed out")
             |
             v
Service: TechnicalFailure("DEPENDENCY_UNAVAILABLE", cause)
             |
             v
HTTP boundary: log one technical event + map to 503
             |
             v
Client: safe response code and error_id
```

In the repository layer, calling `logger.error(..., e)` before throwing is not always necessary. If the service logs the same error and the controller logs it again, operators will see three stack traces for a single request. More logs do not equal better observability.

### 3.1. Preserving the Cause When Wrapping

Correct pattern in Java:

```java
// Integration snippet, not a standalone runnable program.
try {
    repository.write(order);
} catch (java.io.IOException cause) {
    throw new OrderStorageException(
            "ORDER_STORAGE_UNAVAILABLE", cause);
}
```

`OrderStorageException` is a **project-defined custom exception**; its constructor must store `cause` via `super(message, cause)`. This allows the boundary to inspect the root cause type and stack trace when permitted.

Anti-pattern:

```java
// Anti-pattern: loses the cause and may put sensitive text into the error.
catch (java.io.IOException e) {
    throw new RuntimeException(e.getMessage());
}
```

`getMessage()` does not replace `getCause()`. The snippet above loses the original call stack and copies raw potentially sensitive text into the new message. A stable error code with a preserved cause is usually far better.

### 3.2. Do Not Swallow Exceptions Just to "Avoid Seeing ERROR"

```java
// Anti-pattern: the caller may think the operation succeeded.
try {
    repository.write(order);
} catch (Exception ignored) {
    logger.warn("Temporary issue");
}
```

If an error is ignored, the transaction/caller may continue in an invalid state. Only swallow an error when there is a **real policy and fallback** that allows continuing, while ensuring state and metrics reflect the outcome. Do not catch generic `Exception` and always return success just to reduce ERROR log counts.

## 4. Logging Boundary: Log Where the Outcome Is Decided

A **logging boundary** is the place in a system responsible for observing the final outcome of an operation: an HTTP exception handler, a consumer container boundary, a scheduler/job runner, or a worker supervisor. This is usually where full request/job context is available and the final result/response is decided.

A recommended design:

```text
Transport / controller / consumer
           |
           v
        Service
           |
           v
       Repository  -- IOException
           |
           v
   Wrap preserving cause
           |
           v
     Propagate through
           |
           v
    Boundary decides outcome
           |
           +--> classify / map response or retry
           |
           +--> emit one coherent error event
           |
           +--> metrics / alert / retry policy
```

### 4.1. Do Not Log and Throw at Every Layer

Anti-pattern:

```java
// Illustrative code snippets; not a complete Java class.
// Repository
catch (IOException e) {
    logger.error("DB failed", e);
    throw e;
}

// Service
catch (IOException e) {
    logger.error("Order failed", e);
    throw new OrderStorageException("DEPENDENCY_UNAVAILABLE", e);
}

// Controller
catch (OrderStorageException e) {
    logger.error("Request failed", e);
    throw e;
}
```

A single failure produces multiple nearly identical `ERROR` records. Aggregators may miscount it as three errors, duplicate stack traces waste resources, and alerts get amplified.

Better approach:
- The repository attaches the **cause/type and necessary context** via an exception or structured result, without duplicate logging unless there is a distinct useful event.
- The service wraps errors by **semantics** without hiding the cause.
- The boundary logs one event with request ID, operation, classification, dependency, and outcome.
- If a lower-level log is needed to observe retries or circuit breakers, use a **different event** such as `dependency_retry_scheduled` or purposeful DEBUG logging; do not endlessly copy the same ERROR.

**Exception:** Logging at multiple layers can be warranted when each log describes a **different event**: "retry scheduled", "circuit breaker transitioned to OPEN", "request ultimately failed". These are not meaningless duplicates if their schema and outcome differ.

### 4.2. Distinguish Handled from Unhandled

If an error was handled and a fallback succeeded, `WARN` or `INFO` with `recovered=true` may be appropriate. If the final operation failed, the boundary can use `ERROR` or `SEVERE` depending on the backend and impact. If you only log ERROR before a retry and the retry succeeds, dashboards may show false alarms without the final result.

Example flow:

```text
dependency_attempt_failed attempt=1 transient=true
dependency_retry_scheduled backoff_ms=200
dependency_attempt_succeeded attempt=2
request_completed outcome=SUCCESS recovered=true
```

Do not log `request_failed` when the request ultimately succeeded. Distinguish **attempt-level errors** from **operation-level failures**.

## 5. Designing a Log Schema for Technical Errors

Illustrative JSON event example:

```json
{
  "event": "technical_error",
  "occurred_at": "2026-11-10T03:00:00Z",
  "severity": "ERROR",
  "service": "order-api",
  "operation": "order_read",
  "request_id": "req-104",
  "error_code": "DEPENDENCY_UNAVAILABLE",
  "category": "TRANSIENT_DEPENDENCY",
  "dependency": "orders-db",
  "exception_type": "IOException",
  "outcome": "FAILED",
  "retryable": true,
  "attempt": 1
}
```

**The values above are illustrative.** `retryable=true` is only accurate when the classification layer and retry policy prove the operation is safe to retry. Do not automatically mark every `IOException` as `retryable=true`.

| Field | Meaning | Notes |
| --- | --- | --- |
| `event` | Stable technical record type | Distinguish `technical_error` from `retry_scheduled` |
| `operation` | Logical operation that failed | Short stable name; do not embed raw URLs |
| `error_code` | Internal error code | From a managed list; can be grouped by domain |
| `category` | Dependency/config/bug/resource error | Needs clearly defined criteria |
| `outcome` | `FAILED`, `RECOVERED`, `CANCELLED` | Based on the **final boundary result** |
| `dependency` | Affected subsystem | Use an alias like `orders-db`, without credentials |
| `exception_type` | Relevant source exception class | Do not use raw exception message as an error code |
| `request_id` / `trace_id` | Correlation | Validate length/characters; not a secret |
| `attempt` | Execution attempt number | Scope and counting source must be clear |
| `retryable` | Whether retryable per policy | Do not infer solely from class or HTTP status |
| `duration_ms` | Operation latency | Measured number, not inferred from disparate timestamps |
| `service` / `instance` | Where the error was observed | Helps correlate multi-service logs |
| `error_id` | ID of a specific error occurrence | Useful for matching safe client responses with logs |

A log should not contain **full request bodies**, passwords, tokens, private keys, JDBC connection strings with credentials, cookies, payment cards, or unnecessary personal data. `Throwable.getMessage()`, stack traces, suppressed exceptions, and client library messages can contain URIs or payloads. Include permitted information via an **allowlist** and decide separately how full throwables are emitted.

**Structured logging** such as the SLF4J 2 fluent API makes fields searchable; it **does not automatically filter sensitive data**. Do not pass raw exceptions, DTOs, or headers into key-value pairs without review.

## 6. Standalone Java 17 Example: Distinguishing Business and Technical Errors

This example uses `java.util.logging` (JUL) built into JDK 17, requiring no Maven or Gradle. The program simulates four outcomes:
1. Successful operation.
2. Business rejection (`ORDER_NOT_FOUND`).
3. Dependency error (`IOException`) wrapped into a custom `TechnicalFault` while preserving the cause.
4. Unexpected error (`IllegalStateException`).

One exception in the demo intentionally contains a **simulated** secret string, but the logger only records **standardized error codes and exception types**, without raw messages or stack traces. This keeps stdout deterministic and demonstrates **data minimization**; in real deployments, stack traces may need to be written to an internal sink with appropriate security and redaction policies.

Create `TechnicalErrorLoggingDemo.java`:

```java
import java.io.IOException;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class TechnicalErrorLoggingDemo {
    private static final class BusinessFault extends RuntimeException {
        private final String code;

        BusinessFault(String code) {
            super(code);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    private static final class TechnicalFault extends RuntimeException {
        private final String code;

        TechnicalFault(String code, Throwable cause) {
            super("Technical operation failed", cause);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    private static final class CaptureHandler extends Handler {
        private final StringBuilder events = new StringBuilder();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.append(record.getLevel().getName())
                        .append(' ')
                        .append(record.getMessage())
                        .append('\n');
            }
        }

        @Override
        public void flush() {
            // Capture in memory; no file I/O.
        }

        @Override
        public void close() {
            flush();
        }

        String text() {
            return events.toString();
        }
    }

    private static void callDatabase() throws IOException {
        throw new IOException("database password=demo-db-secret");
    }

    private static String readOrder(int scenario) {
        if (scenario == 1) {
            throw new BusinessFault("ORDER_NOT_FOUND");
        }
        if (scenario == 2) {
            try {
                callDatabase();
            } catch (IOException cause) {
                throw new TechnicalFault("DEPENDENCY_UNAVAILABLE", cause);
            }
        }
        if (scenario == 3) {
            throw new IllegalStateException(
                    "debug token=demo-access-token");
        }
        return "READY";
    }

    private static void handle(
            Logger logger, String requestId, int scenario) {
        try {
            readOrder(scenario);
            logger.info("event=order_read result=OK requestId="
                    + requestId);
        } catch (BusinessFault business) {
            logger.info("event=order_read result=REJECTED code="
                    + business.code() + " requestId=" + requestId);
        } catch (TechnicalFault technical) {
            logger.severe("event=technical_error operation=order_read"
                    + " code=" + technical.code()
                    + " causeType="
                    + technical.getCause().getClass().getSimpleName()
                    + " requestId=" + requestId);
        } catch (RuntimeException unexpected) {
            logger.severe("event=technical_error operation=order_read"
                    + " code=UNEXPECTED causeType="
                    + unexpected.getClass().getSimpleName()
                    + " requestId=" + requestId);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lesson.technical.error.demo");
        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);

        CaptureHandler capture = new CaptureHandler();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        try {
            handle(logger, "req-101", 0);
            handle(logger, "req-102", 1);
            handle(logger, "req-103", 2);
            handle(logger, "req-104", 3);

            String output = capture.text();
            System.out.print(output);
            boolean secretLeaked =
                    output.contains("demo-db-secret")
                    || output.contains("demo-access-token");
            System.out.println("secretLeaked=" + secretLeaked);
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac TechnicalErrorLoggingDemo.java
java TechnicalErrorLoggingDemo
```

**Exact stdout** when run in a fresh JVM with no external code interfering with the demo logger:

```text
INFO event=order_read result=OK requestId=req-101
INFO event=order_read result=REJECTED code=ORDER_NOT_FOUND requestId=req-102
SEVERE event=technical_error operation=order_read code=DEPENDENCY_UNAVAILABLE causeType=IOException requestId=req-103
SEVERE event=technical_error operation=order_read code=UNEXPECTED causeType=IllegalStateException requestId=req-104
secretLeaked=false
```

### 6.1. Output Explanation

- `req-101`: `OK` outcome; no technical error.
- `req-102`: business rejection `ORDER_NOT_FOUND`, logged at `INFO` rather than treated as an alert-worthy system failure by default.
- `req-103`: I/O error wrapped into `TechnicalFault` with code `DEPENDENCY_UNAVAILABLE` and `IOException` preserved as `cause`. The logger records `causeType=IOException` without exposing the raw message containing `demo-db-secret`.
- `req-104`: unexpected error caught by the `RuntimeException` branch, classified as `UNEXPECTED` and logged with class name `IllegalStateException` without exposing the message containing the fake token.
- `secretLeaked=false` only proves **the two sample strings did not appear in the demo output**; it does not prove all parts of a real application handle secrets safely.
- `CaptureHandler` buffers text in a `StringBuilder` and disables parent handlers, so there are no timestamps or extra stack traces; the code only illustrates single-threaded execution and is **not a multi-threaded production logger**.
- Both technical errors are **handled at a simulated boundary**: `handle` does not return an HTTP status or perform an actual rollback. In a real system, combine transactions, response mapping, retries, and error metrics according to contract.

### 6.2. Why Doesn't the Demo Print Full Stack Traces?

A full stack trace from a specific exception contains file/line numbers and non-deterministic messages, making deterministic stdout difficult. More importantly, exception messages generated by libraries sometimes contain tokens, URLs, or private data. The demo intentionally outputs **safe codes/types**. In production, a restricted-access diagnostic sink may need stack traces to fix bugs; ensure data classification, retention, and secret handling are in place before enabling full output.

**Do not** enforce a blanket rule to "ban all stack traces." The right rule is choosing **when, where, and with what permissions** stack traces may be recorded, and ensuring messages/causes do not contain sensitive data. You cannot control every third-party library with a single regex.

### 6.3. Limitations and Production Improvements

The `scenario` classifier is only a simulation. In real applications, you do not read an integer from a client to decide the error type. Classification is based on exception/result contracts, retry policies, dependency health, and business impact. Checked exceptions like `IOException` are often wrapped at service boundaries when translating to domain-independent technical exceptions, though wrapping is not always necessary.

A production handler should:
- Use system-managed exception codes, not raw `getMessage()` strings as labels.
- Check whether `cause` is null before calling `getCause().getClass()` or use a null-safe helper method.
- Attach a server-generated or validated correlation ID.
- Decide log level after knowing whether the error was recovered.
- Avoid catching `Error`, `InterruptedException`, or cancellation in ways that lose runtime signals.
- Keep the original exception intact and follow appropriate transaction, ack, or HTTP response handling.

## 7. Log Levels: ERROR Does Not Mean "Every Throw"

Java JUL uses `SEVERE`, `WARNING`, `INFO`, `FINE`, etc.; SLF4J/Logback/Log4j 2 typically use `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE`. **Level names differ**, and the chosen level still depends on the event's meaning.

| Event | Reference Level | Explanation |
| --- | --- | --- |
| Input violates contract | INFO/DEBUG or metric | Clients may send invalid input normally; avoid log storms |
| Valid business rejection | INFO, audit per policy | System is enforcing rules as designed |
| Transient dependency error, then retry succeeds | WARN/DEBUG on attempt; INFO on outcome | Do not mark the operation as FAILED if it recovered |
| Dependency error causing final operation failure | ERROR/SEVERE at boundary | Needs investigation of error rate and impact |
| Unexpected/unhandled bug | ERROR/SEVERE at boundary | Needs controlled stack/context and alerts if significant |
| Missing message due to client cancellation | Protocol-dependent, often INFO/DEBUG | Do not treat every cancellation as an outage |
| Controlled shutdown | INFO/WARN depending on lifecycle | Distinguish normal shutdown from incomplete drain failures |
| Error inside logger/appender | Status/internal diagnostic channel | Avoid calling back into the broken pipeline |

There is no single level table for every system. For example, a startup configuration error may be **fatal for the service**, whereas a single 500 request might be one out of thousands of requests. Consider **blast radius, frequency, recoverability, and SLO commitments**.

### 7.1. Avoiding Alert Storms and False Severity

A request calls a dependency 3 times and ultimately fails:
- Three `attempt_failed` occurrences can be tracked via metrics.
- Only one `operation_failed` with an error code needs to be reported at the operation level.
- If the final retry succeeds, the summary event should be `operation_completed recovered=true`.
- If a retry is scheduled but not yet executed, do not report the operation as succeeded.

During a widespread downstream outage, tens of thousands of requests can generate tens of thousands of ERRORs. Rate limiting, sampling of **diagnostic logs**, aggregation, and error-rate alerting can reduce noise; do not arbitrarily sample **mandatory audit events**.

## 8. Security and Privacy of Exception Logs

Technical errors often carry messages from underlying subsystems. Examples prone to leaking data:

```text
Connection failed: jdbc:vendor://db.internal/app?user=svc&password=secret
HTTP call failed: https://partner.example.test?api_key=secret
Rejected payload: {"email":"x@example.test","password":"secret"}
Authorization failed: Bearer secret-token
```

These are **illustrative fake strings** showing what should not be logged. Store **dependency alias, code, request ID, and exception type**, not raw credentials or request bodies.

Areas to review:
- `exception.getMessage()` and `exception.toString()`.
- Full cause chains, suppressed exceptions, and stack traces.
- Headers such as `Authorization`, `Cookie`; signed URLs and query strings.
- SQL bind values, connection URIs, and file paths containing personal information.
- DTO `toString()` / record-generated methods, JSON serializers, and HTTP wire logging.
- MDC/ThreadContext or automatically attached structured logging fields.
- Log collectors, stdout, debug endpoints, backups, alerts, and tickets quoting logs.

**A regex in the log collector is no substitute for not generating secrets in logs.** Once an exception message is written to stdout, a masking layer in the dashboard does not erase the data from stdout, files, or upstream forwarders.

When a real secret leaks via logs: stop further leakage, assess affected sinks, restrict access, rotate/revoke credentials per policy, investigate access, and remediate the risk. Never paste real secrets into incident tickets or chat to "ask someone to check the error."

## 9. Spring Boot / REST API: Handling Errors at the Entry Point

In Spring MVC, `@RestControllerAdvice` with `@ExceptionHandler` is a common boundary for mapping exceptions to responses. This is **illustrative integration code** for a modern Spring project, not a standalone dependency-free Java 17 program.

```java
// Spring MVC illustrative snippet. The BusinessFault/TechnicalFault types
// here are project-defined custom exceptions.
@RestControllerAdvice
class ApiErrorHandler {
    private static final org.slf4j.Logger log =
        org.slf4j.LoggerFactory.getLogger(ApiErrorHandler.class);

    @ExceptionHandler(TechnicalFault.class)
    org.springframework.http.ResponseEntity<ApiError> onTechnical(
            TechnicalFault ex) {
        String errorId = java.util.UUID.randomUUID().toString();
        log.error("event=technical_error errorId={} code={}",
                  errorId, ex.code());
        return org.springframework.http.ResponseEntity
                .status(503)
                .body(new ApiError("SERVICE_UNAVAILABLE", errorId));
    }

    @ExceptionHandler(Exception.class)
    org.springframework.http.ResponseEntity<ApiError> onUnexpected(
            Exception ex) {
        String errorId = java.util.UUID.randomUUID().toString();
        log.error("event=technical_error errorId={} code=UNEXPECTED",
                  errorId);
        return org.springframework.http.ResponseEntity
                .status(500)
                .body(new ApiError("INTERNAL_ERROR", errorId));
    }

    record ApiError(String code, String errorId) {}
}
```

**Design Notes:**
1. The snippet above only shows the **error mapping point**; it does not declare external `TechnicalFault`, `ApiError`, or security/transaction configuration. Custom exception constructors/methods are provided by the project.
2. Do not return `ex.getMessage()` or stack traces to the client. Use `errorId` to correlate with internal logs.
3. `503` is not the right choice for **every** `TechnicalFault`; an unrecoverable error might be `500`, and a gateway might return `502`. Classify specifically.
4. `@ExceptionHandler(Exception.class)` should not swallow/capture every error across every stack: the framework has built-in exception resolvers, validation, and security filters. Verify this handler does not accidentally map 400/401/403 to 500 or mask predefined responses.
5. This code **intentionally omits printing throwable stack traces**. When production requires deep investigation, define a security policy and optionally use a logger overload accepting `Throwable` at the **single boundary**.
6. If an exception is handled by a filter before reaching MVC or by the servlet container after the response is committed, the advice may not receive it. Observe errors at the proper HTTP lifecycle boundaries.
7. Do not construct `errorId` from arbitrary request headers. The UUID is server-generated in the example to prevent users from injecting newlines or fake IDs into logs.
8. If tracing is enabled, log the validated trace ID from context to support cross-service investigation.

### 9.1. Safe Example with SLF4J 2.x

A concise structured log:

```java
// Integration snippet, logger is from SLF4J 2.x; variables
// must come from a controlled context and stable enum/error codes.
log.atError()
   .addKeyValue("event", "technical_error")
   .addKeyValue("operation", "order_read")
   .addKeyValue("error_code", "DEPENDENCY_UNAVAILABLE")
   .addKeyValue("dependency", "orders-db")
   .addKeyValue("request_id", safeRequestId)
   .log("Order read failed");
```

Not every backend/encoder will output key-value fields unless configured. `atError()` only sets the level; the API does not automatically sanitize sensitive data. When using MDC, clear/restore context per scope so one request does not carry data from another request on a thread pool.

### 9.2. Stack Traces: When and How?

With standard SLF4J, the backend can receive a throwable:

```java
// Integration snippet, run when Throwable has been evaluated as safe
// to emit to an internal sink; do not include in client responses.
logger.error("Dependency failed operation={} errorCode={}",
             "order_read", "DEPENDENCY_UNAVAILABLE", cause);
```

`cause` is the final throwable argument; a compatible backend will record the stack/cause. You must **evaluate the exception message content** and backend/encoder configuration before applying this to sensitive data. If raw exceptions contain secrets or payloads, prefer a safe error code, keep details in a controlled investigation channel, and do not assume masked stack traces are guaranteed by default.

## 10. Technical Errors in Messaging Applications and Scheduled Jobs

Non-REST boundaries have their own error policies:

- **Message consumer**: receives event, processes, commits business changes, acks/commits message; technical errors may cause broker redelivery. Log receipt/attempt and result separately, and do not log `PROCESSED` before the transaction commits.
- **Scheduled job**: a task failure should include job name, execution ID, attempt, timestamp, and status. Never leave an isolated exception without job identity.
- **Batch pipeline**: may partially succeed; log `PARTIAL_FAILURE` and reliable counts, rather than marking the entire batch `SUCCESS`.
- **Background executor**: exceptions may reside in a `Future` or reach `UncaughtExceptionHandler`; control who logs and who handles retry/cancellation.
- **Stream processing**: redeliveries and retries create multiple attempt-level logs; final outcome and idempotency must be tracked separately.

Example message flow:

```text
message_received eventId=evt-42 attempt=1
dependency_failed eventId=evt-42 attempt=1 retryable=true
retry_scheduled eventId=evt-42 attempt=1 delayMs=500
message_received eventId=evt-42 attempt=2
message_applied eventId=evt-42 attempt=2
ack_requested eventId=evt-42 attempt=2
```

Only **log `ack_confirmed` when the client/broker actually provides a confirmation mechanism**. `ack_requested` alone does not prove the broker acknowledged it. Do not retry money transfers or email sends without an idempotency key or reconciliation mechanism.

### 10.1. Distinguish "Message Fail" from "System Fail"

An unparseable message may be a **poison message**; endless retries usually will not help. A dependency timeout may be transient. An event already processed but redelivered by the broker may be a valid **duplicate delivery**, not a business technical failure.

Assign error codes and retry policies semantically; use a DLQ/quarantine where appropriate. **Do not log the entire payload** to prove a message failed; use event ID, schema version, a risk-assessed hash/fingerprint, and validation codes.

### 10.2. Do Not Swallow Interruption/Cancellation

For a waiting thread, `InterruptedException` is a critical control signal. If code decides not to rethrow it, it usually needs to restore the interrupt status so upper layers know about the cancellation:

```java
// Integration snippet, not a standalone program.
try {
    Thread.sleep(1000);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Exit or propagate the cancellation signal per the task's contract.
    return;
}
```

In async flows, `CancellationException` or client disconnects can be normal behavior. Do not log ERROR for every case. Do not catch `Throwable` and treat every condition—including `OutOfMemoryError` or `ThreadDeath`—as a retryable business error.

## 11. Retries, Backoff, Timeouts, Circuit Breakers, and Error Logging

Technical errors often trigger recovery mechanisms, but a flawed strategy can worsen an incident.

### 11.1. Retry Only When Safe

Questions to ask before retrying:
- Is the error **truly transient** or an auth/config/schema bug?
- Is the operation **idempotent** or backed by an idempotency key?
- Are there overall timeouts, max attempts, backoff, and jitter?
- If the request reached the dependency and the response was lost, is there a risk of **ambiguous success**?
- Could retries exceed the client deadline or worsen load on an overloaded dependency?
- Does each retry attempt emit heavy ERROR logs causing a log storm?

Do not write `catch(Exception e) { retryForever(); }`. A 401 auth error from a dependency will not disappear with infinite retries; a database timeout does not prove the transaction failed to commit.

### 11.2. Log by Attempt and Outcome

Example:

```text
attempt_failed operation=charge attempt=1 code=UPSTREAM_TIMEOUT
retry_requested operation=charge attempt=1 delayMs=250
attempt_failed operation=charge attempt=2 code=UPSTREAM_TIMEOUT
operation_failed operation=charge attempts=2 code=RETRY_EXHAUSTED
```

This is an illustrative log, **not advice to retry payments without idempotency**. When a retry succeeds, replace `operation_failed` with `SUCCESS recovered=true`. At the metrics level, you can count all attempts, while emitting an operation-level ERROR log only once at the responsible boundary.

### 11.3. Circuit Breakers Are Not "Catch and Stay Silent"

An OPEN circuit breaker proactively rejects dependency calls to shed load. This is a **control outcome**: log `dependency_circuit_open`/`short_circuited` with a stable code, rather than pretending the database just threw a timeout for that request. When the breaker changes state, `circuit_opened`/`circuit_closed` events have distinct observability value.

### 11.4. Successful Fallbacks Still Need Observability

If the primary path fails and a fallback succeeds, the final operation may be `SUCCESS` or `DEGRADED_SUCCESS`. Log `fallback_activated`/`degraded=true` and record metrics so operators know the system is relying on a backup path, without marking every final request as failed if the contract is still met.

## 12. Correlation, Tracing, and Distributed Errors Across Services

A technical error may propagate from service A -> B -> database. If every service logs a full stack trace for a single timeout, investigation becomes noisy. Use:
- `trace_id`/`span_id`: links operations in distributed tracing when available.
- `request_id`/`correlation_id`: request/workflow identifier, server-generated or format-validated.
- `service` and `operation`: log source and action.
- `dependency` and `error_code`: error grouping.
- `event_id`: identifies a single log event emission if ingestion deduplication is needed.

Correlation links "B reported a dependency timeout" with "A returned 503"; **do not sum those two logs as two independent failures when measuring failed requests**. Observability should separate request-level metrics from dependency-attempt-level metrics.

**MDC/ThreadContext** is useful for attaching request IDs, provided you:
1. Only store permitted metadata; never tokens, headers, bodies, or credentials.
2. Propagate context across async threads/pools using proper instrumentation; do not assume `ThreadLocal` automatically crosses executors.
3. Clear or restore `MDC` in `finally`/scope upon completion.
4. Do not trust raw correlation headers from clients without length/charset/trust validation.
5. Watch out for exceptions logged on another thread after the request context has closed.

Traces can also automatically capture exception messages and attributes, so they require security policies similar to logs. There is no point in avoiding printing a token to the console if it gets logged in a span event.

## 13. Performance and Reliability of Technical Error Logs

A degraded system sometimes generates **more logs than a healthy one**, creating error amplification:
- A dependency timeout causes thousands of requests to print long stack traces simultaneously.
- Encoders serialize exception causes/suppressed lists and large MDCs, spiking CPU/heap/GC.
- Full async queues cause drops or blocking; slow sync file/network appenders increase request p99 latency.
- A full log disk becomes a second failure; collectors keep retrying batches and increasing duplicates.
- A logger/appender failure triggers a handler that calls the same logger, risking recursion or a log storm.

Measure:
- Technical errors by `service/operation/error_code` (low-cardinality labels).
- Error rate, p95/p99 latency, retry count, dependency timeout rate.
- Logging queue size, dropped events, formatter/serialization cost, and bytes emitted.
- Disk/network pressure, retention, shipping failures, and shutdown flush duration.
- Recovery time and number of affected requests.

**Do not put `requestId`, full URLs, exception messages, or user IDs into metric labels** where cardinality is virtually unbounded. Keep IDs in logs/traces and use stable enums/groups for metric labels.

### 13.1. Logging Failures of the Logger Itself

If a file appender fails, calling `logger.error("appender failed", e)` through that same appender may fail to output or cause a loop. Use an independent status logger / internal diagnostic channel, rate limiting, and health metrics. Critical audits may require a dedicated durable sink rather than relying on a best-effort pipeline by default.

### 13.2. Integrity and Retention

Technical error logs can contain stack traces, hostnames, request IDs, and indirect personal data. Retain them only as long as necessary, enforce access control, encrypt them, and manage backups/exports. If the application requires mandatory audit evidence, design a durable recording mechanism (such as an outbox or transactional store); `logger.error` returning **is not a guarantee of durable storage**.

## 14. Testing Technical Error Logging

A good test suite should verify **error types**, **exception propagation paths**, **business outcomes**, and **log records at the sink**.

| Scenario | What to Verify |
| --- | --- |
| Input validation failure | Correct client error/response; no false technical ERROR |
| Business rule rejection | Stable business code; not alerted as an outage |
| Repository throws IOException | Cause preserved when wrapped; correct code and boundary |
| Dependency timeout before reaching target | Appropriate retry policy; does not assume commit |
| Timeout after sending write | Handles ambiguous outcome/idempotency; no blind replay |
| Retry succeeds | Attempt metrics recorded; final outcome is not FAILED |
| Retries exhausted | Single operation-level failure with standardized code |
| Unexpected RuntimeException | Logged once at boundary with lookup ID |
| Exception containing fake password/token | No secret emitted in message/JSON/stack/inspected collector |
| Exception with suppressed causes | Debug path preserves source details if needed |
| InterruptedException / cancellation | System respects cancellation; not mistaken for severe failure |
| Two layers logging | Same stack trace not duplicated unintentionally |
| Async logging queue full | Clear drop/block policy and metric |
| Broken appender | Diagnostics do not recurse back into the same appender |
| HTTP response already committed | Boundary does not attempt a second response or hide the error |
| Message consumer crashes before ack | Correct redelivery/idempotency; no fake ACK confirmed log |
| MDC across thread pool | Accurate correlation, context cleaned up, no cross-request leakage |
| Collector duplicates logs | Distinguishes duplicate ingestion from duplicate execution |

### 14.1. Testing Stdout/Handlers in Unit Tests

The Java 17 example in Section 6 used `CaptureHandler` to inspect messages. In real tests:
- Create an isolated logger for tests and disable parent handlers to avoid affecting other systems.
- Assert `event=technical_error` appears exactly once at the expected boundary.
- Assert valid error codes and correlation IDs; do not depend on raw exception messages.
- Use fake canary secrets to ensure none leak into **any field** of the event (message, MDC, structured keys, throwable renderer).
- Assert response codes and transaction outcomes independently of logs.
- Test the actual appender/collector if applicable, rather than stopping at captured text in unit tests.

### 14.2. Fault Injection

In staging, create controlled conditions:
1. Database connection pool exhaustion or bounded timeouts.
2. Dependencies returning 429/503 under different retry policies.
3. Clients closing connections mid-flight.
4. Workers being interrupted/cancelled.
5. Appenders/collectors temporarily unavailable.
6. Two concurrent requests triggering the same error.
7. Process restarts between DB commit and log/ack.

Observe log counts, error codes, latency, retries, transactions, and verify no sensitive data leaks. Never corrupt production log files or databases just to "test WARN/ERROR."

## 15. Common Mistakes

| Mistake | Why It Is Harmful | How to Fix |
| --- | --- | --- |
| Logging `ERROR` for every exception | Validation, business rejections, and cancellations can be normal | Classify by semantics/outcome |
| `logger.error(...)` then `throw` at every layer | Duplicate stack traces, skewed error rates | Establish clear logging boundaries |
| Wrapping with `new RuntimeException(e.getMessage())` | Loses cause and may leak secrets | `super(message, cause)` with safe error code |
| Catching `Exception` and returning success | Hides errors, corrupts state, prevents retries | Propagate/map per contract |
| Logging only `e.getMessage()` | Lacks root cause/type and context; may leak secrets | Safe error code, cause preservation |
| Logging full `request`/`body` with stack trace | Leaks PII/tokens, bloats log volume | Metadata/allowlist, controlled throwables |
| Returning stack traces to HTTP clients | Exposes paths, internal structure, secrets | Public error code + errorId |
| Using exception class as retry policy | Fails to distinguish committed vs. uncommitted timeouts | Retry based on idempotency and contract |
| Logging every retry as a final operation failure | Alert storms / false alarms | Separate attempt-level from final outcome |
| Using a single internal `INTERNAL_ERROR` code for everything | Difficult to classify and investigate | Systematic internal error codes |
| Relying on logs as proof of transaction commit | Logs can be lost or written before rollback | Use durable audit/outbox when mandatory |
| Assuming MDC automatically crosses all async tasks | Lost context or cross-thread data mixing | Propagate/cleanup per scope |
| Putting request IDs into metric labels | Extremely high cardinality | Keep IDs in logs/traces; use stable metric labels |
| Catching `Throwable` and retrying `Error` | Masks severe JVM/lifecycle failures | Catch per contract; do not swallow errors |
| Failing to restore interrupt status | Loses cancellation signal, stalls shutdown | `Thread.currentThread().interrupt()` |
| Logging appender errors via the same appender | Recursion / log storm / lost diagnostics | Independent status channel |
| Looking only at exception messages | Misses operation, dependency, customer impact | Structured fields and correlation |

## 16. Self-Check Exercises

**Question 1 — Business or technical?** An API receives a valid request, but the customer has insufficient balance. Is this a `technical_error` requiring a SEVERE alert?

**Answer:** Usually **no**. This is an expected business rejection; return the contract result code and log INFO/audit as needed. If the balance calculation system failed due to a database error, however, that is a technical error.

**Question 2 — Logged twice?** A repository calls `logger.error("read failed", e)` and throws; the service also calls the logger and rethrows; the HTTP handler logs the stack trace. Does a high count of ERROR lines prove three independent incidents?

**Answer:** **No**. All three may describe a single failure. Choose one boundary to own the final log and preserve cause/context across layers.

**Question 3 — Retrying a database timeout.** An order creation request was sent, but no response was received. Can you immediately retry indefinitely because the error is a `TimeoutException`?

**Answer:** **No**. You must consider whether the operation may have committed, idempotency keys, deadlines, retry budgets, backoff, and reconciliation. Exception class alone does not determine whether a retry is safe.

**Question 4 — Cause preservation.** Why is `throw new RuntimeException(e.getMessage())` worse than `throw new TechnicalFault("DEPENDENCY_UNAVAILABLE", e)`?

**Answer:** The first version loses the cause chain and may copy sensitive data from the raw message. The second version preserves the cause for investigation and uses a stable error code.

**Question 5 — Secrets in exceptions.** A library throws `IOException("url?api_key=secret")`. What are the risks of returning `e.getMessage()` to the client or logging it unchecked?

**Answer:** It can expose credentials to clients, log viewers, or collectors. Use safe error codes, dependency aliases, and error IDs; control where stack traces are stored based on permissions and policy.

**Question 6 — Interruption.** A worker catches `InterruptedException` without rethrowing or restoring the interrupt status. What can go wrong?

**Answer:** Upper layers may lose the cancellation signal, tasks may keep running, or shutdown may stall. If not propagating the exception, usually restore the interrupt status and exit according to contract.

**Question 7 — Outcome.** A dependency fails on the first attempt, but the second retry attempt succeeds. Should you log `operation_failed` for the request?

**Answer:** No, if the final outcome is success. You can log `attempt_failed`, `retry_scheduled`, and `operation_completed recovered=true`, alongside retry metrics.

## 17. Production Checklist for Technical Error Logs

Before shipping exception logging to production, verify:

1. **Clear taxonomy**: validation, business, authn/authz, transient/permanent technical, unexpected defect, cancellation.
2. **Semantically sound exception propagation**: preserve `cause`, do not mask errors as success, do not catch overly broadly.
3. **Defined logging boundaries** for HTTP, message consumers, and jobs/executors; do not log the same stack trace across multiple layers.
4. **Schema includes event/error code/operation/outcome/request ID**, plus dependency and service where needed; do not cram all context into free-form messages.
5. **Log levels reflect final outcomes and impact**, distinguishing attempt-level from operation-level events.
6. **Retries have idempotency, timeouts, backoff, and limits**, handling cases where dependency commit status is uncertain.
7. **Client responses are safe**, returning no stack traces, SQL, tokens, or detailed infrastructure errors.
8. **Throwable logging is reviewed**, covering messages, causes, suppressed exceptions, MDC, structured fields, and secondary sinks.
9. **Correlation works across async/distributed boundaries**; MDC/context is cleaned up; IDs are not blindly accepted from clients.
10. **Metrics/alerts use low-cardinality labels**, tracking error rates, retries, queue depth, log loss, and dependency health.
11. **Simulated fault tests** cover success/reject/timeout/bug/cancel/recovery paths and include canary secret tests.
12. **Access control, retention, backups, and audit logs** are protected per policy; do not treat standard loggers as transactional audit stores.
13. **No logging recursion** when appenders fail; maintain an independent internal status/health diagnostic channel.
14. **Incident response process exists** for credentials/PII accidentally emitted in exception logs.

**Conclusion:** Effective technical error logging is not about printing as many stack traces as possible. **Distinguish technical errors from business outcomes**, preserve exception causes properly, emit a structured diagnostic event at the appropriate boundary, and use correlation IDs to connect traces. Combining retry/idempotency discipline, log security, metrics, and realistic fault testing keeps Java systems easy to investigate while avoiding log duplication, data leaks, and incident amplification.
