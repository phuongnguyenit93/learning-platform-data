# Do Not Swallow Exceptions or Lose Correlation in Spring Integration Runtime

## Lesson Objectives

In **Spring Integration Runtime**, messages flow through channels, endpoints, consumers, pollers, and executors. When a handler fails, the system must know **which message the error belongs to**, **whether it was handled successfully**, and **whether to retry, roll back, route to an error queue, or notify the caller**. If a component catches and ignores an exception, or drops the correlation key while transforming a message, the flow may report false success, process duplicates, misgroup messages, or lose incident traceability.

After this lesson, you will be able to:

- Identify **swallowing exceptions** and distinguish it from error handling with a clear business decision.
- Explain how errors travel across **DirectChannel**, **ExecutorChannel**, **pollers**, **gateways**, and **errorChannel**.
- Read **ErrorMessage**, **MessagingException**, **failedMessage**, and the original message properly to trace the error source.
- Preserve **correlationId**, business keys, and **idempotency keys** across transforms, retries, splits, aggregations, and asynchronous boundaries.
- Design retries, transactions, message stores, quarantine/DLQ, and observability so failures are never silently declared successful.
- Write tests proving errors are not lost and messages remain linked to the right business action.

> Principle: **Every error must have an intentional outcome**: return an error to the caller, roll back so the source redelivers, perform bounded retries, record a durable failure, move to quarantine/DLQ, or mark a business error as resolved. Merely logging and continuing is rarely enough.

## 1. What Does "Swallowing an Exception" Mean?

**Swallowing an exception** happens when code catches an error without propagating it, without returning an appropriate failure status, and without executing a trackable terminal handling workflow.

Example of a service activator handling a payment request:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;

// Bad example: logs the error and lets the method return normally.
@ServiceActivator(inputChannel = "paymentRequests")
public void handle(Message<PaymentCommand> message) {
    try {
        paymentClient.charge(message.getPayload());
    } catch (RuntimeException ex) {
        log.error("Payment failed", ex);
        // Does not rethrow, does not record failure,
        // does not forward to a retry/quarantine mechanism.
    }
}
~~~

A synchronous caller will see no exception. With a consumer/poller or adapter, returning normally can cause the upper layer to consider this processing attempt complete, depending on acknowledgment and transaction configuration. **Logging the error** is only observation; it does not undo the operation, trigger retries, or guarantee the message is retained.

Other variants:

- Catching and returning **null** in a step expected to produce a reply, leaving downstream branches without results or causing unexplained timeouts.
- Catching and returning a default DTO like **success=true** or an empty object, masking the business failure.
- A Future or executor task fails without the caller observing the result or wiring an error flow.
- Catching and building a new message while dropping **correlationId**, `requestId`, or original error context.
- An error handler simply logging and finishing while operators believe failures are being stored/retried.

Conversely, **intentional exception handling** is valid. For example, a duplicate command already confirmed earlier can return an **already-processed** result under an idempotency contract; an unimportant notification may be safely ignored if that policy is explicitly defined and measured.

## 2. Exception Paths Depend on Channels and Threads

You cannot deduce an error's path solely from the handler's name. You must identify whether the message is processed **on the sender's thread or another thread**.

~~~mermaid
flowchart TD
    A["Producer / Gateway"] --> D["DirectChannel"]
    D --> H1["Synchronous handler"]
    H1 -- "throw" --> A
    B["Producer"] --> E["ExecutorChannel"]
    E --> H2["Handler on worker thread"]
    H2 -- "throw" --> EM["ErrorMessage"]
    EM --> EC["Configured errorChannel"]
    EC --> EH["Error handler / retry / quarantine"]
~~~

The diagram shows two typical paths; **it does not claim every gateway and adapter shares identical behavior**. A gateway with a configured error channel or error reply can convert failures into replies per contract; an adapter has its own acknowledgment or recovery mechanisms.

