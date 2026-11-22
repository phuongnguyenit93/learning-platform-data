# Business Errors in Java: Classifying Exceptions and Logging with Business Semantics

## 1. What is a business error?

A **business error** (domain rule error) is a case where a request **cannot be completed according to defined business rules**, even though the application and infrastructure may still be operating normally. Examples:

- A customer orders a product quantity exceeding available inventory.
- An order has already been shipped and therefore cannot be cancelled.
- Insufficient balance to perform a funds transfer.
- A discount code has expired or does not apply to the current cart.
- A user does not have permission to perform a sensitive operation.
- An idempotent operation is resent when the state already matches the requested outcome.

Not every failure is a technical "exceptional failure". The application may be **correct** in rejecting the request. In Java code, a business error can be represented by a typed exception, a `Result`/`Either` type, or a validation result—the choice depends on architecture, frequency, and API design.

Example:

```text
Request: Cancel order O-100
Condition: Order is already SHIPPED
Result: REJECTED, reasonCode=ORDER_ALREADY_SHIPPED
System: Still operating normally, no infrastructure error
```

If this case is logged as:

```text
ERROR Critical system failure!!! java.lang.IllegalStateException: ...
```

then dashboards will generate noise, operations teams can easily mistake it for a system incident, and stack trace overhead may increase unnecessarily. A more appropriate message is typically:

```text
INFO action=ORDER_CANCEL outcome=REJECTED reasonCode=ORDER_ALREADY_SHIPPED
     requestId=req-17 orderId=O-100
```

The `INFO` level here is a **policy example**, not a requirement for every organization. If permission denials repeat unusually or pose a security risk, the same type of event may need to be emitted to **security audit** and a separate alert. Severity is based on **operational impact and observability purpose**, not merely because the code threw an exception.

### Focus of logging

A useful business error log should answer:

1. **What was requested?** `action` and resource.
2. **What was the outcome?** `REJECTED`, `DENIED`, `NO_CHANGE`, `FAILED`, or another exact status.
3. **Why?** A stable `reasonCode`, not a free-form message.
4. **Did the operation leave side effects?** No change, rolled back, partial change, or uncertain outcome.
5. **How to correlate the request?** A validated `requestId`/`operationId`.
6. **Is an alert needed?** Based on rate/significance, avoiding turning every valid rejection into `ERROR`.

**A business error is not synonymous with a bug, crash, or ERROR log level.** It reflects a business branch that must be designed, returned, and observed consistently.

## 2. How do business errors, technical errors, and programming errors differ?

| Type | Example | Typical handling | Recommended logging |
| --- | --- | --- | --- |
| **Business rule violation** | Cancelling a shipped order, exceeding limit | Rejection result with a defined code | `INFO` or `WARN` depending on risk, usually no full stack |
| **Validation error** | Missing required field, invalid schema value | Return validation result; no mutation | May skip logging individual errors; aggregate metrics, audit when needed |
| **Authorization denied** | Actor lacks permission to change role | Reject; may require security audit | Controlled audit channel; `WARN` when policy requires |
| **Conflict/idempotency** | Stale version, target state already reached | `CONFLICT` or `NO_CHANGE` per API contract | Log brief context, do not treat as an incident by default |
| **Technical/infrastructure failure** | Database unreachable, disk full, dependency timeout | Controlled retry or fail/UNKNOWN | `ERROR` at the responsible boundary; selective trace |
| **Programming defect** | `NullPointerException` from broken invariant, bad index | Fail fast, fix source code | Error + stack and safe context |
| **Unknown distributed outcome** | Timeout after sending payment command | Reconcile before retrying | `WARN/ERROR` by impact; `UNKNOWN`, do not conclude failure with certainty |
| **Expected cancellation** | User cancels a job that has not run | `CANCELED` outcome | May be `INFO` or audit, no stack needed |

For example, `IllegalArgumentException` does not by itself tell you whether it is a business error. It can be a valid validation **or** indicate a programming bug depending on where it is thrown and the contract. Therefore, **do not classify solely by exception name or HTTP status code**.

Some principles:

- If an error is expected in daily operations and the client has a way to fix it, prefer a **stable reason code** and structured result.
- If an internal invariant that the code promises to always uphold is broken, that may be a **bug** and should not be converted into "invalid customer input".
- Dependency errors typically need diagnostic info, retry policies, circuit breakers, and health tracking.
- When side effects may have occurred, do not record `FAILED/ROLLED_BACK` before verifying; consider `UNKNOWN` or `PARTIAL`.

## 3. Defining a business error code set

Do not force clients or dashboards to parse:

```text
"Order cannot be cancelled because it has already been shipped."
```

to guess the error type. This message may change in language, structure, or wording.

Define a domain **code set**:

