# Recoverer After Retries Are Exhausted

**Chapter:** Reliability  
**Lesson:** Recoverer after retries are exhausted  
**Module:** Spring Integration Adapters  
**Scope:** Designing and implementing message-handling strategies when an adapter or message handler has retried the configured number of times and still failed; covers `RequestHandlerRetryAdvice`, Spring Retry, `RecoveryCallback`, `ErrorMessageSendingRecoverer`, `MessageChannel`, dead-letter flows, idempotency, acknowledgement, and operational auditing.

## 1. The problem to solve

A Spring Integration flow often communicates with external systems: HTTP APIs, SFTP, JMS, AMQP, Kafka, filesystems, or databases. Those connections can fail temporarily due to timeouts, overload, brief network drops, or server errors. **Retry** gives the system a chance to recover without manual intervention.

However, what if all configured retry attempts are exhausted and the operation still fails?

- If it merely throws an exception, an upstream adapter may roll back, redeliver, or stop processing depending on configuration.
- If it logs and ignores the error, the message risks being lost from a business perspective.
- If it sends the message to an error channel with no durable consumer, the failure can still go unhandled.
- If it keeps retrying forever, a poison message can tie up threads, overload downstream systems, or create a loop.

**Recoverer** is the step that decides **what to do after retries are exhausted**. It does not mean the request itself succeeded. A proper recovery strategy preserves failure details, chooses where to store/return errors or route to a DLQ, ensures proper acknowledgement state, and provides a controlled remediation or replay path.

### 1.1. Illustrative scenario

A flow receives files via SFTP, transforms each record into a message, and sends it to a partner's HTTP API:

~~~text
SFTP inbound adapter
    -> transform/validate
    -> MessageChannel
    -> HTTP outbound gateway / handler
    -> partner API
~~~

The partner API times out. The system tries three times in total. After the third attempt, if it still times out, the flow must create a **failure record** containing the message ID, source file, correlation ID, last error, and status **`RETRY_EXHAUSTED`**, then act per policy: save to a failure store, route to a dead-letter flow, or escalate to operations.

Crucially, retry and recovery are **two distinct phases**:

1. **Retry:** Repeat the same operation under a bounded policy.
2. **Recovery:** Produce a terminal decision once attempts run out or the error is deemed non-retryable.

## 2. Learning objectives

After this lesson, learners can:

1. Explain the relationship among `RetryTemplate`, `RequestHandlerRetryAdvice`, `RecoveryCallback`, and `ErrorMessageSendingRecoverer`.
2. Distinguish **transient errors** from **permanent errors** to avoid retrying operations that cannot succeed.
3. Configure attempt counts, backoff, and recoverers on a Spring Integration message handler.
4. Choose the right recovery action: **propagate exception**, **error channel**, **durable failure store**, **dead-letter destination**, or **fallback** with a clear contract.
5. Analyze the impact of recovery on ack/nack, transactions, gateway responses, and broker redelivery.
6. Design idempotency, correlation, and replay across File/SFTP, HTTP, JMS, AMQP, Kafka, and JDBC adapters.
7. Build test matrices and observability metrics for retry exhaustion without leaking payloads, credentials, or sensitive data.

## 3. Distinguishing error-handling layers

| Component | Function | Does not automatically guarantee |
| --- | --- | --- |
| **Message handler** | Executes business logic or calls an external system | Does not manage durable retry on its own |
| **RetryTemplate (Spring Retry)** | Decides attempt count, retryable exceptions, and wait times | Does not automatically persist to DLQ or ack a broker properly |
| **RequestHandlerRetryAdvice** | Wraps retry around an eligible Spring Integration request handler | Does not automatically apply to every segment of the whole flow |
| **RecoveryCallback** | Decides the outcome once retries are exhausted | Does not provide persistence or auditing by default |
| **ErrorMessageSendingRecoverer** | Sends an `ErrorMessage` to a designated channel | Does not durably persist or create a broker DLQ by default |
| **Error channel / error flow** | Receives, routes, and handles error messages | Does not automatically mean the business failure is resolved |
| **Broker retry / DLQ** | Retry, redelivery, or dead-lettering handled by broker/container | Not equivalent to retry inside handler advice |
| **Transaction / acknowledgement** | Decides commit, rollback, or confirmation of the source message | Depends on the specific adapter, source, and configuration |

### 3.1. What state is retry exhaustion?

Suppose **maxAttempts = 3**. This value normally counts **the initial invocation as well**:

~~~text
Attempt 1: send HTTP -> timeout
Backoff 1: wait per configuration
Attempt 2: send HTTP -> timeout
Backoff 2: wait per configuration
Attempt 3: send HTTP -> timeout
RetryTemplate: does not attempt a 4th call
RecoveryCallback: invoked with final failure details
~~~

Thus **three attempts means one initial call plus two retries**, not one initial call plus three retries. If an exception is classified as **non-retryable**, recovery can execute without running all three attempts.

### 3.2. Retry exhaustion does not prove downstream did not process it

Especially for HTTP, JMS, or write operations: **a client timeout does not mean the server never received or committed the work**. The server may have processed it while the response was lost. Resending without idempotency can create the same order multiple times.

Therefore, recoverer design must answer two questions:

- **Technical state:** Was a valid response/ack received?
- **Business state:** Could the task have already been executed downstream?

When the two cannot be distinguished, an intermediate state such as **`OUTCOME_UNKNOWN` / `RECONCILIATION_REQUIRED`** is more honest than blindly concluding `FAILED`.

## 4. Retry-then-recover model

~~~mermaid
flowchart TD
    IN["Incoming Message"] --> H["Handler / Outbound Adapter"]
    H --> OK{"Succeeded?"}
    OK -->|Yes| DONE["Continue flow / reply"]
    OK -->|No| CL{"Exception retryable?"}
    CL -->|No| REC["RecoveryCallback"]
    CL -->|Yes| N{"Attempts left?"}
    N -->|Yes| WAIT["Backoff per policy"]
    WAIT --> H
    N -->|No| REC
    REC --> CH{"Recovery policy"}
    CH -->|Throw error| PROP["Upstream exception / rollback per config"]
    CH -->|Durable| STORE["Failure store / DLQ / incident"]
    CH -->|Valid fallback| FALL["Alternative result under contract"]
    STORE --> VERIFY["Verify persistence + source state"]
    PROP --> VERIFY
    FALL --> VERIFY
