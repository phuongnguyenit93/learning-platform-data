# Error Handling with onErrorResume, retryWhen, and Recovery Scope

In reactive applications, an error is a terminal signal of a `Mono` or `Flux`. When a publisher emits `onError`, the current processing chain terminates unless a recovery operator replaces the error signal or resubscribes to the source. With Spring Cloud Stream, this is especially important when a function receives a stream of messages, calls external services, and emits results back to the broker.

Reactor provides two commonly used operators for this situation. `onErrorResume` translates an error into a fallback publisher; `retryWhen` resubscribes to the publisher when an error satisfies a retry policy. They can be combined, but operator placement determines recovery scope: just one message, one step in the pipeline, or the entire stream. Placing them in the wrong position can drop messages, halt the whole stream, or repeat already-executed side effects.

This lesson belongs to the **Reactive Processing** chapter of the `SPRING_CLOUD_STREAM` module. The module uses the `Supplier`/`Function`/`Consumer` function model, bindings, and binders for Kafka, RabbitMQ, or Pulsar. We will use Reactor `Mono`/`Flux` to illustrate error handling in reactive functions, while distinguishing application-level retries from retries, redelivery, and message acknowledgement at the binder/broker layer.

## 1. Errors in Reactor Are Publisher Signals

A `Mono<T>` can emit one value and complete, complete without a value, or emit an error. A `Flux<T>` can emit many values and complete, or emit an error. Once a publisher emits `onError`, that publisher does not continue emitting elements after the error.

```text
Flux<OrderEvent>
     |
     +--> onNext(event 1)
     +--> onNext(event 2)
     +--> onError(exception)
     |
     +--> terminates the current chain
```

This differs from an imperative loop that can catch an exception per iteration and continue. With a reactive stream, if an operation inside `flatMap` emits an error and that error escapes outward, the error can terminate the outer publisher. To isolate per-message errors, place the recovery mechanism inside the publisher processing that message.

In a Spring Cloud Stream reactive function such as `Function<Flux<OrderEvent>, Flux<OrderResult>>`, the framework connects the input message stream to the output publisher. The function should clearly express which errors are recovered, which are retried, and which must propagate outward for the next error-handling layer to decide.

## 2. Distinguishing `onErrorResume` and `retryWhen`

| Operator | Behavior | Use when |
|---|---|---|
| `onErrorResume` | When the publisher errors, invokes a fallback function and switches to a new publisher | An alternative result exists, you want to record the error, or route the message to a quarantine stream |
| `retryWhen` | When the error satisfies a retry policy, resubscribes to the source publisher | The error is transient and the operation can be safely re-executed |

`onErrorResume` does not re-run the failed operation itself. It replaces the error signal with another publisher. The fallback publisher can return a default result, emit a business outcome such as `REJECTED`, write the message to a DLQ and complete, or propagate an error.

`retryWhen` does not produce a fallback result. It resubscribes to the publisher according to a policy, which can include attempt counts, wait intervals, backoff, and error-type filtering. Once retries are exhausted, the final error is emitted unless another policy handles it.

Simple example:

```java
Mono<OrderResult> result = orderService.process(order)
    .onErrorResume(InsufficientStockException.class,
        error -> Mono.just(OrderResult.rejected(order.orderId())))
    .retryWhen(Retry.max(2));
```

This snippet is not a good combination for every case: once `onErrorResume` turns the error into a success outcome, `retryWhen` afterward no longer sees that error to retry it. Operator ordering must match recovery intent. The following sections show how to place retry before fallback.

## 3. Using `onErrorResume` to Substitute Errors

`onErrorResume` accepts an error and returns a replacement publisher. You can select a fallback publisher by exception type:

```java
Mono<OrderResult> result = orderService.process(order)
    .onErrorResume(InsufficientStockException.class,
        error -> Mono.just(
            OrderResult.rejected(order.orderId(), error.getMessage())
        ));
```