| `reasonCode` | Meaning | Suggested outcome | Auto-retry? |
| --- | --- | --- | --- |
| `ORDER_ALREADY_SHIPPED` | Already shipped, cannot cancel | `REJECTED` | No |
| `INSUFFICIENT_STOCK` | Insufficient stock per rules | `REJECTED` | Only after conditions change |
| `CREDIT_LIMIT_EXCEEDED` | Limit exceeded | `REJECTED` | No hot retry |
| `ORDER_NOT_FOUND` | Object absent within permitted visibility context | `REJECTED` | No, unless eventual data |
| `ALREADY_CANCELLED` | Already in target state | `NO_CHANGE` | Not needed |
| `POLICY_DENIED` | Denied by permissions | `DENIED` | No |
| `VERSION_CONFLICT` | Optimistic concurrency conflict | `CONFLICT/REJECTED` | Conditional retry possible |
| `DEPENDENCY_UNAVAILABLE` | Service/DB outage | `FAILED/UNKNOWN` | Per technical policy |

An error code should have **one governed meaning**; avoid letting the same code carry two different meanings across services. Broad code groups can be added, such as `ORDER_`, `PAYMENT_`, `AUTH_`, but do not create overly granular codes that leak internal data or cause uncontrolled cardinality growth.

### Distinguishing error codes from messages

- `code`: stable, serving APIs, logic, metrics, and analytics.
- `publicMessage`: friendly, safe, localizable; does not disclose secrets.
- `technicalDetails`: information solely for internal diagnostics, access-restricted, and not included in every log.
- `correlationId`: links the client request to logs/traces, containing no tokens.

Do not use `exception.getMessage()` as `reasonCode`. Messages may contain SQL, paths, emails, user values, or newlines; over time they are also unstable for querying.

## 4. What log level should a business error use?

**There is no absolute mapping of exception → ERROR.** Severity is an observability decision.

| Scenario | Typically considered log level | Stack trace needed? |
| --- | --- | --- |
| Frequent input validation rejections | Do not log individual cases, or `DEBUG` | Usually no |
| Cancelling an order after it has shipped | `INFO` when tracking is needed, or audit | Usually no |
| Insufficient payment limit | `INFO`/audit per policy | Usually no |
| Access denied | Security audit; `INFO/WARN` depending on risk | Not by default |
| Expected optimistic locking conflict | `DEBUG/INFO` if high volume | Not by default |
| Unusual business rule violation with high impact | `WARN` and metric/alert | May add context, not necessarily stack |
| Database offline causing operation failure | `ERROR` at appropriate boundary | Usually with trace for investigation |
| Bug leaving data in an inconsistent state | `ERROR`, incident | With trace per policy |

**Example of an API with thousands of validation error requests per minute:** printing a full stack trace for every request drives up CPU, ingestion cost, log storage cost, and alert noise. Record counts by error code and minimize per-event payloads, enabling scoped detailed diagnostics only when needed.

However, **not every "business error" should be ignored**. Some behaviors such as transaction rejections, unauthorized access, or failed configuration changes can be important evidence. They can be emitted to a reliable audit sink even without triggering an ERROR alert on the operational logger.

### Choosing log level by policy rather than by `catch`

SLF4J illustration snippet:

```java
try {
    orderService.cancel(orderId);
} catch (OrderBusinessException ex) {
    logger.info(
        "action=ORDER_CANCEL outcome=REJECTED reasonCode={} orderId={}",
        ex.code(), safeOrderId);
    throw ex; // Or map to a result at the boundary.
}
```

This is a snippet within a project that already has the appropriate variables/classes, **not a standalone Java program**. If an upper layer logs the same error again, it can create duplicate logs. Let a **responsible boundary** choose where to record the outcome event, rather than having every layer log.

## 5. Logging at the boundary: do not log the same error in every layer

A business error can pass through controller → application service → domain service → repository. If every layer calls `logger.error(..., ex)`, a single event turns into multiple identical stack traces.

Poor example:

```java
// Domain layer
throw new OrderBusinessException(ORDER_ALREADY_SHIPPED);

// Application layer
catch (OrderBusinessException e) {
    logger.error("Cannot cancel", e); // Duplicate 1
    throw e;
}

// Web layer
catch (OrderBusinessException e) {
    logger.error("Request failed", e); // Duplicate 2
    return conflictResponse(e);
}
```

This example is **illustrative pseudocode**, lacking full imports/classes/variables to compile standalone.

A better design:

1. **Domain layer:** defines rules, throws a coded exception or returns a result; usually does not log requests itself.
2. **Application layer:** decides transactions, audit, and business state; enriches metadata if needed.
3. **Boundary** (HTTP handler, message consumer, scheduled job): maps the error to a response/outcome and logs **one structured event** with action, reasonCode, and correlation ID.
4. **Observability layer:** collects metrics/traces by codes, without repeating meaningless messages/stacks.

The principle **"log or throw, do not both log and throw at every layer"** is a useful heuristic, not an absolute law. A layer may log a genuinely necessary independent event (such as an attempt timeout or an audit event), but it must have a distinct **event type** so readers do not think the same error happened multiple times.

