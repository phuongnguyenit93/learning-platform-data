# Avoiding Multi-Layer Nested Retries in Spring Integration Runtime

## Lesson Objectives

In **Spring Integration Runtime**, a message can travel through a gateway, channel, service activator, poller, executor, adapter, and external system. Multiple components in that chain may retry on their own: the HTTP client, **RequestHandlerRetryAdvice**, a transaction interceptor, a polling consumer, broker redelivery, or an upstream caller.

Problems arise when each layer is configured independently and all try to "rescue" the same failure. A single request can be executed dozens of times, exceed deadlines, clog thread pools, or duplicate business side effects.

After this lesson, you will be able to:

- Identify **retry layers** and map the execution boundaries of a message.
- Calculate attempt amplification, total latency, and load amplification from nested retries.
- Choose the right **retry owner** per boundary and set attempt and time limits.
- Distinguish **internal retry**, **broker redelivery**, **transaction rollback**, and **post-exhaustion recovery**.
- Design idempotency, correlation, error channels, message stores, and DLQs so effects are not duplicated.
- Verify behavior under timeouts, invalid data, executor saturation, dropped connections, and flow restarts.

> **Principle:** Every business operation should have one **clearly visible end-to-end retry policy**, specifying who owns retry, which conditions are retried, maximum limits, where messages go once exhausted, and how the same request is identified across attempts.

## 1. What Are Multi-Layer Nested Retries?

Suppose a payment flow has this structure:

~~~mermaid
flowchart LR
    G["HTTP gateway<br/>caller retry"] --> C["Spring Integration channel"]
    C --> P["Poller/broker consumer<br/>redelivery"]
    P --> A["Service activator<br/>RetryAdvice"]
    A --> H["HTTP client<br/>transport retry"]
    H --> S["Payment service"]
~~~

Each component can retry on its own when it fails to receive an expected result:

| Layer | Example mechanism | Unit being re-executed |
| --- | --- | --- |
| Upstream caller/gateway | HTTP request retry, job re-triggering scheduler | May re-send the **entire business command** |
| Broker/adapter | Nack, rollback, redelivery, consumer restart | **Transport message** is redelivered |
| Poller/transaction | Poll fails, source retains message or transaction rolls back | May fetch the message again on a later poll |
| Spring Integration endpoint | **RequestHandlerRetryAdvice** re-invokes handler | One **handle message** call |
| HTTP/DB client | Connection retry, timeout retry, SQL statement or HTTP request | One **dependency call** |
| Recovery scheduler | Replay from DLQ/quarantine after a delay | A **new processing run**, possibly hours later |

Not every layer enables retries by default. The rows above list **places where real configuration must be audited**, not a claim that the framework enables all of them automatically.

### Exponential Multiplication of Attempts

If a broker delivers a message up to **4 times**, each handler invocation retries up to **3 times**, and the HTTP client retries up to **2 times** per call, then when every attempt fails:

\[
N_{\mathrm{HTTP,max}} = 4 \times 3 \times 2 = 24
\]

**A single business request** can generate up to **24 calls to the payment service**. If the caller also retries the entire request twice, the theoretical ceiling becomes 48. That is an **upper bound** assuming every layer runs its full quota; earlier successes or inactive layers yield fewer attempts.

In practice, nested retries are even more dangerous than simple multiplication:

- An outer layer can time out while an inner layer **is still running**, causing overlapping executions.
- An API returning a timeout **does not prove** the side effect failed; the receiver may have committed.
- Each retry consumes extra waiting threads, connections, logs, trace spans, and locks.
- When downstream is overloaded, concurrent retries create a **retry storm**, making the outage worse.

### Three Concepts to Keep Separate

- **Attempt**: one specific execution, e.g., a single charge call.
- **Delivery**: one broker/poller delivery of a message to a consumer; one delivery can contain multiple attempts.
- **Business operation**: one unique business action, e.g., charging **paymentId=PAY-42**; every attempt/delivery for it must share the same business key.

Never treat handler invocation count as successful transaction count. **At-least-once delivery** plus retries does not produce **exactly-once side effects** on its own.

## 2. Identifying Retry Layers in a Message Flow

When diagnosing a flow, trace the exact execution path:

~~~text
External producer
  └─ inbound adapter / gateway
       └─ input channel
            └─ poller or dispatcher
                 └─ handler advice chain
                      └─ service / repository
                           └─ external HTTP/DB client
  └─ error flow / recovery / broker redelivery
