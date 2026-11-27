# Impact of Multiple Subscriptions on Call Counts and Statistics

## Objectives

In Reactor, creating a `Mono` or `Flux` does not mean the HTTP call has run yet. A publisher only executes when a subscription occurs. A publisher can be subscribed to multiple times; depending on how the publisher is created and shared, each subscription can trigger a new request, reuse a cached result, or receive data from an active stream. When a publisher is protected by Spring Cloud CircuitBreaker, how subscriptions are organized also affects how many permits are granted and how many outcomes the Circuit Breaker records.

After this lesson, you will be able to:

- Distinguish the publisher creation phase from the subscription phase.
- Explain why two subscriptions to a cold publisher typically produce two requests and two Circuit Breaker evaluations.
- Predict the impact of `cache()`, `share()`, and Circuit Breaker placement on actual request counts and statistical samples.
- Distinguish retries placed inside versus outside the Circuit Breaker.
- Control unintended subscriptions, observe metrics, and test behavior with multiple subscribers.

## Creating a publisher and executing a publisher

Reactor separates two phases:

1. **Assembly:** the application builds an operator chain and receives a `Mono` or `Flux`. Typically, these steps only describe the work to be done.
2. **Subscription:** a subscriber registers to receive signals. The publisher begins executing according to the semantics of the data source and the operators in the chain.

Example:

```java
Mono<Product> product = webClient.get()
        .uri("/products/{id}", "p-100")
        .retrieve()
        .bodyToMono(Product.class);
```

The code above creates a publisher. The HTTP request has not been sent merely because the `product` variable was assigned. When a subscription occurs, `WebClient` executes the request. With a cold publisher like a `Mono` created from a `WebClient` call, each independent subscription typically initiates a new request:

```java
product.subscribe(value -> log.info("Subscriber A: {}", value));
product.subscribe(value -> log.info("Subscriber B: {}", value));
```

Two `subscribe` calls create two subscriptions. With the cold publisher in this example, the catalog service typically receives two requests. Reusing the same `product` variable does not automatically share results between two subscribers.

Some sources are hot publishers or are already shared/cached. They can emit the same data stream to multiple subscribers, or late subscribers only receive what the source's semantics permit. Therefore, you cannot deduce network request counts solely from the number of `Mono`/`Flux` variables; inspect where the publisher is created and where sharing/caching operators are placed.

## How does each subscription pass through the Circuit Breaker?

With reactive integration, `ReactiveCircuitBreaker.run` takes a publisher and a fallback function. When a subscriber subscribes to the protected publisher, the Circuit Breaker operator participates in the subscription process. With a cold publisher, each subscription typically triggers an independent call attempt: the Circuit Breaker checks call permission, the source executes, and the outcome is recorded when the chain terminates.

```java
ReactiveCircuitBreaker breaker = factory.create("catalog");

Mono<Product> protectedProduct = Mono.from(
        breaker.run(
                webClient.get()
                        .uri("/products/{id}", "p-100")
                        .retrieve()
                        .bodyToMono(Product.class),
                error -> Mono.just(Product.unavailable("p-100"))));
```

If `protectedProduct` is a cold publisher and is subscribed to twice, there will typically be two passes through the Circuit Breaker and two requests to the service. Each pass can consume a call permit, be recorded as a success/failure, or be rejected depending on the state and outcome.

For example, with `slidingWindowType: COUNT_BASED`, `slidingWindowSize: 10`, and `minimumNumberOfCalls: 5`, five independently completed subscriptions can produce five samples in the window. If all five fail and the exceptions are recorded as failures, the failure rate reaches 100% once the minimum sample count is met. The circuit can transition to `OPEN` according to `failureRateThreshold`.

In `HALF_OPEN`, the number of permitted subscriptions is also bounded by `permittedNumberOfCallsInHalfOpenState`. A cold publisher subscribed to multiple times can consume multiple probes. Once permits are exhausted, subsequent subscriptions can be rejected and routed to the fallback.

## Placing subscriptions in the right layer

In a WebFlux application, a controller typically returns a `Mono` or `Flux` so the framework performs the subscription. Do not manually call `subscribe()` inside a service and then return that same publisher to the controller:

