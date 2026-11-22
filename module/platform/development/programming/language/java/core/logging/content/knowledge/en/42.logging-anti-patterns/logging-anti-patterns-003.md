# Context-Free Log Messages: A Logging Anti-Pattern in Java Applications

## 1. What Is a Context-Free Log Message?

A **context-free log message** (context-free or context-poor logging) is an anti-pattern where a log record contains only generic remarks such as `Done`, `Failed`, `Updated`, `Something went wrong`, or an isolated value without **enough information to identify the operation, target object, outcome, and related execution chain**.

Example:

```text
INFO Done
INFO Updated
ERROR Failed
```

In a Java application with hundreds of concurrent requests, multiple instances, or multiple message consumers, those three lines barely help answer:

- **Which operation** was performed: creating an order, updating a profile, revoking permissions, exporting a report?
- **Which target object** was affected: order ID, job ID, resource ID, message ID?
- **Which request/message/operation** produced that log record?
- **What the actual outcome** was: completed, denied, failed, retrying, or merely accepted?
- **Which component** emitted the log: service, module, method, deployment, instance?
- **When and for how long** did the event occur?
- **Why did it fail**—is there an error code, exception, or causal relationship?

A short message is not automatically an anti-pattern. `Application started` in a startup log that already carries timestamp, logger, service, and version in an appropriate envelope can still be sufficient. The problem arises when **information needed for investigation or operations is missing and cannot be reliably inferred** from other fields.

**Goal:** log just enough context so that an event is **self-explanatory**, easy to search, and easy to correlate, without turning every log into a dump of request payloads, sessions, tokens, or personal data.

## 2. Why Does Missing Context Make Incident Troubleshooting Difficult?

Suppose an order-processing system emits:

```text
09:00:00.100 INFO Updated
09:00:00.104 ERROR Failed
09:00:00.107 INFO Retry
09:00:00.110 INFO Done
```

Without `orderId`, `requestId`, `operation`, and `outcome`, it is impossible to tell whether `Failed` belongs to the same order as `Done`. One event could come from another worker or another instance. Timestamp proximity does not prove causality.

Common impacts:

1. **Increased Mean Time to Resolution (MTTR):** engineers must search for additional stack traces, grep across multiple services, or reproduce the error.
2. **Inaccurate search results:** querying `message contains "failed"` pulls in completely different failure types.
3. **Hard-to-analyze failure rates:** inability to distinguish actions or outcomes via standardized fields.
4. **Misleading root-cause investigation:** treating logs that happen to be close in time as belonging to the same request even when they are unrelated.
5. **Noisy monitoring:** without stable error codes, alerts rely on free-form messages that can change from one release to the next.
6. **Missing business evidence:** an `Updated` record does not tell you what changed or whether the transaction committed.
7. **Difficulties in distributed environments:** logs from multiple replicas, queue consumers, background jobs, and HTTP requests interleave.
8. **Pressure to add more logs:** because each line is so information-poor, teams tend to log multiple lines at every layer to compensate, easily leading to a log storm.

Changing `log.info("Done")` to `log.info("Done " + requestId)` only solves part of the problem. You still need to clarify **what was done**, the target object, and **the point at which success was confirmed**.

## 3. What Is the Minimum Required Context?

There is no single mandatory set of fields for every log. Start from **the questions an operator will ask** and **the type of event being emitted**.

| Question Category | Suggested Fields | Example |
| --- | --- | --- |
| **What happened?** | `event`, `operation` | `order.create.result`, `CREATE_ORDER` |
| **Which target?** | `orderId`, `resourceType`, `resourceId` | `ord-42` |
| **Which execution?** | `requestId`, `operationId`, `messageId`, `jobRunId` | `req-101` |
| **Outcome?** | `outcome`, `reasonCode` | `SUCCEEDED`, `ROLE_MISSING` |
| **Where?** | `service.name`, logger name, environment, instance | `orders-api`, `production` |
| **When?** | UTC timestamp, duration | `2026-11-10T02:00:00Z`, `27ms` |
| **Who?** | Authenticated actor ID if meaningful and permitted | `admin-7` |
| **Why?** | Error code, exception type/cause, policy | `STORAGE_UNAVAILABLE` |
| **How related?** | `traceId`, `spanId`, `correlationId` | A related trace/operation |

**Log context = envelope + event data.** Timestamp, level, logger, and service are sometimes added automatically by the backend/collector; there is no need to duplicate them in the message if the system reliably stores them. Business-meaningful fields such as action, target, and outcome usually must be provided by the logging code itself.

A good log record should answer at least: **"What happened, to which target, in which execution, and with what outcome?"** — tailored to the sensitivity and purpose of the event.

## 4. Before/After: Turning Vague Logs into Meaningful Logs

