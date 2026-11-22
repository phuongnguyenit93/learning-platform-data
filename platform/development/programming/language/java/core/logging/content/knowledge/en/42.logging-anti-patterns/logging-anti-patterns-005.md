# Logging the Same Exception Multiple Times — Anti-Pattern in Java Core Logging

## 1. Problem and Impact

**Logging the same exception multiple times** occurs when **the same failure occurrence** is logged repeatedly across the repository, service, controller, exception handler, or asynchronous callback, often with **the same stack trace**. The classic pattern is **log-and-rethrow**: each layer catches the exception, calls `logger.error(...)`, and then rethrows it to the upper layer, where it is logged again.

~~~text
[Repository] ERROR save failed
java.sql.SQLException: connection timed out
   at ...
[Service] ERROR checkout failed
java.sql.SQLException: connection timed out
   at ...
[Controller] ERROR request failed
java.sql.SQLException: connection timed out
   at ...
~~~

A single request can generate **three ERROR records** even though there is only one root cause and one failed outcome. The resulting issues include:

- Slow diagnosis because three identical stack traces obscure other signals.
- Inaccurate alerts and dashboards if `count(level=ERROR)` is treated as the number of failed requests.
- Increased I/O, stack trace formatting CPU, ingest bytes, retention, and backend costs.
- The same exception content—potentially containing SQL, URLs, tokens, or PII—being duplicated across multiple sinks.
- Different layers emitting different messages, making a single failure look like three separate causes.
- When combined with retries or asynchronous work, difficulty distinguishing which log belongs to an **attempt** and which belongs to the **final failure**.

**Core principle:** it is usually best to keep **a single boundary responsible for logging the final failure**, preserve `cause` across layers, and add context via typed exceptions, `errorCode`, or structured fields. Not every class with a `catch` block needs to log an ERROR.

**Do not apply the “log once” slogan dogmatically.** An audit event, a scheduled retry, an executed fallback, or a genuine business decision may deserve its own log entry. What needs to be eliminated is **multiple synonymous records emitted solely because an exception passes through multiple catch blocks**, not genuinely distinct events.

## 2. Distinguish Types of “Duplicates” Before Fixing

| Symptom | Nature | Diagnostic Direction |
| --- | --- | --- |
| **Logging the same Throwable multiple times in code** | Multiple logger calls, e.g., DAO → service → HTTP handler | Find `log-and-rethrow`, choose an owner |
| **One LogEvent reaching a sink twice** | One log call routed through multiple appenders/handlers to the same destination | Check Logback `additivity`, JUL parent handlers |
| **One record duplicated by a collector** | Two shippers or stdout + file both ingesting, batch retries | Compare source/offset, collector, exporter |
| **Valid retry/redelivery** | Multiple actual attempts, each with its own event | Use `attempt`, `messageId`, outcome |
| **One stack trace with multiple “Caused by”** | Cause chain of a single Throwable | Do not count each “Caused by” as a separate log event |
| **Two independent requests failing similarly** | Two genuine failure occurrences | Distinguish by requestId/traceId/instance |

One Throwable instance can be thrown across three layers and logged by all three. However, a new Throwable wrapped with `new DomainException(..., ex)` can still represent **the same original failure**, not necessarily a new error. Conversely, two requests producing two Throwables with identical messages are still two real failures.

**Count the right units:**

- `LogRecord`/`LogEvent` = logging event after level/filter evaluation.
- `Throwable` = exception object, which can be rethrown and logged multiple times.
- `attempt` = a single processing attempt.
- `operationId`/`requestId`/`messageId` = business or correlation unit, which may contain multiple events.
- `errorCode` = **error category**, not unique to a single failure occurrence.
- `errorOccurrenceId` = ID of a specific failure occurrence if the system defines that contract.
- Log `eventId` = ID of a single source record if transport-level deduplication is needed.

Do not deduplicate solely by exception message, error code, or rounded timestamp: doing so can delete valid independent events.

## 3. Java Anti-Pattern: Log and Rethrow

The example below consists of **three illustrative snippets**, not a complete program: `log` (SLF4J), `order`, `orderRef`, `saveToDatabase(...)`, and the helpers are application components.

