# Error Codes in Java Core Logging and Exception Handling

## 1. What Is an Error Code?

An **error code** is a structured, stable identifier for an **error type** that an application knows how to classify. When logs only contain `"Request failed"` or `"An error occurred"`, operators have to investigate by reading messages, stack traces, Java classes, or writing fragile regex queries. By adding a standardized `errorCode`, applications and monitoring systems can search, aggregate, distinguish, and correlate each group of errors independently of the message language.

Example:

~~~text
2026-11-10T03:00:00Z ERROR event=payment_failed errorCode=PAY-TIMEOUT requestId=req-101 retryable=true
2026-11-10T03:00:02Z ERROR event=payment_failed errorCode=PAY-TIMEOUT requestId=req-204 retryable=true
2026-11-10T03:00:04Z WARN  event=order_rejected errorCode=ORD-STATE-CONFLICT requestId=req-205 retryable=false
~~~

The first two lines share the same **error type** but belong to **different requests**. The code `PAY-TIMEOUT` is not a unique identifier for a single occurrence. Nor does every error with the same code need to emit multiple ERROR logs during a retry: that is a logging policy decision.

Concrete benefits:

- Query logs and build dashboards by `errorCode` instead of parsing `Throwable.getMessage()` strings.
- Link to runbooks, owning teams, severity/priority, and remediation guidance.
- Distinguish invalid user input, rejected business operations, dependency failures, and unknown bugs.
- Maintain an error contract for clients when refactoring code or translating messages into other languages.
- Allow support teams to receive a `requestId` or `errorOccurrenceId` and look up the error type in authorized internal logs.
- Enable low-cardinality metric aggregation if codes are governed as a **finite set**.

Do not generate error codes by hashing exception messages, concatenating userId/orderId, picking random method/frame names, or using a bare `UUID.randomUUID()`. Those values either change per request or fail to represent the **type** of error.

## 2. Related Concepts That Must Be Kept Separate

| Field | Purpose | Example | Characteristics |
| --- | --- | --- | --- |
| `errorCode` | Error type in the application's taxonomy | `ORD-NOT-FOUND` | Kept stable for the same situation |
| `exceptionClass` | Java object type thrown | `IllegalStateException` | May change due to refactoring |
| `message` | Human-readable message | `Order not found` | Can be translated or reworded |
| `httpStatus` | HTTP result at the API boundary | `404`, `409`, `503` | Reflects protocol, insufficient to express domain semantics |
| `logLevel` | Logging attention level | `WARN`, `ERROR` | Chosen based on operational value |
| `retryable` | Hint by error/operation type | `true` | Does not guarantee that retrying side effects is safe |
| `requestId` | A single incoming request/correlation | `req-101` | Multiple events can share the same request |
| `traceId` / `spanId` | Distributed tracing | trace/span ID | Not an error or an idempotency key |
| `errorOccurrenceId` | A specific error occurrence | `err-00042` | Different for each occurrence when a contract exists |
| `eventId` | A single emitted log event | `logevt-005` | Used to detect duplicate ingestion if preserved |

In a system, `ORD-NOT-FOUND` may occur millions of times yet remain **a single error type**. If each occurrence ID were used as an errorCode, the metric `errors_total{error_code=...}` would create a new label per request, causing high cardinality. If `requestId` were used instead of `errorCode`, you could not aggregate by root cause.

**An error code is not synonymous with an HTTP status.** HTTP 409 Conflict can correspond to an order state conflict, a version conflict, or an idempotency key conflict; each of these requires different handling. **An error code is also not synonymous with a log level.** A 404 may be a normal outcome that only needs INFO, whereas an unexpected 500 typically needs ERROR and a stack trace in an internal sink.

## 3. Designing a Meaningful and Stable Taxonomy

An error code catalog should have a clear scope (service, domain, or API), an owner, and change rules. Example:

