# Differences Between Synchronous Call Errors and Asynchronous Event Processing Errors

> **Chapter:** Serverless  
> **Module:** SPRING_CLOUD_FUNCTION  
> **Focus:** Distinguish request/response errors from asynchronous event-processing errors; understand responses, acknowledgements, retries, dead-lettering, and idempotency when the same `Supplier`, `Function`, or `Consumer` bean runs via HTTP, AWS Lambda, Azure Functions, Google Cloud Run functions, and message brokers.  
> **Reference baseline:** November 24, 2026. Java examples use Java 21, Spring Boot 4.2.0, Spring Cloud BOM 2026.0.0, and Spring Cloud Function 5.1.0. Retry/ack policies depend on the trigger, broker, adapter, and deployment configuration.

## 1. Same Exception, Two Different Handling Contracts

Suppose a business bean normalizes an order code:

~~~java
@Bean
public Function<OrderCommand, OrderResult> normalizeOrder() {
    return command -> {
        if (command.code() == null || command.code().isBlank()) {
            throw new InvalidOrderException("Missing order code");
        }
        return new OrderResult(
                command.eventId(),
                command.code().trim().toUpperCase(Locale.ROOT));
    };
}
~~~

If a caller sends a synchronous HTTP request, the exception can map to **HTTP 400** so the caller fixes the input. The caller is waiting for a response and can decide whether to resend.

If the same command arrives from a queue, throwing an exception from the handler can cause the runtime/broker **not to acknowledge the message**, redelivering it per the retry policy. If the data is permanently invalid, endless retries repeat the exact same failure and can clog the queue.

The key question is not merely "which exception does the function throw?"—it is: who is waiting for the result, who decides the request/event succeeded, is the error returned to a caller or retained in a queue, and if the event re-runs, will side effects execute twice?

**Spring Cloud Function keeps business logic reusable; the adapter and platform decide how an exception becomes a response, nack, retry, or dead-letter.**

### 1.1. Diagram of the Two Paths

~~~mermaid
flowchart TB
    subgraph Sync["Synchronous invocation"]
        C["Client"] --> H["HTTP handler / adapter"]
        H --> F["FunctionCatalog"]
        F --> B["Business Function"]
        B -->|Success| R["HTTP response 2xx"]
        B -->|Exception| E["HTTP error response"]
        E --> C
        R --> C
    end

    subgraph Async["Asynchronous event processing"]
        P["Producer"] --> Q["Queue / event broker"]
        Q --> W["Trigger / event adapter"]
        W --> FC["FunctionCatalog"]
        FC --> BB["Business Function / Consumer"]
        BB -->|Complete| ACK["Ack / checkpoint / complete"]
        BB -->|Exception| NACK["Nack / unacked / batch failure"]
        NACK --> RETRY["Retry / redelivery"]
        RETRY --> W
        RETRY --> DLQ["DLQ / failure destination"]
    end
~~~

This diagram is a conceptual model. Exact ack/nack operations and retry rules differ across SQS, Kafka, Azure Service Bus, Pub/Sub, and individual adapters.

### 1.2. Learning Objectives

After this lesson, you will be able to:

1. Explain synchronous invocation vs. asynchronous event processing.
2. Distinguish HTTP responses, Lambda Invoke API responses, event acceptance, and broker acknowledgements.
3. Identify the layer responsible for retries on AWS, Azure, and Google Cloud.
4. Classify permanent, transient, and uncertain-outcome errors.
5. Design idempotency, DLQs, partial batch responses, and redrive procedures.
6. Understand the role of `FunctionCatalog` and why the catalog does not define retry policies on its own.
7. Write tests exercising the same business function across both boundaries.

## 2. Synchronous vs. Asynchronous: Differing Completion Contracts

### 2.1. Synchronous Invocation

A caller sends a request and waits for a result:

1. The client sends an HTTP request or invokes a synchronous API.
2. The handler authenticates, parses the payload, and calls the function.
3. The function returns a result or throws an exception.
4. The adapter maps the outcome to a response or error.
5. The client receives the response or hits a timeout.

There is an **active caller waiting**. Results are communicated through the response contract; the client or upstream service typically decides on retries. A client or gateway timeout does not prove business code never ran or never wrote data.

### 2.2. Asynchronous Event Processing

A producer emits an event, and a consumer processes it later:

1. The producer publishes an event to a queue/broker or requests an asynchronous provider invocation.
2. The producer receives acceptance confirmation per the source's contract.
3. The trigger/runtime delivers the event to the function.
4. The function processes it and signals success or failure per the adapter contract.
5. The event source decides whether to ack, retry, retain, route to a DLQ, or drop the event per policy.

**Accepted does not equal processed successfully.** Producers normally need a status API, callback, or result event to learn the final business outcome.

### 2.3. Comparison Table

| Criterion | Synchronous | Asynchronous |
| --- | --- | --- |
| Who is waiting? | Client/caller waits for response. | Producer usually only waits for broker/provider acceptance. |
| Success signal | HTTP status/body or API response. | Ack/checkpoint/complete per trigger contract. |
| Business error | Mapped to response/error for caller. | Signaled to runtime/broker for retry, quarantine, or DLQ. |
| Who retries? | Caller/SDK/gateway per policy. | Trigger, broker, provider, or event source mapping. |
| Duplicates | Client may resend after a timeout. | Redelivery / at-least-once delivery can produce duplicates. |
| Final outcome | Usually returned in the response. | Often requires a separate job-status or result event. |
| Best suited for | Validation, queries, fast commands. | Event integration, batches, side effects, deferrable work. |

## 3. Errors Can Occur Across Many Layers

~~~mermaid
flowchart TD
    A["Client / producer"] --> B["Gateway / broker"]
    B --> C["Provider runtime + handler"]
    C --> D["Deserialize / convert / route"]
    D --> E["FunctionCatalog"]
    E --> F["Business function"]
    F --> G["Database / API / storage"]
    G --> H["Serialize result / side effect"]
    H --> I["Response / ack"]
