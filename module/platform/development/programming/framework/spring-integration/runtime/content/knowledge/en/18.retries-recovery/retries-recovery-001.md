# Retry Advice Around Message Handlers in Spring Integration

## 1. Objectives and Runtime Context

In **SPRING_INTEGRATION_RUNTIME**, messages are dispatched through `MessageChannel`, consumer endpoints, pollers, and executors. When a handler calls an HTTP endpoint, queries a database, or pushes a message to another system, transient errors can cause processing to fail even when the input message is completely valid. The **Retries and recovery → Retry advice around message handlers** section explains how to retry **the exact handler operation** and route final failures so operations remain observable and controllable.

For example, suppose a system has the following flow:

~~~mermaid
flowchart LR
    A["requests"] --> C["Consumer endpoint"]
    C --> R["RequestHandlerRetryAdvice"]
    R --> H["Invoke message handler\nsubmit order to shipping service"]
    H -->|Success| S["Complete operation"]
    H -->|Retryable error| R
    H -->|Retries exhausted / non-retryable| E{"Has recoveryCallback?"}
    E -->|Yes| F["ErrorMessageSendingRecoverer"]
    F --> G["recoveryChannel\nDLQ / audit / alert"]
    E -->|No| X["Throw exception to caller\nor appropriate error flow"]
~~~

Specific objectives:

- Attach `RequestHandlerRetryAdvice` to a message handler instead of reprocessing the entire flow.
- Control exception types, retry counts, backoff intervals, timeouts, and recovery strategies.
- Distinguish **stateless retry** (retrying immediately within the same processing invocation) from **stateful retry** (relying on the message source to redeliver).
- Understand the impact of `DirectChannel`, pollers, executors, transactions, asynchronous errors, and duplicate processing risk.
- Track actual invocation counts, the last error, the original message, correlation, and endpoint state.

**Core principle:** retry is the behavior of repeating an operation that may fail due to transient causes. Retry does not fix permanently invalid input, does not automatically create a transaction, and does not guarantee "exactly once" delivery.

## 2. Which Part of the Flow Does Retry Advice Wrap?

`RequestHandlerRetryAdvice` is a type of request-handler advice in Spring Integration. It wraps the execution of the target handler, much like an `around advice`; when the handler throws an exception, the advice checks the policy and decides whether to retry, recover, or propagate the exception outward.

Example flow:

~~~text
inbound-adapter -> transform -> httpOutboundGateway -> jdbcOutboundAdapter
                                      ^
                            retry advice placed here
~~~

If the HTTP gateway encounters a transient failure, attaching retry directly to the gateway retries the HTTP call **without automatically re-running the transformer and JDBC steps**. If instead retry is attached to a **poller** wrapping the poll/dispatch operation, the scope can include multiple downstream endpoints executing synchronously; an error at the JDBC step could cause the HTTP gateway to run again. Choose the boundary based on business requirements.

| Configuration location | What gets repeated | When appropriate | Risk |
| --- | --- | --- | --- |
| Request handler advice for HTTP outbound gateway | HTTP handler invocation | Retrying network/API errors at the call site | Resends the same request; external endpoint must be idempotent |
| Request handler advice for `@ServiceActivator` | Advised method/handler invocation | Retrying processing at a specific endpoint | Side effects inside the handler may repeat |
| Poller advice | Message polling and processing cycle under poller mechanics | Retry/transaction at the polling boundary | May re-execute an entire synchronous flow segment |
| Retry at adapter/broker client | Transport/redelivery via adapter/broker | Leveraging ack, nack, rollback, broker retry | May stack multiple retry layers if the handler also retries |

Scope detail: for reply-producing handlers (`AbstractReplyProducingMessageHandler`), request-handler advice is typically applied to `handleRequestMessage()`; sending the reply downstream normally lies **outside** that advice. To wrap both the `handleMessage()` call and the downstream flow, consider `HandleMessageAdvice`/`HandleMessageAdviceAdapter` or placing retry at a different boundary. Verify the actual scope instead of assuming an endpoint advice wraps the entire pipeline.

