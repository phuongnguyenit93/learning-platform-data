# Adding Operation Context and Useful Identifiers for Error Investigation in Java

> **Topic:** Java Core → Exception → Diagnostics and Logging. The goal of this lesson is to turn a generic exception message into evidence sufficient to trace *which operation failed, which business entity was involved, which request/task originated the error, which step the system was at, and what the root cause was*; while avoiding exposing sensitive data or creating noise from duplicate logs.

## 1. Why is logging only the exception message not enough?

Suppose a service processes thousands of orders concurrently and the only log is:

~~~text
ERROR java.lang.IllegalStateException: timeout
~~~

This message does not specify whether the error occurred during order confirmation, payment, inventory reservation, or sending a notification; it cannot be linked to a specific request, order, background task, or dependency. A stack trace identifies the **code call path**, but it does not necessarily indicate the **business context** in which the error occurred.

A useful log event can express:

~~~text
level=ERROR event=order_save_failed operation=place_order
requestId=req-7e21 orderId=ord-1042
errorCode=ORDER_PERSIST_FAILED dependency=orders-db
exception=OrderProcessingException
cause=SQLTransientConnectionException
~~~

This is an **illustrative** log, not output from the runnable code below. The identifiers in the example are dummy data. With those fields, an investigator can find related events for the same request, inspect the specific order, group by error code, and correlate the error with the dependent service.

**Key principle:** *the exception explains the failure process in code; the context explains which piece of work the failure belongs to*. Both are needed, but you should not stuff every obtainable piece of data into the message or log.

## 2. Four groups of context to consider

Not every error needs every field. Choose context useful for investigation that fits the boundary and contract of the operation.

| Group | Typical fields | Question answered | Notes |
|---|---|---|---|
| Operation | `operation`, `event`, `stage`, `component` | What work was being done, at which step? | Prefer stable names with business meaning |
| Request correlation | `requestId`, `correlationId`, `traceId`, `spanId` | Which logs belong to the same business flow? | Avoid regenerating IDs arbitrarily at each layer |
| Business entity | `orderId`, `jobId`, `paymentAttemptId`, `messageId` | Which order/task/attempt was affected? | Use minimal IDs with access control |
| Technical diagnostics | `errorCode`, `dependency`, `attempt`, `elapsedMs`, `exception.type`, `cause` | Why did it fail, and can it be reproduced and aggregated? | Distinguish measured evidence from speculation |

Fields should have clear definitions. For example, `orderId` identifies **the order**, whereas `requestId` identifies **a single processing request**; one order may be processed by multiple requests. A `messageId` may be reprocessed multiple times, so `attempt` or `jobExecutionId` helps distinguish each execution.

### Operation names: specific enough yet stable

Use `operation=reserve_inventory`, `operation=charge_payment`, `operation=publish_order_event` instead of vague names like `process`, `run`, or method names that easily change during refactoring. A stable operation name helps:

- Aggregate error counts by feature.
- Compare logs before and after releases.
- Build queries and alerts that do not depend on stack traces.
- Correlate different stages of the same workflow.

Do not put full URLs containing tokens or verbatim SQL containing customer information into the operation name. Use a template-style name (route/template) if you need to describe an endpoint.

## 3. Distinguishing request ID, correlation ID, trace ID, and business ID

These fields are related but **not synonymous**.

- **Request ID:** identifies a single incoming request at the system boundary; useful for finding logs of a specific request.
- **Correlation ID:** links multiple messages, requests, or steps belonging to the same business workflow. Some systems reuse the request ID as the correlation ID, but a consistent convention is required.
- **Trace ID:** identifies a distributed trace; multiple spans belong to the same trace. When a tracing tool is in place, use the trace ID provided by the tracing system rather than inventing another ID and calling it `traceId`.
- **Span ID:** identifies a unit of work within a trace. It can change across stages; do not use it in place of the ID spanning the entire trace.
- **Business ID:** the ID of an order, transaction, job, or affected entity. One entity may appear across many different requests/traces.
- **Attempt/Execution ID:** identifies a single attempt to execute work, especially important for retries, batches, queues, and scheduled tasks.

