# Time Limiting in Reactive Flows and Handling Cancellation

In Spring Cloud applications using WebClient and Reactor, calls to dependent services typically return a Mono or Flux. A publisher may fail to emit a result for a long time, or keep emitting data without completing. If the upstream request has already exhausted its time budget while the call keeps running, resources can stay tied up and the returned result is no longer useful.

With reactive flows, you must set appropriate time limits and understand how cancellation propagates. Reactor provides the `timeout` operator to emit an error when a publisher fails to respond on time and cancel the upstream subscription. Spring Cloud CircuitBreaker can wrap the publisher to record timeout errors and switch to a fallback. However, cancellation only asks upstream components to stop work; it does not guarantee that the remote server has stopped processing.

## What is a timeout in a reactive flow?

A timeout defines the maximum duration a call is allowed to wait according to application policy. When the deadline expires, the stream emits a timeout error signal instead of waiting indefinitely.

For `Mono`, `timeout(Duration)` bounds the time from when subscription begins until the Mono emits a result or completes. For example:

~~~java
Mono<Product> product = webClient.get()
        .uri("/products/{sku}", sku)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(2));
~~~

If the Mono does not complete within two seconds, Reactor emits a `TimeoutException` error and cancels the source publisher's subscription. This deadline covers connection wait time, response wait time, and processing in the publisher chain starting from subscription. Individual HTTP client timeouts still need to be configured to bound each network stage and also protect call paths that do not pass through this operator.

For `Flux`, distinguish between an inter-element timeout and a deadline for the entire stream. `Flux.timeout(Duration)` typically bounds the wait interval for the next signal; if the stream emits items steadily, it can continue longer than Duration. If an overall deadline is needed, place the limit at the request boundary or aggregate a finite stream into a Mono and apply timeout to the whole operation. Do not treat an inter-element timeout as if it were the total duration limit of a long-lived stream.

## What is cancellation and when does it happen?

Reactive Streams allows a subscriber to cancel a subscription via the `cancel()` signal. When cancellation is sent upstream, publishers and operators are requested to stop emitting data and release resources they manage.

Cancellation can occur in several situations:

- A user closes the page or the HTTP client disconnects.
- The upstream request hits its deadline and cancels the processing stream.
- The `timeout` operator expires and cancels the source publisher.
- An operator such as `take` or business logic decides no more data is needed.
- An aggregating publisher is canceled once another branch already provides enough results.

Cancellation is a distinct stream control signal. It is neither an exception emitted via `onError` nor synonymous with a call failing in a business sense. Therefore, do not assume by default that every cancellation increments the circuit breaker's failure count. Monitor cancellations separately and verify the specific behavior of the operator/backend version in use.

## How do timeout and cancellation work together?

When a Mono times out, Reactor performs two actions in sequence:

1. Cancels the source publisher's subscription to ask upstream to stop work.
2. Emits a timeout error to the downstream subscriber, unless the application specified a fallback publisher directly inside the timeout operator.

General flow:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant T as Timeout operator
    participant W as WebClient publisher
    participant S as Dependent service
    C->>T: subscribe
    T->>W: subscribe upstream
    W->>S: Send HTTP request
    Note over T: Deadline expires
    T-->>W: cancel()
    T-->>C: onError(TimeoutException)
    Note over S: Server may still be processing
~~~

Reactor can cancel the client-side request and release connection resources when the HTTP client supports cancellation. However, if the server has already received the request and started processing, the client closing the connection does not guarantee the server stops the task. A write transaction may have already executed even though the client received no response.

For write operations such as payment or inventory reservation, a timeout produces an uncertain outcome: the caller does not know whether the transaction completed on the server. Never automatically resend a non-idempotent operation just because the client timed out. Use an idempotency key, transaction ID, or status-lookup API to determine the outcome before retrying.

## Placing timeout in WebClient and Spring Cloud CircuitBreaker

You can combine Reactor `timeout` with `ReactiveCircuitBreaker`. The timeout operator is placed on the publisher protected by the circuit breaker so timeout errors pass through the circuit breaker and are recorded under its classification policy.

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@Service
public class ReactiveInventoryClient {

    private final WebClient webClient;
    private final ReactiveCircuitBreaker inventoryBreaker;

    public ReactiveInventoryClient(
            WebClient.Builder builder,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.webClient = builder
                .baseUrl("http://inventory-service")
                .build();

        this.inventoryBreaker =
                circuitBreakerFactory.create("inventory-read");
    }

    public Mono<InventoryResult> find(String sku) {
        Mono<Inventory> request = Mono.defer(() ->
                webClient.get()
                        .uri("/inventory/{sku}", sku)
                        .retrieve()
                        .bodyToMono(Inventory.class)
        )
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                // Record that the upstream subscription was canceled.
            }
        })
        .timeout(Duration.ofMillis(900));

        return inventoryBreaker.run(
                request.map(InventoryResult::fresh),
                error -> {
                    if (error instanceof TimeoutException) {
                        return Mono.just(InventoryResult.unavailable(sku));
                    }
                    return Mono.just(InventoryResult.unavailable(sku));
                }
        );
    }
}
~~~