| Illustrative Error Code | Meaning | Reference HTTP | Reference Severity | Retry? |
| --- | --- | --- | --- | --- |
| `REQ-VALIDATION-001` | Request does not satisfy schema/contract | 400/422 depending on semantics | INFO/WARN | No if input is unchanged |
| `ORD-NOT-FOUND` | Order does not exist / is not visible per policy | 404 | INFO/WARN | Usually no |
| `ORD-STATE-CONFLICT` | State/version does not allow the operation | 409 | WARN | Need to read fresh state |
| `AUTH-FORBIDDEN` | Principal is not authorized for the operation | 403 | WARN/audit | No if permissions are unchanged |
| `PAY-TIMEOUT` | Payment dependency timed out | 503/504 depending on layer | WARN/ERROR | Must check idempotency |
| `DB-UNAVAILABLE` | Data backend temporarily unavailable | 503/500 depending on boundary | ERROR | Conditional |
| `SYS-UNEXPECTED` | Unrecognized error / bug | 500 | ERROR | Not by default |

These are **codes defined for this lesson**, not a standard mandated by Java, HTTP, or any framework. Each product may use `E_ORDER_NOT_FOUND` or `ORD-0042`, as long as the contract is applied consistently.

Naming and design rules:

1. **Name by semantics, not implementation details.** `PAY-TIMEOUT` is not `SocketTimeoutException#34`; switching HTTP libraries should not require changing the public code.
2. **Never reuse an old code for a new meaning.** If semantics are no longer compatible, add a new code, version it, or deprecate it with a migration path.
3. **Never change a code when changing messages or translating languages.** API clients and dashboards may rely on the code; messages are for display.
4. **Distinguish different actions.** A permanent validation error and a transient dependency timeout should not share `GENERAL_ERROR` if they require different retry policies.
5. **Do not encode dynamic data into the code.** Order ID, tenant ID, hostname, email, and port belong in separate, controlled fields.
6. **Do not turn every Exception class into an error code.** Low-level exceptions such as `IllegalArgumentException` can also come from programming bugs, not always from bad requests.
7. **Have a safe fallback code** such as `SYS-UNEXPECTED`, but monitor the fallback rate to evolve the catalog when real needs arise.
8. **Maintain clear namespaces/ownership** if multiple services share a catalog. Avoid having two domains use the same code with conflicting meanings.

### What Should a Catalog Contain?

For each code, document the specific trigger description, cases where the code must not be applied, ownership/team, log example, response policy, retryability, severity, public-safe title, runbook link, version, and deprecation date if applicable. Contract tests should be in place to prevent breaking changes or deletions.

A small service can declare an enum, while a large system may use a shared catalog/schema. Do not force domain logic to depend directly on an HTTP enum or a Logback class just for sharing: transport mapping can live in an adapter.

## 4. Exception Classes, Root Causes, and Handling Boundaries

Java exception flow can span multiple layers:

~~~text
HTTP controller / message consumer
          |
          v
Application service
          |
          +--> Domain check -> DomainException(ORD-STATE-CONFLICT)
          |
          +--> Payment adapter -> IOException / timeout
                                   classified as PAY-TIMEOUT
~~~

The domain layer raises business situations or returns a `Result`-style type; adapters translate technical dependency errors into meaningful error codes; boundaries decide log severity, HTTP responses, or retry/DLQ behavior.

Domain example:

~~~java
// Illustrative snippet: a custom DomainException class for the application.
public final class DomainException extends RuntimeException {
    private final String errorCode;

    public DomainException(String errorCode, String safeMessage,
                           Throwable cause) {
        super(safeMessage, cause);
        this.errorCode = errorCode;
    }

    public String errorCode() {
        return errorCode;
    }
}
~~~

Accepting a `String` here illustrates the idea, but production code should use a **catalog/enum** to prevent callers from inventing arbitrary codes. Preserving the root cause via `cause` helps investigation, though it does not mean every message/stack trace may be written verbatim to every sink: exceptions can contain SQL, URL queries, access tokens, or PII.

**Do not map using exception text:**

