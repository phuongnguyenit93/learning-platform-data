# Reactive Pipeline Not Properly Wrapped or Subscribed Multiple Times

## Why Is This Bug Hard to Spot?

In Spring Cloud Circuit Breaker, reactive calls are typically represented by `Mono` or `Flux`. A publisher describes a processing pipeline; it does not execute the request at creation time. For most publishers from `WebClient`, I/O work begins only upon subscription. Therefore, a method can return a `Mono` that looks right, yet the Circuit Breaker may not properly wrap the network call, or a publisher may be subscribed multiple times unintentionally.

Two symptoms often appear together:

- **Pipeline not properly wrapped:** connection errors, timeouts, or HTTP statuses are not recorded in the Circuit Breaker because they occur outside the protected publisher, or are converted into success signals before passing through the breaker.
- **Publisher subscribed multiple times:** the same cold publisher is triggered by multiple subscribers, causing HTTP requests to be sent repeatedly, metrics to increment multiple times, and side-effecting operations to possibly repeat.

In Spring Cloud systems using WebFlux, maintain a clear boundary between creating the publisher, applying the Circuit Breaker, and subscribing. Each subscription can correspond to an actual dependency execution. You cannot infer network request counts solely from how many times a service method is invoked.

## Understand the Lifecycle of Mono and Flux

Reactor publishers are typically created lazily. For example:

```java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", productId)
    .retrieve()
    .bodyToMono(Product.class);
```

This snippet creates a publisher describing the request. Only when a subscriber subscribes does `WebClient` execute the call. A cold publisher can re-execute the entire source for each subscriber:

```java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", productId)
    .retrieve()
    .bodyToMono(Product.class);

product.subscribe();
product.subscribe(); // May trigger a second HTTP request.
```

With `WebClient`, each subscription to a request publisher typically triggers a separate HTTP execution. If the publisher is wrapped by a Circuit Breaker, each protected subscription can be recorded as a separate call. Thus, two subscriptions are not two ways of reading the same result; they can be two dependency calls.

`Mono.just(value)` typically holds an already-created value, whereas `Mono.defer(supplier)` invokes the supplier upon subscription. `Mono.defer` is useful when you need to defer publisher creation or perform per-subscription side work:

```java
Mono<Product> product = Mono.defer(() ->
    webClient.get()
        .uri("/products/{id}", productId)
        .retrieve()
        .bodyToMono(Product.class)
);
```

`defer` does not prevent multiple subscriptions by itself. It ensures publisher creation runs per subscription; if there are two subscribers, the supplier can still run twice. To share a single execution across multiple branches, you must explicitly design result sharing.

## Place the Circuit Breaker Around the Right Dependency Call

With the Spring Cloud Circuit Breaker reactive API, use `ReactiveCircuitBreakerFactory` to create a breaker and pass both the primary publisher and fallback publisher to `run`:

```java
import java.time.Duration;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ProductService {
    private final WebClient webClient;
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public ProductService(
            WebClient webClient,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.webClient = webClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public Mono<ProductView> find(String productId) {
        Mono<ProductView> primary = Mono.defer(() ->
            webClient.get()
                .uri("/products/{id}", productId)
                .retrieve()
                .bodyToMono(Product.class)
                .timeout(Duration.ofSeconds(2))
                .map(ProductView::available)
        );

        return circuitBreakerFactory.create("product-catalog").run(
            primary,
            error -> Mono.just(ProductView.unavailable(productId))
        );
    }
}
```

`primary` contains the HTTP call, timeout, and response mapping. `run` wraps that publisher with the Circuit Breaker and accepts a fallback publisher. Because the timeout sits inside the publisher passed to `run`, timeout signals can be observed and classified by the breaker according to provider configuration. `Product` and `ProductView` are application types; the `unavailable` state should clearly indicate data could not be retrieved.

If using the Resilience4j Reactor operator directly, you can wrap the publisher with `CircuitBreakerOperator`:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.reactor.circuitbreaker.operator.CircuitBreakerOperator;
import reactor.core.publisher.Mono;

