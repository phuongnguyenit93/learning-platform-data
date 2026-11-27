# RetryTemplate

## 1. Objectives and Version Scope

In the **Advice and Retries** chapter of the **SPRING_INTEGRATION_CORE** module, `RetryTemplate` helps re-execute an operation when it encounters errors that are likely to resolve on their own. For example: an endpoint calling a shipping carrier receives a temporary service error; the application waits briefly and tries again before routing the request to a failure-handling flow.

After this lesson, you will be able to define the unit of work to retry, configure attempt counts and wait intervals, classify exceptions, attach retry to a Java DSL endpoint, and verify results both when retry succeeds and when attempts are exhausted.

There are two classes named `RetryTemplate` across two API generations. This lesson uses **Java 17+, Spring Integration 6.5.x, and Spring Retry 2.0.x** for the main examples in Sections 2–12; Section 13 presents the corresponding API in Spring Integration 7.x. Choosing the 6.5 branch allows a complete explanation of Spring Retry's `RetryContext`, `BackOffPolicy`, and `RecoveryCallback` model—it is not a requirement to downgrade a project already on 7.x.

| Topic | Main Examples: Integration 6.5 + Spring Retry 2.0 | Integration 7.x + Spring Framework 7.x |
| --- | --- | --- |
| Template class | `org.springframework.retry.support.RetryTemplate` | `org.springframework.core.retry.RetryTemplate` |
| Attempt count configuration | `maxAttempts(n)`: includes the initial attempt | `maxRetries(n)`: additional attempts after the initial call |
| Attaching to retry advice | `setRetryTemplate(template)` | `setRetryPolicy(policy)` |
| Recovery in Integration | `org.springframework.retry.RecoveryCallback` | `org.springframework.integration.core.RecoveryCallback` |

