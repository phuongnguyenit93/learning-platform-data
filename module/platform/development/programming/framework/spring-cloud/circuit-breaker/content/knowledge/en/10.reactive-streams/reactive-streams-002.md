# Wrapping WebClient with ReactiveCircuitBreakerFactory

In a Spring WebFlux application, `WebClient` performs HTTP calls reactively and returns publishers such as `Mono<T>` or `Flux<T>`. To protect those calls with a Circuit Breaker, Spring Cloud CircuitBreaker provides `ReactiveCircuitBreakerFactory`. The factory creates a Circuit Breaker by name; the created instance can wrap a `WebClient` publisher and apply a fallback when the call produces an error or is rejected.

In the **SPRING_CLOUD_CIRCUIT_BREAKER** module, this integration helps prevent cascading failures when a dependent service is slow or unavailable. You need to preserve the reactive chain from request creation to returning the result, so that the Circuit Breaker observes success, error, and execution duration signals without blocking threads with `block()`.

## 1. Role of ReactiveCircuitBreakerFactory

`ReactiveCircuitBreakerFactory` is the entry point for creating reactive Circuit Breakers in the Spring Cloud abstraction. An application typically injects the factory into a service or component that calls a dependent service, then calls `create(name)` to obtain the corresponding Circuit Breaker.

Key components:

| Component | Role |
| --- | --- |
| `WebClient` | Creates HTTP requests and returns reactive publishers |
| `ReactiveCircuitBreakerFactory` | Creates a Circuit Breaker by identifier |
| `ReactiveCircuitBreaker` | Wraps the primary publisher, tracks outcomes, and forwards errors to the fallback |
| `Mono<T>` | The publisher type used by Spring Cloud's `ReactiveCircuitBreaker.run` API for a single result or a completing stream |
| `Flux<T>` | Multi-element publisher that WebClient can return; for streaming flows, choose an appropriate integration strategy rather than assuming every Spring Cloud abstraction overload accepts Flux directly |
| Fallback | Creates a replacement publisher when the primary publisher fails or the Circuit Breaker rejects the call |

Overall flow:

~~~mermaid
flowchart TD
    A[Service receives request] --> B[Create ReactiveCircuitBreaker by name]
    B --> C[Create publisher from WebClient]
    C --> D[ReactiveCircuitBreaker.run]
    D --> E{Primary publisher}
    E -->|Completes successfully| F[Return data from dependent service]
    E -->|Emits onError| G[Fallback receives Throwable]
    E -->|Circuit OPEN| G
    G --> H[Fallback publisher]
    F --> I[Return reactive result to caller]
    H --> I
~~~

The key point is that the `WebClient` publisher must be passed into `ReactiveCircuitBreaker.run`. When the publisher emits an `onError` signal, the Circuit Breaker can record the failed call and invoke the fallback if one is provided.

## 2. Declaring dependencies and configuration

The application needs the Spring Cloud CircuitBreaker starter corresponding to Resilience4j and the WebFlux dependency to use `WebClient`. Specific artifact names should be chosen according to the Spring Cloud release train and Spring Boot version used by the project; avoid mixing incompatible versions.

Example configuration for a Circuit Breaker named `inventory` in `application.yml`:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

In this example, the Circuit Breaker tracks the most recent 20 calls and requires at least 10 outcomes before evaluating rates. If the failure rate reaches 50% or the slow call rate reaches 60%, the circuit can transition to OPEN. After a 10-second wait duration, the circuit permits up to 3 trial calls in HALF_OPEN.

These are illustrative values. Adjust them based on traffic volume, normal latency, HTTP client timeouts, and the service-level objectives of the dependent service. The name `inventory` in the configuration must match the name passed to `reactiveCircuitBreakerFactory.create("inventory")`.

## 3. Creating WebClient and injecting the factory

