# RetryTemplate and Retry Policy in Spring Integration Adapters

> **Chapter:** Reliability  
> **Lesson:** RetryTemplate and retry policy  
> **Scope:** Connecting external systems to Spring Integration using inbound/outbound adapters, gateways, pollers, and MessageChannels. Practicing flows over **file, SFTP, HTTP, JMS, AMQP, Kafka, and databases**, while managing message contracts, errors, consistency, and connection lifecycles.

## 1. Learning objectives

After completing this lesson, learners can:

1. Explain what types of failures **retry** solves and distinguish transient errors from permanent errors.
2. Identify the components **RetryTemplate, RetryPolicy, BackOffPolicy, RetryContext, RetryCallback, and RecoveryCallback** in Spring Retry.
3. Configure bounded retries, exception classification, exponential backoff, and wait time limits.
4. Integrate **RequestHandlerRetryAdvice** at a Spring Integration request handler, understanding retry scope relative to pollers, gateways, and message channels.
5. Explain the difference between **in-process retry**, **broker redelivery**, and **datastore replay**, avoiding uncontrolled nested retry loops.
6. Design **idempotency, transactions, acknowledgement, error channels, dead-lettering, and recovery** suited to each adapter.
7. Analyze failure scenarios across **File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC** and pinpoint exact commit/ack points.
8. Write tests and metrics to measure **attempts, exhaustion, delay, duplicate effects, backlog, and recovery time**.

## 2. Context: Spring Integration and a failed exchange

An Integration Flow typically receives a message from an **inbound adapter** or **gateway**, passes it through a **MessageChannel**, processes it via a transformer/router/filter/service activator, and sends it to an **outbound adapter** or **outbound gateway**.

Example:

~~~text
File/SFTP inbound adapter
    -> inputChannel
    -> parse/validate
    -> enrichHeaders(eventId, correlationId)
    -> processChannel
    -> HTTP outbound gateway
    -> partner-resultChannel
~~~

Any step can fail, yet **not every error should be retried**:

- Poller cannot read a file because it is still being written: it can **wait** for the next poll rather than necessarily retrying everything.
- Temporary SFTP disconnect: may recover after backoff.
- JSON payload missing a required field: resending the same data will usually keep failing.
- HTTP 503/429: may be transient; respect target capacity and safety policies.
- HTTP 401/403: usually requires fixing credentials or permissions, not repeating requests unconditionally.
- JDBC deadlock/serialization conflict: can retry the **transaction** if designed properly.
- JMS/Kafka consumer failure: must coordinate **acknowledgement/offset commit** and broker redelivery mechanisms.
- HTTP POST already processed by the partner but the response was lost: retrying may **create duplicate business operations**.

**Retry does not guarantee success.** It simply gives a recoverable failure another chance to succeed; misconfigured retry can generate heavy load, duplicate side effects, or trap messages in an unprocessable state.

## 3. Reliability goal: the right task and the right number of effects

Separate three questions:

1. **Can the operation be retried?** Consider the exception, operation, recoverability, data source, and time limits.
2. **Is retrying safe?** Consider idempotency, transactions, and the possibility that the partner already received the request before timing out.
3. **What if attempts are exhausted?** Consider recovery, dead-lettering, persisting evidence, alerting, controlled replay, and ack/rollback.

### Three delivery terms

| Term | Common meaning | Caution |
|---|---|---|
| **At-most-once** | Does not resend when processing may have happened; tasks may be lost | Not inherently suitable for financial data requiring complete processing |
| **At-least-once** | May retry or redeliver to avoid dropping tasks | Must handle duplicate processing |
| **Exactly-once effect** | Business effect is not duplicated within the designed scope | Usually requires idempotency/transactions/dedup; cannot be inferred just from enabling retry |

A message may be delivered multiple times yet produce **a single business effect** if there is an idempotency key and consistent result storage.

**No RetryPolicy choice alone turns a distributed system into end-to-end exactly-once.**

## 4. Foundational components of Spring Retry

Spring Retry provides concepts applicable inside Java/Spring applications, while Spring Integration helps attach them to message-handling points.

| Component | Responsibility | Remember |
|---|---|---|
| **RetryTemplate** | Coordinates multiple attempts and finishes with success or exhaustion | In-process mechanism, not a durable retry store |
| **RetryCallback** | The unit of work executed on each attempt | Scope carefully to avoid re-running unrelated side effects |
| **RetryPolicy** | Decides whether another retry is allowed and when to stop | Based on attempt count, exception, timeout, or composite policies |
| **BackOffPolicy** | Defines the pause interval between attempts | Prevents hammering a failing system continuously |
| **RetryContext** | State of a retry sequence, attempts made, last exception, and metadata | Do not confuse with message headers or durable persisted state |
| **RecoveryCallback** | Action after retries can no longer continue | Can record failure, route to dead-letter, return fallback, or throw |
| **RetryListener** | Observes attempt start, errors, and completion | Suitable for metrics/tracing with protected data |
| **RequestHandlerRetryAdvice** | Wraps a Spring Integration request handler with retry | Scope depends on the endpoint/advice chain it is attached to |

In a Spring Integration Flow, adapters and gateways connect to external systems; **`RetryTemplate` does not automatically know how a broker acks messages, saves SFTP checkpoints, or commits Kafka offsets**. Those responsibilities belong to separate adapter/container/transaction/recovery design.

### Lifecycle diagram of a RetryTemplate

~~~mermaid
flowchart TD
    A["Message arrives at handler with retry"] --> B["Open RetryContext"]
    B --> C{"RetryPolicy still allows?"}
    C -->|"Yes"| D["Invoke RetryCallback / handler"]
    D -->|"Success"| S["Return result, finish"]
    D -->|"Exception"| E["Classify exception and update context"]
    E --> C
    C -->|"No"| F{"RecoveryCallback present?"}
    F -->|"Yes"| G["Recovery: DLQ, error flow, fallback, or rethrow"]
    F -->|"No"| H["Exception surfaces to caller/container"]
    G --> I["Close retry context"]
    H --> I
    S --> I
    E -.-> J["BackOffPolicy before next attempt"]
    J -.-> C
~~~

*This is a logical model*: retry policy and backoff operate under Spring Retry's contract; a non-retryable exception can go straight to recovery/exhaustion. Do not infer from the diagram that every recovery succeeds or that the broker automatically acknowledges the message.

## 5. RetryPolicy: which invocations count as attempts?

**SimpleRetryPolicy** is commonly used to limit attempts. Setting **maxAttempts = 4** means:

- **Attempt 1:** initial invocation;
- **Retry 1:** second invocation;
- **Retry 2:** third invocation;
- **Retry 3:** fourth invocation.

Thus there are **4 attempts total**, of which at most **3 are retries**.

### Example of calculating total latency

Suppose each HTTP call has a maximum timeout of 2 seconds and backoff is 300 ms, 600 ms, 1,200 ms between the four attempts.

**Approximate worst-case duration = 4 × 2,000 ms + (300 + 600 + 1,200) ms = 10,100 ms**, excluding scheduling, serialization, queueing, TLS handshake, and other overhead.

From this:

- If the API caller only has a 5-second deadline, this configuration is unsuitable.
- If a worker uses a fixed thread, consecutive retries can hold the thread for over 10 seconds.
- If 500 messages fail together on the same schedule, synchronized backoff can trigger a **retry storm**.

**Per-attempt timeout is not the total timeout of the retry sequence.** You must manage deadlines and time budgets across multiple layers.

### Distinguishing policy types