Spring Integration 7.0 moved from Spring Retry to the retry API in Spring Framework Core and changed the `RequestHandlerRetryAdvice` API. Therefore, simply changing `import` statements is not enough to upgrade the examples. Source: [Changes from Spring Integration 6.5 to 7.0](https://docs.spring.io/spring-integration/reference/changes-6.5-7.0.html).

## 2. Where Does Retry Live in a Message Flow?

Consider a shipment creation flow:

```text
Message<ShippingRequest>
    -> shippingRequests: DirectChannel
    -> service activator calling the shipping carrier, with retry advice
    -> shippingResults: QueueChannel

If the protected operation fails:
    -> recovery callback
    -> shippingFailures: QueueChannel containing ErrorMessage
```

`Message` carries the request and headers; `MessageChannel` transports the message; the endpoint performs the business operation; the advice wraps that endpoint's execution. `RetryTemplate` manages the retry cycle, while `RequestHandlerRetryAdvice` connects the retry mechanism to message handling.

The boundary should enclose **an operation that can be safely re-invoked**. In the example above, that is the shipment creation call using a deduplication key; you should not wrap an entire sequence of deducting inventory, capturing payment, and sending email if all three steps would repeat when only the last step fails.

Attaching an advice to a service activator does not turn the whole flow into a single retry unit. In particular, an error sending the reply to the downstream channel should not automatically be treated as a failure of the protected call. To retry a multi-endpoint segment, design an explicit invocation boundary—such as through a gateway—and re-evaluate every side effect inside that segment. The core mechanism is described in [Spring Integration 6.5 Retry Advice](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/classes.html).

## 3. Components Working Together with RetryTemplate

| Component | Question It Answers |
| --- | --- |
| `RetryCallback<T, E>` | Which operation will be retried? |
| `RetryPolicy` | Given the current failure count and error type, can it still be retried? |
| `BackOffPolicy` | If it can be retried, how long should it wait? |
| `RetryContext` | How many times has the current cycle failed, and what was the last error? |
| `RecoveryCallback<T>` | When retries stop, what is the fallback result or final handling action? |
| `RetryListener` | How do we observe cycle start, per-attempt errors, and cycle completion? |

Stateless execution steps can be pictured as follows:

```text
Open context
    -> invoke callback
        -> success: return result, finish
        -> exception: record failure
            -> still retryable: backoff then re-invoke callback
            -> no longer retryable:
                -> suitable recovery present: invoke recovery
                -> no recovery: throw error outward
```

If the callback catches an exception and returns a normal value, the template sees a successful execution. Returning `null`, an error code, or an object with `status = FAILED` does not automatically trigger a retry. To retry based on a response from an external system, the client layer must classify responses and convert retryable cases into exceptions.

A single `RetryTemplate` instance can be used concurrently across multiple operations; attempt-count state resides in each cycle's context. That does not make your custom callbacks, clients, or application counters thread-safe. See [Spring Retry RetryTemplate Javadoc](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/support/RetryTemplate.html).

## 4. Counting Attempts Correctly

In Spring Retry, `maxAttempts(3)` means **at most three total executions: one initial attempt and two retries**. `maxAttempts(1)` still executes the operation once with no retries. This convention also applies to `SimpleRetryPolicy`; see [SimpleRetryPolicy Javadoc](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/policy/SimpleRetryPolicy.html).

The standalone example below simulates two failures followed by success on the third attempt:

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.retry.support.RetryTemplate;

public class RetryCountingExample {

    static class TemporaryCarrierException extends RuntimeException {
        TemporaryCarrierException(String message) {
            super(message);
        }
    }

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();

        RetryTemplate template = RetryTemplate.builder()
                .maxAttempts(3)
                .noBackoff()
                .retryOn(TemporaryCarrierException.class)
                .build();

        String trackingCode = template.execute(context -> {
            int attempt = context.getRetryCount() + 1;
            int call = calls.incrementAndGet();
            System.out.println("attempt=" + attempt);

            if (call < 3) {
                throw new TemporaryCarrierException("Carrier unavailable");
            }
            return "TRACK-A001";
        });

        System.out.println(trackingCode + ", calls=" + calls.get());
    }
}
```

Expected output:

```text
attempt=1
attempt=2
attempt=3
TRACK-A001, calls=3
```

At the start of the first callback invocation, `getRetryCount()` equals `0`. After one failure, the value equals `1`; if the callback runs again, that is the second execution. If all three attempts fail, recovery sees a count of `3`. Therefore, when logging, know whether the log occurs before an invocation or after an error so you do not blindly add `1` everywhere. The context also provides `getLastThrowable()` to inspect the most recent error; see [RetryContext Javadoc](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/RetryContext.html).

## 5. Choosing Which Errors to Retry

### 5.1. Classifying by Recoverability

Retry is useful when the same request can succeed after a wait without modifying input data. The table below is a design guide for the shipping carrier example; final classification depends on the partner's API contract.

| Scenario | Expected Action |
| --- | --- |
| Partner reports service temporarily unavailable | Can retry with a bound and backoff |
| Connection dropped before outcome is known | Consider retrying with a deduplication key, or look up the prior result first |
| Partner rate limits requests | Respect wait intervals in the API contract and control total request volume |
| Address is missing a required field | Do not retry; data must be corrected |
| Invalid credentials or access denied | Do not immediately repeat the same request; fix configuration/permissions |
| Programming errors such as `NullPointerException` | Do not mask with a broad retry loop |

Example configuration that retries only transient errors:

```java
RetryTemplate template = RetryTemplate.builder()
        .maxAttempts(3)
        .fixedBackoff(200)
        .retryOn(TemporaryCarrierException.class)
        .traversingCauses()
        .build();
```

In the short snippets, `TemporaryCarrierException` is the business exception declared in the corresponding example. Numeric durations in the Spring Retry builder here are in **milliseconds**.

### 5.2. Watch Out for Exceptions Wrapped in Messaging

A client error may sit inside a cause chain:

```text
MessageHandlingException
    -> TemporaryCarrierException