`Inventory` and `InventoryResult` are illustrative types. In a real application, substitute your project's data models and fallback policy.

Points to note:

- `Mono.defer` creates the call on subscription, avoiding starting work before the publisher is subscribed.
- `timeout` is placed inside the publisher passed to the circuit breaker, so timeouts are emitted as errors of the protected call.
- `doFinally` sits before `timeout`, so it observes the cancellation sent upstream by timeout. If the caller cancels the entire request, the CANCEL signal can pass through here as well.
- The fallback returns an intentionally degraded result. Do not assume that a timeout means the product does not exist or inventory equals 0.
- Circuit breaker and timeout have two distinct responsibilities: timeout limits the duration of one call; circuit breaker decides whether to allow subsequent calls to reach the dependency.

If you use the `timeout(Duration, fallbackPublisher)` overload to replace a timeout error with fallback data before the publisher reaches the circuit breaker, the circuit breaker may only see a successful outcome and fail to record the timeout as an error. When timeouts need to contribute to failure rate, let the timeout error pass through the circuit breaker and handle it in the circuit breaker's fallback or at a higher layer.

## How do TimeLimiter and Reactor timeout differ?

The name TimeLimiter typically refers to Resilience4j's mechanism for bounding the duration of Future- or CompletionStage-based tasks. For reactive publishers, cancellation is driven by Reactive Streams and Reactor operators.

| Mechanism | Primary target | Behavior on expiration |
|---|---|---|
| Resilience4j TimeLimiter | Protected Future or CompletionStage | Completes the wrapped task with a timeout error; may request canceling Future per config. |
| Reactor `Mono.timeout` | A Mono | Cancels source subscription and emits TimeoutException if no result arrives on time. |
| Reactor `Flux.timeout` | A Flux | Tracks wait time for signals; typically inter-element duration. |
| HTTP client timeout | Connection, response, or network operation | Bounds the network stage according to client capabilities. |

Example TimeLimiter configuration for a Future-based call path:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory-lookup:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

`cancelRunningFuture` requests canceling the running Future when TimeLimiter expires. Whether work actually stops depends on the Future, executor, and whether the underlying task responds to interrupts. For WebClient and Reactor, use publisher cancellation and HTTP client timeout configuration; do not assume `cancelRunningFuture` automatically cancels all reactive activity or stops processing on the remote server.

Some Spring Cloud CircuitBreaker versions or configurations may integrate timeouts according to the backend. Identify clearly whether a call path uses synchronous, Future, or reactive APIs and check extension points for that exact version. Avoid layering overlapping timeouts without knowing which timeout fires first or which error the circuit breaker actually records.

## Allocating the time budget for the whole request

A dependency call's timeout must fit inside the upstream request's time budget. If an API must respond in two seconds, you cannot give the entire two seconds to the inventory service and only afterward run caching, database work, and response serialization.

Budget example:

| Stage | Illustrative budget |
|---|---:|
| Validation and input handling | 100 ms |
| Calling inventory service | 700 ms |
| Reading local data and building response | 300 ms |
| Buffer for scheduler, network, and serialization | 400 ms |
| Total API deadline | 1,500 ms |

Numbers should be tuned to SLAs and actual latency distributions. Set each dependency timeout lower than the request's remaining budget. For multiple sequential calls, sum durations; for calls running in parallel, budget by the slowest branch plus aggregation time.

Multiple timeout layers can be configured:

- Connect timeout to bound connection setup time.
- Response or read timeout to bound response wait time per the HTTP client.
- Reactor timeout to set a deadline on the publisher chain.
- Upstream request deadline to protect the entire processing lifecycle.

Timeouts must be coordinated. If the HTTP client timeout is much longer than the reactive deadline, Reactor may cancel the publisher first, yet the client still has to handle closing resources. If a lower-layer timeout is far shorter, the application may raise errors even though the upstream request still had budget left.

## Combining timeouts with retries and circuit breakers

Retries can overcome transient errors, but each retry consumes time and adds load. Bound retry count and total deadline.

For example, setting a per-attempt timeout and a total timeout for the whole chain:

~~~java
Mono<Product> request = Mono.defer(this::callProductService)
        .timeout(Duration.ofMillis(400))
        .retryWhen(
                Retry.max(1)
                        .filter(this::isTransientFailure)
        )
        .timeout(Duration.ofMillis(900));
~~~

In this example, each attempt has a 400 ms limit and the entire retry chain has a 900 ms deadline. Retries apply only to identified transient errors. Add backoff and jitter where the system allows, and avoid retrying when the circuit breaker is OPEN or when errors are not recoverable by retrying.

Where the circuit breaker sits relative to retries changes what unit is counted. If retries sit inside the publisher protected by the circuit breaker, the circuit breaker typically observes the final outcome of the whole retry chain as one logical call. If each retry passes through a separate circuit breaker, individual attempts can be counted separately. Choose the placement matching the application's measurement and protection goals.

For write operations, only retry when the API supports idempotency or the application can determine with certainty that the previous attempt did not execute. Client-side cancellation and timeout are not proof that the server has not processed the request.

