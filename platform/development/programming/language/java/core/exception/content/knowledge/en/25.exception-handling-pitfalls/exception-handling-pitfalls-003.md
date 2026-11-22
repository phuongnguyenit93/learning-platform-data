# Logging and Rethrowing Across Multiple Layers: Avoiding Duplicate Errors in Java

> **Topic:** Java Core → Exception → Common Pitfalls. This article analyzes the **log-and-rethrow** anti-pattern: an exception passes through a repository, service, controller, or worker, and each layer logs the error and rethrows it. The goal is to design a **responsible error-logging boundary** that preserves the cause and context, avoids duplicate stack traces, and still does not lose genuinely valuable operational events.

## 1. The Problem: One Failure Can Become Multiple ERROR Lines

Suppose saving an order fails because the database is unavailable. The error passes through three layers:

~~~text
database call
   |
   v
Repository ── catch, ERROR, throw ──>
   |
   v
Service    ── catch, ERROR, throw ──>
   |
   v
Controller ── catch, ERROR, response
~~~

If each layer logs the same stack trace, one actual failure can produce three `ERROR` events, multiple copies of the stack trace, and messages that differ only slightly. The consequences go beyond wasting log storage:

- **Inflated error counts:** dashboards grouped by `ERROR` logs may look like three independent failures when only a single request failed.
- **Hard to identify the final handler:** logs appear in the repository, then the service, then the controller, making it unclear which layer decided to retry, fall back, or return an error externally.
- **Operational overhead:** formatting stack traces, writing logs, shipping, and storing logs increase significantly at high volume.
- **Loss of correlation:** three lines without a correlation ID can be mistaken for three separate requests.
- **Masking real signals:** repeated logs compete with independent errors, making alerts noisy and hard to triage.
- **Data exposure risk:** the same message containing sensitive information gets copied across multiple log sinks.

Practical rule: **when you are only propagating an exception to an upper layer so it can decide how to handle it, you usually do not need to log an `ERROR` and the full stack trace at every intermediate layer**. Instead, attach the `cause`/context and log at a boundary that aligns with outcome ownership.

This rule does not mean every failure across the entire system may produce only a single log line. A retry attempt or a compensation step can be a **separate event** worth logging; the issue is duplicating *the same failure event* without adding new information.

## 2. Defining Log-and-Rethrow and Handling Boundaries

**Log-and-rethrow** is the following pattern:

~~~java
// Illustrative code; log is provided by the application's logging library.
try {
    repository.save(order);
} catch (RuntimeException ex) {
    log.error("save failed", ex);
    throw ex;
}
~~~

This snippet preserves the exception so it does not lose `cause`, but if the upper layer also catches it, logs an `ERROR`, and rethrows, the same failure is recorded multiple times. When many classes adopt this pattern by default, log volume grows with the number of layers the exception traverses.

Distinguish three roles:

1. **Detection site:** where the API cannot complete and the exception is created or thrown; it may not know the full request or business context.
2. **Semantic translation site:** where a technical error is translated into a domain exception or new abstraction; it can add the operation, business ID, and `cause` without logging on the spot.
3. **Outcome decision site:** the HTTP boundary, consumer, scheduled job, CLI, or event loop that decides whether to retry, fall back, fail the request, or stop the job; this is usually the right place to log the **final failure**.

If a layer **actually handles** the error (for example, recovering via a fallback and not rethrowing), that layer may log its own outcome event. If a layer only forwards the error, do not automatically log a full `ERROR` entry.

## 3. Anti-Example: Every Layer Logs and Then Throws

~~~java
// Excerpt of system layers, not a standalone program.
void saveInRepository(Order order) {
    try {
        jdbcWrite(order);
    } catch (SQLException ex) {
        log.error("Repository save failed", ex);
        throw new StorageException("write failed", ex);
    }
}

void placeOrder(Order order) {
    try {
        saveInRepository(order);
    } catch (StorageException ex) {
        log.error("Service placeOrder failed", ex);
        throw new OrderProcessingException("order failed", ex);
    }
}

void handleHttpRequest(Order order) {
    try {
        placeOrder(order);
    } catch (OrderProcessingException ex) {
        log.error("Request failed", ex);
        sendErrorResponse();
    }
}
~~~

