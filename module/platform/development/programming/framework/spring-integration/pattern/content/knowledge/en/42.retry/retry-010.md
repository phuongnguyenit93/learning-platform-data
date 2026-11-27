# Combining Retry with Error Channels in Spring Integration

## 1. The Problem: Where Does Retry Happen, and Where Does the Final Error Go?

A system receives an `OrderPaid` event and must call an invoicing API. The partner API occasionally returns HTTP 503, yet it can also reject permanently if the order data is invalid. If the application simply catches and ignores the exception, the transaction may be lost. If it retries forever, the flow stalls and can overload the partner.

The desired design is:

1. **Bounded retries** when a recoverable error occurs.
2. **Backoff** so the service is not bombarded while already failing.
3. Once retries are exhausted, produce an **`ErrorMessage`** and route it to an observable error channel.
4. On the error channel, record `eventId`, root cause, and attempt count, then route into remediation or dead-letter/quarantine workflows.
5. On retries or replays, prevent **duplicate business side effects**.

In the **SPRING_INTEGRATION_PATTERN** module, this lesson combines Enterprise Integration Patterns with Router, Filter, Transformer, Splitter, Aggregator, Gateway, and correlation flows. The goal is not merely "keep retrying until it works," but rather to create loosely coupled message flows with transparent success/error paths, per-branch testability, and zero silent data loss.

~~~mermaid
flowchart LR
    P[Producer] --> F[Validation / Filter]
    F --> H["Service handler<br/>Retry Advice"]
    H -->|Success| S[Success channel]
    H -->|Retryable error| H
    H -->|Retries exhausted| R[Recovery callback]
    R --> E["ErrorMessage<br/>Error channel"]
    E --> D["Dead letter / Audit"]
    D --> O[Controlled investigation and replay]
~~~

> **Key rule:** retry and error channels do not replace each other. Retry is a **policy for reacting to failures**. An error channel is a **transport path for error details** so another endpoint can handle, record, or decide remediation.

## 2. Concepts You Must Distinguish

| Term | Meaning | Example |
| --- | --- | --- |
| **Retry attempt** | One re-execution of a failed operation | Calling the invoicing API a 2nd time |
| **Retry policy** | Decides which errors are retryable and max attempts | 3 tries on transient connection errors |
| **Backoff policy** | Wait interval between attempts | 200 ms then increasing |
| **Recovery callback** | Action when retry cannot continue | Routing the error to a handling channel |
| **ErrorMessage** | Message carrying a `Throwable` payload | Exception + failed message context |
| **Error channel** | `MessageChannel` receiving `ErrorMessage` | `orders.retry.exhausted` |
| **Dead-letter/quarantine** | Storage holding failed data for triage/replay | DB table or error topic |
| **Idempotency key** | Stable ID for the business operation | `invoice:order-501:v1` |

### Attempt Count Includes the Initial Call

With `SimpleRetryPolicy(3)`, there are at most **3 handler executions total**, not one initial call plus three retries.

~~~text
Attempt 1: exception -> backoff
Attempt 2: exception -> backoff
Attempt 3: exception -> recovery callback
~~~

If the second attempt succeeds, there is no third attempt. If the error is classified as non-retryable, the policy can route straight to recovery/error handling without retrying.

### Retry Is Not Infinite Replay

A long-running message processing system needs a **clear termination point** when processing cannot succeed. For example:

- HTTP 503 or transient timeout: bounded retry is appropriate depending on operation idempotency.
- HTTP 400 from bad data: generally should not be retried with the exact same data.
- HTTP timeout after the partner **already processed successfully**: outcome is uncertain; query or retry with an idempotency key to avoid issuing two invoices.

## 3. How Synchronous and Asynchronous Errors Reach Error Channels Differently

### 3.1. Synchronous Handler on `DirectChannel`

`DirectChannel` invokes its subscriber on the sender's thread. If the handler throws an exception with no surrounding retry/recovery, the exception normally propagates back to the caller:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as DirectChannel
    participant H as Handler
    P->>C: send(message)
    C->>H: invoke(message)
    H--xC: throw exception
    C--xP: exception to caller