### When to log the original exception

If a business exception only carries an error code, logging the code + context is enough—no full `Throwable` is needed. If a technical failure has a root cause needing investigation, the responsible boundary can log the exception once with its stack trace and correlation ID, avoiding stripping the `cause`.

Never turn an unclassified exception into a business error just to reduce `ERROR` levels: that hides bugs and skews SLAs/alerts.

## 6. Typed exception or Result object?

There are two common design approaches.

### 6.1. Exception for business cases that cannot complete

```java
public final class OrderBusinessException extends RuntimeException {
    private final String code;

    public OrderBusinessException(String code, String internalMessage) {
        super(internalMessage);
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

Saving this example as `OrderBusinessException.java` yields a valid Java class. In a real project, use an `enum`/`sealed hierarchy` where helpful to constrain error codes; never let the client choose `code` from input data.

**Pros:** easy integration with middleware/exception handlers, separates the happy path, propagates errors across layers.

**Trade-offs:** exceptions can capture a stack trace at instantiation; if used hundreds of thousands of times per second for very common states, allocation/stack-capture cost can be significant. Exceptions can also be mis-mapped by an outer `catch (Exception)` as system errors if not classified properly.

### 6.2. Explicit result type for expected branches

```java
// Java 17, example illustrating type design.
sealed interface CancelResult
        permits CancelResult.Cancelled,
                CancelResult.NoChange,
                CancelResult.Rejected {

    record Cancelled() implements CancelResult {}
    record NoChange() implements CancelResult {}
    record Rejected(String reasonCode) implements CancelResult {}
}
```

This is a valid data type in Java 17 when placed in an appropriate declaration context. Callers handle each outcome explicitly without creating an exception for an expected state. However, `Result` does not automatically guarantee callers handle all branches exhaustively (without pattern matching/checks), does not automatically manage transactions, and does not automatically write audits. If existing APIs/middleware use typed exceptions, staying consistent matters more than switching styles just to avoid stacks.

### Which to choose?

- **Frequent validation:** returning structured errors/`Result` is usually appropriate, no need to throw exceptions for control flow.
- **Domain rules preventing completion:** can use a coded business exception or `Result`, as long as mapping is consistent.
- **Unexpected technical failures:** exceptions with `cause` and stack have diagnostic value.
- **Hot paths:** measure with a profiler/JMH before optimizing on intuition.

Do not strip stack traces from all exceptions to save cost: for bugs or infrastructure outages, stacks are critical data for investigation.

## 7. Standalone Java 17 example: order cancellation and accurate logging

The following example uses **`java.util.logging` (JUL)** built into the JDK. We simulate five requests: one successful cancellation, one idempotent no-change request, two requests rejected by business rules, and one simulated infrastructure failure. The test logger prints only level/message and the throwable class name for deterministic stdout; **this is not a production formatter**.

### 7.1. Source code `BusinessErrorLoggingDemo.java`

```java
import java.util.HashMap;
import java.util.Map;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class BusinessErrorLoggingDemo {
    enum Status { CREATED, SHIPPED, CANCELLED }

    enum Reason {
        ORDER_NOT_FOUND,
        ORDER_ALREADY_SHIPPED
    }

    static final class BusinessRuleException extends RuntimeException {
        private final Reason reason;

        BusinessRuleException(Reason reason) {
            super(reason.name());
            this.reason = reason;
        }

        Reason reason() {
            return reason;
        }
    }

    static final class DependencyUnavailableException
            extends RuntimeException {
        DependencyUnavailableException() {
            super("simulated storage unavailable");
        }
    }

    static final class OrderService {
        private final Map<String, Status> orders =
                new HashMap<>(Map.of(
                        "o-1", Status.CREATED,
                        "o-2", Status.SHIPPED));

        boolean cancel(String orderId) {
            if ("db-down".equals(orderId)) {
                throw new DependencyUnavailableException();
            }

            Status status = orders.get(orderId);
            if (status == null) {
                throw new BusinessRuleException(Reason.ORDER_NOT_FOUND);
            }

            if (status == Status.SHIPPED) {
                throw new BusinessRuleException(
                        Reason.ORDER_ALREADY_SHIPPED);
            }

            if (status == Status.CANCELLED) {
                return false;
            }

            orders.put(orderId, Status.CANCELLED);
            return true;
        }

        Status statusOf(String orderId) {
            return orders.get(orderId);
        }
    }

    private static final Logger LOG =
            Logger.getLogger("example.business.error");

    private static void handle(
            OrderService service, String requestId, String orderId) {
        try {
            boolean changed = service.cancel(orderId);
            String outcome = changed ? "SUCCEEDED" : "NO_CHANGE";
            String reason = changed
                    ? "CANCELLED" : "ALREADY_CANCELLED";

            LOG.info("action=ORDER_CANCEL outcome=" + outcome
                    + " reasonCode=" + reason
                    + " requestId=" + requestId);
        } catch (BusinessRuleException e) {
            // Expected business branch: do not print full stack.
            LOG.info("action=ORDER_CANCEL outcome=REJECTED"
                    + " reasonCode=" + e.reason()
                    + " requestId=" + requestId);
        } catch (DependencyUnavailableException e) {
            // Technical error: keep Throwable so the backend can record the stack.
            LOG.log(Level.SEVERE,
                    "action=ORDER_CANCEL outcome=FAILED"
                    + " reasonCode=DEPENDENCY_UNAVAILABLE"
                    + " requestId=" + requestId, e);
        }
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler deterministic = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }

                String line = record.getLevel().getName()
                        + " " + record.getMessage();

                if (record.getThrown() != null) {
                    line += " throwable="
                            + record.getThrown()
                                    .getClass().getSimpleName();
                }

                System.out.println(line);
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };

        deterministic.setLevel(Level.ALL);
        LOG.addHandler(deterministic);
        try {
            OrderService service = new OrderService();

            handle(service, "req-1", "o-1");
            handle(service, "req-2", "o-1");
            handle(service, "req-3", "o-2");
            handle(service, "req-4", "unknown");
            handle(service, "req-5", "db-down");

            System.out.println("finalStatus="
                    + service.statusOf("o-1"));
        } finally {
            LOG.removeHandler(deterministic);
            deterministic.close();
        }
    }
}
```

Save the file with the exact name, using JDK 17 or newer:

```bash
javac BusinessErrorLoggingDemo.java
java BusinessErrorLoggingDemo
```

**Exact stdout when running the above program standalone:**

```text
INFO action=ORDER_CANCEL outcome=SUCCEEDED reasonCode=CANCELLED requestId=req-1
INFO action=ORDER_CANCEL outcome=NO_CHANGE reasonCode=ALREADY_CANCELLED requestId=req-2
INFO action=ORDER_CANCEL outcome=REJECTED reasonCode=ORDER_ALREADY_SHIPPED requestId=req-3
INFO action=ORDER_CANCEL outcome=REJECTED reasonCode=ORDER_NOT_FOUND requestId=req-4
SEVERE action=ORDER_CANCEL outcome=FAILED reasonCode=DEPENDENCY_UNAVAILABLE requestId=req-5 throwable=DependencyUnavailableException
finalStatus=CANCELLED
```

### 7.2. Reading the output

- **req-1:** order `o-1` is in `CREATED` state, cancelled successfully; logger prints `SUCCEEDED`.
- **req-2:** same order is already `CANCELLED`; no further mutation needed, logger prints `NO_CHANGE`.
- **req-3:** order `o-2` is already `SHIPPED`, cancellation disallowed; `BusinessRuleException` is mapped to `REJECTED` at `INFO`.
- **req-4:** order does not exist in the model; mapped to `REJECTED/ORDER_NOT_FOUND`. In systems requiring anti-enumeration, the client response may not reveal whether the object exists; internal audit must still respect appropriate access permissions.
- **req-5:** simulates an unavailable dependency; logged at `SEVERE` (corresponding to severe errors in JUL) with `Throwable` attached, not mistaken for a business rule.
- The last line verifies the first valid cancellation changed the order's state.

**Note on output:** The `deterministic` handler prints only the throwable's class name, **not the stack trace**. In systems using standard `ConsoleHandler`/Logback formatters, attaching an exception to a log record can produce additional stack traces and non-fixed formatting. This demo uses a simplified formatter to highlight the difference between outcome logs and diagnostic logs.

**Limitations of the example:** `HashMap` operates in-memory on a single thread, without database transactions, permission checks, durable logging sinks, or encryption. `BusinessRuleException` still captures a stack trace on instantiation even though the test does not print it. The `db-down` case is an intentional simulated failure. This program helps illustrate classification and messaging, **not production order-processing code**.

## 8. Mapping business errors to HTTP/API

In HTTP applications, business errors must be mapped to **a consistent API contract**, while logging appropriate internal context. A sample response:

```json
{
  "code": "ORDER_ALREADY_SHIPPED",
  "message": "Order cannot be cancelled at this stage.",
  "requestId": "req-3"
}
```

HTTP status depends on semantics:

| Condition | Typically considered HTTP status | Internal outcome |
| --- | --- | --- |
| Invalid input schema | `400 Bad Request` | `REJECTED` |
| Resource not found and safe to disclose | `404 Not Found` | `REJECTED` |
| Actor lacks permission | `403 Forbidden` | `DENIED` |
| Current state conflicts with request | `409 Conflict` | `REJECTED`/`CONFLICT` |
| Domain rule violation despite valid syntax | `422 Unprocessable Content` or `409` per contract | `REJECTED` |
| Idempotent request already in desired state | May be `200/204` | `NO_CHANGE` |
| Dependency unavailable | `503 Service Unavailable` when appropriate | `FAILED/UNKNOWN` per evidence |
| Unhandled bug | `500 Internal Server Error` | `FAILED`, internal error ID |

**Do not use the HTTP status code alone to conclude the outcome.** An HTTP 500 after commit may be a response-encoding error; an HTTP 202 may only confirm the request was accepted, not that the job finished.

### Spring Boot `@RestControllerAdvice`: illustrative code

```java
@RestControllerAdvice
class ApiErrorHandler {
    @ExceptionHandler(OrderBusinessException.class)
    ResponseEntity<ApiError> handleBusiness(
            OrderBusinessException ex,
            HttpServletRequest request) {

        String requestId = validatedRequestId(request);
        log.info("outcome=REJECTED reasonCode={} requestId={}",
                ex.reason(), requestId);

        ApiError body = new ApiError(
                ex.reason().name(),
                "Request cannot be completed.",
                requestId);

        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }
}
```

This is **only an illustrative snippet**, not standalone: it assumes SLF4J `log`, `OrderBusinessException`, `ApiError`, `validatedRequestId`, and appropriate Spring/Servlet imports. In practice, map **each `reasonCode`** to an appropriate status rather than returning `409` for every error type. When validating, do not trust the request ID header directly without validation. Public APIs should use safe messages without sending stack traces, SQL, or raw exception contents.

If the service layer already logs the same `BusinessRuleException`, pick a single responsible logging point to avoid duplication. If an audit channel needs to record every denied/rejected request, that can be an independent event from access logs at the web boundary.

## 9. Business errors in messaging or async job applications

A message consumer receiving `CancelOrder` may encounter `ORDER_ALREADY_SHIPPED`. This may be an error **that cannot be cured by retrying**. If the consumer automatically NACKs/requeues forever, the poison message will keep re-running and spamming logs.

Classify by recoverability:

| Group | Example | Common action |
| --- | --- | --- |
| Permanent business rejection | Order already shipped, invalid coupon | Record `REJECTED` outcome, ACK or DLQ per contract, no hot retry |
| Payload validation error | Missing required schema field | Reject/DLQ, alert producer, avoid loops |
| Transient technical | Network timeout, DB temporarily unavailable | Retry with backoff, budget, idempotency |
| Unknown remote outcome | Payment timeout after issuing command | Reconcile/idempotency before retrying side effects |
| Idempotent duplicate | Message already processed with same ID | Record `DEDUP/NO_CHANGE`, ACK per contract |

A broker **ACK** only indicates message progress at the protocol level; it does not prove the audit log was durably persisted. Business errors concluded at the consumer need `messageId`, `operationId`, `attempt`, and reason code for investigation; do not log raw payloads containing personal data.

A semantically safe flow:

```text
Receive message
   |
   v