| Policy / classification approach | When useful | Notes |
|---|---|---|
| **SimpleRetryPolicy** | Caps attempts, basic exception classification | Does not know business safety of the operation |
| **TimeoutRetryPolicy** | Caps retry time window per policy | Must be paired with actual external call timeouts |
| **ExceptionClassifierRetryPolicy** | Different exception groups need different retry strategies | Classifier must understand Spring Integration wrapper exceptions |
| **CompositeRetryPolicy** | Combines conditions such as attempt count and deadline | AND/OR semantics must be verified in configuration |
| **CircuitBreakerRetryPolicy** or standalone circuit breaker | Limits repeated failures per strategy | Do not confuse with a distributed circuit breaker with its own state/metrics |
| **NeverRetryPolicy** | Errors that should not be retried | Routes immediately to recovery or returns error |
| **AlwaysRetryPolicy** | Used in tightly controlled cases | Easily creates infinite loops; avoid blind use with external systems |

The list above describes **library concepts/APIs**; exact capabilities and builders may differ across Spring Retry versions. In real systems, always explicitly declare **max attempts and deadline/total limits**.

## 6. Classifying exceptions: transient vs. permanent errors

Not every exception means the request should be run again. Classify by **cause and operation safety**.

| Error group | Examples | Usually reasonable strategy |
|---|---|---|
| **Transient network** | Socket timeout, connection reset, brief DNS/service discovery disruption | Bounded retry, backoff; note request may have reached target |
| **Rate limit / overload** | HTTP 429, overloaded broker/target component | Backoff, jitter, honor `Retry-After` if present |
| **Temporary unavailability** | HTTP 503, brief service maintenance | Budgeted retry; circuit breaker when errors spread |
| **Transient concurrency** | Deadlock, optimistic lock conflict, serialization error | Retry properly scoped unit of transaction |
| **Invalid input** | Schema-invalid JSON, missing required field, business rule failure | Do not retry unconditionally; route invalid message to dedicated handling |
| **Authentication/authorization** | HTTP 401/403, wrong JMS/Kafka permissions, revoked key | Stop and fix credentials/policy; do not repeat futile requests |
| **Not found** | HTTP 404 | Depends on API contract; typically do not retry unless known eventual consistency |
| **Business conflict** | HTTP 409 | Must understand whether conflict is auto-resolvable; do not treat all as transient |
| **Permanent filesystem** | Permission denied, wrong path, misconfigured quota | Fix system/permissions first; avoid looping |
| **Unknown send outcome** | Response timeout after POST | Must use idempotency key/status query before resending |

### Retry decisions should rest on two dimensions

**Retryability = recoverability of error type × safety of repeating the operation.**

For example, HTTP 503 may be transient, yet a POST creating an order **without an idempotency key** still risks creating duplicate orders if the first attempt was recorded before 503 was returned.

One decision approach:

1. If payload is invalid or lacks permission → **do not retry**, route to intentional handling.
2. If error is transient and operation is idempotent → **bounded retry**.
3. If execution status is unknown but operation has an idempotency key → retry per the target's idempotency contract.
4. If status is unknown and operation is non-idempotent → **query status/reconcile**, do not blindly resend.
5. If retries are exhausted → recovery/parking/DLQ and alert; do not erase error evidence.

### Watch out for exception wrappers

In Spring Integration, a handler may wrap an external system error in **`MessagingException`/`MessageHandlingException`** or another exception. If `RetryPolicy` only checks exact classes without inspecting the cause chain, a real `IOException` may be misclassified.

**Do not retry all `MessagingException` instances.** Inspect the root cause and action type: the same wrapper can contain a transient `IOException` or a permanent `ValidationException`.

## 7. BackOffPolicy: reducing load and avoiding retry storms

Backoff determines **how long to wait between two attempts**.

| Backoff type | Description | Suitable cases |
|---|---|---|
| No backoff | Resends almost immediately | Only for very brief, cheap, controlled errors |
| **FixedBackOffPolicy** | Fixed wait interval, e.g., 500 ms | Short scenarios, few clients |
| **ExponentialBackOffPolicy** | Wait interval grows by a multiplier up to `maxInterval` | Overloaded target service or brief network glitches |
| **ExponentialRandomBackOffPolicy** / jitter | Wait interval includes randomness | Multiple clients retrying concurrently, reducing herd effect |
| Retry-After-aware | Adjusts to target's hint | HTTP 429/503 with valid `Retry-After`; requires explicit integration logic |

### Exponential backoff example

- `initialInterval` = 300 ms;
- `multiplier` = 2;
- `maxInterval` = 2,000 ms;
- `maxAttempts` = 4.

Intervals between attempts are roughly **300, 600, 1,200 ms** without jitter. With more attempts, wait intervals will not exceed the 2,000 ms ceiling per policy.

**Standard `ExponentialBackOffPolicy` does not add jitter automatically.** To reduce synchronized client spikes, choose a randomized policy or design an appropriate randomized pause.

### Retry budget

Beyond `maxAttempts`, define:

- **Per-attempt timeout** for network calls;
- **Total deadline** for the request or job;
- **Concurrency limit** on in-flight retrying requests;
- **Rate limit** toward the partner;
- **Retry budget** as a ratio relative to original requests;
- **Stop rules** when a circuit breaker opens or the client cancels the request.

For instance, if a user waits on an HTTP gateway for 3 seconds, do not configure the adapter to retry for tens of seconds before responding unless the UX contract allows it.

## 8. Configuring RetryTemplate in Java

The following example demonstrates **explicit exception classification** and bounded backoff. It is suitable for learning Spring Retry's API structure; verify against your project's dependency versions when implementing.

~~~java
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;

@Configuration
class PartnerRetryConfiguration {

    @Bean
    RetryTemplate partnerRetryTemplate() {
        Map<Class<? extends Throwable>, Boolean> retryable = new HashMap<>();

        // Example: only potentially transient errors.
        retryable.put(IOException.class, true);
        retryable.put(HttpClientErrorException.TooManyRequests.class, true);
        retryable.put(HttpServerErrorException.ServiceUnavailable.class, true);

        // 4 attempts total, traverse cause chain, default for other classes = false.
        SimpleRetryPolicy retryPolicy =
                new SimpleRetryPolicy(4, retryable, true, false);

        ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
        backOff.setInitialInterval(300L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(2_000L);

        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(retryPolicy);
        template.setBackOffPolicy(backOff);
        return template;
    }
}
~~~

**Key points to understand:**

- **4** is total attempts, not four retries after the first call.
- By using an explicit exception map with default **false**, the example avoids retrying `IllegalArgumentException` or permission errors.
- Enabling `traverseCauses` helps detect underlying causes inside wrappers when supported by the policy.
- Retrying `IOException` does not guarantee safety for HTTP POST; idempotency must be enforced at the business layer.
- The example does not yet include jitter, a total deadline, a retry budget, or specific handling for **502/504** responses. Add those if required by your application.
- `HttpClientErrorException.TooManyRequests` and `HttpServerErrorException.ServiceUnavailable` are Spring Web types; retrying by status/exception still depends on how your HTTP client and gateway translate errors.

### Using RetryTemplate directly

~~~java
RetryTemplate template = partnerRetryTemplate();

String response = template.execute(context -> {
    // This operation may execute multiple times.
    // Only do this when idempotency is confirmed.
    return partnerClient.getStatus();
});
~~~

The callback parameter can expose **`retryCount`** and error details of the retry sequence, but never use `retryCount` as a business event ID: it changes per attempt and is not stable across broker redeliveries.

### When to use execute directly?

Use it when you want to control a **block of operations** outside a handler or inside a service. However, if a Spring Integration endpoint already has retry advice, calling `RetryTemplate` again inside the service can create **nested retries**. Designate one retry owner per boundary and document total attempts.

## 9. Attaching RetryTemplate to Spring Integration with RequestHandlerRetryAdvice

Spring Integration supports **advice** on request handler endpoints. **`RequestHandlerRetryAdvice`** allows a failed handler invocation to be retried according to a `RetryTemplate`.

### Advice configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Configuration
class IntegrationRetryAdviceConfiguration {