Mono<Product> protectedCall = Mono.defer(() ->
    webClient.get()
        .uri("/products/{id}", productId)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(2))
).transformDeferred(CircuitBreakerOperator.of(circuitBreaker));
```

The operator example uses a `CircuitBreaker` instance retrieved from the Resilience4j registry. Choose **one** integration point per call: either the Spring Cloud reactive factory or the operator directly. Do not wrap the same request with both `ReactiveCircuitBreakerFactory.run(...)` and `CircuitBreakerOperator` for the same purpose unless two protection layers are deliberately designed.

## Understand transform and transformDeferred

Reactor provides `transform` and `transformDeferred` to apply a transformation function to a publisher:

- `transform` applies the transformation when the pipeline is assembled. The resulting publisher can still be subscribed to multiple times.
- `transformDeferred` applies the transformation per subscriber. This is useful when the transformation needs to create or obtain a per-subscription decorator.

Example:

```java
Mono<Product> protectedCall = remoteCall
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker));
```

`transformDeferred` is not a deduplication mechanism. If `protectedCall` has two subscribers and the source is cold, the source can still execute twice. Nor does it cache results automatically. To understand call counts, trace actual subscriptions and operator placement in the chain.

When using `ReactiveCircuitBreakerFactory.run`, the factory already handles applying the Circuit Breaker to the publisher. There is no need to wrap additionally with `CircuitBreakerOperator` merely because the publisher was built with `Mono.defer` or `transformDeferred`.

## Bugs Caused by Manually Calling subscribe in Services or Controllers

A common mistake is calling `subscribe()` inside a service and returning a different publisher:

```java
// Avoid: creates a subscription detached from the WebFlux request.
public Mono<ResponseEntity<String>> refresh(String id) {
    productService.find(id).subscribe();
    return Mono.just(ResponseEntity.accepted().body("started"));
}
```

A manually created subscription no longer lives inside the WebFlux request lifecycle. The gateway or controller may return a response before the call finishes; errors may bypass request error handling; client cancellation does not necessarily cancel the detached subscription. If that call is wrapped by a Circuit Breaker, the breaker may still record the subscription, but the application loses the ability to coordinate it with the main response flow.

Return the publisher so the framework manages subscriptions:

```java
public Mono<ResponseEntity<ProductView>> find(String id) {
    return productService.find(id)
        .map(ResponseEntity::ok);
}
```

Only call `subscribe()` at an application boundary explicitly designed for background work, with its own lifecycle, error, retry, and shutdown management. For critical background processing, consider durable queues rather than spawning an unmanaged subscription inside a request handler.

## A Publisher Used Across Multiple Branches Can Call the Dependency Multiple Times

The snippet below appears to reuse the same `Mono` variable, yet a `Mono` from WebClient is cold:

```java
Mono<Product> product = productClient.find(productId);

return Mono.zip(
    product,
    product.map(Product::displayName)
);
```

`Mono.zip` subscribes to each input source. Here both `product` and `product.map(...)` subscribe to the same cold publisher, so upstream can execute twice. If upstream contains WebClient and a Circuit Breaker, there can be two HTTP requests and two breaker recordings.

If two branches need the same result, share the result after applying the Circuit Breaker:

```java
Mono<Product> sharedProduct = productClient.find(productId)
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker))
    .cache();

return Mono.zip(
    sharedProduct,
    sharedProduct.map(Product::displayName)
);
```

In this structure, caching sits after the Circuit Breaker. The protected source executes once for the first subscription; branches share the cached result within that publisher instance. `Mono.cache()` also caches terminal signals, including errors, so understand the publisher's lifetime and scope. Never store a cached publisher in a singleton field if the data depends on a request or user, as that could leak results across unrelated requests.

Cache placement affects what the breaker observes. If caching sits before the Circuit Breaker, multiple subscribers may pass through the breaker yet receive the same terminal signal from an earlier source execution. Then the breaker's recorded call count can differ from actual HTTP requests sent. Choose placement based on measurement goals: the breaker should normally wrap the actual dependency call, and only then should the result be shared across branches in the same business flow.

## Retry and Circuit Breaker Ordering Changes Metrics

`retryWhen` re-subscribes to a publisher on matching errors. Where Retry sits relative to the Circuit Breaker determines whether the breaker observes each attempt or only the final result of the retry sequence.

```java
// Circuit Breaker inside Retry: each retry re-subscribes through the breaker.
Mono<Product> countEachAttempt = remoteCall
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker))
    .retryWhen(retrySpec);