~~~

On a **synchronous** path, do not assume exceptions automatically go to the global `errorChannel`. To funnel failures into a handling channel, **explicitly configure** a mechanism such as `RequestHandlerRetryAdvice` with `ErrorMessageSendingRecoverer`, or catch/route errors at an appropriate call boundary.

### 3.2. Executors, Pollers, and Asynchronous Boundaries

With an `ExecutorChannel` or poller-driven endpoints, producer code may have already returned when the downstream handler fails. Several asynchronous Spring Integration components use `ErrorMessagePublisher`/`MessagePublishingErrorHandler` to convert exceptions into `ErrorMessage`s sent to a specified error channel, or fall back to the shared `errorChannel`.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant E as ExecutorChannel
    participant H as Handler
    participant X as ErrorChannel
    P->>E: send(message)
    E-->>P: Accepted
    E->>H: runs on another thread
    H--xE: exception
    E->>X: ErrorMessage per configured error handler
~~~

**Do not assume every async failure always lands on one specific channel.** Behavior depends on the endpoint, error handler, `errorChannel` header, channel type, and integration configuration. With external broker adapters or consumers, check the acknowledgement and retry/redelivery contract of the adapter/broker itself.

### 3.3. Three Names That Are Easy to Confuse

| Mechanism | Where it is used |
| --- | --- |
| Global `errorChannel` | Spring Integration's default error channel when an async publisher/handler uses it |
| `errorChannel` header | A message can specify an error channel if the error-emitting component honors that header |
| Custom `orders.retry.exhausted` | An application-specified **recovery** channel, e.g., with `ErrorMessageSendingRecoverer` |

A channel named `orders.retry.exhausted` will not receive errors on its own unless some component sends `ErrorMessage`s to it. Conversely, the global `errorChannel` does not automatically act as a durable dead-letter store.

## 4. Two Common Ways to Organize Retries

### Approach A — Retry at the Handler Itself

Attach `RequestHandlerRetryAdvice` to a Service Activator or outbound handler. Retries wrap that handler invocation, and `ErrorMessageSendingRecoverer` can serve as the recovery callback.

~~~mermaid
flowchart LR
    A[Inbound channel] --> B["Handler + RetryAdvice"]
    B -->|Success| C[Output channel]
    B -->|Exhausted| D[ErrorMessageSendingRecoverer]
    D --> E[Recovery channel]
~~~

Suitable when exceptions occur **during a synchronous handler call** and you want to decouple final failure handling from the producer. Note: depending on backoff, retries can hold the executing thread.

### Approach B — Retry at the Consumer or Async Source

Once a message is placed into a `QueueChannel`/broker, the downstream receiver needs **its own** retry and error flow:

~~~mermaid
flowchart LR
    A[Producer] --> Q[Queue / Broker]
    Q --> P[Poller / Consumer]
    P --> H[Handler + retry]
    H -->|Success| S[ACK / Complete]
    H -->|Failure exhausted| E[Error channel / DLQ]
~~~

Never attach Retry Advice **before a queue** and expect it to catch exceptions thrown **after** a separate consumer pulls the message out.

## 5. Complete Example: `RequestHandlerRetryAdvice` + `ErrorMessageSendingRecoverer`

This learning example illustrates a flow with two outputs:

- `orders.success`: handler succeeds within at most three attempts.
- `orders.retry.exhausted`: recovery callback emits an `ErrorMessage` after retries are exhausted.

The example components live in a `@Configuration` class runnable inside a Spring context. Core dependencies: `spring-boot-starter-integration`, Spring Retry (`spring-retry` module), and `spring-boot-starter-test` for JUnit.

### 5.1. Declaring Channels and Retry Policy

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
public class RetryErrorChannelConfig {

    @Bean("orders.in")
    public MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean("orders.success")
    public PollableChannel ordersSuccess() {
        return new QueueChannel();
    }

    @Bean("orders.retry.exhausted")
    public PollableChannel ordersRetryExhausted() {
        return new QueueChannel();
    }

