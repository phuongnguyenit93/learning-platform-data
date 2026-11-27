# Decorating Mono or Flux Through the Common API

## Lesson Objectives

In a Spring WebFlux application, calls to dependent services typically return a Reactor publisher: `Mono` represents at most one result, while `Flux` represents a sequence of zero, one, or many elements. When a remote service is slow or unavailable, the circuit breaker needs to protect the asynchronous call without losing the reactive properties of the processing pipeline.

Spring Cloud CircuitBreaker provides a common API for applications to create and use a reactive circuit breaker. With this API, you can wrap a `Mono` along with a fallback function. When you need to protect a `Flux`, it is important to understand the boundaries of the common API and how to use Resilience4j's Reactor operator. Distinguishing these two approaches helps you choose the right abstraction, preserve streaming, and avoid accidentally turning a large data stream into a collection that must be loaded entirely into memory.

After this lesson, you will be able to:

- Distinguish between `Mono` and `Flux` in the context of calls to dependent services.
- Use `ReactiveCircuitBreakerFactory` to protect a `Mono` and provide a fallback.
- Use `CircuitBreakerOperator` to decorate a `Mono` or `Flux` with Resilience4j Reactor.
- Place fallbacks at the right position in the operator chain so the breaker still records failures.
- Understand how a subscription is counted and why long-lived streams need appropriate protection.
- Verify behavior when the breaker is closed, open, and attempting recovery in a reactive application.

## 1. Mono and Flux in a Remote Call

Reactor is the reactive library used by Spring WebFlux. The two commonly encountered core types are:

| Type | Number of elements | Examples |
| --- | --- | --- |
| Mono<T> | At most one element, or completes empty, or emits an error. | Looking up a product by ID; retrieving inventory information. |
| Flux<T> | Zero, one, or many elements; can emit continuously until completion or error. | Fetching a list of products; receiving an event stream; reading paginated or streamed data. |

`WebClient` provides methods to create publishers from an HTTP response. `bodyToMono(Product.class)` returns `Mono<Product>`; `bodyToFlux(Product.class)` returns `Flux<Product>`. Creating a publisher usually does not send the request immediately. With a cold publisher, the request is executed when subscribed.

A call to `inventory-service` typically returns a single result, making `Mono` suitable:

    Mono<InventoryResponse> response = webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryResponse.class);

A call that retrieves a list or data stream can return a `Flux`:

    Flux<Product> products = webClient.get()
        .uri("/products")
        .retrieve()
        .bodyToFlux(Product.class);

By default, a circuit breaker protects the dependency-calling operation, not individual data elements. When decorating a publisher, determine whether one subscription represents a single HTTP call, a streaming flow, or a business task. This boundary determines whether the breaker's statistics are meaningful.

## 2. The Common Reactive API of Spring Cloud CircuitBreaker

Spring Cloud CircuitBreaker provides `ReactiveCircuitBreakerFactory` to create a breaker by name. The common `ReactiveCircuitBreaker` API accepts a `Mono` along with a fallback function returning a `Mono`. For example:

    import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
    import org.springframework.stereotype.Service;
    import org.springframework.web.reactive.function.client.WebClient;
    import reactor.core.publisher.Mono;

    @Service
    public class ReactiveInventoryGateway {

        private final WebClient webClient;
        private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public ReactiveInventoryGateway(
                WebClient webClient,
                ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.webClient = webClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public Mono<InventoryResponse> find(String sku) {
            Mono<InventoryResponse> request = webClient.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);

            return circuitBreakerFactory.create("inventory").run(
                request,
                error -> Mono.just(InventoryResponse.unknown(sku))
            );
        }
    }

In this example:

- `create("inventory")` obtains the reactive circuit breaker named `inventory`. This name links the call to its corresponding configuration and metrics.
- `request` is the publisher that executes the HTTP request when subscribed.
- `run` accepts the primary publisher and the fallback function. The fallback returns a `Mono` of the same data type as the primary publisher.
- `InventoryResponse.unknown(sku)` is an application-defined method representing an unknown state; it is not a built-in Spring class.

When the breaker is `CLOSED`, the call is forwarded and the outcome is recorded. If recorded failures exceed the threshold, the breaker can transition to `OPEN`. In the `OPEN` state, subsequent calls fail fast and the fallback function can produce an alternative response. After the wait duration, the breaker transitions to `HALF_OPEN` to allow a limited number of probe calls. The outcomes of those probes determine whether the breaker returns to `CLOSED` or re-opens.