// Retry inside Circuit Breaker: breaker wraps the entire retry chain.
Mono<Product> countLogicalCall = remoteCall
    .retryWhen(retrySpec)
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker));
```

In the first approach, each retry can count as a separate call to the Circuit Breaker. In the second approach, the breaker observes the final outcome of the retried publisher; internal attempts still generate network requests, but are not necessarily recorded as individual calls on the outer breaker. Choose according to measurement goals and verify the decorator ordering of your provider.

Retries can amplify load on a dependency. If one request retries three times and many requests fail simultaneously, the backend can receive a surge larger than the original business traffic. Set attempt limits, backoff, jitter, and an overall deadline. Never retry write operations without idempotency keys or duplicate-processing protection.

## Place Fallbacks After the Boundary Being Measured

Where `onErrorResume` sits affects the outcome the Circuit Breaker sees. If errors are converted into a normal value before applying the breaker, the breaker may record success even though the primary dependency failed:

```java
// Fallback inside the protected boundary: breaker may only see a normal completion.
Mono<ProductView> possiblyMisclassified = remoteCall
    .onErrorResume(error -> Mono.just(ProductView.unavailable()))
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker));
```

If you want the Circuit Breaker to record the dependency failure before the fallback creates an alternative response, place the fallback outside the operator:

```java
Mono<ProductView> correctlyClassified = remoteCall
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker))
    .onErrorResume(error -> Mono.just(ProductView.unavailable()));
```

With Spring Cloud `ReactiveCircuitBreaker`, pass the fallback function directly to `run` so the integration manages recording order and fallback execution:

```java
return reactiveCircuitBreakerFactory.create("catalog").run(
    remoteCall,
    error -> Mono.just(ProductView.unavailable())
);
```

A fallback is a substitute response for the caller; it does not prove the dependency succeeded. Track fallback counts, primary error counts, and Circuit Breaker state separately so an HTTP 200 fallback response does not hide an outage.

## Timeouts Must Sit Inside the Circuit Breaker Region Being Observed

If you want timeouts to count as dependency failures, place the timeout operator inside the publisher protected by the Circuit Breaker:

```java
Mono<Product> protectedWithTimeout = remoteCall
    .timeout(Duration.ofSeconds(2))
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker));
```

When the timeout emits `TimeoutException` inside the publisher, the Circuit Breaker can record it according to the configured predicate. If placed outside the operator, the timeout can cancel the upstream subscription from outside; how the breaker records cancellation depends on the operator/provider and version. Verify with tests and metrics rather than assuming an outer timeout is always counted as a failure.

Reactor's timeout also does not guarantee the server stopped processing the request. For writes, the server may have already executed the side effect while the response arrived too late. Combine timeouts with idempotency and business deadlines.

## Distinguish HTTP Errors, Transport Errors, and Post-Response Processing Errors

With `WebClient.retrieve()`, 4xx/5xx responses are converted into `WebClientResponseException` by default unless status handling is customized. Connection, DNS, or timeout errors usually surface as corresponding transport errors. If using `exchangeToMono` or converting statuses into normal values manually, the Circuit Breaker may not see an exception.

Example converting 5xx statuses into errors before completing the publisher:

```java
Mono<Product> remoteCall = webClient.get()
    .uri("/products/{id}", productId)
    .retrieve()
    .onStatus(
        status -> status.is5xxServerError(),
        response -> response.createException()
    )
    .bodyToMono(Product.class);