~~~java
// Repository: log the error and rethrow.
try {
    saveToDatabase(order);
} catch (SQLException ex) {
    log.error("database save failed orderRef={}", orderRef, ex);
    throw ex;
}

// Service: log the same exception again and rethrow.
try {
    orderRepository.save(order);
} catch (SQLException ex) {
    log.error("checkout failed orderRef={}", orderRef, ex);
    throw ex;
}

// HTTP boundary: print the same stack trace a third time.
try {
    checkoutService.checkout(order);
} catch (SQLException ex) {
    log.error("request failed orderRef={}", orderRef, ex);
    return serverErrorResponse();
}
~~~

If the controller rethrows to `@ControllerAdvice` and the global handler also logs, it can become four times. The fault does not lie in `SQLException`; it lies in **how logging responsibility is assigned**.

### Alternative Approach

The repository translates the infrastructure error into a meaningful exception and **preserves the cause**, without printing a stack trace:

~~~java
// Snippet in the repository adapter.
try {
    saveToDatabase(order);
} catch (SQLException ex) {
    throw new OrderStorageException(
            "ORDER_STORAGE_UNAVAILABLE", ex);
}
~~~

The service can let it propagate, or translate the abstraction once if truly needed, without logging the same cause.

The final boundary knows `requestId`, `operation`, and the final outcome:

~~~java
// Snippet in the HTTP boundary; do not rethrow after returning the response.
try {
    checkoutService.checkout(order);
    return successResponse();
} catch (OrderStorageException ex) {
    log.error(
        "event=checkout_failed errorCode={} requestId={} orderRef={}",
        ex.errorCode(), requestId, safeOrderRef, ex);
    return serverErrorResponse();
}
~~~

The snippet above requires the `OrderStorageException` class and application helpers/variables. When a framework already provides a global exception handler in this role, let the handler log and return the response; **do not log in the controller and also rethrow for the framework to log again**.

**Why is preserving the cause important?** A typed exception keeps upper layers independent of SQL/JDBC, while `cause` helps engineers identify the real root cause. Do not replace it with `new OrderStorageException("...", null)` and lose context; likewise, do not copy raw `ex.getMessage()` containing secrets into a public error response.

## 4. A Clear Ownership Rule Across Layers

| Layer | Responsibility | Typical Sound Exception Logging Policy |
| --- | --- | --- |
| Repository / JDBC adapter | Classify storage errors, preserve cause | **Do not log stack trace** if rethrowing upward |
| Domain/service | Enforce rules, translate exceptions, fallback or retry | Log a **new event** when making a recovery decision; do not log on every catch/rethrow |
| HTTP `@ControllerAdvice` / error boundary | Map status, return safe error, determine final outcome | One final failure event and throwable to an internal sink |
| Message consumer | ACK/NACK, retry, DLQ, determine message outcome | Log attempt/outcome per policy, do not log stack trace in every callback |
| Job/scheduler coordinator | Determine job failed/succeeded, retry budget | Owner of the final job failure |
| Async caller/worker | Track Future/stage and decide outcome | Pick **one owner**; avoid both worker and caller logging the stack trace |
| Security/audit module | Record sensitive actions per independent policy | **May be required** to emit a separate audit event |
| Logging backend/collector | Format and forward events to sinks | Do not unintentionally duplicate the same event |

**Heuristic:** *“If this layer only rethrows the same failure upward without handling it, does this log entry add anything that cannot be captured at the boundary?”* If not, usually omit the log. If this layer took a new action such as a retry, rollback, circuit-breaker transition, or compensation, that may be a **semantically different event**, not a duplicate.

A system may have multiple boundaries: HTTP requests, message processing, background jobs. An inter-service request may produce outcomes in each service. What matters is **having a counting and ownership convention per operation**, rather than forcing an entire distributed trace to have only one ERROR.

## 5. Standalone Java 17 Demo: From Three LogRecords Down to One

The following program uses only **JDK 17** (`java.util.logging`). `Capture` is a test handler that stores `LogRecord`s in memory, helping distinguish **the number of events emitted to a sink** from the number of stack trace lines. The program runs sequentially with no real DB connection.