~~~

The diagram illustrates logical decisions. **A specific implementation typically chooses one explicit recovery path per failure**, rather than treating throwing and swallowing exceptions as equivalent outcomes.

### 4.1. Naming each milestone accurately

| Milestone | Example state | Interpretation |
| --- | --- | --- |
| Before send | `RECEIVED` | Message received by adapter per source mechanics |
| Handler fails first time | `RETRYABLE_FAILURE` | Can retry if classified as transient |
| Waiting for retry | `RETRY_SCHEDULED` | Cannot yet be considered complete |
| Attempts exhausted | `RETRY_EXHAUSTED` | Handler has no successful result |
| Recoverer writes record | `RECOVERY_PERSISTED` | Failure record saved durably; business task still unresolved |
| Post-incident handling | `REPLAY_REQUESTED` | Approved for resend per runbook |
| Downstream confirms | `DELIVERED` / `RECONCILED` | Evidence of matching outcome obtained |
| Outcome unclear | `OUTCOME_UNKNOWN` | Requires reconciliation; avoid blind resending |

**`RECOVERY_PERSISTED` does not mean `DELIVERED`.** That distinction is central when building reliable adapters.

## 5. Three main choices after retry

### 5.1. Propagate the exception

If no recovery callback is configured, or the callback intentionally rethrows, the failure propagates back to the caller/adapter depending on how the handler was invoked.

Appropriate when:

- The inbound adapter has reliable transactions or rollback/redelivery mechanisms.
- You want the broker/container policy to decide retry/DLQ.
- A gateway needs to return a failure rather than silently treating the transaction as handled.
- The failure record could not be persisted durably.

**Risk:** If upstream does not manage errors, threads may fail, messages may be lost, or infinite redelivery loops may form. Never pick propagation just to "let Spring handle it."

### 5.2. Publish an ErrorMessage and process in an error flow

`ErrorMessageSendingRecoverer` forwards the post-retry failure to a dedicated **MessageChannel** for recovery. The error flow must handle:

1. Receiving the final exception and original message/metadata if accessible.
2. Identifying root cause, destination, correlation, and outcome status.
3. Writing the failure to a DB, queue, or DLQ **with appropriate durability guarantees**.
4. Deciding whether the source message can be acknowledged only after persisting succeeds.
5. Providing replay runbooks, alerts, and auditing.

**Note:** `ErrorMessageSendingRecoverer` itself only **sends** an `ErrorMessage`. An in-memory `DirectChannel` is not a durable queue. If the error flow merely logs and returns, the source message may be treated as handled in some configurations while the business work remains undone.

### 5.3. Intentional fallback

`RecoveryCallback` may return an alternative result **if** the handler/gateway contract permits it—for example:

- Returning a cached snapshot for non-sensitive reads with an explicit stale-data policy.
- Transitioning task state to **`PENDING_RECONCILIATION`**.
- Returning a result indicating a temporary error without faking success.

Never return `null` or a fake "success" object by default to mask failures. For a **request-reply gateway**, ensure the caller receives a timely, properly typed reply/error, because a recoverer that **sends an `ErrorMessage`** usually does not produce a business reply for the gateway.

## 6. Errors to retry vs. errors not to retry

| Error group | Examples | Handling approach |
| --- | --- | --- |
| **Transient infrastructure** | Connection reset, temporary timeout, brief DNS/network disruption | Bounded retry with backoff |
| **Remote overload** | HTTP 429, certain HTTP 503s | Retry if API contract allows; honor `Retry-After`/rate limits |
| **Temporary database contention** | Deadlock or temporarily exhausted connection pool when operation is safe to repeat | Retry by error type and transaction |
| **Permanent input error** | Invalid JSON, missing required field, schema mismatch | Do not retry pointlessly; route to quarantine/failure |
| **Authentication/authorization** | Wrong credentials, 401/403 from permission config | Usually do not retry in tight loops; alert config/security owners |
| **Business-level not found** | Resource does not exist and no eventual consistency is promised | Usually do not retry; return business error |
| **Idempotency conflict** | Request exists with same key but different payload | Do not retry as transient; reconcile |
| **Downstream outcome unknown** | Timeout after sending payment command | Query status by idempotency/correlation before replaying |

Do not assume all **5xx** codes are safe to retry: you must know whether the endpoint has side effects and check the partner contract. Even **4xx** codes can have protocol/application-specific retry exceptions; final decisions depend on API documentation and risk.

### 6.1. Traversing causes properly

In Spring Integration, an underlying error may be wrapped in `MessagingException` or an adapter exception. The retry policy needs to know whether to inspect the **cause chain**.

For example: a service throws `TemporaryPartnerException`, but the handler throws `MessageHandlingException` wrapping it. If the policy only checks the outer exception class, a transient error can be misclassified.

Never enable "retry all `Throwable`" to compensate for not understanding wrappers. Define explicit exception groups and test both direct and wrapped forms.

## 7. Java DSL: configuring RequestHandlerRetryAdvice

This example uses **Spring Integration Java DSL** with **Spring Retry** to illustrate attaching advice to a handler. Verify package names and overloads against your project's Spring Integration/Spring Retry versions; business components `PartnerSender` and `FailureArchive` are application-implemented.