Retry **only triggers when an exception escapes the advice scope**. If the handler catches the error itself and returns a "failed" value or merely logs and swallows the exception, the advice considers the call successful and will not retry.

## 3. Lifecycle of a Retry and Invocation Counts

A stateless execution proceeds as follows:

~~~mermaid
sequenceDiagram
    participant M as MessageChannel
    participant A as Retry advice
    participant H as Handler
    participant R as Recovery channel
    M->>A: Message
    A->>H: Attempt #1
    H-->>A: Exception
    A->>A: RetryPolicy? Backoff
    A->>H: Attempt #2
    H-->>A: Exception
    A->>A: RetryPolicy? Backoff
    A->>H: Attempt #3
    alt Attempt #3 succeeds
        H-->>A: Result / completion
        A-->>M: Normal completion
    else Attempt #3 fails
        H-->>A: Final exception
        A->>R: RecoveryCallback (if configured)
        A-->>M: Completes per recovery result
    end
~~~

### Important Version Note: Spring Integration 6.x vs. 7.x

The retry API changed between the two generations of Spring Integration. Do not copy retry policy configuration from tutorials targeting a different version:

| Aspect | Spring Integration 6.x | Spring Integration 7.x |
| --- | --- | --- |
| Retry foundation | **Spring Retry** (`org.springframework.retry.*`) | **Spring Framework Retry** (`org.springframework.core.retry.*`) |
| Configuration on `RequestHandlerRetryAdvice` | `setRetryTemplate(org.springframework.retry.support.RetryTemplate)` | `setRetryPolicy(org.springframework.core.retry.RetryPolicy)` or `setBackOff(...)` |
| Attempt count parameter | `maxAttempts` = **total invocations**, including initial attempt | `maxRetries` = **number of retries after the initial attempt** |
| Advice default | Typically **3 total invocations**, no delay | **3 retries after initial attempt** (up to 4 invocations), no delay |
| Stateful API | `RetryStateGenerator` | `setStateKeyFunction(...)` and state cache |
| Recovery | `setRecoveryCallback(...)`, commonly `ErrorMessageSendingRecoverer` | Still supports `setRecoveryCallback(...)` |

**Invocation count example:** `maxAttempts(3)` in Spring Retry 6.x corresponds to **one initial attempt + two retries**. `maxRetries(2)` in Spring Framework Retry 7.x also corresponds to **one initial attempt + two retries**. For this lesson, the primary examples use **Spring Integration 7.x**; section 6 provides the 6.x version.

Do not infer attempt counts solely from property names: measure **how many times the handler is actually invoked** and inspect the active policy. In addition, the default backoff of `RequestHandlerRetryAdvice` may differ from `RetryPolicy.withDefaults()` used standalone; configure it explicitly for critical flows.

## 4. Configuring `RequestHandlerRetryAdvice` with Annotations (Spring Integration 7.x)

You can declare an advice bean and reference it from `@ServiceActivator(adviceChain = "retryAdvice")`:

~~~java
// Spring Integration 7.x, Spring Framework 7.x
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.retry.RetryPolicy;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;

@Configuration
class HandlerRetryConfiguration {

    @Bean("retryAdvice")
    RequestHandlerRetryAdvice retryAdvice() {
        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();

        // 1 initial attempt + up to 2 retries = up to 3 invocations.
        RetryPolicy policy = RetryPolicy.builder()
                .maxRetries(2)
                .delay(Duration.ofMillis(100))
                .multiplier(2.0)
                .maxDelay(Duration.ofMillis(400))
                .build();

        advice.setRetryPolicy(policy);
        return advice;
    }
}
~~~

~~~java
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.ServiceActivator;

@MessageEndpoint
class ShipmentHandler {

    @ServiceActivator(inputChannel = "shipmentRequests",
                      adviceChain = "retryAdvice")
    public void sendShipment(ShipmentRequest request) {
        shippingApi.submit(request); // example business dependency
    }
}
~~~