```

If a status is turned into a result object like `ProductView.unavailable()` before passing through the Circuit Breaker, the breaker may record a success. Clearly decide which statuses represent dependency errors vs. business outcomes and configure `recordException`, `ignoreException`, or result handling accordingly.

Also define the protected pipeline scope carefully. If only the HTTP call is wrapped while body decoding or a critical transformation sits outside the operator, errors in that step may not count toward the breaker. Conversely, avoid including local business steps unrelated to the dependency in the same failure rate if they can fail independently.

## Long-Lived Flux Streams and Non-Terminating Subscriptions

Reactive Circuit Breakers typically evaluate outcomes when a publisher completes or emits an error. For `Mono`, the lifecycle is short with a single result. For `Flux`, one subscription can emit many elements and stay open for a long time. Wrapping an unbounded stream such as SSE, WebSocket, or an endless event feed can leave the breaker holding the call in flight indefinitely with no terminal signal to evaluate.

For long-lived streams, define protection goals clearly:

- If you need to protect connection establishment, apply timeouts and Circuit Breakers to opening the connection or acquiring the initial stream.
- If you need to track errors mid-stream, use protocol-appropriate metrics, reconnect policies, and health signals.
- Do not treat every `onNext` element as an independent Circuit Breaker call when the operator wraps the whole publisher.
- When a subscriber cancels a stream, verify cancellation releases resources and permits properly; do not automatically treat client disconnects as dependency failures.

Do not use a request-response Circuit Breaker as a substitute for health monitoring of a long-lived streaming connection.

## Diagnose When Requests Are Triggered Multiple Times

When a single business request triggers multiple HTTP requests, check in order:

1. Find all `subscribe()` call sites across controllers, services, and helpers.
2. Check whether the publisher is reused across multiple branches like `zip`, `when`, `flatMap`, or multiple response subscribers.
3. Check `retry`, `repeat`, `cache`, `share`, and multicast operators.
4. Check whether frameworks or filters create extra subscriptions.
5. Count actual subscriptions and actual HTTP requests in a WebClient filter or mock server.
6. Compare subscription counts against Circuit Breaker metrics to determine whether the operator sits before or after the sharing point.

A simple observation technique in development environments:

```java
Mono<Product> remoteCall = Mono.defer(() -> {
    log.debug("Subscribing to catalog request for productId={}", productId);
    return webClient.get()
        .uri("/products/{id}", productId)
        .retrieve()
        .bodyToMono(Product.class);
});

return remoteCall
    .doOnSubscribe(subscription -> log.debug("Catalog publisher subscribed"))
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker));
```

The `doOnSubscribe` log reveals how many subscriptions flow through the publisher. Never log tokens, sensitive data, or personal information. In production, prefer low-cardinality counters/traces instead of debug-logging every request.

## Testing with StepVerifier and Controllable Publishers

Reactive tests should verify how many times the source executes, how many times the fallback runs, and the terminal signal. Example using `Mono.defer` in a mock to count actual subscriptions:

```java
@Test
void oneSubscriptionProducesOneRemoteExecution() {
    AtomicInteger executions = new AtomicInteger();
    when(productClient.find("p-1")).thenReturn(Mono.defer(() -> {
        executions.incrementAndGet();
        return Mono.just(new Product("p-1"));
    }));

    StepVerifier.create(productService.find("p-1"))
        .expectNextMatches(product -> product.id().equals("p-1"))
        .verifyComplete();

    assertThat(executions).hasValue(1);
}
```

To verify whether subscribing twice executes the source twice:

```java
Mono<Product> result = productService.find("p-1");

StepVerifier.create(result)
    .expectNextCount(1)
    .verifyComplete();

StepVerifier.create(result)
    .expectNextCount(1)
    .verifyComplete();

