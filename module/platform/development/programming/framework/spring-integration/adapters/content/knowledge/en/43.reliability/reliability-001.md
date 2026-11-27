# Retry Advice for Request Handlers

**Chapter:** Reliability  
**Lesson:** Retry advice for request handlers  
**Module:** Spring Integration Adapters  
**Scope:** Designing and operating retry mechanisms at the **message handler** in Spring Integration, coordinating with inbound/outbound adapters, gateways, pollers, and MessageChannels; distinguishing transient errors from permanent errors, handling backoff, recovery, idempotency, transactions, and monitoring evidence.

## 1. Why does a request handler need retry?

In an integration system, sending or receiving data over HTTP, SFTP, JMS, AMQP, Kafka, files, or databases can fail due to non-permanent causes: a connection drops briefly, a remote service is overloaded, a broker changes leader, a database experiences a deadlock, or a file transfer session closes mid-way. If all errors are ignored, messages may be lost; if all errors are retried, the flow may get stuck or cause duplicate processing.

**Retry advice for a request handler** is a way to place a retry mechanism right at the **message handling step**. In Spring Integration, the commonly used class is **`RequestHandlerRetryAdvice`**, combined with **Spring Retry `RetryTemplate`** to decide:

- Which errors can be retried?
- What is the maximum number of handler invocations?
- How long is the wait interval between attempts?
- If it still fails, should the error be rethrown or handed off to recovery?
- What impact does this retry have on acknowledgement, transactions, message ordering, and idempotency?

**Core principle:** Retry is not an operation to "call again whenever an error occurs." It is **an error-handling policy with clear boundaries**, placed on the right endpoint and governed by rules when final failure occurs.

### 1.1. Introductory scenario

An application receives a command to create a shipping request from JMS, transforms it into JSON, and calls a partner's HTTP service. The partner times out due to an unstable network.

~~~text
JMS inbound adapter
    -> transform payload
    -> DirectChannel
    -> HTTP outbound gateway
    -> result / error
~~~

If the HTTP handler times out, retry can help re-invoke it without requiring the producer to send a new message. However, if the partner **already created the request but the response was lost**, re-invoking may create two shipping requests. Therefore, retry must go hand in hand with an **idempotency key**, a timeout policy, and rules for verifying uncertain outcomes.

### 1.2. Learning objectives

After this lesson, learners can:

1. Pinpoint the exact location of `RequestHandlerRetryAdvice` in a Spring Integration flow.
2. Distinguish handler-level retry from retry at the poller, listener container, broker, or external caller.
3. Configure `RetryTemplate`, retry policy, exponential backoff, and recovery for an endpoint.
4. Classify transient, permanent, and **ambiguous outcome** errors instead of retrying everything.
5. Explain the relationship between retry, transactions, acknowledgement, error channels, and dead-letter handling.
6. Choose strategies suited for file/SFTP, HTTP, JMS/AMQP, Kafka, and JDBC.
7. Design metrics, logs, tests, and operational runbooks when retries are exhausted.

## 2. Reviewing related Spring Integration components

| Component | Role in the flow | Relation to retry |
| --- | --- | --- |
| **Message** | Payload and headers carrying the data contract | The same message may be processed again; headers do not automatically guarantee idempotency |
| **MessageChannel** | Connects endpoints | `DirectChannel` is typically synchronous; `ExecutorChannel` creates an asynchronous boundary |
| **Inbound channel adapter** | Receives data/events from an external system and creates messages | Has its own poll/ack/redelivery mechanism |
| **Outbound channel adapter** | Sends messages to an external system, typically with no application reply | Retry wraps the send operation in the handler if supported |
| **Outbound gateway** | Sends a request and receives a reply | Retry can repeat the entire request; watch out for remote side effects |
| **Service activator** | Processes a message using business methods | Advice can be attached to the corresponding endpoint |
| **Poller** | Triggers a receiving source on a schedule/trigger | Poller advice/transaction has a different boundary than handler advice |
| **Error channel** | Receives `ErrorMessage` when errors are routed to the error-handling flow | Does not automatically replace a retry policy |
| **`RequestHandlerRetryAdvice`** | Retries the handler's execution according to `RetryTemplate` | Does not automatically perform broker redelivery or message persistence |

A **gateway** differs from an **adapter** in its reply contract. In a gateway, the caller may be waiting for a response; in a one-way outbound adapter, the system typically only cares that the send side effect succeeded. The choice of recovery directly affects this contract.

### 2.1. Exception classes and where errors surface

An HTTP handler may throw `ResourceAccessException` on connection errors; another handler may wrap the root cause in a `MessagingException`. The retry policy needs to evaluate **the error thrown at the handler boundary**, sometimes including the cause chain. You should not rely solely on error message text or descriptive strings like "timeout".

### 2.2. The request handler is the processing boundary, not every point in the flow

Suppose:

~~~text
inbound adapter
  -> transform
  -> filter
  -> outbound HTTP handler [retry advice]
  -> output channel
~~~

If advice is placed on the **outbound HTTP handler**, Spring Integration will retry executing that handler according to the policy. It **does not mean** the entire inbound–transform–filter chain is re-run on every attempt. Errors in an upstream transformer or in another handler require separate mechanisms.

## 3. How does RequestHandlerRetryAdvice work?

`RequestHandlerRetryAdvice` belongs to Spring Integration's **request-handler advice** family. It works with `RetryTemplate`: each time message handling passes through the advice, the template decides whether to perform additional processing attempts when the handler throws an exception.

~~~mermaid
flowchart TD
    IN["Message arrives at endpoint"] --> AD["RequestHandlerRetryAdvice"]
    AD --> POL["RetryTemplate<br/>RetryPolicy + BackOffPolicy"]
    POL --> H["Message handler executes"]
    H --> Q{"Succeeded?"}
    Q -->|Yes| OK["Return reply / complete handler"]
    Q -->|Error| C{"Retryable and attempts remaining?"}
    C -->|Yes| WAIT["Backoff per policy"]
    WAIT --> H
    C -->|No| REC{"Recovery callback present?"}
    REC -->|Yes| RC["Execute recovery"]
    REC -->|No| EX["Throw error to caller boundary"]
    RC --> END["Outcome depends on callback"]
~~~

**The default targets retrying the current handler invocation.** In standard retry mode (stateless), attempts occur within the same processing execution, usually on the same thread and with the same message. When state needs to be preserved across broker redeliveries or separate transactions, you need to evaluate **stateful retry** and the source adapter architecture rather than assuming `RequestHandlerRetryAdvice` provides persistence by default.

### 3.1. Configuration components

| Component | Responsibility |
| --- | --- |
| `RequestHandlerRetryAdvice` | Attaches retry to an endpoint's request handler |
| `RetryTemplate` | Executes the attempt loop and handles recovery |
| `RetryPolicy` | Decides whether an exception is retryable, the attempt count, and stop conditions |
| `BackOffPolicy` | Decides the wait interval between attempts |
| `RetryContext` | Tracks the state of the retry operation |
| `RecoveryCallback` | Handles failure when retries are exhausted or the policy stops |
| `ErrorMessageSendingRecoverer` | An option to send the final error as an `ErrorMessage` to a channel |

**The attempt count includes the initial call.** If configured for a maximum of 4 attempts, there is typically **1 initial call + at most 3 retries**, not 4 additional retries.

### 3.2. Advice does not create durable retry

If the JVM dies during the second attempt, a stateless `RetryTemplate` does not automatically persist attempt history to a database for recovery. Whether the message re-enters the flow after restart depends on the inbound adapter, transaction/ack, broker, file filter, and storage design.

Therefore, you need to distinguish:

- **In-process retry:** Fast, close to the error, with backoff, but consumes a thread and loses state when the process stops.
- **Broker redelivery / durable retry:** The message is re-delivered via a broker/container or retry topic/queue, capable of surviving restarts if configured properly.
- **Application-level recovery:** Persists uncompleted requests in a durable store for later processing, with an owner and idempotency.

## 4. Placing advice on the right endpoint

In Java DSL, advice is typically attached to the handler's **endpoint configuration** via the endpoint's advice configuration method. Structural example:

~~~java
// Illustrative DSL: the handler invocation is wrapped by the advice.
return IntegrationFlow.from("outboundRequests")
    .handle(someOutboundHandlerSpec,
        endpoint -> endpoint.advice(requestHandlerRetryAdvice))
    .get();
~~~

This differs from placing advice on a poller or using the HTTP client's built-in retry. A flow with multiple handlers may require **different** retry policies:

~~~mermaid
flowchart LR
    SRC["Inbound Adapter"] --> T["Transformer"]
    T --> A["HTTP Gateway<br/>Retry: network transient"]
    A --> B["JDBC Handler<br/>Retry: DB transient"]
    B --> OUT["Result Channel"]
    E["Error/Recovery Channels"] -.-> A
    E -.-> B
~~~

Do not apply a single "retry all errors 10 times" policy across all endpoints: HTTP timeouts, JDBC constraint errors, and wrong SFTP credentials require different handling.

### 4.1. Synchronous and asynchronous boundary traps

**`DirectChannel`** invokes subscribers synchronously; exceptions can typically propagate to the caller within the same call stack. **`ExecutorChannel`** dispatches processing to an executor thread, creating an asynchronous boundary: the upstream caller may have already finished sending the message before the downstream handler fails.

Consequently:

- Retry advice on a downstream handler can still retry at that handler.
- Exceptions after an asynchronous boundary may route to an error flow rather than propagating back the way a synchronous caller expects.
- The source adapter's transaction/acknowledgement **is not automatically extended** across every asynchronous channel.
- You must clearly define at which boundary a message is marked as successfully processed.

### 4.2. Handler advice differs from poller advice

A poller triggers fetching messages from a source; for example, a file poller checks a directory every 5 seconds. **Poller retry** relates to the poll/receive operation, whereas **request-handler retry** relates to the handler logic after the message has already been fetched.

Do not treat retrying an outbound HTTP call as equivalent to **re-reading a file/SFTP message**. If the source needs to re-emit a message after a crash, you must design the accept-once filter, metadata store, transaction, or redelivery mechanism accordingly.

## 5. Classifying errors before writing a retry policy

A good policy starts by **defining retryable errors**.

| Error category | Examples | Typically appropriate decision |
| --- | --- | --- |
| **Transient network** | Connection reset, connect timeout, brief disconnect | Bounded retry, backoff, and timeout |
| **Rate limiting / overloaded service** | HTTP 429; HTTP 503 per remote contract | Wait per `Retry-After` when appropriate, rate limit |
| **Transient database** | Deadlock, serialization conflict, brief connection drop | Retry appropriate task/transaction if idempotent |
| **Broker failover** | Temporary session loss, reconnect during leader change | Client/container retry/reconnect policy |
| **Permanent client error** | Schema-invalid payload, invalid parameters, invalid resource | Do not retry indefinitely; fix data or code |
| **Authentication / authorization** | HTTP 401/403, token lacks permissions | Usually do not retry with same credentials; fix identity/permissions |
| **Configuration error** | Wrong SFTP credentials, invalid path, misconfigured exchange/queue | Do not retry aggressively; alert operations |
| **Conflict / duplicate** | Unique constraint, entity already exists | Verify business semantics; may treat as already completed if idempotent |
| **Ambiguous outcome** | Remote processed the request but response/ack was lost | Requires idempotency or status query before retrying |
| **Poison message** | Data that always causes the handler to throw an exception | Stop after a reasonable count, isolate to DLQ/quarantine |

**5xx errors are not automatically safe to retry.** A service may finish processing a request and then fail while returning the response. **HTTP POST is not inherently idempotent**; only retry when the API contract and deduplication mechanism support it.

### 5.1. Handling the cause chain

The Spring Integration layer may wrap the root cause in a messaging exception. If a retry policy only checks the outer exception class, it may miss `ResourceAccessException` or the underlying connection error. Conversely, configuring retry for **every `Exception`** may accidentally retry data errors, code bugs, or permission errors.

Classify based on **well-justified exception types**, inspect nested causes when appropriate, and add tests for the actual wrapped exceptions produced by the adapter.

### 5.2. A decision checklist before retrying

For each error group, ask:

1. Is the error likely to disappear if we wait and try again?
2. Does the handler invocation have side effects?
3. Do we know for sure that the remote **has not processed** the request?
4. If unknown, is there an idempotency key or status query mechanism?
5. Will retrying exceed the upstream deadline?
6. When retries are exhausted, will the message be redelivered, sent to a DLQ, or marked as completed?

If you cannot answer questions 2–4, **do not apply blind retry to operations that can create data or transfer money**.

## 6. Configuring RetryTemplate and backoff

Spring Retry provides `RetryTemplate`, which can combine a `RetryPolicy` and a `BackOffPolicy`. A common configuration for transient connection errors:

- Maximum of **4 attempts**.
- Initial backoff of **250 ms**.
- Double the wait interval after each failure.
- Cap the wait interval per attempt at **3 seconds**.
- Retry only identified exception classes, including nested causes when genuinely needed.

### 6.1. Java configuration for advice

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.web.client.ResourceAccessException;

@Configuration
public class RetryAdviceConfiguration {

    @Bean
    public RequestHandlerRetryAdvice httpNetworkRetryAdvice() {
        // 4 attempts TOTAL, including the initial invocation.
        var retryable = Map.<Class<? extends Throwable>, Boolean>of(
                ResourceAccessException.class, true);
        var retryPolicy = new SimpleRetryPolicy(
                4, retryable, true); // true: also inspect nested causes

        var backOff = new ExponentialBackOffPolicy();
        backOff.setInitialInterval(250L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(3_000L);

        var retryTemplate = new RetryTemplate();
        retryTemplate.setRetryPolicy(retryPolicy);
        retryTemplate.setBackOffPolicy(backOff);

        var advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(retryTemplate);
        return advice;
    }
}
~~~

**Explanation:** The illustrative policy only retries `ResourceAccessException` or a matching cause in the cause chain. It does not automatically retry HTTP 5xx or 429; if the remote API requires handling those, you must **selectively extend the policy** and design appropriately for `Retry-After`, idempotency, and overall timeout.

**Compatibility note:** The example uses Spring Integration and Spring Retry APIs common in the modern Spring ecosystem; imports, DSL builders, and overloads may vary by actual dependency version. Every configuration before production must be compiled and tested against the application's BOM/version.

### 6.2. What does exponential backoff do?

If timeouts occur because the remote is overloaded, retrying immediately can make things worse. Backoff spaces out attempts, helping prevent request storms.

~~~text
Attempt 1 -> error
  wait 250 ms
Attempt 2 -> error
  wait 500 ms
Attempt 3 -> error
  wait 1000 ms
Attempt 4 -> error or success
  retry quota exhausted, handle per recovery/exception
~~~

Consider **jitter** in backoff if multiple instances retry simultaneously: overly synchronized wait intervals can cause request spikes. You can use a backoff policy that supports randomization or an equivalent mechanism tested for your version of Spring Retry.

### 6.3. Retry budget and deadline

Suppose there are `N` attempts, a maximum per-attempt timeout `T`, and wait intervals `B₁ ... Bₙ₋₁`; the time before returning a result is approximately:

~~~text
Worst-case retry time ≈ N × T + sum(Bi) + overhead
~~~

Use the caller's deadline, gateway wait time, consumer poll/ack timeouts, and thread pool limits to choose `N` and backoff. An HTTP gateway with a 3-second caller timeout **should not** run a synchronous retry loop expected to take dozens of seconds without an asynchronous contract or appropriate response mechanism.

### 6.4. Retry is not a cure-all for timeouts

If the problem is an undersized HTTP pool, wrong DNS, misconfigured socket timeouts, or a network policy blocking traffic completely, increasing attempts only hides the cause and adds extra load. A retry policy must be paired with **timeouts, connection pools, concurrency limits, health checks, and circuit breakers** in the right places.

## 7. Attaching RequestHandlerRetryAdvice to an HTTP outbound gateway

The example below focuses on the **request handler** of an HTTP outbound gateway. A channel receives a message; the gateway makes an HTTP POST call; if a network error matching the policy occurs, the handler invocation is retried. On success, the result is sent to the next channel.

### 7.1. Java DSL configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.integration.http.dsl.Http;

@Configuration
public class OutboundHttpFlowConfiguration {