Save the file as **`DoubleExceptionLogDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class DoubleExceptionLogDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.double.exception");

    static final class StorageException extends RuntimeException {
        StorageException(Throwable cause) {
            super("storage failed", cause);
        }
    }

    static final class Capture extends Handler {
        final List<LogRecord> records = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                records.add(record);
            }
        }

        @Override
        public void flush() {
            // No buffered I/O to flush.
        }

        @Override
        public void close() {
            // Holds no external resources.
        }

        void clear() {
            records.clear();
        }
    }

    static void repository() {
        throw new StorageException(
                new IllegalStateException("connection interrupted"));
    }

    // Wrong approach: repository logs and rethrows.
    static void repositoryBad() {
        try {
            repository();
        } catch (StorageException ex) {
            LOG.log(Level.SEVERE,
                    "event=repository_failed errorCode=STORAGE_UNAVAILABLE",
                    ex);
            throw ex;
        }
    }

    // Wrong approach: service logs and rethrows.
    static void serviceBad() {
        try {
            repositoryBad();
        } catch (StorageException ex) {
            LOG.log(Level.SEVERE,
                    "event=service_failed errorCode=STORAGE_UNAVAILABLE",
                    ex);
            throw ex;
        }
    }

    static void boundaryBad() {
        try {
            serviceBad();
        } catch (StorageException ex) {
            LOG.log(Level.SEVERE,
                    "event=request_failed errorCode=STORAGE_UNAVAILABLE",
                    ex);
        }
    }

    // Good approach: boundary takes responsibility for logging the final error.
    static void boundaryGood() {
        try {
            repository();
        } catch (StorageException ex) {
            LOG.log(Level.SEVERE,
                    "event=request_failed errorCode=STORAGE_UNAVAILABLE",
                    ex);
        }
    }

    public static void main(String[] args) {
        Level previousLevel = LOG.getLevel();
        boolean previousParent = LOG.getUseParentHandlers();

        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        LOG.setLevel(Level.ALL);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(capture);

        try {
            boundaryBad();

            System.out.println(
                    "before_log_records=" + capture.records.size());

            Throwable first = capture.records.get(0).getThrown();
            boolean sameThrowable = capture.records.stream()
                    .allMatch(r -> r.getThrown() == first);
            System.out.println(
                    "before_same_throwable=" + sameThrowable);

            capture.clear();
            boundaryGood();

            System.out.println(
                    "after_log_records=" + capture.records.size());
            System.out.println(
                    "after_preserves_cause="
                    + (capture.records.get(0)
                            .getThrown().getCause() != null));
        } finally {
            LOG.removeHandler(capture);
            LOG.setUseParentHandlers(previousParent);
            LOG.setLevel(previousLevel);
            capture.close();
        }
    }
}
~~~

Compile/run commands:

~~~bash
javac -encoding UTF-8 DoubleExceptionLogDemo.java
java DoubleExceptionLogDemo
~~~

**Deterministic stdout:**

~~~text
before_log_records=3
before_same_throwable=true
after_log_records=1
after_preserves_cause=true
~~~

Analysis:

1. `repository()` creates a `StorageException` with `IllegalStateException` as its `cause`.
2. `repositoryBad()` and `serviceBad()` call `LOG.log(Level.SEVERE, ..., ex)` and then `throw ex`, keeping **the same Throwable object**.
3. `boundaryBad()` logs again, so `Capture.records` contains three `LogRecord`s referencing the exact same Throwable. This is concrete evidence of the anti-pattern.
4. `boundaryGood()` does not log in the lower layers, logging only once at the boundary; `getThrown().getCause()` remains non-null so the cause chain is not lost.
5. `setUseParentHandlers(false)` prevents the JUL root handler from emitting extra unintended console text; it is not the primary fix for the code anti-pattern.
6. `Capture.records` uses `ArrayList` because the demo runs sequentially. Do not use this handler as a concurrent production logging library; for multi-threaded tests, use proper synchronization and a suitable capture mechanism.
7. The demo uses fixed event messages and does not print stack traces so the output is verifiable. Real loggers/backends may format Throwables differently; counting `LogRecord`s is more reliable than counting text lines.

Equivalent logic was executed with JShell using APIs present in Java 17, producing the exact four lines above. This **is not a claim of compiling the file with a local JDK 17 `javac` binary**.

## 6. Do Not Log at Every Catch, Yet Preserve Context

An exception should be **classified by contract**, not guessed from message strings:

~~~java
// This is an application-specific class snippet.
public final class OrderStorageException extends RuntimeException {
    private final String errorCode;

    public OrderStorageException(String errorCode, Throwable cause) {
        super("Order persistence failed", cause);
        this.errorCode = errorCode;
    }

    public String errorCode() {
        return errorCode;
    }
}
~~~

In a repository adapter, `catch(SQLException ex)` can throw `new OrderStorageException("ORDER_STORAGE_UNAVAILABLE", ex)`. Another layer can add `orderRef`/`retryBudget` to structured context without needing to print a stack trace. At the boundary, the error code, `requestId`, outcome, and throwable are sufficient for investigation.

**A wrapper exception does not automatically increase the failure count.** An `OrderStorageException` with a `Caused by: SQLException` is a **cause chain** within a single event if logged only once. `Throwable.addSuppressed(...)` or try-with-resources can also add `Suppressed` entries to a stack trace; do not treat each section as a separate log event.

When translating exception types, avoid:

~~~java
// Wrong if it loses the root cause:
throw new OrderStorageException("ORDER_STORAGE_UNAVAILABLE", null);

// Right when the cause needs to be preserved:
throw new OrderStorageException("ORDER_STORAGE_UNAVAILABLE", ex);
~~~

Here `ex` is the caught Throwable; the snippets are not standalone runnable code. Do not copy a dependency's raw exception message into a public API response: it may contain SQL, URLs, tokens, or sensitive information.

### When Should a Middle Layer Log?

When that layer **genuinely makes a meaningful decision**:

- `event=retry_scheduled` with `attempt`/`retryDelayMs`.
- `event=fallback_used` when switching to a backup endpoint succeeds.
- `event=circuit_breaker_opened` when the circuit breaker state changes.
- `event=compensation_started` when a saga begins an intentional rollback.
- `event=access_denied` in the security/audit trail if policy requires it.

These differ in **event type**, not merely by changing `"Error occurred"` to `"Service failed"`. It is not always necessary to log a full stack trace for every intermediate event.

## 7. SLF4J: Passing Throwable According to the API

In SLF4J, pass the Throwable as an exception argument so the backend manages the stack trace. For example:

~~~java
// Snippet in boundary; LOG is org.slf4j.Logger.
LOG.error("event=checkout_failed errorCode={} requestId={} orderRef={}",
        "ORDER_STORAGE_UNAVAILABLE", requestId, safeOrderRef, ex);
~~~

The variables are supplied by the application. With a conforming SLF4J implementation, the trailing Throwable argument is treated as the cause; there is no need to manually stringify the stack trace. For maximum clarity when no placeholders are needed, you can use:

~~~java
LOG.error("event=checkout_failed", ex);
~~~

Common mistakes:

~~~java
// Wrong: log-and-rethrow allows upper layers to print the same Throwable again.
catch (OrderStorageException ex) {
    LOG.error("event=checkout_failed", ex);
    throw ex;
}

// Wrong: System.err and the logging backend both print the same exception.
catch (OrderStorageException ex) {
    ex.printStackTrace();
    LOG.error("event=checkout_failed", ex);
    return errorResponse();
}

// Risk: the exception message is duplicated and may contain PII/secrets.
LOG.error("event=checkout_failed detail=" + ex.getMessage(), ex);
~~~

The `catch` blocks are snippets requiring appropriate `try`, `LOG`, and response helpers. `Throwable#printStackTrace()` prints to `System.err` by default and bypasses structured logging/correlation; when the backend also logs the Throwable, the console may show two stack traces.