assertThat(executions).hasValue(2);
```

If the design requires calling the dependency only once for multiple branches, add caching or sharing at the right spot and assert execution count stays at one. Do not use a global cache just to make a test pass while hiding a multi-subscription bug.

Scenarios your test suite should cover:

| Scenario | What to Verify |
| --- | --- |
| Single successful subscription | Supplier runs once and breaker records one outcome. |
| Dependency emits exception | Breaker records per predicate and fallback runs exactly once. |
| Two subscribers on a cold publisher | Two executions occur unless result sharing is configured. |
| Multiple branches sharing a post-breaker cached publisher | Dependency is called only once within that publisher's scope. |
| Retry enabled | Actual attempts match retry policy and decorator ordering. |
| Timeout occurs inside protected region | Breaker receives timeout signal per configuration. |
| Subscriber cancels | Resources are released; cancellation is not mistaken for a successful response. |
| Fallback itself fails | Fallback error is propagated/observed separately without hiding the original cause. |

`StepVerifier` lets you test publishers without manually calling `subscribe()` in application code. For retry or timeout durations, use virtual time if the publisher and scheduler support it; avoid long real-time waits in tests. When using a mock HTTP server, count actual requests received—not just client method invocations.

## Distinguish Signals in Metrics

When a publisher is subscribed multiple times, protected calls, HTTP requests, and Circuit Breaker recordings may all increase accordingly. However, if cache, retry, or fallback sit in different positions, those counts do not have to match.

Track separately:

- How many times the service method creates a publisher.
- Number of subscriptions entering the protected publisher.
- Actual HTTP requests sent to the dependency.
- Number of retries.
- Number of Circuit Breaker success, failure, slow-call, or not-permitted recordings.
- Number of fallback invocations and completions.

Tag metrics by stable dependency or breaker IDs. Never put product ID, user ID, request ID, or exception message in tags, as cardinality grows rapidly. Use trace IDs in logs or distributed tracing to follow a specific request.

If actual HTTP requests rise while breaker calls do not, part of the requests may bypass the protected region or retry sits inside the boundary. If breaker metrics rise while requests to the dependency do not, the Circuit Breaker may be rejecting calls, a cache may be serving results, or errors occur before network dispatch. Cross-check all three layers: subscriptions, breaker events, and the HTTP client.

## Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Creating a publisher without returning or subscribing | Call never executes. | Return `Mono`/`Flux` to WebFlux or subscribe at a managed background boundary. |
| Calling `subscribe()` inside service/controller | Subscription detaches from request lifecycle; errors and cancellation become hard to manage. | Return the publisher to the framework. |
| Subscribing multiple times to a cold publisher | Dependency is called multiple times and breaker records multiple invocations. | Audit subscribers, share results when needed, and test execution counts. |
| Wrapping breaker after errors were converted to fallback values | Breaker may only see successes. | Move fallback outside the boundary or use the reactive circuit breaker's fallback API. |
| Placing timeout outside breaker when intending to record timeouts | Breaker may only observe cancellation depending on provider. | Place timeout inside the protected publisher and verify with tests. |
| Using imperative factory followed by `block()` | Blocks the event loop and breaks the reactive model. | Use `ReactiveCircuitBreakerFactory` or Reactor operators. |
| Using both factory and operator for the same dependency call | Two breakers or two metric layers may nest. | Choose one clear integration boundary. |
| Placing breaker after cache or share without understanding semantics | Breaker metrics may not match network requests. | Place breaker around the dependency source, then share results if the goal is counting remote calls. |
| Putting Retry outside breaker while expecting one recording | Each retry can re-subscribe through the breaker. | Clarify decorator ordering and measure both attempts and logical calls. |
| Wrapping an unbounded `Flux` with Circuit Breaker | Calls may never emit a terminal signal for evaluation. | Protect connection setup and monitor streams with dedicated mechanisms. |

## Troubleshooting Workflow

When a reactive pipeline appears unprotected or a dependency is called multiple times, follow these steps in order:

1. Identify which publisher contains the dependency call and whether it is cold, hot, or cached/shared.
2. Sketch the operator chain from source to subscriber, marking Circuit Breaker, timeout, retry, fallback, and cache positions.
3. Confirm WebFlux/controllers return the publisher without spawning detached subscriptions.
4. Count actual subscriptions and HTTP requests using `doOnSubscribe`, mocks, or an HTTP test server.
5. Place the Circuit Breaker around the exact segment to measure; ensure errors and timeouts occur inside the boundary.
6. Decide whether one business call should share results across branches or invoke the dependency separately per branch.
7. Verify Retry, fallback, and cache ordering so metrics reflect what you intend to protect.
8. Run `StepVerifier` for success, error, timeout, cancellation, and multiple subscribers.
9. Cross-check Circuit Breaker metrics against actual dependency request counts before concluding the issue is resolved.

A reactive pipeline is properly protected when the subscription executing the dependency call passes through a Circuit Breaker with a clear boundary, errors intended for tracking are not converted into successes before the breaker observes them, and subscription counts match intended business invocations. Keeping publishers within WebFlux's lifecycle, controlling retry/fallback/cache placement, and verifying with `StepVerifier` prevents duplicate calls, misrecorded failure rates, and distorted protection behavior in Spring Cloud Circuit Breaker.