```java
// Avoid: creates an extra subscription outside the WebFlux-managed lifecycle.
public Mono<Product> findById(String id) {
    Mono<Product> result = callProtectedService(id);
    result.subscribe();
    return result;
}
```

The code above can create two subscriptions: one triggered manually by the service and one triggered by the framework when writing the response. With a cold source, the request can run twice; the Circuit Breaker can also record two calls.

Return the publisher to the caller and let the framework manage the lifecycle:

```java
public Mono<Product> findById(String id) {
    return callProtectedService(id);
}
```

Only subscribe manually when intentionally creating an independent processing flow, such as a background task with its own lifecycle and monitoring. In that case, clearly define who manages errors, subscription cancellation, and backpressure.

## Implementation pattern with ReactiveCircuitBreakerFactory

This gateway example creates the Circuit Breaker once per dependency ID. `Mono.defer` constructs the request chain per subscription, and `ReactiveCircuitBreaker.run` protects each execution:

```java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class CatalogGateway {
    private final WebClient webClient;
    private final ReactiveCircuitBreaker catalogBreaker;

    public CatalogGateway(
            WebClient webClient,
            ReactiveCircuitBreakerFactory<?, ?> factory) {
        this.webClient = webClient;
        this.catalogBreaker = factory.create("catalog");
    }

    public Mono<Product> findById(String id) {
        return Mono.defer(() -> {
            Mono<Product> request = webClient.get()
                    .uri("/products/{id}", id)
                    .retrieve()
                    .bodyToMono(Product.class);

            return Mono.from(catalogBreaker.run(
                    request,
                    error -> Mono.just(Product.unavailable(id))));
        });
    }
}
```

`Product` and `Product.unavailable` are application data types. `Mono.defer` ensures each subscription creates a new request publisher and executes the call within the protected boundary. If subscriber A and subscriber B both subscribe to the result of `findById`, each subscriber typically triggers an independent request and a Circuit Breaker evaluation.

If the caller only needs one result, pass the publisher along without manually subscribing multiple times. If a single request needs to be shared among multiple consumers, explicitly choose a sharing operator and its placement relative to the Circuit Breaker.

## Impact of cache() and Circuit Breaker placement

`cache()` stores a publisher's terminal signal so subsequent subscribers receive the stored signal instead of re-triggering the upstream source. Where `cache()` is placed determines whether the Circuit Breaker sees one subscription or multiple subscriptions.

**Protect first, cache after:**

```java
Mono<Product> protectedCall = Mono.from(
        catalogBreaker.run(remoteCall,
                error -> Mono.just(Product.unavailable(id))))
        .cache();
```

The first subscriber passes through the Circuit Breaker and executes the request. The final outcome of the chain is cached. Subsequent subscribers receive the cached signal; they neither create new subscriptions on the Circuit Breaker nor trigger new requests. For this publisher, the Circuit Breaker typically records one call to populate the cache.

**Cache the source first, protect after:**

```java
Mono<Product> cachedRemoteCall = remoteCall.cache();

Mono<Product> protectedCall = Mono.from(
        catalogBreaker.run(cachedRemoteCall,
                error -> Mono.just(Product.unavailable(id))));
```

Every subscriber to `protectedCall` still passes through the Circuit Breaker. However, `cachedRemoteCall` executes the upstream source only once and replays the cached signal. As a result, the Circuit Breaker can record multiple subscriptions while the target service receives only one network request.

| Placement | Passes through Circuit Breaker with multiple subscribers | Typical cold source executions |
|---|---:|---:|
| `breaker.run(source).cache()` | One pass when the cache is populated. | One request. |
| `breaker.run(source.cache())` | One pass per subscriber. | One shared request. |
| `breaker.run(source)` without cache/share | One pass per subscriber. | One request per subscriber. |

`cache()` also caches error signals or empty completions. If the source emits an error once and that error is cached, later subscribers still receive the stored error. When cache sits before the Circuit Breaker, each subscription can cause the Circuit Breaker to re-evaluate the old error signal even though no new request reaches the service. When cache sits after the Circuit Breaker, a fallback result can also become the cached signal. Choose appropriate TTL, invalidation, and cache scope policies; do not use an unbounded cache for data that must refresh frequently.

## Impact of share() and publish()