~~~

| Layer | Example errors | Notes |
| --- | --- | --- |
| Client/network | DNS, TLS, client timeout | Client cannot be sure whether the server processed it. |
| Gateway/ingress | 401, 403, 413, rate limit, integration timeout | The function may never have been invoked. |
| Provider runtime | Cold start failure, OOM, invocation timeout | Runtime may reset or redeliver the event. |
| Conversion | Malformed JSON, invalid Base64, missing fields | The business function may not have run. |
| `FunctionCatalog`/routing | Wrong definition, bean not found | Configuration/integration error. |
| Business logic | Validation, invalid state | Typically a permanent error. |
| Downstream | DB unavailable, API 429/503 | Typically a transient error. |
| Response/ack | Serialization failure, dropped connection, ack failure | Side effects may already have committed before the error. |

**Seeing an exception in logs does not mean the business function executed.** If JSON conversion fails, the function may never have run. Conversely, the function may have committed to the DB before the response or ack was lost.

## 4. Synchronous: Responses Are Contracts with the Caller

### 4.1. HTTP Status Codes and Error Bodies

| Error category | Suggested HTTP response | Meaning |
| --- | --- | --- |
| Bad schema / missing fields | 400 Bad Request | Caller must fix input. |
| Unauthenticated / unauthorized | 401/403 | Caller needs valid credentials or permissions. |
| Resource not found | 404 | Target resource does not exist. |
| Conflict / disallowed state | 409 | Request conflicts with current state. |
| Rate limited | 429 | Caller should slow down and follow retry policy. |
| Downstream temporarily unavailable | 503 | Safe to retry after an appropriate delay. |
| Unexpected internal error | 500 | Never expose stack traces to callers. |

Example Problem Details-style error body:

~~~json
{
  "type": "https://api.example.com/problems/invalid-order",
  "title": "Invalid order",
  "status": 400,
  "code": "INVALID_ORDER_CODE",
  "detail": "Order code must match pattern AA-999",
  "correlationId": "corr-42"
}
~~~

Never return internal class names, SQL statements, access tokens, or stack traces.

### 4.2. Timeouts Do Not Prove a Request Failed

Suppose a client sends `POST /orders`. The server receives the request and writes the order successfully, then the connection drops before the client reads the response. The client observes a timeout even though the order already exists. If the client resends without an idempotency key, the system may create a duplicate order.

**Synchronous does not guarantee exactly-once execution.** Design idempotency for mutating commands, even over HTTP.

### 4.3. HTTP 202 Only Confirms Acceptance

For long-running work, an API can return:

~~~http
HTTP/1.1 202 Accepted
Location: /jobs/job-42
Content-Type: application/json

{"jobId":"job-42","status":"ACCEPTED"}
~~~

`202 Accepted` means the request was accepted for processing; **it does not claim the task has finished**. Clients must poll `GET /jobs/job-42`, receive a webhook, or subscribe to completion events. Job state must be persisted durably, never stored in a Spring singleton bean field.

## 5. AWS Lambda: Three Invocation Modes You Must Not Equate

### 5.1. `RequestResponse` — Synchronous Invocation

When calling the Lambda Invoke API with:

~~~text
InvocationType = RequestResponse
~~~

the caller waits for the function to run and returns the response. If the function throws an exception, the Invoke API response may still carry **HTTP status 200 at the Lambda Invoke API layer** alongside an `X-Amz-Function-Error` header and error payload. When calling the Invoke API directly, never check HTTP status alone; inspect that header and error payload.

Through API Gateway or a Function URL, the HTTP response seen by clients depends on the integration/adapter and response mapping. Never apply Lambda Invoke API's `X-Amz-Function-Error` behavior mechanically to HTTP proxy responses.

AWS does not automatically retry function errors on `RequestResponse` invocations simply because the function threw an exception. The caller or upstream service decides whether to retry.

### 5.2. `Event` — Asynchronous Invocation

When invoking Lambda with:

~~~text
InvocationType = Event
~~~

Lambda places the event onto an internal queue and normally returns **202 Accepted** once queued. That response **is not the business processing result**.

Under default asynchronous invocation settings:

- Function errors are retried up to **two additional times** (up to three total attempts normally).
- Throttling/system errors follow separate retry/backoff rules; events can remain queued up to the maximum event age.
- Events can be delivered more than once even when the function throws no errors due to queue semantics.
- You can configure maximum retry attempts, maximum event age, a DLQ, or an on-failure destination.

Do not confuse asynchronous invocation retries with SQS event source mapping retries.

### 5.3. SQS Event Source Mapping: Batches Invoked Synchronously by a Poller

When Lambda polls SQS, Lambda fetches a batch and invokes your function via the event source mapping. This is a **distinct model**:

- The function is invoked synchronously with a batch event.
- If the batch succeeds, messages are deleted from the queue.
- If the invocation fails, messages may become visible again after the visibility timeout.
- By default, one failing record can cause the entire batch to be redelivered.
- With `ReportBatchItemFailures` enabled and a proper failing-item response, only reported failed records need reprocessing per contract.

Thus, **SQS → Lambda is not simply `InvocationType=Event`**. Retries are governed by the event source mapping and SQS visibility/redrive rules.

### 5.4. AWS Comparison Table

| Invocation mode | What the caller sees | Who retries? |
| --- | --- | --- |
| Lambda `RequestResponse` | Invocation response and function error details. | Caller/service retries per its own policy. |
| Lambda `Event` | 202 when Lambda accepts the event. | Lambda async queue per retry/age/destination settings. |
| SQS → Lambda event source mapping | Poller delivers batch; success/failure per batch response. | SQS/Lambda event source mapping per visibility timeout, redrive, and partial batches. |
| Kinesis/DynamoDB Streams | Batch records per shard/partition. | Event source mapping; errors can block a shard until resolved/expired or configured bisect/partial responses. |