The `ShipmentHandler` snippet illustrates where to place the annotation, not a standalone runnable program: you need the `ShipmentRequest` type, the `shippingApi` bean, the `shipmentRequests` channel, and context configuration. A more self-contained example is in section 5.

Key tunable properties:

| Property / policy | Role | Usage recommendation |
| --- | --- | --- |
| `maxRetries(n)` | Allows at most `n` retries after the initial attempt | Bound explicitly according to SLA and error characteristics |
| `delay(...)` | Initial wait interval | Avoid hammering an external service that is overloaded |
| `multiplier(...)` | Multiplies the wait interval on subsequent attempts | Exponential backoff suits transient failures |
| `maxDelay(...)` | Caps unbounded delay growth | Protects latency and worker resources |
| `jitter(...)` | Adds randomness to the delay | Reduces synchronized retry storms across multiple workers |
| `includes(...)` / `excludes(...)` | Scopes which exceptions are retried | Retry only transient errors; exclude permanent business errors |
| `setRecoveryCallback(...)` | Runs after retries are exhausted or on non-retryable errors | Log/route to error flow, return a controlled fallback |

In Spring Integration, method exceptions are sometimes wrapped in `MessageHandlingException`/`MessagingException`. When defining `includes`/`excludes`, verify whether the policy inspects the cause chain and test against the **actual observed exception**. Do not filter only by a raw exception class while ignoring wrappers.

### Registration and DSL

`@ServiceActivator`, `@Transformer`, `@Filter`, and `@Splitter` support referencing the bean name via `adviceChain`. In Java DSL, you can attach the advice directly on the endpoint:

~~~java
@Bean
IntegrationFlow shipmentFlow(ShipmentService service,
                             RequestHandlerRetryAdvice retryAdvice) {
    return IntegrationFlow.from("shipmentRequests")
            .handle(service, "sendShipment", e -> e.advice(retryAdvice))
            .get();
}
~~~

The DSL code is an **alternative** to the endpoint annotation above; do not register both consumers on the same `shipmentRequests` channel if the goal is to process each message once. With the XML namespace, request-handler advice is placed inside `<int:request-handler-advice-chain>` and has dedicated retry tags; attribute names differ between 6.x and 7.x, so consult the documentation matching your version.

## 5. Runnable Example: Succeeding After Retry and Recovering When Exhausted

The example below uses Spring Integration 7.x, Spring Framework 7.x, Java 17+, and a compatible Spring Boot version. Put all the code into a **single file** `RetryAdviceDemoApplication.java` in package `demo.integration`; dependencies require the Spring Integration core/starter compatible with Spring Boot. The demo uses `DirectChannel` to observe synchronous invocations and an in-memory counter to simulate failures.

~~~java
package demo.integration;

import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.retry.RetryPolicy;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class RetryAdviceDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RetryAdviceDemoApplication.class, args);
    }

    @Bean("requests")
    MessageChannel requests() {
        return new DirectChannel();
    }

    @Bean("recoveries")
    MessageChannel recoveries() {
        return new DirectChannel();
    }

    @Bean("retryAdvice")
    RequestHandlerRetryAdvice retryAdvice(
            @Qualifier("recoveries") MessageChannel recoveries) {

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryPolicy(RetryPolicy.builder()
                .maxRetries(2)                 // 3 calls total
                .delay(Duration.ofMillis(50))
                .multiplier(2.0)
                .maxDelay(Duration.ofMillis(200))
                .build());

        advice.setRecoveryCallback(
                new ErrorMessageSendingRecoverer(recoveries));
        return advice;
    }

    @Bean
    ApplicationRunner demo(@Qualifier("requests") MessageChannel requests) {
        return args -> {
            requests.send(MessageBuilder.withPayload("temporary")
                    .setHeader("traceId", "trace-101")
                    .build());
            requests.send(MessageBuilder.withPayload("permanent")
                    .setHeader("traceId", "trace-102")
                    .build());
        };
    }
}