    @Bean
    public ConcurrentMap<String, AtomicInteger> attemptsByEvent() {
        return new ConcurrentHashMap<>();
    }

    @Bean
    public RequestHandlerRetryAdvice orderRetryAdvice(
            @Qualifier("orders.retry.exhausted") PollableChannel errors) {

        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(new SimpleRetryPolicy(3));

        FixedBackOffPolicy backOff = new FixedBackOffPolicy();
        backOff.setBackOffPeriod(100L);
        template.setBackOffPolicy(backOff);

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(template);
        advice.setRecoveryCallback(
                new ErrorMessageSendingRecoverer(errors));
        return advice;
    }

    @Bean
    public IntegrationFlow orderFlow(
            RequestHandlerRetryAdvice orderRetryAdvice,
            ConcurrentMap<String, AtomicInteger> attemptsByEvent) {

        return IntegrationFlow.from("orders.in")
                .handle(String.class, (payload, headers) -> {
                    String eventId = (String) headers.get("eventId");
                    int attempt = attemptsByEvent
                            .computeIfAbsent(eventId, key -> new AtomicInteger())
                            .incrementAndGet();

                    if (payload.equals("FAIL_ALWAYS") || attempt < 3) {
                        throw new IllegalStateException(
                                "Simulated temporary failure, attempt=" + attempt);
                    }

                    return "INVOICED:" + payload;
                }, endpoint -> endpoint.advice(orderRetryAdvice))
                .channel("orders.success")
                .get();
    }
}
~~~

**Key points in this configuration:**

1. `SimpleRetryPolicy(3)` permits up to three handler calls under the demo policy.
2. `FixedBackOffPolicy(100 ms)` inserts a fixed pause between attempts.
3. `RequestHandlerRetryAdvice` wraps specifically the handler configured with `endpoint.advice(...)`.
4. `ErrorMessageSendingRecoverer` sends the final error to the `orders.retry.exhausted` channel.
5. `QueueChannel` success and error outputs let tests call `receive(timeout)`; **they are not durable DLQs**.

The simulation intentionally fails for one message using a counter map for testing purposes. In production, never store retry state in this in-memory map across multiple instances or restarts, and never throw synthetic errors from business logic like this.

### 5.2. Producer Attaching Business Identity

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public boolean submitInvoice(MessageChannel ordersInput,
                             String eventId, String payload) {
    return ordersInput.send(
            MessageBuilder.withPayload(payload)
                    .setHeader("eventId", eventId)
                    .setHeader("correlationId", "order-501")
                    .build());
}
~~~

`ordersInput` must be the `orders.in` bean. In a real system, the producer might receive requests via a Gateway, HTTP inbound adapter, or broker. `eventId` must remain **stable across replays**, never randomly regenerated per handler execution.

### 5.3. Recovery Callbacks Change the Caller's Success Contract

When retries exhaust and `ErrorMessageSendingRecoverer` **successfully sends** to `orders.retry.exhausted`, the error is handled at the **retry interceptor** level: the sender may no longer see an exception even though the business operation **did not succeed**. A message entering an error queue does **not** equal successful invoicing.

Therefore, the API invoking the flow must distinguish outcomes:

- Business operation succeeded.
- Accepted for asynchronous processing.
- Failed to process; routed to error queue or awaiting remediation.

When designing a synchronous request/reply Gateway, define what happens if the recovery callback returns `null` with no reply: the caller may hang until `replyTimeout`. Never report "success" simply because the initial `send(...)` call did not throw.

## 6. What Does `ErrorMessage` Contain?

`ErrorMessage` is a message whose payload is a `Throwable`. When Retry Advice is exhausted, the error may be wrapped in a `MessagingException` or related exception. Depending on how it was created, you can access the original message via `ErrorMessage.getOriginalMessage()` or `MessagingException.getFailedMessage()`.

Example error-handling handler:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

public class ExhaustedRetryHandler {