When insufficient stock is an expected business outcome, the application can return `REJECTED` instead of letting a technical error terminate the stream. This is business-layer recovery; it does not mean the order succeeded.

Several common fallback patterns:

```java
// Return an alternative result of the same type.
source.onErrorResume(error -> Mono.just(fallbackValue));

// Skip the current element/processing attempt by completing empty.
source.onErrorResume(error -> Mono.empty());

// Switch to another publisher, e.g., recording status.
source.onErrorResume(error -> auditService.record(error).thenReturn(fallbackValue));

// Do not recover a specific error type; continue propagating the error to outer layers.
source.onErrorResume(error -> Mono.error(error));
```

The replacement publisher must match the chain's output type. For `Mono<OrderResult>`, the fallback must typically return `Mono<OrderResult>`. Using `Mono.empty()` means emitting no result for that element; clarify whether omitting the result matches the business contract.

Do not return a default value like `OrderResult.success()` just to keep the stream error-free. If the real operation failed, a fake success result can cause downstream systems to update state incorrectly.

## 4. Using `retryWhen` for Transient Errors

Errors such as brief timeouts, temporary database connection interruptions, or dependent services returning 503 can recover after a short wait. You can use `Retry.backoff` to retry with increasing delays:

```java
import java.time.Duration;

import reactor.util.retry.Retry;

Mono<Reservation> reservation = inventoryClient.reserve(order)
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2))
            .filter(this::isTransientFailure)
    );
```

In this example:

- `3` is the maximum number of retries after the initial attempt. Thus there can be up to four executions total: one initial attempt plus three retries.
- Delay starts at 200 milliseconds and increases via backoff.
- `maxBackoff` caps the maximum wait interval at 2 seconds.
- `filter` allows retrying only exceptions considered transient.

Example of error classification:

```java
private boolean isTransientFailure(Throwable error) {
    return error instanceof java.util.concurrent.TimeoutException
        || error instanceof TransientOrderDependencyException;
}
```

Do not retry every exception. Invalid data, missing permissions, business-rule violations, or malformed schemas generally will not fix themselves by waiting. Retrying them only adds load and stretches processing time.

You can add jitter so multiple instances do not retry at the exact same instant:

```java
Retry.backoff(3, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(2))
    .jitter(0.5)
    .filter(this::isTransientFailure);
```

Jitter randomizes wait intervals around the backoff schedule, reducing thundering herds when many consumers hit a dependency simultaneously after recovery.

## 5. Why Wrap Retryable Operations in `Mono.defer`?

`retryWhen` resubscribes to the upstream publisher. So that each subscription genuinely triggers a fresh business call, use `Mono.defer`:

```java
Mono<Reservation> reservation = Mono.defer(
        () -> inventoryClient.reserve(order))
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .filter(this::isTransientFailure)
    );
```

`Mono.defer` delays calling `reserve` until subscription time. On every retry resubscription, the lambda runs again and creates a new publisher. This also brings synchronous exceptions thrown while building the publisher into the reactive chain so downstream operators can handle them.

If the publisher was already built as a cold publisher and work executes only upon subscribe, retry can resubscribe to that publisher. Even so, `defer` makes the execution boundary explicit and is usually safer when a service method call might throw immediately upon invocation.

Note: `Mono.defer` does not automatically make an operation idempotent. If the first attempt wrote data or charged money before timing out, a retry may duplicate side effects. You need idempotency keys, unique constraints, or appropriate transaction mechanisms.

## 6. Recovery Scope: One Message or the Whole Flux?

This is the most important decision when handling errors inside a reactive function.

### Per-Message Recovery

Place `retryWhen` and `onErrorResume` inside the per-element publisher. One failing message can be retried or quarantined without halting other messages:

```java
Flux<OrderResult> results = events.flatMap(event ->
    Mono.defer(() -> orderService.process(event))
        .retryWhen(retryPolicy)
        .onErrorResume(error -> handleFailure(event, error))
);
```