| Context | Where does the error surface? | What to clarify |
| --- | --- | --- |
| **DirectChannel** | Handler normally runs on the calling send thread; exception can propagate back to sender | Does the caller catch and drop the error? Does the gateway convert exceptions to replies? |
| **ExecutorChannel** | Handler runs on a `TaskExecutor` thread; sender may have completed `send()` | Which error channel receives the published error, who consumes it, and is there a failure-storage path? |
| **QueueChannel + polling endpoint** | Handler is invoked from a poll cycle; transactions and advice may wrap that call | Does the poller have retry/transaction/error channel? Will the message be redelivered or consumed? |
| **Inbound adapter / broker consumer** | Exceptions can occur in deserialization, before or after creating a Spring Message | What are the broker's ack/nack, redelivery, DLQ, and offset policies? |
| **Aggregator / resequencer** | Errors can occur in release strategy, message store, or processor | Which group is affected, is group state preserved, and how are timeouts/late arrivals handled? |

In Spring Integration, asynchronous processing errors are typically wrapped in an **ErrorMessage** and sent to the error channel identified by the **errorChannel** header or global error configuration. By contrast, synchronous paths propagating exceptions to callers do not necessarily emit an `ErrorMessage`. Before designing error handling, verify whether the exact endpoint/adapter is **an ErrorMessage publisher**.

### An error channel does not automatically imply retry or rollback

An error channel receiving an `ErrorMessage` does not mean the message is replayed. If the error handler receives it, merely logs, and returns normally, that may be **the end of the error's lifecycle**. Whether transactions commit or roll back and whether the source redelivers depend on where the error was caught and the specific advice/transaction/adapter.

Therefore, distinguish four steps:

1. **Error detection**: handler throws an exception.
2. **Error propagation**: exception reaches caller or `ErrorMessage` reaches the error flow.
3. **Recovery decision**: retry/rollback/quarantine/return business error.
4. **State recording**: message is processed, failed, or still pending.

These four steps may reside in different components; never assume an earlier step guarantees a later one.

## 3. Writing Handlers That Do Not Hide Errors and Preserve failedMessage

In Spring Messaging, **MessagingException** can carry **failedMessage**. When wrapping an error to add context, **keep the original exception as the cause** and link it to the message being processed:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.stereotype.Component;

record PaymentCommand(String orderId, String requestId, long amount) {}

interface PaymentClient {
    void charge(PaymentCommand command);
}

@Component
class PaymentHandler {
    private final PaymentClient paymentClient;

    PaymentHandler(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }

    @ServiceActivator(inputChannel = "paymentRequests")
    public void handle(Message<PaymentCommand> message) {
        PaymentCommand command = message.getPayload();
        try {
            paymentClient.charge(command);
        } catch (RuntimeException cause) {
            throw new MessagingException(
                    message,
                    "Unable to charge orderId=" + command.orderId(),
                    cause);
        }
    }
}
~~~

When a caller or error flow inspects **MessagingException**, it can extract:

- **getFailedMessage()**: the message associated with the failure (if present).
- **getCause()**: the root cause for transient/permanent classification.
- **MessageHeaders** of the failed message: `correlationId`, `requestId`, event type, tenant name if permitted by data policy.

Never create a new exception with only a short string like "Payment failed" while discarding the cause and original message; that destroys critical clues. However, **not every exception is a MessagingException**, and not every `MessagingException` carries `failedMessage`. Error consumers must handle missing fields gracefully.

**Note on idempotency:** The code above propagates errors properly, yet **does not prevent duplicate charges**. If the payment provider already debited the account and timed out returning the response, a retry may call it again. Pass a provider-supported **requestId/idempotency key**, or implement appropriate reconciliation and compensation.

## 4. Reading ErrorMessage to Trace the Failure and Related Message

**ErrorMessage** is a Spring Message whose payload is a **Throwable**. The headers of `ErrorMessage` itself do not necessarily hold all correlation headers of the business message. Inspect both **original message** (if present) and `MessagingException`'s **failedMessage**.