`share()` allows multiple subscribers to share a subscription to an upstream source. With `Flux`, connecting and disconnecting also depend on the active subscriber count and `refCount` semantics; with `Mono`, terminal signals may be replayed to later subscribers. Exact behavior should be verified against the publisher type and Reactor version. `share()` does not provide business-level TTL or invalidation policies like a dedicated cache.

The placement of `share()` also affects statistics:

```java
// Circuit Breaker upstream of share: subscribers share one protected execution.
Mono<Product> oneProtectedExecution = Mono.from(
        catalogBreaker.run(remoteCall, fallback)).share();

// Circuit Breaker downstream of share: each subscriber goes through the breaker,
// while the upstream source can be shared.
Mono<Product> sharedSource = remoteCall.share();
Mono<Product> protectedPerSubscriber = Mono.from(
        catalogBreaker.run(sharedSource, fallback));
```

In the first case, concurrent subscribers share a single subscription to the protected publisher; the Circuit Breaker typically sees one call. In the second case, each subscriber registers through the Circuit Breaker, while the `share()` source may create only one upstream subscription for the active group of subscribers. Consequently, Circuit Breaker evaluations can outnumber actual network requests.

The behavior of `share()` depends on the publisher type and when subscribers arrive or leave. With `Flux` using `refCount`, when subscriber count drops below the threshold, the connection can be cancelled; a new subscriber afterward can create a new upstream connection. With `Mono`, verify terminal signal replay semantics in the Reactor version in use. If you need TTL-based storage, refresh, or explicit invalidation, use a cache mechanism with proper policies instead of relying on `share()`.

## Retries inside versus outside the Circuit Breaker

Where `retryWhen` is placed determines whether the Circuit Breaker observes each attempt or only the final outcome of the retry sequence.

**Retry outside the Circuit Breaker:**

```java
Mono<Product> retriedOutside = Mono.from(
        catalogBreaker.run(remoteCall,
                error -> Mono.error(error)))
        .retryWhen(retrySpec);
```

Each retry resubscribes to the protected publisher. Each attempt can consume a call permit and produce a separate statistical outcome. If the first attempt causes the circuit to transition to `OPEN`, the next retry attempt can be rejected immediately without calling the target service.

**Retry inside the Circuit Breaker:**

```java
Mono<Product> retriedInside = Mono.from(
        catalogBreaker.run(
                remoteCall.retryWhen(retrySpec),
                error -> Mono.just(Product.unavailable(id))));
```

The Circuit Breaker wraps the entire retry chain and typically records one final outcome for the outer subscription. The target service may still receive multiple requests due to retries, but the Circuit Breaker only observes the final outcome of the sequence. This can cause network requests to outnumber Circuit Breaker recorded calls.

| Retry placement | What the Circuit Breaker observes | Requests to target service |
|---|---|---|
| Outside `run` | Each subscription/attempt passing through the breaker. | Potentially multiple requests; later ones may be rejected by `OPEN`. |
| Inside the supplier/publisher passed to `run` | Final outcome of the retry chain per outer subscription. | Potentially multiple requests within a single breaker pass. |

The example uses `Mono.error(error)` in the fallback to let the error propagate out so retrying can proceed. If the fallback converts the error into a success value, the outer `retryWhen` will not retry because the chain completed successfully. Coordinate retry counts, backoff, timeouts, and Circuit Breaker thresholds; excessive retries can amplify load while a service is recovering.

## Multiple subscriptions in flatMap and concurrency limits

A `flatMap` chain can create subscriptions to inner publishers for many elements:

```java
Flux<Product> products = ids.flatMap(
        id -> catalogGateway.findById(id),
        8);
```

The `8` parameter limits how many inner publishers are subscribed to concurrently within this `flatMap`. If each element calls a dependency and each inner publisher goes through a Circuit Breaker, each subscription can consume a call permit. The concurrency limit on `flatMap` controls concurrency in this flow, but it does not replace a Bulkhead because other call paths in the application may share the same dependency.

If you need to limit total concurrent calls to a dependency, configure a Bulkhead aligned with your implementation and reactive model. Monitor subscription counts, actual request counts, rejected calls, and active tasks to confirm which limit is taking effect.

## Subscription cancellation and statistics