`flatMap` creates an inner publisher for each event. If the inner publisher handles the error and completes, other events can keep flowing. If an error escapes the inner publisher, it can propagate outward and terminate the outer `Flux`.

### Whole-Stream Recovery

Placing `onErrorResume` after `Flux`-level processing operators recovers errors across the entire chain:

```java
Flux<OrderResult> results = events
    .flatMap(orderService::process)
    .onErrorResume(error -> fallbackForWholeStream(error));
```

If one event causes `flatMap` to emit an error outward, the input `Flux` has already entered an error state. `onErrorResume` replaces the entire remainder of the stream with the fallback publisher. It does not automatically resume with the next event from the original source. Unprocessed events in that subscription may never pass through the function as expected.

### Scope Diagram

```text
Per-message recovery

Flux<Event> -> flatMap(
                 event -> process(event)
                            .retryWhen(...)
                            .onErrorResume(...)
              ) -> Flux<Result>

Whole-stream recovery

Flux<Event> -> flatMap(process)
                    |
                    +-- one error escapes outward
                    v
              onErrorResume(fallback)
                    |
                    v
              fallback for the rest of the stream
```

For independent message processing, usually recover inside each event's publisher. Whole-stream recovery fits when an error makes the entire stream unable to continue—such as a shared configuration source or global dependency becoming invalid—and the application deliberately switches to a fallback stream.

## 7. Example Reactive Function Processing Individual Orders

The example below illustrates three steps: retrying transient errors, converting known business errors into rejection outcomes, and routing remaining errors to a quarantine publisher. Services are assumed to return Reactor publishers.

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

record OrderEvent(String eventId, String orderId, long total) {}

record OrderResult(String orderId, String status, String reason) {
    static OrderResult rejected(String orderId, String reason) {
        return new OrderResult(orderId, "REJECTED", reason);
    }
}

@Configuration
class ReactiveOrderConfiguration {

    @Bean
    Function<Flux<OrderEvent>, Flux<OrderResult>> processOrders(
            OrderService orderService,
            DeadLetterPublisher deadLetterPublisher) {

        return events -> events.flatMap(event ->
            Mono.defer(() -> orderService.process(event))
                .retryWhen(
                    Retry.backoff(3, Duration.ofMillis(200))
                        .maxBackoff(Duration.ofSeconds(2))
                        .filter(error ->
                            error instanceof TimeoutException
                                || error instanceof TransientOrderDependencyException)
                        .onRetryExhaustedThrow((spec, signal) -> signal.failure())
                )
                .onErrorResume(InsufficientStockException.class, error ->
                    Mono.just(OrderResult.rejected(
                        event.orderId(), error.getMessage()))
                )
                .onErrorResume(error ->
                    deadLetterPublisher.publish(event, error)
                        .then(Mono.<OrderResult>empty())
                )
        );
    }
}
```

Key points to understand:

1. `events.flatMap(...)` processes each message via an inner publisher.
2. `Mono.defer` calls `orderService.process(event)` when the publisher is subscribed to.
3. `retryWhen` retries timeouts and transient dependency errors up to three times.
4. `InsufficientStockException` is converted into a `REJECTED` business outcome.
5. Remaining errors are sent to `DeadLetterPublisher`; only after the DLQ publisher completes does the inner publisher complete empty.
6. If DLQ publishing also fails, the error from `deadLetterPublisher` propagates outward because the fallback did not complete successfully.

This snippet is an illustrative template; `OrderService`, `DeadLetterPublisher`, and the exceptions are application components to implement. If you need to preserve processing and result emission order matching the input order, consider `concatMap` instead of `flatMap`, trading off parallel execution. `flatMapSequential` can run inner publishers concurrently while preserving result emission order; it does not guarantee inner side effects finish in order.

## 8. Operator Ordering Changes Behavior

Normally, place retry before fallback so errors get a chance to be retried before switching to a replacement outcome:

```java
source
    .retryWhen(retryPolicy)
    .onErrorResume(error -> fallback(error));