@MessageEndpoint
class DemoHandlers {

    private final ConcurrentMap<String, AtomicInteger> invocations =
            new ConcurrentHashMap<>();

    @ServiceActivator(inputChannel = "requests", adviceChain = "retryAdvice")
    public void handle(Message<String> message) {
        String taskId = message.getPayload();
        int attempt = invocations
                .computeIfAbsent(taskId, id -> new AtomicInteger())
                .incrementAndGet();

        System.out.printf("handle %s attempt=%d thread=%s%n",
                taskId, attempt, Thread.currentThread().getName());

        // "temporary" succeeds on attempt 3; "permanent" always fails.
        if (("temporary".equals(taskId) && attempt < 3)
                || "permanent".equals(taskId)) {
            throw new IllegalStateException("Simulated downstream failure");
        }
        System.out.println("DELIVERED " + taskId);
    }

    @ServiceActivator(inputChannel = "recoveries")
    public void onRecovery(ErrorMessage error) {
        Message<?> original = error.getOriginalMessage();
        Throwable cause = error.getPayload();

        System.out.printf("RECOVER original=%s error=%s%n",
                original == null ? "unknown" : original.getPayload(),
                cause.getClass().getSimpleName());
    }
}
~~~

Behavioral outcome:

| Message | Handler invocations | Outcome |
| --- | --- | --- |
| `temporary` | #1 fails, #2 fails, #3 succeeds | Logs `DELIVERED temporary`, nothing sent to recovery |
| `permanent` | #1 fails, #2 fails, #3 fails | One `ErrorMessage` sent to `recoveries`; `onRecovery` logs the error |
| Message with error where handler swallows exception | Usually only once | Advice is unaware of the error; no retry |

Log timing may vary depending on scheduler/CPU; with `DirectChannel` and stateless retry, handler invocations for the same message in this example execute sequentially on the sending thread. `onRecovery` runs synchronously because `recoveries` also uses `DirectChannel`.

**Important note on contract:** `ErrorMessageSendingRecoverer` sends an `ErrorMessage` carrying the final exception to the recovery channel. It does not by itself provide a durable dead-letter store. If the recovery consumer processes the message successfully, the advice can complete without throwing an exception back to the message source. Therefore, in broker-based systems with acks, recovery must ensure the failure is persisted or routed according to the desired guarantee before treating the message as handled.

The `ConcurrentMap` counter is strictly for demonstration and is **not** production retry state, nor does it survive restarts; production systems should use an idempotency key and persist job state in an appropriate store.

## 6. If Your Application Uses Spring Integration 6.x

Do not import `org.springframework.core.retry.RetryPolicy` or use `setRetryPolicy(...)` in Spring Integration 6.x. Instead, use `RetryTemplate` from **Spring Retry** and `setRetryTemplate(...)`:

~~~java
// Spring Integration 6.x + Spring Retry 2.x
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Bean("retryAdvice")
RequestHandlerRetryAdvice retryAdvice() {
    RetryTemplate template = RetryTemplate.builder()
            .maxAttempts(3)               // 1 initial + 2 retries
            .exponentialBackoff(100, 2.0, 400)
            .build();

    RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(template);
    return advice;
}
~~~

This snippet illustrates a bean method inside `@Configuration` and requires importing `org.springframework.context.annotation.Bean`. If you want recovery as in section 5, add `advice.setRecoveryCallback(new ErrorMessageSendingRecoverer(recoveries))` with a declared channel.

With exception-class policies in 6.x, method invocations may throw `MessagingException` wrapping the root error; the API documentation recommends enabling **cause traversal** on the policy when classifying by the underlying cause. APIs and XML attribute names differ across generations; consult the Javadoc matching your actual dependency version.

## 7. Recovery After Attempts Are Exhausted

`RecoveryCallback` determines the final behavior of the retry loop. A common implementation is `ErrorMessageSendingRecoverer`, which publishes an `ErrorMessage` to a channel for handling:

~~~java
RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
advice.setRecoveryCallback(
        new ErrorMessageSendingRecoverer(recoveryChannel));
~~~

Distinguishing the options:

| Final state | Without recovery callback | With `ErrorMessageSendingRecoverer` |
| --- | --- | --- |
| Handler succeeds | Proceeds normally | Proceeds normally, no recovery |
| Retries exhausted, still failing | Exception propagates to caller or error flow at the appropriate boundary | Sends `ErrorMessage` to recovery channel; callback may complete without error per its contract |
| Error classified as non-retryable by policy | Error exits per policy/advice mechanics | May trigger recovery immediately depending on how policy/callback handle it |
| Recovery channel consumer throws exception | Not applicable | Recovery error may propagate back; do not assume recovery always succeeds |

A useful recovery flow should capture at least: **original job key**, **error type + summarized stack trace**, **attempt count/frequency**, **timestamp**, **trace/correlation ID**, and **next action**. For retries that may produce duplicates, record events using an idempotency key.

In durable messaging environments, three strategies are common:

1. **Dead-letter:** move payload + required headers + error details to a DLQ/error table; reprocess later in a controlled manner.
2. **Compensation:** record the failure state and trigger business undo or a repair workflow if the handler already caused earlier side effects.
3. **Fallback:** return an alternative result when the contract genuinely permits it; never turn a data-loss error into "success" with an arbitrary default value.

A `RecoveryCallback` can return an object. For reply-producing handlers, that return value can affect reply semantics; verify the output contract/`requiresReply`. For `void` handlers like in the example, use a recoverer to route errors clearly without fabricating a reply.

### `errorChannel` and `recoveryChannel` Are Not Identical

- **Recovery channel** is passed directly to `ErrorMessageSendingRecoverer`; it is only sent to when that callback executes.
- **`errorChannel`** is Spring Integration's broader error mechanism at boundaries that support sending `ErrorMessage`, especially important for asynchronous/polling consumers.
- If the advice has **no** callback, the exception may go to an error flow via the inbound endpoint/poller mechanism or propagate back to the sender if processed synchronously. You cannot assume every exception will automatically appear on `errorChannel` in all configurations.
- If a recovery callback **swallows the error after recording it**, it can cause upstream to consider the message processed. Ensure the recovery channel has a subscriber, persistence/reliability matching requirements, and clearly defined success semantics.

## 8. Stateless Retry vs. Stateful Retry

### 8.1. Stateless: Operation Is Retried Immediately at the Handler

This is the mode used when no state key is configured. A message enters the endpoint, and the advice invokes the handler multiple times according to the policy within **a single processing turn**. If there is a delay, the processing thread may wait between attempts.

Advantages: simple, easy to test, independent of broker redelivery, suited to fast/idempotent operations.

Limitations: holds the worker thread throughout retry/backoff; if the handler performs blocking I/O and many messages fail, queues back up easily, threads are exhausted, and system-wide latency rises.

### 8.2. Stateful: Relying on the Source to Redeliver the Message

Stateful retry is suited to cases where an external source (JMS/AMQP/Kafka adapter or configured broker) supports redelivery. When the handler fails, the advice maintains retry state keyed by a stable identifier and **throws the exception outward** so the source can rollback/nack/requeue. When the same logical message arrives again, it continues the retry cycle. In Spring Integration 7.x, you can enable this mode with:

~~~java
RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();

advice.setStateKeyFunction(message -> {
    Object eventId = message.getHeaders().get("eventId");
    if (eventId == null) {
        throw new IllegalArgumentException("Missing stable eventId");
    }
    return eventId;
});

// Stateful retry options:
advice.setStateCacheSize(1000);
advice.setNewMessagePredicate(message -> false);
~~~

This is an **illustrative configuration**, not meant to be pasted into the `DirectChannel` demo in section 5. `stateKeyFunction` uses `eventId` from the data source; do not rely on `MessageHeaders.ID` if each broker redelivery constructs a new message with a different ID. In production, a broker/client must actually redeliver the message when the exception is propagated.