**Avoid forcing an exception into a `{}` placeholder just to display `toString()`.** When the goal is a stack trace, use the explicit form `LOG.error("Failure", ex)` or place it at the end of the argument list per the SLF4J contract. Test with your active provider/backend to observe the actual output.

### Fluent API in SLF4J 2.x

~~~java
// Snippet, only use when the application has SLF4J 2.x.
LOG.atError()
   .addKeyValue("event", "checkout_failed")
   .addKeyValue("errorCode", "ORDER_STORAGE_UNAVAILABLE")
   .addKeyValue("requestId", requestId)
   .setCause(ex)
   .log("Checkout failed");
~~~

This produces one log event with one cause. Whether key–values are emitted as JSON depends on the encoder/layout; it does not happen automatically just by using the fluent builder. The Fluent API does not exist in SLF4J 1.7, and forgetting `log()` will prevent the event from being emitted.

## 8. HTTP Controller and Global Exception Handler

In a web application, an exception can pass through a controller, interceptor, servlet filter, error resolver, and `@ControllerAdvice`. Each layer **may** log depending on implementation/configuration, though not all of them log automatically.

~~~text
Request -> Controller -> Service -> Repository throws
             |
             +-- catch/log/rethrow?
             |
             v
         Global exception handler
             |
             +-- map status/public-safe error
             +-- log terminal failure?
             |
             v
         HTTP response