## 6. AWS: Choosing the Right Place to Handle Exceptions and Batch Failures

### 6.1. Catching Errors and Returning Success Can Delete Messages

Dangerous example:

~~~java
@Bean
public Consumer<OrderCommand> consumeOrder() {
    return command -> {
        try {
            process(command);
        } catch (Exception exception) {
            log.error("Failed to process order", exception);
            // Neither rethrows the error nor writes durably to a DLQ.
            // The adapter may treat the invocation as successful.
        }
    };
}
~~~

For event consumers, returning normally allows the adapter/binder to mark the message as processed. Logging an exception **is not** a retry mechanism.

If you intentionally catch errors to route events to a DLQ or persist a failure record, report success only after the quarantine write is durable and auditable.

### 6.2. Partial Batch Responses

With SQS, responses can pinpoint failed records:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "message-id-2"}
  ]
}
~~~

When the event source mapping enables `ReportBatchItemFailures`, the adapter returns the message IDs requiring retry. If the handler throws an exception instead of returning a partial response, the entire batch may be marked failed.

**FIFO queues:** preserve message-group ordering. Upon error, do not continue processing subsequent records in the same group arbitrarily; report all unprocessed records per AWS guidance.

### 6.3. Stream Errors Differ from Queue Errors

With Kinesis/DynamoDB Streams, the event source mapping manages checkpoints per shard. A failing batch can retry and stall that shard at the checkpoint. Options such as bisect-on-error, partial batch responses, and maximum record age/attempts have stream-specific semantics. Never apply SQS visibility-timeout assumptions to Kinesis checkpoints.

## 7. Azure Functions: HTTP Responses and Trigger Retries Use Different Mechanisms

### 7.1. HTTP Triggers

With HTTP triggers, the handler returns a response to the caller. The caller inspects status/body and retries per client policy.

- 400/401/403 normally indicate invalid requests or permissions.
- 429/503 may signal backoff retries if allowed by the API contract.
- 500 indicates a server error; the caller must know whether the request is idempotent.
- A client timeout does not tell whether the function stopped or side effects committed.

Azure Functions does not enforce a single global retry policy across all HTTP requests. Any retries must be defined in clients, API gateways, or workflows.

### 7.2. Queue Storage Triggers

Azure Queue Storage triggers have their own poison-message mechanism. Per Azure docs, when a function fails, the runtime retries a message up to **five times total including the initial attempt**; if it still fails, the message moves to a queue suffixed with `-poison`.

This is specific to **Queue Storage triggers**—not a universal rule for Service Bus, Event Hubs, Kafka, or HTTP.

### 7.3. Service Bus Triggers and `PeekLock`

With Azure Service Bus triggers, the runtime receives messages in `PeekLock` mode:

- When the function finishes normally, the runtime defaults to calling `Complete`.
- When the function fails, the runtime defaults to calling `Abandon`, making the message eligible for redelivery.
- If a message exceeds the entity's `MaxDeliveryCount`, Service Bus can move it to the dead-letter queue.
- Locks can auto-renew up to the configured `maxAutoLockRenewDuration`.

This is **Service Bus's settlement contract**. A `void` Java method does not guarantee every message completes; exceptions and trigger configuration determine the outcome.

### 7.4. Azure Retry Policies Depend on the Extension and Trigger

Azure has two categories:

1. Retry behavior built into individual trigger/binding extensions.
2. Function-level retry policies executed by the Azure Functions runtime for supported triggers.

Documentation lists function-level retry policies for triggers such as Cosmos DB, Event Hubs, Kafka, and Timer; Queue Storage, Blob Storage, Event Grid, Service Bus, and RabbitMQ have extension-specific behaviors.

Therefore, **never just add `@Retryable` to a Spring bean assuming the Azure runtime will retry every event**. Configure trigger extensions, host settings, and broker policies explicitly.

## 8. Google Cloud Run Functions: HTTP Errors vs. Eventarc Retries

### 8.1. HTTP Functions

HTTP callers wait for status and responses. If a function returns an error or times out, the caller or workflow decides whether to resend. There is no built-in event queue automatically retrying synchronous HTTP requests just because a Java function threw an exception.

If a request wrote data before the response dropped, client retries can create duplicates. Use idempotency keys for mutating commands.

### 8.2. Event-Driven Functions

For Pub/Sub and Eventarc, retries belong to **trigger/subscription delivery policies**, not the Java bean:

- Pub/Sub push redelivers if a subscriber does not acknowledge.
- Eventarc triggers carry their own retry configuration.
- Depending on trigger creation, retries may be enabled or limited to a single delivery attempt.
- When retries are enabled, unhandled exceptions or non-success responses can trigger exponential-backoff redelivery.
- Retry windows, min/max backoff, delivery attempts, and dead-letter topics are configured on the subscription or trigger.

Cloud Run functions docs list HTTP status codes considered successful along certain delivery paths—including 102, 200, 201, 202, and 204—while other codes can be treated as negative acknowledgements when retries are enabled. **Verify your exact trigger**, and do not apply that status list blindly to ordinary HTTP APIs.

### 8.3. Acknowledgement Deadlines

Pub/Sub push and Eventarc deliveries enforce an acknowledgement deadline. If processing exceeds that deadline, the event may be redelivered while the original invocation is still running, leaving two workers processing the same event concurrently.

Size deadlines within provider limits, keep processing within budget, and enforce idempotency / atomic claims. Extending deadlines never replaces transactions or duplicate protection.

## 9. Spring Cloud Function: How Exceptions Travel Through the Catalog

### 9.1. `FunctionCatalog` Is Not a Retry Engine

Spring Cloud Function normalizes functional beans and provides wrappers for type conversion, composition, and lookup. When an adapter calls a function:

~~~text
HTTP / Event adapter
        |
        v
FunctionCatalog.lookup("normalizeOrder")
        |
        v