For example, a payment attempt might have:

~~~text
traceId=4bf92f3577b34da6a3ce929d0e0e4736
requestId=req-e9b3
orderId=ord-321
paymentAttemptId=pat-02
attempt=2
~~~

The `traceId` value here is only a hex format example, not an ID extracted from a real system.

**Do not automatically trust identifiers coming from the client.** If an HTTP header provides a request/correlation ID, the system should validate its length, allowed characters, format, and trust policy, and prevent log injection. When no valid ID is present, generate a server-side ID according to convention and propagate it across the relevant layers.

## 4. Where context lives: parameters, exceptions, or logging context?

There are three approaches commonly combined depending on the architecture.

### 4.1. Passing an explicit context object

~~~java
// Illustrative snippet in Java 17.
record OperationContext(
        String operation,
        String requestId,
        String orderId) {
}
~~~

Layers then accept `OperationContext context` as a parameter. This approach makes dependencies explicit, is relatively easy to test, and works with both thread pools and asynchronous callbacks as long as developers actually pass the context along with the task.

Pros: does not depend on implicit thread state, easy to read the contract. Cons: needs to be passed through multiple layers; avoid turning it into a catch-all object or dragging private data where it is not needed.

### 4.2. Attaching selective information to an exception

A domain exception can hold an error code and a few necessary IDs; when propagating the error across layers, it still tells the caller which operation was involved:

~~~java
// Excerpt inside a Java class.
final class OrderWriteException extends RuntimeException {
    private final String errorCode;
    private final String orderId;

    OrderWriteException(String orderId, Throwable cause) {
        super("cannot save order", cause);
        this.errorCode = "ORDER_WRITE_FAILED";
        this.orderId = orderId;
    }

    String errorCode() {
        return errorCode;
    }

    String orderId() {
        return orderId;
    }
}
~~~

This is a compilable excerpt when placed in an appropriate file/class. The `RuntimeException(String, Throwable)` constructor preserves the cause; typed fields allow callers to classify the error without parsing the message string. Do not put tokens, payment data, or large payloads into exceptions because exceptions can propagate into logs, telemetry, or uncontrolled responses.

### 4.3. Structured logging context / MDC

Popular logging libraries, such as SLF4J paired with a backend supporting `MDC` (Mapped Diagnostic Context), allow setting common fields for logs within the current scope. This is a **logging library capability**, not a built-in `MDC` API in Java SE.

~~~java
// Illustration requiring SLF4J + an appropriate logging backend; does not run with JDK alone.
try {
    org.slf4j.MDC.put("requestId", context.requestId());
    org.slf4j.MDC.put("operation", context.operation());
    service.execute(context);
} finally {
    org.slf4j.MDC.remove("requestId");
    org.slf4j.MDC.remove("operation");
}
~~~

MDC is typically bound to a thread (depending on the implementation), so you must **clean up in finally** to avoid leaking IDs into the next request handled on the same thread pool. On other threads or async stages, do not assume MDC propagates automatically; you must capture/restore it or use a context propagation mechanism supported by the framework.

**Practical choice:** an explicit business/context object serves as the reliable source of truth; MDC or structured logging is a convenient way to emit fields across many log lines within a controlled scope.

## 5. Wrapping exceptions to add context: do not lose the cause

A technical error may pass through multiple layers:

~~~text
Repository: connection timeout
      ↓ cause
Application service: cannot persist order
      ↓ context
Request boundary: operation=place_order, requestId=..., orderId=...
~~~

If you only throw:

~~~java
// Do not do this if you need to preserve the root cause.
throw new IllegalStateException("order failed");
~~~

then outer layers may lose visibility into the original exception, the original stack trace, and the error classification from the dependency.

Instead, use:

~~~java
throw new IllegalStateException("order failed: " + orderId, originalCause);
~~~

For sensitive data, rather than concatenating every value into the message, keep a few controlled IDs in typed fields and emit them into structured logs at the boundary. `Throwable.getCause()` allows walking back the error chain, for example `SQLException` → `RepositoryException` → `OrderWriteException`.

**Do not re-wrap the same error at every layer** without adding new meaning. A five-layer chain of `RuntimeException("failed")` makes logs long without adding clues. Wrap only at abstraction boundaries where there is a semantic transition, such as from a JDBC error to an order persistence error.

### Expected errors vs. unexpected errors

- Business errors such as out-of-stock or order already closed: a structured error code and business ID may suffice; log at WARN/INFO depending on policy and frequency.
- Unexpected errors such as invariant violations, database errors, or coding bugs: log at ERROR when the impact is severe enough, preserving the stack trace/cause and context.
- Timeout/cancellation errors: distinguish them from normal failures; if a task was cancelled according to policy, logging WARN/INFO may be more appropriate than ERROR.
- Do not assign a fixed log level based solely on the exception class name without considering business impact and expectations.

## 6. Standalone Java 17 program: adding context and preserving the root cause

This example uses only Java SE, without depending on SLF4J, so it can be compiled and run with `javac`. Production applications should pass fields to a structured logger instead of manually concatenating long strings.

Save the entire program as **`ExceptionContextDemo.java`**:

~~~java
import java.util.Objects;

public class ExceptionContextDemo {
    record OperationContext(
            String operation, String requestId, String orderId) {
        OperationContext {
            Objects.requireNonNull(operation, "operation");
            Objects.requireNonNull(requestId, "requestId");
            Objects.requireNonNull(orderId, "orderId");
        }
    }

    static final class OrderWriteException extends RuntimeException {
        private final String errorCode;
        private final String orderId;

        OrderWriteException(String orderId, Throwable cause) {
            super("could not save order", cause);
            this.errorCode = "ORDER_WRITE_FAILED";
            this.orderId = orderId;
        }

        String errorCode() {
            return errorCode;
        }

        String orderId() {
            return orderId;
        }
    }

    static void persist() {
        throw new IllegalStateException("storage unavailable");
    }

    static void placeOrder(OperationContext context) {
        try {
            persist();
        } catch (IllegalStateException cause) {
            throw new OrderWriteException(context.orderId(), cause);
        }
    }