~~~

If the controller logs the full stack trace and rethrows, and the global handler logs it again, **the code itself is duplicating the event**. Choose a clear contract:

1. Service/repository preserve the exception type/cause and do not log just to rethrow.
2. Controllers do not catch solely to print a stack trace and rethrow.
3. The handler is responsible for mapping status/public response and logging **one** final failure event when needed.
4. Filters can log access events such as `request_completed`, duration, and status, without necessarily logging the Throwable again.
5. Check default framework/container error logging if you rethrow to the framework; do not log manually and also let the framework log it a second time.

For expected 4xx responses, a domain exception may only need INFO/WARN or metrics. You do not need to emit an ERROR with a stack trace for every validation failure or 404. An unexpected 500 may warrant an ERROR at the boundary, along with `requestId` and a safe code for support.

**Do not expose full exception stack traces in an HTTP response** under the rationale of “logging only once”: response viewers have different permissions than internal logs. Use a public-safe error code and correlation ID.

## 9. Exceptions in Future, CompletableFuture, and Workers

With `ExecutorService.submit(...)`, worker errors are captured inside the `Future`. The caller receives an `ExecutionException` when calling `Future.get()` and can inspect the root cause via `getCause()`. If the worker logs and rethrows, and the caller logs again in the `get()` catch block, one failure produces two stack traces.

~~~java
// Anti-pattern snippet: executor, LOG, and performWork() are already available.
Future<?> future = executor.submit(() -> {
    try {
        performWork();
    } catch (RuntimeException ex) {
        LOG.error("event=worker_failed", ex);
        throw ex;
    }
});

try {
    future.get();
} catch (ExecutionException ex) {
    LOG.error("event=job_failed", ex.getCause());
}
~~~

The better approach depends on **who owns the final outcome**:

- **Caller/job coordinator is the owner:** the worker only throws the exception; the caller decides whether to retry/fail and logs once.
- **Worker is an independent operation and finalizes itself:** the worker may log a final error, while the caller logs an aggregate status without reprinting the same stack trace.
- **Two semantically distinct events are needed:** `task_attempt_failed` and `job_failed_after_retries`; each event carries `attempt`/`outcome`, with the full stack trace only where it adds value.

With `CompletableFuture`, callbacks like `whenComplete`, `handle`, `exceptionally`, and a `join()` call can all observe the same failure; `join()` typically throws `CompletionException`. If every callback calls `LOG.error("failed", throwable)` and propagates, the error is logged once per callback. Choose a single boundary, and use the remaining callbacks for cleanup, mapping, or appropriate metrics.

**Do not treat `ExecutionException`/`CompletionException` as new business errors by default.** They are typically wrappers. Mappers should classify the cause according to the application's contract rather than logging the wrapper stack separately and then logging the root cause again just to see two `Caused by` chains.

When catching `InterruptedException` for cleanup, preserve interruption semantics and restore the interrupt flag properly if not rethrowing. Do not catch broad `Throwable` and continue running normally, especially for `Error`s like `OutOfMemoryError`.

### Context Across Thread Pools

MDC is typically thread-bound; when both worker and caller log, context must be propagated/captured at the boundary. If a worker reuses a thread that still holds a `requestId` from a previous request, having two “similar” logs becomes even harder to investigate. Clear MDC in `finally`, use propagation supported by your logging/tracing framework, and never attach sensitive data to global static state.