~~~

At each point, record the **attempt limit**, **backoff**, **timeout**, **transaction boundary**, and **who decides the message succeeded**. An application can have retries inside underlying libraries that were never declared explicitly in the `IntegrationFlow`.

### DirectChannel and ExecutorChannel

**DirectChannel** invokes the consumer on the sender's thread. If the handler throws, the error can propagate back to the sender; a caller retrying the entire `send` will re-run the whole synchronous chain. When **RequestHandlerRetryAdvice** wraps the handler, a single `send` can also invoke the handler multiple times.

**ExecutorChannel** hands processing off to an executor thread. The producer's `send` can finish before the handler fails. Transactions or retries on the sending thread **do not automatically cover** consumer execution. A retry at the producer can dispatch a **new message** while the prior send is still running on a worker.

### Pollers and Brokers

Pollers decide when to pull messages from a source. Periodic polling **does not imply** failed messages are automatically replayed: the outcome depends on source type, transactions, acks, and error-flow configuration. With brokers, redelivery can stem from rollback/nack, visibility timeouts, offset resets, or restarts.

If a handler retries three times and then throws, the broker **may** redeliver the message from the start per source policy. If handler recovery catches the error and finishes normally, the broker **may** treat the delivery as successfully processed. Verify the real adapter/ack contract; never infer it from the name `errorChannel`.

## 3. Subtle Consequences of Nested Retries

### 3.1. Exceeding Total Wait Budgets

Suppose each HTTP call times out after **2 seconds**. With three handler attempts and two HTTP client attempts, network waits alone can approach **12 seconds** for a single delivery, excluding backoff, serialization, DB work, and thread overhead. If the gateway only allows **5 seconds**, the caller gives up and retries while the earlier handler is still running.

Set an **end-to-end deadline** for the request. Each inner layer should consume the remaining budget instead of starting fresh unbounded timeouts. Once the budget is spent, stop initiating new side effects unless an asynchronous workflow is explicitly designed for it.

### 3.2. Duplicate Side Effects

~~~text
T1: handler calls payment provider with paymentId=PAY-42.
T2: provider succeeds, but the response is lost.
T3: HTTP client times out and retries.
T4: RetryAdvice retries the entire handler again.
T5: Broker redelivers the message when the transaction fails.
~~~

If the provider does not support idempotency keys and the application lacks reconciliation, a single command can charge multiple times. **Rolling back a local DB transaction cannot roll back** a completed HTTP call in an external system.

### 3.3. Load Amplification and Runtime Contention

Retries with synchronous backoff keep processing threads blocked while waiting; small poller or executor pools fill up fast. When many messages fail simultaneously, queues grow, latency climbs, and new timeouts trigger even more retries. Adding threads at that point may just send more requests into the failing dependency.

### 3.4. Blurred Operational Ownership

Logs reading "retry attempt 3/3", "delivery count 2", and "HTTP retry 2" may refer to **three different counters**. Without attaching **businessId/requestId/correlationId** across all attempts, operators cannot easily tell how many times a command was actually sent.

## 4. Choosing One Retry Owner per Boundary

A **retry owner** is the layer that decides whether to re-execute **the entire protected operation**. Choose it based on state consistency scope, transaction placement, error types, and side-effect cost.

| Scenario | Typically suitable retry owner | Why |
| --- | --- | --- |
| Transient errors calling an external service, stateless handler | Handler retry advice **or** bounded client retry | Avoid both retrying by default |
| Consuming from a broker with its own transaction/ack | Consumer/broker redelivery with limits and a DLQ | Source controls delivery; avoid unbounded retries |
| DB transaction hits deadlock/serialization conflict | Retry wrapping a **fresh transaction** | Next attempt needs clean transaction state |
| Malformed JSON, missing required fields | No hot retry; quarantine/DLQ | Repeating the same payload will not change the outcome |
| Waiting for a service to recover from a long outage | Durable delayed retry / scheduler / DLQ replay | Avoid tying up threads or holding transactions for hours |
| Side effect left an uncertain outcome | Reconcile by idempotency key before retrying | A timeout does not prove the operation failed |

Choosing one owner **does not necessarily forbid every lower-level retry**. For instance, a client might safely retry a connection setup once within an agreed budget. However, **total** attempts, time, and retry conditions must be budgeted together; never configure layers independently and let them add up blindly.

### Per-Error Decision Model