| Anti-pattern | More Useful Record | Benefit |
| --- | --- | --- |
| `INFO Updated` | `event=profile.email.changed userId=u-42 outcome=SUCCEEDED` | Identifies update type and target |
| `ERROR Failed` | `event=payment.capture.failed paymentId=p-7 errorCode=PROVIDER_TIMEOUT` | Identifies action and error category |
| `INFO Done` | `event=order.create.result orderId=ord-42 outcome=SUCCEEDED` | Identifies operation and outcome |
| `WARN Retry` | `event=message.retry_scheduled messageId=evt-9 attempt=3 reason=DEPENDENCY_UNAVAILABLE` | Places retry in the lifecycle |
| `INFO Request received` | `event=http.request.received requestId=req-101 route=/api/orders/{id} method=POST` | Correlates with a specific HTTP request |
| `ERROR Database error` | `event=order.persist.failed operationId=op-9 errorCode=DB_CONNECTION_TIMEOUT` with Throwable | Provides root cause and context |
| `INFO Starting` | `event=job.run.started job=nightly-settlement runId=run-72` | Distinguishes between job runs |
| `INFO User authenticated` | `event=auth.login.result outcome=SUCCEEDED actorId=u-42` | Identifies the security event type |

These field/event names are **design patterns**, not mandatory formats of JUL, Logback, Log4j 2, or OpenTelemetry. Establish a consistent schema and naming convention for your system.

Do not add `rawEmail`, `password`, `accessToken`, or `fullRequestBody` just to "have more context." **Quality** context means necessary and permitted information, not as much data as possible.

## 5. Distinguishing Event Codes, Free-Form Messages, and Outcomes

An **event code** is a value with stable semantics, for example:

```text
order.create.started
order.create.result
order.persist.failed
payment.authorize.result
message.processing.failed
job.run.completed
auth.login.denied
```

**Message text** is for human readers and may be translated or rephrased. **Outcome** expresses the result at a specific boundary:

```json
{
  "event": "order.create.result",
  "operation": "CREATE_ORDER",
  "orderId": "ord-42",
  "outcome": "DENIED",
  "reasonCode": "ROLE_MISSING"
}
```

This data states that **an order creation request was denied**, not that an order was created. `order.create.result` is the result of processing the order creation request; only set `outcome=SUCCEEDED` when the actual success conditions have been met.

Three common design patterns:

- **Event + outcome:** `event=order.create.result, outcome=SUCCEEDED|DENIED|FAILED`.
- **Milestone-based events:** `order.creation.requested`, `order.created`, `order.creation.denied`.
- **Action + phase + outcome:** `action=CREATE_ORDER, phase=RESULT, outcome=FAILED`.

Choose one documented standard. Do not emit `order.created` as soon as an HTTP request is received or before the transaction commits; that makes the log **factually false**, even if it has plenty of context.

### 5.1. Context Must Follow the Actual Lifecycle

An HTTP request returning `202 Accepted` may only prove that a job was enqueued; it does not prove the job finished. A `Kafka Acknowledgment.acknowledge()` call may only request the container to ACK/commit according to its mode; it does not necessarily confirm the offset is already durable at the call site. A message logging `Done` before a database commit can be completely wrong if a rollback occurs.

Therefore, **accurate lifecycle context matters more than writing an English sentence that sounds like success**. Log the exact milestone name: `accepted`, `processing_started`, `committed`, `delivery_requested`, `retry_scheduled`, `failed`.

## 6. Java 17: Runnable Program Comparing Context-Free and Contextual Logs

This Java 17 example uses only `java.util.logging` (JUL), with **no external dependencies**. It prints three lines:

1. A vague `Done` log.
2. A **succeeded** order creation result, with request ID, route, operation, target, outcome, and duration.
3. A **denied** order creation result, with a dedicated reason code.

To keep stdout **deterministic**, a custom handler prints only `level + message` without timestamps or thread names. All values are controlled constants. Production code should use a structured encoder, validation, and policy-compliant redaction instead of concatenating free-form strings directly.

Save as **`ContextualLoggingDemo.java`**:

```java
import java.util.Locale;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ContextualLoggingDemo {
    record Context(String requestId, String route, String operation) {}

    private static void logResult(
            Logger logger,
            Context context,
            String orderId,
            String outcome,
            String reason,
            long durationMs) {

        String message = String.format(
                Locale.ROOT,
                "event=order.create.result requestId=%s route=%s "
                        + "operation=%s orderId=%s outcome=%s "
                        + "reason=%s durationMs=%d",
                context.requestId(),
                context.route(),
                context.operation(),
                orderId,
                outcome,
                reason,
                durationMs);

        logger.info(message);
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.contextual");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler output = new Handler() {
            {
                setLevel(Level.ALL);
            }

            @Override
            public void publish(LogRecord record) {
                if (record != null && isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        logger.addHandler(output);
        try {
            // Anti-pattern: impossible to know which operation "Done" refers to.
            logger.info("Done");

            logResult(
                    logger,
                    new Context(
                            "req-101",
                            "/api/orders/{id}",
                            "CREATE_ORDER"),
                    "ord-42",
                    "SUCCEEDED",
                    "NONE",
                    27);

            logResult(
                    logger,
                    new Context(
                            "req-102",
                            "/api/orders/{id}",
                            "CREATE_ORDER"),
                    "ord-43",
                    "DENIED",
                    "ROLE_MISSING",
                    4);
        } finally {
            logger.removeHandler(output);
            output.close();
        }
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac ContextualLoggingDemo.java
java ContextualLoggingDemo
```