The fallback must fit the business semantics. If inventory cannot be queried, returning `UNKNOWN` may be safer than claiming the product is in stock or out of stock. Another fallback might use unexpired cached data, or return a business error so the API layer prompts the user to retry. Do not call `inventory-service` again inside the fallback, as doing so can create loops and add load to an already failing dependency.

The common API here targets `Mono`. Do not assume `ReactiveCircuitBreaker.run` has an overload accepting `Flux` directly in every version of Spring Cloud CircuitBreaker. When you need to protect a `Flux`, use the corresponding reactive implementation operator or build an application adapter layer to provide a unified interface.

## 3. Decorating Mono or Flux with Resilience4j Reactor

Resilience4j provides a Reactor operator for decorating publishers. `CircuitBreakerOperator` can be used with both `Mono` and `Flux`. This operator applies a Resilience4j `CircuitBreaker` to the subscription lifecycle and terminal signals of the publisher.

The example below illustrates obtaining a `CircuitBreaker` from `CircuitBreakerRegistry` and protecting a `Flux`:

    import io.github.resilience4j.circuitbreaker.CircuitBreaker;
    import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
    import io.github.resilience4j.reactor.circuitbreaker.operator.CircuitBreakerOperator;
    import org.springframework.stereotype.Service;
    import org.springframework.web.reactive.function.client.WebClient;
    import reactor.core.publisher.Flux;

    @Service
    public class ReactiveProductGateway {

        private final WebClient webClient;
        private final CircuitBreaker productStreamBreaker;

        public ReactiveProductGateway(
                WebClient webClient,
                CircuitBreakerRegistry registry) {
            this.webClient = webClient;
            this.productStreamBreaker = registry.circuitBreaker("product-stream");
        }

        public Flux<Product> list() {
            return webClient.get()
                .uri("/products")
                .retrieve()
                .bodyToFlux(Product.class)
                .transformDeferred(
                    CircuitBreakerOperator.of(productStreamBreaker)
                );
        }
    }

`CircuitBreakerRegistry` is Resilience4j's registry. In a Spring Boot application integrated with Resilience4j, the registry is typically configured and provided via the corresponding auto-configuration. If you create a registry manually, ensure the application's instance configurations and the registry are used consistently. Your dependencies must include Resilience4j's Reactor operator; with the Spring Cloud CircuitBreaker reactive starter, inspect the resolved dependencies to confirm the reactor module is present.

`transformDeferred` applies the operator to the publisher at subscription time. This fits cold reactive publishers and binds the protection boundary to each subscription. `CircuitBreakerOperator` does not change the data type: `Mono` remains `Mono` and `Flux` remains `Flux`.

You can use the same operator with `Mono`:

    public Mono<Product> find(String id) {
        CircuitBreaker breaker = registry.circuitBreaker("product-detail");

        return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class)
            .transformDeferred(CircuitBreakerOperator.of(breaker));
    }

This example uses the Resilience4j Reactor operator directly. If the project wants to remain dependent on Spring Cloud's abstraction, consider using `ReactiveCircuitBreakerFactory` for `Mono`. For `Flux`, you can wrap `CircuitBreakerOperator` usage inside an application-specific adapter so business code calls a unified internal API.

## 4. Creating a Unified Application API for Mono and Flux

In a codebase that has calls returning both `Mono` and `Flux`, a development team may want a common facade. This facade is an application-defined API; it is not a default `ReactiveCircuitBreaker` overload in Spring Cloud.

For example, an internal contract can separate two methods by publisher type:

    public interface ReactiveCallProtection {

        <T> Mono<T> protectMono(
            String name,
            Mono<T> source,
            Function<Throwable, Mono<T>> fallback
        );

        <T> Flux<T> protectFlux(
            String name,
            Flux<T> source
        );
    }

An implementation can use `ReactiveCircuitBreakerFactory` for `Mono` and `CircuitBreakerRegistry` with `CircuitBreakerOperator` for `Flux`. Gateways then depend only on `ReactiveCallProtection`; the details of which abstraction is chosen are centralized in the adapter.

Some points to keep in mind when designing a facade:

- Breaker names must be stable and represent a dependency or group of calls with equivalent operational characteristics.
- Do not create breakers per request, user, or product ID, as instance counts and statistical data will grow uncontrollably.
- Do not return a fallback publisher with a different type from the original publisher.
- Explicitly define which errors are recorded, which errors are ignored, and which fallbacks are permitted.
- If the facade offers overloads for `Mono` and `Flux`, document the semantics of each subscription so users do not mistake a `Flux` for multiple independent calls.