    @ServiceActivator(inputChannel = "orders.retry.exhausted")
    public void handle(ErrorMessage error) {
        Throwable failure = error.getPayload();
        Message<?> original = error.getOriginalMessage();

        if (original == null && failure instanceof MessagingException ex) {
            original = ex.getFailedMessage();
        }

        Object eventId = original == null
                ? "UNKNOWN"
                : original.getHeaders().get("eventId");

        // In production: write error and message to a durable DLQ/inbox.
        // A log statement does not replace durable persistence.
        System.err.println("eventId=" + eventId);
        System.err.println("cause=" + failure);
    }
}
~~~

**Note:** the snippet above illustrates reading the error. To run it, register the class as a Spring bean attached to a **subscribable channel** like `DirectChannel`, or build a poller/flow reading the `QueueChannel`. In the section 5 demo, `orders.retry.exhausted` is a **QueueChannel for test polling**, so you cannot simply slap `@ServiceActivator` on it without adding a proper polling setup.

In production flows, one option is making `orders.retry.exhausted` a `DirectChannel` with a Service Activator persisting failures to a DB/error topic, and handling cases where the error store itself is down. Another option is keeping a `QueueChannel` and configuring a poller with dedicated error handling.

### Do Not Treat Every Exception as a Permanently Broken Message

When classifying errors, inspect the **root cause** and context:

| Error | Recommendation |
| --- | --- |
| `ConnectException`, HTTP 503, transient DB error | Bounded retry with appropriate backoff |
| Invalid payload/schema, missing required field | Stop retrying, quarantine for data repair |
| Unauthorized/forbidden | Likely needs config/secret fix before replay |
| HTTP timeout after sending request | Check idempotency / reconcile since side effect may have occurred |
| Unidentified programming bug | Log/alert, limit retries to avoid repeating system errors |

`SimpleRetryPolicy(3)` in the demo defaults to retrying many exception types. Production policies should explicitly classify retryable exceptions rather than retrying all errors uniformly.

## 7. Testing Success and Retry-Exhausted Paths

The test below uses **two messages with distinct `eventId`s** so counters do not collide:

- `success-001`: handler fails twice and succeeds on the third try.
- `exhausted-001`: handler always fails; recoverer sends an `ErrorMessage` to the error channel after three attempts.

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(RetryErrorChannelConfig.class)
class RetryErrorChannelTest {

    @Autowired
    @Qualifier("orders.in")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.success")
    PollableChannel success;

    @Autowired
    @Qualifier("orders.retry.exhausted")
    PollableChannel exhausted;

    @Autowired
    ConcurrentMap<String, AtomicInteger> attemptsByEvent;

    @Test
    void succeedsAfterTwoFailures() {
        assertTrue(input.send(
                MessageBuilder.withPayload("ORDER-501")
                        .setHeader("eventId", "success-001")
                        .build()));

        Message<?> result = success.receive(1_000);
        assertNotNull(result);
        assertEquals("INVOICED:ORDER-501", result.getPayload());
        assertEquals(3, attemptsByEvent.get("success-001").get());
        assertNull(exhausted.receive(0));
    }

    @Test
    void sendsErrorMessageAfterRetryExhausted() {
        assertTrue(input.send(
                MessageBuilder.withPayload("FAIL_ALWAYS")
                        .setHeader("eventId", "exhausted-001")
                        .build()));

        Message<?> failed = exhausted.receive(1_000);
        assertNotNull(failed);
        assertInstanceOf(ErrorMessage.class, failed);
        assertInstanceOf(Throwable.class, failed.getPayload());
        assertEquals(3, attemptsByEvent.get("exhausted-001").get());
        assertNull(success.receive(0));
    }
}
~~~

Test cases should run isolated or use separate contexts/queues in parallel runs so messages from other tests do not leak in. This test verifies flow behavior with a `DirectChannel` and recovery queue; it does not prove durability across restarts.

**How to interpret the result:** if the `exhausted` test passes and `input.send(...)` throws no exception, that is because recovery routed the error message to another channel—it **does not mean business processing succeeded**.

## 8. When There Is No Recovery Callback or When Recovery Also Fails