Exact **`stdout` output**:

```text
INFO Done
INFO event=order.create.result requestId=req-101 route=/api/orders/{id} operation=CREATE_ORDER orderId=ord-42 outcome=SUCCEEDED reason=NONE durationMs=27
INFO event=order.create.result requestId=req-102 route=/api/orders/{id} operation=CREATE_ORDER orderId=ord-43 outcome=DENIED reason=ROLE_MISSING durationMs=4
```

### 6.1. Explaining the Example

- `record Context` represents three request-related fields using modern Java syntax. A `record` does not automatically validate `requestId` or `route`.
- `logger.info("Done")` cannot answer what was completed.
- The next two lines share the same `event` and `operation` but differ in `requestId`, `orderId`, and `outcome`, enabling separate querying and reasoning.
- `reason=ROLE_MISSING` is a **reason code** decided by code, not arbitrary error message text.
- `durationMs` is a fixed value for illustration: in a real application, measure it using a monotonic clock such as `System.nanoTime()` around the measured work.
- `setUseParentHandlers(false)` avoids extra records from parent handlers when running the demo.
- The custom handler prints only the content for stable stdout; it does **not** produce JSON, persist logs durably, manage rotation, or replace a collector.
- All context in the example consists of constant strings. **Do not use this text concatenation approach to log untrusted raw input**, as it risks log injection and parsing errors.

The program does not access a database or API. The two outcomes are simulated to illustrate message design; the `SUCCEEDED` record is not proof that a real order was committed.

### 6.2. Which Output Is Easier to Query?

With the three lines above, a conceptual filter:

```text
event = order.create.result
AND outcome = DENIED
AND reason = ROLE_MISSING
```

filters out denied operations — **if** the pipeline stores/parses the fields as intended. `INFO Done` cannot be accurately grouped under any operation without external context.

**A `key=value` text fragment does not automatically become structured data.** A backend that stores only a monolithic `message` field will still need a parser. Production systems should emit key-value fields through a supported API or an appropriate JSON encoder.

## 7. From "Wordy Messages" to True Structured Logging

A log such as:

```text
Order failed for order ord-42 because database was not available in region east
```

is easier to read than `Failed`, yet still hard to query reliably: sentence order/wording can change, region names may carry non-standard semantics, and parsers depend on regex.

A **structured** event:

```json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "level": "ERROR",
  "service": "orders-api",
  "event": "order.persist.failed",
  "operation": "SAVE_ORDER",
  "requestId": "req-101",
  "orderId": "ord-42",
  "outcome": "FAILED",
  "errorCode": "STORAGE_UNAVAILABLE",
  "durationMs": 27
}
```

These values are **illustrative**, not from a real application. The `errorCode` field supports stable reporting/alerting instead of copying `Exception.getMessage()` verbatim.

A schema can be standardized with:

- Event names in the form `domain.resource.action.phase` or another consistent convention.
- Outcome and errorCode enums with a controlled set of values.
- IDs with validated format/length.
- Fixed field names and data types (`durationMs` as a number, not `"27ms"`, if numeric queries are needed).
- Timestamp, service, and environment provided by a trusted layer.
- Schema version if semantics or required fields change.

**Do not try to cram all information into a single message** if the log backend can store separate fields. That is the difference between a "long message" and a "structured event."

## 8. SLF4J and Logback: How to Write Logs with Context

In an SLF4J application, a common pattern is:

```java
// Integration snippet: log is org.slf4j.Logger; variables are already in scope.
log.info("event=order.create.result orderId={} outcome={} requestId={}",
        safeOrderId, outcomeCode, validatedRequestId);
```

**The `{}` placeholder does not automatically turn arguments into JSON fields.** It formats the string and avoids building the final message when the level is disabled (though expensive argument-building expressions are still evaluated beforehand). With a standard Logback pattern, the result is still a plain string.

With **SLF4J 2.x** and a compatible backend/provider, you can use the **fluent key-value API**:

```java
// Integration snippet: log has type org.slf4j.Logger;
// safeOrderId, validatedRequestId, and outcomeCode are already declared.
log.atInfo()
        .addKeyValue("event", "order.create.result")
        .addKeyValue("operation", "CREATE_ORDER")
        .addKeyValue("orderId", safeOrderId)
        .addKeyValue("requestId", validatedRequestId)
        .addKeyValue("outcome", outcomeCode)
        .log("Order creation attempt finished");
```

This is **not a standalone Java file**. It requires SLF4J 2.x and a corresponding logging provider. `addKeyValue` attaches attributes to the event at the API level; **whether they are emitted as JSON fields** depends on the backend, encoder/layout, and configuration. Do not assume every provider renders key-values in the same format.