The types `Order`, `StorageException`, `OrderProcessingException`, and the helper methods are assumed to be defined by the application; this code only illustrates the anti-pattern. In the flow above:

- `Repository` logs the stack trace and wraps it into a storage exception.
- `Service` logs the already-logged stack/cause chain and wraps it again.
- `Controller` logs the same chain a third time.
- If all three lines are counted as independent failures, the incident rate is multiplied.
- The repeated `"failed"` messages provide no correlation ID, error code, or request state.

Two independent issues must be fixed: **logging location** and **context/cause quality**. Simply deleting logs in lower layers while throwing exceptions without a cause is still insufficient for investigation.

## 4. Standalone Java 17 Example: Three Wrong Logs vs. One Right Log

This example uses `System.out` instead of a logging library to produce **deterministic stdout**. The program does not simulate stack trace cost, but clearly shows the number of `ERROR` events and how `cause` is preserved across layers.

Save as **`LogAndRethrowDemo.java`**:

~~~java
public class LogAndRethrowDemo {
    static final class StorageFailure extends RuntimeException {
        StorageFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class OrderFailure extends RuntimeException {
        private final String orderId;

        OrderFailure(String orderId, Throwable cause) {
            super("place order failed", cause);
            this.orderId = orderId;
        }

        String orderId() {
            return orderId;
        }

        String errorCode() {
            return "ORDER_WRITE_FAILED";
        }
    }

    static void writeToDatabase() {
        throw new IllegalStateException("connection lost");
    }

    static void badRepository() {
        try {
            writeToDatabase();
        } catch (IllegalStateException ex) {
            System.out.println("ERROR repository: " + ex.getMessage());
            throw new StorageFailure("save failed", ex);
        }
    }

    static void badService() {
        try {
            badRepository();
        } catch (StorageFailure ex) {
            System.out.println("ERROR service: " + ex.getMessage());
            throw new OrderFailure("order-42", ex);
        }
    }

    static void badBoundary() {
        try {
            badService();
        } catch (OrderFailure ex) {
            System.out.println("ERROR boundary: " + ex.getMessage());
            Throwable root = rootCause(ex);
            System.out.println("BAD root cause: "
                    + root.getClass().getSimpleName()
                    + ": " + root.getMessage());
        }
    }

    static void goodRepository() {
        try {
            writeToDatabase();
        } catch (IllegalStateException ex) {
            throw new StorageFailure("save failed", ex);
        }
    }

    static void goodService() {
        try {
            goodRepository();
        } catch (StorageFailure ex) {
            throw new OrderFailure("order-42", ex);
        }
    }

    static void goodBoundary() {
        try {
            goodService();
        } catch (OrderFailure ex) {
            System.out.println(
                    "ERROR event=place_order_failed operation=place_order"
                    + " requestId=req-8 orderId=" + ex.orderId()
                    + " code=" + ex.errorCode());

            Throwable root = rootCause(ex);
            System.out.println("GOOD root cause: "
                    + root.getClass().getSimpleName()
                    + ": " + root.getMessage());
        }
    }