```

If only the outermost exception is checked, the classifier might fail to recognize the transient error. `.traversingCauses()` enables inspecting the `cause` chain during classification. This setting is especially helpful when your callback explicitly calls a messaging component that wraps exceptions; do not assume every endpoint wraps errors in the same way.

Simply adding `retryOn(Exception.class)` to make retry "work" widens the scope to include data errors and programming bugs. Instead, identify which exceptions actually cross the protected boundary and select the appropriate exception classes. The builder API and classification options are documented in [RetryTemplateBuilder](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/support/RetryTemplateBuilder.html).

## 6. Backoff and Time Budgets

### 6.1. Choosing Wait Intervals

| Spring Retry Configuration | Behavior |
| --- | --- |
| `.noBackoff()` | Does not actively wait between attempts; suitable for attempt-count tests |
| `.fixedBackoff(200)` | Waits 200 ms between consecutive executions |
| `.exponentialBackoff(100, 2.0, 1000)` | Starts at 100 ms, multiplies by 2, caps wait at 1,000 ms |
| `.exponentialBackoff(100, 2.0, 1000, true)` | Uses a randomized exponential variant; does not follow a rigid fixed schedule |

For non-randomized exponential backoff, the `k`-th wait interval—counting from `k = 1` before the second execution—is modeled as:

```text
d(k) = min(initialInterval × multiplier^(k - 1), maxInterval)
```

This models the schedule; non-integer values may differ due to rounding. With `maxAttempts(4)`, `initialInterval = 100`, `multiplier = 2`, and `maxInterval = 1000`, the three waits are `100, 200, 400` ms. Total wait time is `700` ms. There is no wait before the first attempt or after the final failure. Policy properties are described in [ExponentialBackOffPolicy](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/backoff/ExponentialBackOffPolicy.html).

Randomizing wait intervals prevents multiple instances from retrying at the exact same moment. It does not replace attempt limits, load shedding, or a circuit breaker when the target service is down for a prolonged period.

### 6.2. Accounting for Client and Gateway Timeouts

Suppose each call has an effective timeout of at most `800` ms, with three executions and two waits of `100, 200` ms. The budget estimate for calls and waits is:

```text
T ≈ 3 × 800 + 100 + 200 = 2,700 ms
```

This calculation relies on the assumptions above; it excludes queuing, connection pool waits, channel processing, and recovery. Set appropriate timeouts on the client and actual resources involved in the call, then leave headroom for the overall request.

`maxAttempts` limits the number of attempts rather than interrupting a hung network call. Likewise, a retry timeout policy cannot inherently cancel in-flight I/O. A gateway's reply timeout is also not a mechanism guaranteed to abort background work.

Stateless retry with synchronous backoff holds the endpoint thread for the entire cycle. With a `DirectChannel`, that is also the sender's thread. If each message waits tens of seconds in a small pool, the pool can be exhausted before reaching desired throughput. When long waits are a business requirement, consider a retry queue or a durable redelivery mechanism with appropriate scheduling.

## 7. Complete Example: Attaching RetryTemplate in Java DSL

### 7.1. Preparing Dependencies

For the 6.5 example branch, `spring-integration-core` and `spring-retry` are required. The Maven snippet below assumes the project's dependency management/BOM already manages compatible versions for both; otherwise, declare explicit versions.

```xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-core</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.retry</groupId>
    <artifactId>spring-retry</artifactId>