Validate + authorize + idempotency check
   |
   +-- Permanent business error --> record rejection --> ACK/DLQ per policy
   |
   +-- Transient failure --------> retry scheduling/backoff
   |
   +-- Business effect commit ---> record outcome --> ACK
   |
   +-- Commit uncertain ---------> reconcile, do not retry blindly
```

If a business error is **not terminal** in a specific workflow—for example, out of stock when backordering is allowed—the policy may differ. Do not assume by default that "every business exception is non-retryable"; decide based on domain semantics, mutable state, and deadlines.

## 10. Transactions, rollbacks, and accurate outcomes

A major risk in business error logging is **declaring the wrong outcome**. Example:

```text
T1: Validation passed
T2: Write "SUCCEEDED" to log
T3: UPDATE DB
T4: Transaction rolls back due to conflict
=> Log "SUCCEEDED" does not reflect the final state
```

If an operation can commit or roll back, finalize the outcome after the success boundary per contract. Keep in mind:

- With DB transactions, `repository.save(...)` is not itself proof of commit.
- Updated row counts or optimistic locking can detect conflicts; do not treat 0 updated rows as success.
- When a transaction rolls back due to a business exception, events written in the **same DB transaction** also roll back. If rejection/denied audits are needed, use a separate channel or an independent audit transaction.
- If an exception occurs **after commit**, do not automatically mark the operation `FAILED`. You may need an `UNKNOWN` outcome for the client if it cannot be verified, plus reconciliation.
- Side effects outside the DB do not roll back with a local transaction; if partial execution occurs, use `PARTIALLY_SUCCEEDED`/compensation per contract.

### Outcome and log severity remain two separate axes

`outcome=REJECTED` can be logged at `INFO`; `outcome=SUCCEEDED` can be stored in a dedicated audit store; `outcome=FAILED` due to timeout may need `WARN/ERROR` and reconciliation.

Do not place all business error logs in `catch`/`finally` and assume a rollback occurred. **Commit behavior, transaction boundaries, and error types determine the truth**, and the logger merely records that truth.

## 11. Audit logging: valid rejections can still matter

A business error may not be a technical incident, yet still require audit evidence—especially for:

- Denied access and permission changes.
- Unauthorized payment/debit operations.
- Failed security configuration/key changes.
- Policy, limit, or anti-fraud control decisions.
- Transaction rejections for regulatory compliance.

An audit event might look like:

```json
{
  "eventType": "BUSINESS_OPERATION_RESULT",
  "action": "ORDER_CANCEL",
  "actorId": "user-19",
  "resourceId": "order-100",
  "operationId": "op-72",
  "outcome": "REJECTED",
  "reasonCode": "ORDER_ALREADY_SHIPPED",
  "occurredAt": "2026-01-01T10:00:00Z"
}
```

This JSON is sample data only. Do not rely on `INFO` from a best-effort `AsyncAppender` as a guarantee for critical audits if policy requires durability. When needed, use an audit repository/outbox or a sink with acknowledgments and appropriate access control/retention.

**Do not equate business rejections with security alerts.** A system can reject many legitimate requests; detecting attacks requires combining actor, target, frequency, signals, and trusted sources. Also restrict details in API responses so attackers cannot use reason codes to enumerate or infer sensitive resources.

## 12. SLF4J and structured logging for business errors

In systems using SLF4J, log stable fields:

```java
// Snippet in an application that already has logger, requestId, orderId, and code.
logger.info(
    "action={} outcome={} reasonCode={} requestId={} orderId={}",
    "ORDER_CANCEL", "REJECTED", code, requestId, orderId);