| Aspect | Stateless | Stateful |
| --- | --- | --- |
| What triggers the next attempt? | Retry advice within a single invocation | Source/broker redelivers; advice recognizes retry state |
| Requires a stable identity key? | Not required | Yes |
| Waiting between attempts | Can hold the thread across all attempts | Does not hold the thread across redeliveries; each arrival may still wait per backoff |
| Requires redelivery/rollback? | No | Yes, or an equivalent resubmit mechanism |
| State across restarts | No retry state outside the invocation | Default cache is in-memory; **not durable** across restarts |
| Main risks | Thread exhaustion, repeated side effects within one call | Unstable keys, cache eviction, stacked broker retries |

In Spring Integration 7.x, `stateCacheSize` limits the number of stored states (default 100). `newMessagePredicate` determines when a message with the same key starts a new cycle. If entries are evicted from the cache, multiple instances hold separate caches, or the app restarts, retry state can be lost. Therefore, do not use the advice's cache as the source of truth for execution counts across a cluster.

**Watch out for multiplied counts:** the broker may have its own retry policy, the advice has its own retry policy, and the application may have custom retry logic. If all three repeat 3 times, actual task invocations can exceed expectations. Draw retry boundaries clearly and measure before enabling in production.

## 9. Transactions and Advice Ordering: A Decision That Changes Semantics

Request-handler advice can be combined with transaction advice. The advice chain applies in nested wrapping order: the **first** element is the outermost wrapper, and the last element is closest to the handler.