A facade standardizes how application code invokes protection, but it does not erase the behavioral differences between a single-result publisher and a multi-element stream.

## 5. Placing Fallback at the Right Position in the Operator Chain

When using the Resilience4j Reactor operator directly, the position of `onErrorResume` affects what data the circuit breaker records.

For the breaker to see errors from the primary publisher before transitioning to the fallback, place the circuit breaker operator before `onErrorResume`:

    Flux<Product> products = webClient.get()
        .uri("/products")
        .retrieve()
        .bodyToFlux(Product.class)
        .transformDeferred(CircuitBreakerOperator.of(productBreaker))
        .onErrorResume(
            CallNotPermittedException.class,
            error -> Flux.empty()
        );

In this example, if the breaker is `OPEN`, Resilience4j rejects the call with `CallNotPermittedException`. The downstream `onErrorResume` can turn this case into `Flux.empty()`. Depending on business requirements, the fallback could also return cached data or an event indicating a degraded state. `Flux.empty()` is only appropriate when having no data is acceptable and does not mislead users.

If `onErrorResume` is placed before the circuit breaker:

    Flux<Product> products = webClient.get()
        .uri("/products")
        .retrieve()
        .bodyToFlux(Product.class)
        .onErrorResume(error -> Flux.empty())
        .transformDeferred(CircuitBreakerOperator.of(productBreaker));

Then the upstream error is converted into a normal completion signal before reaching the breaker. The breaker may record the subscription as successful, making the failure rate appear lower than it actually is. This is a common configuration mistake when the fallback is placed too early in the chain.

In practice, do not catch every `Throwable` and turn it into `Flux.empty()` if the application needs to distinguish network errors, server errors, deserialization errors, and breaker-rejection errors. Handle error types according to business policy. With the common Spring Cloud API for `Mono`, the fallback function is passed directly to `run`; with the Resilience4j operator, the fallback is usually attached downstream using Reactor operators.

## 6. One Subscription Is One Protected Call

A cold publisher typically performs its work when subscribed. Consequently, the same `Mono` or `Flux` can be subscribed to multiple times, and each subscription can trigger a call to the remote service.

For example:

    Mono<Product> request = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .transformDeferred(CircuitBreakerOperator.of(productBreaker));

    Mono<Product> first = request;
    Mono<Product> second = request;

If both `first` and `second` are subscribed to, the cold publisher can send two HTTP requests. The circuit breaker evaluates each execution according to the operator's semantics. Avoid creating unintended multiple subscriptions—such as subscribing once to log and again to return data. Use appropriate Reactor operators to share or observe results when needed.

With `Flux`, distinguish two cases:

- **A `Flux` representing a finite request:** for example, `GET /products` returning a list. One subscription can be treated as one dependency call; the breaker evaluates the outcome when the publisher completes or errors.
- **A `Flux` representing a long-lived or infinite stream:** for example, a connection receiving continuous events. The entire subscription can stay open for a very long time without a normal completion signal. A breaker wrapping the whole stream does not automatically count each individual event as a separate call.

If an infinite stream is wrapped as a single call, success state or completion duration may not be recorded in a way that serves statistical evaluation. Consider protecting the connection-establishment step, monitoring disconnect signals, and using separate timeouts and reconnect mechanisms. Do not use a circuit breaker as an error counter for individual messages within a long-lived stream.

If each input element needs to make its own dependent service call, place the breaker on the publisher of each individual call. For example:

    Flux<EnrichedProduct> enriched = productIds.flatMap(id ->
        webClient.get()
            .uri("/products/{id}/details", id)
            .retrieve()
            .bodyToMono(ProductDetails.class)
            .transformDeferred(CircuitBreakerOperator.of(detailsBreaker))
            .map(details -> EnrichedProduct.from(id, details))
    );

Each `Mono` inside `flatMap` represents an individual call and is protected by the breaker. Limit the concurrency of `flatMap` if the source can emit many IDs simultaneously; a circuit breaker is not a concurrency-limiting mechanism. A bulkhead or concurrency limit serves that separate role.

## 7. Do Not Collect Flux into Mono Just to Use the Common API

An apparently simple way to use `ReactiveCircuitBreaker.run` is to convert a `Flux` into a `Mono` via `collectList()`:

    Mono<List<Product>> allProducts = webClient.get()
        .uri("/products")
        .retrieve()
        .bodyToFlux(Product.class)
        .collectList();

    return circuitBreakerFactory.create("product-list").run(
        allProducts,
        error -> Mono.just(List.of())
    );