```

Parameterized logging avoids eager string concatenation in some cases, but it **does not automatically mask secrets** or turn messages into JSON. If downstream parsers need to query `reasonCode` or `outcome`, use a structured logging/JSON encoder suited to your backend; verify keys/types/schemas on the actual sink.

### Recommended fields

| Field | Purpose | Usage |
| --- | --- | --- |
| `eventType` | Event kind: `BUSINESS_RULE_REJECTED` | Enables accurate querying |
| `action` | `ORDER_CANCEL`, `PAYMENT_TRANSFER` | Avoids free-form messages |
| `outcome` | `REJECTED`, `NO_CHANGE`, `FAILED` | Reflects verified outcome |
| `reasonCode` | Domain error code | Do not use raw exception message |
| `requestId`/`traceId` | Correlates requests | Must not carry tokens |
| `operationId` | Links attempts of a logical operation | Keep stable across retries |
| `resourceId` | Related resource | Enforce privacy controls |
| `durationMs` | Latency at a defined boundary | Do not use as proof of commit |
| `service`, `environment` | Emission source | Avoid unreasonable cardinality |
| `retryable` | Whether retry is allowed | Computed by policy, not just exception name |

You do not need to log every field on every event. Pick enough for investigation while minimizing data.

### MDC and context propagation

In multithreaded applications, MDC can hold request/operation IDs to attach to logs:

```java
// Illustration for an application with SLF4J and safe variables.
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("requestId", validatedRequestId);
    processBusinessCommand();
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