Diagram:

~~~text
ErrorMessage
  payload: Throwable
    └─ MessagingException (may sit inside the cause chain)
         ├─ failedMessage: Message<PaymentCommand>
         └─ cause: root error
  originalMessage: may be present, depending on the error publisher
  headers: headers of ErrorMessage itself
~~~

A dedicated handler for the error branch:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

record FailedPayment(
        String requestId,
        String correlationId,
        String errorType) {}

interface FailureJournal {
    // Real implementation must persist durably and deduplicate by requestId.
    void record(FailedPayment failure);

    // Quarantine even when correlation cannot be determined.
    void quarantine(ErrorMessage error);
}

@Component
class PaymentErrorConsumer {
    private final FailureJournal journal;

    PaymentErrorConsumer(FailureJournal journal) {
        this.journal = journal;
    }

    @ServiceActivator(inputChannel = "paymentErrors")
    public void onError(ErrorMessage error) {
        Message<?> failed = error.getOriginalMessage();
        Throwable failure = error.getPayload();

        // Some publishers do not attach originalMessage.
        // Look for MessagingException's failedMessage along the cause chain.
        if (failed == null) {
            for (Throwable current = failure;
                    current != null; current = current.getCause()) {
                if (current instanceof MessagingException messaging
                        && messaging.getFailedMessage() != null) {
                    failed = messaging.getFailedMessage();
                    break;
                }
            }
        }

        if (failed == null) {
            journal.quarantine(error);
            return; // Only finish once quarantine has recorded the error successfully.
        }

        Object requestId = failed.getHeaders().get("requestId");
        Object correlationId = failed.getHeaders().get("correlationId");
        if (!(requestId instanceof String request) || request.isBlank()
                || !(correlationId instanceof String correlation)
                || correlation.isBlank()) {
            journal.quarantine(error);
            return;
        }

        journal.record(new FailedPayment(
                request,
                correlation,
                failure.getClass().getName()));
    }
}
~~~

This pattern **demonstrates the error consumer's responsibility**: instead of stopping at logging, it forwards failure details to a durable **FailureJournal**. In real deployments, the journal may write to a database, quarantine store, or publish events via a transactional outbox. Add statuses such as **pending / failed / quarantined**, timestamps, sources, attempt counts, and retention policies to enable investigation or controlled replay.

If `FailureJournal` fails, **never assume** this secondary error will auto-retry: define retries/transactions for **the error flow itself** along with a fallback when error-recording infrastructure is down. Also avoid designing an error handler that sends its own failures endlessly back to the same error channel.

### Wiring an intentional error channel

Suppose the flow uses an **ExecutorChannel** before the payment handler and defines a channel bean named **paymentErrors**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
class PaymentErrorChannels {
    @Bean
    MessageChannel paymentErrors() {
        return new DirectChannel();
    }
}

// At the producer, when building a Spring Message to enter the async flow:
Message<PaymentCommand> message = MessageBuilder
        .withPayload(new PaymentCommand("O-42", "pay-42", 125000))
        .setHeader("requestId", "pay-42")
        .setHeader("correlationId", "checkout-42")
        .setHeader(MessageHeaders.ERROR_CHANNEL, "paymentErrors")
        .build();
~~~

In a context with an asynchronous error publisher supporting the **errorChannel** header, this header specifies the `ErrorMessage` destination. This is an **illustrative configuration snippet**; wire the real producer, channel, executor, and handler. If execution remains on a synchronous **DirectChannel** and exceptions propagate to the caller, the `errorChannel` header **does not automatically trigger** the error consumer.

When configuring the global **errorChannel**, remember the default subscriber may only log; verify where errors are actually handled and avoid contention or duplicate side effects across subscribers.

## 5. What Is Correlation and Why Is It Easy to Lose?

**Correlation** is the ability to tie messages, results, and errors to the right workflow or business entity. Distinguish these IDs:

| Field | Common Meaning | Stable across retries/transforms? |
| --- | --- | --- |
| **MessageHeaders.ID** | Technical identifier of a single Spring Message | Do not assume stability when constructing new messages or crossing systems |
| **correlationId** | Key linking messages in the same group/flow | Can be stable if explicitly forwarded; may also be set by splitter/aggregator under their own rules |
| **requestId / idempotencyKey** | Identifies a business request whose side effects must apply at most once | Should remain stable across retries/redelivery; used for duplicate control |
| **orderId / businessKey** | Identifies a business entity | May be shared across multiple distinct requests; does not replace `requestId` |
| **traceId / spanId** | Traces a distributed execution | Span may change per processing step; trace context must propagate per observability standards |
| **sequenceNumber / sequenceSize** | Ordering/group-size metadata, typically used with splitter/aggregator | Depends on EIP and sequencing configuration; do not treat as a business key |

**Never use message ID as an idempotency key** if deduplication is needed across adapters, brokers, or retries that generate new messages. Similarly, `orderId` alone is rarely enough: one order can undergo multiple valid operations such as creation, payment, and refund.

### Three places where correlation is commonly dropped

**1. A transformer constructs a new Message and forgets headers**

~~~java
// Easy to lose metadata if constructing a new message solely from payload.
return MessageBuilder.withPayload(normalizedOrder).build();
~~~

Fix with an explicit header policy:

~~~java
return MessageBuilder.withPayload(normalizedOrder)
        .setHeader("correlationId", incoming.getHeaders().get("correlationId"))
        .setHeader("requestId", incoming.getHeaders().get("requestId"))
        .build();
~~~

In some Spring Integration transformers, the framework automatically forwards headers when a method returns a payload. However, when **manually creating a Message**, using custom converters/adapters, or mapping outbound headers, verify actual output. Copy only meaningful headers; `contentType`, ACK handles, routing metadata, or old protocol headers may become invalid after changing representations.

**2. Thread switches and asynchronous error publishing**

After an **ExecutorChannel**, the sender may no longer wait for the handler. An `ErrorMessage` created by a worker has its own headers; read correlation from **failed/original message**, not solely from `ErrorMessage.headers`. If an endpoint relies on `errorChannel` in a header, ensure that header is preserved or replaced by equivalent error-channel configuration.

**3. Split, aggregate, retry, and redelivery**

- **Splitter** can emit multiple child messages and set correlation/sequence headers. If a custom splitter overwrites the group key arbitrarily, the aggregator may misgroup or wait forever.
- **Aggregator** groups messages per correlation strategy and release strategy; an error in a child message must retain both **business key** and **group key** for investigation.
- **Retry** re-executes processing; a new attempt is not a new business request. Keep the idempotency key stable, optionally adding a separate `attemptNumber` for diagnostics.
- **Broker redelivery** can construct a fresh Spring Message object. Comparing two deliveries solely by technical message ID easily misses duplicates.

~~~mermaid
flowchart TD
    REQ["requestId=pay-42\ncorrelationId=checkout-42"] --> T["Transformer"]
    T --> E["ExecutorChannel"]
    E --> H["Payment handler"]
    H -- "exception" --> ERR["ErrorMessage"]
    ERR --> EX["Extract failed/original message"]
    EX --> J["FailureJournal / DLQ"]
    J --> O["Look up pay-42\nwithin checkout-42"]
~~~

The goal is **being able to trace backward from an error to the original business action**, even across threads, internal messages, or app restarts.

## 6. Deciding Retries, Rollback, DLQ, and Processing State

Not every error should be retried; not every error shares the same transaction boundary.