    static void handleRequest(OperationContext context) {
        try {
            placeOrder(context);
        } catch (OrderWriteException ex) {
            System.out.printf(
                    "level=ERROR operation=%s requestId=%s orderId=%s code=%s%n",
                    context.operation(), context.requestId(),
                    ex.orderId(), ex.errorCode());

            System.out.println("exception="
                    + ex.getClass().getSimpleName());

            Throwable cause = ex.getCause();
            System.out.println("cause="
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }
    }

    public static void main(String[] args) {
        OperationContext context = new OperationContext(
                "place_order", "req-17", "ord-42");
        handleRequest(context);
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac ExceptionContextDemo.java
java ExceptionContextDemo
~~~

**Exact stdout:**

~~~text
level=ERROR operation=place_order requestId=req-17 orderId=ord-42 code=ORDER_WRITE_FAILED
exception=OrderWriteException
cause=IllegalStateException: storage unavailable
~~~

Why is this example useful?

1. `OperationContext` stores operation-identifying information in the immutable form of a Java record.
2. `persist()` throws the original technical error. `placeOrder()` translates the error to the business abstraction using `OrderWriteException` **and passes `cause`**.
3. `handleRequest()` is the error-recording boundary; it has the operation, request ID, order ID, error code, exception type, and root cause.
4. Printing at the boundary avoids logging the entire stack trace repeatedly at every layer within a single request.
5. The output is produced using fixed values, independent of time, thread scheduler, machine name, or logger implementation.

**In production:** in addition to the printed fields, pass the full `Throwable` to the logging backend to preserve the stack trace and cause chain. The stdout example intentionally displays only type/message so the lesson can be verified with deterministic output; it is **not** a recommendation to omit stack traces from investigation logs.

## 7. Structured logging is more valuable than concatenating a free-form string

A log event should have **separate fields** so the storage system can filter, group, aggregate, and correlate.

Illustrative JSON sample (not program output):

~~~json
{
  "timestamp": "2026-10-19T03:00:00Z",
  "level": "ERROR",
  "service": "order-service",
  "event": "order_persist_failed",
  "operation": "place_order",
  "requestId": "req-17",
  "orderId": "ord-42",
  "errorCode": "ORDER_WRITE_FAILED",
  "dependency": "orders-db",
  "exception": {
    "type": "OrderWriteException",
    "causeType": "IllegalStateException"
  }
}
~~~

The timestamp and ID values here are fictitious to illustrate the schema, not real data. Production logging systems usually add `timestamp`, `service`, `severity`, hostname, and trace context automatically; avoid letting each team invent different field names.

Benefits:

- Querying `requestId = "req-17"` or `errorCode = "ORDER_WRITE_FAILED"` is more reliable than searching for substrings in text.
- Grouping errors by code and operation without parsing messages.
- Easy correlation with metrics/traces and dashboards.
- Fewer query breakages when message copywriting changes.

A log with `"order id req-17 failed"` is worse than separate `orderId` and `requestId` fields: the two IDs have different semantics and investigators should not have to guess with regex.

### Placeholder logging and Throwable

Many logging frameworks provide parameterized logging APIs, such as SLF4J:

~~~java
// Illustration: log is org.slf4j.Logger, context is already declared.
log.error("operation={} requestId={} orderId={} code={}",
        context.operation(), context.requestId(),
        context.orderId(), "ORDER_WRITE_FAILED", exception);
~~~

The snippet above is **not standalone Java SE code**: it requires SLF4J and a backend. The last parameter position must follow the logger API rules so the backend treats `exception` as a Throwable and records the stack trace; in other libraries/versions, check the exact supported overloads. If the backend supports structured arguments/key-value pairs, prefer them over only embedding values into the format string.

Do not use `ex.printStackTrace()` alongside `log.error(..., ex)` indiscriminately: that usually produces duplicate stack traces across two different channels.

## 8. Log once responsibly, do not log on every catch

An error passing through multiple layers can produce three duplicate log entries:

~~~text
Repository: ERROR write failed
Service: ERROR order failed
Controller: ERROR request failed
~~~

If all three print the same stack trace, the system may report three errors instead of one and make it harder to determine the true impact.

**Practical conventions:**

- Lower layers **throw/wrap with appropriate semantics and preserve the cause**.
- A layer responsible for retry decisions may log at DEBUG/INFO per attempt or update metrics, avoiding treating each retry as a final error.
- The boundary layer responsible for responding to the request/job/message should log **one final failure event with full context** when recovery truly fails.
- When an error is handled successfully via a fallback, logging ERROR is not necessarily required; if observability is needed, log a recovery event at an appropriate level.
- Do not rigidly apply "every error may only be logged once" in every architecture: separate events may exist at important boundaries. However, each event must add new information and purpose, not duplicate the exact same stack trace.

Investigators need to distinguish a single failure passing through multiple stages from multiple independent failures. Using `requestId`/`traceId` and a stable `errorCode` helps determine the relationship between events.

## 9. Choosing identifiers that actually help investigation

Good IDs should meet several criteria:

1. **Searchable:** the ID can be used to query records/traces with proper permissions; a meaningless random ID stored nowhere has little value.
2. **Scope-stable:** the same operation retains the ID across related steps; retries may keep the business ID while changing the execution ID.
3. **Clearly named:** `orderId` is not used to hold `requestId`. If an ID is generated by an external provider, the name should indicate its namespace.
4. **Appropriate sensitivity:** some IDs are still data that can be linked to users; not every ID is safe to log openly.
5. **Controlled length and cardinality:** distinct enough to differentiate, without turning it into an ultra-high-cardinality metric label.
6. **Format contract:** standardize on `UUID`, tracing IDs, or a schema-defined string, with validation at the boundary.

### Request ID does not replace business ID

One request can update multiple orders; the same order can also go through multiple requests. Therefore, the two fields answer different questions:

~~~text
requestId=req-abc    orderId=ord-42     operation=create_order
requestId=req-def    orderId=ord-42     operation=cancel_order
~~~

These can be **two different valid operations** on the same order. If the log only has `orderId`, it is hard to know which request caused the error; if it only has `requestId`, it is hard to find the full history of the order.

### Retries and run identifiers

When a message is retried, consider:

~~~text
messageId=msg-802 executionId=exec-1 attempt=1
messageId=msg-802 executionId=exec-2 attempt=2
~~~

The message ID stays stable to group all processing attempts of the same content; execution ID and attempt distinguish an individual failure. Even with `attempt=2`, you cannot automatically conclude the first attempt had no side effects: retries and idempotency must be designed separately.

## 10. Propagating context across CompletableFuture and thread pools

A common mistake is putting the request ID in `ThreadLocal`/MDC on an HTTP thread, then using `CompletableFuture.supplyAsync(...)` on another executor and assuming the context appears automatically.

In practice, `ThreadLocal` is bound to a specific thread. Tasks in a thread pool may run on a thread that previously served another request. Failing to propagate context can produce logs missing IDs; failing to clean up MDC can produce logs **tagged with the wrong customer ID from a previous request**.

A framework-independent approach is **passing context as an immutable parameter**:

~~~java
// Illustrative code inside a method with Executor executor,
// OperationContext context, and method repositorySave(context).
CompletableFuture<String> task =
        CompletableFuture.supplyAsync(() -> {
            try {
                repositorySave(context);
                return "saved";
            } catch (RuntimeException cause) {
                throw new OrderWriteException(context.orderId(), cause);
            }
        }, executor);
~~~

This is an **excerpt, not a standalone program**; the types and variables must be defined in the system. `context` is intentionally captured by the lambda, independent of which thread the executor picks.

If using MDC:

1. Capture the needed fields **before the asynchronous boundary**.
2. Inside the task, set MDC for the duration of execution.
3. Use `try/finally` or an equivalent scope API to restore the previous values (do not just clear globally if an outer scope already exists).
4. Clean up context on success, exception, and cancellation paths.
5. Check how your framework handles virtual threads, reactive chains, or its own structured context; do not infer context propagation behavior solely from the library name.

### A failed Future does not automatically carry all context

When `future.get()` throws `ExecutionException` or `future.join()` throws `CompletionException`, the caller receives the wrapper and `cause`, but **is not guaranteed to receive the worker's `ThreadLocal`**. Therefore, important business IDs should be passed explicitly or attached to the exception/result in a controlled manner.

If failures need to be logged at the request boundary, the caller should retain the `OperationContext` corresponding to the task—for example via a `requestId -> task` map or a closure accompanying the future—rather than guessing the request ID from thread names.

## 11. Exception context across other boundaries

### HTTP requests

Useful context: `method`, route template, server-generated `requestId`, `operation`, normalized authenticated subject ID permitted for logging, application error code, latency, and HTTP status code returned. Do not log raw auth headers, cookies, tokens, or arbitrary bodies.

A web boundary can:

- Generate or validate the correlation ID.
- Pass the ID down to the service/repository.
- Catch errors at the boundary and map them to a public status/errorCode.
- Log the stack/cause to an internal channel, and return a safe response with `requestId` so the user can provide it to support.

### Queues and events

Useful context: `messageId`, `topic`, `partition`/`offset` (when available), `consumerGroup`, `attempt`, and business ID. For retries, keep one correlation ID throughout while distinguishing execution attempts. Never log the entire sensitive payload just because deserialization failed.

### Batch/cron jobs

Useful context: `jobName`, `jobRunId`, `batchId`, `recordId`, `step`, and sequence number if needed. If a record in a batch fails, logging with a valid, safe `recordId` helps trace the specific record; `jobRunId` helps aggregate a single run.

### Databases and external services

Useful context: stable dependency name, operation type, provider's server-side request ID (if permitted), retry attempt, elapsed time, and standard error code. Avoid logging full SQL with inline data; use a query name/template or operation code. Do not print connection strings containing passwords.

## 12. Protecting sensitive data and preventing log injection

Useful context does not mean **the more the better**. Logs are replicated to many storage, query, and alerting systems; they may be viewed by more people than the source business system.

**Do not log without a business justification, authorization, and appropriate safeguards:**

- Passwords, API keys, access tokens, refresh tokens, session cookies.
- Full payment card data, card verification codes, authentication secrets.
- Transaction contents or health information, addresses, emails, or phone numbers when not strictly needed.
- Raw requests/responses containing personal information or secrets.
- Full headers, URL query strings, or exception text from external services when they may contain tokens.

Safeguards:

1. **Field allowlisting:** decide upfront which fields are logged, rather than logging whole objects, `toString()`, or HTTP payloads.
2. **Redaction:** mask sensitive values before passing them to the logger; watch out for both messages and causes from third-party libraries.
3. **Validation & encoding:** limit length and validate characters of client-provided IDs; handle newlines/control characters to reduce the risk of forging log lines.
4. **Retention & access control:** define where logs are stored, retention duration, viewing permissions, and data export paths.
5. **Hashing/pseudonymization when appropriate:** if events must be linked without exposing raw identifiers, use protected transformations compliant with policy; do not assume a plain hash makes data anonymous.
6. **Testing:** feed inputs containing newlines, control chars, long strings, and dummy sensitive content to verify log events remain safe.

**Note:** even a valid `userId` or `orderId` can become personally identifiable data when joined with other systems. Do not equate "no person's name" with "not sensitive."

## 13. Distinguishing message, error code, and ID

A useful error typically has three distinct layers of information:

- **Exception message:** a brief description of the situation, which may change for clarity. Do not use text messages as a machine-readable API.
- **Error code:** a stable code the system uses for classification, such as `ORDER_WRITE_FAILED` or `INVENTORY_NOT_AVAILABLE`. Can be documented for callers or operators.
- **Identifiers:** request/business/job IDs to locate related events and data.

Example:

~~~text
message=could not save order
errorCode=ORDER_WRITE_FAILED
requestId=req-17
orderId=ord-42
~~~

If the message changes to `order persistence failed`, queries by `errorCode` can remain intact. If each exception generates a random code instead of a stable error code, the system cannot aggregate errors of the same kind.

An investigation ID like `incidentId` can help support find a specific error; however, without a mapping to actual logs or traces, displaying an incident ID to the user alone does not solve the problem.

## 14. Log levels and when to record context

**Log level** should reflect expectedness and impact, not merely the presence of an exception.

| Situation | Commonly considered level | Priority context |
|---|---|---|
| Invalid input returning normal 400 from API | INFO/WARN or skip per-request log if metrics exist | route/operation, requestId, errorCode |
| Duplicate message handled by idempotency | INFO/DEBUG | messageId, operation, attempt |
| Temporary retry due to overloaded dependency | WARN/DEBUG per attempt, ERROR for final failure | dependency, retry count, correlationId |
| Unrecoverable data persistence failure | ERROR | operation, businessId, requestId, cause |
| Intentional cancellation | DEBUG/INFO depending on system | taskId, normalized cancel reason |
| Invariant violation or unexpected bug | ERROR | operation, IDs, stack/cause, version |
| Timeout / wait expiration | WARN/ERROR depending on impact | dependency, elapsedMs, timeout policy, attempt |

Avoid logging normal input errors at ERROR for every request: a burst of invalid traffic can make alerts noisy and spike log volume. Conversely, do not lower the log level of errors that risk data loss just because they are represented by unchecked exceptions.

### Log volume and cardinality

High-cardinality IDs like `requestId` and `orderId` are very useful in **logs/traces** to query a single execution. However, they should not be used as default label dimensions for metrics because they create unbounded time series. Good metrics can group by `operation`, `errorCode`, and `dependency`; when investigating an individual event, pivot from metrics to logs/tracing with detailed IDs.

## 15. Preserving context across retries, timeouts, and cancellation

An error may be retried:

~~~text
operation=save_order orderId=ord-42 attempt=1 outcome=retry
operation=save_order orderId=ord-42 attempt=2 outcome=success
~~~

The final outcome is success, yet the first attempt still failed. Do not count an attempt failure as a final request failure if the user was unaffected. A final alert should record the total number of attempts and the last cause if all retries are exhausted.

For timeouts:

- `TimeoutException` indicates a wait limit was exceeded; it **does not prove** the operation on the dependency has stopped or has not committed.
- Keep `requestId`, `operation`, dependency name, `elapsedMs`, and any request IDs sent to the provider if available.
- If the caller retries after a timeout, use an idempotency key or domain state inspection mechanism to avoid writing duplicate side effects.

For cancellation/interruption:

- `CancellationException` and `InterruptedException` should be distinguished from business errors.
- If catching `InterruptedException` and unable to propagate it, typically call `Thread.currentThread().interrupt()`, while recording the task ID and terminating according to the cancellation policy.
- Do not log ERROR for an intentionally cancelled task just because it threw an exception; however, if cancellation leaves corrupted data behind, that is a separate failure requiring investigation.

## 16. How to investigate from an error event

Once a failure event with sufficient context is recorded, a practical workflow can be:

1. **Isolate a single event:** search by `requestId`, `jobRunId`, or an ID provided by the user/support.
2. **Identify operation/stage:** see which step the system was in, which dependency was called, and how many retries/attempts occurred.
3. **Read the exception chain:** distinguish the application-boundary exception from the technical cause, inspecting the stack trace and suppressed exceptions when present.
4. **Correlate traces:** use `traceId` to view the cross-service flow, finding spans with errors or abnormal latency.
5. **Check business state:** use `orderId`/`jobId` via an authorized query mechanism to determine whether data was committed.
6. **Check recurrence:** group by errorCode, operation, release/version, dependency, and time.
7. **Determine action:** is retrying safe, is compensation needed, and are multiple customers affected.
8. **Record conclusions:** root cause findings, remediation policy, regression tests, and any needed log refinements.

**A single log is not enough to confirm the final root cause** just because it contains a dependency name. An `SQLException` may be due to configuration, network, connection pool exhaustion, or DB overload. Context helps ask the right questions; corroborate with evidence from metrics/traces and actual state.

## 17. Common mistakes

1. **Logging only `ex.getMessage()`:** loses the stack trace, cause, and operation context.
2. **Logging only the stack trace:** shows the failing method, but not which request or business entity was involved.
3. **Generating a new request ID at every layer:** breaks event chain correlation.
4. **Using a generic `id` field:** unclear whether it is a request, order, or message.
5. **Wrapping an exception and dropping the cause:** erases the original technical trail.
6. **Logging the exact same exception at every catch:** duplicates events, inflates volume, and easily triggers duplicate alerts.
7. **Passing entire DTOs/objects to the logger:** accidentally logs sensitive data; `toString()` may change and cause leaks.
8. **Using MDC without cleanup:** the next request on the same thread pool may be tagged with the wrong ID.
9. **Assuming ThreadLocal context automatically crosses CompletableFuture:** missing or wrong context when switching threads.
10. **Using customer IDs as metric labels:** excessively high cardinality.
11. **Treating error messages as stable error codes:** changing wording breaks dashboards and error classification.
12. **Returning raw stack traces to HTTP clients:** exposes implementation details, internal paths, or secrets; return a safe error code and request ID instead.
13. **Trusting IDs from headers without validation:** risks overly long strings, control characters, or log injection.
14. **Logging full URLs/headers/tokens on errors:** increases data security risk.
15. **Attaching `orderId` to errors where the order is not yet determined:** creates false context; use null/omit the field as documented instead of fabricating an ID.
16. **Interpreting timeout/cancel as uncommitted:** verify business state rather than relying on the exception type.

## 18. How to test the investigability of exception logs

A log test suite should assert on **data fields** rather than matching full log strings with dynamic timestamps:

| Scenario | Verification |
|---|---|
| Technical error wrapped in a domain exception | `cause` is non-null and of the right type; `errorCode` is stable |
| Request fails in service | Event contains valid operation, requestId, and business ID |
| API called with missing or overly long ID | Validation/fallback ID works without breaking log format |
| Input contains newline/control characters | Cannot forge a new log line/event |
| Logging across a thread pool | Context does not bleed between two tasks |
| CompletableFuture task fails | Stage/boundary preserves the right context and cause |
| Retries multiple times then succeeds | Distinguishes attempt errors from final outcome |
| Task timeout/cancellation | Has appropriate status; does not falsely log "rolled back" |
| Sensitive data in dependency exception | Logger/redaction does not leak secrets in message/cause |
| Failure across multiple exception layers | Does not emit numerous duplicate ERROR logs for the same cause |

For structured loggers, use a test appender or test collector capable of reading individual fields and the Throwable. For simple Java SE programs, capturing `System.out` works for testing examples, but production should not replace logging tools with print statements.

A good test for log context should include **two different requests on the same single-thread executor**: each task keeps its own request ID, and the second task does not see the first task's ID. This catches MDC leaks that a single-request test misses.

## 19. Logging design checklist for a Java operation

Before finishing an API or background task, review:

- **Operation name:** stable, unambiguous, and aligned with the business boundary.
- **Correlation:** request/correlation/trace ID created or validated at ingress and propagated consistently.
- **Business identity:** only IDs that genuinely aid lookup, without stuffing the full payload.
- **Error classification:** a sufficiently stable `errorCode`, distinguishing final failure, retry, timeout, and cancel.
- **Root cause:** exceptions wrapped with a constructor taking `cause`; logs pass the Throwable to the backend.
- **Logging boundary:** avoid having multiple layers print the same stack trace without adding meaning.
- **Async propagation:** context captured and passed properly across executors/futures; MDC restored/cleaned up.
- **Data minimization:** do not log tokens, secrets, or PII beyond permitted scope; validate input IDs.
- **Diagnostic usefulness:** from a single log line, you can locate the request/trace and the state of related entities.
- **Verification:** test log fields, races/retries, abnormal inputs, and sensitive-data cases.

## 20. Key takeaways

**Adding operation context and useful identifiers for investigation** means leaving enough trail to turn an isolated exception into a searchable, correlatable, and explainable event. At a minimum, this typically includes **operation**, **request/correlation ID**, **business ID if applicable**, **error code**, and the preserved **Throwable/cause**. For asynchronous tasks, intentionally propagate context across thread boundaries.

The value of logs is not measured by the maximum number of fields, but by their ability to answer **exactly what failed, where, for which entity, due to what cause, and what the current state is**, while maintaining security, bounding cardinality, and avoiding misleading information.

### References

- [Java SE 17 — Throwable, cause, and suppressed exceptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)
- [Java SE 17 — RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html)
- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html)
- [SLF4J Manual — MDC and parameterized logging](https://www.slf4j.org/manual.html)
- [OpenTelemetry — Trace and span concepts](https://opentelemetry.io/docs/concepts/signals/traces/)