Function.apply(command)
        |
        +-- return result
        |
        +-- throw exception
~~~

If the function throws an exception, it propagates back up to the caller. **`FunctionCatalog` does not decide** to return HTTP 400, nack SQS, abandon Service Bus, or retry Pub/Sub. Adapters, binders, and providers hold the contract that interprets errors.

### 9.2. `Function` and `Consumer`

`Function<T,R>` returns a result. Over HTTP, the adapter serializes the result into a response. In Stream, the result publishes to an output binding.

`Consumer<T>` returns `void`. When a `Consumer` throws an exception, adapters/binders treat it as a failure; when it returns normally, triggers ack/complete per contract.

**Do not catch and merely log every exception in a `Consumer`** if you want the broker to retry. Catching and returning normally signals success.

### 9.3. Conversion Exceptions Differ from Business Exceptions

Examples:

- JSON fails to parse into `OrderCommand`: conversion/adapter error; the business function may never have run.
- `OrderCommand.code` violates format rules: validation error inside the business function.
- DB timeout during write: transient downstream error.
- Response serialization failure after business side effects committed: outcome uncertain for the caller/trigger.

Log and correlate at **each boundary** to tell whether failure occurred before or after side effects.

### 9.4. Never Use Retry Annotations as a Substitute for Trigger Policies

A retry annotation at the service layer only retries **an internal operation**. It does not replace retries from SQS, Lambda async invocations, Azure Service Bus, Eventarc/Pub/Sub, or HTTP callers.

If both the service and the broker retry, downstream call counts multiply across policies. Set overall budgets, timeouts, and idempotency guards.

## 10. Classifying Errors: Permanent, Transient, and Uncertain

### 10.1. Permanent Errors

Examples: invalid schema, missing event ID, malformed order code, unauthorized user, disallowed business state, or unsupported event schema version.

Retrying the exact same payload will not fix the problem. Return HTTP 400/403/409 synchronously; asynchronously, quarantine, dead-letter, or record a permanent failure per policy.

### 10.2. Transient Errors

Examples: database failover, connection timeouts, downstream 429/503 responses, brief network blips, provider throttling, or temporary overload.

Retry with backoff and jitter when the operation is idempotent and time/age budgets allow.

### 10.3. Uncertain-Outcome Errors

Examples: DB committed but response socket dropped; HTTP client timed out while the server finished; event consumer committed side effects then crashed before ack; provider sent a response but the broker failed to record settlement.

Never assume "timeout means retry safely" or "skip it." Query state by idempotency key or use transactions/outbox/inbox patterns.

### 10.4. Decision Matrix

| Error | Synchronous | Asynchronous |
| --- | --- | --- |
| Invalid input | Return 400/422 per API contract. | Avoid endless retries; quarantine, DLQ, or record permanent failure. |
| Insufficient permissions | Return 401/403. | Record security failure; do not retry like a transient error. |
| DB temporarily unavailable | 503/504 or coded error; caller applies bounded retry. | Rethrow to trigger policy-driven retry with backoff. |
| Downstream rate limit | 429/503 + `Retry-After` if appropriate. | Retry with backoff/jitter; cap concurrency. |
| Function timeout | Caller sees timeout/5xx per gateway; outcome may be uncertain. | Trigger may redeliver; require idempotency. |
| Serialization/ack failure after side effect | Caller may not receive result. | Message may be redelivered. |
| Unexpected code bug | 500, log/trace, and alert. | Throw error; bounded retries then DLQ/failure destination. |

## 11. Retries: Retry Only When Success Is Plausible

### 11.1. Exponential Backoff and Jitter

A common retry schedule:

\[
d_n = \min(d_{\max}, d_0 \times 2^n) + \text{jitter}
\]

where `d_0` is initial delay, `d_max` is max delay, and jitter prevents synchronized client retry waves.

Example: 1 s → 2 s → 4 s → 8 s with jitter, stopping after permitted attempts or event age. This is an **illustrative schedule**, not every provider's default.

### 11.2. Prerequisites Before Enabling Retries

Before turning on retries, define which errors are retryable, max attempts/event age, total backoff/jitter/deadline budget, downstream capacity, idempotency, where exhausted events go, and who owns redrives.

### 11.3. Preventing Retry Storms and Nested Retries

If an HTTP client retries 3 times, a service retries 3 times, and a broker retries 5 times, a downstream system can receive up to **45 attempts** for one event under simple multiplication. Exact counts depend on where failures occur, yet nested retries clearly amplify load.

Designate one primary retry orchestrator, bound internal retries, and enforce total attempt/deadline budgets. When downstream services are overloaded, shedding concurrency or tripping a circuit breaker beats retrying immediately.

## 12. Idempotency: Protecting Side Effects on Redelivery

### 12.1. Why Do Retries Cause Duplicates?

Suppose a consumer processes event `evt-42`:

1. Inserts the order into the database successfully.
2. Crashes before the broker receives ack.
3. The broker redelivers `evt-42`.
4. Without idempotency checks, the consumer inserts the order a second time.

This happens across queues, streams, webhooks, and HTTP client retries.

### 12.2. Using the Business Event ID as a Stable Key

A common pattern:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    result_reference VARCHAR(300),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

On receiving an event, a transaction attempts to insert the `(consumer_name, event_id)` key. On unique conflict, the event is already processed or in progress; return or handle per policy. On insert success, execute the side effect in the same transaction where possible and commit both atomically. Send ack only after the transaction commits.

This is a conceptual model; real implementations must account for transaction isolation, locking, in-progress states, and mid-flight crashes.

### 12.3. Do Not Confuse ID Types

| ID | Role | Good as a business idempotency key? |
| --- | --- | --- |
| Business event ID | Producer-issued business event identifier. | **Usually yes**, when stable and unique within scope. |
| SQS message ID / Pub/Sub message ID | Broker message identifier. | Useful for delivery-level dedup in scope; does not replace business operation IDs everywhere. |
| Lambda request ID | Single invocation identifier. | No; retries receive new request IDs. |
| HTTP correlation ID | Trace/call-chain linker. | Not by default; may span multiple requests. |
| Client-supplied idempotency key | Identifies one logical command. | Good when authenticated, durably stored, and scoped with TTL. |

