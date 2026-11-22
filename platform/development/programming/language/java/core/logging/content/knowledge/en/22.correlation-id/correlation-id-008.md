# Correlation ID and Retry in Java Logging

## 1. The problem: one operation, multiple attempts

A **Correlation ID** is an identifier used to link log events that belong to the same processing flow or logical operation. **Retry** is the act of repeating an operation after a failure or a transient unsuccessful signal.

These two mechanisms often appear together in Java services calling HTTP APIs, databases, message brokers, or other services:

~~~text
A payment request: correlation_id = corr-42
      |
      +-- Attempt 1: timeout
      |
      +-- Wait according to retry policy
      |
      +-- Attempt 2: success
      |
      +-- Final logical outcome: success
~~~

If the code generates a **new correlation_id on every retry**, the logs will look like multiple independent requests, making it hard for operators to recognize that attempt 1 and attempt 2 belong to the same work. Conversely, if the logs only have a correlation ID **without an attempt number**, events can easily be mistaken for duplicates, or readers cannot tell which errors recovered.

**Core rule:** For the **same logical operation**, typically keep the **correlation ID stable across retries**, while attaching a **different attempt number/attempt ID to each attempt**. After all attempts, record the **final outcome** of the operation.

Example of good logs:

~~~text
INFO  cid=corr-42 attempt=1 event=ATTEMPT_STARTED outcome=in_progress
WARN  cid=corr-42 attempt=1 event=ATTEMPT_FAILED reason=TIMEOUT outcome=retrying
INFO  cid=corr-42 attempt=2 event=ATTEMPT_STARTED outcome=in_progress
INFO  cid=corr-42 attempt=2 event=OPERATION_SUCCEEDED outcome=success
~~~

**A failed attempt is not necessarily a failed operation.** If attempt 2 succeeds, the final result is success, not error. When retries are exhausted or a non-retryable error occurs, distinguish it clearly with a final event such as OPERATION_FAILED.

## 2. What questions does a Correlation ID answer?

A Correlation ID helps connect related events:

- Which API calls belong to the same order creation command?
- Which logs belong to the same message/job being reprocessed?
- Did this timeout error lead to a successful retry?
- On which attempt did the system complete?
- Are the Controller, Service, Client, and background worker layers talking about the same activity?
- Was an operation executed multiple times due to retry or message redelivery?

A record with sufficient context might include:

~~~json
{
  "timestamp": "2026-11-09T12:34:56.789Z",
  "level": "WARN",
  "service": "checkout",
  "logger_name": "com.example.payment.PaymentClient",
  "correlation_id": "corr-42",
  "attempt_id": "corr-42-a1",
  "retry_attempt": 1,
  "max_attempts": 3,
  "event_code": "PAYMENT_ATTEMPT_TIMEOUT",
  "reason_code": "PROVIDER_TIMEOUT",
  "outcome": "retrying",
  "message": "Payment attempt timed out; another attempt is planned"
}
~~~

Clearly named fields make it easy to query, group by correlation_id, and distinguish an **attempt failure** from a **terminal failure** without having to parse the message text.

**A Correlation ID is not security data for authenticating users.** Do not use it as a credential or proof that a caller has permission to perform an operation. Values sent by clients must be validated and handled according to trust boundaries.

## 3. Distinguishing common IDs

Do not use all ID types interchangeably just because they are all strings:

| ID | Common scope | Behavior on retry |
| --- | --- | --- |
| **correlation_id** | A business flow/logical request per contract | Kept stable if it is still the same work |
| **request_id** | An HTTP request or a system-defined request | May be kept or changed depending on the contract: a physical HTTP call may have its own request ID |
| **operation_id** | A business operation | Usually kept across attempts of that operation |
| **attempt_id** | A physical attempt | Must distinguish each individual attempt |
| **retry_attempt** | Attempt sequence number, e.g., 1, 2, 3 | Increments with each attempt |
| **trace_id** | A distributed trace | Can be kept across retries belonging to the same trace |
| **span_id** | A specific span within a trace | The span for each attempt usually has its own ID |
| **idempotency_key** | Key for the handler to recognize repeated requests of the same intent, if the API supports it | Kept stable for the same operation requiring idempotent retry |
| **message_id** | A message in a queue system | May be kept across redeliveries of the same message; depends on the broker |
| **delivery_count** | Delivery count observed by the broker/consumer | Changes across redeliveries |

**Correlation ID and idempotency key are not the same.** A Correlation ID helps **observe and link logs**; an idempotency key helps a properly designed system **recognize multiple submissions of the same command** to prevent duplicate side effects.

**A Correlation ID does not prevent duplicates on its own.** Two POST requests carrying the same correlation ID can still create two transactions if the server lacks an idempotency mechanism or other guarantees.

**A Trace ID is not always equal to a correlation ID either.** Distributed tracing standards such as W3C Trace Context define specific formats and propagation rules for trace IDs. If OpenTelemetry is already in place, retrieve the trace/span ID from the valid context; do not assign an arbitrary string to the trace_id field and treat it as a real trace.

## 4. One logical operation, multiple attempts

Recommended model:

~~~text
logical_operation: createPayment
correlation_id: corr-42
operation_id: payment-op-42
idempotency_key: fixed value for the same intent (not necessarily logged in raw form)
    |
    +-- attempt=1 / attempt_id=a-1
    |      -> timeout
    |
    +-- attempt=2 / attempt_id=a-2
    |      -> HTTP 503
    |
    +-- attempt=3 / attempt_id=a-3
           -> success

Final outcome: OPERATION_SUCCEEDED / outcome=success
~~~

**Keep stable:** correlation_id, operation_id, and idempotency key if the attempts genuinely represent the same intent.  
**Change per attempt:** retry_attempt, attempt_id, start time, wait time, duration, HTTP status, or failure reason.