With `RequestHandlerRetryAdvice` without a recovery callback, exhausted exceptions propagate back to the caller on synchronous paths; when running behind a poller/executor, the appropriate error publisher layer can route them to an error channel.

With `ErrorMessageSendingRecoverer`, if the error channel does not exist, has no subscriber, blocks, or fails to persist to the error store, recovery itself can fail. Never assume a message is durably stored simply because code called `send(...)` on a channel.

~~~mermaid
flowchart TB
    H["Handler + Retry Advice"] --> Q{Succeeded?}
    Q -->|Yes| S[Success output]
    Q -->|No, retries exhausted| C[Recovery callback]
    C --> R{Error sent successfully?}
    R -->|Yes| E[Error channel / durable error workflow]
    R -->|No| X[Recovery failure to handle at caller/thread boundary]
~~~

A production design must decide **who takes responsibility** when the error channel or DLQ also fails:

- Rethrow the exception so the source omits ACK and triggers appropriate redelivery.
- Use an outbox or transaction if the source and error store can share one transaction.
- Fail over to a controlled fallback or trigger immediate operational alerts.
- Never settle for just logging an error and "skipping" a critical event.

**Never call an error handler and exit silently unless you are certain the replay context was durably captured.**

## 9. Distinguishing Retry Advice, Delayer Retries, and Broker Redelivery

In a large flow, multiple retry mechanisms can coexist:

| Location | Mechanism | Errors it observes |
| --- | --- | --- |
| Service Activator / outbound handler | `RequestHandlerRetryAdvice` | Exceptions inside the advised handler invocation |
| Delayer releasing due messages | `maxAttempts`, `retryDelay` | Exceptions propagated when Delayer dispatches downstream |
| Poller | Poller advice chain, error handler | Errors during poll/dispatch/handle per endpoint config |
| Kafka/RabbitMQ/JMS consumer | Adapter/broker redelivery/retry/DLQ | Errors and ACK/NACK per consumer contract |
| HTTP client | Client-level retry | Network/request errors controlled by the client |

For example, a Delayer retries up to 3 times while the inner handler also has Retry Advice up to 3 times: if every operation fails and exceptions bubble across both layers, the partner can be called **up to 9 times** in a naive setup. With a recovery callback, the outcome also depends on whether the callback rethrows.

**Rule of thumb:** designate one primary retry owner per error category, compute the **total retry budget**, and avoid unintended multiplicative retries. For HTTP timeouts where request completion is uncertain, enforce idempotency keys before deciding to retry.

## 10. Error Channels and Idempotency

`MessageHeaders.ID` identifies a Spring `Message` instance, yet a resent event from a producer may construct a new message with a different UUID. Therefore:

- `eventId`: stable key for the **business event**.
- `correlationId`: links messages belonging to the same order/workflow.
- `retryAttempt`: operational/alerting telemetry; not a deduplication key by itself.
- `messageGroupId`: if a Delayer is present, the group key for waiting messages, **not** a dedup key.

~~~java
MessageBuilder.withPayload("ORDER-501")
        .setHeader("eventId", "invoice:order-501:v1")
        .setHeader("correlationId", "order-501")
        .build();
~~~

Retrying a call can execute side effects multiple times. For instance, the partner invoicing API succeeds yet the response times out; if the caller retries and the partner does not recognize the idempotency key, two invoices get created.

Architectural pseudocode:

~~~java
// Illustrative concept only, not an atomic production implementation.
void processInvoice(String eventId, String orderId) {
    if (idempotencyStore.alreadyCompleted(eventId)) {
        return;
    }

    partnerApi.createInvoiceWithIdempotencyKey(eventId, orderId);
    idempotencyStore.markCompleted(eventId);
}
~~~

Checking then marking separately has a race condition. Production systems need atomic claim/unique constraints, `PROCESSING`/`COMPLETED` states, transactions, leases/retries for stuck states, and partner-side idempotency. **An error channel receives failures; it does not provide deduplication by itself.**

## 11. Error Flows for Other EIP Patterns in the Module