Log4j 2 provides `ThreadContext` and corresponding structured APIs; JUL uses `LogRecord`, resource bundles, or custom formatters/handlers. **Do not mix Logback and Log4j 2 configurations**, and do not mistake a text pattern for JSON structured logging.

### 8.1. Where Should Context Live?

- **Per event:** operation, outcome, orderId, errorCode specific to the event.
- **Per request/trace:** requestId, traceId, and reliably determined tenant scope.
- **Per deployment:** service.name, version, environment, and instance/pod ID added by logging infrastructure.

Copying a large request context into every log can increase volume and cost. For business-independent event logs, include only the fields genuinely needed for analysis and auditing.

## 9. MDC: Propagating Context Across Logs in a Flow

In SLF4J, **MDC (Mapped Diagnostic Context)** helps attach key-value pairs to the thread/provider logging context so that events within a request can share IDs.

A snippet in a Java web service:

```java
import org.slf4j.MDC;

// Integration code: validatedRequestId is a validated value.
String previous = MDC.get("requestId");
try {
    if (validatedRequestId == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", validatedRequestId);
    }

    processBusinessRequest();
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
```

This is **not a standalone program**; `processBusinessRequest()` and `validatedRequestId` must be provided by the application.

Important conditions:

1. **MDC does not emit logs by itself.** Logback/Log4j 2 must have an encoder/pattern configured to output the value—for example, Logback can use `%X{requestId}`.
2. **Thread pools reuse threads.** If you do not remove/restore in `finally`, a subsequent request may inherit the previous request's ID.
3. **MDC is typically thread-bound.** When using `CompletableFuture`, executors, callbacks, reactive processing, or message listeners, do not assume context propagates automatically across threads.
4. **Never put raw client headers directly into MDC.** IDs must be validated or generated at the gateway/trust boundary according to policy.
5. MDC is suited for small, bounded fields; do not store raw payloads, large objects, tokens, or full user profiles.
6. **A single request may invoke multiple business operations.** An MDC `requestId` does not replace `operationId`, `transactionId`, or event-specific targets.

A log with a valid `requestId` but missing `operation` can still be ambiguous; MDC is **a tool**, not a silver bullet for context-free messages.

## 10. Context Across Async Boundaries: Java 17 Runnable Demo

In async tasks, a common bug is setting `requestId` on thread A, then logging `Done` on thread B without propagating context. To demonstrate a safe approach, the following example **passes an explicit Context record into the task**, rather than relying on `ThreadLocal` which can be lost.