If the application has **a new user action creating a new intent** (for example, the user actively creates another independent order), do not inadvertently reuse the idempotency key or correlation scope of the old operation.

### When should a correlation ID be created?

Ideally **at the entry boundary of the logical operation**, such as an HTTP filter, message consumer, or job scheduler. Then propagate it down through the layers and across retries.

Wrong:

~~~java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    String correlationId = java.util.UUID.randomUUID().toString();
    callRemoteService(correlationId);
}
~~~

This snippet illustrates a method with **maxAttempts** and **callRemoteService**. It creates a new ID on every attempt, making it hard to link the attempts into a single operation.

Better:

~~~java
String correlationId = java.util.UUID.randomUUID().toString();

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    callRemoteService(correlationId, attempt);
}
~~~

This is also an illustrative snippet, not a standalone Java program. In systems where a correlation ID is already provided by the caller/middleware, **it is not necessarily required to generate a new UUID**; follow the propagation and validation contract.

## 5. Attempt counts: clear conventions to avoid confusion

It is good practice to explicitly record **retry_attempt** or **attempt_number** starting at **1** for the first call, if that is the system's convention.

Example:

| Field | Meaning |
| --- | --- |
| **retry_attempt=1** | First physical call |
| **retry_attempt=2** | Second physical call |
| **max_attempts=3** | Maximum total number of attempts allowed, including the first call |
| **retry_count=1** | Number of *retries performed* after the first call (when using this convention) |
| **attempt_id** | Unique ID within the scope needed to track each call |
| **retry_delay_ms** | Planned wait time before the next attempt, if any |
| **duration_ms** | Actual elapsed time of the corresponding attempt/operation |

**max_attempts is different from max_retries.** A **max_retries=3** configuration usually means one initial call plus up to three retries, i.e., **four attempts**; however, libraries may have different names and semantics. Read the contract carefully and use unambiguous field names.

Logs should record:
- **attempt=1/3**, or retry_attempt=1 and max_attempts=3.
- Outcome as **retrying**, **success**, **failed**, **cancelled**, or **degraded** as appropriate.
- **reason_code** separated from the message.
- If there is a timeout or retry delay, include explicit units such as **timeout_ms**, **retry_delay_ms**.

Avoid logging **retry=1** without clarifying whether it means the first attempt, the first retry, or the total number of retries that have occurred.

## 6. Which events should be logged?

You do not need to log every step at INFO; choose events with investigative value and appropriate levels.

| Event | Situation | Reference level |
| --- | --- | --- |
| **ATTEMPT_STARTED** | Starting an attempt | DEBUG or INFO when detailed demo/monitoring is needed |
| **ATTEMPT_FAILED** | An attempt encountered a *potentially* retryable error | DEBUG/WARN depending on severity and frequency |
| **RETRY_SCHEDULED** | Decided to retry after a delay | DEBUG/INFO or WARN if causing degradation |
| **OPERATION_SUCCEEDED** | Logical operation completed | INFO if useful |
| **OPERATION_RECOVERED** | Succeeded after retry/fallback | INFO/WARN depending on the signal to observe |
| **OPERATION_FAILED** | Retries exhausted or non-retryable error encountered | ERROR/SEVERE |
| **RETRY_ABORTED** | Cancelled or exceeded deadline/retry budget | Depends on outcome and impact |

Example after a timeout when another retry will be attempted:

~~~json
{
  "correlation_id": "corr-42",
  "retry_attempt": 1,
  "max_attempts": 3,
  "event_code": "ATTEMPT_FAILED",
  "outcome": "retrying",
  "reason_code": "TIMEOUT"
}
~~~

When attempt 2 succeeds:

~~~json
{
  "correlation_id": "corr-42",
  "retry_attempt": 2,
  "max_attempts": 3,
  "event_code": "OPERATION_SUCCEEDED",
  "outcome": "success"
}
~~~

**Do not log OPERATION_FAILED after attempt 1 if the code is still retrying the same operation.** Doing so causes dashboards or alerts to count a single request as both failed and succeeded.

Some systems still log every ATTEMPT_FAILED at ERROR level for audit purposes; in that case, clearly distinguish event_code/outcome and avoid using raw ERROR counts as the final failure rate.

## 7. Retry policy must align with business semantics

Correlation ID solves observability; the **retry policy** decides whether to retry. Do not retry an unsafe operation just to get cleaner logs.

Questions to answer:

1. **Is the error transient?** Timeouts, connection resets, and some 429/5xx responses may be retryable, depending on the API and actual state.
2. **Is the operation idempotent?** GET is usually easier to retry than a POST that creates side effects; you must still adhere to the endpoint's contract.
3. **Does the server have an idempotency mechanism?** If a request times out after the server already processed it, blindly resending it can cause duplicate side effects.
4. **How much total deadline remains?** Do not retry indefinitely when the user's wait time has already expired.
5. **What is the backoff strategy?** Exponential backoff + jitter, or following Retry-After when valid.
6. **How is the retry budget bounded?** Avoid amplifying load on a dependency that is already experiencing an outage.
7. **How are cancellation/interruption handled?** Do not keep retrying when the operation has been cancelled.
8. **Who owns the retry?** Client, SDK, gateway, queue consumer, or an orchestration layer?

### Not every error should be retried

Some examples:
- Clear validation errors: usually require fixing the input, not retrying as a transient error.
- HTTP 401/403: usually authentication/authorization issues; only retryable if there is a token refresh mechanism or a specifically defined policy.
- HTTP 429: usually requires respecting rate limits, Retry-After if present, and retry budgets.
- HTTP 502/503/504: may be transient, but idempotency, deadline, and dependency state must be considered.
- Read timeout: **does not prove the server has not executed the request**.
- Logic errors or invalid data: retrying usually just repeats the failure.

**Do not use the status code alone as an absolute retry decision.** The API contract and the potential for side effects matter more.