</dependency>
```

The example configures the `RetryTemplate` bean and endpoint advice directly, so `@EnableRetry` is not needed. That annotation serves the proxy model using `@Retryable`, which is a different integration style.

### 7.2. Flow Configuration and Simulated Client

Place the following code in `ShippingRetryConfiguration.java`. The simulated client has three behaviors: order IDs starting with `DOWN-` always encounter transient failures; requests missing an address fail immediately with a data error; remaining requests fail twice and then succeed. This is a local simulation and does not call a real API.

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
public class ShippingRetryConfiguration {

    public record ShippingRequest(String orderId, String address) {}

    public record ShippingResult(String orderId, String trackingCode) {}

    public static class TemporaryCarrierException extends RuntimeException {
        public TemporaryCarrierException(String message) {
            super(message);
        }
    }

    public static class DemoCarrierClient {
        private final ConcurrentMap<String, AtomicInteger> calls =
                new ConcurrentHashMap<>();

        public ShippingResult createShipment(ShippingRequest request) {
            int attempt = calls.computeIfAbsent(
                    request.orderId(), key -> new AtomicInteger())
                    .incrementAndGet();

            if (request.address() == null || request.address().isBlank()) {
                throw new IllegalArgumentException("Shipping address is required");
            }
            if (request.orderId().startsWith("DOWN-") || attempt < 3) {
                throw new TemporaryCarrierException("Carrier temporarily unavailable");
            }
            return new ShippingResult(
                    request.orderId(), "TRACK-" + request.orderId());
        }

        public int attempts(String orderId) {
            AtomicInteger count = calls.get(orderId);
            return count == null ? 0 : count.get();
        }
    }

    @Bean
    public DemoCarrierClient carrierClient() {
        return new DemoCarrierClient();
    }

    @Bean
    public DirectChannel shippingRequests() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel shippingResults() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel shippingFailures() {
        return new QueueChannel(100);
    }

    @Bean
    public RetryTemplate shippingRetryTemplate() {
        return RetryTemplate.builder()
                .maxAttempts(3)
                .exponentialBackoff(100, 2.0, 1000)
                .retryOn(TemporaryCarrierException.class)
                .traversingCauses()
                .build();
    }

    @Bean
    public RequestHandlerRetryAdvice shippingRetryAdvice(
            RetryTemplate shippingRetryTemplate,
            @Qualifier("shippingFailures") QueueChannel failures) {

        ErrorMessageSendingRecoverer recoverer =
                new ErrorMessageSendingRecoverer(failures);
        recoverer.setSendTimeout(1000);

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(shippingRetryTemplate);
        advice.setRecoveryCallback(recoverer);
        return advice;
    }

    @Bean
    public IntegrationFlow shippingFlow(
            DemoCarrierClient carrierClient,
            RequestHandlerRetryAdvice shippingRetryAdvice) {

        return IntegrationFlow.from("shippingRequests")
                .handle(ShippingRequest.class,
                        (request, headers) -> carrierClient.createShipment(request),
                        endpoint -> endpoint.advice(shippingRetryAdvice))
                .channel("shippingResults")
                .get();
    }
}
```