### 7.1. Configuring retry and a recovery channel

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.MessageChannel;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class PartnerReliabilityConfiguration {

    @Bean
    public MessageChannel partnerRecoveryChannel() {
        return new DirectChannel();
    }

    @Bean
    public RequestHandlerRetryAdvice partnerRetryAdvice(
            @Qualifier("partnerRecoveryChannel") MessageChannel recoveryChannel) {

        // 3 attempts = initial invocation + up to 2 retries.
        Map<Class<? extends Throwable>, Boolean> retryable = Map.of(
                TemporaryPartnerException.class, true);

        SimpleRetryPolicy policy = new SimpleRetryPolicy(
                3, retryable, true /* traverse causes */);

        ExponentialBackOffPolicy backoff = new ExponentialBackOffPolicy();
        backoff.setInitialInterval(500L);
        backoff.setMultiplier(2.0);
        backoff.setMaxInterval(5_000L);

        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(policy);
        template.setBackOffPolicy(backoff);

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(template);
        advice.setRecoveryCallback(
                new ErrorMessageSendingRecoverer(recoveryChannel));

        return advice;
    }

    @Bean
    public IntegrationFlow outboundPartnerFlow(
            PartnerSender partnerSender,
            RequestHandlerRetryAdvice partnerRetryAdvice) {

        return IntegrationFlow.from("partnerOutboundRequests")
                .handle(partnerSender, "send",
                        endpoint -> endpoint.advice(partnerRetryAdvice))
                .get();
    }
}
~~~

**Explanation:**

- `RetryTemplate` orchestrates retries; `SimpleRetryPolicy` caps attempts and eligible exception classes.
- `ExponentialBackOffPolicy` sets growing wait intervals, helping avoid hammering a failing system.
- `RequestHandlerRetryAdvice` wraps invocations of the advised **message handler**.
- `ErrorMessageSendingRecoverer` runs when the policy triggers recovery; it sends an `ErrorMessage` to `partnerRecoveryChannel`.
- `PartnerSender.send(...)` is an **application-owned service method**; the sample does not prescribe a specific HTTP/SFTP protocol.
- Returning from the recoverer after sending the error may cause the handler invocation to look complete in some flows; **the business task still has not succeeded**. Clarify source and caller semantics before enabling.

### 7.2. Example business handler