## 10. Retries and Message Redelivery: Distinct Valid Logs

Example with the same `messageId`:

~~~text
event=attempt_failed messageId=msg-1001 attempt=1 errorCode=PAY-TIMEOUT
event=retry_scheduled messageId=msg-1001 attempt=1 delayMs=500
event=attempt_failed messageId=msg-1001 attempt=2 errorCode=PAY-TIMEOUT
event=message_dead_lettered messageId=msg-1001 attempts=2 outcome=failure
~~~

These four lines describe **four operational milestones**, not four duplicates of the same LogEvent. Still, if every milestone prints the same full stack trace, cost and noise remain high. A sound policy might log attempt failures at WARN with `errorCode`/retry metadata, and one terminal failure at ERROR with the Throwable after exhausting the retry budget.

Do not suppress attempt events just because they share the same `errorCode`. With at-least-once message delivery, a broker may redeliver after a side effect was committed but before ACK; logs must distinguish **messageId**, **delivery/attempt**, and **processing outcome**. If a business side effect must not repeat, **idempotency** is needed independently of log reduction.

### In a Distributed Trace

Service B may log `event=payment_service_failed` because B's own work genuinely failed, while Service A logs `event=checkout_failed` because depending on B caused A's request to fail. Those can be **two different operation outcomes in two services**; do not automatically suppress one just because they share a `traceId`. When calculating SLOs, define clear measurement boundaries and services rather than summing every ERROR in a trace as failed end-user requests.

## 11. Distinguishing Code Anti-Patterns from Backend Event Duplication

Do not modify catch/rethrow code if the real issue is in logging configuration:

~~~text
Java logger calls -> LogEvent
                       |
                       +--> logger/appender hierarchy
                       |
                       +--> stdout + file sinks
                                   |
                                   v
                             shipper/collector
                                   |
                                   v
                              backend/index
~~~

**Logback additivity:** when a child logger has an appender and the same appender is also attached to root, by default an event can reach the sink twice due to additivity. Example configuration **snippet** (requires `CONSOLE` to be defined):

~~~xml
<logger name="com.example.orders" level="DEBUG">
    <appender-ref ref="CONSOLE"/>
</logger>
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

If using a shared console appender, attach it only at root and use child loggers to adjust levels. Do not set `additivity="false"` indiscriminately on all loggers; if a logger has no appender of its own, logs can disappear.

**JUL parent handlers:** `java.util.logging.Logger` can forward a `LogRecord` to both the current logger's handlers and its parent's handlers if `useParentHandlers=true`. Inspect `getHandlers()` and check for duplicate handler registration rather than looking only at the message text.

**Collector:** a single source event may be ingested from both console and file; batch retries on uncertain ACKs can also create duplicates. If the process's raw log has only one line while the index shows two, check the shipper/collector and query first. Do not deduplicate by `requestId` or `exceptionType`, since a single request legitimately produces multiple events.

**Cause chains:** `Caused by` and `Suppressed` are parts of a single stack trace, not evidence that the logger was called multiple times. Counting records at the sink is what distinguishes them.

## 12. What Should a Final Failure Event Contain?

**Illustrative** structured log example, not automatically the default output of JUL/SLF4J:

~~~json
{
  "timestamp": "2026-11-10T03:00:00Z",
  "level": "ERROR",
  "service": "checkout",
  "event": "checkout_failed",
  "errorCode": "ORDER_STORAGE_UNAVAILABLE",
  "requestId": "req-101",
  "traceId": "4f0e2c13b69a497389d74e71a52b4e62",
  "operation": "place_order",
  "attempt": 3,
  "outcome": "failed",
  "durationMs": 2450,
  "exceptionType": "OrderStorageException"
}
~~~

Beyond these fields, the backend can store the throwable/stack trace in a restricted internal sink. Distinguish:

- `errorCode` = error category from a finite catalog.
- `requestId`/`traceId` = correlation across multiple events; not a unique log ID.
- `attempt` = attempt number, not embedded in the `errorCode` name.
- `outcome` = final result or interim milestone; not inferred from log level.
- `messageId`/`jobId` = async unit that may have multiple attempts.
- `eventId` = per-log-event ID if transport deduplication is needed, distinct from `requestId`.
- `exceptionType` is useful for debugging but can change during refactoring; it does not replace a domain error code.