Save as **`AsyncLoggingContextDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class AsyncLoggingContextDemo {
    record Context(String correlationId, String messageId) {}

    private static String process(Context context) {
        return "event=message.processing.result"
                + " correlationId=" + context.correlationId()
                + " messageId=" + context.messageId()
                + " outcome=SUCCEEDED";
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Context context = new Context("corr-01", "msg-07");
            Future<String> result = executor.submit(
                    () -> process(context));
            System.out.println(result.get());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Run:

```bash
javac AsyncLoggingContextDemo.java
java AsyncLoggingContextDemo
```

**Exact stdout**:

```text
event=message.processing.result correlationId=corr-01 messageId=msg-07 outcome=SUCCEEDED
```

The example uses a real `ExecutorService` but **prints a string to stdout** without integrating a logging backend. Its purpose is to demonstrate that context can be carried into a task via explicitly passed data and emitted at the end of the task.

In production, you can use task decorators, `Runnable`/`Callable` wrappers, framework context propagation, or OpenTelemetry context scopes; if copying MDC, always **restore/clear in the task's `finally` block** rather than copying onto the thread and leaving it behind. On reactive stacks, use the framework's native context mechanism instead of assuming `ThreadLocal` is sufficient.

### 10.1. Do Not Confuse Correlation IDs with an Authenticated Actor

`correlationId` helps find events in the same flow; if supplied by a client, it can also be spoofed. Security events must separate the **authenticated actor** from correlation IDs. A trace ID does not prove that an operation succeeded, that the user was authorized, or that data was committed.

## 11. HTTP Web Logging: What Does a Complete Event Need?

A request may pass through a reverse proxy, authentication filter, controller, service, and database. If every layer logs `Request done`, finding errors becomes difficult.

An appropriate access event:

```json
{
  "event": "http.request.completed",
  "requestId": "req-101",
  "method": "POST",
  "route": "/api/orders",
  "status": 201,
  "durationMs": 38,
  "service": "orders-api",
  "outcome": "SUCCEEDED"
}
```

**Avoid using raw URLs/query strings in place of route templates** whenever possible: query strings may contain tokens, emails, or personal data, and paths with dynamic IDs cause high cardinality. `/api/orders/{id}` is far more useful than `/api/orders/431928` when aggregating by endpoint.

However, **HTTP status does not always equal business outcome**:

- `202 Accepted` usually only confirms job acceptance.
- `200` may return an application-defined `PENDING` status.
- An API might return `200` even when the body reports a business error (a design that should be reconsidered).
- Streaming requests may be interrupted after status/headers have already been sent.

Therefore, log at the right point in the request lifecycle, avoiding logging `completed` right upon entering the controller. With Servlet async or reactive processing, the moment a filter returns is not necessarily when the response finishes.

### 11.1. Should Client IP, User-Agent, and User ID Always Be Logged?

Not by default. These fields carry privacy and reliability risks:

- `User-Agent` is client-supplied and can be spoofed.
- The immediate IP may be a proxy/gateway; `X-Forwarded-For` must go through a trust policy.
- Raw user ID/tenant ID can be sensitive; retain only within necessary and permitted scope.
- Authenticated principals must come from a trusted authentication mechanism, **not** from arbitrary request parameters.

A request access event should minimize data while still supporting debugging and investigation. Logging "every single header" is not the right fix for the context-free anti-pattern.

## 12. Message Consumers: Context Must Tie to Delivery and Outcome

A consumer receiving events from Kafka/RabbitMQ/JMS might log `Received`, `Retry`, `Done`. If a message is redelivered after a crash/timeout, those lines become very hard to piece together.

Example event:

```json
{
  "event": "message.processing.failed",
  "consumerGroup": "billing-workers",
  "messageType": "OrderCreated",
  "messageId": "evt-77",
  "correlationId": "corr-01",
  "attempt": 2,
  "source": "orders-topic",
  "errorCode": "DEPENDENCY_UNAVAILABLE",
  "retryable": true
}
```

Depending on the broker, you can add **Kafka topic/partition/offset**, RabbitMQ exchange/routing key/delivery tag, or JMS message ID. **Do not use a RabbitMQ delivery tag as a global business event ID**, and do not apply Kafka offset semantics to JMS.

Crucially: logging `message.processing.succeeded` is **different** from `ack_requested` and `offset_commit_succeeded`. If database side effects committed but the offset was not committed, the message may be reprocessed. Therefore, you need an appropriate **idempotency key/transaction** to prevent duplicate business effects, alongside contextual logging.

In batch consumers, distinguish the **batch ID** from **individual message IDs**, and for partial results, log per-record outcomes or a summary with counts and operation links.

## 13. Scheduled Jobs and Background Tasks

For scheduled jobs, a `Job finished` log cannot distinguish between multiple runs or multiple instances.

Example:

```json
{
  "event": "job.run.completed",
  "jobName": "nightly-settlement",
  "runId": "run-20261110-01",
  "triggerType": "SCHEDULED",
  "outcome": "PARTIAL",
  "processedCount": 920,
  "failedCount": 3,
  "durationMs": 18420
}
```

This is an illustrative event. `processedCount`/`failedCount` must clearly define whether they count logical records, attempts, or side effects; do not derive counts by counting `Processed` log lines.

If a job retries, add a meaningful `attempt` or `retryOf`. If an error is caught but the scheduler needs to know the job failed, **do not swallow the exception after merely logging `Failed`**; report job status according to the scheduler contract.

## 14. Exception Logging: Missing Context and Lost Root Cause

Common anti-pattern:

```java
// Illustrative snippet to avoid.
catch (Exception e) {
    log.error("Failed");
}
```

This log lacks operation, target, error code, and **has no throwable**. Even:

```java
// Still diagnostically wrong: keeps only text, without stack trace/cause.
catch (Exception e) {
    log.error("Failed: {}", e.getMessage());
}
```

Better at an error boundary:

```java
// Integration snippet: safeOrderId and log are already declared.
// Do not log the same Throwable at every layer to avoid duplicate stack traces.
try {
    createOrder();
} catch (OrderProcessingException failure) {
    log.error("event=order.create.failed orderId={} errorCode={}",
            safeOrderId, "ORDER_CREATE_FAILED", failure);
    throw failure;
}
```

In this example, `createOrder()` and `OrderProcessingException` are application-defined, not a standalone Java file. In standard SLF4J, a `Throwable` as the final argument is treated as the cause of the logging event. If an overload is ambiguous, `log.error("Order creation failed", failure)` explicitly specifies the `Throwable`.

**Principles:**

1. When wrapping an exception, use `new SomeException("context", original)` to preserve `getCause()`.
2. Pass the **actual `Throwable`** to the logger, not just `getMessage()` or `toString()`.
3. Log vetted event codes and entity/correlation IDs.
4. At the boundary authorized to decide the outcome, log once with full information; avoid duplicating `ERROR`/stack traces across repository, service, and controller layers.
5. For expected validation errors, an `ERROR` stack trace is not always needed; choose the log level based on impact.
6. For retried errors, distinguish transient attempts from final failures.
7. Never expose raw SQL, passwords, tokens, payloads, or stack traces in public HTTP responses.

**A log with context but no `Throwable`** can still lack technical evidence. **A log with a `Throwable` but no request/operation** can still be hard to find in a high-traffic system. Combine both as required.

## 15. Trace, Span, requestId, and operationId: Using Each for Its Purpose

These IDs are not strictly equivalent:

| ID | Semantics |
| --- | --- |
| `requestId` | A single HTTP request or application entry point |
| `traceId` | A distributed tracing span chain, potentially across multiple services |
| `spanId` | A single span within a trace |
| `correlationId` | An identifier linking a group of operations/events by design |
| `operationId` | A business action, potentially spanning multiple requests/retries |
| `messageId` | A logical message |
| `attemptId` | A single execution or delivery attempt |

In a distributed system, request A may produce message B and then background job C. Carrying only an HTTP request ID into a message without clear context propagation easily leads to missing links or misused semantics. Define **cross-chain business identifiers** and design propagation through validated headers.

**Trace context does not store event history by itself**: spans can be sampled, trace exporters can drop data, and a trace ID is not a business event ID. When critical events require auditing, a separate audit record with appropriate durability/integrity is still necessary.

With OpenTelemetry instrumentation, trace/span IDs can be injected into logs, but verify your backend/encoder and propagation. Do not assume every `logger.info` automatically receives a trace ID.

## 16. Do Not Infer Context from Log Line Proximity

Incorrect example:

```text
INFO req-101 BEGIN
INFO processing
ERROR timeout
INFO req-102 BEGIN
INFO processing
INFO done
```

Having `processing` next to `req-101 BEGIN` **does not prove** it belongs to request 101. Thread pools and concurrency interleave logs; shipping from multiple instances can also reorder arrival.

Instead, important events carry correlation IDs **on the event itself** or stored in a trusted structured context:

```text
INFO event=request.started requestId=req-101
WARN event=remote.call.failed requestId=req-101 errorCode=TIMEOUT
INFO event=request.started requestId=req-102
INFO event=order.create.result requestId=req-102 outcome=SUCCEEDED
```

If using MDC, ensure context is restored properly across thread switches and **emitted by the encoder**. If the app and collector use different timezones or clocks, do not rely solely on timestamps to infer causality.

For **event ordering**, if the system must accurately reconstruct a multi-step workflow, consider adding `operationId`, `sequenceNo`, transaction version, or causation ID. UTC timestamps help, but they do not solve clock skew or distributed ingestion reordering.

## 17. Security: Adding Context Must Not Leak Data

Adding `requestBody`, `Authorization`, `password`, or `refreshToken` to messages in search of context is a far more dangerous anti-pattern.

Data categories to consider:

- **Credentials/secrets:** passwords, API keys, JWTs, session cookies, private keys, recovery codes; generally must never be logged.
- **Personal data:** email, phone number, address, user identifiers; log only if genuinely necessary, subject to authorization and retention.
- **Financial/medical details:** do not dump full entities or payloads when only IDs and error codes are needed.
- **Raw URL/query:** may contain tokens or sensitive data.
- **Client headers:** `User-Agent` and client-supplied correlation IDs can be forged.
- **Throwable messages:** may contain SQL, file paths, hostnames, request payloads, or secrets.

For example, `log.info("user={} payload={}", userId, payload)` is both expensive and risks data exposure. Choose **safe IDs, event types, reason codes, and aggregate metrics**.

### 17.1. Log Injection

A client-supplied string may contain newlines/control characters or text resembling a log level. If written directly into a text log:

```text
userName=Alice
ERROR admin permission granted
```

a reader or naive parser may interpret it as two separate events. You should:

1. Validate the format and enforce length limits on IDs.
2. Use a JSON/structured encoder with proper escaping.
3. Strip, escape, or replace control characters in text output.
4. Never let user-controlled fields determine file names, topics, indices, or destinations.
5. Test with Unicode, newlines, tabs, quotes, backslashes, and oversized values.
6. Do not treat SLF4J's `{}` as an automatic escaping/redaction mechanism.

Syntactic sanitization also **does not turn** a client-supplied field into a trusted source for authentication or security decisions.

## 18. Performance: Context Is Useful, Not Unlimited

Every added field increases bytes per event, encoding cost, I/O, and storage. In systems handling thousands of requests per second, over-logging can impact CPU, GC, network, and async queues.

Common performance mistakes:

- Logging entire object graphs via `toString()`, which may trigger lazy loading or traverse large payloads.
- Serializing JSON bodies even when `DEBUG` is disabled.
- Logging stack traces on every retry attempt, causing a log storm.
- Adding raw paths, user IDs, request IDs, or trace IDs as **metric labels**, causing high cardinality.
- Emitting many fragmented diagnostic lines instead of one well-populated event.
- Attaching raw context to every statement via MDC without intent.

When a value is expensive to compute:

```java
// Integration snippet: detailsBuilder.build() is CPU-intensive.
if (log.isDebugEnabled()) {
    log.debug("event=debug.snapshot requestId={} details={}",
            validatedRequestId, detailsBuilder.build());
}
```

Placeholders do not make `detailsBuilder.build()` lazy because Java evaluates argument expressions **before the method call**. Keep the guard or use a `Supplier`/lazy API when needed.

MDC for short IDs is usually cheaper than concatenating large payloads, though cost still depends on the logger, formatter, and pipeline. Do not use `requestId` as a metric label; use bounded labels such as `service`, `operation`, and `errorCode` from a controlled catalog.

## 19. Matching Context to Log Level and Event Type

Context-free logs often appear because developers add `println("here")` or `log.info("ok")` while debugging. Choose **event and level** according to purpose:

| Scenario | Typical Level | Key Context |
| --- | --- | --- |
| Service startup | INFO | service, version, environment, config revision |
| HTTP request completed | Access event/INFO per policy | route, method, status, duration, requestId |
| Business operation completed | INFO or business event | operation, entity ID, outcome, operationId |
| Expected validation error | INFO/WARN per policy | reasonCode, route, requestId |
| Self-healing retry | DEBUG/WARN by impact | attempt, maxAttempts, reason, dependency |
| Unrecoverable error at boundary | ERROR | event/errorCode, requestId, Throwable |
| Safe duplicate message | DEBUG/INFO | messageId, source, decision, attempt |
| Security/audit action | Separate audit channel per policy | authenticated actor, action, target, outcome |
| Detailed debug log | DEBUG/TRACE | local operation, redacted fields |

Not every event needs `userId`, `traceId`, and a stack trace. Context should be **sufficient for the questions of that event type**. Trying to force all logs into one giant schema with many null fields is not necessarily better than having per-event-type schemas.

## 20. Other Design Mistakes That Often Accompany This Anti-Pattern

### 20.1. Wrong Context Is Worse Than Missing Context

A worker that forgets to clear MDC causes request B's logs to carry request A's `requestId`. Investigations can then draw false conclusions about user behavior. Always restore context per scope and test thread reuse.

### 20.2. Generating New IDs at Every Layer

If the controller generates `req-101` and the service generates `req-999` without preserving a link, the chain cannot be correlated by ID. IDs should **propagate** according to policy, generating new ones only at the appropriate trust boundary or new operation.

### 20.3. Using One Message to Claim Multiple Outcomes

For example, logging `Payment processed` when the provider only accepted the request and has not settled it yet. Log `payment.submitted` and `payment.settled` separately if there are two distinct milestones.

### 20.4. Logging Many Steps Without a Final Outcome

A hundred `Start step` lines do not replace a single `operation.result` event with valid `outcome`, `durationMs`, counts, and `errorCode`.

### 20.5. Omitting Deployment Metadata

In a multi-instance cluster, `ERROR Failed` is even harder to debug without knowing the service/version/pod. Usually, logging infrastructure should attach deployment fields rather than concatenating them manually into every message.

### 20.6. Trusting Client-Supplied IDs

An attacker can send oversized IDs or spoof correlation IDs. Validate length/format, normalize, and use server-generated IDs when policy requires. Correlation IDs do not replace an authenticated principal.

### 20.7. Inconsistent Context Naming Across Layers

The controller uses `user_id`, the service uses `userId`, and the worker uses `uid`; centralized queries become hard to unify. Maintain a schema/catalog, tests, and backward compatibility.

### 20.8. Relying on Logger Name to Infer Every Business Action

Logger `com.example.OrderService` identifies the source component, but not the exact method or whether the operation succeeded. Event codes/operations must still be explicit.

### 20.9. Logging After a Catch and Swallowing the Error

```java
// Wrong: the caller may not know that processing failed.
try {
    processPayment();
} catch (Exception e) {
    log.error("Error");
}
```

This snippet only illustrates the anti-pattern. If policy requires retry or rollback, preserve state or throw an exception per contract—do not treat logging as error-control flow.

### 20.10. Assuming Any Log Counts as Durable Audit Evidence

The app may filter/drop logs, a sidecar may back up, disk may fill, or the collector may lose network connectivity. Mandatory audit trails require dedicated durability/integrity policies, retention, read permissions, and reconciliation; even a context-rich event can still be lost.

## 21. Testing Context Quality in Logging

Do not only test that `logger.info` was called. Test **the information needed for investigation** and **its accuracy**:

| Scenario | What to Verify |
| --- | --- |
| Operation succeeded | Has event, operation, target, `SUCCEEDED` after success boundary |
| Denied due to missing permission | `DENIED`, reasonCode; not mistakenly logged as success |
| Validation failed | Valid fields present, no payload leaked |
| Database transaction rollback | No false `committed` event |
| Exception wrapped across layers | `Throwable`/cause chain preserved |
| Two concurrent requests | Each event carries its own `requestId`, no cross-request bleed |
| Thread pool reuse | MDC cleared/restored, no context leak |
| CompletableFuture/executor | Context propagated accurately or intentionally absent |
| Background job retry | Distinct `attempt`, `runId`, and `outcome` per run |
| Kafka/Rabbit redelivery | Message ID and delivery attempt not confused |
| Missing correlation header | Fallback present, no NPE |
| ID containing newline/control chars | No forged log lines created |
| Field with token or PII | Secret redacted/not emitted to sink |
| Logger level/filter changed | Understand which events may be suppressed and why |
| Collector timeout/drop | Do not assume emit = persisted |
| High-cardinality metrics | No metric labels created from user/request IDs |
| JSON encoder | Field types, escaping, `Throwable`, and timestamp are correct |
| Schema version change | Old queries do not misinterpret new event semantics |

An integration testing approach:

1. Configure a **test appender/handler** to capture log events in a dedicated layer.
2. Invoke the business handler with a fixed `requestId` and simulated state.
3. Assert **event code, outcome, IDs, and `errorCode`**; do not only match a free-text sentence.
4. For failures, assert that `Throwable` is not lost.
5. For concurrent executions, run multiple tasks and verify each event has the right context.
6. Test the parser/JSON exporter against a test collector if the pipeline has multiple stages.
7. Verify no passwords/tokens/secrets/PII appear outside policy.
8. Use markers or event IDs to detect missing/duplicate events during collector retries.

In JUL, you can inspect `LogRecord.getThrown()` and `getMessage()`; in Logback, use a test appender with logging events; in Log4j 2, use its corresponding test appender mechanism. If you change the backend/encoder, re-test at the **final storage sink**, not only in the JVM.

### 21.1. How to Review a Log Line

In a code review, ask:

- If I see **only this single line** in a centralized log system, can I tell what happened?
- Is there a way to distinguish success, denial, and failure?
- Can all logs for a single operation/request/message be found?
- Does the context come from a trusted source or untrusted user input?
- Is it logged at the right commit/ACK/response-completion milestone?
- Do any fields contain secrets, raw payloads, or high-cardinality IDs?
- Is the stack trace or event being logged redundantly?
- If the backend switches from pattern layout to JSON, will the schema remain stable?

**You do not need a separate log for every method.** Some places only need metrics/tracing; place logs where **an explainable event occurs**, avoiding extra noise.

## 22. Process for Upgrading a System Full of Vague Logs

If a project already has thousands of `Done`, `Start`, and `Failed` lines, you do not need to fix everything in one commit. An orderly approach:

1. **Inventory by risk:** locate logs in payments, auth, data exports, orders, message retries, and critical API paths.
2. **Group by event:** determine whether each line describes a request lifecycle, business operation, error, or debug progress.
3. **Define a small schema:** `event`, `operation`, `target ID`, `outcome`, `requestId`, and `errorCode` when needed.
4. **Standardize context acquisition:** middleware, authenticated principal, message headers, operation ID; avoid shared static mutable fields.
5. **Choose emission boundaries:** after commit, after deny decision, after retry scheduled, at appropriate error boundaries.
6. **Upgrade the encoder:** if querying fields, use real structured logging and verify the provider/collector.
7. **Test concurrency and async:** prevent MDC leaks, lost correlation, and misleading out-of-order logs.
8. **Remove redundant logs:** once a complete event exists, drop leftover `here`/`done` lines that no longer add value.
9. **Add alerts on standard error codes:** do not rely on constantly changing message wording.
10. **Review cost and retention:** context is valuable, but volume and security must stay under control.

Measure before/after by **the ability to answer a real investigation question**. For example: "In the last 30 minutes, how many `CREATE_ORDER` calls were `DENIED` with `ROLE_MISSING` in service `orders-api`?" If the new schema answers that without manual grepping, that is real improvement.

## 23. Checklist for Implementing Contextual Logging

- [ ] Every important event has a stable **action name/event code**.
- [ ] Every result record has an accurate **outcome** at the business boundary.
- [ ] Target ID/target type is included when objects must be distinguished.
- [ ] `requestId`, `operationId`, `messageId`, or `runId` is present as appropriate for the workload.
- [ ] Trace/correlation IDs are not confused with an authenticated actor.
- [ ] Service, environment, deployment version, and timestamp are reliably added by logging infrastructure.
- [ ] Logger/event fields are emitted as structured data by the encoder when analysis is needed.
- [ ] MDC is restored/cleared and propagated properly across thread pools/async boundaries.
- [ ] For exceptions, the **Throwable/cause chain** is preserved and duplicate logging across layers is avoided.
- [ ] `SUCCEEDED` is never logged before commit, nor is an ACK request called a durable ACK.
- [ ] Raw passwords, tokens, cookies, bodies, query strings, and unnecessary PII are never logged.
- [ ] Inputs are escaped/validated, protected against log injection, and bounded in length.
- [ ] `requestId`/`userId`/raw paths are not used as high-cardinality metric labels.
- [ ] Log volume, rotation, backpressure, and collector delivery are monitored.
- [ ] Event fields, business outcomes, concurrency, async, and sink readback are tested.
- [ ] For mandatory audit trails, dedicated retention/durability/integrity controls are used instead of relying solely on diagnostic logs.

**Conclusion:** **"Context-free log messages"** are not wrong because a sentence is short, but because the record **lacks enough reliable information to state what happened, where, to which target, in which execution, and with what outcome**. The fix is to design **event codes, properly scoped context, correlation IDs, outcomes, and error codes**, log at real lifecycle boundaries, use structured logging when analysis is needed, and **keep data minimal and safe**. A short, structured, semantically accurate event is far more useful than many long `Done`/`Failed` lines that cannot be correlated.