This snippet is not standalone: it requires importing `Map`, `MDC`, and having the corresponding methods/variables. MDC is typically bound to the current thread; `CompletableFuture`, thread pools, or reactive pipelines do not necessarily propagate it automatically. Failing to `clear/restore` can cause request B's business errors to be tagged with request A's ID.

Avoid placing `password`, `accessToken`, raw request bodies, or secrets in MDC: appenders may output the entire context via patterns without developers noticing.

## 13. Security: do not turn business errors into a data leak

Business exceptions can include user-supplied parameters:

```java
throw new BusinessRuleException(
        "Invalid card " + fullCardNumber);
```

If the web layer logs the raw exception message or stack, the card number can flow into files, collectors, dashboards, backups, and exports. Better:

```text
reasonCode=PAYMENT_METHOD_REJECTED
paymentMethodRef=pm_opaque_42
requestId=req-42
```

For client-facing messages, provide only an appropriate code and description; do not include SQL, queries, internal paths, stack traces, or information about objects the actor is not authorized to view.

**Log injection:** client-supplied fields may contain `\r`, `\n`, or control characters to forge log lines. Use an encoder with proper escaping, validate correlation IDs, and limit length. Never trust an arbitrary string to be a safe ID just because the field is named `requestId`.

Some applications use `toString()` on DTOs in logs:

```java
logger.warn("Rejected transfer {}", transferRequest);
```

If the DTO contains accounts, tokens, or PII, object serialization can leak data. Log an **allowlist of reviewed fields**, not the whole object merely for debugging convenience. Hashing does not automatically make PII harmless: identifiers with small domains can still be reversed.

## 14. Performance: frequent exceptions and stack trace cost

Creating a standard `Throwable` typically captures call stack information at instantiation time. Thus, using exceptions as a frequent control-flow mechanism can incur overhead even if you never print the stack.

Options:

- If validation is a very frequent branch, using `Result`/validation reports can reduce cost and make the API contract clearer.
- If business exceptions are relatively rare, the cost is usually negligible compared to DB/network operations; measure before optimizing.
- Avoid `logger.error("Business failed", ex)` on every common rule violation if a trace is not needed.
- When `DEBUG` is disabled, argument expressions like `new Exception(...)` **are still evaluated by Java** before the logger call. Use guards or lazy suppliers where appropriate if building diagnostic info is expensive.
- When you already have a real exception, do not call `getStackTrace()`, format another String, and also pass the same exception to the backend: that easily doubles cost without adding information.

