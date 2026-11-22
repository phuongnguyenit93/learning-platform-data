# Choosing Where to Log Errors in Java Core Logging

## 1. "Where to Log Errors" Has Two Meanings

When an exception occurs in a Java application, the question is not only **whether to call a logger**, but also:

1. **Which layer or component is responsible for recording the error?** For example, a repository, service, HTTP exception handler, message consumer, or job runner.
2. **Which destination is the error event emitted to?** For example, console, file, centralized log collector, alerting channel, or a dedicated audit trail.

These two decisions are related but not identical. A single `Logger` at an API boundary can emit **one error event**, while the logging backend distributes that event to multiple handlers/appenders. Conversely, three Java layers all calling `logger.error` for the same exception does not mean the system is more reliable: it may simply produce three duplicate lines, increasing cost and adding noise to investigations.

**Practical rule:** prefer logging errors at the **boundary where the component actually knows the final outcome and has enough context to decide how to handle it**. At lower layers, if an error cannot be handled, propagate the exception upward while preserving the original `cause`. Do not apply a "log once" rule mechanically: different events, different boundaries, or a retry attempt with its own distinct outcome can still warrant a log entry, provided each log carries new information and a clear purpose.

### Example of a Multi-Layer Request

~~~text
HTTP request
   |
   v
Controller / REST boundary    <-- converts exception into HTTP response,
   |                               knows requestId, error code, and outcome
   v
OrderService                 <-- business logic / retry decision
   |
   v
OrderRepository              <-- encounters SQLException / broken DB connection
   |
   +-- wrap exception, preserve cause, DO NOT log if only rethrowing
   |
   v
OrderService                 <-- propagate; may enrich context
   |
   v
HTTP boundary                <-- log terminal failure ONCE
   |
   +--> Logging backend ------> console / file / collector per policy
   |
   +--> Return safe response to client
~~~

The diagram above is **one common way to structure logging**, not a requirement that every application place logs in the controller. For background applications, the boundary may be a worker, scheduler, consumer, CLI, or job coordinator.

## 2. Why Is Logging in Every `catch` Usually a Design Flaw?

A typical anti-pattern:

~~~java
// Illustrates a mistake, not a standalone program.
try {
    repository.save(order);
} catch (SQLException ex) {
    logger.log(Level.SEVERE, "Repository failed", ex);
    throw new StorageFailure("SAVE_FAILED", ex);
}

// In service:
try {
    saveOrder();
} catch (StorageFailure ex) {
    logger.log(Level.SEVERE, "Service failed", ex);
    throw ex;
}

// In API:
try {
    createOrder();
} catch (StorageFailure ex) {
    logger.log(Level.SEVERE, "HTTP request failed", ex);
    return serverErrorResponse();
}
~~~

These three snippets are **illustrative integration code** that depend on existing variables, classes, and methods and do not compile standalone. The same infrastructure incident can generate three nearly identical stack traces.

Consequences include:

- Log volume, ingestion cost, and storage cost grow with call stack depth.
- A single real error may be counted as multiple incidents, triggering false alerts.
- Context is fragmented; the repository log line does not know whether the final outcome is a successful retry, a fallback, or an HTTP 503.
- Logging an exception too early can expose raw SQL, file paths, personal data, or credentials.
- `ERROR`/`SEVERE` levels may be overused even when the error is handled or has a recovery path.

A better approach when the repository **cannot handle the error**:

~~~java
// Illustrative snippet: StorageFailure is an application-defined exception.
try {
    repository.save(order);
} catch (SQLException cause) {
    throw new StorageFailure("SAVE_FAILED", cause);
}
~~~

Here, the `StorageFailure` constructor must accept and retain `cause` without swallowing the root cause. Upper layers can then decide whether to retry or report a terminal failure. If the service actually **succeeds with a fallback**, it should usually not report "request failed" at a severe error level, and should instead log an appropriate fallback/degradation event.

**Distinction principle:** *Catching an exception* is a control-flow action; *logging* is an operational observability decision. Not every `catch` needs to log.

## 3. Determining Where to Log Based on Outcome Ownership

To choose the responsible layer, ask these questions in order:

1. **Has this layer finished handling the error?** If there is a final outcome or a real fallback, logging the outcome here makes sense.
2. **Does this layer have sufficient context?** Request ID, operation, standardized error code, retry count, resource category, and response target are usually only clear at the boundary.
3. **Will the error still be thrown upward?** If you are only adding context and rethrowing, avoid logging the same exception at every layer.
4. **Who will act on the log?** Does on-call, the security team, a developer, or operations need to receive information at that point?
5. **Does another layer automatically log this error?** Web frameworks, servlet containers, messaging frameworks, and global exception handlers may already record it.

| Scenario | Where to Typically Log | Reason |
| --- | --- | --- |
| HTTP request fails after final handling | Global exception handler / request boundary | Knows method, route pattern, request ID, status, and error code |
| Repository encounters an error and only wraps/rethrows | Usually **do not** log in the repository | Does not yet know whether the error will be retried, fallen back, or handled above |
| Service attempts a fallback and genuinely succeeds | In the service performing the fallback, if operationally valuable | Records **degradation/fallback**, without declaring the whole request failed |
| Scheduled job ends in failure | Job runner / scheduler boundary | Knows job ID, attempt count, and final outcome |
| Message consumer transient failure | Retry coordinator / consumer policy | Knows whether it is retried, backed off, or sent to DLQ |
| Uncaught error in a thread | Uncaught exception boundary as a last line of defense | Can capture unhandled errors; does not replace job/worker monitoring |
| Security action requiring audit | Dedicated audit channel with policy-defined schema | Verification purpose differs from diagnostic logging |
| A component detects local data corruption | The component owning the data, while also notifying upstream | May need an independent event because this is not merely the same exception being rethrown |

**The place with sufficient context is usually better than the place where the exception is created.** Even so, if a layer owns a recovery mechanism, circuit breaker, or data integrity check, it may need to log a separate event—such as `fallback_activated` or `cache_entry_evicted`. In that case, describe **the action taken**, rather than repeating the entire stack trace.

## 4. Standalone Java 17 Example: One Exception, One Boundary Log

This example uses `java.util.logging` (JUL), built into JDK 17. The repository simulates a low-level failure and **wraps it with a cause**; the service simply forwards it; the HTTP boundary simulates the final decision to return `503` and logs **one** error event.

To keep the output verifiable, the formatter in this example prints only the message and **exception type**, intentionally omitting the stack trace. The `LogRecord` still holds the passed `Throwable`; in a production application, a formatter/backend on a restricted-access channel can record stack traces that have been reviewed for sensitive data.

