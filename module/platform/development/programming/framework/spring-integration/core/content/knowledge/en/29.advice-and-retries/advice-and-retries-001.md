# RequestHandlerRetryAdvice

## 1. Objectives and Scope

In the **Advice and Retries** chapter of the **SPRING_INTEGRATION_CORE** module, this lesson explains how to use `RequestHandlerRetryAdvice` to protect a message-processing step against transient errors. The content connects `Message`, `MessageChannel`, endpoints, and Java DSL into a flow with a success path, a recovery path, and a way to verify behavior.

After this lesson, you will be able to:

- Attach retry directly to the handler that needs protection.
- Distinguish the initial invocation from retry attempts.
- Choose retryable exceptions, wait times, and behavior when retries stop.
- Use `ErrorMessageSendingRecoverer` without mistaking recovery for a successful business outcome.
- Distinguish stateless retry from stateful retry and broker redelivery.
- Design for idempotency and test actual invocation counts.

**Version scope:** the main examples use **Spring Integration 7.x and Spring Framework 7.x**, with Java 17 or later. The final section illustrates the corresponding configuration for **Spring Integration 6.x and Spring Retry 2.x**. Starting in Spring Integration 7.0, retry moves to the Spring Framework API; 6.x examples using `setRetryTemplate(...)` must be migrated when upgrading. [Source: 6.x to 7.0 Migration Guide](https://github.com/spring-projects/spring-integration/wiki/Spring-Integration-6.x-to-7.0-Migration-Guide).

This lesson assumes you already know the structure of `Message<?>`, how to declare channel beans, and how a simple `IntegrationFlow` works.

## 2. The Problem: Calling a Partner That Encounters Transient Failures

Suppose an application receives inventory reservation requests:

~~~text
orderRequests -> normalize -> call reservation service -> orderReplies
~~~

The partner service is occasionally unavailable. The first call may fail, while a subsequent call after a short wait may succeed.

Two types of failures need to be handled differently:

| Scenario | Assessment in Example | Handling Approach |
| --- | --- | --- |
| Partner temporarily stops accepting requests and confirms no operation was performed | Recoverable after a short wait | Bounded retry |
| Payload contains an invalid quantity | Resending the same payload will not fix the error | Stop retrying and record the failed request |
| Request is rejected due to a business rule | Requires a new business decision | Return a rejection result or route to a dedicated branch |
| Timeout after the reservation request was already sent | Unknown whether the partner executed the operation | Check status or use idempotency before resending |
| Partner service is down for an extended period | Short-term retry is unlikely to help | Consider a circuit breaker, queue, and scheduled reprocessing |

Choosing retry requires answering three questions simultaneously: whether the error is likely to clear, whether the operation can be safely repeated, and whether enough time budget remains.

In the hands-on section, `TransientPartnerException` simulates a partner that has not performed the operation. This is an exercise assumption; a real network timeout does not inherently carry that guarantee.

## 3. Which Part of the Flow Does the Advice Wrap?

`RequestHandlerRetryAdvice` is an advice for message handlers. For Spring Integration reply-producing handlers, it wraps request handling at the endpoint. This allows you to repeat the partner call at a specific endpoint without proactively re-running earlier normalization steps or downstream reply processing. [Source: Adding Behavior to Endpoints](https://docs.spring.io/spring-integration/reference/handler-advice.html).

~~~mermaid
flowchart LR
    A["Request Message"] --> B["Normalize"]
    B --> C["Partner-calling Endpoint"]
    C --> D["Process Reply"]
    D --> E["Result"]
    subgraph R["Request handler advice scope"]
        C --> F{"Handler succeeded?"}
        F -->|"Retryable error, attempts left"| G["Backoff"]
        G --> C
    end
    F -->|"Stop after error"| H["Recover or throw error"]
~~~

The diagram shows the processing boundary; only a successful reply continues to the reply-processing step.

Example flow:

~~~text
transformer -> reserveHandler [retry] -> auditHandler
~~~

- If `reserveHandler` throws an exception matching the policy, that handler itself is invoked again.
- If the transformer fails before reaching `reserveHandler`, this advice has not executed yet.
- If `auditHandler` fails after `reserveHandler` returns a reply, do not expect the advice on `reserveHandler` to retry `auditHandler`.
- If the code inside `reserveHandler` calls three services sequentially, all three calls fall within the work that may be repeated.

The endpoint boundary determines how you split endpoints. You should place an operation that needs retry into a handler with a clear responsibility, especially when different operations have different side effects.

With a custom `MessageHandler`, the exact scope also depends on which method the advice intercepts and what work the handler performs itself. `AbstractRequestHandlerAdvice` supports `handleRequestMessage(...)` on reply-producing handlers and `handleMessage(...)` on other message handlers. [Source: AbstractRequestHandlerAdvice](https://raw.githubusercontent.com/spring-projects/spring-integration/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/handler/advice/AbstractRequestHandlerAdvice.java).

### Distinguishing Retry Locations

| Location | Work That May Be Repeated | What Must Be Determined |
| --- | --- | --- |
| `endpoint.advice(retryAdvice)` | Request processing at the advised handler | Is the handler small and safe to repeat? |
| Advice wrapping a poller | Work inside the callback wrapped by the poller | Which synchronous endpoints belong to the same callback? |
| Retry in an HTTP client or SDK | Calls made by the client | Does the client already have default retries enabled? |
| Retry at the service layer | Protected method or code block | Is it also wrapped by an endpoint retry? |
| Broker redelivery | Message redelivered into the consumer flow | Will steps before the handler run again? |

Starting from the advice location, trace the actual path of the message before deciding on the retry count.

## 4. Structure of a Retry Cycle in 7.x

Key concepts:

| Component | Role |
| --- | --- |
| `RequestHandlerRetryAdvice` | Wraps handler invocation and coordinates re-execution |
| `org.springframework.core.retry.RetryPolicy` | Classifies exceptions and provides the backoff strategy |
| Backoff | Defines the wait interval and when retry attempts are exhausted |
| `org.springframework.integration.core.RecoveryCallback` | Handles the case when the retry cycle ends in failure |
| `ErrorMessageSendingRecoverer` | A recovery callback that sends an error message to a channel |
| `org.springframework.core.retry.RetryListener` | Monitors events during the retry process |

In 7.x, the policy is configured via `setRetryPolicy(...)`. When no state key is provided, the advice runs in stateless mode. The default advice configuration allows up to **three retries after the initial attempt**, with no wait between calls. You should declare the policy explicitly rather than relying on defaults. [Source: RequestHandlerRetryAdvice API](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

### 4.1. Counting Execution Attempts Correctly

With the policy in this lesson:

~~~java
RetryPolicy.builder()
        .maxRetries(2)
        .delay(Duration.ofMillis(100))
        .multiplier(2.0)
        .maxDelay(Duration.ofSeconds(1))
        .build();
~~~

`maxRetries(2)` allows two retry attempts in addition to the initial call. Spring Framework's formula is:

~~~text
Maximum invocations = 1 + maxRetries
~~~

The example above allows at most three invocations. `maxRetries(0)` still permits the initial attempt. [Source: Spring Framework 7.0 RetryPolicy.Builder](https://docs.spring.io/spring-framework/docs/7.0.0/javadoc-api/org/springframework/core/retry/RetryPolicy.Builder.html).

With continuous transient errors and no jitter configured:

| Handler Execution | Role | Wait Before This Attempt |
| --- | --- | --- |
| 1 | Initial attempt | None |
| 2 | First retry | 100 ms |
| 3 | Second retry | 200 ms |
| After attempt 3 fails | Recovery or error propagation | No 4th invocation |

This is the maximum count. Succeeding on the second attempt finishes immediately; a non-retryable error can terminate on the first attempt.

### 4.2. Errors Must Surface as Exceptions

The advice observes exceptions thrown within the scope of the handler invocation. If the handler catches an exception and returns `null`, returns the string `"FAILED"`, or returns an object containing an error status, the advice does not automatically interpret those values as reasons to retry.

~~~java
// Error representation intended for the example's policy:
throw new TransientPartnerException("Partner is temporarily unavailable");
~~~

With an HTTP client, you must clearly decide which response codes are translated into transient exceptions and which represent business outcomes. Receiving HTTP 503 as a normal response object will not automatically trigger an exception-based policy.

A `Mono` or `CompletableFuture` returned successfully can also signal an error after the method itself has returned. The examples in this lesson use synchronous processing; with asynchronous or reactive processing, the retry mechanism must be placed at a boundary that actually observes the failure.

## 5. Complete Java DSL Example

### 5.1. Environment and Flow Contract

In an application whose dependencies are managed by Spring Boot or a BOM, use the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-core</artifactId>
</dependency>
~~~

Choose a version set compatible with Spring Integration 7.x and Spring Framework 7.x. The dependency above omits the version because it assumes the project manages versions centrally. For the main example, you do not need to add Spring Retry or enable `@EnableRetry`: the advice is created as a bean and attached directly to the endpoint.

The hands-on flow uses:

- `orderRequests`: `DirectChannel`, processed synchronously on the sending thread.
- `orderReplies`: `QueueChannel` holding successful reservation results.
- `exhaustedOrders`: `QueueChannel` holding errors after retries stop.
- `SimulatedPartner`: simulated partner to observe invocation counts.

The two queues in this lesson reside in memory and are read manually or in tests. They do not constitute a durable error storage system.

### 5.2. Configuration and Handler

Place the following code in `RetryDemoConfig.java`. Data types and exceptions are declared inside the same class so the example is self-contained.

~~~java
import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.retry.RetryPolicy;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.MessageChannel;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class RetryDemoConfig {

    @Bean
    public DirectChannel orderRequests() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel orderReplies() {
        return new QueueChannel();
    }

    @Bean
    public QueueChannel exhaustedOrders() {
        return new QueueChannel();
    }

    @Bean
    public SimulatedPartner simulatedPartner() {
        return new SimulatedPartner();
    }

    @Bean
    public RequestHandlerRetryAdvice orderRetryAdvice(
            @Qualifier("exhaustedOrders") MessageChannel recoveryChannel) {

        RetryPolicy policy = RetryPolicy.builder()
                .maxRetries(2)
                .delay(Duration.ofMillis(100))
                .multiplier(2.0)
                .maxDelay(Duration.ofSeconds(1))
                .includes(TransientPartnerException.class)
                .excludes(InvalidOrderException.class)
                .build();

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryPolicy(policy);
        advice.setRecoveryCallback(
                new ErrorMessageSendingRecoverer(recoveryChannel));
        return advice;
    }

    @Bean
    public IntegrationFlow orderFlow(
            SimulatedPartner partner,
            RequestHandlerRetryAdvice orderRetryAdvice) {

        return IntegrationFlow.from("orderRequests")
                .handle(OrderRequest.class,
                        (request, headers) -> partner.reserve(request),
                        endpoint -> endpoint
                                .id("reserveOrder")
                                .advice(orderRetryAdvice))
                .channel("orderReplies")
                .get();
    }

    public record OrderRequest(
            String orderId,
            int simulatedFailuresBeforeSuccess) {
    }

    public record OrderReceipt(String orderId, String status) {
    }

    public static class TransientPartnerException extends RuntimeException {
        public TransientPartnerException(String message) {
            super(message);
        }
    }

    public static class InvalidOrderException extends RuntimeException {
        public InvalidOrderException(String message) {
            super(message);
        }
    }

    public static class SimulatedPartner {

        private final ConcurrentHashMap<String, AtomicInteger> attempts =
                new ConcurrentHashMap<>();

        public OrderReceipt reserve(OrderRequest request) {
            if (request.orderId() == null || request.orderId().isBlank()) {
                throw new InvalidOrderException("orderId must have a value");
            }

            int attempt = attempts
                    .computeIfAbsent(request.orderId(), key -> new AtomicInteger())
                    .incrementAndGet();

            if (request.simulatedFailuresBeforeSuccess() < 0) {
                throw new InvalidOrderException(
                        "Simulated failure count must not be negative");
            }

            if (attempt <= request.simulatedFailuresBeforeSuccess()) {
                throw new TransientPartnerException(
                        "Partner not ready, attempt " + attempt);
            }

            return new OrderReceipt(request.orderId(), "RESERVED");
        }

        public int attemptsFor(String orderId) {
            AtomicInteger count = attempts.get(orderId);
            return count == null ? 0 : count.get();
        }
    }
}
~~~

The policy selects only `TransientPartnerException` for retry. Excluding `InvalidOrderException` makes the intent for business validation errors explicit. In the 7.x API, exception classification also inspects nested causes, which is useful when a handler wraps the original error in a messaging exception. [Source: RetryPolicy](https://raw.githubusercontent.com/spring-projects/spring-framework/v7.0.0/spring-core/src/main/java/org/springframework/core/retry/RetryPolicy.java).

The simulator keeps a separate counter per `orderId`. Each scenario should use a different order ID or a fresh application context so previous attempt counts do not affect results. This counter is only for the exercise, not a mechanism to prevent duplicate reservations.

### 5.3. Sending a Request

Place the following snippet inside a method of a runner program:

~~~java
try (var context =
        new org.springframework.context.annotation.AnnotationConfigApplicationContext(
                RetryDemoConfig.class)) {

    var input = context.getBean("orderRequests",
            org.springframework.messaging.MessageChannel.class);
    var replies = context.getBean("orderReplies",
            org.springframework.integration.channel.QueueChannel.class);

    var request = new RetryDemoConfig.OrderRequest("ORD-100", 2);

    input.send(org.springframework.messaging.support.MessageBuilder
            .withPayload(request)
            .setHeader("businessRequestId", "REQ-100")
            .build());

    var reply = replies.receive(1_000);
    System.out.println(reply == null ? "No reply" : reply.getPayload());
}
~~~

`ORD-100` is configured to fail twice and then succeed. The handler is invoked three times and produces exactly one `OrderReceipt` on `orderReplies`.

If you change the simulated failure count to `99`, all three calls fail. Recovery sends an `ErrorMessage` to `exhaustedOrders`, and the flow produces no `OrderReceipt`.

In this synchronous setup, backoff occurs inside `input.send(...)`. The `replies.receive(1_000)` timeout starts when `receive` is called; it does not limit the time already spent in `send`.

## 6. Recovery and Error Paths

### 6.1. Without a Recovery Callback Configured

When the handler continues failing until the policy stops and no recovery callback is configured, the advice invocation ends by throwing an exception.

With the `DirectChannel` in the example, the sender is on the same call stack and can receive the exception from `send(...)`. Simply declaring a bean named `errorChannel` does not turn every synchronous error into a message on that channel. For a gateway or an asynchronous consumer, the error routing path depends on that component's configuration. [Source: Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

### 6.2. Configuring ErrorMessageSendingRecoverer

`ErrorMessageSendingRecoverer` wraps the final throwable of the cycle into an `ErrorMessage` and sends it to the recovery channel. Passing the channel to the constructor explicitly designates where endpoint failures go. [Source: ErrorMessageSendingRecoverer API](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/ErrorMessageSendingRecoverer.html).

In the current configuration:

~~~text
Handler succeeds -> OrderReceipt -> orderReplies
Handler stops with error -> ErrorMessage -> exhaustedOrders
~~~

When sending the error succeeds, the recoverer returns `null`. Therefore, the recovery path does not automatically generate a substitute business reply. [Source: ErrorMessageSendingRecoverer 7.0 source](https://raw.githubusercontent.com/spring-projects/spring-integration/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/handler/advice/ErrorMessageSendingRecoverer.java).

You must distinguish between:

- The handler completing the business operation.
- The system accepting failure information onto the recovery channel.
- The system durably persisting failure information for later processing.

These three events mean different things. `send(...)` not throwing an exception after recovery does not prove that the partner succeeded in reserving inventory.

If the endpoint must return a reply, or the call arrives through a gateway expecting a response, explicitly design the contract for when recovery returns `null`. You may need a typed failure result, an exception propagated outward, or an asynchronous mechanism with a lookup ID. Never treat the absence of a reply as an implicit success.

### 6.3. Recovery Is Not a Separate Retry Attempt

In the 7.x stateless branch, stopping due to a non-retryable exception can also trigger the recovery callback right after the initial call. Therefore, the name `exhaustedOrders` in the example means the destination for failures when the cycle stops; it does not guarantee every message arriving there was attempted three times.

If `InvalidOrderException` needs to be returned to the caller while partner errors go to the recovery queue, design a validation branch before the endpoint or write a recovery callback that distinguishes the two groups.

If the recovery callback itself fails—for example, unable to send the error message—the recovery error may propagate to the caller. The callback is not automatically retried by the handler's retry loop. In the 7.0 source code, the callback is invoked after the retry execution terminates with `RetryException`. [Source: RequestHandlerRetryAdvice source](https://raw.githubusercontent.com/spring-projects/spring-integration/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.java).

### 6.4. Returning a Typed Fallback

Spring Integration 7.x's `RecoveryCallback` takes two parameters, `context` and `cause`; its return value can replace the failed processing result. [Source: RecoveryCallback](https://docs.spring.io/spring-integration/docs/7.0.0/api/org/springframework/integration/core/RecoveryCallback.html).

The snippet below is an **alternative** to the error-sending recoverer:

~~~java
public record ReservationOutcome(String status) {
}

// Inside the advice factory method:
advice.setRecoveryCallback((context, cause) ->
        new ReservationOutcome("PENDING_REVIEW"));
~~~

Before using it, update the output contract so downstream steps understand `ReservationOutcome`, or use a unified result type for both success and failure. Never substitute `"RESERVED"` as a fallback reservation result when you do not know whether the operation succeeded.

If you both send an error and return a fallback, implement both actions explicitly in the callback and decide how the system should react if sending the error fails.

## 7. Choosing Policy and Backoff Within a Time Budget

### 7.1. Classify Errors Close to the Actual Call

Design exceptions in the client layer according to how they should be handled:

~~~text
Errors where retrying may help -> TransientPartnerException
Invalid data or immutable rule errors -> InvalidOrderException / rejection result
Unclear whether side effects occurred -> decide based on idempotency
~~~

Avoid catching every `RuntimeException` and converting it into a transient error. That approach can cause programming bugs, misconfigurations, or invalid data to be retried repeatedly.

For a specific API, retrying HTTP 429 or 503 should follow the service contract, rate limits, and signals such as `Retry-After`. The fixed exception policy in this lesson does not automatically parse HTTP headers to choose wait schedules.

### 7.2. Calculating Worst-Case Duration

Suppose the client has a per-call timeout `t`, maximum invocations `A`, and backoff intervals `b1...b(A-1)`. Planning estimate:

~~~text
T ≈ A × t + total backoff + other processing overhead
~~~

With three invocations, each bounded at 800 ms, and backoffs of 100 ms and 200 ms:

~~~text
T ≈ 3 × 800 + 100 + 200 = 2,700 ms
~~~

This figure excludes connection pool wait times, thread scheduling, serialization, reply transmission, and recovery. It is an estimate assuming all waiting inside a single call is already bounded by 800 ms.

If the caller has a one-second deadline, this configuration is unsuitable. Reduce the attempt count, shorten the per-attempt timeout, or switch to asynchronous processing with a clear contract.

Retry does not replace connect timeouts, read timeouts, or client time limits. A hanging call holds the retry loop on that attempt.

### 7.3. Impact on Threads and System Load

With synchronous stateless retry, the processing thread waits during backoff. A pool of 20 workers simultaneously waiting on a partner may have no workers left to accept other messages.

To assess the impact, consider all of:

- Number of messages being processed concurrently.
- Total duration a single message can occupy a worker.
- Connection count and partner-side limits.
- Queue depth when ingestion rate exceeds processing rate.

Exponential backoff reduces repeat call frequency. Jitter prevents instances from waking up in lockstep. The example can add `.jitter(Duration.ofMillis(30))` to the builder; in that case, do not rely on the 100 ms and 200 ms table values as exact timings. Jitter and delay bounds follow the builder API of the version in use. [Source: RetryPolicy.Builder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/retry/RetryPolicy.Builder.html).

If waiting minutes or hours is required, consider broker delays, reprocessing queues, or an appropriate scheduler. Holding workers idle for long durations typically reduces flow throughput.

### 7.4. Avoiding Multiplicative Retries Across Layers

Design example:

~~~text
Endpoint: up to 3 handler invocations
HTTP client: up to 3 HTTP calls per handler call to the client
Broker: up to 5 message deliveries across the entire lifecycle
~~~

If all three mechanisms exhaust their attempts and errors continue propagating so the broker redelivers, the number of HTTP calls can reach:

~~~text
3 × 3 × 5 = 45
~~~

This calculation follows the stated assumptions, not a Spring default. If recovery swallows the error and the listener acknowledges the message, the broker may stop redelivering.

Assign retry responsibility per layer and compute the total calls reaching the target system.

## 8. Stateless Retry and Stateful Retry

### 8.1. Stateless: Entire Cycle Within One Handler Entry

The Java DSL example above uses stateless retry:

~~~text
Single message send
  -> handler call 1: error
  -> wait
  -> handler call 2: error
  -> wait
  -> handler call 3: success or recovery
~~~

The caller does not need to resend the message for the second retry attempt to happen. Therefore, counting one `send(...)` call is not enough to infer only one interaction with the partner.

### 8.2. Stateful: Preserving State Across Redeliveries

With stateful retry, the exception is thrown back to the caller during processing, while retry state is retained to recognize redeliveries of the same operation. The message source—such as a properly configured broker and listener—must be capable of redelivering the message.

In 7.x, supplying `stateKeyFunction` switches the advice to stateful mode. `newMessagePredicate` allows starting a fresh cycle, and `stateCacheSize` limits the state cache; by default, the cache holds 100 entries. [Source: Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html).

The following stateful bean example **must not be used as a drop-in replacement for the stateless example without a redelivery mechanism**:

~~~java
@Bean
public RequestHandlerRetryAdvice statefulOrderRetryAdvice() {
    RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();

    advice.setRetryPolicy(RetryPolicy.builder()
            .maxRetries(2)
            .delay(Duration.ofMillis(100))
            .includes(RetryDemoConfig.TransientPartnerException.class)
            .build());

    advice.setStateKeyFunction(message -> {
        String key = message.getHeaders()
                .get("businessRequestId", String.class);

        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException(
                    "Stateful retry requires a stable businessRequestId");
        }
        return key;
    });

    advice.setStateCacheSize(1_000);
    return advice;
}
~~~

This snippet only configures the advice; it does not create a broker consumer, transaction, acknowledgment, or message redelivery schedule.

Lifecycle example:

~~~text
Delivery 1, key=REQ-200 -> handler fails -> caller receives error
Message source decides to redeliver
Delivery 2, key=REQ-200 -> resumes state -> handler is retried
~~~

Do not use `MessageHeaders.ID` as the default key when a message may be reconstructed on redelivery. The key must be stable for **the same business operation**, potentially combining tenant, operation type, and request ID to avoid colliding two distinct tasks.

Stateful does not mean every backoff is non-blocking for threads. In the 7.0 implementation, a redelivery may wait according to the backoff before invoking the handler; the message source remains responsible for redelivery. The state cache also lives inside the advice instance and does not automatically become durable shared memory across nodes. [Source: 7.0 stateful retry implementation](https://raw.githubusercontent.com/spring-projects/spring-integration/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.java).

If the process restarts or a cache entry is evicted when full, do not treat this counter as a permanent global limit. For such requirements, use a durable mechanism at the broker or an appropriate data store.

### 8.3. Comparison for Choosing

| Criterion | Stateless | Stateful |
| --- | --- | --- |
| Who feeds the message into the next attempt? | Advice invokes internally | Caller or message source redelivers |
| Needs a stable correlation key? | Not needed for internal retry state | Yes |
| Automatically creates broker redelivery? | No | No |
| Thread behavior | Can block for the entire cycle | Can block during the redelivered processing attempt |
| Relationship with transactions | Must check the enclosing transaction scope | Typically must coordinate with source rollback/redelivery |
| Good starting point for | Short synchronous calls with transient errors | Broker flows with an explicit redelivery design |

## 9. Idempotency, Transactions, and Advice Ordering

### 9.1. Retries Can Repeat Side Effects

Hypothetical scenario:

1. The partner reserves inventory successfully.
2. The connection drops before the application receives the response.
3. The client reports a timeout.
4. The handler resends the reservation request.

If each call creates a new reservation, retries can reserve inventory twice.

A design can use `businessRequestId` as the idempotency key for the same operation. The party performing the reservation must store the key and result durably, ensuring key checks and business updates happen in a suitably atomic manner.

Simply adding a header to `Message` does not create idempotency. The client must pass the key to the partner, and the partner must process the key according to an agreed contract.

Nor can you treat the stateful retry cache as a deduplication store: the cache serves retry state and has a different lifecycle from business results.

### 9.2. Retry Does Not Automatically Create Transactions

Attaching `RequestHandlerRetryAdvice` does not open a new transaction per attempt by default.

If a transaction wraps the entire retry cycle, the first attempt may already mark the transaction as rollback-only. A subsequent handler attempt that appears to succeed may still fail at commit time.

Two shapes to distinguish:

~~~text
Transaction
  -> Retry
      -> Handler
~~~

~~~text
Retry
  -> Transaction
      -> Handler
~~~

The second shape can allow a fresh transaction on each attempt if the advice, proxy, and propagation are actually configured to do so. Looking at the order on paper is not enough; you must also check for any outer active transaction.

A local database rollback also does not undo a successful HTTP call at a partner. Flows spanning multiple systems often need idempotency, an outbox, or an appropriate compensation mechanism.

### 9.3. Advice Has Nesting Order

In Java DSL, `advice(a, b)` applies advice in nested order. [Source: ConsumerEndpointSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/ConsumerEndpointSpec.html).

When combining retry with timing or transaction advice, write out the desired nesting explicitly:

~~~text
metrics -> retry -> handler
~~~

Can be used to observe the duration of the entire cycle.

~~~text
retry -> metrics -> handler
~~~

Can be used to observe each invocation inside the retry loop, depending on how the metrics advice is implemented.

Also check which advice catches and handles exceptions. If an inner advice converts an error into a normal result, the outer retry advice will no longer see that error.

## 10. Testing Behavior by Invocation Counts and Output Paths

Do not just verify that the application starts. Observe simultaneously the number of handler invocations, the number of replies, and the number of error messages.

### 10.1. Test Matrix

With the stateless configuration from Section 5:

| Simulated Input | Expected Invocations | `orderReplies` | `exhaustedOrders` |
| --- | --- | --- | --- |
| No error | 1 | 1 receipt | 0 |
| Transient error twice then success | 3 | 1 receipt | 0 |
| Continuous transient error | 3 | 0 | 1 ErrorMessage |
| `simulatedFailuresBeforeSuccess = -1`, valid orderId | 1 | 0 | 1 ErrorMessage |

The last row tests an exception excluded from retry, which still enters recovery in the configured stateless branch.

### 10.2. JUnit 5 Example

Place the test in the same package as `RetryDemoConfig` and add JUnit Jupiter through the project's test dependency set. Each test opens a fresh context to isolate counters and queues.

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class RetryDemoConfigTest {

    @Test
    void retriesTwiceThenProducesOneReceipt() {
        try (var context =
                new AnnotationConfigApplicationContext(RetryDemoConfig.class)) {

            var request = new RetryDemoConfig.OrderRequest("ORD-OK", 2);
            send(context, request);

            var partner = context.getBean(
                    RetryDemoConfig.SimulatedPartner.class);
            var replies = context.getBean("orderReplies", QueueChannel.class);
            var errors = context.getBean("exhaustedOrders", QueueChannel.class);

            Message<?> reply = replies.receive(0);

            assertEquals(3, partner.attemptsFor("ORD-OK"));
            assertNotNull(reply);
            assertEquals(
                    new RetryDemoConfig.OrderReceipt("ORD-OK", "RESERVED"),
                    reply.getPayload());
            assertNull(replies.receive(0));
            assertNull(errors.receive(0));
        }
    }

    @Test
    void publishesOneErrorAfterThreeFailedCalls() {
        try (var context =
                new AnnotationConfigApplicationContext(RetryDemoConfig.class)) {

            var request = new RetryDemoConfig.OrderRequest("ORD-FAIL", 99);
            assertDoesNotThrow(() -> send(context, request));

            var partner = context.getBean(
                    RetryDemoConfig.SimulatedPartner.class);
            var replies = context.getBean("orderReplies", QueueChannel.class);
            var errors = context.getBean("exhaustedOrders", QueueChannel.class);

            ErrorMessage error =
                    assertInstanceOf(ErrorMessage.class, errors.receive(0));

            assertEquals(3, partner.attemptsFor("ORD-FAIL"));
            assertNull(replies.receive(0));
            assertTrue(hasCause(error.getPayload(),
                    RetryDemoConfig.TransientPartnerException.class));
            assertNotNull(error.getOriginalMessage());
            assertEquals(request, error.getOriginalMessage().getPayload());
            assertNull(errors.receive(0));
        }
    }

    @Test
    void doesNotRetryInvalidOrder() {
        try (var context =
                new AnnotationConfigApplicationContext(RetryDemoConfig.class)) {

            send(context,
                    new RetryDemoConfig.OrderRequest("ORD-INVALID", -1));

            var partner = context.getBean(
                    RetryDemoConfig.SimulatedPartner.class);
            var errors = context.getBean("exhaustedOrders", QueueChannel.class);
            var replies = context.getBean("orderReplies", QueueChannel.class);

            ErrorMessage error =
                    assertInstanceOf(ErrorMessage.class, errors.receive(0));

            assertEquals(1, partner.attemptsFor("ORD-INVALID"));
            assertTrue(hasCause(error.getPayload(),
                    RetryDemoConfig.InvalidOrderException.class));
            assertNull(replies.receive(0));
            assertNull(errors.receive(0));
        }
    }

    private static void send(
            AnnotationConfigApplicationContext context,
            RetryDemoConfig.OrderRequest request) {

        MessageChannel input =
                context.getBean("orderRequests", MessageChannel.class);

        assertTrue(input.send(MessageBuilder.withPayload(request)
                .setHeader("businessRequestId", request.orderId())
                .build()));
    }

    private static boolean hasCause(
            Throwable failure,
            Class<? extends Throwable> expectedType) {

        Throwable current = failure;
        while (current != null) {
            if (expectedType.isInstance(current)) {
                return true;
            }
            Throwable next = current.getCause();
            if (next == current) {
                break;
            }
            current = next;
        }
        return false;
    }
}
~~~

In this example, `DirectChannel` completes processing before `send` returns, so the test can read the queue immediately with `receive(0)`. If you switch to `ExecutorChannel` or an asynchronous consumer, the test must wait with a bounded timeout for the corresponding result.

The error path may contain multiple wrapper layers. The test traverses the cause chain instead of forcing the error payload itself to directly match the business exception. `RetryTemplate` 7.0 represents the final failure as the cause of `RetryException` and retains earlier failures in suppressed exceptions. [Source: RetryTemplate 7.0](https://raw.githubusercontent.com/spring-projects/spring-framework/v7.0.0/spring-core/src/main/java/org/springframework/core/retry/RetryTemplate.java).

The illustrated tests prioritize checking invocation counts and routing. If you need to verify exact backoff timings, use a wait-strategy substitution point supported by the API in use rather than millisecond-tight timing assertions.

### 10.3. Additional Tests for Real Applications

- Remove the recovery callback and verify the synchronous sender receives the exception when retries stop.
- Make a downstream step fail and verify the reservation call is not repeated by the advice on the reservation endpoint.
- Simulate an operation succeeding while its response is lost to verify idempotency.
- Make the recovery channel unable to accept messages and verify error reporting behavior.
- For stateful retry, redeliver the same business key while constructing a new `Message`.
- With a broker, test acknowledgment, rollback, redelivery, and final error destination together.

These are behavioral tests of the flow. Testing a standalone `RetryTemplate` alone will not verify that the advice is wired to the right endpoint.

## 11. Reading Spring Integration 6.x Configuration

If your application uses Spring Integration 6.x, the advice takes an `org.springframework.retry.support.RetryTemplate` via `setRetryTemplate(...)` and uses the Spring Retry API. Stateful retry in that branch uses `RetryStateGenerator`, unlike `stateKeyFunction` in 7.x. [Source: RequestHandlerRetryAdvice 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

In the same demo configuration, you can replace `orderRetryAdvice(...)` with the snippet below when the project targets the 6.x dependency stack and includes Spring Retry 2.x. Do not mix retry imports from the two branches.

~~~java
@Bean
public RequestHandlerRetryAdvice orderRetryAdvice(
        @Qualifier("exhaustedOrders") MessageChannel recoveryChannel) {

    var template = new org.springframework.retry.support.RetryTemplate();

    var retryableExceptions =
            java.util.Map.<Class<? extends Throwable>, Boolean>of(
                    TransientPartnerException.class, true);

    template.setRetryPolicy(
            new org.springframework.retry.policy.SimpleRetryPolicy(
                    3,
                    retryableExceptions,
                    true));

    var backOff =
            new org.springframework.retry.backoff.ExponentialBackOffPolicy();
    backOff.setInitialInterval(100L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(1_000L);
    template.setBackOffPolicy(backOff);

    var advice = new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(template);
    advice.setRecoveryCallback(
            new ErrorMessageSendingRecoverer(recoveryChannel));
    return advice;
}
~~~

In `SimpleRetryPolicy`, `maxAttempts = 3` **includes the initial attempt**. The `true` constructor argument enables traversing the cause chain to find matching exceptions. [Source: SimpleRetryPolicy](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/policy/SimpleRetryPolicy.html).

| Intent | Spring Integration 6.x / Spring Retry 2.x | Spring Integration 7.x / Spring Framework 7.x |
| --- | --- | --- |
| Up to three invocations | `SimpleRetryPolicy(3, ...)` | `RetryPolicy.builder().maxRetries(2)` |
| Attach retry configuration | `setRetryTemplate(template)` | `setRetryPolicy(policy)` |
| Backoff | `BackOffPolicy` from Spring Retry | `RetryPolicy` builder configuration |
| Stateful | `setRetryStateGenerator(...)` | `setStateKeyFunction(...)` |
| Recovery callback | `org.springframework.retry.RecoveryCallback` | `org.springframework.integration.core.RecoveryCallback` |

The table uses the introduced APIs to compare the two examples. When upgrading, review imports, callbacks, and attempt counts together; renaming classes alone is not enough.

## 12. Operational Observability

When putting the flow into production, record at least:

| Information | Purpose |
| --- | --- |
| Endpoint name | Know which step is retrying |
| Business request ID in logs/traces | Correlate invocations belonging to the same operation |
| Normalized error type or error code | Distinguish transient failures from invalid data |
| Number of handler executions | Assess extra load caused by retries |
| Number of cycles succeeding after retry | Measure how many requests retries actually saved |
| Number of cycles ending in error | Track output requiring recovery |
| Total cycle duration | Evaluate against caller deadlines |
| Error path depth and message age | Detect failed work that has not yet been handled |

These are recommendations for what to observe, not a list of metrics automatically emitted by the advice.

A few design notes:

- Separate handler execution counts from incoming business request counts.
- Use low-cardinality metric labels such as endpoint and error category; keep `orderId` in logs/traces to avoid excessive cardinality.
- Avoid logging full stack traces on every attempt if transient errors occur at high frequency.
- Track recovery errors separately so they are not confused with partner-side errors.
- Avoid putting sensitive payload data into logs by default.

You can use `RetryListener` for retry events, combined with endpoint-level observation to cover first-attempt successes as well. When computing metrics, define which events correspond to a single execution and which correspond to a complete cycle.

## 13. Common Issues and Diagnostics

| Symptom | What to Check |
| --- | --- |
| Runs only once even though a retry bean was created | Is the bean attached to the endpoint via `advice(...)` or `adviceChain`? |
| Root exception matches the type but does not retry | Is there a wrapper; does the policy inspect causes; did the error occur inside the handler scope? |
| No exception and no reply | Did the handler or recovery return `null`; are you waiting on the wrong channel; is a reply required? |
| Multiple reservations for the same request | Is the call idempotent; how many layers are retrying? |
| Input queue grows rapidly when the partner fails | Are workers being tied up by timeouts and backoff? |
| Sender sees no error after processing fails | Did recovery complete normally; is there an asynchronous boundary? |
| Stateful does not resume the previous cycle | Did the business key remain identical; did the message hit the same instance; was the cache evicted? |
| Later attempt succeeds but commit still fails | Was the transaction marked rollback-only on the first attempt? |
| `setRetryTemplate` code does not compile in 7.x | Are you mixing 6.x examples with 7.x dependencies? |
| Expected three retries but only three calls occurred in total | Are you using Spring Retry's `maxAttempts`, which includes the initial call? |

Diagnose in order: identify the endpoint, observe the actual exception, count handler executions, check the output channel, and then inspect transactions and redelivery mechanisms.

## 14. Hands-on Exercises

### Exercise 1: Change Retry Count and Predict First

Change the main policy to `maxRetries(3)`, initial delay 50 ms, multiplier 2, and no jitter.

Before running, predict:

- A request that fails twice then succeeds needs three invocations.
- A request that always fails needs at most four invocations.
- Wait intervals before the three retries are 50 ms, 100 ms, and 200 ms respectively.

Verify using the counter and message counts on both output paths.

### Exercise 2: Prove Endpoint Scope

Add an audit step after the reservation handler. Make the audit throw an exception when reservation succeeds.

Expected observation: the synchronous sender receives the downstream error, while the advice on the reservation handler does not re-invoke the reservation operation because of the audit failure.

### Exercise 3: Design a Durable Error Path

Replace the in-memory error queue with an error persistence approach suited to your application.

The design must specify what data to store, when the source message is acknowledged, how failures while saving the error are handled, and how operators can resubmit the request while keeping the same idempotency key.

### Exercise 4: Explore Stateful Retry

In a brokered environment, reuse the same `businessRequestId` across redeliveries and record the handler execution count.

Next, change the key on each received message. Explain why the advice can no longer correlate redeliveries into the same cycle. Also evaluate what happens if the consumer restarts mid-cycle.

## 15. Key Takeaways

`RequestHandlerRetryAdvice` centralizes retry around the message-processing step that needs protection. A sound configuration must clearly specify the handler scope, retryable exceptions, maximum invocations, wait intervals, and outcome when the cycle stops.

In Spring Integration 7.x, use Spring Framework's `RetryPolicy` and calculate total invocations as `1 + maxRetries`. In 6.x examples using Spring Retry, `maxAttempts` already includes the initial attempt.

Recovery captures failures; the safety of repeating an operation still depends on idempotency, transactions, and the contract with the target system. Always verify behavior with actual execution counts and outputs on both the success and error paths.