```

Here `onErrorResume` receives the remaining error after retries do not apply or attempts are exhausted.

If you reverse the order:

```java
source
    .onErrorResume(error -> fallback(error))
    .retryWhen(retryPolicy);
```

then when the fallback completes normally, `retryWhen` afterward no longer sees an error signal to retry. That may be intentional if the fallback is the final outcome, but is wrong if you meant to retry the source operation first.

A general pattern:

```java
Mono<Result> recover(Mono<Result> source) {
    return source
        .retryWhen(retryTransientErrors())
        .onErrorResume(KnownBusinessException.class,
            this::businessFallback)
        .onErrorResume(UnexpectedException.class,
            this::unexpectedFailurePath);
}
```

Do not chain multiple broad fallbacks without classifying errors. An `onErrorResume(Throwable.class, ...)` placed too early can hide programming bugs, configuration errors, or data issues that ought to be surfaced.

## 9. Retry in Reactor Does Not Equal Broker Redelivery

In Spring Cloud Stream, multiple layers can retry:

- **Reactor retry:** resubscribing to an upstream publisher inside the application.
- **Binder/framework retry:** handling errors observed by the framework/binder at the message handler boundary.
- **Broker redelivery:** the broker redelivering unacknowledged messages per broker mechanics.
- **Business retry:** the application persisting a task to retry later, typically via a database, outbox, or retry destination.

These mechanisms are not equivalent. `retryWhen` inside an event-processing publisher usually repeats a downstream operation such as an API or database call; it does not ask Kafka, RabbitMQ, or Pulsar to redeliver the message from scratch. Conversely, if an error escapes the function, how the binder acknowledges, rolls back, retries, or lets the broker redeliver depends on the binder, version, and configuration.

When `onErrorResume` turns an error into a value or empty completion, outer layers may observe the publisher completing normally. Therefore, do not assume the binder will redeliver the original message. If you want the broker/binder to handle errors, let the error propagate out in a way that mechanism supports, or use an error channel/DLQ with the appropriate configuration.

With reactive bindings, acknowledgements and offset commits can be tied to consuming the publisher; details vary by binder. Test actual runtime behavior instead of inferring it from a `Mono` completing in code.

## 10. Choosing Where to Recover: In the Function or in the Binder?

| Need | Recover in Reactor | Recover in binder/broker |
|---|---|---|
| Retry a transiently failing HTTP call for one event | Fits `retryWhen` around that call | Binder does not necessarily know which layer failed the HTTP call |
| Convert a business error into `REJECTED` | Fits `onErrorResume` with a specific exception type | No broker redelivery needed if that is the final business outcome |
| Message fails to deserialize before invoking function | Cannot use operators inside an uninvoked function | Handle at binder/conversion/error-handling boundary |
| Want broker to redeliver message when function fails | Propagate error outward; do not swallow with a success fallback | Use binder and broker retry/ack/redelivery |
| Quarantine permanently failing message | Can publish DLQ inside function if contract allows | Can use binder DLQ/error channel |
| Shared source failure prevents whole stream from continuing | Recover at stream scope or let error escape | Binder can restart/reconnect consumer per its mechanics |

Pick one layer as the primary retry owner for each error category. If Reactor retries four times including the initial attempt, the binder also redelivers multiple times, and the broker adds its own retry policy, total calls to a dependency can multiply dramatically. Budget total retries across layers and avoid unbounded nested retries.

## 11. Error Recovery When Composing Multiple Functions

A composed pipeline may include multiple steps:

```text
orders.created
      |
      v
normalizeOrder
      |
      v
validateOrder
      |
      v
reserveInventory
      |
      v