    @Bean
    public IntegrationFlow partnerRequestFlow(
            RequestHandlerRetryAdvice httpNetworkRetryAdvice) {

        return IntegrationFlow.from("partnerRequests")
                .handle(
                        Http.outboundGateway(
                                        "https://partner.example.invalid/api/commands")
                                .httpMethod(HttpMethod.POST)
                                .expectedResponseType(String.class),
                        endpoint -> endpoint.advice(httpNetworkRetryAdvice))
                .channel("partnerResponses")
                .get();
    }
}
~~~

This is an example of **how to attach advice**, not a complete production application. The `example.invalid` address is a non-routable placeholder; JSON contracts, authentication, timeouts, HTTPS, idempotency headers, HTTP error handling, and channels must be configured for the target system.

### 7.2. What happens on timeout?

Suppose the first response hits a connection error:

~~~mermaid
sequenceDiagram
    participant C as Caller / upstream channel
    participant A as Retry advice
    participant H as HTTP outbound gateway
    participant P as Partner API
    C->>A: Message containing command
    A->>H: Attempt 1
    H->>P: HTTP POST
    P--xH: Connection/response failed
    H-->>A: Throw retryable exception
    A->>A: Backoff per policy
    A->>H: Attempt 2
    H->>P: Resend request
    P-->>H: 200 + response
    H-->>A: Reply payload
    A-->>C: Handler completes
~~~

**Key risk:** Attempt 1 may already have been processed by the partner before the connection failed. Therefore, the diagram does not prove that retrying POST is always safe. Idempotency must be designed as described in §10.

### 7.3. One retry policy for multiple flows?

You can reuse an advice bean if endpoints share the **same** error policy, attempt count, and backoff. However, production usually requires separate policies for HTTP GET, HTTP POST, SFTP sends, JDBC queries, or brokers:

- GET to a read-only service can tolerate bounded retries per contract.
- POST that creates resources needs an idempotency key or durable state.
- JDBC writes must consider transaction isolation and duplicate constraints.
- File/SFTP carries partial-output risks.

Reusing configuration must not obscure **different levels of side-effect risk**.

## 8. RecoveryCallback and ErrorMessageSendingRecoverer

When attempts are exhausted, there are two common paths:

1. **No recovery callback configured:** The exception is rethrown across the synchronous/asynchronous boundary. The receiving source, error flow, or caller handles it further.
2. **Recovery callback configured:** The advice invokes the recovery logic—for example, sending an `ErrorMessage` to a failure-handling channel. The outcome and whether the exception continues to propagate depend on the callback.

### 8.1. Configuring recovery to send an ErrorMessage

~~~java
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.MessageChannel;
import org.springframework.retry.support.RetryTemplate;

// Illustrates advice configuration; beans and channels are provided by the application.
RequestHandlerRetryAdvice createAdvice(
        RetryTemplate template,
        MessageChannel exhaustedErrors) {
    var advice = new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(template);
    advice.setRecoveryCallback(
            new ErrorMessageSendingRecoverer(exhaustedErrors));
    return advice;
}
~~~

`ErrorMessageSendingRecoverer` is useful for routing **exhausted retry results** to a dedicated channel where the system can write audit logs, open an incident, or route a task to a retry queue/DLQ. **It does not automatically guarantee that the channel is durable or that the message reached the DLQ transactionally.**

### 8.2. Be careful when recovery returns normally

This is a critical point: if a recovery callback **handles the error and returns normally**, the caller or listener container may treat the handler execution as complete. In a flow receiving from JMS/AMQP/Kafka, this can lead to **acking or committing the offset** depending on adapter configuration, even though the business task never completed.

Therefore, before using recovery:

- Define the handler's **success/failure contract**.
- Define where failed messages are stored **durably**.
- Decide whether you want broker redelivery/rollback.
- Verify the ordering: **write DLQ/quarantine → ack source**.
- Do not leave an error channel without subscribers, causing errors to be silently dropped or mishandled.

### 8.3. Recovery in a reply-producing gateway

For a request/reply **outbound gateway**, a recovery callback that returns `null` or only sends an error to another channel may cause the caller **not to receive the expected reply** or to time out depending on flow/configuration. Do not treat a logging callback as a valid business response.

If you want the gateway to return an error per contract, design an explicit **error reply or exception** so the caller can distinguish failure; never silently turn a failed HTTP POST into a success response.

## 9. Error channel, retry, and exception lifecycle

Spring Integration provides error handling via an **error channel** and `ErrorMessage`; the message may carry exception details along with the original message depending on the case. Retry advice is a different layer: it decides **to retry at the handler before the error is handled at an outer layer**.

~~~mermaid
flowchart TD
    M["Message arrives at handler"] --> R["Handler + Retry advice"]
    R --> S{"Succeeded?"}
    S -->|Yes| OUT["Reply or side effect complete"]
    S -->|No, retries exhausted| Q{"Recovery callback present?"}
    Q -->|No| PROP["Exception propagates per caller / endpoint boundary"]
    Q -->|Yes| REC["Recovery receives Throwable/RetryContext"]
    REC --> ERR["ErrorMessage or durable failure record"]
    PROP --> EC["Error flow, transaction rollback, or caller"]
~~~

Depending on the message source and channel type, an exception may surface on the call stack, be sent to an error channel, be handled by a listener container, or trigger a rollback. **You cannot assume that a single generic `errorChannel` configuration will automatically provide retry, rollback, and DLQ for every adapter.**

### 9.1. How should errors be logged?

A retry event should contain:

~~~json
{
  "flow": "partnerRequestFlow",
  "component": "http-outbound-gateway",
  "messageId": "msg-2107",
  "businessKey": "order-7642",
  "attempt": 3,
  "maxAttempts": 4,
  "errorClass": "ResourceAccessException",
  "retryDecision": "RETRY",
  "elapsedMs": 1850,
  "correlationId": "corr-5120"
}
~~~

This is an **example telemetry format**, not a log schema auto-generated by Spring Integration. Do not log tokens, passwords, SFTP credentials, full payloads containing sensitive data, or connection strings containing secrets.

### 9.2. RetryListener and observability

Spring Retry supports a listener mechanism for retry operations; Spring Integration also provides observation/metrics support depending on the version. You can instrument:

- Attempt count and retry reason.
- Backoff duration and handler execution duration.
- Which attempt succeeded after retry.
- Exhausted count and final root cause.
- Number of messages routed to durable recovery/DLQ.
- Correlation between message ID, business key, and remote request ID.

**Do not log an ERROR for every attempt** if high volume causes noise; use WARN/INFO/DEBUG per policy, and log ERROR when retries are exhausted or real impact occurs.

## 10. Idempotency: the key requirement when side effects exist

**Idempotency** means repeating the same operation with the same semantic key without creating unintended additional business effects. Retry and redelivery increase the likelihood that the same message is processed multiple times, so **at-least-once delivery + idempotent consumer/remote endpoint** is usually the practical strategy.

### 10.1. Three scenarios when calling a remote system

| Observed outcome | What did the remote actually do? | Is retry risky? |
| --- | --- | --- |
| Connection failed before sending request | Most likely not processed | Can retry, though failure point must still be understood |
| Remote confirmed transient error before processing | No side effect created if contract guarantees it | Can retry with controls |
| Remote finished processing but response was lost | Side effect **already occurred** | Blind retry may create duplicates |

You cannot infer solely from the word "timeout" that the operation was not executed.

### 10.2. Business key and idempotency key

When calling an API to create a shipping request, use **a stable idempotency key tied to the business operation**. All attempts of the same message must use the same key; a genuinely new operation must use a different key.

~~~text
Message business key: shipment-request-9281
HTTP Idempotency-Key sent: shipment-request-9281

Attempt 1: remote creates shipment, response is lost.
Attempt 2: remote receives same key, returns same result or existing state.
Result: 1 shipment, not 2 shipments.
~~~

Effectiveness depends on **whether the partner API genuinely supports the idempotency key** and how long it retains keys. Adding an `Idempotency-Key` header on your own has no effect if the remote ignores it.

### 10.3. Deduplication on the internal system side

For JMS/AMQP/Kafka inbound flows, you can use an **inbox/deduplication table** or a unique constraint on the business key:

~~~sql
-- Illustrative schema; transaction/UPSERT approach depends on the database.
CREATE TABLE processed_message (
    business_key VARCHAR(200) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Only mark a message as processed when the corresponding side effects are guaranteed under your transaction/consistency model. If the database transaction commits but the remote API has not been called yet, recording deduplication too early may cause the task to be skipped. For flows spanning two systems without a shared transaction, consider **transactional outbox/inbox and a state machine**.

### 10.4. Exactly-once must be stated with accurate scope

A broker or connector may provide certain delivery guarantees within its own ecosystem, but it **does not automatically create exactly-once business effects across HTTP + database + SFTP**. To minimize duplicates, you must build boundary idempotency, local transactions, reconciliation mechanisms, and handling for unknown outcomes.

## 11. Transactions, acknowledgement, and commit

Handler retry must be designed alongside the source's transaction/acknowledgement model. If a message is acked before side effects complete, a subsequent error can cause task loss. If a message is redelivered after the remote already processed it, duplicates can occur.

### 11.1. Stateless retry within the same execution

In standard retry:

~~~text
receive message
  -> handler attempt 1
  -> backoff
  -> handler attempt 2
  -> ... succeed or exhausted
  -> return to caller/container
~~~

If the source container is holding a transaction/ack for the entire invocation, total retry duration affects **consumer concurrency, lock duration, transaction timeout, and redelivery risk**. Do not assume an outbound HTTP call can roll back just because a local database transaction rolls back.

### 11.2. Stateful retry and redelivery

Some architectures need to **persist retry information by message key** across broker redeliveries or new transactions. Spring Retry provides retry state/context mechanisms; Spring Integration supports stateful retry models in appropriate configurations.

Required conditions:

- **A stable retry key** that does not change across redeliveries of the same work item.
- Appropriate management of the retry context cache/state; understand persistence scope and restart behavior.
- Exceptions propagated so the transaction/consumer handles redelivery when required by the design.
- A terminal policy: dead-letter, quarantine, FAILED state, or escalation.

**Stateful does not automatically mean durable across JVM restarts.** Default context caches or specific configurations may not be persistent; if crash survival is required, use a broker mechanism or an intentional durable state store.

### 11.3. Recovery can affect acknowledgement

An illustration with a message broker:

~~~text
Message received
    -> handler retries 4 attempts
    -> exhausted
    -> recovery callback logs and returns normally
    -> listener treats handler as completed
    -> may ack/commit depending on configuration
~~~

Without a durable failure record, the business message can be lost. You must define clearly: **once exhausted, throw an exception for broker redelivery, or write to a guaranteed DLQ and then ack?** Do not mix these two strategies through implicit configuration.

## 12. Three retry layers and the risk of stacked retries

In real integrations, **three or more retry layers** can appear:

1. Internal retry or reconnect in the HTTP/JMS/Kafka/SFTP client library.
2. `RequestHandlerRetryAdvice` at the Spring Integration handler.
3. Broker/listener container redelivery, poller reprocessing, or external caller retry.

~~~mermaid
flowchart TD
    BROKER["Broker / inbound adapter<br/>Has redelivery policy"] --> SI["Spring Integration Handler<br/>Retry advice"]
    SI --> CLIENT["HTTP/SFTP/JDBC client<br/>Has internal timeout/retry"]
    CLIENT --> REM["Remote system"]
    SI -.-> DLQ["Durable recovery / DLQ"]
~~~

If each layer independently configures 3 attempts, the total number of remote hits in a failure scenario can multiply several times over. Never enable retry at every layer while assuming the system only tries three times.

### 12.1. Choosing one primary responsible layer

| Need | Layer to consider | Notes |
| --- | --- | --- |
| Brief connection error during a request | Handler advice or HTTP client, avoiding uncontrolled loops | Deadline, idempotency |
| Retry after several minutes or across restarts | Broker retry queue/topic, durable scheduler, outbox | Do not hold threads waiting long |
| Error fetching file/row from source | Poller/source adapter or source transaction | Do not mix with outbound handler retry |
| Broker consumer fails and needs redelivery | Listener/container/broker transaction/ack | Check whether recovery swallows exceptions |
| Task requires manual intervention | DLQ/quarantine, runbook, and idempotent replay | Do not retry poison messages forever |

**Principle:** A flow may need multiple layers, but each layer must have its **role, retry budget, time limit, and inter-layer error handoff** explicitly documented.

## 13. File adapter: retrying a handler is not re-reading the file

File inbound and outbound adapters have their own failure modes: a file may still be in the middle of being written, locked, renamed, already processed without being recorded, or partially written on error.

### 13.1. Inbound file adapter

A common flow:

~~~text
Directory
  -> FileReadingMessageSource + poller
  -> Message<File>
  -> transformer/validator
  -> handler [RequestHandlerRetryAdvice if attached here]
  -> downstream service
~~~

If the handler fails, the advice retries the **handler step**; the poller will not necessarily re-emit the same file on the next scan. You must understand the **file filter, metadata store, received state, and how processed files are marked**.

A system using an in-memory accept-once filter can behave differently after restart compared to one using a persistent metadata store. If you want "at-least-once processing," you must design claim/move/marking based on outcome state, not just increase `maxAttempts`.

### 13.2. File outbound adapter and partial output

Suppose a handler writes an output file, but the process is interrupted after writing part of it. Retrying the same handler without controlling file naming can:

- Overwrite a completed file.
- Append to a corrupted file.
- Create multiple copies under different names.
- Cause downstream consumers to read an incomplete file.

A safe design typically includes:

1. Deriving the filename from a stable **business key** or message ID.
2. Writing to a **temporary path** not read by consumers.
3. Verifying complete write and flushing/syncing as needed.
4. Moving the file to the target name or creating a completion marker per filesystem semantics.
5. On retry, detecting an already-completed target file and handling it idempotently.
6. Auditing delivery status rather than treating "a file with that name exists" as proof of a valid file.

**Atomic rename** depends on the filesystem and whether the move stays within the same filesystem; do not assume every storage environment provides the same guarantee.

### 13.3. When should you retry?

| File error | Decision |
| --- | --- |
| File is still being written by producer and protocol has completion mechanism | Wait for stability/ready marker before processing; retry may fit |
| File is temporarily locked | Bounded retry with backoff |
| Output path missing due to misconfiguration | Report configuration issue; do not retry blindly |
| Permission denied | Usually requires fixing permissions or ownership, not infinite looping |
| Partial output or checksum mismatch | Controlled quarantine/cleanup, rewrite from authoritative source |
| Retry after crash | Use durable metadata, reprocess idempotently |

## 14. SFTP adapter: connection retry and transfer integrity

SFTP inbound/outbound adapters rely on sessions to a remote server. Common failures include session disconnect, handshake timeout, incomplete files, missing directories, authentication failure, quota limits, or remote permission errors.

### 14.1. Attaching advice to the intended processing step

~~~text
SFTP inbound synchronization / polling
   -> local message channel
   -> validate file
   -> outbound SFTP handler [retry advice]
   -> publish completion event
~~~

If advice is attached to the **outbound handler**, it can retry the file-sending operation. It **does not automatically fix** errors in the inbound synchronizer listing files from the server, nor does it automatically re-synchronize previously downloaded files.

### 14.2. Avoiding partial file writes

Recommended steps when the remote consumer is sensitive to incomplete files:

- Use a temporary name during upload if the adapter/server and remote contract allow it.
- Verify complete transfer and checksum/size when needed.
- Only rename or emit a completion marker after upload succeeds.
- Use a stable filename or idempotency key per transaction.
- When retrying after a timeout, check whether the remote already has the complete file before re-writing.
- Handle orphaned, temporary, or corrupted files via a runbook.

**A lost ACK or response does not prove an upload failed.** If the remote already received the entire file, retrying may create duplicates or overwrite data.

### 14.3. Classifying SFTP errors

| Scenario | Policy |
| --- | --- |
| Temporary session reset / connection timeout | Retry and recreate session per client/session factory |
| Server under brief maintenance | Backoff, circuit breaker, or durable scheduling |
| Wrong credentials / host key | Do not retry hundreds of times; fix configuration and security |
| No write permission on remote directory | Alert the owner; do not treat as transient |
| Temporary file already exists from previous attempt | Verify content and status; do not overwrite automatically |
| Server quota / disk full | May require operational intervention; do not block the flow indefinitely |

Host key verification is a security control; **never disable it just to make retries succeed**.

## 15. HTTP outbound gateway: timeouts, status codes, and idempotency

HTTP clearly illustrates the difference between **transport errors**, **protocol errors**, and **business errors**.

### 15.1. HTTP classification

| HTTP outcome | Common meaning | Retry advice |
| --- | --- | --- |
| **Network timeout / connection reset** | Connection failed or response did not arrive | Can retry if request is safe to repeat |
| **429 Too Many Requests** | Rate limit | Consider `Retry-After` and overall load limits |
| **503 Service Unavailable** | Service temporarily unavailable | Bounded retry when contract allows |
| **500 Internal Server Error** | Remote failed processing | Do not retry non-idempotent POST by default |
| **400 Bad Request** | Payload violates contract | Fix validation/schema; usually do not retry |
| **401 Unauthorized** | Missing/expired credentials | Use proper credential refresh mechanism, do not retry blindly |
| **403 Forbidden** | Principal lacks permission or blocked by policy | Fix authorization, do not use retry to bypass |
| **404 Not Found** | Resource does not exist or consistency delay | Depends on contract; some APIs allow waiting for materialization |
| **409 Conflict** | State conflict or duplicate | May reconcile instead of calling again |

In Spring, HTTP clients can throw different exceptions for connection failures and error status codes. The retry policy must be tailored to the actual **client implementation and error handler**, without assuming every 503 response maps to the same exception across all adapters.

### 15.2. When HTTP POST lacks idempotency

Do not implement:

~~~text
POST /charge-card
  -> timeout
  -> POST /charge-card again
  -> timeout
  -> POST /charge-card again
~~~

if the remote lacks deduplication or transaction verification. For payments, shipping, booking creation, and similar side effects, handling ambiguous outcomes matters more than adding more attempts.

### 15.3. Safe design pattern

~~~text
Business command
  -> record durable command ID / idempotency key
  -> HTTP outbound gateway + bounded retry for transport errors
      -> success: update status
      -> definitely rejected: record business error
      -> unknown outcome: query by command ID or reconcile
  -> emit completion event only when status is confirmed
~~~

**Do not change the idempotency key on each attempt.** If the key changes, the remote may treat each call as a new request.

### 15.4. Gateway reply and timeout budget

If upstream is waiting for a reply, total duration includes **request transmission, remote processing time, backoff, and attempt count**. A gateway with a reply timeout shorter than the retry budget can cause "upstream timed out while remote is still processing in the background." When a flow requires long waits, consider converting it to an **asynchronous command + completion event/status lookup**.

## 16. JMS: handler retry and broker redelivery

JMS supports message consumption models with acknowledgements and transactions. Spring Integration provides JMS inbound channel adapters/gateways and corresponding outbound components. **Request-handler advice** does not replace **session acknowledgement or listener container policies**.

### 16.1. Example flow

~~~text
JMS queue
  -> JMS message-driven inbound adapter
  -> DirectChannel
  -> business handler [retry advice]
  -> outbound HTTP/DB
~~~

If the handler throws an exception after retries are exhausted, how the JMS message is redelivered depends on **session transactions, acknowledgement, listener container, and error handling configuration**. If a recovery callback merely logs and returns normally, the listener may treat the message as processed.

### 16.2. Models to decide

| Goal | Corresponding design |
| --- | --- |
| Fast retry of transient errors within same delivery | Short handler retry + backoff |
| Broker redelivery when error persists | Let exception propagate to transaction/listener appropriately; configure redelivery |
| Isolate poison messages | DLQ/quarantine and cap redelivery count |
| Prevent message loss during recovery | Durable failure queue or appropriate transaction/confirm |
| Avoid downstream duplicates | Idempotent consumer and business key |

When using a **transacted JMS session**, understand whether the message source and database/HTTP side effects share a transaction. A local JMS rollback **does not automatically roll back** an HTTP call that already occurred.

### 16.3. Avoid unbounded combinations

If the broker redelivers 20 times and each redelivery runs 5 handler attempts, the same poison message can be processed many times, tying up threads and overloading the remote service. You should enforce:

- Handler attempt quota.
- Broker redelivery quota.
- Total message age/lifetime.
- A DLQ path with alerting and controlled replay.
- Early classification of permanent errors to quarantine quickly.

## 17. AMQP/RabbitMQ: ack/nack, retry, and DLQ

AMQP inbound adapters/gateways typically use a listener container with the broker's ack, reject, requeue, and dead-lettering rules. Retry advice on the handler only governs the **message handler step** in Spring Integration; ack/nack and DLQ are configured at the source/broker layer.

### 17.1. Two paths after retries are exhausted

**Path A — Rethrow exception:** The handler cannot process the message, and the error propagates to the container as configured. The container/broker decides whether to requeue, reject, roll back, or route to DLX/DLQ. Ensure requeuing does not create an infinite loop.

**Path B — Recovery:** The message is written to a confirmed durable error path per design, and the flow completes. The container may then ack the input message; ensure the error write and ack do not leave a data-loss gap.

### 17.2. Control settings to review

| Component | Question |
| --- | --- |
| Inbound container | How do auto/manual ack and transactions behave? |
| Spring Integration advice | Is retry applied to the right handler and exception types? |
| Broker policy | Is redelivery/requeue count bounded? |
| DLX/DLQ | Is routing durable, with an owner and metrics? |
| Outbound publish | Are publisher confirms/returns needed and configured? |
| Idempotency | Does reprocessing a message create duplicate side effects? |

**Publisher confirm** tells you the broker accepted the publish under the supported mechanism, but **it does not prove the downstream consumer succeeded in business processing**. Do not treat confirm as a substitute for end-to-end status.

### 17.3. When message ordering matters

A message undergoing long retries in a consumer can block subsequent messages, while moving it to a retry queue/DLQ can alter processing order. For business flows requiring ordering, explicitly define **partitioning keys, per-aggregate ordering, skip conditions, or reordering** rather than adding indefinite retries.

## 18. Kafka: offsets, consumer retry, and DLQ

Spring Integration provides Kafka inbound/outbound components, while Spring Kafka provides the listener container, error handling, and its own retry models. Therefore, separate:

1. **Handler retry:** `RequestHandlerRetryAdvice` repeats the invocation of a handler in the flow.
2. **Consumer error handling:** Offset/seek/retry/record redelivery is decided by the Kafka listener/container and application configuration.
3. **Durable retry topic/DLT:** Failed messages are published to a dedicated topic for later processing per design.

### 18.1. Do not equate handler success with offset commit

~~~text
Kafka record
  -> inbound adapter / listener
  -> channel
  -> handler [retry advice]
  -> business side effect
  -> return / error
  -> offset commit per container/ack mode
~~~

If the handler is exhausted but the recovery callback returns normally, the container may treat the record as successfully processed and commit the offset per its configured mode. Without a durable recovery record, the business operation may be lost.

### 18.2. Kafka does not automatically guarantee exactly-once for HTTP

Kafka has transactional/idempotent producer features that provide guarantees within Kafka's scope. However, a handler reading from Kafka and calling an external REST API **does not automatically get end-to-end exactly-once**. You still need idempotency keys, outbox, or reconcilable business state.

### 18.3. Retry and record ordering

Blocking retry in the handler can hold the consumer thread and affect throughput, heartbeat/poll schedules, or trigger rebalances if processing exceeds configured limits. A durable retry topic can reduce blocking, but typically requires redesigning **ordering semantics**.

For records sharing the same business aggregate ID, explicitly choose whether to preserve order or accept out-of-order processing; do not assume adding a retry topic preserves all original before/after relationships.

### 18.4. When is handler retry appropriate?

It is suitable for **brief transient errors**, low attempt counts, and total duration well within the consumer's budget. For prolonged failures or poison messages, use **supported error handler/retry topic/DLT mechanisms** instead of letting one record block a partition continuously.

## 19. JDBC and databases: retry must understand transactions

Spring Integration can use JDBC inbound/outbound adapters or handlers executing SQL. Some database errors are transient, but many are **permanent business/constraint errors**.

### 19.1. JDBC classification

| Error | Handling approach |
| --- | --- |
| Deadlock / serialization conflict | Can retry **the appropriate entire transaction** after backoff |
| Connection reset / failover | Retry once connection is restored and operation is idempotent |
| Unique constraint violation | May be a duplicate or bad data; check idempotency |
| Foreign key violation | Usually requires fixing data or business ordering |
| SQL syntax error | Fix code/schema; do not retry |
| Permission denied | Fix privileges/connection policy; do not retry blindly |
| Statement timeout with unclear commit | Verify outcome before re-writing |

### 19.2. Transaction boundaries matter more than attempt counts

If a handler runs inside a transaction:

~~~text
BEGIN
  update order status
  write audit record
  call remote HTTP
COMMIT
~~~

A remote failure may roll back the local database, but **it does not roll back** external HTTP side effects. Retrying the entire handler/transaction can repeat the remote call. Clearly separate which steps are transactional, use outbox when coordinating across systems, and verify the remote by business key.

### 19.3. Polling SQL data

Inbound JDBC polling typically reads eligible rows; having "polled" a row does not mean it has been processed. For crash-safe processing, design a **NEW → CLAIMED → COMPLETED/FAILED** state model, concurrency-safe claim conditions, and timeout-based state recovery. Handler retry alone does not prevent another poller from picking up the same row.

### 19.4. Idempotent writes

For INSERT/UPDATE statements, consider unique business keys, conditional updates, or UPSERTs per your database and business contract. The goal is that a retry does not create duplicate rows or overwrite newer data.

## 20. Message contract, headers, and correlation

Handler retry should rely on a **Message** with a clear contract. Commonly useful fields:

| Field/header | Meaning |
| --- | --- |
| `messageId` | Framework message identifier within a flow |
| `correlationId` | Links messages belonging to the same transaction |
| `businessKey` | Business-level deduplication key |
| `sourceSystem` | Message origin for investigation |
| `targetSystem` | Destination and adapter type |
| `createdAt` / `deadline` | Used for message age and timeout budgets |
| `schemaVersion` | Identifies contract version for validation |
| `recoveryRoute` | Routing path upon exhaustion, if part of design |

Do not assume `MessageHeaders.ID` remains stable across every redelivery or message transformation across all adapters. For idempotency across brokers and restarts, use a **system-defined business key** or stable source event ID.

### 20.1. Protecting message headers

A header supplied by an external system **is not automatically trustworthy** when it controls routing to privileged resources, retry budgets, or idempotency. Validate/sanitize at the inbound boundary, bound header sizes, and avoid echoing tokens/secrets onto error channels.

### 20.2. Do not generate a new message on every retry unnecessarily

Handler retry typically repeats the same received message. If the handler generates a new ID or new business timestamp on each attempt, the remote may treat each call as a new transaction. For side effects, the idempotency key must be determined **before the retry loop** and kept constant across attempts.

## 21. Testing retry advice across layers

A good test does not merely assert "the handler was called 4 times." It must verify **which errors are retried, which side effects are not duplicated, recovery after exhaustion, and source receiver behavior**.

### 21.1. Unit/integration test matrix

| Scenario | Expected behavior |
| --- | --- |
| Handler succeeds immediately | 1 attempt, no backoff |
| Two network errors, third attempt succeeds | 3 attempts, correct reply and metrics |
| Validation/payload schema error | No retry; error path receives the failure |
| 401/403 error | Does not retry endlessly with the same credentials |
| Transient error lasting longer than maxAttempts | Recovery or exception per design |
| Exception wrapped in `MessagingException` | Policy classifies nested cause accurately |
| Handler retries POST after ambiguous outcome | Remote idempotency prevents duplicates |
| Recovery sends to error channel, but channel fails | Source is not marked successful without durable failure record |
| JVM restart mid-processing | Message is recovered/redelivered per source contract |
| Multiple consumers receive duplicate business key | Deduplication prevents two business effects |
| Timeout exceeds caller deadline | Does not hold synchronous request uselessly |
| Broker redelivery combined with handler retry | Total attempts stay within defined budget |

### 21.2. Conceptual unit test for RetryTemplate

You can test the retry policy in isolation with a mock handler counting invocations:

~~~java
// Conceptual test example: add imports and @Test in your project.
AtomicInteger attempts = new AtomicInteger();

String result = retryTemplate.execute(context -> {
    int current = attempts.incrementAndGet();
    if (current < 3) {
        throw new ResourceAccessException("temporary disconnect");
    }
    return "ok";
});

assertEquals("ok", result);
assertEquals(3, attempts.get());
~~~

This test verifies that **`RetryTemplate`** retries successfully after two errors; you still need to test **the advice actually attached to the right DSL endpoint** and error channel/ack behavior in integration tests.

### 21.3. HTTP integration test

Use a controlled HTTP stub server to return network/status errors per scenario. Verify:

1. Initial transient failures followed by subsequent success.
2. Remote receives the same idempotency key across attempts.
3. POST does not create multiple business entities.
4. Retry policy rejects non-retryable errors.
5. When retries are exhausted, `partnerResponses` does not receive a false success.

Never make tests depend on a production partner service.

### 21.4. Broker integration test

For JMS/AMQP/Kafka, run tests with the actual listener and corresponding broker/container:

- Verify ack/commit occurs only according to the chosen strategy.
- If recovery completes normally, verify the failure record is durable before ack.
- If exceptions are thrown for redelivery, verify redelivery count and DLQ routing.
- Stop the process mid-flight and verify recovery capability.
- Verify ordering and concurrency with the same business key.

### 21.5. Testing race conditions

When multiple instances process the same business key, a "SELECT to check existence, then INSERT" pattern **is insufficient** without proper constraints/locks or transactions. Test two concurrent consumers and verify that database/remote idempotency produces only one business outcome.

## 22. Observability: knowing whether retry is helping or hurting

Good retry reduces short-lived failures; bad retry hides incidents, increases latency, and overloads remote systems. You must observe both **recovery rate** and **cost impact**.

### 22.1. Recommended metrics

| Metric | Meaning |
| --- | --- |
| `handler_attempts_total` | Handler execution count, categorized by component/result |
| `handler_retries_total` | Retry attempts beyond the first attempt |
| `retry_exhausted_total` | Messages that failed after exhausting quota |
| `retry_recovered_total` | Executions succeeding after at least one retry |
| `retry_backoff_duration` | Time threads spend waiting between attempts |
| `handler_latency` | Total message processing time including retries |
| `downstream_timeout_total` | Timeouts by target system |
| `dlq_depth` / `quarantine_age` | Volume and age of unprocessed tasks |
| `duplicate_prevented_total` | Repeated requests caught by deduplication |
| `consumer_lag` / `poller_delay` | Impact of retries on source throughput |

Metric names are **naming suggestions**, not automatically generated by Spring Integration. Some versions with Micrometer/Observation integration expose different metrics; add controlled instrumentation as needed.

### 22.2. Cardinality and sensitive data

Do not use `messageId`, `businessKey`, full URLs, usernames, or tokens as high-cardinality **metric labels**. They can go into properly access-controlled traces/logs, while metric labels should use flow name, endpoint, error category, adapter type, and outcome status.

### 22.3. Signals that warrant alerting

- Sudden spike in retry rate on an outbound endpoint.
- Rising retry exhaustion alongside remote timeout errors.
- Handler latency exceeding the gateway deadline.
- Thread pools, JMS listeners, or Kafka consumers held too long.
- Growing DLQ with no assigned owner.
- Same business key repeatedly replayed.
- Auth/permission errors retried endlessly (sign of misconfigured policy).
- High retry success accompanied by rising duplicate business effects (sign of missing idempotency).

## 23. Runbook: when retries are exhausted

A reliable system needs a plan for **when retry is no longer helpful**.

### 23.1. Operational procedure

1. **Identify source and destination:** Flow ID, adapter, source message key, target, correlation ID.
2. **Classify the error:** Transient, permanent, ambiguous, or upstream/downstream outage.
3. **Inspect active retry policy:** N attempts, backoff, deadline, recovery callback, and container redelivery.
4. **Check remote state:** If the operation has side effects, verify whether the transaction already executed.
5. **Check durability:** Is the message in the broker, DLQ, durable table, quarantine, or already acked?
6. **Shed load:** If the remote is overloaded, adjust concurrency/circuit breakers per change policy rather than increasing retries across the board.
7. **Fix root cause:** Network, credentials, schema, service state, or deadlock.
8. **Safe replay:** Use business key/idempotency, throttle replay batches, record actor and approval.
9. **Verify:** Correct business outcome achieved, no duplicates created, and no stuck messages left.
10. **Close incident:** Record evidence, timeline, and preventive measures.

### 23.2. Error-handling states

~~~text
RECEIVED       Source message has been received
PROCESSING     Handler is executing
RETRYING       Retrying within budget
EXHAUSTED      No attempts remaining or non-retryable error
RECOVERY       Routing to durable recovery / error handling
QUARANTINED    Message isolated awaiting intervention
REPLAYING      Controlled reprocessing in progress
SUCCEEDED      Side effect/reply confirmed
FAILED         Unrecoverable, with owner and root cause
~~~

These states are **operational recommendations**, not default Spring Integration enums. For retried messages with side effects, record **remote outcome verification** before setting status to `SUCCEEDED`.

### 23.3. Replay is not unconditional resending

Before replaying a batch of messages from a DLQ:

- Verify the root cause has been resolved.
- Check whether the target system partially executed before failing.
- Ensure the business key/idempotency remains valid after a long delay.
- Split into small batches and limit concurrency.
- Monitor downstream health and define a stop condition.
- Log operator, timestamp, outcome, and deduplicated messages.

## 24. Common anti-patterns

| Anti-pattern | Consequence | Remedy |
| --- | --- | --- |
| Retrying every exception | Data/permission errors loop pointlessly | Classify transient/permanent/ambiguous |
| Very high MaxAttempts in a synchronous gateway | Caller timeout, threads tied up | Bound retry budget and deadline |
| Retrying non-idempotent POST | Creates two orders, shipments, or charges | Business key/remote idempotency and reconciliation |
| Zero backoff when remote is overloaded | Retry storm worsens outage | Exponential backoff, jitter, rate limiting |
| Enabling retry in client, handler, and broker without a budget | Invocation count multiplies | Designate responsible layer and total budget |
| Recovery only logs and returns | Message may be acked even though unprocessed | Durable recovery or propagate exception |
| Attaching advice to handler expecting poller to retry | Source file/record is not reprocessed | Design source filter, transaction, or redelivery |
| Assuming `errorChannel` automatically provides a DLQ | Errors sent to channel are not durable | Durable recovery, verify subscriber and ack |
| Using Message ID as business key everywhere | ID changes across redeliveries, duplicates still occur | Stable business key |
| No concurrency limit during retries | Many threads wait, throughput drops | Pool sizing, bulkhead, circuit breaker |
| Wrongly retrying HTTP 401/403 | Floods IdP/remote and masks permission bugs | Refresh credentials properly or fix authorization |
| Retrying all SQL errors | Schema/constraint errors loop forever | Retry transient errors, transaction/idempotency |
| SFTP retry overwrites completed file | Data corruption or duplicates | Temporary name, verify, atomic publish when supported |
| Consumer commits offset after non-durable recovery | Lost Kafka/JMS/AMQP messages | Check ack/commit and transactional failure routing |
| DLQ has no owner/metrics | Failures pile up unnoticed | Runbook, alerts, audited replay |
| Testing only attempt count | Misses duplicates, wrong acks, or post-restart failures | Integration tests for side effects and crash recovery |

## 25. End-to-end scenario: orders from JMS to HTTP and database

An enterprise receives order commands from JMS, validates the message contract, calls a partner system over HTTP, and then saves state via JDBC. Spring Integration flow:

~~~mermaid
flowchart LR
    Q["JMS Queue"] --> IN["Inbound JMS Adapter"]
    IN --> VAL["Validate + business key"]
    VAL --> H["HTTP outbound gateway<br/>RequestHandlerRetryAdvice"]
    H --> DB["JDBC update / outbox"]
    H -.-> DLQ["Durable recovery"]
    DB --> DONE["Completion event"]
~~~

### 25.1. Message contract

~~~json
{
  "commandId": "cmd-order-8201",
  "orderId": "order-8201",
  "customerId": "customer-291",
  "operation": "CREATE_SHIPMENT",
  "schemaVersion": 2,
  "correlationId": "corr-9711"
}
~~~

**commandId** is the idempotency key that must remain stable across retries and redeliveries. Do not pass unnecessary sensitive payload fields into broadly accessible logs and DLQs.

### 25.2. Retry design

| Step | Retry? | Why |
| --- | --- | --- |
| Validate schema | No for permanent schema errors | Retrying will not make the payload valid |
| HTTP connect timeout | Yes, bounded attempts | May be transient; remote must be idempotent |
| HTTP 401/403 | Do not retry with same credentials | Must fix auth/permissions |
| HTTP 503 | Yes if contract allows, with backoff | Remote may be temporarily overloaded |
| JDBC deadlock | Can retry appropriate transaction | Deadlocks are transient |
| JDBC unique violation | Check duplicate and status | Command may already be processed |
| Unknown remote outcome | Query status or reconcile | Do not unconditionally send a new request |

### 25.3. Realistic failure leg

Attempt 1 sends HTTP POST; the remote creates the shipment, but the response is lost. Attempt 2 resends with the same idempotency key `cmd-order-8201`; the remote returns the already-created result. JDBC writes state once using a unique key. Then the outbound completion event is produced via the outbox pattern or an equivalent guaranteed mechanism.

If the remote **does not support idempotency**, the system must have a status query flow by `commandId`/business resource or route uncertain outcomes to reconciliation; blind POST retry should not be enabled.

### 25.4. When all attempts fail

If `RetryTemplate` is exhausted:

1. The handler throws the error to the JMS container per transactional/redelivery design; **or**
2. Recovery persists the command to a guaranteed durable failure store/queue and ends source processing.

You must choose one clear path. Do not both ack the source and log the error only to a memory-only channel. When replaying after the partner recovers, the message still carries the **same commandId**, avoiding creating a new shipment.

### 25.5. Test cases required

- HTTP succeeds on first attempt.
- Single timeout followed by success.
- Remote created shipment, response lost, retry does not create a duplicate.
- Schema-invalid payload goes straight to quarantine.
- JMS redelivery after application crash.
- JDBC deadlock after HTTP success: does not create another shipment.
- Recovery channel or DLQ temporarily unavailable.
- Multiple consumers receive the same `commandId`.
- Replay DLQ batch after partner outage and verify zero loss and zero duplicates.

## 26. Design checklist for request-handler retry advice

1. **Right location:** Advice attached to the handler/endpoint needing retry; not confused with poller or broker retry.
2. **Right error types:** Transient whitelist defined, distinguishing permanent and ambiguous outcomes.
3. **Right attempts:** MaxAttempts includes the initial call; retry budgets do not multiply across layers.
4. **Right backoff:** Exponential/fixed and jitter chosen for load, avoiding retry storms.
5. **Right timeout:** Total attempts and wait time fit within reasonable deadlines/SLAs.
6. **Right message:** Clear business key, correlation ID, schema, and source/resource metadata.
7. **Right idempotency:** Side effects are safe to repeat, especially HTTP POST, file uploads, DB writes.
8. **Right transaction:** Clear boundaries for database, broker, external APIs, and rollback scope.
9. **Right acknowledgement:** Recovery callback can cause source ack; verify in practice.
10. **Right recovery:** After exhaustion, there is a durable route, caller error, or owned DLQ; errors are not swallowed.
11. **Right adapter:** Understand file filters, SFTP partial files, HTTP status codes, JMS/AMQP redelivery, Kafka offsets, JDBC transactions.
12. **Right channel:** Identify sync/async boundaries and where exceptions can propagate.
13. **Right observability:** Monitor attempts, exhausted, recovered, latency, consumer lag, and DLQ.
14. **Right security:** Do not retry auth errors endlessly; do not log credentials/sensitive payloads.
15. **Right testing:** Unit + integration + crash/restart + duplicates + negative cases.
16. **Right runbook:** Procedures for verifying outcomes, replaying, throttling load, and closing incidents.

## 27. Exercises and self-check questions

### Exercise 1. How many retries is MaxAttempts?

**Scenario:** `SimpleRetryPolicy` is set to a maximum of 4 attempts. A developer claims there will be 4 retries in addition to the initial call.

**Answer:** Incorrect. There are typically **4 handler invocations total**, consisting of 1 initial call and at most 3 retries.

### Exercise 2. Which advice handles file inbound polling errors?

**Scenario:** A file inbound poller fails to fetch files from a remote server due to a session error. The engineering team only attaches `RequestHandlerRetryAdvice` to the HTTP outbound handler at the end of the flow.

**Answer:** Advice on the HTTP handler **does not resolve source polling errors**. You must configure/investigate the inbound poller, session reconnect, filters, and corresponding source redelivery.

### Exercise 3. Why can ErrorMessageSendingRecoverer be dangerous?

**Scenario:** A JMS handler exhausts retries; the recoverer sends the error to a channel and returns normally, but that channel is not durably backed.

**Answer:** The listener may ack the source message per configuration because the handler completed normally, while the business task failed and the failure record can be lost. You need durable recovery and ack verification, or let the exception propagate for redelivery per policy.

### Exercise 4. Should HTTP POST timeouts be retried?

**Scenario:** A payment service returns a connect/response timeout after a command is sent. There is no idempotency key or status lookup API.

**Answer:** Do not blindly retry side effects. You must verify the API contract, remote status, or add idempotency before designing automatic retries.

### Exercise 5. Kafka offsets and handler retry

**Scenario:** A handler uses `RequestHandlerRetryAdvice`, exhausts 5 attempts, and recovery returns normally. A developer insists Kafka will definitely redeliver the record.

**Answer:** That cannot be assumed. Commit/ack depends on the listener/container and error handling. If the handler completes normally, the offset may be committed per configuration, preventing the record from being redelivered. Integration testing in the actual mode is required.

### Exercise 6. Duplicates from stacked retries

**Scenario:** HTTP client retry, handler retry, and broker redelivery are all enabled, but the documentation only states "max retries = 3."

**Answer:** That description is insufficient; total remote calls can multiply significantly. You must establish an end-to-end retry budget, designate the responsible layer, set timeouts, and implement deduplication/recovery.

### Exercise 7. JDBC deadlock and HTTP side effect

**Scenario:** A handler calls HTTP to create a shipping order and then writes to JDBC; a JDBC deadlock occurs, so the whole handler is retried.

**Answer:** If HTTP already created the order, retrying the entire handler may create a second order. You need HTTP-side idempotency and appropriate transactions/reconciliation; only retry the truly safe transactional part or use an outbox/state machine.

### Exercise 8. Retrying on 403 errors

**Scenario:** An API rejects requests with 403 due to missing permissions; the system runs exponential retry 20 times.

**Answer:** This is usually an authorization error, and increasing attempts will not solve it. Route to the error flow, check principal/role/scope, and alert the IAM owner; do not use retries as a way around permissions.

## 28. Summary

**`RequestHandlerRetryAdvice`** lets Spring Integration retry **message handler invocations** according to a **`RetryTemplate`** policy, helping handle brief transient errors such as connection drops or temporary remote overload. A useful configuration must specify **retryable exceptions, attempt counts, backoff, timeouts, and behavior upon exhaustion**, rather than merely turning retry on.

In the **Spring Integration Adapters** module, each protocol has its own boundaries: **file/SFTP** must guard against partial output and duplicates; **HTTP** requires idempotency for side effects; **JMS/AMQP/Kafka** must coordinate acks, redelivery, and DLQs; **JDBC** requires understanding transactions/constraints. Handler retry **does not replace** poller retry, broker redelivery, source durability, error channels, or confirmed recovery.

A reliable flow is measured by **correct business outcomes**: messages are not lost, operations are not unintentionally duplicated, failed tasks have a durable home and owner, retries do not cause overload, and everything is traceable via logs, metrics, tests, and runbooks. That is the real goal of **retry advice for request handlers** in production integration systems.