With SLF4J 2.x, use `addKeyValue` and `setCause` to build structured events; configure the encoder properly so fields are actually emitted. Do not abuse MDC to store `errorCode` for an entire request if an error was handled and subsequent success logs would inherit the stale code.

## 13. Security: Repeated Logging Exposes Data More Times

An exception does not contain only class names and stack frames; `getMessage()`, causes, suppressed exceptions, or dependency metadata may include hostnames, database names, SQL literals, URL queries, access tokens, or PII.

Key requirements:

1. Never log passwords, tokens, cookies, private keys, OTPs, or sensitive data outside policy.
2. Log finite event names and `errorCode`s; do not concatenate raw `ex.getMessage()` into public errors or dynamic fields.
3. Pass the Throwable once to a protected internal sink with appropriate redaction and access controls.
4. Guard against log injection from newlines/control characters in input; parameterized logging **does not automatically guarantee** sanitized data.
5. Keep `requestId`, `traceId`, and business identifiers low-sensitivity where possible; do not use email/phone as default correlation keys.
6. Retain mandatory audit/security events even when they coincide with an error incident: they have separate purposes, schemas, and retention rules.

Removing redundant stack traces **does not replace** RBAC, encryption, retention policies, and incident response procedures. Conversely, never use “log once” as an excuse to disable audit logging or hide anomalous access behavior.

## 14. Testing by LogRecord Count, Not Just Mocking the Logger

### Unit Tests

Use a capturing handler/appender from the actual logging backend:

- One request throwing an exception from repository through service to boundary → **exactly one final failure record** in the chosen sink if that is the policy.
- Cause chain preserved: `getThrown().getCause()` still holds the original information.
- Two requests with similar failures → two separate occurrences, not mistakenly deduplicated due to sharing an `errorCode`.
- One retry followed by success → attempt/fallback events still appear per policy, with no false terminal failure.
- Retries exhausting the budget → exactly one terminal failure for the final operation plus the required attempt events.
- Worker and caller both observing an exception → they do not both log full stack traces when only the caller is the owner.
- `CompletableFuture` callback propagation → does not duplicate the same event across multiple callbacks.
- Expected 4xx validation → appropriate log level, not an ERROR stack trace by default.

### Integration Tests

- **Spring/web framework:** verify whether controller, filter, advice, and error resolver all log the same exception.
- **Logback/JUL:** a single logger call reaches the right sink once; test additivity/parent handlers and appender registration.
- **Collector:** check whether one source event is ingested twice from stdout/file or queue retries.
- **Thread pool:** MDC/`requestId` from task A does not leak into task B.
- **Message consumer:** crashing before ACK and redelivery do not cause duplicate side effects; logs distinguish attempts.
- **Privacy:** synthetic sensitive data markers do not appear in unauthorized sinks, including stack traces.
- **Performance:** measure event counts, ingest bytes, and overhead under high exception rates without stressing production disks.

A test that only mocks `LOG.error(...)` in a controller **does not prove the backend writes only one record**, because Logback/JUL/collector configuration can still duplicate it. Test against **actual events received at the sink** or inspect stdout/ingest in an integration environment.

## 15. Runbook When Production Shows Multiple Identical Stack Traces

1. Collect a sample group of suspected duplicate logs with exact timestamps, `logger`, `requestId`, `traceId`, `errorCode`, `attempt`, and `service.instance`.
2. Inspect the **raw log of a single process**: if multiple records already exist there, trace the logger calls and appenders. If there is only one locally but multiple in the backend, inspect the collector/index.
3. Identify where the exception is created, which layers catch/rethrow/wrap it, who handles it, and who decides the final outcome.
4. Check controllers, global handlers, interceptors, `Future`/callbacks, message retries, and framework error loggers.
5. Designate one owner for the terminal failure; other layers only log **semantically distinct events** or rethrow while preserving `cause`.
6. Ensure required security/audit events are not removed and debugging stack traces are not lost.
7. Test `LogRecord` counts, retry/fallback conditions, and structured fields before deploying.
8. Verify appender routing, stdout/file outputs, and collectors to catch concurrent duplicate sources.
9. Compare before/after metrics: actual failed operations, ERROR record count, ingest bytes, alert noise, and queue drops.
10. Update code review guidelines and runbooks so the anti-pattern does not return.