This approach fits when the dataset is finite, bounded in size, and business logic genuinely requires the entire list before processing. However, `collectList()` must buffer elements in memory until the `Flux` completes. For large lists or unbounded streams, it can increase memory usage or never emit a result.

Do not convert a `Flux` to a `Mono` solely to work around an API limitation. If streaming is needed, keep `Flux` and use `CircuitBreakerOperator` or an application adapter supporting `Flux`. If an aggregated result is needed, choose a `reduce`, `count`, or `collect` operation suited to the data requirements and input size limits.

## 8. Configuring the Breaker and Monitoring Reactive Calls

Both Spring Cloud's reactive circuit breaker and the Resilience4j operator rely on the corresponding breaker configuration. Example configuration of an instance for the product stream:

    resilience4j:
      circuitbreaker:
        instances:
          product-stream:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
            slowCallDurationThreshold: 1s
            slowCallRateThreshold: 60
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 3

This is an illustrative configuration. With `COUNT_BASED`, the window stores outcomes of the most recent N calls. `minimumNumberOfCalls` specifies the minimum number of samples before evaluating rates. `failureRateThreshold` and `slowCallRateThreshold` determine when the breaker opens based on failure rate or slow-call rate. `waitDurationInOpenState` defines how long it stays `OPEN` before attempting recovery; `permittedNumberOfCallsInHalfOpenState` limits the number of probe calls.

Choose configuration based on publisher characteristics:

- For finite HTTP requests, measure response time and failure rate per request.
- For a `Flux` returning a large list, check completion time and data limits.
- For long-lived streams, separate connection establishment from per-message processing; use dedicated timeouts, heartbeats, reconnects, and stream metrics.
- For many parallel calls, consider a bulkhead or concurrency limit in addition to the circuit breaker.

For observability, track `CLOSED`, `OPEN`, and `HALF_OPEN` states, successful/failed/rejected call counts, slow-call rates, and response times. For reactive flows, also observe subscription counts, active stream counts, reconnect counts, data decoding errors, and fallback usage counts. These indicators help distinguish whether the breaker is blocking calls to a failing dependency or whether a stream is encountering issues in the data-processing layer.

Spring Boot Actuator and Micrometer can be used to export application and Resilience4j metrics once the appropriate integration is configured. Exact metric names and endpoints depend on versions, registries, and exposure settings. Verify the application's actual metrics, secure management endpoints, and avoid putting sensitive data such as tokens or user payloads into tags.

## 9. Hands-On Exercise: Protecting Mono and Flux

Build a reactive gateway with two capabilities: looking up details for a single product and reading a list of products from `catalog-service`.

**Part A — Mono via the Common API**

1. Create a `WebClient` pointing to `catalog-service`.
2. Write a `findById` method returning `Mono<Product>`.
3. Inject `ReactiveCircuitBreakerFactory` and create a breaker named `product-detail`.
4. Wrap the `Mono` using `run` and provide a fallback representing unknown data or an appropriate business error.
5. Make the dependent service return errors and slow responses to observe the fallback and breaker state.

**Part B — Flux via the Operator**

1. Write a `list` method returning `Flux<Product>`.
2. Obtain a `CircuitBreaker` named `product-stream` from `CircuitBreakerRegistry`.
3. Decorate the `Flux` with `transformDeferred(CircuitBreakerOperator.of(...))`.
4. Place `onErrorResume` after the operator and handle only errors permitted by business rules.
5. Verify that the publisher still streams elements as a `Flux` and that upstream errors are recorded by the breaker.

**Part C — Testing Subscriptions and Long-Lived Streams**

1. Subscribe to a cold publisher twice and observe the actual number of requests.
2. Test a finite `Flux` and a simulated long-lived stream.
3. Identify when the publisher completes, emits an error, or is canceled.
4. Evaluate whether a single breaker wrapping the entire stream provides meaningful statistics.
5. If each element requires a separate call, move the breaker onto the per-call publisher inside `flatMap` and limit concurrency appropriately.

Once finished, you should be able to explain why `Mono` can use `ReactiveCircuitBreaker.run` directly, how to use the Resilience4j Reactor operator to protect `Flux`, how fallback placement affects statistics, and what operation a subscription represents. This understanding enables protecting reactive calls while preserving publisher semantics and operational telemetry.