## 8. A timeout does not mean the server did not process the request

This is especially important when Correlation ID is paired with retry.

~~~text
Client (cid=corr-42)              Server
       |                            |
       |------ POST payment ------->|
       |                            |  Executed and committed successfully
       |          response lost     |
       |<---- client timeout -------|
       |                            |
       |------ POST retry --------->|
       |                            |  Without deduplication:
       |                            |  may create a second payment
~~~

In this situation, the client knows it **did not receive a response in time**, not whether the server actually executed the transaction.

**Correlation ID only helps show that both calls belong to the same operation. It does not guarantee that the second call will be processed safely.**

### Idempotency key vs. correlation ID

An **idempotency key** is sent per a contract with the server so the server can recognize multiple submissions of the same command. When the server properly supports it:
- The same key and the same intent can return the result of the previous execution.
- Side-effecting operations avoid duplicate execution within the documented guarantee scope.
- The server needs to store/check results, validate payload consistency, handle concurrent contention, and manage TTL according to the contract.

**Do not assume setting an Idempotency-Key header is enough.** If the server does not understand the header or lacks deduplication guarantees, sending the key does not make a POST automatically idempotent.

### Should the idempotency key be logged?

Usually **do not log the raw key if it is security-sensitive, predictable, contains PII, or acts like a bearer token**. You can log an **idempotency_ref** or a safe correlation reference according to application policy. Correlation IDs should also be controlled for length and sensitivity.

### The same correlation ID can contain multiple operations

An HTTP request might create an order and then initiate a payment. Those operations may share the same request-level correlation ID, but **the idempotency keys for order creation and payment should be distinct** per the contract. Do not use one global key for all side effects just because they share a correlation ID.

## 9. Exponential backoff, jitter, and Retry-After

Retrying immediately in a tight loop can make it even harder for an overloaded dependency to recover.

A common approach:
- Exponentially increasing delay: **baseDelay × 2^(attempt-1)**.
- A cap at **maxDelay**.
- Adding **jitter** so multiple clients do not retry at the exact same time.
- Respecting **Retry-After** or valid server rate-limit signals when required by policy.
- Not exceeding the **total deadline** and **retry budget**.

Illustrative example, not a rigid formula for every service:

~~~text
attempt 1 failed -> random delay in range 0..200 ms
attempt 2 failed -> random delay in range 0..400 ms
attempt 3 failed -> all 3 attempts exhausted -> terminal failure
~~~

When logging a retry decision, useful fields include:
- retry_attempt, max_attempts
- retry_delay_ms
- next_attempt_at if needed, with explicit timezone
- deadline_remaining_ms
- reason_code
- rate_limit_status if applicable

**Backoff alone does not guarantee business safety.** For non-idempotent commands, deduplication and transaction state must be addressed first.

Do not put a random delay into the expected stdout of a demo unless the seed and execution conditions are fixed; the Java 17 example below **simulates retries without sleeping** so the output is deterministic.

## 10. Standalone Java 17 example: preserving Correlation ID across retries

This example demonstrates:
- The same **correlation_id** for all attempts belonging to one logical operation.
- Changing **attempt_id** and attempt number.
- A safe **idempotency_ref** for observability; it is **not** a server-side deduplication mechanism.
- Attempt 1 timing out and attempt 2 succeeding in the first scenario.
- The second scenario timing out all three times and logging **OPERATION_FAILED** once.
- Built-in JDK 17 JUL logger, requiring no external dependencies.
- A custom Handler printing concise output without dynamic timestamps.
- Attaching the Throwable to LogRecord on errors.
- Avoiding ThreadLocal to prevent context confusion in the demo.

Create **CorrelationRetryDemo.java**:

~~~java
import java.util.concurrent.TimeoutException;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class CorrelationRetryDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.checkout.PaymentClient");

    private record RetryContext(
            String correlationId,
            String idempotencyRef,
            int attempt,
            int maxAttempts) {

        String attemptId() {
            return correlationId + "-a" + attempt;
        }
    }

    private static final class CompactHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }

            Object[] parameters = record.getParameters();
            RetryContext ctx = (RetryContext) parameters[0];
            String outcome = (String) parameters[1];

            StringBuilder line = new StringBuilder()
                    .append(record.getLevel().getName())
                    .append(" | cid=").append(ctx.correlationId())
                    .append(" | attempt=")
                    .append(ctx.attempt()).append("/")
                    .append(ctx.maxAttempts())
                    .append(" | attempt_id=").append(ctx.attemptId())
                    .append(" | idem_ref=").append(ctx.idempotencyRef())
                    .append(" | event=").append(record.getMessage())
                    .append(" | outcome=").append(outcome);

            if (record.getThrown() != null) {
                line.append(" | error=")
                    .append(record.getThrown()
                            .getClass()
                            .getSimpleName());
            }

            System.out.println(line);
        }

        @Override
        public void flush() {
            System.out.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }

    private static void event(
            RetryContext context,
            Level level,
            String eventCode,
            String outcome,
            Throwable cause) {

        LogRecord record = new LogRecord(level, eventCode);
        record.setLoggerName(LOG.getName());
        record.setParameters(new Object[] {context, outcome});

        if (cause != null) {
            record.setThrown(cause);
        }

        LOG.log(record);
    }

    private static void simulateGateway(
            int attempt,
            int successOnAttempt) throws TimeoutException {

        if (attempt != successOnAttempt) {
            throw new TimeoutException("simulated timeout");
        }
    }

    private static void runScenario(
            String correlationId,
            String idempotencyRef,
            int successOnAttempt,
            int maxAttempts) {

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            RetryContext context = new RetryContext(
                    correlationId,
                    idempotencyRef,
                    attempt,
                    maxAttempts);

            event(context, Level.INFO, "ATTEMPT_STARTED",
                    "in_progress", null);

            try {
                simulateGateway(attempt, successOnAttempt);
                event(context, Level.INFO, "OPERATION_SUCCEEDED",
                        "success", null);
                return;

            } catch (TimeoutException error) {
                if (attempt == maxAttempts) {
                    event(context, Level.SEVERE, "OPERATION_FAILED",
                            "failed", error);
                    return;
                }

                event(context, Level.WARNING, "ATTEMPT_FAILED",
                        "retrying", error);
            }
        }
    }

    public static void main(String[] args) {
        Handler output = new CompactHandler();

        output.setLevel(Level.ALL);
        LOG.setLevel(Level.ALL);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(output);

        try {
            // Attempt 1 timeout, attempt 2 success.
            runScenario("corr-42", "safe-ref-42", 2, 3);

            // All attempts timeout.
            runScenario("corr-99", "safe-ref-99", -1, 3);
        } finally {
            LOG.removeHandler(output);
            output.close();
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 CorrelationRetryDemo.java
java CorrelationRetryDemo
~~~

**Exact program stdout:**

~~~text
INFO | cid=corr-42 | attempt=1/3 | attempt_id=corr-42-a1 | idem_ref=safe-ref-42 | event=ATTEMPT_STARTED | outcome=in_progress
WARNING | cid=corr-42 | attempt=1/3 | attempt_id=corr-42-a1 | idem_ref=safe-ref-42 | event=ATTEMPT_FAILED | outcome=retrying | error=TimeoutException
INFO | cid=corr-42 | attempt=2/3 | attempt_id=corr-42-a2 | idem_ref=safe-ref-42 | event=ATTEMPT_STARTED | outcome=in_progress
INFO | cid=corr-42 | attempt=2/3 | attempt_id=corr-42-a2 | idem_ref=safe-ref-42 | event=OPERATION_SUCCEEDED | outcome=success
INFO | cid=corr-99 | attempt=1/3 | attempt_id=corr-99-a1 | idem_ref=safe-ref-99 | event=ATTEMPT_STARTED | outcome=in_progress
WARNING | cid=corr-99 | attempt=1/3 | attempt_id=corr-99-a1 | idem_ref=safe-ref-99 | event=ATTEMPT_FAILED | outcome=retrying | error=TimeoutException
INFO | cid=corr-99 | attempt=2/3 | attempt_id=corr-99-a2 | idem_ref=safe-ref-99 | event=ATTEMPT_STARTED | outcome=in_progress
WARNING | cid=corr-99 | attempt=2/3 | attempt_id=corr-99-a2 | idem_ref=safe-ref-99 | event=ATTEMPT_FAILED | outcome=retrying | error=TimeoutException
INFO | cid=corr-99 | attempt=3/3 | attempt_id=corr-99-a3 | idem_ref=safe-ref-99 | event=ATTEMPT_STARTED | outcome=in_progress
SEVERE | cid=corr-99 | attempt=3/3 | attempt_id=corr-99-a3 | idem_ref=safe-ref-99 | event=OPERATION_FAILED | outcome=failed | error=TimeoutException
~~~

### How the program works

1. **runScenario** receives correlationId once, outside the for loop. Every attempt in the same scenario uses that value.
2. **RetryContext** is an immutable record holding the fields specific to a single attempt.
3. **attemptId()** builds a readable string from the correlation ID and attempt number. This is a **demo identifier**, not a globally unique ID generator safe for all concurrent threads.
4. **idempotencyRef** is a log-safe reference code. The example does not perform real requests and does not implement server idempotency; do not treat it as proof of deduplication.
5. **simulateGateway** throws TimeoutException if the attempt is not the configured successful attempt. It simulates failure without networking, real backoff, or side effects.
6. **LogRecord.setParameters** attaches context to the event using a **demo-specific** convention. JUL does not define a correlation_id schema on its own.
7. **record.setThrown(cause)** preserves the Throwable for error events. The Handler only prints the exception class name to keep stdout stable; a production Formatter can output the cause chain/stack trace.
8. **ATTEMPT_FAILED** has outcome=retrying so it is not misinterpreted as a final result.
9. When attempts are exhausted, **one** OPERATION_FAILED is logged at SEVERE level. For the successful scenario, OPERATION_SUCCEEDED appears exactly once.
10. **LOG.setUseParentHandlers(false)** prevents the JUL root Handler from producing extra lines, and the custom Handler prints to stdout rather than using the default ConsoleHandler which normally writes to stderr.

### Why is this not yet a production retry client?

To use with real HTTP, you also need:
- A policy classifying retryable vs. non-retryable errors.
- Deadlines, per-attempt timeouts, backoff, jitter, and retry budgets.
- Cancellation/InterruptedException handling.
- Idempotency keys per the server contract.
- Context propagation via HTTP headers and tracing frameworks.
- Metrics and security controls.
- Handling ambiguous status (timeout where the server may have already committed).

The example above intentionally separates **correlation logging mechanics** from network/distributed policies that depend on the application.

## 11. Correlation ID in SLF4J MDC

With SLF4J/Logback, **MDC (Mapped Diagnostic Context)** lets you add processing-scoped key–value pairs.

An illustrative code pattern, assuming a Logger **log**, variables **correlationId** and **maxAttempts**, and a method **sendPayment()**:

~~~java
import org.slf4j.MDC;

MDC.put("correlation_id", correlationId);
try {
    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        MDC.put("retry_attempt", Integer.toString(attempt));

        try {
            log.info("Starting payment attempt");
            sendPayment();
            log.info("Payment succeeded");
            break;
        } finally {
            MDC.remove("retry_attempt");
        }
    }
} finally {
    MDC.remove("correlation_id");
}
~~~

This is **not a standalone runnable Java class** and does not yet include retry decision logic on failure; it only illustrates the **MDC lifecycle**. When moving to production, handle errors according to policy and keep correlationId unchanged.

Advantages:
- correlation_id exists across the scope wrapping the entire retry loop.
- retry_attempt exists only for the duration of each specific attempt.
- finally ensures keys are removed when exiting the scope via normal Java control flow.
- Business code does not need to manually concatenate the correlation ID into every message.

**However, MDC.put alone does not guarantee the fields appear in the log file.** The backend and layout/encoder must be configured to output the keys. A Logback text pattern might look like:

~~~xml
<pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS,UTC} %-5level cid=%X{correlation_id} attempt=%X{retry_attempt} %logger - %msg%n</pattern>
~~~