| Error Category | Example | Typical Appropriate Action |
| --- | --- | --- |
| **Transient** | External service timeout, flaky DB connection, rate limit | Bounded retry with backoff/jitter; enforce idempotency |
| **Invalid data** | Malformed JSON schema, missing required field, negative amount | Record error and quarantine/DLQ; wait for data fix, do not retry infinitely |
| **Invariant violation / conflict** | Order already paid, stale version | Specific business rule; sometimes return already-processed, sometimes conflict |
| **Programming bug** | `NullPointerException`, unsupported mapping | Alert, isolate failing message, fix code; avoid tight infinite retries |
| **Uncertain side-effect outcome** | External API executed yet response timed out | Use idempotency key/reconciliation before deciding whether to retry |

### Retrying does not undo side effects that already occurred

~~~text
1. Handler calls payment provider → provider processes successfully.
2. Connection times out before handler receives the response.
3. Handler throws exception → retry attempt 2.
4. Without an idempotency key, the provider may charge a second time.
~~~

Keeping **requestId=pay-42** consistent across attempts is necessary to prevent duplicates; the provider or data store must **enforce** idempotency. Merely logging the same `requestId` does not create idempotency.

### Transactions with DirectChannel and ExecutorChannel

In a synchronous **DirectChannel** chain, handlers can participate in the transaction bound to the calling thread if advice and resources are configured compatibly. Thrown exceptions can trigger rollback per transaction policy. However, DB rollback does not automatically undo emails, HTTP calls, or payment APIs already invoked.

With **ExecutorChannel**, processing runs on another thread; the sender's transaction/`ThreadLocal` does not transfer automatically to the consumer. To protect DB writes at the handler with a transaction, place the transaction boundary on the consumer or appropriate source side. Do not infer transactional safety from the producer successfully sending a message.

### Retry advice and recovery

Spring Integration offers endpoint advice/retry mechanisms, where **RequestHandlerRetryAdvice** can wrap handler invocation. After attempts are exhausted, a **recovery callback** can route the error to an error channel via mechanisms like **ErrorMessageSendingRecoverer**.

When using retry advice, define explicitly:

- **Which step** does retry wrap (handler, poller, adapter), and what side effects may have happened earlier?
- Which exceptions merit retry and what is the maximum backoff?
- Once retries are exhausted, is the exception **rethrown**, converted to an `ErrorMessage`, saved as a failure, or sent to a DLQ?
- When recovery consumes an error, how do **transactions and acknowledgments** behave in the adapter?
- Does the system retain **requestId, correlationId, and attempt** for investigation?

Never attach an error handler just to return normally and assume the broker will redeliver. If broker redelivery is required, verify exception propagation, ack/nack policies, and adapter transactions.

## 7. Correlation Across Message Stores, Restarts, and Multiple Instances

Keeping correlation in headers or payloads at a single moment in time **is not enough** for durable operations:

- In-memory **QueueChannel** or **MessageGroupStore** loses messages/state when the process stops; persistent stores survive restarts but need proper schemas, serializers, and transactions.
- Messages whose headers hold non-serializable objects, such as an in-JVM channel or callback, can fail durable persistence. Use explicit header mapping and channel registration policies instead of blindly copying every header.
- **Aggregator** can use `correlationId` for grouping; when scaling to multiple instances, evaluate lock registries, shared stores, timeouts, incomplete groups, and late arrivals.
- **FailureJournal** or DLQ should persist **businessId, requestId, correlationId, error category, timestamp, attempt, and status**, alongside sanitized payloads or safe references for replay. Never rely solely on in-memory logs.
- When replaying an old message, keep the **idempotency key**, while optionally assigning a **new execution/trace span** to observe the replay attempt.
- Stopping/starting an **IntegrationFlow** does not guarantee in-flight errors have been recorded, nor does it trigger retries automatically. Check lifecycle, store state, in-flight executors, and message ingestion cutoffs.

Example failure record:

~~~json
{
  "requestId": "pay-42",
  "correlationId": "checkout-42",
  "businessId": "O-42",
  "flow": "payment",
  "stage": "paymentHandler",
  "attempt": 3,
  "status": "QUARANTINED",
  "errorType": "PAYMENT_TIMEOUT",
  "occurredAt": "2026-01-15T10:00:00Z"
}
~~~