### 12.4. Transactional Outbox

If one operation both updates a database and publishes an event, two separate writes can diverge: DB commits while publish fails, or publish succeeds while DB rolls back.

A **transactional outbox** writes business data and the outbound event in the same DB transaction; a separate relay publishes outbox rows. Consumers still need idempotency/inboxes because publishing and delivery can repeat.

## 13. Dead-Letter Queues and Poison Messages

### 13.1. What Is a DLQ For?

A DLQ or failure destination stores events that cannot be processed after retry limits expire. It keeps one bad message from blocking the pipeline forever, preserves payload/metadata for investigation, separates permanent data bugs from temporary outages, and enables controlled redrives after fixes.

A DLQ does not fix bugs by itself and must never become an unmonitored permanent dumping ground.

### 13.2. Fields Worth Retaining

A failure record should capture event ID and source/trigger, function/version, failure timestamp, error category/code, delivery count if provided, correlation/trace ID, protected payload or pointer, and redrive status.

Never dump access tokens, raw secrets, or unredacted sensitive payloads into uncontrolled logs or DLQs.

### 13.3. Safe Redrives

Before replaying a DLQ: verify the root cause is fixed; check event schema/version compatibility; inspect whether partial side effects already ran; retain original idempotency keys; throttle redrive rate; monitor outcomes; and keep an audit trail.

## 14. Partial Batch Failures: One Bad Event Should Not Fail the Whole Batch

### 14.1. SQS

With SQS event source mappings, invocation errors can redeliver the entire batch by default. Partial batch responses let you return only the failing record IDs when `ReportBatchItemFailures` is enabled on the event source mapping.

Java pseudo-code:

~~~java
List<BatchItemFailure> failures = new ArrayList<>();

for (SQSEvent.SQSMessage message : event.getRecords()) {
    try {
        processOne(message);
    } catch (PermanentMessageException ex) {
        quarantine(message, ex);
    } catch (TransientProcessingException ex) {
        failures.add(new BatchItemFailure(message.getMessageId()));
    }
}

return new SQSBatchResponse(failures);
~~~

This is pseudo-code because `SQSEvent`, `SQSBatchResponse`, and `BatchItemFailure` belong to AWS event libraries, while `quarantine` and `processOne` are application methods. For FIFO, halt processing subsequent records on failure per ordering rules and report all unprocessed records.

### 14.2. Kinesis / DynamoDB Streams

Streams order records by shard/partition and checkpoint. One failing record can stall the shard at that checkpoint. Features like partial batch responses, bisect-on-error, and max record age/attempts isolate poison records—provided you understand checkpoint and ordering semantics.

### 14.3. Azure and Google

Azure Service Bus and Queue Storage define their own settlement, delivery count, and poison/dead-letter rules. Google Pub/Sub and Eventarc use subscription/trigger acknowledgement and retry policies. Never try to return an `SQSBatchResponse` on those platforms.

## 15. Asynchronous HTTP: Returning 202 and Exposing Job Status

Some workflows are best split into two APIs:

~~~http
POST /jobs
Content-Type: application/json
Idempotency-Key: client-request-42

{"orderId":"order-42","operation":"RECONCILE"}
~~~

Response:

~~~http
HTTP/1.1 202 Accepted
Location: /jobs/job-9001
Retry-After: 3
Content-Type: application/json

{"jobId":"job-9001","status":"ACCEPTED"}
~~~

Workers then process the event asynchronously while clients poll `GET /jobs/job-9001` for `QUEUED`, `RUNNING`, `SUCCEEDED`, or `FAILED`. Persist job state durably—never in a Spring singleton bean field, since instances recycle.

**202 only confirms job acceptance per contract.** If queue publication fails, never return a fake 202. Use a transactional outbox to tie job state creation to event publication.

## 16. Hands-On Project: One Function, Two Error-Reporting Styles

This demo includes a `Function<OrderCommand,OrderResult> normalizeOrder` bean, a `Consumer<OrderCommand> consumeOrder` bean, a synchronous facade mapping exceptions to HTTP-like outcomes, and an asynchronous facade letting exceptions propagate back to the trigger adapter.

These facades are **boundary simulations**—not yet AWS Lambda handlers, Azure triggers, or Google Cloud Functions entrypoints.

### 16.1. Project Structure

~~~text
sync-vs-async-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/vn/example/errors/
    │   │   ├── OrderApplication.java
    │   │   ├── SynchronousOrderFacade.java
    │   │   └── AsynchronousOrderFacade.java
    │   └── resources/application.properties
    └── test/java/vn/example/errors/
        └── ErrorBoundaryTest.java
~~~

### 16.2. Maven `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.2.0</version>
        <relativePath/>
    </parent>

    <groupId>vn.example</groupId>
    <artifactId>sync-vs-async-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
        <spring-cloud.version>2026.0.0</spring-cloud.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2026.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The BOM manages Spring Cloud versions; `spring-cloud-function-context` supplies the catalog and function integration. The project omits Web starters and AWS/Azure/GCP adapters to focus on testing both boundaries inside the JVM.

### 16.3. Configuration

`src/main/resources/application.properties`:

~~~properties
spring.application.name=sync-vs-async-demo
spring.main.web-application-type=none
~~~

The project opens no HTTP port. `SynchronousOrderFacade` simulates mapping errors to HTTP status codes; add a Web controller/adapter for a live HTTP endpoint.

### 16.4. Business Function and Exception Types

Create `src/main/java/vn/example/errors/OrderApplication.java`:

~~~java
package vn.example.errors;