Create the file `ErrorLoggingBoundaryDemo.java`:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ErrorLoggingBoundaryDemo {
    private static final Logger LOGGER =
            Logger.getLogger("demo.error.boundary");

    private static final class StorageUnavailableException
            extends RuntimeException {
        StorageUnavailableException(Throwable cause) {
            super("STORAGE_UNAVAILABLE", cause);
        }
    }

    private static final class OrderRepository {
        void load(String orderId) {
            try {
                // Simulate an infrastructure failure, not a real DB.
                throw new IllegalStateException("simulated storage outage");
            } catch (IllegalStateException cause) {
                // Preserve the cause; do NOT log and then rethrow.
                throw new StorageUnavailableException(cause);
            }
        }
    }

    private static final class OrderService {
        private final OrderRepository repository = new OrderRepository();

        void load(String orderId) {
            repository.load(orderId);
        }
    }

    private static void handleRequest(String requestId) {
        OrderService service = new OrderService();
        try {
            service.load("order-demo-42");
            System.out.println("response=200 requestId=" + requestId);
        } catch (StorageUnavailableException failure) {
            // The boundary knows the final outcome is 503.
            LOGGER.log(Level.SEVERE,
                    "event=order_load_failed requestId=" + requestId
                    + " errorCode=STORAGE_UNAVAILABLE",
                    failure);
            System.out.println("response=503 requestId=" + requestId);
        }
    }

    public static void main(String[] args) {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.ALL);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String exceptionType = record.getThrown() == null
                        ? ""
                        : " exceptionType="
                          + record.getThrown().getClass().getSimpleName();
                return record.getLevel().getName() + ": "
                        + formatMessage(record)
                        + exceptionType
                        + System.lineSeparator();
            }
        });
        LOGGER.addHandler(handler);

        try {
            handleRequest("req-101");
        } finally {
            LOGGER.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
~~~

Compile and run:

~~~bash
javac ErrorLoggingBoundaryDemo.java
java ErrorLoggingBoundaryDemo
~~~

**Exact stdout:**

~~~text
response=503 requestId=req-101
~~~

**Exact stderr:**

~~~text
SEVERE: event=order_load_failed requestId=req-101 errorCode=STORAGE_UNAVAILABLE exceptionType=StorageUnavailableException
~~~

JUL's `ConsoleHandler` writes to **stderr**, while the example uses `System.out.println` to simulate the response. When a terminal merges stdout and stderr, the display order between the two streams is not guaranteed; therefore, the outputs are shown separately.

### Key Takeaways from the Example

1. **Repository:** translates the infrastructure error into `StorageUnavailableException` with a cause, without logging an extra `SEVERE` entry itself.
2. **Service:** propagates the exception, since the service has no retry/fallback policy in this demo.
3. **Boundary:** knows the final result is `503`, so it emits the `order_load_failed` event along with the request ID and error code.
4. **Attached Throwable:** the `LOGGER.log(Level.SEVERE, message, failure)` overload attaches the exception to the `LogRecord`; the demo formatter prints the exception type rather than the stack trace. A real backend can choose a different policy.
5. **No internal error leakage to the client:** the demo response contains only the status and request ID, without sending infrastructure details or exception messages.
6. **Do not log raw business data:** the IDs in the example are stable dummy values; in real systems, request IDs and resource IDs still need to be classified according to privacy policies.
7. **`setUseParentHandlers(false)`:** isolates the demo logger from parent logger handlers, preventing duplicate output. In real applications, understand the logger hierarchy configuration before disabling inheritance.

**Limitation:** this program does not open an HTTP socket, call a database, or demonstrate how Spring/Jakarta automatically translates exceptions. It is a standalone JDK example simulating a boundary to focus on **where to log errors** and **preserving the cause**.

## 5. `log and rethrow` or `propagate with cause`?

### When Should You Not `log and rethrow`?

If a lower layer takes no additional action and does not own the final outcome, the following pattern easily creates duplicate logs:

~~~java
// Integration snippet, not standalone runnable.
catch (SQLException ex) {
    logger.log(Level.SEVERE, "Database query failed", ex);
    throw new StorageFailure("STORAGE_UNAVAILABLE", ex);
}
~~~

Upper layers will see `StorageFailure` and may log the exception and its stack trace again.

Usually, you should do this instead:

~~~java
// Integration snippet; StorageFailure is custom-defined
// and its constructor must store the cause.
catch (SQLException ex) {
    throw new StorageFailure("STORAGE_UNAVAILABLE", ex);
}
~~~

When you need to add context, use an operation code and `cause`; avoid concatenating raw SQL, tokens, or payloads into the exception message. If a lower layer **has handled the error** (for example, invalidating a corrupted cache record or switching to a read replica), it can log an independently meaningful event such as `cache_entry_discarded` or `read_replica_fallback`.

### Do Not Swallow Exceptions

~~~java
// Wrong if the error is not actually handled.
try {
    performCriticalOperation();
} catch (Exception ignored) {
    // Do nothing: the caller may assume processing succeeded.
}
~~~

Neither handling nor propagating an error leaves upper layers **with no information to record the true outcome**. Truly acceptable "best effort" cases should be documented and usually accompanied by an appropriate metric or event log.

### Do Not Broadly Catch `Throwable`

`Throwable` includes `Error` (such as severe resource/runtime errors), not just `Exception`. An HTTP boundary or worker should normally not catch `Throwable` and continue as if nothing happened. Only perform actions consistent with the framework contract and shutdown procedure. For `InterruptedException`, if you catch it without rethrowing, you typically need to restore the interrupt status via `Thread.currentThread().interrupt()` so task cancellation is not broken.

## 6. Choose Log Levels by Outcome, Not Just Exception Type

Severity does not mean "if there is an exception, it must be ERROR". The appropriate level depends on recoverability, impact, frequency, and whether the system requires intervention.

| Scenario | Level Usually Considered | Why |
| --- | --- | --- |
| User submits invalid input, returning expected 400 | `DEBUG`/`FINE` or `INFO`; sometimes not logged per request | This can be a normal validation flow |
| Access denied by authorization, returning 403 | Per security/audit policy; operational log need not be `ERROR` | Need to distinguish expected denials from attack indicators |
| Resource does not exist, normal 404 | `DEBUG`/`INFO` or access log | Should not trigger on-call alerts for every 404 |
| Timeout retried and succeeds | `DEBUG`/`FINE` or `WARNING` for retry event if useful | Final request succeeded; retry metrics aid observability |
| Fallback succeeds but with degraded quality | `WARNING` is usually appropriate | Degraded service needs monitoring, not a total failure |
| Dependency fails and final request returns 503 | `SEVERE` in JUL, `ERROR` in SLF4J when policy matches | Error impacts outcome and requires investigation |
| Message processing exhausts retries, sent to DLQ | Log terminal outcome per policy | Do not spam an `ERROR` stack trace on every attempt |
| Unable to write a mandatory audit event | Dedicated high-priority alert/incident, potentially fail closed | Simply logging `WARN` cannot be treated as guaranteed auditing |

**JUL does not have an `ERROR` enum:** the level typically used for severe errors is `Level.SEVERE`; warnings use `Level.WARNING`. Libraries like SLF4J/Logback/Log4j 2 typically have `ERROR` and `WARN`. Do not mix level names when writing example code.

Exception count is not the same as failed request count: a single request may undergo multiple retries and ultimately succeed. Metrics such as `http_requests_total{outcome=...}`, `dependency_retries_total`, and `job_failures_total` measure impact better than raw counts of `ERROR` log lines.

## 7. Choosing Boundaries by Application Type

### 7.1. Web API / REST

In an HTTP application, a **global exception handler** or centralized middleware/filter typically has the status, route pattern, request ID, and error code needed to log a terminal failure once. Example flow:

~~~text
OrderRepository throws StorageFailure (cause preserved)
     |
OrderService propagates or handles/retries
     |
Global HTTP exception handler:
  - maps expected errors to 4xx, unexpected ones to 5xx
  - logs a structured event at appropriate level
  - returns sanitized response containing requestId/errorCode
~~~

Controller/framework code must follow the specific lifecycle of Spring MVC, Jakarta Servlet, Quarkus, Micronaut, or whichever framework is in use. An exception already logged by a handler might be logged again by the container if rethrown after writing a response, so a single owner for the final log must be established.

**Do not log raw request URLs or bodies**: query strings, headers, and exception messages can contain PII, tokens, or customer data. Prefer `routePattern`, request ID, status, duration, and error code.

### 7.2. Message Consumers and Background Workers

A message consumer can **nack/requeue**, retry with backoff, route a message to a dead-letter queue/topic, or succeed via fallback. Therefore, the place to log a terminal failure is usually the **consumer error handler/retry coordinator**, which knows whether the message was actually acked or sent to a DLQ.

A `message_process_attempt_failed` event can be at `DEBUG`/`INFO` to observe attempts; after retries are exhausted, a `message_dead_lettered` event can have a higher severity. **"Intending to send to DLQ" does not mean the broker confirmed DLQ storage.** If publishing to the DLQ fails, distinguish the outcome and avoid acking the original message prematurely per policy.

With Kafka, committing offsets has different semantics from individual acks in some queue brokers; do not copy a single logging/ack pattern blindly across all products. Use standardized message IDs/correlation IDs and reason codes, without dumping sensitive payloads.

### 7.3. Scheduled Jobs / Batch

A job runner knows `jobId`, `runId`, attempt, succeeded item count, failed item count, and the final outcome. A single-record error can be logged as a separate processing event if there is a skip-and-summarize policy; an error that causes **the entire job to fail** should be logged at the final boundary.

If you log `ERROR` for every business-rejected record and then add a summary `ERROR`, dashboards may exaggerate incident counts. You can use a metric to count failed records and a single terminal failure log if the job aborts.

### 7.4. CLI, `main`, and Unsupervised Threads

In CLI applications, the final boundary is usually `main` or the command dispatcher: log a useful cause, return an appropriate exit code, and avoid exposing sensitive stack traces to end users. `Thread.UncaughtExceptionHandler` can serve as a **fallback mechanism** for uncaught errors, but should not be treated as the sole place to log errors.

In `ExecutorService`, exceptions from tasks submitted via `submit` may be held inside the `Future` and surface when `get()` is called, rather than reaching the uncaught handler. With `CompletableFuture`, observe exceptional completion or callbacks; with job frameworks, use the framework-provided error handler/lifecycle.

## 8. Logging Exceptions Correctly in JUL and SLF4J

### 8.1. Java Util Logging

To attach a `Throwable` (preserving cause/stack trace information for an appropriate formatter):

~~~java
// Integration snippet: LOGGER and failure are existing variables.
LOGGER.log(Level.SEVERE, "Order load failed", failure);
~~~

This is the `Logger.log(Level, String, Throwable)` overload. If you use the parameterized overload:

~~~java
LOGGER.log(Level.SEVERE,
        "Order load failed requestId={0}",
        new Object[] {requestId});
~~~

the arguments are used to format the message, but **`failure` is not automatically attached**. When you need both structured parameters and a throwable for a specific formatter, use an API/backend that supports separate fields, or design an appropriate event/`LogRecord`. Do not assume Java has a `log(Level, String, Object[], Throwable)` overload.

**Avoid this pattern:**

~~~java
LOGGER.severe("Order failed: " + failure.getMessage());
~~~

It can lose the stack trace/cause, print sensitive data from the message, and perform eager string concatenation. If you need a stable error code, use an explicitly mapped `errorCode` rather than defaulting to whatever `getMessage()` a lower-level library returns.

### 8.2. SLF4J (with a Backend Such as Logback or Log4j 2)

Integration code example:

~~~java
// Requires SLF4J API and backend. logger/requestId/failure already exist.
logger.error("Order load failed requestId={} errorCode={}",
        requestId, "STORAGE_UNAVAILABLE", failure);
~~~

In common SLF4J usage, a `Throwable` as the last argument is handled by the backend/API as the exception when the matching varargs overload is selected. Test on your actual version and provider to ensure the throwable is attached properly. For non-parameterized messages, the explicit pattern is `logger.error("Order load failed", failure)`.

**Do not equate "the formatter prints stack traces" with "the formatter definitely does not leak data".** Exceptions can carry file paths, raw SQL, user information, or input messages; check redaction policies and storage destinations before enabling detailed logs.

## 9. Choosing Where to *Emit* Logs: Handlers, Appenders, and Alerting Channels

Only after deciding **which component emits the log** does the logging backend decide **where to write it**.

~~~text
One terminal failure event
           |
           v
         Logger
           |
      Backend routing
       /       |       \
 Console     File     Central collector
 stdout/err  rotating   search/alert/retention
~~~

With JUL, you can attach `ConsoleHandler`, `FileHandler`, and custom handlers, each with its own level, filter, and formatter. With SLF4J, actual routing and writing are controlled by the backend (such as Logback or Log4j 2) via appenders.

| Destination | When Appropriate | Things to Watch Out For |
| --- | --- | --- |
| Console / stdout/stderr | Developers, CLIs, containers, and systems with log collectors | Who collects stdout/stderr, and are there duplicates across pipelines? |
| Local file / rotating file | Apps needing local storage in environments allowing file management | Disk space, rotation, retention, permissions, volume |
| Central log platform | Cross-service investigation, search, access-controlled alerting | Cost, PII, exporter latency/reliability |
| Security/audit store | Events governed by security or audit policies | Schema, integrity, access control, and separate acknowledgment |
| Metrics/traces | Measuring error rates, retries, latency, request paths | Does not replace detailed logs when context is needed |

**A single log event can be fanned out to multiple destinations** without calling the logger multiple times. Conversely, if an application already writes to stdout and a collector ships it to a central store, configuring an additional remote appender to send the same event to that store can create duplicate records.

The source logger's level can filter an event **before** any handler/appender sees it; filters at each destination only further filter the events that were already emitted. Audit trails with strict completeness/durability requirements should not rely solely on an `INFO` log line that might disappear when logging levels change.

## 10. Privacy, Security, and Error Logging

Exceptions are frequently **unintended data leak paths**. For example:

- `SQLException` or query logs can contain personal data parameters.
- HTTP client exceptions can include URLs with query tokens in their messages.
- Validation exceptions can contain raw bodies or user-entered fields.
- Stack traces can expose internal class/infrastructure names and file paths.
- `MDC` can accidentally carry an email, session ID, or data from a previous request if not cleared.

**Prefer logging allowlisted fields:** `requestId`, operation code, route pattern, status, error code, exception type when appropriate, duration, and retry count. `requestId` and correlation IDs can still be linked to an individual, so they also require retention policies and access control.

Do not log passwords, tokens, cookies, entire DTOs, authorization headers, or raw user input just to "have enough info for debugging". **Do not hash an email or IP and assume it is anonymous.** If storing sensitive data is mandatory, use an approved channel, tested masking/redaction, access locks, and separate retention.

A logger should not leak the raw cause into an HTTP response or user-facing error message. The boundary can return a stable `errorCode` and correlation ID; internal details belong only in appropriately access-controlled logs.

## 11. Special Cases to Consider

### When a Fallback Succeeds

Suppose the cache fails, so the service bypasses the cache and reads from the database successfully. A reasonable log might be:

~~~text
event=cache_fallback_activated operation=load_order
outcome=RECOVERED requestId=req-101
~~~

If the repository logs `SEVERE` and the final boundary returns HTTP 200, alerting systems may mistake it for a major incident. It is better for the component performing the fallback to log **one degraded/recovered event** along with monitoring metrics.

### When Multiple Layers Have Independent Observability Value

A system may need to log at both the gateway and a service if the two logs describe **two distinct events**: the gateway terminating with HTTP 502 and the service encountering a timeout when calling a dependency. Include `traceId`/`requestId` fields to correlate them and avoid making them look like two unrelated incidents. This is not a reason for every method in the same service to log the same stack trace.

### When Errors Have Security Implications

A denied login attempt may require an audit event even when HTTP status 401 is expected. Audit and diagnostic logs should be separated in purpose, schema, durability, and access control. **Do not escalate every 401/403 to `SEVERE`**; use appropriate security monitoring policies or rate-based alerts.

### When Retries Occur

If a dependency times out on attempt 1 and succeeds on attempt 2, logging `ERROR` at a low layer for attempt 1 can misreport the request outcome. The retry coordinator should emit metrics and retry events; only log a terminal failure at ERROR level if recovery ultimately fails. For retries with side effects, idempotency and transaction rules are still required; logging alone does not solve duplicate business operations.

## 12. Testing to Ensure the Right Error Logging Location

Do not merely assert generically that "an ERROR log exists". Verify **event count, emitting layer, severity, context, and final state**.

| Test Scenario | Expected Behavior |
| --- | --- |
| Repository throws exception, HTTP returns 503 | One terminal error event at the boundary; cause preserved |
| Repository fails once, retry succeeds | No false terminal failure; retry metric/event if policy requires |
| Expected validation error, returns 400 | No unnecessary `SEVERE`; response includes error code |
| Service fallback succeeds | `RECOVERED`/`DEGRADED` event matching the outcome |
| Message fails multiple attempts then goes to DLQ | Distinguishes attempt failure from DLQ confirmed; no unbounded stack trace multiplication |
| Logger has handlers attached on both child and root | Detects duplicates caused by additivity/parent handlers |
| Exception contains a fake secret | Secret is not emitted to any tested destinations |
| Logging backend unavailable | Application handles per policy, does not treat `logger.info()` as durable acknowledgment |
| Client receives 500 | Contains no raw stack trace, SQL, or tokens |
| Async task fails | Error handler/future observes outcome; does not rely solely on uncaught handler |

### Assertions on Collected Logs

In unit/integration tests, use a test appender/handler to capture events and assert:

- Exactly **one** `order_load_failed` event for a failed request under this policy.
- Presence of `requestId`, stable error code, and exception type.
- Absence of passwords, tokens, raw request bodies, or disallowed stack traces.
- The repository layer does not log `SEVERE` and rethrow.
- Status/exception/outcome match business logic.
- If logs go to multiple sinks, verify how each sink receives the event; do not confuse fan-out with multiple logger calls.

With SLF4J/Logback or Log4j 2, how you attach a test appender depends on the backend and version; with JUL, you can use a custom `Handler` to collect `LogRecord`s. **Do not modify the global root logger in a test and let that configuration leak into other tests**; create a dedicated logger and clean up handlers/lifecycle after the test.

## 13. Common Mistakes and How to Fix Them

| Mistake | Problem | Better Practice |
| --- | --- | --- |
| Calling `ERROR` in every `catch` and rethrowing | Same exception produces multiple duplicate lines | Log at the boundary that decides the outcome, preserve cause when propagating |
| Logging only `ex.getMessage()` | Loses stack trace; message may contain PII | Attach `Throwable` via proper API; log stable error code and control sinks |
| Logging in repository and again in gateway | Unclear where the terminal failure is | Divide log ownership by layer |
| Swallowing exceptions without logging/propagating | Upper layers assume success | Truly handle it, or propagate/fail with an appropriate code |
| Logging all 4xx as `SEVERE` | Alert noise | Choose severity by impact; use separate audit/security policies |
| Logging full stack traces on every retry attempt | Log storm and miscounted errors | Metrics/structured attempt events; clear terminal failure |
| Logging before database transaction commit | May log "success" despite rollback | Log at the right time/outcome or use event-guarantee mechanisms |
| Using `System.out.println(ex)` in web apps | Lacks context, schema, route, and control | Use a logger at the boundary with a configured backend |
| Enabling DEBUG and logging raw payloads | PII/credential leaks | Schema allowlist, redaction, appropriate retention |
| Relying solely on `UncaughtExceptionHandler` | Futures/async tasks may hold exceptions internally | Observe failures at executor/job boundaries |
| Logging once and assuming durable storage | Async queues, files, or networks can fail | Monitor delivery/flush/retention according to requirements |
| Calling logger multiple times because there are multiple appenders | Creates unnecessary records | One event, backend fans out via filters |

## 14. Quick Checklist for Java Projects

- [ ] Identify the layer that owns the **final outcome** of a request/job/message.
- [ ] Place terminal error logs at the boundary or error handler with full context.
- [ ] When wrapping exceptions, preserve `cause`; avoid `log and rethrow` if there is no independent event.
- [ ] Distinguish expected business errors, transient failures, fallbacks, retries, and terminal failures.
- [ ] Define JUL/SLF4J levels by impact, not merely by the `Exception` class name.
- [ ] Attach request ID, operation, error code, and retry count when needed; do not dump payloads.
- [ ] Attach the `Throwable` using the proper API when stack traces are needed; control PII risk and storage destinations.
- [ ] Check logger hierarchy, handlers/appenders, additivity, and pipeline duplication.
- [ ] Separate diagnostic logs from audit events that have distinct requirements.
- [ ] Observe async tasks/futures/message handlers so failures are not missed.
- [ ] Test terminal failure, fallback success, retry success, sensitive data handling, and log duplication.
- [ ] Measure effectiveness with metrics/traces alongside logs, avoiding turning every error line into an incident.

### Knowledge Check

**Q1.** The repository logs `SEVERE` and throws an exception; the controller also logs `SEVERE`. Is that definitely better?  
**A:** No. If it is the same failure left unhandled in the repository, that is usually duplicate logging. Preserve the cause and log at the boundary that knows the outcome.

**Q2.** Retry attempt 1 times out, and attempt 2 succeeds. Should you log "request failed" on the first attempt?  
**A:** No. You can log a retry event or record a metric; the terminal outcome is still success.

**Q3.** Does an exception always require logging `ERROR` or `SEVERE`?  
**A:** No. A 400 validation error, a 403 denial, a successful fallback, and a real infrastructure failure have different purposes and severities.

**Q4.** If an event is written to both the console and a file, must the application call the logger twice?  
**A:** No. Handlers/appenders can fan out a single event to multiple destinations.

**Q5.** Does `LOGGER.severe(ex.getMessage())` guarantee stack trace preservation and security?  
**A:** No. It only logs the message string and can expose sensitive data; consider attaching the `Throwable` with an appropriate schema and sink.

**Q6.** A thread task fails without an uncaught log appearing—does that mean there was no error?  
**A:** No. Tasks in a `Future` or `CompletableFuture` can hold the error for the caller/handler to observe.

**Remember:** "Choosing where to log errors" is first and foremost about choosing **where the outcome is owned and sufficient context is available**, not finding the first `catch` block. Layers that cannot handle an error should propagate the exception with its cause; the final boundary logs a classified error event without multiplying stack traces at every layer. From there, the logging backend routes the event to console, file, or collector with appropriate level, privacy, and reliability policies.