A subscriber can cancel a subscription before the publisher finishes, such as when a client disconnects or an outer timeout operator ends the stream. Cancellation is not equivalent to a successful call. How the Circuit Breaker releases call permits or records cancellation depends on the operator and implementation version; do not blindly lump cancellations into successes or failures when analyzing metrics.

If an HTTP request has already been sent, cancelling the subscription also does not guarantee that the client or remote server stops work immediately. Configure timeouts on the HTTP client, verify connector cancellation capabilities, and monitor in-flight requests after subscriber cancellation.

## Monitoring subscriptions and the Circuit Breaker

With Resilience4j and Micrometer, commonly useful metrics include:

- `resilience4j.circuitbreaker.calls`: call counts by outcome.
- `resilience4j.circuitbreaker.state`: instance state.
- `resilience4j.circuitbreaker.not.permitted.calls`: rejected subscriptions/calls.
- `resilience4j.circuitbreaker.buffered.calls`: outcomes stored in the statistics window.
- `resilience4j.circuitbreaker.failure.rate` and `resilience4j.circuitbreaker.slow.call.rate`: rates used for threshold evaluation.

Exact metric names and tags can vary by version, registry, and configuration. Add logging or tracing at these boundaries:

- When the publisher is created, log the dependency ID and correlation ID if needed.
- When subscription starts, log a unique subscription ID to distinguish multiple subscribers sharing a publisher.
- When the HTTP request is actually sent, log the logical endpoint and start time.
- When the chain finishes, log the outcome, error, fallback, timeout, or cancellation.

Do not log sensitive data or tokens. When comparing numbers, distinguish three counts: subscriptions to the protected publisher, actual requests to the dependent service, and outcomes recorded by the Circuit Breaker. They can differ when using cache, share, retry, or fallback.

## Hands-on verification of multiple subscriptions

Run this in a test environment with a catalog endpoint whose request count you can observe:

1. Create a cold `Mono` using `WebClient` and wrap it with `ReactiveCircuitBreaker.run`.
2. Subscribe twice to the same publisher. Count requests on the target service and inspect Circuit Breaker metrics; with an unshared cold source, there are typically two requests and two evaluations.
3. Place `cache()` after the protected publisher and subscribe twice. Confirm only the first subscription passes through the Circuit Breaker and triggers an upstream request.
4. Place `cache()` before the Circuit Breaker and subscribe twice. Confirm the Circuit Breaker can record two subscriptions while the HTTP source runs only once.
5. Try `share()` with both `Mono` and `Flux`, including concurrent subscribers and subscribers arriving after source completion; note the replay/connection semantics of your Reactor version.
6. Place `retryWhen` outside and inside `run` in turn; compare actual request counts against Circuit Breaker recorded outcomes.
7. Cancel a subscription before the request finishes; inspect metrics, logs, I/O cancellation behavior, and remaining active requests.

Record subscriber count, subscription count, HTTP request count, success/failure outcomes, fallback count, and Circuit Breaker state. Use the same scenario while changing operator positions to see clearly how changes stem from flow organization.

## Common mistakes

- **Assuming creating a Mono has already sent the HTTP call:** requests typically only run when subscribed.
- **Subscribing to the same cold publisher multiple times:** each subscriber can trigger a new request and a separate statistical evaluation.
- **Manually subscribing in a service and then returning the publisher:** can create an extra subscription outside the WebFlux-managed subscription.
- **Placing cache on the wrong side of the Circuit Breaker:** network request counts and statistical samples may no longer align.
- **Using share instead of a TTL-backed cache:** `share()` provides no business expiration or invalidation policy; replay/connection semantics also depend on Mono, Flux, and Reactor version.
- **Retrying outside the breaker without accounting for attempts:** each retry can consume extra call permits and add statistical samples.
- **Retrying inside the breaker while watching only Circuit Breaker metrics:** one final sample can represent multiple network requests.
- **Treating cancellation as success:** cancelled subscriptions must be analyzed separately according to operator behavior.
- **Leaving concurrency unbounded:** `flatMap` can open many concurrent subscriptions and pressure the dependency.

When working with reactive streams, treat subscription as the starting point of an execution. Clearly decide whether each subscriber needs its own request or should share a result, then place `cache`, `share`, retry, and Circuit Breaker according to the desired semantics. Doing so keeps Circuit Breaker metrics aligned with the behavior your system actually needs to protect.