import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrderApplication {

    private static final Logger log =
            LoggerFactory.getLogger(OrderApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }

    public record OrderCommand(String eventId, String code) {}

    public record OrderResult(String eventId, String normalizedCode) {}

    public interface OrderStore {
        void save(OrderResult result);
    }

    public static class InvalidOrderException
            extends RuntimeException {
        public InvalidOrderException(String message) {
            super(message);
        }
    }

    public static class RetryableProcessingException
            extends RuntimeException {
        public RetryableProcessingException(
                String message, Throwable cause) {
            super(message, cause);
        }

        public RetryableProcessingException(String message) {
            super(message);
        }
    }

    @Bean
    public Function<OrderCommand, OrderResult> normalizeOrder() {
        return command -> {
            if (command == null ||
                    command.eventId() == null ||
                    command.eventId().isBlank()) {
                throw new InvalidOrderException("Missing event ID");
            }
            if (command.code() == null || command.code().isBlank()) {
                throw new InvalidOrderException("Missing order code");
            }

            String code = command.code()
                    .trim()
                    .toUpperCase(Locale.ROOT);

            if (!code.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new InvalidOrderException(
                        "Order code must match pattern AA-999");
            }
            return new OrderResult(command.eventId(), code);
        };
    }

    @Bean
    public OrderStore orderStore() {
        // Demo sink: logs only. Production uses repositories/transactions.
        return result -> log.info(
                "Demo save order eventId={}", result.eventId());
    }

    @Bean
    public Consumer<OrderCommand> consumeOrder(
            Function<OrderCommand, OrderResult> normalizeOrder,
            OrderStore store) {
        return command -> store.save(normalizeOrder.apply(command));
    }
}
~~~

`normalizeOrder` performs validation and normalization. `consumeOrder` reuses that exact logic and passes results to `OrderStore`. The demo store simply logs; production uses real persistence transactions and idempotency.

### 16.5. Synchronous Facade

Create `src/main/java/vn/example/errors/SynchronousOrderFacade.java`:

~~~java
package vn.example.errors;

import java.util.function.Function;

import org.springframework.stereotype.Component;

import vn.example.errors.OrderApplication.InvalidOrderException;
import vn.example.errors.OrderApplication.OrderCommand;
import vn.example.errors.OrderApplication.OrderResult;
import vn.example.errors.OrderApplication.RetryableProcessingException;

@Component
public class SynchronousOrderFacade {

    public record HttpOutcome(
            int status,
            OrderResult result,
            String errorCode,
            String message) {}

    private final Function<OrderCommand, OrderResult> function;

    public SynchronousOrderFacade(
            Function<OrderCommand, OrderResult> function) {
        this.function = function;
    }

    public HttpOutcome handle(OrderCommand command) {
        try {
            return new HttpOutcome(200, function.apply(command), null, null);
        } catch (InvalidOrderException exception) {
            return new HttpOutcome(
                    400, null, "INVALID_ORDER", exception.getMessage());
        } catch (RetryableProcessingException exception) {
            return new HttpOutcome(
                    503, null, "DEPENDENCY_UNAVAILABLE",
                    "Service temporarily unavailable");
        }
    }
}
~~~

In a real HTTP controller, the handler maps `HttpOutcome.status` into `ResponseEntity` or a provider response type. Never leak stack traces or technical exception internals outward.

### 16.6. Asynchronous Facade

Create `src/main/java/vn/example/errors/AsynchronousOrderFacade.java`:

~~~java
package vn.example.errors;

import java.util.function.Consumer;

import org.springframework.stereotype.Component;

import vn.example.errors.OrderApplication.OrderCommand;

@Component
public class AsynchronousOrderFacade {

    private final Consumer<OrderCommand> consumer;

    public AsynchronousOrderFacade(Consumer<OrderCommand> consumer) {
        this.consumer = consumer;
    }

    public void onMessage(OrderCommand command) {
        // Exceptions propagate back to the trigger/adapter.
        // The adapter maps them to failed invocations or nacks
        // per the provider's contract.
        consumer.accept(command);
    }
}
~~~

The facade never catches exceptions. When `consumeOrder` throws, the adapter detects invocation failure and triggers retry/ack policies. If a provider handler catches exceptions and returns normally, it can accidentally acknowledge the message.

### 16.7. Translating Infrastructure Errors into Retryable Errors

In production, a repository layer can translate transient DB failures into application exceptions:

~~~java
try {
    repository.save(result);
} catch (TransientDataAccessException exception) {
    throw new RetryableProcessingException(
            "Database temporarily unavailable",
            exception);
}
~~~

This additional snippet requires Spring JDBC/transaction dependencies if using `TransientDataAccessException`. Translate only recoverable errors into retryable exceptions; permanent constraint or schema errors belong in separate categories.

## 17. JUnit: Same Error, Two Representations

Create `src/test/java/vn/example/errors/ErrorBoundaryTest.java`:

~~~java
package vn.example.errors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import vn.example.errors.OrderApplication.InvalidOrderException;
import vn.example.errors.OrderApplication.OrderCommand;
import vn.example.errors.OrderApplication.OrderResult;
import vn.example.errors.OrderApplication.RetryableProcessingException;
import vn.example.errors.SynchronousOrderFacade.HttpOutcome;