    static Throwable rootCause(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    public static void main(String[] args) {
        badBoundary();
        goodBoundary();
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac LogAndRethrowDemo.java
java LogAndRethrowDemo
~~~

**Exact stdout:**

~~~text
ERROR repository: connection lost
ERROR service: save failed
ERROR boundary: place order failed
BAD root cause: IllegalStateException: connection lost
ERROR event=place_order_failed operation=place_order requestId=req-8 orderId=order-42 code=ORDER_WRITE_FAILED
GOOD root cause: IllegalStateException: connection lost
~~~

### Explanation

- **Bad branch:** repository, service, and boundary each log an `ERROR` event; all three `ERROR` lines originate from a single failed database write.
- **Good branch:** repository only translates `IllegalStateException` into `StorageFailure` with a cause; service only translates it into `OrderFailure` with a business ID and cause; the boundary logs **one `ERROR` event** containing the operation, request ID, order ID, and error code.
- The `rootCause` helper walks the cause chain to demonstrate that `IllegalStateException("connection lost")` can still be recovered after two wrapping layers. In real programs, an exception tree can also have `suppressed` exceptions and custom wrappers; do not assume "the deepest cause is the whole truth".
- The two calls (`badBoundary()` and `goodBoundary()`) in `main` are **two independent demonstration runs**, not two attempts on the same production request.
- The `GOOD root cause` line is an explanatory line for the reader, **not a second ERROR log**. In production, log the entire `Throwable` once at the boundary so the logging backend preserves the stack trace, cause chain, and suppressed exceptions.

Using `System.out` in this example is not a recommendation for production logging. Choose a logger with appropriate levels, structured fields, and centralized collection.

## 5. New Design: Throw with Context, Log Where Responsibility Lives

A design pattern that usually fits layered applications:

~~~text
Repository
  -> catch technical error when abstraction translation is needed
  -> throw StorageException(cause)

Service
  -> add business operation or error code
  -> throw OrderException(cause)

Boundary
  -> classify error / decide HTTP status or job outcome
  -> log one failure event with context + Throwable
  -> return response / mark task failed / propagate error per contract
~~~

Benefits:

- Each boundary has a clear responsibility: semantic translation, adding context, or handling the outcome.
- No need to log when there is no independent operational action.
- The final log can include `requestId`, `traceId`, business ID, error code, and `cause`.
- A single final failure is easy to count in metrics/alerts.
- Unit tests can verify exception types and causes without asserting log text at every layer.

**Choose the log owner by error-handling authority, not just by class name.** In an HTTP server, a global exception handler is often where unhandled errors are resolved. In a small CLI, `main` may be where errors are printed. In a worker, the task lifecycle manager or message consumer may be the boundary. In a reusable library, it is usually better to throw exceptions for the host application to decide rather than logging `ERROR` by default.

## 6. Which Boundary Should Hold the Log?

| Location | What It Should Usually Do | Should It Log ERROR? |
|---|---|---|
| DAO/repository | Preserve `cause` when translating technology errors into storage errors | Not by default if the caller still handles it |
| Application service | Add operation, business ID, error code; propagate | Not by default if it does not own the outcome |
| REST controller/global handler | Map error to response, log final failure event | Usually appropriate when the error is severe enough |
| Message consumer | Decide ack/retry/dead-letter; log outcome | Appropriate if it truly owns message handling |
| Scheduled job boundary | Decide job failed, retry, or stop | Appropriate for the final failure |
| Background CompletableFuture | Preserve exceptional completion; consumer observes outcome | Only log independently if the result may have no consumer |
| Low-level shared library | Throw semantically, document causes | Avoid spamming/error logging at every caller |
| Retry attempt handler | May log attempt event, metrics, backoff | WARN/DEBUG/metrics when not yet the final failure |

**Do not force a single boundary across an entire distributed system.** Service A may log that an incoming request to A failed, and Service B may also log the corresponding request to B, because they are two different deployment units/owners. You need `traceId`, `spanId`, and correlation IDs to link them, but not every log across multiple services is a bad duplicate. The problem is the same layer or the same local control flow throwing through multiple classes where each class emits an error record with no new meaning.

## 7. Preserving Cause and Exception Types

Removing log-and-rethrow at every layer **does not mean discarding the error cause**. A repository can translate a technical error into an exception better suited to the storage layer:

~~~java
try {
    jdbcWrite(order);
} catch (java.sql.SQLException original) {
    throw new OrderStorageException("order persistence failed", original);
}
~~~

This is an illustrative snippet; `OrderStorageException` needs a `(String, Throwable)` constructor and `jdbcWrite` must be declared. If `SQLException` already fits the contract, letting it propagate or `throw original;` is also appropriate. Do not create multiple `RuntimeException("failed", error)` wrappers across layers when they add no semantic value.

The core idea of **log ownership** is that each layer preserves the cause and supplies necessary context, without logging the same stack trace in the repository, service, and controller when handling a single failure. A separate article on causes explains how to construct, preserve, and traverse exception chains.

## 8. Adding Context in the Right Place, Avoiding Generic Messages

A final log record should help answer: **what operation**, **which request/task**, **which business entity**, **which dependency**, and **what error**.

~~~json
{
  "level": "ERROR",
  "event": "order_persist_failed",
  "operation": "place_order",
  "requestId": "req-8",
  "orderId": "order-42",
  "errorCode": "ORDER_WRITE_FAILED",
  "dependency": "orders-db",
  "exceptionType": "OrderFailure",
  "causeType": "IllegalStateException"
}
~~~

This is an **illustrative schema**, not output generated by the Java example. In production, a structured logger can record these fields separately and attach the `Throwable` to preserve the stack trace and cause. Avoid concatenating text into a single message that cannot be queried by field.

Reference for IDs:

- `requestId`: find all events within a specific request.
- `traceId`: connect the journey across services when distributed tracing is used.
- `orderId`: trace operations on a specific order; does not replace `requestId`.
- `jobRunId`/`messageId`: needed for workers, queues, and batches.
- `attempt`: distinguish a retry attempt from the final outcome.
- `errorCode`: stable error grouping, not a random ID.

**Carry context across layers without logging multiple times.** You can pass an immutable context object or attach typed fields to domain exceptions. A logging framework's MDC is convenient, but it requires cleanup and context propagation across thread pools; it does not automatically propagate across every `CompletableFuture` or executor.

## 9. When Are Intermediate Logs Still Appropriate?

There is no absolute "log only once" rule. An intermediate log can be right if it describes a **distinct operational event**:

### 9.1. Meaningful Retry Attempts

~~~text
WARN  event=dependency_attempt_failed operation=save_order attempt=1 willRetry=true
WARN  event=dependency_attempt_failed operation=save_order attempt=2 willRetry=true
ERROR event=order_save_failed operation=save_order attempts=3 final=true
~~~

If an application hits two transient failures before failing on the final attempt, the attempts are separate events that help analyze backoff and circuit breakers. However, you do not need three identical stack traces: you can log lightweight info at `WARN`/`DEBUG`, emit per-attempt metrics, and record the full stack/cause for the final failure. If the final retry succeeds, log a **success outcome** and do not count transient attempts as final request failures.

### 9.2. Failed Compensation or Rollback

For example, a money transfer fails and the compensation/rollback step also fails. These are **two different failures**, not logging the same exception twice. A separate log event for a compensation failure can be critical because it changes business state.

### 9.3. Locally Handled Errors

A lower layer may catch an error from provider A, fall back to provider B, and succeed. It does not throw the same error upward; a `fallback_used` event or metric is appropriate when operations need visibility. Do not automatically use `ERROR` if fallback is an expected strategy and users are unaffected.

### 9.4. Different Ownership Boundaries

One microservice calling another may log an outbound dependency failure; the receiving service also logs the inbound failure within its own scope. Each event should have a clear message/operation, trace context, and avoid duplicating `eventId` or treating one failure as three independent incidents.

**Criterion:** does the intermediate log answer a new question that the final log cannot? If it only logs `"failed"` + the same stack trace, it is usually not worth logging.

## 10. Do Not Turn Every Exception into ERROR

Log levels must be based on **expectedness and actual impact**, not merely the presence of a `catch`:

| Situation | Reasonable Level to Consider | Notes |
|---|---|---|
| Invalid client input, returning 400 response | INFO/WARN or metrics only | May be an expected flow; avoid flooding |
| Record already processed (idempotency) | DEBUG/INFO | Not necessarily an error |
| Transient retry, recovery still possible | WARN/DEBUG or metrics | `attempt` and `willRetry` are valuable |
| Final dependency failure, request fails | ERROR | Log final failure once with full context |
| User intentionally cancels operation | DEBUG/INFO | `CancellationException` is not necessarily an incident |
| Invariant violation or coding bug | ERROR | Preserve stack trace/cause |
| Timeout after task may have committed | WARN/ERROR depending on impact | Do not assume it rolled back |

If overly broad logging causes error alerts to count every invalid input or cancellation, the operations team can lose trust in dashboards. Conversely, do not downgrade the severity of a data-loss error just because it was caught and retried once.

## 11. Log-and-Rethrow Inside Loops or Batches

A worker processing 100,000 records may encounter malformed data frequently. If every invalid record logs a stack trace in the parse layer, validation layer, and batch layer, log volume grows non-linearly along the error-handling chain.

Avoid:

~~~java
// Illustrative code: parse, validate, and batch handle the same error.
try {
    processRecord(record);
} catch (ValidationException ex) {
    log.error("record error", ex);
    throw ex;
}
~~~

If invalid records are an expected outcome, you can use a `ValidationResult` or aggregate errors by code to report back to the user, without needing an exception/stack trace for every record. If one invalid record causes the entire batch to fail, the batch boundary can log `batchId`, `recordId`, `errorCode`, and the number of processed items.

**Performance is not the only reason:** triage improves when logs reflect "one batch failed" and the relevant records, rather than tens of thousands of uncorrelated `ERROR` lines.

## 12. Log-and-Rethrow in CompletableFuture and ExecutorService

With asynchronous work, a common source of duplicate logs is:

~~~java
// Excerpt; serviceAsync returns CompletableFuture and log is already available.
CompletableFuture<String> stage =
        serviceAsync().whenComplete((value, error) -> {
            if (error != null) {
                log.error("async failed", error);
            }
        });

// Later, the boundary still calls stage.join() and logs the same error again.
~~~

`whenComplete` is primarily for **observation**; by default it does not turn a failure into a successful result. If the upstream stage completes exceptionally, downstream stages usually complete exceptionally as well; a boundary calling `join()` can catch `CompletionException` and log a second time. Therefore:

- If the boundary is guaranteed to receive and handle the result, prefer letting the pipeline propagate the failure and logging at the boundary.
- If the task is strictly *fire-and-forget* with no caller consuming the `Future`, you need a **responsible error-monitoring point** inside the worker or result handler. Do not rely on "log at the end" when nobody is actually observing the end.
- `ExecutorService.submit` stores exceptions inside the `Future`; if nobody calls `get()` or inspects the future, the error may never be reported to the application. Design clear future/monitoring ownership.
- `Thread.UncaughtExceptionHandler` helps capture uncaught errors on raw threads, but does not replace the error mechanism of `FutureTask` or pipelines.
- When a `whenComplete` callback performs additional work that can throw an exception, the new stage may carry a different error; check the API semantics before placing logging side effects there.

### Unwrapping at the Right Level

~~~java
// Illustrative code; a method with CompletableFuture<String> future.
try {
    String value = future.join();
    consume(value);
} catch (java.util.concurrent.CancellationException ex) {
    handleCancellation(ex);
} catch (java.util.concurrent.CompletionException ex) {
    Throwable cause = ex.getCause();
    handleFailure(cause == null ? ex : cause);
}
~~~

`consume`, `handleCancellation`, and `handleFailure` are application-defined methods; this snippet is not standalone. Do not log both `CompletionException` and `cause` as **two `ERROR` events** just because two exception objects are involved. Pass the full `Throwable` with its cause to the logger and add context at the boundary.

With `Future.get()`, computation errors usually arrive via `ExecutionException`; `InterruptedException` indicates the **waiting thread** was interrupted, not a business failure from the task. Do not catch broadly and log every exception as the same root cause.

## 13. Do Not Let Logging Operations Mask the Original Exception

In most cases, loggers are designed to be reliable, but auxiliary operations such as serializing objects, computing arguments, calling `toString()`, enriching context, or sending to an external sink **can fail or block**. Bad example:

~~~java
// Illustrative; formatter and auditSink are application dependencies.
catch (RuntimeException original) {
    String payload = formatter.format(hugeMutableRequest);
    auditSink.send(payload); // If this throws, original may be masked.
    throw original;
}
~~~

Here, if `formatter` or `auditSink` fails, `throw original;` may never execute. If sending an audit event is a mandatory business responsibility, define an explicit contract for **two independent failures** and a transaction/outbox policy; never assume logging cannot affect control flow.

Recommended approach:

- Avoid putting complex computations or accessing large mutable data structures inside log arguments.
- Use minimal structured fields with validated data and sensitive-data boundaries.
- With standard loggers that offer parameterized APIs, pass the `Throwable` to the backend to preserve the cause and stack trace.
- Do not swallow `InterruptedException` while waiting to send logs; if you cannot propagate it, consider restoring the interrupt flag and terminating according to policy.
- If you must catch an error raised during related cleanup, preserve the original exception and secondary failure information (`addSuppressed` when appropriate) rather than silently replacing it.
- Avoid `System.out.println` as the sole production error-management mechanism because it lacks levels, structure, and reliable collection pipelines.

## 14. Multi-Level Logging with Common Libraries

SLF4J, Log4j, or `java.util.logging` are options with their own API contracts. SLF4J example (requires dependencies and a logging backend, **not a standalone JDK program**):

~~~java
// log: org.slf4j.Logger; context and ex are already in scope.
log.error(
        "event=order_write_failed operation={} requestId={} orderId={}",
        context.operation(), context.requestId(), context.orderId(), ex);
~~~

When using SLF4J, check the overload and `Throwable` handling in your specific version to ensure the last argument is logged as a stack trace rather than only formatted as a value. If the backend supports structured key-value pairs, prefer emitting separate fields for querying instead of concatenating one long message.

### MDC and Async Context

Logging frameworks may provide MDC to attach request/correlation IDs to every event on the current thread. However:

- `ThreadLocal`/MDC does not automatically propagate to every executor or `CompletableFuture` stage.
- Thread pools reuse threads; context not cleared in `finally` can cause request B to emit logs carrying request A's ID.
- MDC is a **way to enrich logs**, not the sole place to store business information required by the exception contract.
- If you need to log at an async boundary, pass an immutable context into the task or use framework-supported context propagation.

Do not work around "log once at the boundary" by catching and logging at every layer just because that layer is the last place `requestId` is visible. Design the context propagation path first.

## 15. Security and Stability of Log Context

Logging fewer times does not help if every log still contains secrets. Things that **should not be placed verbatim** into exception messages or logging fields without clear justification and protection:

- Passwords, API keys, access tokens, refresh tokens, cookies, authorization headers.
- Full payment card details or secret verification codes.
- Full request/response bodies, personal data, or health information when unnecessary.
- Connection URLs containing credentials, SQL with sensitive literals, or `toString()` outputs that may leak secrets.
- Externally supplied IDs that have not been checked for length, control characters, or log injection risks.

Prefer `requestId`, `traceId`, `operation`, `errorCode`, `dependency`, and approved business IDs. Validate client-supplied IDs: enforce length limits, character sets, trim/control character stripping, anti-log-forging protections, and namespace separation. Logs may be copied to other systems with broader access permissions, so apply appropriate retention and access controls.

An `orderId` can be linked back to a user when combined with other data; do not equate "ID" with "non-sensitive".

## 16. Stack Trace, Cause, and Suppressed Exceptions: What Is Enough?

Java `Throwable` stores useful diagnostic information:

- **Type:** the exception class.
- **Message:** description of the situation, not necessarily a stable error code.
- **Stack trace:** the frames at the throw/creation site according to `Throwable` semantics.
- **Cause:** the wrapped cause accessible via `Throwable.getCause()`.
- **Suppressed exceptions:** commonly appear when closing resources in `try-with-resources` or when application code calls `addSuppressed`.

When a layer logs only `ex.getMessage()` and then throws, that layer's log may lack the full cause/stack, while the final layer may receive the complete chain. The goal is **one complete diagnostic event**, not scattered fragments across layers that must be pieced together manually.

In `try-with-resources`, resource-closing failures can be attached to `getSuppressed()` on the primary exception. If you only log the root cause via `rootCause(ex).getMessage()`, cleanup failure details can be lost. In production, pass the `Throwable` object itself to the logger so the backend can surface the entire related structure.

**Do not collapse every throwable to its deepest root cause and discard the wrapper layers.** Wrappers can carry IDs, error codes, and abstraction meaning. The root cause is one perspective, not a replacement for the full exception chain.

## 17. Monitoring and Metrics: One Log Is Not One Failure Count

Many dashboards count `ERROR` logs as if they were failed requests. With multi-layer log-and-rethrow, that count is usually wrong.

Choose semantically meaningful metrics:

- `requests_total{status="failed",operation=...}`: counts **requests** that ended with a failed outcome.
- `job_runs_total{outcome="failed"}`: counts failed job runs.
- `retry_attempts_total{dependency=...,result=...}`: counts retry attempts, separate from final failures.
- `exceptions_observed_total` if used: reflects observed exception events, not automatically equated to failed business transactions.

These are **illustrative metric names**, not a mandatory standard schema. For metrics, do not attach `requestId` or `orderId` as labels: cardinality becomes huge. Specific IDs belong in logs and traces; metrics by `operation`/`errorCode`/`dependency` support aggregation.

Reducing `ERROR` logs from three to one does not mean reliability magically improved threefold. **You reduced duplicate logs**, not actual exceptions. Evaluate observability and error-handling code quality separately.

## 18. Testing Log Ownership and Exceptions

A good test suite verifies both program behavior and logging strategy:

| Scenario | What to Assert |
|---|---|
| Repository throws technical error | Service receives `cause`; no duplicate `ERROR` printed in repository |
| Service wraps domain error | Wrapper has the right error code/ID; `cause` is preserved |
| Boundary handles final failure | One failure event with `operation`/`requestId`/`businessId` and `Throwable` |
| Retry then succeed | Final outcome is not counted as failed; attempt metrics are separate |
| Retries exhausted | Final failure logged once; attempt metadata sufficient for investigation |
| Fallback handles error | No final error if the contract treats recovery as success |
| CompletableFuture fails | An owner receives exceptional completion; no lost error or duplicate log |
| Cancellation/interrupt | Valid cancellation does not accidentally log `ERROR`; interrupt signal is handled |
| Error during cleanup | Original exception remains; secondary error is linked or reported appropriately |
| Two requests on one thread pool | MDC/context does not leak across requests |
| Exception contains sensitive info | Logs/responses do not expose data outside policy |
| Logging backend fails | Application policy does not silently lose primary error information |

Application unit tests can use a test appender or in-memory logger to **count log events by code/name**, rather than just matching text. Also use `assertThrows` and check `getCause()`/error codes for exception-translating layers. Separate logging-strategy tests from request-behavior tests to avoid coupling to backend formatting details.

**Test errors on both the async path and the caller path:** if a callback logs and the `join()` boundary also logs, tests should catch the two duplicate events and help eliminate one. If there is no future consumer, tests must prove the failure event still reaches the monitoring channel.

## 19. Code Review Checklist for Multi-Catch/Log Code

When you see the same exception passing through multiple `catch` blocks, ask in order:

1. **Is this one failure or multiple distinct failures?** Check the original exception/cause, `requestId`, `attempt`, and event type.
2. **Which layer owns the outcome?** Who decides to retry, fall back, return a response, or mark a job failed?
3. **Does this `catch` do anything besides log and throw?** If not, consider removing the `catch` or keeping only abstraction mapping.
4. **If we remove logging at this layer, what context is lost?** Move that context into the exception, result, MDC, or tracing before deleting the log.
5. **Is `cause` preserved?** When wrapping, use a constructor that accepts `cause`; do not create a new `RuntimeException` that drops the origin.
6. **Is the information in the log useful?** Operation, IDs, error code, dependency, attempt, rollback/commit state.
7. **Is there already a complete final log elsewhere?** If so, check whether logs in other layers reflect genuinely independent events.
8. **Does severity reflect impact?** Expected validation, cancellation, or retry events are not always `ERROR`.
9. **Are there duplicate stack traces from framework auto-logging?** For example, a request error handler plus a servlet/container logger, or a background task logger.
10. **Is there sensitive data in the message, cause, or context?** Remove or redact it in the right place.
11. **Is there unobserved async code?** Check `Future`/`CompletableFuture` and monitoring channels if fire-and-forget.
12. **Are tests and metrics still accurate after refactoring?** Reduce duplicate logs without losing information about the final failure.

## 20. Conclusion

**Logging and rethrowing across multiple layers** is a common pitfall because it duplicates one failure into multiple `ERROR` events, complicates diagnosis, increases logging cost, and can skew dashboard counts. When the current layer only **propagates an error**, rethrow or wrap it with `cause` and add semantically appropriate context. When a layer **owns the final outcome**, log one failure event with the operation, correlation/business IDs, error code, and full `Throwable`.

**Do not confuse "log at the boundary" with "forbid all intermediate logs".** Retry attempts, fallbacks, compensations, audits, or distinct service boundaries can all be separate events worth logging — as long as each event has a clear purpose, severity, and identity.

Self-check rule: *If I delete the log line in this layer, is investigative information lost? If yes, can that information be carried as context so the boundary logs it once?* The answer leads to a more maintainable exception-handling design and a more trustworthy logging system.

### References

- [Java SE 17 — Throwable: cause, stack trace, suppressed exceptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)
- [Java SE 17 — RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html)
- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [SLF4J Manual — parameterized logging](https://www.slf4j.org/manual.html)