~~~mermaid
flowchart TD
    F["Exception caught"] --> C{"Recoverable<br/>if retried?"}
    C -- "No" --> Q["Record and quarantine / business failure"]
    C -- "Yes" --> U{"Is side-effect outcome<br/>certain?"}
    U -- "Unclear" --> I["Query / reconcile by idempotency key"]
    I --> U2{"Evidence it did not complete?"}
    U2 -- "No" --> M["Hold for investigation<br/>or controlled recovery"]
    U2 -- "Yes" --> B{"Attempt budget and<br/>deadline remain?"}
    U -- "Not executed or safe to call again" --> B
    B -- "Yes" --> R["Retry at chosen owner"]
    B -- "No" --> E["Recovery: DLQ / journal / alert"]
~~~

Model the **unknown outcome** state explicitly. Returning "failed" right after an HTTP timeout without checking the provider can prompt the user to retry a transaction that already succeeded.

## 5. Example RequestHandlerRetryAdvice Configuration with Explicit Scope

The example below illustrates **a single retry owner at the service activator** when downstream fails transiently. Assume the underlying HTTP client is configured not to repeat the same business command on its own, and ingress adds no independent hot retry loop.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
class PaymentRetryConfiguration {

    @Bean("paymentRetryAdvice")
    RequestHandlerRetryAdvice paymentRetryAdvice() {
        // maxAttempts = 3: includes the initial attempt and up to 2 retries.
        SimpleRetryPolicy policy = new SimpleRetryPolicy(3);

        ExponentialBackOffPolicy backoff = new ExponentialBackOffPolicy();
        backoff.setInitialInterval(200L);
        backoff.setMultiplier(2.0);
        backoff.setMaxInterval(800L);

        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(policy);
        template.setBackOffPolicy(backoff);

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(template);
        return advice;
    }
}
~~~

Apply the advice to the endpoint by bean name:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

record PaymentCommand(String paymentId, long amount) {}

interface PaymentGateway {
    // Provider must enforce idempotencyKey for the payment operation.
    void charge(PaymentCommand command, String idempotencyKey);
}

@Component
class PaymentHandler {
    private final PaymentGateway gateway;

    PaymentHandler(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    @ServiceActivator(
            inputChannel = "paymentCommands",
            adviceChain = "paymentRetryAdvice")
    public void handle(Message<PaymentCommand> message) {
        String idempotencyKey =
                (String) message.getHeaders().get("idempotencyKey");
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            throw new IllegalArgumentException("Missing idempotencyKey");
        }

        gateway.charge(message.getPayload(), idempotencyKey);
    }
}
~~~

**Explanation and limitations of the example:**

1. Retry here wraps **the handler invocation**; it does not automatically wrap the producer, broker redelivery, or any other endpoints.
2. **SimpleRetryPolicy(3)** illustrates attempt counts, but its default rule set is too broad for production: restrict by **retryable exceptions**, inspect cause chains, and avoid retrying permanent validation/authorization errors.
3. With two backoffs of **200 ms then 400 ms**, theoretical wait time is around **600 ms** if all three attempts execute; real duration adds processing time, timeouts, and scheduler latency.
4. No recovery callback is configured in this snippet: on exhaustion, the exception propagates to the corresponding error handling path. Production final handling requires configuring error flows/transactions and appropriate ack behavior.
5. **idempotencyKey** must stay identical across every attempt, broker redelivery, and replay. Passing a key to the provider is insufficient if the provider lacks idempotency guarantees or expires keys too early.
6. In real deployments, **never retry immediately after an ambiguous timeout** without deduplication/reconciliation controls. You may need to separate status lookup from the charge command.

### When Both Transactions and Retries Wrap a Handler

Advice ordering changes semantics. If retries run **inside the same transaction** marked rollback-only after the first failure, subsequent attempts execute inside an invalid transaction. Usually **each attempt needs a fresh transaction** for atomic work; for broker sources, rollback/ack also depends on the consumer container and transaction manager.

Conceptual illustration:

~~~text
Retry (3 attempts)
  ├─ Transaction 1 → handler → rollback
  ├─ Transaction 2 → handler → rollback
  └─ Transaction 3 → handler → commit or final failure
~~~

Actual ordering of advices/proxies and transaction managers must be verified with integration tests rather than inferred from annotation order alone. And even when the DB rolls back, an external HTTP call may already have succeeded.

## 6. Recovery After Retries Exhaust: Do Not Create Another Infinite Retry Loop

A complete policy must answer: **After the final attempt, where does the message go?**