~~~java
// Avoid: the message can change depending on language, dependency, or data.
if (exception.getMessage().contains("not found")) {
    code = "ORD-NOT-FOUND";
}
~~~

If an exception is already designed with a stable type and code, map by that type. For third-party libraries, an adapter can map using **typed exceptions + documented state/protocol**; if there is insufficient evidence, fall back safely.

### Handling Wrapped Exceptions in Async Code

`CompletionException`, `ExecutionException`, and some framework-generated wrappers can carry a `getCause()`. If the cause is a classified domain exception, its code can be preserved. However, walking the entire cause chain looking for an `IllegalArgumentException` is wrong: programming bugs inside libraries can also throw that exception type.

When handling `InterruptedException`, preserve cancellation/interruption semantics; if caught for cleanup in Java, consider calling `Thread.currentThread().interrupt()` where appropriate. Do not use `catch (Throwable)` to swallow everything and continue as normal; an `Error` like `OutOfMemoryError` is not domain validation.

## 5. Complete Java 17 Example: Classifying Exceptions and Logging Error Codes

This program uses **JDK 17 only**. It defines an error code enum, searches for a coded exception in the cause chain, selects the corresponding `httpStatus`/`retryable`/JUL level, and emits an event via `java.util.logging`.

Save **`ErrorCodeDemo.java`**:

~~~java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import java.util.concurrent.CompletionException;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ErrorCodeDemo {
    enum ErrorCode {
        INPUT_INVALID("REQ-VALIDATION-001", Level.WARNING, 400, false),
        ORDER_NOT_FOUND("ORD-NOT-FOUND", Level.INFO, 404, false),
        PAYMENT_TIMEOUT("PAY-TIMEOUT", Level.SEVERE, 503, true),
        UNEXPECTED("SYS-UNEXPECTED", Level.SEVERE, 500, false);

        final String value;
        final Level level;
        final int httpStatus;
        final boolean retryable;

        ErrorCode(String value, Level level, int httpStatus,
                  boolean retryable) {
            this.value = value;
            this.level = level;
            this.httpStatus = httpStatus;
            this.retryable = retryable;
        }
    }

    static final class AppException extends RuntimeException {
        final ErrorCode errorCode;

        AppException(ErrorCode errorCode, Throwable cause) {
            super(errorCode.name(), cause);
            this.errorCode = errorCode;
        }
    }

    static ErrorCode classify(Throwable error) {
        Set<Throwable> visited =
                Collections.newSetFromMap(new IdentityHashMap<>());

        for (Throwable current = error;
             current != null && visited.add(current);
             current = current.getCause()) {

            if (current instanceof AppException app) {
                return app.errorCode;
            }
        }

        return ErrorCode.UNEXPECTED;
    }

    static void logFailure(Logger log, String requestId,
                           Throwable error) {
        ErrorCode code = classify(error);
        LogRecord record = new LogRecord(
                code.level,
                "event=request_failed errorCode=" + code.value
                + " requestId=" + requestId
                + " retryable=" + code.retryable
                + " httpStatus=" + code.httpStatus);

        record.setLoggerName(log.getName());
        record.setThrown(error);
        log.log(record);
    }

    static final class MessageOnlyHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                System.out.println(record.getMessage());
            }
        }

        @Override
        public void flush() {
            // No separate buffered I/O.
        }

        @Override
        public void close() {
            // Holds no external resources.
        }
    }

    public static void main(String[] args) {
        Logger log = Logger.getLogger("demo.error.codes");
        log.setUseParentHandlers(false);
        log.setLevel(Level.ALL);

        MessageOnlyHandler sink = new MessageOnlyHandler();
        sink.setLevel(Level.ALL);
        log.addHandler(sink);

        try {
            logFailure(log, "req-100",
                    new AppException(ErrorCode.INPUT_INVALID, null));
            logFailure(log, "req-101",
                    new CompletionException(
                        new AppException(
                            ErrorCode.PAYMENT_TIMEOUT,
                            new IllegalStateException("gateway timeout"))));
            logFailure(log, "req-102",
                    new IllegalStateException("unexpected condition"));
        } finally {
            log.removeHandler(sink);
            sink.close();
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 ErrorCodeDemo.java
java ErrorCodeDemo
~~~

**Deterministic stdout** (equivalent logic verified with JShell, using Java 17 APIs only):

~~~text
event=request_failed errorCode=REQ-VALIDATION-001 requestId=req-100 retryable=false httpStatus=400
event=request_failed errorCode=PAY-TIMEOUT requestId=req-101 retryable=true httpStatus=503
event=request_failed errorCode=SYS-UNEXPECTED requestId=req-102 retryable=false httpStatus=500
~~~

Explanation:

1. `ErrorCode` is a small catalog for this lesson. `Level.WARNING` and `Level.SEVERE` belong to JUL, corresponding roughly to common WARN/ERROR log meanings, though they are not Logback/SLF4J enums.
2. `AppException` carries an explicit application-known code. `classify(...)` only extracts the first `AppException` in the cause chain rather than guessing from an unstable message string.
3. `IdentityHashMap` backed by an identity-based `Set` stops traversal if an unusual cyclic cause chain is encountered. The common case remains an acyclic chain.
4. `CompletionException` wrapping `PAY-TIMEOUT` preserves the code. An unknown `IllegalStateException` resolves to `SYS-UNEXPECTED`.
5. `LogRecord` holds `level`, `message`, and `thrown`. The demo handler intentionally prints only the message so stdout is deterministic; a real handler may print stack traces and requires a redaction policy.
6. `setUseParentHandlers(false)` prevents the root logger from emitting an extra record and duplicating output.
7. `httpStatus` is metadata for the demo only; the program **does not return an HTTP response**, and `retryable=true` does not trigger a retry. In multi-transport applications, keep HTTP mappers separate from domain enums.

**Limitations:** this example demonstrates policy without network requests and does not test SQL/HTTP or exception messages containing PII. Do not copy raw throwable logging directly to public sinks. `requestId` must be generated/validated and character-bounded at real boundaries.

## 6. Structured Logging: Writing Codes as Queryable Fields

In real systems, use structured JSON logging or an encoder with fixed fields:

~~~json
{
  "timestamp": "2026-11-10T03:15:00Z",
  "level": "ERROR",
  "service": "checkout",
  "event": "payment_failed",
  "errorCode": "PAY-TIMEOUT",
  "errorCategory": "dependency",
  "requestId": "req-101",
  "traceId": "4f0e2c13b69a497389d74e71a52b4e62",
  "retryable": true,
  "attempt": 3,
  "outcome": "failed",
  "durationMs": 4100
}
~~~

This is illustrative JSON, not the output of `ErrorCodeDemo`. The `traceId` field uses a placeholder value; real values must come from a managed tracing context. Do not put full request bodies, passwords, auth headers, or uncontrolled stack traces into JSON logs.

A stable field set typically includes:

- `event`: log event type such as `payment_failed`.
- `errorCode`: standardized error type; never the raw exception message.
- `errorCategory`: grouping such as `validation`/`domain`/`dependency`/`unexpected` when helpful.
- `requestId`, `traceId`: correlation, not error taxonomy.
- `attempt`, `outcome`: distinguish transient errors during retries from final failure.
- `service`/`instance`/`version`: locate the emitting component.
- `exceptionType` or stack trace in a protected internal sink when needed.
- `httpStatus` only when the event has an HTTP context; do not force it onto every job/consumer.

**Do not build dashboards by regex-parsing message text when independent fields can be emitted.** Changing message wording should not break metrics grouped by `errorCode`.

### SLF4J Parameterized Logging

SLF4J snippet example (**requires a dependency/backend, not JDK-only**):

~~~java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(PaymentService.class);

void reportFailure(String requestId, String errorCode,
                   Throwable cause) {
    LOG.error("event=payment_failed errorCode={} requestId={}",
            errorCode, requestId, cause);
}
~~~

`PaymentService` is an application class and is not included in the snippet. With SLF4J, passing a throwable as the final varargs argument allows the backend to record the stack trace. Do not manually convert `cause` to a string and also pass the throwable, which results in duplicate stack traces.

SLF4J 2.x supports a fluent key–value API:

~~~java
LOG.atError()
   .addKeyValue("event", "payment_failed")
   .addKeyValue("errorCode", errorCode)
   .addKeyValue("requestId", requestId)
   .setCause(cause)
   .log("Payment failed");
~~~

This snippet also requires SLF4J 2.x and a compatible backend. Having key–value calls in the API does not automatically guarantee JSON output: a supporting encoder/layout and integration tests against the actual runtime are required.

## 7. HTTP APIs: Error Codes and RFC 9457 Problem Details

For HTTP, **Problem Details** under RFC 9457 defines the `application/problem+json` format with fields such as `type`, `title`, `status`, `detail`, and `instance`. Applications can add `errorCode` and `requestId` as **extension members**.

Illustrative response:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "The requested order was not found.",
  "instance": "/problems/occurrences/err-24",
  "errorCode": "ORD-NOT-FOUND",
  "requestId": "req-101"
}
~~~

`api.example.com` and the IDs above are sample data. **Under RFC 9457, `type` is the primary identifier of the problem type**; `errorCode` is an application-specific extension and does not replace `type`. `instance` identifies a single occurrence, not a taxonomy code.

Key rules:

- `status` in the body must match the HTTP response status generated by the origin server. Never put 404 in JSON when the actual response is 500.
- `title` summarizes the problem type; `detail` helps the client understand/fix the request and must **not** contain stack traces, SQL, passwords, or internal hostnames.
- `type` must be stable if clients branch on it and may link to documentation. Clients should not blindly dereference untrusted URIs.
- `instance` must not contain sensitive identifying data. If accepting `requestId` for support, restrict lookup permissions to avoid exposing other users' logs.
- `errorCode`, when added, must have its own versioning/stability contract; do not expose internal codes that reveal infrastructure topology unless authorized.
- `Retry-After` can be useful in appropriate cases; retries must still account for idempotency, budgets, and side-effect state.
- RFC 9457 **obsoletes RFC 7807**. APIs with an existing error format can keep using it if governed stably; there is no need to switch solely to add a code.

### Example HTTP Mapping Without Mixing Layers

| Application Error | Code | Sample Contract Status | Meaning for Client |
| --- | --- | --- | --- |
| Invalid input data | `REQ-VALIDATION-001` | 400 | Fix the request |
| Order not found | `ORD-NOT-FOUND` | 404 | Check accessible ID/state |
| Order version conflict | `ORD-STATE-CONFLICT` | 409 | Re-read state and resolve conflict |
| Principal lacks permission | `AUTH-FORBIDDEN` | 403 | Request appropriate permission |
| Dependency temporarily unavailable | `PAY-TIMEOUT` | 503 in sample | Retry with control if safe |
| Unexpected bug | `SYS-UNEXPECTED` | 500 | Contact support with requestId |

An upstream timeout may be returned as 504 by a gateway in some architectures; do not treat `PAY-TIMEOUT` as universally 503 across all transports. HTTP status should be decided by the outermost adapter according to RFC 9110 and the application contract.

## 8. Error Codes in Message Consumers, Jobs, and Async Tasks

For message brokers or batch jobs, HTTP status codes usually **do not exist**. Error codes help select the handling policy:

~~~text
Consume message / run job
       |
       v
Validate context + process
       |
       +-- Success -> ACK/commit/outcome success
       |
       +-- Transient failure -> retry with limit/backoff
       |
       +-- Permanent failure -> reject/DLQ per policy
       |
       +-- Unknown failure -> alert and handle safely
~~~

A log entry might look like:

~~~json
{
  "event": "message_processing_failed",
  "messageId": "msg-1001",
  "consumer": "billing-worker",
  "errorCode": "PAY-TIMEOUT",
  "retryable": true,
  "attempt": 2,
  "action": "retry_scheduled",
  "correlationId": "flow-42"
}
~~~

The same message may be redelivered after an uncertain ACK/commit; do not use `errorCode` in place of `messageId` or `idempotencyKey`. A code may appear on each attempt, but **final failure metrics** should count operation outcomes rather than simply counting every ERROR line.

Distinguish:

- **Temporary:** timeouts/dependency unavailability; retry with backoff, limits, and checks for existing side effects.
- **Permanent:** invalid data, unsupported schema, unauthorized resource/permission; route to DLQ, quarantine, or reject per policy.
- **Unknown:** uncataloged exception; log diagnostics to a protected sink, alert, and avoid infinite retries.
- **Cancellation/interrupt:** do not treat as a business error by default. Respect task-stopping contracts.

When moving messages to a DLQ, you can keep `originalMessageId`, `failureCode`, `attempts`, `firstFailureAt`, `lastFailureAt`, source/destination, and a safe summary. Do not copy raw stack traces or secrets into headers just to "preserve the cause" without access controls.

## 9. Retryable Does Not Mean Every Operation Can Be Retried

`retryable` should be treated as a **hint**. Whether a retry is safe depends on the operation:

| Error Code | Typical Handling | Risk of Blind Retries |
| --- | --- | --- |
| `REQ-VALIDATION-001` | Fix input | Creates spam, will never succeed |
| `ORD-NOT-FOUND` | Verify ID/state per contract | Pointless load increase |
| `ORD-STATE-CONFLICT` | Read fresh state, resolve conflict | Update race conditions |
| `AUTH-FORBIDDEN` | Verify permissions, no auto-retry | Permission probing or rate-limiting |
| `PAY-TIMEOUT` | Check charge status and idempotency key | Double charging |
| `DB-UNAVAILABLE` | Backoff + deadline, circuit breaker | Retry storm while DB is overloaded |
| `SYS-UNEXPECTED` | Investigate/alert; no default retry | Hiding bugs, repeating side effects |

If a POST request committed but the response was lost, a client timeout does not prove failure. Check the idempotency key or business state before retrying. In HTTP, `Retry-After` can provide a reasonable wait time. In message consumers, retry topics, dead-letter queues, ACKs, and side effects need their own contract.

Do not fold `attempt=2` into `errorCode` as `PAY-TIMEOUT-ATTEMPT-2`; `attempt` must be a separate field. Also do not use `errorCode` as an idempotency key because different operations can share the same code.

## 10. Avoiding Duplicate Logs and Choosing Meaningful Log Levels

An exception can travel from a repository up through a service to an HTTP handler. If every layer does:

~~~java
catch (Exception ex) {
    log.error("failed", ex);
    throw ex;
}
~~~

then a single failure generates multiple stack traces and duplicate alerts. The code above is only a snippet inside a `try` block with an appropriate logger. Error codes help group events, but **they do not automatically eliminate duplicates**.

Design clear responsibilities:

1. **Domain/adapter:** create a classified exception preserving the cause, optionally attaching safe metadata.
2. **Service:** log only when a new event occurs (fallback invoked, retry scheduled, business compensation); do not unconditionally log full stack traces and rethrow.
3. **Final boundary:** decide the response/retry and emit the single required failure outcome record with `errorCode`, `requestId`, and `outcome`.
4. **Logging backend:** prevent child and root appenders from writing the same event twice due to additivity; integration-test the record count at the sink.
5. **Metrics:** count operation/request failures by outcome, not by the number of stack traces printed.

A 400 validation error may be logged at INFO/WARN depending on expected behavior; a 404 is not a severe server incident by default. Reserve ERROR for significant unhandled/unrecovered failures. Do not raise the level to ERROR for every code just because it has "error" in its name.

## 11. Context and MDC: Avoiding Error Code Leakage Across Requests

SLF4J MDC binds metadata to the **current thread**. When using MDC for `requestId`/`traceId`, always clean up in `finally` so request B does not inherit request A's `requestId`. Keeping `errorCode` as a field on the **event** is usually better than keeping it in MDC for the whole request: if you put `errorCode` into MDC after a failure and forget to clear it, subsequent successful events may carry the stale error code.

Illustrative scoped MDC example (requires SLF4J, not a pure JDK program):

~~~java
import java.util.Map;
import org.slf4j.MDC;

Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("requestId", requestId);
    processRequest();
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
~~~

`requestId` and `processRequest()` belong to the application. When using `ExecutorService` or `CompletableFuture`, context may not propagate automatically to worker threads; capture a snapshot at submission time and restore/clean up at the boundary, rather than reading the async writer thread's MDC instead of the context from when the event was created.

Avoid placing secrets in MDC: any appender or encoder can output those fields. A formatter rendering `%X{requestId}` does not sanitize input automatically.

## 12. Security: Public Codes and Internal Causes Are Not the Same

Technical errors can contain SQL, hostnames, URL queries, tokens, cookies, and personal data. **Never expose raw exception messages or stack traces in public responses**, even when `errorCode` is properly set.

What not to do:

~~~text
errorCode=SQL_ERROR_FOR_john@example.com
message=Connect failed with Authorization: Bearer <secret>
~~~

This is fabricated bad-format sample data, not real data. Error codes must come from an approved catalog, never from user input, and must not contain userId, email, or tokens.

Separate clearly:

- **Public error:** stable public code (`SYS-UNEXPECTED`), safe message, controlled `requestId`/`occurrenceId`.
- **Internal log:** code, event, dependency, exception type, permitted stack trace, necessary business context, and redaction applied.
- **Audit/security log:** access events, permission denials, or privilege changes under retention/access policies; separate from regular diagnostic logs.
- **Monitoring:** metrics by code/category, excluding `userId` or dynamic URLs as labels.

Watch out for **user enumeration**: in password-reset or login flows, returning distinct codes for "email exists" versus "email does not exist" can leak account existence; depending on the threat model, a unified public response may be required while internal audit logs record distinct codes.

Sanitize newline and control characters from input before logging to reduce log injection risk. Parameterized logging helps with formatting, but **does not automatically encrypt or mask PII**. Protect logs with ACL/RBAC, retention policies, encryption, access auditing, and data minimization.

## 13. Monitoring with Error Codes and Bounding Cardinality

Finite error codes work well as metric labels:

~~~text
requests_failed_total{service="checkout",error_code="PAY-TIMEOUT",route="/orders"}
requests_failed_total{service="checkout",error_code="ORD-STATE-CONFLICT",route="/orders"}
~~~

This is a Prometheus text-format example, **not a metric emitted by the Java demo**.

Never put `requestId`, `errorOccurrenceId`, `userId`, `messageId`, exception messages, or paths containing dynamic IDs into metric labels. Those values cause massive cardinality explosions and drive up time-series storage costs. Keep them in indexed logs/traces with appropriate retention instead.

Useful dashboards can show:

- Top error codes by count and growth rate.
- `PAY-TIMEOUT` rate by dependency and deployment.
- Unclassified `SYS-UNEXPECTED` errors and appearances of new codes.
- **Final** failed operation rate, separate from retry attempt counts.
- Links to runbooks and log queries filtered by code/service/time, then drilling down to a specific `requestId`.

Note that an operation might retry three times and then succeed; if a metric counts "number of ERROR lines," the system would report three failures even though the final outcome was success. Define denominators and outcome events clearly.

## 14. Testing Error Codes as an API Contract

| Scenario | Expectation |
| --- | --- |
| Classified domain exception | Preserves exact code and meaning |
| `CompletionException` wrapping domain exception | Does not lose the inner code |
| Unknown exception | Fallback code `SYS-UNEXPECTED`, safe response |
| Two requests with the same error type | Same `errorCode`, different `requestId` |
| Two retries and final failure | Clear `attempt` and `outcome`; do not count the operation multiple times |
| Normal 404/400 | Not forced to log ERROR or stack trace |
| HTTP Problem Details | Body `status` matches HTTP status; `type`/`errorCode` remain stable |
| Message wording changes | Contract test confirms code does not change |
| Security exception containing secrets | Not leaked in public responses or unauthorized sinks |
| Async/thread pool | MDC is cleaned up properly, `requestId` does not leak |
| Logback/SLF4J structured output | JSON field `errorCode` is actually emitted, not just mocked |
| Metrics | `error_code` label belongs to the finite catalog |
| Deprecated code | Has version/alias/migration plan, not reused with another meaning |

Taxonomy testing: use an enum or catalog config to verify there are no empty or duplicate codes, naming patterns are followed, and each code has an owner/response mapping/runbook per policy. For public APIs, snapshot/contract tests catch accidental refactors that change a code and break client branching.

Test logging at the **receiving appender/handler**, not just by mocking `logger.error`. With JUL, inspect `LogRecord.getMessage()`, `getThrown()`, and `getLevel()`; with SLF4J/Logback, use a real encoder to verify key–value pairs are emitted properly. In async pipelines, test propagation, buffering, and shutdown.

## 15. Common Pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Deriving code from exception message | Changes by user/dependency; may leak secrets | Map to a finite catalog |
| Using Java class name as code | Refactoring breaks client contracts | Implementation-independent business codes |
| Single `ERROR_UNKNOWN` code for everything | No clear investigation signal | Dedicated codes for actionable failures |
| Generating a new UUID per error | Cardinality explosion, impossible to aggregate | UUID for occurrence, code for type |
| Equating code with HTTP status | Multiple errors share 409/503 but need different handling | Separate fields and mappers |
| Equating code with log level | Normal 404 becomes noisy ERROR | Choose level by impact/policy |
| Mapping every IllegalArgumentException to 400 | Programming bugs masked as client errors | Map only typed domain exceptions |
| Retrying every code containing TIMEOUT | Duplicate charges/updates or retry storms | Idempotency + budget + side-effect state |
| Logging exception at every layer and rethrowing | Duplicate stack traces and alerts | Boundary logging ownership |
| Copying Throwable message into response | Leaks SQL, tokens, hosts, PII | Public-safe message + redaction |
| Using code as idempotency key | Different operations get conflated | Per-operation key |
| Changing code meaning without versioning | Clients and dashboards misbehave | Versioning/deprecation/aliases |
| Enabling SLF4J fluent API and assuming JSON | Key–value fields may not be printed by encoder | Backend/layout integration tests |

## 16. Implementation Checklist

1. Define the purpose of error codes (clients, support, observability, retries, runbooks).
2. Create a taxonomy with owners, stable codes, descriptions, and compatibility policies.
3. Separate `errorCode` from exception class, HTTP/gRPC status, log level, `requestId`, and `occurrenceId`.
4. Classify at the domain/adapter level; map at the boundary, preserving causes without leaking sensitive data.
5. Emit structured fields with `event`, `errorCode`, `requestId`/`traceId`, `attempt`, and `outcome` where appropriate.
6. Assign one boundary responsible for logging the final failure; log retries as separate events.
7. Choose retry policies by operation and idempotency, not by code alone.
8. Control public responses, log data, RBAC/retention, and user enumeration risks.
9. Test contracts, cause wrappers, fallbacks, formatters, metric cardinality, and async context.
10. Use finite codes in metrics; use `requestId` in logs/traces to investigate occurrences.

**Remember:** An error code is a meaningful, stable name for an **error type**. The exception class is a Java detail, the HTTP status is a protocol result, the log level is an attention signal, and `requestId`/`traceId`/`occurrenceId` trace a **specific occurrence**. Do not mix these roles, do not generate codes from dynamic text, and do not use error codes as a substitute for idempotency or security.

### Official References

- IETF — [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html), [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html).
- Java SE 17 — [Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html), [CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html), [java.util.logging.LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html).
- SLF4J — [Manual](https://www.slf4j.org/manual.html), [MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html).
- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html).