You can declare a shared `WebClient` as a bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class HttpClientConfiguration {
    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

In the service, inject `ReactiveCircuitBreakerFactory` and `WebClient`:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

@Service
public class InventoryGateway {
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final WebClient inventoryWebClient;

    public InventoryGateway(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            WebClient inventoryWebClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryWebClient = inventoryWebClient;
    }
}
~~~

Spring injects the factory configured by the active implementation, such as Resilience4j. The wildcards in the generic type keep the service decoupled from the implementation's internal configuration types.

## 4. Wrapping WebClient calls with ReactiveCircuitBreaker

The `getInventory` method below calls the Inventory service and returns `Mono<Inventory>`:

~~~java
import reactor.core.publisher.Mono;

public Mono<Inventory> getInventory(String sku) {
    ReactiveCircuitBreaker circuitBreaker =
            circuitBreakerFactory.create("inventory");

    Mono<Inventory> primary = inventoryWebClient.get()
            .uri("/items/{sku}", sku)
            .retrieve()
            .bodyToMono(Inventory.class);

    return circuitBreaker.run(
            primary,
            failure -> Mono.just(Inventory.unavailable(sku))
    );
}
~~~

This snippet performs three steps:

1. The factory creates a Circuit Breaker named `inventory`.
2. `WebClient` creates the primary publisher. The request is not necessarily sent at the declaration line; WebClient publishers are lazy and execution happens upon subscription.
3. `circuitBreaker.run` wraps the primary publisher and accepts a fallback function. The fallback receives a `Throwable` and returns a `Mono<Inventory>` whose type is compatible with the primary publisher.

If the Inventory service returns a valid result, the `Mono` emits the data and completes. If the call throws an exception, the Circuit Breaker can record the failure and pass the cause to the fallback. If the circuit is OPEN, the call is rejected before the request is sent to the dependent service; the fallback can handle that rejection error.

The example assumes the application has an `Inventory` class with an `unavailable(sku)` method to represent a state where stock cannot be verified. Do not use a quantity of 0 as a fallback if 0 means confirmed out of stock.

## 5. Converting HTTP statuses into exceptions

With `retrieve()`, WebClient emits `WebClientResponseException` by default for 4xx and 5xx responses. You can rely on this default behavior so the Circuit Breaker observes HTTP errors. When you want to classify statuses by business rules, use `onStatus`:

~~~java
private Mono<Inventory> requestInventory(String sku) {
    return inventoryWebClient.get()
            .uri("/items/{sku}", sku)
            .retrieve()
            .onStatus(
                    status -> status.value() == 404,
                    response -> Mono.error(
                            new InventoryNotFoundException(sku))
            )
            .onStatus(
                    status -> status.is5xxServerError(),
                    response -> response.createException()
            )
            .bodyToMono(Inventory.class);
}

public Mono<Inventory> getInventory(String sku) {
    ReactiveCircuitBreaker circuitBreaker =
            circuitBreakerFactory.create("inventory");

    return circuitBreaker.run(
            requestInventory(sku),
            failure -> fallbackInventory(sku, failure)
    );
}
~~~

In this example, 404 is translated into a dedicated business exception; 5xx statuses use the exception created by WebClient. If 404 is a normal business outcome, you can configure Resilience4j to ignore `InventoryNotFoundException` when calculating the failure rate, while still letting the calling layer handle that exception appropriately.

Example fallback that distinguishes errors:

~~~java
private Mono<Inventory> fallbackInventory(String sku, Throwable failure) {
    if (failure instanceof InventoryNotFoundException) {
        return Mono.error(failure);
    }

    return inventoryCache.findRecent(sku)
            .map(value -> value.withStale(true))
            .defaultIfEmpty(Inventory.unavailable(sku));
}
~~~

The fallback returns cached data if available and marks it as stale. If no cached entry exists, it returns the unavailable state. For a product-not-found business error, the fallback propagates the error so the API can return an appropriate response.

Do not use `onErrorReturn` or `onErrorResume` to turn an error into a success value before passing the publisher into the Circuit Breaker if the goal is for the Circuit Breaker to record the original error. Let the error signal reach `run`, and handle it through the Circuit Breaker fallback or an outer layer afterward.

## 6. Fallbacks must return a compatible publisher

With Spring Cloud's `ReactiveCircuitBreaker` API, both the primary call and the fallback typically use `Mono<T>`; the fallback does not return an `Inventory` object directly, but rather a `Mono<Inventory>`. When you need to protect a streaming `Flux<T>`, use the Resilience4j Reactor operator integration shown later, where the fallback publisher can be attached using Reactor operators.

Example fallback backed by a cache:

~~~java
private Mono<Inventory> fallbackFromCache(String sku, Throwable failure) {
    return inventoryCache.findRecent(sku)
            .switchIfEmpty(Mono.just(Inventory.unavailable(sku)));
}
~~~

You can pass a method reference if the signature matches:

~~~java
return circuitBreaker.run(
        requestInventory(sku),
        this::fallbackFromCache
);
~~~

When the fallback needs extra context such as `sku`, a lambda lets you pass that variable along with the `Throwable`:

~~~java
return circuitBreaker.run(
        requestInventory(sku),
        failure -> fallbackFromCache(sku, failure)
);
~~~

Do not call `block()` to fetch cached data inside a fallback. Doing so blocks the thread and defeats the benefits of reactive programming. Return the cache's publisher so Reactor composes the asynchronous operations.

If the fallback itself raises an error, the resulting publisher emits `onError` and that error propagates to the upstream caller. You should monitor both primary call errors and errors when producing fallback results.

## 7. Adding a timeout to the publisher

The Circuit Breaker can evaluate slow calls via `slowCallDurationThreshold`, but that threshold does not replace a timeout. If a call never completes, the application must bound the wait time so the publisher emits a timeout error and releases associated resources.

You can place a timeout on the publisher:

~~~java
import java.time.Duration;

private Mono<Inventory> requestInventory(String sku) {
    return inventoryWebClient.get()
            .uri("/items/{sku}", sku)
            .retrieve()
            .bodyToMono(Inventory.class)
            .timeout(Duration.ofSeconds(2));
}
~~~

When a timeout occurs, the publisher emits a `TimeoutException`; if the timeout is inside the publisher passed to the Circuit Breaker, the Circuit Breaker can observe this error and apply its recording policy. You can configure Resilience4j's own TimeLimiter or HTTP client timeouts depending on requirements. Avoid configuring multiple overlapping timeouts without clearly determining which limit takes effect first.

If you need to use TimeLimiter, check the reactive configuration for your specific Spring Cloud CircuitBreaker and Resilience4j versions. Timeout configuration can vary across versions and client types.

## 8. Understanding lazy execution, subscription, and cancellation

WebClient publishers are lazy: declaring a `Mono` variable does not mean the request has been sent. The request is triggered when a subscriber subscribes. The Circuit Breaker wraps the publisher and applies protective logic during subscription.

This has several consequences:

- If a controller or caller neither subscribes to the publisher nor returns it to a managed reactive runtime, the request will not run.
- Do not call `subscribe()` manually inside a service just to "trigger" the request; return the publisher to the caller so WebFlux manages subscription and errors.
- When a client cancels a subscription, the cancellation signal can propagate down to the source publisher. Do not treat caller-initiated cancellation as an ordinary HTTP failure.
- If using `Mono.defer`, publisher construction runs per subscription. This is useful when you need to read contextual data or build the operation at execution time.

Example using `defer`:

~~~java
Mono<Inventory> primary = Mono.defer(() ->
        inventoryWebClient.get()
                .uri("/items/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class)
);

return circuitBreaker.run(
        primary,
        failure -> fallbackInventory(sku, failure)
);
~~~

You do not need to wrap every WebClient call in `Mono.defer`; WebClient already creates a lazy publisher. Only use it when you want to defer the publisher construction step itself or when data must be re-evaluated for each subscription.

## 9. Combining with Flux and multi-element streams

For endpoints returning multiple items, WebClient can return `Flux<Item>`. The `ReactiveCircuitBreaker` API in the Spring Cloud abstraction typically provides the `run(Mono<T>, Function<Throwable, Mono<T>>)` overload; therefore, do not assume you can pass `Flux<T>` directly into a factory-created circuit breaker.

If the stream is finite and bounded in size, you can collect it into a `Mono<List<Item>>`, protect that Mono with the factory, and convert the list back into a Flux:

~~~java
public Flux<Item> getItems() {
    ReactiveCircuitBreaker circuitBreaker =
            circuitBreakerFactory.create("catalog");

    Mono<List<Item>> primary = catalogWebClient.get()
            .uri("/items")
            .retrieve()
            .bodyToFlux(Item.class)
            .collectList();

    return circuitBreaker.run(
            primary,
            failure -> fallbackItems(failure).collectList()
    ).flatMapMany(Flux::fromIterable);
}
~~~

This approach buffers the entire list in memory before emitting the first element. Use it only when results are bounded and collecting all data is appropriate. The fallback must return `Mono<List<Item>>` to match the primary publisher's type. An empty list may lead callers to believe the catalog genuinely has no items when the real cause is service unavailability; choose a result type with an explicit status or emit an appropriate error.

For long-lived or unbounded streaming flows, do not collect all data into a list. If the application uses the Resilience4j Reactor module, you can apply `CircuitBreakerOperator` directly to the Flux and handle errors after the operator:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.reactor.circuitbreaker.operator.CircuitBreakerOperator;
import reactor.core.publisher.Flux;

public Flux<Item> streamItems() {
    CircuitBreaker circuitBreaker =
            circuitBreakerRegistry.circuitBreaker("catalog");

    return catalogWebClient.get()
            .uri("/items/stream")
            .retrieve()
            .bodyToFlux(Item.class)
            .transformDeferred(CircuitBreakerOperator.of(circuitBreaker))
            .onErrorResume(failure -> fallbackItems(failure));
}
~~~

This example uses the Resilience4j Reactor operator directly and requires the Reactor integration dependency along with a Circuit Breaker from the registry. The operator must come before `onErrorResume` so the Circuit Breaker sees the error before the fallback converts the error into a replacement publisher. For a stream that emits partial data before failing, items already sent cannot be retracted; the API must define whether to continue with fallback data, terminate with an error, or mark the stream incomplete.

## 10. Monitoring state and metrics

To evaluate a reactive Circuit Breaker, track the following metrics:

- State per instance: CLOSED, OPEN, or HALF_OPEN.
- Counts of successful, failed, slow, and rejected calls.
- Failure rate and slow call rate compared against configured thresholds.
- Number of fallback invocations and fallback failure rate.
- Primary publisher latency and total time to return the final result.
- Cancelled or timed-out requests if the system records them separately.

Spring Cloud CircuitBreaker combined with Resilience4j can export metrics via Micrometer when the application enables the appropriate configuration. You can use Spring Boot Actuator and a metrics collection system to observe the `inventory` instance. When reading dashboards, distinguish HTTP errors from the dependent service from rejection errors caused by an OPEN circuit.

If the outermost API still returns successful results while fallback invocations increase, the dependent service may be degrading. Surface fallback status or mark stale cached data so UI and operations layers interpret the result accurately.

## 11. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Creating a Circuit Breaker with a name that does not match configuration | Intended instance configuration is not applied | Match the name in `create(...)` with `instances` |
| Not passing the WebClient publisher to `run` | Circuit Breaker does not wrap the protected call | Pass the primary publisher into `run` |
| Using `block()` in a reactive service | Blocks threads and reduces scalability | Return `Mono` or `Flux` to the caller |
| Turning errors into values before the Circuit Breaker | Circuit Breaker may record a success | Let errors reach `run` and use the Circuit Breaker fallback |
| Fallback returning an incompatible publisher type | Compilation failure or API mismatch | Return the matching `Mono<T>` or `Flux<T>` type |
| Treating `Flux.empty()` as always a safe fallback | Masks dependency unavailability | Use a result with explicit status or emit an appropriate error |
| Configuring only slow call threshold without a timeout | Hanging calls can hold resources too long | Configure a timeout on the publisher or HTTP client |
| Not monitoring fallbacks | API can appear healthy while dependencies are failing | Record fallback metrics and Circuit Breaker state |

## 12. Integration workflow

When protecting a WebClient call, you can follow these steps:

1. Choose a stable Circuit Breaker name for the dependency, such as `inventory`.
2. Declare the corresponding instance in the Resilience4j configuration.
3. Inject `ReactiveCircuitBreakerFactory` and `WebClient` into the gateway or service.
4. Build the primary publisher using `retrieve()` or `exchangeToMono()`, converting error statuses into appropriate exceptions.
5. Call `factory.create(name)` and pass the publisher and fallback into `ReactiveCircuitBreaker.run`.
6. Return the publisher to the caller; avoid `block()` and manual `subscribe()` in the service.
7. Test success, HTTP 5xx, timeout, OPEN circuit, and fallback; inspect metrics to confirm the Circuit Breaker records outcomes accurately.

Wrapping WebClient with `ReactiveCircuitBreakerFactory` brings HTTP calls under the same protective mechanism as synchronous operations while preserving the reactive model. When the primary publisher, HTTP status conversion, timeout, and fallback are placed properly, the Circuit Breaker can record dependency failures, open the circuit when needed, and attempt controlled recovery without blocking processing threads.