This is **part** of a Logback configuration, not a complete configuration file. If using a JSON encoder, verify that correlation_id and retry_attempt are exported with the expected field names and types.

### Be careful with nested scopes

If an upper layer already set correlation_id and a lower layer calls:

~~~java
MDC.put("correlation_id", anotherId);
// ...
MDC.remove("correlation_id");
~~~

the original correlation ID will be lost, because **remove does not automatically restore the previous value**.

In scopes that might overwrite a key, save the previous value first:

~~~java
String previous = MDC.get("correlation_id");
MDC.put("correlation_id", currentId);
try {
    performOperation();
} finally {
    if (previous == null) {
        MDC.remove("correlation_id");
    } else {
        MDC.put("correlation_id", previous);
    }
}
~~~

This is an illustrative snippet requiring existing methods/variables. For multiple keys, you can snapshot **MDC.getCopyOfContextMap()** and restore **MDC.setContextMap(...)** according to ownership. Do not call **MDC.clear()** indiscriminately inside a helper, as it can wipe out trace_id, request_id, and other fields managed by the caller.

## 12. Key-value events with SLF4J 2.x

**SLF4J 2.x** provides a fluent API for attaching fields to a **single event**:

~~~java
log.atWarn()
        .addKeyValue("event_code", "ATTEMPT_FAILED")
        .addKeyValue("retry_attempt", attempt)
        .addKeyValue("max_attempts", maxAttempts)
        .addKeyValue("reason_code", "PROVIDER_TIMEOUT")
        .addKeyValue("outcome", "retrying")
        .setCause(exception)
        .log("Payment attempt timed out");
~~~

This is an illustrative snippet with an SLF4J 2.x Logger, and variables attempt, maxAttempts, and exception in scope. When MDC already holds correlation_id, the encoder can output both the correlation ID and the event-specific fields. **setCause(exception)** preserves the Throwable; do not only print exception.getMessage() if stack traces are needed.

**addKeyValue does not automatically convert all logs to JSON.** The provider/backend (Logback, Log4j 2 via the appropriate SLF4J provider, etc.) must have an encoder/layout configured to actually serialize the fields.

Use event-specific fields for:
- event_code
- retry_attempt
- max_attempts
- reason_code
- retry_delay_ms
- outcome
- error_type

Meanwhile, correlation_id, trace_id, and request_id can live in scoped context if their lifecycles match. Regardless of the design, **the created event** must capture the right values without depending on when an async appender writes to disk.

## 13. Propagating correlation with ExecutorService or CompletableFuture

Retries may execute on a **different worker thread** than the initial thread. In SLF4J with a thread-bound MDC backend, **do not assume MDC automatically propagates across ExecutorService**, thread pools, or CompletableFuture.

Capture → install → restore pattern (illustrative snippet):

~~~java
Map<String, String> captured = MDC.getCopyOfContextMap();