Do not run a backend job that “deletes identical lines” as a first resort. It does not reduce source formatting/I/O and can mistakenly delete two valid requests with identical messages. Only deduplicate transport records if there is an `eventId`/provenance and a clear contract.

## 16. Common Wrong Fixes

| Quick Fix | Consequence | Right Approach |
| --- | --- | --- |
| Remove all `LOG.error` calls in all services | Loses real fallback/recovery events | Keep meaningful events, remove redundant log-and-rethrow |
| Raise the log level to reduce lines | Two ERRORs can still repeat; loses useful INFO | Pick a log owner and fix routing |
| Set `additivity=false` on every logger | Loggers without their own appender can lose logs | Fix only after identifying hierarchy issues |
| Strip Throwables from all logs | Loses root cause during investigation | Keep one Throwable in an appropriate internal sink |
| `printStackTrace()` followed by `LOG.error(...)` | Two outputs written to stderr/backend | Use the logging API once |
| Wrap exceptions without preserving `cause` | Cannot trace back to the original error | Use a constructor that accepts `cause` |
| Catch `Throwable` and continue running | Can swallow fatal Errors/interrupts | Respect lifecycle and exception types |
| Both worker and caller log | One async failure becomes two stack traces | Assign clear ownership |
| Count ERROR logs as failed requests | Wrong during retries or multi-sink setups | Count terminal outcomes or actual HTTP statuses |
| Use `requestId` as the log event ID | One request has multiple valid events | Give each event its own ID if ingest dedup is needed |
| Disable audit logs to “reduce duplicates” | Loses evidence and may violate retention | Keep audit and diagnostic logs separate by purpose |
| Log `ex.getMessage()` in public responses | Leaks system internals and sensitive data | Return public-safe code/message + correlation ID |
| Only unit-test with a mocked logger | Misses appender/collector duplication | Count actual `LogRecord`s / appender output |
| Deduplicate by raw message text | Merges two independent requests | Compare context, attempts, and `eventId`/provenance |

## 17. Code Review Checklist

- [ ] Is there any `catch` block that only logs and then calls `throw ex`/`throw new Exception(..., ex)`?
- [ ] Who is responsible for logging the **terminal failure** at the HTTP, message, or job boundary?
- [ ] Is `cause` preserved without logging the same stack trace at every layer?
- [ ] Are genuine intermediate events (`retry_scheduled`, `fallback_used`, `audit_decision`) preserved?
- [ ] Are `ERROR`/`WARN` chosen based on impact and final outcome, not merely HTTP status?
- [ ] Do `errorCode`, `requestId`, `traceId`, `messageId`, and `attempt` carry the right semantics?
- [ ] Do workers, `Future.get`, and `CompletableFuture` callbacks log the same failure repeatedly?
- [ ] Do the controller, filter, global handler, and framework all log the same exception?
- [ ] Could appender additivity, JUL parent handlers, or collectors duplicate a single event?
- [ ] Are tests counting events at the sink, rather than only mocking the logging API?
- [ ] Do metrics/SLOs count final outcomes rather than ERROR line counts?
- [ ] Do stack traces and exception messages avoid leaking secrets, and are audit events preserved?

**Takeaway:** An exception passing through multiple catch blocks is not automatically multiple errors. **Do not log at every layer and rethrow.** Preserve `cause`, classify `errorCode`, log genuinely new decisions made at each layer, and let the responsible boundary emit **one useful log for the final outcome**. At the same time, distinguish duplicate logs caused by **appenders/collectors** from **valid retry/audit events** so you do not treat the symptom by losing critical logs.

### Official References

- Java SE 17 — [`java.util.logging.Logger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html), [`LogRecord`](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html), [`Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html).
- Java SE 17 — [`ExecutionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html), [`CompletionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html).
- SLF4J — [Manual: parameterized logging and Fluent API](https://www.slf4j.org/manual.html).
- Logback — [Architecture: Logger/Appender/additivity](https://logback.qos.ch/manual/architecture.html), [Configuration](https://logback.qos.ch/manual/configuration.html).
- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html).