## Cancellation does not mean background tasks stopped

Cancellation is a stop request from subscriber to publisher. Cooperating reactive operators release their subscriptions and resources. However, blocking tasks or calls to libraries without cancellation support may keep running.

Example avoiding running a blocking call directly on the event loop:

~~~java
Mono.fromCallable(() -> blockingInventoryClient.find(sku))
        .subscribeOn(Schedulers.boundedElastic())
        .timeout(Duration.ofSeconds(1));
~~~

Moving the blocking call onto boundedElastic avoids blocking the event loop, yet a timeout still does not guarantee the blocking method stops immediately. Subscription cancellation may request interrupting the thread; a blocking library may ignore interrupts or keep waiting on a socket. Configure timeouts on the HTTP client or JDBC driver itself, cap threads and connection pools, and test the library's cancellation behavior.

With WebClient, cancellation is normally propagated to Reactor Netty to cancel the client-side HTTP exchange. Even so, the server may already have received and continued processing. For reads, this usually just wastes some resources. For writes, idempotency or status lookup is needed to handle uncertain outcomes.

## Observing timeouts and cancellations

Distinguish signals in operations:

- Timeout: the operator or client deadline expired.
- Caller cancellation: the upstream client no longer needs the result.
- Circuit breaker OPEN: the call was rejected before reaching the dependency.
- Connect or response error: the HTTP client emitted an error before the application timeout expired.
- Normal completion: the publisher emitted results and completed.

You can use `doFinally` to observe the terminal signal type:

~~~java
publisher.doFinally(signalType -> {
    switch (signalType) {
        case CANCEL:
            // Increment cancellation counter.
            break;
        case ON_ERROR:
            // Record error.
            break;
        case ON_COMPLETE:
            // Record completion.
            break;
        default:
            break;
    }
});
~~~

The snippet illustrates distinguishing signals. Metrics should use bounded labels such as circuit breaker ID, dependency, and signal type. Do not put request ID, SKU, or user ID into metric labels. Record correlation IDs in logs or traces to link events across a request.

Useful indicators:

- Timeouts per dependency and endpoint.
- Caller cancellations and timeout-induced cancellations.
- p50, p95, and p99 latency of reactive calls.
- Calls rejected by the circuit breaker.
- Fallback counts and fallback outcomes.
- Blocking tasks still running after the caller canceled.
- Connections or threads held too long.

If timeouts rise while server error rates do not, the dependency may be slow or the timeout too low. If cancellations spike, check client disconnects, gateway or frontend deadlines, and requests canceled when users navigate away.

## Testing timeouts and cancellation

Use mock publishers that can delay, emit errors, emit data, or record cancellation to verify behavior. Do not check only the final response; also verify the source publisher received cancellation and resources were released.

| Scenario | Outcome to verify |
|---|---|
| Mono finishes before timeout | Returns normal result. |
| Mono does not finish within deadline | Emits TimeoutException and cancels source subscription. |
| Caller cancels subscription before completion | Upstream receives cancellation; CANCEL signal is recorded. |
| WebClient times out | Client cancels exchange if possible; do not assume server definitely stops processing. |
| Circuit breaker is OPEN | Does not call source service; fallback handles the rejected call. |
| Timeout placed inside circuit breaker | Timeout is recorded per the circuit breaker's error policy. |
| Timeout converted to fallback before circuit breaker | Verify the circuit breaker may see only a successful substitute result. |
| Flux emits steadily yet runs long | Verify inter-element timeout is not mistaken for an overall deadline. |
| Blocking call is canceled | Verify whether the library reacts to interrupts or its own timeout. |
| Write operation times out | Use idempotency key or status lookup before retrying. |

In tests, use Clock or virtual-time publisher timers to control time and avoid long waits. With WebClient, use a mock server capable of delaying responses or closing connections to verify timeouts, cancellation, and network error handling.

## Implementation workflow

1. Identify the request deadline and the budget allocated to each dependent call.
2. Use Reactor `timeout` for a Mono or reactive chain needing a deadline; understand Flux inter-element timeouts.
3. Configure connect/read/response timeouts on the HTTP client to bound network stages.
4. Place the time-bounded publisher inside ReactiveCircuitBreaker so timeouts are recorded properly.
5. Keep fallbacks separate from the timeout operator when the circuit breaker needs to count timeouts as errors.
6. Handle cancellation by releasing resources and measuring CANCEL signals; do not assume the remote server stopped.
7. Cap retries within the total budget and retry only recoverable transient errors.
8. For write operations, use idempotency or status lookup to handle uncertain outcomes after timeouts.
9. Test timeouts, caller cancellations, circuit breaker OPEN state, blocking calls, and long-lived Flux streams.

In reactive flows, timeout establishes a time bound and cancellation requests that the source publisher stop work. When combined properly with Spring Cloud CircuitBreaker, the application can switch to fallbacks promptly and reduce resources held by slow calls. Design deadlines around the request budget, monitor cancellations separately, and remember that stopping waiting on the client does not mean the server-side transaction was canceled.