This is an **example format**, not a default Spring Integration schema. Never store payment card data or secrets in the journal. If storing payloads, consider encryption, access controls, TTL, and schema versioning.

## 8. Observing Errors Without Losing Context

Every critical log/trace event should answer:

1. **Which message?** `requestId`, `correlationId`, `businessId`, message type.
2. **Where?** flow name, channel, endpoint, consumer, thread, application instance.
3. **What happened?** exception class, cause chain, attempt, processing stage, and whether side-effect outcome is known.
4. **What next?** `RETRYING`, `FAILED`, `QUARANTINED`, `REPLAYED`, `COMPLETED`.

Example structured log:

~~~text
level=ERROR flow=payment endpoint=paymentHandler
requestId=pay-42 correlationId=checkout-42 businessId=O-42
thread=payment-worker-3 attempt=2 errorType=PAYMENT_TIMEOUT
nextAction=RETRY outcome=UNKNOWN
~~~

**Do not equate trace ID with correlation ID.** Traces/spans are created by observability tooling and propagate with execution context; business correlation often outlives a single attempt or HTTP request. Log both in their respective roles.

Track these metrics:

- Success/failure counts by endpoint, exception classification, and attempt count.
- Retry rate, failures after retry exhaustion, DLQ/quarantine size, and oldest item age.
- Executor queue length, rejected tasks, processing latency, and poller backlog.
- Unreleased aggregator groups, group timeouts, duplicate messages, and late arrivals.
- Count of errors **missing requestId/correlationId** — a metadata quality signal that must not be ignored.

For centralized error handling, add size limits and PII protections; never log raw secret payloads merely for debugging convenience.

## 9. Testing to Guarantee Errors and Correlation Are Not Lost

### A. Unit test for synchronous handler

Mock the payment client to throw an exception; verify the handler throws **MessagingException** with the right **cause** and **failedMessage**:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

class PaymentHandlerTest {
    @Test
    void propagatesFailureWithOriginalMessage() {
        RuntimeException providerTimeout =
                new RuntimeException("provider timeout");
        PaymentClient client = command -> {
            throw providerTimeout;
        };
        PaymentHandler handler = new PaymentHandler(client);

        Message<PaymentCommand> input = MessageBuilder
                .withPayload(new PaymentCommand("O-42", "pay-42", 125000))
                .setHeader("requestId", "pay-42")
                .setHeader("correlationId", "checkout-42")
                .build();

        MessagingException error = assertThrows(
                MessagingException.class,
                () -> handler.handle(input));

        assertSame(input, error.getFailedMessage());
        assertSame(providerTimeout, error.getCause());
        assertEquals("checkout-42",
                error.getFailedMessage()
                        .getHeaders().get("correlationId"));
    }
}
~~~

This test verifies the handler preserves the error and metadata **when invoked directly**. It does not prove the entire flow behaves properly across executors/adapters, so integration tests are still required.

### B. Integration test for asynchronous flow

Create an input channel, **ExecutorChannel**, a handler that intentionally throws, and an error consumer receiving `ErrorMessage`. Use synchronization primitives in tests such as `CountDownLatch` to await events instead of arbitrary **sleep** durations. Verify:

- After the producer sends, the error **is routed to the error flow** as configured.
- `ErrorMessage` carries the root cause; original/failed message yields **requestId and correlationId**.
- The journal records **exactly one intentional failure outcome** per idempotency key; never misreported as success.
- If correlation is absent, the message enters **quarantine** and raises an alert; no arbitrary ID is fabricated.
- Across retries, `requestId` stays identical; attempts vary without producing multiple business charges.

### C. End-to-end test for transactions, redelivery, and restarts

Test each scenario:

| Simulated Scenario | Evidence to Collect |
| --- | --- |
| Handler throws immediately on entry | Caller/error flow observes error; success state is not wrongly recorded |
| DB failure inside transaction | Actual rollback occurs; redelivery follows source configuration |
| Timeout after external API already executed | Idempotency/reconciliation prevents duplicate side effects |
| Message passes through transformer building a new Message | Correlation/`requestId` remain intact; `contentType` adjusted if needed |
| Splitter creates parts and aggregator waits for results | Each part has proper group key/sequence; errors identify the group |
| Executor overloaded or rejects tasks | Errors/metrics reflect dispatch failure; messages are not silently dropped |
| Restart with in-flight messages/persistent store | State, correlation keys, and replay policy are preserved accurately |
| Error journal/DLQ temporarily unavailable | Defined retry/fallback operates; errors in the error handler itself are observed |

## 10. Practice Exercise: Finding Gaps in a Flow

Suppose we have this flow:

~~~text
HTTP gateway
  → DirectChannel
  → JSON transformer
  → ExecutorChannel
  → payment handler
  → outbound event

errorChannel
  → logger
~~~

Initial conditions:

- The JSON transformer **manually creates** a new Message solely from the payload.
- The payment handler uses `catch(Exception)` and only logs.
- The outbound event uses **MessageHeaders.ID** for deduplication.
- The global error channel has only a logging subscriber.

Analyze the flaws that can occur:

1. **Lost correlation:** the transformer does not preserve `requestId`/`correlationId`, leaving the error flow without tracking keys.
2. **Lost failure signal:** the payment handler exits normally; the error publisher may receive no exception to send to the error channel.
3. **Deduplicating on the wrong key:** technical message IDs can change during transformations or replays, causing one request to be processed as multiple business actions.
4. **Undefined recovery:** even if an error reaches the logger, logging alone proves neither retry, rollback, nor quarantine.

One remediation plan:

- Preserve **business correlation and requestId** during transformation, verifying headers via integration tests.
- Let the handler **throw errors carrying cause and failedMessage**, converting to a business outcome only under explicit rules.
- Design an error flow persisting to **FailureJournal/DLQ** and alerting, with a safe replay path.
- Enforce an idempotency key at the side-effect execution layer, with retries/backoff and properly scoped transactions.
- Track counts of failed messages **missing correlation** to detect regressions.

## 11. Pre-Production Checklist

- **Propagation:** Every `catch` block handles errors with a concrete outcome or rethrows with cause; never log and ignore unconditionally.
- **Thread boundaries:** For `DirectChannel`, `ExecutorChannel`, and pollers, know whether errors go to callers or which error flow.
- **Error flow:** An actual consumer handles `ErrorMessage`, records terminal state, and handles failures within the error handler itself.
- **Identity:** Use business keys, `requestId`/idempotency keys, and `correlationId` in their proper roles; do not confuse with message ID or trace ID.
- **Header contract:** Transformers, gateways, adapters, splitters, and aggregators preserve/map correlation as verified by tests.
- **Retry:** Classify errors, bound attempts, apply backoff, and define exhaustion outcomes; avoid duplicate side effects.
- **Transactions:** Know where transactions start/end, especially across executors and external APIs.
- **Persistence:** Message store, `FailureJournal`, or DLQ retains required state across restarts.
- **Observability:** Logs/traces/metrics cover lost correlation, exception causes, and quarantine backlog.
- **Verification:** Unit tests check cause/`failedMessage`; integration tests verify async error paths and replay.

## Conclusion

In Spring Integration, **keeping exceptions meaningful** and **preserving correlation across the message flow** are two core requirements for a reliable runtime. Channels determine execution paths, endpoints and advice govern error propagation, transactions/retries control recovery, and business correlation links every outcome back to the right request. Good design does not stop at catching errors: it **makes each message's terminal state explicit** and enables investigation, repair, or replay without duplicating business side effects.

## References

- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html)
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Framework API — MessagingException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessagingException.html)
- [Spring Framework API — ErrorMessage](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ErrorMessage.html)