In Spring Integration, **RequestHandlerRetryAdvice** can be paired with a recovery callback, such as a mechanism built on **ErrorMessageSendingRecoverer** to emit failure notifications. The error flow can write a **FailureJournal**, route to quarantine/DLQ, or trigger alerts. **Point to verify:** Recovery consuming the exception can make outer layers treat processing as complete; whether the broker redelivers depends on the adapter, ack, and transaction.

~~~mermaid
flowchart LR
    IN["Message received"] --> RP["Retry owner<br/>max 3 attempts"]
    RP -- "Success" --> OK["Record COMPLETED"]
    RP -- "Retries exhausted" --> REC["Recovery"]
    REC --> FJ[("FailureJournal / DLQ")]
    FJ --> OBS["Alert + status lookup"]
    FJ -. "Conditional replay<br/>after fixing root cause" .-> IN
~~~

Common recovery options:

- **Rethrow the exception** so the transaction rolls back or the source decides redelivery, if intentional and delivery-bounded.
- **Send to DLQ/quarantine** when payload cannot be processed or budget is exhausted; store safe payload/references, reason, timestamp, and correlation.
- **Write FailureJournal** and mark the business record `FAILED`/`UNKNOWN`, backed by reconciliation and a recovery workflow.
- **Durable delayed retry** for prolonged transient outages, using a job/broker delay with maximum replay limits and TTL; never hold threads sleeping for hours.

If a recovery handler merely logs and returns, the message may be treated as delivery-successful even though the business operation never completed. If recovery automatically replays continuously without tracking total retry counts, it can create an **infinite loop through the DLQ**.

### Not Every ErrorMessage Is a Retry

An **ErrorMessage** carrying a failure is published by components supporting error flows; sending an `ErrorMessage` does not automatically send the original message back to the input channel. **`errorChannel`** is merely an error-notification routing path; retry, replay, and ack must be designed explicitly.

When errors occur after an **ExecutorChannel**, the producer may already have returned success. Observe exceptions on the worker thread and its error flow. Retrying at an outer HTTP caller could resend the entire request while the earlier attempt is still in flight.

## 7. Idempotency, Correlation, and Deduplication Across All Attempts

The most critical condition whenever retries exist is that **retrying processing must not repeat business effects**. This can be achieved at several levels depending on the system:

| Data / key | What to use it for | What NOT to use it for |
| --- | --- | --- |
| **paymentId / operationId** | Identifying a single unique business operation | Changing on every attempt |
| **idempotencyKey** | Letting the receiver recognize multiple attempts of the same operation | Sharing across two different business actions |
| **correlationId** | Linking messages, errors, and events across one journey | Assuming it is unique per individual side effect |
| **Spring MessageHeaders.ID** | Identifying a technical Spring `Message` instance | Deduplication key across restarts/brokers/rebuilt messages |
| **deliveryAttempt / retryCount** | Analyzing how many times one layer tried | Representing total attempts across all layers |
| **traceId/spanId** | Observing execution paths; spans may vary | Replacing business keys or idempotency keys |

A combined example:

~~~text
paymentId=PAY-42
idempotencyKey=charge:PAY-42
correlationId=checkout-42
brokerDelivery=3
handlerAttempt=2
httpAttempt=1
~~~

When a message is redelivered, **preserve `paymentId`/`idempotencyKey`/`correlationId`**. You can generate a new `executionId` or trace span for the run to distinguish retries. Never use delivery count as a business key because it changes with every redelivery.

### Enforcing Deduplication in State Storage

Single-JVM mechanisms (`AtomicInteger`, `synchronized`, `ConcurrentHashMap`) do not protect across multiple instances or restarts. In a database, typically use a **unique constraint** on `operationId`, processing states, and transactions to prevent two concurrent consumers from committing the same state simultaneously.

A possible state model:

~~~text
RECEIVED → PROCESSING → COMPLETED
                      → FAILED_RETRYABLE → SCHEDULED
                      → QUARANTINED
                      → UNKNOWN_OUTCOME → RECONCILING
~~~

When side effects happen in an external system, a DB unique constraint **does not create a distributed transaction** with the HTTP provider. To avoid duplicate calls, use **provider-enforced idempotency keys**, transactional outbox/inbox, status queries by `operationId`, or reconciliation/compensation workflows. Also handle crashes occurring between calling the provider and writing `COMPLETED`.

## 8. Capping Total Attempts, Backoff, and Deadlines

A practical policy needs a **shared budget** or at least cross-layer coordination rules:

- **maxAttempts**: includes the initial attempt, e.g., 3 attempts means at most 2 retries.
- **maxElapsedTime/deadline**: total time the business operation is allowed to wait; every sub-call must respect remaining time.
- **Retryable exceptions**: connection timeouts, transient overload, HTTP 429/503 when protocol and idempotency permit; avoid retrying bad data, auth failures, or non-recoverable errors.
- **Backoff + jitter**: reduces synchronized retries across failing messages; cap intervals and watch throughput limits.
- **Rate limit, bulkhead, circuit breaker**: shed load to downstream when failures spread; never turn a circuit-breaker rejection into another retry loop.
- **Per-operation attempt counter**: when delayed retries and broker redeliveries coexist, persist total replay counts durably; never rely solely on a bean counter reset on restart.

To quantify: if inner retry allows up to 3 attempts, each request times out at 2 seconds, and backoffs are 0.2 + 0.4 seconds, **one delivery** can take nearly **6.6 seconds** before overhead. If the broker redelivers 4 times, total sequential time can reach nearly **26.4 seconds** plus broker backoff. A caller with a 5-second deadline cannot wait out this entire cycle.

**Simple upper-bound formula** when attempts execute sequentially:

\[
T_{\mathrm{upper}} \approx
N_{\mathrm{outer}}\left(
N_{\mathrm{inner}}\,T_{\mathrm{attempt}} +
\sum T_{\mathrm{inner\ backoff}}
\right) + \sum T_{\mathrm{outer\ backoff}}
\]

In reality, queueing latency, transactions, serialization, GC, and **overlapping** attempts caused by outer timeouts also contribute. Treat this as a budget estimate, not a hard maximum guarantee.

## 9. Hands-On Scenario: Fixing a Flow with Three Nested Retry Loops

A system receives payment messages from a broker:

~~~text
Broker consumer: redelivery up to 4 deliveries
  └─ DirectChannel
       └─ service activator + RequestHandlerRetryAdvice(3 attempts)
            └─ HTTP client retry(2 attempts)
                 └─ payment provider
~~~

Symptoms:

- One payment command occasionally generates 24 HTTP calls when the provider is slow or failing.
- Consumer thread pools stay occupied for long stretches, and broker backlog climbs.
- In some cases the provider succeeded while the caller saw a timeout.
- After restarts, messages are redelivered yet logs lack a shared `operationId`.

### Remediation Steps

**Step 1 — Measure before changing.** Gather logs, traces, and live configuration to pinpoint which layers retry. Record `operationId`, broker delivery ID/count, handler attempt, HTTP attempt, exception, and duration per call. Cross-check the provider by idempotency key to see which side effects already occurred.

**Step 2 — Pick one retry owner.** For instance, choose **handler retry** for short-lived HTTP errors: cap at three attempts with an explicit deadline, disable client-level charge retries, and let the broker redeliver only when transactions fail outside handled scope or per a coordinated recovery policy. Never let the broker run an independent hot redelivery loop once the app already decided to send to the DLQ.

**Step 3 — Classify errors.** Route malformed JSON and validation errors to quarantine immediately. Route ambiguous timeouts to reconciliation, or retry with **the same idempotency key** if the provider supports it. Retry HTTP 429/503 with backoff/jitter within budget.

**Step 4 — Decide post-exhaustion outcomes.** Persist an inspectable outcome: `COMPLETED`, `QUARANTINED`, `FAILED`, or `UNKNOWN_OUTCOME`. If scheduled replay is needed, maintain durable attempt budgets across deliveries and restarts.

**Step 5 — Test end-to-end.** Run concurrent messages with identical and distinct `operationId`s; measure total HTTP calls, real provider effects, completion time, DLQ counts, and correlation continuity.

Before/after comparison:

| Criterion | Uncoordinated nested retries | After a unified policy |
| --- | --- | --- |
| Maximum calls | 4 × 3 × 2 = **24** per operation | Capped by unified policy, e.g., **3** per processing cycle |
| Timeouts | Each layer sets independent timeouts | One deadline and remaining-budget propagation |
| Duplicates | No stable idempotency key | Same `operationId`/`idempotencyKey` across every attempt |
| After exhaustion | Redelivery and error handlers may loop infinitely | Explicit `FAILED`/`UNKNOWN`/DLQ; conditional replay |
| Diagnostics | Fragmented attempt logs | Correlation, delivery count, and retry count per layer |