@SpringBootTest
class ErrorBoundaryTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    SynchronousOrderFacade synchronousFacade;

    @Autowired
    AsynchronousOrderFacade asynchronousFacade;

    @Test
    void catalogFindsBusinessFunction() {
        Function<OrderCommand, OrderResult> function =
                catalog.lookup("normalizeOrder");
        assertNotNull(function);

        OrderResult result = function.apply(
                new OrderCommand("evt-42", "  od-123 "));
        assertEquals("OD-123", result.normalizedCode());
    }

    @Test
    void synchronousValidationErrorBecomes400() {
        HttpOutcome outcome = synchronousFacade.handle(
                new OrderCommand("evt-43", "bad-code"));
        assertEquals(400, outcome.status());
        assertEquals("INVALID_ORDER", outcome.errorCode());
    }

    @Test
    void asynchronousValidationErrorPropagates() {
        assertThrows(InvalidOrderException.class,
                () -> asynchronousFacade.onMessage(
                        new OrderCommand("evt-44", "bad-code")));
    }

    @Test
    void synchronousTransientErrorBecomes503() {
        Function<OrderCommand, OrderResult> failingFunction =
                command -> {
                    throw new RetryableProcessingException(
                            "Simulated downstream timeout");
                };

        var facade = new SynchronousOrderFacade(failingFunction);
        HttpOutcome outcome = facade.handle(
                new OrderCommand("evt-45", "OD-123"));

        assertEquals(503, outcome.status());
        assertEquals("DEPENDENCY_UNAVAILABLE", outcome.errorCode());
    }

    @Test
    void asynchronousTransientErrorPropagatesToAdapter() {
        Consumer<OrderCommand> failingConsumer =
                command -> {
                    throw new RetryableProcessingException(
                            "Simulated database unavailable");
                };

        var facade = new AsynchronousOrderFacade(failingConsumer);
        assertThrows(RetryableProcessingException.class,
                () -> facade.onMessage(
                        new OrderCommand("evt-46", "OD-123")));
    }

    @Test
    void consumerIsRegisteredInCatalog() {
        Consumer<OrderCommand> consumer =
                catalog.lookup("consumeOrder");
        assertNotNull(consumer);
        consumer.accept(new OrderCommand("evt-47", "OD-123"));
    }
}
~~~

Run inside the project directory:

~~~bash
mvn clean test
~~~

If the repository has Maven Wrapper, use `./mvnw clean test` or `./mvnw.cmd clean test` on Windows.

This test suite demonstrates catalog lookup, HTTP-like 400/503 mapping, exception propagation in the async facade, and consumer registration. **Tests do not prove AWS/Azure/GCP performed real retries.** To verify that, add provider adapters, triggers, retry config, DLQs, and integration tests on the target runtime.

## 18. Testing and Observing Errors in Production-Like Environments

### 18.1. Minimum Test Suite

| Layer | What to test |
| --- | --- |
| Unit tests | Validation, domain exceptions, permanent vs. transient classification. |
| `FunctionCatalog` tests | `Function`/`Consumer` lookup, conversion, composition. |
| HTTP contract tests | Status codes, error bodies, `Retry-After`, idempotency keys. |
| Event contract tests | Envelope parsing, event IDs, ack/failure responses, batch semantics. |
| Provider integration tests | Real triggers, retries, visibility/locks/checkpoints, DLQs. |
| Failure injection | DB timeouts, 429/503, connection resets, function timeouts. |
| Duplicate tests | Same event delivered twice or processed concurrently by two instances. |
| Redrive tests | DLQ replay after fixes while preserving idempotency. |

### 18.2. Metrics to Monitor

- Invocation counts, successes, errors, and timeouts.
- Error rates by function, trigger, and error category.
- Retry attempts, duplicate counts, and event age.
- Queue depth, oldest-message age, and dead-letter counts.
- Partial batch failures / per-record failures.
- HTTP 4xx/5xx/429 rates and client retry rates.
- Downstream dependency latency and availability.
- Idempotency conflicts and transaction rollbacks.
- Trace/correlation IDs linking producer → trigger → function → database.

### 18.3. Structured Logging

Example application log:

~~~json
{
  "eventId": "evt-42",
  "correlationId": "corr-7",
  "function": "consumeOrder",
  "trigger": "sqs",
  "attempt": 2,
  "errorCategory": "TRANSIENT_DEPENDENCY",
  "outcome": "RETRY"
}
~~~

Never log raw payloads, access tokens, `receiptHandle`s, or unnecessary personal data. Keep event IDs and correlation IDs for investigation without leaking data.

## 19. Common Mistakes When Designing Both Models

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Returning HTTP 200 after catching every exception | Caller believes processing succeeded. | Map errors to accurate status codes; return success only when failure was durably handled per contract. |
| Treating AWS async 202 as business success | Producer misses failed event executions. | Monitor destinations/DLQs or emit result events. |
| Applying one retry policy across all triggers | Wrong retry semantics; lost or multiplied events. | Configure per Lambda async/SQS, Azure extension, or Eventarc subscription. |
| Catching exceptions in a `Consumer` and only logging | Broker acks message; loses retries. | Rethrow retryable errors or quarantine durably before acking. |
| Retrying validation errors | Queue fills with poison messages and wastes resources. | Separate permanent vs. transient errors; use DLQ/quarantine. |
| Retrying without idempotency | Duplicate side effects. | Business keys, unique constraints, transactions/inbox/outbox. |
| Using request ID as idempotency key | Retries generate new IDs. | Use stable event or operation IDs. |
| Assuming timeouts mean uncommitted writes | Client retries and creates duplicate records. | Query state by idempotency key. |
| Enabling unbounded retries | Rising costs, backlogs, and retry storms. | Cap attempts/age; add backoff and DLQs. |
| Returning SQS batch responses for Pub/Sub | Violates adapter contract. | Match ack/response semantics of the real trigger. |
| Lumping parse errors with domain errors | Harder diagnostics, wrong status/retries. | Log and track metrics by boundary and error category. |
| Treating retry annotations as broker retries | Broker may still ack or retry unexpectedly. | Coordinate internal retries with trigger policies and integration tests. |

## 20. Scenario Exercises

### Exercise 1 — Distinguish Acceptance Responses from Processing Results

An AWS Lambda is invoked with `InvocationType=Event`. The API returns 202, and later the function throws an exception.

1. What does 202 signify?
2. Who retries the function error by default?
3. How can the producer learn that the event ultimately failed?
4. How do a DLQ and an on-failure destination differ in purpose?

**Hint:** 202 means invocation acceptance, not business outcome. Lambda's async queue applies its retry policy; failure destinations/DLQs capture failed events for investigation.