~~~text
Chain A: [retryAdvice, transactionAdvice]
  retry {
      transaction { handler attempt #1 }
      transaction { handler attempt #2 }
      transaction { handler attempt #3 }
  }

Chain B: [transactionAdvice, retryAdvice]
  transaction {
      retry {
          handler attempt #1
          handler attempt #2
          handler attempt #3
      }
      recoveryCallback (if within transaction scope)
  }
~~~

With **Chain A**, when new transactions are created appropriately, each retry attempt can run in its own transaction. With **Chain B**, all attempts may share the same transaction, and a rollback-only state can persist until the end. Neither chain is universally right; base the choice on the atomicity of the operation.

Also consider these contexts:

- A transaction is already open from a poller/inbound adapter or an outer calling method: the inner transaction advice may **join** the existing transaction depending on propagation. Reordering alone does not guarantee a new transaction is created.
- `DirectChannel` keeps the thread synchronous, whereas across an `ExecutorChannel` or polling consumer, the transaction context **does not automatically propagate** to another thread.
- Recovery writing to a DLQ/database also needs appropriate transaction/reliability guarantees. If the message-receiving transaction rolls back after recovery has already been persisted, duplicates or state inconsistencies can occur.
- When a handler has side effects committed before an error (for example, an external API accepted the request before the response timed out), rolling back the database does not undo the external request.

**Design should prioritize idempotency:** use `eventId`/`orderId` as an idempotency key, with a unique constraint/inbox table/deduplication store where appropriate. Retry configuration only decides *when to retry*; it cannot guarantee an external action runs once.

## 10. Threading, Pollers, Executors, and Load Capacity

| Flow style | Which thread does retry impact? | What to monitor |
| --- | --- | --- |
| `DirectChannel` + synchronous handler | Usually the thread calling `send()` | Producer latency, timeouts, exception propagation to caller |
| `ExecutorChannel` before endpoint | Worker thread from executor | Queue backlog, pool size, task rejection rate, in-thread retry |
| `QueueChannel` + polling consumer | Poller/consumer thread | Batch size, polling interval, throughput, transaction/ack semantics |
| Inbound broker listener | Container/listener thread or handoff thread | Broker redelivery, ack/nack, consumer concurrency |
| Handler using async/reactive contract | Depends on implementation/adapter; may cross threads | Whether advice sees the error before the handler returns |

**Do not assume** that any error emitted after a handler returns a `Future`/publisher falls within synchronous retry advice scope. If an asynchronous task reports failure later, use a retry/operator compatible with that abstraction or design a dedicated error flow.

For stateless retry, a simple estimate of per-message cost:

~~~text
worker hold time ≈ sum of attempt durations
                 + sum of backoff intervals
                 + dispatch / recovery overhead
~~~

For example, if a handler times out after 2 seconds and the policy has one initial attempt plus two retries, before even counting backoff, a failing message can occupy a worker for **about 6 seconds**. If 100 messages fail together, a small pool easily exhausts workers and queues grow rapidly. Therefore:

- Set each I/O timeout lower than the total time budget; cap retry counts and delays.
- Apply jitter when multiple consumers may recover together from an outage wave.
- Use a circuit breaker/rate limiter when an external source is slow or overloaded, and ensure intentional advice ordering.
- Use stateful retry/redelivery or non-blocking waiting mechanisms if the workload requires long delays and high throughput.
- Monitor `active threads`, `queue depth`, p95/p99 latency, retry rate, final failure count, and recovery rate.

## 11. Selecting Retryable Errors and Preventing Duplicate Side Effects

| Scenario | Should you retry? | Notes |
| --- | --- | --- |
| HTTP 503/429, connection reset, network timeout | Possibly | Exponential backoff, rate limit, overall deadline, idempotency key |
| Resolvable deadlock / optimistic lock error | Possibly | Depends on transaction boundary and business logic |
| Invalid schema input, missing required fields | Usually no | Route to validation/error flow |
| Persistent authentication/authorization rejection | Usually no | Fix configuration or token; endless retries add load and log noise |
| HTTP 409 from permanent business conflict | Depends on contract | Distinguish temporary conflict from final state |
| External operation succeeded but response timed out | Very cautiously | May send duplicates; require idempotency or status lookup before retrying |

For handlers calling external services, apply practical duplicate-prevention measures:

1. Assign a stable `operationId` for the same logical command.
2. Send `operationId` in a header or body per the target contract.
3. Have the receiving system store results/deduplicate for an appropriate retention window.
4. After a timeout, if a status-query API exists, check status before resending.
5. Separate non-idempotent operations from the retried segment if possible, or use the outbox/inbox pattern.

Special note for routers/filters: when a call inside advice scope sends synchronously to another channel, downstream errors sometimes bubble up the same stack; however, exact scope depends on the adapter and `handleRequestMessage`. Test with simulated failures at **each location**, rather than assuming every branch is retried.

## 12. Runtime Observability and Diagnostics

When investigating a message that was processed repeatedly or disappeared, check in order:

1. **Retry point:** which endpoint is the advice attached to? Was handler `adviceChain` confused with poller advice? Is the handler bean created and its lifecycle running?
2. **Exception type:** what exception leaves the handler, is it wrapped in `MessagingException`, and does the policy classify that error type accurately?
3. **Attempt count:** how many times was the handler actually invoked for the same logical event ID, and is broker redelivery occurring outside the advice?
4. **Stop conditions:** how are max retries, timeout, backoff, recoverer, and recovery channel configured?
5. **Thread/transaction:** what is the thread name, is a transaction active, and where are the async boundaries?
6. **Side effects:** did an external API/database partially commit before failing? Is deduplication working?
7. **Recovery:** did `ErrorMessage` reach the recovery channel, is there a consumer, and was the error record persisted before ack?

### Symptoms and Troubleshooting

| Symptom | Common cause | How to check |
| --- | --- | --- |
| Handler runs only once despite advice | Method swallows exception, policy does not retry, wrong bean name, advice not attached to handler | Add counter/log at handler entry and verify exception escapes |
| Observed attempt count differs from expected | Confusing `maxRetries` with `maxAttempts`, broker redelivering on its own, multi-layer retries | Check version and measure total invocations per eventId |
| Recovery receives no messages | Missing `RecoveryCallback`, error never reached callback, recovery channel has no consumer or recovery itself fails | Inspect callback bean, channel name, and stack traces |
| Producer hangs for a long time | Stateless backoff holds thread, large I/O timeout | Check thread dumps, timeouts, wait durations, and executor saturation |
| A payment/order is processed twice | Handler created side effect then threw error, non-idempotent retry | Check idempotency key, outbox, and target service logs |
| Direct flow test catches exception; production does not | Production uses `ExecutorChannel`/poller, error occurs on another thread | Configure `errorChannel` and observe workers |
| Stateful retry count does not increment across redeliveries | Key changes, state cache evicted, multiple instances or restart | Use a stable source key, inspect cache and broker delivery ID |
| Transaction keeps rolling back even after retry succeeds | Transaction was marked rollback-only on an earlier attempt | Check propagation and advice/transaction ordering |

You can emit metrics such as `handler.retry.attempt`, `handler.retry.recovered`, `handler.retry.exhausted`, and `handler.latency` tagged with **endpoint**, **exception class**, and **outcome**. Avoid tagging directly with orderId/eventId in metrics systems due to high cardinality; put those in traces/logs carefully. All logs should include `traceId`/`correlationId` to connect steps across thread switches.

## 13. Hands-On Exercises

1. **Verify stateless retry:** run the code in section 5; count exact invocations for `temporary` and `permanent`, and observe `recoveries` receiving only the final failure message.
2. **Exclude non-retryable errors:** create a dedicated validation exception and use the version-appropriate `excludes(...)` policy. Verify business-rejected messages do not waste three invocations.
3. **Backoff and threads:** test delays of 100/200/400 ms on a synchronous flow, log `Thread.currentThread().getName()` and `send()` latency; observe worker hold cost.
4. **Switch to async:** replace the input `DirectChannel` with an `ExecutorChannel` backed by a configured `TaskExecutor`. Compare where exceptions are caught, when `send()` returns, and how error/recovery moves through the flow.
5. **Recovery failure:** make the `recoveries` consumer throw a test exception, observe how the sender/transaction/broker reacts, then restore the recovery handler.
6. **Stateful:** with an inbound broker that supports real redelivery, configure keying by `eventId`; trigger rollback then redelivery and verify retry state. Ensure you do not use newly generated message IDs as the key.
7. **Transaction and idempotency:** use a test database with a unique key on `operationId`; simulate a side effect before throwing an error and verify retries do not create two records.

### Pre-Production Design Checklist

- Retry wraps the right handler and scope, without unintentionally re-running multiple endpoints.
- Retry count is configured using the API of the **version in use** and is bounded.
- Timeouts, backoff (and jitter if needed) are set; policy excludes permanent failures.
- Side effects are safe on repeat via idempotency/deduplication.
- Recovery has a consumer and durable error storage when the contract requires it.
- Broker ack/redelivery, transactions, pollers, and executors are verified together.
- Metrics, correlation logs, and alerts for retry storms and recovery volume are in place.

## 14. Official References

- [Spring Integration 7.x — Provided Advice Classes / Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): stateless/stateful retry, recovery callback, retry policy, and configuration.
- [Spring Integration — Advising Endpoints Using Annotations](https://docs.spring.io/spring-integration/reference/handler-advice/advising-with-annotations.html): using `adviceChain` with endpoint annotations.
- [Spring Integration — Ordering Advices within Advice Chain](https://docs.spring.io/spring-integration/reference/handler-advice/order.html): nesting order between retry and transaction advices.
- [Spring Integration API — RequestHandlerRetryAdvice](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html): API, state cache, and 7.x setters.
- [Spring Integration API — ErrorMessageSendingRecoverer](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/ErrorMessageSendingRecoverer.html): publishing `ErrorMessage` after retry exhaustion.
- [Spring Framework 7.x — Resilience Features](https://docs.spring.io/spring-framework/reference/core/resilience.html): `RetryPolicy`, `maxRetries`, backoff, exception classification.
- [Spring Integration 6.4 API — RequestHandlerRetryAdvice](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html): `setRetryTemplate` and 6.x stateful API.