    @Bean
    RequestHandlerRetryAdvice partnerRetryAdvice(
            RetryTemplate partnerRetryTemplate) {

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(partnerRetryTemplate);

        // Retries exhausted: continue throwing so upstream flow
        // or error-handling policy resolves it.
        advice.setRecoveryCallback(context -> {
            throw new IllegalStateException(
                    "Partner request exhausted retry policy",
                    context.getLastThrowable()
            );
        });

        return advice;
    }
}
~~~

**Note:** The code above intentionally **rethrows** on exhaustion. If `RecoveryCallback` returns a normal value instead of throwing, the calling layer may treat the handler as having succeeded per endpoint semantics, so you must explicitly design the outcome and ack/broker recovery.

### Integration Flow with an HTTP outbound gateway

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.integration.http.dsl.Http;

@Configuration
class PartnerHttpFlowConfiguration {

    @Bean
    IntegrationFlow partnerPingFlow(RequestHandlerRetryAdvice partnerRetryAdvice) {
        return IntegrationFlow.from("partnerPingRequests")
                .handle(
                        Http.outboundGateway(
                                "https://partner.example.invalid/health"
                        )
                        .httpMethod(HttpMethod.GET)
                        .expectedResponseType(String.class),
                        endpoint -> endpoint.advice(partnerRetryAdvice)
                )
                .channel("partnerPingResponses")
                .get();
    }
}
~~~

The example uses **GET** to focus on retry wiring, not to illustrate a POST operation with side effects. The `example.invalid` domain is purely illustrative; replace it with the real endpoint, timeouts, HTTP message converters, and error policies when integrating.

**Retried scope:** Advice placed on this outbound handler wraps **invocations of that handler**, and does not automatically retry an upstream transformer or steps after `partnerPingResponses`. If an entire workflow needs retrying, choose a dedicated transaction/unit-of-work boundary rather than pulling the whole flow into one callback by default.

### Do not apply advice indiscriminately

- Handlers performing **non-idempotent** writes: deduplication must come before retry.
- Handlers sending emails or webhooks: may already have sent even if the caller timed out.
- Handlers with multiple side effects: retrying the whole handler can repeat the first side effect.
- Handlers inside a broker container with redelivery: sum the total retry budget across layers.
- Handlers inside a transaction: clarify how transaction rollback/reopen works between attempts.

## 10. How do retry advice, pollers, gateways, and MessageChannels differ?

A common source of confusion is **where to place retry**.

| Location | Unit of work retried | Risk |
|---|---|---|
| **Inside a service** using `RetryTemplate.execute` | Code block of the callback | If side effects precede the error, the callback re-runs them |
| **RequestHandlerRetryAdvice** at endpoint | Invocation of the wrapped handler | Does not automatically retry upstream source or downstream handlers |
| **Poller advice** | Part of polling activity per advice/poller order | May retry polling, not necessarily the same already-fetched message |
| **Error flow / scheduled replay** | Persisted/failed message replayed later | Requires storage, idempotency, redrive caps |
| **JMS/AMQP broker redelivery** | Message delivery after rollback/nack/reject per policy | Delivery count and DLQ depend on container/broker |
| **Kafka consumer retry/redelivery** | Record/batch via container/error handler/seek/retry topics | Offset commit, partition ordering, and concurrency are critical |
| **HTTP caller retry** | Entire HTTP request resent by client | Can compound with server or gateway retry, multiplying calls |

### DirectChannel and ExecutorChannel

**`DirectChannel`** typically invokes subscriber handlers synchronously on the sender's thread; exceptions can propagate back to the caller. If a handler holds the thread during backoff, the inbound source/gateway may be delayed.

**`ExecutorChannel`** introduces an asynchronous boundary: exceptions generally no longer surface directly on the sender's thread in the same way; you must design error channels, rejection handling, and acknowledgement. **`MessageChannel` does not automatically create durable retry.**

With **`QueueChannel`** or a message store, messages can be persisted and read again under their own mechanics, though you must still define transactions, duplicate detection, and consumption rules.

### A poller is a fetch schedule, not broker retry

A poller may invoke an adapter on a schedule, e.g., every 2 seconds. If the source has no files yet, "no message" is normally not an exception to retry. If the poller hits a connection error, the next poll can try again; if a message was already fetched and downstream fails, examine **acknowledgement and metadata/filters** to know whether that exact message will be read again.

Do not assume "the poller runs again = failed messages are safely redelivered."

## 11. Error channel and RecoveryCallback: where do exhausted retries go?

When `RetryPolicy` permits no more attempts, the system needs an intentional **terminal outcome**:

- Route the message to an **error channel** with error metadata for handling/monitoring.
- Write to a **dead-letter queue/topic** or durable parking store.
- Move to a **manual review** queue when the failure is data/business-related.
- Schedule a bounded **delayed replay** if the outage lasts longer than in-process retry scope.
- Return a fallback **only when the business contract permits**.
- Propagate the error back to the consumer/gateway so the external layer decides on rollback, nack, or an error response.

### Critical warning about recovery

**A `RecoveryCallback` that returns normally can cause the retry invocation to be treated as handled.** If the caller/container relies on an exception to withhold ack, swallowing the exception can cause **unintended message loss**.

Example of a flawed policy:

~~~text
onRetryExhausted:
    log.error("Delivery failed")
    return null

Broker/container:
    handler returned normally -> may acknowledge/commit
Result:
    message is gone from source, with no guaranteed recovery copy
~~~

The right approach must clearly establish:

1. Were the message and error written to a **durable failure store**?
2. Was writing to the DLQ/parking confirmed successful?
3. Who is responsible for source ack/commit?
4. If writing to the DLQ fails, does the exception propagate so the source **redelivers**?
5. Are there limits on **redrive** attempts and a path for poison messages?

In Spring Integration, **`ErrorMessage`** can carry the exception and original failed message depending on context. When using recovery to send to an error channel, understand the semantics of the chosen component and **test end-to-end** before equating sending to an error channel with "safely persisted."

### Sample failure record

~~~json
{
  "eventId": "order-sync-20261123-0412",
  "correlationId": "corr-77f3",
  "source": "sftp-inbound",
  "destination": "partner-http",
  "operation": "order.upsert",
  "attempts": 4,
  "terminalReason": "RETRY_EXHAUSTED",
  "errorCategory": "TRANSIENT_REMOTE_UNAVAILABLE",
  "lastErrorType": "ServiceUnavailable",
  "payloadReference": "secure-message-store/item-0412",
  "occurredAt": "2026-11-23T08:20:00Z",
  "replayState": "PARKED"
}
~~~

This example is a business schema, not a default Spring Integration format. **Do not log passwords, SFTP private keys, bearer tokens, full customer payloads, or SFTP credentials in failure logs.** `payloadReference` should point to a managed store with appropriate access controls and retention.

## 12. Idempotency: the foundation so retry does not create duplicate data

**Idempotent** means invoking the same operation with the same semantic intent does not cause unintended additional side effects in the business outcome.

### Scenarios requiring vigilance

| Operation | Retry risk | Mitigation |
|---|---|---|
| GET to check status | Usually makes no changes | Still bound retries to avoid overload |
| PUT updating a resource with deterministic content | Usually easier to design idempotently | Check versioning/concurrency, hidden side effects |
| POST creating an order/payment | May create two records | **Idempotency key** and persisted result state |
| Sending email | May send duplicates | Outbox/dedup and provider contract if available |
| Writing a database row | May insert duplicates | Unique constraint on business event ID; appropriate UPSERT |
| Consuming Kafka/JMS | Broker may redeliver | Inbox/dedup by event ID, timely commit/ack |
| Copying/moving SFTP files | May copy twice or leave partial writes | Temp file, atomic rename when suitable, checksum/manifest, process state |
| Triggering a batch job | May launch multiple jobs | Idempotent job launch with stable job key |

### Stable idempotency key

Generate or receive a **stable business event ID** from upstream—such as `order-8291/version-3`—rather than relying on `MessageHeaders.ID`, which is regenerated as messages traverse flows or across broker redeliveries.

~~~text
Business event:
    eventId = order-8291-v3
    operation = partner.order.upsert
    target = partner-X

Attempt 1:
    Idempotency-Key = order-8291-v3
    response timeout; outcome unknown

Attempt 2:
    Idempotency-Key = order-8291-v3
    partner returns previously processed result

Local result:
    One valid order, no second order created
~~~

This mechanism is only safe if **the partner genuinely supports and retains the idempotency key**, including scope, key TTL, and handling of requests with the same key but different payloads.

### Inbox/outbox and unique keys

**Inbox/dedupe** records processed business events on the receiving side, typically within the same transaction as business data if sharing a database.

**Transactional outbox** records business state and events to publish in a single database transaction; a worker publishes events later and may send duplicates, so consumers still need to be idempotent.

Constraint example:

~~~sql
-- Illustrative table: an eventId can only be applied once per consumer scope.
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

A unique key alone is insufficient if an external side effect already occurred and cannot participate in the same transaction as this table. In that case, you need an **external idempotency contract**, saga/compensation state, or an outcome reconciliation process.

## 13. Transactions and acknowledgement: retry cannot be separated from commit

Picture a message delivered to the application by a broker. After the handler processes it, the consumer may have to **ack** or **commit offset**. If the handler retries and fails, what happens next depends on the adapter/container's transaction/ack mechanism.

### Three distinct boundaries

1. **Retry attempt:** a single handler/service call tried multiple times.
2. **Transaction:** a unit of data changes committed or rolled back.
3. **Source acknowledgement/checkpoint:** the source believing a message/record has finished processing.

These three boundaries do not always align. Specifically:

- In-process retry can happen **inside** an already-started transaction.
- A broker can **redeliver** the entire message after rollback.
- Kafka can **replay the record** if the offset was not committed.
- File/SFTP may or may not re-pick a file depending on filters/metadata.

### Common pitfall: transaction already marked rollback-only

Suppose a JDBC operation causes a deadlock that marks the transaction `rollback-only`. If `RetryTemplate` sits **inside the same transaction**, the next attempt may run against a context that can no longer commit. Some cases require **a fresh transaction per attempt**.

**Design rule:** define the retry boundary relative to transaction advice/transaction templates; test with real deadlocks/commit failures. Never assume retrying a statement recovers the whole transaction.

### Decision table

| Source type | When handler succeeds | When handler is exhausted |
|---|---|---|
| HTTP inbound gateway | Return response per contract | Return appropriate error; client may retry |
| File/SFTP inbound poller | Update processing/file state per flow | Needs re-poll/parking policy; no default broker ack |
| JMS listener | Commit/ack per container/transaction | Rollback/redelivery or DLQ per design |
| AMQP listener | Ack or transaction commit | Nack/reject/requeue/DLX/DLQ depending on container/broker |
| Kafka consumer | Commit offset per container/ack mode | Seek/redelivery/retry topic/DLT per configuration |
| JDBC polling | Update row status/transaction per design | Row may be re-selected; needs lease/retry/dead states |

**Do not infer from an adapter's name that ack mechanics are identical.** Inspect adapter/container configuration and test failure cases.

## 14. File inbound/outbound: retry must know file state

Spring Integration File adapters clearly show the difference between **retrying I/O operations** and **retrying message processing**.

### Inbound file

A poller fetches files from a directory. Scenarios:

- File is still being written: the application reads a partial file and fails parsing.
- File has invalid content: retrying parsing will not fix it.
- File was selected once by an accept-once filter: a handler failure does not guarantee the next poll sees the file again.
- Metadata store is in-memory only: a restart may re-ingest the file and create duplicates.
- File was moved/archived before downstream succeeded: retry struggles to find the source.

### A safer workflow

1. Source writes the file under a temporary name, e.g., `order-8291.part`.
2. After writing and verifying completion, the source **renames** it to `order-8291.ready` on the same filesystem when atomic rename is supported.
3. The inbound adapter only picks up ready files.
4. Generate a stable `eventId` from the filename/manifest or signed content per contract.
5. Parse/validate; route invalid files to quarantine with a reason.
6. Execute idempotent business processing; only archive/delete after confirmed success.
7. On temporary downstream failure, retry with limits; if exhausted, record `PARKED` state with a replay path.

**Not all filesystems support atomic rename in the same way.** If the source is object storage or an external system, use a manifest/ready flag or corresponding publishing contract.

### Outbound file

Writing files also suffers from partial output issues. If a previous attempt wrote a partial file and then retried, it could:

- Overwrite data inconsistently;
- Create multiple files;
- Cause recipients to read an incomplete file.

Solution: write to a temporary path, sync/close the file, then publish via rename/manifest as supported by the destination, with clear overwrite policies and checksums. For adapter-based outbound files, control filename selection and handle collisions by `eventId`.

## 15. SFTP: reconnect is not safe replay

SFTP inbound/outbound commonly faces **network drops, timeouts, stale sessions, permission denied, or partial transfers**.

### Error classification

| Incident | Retry? | Reason |
|---|---|---|
| Temporary connection drop/timeout | Possibly, bounded with backoff | Network may recover |
| SFTP server overloaded | Possibly, with delay/jitter | Avoid retry storms |
| Invalid private key or host key validation | Do not retry endlessly | Fix auth/trust; never weaken host key checks |
| Permission denied on target directory | Usually no | Fix target permissions/state |
| Source file missing | Depends on contract | Source may not have published yet, or filename is wrong |
| Upload completed but ACK lost | Outcome unknown | Inspect target file/checksum/manifest before resending |
| File picked up mid-write | Do not retry parse endlessly | Enforce file ready/rename rules |

### Inbound file synchronization from SFTP

Typically pay attention to:

- Mechanism to detect **completed uploads**;
- Remote/local filters and accept-once state;
- Whether the metadata store survives restarts;
- Behavior of temporary download, local rename, and remote deletion;
- Policy for parsing or downstream failures;
- Replaying files by `eventId` and checksum, not solely by timestamp.

**Retry advice on a downstream HTTP handler does not automatically make the SFTP inbound adapter re-download a file.** Once a file is marked received, you need an independent parking/replay strategy.

### Outbound SFTP

If an outbound upload succeeds but the response is lost, retrying with the same filename may overwrite or create a new version. Design a deterministic target filename from `eventId`, upload to a temp name then publish, reconcile size/hash/manifest, and define clear overwrite rules. Do not assume every remote SFTP server supports atomic cross-filesystem renames.

## 16. HTTP outbound gateway: selecting errors and idempotency contracts

An **HTTP outbound gateway** sends a request and waits for a response, typically fitting request–reply patterns. Handler retry **resends the HTTP request**, so safety depends on the HTTP method and the partner's contract.

### Suggested decision table

| Status/exception | Retryable? | Conditions |
|---|---|---|
| Connect/read timeout | Possibly | Within timeout/budget; request outcome may be unknown |
| 429 Too Many Requests | Usually yes, not immediately | Honor `Retry-After`/rate limit; require idempotency if side effects exist |
| 503 Service Unavailable | Possibly | Backoff/jitter and bounded attempts |
| 502/504 | Possibly in some cases | Weigh unknown outcome and repeated side-effect risk |
| 400 Bad Request | Usually no | Fix payload/schema |
| 401 Unauthorized | Usually do not retry with same credentials | Refresh/rotate credentials via dedicated flow if permitted |
| 403 Forbidden | Usually do not retry | Verify permissions/policy |
| 404 Not Found | Depends on contract | Eventual consistency may allow bounded retries |
| 409 Conflict | Depends on business logic | May mean already-processed or unresolvable conflict |
| 500 Internal Server Error | Do not retry all by default | Some servers already committed side effects before erroring |

### Never erase traces of unknown outcomes

~~~text
Client                     Partner
  | -- POST /payments ------> |
  |                           | records payment successfully
  | <--- response lost ------ |
  |                           |
  | -- POST again ----------> |
  |                           | risk of second payment
~~~

Without an idempotency contract, a timeout **does not prove the request was not processed**. Possible solutions:

- Send the same stable **`Idempotency-Key`** across every attempt.
- Call a status lookup API by `transactionId` before retrying.
- Use an upsert contract keyed by business key/version.
- Use outbox and post-timeout reconciliation.
- Escalate manually when outcomes cannot be verified.

### Distinguishing inbound and outbound gateways

- **HTTP inbound gateway:** a client calls into the application; if the server returns 5xx/timeout, **the client** may retry. Inbound idempotency is required.
- **HTTP outbound gateway:** the application calls the partner; `RetryAdvice` may resend the HTTP request.
- When inbound triggers outbound, if both client and service retry **4 attempts**, the partner may receive up to **4 × 4 = 16 calls** for one business event if all fail and no other limits exist.

Therefore, you need an **end-to-end retry budget**. Do not configure independent retries at every layer simply because every layer supports `RetryTemplate`.

## 17. JMS and AMQP: coordinating retry with broker redelivery

JMS/AMQP support **delivery, acknowledge/commit, rollback, or dead-letter** mechanisms, with details governed by the broker and container. Spring Integration provides the relevant inbound/outbound adapters/gateways; in-process retry is only one layer.

### Three common models

1. **Short in-process retry:** handler retries a few times quickly on transient errors with short backoff.
2. **Broker redelivery:** after exhaustion, trigger rollback/nack/requeue so the broker redelivers per configuration.
3. **Dead-letter / delayed replay:** beyond a failure threshold, move to DLQ/parking for inspection or controlled replay.

If **both retry advice and broker redelivery** repeat 5 times, total handler invocations can reach **25**, excluding other layers. Actual counts depend on container, requeue, and recovery behavior.

### JMS

For JMS listeners/gateways:

- Determine **transacted session** or acknowledgement mode.
- When the handler fails and the exception propagates, the container can roll back/redeliver per configuration.
- If `RecoveryCallback` swallows the error and returns normally, the container may consider the message processed.
- A message can be redelivered after a crash even if the handler already caused external side effects; idempotency is required.
- Poison messages need redelivery caps and a DLQ so they do not block the consumer forever.

### AMQP/RabbitMQ

For AMQP:

- Manual/auto ack, reject/nack, requeue, dead-letter exchange, and prefetch affect recovery.
- **Immediate continuous requeue without backoff** can create a hot loop and burn CPU/broker resources.
- If delayed retry is needed, use a **retry queue with TTL, a delayed exchange if supported, or an explicitly configured listener/framework retry mechanism**.
- Cap redelivery counts via reliable mechanisms/metadata; do not rely solely on a header from an untrusted source.

### Reference safe flow

~~~mermaid
flowchart TD
    B["Broker delivers message"] --> H["Consumer / Integration handler"]
    H --> P{"Processed successfully?"}
    P -->|"Yes"| A["Commit / ack per container"]
    P -->|"No"| R{"In-process retry budget left?"}
    R -->|"Yes"| W["Backoff then retry handler"]
    W --> P
    R -->|"No"| D{"Recovery guaranteed?"}
    D -->|"Has durable store"| Q["DLQ / parking / delayed retry"]
    Q --> K["Ack source after persisting message per design"]
    D -->|"Not yet persisted"| E["Propagate error, rollback/nack per policy"]
    E --> B
~~~

The diagram illustrates **business responsibilities**. Do not assume writing to a DLQ and acking the source are atomic if using **two independent systems** without a corresponding transaction/guarantee contract.

## 18. Kafka: offset commits, retry, and partition ordering

Kafka highlights the difference between **handler retry** and **record replay**. If a consumer receives a record, fails processing, and has not committed the offset, that record may be processed again. If the offset is committed before side effects finish, messages can be lost.

### Decisions to make

- Does the consumer process **records or batches**?
- Who manages **offset ack/commit**?
- Are errors handled via listener container/Spring Kafka mechanisms, `RequestHandlerRetryAdvice`, or retry topics?
- Does a failing record **block the partition**?
- If moved to a retry topic, is ordering among records sharing a key still preserved as before?
- When retries are exhausted, how does the record reach the DLT and who approves replay?
- Does reprocessing a record create duplicate database/outbound API effects?

### Key point

**A `RetryTemplate` on a service activator does not perform Kafka seeks, commit offsets, or configure retry topics/DLTs.** Those responsibilities belong to the Kafka consumer/listener container, Spring Kafka configuration, and flow design.

One possible strategy:

~~~text
Kafka record
  -> consumer/adapter
  -> validate
  -> business handler with short retry for transient dependencies
  -> success: commit per container configuration
  -> exhausted: propagate to error handling
  -> container retry / DLT per policy
  -> DLT monitored with manual/scheduled redrive
~~~

Even if an application uses **Kafka transactions** or exactly-once semantics within Kafka's scope, never assume an external HTTP partner or out-of-transaction database gets exactly-once side effects. You still need an idempotent consumer/outbox or dedicated coordination protocol.

### Ordering and throughput

A poison record on a partition can degrade throughput if the consumer repeatedly retries it. Routing the record to a retry topic or DLT unblocks the main path, but **can break business ordering** if a later record is processed ahead of the retrying record. Decide ordering requirements per aggregate/key; do not choose a retry topology based on latency alone.

## 19. Database/JDBC polling: transactions and re-selecting records

Spring Integration provides adapters for polling data or writing to databases. Retries here typically involve:

- DB connection timeouts;
- Deadlocks or serialization conflicts;
- Potentially transient lock timeouts;
- Unique constraint violations;
- Incompatible schema migrations;
- Downstream failures after a row was marked processed.

### State-based polling pattern

~~~text
NEW -> CLAIMED -> PROCESSING -> DONE
                  |
                  v
               RETRY_WAIT -> PROCESSING
                  |
                  v
                 PARKED
~~~

Each row needs a **stable ID**, attempt count, owner/lease, status, `nextAttemptAt`, and failure reason. If a worker crashes in `PROCESSING`, you need controlled lease expiry/re-claiming; otherwise rows remain stuck forever.

### Logical schema example

~~~sql
CREATE TABLE integration_jobs (
    id BIGINT PRIMARY KEY,
    business_event_id VARCHAR(120) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL,
    attempt_count INT NOT NULL,
    next_attempt_at TIMESTAMP,
    lease_owner VARCHAR(100),
    lease_until TIMESTAMP,
    last_error_category VARCHAR(64)
);
~~~

**This example is not production-ready for concurrency.** It requires transactions, atomic claims, indexes, optimistic locking/`SKIP LOCKED` where appropriate, plus retry and idempotency policies.

### Transaction boundaries

- A database deadlock may require **rolling back the entire transaction and starting a new one** before the next attempt.
- If an outbound HTTP call succeeded and then the local transaction rolled back, re-running the transaction can **send the HTTP call twice**.
- Updating status to `DONE` before outbound delivery succeeds can lose messages.
- **Transactional outbox** persists business data and sending intent in one transaction; the sender retries by event ID and the receiver processes idempotently.

Do not lump everything into one giant `RetryCallback` without designing for side effects.

## 20. Retry in asynchronous systems: threads, backpressure, and deadlines

`RetryTemplate` with standard backoff holds execution across a sequence of attempts. On small thread pools:

- Many handlers waiting in backoff can cause queues to grow.
- A synchronous `MessageChannel` can slow down an inbound HTTP gateway.
- A broker consumer may hold deliveries/partitions too long, affecting rebalances, prefetch, or throughput.
- Multiple instances retrying concurrently increase pressure on an already overloaded service.
- If the business request's deadline has expired, late retries can cause unwanted side effects.

### Simple capacity estimation formula

Suppose a worker thread processes each successful message in 100 ms. Normally, theoretical throughput is around **10 messages/s/thread** (excluding overhead).

If a partner fails and each message spends 10 seconds in a retry sequence, throughput drops to around **0.1 messages/s/thread**. With 10 threads, the system handles only about 1 message/s and backlog can spike rapidly.

This is only a simple model, not an exact forecast. Measure **P95/P99 handler latency, concurrent retries, queue depth, and broker lag** to cap in-process retries.

### When to switch to delayed retry

If an error is expected to recover over minutes or hours, do not hold threads or HTTP connections for long periods. Persist the message and schedule durable retries via a queue/topic/job store with:

- Retry state and `nextAttemptAt`;
- Attempt count durable across restarts;
- Stable `eventId` and idempotency;
- Message age limits;
- Backlog monitoring and manual replay capability;
- Terminal DLQ/`PARKED` state and an assigned owner.

**Handler retry and delayed replay are two layers with distinct boundaries** that must share an agreed total retry budget.

## 21. How do circuit breakers, rate limits, and timeouts complement retry?

Retry only makes sense when failures have a chance to self-recover. If an entire target system is down, hundreds of instances retrying together make things worse.

| Mechanism | Addresses | Key point |
|---|---|---|
| **Retry** | Transient errors per operation | Bound attempts and control side effects |
| **Timeout** | Prevents an attempt from hanging forever | Distinguish connect, read, and total deadlines |
| **Circuit breaker** | Cuts calls to a continuously failing dependency | When open, skips calling target; has half-open/recovery per policy |
| **Rate limiter** | Caps requests over time | Essential for 429s and quota-limited partners |
| **Bulkhead** | Isolates resources per workload/dependency | Prevents one down partner from exhausting all threads |
| **Backpressure** | Stops upstream from pushing faster than downstream handles | Prevents unbounded queue growth |
| **DLQ/parking** | Preserves failed messages for investigation/redrive | Does not fix invalid payloads automatically |
| **Idempotency** | Prevents duplicate side effects on resend | Separate requirement, not provided by retry |
| **Outbox/inbox** | Closes gaps between business data and messaging | Still needs transactions/uniqueness and recovery |

### No one-size-fits-all ordering

One pragmatic ordering:

1. Validate data and classify operation;
2. Acquire rate limit/bulkhead permit where appropriate;
3. Circuit breaker evaluates dependency health;
4. Execute one attempt with an explicit timeout;
5. Retry with backoff if the error qualifies and deadline permits;
6. Upon exhaustion, durable recovery.

Composing advice/circuit breakers in different orders yields **different call-count semantics**. Document the composition order and run tests proving no unintended calls happen while the circuit is open.

## 22. Logging, tracing, and metrics for retry

Do not just log `"Retrying request..."` on each attempt and consider the system observable. You need attempt counts, root causes, timings, final states, and message origins.

### Fields to record

| Field | Purpose |
|---|---|
| `eventId` | Identifies the stable business event across redelivery/replay |
| `correlationId`/`traceId` | Links inbound, outbound, and downstream |
| `flowId`/`endpointId` | Shows which adapter/handler is retrying |
| `attemptNumber`/`maxAttempts` | Distinguishes attempts from retries; avoids confusing 4 attempts with 4 retries |
| `errorCategory` | Transient, rate limit, invalid data, auth, unknown outcome |
| `exceptionType` | Technical classification; no need for full payload |
| `backoffDuration` | Measures wait time |
| `targetSystem` | HTTP partner, SFTP, JMS/AMQP, Kafka, or DB |
| `finalOutcome` | `SUCCESS`, `RETRY_EXHAUSTED`, `PARKED`, `DLQ`, `CANCELLED` |
| `ackOrCommitOutcome` | Whether the broker/source confirmed completion |
| `processingLatency` | Total latency and per-attempt latency |
| `idempotencyKeyRef` | Properly sanitized reference; contains no secrets |

**Never log** passwords, SFTP private keys, bearer tokens, full payment payloads, or unnecessary customer data. Handle trace context carefully so sensitive data never leaks to partners.

### Suggested metrics

| Metric | Definition | Why it matters |
|---|---|---|
| **`retry_attempts_total`** | Total attempts by flow and error category | Pinpoints endpoints with rising errors |
| **`retry_exhausted_total`** | Retry sequences ending unsuccessfully | Reveals recovery load |
| **`retry_success_after_retry_total`** | Messages succeeding after at least one retry | Measures retry effectiveness |
| **`retry_backoff_seconds`** | Distribution of wait times | Checks budget and latency |
| **`outbound_duration_seconds`** | Per-attempt and total processing time with separate labels | Spots bottlenecks |
| **`dead_letter_backlog`** | Messages in `PARKED`/DLQ by age and criticality | Prevents failed messages from being forgotten |
| **`duplicate_effect_prevented_total`** | Duplicate business events caught by dedup | Tracks redelivery and idempotency |
| **`source_redeliveries_total`** | Broker/file/job redrive redeliveries | Separates redeliveries from in-process retries |
| **`broker_lag` / `queue_depth`** | Messages waiting | Evaluates backpressure |
| **`terminal_failure_age`** | Max and P95 age of unresolved failures | Prioritizes backlog with business impact |

**Cardinality:** never attach `eventId` or `orderId` directly as metric labels (e.g., Prometheus labels), as every message creates a new time series. Put IDs in logs/traces, and restrict metric labels to bounded dimensions like flow, endpoint, error category, and outcome.

### Illustrative SLO set

- Percentage of valid messages processed successfully over a 24-hour/7-day window;
- P95 end-to-end processing latency with clear N;
- Zero business-critical messages stuck in `PARKED` past deadline;
- Zero duplicate business effects across defined test suites;
- Percentage of terminal errors carrying complete metadata for replay;
- Partner outages do not push backlog past operational thresholds longer than allowed.

Thresholds must be defined by the organization according to business needs; no single retry level or SLO fits every system.

## 23. Required test suite

Retry tests must verify **final outcomes and side effects**, not merely assert that a mock was called N times.

| ID | Scenario | Expected outcome |
|---|---|---|
| R1 | Handler succeeds on first attempt | Single invocation; no backoff |
| R2 | Two transient errors then success | Three attempts; correct result returned |
| R3 | Persistent transient error with maxAttempts=4 | Exactly four attempts, then routes to recovery |
| R4 | Invalid payload | No retry; goes to invalid-handling branch |
| R5 | HTTP 401/403 | Does not repeat requests with the same credentials |
| R6 | HTTP 429 + `Retry-After` | Delays per policy; no retry storm |
| R7 | HTTP POST succeeds but response times out | Does not create two business records due to idempotency/reconciliation |
| R8 | `RecoveryCallback` throws exception | Caller/container receives proper error; no erroneous ack |
| R9 | `RecoveryCallback` writes DLQ then returns normally | Acks only after message is safely persisted per design |
| R10 | Writing to DLQ fails | No message loss; rollback/nack or alternate durable path |
| R11 | Two nested retry layers | Total attempts calculable and bounded |
| R12 | Exponential backoff | Wait intervals match policy and respect cap |
| R13 | Multiple consumers fail concurrently | Does not exceed concurrency/rate budget |
| R14 | File inbound parse invalid | Quarantined once, not polled endlessly causing duplicates |
| R15 | SFTP upload times out after remote received file | Reconciled/checksummed, file not duplicated |
| R16 | JMS listener rolls back after exhaustion | Redelivery/DLQ per config; no duplicate business effect |
| R17 | AMQP consumer nacks/requeues | No unbounded hot loop; routes to DLQ |
| R18 | Kafka record fails processing | Offset not wrongly committed; ordering per contract |
| R19 | Kafka DLT replay with same `eventId` | Deduplication still holds |
| R20 | JDBC deadlock | Transaction retried in fresh scope, committed exactly once |
| R21 | Crash between outbound side effect and local commit | Dedupe/outbox/reconciliation resolves unknown outcome |
| R22 | Large backlog when partner is down | Threads/memory bounded, alert fires |
| R23 | Error channel has no subscriber | Terminal failure is not swallowed; recovery path clear |
| R24 | Retry policy `maxAttempts` modified | Contract tests catch change in call counts and latency |
| R25 | Worker/app restarts mid-retry | Distinguishes lost in-memory retry vs. durable replay |
| R26 | Expired credentials or wrong permissions | Does not retry endlessly; routes to proper ops handling |

### Example RetryTemplate test without external systems

~~~java
import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger invocations = new AtomicInteger();

String result = retryTemplate.execute(ctx -> {
    int current = invocations.incrementAndGet();
    if (current < 3) {
        throw new IOException("Temporary remote failure");
    }
    return "OK";
});

// Expectations:
// result == "OK"
// invocations.get() == 3
// backoff occurs between attempt 1/2 and 2/3
~~~

This pattern assumes `RetryPolicy` permits `IOException` and `maxAttempts` is at least 3. To verify backoff intervals reliably, use a **BackOffPolicy test double/clock abstraction** instead of tight wall-clock assertions (which flake under scheduling jitter).

### Real-world testing must include negative cases

A test checking only "retry on 503 eventually succeeds" is insufficient. You must also test that:

- A non-idempotent request **does not** create two side effects;
- An invalid message **is not** retried endlessly;
- A failed message **is not** acked and lost before reaching the recovery store;
- SFTP/File retry **does not** corrupt filter/metadata store state;
- Broker redelivery and handler retry **do not** multiply total attempts beyond budget;
- When a worker restarts, pending messages remain properly tracked.

## 24. Case study: order synchronization over SFTP and HTTP

### Background

An enterprise receives order files from a partner via SFTP. Spring Integration downloads the file, parses each record into a message, and calls an HTTP outbound gateway to create the order in an ERP system. Results are saved to a database and notifications are sent over AMQP.

Flow:

~~~text
SFTP inbound adapter / poller
   -> local file staging
   -> parse + validate
   -> message(eventId=orderId/version)
   -> HTTP outbound gateway (ERP)
   -> database status update
   -> AMQP outbound adapter
   -> archive file
~~~

Conditions:

- The SFTP partner sometimes uploads files slowly.
- The ERP returns 503 for a few minutes each day.
- The ERP occasionally records an order before the response times out.
- Some records are missing `customerId`.
- The database occasionally hits deadlocks.
- RabbitMQ occasionally disconnects.
- The system has **`maxAttempts=4`** for outbound HTTP, plus a scheduled file replay on failure.
- The organization requires zero duplicate orders and zero silently lost failed records.

### Simulated timeline

| Time | Event |
|---|---|
| 08:00 | File `orders-001.part` is uploading, not ready |
| 08:02 | Partner renames it to `orders-001.ready` |
| 08:03 | Poller picks up the file; record A is valid, record B is missing `customerId` |
| 08:04 | HTTP creates order A: ERP writes it, then response times out |
| 08:04–08:05 | `RetryTemplate` retries with backoff, risking a duplicate |
| 08:06 | Database update for status A hits a deadlock |
| 08:07 | Outbound AMQP fails to send notification |
| 08:10 | Replay scheduler attempts to reprocess the file |
| 09:00 | Operations sees high processed file counts, but ERP contains duplicate orders |

### Tasks

1. Identify which errors should be retried and which should not.
2. Choose appropriate **`RetryTemplate` boundaries**: at the HTTP outbound gateway, JDBC transaction, AMQP send, or entire flow?
3. Propose an **idempotency key and processing states** for each record.
4. Design handling when HTTP response times out even though ERP may have created the order.
5. Design recovery/DLQ/parking for invalid record B and exhausted record A.
6. Explain the impact of file replay on the accept-once filter and duplicate effects.
7. Identify the **ack/commit/transaction boundary** at each system.
8. Propose at least five metrics and six test cases to validate system reliability.

### Suggested solution

**1. Error classification.** Incomplete uploading files must not be processed; use temporary filenames/ready markers. Record B missing `customerId` is a payload error—do not auto-retry. HTTP 503 can be retried with backoff/rate budget. Timeout after POST is an unknown outcome—retry only if ERP supports idempotency or provides a status query API. JDBC deadlocks can retry the appropriate transaction; temporary AMQP disconnects can use retry/durable publishing.

**2. Boundaries.** Short handler retry for HTTP with idempotent operations; separate transaction retry for DB updates; AMQP notifications should consider transactional outbox so events are not lost if DB commits while the broker is down. **Never retry the entire flow from file ingestion** because that easily duplicates HTTP, DB, and notification calls.

**3. Stable EventId.** Each record gets **`partnerId + orderId + businessVersion`**, not a per-attempt message UUID. Persist states such as `RECEIVED`, `VALIDATED`, `ERP_PENDING`, `ERP_CONFIRMED`, `NOTIFICATION_PENDING`, `DONE`, `PARKED` alongside attempt count and a durable payload reference. A DB unique constraint prevents two records with the same `eventId`.

**4. Unknown outcome.** Send the same `Idempotency-Key` to ERP if supported by contract; otherwise query `orderId` before retrying, or route to manual reconciliation. Never treat a timeout as proof nothing was written.

**5. Recovery.** Invalid record B goes to quarantine with a reason code; exhausted record A goes to `PARKED`/DLQ with controlled replay. Mark the file complete only when all records are `DONE` or safely persisted in terminal states per business rules. If writing to parking fails, never delete the source file/state and lose data.

**6. Replay.** Accept-once filters/metadata stores may prevent re-polling the file, or if metadata is reset, the file is ingested with new message IDs. Therefore, replay must rely on **business event IDs and durable persisted state**, not in-memory retry contexts.

**7. Boundaries.** SFTP has no Kafka-style message ack; manage file staging/archiving/metadata explicitly. HTTP uses request/response, though outcomes may be unknown. DB transactions commit independently; RabbitMQ publishes and consumer acks/confirms are separate. There is no automatic distributed transaction spanning SFTP, ERP, DB, and RabbitMQ. Outbox/inbox and idempotency narrow the gap.

**8. Metrics/tests.** Track retry attempts by error category, retry exhausted, ERP duplicates prevented, parking backlog age, HTTP latency, DB deadlock retries, and AMQP publish failures. Test files still uploading, invalid records, ERP 503s, response timeouts after order creation, DB rollbacks, AMQP downtime, process restarts, and replaying the same `eventId`.

### Improved architectural approach

~~~mermaid
flowchart TD
    S["Completed SFTP file"] --> V["Stage + parse/validate"]
    V -->|"Invalid"| Q["Quarantine record with reason"]
    V -->|"Valid"| I["Inbox: unique business eventId"]
    I --> P["ERP sync state machine"]
    P --> H{"ERP request idempotent?"}
    H -->|"Yes"| R["Short retry + backoff + budget"]
    H -->|"No / outcome unknown"| C["Query status / reconcile"]
    R --> O["ERP_CONFIRMED"]
    C --> O
    R -->|"Exhausted"| K["PARKED / durable delayed retry"]
    O --> D["DB transaction: status + Outbox event"]
    D --> A["Outbox publisher sends AMQP"]
    A -->|"Broker unavailable"| A
    A --> F["Confirm publish + mark outbox sent"]
    F --> Z["DONE + archive per policy"]
    K --> M["Alert + controlled redrive"]
    Q --> M
~~~

The diagram depicts the **business target**, not an out-of-the-box framework flow. The AMQP publishing loop must use delayed scheduling, backoff, bounded attempts, and monitoring—not an infinite busy loop. Publish confirmation also depends on broker confirm semantics and consumer idempotency.

## 25. Common anti-patterns

| Anti-pattern | Consequence | Fix |
|---|---|---|
| Retrying every `Exception` | Permanent errors tie up threads and add load | Classify by error type and operation |
| Treating `maxAttempts` as excluding the first call | Exceeds expected request count | Explicitly distinguish attempts vs. retries |
| No backoff | Retry storm when partner goes down | Backoff + jitter + rate budget |
| Retrying HTTP POST without idempotency | Duplicate orders/payments | Idempotency key/status lookup/outbox |
| Swallowing exceptions in `RecoveryCallback` | Broker may ack unpersisted messages | Durable parking/DLQ or propagate exception |
| Confusing retry with redelivery | Total calls multiply unexpectedly | End-to-end total retry budget |
| Using message UUID as business key | Deduplication fails after redelivery | Stable business `eventId` |
| Using retry advice to fix invalid files | Poison messages never succeed | Quarantine and fix data |
| Retrying JDBC inside a `rollback-only` transaction | Commit still fails | Recreate transaction at the proper boundary |
| Believing Kafka offset commit covers external side effects | Duplicate or lost business work | Idempotent consumer/outbox |
| Treating `errorChannel` as a default durable store | Messages lost on restart or subscriber error | Persist parking/DLQ durably |
| Omitting timeouts | Attempts hang, no retry triggers | Per-attempt timeout + total deadline |
| Letting retries occupy all worker threads | Backlog and latency spike | Delayed retry, bulkhead, concurrency limits |
| Resending SFTP uploads on unknown outcome | Duplicate/partial files | Temporary name, checksum, reconcile |
| Enabling every retry layer by default | Accidental 4 × 4 × 4 attempts | Assign retry owner, bound each layer |
| Having no terminal outcome | Failed messages forgotten or loop forever | `PARKED`/DLQ with owner, alerts, replay |

## 26. Practical implementation checklist

- [ ] Define a **message contract**: `eventId`, schema/version, `correlationId`, payload reference, expiry, and sensitivity.
- [ ] Map every inbound/outbound adapter, gateway, poller, channel, and handler in the flow.
- [ ] Classify errors into **transient/permanent/unknown outcome**; never retry everything.
- [ ] Configure `RetryPolicy` with total **`maxAttempts`**, explicit stop conditions, and deadlines.
- [ ] Bound `BackOffPolicy`, using jitter/rate limits when multiple clients can retry concurrently.
- [ ] Set appropriate connect/read/operation timeouts on every external call.
- [ ] Avoid stacking retries across handler, HTTP client, gateway, and broker without an overall budget.
- [ ] Wrap only the target handler with `RequestHandlerRetryAdvice`; know what upstream/downstream steps are out of scope.
- [ ] Give `RecoveryCallback` a clear terminal outcome; never swallow exceptions before persisting the message.
- [ ] Assign owners, retention, reason codes, and attempt caps to error channels, parking, DLQs, and redrive flows.
- [ ] Use idempotency or outcome reconciliation for HTTP POST/payment/order operations.
- [ ] Enforce ready rules, partial-file protection, checksums, accept-once metadata, and replay for File/SFTP.
- [ ] Align JMS/AMQP ack/transaction/requeue/DLQ settings with broker configuration.
- [ ] Align Kafka offset/ack/error-handler/DLT settings with ordering and concurrency contracts.
- [ ] Scope JDBC retries to clean transactions; use unique keys/UPSERTs or outbox/inbox as needed.
- [ ] Manage service accounts and SFTP/HTTP/broker tokens securely; never log credentials.
- [ ] Collect metrics on attempts, exhaustion, latency, broker lag, parking backlog, and duplicate effects.
- [ ] Test crashes/restarts, timeouts after success, duplicate deliveries, DLQ failures, and recovery.
- [ ] Maintain runbooks for prolonged partner outages, poison messages, backlog thresholds, and credential failures.

## 27. Key terms and further reading

### Glossary

| Term | Meaning |
|---|---|
| **RetryTemplate** | Coordinates multiple attempts for a callback/handler |
| **RetryPolicy** | Decides which exceptions/conditions are retryable and caps attempts |
| **SimpleRetryPolicy** | Policy with attempt count cap and basic exception classification |
| **BackOffPolicy** | Defines wait intervals between attempts |
| **RetryContext** | Runtime state of an active retry sequence |
| **RecoveryCallback** | Fallback path executed after retries are exhausted |
| **RequestHandlerRetryAdvice** | Retry advice applied at a Spring Integration request handler |
| **ErrorChannel** | Messaging channel receiving errors; not a durable store by default |
| **Redelivery** | Broker/source re-delivering a message after error or missing ack |
| **Idempotency** | Repeating the same business event without unintended extra side effects |
| **Poison message** | A message that cannot succeed without fixing data or policy |
| **DLQ/DLT** | Dead-letter queue/topic holding messages unprocessable in the main flow |
| **Outbox/Inbox** | Patterns persisting send intent and deduplicating receipts by transaction/business key |
| **Ack / offset commit** | Source marking a message/record as processed under its protocol |
| **Retry storm** | Many clients retrying simultaneously, worsening load on a failing service |
| **Retry budget** | System-wide cap on resources, counts, or time spent on retries |
| **Outcome unknown** | Uncertainty about whether the target system applied the side effect |

### References

- **Spring Retry Reference:** `RetryTemplate`, `RetryPolicy`, `RetryContext`, `BackOffPolicy`, `RecoveryCallback`, and listeners.
- **Spring Integration Reference — Retry and More / Message Handler Advice:** `RequestHandlerRetryAdvice`, advice chains, and error handling.
- **Spring Integration Reference — Polling Consumer, Message Channels, Error Handling:** poller scope, synchronous/asynchronous errors, and error channels.
- **Spring Integration Reference — File/SFTP Adapters:** inbound file filters, metadata stores, local/remote transfers, and outbound file handling.
- **Spring Integration Reference — HTTP, JMS, AMQP, Kafka, JDBC Adapters/Gateways:** per-transport semantics.
- **Spring for Apache Kafka and Spring AMQP Reference:** consumer error handling, redelivery, acknowledgement, offsets, DLQ/DLT, publisher confirms.
- **Enterprise Integration Patterns:** Idempotent Receiver, Dead Letter Channel, Guaranteed Delivery, Message Store, Transactional Client.
- **Spring Framework Transaction Management:** transaction boundaries, rollback behavior, and coordinating retry with transactions.

**Key takeaway:** `RetryTemplate` enables **bounded, controlled retries of a unit of work**; `RetryPolicy` decides when to retry and `BackOffPolicy` decides how long to wait. Reliability in **Spring Integration Adapters** is achieved only when retry is placed at the right **message/handler boundary**, errors are accurately classified, **idempotency and transaction/ack behavior** are controlled, and **durable terminal recovery** exists when failures persist. Always verify: **"If a call times out, can the application retry without losing messages or duplicating business effects?"**