### Exercise 2 — Direct Invoke vs. API Gateway

A Lambda invoked directly with `RequestResponse` returns HTTP 200 from the Invoke API while carrying `X-Amz-Function-Error`. Another API Gateway route invokes the same function and returns 5xx to clients.

Explain why these two responses do not contradict each other. Name the fields to inspect on the Lambda Invoke API and in API Gateway response mapping.

### Exercise 3 — SQS Batch

A batch contains three records: `m-1`, `m-2`, and `m-3`. `m-2` hits a database timeout while the other two succeed.

1. Without partial batch responses enabled, what can happen?
2. With `ReportBatchItemFailures` enabled, which record must appear in the response?
3. If the handler catches `m-2`'s error and returns normally, what happens?
4. Why is idempotency still required for `m-1` and `m-3`?

### Exercise 4 — Azure Queue Storage vs. Service Bus

A team assumes "Azure retries 5 times" uniformly for both Queue Storage and Service Bus.

1. Why is that assumption wrong?
2. How does Queue Storage's poison queue work?
3. What do Service Bus `PeekLock` `Complete` and `Abandon` mean?
4. Which layer owns `MaxDeliveryCount` and the DLQ?

### Exercise 5 — Google Eventarc

A Cloud Run function receives Pub/Sub events. On DB timeouts, the handler throws an exception. Determine:

- Are retries enabled on the trigger/subscription?
- Which HTTP status codes count as success vs. negative ack along that delivery path?
- Where are retry windows, backoff, and DLQs configured?
- If an event redelivers while an earlier invocation is still running, how do you prevent duplicates?

### Exercise 6 — One Function, Two Facades

Using the project in sections 16–17:

1. Keep `normalizeOrder` stateless.
2. Have the sync facade return 400 on invalid codes.
3. Let the async facade propagate `InvalidOrderException`.
4. Add `RetryableProcessingException` and test 503 vs. propagated exceptions.
5. Explain why JUnit tests do not prove the broker actually retried.

### Exercise 7 — Side Effect Committed Before Ack Failed

A consumer commits a payment successfully, then the process crashes before sending ack.

1. What might the broker do next?
2. Why could a retry create a duplicate payment?
3. Design the idempotency key and unique constraint.
4. Where should transaction state be stored?
5. When should you use outbox/inbox vs. sending events to a DLQ?

## 21. Deployment Checklist

| Item | What to verify |
| --- | --- |
| Invocation mode | HTTP/request-response, Lambda async, SQS mapping, Service Bus, Eventarc, or Kafka binder? |
| Error contract | HTTP status/body, Lambda `FunctionError`, batch response, or broker settlement? |
| Retry owner | Client, provider async queue, event source mapping, extension, or subscription? |
| Retry budget | Attempts, backoff/jitter, event age, visibility/lock/deadline. |
| Error classification | Permanent, transient, uncertain outcome. |
| Idempotency | Business event/operation key, unique constraint, transaction. |
| Batch semantics | All-or-nothing vs. partial record failures? FIFO/partition ordering? |
| DLQ / failure destination | Payload, metadata, retention, access, and redrive procedure. |
| Observability | Error category, attempt count, event age, trace/correlation, queue depth. |
| Tests | Unit, catalog, contract, provider integration, duplicate, and redrive tests. |
| Security | Redact secrets/PII from logs; authenticate producers and authorize redrives. |

## 22. Summary and Official Documentation

**Synchronous errors belong to the response contract; asynchronous errors belong to the delivery and acknowledgement contract.** The same Java function can serve both worlds, yet error reporting and retries must follow each adapter and provider.

Remember:

- Synchronous: callers wait for responses; errors map to status/body or error payloads; callers/services decide on retries.
- Asynchronous: producers normally receive only acceptance confirmation; consumers must ack/complete or fail so triggers/brokers act.
- AWS `RequestResponse`, Lambda `Event`, and SQS event source mappings are three invocation modes with distinct semantics.
- Azure HTTP, Queue Storage, Service Bus, and Event Hubs do not share a single retry policy.
- Google HTTP and Eventarc/Pub/Sub have different retry owners and settings; check exact triggers and subscriptions.
- `FunctionCatalog` handles lookup, wrapping, and conversion—**never** retries or acks.
- Classify permanent, transient, and uncertain errors; use bounded backoff, DLQs, idempotency, and transactions/outboxes.
- Timeouts or lost responses do not prove side effects never committed; guard every mutating command against duplicates.

**Official documentation:**

1. Spring Cloud Function 5.1.0 — Programming Model, `FunctionCatalog`, and functional beans: https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html
2. Spring Cloud Function — AWS Lambda adapter: https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html
3. AWS Lambda — Synchronous and asynchronous invocation: https://docs.aws.amazon.com/lambda/latest/dg/lambda-invocation.html
4. AWS Lambda — Asynchronous invocation error handling and retries: https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html
5. AWS Lambda — Configure asynchronous invocation destinations/retry age: https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-configuring.html
6. AWS Lambda — SQS event source error handling and partial batch responses: https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html
7. AWS Lambda — SQS event source mapping and at-least-once behavior: https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html
8. Microsoft Azure Functions — Error handling and retries by trigger: https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-error-pages
9. Microsoft Azure Functions — Service Bus trigger, `PeekLock`, and dead-lettering: https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-service-bus-trigger
10. Microsoft Azure Functions — Queue Storage trigger and poison messages: https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-trigger
11. Google Cloud Run functions — Configure event-driven function retries: https://docs.cloud.google.com/run/docs/tips/function-retries
12. Google Cloud Run — Troubleshoot redelivery and acknowledgement behavior: https://docs.cloud.google.com/run/docs/troubleshooting
13. Spring Cloud Stream — Error handling and binder reference: https://docs.spring.io/spring-cloud-stream/reference/
14. Spring Cloud — Release train compatibility: https://spring.io/projects/spring-cloud/