Do not strip stack traces from all custom exceptions just to improve microbenchmarks; losing the origin of bugs can be far costlier. JMH/profilers, allocation rates, p95/p99, and actual error rates should guide whether optimization is needed.

## 15. Logging business errors in retry and idempotency flows

A client may resend a request due to a timeout, or a message broker may redeliver after a lost ACK. An operation that succeeded the first time may be called again when data has already changed. In such cases, **logging the accurate outcome** matters more than printing an exception.

Example:

```text
operationId=op-9 attempt=1 -> SUCCEEDED, order canceled
operationId=op-9 attempt=2 -> NO_CHANGE, already canceled
logical operation outcome -> SUCCEEDED
```

If a second request targets the same resource with a **different operation ID**, `NO_CHANGE` may still be right, but do not assume it is a "retry of the same operation". Distinguish `requestId`, `operationId`, `attemptId`, and event ID.

For non-retryable business errors like `ORDER_ALREADY_SHIPPED`, continuous automatic retries cause log flooding. For transient errors like `DEPENDENCY_UNAVAILABLE`, retries can follow backoff, timeouts, budgets, and idempotency. For timeouts after uncertain side effects, reconcile; do not assume `FAILED` and retrying is always safe.

### Defining success by scope

A worker may log `MESSAGE_ACK_REQUESTED` after processing. Yet broker acceptance of the ACK and collector persistence of the audit event **are two different outcomes**. If a business error requires audit persistence, a separate storage contract is needed.

In multi-step systems or sagas, a business error at one step may trigger compensation. Record the initial attempt, the error, the compensation, and the final outcome; do not overwrite history with a single `FAILED` event.

## 16. Testing business error logging

Asserting `throw BusinessRuleException` or `verify(logger).warn(...)` is not enough; you must verify **actual outcomes and side effects**.

### Suggested test matrix

| Scenario | Business state | Expected event | Level/notes |
| --- | --- | --- | --- |
| Allowed order cancellation | Transitioned to `CANCELLED` | `SUCCEEDED/CANCELLED` | `INFO` per policy |
| Re-cancelling a cancelled order | Unchanged | `NO_CHANGE/ALREADY_CANCELLED` | No false error |
| Order already shipped | Unchanged | `REJECTED/ORDER_ALREADY_SHIPPED` | Full stack not required |
| Order does not exist | Unchanged | `REJECTED/ORDER_NOT_FOUND` | Do not leak info beyond permissions |
| Insufficient permission | Unchanged | `DENIED/POLICY_DENIED` | Audit if policy requires |
| DB error before mutation | Unchanged | `FAILED/DEPENDENCY_UNAVAILABLE` | Appropriate trace/error ID |
| Timeout after possible commit | Uncertain | `UNKNOWN/RESULT_UNCONFIRMED` | Reconcile |
| Concurrent update conflict | Update not accepted | `REJECTED/CONFLICT` | Check version/row count |
| Job accepted to run | Not finished | `PENDING` | Followed by terminal event |
| Bulk with 8/10 committed | 8 side effects | `PARTIALLY_SUCCEEDED` | Record counts and item links |

### Testing across layers

1. **Domain/unit:** business rules return the right code, no mutation on rejection, clear `NO_CHANGE` cases.
2. **Application/integration:** transactions actually commit/roll back, outcomes match final state.
3. **Web/message boundary:** HTTP/NACK/ACK codes or results and log contents match schema; no duplicate logs in lower layers.
4. **Audit delivery:** critical events are persisted per contract, handling collector loss/retry/dedup appropriately.
5. **Security:** exception messages, MDC, and DTO `toString()` do not leak tokens/PII; CR/LF inputs do not forge logs.
6. **Concurrency/retry:** parallel requests, optimistic versioning, idempotency keys, and correlation context do not cross-leak.

### JUnit 5 example for business exception mapping