The attachment point is `endpoint.advice(shippingRetryAdvice)`: a template bean affects an endpoint only when passed into an advice and attached to that endpoint. The `.handle(...)` method creates the client-calling step receiving a `ShippingRequest` payload; see [Java DSL Service Activator](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-handle.html) and [RequestHandlerRetryAdvice 6.5 API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

The simulated client counts by `orderId` for demonstration. In a real application, validate `orderId` and required fields before the client-call boundary. The map in this example is neither a production deduplication store nor a retry state store.

### 7.3. Expected Results

For each new request in a fresh application context:

| Payload | Client Calls | Outcome |
| --- | --- | --- |
| `new ShippingRequest("A-1", "12 Nguyen Trai")` | 3 | One `ShippingResult` in `shippingResults` |
| `new ShippingRequest("DOWN-1", "12 Nguyen Trai")` | 3 | One `ErrorMessage` in `shippingFailures` |
| `new ShippingRequest("BAD-1", " ")` | 1 | One `ErrorMessage` in `shippingFailures`, no retries |

The data error in the last row is not retried, yet it still enters recovery in this configuration. **Not retrying** and **not recovering** are two separate decisions. If business requirements demand throwing a particular error outward instead of sending it to the failure channel, express that in the appropriate policy or recovery logic.

The two queues in the example are in-memory, bounded in capacity, and read directly in tests. In a continuously running flow, they need consumers; whether to persist them durably is a separate decision. Naming a channel `shippingFailures` does not automatically create a dead-letter queue on a message broker. When the queue is full and sending during recovery exceeds the configured timeout, recovery itself can fail.

## 8. Recovery and Error Channels

### 8.1. Recovery Returning a Fallback Result

When calling the template directly, recovery can produce a meaningful business outcome. The following snippet is placed inside a method that already has `request`, `carrierClient`, and `template`, using the types from Section 7:

```java
record ShippingDecision(String orderId, String status, String trackingCode) {}

ShippingDecision decision = template.execute(
        context -> {
            var result = carrierClient.createShipment(request);
            return new ShippingDecision(
                    result.orderId(), "CREATED", result.trackingCode());
        },
        context -> new ShippingDecision(
                request.orderId(), "PENDING_REVIEW", null));
```

`PENDING_REVIEW` indicates that no shipment creation result exists yet, not a successfully created shipment. Downstream recipients must handle that status. If recovery persists data or emits another message, that action also needs appropriate failure detection and deduplication.

### 8.2. Recovery Sending an ErrorMessage

In Section 7, `ErrorMessageSendingRecoverer` sends the final error as an `ErrorMessage` to the designated channel. The payload of an error message is a `Throwable`, not `ShippingRequest` directly. To recover the original request, inspect the original message / `failedMessage` provided by the exception or error-message strategy; do not cast the error payload to the business payload. See [ErrorMessageSendingRecoverer](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/handler/advice/ErrorMessageSendingRecoverer.html).

When the recoverer sends successfully and returns `null`, the endpoint emits no business reply to the `shippingResults` branch. If you replace the flow with a request–reply gateway, design a failure result or corresponding reply path; otherwise, the caller may wait until timeout.

Completing recovery also changes what the caller observes: the cycle is considered handled via the recovery branch, even though shipment creation failed. Do not infer from `channel.send(...) == true` that a shipment was created. With adapters involving transactions or acknowledgments, suppressing the exception can affect commit or ack behavior; check the specific adapter and transaction configuration.

### 8.3. When Recovery Is Not Configured

To let the final error escape the advice in the 6.5 example, omit `setRecoveryCallback(...)`. In a synchronous flow over a `DirectChannel`, the error can propagate back to the sender, typically wrapped in a messaging exception containing the root cause.

Simply setting an `errorChannel` header does not automatically turn every synchronous exception into an error message. In asynchronous processing, the framework/adapter error handler is what publishes errors; gateways also have their own error-handling rules. Therefore, always verify **who catches the final exception** and **who sends the ErrorMessage** in each flow. See [Spring Integration 6.5 Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

## 9. Stateless, Stateful, and Redelivery

| Aspect | Stateless Retry | Stateful Retry |
| --- | --- | --- |
| How retries continue | Retries within a single template call | Saves state by key and resumes across redelivery calls |
| Can the caller see intermediate errors? | Usually only after the cycle stops or recovery is absent | Yes; errors can be thrown so upstream rolls back and redelivers |
| Identifying the same request | Single context for one call | Requires a stable key across redeliveries |
| Who guarantees redelivery? | Upstream is not needed for attempts within the cycle | Broker, container, or caller invokes again |

The Section 7 example is stateless: three executions can happen within a single `shippingRequests.send(...)`. No new message is re-sent to the input channel between those three attempts.

In Integration 6.5, stateful retry uses `RetryStateGenerator` on the retry advice. In Integration 7.x, this mechanism moves to `stateKeyFunction`. The key should usually represent the same business operation—such as `tenantId + orderId + operation`—rather than a message ID that may change each time a broker redelivers.

Stateful retry does not create redelivery on its own and does not automatically make wait intervals asynchronous. Check who redelivers, when redelivery occurs, where state is stored, and what happens if the application restarts. A local cache does not preserve retry budgets across process loss.

Another risk is retrying across multiple layers. Suppose the HTTP client tries up to 3 times per handler invocation, the advice invokes the handler up to 3 times, and the broker redelivers the message up to 5 times; if all three layers exhaust their attempts without recovery terminating early, requests reaching the partner can reach:

```text
3 × 3 × 5 = 45 requests for one business request
```

This calculation reflects the hypothetical configuration above, not framework defaults. Define a total budget and allocate it across layers, including wait times and stopping conditions.

## 10. Idempotency, Transactions, and Asynchronous Work

### 10.1. Retrying Does Not Prove the Previous Attempt Failed

A common shipment creation scenario:

1. The shipping carrier creates the shipment successfully.
2. The response is lost on the return path.
3. The client times out and throws an exception.
4. Retry sends the creation request again with the same data.

Without partner-side deduplication, the system may create two shipments. Each creation operation should have a stable `idempotencyKey` across all retry attempts and redeliveries. The partner must enforce the deduplication contract with that key; merely adding a header inside an internal message creates no guarantee.

If the partner does not support idempotency, consider looking up by business reference ID or routing uncertain outcomes to reconciliation. Never return a fabricated tracking code to make the flow look successful.

### 10.2. Which Transaction Wraps Each Attempt?

An outer transaction spanning the entire cycle differs from a fresh transaction per attempt. For instance, after a database error, the current transaction may already be marked rollback-only; retrying inside that same transaction does not guarantee recovery.

When a separate transaction is needed per attempt, the retry boundary must sit outside the boundary that creates a transaction per call. With multiple advices, application order matters; do not infer order merely from two beans coexisting. Test with an actual rollback scenario and verify commit/rollback on each attempt.

Rolling back a local transaction also does not revoke a shipment already created in a remote system. Idempotency and reconciliation mechanisms remain necessary.

### 10.3. Exceptions Must Occur Within the Protected Boundary

If a handler merely starts a `CompletableFuture` or returns a publisher and exits, errors occurring later may fall outside the invocation protected by the advice. Synchronous `RetryTemplate` does not automatically subscribe to track asynchronous or reactive work spawned by the handler.

Place retry where the actual result or error is observed, or use a retry mechanism designed for that execution style. At the same time, keep the retry boundary tight enough to avoid repeating steps that already caused side effects.

## 11. Observing the Retry Cycle

With Spring Retry 2.x, you can register a `RetryListener` to observe retries without embedding logging logic in every client:

```java
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.RetryListener;

template.registerListener(new RetryListener() {
    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {

        System.out.printf(
                "operation=create-shipment failedAttempts=%d exception=%s%n",
                context.getRetryCount(),
                throwable.getClass().getSimpleName());
    }
});
```

Here `template` is the created instance. Register the listener during bean configuration before the flow receives traffic. `onError` is called after every failure, including the last one; a single `onError` event is not enough to conclude the entire request failed. The `open`, `onSuccess`, and `close` hooks serve different lifecycle points; see [RetryListener](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/RetryListener.html).

Useful measurements for the shipment creation flow include actual calls made to the partner, requests succeeding after retry, requests entering recovery, and total processing duration per request. Distinguish "shipment created" from "accepted for reconciliation."

Use endpoint name, operation name, and exception category as bounded-cardinality metric tags. `orderId`, street addresses, and full payloads are unsuitable as metric tags; reconciliation IDs belong in controlled logs. Listeners must also execute quickly and never throw a new error that masks the observed failure.

## 12. Testing Behavior Without Depending on Real Wait Times

### 12.1. Testing Success, Exhaustion, and Non-Retryable Errors

Place the following class in the same package as `ShippingRetryConfiguration` and add JUnit Jupiter to your test dependencies. Each test creates its own context so simulated data does not leak across tests. A helper swaps backoff for `NoBackOffPolicy` before sending messages, preserving attempt limits and exception classification.

```java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.GenericMessage;
import org.springframework.retry.backoff.NoBackOffPolicy;
import org.springframework.retry.support.RetryTemplate;

import static org.junit.jupiter.api.Assertions.*;

class ShippingRetryFlowTest {

    private AnnotationConfigApplicationContext newContext() {
        var context = new AnnotationConfigApplicationContext(
                ShippingRetryConfiguration.class);
        context.getBean("shippingRetryTemplate", RetryTemplate.class)
                .setBackOffPolicy(new NoBackOffPolicy());
        return context;
    }

    private void send(AnnotationConfigApplicationContext context,
                      String orderId, String address) {
        var request = new ShippingRetryConfiguration.ShippingRequest(
                orderId, address);
        context.getBean("shippingRequests", MessageChannel.class)
                .send(new GenericMessage<>(request));
    }

    @Test
    void succeedsOnThirdAttempt() {
        try (var context = newContext()) {
            send(context, "A-1", "12 Nguyen Trai");

            var client = context.getBean(
                    ShippingRetryConfiguration.DemoCarrierClient.class);
            var results = context.getBean("shippingResults", QueueChannel.class);
            var failures = context.getBean("shippingFailures", QueueChannel.class);

            assertEquals(3, client.attempts("A-1"));
            Message<?> reply = results.receive(0);
            assertNotNull(reply);
            assertEquals(
                    new ShippingRetryConfiguration.ShippingResult(
                            "A-1", "TRACK-A-1"),
                    reply.getPayload());
            assertNull(results.receive(0));
            assertNull(failures.receive(0));
        }
    }

    @Test
    void sendsOneErrorAfterRetryExhaustion() {
        try (var context = newContext()) {
            send(context, "DOWN-1", "12 Nguyen Trai");

            var client = context.getBean(
                    ShippingRetryConfiguration.DemoCarrierClient.class);
            var results = context.getBean("shippingResults", QueueChannel.class);
            var failures = context.getBean("shippingFailures", QueueChannel.class);

            assertEquals(3, client.attempts("DOWN-1"));
            assertNull(results.receive(0));
            assertInstanceOf(ErrorMessage.class, failures.receive(0));
            assertNull(failures.receive(0));
        }
    }

    @Test
    void doesNotRetryInvalidAddress() {
        try (var context = newContext()) {
            send(context, "BAD-1", " ");

            var client = context.getBean(
                    ShippingRetryConfiguration.DemoCarrierClient.class);
            var results = context.getBean("shippingResults", QueueChannel.class);
            var failures = context.getBean("shippingFailures", QueueChannel.class);

            assertEquals(1, client.attempts("BAD-1"));
            assertNull(results.receive(0));
            assertInstanceOf(ErrorMessage.class, failures.receive(0));
            assertNull(failures.receive(0));
        }
    }
}
```

`receive(0)` reads immediately because the input is a `DirectChannel`: once `send` returns normally, the synchronous handler and recovery in this configuration have finished running. If you switch to `ExecutorChannel` or a polled consumer, wait with an explicit timeout instead of keeping this assumption.

### 12.2. Testing Exception Cause Traversal Separately

The following test can be added in a separate JUnit class. It deliberately constructs a wrapped exception to verify classification configuration without relying on assumptions about how an endpoint wraps errors:

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.support.GenericMessage;
import org.springframework.retry.support.RetryTemplate;
import static org.junit.jupiter.api.Assertions.assertEquals;

class WrappedCauseRetryTest {
    @Test
    void retriesWhenTemporaryFailureIsWrapped() {
        AtomicInteger calls = new AtomicInteger();
        var message = new GenericMessage<>("create-shipment");
        var template = RetryTemplate.builder()
                .maxAttempts(3)
                .noBackoff()
                .retryOn(ShippingRetryConfiguration.TemporaryCarrierException.class)
                .traversingCauses()
                .build();

        String result = template.execute(context -> {
            if (calls.incrementAndGet() < 3) {
                throw new MessageHandlingException(message,
                        new ShippingRetryConfiguration.TemporaryCarrierException(
                                "Temporary failure"));
            }
            return "OK";
        });

        assertEquals("OK", result);
        assertEquals(3, calls.get());
    }
}
```

When you need to test the exponential backoff schedule itself, you can use `ExponentialBackOffPolicy#setSleeper(...)` to record wait intervals without actually sleeping, then compare the captured list against the expected schedule. Load testing, client timeouts, and transactions are separate tests; the attempt-counting tests above do not replace them.

## 13. Corresponding API in Spring Integration 7.x

This section uses **Spring Framework 7.x**, independent of the Spring Retry snippets above. The new template's callback does not accept a `RetryContext`; the attempt limit lives in `RetryPolicy` and configures the number of additional retry attempts.

Example allowing at most three total executions:

```java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.core.retry.RetryPolicy;
import org.springframework.core.retry.RetryTemplate;

public class FrameworkRetryExample {

    static class TemporaryCarrierException extends RuntimeException {}

    public static void main(String[] args) {
        RetryPolicy policy = RetryPolicy.builder()
                .maxRetries(2)
                .delay(Duration.ofMillis(100))
                .multiplier(2.0)
                .maxDelay(Duration.ofSeconds(1))
                .includes(TemporaryCarrierException.class)
                .build();

        RetryTemplate template = new RetryTemplate(policy);
        AtomicInteger calls = new AtomicInteger();

        String result = template.execute(() -> {
            if (calls.incrementAndGet() < 3) {
                throw new TemporaryCarrierException();
            }
            return "TRACK-A001";
        });

        System.out.println(result + ", calls=" + calls.get());
    }
}
```

In this API, `.maxRetries(2)` permits one initial attempt plus two additional retries. The builder also provides `delay`, `multiplier`, `maxDelay`, and exception filters; see [Spring Framework 7 RetryPolicy.Builder](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/core/retry/RetryPolicy.Builder.html).

If `execute(...)` fails, the new template throws `org.springframework.core.retry.RetryException`; the final attempt's error is in `cause`, and earlier errors may appear in `suppressed exceptions`. For recovery on direct calls, use `try/catch` instead of passing a Spring Retry `RecoveryCallback` to `execute`. This is the behavior of [RetryTemplate in Spring Framework](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/retry/RetryTemplate.html).

To apply the same policy to a Spring Integration 7.x endpoint:

```java
// policy is the org.springframework.core.retry.RetryPolicy created above.
var advice = new org.springframework.integration.handler.advice.RequestHandlerRetryAdvice();
advice.setRetryPolicy(policy);

// Register advice as a bean and attach it to the IntegrationFlow endpoint:
// .handle(..., endpoint -> endpoint.advice(advice))
```

Do not pass `org.springframework.retry.support.RetryTemplate` or call `setRetryTemplate(...)` on the advice in this branch. When migrating an application, check imports, attempt counting, final exception types, recovery, and stateful retry. The exact API is listed in [Integration 7.x RequestHandlerRetryAdvice](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

## 14. Practice Exercises

1. In the 6.5 configuration, reduce `maxAttempts` from `3` to `2`. With the simulated client not succeeding before the third attempt, predict which channel receives the result and the call count before running.
2. Remove recovery from the advice while keeping `DirectChannel`. Send `DOWN-1` and inspect the exception received by the sender along with its cause chain.
3. Add a stable deduplication key to the request. Simulate the partner having created the shipment while the client times out, then design how the next attempt retrieves the same shipment.
4. Add a notification step after the shipment creation endpoint. Make the notification step fail and verify whether the shipment creation call is actually inside the retry boundary for that error.
5. Migrate the configuration to Integration 7.x while keeping the requirement of at most three total executions. Rewrite the policy and tests to catch accidentally increasing the attempt count when switching from `maxAttempts` to `maxRetries`.

For each option, be able to explain: which operation is re-invoked, why the error is recoverable, what the maximum total request count is, and where the request goes once retries stop. Those decisions turn retry into a controllable part of the message flow.
