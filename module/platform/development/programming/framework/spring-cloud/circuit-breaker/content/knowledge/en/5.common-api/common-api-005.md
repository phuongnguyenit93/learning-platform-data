# ReactiveCircuitBreakerFactory and ReactiveCircuitBreaker

In Spring Cloud applications using WebFlux and Reactor, calls to dependent services typically return `Mono` or `Flux`. To protect these asynchronous calls, Spring Cloud CircuitBreaker provides two main reactive APIs: `ReactiveCircuitBreakerFactory` and `ReactiveCircuitBreaker`.

`ReactiveCircuitBreakerFactory` creates a Circuit Breaker by configuration name. `ReactiveCircuitBreaker` wraps a `Mono` or `Flux` publisher, tracks execution outcomes, and switches to a fallback when the publisher emits an error or the Circuit Breaker rejects the call. These two APIs allow the business layer to use protection mechanisms without depending directly on Resilience4j-specific implementation classes.

This lesson focuses on how to create, use, and configure these two reactive APIs in Spring Cloud CircuitBreaker with Resilience4j, how to write type-safe fallbacks, how to combine timeouts, and how to avoid common pitfalls in Reactor pipelines.

## 1. Roles of the Two APIs

The two components have distinct responsibilities:

- **ReactiveCircuitBreakerFactory** is a Spring-managed factory injected into the application. It creates a `ReactiveCircuitBreaker` by ID, such as `inventory` or `payment`.
- **ReactiveCircuitBreaker** is the object protecting a specific reactive call. It accepts a `Mono` or `Flux`, executes the publisher upon subscription, records the outcome, and applies a fallback when an error occurs.

High-level execution flow:

~~~mermaid
flowchart TD
    A[Service receives request] --> B[ReactiveCircuitBreakerFactory]
    B --> C[Create or retrieve breaker by ID]
    C --> D[ReactiveCircuitBreaker.run]
    D --> E[Mono or Flux calls dependency]
    E --> F{Publisher outcome}
    F -- Success --> G[Return data to caller]
    F -- Error or rejected --> H[Run fallback publisher]
    H --> I[Return degraded result or controlled error]
~~~

The factory is typically injected once into a service, and the breaker is created by ID in the constructor or during component initialization. Using a stable ID binds the breaker to its corresponding configuration and enables monitoring metrics to be distinguished per dependency.

## 2. ReactiveCircuitBreakerFactory

In Spring Cloud CircuitBreaker, `ReactiveCircuitBreakerFactory` is the entry point for creating a reactive breaker. Basic usage:

~~~java
ReactiveCircuitBreaker inventoryBreaker =
        circuitBreakerFactory.create("inventory");
~~~

The string `inventory` is the ID of the Circuit Breaker. When using the Resilience4j implementation, this ID maps to the corresponding instance configuration in `application.yml`, for example:

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
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

In the configuration above, `inventory` is the instance name. If code creates a breaker with a different ID, such as `inventory-api`, the `inventory` configuration will not automatically apply to that new ID. Keep the name in code and the instance name in configuration consistent.

The factory hides implementation details. The service only needs to know the `ReactiveCircuitBreakerFactory` and `ReactiveCircuitBreaker` interfaces. As a result, dependency-calling logic is less tightly coupled to Resilience4j, making it easier to swap implementations or adjust configuration across environments.

Example of injecting the factory into a service:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final ReactiveCircuitBreaker inventoryBreaker;

    public InventoryService(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.inventoryBreaker = circuitBreakerFactory.create("inventory");
    }
}
~~~

The factory's generic type parameters can vary across versions and implementations. Use the interfaces provided by Spring Cloud to keep application-layer code independent of Resilience4j's internal configuration API.

## 3. ReactiveCircuitBreaker and the run Method

`ReactiveCircuitBreaker` provides `run` methods for two common publisher types:

- `Mono<T>` represents an asynchronous result that may emit zero or one value.
- `Flux<T>` represents an asynchronous sequence of zero, one, or many elements.

For `Mono`, the signature looks like:

~~~java
<T> Mono<T> run(
        Mono<T> toRun,
        Function<Throwable, Mono<T>> fallback);
~~~

For `Flux`, the signature looks like:

~~~java
<T> Flux<T> run(
        Flux<T> toRun,
        Function<Throwable, Flux<T>> fallback);
~~~

The `toRun` parameter is the publisher executing the call to protect. The `fallback` parameter is a function that receives the failure cause and returns an alternative publisher with the same element type.

Example with `Mono`:

~~~java
Mono<Inventory> result = inventoryBreaker.run(
        inventoryClient.findInventory(sku),
        error -> Mono.just(Inventory.unavailable(sku))
);
~~~

Example with `Flux`:

~~~java
Flux<Inventory> result = inventoryBreaker.run(
        inventoryClient.findAllInventory(),
        error -> inventoryCache.findAllAvailable()
);
~~~

A `Mono` fallback must return a `Mono` of the same data type. A `Flux` fallback must return a `Flux` of the same element type. You cannot return a `Mono` from the fallback of a `Flux` call or vice versa.

Publishers in Reactor are lazy: creating a `Mono` or `Flux` does not mean the request has been sent yet. A publisher starts executing only upon subscription. `ReactiveCircuitBreaker` wraps the publisher to observe that execution. Therefore, do not call `subscribe()` inside the service just to trigger the call; return the publisher to the upper calling layer so the entire pipeline can be composed and subscribed at the right point.

## 4. Integrating with WebClient

A common case is a service using `WebClient` to call an inventory service. The Spring Cloud CircuitBreaker reactive starter for Resilience4j can be added to the application:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
~~~

Manage Spring Cloud versions with a BOM compatible with the Spring Boot version in use. Avoid picking an individual starter version manually while ignoring the project's compatibility matrix.

Example of a service protecting a `WebClient` call:

~~~java
import java.time.Duration;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class InventoryClient {

    private final WebClient webClient;
    private final ReactiveCircuitBreaker inventoryBreaker;

    public InventoryClient(
            WebClient.Builder webClientBuilder,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.webClient = webClientBuilder
                .baseUrl("http://inventory-service")
                .build();
        this.inventoryBreaker = circuitBreakerFactory.create("inventory");
    }

    public Mono<Inventory> findInventory(String sku) {
        Mono<Inventory> remoteCall = webClient.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class)
                .timeout(Duration.ofSeconds(2));

        return inventoryBreaker.run(
                remoteCall,
                error -> fallback(sku, error)
        );
    }

    private Mono<Inventory> fallback(String sku, Throwable error) {
        return Mono.just(Inventory.unavailable(sku));
    }
}
~~~

`Inventory` is an application data type; the `unavailable` method in the example represents constructing a degraded result according to the business model. Replace them with your project's actual model and fallback policy.

In this example, the timeout is placed on the `remoteCall` publisher before passing it into `run`. When the call exceeds two seconds, Reactor emits a timeout error and the Circuit Breaker can record that outcome according to its error classification policy. If the timeout is placed at an outer layer not observed by the Circuit Breaker, the breaker's measurements may not accurately reflect the wait time actually experienced by the caller.

`WebClient` emits an error for unsuccessful HTTP responses when using `retrieve()` with default settings. Decide which status codes represent infrastructure failures and which represent normal business outcomes. For example, 404 may mean the product does not exist rather than the inventory service being broken. You can handle and classify HTTP errors before letting them reach the Circuit Breaker.

## 5. Writing Fallbacks Properly

A fallback is an alternative publisher used when the primary call emits an error or is rejected by an `OPEN` Circuit Breaker. The fallback function receives a `Throwable`, so it can inspect the cause to select how to respond:

~~~java
private Mono<Inventory> fallback(String sku, Throwable error) {
    if (error instanceof CallNotPermittedException) {
        return cachedInventory(sku);
    }

    if (error instanceof TimeoutException) {
        return cachedInventory(sku);
    }

    return Mono.error(error);
}
~~~

The example above illustrates branching by error type; import the appropriate exception classes and define `cachedInventory` according to your application. If cached data is unavailable or a safe degraded result cannot be produced, the fallback can propagate the error via `Mono.error` for the caller to handle. Do not turn every error into a fake success response.

A good fallback should follow these principles:

- **Same data type**: `Mono<T>` must be replaced by `Mono<T>`; `Flux<T>` must be replaced by `Flux<T>`.
- **Do not block the event loop**: avoid `block()`, synchronous I/O calls, or blocking on `Future` inside a fallback.
- **Business-meaningful**: return cached data, a temporary status, or a well-defined degraded result.
- **Do not hide incidents**: log and record metrics about the fallback cause, distinguishing timeouts, remote errors, and calls rejected by the Circuit Breaker.
- **Do not introduce another fragile dependency**: a fallback calling another remote service can introduce a second point of failure.

A fallback is not a retry. Retry re-invokes the primary operation according to a retry policy; fallback provides an alternative flow when the primary operation cannot deliver a result. The two mechanisms can be combined, but total attempts and overall duration must be bounded.

## 6. Protecting Flux and Handling Multi-Element Streams

With `Flux`, an error can occur after several elements have already been emitted. When the publisher emits an `onError` signal, the original stream terminates. `ReactiveCircuitBreaker` can switch to the provided fallback publisher. The fallback must be designed to match the application's data semantics.

For example, an API returning a list of inventory items:

~~~java
public Flux<Inventory> findAllInventory() {
    Flux<Inventory> remoteStream = webClient.get()
            .uri("/inventory")
            .retrieve()
            .bodyToFlux(Inventory.class)
            .timeout(Duration.ofSeconds(3));

    return inventoryBreaker.run(
            remoteStream,
            error -> inventoryCache.findAllAvailable()
    );
}
~~~

If `remoteStream` errors, the fallback returns a `Flux` from the cache. Clearly define how stale cached data is allowed to be and whether the caller needs to know the result came from cache. If the API needs to distinguish live data from degraded data, represent the data source in the response type or business metadata.

Do not default fallbacks to `Flux.empty()` for every error. An empty stream can be misinterpreted by callers as the dependency operating normally with no data. If the error truly matters, propagate the error or return a recognizable degraded state.

## 7. Combining Timeout and Circuit Breaker

`ReactiveCircuitBreaker` observes the outcome of a publisher; `timeout` defines the waiting limit for that publisher. The two mechanisms can work together to prevent a slow call from holding resources too long and to give the Circuit Breaker data to detect a degrading dependency.

Example:

~~~java
Mono<Product> remoteCall = webClient.get()
        .uri("/products/{id}", productId)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(2));

return productBreaker.run(
        remoteCall,
        error -> productCache.find(productId)
);
~~~

When the timeout is placed inside the publisher passed to `run`, the timeout becomes an error that the Circuit Breaker can record. When the failure rate or slow-call rate reaches the threshold, the Circuit Breaker can transition to `OPEN` and reject new calls during the wait duration.

Distinguish per-call timeout from the deadline of the entire request. If a request has multiple dependencies or retries, total processing time can exceed a single publisher's timeout. Account for wait time, retries, fallback execution, and upper-layer processing so the overall SLA is not violated.

## 8. Configuring by ID and Managing Multiple Dependencies

Each dependency has different latency, traffic, and reliability characteristics. Assign distinct IDs to Circuit Breakers with different operational policies. For example:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
      payment:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 20
        failureRateThreshold: 40
        waitDurationInOpenState: 15s
~~~

In code, create breakers with the exact matching IDs:

~~~java
this.inventoryBreaker = circuitBreakerFactory.create("inventory");
this.paymentBreaker = circuitBreakerFactory.create("payment");
~~~

Do not share a single ID across dependencies with different failure characteristics if they need separate monitoring and tuning. Conversely, do not create new IDs per request or per high-cardinality value. Increasing the number of instances increases the state and statistical resources that must be maintained.

If the application uses multiple profiles, set appropriate configurations for each environment. Development configurations can be simpler for testing; production configurations should be based on traffic, SLAs, and real-world metrics.

## 9. Monitoring and Observing Reactive Breaker Behavior

Resilience4j can integrate with Micrometer and Spring Boot Actuator to export metrics. When the corresponding endpoints and registries are enabled, monitoring systems can track the health of each breaker.

Metrics worth tracking include:

- Current state of each breaker: `CLOSED`, `OPEN`, or `HALF_OPEN`.
- Counts of successful, failed, slow, and rejected calls.
- Number of fallback invocations and the cause types triggering fallback.
- Latency of the primary publisher and final response time after fallback.
- Rates of timeouts, HTTP errors, and connection errors per dependency.
- Number of breaker instances and changes over time.

Metrics should carry just enough tags to distinguish dependencies. Avoid putting request IDs, user IDs, or high-cardinality dynamic values into metric tags. Details needed to trace a specific request belong in distributed traces and correlated logs.

When a breaker opens frequently, inspect the dependency's underlying latency and root errors, timeouts, statistical thresholds, and exception classification rules. When fallback invocations spike while overall request success rate still looks high, surface the fallback rate separately so dashboards do not mask quality degradation.

## 10. Common Mistakes When Using the Reactive API

- **Using synchronous `CircuitBreakerFactory` for reactive publishers**: choose `ReactiveCircuitBreakerFactory` when the protected call returns `Mono` or `Flux` to preserve the reactive execution model.
- **Mismatched configuration ID**: the ID passed to `create` must match the instance name in the Resilience4j configuration.
- **Wrong fallback publisher type**: `Mono` and `Flux` fallbacks are not interchangeable.
- **Calling `block()` in a WebFlux flow**: blocking operations can occupy event-loop threads and reduce concurrency.
- **Calling `subscribe()` manually inside a service**: this detaches the call from the caller-managed reactive chain and can break composition, error handling, or lifecycle management.
- **Fallback always returning dummy data**: callers may mistake degraded data for fresh data.
- **Not classifying business errors**: errors like 404 may be counted as dependency failures if not handled appropriately.
- **Placing timeout in the wrong layer**: the Circuit Breaker may fail to record timeout errors if the timeout sits outside the protected publisher.
- **Fallback calling an unprotected remote service**: failures can cascade to a second dependency and spread further.

## 11. Implementation Workflow

When integrating `ReactiveCircuitBreakerFactory` and `ReactiveCircuitBreaker` into a WebFlux service, you can follow these steps:

1. Add the Resilience4j reactive starter and use a BOM compatible with Spring Boot.
2. Inject `ReactiveCircuitBreakerFactory` into the service or dependency client class.
3. Create the breaker with a stable ID representing the dependency to protect.
4. Declare Resilience4j configuration with the same ID in `application.yml`.
5. Build the `Mono` or `Flux` for the `WebClient` call and apply an appropriate timeout.
6. Pass the publisher and matching-type fallback into `ReactiveCircuitBreaker.run`.
7. Design a fallback that is business-meaningful, non-blocking, and observable.
8. Monitor state, error metrics, timeouts, and fallback rates in the actual runtime environment.

`ReactiveCircuitBreakerFactory` provides a way to create breakers by ID; `ReactiveCircuitBreaker.run` applies protection to `Mono` and `Flux`. With matching publisher types, consistent configuration IDs, proper timeouts, and carefully designed fallbacks, Spring Cloud applications can protect reactive dependency calls while preserving Reactor's asynchronous nature.