~~~java
public class TemporaryPartnerException extends RuntimeException {
    public TemporaryPartnerException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class PartnerSender {
    private final PartnerApiClient apiClient;

    public PartnerSender(PartnerApiClient apiClient) {
        this.apiClient = apiClient;
    }

    // Method invoked by Service Activator in IntegrationFlow.
    public void send(String payload) {
        try {
            apiClient.submit(payload);
        }
        catch (PartnerTimeoutException ex) {
            throw new TemporaryPartnerException(
                    "Partner temporarily unavailable", ex);
        }
        // Validation, auth, and business conflict errors must be classified separately;
        // do not collapse every exception into TemporaryPartnerException.
    }
}
~~~

`PartnerApiClient` and `PartnerTimeoutException` are illustrative domain types, **not built-in Spring Integration APIs**. In real projects, HTTP/JMS/SFTP clients throw specific exceptions; your error classifier must match actual exception types and external system contracts.

### 7.3. Recovery handler must persist failures durably

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class PartnerRecoveryHandler {
    private final FailureArchive archive;

    public PartnerRecoveryHandler(FailureArchive archive) {
        this.archive = archive;
    }

    @ServiceActivator(inputChannel = "partnerRecoveryChannel")
    public void onRecovery(ErrorMessage errorMessage) {
        Throwable failure = errorMessage.getPayload();

        Message<?> original = failure instanceof MessagingException me
                ? me.getFailedMessage()
                : errorMessage.getOriginalMessage();

        // Must actually persist durably + coordinate source transaction/ack.
        // Archive is application-implemented and guards sensitive data.
        archive.persist(original, failure);
    }
}
~~~

`FailureArchive` is a **project-implemented business interface**, not provided out of the box by Spring Integration. The handler must clearly define how payloads/references are preserved, durability guarantees, deduplication keys, the archive's own error policy, and replay support.

**Testing note:** Different versions and error paths can wrap exceptions in different `MessagingException` subclasses. Never assume the original message always lives in the same field; if it cannot be found, raise an investigable error rather than persisting an incomplete failure record and treating it as success.

### 7.4. Never use a recoverer just to log

~~~java
// Anti-pattern in any flow that must guarantee zero message loss.
@ServiceActivator(inputChannel = "partnerRecoveryChannel")
public void logAndForget(ErrorMessage error) {
    log.warn("Delivery failed", error.getPayload());
    // No durable storage, no DLQ, no processing state.
}
~~~

If upstream acks the message because the recovery callback completed, while the failure lives only in a hard-to-replay log line, the system can **lose business processing capability** even though an error was logged.

## 8. Custom RecoveryCallback and rethrow strategies

`RequestHandlerRetryAdvice` can use a custom `RecoveryCallback` instead of `ErrorMessageSendingRecoverer`. Distinguish three contracts:

1. **Return replacement data:** Appropriate only when the caller understands it as a fallback and the return type is valid.
2. **Persist failure then return:** Appropriate only when the failure store is durable and ack/commit semantics permit treating the source message as accepted for later handling.
3. **Throw an exception:** Appropriate when transaction rollback is needed or the source should decide redelivery.

~~~java
advice.setRecoveryCallback(context -> {
    Throwable lastFailure = context.getLastThrowable();
    if (lastFailure == null) {
        throw new IllegalStateException("Retry ended without a failure");
    }

    // In flows requiring upstream rollback or nack,
    // throw an exception preserving the cause instead of silently returning null.
    throw new IllegalStateException(
            "Outbound handler exhausted retry attempts", lastFailure);
});
~~~

This snippet illustrates **a callback that intentionally propagates errors**. Where upstream catches the exception, whether rollback happens, and whether the source redelivers depend on the adapter. Do not use this callback if the real requirement is persisting failures and acking after durable storage.

### 8.1. RecoveryCallback is not a fourth retry handler

The callback receives `RetryContext` with retry metadata (including the last failure). It is not an automatic extra retry attempt. If the callback calls an external API again without idempotency/caps, you have created a **hidden retry path** that makes external call counts hard to track.

### 8.2. Choosing the final action by source

| Source | Typical considerations |
| --- | --- |
| HTTP request-reply gateway | Return a contracted failure; do not swallow errors and leave caller to time out needlessly |
| JMS/AMQP inbound | Ack/rollback/redelivery/DLQ must be verified against listener container |
| Kafka inbound | Consumer offset commit/seek/error handling is not the same as handler retry advice |
| File/SFTP polling | No equivalent broker ack; requires persistent filters, move/quarantine, and file state |
| Database polling | Row locking, transactions, processing status, and duplicates on next poll |
| In-memory `DirectChannel` | Errors may propagate synchronously; no durable storage by default |

## 9. How does a recovery channel differ from the global errorChannel?

Spring Integration supports **error channels** and `ErrorMessage` mechanics where applicable. However, **a message emitted to a recovery channel** and **an exception caught by an error flow from a poller/asynchronous endpoint** do not always share the same origin.

### 9.1. Dedicated recovery channel

A dedicated channel like `partnerRecoveryChannel` has clear benefits:

- Pinpoints failures that **exceeded a specific handler's retry policy**.
- Applies partner-specific retention, alerting, quarantine, and replay rules.
- Separates file parsing errors from outbound HTTP errors and container errors.
- Makes attaching service owners and correlation metadata easy.

Drawback: you must ensure the subscriber/error flow is always active so it never becomes a message "black hole." `DirectChannel` has no built-in durability and may propagate recovery handler exceptions back to the caller.

### 9.2. Global errorChannel and the errorChannel header

Some endpoints route errors to the channel named in the `errorChannel` header or the global `errorChannel`, depending on dispatch mechanics and source. Never assume **every asynchronous exception** lands on a dedicated recovery channel if advice was not attached to the right handler, or that every synchronous exception turns into an `ErrorMessage` automatically.

Verify:

1. Which handler is actually wrapped by the advice?
2. Which thread executes the handler?
3. At what point is an `ErrorMessage` emitted?
4. To which channel does the recoverer send?
5. Does that channel have a consumer, and what does it do if persistence fails?
6. Does upstream receive success or an exception after the recoverer finishes?

## 10. Retry advice does not mean retrying the whole flow

`RequestHandlerRetryAdvice` wraps the **configured handler**. If a flow is parse → transform → outbound call, advice on the outbound handler normally only retries that outbound step.

~~~text
SFTP source
  -> parser                 (outside handler retry)
  -> transformer            (outside handler retry)
  -> outbound HTTP handler  (RequestHandlerRetryAdvice attached)
  -> downstream
~~~

Benefit: avoids re-reading files and re-parsing all data for a transient partner API glitch. Limitation: upstream parse errors **do not automatically pass through the HTTP handler's recoverer**.

### 10.1. Synchronous and asynchronous boundaries

**`DirectChannel`** typically delivers messages synchronously on the caller's thread. **`ExecutorChannel`** or an asynchronous consumer/poller splits threads and exception propagation boundaries.

When placing advice:

- Confirm exceptions are thrown inside the **handler portion wrapped by advice**, not only in a later async callback.
- If an outbound gateway calls a remote API on the handler thread, retry can wrap that call.
- If a handler merely enqueues work and returns, later errors will not jump back into the already-completed invocation to retry.
- Clarify which retries belong to the application, broker, scheduler, consumer container, or remote client.

### 10.2. Request-reply gateways have their own contract

For an outbound gateway expecting a reply, if the recoverer sends an `ErrorMessage` and returns without producing a reply, the caller may get `null`, time out, or behave differently per endpoint configuration. **Never use a recovery channel as a substitute for a reply without designing an explicit error contract.**

An appropriate approach may be **throwing a structured exception so an inbound gateway returns HTTP 503**, or returning a business response describing pending processing if the application already persisted the request durably. The choice must match the caller's contract and timeout budget.

## 11. Retry policy must go with timeouts and backoff

If an HTTP call has a 30-second timeout and retries three times, one thread can be blocked for over 90 seconds plus backoff time. Configuring retries without a latency budget can exhaust thread pools during downstream outages.

### 11.1. Calculating the latency budget

~~~text
maxAttempts = 3
timeoutPerAttempt = 2 seconds
backoff = 0.5 seconds then 1 second

Approximate worst-case:
    3 * 2 seconds + 0.5 seconds + 1 second
  = 7.5 seconds

Excluding: serialization, scheduling, connect, DNS,
client/server timeout skew, and other overhead.
~~~

If an upstream gateway only waits 5 seconds, this configuration can cause the caller's request to expire **before the recoverer is ever invoked**. Align total retry time, timeouts, throughput, and SLAs.

### 11.2. Exponential backoff and jitter

Progressive backoff reduces load while downstream is failing. Jitter prevents clients from retrying in synchronized waves.

Do not assume an exponential backoff config adds **automatic jitter**; verify the exact Spring Retry policy chosen. In multi-instance deployments, evaluate jittered backoff per library capabilities and operational policy.

### 11.3. Retry storms and backpressure

If 100 consumers retry three times together, downstream load can multiply right during an incident. Combine:

- Reasonable concurrency limits / worker pool sizes.
- Circuit breakers and bulkheads where supported by architecture.
- Rate limiters or honoring `Retry-After`.
- Queue depth monitoring, dead-letter policies, and backpressure.
- Per-layer retry caps: handler, SDK, broker, and workflow.

Actual request counts can exceed a single layer's `maxAttempts` if the HTTP client or broker also retries on its own.

## 12. Stateful retry and broker redelivery

**Stateless retry** typically retries within **one handler invocation**; `RetryTemplate` holds state for the duration of that call. If an exception is thrown back to the broker/container after exhaustion, the broker may **redeliver the message**, starting a fresh retry cycle.

Example:

~~~text
JMS/AMQP broker redelivers up to 4 delivery attempts
RequestHandlerRetryAdvice maxAttempts = 3

If every delivery exhausts all handler retries:
    4 broker deliveries x 3 handler attempts
  = up to 12 downstream calls
~~~

This is an **illustrative model**, not a claim that every broker uses those defaults. Verify against listener, transaction, nack/requeue, and SDK retry configurations.

### 12.1. Is stateful retry needed?

Spring Retry offers a **stateful retry** model that tracks state by a message or transaction key for cases that must release exceptions to roll back transactions and retry upon redelivery. In Spring Integration, configuration may involve a **retry state generator** and `RetryContextCache` per version-supported APIs.

Notes:

- Choose a **stable, unique key** per business message; never use values that change on each delivery.
- In-memory retry contexts **do not persist across restarts by default**.
- Cache, concurrency, and redelivery must be tested; different brokers have different semantics.
- Do not enable stateful retry just for "better retries": it increases transactional and operational complexity.

### 12.2. Designate one primary retry owner

To keep attempt counts predictable and guarantee recovery, clearly specify:

- Which layer retries ultra-short connection blips?
- Which layer decides retry exhaustion?
- Which layer manages durable redelivery?
- Which layer routes messages to the DLQ?
- When a message returns, how are the same idempotency key and attempt lineage preserved?

Never let SDK, handler advice, Spring Kafka container, and broker all retry without an overall budget.

## 13. Interaction with transactions and acknowledgement

**This directly affects the risk of losing or duplicating messages.** After a recoverer sends an `ErrorMessage` and returns normally, the source consumer may treat the handler as complete. Yet whether **ack/commit/rollback actually occurs** depends on the adapter, listener container, transaction manager, thread boundaries, and application config.

### 13.1. Behavior matrix requiring verification

| Source/adapter | When recoverer finishes without throwing | Must verify |
| --- | --- | --- |
| JMS inbound | Container may commit/ack if overall processing looks successful | Transaction/session acknowledgement, redelivery policy, DLQ |
| AMQP inbound | Container may ack per config when handler returns normally | Ack mode, requeue/nack, DLX, and retry advice |
| Kafka inbound | Consumer/container may commit offset per processing/ack mode | Offset commit, container error handler, transactions, DLT |
| File inbound | No shared broker ack; file may still be skipped by filter or re-polled | File state, accept-once filter, move/quarantine, recovery |
| SFTP inbound | Poll/download and remote file lifecycle may be decoupled from HTTP delivery | Metadata store, filters, local staging, remote move |
| HTTP inbound | Caller needs proper status/reply/error | Timeouts, HTTP response, retries completing within deadline |
| JDBC polling | Record/transaction state decides whether it is read again | Row claim, locks, processed flags, rollback |

**Do not rely on the table to infer default behavior.** Its purpose is to push designers to **inspect real configurations** and write tests verifying ack/commit after recovery.

### 13.2. A safe approach when acking after exhaustion

~~~text
Inbound message
  -> handler retry
  -> exhaustion
  -> recovery handler
  -> write failure to durable store
  -> confirm persistence succeeded
  -> only then allow branch to finish per ack policy
~~~

If writing to the failure store fails, the recovery handler must **throw an exception or trigger the appropriate source policy**, rather than swallowing the error and letting the source commit. Failure persistence and source ack may not share a distributed transaction; design idempotency and reconciliation for the gap between those two steps.

### 13.3. When to let the broker manage the DLQ

If a JMS, RabbitMQ, or Kafka consumer already has a solid retry/commit/error-handler strategy at the **container/broker layer**, you may not need redundant `RequestHandlerRetryAdvice` on the handler, or you may restrict advice to very short retries.

Prefer **one clear authority for terminal failure decisions** and a way to prove messages are neither lost nor unexpectedly duplicated.

## 14. Dead-letter and quarantine: designing the failure record

A **dead-letter queue (DLQ)** or **quarantine store** holds messages that failed after retries so they can be analyzed, fixed, and replayed. Names vary by broker and architecture; `ErrorMessageSendingRecoverer` does not automatically create a DLQ on JMS/AMQP/Kafka.

### 14.1. Minimum failure envelope

~~~json
{
  "failureId": "fail-2026-11-23-0042",
  "messageId": "msg-84021",
  "correlationId": "order-7321",
  "sourceAdapter": "sftp-orders",
  "destination": "partner-http-api",
  "operation": "submit-order",
  "status": "RETRY_EXHAUSTED",
  "attempts": 3,
  "lastErrorType": "TemporaryPartnerException",
  "firstSeenAt": "2026-11-23T08:00:00Z",
  "lastAttemptAt": "2026-11-23T08:00:02Z",
  "payloadReference": "encrypted-object-ref:orders/msg-84021",
  "replayPolicy": "manual-after-reconciliation"
}
~~~

This is an **illustrative business schema**, not automatically generated by `ErrorMessageSendingRecoverer`. The **`attempts`** field should come from a reliable source when accuracy matters; never hardcode 3 if a non-retryable exception ran only once.

### 14.2. Why use payloadReference?

The original payload may contain personal data, secrets, large files, binaries, or references to deleted objects. Instead of logging the full payload, store:

- An encrypted copy in a durable store with proper access control.
- Reference and checksum to verify integrity.
- Message ID / file ID / business key to reconstruct the task.
- Necessary headers and schema/contract version.

Never log raw `Authorization` headers, cookies, access keys, SFTP passwords, or full sensitive business payloads.

### 14.3. How does quarantine differ from DLQ?

Quarantine typically emphasizes **data remediation or review** before resending. A DLQ is usually the broker or application mechanism **holding failed messages**. Both require:

1. Owner, retention, and read permissions.
2. Processing state.
3. Approved, audited replay path.
4. Dead-letter message ID linked to the source message ID.
5. Loop protection when replays keep failing.
6. Cleanup or archiving per data retention rules.

## 15. Idempotency: protecting against retry and replay

For operations with side effects, **idempotency** is just as important as retry. A request that succeeded before its response was lost may be resent. Without downstream deduplication, you can create duplicate orders, payments, or files.

### 15.1. Idempotency key example

~~~text
Business operation: create-payment
Idempotency key: payment-tenant42-order7321-v1

Attempt 1 -> timeout after send
Attempt 2 -> same idempotency key
Attempt 3 -> same idempotency key
Recovery -> OUTCOME_UNKNOWN
Reconciliation -> query result using same business key
Replay if needed -> still same operation key per contract
~~~

The key must bind to the **business operation**, not a new UUID generated on each retry. Behavior when a body changes under the same key must be explicitly defined (usually conflict detection).

### 15.2. Deduplication layers

| Layer | Control |
| --- | --- |
| Inbound adapter | Persistent filters, source checkpoints, dedup keys |
| Spring Integration flow | `MetadataStore`, Idempotent Receiver where fitting, correlation |
| Database | Unique constraints, upserts, transactional state machines |
| External HTTP API | `Idempotency-Key` or deduplicating API contract |
| Broker | Message keys, broker-level deduplication if supported |
| Replay tool | Preserve operation ID, log replay history |

Never claim **end-to-end exactly-once** merely because you used a single transaction or connector. Across SFTP → HTTP → DB → broker, you usually need **at-least-once + idempotency + reconciliation** rather than assuming a perfect distributed transaction.

## 16. Recovery per adapter

### 16.1. File and SFTP inbound

Specific risks involve source file state and processing progress:

- File was downloaded but processing did not finish.
- Poller filter recorded the file as already seen.
- File split into multiple messages; one message failed after retries.
- File was moved/archived at the wrong step and cannot be replayed.
- Multiple instances read the same file without coordination.

Designs should include **file ID/checksum, persistent accept-once state when appropriate, staging directories, per-record state, and quarantine**, without expecting HTTP retries to govern the remote SFTP file lifecycle.

### 16.2. HTTP outbound gateway or adapter

Specific risks:

- Timeout does not prove the server did not process the call.
- 429/503 may require retry with backoff and rate-limit compliance.
- 400/401/403 are usually unsuitable for repeated retries.
- Gateways owe callers a clear reply/error.
- Client SDKs may have built-in retries, increasing total attempts.

Recovery should distinguish **`REJECTED`**, **`TEMPORARY_UNAVAILABLE`**, and **`OUTCOME_UNKNOWN`**; when needed, query downstream state before replaying.

### 16.3. JMS and AMQP

Specific risks are **redelivery** and **acknowledgement**. Handler advice retries within the current delivery; the broker/container may deliver again if the transaction rolls back. If the recoverer swallows the error and the error flow does not persist durably, the source may ack the failed message.

Must test:

- Ack/commit when recoverer returns normally.
- Rollback/nack when recoverer or archive throws an exception.
- Broker DLQ routing after exceeding configured deliveries.
- Requeue policies, max redelivery, duplicates, and poison messages.

### 16.4. Kafka

Kafka has offsets and consumer groups; retry in a Spring Integration handler is not the same as retry in a **Spring Kafka listener container error handler**. Check which layer the endpoint actually uses and under what configuration offsets commit.

Verify:

- When the recoverer completes, does the offset commit?
- When errors propagate, does the consumer seek/redeliver or send to DLT per design?
- Do transactions and the DLT producer provide required guarantees?
- Does replay keep the same business key and prevent duplicate side effects?

### 16.5. JDBC / database polling

Specific risks involve row locks and record states:

- Record is claimed, then the external API fails.
- Transaction rollback causes the record to reappear.
- Persisting failure and marking processed live in two separate transactions.
- Competing pollers contend for the same row.

Design **explicit state transitions**: `NEW` → `CLAIMED` → `SENT` or `RECOVERY_PENDING` → `REPLAYED`/`RECONCILED`. Use database locks, unique constraints, and transactions as supported in practice.

## 17. Recovery handlers can fail too

Never assume the error flow always succeeds. The failure store may lose connectivity, the DLQ broker may be overloaded, or the failure schema may error.

### 17.1. Fail-safe rule

If recovery fails to persist durably yet the recoverer returns normally, you risk **acking the source before the message has a safe copy**. When archiving fails, the system needs a clear decision:

- Propagate the exception so upstream rolls back/redelivers when backed by a proper transaction.
- Route to an alternate verified durable persistence channel.
- Pause intake cleanly, alert, and leave the message at the source.

Never "catch Exception and log" in a recovery handler just to protect throughput at all costs.

### 17.2. Avoiding recursion and error loops

~~~text
Outbound failure -> recoverer -> recoveryChannel
Recovery handler -> failure store timeout
Never allow an infinite loop:
    retry recovery -> same recoverer -> same channel -> ...
~~~

The recovery path needs its own retry policy, clear bounds, and a **final stopping point** such as alerting + preserving source state if persistence fails. Error-flow retries must not blindly loop back into the outbound handler without preconditions and idempotency.

## 18. Measurement and observability

Retry exhaustion must be a **first-class event in reliability observability**, not just an exception stack trace.

### 18.1. Essential metrics

| Metric | Meaning |
| --- | --- |
| `adapter_attempts_total` | Total handler attempts |
| `adapter_retry_total` | Retry attempts after the initial call |
| `adapter_retry_exhausted_total` | Messages that exhausted retries |
| `adapter_recovery_persisted_total` | Failure records persisted successfully |
| `adapter_recovery_failed_total` | Failures along the recovery path |
| `adapter_dead_letter_depth` | Records/messages awaiting handling |
| `adapter_replay_total` | Replay executions |
| `adapter_reconciliation_pending` | Tasks with unknown outcomes |
| `adapter_end_to_end_latency` | Time from source to final outcome |
| `adapter_source_lag` | Queue/file/polling source lag |

Group metrics by **adapter, dependency, error category, environment, and result**. Never use message ID or user ID as high-cardinality metric labels; keep correlation IDs in access-controlled traces/logs.

### 18.2. Suggested structured log

~~~json
{
  "event": "adapter.retry.exhausted",
  "flow": "sftp-to-partner-http",
  "sourceMessageId": "msg-84021",
  "correlationId": "order-7321",
  "adapter": "partner-http",
  "errorCategory": "TRANSIENT_TIMEOUT",
  "attemptsObserved": 3,
  "recoveryDecision": "PERSIST_FOR_RECONCILIATION",
  "recoveryStatus": "PERSISTED",
  "occurredAt": "2026-11-23T08:00:03Z"
}
~~~

This is an example **application-defined log schema**; Spring Integration does not emit all these fields automatically. Never log raw payloads containing PII or `Authorization` headers.

### 18.3. Critical alerts

- Retry exhaustion spiking relative to baseline.
- Failure store/DLQ not receiving messages or lacking consumers.
- Continuously rising dead-letter depth and max age.
- Recovery handler failures.
- Downstream unresponsive while upstream continues acking.
- Repeated replay failures for the same business key.
- Rising auth/permission errors (likely misconfiguration—should not retry pointlessly).
- Excessively high `OUTCOME_UNKNOWN` ratio.

## 19. Testing: go beyond counting invocations

A strong test suite proves **happy paths, transient errors, permanent errors, exhaustion, recovery, acks, and replay**.

| Test case | Setup | Expectation |
| --- | --- | --- |
| Immediate success | First call succeeds | Handler called once, recoverer does not run |
| Transient then success | Two failures, 3rd succeeds | 3 attempts, no failure record |
| Retries exhausted | 3 retryable timeouts | 3 attempts, recoverer runs once |
| Non-retryable error | Validation/auth failure | No pointless retries, routes per policy |
| Wrapped exception | `MessagingException` wrapping transient cause | Policy matches cause per `traverseCauses` config |
| Durable recovery save | Store succeeds | Failure envelope has right correlation, no logged secrets |
| Recovery store fails | Store throws exception | No silent ack; source behaves per contract |
| Handler with side effects | Response lost after server commit | No duplicates; idempotency/reconciliation handles it |
| Reply-expecting gateway | Handler exhausts | Caller gets contracted error/fallback without unexpected hang |
| Broker redelivery | Source rollback/requeue | Total attempts across all layers stay bounded |
| Approved replay | Downstream fixed then replayed | Business key preserved; outcome reconciled |
| Concurrent duplicates | Two messages with same business ID | Only one valid business effect per design |

### 19.1. Verifying maxAttempts

A common mistake is expecting **4 calls** when **`maxAttempts = 3`** is configured. Assert actual handler invocation counts and recoverer invocation counts. For non-retryable exceptions, expected attempts may be fewer than 3.

### 19.2. Verifying real ack/offset behavior

Never just mock `RecoveryCallback` and conclude the system loses zero messages. Run integration tests against real-like sources (e.g., test brokers or isolated file directories) to observe:

1. Source message is received.
2. Handler retries the exact configured count.
3. Recovery record is persisted.
4. Container ack/offset/file state is correct after recovery.
5. If the recovery store fails, the source message does not vanish without a durable record.

### 19.3. Timing tests

Backoff introduces real delays. In unit tests, use very short backoff settings or your library version's test clock/backoff mechanism. In integration tests, measure total duration and end-to-end timeouts; avoid brittle assertions tied to exact millisecond timings.

## 20. End-to-end scenario: SFTP to HTTP

A system polls order files every minute from SFTP and calls a carrier's HTTP API.

### 20.1. Flow design

~~~mermaid
flowchart LR
    S["SFTP inbound + file metadata"] --> P["Parser + schema validation"]
    P --> ID["Business ID / idempotency key"]
    ID --> C["MessageChannel"]
    C --> H["HTTP outbound handler + retry advice"]
    H -->|Success| DONE["Record delivered"]
    H -->|Exhaustion| REC["ErrorMessageSendingRecoverer"]
    REC --> ER["Dedicated recovery channel"]
    ER --> STORE["Durable failure store"]
    STORE --> OPS["Controlled reconciliation / replay"]
~~~

### 20.2. Record states

~~~text
NEW
  -> VALIDATED
  -> SENDING
  -> DELIVERED
  -> RETRY_EXHAUSTED
       -> RECOVERY_PERSISTED
       -> OUTCOME_UNKNOWN / REJECTED
       -> RECONCILIATION_REQUIRED
       -> REPLAY_APPROVED
       -> DELIVERED / CLOSED_WITH_REASON
~~~

Not every record passes through every state. A validation-invalid message can be quarantined **before handler retry**. An HTTP timeout needs outcome investigation before replay, whereas an explicit rejection can be closed per business rules.

### 20.3. Three scenarios

**Scenario A — Partner recovers:** HTTP times out on attempts 1 and 2, succeeds on attempt 3. No failure envelope created; success recorded; API idempotency holds per contract.

**Scenario B — Retries exhausted:** All 3 attempts time out; recoverer emits `ErrorMessage`; error flow persists failure durably; owner is alerted if backlog crosses threshold. Business task enters reconciliation rather than assuming permanent delivery failure.

**Scenario C — Failure store also fails:** If the recoverer cannot persist, the flow must execute its error-throwing/rollback policy or preserve source state per design. Never move the file to `DONE` or ack the source if doing so forfeits reprocessing.

### 20.4. Correlation from file to request

A record may carry:

~~~yaml
# Illustrative metadata for an integration contract
source:
  protocol: sftp
  fileId: file-20261123-17
  recordNumber: 42
message:
  messageId: msg-84021
  correlationId: order-7321
  businessOperation: create-shipment
  idempotencyKey: ship-tenant-a-order-7321
destination:
  protocol: https
  partner: logistics-service
failurePolicy:
  maxAttempts: 3
  onExhausted: persist-and-reconcile
~~~

This schema is a business requirement, not headers auto-generated by Spring Integration. Define how fields map into `MessageHeaders` and the failure store. Never use the filename alone as a deduplication key when a single file holds multiple records.

## 21. Runbook when retry exhaustion spikes

### 21.1. Initial triage

1. Identify affected flows: source, destination, endpoint, environment.
2. Classify the error: timeout, 429/503, auth, validation, network, or database.
3. Check handler attempt counts, final error, logs/traces, and start time.
4. Check downstream health, rate limits, dependency incidents, and credential expiry.
5. Confirm the recovery store/DLQ is healthy and not dropping messages.
6. Check source acks/commits, queue depth/lag, and active redelivery policies.

### 21.2. Remediation

- For transient outages: reduce concurrency/tune backoff, consider circuit breakers; do not increase retries endlessly.
- For auth/config issues: fix credentials or permissions under change control; stop repeating 401/403 calls.
- For validation errors: fix contract/parser or quarantine messages; never manually alter sensitive data without approval.
- For unknown outcomes: reconcile downstream state before replaying.
- For backlogs: process by priority and rate-limit replays to avoid recurring outages.

### 21.3. Closing the incident

Close only with evidence that:

- Downstream has recovered or the root fault is fixed.
- Failure records have been reconciled, replayed, or closed per policy.
- No messages with unknown status remain overlooked.
- Acks, offsets, or file states are consistent with the recovery store.
- Retry exhaustion rates have returned to acceptable baselines.
- Root cause, config changes, and regression tests have been documented.

## 22. Anti-patterns to avoid

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| Retrying all exceptions | Wastes cycles on schema/auth failures | Separate retryable and non-retryable |
| Confusing `maxAttempts=3` with 3 retries after first call | Misestimates load and latency | Count the initial attempt |
| Recoverer only logs and returns | Message may be acked with no copy for follow-up | Persist durably or propagate properly |
| Using `DirectChannel` as a durable DLQ | State lost if process stops | Use durable broker/store and verify writes |
| Retrying non-idempotent POST without a key | Creates duplicate orders/transactions | Idempotency key + reconciliation |
| Callback makes an uncontrolled 4th API call | Extra side effects outside retry policy | Keep recovery terminal and clean |
| Too many stacked retry layers | Retry storm and multiplied attempts | Unified budget across SDK/handler/container/broker |
| Retrying longer than gateway timeout | Caller times out before recoverer runs | Align latency budgets |
| Never testing recovery handler failure | Source may ack after persistence fails | Test rollback/nack/retention |
| Dumping all errors to global `errorChannel` | Hard to identify owners and retry exhaustion | Dedicated recovery route per flow |
| Forgetting async boundaries | Errors occur outside advice scope | Place retry on the right handler/thread boundary |
| Confusing `ErrorMessage` with business success | Caller/monitoring records wrong status | Separate terminal states and error contracts |
| Guessing Kafka offset/JMS ack behavior | Lost or duplicated messages | Integration-test each source |
| Replay generates new message ID as idempotency key | Loses deduplication across retries | Keep business operation key stable |
| Storing raw payloads/`Authorization` in DLQ/logs | Sensitive data leakage | Redaction, encryption, access controls |
| Retry exhaustion without an owner | DLQ grows unchecked | Alerts, SLAs, retention, runbooks |

## 23. Self-check questions

### Q1. What does `maxAttempts` equal to 3 mean?

**Answer:** Typically at most **three handler executions**, consisting of the initial attempt plus two retries, provided the policy classifies the exception as retryable. Non-retryable failures may enter recovery sooner.

### Q2. Does `ErrorMessageSendingRecoverer` create a dead-letter queue automatically?

**Answer:** No. It sends an `ErrorMessage` to a designated channel. The downstream error flow must persist it durably, publish to a DLQ, or handle it per policy; you must test what happens if the error flow itself fails.

### Q3. After retry exhaustion, should recovery always return `null`?

**Answer:** No. Returning normally may signal to upstream that the handler succeeded; for gateways it can drop the expected reply; for brokers it can trigger ack/commit. Explicitly choose propagate, persist-and-ack, or a contracted fallback.

### Q4. Does an HTTP timeout prove downstream did not create the order?

**Answer:** No. The server may have committed while the response was lost. Use an idempotency key and state reconciliation before replaying.

### Q5. Does `RequestHandlerRetryAdvice` retry parser errors from an earlier step?

**Answer:** Not by default. Advice wraps a **specific handler**; errors outside that handler's scope need their own error/retry strategy.

### Q6. Why can combining broker retry and handler retry be dangerous?

**Answer:** Each broker delivery can trigger a fresh handler retry cycle, multiplying total attempts across layers and increasing side effects. Define a total retry budget and a terminal DLQ cutoff.

### Q7. Does `RECOVERY_PERSISTED` mean the message was delivered?

**Answer:** Not yet. It only means the failure was durably recorded for follow-up. The business task still needs replay/reconciliation and proof of successful execution.

### Q8. When does a non-retryable exception still reach the recoverer?

**Answer:** When the retry policy determines it should not be retried and a recovery callback is configured; recovery can run after one attempt without consuming all `maxAttempts`. Check your exact policy and verify with tests.

## 24. Checklist for implementing a safe recoverer

1. **Right advice target:** Retry only the handler/outbound endpoint that actually needs it; identify sync/async boundaries.
2. **Right error classification:** Retry transient errors; avoid pointless loops on validation, auth, or conflicts.
3. **Right attempt count:** `maxAttempts` includes the initial call; account for SDK/container/broker retries too.
4. **Right timeouts:** Total attempts + backoff fit request SLAs and thread budgets.
5. **Sensible backoff:** Avoid retry storms; use jitter/rate limits where needed.
6. **Clear recovery:** Choose propagate, durable store/DLQ, or contracted fallback.
7. **Error channel has consumers:** Never leave recovery channels as unmanaged sinks.
8. **Verified durability:** Successfully sending an `ErrorMessage` is not enough; failure records must be durably persisted.
9. **Tested ack/commit:** Never guess JMS, AMQP, Kafka, or poller behavior.
10. **Idempotency:** Keep business keys stable across retries, broker redeliveries, and replays.
11. **Unknown outcomes:** Reconcile when downstream may have processed before timing out.
12. **Recovery-path failures:** Provide fail-safes and escalation without infinite retry loops.
13. **Observability:** Track exhaustion, recovery success/failure, backlog, lag, replays, and latency.
14. **Auditability:** Record correlation IDs, actual attempts, error categories, owners, and decisions.
15. **Security:** Redact secrets/PII, encrypt stored payloads, and restrict DLQ access.
16. **Controlled replay:** Define owners, approvals where needed, backpressure, and duplicate prevention.
17. **Realistic tests:** Cover success, transient recovery, exhaustion, non-retryable, archive failure, broker ack, and gateway reply.
18. **Runbook:** Document triage, retry/replay decisions, and incident closure criteria.

## 25. Summary

**A recoverer after retries are exhausted** transitions a message from a finite retry loop to a **terminal handling decision**. In Spring Integration, `RequestHandlerRetryAdvice` pairs with `RetryTemplate` to retry a handler; `RecoveryCallback` decides the next step, and `ErrorMessageSendingRecoverer` is an option to forward failures to a `MessageChannel` for follow-up.

Reliability comes not from high retry counts, but from **accurate error classification, sensible timeouts and backoff, preventing duplicate side effects, durable recovery, consistent ack/transaction semantics, and controlled replay**. When implementing File/SFTP, HTTP, JMS, AMQP, Kafka, or JDBC adapters, verify the exact failure boundary and source semantics. A message is safely handled after exhaustion when **either a durable failure record exists or upstream retains delivery responsibility**, all unknown outcomes are reconciled, and final outcomes can be observed, tested, and audited.