orders.ready
```

If one reactive step emits an error and does not recover, the error can propagate through the composition and fail message processing. You can place `onErrorResume` inside each step if that step has a valid fallback, or place a unified policy at the single-message processing boundary.

Do not place a fallback at the end of a multi-message `Flux` if the intent is only to skip one failing message. In that setup, one element's error can terminate the entire outer publisher before the fallback runs. Create a dedicated inner publisher per message and handle errors inside that inner publisher.

If a step has side effects such as reserving inventory, design compensation or idempotency. For instance, `reserveInventory` succeeds but payment fails; retrying the whole pipeline might reserve inventory a second time. Store saga state, use commands with idempotency keys, and emit compensating events when needed.

## 12. Retries Must Be Side-Effect Safe

Retrying means an operation may execute multiple times. Before using `retryWhen`, determine:

- Is the operation read-only or does it mutate state?
- Could the first attempt have succeeded while the response timed out?
- Does the target API support idempotency keys?
- Does the database have unique constraints or an inbox table to prevent duplicate writes?
- Is there a transaction covering the entire operation or only part of it?
- Once retries are exhausted, where are message and business states stored?

For example, when creating a payment request, use a stable idempotency key derived from the order or event ID:

```java
Mono<PaymentResult> authorize(OrderEvent event) {
    return paymentClient.authorize(
        event.orderId(),
        event.eventId() // idempotency key defined by the API contract
    );
}
```

If the payment client supports idempotency, repeated calls with the same key can return the same result rather than creating multiple transactions. Actual parameter names and semantics depend on the payment API; not every service supports this mechanism.

With databases, you can insert `eventId` into an inbox table and update business state in the same transaction. For flows emitting events after database writes, a transactional outbox keeps state mutations synchronized with events queued for publishing. These patterns complement retries; `retryWhen` alone does not guarantee exactly-once processing.

## 13. Timeouts, Backoff, and Load Limits

Retries must be bounded. If each dependency call has a 3-second timeout, retrying three times with backoff can keep a single event in the pipeline for many seconds. Design an overall per-event timeout budget and consider concurrent events.

Measures commonly combined:

- Set per-call dependency timeouts using `timeout(Duration)`.
- Use backoff and jitter to avoid synchronized retry waves.
- Retry only transient errors; never retry data or authorization errors.
- Bound `flatMap` concurrency to avoid spawning excessive simultaneous requests.
- Use a circuit breaker or bulkhead when a dependency experiences prolonged outages.
- Enforce a business deadline; once exceeded, transition state or quarantine instead of holding the message indefinitely.

Example bounding concurrency:

```java
events.flatMap(event -> processOne(event), 16);
```

The value `16` bounds concurrently subscribed inner publishers in this operator. It is not the partition count, instance count, or retry count. Pick it according to database, API, and broker capacity.

## 14. Testing `onErrorResume` and `retryWhen`

Reactive tests should verify subscription counts, fallback outputs, error scope, and whether errors propagate outward. Reactor Test provides `StepVerifier` to assert publisher signals.

Example testing retries followed by success:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

class RetryPolicyTest {

    @Test
    void retriesTransientFailureThenSucceeds() {
        AtomicInteger attempts = new AtomicInteger();

        Mono<String> source = Mono.defer(() -> {
            if (attempts.incrementAndGet() < 3) {
                return Mono.error(new TransientOrderDependencyException());
            }
            return Mono.just("accepted");
        });

        Mono<String> result = source.retryWhen(
            Retry.backoff(3, Duration.ofMillis(1))
                .maxBackoff(Duration.ofMillis(5))
                .filter(error -> error instanceof TransientOrderDependencyException)
        );

        StepVerifier.create(result)
            .expectNext("accepted")
            .verifyComplete();

        assertEquals(3, attempts.get());
    }
}
```

Scenarios to include in the test suite:

| Scenario | What to verify |
|---|---|
| Transient failure then success | `retryWhen` resubscribes to the publisher the expected number of times |
| Non-retryable error | `filter` predicate rejects retry and error reaches fallback or caller |
| Retries exhausted | Final error is emitted or translated per `onRetryExhaustedThrow` |
| Known business error | `onErrorResume` returns the expected business outcome |
| One failing event among many | That event's publisher recovers; other events continue processing per policy |
| Outer Flux-level error | Confirm whole-stream fallback replaces the remainder as designed |
| DLQ publish failure | DLQ error is not swallowed and remains observable to outer layers |
| Retried side effects | Idempotency prevents duplicate records or transactions |
| Broker redelivery | Integration tests verify ack/retry/DLQ with a real binder |

Unit tests with `StepVerifier` verify Reactor logic. Integration tests with the test binder or a real broker are required to verify how Spring Cloud Stream and the broker handle acknowledgements, redelivery, offsets, and DLQs.

## 15. Observing Errors and Retries in Production

Measure the following separately:

- Retry counts by error type and dependency.
- Events succeeding after retry and events exhausting retry budgets.
- Business fallbacks such as `REJECTED` or `PENDING`.
- Messages sent to DLQ and DLQ publish failures.
- Per-event processing latency, total retry duration, and timeouts.
- Consumer lag/backlog and oldest message age.
- Errors escaping the reactive function to the binder.

Logs should include `eventId`, `correlationId`, `orderId`, or appropriate business identifiers, error type, attempt count, and dependency name. Avoid logging full payloads or secrets. For metrics, never use arbitrary message IDs as labels since cardinality can grow without bound.

When a message retries repeatedly, determine whether it is retrying inside Reactor, being redelivered by the binder, or sitting in a retry topic/queue. Without distinguishing layers, investigations can lead to increasing retries everywhere and worsening system load.

## 16. Recovery Policy Selection Workflow

When designing a reactive function in Spring Cloud Stream:

1. Identify which step can fail: deserialization, validation, dependency calls, database writes, or output publishing.
2. Classify errors into business errors, transient errors, and non-recoverable errors.
3. Determine scope: a single message, a composition step, or the entire Flux.
4. Use `retryWhen` around the publisher of transient and safely repeatable operations.
5. Use `onErrorResume` for meaningful business fallbacks, quarantine, or switching to another publisher.
6. Place retry before fallback if you want to retry before substituting the result.
7. Ensure side-effecting operations are idempotent or backed by proper transactions/outbox/inbox.
8. Decide which errors propagate to the binder for layer-level acknowledgement, retry, or DLQ.
9. Set timeouts, backoff, jitter, concurrency, and an overall retry budget.
10. Test single-event errors, whole-stream errors, DLQ failures, redelivery, and duplicates.
11. Monitor retries, fallbacks, DLQ, lag, and recovery times in production.

## 17. Self-Check

- [ ] Can explain that an error is a terminal signal of `Mono`/`Flux`.
- [ ] Can distinguish `onErrorResume` from `retryWhen`.
- [ ] Know how to use `Retry.backoff`, `maxBackoff`, and `filter` to bound transient-error retries.
- [ ] Can explain why `Mono.defer` is useful around operations needing resubscription.
- [ ] Can distinguish per-message inner-publisher recovery from whole-`Flux` recovery.
- [ ] Know how the order of `retryWhen` and `onErrorResume` changes behavior.
- [ ] Can distinguish Reactor retries from binder retries and broker redelivery.
- [ ] Can recognize duplicate side-effect risks and apply idempotency.
- [ ] Can design fallbacks, DLQs, timeouts, backoff, and concurrency bounds.
- [ ] Can test retries, fallbacks, error scope, and real acknowledgement behavior.

## Conclusion

`onErrorResume` replaces an error signal with a fallback publisher; `retryWhen` resubscribes to a publisher when an error satisfies a retry policy. In reactive functions processing multiple messages, operator placement defines recovery scope: place operators inside each event's publisher to isolate per-message failures, or outside the chain for whole-stream recovery when intentional. Retries must be bounded, error-classified, and idempotent. At the same time, distinguish Reactor retries from binder and broker retry/redelivery/acknowledgement; only integration tests on the appropriate binder confirm real delivery behavior.