Future<?> future = executor.submit(() -> {
    Map<String, String> previous =
            MDC.getCopyOfContextMap();

    try {
        if (captured == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }

        executeRetryOperation();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
});
~~~

Requires importing **java.util.Map, java.util.concurrent.Future, org.slf4j.MDC**, with an executor variable and executeRetryOperation method. This snippet is not a standalone example.

Why this matters:
- Capture the context **before submitting**.
- Install the context in the worker running the retry.
- Clean up/restore the worker's previous context in finally.
- Avoid losing keys from prior work or leaking keys into subsequent work.

If the retry scope finishes on the source thread while a submitted task is still running, clearing MDC on the source thread does not cause the worker to lose its correlation. **Each task needs an appropriate context snapshot** and should not hold arbitrary shared mutable references.

In reactive frameworks or virtual-thread workflows, use the framework-supported propagation mechanism and test cancellation, thread hopping, and context restoration. Do not assume ThreadLocal always accurately represents the entire journey of a request.

## 14. Propagation across HTTP and microservices

Example of a request traversing multiple services:

~~~text
API Gateway
  | correlation_id=corr-42
  | trace_id=trace-X
  v
Order Service
  | attempt=1
  v
Payment Service --> TIMEOUT
  |
Order Service
  | attempt=2
  v
Payment Service --> SUCCESS
~~~

Here, the events can share **correlation_id=corr-42**. However, each HTTP attempt can also have its own **physical request ID** generated by the gateway or upstream.

### Designing the header contract

You can define an internal header such as:

~~~text
X-Correlation-ID: corr-42
~~~

This header name is an application convention, **not a mandatory Java standard**. When sending a retry:
- Keep the correlation ID stable if it is still the same logical operation.
- Generate a new attempt ID or pass the attempt number if the contract allows it.
- Propagate trace context according to the tracing tool in use.
- Do not reuse the span ID of an old attempt by default.
- Only propagate context across authorized trust boundaries.

**W3C Trace Context** uses headers like **traceparent** and **tracestate** for tracing. Do not replace these headers with an arbitrary correlation ID; they have their own format and semantics.

### Are client-supplied IDs trustworthy?

An external caller might attach a very long string, newline characters, sensitive data, or a spoofed ID. Before logging or forwarding:
- Validate length and character set.
- Have a mechanism to generate a safe ID when missing or invalid.
- Prevent log injection.
- Do not treat the ID as authorization information.
- Consider distinguishing external_correlation_id and internal_correlation_id.

**Do not propagate the entire MDC across service boundaries** if it contains tenant metadata, secrets, or internal context that must not leave the system.

## 15. Retries in message queues and job processing

Retries do not only happen in HTTP calls. A message queue can **redeliver** the same message after a consumer crash, timeout, or unacknowledged processing.

Example:

~~~text
Message M:
  message_id=msg-42
  correlation_id=corr-42
  operation_id=payment-op-42

Delivery 1 -> consumer timeout, not acked
Delivery 2 -> consumer reprocesses
Delivery 3 -> success, acked
~~~

The logging model should distinguish:
- **correlation_id:** links the entire business flow.
- **message_id:** identifies the message per the broker/application.
- **delivery_attempt** or **delivery_count:** the delivery number received by the consumer.
- **consumer_instance:** the processing instance if needed.
- **outcome:** retrying, processed, dead_lettered, or failed.
- **reason_code:** transient error / terminal error.
- **idempotency key/dedupe ID:** independent business mechanism to prevent duplicate side effects.

**Do not assume every broker's delivery count starts at one or is maintained the same way**. For example, some brokers do not provide a built-in delivery count; in that case, you may need a custom field in the payload/header or a redelivery policy.

### Dead-letter queue (DLQ)

After retries exceed the limit, a message may be moved to a DLQ. The final log might be:

~~~json
{
  "correlation_id": "corr-42",
  "message_id": "msg-42",
  "event_code": "MESSAGE_DEAD_LETTERED",
  "outcome": "dead_lettered",
  "reason_code": "RETRIES_EXHAUSTED"
}
~~~

Do not equate **message moved to DLQ** with **transaction completed**. Manual intervention, replay, auditing, or workflow compensation may still be required.

### Is a replay the same logical operation?

It depends on the contract. If replaying the same intent to complete the old request, the correlation ID/operation ID may need to be preserved. If an operator creates **a new operation** from old data, you can use a new correlation ID and record **original_correlation_id** to link the history. This rule must be documented, not applied mechanically.

## 16. Nested retries: avoiding call amplification

A gateway has retries, an HTTP client SDK also retries, and the service calling the SDK retries as well. The actual number of calls can be much larger than expected.

Example:
- The Service layer tries up to 3 times.
- Each Service attempt calls the SDK, and the SDK tries 3 times on its own.

When all layers exhaust their retries, this can generate up to **9 network calls** for a single upper-layer operation, if no other stopping condition exists.

~~~text
service attempt 1 -> sdk attempts 1,2,3
service attempt 2 -> sdk attempts 1,2,3
service attempt 3 -> sdk attempts 1,2,3
~~~

Logs need to know **which layer's attempt** it is:
- outer_attempt
- sdk_attempt
- total_attempt_count if accurately measured
- shared correlation_id
- span ID per layer/operation
- retry_policy or retry_layer if needed for investigation

**Do not reuse a single attempt=1 field across multiple retry layers** and infer the real call count from it.

Common design solutions include:
- Choosing one layer to be the primary retry owner.
- Disabling or capping retries at other layers if policy allows.
- Using cross-layer deadlines and retry budgets.
- Monitoring retry rates, dependency load, and error rates.
- Only retrying operations that are safe per the contract.

## 17. Log levels and counting errors: attempt vs. operation

A common mistake is logging every attempt timeout as ERROR, and then logging INFO when the operation succeeds. Dashboards counting ERROR will think the request failed even though it recovered.

Distinguish **two types of metrics**:

**Attempt failure rate:** failed attempts / total attempts.  
**Operation failure rate:** logical operations that ultimately failed / total logical operations.

For example, out of 100 operations, 15 needed retries, and in the end 98 succeeded and 2 failed:
- The operation failure rate is **2/100 = 2%**.
- The attempt failure count may be higher than 2, and the total attempts denominator must be used to calculate the corresponding rate.

Do not use count(log level=ERROR) as the denominator or numerator of operation failure if the logging policy logs errors at multiple layers or samples/drops logs.

### Metrics to measure separately

Useful metrics include:
- retry_attempts_total by low-cardinality service/dependency/reason_code.
- logical_operations_total by outcome.
- retry_exhausted_total.
- retry_delay_seconds or attempt duration.
- dependency latency/error rate.
- circuit breaker status per dependency.

Do not put **correlation_id** or **attempt_id** into metric labels arbitrarily: every request can generate a new value, causing massive time-series cardinality growth.

Correlation IDs belong in logs/tracing, while metrics usually use labels with controlled value domains.

## 18. Structured logging schema for retries

A sufficient schema might include:

| Field | Example | Type | Notes |
| --- | --- | --- | --- |
| timestamp | 2026-11-09T12:34:56.789Z | String time | Explicit UTC/offset |
| level | WARN | String/enum | Per backend mapping |
| service | checkout | String | Resource |
| correlation_id | corr-42 | String | Stable across the same logical operation |
| operation | authorizePayment | String | Operation name |
| attempt_id | corr-42-a1 | String | Specific to the attempt |
| retry_attempt | 1 | Number | First attempt, starting from 1 |
| max_attempts | 3 | Number | Including the first attempt |
| event_code | ATTEMPT_FAILED | String/enum | Stable event code |
| outcome | retrying | String/enum | Not yet terminal |
| reason_code | PROVIDER_TIMEOUT | String/enum | Error classification |
| retry_delay_ms | 200 | Number | If there is a delay |
| duration_ms | 130 | Number | Actual measured duration |
| error_type | TimeoutException | String | Exception type |
| trace_id | Trace ID | String | From tracing context |
| span_id | Current span ID | String | May change per attempt |
| idempotency_ref | safe-ref-42 | String | Only if safe for logging |

Do not log every field in every event. **ATTEMPT_STARTED** may not have error_type; **OPERATION_FAILED** needs outcome=failed and reason_code; **OPERATION_SUCCEEDED** does not need a cause just to fill columns.

Measurements need clear units. The retry_delay_ms field should be a Number, not a string like "200ms", if you want numeric filtering.

### Example of two events belonging to one correlation

~~~json
{"correlation_id":"corr-42","retry_attempt":1,"max_attempts":3,"event_code":"ATTEMPT_FAILED","reason_code":"PROVIDER_TIMEOUT","outcome":"retrying"}
{"correlation_id":"corr-42","retry_attempt":2,"max_attempts":3,"event_code":"OPERATION_SUCCEEDED","outcome":"success"}
~~~

From these two records, we know an operation was retried and eventually succeeded. They cannot be mistaken for two independent payments if the schema is used properly.

## 19. Managing Correlation ID in the Java lifecycle

Places that can own the correlation ID:
- HTTP filter / interceptor at the request boundary.
- Message consumer receiving metadata from the broker.
- Job scheduler or batch processor.
- Workflow orchestrator.
- Tracing middleware.

Avoid:
- Generating a new UUID inside each retry.
- Putting the correlation ID into a dynamic **Logger name** for every request.
- Using a global mutable static variable to hold currentCorrelationId.
- Setting MDC and forgetting to clear/remove it when the thread is reused.
- Wiping out the caller's trace ID with MDC.clear() inside a small method.

### Scopes with existing values

Suppose the caller already set correlation_id. Another helper resets the same key and only calls **MDC.remove("correlation_id")** in finally, which loses the caller's ID.

Per-key save/restore pattern:

~~~java
String old = MDC.get("correlation_id");
MDC.put("correlation_id", newCorrelationId);

try {
    performOperation();
} finally {
    if (old == null) {
        MDC.remove("correlation_id");
    } else {
        MDC.put("correlation_id", old);
    }
}
~~~

This is an illustrative snippet, not standalone Java. For scopes with multiple keys, you can snapshot **MDC.getCopyOfContextMap()** and restore **MDC.setContextMap(...)** according to ownership rules.

**MDC.putCloseable** automatically removes the key on close, but it does not automatically restore an overwritten previous value. If nested operations can overwrite correlation_id, you must use explicit restoration or a tested scope abstraction.

## 20. Security, reliability, and cardinality

Correlation ID and retry context should be treated as queryable operational data.

### Common risks

- Clients sending correlation headers containing newlines, long text, sensitive data, or spoofed values.
- IDs containing user emails, phone numbers, or tokens.
- Logging raw **idempotency_key** potentially exposing a code the server considers sensitive.
- Copying the entire HTTP request/response into exception logs, leaking the Authorization header.
- A multitenant system logging the wrong tenant_id due to an MDC leak.
- Indexing all random IDs causing high costs.
- Logging too many retries causing storage issues or slowing down processing.

### Mitigations

- Validate externally supplied IDs, limiting length and character set.
- Generate a new internal ID when needed and log its relationship with the external ID per contract.
- Do not use correlation ID for authorization decisions.
- Log only necessary fields; redact secrets.
- Use a standard JSON encoder/serializer and escape control characters.
- Clean up MDC at the request/task boundary, even when exceptions occur.
- Consider sampling detailed events while keeping required terminal outcomes per observability/audit policy.
- Set appropriate retention and access permissions.
- Do not treat text logs as guaranteed durable audit storage.

### Should Correlation IDs be globally unique?

To avoid collisions when joining logs, it is usually good to generate IDs with sufficient entropy within the system's scope, such as UUID v4 or ID mechanisms managed by tracing/request middleware. However, **there is no single mandatory format for all correlation IDs**. A system may receive IDs from partners per a contract. Length, format, uniqueness scope, and trust boundaries must be agreed upon.

## 21. Testing what matters

A test suite should verify both retry correctness and observability:

| Scenario | What to verify |
| --- | --- |
| Success on attempt 1 | One correlation ID, attempt=1, OPERATION_SUCCEEDED |
| Timeout then success | Same correlation ID, attempt increments, final outcome success |
| Retries exhausted | One final OPERATION_FAILED event; no false success |
| Non-retryable error | No further attempts run, outcome clearly failed |
| Timeout after server commit | Idempotency/status lookup prevents duplicate side effects per contract |
| HTTP 429 with Retry-After | Delay/budget follows policy |
| Cancellation/deadline | Does not continue retrying after conditions expire |
| Concurrent requests | Two requests with different correlation IDs do not interfere in MDC |
| Thread pool reuse | Request B does not inherit A's correlation ID |
| CompletableFuture/executor | Correlation is propagated and restored properly |
| Nested retry in SDK | Outer and inner attempts are distinguished, real network calls measured |
| Broker redelivery | Correlation kept per logical job, delivery attempts distinguished |
| JSON collector | Attempt field is a Number and correlation_id is not dropped |
| Malicious client ID | Validation and log escaping work; no secret leaks |
| Exception chain | Throwable is preserved and logged at an appropriate boundary |

### Verifying logs with queries

Some sample queries:
- Show **all events for correlation_id=corr-42**, sorted by event time and attempt.
- Count **OPERATION_FAILED** by reason_code, not just ATTEMPT_FAILED.
- Find operations with multiple attempts whose final outcome is success.
- Find a correlation ID with **conflicting terminal outcomes** (e.g., both success and failed), indicating a bug/race to investigate.
- Find retries that stretched close to the deadline.
- Detect requests missing a correlation ID or attempts whose retry_attempt does not increment properly.

When logs span multiple hosts, clock skew can prevent timestamps from reflecting absolute causal order. Combine attempt number, span relationships, and event codes; do not sort solely by timestamp strings.

## 22. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Generating correlation ID inside retry loop | Every attempt looks like a different request | Create/receive ID once at logical operation |
| Using one attempt_id for all attempts | Cannot distinguish attempts | Separate ID/number for each attempt |
| Using correlation ID for deduplication | Server can still commit multiple times | Idempotency contract and real deduplication |
| Generating new idempotency key on each retry | Server does not recognize the same intent | Keep key per logical operation |
| Reusing idempotency key for independent operations | May return wrong result/dedupe erroneously | Distinguish each business intent |
| Logging every ATTEMPT_FAILED as OPERATION_FAILED | Dashboards/alerts inflate error rates | Separate event codes and outcomes |
| Logging only attempt errors, no terminal outcome | Hard to tell if request ultimately succeeded | Explicit OPERATION_SUCCEEDED/FAILED |
| Inconsistent max_attempts and max_retries | Off-by-one attempt counts | Define 1-based convention |
| Using MDC without cleanup | Context leaks in thread pools | try/finally and restore |
| Not propagating context across async boundaries | Worker logs missing IDs | Capture/install/restore |
| Using homemade trace_id as a standard trace | Tracing does not link up | Retrieve ID from tracing context |
| Copying entire MDC across trust boundaries | Internal data leaks | Allowlist and propagation policy |
| Not handling ambiguous timeouts | Duplicate side effects | Idempotency and status lookup |
| Retrying immediately in a tight loop | Increases load when dependency fails | Backoff, jitter, budget, deadline |
| Retrying simultaneously at multiple layers | Amplifies network calls | Assign retry owner and budget |
| Using request_id as a metric label | High cardinality | Keep IDs in logs/tracing |
| Counting log lines as request count | Inaccurate with sampling/drops/duplicate logs | Use metrics and outcomes |
| Checking only stdout, not the collector | Fields may be lost or change type | Integration test the pipeline |

## 23. Production checklist

1. **Identify the logical operation:** Which exact intent is the retry serving?
2. **Correlation ID:** Generate/receive at the boundary, keep stable across attempts of the same operation.
3. **Attempt:** Have a distinct attempt number/ID and a clear max_attempts convention.
4. **Idempotency:** If there are side effects, ensure the backend supports deduplication per contract.
5. **Outcome:** Distinguish attempt failure, retrying, recovered, success, and terminal failed.
6. **Retry policy:** Error classification, deadline, timeout, budget, backoff, jitter, Retry-After.
7. **Layering:** Avoid uncontrolled overlapping retry layers.
8. **Logging:** Stable event_code and reason_code, numeric fields with units.
9. **Throwable:** Preserve exception/cause; do not log duplicate stack traces across multiple layers.
10. **MDC:** Properly scoped context, cleaned up/restored in finally.
11. **Async:** Propagate context across executors, queues, and callbacks.
12. **Tracing:** Standard trace_id/span_id, and do not use them in place of idempotency keys.
13. **HTTP/MQ:** Propagate metadata per contract and validate trust boundaries.
14. **Privacy:** Do not log secrets, tokens, or sensitive keys.
15. **Collector:** Parse JSON with the right field names/types and timestamps.
16. **Metrics:** Separate retry attempt metrics from operation outcome metrics.
17. **QA:** Test timeout after commit, concurrent requests, thread reuse, exhaustion, and cancellation.

## 24. Self-check questions

**1. Should the Correlation ID change on every retry?**  
Normally no, if the retries belong to the same logical operation. Keep the correlation ID; change the attempt number/ID.

**2. How do Attempt ID and correlation ID differ?**  
Correlation ID links the entire body of work; attempt ID identifies a single distinct try within it.

**3. Does a Correlation ID prevent the server from creating two payments on timeout?**  
No. You need idempotency or a server-side deduplication mechanism per the contract.

**4. Why does a timeout not prove the operation failed on the server?**  
The server may have committed while the response was lost or delayed, so the client only knows it did not receive a response.

**5. When attempt 1 fails but attempt 2 succeeds, what is the final result?**  
OPERATION_SUCCEEDED/outcome=success; attempt 1 can have an ATTEMPT_FAILED/outcome=retrying event.

**6. Does max_attempts=3 mean three retries after the first call?**  
No. By the convention in this article, it means three attempts **in total**, including the initial call.

**7. Does MDC automatically propagate across ExecutorService?**  
Do not assume so. You must capture/install/restore context in the worker or use a tested propagation mechanism.

**8. Should correlation_id be put into a metric label?**  
Normally no, because cardinality is very high. Use IDs in logs/tracing, and use metrics with low-cardinality labels.

**9. Why must the idempotency key be kept across retries of the same intent?**  
So a backend that supports idempotency recognizes them as the same operation and handles deduplication per the contract.

**10. Can the same correlation ID be used across broker redeliveries?**  
Yes, if the redelivery belongs to the same logical job; add delivery attempt/message ID to distinguish each delivery.

**11. Is logging WARNING for every attempt failure mandatory?**  
No. It depends on logging policy and traffic volume; event_code, reason_code, and outcome are the foundation for accurate interpretation.

**12. Is a correlation ID alone enough to analyze retries?**  
Not enough. You should also have attempt number/ID, event_code, outcome, reason_code, and terminal result to distinguish each attempt.

## 25. Key takeaways

**Correlation ID lets you see multiple retries as one piece of work; attempt ID shows each try as a separate event; idempotency protects side effects if the system actually supports it; outcome tells you the final result.**

In Java applications, create or accept the correlation ID at the logical operation boundary, keep it stable across the same retry workflow, increment the attempt number consistently, log ATTEMPT_FAILED differently from OPERATION_FAILED, propagate context properly across HTTP/queues/async boundaries, and clean up MDC after the scope. Retry only when the business contract, deadline, retry budget, and idempotency allow it; **good logging cannot fix an unsafe retry policy**, but it helps detect and explain those bugs much faster.