A solid error path must carry sufficient context as messages cross multiple patterns:

~~~mermaid
flowchart LR
    A[Inbound] --> T[Transformer]
    T --> R{Router}
    R --> S[Service Activator + Retry]
    R --> Q[Other route]
    S -->|Success| O[Success]
    S -->|Retries exhausted| E[Error channel]
    E --> P[Audit / Quarantine]
~~~

| EIP | Notes when combining retry and error channel |
| --- | --- |
| **Transformer** | For invalid-data errors, repair data or route to quarantine instead of pointless retries |
| **Router** | Route based on error code/message type; preserve `eventId` and `correlationId` |
| **Filter** | Discard events that expired during wait windows to avoid executing stale actions |
| **Splitter** | Each part can retry independently; key on `eventId + partId` to avoid partial duplicates |
| **Aggregator** | Retrying one part can send duplicates to the group; manage correlation and duplicate suppression |
| **Gateway** | Caller may time out even though recovery captured the error; define clear ACK/status contracts |
| **Delayer** | Release failures have their own retry/error channel, distinct from handler Retry Advice |

A flow with Splitter → multiple handlers → Aggregator needs an error path for **each element** and clear group completion rules. If one element goes to a DLQ, the Aggregator can wait forever unless a timeout/release strategy handles missing elements.

## 12. Backoff, Timeouts, and Thread Starvation Risk

`FixedBackOffPolicy` in the example is a basic policy. When a partner experiences widespread transient errors, many requests retrying in lockstep after 100 ms create repeated traffic spikes. Consider **exponential backoff and jitter** at the right retry layer, bounded by a ceiling and attempt cap.

| Component | Timing impact |
| --- | --- |
| `RetryTemplate` with synchronous backoff | Holds the handler thread while waiting for the next attempt |
| `ExecutorChannel` | Decouples producer thread from handler; downstream failures need an async error flow |
| `Gateway.replyTimeout` | Caller may stop waiting before all retries finish |
| Delayer | Delays **before dispatching the message**; not a rate limiter or cron by itself |
| Scheduler/broker | Better suited for long-duration retries, large backlogs, or high durability needs |

### Total Time Budget Problem

Suppose each API call has a 2-second timeout, up to 3 attempts, and 500 ms backoff between attempts:

\[
\text{approximate max duration} = 3 \times 2s + 2 \times 0.5s = 7s
\]

This estimate assumes each attempt hits the full timeout; real duration also depends on overhead, scheduling, connections, and load. If a Gateway waits only 3 seconds, the caller times out while retries continue running. Align request deadlines and the **retry budget** with the application contract.

For retries spanning minutes or hours, never hold a thread the entire time. Instead, move messages to a durable error/retry-wait queue or use a dedicated Delayer/rescheduling worker, depending on architecture.

## 13. Observability, Alerting, and Controlled Replay

A failure record should answer "which message?", "what error?", "how many attempts?", and "did an external side effect already happen?":

~~~text
flow=invoiceCreation
eventId=invoice:order-501:v1
correlationId=order-501
handler=invoicePartnerAdapter
exceptionType=java.net.SocketTimeoutException
attempts=3
recoveryChannel=orders.retry.exhausted
firstAttemptAt=2026-11-21T10:00:00Z
lastAttemptAt=2026-11-21T10:00:05Z
outcome=QUARANTINED
~~~

This is an **application-designed log format**, not fields automatically emitted by Spring Integration. Never log tokens, passwords, or sensitive payment data in payload logs.

Key metrics:

| Metric | Meaning |
| --- | --- |
| `handlerSuccessCount` | Messages processed successfully |
| `retryAttemptCount` | Total retry attempts |
| `retryExhaustedCount` | Messages exhausting all attempts |
| `errorChannelPublishFailures` | Times even recovery failed to send or persist the error |
| `deadLetterBacklog` | Unresolved messages sitting in the error store |
| `retryLatencyMs` | Elapsed time from first attempt to final outcome |
| `duplicateSuppressedCount` | Duplicate side effects prevented by idempotent consumers |