**Caveat on the number "3":** If policy still permits broker redeliveries or scheduled replays later, total calls over the lifetime of the operation **can exceed 3**. To cap lifetime calls, manage the budget **across deliveries and replays**, not solely via `RetryAdvice(3)`.

## 10. Testing and Runtime Observability

### Valuable Test Cases

1. **Transient failure then success:** downstream fails twice and succeeds on the third try; verify exactly three calls, identical `idempotencyKey`, and one business effect.
2. **Invalid payload:** handler/recovery rejects immediately; verify no hot retry loop occurs.
3. **All attempts fail:** exhausting budget routes properly to error flow/DLQ; message does not vanish after logging.
4. **Timeout after provider succeeded:** verify idempotency or reconciliation; never charge twice.
5. **ExecutorChannel:** producer finishes `send` before downstream fails; exceptions reach the right error channel without caller retries spawning parallel duplicate tasks.
6. **Transaction rollback:** verify a fresh transaction per attempt when required by contract; verify broker ack/redelivery after retries exhaust.
7. **Restart mid-retries:** budget, `idempotencyKey`, and `correlationId` are not accidentally reset; message store remains readable.
8. **Multiple consumers/instances:** for the same `operationId`, only one outcome state commits or reconciliation handles it safely.
9. **Widespread downstream overload:** retries apply backoff/jitter and rate limiting without unbounded executor queue growth.

Count calls at **the real target or a counting stub**, not just framework calls into the handler; an HTTP client may retry on its own without handler unit tests noticing.

### Recommended Metrics and Logs

~~~text
operationId=PAY-42 correlationId=checkout-42
flow=payment endpoint=paymentHandler
deliveryAttempt=2 handlerAttempt=3 clientAttempt=1
errorType=PAYMENT_TIMEOUT
decision=QUARANTINED elapsedMs=6480
~~~

- Total external calls per **`operationId`** and call-to-business-request ratio.
- Retries **per layer**, post-retry success rate, and exception classes.
- P95/P99 latency, deadline-exceeded count, in-flight operations, and executor queue depth.
- Messages waiting in queue/poller, DLQ depth, oldest message age, and delayed retry counts.
- Unknown outcomes, pending reconciliations, duplicate side effects, and idempotency key conflicts.
- Messages missing `correlationId` or `idempotencyKey` in the error flow.

When evaluating performance, boosting throughput is not a valid reason to add retries. Retries solve **transient errors** within a budget; when downstream is overloaded, reducing concurrency or throttling sends is usually far more effective.

## 11. Implementation Checklist

- Identify every retry source: caller, gateway, broker, poller, handler advice, DB/HTTP client, scheduler, and replay.
- Explicitly assign a **retry owner** per error type and boundary; avoid independent attempt settings across multiple layers.
- Compute maximum attempts and elapsed time via **multiplication** whenever retries nest.
- Bound **`maxAttempts`, deadlines, timeouts, and backoff + jitter**, verifiable in operations.
- Retry only appropriate errors; never hot-retry bad data or ambiguous side-effect outcomes without reconciliation.
- Preserve `operationId`, `correlationId`, and **`idempotencyKey`** across message transformations, broker redeliveries, `errorChannel`, DLQ, and restarts.
- Define transaction/ack semantics explicitly, especially across `ExecutorChannel` or when combining `RequestHandlerRetryAdvice` with transaction advice.
- Design post-exhaustion recovery with durable state, alerts, and conditional replay.
- Verify via integration tests the **real** call count, business effects, and behavior under downstream timeouts.
- Monitor retry storms, executor saturation, queue backlogs, and `UNKNOWN_OUTCOME` volume.

## Conclusion

Retry is a tool for recovering from transient failures; **multi-layer nested retries**, however, can turn a minor glitch into an avalanche of requests, overlapping timeouts, and duplicate side effects. In Spring Integration Runtime, inspect channels, endpoints, pollers, executors, transactions, adapters, message stores, and error flows together to see who is retrying. With **one unified policy**, finite budgets, stable idempotency, and well-defined recovery outcomes, the system can recover while keeping load and business correctness under control.

## References

- [Spring Integration Reference — Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Retry API — RetryTemplate](https://docs.spring.io/spring-retry/docs/current/apidocs/org/springframework/retry/support/RetryTemplate.html)
- [Spring Retry API — SimpleRetryPolicy](https://docs.spring.io/spring-retry/docs/current/apidocs/org/springframework/retry/policy/SimpleRetryPolicy.html)