The snippet below is an **illustrative test** using JUnit Jupiter; it must be placed in the same package as `BusinessErrorLoggingDemo` (or visibility adjusted per project) with JUnit on the classpath, and is not a standalone runnable class:

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class BusinessErrorTest {
    @Test
    void cannotCancelShippedOrder() {
        var service = new BusinessErrorLoggingDemo.OrderService();

        var ex = assertThrows(
                BusinessErrorLoggingDemo.BusinessRuleException.class,
                () -> service.cancel("o-2"));

        assertEquals(
                BusinessErrorLoggingDemo.Reason.ORDER_ALREADY_SHIPPED,
                ex.reason());
        assertEquals(
                BusinessErrorLoggingDemo.Status.SHIPPED,
                service.statusOf("o-2"));
    }

    @Test
    void secondCancelIsNoChange() {
        var service = new BusinessErrorLoggingDemo.OrderService();

        assertTrue(service.cancel("o-1"));
        assertFalse(service.cancel("o-1"));
    }
}
```

These two tests only verify **domain behavior**. To assert actual logs, attach an in-memory JUL `Handler`/Logback `ListAppender` and compare message/level/context; always detach the appender and restore state after the test so you do not pollute the test suite.

If the logging backend is asynchronous, wait for events using `BlockingQueue.poll(timeout)` or a latch/sink acknowledgment; do not assume an event arrived just because the logger call returned or after a fixed `Thread.sleep`.

## 17. Metrics and alerting for business errors

Business errors can be numerous, yet most represent the system correctly enforcing rules. Metrics must **distinguish expected behavior from infrastructure failures**.

Illustrative metric names:

| Metric | Purpose |
| --- | --- |
| `business_operations_total{action,outcome}` | Outcome distribution by action |
| `business_rejections_total{reasonCode}` | Track which business rejections are rising |
| `technical_failures_total{dependency}` | Track infrastructure outages separately |
| `business_operation_duration_seconds` | Track latency by outcome |
| `audit_delivery_errors_total` | Separate audit write failures from business errors |
| `business_unknown_outcomes` | Number of operations needing reconciliation |
| `retry_attempts_total{reasonGroup}` | Detect retry loops |
| `business_conflicts_total{action}` | Analyze contention/optimistic locking |

These names are not default SLF4J or Logback metrics. When implementing with Micrometer/Prometheus or another solution, control **cardinality**: never use `requestId`, `orderId`, usernames, or free-form messages as labels.

You do not necessarily need to alert on every `ORDER_ALREADY_SHIPPED`. Sudden rate spikes, abnormal distributions, or high-impact business outcomes can be meaningful signals. For example, many `POLICY_DENIED` events on a sensitive resource warrant investigation per security policy; many `VERSION_CONFLICT` events may reflect concurrency needing optimization rather than an attack.

## 18. Common mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Logging `ERROR` for any exception | Business rejections can be normal operation | Classify by taxonomy and impact |
| Logging stack traces for every validation | High CPU/GC/log cost, alert noise | Code + context; stack for technical errors |
| `logger.error` in service then throwing for web to log again | Duplicates the same error | One responsible boundary |
| Logging `SUCCEEDED` before transaction commit | Untrue if rolled back | Finalize after verifying effect |
| Treating any timeout as `FAILED` | Side effects may have occurred | `UNKNOWN` + reconciliation |
| Mapping all `RuntimeException` to business rejection | Hides bugs/infrastructure issues | Catch specific types; unexpected stays technical |
| Using free-form messages as error codes | Hard to query, language changes | Governed `reasonCode` |
| Returning raw exceptions to clients | May leak stacks, SQL, tokens | Safe public messages |
| Logging full DTO `toString()` | May contain PII/secrets | Allowlist permitted fields |
| Infinitely retrying business exceptions | Poison loops, log spam, wasted resources | Classify permanent vs. transient |
| Treating HTTP status as final job outcome | `202` may only mean job accepted | Lifecycle + operation ID |
| Not logging denied actions because there was no mutation | Missing security trail | Separate audit per policy |
| Testing only exception types | Unknown if state/commit/logs are right | Test outcome, state, and sink |
| Assuming `INFO` is durably stored as audit | Filters/async queues/collectors can drop events | Audit store/outbox/ack when needed |

## 19. Production readiness checklist

- [ ] Agreed on definitions for business error, validation, technical failure, and programming defect.
- [ ] Stable `reasonCode` and `outcome` defined, not derived from exception messages.
- [ ] Log levels based on operational needs, not defaulting to `ERROR` for every `throw`.
- [ ] Expected business rejections do not have stack traces logged repeatedly across layers.
- [ ] Boundary is responsible for mapping responses/messages and logging context at the right point.
- [ ] `SUCCEEDED` is never logged before business effects are verified/committed.
- [ ] `UNKNOWN`/`PARTIALLY_SUCCEEDED` used when side effects are uncertain or partial.
- [ ] Retry policy distinguishes permanent from transient errors; idempotency is in place.
- [ ] Events include action, outcome, reason, correlation IDs; no secrets/PII outside policy.
- [ ] Required audit/security events are separated from best-effort debug logs where appropriate.
- [ ] Tests verify domain state, error codes, log levels, messages, and transaction behavior.
- [ ] Failure-injection tests cover DB/collector issues, concurrent updates, and async logging.
- [ ] Monitoring separates business rejection rates from technical incidents without alert noise.
- [ ] Error and log schemas are reviewed/versioned when semantics change.

**Remember:** a business error does not mean the system is broken. It is often **the valid outcome of a business rule**, requiring a stable code, sufficient context, and the right log level—without duplicating stack traces. Only by distinguishing **rejected requests** from **infrastructure-failed operations** can a logging system help development, operations, and audit teams understand what truly happened.