### Safe Replay Procedure

1. Read error details and classify the root cause: bad data, bad config, overloaded partner, or indeterminate outcome.
2. Check the outcome at the target system using `eventId`; never assume the prior attempt failed just because the caller timed out.
3. Fix data or configuration; confirm the new retry policy.
4. Replay using the exact same **idempotency key** when retrying the same business operation.
5. Update error-store status via an appropriate transaction/reconciliation step; monitor post-replay effects.

Never run unbounded auto-replays, never delete failure records before processing is verified, and never mint a fresh event ID merely to bypass duplicate checks.

## 14. Decision and Troubleshooting Matrix

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| `send()` throws immediately | Synchronous handler failed with no recovery or recovery failed | Check Retry Advice, exception types, and channel |
| `send()` succeeds yet no business output appears | Recovery routed error to error channel; output produced no reply | Inspect both success and error channels and ACK contract |
| Global `errorChannel` is empty | Error traveled synchronously, or recoverer used a custom channel | Verify `ErrorMessage` publisher placement |
| Retries do not execute | Advice not attached to endpoint; failure happened in downstream async consumer | Attach advice to right handler or add consumer retry |
| Handler invoked 9 times instead of 3 | Two retry layers both configured for 3 tries | Define one retry owner and total budget |
| Error queue grows continuously | Prolonged partner outage, invalid data, or unconsumed DLQ | Alert, classify errors, and drain backlog |
| HTTP retry creates two invoices | Timeout after side effect with missing idempotency | Enforce event keys at target service and reconcile |
| Error handler only logs then message is lost | Non-durable error channel or logging | Use a durable dead-letter store and replay process |
| Gateway times out before retries finish | `replyTimeout` shorter than retry budget | Switch to async ACK or adjust contract |

## 15. Practice Exercises and Self-Check Questions

1. Configure `RequestHandlerRetryAdvice` for up to 3 attempts. Fail the first two attempts and succeed on the third; assert `orders.success` gets one result and the error queue is empty.
2. Make the handler always fail and verify one `ErrorMessage` appears on `orders.retry.exhausted` after three attempts.
3. Remove the recovery callback. Compare the exception reaching the caller on `DirectChannel` against the behavior with a callback.
4. Replace the error queue with a `DirectChannel` and a `ServiceActivator` that persists failures durably; make the error store throw an exception and trace the impact back to the message source.
5. Replace the handler with a consumer behind an `ExecutorChannel`, and explain why an error channel/publisher at the async boundary is essential.
6. Configure two retry layers with 3 tries each, measure total service calls, then redesign so only one layer owns retries.
7. Simulate an HTTP timeout after the partner already processed the request. Use `eventId`/idempotency key to prevent creating two invoices.
8. Create a non-retryable error such as a missing order code in the payload and route it to quarantine immediately without waiting through 3 attempts.
9. Add `correlationId` and `partId` after a Splitter; replay one element and verify whether the Aggregator sees a duplicate.
10. Set Gateway `replyTimeout` shorter than the total retry budget; build an async ACK API and status-query channel so clients do not mistake a timeout for a business failure.

**Self-check questions:** Why does the global `errorChannel` not automatically catch every exception on a `DirectChannel`? How do `RetryTemplate` and `ErrorMessageSendingRecoverer` differ in responsibility? If the recoverer sends the error successfully, what might the caller observe? Why is the `QueueChannel` in the test not a durable dead-letter store? At what stage can retries create duplicate side effects? When using a Gateway, how do you distinguish waiting timeout from a failed business operation?

## References

- [Spring Integration Reference — Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): `RequestHandlerRetryAdvice` and `ErrorMessageSendingRecoverer`.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, error channels, and sync/async boundaries.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): attaching advice to handlers in `IntegrationFlow`.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): reply timeouts and request/reply flows.
- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): difference between Delayer release retry and handler retry.
- [Spring Retry Reference](https://docs.spring.io/spring-retry/reference/): `RetryTemplate`, retry policies, backoff, and recovery.
